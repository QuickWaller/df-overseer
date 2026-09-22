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

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from conductor.archive import CycleArchive
from conductor.briefing import build_briefing
from conductor.cursors import CursorStore
from conductor.mcp_client import MCPToolError, ToolCaller, tool_name
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
    "job_stalled": "stuck_job",
    "stock_below_threshold": "stock_below_target",
}

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


@dataclass
class CycleResult:
    cycle_index: int
    game_tick: Optional[int]
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


def _vital_nearing(vitals: Mapping[str, Any]) -> bool:
    return (
        vitals.get("worst_hunger_status") in _NEARING_STATUSES
        or vitals.get("worst_thirst_status") in _NEARING_STATUSES
    )


async def _drain_all_cursors(
    call: Callable, cursor_store: CursorStore, *, dry_run: bool,
) -> Dict[str, List[dict]]:
    """One `diff.since` call per role in `ALL_ROLES`, each against that
    role's own persisted cursor (`docs/AGENT-ARCHITECTURE.md` §4: "each
    role keeps its own cursor"). The cursor is only ADVANCED
    (`cursor_store.set`) for a real cycle -- a dry run reads the same
    window it would for real but never moves anyone's cursor, so a
    following real cycle sees the same events a dry run already showed."""
    events_by_role: Dict[str, List[dict]] = {}
    for role in ALL_ROLES:
        cursor = cursor_store.get(role)
        drained = await call("diff.since", {"cursor": cursor})
        events = list(drained.get("events") or [])
        events_by_role[role] = events
        if not dry_run:
            new_cursor = drained.get("cursor")
            if new_cursor is not None:
                cursor_store.set(role, int(new_cursor))
    return events_by_role


def _game_tick(overview: Mapping[str, Any]) -> Optional[int]:
    """Best-effort: `dfqueue.grade.game_tick_from_overview` is the real,
    tested parser for this, but importing `dfqueue` here would pull a
    fort-side package into a service that otherwise depends on nothing but
    this repo's own `conductor/` and `mcp`/`yaml` -- kept as a soft,
    non-fatal read instead (a cycle that cannot parse the tick still runs;
    it just archives `game_tick: None` rather than refusing outright)."""
    try:
        from dfqueue.grade import game_tick_from_overview
        return game_tick_from_overview(overview)
    except Exception:
        return None


