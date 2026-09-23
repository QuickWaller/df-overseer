"""Triage: who wakes, if anyone, and at what clock speed.

`docs/AGENT-LOOP.md` §1 step 3 and §4's own triage rules v1: "wake advisors
on a vital crossing a threshold, a stuck job, a prediction falling due or
graded, a migrant or caravan event, or at least every 7 game days; wake the
Overseer only when the queue holds something for it." The Consultant wakes
only on an open ask or fact-check (§4's own roster note), and the ordering
within a cycle is fixed: advisors, then Consultant, then Overseer.

Everything here is pure: given a `Signals` snapshot (already-read Tier 0
data, assembled by `conductor/cycle.py` from the conductor's own MCP calls)
and a `Policy`, `triage()` returns a `TriageResult` with no side effect and
no further DFHack read of its own -- a quiet cycle (a default `Signals()`)
always wakes nobody and costs nothing, matching §1's own words.

**Tripwires are NOT triaged here.** A latched tripwire pauses the fort
directly, inside the game loop (`docs/AGENT-LOOP.md` §3), independent of
this module; `conductor/cycle.py` reads `clock.status`'s own latch and wakes
the Overseer for it directly, never through `triage()`. This module only
covers the ordinary wake-reason table (§2's fallback table plus the
ticks-to-consequence rule), never the tripwire row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from conductor.policy import FULL_SPEED, Policy, clock_for_reason, most_urgent

#: The fixed roster this build knows about (docs/AGENT-LOOP.md §4: "Overseer,
#: Architect, Quartermaster and Consultant").
ADVISORS: Tuple[str, ...] = ("architect", "quartermaster")
CONSULTANT = "consultant"
OVERSEER = "overseer"


@dataclass(frozen=True)
class Wake:
    """One reason this cycle woke someone (or affected the clock without
    waking anyone, e.g. a hostile seen but not yet reachable)."""

    reason: str
    detail: str
    roles: Tuple[str, ...]
    clock: str


@dataclass(frozen=True)
class Signals:
    """Already-read Tier 0 data for one cycle. Every field defaults to
    "nothing to report", so a caller can build a mostly-empty `Signals` for
    a genuinely quiet cycle without enumerating every field. `conductor/
    cycle.py` is what turns raw tool results (vitals.summary, queue.grade,
    each advisor's own diff.since drain, clock.status) into this shape --
    this module never reads a tool itself.
    """

    # docs/AGENT-LOOP.md §2's table: "vital nearing its threshold" -> slowed
    # (or full_speed if not yet close, via the ticks-to-consequence rule).
    # The tripwire itself ("a critical vital") is a separate, non-triaged
    # path -- see this module's own docstring.
    vital_nearing_threshold: bool = False
    vital_ticks_to_consequence: Optional[int] = None

    # From each advisor's own diff.since drain, already classified by
    # conductor/cycle.py's own event-to-reason mapping -- this module never
    # parses a raw DFHack event.
    stuck_job: bool = False
    stuck_job_ticks_to_consequence: Optional[int] = None
    stock_below_target: bool = False
    stock_below_target_ticks_to_consequence: Optional[int] = None
    migrant_wave: bool = False
    caravan_present: bool = False
    season_change: bool = False
    hostile_seen_unreachable: bool = False

    # handoffs/2026-09-23-stalled-order-poller.md: polled from orders.list
    # via conductor/order_watch.py, never from a diff.since event -- there
    # is no announcement to drain for this failure mode (research/2026-09-
    # 23-announcement-severity.md §C). See that module's own docstring for
    # the stalled-vs-blocked distinction and the dedup/renotify rule.
    stalled_order: bool = False
    stalled_order_ids: Tuple[int, ...] = ()
    blocked_order: bool = False
    blocked_order_ids: Tuple[int, ...] = ()

    # handoffs/2026-09-23-attention-tiers-ingame.md item 2 / this stream's
    # item 4: a `slow`-level announcement, drained through diff.since and
    # classified by conductor/cycle.py's `_classify_slow_announcements`.
    # Unlike every other reason above, WHICH role(s) wake is data carried on
    # the event itself (each announcement type's own `wake` list in
    # research/data/2026-09-23-announcement-severity.yaml), not a fixed
    # policy.yaml role list -- see this module's own triage() handling below.
    slow_announcement: bool = False
    slow_announcement_roles: Tuple[str, ...] = ()
    slow_announcement_detail: str = ""

    # This cycle's own queue.grade result.
    prediction_due: bool = False
    prediction_graded: bool = False

    # Routine review: game days since advisors last woke for any reason.
    game_days_since_routine_review: float = 0.0

    # Queue state.
    queue_holds_for_overseer: bool = False
    open_ask_for_consultant: bool = False


@dataclass(frozen=True)
class TriageResult:
    wakes: Tuple[Wake, ...]
    clock: str
    roles_to_wake: Tuple[str, ...]  # ordered: advisors, then consultant, then overseer

    def wake_for(self, role: str) -> Optional[Wake]:
        """The first `Wake` naming `role`, or `None` if this role was not
        woken this cycle -- what `conductor/cycle.py` hands to
        `conductor.briefing.build_briefing`."""
        for wake in self.wakes:
            if role in wake.roles:
                return wake
        return None


#: The subset of docs/AGENT-ARCHITECTURE.md §4's closed wake-event
#: vocabulary this `Signals` shape carries as a plain boolean (no computable
#: ticks-to-consequence). Kept here, as data, rather than as a chain of
#: `if signals.x: ...` per field -- one place wiring a `Signals` field to
#: its `policy.yaml` reason name.
_BOOLEAN_REASONS: Tuple[str, ...] = (
    "migrant_wave", "caravan_present", "season_change", "hostile_seen_unreachable",
)
#: The subset marked `computable: true` in policy.yaml -- each one also
#: carries a `<reason>_ticks_to_consequence` field on `Signals`.
_COMPUTABLE_REASONS: Tuple[str, ...] = (
    "stuck_job", "stock_below_target", "vital_nearing_threshold",
)


def triage(signals: Signals, policy: Policy, *, base_fps: Optional[int] = None) -> TriageResult:
    """`docs/AGENT-LOOP.md` §1 step 3. Never calls a tool; every input is
    already read. `Signals()` at every default (a quiet cycle) always
    returns `TriageResult(wakes=(), clock=FULL_SPEED, roles_to_wake=())` --
    "a quiet cycle wakes nobody and costs nothing."
    """
    wakes: List[Wake] = []

    if signals.prediction_due:
        rp = policy.reason("prediction_due")
        wakes.append(Wake(
            "prediction_due", "a prediction fell due this cycle",
            rp.wakes, clock_for_reason("prediction_due", policy),
        ))
    if signals.prediction_graded:
        rp = policy.reason("prediction_graded")
        wakes.append(Wake(
            "prediction_graded", "a prediction was graded this cycle",
            rp.wakes, clock_for_reason("prediction_graded", policy),
        ))

    for reason in _BOOLEAN_REASONS:
        if getattr(signals, reason):
            rp = policy.reason(reason)
            wakes.append(Wake(
                reason, reason.replace("_", " "),
                rp.wakes, clock_for_reason(reason, policy),
            ))

    for reason in _COMPUTABLE_REASONS:
        if getattr(signals, reason):
            ticks = getattr(signals, f"{reason}_ticks_to_consequence", None)
            rp = policy.reason(reason)
            clock = clock_for_reason(reason, policy, ticks_to_consequence=ticks, base_fps=base_fps)
            detail = reason.replace("_", " ")
            if ticks is not None:
                detail += f" ({ticks} ticks to consequence)"
            wakes.append(Wake(reason, detail, rp.wakes, clock))

    if signals.game_days_since_routine_review >= policy.routine_review_interval_game_days:
        rp = policy.reason("routine_review")
        wakes.append(Wake(
            "routine_review",
            f"{signals.game_days_since_routine_review:.1f} game days since the last "
            f"routine review (interval {policy.routine_review_interval_game_days})",
            rp.wakes, clock_for_reason("routine_review", policy),
        ))

    # handoffs/2026-09-23-stalled-order-poller.md item 1. Dedicated blocks
    # (not the generic _BOOLEAN_REASONS loop above) because the detail
    # string names the actual order ids, the same way routine_review's own
    # detail names the actual figure rather than a bare reason name.
    if signals.stalled_order:
        rp = policy.reason("stalled_order")
        ids = ", ".join(str(i) for i in signals.stalled_order_ids)
        wakes.append(Wake(
            "stalled_order",
            f"order(s) {ids} validated but not dispatched for at least the stall threshold",
            rp.wakes, clock_for_reason("stalled_order", policy),
        ))
    if signals.blocked_order:
        rp = policy.reason("blocked_order")
        ids = ", ".join(str(i) for i in signals.blocked_order_ids)
        wakes.append(Wake(
            "blocked_order",
            f"order(s) {ids} could not be validated by the Manager",
            rp.wakes, clock_for_reason("blocked_order", policy),
        ))

    # handoffs/2026-09-23-attention-tiers-ingame.md item 2 / this stream's
    # item 4. Roles come from the event data (signals.slow_announcement_roles,
    # already ordered/deduped by conductor/cycle.py), not from
    # policy.reason("slow_announcement").wakes -- that entry's own `wakes`
    # field is deliberately unused for role selection, see policy.yaml.
    if signals.slow_announcement:
        wakes.append(Wake(
            "slow_announcement",
            signals.slow_announcement_detail or "a slow-tier announcement fired",
            signals.slow_announcement_roles, clock_for_reason("slow_announcement", policy),
        ))

    # docs/AGENT-LOOP.md §4: "wake the Overseer only when the queue holds
    # something for it." Not part of the wake_reasons table (there is no
    # ticks-to-consequence or fallback clock question here -- ruling always
    # runs at full speed unless something else in this same cycle already
    # slowed or paused it), so this reason is constructed directly rather
    # than looked up via policy.reason().
    if signals.queue_holds_for_overseer:
        wakes.append(Wake(
            "queue_pending", "the queue holds something for the Overseer",
            (OVERSEER,), FULL_SPEED,
        ))

    # §4's roster note: the Consultant wakes only on an open ask or
    # fact-check. Same reasoning as queue_pending above.
    if signals.open_ask_for_consultant:
        wakes.append(Wake(
            "open_ask", "an ask or fact-check is open for the Consultant",
            (CONSULTANT,), FULL_SPEED,
        ))

    clock = most_urgent(w.clock for w in wakes)

    roles_to_wake: List[str] = []
    for wake in wakes:
        for role in wake.roles:
            if role and role not in roles_to_wake:
                roles_to_wake.append(role)
    ordered = tuple(r for r in (*ADVISORS, CONSULTANT, OVERSEER) if r in roles_to_wake)

    return TriageResult(wakes=tuple(wakes), clock=clock, roles_to_wake=ordered)
