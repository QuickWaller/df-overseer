"""conductor/plan_watch.py, pure: the season cursor, the bootstrap, the review
and ruling wakes, and the shortfall watch (handoffs/2026-10-07-planner-p1b.md,
research/2026-10-07-planner-design.md 5). Every test feeds `evaluate` a
hand-built `plan.status` result and a tick, so nothing here touches a tool, a
file (except the store round trip) or a model."""

from __future__ import annotations

from types import SimpleNamespace

from conductor.plan_watch import (
    Backoff, PlanWatchState, PlanWatchStore, REASON_BOOTSTRAP, REASON_INPUT_SHORT, REASON_REVIEW,
    REASON_RULING, REASON_SHORTFALL, REASON_STALLED, SeasonEdge, advance_season, evaluate, last_refusal,
    season_index, shortfall_line,
)
from conductor.policy import PlanPolicy, ShortfallWatchPolicy

SEASON = 100800
BASE = 12000


def policy(*, shortfall=True, **over):
    sw = ShortfallWatchPolicy(
        enabled=shortfall, renotify_ticks=BASE, renotify_cap_ticks=SEASON, stall_after=3, owner_ceiling=2,
        serving_types={"zones": ("room_siting", "corridor")},
    )
    return PlanPolicy(enabled=True, season_ticks=SEASON, renotify_ticks=BASE, renotify_cap_ticks=SEASON,
                      shortfall=sw, **over)


def target(tid="bedrooms", *, on_hand=9.0, in_flight=0.0, want_units=22.0, state="open", owner="architect",
           serving=(), inputs=(), at_max=False, signal='zones."Bedroom".furnished'):
    position = on_hand + in_flight
    return {
        "id": tid, "signal": signal, "owner": owner, "state": state, "on_hand": on_hand, "in_flight": in_flight,
        "position": position, "want_units": want_units, "short_units": max(0.0, want_units - position),
        "below_want": position < want_units, "serving": [dict(s) for s in serving],
        "at_max_in_flight": at_max, "inputs": [dict(i) for i in inputs],
    }


def serving(*ids, state="pending"):
    return [{"proposal_id": i, "type": "room_siting", "role": "architect", "state": state} for i in ids]


def status(targets=(), *, version=3, season=1, bootstrap=False, owners=None, awaiting=(), reviewed=None):
    if bootstrap:
        return {"active": None, "bootstrap": True, "last_reviewed_tick": None, "plan_changes_awaiting": []}
    return {
        "active": {"id": f"plan-{version}", "version": version, "season_index": season, "tick": 5},
        "bootstrap": False, "last_reviewed_tick": reviewed, "last_pass_tick": reviewed,
        "plan_changes_awaiting": [{"proposal_id": p, "ruling_id": r} for p, r in awaiting],
        "targets": list(targets), "owners": owners or {}, "alive": 22,
    }


def run(st, tick, state, pol=None, edge=None, **kw):
    return evaluate(st, tick, pol or policy(), state, edge, **kw)


def by_reason(result, reason):
    return [w for w in result.wakes if w.reason == reason]


# ---------------------------------------------------------------------------
# The season cursor (F-3, F-11)
# ---------------------------------------------------------------------------


def test_season_index_is_the_tick_over_the_season_length():
    assert season_index(0, SEASON) == 0
    assert season_index(SEASON - 1, SEASON) == 0
    assert season_index(SEASON, SEASON) == 1
    assert season_index(3 * SEASON + 5, SEASON) == 3


def test_the_first_sighting_sets_the_cursor_and_is_not_a_change():
    state = PlanWatchState()
    edge = advance_season(state, SEASON + 10, SEASON)
    assert edge == SeasonEdge(1, first=True)
    assert (state.season_index, state.season_tick) == (1, SEASON + 10)


