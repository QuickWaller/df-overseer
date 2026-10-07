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
