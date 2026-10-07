"""The conductor's clock policy and wake-reason table: `docs/AGENT-LOOP.md`
§2 ("The game clock") and part of §4 ("Build items", row 1), read from
`conductor/policy.yaml` -- data, never literal-reason branches in
`conductor/cycle.py`.

## The three clock levels

`FULL_SPEED`, `SLOWED`, `PAUSED` (§2's table). `PAUSED` has no configured
`fps`: it means the fort is stopped, via `clock.pause`, never `clock.set-speed`
with some tiny number.

## The "closing in" rule, both ways

§2: "slow the fort only when the ticks until a consequence are fewer than a
few multiples of the expected thinking time, measured in ticks at the
current `base_fps`. ... The table is the fallback for wake reasons with no
computable deadline." `ticks_to_consequence_clock` is that rule in isolation
(given a tick count, or `None` for "not computable this cycle");
`clock_for_reason` is the one entry point `conductor/cycle.py` actually
calls, which picks the computed rule when the reason is computable and a
real tick count was supplied, and the fallback table otherwise -- covering
both directions the handoff asks to test: a reason close enough to slow, and
the same reason far enough (or uncomputable) to stay at the fallback.

## "The most urgent live reason wins"

§2, verbatim. `most_urgent` orders `PAUSED > SLOWED > FULL_SPEED` and reduces
a cycle's live set of clock levels (one per wake reason actually in play) to
the one the conductor should actually set. An empty set means nothing urgent
is being deliberated, which §2 says restores `base_fps` -- `most_urgent(())
== FULL_SPEED` encodes exactly that, so the caller never needs a separate
"nothing urgent" branch.

## Expected thinking time: measured, not fixed

§1's build item: "Expected thinking time starts as a config value and is
measured from each run's wall-clock and updated (a moving figure, logged)."
`update_expected_thinking_seconds` is that update rule: an exponentially
weighted moving average, not a plain overwrite, so one unusually slow or
fast run does not itself become next cycle's whole expectation.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Tuple

import yaml

from conductor.backoff import Backoff

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "policy.yaml"

FULL_SPEED = "full_speed"
SLOWED = "slowed"
PAUSED = "paused"
CLOCK_LEVELS = (FULL_SPEED, SLOWED, PAUSED)

#: Ordering for `most_urgent` -- higher wins. PAUSED is the most urgent
#: level a wake-reason table entry can name; a tripwire latch itself is
#: handled separately in conductor/cycle.py (it pauses the fort directly,
#: inside the game loop, independent of this table -- docs/AGENT-LOOP.md §3).
_URGENCY = {FULL_SPEED: 0, SLOWED: 1, PAUSED: 2}

#: The moving-average weight for update_expected_thinking_seconds: how much
#: one new measurement moves the figure. 0.3 is this stream's own reasoned
#: default (not sourced from anywhere -- no real run has been measured yet),
#: chosen so three or four consecutive slow runs visibly move the figure
#: within a handful of cycles without one outlier swinging it wildly.
THINKING_TIME_EWMA_WEIGHT = 0.3


class PolicyError(Exception):
    """`conductor/policy.yaml` is missing a required value or names a clock
    level outside `CLOCK_LEVELS`. Always a hard failure at load time, never
    a silent default -- the conductor must not run with a guessed policy."""


@dataclass(frozen=True)
class WakeReasonPolicy:
    reason: str
    clock: str
    wakes: Tuple[str, ...]
    computable: bool = False


#: What a threshold alert may divide its value by (`per`): nothing, or the
#: fort's live citizen count (vitals.summary's `alive`).
ALERT_PER = (None, "alive")


@dataclass(frozen=True)
class ThresholdAlert:
    """docs/CONDUCTOR-EXECUTION.md 3.3: a briefing line shown only while a read
    value (divided by `per`, if set) is below `below`. Pure data: the tool, its
    arguments and the dotted field path are read generically, never by an
    item-specific branch."""
    name: str
    tool: str
    args: Mapping
    field: str
    below: float
    text: str
    per: Optional[str] = None
    #: Generic default for a field that is absent from a SUCCESSFUL read (a
    #: count keyed by kind is simply missing when nothing of that kind
    #: exists). `None` keeps the old behaviour: an absent field drops the
    #: line. A failed read always drops the line, whatever this says.
    missing_leaf: Optional[float] = None


@dataclass(frozen=True)
class EventLane:
    """One diff.since event kind a role's lane watches: `type` is the event's
    own `type`; `detail_matches` (regexes, case-insensitive, any one) narrows
    it by the event's `detail`, empty meaning every event of that type."""
    type: str
    detail_matches: Tuple["re.Pattern", ...] = ()