def test_the_cursor_fires_once_per_index_and_never_again_within_it():
    state = PlanWatchState()
    advance_season(state, 100, SEASON)
    assert advance_season(state, SEASON - 1, SEASON).changed is False
    crossing = advance_season(state, SEASON, SEASON)
    assert crossing.changed is True and crossing.index == 1
    for tick in (SEASON + 1, SEASON + 5000, 2 * SEASON - 1):
        assert advance_season(state, tick, SEASON).changed is False
    assert advance_season(state, 2 * SEASON, SEASON).changed is True


def test_a_season_skipped_while_the_conductor_was_off_is_one_change():
    state = PlanWatchState()
    advance_season(state, 10, SEASON)
    edge = advance_season(state, 5 * SEASON + 3, SEASON)
    assert edge.changed and edge.index == 5


def test_a_tick_that_goes_backwards_is_a_reload_that_resets_the_cursor_without_a_change():
    state = PlanWatchState()
    advance_season(state, 3 * SEASON + 9, SEASON)
    state.review_index, state.review_since = 3, 3 * SEASON
    edge = advance_season(state, SEASON + 4, SEASON)
    assert edge.reload is True and edge.changed is False and edge.index == 1
    assert state.season_index == 1 and state.review_index is None
    # And the cursor then runs forward normally from the reset point.
    assert advance_season(state, 2 * SEASON, SEASON).changed is True


def test_an_unknown_tick_leaves_the_cursor_alone():
    state = PlanWatchState(season_index=2, season_tick=7)
    assert advance_season(state, None, SEASON) is None
    assert (state.season_index, state.season_tick) == (2, 7)


# ---------------------------------------------------------------------------
# Quiet by default
# ---------------------------------------------------------------------------


def test_a_disabled_plan_policy_wakes_nobody():
    off = PlanPolicy(enabled=False)
    assert run(status(bootstrap=True), 10, PlanWatchState(), off).wakes == []


def test_a_failed_read_or_an_unknown_tick_wakes_nobody():
    state = PlanWatchState()
    assert run(None, 10, state).wakes == []
    assert run(status(bootstrap=True), None, state).wakes == []
    assert state.bootstrap.wakes == 0  # nothing was counted


# ---------------------------------------------------------------------------
# Bootstrap (F-19)
# ---------------------------------------------------------------------------


def test_the_bootstrap_wakes_the_planner_then_backs_off_doubling():
    state = PlanWatchState()
    st = status(bootstrap=True)
    first = run(st, 1000, state)
    assert [w.reason for w in first.wakes] == [REASON_BOOTSTRAP] and first.wakes[0].role == "planner"
    # Not again until the backoff has run: BASE after the first wake.
    assert run(st, 1000 + BASE - 1, state).wakes == []
    second = run(st, 1000 + BASE, state)
    assert [w.reason for w in second.wakes] == [REASON_BOOTSTRAP]
    # Doubled: 2 * BASE after the second.
    assert run(st, 1000 + BASE + 2 * BASE - 1, state).wakes == []
    assert len(run(st, 1000 + BASE + 2 * BASE, state).wakes) == 1


def test_three_failed_bootstrap_wakes_escalate_to_the_operator_with_the_last_refusal():
    state = PlanWatchState()
    st = status(bootstrap=True)
    tick = 0
    for attempt in range(3):
        assert len(run(st, tick, state).wakes) == 1
        state.last_refusal = f"plan.write: refused attempt {attempt + 1}"
        tick += 4 * BASE  # past every backoff step
    out = run(st, tick, state)
    assert out.wakes == []
    assert len(out.alerts) == 1
    assert "3 times" in out.alerts[0] and "refused attempt 3" in out.alerts[0]
    assert state.bootstrap_escalated is True
    # Once escalated it neither wakes nor alerts again.
    again = run(st, tick + 10 * BASE, state)
    assert again.wakes == [] and again.alerts == []


def test_a_plan_appearing_ends_the_bootstrap_and_rearms_it():
    state = PlanWatchState()
    run(status(bootstrap=True), 0, state)
    state.last_refusal = "plan.write: x"
    run(status([], version=1), 10, state)
    assert state.bootstrap.wakes == 0 and state.bootstrap_escalated is False and state.last_refusal is None


