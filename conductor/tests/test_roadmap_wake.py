"""Fort roadmap V1 on the conductor side (register 2026-10-08): the
`roadmap_stage_entered` wake from `conductor/plan_watch.py`, the Overseer's
one briefing line, the Planner's utilisation summary and the per-cycle
utilisation sample. Pure `evaluate` tests plus `run_cycle` over the fakes."""

from __future__ import annotations

import json

import pytest

from conductor import utilisation
from conductor.briefing import build_briefing, build_ruling_briefing
from conductor.plan_watch import (
    PlanWatchState, PlanWatchStore, REASON_STAGE, evaluate,
)
from conductor.cycle import run_cycle
from conductor.tests.test_plan_cycle import (
    Clock, SEASON, _plan_deps, _planner_calls, _store,
)
from conductor.tests.test_cycle import _base_tools
from conductor.tests.test_plan_watch import policy, status
from conductor.triage import Wake

BASE = 12000
pytestmark = pytest.mark.asyncio


def rm(stage="hamlet", *, alive=24, summary="Twenty or more citizens.", cross=()):
    return {
        "stage": stage, "alive": alive, "summary": summary, "entered": False, "held": False,
        "cross_check": list(cross), "targets": [], "line": f"ROADMAP stage {stage} (alive {alive}).",
    }


def with_roadmap(base, block, *, plan_stage=None):
    out = dict(base)
    out["roadmap"] = block
    if out.get("active") is not None and plan_stage is not None:
        out["active"] = {**out["active"], "roadmap_stage": plan_stage}
    return out


def run(st, tick, state, **kw):
    return evaluate(st, tick, policy(shortfall=False), state, None, **kw)


def stage_wakes(result):
    return [w for w in result.wakes if w.reason == REASON_STAGE]


# ---- the wake ------------------------------------------------------------------------------------


def test_a_plan_filed_before_stages_existed_is_asked_to_adopt_the_current_stage_once():
    state = PlanWatchState()
    res = run(with_roadmap(status(), rm("hamlet")), 1000, state)
    (w,) = stage_wakes(res)
    assert w.role == "planner" and w.key == "stage-hamlet"
    assert "hamlet stage" in w.detail and "before stages existed" in w.detail and "plan.read" in w.detail
    assert "deviation_reason" in w.detail
    assert state.roadmap_stage == "hamlet" and state.roadmap_owed == "hamlet"
    # inside the backoff nothing more is raised, edge triggered
    assert stage_wakes(run(with_roadmap(status(), rm("hamlet")), 1000 + BASE - 1, state)) == []


def test_the_wake_is_settled_by_a_plan_filed_in_that_stage():
    state = PlanWatchState()
    run(with_roadmap(status(), rm("hamlet")), 1000, state)
    res = run(with_roadmap(status(), rm("hamlet"), plan_stage="hamlet"), 1000 + BASE, state)
    assert stage_wakes(res) == [] and state.roadmap_owed is None


def test_a_planner_pass_settles_it_too():
    state = PlanWatchState()
    run(with_roadmap(status(), rm("hamlet")), 1000, state)
    res = run(with_roadmap(status(reviewed=1500), rm("hamlet")), 1000 + BASE, state)
    assert stage_wakes(res) == [] and state.roadmap_owed is None


def test_an_unanswered_wake_retries_on_the_backoff_a_bounded_number_of_times():
    state = PlanWatchState()
    tick, n = 1000, 0
    for _ in range(10):
        n += len(stage_wakes(run(with_roadmap(status(), rm("hamlet")), tick, state)))
        tick += SEASON
    assert n == 3                                       # review_max_wakes, then left alone


def test_a_plan_already_in_the_stage_is_not_woken_for():
    state = PlanWatchState()
    res = run(with_roadmap(status(), rm("hamlet"), plan_stage="hamlet"), 1000, state)
    assert stage_wakes(res) == [] and state.roadmap_stage == "hamlet" and state.roadmap_owed is None


def test_entering_the_next_stage_wakes_again_and_a_dip_does_not():
    state = PlanWatchState()
    run(with_roadmap(status(), rm("hamlet"), plan_stage="hamlet"), 1000, state)
    # the server holds the stage through a dip, so the block still says hamlet: nothing happens
    assert stage_wakes(run(with_roadmap(status(), rm("hamlet", alive=17), plan_stage="hamlet"), 2000, state)) == []
    res = run(with_roadmap(status(), rm("village", alive=51, summary="Fifty or more."), plan_stage="hamlet"), 3000, state)
    (w,) = stage_wakes(res)
    assert w.key == "stage-village" and "village stage" in w.detail and "for the hamlet stage" in w.detail


