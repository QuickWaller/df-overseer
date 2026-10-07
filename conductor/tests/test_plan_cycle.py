"""The Planner's conductor wiring through a real `run_cycle` over the fakes
(handoffs/2026-10-07-planner-p1b.md): the computed season cursor, the Planner
running first, the bootstrap and its escalation, the ruling wake, the
shortfall watch (off by default, on in these tests), and every failure being
non-fatal. No VM, no model."""

from __future__ import annotations

import dataclasses
import json
import logging

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.plan_watch import PlanWatchStore
from conductor.policy import PlanPolicy, ShortfallWatchPolicy, load_policy
from conductor.runner import RunResult
from conductor.status import status_from_cycle
from conductor.tests.test_cycle import (
    CHARTERS, MODELS, _base_tools, _deps, _diff_sequence, _overview, _queue_overview,
)

pytestmark = pytest.mark.asyncio

POLICY = load_policy()
SEASON = 100800
YEAR = 403200
BASE = 12000


def _plan_policy(*, shortfall=False, **over):
    return dataclasses.replace(POLICY, plan=PlanPolicy(
        enabled=True, season_ticks=SEASON, renotify_ticks=BASE, renotify_cap_ticks=SEASON,
        shortfall=ShortfallWatchPolicy(
            enabled=shortfall, renotify_ticks=BASE, renotify_cap_ticks=SEASON, stall_after=3,
            serving_types={"zones": ("room_siting", "corridor")},
        ), **over,
    ))


def _overview_at(abs_tick):
    return _overview(tick=abs_tick % YEAR) | {
        "tier2": {"in_game_date": f"year {abs_tick // YEAR}, month 1, day 1, tick {abs_tick % YEAR}", "alerts": []},
    }


class Clock:
    """A fort whose absolute tick the test moves."""

    def __init__(self, tick):
        self.tick = tick

    def overview(self, _args):
        return _overview_at(self.tick)


def _status(*, bootstrap=False, version=3, season=1, targets=(), owners=None, awaiting=(), reviewed=None):
    if bootstrap:
        return {"active": None, "bootstrap": True, "last_reviewed_tick": None, "plan_changes_awaiting": []}
    return {
        "active": {"id": f"plan-{version}", "version": version, "season_index": season, "tick": 5},
        "bootstrap": False, "last_reviewed_tick": reviewed,
        "plan_changes_awaiting": [{"proposal_id": p, "ruling_id": r} for p, r in awaiting],
        "targets": list(targets), "owners": owners or {}, "alive": 22,
    }


def _target(tid="bedrooms", *, on_hand=9.0, in_flight=0.0, want=22.0, owner="architect", serving=(), inputs=()):
    pos = on_hand + in_flight
    return {
        "id": tid, "signal": 'zones."Bedroom".furnished', "owner": owner, "state": "open",
        "on_hand": on_hand, "in_flight": in_flight, "position": pos, "want_units": want,
        "short_units": max(0.0, want - pos), "below_want": pos < want, "serving": list(serving),
        "at_max_in_flight": False, "inputs": list(inputs),
    }


def _plan_deps(tmp_path, clock, status, *, policy=None, tools=None, runner=None, dry_run=False):
    tools = dict(tools or _base_tools())
    tools["overview.get"] = clock.overview
    tools["plan.status"] = status
    # Keep the Quartermaster's season-length routine wake out of these tests: they are about the plan.
    quiet = dataclasses.replace(policy or _plan_policy(), routine_review_interval_game_days=10 ** 6)
    deps = _deps(tmp_path, tools=tools, runner=runner, dry_run=dry_run, policy=quiet, just_reviewed=False)
    deps.cursor_store.set("__routine_review__", clock.tick)
    deps.models = {**MODELS, "planner": "deepseek/deepseek-v4-pro"}
    deps.charters = {**CHARTERS, "planner": "# planner\n\nCharter."}
    return deps


def _store(tmp_path):
    return PlanWatchStore(tmp_path / "plan_watch.json")


def _planner_calls(deps):
    return [c for c in deps.role_runner.calls if c["role"] == "planner"]


# ---------------------------------------------------------------------------
# The computed season cursor (works with the Planner off)
# ---------------------------------------------------------------------------


