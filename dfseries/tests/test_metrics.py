"""The metric-kind registry (`dfseries/metrics.py`). Handoff's named
requirement: level vs resetting_counter, with each counter's established
rate and evidence or "not established", and unknown metrics default to
level."""

from __future__ import annotations

from dfseries import metrics


def test_unknown_metric_defaults_to_level():
    mk = metrics.kind_of("some_metric_nobody_registered")
    assert mk.kind == metrics.LEVEL
    assert mk.rate_per_tick is None
    assert mk.evidence  # never blank -- always says why


def test_thirst_timer_is_an_established_resetting_counter():
    mk = metrics.kind_of("thirst_timer")
    assert mk.kind == metrics.RESETTING_COUNTER
    assert mk.rate_per_tick == 1.0
    assert "206" in mk.evidence and "207" in mk.evidence


def test_hunger_timer_is_established_by_analogy_not_by_a_real_reset():
    mk = metrics.kind_of("hunger_timer")
    assert mk.kind == metrics.RESETTING_COUNTER
    assert mk.rate_per_tick == 1.0
    assert "zero resets" in mk.evidence.lower() or "never been tested" in mk.evidence.lower()


def test_sleepiness_timer_rate_is_not_established():
    mk = metrics.kind_of("sleepiness_timer")
    assert mk.kind == metrics.RESETTING_COUNTER
    assert mk.rate_per_tick is None
    assert "not established" in mk.evidence.lower()


def test_a_level_metric_carries_no_rate():
    mk = metrics.kind_of("population")
    assert mk.kind == metrics.LEVEL
    assert mk.rate_per_tick is None
