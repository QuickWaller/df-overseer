"""The per-tool checks `queue.propose` makes on a routed step
(`docs/CONDUCTOR-EXECUTION.md` 2.2 items 1 to 3, 5 and 6, and the coverage test
of section 5). The store checks structure (`dfqueue/store.py`
`_check_proposal_routing`); everything that needs the tool's declared data, the
template or the game is here, and none of it names a tool: it reads
`TOOLS.yaml`'s `execution:` blocks through `dfmcp/action_data.py`.

`queue.propose` calls `check_filing` once per step proposal, after the cited
facts are read and before the record is written. A refusal writes nothing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from dfqueue import routing, schema as dq_schema, store

from . import action_data as ad
from .executor_run import (
    DRY_RUN_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS, CallFailed, CallNotSent, CallOutcomeUnknown,
    ExecEnv, _by_id, _clip, _r, current_steps,
)
from .queue_tools import QueueToolError

#: The proposal does not have an id until the store assigns one, so the dry run
#: (which only has to prove the argument is acceptable, e.g. the purpose still
#: fits its length bound) uses this stand-in for the text the server appends.
PLACEHOLDER_PROPOSAL_ID = "proposal-0000"


def _fail(problems: List[str]) -> QueueToolError:
    return QueueToolError("queue.propose: refused: " + "; ".join(problems))


def _bounded_preview(preview: Dict[str, Any]) -> Dict[str, Any]:
    """Keep a preview inside the schema's size bound, dropping the bulkiest
    detail first (the verdict and the resolution always stay)."""
    limit = dq_schema.PREVIEW_MAX - 200

    def size(p: Dict[str, Any]) -> int:
        return len(json.dumps(p, sort_keys=True, ensure_ascii=False))

    if size(preview) <= limit:
        return preview
    fields = dict(preview.get("fields") or {})
    for key in sorted(fields, key=lambda k: -len(json.dumps(fields[k]))):
        fields.pop(key)
        preview = {**preview, "fields": fields, "trimmed": True}
        if size(preview) <= limit:
            break
    return preview


async def check_filing(
    env: ExecEnv, role: str, record: Mapping[str, Any], urgency: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns the server-set fields to add to the record (`preview`, and
    `covered_by` when coverage is on and the follow-up is exactly the next
    declared phase) or raises `QueueToolError` listing why it was refused. A
    type that is not routed returns `{}`: the store gives the freeze or
    "not routed yet" message."""
    from .tools import ArgumentError, argv_for_call

    del role
    ptype = record.get("type")
    group = routing.group_of(ptype) if isinstance(ptype, str) else None
    if group is None or not routing.is_routed(ptype) or "step" not in record:
        return {}
    step = record["step"]
    tool, args = step["tool"], dict(step.get("args") or {})
    if tool not in routing.tools(group):
        raise _fail([f"{tool!r} is not a tool of group {group!r}"])
    spec = env.spec(tool)
    if spec is None:
        raise _fail([f"{tool} declares no verdict (TOOLS.yaml execution:), so it cannot be proposed as a step"])

    # 2: arguments
    problems: List[str] = []
    if urgency is not None and urgency not in dq_schema.URGENCIES:
        problems.append(f"urgency {urgency!r} is not in {dq_schema.URGENCIES}")
    for k in args:
        if k.lower() == ad.DRY_RUN_ARG:
            problems.append("`dry_run` is set by the server, never by a proposal")
        if k.lower() in spec.override_args:
            problems.append(f"{k!r} is an override argument; steps may not use it")
    if problems:
        raise _fail(problems)

    # 6: cited handles
    follow = record.get("project_id")
    for name in spec.handle_args:
        v = args.get(name)
        if not isinstance(v, str):
            continue
        if follow:
            issued = await _r(env, "queue.propose", store.issued_handles, env.db_path, follow)
            if v not in issued:
                problems.append(
                    f"{name}={v!r}: a follow-up cites a handle its own project issued ({issued or 'none yet'})")
        elif ad.HANDLE_RE.match(v):
            for p in await _r(env, "queue.propose", store.open_projects, env.db_path):
                if v in await _r(env, "queue.propose", store.issued_handles, env.db_path, p["project_id"]):
                    problems.append(f"{name}={v!r} was issued by open project {p['project_id']}; "
                                    "file a follow-up on it instead")
    if problems:
        raise _fail(problems)

    # 2 (continued) and 3: the call as the executor will make it, dry
    ctx = {**args, "proposal_id": PLACEHOLDER_PROPOSAL_ID}
    call_args = {**ad.apply_append(spec, args, ctx), ad.DRY_RUN_ARG: "true"}
    try:
        argv_for_call(env.registry.get(tool), call_args)
    except ArgumentError as exc:
        raise _fail([str(exc)]) from exc
    try:
        dry = await env.call_tool(tool, call_args, timeout=DRY_RUN_TIMEOUT_SECONDS)
    except (CallNotSent, CallOutcomeUnknown, CallFailed) as exc:
        raise QueueToolError(
            f"queue.propose: server busy, file again (the dry run of {tool} could not be completed: "
            f"{_clip(exc)}; nothing was written)") from exc
    verdict = ad.judge(spec, dry, dry=True)
    if verdict.kind == "refused":
        raise _fail([f"the dry run of {tool} was refused: {_clip(verdict.reason, 300)}"])
    if verdict.kind == "invalid":
        raise _fail([f"the dry run of {tool} gave an unusable result ({_clip(verdict.reason, 300)}); "
                     "this is a tool-data problem for the operator, not a fault in your arguments"])
    resolution, missing = ad.resolution(spec, dry)
    if missing:
        raise _fail([f"the dry run is missing declared field(s) {missing}"])
    fields: Dict[str, Any] = {}
    for path in spec.preview_fields:
        found, value = ad.get_path(dry, path)
        if found:
            fields[path] = value
    preview: Dict[str, Any] = {
        "verdict": "ok", "summary": f"dry run of {tool} passed", "tick": record.get("cycle"), "fields": fields,
    }
    if resolution:
        preview["resolution"] = resolution
    if urgency is not None:
        preview["urgency"] = urgency

    # 5: declared phases
    phases = record.get("phases")
    if phases:
        pspec = env.spec(phases["tool"])
        if pspec is None or not pspec.phases:
            raise _fail([f"{phases['tool']} declares no phase source, so phases cannot be declared for it"])
        absent = [a for a in pspec.phases["carry"] if args.get(a) is None]
        if absent:
            raise _fail([f"phases carry {absent} from the step's arguments, which has none"])
        try:
            plan_tool, plan_args = ad.plan_request(pspec, args)
            plan = ad.plan_phases(pspec, await env.call_tool(plan_tool, plan_args, timeout=READ_TIMEOUT_SECONDS))
        except (CallNotSent, CallOutcomeUnknown, CallFailed) as exc:
            raise QueueToolError(
                f"queue.propose: server busy, file again (the template's phases could not be read: "
                f"{_clip(exc)})") from exc
        except ad.ActionDataError as exc:
            raise _fail([f"the template's phases could not be read: {exc}"]) from exc
        first = args.get(pspec.phases["arg"]) if tool == phases["tool"] else None
        bad = ad.check_declared_phases(plan, list(phases["list"]), first)
        if bad:
            raise _fail(bad)

    updates: Dict[str, Any] = {"preview": _bounded_preview(preview)}
    if follow and routing.coverage_on(ptype):
        covered = await _covered_by(env, record, args)
        if covered:
            updates["covered_by"] = covered
    return updates


