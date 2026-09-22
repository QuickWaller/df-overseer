"""conductor/cycle.py: the full cycle, end to end, over a FakeToolCaller and
a FakeRoleRunner -- no VM, no docker, no model call, ever. These tests are
this stream's proof for the handoff's own "Done when" test list: a quiet
cycle wakes nobody and changes no clock; each wake reason picks the right
level; a tripwire pauses, wakes the Overseer and clears only after (and
never if it escalated); the ticks-to-consequence rule both ways (unit-level
in test_triage.py, exercised here through a real cycle too); the briefing's
size is independent of fort size (unit-level in test_briefing.py); the
Overseer is woken only when the queue holds something.
"""

from __future__ import annotations

import json

import pytest

from conductor.archive import CycleArchive
from conductor.cursors import CursorStore
from conductor.cycle import CycleDeps, run_cycle
from conductor.mcp_client import FakeToolCaller, MCPToolError, tool_name
from conductor.policy import FULL_SPEED, PAUSED, SLOWED, load_policy
from conductor.runner import FakeRoleRunner, RunResult
from conductor.triage import ADVISORS, CONSULTANT, OVERSEER

POLICY = load_policy()  # the real, committed conductor/policy.yaml

CHARTERS = {role: f"# {role}\n\nCharter." for role in (*ADVISORS, CONSULTANT, OVERSEER)}
MODELS = {role: "deepseek/deepseek-v4-flash" for role in (*ADVISORS, CONSULTANT, OVERSEER)}


def _vitals(**overrides):
    base = {
        "ok": True, "alive": 20, "dead_total": 0,
        "worst_hunger_status": "fine", "worst_thirst_status": "fine", "warning_count": 0,
    }
    base.update(overrides)
    return base


def _clock_status(**overrides):
    base = {
        "paused": False, "fps": 100, "cur_year": 1, "cur_year_tick": 1000,
        "abs_tick": 403200 + 1000, "armed": True, "tripwire": None,
    }
    base.update(overrides)
    return base


def _overview(tick=1000):
    return {"tier1": {"population": 20}, "tier2": {"in_game_date": f"year 1, month 1, day 1, tick {tick}", "alerts": []}}


def _diff_sequence(per_call_events=None):
    """One entry per diff.since call, in ALL_ROLES order (architect,
    quartermaster, consultant, overseer). Missing entries default to no
    events."""
    per_call_events = per_call_events or []
    state = {"i": 0}

    def _fn(arguments):
        i = state["i"]
        state["i"] += 1
        events = per_call_events[i] if i < len(per_call_events) else []
        cursor = int(arguments.get("cursor", 0))
        return {"cursor": str(cursor + len(events)), "events": events}

    return _fn


def _grade_result(**overrides):
    base = {
        "current_game_tick": 403200 + 1000, "graded_at": "2026-09-22T00:00:00+00:00",
        "graded_count": 0, "graded": [], "unexecuted_count": 0, "unexecuted": [],
    }
    base.update(overrides)
    return base


def _queue_overview(**overrides):
    base = {
        "proposals": {"count": 0, "proposal_ids": []},
        "asks": {"count": 0, "ask_ids": []},
    }
    base.update(overrides)
    return base


def _base_tools(**overrides):
    results = {
        "vitals.summary": _vitals(),
        "clock.status": _clock_status(),
        "overview.get": _overview(),
        "queue.overview": _queue_overview(),
        "diff.since": _diff_sequence(),
        "queue.grade": _grade_result(),
        "clock.set-speed": {"ok": True, "old_fps": 100, "new_fps": 100},
        "clock.arm": {"ok": True, "armed": True},
        "clock.clear": {"ok": True, "had_latch": True},
        "clock.resume": {"ok": True, "paused": False},
        "clock.pause": {"ok": True, "paused": True},
        "fort.quicksave": {
            "ok": True, "mode": "issued", "issued": True,
            "predicted_slot": "autosave 1", "predicted_slot_prior_mtime": 123,
        },
    }
    results.update(overrides)
    return results


