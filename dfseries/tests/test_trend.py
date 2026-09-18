"""The trend layer (`dfseries/trend.py`): series, latest, rate, and rows
shaped for `production/cover.py`. Handoff's named tests: the default rate
does not straddle a rollback, nulls are skipped and counted (never treated
as zero), and a citizen who did not drink gives a thirst rate of exactly 1
per tick.
"""

from __future__ import annotations

import json

import pytest

from dfseries import importer, store, trend
from production import cover as production_cover

A_START = 213_622
A_END = 235_668
B_START = 213_622


def _record(timeline_id, timeline_start_abs_tick, abs_tick, wall_utc, metrics):
    return {
        "v": 1,
        "timeline_id": timeline_id,
        "timeline_start_abs_tick": timeline_start_abs_tick,
        "abs_tick": abs_tick,
        "cur_year": 0,
        "cur_year_tick": abs_tick,
        "wall_utc": wall_utc,
        "sampler_version": "test",
        "metrics": metrics,
    }


def _thirst(value, error=None):
    m = {"subject": "unit:192", "metric": "thirst_timer", "unit": "ticks"}
    if error is not None:
        m["value"] = None
        m["error"] = error
    else:
        m["value"] = value
    return [m]


def _write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


@pytest.fixture()
def conn(tmp_path):
    with store.connect(tmp_path / "trend.series.sqlite3") as c:
        yield c


# ---- the rollback: default rate must not straddle it --------------------------


@pytest.fixture()
def rollback_db(conn, tmp_path):
    a_path = tmp_path / "a.jsonl"
    _write(a_path, [
        _record("timeline-A", A_START, A_START, "2026-09-19T08:00:00Z", _thirst(0)),
        _record("timeline-A", A_START, 220_000, "2026-09-19T08:10:00Z", _thirst(6378)),
        _record("timeline-A", A_START, A_END, "2026-09-19T08:20:00Z", _thirst(22046)),
    ])
    importer.import_file(conn, a_path)

    b_path = tmp_path / "b.jsonl"
    _write(b_path, [
        _record("timeline-B", B_START, B_START, "2026-09-19T09:00:00Z", _thirst(500)),
        _record("timeline-B", B_START, 230_000, "2026-09-19T09:10:00Z", _thirst(16878)),
        _record("timeline-B", B_START, 250_000, "2026-09-19T09:20:00Z", _thirst(36878)),
    ])
    importer.import_file(conn, b_path)
    return conn


def test_default_series_excludes_superseded_samples(rollback_db):
    rows = trend.series(rollback_db, "unit:192", "thirst_timer")
    ticks = sorted(r["abs_tick"] for r in rows)
    # A's post-rollback samples (220000, 235668) must not appear by default.
    assert 220_000 not in ticks
    assert A_END not in ticks


def test_default_rate_does_not_straddle_the_rollback(rollback_db):
    """The critical test: a rate computed from A's early samples mixed with
    B's later samples would be nonsense (it would cross the discontinuity
    where the tick counter jumped backwards). The default (current-lineage)
    rate must only ever see B's own progression once B exists."""
    result = trend.rate(rollback_db, "unit:192", "thirst_timer", start_abs_tick=A_START, end_abs_tick=250_000)
    assert result.status == trend.MEASURED
    # Every value used must come from timeline-B's own rows: first=500 at
    # 213622, last=36878 at 250000, both from B (A's 213622 row is 0, not
    # 500 -- if the calculation had picked up A's boundary sample instead,
    # this value would differ).
    expected = (36_878 - 500) / (250_000 - 213_622)
    assert result.value == pytest.approx(expected)


def test_superseded_samples_are_reachable_explicitly(rollback_db):
    rows = trend.series(rollback_db, "unit:192", "thirst_timer", lineage="all")
    ticks = sorted(r["abs_tick"] for r in rows)
    assert 220_000 in ticks
    assert A_END in ticks
    row_220000 = next(r for r in rows if r["abs_tick"] == 220_000)
    assert row_220000["superseded"] is True


def test_rate_across_superseded_branch_explicitly_uses_A_data(rollback_db):
    """Asking across the superseded branch is an explicit choice
    (`lineage='all'`); this is not "the" default rate, just proof the data
    is still reachable and usable when asked for."""
    result = trend.rate(
        rollback_db, "unit:192", "thirst_timer",
        start_abs_tick=A_START, end_abs_tick=A_END, lineage="all",
    )
    assert result.status == trend.MEASURED
    # This window mixes A and B rows at the same ticks; just prove it does
    # not crash and produces *some* measured figure using distinct ticks.
    assert result.sample_count >= 2


# ---- nulls: skipped and counted, never treated as zero -------------------------


