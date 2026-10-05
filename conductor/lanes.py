"""Lane triggers: wake a role only on a change in its own lane.

handoffs/2026-10-05-stricter-wakes.md. Live on 2026-10-05
(`evals/live/2026-10-05-execution-stage-0/`) the advisors woke on nearly every
cycle, each run minutes of mostly reasoning, and the Architect re-proposed
bedrooms already accepted and dug that morning. The rule here: a role wakes
only when something in its own lane changed since its last completed run.

What a lane is, and what it reads, is DATA (`lane_triggers` in
`conductor/policy.yaml`, parsed into `conductor.policy.LaneTriggers`). This
module only evaluates it, generically; there is no per-role branch.

Four kinds of change, each read from something the conductor already
observes:

- **events**: the role's OWN `diff.since` drain (the per-role cursor is
  exactly "since its last completed run"), matched on event type and an
  optional regex over the event's detail.
- **stuck jobs**: a job the stuck-job watch found due, matched by regex over
  its type and description.
- **alerts**: a threshold alert crossing from clear to crossed. Edge
  triggered: a crossed alert wakes once, and again only after it has cleared
  and re-crossed. A failed read keeps the last known state rather than
  reading as "cleared".
- **rulings**: a proposal this role filed leaving the pending list. The
  conductor cannot read a proposal's author, so it learns it by watching
  which advisor's run added a pending proposal id (`attribute_new_proposals`).

State that must survive a cycle (alert edge state, proposer map, wakes still
owed to a role whose run has not completed) lives in `lane_state.json` beside
the cursor store, single-writer like `CursorStore`.

Not observable today, and substituted rather than faked: a new landmark (no
landmark read on the conductor's allowlist), approximated by dig and
construction completions in the Architect's own drain; the author of a graded
prediction (`queue.grade` omits it), so a miss wakes both advisors.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from conductor.policy import LaneTriggers, Policy
from conductor.triage import LaneWake

#: Reasons this module raises; each must exist in policy.yaml `wake_reasons`
#: (its `clock` is read from there, its `wakes` is unused).
REASON_EVENT = "lane_event"
REASON_ALERT = "alert_crossed"
REASON_RULING = "ruling_on_own"

#: `pending` keys: `alert:<name>`, `ruling:<proposal id>`.
_ALERT = "alert:"
_RULING = "ruling:"


@dataclass
class LaneState:
    #: alert name -> crossed on the last successful read.
    alerts: Dict[str, bool] = field(default_factory=dict)
    #: proposal id -> the advisor whose run added it, until its ruling is seen.
    proposers: Dict[str, str] = field(default_factory=dict)
    #: role -> {key: one-line detail} for wakes owed until that role completes a run.
    pending: Dict[str, Dict[str, str]] = field(default_factory=dict)


class LaneStore:
    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> LaneState:
        if not self.path.is_file():
            return LaneState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{self.path}: expected a JSON object")
        return LaneState(
            alerts={str(k): bool(v) for k, v in (raw.get("alerts") or {}).items()},
            proposers={str(k): str(v) for k, v in (raw.get("proposers") or {}).items()},
            pending={
                str(r): {str(k): str(v) for k, v in (m or {}).items()}
                for r, m in (raw.get("pending") or {}).items()
            },
        )

    def save(self, state: LaneState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    {"alerts": state.alerts, "proposers": state.proposers, "pending": state.pending},
                    fh, indent=2, sort_keys=True,
                )
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def _lane(policy: Policy, role: str) -> Optional[LaneTriggers]:
    return policy.lane_triggers.get(role)


def event_matches(policy: Policy, role: str, events: Iterable[Mapping[str, Any]]) -> List[str]:
    """One short line per drained event that is a change in `role`'s lane."""
    lane = _lane(policy, role)
    if lane is None:
        return []
    lines: List[str] = []
    for event in events:
        etype = event.get("type") or event.get("announcement")
        detail = str(event.get("detail") or "")
        for rule in lane.events:
            if rule.type != etype:
                continue
            if rule.detail_matches and not any(p.search(detail) for p in rule.detail_matches):
                continue
            lines.append(f"{etype}: {detail}" if detail else str(etype))
            break
    return lines