def test_a_fort_with_no_plan_is_not_owed_an_adoption_version_one_is_composed_from_the_stage():
    state = PlanWatchState()
    res = run({"active": None, "bootstrap": True, "last_reviewed_tick": None, "plan_changes_awaiting": [],
               "roadmap": rm("hamlet")}, 1000, state)
    assert stage_wakes(res) == [] and state.roadmap_stage == "hamlet" and state.roadmap_owed is None


def test_a_missing_roadmap_block_changes_nothing_and_wakes_nobody():
    state = PlanWatchState()
    res = run(status(), 1000, state)                   # a server that predates the roadmap
    assert stage_wakes(res) == [] and res.roadmap is None and state.roadmap_stage is None


def test_a_disagreeing_game_flag_is_noted_not_acted_on():
    cross = [{"stage": "village", "requires_population": 50, "alive": 24, "state": "disagree", "game_flag_met": True}]
    state = PlanWatchState()
    res = run(with_roadmap(status(), rm("hamlet", cross=cross), plan_stage="hamlet"), 1000, state)
    assert any("disagrees with alive 24" in n for n in res.notes) and res.wakes == []


def test_the_roadmap_cursor_survives_a_save_and_load(tmp_path):
    state = PlanWatchState()
    run(with_roadmap(status(), rm("hamlet")), 1000, state)
    store = PlanWatchStore(tmp_path / "plan_watch.json")
    store.save(state)
    again = store.load()
    assert (again.roadmap_stage, again.roadmap_owed, again.roadmap_since) == ("hamlet", "hamlet", 1000)
    assert again.roadmap.wakes == 1 and stage_wakes(run(with_roadmap(status(), rm("hamlet")), 1001, again)) == []


def test_the_result_dict_carries_the_roadmap_for_the_cycle_summary():
    res = run(with_roadmap(status(), rm("hamlet")), 1000, PlanWatchState())
    d = res.as_dict()
    assert d["roadmap"]["stage"] == "hamlet" and d["roadmap"]["line"].startswith("ROADMAP stage hamlet")


# ---- the briefing lines -------------------------------------------------------------------------------


def _wake():
    return Wake("routine_review", "d", ("overseer",), "full_speed")


def test_the_overseer_ruling_briefing_carries_one_roadmap_line_after_the_vitals():
    text = build_ruling_briefing(
        game_tick=5, wake=_wake(), vitals={"alive": 24}, alerts=[], pending_brief=None,
        roadmap_line="ROADMAP stage hamlet (alive 24, village at 50): bedrooms 1/alive.",
    )
    lines = text.splitlines()
    assert lines[2].startswith("ALERT") is False and "ROADMAP stage hamlet" in lines[2]
    assert sum("ROADMAP" in ln for ln in lines) == 1
    assert "ROADMAP" not in build_ruling_briefing(
        game_tick=5, wake=_wake(), vitals={}, alerts=[], pending_brief=None)


def test_the_json_briefing_carries_the_roadmap_line_and_the_planners_utilisation_only_when_given():
    kw = dict(role="planner", game_tick=1, wake=_wake(), vitals={}, diff_events=[], queue_summary={})
    plain = build_briefing(**kw)
    assert "roadmap" not in plain and "utilisation" not in plain
    full = build_briefing(**kw, roadmap_line="ROADMAP stage hamlet.", utilisation={"samples": 3, "sleep": None})
    assert full["roadmap"] == "ROADMAP stage hamlet." and full["utilisation"]["samples"] == 3
    long = build_briefing(**kw, roadmap_line="x" * 2000)
    assert len(long["roadmap"]) <= 400


# ---- utilisation ------------------------------------------------------------------------------------------


def _unit_status(*jobs):
    return {"filter": "all", "count": len(jobs), "citizens": [{"id": i, "job": j} for i, j in enumerate(jobs)]}


def test_a_sample_counts_sleep_eat_and_drink_jobs_per_alive():
    row = utilisation.sample(
        _unit_status(*(["Sleep"] * 2 + ["Eat", "Drink", "Plant seeds"] + ["idle"] * 15)), 20, 1234,
    )
    assert row["tick"] == 1234 and row["citizens"] == 20
    assert (row["sleep"], row["eat"], row["drink"]) == (2, 1, 1)
    assert row["sleep_per_alive"] == 0.1 and row["eat_per_alive"] == 0.05


def test_the_per_alive_denominator_is_vitals_alive_else_the_citizens_read():
    s = _unit_status("Sleep", "idle", "idle", "idle")
    assert utilisation.sample(s, 8, 5)["sleep_per_alive"] == 0.125
    assert utilisation.sample(s, None, 5)["sleep_per_alive"] == 0.25
    assert utilisation.sample(s, 0, 5)["sleep_per_alive"] == 0.25      # a zero count is not a divisor


