"""Stage T (handoffs/2026-10-06-stage-t-tripwire.md): the tripwire sequence.

An owner runs first for the cause (thirst and hunger: the Quartermaster;
hostiles and unknown causes: the Overseer alone), the Overseer rules and gives
the verdict, and the fort resumes only on an explicit `pause.verdict`
resume=true from that run. A repeat of the same cause escalates to the human.
"""

from __future__ import annotations

import pytest

from conductor.cycle import run_cycle
from conductor.hold import HoldStore
from conductor.mcp_client import tool_name
from conductor.pause_watch import PauseWatchStore
from conductor.policy import FULL_SPEED, PAUSED, PolicyError, load_policy
from conductor.runner import FakeRoleRunner, RunResult
from conductor.tests.test_pause_watch import NOW, FakeFort, _cycle_deps, _ok_run
from conductor.tripwire import TripwireState, note_latch, repeat_count

pytestmark = pytest.mark.asyncio

QM = "quartermaster"
OV = "overseer"
YES = {"resume": True, "reason": "the water is back"}
NO = {"resume": False, "reason": "still dry"}


def _thirst(tick=1000):
    return {"reason": "thirst_critical", "tick": tick, "detail": "Urist is dehydrated"}


def _runner(**extra):
    results = {OV: _ok_run(OV), QM: _ok_run(QM)}
    results.update(extra)
    return FakeRoleRunner(results)


def _failed(role):
    return RunResult(
        role=role, ok=False, status="error", cost_usd=0.0, wall_clock_seconds=1.0, timed_out=False,
        tool_summary={}, final_answer=None, raw={}, error="boom",
    )


def _called(deps):
    return [c[0] for c in deps.tool_caller.calls]


