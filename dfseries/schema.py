"""The dfseries schema: DDL plus record-version validation.

Deliberately **not** `production/schema.py`: that module's `production_node`
DDL comment says why the two databases must never share a lifecycle ("the
history must never share a lifecycle with the static graph",
`handoffs/2026-09-19-dfseries-store.md`). This module owns none of
`production/`'s closed vocabularies (`STATUS_VALUES`, `OBSERVATION_METRICS`)
on purpose: `docs/TIMESERIES.md` says "the store must accept unknown metrics
rather than drop them, since the sampler will grow", so `metric` and
`subject` here are open strings, not a CHECK-constrained enum.

Four tables:

- `timelines` -- one row per `timeline_id` (`docs/TIMESERIES.md`
  "Timelines"). `first_wall_utc` is the ordering key rollback detection
  needs: after a rollback, tick order is exactly what breaks, so only the
  sampler's real-world clock can say which timeline actually came second.
  `cutoff_abs_tick` is computed, not carried by the sampler: NULL for the
  newest timeline in the chain, else the `abs_tick` at which its immediate
  successor began (`docs/TIMESERIES.md`: "only its samples at or before the
  tick where its successor began").
- `sample_events` -- one row per JSONL line (one sample event, per the
  contract's "one line per sample event, not per metric"). Carries the
  event-level fields (`abs_tick`, `cur_year`, wall clock, sampler version)
  once, plus `superseded`, recomputed whenever a new timeline is discovered.
- `sample_metrics` -- one row per metric in that event's `metrics` array.
  `value` is nullable (a failed read); `error` is the metric's own recorded
  reason, carried through unchanged, never collapsed to a number.
- `imported_files` -- import progress per source file, `lines_imported`
  counting only lines *committed* to `sample_events` (a torn final line is
  never counted, so the same line is retried on the next import of a grown
  file).
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

RECORD_VERSION = 1  # the only `v` this importer currently accepts

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS timelines (
    id                TEXT PRIMARY KEY,
    start_abs_tick    INTEGER NOT NULL,
    first_wall_utc    TEXT,
    cutoff_abs_tick   INTEGER
);

CREATE TABLE IF NOT EXISTS sample_events (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file              TEXT NOT NULL,
    source_line              INTEGER NOT NULL,
    timeline_id              TEXT NOT NULL REFERENCES timelines(id),
    timeline_start_abs_tick  INTEGER NOT NULL,
    abs_tick                 INTEGER NOT NULL,
    cur_year                 INTEGER,
    cur_year_tick            INTEGER,
    wall_utc                 TEXT,
    sampler_version          TEXT,
    superseded               INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_file, source_line)
);

CREATE INDEX IF NOT EXISTS idx_events_timeline_tick ON sample_events(timeline_id, abs_tick);
CREATE INDEX IF NOT EXISTS idx_events_superseded ON sample_events(superseded);

CREATE TABLE IF NOT EXISTS sample_metrics (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id  INTEGER NOT NULL REFERENCES sample_events(id),
    subject   TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     REAL,
    unit      TEXT,
    error     TEXT
);

CREATE INDEX IF NOT EXISTS idx_metrics_subject_metric ON sample_metrics(subject, metric);
CREATE INDEX IF NOT EXISTS idx_metrics_event ON sample_metrics(event_id);

CREATE TABLE IF NOT EXISTS imported_files (
    path              TEXT PRIMARY KEY,
    lines_imported    INTEGER NOT NULL DEFAULT 0,
    last_imported_at  TEXT
);
"""


class SchemaError(Exception):
    """Raised when a database's schema_version does not match this code."""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif row[0] != SCHEMA_VERSION:
        raise SchemaError(
            f"database is schema_version {row[0]}, this code is {SCHEMA_VERSION}"
        )