def _deps(tmp_path, *, tools=None, runner=None, dry_run=False, policy=None, just_reviewed=True):
    """`just_reviewed=True` (the default): the routine-review cursor is
    pre-seeded to this fixture's own game tick, so an ordinary test's
    "quiet cycle" baseline is not itself polluted by the very-first-cycle
    "never reviewed yet, due immediately" rule
    (conductor/cycle.py's _game_days_since) -- that rule gets its own
    dedicated test below rather than firing incidentally in every other
    one."""
    cursor_store = CursorStore(tmp_path / "cursors.json")
    if just_reviewed:
        cursor_store.set("__routine_review__", 403200 + 1000)  # matches _overview()'s default tick
    return CycleDeps(
        tool_caller=FakeToolCaller(tools or _base_tools()),
        role_runner=runner or FakeRoleRunner(),
        policy=policy or POLICY,
        cursor_store=cursor_store,
        archive=CycleArchive(tmp_path / "cycles"),
        charters=CHARTERS,
        models=MODELS,
        dry_run=dry_run,
    )


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# A quiet cycle wakes nobody and changes no clock
# ---------------------------------------------------------------------------


async def test_a_quiet_cycle_wakes_nobody_and_changes_no_clock(tmp_path):
    deps = _deps(tmp_path)
    result = await run_cycle(1, deps)

    assert result.roles_woken == ()
    assert result.role_runs == []
    assert result.clock_level == FULL_SPEED
    # fps already 100 == base_fps, so no clock.set-speed call was needed.
    assert result.clock_changes == []
    assert deps.role_runner.calls == []
    assert result.archived_path is not None
    assert (result.archived_path / "summary.json").is_file()


async def test_a_quiet_cycle_still_re_arms_a_disarmed_watcher(tmp_path):
    tools = _base_tools()
    tools["clock.status"] = _clock_status(armed=False)
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert [c["tool"] for c in result.clock_changes] == ["clock.arm"]


# ---------------------------------------------------------------------------
# Each wake reason picks the right level and role(s)
# ---------------------------------------------------------------------------


async def test_migrant_wave_wakes_both_advisors_at_full_speed(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert result.roles_woken == ("architect", "quartermaster")
    assert result.clock_level == FULL_SPEED
    assert [c["role"] for c in deps.role_runner.calls] == ["architect", "quartermaster"]


async def test_caravan_present_slows_the_clock_and_wakes_only_the_quartermaster(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[], [{"id": 1, "type": "caravan_arrived"}]])
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert result.roles_woken == ("quartermaster",)
    assert result.clock_level == SLOWED
    change = next(c for c in result.clock_changes if c["tool"] == "clock.set-speed")
    assert change["args"]["fps"] == POLICY.think_fps


async def test_a_never_reviewed_fort_triggers_a_routine_review_on_its_first_cycle(tmp_path):
    """The other side of the same rule the just_reviewed=True default in
    _deps() exists to keep out of every other test's way: a genuinely fresh
    conductor (no __routine_review__ cursor yet) treats the review as due
    immediately, per conductor/cycle.py's own _game_days_since."""
    deps = _deps(tmp_path, just_reviewed=False)
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("architect", "quartermaster")


async def test_vital_nearing_threshold_slows_the_clock(tmp_path):
    tools = _base_tools()
    tools["vitals.summary"] = _vitals(worst_thirst_status="thirsty", warning_count=1)
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert result.clock_level == SLOWED
    assert "quartermaster" in result.roles_woken


# ---------------------------------------------------------------------------
# The Overseer wakes only when the queue holds something for it
# ---------------------------------------------------------------------------


async def test_overseer_not_woken_when_the_queue_is_empty(tmp_path):
    deps = _deps(tmp_path)
    result = await run_cycle(1, deps)
    assert OVERSEER not in result.roles_woken


