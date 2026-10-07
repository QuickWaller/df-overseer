"""The conductor's run reports: one row per role run, written through the
`conductor.report` MCP tool (`dfmcp/conductor_tools.py`) and read, strictly
read-only, by the stream publisher (`dfqueue/live.py`).

A small store of its own, deliberately NOT a table in the queue database:
the queue is an append-only ledger of decisions with a schema version, a
validator, a grader and a feed that all walk `records`; a run report is
mutable operational telemetry (created at launch, completed at the end).
The file sits next to the queue database (`runs_path`), WAL mode, written
only by the MCP server process, opened `mode=ro` by readers.

Records a run touched are resolved here, from the queue, by role and time
window (`records_in_window`), never reported by the conductor.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

RUN_ROLES = ("architect", "overseer", "quartermaster", "consultant", "planner")

FINAL_ANSWER_MAX = 4000
#: The conductor already caps reasoning at 12,000 characters (start and end
#: kept, conductor/runner.py cap_thinking); this is the store's own backstop.
THINKING_MAX = 12500
#: The run's full transcript, a JSON string the conductor already capped (policy
#: `transcript:` block). Truncating JSON would corrupt it, so an over-cap one is
#: dropped whole (stored NULL), never cut.
TRANSCRIPT_MAX = 70000
WAKE_REASON_MAX = 64
WAKE_DETAIL_MAX = 300
ERROR_MAX = 500
STATUS_MAX = 40
RECORDS_MAX = 50
KEEP_ROWS = 500
TRUNCATION_MARKER = "\n[truncated]"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    wake_reason TEXT,
    wake_detail TEXT,
    cycle INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT,
    ok INTEGER,
    timed_out INTEGER,
    duration_s REAL,
    cost_usd REAL,
    error TEXT,
    final_answer TEXT,
    records_json TEXT,
    thinking TEXT,
    transcript TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
"""


class RunsError(Exception):
    pass


def runs_path(queue_db_path: "str | Path") -> Path:
    """`<dir>/<stem>.runs.sqlite3` beside the queue database."""
    p = Path(queue_db_path)
    return p.with_name(p.stem + ".runs.sqlite3")


@contextmanager
def _connect(path: "str | Path") -> Iterator[sqlite3.Connection]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
        if "thinking" not in cols:  # stores made before 2026-10-05
            conn.execute("ALTER TABLE runs ADD COLUMN thinking TEXT")
        if "transcript" not in cols:  # stores made before 2026-10-07
            conn.execute("ALTER TABLE runs ADD COLUMN transcript TEXT")
        yield conn
    finally:
        conn.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _whole_or_none(text: Any, limit: int) -> Optional[str]:
    """`text` whole, or None when absent or over `limit` (never truncated)."""
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= limit else None


def _cap(text: Any, limit: int, *, marker: bool = False) -> Optional[str]:
    if text is None:
        return None
    s = str(text)
    if len(s) <= limit:
        return s
    if marker:
        return s[: limit - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER
    return s[:limit]


def _next_run_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(CAST(SUBSTR(run_id, 5) AS INTEGER)) AS n FROM runs").fetchone()
    return f"run-{(row['n'] or 0) + 1:04d}"


def start_run(
    path: "str | Path", *, role: str, wake_reason: Optional[str], wake_detail: Optional[str],
    cycle: Optional[int], now: Optional[datetime] = None,
) -> dict:
    if role not in RUN_ROLES:
        raise RunsError(f"role {role!r} is not one of {list(RUN_ROLES)}")
    now = now or _now()
    with _connect(path) as conn:
        run_id = _next_run_id(conn)
        conn.execute(
            "INSERT INTO runs (run_id, role, wake_reason, wake_detail, cycle, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, role, _cap(wake_reason, WAKE_REASON_MAX), _cap(wake_detail, WAKE_DETAIL_MAX),
             cycle, now.isoformat()),
        )
        conn.commit()
    return {"run_id": run_id, "started_at": now.isoformat()}


def window_for(
    path: "str | Path", *, run_id: Optional[str], duration_s: Optional[float],
    now: Optional[datetime] = None,
) -> tuple:
    """`(role, started_at, ended_at)` for the run an `end` call is about to
    complete, so the caller can resolve the records before `end_run`.
    Without a `run_id` the window is backdated by `duration_s`, matching what
    `end_run` will store."""
    now = now or _now()
    if run_id is None:
        return None, (now - timedelta(seconds=max(0.0, duration_s or 0.0))).isoformat(), now.isoformat()
    row = get_run(path, run_id)
    if row is None:
        raise RunsError(f"unknown run_id {run_id!r}")
    return row["role"], row["started_at"], now.isoformat()