@pytest.mark.parametrize("raw,tick", [
    ({"error": "no fort"}, 5), (None, 5), ({"citizens": "x"}, 5), (_unit_status("Sleep"), None), (_unit_status("Sleep"), True),
])
def test_an_unusable_read_or_tick_gives_no_sample_never_a_zero(raw, tick):
    assert utilisation.sample(raw, 10, tick) is None


def test_the_summary_gives_peak_p90_and_last_and_says_when_it_is_thin():
    rows = [utilisation.sample(_unit_status(*(["Sleep"] * n + ["idle"] * (10 - n))), 10, t)
            for t, n in enumerate([0, 1, 1, 2, 5, 1, 0, 1, 1, 1])]
    s = utilisation.summarise(rows)
    assert s["samples"] == 10 and s["sleep"]["peak"] == 0.5 and s["sleep"]["last"] == 0.1
    assert s["sleep"]["p90"] == 0.5 and s["eat"] == {"peak": 0.0, "p90": 0.0, "last": 0.0}
    assert utilisation.summarise([]) == {"samples": 0, "sleep": None, "eat": None, "drink": None}


def test_the_store_appends_once_per_game_tick_and_survives_a_torn_line(tmp_path):
    store = utilisation.UtilisationStore(tmp_path / "utilisation.jsonl")
    a = utilisation.sample(_unit_status("Sleep", "idle"), 2, 100)
    assert store.append(a) is True
    assert store.append(a) is False                    # a paused fort: the same instant is not weighed twice
    assert store.append(utilisation.sample(_unit_status("idle", "idle"), 2, 50)) is True   # a reload went back
    with store.path.open("a", encoding="utf-8") as fh:
        fh.write("{torn\n")
    assert [r["tick"] for r in store.rows()] == [100, 50]
    assert store.summary()["samples"] == 2


# ---- through a real cycle ---------------------------------------------------------------------------------------


def _cycle_status(plan_stage=None):
    st = status(version=3, season=1)
    return with_roadmap(st, rm("hamlet"), plan_stage=plan_stage)


def _tools_with_jobs(jobs):
    return {**_base_tools(), "labor.unit-status": _unit_status(*jobs)}


async def test_a_cycle_wakes_the_planner_for_the_stage_samples_utilisation_and_briefs_it(tmp_path):
    clock = Clock(SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _cycle_status(), tools=_tools_with_jobs(["Sleep", "Eat", "idle", "idle"]))
    result = await run_cycle(1, deps)
    assert "planner" in result.roles_woken
    [call] = _planner_calls(deps)
    briefing = json.loads(call["prompt"])
    assert "roadmap_stage_entered" in briefing["wake_reason"] + briefing["wake_detail"]
    assert briefing["roadmap"].startswith("ROADMAP stage hamlet")
    assert briefing["utilisation"]["samples"] == 1 and briefing["utilisation"]["sleep"]["last"] > 0
    rows = utilisation.UtilisationStore(tmp_path / "utilisation.jsonl").rows()
    assert len(rows) == 1 and rows[0]["sleep"] == 1 and rows[0]["eat"] == 1
    assert result.plan_watch["roadmap"]["stage"] == "hamlet"
    assert _store(tmp_path).load().roadmap_owed == "hamlet"


async def test_a_dry_run_samples_nothing_into_the_series(tmp_path):
    clock = Clock(SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _cycle_status(), tools=_tools_with_jobs(["Sleep", "idle"]), dry_run=True)
    await run_cycle(1, deps)
    assert not (tmp_path / "utilisation.jsonl").exists()


async def test_a_failed_unit_status_read_is_not_fatal_and_records_nothing(tmp_path):
    clock = Clock(SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, _cycle_status(plan_stage="hamlet"))   # no labor.unit-status tool at all
    result = await run_cycle(1, deps)
    assert result.archived_path is not None
    assert not (tmp_path / "utilisation.jsonl").exists()
    assert result.roles_woken == ()


async def test_the_series_is_not_sampled_with_the_planner_switched_off(tmp_path):
    import dataclasses
    from conductor.tests.test_plan_cycle import OFF
    clock = Clock(SEASON + 1000)
    deps = _plan_deps(tmp_path, clock, {"unused": True}, policy=OFF, tools=_tools_with_jobs(["Sleep"]))
    await run_cycle(1, deps)
    assert not (tmp_path / "utilisation.jsonl").exists()
    assert not any(t == "labor.unit-status" for t, _ in deps.tool_caller.calls)
    assert dataclasses.is_dataclass(OFF)