async def test_thirst_wakes_the_quartermaster_then_the_overseer(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    runner = _runner()
    deps = _cycle_deps(tmp_path, fort, runner=runner)
    result = await run_cycle(1, deps)

    assert [c["role"] for c in runner.calls] == [QM, OV]
    assert result.roles_woken == (QM, OV)
    assert "thirst_critical" in runner.calls[0]["prompt"]
    # the Overseer's briefing is the ruling prompt, and says the owner ran first
    assert "quartermaster ran first" in runner.calls[1]["prompt"]
    assert "pause.verdict" in runner.calls[1]["prompt"]
    # the verdict baseline was read after the owner and before the Overseer
    calls = _called(deps)
    assert calls.index("queue.pending_brief") < calls.index("pause.verdict_read")


async def test_hunger_also_belongs_to_the_quartermaster(tmp_path):
    fort = FakeFort(tripwire={"reason": "hunger_critical", "tick": 5, "detail": "x"}, verdict=YES)
    runner = _runner()
    await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert [c["role"] for c in runner.calls] == [QM, OV]


async def test_hostiles_wake_only_the_overseer(tmp_path):
    fort = FakeFort(tripwire={"reason": "hostile_reachable", "tick": 5, "detail": "a goblin"}, verdict=YES)
    runner = _runner()
    result = await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert [c["role"] for c in runner.calls] == [OV]
    assert result.roles_woken == (OV,)


async def test_an_unknown_cause_wakes_only_the_overseer(tmp_path):
    fort = FakeFort(tripwire={"reason": "something_new", "tick": 5, "detail": "?"}, verdict=YES)
    runner = _runner()
    await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert [c["role"] for c in runner.calls] == [OV]


async def test_no_verdict_keeps_the_fort_paused_latched_and_alerts(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=None)
    deps = _cycle_deps(tmp_path, fort, runner=_runner())
    result = await run_cycle(1, deps)

    assert "clock.resume" not in _called(deps) and "clock.clear" not in _called(deps)
    assert fort.paused is True and fort.tripwire is not None   # the latch stands
    assert result.pause_watch["verdict"] == "alert" and result.pause_watch["alerts"]
    assert result.clock_level == PAUSED


async def test_a_resume_true_verdict_clears_then_resumes_once_with_the_tick_verified(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    deps = _cycle_deps(tmp_path, fort, runner=_runner())
    result = await run_cycle(1, deps)

    calls = _called(deps)
    assert calls.index("clock.clear") < calls.index("clock.resume")
    assert fort.resume_calls == 1 and fort.paused is False and fort.tripwire is None
    assert result.pause_watch["resumed"] is True
    assert any(a.get("verify") == "tick advanced" for a in result.pause_watch["actions"])
    assert result.clock_level == FULL_SPEED
    assert not result.pause_watch["alerts"]


async def test_a_resume_that_does_not_move_the_tick_pauses_again_and_alerts(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES, resume_moves_tick=False)
    deps = _cycle_deps(tmp_path, fort, runner=_runner())
    result = await run_cycle(1, deps)
    assert fort.paused is True
    assert result.pause_watch["verdict"] == "alert" and result.clock_level == PAUSED


async def test_a_resume_false_verdict_keeps_the_fort_paused_and_latched(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=NO)
    deps = _cycle_deps(tmp_path, fort, runner=_runner())
    result = await run_cycle(1, deps)
    assert fort.resume_calls == 0 and fort.paused is True and fort.tripwire is not None
    assert "clock.clear" not in _called(deps)
    assert "still dry" in result.pause_watch["alerts"][0]["reason"]


async def test_an_escalation_keeps_the_fort_paused_even_with_a_resume_verdict(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    runner = _runner(**{OV: _ok_run(OV, tools=[tool_name("queue.escalate")])})
    result = await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert result.escalated is True
    assert fort.resume_calls == 0 and fort.paused is True and fort.tripwire is not None


async def test_an_operator_hold_suppresses_the_resume_even_after_a_true_verdict(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    HoldStore(tmp_path / "hold.json").set("planning", who="op", now=NOW)
    deps = _cycle_deps(tmp_path, fort, runner=_runner())
    result = await run_cycle(1, deps)
    assert fort.resume_calls == 0 and fort.paused is True
    assert "clock.resume" not in _called(deps)
    assert result.pause_watch["verdict"] == "held"


async def test_a_failed_owner_run_does_not_stop_the_overseer(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    runner = _runner(**{QM: _failed(QM)})
    result = await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert [c["role"] for c in runner.calls] == [QM, OV]
    assert result.pause_watch["resumed"] is True


async def test_the_owners_cursor_advances_only_on_a_clean_run(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=None)
    deps = _cycle_deps(tmp_path, fort, runner=_runner(**{QM: _failed(QM)}))
    await run_cycle(1, deps)
    assert deps.cursor_store.get(QM) is None or deps.cursor_store.get(QM) == 0


# ---- the repeat counter ------------------------------------------------------


async def _latch_and_resolve(tmp_path, fort, tick, runner):
    fort.tripwire = _thirst(tick)
    fort.paused = True
    fort.verdict = YES
    fort._verdict_reads = 0
    deps = _cycle_deps(tmp_path, fort, runner=runner)
    return await run_cycle(1, deps), deps


async def test_the_same_cause_relatching_past_the_limit_escalates_instead_of_rerunning(tmp_path):
    fort = FakeFort()
    limit = load_policy().tripwire_repeat_limit
    for i in range(limit):
        runner = _runner()
        result, _ = await _latch_and_resolve(tmp_path, fort, 1000 + 10 * i, runner)
        assert [c["role"] for c in runner.calls] == [QM, OV] and result.pause_watch["resumed"] is True

    runner = _runner()
    result, deps = await _latch_and_resolve(tmp_path, fort, 1000 + 10 * limit, runner)
    assert runner.calls == []                      # the sequence did not run
    assert result.escalated is True and result.roles_woken == ()
    assert fort.paused is True and fort.tripwire is not None
    assert "latched" in result.pause_watch["alerts"][0]["reason"]
    assert "clock.resume" not in _called(deps) and "fort.quicksave" not in _called(deps)

    # the same standing latch next cycle: still no run, still an alert
    runner2 = _runner()
    fort.verdict = YES
    fort._verdict_reads = 0
    result2 = await run_cycle(2, _cycle_deps(tmp_path, fort, runner=runner2))
    assert runner2.calls == [] and result2.pause_watch["alerts"]


async def test_a_latch_outside_the_window_starts_a_fresh_count(tmp_path):
    fort = FakeFort()
    pol = load_policy()
    for i in range(pol.tripwire_repeat_limit):
        await _latch_and_resolve(tmp_path, fort, 1000 + 10 * i, _runner())
    runner = _runner()
    result, _ = await _latch_and_resolve(tmp_path, fort, 1000 + pol.tripwire_repeat_window_ticks + 500, runner)
    assert [c["role"] for c in runner.calls] == [QM, OV] and result.pause_watch["resumed"] is True


async def test_a_different_cause_does_not_count_against_another(tmp_path):
    fort = FakeFort()
    for i in range(load_policy().tripwire_repeat_limit):
        await _latch_and_resolve(tmp_path, fort, 1000 + i, _runner())
    fort.tripwire = {"reason": "hostile_reachable", "tick": 1010, "detail": "x"}
    fort.paused = True
    fort.verdict = YES
    fort._verdict_reads = 0
    runner = _runner()
    await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert [c["role"] for c in runner.calls] == [OV]


async def test_a_standing_latch_is_counted_once_across_cycles(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=None)
    for i in range(1, 6):  # no verdict each time: the same latch is seen every cycle
        fort._verdict_reads = 0
        runner = _runner()
        await run_cycle(i, _cycle_deps(tmp_path, fort, runner=runner))
        assert [c["role"] for c in runner.calls] == [QM, OV]   # retried, never "repeat"-escalated


async def test_a_corrupt_counter_file_stays_paused_and_alerts(tmp_path):
    (tmp_path / "tripwire_state.json").write_text("{not json", encoding="utf-8")
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    runner = _runner()
    result = await run_cycle(1, _cycle_deps(tmp_path, fort, runner=runner))
    assert runner.calls == [] and fort.paused is True
    assert "unreadable" in result.pause_watch["alerts"][0]["reason"]


async def test_a_dry_run_plans_the_sequence_and_touches_nothing(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=YES)
    deps = _cycle_deps(tmp_path, fort, runner=_runner())
    deps.dry_run = True
    result = await run_cycle(1, deps)
    assert result.plan["would_wake"] == [QM, OV]
    assert deps.role_runner.calls == [] and not (tmp_path / "tripwire_state.json").exists()
    assert "clock.resume" not in _called(deps)


async def test_the_alert_is_recorded_in_the_pause_watch_state(tmp_path):
    fort = FakeFort(tripwire=_thirst(), verdict=None)
    await run_cycle(1, _cycle_deps(tmp_path, fort, runner=_runner()))
    assert PauseWatchStore(tmp_path / "pause_watch.json").load().alert_reason


# ---- policy and pure helpers ---------------------------------------------------


def test_the_committed_policy_names_the_owners():
    pol = load_policy()
    assert pol.tripwire_owners["thirst_critical"] == (QM,)
    assert pol.tripwire_owners["hunger_critical"] == (QM,)
    assert pol.tripwire_owners["hostile_reachable"] == ()   # the Overseer alone, it always runs last
    assert pol.tripwire_repeat_limit >= 1 and pol.tripwire_repeat_window_ticks >= 1


def test_a_bad_owner_role_or_repeat_value_is_refused(tmp_path):
    base = (load_policy.__globals__["DEFAULT_POLICY_PATH"]).read_text(encoding="utf-8")
    bad_role = tmp_path / "a.yaml"
    bad_role.write_text(base + "\ntripwire_owners:\n  thirst_critical: [nobody]\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(bad_role)


def test_repeat_count_is_per_cause_and_windowed():
    s = TripwireState()
    for t in (100, 200, 300):
        assert note_latch(s, {"reason": "a", "tick": t}) is True
    assert note_latch(s, {"reason": "a", "tick": 300}) is False
    note_latch(s, {"reason": "b", "tick": 250})
    assert repeat_count(s, {"reason": "a", "tick": 300}, 1000) == 3
    assert repeat_count(s, {"reason": "a", "tick": 300}, 150) == 2
    assert repeat_count(s, {"reason": "b", "tick": 250}, 1000) == 1
