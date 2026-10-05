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
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from dfqueue import runs

CONDUCTOR_REPORT = "conductor.report"
NATIVE_TOOL_IDS = (CONDUCTOR_REPORT,)

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
        return _DESCRIPTION, _SCHEMA


NATIVE_TOOLS: Dict[str, NativeTool] = {CONDUCTOR_REPORT: NativeTool(id=CONDUCTOR_REPORT)}

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
