"""The executor's run machinery: `queue.run_step`, `queue.resolve_uncertain`,
`queue.observe`, `queue.cleanup_project`, `queue.open_project`,
`queue.apply_followup`, `queue.close`, and the filing checks `queue.propose`
applies to a routed step (`docs/CONDUCTOR-EXECUTION.md` 2.2 and 4).

Nothing here names a tool. What differs per tool (how its dry run is judged,
which field is the handle it issued, how progress and an Uncertain call are
read, how a handle is cleaned up) is declared in `TOOLS.yaml` and read through
`dfmcp/action_data.py`. This module owns what is the same for every tool: the
order of a run, and what each outcome class means.

DFHack is reached only through the injected `ExecEnv.call_tool`, which raises:

- `CallNotSent`: failed before the command could have been sent (safe to retry);
- `CallOutcomeUnknown`: the command may have run (timeout, dropped connection,
  output that is not JSON); never retried blind;
- `CallFailed`: DFHack itself reported the command failed.

A real call that raises anything but `CallNotSent` leaves its `step_runs` row
`issuing`, which is what makes the outcome Uncertain and resolvable later.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

from dfqueue import routing, schema as dq_schema, store

from . import action_data as ad
from .queue_tools import QueueToolError, _stamp_cycle_snapshot

#: Per-read bounds for DFHack calls. A tool legitimately takes 45 to 80 s under
#: load while the pool's default is 10 s; the dry run shares the design's 60 s
#: filing bound and the real call gets twice that (the 300 s cap is stage 6).
DRY_RUN_TIMEOUT_SECONDS = 60.0
REAL_CALL_TIMEOUT_SECONDS = 120.0
READ_TIMEOUT_SECONDS = 60.0

DETAIL_MAX = 240


class CallNotSent(Exception):
    """The call failed before the command could have been sent."""


class CallOutcomeUnknown(Exception):
    """The command may have run; no usable result came back."""


class CallFailed(Exception):
    """DFHack reported the command failed (RPC failure)."""


CallTool = Callable[..., Awaitable[Dict[str, Any]]]
CallDFHack = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


@dataclass
class ExecEnv:
    db_path: Any
    write_lock: "asyncio.Lock"
    call_tool: CallTool
    call_dfhack: CallDFHack
    registry: Any
    _specs: Dict[str, Optional[ad.ExecSpec]] = field(default_factory=dict)

    def spec(self, tool_id: str) -> Optional[ad.ExecSpec]:
        if tool_id not in self._specs:
            try:
                tool = self.registry.get(tool_id)
            except KeyError:
                self._specs[tool_id] = None
            else:
                self._specs[tool_id] = ad.spec_for(tool)
        return self._specs[tool_id]


# ---------------------------------------------------------------- store access


def _err(tool_id: str, exc: BaseException) -> QueueToolError:
    if isinstance(exc, store.QueueError):
        return QueueToolError(f"{tool_id}: {exc}")
    return QueueToolError(f"{tool_id}: the queue database is unavailable: {exc}")


async def _w(env: ExecEnv, tool_id: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """A store call off the event loop, under the one write lock."""
    try:
        async with env.write_lock:
            return await asyncio.to_thread(fn, *args, **kwargs)
    except (store.QueueError, sqlite3.Error, OSError) as exc:
        raise _err(tool_id, exc) from exc


async def _r(env: ExecEnv, tool_id: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except (store.QueueError, sqlite3.Error, OSError) as exc:
        raise _err(tool_id, exc) from exc


def _clip(text: Any, cap: int = DETAIL_MAX) -> str:
    text = " ".join(str(text if text is not None else "").split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def current_steps(records: List[dict], project_id: str) -> List[dict]:
    """The project's current plan: the latest amend's steps, else the project's."""
    steps: List[dict] = []
    for r in records:
        if r.get("kind") == "project" and r.get("id") == project_id:
            steps = r.get("steps") or []
    for r in records:
        if r.get("kind") == "amend" and r.get("project_id") == project_id:
            steps = r.get("steps") or []
    return steps


def _by_id(records: List[dict]) -> Dict[str, dict]:
    return {r["id"]: r for r in records if isinstance(r.get("id"), str)}


# ---------------------------------------------------------------- open / follow-up / close