@dataclass(frozen=True)
class UnsuppliedPolicy:
    """Backoff for the unsupplied-building wake (policy.yaml `unsupplied_building`;
    research/2026-10-07-wake-audit.md rec 3): wake when a kind first appears, then
    again after `base_ticks`, doubling each time up to `cap_ticks`, and mark it
    stalled (no more wakes) after `max_wakes` wakes."""
    base_ticks: int = 6000
    cap_ticks: int = 100800
    max_wakes: int = 3


@dataclass(frozen=True)
class LaneTriggers:
    """What counts as a change in one role's own lane (handoffs/2026-10-05-
    stricter-wakes.md). Pure data; conductor/lanes.py reads it generically.
    `events`: drained diff events in the role's OWN drain. `stuck_jobs`:
    regexes over a due stuck job's type and description. `alerts`: threshold
    alert names whose fresh crossing wakes the role (`"*"` for any). `rulings`:
    a ruling on a proposal this role filed. `ore`: an ore or gem newly exposed
    on a dug room's walls (handoffs/2026-10-05-ore-exposed-signal.md)."""
    events: Tuple[EventLane, ...] = ()
    stuck_jobs: Tuple["re.Pattern", ...] = ()
    alerts: Tuple[str, ...] = ()
    rulings: bool = False
    ore: bool = False
    #: A planned building waits on an item kind nobody makes
    #: (handoffs/2026-10-07-unsupplied-building-watch.md).
    unsupplied: bool = False
    #: The role is told of its routed projects' progress and holds
    #: (`step_done`, `step_attention`, `project_idle`) when the project's
    #: proposer is unknown to the conductor (docs/CONDUCTOR-EXECUTION.md 5).
    execution: bool = False


@dataclass(frozen=True)
class ExecutionPolicy:
    """The execute phase's knobs (policy.yaml `execution`, docs/CONDUCTOR-
    EXECUTION.md 4 and 5), all data. Game ticks are raw ticks."""
    #: Real calls to `queue.run_step` per cycle, a cap on the whole phase.
    max_steps_per_cycle: int = 4
    #: A project with every step done and no follow-up: one `project_idle` wake
    #: after this many ticks, closed (`completed`, idle) after the same again.
    idle_wake_ticks: int = 8400
    idle_close_ticks: int = 8400
    #: Unreadable resolutions of one Uncertain run before it is held.
    uncertain_hold_after: int = 3
    #: Consecutive transient results before a step goes to its proposer.
    transient_attention_after: int = 3
    #: Consecutive `unknown` reads of an issued step before its proposer is told.
    unknown_attention_after: int = 3
    #: Phase labels matching this wait on exposed ore before they run.
    ore_hold_phase: Optional["re.Pattern"] = None
    #: Ready steps run in this urgency order, then oldest first.
    urgency_order: Tuple[str, ...] = ("high", "normal", "low")
    #: A refused open or apply is tried at most this many times.
    refusal_limit: int = 3


