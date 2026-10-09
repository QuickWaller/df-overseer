"""The Overseer's write tools record an action instead of writing (2026-10-09,
register "Hold scope, settled same day: the conductor is the only writer to the game").

Sixteen tools (`dfqueue/action_tools.yaml` group `direct`) keep their names and
argument schemas for the Overseer. A call that would write now:

1. checks the arguments exactly as the tool would (`argv_for_call`), and, for a
   tool that takes `DRY_RUN`, runs its dry run (a preview that may read the game
   but never writes). A refusal at either step is returned as the tool's own
   error and nothing is recorded;
2. records a `direct_action` proposal and its accepting ruling in one
   transaction (`store.file_direct_action`), one step, the tool and the exact
   arguments the Overseer gave;
3. replies with one line: queued, and it runs after the Overseer's run.

The conductor's execute phase (`conductor/execute.py`) then opens the project
from the ruling and runs the step through `queue.run_step`, the same machinery
as any routed step, after one quicksave and only when no operator hold blocks
execution. So the hold blocks every write, and nothing here ever touches the
game's state.

A call that is a dry run (`dry_run` true, or left at the tool's default of true) is not recorded: it is a preview
and is passed through to the tool as before (`is_preview`).

HOOK, stateless stock check (a separate later build, register 2026-10-09 "stock
checks go stateless"): `_Phase.stock_check` in `conductor/execute.py` is where a
check that the stock a step relies on still holds at execution would run; this
module records nothing it would need.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Mapping, Optional, Tuple

from dfqueue import routing, schema as dq_schema, store

from . import action_data as ad
from .executor_run import (
    DRY_RUN_TIMEOUT_SECONDS, CallFailed, CallNotSent, CallOutcomeUnknown, ExecEnv, _clip,
)
from .queue_tools import QueueToolError, _stamp_cycle_snapshot

#: A short, fixed prediction every direct action carries. The schema requires one;
#: a direct action has no claim of its own to grade, so it claims the fort still has
#: a dwarf in it, which keeps the grader and the metrics working without inventing
#: a verdict on the action. Its type (`direct_action`) is its own bucket.
PREDICTION = {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200}

QUEUED_LINE = (
    "Queued as {proposal_id} (ruled {ruling_id}): the conductor runs {tool} after your run, "
    "so it has not happened yet. Do not file queue.executed for it."
)


def is_direct_tool(tool_id: str, role: str) -> bool:
    """A call to record rather than run: a direct-group tool called by the sole writer."""
    return role == store.sole_writer() and tool_id in routing.direct_tools()


def is_preview(tool: Any, arguments: Mapping[str, Any]) -> bool:
    """Is this call a dry run? A tool with a DRY_RUN argument defaults to the documented
    default (usually true), so a call that does not say `dry_run: false` is a preview and
    is passed through to the tool unchanged: nothing is queued. A tool with no DRY_RUN
    argument is never a preview."""
    if not ad.takes_dry_run(tool):
        return False
    v = arguments.get(ad.DRY_RUN_ARG)
    if v is None:
        v = (getattr(tool, "defaults", {}) or {}).get("DRY_RUN", "true")
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("false", "0", "no", "off")


def _compact_args(args: Mapping[str, Any]) -> str:
    return " ".join(f"{k}={json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}" for k, v in args.items())


async def file_action(
    env: ExecEnv, role: str, tool_id: str, arguments: Mapping[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Validate, preview, record, reply. Raises `QueueToolError` for any refusal,
    with nothing written."""
    from .tools import ArgumentError, argv_for_call

    tool = env.registry.get(tool_id)
    args = {k: v for k, v in dict(arguments or {}).items() if k.lower() != ad.DRY_RUN_ARG}
    # `dry_run` is the server's to set at execution, never part of the recorded step.
    try:
        argv_for_call(tool, args)
    except ArgumentError as exc:
        raise QueueToolError(str(exc)) from exc

    if ad.takes_dry_run(tool):
        try:
            dry = await env.call_tool(tool_id, {**args, ad.DRY_RUN_ARG: "true"}, timeout=DRY_RUN_TIMEOUT_SECONDS)
        except CallFailed as exc:
            raise QueueToolError(str(exc)) from exc
        except (CallNotSent, CallOutcomeUnknown) as exc:
            raise QueueToolError(
                f"{tool_id}: server busy, call again (its dry run could not be completed: {_clip(exc)}; "
                "nothing was queued)") from exc
        spec = env.spec(tool_id) or ad.direct_spec(tool_id, True)
        verdict = ad.judge(spec, dry, dry=True)
        if verdict.kind == "refused":
            raise QueueToolError(verdict.reason)
        if verdict.kind == "invalid":
            raise QueueToolError(f"{tool_id}: its dry run gave an unusable result ({_clip(verdict.reason, 200)}); "
                                 "nothing was queued")

    try:
        tick, snapshot = await _stamp_cycle_snapshot(env.call_dfhack)
    except QueueToolError:
        raise
    summary = _clip(f"{tool_id} {_compact_args(args)}".strip(), 200)
    proposal = {
        "kind": dq_schema.PROPOSAL, "role": role, "cycle": tick, "snapshot": snapshot,
        "type": routing.direct_type(),
        "summary": summary,
        "rationale": f"The Overseer called {tool_id} directly; recorded as a ready-ruled action the conductor runs.",
        "prediction": dict(PREDICTION),
        "cost": {"estimate": 1, "unit": dq_schema.DWARF_TICKS},
        "suggested_priority": 4,
        "preconditions": [],
        "public_title": _clip(tool_id, dq_schema.PUBLIC_TITLE_MAX),
        "public_rationale": "The Overseer acted directly; the conductor carries it out.",
        "step": {"tool": tool_id, "args": args},
    }
    ruling = {
        "kind": dq_schema.RULING, "role": role, "cycle": tick, "snapshot": snapshot,
        "decision": dq_schema.ACCEPT,
        "reason": "A direct call by the Overseer: ruled when made, run by the conductor.",
        "public_rationale": "The Overseer acted directly; the conductor carries it out.",
    }
    try:
        async with env.write_lock:
            prop, rul = await asyncio.to_thread(store.file_direct_action, env.db_path, proposal, ruling,
                                                game_tick=tick)
    except store.QueueError as exc:
        raise QueueToolError(f"{tool_id}: could not be queued: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 -- sqlite3.Error / OSError: the queue database is unavailable
        raise QueueToolError(f"{tool_id}: could not be queued, the queue database is unavailable: {exc}") from exc
    text = QUEUED_LINE.format(proposal_id=prop["id"], ruling_id=rul["id"], tool=tool_id)
    return text, {"queued": True, "proposal_id": prop["id"], "ruling_id": rul["id"], "tool": tool_id}
