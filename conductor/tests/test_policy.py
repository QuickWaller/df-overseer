"""conductor/policy.py: the clock levels, the ticks-to-consequence rule both
ways, "the most urgent live reason wins", and the real, committed
conductor/policy.yaml loading cleanly."""

from __future__ import annotations

import textwrap

import pytest

from conductor import policy as policy_mod
from conductor.policy import (
    DEFAULT_POLICY_PATH, FULL_SPEED, PAUSED, SLOWED, Policy, PolicyError,
    WakeReasonPolicy, clock_for_reason, load_policy, most_urgent,
    ticks_to_consequence_clock, update_expected_thinking_seconds,
)


def _policy(**overrides) -> Policy:
    base = dict(
        base_fps=100,
        think_fps=10,
        closing_in_multiple=3,
        expected_thinking_seconds=60,
        routine_review_interval_game_days=7,
        stalled_order_threshold_ticks=1200,
        stalled_order_renotify_ticks=1200,
        wake_reasons={
            "routine_review": WakeReasonPolicy(
                reason="routine_review", clock=FULL_SPEED, wakes=("architect",),
            ),
            "stuck_job": WakeReasonPolicy(
                reason="stuck_job", clock=FULL_SPEED, wakes=("quartermaster",), computable=True,
            ),
            "vital_nearing_threshold": WakeReasonPolicy(
                reason="vital_nearing_threshold", clock=SLOWED, wakes=("quartermaster",),
                computable=True,
            ),
            "tripwire": WakeReasonPolicy(reason="tripwire", clock=PAUSED, wakes=("overseer",)),
        },
    )
    base.update(overrides)
    return Policy(**base)


# ---------------------------------------------------------------------------
# The real, committed conductor/policy.yaml
# ---------------------------------------------------------------------------


def test_the_real_policy_yaml_loads_cleanly():
    policy = load_policy(DEFAULT_POLICY_PATH)
    assert policy.base_fps == 100
    assert policy.think_fps == 10
    assert "tripwire" in policy.wake_reasons
    assert policy.reason("tripwire").clock == PAUSED
    assert policy.reason("tripwire").wakes == ("overseer",)
    assert policy.reason("routine_review").wakes == ("architect", "quartermaster")


def test_load_policy_refuses_a_bad_clock_level(tmp_path):
    bad = tmp_path / "policy.yaml"
    bad.write_text(textwrap.dedent("""\
        base_fps: 100
        think_fps: 10
        closing_in_multiple: 3
        expected_thinking_seconds: 60
        routine_review_interval_game_days: 7
        wake_reasons:
          tripwire:
            clock: "very paused"
            wakes: [overseer]
    """), encoding="utf-8")
    with pytest.raises(PolicyError, match="very paused"):
        load_policy(bad)


def test_load_policy_refuses_a_missing_required_key(tmp_path):
    bad = tmp_path / "policy.yaml"
    bad.write_text("base_fps: 100\n", encoding="utf-8")
    with pytest.raises(PolicyError, match="think_fps"):
        load_policy(bad)


def test_load_policy_refuses_a_missing_file(tmp_path):
    with pytest.raises(PolicyError, match="no such policy file"):
        load_policy(tmp_path / "does-not-exist.yaml")


def test_policy_reason_refuses_an_unknown_reason():
    policy = _policy()
    with pytest.raises(PolicyError, match="not a wake reason"):
        policy.reason("made_up_reason")


# ---------------------------------------------------------------------------
# ticks_to_consequence_clock: both directions
# ---------------------------------------------------------------------------


def test_ticks_to_consequence_close_in_slows():
    policy = _policy(expected_thinking_seconds=60, closing_in_multiple=3, base_fps=100)
    # threshold = 3 * 60 * 100 = 18000 ticks
    assert ticks_to_consequence_clock(1000, policy) == SLOWED
    assert ticks_to_consequence_clock(17999, policy) == SLOWED


def test_ticks_to_consequence_far_off_stays_full_speed():
    policy = _policy(expected_thinking_seconds=60, closing_in_multiple=3, base_fps=100)
    assert ticks_to_consequence_clock(18000, policy) == FULL_SPEED  # exactly at the threshold
    assert ticks_to_consequence_clock(100_000, policy) == FULL_SPEED


def test_ticks_to_consequence_none_is_full_speed_not_a_crash():
    policy = _policy()
    assert ticks_to_consequence_clock(None, policy) == FULL_SPEED


