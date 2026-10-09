"""The Planner's conductor side: the season cursor, the bootstrap, the review
and ruling wakes, and the plan shortfall watch.

`research/2026-10-07-planner-design.md` 5 and `handoffs/2026-10-07-planner-p1b.md`.
Everything here is pure arithmetic over one `plan.status` read (the server
computes every position, in-flight count and derived input; the conductor does
arithmetic on nothing) and a small state file beside the cursor store. It reads
no tool, writes no record and wakes nobody itself: `evaluate` returns
`PlanWake`s that `conductor/cycle.py` hands to triage as lane wakes.

What it raises, by wake reason (all in `conductor/policy.yaml wake_reasons`):

- `plan_bootstrap`, no active plan. Backs off (doubling, capped at a season);
  after `bootstrap_escalate_after` wakes that left no plan it tells the
  operator, with the last refusal text, and stops waking the Planner (F-19).
- `plan_review`, the computed season index changed and the active version is
  from an earlier season. Owed until the Planner files a version or passes
  (a pass records the review tick); retried on backoff, a bounded number of
  times.
- `ruling_on_own`, an accepted `plan_change` no version has cited yet (the
  lane machinery already wakes the Planner once on a ruling; this is the
  backstop with backoff when it passes without filing).
- `roadmap_stage_entered`, the fort's roadmap stage (`plan.status`'s `roadmap`
  block: `alive` with a high-water mark, see `fort_roadmap/roadmap.py`) is not
  the stage the active plan was filed for. Edge triggered on a stage change
  (and whenever the plan stamp differs from the stage, a missing stamp included, regardless of the stored cursor: that is how a plan filed before stages
  existed is asked to adopt the current one), retried on the review backoff,
  and settled by a plan version filed in that stage or a Planner pass.
- `plan_shortfall`, a target is open and its owner is woken with a fixed-shape
  line, edge triggered, renotified on a doubling backoff, suppressed while the
  target holds its max in flight, while the owner's plan budget is used (targets
  compete in plan order), under an operator hold, while the owner's group is
  frozen, and after a serving proposal was rejected (until the next plan version
  or the next backoff step, whichever is later). After `stall_after` wakes with
  the position unchanged the target is `stalled`: no more owner wakes this
  version, and the Planner gets `plan_target_stalled` once (F-8).
- `plan_input_short`, a target's derived input (an item its serving template
  needs) is short for the work in flight: the input's owner is woken, edge
  triggered, on the same backoff.

**The shortfall watch ships OFF** (`plan.shortfall_watch.enabled: false`, user's
call 2026-10-07): the bootstrap, review and ruling wakes may run so version 1
can be read first, but a target's shortfall wakes nobody.

The season cursor is independent of the Planner (`plan.season_wake`): it needs
only the game tick, and it gives the Quartermaster's `season_change` wake a real
trigger for the first time (F-3).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from conductor.policy import PlanPolicy

#: The tool the conductor reads once a cycle (agents/conductor/tools.yaml).
STATUS_TOOL = "plan.status"

PLANNER = "planner"

REASON_BOOTSTRAP = "plan_bootstrap"
REASON_REVIEW = "plan_review"
REASON_STALLED = "plan_target_stalled"
REASON_SHORTFALL = "plan_shortfall"
REASON_STAGE = "roadmap_stage_entered"
REASON_INPUT_SHORT = "plan_input_short"
#: Reused from conductor/lanes.py (its own reason name), raised here for an
#: accepted plan_change nobody has cited.
REASON_RULING = "ruling_on_own"

#: A wake line is bounded like every other conductor line.
MAX_LINE_CHARS = 600


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class Backoff:
    """One wake source's retry state: `wakes` so far, the tick of the next one
    that is allowed (`next_tick`), the position at the last wake, and whether it
    has been given up on (`stalled`)."""
    wakes: int = 0
    next_tick: Optional[int] = None
    last_position: Optional[float] = None
    stalled: bool = False


@dataclass
class TargetState:
    version: Optional[int] = None
    open: bool = False
    backoff: Backoff = field(default_factory=Backoff)
    planner_told: bool = False
    #: Serving proposal ids seen last cycle, and the position then: a serving
    #: id that vanishes while the position fell was rejected or abandoned.
    seen_serving: List[str] = field(default_factory=list)
    prev_position: Optional[float] = None
    #: Rejection suppression: this version, until `suppress_until`.
    suppress_version: Optional[int] = None
    suppress_until: int = 0


@dataclass
class PlanWatchState:
    #: The season cursor: the last index seen and the tick it was seen at.
    season_index: Optional[int] = None
    season_tick: Optional[int] = None
    #: A season review owed to the Planner: the index, the tick it was raised
    #: and its retry state.
    review_index: Optional[int] = None
    review_since: Optional[int] = None
    review: Backoff = field(default_factory=Backoff)
    bootstrap: Backoff = field(default_factory=Backoff)
    bootstrap_escalated: bool = False
    last_refusal: Optional[str] = None
    awaiting: Dict[str, Backoff] = field(default_factory=dict)
    targets: Dict[str, TargetState] = field(default_factory=dict)
    inputs: Dict[str, Backoff] = field(default_factory=dict)
    #: The last fort-roadmap stage seen, the stage an adoption is owed for (if
    #: any), the tick it was raised and its retry state.
    roadmap_stage: Optional[str] = None
    roadmap_owed: Optional[str] = None
    roadmap_since: Optional[int] = None
    #: The stage a Planner pass settled (so a passed stage is not re-owed
    #: every cycle); cleared when the stage changes or a plan matches it.
    roadmap_passed: Optional[str] = None
    roadmap: Backoff = field(default_factory=Backoff)
    #: The Planner to-do list's per-item backoff (conductor/plan_todo.py):
    #: item key -> {sig, wakes, next_tick, stalled, pass_at_wake}.
    todo: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def _passed_for(marker: Optional[str], stage: str) -> bool:
    """A recorded pass must carry the pass tick (`<stage>@<tick>`); a bare
    stage name (written by the 0730333 build, which inferred passes) is not
    evidence of a Planner run and is ignored."""
    if not isinstance(marker, str) or "@" not in marker:
        return False
    name, _, tick = marker.partition("@")
    return name == stage and tick.isdigit()


def _backoff(raw: Any) -> Backoff:
    if not isinstance(raw, dict):
        return Backoff()
    known = {k: v for k, v in raw.items() if k in Backoff.__dataclass_fields__}
    return Backoff(**known)


def _from_dict(raw: Mapping[str, Any]) -> PlanWatchState:
    st = PlanWatchState()
    for key in (
        "season_index", "season_tick", "review_index", "review_since", "last_refusal",
        "roadmap_stage", "roadmap_owed", "roadmap_since", "roadmap_passed",
    ):
        if key in raw:
            setattr(st, key, raw[key])
    st.bootstrap_escalated = bool(raw.get("bootstrap_escalated", False))
    st.review = _backoff(raw.get("review"))
    st.bootstrap = _backoff(raw.get("bootstrap"))
    st.roadmap = _backoff(raw.get("roadmap"))
    st.awaiting = {str(k): _backoff(v) for k, v in (raw.get("awaiting") or {}).items()}
    st.inputs = {str(k): _backoff(v) for k, v in (raw.get("inputs") or {}).items()}
    st.todo = {str(k): dict(v) for k, v in (raw.get("todo") or {}).items() if isinstance(v, dict)}
    for tid, tr in (raw.get("targets") or {}).items():
        if not isinstance(tr, dict):
            continue
        ts = TargetState()
        for key in ("version", "prev_position", "suppress_version"):
            if key in tr:
                setattr(ts, key, tr[key])
        ts.open = bool(tr.get("open", False))
        ts.backoff = _backoff(tr.get("backoff"))
        ts.planner_told = bool(tr.get("planner_told", False))
        ts.seen_serving = [str(x) for x in (tr.get("seen_serving") or [])]
        ts.suppress_until = int(tr.get("suppress_until") or 0)
        st.targets[str(tid)] = ts
    return st


class PlanWatchStore:
    """Single-writer JSON state beside the cursor store, like `LaneStore`. A
    missing file is a fresh state; a corrupt one is an error the caller treats
    as "no plan wakes this cycle" (never a silent reset that re-arms every
    backoff at once)."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> PlanWatchState:
        if not self.path.is_file():
            return PlanWatchState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{self.path}: expected a JSON object")
        return _from_dict(raw)

    def save(self, state: PlanWatchState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(asdict(state), fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


# ---------------------------------------------------------------------------
# The season cursor (F-3, F-11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeasonEdge:
    """`index` is the season now. `changed`: it moved forward since the cursor
    (the edge `season_change` and `plan_review` key on). `first`: there was no
    cursor yet. `reload`: the tick went backwards, so the cursor was reset and
    nobody is woken."""
    index: int
    changed: bool = False
    first: bool = False
    reload: bool = False


def season_index(tick: int, season_ticks: int) -> int:
    return int(tick) // int(season_ticks)


def advance_season(state: PlanWatchState, tick: Optional[int], season_ticks: int) -> Optional[SeasonEdge]:
    """Fold this cycle's tick into the cursor and say what changed. `None` when
    the tick is unknown (the cursor is left alone). A tick below the last one
    seen is a reload: the cursor resets to the new season with no wake and any
    owed review is dropped (the reloaded fort may be in an earlier season)."""
    if tick is None:
        return None
    cur = season_index(tick, season_ticks)
    prev_idx, prev_tick = state.season_index, state.season_tick
    if prev_idx is None or prev_tick is None:
        edge = SeasonEdge(cur, first=True)
    elif tick < prev_tick:
        state.review_index = None
        state.review_since = None
        state.review = Backoff()
        edge = SeasonEdge(cur, reload=True)
    elif cur != prev_idx:
        edge = SeasonEdge(cur, changed=True)
    else:
        edge = SeasonEdge(cur)
    state.season_index = cur
    state.season_tick = int(tick)
    return edge


# ---------------------------------------------------------------------------
# Wakes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanWake:
    reason: str
    role: str
    detail: str
    #: A short stable id for logs and tests (a target id, a ruling id).
    key: str = ""


@dataclass
class PlanWatchResult:
    wakes: List[PlanWake] = field(default_factory=list)
    #: Messages for the operator (a bootstrap that will not wake again).
    alerts: List[str] = field(default_factory=list)
    #: Why something was not woken, for the archive and tests.
    notes: List[str] = field(default_factory=list)
    #: The fort-roadmap block `plan.status` returned this cycle (stage, the
    #: one-line summary, the cross-check), for the briefing; `None` when the
    #: read failed or the server predates it.
    roadmap: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "wakes": [{"reason": w.reason, "role": w.role, "key": w.key, "detail": w.detail} for w in self.wakes],
            "alerts": list(self.alerts), "notes": list(self.notes),
        }
        if self.roadmap is not None:
            out["roadmap"] = {k: self.roadmap.get(k) for k in ("stage", "alive", "entered", "held", "line", "cross_check")}
        return out


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LINE_CHARS else text[: MAX_LINE_CHARS - 3] + "..."


def _num(v: Any) -> str:
    """`22` for 22.0, `2.5` for 2.5, `?` for none."""
    if v is None or isinstance(v, bool):
        return "?"
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:.1f}"
    return str(v)