# ---------------------------------------------------------------------------
# The season review
# ---------------------------------------------------------------------------


def test_a_changed_season_with_an_earlier_active_version_wakes_the_planner_once_owed():
    state = PlanWatchState(season_index=1, season_tick=1)
    edge = advance_season(state, SEASON + 5, SEASON)  # season 1 -> ... index 1 stays
    # Cross into season 2 with a plan filed in season 1.
    edge = advance_season(state, 2 * SEASON, SEASON)
    out = run(status([], season=1), 2 * SEASON, state, edge=edge)
    assert [w.reason for w in out.wakes] == [REASON_REVIEW]
    assert out.wakes[0].role == "planner"
    # Edge triggered: the next cycle (same index, no change) does not raise a second one inside the backoff.
    assert run(status([], season=1), 2 * SEASON + 100, state, edge=SeasonEdge(2)).wakes == []


def test_the_review_is_not_owed_when_the_active_version_is_from_this_or_a_later_season():
    state = PlanWatchState()
    edge = SeasonEdge(2, changed=True)
    assert run(status([], season=2), 2 * SEASON, state, edge=edge).wakes == []
    # A reload leaves an active version from a later season: counts as elapsed.
    assert run(status([], season=4), 2 * SEASON, state, edge=edge).wakes == []


def test_the_first_sighting_with_a_stale_plan_owes_a_review():
    state = PlanWatchState()
    out = run(status([], season=0), 3 * SEASON, state, edge=SeasonEdge(3, first=True))
    assert [w.reason for w in out.wakes] == [REASON_REVIEW]


def test_a_new_version_or_a_pass_clears_the_owed_review():
    state = PlanWatchState()
    run(status([], season=1), 2 * SEASON, state, edge=SeasonEdge(2, changed=True))
    assert state.review_index == 2
    # The Planner passed: queue.pass recorded the review tick after the review was raised.
    out = run(status([], season=1, reviewed=2 * SEASON + 50), 2 * SEASON + BASE, state, edge=SeasonEdge(2))
    assert out.wakes == [] and state.review_index is None

    state = PlanWatchState()
    run(status([], season=1), 2 * SEASON, state, edge=SeasonEdge(2, changed=True))
    out = run(status([], version=4, season=2), 2 * SEASON + BASE, state, edge=SeasonEdge(2))
    assert out.wakes == [] and state.review_index is None


def test_an_unanswered_review_retries_on_backoff_a_bounded_number_of_times():
    state = PlanWatchState()
    pol = policy(review_max_wakes=2)
    edge = SeasonEdge(2, changed=True)
    assert len(run(status([], season=1), 0, state, pol, edge=edge).wakes) == 1
    assert run(status([], season=1), BASE - 1, state, pol, edge=SeasonEdge(2)).wakes == []
    assert len(run(status([], season=1), BASE, state, pol, edge=SeasonEdge(2)).wakes) == 1
    assert run(status([], season=1), 20 * BASE, state, pol, edge=SeasonEdge(2)).wakes == []


# ---------------------------------------------------------------------------
# An accepted plan_change nobody has cited
# ---------------------------------------------------------------------------


def test_an_accepted_plan_change_wakes_the_planner_with_the_ruling_id_and_backs_off():
    state = PlanWatchState()
    st = status([], awaiting=[("proposal-0042", "ruling-0031")])
    out = run(st, 100, state)
    assert [w.reason for w in out.wakes] == [REASON_RULING]
    assert 'ruling_id "ruling-0031"' in out.wakes[0].detail and "proposal-0042" in out.wakes[0].detail
    assert run(st, 100 + BASE - 1, state).wakes == []
    assert len(run(st, 100 + BASE, state).wakes) == 1


