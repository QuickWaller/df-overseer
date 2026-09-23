"""Shared game-tick parsing fixtures, read by both `conductor/game_tick.py`'s
own tests and `dfqueue/grade.py`'s. `handoffs/2026-09-23-conductor-game-tick.md`:
`conductor/game_tick.py` is a vendored copy of `dfqueue.grade.game_tick_from_
overview`'s parsing logic (the conductor deliberately does not depend on
`dfqueue` -- see that module's own docstring for why), so the two must never
be free to silently drift apart. `tests/test_game_tick_parity.py` runs both
parsers over every case below and asserts equal results; a change to either
copy's parsing rule breaks that test unless the other copy changes to match.

Each case: `(in_game_date_string, expected_absolute_tick)`. `expected_
absolute_tick` follows `year * 403200 + tick`, the same formula both
implementations use (`GAME_TICKS_PER_YEAR`, pinned equal between the two
modules by `tests/test_game_tick_parity.py` itself).
"""

from __future__ import annotations

from typing import List, Tuple

GAME_TICKS_PER_YEAR = 403200

CASES: List[Tuple[str, int]] = [
    # The live string this bug was found against, 2026-09-23
    # (handoffs/2026-09-23-conductor-game-tick.md): "year 31, month 4, day
    # 10, tick 112357".
    ("year 31, month 4, day 10, tick 112357", 31 * GAME_TICKS_PER_YEAR + 112357),
    # dfqueue/grade.py's own live-verified case, 2026-09-15: year 30, tick
    # 178877 (cur_year_tick, not frame_counter -- see that module's
    # docstring).
    ("year 30, month 6, day 10, tick 178877", 30 * GAME_TICKS_PER_YEAR + 178877),
    # Year 1, the fort's very first tick.
    ("year 1, month 1, day 1, tick 0", 1 * GAME_TICKS_PER_YEAR + 0),
    # A tick right at the top of a game-year, just before it would roll to
    # year+1/tick 0 -- exercises that year and tick are combined, not tick
    # alone (tick alone is not monotonic across a year boundary).
    ("year 5, month 12, day 28, tick 403199", 5 * GAME_TICKS_PER_YEAR + 403199),
]

#: Malformed/missing shapes both parsers must reject rather than guess at.
#: Each entry is an `overview_json`-shaped mapping (or fragment) that should
#: raise, not return a value.
INVALID_OVERVIEW_CASES: List[dict] = [
    {},  # no tier2 at all
    {"tier2": {}},  # no in_game_date
    {"tier2": {"in_game_date": "not a date string"}},
    {"tier2": {"in_game_date": "year 31, month 4, day 10"}},  # no tick
]


def overview_json(date_string: str) -> dict:
    """Wrap a raw `in_game_date` string in the `overview.get` shape both
    parsers actually read (`{"tier2": {"in_game_date": ...}}`)."""
    return {"tier2": {"in_game_date": date_string}}