def _due(b: Backoff, tick: int, cap: int) -> bool:
    """Is a wake allowed now? A `next_tick` further out than the cap can only
    come from before a reload (the tick went backwards): re-arm."""
    return b.next_tick is None or tick >= b.next_tick or (b.next_tick - tick) > cap


def _note_wake(b: Backoff, tick: int, base: int, cap: int, position: Optional[float] = None) -> None:
    """Count a wake and set when the next is allowed: `base` after the first,
    doubling per consecutive wake, never above `cap`."""
    b.wakes += 1
    b.last_position = position
    b.next_tick = tick + min(cap, base * (2 ** (b.wakes - 1)))


def _frozen(signal: Any, serving_types: Mapping, frozen_types: Optional[Iterable[str]]) -> bool:
    """Every proposal type that serves this signal's family is frozen (a
    frozen group takes no proposals), so waking the owner is pointless."""
    if not frozen_types or not isinstance(signal, str):
        return False
    types = tuple(serving_types.get(signal.split(".", 1)[0]) or ())
    return bool(types) and set(types) <= set(frozen_types)


def last_refusal(run_result: Any) -> Optional[str]:
    """The last failed tool call's text from a role run, for the bootstrap
    escalation: the transcript's last errored call (or last `plan.write`
    result that did not file), else the run's error, else its final answer.
    Total: anything unreadable is `None`."""
    try:
        transcript = getattr(run_result, "transcript", None) or {}
        last: Optional[str] = None
        for rnd in transcript.get("rounds") or []:
            for call in rnd.get("calls") or []:
                text = call.get("result")
                if not isinstance(text, str) or not text:
                    continue
                if call.get("error"):
                    last = f"{call.get('name')}: {text}"
                elif call.get("name") == "plan.write" and '"filed": true' not in text and '"filed":true' not in text:
                    last = f"{call.get('name')}: {text}"
        if last:
            return last[:MAX_LINE_CHARS]
        for attr in ("error", "final_answer"):
            text = getattr(run_result, attr, None)
            if isinstance(text, str) and text.strip():
                return text.strip()[:MAX_LINE_CHARS]
    except Exception:  # noqa: BLE001 -- total: a refusal text is best effort
        return None
    return None