def test_ticks_to_consequence_negative_is_refused():
    policy = _policy()
    with pytest.raises(PolicyError):
        ticks_to_consequence_clock(-1, policy)


def test_ticks_to_consequence_honours_an_overridden_base_fps():
    """base_fps is a setting, not a constant (docs/AGENT-LOOP.md §2): a
    caller may already be at think_fps when computing this, and the rule is
    written in ticks at whatever fps currently applies."""
    policy = _policy(expected_thinking_seconds=60, closing_in_multiple=3, base_fps=100)
    # At fps=10: threshold = 3 * 60 * 10 = 1800, much lower than at fps=100.
    assert ticks_to_consequence_clock(1900, policy, base_fps=10) == FULL_SPEED
    assert ticks_to_consequence_clock(1700, policy, base_fps=10) == SLOWED


# ---------------------------------------------------------------------------
# clock_for_reason: computed rule vs fallback table
# ---------------------------------------------------------------------------


def test_clock_for_reason_uses_the_fallback_table_for_a_non_computable_reason():
    policy = _policy()
    # routine_review is not computable: always its table entry, regardless
    # of any ticks_to_consequence supplied.
    assert clock_for_reason("routine_review", policy, ticks_to_consequence=1) == FULL_SPEED


def test_clock_for_reason_uses_the_computed_rule_for_a_computable_reason_when_priced():
    policy = _policy(expected_thinking_seconds=60, closing_in_multiple=3, base_fps=100)
    assert clock_for_reason("stuck_job", policy, ticks_to_consequence=100) == SLOWED
    assert clock_for_reason("stuck_job", policy, ticks_to_consequence=100_000) == FULL_SPEED


def test_clock_for_reason_falls_back_to_the_table_when_a_computable_reason_cannot_be_priced():
    """§2: "The table is the fallback for wake reasons with no computable
    deadline." A computable reason with ticks_to_consequence=None (this
    cycle simply could not price it) still gets its table entry, not a
    crash and not always full_speed."""
    policy = _policy()
    assert (
        clock_for_reason("vital_nearing_threshold", policy, ticks_to_consequence=None) == SLOWED
    )


def test_clock_for_reason_refuses_an_unknown_reason():
    policy = _policy()
    with pytest.raises(PolicyError):
        clock_for_reason("no_such_reason", policy)


# ---------------------------------------------------------------------------
# most_urgent: "the most urgent live reason wins"
# ---------------------------------------------------------------------------


def test_most_urgent_of_an_empty_set_restores_full_speed():
    assert most_urgent(()) == FULL_SPEED


def test_most_urgent_picks_paused_over_slowed_and_full_speed():
    assert most_urgent([FULL_SPEED, SLOWED, PAUSED]) == PAUSED
    assert most_urgent([SLOWED, FULL_SPEED]) == SLOWED
    assert most_urgent([FULL_SPEED, FULL_SPEED]) == FULL_SPEED


def test_most_urgent_refuses_an_unknown_level():
    with pytest.raises(PolicyError):
        most_urgent(["not_a_real_level"])


# ---------------------------------------------------------------------------
# update_expected_thinking_seconds: a moving figure, not an overwrite
# ---------------------------------------------------------------------------


def test_update_expected_thinking_seconds_moves_toward_the_measurement():
    policy = _policy(expected_thinking_seconds=60)
    updated = update_expected_thinking_seconds(policy, 120)
    # EWMA: strictly between the old value and the new measurement, and
    # closer to nothing (still a moving figure) if the weight is < 1.
    assert 60 < updated.expected_thinking_seconds < 120
    weight = policy_mod.THINKING_TIME_EWMA_WEIGHT
    expected = (1 - weight) * 60 + weight * 120
    assert updated.expected_thinking_seconds == pytest.approx(expected)
    # Original policy object is untouched -- Policy is frozen.
    assert policy.expected_thinking_seconds == 60


def test_update_expected_thinking_seconds_refuses_a_negative_measurement():
    policy = _policy()
    with pytest.raises(PolicyError):
        update_expected_thinking_seconds(policy, -5)


def test_repeated_updates_converge_toward_a_new_steady_measurement():
    policy = _policy(expected_thinking_seconds=60)
    for _ in range(50):
        policy = update_expected_thinking_seconds(policy, 30)
    assert policy.expected_thinking_seconds == pytest.approx(30, abs=0.5)
