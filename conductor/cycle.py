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
   stays `False` always; left as a documented gap, not a silent one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from conductor.archive import CycleArchive
from conductor.briefing import build_briefing, build_ruling_briefing, evaluate_threshold_alerts
from conductor import lanes
from conductor.cursors import CursorStore
from conductor.game_tick import GameTickError, game_tick_from_overview
from conductor.hold import HoldState, HoldStore, hold_path_for
from conductor.mcp_client import MCPToolError, ToolCaller, tool_name
from conductor.job_watch import JobWatchResult, JobWatchStore, evaluate_jobs, jobs_from_result
from conductor.ore_watch import POLL_TOOL as ORE_POLL_TOOL, OreRead, ore_read_from_sites
from conductor.order_watch import OrderWatchResult, evaluate_orders
from conductor.pause_watch import (
    OWNED_ESCALATION, UNEXPLAINED_PAUSE, PauseWatchStore, PausePolicy, Verdict,
    finish_after_overseer, load_pause_policy, read_verdict_after, read_verdict_baseline, run_pause_watch,
)
from conductor.policy import FULL_SPEED, PAUSED, Policy
from conductor.runner import RoleRunner, RunResult
from conductor.triage import ADVISORS, CONSULTANT, OVERSEER, Signals, Wake, triage

LOG = logging.getLogger("conductor.cycle")

#: The roles this cycle ever drains a diff for and may wake, in the fixed
#: order docs/AGENT-LOOP.md §4 names: "advisors, then Consultant, then
#: Overseer." Tuple, not a set, so it also fixes drain/launch order.
ALL_ROLES = (*ADVISORS, CONSULTANT, OVERSEER)

#: docs/AGENT-ARCHITECTURE.md §4's own closed wake-event vocabulary, scoped
#: to the subset conductor/triage.py's Signals carries as a plain boolean.
#: Maps a drained diff.since event's own "type" field to the Signals field
#: it sets. **Unverified against a real diff.since payload** (no VM this
#: stream) -- the exact key a drained event carries its classification
#: under was not independently re-derived here; flagged in this stream's
#: report as needing a live check before this mapping is trusted.
EVENT_TYPE_TO_SIGNAL: Dict[str, str] = {
    "migrant_wave": "migrant_wave",
    "caravan_arrived": "caravan_present",
    "season_change": "season_change",
    "stock_below_threshold": "stock_below_target",
}

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