# ---------------------------------------------------------------------------
# The fixed-shape lines
# ---------------------------------------------------------------------------


def shortfall_line(version: Any, target: Mapping, ceiling: int, used: int) -> str:
    """Facts first so the owner acts in few rounds (design 5.2):
    `Plan v3 target bedrooms: 9 on hand of 22 wanted (signal zones."Bedroom".
    furnished, open at 2 short); 2 in flight (proposal-0007, proposal-0008);
    1 of 2 plan slots in use. Derived input: bed 0 available, 2 needed
    (Quartermaster notified). File a proposal with serves: ["bedrooms"], or
    pass with a reason.`"""
    tid = target.get("id")
    serving = [s for s in target.get("serving") or [] if isinstance(s, Mapping)]
    ids = ", ".join(str(s.get("proposal_id")) for s in serving[:4])
    flight = f"{len(serving)} in flight" + (f" ({ids})" if ids else "")
    parts = [
        f"Plan v{version} target {tid}: {_num(target.get('on_hand'))} on hand of "
        f"{_num(target.get('want_units'))} wanted (signal {target.get('signal')}, "
        f"{_num(target.get('short_units'))} short); {flight}; {used} of {ceiling} plan slots in use."
    ]
    short_inputs = [i for i in target.get("inputs") or [] if isinstance(i, Mapping) and (i.get("short") or 0) > 0]
    for i in short_inputs[:3]:
        parts.append(
            f"Derived input: {i.get('item')} {_num(i.get('available'))} available, "
            f"{_num(i.get('needed'))} needed ({i.get('owner')} notified)."
        )
    parts.append(f'File a proposal with serves: ["{tid}"], or pass with a reason.')
    return _clip(" ".join(parts))


