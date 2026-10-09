"""The Planner's derived to-do list (conductor/plan_todo.py, register 2026-10-09
"A work queue for the Planner"): pure `fold` tests over hand-built `plan.status`
results, the policy block, and one `run_cycle` that wakes the Planner with the
crop-target and dining_tables-floor items."""

from __future__ import annotations

import dataclasses
import json

import pytest

from conductor.cycle import run_cycle
from conductor.plan_todo import REASON_TODO, fold
from conductor.plan_watch import PlanWake, PlanWatchResult, PlanWatchState, PlanWatchStore, evaluate
from conductor.policy import PlanPolicy, WorkQueuePolicy, load_policy
from conductor.tests.test_cycle import _queue_overview
from conductor.tests.test_plan_cycle import Clock, SEASON, _plan_deps, _plan_policy, _planner_calls, _status
from conductor.tests.test_plan_watch import BASE, policy as watch_policy, status as base_status

KINDS = {"autofarm": "crop targets (sync: autofarm)"}


def pol(**over):
    wq = WorkQueuePolicy(enabled=True, max_wakes=3, max_items=8, owned_kinds=KINDS)
    return dataclasses.replace(watch_policy(shortfall=False), work_queue=dataclasses.replace(wq, **over))


DINING = {"id": "dining_tables", "ref": "dining_tables", "kind": "down", "reason": "numeric want only"}


def st(*, missing=(), deviations=(), targets=(), pass_tick=None, version=2):
    out = base_status(targets, version=version)
    out["last_pass_tick"] = pass_tick
    out["roadmap_check"] = {"stage": "hamlet", "missing": list(missing), "deviations": list(deviations)}
    return out


def crop(crop_name="crop_plump", **kw):
    return {"id": crop_name, "sync": "autofarm", "crop": "PLUMP_HELMET", "state": "synced", **kw}


def run(status, tick, state, policy=None, asks=(), wakes=()):
    res = PlanWatchResult(wakes=list(wakes))
    fold(res, status, tick, tick, policy or pol(), state, asks)
    return res


def todo(res):
    return [w for w in res.wakes if w.reason == REASON_TODO]


def test_the_crop_and_floor_items_wake_the_planner_once_with_fixed_lines():
    state = PlanWatchState()
    res = run(st(deviations=[DINING]), 1000, state)
    [w] = todo(res)
    assert w.role == "planner"
    lines = w.detail.splitlines()
    assert lines[0].startswith("Your to-do list: 2 item(s)")
    assert lines[1].startswith("1. target_deviation dining_tables: differs from roadmap entry dining_tables (down)")
    assert "numeric want only" in lines[1]
    assert lines[2].startswith("2. unplanned_kind autofarm:") and "crop targets" in lines[2]


def test_a_missing_stage_entry_is_an_item_and_a_crop_target_clears_the_kind_item():
    res = run(st(missing=["beds"], targets=[crop()]), 1000, PlanWatchState())
    [w] = todo(res)
    assert "stage_target_missing beds" in w.detail and "unplanned_kind" not in w.detail


def test_only_a_default_crop_target_still_leaves_the_kind_open():
    res = run(st(targets=[crop("crop_default") | {"crop": "default"}]), 1000, PlanWatchState())
    assert "unplanned_kind autofarm" in todo(res)[0].detail


def test_an_explained_deviation_that_only_raised_the_level_is_not_listed():
    up = {"id": "bedrooms", "ref": "bedrooms", "kind": "up", "reason": "more beds"}
    res = run(st(deviations=[up], targets=[crop()]), 1000, PlanWatchState())
    assert todo(res) == []


def test_nothing_open_wakes_nobody_and_leaves_other_wakes_alone():
    keep = PlanWake("plan_shortfall", "architect", "x", key="bedrooms")
    res = run(st(targets=[crop()]), 1000, PlanWatchState(), wakes=[keep])
    assert res.wakes == [keep]


def test_the_planners_other_wakes_fold_into_the_one_list_and_owner_wakes_stay():
    owner = PlanWake("plan_shortfall", "architect", "x", key="bedrooms")
    stage = PlanWake("roadmap_stage_entered", "planner", "The fort is in the hamlet stage", key="stage-hamlet")
    res = run(st(targets=[crop()]), 1000, PlanWatchState(), wakes=[stage, owner])
    assert owner in res.wakes and not [w for w in res.wakes if w.reason == "roadmap_stage_entered"]
    [w] = todo(res)
    assert "1. [roadmap_stage_entered] The fort is in the hamlet stage" in w.detail


def test_an_item_backs_off_then_stalls_after_max_wakes_and_reopens_on_a_changed_signature():
    state = PlanWatchState()
    status = st(deviations=[DINING], targets=[crop()])
    assert todo(run(status, 1000, state))
    assert not todo(run(status, 1000 + BASE - 1, state))        # inside the backoff
    assert todo(run(status, 1000 + BASE, state))                 # second wake
    assert todo(run(status, 1000 + BASE + 2 * BASE, state))      # third wake: doubled wait
    assert state.todo["deviation:dining_tables"]["stalled"] is True
    assert not todo(run(status, 10 ** 7, state))                 # stalled: silent
    changed = st(deviations=[{**DINING, "reason": "other"}], targets=[crop()])
    assert todo(run(changed, 10 ** 7, state))                    # its state changed: reopened