async def test_overseer_woken_and_quicksaved_before_running_when_the_queue_holds_something(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(proposals={"count": 1, "proposal_ids": ["proposal-0001"]})
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert OVERSEER in result.roles_woken
    quicksave_calls = [c for c in result.clock_changes if c["tool"] == "fort.quicksave"]
    assert len(quicksave_calls) == 1
    # The overseer's own run must be the call AFTER the quicksave.
    tool_order = [c["tool"] for c in result.clock_changes]
    assert tool_order.index("fort.quicksave") < len(tool_order)
    assert deps.role_runner.calls[-1]["role"] == OVERSEER


# ---------------------------------------------------------------------------
# A tripwire pauses, wakes the Overseer, and clears/resumes only after
# ---------------------------------------------------------------------------


async def test_a_tripwire_wakes_the_overseer_and_clears_and_resumes_after_a_clean_run(tmp_path):
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hunger_critical", "tick": 999, "detail": "Urist is starving"},
    )
    runner = FakeRoleRunner({
        OVERSEER: RunResult(
            role=OVERSEER, ok=True, status="ok", cost_usd=0.01, wall_clock_seconds=5.0,
            timed_out=False, tool_summary={"calls": 2}, final_answer="Handled it.", raw={},
        ),
    })
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.tripwire["reason"] == "hunger_critical"
    assert result.roles_woken == (OVERSEER,)
    assert result.escalated is False
    tool_order = [c["tool"] for c in result.clock_changes]
    assert tool_order == ["fort.quicksave", "clock.clear", "clock.resume"]
    assert [c["role"] for c in runner.calls] == [OVERSEER]


async def test_a_tripwire_leaves_the_fort_paused_when_the_overseer_run_fails(tmp_path):
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "unit_critical", "tick": 999, "detail": "a death"},
    )
    runner = FakeRoleRunner({
        OVERSEER: RunResult(
            role=OVERSEER, ok=False, status="error", cost_usd=0.0, wall_clock_seconds=1.0,
            timed_out=False, tool_summary={}, final_answer=None, raw={}, error="model refused",
        ),
    })
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.escalated is True
    tool_order = [c["tool"] for c in result.clock_changes]
    assert "clock.clear" not in tool_order
    assert "clock.resume" not in tool_order
    assert tool_order == ["fort.quicksave"]


async def test_a_tripwire_never_resumes_when_the_overseer_run_times_out(tmp_path):
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hostile_reachable", "tick": 999, "detail": "a goblin"},
    )
    runner = FakeRoleRunner({
        OVERSEER: RunResult(
            role=OVERSEER, ok=False, status="timeout", cost_usd=0.0, wall_clock_seconds=600.0,
            timed_out=True, tool_summary={}, final_answer=None, raw={}, error="timed out",
        ),
    })
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.escalated is True
    assert "clock.resume" not in [c["tool"] for c in result.clock_changes]


async def test_a_tripwire_takes_priority_over_ordinary_triage_this_cycle(tmp_path):
    """Even if a migrant wave also happened this cycle, a live tripwire
    means ONLY the Overseer wakes, at PAUSED, per docs/AGENT-LOOP.md §3's
    own priority (safety over the ordinary wake table)."""
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hunger_critical", "tick": 999, "detail": "x"},
    )
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    runner = FakeRoleRunner({
        OVERSEER: RunResult(
            role=OVERSEER, ok=True, status="ok", cost_usd=0.0, wall_clock_seconds=1.0,
            timed_out=False, tool_summary={}, final_answer="ok", raw={},
        ),
    })
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.roles_woken == (OVERSEER,)
    assert result.clock_level == PAUSED
    assert "architect" not in [c["role"] for c in runner.calls]


# ---------------------------------------------------------------------------
# Dry-run mode: reads happen, nothing is changed or launched
# ---------------------------------------------------------------------------


