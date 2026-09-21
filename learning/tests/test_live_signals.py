"""`learning.live_signals`: parsing, quoting, and reading against fake tool
JSON copied from real output shapes (`scripts/dfhack/df-overseer-overview.lua`,
`df-overseer-landmarks.lua`, `df-overseer-stuckjobs.lua`), never invented --
this repo has already been bitten once by a fake-server payload that shaped
differently from reality (dfmcp's live smoke test, 2026-09-14, `handoffs/
2026-09-14-mcp-live-smoke-test.md`).
"""

from __future__ import annotations

import pytest

from learning.live_signals import (
    BOOLEAN, FORT_ALERTS_COUNT, FORT_LANDMARKS_COUNT, FORT_POPULATION,
    FORT_STUCK_JOBS_COUNT, INTEGER, LANDMARK_EXISTS, LANDMARK_EXIT_DISTANCE,
    ORDER_EXISTS, STOCKS_AVAILABILITY_UNITS, STOCKS_DRINK_UNITS,
    STOCKS_PREPARED_MEALS_UNITS, STOCKS_RAW_EDIBLES_UNITS, STOCKS_SEEDS_UNITS,
    SignalError, UNRESOLVABLE, parse, quote_landmark_name, read,
)

# ---- fixtures: real output shapes, not invented --------------------------------

# df-overseer-overview.lua's get_overview(): tier0/tier1/tier2, population
# under tier1, alerts under tier2. Values match the real survey in
# evals/live/2026-09-14-architect-first-charter/run.json ("Uniboslan, year
# 30, month 6, day 10 (tick 178877)... Population 15, no alerts").
OVERVIEW_JSON = {
    "tier0": {"fortress": "Uniboslan"},
    "tier1": {"population": 15, "landmarks": []},
    "tier2": {
        "in_game_date": "year 30, month 6, day 10, tick 178877",
        "main_group_id": 11,
        "alerts": [],
    },
}

OVERVIEW_WITH_ALERTS_JSON = {
    "tier0": {"fortress": "Uniboslan"},
    "tier1": {"population": 15, "landmarks": []},
    "tier2": {
        "in_game_date": "year 30, month 6, day 10, tick 178877",
        "main_group_id": 11,
        "alerts": [
            "1 citizen stranded (group 4): Urist McMiner, near Embark Site (SE, 6 tiles)",
        ],
    },
}

# df-overseer-landmarks.lua's list_landmarks(): a bare array, each entry
# {name, kind, exits: [{to, direction, distance_tiles, walkable}, ...]}.
# Names/distances taken from run #1's own survey text (Wagon 1 tile E of the
# Embark Site; Stockpile #1 3 tiles SW; Stockpile #2 8 tiles SW of the
# Embark Site, 6 tiles SW of Stockpile #1, 9 tiles SW of the Wagon).
LANDMARKS_LIST_JSON = [
    {
        "name": "Embark Site",
        "kind": "seed",
        "exits": [
            {"to": "Wagon", "direction": "E", "distance_tiles": 1, "walkable": True},
            {"to": "Stockpile #1", "direction": "SW", "distance_tiles": 3, "walkable": True},
            {"to": "Stockpile #2", "direction": "SW", "distance_tiles": 8, "walkable": True},
        ],
    },
    {
        "name": "Stockpile #2",
        "kind": "Stockpile",
        "exits": [
            {"to": "Stockpile #1", "direction": "NE", "distance_tiles": 6, "walkable": True},
            {"to": "Embark Site", "direction": "NE", "distance_tiles": 8, "walkable": True},
            {"to": "Wagon", "direction": "NE", "distance_tiles": 9, "walkable": True},
        ],
    },
    {
        "name": "Wagon",
        "kind": "Wagon",
        "exits": [
            {"to": "Embark Site", "direction": "W", "distance_tiles": 1, "walkable": True},
        ],
    },
]

# df-overseer-landmarks.lua's `get NAME` CLI command / get_landmark(): a
# single landmark dict, or {"error": "not found"} -- see the .lua's own
# `print(lm and json.encode(lm) or json.encode({error = "not found"}))`.
LANDMARK_GET_STOCKPILE_2_JSON = LANDMARKS_LIST_JSON[1]
LANDMARK_GET_NOT_FOUND_JSON = {"error": "not found"}

