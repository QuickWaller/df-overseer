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
#: Every reason a role was woken for in one run (ordered, deduplicated), a JSON
#: list of codes in the `wake_reasons` column; `wake_reason` stays the first.
WAKE_REASONS_MAX = 12
ERROR_MAX = 500
#: Session fields (research/2026-10-09-gateway-sessions-v1.md 15.9), all nullable: a row from
#: before them, or a run that reported none, has NULLs. `transport` is one of TRANSPORTS;
#: `activation_id` is the conductor's activation the run was part of (a one-shot Overseer run is
#: its own activation, `act-<run_id>`); `items_pushed` and `news_lines` count what the conductor
#: sent into the session on that activation.
TRANSPORTS = ("one_shot", "gateway")
SESSION_KEY_MAX = 120
ACTIVATION_ID_MAX = 120
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
    wake_reasons TEXT,
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
    transcript TEXT,
    transport TEXT,
    session_key TEXT,
    activation_id TEXT,
    items_pushed INTEGER,
    news_lines INTEGER
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
        if "wake_reasons" not in cols:  # stores made before 2026-10-07 (all wake reasons)
            conn.execute("ALTER TABLE runs ADD COLUMN wake_reasons TEXT")
        for name, kind in (("transport", "TEXT"), ("session_key", "TEXT"), ("activation_id", "TEXT"),
                           ("items_pushed", "INTEGER"), ("news_lines", "INTEGER")):
            if name not in cols:  # stores made before 2026-10-09 (session fields)
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {kind}")
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


def encode_wake_reasons(reasons: Any, first: Optional[str] = None) -> Optional[str]:
    """The `wake_reasons` column value: a JSON list, ordered and deduplicated,
    each code capped like `wake_reason`, at most `WAKE_REASONS_MAX` of them.
    `first` (the single `wake_reason`) leads when given. None when there is
    nothing to record."""
    out: list = []
    for r in [first, *(reasons or [])]:
        c = _cap(r, WAKE_REASON_MAX) if r else None
        if c and c not in out:
            out.append(c)
    return json.dumps(out[:WAKE_REASONS_MAX]) if out else None


def decode_wake_reasons(row: Any) -> list:
    """A run row's reasons as a list: the column when present, else the single
    `wake_reason` (rows from before the column)."""
    try:
        got = json.loads(row.get("wake_reasons") or "null")
    except (ValueError, TypeError, AttributeError):
        got = None
    if isinstance(got, list) and got:
        return [x for x in got if isinstance(x, str)]
    one = row.get("wake_reason") if hasattr(row, "get") else None
    return [one] if isinstance(one, str) and one else []


def session_values(
    transport: Optional[str], session_key: Optional[str], activation_id: Optional[str],
    items_pushed: Optional[int], news_lines: Optional[int],
) -> tuple:
    """The five session columns, validated and capped; all None for a run that has none."""
    if transport is not None and transport not in TRANSPORTS:
        raise RunsError(f"transport {transport!r} is not one of {list(TRANSPORTS)}")
    for name, v in (("items_pushed", items_pushed), ("news_lines", news_lines)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            raise RunsError(f"{name} must be a non-negative integer")
    return (transport, _cap(session_key, SESSION_KEY_MAX), _cap(activation_id, ACTIVATION_ID_MAX),
            items_pushed, news_lines)


def _next_run_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(CAST(SUBSTR(run_id, 5) AS INTEGER)) AS n FROM runs").fetchone()
    return f"run-{(row['n'] or 0) + 1:04d}"


def start_run(
    path: "str | Path", *, role: str, wake_reason: Optional[str], wake_detail: Optional[str],
    cycle: Optional[int], now: Optional[datetime] = None, wake_reasons: Optional[list] = None,
    transport: Optional[str] = None, session_key: Optional[str] = None, activation_id: Optional[str] = None,
    items_pushed: Optional[int] = None, news_lines: Optional[int] = None,
) -> dict:
    if role not in RUN_ROLES:
        raise RunsError(f"role {role!r} is not one of {list(RUN_ROLES)}")
    sess = session_values(transport, session_key, activation_id, items_pushed, news_lines)
    now = now or _now()
    with _connect(path) as conn:
        run_id = _next_run_id(conn)
        conn.execute(
            "INSERT INTO runs (run_id, role, wake_reason, wake_detail, wake_reasons, cycle, started_at, "
            "transport, session_key, activation_id, items_pushed, news_lines) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, role, _cap(wake_reason, WAKE_REASON_MAX), _cap(wake_detail, WAKE_DETAIL_MAX),
             encode_wake_reasons(wake_reasons, wake_reason), cycle, now.isoformat(), *sess),
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
    wake_reasons: Optional[list] = None,
    transport: Optional[str] = None, session_key: Optional[str] = None, activation_id: Optional[str] = None,
    items_pushed: Optional[int] = None, news_lines: Optional[int] = None,
) -> dict:
    """Completes `run_id`, or, when it is None (the start call failed),
    creates the row from `role` and backdates `started_at` by `duration_s`."""
    sess = session_values(transport, session_key, activation_id, items_pushed, news_lines)
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
                "INSERT INTO runs (run_id, role, wake_reason, wake_detail, wake_reasons, cycle, started_at, "
                "transport, session_key, activation_id, items_pushed, news_lines) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, role, _cap(wake_reason, WAKE_REASON_MAX),
                 _cap(wake_detail, WAKE_DETAIL_MAX), encode_wake_reasons(wake_reasons, wake_reason),
                 cycle, started.isoformat(), *sess),
            )
        conn.execute(
            "UPDATE runs SET ended_at=?, status=?, ok=?, timed_out=?, duration_s=?, cost_usd=?, "
            "error=?, final_answer=?, records_json=?, thinking=?, transcript=?, "
            "transport=COALESCE(?, transport), session_key=COALESCE(?, session_key), "
            "activation_id=COALESCE(?, activation_id), items_pushed=COALESCE(?, items_pushed), "
            "news_lines=COALESCE(?, news_lines) WHERE run_id=?",
            (now.isoformat(), _cap(status, STATUS_MAX),
             None if ok is None else int(bool(ok)),
             None if timed_out is None else int(bool(timed_out)),
             duration_s, cost_usd, _cap(error, ERROR_MAX),
             _cap(final_answer, FINAL_ANSWER_MAX, marker=True),
             json.dumps(records[:RECORDS_MAX]),
             _cap(thinking, THINKING_MAX, marker=True), _whole_or_none(transcript, TRANSCRIPT_MAX),
             *sess, run_id),
        )
        conn.execute(
            "DELETE FROM runs WHERE run_id NOT IN "
            "(SELECT run_id FROM runs ORDER BY started_at DESC LIMIT ?)", (KEEP_ROWS,),
        )
        conn.commit()
    kept = records[:RECORDS_MAX]
    # `record_ids`: what the conductor's execute containment checks a ruling against (a record
    # the run wrote, on the server's own clock). Capped like the stored list, so a run that
    # wrote more than RECORDS_MAX records leaves the rest uncontained (fail closed).
    return {"run_id": run_id, "ended_at": now.isoformat(), "records": len(kept),
            "record_ids": [r["id"] for r in kept if isinstance(r, dict) and r.get("id")]}


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
