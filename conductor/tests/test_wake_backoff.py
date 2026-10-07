"""handoffs/2026-10-07-wake-cleanup.md item 3: renotify counted in wakes
(exponential backoff, stalled after three) for stalled orders, stuck jobs, ore
exposure and threshold alerts, all through `conductor/backoff.py`."""

from __future__ import annotations

from conductor import backoff, lanes
from conductor.cursors import CursorStore
from conductor.job_watch import JobWatchStore, evaluate_jobs
from conductor.order_watch import evaluate_orders
from conductor.ore_watch import ore_read_from_sites
from conductor.policy import load_policy
from conductor.tests.test_ore_watch import HEM2, _row

POLICY = load_policy()


def test_the_backoff_doubles_per_wake_and_stalls_after_the_third():
    rule = backoff.Backoff(base_ticks=1000, cap_ticks=100800, max_wakes=3)
    rec, due, stalled = backoff.advance(None, 0, rule)
    assert (due, stalled, rec["wakes"]) == (True, False, 1)
    rec, due, _ = backoff.advance(rec, 999, rule)
    assert due is False
    rec, due, stalled = backoff.advance(rec, 1000, rule)  # wait after wake 1 = base
    assert (due, stalled, rec["wakes"]) == (True, False, 2)
    rec, due, _ = backoff.advance(rec, 2999, rule)  # wait after wake 2 = 2 * base
    assert due is False
    rec, due, stalled = backoff.advance(rec, 3000, rule)
    assert (due, stalled, rec["wakes"]) == (True, True, 3)
    rec, due, _ = backoff.advance(rec, 10_000_000, rule)  # stalled: silent however long
    assert due is False


def test_the_wait_is_capped():
    rule = backoff.Backoff(base_ticks=1000, cap_ticks=3000, max_wakes=9)
    assert backoff.wait_ticks(rule, 1) == 1000
    assert backoff.wait_ticks(rule, 5) == 3000


def test_a_clock_that_went_backwards_starts_the_fact_over():
    rule = backoff.Backoff(1000, max_wakes=3)
    old = {"first": 0, "last": 90000, "wakes": 3, "stalled": True}
    rec, due, _ = backoff.advance(old, 500, rule)
    assert due is True and rec["wakes"] == 1 and rec["stalled"] is False


def _order(id=0):
    return {"id": id, "validated": True, "active": False, "amount_left": 5, "amount_total": 5, "finished_year": -1}


def test_a_stalled_order_wakes_three_times_with_growing_gaps_then_stays_silent(tmp_path):
    store = CursorStore(tmp_path / "cursors.json")
    fired = []

    def at(tick):
        r = evaluate_orders([_order(3)], game_tick=tick, threshold_ticks=100, renotify_ticks=1000,
                            cursor_store=store, dry_run=False)
        if r.stalled_ids:
            fired.append(tick)

    at(10)  # first seen
    for tick in range(200, 20000, 100):
        at(tick)
    assert fired == [200, 1200, 3200]  # then base, 2x base, and stalled


def test_a_cleared_order_wakes_afresh_when_it_stalls_again(tmp_path):
    store = CursorStore(tmp_path / "cursors.json")
    kw = dict(threshold_ticks=100, renotify_ticks=1000, cursor_store=store, dry_run=False)
    evaluate_orders([_order(3)], game_tick=10, **kw)
    assert evaluate_orders([_order(3)], game_tick=200, **kw).stalled_ids == (3,)
    running = dict(_order(3), active=True)  # dispatched: no longer a candidate
    evaluate_orders([running], game_tick=300, **kw)
    evaluate_orders([_order(3)], game_tick=400, **kw)
    assert evaluate_orders([_order(3)], game_tick=600, **kw).stalled_ids == (3,)


def test_a_stuck_job_stops_waking_after_three_wakes_but_stays_listed(tmp_path):
    store = JobWatchStore(tmp_path / "job_watch.json")
    job = {"job_type": "ConstructBuilding", "detail": "Construct Bed", "building": "Bed",
           "waiting_on": "suspended", "near_landmark": "Well", "direction": "N", "distance_tiles": 4}
    woke, listed = [], 0
    for tick in range(100, 60000, 100):
        r = evaluate_jobs([job], game_tick=tick, unclaimed_threshold_ticks=500, suspended_threshold_ticks=500,
                          renotify_ticks=2000, store=store, dry_run=False)
        if r.any_due:
            woke.append(tick)
        listed += bool(r.stuck)
    assert len(woke) == 3
    assert woke[1] - woke[0] >= 2000 and woke[2] - woke[1] >= 4000
    assert listed > 3  # the standing line in the briefing stays


def test_ore_wakes_three_times_with_growing_gaps_then_stops_until_mined():
    state = lanes.LaneState()
    exposed = ore_read_from_sites([_row("site-5", HEM2)])
    base = POLICY.ore_renotify_ticks
    woke = []
    for tick in range(0, base * 40, 1000):
        state.pending.clear()
        lanes.apply_ore_edges(POLICY, state, exposed, tick)
        if state.pending:
            woke.append(tick)
    assert len(woke) == POLICY.renotify_max_wakes
    assert woke[1] - woke[0] >= base and woke[2] - woke[1] >= 2 * base
    # Mined (gone from the read), then exposed again: wakes afresh.
    lanes.apply_ore_edges(POLICY, state, ore_read_from_sites([_row("site-5", [])]), base * 50)
    state.pending.clear()
    lanes.apply_ore_edges(POLICY, state, exposed, base * 51)
    assert state.pending


def test_a_crossed_alert_that_stays_crossed_renotifies_with_backoff_then_stalls():
    state = lanes.LaneState()
    base = POLICY.alert_renotify_ticks
    line = {"drink_per_citizen": "Drink is low"}
    woke = []
    for tick in range(0, base * 40, 1000):
        state.pending.clear()
        lanes.apply_alert_edges(POLICY, state, {"drink_per_citizen": True}, line, tick)
        if state.pending:
            woke.append(tick)
    assert len(woke) == POLICY.renotify_max_wakes
    assert woke[1] - woke[0] >= base and woke[2] - woke[1] >= 2 * base
    # It clears and crosses again: a fresh edge wakes immediately.
    lanes.apply_alert_edges(POLICY, state, {"drink_per_citizen": False}, {}, base * 50)
    state.pending.clear()
    lanes.apply_alert_edges(POLICY, state, {"drink_per_citizen": True}, line, base * 51)
    assert state.pending


def test_an_alert_edge_without_a_tick_wakes_once_and_does_not_renotify():
    state = lanes.LaneState()
    lanes.apply_alert_edges(POLICY, state, {"drink_per_citizen": True}, {"drink_per_citizen": "x"})
    assert state.pending
    state.pending.clear()
    lanes.apply_alert_edges(POLICY, state, {"drink_per_citizen": True}, {"drink_per_citizen": "x"})
    assert not state.pending
