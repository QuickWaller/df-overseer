"""conductor/order_watch.py: stalled vs blocked orders, the threshold gate,
the renotify cooldown, and bookkeeping reset once an order stops being a
candidate."""

from __future__ import annotations

from conductor.cursors import CursorStore
from conductor.order_watch import evaluate_orders


def _store(tmp_path) -> CursorStore:
    return CursorStore(tmp_path / "cursors.json")


def _order(id=0, validated=True, active=False, amount_left=5, amount_total=5, finished_year=-1):
    return {
        "id": id, "validated": validated, "active": active,
        "amount_left": amount_left, "amount_total": amount_total,
        "finished_year": finished_year,
    }


def test_a_freshly_stalled_order_does_not_fire_before_the_threshold(tmp_path):
    store = _store(tmp_path)
    result = evaluate_orders(
        [_order()], game_tick=1000, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert result.stalled_ids == ()
    assert result.any_due is False


def test_an_order_stalled_past_the_threshold_fires_once(tmp_path):
    store = _store(tmp_path)
    # Cycle 1 at tick 1000: first seen, not yet past threshold.
    evaluate_orders(
        [_order(id=7)], game_tick=1000, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    # Cycle 2 at tick 2300 (1300 ticks later): past the threshold.
    result = evaluate_orders(
        [_order(id=7)], game_tick=2300, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert result.stalled_ids == (7,)


def test_the_same_stalled_order_does_not_refire_every_cycle(tmp_path):
    """The handoff's own requirement: 'how not to wake every cycle for the
    same order stalled for a known reason.'"""
    store = _store(tmp_path)
    evaluate_orders(
        [_order(id=7)], game_tick=1000, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    first = evaluate_orders(
        [_order(id=7)], game_tick=2300, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert first.stalled_ids == (7,)

    # Same order, still stalled, one cycle later (well within the renotify
    # cooldown): must NOT fire again.
    second = evaluate_orders(
        [_order(id=7)], game_tick=2400, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert second.stalled_ids == ()

    # Once the renotify window has elapsed, it is allowed to fire again.
    third = evaluate_orders(
        [_order(id=7)], game_tick=3600, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert third.stalled_ids == (7,)


def test_validated_false_is_blocked_not_stalled(tmp_path):
    store = _store(tmp_path)
    evaluate_orders(
        [_order(id=3, validated=False)], game_tick=1000, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    result = evaluate_orders(
        [_order(id=3, validated=False)], game_tick=2300, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    assert result.blocked_ids == (3,)
    assert result.stalled_ids == ()


def test_a_dispatched_order_is_not_a_candidate(tmp_path):
    store = _store(tmp_path)
    result = evaluate_orders(
        [_order(id=1, validated=True, active=True)], game_tick=5000, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    assert result.any_due is False


def test_a_finished_order_is_not_a_candidate(tmp_path):
    store = _store(tmp_path)
    result = evaluate_orders(
        [_order(id=1, finished_year=2)], game_tick=5000, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    assert result.any_due is False


def test_an_order_with_no_amount_left_is_not_a_candidate(tmp_path):
    store = _store(tmp_path)
    result = evaluate_orders(
        [_order(id=1, amount_left=0, amount_total=5)], game_tick=5000, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    assert result.any_due is False


def test_an_infinite_order_amount_total_zero_still_counts_as_having_work_left(tmp_path):
    store = _store(tmp_path)
    evaluate_orders(
        [_order(id=1, amount_left=0, amount_total=0)], game_tick=1000, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    result = evaluate_orders(
        [_order(id=1, amount_left=0, amount_total=0)], game_tick=2300, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    assert result.stalled_ids == (1,)


def test_an_order_that_stops_stalling_resets_its_bookkeeping(tmp_path):
    store = _store(tmp_path)
    evaluate_orders(
        [_order(id=7)], game_tick=1000, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    # The order starts running (active=True): no longer a candidate, history
    # should be forgotten.
    evaluate_orders(
        [_order(id=7, active=True)], game_tick=1500, threshold_ticks=1200,
        renotify_ticks=1200, cursor_store=store, dry_run=False,
    )
    # It stalls again later. If bookkeeping had NOT been reset, this would
    # already be past a threshold measured from the very first sighting
    # (tick 1000 -> 2000 is 1000 ticks, still under 1200) and could
    # incorrectly fire; with reset, it must not fire yet either way -- the
    # real proof is the next assertion, at a tick that would fire OFF THE
    # OLD first-seen but not off a freshly reset one.
    just_under_from_reset = evaluate_orders(
        [_order(id=7)], game_tick=2600, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    # 2600 - 1500 (the reset point) = 1100 < 1200: must not have fired yet.
    assert just_under_from_reset.stalled_ids == ()


def test_dry_run_reads_state_but_never_advances_it(tmp_path):
    store = _store(tmp_path)
    evaluate_orders(
        [_order(id=7)], game_tick=1000, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=True,
    )
    # Nothing persisted: a later REAL cycle at the same tick should behave
    # exactly as if this dry run never happened.
    assert store.get("__order_first_seen_7") == 0
    result = evaluate_orders(
        [_order(id=7)], game_tick=2300, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    # First real sighting is now tick 2300, so it has not held for 1200
    # ticks yet.
    assert result.stalled_ids == ()


def test_no_game_tick_returns_an_empty_result(tmp_path):
    store = _store(tmp_path)
    result = evaluate_orders(
        [_order(id=7)], game_tick=None, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert result.any_due is False


def test_an_order_missing_an_id_is_skipped_not_crashed_on(tmp_path):
    store = _store(tmp_path)
    result = evaluate_orders(
        [{"validated": True, "active": False, "amount_left": 1, "amount_total": 1, "finished_year": -1}],
        game_tick=5000, threshold_ticks=1200, renotify_ticks=1200,
        cursor_store=store, dry_run=False,
    )
    assert result.any_due is False
