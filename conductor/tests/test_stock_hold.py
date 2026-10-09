"""Item binding 3a (register 2026-10-09): the stateless stock check at execution, the hold note,
the wake rules, the briefing line, and the policy loader. No ledger: a short step is held and
retries, and the only thing stored is the hold note."""

import re
from dataclasses import replace

import pytest

from conductor import stock_hold
from conductor.briefing import build_briefing, build_ruling_briefing
from conductor.execute import ExecuteState, ExecuteStore, REASON_ATTENTION, run_execute
from conductor.policy import (
    ExecutionPolicy, PolicyError, StockCheckPolicy, StockConsumer, load_policy,
)
from conductor.tests.test_execute import Script, SUCCESS, _proj, _ready
from conductor.triage import Wake

pytestmark = pytest.mark.asyncio

CONSUMER = StockConsumer(item_arg="job", item_map={"ConstructBlocks": "BOULDER"}, count_arg="amount", per_unit=0.25)
STOCK = StockCheckPolicy(
    enabled=True, margin=1, margin_fraction=0.0, consumers={"orders.create": CONSUMER},
    survival=re.compile("brew|drink|food", re.IGNORECASE), wake_after_ticks=1200,
)
POLICY = replace(ExecutionPolicy(), stock_check=STOCK)


def _blocks(n=1, amount=8, **extra):
    return _ready(n, tool="orders.create", args={"job": "ConstructBlocks", "amount": amount}, **extra)


def _stock(free, in_job=0):
    return {"available_units": free, "in_job_units": in_job, "total_units": free + in_job}


async def _run(script, state=None, tick=10000, policy=POLICY):
    state = state or ExecuteState()
    report = await run_execute(script, policy, state, game_tick=tick)
    return report, state


def _runs(script):
    return [a["step_id"] for t, a in script.calls if t == "queue.run_step"]


# ---------------------------------------------------------------- need and margin


def test_need_is_count_times_per_unit_rounded_up_and_unmapped_items_are_skipped():
    assert stock_hold.need_for(CONSUMER, {"job": "ConstructBlocks", "amount": 8}) == ("BOULDER", 2)
    assert stock_hold.need_for(CONSUMER, {"JOB": "ConstructBlocks", "AMOUNT": "5"}) == ("BOULDER", 2)
    assert stock_hold.need_for(CONSUMER, {"job": "MakeBucket", "amount": 3}) is None
    assert stock_hold.need_for(CONSUMER, {"job": "ConstructBlocks", "amount": "lots"}) is None


def test_margin_is_the_larger_of_fixed_and_fraction():
    assert stock_hold.required_with_margin(replace(STOCK, margin=1, margin_fraction=0.1), 5) == 6
    assert stock_hold.required_with_margin(replace(STOCK, margin=1, margin_fraction=0.5), 10) == 15
    assert stock_hold.short_reason("BOULDER", 2, 3, 3, None) is None
    assert "short BOULDER: needs 2 (+1 margin), 2 free" in stock_hold.short_reason("BOULDER", 2, 3, 2, None)
    assert "4 more held by other jobs" in stock_hold.short_reason("BOULDER", 2, 3, 0, 4)


# ---------------------------------------------------------------- the check at execution


async def test_enough_stock_runs_the_step_and_nothing_is_stored():
    script = Script({"open_projects": [_proj()], "ready_steps": [_blocks()]},
                    {"stocks.availability": _stock(3), "queue.run_step": SUCCESS})
    report, state = await _run(script)
    assert _runs(script) == ["project-0001/s1"]
    assert ("stocks.availability", {"type": "BOULDER"}) in script.calls
    assert state.holds == {}


async def test_short_stock_holds_the_step_with_a_one_line_reason_and_does_not_run_or_quicksave():
    script = Script({"open_projects": [_proj(steps_open=1)], "ready_steps": [_blocks()]},
                    {"stocks.availability": _stock(2, in_job=3), "queue.run_step": SUCCESS})
    saves = []

    async def quicksave():
        saves.append(1)

    state = ExecuteState()
    report = await run_execute(script, POLICY, state, game_tick=10000, quicksave=quicksave)
    assert _runs(script) == [] and not saves and report.steps_run == 0
    note = state.holds["project-0001/s1"]
    assert note["since"] == 10000 and note["pid"] == "project-0001"
    assert "short BOULDER" in note["why"] and "3 more held by other jobs" in note["why"]
    # an ordinary hold is a briefing line, not a wake
    assert report.wakes == []


