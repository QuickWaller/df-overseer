"""The execute phase (`docs/CONDUCTOR-EXECUTION.md` 4 and 5, stage 2D).

The conductor acts as code on what the Overseer has ruled for a routed type.
Everything it does is a call to an ids-only `queue.*` executor tool through the
injected tool caller; nothing here names a game tool, a coordinate or a
template. What differs per tool (verdict, handle, progress, landed read, cleanup)
is declared server-side in `TOOLS.yaml`; what is the same for every tool, the
order of a cycle's work and what each outcome means, is here.

One pass, in this order, each step total (a failed call is logged and the pass
goes on; the fort is never put at risk by an exception here):

1. read `queue.execution_state` once;
2. resolve every Uncertain run (`queue.resolve_uncertain`) before anything can
   rerun: a call that may have been sent is read, never retried blind;
3. open the project for each accepted routed ruling, apply each accepted or
   covered follow-up (refused ones are tried a bounded number of times);
4. clean up abandoned projects (`queue.cleanup_project`);
5. reconcile: `queue.observe` each issued step; `done` fires `step_done` once;
   stalled, blocked or repeatedly unreadable goes to the proposer as
   `step_attention`;
6. idle projects: one `project_idle` wake, closed (`completed`, idle) after
   another interval;
7. run ready steps, high urgency first then oldest, at most the policy cap,
   after one quicksave. A finish phase waits while ore shows on its site.

It never touches the clock: the fort is never resumed from here. Whether the
phase may run at all (an owned pause, an escalation, an operator hold without
`allow_execution`) is the caller's rule, in `conductor/cycle.py`.

**What the phase needs from `queue.execution_state`** beyond the 2C contract
(reported as a dfmcp change; every key is optional, and a key that is absent
just means that part of the phase has nothing to do): `to_open` (accepted
routed rulings with no project: `ruling_id`), `to_apply` (accepted or covered
follow-ups not yet applied: `proposal_id`), `issued_steps` (`project_id`,
`step_id`), per open project `role`, per ready step `tool`, `args`.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from conductor.mcp_client import MCPToolError
from conductor.ore_watch import MINE_TOOL, OreRead
from conductor.policy import ExecutionPolicy

LOG = logging.getLogger("conductor.execute")

#: Wake reasons this phase raises (policy.yaml `wake_reasons`) and their keys
#: in `LaneState.pending`.
REASON_DONE = "step_done"
REASON_ATTENTION = "step_attention"
REASON_IDLE = "project_idle"

ToolCall = Callable[[str, Mapping[str, Any]], Awaitable[Any]]

_SENT_KEEP = 400
_TEXT = 300


def _clip(text: Any, cap: int = _TEXT) -> str:
    text = " ".join(str(text if text is not None else "").split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


# ---------------------------------------------------------------- state


@dataclass
class ExecuteState:
    """What must survive a cycle. Single writer, like `LaneStore`."""
    #: Last observation id already read from `done_since`.
    since: Optional[str] = None
    #: Step ids whose `step_done` was sent (once per step).
    sent: List[str] = field(default_factory=list)
    uncertain: Dict[str, int] = field(default_factory=dict)
    transient: Dict[str, int] = field(default_factory=dict)
    unknown: Dict[str, int] = field(default_factory=dict)
    #: step id -> the last attention key sent, so one cause wakes once.
    attention: Dict[str, str] = field(default_factory=dict)
    #: step id -> the materials text a finish step is waiting on.
    ore_held: Dict[str, str] = field(default_factory=dict)
    refused: Dict[str, int] = field(default_factory=dict)
    cleanup_failed: Dict[str, int] = field(default_factory=dict)
    #: project -> {"since": tick, "woke": tick or None}
    idle: Dict[str, Dict[str, Optional[int]]] = field(default_factory=dict)
    #: project -> proposer role, remembered after it leaves the open list.
    roles: Dict[str, str] = field(default_factory=dict)


_FIELDS = ("since", "sent", "uncertain", "transient", "unknown", "attention", "ore_held",
           "refused", "cleanup_failed", "idle", "roles")


class ExecuteStore:
    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> ExecuteState:
        if not self.path.is_file():
            return ExecuteState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{self.path}: expected a JSON object")
        state = ExecuteState()
        for name in _FIELDS:
            if name in raw:
                setattr(state, name, raw[name])
        return state

    def save(self, state: ExecuteState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump({n: getattr(state, n) for n in _FIELDS}, fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


# ---------------------------------------------------------------- report


@dataclass(frozen=True)
class ExecWake:
    """One owed wake for the project's proposer: `reason` is a wake reason,
    `key` its `LaneState.pending` key (so it is served once)."""
    role: str
    reason: str
    key: str
    text: str


@dataclass
class ExecuteReport:
    ran: bool = False
    skipped: Optional[str] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)
    wakes: List[ExecWake] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    steps_run: int = 0

    def act(self, kind: str, **detail: Any) -> None:
        self.actions.append({"kind": kind, **{k: v for k, v in detail.items() if v is not None}})

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ran": self.ran, "skipped": self.skipped, "steps_run": self.steps_run,
            "actions": self.actions, "wakes": [{"role": w.role, "reason": w.reason, "key": w.key} for w in self.wakes],
            "errors": self.errors,
        }


def skipped_report(why: str) -> ExecuteReport:
    return ExecuteReport(ran=False, skipped=why)


# ---------------------------------------------------------------- the phase


class _Phase:
    def __init__(self, call: ToolCall, policy: ExecutionPolicy, state: ExecuteState, *, game_tick: Optional[int],
                 ore_read: Optional[OreRead], quicksave: Optional[Callable[[], Awaitable[Any]]],
                 fallback_roles: Sequence[str], latched: bool):
        self.call, self.pol, self.st = call, policy, state
        self.tick, self.ore, self.quicksave = game_tick, ore_read, quicksave
        self.fallback = tuple(fallback_roles)
        self.latched = latched
        self.report = ExecuteReport(ran=True)
        self.projects: Dict[str, Mapping[str, Any]] = {}
        self.saved = False

    # -- plumbing ----------------------------------------------------------

    async def tool(self, tool_id: str, args: Mapping[str, Any]) -> Optional[Any]:
        try:
            return await self.call(tool_id, dict(args))
        except MCPToolError as exc:
            self.report.errors.append(_clip(f"{tool_id} {sorted(args)}: {exc}", 240))
            LOG.warning("execute: %s failed: %s", tool_id, exc)
            return None
        except Exception as exc:  # noqa: BLE001 -- total: nothing here may stop the cycle
            self.report.errors.append(_clip(f"{tool_id}: {type(exc).__name__}: {exc}", 240))
            LOG.exception("execute: %s raised", tool_id)
            return None

    def roles_for(self, project_id: str) -> Tuple[str, ...]:
        role = (self.projects.get(project_id) or {}).get("role") or self.st.roles.get(project_id)
        return (str(role),) if role else self.fallback

    def wake(self, project_id: str, reason: str, key: str, text: str) -> None:
        for role in self.roles_for(project_id):
            self.report.wakes.append(ExecWake(role, reason, f"{reason}:{key}", _clip(text)))

    def attend(self, project_id: str, step_id: str, cause: str, text: str) -> None:
        """One `step_attention` per (step, cause): the same cause does not wake twice."""
        if self.st.attention.get(step_id) == cause:
            return
        self.st.attention[step_id] = cause
        self.wake(project_id, REASON_ATTENTION, step_id,
                  f"project {project_id} step {step_id}: {text} File a follow-up, or queue.pass naming "
                  f"{project_id} to close it.")
        self.report.act("attention", project=project_id, step=step_id, cause=cause)

    def done(self, project_id: str, step_id: str, detail: str = "") -> None:
        if step_id in self.st.sent:
            return
        self.st.sent.append(step_id)
        del self.st.sent[:-_SENT_KEEP]
        self.st.attention.pop(step_id, None)
        self.st.transient.pop(step_id, None)
        self.st.unknown.pop(step_id, None)
        self.st.ore_held.pop(step_id, None)
        left = (self.projects.get(project_id) or {}).get("phases_remaining")
        tail = f" {left} declared phase(s) left." if isinstance(left, int) and left > 0 else ""
        self.wake(
            project_id, REASON_DONE, step_id,
            f"project {project_id}: step {step_id} is done{(' (' + detail + ')') if detail else ''}.{tail} "
            f"File the next step as a follow-up naming project {project_id} and step {step_id}, or "
            f"queue.pass naming {project_id} to close it.",
        )
        self.report.act("step_done", project=project_id, step=step_id)

    # -- the passes --------------------------------------------------------

    async def read_state(self) -> Optional[Mapping[str, Any]]:
        args: Dict[str, Any] = {}
        if self.st.since:
            args["since"] = self.st.since
        out = await self.tool("queue.execution_state", args)
        if not isinstance(out, Mapping):
            return None
        self.projects = {
            str(p["project_id"]): p for p in (out.get("open_projects") or ())
            if isinstance(p, Mapping) and p.get("project_id")
        }
        for pid, p in self.projects.items():
            if p.get("role"):
                self.st.roles[pid] = str(p["role"])
        return out

    async def resolve_uncertain(self, runs: Sequence[Mapping[str, Any]]) -> int:
        """Settle every unresolved run. Returns how many were attempted."""
        n = 0
        for run in runs:
            rid = run.get("run_id")
            if not isinstance(rid, int):
                continue
            n += 1
            out = await self.tool("queue.resolve_uncertain", {"run_id": rid})
            if not isinstance(out, Mapping):
                continue
            key = str(rid)
            cls = out.get("class")
            pid, sid = str(run.get("project_id") or ""), str(run.get("step_id") or "")
            if cls in ("success", "transient"):
                self.st.uncertain.pop(key, None)
                self.report.act("resolved", run=rid, outcome=cls, handle=out.get("handle"))
                continue
            count = self.st.uncertain.get(key, 0) + 1
            self.st.uncertain[key] = count
            self.report.act("unreadable", run=rid, count=count)
            if count >= self.pol.uncertain_hold_after:
                held = await self.tool("queue.resolve_uncertain", {"run_id": rid, "hold": True})
                if isinstance(held, Mapping) and not sid.startswith("cleanup:"):
                    self.attend(pid, sid, f"uncertain-held:{rid}",
                                f"a call may have run and could not be read back after {count} tries; "
                                f"the step is held.")
        return n

    async def open_and_apply(self, state: Mapping[str, Any]) -> bool:
        changed = False
        for entry in state.get("to_open") or ():
            rid = entry.get("ruling_id") if isinstance(entry, Mapping) else None
            if not isinstance(rid, str) or self.st.refused.get(rid, 0) >= self.pol.refusal_limit:
                continue
            out = await self.tool("queue.open_project", {"ruling_id": rid})
            if isinstance(out, Mapping) and out.get("project_id"):
                changed = True
                self.report.act("opened", ruling=rid, project=out["project_id"])
                if entry.get("role"):
                    self.st.roles[str(out["project_id"])] = str(entry["role"])
            else:
                self.st.refused[rid] = self.st.refused.get(rid, 0) + 1
        for entry in state.get("to_apply") or ():
            pid = entry.get("proposal_id") if isinstance(entry, Mapping) else None
            if not isinstance(pid, str) or self.st.refused.get(pid, 0) >= self.pol.refusal_limit:
                continue
            out = await self.tool("queue.apply_followup", {"proposal_id": pid})
            if isinstance(out, Mapping) and out.get("step_id"):
                changed = True
                self.report.act("applied", proposal=pid, project=out.get("project_id"), step=out["step_id"])
            else:
                self.st.refused[pid] = self.st.refused.get(pid, 0) + 1
        return changed

    async def cleanup(self, state: Mapping[str, Any]) -> None:
        for entry in state.get("awaiting_cleanup") or ():
            pid = entry.get("project_id") if isinstance(entry, Mapping) else None
            if not isinstance(pid, str):
                continue
            out = await self.tool("queue.cleanup_project", {"project_id": pid})
            if not isinstance(out, Mapping):
                self.st.cleanup_failed[pid] = self.st.cleanup_failed.get(pid, 0) + 1
                continue
            failed = out.get("failed") or []
            self.report.act("cleanup", project=pid, released=len(out.get("released") or []),
                            unreserved=len(out.get("unreserved") or []), failed=len(failed),
                            close_id=out.get("close_id"))
            if failed:
                self.st.cleanup_failed[pid] = self.st.cleanup_failed.get(pid, 0) + 1
            else:
                self.st.cleanup_failed.pop(pid, None)

    async def reconcile(self, state: Mapping[str, Any]) -> None:
        for entry in state.get("done_since") or ():
            if isinstance(entry, Mapping) and entry.get("step_id"):
                self.done(str(entry.get("project_id")), str(entry["step_id"]))
        for entry in state.get("issued_steps") or ():
            if not isinstance(entry, Mapping):
                continue
            pid, sid = str(entry.get("project_id") or ""), str(entry.get("step_id") or "")
            if not pid or not sid:
                continue
            out = await self.tool("queue.observe", {"project_id": pid, "step_id": sid})
            if not isinstance(out, Mapping):
                continue
            obs = out.get("state")
            if obs == "done":
                self.done(pid, sid, _clip(out.get("detail"), 80) if out.get("detail") != "already done" else "")
                continue
            if obs == "unknown":
                n = self.st.unknown.get(sid, 0) + 1
                self.st.unknown[sid] = n
                if n >= self.pol.unknown_attention_after:
                    self.attend(pid, sid, "unknown", f"its progress cannot be read ({n} reads in a row): "
                                f"{_clip(out.get('detail'), 120)}.")
                continue
            self.st.unknown.pop(sid, None)
            if obs in ("stalled", "blocked_material"):
                label = "the work has stalled" if obs == "stalled" else "a material it needs is blocked"
                self.attend(pid, sid, obs, f"{label}: {_clip(out.get('detail'), 160)}.")
            elif obs == "issued":
                self.st.attention.pop(sid, None)

    async def idle(self) -> None:
        if self.tick is None:
            return
        live = set()
        for pid, p in self.projects.items():
            waiting = int(p.get("steps_open") or 0) == 0 and int(p.get("phases_remaining") or 0) > 0
            if not waiting:
                continue
            live.add(pid)
            rec = self.st.idle.setdefault(pid, {"since": self.tick, "woke": None})
            if rec["since"] is None or rec["since"] > self.tick:  # a save reload: start over
                rec["since"], rec["woke"] = self.tick, None
            if rec["woke"] is None:
                if self.tick - rec["since"] >= self.pol.idle_wake_ticks:
                    rec["woke"] = self.tick
                    self.wake(pid, REASON_IDLE, pid,
                              f"project {pid} has every step done and nothing filed for "
                              f"{self.pol.idle_wake_ticks // 1200} game days. File the next step as a follow-up, "
                              f"or queue.pass naming {pid} to close it; otherwise it closes in "
                              f"{self.pol.idle_close_ticks // 1200} more.")
                    self.report.act("idle_wake", project=pid)
            elif self.tick - rec["woke"] >= self.pol.idle_close_ticks:
                out = await self.tool("queue.close", {
                    "project_id": pid, "outcome": "completed",
                    "reason": f"idle: every step done and no follow-up for "
                              f"{(self.pol.idle_wake_ticks + self.pol.idle_close_ticks) // 1200} game days",
                })
                if isinstance(out, Mapping) and out.get("close_id"):
                    self.st.idle.pop(pid, None)
                    self.report.act("idle_close", project=pid, close_id=out["close_id"])
        for pid in [p for p in self.st.idle if p not in live]:
            del self.st.idle[pid]  # a follow-up arrived, or the project closed

    def ore_block(self, step: Mapping[str, Any]) -> Optional[Tuple[str, Optional[str]]]:
        """(why, wake text or None) when a finish phase must wait on ore."""
        pat = self.pol.ore_hold_phase
        args = step.get("args") if isinstance(step.get("args"), Mapping) else {}
        phase, site = args.get("phase"), args.get("site")
        if pat is None or not phase or not site or not pat.search(str(phase)):
            return None
        site = str(site)
        if self.ore is None:
            return "the ore read is unavailable", None
        exposed = self.ore.exposed_on(site)
        unknown = self.ore.unclassified.get(site, 0)
        if exposed or unknown:
            mats = ", ".join(f"{e.mineral} ({e.tiles})" for e in exposed) or "unclassified tiles"
            tail = f"; mine with {MINE_TOOL} {site}" if exposed else ""
            return mats, (
                f"waiting on ore: {mats} still shows on {site}'s room walls{tail}. "
                f"It runs again once nothing is exposed."
            )
        if site in self.ore.unreadable_handles:
            return "the site's walls could not be read", None
        return None

    async def run_ready(self, state: Mapping[str, Any]) -> None:
        ready = [r for r in (state.get("ready_steps") or ()) if isinstance(r, Mapping)]
        blocked_projects = {str(r.get("project_id")) for r in (state.get("unresolved_runs") or ()) if isinstance(r, Mapping)}
        order = {u: i for i, u in enumerate(self.pol.urgency_order)}
        indexed = sorted(
            enumerate(ready), key=lambda t: (order.get(str(t[1].get("urgency") or "normal"), len(order)), t[0]),
        )
        quicksaved = False
        for _i, step in indexed:
            if self.report.steps_run >= self.pol.max_steps_per_cycle:
                self.report.act("cap", max=self.pol.max_steps_per_cycle)
                break
            pid, sid = str(step.get("project_id") or ""), str(step.get("step_id") or "")
            if not pid or not sid:
                continue
            if self.latched and str(step.get("urgency") or "normal") != "high":
                continue
            if pid in blocked_projects:
                continue
            block = self.ore_block(step)
            if block is not None:
                why, text = block
                if self.st.ore_held.get(sid) != why:
                    self.st.ore_held[sid] = why
                    if text:
                        self.wake(pid, REASON_ATTENTION, f"{sid}:ore", f"project {pid} step {sid}: {text}")
                self.report.act("ore_hold", project=pid, step=sid, why=why)
                continue
            if sid in self.st.ore_held:
                del self.st.ore_held[sid]
                self.report.act("ore_released", project=pid, step=sid)
            if not quicksaved and self.quicksave is not None:
                quicksaved = True
                try:
                    await self.quicksave()
                except Exception as exc:  # noqa: BLE001 -- a failed save must not hide the phase's other work
                    self.report.errors.append(_clip(f"quicksave: {exc}", 160))
                    LOG.warning("execute: quicksave failed: %s", exc)
            out = await self.tool("queue.run_step", {"project_id": pid, "step_id": sid})
            if not isinstance(out, Mapping):
                continue
            self.report.steps_run += 1
            self.after_run(pid, sid, out)

    def after_run(self, pid: str, sid: str, out: Mapping[str, Any]) -> None:
        cls = out.get("class")
        self.report.act("run", project=pid, step=sid, outcome=cls, handle=out.get("handle"))
        if cls == "success":
            self.st.transient.pop(sid, None)
            self.st.attention.pop(sid, None)
        elif cls == "transient":
            n = self.st.transient.get(sid, 0) + 1
            self.st.transient[sid] = n
            if n >= self.pol.transient_attention_after:
                self.attend(pid, sid, "transient", f"it could not be run {n} times in a row: "
                            f"{_clip(out.get('detail'), 140)}.")
        elif cls == "needs_judgment":
            self.attend(pid, sid, f"judgment:{_clip(out.get('detail'), 60)}",
                        f"it needs your judgment: {_clip(out.get('detail'), 180)}.")
        elif cls == "failed":
            if out.get("retryable") is False:
                self.attend(pid, sid, "failed", f"it failed and will not be retried: {_clip(out.get('detail'), 160)}.")
        elif cls == "uncertain":
            self.report.act("uncertain", project=pid, step=sid, run=out.get("run_id"))
        # waiting, not_runnable: nothing to say; the next cycle looks again.


async def run_execute(
    call: ToolCall, policy: ExecutionPolicy, state: ExecuteState, *, game_tick: Optional[int],
    ore_read: Optional[OreRead] = None, quicksave: Optional[Callable[[], Awaitable[Any]]] = None,
    fallback_roles: Sequence[str] = (), latched: bool = False,
) -> ExecuteReport:
    """One execute pass. `latched`: a tripwire is latched, so only the open,
    apply, resolve and run steps happen and only `high` urgency runs (the
    server refuses any other, 4.5). Mutates `state`; the caller saves it and
    merges `report.wakes` into the lane state."""
    ph = _Phase(call, policy, state, game_tick=game_tick, ore_read=ore_read, quicksave=quicksave,
                fallback_roles=fallback_roles, latched=latched)
    snap = await ph.read_state()
    if snap is None:
        ph.report.skipped = "queue.execution_state could not be read"
        ph.report.ran = False
        return ph.report
    if await ph.resolve_uncertain(snap.get("unresolved_runs") or ()):
        snap = await ph.read_state() or snap
    if await ph.open_and_apply(snap):
        snap = await ph.read_state() or snap
    if not latched:
        await ph.cleanup(snap)
        await ph.reconcile(snap)
        await ph.idle()
    latest = snap.get("latest_observation_id")
    if isinstance(latest, str):
        state.since = latest
    await ph.run_ready(snap)
    return ph.report
