"""The pause watchdog (`handoffs/2026-10-05-pause-safety.md`; register
2026-10-01, "No pause goes unowned; harmless self-pauses auto-resume").

A fort can stop without the tripwire knowing: a mega popup the game raises
(noble succession, 2026-09-28), a stuck screen (2026-09-16), a pause nobody
owns. This module is the conductor's answer, in two parts:

- `decide`: a PURE decision table. Observations in, one `Verdict` out. No
  I/O, no clock, no announcement name in code: the harmless list and every
  number live in `conductor/pause_policy.yaml`.
- `run_pause_watch`: the thin executor around it. Reads `pause.why`, calls
  `pause.dismiss`, `clock.resume` and `clock.pause` through the injected
  tool caller, and keeps a small state file (`PauseWatchStore`) so a pause
  that outlives a cycle, or a conductor restart, is still owned by someone.

## The hard lines (checked first, in this order, in `decide`)

1. A latched tripwire owns its pause. The watchdog never resumes it; the
   existing tripwire branch in `conductor/cycle.py` is the only path.
   `clock.resume` also refuses while a latch stands.
2. A pause owned by an Overseer escalation (`owned == "escalation"`) is not
   touched either, except that its age is counted for the liveness alert.
3. Dismissing a popup is not resuming. It closes a box a player could close.
   Resuming needs a cause on the harmless list, verified by the tick moving,
   once per pause episode.

Everything else is a hold: the fort stays paused, the Overseer is woken
(`unexplained_pause`) or the human is alerted. "Alert the human" is one
function (`_alert`) today a CRITICAL log line plus a record in the status
block; Telegram (register 2026-10-01) extends that one function.
"""

from __future__ import annotations

import enum
import json
import logging
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

import yaml

from conductor.mcp_client import MCPToolError

LOG = logging.getLogger("conductor.pause_watch")

DEFAULT_PAUSE_POLICY_PATH = Path(__file__).resolve().parent / "pause_policy.yaml"

WHY_TOOL_ID = "pause.why"
DISMISS_TOOL_ID = "pause.dismiss"

#: The wake reason this watchdog hands the cycle (conductor/policy.yaml).
UNEXPLAINED_PAUSE = "unexplained_pause"

OWNED_ESCALATION = "escalation"

_HISTORY_LIMIT = 20


class PausePolicyError(Exception):
    """`pause_policy.yaml` is missing or malformed. Never defaulted silently:
    a typo in the harmless list must not quietly widen what auto-resumes."""


@dataclass(frozen=True)
class PausePolicy:
    harmless_announcements: Tuple[str, ...]
    cause_window_ticks: int
    cause_slack_ticks: int
    dismiss_cap: int
    plain_pause_grace_seconds: float
    liveness_limit_seconds: float
    verify_wait_seconds: float
    verify_min_ticks: int
    frozen_after_seconds: float


