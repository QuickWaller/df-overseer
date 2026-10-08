"""A roadmap pass is recorded only from an explicit Planner pass tick (live bug
2026-10-08: the plan's own filing tick, folded into `last_reviewed_tick`, equals
the current tick on a paused fort and was read as a pass)."""

from __future__ import annotations

import json

from conductor.plan_watch import PlanWatchState, PlanWatchStore
from conductor.tests.test_roadmap_wake import rm, run, stage_wakes

LIVE_STATUS = {   # plan.status as read live: the plan's filing tick IS last_reviewed_tick
    "active": {"id": "fort_plan-0001", "roadmap_stage": None, "season_index": 128, "tick": 12930359, "version": 1},
    "alive": 24, "bootstrap": False, "flags": [], "last_reviewed_tick": 12930359, "last_pass_tick": None,
    "plan_changes_awaiting": [], "targets": [], "owners": {}, "roadmap": rm("hamlet"),
}


def test_a_plan_filing_tick_is_not_a_planner_pass_and_a_wrongly_recorded_pass_is_ignored(tmp_path):
    path = tmp_path / "plan_watch.json"
    path.write_text(json.dumps({   # the exact file the buggy build left on disk
        "awaiting": {}, "bootstrap": {"last_position": None, "next_tick": None, "stalled": False, "wakes": 0},
        "bootstrap_escalated": False, "inputs": {}, "last_refusal": None,
        "review": {"last_position": None, "next_tick": None, "stalled": False, "wakes": 0},
        "review_index": None, "review_since": None,
        "roadmap": {"last_position": None, "next_tick": None, "stalled": False, "wakes": 0},
        "roadmap_owed": None, "roadmap_passed": "hamlet", "roadmap_since": None, "roadmap_stage": "hamlet",
        "season_index": 128, "season_tick": 12930359, "targets": {},
    }))
    state = PlanWatchStore(path).load()
    (w,) = stage_wakes(run(dict(LIVE_STATUS), 12930359, state))     # paused: tick == plan tick
    assert w.role == "planner" and state.roadmap_owed == "hamlet"
    # still owed, not settled, on the next paused cycle (inside the backoff: no repeat wake)
    assert stage_wakes(run(dict(LIVE_STATUS), 12930359, state)) == [] and state.roadmap_owed == "hamlet"


def test_a_season_review_is_not_settled_by_the_plan_filing_tick_on_a_paused_fort():
    from conductor.plan_watch import REASON_REVIEW, SeasonEdge, evaluate
    from conductor.tests.test_plan_watch import policy
    state = PlanWatchState()
    st = {**LIVE_STATUS, "active": {**LIVE_STATUS["active"], "season_index": 127}, "roadmap": rm("hamlet"),
          "last_reviewed_tick": 12930359, "last_pass_tick": None}
    out = evaluate(st, 12930359, policy(shortfall=False), state, SeasonEdge(128, changed=True))     # tick == the plan's tick
    assert any(w.reason == REASON_REVIEW for w in out.wakes) and state.review_index == 128
    # a real pass at or after the owed tick settles it
    out = evaluate({**st, "last_pass_tick": 12930359}, 12930359, policy(shortfall=False), state, SeasonEdge(128))
    assert not any(w.reason == REASON_REVIEW for w in out.wakes) and state.review_index is None


def test_a_real_pass_carries_its_tick_and_settles_without_re_owing():
    state = PlanWatchState()
    run(dict(LIVE_STATUS), 12930359, state)
    after = {**LIVE_STATUS, "last_pass_tick": 12930359}
    assert stage_wakes(run(after, 12930359, state)) == []
    assert state.roadmap_owed is None and state.roadmap_passed == "hamlet@12930359"
    assert stage_wakes(run(after, 12930360, state)) == []
