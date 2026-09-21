"""conductor/triage.py: a quiet cycle wakes nobody; each wake reason picks
the right level and role(s); the Overseer wakes only when the queue holds
something for it; the Consultant wakes only on an open ask."""

from __future__ import annotations

from conductor.policy import FULL_SPEED, SLOWED, load_policy
from conductor.triage import CONSULTANT, OVERSEER, Signals, triage

POLICY = load_policy()  # the real, committed conductor/policy.yaml


def test_a_quiet_cycle_wakes_nobody_and_costs_nothing():
    result = triage(Signals(), POLICY)
    assert result.wakes == ()
    assert result.roles_to_wake == ()
    assert result.clock == FULL_SPEED


def test_migrant_wave_wakes_both_advisors_at_full_speed():
    result = triage(Signals(migrant_wave=True), POLICY)
    assert result.clock == FULL_SPEED
    assert result.roles_to_wake == ("architect", "quartermaster")
    wake = result.wake_for("architect")
    assert wake.reason == "migrant_wave"


def test_caravan_present_slows_and_wakes_only_the_quartermaster():
    result = triage(Signals(caravan_present=True), POLICY)
    assert result.clock == SLOWED
    assert result.roles_to_wake == ("quartermaster",)
    assert result.wake_for("architect") is None


def test_hostile_seen_unreachable_slows_the_clock_but_wakes_nobody():
    result = triage(Signals(hostile_seen_unreachable=True), POLICY)
    assert result.clock == SLOWED
    assert result.roles_to_wake == ()
    assert len(result.wakes) == 1
    assert result.wakes[0].roles == ()


def test_queue_holds_for_overseer_wakes_only_the_overseer_at_full_speed():
    result = triage(Signals(queue_holds_for_overseer=True), POLICY)
    assert result.roles_to_wake == (OVERSEER,)
    assert result.clock == FULL_SPEED


def test_open_ask_wakes_only_the_consultant():
    result = triage(Signals(open_ask_for_consultant=True), POLICY)
    assert result.roles_to_wake == (CONSULTANT,)


def test_routine_review_fires_once_the_interval_is_reached():
    just_under = triage(Signals(game_days_since_routine_review=6.9), POLICY)
    assert just_under.roles_to_wake == ()

    at_interval = triage(Signals(game_days_since_routine_review=7.0), POLICY)
    assert at_interval.roles_to_wake == ("architect", "quartermaster")


def test_roles_to_wake_is_ordered_advisors_then_consultant_then_overseer():
    """docs/AGENT-LOOP.md §4: "within a cycle the order is advisors, then
    Consultant, then Overseer." Fire all three groups in one cycle and check
    the ORDER of roles_to_wake, not just the membership."""
    result = triage(
        Signals(
            migrant_wave=True,  # wakes both advisors
            open_ask_for_consultant=True,  # wakes the consultant
            queue_holds_for_overseer=True,  # wakes the overseer
        ),
        POLICY,
    )
    assert result.roles_to_wake == ("architect", "quartermaster", CONSULTANT, OVERSEER)


def test_a_stuck_job_close_to_consequence_slows_the_clock():
    result = triage(
        Signals(stuck_job=True, stuck_job_ticks_to_consequence=100), POLICY, base_fps=100,
    )
    assert result.clock == SLOWED


def test_a_stuck_job_far_from_consequence_stays_full_speed():
    result = triage(
        Signals(stuck_job=True, stuck_job_ticks_to_consequence=10_000_000), POLICY, base_fps=100,
    )
    assert result.clock == FULL_SPEED


def test_a_computable_reason_with_no_priced_ticks_falls_back_to_its_table_entry():
    """vital_nearing_threshold's table entry is slowed; with no computed
    ticks-to-consequence this cycle, it should still fall back to that,
    never crash and never silently become full_speed."""
    result = triage(Signals(vital_nearing_threshold=True), POLICY)
    assert result.clock == SLOWED


def test_the_most_urgent_of_several_live_reasons_wins():
    result = triage(
        Signals(migrant_wave=True, caravan_present=True), POLICY,  # full_speed and slowed
    )
    assert result.clock == SLOWED
    assert set(result.roles_to_wake) == {"architect", "quartermaster"}


def test_wake_for_returns_none_for_an_unwoken_role():
    result = triage(Signals(caravan_present=True), POLICY)
    assert result.wake_for(OVERSEER) is None