def load_pause_policy(path: "Path | str" = DEFAULT_PAUSE_POLICY_PATH) -> PausePolicy:
    path = Path(path)
    if not path.is_file():
        raise PausePolicyError(f"{path}: no such pause policy file")
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}

    def need(key: str):
        if key not in doc:
            raise PausePolicyError(f"{path}: missing required key {key!r}")
        return doc[key]

    harmless = need("harmless_announcements")
    if not isinstance(harmless, list) or not all(isinstance(x, str) and x for x in harmless):
        raise PausePolicyError(f"{path}: harmless_announcements must be a list of announcement names")

    def number(key: str, *, minimum: float, integer: bool = False):
        value = need(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
            raise PausePolicyError(f"{path}: {key} must be a number >= {minimum}, got {value!r}")
        return int(value) if integer else float(value)

    return PausePolicy(
        harmless_announcements=tuple(harmless),
        cause_window_ticks=number("cause_window_ticks", minimum=1, integer=True),
        cause_slack_ticks=number("cause_slack_ticks", minimum=0, integer=True),
        dismiss_cap=number("dismiss_cap", minimum=1, integer=True),
        plain_pause_grace_seconds=number("plain_pause_grace_seconds", minimum=0),
        liveness_limit_seconds=number("liveness_limit_seconds", minimum=1),
        verify_wait_seconds=number("verify_wait_seconds", minimum=0),
        verify_min_ticks=number("verify_min_ticks", minimum=1, integer=True),
        frozen_after_seconds=number("frozen_after_seconds", minimum=1),
    )


# ---------------------------------------------------------------------------
# State: one small JSON file, atomic like conductor/cursors.py
# ---------------------------------------------------------------------------


@dataclass
class WatchState:
    episode_started: Optional[float] = None   # wall seconds, when this pause was first seen
    owned: Optional[str] = None               # "escalation" while an Overseer escalation holds it
    dismissed: int = 0                        # boxes closed this episode
    dismiss_failed: bool = False
    resume_attempts: int = 0                  # resume-and-verify tries this episode (max one)
    overseer_woken: bool = False
    last_alert: Optional[float] = None
    last_abs_tick: Optional[int] = None       # for the frozen-but-unpaused check
    last_tick_change: Optional[float] = None  # wall seconds when abs_tick last changed
    history: List[Dict[str, Any]] = field(default_factory=list)

    def end_episode(self) -> None:
        self.episode_started = None
        self.owned = None
        self.dismissed = 0
        self.dismiss_failed = False
        self.resume_attempts = 0
        self.overseer_woken = False
        self.last_alert = None

    def note(self, now: float, kind: str, detail: Any) -> None:
        self.history.append({"at": now, "kind": kind, "detail": detail})
        del self.history[:-_HISTORY_LIMIT]


class PauseWatchStore:
    """Single-writer, like `CursorStore`. A missing file is a fresh state; a
    corrupt one is an error rather than a silent reset (a reset could drop an
    escalation ownership and let the watchdog act over it)."""

    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> WatchState:
        if not self.path.is_file():
            return WatchState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PausePolicyError(f"{self.path}: not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise PausePolicyError(f"{self.path}: expected a JSON object")
        known = {k: v for k, v in raw.items() if k in WatchState.__dataclass_fields__}
        return WatchState(**known)

    def save(self, state: WatchState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(asdict(state), fh, indent=2, sort_keys=True)
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def mark_owned(self, kind: str, now: float) -> None:
        """The conductor's own pause (an Overseer escalation) is recorded so
        the watchdog never mistakes it for an unowned one."""
        state = self.load()
        if state.episode_started is None:
            state.episode_started = now
        state.owned = kind
        state.note(now, "owned", kind)
        self.save(state)


# ---------------------------------------------------------------------------
# The decision table (pure)
# ---------------------------------------------------------------------------


class Verdict(str, enum.Enum):
    IDLE = "idle"                      # not paused
    TRIPWIRE = "tripwire"              # a latch owns it; the tripwire branch decides
    OWNED = "owned"                    # an Overseer escalation owns it
    DISMISS = "dismiss"                # a popup is pending: close it
    ALERT = "alert"                    # not safe to touch, a human must look
    RESUME = "resume"                  # harmless cause: resume once, verify
    WAKE_OVERSEER = "wake_overseer"    # a threat, an unknown cause, or an unexplained pause
    WAIT = "wait"                      # a plain pause inside the grace period
    HELD = "held"                      # already handled this episode; stay paused


@dataclass(frozen=True)
class Observation:
    """What one `pause.why` read plus `clock.status` says. `report_types` are
    the announcement names of the recent DO_MEGA/PAUSE reports; `report_ticks`
    their ticks (aligned). `abs_tick` is the fort's tick now."""

    paused: bool
    tripwire: Optional[Mapping[str, Any]] = None
    cause: Optional[str] = None            # pause.why's own derived cause, None if unread
    popups_pending: int = 0
    viewscreen_type: Optional[str] = None
    report_types: Tuple[str, ...] = ()
    report_ticks: Tuple[Optional[int], ...] = ()
    abs_tick: Optional[int] = None


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str


def classify_causes(obs: Observation, policy: PausePolicy, *, popup_dismissed: bool) -> str:
    """`harmless`, `hold` or `none`, from the recent flagged reports.

    harmless: at least one report, every one named on the harmless list, and
    the pause plausibly began with it (a popup was dismissed this episode, or
    the newest report is within `cause_slack_ticks` of now). Anything else
    with a report is `hold`, including an unknown name. No report is `none`."""
    if not obs.report_types:
        return "none"
    if not all(t in policy.harmless_announcements for t in obs.report_types):
        return "hold"
    if popup_dismissed:
        return "harmless"
    ticks = [t for t in obs.report_ticks if t is not None]
    if obs.abs_tick is not None and ticks and (obs.abs_tick - max(ticks)) <= policy.cause_slack_ticks:
        return "harmless"
    return "hold"


def decide(obs: Observation, policy: PausePolicy, state: WatchState, now: float) -> Decision:
    if not obs.paused:
        return Decision(Verdict.IDLE, "not paused")
    if obs.tripwire:
        return Decision(Verdict.TRIPWIRE, "a tripwire is latched; the tripwire branch owns this pause")
    if state.owned == OWNED_ESCALATION:
        return Decision(Verdict.OWNED, "an Overseer escalation owns this pause")

    if obs.cause == "modal_viewscreen":
        return Decision(Verdict.ALERT, f"the game is on {obs.viewscreen_type}, not the play screen; a human must look")
    if obs.popups_pending > 0:
        if state.dismiss_failed or state.dismissed >= policy.dismiss_cap:
            return Decision(Verdict.ALERT, "a popup is pending and dismissing did not clear it")
        return Decision(Verdict.DISMISS, "a popup is pending; close it (dismiss never resumes)")

    if state.resume_attempts >= 1 or state.overseer_woken:
        return Decision(Verdict.HELD, "this episode was already handled once; staying paused")

    kind = classify_causes(obs, policy, popup_dismissed=state.dismissed > 0)
    if kind == "harmless":
        return Decision(Verdict.RESUME, "every recent cause is on the harmless list: resume once and verify")
    if kind == "hold":
        return Decision(Verdict.WAKE_OVERSEER, "a recent cause is a threat, unknown, or not tied to this pause")
    started = state.episode_started if state.episode_started is not None else now
    if now - started < policy.plain_pause_grace_seconds:
        return Decision(Verdict.WAIT, "a plain pause inside the grace period; a human may have paused it")
    return Decision(Verdict.WAKE_OVERSEER, "a plain pause nothing explains, past the grace period")


def liveness_due(state: WatchState, policy: PausePolicy, now: float) -> bool:
    if state.episode_started is None:
        return False
    if now - state.episode_started < policy.liveness_limit_seconds:
        return False
    return state.last_alert is None or (now - state.last_alert) >= policy.liveness_limit_seconds


# ---------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------


@dataclass
class WatchOutcome:
    verdict: Verdict
    reason: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    #: Set when the Overseer must be woken (the cycle runs it).
    wake_detail: Optional[str] = None
    why: Optional[Dict[str, Any]] = None
    #: True when the fort is still paused after this pass.
    still_paused: bool = False
    #: True once this pass resumed the fort and the tick advanced.
    resumed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value, "reason": self.reason,
            "actions": self.actions, "alerts": self.alerts,
            "still_paused": self.still_paused, "resumed": self.resumed,
            "cause": (self.why or {}).get("cause"),
        }


Sleep = Callable[[float], Awaitable[None]]


def _observation(status: Mapping[str, Any], why: Optional[Mapping[str, Any]]) -> Observation:
    why = why or {}
    reports = why.get("recent_reports") or []
    return Observation(
        paused=bool(status.get("paused")),
        tripwire=status.get("tripwire"),
        cause=why.get("cause"),
        popups_pending=int(why.get("popups_pending") or 0),
        viewscreen_type=why.get("viewscreen_type"),
        report_types=tuple(str(r.get("type")) for r in reports),
        report_ticks=tuple(r.get("tick") for r in reports),
        abs_tick=status.get("abs_tick"),
    )


def _alert(state: WatchState, outcome: WatchOutcome, now: float, reason: str) -> None:
    """The one human-alert sink. Telegram (register 2026-10-01) extends this."""
    LOG.critical("HUMAN ALERT: the fort is paused and the pause watchdog cannot clear it: %s", reason)
    alert = {"at": now, "reason": reason}
    outcome.alerts.append(alert)
    state.last_alert = now
    state.note(now, "alert", reason)


async def _read_why(call: Callable, window: int) -> Optional[Dict[str, Any]]:
    try:
        result = await call(WHY_TOOL_ID, {"window_ticks": window})
    except MCPToolError as exc:
        LOG.error("pause watchdog: %s failed (deployed yet?): %s", WHY_TOOL_ID, exc)
        return None
    return result if isinstance(result, dict) else None


async def _dismiss(call: Callable, cap: int, outcome: WatchOutcome, state: WatchState, now: float) -> None:
    try:
        result = await call(DISMISS_TOOL_ID, {"max": cap})
    except MCPToolError as exc:
        LOG.error("pause watchdog: %s failed: %s", DISMISS_TOOL_ID, exc)
        state.dismiss_failed = True
        outcome.actions.append({"tool": DISMISS_TOOL_ID, "error": str(exc)})
        return
    result = result if isinstance(result, dict) else {}
    closed = result.get("dismissed") or []
    state.dismissed += len(closed)
    if not result.get("ok", False) and int(result.get("remaining") or 0) > 0:
        state.dismiss_failed = True
    outcome.actions.append({
        "tool": DISMISS_TOOL_ID, "closed": len(closed), "remaining": result.get("remaining"),
        "said": [c.get("said") for c in closed],
    })
    for c in closed:
        state.note(now, "dismissed", {"kind": c.get("kind"), "said": c.get("said")})


async def resume_and_verify(
    call: Callable, policy: PausePolicy, sleep: Sleep, *, before_tick: Optional[int], outcome: WatchOutcome,
) -> bool:
    """`clock.resume`, wait, re-read: the tick must have moved. On a failure
    (refused, or the tick did not advance) pause again, the safe direction,
    and report False. One call per pause episode; the caller counts it."""
    try:
        res = await call("clock.resume", {})
    except MCPToolError as exc:
        outcome.actions.append({"tool": "clock.resume", "error": str(exc)})
        return False
    outcome.actions.append({"tool": "clock.resume", "result": res})
    if not (isinstance(res, dict) and res.get("ok", False)):
        return False
    await sleep(policy.verify_wait_seconds)
    try:
        after = await call("clock.status", {})
    except MCPToolError as exc:
        outcome.actions.append({"tool": "clock.status", "error": str(exc)})
        return False
    moved = (
        before_tick is not None and after.get("abs_tick") is not None
        and after["abs_tick"] - before_tick >= policy.verify_min_ticks and not after.get("paused")
    )
    outcome.actions.append({
        "tool": "clock.status", "verify": "tick advanced" if moved else "tick did NOT advance",
        "before": before_tick, "after": after.get("abs_tick"),
    })
    if not moved:
        try:
            await call("clock.pause", {})
            outcome.actions.append({"tool": "clock.pause", "why": "verify failed; back to the safe state"})
        except MCPToolError as exc:
            outcome.actions.append({"tool": "clock.pause", "error": str(exc)})
    return moved


async def run_pause_watch(
    call: Callable, store: PauseWatchStore, policy: PausePolicy, *,
    clock_status: Mapping[str, Any], now: float, sleep: Sleep, dry_run: bool = False,
) -> WatchOutcome:
    """One watchdog pass over this cycle's `clock.status`. Reads `pause.why`
    only when it is needed (a pause with no latch, or a frozen tick). A dry
    run reads and decides but writes nothing: no dismiss, no resume, no
    state."""
    state = store.load()
    paused = bool(clock_status.get("paused"))
    abs_tick = clock_status.get("abs_tick")
    outcome = WatchOutcome(Verdict.IDLE, "not paused")

    # Track whether the tick is moving, for the frozen-but-unpaused check.
    frozen = False
    if not paused:
        if state.last_abs_tick is not None and abs_tick is not None and abs_tick == state.last_abs_tick:
            frozen = (
                state.last_tick_change is not None
                and (now - state.last_tick_change) >= policy.frozen_after_seconds
            )
        else:
            state.last_tick_change = now
        state.last_abs_tick = abs_tick
    else:
        state.last_abs_tick = None
        state.last_tick_change = None

    if not paused:
        state.end_episode()
        if frozen:
            outcome = await _frozen_pass(call, policy, state, outcome, now, dry_run=dry_run)
        if not dry_run:
            store.save(state)
        return outcome

    if clock_status.get("tripwire"):
        # The tripwire branch owns it. Not an episode of ours.
        state.end_episode()
        if not dry_run:
            store.save(state)
        return WatchOutcome(Verdict.TRIPWIRE, "a tripwire is latched; the tripwire branch owns this pause", still_paused=True)

    if state.episode_started is None:
        state.episode_started = now
        state.note(now, "episode_started", None)

    why: Optional[Dict[str, Any]] = None
    if state.owned != OWNED_ESCALATION:
        why = await _read_why(call, policy.cause_window_ticks)
        outcome.why = why

    for _pass in range(3):
        obs = _observation(clock_status, why)
        decision = decide(obs, policy, state, now)
        outcome.verdict, outcome.reason = decision.verdict, decision.reason

        if decision.verdict is Verdict.DISMISS:
            if dry_run:
                break
            await _dismiss(call, policy.dismiss_cap, outcome, state, now)
            why = await _read_why(call, policy.cause_window_ticks)
            outcome.why = why
            continue
        break

    verdict = outcome.verdict
    if not dry_run:
        if verdict is Verdict.RESUME:
            state.resume_attempts += 1
            moved = await resume_and_verify(call, policy, sleep, before_tick=abs_tick, outcome=outcome)
            if moved:
                outcome.resumed = True
                state.note(now, "resumed", {"causes": [r for r in (why or {}).get("recent_reports", [])]})
                state.end_episode()
            else:
                _alert(state, outcome, now, "a harmless-cause resume did not move the tick; staying paused")
                outcome.verdict = Verdict.ALERT
        elif verdict is Verdict.ALERT:
            _alert(state, outcome, now, decision.reason)
        elif verdict is Verdict.WAKE_OVERSEER:
            state.overseer_woken = True
            seen = why or {}
            outcome.wake_detail = (
                f"{decision.reason}. cause={seen.get('cause')}, "
                f"recent={[r.get('type') for r in seen.get('recent_reports', [])]}, "
                f"dismissed_this_episode={state.dismissed}"
            )

        if not outcome.alerts and liveness_due(state, policy, now):
            _alert(state, outcome, now, "the pause has gone unresolved past the liveness limit")
        store.save(state)

    outcome.still_paused = not outcome.resumed
    return outcome


async def _frozen_pass(
    call: Callable, policy: PausePolicy, state: WatchState, outcome: WatchOutcome, now: float, *, dry_run: bool,
) -> WatchOutcome:
    """The tick has not moved for a while though the game is not paused."""
    why = await _read_why(call, policy.cause_window_ticks)
    outcome.why = why
    outcome.verdict = Verdict.ALERT
    outcome.reason = "the tick has stopped advancing though the fort is not paused"
    outcome.still_paused = True
    if dry_run:
        return outcome
    if why and int(why.get("popups_pending") or 0) > 0:
        await _dismiss(call, policy.dismiss_cap, outcome, state, now)
        outcome.reason = "frozen behind a popup; dismissed it"
        state.note(now, "frozen_dismissed", None)
        # Re-measure next cycle: forget the stall so a clear popup is not re-alerted.
        state.last_tick_change = now
        return outcome
    cause = (why or {}).get("cause", "unknown")
    _alert(state, outcome, now, f"the tick is not advancing and the fort is not paused (cause: {cause})")
    return outcome


async def finish_after_overseer(
    call: Callable, store: PauseWatchStore, policy: PausePolicy, *,
    escalated: bool, clock_status: Mapping[str, Any], now: float, sleep: Sleep,
) -> WatchOutcome:
    """After the Overseer ran on an `unexplained_pause` wake. Mirrors the
    tripwire branch: an escalation (or an unclean run, the caller folds that
    in) keeps the fort paused and owned by it, with a human alert; a clean
    un-escalated run is the decision to resume, once, verified."""
    state = store.load()
    outcome = WatchOutcome(Verdict.WAKE_OVERSEER, "the Overseer ran on an unexplained pause", still_paused=True)
    if escalated:
        state.owned = OWNED_ESCALATION
        state.note(now, "owned", OWNED_ESCALATION)
        _alert(state, outcome, now, "the Overseer escalated an unexplained pause")
        store.save(state)
        return outcome
    state.resume_attempts += 1
    moved = await resume_and_verify(
        call, policy, sleep, before_tick=clock_status.get("abs_tick"), outcome=outcome,
    )
    if moved:
        outcome.resumed = True
        outcome.still_paused = False
        state.note(now, "resumed_after_overseer", None)
        state.end_episode()
    else:
        _alert(state, outcome, now, "resuming after the Overseer's decision did not move the tick; staying paused")
        outcome.verdict = Verdict.ALERT
    store.save(state)
    return outcome