def test_a_planner_pass_after_the_wake_stops_the_item():
    state = PlanWatchState()
    assert todo(run(st(deviations=[DINING], targets=[crop()]), 1000, state))
    passed = st(deviations=[DINING], targets=[crop()], pass_tick=1500)
    assert not todo(run(passed, 1000 + BASE, state))
    assert not todo(run(passed, 10 ** 7, state))


def test_an_item_that_goes_away_forgets_its_state_and_wakes_afresh_if_it_returns():
    state = PlanWatchState()
    assert todo(run(st(deviations=[DINING], targets=[crop()]), 1000, state))
    run(st(targets=[crop()]), 1100, state)
    assert state.todo == {}
    assert todo(run(st(deviations=[DINING], targets=[crop()]), 1200, state))


def test_asks_to_the_planner_are_items_and_the_list_is_capped():
    res = run(st(targets=[crop()]), 1000, PlanWatchState(), pol(max_items=2), asks=["ask-0001", "ask-0002", "ask-0003"])
    [w] = todo(res)
    assert w.detail.count("open_ask") == 2 and "Your to-do list: 2 item(s)" in w.detail
    # the third waits for the next wake, it is not lost
    state = PlanWatchState()
    run(st(targets=[crop()]), 1000, state, pol(max_items=2), asks=["ask-0001", "ask-0002", "ask-0003"])
    assert "ask:ask-0003" not in state.todo


def test_the_work_queue_off_or_an_unreadable_status_changes_nothing():
    keep = PlanWake("roadmap_stage_entered", "planner", "d", key="k")
    assert run(st(), 1000, PlanWatchState(), pol(enabled=False), wakes=[keep]).wakes == [keep]
    assert run(None, 1000, PlanWatchState(), wakes=[keep]).wakes == [keep]


def test_no_plan_keeps_the_bootstrap_wake_in_the_list_with_its_tag():
    boot = PlanWake("plan_bootstrap", "planner", "The fort has no plan", key="bootstrap")
    res = run(base_status(bootstrap=True), 1000, PlanWatchState(), wakes=[boot])
    assert "[plan_bootstrap] The fort has no plan" in todo(res)[0].detail


def test_the_state_round_trips_through_the_store(tmp_path):
    state = PlanWatchState()
    run(st(deviations=[DINING]), 1000, state)
    store = PlanWatchStore(tmp_path / "plan_watch.json")
    store.save(state)
    assert store.load().todo == state.todo


def test_the_committed_policy_ships_the_queue_on_with_autofarm_as_an_owned_kind():
    wq = load_policy().plan.work_queue
    assert wq.enabled and "autofarm" in wq.owned_kinds and load_policy().reason(REASON_TODO)




@pytest.mark.asyncio
async def test_a_cycle_wakes_the_planner_once_with_the_crop_and_floor_items_and_not_again_inside_the_backoff(tmp_path):
    clock = Clock(SEASON + 1000)
    status = _status(version=2, season=1)
    status["active"]["roadmap_stage"] = "hamlet"
    status["roadmap"] = {"stage": "hamlet", "alive": 24, "entered": False, "held": False, "cross_check": [],
                         "targets": [], "line": "ROADMAP stage hamlet (alive 24)."}
    status["last_pass_tick"] = None
    status["roadmap_check"] = {"stage": "hamlet", "missing": [], "deviations": [DINING]}
    base = _plan_policy()
    wq = WorkQueuePolicy(enabled=True, owned_kinds=KINDS)
    policy = dataclasses.replace(base, plan=dataclasses.replace(base.plan, work_queue=wq))
    tools = {"queue.overview": _queue_overview(asks={"count": 1, "ask_ids": ["ask-0007"], "to": {"planner": ["ask-0007"]}})}
    from conductor.tests.test_cycle import _base_tools
    tools = {**_base_tools(), **tools}
    deps = _plan_deps(tmp_path, clock, status, policy=policy, tools=tools)
    result = await run_cycle(1, deps)
    [call] = _planner_calls(deps)
    briefing = json.loads(call["prompt"])
    text = briefing["wake_reason"] + briefing["wake_detail"]
    assert "plan_todo" in text
    assert "target_deviation dining_tables" in text and "unplanned_kind autofarm" in text and "open_ask ask-0007" in text
    assert result.plan_watch["wakes"][0]["reason"] == REASON_TODO

    # Next cycle, same state, inside the backoff: the plan items do not wake it again.
    deps2 = _plan_deps(tmp_path, clock, status, policy=policy, tools=tools)
    await run_cycle(2, deps2)
    again = _planner_calls(deps2)
    if again:   # the ask's own addressee wake may still run it, but not for the plan items
        text2 = json.dumps(json.loads(again[0]["prompt"]))
        assert "dining_tables" not in text2 and "unplanned_kind" not in text2
