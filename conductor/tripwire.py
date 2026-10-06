"""Stage T: the tripwire sequence's own state (handoffs/2026-10-06-stage-t-tripwire.md).

The in-game watcher (`scripts/dfhack/df-overseer-clock.lua`) has no
hysteresis: once the latch is cleared and the fort resumed, a dwarf still past
the thirst or hunger threshold re-latches on the very next check, with a new
latch tick. Nothing in the game stops the same cause cycling forever, so the
conductor counts it. A latch is one *episode*, identified by (reason, latch
tick); the conductor sees the same standing latch every cycle until it is
cleared, and must count it once.

Pure helpers plus one small JSON file beside the cursors, written atomically
like `conductor/cursors.py`. A missing file is empty; a corrupt one is an
error rather than a silent reset (a reset would let a runaway cause look new).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

_KEEP = 40


class TripwireStateError(Exception):
    pass


@dataclass
class TripwireState:
    #: Every latch the conductor has seen: {"reason", "tick"} newest last.
    episodes: List[Dict[str, Any]] = field(default_factory=list)
    #: The (reason, tick) of the latch already sent to the human for
    #: repeating, so a standing latch alerts without re-running the sequence.
    repeat_escalated: Optional[Dict[str, Any]] = None


class TripwireStore:
    def __init__(self, path: "Path | str"):
        self.path = Path(path)

    def load(self) -> TripwireState:
        if not self.path.is_file():
            return TripwireState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TripwireStateError(f"{self.path}: not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise TripwireStateError(f"{self.path}: expected a JSON object")
        eps = [e for e in (raw.get("episodes") or []) if isinstance(e, dict)]
        esc = raw.get("repeat_escalated")
        return TripwireState(episodes=eps, repeat_escalated=esc if isinstance(esc, dict) else None)

    def save(self, state: TripwireState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    {"episodes": state.episodes[-_KEEP:], "repeat_escalated": state.repeat_escalated},
                    fh, indent=2, sort_keys=True,
                )
            Path(tmp_name).replace(self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def _key(reason: Any, tick: Any) -> Tuple[str, Any]:
    return (str(reason), tick)


def note_latch(state: TripwireState, tripwire: Mapping[str, Any]) -> bool:
    """Record this latch as an episode; True when it is new (not the standing
    latch already counted on an earlier cycle)."""
    k = _key(tripwire.get("reason"), tripwire.get("tick"))
    if any(_key(e.get("reason"), e.get("tick")) == k for e in state.episodes):
        return False
    state.episodes.append({"reason": k[0], "tick": k[1]})
    del state.episodes[:-_KEEP]
    return True


def repeat_count(state: TripwireState, tripwire: Mapping[str, Any], window_ticks: int) -> int:
    """How many episodes of this latch's cause fall within `window_ticks` game
    ticks of it, itself included. A latch with an unreadable tick counts every
    episode of the cause with an unreadable tick (the safe, noisier side)."""
    reason = str(tripwire.get("reason"))
    tick = tripwire.get("tick")
    n = 0
    for e in state.episodes:
        if str(e.get("reason")) != reason:
            continue
        et = e.get("tick")
        if isinstance(tick, int) and isinstance(et, int):
            if abs(tick - et) <= window_ticks:
                n += 1
        elif not isinstance(tick, int) and not isinstance(et, int):
            n += 1
    return n


def owners_for(policy_owners: Mapping[str, Tuple[str, ...]], reason: Any) -> Tuple[str, ...]:
    """The roles that run before the Overseer for this cause (possibly none)."""
    return tuple(policy_owners.get(str(reason), ()))
