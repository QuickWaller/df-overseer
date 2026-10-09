"""The cycle: `docs/AGENT-LOOP.md` §1, tying together `conductor/policy.py`,
`conductor/triage.py`, `conductor/briefing.py`, `conductor/cursors.py`,
`conductor/archive.py`, `conductor/runner.py` and `conductor/mcp_client.py`
into the one sequence -- read, grade, triage, advise, decide-and-act, save.

Everything the cycle touches is injected (`CycleDeps`): the conductor's own
`ToolCaller`, a `RoleRunner`, the loaded `Policy`, a `CursorStore`, a
`CycleArchive`, each role's charter text and model id. `run_cycle` never
constructs a real MCP connection or launches a real container itself --
`conductor/service.py` is what wires the real `StreamableHTTPMCPClient`/
`DockerOpenClawRunner` in for the deploy; every test here drives the exact
same code path with `FakeToolCaller`/`FakeRoleRunner` instead.

## Two known, load-bearing gaps found while building the conductor service
## stream -- both fixed by `handoffs/2026-09-22-loop-conductor-fixes.md`

1. **FIXED.** `queue.pending`'s role branch used to be keyed to the
   CALLER's own authenticated identity, not an argument
   (`dfmcp/queue_tools.py`'s `_pending`). The conductor calls dfmcp as
   `conductor`, never `consultant`, so it could only ever see
   `pending_proposals()` -- there was no way, from the conductor's own
   token, to ask "is there an open ask for the Consultant?" This module now
   calls the new, conductor-only, role-independent `queue.overview` native
   tool instead (`dfmcp/queue_tools.py`'s `_overview`), which always
   returns both `pending_proposals()` and `open_asks()` in one read. See
   `_queue_summary_for` below for how each role's own briefing still gets
   only the half of that read it cares about.
2. **Still open, on purpose, after checking.** `handoffs/2026-09-22-loop-
   conductor-fixes.md` item 4 asked to grant `threat.scan`
   (`scripts/dfhack/df-overseer-threat.lua`'s `scan [RADIUS_TILES]`) if its
   cost is bounded. Read from source: it is bounded (one pass over
   `world.units.active`, `MAX_RADIUS`/`MAX_RESULTS` capped) -- but granting
   it would not actually fix `hostile_seen_unreachable`, because that tool
   answers a different question than this signal needs. `find_threats`'s
   own admission rule is `shares_walkable_group OR near_a_landmark` --
   **reachability**, by design (its header: "reachability gets both right");
   it structurally cannot return a hostile that is seen but NOT yet
   reachable, which is exactly this signal's own definition
   (`docs/AGENT-LOOP.md` §1/§3: "hostile seen but not yet able to reach the
   fort" -> slowed, vs. "a hostile that can reach the fort" -> the in-game
   tripwire, which already runs this same `find_threats` reachability check
   itself, server-side, for `hostile_reachable`). Anything `threat.scan`
   returns to the conductor would duplicate the tripwire's own reachable
   case, not cover the unreachable one. The real fix needs the still-owed
   announcement-class tripwire/event (`docs/AGENT-LOOP.md` §3: "the
   announcement tripwire... is still owed") feeding a genuine sighting event
   into `diff.since`, not a new grant of this tool. `hostile_seen_unreachable`
   stayed `False` always, a documented gap; the stub (signal, policy entry) was
   deleted in handoffs/2026-10-07-wake-cleanup.md and returns with a real source.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from conductor.archive import CycleArchive
from conductor.briefing import paused_line, build_briefing, build_ruling_briefing, evaluate_threshold_alerts, routing_from_state
from conductor import lanes
from conductor.cursors import CursorStore
from conductor.backoff import RetryClock
from conductor.game_tick import GameTickError, game_tick_from_overview
from conductor.execute import ExecuteStore, ExecuteReport, run_execute, skipped_report
from conductor.hold import HoldState, HoldStore, hold_path_for
from conductor.mcp_client import MCPToolError, ToolCaller, tool_name
from conductor.job_watch import JobWatchResult, JobWatchStore, evaluate_jobs, jobs_from_result
from conductor.ore_watch import POLL_TOOL as ORE_POLL_TOOL, OreRead, ore_read_from_sites
from conductor import noble_room_watch
from conductor import automine as automine_mod
from conductor.unsupplied_watch import POLL_TOOL as UNSUPPLIED_POLL_TOOL, UnsuppliedRead, unsupplied_read
from conductor.order_watch import OrderWatchResult, evaluate_orders
from conductor.pause_watch import (
    OWNED_ESCALATION, UNEXPLAINED_PAUSE, PauseWatchStore, PausePolicy, Verdict, WatchOutcome,
    _alert as _pause_alert,
    finish_after_overseer, load_pause_policy, read_verdict_after, read_verdict_baseline, run_pause_watch,
)
from conductor.policy import FULL_SPEED, PAUSED, Policy
from conductor.plan_watch import (
    STATUS_TOOL as PLAN_STATUS_TOOL, PlanWatchResult, PlanWatchState, PlanWatchStore, SeasonEdge,
    advance_season, evaluate as evaluate_plan, last_refusal,
)
from conductor.utilisation import UNIT_STATUS_TOOL, UtilisationStore, sample as utilisation_sample
from conductor.runner import RoleRunner, RunResult
from conductor.triage import ADVISORS, CONSULTANT, OVERSEER, PLANNER, PROPOSERS, LaneWake, Signals, Wake, triage
from conductor.tripwire import (
    TripwireStateError, TripwireStore, note_latch, owners_for, repeat_count,
)

LOG = logging.getLogger("conductor.cycle")

#: The roles this cycle ever drains a diff for and may wake, in the fixed
#: order docs/AGENT-LOOP.md §4 names: "advisors, then Consultant, then
#: Overseer." Tuple, not a set, so it also fixes drain/launch order.
ALL_ROLES = (*ADVISORS, CONSULTANT, OVERSEER)
#: Roles that may run together when `parallel.proposers` is on: every proposer
#: but the Planner (which runs first, alone), plus the Consultant. Never the
#: Overseer: there is exactly one judge and it runs after them.
CONCURRENT_ROLES = (*ADVISORS, CONSULTANT)

#: docs/AGENT-ARCHITECTURE.md §4's own closed wake-event vocabulary, scoped
#: to the subset conductor/triage.py's Signals carries as a plain boolean.
#: Maps a drained diff.since event's own "type" field to the Signals field
#: it sets. **Unverified against a real diff.since payload** (no VM this
#: stream) -- the exact key a drained event carries its classification
#: under was not independently re-derived here; flagged in this stream's
#: report as needing a live check before this mapping is trusted.
#:
#: Empty since handoffs/2026-10-07-wake-cleanup.md: `migrant_wave`,
#: `caravan_arrived`, `season_change` and `stock_below_threshold` were never
#: emitted by any DFHack script (research/2026-10-07-wake-audit.md rows 19, 23
#: to 25), so their entries and signals were deleted. `season_change` is now
#: computed from the game tick (conductor/plan_watch.py), not drained. A real
#: emitter would add its entry here again.
EVENT_TYPE_TO_SIGNAL: Dict[str, str] = {}

#: handoffs/2026-09-23-attention-tiers-ingame.md item 2 / this stream's item
#: 4. The event `type` this stream ASSUMES the sibling in-game stream's
#: still-owed fifth tripwire (the 23 `slow`-level announcement ids,
#: research/2026-09-23-announcement-severity.md) will drain through
#: diff.since as, once it lands: `{"type": "announcement_slow",
#: "announcement_type": <df.announcement_type name>, "tick": <int>,
#: "wake": [<role>, ...], "detail": <one-clause gloss>}` -- `wake` copied
#: from the severity YAML's own per-type `wake` field (may be empty; that
#: type still slows the clock, wakes nobody, same shape as
#: hostile_seen_unreachable). **Not verified against a real payload from
#: that stream** -- recorded as an assumed interface in this stream's own
#: Result section, to be confirmed or corrected once that stream's build
#: lands, the same "unverified, flagged plainly" discipline
#: EVENT_TYPE_TO_SIGNAL above already uses for diff.since's general shape.
SLOW_ANNOUNCEMENT_EVENT_TYPE = "announcement_slow"

#: vitals.summary's own status categories that count as "nearing" rather
#: than "fine" -- the critical end of each scale is what the in-game
#: tripwire pauses for (docs/AGENT-LOOP.md §3), so only the WARNING end
#: belongs to this ordinary (non-paused) wake reason.
_NEARING_STATUSES = ("hungry", "thirsty")

#: An empty sub-summary, used whenever queue.overview's own result is
#: missing a key it should always carry (defensive, not expected live).
_EMPTY_QUEUE_SUB_SUMMARY: Dict[str, Any] = {"count": 0}



async def _carry_out_wake_ids(
    call: Callable, unexecuted_ids: Sequence[Any], hold: HoldState, cycle_index: int,
) -> List[str]:
    """The unexecuted wake (docs/CONDUCTOR-EXECUTION.md 3, P3-B1, P3-L1).

    `queue.grade` already lists only accepted work the executor does not own:
    the store excludes routed types, follow-up and closed rulings and keys on
    the step's `proposal_id`. This adds the two conductor-side rules:

    - under an operator hold nothing is carried out and nothing wakes, so a
      held fort is not nagged about work that cannot run;
    - until deploy 2a has set the legacy cutover (`conductor.cutover legacy
      --apply`), every unexecuted ruling is pre-cutover work that 2a will
      close, so none wakes (this replaces the old `unexecuted_wake_ignore`
      stopgap). An unreadable cutover reads as not set: a missed wake is
      recovered next cycle, a wrong one sends the Overseer after dead work.
    """
    ids = [i for i in unexecuted_ids if isinstance(i, str)]
    if not ids:
        return []
    if hold.held:
        LOG.info("cycle %s: %d unexecuted ruling(s) not woken for: operator hold", cycle_index, len(ids))
        return []
    try:
        state = await call("queue.cutover", {"group": "legacy", "apply": False})
    except MCPToolError as exc:
        LOG.warning("cycle %s: legacy cutover unreadable (%s); no unexecuted wake", cycle_index, exc)
        return []
    if not isinstance(state, Mapping) or state.get("cutover_set") is None:
        LOG.info(
            "cycle %s: legacy cutover not applied; %d unexecuted ruling(s) are pre-cutover, no wake",
            cycle_index, len(ids),
        )
        return []
    return ids



async def _read_routing(call: Callable, cycle_index: int) -> Optional[Mapping[str, Any]]:
    """The routed, unrouted and frozen proposal types, from `queue.execution_state`'s
    `routing` block. `None` (not reported, or the read failed) means every
    briefing is exactly what it was before routing existed."""
    try:
        return routing_from_state(await call("queue.execution_state", {}))
    except Exception as exc:  # noqa: BLE001 -- total: a briefing never depends on this read
        LOG.warning("cycle %s: routing read failed (%s); briefings carry no routing lines", cycle_index, exc)
        return None


def _automine_store(deps: "CycleDeps") -> automine_mod.AutomineStore:
    return automine_mod.AutomineStore(deps.cursor_store.path.with_name("automine_state.json"))


async def _automine_phase(
    deps: "CycleDeps", call: Callable, *, cycle_index: int, hold: HoldState, escalated: bool,
) -> automine_mod.AutomineReport:
    """The automine pass (conductor/automine.py). Skipped under ANY operator hold
    (unlike the execute phase, `--allow-execution` does not allow it), after an
    escalation, and when policy turns it off. Total."""
    pol = deps.policy.automine
    try:
        report = await automine_mod.run_automine(
            call, enabled=pol.enabled, held=hold.held, escalated=escalated,
            store=_automine_store(deps), max_per_call=pol.max_per_call,
        )
    except Exception:  # noqa: BLE001
        LOG.exception("cycle %s: the automine phase failed", cycle_index)
        return automine_mod.AutomineReport(skipped="the automine phase raised")
    if report.ran:
        LOG.info("cycle %s: automine: %d designated, %d in a reservation, %d cavern breach(es)",
                 cycle_index, report.designated, report.in_reservation, report.cavern_breaches)
    elif report.skipped and report.skipped != "disabled in policy":
        LOG.info("cycle %s: automine skipped: %s", cycle_index, report.skipped)
    return report


def _execute_store(deps: "CycleDeps") -> ExecuteStore:
    return ExecuteStore(deps.cursor_store.path.with_name("execute_state.json"))


async def _execute_phase(
    deps: "CycleDeps", call: Callable, *, cycle_index: int, game_tick: Optional[int], hold: HoldState,
    escalated: bool, ore_read: Optional[OreRead], lane_state: "lanes.LaneState",
    clock_changes: List[Dict[str, Any]], latched: bool,
) -> ExecuteReport:
    """The execute phase's gate and plumbing (conductor/execute.py has the
    work). Skipped, with the reason recorded, for an escalation this cycle or
    an operator hold that does not allow execution; never run for a
    watchdog-owned pause or a latched tripwire in the ordinary path, since
    those cycles return before reaching here (a latch runs it through
    `_tripwire_cycle` with `latched=True`, high urgency only). Total: a fault
    here is logged and never stops the cycle, and the phase never touches the
    clock, so it can never resume the fort."""
    if escalated:
        return skipped_report("an escalation this cycle")
    if hold.held and not hold.allow_execution:
        LOG.info("cycle %s: execute phase skipped: operator hold without --allow-execution", cycle_index)
        return skipped_report("operator hold")
    store = _execute_store(deps)
    try:
        state = store.load()
    except Exception:  # noqa: BLE001 -- a corrupt state would resend every wake: skip, say so
        LOG.exception("cycle %s: execute state unreadable; the execute phase is skipped", cycle_index)
        return skipped_report("execute state unreadable")

    async def quicksave() -> None:
        await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)

    fallback = tuple(r for r, lane in deps.policy.lane_triggers.items() if lane.execution)
    try:
        report = await run_execute(
            deps.tool_caller.call_tool, deps.policy.execution, state, game_tick=game_tick, ore_read=ore_read,
            quicksave=quicksave, fallback_roles=fallback, latched=latched,
        )
    except Exception:  # noqa: BLE001
        LOG.exception("cycle %s: the execute phase failed", cycle_index)
        return skipped_report("the execute phase raised")
    if not report.ran:
        LOG.warning("cycle %s: execute phase did not run: %s", cycle_index, report.skipped)
        return report
    try:
        store.save(state)
    except Exception:  # noqa: BLE001
        LOG.exception("cycle %s: could not save the execute state", cycle_index)
    if report.wakes and deps.policy.lane_triggers:
        for w in report.wakes:
            lanes.add_pending(lane_state, w.role, w.key, w.text)
        try:
            _lane_store(deps).save(lane_state)
        except Exception:  # noqa: BLE001
            LOG.exception("cycle %s: could not save lane state after the execute phase", cycle_index)
    for action in report.actions:
        LOG.info("cycle %s: execute: %s", cycle_index, action)
    for err in report.errors:
        LOG.warning("cycle %s: execute error: %s", cycle_index, err)
    return report


def _queue_summary_for(role: str, queue_state: Mapping[str, Any]) -> Mapping[str, Any]:
    """`queue.overview`'s own result carries BOTH halves of the queue
    (`proposals`, `asks`) in one read (fix 1, this module's own docstring
    above). A role's own briefing should still only see the half that is
    actually "pending for it": the Consultant never proposes, so what is
    pending for it is open asks, exactly the distinction `dfmcp/
    queue_tools.py`'s old per-caller-role `queue.pending` branch used to
    draw at the SERVER -- now drawn here instead, once, from one
    role-independent read."""
    asks = queue_state.get("asks") or _EMPTY_QUEUE_SUB_SUMMARY
    if role == CONSULTANT or role in (asks.get("to") or {}):
        # Asks addressed to this role only; a summary with no `to` map is the
        # pre-addressing shape, where every ask is the Consultant's.
        to = asks.get("to")
        if to is None:
            return asks if role == CONSULTANT else _EMPTY_QUEUE_SUB_SUMMARY
        ids = list(to.get(role) or ())
        return {"count": len(ids), "ask_ids": ids}
    return queue_state.get("proposals") or _EMPTY_QUEUE_SUB_SUMMARY


def _miss_proposers(policy: Any, grade_result: Mapping[str, Any], cycle_index: int) -> Tuple[str, ...]:
    """Who a missed prediction wakes: its proposer only
    (handoffs/2026-10-07-wake-cleanup.md item 6; research/2026-10-07-wake-audit.md
    row 21, where the other advisor ran for nothing). `queue.grade`'s graded
    rows carry `proposer`. A row without one (an older server) falls back to the
    reason's own `wakes` list, so a rollout order cannot silence a miss. A
    proposer this build does not run (the Planner while it is off, an unknown
    role) is logged and wakes nobody, never someone else in its place."""
    misses = [
        g for g in (grade_result.get("graded") or ())
        if isinstance(g, Mapping) and g.get("status") == "graded_false"
    ]
    if not misses:
        return ()
    if any("proposer" not in g for g in misses):
        return tuple(policy.reason("prediction_graded").wakes)
    runnable = {*ADVISORS, *((PLANNER,) if policy.plan.enabled else ())}
    roles: List[str] = []
    for g in misses:
        who = g.get("proposer")
        if who in runnable:
            if who not in roles:
                roles.append(who)
        else:
            LOG.info("cycle %s: a prediction missed whose proposer %r this build does not run; no wake", cycle_index, who)
    return tuple(roles)


def _open_ask_addressees(queue_state: Mapping[str, Any]) -> Tuple[str, ...]:
    """Roles with an open ask addressed to them, from `queue.overview`'s
    `asks.to` map. A summary without the map is the pre-addressing shape:
    any open ask is the Consultant's."""
    asks = queue_state.get("asks") or {}
    to = asks.get("to")
    if to is None:
        return (CONSULTANT,) if asks.get("count", 0) else ()
    return tuple(role for role, ids in to.items() if ids)


