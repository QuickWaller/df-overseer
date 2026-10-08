"""handoffs/2026-10-05-stricter-wakes.md: a role wakes only on a change in its
own lane. Each trigger is exercised through a real `run_cycle` over the fakes
(no VM, no model), plus the pure pieces in `conductor/lanes.py`."""

from __future__ import annotations

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.policy import load_policy
from conductor.runner import RunResult
from conductor.tests.test_cycle import (
    _STUCK_BED, _STUCK_BREW, _base_tools, _deps, _diff_sequence, _food_drink, _grade_result,
    _queue_overview,
)

pytestmark = pytest.mark.asyncio

POLICY = load_policy()
ADV = ("architect", "quartermaster")


def _events(architect=None, quartermaster=None):
    return _diff_sequence([architect or [], quartermaster or []])


# ---------------------------------------------------------------------------
# Diff-event lanes
# ---------------------------------------------------------------------------


async def test_a_dig_completing_wakes_only_the_architect(tmp_path):
    tools = _base_tools(**{"diff.since": _events(architect=[{"id": 1, "type": "JOB_COMPLETED", "detail": "Dig"}])})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ("architect",)


async def test_a_construction_completing_is_in_the_architects_lane_not_the_quartermasters(tmp_path):
    ev = [{"id": 1, "type": "JOB_COMPLETED", "detail": "Construct Bed"}]
    tools = _base_tools(**{"diff.since": _events(quartermaster=ev)})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


async def test_a_production_job_completing_wakes_nobody(tmp_path):
    ev = [{"id": 1, "type": "JOB_COMPLETED", "detail": "Brew Drink From Plant"}]
    tools = _base_tools(**{"diff.since": _events(architect=ev, quartermaster=ev)})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


# ---------------------------------------------------------------------------
# Stuck jobs
# ---------------------------------------------------------------------------


def _stuck_deps(tmp_path, job):
    from conductor.job_watch import JobWatchStore, _base_key

    deps = _deps(tmp_path, tools=_base_tools(**{"stuckjobs.find": [job]}))
    JobWatchStore(deps.cursor_store.path.with_name("job_watch.json")).save(
        {f"{_base_key(job)}#0": {"first_seen": 403200 + 1000 - 3600, "last_notified": None}}
    )
    return deps


async def test_a_stuck_construction_job_wakes_only_the_architect(tmp_path):
    result = await run_cycle(1, _stuck_deps(tmp_path, _STUCK_BED))
    assert result.roles_woken == ("architect",)


async def test_a_stuck_production_job_wakes_only_the_quartermaster(tmp_path):
    result = await run_cycle(1, _stuck_deps(tmp_path, _STUCK_BREW))
    assert result.roles_woken == ("quartermaster",)


async def test_a_stuck_job_in_no_lane_wakes_nobody(tmp_path):
    hauling = dict(_STUCK_BED, job_type="StoreItemInStockpile", detail="Store Item", building="")
    result = await run_cycle(1, _stuck_deps(tmp_path, hauling))
    assert result.roles_woken == ()


# ---------------------------------------------------------------------------
# Predictions: a hit wakes nobody, a miss wakes the advisors
# ---------------------------------------------------------------------------


def _graded(status):
    return _grade_result(graded_count=1, graded=[{"id": 1, "status": status}])


async def test_a_graded_hit_wakes_nobody(tmp_path):
    tools = _base_tools(**{"queue.grade": _graded("graded_true")})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


async def test_a_graded_miss_wakes_the_advisors(tmp_path):
    tools = _base_tools(**{"queue.grade": _graded("graded_false")})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ADV
    assert result.signals.prediction_misses == 1


async def test_an_unresolvable_prediction_wakes_nobody(tmp_path):
    tools = _base_tools(**{"queue.grade": _graded("unresolvable")})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


# ---------------------------------------------------------------------------
# Alerts are edge-triggered
# ---------------------------------------------------------------------------


async def test_an_alert_wakes_once_until_it_clears_and_recrosses(tmp_path):
    level = {"drink": 10}  # 20 alive: 0.5 per citizen, below 2
    tools = _base_tools(**{"stocks.food-drink": lambda a: _food_drink(drink=level["drink"])})
    deps = _deps(tmp_path, tools=tools)

    first = await run_cycle(1, deps)
    assert first.roles_woken == ("quartermaster",)
    assert deps.role_runner.calls[0]["role"] == "quartermaster"

    second = await run_cycle(2, deps)  # still crossed: no new wake
    assert second.roles_woken == ()

    level["drink"] = 500
    assert (await run_cycle(3, deps)).roles_woken == ()  # cleared

    level["drink"] = 10
    assert (await run_cycle(4, deps)).roles_woken == ("quartermaster",)  # re-crossed


async def test_an_alert_stays_owed_when_the_quartermasters_run_fails(tmp_path):
    tools = _base_tools(**{"stocks.food-drink": lambda a: _food_drink(drink=10)})
    deps = _deps(tmp_path, tools=tools)
    deps.role_runner.set_result("quartermaster", RunResult(
        role="quartermaster", ok=False, status="failed", cost_usd=0.0, wall_clock_seconds=0.0,
        timed_out=False, tool_summary={}, final_answer="", raw={},
    ))
    assert (await run_cycle(1, deps)).roles_woken == ("quartermaster",)
    assert (await run_cycle(2, deps)).roles_woken == ("quartermaster",)  # retried: not yet served
    deps.role_runner.set_result("quartermaster", RunResult(
        role="quartermaster", ok=True, status="ok", cost_usd=0.0, wall_clock_seconds=0.0,
        timed_out=False, tool_summary={}, final_answer="", raw={},
    ))
    assert (await run_cycle(3, deps)).roles_woken == ("quartermaster",)
    assert (await run_cycle(4, deps)).roles_woken == ()