async def _covered_by(env: ExecEnv, record: Mapping[str, Any], args: Mapping[str, Any]) -> Optional[str]:
    """Section 5: a follow-up is covered when it has the same proposer role, the
    declared phases tool, exactly the carried arguments, the next declared phase,
    a handle this project issued, and `after_step` is the done step of the
    previous declared phase. Returns `after_step` when covered."""
    pid = record["project_id"]
    records = await _r(env, "queue.propose", store.load, env.db_path)
    idx = _by_id(records)
    project = idx.get(pid)
    root = idx.get(idx.get((project or {}).get("from_ruling", ""), {}).get("proposal_id", ""))
    if not project or not root or root.get("role") != record.get("role") or not root.get("phases"):
        return None
    declared = root["phases"]
    pspec = env.spec(declared["tool"])
    if record["step"]["tool"] != declared["tool"] or pspec is None or not pspec.phases:
        return None
    root_args = (root.get("step") or {}).get("args") or {}
    if any(args.get(a) != root_args.get(a) for a in pspec.phases["carry"]):
        return None
    steps = current_steps(records, pid)
    n = len(steps) - 1
    if n >= len(declared["list"]) or args.get(pspec.phases["arg"]) != declared["list"][n]:
        return None
    issued = await _r(env, "queue.propose", store.issued_handles, env.db_path, pid)
    if args.get(pspec.phases["site_arg"]) not in issued:
        return None
    last = steps[-1]["id"]
    if record.get("after_step") != last:
        return None
    states = [r["state"] for r in await _r(env, "queue.propose", store.target_states, env.db_path, pid)
              if r["step_id"] == last]
    return last if states and all(s == dq_schema.DONE for s in states) else None