@dataclass(frozen=True)
class ShortfallWatchPolicy:
    """The plan shortfall watch (conductor/plan_watch.py). Ships OFF
    (`enabled: false`, user's call 2026-10-07, planner open question 3) so the
    Planner's first version can be read before anything it says wakes an owner.
    Ticks are raw game ticks."""
    enabled: bool = False
    #: First renotify interval; it doubles per consecutive renotify with no
    #: change in position, capped at `renotify_cap_ticks` (one season).
    renotify_ticks: int = 12000
    renotify_cap_ticks: int = 100800
    #: Owner wakes per target per plan version while the position never moves
    #: (the opening wake counts); then the target is `stalled`, stops waking its
    #: owner, and wakes the Planner once.
    stall_after: int = 3
    #: In-flight plan work allowed per owner when `plan.status` names no
    #: ceiling for it (mirrors dfqueue/plan_policy.yaml `in_flight_per_owner`).
    owner_ceiling: int = 2
    #: Per signal family (the part before the first dot), the proposal types
    #: that serve a target; an owner whose family types are all frozen is not
    #: woken (a frozen group takes no proposals). Data, so a new family is
    #: one entry. Mirrors dfqueue/plan_policy.yaml `family_serving_types`.
    serving_types: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class PlanPolicy:
    """The Planner's conductor-side wiring (handoffs/2026-10-07-planner-p1b.md),
    its own top-level block `plan:` in policy.yaml."""
    #: Master switch for everything that needs the Planner role: the
    #: `plan.status` read each cycle, the bootstrap, review and ruling wakes
    #: and the shortfall watch (itself behind `shortfall_watch.enabled`). Off
    #: until the supervised first plan (the enable commit flips it).
    enabled: bool = False
    #: The season length in game ticks (a DF season is 100,800), for the
    #: computed season index. Must match dfqueue/plan_policy.yaml `season_ticks`.
    season_ticks: int = 100800
    #: Compute the season index from the tick and raise `season_change` (the
    #: Quartermaster's wake) when it changes. Independent of `enabled`: it needs
    #: only the game tick, not the Planner.
    season_wake: bool = True
    #: Retry interval for a Planner wake that did not resolve its cause (no
    #: plan yet, a review not done, an accepted plan_change not cited): it
    #: doubles per wake, capped at `renotify_cap_ticks`.
    renotify_ticks: int = 12000
    renotify_cap_ticks: int = 100800
    #: No active plan: after this many wakes that left no plan, tell the
    #: operator with the last refusal text instead of waking again.
    bootstrap_escalate_after: int = 3
    #: Wakes for an owed season review, and for one accepted plan_change, before
    #: each is left alone (the next season or version re-arms it).
    review_max_wakes: int = 3
    awaiting_max_wakes: int = 3
    shortfall: ShortfallWatchPolicy = field(default_factory=ShortfallWatchPolicy)


