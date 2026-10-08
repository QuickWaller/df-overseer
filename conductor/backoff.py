"""One renotify rule for every wake that can stand: exponential backoff counted
in WAKES, stalled after a few (research/2026-10-07-wake-audit.md rec 3).

The old rules renotified after a fixed number of game ticks. At 100 FPS one
game day (1200 ticks) is 12 real seconds, so a 1200-tick renotify fired every
conductor cycle and a 12000-tick one about every ten. This rule instead grows
the wait with each wake already sent (`base`, `2*base`, `4*base`, up to `cap`)
and stops altogether, "stalled", once `max_wakes` wakes have been sent: a
standing fact that three wakes did not resolve needs a human or a different
signal, not a fourth identical wake. The stalled fact is not forgotten, only
silenced; it clears with the fact itself, so a later recurrence wakes afresh.

A record is a plain dict, `{"first", "last", "wakes", "stalled"}` (ticks and
counts), so each watch keeps it wherever it already keeps its state. The one
function `advance` is the whole rule; the watches differ only in the base.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple


@dataclass(frozen=True)
class Backoff:
    """`base_ticks` is the wait before the SECOND wake; it doubles per wake
    up to `cap_ticks`. After `max_wakes` wakes the fact is stalled."""
    base_ticks: int
    cap_ticks: int = 100800
    max_wakes: int = 3


def wait_ticks(rule: Backoff, wakes: int) -> int:
    """Ticks to wait after `wakes` wakes have been sent before the next."""
    return min(rule.base_ticks * (2 ** max(wakes - 1, 0)), rule.cap_ticks)


def new_record(now: int) -> Dict[str, Any]:
    return {"first": now, "last": now, "wakes": 0, "stalled": False}


def advance(rec: Optional[Mapping[str, Any]], now: int, rule: Backoff) -> Tuple[Dict[str, Any], bool, bool]:
    """Fold one observation of a still-standing fact into its record.
    Returns `(record, due, newly_stalled)`: `due` means send a wake now (the
    record already counts it); `newly_stalled` means this wake was the last.

    No record, or a `last` in the future (the save was reloaded and the clock
    went backwards), starts the fact over with its first wake."""
    if rec is None or int(rec.get("last", 0)) > now:
        out = new_record(now)
        out["wakes"] = 1
        stalled = out["wakes"] >= rule.max_wakes
        out["stalled"] = stalled
        return out, True, stalled
    out = dict(rec)
    out.setdefault("first", now)
    out.setdefault("wakes", 0)
    if out.get("stalled"):
        return out, False, False
    if out["wakes"] <= 0:
        # Seen before it ever woke (e.g. a job counting its threshold): first wake.
        due = True
    else:
        due = (now - int(out["last"])) >= wait_ticks(rule, int(out["wakes"]))
    if not due:
        return out, False, False
    out["last"] = now
    out["wakes"] = int(out["wakes"]) + 1
    stalled = out["wakes"] >= rule.max_wakes
    out["stalled"] = stalled
    return out, True, stalled


class RetryClock:
    """A tick clock for the backoffs that also runs while the fort is paused.

    Every backoff above is counted in game ticks, and a paused fort never
    advances them, so a retry owed to a standing fact never came (live
    2026-10-08: the Planner's roadmap wake timed out with the fort paused and
    its next try was 12000 ticks away). `now()` returns the real tick plus an
    offset that grows by `retry_ticks` each time the real tick has stood still
    for `paused_seconds` of wall clock. It is monotone while the game runs
    (the offset only grows), so once the tick moves again nothing fires twice:
    stored `last`/`next_tick` values were written in the same clock. A tick
    that goes BACKWARDS (a reloaded save) resets the offset, which is exactly
    the case the backoffs already re-arm on.

    State lives in the cursor store under `__retry_*__` keys (integers). Only
    the backoffs may read this clock: ages, briefings and cursors use the real
    tick."""

    SEEN = "__retry_seen_tick__"
    WALL = "__retry_wall__"
    OFFSET = "__retry_offset__"

    def __init__(self, store: Any, paused_seconds: float, retry_ticks: int, wall: Any = None, persist: bool = True):
        import time
        self.store, self.paused_seconds, self.retry_ticks = store, float(paused_seconds), int(retry_ticks)
        self.wall = wall or time.time
        self.persist = persist

    def now(self, real_tick: Optional[int]) -> Optional[int]:
        if real_tick is None or self.paused_seconds <= 0 or self.store is None:
            return real_tick
        cur = self.store.load()
        seen, wall0, off = cur.get(self.SEEN), cur.get(self.WALL), int(cur.get(self.OFFSET, 0))
        now_wall = int(self.wall())
        if seen is None or wall0 is None:
            seen, wall0 = real_tick, now_wall
        elif real_tick < seen:
            seen, wall0, off = real_tick, now_wall, 0
        elif real_tick > seen:
            seen, wall0 = real_tick, now_wall
        elif now_wall - wall0 >= self.paused_seconds:
            off += self.retry_ticks
            wall0 = now_wall
        if self.persist:
            for key, val in ((self.SEEN, seen), (self.WALL, wall0), (self.OFFSET, off)):
                if cur.get(key) != val:
                    self.store.set(key, val)
        return real_tick + off
