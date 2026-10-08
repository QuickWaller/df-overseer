"""Lane triggers: wake a role only on a change in its own lane.

handoffs/2026-10-05-stricter-wakes.md. Live on 2026-10-05
(`evals/live/2026-10-05-execution-stage-0/`) the advisors woke on nearly every
cycle, each run minutes of mostly reasoning, and the Architect re-proposed
bedrooms already accepted and dug that morning. The rule here: a role wakes
only when something in its own lane changed since its last completed run.

What a lane is, and what it reads, is DATA (`lane_triggers` in
`conductor/policy.yaml`, parsed into `conductor.policy.LaneTriggers`). This
module only evaluates it, generically; there is no per-role branch.

Five kinds of change, each read from something the conductor already
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
- **ore**: ore or gem newly exposed on a dug room's walls
  (`conductor/ore_watch.py`, handoffs/2026-10-05-ore-exposed-signal.md). Edge
  triggered per (site, material): wakes once on first sight; re-arms when the
  pair leaves the read (the vein was mined) or after `ore_renotify_ticks`
  still exposed (the backstop when a proposal was ruled but the vein is still
  there). A site the poll could not read keeps its state, and a failed poll
  is never applied at all.

State that must survive a cycle (alert edge state, proposer map, wakes still
owed to a role whose run has not completed) lives in `lane_state.json` beside
the cursor store, single-writer like `CursorStore`.

Not observable today, and substituted rather than faked: a new landmark (no
landmark read on the conductor's allowlist), approximated by dig and
construction completions in the Architect's own drain. (The author of a graded
prediction used to be unobservable too; `queue.grade` now names the proposer
and a miss wakes only it, `conductor/cycle.py` `_miss_proposers`.)
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from conductor import backoff
from conductor.noble_room_watch import NobleRoomRead
from conductor.ore_watch import OreRead
from conductor.policy import LaneTriggers, Policy
from conductor.triage import LaneWake
from conductor.unsupplied_watch import UnsuppliedRead

LOG = logging.getLogger(__name__)

#: Reasons this module raises; each must exist in policy.yaml `wake_reasons`
#: (its `clock` is read from there, its `wakes` is unused).
REASON_EVENT = "lane_event"
REASON_ALERT = "alert_crossed"
REASON_RULING = "ruling_on_own"
REASON_ORE = "ore_exposed"
REASON_UNSUPPLIED = "unsupplied_building"
REASON_NOBLE_ROOM = "noble_room_unmet"
REASON_ANSWER = "answer_ready"
#: The execute phase's wakes (conductor/execute.py), queued into `pending`
#: under `<reason>:<key>` for the project's proposer.
REASON_STEP_DONE = "step_done"
REASON_STEP_ATTENTION = "step_attention"
REASON_PROJECT_IDLE = "project_idle"

#: `pending` keys: `alert:<name>`, `ruling:<proposal id>`, `ore:<site>:<mineral>`.
_ALERT = "alert:"
_RULING = "ruling:"
_ORE = "ore:"
_UNSUPPLIED = "unsupplied:"
_NOBLE_ROOM = "noble_room:"
_ANSWER = "answer:"


@dataclass
class LaneState:
    #: alert name -> crossed on the last successful read.
    alerts: Dict[str, bool] = field(default_factory=dict)
    #: proposal id -> the advisor whose run added it, until its ruling is seen.
    proposers: Dict[str, str] = field(default_factory=dict)
    #: role -> {key: one-line detail} for wakes owed until that role completes a run.
    pending: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: "<site>:<mineral>" -> game tick it last woke a role, while still exposed.
    ore: Dict[str, int] = field(default_factory=dict)
    #: "<site>:<mineral>" -> wakes sent for it so far (conductor/backoff.py).
    ore_wakes: Dict[str, int] = field(default_factory=dict)
    #: alert name -> backoff record while the alert stays crossed (renotify).
    alert_wakes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: item kind -> {"first": tick first seen unsupplied, "last": tick of its last
    #: wake, "wakes": wakes so far, "stalled": no more wakes}, while unsupplied
    #: (conductor/unsupplied_watch.py).
    unsupplied: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: "<position>:<unit id>:<room kind>" -> the same backoff record, while the
    #: holder lacks that room (conductor/noble_room_watch.py).
    noble_rooms: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: ask id -> the role whose run added it, until its answer is seen.
    askers: Dict[str, str] = field(default_factory=dict)
    #: Conductor cycles seen, persisted: the clock for every cycle-counted
    #: window here (a service restart or a `--once` run must not reset it).
    cycles: int = 0
    #: proposal id -> {"asks": open ask ids when the Overseer last ran and left
    #: it pending, "at": `cycles` then}. The Overseer's wake for a pending
    #: proposal is an edge: see `split_pending_for_overseer`.
    overseer_seen: Dict[str, Dict[str, Any]] = field(default_factory=dict)


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
            ore={str(k): int(v) for k, v in (raw.get("ore") or {}).items()},
            ore_wakes={str(k): int(v) for k, v in (raw.get("ore_wakes") or {}).items()},
            alert_wakes={
                str(k): {"first": int(v.get("first", 0)), "last": int(v.get("last", 0)),
                         "wakes": int(v.get("wakes", 0)), "stalled": bool(v.get("stalled", False))}
                for k, v in (raw.get("alert_wakes") or {}).items() if isinstance(v, dict)
            },
            unsupplied={
                str(k): {"first": int(v.get("first", 0)), "last": int(v.get("last", 0)),
                         "wakes": int(v.get("wakes", 0)), "stalled": bool(v.get("stalled", False))}
                for k, v in (raw.get("unsupplied") or {}).items() if isinstance(v, dict)
            },
            noble_rooms={
                str(k): {"first": int(v.get("first", 0)), "last": int(v.get("last", 0)),
                         "wakes": int(v.get("wakes", 0)), "stalled": bool(v.get("stalled", False))}
                for k, v in (raw.get("noble_rooms") or {}).items() if isinstance(v, dict)
            },
            askers={str(k): str(v) for k, v in (raw.get("askers") or {}).items()},
            cycles=int(raw.get("cycles") or 0),
            overseer_seen={
                str(k): {"asks": [str(a) for a in (v.get("asks") or [])], "at": int(v.get("at", 0))}
                for k, v in (raw.get("overseer_seen") or {}).items() if isinstance(v, dict)
            },
        )

    def save(self, state: LaneState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    {"alerts": state.alerts, "proposers": state.proposers, "pending": state.pending,
                     "ore": state.ore, "unsupplied": state.unsupplied, "noble_rooms": state.noble_rooms,
                     "cycles": state.cycles, "overseer_seen": state.overseer_seen,
                     "ore_wakes": state.ore_wakes, "alert_wakes": state.alert_wakes, "askers": state.askers},
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
    game_tick: Optional[int] = None,
) -> None:
    """Fold this cycle's alert readings into `state`. `crossed[name]` is True,
    False, or None for a failed read (state kept). A fresh crossing adds a
    pending entry for every role whose lane lists the alert; an alert that has
    cleared drops its not-yet-served entries and its backoff record, since the
    condition is gone. An alert that STAYS crossed wakes its owners again on
    the shared renotify backoff (`policy.alert_renotify_ticks`, doubling per
    wake, stalled after `renotify_max_wakes`): a survival signal an owner left
    standing is not forgotten, and not repeated every cycle either. Without a
    game tick the renotify is skipped (the edge alone wakes)."""
    rule = policy.backoff(policy.alert_renotify_ticks)
    for name, now in crossed.items():
        if now is None:
            continue
        was = state.alerts.get(name, False)
        state.alerts[name] = now
        key = _ALERT + name
        due = False
        if now and not was:
            due = True
            if game_tick is not None:
                rec, _, stalled = backoff.advance(None, game_tick, rule)
                state.alert_wakes[name] = rec
        elif now and game_tick is not None:
            rec, due, stalled = backoff.advance(state.alert_wakes.get(name), game_tick, rule)
            state.alert_wakes[name] = rec
            if stalled:
                LOG.info("alert %s still crossed after %d wakes: no more wakes until it clears (stalled)", name, rec["wakes"])
        elif not now:
            state.alert_wakes.pop(name, None)
            for entries in state.pending.values():
                entries.pop(key, None)
        if due:
            for role, lane in policy.lane_triggers.items():
                if name in lane.alerts or "*" in lane.alerts:
                    state.pending.setdefault(role, {})[key] = lines.get(name) or name


def apply_ore_edges(
    policy: Policy, state: LaneState, read: Optional[OreRead], game_tick: Optional[int],
) -> None:
    """Fold one ore poll into `state`. `read=None` (the poll failed) changes
    nothing. A (site, material) seen for the first time, or still exposed
    `policy.ore_renotify_ticks` after it last woke, adds a pending wake for
    every role whose lane has `ore`; one that has left the read (and whose
    site was readable) has been mined, so its state and any wake not yet
    served are dropped and a later exposure wakes afresh."""
    if read is None:
        return
    now = game_tick if game_tick is not None else 0
    rule = policy.backoff(policy.ore_renotify_ticks)
    roles = [role for role, lane in policy.lane_triggers.items() if lane.ore]
    live = set()
    for exp in read.exposures:
        live.add(exp.key)
        last = state.ore.get(exp.key)
        wakes = state.ore_wakes.get(exp.key, 1 if last is not None else 0)
        # Exponential backoff in wakes, stalled after `renotify_max_wakes`; a
        # last-woke tick in the future (a reloaded save) re-arms it
        # (conductor/backoff.py).
        rec = {"first": last, "last": last, "wakes": wakes, "stalled": wakes >= rule.max_wakes} if last is not None else None
        rec, due, newly_stalled = backoff.advance(rec, now, rule)
        if due:
            state.ore[exp.key] = now
            state.ore_wakes[exp.key] = rec["wakes"]
            for role in roles:
                state.pending.setdefault(role, {})[_ORE + exp.key] = exp.line
            if newly_stalled:
                LOG.info("ore %s still exposed after %d wakes: no more wakes until it is mined (stalled)", exp.key, rec["wakes"])
    for key in [k for k in state.ore if k not in live]:
        if key.split(":", 1)[0] in read.unreadable_handles:
            continue
        del state.ore[key]
        state.ore_wakes.pop(key, None)
        for entries in state.pending.values():
            entries.pop(_ORE + key, None)


def apply_unsupplied_edges(
    policy: Policy, state: LaneState, read: Optional[UnsuppliedRead], game_tick: Optional[int],
) -> None:
    """Fold one unsupplied-building poll into `state` (research/2026-10-07-wake-
    audit.md rec 3). `read=None` (the poll failed) changes nothing. An item kind
    seen for the first time wakes every role whose lane has `unsupplied`; while
    it stays unsupplied it wakes again after `base_ticks`, doubling each time up
    to `cap_ticks`, and goes `stalled` (no more wakes) once `max_wakes` wakes
    have been sent. A kind that leaves the read (and was judgeable) is supplied,
    so its state and any wake not yet served are dropped and a later recurrence
    wakes afresh. A kind merely unreadable this poll keeps its state."""
    if read is None:
        return
    pol = policy.unsupplied_building
    rule = backoff.Backoff(pol.base_ticks, pol.cap_ticks, pol.max_wakes)
    now = game_tick if game_tick is not None else 0
    roles = [role for role, lane in policy.lane_triggers.items() if lane.unsupplied]
    live = set()
    for it in read.items:
        live.add(it.key)
        prior = state.unsupplied.get(it.key)
        if prior is not None and prior.get("first", 0) > now:
            prior = None  # a save reload put the clock behind it: start over
        rec, due, _ = backoff.advance(prior, now, rule)
        if prior is None:
            rec["first"] = now
        state.unsupplied[it.key] = rec
        if due:
            for role in roles:
                state.pending.setdefault(role, {})[_UNSUPPLIED + it.key] = it.line(now - rec["first"])
    for key in [k for k in state.unsupplied if k not in live]:
        if key in read.unreadable:
            continue
        del state.unsupplied[key]
        for entries in state.pending.values():
            entries.pop(_UNSUPPLIED + key, None)


def apply_noble_room_edges(
    policy: Policy, state: LaneState, read: Optional[NobleRoomRead], game_tick: Optional[int],
) -> None:
    """Fold one noble-room poll into `state`, the same edge and backoff rule as
    the unsupplied-building wake. `read=None` (the poll failed) changes nothing.
    A (position, holder, kind) seen unmet for the first time wakes every role
    whose lane has `noble_rooms`; it wakes again after `base_ticks`, doubling to
    `cap_ticks`, and stalls after `max_wakes`. An item covered by an open
    assign-owner proposal or step is not woken but keeps its record (so the
    backoff does not restart if the cover lapses). An item that leaves the read
    (met, or the holder changed) loses its state and any wake not yet served;
    one merely unjudgeable this poll keeps it."""
    if read is None:
        return
    pol = policy.noble_room
    rule = backoff.Backoff(pol.base_ticks, pol.cap_ticks, pol.max_wakes)
    now = game_tick if game_tick is not None else 0
    roles = [role for role, lane in policy.lane_triggers.items() if lane.noble_rooms]
    live = set()
    for it in read.items:
        live.add(it.key)
        prior = state.noble_rooms.get(it.key)
        if prior is not None and prior.get("first", 0) > now:
            prior = None  # a save reload put the clock behind it: start over
        if it.unit_id in read.covered_units:
            if prior is not None:
                state.noble_rooms[it.key] = prior
            for entries in state.pending.values():
                entries.pop(_NOBLE_ROOM + it.key, None)
            continue
        rec, due, _ = backoff.advance(prior, now, rule)
        if prior is None:
            rec["first"] = now
        state.noble_rooms[it.key] = rec
        if due:
            for role in roles:
                state.pending.setdefault(role, {})[_NOBLE_ROOM + it.key] = it.line()
    for key in [k for k in state.noble_rooms if k not in live]:
        position_code = key.split(":", 1)[0]
        if key in read.unreadable or position_code in read.unreadable_codes:
            continue
        del state.noble_rooms[key]
        for entries in state.pending.values():
            entries.pop(_NOBLE_ROOM + key, None)


#: How many pending proposals the Overseer's ruling briefing shows (the same
#: cap as `dfmcp.queue_tools.BRIEF_MAX_PROPOSALS`); a pending proposal past it
#: was never put in front of the Overseer, so it is never recorded as seen.
OVERSEER_BRIEF_CAP = 8


def defer_changed(policy: Policy, state: LaneState, seen: Mapping[str, Any], open_ask_ids: Iterable[str]) -> Optional[str]:
    """Why a proposal the Overseer already left pending should be looked at
    again, or None. The one place that defines "changed since the defer":

    - a new answer: an ask that was open at the defer is no longer open;
    - the backstop: `policy.overseer_defer_recheck_cycles` cycles elapsed.

    Not observable by the conductor today, and so not tested here: a new
    citation on the proposal (a proposal record is immutable; the cited facts
    live in `queue.pending_brief`, which costs a read per cycle) and a defer
    that names its own condition (free text in a ruling's reason). Both would
    hook in here."""
    still_open = {str(a) for a in open_ask_ids}
    answered = [a for a in seen.get("asks", ()) if a not in still_open]
    if answered:
        return f"ask {', '.join(answered)} answered since the defer"
    if state.cycles - int(seen.get("at", 0)) >= policy.overseer_defer_recheck_cycles:
        return f"{policy.overseer_defer_recheck_cycles} cycles since the defer"
    return None


def split_pending_for_overseer(
    policy: Policy, state: LaneState, pending_ids: Sequence[str], open_ask_ids: Iterable[str],
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """(wake-worthy, quiet) for the pending proposals. A pending id the
    Overseer has not left pending before is wake-worthy (new); one it has is
    quiet, as `(id, reason)`, unless `defer_changed` finds a reason. The quiet
    list is the seam where a future inbox or notes channel would take a
    deferred proposal as a note instead of dropping it."""
    ask_ids = list(open_ask_ids)
    fresh: List[str] = []
    quiet: List[Tuple[str, str]] = []
    for pid in pending_ids:
        seen = state.overseer_seen.get(str(pid))
        if seen is None:
            fresh.append(str(pid))
            continue
        if defer_changed(policy, state, seen, ask_ids) is not None:
            fresh.append(str(pid))
        else:
            quiet.append((str(pid), "already deferred, nothing changed"))
    return fresh, quiet


def record_overseer_seen(state: LaneState, pending_ids: Sequence[str], open_ask_ids: Iterable[str]) -> None:
    """After an OK Overseer run: the first `OVERSEER_BRIEF_CAP` proposals still
    pending were shown to it and left pending, so they stop waking it until
    `defer_changed`. A proposal past the cap stays wake-worthy. Ids that left
    the pending list are forgotten; one re-woken for a change is re-stamped."""
    ids = [str(p) for p in pending_ids]
    asks = [str(a) for a in open_ask_ids]
    for pid in ids[:OVERSEER_BRIEF_CAP]:
        state.overseer_seen[pid] = {"asks": asks, "at": state.cycles}
    keep = set(ids)
    for pid in [p for p in state.overseer_seen if p not in keep]:
        del state.overseer_seen[pid]


def attribute_new_proposals(
    state: LaneState, role: str, known_ids: Set[str], pending_ids: Iterable[str],
    authors: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    """Learn who filed each pending proposal. With `authors` (the `by_role` map
    `queue.overview` returns: the role recorded on the record, set by the
    server from the caller's credential) each new id goes to its recorded
    author, whichever role's run is finishing, so roles running at once cannot
    swap credit. Without it (an older server) fall back to the diff: every id
    not seen before was added by `role`'s run. Returns the enlarged known set."""
    now = {str(i) for i in pending_ids}
    for pid in sorted(now - known_ids):
        author = authors.get(pid) if authors is not None else role
        if isinstance(author, str) and author:
            state.proposers[pid] = author
    return known_ids | now


def attribute_new_asks(
    state: LaneState, role: str, known_ids: Set[str], open_ask_ids: Iterable[str],
    authors: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    """As `attribute_new_proposals`, for open asks (`state.askers`)."""
    now = {str(i) for i in open_ask_ids}
    for aid in sorted(now - known_ids):
        author = authors.get(aid) if authors is not None else role
        if isinstance(author, str) and author:
            state.askers[aid] = author
    return known_ids | now


def apply_answers(policy: Policy, state: LaneState, open_ask_ids: Iterable[str]) -> None:
    """A learned ask no longer open was answered. Queue one wake for its asker
    when the asker's lane has `answers`. If the asker is also being woken for
    something else this cycle the cycle runs it once (one run per role), so the
    answer arrives with that run; the place a notes channel would take the
    answer instead of a wake is here."""
    now = {str(i) for i in open_ask_ids}
    for aid in [a for a in state.askers if a not in now]:
        role = state.askers.pop(aid)
        lane = _lane(policy, role)
        if lane is not None and lane.answers:
            state.pending.setdefault(role, {})[_ANSWER + aid] = f"{aid} was answered"
        else:
            LOG.info("%s was answered; its asker %s has no answer wake (lane_triggers.%s.answers is off)", aid, role, role)


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
        for prefix, reason in (
            (_ALERT, REASON_ALERT), (_RULING, REASON_RULING), (_ORE, REASON_ORE),
            (_UNSUPPLIED, REASON_UNSUPPLIED), (_NOBLE_ROOM, REASON_NOBLE_ROOM), (_ANSWER, REASON_ANSWER),
            (REASON_STEP_DONE + ":", REASON_STEP_DONE), (REASON_STEP_ATTENTION + ":", REASON_STEP_ATTENTION),
            (REASON_PROJECT_IDLE + ":", REASON_PROJECT_IDLE),
        ):
            details = [v for k, v in sorted(entries.items()) if k.startswith(prefix)]
            if details:
                out.append(LaneWake(reason, "; ".join(details), (role,)))
    return tuple(out)


def add_pending(state: LaneState, role: str, key: str, text: str) -> None:
    """Owe `role` a wake (`key` is `<reason>:<id>`), served when its next run
    completes. Used by the execute phase for the step wakes."""
    state.pending.setdefault(role, {})[key] = text


def clear_served(state: LaneState, role: str) -> None:
    """`role` completed a run: whatever was owed to it is served."""
    state.pending.pop(role, None)