def _queue_summary_for(role: str, queue_state: Mapping[str, Any]) -> Mapping[str, Any]:
    """`queue.overview`'s own result carries BOTH halves of the queue
    (`proposals`, `asks`) in one read (fix 1, this module's own docstring
    above). A role's own briefing should still only see the half that is
    actually "pending for it": the Consultant never proposes, so what is
    pending for it is open asks, exactly the distinction `dfmcp/
    queue_tools.py`'s old per-caller-role `queue.pending` branch used to
    draw at the SERVER -- now drawn here instead, once, from one
    role-independent read."""
    key = "asks" if role == CONSULTANT else "proposals"
    return queue_state.get(key) or _EMPTY_QUEUE_SUB_SUMMARY


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
) -> RunResult:
    """`deps.role_runner.run`, bracketed by two `conductor.report` calls (start,
    end). The wake reason and its detail go out at launch; the outcome, cost,
    duration and final answer at the end. When the start call failed, the end
    call carries `role`, `wake_reason` and `cycle` too, so it is self-contained."""
    started = await _report(call, {
        "phase": "start", "role": role, "wake_reason": wake.reason,
        "wake_detail": wake.detail, "cycle": cycle_index,
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
    if run_id:
        end_args["run_id"] = run_id
    else:
        end_args.update({"role": role, "wake_reason": wake.reason, "wake_detail": wake.detail, "cycle": cycle_index})
    await _report(call, end_args)
    return run_result


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
    if tripwire is not None:
        wake = Wake(
            "tripwire", f"{tripwire.get('reason')}: {tripwire.get('detail')}", (OVERSEER,), PAUSED,
        )
        overseer_run: Optional[RunResult] = None
        escalated = False
        for other in ALL_ROLES:  # everyone but the woken Overseer consumes nothing this cycle
            if other != OVERSEER:
                _commit_cursor(deps, new_cursors, other)

        if not deps.dry_run:
            await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)

            briefing = build_briefing(
                role=OVERSEER, game_tick=game_tick or 0, wake=wake, vitals=vitals,
                diff_events=events_by_role.get(OVERSEER, []),
                queue_summary=_queue_summary_for(OVERSEER, queue_state),
            )
            overseer_run = await _run_role(
                deps, call, OVERSEER, json.dumps(briefing, default=str), wake=wake,
                cycle_index=cycle_index,
            )
            role_runs.append(overseer_run)
            if overseer_run.ok:
                _commit_cursor(deps, new_cursors, OVERSEER)  # a failed run keeps its events
            # Fix 3: two independent reasons the fort might stay paused, no
            # longer conflated into one proxy (see _overseer_called_escalate's
            # own docstring). "A failed or timed-out run still leaves the
            # fort paused" (unchanged from before); "a clean run with no
            # escalation [call] must no longer be treated as one" (the
            # actual behaviour change) -- and the new capability this fixes:
            # a CLEAN run that DID call queue.escalate now correctly stays
            # paused too, which the old proxy could never detect.
            called_escalate = _overseer_called_escalate(overseer_run)
            run_unclean = (not overseer_run.ok) or overseer_run.timed_out
            escalated = run_unclean or called_escalate

            if not escalated:
                if hold.held:
                    LOG.warning(
                        "cycle %s: tripwire handled by a clean Overseer run, but the fort is HELD by operator "
                        "(%s); clearing the latch and NOT resuming", cycle_index, hold.reason,
                    )
                await _call_write(call, "clock.clear", {}, clock_changes=clock_changes, cycle_index=cycle_index)
                # _call_write already logs any refusal (e.g. clock.resume
                # refused after clearing) at ERROR -- see its own docstring
                # and fix 2 in this module's report.
                if not hold.held:
                    await _call_write(call, "clock.resume", {}, clock_changes=clock_changes, cycle_index=cycle_index)
            elif called_escalate:
                LOG.error(
                    "ESCALATION: cycle %s's Overseer explicitly escalated via "
                    "queue.escalate; the fort stays PAUSED, tripwire=%s",
                    cycle_index, tripwire,
                )
            else:
                LOG.error(
                    "ESCALATION: cycle %s's Overseer run did not complete cleanly "
                    "(status=%s, ok=%s); the fort stays PAUSED, tripwire=%s",
                    cycle_index, overseer_run.status, overseer_run.ok, tripwire,
                )

        result = CycleResult(
            cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
            signals=Signals(),
            clock_level=PAUSED, roles_woken=(OVERSEER,), clock_changes=clock_changes,
            role_runs=role_runs, tripwire=tripwire, escalated=escalated, unexecuted=[],
            archived_path=None, dry_run=deps.dry_run,
            plan=(
                {"would_read": list(ALL_ROLES), "would_wake": [OVERSEER], "tripwire": tripwire}
                if deps.dry_run else None
            ),
        )
        if not deps.dry_run:
            result.archived_path = _archive(deps, cycle_index, result, briefings={OVERSEER: briefing})
        return result

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
        unexecuted = grade_result.get("unexecuted", []) or []
        # Over MCP, queue.grade returns only `unexecuted_proposal_ids` (the
        # local dfqueue call returns full `unexecuted` dicts). Read both.
        unexecuted_ids = list(grade_result.get("unexecuted_proposal_ids") or []) or [
            (u.get("proposal") or {}).get("id") for u in unexecuted if isinstance(u, dict)
        ]
        to_carry_out = [
            i for i in unexecuted_ids
            if isinstance(i, str) and i not in deps.policy.unexecuted_wake_ignore
        ]

    # ---- 3. TRIAGE ------------------------------------------------------------
    event_hits: Dict[str, bool] = {}
    for role in ALL_ROLES:
        event_hits.update(_classify_diff_events(events_by_role.get(role, [])))

    order_watch: OrderWatchResult = evaluate_orders(
        (orders_state.get("orders") or []),
        game_tick=game_tick,
        threshold_ticks=deps.policy.stalled_order_threshold_ticks,
        renotify_ticks=deps.policy.stalled_order_renotify_ticks,
        cursor_store=deps.cursor_store,
        dry_run=deps.dry_run,
    )
    job_watch = await _job_watch(deps, call, game_tick, cycle_index)
    slow_hit, slow_roles, slow_detail = _classify_slow_announcements(events_by_role)

    # Lane triggers (handoffs/2026-10-05-stricter-wakes.md): what changed in
    # each role's own lane. Alerts are read here, once, so a fresh crossing can
    # wake the role it belongs to; the briefings reuse the same lines.
    alerts, alert_crossed, alert_lines = await _read_alert_state(call, deps.policy, vitals, cycle_index)
    ore_read = await _ore_watch(deps, call, cycle_index)
    lane_store = _lane_store(deps)
    lane_state = lanes.LaneState()
    lane_wakes: Tuple[Any, ...] = ()
    pending_ids: List[str] = []
    if deps.policy.lane_triggers:
        try:
            lane_state = lane_store.load()
            pending_ids = list((queue_state.get("proposals") or {}).get("proposal_ids") or [])
            lanes.apply_alert_edges(deps.policy, lane_state, alert_crossed, alert_lines)
            lanes.apply_ore_edges(deps.policy, lane_state, ore_read, game_tick)
            lanes.apply_rulings(deps.policy, lane_state, pending_ids)
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

    signals = Signals(
        vital_nearing_threshold=_vital_nearing(vitals),
        vital_ticks_to_consequence=None,  # see module docstring: vitals.summary carries no timer
        stuck_job=event_hits.get("stuck_job", False) or job_watch.any_due,
        stuck_job_detail=job_watch.wake_detail(),
        stuck_job_roles=stuck_roles,
        stock_below_target=event_hits.get("stock_below_target", False),
        migrant_wave=event_hits.get("migrant_wave", False),
        caravan_present=event_hits.get("caravan_present", False),
        season_change=event_hits.get("season_change", False),
        hostile_seen_unreachable=False,  # gap 2, see module docstring (documented, not fixable here)
        stalled_order=bool(order_watch.stalled_ids),
        stalled_order_ids=order_watch.stalled_ids,
        blocked_order=bool(order_watch.blocked_ids),
        blocked_order_ids=order_watch.blocked_ids,
        slow_announcement=slow_hit,
        slow_announcement_roles=slow_roles,
        slow_announcement_detail=slow_detail,
        prediction_due=False,             # folded into prediction_graded, see module docstring
        prediction_graded=prediction_graded,
        prediction_misses=prediction_misses,
        lane_wakes=lane_wakes,
        game_days_since_routine_review=_game_days_since(deps.cursor_store, game_tick, deps.policy),
        queue_holds_for_overseer=bool((queue_state.get("proposals") or {}).get("count", 0)) or bool(to_carry_out),
        open_ask_for_consultant=bool((queue_state.get("asks") or {}).get("count", 0)),  # gap 1, fixed
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
            and next_role not in ADVISORS and any(r.role in ADVISORS for r in role_runs)
        ):
            queue_refreshed = True
            try:
                queue_state = await call("queue.overview", {})
            except MCPToolError as exc:
                LOG.error("cycle %s: queue re-read after the advisors failed: %s", cycle_index, exc)
            else:
                if (
                    bool((queue_state.get("asks") or {}).get("count", 0))
                    and CONSULTANT not in roles_to_run
                ):
                    extra_wakes[CONSULTANT] = Wake(
                        "open_ask", "an ask filed earlier this cycle is open for the Consultant",
                        (CONSULTANT,), FULL_SPEED,
                    )
                    # Inserted at idx: the Consultant runs before the Overseer
                    # (if any) and after every advisor.
                    roles_to_run.insert(idx, CONSULTANT)
                    roles_woken_out.append(CONSULTANT)

        if idx >= len(roles_to_run):
            break
        role = roles_to_run[idx]
        idx += 1

        wake = extra_wakes.get(role) or triage_result.wake_for(role)
        briefing = build_briefing(
            role=role, game_tick=game_tick or 0, wake=wake, vitals=vitals,
            diff_events=events_by_role.get(role, []),
            queue_summary=_queue_summary_for(role, queue_state),
            stuck_jobs=job_watch.lines, alerts=alerts,
            ore_exposed=_ore_lines_for(deps.policy, role, ore_read),
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
                stuck_jobs=job_watch.lines, to_carry_out=to_carry_out,
            )
            briefings[role] = {"ruling_prompt": prompt, "pending_brief": pending_brief}

        if deps.dry_run:
            continue

        if role == OVERSEER:
            # docs/AGENT-LOOP.md §1 step 6: "quicksave before the Overseer
            # runs whenever it may act."
            await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)

        run_result = await _run_role(
            deps, call, role, prompt, wake=wake, cycle_index=cycle_index,
        )
        role_runs.append(run_result)

        # Learn who proposed what: a pending proposal id that appeared during an
        # advisor's run is that advisor's (the conductor cannot read an author).
        # A completed run also serves whatever lane wakes were owed to the role.
        if deps.policy.lane_triggers and role in ADVISORS:
            try:
                after = await call("queue.overview", {})
                known_ids = lanes.attribute_new_proposals(
                    lane_state, role, known_ids, (after.get("proposals") or {}).get("proposal_ids") or [],
                )
            except Exception as exc:  # noqa: BLE001 -- total: attribution is best effort
                LOG.warning("cycle %s: proposer attribution after %s failed: %s", cycle_index, role, exc)
            if run_result.ok:
                lanes.clear_served(lane_state, role)
            try:
                lane_store.save(lane_state)
            except Exception:  # noqa: BLE001
                LOG.exception("cycle %s: could not save lane state", cycle_index)

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

    result = CycleResult(
        cycle_index=cycle_index, game_tick=game_tick, game_tick_error=game_tick_error,
        signals=signals,
        clock_level=(PAUSED if ordinary_escalated else triage_result.clock),
        roles_woken=tuple(roles_woken_out),
        clock_changes=clock_changes, role_runs=role_runs, tripwire=None,
        escalated=ordinary_escalated,
        unexecuted=unexecuted, archived_path=None, dry_run=deps.dry_run,
        pause_watch=pause_watch_dict,
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


async def _read_pending_brief(call: Callable, cycle_index: int) -> Optional[Dict[str, Any]]:
    """`queue.pending_brief` for the Overseer's ruling briefing; `None` if the
    read fails (the briefing then says so)."""
    try:
        result = await call("queue.pending_brief", {})
    except Exception as exc:  # noqa: BLE001 -- deliberately total
        LOG.error("cycle %s: queue.pending_brief failed: %s", cycle_index, exc)
        return None
    return result if isinstance(result, dict) else None


def _pause_store(deps: "CycleDeps") -> PauseWatchStore:
    return deps.pause_store or PauseWatchStore(deps.cursor_store.path.with_name("pause_watch.json"))


def _lane_store(deps: "CycleDeps") -> "lanes.LaneStore":
    return lanes.LaneStore(deps.cursor_store.path.with_name("lane_state.json"))


def _job_store(deps: "CycleDeps") -> JobWatchStore:
    return JobWatchStore(deps.cursor_store.path.with_name("job_watch.json"))


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


def _ore_lines_for(policy: Any, role: str, ore_read: Optional[OreRead]) -> Optional[List[str]]:
    """The standing exposure lines for a role whose lane has `ore`, else `None`
    (the briefing then has no `ore_exposed` key at all)."""
    lane = policy.lane_triggers.get(role)
    if ore_read is None or lane is None or not lane.ore:
        return None
    return ore_read.lines


async def _job_watch(deps: "CycleDeps", call: Callable, game_tick: Optional[int], cycle_index: int) -> JobWatchResult:
    """Poll `stuckjobs.find` (conductor/job_watch.py). Total by design, like the
    pause watchdog: an undeployed allowlist entry, a tool error or a corrupt
    state file logs loudly and the cycle carries on with no stuck-job signal."""
    try:
        found = await call("stuckjobs.find", {})
        return evaluate_jobs(
            jobs_from_result(found), game_tick=game_tick,
            unclaimed_threshold_ticks=deps.policy.stuck_job_unclaimed_threshold_ticks,
            suspended_threshold_ticks=deps.policy.stuck_job_suspended_threshold_ticks,
            renotify_ticks=deps.policy.stuck_job_renotify_ticks,
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
