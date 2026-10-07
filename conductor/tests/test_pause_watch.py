"""conductor/pause_watch.py and its wiring into conductor/cycle.py
(handoffs/2026-10-05-pause-safety.md): the pause watchdog's decision table,
its executor over a fake fort, and the cycle integration. No VM, no model.

The fake fort is the point: it models a game that is paused behind a popup,
a game whose resume does or does not make the tick advance, and a tripwire
latch, so the tests prove the hard lines (never resume over a latch or an
escalation; dismiss is not resume; one resume per episode) against the real
executor code, not a re-description of it.
"""

from __future__ import annotations

import json

import pytest

from conductor.cursors import CursorStore
from conductor.mcp_client import FakeToolCaller, MCPToolError
from conductor.pause_watch import (
    OWNED_ESCALATION, Observation, PausePolicy, PausePolicyError, PauseWatchStore, Verdict, WatchState,
    classify_causes, decide, finish_after_overseer, liveness_due, load_pause_policy, read_verdict_after,
    read_verdict_baseline, run_pause_watch,
)

POLICY = load_pause_policy()  # the real, committed conductor/pause_policy.yaml
NOW = 1_000_000.0
TICK = 403200 * 3 + 5000


def _obs(**kw):
    base = dict(paused=True, cause="plain_pause", abs_tick=TICK)
    base.update(kw)
    return Observation(**base)


def _succession(tick=TICK):
    return dict(report_types=("FORT_POSITION_SUCCESSION",), report_ticks=(tick,), cause="announcement")


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------


def test_the_committed_policy_loads_and_never_lists_a_threat_as_harmless():
    harmless = set(POLICY.harmless_announcements)
    assert "FORT_POSITION_SUCCESSION" in harmless
    for threat in (
        "MEGABEAST_ARRIVAL", "WEREBEAST_ARRIVAL", "NIGHT_ATTACK_STARTS", "UNDEAD_ATTACK",
        "AMBUSH_HERO", "CRIME_WITNESS_HANDOFF", "ENDGAME_EVENT_1", "DEITY_CURSE",
        "EMERGENCY_TACTICAL_CONTROL",
    ):
        assert threat not in harmless