async def test_the_held_step_retries_next_cycle_and_the_note_goes_when_it_runs():
    state = ExecuteState()
    snap = {"open_projects": [_proj()], "ready_steps": [_blocks()]}
    await _run(Script(snap, {"stocks.availability": _stock(1)}), state, tick=10000)
    assert "project-0001/s1" in state.holds
    again = Script(snap, {"stocks.availability": _stock(5), "queue.run_step": SUCCESS})
    await _run(again, state, tick=10100)
    assert _runs(again) == ["project-0001/s1"] and state.holds == {}


async def test_the_note_keeps_its_first_tick_across_cycles_and_dies_with_the_step():
    state = ExecuteState()
    snap = {"open_projects": [_proj()], "ready_steps": [_blocks()]}
    await _run(Script(snap, {"stocks.availability": _stock(0)}), state, tick=10000)
    await _run(Script(snap, {"stocks.availability": _stock(0)}), state, tick=10300)
    assert state.holds["project-0001/s1"]["since"] == 10000
    await _run(Script({"open_projects": [_proj()], "ready_steps": []}), state, tick=10400)
    assert state.holds == {}


async def test_a_tool_that_declares_nothing_is_never_checked():
    script = Script({"open_projects": [_proj()], "ready_steps": [_ready(1, tool="blueprint.apply", args={})]},
                    {"queue.run_step": SUCCESS})
    await _run(script)
    assert "stocks.availability" not in script.names() and _runs(script) == ["project-0001/s1"]


async def test_an_unreadable_stock_fails_open_and_the_step_runs():
    script = Script({"open_projects": [_proj()], "ready_steps": [_blocks()]}, {"queue.run_step": SUCCESS})
    report, state = await _run(script)  # stocks.availability raises MCPToolError in the Script
    assert _runs(script) == ["project-0001/s1"] and state.holds == {}


async def test_a_disabled_check_does_nothing():
    script = Script({"open_projects": [_proj()], "ready_steps": [_blocks()]}, {"queue.run_step": SUCCESS})
    await _run(script, policy=replace(POLICY, stock_check=replace(STOCK, enabled=False)))
    assert "stocks.availability" not in script.names()


async def test_one_item_is_read_once_per_pass():
    script = Script({"open_projects": [_proj()], "ready_steps": [_blocks(1), _blocks(2)]},
                    {"stocks.availability": _stock(0)})
    await _run(script)
    assert script.names().count("stocks.availability") == 1


# ---------------------------------------------------------------- 3a: which holds wake


async def test_a_survival_hold_wakes_once():
    brew = _ready(1, tool="orders.create", args={"job": "ConstructBlocks", "amount": 8, "note": "drink supply"})
    snap = {"open_projects": [_proj()], "ready_steps": [brew]}
    state = ExecuteState()
    report, _ = await _run(Script(snap, {"stocks.availability": _stock(0)}), state)
    assert [w.reason for w in report.wakes] == [REASON_ATTENTION]
    assert "food, drink or defence" in report.wakes[0].text and "short BOULDER" in report.wakes[0].text
    again, _ = await _run(Script(snap, {"stocks.availability": _stock(0)}), state, tick=10200)
    assert again.wakes == []  # the same cause does not wake twice


async def test_a_hold_older_than_a_game_day_wakes():
    snap = {"open_projects": [_proj()], "ready_steps": [_blocks()]}
    state = ExecuteState()
    first, _ = await _run(Script(snap, {"stocks.availability": _stock(0)}), state, tick=10000)
    assert first.wakes == []
    later, _ = await _run(Script(snap, {"stocks.availability": _stock(0)}), state, tick=11199)
    assert later.wakes == []
    old, _ = await _run(Script(snap, {"stocks.availability": _stock(0)}), state, tick=11200)
    assert len(old.wakes) == 1 and "over a game day" in old.wakes[0].text


async def test_a_hold_that_blocks_other_steps_in_its_project_wakes():
    snap = {"open_projects": [_proj(steps_open=3)], "ready_steps": [_blocks()]}
    report, _ = await _run(Script(snap, {"stocks.availability": _stock(0)}))
    assert len(report.wakes) == 1 and "blocks other steps" in report.wakes[0].text


