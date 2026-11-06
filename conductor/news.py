"""News for sessions: which conductor events reach which session, and how.

Spec: `research/2026-10-09-gateway-sessions-v1.md` sections 15.4 and 15.7; register
2026-10-09 "Session layout". Nothing here is a new source of truth: every event is
derived from state the conductor already holds (the lane state's pending wakes, the
execute state's stock-hold notes, the queue's recent rulings, the job watch, the
automine note, alerts, the pause state). This module turns those into
`NewsEvent`s, classifies each (actionable or informational, from policy data), and
says which sessions an event belongs to. `conductor/sessions.py` does the rest.

Classes (policy.yaml `sessions.news`, one entry per kind):

- **actionable** starts a turn of its session in this cycle if the session is idle
  and budget remains (a reject, defer or amend ruling, a failed step, an answered
  ask, a missed prediction, a fort-wide alarm).
- **informational** never starts a turn. It rides the first lines of the session's
  next message, at most `news_max_lines` of them ("and k more" after).
- `last` is actionable only when the event is the last step of its project.
- `urgent` is actionable only when the event is flagged urgent (the stock-hold
  thresholds of register 3a: survival, older than a game day).

News is never sent while a session's turn is in flight (no mid-turn injection was
verified): the sessions engine holds it and delivers it as the first lines of the
session's next message.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from conductor import stock_hold
from conductor.policy import Policy, SessionsPolicy

ACTIONABLE = "actionable"
INFORMATIONAL = "informational"

#: Lane `pending` key prefixes (conductor/lanes.py) and the news kind each is.
_LANE_KIND = {
    "step_done": "step_done",
    "step_attention": "step_attention",
    "project_idle": "step_done",   # every step done: the proposer files the next step or closes it
    "ruling": None,               # decided by the ruling's own decision, see `ruling_kind`
    "answer": "ask_answered",
    "alert": "alarm",
}
#: Lane items that are lane FACTS (drafting material), not news, unless a proposal covers them.
LANE_FACT_PREFIXES = ("ore", "unsupplied", "noble_room")

_PROJECT_RE = re.compile(r"project\s+([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class NewsEvent:
    #: Stable id, the delivery-cursor key (a session never gets the same id twice).
    id: str
    kind: str
    text: str
    #: The open proposal it is about, when it could be resolved. None: fort-wide
    #: or untraceable (never guessed onto a proposal).
    subject: Optional[str] = None
    #: Restrict delivery to this role (the asker of an answered ask).
    role: Optional[str] = None
    #: A fort-wide alarm. `alarm` is the threshold alert's name (matched against a
    #: role lane's `alerts`), `lane` a boolean lane attribute (`ore`) for alarms
    #: that are not alerts; with neither, every role is affected.
    fort_wide: bool = False
    alarm: Optional[str] = None
    lane: Optional[str] = None
    last: bool = False
    urgent: bool = False
    #: Overrides the policy class (an unreadable ruling decision is actionable).
    cls_override: Optional[str] = None
    tick: Optional[int] = None

    def line(self) -> str:
        return f"{self.kind}: {self.text}"


def classify(event: NewsEvent, pol: SessionsPolicy) -> str:
    """`actionable` or `informational`, from policy data and the event's flags."""
    if event.cls_override in (ACTIONABLE, INFORMATIONAL):
        return event.cls_override
    cls = pol.news.get(event.kind, "actionable")
    if cls == "last":
        return ACTIONABLE if event.last else INFORMATIONAL
    if cls == "urgent":
        return ACTIONABLE if event.urgent else INFORMATIONAL
    return cls if cls in (ACTIONABLE, INFORMATIONAL) else ACTIONABLE


# ---- constructors, one per source ----------------------------------------


def project_of(text: str) -> Optional[str]:
    """The project id an execute wake's text names ("project <id> step ..."), or None."""
    m = _PROJECT_RE.search(text or "")
    return m.group(1) if m else None