async def test_the_season_cursor_wakes_the_quartermaster_once_per_season_even_with_the_planner_off(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, {"unused": True}, policy=POLICY)  # the committed policy: planner off
    first = await run_cycle(1, deps)
    assert first.roles_woken == ()  # first sighting sets the cursor, wakes nobody

    clock.tick = 4 * SEASON + 50000
    assert (await run_cycle(2, deps)).roles_woken == ()

    clock.tick = 5 * SEASON + 10
    crossing = await run_cycle(3, deps)
    assert crossing.roles_woken == ("quartermaster",)
    wake = crossing.signals
    assert wake.season_change is True

    clock.tick = 5 * SEASON + 20000
    assert (await run_cycle(4, deps)).roles_woken == ()  # fires once per index
    assert all(t != "plan.status" for t, _ in deps.tool_caller.calls)  # planner off: no plan read


async def test_a_reload_resets_the_season_cursor_without_waking_anyone(tmp_path):
    clock = Clock(6 * SEASON + 5)
    deps = _plan_deps(tmp_path, clock, {"unused": True}, policy=POLICY)
    await run_cycle(1, deps)
    clock.tick = 2 * SEASON + 5  # the save was reloaded to an earlier season
    result = await run_cycle(2, deps)
    assert result.roles_woken == ()
    clock.tick = 3 * SEASON
    assert (await run_cycle(3, deps)).roles_woken == ("quartermaster",)


async def test_the_season_wake_can_be_switched_off(tmp_path):
    pol = dataclasses.replace(POLICY, plan=dataclasses.replace(POLICY.plan, season_wake=False))
    clock = Clock(SEASON + 5)
    deps = _plan_deps(tmp_path, clock, {"unused": True}, policy=pol)
    await run_cycle(1, deps)
    clock.tick = 2 * SEASON + 5
    assert (await run_cycle(2, deps)).roles_woken == ()
    assert not (tmp_path / "plan_watch.json").exists()


# ---------------------------------------------------------------------------
# Off means off
# ---------------------------------------------------------------------------


async def test_with_the_planner_disabled_no_plan_status_is_read_and_nobody_is_woken(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _status(bootstrap=True), policy=POLICY)
    result = await run_cycle(1, deps)
    assert result.roles_woken == ()
    assert not any(t == "plan.status" for t, _ in deps.tool_caller.calls)


# ---------------------------------------------------------------------------
# Bootstrap, run first, escalation
# ---------------------------------------------------------------------------


async def test_a_fort_with_no_plan_wakes_the_planner_with_the_bootstrap_line(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _status(bootstrap=True))
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("planner",)
    [call] = _planner_calls(deps)
    assert call["model"] == "deepseek/deepseek-v4-pro" and call["charter"].startswith("# planner")
    briefing = json.loads(call["prompt"])
    assert briefing["wake_reason"] == "plan_bootstrap"
    assert "version 1" in briefing["wake_detail"] and "base_version 0" in briefing["wake_detail"]
    assert result.plan_watch["wakes"][0]["reason"] == "plan_bootstrap"