def end_run(
    path: "str | Path", *, run_id: Optional[str], role: Optional[str],
    wake_reason: Optional[str], wake_detail: Optional[str], cycle: Optional[int],
    status: Optional[str], ok: Optional[bool], timed_out: Optional[bool],
    duration_s: Optional[float], cost_usd: Optional[float], error: Optional[str],
    final_answer: Optional[str], records: list, now: Optional[datetime] = None,
    thinking: Optional[str] = None, transcript: Optional[str] = None,
) -> dict:
    """Completes `run_id`, or, when it is None (the start call failed),
    creates the row from `role` and backdates `started_at` by `duration_s`."""
    now = now or _now()
    with _connect(path) as conn:
        if run_id is not None:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise RunsError(f"unknown run_id {run_id!r}")
            if row["ended_at"] is not None:
                raise RunsError(f"run {run_id} already ended")
        else:
            if role not in RUN_ROLES:
                raise RunsError("end without run_id needs a valid role")
            started = now - timedelta(seconds=max(0.0, duration_s or 0.0))
            run_id = _next_run_id(conn)
            conn.execute(
                "INSERT INTO runs (run_id, role, wake_reason, wake_detail, cycle, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, role, _cap(wake_reason, WAKE_REASON_MAX),
                 _cap(wake_detail, WAKE_DETAIL_MAX), cycle, started.isoformat()),
            )
        conn.execute(
            "UPDATE runs SET ended_at=?, status=?, ok=?, timed_out=?, duration_s=?, cost_usd=?, "
            "error=?, final_answer=?, records_json=?, thinking=?, transcript=? WHERE run_id=?",
            (now.isoformat(), _cap(status, STATUS_MAX),
             None if ok is None else int(bool(ok)),
             None if timed_out is None else int(bool(timed_out)),
             duration_s, cost_usd, _cap(error, ERROR_MAX),
             _cap(final_answer, FINAL_ANSWER_MAX, marker=True),
             json.dumps(records[:RECORDS_MAX]),
             _cap(thinking, THINKING_MAX, marker=True), _whole_or_none(transcript, TRANSCRIPT_MAX),
             run_id),
        )
        conn.execute(
            "DELETE FROM runs WHERE run_id NOT IN "
            "(SELECT run_id FROM runs ORDER BY started_at DESC LIMIT ?)", (KEEP_ROWS,),
        )
        conn.commit()
    return {"run_id": run_id, "ended_at": now.isoformat(), "records": len(records[:RECORDS_MAX])}


def get_run(path: "str | Path", run_id: str) -> Optional[dict]:
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return None if row is None else dict(row)


def read_runs_readonly(path: "str | Path", limit: int = 60) -> list:
    """Newest-first run rows, opened `mode=ro` (never creates or migrates).
    Raises sqlite3.OperationalError if the file or table is absent: the
    caller decides what absence means."""
    uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC, run_id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ---- linking a run to the queue records it wrote ---------------------------


def _parse(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def queue_records_readonly(queue_db: "str | Path") -> list:
    """Every queue record, read `mode=ro` (never creates the database). An
    absent or unreadable queue gives `[]`: linking is best-effort."""
    uri = f"file:{Path(queue_db).resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            rows = conn.execute("SELECT payload FROM records ORDER BY rowid ASC").fetchall()
        finally:
            conn.close()
        return [json.loads(r[0]) for r in rows]
    except (sqlite3.Error, ValueError, OSError):
        return []


def records_in_window(records: list, role: str, started_at: str, ended_at: str) -> list:
    """`[{id, kind, thread}]` for every queue record written by `role`
    between the two server-stamped times, oldest first. `thread` is the
    thread id exactly as the feed computes it (`feed.compute_thread`), so a
    project, plan change or executed step lands in its founding proposal's
    thread on the page."""
    start, end = _parse(started_at), _parse(ended_at)
    if start is None or end is None:
        return []
    # The page's thread ids come from the feed, so resolve them the same way
    # (a project or plan change belongs to its founding proposal's thread).
    from dfqueue import feed
    reply_to_by_id = {r["id"]: feed.compute_reply_to(r) for r in records if isinstance(r, dict) and r.get("id")}
    out = []
    for rec in records:
        if not isinstance(rec, dict) or rec.get("role") != role:
            continue
        ts = _parse(rec.get("ts"))
        if ts is None or ts < start or ts > end:
            continue
        thread = feed.compute_thread(rec["id"], reply_to_by_id) if rec.get("id") else None
        out.append({"id": rec.get("id"), "kind": rec.get("kind"), "thread": thread or rec.get("id")})
    return out