def test_an_accepted_plan_change_is_left_alone_after_its_wakes_and_forgotten_once_cited():
    state = PlanWatchState()
    pol = policy(awaiting_max_wakes=2)
    st = status([], awaiting=[("proposal-1", "ruling-1")])
    run(st, 0, state, pol)
    run(st, BASE, state, pol)
    assert run(st, 10 * BASE, state, pol).wakes == []
    run(status([]), 11 * BASE, state, pol)  # a version cited it: no longer awaiting
    assert state.awaiting == {}


# ---------------------------------------------------------------------------
# The shortfall watch ships OFF
# ---------------------------------------------------------------------------


def test_the_shortfall_watch_is_off_by_default_and_wakes_no_owner():
    assert PlanPolicy().shortfall.enabled is False
    state = PlanWatchState()
    out = run(status([target()]), 100, state, policy(shortfall=False))
    assert by_reason(out, REASON_SHORTFALL) == [] and by_reason(out, REASON_INPUT_SHORT) == []
    assert state.targets == {}


def test_the_committed_policy_ships_the_watch_off_and_the_planner_off():
    from conductor.policy import load_policy
    plan = load_policy().plan
    assert plan.shortfall.enabled is False


# ---------------------------------------------------------------------------
# The shortfall watch, on
# ---------------------------------------------------------------------------


def test_an_open_target_wakes_its_owner_with_the_fixed_line():
    state = PlanWatchState()
    t = target(in_flight=2.0, serving=serving("proposal-0007", "proposal-0008"), inputs=[
        {"item": "bed", "needed": 2.0, "available": 0.0, "owner": "quartermaster", "short": 2.0},
    ])
    out = run(status([t], owners={"architect": {"in_flight": 1, "ceiling": 2}}), 500, state)
    w = by_reason(out, REASON_SHORTFALL)[0]
    assert w.role == "architect" and w.key == "bedrooms"
    assert w.detail.startswith("Plan v3 target bedrooms: 9 on hand of 22 wanted")
    assert "11 short" in w.detail and "2 in flight (proposal-0007, proposal-0008)" in w.detail
    assert "1 of 2 plan slots in use" in w.detail
    assert "Derived input: bed 0 available, 2 needed (quartermaster notified)." in w.detail
    assert w.detail.endswith('File a proposal with serves: ["bedrooms"], or pass with a reason.')


def test_a_quiet_target_wakes_nobody_and_an_open_one_closes_only_at_want():
    state = PlanWatchState()
    # In the band between reorder and want: quiet, never opened.
    assert run(status([target(state="quiet", on_hand=20.0)]), 0, state).wakes == []
    # Opens below the reorder level.
    assert len(by_reason(run(status([target(on_hand=5.0)]), 100, state), REASON_SHORTFALL)) == 1
    assert state.targets["bedrooms"].open is True
    # Back into the band: the plan.status state reads quiet, but the want is not met, so it stays open.
    run(status([target(state="quiet", on_hand=20.0)]), 200, state)
    assert state.targets["bedrooms"].open is True
    # At want: closes.
    run(status([target(state="quiet", on_hand=22.0)]), 300, state)
    assert state.targets["bedrooms"].open is False


def test_a_shortfall_one_unit_short_is_never_rounded_away():
    state = PlanWatchState()
    out = run(status([target(on_hand=21.0, want_units=22.0)]), 0, state)
    assert len(by_reason(out, REASON_SHORTFALL)) == 1  # open per plan.status; the line says 1 short
    assert "1 short" in by_reason(out, REASON_SHORTFALL)[0].detail


def test_renotify_backs_off_doubling_while_the_position_never_moves():
    state = PlanWatchState()
    st = status([target()])
    assert len(run(st, 0, state).wakes) == 1  # opening wake
    assert run(st, BASE - 1, state).wakes == []
    assert len(run(st, BASE, state).wakes) == 1  # renotify 1 after BASE
    assert run(st, BASE + 2 * BASE - 1, state).wakes == []
    assert len(run(st, BASE + 2 * BASE, state).wakes) == 1  # renotify 2 after 2 * BASE


