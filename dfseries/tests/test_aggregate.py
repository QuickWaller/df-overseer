"""`aggregate.dwarf_day_reset_rate` (`dfseries/aggregate.py`): the handoff's
deliverable 4, reset events per dwarf-day across every `unit:*` subject.
Hand-written fixtures, small versions of the real file's shape: one citizen
who resets once, one who never resets, and one with only a single reading
(contributes zero dwarf-days, since a rate needs two)."""

from __future__ import annotations

import json

import pytest

from dfseries import aggregate, importer, metrics, store, trend


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


def _write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


@pytest.fixture()
def conn(tmp_path):
    with store.connect(tmp_path / "aggregate.series.sqlite3") as c:
        yield c


def test_dwarf_day_reset_rate_across_three_citizens(conn, tmp_path):
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 30_000, "unit": "ticks"},
            {"subject": "unit:193", "metric": "thirst_timer", "value": 500, "unit": "ticks"},
            {"subject": "unit:194", "metric": "thirst_timer", "value": 100, "unit": "ticks"},
        ]),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 200, "unit": "ticks"},  # reset
            {"subject": "unit:193", "metric": "thirst_timer", "value": 1500, "unit": "ticks"},
        ]),
        _record("t1", 0, 2000, "2026-09-19T08:02:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 1200, "unit": "ticks"},
            {"subject": "unit:193", "metric": "thirst_timer", "value": 2500, "unit": "ticks"},
        ]),
    ])
    importer.import_file(conn, p)

    result = aggregate.dwarf_day_reset_rate(conn, "thirst_timer")

    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.label == "drinking events per dwarf-day"
    assert result.subjects_observed == 3  # unit:192, unit:193, unit:194 all had >= 1 reading
    assert result.event_count == 1
    assert result.exact_tick_events == 1
    assert result.interval_bounded_events == 0
    assert result.anomaly_count == 0
    # unit:192: (2000-0)/1200, unit:193: (2000-0)/1200, unit:194: (0-0)/1200 = 0 (one reading only)
    assert result.dwarf_days_observed == pytest.approx(2000 / 1200 * 2)
    assert result.events_per_dwarf_day == pytest.approx(1 / (2000 / 1200 * 2))
    assert result.events_per_dwarf_day == pytest.approx(0.3)


def test_dwarf_day_reset_rate_with_no_subjects_is_none_not_a_crash(conn):
    result = aggregate.dwarf_day_reset_rate(conn, "thirst_timer")
    assert result.subjects_observed == 0
    assert result.dwarf_days_observed == 0
    assert result.event_count == 0
    assert result.events_per_dwarf_day is None


def test_dwarf_day_reset_rate_on_sleepiness_counts_interval_bounded_events(conn, tmp_path):
    p = tmp_path / "sleep.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "unit:192", "metric": "sleepiness_timer", "value": 49168, "unit": "ticks"},
        ]),
        _record("t1", 0, 1200, "2026-09-19T08:01:00Z", [
            {"subject": "unit:192", "metric": "sleepiness_timer", "value": 46048, "unit": "ticks"},  # decrease
        ]),
    ])
    importer.import_file(conn, p)

    result = aggregate.dwarf_day_reset_rate(conn, "sleepiness_timer")
    assert result.metric_kind == metrics.RESETTING_COUNTER
    assert result.rate_per_tick is None
    assert result.label == "sleepiness_timer reset events per dwarf-day"  # no special-cased label
    assert result.event_count == 1
    assert result.interval_bounded_events == 1
    assert result.exact_tick_events == 0


def test_dwarf_day_reset_rate_respects_the_window(conn, tmp_path):
    """A subject's reading outside [start, end] must not extend its
    observed span or contribute a reset from outside the window."""
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 30_000, "unit": "ticks"},
        ]),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 200, "unit": "ticks"},  # reset, outside window below
        ]),
        _record("t1", 0, 2000, "2026-09-19T08:02:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 1200, "unit": "ticks"},
        ]),
        _record("t1", 0, 3000, "2026-09-19T08:03:00Z", [
            {"subject": "unit:192", "metric": "thirst_timer", "value": 2200, "unit": "ticks"},
        ]),
    ])
    importer.import_file(conn, p)

    result = aggregate.dwarf_day_reset_rate(conn, "thirst_timer", start_abs_tick=1000, end_abs_tick=3000)
    assert result.event_count == 0  # the reset happened before abs_tick 1000
    assert result.dwarf_days_observed == pytest.approx((3000 - 1000) / 1200)
