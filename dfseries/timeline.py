"""Rollback detection and lineage computation, per `docs/TIMESERIES.md`
"Timelines".

**Why wall-clock order, not tick order.** A rollback is defined by tick
order breaking: timeline B can start at a tick earlier than timeline A's
latest sample. So tick values cannot be used to decide which timeline came
second in the real world -- only `wall_utc`, the sampler's own clock, can.
`docs/TIMESERIES.md`'s record format carries `wall_utc` for exactly this
reason.

**The chain rule.** Order every known timeline by its earliest `wall_utc`
(oldest first). Each timeline's cutoff is its *immediate* successor's
`start_abs_tick` -- not the newest timeline's, and not any later timeline's.
This matches the contract's own wording: "for each predecessor, only its
samples at or before the tick where its successor began" (singular
successor). A predecessor which is itself later superseded by a *third*
timeline does not retroactively change an earlier predecessor's cutoff --
the earlier predecessor was already superseded by its own immediate
successor, and nothing that happens afterwards un-supersedes it.

If two timelines were never told apart by wall clock (missing or identical
`wall_utc`), the tiebreak is insertion order (`rowid`): the order in which
this database first saw each timeline. Callers that import files must do so
in real-world order for correct lineage when `wall_utc` is absent -- with
`wall_utc` present (the normal case; the contract always includes it), this
never matters.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from . import store


def _parse_wall_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recompute_lineage(conn: sqlite3.Connection) -> None:
    """Recompute every timeline's `cutoff_abs_tick` and every sample event's
    `superseded` flag from scratch. Called after any import that may have
    added a new timeline or new samples to an existing one. Idempotent and
    cheap at this project's sample volume (one event per game day) -- a full
    recompute is simpler to get right than incremental patching and does not
    depend on the order timelines were discovered in."""
    rows = conn.execute("SELECT rowid AS _rowid, * FROM timelines").fetchall()
    if not rows:
        return

    def sort_key(row: sqlite3.Row):
        wall = _parse_wall_utc(row["first_wall_utc"])
        # (has_no_wall_utc, wall_or_epoch, rowid): timelines with a real
        # wall_utc always sort before ones without, then by wall_utc, then
        # by insertion order as the last-resort tiebreak.
        return (wall is None, wall or datetime.min, row["_rowid"])

    ordered = sorted(rows, key=sort_key)

    for i, row in enumerate(ordered):
        if i == len(ordered) - 1:
            cutoff = None  # newest timeline in the chain: nothing supersedes it
        else:
            cutoff = ordered[i + 1]["start_abs_tick"]
        store.set_cutoff(conn, row["id"], cutoff)

    store.recompute_superseded(conn)


def lineage_summary(conn: sqlite3.Connection) -> list[dict]:
    """One row per timeline, oldest first, with its computed cutoff -- for
    the CLI and for tests that want to see the chain without reasoning
    through raw SQL."""
    rows = conn.execute("SELECT rowid AS _rowid, * FROM timelines").fetchall()

    def sort_key(row: sqlite3.Row):
        wall = _parse_wall_utc(row["first_wall_utc"])
        return (wall is None, wall or datetime.min, row["_rowid"])

    ordered = sorted(rows, key=sort_key)
    return [
        {
            "timeline_id": r["id"],
            "start_abs_tick": r["start_abs_tick"],
            "first_wall_utc": r["first_wall_utc"],
            "cutoff_abs_tick": r["cutoff_abs_tick"],
            "is_current_tip": r["cutoff_abs_tick"] is None,
        }
        for r in ordered
    ]