def test_the_backoff_is_capped_at_one_season():
    from conductor.plan_watch import _note_wake
    b = Backoff()
    for _ in range(12):
        _note_wake(b, 0, BASE, SEASON)
    assert b.next_tick == SEASON


def test_a_target_whose_position_never_moves_wakes_its_owner_at_most_three_times_per_version():
    state = PlanWatchState()
    st = status([target()])
    owner_wakes = planner_wakes = 0
    for tick in range(0, 30 * BASE, 1000):
        out = run(st, tick, state)
        owner_wakes += len(by_reason(out, REASON_SHORTFALL))
        planner_wakes += len(by_reason(out, REASON_STALLED))
    assert owner_wakes == 3
    assert planner_wakes == 1  # once per target per version
    assert state.targets["bedrooms"].backoff.stalled is True


def test_stalled_wakes_the_planner_with_a_line_naming_the_target_and_the_choices():
    state = PlanWatchState()
    st = status([target()])
    stalled = None
    for tick in range(0, 30 * BASE, 1000):
        for w in by_reason(run(st, tick, state), REASON_STALLED):
            stalled = w
    assert stalled is not None and stalled.role == "planner"
    assert "bedrooms is stalled" in stalled.detail and "plan_change" in stalled.detail


def test_a_new_plan_version_rearms_a_stalled_target():
    state = PlanWatchState()
    for tick in range(0, 30 * BASE, 1000):
        run(status([target()], version=3), tick, state)
    assert state.targets["bedrooms"].backoff.stalled
    out = run(status([target()], version=4), 31 * BASE, state)
    assert len(by_reason(out, REASON_SHORTFALL)) == 1
    assert state.targets["bedrooms"].backoff.stalled is False


def test_a_target_whose_position_moves_restarts_its_backoff_instead_of_stalling():
    state = PlanWatchState()
    on_hand = 9.0
    owner_wakes = 0
    for tick in range(0, 30 * BASE, 1000):
        # The fort makes progress every few cycles, but never reaches want.
        if tick % (BASE) == 0:
            on_hand += 1.0
        owner_wakes += len(by_reason(run(status([target(on_hand=on_hand)]), tick, state), REASON_SHORTFALL))
    assert owner_wakes > 3
    assert state.targets["bedrooms"].backoff.stalled is False


def test_a_target_holding_its_max_in_flight_wakes_nobody():
    state = PlanWatchState()
    out = run(status([target(at_max=True, in_flight=2.0, serving=serving("p1", "p2"))]), 0, state)
    assert by_reason(out, REASON_SHORTFALL) == []
    assert any("max in flight" in n for n in out.notes)


def test_the_per_owner_ceiling_suppresses_later_targets_in_plan_order():
    state = PlanWatchState()
    targets = [target(f"t{i}", signal=f'zones."Z{i}".count') for i in range(3)]
    out = run(status(targets, owners={}), 0, state)
    woken = [w.key for w in by_reason(out, REASON_SHORTFALL)]
    assert woken == ["t0", "t1"]  # ceiling 2, plan order
    assert any("plan budget" in n for n in out.notes)
    # An owner already using its budget is not woken at all.
    state = PlanWatchState()
    out = run(status(targets, owners={"architect": {"in_flight": 2, "ceiling": 2}}), 0, state)
    assert by_reason(out, REASON_SHORTFALL) == []


def test_the_ceiling_is_per_owner():
    state = PlanWatchState()
    targets = [target("a1"), target("a2"), target("a3"), target("q1", owner="quartermaster", signal='stocks."BED".available_units')]
    woken = [(w.role, w.key) for w in by_reason(run(status(targets), 0, state), REASON_SHORTFALL)]
    assert woken == [("architect", "a1"), ("architect", "a2"), ("quartermaster", "q1")]


def test_an_operator_hold_suppresses_every_owner_wake_without_losing_state():
    state = PlanWatchState()
    out = run(status([target()]), 0, state, held=True)
    assert out.wakes == [] and state.targets == {}
    # Released: it wakes as an ordinary opening.
    assert len(by_reason(run(status([target()]), 10, state), REASON_SHORTFALL)) == 1


