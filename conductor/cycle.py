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

## Two known, load-bearing gaps found while building this, not fixed here

1. **`queue.pending`'s role branch is keyed to the CALLER's own
   authenticated identity, not an argument** (`dfmcp/queue_tools.py`'s
   `_pending`: `if role == "consultant": ... else: pending_proposals`).
   The conductor calls it as `conductor`, never `consultant`, so it can
   only ever see `pending_proposals()` -- there is no way, from the
   conductor's own token, to ask "is there an open ask for the
   Consultant?" `open_ask_for_consultant` is therefore always `False` in
   this build. Fixing it needs a new native tool or a role-override
   argument restricted to the conductor, which is outside this stream's
   touched-surfaces grant for `dfmcp/queue_tools.py` (scoped to the grading
   tool only). Flagged loudly in this stream's report, not silently
   worked around.
2. **The conductor holds no reachability read** (`threat.scan` is
   advisor/overseer-only, per `agents/*/tools.yaml`), so
   `hostile_seen_unreachable` cannot be computed from the conductor's own
   allowed reads. It stays `False` always; whatever `diff.since` drains
   may or may not even carry a distinguishable event for this
   (`docs/AGENT-ARCHITECTURE.md` §4's own finding: `hostile_detected` is
   "dangerously narrow" and reachability is not itself a Report field).
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
from conductor.mcp_client import MCPToolError, ToolCaller
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


def _overseer_escalated(run_result: RunResult) -> bool:
    """No established, tested contract exists yet for how the Overseer's
    run signals "I am escalating to the human" inside openclaw's own JSON
    envelope (`agents/overseer/role.md`, which would need to define this,
    is not in this stream's touched surfaces). Conservative interpretation,
    documented rather than silently assumed: a run that did not complete
    cleanly (`ok` is False, or it timed out) is treated as equivalent to an
    escalation for "never resume past a live latch if it escalated" -- the
    fort stays paused rather than auto-resuming after an unclear outcome.
    A clean run is additionally checked for an explicit `escalated: true`
    key in its own raw envelope, in case a future Overseer charter starts
    setting one; absent that key, a clean run is NOT an escalation.
    """
    if not run_result.ok or run_result.timed_out:
        return True
    return bool(run_result.raw.get("escalated"))


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
        queue_state = await call("queue.pending", {})  # see module docstring, gap 1
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
        arm_result = await call("clock.arm", {})
        clock_changes.append({"tool": "clock.arm", "args": {}, "result": arm_result})

    # ---- Tripwire: paused, independent of ordinary triage ------------------
    if tripwire is not None:
        wake = Wake(
            "tripwire", f"{tripwire.get('reason')}: {tripwire.get('detail')}", (OVERSEER,), PAUSED,
        )
        overseer_run: Optional[RunResult] = None
        escalated = False

        if not deps.dry_run:
            qs = await call("fort.quicksave", {})
            clock_changes.append({"tool": "fort.quicksave", "args": {}, "result": qs})

            briefing = build_briefing(
                role=OVERSEER, game_tick=game_tick or 0, wake=wake, vitals=vitals,
                diff_events=events_by_role.get(OVERSEER, []), queue_summary=queue_state,
            )
            overseer_run = await deps.role_runner.run(
                OVERSEER, json.dumps(briefing, default=str), model=deps.models[OVERSEER],
                timeout_seconds=deps.role_timeout_seconds, charter=deps.charters.get(OVERSEER),
            )
            role_runs.append(overseer_run)
            escalated = _overseer_escalated(overseer_run)

            if not escalated:
                clear_result = await call("clock.clear", {})
                clock_changes.append({"tool": "clock.clear", "args": {}, "result": clear_result})
                resume_result = await call("clock.resume", {})
                clock_changes.append({"tool": "clock.resume", "args": {}, "result": resume_result})
                if not resume_result.get("ok", False):
                    # clock.resume's own refusal shape ({"ok": False,
                    # "error": ..., "tripwire": ...}) does not surface as an
                    # MCP isError (see this module's docstring / this
                    # stream's report), so this must be checked explicitly.
                    LOG.error(
                        "cycle %s: clock.resume refused after clearing the tripwire: %s",
                        cycle_index, resume_result.get("error"),
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
        hostile_seen_unreachable=False,  # gap 2, see module docstring
        prediction_due=False,             # folded into prediction_graded, see module docstring
        prediction_graded=prediction_graded,
        game_days_since_routine_review=_game_days_since(deps.cursor_store, game_tick, deps.policy),
        queue_holds_for_overseer=bool(queue_state.get("count", 0)),
        open_ask_for_consultant=False,    # gap 1, see module docstring
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
        set_result = await call("clock.set-speed", {"fps": target_fps})
        clock_changes.append({
            "tool": "clock.set-speed", "args": {"fps": target_fps}, "result": set_result,
        })

    # ---- 4/5. Advise, then decide-and-act, in the fixed roster order ---------
    briefings: Dict[str, dict] = {}
    for role in triage_result.roles_to_wake:
        wake = triage_result.wake_for(role)
        briefing = build_briefing(
            role=role, game_tick=game_tick or 0, wake=wake, vitals=vitals,
            diff_events=events_by_role.get(role, []), queue_summary=queue_state,
        )
        briefings[role] = briefing

        if deps.dry_run:
            continue

        if role == OVERSEER:
            # docs/AGENT-LOOP.md §1 step 6: "quicksave before the Overseer
            # runs whenever it may act."
            qs = await call("fort.quicksave", {})
            clock_changes.append({"tool": "fort.quicksave", "args": {}, "result": qs})

        run_result = await deps.role_runner.run(
            role, json.dumps(briefing, default=str), model=deps.models[role],
            timeout_seconds=deps.role_timeout_seconds, charter=deps.charters.get(role),
        )
        role_runs.append(run_result)

    result = CycleResult(
        cycle_index=cycle_index, game_tick=game_tick, signals=signals,
        clock_level=triage_result.clock, roles_woken=triage_result.roles_to_wake,
        clock_changes=clock_changes, role_runs=role_runs, tripwire=None, escalated=False,
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