async def open_project(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    ruling_id = _need(QUEUE_OPEN, arguments, "ruling_id")
    records = await _r(env, QUEUE_OPEN, store.load, env.db_path)
    idx = _by_id(records)
    ruling = idx.get(ruling_id)
    proposal = idx.get((ruling or {}).get("proposal_id") or "")
    # The Overseer's ruling sets the urgency; else the proposal's, else normal.
    urgency = (ruling or {}).get("urgency") or ((proposal or {}).get("preview") or {}).get("urgency")
    rec = await _w(env, QUEUE_OPEN, store.open_project_from_ruling, env.db_path, ruling_id, urgency=urgency)
    out = {"project_id": rec["id"], "step_ids": [s["id"] for s in rec["steps"]], "urgency": rec.get("urgency", "normal")}
    return f"{rec['id']} opened from {ruling_id}", out


async def apply_followup(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    pid = _need(QUEUE_FOLLOWUP, arguments, "proposal_id")
    rec = await _w(env, QUEUE_FOLLOWUP, store.apply_followup, env.db_path, pid)
    status = await _r(env, QUEUE_FOLLOWUP, store.project_status, env.db_path, rec["project_id"])
    out = {"project_id": rec["project_id"], "version": status["version"], "step_id": (rec.get("adds") or [None])[0]}
    return f"{out['step_id']} added to {rec['project_id']}", out


async def close_project(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    pid = _need(QUEUE_CLOSE_, arguments, "project_id")
    outcome = _need(QUEUE_CLOSE_, arguments, "outcome")
    reason = _need(QUEUE_CLOSE_, arguments, "reason")
    if not pid.startswith("project-"):
        raise QueueToolError(f"{QUEUE_CLOSE_}: 'project_id' must be a project-N id")
    rec = await _w(env, QUEUE_CLOSE_, store.close, env.db_path, target_id=pid, outcome=outcome, reason=reason)
    return f"{rec['id']}: {pid} closed {outcome}", {"close_id": rec["id"]}


QUEUE_OPEN = "queue.open_project"
QUEUE_FOLLOWUP = "queue.apply_followup"
QUEUE_RUN = "queue.run_step"
QUEUE_RESOLVE = "queue.resolve_uncertain"
QUEUE_OBSERVE_ = "queue.observe"
QUEUE_CLEANUP = "queue.cleanup_project"
QUEUE_CLOSE_ = "queue.close"


def _need(tool_id: str, arguments: Mapping[str, Any], key: str) -> str:
    v = arguments.get(key)
    if not isinstance(v, str) or not v.strip():
        raise QueueToolError(f"{tool_id}: {key!r} must be a non-empty string")
    return v.strip()


# ---------------------------------------------------------------- run_step


async def _tripwire_latched(env: ExecEnv) -> bool:
    """Is a tripwire latched? An unreadable clock counts as latched: a high
    urgency step still runs, every other waits."""
    try:
        status = await env.call_dfhack("clock.status", {})
    except Exception:
        return True
    return bool(isinstance(status, Mapping) and status.get("tripwire"))


def _result(cls: str, **kw: Any) -> Tuple[str, dict]:
    out = {"class": cls, **{k: v for k, v in kw.items() if v is not None}}
    return f"{cls}: {out.get('detail') or out.get('reasons') or ''}".strip(": "), out


async def run_step(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    pid = _need(QUEUE_RUN, arguments, "project_id")
    sid = _need(QUEUE_RUN, arguments, "step_id")

    # (1) runnable
    latched = await _tripwire_latched(env)
    reasons = await _r(env, QUEUE_RUN, store.check_step_runnable, env.db_path, pid, sid, latched=latched)
    records = await _r(env, QUEUE_RUN, store.load, env.db_path)
    steps = current_steps(records, pid)
    step = next((s for s in steps if s.get("id") == sid), None)
    if reasons:
        if step is not None and reasons == ["the step's prerequisites are not done"]:
            states = {}
            for row in await _r(env, QUEUE_RUN, store.target_states, env.db_path, pid):
                states.setdefault(row["step_id"], []).append(row["state"])
            reqs = step.get("requires") or []
            if reqs and all(set(states.get(r, [])) == {dq_schema.ISSUED} for r in reqs):
                return _result("waiting", reasons=reasons, detail="a prerequisite is issued, not done")
        return _result("not_runnable", reasons=reasons)
    assert step is not None
    tool = step["tool"]
    args = dict(step.get("args") or {})
    spec = env.spec(tool)
    if spec is None:
        return _result("needs_judgment", detail=f"{tool} declares no execution data (TOOLS.yaml execution:)")
    proposal_id = step["proposal_id"]
    ctx = {**args, "proposal_id": proposal_id}
    proposal = _by_id(records).get(proposal_id, {})

    # (2) dry run
    try:
        dry_args = {**ad.apply_append(spec, args, ctx), ad.DRY_RUN_ARG: "true"}
        dry = await env.call_tool(tool, dry_args, timeout=DRY_RUN_TIMEOUT_SECONDS)
    except (CallNotSent, CallOutcomeUnknown, CallFailed) as exc:
        return _result("transient", detail=f"the dry run could not be completed: {_clip(exc)}")
    verdict = ad.judge(spec, dry, dry=True)
    if verdict.kind != "ok":
        await _record_attention(env, pid, sid, verdict.reason, records)
        return _result("needs_judgment", detail=_clip(verdict.reason), verdict=verdict.kind)
    if spec.resolution_fields:
        now, missing = ad.resolution(spec, dry)
        was = (proposal.get("preview") or {}).get("resolution") or {}
        changed = {k: {"was": was.get(k), "now": now.get(k)} for k in spec.resolution_fields
                   if k in was and was.get(k) != now.get(k)}
        if missing or changed:
            reason = f"the resolution changed since filing: {changed}" if changed else f"declared field(s) absent: {missing}"
            await _record_attention(env, pid, sid, reason, records)
            return _result("needs_judgment", detail=_clip(reason), changed=changed or None)

    # (3) baseline, tick, marker
    entry = ad.landed_entry(spec, args)
    baseline: Any = {}
    if entry is not None:
        try:
            parsed = await env.call_tool(*(_split(ad.landed_request(entry, ctx))), timeout=READ_TIMEOUT_SECONDS)
        except (CallNotSent, CallOutcomeUnknown, CallFailed) as exc:
            return _result("transient", detail=f"the landed baseline could not be read: {_clip(exc)}")
        baseline = ad.landed_baseline(entry, parsed, ctx)
        if baseline is None:
            return _result("transient", detail="the landed baseline read was unusable; a call that could "
                           "not be resolved afterwards is not sent")
    try:
        tick, _snap = await _stamp_cycle_snapshot(env.call_dfhack)
    except QueueToolError as exc:
        return _result("transient", detail=_clip(exc))
    try:
        run_id = await _w(env, QUEUE_RUN, store.begin_step_run, env.db_path, pid, sid, tick=tick, baseline=baseline)
    except QueueToolError as exc:
        return _result("not_runnable", reasons=[_clip(exc, 400)])

    # (4) the real call. From here on, anything but "not sent" leaves the row issuing.
    real_args = {**ad.apply_append(spec, args, ctx), ad.DRY_RUN_ARG: "false"}
    try:
        out = await env.call_tool(tool, real_args, timeout=REAL_CALL_TIMEOUT_SECONDS)
    except CallNotSent as exc:
        try:
            await _w(env, QUEUE_RUN, store.resolve_step_run, env.db_path, run_id, "transient",
                     tick=tick, notes="the call was never sent")
        except Exception:
            return _result("uncertain", run_id=run_id, detail=f"not sent ({_clip(exc)}) but the marker could not be voided")
        return _result("transient", run_id=run_id, detail=f"the call was never sent: {_clip(exc)}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _result("uncertain", run_id=run_id, detail=f"the call may have run: {_clip(exc)}")

    # (5) judge and record
    try:
        verdict = ad.judge(spec, out, dry=False)
        if verdict.ok:
            handle = ad.issued_handle(spec, out)
            if spec.issues_handle and handle is None:
                return _result("uncertain", run_id=run_id, detail="the call reported success but no handle")
            executed = {
                "actions": [{
                    "tool": tool, "outcome": dq_schema.SUCCESS, "detail": _clip(f"{tool} issued {handle or 'done'}"),
                    "targets": [sid], "target_state": dq_schema.ISSUED,
                    **({"game_refs": [handle]} if handle else {}),
                }],
                "notes": f"run {run_id} of {sid}",
            }
            fin = await _w(env, QUEUE_RUN, store.finish_step_run, env.db_path, run_id, executed, handle=handle)
            return _result("success", run_id=run_id, executed_id=fin["executed"]["id"], handle=handle,
                           detail=f"{tool} issued {handle or 'done'}")
        if verdict.kind == "refused" and ad.nothing_applied(spec, out) is True:
            prior = [r for r in await _r(env, QUEUE_RUN, store.step_runs, env.db_path, pid, sid)
                     if r["status"] == "recorded" and r["outcome"] == "failure"]
            final = len(prior) >= 1
            action: Dict[str, Any] = {"tool": tool, "outcome": dq_schema.FAILURE, "detail": _clip(verdict.reason)}
            if final:
                action.update({"targets": [sid], "target_state": dq_schema.FAILED})
            fin = await _w(env, QUEUE_RUN, store.finish_step_run, env.db_path, run_id,
                           {"actions": [action], "notes": f"run {run_id} of {sid} refused: {_clip(verdict.reason, 120)}"})
            return _result("failed", run_id=run_id, executed_id=fin["executed"]["id"],
                           retryable=not final, detail=_clip(verdict.reason))
        return _result("uncertain", run_id=run_id,
                       detail=_clip(f"the call returned an unclear result ({verdict.kind}: {verdict.reason})"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _result("uncertain", run_id=run_id, detail=f"the result could not be recorded: {_clip(exc)}")


def _obs(state: str, observation_id: Optional[str], detail: str, *, recorded: bool) -> Tuple[str, dict]:
    out = {"state": state, "observation_id": observation_id, "detail": _clip(detail), "recorded": recorded}
    return f"{state}: {out['detail']}", out


def _split(req: Tuple[str, Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    return req


async def _record_attention(env: ExecEnv, pid: str, sid: str, reason: str, records: List[dict]) -> None:
    """Write one `contradicted` observation for a step that needs judgment, unless
    the latest one for it already says the same. Best effort: never fails a run."""
    reason = _clip(reason, 200) or "blocked"
    last = next((r for r in reversed(records) if r.get("kind") == "observation"
                 and r.get("project_id") == pid and r.get("step_id") == sid), None)
    if last is not None and (last.get("results") or [{}])[0].get("reason") == reason:
        return
    try:
        tick, _ = await _stamp_cycle_snapshot(env.call_dfhack)
        await _w(env, QUEUE_RUN, store.record_observation, env.db_path, pid, sid, tick=tick, done=False,
                 detail={"status": dq_schema.OBS_CONTRADICTED, "reason": reason})
    except Exception:
        pass


# ---------------------------------------------------------------- resolve_uncertain


async def resolve_uncertain(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    run_id = arguments.get("run_id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise QueueToolError(f"{QUEUE_RESOLVE}: 'run_id' must be a positive integer")
    hold = arguments.get("hold", False)
    if not isinstance(hold, bool):
        raise QueueToolError(f"{QUEUE_RESOLVE}: 'hold' must be true or false")
    row = await _r(env, QUEUE_RESOLVE, store.get_step_run, env.db_path, run_id)
    if row["status"] != "issuing":
        raise QueueToolError(f"{QUEUE_RESOLVE}: run {run_id} is {row['status']!r}, not unresolved")
    try:
        tick, _ = await _stamp_cycle_snapshot(env.call_dfhack)
    except QueueToolError:
        tick = row["tick"]
    pid, sid = row["project_id"], row["step_id"]
    if sid.startswith(store.CLEANUP_PREFIX):
        # An abandon cleanup call is idempotent (an already-withdrawn handle answers "no site"):
        # voiding the marker just lets the next cleanup pass redo it.
        await _w(env, QUEUE_RESOLVE, store.resolve_step_run, env.db_path, run_id, "transient", tick=tick,
                 notes="cleanup call outcome unknown; it is idempotent and will be redone")
        return _result("transient", detail="a cleanup call is idempotent; it will be redone")
    records = await _r(env, QUEUE_RESOLVE, store.load, env.db_path)
    step = next((s for s in current_steps(records, pid) if s.get("id") == sid), None)
    spec = env.spec(step["tool"]) if step else None
    entry = ad.landed_entry(spec, step.get("args") or {}) if spec and step else None
    if entry is None:
        return await _stay_or_hold(env, run_id, tick, hold, "the tool declares no landed read")
    ctx = {**(step.get("args") or {}), "proposal_id": step["proposal_id"]}
    try:
        parsed = await env.call_tool(*ad.landed_request(entry, ctx), timeout=READ_TIMEOUT_SECONDS)
    except (CallNotSent, CallOutcomeUnknown, CallFailed) as exc:
        return await _stay_or_hold(env, run_id, tick, hold, f"the landed read failed: {_clip(exc)}")
    kind, handle = ad.landed_resolve(entry, row["baseline"], parsed, ctx)
    if kind == "success":
        await _w(env, QUEUE_RESOLVE, store.resolve_step_run, env.db_path, run_id, "success", handle, tick=tick)
        return _result("success", handle=handle, run_id=run_id, detail=f"it landed: {handle}")
    if kind == "nothing":
        await _w(env, QUEUE_RESOLVE, store.resolve_step_run, env.db_path, run_id, "transient", tick=tick,
                 notes="nothing landed")
        return _result("transient", run_id=run_id, detail="nothing landed; the step may run again")
    return await _stay_or_hold(env, run_id, tick, hold, "the landed read could not tell")


async def _stay_or_hold(env: ExecEnv, run_id: int, tick: int, hold: bool, why: str) -> Tuple[str, dict]:
    if hold:
        await _w(env, QUEUE_RESOLVE, store.resolve_step_run, env.db_path, run_id, "held", tick=tick, notes=why)
        return _result("uncertain", run_id=run_id, held=True, detail=f"held: {why}")
    return _result("uncertain", run_id=run_id, held=False, detail=why)


# ---------------------------------------------------------------- observe


async def observe(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    pid = _need(QUEUE_OBSERVE_, arguments, "project_id")
    sid = _need(QUEUE_OBSERVE_, arguments, "step_id")
    records = await _r(env, QUEUE_OBSERVE_, store.load, env.db_path)
    step = next((s for s in current_steps(records, pid) if s.get("id") == sid), None)
    if step is None:
        raise QueueToolError(f"{QUEUE_OBSERVE_}: {sid!r} is not a step of {pid!r}")
    states = [r["state"] for r in await _r(env, QUEUE_OBSERVE_, store.target_states, env.db_path, pid)
              if r["step_id"] == sid]
    if states and all(s == dq_schema.DONE for s in states):
        return _obs("done", None, "already done", recorded=False)
    if not states or any(s != dq_schema.ISSUED for s in states):
        raise QueueToolError(f"{QUEUE_OBSERVE_}: {sid!r} is {sorted(set(states)) or 'untracked'}, not issued")
    spec = env.spec(step["tool"])
    if spec is None:
        raise QueueToolError(f"{QUEUE_OBSERVE_}: {step['tool']} declares no execution data")
    handles = [r["handle"] for r in await _r(env, QUEUE_OBSERVE_, store.step_runs, env.db_path, pid, sid)
               if r["handle"] and r["status"] in ("recorded", "resolved")]
    handle = handles[-1] if handles else None
    tick, _ = await _stamp_cycle_snapshot(env.call_dfhack)
    read_vals: Dict[str, Any] = {}
    if spec.progress is None:
        judged = ad.judge_progress(spec, {})
    else:
        try:
            req = ad.progress_request(spec, {**(step.get("args") or {}), "handle": handle})
        except ad.ActionDataError as exc:
            req, judged = None, {"state": "unknown", "done": None, "reason": str(exc)}
        if req is not None:
            try:
                out = await env.call_tool(req[0], req[1], timeout=READ_TIMEOUT_SECONDS)
            except (CallNotSent, CallOutcomeUnknown, CallFailed) as exc:
                judged = {"state": "unknown", "done": None, "reason": f"the progress read failed: {_clip(exc)}"}
            else:
                judged = ad.judge_progress(spec, out)
                p = spec.progress
                conds = [c for c in (p.get("not_done_if"), p.get("stalled_if"), p.get("blocked_if"), p.get("cancelled_if")) if c]
                for path in [p["done_field"]] + [c["path"] for c in conds]:
                    f, v = ad.get_path(out, path)
                    if f and (v is None or isinstance(v, (bool, int, float, str))):
                        read_vals[path] = v
    state = judged["state"]
    last = next((r for r in reversed(records) if r.get("kind") == "observation"
                 and r.get("project_id") == pid and r.get("step_id") == sid), None)
    last_state = ((last or {}).get("detail") or {}).get("state")
    if state != "done" and last is not None and last_state == state:
        return _obs(state, last["id"], judged["reason"], recorded=False)
    status = {"done": dq_schema.OBS_CONSISTENT, "issued": dq_schema.OBS_CONSISTENT,
              "unknown": dq_schema.OBS_NOT_OBSERVABLE}.get(state, dq_schema.OBS_CONTRADICTED)
    detail = {"status": status, "reason": _clip(judged["reason"], 200), "state": state, "read": read_vals}
    rec = await _w(env, QUEUE_OBSERVE_, store.record_observation, env.db_path, pid, sid, tick=tick,
                   done=state == "done", detail=detail)
    return _obs(state, rec["id"], judged["reason"], recorded=True)


# ---------------------------------------------------------------- cleanup_project


async def cleanup_project(env: ExecEnv, arguments: Mapping[str, Any]) -> Tuple[str, dict]:
    pid = _need(QUEUE_CLEANUP, arguments, "project_id")
    waiting = {p["project_id"]: p for p in await _r(env, QUEUE_CLEANUP, store.projects_awaiting_cleanup, env.db_path)}
    if pid not in waiting:
        raise QueueToolError(f"{QUEUE_CLEANUP}: {pid!r} is not an abandoned routed project awaiting cleanup")
    tick, _ = await _stamp_cycle_snapshot(env.call_dfhack)
    # A cleanup call left unresolved by an earlier pass is idempotent: void it and redo.
    for run in await _r(env, QUEUE_CLEANUP, store.unresolved_step_runs, env.db_path):
        if run["project_id"] == pid and run["step_id"].startswith(store.CLEANUP_PREFIX):
            await _w(env, QUEUE_CLEANUP, store.resolve_step_run, env.db_path, run["run_id"], "transient", tick=tick,
                     notes="redoing an idempotent cleanup call")
    groups: Dict[str, List[str]] = {}
    failed: List[dict] = []
    cleanup_log: List[dict] = []
    for handle in reversed(waiting[pid]["handles"]):
        found = ad.cleanup_for(env.registry, handle)
        if found is None:
            failed.append({"handle": handle, "detail": "no cleanup declared for this kind of handle"})
            continue
        tool, cargs, spec = found
        marker = store.CLEANUP_PREFIX + handle
        try:
            run_id = await _w(env, QUEUE_CLEANUP, store.begin_step_run, env.db_path, pid, marker, tick=tick, baseline=None)
        except QueueToolError as exc:
            failed.append({"handle": handle, "tool": tool, "detail": _clip(exc)})
            continue
        entry: Dict[str, Any] = {"handle": handle, "tool": tool}
        try:
            out = await env.call_tool(tool, cargs, timeout=REAL_CALL_TIMEOUT_SECONDS)
        except CallNotSent as exc:
            await _w(env, QUEUE_CLEANUP, store.resolve_step_run, env.db_path, run_id, "transient", tick=tick)
            failed.append({**entry, "detail": f"never sent: {_clip(exc)}"})
            continue
        except Exception as exc:  # may have run: leave the marker; the next pass redoes it
            failed.append({**entry, "detail": f"outcome unknown: {_clip(exc)}"})
            continue
        err = ad.error_text(out)
        already = err is not None and any(m in err for m in spec.cleanup.get("already_done_if_error_contains") or ())  # type: ignore[union-attr]
        verdict = ad.judge(spec, out, dry=False) if err is None else None
        if already or (verdict is not None and verdict.ok):
            detail = "already gone" if already else "done"
            if isinstance(out, Mapping) and out.get("skipped_phases"):
                detail += f"; planned buildings and zones left behind: {list(out['skipped_phases'])}"
            await _w(env, QUEUE_CLEANUP, store.finish_step_run, env.db_path, run_id,
                     {"actions": [{"tool": tool, "outcome": dq_schema.SUCCESS}]})
            groups.setdefault(spec.cleanup.get("report_as") or "released", []).append(handle)  # type: ignore[union-attr]
            cleanup_log.append({**entry, "outcome": "already_gone" if already else "done", "detail": _clip(detail)})
        else:
            why = err or (verdict.reason if verdict else "unclear result")
            await _w(env, QUEUE_CLEANUP, store.finish_step_run, env.db_path, run_id,
                     {"actions": [{"tool": tool, "outcome": dq_schema.FAILURE, "detail": _clip(why)}]})
            failed.append({**entry, "detail": _clip(why)})
    close_id = None
    if not failed:
        rec = await _w(env, QUEUE_CLEANUP, store.close, env.db_path, target_id=pid, outcome=dq_schema.CLOSE_ABANDONED,
                       reason="abandoned; reserved and designated work released, dug tiles left as they are",
                       cleanup=cleanup_log or None, tick=tick)
        close_id = rec["id"]
    out_d = {"released": groups.get("released", []), "unreserved": groups.get("unreserved", []),
             "failed": failed, "close_id": close_id}
    return f"{pid}: {len(cleanup_log)} cleaned, {len(failed)} failed", out_d