def test_rate_over_nulls_reports_how_many_it_skipped(conn, tmp_path):
    p = tmp_path / "nulls.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", _thirst(0)),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", _thirst(None, error="vector read failed")),
        _record("t1", 0, 2000, "2026-09-19T08:02:00Z", _thirst(None, error="vector read failed")),
        _record("t1", 0, 3000, "2026-09-19T08:03:00Z", _thirst(3000)),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "unit:192", "thirst_timer")
    assert result.status == trend.MEASURED
    assert result.skipped_nulls == 2
    assert result.sample_count == 2  # only the two non-null readings
    assert result.value == pytest.approx(1.0)  # (3000-0)/(3000-0)


def test_series_never_turns_null_into_zero(conn, tmp_path):
    p = tmp_path / "nulls.jsonl"
    _write(p, [_record("t1", 0, 0, "2026-09-19T08:00:00Z", _thirst(None, error="vector read failed"))])
    importer.import_file(conn, p)

    rows = trend.series(conn, "unit:192", "thirst_timer")
    assert len(rows) == 1
    assert rows[0]["value"] is None
    assert rows[0]["error"] == "vector read failed"


def test_rate_with_only_null_readings_is_unavailable(conn, tmp_path):
    p = tmp_path / "nulls.jsonl"
    _write(p, [
        _record("t1", 0, 0, "2026-09-19T08:00:00Z", _thirst(None, error="x")),
        _record("t1", 0, 1000, "2026-09-19T08:01:00Z", _thirst(None, error="x")),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "unit:192", "thirst_timer")
    assert result.status == trend.UNAVAILABLE
    assert result.value is None
    assert result.skipped_nulls == 2
    assert "two" in result.reason.lower() or "distinct" in result.reason.lower()


# ---- the thirst check: a citizen who did not drink -----------------------------


def test_citizen_who_did_not_drink_has_thirst_rate_of_exactly_one_per_tick(conn, tmp_path):
    p = tmp_path / "thirst.jsonl"
    _write(p, [
        _record("t1", 0, 100_000, "2026-09-19T08:00:00Z", _thirst(20_000)),
        _record("t1", 0, 106_303, "2026-09-19T08:01:00Z", _thirst(26_303)),
    ])
    importer.import_file(conn, p)

    result = trend.rate(conn, "unit:192", "thirst_timer")
    assert result.status == trend.MEASURED
    assert result.value == pytest.approx(1.0)
    assert result.tick_span == 6_303
    assert result.sample_count == 2


# ---- rows shaped for production/cover.py ----------------------------------------


def test_cover_rows_feed_the_real_cover_calculator(conn, tmp_path):
    p = tmp_path / "stock.jsonl"
    _write(p, [
        _record("t1", 0, 1_000_000, "2026-09-19T08:00:00Z",
                 [{"subject": "item:DRINK", "metric": "stock", "value": 150, "unit": "units"}]),
        _record("t1", 0, 1_000_000 + production_cover.TICKS_PER_DAY, "2026-09-19T08:01:00Z",
                 [{"subject": "item:DRINK", "metric": "stock", "value": 130, "unit": "units"}]),
    ])
    importer.import_file(conn, p)

    rows = trend.cover_rows(conn, "item:DRINK", "stock")
    assert len(rows) == 2
    assert all(r["value"] is not None for r in rows)

    figure = production_cover.depletion_rate_per_day(rows)
    assert figure.status == "measured"
    assert figure.value == pytest.approx(20.0)


def test_cover_rows_excludes_nulls_so_cover_py_never_subtracts_none(conn, tmp_path):
    p = tmp_path / "stock.jsonl"
    _write(p, [
        _record("t1", 0, 1_000_000, "2026-09-19T08:00:00Z",
                 [{"subject": "item:DRINK", "metric": "stock", "value": None, "unit": "units", "error": "read failed"}]),
        _record("t1", 0, 1_000_100, "2026-09-19T08:01:00Z",
                 [{"subject": "item:DRINK", "metric": "stock", "value": 130, "unit": "units"}]),
    ])
    importer.import_file(conn, p)

    rows = trend.cover_rows(conn, "item:DRINK", "stock")
    assert len(rows) == 1
    assert rows[0]["value"] == 130


# ---- latest ------------------------------------------------------------------


def test_latest_returns_the_most_recent_reading(conn, tmp_path):
    p = tmp_path / "pop.jsonl"
    _write(p, [
        _record("t1", 0, 1000, "2026-09-19T08:00:00Z", [{"subject": "fort", "metric": "population", "value": 14, "unit": "citizens"}]),
        _record("t1", 0, 2000, "2026-09-19T08:01:00Z", [{"subject": "fort", "metric": "population", "value": 15, "unit": "citizens"}]),
    ])
    importer.import_file(conn, p)

    row = trend.latest(conn, "fort", "population")
    assert row["abs_tick"] == 2000
    assert row["value"] == 15


def test_latest_with_no_data_returns_none(conn):
    assert trend.latest(conn, "fort", "population") is None
