"""`trend.resets()` and `trend.rate()`'s refusal to straddle a reset, per
`handoffs/2026-09-19-dfseries-resets.md`. Fixtures are hand-written, small
versions of the dynamics measured against the real file
(`tl-20260918T213057Z-688464.jsonl`, never committed here): a citizen who
drinks mid-run (thirst_timer, established rate), a citizen who never resets
(hunger_timer, same established rate but nothing to detect), and a
sleep-drain shape (sleepiness_timer, rate not established).
"""

from __future__ import annotations

import json

import pytest

from dfseries import importer, metrics, store, trend


def _record(timeline_id, timeline_start_abs_tick, abs_tick, wall_utc, metrics_list):
    return {
        "v": 1,
        "timeline_id": timeline_id,
        "timeline_start_abs_tick": timeline_start_abs_tick,
        "abs_tick": abs_tick,
        "cur_year": 0,
        "cur_year_tick": abs_tick,
        "wall_utc": wall_utc,
        "sampler_version": "test",
        "metrics": metrics_list,
    }


def _metric(subject, metric, value, unit="ticks"):
    return [{"subject": subject, "metric": metric, "value": value, "unit": unit}]


def _write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


@pytest.fixture()
def conn(tmp_path):
    with store.connect(tmp_path / "resets.series.sqlite3") as c:
        yield c


# ---- thirst_timer: established rate, a real reset ------------------------------


def test_resets_dates_a_drink_to_the_exact_tick(conn, tmp_path):
    """Mirrors the real run's unit:192: 33722 at abs_tick 12373406, 1085 at
    abs_tick 12374606 -- reset dates to 12374606 - 1085 = 12373521."""
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 12373406, "2026-09-19T08:00:00Z", _metric("unit:192", "thirst_timer", 33722)),
        _record("t1", 0, 12374606, "2026-09-19T08:01:00Z", _metric("unit:192", "thirst_timer", 1085)),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "unit:192", "thirst_timer")
    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.rate_per_tick == 1.0
    assert len(result.events) == 1
    event = result.events[0]
    assert event.kind == trend.EXACT_TICK
    assert event.abs_tick == 12373521
    assert event.window_start_abs_tick == 12373406
    assert event.window_end_abs_tick == 12374606
    assert result.anomalies == []


def test_resets_reports_none_for_a_citizen_who_never_reset(conn, tmp_path):
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 100_000, "2026-09-19T08:00:00Z", _metric("unit:193", "thirst_timer", 20_000)),
        _record("t1", 0, 106_303, "2026-09-19T08:01:00Z", _metric("unit:193", "thirst_timer", 26_303)),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "unit:193", "thirst_timer")
    assert result.events == []
    assert result.anomalies == []


def test_resets_reports_a_rise_above_the_established_rate_as_an_anomaly_not_an_event(conn, tmp_path):
    """v1 > v0 + rate*(t1-t0) is impossible for an established 1/tick
    counter -- must never be absorbed into events."""
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", _metric("unit:192", "thirst_timer", 0)),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", _metric("unit:192", "thirst_timer", 5000)),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "unit:192", "thirst_timer")
    assert result.events == []
    assert len(result.anomalies) == 1
    assert result.anomalies[0].from_value == 0
    assert result.anomalies[0].to_value == 5000


# ---- hunger_timer: established rate, but nothing to detect in this window ------


def test_hunger_shows_no_resets_when_nobody_ate(conn, tmp_path):
    p = tmp_path / "hunger.jsonl"
    _write(p, [
        _record("t1", 0, 12368606, "2026-09-19T08:00:00Z", _metric("unit:193", "hunger_timer", 10_000)),
        _record("t1", 0, 12369806, "2026-09-19T08:01:00Z", _metric("unit:193", "hunger_timer", 11_200)),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "unit:193", "hunger_timer")
    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.rate_per_tick == 1.0
    assert result.events == []


# ---- sleepiness_timer: rate not established, only interval-bounded detection ---


def test_sleepiness_decrease_is_interval_bounded_not_exact_tick(conn, tmp_path):
    """Hand-written from the real shape: unit:192 fell 49168 -> 46048 over a
    1200-tick gap. Not dated to a tick -- the rate is not established."""
    p = tmp_path / "sleep.jsonl"
    _write(p, [
        _record("t1", 0, 12372206, "2026-09-19T08:00:00Z", _metric("unit:192", "sleepiness_timer", 49168)),
        _record("t1", 0, 12373406, "2026-09-19T08:01:00Z", _metric("unit:192", "sleepiness_timer", 46048)),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "unit:192", "sleepiness_timer")
    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.rate_per_tick is None
    assert len(result.events) == 1
    event = result.events[0]
    assert event.kind == trend.INTERVAL_BOUNDED
    assert event.abs_tick is None
    assert event.window_start_abs_tick == 12372206
    assert event.window_end_abs_tick == 12373406
    assert result.anomalies == []  # no established rate means nothing is "impossible"


def test_sleepiness_rise_is_neither_event_nor_anomaly(conn, tmp_path):
    """A rise, even a slow one, says nothing either way without a known
    rate -- it must not be reported as either a reset or an anomaly."""
    p = tmp_path / "sleep.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", _metric("unit:192", "sleepiness_timer", 448)),
        _record("t1", 0, 1200, "2026-09-19T08:01:00Z", _metric("unit:192", "sleepiness_timer", 1468)),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "unit:192", "sleepiness_timer")
    assert result.events == []
    assert result.anomalies == []


