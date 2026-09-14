"""Mechanical grading of due live-signal predictions.

Same discipline as `learning/predictions/grade.py`, and reuses its exact
predicate logic (`apply_predicate`, the public alias for that module's
`_apply`) rather than a second copy of it: nothing here ever reads a
record's `summary`/`rationale` prose, only `prediction.signal`,
`prediction.op` and `prediction.value` (as stored in `dfqueue.store`'s
`predictions` table) against a **live** value read through
`learning.live_signals`, never the fort ledger.
"""

from __future__ import annotations

import re
from typing import Callable

from learning import live_signals
from learning.predictions.grade import apply_predicate
from learning.predictions.schema import (
    EXISTS, GRADED_FALSE, GRADED_TRUE, PRESENCE_OPS, UNRESOLVABLE,
)

from . import store

#: DF's own fixed fortress-mode calendar: 1200 ticks/day, 28 days/month
#: (33,600 ticks/month), 12 months/year -> 403,200 ticks/year. A hardcoded
#: game constant, not something this repo measured or configured. Source:
#: the Dwarf Fortress Wiki's "Time" article
#: (https://dwarffortresswiki.org/index.php/DF2014:Time, "1 day = 1200
#: ticks", "1 year = 403200 ticks"), checked this session via WebFetch —
#: not independently re-derived against a live VM (no VM access in this
#: stream; see the handoff report).
GAME_TICKS_PER_YEAR = 403200

_YEAR_RE = re.compile(r"year (-?\d+)")
_TICK_RE = re.compile(r"tick (-?\d+)")


def game_tick_from_overview(overview_json: dict) -> int:
    """An absolute, monotonically-increasing tick counter from
    `overview.get`'s `tier2.in_game_date` string (e.g. "year 30, month 6,
    day 10, tick 178877", from `df-overseer-overview.lua`).

    `dfhack.world.ReadCurrentTick()` — the `T` in that string — counts ticks
    elapsed *within the current in-game year*, not a running total.
    Verified live on VM 103 2026-09-15: `ReadCurrentTick()` and
    `df.global.cur_year_tick` both read 178877 at year 30, while
    `df.global.world.frame_counter` read 44275, so the backing value is
    `cur_year_tick`, not `frame_counter` (an earlier note here cited the
    DFHack Lua API docs as saying `frame_counter`; the live reading is what
    counts). So the
    string alone is not monotonic turn to turn (`tick` resets every year);
    this function combines it with `year` to get one absolute counter that
    is, which `dfqueue.store`'s `due_game_tick` column needs to compare
    against turn to turn.
    """
    date = overview_json["tier2"]["in_game_date"]
    year_match = _YEAR_RE.search(date)
    tick_match = _TICK_RE.search(date)
    if not year_match or not tick_match:
        raise ValueError(f"in_game_date does not match the expected shape: {date!r}")
    year, tick = int(year_match.group(1)), int(tick_match.group(1))
    return year * GAME_TICKS_PER_YEAR + tick


CallTool = Callable[[str, dict], object]


def grade_due(
    db, current_game_tick: int, call_tool: CallTool, graded_at: str,
) -> list[dict]:
    """Grade every pending prediction in `db` whose `due_game_tick` has
    arrived (`<= current_game_tick`). For each: reads the signal through
    `learning.live_signals`, applies the shared predicate logic, and writes
    `status`/`actual_value`/`graded_at`/`grade_note` for the whole batch in
    one transaction (`store.apply_grades`). Returns the updates applied
    (possibly empty).

    Idempotent by construction: `store.pending_due` only ever returns rows
    still `status = "pending"`, so a prediction graded on one call is never
    re-read or re-written by a later one.
    """
    due = store.pending_due(db, current_game_tick)
    updates: list[dict] = []

    for row in due:
        try:
            parsed = live_signals.parse(row["signal"])
            actual = live_signals.read(parsed, call_tool)
        except live_signals.SignalError as exc:
            updates.append({
                "id": row["id"], "status": UNRESOLVABLE, "actual_value": None,
                "graded_at": graded_at, "grade_note": f"signal no longer parses: {exc}",
            })
            continue

        if actual is live_signals.UNRESOLVABLE:
            updates.append({
                "id": row["id"], "status": UNRESOLVABLE, "actual_value": None,
                "graded_at": graded_at,
                "grade_note": "signal not (yet) resolvable: the landmark or exit it "
                               "names does not exist",
            })
            continue

        op = row["op"]
        if op in PRESENCE_OPS:
            # `actual` is already a real, resolved value (the branch above
            # would have caught UNRESOLVABLE), so a presence op reduces to
            # "did the signal resolve at all" -- exists=true, not_exists=false.
            status = GRADED_TRUE if op == EXISTS else GRADED_FALSE
        else:
            ok = apply_predicate(op, actual, row["value"])
            status = GRADED_TRUE if ok else GRADED_FALSE

        updates.append({
            "id": row["id"], "status": status, "actual_value": actual,
            "graded_at": graded_at, "grade_note": "",
        })

    store.apply_grades(db, updates)
    return updates