@dataclass(frozen=True)
class Policy:
    base_fps: int
    think_fps: int
    closing_in_multiple: float
    expected_thinking_seconds: float
    routine_review_interval_game_days: int
    #: handoffs/2026-09-23-stalled-order-poller.md, conductor/order_watch.py.
    #: Raw game ticks, not game days -- see policy.yaml's own comment.
    stalled_order_threshold_ticks: int
    stalled_order_renotify_ticks: int
    wake_reasons: Dict[str, WakeReasonPolicy]
    #: Re-read the queue after the advisors run and wake the Consultant for an
    #: ask they filed this cycle (see conductor/cycle.py's role loop).
    consultant_rewake_after_advisors: bool = True
    #: Per-role cap on one `agent exec` run, seconds. Roles absent here use
    #: the service-wide `CONDUCTOR_ROLE_TIMEOUT_SECONDS`.
    role_timeout_seconds: Dict[str, float] = field(default_factory=dict)
    #: handoffs/2026-10-05-stuck-job-watch.md, conductor/job_watch.py. Raw game
    #: ticks. Optional with defaults so a policy file predating the watch loads.
    stuck_job_unclaimed_threshold_ticks: int = 2400
    stuck_job_suspended_threshold_ticks: int = 2400
    stuck_job_renotify_ticks: int = 12000
    #: handoffs/2026-10-05-ore-exposed-signal.md, conductor/ore_watch.py: a
    #: vein that is still exposed this many game ticks after it first woke the
    #: Architect wakes it once more (the backstop for a ruled-but-not-mined
    #: case). 12000 = 10 game days.
    ore_renotify_ticks: int = 12000
    #: handoffs/2026-10-07-unsupplied-building-watch.md (its own policy block).
    unsupplied_building: UnsuppliedPolicy = field(default_factory=UnsuppliedPolicy)
    #: Threshold alerts for every role's briefing (policy.yaml `threshold_alerts`).
    threshold_alerts: Tuple[ThresholdAlert, ...] = ()
    #: Per-role lane triggers (policy.yaml `lane_triggers`). Empty: no lane
    #: filtering, every wake reason wakes the roles its table entry names.
    lane_triggers: Dict[str, LaneTriggers] = field(default_factory=dict)
    #: Stage T (handoffs/2026-10-06-stage-t-tripwire.md): per latch reason, the
    #: roles that run BEFORE the Overseer after a tripwire. A reason absent
    #: here (an unknown cause included) has no owner and wakes the Overseer
    #: alone; the Overseer always runs last and always gives the verdict.
    tripwire_owners: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    #: The same cause latching more than `tripwire_repeat_limit` times within
    #: `tripwire_repeat_window_ticks` game ticks goes to the human instead of
    #: re-running the sequence.
    tripwire_repeat_limit: int = 3
    tripwire_repeat_window_ticks: int = 4800
    #: The execute phase (docs/CONDUCTOR-EXECUTION.md 4.5, 5).
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    #: The Planner's wiring (policy.yaml `plan`).
    plan: PlanPolicy = field(default_factory=PlanPolicy)
    #: How many of a proposer's newest filings its briefing shows (policy.yaml
    #: `own_filings.recent`); 0 turns the block off.
    own_filings_recent: int = 5
    #: queue_pending is an edge (research/2026-10-07-wake-audit.md rec 1): a
    #: proposal the Overseer already saw and left pending (a defer) does not
    #: wake it again until something observable changed, or after this many
    #: cycles as a backstop. Counted in the conductor's own persisted cycle
    #: counter, not ticks (ticks freeze under a hold and race at 100 FPS).
    overseer_defer_recheck_cycles: int = 12
    #: Renotify backoff shared by every standing wake (conductor/backoff.py): the
    #: wait before the second wake is the reason's own base (`stalled_order_
    #: renotify_ticks`, `stuck_job_renotify_ticks`, `ore_renotify_ticks`,
    #: `alert_renotify_ticks`), doubling per wake up to `renotify_cap_ticks`
    #: (one season), and the fact is stalled (no more wakes) after
    #: `renotify_max_wakes` wakes.
    renotify_cap_ticks: int = 100800
    renotify_max_wakes: int = 3
    alert_renotify_ticks: int = 12000

    def backoff(self, base_ticks: int) -> Backoff:
        """The shared renotify rule with this reason's base wait."""
        return Backoff(base_ticks, self.renotify_cap_ticks, self.renotify_max_wakes)

    def reason(self, name: str) -> WakeReasonPolicy:
        try:
            return self.wake_reasons[name]
        except KeyError:
            raise PolicyError(
                f"{name!r} is not a wake reason in this policy config "
                f"(known: {sorted(self.wake_reasons)})"
            ) from None

    def with_expected_thinking_seconds(self, value: float) -> "Policy":
        """A new `Policy` with only `expected_thinking_seconds` replaced --
        used by `update_expected_thinking_seconds` below. `Policy` is frozen
        (dataclasses.replace-friendly) so the moving figure is always an
        explicit, auditable transition, never an in-place mutation a test
        (or a later reader of a log line) could miss."""
        return replace(self, expected_thinking_seconds=value)


def _require(doc: Mapping, key: str, path: Path):
    if key not in doc:
        raise PolicyError(f"{path}: missing required key {key!r}")
    return doc[key]