def _runnable_ask_addressees(queue_state: Mapping[str, Any], cycle_index: int) -> Tuple[str, ...]:
    """Open-ask addressees other than the Consultant that the conductor can
    actually run. An ask addressed to a role it has no runner for (a role added
    to the roster before the conductor learns to run it) wakes nobody and is
    logged, never a crash or a blind wake."""
    out = []
    for role in _open_ask_addressees(queue_state):
        if role == CONSULTANT:
            continue
        if role in ALL_ROLES and role != OVERSEER:
            out.append(role)
        else:
            LOG.warning("cycle %s: an ask is open for %r, which the conductor does not run", cycle_index, role)
    return tuple(out)


async def _call_write(
    call: Callable, tool_id: str, arguments: Mapping[str, Any], *,
    clock_changes: List[Dict[str, Any]], cycle_index: int,
) -> Dict[str, Any]:
    """A `clock.*`/`fort.quicksave` write call. Fix 2, this module's own
    docstring update below: `dfmcp/server.py`'s own refusal shape for this
    tool family (`{"ok": false, "error": ..., ...}`) now correctly surfaces
    as an MCP `isError`, which the real `StreamableHTTPMCPClient` turns into
    a raised `MCPToolError` -- so a refusal no longer silently comes back as
    an ordinary-looking dict a careless caller could ignore. This wrapper is
    what keeps every caller below simple and uniform: it always returns a
    dict with `"ok"` set (synthesising `{"ok": False, "error": <text>}` from
    a caught `MCPToolError`, matching the SAME shape the tool used to return
    directly before the fix, so a downstream `.get("ok", False)` check still
    means exactly what it always meant), always logs a refusal once at
    ERROR (tool id and reason -- previously only `clock.resume` did this,
    inconsistently; every write in this family gets the same treatment
    now), and always records the attempt in `clock_changes`, refused or not,
    so a cycle's own archived record of what it tried never silently drops
    a call just because it failed.
    """
    try:
        result = await call(tool_id, arguments)
    except MCPToolError as exc:
        LOG.error("cycle %s: %s refused: %s", cycle_index, tool_id, exc)
        result = {"ok": False, "error": str(exc)}
    clock_changes.append({"tool": tool_id, "args": dict(arguments), "result": result})
    return result


class CycleError(Exception):
    """A cycle could not complete a required read (DFHack/dfmcp
    unreachable). Never raised for a role run's own failure -- that is a
    `RunResult` with `ok=False`, handled inline, not an exception."""


@dataclass
class CycleDeps:
    """Everything one cycle needs, injected -- never constructed inside
    `run_cycle` itself, so a test supplies fakes for every side effect."""

    tool_caller: ToolCaller
    role_runner: RoleRunner
    policy: Policy
    cursor_store: CursorStore
    archive: CycleArchive
    charters: Mapping[str, str]          # role -> charter markdown (agents/<role>/role.md)
    models: Mapping[str, str]            # role -> model id
    role_timeout_seconds: float = 600.0
    dry_run: bool = False
    clock: Callable[[], float] = time.monotonic
    #: The pause watchdog (conductor/pause_watch.py). All optional: unset, the
    #: policy is the committed conductor/pause_policy.yaml and the state file
    #: sits beside the cursor store. `wall_clock` is real time (the state
    #: outlives a process, so a monotonic clock will not do); `pause_sleep`
    #: is the wait between a resume and its tick check.
    pause_policy: Optional[PausePolicy] = None
    pause_store: Optional[PauseWatchStore] = None
    #: The operator hold (conductor/hold.py, handoffs/2026-10-05-operator-hold.md),
    #: `hold.json` beside the cursor store unless set. Read-only here: only the
    #: operator's CLI writes it.
    hold_store: Optional[HoldStore] = None
    wall_clock: Callable[[], float] = time.time
    pause_sleep: Callable[[float], Any] = asyncio.sleep


@dataclass
class CycleResult:
    cycle_index: int
    game_tick: Optional[int]
    game_tick_error: Optional[str]
    signals: Signals
    clock_level: str
    roles_woken: tuple
    clock_changes: List[Dict[str, Any]]
    role_runs: List[RunResult]
    tripwire: Optional[dict]
    escalated: bool
    unexecuted: List[dict]
    archived_path: Optional[Any]
    dry_run: bool
    plan: Optional[Dict[str, Any]] = None  # dry-run only: what WOULD have happened
    #: The pause watchdog's pass this cycle (verdict, reason, actions, alerts),
    #: None when it did not run. handoffs/2026-10-05-pause-safety.md.
    pause_watch: Optional[Dict[str, Any]] = None
    #: The operator hold in force this cycle (`HoldState.as_dict()`), None when
    #: there is none. Carried to the status block and the cycle log line.
    hold: Optional[Dict[str, Any]] = None
    #: The execute phase's report (`conductor.execute.ExecuteReport.as_dict()`),
    #: None when it did not run or was not attempted (dry run).
    execute: Optional[Dict[str, Any]] = None
    #: The automine pass (`conductor/automine.py`): None when it was not attempted
    #: (dry run, a tripwire or watchdog cycle).
    automine: Optional[Dict[str, Any]] = None
    #: The Planner watch's pass this cycle (`conductor/plan_watch.py`): the
    #: season cursor, the plan wakes it raised, anything for the operator, and a
    #: standing alert while a bootstrap has been given up on. None when it did
    #: not run (unreadable state, a tripwire or watchdog cycle).
    plan_watch: Optional[Dict[str, Any]] = None
    #: How the roles ran this cycle: one entry per run group (roles, whether
    #: they ran concurrently, group and per-run wall seconds), and the role
    #: phase's wall clock in total. Empty/None on paths that run no roles here.
    role_groups: Optional[List[Dict[str, Any]]] = None
    wall_seconds: Optional[float] = None