# df-overseer-stocks.lua's get_food_drink()/get_seeds(): real shapes,
# live-verified against Uniboslan 2026-09-16 (handoffs/2026-09-16-
# stocks-read-and-labor-race.md) via a throwaway /tmp script over
# dfhack-run lua -- these exact numbers are the real live counts that
# session read, not invented. SECOND FIX, same day: the tool used to count
# item ENTITIES only ("count"); the user reading the screen caught that "5
# raw edible items" was really ~20-24 units of food (a fisherdwarf's/
# hunter's catch stacks several units per item entity). Every bucket now
# reports both `units` (item.stack_size summed -- the real quantity) and
# `item_count` (the distinct-entity count) -- these fixtures use the
# corrected, re-verified live numbers: raw_edibles units=24 (10 fish + 9
# plant + 5 meat), item_count=5; drink units=0 (unaffected -- both real
# DRINK items are caravan-held either way), foreign_units=50.
STOCKS_FOOD_DRINK_JSON = {
    "drink": {
        "units": 0, "item_count": 0,
        "foreign_units": 50, "foreign_item_count": 2,
        "rotten_units": 0, "unreachable_units": 0,
    },
    "prepared_meals": {
        "units": 0, "item_count": 0,
        "foreign_units": 0, "foreign_item_count": 0,
        "rotten_units": 0, "unreachable_units": 0,
    },
    "raw_edibles": {
        "units": 24, "item_count": 5,
        "foreign_units": 245, "foreign_item_count": 49,
        "rotten_units": 0, "unreachable_units": 0,
    },
}

# SEEDS items on this fort happen to always carry stack_size == 1, so
# total_units == total_item_count here -- an observed fact about this fort
# today, not a property of the SEEDS type in general, which is exactly why
# get_seeds() reports both rather than assuming the equality holds.
STOCKS_SEEDS_JSON = {
    "total_units": 59,
    "total_item_count": 59,
    "by_plant_units": {
        "MUSHROOM_HELMET_PLUMP": 34,
        "POD_SWEET": 5,
        "GRASS_TAIL_PIG": 5,
        "MUSHROOM_CUP_DIMPLE": 5,
        "GRASS_WHEAT_CAVE": 5,
        "BUSH_QUARRY": 5,
    },
    "by_plant_item_count": {
        "MUSHROOM_HELMET_PLUMP": 34,
        "POD_SWEET": 5,
        "GRASS_TAIL_PIG": 5,
        "MUSHROOM_CUP_DIMPLE": 5,
        "GRASS_WHEAT_CAVE": 5,
        "BUSH_QUARRY": 5,
    },
}

# df-overseer-orders.lua's list_orders(): {orders: [...], manager_appointed}.
# Shape matches df-overseer-orders.lua's own header/TOOLS.yaml notes.
ORDERS_LIST_JSON = {
    "orders": [
        {
            "id": 17, "queue_position": 1, "job": "ConstructBlocks",
            "reaction": None, "amount_left": 3, "amount_total": 5,
        },
    ],
    "manager_appointed": True,
}

# df-overseer-stocks.lua's get_availability(): live-verified 2026-09-20,
# `availability BOULDER` read 7 total, 3 in buildings, 4 available
# (scripts/dfhack/TOOLS.yaml's own "availability TYPE" entry). Only the
# fields this signal reads are filled in exactly; the rest are the real
# per-flag breakdown fields this tool reports, included so the fixture is
# an honest stand-in for the real shape, not a stripped-down guess.
STOCKS_AVAILABILITY_BOULDER_JSON = {
    "type": "BOULDER",
    "total_units": 7, "total_item_count": 7,
    "available_units": 4, "available_item_count": 4,
    "unnetted_units": 0, "unnetted_item_count": 0,
    "in_job_units": 0, "in_job_item_count": 0,
    "forbid_units": 0, "forbid_item_count": 0,
    "owned_units": 0, "owned_item_count": 0,
    "owned_ref_check": {"verified_offline": True},
    "in_building_units": 3, "in_building_item_count": 3,
    "construction_units": 0, "construction_item_count": 0,
    "trader_units": 0, "trader_item_count": 0,
    "rotten_units": 0, "unreachable_units": 0,
    "flag_read_errors": [],
}

# get_availability's own real failure shape for an unresolved TYPE
# (scripts/dfhack/TOOLS.yaml: "An unresolved TYPE returns {error: ...}").
STOCKS_AVAILABILITY_UNKNOWN_TYPE_JSON = {"error": "unknown item type: NOT_A_REAL_TYPE"}

# df-overseer-stuckjobs.lua's get_stuck_jobs(): a bare array.
STUCK_JOBS_JSON = [
    {
        "job_type": "ConstructBuilding",
        "detail": "Construct Mason's Workshop",
        "building": None,
        "waiting_on": "no worker assigned",
        "idle_ticks": None,
        "near_landmark": "Embark Site",
        "direction": "S",
        "distance_tiles": 5,
    },
]