async def run_cycle(cycle_index: int, deps: CycleDeps) -> CycleResult:
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
        events_by_role = await _drain_all_cursors(call, deps.cursor_store, dry_run=deps.dry_run)
    except MCPToolError as exc:
        raise CycleError(f"cycle {cycle_index}: could not complete this cycle's read: {exc}") from exc

    game_tick = _game_tick(overview)
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

        if not deps.dry_run:
            await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)

            briefing = build_briefing(
                role=OVERSEER, game_tick=game_tick or 0, wake=wake, vitals=vitals,
                diff_events=events_by_role.get(OVERSEER, []),
                queue_summary=_queue_summary_for(OVERSEER, queue_state),
            )
            overseer_run = await deps.role_runner.run(
                OVERSEER, json.dumps(briefing, default=str), model=deps.models[OVERSEER],
                timeout_seconds=deps.role_timeout_seconds, charter=deps.charters.get(OVERSEER),
            )
            role_runs.append(overseer_run)
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
                await _call_write(call, "clock.clear", {}, clock_changes=clock_changes, cycle_index=cycle_index)
                # _call_write already logs any refusal (e.g. clock.resume
                # refused after clearing) at ERROR -- see its own docstring
                # and fix 2 in this module's report.
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
            cycle_index=cycle_index, game_tick=game_tick, signals=Signals(),
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

    # ---- 2. GRADE -----------------------------------------------------------
    prediction_graded = False
    unexecuted: List[dict] = []
    if not deps.dry_run:
        try:
            grade_result = await call("queue.grade", {})
        except MCPToolError as exc:
            raise CycleError(f"cycle {cycle_index}: grading failed: {exc}") from exc
        prediction_graded = grade_result.get("graded_count", 0) > 0
        unexecuted = grade_result.get("unexecuted", []) or []

    # ---- 3. TRIAGE ------------------------------------------------------------
    event_hits: Dict[str, bool] = {}
    for role in ALL_ROLES:
        event_hits.update(_classify_diff_events(events_by_role.get(role, [])))

    signals = Signals(
        vital_nearing_threshold=_vital_nearing(vitals),
        vital_ticks_to_consequence=None,  # see module docstring: vitals.summary carries no timer
        stuck_job=event_hits.get("stuck_job", False),
        stock_below_target=event_hits.get("stock_below_target", False),
        migrant_wave=event_hits.get("migrant_wave", False),
        caravan_present=event_hits.get("caravan_present", False),
        season_change=event_hits.get("season_change", False),
        hostile_seen_unreachable=False,  # gap 2, see module docstring (documented, not fixable here)
        prediction_due=False,             # folded into prediction_graded, see module docstring
        prediction_graded=prediction_graded,
        game_days_since_routine_review=_game_days_since(deps.cursor_store, game_tick, deps.policy),
        queue_holds_for_overseer=bool((queue_state.get("proposals") or {}).get("count", 0)),
        open_ask_for_consultant=bool((queue_state.get("asks") or {}).get("count", 0)),  # gap 1, fixed
    )
    triage_result = triage(signals, deps.policy, base_fps=clock_status.get("fps"))

    # The routine-review cursor advances whenever that reason actually
    # fires this cycle (never on a dry run) -- self-contained here rather
    # than pushed onto conductor/service.py, so _game_days_since's own
    # state stays entirely owned by this module.
    if not deps.dry_run and game_tick is not None:
        if any(w.reason == "routine_review" for w in triage_result.wakes):
            deps.cursor_store.set("__routine_review__", game_tick)

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
    for role in triage_result.roles_to_wake:
        wake = triage_result.wake_for(role)
        briefing = build_briefing(
            role=role, game_tick=game_tick or 0, wake=wake, vitals=vitals,
            diff_events=events_by_role.get(role, []),
            queue_summary=_queue_summary_for(role, queue_state),
        )
        briefings[role] = briefing

        if deps.dry_run:
            continue

        if role == OVERSEER:
            # docs/AGENT-LOOP.md §1 step 6: "quicksave before the Overseer
            # runs whenever it may act."
            await _call_write(call, "fort.quicksave", {}, clock_changes=clock_changes, cycle_index=cycle_index)

        run_result = await deps.role_runner.run(
            role, json.dumps(briefing, default=str), model=deps.models[role],
            timeout_seconds=deps.role_timeout_seconds, charter=deps.charters.get(role),
        )
        role_runs.append(run_result)

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
            LOG.error(
                "ESCALATION: cycle %s's Overseer explicitly escalated via queue.escalate "
                "during an ordinary cycle; the fort is now PAUSED.",
                cycle_index,
            )

    result = CycleResult(
        cycle_index=cycle_index, game_tick=game_tick, signals=signals,
        clock_level=(PAUSED if ordinary_escalated else triage_result.clock),
        roles_woken=triage_result.roles_to_wake,
        clock_changes=clock_changes, role_runs=role_runs, tripwire=None,
        escalated=ordinary_escalated,
        unexecuted=unexecuted, archived_path=None, dry_run=deps.dry_run,
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
        "clock_level": result.clock_level,
        "roles_woken": list(result.roles_woken),
        "tripwire": result.tripwire,
        "escalated": result.escalated,
        "unexecuted_proposal_ids": [u.get("proposal", {}).get("id") for u in result.unexecuted],
    }
    role_run_dicts = [
        {
            "role": r.role, "ok": r.ok, "status": r.status, "cost_usd": r.cost_usd,
            "wall_clock_seconds": r.wall_clock_seconds, "timed_out": r.timed_out,
            "tool_summary": r.tool_summary, "final_answer": r.final_answer, "error": r.error,
        }
        for r in result.role_runs
    ]
    for r in result.role_runs:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        deps.archive.append_daily_cost(today, r.cost_usd)
        LOG.info(
            "cycle %s: role=%s cost_usd=%.6f wall_clock_seconds=%.1f",
            cycle_index, r.role, r.cost_usd, r.wall_clock_seconds,
        )
    return deps.archive.write_cycle(
        cycle_index, summary=summary, briefings=briefings,
        clock_changes=result.clock_changes, role_runs=role_run_dicts,
    )