def _patterns(raw, where: str) -> Tuple["re.Pattern", ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise PolicyError(f"{where} must be a list of regex strings")
    out = []
    for text in raw:
        try:
            out.append(re.compile(text, re.IGNORECASE))
        except re.error as exc:
            raise PolicyError(f"{where}: bad regex {text!r}: {exc}") from None
    return tuple(out)


def _load_lane_triggers(raw, path: Path) -> Dict[str, LaneTriggers]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: lane_triggers must be a mapping of role to triggers")
    lanes: Dict[str, LaneTriggers] = {}
    for role, entry in raw.items():
        where = f"{path}: lane_triggers.{role}"
        entry = entry or {}
        if not isinstance(entry, dict):
            raise PolicyError(f"{where} must be a mapping")
        events = []
        for i, ev in enumerate(entry.get("events") or []):
            if not isinstance(ev, dict) or not isinstance(ev.get("type"), str):
                raise PolicyError(f"{where}.events[{i}] needs a string `type`")
            events.append(EventLane(
                type=ev["type"], detail_matches=_patterns(ev.get("detail_matches"), f"{where}.events[{i}].detail_matches"),
            ))
        alerts = entry.get("alerts") or []
        if not isinstance(alerts, list) or not all(isinstance(x, str) for x in alerts):
            raise PolicyError(f"{where}.alerts must be a list of alert names")
        lanes[str(role)] = LaneTriggers(
            events=tuple(events),
            stuck_jobs=_patterns(entry.get("stuck_jobs"), f"{where}.stuck_jobs"),
            alerts=tuple(alerts),
            rulings=bool(entry.get("rulings", False)),
            ore=bool(entry.get("ore", False)),
            unsupplied=bool(entry.get("unsupplied", False)),
            execution=bool(entry.get("execution", False)),
        )
    return lanes


def _load_unsupplied(raw, path: Path) -> UnsuppliedPolicy:
    if raw is None:
        return UnsuppliedPolicy()
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: unsupplied_building must be a mapping")
    out = {}
    for key, default in (("base_ticks", 6000), ("cap_ticks", 100800), ("max_wakes", 3)):
        v = raw.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise PolicyError(f"{path}: unsupplied_building.{key} must be a positive integer")
        out[key] = v
    if out["cap_ticks"] < out["base_ticks"]:
        raise PolicyError(f"{path}: unsupplied_building.cap_ticks must be at least base_ticks")
    return UnsuppliedPolicy(**out)


def _load_execution(raw, path: Path) -> ExecutionPolicy:
    if raw is None:
        return ExecutionPolicy()
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: execution must be a mapping")
    base = ExecutionPolicy()
    ints = {}
    for key in ("max_steps_per_cycle", "idle_wake_ticks", "idle_close_ticks", "uncertain_hold_after",
                "transient_attention_after", "unknown_attention_after", "refusal_limit"):
        value = raw.get(key, getattr(base, key))
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise PolicyError(f"{path}: execution.{key} must be a positive integer")
        ints[key] = value
    order = raw.get("urgency_order", list(base.urgency_order))
    if not isinstance(order, list) or not order or not all(isinstance(x, str) for x in order):
        raise PolicyError(f"{path}: execution.urgency_order must be a list of urgency names")
    pattern = raw.get("ore_hold_phase")
    compiled = None
    if pattern is not None:
        if not isinstance(pattern, str):
            raise PolicyError(f"{path}: execution.ore_hold_phase must be a regex string")
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise PolicyError(f"{path}: execution.ore_hold_phase is not a valid regex: {exc}") from None
    return ExecutionPolicy(ore_hold_phase=compiled, urgency_order=tuple(order), **ints)


#: Roles a tripwire owner may name (the roster; the Overseer is implicit).
_OWNER_ROLES = ("architect", "quartermaster", "consultant", "overseer", "planner")


def _load_tripwire_owners(raw, path: Path) -> Dict[str, Tuple[str, ...]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: tripwire_owners must be a mapping of latch reason to roles")
    out: Dict[str, Tuple[str, ...]] = {}
    for reason, roles in raw.items():
        where = f"{path}: tripwire_owners.{reason}"
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise PolicyError(f"{where} must be a list of role names")
        for r in roles:
            if r not in _OWNER_ROLES:
                raise PolicyError(f"{where}: {r!r} is not a role (known: {list(_OWNER_ROLES)})")
        # The Overseer runs last regardless; naming it here is a statement of
        # intent, not an extra run.
        out[str(reason)] = tuple(dict.fromkeys(r for r in roles if r != "overseer"))
    return out


def _load_tripwire_repeat(raw, path: Path) -> Tuple[int, int]:
    if raw is None:
        return 3, 4800
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: tripwire_repeat must be a mapping")
    out = []
    for key, default in (("limit", 3), ("window_ticks", 4800)):
        v = raw.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise PolicyError(f"{path}: tripwire_repeat.{key} must be a positive integer")
        out.append(v)
    return out[0], out[1]


def _pos_int(raw: Mapping, key: str, default: int, where: str) -> int:
    v = raw.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise PolicyError(f"{where}.{key} must be a positive integer")
    return v


def _flag(raw: Mapping, key: str, default: bool, where: str) -> bool:
    v = raw.get(key, default)
    if not isinstance(v, bool):
        raise PolicyError(f"{where}.{key} must be true or false")
    return v


def _load_plan(raw, path: Path) -> PlanPolicy:
    """The `plan:` block. Absent means everything off (a policy file that
    predates the Planner loads unchanged)."""
    if raw is None:
        return PlanPolicy()
    where = f"{path}: plan"
    if not isinstance(raw, dict):
        raise PolicyError(f"{where} must be a mapping")
    sraw = raw.get("shortfall_watch") or {}
    if not isinstance(sraw, dict):
        raise PolicyError(f"{where}.shortfall_watch must be a mapping")
    swhere = f"{where}.shortfall_watch"
    types = sraw.get("serving_types") or {}
    if not isinstance(types, dict) or not all(
        isinstance(v, list) and all(isinstance(t, str) for t in v) for v in types.values()
    ):
        raise PolicyError(f"{swhere}.serving_types must map a signal family to a list of proposal types")
    base = ShortfallWatchPolicy()
    shortfall = ShortfallWatchPolicy(
        enabled=_flag(sraw, "enabled", base.enabled, swhere),
        renotify_ticks=_pos_int(sraw, "renotify_ticks", base.renotify_ticks, swhere),
        renotify_cap_ticks=_pos_int(sraw, "renotify_cap_ticks", base.renotify_cap_ticks, swhere),
        stall_after=_pos_int(sraw, "stall_after", base.stall_after, swhere),
        owner_ceiling=_pos_int(sraw, "owner_ceiling", base.owner_ceiling, swhere),
        serving_types={str(k): tuple(v) for k, v in types.items()},
    )
    pb = PlanPolicy()
    return PlanPolicy(
        enabled=_flag(raw, "enabled", pb.enabled, where),
        season_ticks=_pos_int(raw, "season_ticks", pb.season_ticks, where),
        season_wake=_flag(raw, "season_wake", pb.season_wake, where),
        renotify_ticks=_pos_int(raw, "renotify_ticks", pb.renotify_ticks, where),
        renotify_cap_ticks=_pos_int(raw, "renotify_cap_ticks", pb.renotify_cap_ticks, where),
        bootstrap_escalate_after=_pos_int(raw, "bootstrap_escalate_after", pb.bootstrap_escalate_after, where),
        review_max_wakes=_pos_int(raw, "review_max_wakes", pb.review_max_wakes, where),
        awaiting_max_wakes=_pos_int(raw, "awaiting_max_wakes", pb.awaiting_max_wakes, where),
        shortfall=shortfall,
    )


def load_policy(path: "Path | str" = DEFAULT_POLICY_PATH) -> Policy:
    """Load and validate `conductor/policy.yaml` (or an override path, e.g.
    a test fixture). Raises `PolicyError` for anything malformed -- a typo
    in a clock level, a missing key -- rather than defaulting silently."""
    path = Path(path)
    if not path.is_file():
        raise PolicyError(f"{path}: no such policy file")
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}

    wake_reasons: Dict[str, WakeReasonPolicy] = {}
    raw_reasons = doc.get("wake_reasons") or {}
    if not isinstance(raw_reasons, dict):
        raise PolicyError(f"{path}: wake_reasons must be a mapping")
    for name, entry in raw_reasons.items():
        entry = entry or {}
        clock = entry.get("clock")
        if clock not in CLOCK_LEVELS:
            raise PolicyError(
                f"{path}: wake_reasons.{name}.clock is {clock!r}, "
                f"must be one of {CLOCK_LEVELS}"
            )
        wakes = entry.get("wakes") or []
        if not isinstance(wakes, list):
            raise PolicyError(f"{path}: wake_reasons.{name}.wakes must be a list")
        wake_reasons[name] = WakeReasonPolicy(
            reason=name, clock=clock, wakes=tuple(wakes),
            computable=bool(entry.get("computable", False)),
        )

    alerts = []
    raw_alerts = doc.get("threshold_alerts") or []
    if not isinstance(raw_alerts, list):
        raise PolicyError(f"{path}: threshold_alerts must be a list")
    for i, entry in enumerate(raw_alerts):
        where = f"{path}: threshold_alerts[{i}]"
        if not isinstance(entry, dict):
            raise PolicyError(f"{where} must be a mapping")
        read = entry.get("read")
        if not isinstance(read, dict) or not read.get("tool") or not read.get("field"):
            raise PolicyError(f"{where}.read needs a tool and a field")
        args = read.get("args") or {}
        if not isinstance(args, dict):
            raise PolicyError(f"{where}.read.args must be a mapping")
        per = entry.get("per")
        if per not in ALERT_PER:
            raise PolicyError(f"{where}.per is {per!r}, must be one of {ALERT_PER}")
        try:
            below = float(entry["below"])
        except (KeyError, TypeError, ValueError):
            raise PolicyError(f"{where}.below must be a number") from None
        text = entry.get("text")
        if not isinstance(text, str) or not text:
            raise PolicyError(f"{where}.text must be a non-empty string")
        missing = entry.get("missing_leaf")
        if missing is not None:
            if isinstance(missing, bool) or not isinstance(missing, (int, float)):
                raise PolicyError(f"{where}.missing_leaf must be a number")
            missing = float(missing)
        alerts.append(ThresholdAlert(
            name=str(entry.get("name") or f"alert-{i}"), tool=str(read["tool"]), args=dict(args),
            field=str(read["field"]), below=below, text=text, per=per, missing_leaf=missing,
        ))

    lane_triggers = _load_lane_triggers(doc.get("lane_triggers"), path)
    tripwire_owners = _load_tripwire_owners(doc.get("tripwire_owners"), path)
    repeat_limit, repeat_window = _load_tripwire_repeat(doc.get("tripwire_repeat"), path)
    execution = _load_execution(doc.get("execution"), path)
    plan = _load_plan(doc.get("plan"), path)
    own_raw = doc.get("own_filings") or {}
    if not isinstance(own_raw, dict):
        raise PolicyError(f"{path}: own_filings must be a mapping")
    own_recent = own_raw.get("recent", 5)
    if isinstance(own_recent, bool) or not isinstance(own_recent, int) or own_recent < 0:
        raise PolicyError(f"{path}: own_filings.recent must be a non-negative integer")

    return Policy(
        own_filings_recent=own_recent,
        overseer_defer_recheck_cycles=_pos_int(doc, "overseer_defer_recheck_cycles", 12, str(path)),
        renotify_cap_ticks=_pos_int(doc, "renotify_cap_ticks", 100800, str(path)),
        renotify_max_wakes=_pos_int(doc, "renotify_max_wakes", 3, str(path)),
        alert_renotify_ticks=_pos_int(doc, "alert_renotify_ticks", 12000, str(path)),
        tripwire_owners=tripwire_owners,
        tripwire_repeat_limit=repeat_limit,
        tripwire_repeat_window_ticks=repeat_window,
        lane_triggers=lane_triggers,
        execution=execution,
        plan=plan,
        threshold_alerts=tuple(alerts),
        base_fps=int(_require(doc, "base_fps", path)),
        think_fps=int(_require(doc, "think_fps", path)),
        closing_in_multiple=float(_require(doc, "closing_in_multiple", path)),
        expected_thinking_seconds=float(_require(doc, "expected_thinking_seconds", path)),
        routine_review_interval_game_days=int(
            _require(doc, "routine_review_interval_game_days", path)
        ),
        stalled_order_threshold_ticks=int(
            _require(doc, "stalled_order_threshold_ticks", path)
        ),
        stalled_order_renotify_ticks=int(
            _require(doc, "stalled_order_renotify_ticks", path)
        ),
        wake_reasons=wake_reasons,
        consultant_rewake_after_advisors=bool(doc.get("consultant_rewake_after_advisors", True)),
        stuck_job_unclaimed_threshold_ticks=int(doc.get("stuck_job_unclaimed_threshold_ticks", 2400)),
        stuck_job_suspended_threshold_ticks=int(doc.get("stuck_job_suspended_threshold_ticks", 2400)),
        stuck_job_renotify_ticks=int(doc.get("stuck_job_renotify_ticks", 12000)),
        ore_renotify_ticks=int(doc.get("ore_renotify_ticks", 12000)),
        unsupplied_building=_load_unsupplied(doc.get("unsupplied_building"), path),
        role_timeout_seconds={str(k): float(v) for k, v in (doc.get("role_timeout_seconds") or {}).items()},
    )


def ticks_to_consequence_clock(
    ticks_to_consequence: Optional[int], policy: Policy, *, base_fps: Optional[int] = None,
) -> str:
    """§2's "closing in" rule in isolation. `None` (no computable deadline
    this cycle) always returns `FULL_SPEED` -- the caller (`clock_for_reason`)
    is what falls back to the reason's own table entry in that case, not
    this function, so this one function stays a pure, single-purpose rule
    that a test can drive both ways with a plain tick count."""
    if ticks_to_consequence is None:
        return FULL_SPEED
    if ticks_to_consequence < 0:
        raise PolicyError(f"ticks_to_consequence must not be negative, got {ticks_to_consequence}")
    fps = base_fps if base_fps is not None else policy.base_fps
    expected_thinking_ticks = policy.expected_thinking_seconds * fps
    threshold = policy.closing_in_multiple * expected_thinking_ticks
    return SLOWED if ticks_to_consequence < threshold else FULL_SPEED


def clock_for_reason(
    reason: str, policy: Policy, *, ticks_to_consequence: Optional[int] = None,
    base_fps: Optional[int] = None,
) -> str:
    """The one entry point `conductor/cycle.py` calls per live wake reason.
    Computed rule where the reason is marked `computable` in the policy
    config AND a real tick count is available; the fallback table entry
    otherwise (an uncomputable reason, or a computable one this cycle simply
    could not price -- `ticks_to_consequence=None`)."""
    rp = policy.reason(reason)
    if rp.computable and ticks_to_consequence is not None:
        return ticks_to_consequence_clock(ticks_to_consequence, policy, base_fps=base_fps)
    return rp.clock


def most_urgent(levels: Iterable[str]) -> str:
    """"The most urgent live reason wins" (§2). An empty `levels` means
    nothing urgent is being deliberated this cycle -- returns `FULL_SPEED`,
    which is what §2 calls "restore base_fps once nothing urgent is being
    deliberated", so the caller needs no separate empty-set branch."""
    levels = list(levels)
    if not levels:
        return FULL_SPEED
    for level in levels:
        if level not in _URGENCY:
            raise PolicyError(f"{level!r} is not a clock level ({CLOCK_LEVELS})")
    return max(levels, key=lambda lvl: _URGENCY[lvl])


def update_expected_thinking_seconds(policy: Policy, measured_seconds: float) -> Policy:
    """docs/AGENT-LOOP.md §1: "Expected thinking time starts as a config
    value and is measured from each run's wall-clock and updated (a moving
    figure, logged)." An exponentially weighted moving average
    (`THINKING_TIME_EWMA_WEIGHT`), never a plain overwrite -- see this
    module's own docstring for why. `conductor/cycle.py` is what actually
    logs the transition (old value, new value, the measurement that moved
    it); this function only computes the new figure."""
    if measured_seconds < 0:
        raise PolicyError(f"measured_seconds must not be negative, got {measured_seconds}")
    w = THINKING_TIME_EWMA_WEIGHT
    new_value = (1 - w) * policy.expected_thinking_seconds + w * measured_seconds
    return policy.with_expected_thinking_seconds(new_value)
