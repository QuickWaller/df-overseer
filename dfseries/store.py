"""Connection management and the low-level write path for the dfseries
database. Follows `dfqueue/store.py`'s own precedent: WAL journal, `Row`
factory, a `schema_version` check on connect, and `with conn:` transactions
so a partial write never lands.

Nothing here parses JSONL or reasons about timelines -- that is
`importer.py` and `timeline.py`. This module only knows how to open the
database and insert rows that are already well-formed dicts.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from . import schema

DEFAULT_DIR = Path(__file__).resolve().parent


def default_path(fort: str = "uniboslan") -> Path:
    return DEFAULT_DIR / f"{fort}.series.sqlite3"


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        schema.create_schema(conn)
        yield conn
    finally:
        conn.close()


# ---- timelines ---------------------------------------------------------------


def upsert_timeline(
    conn: sqlite3.Connection, *, timeline_id: str, start_abs_tick: int, wall_utc: str | None,
) -> None:
    """Insert a timeline the first time it is seen; on a later sighting,
    only ever *lower* `first_wall_utc` (the earliest real-world clock
    reading for this timeline is the ordering key rollback detection needs;
    a later-imported line from the same timeline must never push it later)."""
    row = conn.execute("SELECT first_wall_utc FROM timelines WHERE id = ?", (timeline_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO timelines (id, start_abs_tick, first_wall_utc, cutoff_abs_tick) "
            "VALUES (?, ?, ?, NULL)",
            (timeline_id, start_abs_tick, wall_utc),
        )
        return
    existing = row["first_wall_utc"]
    if wall_utc is not None and (existing is None or wall_utc < existing):
        conn.execute(
            "UPDATE timelines SET first_wall_utc = ? WHERE id = ?", (wall_utc, timeline_id)
        )


def all_timelines(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM timelines").fetchall()


def set_cutoff(conn: sqlite3.Connection, timeline_id: str, cutoff_abs_tick: int | None) -> None:
    conn.execute(
        "UPDATE timelines SET cutoff_abs_tick = ? WHERE id = ?", (cutoff_abs_tick, timeline_id)
    )


def recompute_superseded(conn: sqlite3.Connection) -> None:
    """Re-derive `sample_events.superseded` from the current
    `timelines.cutoff_abs_tick` values. Cheap full recompute (this project's
    sample volume is one event per game day) rather than incremental
    patching, so it is correct no matter what order files were imported in
    or how many new timelines a single import call discovers."""
    conn.execute(
        "UPDATE sample_events SET superseded = CASE "
        "WHEN (SELECT cutoff_abs_tick FROM timelines t WHERE t.id = sample_events.timeline_id) IS NOT NULL "
        "AND abs_tick > (SELECT cutoff_abs_tick FROM timelines t WHERE t.id = sample_events.timeline_id) "
        "THEN 1 ELSE 0 END"
    )


# ---- sample events and metrics -----------------------------------------------


def insert_event(conn: sqlite3.Connection, event: dict) -> Optional[int]:
    """Insert one sample event. Returns its `id`, or `None` if a row with
    the same `(source_file, source_line)` already exists (idempotent
    re-import) -- the caller should not insert metrics in that case, since
    they would already be there too."""
    existing = conn.execute(
        "SELECT id FROM sample_events WHERE source_file = ? AND source_line = ?",
        (event["source_file"], event["source_line"]),
    ).fetchone()
    if existing is not None:
        return None
    cur = conn.execute(
        "INSERT INTO sample_events "
        "(source_file, source_line, timeline_id, timeline_start_abs_tick, abs_tick, "
        "cur_year, cur_year_tick, wall_utc, sampler_version, superseded) "
        "VALUES (:source_file, :source_line, :timeline_id, :timeline_start_abs_tick, :abs_tick, "
        ":cur_year, :cur_year_tick, :wall_utc, :sampler_version, 0)",
        event,
    )
    return cur.lastrowid


def insert_metric(conn: sqlite3.Connection, event_id: int, metric: dict) -> None:
    conn.execute(
        "INSERT INTO sample_metrics (event_id, subject, metric, value, unit, error) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            event_id, metric["subject"], metric["metric"], metric.get("value"),
            metric.get("unit"), metric.get("error"),
        ),
    )


# ---- import progress ----------------------------------------------------------


def get_progress(conn: sqlite3.Connection, path: str) -> int:
    row = conn.execute("SELECT lines_imported FROM imported_files WHERE path = ?", (path,)).fetchone()
    return row["lines_imported"] if row is not None else 0


def set_progress(conn: sqlite3.Connection, path: str, lines_imported: int, imported_at: str) -> None:
    conn.execute(
        "INSERT INTO imported_files (path, lines_imported, last_imported_at) VALUES (?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET lines_imported = excluded.lines_imported, "
        "last_imported_at = excluded.last_imported_at",
        (path, lines_imported, imported_at),
    )
