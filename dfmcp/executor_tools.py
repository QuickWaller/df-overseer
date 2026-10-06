"""The conductor's executor tools (`docs/CONDUCTOR-EXECUTION.md` section 6.3).

Ids-only native tools the conductor, which is code and never a model, calls to
open a project from an accepted ruling, run one step, observe it, close it, and
sweep legacy work at a cutover. **Nothing here is reachable by a model**: every
tool is `executor_only` (a load-time rule in `dfmcp/roles.py` grants it only to a
role of kind `system`) and every handler refuses any role but the conductor.

Why not `TOOLS.yaml`: like `queue.*` and `conductor.report` these call no DFHack
command of their own; they read and write `dfqueue`'s database through its
store API (`dfqueue/store.py`, stage 2A). `run_step`, `observe` and
`cleanup_project` do reach DFHack, through an injected `call_tool`, never
through `Roster.check` (server bookkeeping on the conductor's behalf, the same
reason `queue_tools._stamp_cycle_snapshot` bypasses it).

Registered through `dfmcp/conductor_tools.py`'s `NATIVE_TOOLS` (so every place
that merges the conductor's native tools picks these up) and routed by
`dfmcp/server.py` ahead of `conductor_tools.call`.

Deploy 2a ships only `queue.close_legacy`, `queue.cutover` and the read
`queue.execution_state`; they touch no game state and make no DFHack call.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from dfqueue import routing, schema as dq_schema, store

from . import executor_run as run
from .queue_tools import QueueToolError

EXECUTOR_ROLE = "conductor"

QUEUE_CLOSE_LEGACY = "queue.close_legacy"
QUEUE_CUTOVER = "queue.cutover"
QUEUE_EXECUTION_STATE = "queue.execution_state"

#: Short reasons written onto the `close` records of a sweep, so the public
#: Board shows why old work was closed.
LEGACY_CLOSE_REASON = "closed at the executor cutover; re-file as an exact action if still wanted"

SUMMARY_MAX = 120


@dataclass(frozen=True)
class NativeTool:
    """Duck-typed like `dfmcp.queue_tools.NativeTool`; `executor_only` is the
    flag `dfmcp/roles.py` reads (only a role of kind `system` may hold it)."""

    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    executor_only: bool = True
    native: bool = True
    args: Tuple[str, ...] = ()

    def describe(self, role: str) -> Tuple[str, dict]:
        del role
        return _DESCRIPTIONS[self.id], _SCHEMAS[self.id]


QUEUE_OPEN_PROJECT = "queue.open_project"
QUEUE_APPLY_FOLLOWUP = "queue.apply_followup"
QUEUE_RUN_STEP = "queue.run_step"
QUEUE_RESOLVE_UNCERTAIN = "queue.resolve_uncertain"
QUEUE_OBSERVE = "queue.observe"
QUEUE_CLEANUP_PROJECT = "queue.cleanup_project"
QUEUE_CLOSE = "queue.close"

_TOOL_IDS = [
    QUEUE_CLOSE_LEGACY, QUEUE_CUTOVER, QUEUE_EXECUTION_STATE,
    QUEUE_OPEN_PROJECT, QUEUE_APPLY_FOLLOWUP, QUEUE_RUN_STEP, QUEUE_RESOLVE_UNCERTAIN,
    QUEUE_OBSERVE, QUEUE_CLEANUP_PROJECT, QUEUE_CLOSE,
]
NATIVE_TOOLS: Dict[str, NativeTool] = {i: NativeTool(id=i) for i in _TOOL_IDS}
NATIVE_TOOL_IDS = tuple(NATIVE_TOOLS)

_DESCRIPTIONS: Dict[str, str] = {}
_SCHEMAS: Dict[str, dict] = {}


def _register(tool_id: str, description: str, properties: dict, required: Tuple[str, ...] = ()) -> None:
    _DESCRIPTIONS[tool_id] = description
    schema: dict = {"type": "object", "additionalProperties": False, "properties": properties}
    if required:
        schema["required"] = list(required)
    _SCHEMAS[tool_id] = schema


_register(
    QUEUE_CLOSE_LEGACY,
    "Conductor only. Close one old ruling, project or pending step-less proposal that is at or "
    "below its cutover, under the executor's name. Writes a `close` record only: it touches no "
    "game state and never calls DFHack. The outcome is computed by the store (completed if the "
    "work was executed, else not_done). Refused above the cutover, with no cutover, or when "
    "already closed.",
    {
        "target_id": {"type": "string", "description": "A ruling-N, project-N or proposal-N id."},
        "reason": {"type": "string", "minLength": 1, "maxLength": 300},
    },
    ("target_id", "reason"),
)

_register(
    QUEUE_CUTOVER,
    "Conductor only. The cutover for a group: `legacy` (every accepted ruling from before the "
    "executor, deploy 2a) or a routing group such as `rooms`. With apply=false it only checks: "
    "lists what a cutover would close and any blockers, and changes nothing. With apply=true and "
    "no blockers it records the cutover at the highest ruling (an already-set cutover is kept) "
    "and closes every target through the same store call as queue.close_legacy, so a crash "
    "resumes. Never calls DFHack and touches no game state.",
    {
        "group": {"type": "string", "description": "`legacy` or a routing group name."},
        "apply": {"type": "boolean", "description": "false (default): check only."},
    },
    ("group",),
)

_register(
    QUEUE_EXECUTION_STATE,
    "Conductor only, read-only. The executor's whole picture in one read: open projects, steps "
    "ready to run now, unresolved (Uncertain) step runs, abandoned projects awaiting cleanup, and "
    "steps observed done after `since` (an observation id; omit for none).",
    {"since": {"type": "string", "description": "An observation id; steps observed done after it are listed."}},
)


_PROJECT_ID = {"type": "string", "description": "A project-N id."}
_STEP_ID = {"type": "string", "description": "A step id such as project-0001/s1."}

_register(
    QUEUE_OPEN_PROJECT,
    "Conductor only. Open the project for an accepted routed proposal's ruling: one step, its own "
    "tracked target, the proposal's tool and exact arguments. Refused for a follow-up, an unrouted "
    "type, a ruling at or below the group's cutover, a closed ruling or one that already has a "
    "project. The project's urgency is the proposal's (normal if it gave none).",
    {"ruling_id": {"type": "string", "description": "A ruling-N id."}},
    ("ruling_id",),
)
_register(
    QUEUE_APPLY_FOLLOWUP,
    "Conductor only. Apply an accepted (or covered) follow-up: one amend carrying the project's "
    "whole plan plus the follow-up's step, which requires the step the follow-up cited.",
    {"proposal_id": {"type": "string", "description": "A proposal-N id of a follow-up."}},
    ("proposal_id",),
)
_register(
    QUEUE_RUN_STEP,
    "Conductor only. Run one step of a project as code, in the fixed order: runnable check, dry run "
    "judged by the tool's declared verdict, landed baseline, a step-run marker, the real call, the "
    "executed record. Returns {class, ...}: success (executed_id, handle), transient (retry next "
    "cycle), waiting (prerequisites issued, not done), needs_judgment (blocked with prerequisites "
    "done, or a reserve's resolution changed), failed (retryable true on the first), uncertain (the "
    "real call was sent and the outcome is unknown; resolve it with queue.resolve_uncertain, never "
    "run it again), not_runnable (reasons). A call that may have been sent is never retried blind.",
    {"project_id": _PROJECT_ID, "step_id": _STEP_ID},
    ("project_id", "step_id"),
)
_register(
    QUEUE_RESOLVE_UNCERTAIN,
    "Conductor only. Settle a step run left `issuing` by reading what the call should have changed "
    "against the baseline taken before it: success (the handle it issued; the step's executed "
    "record is written), transient (nothing landed; the step may run again) or uncertain (the read "
    "was unusable; the run stays unresolved, or is held when hold is true).",
    {
        "run_id": {"type": "integer", "minimum": 1},
        "hold": {"type": "boolean", "description": "Only after repeated unreadable results: block the step."},
    },
    ("run_id",),
)
_register(
    QUEUE_OBSERVE,
    "Conductor only. Read an issued step's progress through its tool's declared progress read and "
    "record one observation. Returns {state: issued|done|stalled|unknown|blocked_material, "
    "observation_id}. Only `done` completes the step (the game says so, not the call).",
    {"project_id": _PROJECT_ID, "step_id": _STEP_ID},
    ("project_id", "step_id"),
)
_register(
    QUEUE_CLEANUP_PROJECT,
    "Conductor only. Abandon cleanup for a project the Overseer abandoned: for each handle it "
    "issued, newest first, the tool declared for that handle's kind withdraws its outstanding "
    "designations or frees its reservation. Dug tiles are never touched. Returns {released, "
    "unreserved, failed}; the project is closed with the results listed once nothing failed.",
    {"project_id": _PROJECT_ID},
    ("project_id",),
)
_register(
    QUEUE_CLOSE,
    "Conductor only. Close a project with a reason (an idle project, or one the proposer passed on). "
    "Writes a `close` record only; touches no game state.",
    {
        "project_id": _PROJECT_ID,
        "outcome": {"type": "string", "enum": list(dq_schema.CLOSE_OUTCOMES)},
        "reason": {"type": "string", "minLength": 1, "maxLength": 300},
    },
    ("project_id", "outcome", "reason"),
)


def _clip(text: Any, cap: int = SUMMARY_MAX) -> str:
    text = str(text if text is not None else "")
    return text if len(text) <= cap else text[: cap - 1] + "…"


def _refuse_role(tool_id: str, role: str) -> None:
    if role != EXECUTOR_ROLE:
        raise QueueToolError(f"{tool_id}: only the conductor may call this tool")


def _reject_unknown(tool_id: str, arguments: Mapping[str, Any]) -> None:
    known = set(_SCHEMAS[tool_id]["properties"])
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise QueueToolError(f"{tool_id}: unexpected argument(s) {unknown}; accepts only {sorted(known)}")


def _require_str(tool_id: str, arguments: Mapping[str, Any], key: str, *, cap: int = 300) -> str:
    v = arguments.get(key)
    if not isinstance(v, str) or not v.strip():
        raise QueueToolError(f"{tool_id}: {key!r} must be a non-empty string")
    return " ".join(v.split())[:cap]


def _store_errors(tool_id: str):
    """Context manager turning store and storage errors into refusals."""
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, et, ev, tb):
            if ev is None:
                return False
            if isinstance(ev, store.QueueError):
                raise QueueToolError(f"{tool_id}: {ev}") from ev
            if isinstance(ev, (sqlite3.Error, OSError)):
                raise QueueToolError(f"{tool_id}: the queue database is unavailable: {ev}") from ev
            return False

    return _Ctx()


# ---------------------------------------------------------------- close_legacy


def _close_legacy_sync(arguments: Mapping[str, Any], db_path: Any) -> Tuple[str, dict]:
    target = _require_str(QUEUE_CLOSE_LEGACY, arguments, "target_id", cap=60)
    reason = _require_str(QUEUE_CLOSE_LEGACY, arguments, "reason")
    with _store_errors(QUEUE_CLOSE_LEGACY):
        rec = store.close_legacy(db_path, target, reason=reason)
    out = {"close_id": rec["id"], "outcome": rec["outcome"], "target_id": target}
    return f"{rec['id']}: {target} closed {rec['outcome']}", out


# ---------------------------------------------------------------- cutover


def _cutover_blockers(db_path: Any, group: str) -> list:
    """Why a cutover cannot be applied now. Only meaningful while no cutover is
    set for the group: once set, applying only resumes the sweep."""
    blockers: list = []
    if store.highest_ruling(db_path) is None:
        blockers.append("there is no ruling to bound the cutover")
    if group != store.LEGACY:
        if routing.groups() and group not in routing.groups():
            blockers.append(f"{group!r} is not a routing group")
            return blockers
        if store.cutover(db_path, store.LEGACY) is None:
            blockers.append("the legacy cutover is not set (deploy 2a comes first)")
        sample = routing.types(group)[0]
        if routing.is_routed(sample):
            blockers.append(f"{group!r} is already routed; its cutover must be set before the flip")
        if not routing.is_frozen(sample):
            blockers.append(f"{group!r} is not frozen; set `frozen: true` and wait for an Overseer wake first")
        runs = store.unresolved_step_runs(db_path)
        if runs:
            blockers.append(f"{len(runs)} step run(s) are unresolved (Uncertain)")
    return blockers


def _cutover_sync(arguments: Mapping[str, Any], db_path: Any) -> Tuple[str, dict]:
    group = _require_str(QUEUE_CUTOVER, arguments, "group", cap=40)
    apply = arguments.get("apply", False)
    if not isinstance(apply, bool):
        raise QueueToolError(f"{QUEUE_CUTOVER}: 'apply' must be true or false")
    with _store_errors(QUEUE_CUTOVER):
        if group != store.LEGACY and group not in routing.groups():
            raise QueueToolError(
                f"{QUEUE_CUTOVER}: {group!r} is not `legacy` or a routing group {routing.groups()}"
            )
        existing = store.cutover(db_path, group)
        blockers = [] if existing is not None else _cutover_blockers(db_path, group)
        targets = store.legacy_targets(db_path, group)
        listing = [
            {"kind": t["kind"], "id": t["id"], "executed": t["executed"], "summary": _clip(t.get("summary"))}
            for t in targets
        ]
        out: Dict[str, Any] = {
            "ok": not blockers, "blockers": blockers, "group": group,
            "cutover_set": existing, "would_close": len(listing), "targets": listing, "applied": False,
        }
        if not apply:
            return f"{group}: {len(listing)} target(s), {len(blockers)} blocker(s); nothing changed", out
        if blockers:
            return f"{group}: not applied, {len(blockers)} blocker(s)", out
        cutover_id = existing
        if cutover_id is None:
            cutover_id = store.highest_ruling(db_path)
            store.set_cutover(db_path, group, cutover_id)
        closed = []
        for t in store.legacy_targets(db_path, group):
            rec = store.close_legacy(db_path, t["id"], reason=LEGACY_CLOSE_REASON)
            closed.append({"id": t["id"], "close_id": rec["id"], "outcome": rec["outcome"]})
        out.update({"cutover_id": cutover_id, "cutover_set": cutover_id, "applied": True,
                    "closed": closed, "would_close": 0, "targets": []})
        return f"{group}: cutover {cutover_id}, {len(closed)} closed", out


# ---------------------------------------------------------------- execution_state


def _execution_state_sync(arguments: Mapping[str, Any], db_path: Any) -> Tuple[str, dict]:
    since = arguments.get("since")
    if since is not None and (not isinstance(since, str) or not since.startswith("observation-")):
        raise QueueToolError(f"{QUEUE_EXECUTION_STATE}: 'since' must be an observation id")
    with _store_errors(QUEUE_EXECUTION_STATE):
        opens = store.open_projects(db_path)
        ready: list = []
        for p in opens:
            if p.get("group") is None or p["group"] not in routing.routed_groups():
                continue
            seen: list = []
            for row in store.target_states(db_path, p["project_id"]):
                if row["step_id"] not in seen:
                    seen.append(row["step_id"])
            for sid in seen:
                if not store.check_step_runnable(db_path, p["project_id"], sid, latched=False):
                    ready.append({"project_id": p["project_id"], "step_id": sid, "urgency": p["urgency"]})
        records = store.load(db_path)
        obs = [r for r in records if r.get("kind") == "observation" and r.get("done") is True]
        latest = max((r["id"] for r in records if r.get("kind") == "observation"),
                     key=store._num, default=None)
        done_since = [
            {"observation_id": r["id"], "project_id": r["project_id"], "step_id": r["step_id"]}
            for r in obs if since is not None and store._num(r["id"]) > store._num(since)
        ]
        out = {
            "open_projects": [
                {k: p[k] for k in ("project_id", "group", "urgency", "status", "steps_open", "phases_remaining")}
                | {"summary": _clip(p.get("summary"))}
                for p in opens
            ],
            "ready_steps": ready,
            "unresolved_runs": store.unresolved_step_runs(db_path),
            "awaiting_cleanup": store.projects_awaiting_cleanup(db_path),
            "done_since": done_since,
            "latest_observation_id": latest,
        }
    return (
        f"{len(opens)} open, {len(ready)} ready, {len(out['unresolved_runs'])} unresolved, "
        f"{len(out['awaiting_cleanup'])} to clean up, {len(done_since)} newly done"
    ), out




# ---------------------------------------------------------------- dispatch

_SYNC = {
    QUEUE_CLOSE_LEGACY: _close_legacy_sync,
    QUEUE_CUTOVER: _cutover_sync,
    QUEUE_EXECUTION_STATE: _execution_state_sync,
}
_READ_ONLY = frozenset({QUEUE_EXECUTION_STATE})
_RUN = {
    QUEUE_OPEN_PROJECT: run.open_project,
    QUEUE_APPLY_FOLLOWUP: run.apply_followup,
    QUEUE_RUN_STEP: run.run_step,
    QUEUE_RESOLVE_UNCERTAIN: run.resolve_uncertain,
    QUEUE_OBSERVE: run.observe,
    QUEUE_CLEANUP_PROJECT: run.cleanup_project,
    QUEUE_CLOSE: run.close_project,
}


async def call(
    tool_id: str, role: str, arguments: Mapping[str, Any], *, db_path: Any,
    write_lock: "asyncio.Lock", call_dfhack: Optional[Any] = None,
    call_tool: Optional[Any] = None, registry: Optional[Any] = None, **_unused: Any,
) -> Tuple[str, Optional[dict]]:
    """Dispatch one executor tool. Raises `QueueToolError` for a refusal.
    `call_tool` and `registry` are needed only by the tools that reach DFHack
    (run_step, resolve_uncertain, observe, cleanup_project)."""
    if tool_id not in _SYNC and tool_id not in _RUN:  # pragma: no cover -- the server routes only known ids here
        raise AssertionError(f"executor_tools.call: unknown tool id {tool_id!r}")
    _refuse_role(tool_id, role)
    _reject_unknown(tool_id, arguments)
    handler = _SYNC.get(tool_id)
    if handler is not None:
        if tool_id in _READ_ONLY:
            return await asyncio.to_thread(handler, arguments, db_path)
        async with write_lock:
            return await asyncio.to_thread(handler, arguments, db_path)
    if call_dfhack is None or call_tool is None or registry is None:
        raise QueueToolError(f"{tool_id}: this server was built without a DFHack route for the executor")
    env = run.ExecEnv(
        db_path=db_path, write_lock=write_lock, call_tool=call_tool, call_dfhack=call_dfhack, registry=registry,
    )
    return await _RUN[tool_id](env, arguments)