def ruling_kind(decision: Any) -> Optional[str]:
    """`ruling_<accept|reject|defer|amend>` from a ruling's decision text, or None
    when it cannot be read (the caller then makes the event actionable)."""
    d = str(decision or "").strip().lower()
    for word in ("accept", "reject", "defer", "amend"):
        if d.startswith(word):
            return f"ruling_{word}"
    return None


def lane_item_event(
    key: str, text: str, *, role: str, subject: Optional[str], decisions: Optional[Mapping[str, str]] = None,
    tick: Optional[int] = None,
) -> Optional[NewsEvent]:
    """The news event a lane `pending` entry stands for, or None for a lane FACT
    (`ore:`, `unsupplied:`, `noble_room:`) and anything unrecognised: those are
    drafting items unless a proposal covers them (conductor/sessions.py)."""
    prefix, _, rest = key.partition(":")
    if prefix not in _LANE_KIND:
        return None
    eid = f"lane:{role}:{key}"
    if prefix == "ruling":
        pid = rest
        kind = ruling_kind((decisions or {}).get(pid))
        return NewsEvent(
            eid, kind or "ruling_defer", text or f"{pid} was ruled on", subject=subject or pid, role=role,
            cls_override=None if kind else ACTIONABLE, tick=tick,
        )
    kind = _LANE_KIND[prefix]
    if prefix == "alert":
        return NewsEvent(eid, "alarm", text, subject=None, fort_wide=True, alarm=rest, role=role, tick=tick)
    last = prefix == "project_idle" or (prefix == "step_done" and "declared phase" not in (text or ""))
    return NewsEvent(eid, kind, text, subject=subject, role=role, last=last, tick=tick)


def ruling_events(recent_rulings: Sequence[Mapping[str, Any]], *, tick: Optional[int] = None) -> List[NewsEvent]:
    """One event per recent ruling (`queue.pending_brief` `decided.recent_rulings`:
    `id`, `decision`, `proposal_id`, `reason`), tied to the ruled proposal. A defer
    and an amend never appear in the lane state (the proposal stays pending), so
    this is their only source."""
    out: List[NewsEvent] = []
    for r in recent_rulings or ():
        if not isinstance(r, Mapping) or not r.get("proposal_id"):
            continue
        kind = ruling_kind(r.get("decision"))
        reason = str(r.get("reason") or "").strip()
        out.append(NewsEvent(
            f"ruling:{r.get('id')}", kind or "ruling_defer",
            f"{r['proposal_id']} {r.get('decision')}" + (f": {reason[:240]}" if reason else ""),
            subject=str(r["proposal_id"]), cls_override=None if kind else ACTIONABLE, tick=tick,
        ))
    return out


def hold_events(
    holds: Mapping[str, Mapping[str, Any]], *, tick: Optional[int], policy: Policy,
    subject_of: Mapping[str, str],
) -> List[NewsEvent]:
    """One event per standing stock-hold note (the execute state's `holds`: step id ->
    `{pid, tool, why, since}`), tied to its proposal through `subject_of` (project id
    -> proposal id). `urgent` is the survival and older-than-a-game-day rule of
    register 3a (`stock_hold.wake_kind`); "blocks other steps" is not visible here and
    reads as not urgent. The id includes `since`, so a hold that clears and recurs is
    news again."""
    out: List[NewsEvent] = []
    check = policy.execution.stock_check
    for sid, rec in sorted(holds.items()):
        step = {"tool": rec.get("tool"), "args": {}}
        urgent = False
        if check is not None:
            urgent = stock_hold.wake_kind(check, step, rec, tick, False) is not None
        pid = str(rec.get("pid") or "")
        out.append(NewsEvent(
            f"hold:{sid}:{rec.get('since')}", "stock_hold", stock_hold.hold_line(sid, rec),
            subject=subject_of.get(pid), urgent=urgent, tick=tick,
        ))
    return out