def _call_tool(tool_id: str, arguments: dict):
    """A fixed router over the fake JSON above, standing in for the
    injected `call_tool` a real caller (`dfqueue.grade`, eventually
    `dfmcp`) supplies."""
    if tool_id == "overview.get":
        return OVERVIEW_JSON
    if tool_id == "landmarks.list":
        return LANDMARKS_LIST_JSON
    if tool_id == "landmarks.get":
        name = arguments.get("name")
        if name == "Stockpile #2":
            return LANDMARK_GET_STOCKPILE_2_JSON
        return LANDMARK_GET_NOT_FOUND_JSON
    if tool_id == "stuckjobs.find":
        return STUCK_JOBS_JSON
    if tool_id == "stocks.food-drink":
        return STOCKS_FOOD_DRINK_JSON
    if tool_id == "stocks.seeds":
        return STOCKS_SEEDS_JSON
    if tool_id == "orders.list":
        return ORDERS_LIST_JSON
    if tool_id == "stocks.availability":
        item_type = arguments.get("type")
        if item_type == "BOULDER":
            return STOCKS_AVAILABILITY_BOULDER_JSON
        return STOCKS_AVAILABILITY_UNKNOWN_TYPE_JSON
    raise AssertionError(f"unexpected tool_id in test double: {tool_id!r}")


# ---- parse() --------------------------------------------------------------------


def test_parse_each_fixed_signal():
    for signal, kind in (
        ("fort.population", FORT_POPULATION),
        ("fort.alerts.count", FORT_ALERTS_COUNT),
        ("fort.stuck_jobs.count", FORT_STUCK_JOBS_COUNT),
        ("fort.landmarks.count", FORT_LANDMARKS_COUNT),
    ):
        parsed = parse(signal)
        assert parsed.kind == kind
        assert parsed.signal == signal
        assert parsed.value_type == INTEGER


def test_parse_each_stocks_signal():
    for signal, kind in (
        ("stocks.drink.units", STOCKS_DRINK_UNITS),
        ("stocks.prepared_meals.units", STOCKS_PREPARED_MEALS_UNITS),
        ("stocks.raw_edibles.units", STOCKS_RAW_EDIBLES_UNITS),
        ("stocks.seeds.units", STOCKS_SEEDS_UNITS),
    ):
        parsed = parse(signal)
        assert parsed.kind == kind
        assert parsed.signal == signal
        assert parsed.value_type == INTEGER


def test_parse_order_exists():
    parsed = parse('order."17".exists')
    assert parsed.kind == ORDER_EXISTS
    assert parsed.order_id == "17"
    assert parsed.value_type == BOOLEAN


def test_parse_stocks_availability_units():
    parsed = parse('stocks.availability."BOULDER".available_units')
    assert parsed.kind == STOCKS_AVAILABILITY_UNITS
    assert parsed.item_type == "BOULDER"
    assert parsed.value_type == INTEGER


def test_parse_landmark_exists_with_a_plain_name():
    parsed = parse('landmark."Wagon".exists')
    assert parsed.kind == LANDMARK_EXISTS
    assert parsed.landmark == "Wagon"
    assert parsed.value_type == BOOLEAN


def test_parse_landmark_exit_distance():
    parsed = parse('landmark."Stockpile #2".exit."Wagon".distance_tiles')
    assert parsed.kind == LANDMARK_EXIT_DISTANCE
    assert parsed.landmark == "Stockpile #2"
    assert parsed.exit_to == "Wagon"
    assert parsed.value_type == INTEGER


def test_parse_landmark_name_with_a_space_and_a_hash():
    # "Stockpile #2" is a real, live-confirmed default DF building name
    # (df-overseer-landmarks.lua's header comment). Neither the space nor
    # the '#' needs escaping inside the quotes.
    parsed = parse('landmark."Stockpile #2".exists')
    assert parsed.landmark == "Stockpile #2"


def test_parse_landmark_name_containing_a_dot():
    # A literal '.' inside the quotes must not be mistaken for the signal
    # grammar's own separators.
    parsed = parse('landmark."Mason\'s Workshop No. 2".exit."Wagon".distance_tiles')
    assert parsed.landmark == "Mason's Workshop No. 2"
    assert parsed.exit_to == "Wagon"


def test_parse_landmark_name_containing_a_literal_quote_is_escaped():
    name = 'Odd "Named" Hall'
    signal = f'landmark."{quote_landmark_name(name)}".exists'
    assert signal == r'landmark."Odd \"Named\" Hall".exists'
    parsed = parse(signal)
    assert parsed.landmark == name


def test_parse_landmark_name_containing_a_literal_backslash_is_escaped():
    name = r"Back\Slash Hall"
    signal = f'landmark."{quote_landmark_name(name)}".exists'
    parsed = parse(signal)
    assert parsed.landmark == name


@pytest.mark.parametrize("bad", [
    "",
    "fort.popuation",
    "landmarks.new_workshop.exit_to_Wagon.distance_tiles",  # run #1's raw, unquoted shape
    "landmark.Wagon.exists",       # unquoted name -- must be rejected outright
    'landmark."Wagon".exit."X"',   # missing .distance_tiles
    "design.entrance_count",       # a real ledger field, not a live signal
])
def test_parse_rejects_anything_not_a_known_live_signal(bad):
    with pytest.raises(SignalError):
        parse(bad)