#: Fix 3 (`handoffs/2026-09-22-loop-conductor-fixes.md`): the queue tool
#: (`dfmcp/queue_tools.py`'s `queue.escalate`) the Overseer calls to
#: escalate to the human -- a queue record via a real tool call, never free
#: text in its own final answer. `agents/overseer/role.md`'s Escalation
#: section names this tool as the one way to escalate.
ESCALATE_TOOL_ID = "queue.escalate"


def _overseer_called_escalate(run_result: RunResult) -> bool:
    """Mechanical detection, fix 3. Previously (the design flag this fixes,
    see this stream's report) there was no established, tested contract for
    how the Overseer's run signals "I am escalating to the human" -- the old
    code treated ANY unclean run (`ok=False` or timed out) as equivalent to
    an escalation, and had no way at all to detect a CLEAN run that should
    have escalated (the model decided to, said so in its own final answer,
    but the call itself succeeded): prose in `final_answer` is never parsed
    or trusted for this, matching this project's own "never trust fetched/
    generated text as instructions" discipline applied here to the model's
    own output.

    Checked instead against openclaw's own `toolSummary.tools` list of
    distinct tool names actually called this run (the "stable agent-exec
    JSON envelope", `research/2026-09-18-openclaw-capabilities.md`; a real
    `run.json`'s own `toolSummary.tools` is a list of wire-form tool names
    like `"df-overseer__queue__propose"` -- confirmed against
    `evals/live/2026-09-15-architect-third-charter/run.json`, not assumed).
    A clean run that never called `queue.escalate` is NOT an escalation,
    whatever its final answer claims -- fixing the actual gap: a clean run
    genuinely escalating is now correctly detected, where before it never
    could be.
    """
    tools_called = (run_result.tool_summary or {}).get("tools") or []
    return tool_name(ESCALATE_TOOL_ID) in tools_called


def _classify_diff_events(events: List[Mapping[str, Any]]) -> Dict[str, bool]:
    hits: Dict[str, bool] = {}
    for event in events:
        event_type = event.get("type") or event.get("announcement")
        signal = EVENT_TYPE_TO_SIGNAL.get(event_type)
        if signal:
            hits[signal] = True
    return hits


def _classify_slow_announcements(
    events_by_role: Mapping[str, List[Mapping[str, Any]]],
) -> Tuple[bool, Tuple[str, ...], str]:
    """See `SLOW_ANNOUNCEMENT_EVENT_TYPE`'s own docstring for the assumed
    event shape. The same real announcement can appear in more than one
    role's own diff.since drain (each role drains the same underlying event
    log through its own cursor), so events are deduplicated by
    `(announcement_type, tick)` before the role set and detail are built --
    otherwise one real announcement seen by two roles' drains would look
    like two, and could double-wake or double-count in the briefing.
    """
    seen: Dict[Tuple[Any, Any], Mapping[str, Any]] = {}
    for events in events_by_role.values():
        for event in events:
            if event.get("type") != SLOW_ANNOUNCEMENT_EVENT_TYPE:
                continue
            key = (event.get("announcement_type"), event.get("tick"))
            seen[key] = event

    if not seen:
        return False, (), ""

    roles: List[str] = []
    for event in seen.values():
        for role in event.get("wake") or ():
            if role not in roles:
                roles.append(role)
    ordered_roles = tuple(r for r in (*ADVISORS, CONSULTANT, OVERSEER) if r in roles)

    latest = max(seen.values(), key=lambda e: e.get("tick") or 0)
    detail = (
        f"{len(seen)} slow-tier announcement(s), most recent "
        f"{latest.get('announcement_type')} at tick {latest.get('tick')}"
    )
    if latest.get("detail"):
        detail += f": {latest['detail']}"
    return True, ordered_roles, detail


def _vital_nearing(vitals: Mapping[str, Any]) -> bool:
    return (
        vitals.get("worst_hunger_status") in _NEARING_STATUSES
        or vitals.get("worst_thirst_status") in _NEARING_STATUSES
    )


async def _drain_all_cursors(
    call: Callable, cursor_store: CursorStore, *, dry_run: bool,
) -> Tuple[Dict[str, List[dict]], Dict[str, int]]:
    """One `diff.since` call per role in `ALL_ROLES`, each against that
    role's own persisted cursor (`docs/AGENT-ARCHITECTURE.md` §4: "each
    role keeps its own cursor"). This function only READS: it returns
    `(events_by_role, new_cursors)` and never moves a cursor. The caller
    commits a role's new cursor (`_commit_cursor`) only once that role has
    actually consumed its events (its run was ok) or was not woken at all;
    a failed run (launch_failed, no_output, timeout) must not silently drop
    the events it never processed. A dry run never commits, so a following
    real cycle sees the same events a dry run already showed."""
    events_by_role: Dict[str, List[dict]] = {}
    new_cursors: Dict[str, int] = {}
    for role in ALL_ROLES:
        cursor = cursor_store.get(role)
        drained = await call("diff.since", {"cursor": cursor})
        events_by_role[role] = list(drained.get("events") or [])
        new_cursor = drained.get("cursor")
        if new_cursor is not None:
            new_cursors[role] = int(new_cursor)
    return events_by_role, new_cursors


#: handoffs/2026-10-05-conductor-report.md: the conductor-only MCP tool that
#: carries each run's wake reason (at launch) and summary (at the end) to the
#: host the stream publisher runs on.
REPORT_TOOL_ID = "conductor.report"


