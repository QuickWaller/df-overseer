"""The Planner's derived to-do list (register 2026-10-09, "A work queue for the
Planner"; `evals/live/2026-10-09-post-deploy-cycle/`, which showed the Planner
cannot wake for "the plan is missing something").

Nothing here is stored as a list. Each cycle, after `plan_watch.evaluate`, the
conductor derives items from state that already exists and wakes the Planner
ONCE, with every due item in its briefing:

1. `stage_target_missing`: a target of the fort's current roadmap stage that no
   plan target adopts (`plan.status`'s `roadmap_check.missing`).
2. `target_deviation`: a plan target that differs from its roadmap entry
   (`roadmap_check.deviations`, e.g. a lost `min` floor). An explained
   deviation that only raised the level (`up`) is deliberate and not listed.
3. `unplanned_kind`: a kind the Planner owns (policy `plan.work_queue.
   owned_kinds`, a `sync` kind such as `autofarm`) with no target of it in the
   plan. Data, so the next kind is one policy entry.
4. `open_ask`: an ask addressed to the Planner.
5. Today's wake reasons, folded in: bootstrap, stage entered, season review, a
   `plan_change` ruling, a stalled target (`plan_watch` still decides when each
   is due and backs it off; here they join the one list instead of waking
   separately).

Backoff, per derived item, kept in `plan_watch.json` beside the other watches
(no new file): the item's first sighting wakes; each wake sets the retry
clock's doubling wait (`conductor/backoff.py` `RetryClock` time, so a paused
fort still retries); after `max_wakes` wakes the item is stalled. A Planner
`queue.pass` filed after an item's wake also stops it (the Planner looked and
left it). An item reopens when its signature changes (a different deviation, a
new ask) and starts afresh when it disappears and later recurs.

The operator hold does not gate this: the Planner may run and file under a hold.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from conductor.plan_watch import (
    Backoff, PLANNER, PlanWake, PlanWatchResult, PlanWatchState, REASON_BOOTSTRAP, REASON_REVIEW,
    REASON_RULING, REASON_STAGE, REASON_STALLED, _clip, _due, _note_wake,
)
from conductor.policy import PlanPolicy

REASON_TODO = "plan_todo"

#: Planner wake reasons from `plan_watch.evaluate` that become items instead.
FOLDED = (REASON_BOOTSTRAP, REASON_REVIEW, REASON_RULING, REASON_STAGE, REASON_STALLED)

HEADER = (
    "Your to-do list: {n} item(s), derived this cycle. Handle all of them in this run "
    "(plan.read first, plan.write with a dry run, then queue.pass for any you deliberately leave, "
    "with a reason naming it)."
)

_BACKOFF_FIELDS = tuple(Backoff.__dataclass_fields__)


def _backoff_of(rec: Optional[Mapping[str, Any]]) -> Backoff:
    return Backoff(**{f: rec[f] for f in _BACKOFF_FIELDS if rec and f in rec})


def _derived(status: Mapping[str, Any], wq: Any, ask_ids: Sequence[str]) -> List[Tuple[str, str, str]]:
    """`(key, signature, line)` for items 1 to 4, in that order."""
    out: List[Tuple[str, str, str]] = []
    active = status.get("active") if isinstance(status.get("active"), Mapping) else None
    if active is None:
        return out
    version = active.get("version")
    check = status.get("roadmap_check") if isinstance(status.get("roadmap_check"), Mapping) else None
    if check is not None:
        stage = check.get("stage")
        for ref in check.get("missing") or []:
            out.append((
                f"missing:{ref}", "missing",
                f"stage_target_missing {ref}: the {stage} roadmap entry {ref} is in no target of plan v{version}. "
                f"Adopt it (roadmap_ref {ref}), or pass saying why not.",
            ))
        for d in check.get("deviations") or []:
            if not isinstance(d, Mapping) or not isinstance(d.get("id"), str):
                continue
            reason = d.get("reason") if isinstance(d.get("reason"), str) and d.get("reason") else None
            if reason and d.get("kind") == "up":
                continue
            why = f"its deviation_reason: {reason[:140]}" if reason else "it has no deviation_reason"
            out.append((
                f"deviation:{d['id']}", f"{d.get('kind')}|{reason}",
                f"target_deviation {d['id']}: differs from roadmap entry {d.get('ref')} ({d.get('kind')}); {why}. "
                "Restore it to the entry, or keep it and pass saying why.",
            ))
    rows = [r for r in status.get("targets") or [] if isinstance(r, Mapping)]
    for kind, desc in (getattr(wq, "owned_kinds", None) or {}).items():
        if not [r for r in rows if r.get("sync") == kind and r.get("crop") != "default"]:
            out.append((
                f"kind:{kind}", "none",
                f"unplanned_kind {kind}: plan v{version} has no {desc}. File them, or pass saying why not.",
            ))
    for aid in ask_ids:
        out.append((
            f"ask:{aid}", str(aid),
            f"open_ask {aid}: an ask addressed to you is open (its id is in your queue list). Answer it, or pass saying why not.",
        ))
    return out


def fold(
    result: PlanWatchResult, status: Optional[Mapping[str, Any]], tick: Optional[int], retry_tick: Optional[int],
    policy: PlanPolicy, state: PlanWatchState, planner_asks: Sequence[str] = (),
) -> None:
    """Replace the Planner's separate plan wakes in `result` with one
    `plan_todo` wake carrying them and every due derived item. Mutates `result`
    and `state.todo` only. Does nothing when the work queue is off or `status`
    is unreadable (a failed read never reads as "nothing to do"); with no item
    due the wakes stay as `evaluate` raised them."""
    wq = policy.work_queue
    if not wq.enabled or not isinstance(status, Mapping) or tick is None:
        return
    rt = retry_tick if retry_tick is not None else tick
    base, cap = policy.renotify_ticks, policy.renotify_cap_ticks
    folded = [w for w in result.wakes if w.role == PLANNER and w.reason in FOLDED]
    rest = [w for w in result.wakes if not (w.role == PLANNER and w.reason in FOLDED)]
    cands = _derived(status, wq, [str(a) for a in planner_asks])

    live = {k for k, _, _ in cands}
    for k in [k for k in state.todo if k not in live]:
        del state.todo[k]   # gone: a later recurrence wakes afresh
    pass_tick = status.get("last_pass_tick")

    room = max(0, wq.max_items - len(folded))
    due: List[Tuple[str, str, str]] = []
    for key, sig, line in cands:
        rec = state.todo.get(key)
        if rec is not None and rec.get("sig") != sig:
            rec = None   # its state changed: reopen
            del state.todo[key]
        if rec is not None:
            if int(rec.get("wakes", 0)) > 0 and pass_tick is not None and pass_tick != rec.get("pass_at_wake"):
                rec["stalled"] = True   # the Planner passed after being told: it looked and left it
            if rec.get("stalled") or int(rec.get("wakes", 0)) >= wq.max_wakes:
                continue
            if not _due(_backoff_of(rec), rt, cap):
                continue
        if len(due) < room:
            due.append((key, sig, line))

    for key, sig, _ in due:
        b = _backoff_of(state.todo.get(key))
        _note_wake(b, rt, base, cap)
        b.stalled = b.wakes >= wq.max_wakes
        state.todo[key] = {**asdict(b), "sig": sig, "pass_at_wake": pass_tick}

    lines = [f"[{w.reason}] {w.detail}" for w in folded] + [line for _, _, line in due]
    if not lines:
        return
    detail = HEADER.format(n=len(lines)) + "".join(f"\n{i}. {_clip(t)}" for i, t in enumerate(lines, 1))
    result.wakes = rest + [PlanWake(REASON_TODO, PLANNER, detail, key="todo")]
    result.notes.append(f"work queue: {len(lines)} item(s) listed ({len(folded)} folded wake(s), {len(due)} derived)")