def test_a_bad_policy_is_an_error_not_a_default(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("schema_version: 1\nharmless_announcements: oops\n", encoding="utf-8")
    with pytest.raises(PausePolicyError):
        load_pause_policy(bad)
    with pytest.raises(PausePolicyError):
        load_pause_policy(tmp_path / "missing.yaml")


# ---------------------------------------------------------------------------
# decide: the table
# ---------------------------------------------------------------------------


def test_not_paused_is_idle():
    assert decide(_obs(paused=False), POLICY, WatchState(), NOW).verdict is Verdict.IDLE


def test_a_latched_tripwire_wins_over_everything_including_a_harmless_cause():
    obs = _obs(tripwire={"reason": "death"}, popups_pending=1, **_succession())
    assert decide(obs, POLICY, WatchState(), NOW).verdict is Verdict.TRIPWIRE


def test_an_overseer_escalation_owns_the_pause_even_with_a_harmless_cause():
    state = WatchState(owned=OWNED_ESCALATION)
    assert decide(_obs(**_succession()), POLICY, state, NOW).verdict is Verdict.OWNED


def test_a_non_play_screen_alerts_the_human():
    d = decide(_obs(cause="modal_viewscreen", viewscreen_type="viewscreen_savegamest"), POLICY, WatchState(), NOW)
    assert d.verdict is Verdict.ALERT


def test_a_pending_popup_is_dismissed_not_resumed():
    assert decide(_obs(popups_pending=1, cause="popup"), POLICY, WatchState(), NOW).verdict is Verdict.DISMISS


def test_a_failed_dismiss_or_the_cap_alerts():
    assert decide(_obs(popups_pending=1), POLICY, WatchState(dismiss_failed=True), NOW).verdict is Verdict.ALERT
    assert decide(_obs(popups_pending=1), POLICY, WatchState(dismissed=POLICY.dismiss_cap), NOW).verdict is Verdict.ALERT


def test_a_recent_harmless_cause_resumes():
    assert decide(_obs(**_succession()), POLICY, WatchState(), NOW).verdict is Verdict.RESUME


def test_a_harmless_report_that_is_not_tied_to_this_pause_is_a_hold():
    old = _succession(tick=TICK - 5000)  # well outside cause_slack_ticks
    assert decide(_obs(**old), POLICY, WatchState(), NOW).verdict is Verdict.WAKE_OVERSEER


def test_a_dismissed_popup_ties_an_older_harmless_report_to_the_pause():
    old = _succession(tick=TICK - 500)
    assert decide(_obs(**old), POLICY, WatchState(dismissed=1), NOW).verdict is Verdict.RESUME


@pytest.mark.parametrize("name", ["MEGABEAST_ARRIVAL", "NIGHT_ATTACK_STARTS", "SOME_FUTURE_TYPE"])
def test_a_threat_or_unknown_cause_wakes_the_overseer(name):
    obs = _obs(report_types=(name,), report_ticks=(TICK,), cause="announcement")
    assert decide(obs, POLICY, WatchState(), NOW).verdict is Verdict.WAKE_OVERSEER


def test_one_threat_among_harmless_causes_is_still_a_hold():
    obs = _obs(report_types=("FORT_POSITION_SUCCESSION", "MEGABEAST_ARRIVAL"), report_ticks=(TICK, TICK))
    assert classify_causes(obs, POLICY, popup_dismissed=True) == "hold"
    assert decide(obs, POLICY, WatchState(), NOW).verdict is Verdict.WAKE_OVERSEER


def test_a_plain_pause_waits_out_the_grace_then_wakes_the_overseer():
    state = WatchState(episode_started=NOW)
    assert decide(_obs(), POLICY, state, NOW + 60).verdict is Verdict.WAIT
    assert decide(_obs(), POLICY, state, NOW + POLICY.plain_pause_grace_seconds + 1).verdict is Verdict.WAKE_OVERSEER


def test_an_episode_already_handled_is_held_not_retried():
    assert decide(_obs(**_succession()), POLICY, WatchState(resume_attempts=1), NOW).verdict is Verdict.HELD
    assert decide(_obs(**_succession()), POLICY, WatchState(overseer_woken=True), NOW).verdict is Verdict.HELD


def test_liveness_fires_once_per_interval():
    state = WatchState(episode_started=NOW)
    assert not liveness_due(state, POLICY, NOW + 10)
    assert liveness_due(state, POLICY, NOW + POLICY.liveness_limit_seconds)
    state.last_alert = NOW + POLICY.liveness_limit_seconds
    assert not liveness_due(state, POLICY, NOW + POLICY.liveness_limit_seconds + 10)
    assert liveness_due(state, POLICY, NOW + 2 * POLICY.liveness_limit_seconds)
    assert not liveness_due(WatchState(), POLICY, NOW + 10 ** 6)


# ---------------------------------------------------------------------------
# the executor, over a fake fort
# ---------------------------------------------------------------------------


class FakeFort:
    def __init__(self, *, paused=True, popups=0, reports=(), tripwire=None, resume_moves_tick=True,
                 dismiss_works=True, viewscreen="viewscreen_dwarfmodest", why_available=True,
                 verdict=None, verdict_store_down=False, blocking_panel=None):
        self.paused = paused
        self.tick = TICK
        self.popups = popups
        self.reports = list(reports)
        self.tripwire = tripwire
        self.resume_moves_tick = resume_moves_tick
        self.dismiss_works = dismiss_works
        self.viewscreen = viewscreen
        self.why_available = why_available
        self.resume_calls = 0
        #: An open in-game panel that blocks resume (2026-10-08, Work Orders): {name, focus} or None.
        self.blocking_panel = blocking_panel
        #: The Overseer's pause.verdict, as the store would show it once the
        #: Overseer's run has written it: None (silence) or {"resume", "reason"}.
        self.verdict = verdict
        self.verdict_store_down = verdict_store_down
        self._verdict_reads = 0

    def verdict_read(self, _a=None):
        if self.verdict_store_down:
            raise MCPToolError("unknown tool pause.verdict_read")
        self._verdict_reads += 1
        if self._verdict_reads == 1:  # the baseline read, before the Overseer runs
            return {"latest_id": 0, "verdicts": []}
        rows = [{"id": 1, "at": "t", **self.verdict}] if self.verdict else []
        return {"latest_id": len(rows), "verdicts": rows}

    def status(self, _a=None):
        out = {"paused": self.paused, "fps": 100, "abs_tick": self.tick, "armed": True, "tripwire": self.tripwire}
        if self.blocking_panel:
            out["blocking_panel"] = self.blocking_panel
        return out

    def why(self, _a=None):
        if not self.why_available:
            raise MCPToolError("unknown tool pause.why")
        if self.tripwire:
            cause = "tripwire"
        elif self.viewscreen != "viewscreen_dwarfmodest":
            cause = "modal_viewscreen"
        elif self.popups:
            cause = "popup"
        elif self.reports:
            cause = "announcement"
        else:
            cause = "plain_pause"
        return {
            "ok": True, "paused": self.paused, "cause": cause, "popups_pending": self.popups,
            "viewscreen_type": self.viewscreen, "recent_reports": list(self.reports),
        }

    def dismiss(self, args):
        closed = []
        while self.popups and len(closed) < args.get("max", 5) and self.dismiss_works:
            self.popups -= 1
            closed.append({"kind": "mega", "strategy": "click_text", "said": "Meng has claimed the position of queen."})
        return {"ok": self.popups == 0, "dismissed": closed, "remaining": self.popups}

    def resume(self, _a=None):
        self.resume_calls += 1
        if self.tripwire:
            raise MCPToolError("refused: a tripwire is latched")
        if self.blocking_panel:
            # The real game: SetPauseState(false) is a no-op behind the panel.
            return {"ok": True, "paused": True, "blocking_panel": self.blocking_panel, "warning": "a panel is open"}
        self.paused = False
        return {"ok": True, "paused": False}

    def clear(self, _a=None):
        had = self.tripwire is not None
        self.tripwire = None
        return {"ok": True, "had_latch": had}

    def pause(self, _a=None):
        self.paused = True
        return {"ok": True, "paused": True}

    async def sleep(self, _seconds):
        if not self.paused and self.resume_moves_tick and not self.blocking_panel:
            self.tick += 700

    def tool_map(self):
        return {
            "clock.status": self.status, "pause.why": self.why, "pause.dismiss": self.dismiss,
            "clock.resume": self.resume, "clock.pause": self.pause, "clock.clear": self.clear,
            "pause.verdict_read": self.verdict_read,
        }

    def tools(self):
        return FakeToolCaller(self.tool_map())


def _report(name="FORT_POSITION_SUCCESSION", tick=TICK):
    return {"id": 1, "type": name, "flags": ["DO_MEGA"], "tick": tick, "text": "x"}


async def _run(fort, store, *, now=NOW, dry_run=False, tools=None):
    caller = tools or fort.tools()
    status = fort.status()
    out = await run_pause_watch(
        caller.call_tool, store, POLICY, clock_status=status, now=now, sleep=fort.sleep, dry_run=dry_run,
    )
    return out, caller


@pytest.mark.asyncio
async def test_the_succession_case_dismisses_then_resumes_and_verifies_the_tick(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    store = PauseWatchStore(tmp_path / "pw.json")
    out, caller = await _run(fort, store)
    assert out.resumed is True and out.still_paused is False
    called = [c[0] for c in caller.calls]
    assert called.index("pause.dismiss") < called.index("clock.resume")
    assert fort.paused is False and fort.tick > TICK
    # The episode is over: nothing owed, state cleared.
    state = store.load()
    assert state.episode_started is None and state.resume_attempts == 0
    assert any(h["kind"] == "dismissed" and "queen" in h["detail"]["said"] for h in state.history)


@pytest.mark.asyncio
async def test_a_resume_whose_tick_does_not_move_pauses_again_alerts_and_never_retries(tmp_path):
    fort = FakeFort(reports=[_report()], resume_moves_tick=False)
    store = PauseWatchStore(tmp_path / "pw.json")
    out, caller = await _run(fort, store)
    assert out.resumed is False and out.verdict is Verdict.ALERT
    assert out.alerts and "did not move" in out.alerts[0]["reason"]
    assert fort.paused is True  # back to the safe state
    assert fort.resume_calls == 1
    # Next cycle: held, no second resume.
    out2, _ = await _run(fort, store, now=NOW + 30)
    assert out2.verdict is Verdict.HELD
    assert fort.resume_calls == 1


@pytest.mark.asyncio
async def test_a_threat_is_never_resumed_and_the_overseer_is_woken(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")])
    out, caller = await _run(fort, PauseWatchStore(tmp_path / "pw.json"))
    assert out.verdict is Verdict.WAKE_OVERSEER
    assert "MEGABEAST_ARRIVAL" in out.wake_detail
    assert fort.resume_calls == 0
    assert out.still_paused is True


@pytest.mark.asyncio
async def test_a_latched_tripwire_is_never_touched_and_pause_why_is_not_even_read(tmp_path):
    fort = FakeFort(popups=2, reports=[_report()], tripwire={"reason": "death", "tick": 1, "detail": "x"})
    out, caller = await _run(fort, PauseWatchStore(tmp_path / "pw.json"))
    assert out.verdict is Verdict.TRIPWIRE
    assert [c[0] for c in caller.calls] == []
    assert fort.resume_calls == 0 and fort.popups == 2


@pytest.mark.asyncio
async def test_an_owned_escalation_pause_is_never_resumed_even_for_a_harmless_cause(tmp_path):
    fort = FakeFort(reports=[_report()])
    store = PauseWatchStore(tmp_path / "pw.json")
    store.mark_owned(OWNED_ESCALATION, NOW)
    out, caller = await _run(fort, store, now=NOW + 5)
    assert out.verdict is Verdict.OWNED
    assert fort.resume_calls == 0
    assert "clock.resume" not in [c[0] for c in caller.calls]


@pytest.mark.asyncio
async def test_an_owned_pause_alerts_the_human_at_the_liveness_limit(tmp_path):
    fort = FakeFort()
    store = PauseWatchStore(tmp_path / "pw.json")
    store.mark_owned(OWNED_ESCALATION, NOW)
    out, _ = await _run(fort, store, now=NOW + POLICY.liveness_limit_seconds + 1)
    assert out.verdict is Verdict.OWNED
    assert out.alerts and "liveness" in out.alerts[0]["reason"]


@pytest.mark.asyncio
async def test_a_failed_dismiss_alerts_and_does_not_resume(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()], dismiss_works=False)
    out, _ = await _run(fort, PauseWatchStore(tmp_path / "pw.json"))
    assert out.verdict is Verdict.ALERT
    assert fort.resume_calls == 0 and fort.paused is True


@pytest.mark.asyncio
async def test_a_stuck_screen_alerts_at_once_and_dismisses_nothing(tmp_path):
    fort = FakeFort(viewscreen="viewscreen_savegamest", popups=1)
    out, caller = await _run(fort, PauseWatchStore(tmp_path / "pw.json"))
    assert out.verdict is Verdict.ALERT
    assert "pause.dismiss" not in [c[0] for c in caller.calls]


@pytest.mark.asyncio
async def test_a_plain_pause_waits_then_wakes_the_overseer_after_the_grace(tmp_path):
    fort = FakeFort()
    store = PauseWatchStore(tmp_path / "pw.json")
    out, _ = await _run(fort, store, now=NOW)
    assert out.verdict is Verdict.WAIT and out.wake_detail is None
    out2, _ = await _run(fort, store, now=NOW + POLICY.plain_pause_grace_seconds + 5)
    assert out2.verdict is Verdict.WAKE_OVERSEER
    # The wake is spent: the next pass holds rather than waking again.
    out3, _ = await _run(fort, store, now=NOW + POLICY.plain_pause_grace_seconds + 60)
    assert out3.verdict is Verdict.HELD


@pytest.mark.asyncio
async def test_an_undeployed_pause_why_degrades_to_waiting_then_a_liveness_alert(tmp_path):
    fort = FakeFort(why_available=False)
    store = PauseWatchStore(tmp_path / "pw.json")
    out, _ = await _run(fort, store, now=NOW)
    assert out.verdict is Verdict.WAIT
    late, _ = await _run(fort, store, now=NOW + POLICY.liveness_limit_seconds + 1)
    assert late.alerts  # liveness still fires with no why read at all
    assert fort.resume_calls == 0


@pytest.mark.asyncio
async def test_dry_run_reads_and_decides_but_changes_nothing(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    store = PauseWatchStore(tmp_path / "pw.json")
    out, caller = await _run(fort, store, dry_run=True)
    assert out.verdict is Verdict.DISMISS
    assert fort.popups == 1 and fort.resume_calls == 0
    assert not (tmp_path / "pw.json").exists()
    assert [c[0] for c in caller.calls] == ["pause.why"]


@pytest.mark.asyncio
async def test_the_running_fort_ends_any_episode(tmp_path):
    store = PauseWatchStore(tmp_path / "pw.json")
    store.mark_owned(OWNED_ESCALATION, NOW)
    fort = FakeFort(paused=False)
    out, _ = await _run(fort, store, now=NOW + 5)
    assert out.verdict is Verdict.IDLE
    assert store.load().owned is None


@pytest.mark.asyncio
async def test_a_frozen_unpaused_fort_behind_a_popup_is_dismissed(tmp_path):
    fort = FakeFort(paused=False, popups=1)
    store = PauseWatchStore(tmp_path / "pw.json")
    await _run(fort, store, now=NOW)                      # first sight of this tick
    out, _ = await _run(fort, store, now=NOW + POLICY.frozen_after_seconds + 1)
    assert fort.popups == 0
    assert "frozen" in out.reason


@pytest.mark.asyncio
async def test_a_frozen_unpaused_fort_with_no_popup_alerts(tmp_path):
    fort = FakeFort(paused=False)
    store = PauseWatchStore(tmp_path / "pw.json")
    await _run(fort, store, now=NOW)
    out, _ = await _run(fort, store, now=NOW + POLICY.frozen_after_seconds + 1)
    assert out.alerts and "not advancing" in out.alerts[0]["reason"]


@pytest.mark.asyncio
async def test_a_moving_tick_is_never_frozen(tmp_path):
    fort = FakeFort(paused=False)
    store = PauseWatchStore(tmp_path / "pw.json")
    await _run(fort, store, now=NOW)
    fort.tick += 500
    out, _ = await _run(fort, store, now=NOW + 10 * POLICY.frozen_after_seconds)
    assert out.verdict is Verdict.IDLE and not out.alerts


@pytest.mark.asyncio
async def test_after_the_overseer_a_clean_run_resumes_and_an_escalation_does_not(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")])
    store = PauseWatchStore(tmp_path / "pw.json")
    out, caller = await _run(fort, store)
    assert out.verdict is Verdict.WAKE_OVERSEER

    esc = await finish_after_overseer(
        caller.call_tool, store, POLICY, escalated=True, clock_status=fort.status(), now=NOW + 1, sleep=fort.sleep,
    )
    assert esc.alerts and fort.resume_calls == 0 and fort.paused is True
    assert store.load().owned == OWNED_ESCALATION

    # A fresh episode, an explicit resume=true verdict: the only resume.
    fort2 = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")])
    store2 = PauseWatchStore(tmp_path / "pw2.json")
    out2, caller2 = await _run(fort2, store2)
    fin = await finish_after_overseer(
        caller2.call_tool, store2, POLICY, escalated=False, clock_status=fort2.status(), now=NOW + 1,
        sleep=fort2.sleep, verdict={"resume": True, "reason": "a visiting trader, nothing hostile"},
    )
    assert fin.resumed is True and fort2.paused is False


async def _after_overseer(tmp_path, verdict, *, escalated=False, resume_moves_tick=True):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")], resume_moves_tick=resume_moves_tick)
    store = PauseWatchStore(tmp_path / "pw.json")
    await _run(fort, store)
    fin = await finish_after_overseer(
        fort.tools().call_tool, store, POLICY, escalated=escalated, clock_status=fort.status(),
        now=NOW + 1, sleep=fort.sleep, verdict=verdict,
    )
    return fort, store, fin


@pytest.mark.asyncio
async def test_no_verdict_keeps_the_fort_paused_and_alerts(tmp_path):
    fort, store, fin = await _after_overseer(tmp_path, None)
    assert fin.resumed is False and fort.resume_calls == 0 and fort.paused is True
    assert fin.verdict is Verdict.ALERT and fin.alerts and "no verdict" in fin.alerts[0]["reason"]
    assert fin.alert["reason"] == store.load().alert_reason


@pytest.mark.asyncio
async def test_a_false_verdict_keeps_the_fort_paused_and_alerts_with_the_reason(tmp_path):
    fort, store, fin = await _after_overseer(tmp_path, {"resume": False, "reason": "a siege may be forming"})
    assert fin.resumed is False and fort.resume_calls == 0 and fort.paused is True
    assert fin.alerts and "siege may be forming" in fin.alerts[0]["reason"]


@pytest.mark.asyncio
async def test_a_true_verdict_resumes_once_and_verifies_the_tick(tmp_path):
    fort, store, fin = await _after_overseer(tmp_path, {"resume": True, "reason": "harmless"})
    assert fin.resumed is True and fort.resume_calls == 1 and fort.paused is False
    assert store.load().episode_started is None and store.load().alert_reason is None


@pytest.mark.asyncio
async def test_a_true_verdict_whose_resume_does_not_move_the_tick_pauses_again_and_alerts(tmp_path):
    fort, store, fin = await _after_overseer(tmp_path, {"resume": True, "reason": "ok"}, resume_moves_tick=False)
    assert fin.resumed is False and fort.paused is True and fin.alerts


@pytest.mark.asyncio
async def test_an_escalation_overrides_even_a_true_verdict(tmp_path):
    fort, store, fin = await _after_overseer(tmp_path, {"resume": True, "reason": "ok"}, escalated=True)
    assert fort.resume_calls == 0 and fort.paused is True
    assert store.load().owned == OWNED_ESCALATION


@pytest.mark.asyncio
async def test_baseline_and_after_reads_only_count_a_verdict_written_after_the_baseline():
    fort = FakeFort(verdict={"resume": True, "reason": "x"})
    call = fort.tools().call_tool
    base = await read_verdict_baseline(call)
    assert base == 0
    assert (await read_verdict_after(call, base)) == {"resume": True, "reason": "x"}
    assert (await read_verdict_after(call, None)) is None  # no baseline: safe direction
    down = FakeFort(verdict_store_down=True).tools().call_tool
    assert (await read_verdict_baseline(down)) is None
    assert (await read_verdict_after(down, 0)) is None


@pytest.mark.asyncio
async def test_the_plain_pause_grace_wait_is_waiting_on_a_human_and_a_hold_carries_the_alert(tmp_path):
    fort = FakeFort()
    store = PauseWatchStore(tmp_path / "pw.json")
    out, _ = await _run(fort, store)
    assert out.verdict is Verdict.WAIT and out.waiting_on_human is True and out.alert is None
    assert out.as_dict()["waiting_on_human"] is True
    # A stuck screen alerts at once; the next pass still carries the standing alert.
    fort2 = FakeFort(viewscreen="viewscreen_titlest")
    store2 = PauseWatchStore(tmp_path / "pw2.json")
    first, _ = await _run(fort2, store2)
    assert first.alert and first.alert["since"] == NOW
    later, _ = await _run(fort2, store2, now=NOW + 5)
    assert later.alert and later.alert["since"] == NOW and later.waiting_on_human is False


# ---------------------------------------------------------------------------
# state file
# ---------------------------------------------------------------------------


def test_state_round_trips_and_a_corrupt_file_is_an_error(tmp_path):
    store = PauseWatchStore(tmp_path / "s.json")
    s = WatchState(episode_started=5.0, owned="escalation", dismissed=2)
    s.note(1.0, "x", {"a": 1})
    store.save(s)
    back = store.load()
    assert back.owned == "escalation" and back.dismissed == 2 and back.history[0]["kind"] == "x"
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PausePolicyError):
        PauseWatchStore(tmp_path / "bad.json").load()


# ---------------------------------------------------------------------------
# cycle integration
# ---------------------------------------------------------------------------

from conductor.archive import CycleArchive  # noqa: E402
from conductor.cycle import CycleDeps, run_cycle  # noqa: E402
from conductor.mcp_client import tool_name  # noqa: E402
from conductor.policy import PAUSED, load_policy  # noqa: E402
from conductor.runner import FakeRoleRunner, RunResult  # noqa: E402
from conductor.tests.test_cycle import (  # noqa: E402
    CHARTERS, MODELS, _base_tools, _diff_sequence,
)


def _cycle_deps(tmp_path, fort, *, runner=None, extra=None):
    tools = _base_tools()
    tools.update(fort.tool_map())
    tools["clock.status"] = lambda _a=None: {**fort.status(), "cur_year": 3, "cur_year_tick": 5000}
    tools["diff.since"] = _diff_sequence()
    if extra:
        tools.update(extra)
    cursor_store = CursorStore(tmp_path / "cursors.json")
    cursor_store.set("__routine_review__", 403200 + 1000)
    return CycleDeps(
        tool_caller=FakeToolCaller(tools), role_runner=runner or FakeRoleRunner(), policy=load_policy(),
        cursor_store=cursor_store, archive=CycleArchive(tmp_path / "cycles"),
        charters=CHARTERS, models=MODELS, wall_clock=lambda: NOW, pause_sleep=fort.sleep,
    )


def _ok_run(role="overseer", tools=()):
    return RunResult(
        role=role, ok=True, status="ok", cost_usd=0.0, wall_clock_seconds=1.0, timed_out=False,
        tool_summary={"tools": list(tools)}, final_answer="done", raw={},
    )


@pytest.mark.asyncio
async def test_cycle_a_harmless_self_pause_is_cleared_and_the_cycle_goes_on(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert result.pause_watch["resumed"] is True
    assert fort.paused is False
    assert deps.role_runner.calls == []  # nobody needed waking for a notice


@pytest.mark.asyncio
async def test_cycle_a_threat_pause_wakes_only_the_overseer_with_the_unexplained_pause_reason(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")])
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert [c["role"] for c in deps.role_runner.calls] == ["overseer"]
    briefing = json.loads(deps.role_runner.calls[0]["prompt"])
    assert briefing["wake_reason"] == "unexplained_pause"
    assert "MEGABEAST_ARRIVAL" in json.dumps(briefing)
    assert result.roles_woken == ("overseer",)
    # Silence is not consent: no pause.verdict from the run, so it stays paused.
    assert fort.paused is True and result.pause_watch["resumed"] is False
    assert fort.resume_calls == 0
    assert result.pause_watch["alert"]["reason"].startswith("the Overseer gave no verdict")


@pytest.mark.asyncio
async def test_cycle_an_explicit_resume_true_verdict_from_the_run_resumes_once(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")], verdict={"resume": True, "reason": "harmless"})
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert fort.paused is False and fort.resume_calls == 1 and result.pause_watch["resumed"] is True
    assert result.pause_watch["alert"] is None


@pytest.mark.asyncio
async def test_cycle_a_false_verdict_holds_and_the_standing_alert_reaches_the_status_block(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")], verdict={"resume": False, "reason": "unsure"})
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert fort.paused is True and fort.resume_calls == 0
    from conductor.status import status_from_cycle
    block = status_from_cycle(result)["pause_watch"]
    assert block["alert"]["reason"].startswith("the Overseer says do not resume")
    # The next cycle holds (episode handled) and still carries the alert.
    result2 = await run_cycle(2, _cycle_deps(tmp_path, fort, runner=FakeRoleRunner()))
    assert result2.pause_watch["verdict"] == "held" and result2.pause_watch["alert"]


@pytest.mark.asyncio
async def test_cycle_an_unreadable_verdict_store_is_silence_not_consent(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")], verdict={"resume": True, "reason": "x"},
                    verdict_store_down=True)
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert fort.paused is True and fort.resume_calls == 0 and result.pause_watch["alert"]


@pytest.mark.asyncio
async def test_cycle_an_overseer_escalation_on_an_unexplained_pause_keeps_it_paused_and_owned(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")])
    runner = FakeRoleRunner({"overseer": _ok_run(tools=[tool_name("queue.escalate")])})
    deps = _cycle_deps(tmp_path, fort, runner=runner)
    result = await run_cycle(1, deps)
    assert result.escalated is True and result.clock_level == PAUSED
    assert fort.paused is True and fort.resume_calls == 0
    assert result.pause_watch["alerts"]

    # Next cycle: owned, so nothing is woken and nothing resumed.
    deps2 = _cycle_deps(tmp_path, fort, runner=FakeRoleRunner())
    result2 = await run_cycle(2, deps2)
    assert deps2.role_runner.calls == []
    assert result2.pause_watch["verdict"] == "owned"
    assert fort.resume_calls == 0 and fort.paused is True


@pytest.mark.asyncio
async def test_cycle_a_latched_tripwire_still_goes_through_the_tripwire_branch_only(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()], tripwire={"reason": "death", "tick": 1, "detail": "x"})
    runner = FakeRoleRunner({"overseer": _ok_run(tools=[tool_name("queue.escalate")])})
    deps = _cycle_deps(tmp_path, fort, runner=runner)
    result = await run_cycle(1, deps)
    assert result.tripwire is not None
    assert "pause.why" not in [c[0] for c in deps.tool_caller.calls]  # the watchdog never ran
    assert fort.popups == 1                    # and dismissed nothing
    assert fort.resume_calls == 0              # escalated: still paused


@pytest.mark.asyncio
async def test_cycle_an_ordinary_cycle_escalation_pause_is_recorded_as_owned(tmp_path):
    fort = FakeFort(paused=False)
    runner = FakeRoleRunner({"overseer": _ok_run(tools=[tool_name("queue.escalate")])})
    extra = {
        "queue.overview": {"proposals": {"count": 1, "proposal_ids": ["p1"]}, "asks": {"count": 0, "ask_ids": []}},
    }
    deps = _cycle_deps(tmp_path, fort, runner=runner, extra=extra)
    result = await run_cycle(1, deps)
    assert result.escalated is True
    assert PauseWatchStore(tmp_path / "pause_watch.json").load().owned == OWNED_ESCALATION
    # The fake clock.pause flipped the fort; the next cycle must not resume it.
    deps2 = _cycle_deps(tmp_path, fort)
    result2 = await run_cycle(2, deps2)
    assert result2.pause_watch["verdict"] == "owned"
    assert fort.resume_calls == 0


@pytest.mark.asyncio
async def test_cycle_a_watchdog_failure_never_fails_the_cycle(tmp_path):
    fort = FakeFort(popups=1, reports=[_report()])
    deps = _cycle_deps(tmp_path, fort)

    async def boom(*_a, **_k):
        raise RuntimeError("bug in the watchdog")

    import conductor.cycle as cycle_mod
    original = cycle_mod.run_pause_watch
    cycle_mod.run_pause_watch = boom
    try:
        result = await run_cycle(1, deps)
    finally:
        cycle_mod.run_pause_watch = original
    assert result.pause_watch is None


@pytest.mark.asyncio
async def test_cycle_a_quiet_running_fort_is_untouched_by_the_watchdog(tmp_path):
    fort = FakeFort(paused=False)
    deps = _cycle_deps(tmp_path, fort)
    result = await run_cycle(1, deps)
    assert result.pause_watch["verdict"] == "idle"
    assert result.roles_woken == ()
    assert fort.resume_calls == 0


# ---------------------------------------------------------------------------
# an open panel blocks resume (2026-10-08): report it by name, never close it
# ---------------------------------------------------------------------------

PANEL = {"name": "info_panel", "focus": "dwarfmode/Info/WORK_ORDERS/Default"}


@pytest.mark.asyncio
async def test_a_harmless_resume_blocked_by_an_open_panel_alerts_naming_the_panel(tmp_path):
    fort = FakeFort(reports=[_report()], blocking_panel=PANEL)
    store = PauseWatchStore(tmp_path / "pw.json")
    out, caller = await _run(fort, store)
    assert out.resumed is False and out.verdict is Verdict.ALERT
    assert out.blocking_panel == PANEL
    assert "dwarfmode/Info/WORK_ORDERS/Default" in out.alerts[0]["reason"]
    assert out.as_dict()["blocking_panel"] == PANEL
    # Report only: nothing tried to close it, and the fort is left paused.
    assert {c[0] for c in caller.calls} <= {"clock.status", "pause.why", "clock.resume", "clock.pause"}
    assert fort.paused is True


@pytest.mark.asyncio
async def test_a_verdict_resume_blocked_by_an_open_panel_alerts_naming_the_panel(tmp_path):
    fort = FakeFort(reports=[_report("MEGABEAST_ARRIVAL")], blocking_panel=PANEL)
    store = PauseWatchStore(tmp_path / "pw.json")
    await _run(fort, store)
    fin = await finish_after_overseer(
        fort.tools().call_tool, store, POLICY, escalated=False, clock_status=fort.status(), now=NOW + 1,
        sleep=fort.sleep, verdict={"resume": True, "reason": "safe"},
    )
    assert fin.resumed is False and fin.blocking_panel == PANEL
    assert "WORK_ORDERS" in fin.alerts[0]["reason"]


@pytest.mark.asyncio
async def test_a_frozen_unpaused_fort_behind_an_open_panel_names_it(tmp_path):
    fort = FakeFort(paused=False, blocking_panel=PANEL)
    store = PauseWatchStore(tmp_path / "pw.json")
    await _run(fort, store, now=NOW)
    out, _ = await _run(fort, store, now=NOW + POLICY.frozen_after_seconds + 1)
    assert out.blocking_panel == PANEL and "WORK_ORDERS" in out.alerts[0]["reason"]