def cavern_event(note: str, *, tick: Optional[int] = None) -> NewsEvent:
    digest = hashlib.sha1(note.encode("utf-8")).hexdigest()[:8]
    return NewsEvent(f"cavern:{digest}", "cavern_breach", note, fort_wide=True, lane="ore", tick=tick)


def stuck_job_events(
    due_jobs: Sequence[Any], *, tick: Optional[int], roles_for: Mapping[str, Sequence[str]],
) -> List[NewsEvent]:
    """A due stuck job (`conductor.job_watch.StuckJob`: `key`, `line`) for the roles whose
    lane claims it. Never tied to a proposal: the conductor cannot trace a job to a step
    (Q8), so it goes to the role's lane, as today."""
    out: List[NewsEvent] = []
    for job in due_jobs:
        key = str(getattr(job, "key", ""))
        for role in roles_for.get(key, ()):
            out.append(NewsEvent(f"stuck:{role}:{key}:{tick}", "stuck_job", str(getattr(job, "line", key)), role=role, tick=tick))
    return out


def miss_events(graded: Sequence[Mapping[str, Any]], *, tick: Optional[int]) -> List[NewsEvent]:
    """A missed prediction (`queue.grade` row `status == graded_false`) for its proposer.
    Tied to its proposal only when the row carries `proposal_id` (today's rows carry the
    prediction id and the proposer only, so it reaches the proposer's lane)."""
    out: List[NewsEvent] = []
    for g in graded or ():
        if not isinstance(g, Mapping) or g.get("status") != "graded_false":
            continue
        pid = g.get("proposal_id")
        out.append(NewsEvent(
            f"miss:{g.get('id')}", "prediction_missed",
            f"prediction {g.get('id')} missed (actual {g.get('actual_value')})",
            subject=str(pid) if pid else None, role=g.get("proposer") if isinstance(g.get("proposer"), str) else None,
            tick=tick,
        ))
    return out


def pause_change_event(was_paused: Optional[bool], now_paused: bool, *, tick: Optional[int], why: str = "") -> Optional[NewsEvent]:
    """A control line when the pause state flipped since the last cycle."""
    if was_paused is None or bool(was_paused) == bool(now_paused):
        return None
    what = "running to paused" if now_paused else "paused to running"
    return NewsEvent(
        f"pause:{tick}:{int(now_paused)}", "pause_change",
        f"FORT CHANGED at tick {tick}: {what}" + (f", {why}" if why else ""), fort_wide=True, tick=tick,
    )


# ---- routing ---------------------------------------------------------------


def affected_roles(event: NewsEvent, policy: Policy, roles: Iterable[str]) -> Tuple[str, ...]:
    """Roles a fort-wide event concerns: those whose lane lists the alarm (`alerts`,
    `"*"` for any) or has the boolean `lane` attribute; with neither, every role in
    `roles`. A role with no lane entry at all is not affected by a named alarm."""
    out: List[str] = []
    for role in roles:
        lane = policy.lane_triggers.get(role)
        if event.alarm is not None:
            ok = lane is not None and (event.alarm in lane.alerts or "*" in lane.alerts)
        elif event.lane is not None:
            ok = lane is not None and bool(getattr(lane, event.lane, False))
        else:
            ok = True
        if ok:
            out.append(role)
    return tuple(out)


def render_lines(events: Sequence[NewsEvent], max_lines: int, pol: SessionsPolicy) -> List[str]:
    """The news block: at most `max_lines` lines, actionable first then in order, the
    rest folded into one "and k more" line."""
    ordered = sorted(events, key=lambda e: 0 if classify(e, pol) == ACTIONABLE else 1)
    lines = [f"- {e.line()}"[:300] for e in ordered[:max_lines]]
    if len(ordered) > max_lines:
        lines.append(f"- and {len(ordered) - max_lines} more")
    return lines
