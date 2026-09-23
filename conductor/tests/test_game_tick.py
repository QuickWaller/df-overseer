"""conductor/game_tick.py: the conductor's own vendored tick parser.
handoffs/2026-09-23-conductor-game-tick.md. `tests/test_game_tick_parity.py`
(top-level, not here) is what pins this module against `dfqueue/grade.py`'s
own copy -- these tests only check this module's own behaviour in
isolation, including that it never imports `dfqueue`."""

from __future__ import annotations

import inspect

import pytest

import conductor.game_tick as conductor_game_tick
from conductor.game_tick import GAME_TICKS_PER_YEAR, GameTickError, game_tick_from_overview
from tests.game_tick_fixtures import CASES, INVALID_OVERVIEW_CASES, overview_json


@pytest.mark.parametrize("date_string,expected_tick", CASES)
def test_game_tick_from_overview_parses_every_known_case(date_string, expected_tick):
    assert game_tick_from_overview(overview_json(date_string)) == expected_tick


@pytest.mark.parametrize("overview", INVALID_OVERVIEW_CASES)
def test_game_tick_from_overview_raises_on_malformed_input(overview):
    with pytest.raises(GameTickError):
        game_tick_from_overview(overview)


def test_ticks_per_year_matches_the_documented_calendar():
    # 1200 ticks/day * 28 days/month * 12 months/year.
    assert GAME_TICKS_PER_YEAR == 1200 * 28 * 12


def test_this_module_never_imports_dfqueue():
    """The whole point of vendoring this parser
    (handoffs/2026-09-23-conductor-game-tick.md): a `conductor/` module must
    never depend on `dfqueue`, which is not shipped alongside it in
    production -- the old `_game_tick` did import it, inside a bare
    `except Exception: return None`, which is how the tick came to be
    permanently null in production without anyone noticing. A static check
    on this module's own source, not a `sys.modules` check, because other
    test modules in the same pytest process legitimately import `dfqueue`
    themselves and would make a runtime check meaningless."""
    _assert_no_dfqueue_import(inspect.getsource(conductor_game_tick))


def test_cycle_module_never_imports_dfqueue_either():
    """`conductor/cycle.py`'s own `_game_tick` is the function this whole
    bug lived in -- same static-source check as the test above, on the
    actual caller, so a future edit that reintroduces
    `from dfqueue.grade import ...` inside `_game_tick` (or anywhere else in
    the module) fails a test immediately instead of only failing silently
    in production again."""
    import conductor.cycle as conductor_cycle

    _assert_no_dfqueue_import(inspect.getsource(conductor_cycle))


def _assert_no_dfqueue_import(source: str) -> None:
    """Checks for an actual import statement, not just the word "dfqueue"
    -- both modules' own docstrings legitimately discuss, in prose, the
    `dfqueue` import this stream removed and why, so a bare substring check
    on the whole source would false-positive on its own explanation."""
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("import dfqueue"), line
        assert not stripped.startswith("from dfqueue"), line