# ---- resets() on a level metric ------------------------------------------------


def test_resets_on_a_level_metric_is_always_empty(conn, tmp_path):
    p = tmp_path / "pop.jsonl"
    _write(p, [
        _record("t1", 0, 1000, "2026-09-19T08:00:00Z", _metric("fort", "population", 14, unit="citizens")),
        _record("t1", 0, 2000, "2026-09-19T08:01:00Z", _metric("fort", "population", 8, unit="citizens")),
    ])
    importer.import_file(conn, p)

    result = trend.resets(conn, "fort", "population")
    assert result.metric_kind == metrics.LEVEL
    assert result.events == []
    assert result.anomalies == []


# ---- rate() refuses to straddle a reset ----------------------------------------


def test_rate_refuses_the_endpoint_slope_across_a_reset(conn, tmp_path):
    """The bug this handoff fixes: unit:192 drank mid-run. The old endpoint
    rate gave -2.133056/tick over the full window; the new rate() must
    never return that number for a resetting counter."""
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 12368606, "2026-09-19T08:00:00Z", _metric("unit:192", "thirst_timer", 28_922)),
        _record("t1", 0, 12373406, "2026-09-19T08:01:00Z", _metric("unit:192", "thirst_timer", 33_722)),
        _record("t1", 0, 12374606, "2026-09-19T08:02:00Z", _metric("unit:192", "thirst_timer", 1_085)),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "unit:192", "thirst_timer")
    assert result.metric_kind == metrics.RESETTING_COUNTER
    # The straddling endpoint slope would be (1085 - 28922) / (12374606 - 12368606) =~ -4.64/tick.
    # That number must never come out of rate() for a resetting counter.
    straddling_endpoint = (1_085 - 28_922) / (12_374_606 - 12_368_606)
    if result.value is not None:
        assert result.value != pytest.approx(straddling_endpoint)
    # Only one reading remains after the reset (12374606 itself) -- too few
    # for a between-reset slope, so this must be UNAVAILABLE, naming the reset.
    assert result.status == trend.UNAVAILABLE
    assert "12373521" in result.reason
    assert "resets()" in result.reason


def test_rate_returns_the_between_reset_slope_when_enough_data_follows(conn, tmp_path):
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", _metric("unit:192", "thirst_timer", 30_000)),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", _metric("unit:192", "thirst_timer", 200)),
        _record("t1", 0, 2000, "2026-09-19T08:02:00Z", _metric("unit:192", "thirst_timer", 1200)),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "unit:192", "thirst_timer")
    assert result.status == trend.MEASURED
    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.segment == "between_reset"
    # reset dated to 1000 - 200 = 800; between-reset slope uses 800 and after
    # only the readings from abs_tick 800 onward -- here that is just the
    # abs_tick=1000 (200) and abs_tick=2000 (1200) readings.
    assert result.used_start_abs_tick == 1000
    assert result.value == pytest.approx((1200 - 200) / (2000 - 1000))
    assert "reset" in result.reason.lower()


def test_rate_with_no_reset_in_window_returns_the_endpoint_slope_labelled(conn, tmp_path):
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 100_000, "2026-09-19T08:00:00Z", _metric("unit:193", "thirst_timer", 20_000)),
        _record("t1", 0, 106_303, "2026-09-19T08:01:00Z", _metric("unit:193", "thirst_timer", 26_303)),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "unit:193", "thirst_timer")
    assert result.status == trend.MEASURED
    assert result.segment == "endpoint"
    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.value == pytest.approx(1.0)


def test_rate_on_level_metric_is_unchanged_and_labelled_endpoint(conn, tmp_path):
    p = tmp_path / "pop.jsonl"
    _write(p, [
        _record("t1", 0, 1000, "2026-09-19T08:00:00Z", _metric("fort", "population", 14, unit="citizens")),
        _record("t1", 0, 2000, "2026-09-19T08:01:00Z", _metric("fort", "population", 15, unit="citizens")),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "fort", "population")
    assert result.status == trend.MEASURED
    assert result.metric_kind == metrics.LEVEL
    assert result.segment == "endpoint"
    assert result.value == pytest.approx(0.001)


def test_hunger_reset_to_zero_verified_by_a_real_meal():
    """Hunger was held interval-bounded until a real meal showed reset-to-zero
    (orchestrator, 2026-09-19). The first real meals confirmed it: unit:344
    went 45629 -> 442, then rose exactly +1200 per 1200-tick sample. Both
    counters with evidence of resetting to zero now date resets exactly;
    sleepiness, which drains instead, does not."""
    from dfseries.metrics import kind_of
    assert kind_of("hunger_timer").rate_per_tick == 1.0
    assert kind_of("hunger_timer").reset_to_zero_verified is True
    assert kind_of("thirst_timer").reset_to_zero_verified is True
    assert kind_of("sleepiness_timer").reset_to_zero_verified is False
