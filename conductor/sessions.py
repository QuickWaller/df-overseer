"""Sessions: which Gateway session a piece of work belongs to, when one opens and
closes, and how a cycle's session turns run.

Spec: `research/2026-10-09-gateway-sessions-v1.md` section 15 (it wins over sections
1 to 14), the 2026-10-09 register rows "Session layout: per relevant open proposal",
"Session concurrency: no per-role caps; one adaptive limit on concurrent turns" and
"Overseer bottleneck: batch when busy now". The transport is
`conductor/session_runner.py` (its header documents the interface used here); the
news routing is `conductor/news.py`.

Nothing here runs unless policy `sessions.enabled` is true AND a role is set to
`session` (`SessionsPolicy.mode_of`). Every role defaults to one-shot, so shipping this
changes nothing live.

## The rules, in one place

**Keys.** The Overseer gets `agent:overseer:w<wake>` per wake. Every other role gets
`agent:<role>:p<proposal>` per RELEVANT open proposal (a re-opened one after a size cap
gets an `r<n>` suffix) and `agent:<role>:d<activation>` for a drafting session. A
drafting session that files a proposal is MAPPED to it (`SessionRecord.refs`), never
re-keyed (no session rename exists); one that files nothing is closed at the end of its
activation; one that files several is one session mapped to all of them.

**Relevance** (`relevant_proposals`). A role has a part in a proposal when it filed it, or
an ask or pass carrying that proposal id is addressed to or filed by it. Lane facts that
one of the role's own open proposals covers (typed step identity, policy `covers`) are
news to that proposal's session; the rest are drafting items; no session for a proposal
the role has no part in.

**State.** One small single-writer file, `sessions_state.json` beside the cursor store:
the key map, each session's delivered-news cursor, parked informational news, the ask to
proposal links seen, the id counters and the adaptive limit. Items are NOT stored: they
are derived each cycle from the lane state's pending wakes, the open asks and the
triage wakes (`derive_items`). The one deviation from "derive everything": informational
news is parked (bounded per role) because the lane state would otherwise keep waking the
role for it every cycle.

**Concurrency.** No per-role cap. One adaptive limit on simultaneous model turns
(`TurnLimiter`): lowered one step on a transport loss, a timeout, an errored turn or a slow
turn, raised one step after a run of clean turns, alerted when it ends cycles in a row below
its start. Never two turns on one key. A 1.5 s stagger between same-role turn starts.

**Pipelining.** After every turn of any non-Overseer session the engine re-reads the
pending proposals; anything newly filed goes into the open Overseer session as its next
item, one at a time, or as one batch when `overseer_batch_threshold` or more are waiting.
The Overseer's wait for the last proposer is gone.

**News.** Never sent mid-turn (held; the first lines of the session's next message).
Actionable news starts a turn if budget remains; informational news is batched into the
next message (at most `news_max_lines`). Every activation opens with a fresh vitals line and
"earlier tool results in this session may be out of date; re-read before acting".

**Close and reset.** A proposal that closes closes its sessions. A turn whose prompt passes
`size_cap_tokens` drops the session; the next activation opens a fresh key with a re-brief
built from the queue (never a model-written summary). A proposal session that is new (never
opened under that key) always opens with a re-brief, so a Gateway wipe is recovered the same
way. Run limits per activation are unchanged (the role's own timeout, Overseer 20 minutes);
each turn's `--timeout` is what is left of it.

**Ambiguity.** A `timeout` or `transport_lost` turn may have acted or still be running, so
the same session is never sent to again this phase, the items stay pending (not served),
and after a transport loss no new turns start this phase (carry, spec 7.3).

## What the cycle supplies (`PhaseCtx`)

The engine never reads a tool or builds the role's briefing itself. The cycle hands it
callables for the things only it knows (the one-shot prompt a drafting session starts from,
the Overseer's ruling briefing, the queue re-reads, one bracketed turn with the
`conductor.report` start and end calls). See `PhaseCtx`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from conductor import news as news_mod
from conductor.briefing import format_proposal_lines
from conductor.news import ACTIONABLE, INFORMATIONAL, NewsEvent
from conductor.policy import Policy, SessionsPolicy
from conductor.runner import RunResult
from conductor.session_runner import GatewayHealth, RouteDecision, SessionRunner, decide_route, is_ambiguous
from conductor.triage import LaneWake, OVERSEER, Wake

LOG = logging.getLogger("conductor.sessions")

KIND_PROPOSAL = "proposal"
KIND_DRAFTING = "drafting"
KIND_OVERSEER = "overseer"

#: The fixed line every activation's first message carries (Q9).
STALE_LINE = "Earlier tool results in this session may be out of date; re-read before acting."

#: Wake reasons whose content the lane `pending` entries, the open asks and the news
#: events already carry as items, so they are not a separate drafting item.
ITEMISED_REASONS = frozenset({
    "ruling_on_own", "ore_exposed", "unsupplied_building", "noble_room_unmet", "answer_ready",
    "step_done", "step_attention", "project_idle", "alert_crossed", "open_ask", "session_news",
    "prediction_graded", "stuck_job",
})

#: Statuses that are not a model/transport health signal (config or not launched).
_NEUTRAL_STATUSES = frozenset({"no_budget", "launch_failed", "gateway_auth"})

_DELIVERED_KEEP = 400
_ASK_LINKS_KEEP = 200
_FORT_EVENTS_KEEP = 8


# ---- keys -------------------------------------------------------------------


def short_id(proposal_id: str) -> str:
    return str(proposal_id).removeprefix("proposal-")


def overseer_key(wake_id: int) -> str:
    return f"agent:{OVERSEER}:w{wake_id}"


def proposal_key(role: str, proposal_id: str, generation: int = 0) -> str:
    return f"agent:{role}:p{short_id(proposal_id)}" + (f"r{generation}" if generation else "")


def drafting_key(role: str, activation_id: int) -> str:
    return f"agent:{role}:d{activation_id}"


# ---- state ------------------------------------------------------------------


@dataclass
class SessionRecord:
    key: str
    role: str
    kind: str
    #: Proposal ids this session is mapped to (a drafting session gains one when it files).
    refs: List[str] = field(default_factory=list)
    activation: int = 0
    opened_cycle: int = 0
    turns: int = 0
    #: The last turn's prompt size (input plus cache read), None when unknown.
    prompt_tokens: Optional[int] = None


@dataclass
class SessionState:
    sessions: Dict[str, SessionRecord] = field(default_factory=dict)
    #: "<role>:<proposal id>" -> times its session was dropped (the key suffix).
    generations: Dict[str, int] = field(default_factory=dict)
    #: role -> news ids already delivered (the per-session cursor, by role: an id is
    #: delivered once to a role even if it has several sessions on it).
    delivered: Dict[str, List[str]] = field(default_factory=dict)
    #: role -> informational events waiting for the role's next message.
    parked: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    #: ask id -> proposal id, remembered while the ask was open (an answered ask leaves the queue).
    ask_proposals: Dict[str, str] = field(default_factory=dict)
    activation_counter: int = 0
    wake_counter: int = 0
    limit: int = 0
    clean_turns: int = 0
    lowered_cycles: int = 0
    #: A Gateway outage was alerted and not yet recovered from.
    outage: bool = False
    last_paused: Optional[bool] = None
    #: Control lines noted by cycles that ran no sessions (a tripwire, an unexplained pause).
    fort_events: List[Dict[str, Any]] = field(default_factory=list)

    # -- derived views ----------------------------------------------------

    def for_proposal(self, role: str, proposal_id: str) -> Optional[SessionRecord]:
        for rec in self.sessions.values():
            if rec.role == role and rec.kind != KIND_OVERSEER and proposal_id in rec.refs:
                return rec
        return None

    def sessions_of(self, role: str) -> List[SessionRecord]:
        return [r for r in self.sessions.values() if r.role == role]

    def is_delivered(self, role: str, event_id: str) -> bool:
        return event_id in self.delivered.get(role, ())

    def mark_delivered(self, role: str, event_id: str) -> None:
        ids = self.delivered.setdefault(role, [])
        if event_id not in ids:
            ids.append(event_id)
            del ids[:-_DELIVERED_KEEP]

    def park(self, role: str, event: NewsEvent, cap: int) -> None:
        if self.is_delivered(role, event.id) or any(p.get("id") == event.id for p in self.parked.get(role, ())):
            return
        rows = self.parked.setdefault(role, [])
        rows.append({"id": event.id, "kind": event.kind, "text": event.text, "subject": event.subject, "tick": event.tick})
        del rows[:-cap]

    def next_activation(self) -> int:
        self.activation_counter += 1
        return self.activation_counter

    def next_wake(self) -> int:
        self.wake_counter += 1
        return self.wake_counter


class SessionStore:
    """`sessions_state.json`, single-writer, atomic replace (like `LaneStore`)."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> SessionState:
        if not self.path.is_file():
            return SessionState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{self.path}: expected a JSON object")
        state = SessionState()
        for key, rec in (raw.get("sessions") or {}).items():
            if isinstance(rec, dict):
                state.sessions[str(key)] = SessionRecord(
                    key=str(key), role=str(rec.get("role")), kind=str(rec.get("kind")),
                    refs=[str(r) for r in rec.get("refs") or []], activation=int(rec.get("activation") or 0),
                    opened_cycle=int(rec.get("opened_cycle") or 0), turns=int(rec.get("turns") or 0),
                    prompt_tokens=rec.get("prompt_tokens") if isinstance(rec.get("prompt_tokens"), int) else None,
                )
        state.generations = {str(k): int(v) for k, v in (raw.get("generations") or {}).items()}
        state.delivered = {str(k): [str(i) for i in v] for k, v in (raw.get("delivered") or {}).items()}
        state.parked = {str(k): [dict(p) for p in v if isinstance(p, dict)] for k, v in (raw.get("parked") or {}).items()}
        state.ask_proposals = {str(k): str(v) for k, v in (raw.get("ask_proposals") or {}).items()}
        state.activation_counter = int(raw.get("activation_counter") or 0)
        state.wake_counter = int(raw.get("wake_counter") or 0)
        state.limit = int(raw.get("limit") or 0)
        state.clean_turns = int(raw.get("clean_turns") or 0)
        state.lowered_cycles = int(raw.get("lowered_cycles") or 0)
        state.outage = bool(raw.get("outage", False))
        lp = raw.get("last_paused")
        state.last_paused = lp if isinstance(lp, bool) else None
        state.fort_events = [dict(e) for e in raw.get("fort_events") or [] if isinstance(e, dict)]
        return state

    def save(self, state: SessionState) -> None:
        doc = {
            "sessions": {k: asdict(v) for k, v in state.sessions.items()},
            "generations": state.generations, "delivered": state.delivered, "parked": state.parked,
            "ask_proposals": state.ask_proposals, "activation_counter": state.activation_counter,
            "wake_counter": state.wake_counter, "limit": state.limit, "clean_turns": state.clean_turns,
            "lowered_cycles": state.lowered_cycles, "outage": state.outage, "last_paused": state.last_paused,
            "fort_events": state.fort_events,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def sessions_path_for(cursor_store_path: "Path | str") -> Path:
    return Path(cursor_store_path).with_name("sessions_state.json")


# ---- queue facts ------------------------------------------------------------


@dataclass
class QueueFacts:
    """What the conductor knows about the queue this cycle, parsed tolerantly from
    reads it already makes (`queue.overview`, `queue.execution_state`,
    `queue.pending_brief`) so a key the server does not carry yet just narrows what
    can be matched (degrading to a drafting session or one-shot, never a crash)."""

    #: pending (or deferred) proposal id -> filing role
    proposals: Dict[str, str] = field(default_factory=dict)
    #: open ask id -> {"to": role, "by": role, "proposal_id": id or None}
    asks: Dict[str, Dict[str, Optional[str]]] = field(default_factory=dict)
    #: [(role, proposal id)] for passes that name a proposal
    passes: List[Tuple[str, str]] = field(default_factory=list)
    #: open project id -> {"proposal_id": id or None, "role": role}
    projects: Dict[str, Dict[str, Optional[str]]] = field(default_factory=dict)
    #: live proposals' step calls: {"proposal_id", "tool", "args", ...} (queue.overview open_steps)
    open_steps: List[Mapping[str, Any]] = field(default_factory=list)
    #: proposal id -> latest ruling decision text (queue.pending_brief decided.recent_rulings)
    decisions: Dict[str, str] = field(default_factory=dict)
    recent_rulings: List[Mapping[str, Any]] = field(default_factory=list)
    #: ids of proposals with an open project (resolved through `projects`)
    projects_open: Set[str] = field(default_factory=set)

    @property
    def open_proposals(self) -> Set[str]:
        return set(self.proposals) | self.projects_open

    def proposal_role(self, pid: str) -> Optional[str]:
        return self.proposals.get(pid) or next(
            (p.get("role") for p in self.projects.values() if p.get("proposal_id") == pid and p.get("role")), None,
        )

    def subject_of_project(self) -> Dict[str, str]:
        return {pid: str(p["proposal_id"]) for pid, p in self.projects.items() if p.get("proposal_id")}


def _mapping(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def facts_from_reads(
    queue_state: Optional[Mapping[str, Any]], *, execution_state: Optional[Mapping[str, Any]] = None,
    pending_brief: Optional[Mapping[str, Any]] = None, open_steps: Optional[Sequence[Mapping[str, Any]]] = None,
) -> QueueFacts:
    """Parse `queue.overview` (`proposals.by_role`, `asks.to`/`by_role`, and the optional
    `asks.proposal_ids` / `passes` maps that name a proposal), `queue.execution_state`
    (`open_projects[]`, with an optional `proposal_id`), `queue.pending_brief`
    (`decided.recent_rulings`) and an `open_steps` read. Total."""
    facts = QueueFacts()
    props = _mapping(_mapping(queue_state).get("proposals"))
    by_role = _mapping(props.get("by_role"))
    for pid in props.get("proposal_ids") or ():
        facts.proposals[str(pid)] = str(by_role.get(pid) or "")
    asks = _mapping(_mapping(queue_state).get("asks"))
    to: Dict[str, str] = {}
    for addressee, ids in _mapping(asks.get("to")).items():
        for aid in ids or ():
            to[str(aid)] = str(addressee)
    ask_by = _mapping(asks.get("by_role"))
    ask_prop = _mapping(asks.get("proposal_ids"))
    for aid in asks.get("ask_ids") or ():
        aid = str(aid)
        facts.asks[aid] = {
            "to": to.get(aid) or ("consultant" if not to else None), "by": ask_by.get(aid) if isinstance(ask_by.get(aid), str) else None,
            "proposal_id": str(ask_prop[aid]) if ask_prop.get(aid) else None,
        }
    passes = _mapping(_mapping(queue_state).get("passes"))
    pass_roles = _mapping(passes.get("by_role"))
    for qid, pid in _mapping(passes.get("proposal_ids")).items():
        if pid and isinstance(pass_roles.get(qid), str):
            facts.passes.append((str(pass_roles[qid]), str(pid)))
    for p in _mapping(execution_state).get("open_projects") or ():
        if isinstance(p, Mapping) and p.get("project_id"):
            pid = str(p["proposal_id"]) if p.get("proposal_id") else None
            facts.projects[str(p["project_id"])] = {"proposal_id": pid, "role": p.get("role")}
            if pid:
                facts.projects_open.add(pid)
    decided = _mapping(_mapping(pending_brief).get("decided"))
    for r in decided.get("recent_rulings") or ():
        if isinstance(r, Mapping) and r.get("proposal_id"):
            facts.recent_rulings.append(r)
            facts.decisions.setdefault(str(r["proposal_id"]), str(r.get("decision") or ""))
    facts.open_steps = [r for r in (open_steps or ()) if isinstance(r, Mapping)]
    return facts


def relevant_proposals(role: str, facts: QueueFacts) -> Dict[str, str]:
    """proposal id -> why `role` has a part in it (15.3): `filed`, `asked` (an ask or pass of
    its own names the proposal) or `pulled_in` (an ask addressed to it names the proposal)."""
    out: Dict[str, str] = {}
    for pid, filer in facts.proposals.items():
        if filer == role:
            out[pid] = "filed"
    for pid in facts.projects_open:
        if facts.proposal_role(pid) == role:
            out.setdefault(pid, "filed")
    for ask in facts.asks.values():
        pid = ask.get("proposal_id")
        if not pid:
            continue
        if ask.get("to") == role:
            out.setdefault(pid, "pulled_in")
        elif ask.get("by") == role:
            out.setdefault(pid, "asked")
    for prole, pid in facts.passes:
        if prole == role:
            out.setdefault(pid, "asked")
    return out


def covering_proposal(
    role: str, key: str, pol: SessionsPolicy, facts: QueueFacts,
) -> Optional[str]:
    """The role's OWN open proposal that covers lane item `key` (`<kind>:<rest>`), matched on
    typed step identity per policy `covers`, else None (untyped kinds are never matched)."""
    kind, _, rest = key.partition(":")
    parts = rest.split(":")
    for rule in pol.covers:
        if rule.kind != kind or rule.part >= len(parts):
            continue
        wanted = parts[rule.part]
        for row in facts.open_steps:
            if row.get("tool") != rule.tool:
                continue
            args = _mapping(row.get("args"))
            have = next((v for k, v in args.items() if str(k).lower() == rule.arg.lower()), None)
            pid = row.get("proposal_id")
            if have is not None and str(have) == wanted and pid and facts.proposal_role(str(pid)) in (role, None):
                return str(pid)
    return None


# ---- items and turn plans ---------------------------------------------------


@dataclass(frozen=True)
class Item:
    role: str
    #: Dedupe and serve id: `lane:<key>`, `ask:<id>`, `news:<event id>` or `wake:<reason>`.
    id: str
    source: str            # lane | ask | news | wake
    kind: str
    text: str
    subject: Optional[str] = None
    actionable: bool = True
    #: The lane `pending` key to clear when this item is served.
    lane_key: Optional[str] = None
    event: Optional[NewsEvent] = None


@dataclass
class TurnPlan:
    """One session's work this cycle."""
    role: str
    kind: str
    key: str
    refs: List[str]
    items: List[Item]
    wake: Optional[Wake] = None
    #: No record under this key yet: the first message carries a re-brief (proposal sessions).
    needs_rebrief: bool = False
    activation: int = 0
    generation: int = 0


@dataclass
class PhasePlan:
    turns: List[TurnPlan] = field(default_factory=list)
    overseer: Optional[TurnPlan] = None
    #: Session-mode roles that run one-shot this cycle (an ask with no proposal, say).
    oneshot_roles: List[str] = field(default_factory=list)
    parked_only: List[str] = field(default_factory=list)


def derive_items(
    role: str, *, lane_pending: Mapping[str, str], facts: QueueFacts, state: SessionState, pol: Policy,
    events: Sequence[NewsEvent], wakes: Sequence[Wake],
) -> Tuple[List[Item], bool]:
    """The role's items this cycle, all derived: lane `pending` entries (news kinds become
    news items; lane facts become drafting items, or news to a covering own proposal), open
    asks addressed to the role, the non-itemised triage wakes (a drafting item each), and the
    news events targeted at it. Also returns whether any item cannot be placed in a session
    (an ask with no proposal id): the role then runs one-shot this cycle."""
    sp = pol.sessions
    items: List[Item] = []
    subject_of_project = facts.subject_of_project()
    unplaceable = False
    for key, text in sorted(lane_pending.items()):
        prefix = key.partition(":")[0]
        subject = None
        if prefix in ("step_done", "step_attention", "project_idle"):
            project = news_mod.project_of(text) or (key.partition(":")[2] if prefix == "project_idle" else None)
            subject = subject_of_project.get(project or "")
        elif prefix == "answer":
            subject = state.ask_proposals.get(key.partition(":")[2])
        ev = news_mod.lane_item_event(key, text, role=role, subject=subject, decisions=facts.decisions)
        if ev is not None:
            items.append(Item(
                role, f"lane:{key}", "lane", ev.kind, ev.text, subject=ev.subject,
                actionable=news_mod.classify(ev, sp) == ACTIONABLE, lane_key=key, event=ev,
            ))
            continue
        covered = covering_proposal(role, key, sp, facts)
        if covered is not None:
            cev = NewsEvent(f"lane:{role}:{key}", "lane_covered", f"{key}: {text} (covered by {covered})", subject=covered, role=role)
            items.append(Item(role, f"lane:{key}", "lane", "lane_covered", cev.text, subject=covered, actionable=False, lane_key=key, event=cev))
        else:
            items.append(Item(role, f"lane:{key}", "lane", prefix, f"{key}: {text}", subject=None, lane_key=key))
    for aid, ask in sorted(facts.asks.items()):
        if ask.get("to") != role:
            continue
        pid = ask.get("proposal_id")
        if pid is None:
            unplaceable = True
        items.append(Item(role, f"ask:{aid}", "ask", "ask", f"ask {aid} is open for you (its id is in your queue list); answer it.", subject=pid))
    for ev in events:
        if ev.role not in (None, role):
            continue
        if state.is_delivered(role, ev.id):
            continue
        items.append(Item(
            role, f"news:{ev.id}", "news", ev.kind, ev.line(), subject=ev.subject,
            actionable=news_mod.classify(ev, sp) == ACTIONABLE, event=ev,
        ))
    seen_reasons: Set[str] = set()
    for w in wakes:
        if w.reason in ITEMISED_REASONS or w.reason in seen_reasons:
            continue
        seen_reasons.add(w.reason)
        items.append(Item(role, f"wake:{w.reason}", "wake", w.reason, f"{w.reason}: {w.detail}"))
    return items, unplaceable


def plan_role(
    role: str, items: Sequence[Item], *, facts: QueueFacts, state: SessionState, wake: Optional[Wake], cycle: int,
) -> List[TurnPlan]:
    """Group a role's items into sessions. Actionable work on a subject opens (or resumes)
    that proposal's session; subject-less actionable work opens one drafting session;
    informational work rides along when its session has a turn and otherwise stays parked
    (the caller parks `informational only` leftovers)."""
    relevant = relevant_proposals(role, facts)
    by_subject: Dict[str, List[Item]] = {}
    loose: List[Item] = []
    for it in items:
        if it.subject is not None:
            by_subject.setdefault(it.subject, []).append(it)
        else:
            loose.append(it)
    plans: List[TurnPlan] = []
    for pid, its in by_subject.items():
        if not any(i.actionable for i in its):
            continue
        # A subject the role has no part in (an alarm text that names a foreign proposal)
        # is never given its session: the items fall to the drafting session.
        if pid not in relevant and state.for_proposal(role, pid) is None and not any(i.source in ("lane", "news") and i.event and i.event.role == role for i in its):
            loose.extend(its)
            continue
        rec = state.for_proposal(role, pid)
        if rec is not None:
            plans.append(TurnPlan(role, KIND_PROPOSAL, rec.key, list(rec.refs), its, wake, False, rec.activation, 0))
        else:
            gen = state.generations.get(f"{role}:{pid}", 0)
            plans.append(TurnPlan(role, KIND_PROPOSAL, proposal_key(role, pid, gen), [pid], its, wake, True, 0, gen))
    if any(i.actionable for i in loose):
        act = state.next_activation()
        plans.append(TurnPlan(role, KIND_DRAFTING, drafting_key(role, act), [], loose, wake, False, act, 0))
    return plans


def prompt_tokens(result: RunResult) -> Optional[int]:
    """The turn's prompt size, input plus cache read. Prefers the envelope's own
    `agentMeta.promptTokens` / `lastCallUsage` (the last model call's prompt, which is the
    session's size now); falls back to the run's cumulative `usage` (an overestimate for a
    multi-round turn, so it can only drop a session early, never late)."""
    meta = _mapping(_mapping(_mapping(result.raw).get("result")).get("meta"))
    agent = _mapping(meta.get("agentMeta"))
    n = agent.get("promptTokens")
    if isinstance(n, (int, float)) and not isinstance(n, bool):
        return int(n)
    last = _mapping(agent.get("lastCallUsage"))
    usage = last or _mapping(result.usage)
    parts = [usage.get("input"), usage.get("cacheRead")]
    nums = [p for p in parts if isinstance(p, (int, float)) and not isinstance(p, bool)]
    return int(sum(nums)) if nums else None


# ---- the adaptive turn limit ------------------------------------------------


class TurnLimiter:
    """One limit on simultaneous model turns (not open sessions), never two turns on one
    key, and a stagger between same-role turn starts. The limit moves with what the
    turns report (`release`); `end_cycle` says whether it has stayed down long enough to
    alert."""

    def __init__(
        self, pol: SessionsPolicy, *, limit: int = 0, clean: int = 0, lowered_cycles: int = 0,
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ):
        self.pol = pol
        self.limit = limit if limit > 0 else pol.concurrency_start
        self.limit = max(pol.concurrency_min, min(pol.concurrency_max, self.limit))
        self.clean = clean
        self.lowered_cycles = lowered_cycles
        self._clock, self._sleep = clock, sleep
        self._cv: Optional[asyncio.Condition] = None
        self._active: Set[str] = set()
        self._next_slot: Dict[str, float] = {}
        self.peak = 0
        self.lowered_this_cycle = False

    def _condition(self) -> asyncio.Condition:
        if self._cv is None:
            self._cv = asyncio.Condition()
        return self._cv

    async def acquire(self, key: str, role: str) -> None:
        cv = self._condition()
        async with cv:
            while key in self._active or len(self._active) >= self.limit:
                await cv.wait()
            self._active.add(key)
            self.peak = max(self.peak, len(self._active))
            now = self._clock()
            slot = max(now, self._next_slot.get(role, 0.0))
            self._next_slot[role] = slot + self.pol.stagger_seconds
        if slot > now:
            await self._sleep(slot - now)

    async def release(self, key: str, result: Optional[RunResult]) -> None:
        cv = self._condition()
        async with cv:
            self._active.discard(key)
            if result is not None:
                self._note(result)
            cv.notify_all()

    def _note(self, result: RunResult) -> None:
        if result.status in _NEUTRAL_STATUSES:
            return
        slow = float(result.wall_clock_seconds or 0.0) > self.pol.slow_turn_seconds
        if not result.ok or slow:
            if self.limit > self.pol.concurrency_min:
                self.limit -= 1
                LOG.warning("session turn limit lowered to %d (%s%s)", self.limit, result.status, ", slow" if slow else "")
            self.lowered_this_cycle = True
            self.clean = 0
            return
        self.clean += 1
        if self.clean >= self.pol.raise_after_clean_turns and self.limit < self.pol.concurrency_max:
            self.limit += 1
            self.clean = 0
            LOG.info("session turn limit raised to %d", self.limit)

    def end_cycle(self) -> Optional[str]:
        """Counts a cycle that ended below the starting limit; returns the alert text once
        it has lasted `alert_after_cycles` cycles in a row (and on every cycle after)."""
        if self.limit < self.pol.concurrency_start:
            self.lowered_cycles += 1
        else:
            self.lowered_cycles = 0
        if self.lowered_cycles >= self.pol.alert_after_cycles:
            return (
                f"session turn limit has been below its start ({self.limit} of {self.pol.concurrency_start}) "
                f"for {self.lowered_cycles} cycles: the Gateway or DeepSeek is erroring or slow"
            )
        return None


# ---- messages ---------------------------------------------------------------


def build_turn_message(
    plan: TurnPlan, items: Sequence[Item], *, turn: int, fort_line: str, news_lines: Sequence[str],
    rebrief: Sequence[str] = (), briefing: Optional[str] = None, fort_events: Sequence[str] = (),
) -> str:
    """One session message: header, the fresh vitals line and the staleness line (every
    activation's FIRST turn), any control lines, the re-brief, the news block, the items.
    A drafting session's first turn also carries the role's ordinary briefing."""
    out = [f"SESSION {plan.key} ({plan.kind}; turn {turn})"]
    if turn == 1:
        out.append(fort_line)
        out.append(STALE_LINE)
    for line in fort_events:
        out.append(line)
    if rebrief:
        out.append("RE-BRIEF (rebuilt from the queue; this session is new or was reset):")
        out.extend(f"  {r}" for r in rebrief)
    if briefing and plan.kind == KIND_DRAFTING and turn == 1:
        out.append("BRIEFING")
        out.append(briefing)
    if news_lines:
        out.append(f"NEWS ({len(news_lines)} line(s), for your information)")
        out.extend(news_lines)
    out.append(f"ITEMS ({len(items)})")
    for i, it in enumerate(items, 1):
        out.append(f"{i}. [{it.kind}] {it.text}")
    out.append("Handle each item, then stop. To leave one deliberately, queue.pass naming its proposal with a reason.")
    return "\n".join(out)


def docket_lines(proposals: Sequence[Mapping[str, Any]]) -> List[str]:
    """One line per proposal waiting (id, role, type, priority): the Overseer's overview
    of everything not shown in full."""
    return [
        f"- {p.get('id')} [{p.get('role')}, {p.get('type')}] priority {p.get('priority')}" for p in proposals
    ]


def build_overseer_item(proposals: Sequence[Mapping[str, Any]], *, waiting_more: Sequence[Mapping[str, Any]], ask: str,
                        routed_types: Sequence[str] = ()) -> str:
    """A later message in the Overseer's session: newly filed proposals (one, or a batch)."""
    out = [f"NEW PROPOSAL{'S' if len(proposals) != 1 else ''} filed while you were ruling ({len(proposals)}):"]
    for p in proposals:
        out.extend(format_proposal_lines(p, routed_types))
    if waiting_more:
        out.append(f"STILL WAITING after these ({len(waiting_more)}):")
        out.extend(docket_lines(waiting_more))
    out.append(ask)
    return "\n".join(out)


# ---- the engine -------------------------------------------------------------

ExecuteTurn = Callable[[str, Optional[Wake], str, str, float], Awaitable[RunResult]]


@dataclass
class PhaseCtx:
    """What the cycle gives the engine for one phase. Every callable is the cycle's own
    code, so the engine stays free of tool reads and briefing text."""

    #: One bracketed turn (the `conductor.report` start and end around the runner):
    #: `(role, wake, session_key, message, budget_seconds) -> RunResult`.
    execute_turn: ExecuteTurn
    #: Called after every turn: `(role, wake, result, shown_ids)`; returns True when the cycle
    #: must stop new turns (the Overseer escalated). Runs the cycle's own post-run work
    #: (proposer attribution, cursors, the escalation check).
    post_turn: Callable[[str, Optional[Wake], RunResult, Optional[Sequence[str]]], Awaitable[bool]]
    timeout_for: Callable[[str], float]
    #: One line: FORT tick and vitals (plus the paused line), fresh each activation.
    fort_line: Callable[[], str]
    #: The role's ordinary one-shot prompt text (a drafting session's briefing).
    prompt_for: Callable[[str], str]
    #: `queue.pending_brief`, or None when the read failed.
    read_pending_brief: Callable[[], Awaitable[Optional[Mapping[str, Any]]]]
    #: `queue.overview`'s proposals, as `{id: filing role}`, or None when the read failed.
    read_pending: Callable[[], Awaitable[Optional[Dict[str, str]]]]
    #: The Overseer's opening message for a (subset of the) pending brief, today's ruling briefing.
    ruling_message: Callable[[Optional[Mapping[str, Any]]], str]
    #: The ruling ask for `n` proposals (`briefing.ruling_ask`).
    ruling_ask: Callable[[int], str]
    routed_types: Sequence[str] = ()
    #: Lines for a re-brief of `(role, proposal id)`, built from the queue.
    rebrief: Callable[[str, str], Awaitable[List[str]]] = None  # type: ignore[assignment]
    #: The live lane `pending` map (role -> key -> text), mutated as items are served.
    lane_pending: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: Wakes per role this cycle (triage).
    wakes: Mapping[str, Sequence[Wake]] = field(default_factory=dict)
    cycle_index: int = 0
    #: HOOK(stream 4, execute containment): `activation_hook("open"|"close", activation)` is
    #: called around every Overseer activation (`{"key", "activation", "wake_id"}`) so the
    #: execute phase can restrict itself to actions recorded inside one. The cycle leaves it None.
    activation_hook: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None


@dataclass
class PhaseResult:
    runs: List[RunResult] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    #: One summary per activation (session key, kind, turns, outcome) for the cycle archive.
    activations: List[Dict[str, Any]] = field(default_factory=list)
    halted: bool = False
    lost: bool = False
    #: Items not sent this cycle (budget, a lost transport, a halt): they stay pending.
    carried: List[str] = field(default_factory=list)
    limit: int = 0
    peak: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "activations": self.activations, "alerts": self.alerts, "halted": self.halted, "lost": self.lost,
            "carried": self.carried, "limit": self.limit, "peak_concurrent_turns": self.peak,
            "turns": len(self.runs),
        }


class SessionEngine:
    """The cycle's session machinery. One instance per conductor process; `state` is loaded
    at the start of each cycle (`begin_cycle`) and saved at its end (`end_cycle`)."""

    def __init__(
        self, policy: Policy, store: SessionStore, runner: SessionRunner, *,
        health: Optional[Callable[[], Awaitable[GatewayHealth]]] = None,
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ):
        self.policy = policy
        self.store = store
        self.runner = runner
        self._health = health
        self._clock, self._sleep = clock, sleep
        self.state = SessionState()
        self.limiter = TurnLimiter(policy.sessions, clock=clock, sleep=sleep)
        self._cycle_events: Dict[str, List[NewsEvent]] = {}
        self._cycle = 0
        self._halt = False
        self._lost = False
        self._inflight: Dict[str, Set[str]] = {}
        self._handed: Set[str] = set()
        self._known_pending: Set[str] = set()

    # -- gating -------------------------------------------------------------

    @property
    def sp(self) -> SessionsPolicy:
        return self.policy.sessions

    @property
    def enabled(self) -> bool:
        return self.sp.enabled and bool(self.sp.session_roles())

    def mode_of(self, role: str) -> str:
        return self.sp.mode_of(role)

    def begin_cycle(self, cycle_index: int) -> None:
        self._cycle = cycle_index
        try:
            self.state = self.store.load()
        except Exception:  # noqa: BLE001 -- an unreadable file is a clean slate, said loudly
            LOG.exception("sessions state unreadable; starting from an empty key map")
            self.state = SessionState()
        self.limiter = TurnLimiter(
            self.sp, limit=self.state.limit, clean=self.state.clean_turns, lowered_cycles=self.state.lowered_cycles,
            clock=self._clock, sleep=self._sleep,
        )
        self._cycle_events = {}

    def save(self) -> None:
        self.state.limit = self.limiter.limit
        self.state.clean_turns = self.limiter.clean
        self.state.lowered_cycles = self.limiter.lowered_cycles
        try:
            self.store.save(self.state)
        except Exception:  # noqa: BLE001
            LOG.exception("could not save sessions state")

    async def route(self) -> RouteDecision:
        """The cycle's one Gateway decision (spec 7.3): `gateway`, or `oneshot` (every session role
        runs one-shot this cycle, one alert per outage). Recovery from an outage drops every
        session: the Gateway was down, so its history may be wiped (spec 7.2)."""
        if self._health is None:
            health = GatewayHealth("started")
        else:
            try:
                health = await self._health()
            except Exception as exc:  # noqa: BLE001 -- a broken probe reads as down
                health = GatewayHealth("down", f"{type(exc).__name__}: {exc}")
        decision = decide_route(health, role_mode="session")
        if decision.route == "gateway" and self.state.outage:
            self.gateway_restarted("the Gateway is back after an outage")
            self.state.outage = False
        if decision.route != "gateway":
            first = not self.state.outage
            self.state.outage = True
            return replace(decision, alert=first)
        return decision

    def gateway_restarted(self, why: str = "") -> None:
        """The Gateway's session store was wiped (a restart, a dfmcp deploy under U8): every key
        is gone. Each open proposal reopens on its next activation with a re-brief."""
        LOG.warning("gateway restarted (%s): dropping %d session(s)", why or "no reason given", len(self.state.sessions))
        for rec in list(self.state.sessions.values()):
            self.drop(rec, bump=False)

    def drop(self, rec: SessionRecord, *, bump: bool = True) -> None:
        self.state.sessions.pop(rec.key, None)
        if bump:
            for pid in rec.refs:
                gk = f"{rec.role}:{pid}"
                self.state.generations[gk] = self.state.generations.get(gk, 0) + 1

    # -- the fort-wide notes ---------------------------------------------------

    def note_fort_event(self, text: str, *, tick: Optional[int] = None) -> None:
        """A control line from a cycle that ran no sessions (a tripwire, an unexplained
        pause): shown once at the top of each role's next first message."""
        rows = self.state.fort_events
        rows.append({"text": text, "tick": tick, "seen_by": []})
        del rows[:-_FORT_EVENTS_KEEP]

    def _fort_lines_for(self, role: str) -> List[str]:
        return [e["text"] for e in self.state.fort_events if role not in e.get("seen_by", [])]

    def _mark_fort_seen(self, role: str) -> None:
        for e in self.state.fort_events:
            seen = e.setdefault("seen_by", [])
            if role not in seen:
                seen.append(role)

    # -- H1: before triage ------------------------------------------------------

    def close_finished(self, facts: QueueFacts, *, projects_known: bool) -> List[str]:
        """Close every session none of whose proposals is still open. When the server does not say
        which proposal an open project belongs to (`projects_known` false) a session is kept
        while its role still has any open project, so an accepted proposal's session is not
        closed under it."""
        open_ids = facts.open_proposals
        closed: List[str] = []
        role_has_project = {str(p.get("role")) for p in facts.projects.values()}
        for rec in list(self.state.sessions.values()):
            if rec.kind == KIND_OVERSEER:
                continue
            if rec.kind == KIND_DRAFTING and not rec.refs:
                continue  # closed at the end of its own activation
            if any(r in open_ids for r in rec.refs):
                continue
            if not projects_known and rec.role in role_has_project:
                continue
            self.state.sessions.pop(rec.key, None)
            closed.append(rec.key)
        return closed

    def absorb(
        self, *, lane_state: Any, facts: QueueFacts, events: Sequence[NewsEvent],
    ) -> List[LaneWake]:
        """Run before triage. For every session-mode role: (1) record the ask to proposal links
        now open; (2) move informational lane entries and lane facts a proposal covers out of
        `lane_state.pending` into parked news, so they stop waking the role; (3) route the
        cycle's derived news events: informational ones are parked, actionable ones are
        returned as lane wakes (`session_news`) so triage wakes the role for them. Mutates
        `lane_state.pending` only by removing entries."""
        sp = self.sp
        for aid, ask in facts.asks.items():
            if ask.get("proposal_id"):
                self.state.ask_proposals[aid] = str(ask["proposal_id"])
        while len(self.state.ask_proposals) > _ASK_LINKS_KEEP:
            self.state.ask_proposals.pop(next(iter(self.state.ask_proposals)))
        wakes: List[LaneWake] = []
        subject_of_project = facts.subject_of_project()
        for role in sp.session_roles():
            pending = lane_state.pending.get(role) or {}
            for key, text in list(pending.items()):
                prefix = key.partition(":")[0]
                subject = None
                if prefix in ("step_done", "step_attention", "project_idle"):
                    project = news_mod.project_of(text) or (key.partition(":")[2] if prefix == "project_idle" else None)
                    subject = subject_of_project.get(project or "")
                elif prefix == "answer":
                    subject = self.state.ask_proposals.get(key.partition(":")[2])
                ev = news_mod.lane_item_event(key, text, role=role, subject=subject, decisions=facts.decisions)
                if ev is None:
                    covered = covering_proposal(role, key, sp, facts)
                    if covered is None:
                        continue
                    ev = NewsEvent(f"lane:{role}:{key}", "lane_covered", f"{key}: {text} (covered by {covered})", subject=covered, role=role)
                if news_mod.classify(ev, sp) == INFORMATIONAL:
                    self.state.park(role, ev, sp.parked_news_cap)
                    pending.pop(key, None)
            if role in lane_state.pending and not lane_state.pending[role]:
                del lane_state.pending[role]
        for ev in events:
            for role in self._targets(ev, facts):
                if self.state.is_delivered(role, ev.id):
                    continue
                if news_mod.classify(ev, sp) == INFORMATIONAL:
                    self.state.park(role, ev, sp.parked_news_cap)
                else:
                    self._cycle_events.setdefault(role, []).append(ev)
        for role, evs in self._cycle_events.items():
            wakes.append(LaneWake("session_news", "; ".join(e.line() for e in evs)[:300], (role,)))
        return wakes

    def _targets(self, ev: NewsEvent, facts: QueueFacts) -> List[str]:
        """The session-mode roles an event is for."""
        roles = list(self.sp.session_roles())
        if ev.fort_wide:
            return list(news_mod.affected_roles(ev, self.policy, [r for r in roles if r != OVERSEER]))
        if ev.role is not None:
            return [ev.role] if ev.role in roles else []
        if ev.subject is None:
            return []
        out = [r for r in roles if r != OVERSEER and ev.subject in relevant_proposals(r, facts)]
        for rec in self.state.sessions.values():
            if ev.subject in rec.refs and rec.role in roles and rec.role not in out and rec.role != OVERSEER:
                out.append(rec.role)
        return out

    # -- planning ----------------------------------------------------------------

    def plan(
        self, *, woken: Sequence[str], facts: QueueFacts, lane_pending: Mapping[str, Mapping[str, str]],
        wakes: Mapping[str, Sequence[Wake]],
    ) -> PhasePlan:
        """Split the woken session-mode roles into session turns, one-shot fallbacks (an ask with no
        proposal id cannot join a session) and the Overseer's per-wake session."""
        plan = PhasePlan()
        for role in woken:
            if self.mode_of(role) != "session":
                continue
            ws = list(wakes.get(role, ()))
            head = ws[0] if ws else None
            if role == OVERSEER:
                wake_id = self.state.next_wake()
                plan.overseer = TurnPlan(role, KIND_OVERSEER, overseer_key(wake_id), [], [], head, False, wake_id, 0)
                continue
            items, unplaceable = derive_items(
                role, lane_pending=lane_pending.get(role) or {}, facts=facts, state=self.state, pol=self.policy,
                events=self._cycle_events.get(role, ()), wakes=ws,
            )
            if unplaceable:
                plan.oneshot_roles.append(role)
                continue
            turns = plan_role(role, items, facts=facts, state=self.state, wake=head, cycle=self._cycle)
            if not turns:
                plan.parked_only.append(role)
                continue
            plan.turns.extend(turns)
        return plan

    # -- running -----------------------------------------------------------------

    def _news_for(self, role: str, plan: TurnPlan, items: Sequence[Item]) -> Tuple[List[NewsEvent], List[Item]]:
        """The informational news that rides this message: the parked events for the role that are
        about this session's proposals (or the role at large for a drafting session), plus the
        informational items of the plan. Returns (events, the actionable items to list)."""
        events: List[NewsEvent] = []
        seen: Set[str] = set()
        for row in self.state.parked.get(role, ()):
            subj = row.get("subject")
            if plan.kind == KIND_PROPOSAL and subj not in plan.refs:
                continue
            if plan.kind == KIND_DRAFTING and subj is not None:
                continue
            events.append(NewsEvent(str(row["id"]), str(row["kind"]), str(row["text"]), subject=subj, tick=row.get("tick"),
                                    cls_override=INFORMATIONAL))
            seen.add(str(row["id"]))
        actionable: List[Item] = []
        for it in items:
            if it.actionable:
                actionable.append(it)
            elif it.event is not None and it.event.id not in seen:
                events.append(replace(it.event, cls_override=INFORMATIONAL))
                seen.add(it.event.id)
        return events, actionable

    def _serve(self, role: str, items: Sequence[Item], events: Sequence[NewsEvent], lane_pending: Dict[str, Dict[str, str]]) -> None:
        for it in items:
            if it.lane_key is not None:
                (lane_pending.get(role) or {}).pop(it.lane_key, None)
            if it.event is not None:
                self.state.mark_delivered(role, it.event.id)
        for ev in events:
            self.state.mark_delivered(role, ev.id)
            self.state.parked[role] = [p for p in self.state.parked.get(role, []) if p.get("id") != ev.id]
        if role in lane_pending and not lane_pending[role]:
            del lane_pending[role]

    async def run_phase(self, plan: PhasePlan, ctx: PhaseCtx, facts: QueueFacts) -> PhaseResult:
        res = PhaseResult()
        self._halt = False
        self._lost = False
        self._inflight: Dict[str, Set[str]] = {}
        self._handed: Set[str] = set()
        inbox: "asyncio.Queue[Optional[Mapping[str, Any]]]" = asyncio.Queue()
        pending_snapshot = await ctx.read_pending()
        self._known_pending = set((pending_snapshot or {}).keys())
        tasks = [asyncio.ensure_future(self._activation(tp, ctx, res, inbox, facts)) for tp in plan.turns]
        overseer_task = None
        if plan.overseer is not None:
            overseer_task = asyncio.ensure_future(self._overseer_activation(plan.overseer, ctx, res, inbox))
        try:
            if tasks:
                await asyncio.gather(*tasks)
        finally:
            await inbox.put(None)  # the Overseer's sentinel: every proposer is done
            if overseer_task is not None:
                await overseer_task
        res.halted, res.lost = self._halt, self._lost
        alert = self.limiter.end_cycle()
        if alert:
            res.alerts.append(alert)
            LOG.error("sessions: %s", alert)
        res.limit, res.peak = self.limiter.limit, self.limiter.peak
        for role in plan.parked_only:
            res.activations.append({"role": role, "kind": "parked", "turns": 0})
        return res

    async def _one_turn(
        self, ctx: PhaseCtx, role: str, wake: Optional[Wake], key: str, message: str, budget: float,
    ) -> RunResult:
        await self.limiter.acquire(key, role)
        result: Optional[RunResult] = None
        try:
            result = await ctx.execute_turn(role, wake, key, message, budget)
            return result
        finally:
            await self.limiter.release(key, result)

    async def _activation(
        self, tp: TurnPlan, ctx: PhaseCtx, res: PhaseResult, inbox: "asyncio.Queue", facts: QueueFacts,
    ) -> None:
        role = tp.role
        started = self._clock()
        total = ctx.timeout_for(role)
        rec = self.state.sessions.get(tp.key)
        if rec is None:
            rec = SessionRecord(tp.key, role, tp.kind, refs=list(tp.refs), activation=tp.activation, opened_cycle=self._cycle)
            self.state.sessions[tp.key] = rec
        summary: Dict[str, Any] = {"role": role, "key": tp.key, "kind": tp.kind, "refs": list(rec.refs), "turns": 0, "outcome": "ok"}
        res.activations.append(summary)
        self._inflight.setdefault(role, set()).add(tp.key)
        items = list(tp.items)
        try:
            turn = 0
            while items:
                if self._halt or self._lost:
                    res.carried.extend(i.id for i in items)
                    summary["outcome"] = "carried"
                    break
                news_events, listed = self._news_for(role, tp, items)
                if not listed:
                    break
                budget = total - (self._clock() - started)
                turn += 1
                rebrief: List[str] = []
                if turn == 1 and tp.needs_rebrief and tp.kind == KIND_PROPOSAL:
                    for pid in tp.refs:
                        rebrief.extend(await ctx.rebrief(role, pid) if ctx.rebrief else [])
                briefing = ctx.prompt_for(role) if tp.kind == KIND_DRAFTING and turn == 1 else None
                message = build_turn_message(
                    tp, listed, turn=turn, fort_line=ctx.fort_line(),
                    news_lines=news_mod.render_lines(news_events, self.sp.news_max_lines, self.sp), rebrief=rebrief,
                    briefing=briefing, fort_events=self._fort_lines_for(role) if turn == 1 else (),
                )
                result = await self._one_turn(ctx, role, tp.wake, tp.key, message, budget)
                res.runs.append(result)
                summary["turns"] = turn
                rec.turns += 1
                await self._after_turn(tp, rec, ctx, result, res, inbox)
                if result.status == "no_budget":
                    res.carried.extend(i.id for i in listed)
                    summary["outcome"] = "no_budget"
                    break
                if not result.ok:
                    summary["outcome"] = result.status
                    if result.status == "transport_lost":
                        self._lost = True
                    # Ambiguous or failed: the items stay pending (not served), and this session
                    # is not sent to again this phase.
                    break
                self._serve(role, items, news_events, ctx.lane_pending)
                if turn == 1:
                    self._mark_fort_seen(role)
                items = [i for i in self._take_new_actionable(role, tp) if i.id not in {x.id for x in listed}]
        finally:
            self._inflight.get(role, set()).discard(tp.key)
            if tp.kind == KIND_DRAFTING and not rec.refs:
                self.state.sessions.pop(tp.key, None)  # filed nothing: closed
                summary["closed"] = "nothing filed"
            await self._transcript(res, tp.key)

    def _take_new_actionable(self, role: str, tp: TurnPlan) -> List[Item]:
        """Actionable work that arrived for this session while it ran. Nothing arrives mid-cycle
        today but the Overseer's rulings, which reach a proposer through the next cycle's lane
        state, so this is the seam (kept for a ruling-after-each-turn switch, Q5)."""
        return []

    async def _transcript(self, res: PhaseResult, key: str) -> None:
        """`chat.history` for the key, read once at the end of its activation and attached to
        its LAST run (the archive and `conductor.report` already carry a result's transcript)."""
        try:
            transcript = await self.runner.transcript(key)
        except Exception:  # noqa: BLE001
            transcript = None
        if transcript is None:
            return
        for i in range(len(res.runs) - 1, -1, -1):
            if res.runs[i].session_key == key:
                res.runs[i] = replace(res.runs[i], transcript=transcript)
                return

    async def _after_turn(
        self, tp: TurnPlan, rec: SessionRecord, ctx: PhaseCtx, result: RunResult, res: PhaseResult, inbox: "asyncio.Queue",
    ) -> None:
        tokens = prompt_tokens(result)
        if tokens is not None:
            rec.prompt_tokens = tokens
            if tokens > self.sp.size_cap_tokens:
                LOG.info("session %s prompt is %d tokens (cap %d): dropped, re-briefed on its next activation",
                         tp.key, tokens, self.sp.size_cap_tokens)
                self.drop(rec)
        halt = await ctx.post_turn(tp.role, tp.wake, result, None)
        if halt:
            self._halt = True
        if result.ok and not self._halt:
            await self._pipeline(tp, rec, ctx, inbox)

    async def _pipeline(self, tp: TurnPlan, rec: SessionRecord, ctx: PhaseCtx, inbox: "asyncio.Queue") -> None:
        """After a non-Overseer turn: re-read the pending proposals, map each new one to the session
        that filed it (a drafting session becomes its proposal's session) and hand it to the
        Overseer's inbox. A filing's author is the role recorded on it; when several same-role
        sessions ran at once the proposal is mapped only if exactly one of them is a drafting
        session (never guessed)."""
        snap = await ctx.read_pending()
        if snap is None:
            return
        new = [pid for pid in snap if pid not in self._known_pending]
        if not new:
            return
        self._known_pending.update(new)
        brief = await ctx.read_pending_brief()
        by_id = {str(p.get("id")): p for p in (_mapping(brief).get("proposals") or ()) if isinstance(p, Mapping)}
        for pid in new:
            author = snap.get(pid)
            if author == tp.role:
                candidates = [self.state.sessions[k] for k in self._inflight.get(tp.role, ()) if k in self.state.sessions]
                target: Optional[SessionRecord] = rec if len(candidates) <= 1 else None
                if target is None:
                    drafting = [c for c in candidates if c.kind == KIND_DRAFTING]
                    target = drafting[0] if len(drafting) == 1 else None
                if target is not None and pid not in target.refs:
                    target.refs.append(pid)
                elif target is None:
                    LOG.info("proposal %s filed by %s while %d of its sessions ran: not mapped to one", pid, tp.role, len(candidates))
            await inbox.put(by_id.get(pid) or {"id": pid, "role": author, "type": "?", "summary": "(brief unavailable)", "priority": "?"})

    # -- the Overseer's session --------------------------------------------------

    async def _overseer_activation(
        self, tp: TurnPlan, ctx: PhaseCtx, res: PhaseResult, inbox: "asyncio.Queue",
    ) -> None:
        sp = self.sp
        role = tp.role
        started = self._clock()
        total = ctx.timeout_for(role)
        rec = SessionRecord(tp.key, role, KIND_OVERSEER, activation=tp.activation, opened_cycle=self._cycle)
        self.state.sessions[tp.key] = rec
        summary: Dict[str, Any] = {"role": role, "key": tp.key, "kind": KIND_OVERSEER, "turns": 0, "outcome": "ok", "shown": []}
        res.activations.append(summary)
        hook_info = {"key": tp.key, "activation": tp.activation, "wake_id": tp.activation}
        if ctx.activation_hook:
            await ctx.activation_hook("open", hook_info)
        shown: List[str] = []
        try:
            brief = await ctx.read_pending_brief()
            proposals = [p for p in (_mapping(brief).get("proposals") or ()) if isinstance(p, Mapping)]
            batch = len(proposals) >= sp.overseer_batch_threshold
            first = proposals if batch or not proposals else proposals[:1]
            waiting: Deque[Mapping[str, Any]] = deque(proposals[len(first):])
            subset = dict(brief or {}, proposals=list(first), count=len(first)) if brief is not None else None
            message = ctx.ruling_message(subset)
            if waiting:
                message += "\nDOCKET, still to come one at a time:\n" + "\n".join(docket_lines(list(waiting)))
            message = f"SESSION {tp.key} (overseer; turn 1)\n{STALE_LINE}\n{message}"
            turn = 0
            done_inbox = False
            while True:
                if self._halt:
                    summary["outcome"] = "halted"
                    break
                budget = total - (self._clock() - started)
                turn += 1
                shown.extend(str(p.get("id")) for p in first)
                result = await self._one_turn(ctx, role, tp.wake, tp.key, message, budget)
                res.runs.append(result)
                summary["turns"] = turn
                rec.turns += 1
                prompt = prompt_tokens(result)
                rec.prompt_tokens = prompt if prompt is not None else rec.prompt_tokens
                if await ctx.post_turn(role, tp.wake, result, list(shown)):
                    self._halt = True
                    summary["outcome"] = "escalated"
                    break
                if result.status == "no_budget":
                    summary["outcome"] = "no_budget"
                    break
                if not result.ok:
                    summary["outcome"] = result.status
                    if result.status == "transport_lost":
                        self._lost = True
                    break
                if prompt is not None and prompt > sp.size_cap_tokens:
                    LOG.info("overseer session %s passed the size cap (%d); it ends with this wake anyway", tp.key, prompt)
                # Next hand-over: whatever is waiting now, else wait for the next filing.
                if not waiting:
                    if done_inbox:
                        break
                    item = await inbox.get()
                    if item is None:
                        done_inbox = True
                        break
                    waiting.append(item)
                while not inbox.empty():
                    item = inbox.get_nowait()
                    if item is None:
                        done_inbox = True
                        break
                    waiting.append(item)
                if not waiting:
                    break
                if self._clock() - started >= total:
                    break
                take = list(waiting) if len(waiting) >= sp.overseer_batch_threshold else [waiting[0]]
                for _ in take:
                    waiting.popleft()
                first = take
                message = build_overseer_item(
                    take, waiting_more=list(waiting), ask=ctx.ruling_ask(max(2, 4 * len(take) + 2)),
                    routed_types=ctx.routed_types,
                )
            summary["shown"] = list(shown)
            if waiting:
                res.carried.extend(str(p.get("id")) for p in waiting)
        finally:
            self.state.sessions.pop(tp.key, None)  # the Overseer's session is per wake
            if ctx.activation_hook:
                await ctx.activation_hook("close", hook_info)
            await self._transcript(res, tp.key)