async def _report(call: Callable, arguments: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """One `conductor.report` call. NEVER raises: a report is observability,
    and a failure (the tool not deployed yet, the server unreachable, a
    refusal) is one warning line, never a failed cycle or a lost run."""
    try:
        result = await call(REPORT_TOOL_ID, dict(arguments))
        return result if isinstance(result, dict) else None
    except Exception as exc:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.warning("%s (%s) failed, the run goes on: %s", REPORT_TOOL_ID, arguments.get("phase"), exc)
        return None


async def _run_role(
    deps: "CycleDeps", call: Callable, role: str, prompt: str, *, wake: Any, cycle_index: int,
    wake_reasons: Any = None,
) -> RunResult:
    """`deps.role_runner.run`, bracketed by two `conductor.report` calls (start,
    end). The wake reason and its detail go out at launch; the outcome, cost,
    duration and final answer at the end. When the start call failed, the end
    call carries `role`, `wake_reason` and `cycle` too, so it is self-contained."""
    # Every reason the role was woken for (ordered, deduplicated), the headline
    # reason first; a lone wake (tripwire, pause) is just its own reason.
    reasons = [wake.reason]
    for r in wake_reasons or ():
        if r not in reasons:
            reasons.append(r)
    started = await _report(call, {
        "phase": "start", "role": role, "wake_reason": wake.reason,
        "wake_reasons": reasons, "wake_detail": wake.detail, "cycle": cycle_index,
    })
    run_id = (started or {}).get("run_id")
    run_result = await deps.role_runner.run(
        role, prompt, model=deps.models[role],
        timeout_seconds=_timeout_for(deps, role), charter=deps.charters.get(role),
    )
    end_args: Dict[str, Any] = {
        "phase": "end", "status": run_result.status, "ok": bool(run_result.ok),
        "timed_out": bool(run_result.timed_out),
        "duration_s": float(run_result.wall_clock_seconds or 0.0),
        "cost_usd": run_result.cost_usd, "error": run_result.error,
        "final_answer": run_result.final_answer,
    }
    if run_result.thinking:
        end_args["thinking"] = run_result.thinking
    if run_result.transcript:
        end_args["transcript"] = json.dumps(run_result.transcript, sort_keys=True, separators=(",", ":"))
    if run_id:
        end_args["run_id"] = run_id
    else:
        end_args.update({
            "role": role, "wake_reason": wake.reason, "wake_reasons": reasons,
            "wake_detail": wake.detail, "cycle": cycle_index,
        })
    await _report(call, end_args)
    return run_result


def _retry_tick(deps: "CycleDeps", game_tick: Optional[int], cycle_index: int) -> Optional[int]:
    """The backoff clock for this cycle (`RetryClock`); the real tick when the
    fallback is off or its state cannot be read (never stops a cycle)."""
    pol = deps.policy
    try:
        return RetryClock(
            deps.cursor_store, pol.paused_retry_seconds, pol.paused_retry_ticks, persist=not deps.dry_run,
        ).now(game_tick)
    except Exception:  # noqa: BLE001 -- total
        LOG.exception("cycle %s: the retry clock failed; using the real tick", cycle_index)
        return game_tick


def _timeout_for(deps: "CycleDeps", role: str) -> float:
    """Per-role cap from `policy.yaml` (`role_timeout_seconds`) if set, else the
    service-wide cap."""
    return deps.policy.role_timeout_seconds.get(role, deps.role_timeout_seconds)


def _commit_cursor(deps: "CycleDeps", new_cursors: Mapping[str, int], role: str) -> None:
    if not deps.dry_run and role in new_cursors:
        deps.cursor_store.set(role, new_cursors[role])


def _game_tick(overview: Mapping[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """`conductor/game_tick.py`'s own parser, vendored specifically so this
    module never imports `dfqueue` (see that module's own docstring for why
    -- the previous version of this function imported
    `dfqueue.grade.game_tick_from_overview` inside a bare
    `except Exception: return None`, which is how `game_tick` came to be
    permanently `null` in production: `dfqueue` is not shipped alongside
    `conductor/`, so that import failed every single cycle, silently, since
    the service was first deployed. Confirmed live on VM 106 2026-09-23,
    `handoffs/2026-09-23-conductor-game-tick.md`.

    Still non-fatal -- a cycle that cannot parse the tick still runs, it
    just cannot evaluate either time-based wake reason this cycle (see this
    module's own `run_cycle` and `_game_days_since`, and
    `conductor/order_watch.py`'s own `game_tick=None` handling) -- but no
    longer silent: returns `(None, <reason>)` instead of a bare `None`, and
    `run_cycle` logs the reason at ERROR and threads it into both the
    archived record and `status.json` (`conductor/status.py`) every single
    cycle it recurs, not just once. See this stream's own Result section for
    why a parse failure is reported loudly rather than escalated/paused
    outright."""
    try:
        return game_tick_from_overview(overview), None
    except GameTickError as exc:
        return None, str(exc)


def _hold_store(deps: "CycleDeps") -> HoldStore:
    return deps.hold_store or HoldStore(hold_path_for(deps.cursor_store.path))


async def run_cycle(cycle_index: int, deps: CycleDeps) -> CycleResult:
    """One cycle, under whatever operator hold stands (conductor/hold.py). The
    hold is read once, up front, by a total reader: a corrupt file reads as
    held. It is carried on the result (and the dry-run plan) so every consumer
    can show it. The hold never adds an action; it only removes resume paths."""
    hold: HoldState = _hold_store(deps).read(deps.wall_clock())
    if hold.held:
        LOG.info("cycle %s: HELD by operator (%s); the conductor will not resume the fort", cycle_index, hold.reason)
    result = await _run_cycle(cycle_index, deps, hold)
    result.hold = hold.as_dict()
    if isinstance(result.plan, dict):
        result.plan["hold"] = result.hold
    return result


async def _run_cycle(cycle_index: int, deps: CycleDeps, hold: HoldState) -> CycleResult:
    """`docs/AGENT-LOOP.md` §1, one full cycle. `deps.dry_run`: every read
    below still happens (so the plan reflects real state), but no clock
    change, no quicksave, no grading write, and no role is actually
    launched -- see the `dry_run` branches inline and this module's own
    "Dry-run mode" section in the class docstring above.
    """
    call = deps.tool_caller.call_tool
    clock_changes: List[Dict[str, Any]] = []
    role_runs: List[RunResult] = []

    # ---- 1. READ (Tier 0) --------------------------------------------------
    try:
        vitals = await call("vitals.summary", {})
        clock_status = await call("clock.status", {})
        overview = await call("overview.get", {})
        queue_state = await call("queue.overview", {})  # see module docstring, gap 1 (fixed)
        orders_state = await call("orders.list", {})  # handoffs/2026-09-23-stalled-order-poller.md
        events_by_role, new_cursors = await _drain_all_cursors(call, deps.cursor_store, dry_run=deps.dry_run)
    except MCPToolError as exc:
        raise CycleError(f"cycle {cycle_index}: could not complete this cycle's read: {exc}") from exc

    game_tick, game_tick_error = _game_tick(overview)
    if game_tick_error is not None:
        LOG.error(
            "cycle %s: could not parse the game tick from overview.get: %s -- "
            "both time-based wake reasons (routine review, the stalled-order "
            "poller) cannot run this cycle",
            cycle_index, game_tick_error,
        )
    # The backoffs' own clock: the real tick plus whatever a paused fort has
    # earned (conductor/backoff.py RetryClock). Backoffs only.
    retry_tick = _retry_tick(deps, game_tick, cycle_index)
    tripwire = clock_status.get("tripwire")
    armed = clock_status.get("armed")

    # Re-assert the frame cap and re-arm the watcher after a game restart
    # (docs/AGENT-LOOP.md §2: "The frame cap does not survive a game
    # process restart"; §3: the conductor re-asserts it). Detected here as
    # "the watcher somehow isn't armed" rather than trying to detect a
    # restart directly -- re-arming an already-armed watcher is itself a
    # safe no-op (clock_arm's own header: "a fresh arm is a clean start"),
    # so this check is correct whether or not a restart actually happened.
    if not deps.dry_run and not armed:
        await _call_write(call, "clock.arm", {}, clock_changes=clock_changes, cycle_index=cycle_index)

    # ---- Tripwire: paused, independent of ordinary triage ------------------
    # Stage T (handoffs/2026-10-06-stage-t-tripwire.md): the cause's owner
    # runs first, the Overseer rules and gives the verdict, and only an
    # explicit `pause.verdict` resume=true resumes the fort.
    if tripwire is not None:
        return await _tripwire_cycle(
            deps, call, cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
            clock_status=clock_status, vitals=vitals, events_by_role=events_by_role,
            queue_state=queue_state, new_cursors=new_cursors, clock_changes=clock_changes,
            tripwire=tripwire, hold=hold,
        )

    # ---- Pause watchdog: a pause the tripwire does not explain --------------
    # handoffs/2026-10-05-pause-safety.md. Runs only here, after the tripwire
    # branch has had its turn, so a latched tripwire is never seen by it as
    # unowned and never resumed by it.
    pause_outcome = await _pause_watch(deps, call, clock_status, cycle_index, hold)
    pause_watch_dict = pause_outcome.as_dict() if pause_outcome is not None else None
    # ORDINARY_HELD: a plain or harmless pause under an operator hold is not
    # the watchdog's to resolve; fall through to the ordinary path with the
    # fort paused (roles wake on their usual signals, the job watch polls).
    if (
        pause_outcome is not None and pause_outcome.verdict not in (Verdict.IDLE, Verdict.ORDINARY_HELD)
        and pause_outcome.still_paused
    ):
        return await _paused_cycle_result(
            deps, call, cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
            clock_status=clock_status, vitals=vitals, events_by_role=events_by_role,
            queue_state=queue_state, new_cursors=new_cursors, clock_changes=clock_changes,
            pause_outcome=pause_outcome, hold=hold,
        )

    # ---- 2. GRADE -----------------------------------------------------------
    prediction_graded = False
    prediction_misses = 0
    prediction_miss_roles: Tuple[str, ...] = ()
    unexecuted: List[dict] = []
    to_carry_out: List[str] = []
    if not deps.dry_run:
        try:
            grade_result = await call("queue.grade", {})
        except MCPToolError as exc:
            raise CycleError(f"cycle {cycle_index}: grading failed: {exc}") from exc
        # Only a MISS wakes anyone (handoffs/2026-10-05-stricter-wakes.md): a hit
        # is recorded by the grader and needs no advisor. queue.grade does not
        # say who proposed a prediction, so the wake cannot be narrowed to the
        # proposer yet (policy.yaml prediction_graded names both advisors).
        prediction_misses = sum(
            1 for g in (grade_result.get("graded") or ())
            if isinstance(g, Mapping) and g.get("status") == "graded_false"
        )
        prediction_graded = prediction_misses > 0
        prediction_miss_roles = _miss_proposers(deps.policy, grade_result, cycle_index)
        if prediction_graded and not prediction_miss_roles:
            # Nobody to wake (the proposer is not a role this build runs): no wake.
            prediction_graded = False
        unexecuted = grade_result.get("unexecuted", []) or []
        # Over MCP, queue.grade returns only `unexecuted_proposal_ids` (the
        # local dfqueue call returns full `unexecuted` dicts). Read both.
        unexecuted_ids = list(grade_result.get("unexecuted_proposal_ids") or []) or [
            (u.get("proposal") or {}).get("id") for u in unexecuted if isinstance(u, dict)
        ]
        to_carry_out = await _carry_out_wake_ids(call, unexecuted_ids, hold, cycle_index)

    # ---- 3. TRIAGE ------------------------------------------------------------
    event_hits: Dict[str, bool] = {}
    for role in ALL_ROLES:
        event_hits.update(_classify_diff_events(events_by_role.get(role, [])))

    order_watch: OrderWatchResult = evaluate_orders(
        (orders_state.get("orders") or []),
        game_tick=game_tick, retry_tick=retry_tick,
        threshold_ticks=deps.policy.stalled_order_threshold_ticks,
        renotify_ticks=deps.policy.stalled_order_renotify_ticks,
        renotify_cap_ticks=deps.policy.renotify_cap_ticks,
        max_wakes=deps.policy.renotify_max_wakes,
        cursor_store=deps.cursor_store,
        dry_run=deps.dry_run,
    )
    job_watch = await _job_watch(deps, call, game_tick, cycle_index, retry_tick)
    slow_hit, slow_roles, slow_detail = _classify_slow_announcements(events_by_role)

    # Lane triggers (handoffs/2026-10-05-stricter-wakes.md): what changed in
    # each role's own lane. Alerts are read here, once, so a fresh crossing can
    # wake the role it belongs to; the briefings reuse the same lines.
    alerts, alert_crossed, alert_lines = await _read_alert_state(call, deps.policy, vitals, cycle_index)
    ore_read = await _ore_watch(deps, call, cycle_index)
    unsupplied = await _unsupplied_watch(deps, call, orders_state, cycle_index)
    noble_rooms = await _noble_room_watch(deps, call, cycle_index)
    lane_store = _lane_store(deps)
    lane_state = lanes.LaneState()
    lane_wakes: Tuple[Any, ...] = ()
    pending_ids: List[str] = []
    #: queue_pending is an edge: pending proposals the Overseer has not already
    #: left pending (or whose defer has a reason to be looked at again). With no
    #: lane state every pending proposal counts, as before.
    fresh_pending: Optional[List[str]] = None
    if deps.policy.lane_triggers:
        try:
            lane_state = lane_store.load()
            pending_ids = list((queue_state.get("proposals") or {}).get("proposal_ids") or [])
            lane_state.cycles += 1
            lanes.apply_alert_edges(deps.policy, lane_state, alert_crossed, alert_lines, retry_tick)
            lanes.apply_ore_edges(deps.policy, lane_state, ore_read, retry_tick)
            lanes.apply_unsupplied_edges(deps.policy, lane_state, unsupplied, retry_tick)
            lanes.apply_noble_room_edges(deps.policy, lane_state, noble_rooms, retry_tick)
            lanes.apply_rulings(deps.policy, lane_state, pending_ids)
            lanes.apply_answers(deps.policy, lane_state, (queue_state.get("asks") or {}).get("ask_ids") or [])
            fresh_pending, quiet_pending = lanes.split_pending_for_overseer(
                deps.policy, lane_state, pending_ids, (queue_state.get("asks") or {}).get("ask_ids") or [],
            )
            for pid, why in quiet_pending:
                LOG.info("cycle %s: %s pending but no wake for the Overseer: %s", cycle_index, pid, why)
            lane_wakes = lanes.lane_wakes(deps.policy, lane_state, events_by_role)
            if not deps.dry_run:
                lane_store.save(lane_state)
        except Exception:  # noqa: BLE001 -- a lane-state fault must not stop the cycle
            LOG.exception("cycle %s: lane state unavailable; no lane wakes this cycle", cycle_index)
            lane_state = lanes.LaneState()
            lane_wakes = ()
    stuck_roles: Optional[Tuple[str, ...]] = None
    if deps.policy.lane_triggers and not event_hits.get("stuck_job", False):
        stuck_roles = lanes.stuck_job_roles(deps.policy, job_watch.due)
        if job_watch.any_due and not stuck_roles:
            LOG.info("cycle %s: due stuck job(s) belong to no role's lane; no wake", cycle_index)

    # The Planner's side: the computed season cursor (which also gives the
    # Quartermaster's `season_change` wake a real trigger) and, once the Planner
    # is enabled, bootstrap, review, ruling and shortfall wakes from `plan.status`.
    early_routing: Optional[Mapping[str, Any]] = None
    early_routing_read = False
    if deps.policy.plan.enabled and deps.policy.plan.shortfall.enabled:
        early_routing_read = True
        early_routing = await _read_routing(call, cycle_index)
    plan_state, season_edge, plan_result = await _plan_watch(
        deps, call, game_tick, cycle_index, hold, (early_routing or {}).get("frozen_types"), retry_tick,
    )
    plan_watch_dict = _plan_watch_dict(plan_state, season_edge, plan_result)
    roadmap_line = (plan_result.roadmap or {}).get("line")
    utilisation = await _utilisation(deps, call, vitals, game_tick, cycle_index)
    lane_wakes = (*lane_wakes, *(LaneWake(w.reason, w.detail, (w.role,)) for w in plan_result.wakes))

    signals = Signals(
        vital_nearing_threshold=_vital_nearing(vitals),
        vital_ticks_to_consequence=None,  # see module docstring: vitals.summary carries no timer
        stuck_job=event_hits.get("stuck_job", False) or job_watch.any_due,
        stuck_job_detail=job_watch.wake_detail(),
        stuck_job_roles=stuck_roles,
        season_change=bool(season_edge is not None and season_edge.changed and deps.policy.plan.season_wake),
        stalled_order=bool(order_watch.stalled_ids),
        stalled_order_ids=order_watch.stalled_ids,
        blocked_order=bool(order_watch.blocked_ids),
        blocked_order_ids=order_watch.blocked_ids,
        slow_announcement=slow_hit,
        slow_announcement_roles=slow_roles,
        slow_announcement_detail=slow_detail,
        prediction_graded=prediction_graded,
        prediction_misses=prediction_misses,
        prediction_miss_roles=prediction_miss_roles,
        lane_wakes=lane_wakes,
        game_days_since_routine_review=_game_days_since(deps.cursor_store, game_tick, deps.policy),
        queue_holds_for_overseer=(
            bool((queue_state.get("proposals") or {}).get("count", 0) if fresh_pending is None else fresh_pending)
            or bool(to_carry_out)
        ),
        open_ask_for_consultant=CONSULTANT in _open_ask_addressees(queue_state),  # gap 1, fixed
        open_ask_for_roles=_runnable_ask_addressees(queue_state, cycle_index),
    )
    triage_result = triage(signals, deps.policy, base_fps=clock_status.get("fps"))

    # Cursors of roles NOT woken this cycle advance as before (they are not
    # going to consume their events). A woken role's cursor, and the
    # routine-review cursor, advance only after a run that actually
    # completed (see the role loop below): a failed run must not advance
    # state, or the next review/diff window is silently skipped.
    woken_now = set(triage_result.roles_to_wake)
    for role in ALL_ROLES:
        if role not in woken_now:
            _commit_cursor(deps, new_cursors, role)

    # ---- Set the clock (never paused from ordinary triage -- see triage.py) --
    target_fps = deps.policy.base_fps if triage_result.clock == FULL_SPEED else deps.policy.think_fps
    if not deps.dry_run and clock_status.get("fps") != target_fps:
        await _call_write(
            call, "clock.set-speed", {"fps": target_fps},
            clock_changes=clock_changes, cycle_index=cycle_index,
        )

    # ---- 4/5. Advise, then decide-and-act, in the fixed roster order ---------
    briefings: Dict[str, dict] = {}
    ordinary_escalated = False
    roles_to_run: List[str] = list(triage_result.roles_to_wake)
    roles_woken_out: List[str] = list(roles_to_run)
    extra_wakes: Dict[str, Wake] = {}
    queue_refreshed = False
    known_ids: Set[str] = set(pending_ids) | set(lane_state.proposers)
    known_ask_ids: Set[str] = set((queue_state.get("asks") or {}).get("ask_ids") or []) | set(lane_state.askers)
    routing: Optional[Mapping[str, Any]] = early_routing
    routing_read = early_routing_read
    parallel_on = bool(deps.policy.parallel_proposers)
    if parallel_on and not getattr(deps.role_runner, "isolated_state", True):
        LOG.warning(
            "cycle %s: parallel.proposers is on but the runner has no per-run state dir "
            "(CONDUCTOR_THINKING_STATE_DIR unset); running serially", cycle_index,
        )
        parallel_on = False
    parallel_groups: List[Dict[str, Any]] = []
    cycle_started = time.monotonic()

    async def _launch(role: str, wake: Any, prompt: str, delay: float) -> RunResult:
        """One role's run: quicksave first for the Overseer, then the run
        itself. `delay` staggers the start of concurrent roles."""
        if delay > 0:
            await asyncio.sleep(delay)
        if role == OVERSEER:
            # docs/AGENT-LOOP.md §1 step 6: "quicksave before the Overseer
            # runs whenever it may act."
            await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)

        run_result = await _run_role(
            deps, call, role, prompt, wake=wake, cycle_index=cycle_index,
            wake_reasons=triage_result.reasons_for(role),
        )
        return run_result

    idx = 0
    while True:
        # Advisors have run; anything they filed (an ask above all) is not in
        # the queue read taken at the top of the cycle. Re-read once, at the
        # point where the next role (if any) is no longer an advisor, and wake
        # the Consultant for a newly open ask (first real cycle 2026-09-25:
        # ask-0001 was filed mid-cycle and waited a whole cycle).
        next_role = roles_to_run[idx] if idx < len(roles_to_run) else None
        if (
            not queue_refreshed and not deps.dry_run and deps.policy.consultant_rewake_after_advisors
            and next_role not in PROPOSERS and any(r.role in PROPOSERS for r in role_runs)
        ):
            queue_refreshed = True
            try:
                queue_state = await call("queue.overview", {})
            except MCPToolError as exc:
                LOG.error("cycle %s: queue re-read after the advisors failed: %s", cycle_index, exc)
            else:
                ran = {r.role for r in role_runs}
                for addressee in _open_ask_addressees(queue_state):
                    if addressee in roles_to_run or addressee in ran:
                        continue
                    if addressee not in ALL_ROLES or addressee == OVERSEER:
                        LOG.warning(
                            "cycle %s: an ask is open for %r, which the conductor does not run",
                            cycle_index, addressee,
                        )
                        continue
                    extra_wakes[addressee] = Wake(
                        "open_ask", f"an ask filed earlier this cycle is open for {addressee}",
                        (addressee,), FULL_SPEED,
                    )
                    # Inserted at idx: runs before the Overseer (if any) and
                    # after every advisor that already ran.
                    roles_to_run.insert(idx, addressee)
                    roles_woken_out.append(addressee)

        if idx >= len(roles_to_run):
            break
        role = roles_to_run[idx]
        idx += 1
        # Parallel proposers (policy `parallel.proposers`, default off): the
        # consecutive concurrent-safe roles from here run together. The Planner
        # (first) and the Overseer (the one judge, last) always run alone.
        group = [role]
        if parallel_on and role in CONCURRENT_ROLES:
            while idx < len(roles_to_run) and roles_to_run[idx] in CONCURRENT_ROLES:
                group.append(roles_to_run[idx])
                idx += 1
        prepared: List[Tuple[str, Any, str]] = []
        for role in group:

            # The Planner may be woken for several reasons at once (a review and an
            # accepted plan_change): its briefing carries all of them.
            wake = extra_wakes.get(role) or (
                triage_result.merged_wake_for(role) if role == PLANNER else triage_result.wake_for(role)
            )
            # Which proposal types the conductor runs or has frozen (stage 2D): one
            # cheap read, only when a role that needs it is about to be briefed.
            if not routing_read and not deps.dry_run and role in (*ADVISORS, OVERSEER):
                routing_read = True
                routing = await _read_routing(call, cycle_index)
            paused_now = paused_line(clock_status, hold, still_paused=pause_outcome is None or pause_outcome.still_paused)
            own_filings = None
            if role in PROPOSERS and not deps.dry_run and deps.policy.own_filings_recent > 0:
                own_filings = await _read_own_filings(call, role, deps.policy.own_filings_recent, cycle_index)
            # A cavern breach noted by last cycle's automine pass, said once to the
            # Overseer (taken from the store, so it is not repeated).
            automine_notes = _automine_store(deps).take() if (role == OVERSEER and not deps.dry_run) else []
            briefing = build_briefing(
                role=role, game_tick=game_tick or 0, wake=wake, vitals=vitals,
                diff_events=events_by_role.get(role, []),
                queue_summary=_queue_summary_for(role, queue_state),
                own_filings=own_filings, automine_notes=automine_notes,
                stuck_jobs=job_watch.lines, alerts=alerts,
                ore_exposed=_ore_lines_for(deps.policy, role, ore_read),
                frozen_types=(routing or {}).get("frozen_types") if role in ADVISORS else None,
                roadmap_line=roadmap_line if role in (OVERSEER, PLANNER) else None,
                utilisation=utilisation if role == PLANNER else None,
                paused=paused_now,
            )
            briefings[role] = briefing
            prompt = json.dumps(briefing, default=str)
            if role == OVERSEER and not deps.dry_run:
                # docs/CONDUCTOR-EXECUTION.md 3.3: the ruling turn gets a fixed-order
                # text briefing built from queue.pending_brief, ask last. A failed
                # read says so in the briefing; the run still goes ahead.
                pending_brief = await _read_pending_brief(call, cycle_index)
                prompt = build_ruling_briefing(
                    game_tick=game_tick or 0, wake=wake, vitals=vitals, alerts=alerts,
                    pending_brief=pending_brief, diff_events=events_by_role.get(role, []),
                    stuck_jobs=job_watch.lines, to_carry_out=to_carry_out, routing=routing,
                    roadmap_line=roadmap_line, paused=paused_now, automine_notes=automine_notes,
                )
                briefings[role] = {"ruling_prompt": prompt, "pending_brief": pending_brief}

            if deps.dry_run:
                continue
            prepared.append((role, wake, prompt))
        if not prepared:
            continue

        group_started = time.monotonic()
        if len(prepared) == 1:
            runs_done = [await _launch(prepared[0][0], prepared[0][1], prepared[0][2], 0.0)]
        else:
            LOG.info("cycle %s: running %s concurrently", cycle_index, [r for r, _, _ in prepared])
            runs_done = list(await asyncio.gather(*(
                _launch(r, w, pr, i * deps.policy.parallel_stagger_seconds)
                for i, (r, w, pr) in enumerate(prepared)
            )))
        parallel_groups.append({
            "roles": [r for r, _, _ in prepared], "concurrent": len(prepared) > 1,
            "wall_seconds": round(time.monotonic() - group_started, 3),
            "run_seconds": {rr.role: round(float(rr.wall_clock_seconds or 0.0), 3) for rr in runs_done},
        })
        role_runs.extend(runs_done)

        for (role, wake, _prompt), run_result in zip(prepared, runs_done):
            # Learn who proposed what: a pending proposal id that appeared during an
            # advisor's run is that advisor's (the conductor cannot read an author).
            # A completed run also serves whatever lane wakes were owed to the role.
            if deps.policy.lane_triggers and role == OVERSEER and run_result.ok:
                try:
                    after = await call("queue.overview", {})
                    lanes.record_overseer_seen(
                        lane_state, (after.get("proposals") or {}).get("proposal_ids") or [],
                        (after.get("asks") or {}).get("ask_ids") or [],
                    )
                    lane_store.save(lane_state)
                except Exception as exc:  # noqa: BLE001 -- best effort: worst case it wakes again
                    LOG.warning("cycle %s: recording the Overseer's seen proposals failed: %s", cycle_index, exc)
            if deps.policy.lane_triggers and role in PROPOSERS:
                try:
                    after = await call("queue.overview", {})
                    known_ids = lanes.attribute_new_proposals(
                        lane_state, role, known_ids, (after.get("proposals") or {}).get("proposal_ids") or [],
                        authors=(after.get("proposals") or {}).get("by_role"),
                    )
                    known_ask_ids = lanes.attribute_new_asks(
                        lane_state, role, known_ask_ids, (after.get("asks") or {}).get("ask_ids") or [],
                        authors=(after.get("asks") or {}).get("by_role"),
                    )
                except Exception as exc:  # noqa: BLE001 -- total: attribution is best effort
                    LOG.warning("cycle %s: proposer attribution after %s failed: %s", cycle_index, role, exc)
                if run_result.ok:
                    lanes.clear_served(lane_state, role)
                try:
                    lane_store.save(lane_state)
                except Exception:  # noqa: BLE001
                    LOG.exception("cycle %s: could not save lane state", cycle_index)

            # A bootstrap wake that left no plan: keep the refusal text for the
            # operator alert if the attempts run out (conductor/plan_watch.py).
            if role == PLANNER and plan_state is not None and wake is not None and "plan_bootstrap" in wake.reason + wake.detail:
                plan_state.last_refusal = last_refusal(run_result)
                try:
                    _plan_store(deps).save(plan_state)
                except Exception:  # noqa: BLE001
                    LOG.exception("cycle %s: could not save the plan watch state", cycle_index)

            # Only a run that completed consumes its diff window and counts as
            # having performed a routine review.
            if run_result.ok:
                _commit_cursor(deps, new_cursors, role)
                if game_tick is not None and any(
                    w.reason == "routine_review" and role in w.roles for w in triage_result.wakes
                ):
                    deps.cursor_store.set("__routine_review__", game_tick)

            # Fix 3: the Overseer's own Escalation section
            # (agents/overseer/role.md) is not tripwire-specific -- an
            # irreversible action, a contradicted fact or a repeatedly-failed
            # plan step can come up in an ORDINARY cycle too, not only while a
            # tripwire is already latched. A clean run that mechanically called
            # queue.escalate here pauses the fort the same way a tripwire does,
            # rather than only being detectable the next time one happens to
            # latch.
            if role == OVERSEER and _overseer_called_escalate(run_result):
                ordinary_escalated = True
                await _call_write(call, "clock.pause", {}, clock_changes=clock_changes, cycle_index=cycle_index)
                _mark_pause_owned(deps)
                LOG.error(
                    "ESCALATION: cycle %s's Overseer explicitly escalated via queue.escalate "
                    "during an ordinary cycle; the fort is now PAUSED.",
                    cycle_index,
                )

    # ---- 6. EXECUTE (docs/CONDUCTOR-EXECUTION.md 4.5) --------------------------
    execute_report: Optional[ExecuteReport] = None
    if not deps.dry_run:
        execute_report = await _execute_phase(
            deps, call, cycle_index=cycle_index, game_tick=game_tick, hold=hold, escalated=ordinary_escalated,
            ore_read=ore_read, lane_state=lane_state, clock_changes=clock_changes, latched=False,
        )

    # ---- 7. AUTOMINE (research/2026-10-09-auto-mine.md): a game write, blocked by any hold --
    automine_report: Optional[automine_mod.AutomineReport] = None
    if not deps.dry_run:
        automine_report = await _automine_phase(
            deps, call, cycle_index=cycle_index, hold=hold, escalated=ordinary_escalated,
        )

    result = CycleResult(
        cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
        signals=signals,
        clock_level=(PAUSED if ordinary_escalated else triage_result.clock),
        roles_woken=tuple(roles_woken_out),
        clock_changes=clock_changes, role_runs=role_runs, tripwire=None,
        escalated=ordinary_escalated,
        unexecuted=unexecuted, archived_path=None, dry_run=deps.dry_run,
        pause_watch=pause_watch_dict,
        plan_watch=plan_watch_dict,
        execute=execute_report.as_dict() if execute_report is not None else None,
        automine=automine_report.as_dict() if automine_report is not None else None,
        role_groups=parallel_groups, wall_seconds=round(time.monotonic() - cycle_started, 3),
        plan=(
            {
                "would_read": list(ALL_ROLES),
                "would_wake": list(triage_result.roles_to_wake),
                "would_set_clock": target_fps,
                "wakes": [
                    {"reason": w.reason, "detail": w.detail, "roles": list(w.roles), "clock": w.clock}
                    for w in triage_result.wakes
                ],
            }
            if deps.dry_run else None
        ),
    )
    if not deps.dry_run:
        result.archived_path = _archive(deps, cycle_index, result, briefings=briefings)
    return result


async def _read_alert_state(
    call: Callable, policy: Policy, vitals: Mapping[str, Any], cycle_index: int,
) -> Tuple[List[str], Dict[str, Optional[bool]], Dict[str, str]]:
    """Threshold-alert lines for this cycle (policy.yaml `threshold_alerts`):
    each distinct read taken once, a failed read logged and its line dropped.
    Also returns, per alert name, whether it is crossed (`None` when its read
    failed, so edge state is kept rather than read as cleared) and its line.
    Total by design, like the job watch."""
    reads: Dict[str, Any] = {}
    cache: Dict[str, Any] = {}
    for alert in policy.threshold_alerts:
        key = json.dumps([alert.tool, alert.args], sort_keys=True, default=str)
        if key not in cache:
            try:
                cache[key] = await call(alert.tool, dict(alert.args))
            except Exception as exc:  # noqa: BLE001 -- deliberately total
                LOG.warning("cycle %s: alert read %s failed: %s", cycle_index, alert.tool, exc)
                cache[key] = None
        reads[alert.name] = cache[key]
    crossed: Dict[str, Optional[bool]] = {}
    by_name: Dict[str, str] = {}
    try:
        for alert in policy.threshold_alerts:
            if reads.get(alert.name) is None:
                crossed[alert.name] = None
                continue
            found = evaluate_threshold_alerts([alert], reads, vitals.get("alive"))
            crossed[alert.name] = bool(found)
            if found:
                by_name[alert.name] = found[0]
        lines = evaluate_threshold_alerts(policy.threshold_alerts, reads, vitals.get("alive"))
    except Exception:  # noqa: BLE001 -- deliberately total
        LOG.exception("cycle %s: could not evaluate threshold alerts", cycle_index)
        return [], {}, {}
    return lines, crossed, by_name


async def _read_alerts(call: Callable, policy: Policy, vitals: Mapping[str, Any], cycle_index: int) -> List[str]:
    return (await _read_alert_state(call, policy, vitals, cycle_index))[0]


async def _read_own_filings(call: Callable, role: str, recent: int, cycle_index: int) -> Optional[List[str]]:
    """`queue.filings_brief` for one proposer's "YOUR RECENT FILINGS" block;
    `None` (block omitted) if the read fails: a briefing never blocks on it."""
    try:
        result = await call("queue.filings_brief", {"roles": [role], "recent": recent})
    except Exception as exc:  # noqa: BLE001 -- deliberately total
        LOG.error("cycle %s: queue.filings_brief failed for %s: %s", cycle_index, role, exc)
        return None
    lines = ((result or {}).get("filings") or {}).get(role) if isinstance(result, dict) else None
    return list(lines) if isinstance(lines, list) else None


async def _read_pending_brief(call: Callable, cycle_index: int) -> Optional[Dict[str, Any]]:
    """`queue.pending_brief` for the Overseer's ruling briefing; `None` if the
    read fails (the briefing then says so)."""
    try:
        result = await call("queue.pending_brief", {})
    except Exception as exc:  # noqa: BLE001 -- deliberately total
        LOG.error("cycle %s: queue.pending_brief failed: %s", cycle_index, exc)
        return None
    return result if isinstance(result, dict) else None



def _tripwire_store(deps: "CycleDeps") -> TripwireStore:
    return TripwireStore(deps.cursor_store.path.with_name("tripwire_state.json"))


def _human_alert(deps: "CycleDeps", reason: str) -> Dict[str, Any]:
    """Raise the one human alert (`pause_watch._alert`, today a CRITICAL log
    line plus the status block's standing alert) for a tripwire the conductor
    will not resolve. Returns the pause-watch dict for the cycle result."""
    store = _pause_store(deps)
    state = store.load()
    outcome = WatchOutcome(Verdict.ALERT, reason, still_paused=True)
    _pause_alert(state, outcome, deps.wall_clock(), reason)
    store.save(state)
    return outcome.as_dict()


async def _tripwire_cycle(
    deps: "CycleDeps", call: Callable, *, cycle_index: int, game_tick, game_tick_error,
    clock_status: Mapping[str, Any], vitals: Mapping[str, Any], events_by_role, queue_state, new_cursors,
    clock_changes: List[Dict[str, Any]], tripwire: dict, hold: HoldState,
) -> "CycleResult":
    """One cycle with a latched tripwire. The sequence, all inside this cycle:

    1. a repeat check: the same cause latching more than the policy limit
       within its window goes to the human and runs nothing;
    2. quicksave, then the cause's owner run(s) (`tripwire_owners`, may file
       proposals), then the Overseer, who rules on them and gives the verdict;
    3. only an explicit `pause.verdict` resume=true from the Overseer's run
       resumes (`finish_after_overseer`, tick verified, once). The latch is
       cleared first because `clock.resume` refuses under one. No verdict, a
       false one, an escalation or an unclean run leaves the latch standing,
       the fort paused and the human alerted. An operator hold removes the
       resume even after a true verdict (the latch is still cleared, as it was
       before this stage).
    """
    reason = tripwire.get("reason")
    owners = owners_for(deps.policy.tripwire_owners, reason)
    sequence = (*owners, OVERSEER)
    detail = f"{reason}: {tripwire.get('detail')}"
    role_runs: List[RunResult] = []
    briefings: Dict[str, Any] = {}
    escalated = False
    pause_dict: Optional[Dict[str, Any]] = None

    for other in ALL_ROLES:  # everyone not in the sequence consumes nothing this cycle
        if other not in sequence:
            _commit_cursor(deps, new_cursors, other)

    if deps.dry_run:
        return CycleResult(
            cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
            signals=Signals(), clock_level=PAUSED, roles_woken=sequence, clock_changes=clock_changes,
            role_runs=role_runs, tripwire=tripwire, escalated=False, unexecuted=[],
            archived_path=None, dry_run=True,
            plan={"would_read": list(ALL_ROLES), "would_wake": list(sequence), "tripwire": tripwire},
        )

    # ---- 1. the repeat counter ------------------------------------------------
    key = {"reason": str(reason), "tick": tripwire.get("tick")}
    repeat_reason: Optional[str] = None
    store = _tripwire_store(deps)
    try:
        tstate = store.load()
    except TripwireStateError as exc:
        LOG.error("cycle %s: tripwire state unreadable (%s); treating the latch as a repeat", cycle_index, exc)
        tstate = None
        repeat_reason = "the tripwire repeat counter's state file is unreadable"
    if tstate is not None:
        note_latch(tstate, tripwire)
        count = repeat_count(tstate, tripwire, deps.policy.tripwire_repeat_window_ticks)
        standing = tstate.repeat_escalated == key
        if standing or count > deps.policy.tripwire_repeat_limit:
            repeat_reason = (
                f"tripwire {reason} has latched {count} times within "
                f"{deps.policy.tripwire_repeat_window_ticks} game ticks (limit "
                f"{deps.policy.tripwire_repeat_limit}); not re-running the sequence"
            )
            tstate.repeat_escalated = key
        try:
            store.save(tstate)
        except Exception:  # noqa: BLE001 -- a counter write fault must not stop the safety path
            LOG.exception("cycle %s: could not save the tripwire repeat state", cycle_index)

    if repeat_reason is not None:
        pause_dict = _human_alert(deps, repeat_reason)
        LOG.error("ESCALATION: cycle %s: %s; the fort stays PAUSED, tripwire=%s", cycle_index, repeat_reason, tripwire)
        result = CycleResult(
            cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
            signals=Signals(), clock_level=PAUSED, roles_woken=(), clock_changes=clock_changes,
            role_runs=role_runs, tripwire=tripwire, escalated=True, unexecuted=[],
            archived_path=None, dry_run=False, pause_watch=pause_dict,
        )
        result.archived_path = _archive(deps, cycle_index, result, briefings=briefings)
        return result

    # ---- 2. quicksave, the owner(s), then the Overseer ----------------------------
    await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)
    verdict_baseline: Optional[int] = None
    overseer_run: Optional[RunResult] = None
    for role in sequence:
        if role == OVERSEER:
            note = (
                f"; the {', '.join(owners)} ran first this cycle and may have filed proposals" if owners else ""
            )
            wake = Wake(
                "tripwire", f"{detail}{note}. Rule on what is pending, then give your pause.verdict.",
                (OVERSEER,), PAUSED,
            )
            pending_brief = await _read_pending_brief(call, cycle_index)
            prompt = build_ruling_briefing(
                game_tick=game_tick or 0, wake=wake, vitals=vitals, alerts=[],
                pending_brief=pending_brief, diff_events=events_by_role.get(OVERSEER, []),
                paused=paused_line(clock_status, hold),
            )
            briefings[OVERSEER] = {"ruling_prompt": prompt, "pending_brief": pending_brief}
            verdict_baseline = await read_verdict_baseline(call)
        else:
            wake = Wake("tripwire", detail, (role,), PAUSED)
            briefing = build_briefing(
                role=role, game_tick=game_tick or 0, wake=wake, vitals=vitals,
                diff_events=events_by_role.get(role, []),
                queue_summary=_queue_summary_for(role, queue_state),
                paused=paused_line(clock_status, hold),
            )
            briefings[role] = briefing
            prompt = json.dumps(briefing, default=str)
        run_result = await _run_role(deps, call, role, prompt, wake=wake, cycle_index=cycle_index)
        role_runs.append(run_result)
        if run_result.ok:
            _commit_cursor(deps, new_cursors, role)  # a failed run keeps its events
        elif role != OVERSEER:
            LOG.error(
                "cycle %s: tripwire owner %s did not complete (status=%s); the Overseer still runs",
                cycle_index, role, run_result.status,
            )
        if role == OVERSEER:
            overseer_run = run_result

    # ---- 3. the verdict --------------------------------------------------------------
    assert overseer_run is not None
    called_escalate = _overseer_called_escalate(overseer_run)
    run_unclean = (not overseer_run.ok) or overseer_run.timed_out
    escalated = run_unclean or called_escalate
    # Stage 2D (docs/CONDUCTOR-EXECUTION.md 4.5): while the latch still stands,
    # the execute phase may run only high-urgency routed steps, accepted in this
    # episode. It runs before the verdict is acted on, never after a resume, and
    # never under an escalation or an operator hold without --allow-execution.
    execute_report: Optional[ExecuteReport] = None
    if not escalated:
        lane_state = lanes.LaneState()
        try:
            lane_state = _lane_store(deps).load()
        except Exception:  # noqa: BLE001
            LOG.exception("cycle %s: lane state unavailable during the tripwire execute pass", cycle_index)
        execute_report = await _execute_phase(
            deps, call, cycle_index=cycle_index, game_tick=game_tick, hold=hold, escalated=False,
            ore_read=await _ore_watch(deps, call, cycle_index), lane_state=lane_state,
            clock_changes=clock_changes, latched=True,
        )
    verdict = None if escalated else await read_verdict_after(call, verdict_baseline)
    if verdict is not None and verdict.get("resume"):
        # clock.resume refuses while a latch stands: clear it first. Under an
        # operator hold the latch is cleared and the fort left paused.
        await _call_write(call, "clock.clear", {}, clock_changes=clock_changes, cycle_index=cycle_index)
    finished = await finish_after_overseer(
        call, _pause_store(deps), deps.pause_policy or load_pause_policy(),
        escalated=escalated, clock_status=clock_status, now=deps.wall_clock(), sleep=deps.pause_sleep,
        verdict=verdict, held=hold.held, what=f"tripwire {reason}",
    )
    pause_dict = finished.as_dict()
    clock_level = PAUSED if finished.still_paused else FULL_SPEED
    if called_escalate:
        LOG.error(
            "ESCALATION: cycle %s's Overseer explicitly escalated via queue.escalate; "
            "the fort stays PAUSED, tripwire=%s", cycle_index, tripwire,
        )
    elif run_unclean:
        LOG.error(
            "ESCALATION: cycle %s's Overseer run did not complete cleanly (status=%s, ok=%s); "
            "the fort stays PAUSED, tripwire=%s", cycle_index, overseer_run.status, overseer_run.ok, tripwire,
        )
    elif finished.resumed:
        LOG.info("cycle %s: tripwire %s resumed on the Overseer's explicit verdict", cycle_index, reason)
    else:
        LOG.error(
            "cycle %s: tripwire %s: no resume verdict acted on (%s); the fort stays PAUSED",
            cycle_index, reason, finished.reason,
        )

    result = CycleResult(
        cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
        signals=Signals(), clock_level=clock_level, roles_woken=sequence, clock_changes=clock_changes,
        role_runs=role_runs, tripwire=tripwire, escalated=escalated, unexecuted=[],
        archived_path=None, dry_run=False, pause_watch=pause_dict,
        execute=execute_report.as_dict() if execute_report is not None else None,
    )
    result.archived_path = _archive(deps, cycle_index, result, briefings=briefings)
    return result


def _pause_store(deps: "CycleDeps") -> PauseWatchStore:
    return deps.pause_store or PauseWatchStore(deps.cursor_store.path.with_name("pause_watch.json"))


def _lane_store(deps: "CycleDeps") -> "lanes.LaneStore":
    return lanes.LaneStore(deps.cursor_store.path.with_name("lane_state.json"))


def _job_store(deps: "CycleDeps") -> JobWatchStore:
    return JobWatchStore(deps.cursor_store.path.with_name("job_watch.json"))


def _plan_store(deps: "CycleDeps") -> PlanWatchStore:
    return PlanWatchStore(deps.cursor_store.path.with_name("plan_watch.json"))


async def _plan_watch(
    deps: "CycleDeps", call: Callable, game_tick: Optional[int], cycle_index: int, hold: HoldState,
    frozen_types: Optional[Sequence[str]], retry_tick: Optional[int] = None,
) -> Tuple[Optional[PlanWatchState], Optional[SeasonEdge], PlanWatchResult]:
    """The Planner's conductor side (conductor/plan_watch.py): advance the
    season cursor and, when the Planner is enabled, read `plan.status` once and
    fold it in. Total by design, like the other watches: an unreadable state
    file, an undeployed tool or a tool error logs, wakes nobody and leaves the
    state as it was (a failed read never reads as "no plan" or "no shortfall").
    The state is saved unless this is a dry run."""
    plan = deps.policy.plan
    result = PlanWatchResult()
    if not (plan.season_wake or plan.enabled):
        return None, None, result
    store = _plan_store(deps)
    try:
        state = store.load()
    except Exception:  # noqa: BLE001 -- a corrupt file must not stop the cycle or re-arm every backoff
        LOG.exception("cycle %s: the plan watch state is unreadable; no plan wakes this cycle", cycle_index)
        return None, None, result
    edge = advance_season(state, game_tick, plan.season_ticks)
    if plan.enabled:
        status: Optional[Mapping[str, Any]] = None
        try:
            raw = await call(PLAN_STATUS_TOOL, {})
            status = raw if isinstance(raw, Mapping) else None
        except Exception as exc:  # noqa: BLE001 -- total, see docstring
            LOG.warning("cycle %s: %s failed; no plan wakes this cycle: %s", cycle_index, PLAN_STATUS_TOOL, exc)
        result = evaluate_plan(
            status, game_tick, plan, state, edge, held=hold.held, frozen_types=frozen_types,
            retry_tick=retry_tick,
        )
        for alert in result.alerts:
            LOG.critical("PLAN: %s", alert)
    if not deps.dry_run:
        try:
            store.save(state)
        except Exception:  # noqa: BLE001
            LOG.exception("cycle %s: could not save the plan watch state", cycle_index)
    return state, edge, result


async def _utilisation(
    deps: "CycleDeps", call: Callable, vitals: Mapping[str, Any], game_tick: Optional[int], cycle_index: int,
) -> Optional[Dict[str, Any]]:
    """Fort roadmap V1 item 6 (conductor/utilisation.py): one `labor.unit-status`
    read a cycle, counted into a sample and appended to the series (not on a
    dry run), and the series' summary for the Planner's briefing. Total, like
    the other watches: a failed read logs and gives `None`, never a zero."""
    if not deps.policy.plan.enabled:
        return None
    store = UtilisationStore(deps.cursor_store.path.with_name("utilisation.jsonl"))
    try:
        row = utilisation_sample(await call(UNIT_STATUS_TOOL, {}), vitals.get("alive"), game_tick)
        if row is None:
            LOG.warning("cycle %s: %s gave no usable citizen list; no utilisation sample", cycle_index, UNIT_STATUS_TOOL)
        elif not deps.dry_run:
            store.append(row)
        summary = store.summary()
        return summary if summary.get("samples") else None
    except Exception as exc:  # noqa: BLE001 -- total, see docstring
        LOG.warning("cycle %s: utilisation sampling failed: %s", cycle_index, exc)
        return None


def _plan_watch_dict(
    state: Optional[PlanWatchState], edge: Optional[SeasonEdge], result: PlanWatchResult,
) -> Optional[Dict[str, Any]]:
    if state is None:
        return None
    out: Dict[str, Any] = result.as_dict()
    if edge is not None:
        out["season"] = {"index": edge.index, "changed": edge.changed, "first": edge.first, "reload": edge.reload}
    if state.bootstrap_escalated:
        out["standing_alert"] = (
            f"no fort plan after {state.bootstrap.wakes} Planner wakes; "
            f"last refusal: {state.last_refusal or 'none recorded'}"
        )
    return out


async def _ore_watch(deps: "CycleDeps", call: Callable, cycle_index: int) -> Optional[OreRead]:
    """Poll `blueprint.sites` for exposed ore (conductor/ore_watch.py). Total by
    design, like the job watch: an undeployed allowlist entry or a tool error
    logs loudly, returns `None`, and the lane state is left exactly as it was
    (a failed poll never reads as "mined")."""
    if not any(lane.ore for lane in deps.policy.lane_triggers.values()):
        return None
    try:
        return ore_read_from_sites(await call(ORE_POLL_TOOL, {}))
    except Exception:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.exception("cycle %s: the ore watch failed; carrying on without it", cycle_index)
        return None


async def _unsupplied_watch(
    deps: "CycleDeps", call: Callable, orders_state: Any, cycle_index: int,
) -> Optional[UnsuppliedRead]:
    """Poll `workjob.unsupplied` and join this cycle's `orders.list`
    (conductor/unsupplied_watch.py). Total by design, like the ore watch: a
    tool error or an undeployed allowlist entry logs loudly and returns `None`,
    leaving the lane state as it was. An order list with no `orders` array is
    passed on as unreadable, never as an empty list."""
    if not any(lane.unsupplied for lane in deps.policy.lane_triggers.values()):
        return None
    orders = orders_state.get("orders") if isinstance(orders_state, Mapping) else None
    try:
        return unsupplied_read(await call(UNSUPPLIED_POLL_TOOL, {}), orders if isinstance(orders, list) else None)
    except Exception:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.exception("cycle %s: the unsupplied-building watch failed; carrying on without it", cycle_index)
        return None


async def _noble_room_watch(
    deps: "CycleDeps", call: Callable, cycle_index: int,
) -> Optional[noble_room_watch.NobleRoomRead]:
    """The noble-room watch (conductor/noble_room_watch.py): `nobles.list`, then
    `nobles.requirements` for each held position (bounded by policy), then, only
    for an unmet room, `zone.list` for the unowned zones of that kind, and one
    `queue.overview` for open assign-owner steps (coverage). Total by design:
    any fault logs and returns `None`, leaving the lane state as it was. A
    position whose requirements read fails is named unreadable, never judged."""
    if not any(lane.noble_rooms for lane in deps.policy.lane_triggers.values()):
        return None
    pol = deps.policy.noble_room
    try:
        held = noble_room_watch.held_positions(await call(noble_room_watch.LIST_TOOL, {}), pol.max_positions)
        if held is None:
            LOG.warning("cycle %s: nobles.list was not a position list; no noble-room signal", cycle_index)
            return None
        items: List[noble_room_watch.NobleRoomItem] = []
        bad_codes = set()
        for code, uid, name in held:
            try:
                kinds = noble_room_watch.unmet_kinds(
                    await call(noble_room_watch.REQUIREMENTS_TOOL, {"position_code": code}), uid, pol.statuses,
                )
            except MCPToolError as exc:
                LOG.warning("cycle %s: nobles.requirements %s failed: %s", cycle_index, code, exc)
                kinds = None
            if kinds is None:
                bad_codes.add(code)
                continue
            for kind in kinds:
                try:
                    zones = noble_room_watch.unowned_zone_ids(await call(
                        noble_room_watch.ZONE_LIST_TOOL,
                        {"kind_filter": kind, "owner_filter": "unowned", "valid_filter": "", "near_landmark_filter": ""},
                    ))
                except MCPToolError:
                    zones = None
                items.append(noble_room_watch.NobleRoomItem(code, uid, name, kind, zones))
        covered: frozenset = frozenset()
        if items:
            try:
                got = noble_room_watch.covered_unit_ids(await call(
                    "queue.overview", {"limit": 1, "open_steps_for": [noble_room_watch.ASSIGN_TOOL]},
                ))
            except MCPToolError as exc:
                LOG.warning("cycle %s: coverage read failed (%s); not suppressing the noble-room wake", cycle_index, exc)
                got = None
            covered = got if got is not None else frozenset()
        return noble_room_watch.NobleRoomRead(
            items=tuple(items), covered_units=covered, unreadable_codes=frozenset(bad_codes),
        )
    except Exception:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.exception("cycle %s: the noble-room watch failed; carrying on without it", cycle_index)
        return None


def _ore_lines_for(policy: Any, role: str, ore_read: Optional[OreRead]) -> Optional[List[str]]:
    """The standing exposure lines for a role whose lane has `ore`, else `None`
    (the briefing then has no `ore_exposed` key at all)."""
    lane = policy.lane_triggers.get(role)
    if ore_read is None or lane is None or not lane.ore:
        return None
    return ore_read.lines


async def _job_watch(deps: "CycleDeps", call: Callable, game_tick: Optional[int], cycle_index: int,
                     retry_tick: Optional[int] = None) -> JobWatchResult:
    """Poll `stuckjobs.find` (conductor/job_watch.py). Total by design, like the
    pause watchdog: an undeployed allowlist entry, a tool error or a corrupt
    state file logs loudly and the cycle carries on with no stuck-job signal."""
    try:
        found = await call("stuckjobs.find", {})
        return evaluate_jobs(
            jobs_from_result(found), game_tick=game_tick, retry_tick=retry_tick,
            unclaimed_threshold_ticks=deps.policy.stuck_job_unclaimed_threshold_ticks,
            suspended_threshold_ticks=deps.policy.stuck_job_suspended_threshold_ticks,
            renotify_ticks=deps.policy.stuck_job_renotify_ticks,
            renotify_cap_ticks=deps.policy.renotify_cap_ticks,
            max_wakes=deps.policy.renotify_max_wakes,
            store=_job_store(deps), dry_run=deps.dry_run,
        )
    except Exception:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.exception("cycle %s: the stuck-job watch failed; carrying on without it", cycle_index)
        return JobWatchResult()


def _mark_pause_owned(deps: "CycleDeps") -> None:
    """The conductor's own escalation pause is recorded so the watchdog never
    treats it as unowned. Never raises: bookkeeping must not fail a cycle."""
    try:
        _pause_store(deps).mark_owned(OWNED_ESCALATION, deps.wall_clock())
    except Exception:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.exception("could not record the escalation pause as owned")


async def _pause_watch(
    deps: "CycleDeps", call: Callable, clock_status: Mapping[str, Any], cycle_index: int, hold: HoldState,
):
    """One watchdog pass. Total by design: a bug or an undeployed tool in the
    watchdog logs loudly and the cycle goes on as it did before the watchdog
    existed; it must never be the reason a cycle fails."""
    try:
        return await run_pause_watch(
            call, _pause_store(deps), deps.pause_policy or load_pause_policy(),
            clock_status=clock_status, now=deps.wall_clock(), sleep=deps.pause_sleep,
            dry_run=deps.dry_run, held=hold.held,
        )
    except Exception:  # noqa: BLE001 -- deliberately total, see docstring
        LOG.exception("cycle %s: the pause watchdog failed; carrying on without it", cycle_index)
        return None


async def _paused_cycle_result(
    deps: "CycleDeps", call: Callable, *, cycle_index: int, game_tick, game_tick_error,
    clock_status: Mapping[str, Any], vitals: Mapping[str, Any], events_by_role, queue_state, new_cursors,
    clock_changes: List[Dict[str, Any]], pause_outcome, hold: HoldState,
) -> "CycleResult":
    """The fort is still paused after the watchdog's pass: no ordinary triage
    (advisors would deliberate over a frozen fort). When the verdict is
    `wake_overseer`, run the Overseer once on an `unexplained_pause` wake and
    let `finish_after_overseer` decide: only an explicit `pause.verdict`
    resume=true from that run resumes (once, tick verified); no verdict, a
    false one, an escalation or an unclean run keeps the fort paused and
    alerts the human (silence is not consent)."""
    role_runs: List[RunResult] = []
    escalated = False
    briefings: Dict[str, Any] = {}
    woken: tuple = ()

    if pause_outcome.verdict is Verdict.WAKE_OVERSEER and pause_outcome.wake_detail and not deps.dry_run:
        wake = Wake(UNEXPLAINED_PAUSE, pause_outcome.wake_detail, (OVERSEER,), PAUSED)
        woken = (OVERSEER,)
        for other in ALL_ROLES:
            if other != OVERSEER:
                _commit_cursor(deps, new_cursors, other)
        await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)
        briefing = build_briefing(
            role=OVERSEER, game_tick=game_tick or 0, wake=wake, vitals=vitals,
            diff_events=events_by_role.get(OVERSEER, []),
            queue_summary=_queue_summary_for(OVERSEER, queue_state),
            paused=paused_line(clock_status, hold),
        )
        briefings[OVERSEER] = briefing
        verdict_baseline = await read_verdict_baseline(call)
        run_result = await _run_role(
            deps, call, OVERSEER, json.dumps(briefing, default=str), wake=wake, cycle_index=cycle_index,
        )
        role_runs.append(run_result)
        if run_result.ok:
            _commit_cursor(deps, new_cursors, OVERSEER)
        escalated = _overseer_called_escalate(run_result) or (not run_result.ok) or run_result.timed_out
        # Silence is not consent: resume only on an explicit pause.verdict
        # resume=true written by THIS run (baseline id taken before it ran).
        verdict = None if escalated else await read_verdict_after(call, verdict_baseline)
        finished = await finish_after_overseer(
            call, _pause_store(deps), deps.pause_policy or load_pause_policy(),
            escalated=escalated, clock_status=clock_status, now=deps.wall_clock(), sleep=deps.pause_sleep,
            verdict=verdict, held=hold.held,
        )
        pause_outcome.actions.extend(finished.actions)
        pause_outcome.alerts.extend(finished.alerts)
        pause_outcome.resumed = finished.resumed
        pause_outcome.still_paused = finished.still_paused
        pause_outcome.alert = finished.alert
        pause_outcome.waiting_on_human = False
        if finished.verdict in (Verdict.ALERT, Verdict.HELD):
            pause_outcome.verdict = finished.verdict

    # Nothing woken (a hold, an owned pause, a grace wait): no role consumes
    # anything, so no cursor moves.
    result = CycleResult(
        cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
        signals=Signals(), clock_level=PAUSED if pause_outcome.still_paused else FULL_SPEED,
        roles_woken=woken, clock_changes=clock_changes, role_runs=role_runs, tripwire=None,
        escalated=escalated, unexecuted=[], archived_path=None, dry_run=deps.dry_run,
        pause_watch=pause_outcome.as_dict(),
        plan=(
            {"would_read": list(ALL_ROLES), "would_wake": [], "pause_watch": pause_outcome.as_dict()}
            if deps.dry_run else None
        ),
    )
    if not deps.dry_run:
        result.archived_path = _archive(deps, cycle_index, result, briefings=briefings)
    return result


