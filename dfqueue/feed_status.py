"""A read-only equivalent of `dfqueue.store.project_status`, for the stream
page publisher (slice S1, `handoffs/2026-10-01-stream-page-s1-prep.md`,
closing the gap `dfqueue/feed.py`'s own `GAPS` list names: "a read-only
equivalent of `dfqueue.store.project_status` for step-level progress
(S0's named gap), in a new module, without touching `store.py`").

`store.project_status` reads through `store._connect`, which runs
`_ensure_schema` on open and could create or migrate tables -- exactly the
write path design §4.1 forbids a publisher from touching ("the publisher
must open the queue with a read-only SQLite connection, not through
`dfqueue.store._connect`"). This module opens the same database file with
the same `file:...?mode=ro` URI `dfqueue.feed.load_records_readonly` already
uses, then runs the *same* status computation `store.project_status` does.

The computation itself is not re-derived here: `step_status`,
`_current_steps_and_version`, `_step_has_executed_record` and
`PROJECT_ABANDONED` are imported from `store` and called against this
module's own read-only connection. All three take a plain
`sqlite3.Connection` and perform only `SELECT`s -- they have no write side
effects of their own, so importing them is reading `store.py`'s logic, not
touching it (this handoff's own rule is "do not write
`dfqueue/schema.py`, `dfqueue/store.py`"; nothing here edits either file).
Duplicating `project_status`'s own query shape here, rather than its
connection acquisition, is deliberate: a second implementation of "which
step counts as done" would drift from `store.py`'s the first time one of
them changed, which is exactly the two-source-of-truth problem design §4.1
rejects for the publisher pipeline as a whole (one store, one publisher).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .schema import ABANDON, DONE, HELD, PROJECT
from .store import (
    PROJECT_ABANDONED,
    QueueError,
    _current_steps_and_version,
    _step_has_executed_record,
    step_status,
)


def _connect_readonly(path: str | Path) -> sqlite3.Connection:
    """Open `path` strictly read-only, same URI form as
    `dfqueue.feed.load_records_readonly` -- SQLite's own read-only URI mode,
    never `store._connect` (which runs `_ensure_schema`, a write, on open).
    Raises `sqlite3.OperationalError` if the file does not exist, same
    "do not swallow a missing database" choice `feed.load_records_readonly`
    makes."""
    uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_project_ids_readonly(path: str | Path) -> list[str]:
    """Read-only equivalent of `store.list_project_ids`: every `project`
    record's own id, oldest first (insertion order)."""
    conn = _connect_readonly(path)
    try:
        rows = conn.execute(
            "SELECT id FROM records WHERE kind = ? ORDER BY rowid ASC", (PROJECT,)
        ).fetchall()
    finally:
        conn.close()
    return [r["id"] for r in rows]


def project_status_readonly(path: str | Path, project_id: str) -> dict:
    """Read-only equivalent of `store.project_status`: same return shape
    (`project_id`, `summary`, `status`, `version`, `counts`, `top_blocker`,
    and `abandoned_reason` when abandoned), computed the same way, over a
    read-only connection. See the module docstring for why the computation
    itself is imported rather than re-derived."""
    conn = _connect_readonly(path)
    try:
        proj_row = conn.execute(
            "SELECT payload FROM records WHERE id = ? AND kind = ?",
            (project_id, PROJECT),
        ).fetchone()
        if proj_row is None:
            raise QueueError(f"no such project: {project_id!r}")
        project = json.loads(proj_row["payload"])

        abandon_row = conn.execute(
            "SELECT payload FROM records WHERE kind = ? AND "
            "json_extract(payload, '$.project_id') = ?",
            (ABANDON, project_id),
        ).fetchone()

        steps, version = _current_steps_and_version(conn, project)

        rows = conn.execute(
            "SELECT id, step_id, target, state, reason FROM step_targets "
            "WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()

        counts: dict[str, int] = {}
        top_blocker = None
        rows_by_step: dict = {}
        for r in rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
            rows_by_step.setdefault(r["step_id"], []).append(r["state"])
            if top_blocker is None and r["state"] == HELD:
                top_blocker = {
                    "step_id": r["step_id"], "target": r["target"],
                    "reason": r["reason"],
                }

        if abandon_row is not None:
            status = PROJECT_ABANDONED
            abandoned_reason = json.loads(abandon_row["payload"]).get("reason")
        else:
            abandoned_reason = None
            ruling_id = project["from_ruling"]
            all_done = True
            for step in steps:
                if not (
                    isinstance(step, dict)
                    and isinstance(step.get("id"), str)
                    and step["id"]
                ):
                    continue
                own_rows = rows_by_step.get(step["id"], [])
                has_executed = own_rows == [] and _step_has_executed_record(
                    conn, ruling_id, step
                )
                if step_status(own_rows, has_executed) != DONE:
                    all_done = False
                    break
            status = DONE if all_done else "active"
    finally:
        conn.close()

    result = {
        "project_id": project_id,
        "summary": project.get("summary"),
        "status": status,
        "version": version,
        "counts": counts,
        "top_blocker": top_blocker,
    }
    if abandoned_reason is not None:
        result["abandoned_reason"] = abandoned_reason
    return result


def all_project_statuses_readonly(path: str | Path) -> dict[str, dict]:
    """Every project's status, keyed by id -- the publisher's one call per
    feed build, rather than enumerating ids and calling
    `project_status_readonly` once per id itself (same two-step shape
    `store.list_project_ids` plus `store.project_status` already uses, just
    bundled for a single-pass caller)."""
    return {
        pid: project_status_readonly(path, pid)
        for pid in list_project_ids_readonly(path)
    }
