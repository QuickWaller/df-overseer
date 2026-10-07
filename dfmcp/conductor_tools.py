"""`conductor.report`: the conductor's run reports, carried to VM 103 over the
MCP connection it already holds (handoffs/2026-10-05-conductor-report.md).

One native tool, two phases. `start` is called when the conductor launches a
role's run; `end` when it finishes. The server stamps both times itself (one
clock, no cross-host skew), stores the row in `dfqueue/runs.py`'s small store
beside the queue database, and at `end` resolves which queue records that role
wrote inside the run's window (never reported by the conductor, so it cannot
be a model's claim).

Conductor only, twice over: the allowlist (`agents/conductor/tools.yaml` is the
only grant) and a refusal here when the authenticated role is anything else.
Not `mutates` (it never touches the fort).

Failure containment is the caller's job (`conductor/cycle.py` swallows and
logs); this module's job is to refuse cleanly: bad arguments, a storage error,
an unknown run id all raise `ConductorToolError`, which `dfmcp/server.py`
turns into an `isError` result.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from dfqueue import runs

from . import executor_tools, plan_tools

CONDUCTOR_REPORT = "conductor.report"
#: handoffs/2026-10-05-safe-to-resume.md. The Overseer's explicit answer to
#: "is it safe to resume this unexplained pause?", and the conductor's read of
#: it. The verdict is recorded, never acted on here: nothing in this module
#: touches the fort, and the Overseer still holds no `clock.resume`.
PAUSE_VERDICT = "pause.verdict"
PAUSE_VERDICT_READ = "pause.verdict_read"
NATIVE_TOOL_IDS = (CONDUCTOR_REPORT, PAUSE_VERDICT, PAUSE_VERDICT_READ)
VERDICT_REASON_MAX = 300

REPORTER_ROLE = "conductor"


class ConductorToolError(Exception):
    """A `conductor.report` call is refused."""


@dataclass(frozen=True)
class NativeTool:
    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()

    def describe(self, role: str) -> Tuple[str, dict]:
        del role
        return _DESCRIPTIONS[self.id], _SCHEMAS[self.id]


NATIVE_TOOLS: Dict[str, Any] = {
    CONDUCTOR_REPORT: NativeTool(id=CONDUCTOR_REPORT),
    # Overseer only, by the same sole_writer_only mechanism as queue.escalate.
    PAUSE_VERDICT: NativeTool(id=PAUSE_VERDICT, sole_writer_only=True),
    PAUSE_VERDICT_READ: NativeTool(id=PAUSE_VERDICT_READ),
}
# The executor tools (dfmcp/executor_tools.py) are the conductor's too. They are
# merged into this table, and not into a fifth dict at every merge site, so every
# place that registers "the conductor's native tools" picks them up; the server
# routes their calls to `executor_tools.call`, ahead of this module's own.
NATIVE_TOOLS.update(executor_tools.NATIVE_TOOLS)
# The plan tools (dfmcp/plan_tools.py: plan.write, plan.read, plan.status) ride
# the same table for the same reason: roles other than the conductor hold them
# (the Planner writes, four roles read), and every place that builds a registry
# from "the native tools" already merges this table, so none can forget them.
# The server routes their calls to `plan_tools.call`, ahead of this module's.
NATIVE_TOOLS.update(plan_tools.NATIVE_TOOLS)

_DESCRIPTION = (
    "Report one role run to the operator's record, conductor only. phase='start' when "
    "launching a run (role, wake_reason, wake_detail, cycle); it returns a run_id. "
    "phase='end' when it finishes (run_id, status, ok, timed_out, duration_s, cost_usd, "
    "error, final_answer, thinking; both texts are capped). The server stamps times and works "
    "out which queue records the run wrote. Never changes the fort."
)

_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phase"],
    "properties": {
        "phase": {"type": "string", "enum": ["start", "end"]},
        "run_id": {"type": "string", "description": "From the start call; end only."},
        "role": {"type": "string", "enum": list(runs.RUN_ROLES)},
        "wake_reason": {"type": "string", "maxLength": runs.WAKE_REASON_MAX},
        "wake_detail": {"type": "string", "maxLength": runs.WAKE_DETAIL_MAX},
        "cycle": {"type": "integer"},
        "status": {"type": "string", "maxLength": runs.STATUS_MAX},
        "ok": {"type": "boolean"},
        "timed_out": {"type": "boolean"},
        "duration_s": {"type": "number", "minimum": 0},
        "cost_usd": {"type": ["number", "null"], "minimum": 0},
        "error": {"type": ["string", "null"]},
        "final_answer": {"type": ["string", "null"]},
        "thinking": {"type": ["string", "null"]},
    },
}

_FIELDS = set(_SCHEMA["properties"])

_VERDICT_DESCRIPTION = (
    "Give your verdict on an unexplained pause: resume=true says you looked and it is safe "
    "for the conductor to resume; resume=false says keep the fort paused. A required one-line "
    "reason. Call it once, only when woken for an unexplained_pause. It resumes nothing "
    "itself: the conductor resumes once and verifies the tick, and never over a tripwire or an "
    "escalation. No verdict, or resume=false, keeps the fort paused and alerts the human."
)
_VERDICT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["resume", "reason"],
    "properties": {
        "resume": {"type": "boolean"},
        "reason": {"type": "string", "minLength": 1, "maxLength": VERDICT_REASON_MAX},
    },
}
_VERDICT_READ_DESCRIPTION = (
    "Conductor only. Returns the pause verdicts written after since_id (default 0) and the "
    "latest verdict id, so the conductor can tell this run's verdict from an old one. Read-only."
)
_VERDICT_READ_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"since_id": {"type": "integer", "minimum": 0}},
}
_DESCRIPTIONS = {
    CONDUCTOR_REPORT: _DESCRIPTION, PAUSE_VERDICT: _VERDICT_DESCRIPTION,
    PAUSE_VERDICT_READ: _VERDICT_READ_DESCRIPTION,
}
_SCHEMAS = {
    CONDUCTOR_REPORT: _SCHEMA, PAUSE_VERDICT: _VERDICT_SCHEMA, PAUSE_VERDICT_READ: _VERDICT_READ_SCHEMA,
}


def pause_verdict_path(queue_db_path: Any) -> Path:
    """`<dir>/<stem>.pause.sqlite3` beside the queue database."""
    p = Path(queue_db_path)
    return p.with_name(p.stem + ".pause.sqlite3")


def _verdict_connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS verdicts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "at TEXT NOT NULL, role TEXT NOT NULL, resume INTEGER NOT NULL, reason TEXT NOT NULL)"
    )
    return conn


def _verdict_sync(role: str, arguments: Mapping[str, Any], queue_db_path: Any) -> Tuple[str, dict]:
    resume, reason = arguments.get("resume"), arguments.get("reason")
    if not isinstance(resume, bool):
        raise ConductorToolError(f"{PAUSE_VERDICT}: 'resume' must be true or false")
    if not isinstance(reason, str) or not reason.strip():
        raise ConductorToolError(f"{PAUSE_VERDICT}: a one-line 'reason' is required")
    reason = " ".join(reason.split())[:VERDICT_REASON_MAX]
    at = datetime.now(timezone.utc).isoformat()
    try:
        conn = _verdict_connect(pause_verdict_path(queue_db_path))
        try:
            cur = conn.execute(
                "INSERT INTO verdicts (at, role, resume, reason) VALUES (?, ?, ?, ?)",
                (at, role, 1 if resume else 0, reason),
            )
            conn.commit()
            vid = cur.lastrowid
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        raise ConductorToolError(f"{PAUSE_VERDICT}: the verdict store is unavailable: {exc}") from exc
    out = {"id": vid, "at": at, "resume": resume, "reason": reason}
    return f"verdict {vid} recorded: resume={str(resume).lower()}", out


def _verdict_read_sync(arguments: Mapping[str, Any], queue_db_path: Any) -> Tuple[str, dict]:
    since = arguments.get("since_id", 0)
    if isinstance(since, bool) or not isinstance(since, int) or since < 0:
        raise ConductorToolError(f"{PAUSE_VERDICT_READ}: 'since_id' must be a non-negative integer")
    path = pause_verdict_path(queue_db_path)
    rows: list = []
    latest = 0
    try:
        if path.is_file():
            conn = _verdict_connect(path)
            try:
                latest = conn.execute("SELECT COALESCE(MAX(id), 0) FROM verdicts").fetchone()[0]
                rows = [
                    {"id": r["id"], "at": r["at"], "resume": bool(r["resume"]), "reason": r["reason"]}
                    for r in conn.execute("SELECT * FROM verdicts WHERE id > ? ORDER BY id", (since,))
                ]
            finally:
                conn.close()
    except (sqlite3.Error, OSError) as exc:
        raise ConductorToolError(f"{PAUSE_VERDICT_READ}: the verdict store is unavailable: {exc}") from exc
    return f"{len(rows)} verdict(s) after {since}, latest id {latest}", {"latest_id": latest, "verdicts": rows}


def _opt_str(arguments: Mapping[str, Any], key: str) -> Optional[str]:
    v = arguments.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: {key!r} must be a string")
    return v


def _opt_num(arguments: Mapping[str, Any], key: str) -> Optional[float]:
    v = arguments.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: {key!r} must be a number")
    return float(v)


def _opt_bool(arguments: Mapping[str, Any], key: str) -> Optional[bool]:
    v = arguments.get(key)
    if v is None:
        return None
    if not isinstance(v, bool):
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: {key!r} must be a boolean")
    return v


def _opt_int(arguments: Mapping[str, Any], key: str) -> Optional[int]:
    v = arguments.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: {key!r} must be an integer")
    return v


def _report_sync(arguments: Mapping[str, Any], queue_db_path: Any) -> Tuple[str, dict]:
    phase = arguments.get("phase")
    if phase not in ("start", "end"):
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: 'phase' must be 'start' or 'end'")
    path = runs.runs_path(queue_db_path)
    role = _opt_str(arguments, "role")
    wake_reason = _opt_str(arguments, "wake_reason")
    wake_detail = _opt_str(arguments, "wake_detail")
    cycle = _opt_int(arguments, "cycle")
    try:
        if phase == "start":
            if role is None:
                raise ConductorToolError(f"{CONDUCTOR_REPORT}: start needs 'role'")
            out = runs.start_run(
                path, role=role, wake_reason=wake_reason, wake_detail=wake_detail, cycle=cycle,
            )
            return f"{out['run_id']} started ({role})", out

        run_id = _opt_str(arguments, "run_id")
        duration_s = _opt_num(arguments, "duration_s")
        run_role, started_at, ended_at = runs.window_for(path, run_id=run_id, duration_s=duration_s)
        run_role = run_role or role
        linked: list = []
        if run_role in runs.RUN_ROLES:
            linked = runs.records_in_window(
                runs.queue_records_readonly(queue_db_path), run_role, started_at, ended_at,
            )
        out = runs.end_run(
            path, run_id=run_id, role=role, wake_reason=wake_reason, wake_detail=wake_detail,
            cycle=cycle, status=_opt_str(arguments, "status"), ok=_opt_bool(arguments, "ok"),
            timed_out=_opt_bool(arguments, "timed_out"), duration_s=duration_s,
            cost_usd=_opt_num(arguments, "cost_usd"), error=_opt_str(arguments, "error"),
            final_answer=_opt_str(arguments, "final_answer"), records=linked,
            thinking=_opt_str(arguments, "thinking"),
        )
        return f"{out['run_id']} ended, {out['records']} record(s) linked", out
    except runs.RunsError as exc:
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: {exc}") from exc
    except (sqlite3.Error, OSError) as exc:
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: the run store is unavailable: {exc}") from exc


async def call(
    tool_id: str, role: str, arguments: Mapping[str, Any], *, queue_db_path: Any,
    write_lock: "asyncio.Lock",
) -> Tuple[str, Optional[dict]]:
    if tool_id == PAUSE_VERDICT:
        # The roster's sole_writer only: the allowlist plus this check.
        from dfqueue import schema as _schema
        if role != _schema.sole_writer():
            raise ConductorToolError(f"{PAUSE_VERDICT}: only the Overseer may give a pause verdict")
        unknown = sorted(set(arguments) - set(_VERDICT_SCHEMA["properties"]))
        if unknown:
            raise ConductorToolError(f"{PAUSE_VERDICT}: unexpected argument(s) {unknown}")
        async with write_lock:
            return await asyncio.to_thread(_verdict_sync, role, arguments, queue_db_path)
    if tool_id == PAUSE_VERDICT_READ:
        if role != REPORTER_ROLE:
            raise ConductorToolError(f"{PAUSE_VERDICT_READ}: only the conductor may read pause verdicts")
        unknown = sorted(set(arguments) - {"since_id"})
        if unknown:
            raise ConductorToolError(f"{PAUSE_VERDICT_READ}: unexpected argument(s) {unknown}")
        async with write_lock:
            return await asyncio.to_thread(_verdict_read_sync, arguments, queue_db_path)
    if tool_id != CONDUCTOR_REPORT:  # pragma: no cover -- server routes only known ids here
        raise AssertionError(f"conductor_tools.call: unknown native tool id {tool_id!r}")
    if role != REPORTER_ROLE:
        raise ConductorToolError(f"{CONDUCTOR_REPORT}: only the conductor may report runs")
    unknown = sorted(set(arguments) - _FIELDS)
    if unknown:
        raise ConductorToolError(
            f"{CONDUCTOR_REPORT}: unexpected argument(s) {unknown}; accepts only {sorted(_FIELDS)}"
        )
    async with write_lock:
        return await asyncio.to_thread(_report_sync, arguments, queue_db_path)