def _game_days_since(
    cursor_store: CursorStore, game_tick: Optional[int], policy: Policy,
) -> float:
    """Game days since the routine-review cursor was last advanced. Reuses
    `CursorStore` (keyed `"__routine_review__"`, a reserved role-shaped
    string no real role name collides with) rather than a second, parallel
    state file -- one small JSON file for all of this service's "last time
    X happened" bookkeeping. `run_cycle` itself is what advances this
    cursor once the routine-review wake reason has actually fired (see the
    block right after `triage()` is called); this function only reads it,
    staying a pure query."""
    if game_tick is None:
        return 0.0
    last = cursor_store.get("__routine_review__")
    if last == 0:
        return float(policy.routine_review_interval_game_days)  # never reviewed: due immediately
    return max(0.0, (game_tick - last)) / 1200.0  # 1200 ticks/game day, dfqueue.grade's own constant





def _archive(
    deps: CycleDeps, cycle_index: int, result: CycleResult, *, briefings: Dict[str, Any],
) -> Any:
    summary = {
        "cycle_index": cycle_index,
        "game_tick": result.game_tick,
        "game_tick_error": result.game_tick_error,
        "clock_level": result.clock_level,
        "roles_woken": list(result.roles_woken),
        "tripwire": result.tripwire,
        "escalated": result.escalated,
        "pause_watch": result.pause_watch,
        "plan_watch": result.plan_watch,
        "role_groups": result.role_groups,
        "wall_seconds": result.wall_seconds,
        "execute": result.execute,
        "unexecuted_proposal_ids": [u.get("proposal", {}).get("id") for u in result.unexecuted],
    }
    role_run_dicts = [
        {
            "role": r.role, "ok": r.ok, "status": r.status, "cost_usd": r.cost_usd,
            "wall_clock_seconds": r.wall_clock_seconds, "timed_out": r.timed_out,
            "tool_summary": r.tool_summary, "final_answer": r.final_answer, "error": r.error,
            "usage": r.usage, "assistant_turns": r.assistant_turns,
        }
        for r in result.role_runs
    ]
    for r in result.role_runs:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        total = deps.archive.append_daily_cost(today, r.cost_usd)
        unknown = deps.archive.daily_unknown_runs(today)
        cost_text = "UNKNOWN" if r.cost_usd is None else f"{r.cost_usd:.6f}"
        LOG.info(
            "cycle %s: role=%s cost_usd=%s wall_clock_seconds=%.1f "
            "daily_total_usd=%.6f (known only; %d run(s) today with unknown cost)",
            cycle_index, r.role, cost_text, r.wall_clock_seconds, total, unknown,
        )
        if r.usage or r.assistant_turns is not None:
            LOG.info(
                "cycle %s: role=%s turns=%s usage=%s", cycle_index, r.role,
                r.assistant_turns, json.dumps(r.usage, sort_keys=True),
            )
    return deps.archive.write_cycle(
        cycle_index, summary=summary, briefings=briefings,
        clock_changes=result.clock_changes, role_runs=role_run_dicts,
    )
