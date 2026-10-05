"""The briefing's `facts` block: handoffs/2026-10-05-better-briefing.md."""

from __future__ import annotations

import json

from conductor.briefing import (
    MAX_AVAILABILITY_LINES, MAX_ORDER_LINES, availability_line, build_briefing, build_facts, order_facts,
    seed_facts, stock_facts,
)
from conductor.triage import Wake

_WAKE = Wake("migrant_wave", "a migrant wave arrived", ("architect", "quartermaster"), "full_speed")
_VITALS = {
    "alive": 22, "dead_total": 1, "worst_hunger_status": "fine",
    "worst_thirst_status": "fine", "warning_count": 0,
}
_FOOD_DRINK = {
    "drink": {"units": 4, "item_count": 1, "foreign_units": 50, "unreachable_units": 0},
    "prepared_meals": {"units": 0, "item_count": 0},
    "raw_edibles": {"units": 24, "item_count": 5, "unreachable_units": 3},
}


def test_stock_facts_use_fort_owned_units_and_divide_by_citizens():
    facts = stock_facts(_FOOD_DRINK, 22)
    assert facts["drink_units"] == 4
    assert facts["drink_per_citizen"] == 0.2
    assert facts["raw_edibles_units"] == 24
    assert facts["raw_edibles_unreachable_units"] == 3
    assert "drink_unreachable_units" not in facts  # zero is not worth a line
    assert "foreign" not in json.dumps(facts)  # caravan goods are not the fort's


def test_stock_facts_drop_on_a_bad_shape():
    assert stock_facts(None, 22) is None
    assert stock_facts({"error": "x"}, 22) is None
    assert stock_facts("nope", 22) is None


def test_order_facts_list_only_orders_not_progressing_and_cap_them():
    orders = [{"id": 1, "job": "MakeBarrel", "validated": True, "active": True, "amount_left": 1, "amount_total": 2}]
    orders += [
        {"id": 10 + i, "job": "BrewDrinkFromPlant", "validated": True, "active": False,
         "amount_left": 1, "amount_total": 1} for i in range(MAX_ORDER_LINES + 3)
    ]
    orders.append({"id": 99, "job": "MakeBed", "validated": False, "active": False})
    out = order_facts({"orders": orders, "manager_appointed": True})
    assert out["total"] == len(orders)
    assert out["not_progressing"]["count"] == MAX_ORDER_LINES + 4
    assert len(out["not_progressing"]["items"]) == MAX_ORDER_LINES
    assert out["not_progressing"]["items"][0] == "#10 BrewDrinkFromPlant validated, not active, 1 of 1 left"
    assert out["manager_appointed"] is True


def test_order_facts_drop_on_a_bad_shape():
    assert order_facts(None) is None
    assert order_facts({"orders": "x"}) is None


def test_availability_line_and_bad_rows():
    row = {"total_units": 6, "available_units": 2, "in_job_units": 1}
    assert availability_line("BARREL", row) == "BARREL: 2 free of 6, 1 in jobs"
    assert availability_line("BED", {"total_units": 0, "available_units": 0}) == "BED: 0 free of 0"
    assert availability_line("BED", {"error": "unknown item type"}) is None
    assert availability_line("BED", None) is None


def test_seed_facts_name_the_top_plants_only():
    out = seed_facts({"total_units": 59, "by_plant_units": {"A": 34, "B": 10, "C": 9, "D": 6}})
    assert out == {"total_units": 59, "top_plants": ["A 34", "B 10", "C 9"]}
    assert seed_facts({"error": "x"}) is None


def test_build_facts_shows_only_the_types_the_role_asked_for():
    availability = {
        "BARREL": {"total_units": 6, "available_units": 2},
        "BED": {"total_units": 1, "available_units": 0},
    }
    facts = build_facts(
        vitals=_VITALS, food_drink=_FOOD_DRINK, orders_state={"orders": []},
        availability=availability, want_availability=["BARREL", "WOOD"],
    )
    assert facts["availability"]["items"] == ["BARREL: 2 free of 6"]  # BED not asked, WOOD not read
    assert "seeds" not in facts
    assert facts["stocks"]["drink_units"] == 4


def test_build_facts_is_empty_when_every_read_failed():
    assert build_facts(vitals=_VITALS) == {}
    assert build_facts(vitals={}, food_drink=_FOOD_DRINK)["stocks"]["drink_units"] == 4


def test_facts_size_is_bounded_whatever_the_fort_holds():
    orders = [{"id": i, "job": "J", "validated": True, "active": False} for i in range(5000)]
    types = [f"T{i}" for i in range(100)]
    availability = {t: {"total_units": 9, "available_units": 3} for t in types}
    facts = build_facts(
        vitals=_VITALS, food_drink=_FOOD_DRINK, orders_state={"orders": orders},
        availability=availability, want_availability=types,
        seeds={"total_units": 1, "by_plant_units": {str(i): i for i in range(500)}}, want_seeds=True,
    )
    assert len(facts["orders"]["not_progressing"]["items"]) == MAX_ORDER_LINES
    assert len(facts["availability"]["items"]) == MAX_AVAILABILITY_LINES
    assert len(facts["seeds"]["top_plants"]) == 3
    assert len(json.dumps(facts)) < 2500


def test_build_briefing_carries_facts_only_when_given():
    base = dict(role="quartermaster", game_tick=1, wake=_WAKE, vitals=_VITALS, diff_events=[], queue_summary={"count": 0})
    assert "facts" not in build_briefing(**base)
    assert "facts" not in build_briefing(**base, facts={})
    assert build_briefing(**base, facts={"stocks": {"drink_units": 4}})["facts"] == {"stocks": {"drink_units": 4}}