async def test_a_failed_alert_read_does_not_count_as_cleared(tmp_path):
    state = {"mode": "low"}

    def food(args):
        if state["mode"] == "fail":
            raise RuntimeError("read failed")
        return _food_drink(drink=10)

    deps = _deps(tmp_path, tools=_base_tools(**{"stocks.food-drink": food}))
    assert (await run_cycle(1, deps)).roles_woken == ("quartermaster",)
    state["mode"] = "fail"
    assert (await run_cycle(2, deps)).roles_woken == ()
    state["mode"] = "low"
    assert (await run_cycle(3, deps)).roles_woken == ()  # never cleared, so no re-cross


# ---------------------------------------------------------------------------
# A ruling on a role's own proposal
# ---------------------------------------------------------------------------


async def test_a_ruling_wakes_only_the_proposer(tmp_path):
    pending = {"after_architect": ["proposal-0009"]}
    calls = {"n": 0}

    def overview(args):
        calls["n"] += 1
        # Call 1 is the top-of-cycle read; later reads (after the Architect's
        # run) see the proposal the Architect filed.
        ids = [] if calls["n"] == 1 else pending["after_architect"]
        return _queue_overview(proposals={"count": len(ids), "proposal_ids": ids})

    ev = [{"id": 1, "type": "JOB_COMPLETED", "detail": "Dig"}]
    tools = _base_tools(**{"diff.since": _events(architect=ev), "queue.overview": overview})
    deps = _deps(tmp_path, tools=tools)

    first = await run_cycle(1, deps)
    assert "architect" in first.roles_woken and "quartermaster" not in first.roles_woken
    assert lanes.LaneStore(tmp_path / "lane_state.json").load().proposers == {"proposal-0009": "architect"}

    # Ruled between cycles: it is no longer pending.
    pending["after_architect"] = []
    calls["n"] = 5
    deps.tool_caller.set_result("diff.since", _diff_sequence())
    second = await run_cycle(2, deps)
    assert second.roles_woken == ("architect",)

    third = await run_cycle(3, deps)
    assert third.roles_woken == ()  # served once


# ---------------------------------------------------------------------------
# Routine review and quiet cycles
# ---------------------------------------------------------------------------


async def test_the_routine_review_wakes_only_the_quartermaster(tmp_path):
    """Planner P1b (user's call 2026-10-07): the Architect's 7-day routine wake
    is retired; the Quartermaster's remains, at season length."""
    deps = _deps(tmp_path, just_reviewed=False)
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("quartermaster",)


async def test_a_quiet_cycle_wakes_nobody(tmp_path):
    result = await run_cycle(1, _deps(tmp_path))
    assert result.roles_woken == ()


# ---------------------------------------------------------------------------
# lanes.py, pure
# ---------------------------------------------------------------------------


def test_apply_rulings_ignores_a_proposal_of_unknown_author():
    state = lanes.LaneState()
    lanes.apply_rulings(POLICY, state, [])
    assert state.pending == {}


def test_a_deferred_proposal_stays_pending_and_wakes_nobody():
    state = lanes.LaneState(proposers={"proposal-1": "architect"})
    lanes.apply_rulings(POLICY, state, ["proposal-1"])
    assert state.pending == {} and state.proposers == {"proposal-1": "architect"}


def test_attribution_names_the_advisor_whose_run_added_the_id():
    state = lanes.LaneState()
    known = lanes.attribute_new_proposals(state, "quartermaster", {"p1"}, ["p1", "p2"])
    assert state.proposers == {"p2": "quartermaster"} and known == {"p1", "p2"}


def test_attribution_by_recorded_author_ignores_which_run_finished():
    state = lanes.LaneState()
    # Two roles ran at once; the Quartermaster's run finishes last, yet both
    # filings keep their recorded authors.
    known = lanes.attribute_new_proposals(
        state, "quartermaster", {"p1"}, ["p1", "p2", "p3"],
        authors={"p1": "planner", "p2": "architect", "p3": "quartermaster"},
    )
    assert state.proposers == {"p2": "architect", "p3": "quartermaster"} and known == {"p1", "p2", "p3"}
    asks = lanes.attribute_new_asks(
        state, "quartermaster", set(), ["a1", "a2"], authors={"a1": "architect", "a2": "quartermaster"},
    )
    assert state.askers == {"a1": "architect", "a2": "quartermaster"} and asks == {"a1", "a2"}


def test_an_id_with_no_recorded_author_is_left_unattributed_not_guessed():
    state = lanes.LaneState()
    lanes.attribute_new_proposals(state, "architect", set(), ["p1"], authors={})
    assert state.proposers == {}


def test_lane_state_round_trips(tmp_path):
    store = lanes.LaneStore(tmp_path / "s.json")
    state = lanes.LaneState(alerts={"a": True}, proposers={"p": "architect"}, pending={"architect": {"k": "v"}})
    store.save(state)
    assert store.load() == state
    assert lanes.LaneStore(tmp_path / "missing.json").load() == lanes.LaneState()