def input_line(version: Any, target: Mapping, item: Mapping) -> str:
    tid = target.get("id")
    return _clip(
        f"Plan v{version} target {tid}: input {item.get('item')} is short for the work in flight: "
        f"{_num(item.get('needed'))} needed, {_num(item.get('available'))} available. "
        f"You supply {item.get('item')}; a standing order or stock target is preferred over a one-off. "
        f'File it with serves: ["{tid}"], or pass with a reason.'
    )


def stalled_line(version: Any, target: Mapping, wakes: int) -> str:
    return _clip(
        f"Plan v{version} target {target.get('id')} is stalled: its owner {target.get('owner')} was woken "
        f"{wakes} times and the position stayed at {_num(target.get('position'))} "
        f"(want {_num(target.get('want_units'))}). Lower it, re-scope it or drop it (a plan_change if this "
        "season already has a version), or pass with a reason."
    )


# ---------------------------------------------------------------------------
# The watch
# ---------------------------------------------------------------------------


def evaluate(
    status: Optional[Mapping[str, Any]], tick: Optional[int], policy: PlanPolicy, state: PlanWatchState,
    edge: Optional[SeasonEdge], *, held: bool = False, frozen_types: Optional[Iterable[str]] = None,
    retry_tick: Optional[int] = None,
) -> PlanWatchResult:
    """Fold one `plan.status` read into `state` and return the wakes owed. A
    `None` status (the read failed) or an unknown tick changes nothing and
    wakes nobody. Pure over its arguments: `state` is the only thing mutated,
    and the caller decides whether to save it (a dry run does not)."""
    out = PlanWatchResult()
    if not policy.enabled or not isinstance(status, Mapping) or tick is None:
        return out
    base, cap = policy.renotify_ticks, policy.renotify_cap_ticks
    # The backoffs read the retry clock (conductor/backoff.py RetryClock), which
    # also runs while the fort is paused; positions and `since` stay on `tick`.
    rt = retry_tick if retry_tick is not None else tick
    active = status.get("active") if isinstance(status.get("active"), Mapping) else None
    rm = status.get("roadmap") if isinstance(status.get("roadmap"), Mapping) else None
    if rm is not None:
        out.roadmap = dict(rm)
    stage = rm.get("stage") if rm is not None and isinstance(rm.get("stage"), str) and rm.get("stage") else None
    if rm is not None:
        for c in rm.get("cross_check") or []:
            if isinstance(c, Mapping) and c.get("state") == "disagree":
                out.notes.append(
                    f"roadmap: the game's population flag ({c.get('requires_population')}) disagrees with alive "
                    f"{_num(c.get('alive'))}; reported, not acted on"
                )

    # ---- bootstrap (F-19) -------------------------------------------------
    if status.get("bootstrap") is True:
        b = state.bootstrap
        if state.bootstrap_escalated:
            out.notes.append("bootstrap: escalated to the operator, not waking the Planner")
        elif _due(b, rt, cap):
            if b.wakes >= policy.bootstrap_escalate_after:
                state.bootstrap_escalated = True
                out.alerts.append(
                    f"The Planner was woken {b.wakes} times and no plan exists. Last refusal: "
                    f"{state.last_refusal or 'none recorded (the runs may have failed before filing)'}. "
                    "File version 1 by hand or fix the cause; the conductor will not wake the Planner again "
                    "until a plan exists."
                )
            else:
                _note_wake(b, rt, base, cap)
                out.wakes.append(PlanWake(
                    REASON_BOOTSTRAP, PLANNER,
                    f"The fort has no plan (attempt {b.wakes} of {policy.bootstrap_escalate_after}). Read plan.read "
                    "(it returns the default plan to start from), then file version 1 with plan.write base_version 0: "
                    "dry run first.",
                    key="bootstrap",
                ))
    else:
        # A plan exists: the bootstrap is over and re-arms from scratch.
        state.bootstrap = Backoff()
        state.bootstrap_escalated = False
        state.last_refusal = None

    if active is None:
        # Nothing below applies before version 1; version 1 is composed from
        # the current stage, so no adoption is owed.
        state.review_index = None
        if stage:
            state.roadmap_stage, state.roadmap_owed, state.roadmap_since = stage, None, None
            state.roadmap = Backoff()
        return out

    version = active.get("version")

    # ---- a new roadmap stage the plan was not filed for ---------------------
    if stage:
        plan_stage = active.get("roadmap_stage")
        # Owed whenever the plan's stamp (a missing one included) differs from
        # the current stage, whatever the stored cursor says: a first
        # observation is not a baseline. A stage change re-owes; a pass for
        # this stage (roadmap_passed) stops the re-owing until the next change.
        if plan_stage == stage:
            state.roadmap_owed, state.roadmap_since, state.roadmap_passed = None, None, None
            state.roadmap = Backoff()
        elif state.roadmap_stage != stage:
            state.roadmap_owed, state.roadmap_since, state.roadmap = stage, int(tick), Backoff()
            state.roadmap_passed = None
        elif state.roadmap_owed != stage and not _passed_for(state.roadmap_passed, stage):
            state.roadmap_owed, state.roadmap_since, state.roadmap = stage, int(tick), Backoff()
        state.roadmap_stage = stage
        if state.roadmap_owed is not None:
            # A pass is recorded ONLY from `last_pass_tick`, the tick of an
            # explicit Planner `queue.pass`. `last_reviewed_tick` also folds in
            # the active plan's own filing tick, which on a paused fort equals
            # the current tick and read as a pass (live bug 2026-10-08). A
            # server without `last_pass_tick` never yields a pass.
            pass_tick = status.get("last_pass_tick")
            passed = (
                isinstance(pass_tick, int) and not isinstance(pass_tick, bool)
                and state.roadmap_since is not None and pass_tick >= state.roadmap_since
            )
            if passed:
                state.roadmap_passed = f"{state.roadmap_owed}@{pass_tick}"
            done = plan_stage == state.roadmap_owed or passed
            if done:
                state.roadmap_owed, state.roadmap_since, state.roadmap = None, None, Backoff()
            elif state.roadmap.wakes < policy.review_max_wakes and _due(state.roadmap, rt, cap):
                _note_wake(state.roadmap, rt, base, cap)
                summary = f" ({rm.get('summary')})" if isinstance(rm.get("summary"), str) and rm.get("summary") else ""
                filed = f"for the {plan_stage} stage" if isinstance(plan_stage, str) else "before stages existed"
                out.wakes.append(PlanWake(
                    REASON_STAGE, PLANNER,
                    f"The fort is in the {state.roadmap_owed} stage{summary}; the active plan (v{version}) was "
                    f"filed {filed}. "
                    "Read plan.read (its roadmap block lists the stage's targets and rationale), then adopt them "
                    "with plan.write (dry run first): a revision that only adopts the stage's targets is allowed "
                    "this season. A target that differs from its entry needs a deviation_reason. Or pass with a reason.",
                    key=f"stage-{state.roadmap_owed}",
                ))

    # ---- season review ----------------------------------------------------
    if edge is not None and (edge.changed or edge.first):
        a_season = active.get("season_index")
        if isinstance(a_season, int) and a_season < edge.index and state.review_index != edge.index:
            state.review_index = edge.index
            state.review_since = int(tick)
            state.review = Backoff()
    if state.review_index is not None:
        a_season = active.get("season_index")
        reviewed = status.get("last_pass_tick")   # explicit pass only: last_reviewed_tick folds in the plan filing tick
        done = (
            (isinstance(a_season, int) and a_season >= state.review_index)
            or (isinstance(reviewed, int) and not isinstance(reviewed, bool) and state.review_since is not None and reviewed >= state.review_since)
        )
        if done:
            state.review_index = None
            state.review_since = None
            state.review = Backoff()
        elif state.review.wakes < policy.review_max_wakes and _due(state.review, rt, cap):
            _note_wake(state.review, rt, base, cap)
            out.wakes.append(PlanWake(
                REASON_REVIEW, PLANNER,
                f"Season {state.review_index} has begun and the active plan (v{version}) is from season "
                f"{active.get('season_index')}. Review it against the digest: file a new version with plan.write "
                "(dry run first), or pass with a reason.",
                key=f"season-{state.review_index}",
            ))

    # ---- an accepted plan_change nobody has cited -------------------------
    awaiting = [a for a in status.get("plan_changes_awaiting") or [] if isinstance(a, Mapping)]
    live_ids = {str(a.get("ruling_id")) for a in awaiting}
    for rid in [r for r in state.awaiting if r not in live_ids]:
        del state.awaiting[rid]
    for a in awaiting:
        rid = str(a.get("ruling_id"))
        b = state.awaiting.setdefault(rid, Backoff())
        if b.wakes < policy.awaiting_max_wakes and _due(b, rt, cap):
            _note_wake(b, rt, base, cap)
            out.wakes.append(PlanWake(
                REASON_RULING, PLANNER,
                f"{a.get('proposal_id')} (plan_change) was accepted by {rid}: file a plan version with "
                f'ruling_id "{rid}", or pass with a reason.',
                key=rid,
            ))

    # ---- the shortfall watch (ships off) ----------------------------------
    sw = policy.shortfall
    if not sw.enabled:
        return out
    if held:
        out.notes.append("shortfall watch: operator hold in force, no owner wakes")
        return out
    _shortfall(status, rt, version, sw, state, out, frozen_types)
    return out