def test_a_frozen_owner_group_is_not_woken():
    state = PlanWatchState()
    out = run(status([target()]), 0, state, frozen_types=["room_siting", "corridor"])
    assert by_reason(out, REASON_SHORTFALL) == []
    # Only part of the family frozen: the owner can still file the other type.
    state = PlanWatchState()
    assert len(by_reason(run(status([target()]), 0, state, frozen_types=["room_siting"]), REASON_SHORTFALL)) == 1


def test_a_rejected_serving_proposal_suppresses_renotify_until_the_next_version_and_the_backoff_step():
    state = PlanWatchState()
    # Cycle 1: opens, wakes; the owner files a proposal and the next cycle sees it in flight.
    run(status([target()]), 0, state)
    run(status([target(in_flight=2.0, serving=serving("proposal-9"))]), 1000, state)
    # The Overseer rejects it: it vanishes from serving and the position falls.
    out = run(status([target()]), 2000, state)
    assert by_reason(out, REASON_SHORTFALL) == []
    assert any("renotify suppressed" in n for n in out.notes)
    # Well past the backoff step, same version: still suppressed.
    assert by_reason(run(status([target()]), 10 * BASE, state), REASON_SHORTFALL) == []
    # A new plan version re-arms it (the backoff step is long past).
    assert len(by_reason(run(status([target()], version=4), 11 * BASE, state), REASON_SHORTFALL)) == 1


def test_a_new_version_before_the_backoff_step_still_waits_for_the_step():
    state = PlanWatchState()
    run(status([target()]), 0, state)
    run(status([target(in_flight=2.0, serving=serving("p9"))]), 100, state)
    run(status([target()]), 200, state)  # rejected; suppressed until 200 + BASE
    out = run(status([target()], version=4), 300, state)
    assert by_reason(out, REASON_SHORTFALL) == []  # the later of (new version, backoff step)
    assert len(by_reason(run(status([target()], version=4), 200 + BASE, state), REASON_SHORTFALL)) == 1


def test_a_finished_serving_proposal_is_progress_not_a_rejection():
    state = PlanWatchState()
    run(status([target()]), 0, state)
    run(status([target(in_flight=2.0, serving=serving("p1"))]), 100, state)
    # It completed: on hand rose, in flight fell, the position did not drop.
    out = run(status([target(on_hand=11.0)]), 200, state)
    assert not any("suppressed" in n for n in out.notes)


def test_unresolved_and_inert_targets_are_never_a_shortfall():
    state = PlanWatchState()
    for st_name in ("unresolved", "inert"):
        t = {"id": "x", "signal": "s", "owner": "architect", "state": st_name, "serving": []}
        out = run(status([t]), 0, state)
        assert out.wakes == []


# ---------------------------------------------------------------------------
# Derived inputs
# ---------------------------------------------------------------------------

BED_SHORT = {"item": "bed", "needed": 2.0, "available": 0.0, "owner": "quartermaster", "short": 2.0}


def test_a_short_derived_input_wakes_the_input_owner_once_per_edge():
    state = PlanWatchState()
    t = target(in_flight=2.0, serving=serving("p1", "p2"), inputs=[BED_SHORT], at_max=True)
    out = run(status([t]), 0, state)
    wakes = by_reason(out, REASON_INPUT_SHORT)
    assert len(wakes) == 1 and wakes[0].role == "quartermaster" and wakes[0].key == "bedrooms:bed"
    assert "bed" in wakes[0].detail and '"bedrooms"' in wakes[0].detail
    # Edge triggered: the very next cycle is quiet.
    assert by_reason(run(status([t]), 100, state), REASON_INPUT_SHORT) == []


