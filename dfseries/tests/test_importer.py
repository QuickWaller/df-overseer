"""The importer (`dfseries/importer.py`): idempotency, a torn final line, an
unknown record version, and unknown metrics accepted. Handoff
(`handoffs/2026-09-19-dfseries-store.md`) "Tests that matter more than
coverage".
"""

from __future__ import annotations

import json

import pytest

from dfseries import importer, schema, store

# ---- small builders ------------------------------------------------------------


def _record(
    timeline_id="t1", timeline_start_abs_tick=100_000, abs_tick=100_000,
    metrics=None, v=1, wall_utc="2026-09-19T09:00:00Z", **extra,
) -> dict:
    rec = {
        "v": v,
        "timeline_id": timeline_id,
        "timeline_start_abs_tick": timeline_start_abs_tick,
        "abs_tick": abs_tick,
        "cur_year": 30,
        "cur_year_tick": abs_tick % 403200,
        "wall_utc": wall_utc,
        "sampler_version": "test",
        "metrics": metrics if metrics is not None else [
            {"subject": "fort", "metric": "population", "value": 15, "unit": "citizens"},
        ],
    }
    rec.update(extra)
    return rec


def _write(path, records: list[dict], *, trailing_newline=True) -> None:
    lines = [json.dumps(r) for r in records]
    text = "\n".join(lines)
    if trailing_newline:
        text += "\n"
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def conn(tmp_path):
    with store.connect(tmp_path / "test.series.sqlite3") as c:
        yield c


# ---- basic import ---------------------------------------------------------------


def test_imports_events_and_metrics(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    _write(p, [
        _record(abs_tick=100_000, metrics=[
            {"subject": "fort", "metric": "population", "value": 15, "unit": "citizens"},
            {"subject": "fort", "metric": "deaths", "value": 0, "unit": "citizens"},
        ]),
        _record(abs_tick=101_200, metrics=[
            {"subject": "fort", "metric": "population", "value": 15, "unit": "citizens"},
        ]),
    ])
    result = importer.import_file(conn, p)
    assert result.events_imported == 2
    assert result.metrics_imported == 3
    assert not result.had_problems

    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    n_metrics = conn.execute("SELECT COUNT(*) AS n FROM sample_metrics").fetchone()["n"]
    assert n_events == 2
    assert n_metrics == 3


def test_unknown_metric_name_is_accepted_and_stored(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    _write(p, [_record(metrics=[
        {"subject": "unit:192", "metric": "a_metric_nobody_has_defined_yet", "value": 42, "unit": "widgets"},
    ])])
    result = importer.import_file(conn, p)
    assert result.events_imported == 1
    assert result.metrics_imported == 1
    row = conn.execute("SELECT * FROM sample_metrics").fetchone()
    assert row["metric"] == "a_metric_nobody_has_defined_yet"
    assert row["value"] == 42


# ---- idempotency ------------------------------------------------------------------


def test_reimporting_the_same_file_never_duplicates(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    _write(p, [_record(abs_tick=100_000), _record(abs_tick=101_200)])

    importer.import_file(conn, p)
    result2 = importer.import_file(conn, p)

    assert result2.events_imported == 0  # nothing new: progress tracking skipped both lines
    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    assert n_events == 2


def test_reimporting_a_grown_file_only_imports_the_new_lines(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    _write(p, [_record(abs_tick=100_000)])
    result1 = importer.import_file(conn, p)
    assert result1.events_imported == 1

    _write(p, [_record(abs_tick=100_000), _record(abs_tick=101_200)])
    result2 = importer.import_file(conn, p)
    assert result2.events_imported == 1  # only the new line

    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    assert n_events == 2


def test_unique_constraint_still_guards_a_from_scratch_reread(conn, tmp_path):
    """Even if progress tracking were bypassed (a fresh call against a path
    already fully imported, re-reading from line 1), the `UNIQUE(source_file,
    source_line)` constraint on `sample_events` is the real idempotency
    guarantee: `insert_event` must return None rather than raising or
    duplicating."""
    p = tmp_path / "sample.jsonl"
    _write(p, [_record(abs_tick=100_000)])
    importer.import_file(conn, p)

    # Simulate "progress lost": clear imported_files but leave sample_events.
    conn.execute("DELETE FROM imported_files")
    result = importer.import_file(conn, p)
    assert result.events_imported == 0
    assert result.duplicate_lines == [1]
    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    assert n_events == 1


# ---- torn final line --------------------------------------------------------------


def test_torn_final_line_is_skipped_and_reported(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    good = json.dumps(_record(abs_tick=100_000))
    torn = '{"v": 1, "timeline_id": "t1", "abs_tick": 101200, "metr'  # cut mid-write
    p.write_text(good + "\n" + torn, encoding="utf-8")

    result = importer.import_file(conn, p)
    assert result.events_imported == 1
    assert result.torn_line == 2

    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    assert n_events == 1


def test_torn_line_is_retried_once_the_file_completes(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    good = json.dumps(_record(abs_tick=100_000))
    torn = '{"v": 1, "timeline_id": "t1", "abs_tick": 101200, "metr'
    p.write_text(good + "\n" + torn, encoding="utf-8")
    result1 = importer.import_file(conn, p)
    assert result1.torn_line == 2

    # The writer finishes the line and moves on.
    completed = json.dumps(_record(abs_tick=101_200))
    p.write_text(good + "\n" + completed + "\n", encoding="utf-8")
    result2 = importer.import_file(conn, p)
    assert result2.torn_line is None
    assert result2.events_imported == 1

    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    assert n_events == 2


# ---- unknown record version ----------------------------------------------------


def test_unknown_version_is_refused_and_reported(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    _write(p, [_record(abs_tick=100_000, v=2), _record(abs_tick=101_200, v=1)])

    result = importer.import_file(conn, p)
    assert result.events_imported == 1  # only the v=1 line
    assert len(result.refused_lines) == 1
    assert result.refused_lines[0][0] == 1
    assert "v=2" in result.refused_lines[0][1]

    n_events = conn.execute("SELECT COUNT(*) AS n FROM sample_events").fetchone()["n"]
    assert n_events == 1


# ---- null values ----------------------------------------------------------------


def test_null_value_is_preserved_never_zero_never_dropped(conn, tmp_path):
    p = tmp_path / "sample.jsonl"
    _write(p, [_record(metrics=[
        {"subject": "item:DRINK", "metric": "stock", "value": None, "unit": "units", "error": "vector read failed"},
    ])])
    result = importer.import_file(conn, p)
    assert result.events_imported == 1
    assert result.metrics_imported == 1

    row = conn.execute("SELECT * FROM sample_metrics").fetchone()
    assert row["value"] is None
    assert row["error"] == "vector read failed"
