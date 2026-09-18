"""Importing contract-format JSONL (`docs/TIMESERIES.md`) into the dfseries
database.

**Idempotent.** Two guards, deliberately redundant: `imported_files.
lines_imported` means a normal re-import (or import of a grown file) never
even re-reads lines it already committed, and the `UNIQUE(source_file,
source_line)` constraint on `sample_events` means that even a from-scratch
re-read of the whole file (e.g. progress tracking lost, or a caller passes
the same path under a different string) still cannot duplicate a row --
`store.insert_event` returns `None` on a collision and the metrics for that
line are simply not re-inserted.

**A torn final line** (`ValueError` from `json.loads` on the last line of
the file) is skipped, reported in the result, and **not** counted into
`lines_imported` -- so the next import of the same path retries exactly that
line, which is what lets a grown file complete the write and import cleanly
next time.

**A non-final line that fails to parse** is not "torn" (only the file's
growing edge can be torn by a mid-write stop) -- it is corruption, reported
separately, and skipped with progress advanced past it, since re-reading it
later cannot fix it.

**An unknown `v`** is refused and reported, never guessed at
(`schema.RECORD_VERSION` is the only value this importer accepts). Refusal
also advances progress past that line for the same reason as corruption: a
complete, valid-JSON line that fails validation will not become valid by
waiting.

**Unknown metrics are accepted.** No metric-name vocabulary check here --
`docs/TIMESERIES.md`: "The store must accept unknown metrics rather than
drop them, since the sampler will grow."
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import sqlite3

from . import schema, store, timeline


@dataclass
class ImportResult:
    path: str
    events_imported: int = 0
    metrics_imported: int = 0
    duplicate_lines: list[int] = field(default_factory=list)
    torn_line: int | None = None
    corrupt_lines: list[tuple[int, str]] = field(default_factory=list)
    refused_lines: list[tuple[int, str]] = field(default_factory=list)

    @property
    def had_problems(self) -> bool:
        return bool(self.torn_line or self.corrupt_lines or self.refused_lines)


_REQUIRED_FIELDS = ("timeline_id", "timeline_start_abs_tick", "abs_tick")


def _validate_record(record: dict) -> list[str]:
    """Structural checks beyond the version check, so a syntactically valid
    but contract-incomplete line is refused with a clear reason instead of
    raising a KeyError deep in `store.insert_event`."""
    errors = []
    if not isinstance(record, dict):
        return ["record is not a JSON object"]
    for f in _REQUIRED_FIELDS:
        if f not in record or record[f] is None:
            errors.append(f"{f}: required field is missing")
    metrics = record.get("metrics")
    if metrics is not None and not isinstance(metrics, list):
        errors.append("metrics: expected a list")
    elif isinstance(metrics, list):
        for i, m in enumerate(metrics):
            if not isinstance(m, dict) or "subject" not in m or "metric" not in m:
                errors.append(f"metrics[{i}]: expected an object with 'subject' and 'metric'")
    return errors


def import_file(conn: sqlite3.Connection, path: str | Path) -> ImportResult:
    """Import one JSONL file. Reads the whole file (this project's sample
    volume, one event per game day, never makes that costly) but only
    inserts lines past `imported_files.lines_imported` for this path, and
    the `sample_events` unique constraint is the real idempotency guarantee
    underneath that optimisation."""
    p = Path(path)
    key = str(p)
    result = ImportResult(path=key)

    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()  # a trailing newline never produces a phantom empty final line

    with conn:
        already = store.get_progress(conn, key)
        progress = already

        for idx in range(already, len(lines)):
            raw = lines[idx]
            line_no = idx + 1  # 1-based, human-facing
            is_last = idx == len(lines) - 1

            if raw.strip() == "":
                progress = line_no
                continue

            try:
                record = json.loads(raw)
            except ValueError:
                if is_last:
                    result.torn_line = line_no
                    break  # leave progress before this line; retry it next time
                result.corrupt_lines.append((line_no, "invalid JSON, not the file's final line"))
                progress = line_no
                continue

            v = record.get("v") if isinstance(record, dict) else None
            if v != schema.RECORD_VERSION:
                result.refused_lines.append(
                    (line_no, f"unknown record version v={v!r}; this importer accepts v={schema.RECORD_VERSION}")
                )
                progress = line_no
                continue

            errors = _validate_record(record)
            if errors:
                result.refused_lines.append((line_no, "; ".join(errors)))
                progress = line_no
                continue

            store.upsert_timeline(
                conn,
                timeline_id=record["timeline_id"],
                start_abs_tick=record["timeline_start_abs_tick"],
                wall_utc=record.get("wall_utc"),
            )
            event = {
                "source_file": key,
                "source_line": line_no,
                "timeline_id": record["timeline_id"],
                "timeline_start_abs_tick": record["timeline_start_abs_tick"],
                "abs_tick": record["abs_tick"],
                "cur_year": record.get("cur_year"),
                "cur_year_tick": record.get("cur_year_tick"),
                "wall_utc": record.get("wall_utc"),
                "sampler_version": record.get("sampler_version"),
            }
            event_id = store.insert_event(conn, event)
            if event_id is None:
                result.duplicate_lines.append(line_no)
            else:
                for m in record.get("metrics", []):
                    store.insert_metric(conn, event_id, m)
                    result.metrics_imported += 1
                result.events_imported += 1
            progress = line_no

        store.set_progress(conn, key, progress, datetime.now(timezone.utc).isoformat())
        timeline.recompute_lineage(conn)

    return result


def import_files(conn: sqlite3.Connection, paths: list[str | Path]) -> list[ImportResult]:
    """Import several files **in the order given** -- for correct lineage
    when a timeline's `wall_utc` is absent, that order should be real-world
    chronological order (e.g. sorted by file mtime); see `timeline.py`'s
    module docstring. With `wall_utc` present, the normal case, order here
    does not matter."""
    return [import_file(conn, p) for p in paths]
