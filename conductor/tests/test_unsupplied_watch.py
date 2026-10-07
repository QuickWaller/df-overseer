"""handoffs/2026-10-07-unsupplied-building-watch.md: a planned building waits on
an item kind nobody makes, so the Quartermaster wakes. Shaped on the live case
(a Bed waiting 38 game days for a BED item, ConstructBed never queued, five
manager orders all inactive). The poll parser and order join, the edge and
backoff rule in lanes.py, and a real `run_cycle` over the fakes."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.hold import HoldStore, hold_path_for
from conductor.policy import load_policy
from conductor.tests.test_cycle import _base_tools, _deps
from conductor.unsupplied_watch import unsupplied_read

POLICY = load_policy()
PB = POLICY.unsupplied_building
CARPENTER = {"job": "ConstructBed", "reaction": None, "workshop_kind": "Carpenters"}


def _row(item="BED", *, available=0, queued=0, buildings=1, producers=(CARPENTER,)):
    return {
        "item": item, "buildings_waiting": buildings, "units_needed": buildings,
        "available": available, "producers": list(producers), "jobs_queued_now": queued,
    }


def _poll(*rows, **extra):
    return {"unsupplied": list(rows), "read_failures": [], **extra}


def _order(id_=1, job="ConstructBed", *, active=False, validated=True, reaction=None, **extra):
    return {
        "id": id_, "job": job, "reaction": reaction, "active": active, "validated": validated,
        "amount_total": 0, "amount_left": 0, "finished_year": -1, **extra,
    }


# --- the parse and the order join ----------------------------------------------


def test_a_planned_building_with_no_supply_is_one_line_naming_the_producing_job_and_workshop():
    read = unsupplied_read(_poll(_row()), [])
    assert [i.item for i in read.items] == ["BED"]
    line = read.items[0].line(38 * 1200)
    assert "BED: 1 planned building waiting 38d, 0 free" in line
    assert "ConstructBed at Carpenters" in line
    assert "no order or job is making it" in line


def test_no_producer_in_the_game_data_is_said_plainly():
    read = unsupplied_read(_poll(_row(producers=())), [])
    assert "no built workshop offers a job making it" in read.items[0].line()


def test_silent_when_the_item_is_available():
    assert unsupplied_read(_poll(_row(available=2)), []).items == ()


def test_silent_when_a_workshop_job_is_already_making_it():
    assert unsupplied_read(_poll(_row(queued=1)), []).items == ()


def test_silent_when_an_active_validated_order_makes_it():
    assert unsupplied_read(_poll(_row()), [_order(active=True, validated=True)]).items == ()


def test_a_reaction_order_must_match_the_reaction_code():
    prod = {"job": "CustomReaction", "reaction": "MAKE_WOODEN_BED", "workshop_kind": "Carpenters"}
    live = _order(job="CustomReaction", reaction="MAKE_WOODEN_BED", active=True)
    other = _order(job="CustomReaction", reaction="BREW_DRINK_FROM_PLANT", active=True)
    assert unsupplied_read(_poll(_row(producers=(prod,))), [live]).items == ()
    assert unsupplied_read(_poll(_row(producers=(prod,))), [other]).items != ()


def test_an_inactive_standing_order_still_wakes_and_the_line_says_so():
    read = unsupplied_read(_poll(_row()), [_order(7, active=False)])
    assert len(read.items) == 1
    assert "order #7 for it is inactive" in read.items[0].line()
    unval = unsupplied_read(_poll(_row()), [_order(8, validated=False)])
    assert "order #8 for it is unvalidated" in unval.items[0].line()


def test_a_finished_order_is_not_supply_and_not_mentioned():
    done = _order(9, active=True, amount_total=5, amount_left=0, finished_year=1)
    read = unsupplied_read(_poll(_row()), [done])
    assert len(read.items) == 1 and "order #9" not in read.items[0].line()


def test_an_unreadable_stock_read_drops_the_line_and_keeps_the_kind_unjudged():
    read = unsupplied_read(_poll(_row(available=None)), [])
    assert read.items == () and read.unreadable == frozenset({"BED"})


def test_an_unreadable_order_list_drops_every_line_rather_than_waking():
    read = unsupplied_read(_poll(_row()), None)
    assert read.items == () and read.unreadable == frozenset({"BED"})


def test_a_failed_poll_is_none_not_an_empty_read():
    assert unsupplied_read({"error": "boom"}, []) is None
    assert unsupplied_read("garbage", []) is None
    assert unsupplied_read(_poll(), []).items == ()


# --- the edge rule and backoff ---------------------------------------------------


def _step(state, read, tick):
    lanes.apply_unsupplied_edges(POLICY, state, read, tick)
    return state


def _present(**kw):
    return unsupplied_read(_poll(_row(**kw)), [])


def test_first_sight_owes_only_the_quartermaster_one_wake():
    state = _step(lanes.LaneState(), _present(), 1000)
    assert set(state.pending) == {"quartermaster"}
    wakes = lanes.lane_wakes(POLICY, state, {})
    assert [(w.reason, w.roles) for w in wakes] == [("unsupplied_building", ("quartermaster",))]
    assert wakes[0].detail.startswith("BED: 1 planned building waiting 0d")


def test_a_served_wake_is_not_resent_while_still_unsupplied_until_the_backoff():
    state = _step(lanes.LaneState(), _present(), 1000)
    lanes.clear_served(state, "quartermaster")
    _step(state, _present(), 1000 + PB.base_ticks - 1)
    assert lanes.lane_wakes(POLICY, state, {}) == ()
    _step(state, _present(), 1000 + PB.base_ticks)
    wakes = lanes.lane_wakes(POLICY, state, {})
    assert [w.reason for w in wakes] == ["unsupplied_building"]
    assert "waiting" in wakes[0].detail


def test_backoff_doubles_then_the_item_is_stalled_after_max_wakes():
    state = lanes.LaneState()
    t = 1000
    _step(state, _present(), t)  # wake 1
    lanes.clear_served(state, "quartermaster")
    t += PB.base_ticks
    _step(state, _present(), t)  # wake 2
    lanes.clear_served(state, "quartermaster")
    assert state.unsupplied["BED"]["wakes"] == 2 and not state.unsupplied["BED"]["stalled"]
    _step(state, _present(), t + PB.base_ticks)  # too early: wait is doubled
    assert lanes.lane_wakes(POLICY, state, {}) == ()
    t += 2 * PB.base_ticks
    _step(state, _present(), t)  # wake 3
    assert state.unsupplied["BED"]["wakes"] == PB.max_wakes and state.unsupplied["BED"]["stalled"]
    lanes.clear_served(state, "quartermaster")
    _step(state, _present(), t + PB.cap_ticks * 10)
    assert lanes.lane_wakes(POLICY, state, {}) == ()  # stalled: no more wakes


def test_it_clears_when_supplied_and_wakes_afresh_if_it_recurs():
    state = _step(lanes.LaneState(), _present(), 1000)
    assert "BED" in state.unsupplied
    _step(state, unsupplied_read(_poll(_row(available=1)), []), 2000)
    assert state.unsupplied == {} and not state.pending.get("quartermaster")
    _step(state, _present(), 3000)
    assert [w.reason for w in lanes.lane_wakes(POLICY, state, {})] == ["unsupplied_building"]


def test_a_failed_poll_or_an_unreadable_kind_keeps_the_edge_state():
    state = _step(lanes.LaneState(), _present(), 1000)
    lanes.clear_served(state, "quartermaster")
    _step(state, None, 2000)
    assert "BED" in state.unsupplied
    _step(state, unsupplied_read(_poll(_row(available=None)), []), 3000)
    assert "BED" in state.unsupplied
    # Not re-woken either: the first-seen record survived.
    assert lanes.lane_wakes(POLICY, state, {}) == ()


def test_one_line_per_item_kind_in_one_wake():
    read = unsupplied_read(_poll(_row("BED"), _row("CHAIR", buildings=2)), [])
    state = _step(lanes.LaneState(), read, 1000)
    (wake,) = lanes.lane_wakes(POLICY, state, {})
    assert wake.detail.count("planned building") == 2 and "BED:" in wake.detail and "CHAIR:" in wake.detail


def test_state_survives_the_store_round_trip(tmp_path):
    state = _step(lanes.LaneState(), _present(), 1000)
    store = lanes.LaneStore(tmp_path / "s.json")
    store.save(state)
    assert store.load() == state


def test_a_save_reload_that_puts_the_clock_behind_rearms_the_wake():
    state = _step(lanes.LaneState(), _present(), 5000)
    lanes.clear_served(state, "quartermaster")
    _step(state, _present(), 100)
    assert [w.reason for w in lanes.lane_wakes(POLICY, state, {})] == ["unsupplied_building"]


def test_no_lane_with_unsupplied_means_no_pending_wake():
    quiet = replace(POLICY, lane_triggers={r: replace(l, unsupplied=False) for r, l in POLICY.lane_triggers.items()})
    state = lanes.LaneState()
    lanes.apply_unsupplied_edges(quiet, state, _present(), 1000)
    assert state.pending == {}


# --- through a real cycle ---------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unsupplied_building_wakes_only_the_quartermaster_once(tmp_path):
    deps = _deps(tmp_path, tools=_base_tools(**{"workjob.unsupplied": _poll(_row())}))
    result = await run_cycle(1, deps)
    assert result.roles_woken == ("quartermaster",)
    brief = json.loads((result.archived_path / "briefings.json").read_text(encoding="utf-8"))["quartermaster"]
    assert brief["wake_reason"] == "unsupplied_building"
    result2 = await run_cycle(2, deps)  # served, edge consumed, backoff not elapsed
    assert result2.roles_woken == ()


@pytest.mark.asyncio
async def test_the_operator_hold_does_not_suppress_the_wake(tmp_path):
    deps = _deps(tmp_path, tools=_base_tools(**{"workjob.unsupplied": _poll(_row())}))
    HoldStore(hold_path_for(deps.cursor_store.path)).set(
        "keeping the fort paused to plan", who="op",
    )
    result = await run_cycle(1, deps)
    assert result.hold  # the hold really stood this cycle
    assert result.roles_woken == ("quartermaster",)


@pytest.mark.asyncio
async def test_a_live_order_for_the_item_keeps_the_cycle_quiet(tmp_path):
    tools = _base_tools(**{
        "workjob.unsupplied": _poll(_row()),
        "orders.list": {"orders": [_order(active=True)], "manager_appointed": True},
    })
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()


@pytest.mark.asyncio
async def test_a_failed_poll_does_not_stop_the_cycle(tmp_path):
    tools = _base_tools()
    tools.pop("workjob.unsupplied", None)  # the allowlist entry is not deployed yet
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert result.roles_woken == ()