def stuck_job_roles(policy: Policy, due_jobs: Sequence[Any]) -> Tuple[str, ...]:
    """Roles whose lane claims at least one of `due_jobs` (objects with `key`
    and `line`, i.e. `conductor.job_watch.StuckJob`). A job no lane claims
    wakes nobody; the routine review is its backstop."""
    roles: List[str] = []
    for role, lane in policy.lane_triggers.items():
        if not lane.stuck_jobs:
            continue
        for job in due_jobs:
            text = f"{getattr(job, 'key', '')} {getattr(job, 'line', '')}"
            if any(p.search(text) for p in lane.stuck_jobs):
                roles.append(role)
                break
    return tuple(roles)


def apply_alert_edges(
    policy: Policy, state: LaneState, crossed: Mapping[str, Optional[bool]], lines: Mapping[str, str],
) -> None:
    """Fold this cycle's alert readings into `state`. `crossed[name]` is True,
    False, or None for a failed read (state kept). A fresh crossing adds a
    pending entry for every role whose lane lists the alert; an alert that has
    cleared drops its not-yet-served entries, since the condition is gone."""
    for name, now in crossed.items():
        if now is None:
            continue
        was = state.alerts.get(name, False)
        state.alerts[name] = now
        key = _ALERT + name
        if now and not was:
            for role, lane in policy.lane_triggers.items():
                if name in lane.alerts or "*" in lane.alerts:
                    state.pending.setdefault(role, {})[key] = lines.get(name) or name
        elif not now:
            for entries in state.pending.values():
                entries.pop(key, None)


def attribute_new_proposals(state: LaneState, role: str, known_ids: Set[str], pending_ids: Iterable[str]) -> Set[str]:
    """After `role`'s run: every pending proposal id not seen before was added
    by that run. Records the author and returns the enlarged known set."""
    now = {str(i) for i in pending_ids}
    for pid in sorted(now - known_ids):
        state.proposers[pid] = role
    return known_ids | now


def apply_rulings(policy: Policy, state: LaneState, pending_ids: Iterable[str]) -> None:
    """A learned proposal no longer pending was ruled (accept or reject; a
    deferral stays pending). Queue the wake for its author, once."""
    now = {str(i) for i in pending_ids}
    for pid in [p for p in state.proposers if p not in now]:
        role = state.proposers.pop(pid)
        lane = _lane(policy, role)
        if lane is not None and lane.rulings:
            state.pending.setdefault(role, {})[_RULING + pid] = f"{pid} was ruled on"


def lane_wakes(policy: Policy, state: LaneState, events_by_role: Mapping[str, Sequence[Mapping[str, Any]]]) -> Tuple[LaneWake, ...]:
    """One wake per (role, kind) with something in its lane."""
    out: List[LaneWake] = []
    for role in policy.lane_triggers:
        lines = event_matches(policy, role, events_by_role.get(role, ()))
        if lines:
            more = f" (and {len(lines) - 1} more)" if len(lines) > 1 else ""
            out.append(LaneWake(REASON_EVENT, f"{lines[0]}{more}", (role,)))
        entries = state.pending.get(role) or {}
        for prefix, reason in ((_ALERT, REASON_ALERT), (_RULING, REASON_RULING)):
            details = [v for k, v in sorted(entries.items()) if k.startswith(prefix)]
            if details:
                out.append(LaneWake(reason, "; ".join(details), (role,)))
    return tuple(out)


def clear_served(state: LaneState, role: str) -> None:
    """`role` completed a run: whatever was owed to it is served."""
    state.pending.pop(role, None)
