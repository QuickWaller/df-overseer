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


@dataclass(frozen=True)
class EventLane:
    """One diff.since event kind a role's lane watches: `type` is the event's
    own `type`; `detail_matches` (regexes, case-insensitive, any one) narrows
    it by the event's `detail`, empty meaning every event of that type."""
    type: str
    detail_matches: Tuple["re.Pattern", ...] = ()


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
    #: Threshold alerts for every role's briefing (policy.yaml `threshold_alerts`).
    threshold_alerts: Tuple[ThresholdAlert, ...] = ()
    #: Accepted proposals never carried out that must NOT wake the Overseer
    #: (legacy rulings the executor closes later, design 8.1). Every other
    #: accepted-but-unexecuted proposal wakes it until carried out.
    unexecuted_wake_ignore: Tuple[str, ...] = ()
    #: Per-role lane triggers (policy.yaml `lane_triggers`). Empty: no lane
    #: filtering, every wake reason wakes the roles its table entry names.
    lane_triggers: Dict[str, LaneTriggers] = field(default_factory=dict)

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
        )
    return lanes


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
        alerts.append(ThresholdAlert(
            name=str(entry.get("name") or f"alert-{i}"), tool=str(read["tool"]), args=dict(args),
            field=str(read["field"]), below=below, text=text, per=per,
        ))

    raw_ignore = doc.get("unexecuted_wake_ignore") or []
    if not isinstance(raw_ignore, list) or not all(isinstance(x, str) for x in raw_ignore):
        raise PolicyError(f"{path}: unexecuted_wake_ignore must be a list of proposal ids")

    lane_triggers = _load_lane_triggers(doc.get("lane_triggers"), path)

    return Policy(
        lane_triggers=lane_triggers,
        threshold_alerts=tuple(alerts),
        unexecuted_wake_ignore=tuple(raw_ignore),
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