async def test_the_planner_runs_before_the_advisors_and_the_overseer(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    tools = _base_tools(**{
        "diff.since": _diff_sequence([[{"id": 1, "type": "JOB_COMPLETED", "detail": "Dig"}]]),
        "queue.overview": _queue_overview(proposals={"count": 1, "proposal_ids": ["proposal-0001"]}),
    })
    deps = _plan_deps(tmp_path, clock, _status(bootstrap=True), tools=tools)
    result = await run_cycle(1, deps)
    assert result.roles_woken[0] == "planner"
    assert result.roles_woken == ("planner", "architect", "overseer")
    assert [c["role"] for c in deps.role_runner.calls] == ["planner", "architect", "overseer"]


async def test_a_bootstrap_inside_its_backoff_does_not_wake_the_planner_again(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _status(bootstrap=True))
    await run_cycle(1, deps)
    clock.tick += BASE - 1
    assert (await run_cycle(2, deps)).roles_woken == ()
    clock.tick += 1
    assert (await run_cycle(3, deps)).roles_woken == ("planner",)


async def test_three_failed_bootstraps_escalate_to_the_operator_with_the_last_refusal_and_stop_waking(tmp_path, caplog):
    clock = Clock(4 * SEASON + 1000)
    refusal = {"rounds": [{"calls": [{"name": "plan.write", "result": "plan.write: refused: stale base", "error": True}]}]}
    from conductor.runner import FakeRoleRunner
    runner = FakeRoleRunner({"planner": RunResult(
        role="planner", ok=True, status="ok", cost_usd=0.0, wall_clock_seconds=1.0, timed_out=False,
        tool_summary={}, final_answer="could not file", raw={}, transcript=refusal,
    )})
    deps = _plan_deps(tmp_path, clock, _status(bootstrap=True), runner=runner)
    for i in range(3):
        assert (await run_cycle(i + 1, deps)).roles_woken == ("planner",)
        clock.tick += 4 * BASE
    with caplog.at_level(logging.CRITICAL, logger="conductor.cycle"):
        result = await run_cycle(4, deps)
    assert "planner" not in result.roles_woken  # (the Quartermaster's season_change may fall in this span)
    assert len(_planner_calls(deps)) == 3
    assert any("stale base" in r.message and "3 times" in r.message for r in caplog.records)
    assert "stale base" in result.plan_watch["standing_alert"]
    # The status block a monitor reads carries it, every cycle after.
    assert "standing_alert" in status_from_cycle(result)["plan_watch"]
    clock.tick += 40 * BASE
    assert "planner" not in (await run_cycle(5, deps)).roles_woken


# ---------------------------------------------------------------------------
# Non-fatal failures and the dry run
# ---------------------------------------------------------------------------


async def test_a_failed_plan_status_read_wakes_nobody_and_does_not_fail_the_cycle(tmp_path):
    from conductor.mcp_client import MCPToolError

    def boom(_args):
        raise MCPToolError("plan.status: not deployed")

    deps = _plan_deps(tmp_path, Clock(4 * SEASON + 1000), boom)
    result = await run_cycle(1, deps)
    assert result.roles_woken == ()


async def test_a_corrupt_plan_state_file_wakes_nobody_and_is_not_silently_reset(tmp_path):
    (tmp_path / "plan_watch.json").write_text("not json", encoding="utf-8")
    deps = _plan_deps(tmp_path, Clock(4 * SEASON + 1000), _status(bootstrap=True))
    result = await run_cycle(1, deps)
    assert result.roles_woken == ()
    assert (tmp_path / "plan_watch.json").read_text(encoding="utf-8") == "not json"


async def test_a_dry_run_reports_the_plan_wakes_but_saves_no_state(tmp_path):
    deps = _plan_deps(tmp_path, Clock(4 * SEASON + 1000), _status(bootstrap=True), dry_run=True)
    result = await run_cycle(1, deps)
    assert [w["reason"] for w in result.plan["wakes"]] == ["plan_bootstrap"]
    assert result.plan["would_wake"] == ["planner"]
    assert deps.role_runner.calls == []
    assert not (tmp_path / "plan_watch.json").exists()


async def test_the_operator_hold_silences_the_shortfall_watch(tmp_path):
    from conductor.hold import HoldStore, hold_path_for
    clock = Clock(4 * SEASON + 1000)
    st = _status(season=4, targets=[_target()])
    tools = _base_tools(**{"queue.execution_state": {"routing": {"routed_types": [], "unrouted_types": [], "frozen_types": []}}})
    deps = _plan_deps(tmp_path, clock, st, policy=_plan_policy(shortfall=True), tools=tools)
    HoldStore(hold_path_for(deps.cursor_store.path)).set("keeping the fort paused to plan", who="tester")
    held = await run_cycle(1, deps)
    assert held.hold is not None and held.roles_woken == ()
    assert any("operator hold" in n for n in held.plan_watch["notes"])
    # Released: the same open target now wakes its owner (the hold, not the target, was the reason).
    HoldStore(hold_path_for(deps.cursor_store.path)).clear()
    assert (await run_cycle(2, deps)).roles_woken == ("architect",)


# ---------------------------------------------------------------------------
# Rulings on the Planner's own plan_change
# ---------------------------------------------------------------------------


async def test_a_ruling_on_the_planners_own_plan_change_wakes_the_planner(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    pending = {"ids": []}
    calls = {"n": 0}

    def overview(_args):
        calls["n"] += 1
        ids = [] if calls["n"] == 1 else pending["ids"]
        return _queue_overview(proposals={"count": len(ids), "proposal_ids": ids})

    tools = _base_tools(**{"queue.overview": overview})
    deps = _plan_deps(tmp_path, clock, _status(bootstrap=True), tools=tools)
    pending["ids"] = ["proposal-0099"]  # the Planner files a plan_change during its run
    first = await run_cycle(1, deps)
    assert first.roles_woken == ("planner",)
    assert lanes.LaneStore(tmp_path / "lane_state.json").load().proposers == {"proposal-0099": "planner"}

    # Ruled between cycles; a plan now exists, so no bootstrap, just the ruling.
    pending["ids"] = []
    calls["n"] = 5
    deps.tool_caller.set_result("plan.status", _status(version=1, season=4))
    clock.tick += 100
    second = await run_cycle(2, deps)
    assert second.roles_woken == ("planner",)
    [_, call] = _planner_calls(deps)
    assert json.loads(call["prompt"])["wake_reason"] == "ruling_on_own"


async def test_a_season_review_and_an_accepted_plan_change_reach_the_planner_in_one_wake(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _status(version=3, season=3, awaiting=[("proposal-0042", "ruling-0031")]))
    result = await run_cycle(1, deps)  # first sighting with a stale plan owes a review
    assert result.roles_woken == ("planner",)
    briefing = json.loads(_planner_calls(deps)[0]["prompt"])
    assert "plan_review" in briefing["wake_detail"] and "ruling-0031" in briefing["wake_detail"]


# ---------------------------------------------------------------------------
# The shortfall watch, through a cycle
# ---------------------------------------------------------------------------

_ROUTING = {"routing": {"routed_types": [], "unrouted_types": [], "frozen_types": []}}
BED = {"item": "bed", "needed": 2.0, "available": 0.0, "owner": "quartermaster", "short": 2.0}


async def test_the_shortfall_watch_off_wakes_no_owner_even_for_an_open_target(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    st = _status(season=4, targets=[_target()])
    deps = _plan_deps(tmp_path, clock, st, policy=_plan_policy(shortfall=False))
    assert (await run_cycle(1, deps)).roles_woken == ()


async def test_the_shortfall_watch_on_wakes_the_architect_with_the_fixed_line_and_the_quartermaster_for_the_bed(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    serving = [{"proposal_id": "proposal-0007", "type": "room_siting", "role": "architect", "state": "pending"}]
    st = _status(season=4, targets=[_target(in_flight=1.0, serving=serving, inputs=[BED])],
                 owners={"architect": {"in_flight": 1, "ceiling": 2}})
    tools = _base_tools(**{"queue.execution_state": _ROUTING})
    deps = _plan_deps(tmp_path, clock, st, policy=_plan_policy(shortfall=True), tools=tools)
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("architect", "quartermaster")
    by_role = {c["role"]: json.loads(c["prompt"]) for c in deps.role_runner.calls}
    arch = by_role["architect"]
    assert arch["wake_reason"] == "plan_shortfall"
    assert arch["wake_detail"].startswith("Plan v3 target bedrooms: 9 on hand of 22 wanted")
    assert "1 of 2 plan slots in use" in arch["wake_detail"]
    assert by_role["quartermaster"]["wake_reason"] == "plan_input_short"
    assert "bed" in by_role["quartermaster"]["wake_detail"]
    # Inside the backoff neither is woken again.
    clock.tick += 100
    assert (await run_cycle(2, deps)).roles_woken == ()


async def test_a_stalled_target_wakes_the_owner_three_times_and_then_the_planner_once(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    # The plan is always from the current season, so no season review is owed while the clock runs.
    def st(_args):
        return _status(season=clock.tick // SEASON, targets=[_target()])

    tools = _base_tools(**{"queue.execution_state": _ROUTING})
    deps = _plan_deps(tmp_path, clock, st, policy=_plan_policy(shortfall=True), tools=tools)
    for i in range(40):
        await run_cycle(i + 1, deps)
        clock.tick += 2 * BASE
    arch = [c for c in deps.role_runner.calls if c["role"] == "architect"]
    planner = _planner_calls(deps)
    assert len(arch) == 3
    assert len(planner) == 1 and json.loads(planner[0]["prompt"])["wake_reason"] == "plan_target_stalled"


async def test_the_frozen_owner_group_is_read_from_the_routing_state(tmp_path):
    clock = Clock(4 * SEASON + 1000)
    st = _status(season=4, targets=[_target()])
    frozen = {"routing": {"routed_types": [], "unrouted_types": [], "frozen_types": ["room_siting", "corridor"]}}
    deps = _plan_deps(tmp_path, clock, st, policy=_plan_policy(shortfall=True), tools=_base_tools(**{"queue.execution_state": frozen}))
    assert (await run_cycle(1, deps)).roles_woken == ()
