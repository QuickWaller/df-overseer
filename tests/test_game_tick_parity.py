"""Pins `conductor/game_tick.py`'s vendored parser against `dfqueue/grade.py`'s
own `game_tick_from_overview` -- `handoffs/2026-09-23-conductor-game-tick.md`:
the conductor deliberately cannot import `dfqueue` (see `conductor/game_tick.py`'s
own docstring), so its copy of this parsing logic must be pinned equal by a
test instead of by a shared import. Every case in `tests/game_tick_fixtures.py`
must produce the exact same result from both modules; a change to either
parser's rule breaks this test unless the other one changes to match.

This is the ONLY place these two modules are compared against each other --
`conductor/tests/test_game_tick.py` and `dfqueue/tests/test_grade_cycle.py`
each test their own module in isolation and never import the other's.
"""

from __future__ import annotations

import pytest

from conductor import game_tick as conductor_game_tick
from dfqueue import grade as dfqueue_grade
from tests.game_tick_fixtures import CASES, INVALID_OVERVIEW_CASES, overview_json


def test_the_two_modules_agree_on_the_shared_ticks_per_year_constant():
    assert conductor_game_tick.GAME_TICKS_PER_YEAR == dfqueue_grade.GAME_TICKS_PER_YEAR


@pytest.mark.parametrize("date_string,expected_tick", CASES)
def test_both_parsers_agree_on_every_valid_case(date_string, expected_tick):
    overview = overview_json(date_string)
    conductor_result = conductor_game_tick.game_tick_from_overview(overview)
    dfqueue_result = dfqueue_grade.game_tick_from_overview(overview)
    assert conductor_result == expected_tick
    assert dfqueue_result == expected_tick
    assert conductor_result == dfqueue_result


@pytest.mark.parametrize("overview", INVALID_OVERVIEW_CASES)
def test_both_parsers_reject_the_same_malformed_shapes(overview):
    with pytest.raises(Exception):
        conductor_game_tick.game_tick_from_overview(overview)
    with pytest.raises(Exception):
        dfqueue_grade.game_tick_from_overview(overview)