async def test_a_wake_for_a_direct_action_does_not_close_it():
    snap = {"open_projects": [_proj(steps_open=2, direct=True)], "ready_steps": [_blocks()]}
    script = Script(snap, {"stocks.availability": _stock(0)})
    report, state = await _run(script)
    assert len(report.wakes) == 1 and "queue.close" not in script.names()


# ---------------------------------------------------------------- the briefing line


def test_hold_lines_are_oldest_first_and_capped():
    holds = {f"p/s{i}": {"pid": "p", "tool": "orders.create", "why": "short BOULDER", "since": 100 - i} for i in range(7)}
    lines = stock_hold.hold_lines(holds, cap=3)
    assert len(lines) == 4 and lines[0].startswith("held step p/p/s6") and lines[-1] == "... and 4 more held steps"


def _wake():
    return Wake("routine", "x", ("overseer",), "full_speed")


def test_the_overseer_briefings_carry_the_hold_lines_and_omit_them_when_none():
    kw = dict(role="overseer", game_tick=1, wake=_wake(), vitals={}, diff_events=[], queue_summary={})
    assert "held_steps" not in build_briefing(**kw)
    assert build_briefing(**kw, stock_holds=["held step p/s1 (orders.create): short BOULDER"])["held_steps"]
    text = build_ruling_briefing(game_tick=1, wake=_wake(), vitals={}, alerts=[], pending_brief=None,
                                 stock_holds=["held step p/s1 (orders.create): short BOULDER"])
    assert "HELD held step p/s1" in text


async def test_the_hold_note_survives_the_store_round_trip(tmp_path):
    state = ExecuteState()
    state.holds["p/s1"] = {"pid": "p", "tool": "t", "why": "w", "since": 5}
    store = ExecuteStore(tmp_path / "e.json")
    store.save(state)
    assert store.load().holds == state.holds


# ---------------------------------------------------------------- policy


def test_the_shipped_policy_loads_the_stock_check_and_stale_order_blocks():
    pol = load_policy().execution
    assert pol.stock_check.enabled and pol.stock_check.margin >= 1
    assert pol.stock_check.consumers["orders.create"].item_map["ConstructBlocks"] == "BOULDER"
    assert pol.stock_check.survival.search("MakeWeapon") and pol.stock_check.wake_after_ticks == 1200
    assert pol.stale_orders.enabled and "abandoned" in pol.stale_orders.outcomes


def test_a_bad_stock_check_block_is_a_policy_error(tmp_path):
    from conductor.policy import _load_stock_check
    for bad in ({"margin": -1}, {"consumers": {"t": {}}}, {"survival": "("}, {"wake_after_ticks": 0}):
        with pytest.raises(PolicyError):
            _load_stock_check(bad, tmp_path)


# ---------------------------------------------------------------- 3b in the execute phase


async def test_the_stale_order_pass_calls_the_server_tool_with_policy_and_logs_each_cancel():
    from conductor.policy import StaleOrderPolicy
    pol = replace(POLICY, stale_orders=StaleOrderPolicy(enabled=True, outcomes=("abandoned",),
                                                        completed_grace_ticks=600, max_per_cycle=2))
    cancelled = {"cancelled": [{"project_id": "project-0003", "handle": "order-5", "outcome": "abandoned"}],
                 "left": [{"project_id": "project-0003", "handle": "order-6", "why": "left alone: the game has started it"}]}
    script = Script({"ready_steps": []}, {"queue.cancel_stale_orders": cancelled})
    report, _ = await _run(script, policy=pol, tick=5000)
    assert ("queue.cancel_stale_orders", {"outcomes": ["abandoned"], "completed_grace_ticks": 600, "max": 2,
                                          "tick": 5000}) in script.calls
    kinds = [a["kind"] for a in report.actions]
    assert "order_cancelled" in kinds and "order_left" in kinds


async def test_the_stale_order_pass_is_off_by_default_and_a_failed_call_never_stops_the_phase():
    script = Script({"ready_steps": []})
    await _run(script, policy=ExecutionPolicy())
    assert "queue.cancel_stale_orders" not in script.names()
    from conductor.policy import StaleOrderPolicy
    on = replace(POLICY, stale_orders=StaleOrderPolicy(enabled=True))
    report, _ = await _run(Script({"ready_steps": []}), policy=on)  # the tool raises in the Script
    assert report.ran and report.errors