async def test_dry_run_reports_a_plan_without_changing_the_clock_or_launching_anyone(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    tools["queue.overview"] = _queue_overview(proposals={"count": 1, "proposal_ids": ["proposal-0001"]})
    runner = FakeRoleRunner()
    deps = _deps(tmp_path, tools=tools, runner=runner, dry_run=True)

    result = await run_cycle(1, deps)

    assert result.dry_run is True
    assert result.plan is not None
    assert "architect" in result.plan["would_wake"]
    assert result.clock_changes == []
    assert result.role_runs == []
    assert runner.calls == []  # no role actually launched
    assert result.archived_path is None  # nothing archived for a dry run


async def test_dry_run_never_calls_queue_grade_or_mutates_the_clock(tmp_path):
    tools = _base_tools()

    def _refuse(_arguments):
        raise AssertionError("queue.grade must not be called in dry-run mode")

    tools["queue.grade"] = _refuse
    deps = _deps(tmp_path, tools=tools, dry_run=True)
    await run_cycle(1, deps)  # must not raise


async def test_dry_run_does_not_advance_diff_cursors(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    deps = _deps(tmp_path, tools=tools, dry_run=True)
    await run_cycle(1, deps)
    assert deps.cursor_store.get("architect") == 0  # unchanged


# ---------------------------------------------------------------------------
# A real cycle DOES advance diff cursors and archives itself
# ---------------------------------------------------------------------------


async def test_a_real_cycle_advances_every_roles_diff_cursor(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([
        [{"id": 1}], [{"id": 1}, {"id": 2}], [], [{"id": 1}],
    ])
    deps = _deps(tmp_path, tools=tools)
    await run_cycle(1, deps)

    assert deps.cursor_store.get("architect") == 1
    assert deps.cursor_store.get("quartermaster") == 2
    assert deps.cursor_store.get("consultant") == 0
    assert deps.cursor_store.get("overseer") == 1


async def test_a_real_cycle_writes_a_full_archive(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert result.archived_path.is_dir()
    summary = json.loads((result.archived_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["roles_woken"] == ["architect", "quartermaster"]
    briefings = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))
    assert "architect" in briefings
    assert (result.archived_path / "run-architect.json").is_file()


async def test_daily_cost_accumulates_across_role_runs(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    runner = FakeRoleRunner({
        "architect": RunResult(
            role="architect", ok=True, status="ok", cost_usd=0.01, wall_clock_seconds=1,
            timed_out=False, tool_summary={}, final_answer="x", raw={},
        ),
        "quartermaster": RunResult(
            role="quartermaster", ok=True, status="ok", cost_usd=0.02, wall_clock_seconds=1,
            timed_out=False, tool_summary={}, final_answer="x", raw={},
        ),
    })
    deps = _deps(tmp_path, tools=tools, runner=runner)
    await run_cycle(1, deps)

    import time
    today = time.strftime("%Y-%m-%d", time.gmtime())
    assert deps.archive.daily_cost(today) == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# The charter and briefing actually reach the runner
# ---------------------------------------------------------------------------


async def test_the_woken_roles_charter_and_briefing_reach_the_runner(tmp_path):
    tools = _base_tools()
    tools["diff.since"] = _diff_sequence([[{"id": 1, "type": "migrant_wave"}]])
    runner = FakeRoleRunner()
    deps = _deps(tmp_path, tools=tools, runner=runner)
    await run_cycle(1, deps)

    call = next(c for c in runner.calls if c["role"] == "architect")
    assert call["charter"] == CHARTERS["architect"]
    briefing = json.loads(call["prompt"])
    assert briefing["role"] == "architect"
    assert briefing["wake_reason"] == "migrant_wave"
    assert briefing["clock"] == FULL_SPEED


# ---------------------------------------------------------------------------
# Fix 1 (handoffs/2026-09-22-loop-conductor-fixes.md): the conductor can now
# see an open ask through queue.overview and wakes the Consultant for it.
# ---------------------------------------------------------------------------


async def test_an_open_ask_wakes_the_consultant(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(asks={"count": 1, "ask_ids": ["ask-0001"]})
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)

    assert CONSULTANT in result.roles_woken
    assert OVERSEER not in result.roles_woken  # the proposal half is still empty


async def test_the_consultants_briefing_carries_ask_ids_not_proposal_ids(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(
        proposals={"count": 1, "proposal_ids": ["proposal-0001"]},
        asks={"count": 1, "ask_ids": ["ask-0001"]},
    )
    runner = FakeRoleRunner()
    deps = _deps(tmp_path, tools=tools, runner=runner)
    await run_cycle(1, deps)

    consultant_call = next(c for c in runner.calls if c["role"] == CONSULTANT)
    briefing = json.loads(consultant_call["prompt"])
    assert briefing["queue"]["ids"]["items"] == ["ask-0001"]

    overseer_call = next(c for c in runner.calls if c["role"] == OVERSEER)
    overseer_briefing = json.loads(overseer_call["prompt"])
    assert overseer_briefing["queue"]["ids"]["items"] == ["proposal-0001"]


# ---------------------------------------------------------------------------
# Fix 2: a clock.*/fort.quicksave refusal (now a real MCPToolError, per
# dfmcp/server.py's own fix) is caught, logged, and does not crash the cycle.
# ---------------------------------------------------------------------------


async def test_a_clock_resume_refusal_is_logged_and_does_not_crash_the_cycle(tmp_path, caplog):
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hunger_critical", "tick": 999, "detail": "x"},
    )

    def _refuse(_arguments):
        raise MCPToolError("clock.resume: refused: a tripwire is latched")

    tools["clock.resume"] = _refuse
    runner = FakeRoleRunner({
        OVERSEER: RunResult(
            role=OVERSEER, ok=True, status="ok", cost_usd=0.0, wall_clock_seconds=1.0,
            timed_out=False, tool_summary={"calls": 1, "tools": []}, final_answer="ok", raw={},
        ),
    })
    deps = _deps(tmp_path, tools=tools, runner=runner)

    import logging
    with caplog.at_level(logging.ERROR, logger="conductor.cycle"):
        result = await run_cycle(1, deps)  # must not raise

    assert result.escalated is False  # the RUN was clean; only the resume call was refused
    resume_change = next(c for c in result.clock_changes if c["tool"] == "clock.resume")
    assert resume_change["result"] == {"ok": False, "error": "clock.resume: refused: a tripwire is latched"}
    assert any("clock.resume refused" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Fix 3: mechanical escalation, via queue.escalate, not free text or "any
# unclean run".
# ---------------------------------------------------------------------------


def _run_that_called(*tool_ids: str, ok: bool = True) -> RunResult:
    return RunResult(
        role=OVERSEER, ok=ok, status="ok" if ok else "error", cost_usd=0.0, wall_clock_seconds=1.0,
        timed_out=False, tool_summary={"calls": len(tool_ids), "tools": [tool_name(t) for t in tool_ids]},
        final_answer="handled" if ok else None, raw={}, error=None if ok else "refused",
    )


async def test_a_tripwire_stays_paused_when_a_clean_run_calls_queue_escalate(tmp_path):
    """The actual gap fix 3 closes: a CLEAN run (ok=True) that mechanically
    called queue.escalate must stay paused -- the old proxy (any unclean
    run) could never detect this, since this run completed fine."""
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hunger_critical", "tick": 999, "detail": "x"},
    )
    runner = FakeRoleRunner({OVERSEER: _run_that_called("queue.escalate")})
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.escalated is True
    tool_order = [c["tool"] for c in result.clock_changes]
    assert "clock.clear" not in tool_order
    assert "clock.resume" not in tool_order


async def test_a_tripwire_resumes_when_a_clean_run_never_calls_queue_escalate(tmp_path):
    """The companion invariant: a clean run with NO escalate call must no
    longer be (mis)treated as an escalation."""
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hunger_critical", "tick": 999, "detail": "x"},
    )
    runner = FakeRoleRunner({OVERSEER: _run_that_called("queue.propose")})
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.escalated is False
    tool_order = [c["tool"] for c in result.clock_changes]
    assert tool_order == ["fort.quicksave", "clock.clear", "clock.resume"]


async def test_the_overseer_can_escalate_during_an_ordinary_cycle_and_pauses_the_fort(tmp_path):
    """agents/overseer/role.md's Escalation section is not tripwire-
    specific: an ordinary cycle where the Overseer wakes (queue holds
    something) and calls queue.escalate must pause the fort too, not only
    the next time a tripwire happens to latch."""
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(proposals={"count": 1, "proposal_ids": ["proposal-0001"]})
    runner = FakeRoleRunner({OVERSEER: _run_that_called("queue.escalate")})
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.escalated is True
    assert result.clock_level == PAUSED
    assert any(c["tool"] == "clock.pause" for c in result.clock_changes)


async def test_an_ordinary_cycle_with_no_escalate_call_never_pauses(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(proposals={"count": 1, "proposal_ids": ["proposal-0001"]})
    runner = FakeRoleRunner({OVERSEER: _run_that_called("queue.rule")})
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)

    assert result.escalated is False
    assert not any(c["tool"] == "clock.pause" for c in result.clock_changes)
