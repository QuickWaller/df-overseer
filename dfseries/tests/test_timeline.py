"""Rollback detection and lineage computation (`dfseries/timeline.py`),
using the real figures from `docs/TIMESERIES.md`'s own example: "a rollback
on 2026-09-19 took [the fort] from 235,668 to 213,622."

Timeline A ran from tick 213,622 to 235,668. Timeline B started at tick
213,622 (the same point A rolled back to) and ran on. A's samples after
213,622 describe a future that did not happen in the surviving history: they
must be marked superseded, kept (not deleted), excluded from the default
lineage, and reachable when asked for explicitly.
"""

from __future__ import annotations

import json

import pytest

from dfseries import importer, store, timeline

A_START = 213_622
A_END = 235_668
B_START = 213_622  # the rollback: B starts exactly where A's history stops being real


def _record(timeline_id, timeline_start_abs_tick, abs_tick, wall_utc, value):
    return {
        "v": 1,
        "timeline_id": timeline_id,
        "timeline_start_abs_tick": timeline_start_abs_tick,
        "abs_tick": abs_tick,
        "cur_year": 0,
        "cur_year_tick": abs_tick,
        "wall_utc": wall_utc,
        "sampler_version": "test",
        "metrics": [{"subject": "unit:192", "metric": "thirst_timer", "value": value, "unit": "ticks"}],
    }


@pytest.fixture()
def conn(tmp_path):
    with store.connect(tmp_path / "rollback.series.sqlite3") as c:
        yield c


@pytest.fixture()
def rollback_db(conn, tmp_path):
    """Timeline A (wall clock earlier) samples 213622 -> 235668; timeline B
    (wall clock later) starts at 213622 and runs to 250000. Imported in
    real-world order, A's file before B's -- the normal case."""
    a_path = tmp_path / "a.jsonl"
    a_records = [
        _record("timeline-A", A_START, A_START, "2026-09-19T08:00:00Z", 0),
        _record("timeline-A", A_START, 220_000, "2026-09-19T08:10:00Z", 6378),
        _record("timeline-A", A_START, A_END, "2026-09-19T08:20:00Z", 22046),
    ]
    a_path.write_text("\n".join(json.dumps(r) for r in a_records) + "\n", encoding="utf-8")
    importer.import_file(conn, a_path)

    b_path = tmp_path / "b.jsonl"
    b_records = [
        _record("timeline-B", B_START, B_START, "2026-09-19T09:00:00Z", 0),
        _record("timeline-B", B_START, 230_000, "2026-09-19T09:10:00Z", 16378),
        _record("timeline-B", B_START, 250_000, "2026-09-19T09:20:00Z", 36378),
    ]
    b_path.write_text("\n".join(json.dumps(r) for r in b_records) + "\n", encoding="utf-8")
    importer.import_file(conn, b_path)
    return conn


def _superseded_by_tick(conn, timeline_id):
    rows = conn.execute(
        "SELECT abs_tick, superseded FROM sample_events WHERE timeline_id = ? ORDER BY abs_tick",
        (timeline_id,),
    ).fetchall()
    return {r["abs_tick"]: bool(r["superseded"]) for r in rows}


def test_a_samples_after_the_rollback_point_are_superseded(rollback_db):
    flags = _superseded_by_tick(rollback_db, "timeline-A")
    assert flags[A_START] is False       # at the rollback tick: still current
    assert flags[220_000] is True        # after it: superseded
    assert flags[A_END] is True          # after it: superseded


def test_b_samples_are_never_superseded_its_the_newest_timeline(rollback_db):
    flags = _superseded_by_tick(rollback_db, "timeline-B")
    assert all(v is False for v in flags.values())


def test_superseded_rows_are_kept_not_deleted(rollback_db):
    n = rollback_db.execute("SELECT COUNT(*) AS n FROM sample_events WHERE timeline_id = ?", ("timeline-A",)).fetchone()["n"]
    assert n == 3  # all three of A's rows still present


def test_lineage_summary_reports_a_as_superseded_and_b_as_the_current_tip(rollback_db):
    summary = {row["timeline_id"]: row for row in timeline.lineage_summary(rollback_db)}
    assert summary["timeline-A"]["cutoff_abs_tick"] == B_START
    assert summary["timeline-A"]["is_current_tip"] is False
    assert summary["timeline-B"]["cutoff_abs_tick"] is None
    assert summary["timeline-B"]["is_current_tip"] is True


def test_import_order_does_not_matter_when_wall_utc_is_present(conn, tmp_path):
    """B (chronologically later) imported before A must produce the same
    lineage as A-then-B, since wall_utc -- not import order -- is the
    ordering key."""
    a_path = tmp_path / "a.jsonl"
    a_records = [
        _record("timeline-A", A_START, A_START, "2026-09-19T08:00:00Z", 0),
        _record("timeline-A", A_START, A_END, "2026-09-19T08:20:00Z", 22046),
    ]
    a_path.write_text("\n".join(json.dumps(r) for r in a_records) + "\n", encoding="utf-8")

    b_path = tmp_path / "b.jsonl"
    b_records = [
        _record("timeline-B", B_START, B_START, "2026-09-19T09:00:00Z", 0),
        _record("timeline-B", B_START, 250_000, "2026-09-19T09:20:00Z", 36378),
    ]
    b_path.write_text("\n".join(json.dumps(r) for r in b_records) + "\n", encoding="utf-8")

    importer.import_file(conn, b_path)  # B first, out of real-world order
    importer.import_file(conn, a_path)

    flags = _superseded_by_tick(conn, "timeline-A")
    assert flags[A_END] is True
    b_flags = _superseded_by_tick(conn, "timeline-B")
    assert all(v is False for v in b_flags.values())