def test_an_input_wake_does_not_depend_on_the_target_being_open():
    """In-flight rooms can bring a target to its want, closing it, while their
    beds are still missing: the input line must still go out."""
    state = PlanWatchState()
    closed = target(on_hand=20.0, in_flight=2.0, want_units=22.0, state="quiet", serving=serving("p1", "p2"), inputs=[BED_SHORT])
    out = run(status([closed]), 0, state)
    assert [w.reason for w in out.wakes] == [REASON_INPUT_SHORT]


def test_an_input_renotifies_on_backoff_stops_after_three_and_rearms_when_no_longer_short():
    state = PlanWatchState()
    t = target(on_hand=20.0, in_flight=2.0, state="quiet", serving=serving("p1"), inputs=[BED_SHORT])
    count = 0
    for tick in range(0, 30 * BASE, 1000):
        count += len(by_reason(run(status([t]), tick, state), REASON_INPUT_SHORT))
    assert count == 3
    ok = dict(BED_SHORT, short=0.0, available=2.0)
    run(status([dict(t, inputs=[ok])]), 40 * BASE, state)
    assert state.inputs == {}
    assert len(by_reason(run(status([t]), 41 * BASE, state), REASON_INPUT_SHORT)) == 1


def test_an_unreadable_input_is_not_a_shortage():
    state = PlanWatchState()
    unknown = dict(BED_SHORT, available=None, short=None)
    t = target(on_hand=20.0, in_flight=2.0, state="quiet", serving=serving("p1"), inputs=[unknown])
    assert run(status([t]), 0, state).wakes == []


# ---------------------------------------------------------------------------
# Reload safety, lines and the last refusal
# ---------------------------------------------------------------------------


def test_a_reload_that_puts_the_next_wake_far_in_the_future_rearms_it():
    state = PlanWatchState()
    st = status([target()])
    run(st, 5 * SEASON, state)  # next_tick = 5 * SEASON + BASE
    # The save was reloaded to a much earlier tick.
    out = run(st, 1000, state)
    assert len(by_reason(out, REASON_SHORTFALL)) == 1


def test_the_shortfall_line_is_bounded_and_names_the_serves_id():
    line = shortfall_line(7, target("x" * 50, serving=serving(*[f"proposal-{i:04d}" for i in range(40)])), 2, 0)
    assert len(line) <= 600 and line.startswith("Plan v7 target ")


def test_last_refusal_prefers_the_last_failed_call_then_the_error_then_the_final_answer():
    run_result = SimpleNamespace(
        transcript={"rounds": [{"calls": [
            {"name": "plan.read", "result": "{}", "error": False},
            {"name": "plan.write", "result": "plan.write: refused: stale base", "error": True},
            {"name": "plan.write", "result": '{"filed": false, "flags": []}', "error": False},
        ]}]},
        error="boom", final_answer="gave up",
    )
    assert "filed" in last_refusal(run_result)
    only_error = SimpleNamespace(transcript=None, error="timed out", final_answer="x")
    assert last_refusal(only_error) == "timed out"
    only_answer = SimpleNamespace(transcript=None, error=None, final_answer="I could not")
    assert last_refusal(only_answer) == "I could not"
    assert last_refusal(SimpleNamespace(transcript=None, error=None, final_answer=None)) is None
    assert last_refusal(object()) is None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def test_the_state_round_trips_through_its_file(tmp_path):
    state = PlanWatchState()
    run(status([target(in_flight=2.0, serving=serving("p1"), inputs=[BED_SHORT])]), 500, state)
    advance_season(state, 12345, SEASON)
    state.last_refusal = "plan.write: no"
    store = PlanWatchStore(tmp_path / "sub" / "plan_watch.json")
    store.save(state)
    loaded = store.load()
    assert loaded == state


def test_a_missing_file_is_a_fresh_state_and_a_corrupt_one_is_an_error(tmp_path):
    store = PlanWatchStore(tmp_path / "plan_watch.json")
    assert store.load() == PlanWatchState()
    (tmp_path / "plan_watch.json").write_text("[1]", encoding="utf-8")
    try:
        store.load()
    except ValueError:
        pass
    else:
        raise AssertionError("a non-object state file must be an error, not a silent reset")