def test_parse_rejects_non_string():
    with pytest.raises(SignalError):
        parse(None)
    with pytest.raises(SignalError):
        parse(123)


# ---- read() ---------------------------------------------------------------------


def test_read_fort_population():
    assert read(parse("fort.population"), _call_tool) == 15


def test_read_fort_alerts_count_nonzero():
    def call_tool(tool_id, arguments):
        if tool_id == "overview.get":
            return OVERVIEW_WITH_ALERTS_JSON
        return _call_tool(tool_id, arguments)

    assert read(parse("fort.alerts.count"), call_tool) == 1


def test_read_fort_alerts_count_zero():
    assert read(parse("fort.alerts.count"), _call_tool) == 0


def test_read_fort_stuck_jobs_count():
    assert read(parse("fort.stuck_jobs.count"), _call_tool) == 1


def test_read_fort_landmarks_count():
    assert read(parse("fort.landmarks.count"), _call_tool) == 3


def test_read_stocks_drink_units_zero():
    # Uniboslan's real, live-verified state 2026-09-16: 2 DRINK items in
    # play, both flags.trader (caravan-held) -- zero fort-owned, whether
    # measured in units or item_count.
    assert read(parse("stocks.drink.units"), _call_tool) == 0


def test_read_stocks_prepared_meals_units():
    assert read(parse("stocks.prepared_meals.units"), _call_tool) == 0


def test_read_stocks_raw_edibles_units():
    # 5 fort-owned item ENTITIES, but 24 UNITS (10 fish + 9 plant + 5 meat)
    # -- the exact bug the user caught by reading the screen: the tool used
    # to report the item_count (5) here, understating real food by ~5x.
    assert read(parse("stocks.raw_edibles.units"), _call_tool) == 24


def test_read_stocks_seeds_units():
    # Of 119 SEEDS items live on this fort, only 59 units are fort-owned --
    # the other 60 are the current caravan's own seed-variety trade goods.
    # SEEDS items each carry stack_size == 1 on this fort, so this number
    # happens to equal the item_count too (checked in the fixture above).
    assert read(parse("stocks.seeds.units"), _call_tool) == 59


def test_read_landmark_exists_true():
    assert read(parse('landmark."Wagon".exists'), _call_tool) is True


def test_read_landmark_exists_false_for_a_landmark_not_built_yet():
    assert read(parse('landmark."new_workshop".exists'), _call_tool) is False


def test_read_landmark_exit_distance():
    parsed = parse('landmark."Stockpile #2".exit."Wagon".distance_tiles')
    assert read(parsed, _call_tool) == 9


def test_read_landmark_exit_distance_missing_landmark_is_unresolvable_not_an_error():
    # The exact situation run #1's real proposal is in: it predicts a
    # distance for a workshop it is itself proposing to build, which does
    # not exist as a landmark yet.
    parsed = parse('landmark."new_workshop".exit."Wagon".distance_tiles')
    assert read(parsed, _call_tool) is UNRESOLVABLE


def test_read_landmark_exit_distance_missing_exit_is_unresolvable():
    # Wagon exists but has no exit named "Nonexistent" in its own ranked list.
    parsed = parse('landmark."Wagon".exit."Nonexistent".distance_tiles')
    assert read(parsed, _call_tool) is UNRESOLVABLE


def test_read_landmarks_list_error_shape_reads_as_no_landmarks():
    # merged_landmarks_with_coords's one failure case (no citizens found
    # yet to seed a landmark set): the CLI prints {"error": ...} instead of
    # a bare array -- must not crash count/exists reads.
    def call_tool(tool_id, arguments):
        if tool_id == "landmarks.list":
            return {"error": "no citizens found -- can't compute an embark-site centroid"}
        return _call_tool(tool_id, arguments)

    assert read(parse("fort.landmarks.count"), call_tool) == 0
    assert read(parse('landmark."Wagon".exists'), call_tool) is False


def test_read_order_exists_true():
    assert read(parse('order."17".exists'), _call_tool) is True


def test_read_order_exists_false_once_gone():
    # A completed or cancelled order is removed from world.manager_orders.all
    # by DF's own engine (see this module's docstring); a caller predicting
    # "the order finishes" writes op="not_exists" against this signal.
    assert read(parse('order."999".exists'), _call_tool) is False


def test_read_stocks_availability_units():
    parsed = parse('stocks.availability."BOULDER".available_units')
    assert read(parsed, _call_tool) == 4


def test_read_stocks_availability_units_unresolvable_for_an_unknown_type():
    parsed = parse('stocks.availability."NOT_A_REAL_TYPE".available_units')
    assert read(parsed, _call_tool) is UNRESOLVABLE
