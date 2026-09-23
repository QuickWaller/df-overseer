"""The conductor's own game-tick parser.

`handoffs/2026-09-23-conductor-game-tick.md`: `conductor/cycle.py`'s
`_game_tick` used to import `dfqueue.grade.game_tick_from_overview` inside a
bare `try/except Exception: return None` -- `dfqueue` is not a dependency
`conductor/` ships (`conductor/requirements.txt`'s own header: "conductor/'s
own dependencies: a thin subset of dfmcp/requirements.txt" -- stdlib plus
`mcp` and `pyyaml` only), so that import has never once succeeded in
production and the `except` silently swallowed it every cycle, live-confirmed
on VM 106 2026-09-23 (`ModuleNotFoundError: No module named 'dfqueue'`,
`game_tick` recorded `null` in `status.json`). Both of the conductor's
time-based wake reasons depend on a real tick (`_game_days_since` in
`conductor/cycle.py`, and `conductor/order_watch.py`'s `evaluate_orders`),
so a null tick silently disabled both, permanently.

**Vendored here rather than factored into a shared module.** The parser is
one small, stable regex over a fixed string shape (`overview.get`'s
`tier2.in_game_date`) with no dependency of its own beyond the stdlib `re`
module -- pulling it into a genuinely shared module `dfqueue` and
`conductor` both import would still have to live somewhere with zero
transitive dependencies to keep `conductor/`'s own dependency line true, which
in practice means a third one-function package for one function. Vendoring
avoids that new package while still removing the broken import; the risk a
vendored copy usually carries (silent drift between the two copies) is
covered instead by `tests/test_game_tick_parity.py`, which runs the SAME
fixture cases (`tests/game_tick_fixtures.py`) through both this module's
`game_tick_from_overview` and `dfqueue.grade.game_tick_from_overview` and
fails if they ever disagree. `dfqueue/grade.py`'s own behaviour and constants
are untouched by this stream, per the handoff's scope line.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

#: DF's own fixed fortress-mode calendar: 1200 ticks/day, 28 days/month
#: (33,600 ticks/month), 12 months/year -> 403,200 ticks/year. Copied from
#: `dfqueue/grade.py`'s own `GAME_TICKS_PER_YEAR`, not re-derived --
#: `tests/test_game_tick_parity.py` pins the two constants equal so this
#: copy cannot silently drift from the source of the live-verified note
#: below.
#:
#: `dfhack.world.ReadCurrentTick()` -- the `T` in `overview.get`'s
#: `tier2.in_game_date` string -- counts ticks elapsed *within the current
#: in-game year*, not a running total. Verified live on VM 103 2026-09-15
#: (`dfqueue/grade.py`'s own docstring): `ReadCurrentTick()` and
#: `df.global.cur_year_tick` both read 178877 at year 30, while
#: `df.global.world.frame_counter` read 44275 -- so the backing value is
#: `cur_year_tick`, not `frame_counter`. Combining `year` and `tick` here
#: gives one absolute, monotonically-increasing counter, the same reason
#: `dfqueue/grade.py` combines them.
GAME_TICKS_PER_YEAR = 403200

_YEAR_RE = re.compile(r"year (-?\d+)")
_TICK_RE = re.compile(r"tick (-?\d+)")


class GameTickError(ValueError):
    """`overview.get`'s `tier2.in_game_date` is missing, malformed, or the
    `overview` payload itself is missing the `tier2` key. Raised, never
    swallowed, by `game_tick_from_overview` -- `conductor/cycle.py`'s own
    `_game_tick` wrapper is what decides how loud to be about it and what a
    cycle does next; this function's job is only to tell the truth about
    whether it could parse the string."""


def game_tick_from_overview(overview_json: Mapping[str, Any]) -> int:
    """An absolute, monotonically-increasing tick counter from
    `overview.get`'s `tier2.in_game_date` string (e.g. "year 30, month 6,
    day 10, tick 178877", from `df-overseer-overview.lua`).

    Same parsing logic as `dfqueue.grade.game_tick_from_overview`, kept
    independent per this module's own docstring above (no import between the
    two) and pinned equal by `tests/test_game_tick_parity.py`.

    Raises `GameTickError` (never returns `None` or a sentinel) if
    `tier2`/`in_game_date` is missing or does not match the expected shape,
    so a caller cannot mistake "could not parse" for "parsed to zero"."""
    try:
        date = overview_json["tier2"]["in_game_date"]
    except (KeyError, TypeError) as exc:
        raise GameTickError(
            f"overview.get result has no tier2.in_game_date: {exc}"
        ) from exc

    year_match = _YEAR_RE.search(date)
    tick_match = _TICK_RE.search(date)
    if not year_match or not tick_match:
        raise GameTickError(f"in_game_date does not match the expected shape: {date!r}")

    year, tick = int(year_match.group(1)), int(tick_match.group(1))
    return year * GAME_TICKS_PER_YEAR + tick