def _shortfall(
    status: Mapping[str, Any], tick: int, version: Any, sw: Any, state: PlanWatchState,
    out: PlanWatchResult, frozen_types: Optional[Iterable[str]],
) -> None:
    owners = status.get("owners") if isinstance(status.get("owners"), Mapping) else {}
    #: owner -> [ceiling, in flight now (from plan.status), slots left this cycle]
    budget: Dict[str, List[int]] = {}

    def slot_state(owner: str) -> List[int]:
        if owner not in budget:
            row = owners.get(owner) if isinstance(owners.get(owner), Mapping) else {}
            ceiling = row.get("ceiling") if isinstance(row.get("ceiling"), int) else sw.owner_ceiling
            used = row.get("in_flight") if isinstance(row.get("in_flight"), int) else 0
            budget[owner] = [ceiling, used, ceiling - used]
        return budget[owner]

    seen_targets = set()
    seen_inputs = set()
    for t in status.get("targets") or []:
        if not isinstance(t, Mapping) or not isinstance(t.get("id"), str):
            continue
        tid = t["id"]
        seen_targets.add(tid)
        ts = state.targets.get(tid)
        if ts is None or ts.version != version:
            carried = ts.suppress_until if ts is not None else 0
            ts = TargetState(version=version, suppress_until=carried)
            state.targets[tid] = ts
        tstate = t.get("state")
        if tstate == "inert" or not isinstance(t.get("owner"), str):
            continue

        # Derived inputs go to the input's owner, on their own backoff. They
        # follow the work in flight, not the target's own open state: a target
        # whose in-flight rooms already reach its want is closed, and still
        # needs its beds.
        for item in t.get("inputs") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("owner"), str):
                continue
            short = item.get("short")
            if not isinstance(short, (int, float)) or isinstance(short, bool) or short <= 0:
                continue
            key = f"{tid}:{item.get('item')}"
            seen_inputs.add(key)
            ib = state.inputs.setdefault(key, Backoff())
            if ib.stalled or not _due(ib, tick, sw.renotify_cap_ticks):
                continue
            if ib.wakes > 0 and float(short) != ib.last_position:
                state.inputs[key] = ib = Backoff()  # the shortage changed: start over
            if ib.wakes >= sw.stall_after:
                ib.stalled = True  # given up for this shortage; the owner has been told enough
                continue
            _note_wake(ib, tick, sw.renotify_ticks, sw.renotify_cap_ticks, float(short))
            out.wakes.append(PlanWake(REASON_INPUT_SHORT, item["owner"], input_line(version, t, item), key=key))

        if tstate == "unresolved":
            continue  # a target that cannot be measured is never a shortfall
        position = t.get("position")
        position = float(position) if isinstance(position, (int, float)) and not isinstance(position, bool) else None
        serving_ids = [str(s.get("proposal_id")) for s in t.get("serving") or [] if isinstance(s, Mapping)]

        # Rejection: a serving proposal vanished and the position fell.
        vanished = set(ts.seen_serving) - set(serving_ids)
        if vanished and position is not None and ts.prev_position is not None and position < ts.prev_position:
            ts.suppress_version = version
            ts.suppress_until = tick + min(
                sw.renotify_cap_ticks, sw.renotify_ticks * (2 ** max(0, ts.backoff.wakes - 1)),
            )
            out.notes.append(
                f"{tid}: a serving proposal ({', '.join(sorted(vanished))}) left and the position fell; renotify suppressed"
            )
        ts.seen_serving = serving_ids
        ts.prev_position = position

        # Open on the reorder level, close only at want (never rounded).
        if not ts.open:
            if tstate != "open":
                continue
            ts.open, ts.backoff, ts.planner_told = True, Backoff(), False
        elif t.get("below_want") is False:
            ts.open, ts.backoff, ts.planner_told = False, Backoff(), False
            ts.suppress_version = None
            continue

        owner = t["owner"]
        ceiling, used, remaining = slot_state(owner)
        reason = None
        if t.get("at_max_in_flight"):
            reason = "holds its max in flight"
        elif _frozen(t.get("signal"), sw.serving_types, frozen_types):
            reason = "the owner's group is frozen"
        elif ts.suppress_version == version or tick < ts.suppress_until:
            reason = "a serving proposal was rejected"
        elif ts.backoff.stalled:
            reason = "stalled"
        elif remaining <= 0:
            reason = f"{owner}'s plan budget is used"
        if reason is not None:
            out.notes.append(f"{tid}: no owner wake ({reason})")
            continue
        if not _due(ts.backoff, tick, sw.renotify_cap_ticks):
            continue
        b = ts.backoff
        if b.wakes > 0 and position != b.last_position:
            ts.backoff = b = Backoff()  # the position moved: progress, start over
        if b.wakes >= sw.stall_after:
            b.stalled = True
            if not ts.planner_told:
                ts.planner_told = True
                out.wakes.append(PlanWake(REASON_STALLED, PLANNER, stalled_line(version, t, b.wakes), key=tid))
            continue
        _note_wake(b, tick, sw.renotify_ticks, sw.renotify_cap_ticks, position)
        budget[owner][2] = remaining - 1
        out.wakes.append(PlanWake(REASON_SHORTFALL, owner, shortfall_line(version, t, ceiling, used), key=tid))

    for tid in [k for k in state.targets if k not in seen_targets]:
        del state.targets[tid]
    for key in [k for k in state.inputs if k not in seen_inputs]:
        del state.inputs[key]
