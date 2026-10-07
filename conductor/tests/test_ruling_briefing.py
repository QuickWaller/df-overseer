"""Conductor-execution stage 1: the Overseer's ruling briefing and threshold
alerts held as policy data (`docs/CONDUCTOR-EXECUTION.md` 3.3)."""

from __future__ import annotations

import pytest

from conductor.briefing import RULING_ASK, build_ruling_briefing, evaluate_threshold_alerts
from conductor.policy import PolicyError, ThresholdAlert, load_policy
from conductor.triage import Wake

WAKE = Wake("queue_pending", "the queue holds something", ("overseer",), "full_speed")
VITALS = {"alive": 20, "dead_total": 1, "worst_hunger_status": "ok", "worst_thirst_status": "ok", "warning_count": 0}

PROPOSAL = {
    "id": "proposal-0007", "role": "quartermaster", "type": "work_order", "summary": "Brew drink",
    "rationale": "Drink is falling.", "priority": 4,
    "prediction": {"signal": "s", "op": "gte", "value": 10, "check_after_ticks": 1200},
    "cost": {"estimate": 3, "unit": "dwarf_ticks"},
    "cited": [
        {"tool": "stocks.availability", "args": {"type": "BARREL"}, "field": "available_units", "value": 2, "tick": 50},
        {"tool": "stocks.food-drink", "args": {}, "field": "drink.units", "value": 9, "tick": 50, "now": 4},
        {"tool": "stocks.seeds", "args": {}, "field": "total_units", "value": 1, "tick": 50, "now_unreadable": True},
    ],
    "duplicate_of": "proposal-0003", "overlaps": ["proposal-0008"],
}
BRIEF = {
    "count": 9, "shown": 1, "truncated": True, "proposals": [PROPOSAL],
    "decided": {
        "open_projects": [{"id": "project-0001", "title": "Bedroom", "steps_done": 1, "steps_total": 3,
                           "top_blocker": "no stone"}],
        "wip_count": 1,
        "recent_rulings": [{"id": "ruling-0002", "proposal_id": "proposal-0001", "decision": "accept", "reason": "ok"}],
    },
}


def _build(**kw):
    args = dict(game_tick=1234, wake=WAKE, vitals=VITALS, alerts=[], pending_brief=BRIEF)
    args.update(kw)
    return build_ruling_briefing(**args)


def test_sections_are_in_the_fixed_order_and_the_ask_is_last():
    text = _build(alerts=["Drink is low."], stuck_jobs=["job 4 stuck"], diff_events=[{"type": "x"}])
    marks = ["WAKE queue_pending", "VITALS alive=20", "ALERT Drink is low.", "DECIDED, DO NOT REDO",
             "PENDING PROPOSALS (1 shown of 9)", "OTHER OPEN ITEMS", "Rule on each pending proposal"]
    positions = [text.index(m) for m in marks]
    assert positions == sorted(positions)
    assert text.splitlines()[-1].startswith("Rule on each pending proposal")
    assert RULING_ASK.split("{")[0] in text


def test_the_stable_prefix_does_not_depend_on_the_proposals():
    one = _build()
    two = _build(pending_brief={**BRIEF, "proposals": [], "count": 0, "shown": 0})
    assert one.split("PENDING PROPOSALS")[0] == two.split("PENDING PROPOSALS")[0]


def test_cited_facts_show_now_only_when_changed_and_unreadable_is_said():
    text = _build()
    assert "stocks.availability(type=BARREL).available_units = 2 at tick 50\n" in text  # unchanged: no "now"
    assert "stocks.food-drink.drink.units = 9 at tick 50, now 4" in text
    assert "now unreadable" in text
    assert "Duplicate of proposal-0003." in text and "Overlaps proposal-0008." in text


def test_a_failed_queue_read_is_said_plainly():
    text = _build(pending_brief=None)
    assert "the queue read failed" in text and "PENDING PROPOSALS (0 shown of 0)" in text


def test_projects_and_rulings_are_one_line_each():
    text = _build()
    assert "- project-0001 Bedroom: 1/3 steps done; blocked: no stone" in text
    assert "- ruling-0002 accept proposal-0001: ok" in text


def test_no_alert_line_without_alerts():
    assert "ALERT" not in _build()


# ---- threshold alerts ------------------------------------------------------

DRINK = ThresholdAlert(
    name="drink", tool="stocks.food-drink", args={}, field="drink.units", per="alive", below=2,
    text="Drink low: {value} units, {per_value} each (below {threshold}).",
)
RAW = ThresholdAlert(name="raw", tool="t.x", args={}, field="n", below=5, text="n={value} below {threshold}")


def test_alert_only_while_crossed_and_divides_by_alive():
    assert evaluate_threshold_alerts([DRINK], {"drink": {"drink": {"units": 30}}}, 20) == [
        "Drink low: 30 units, 1.5 each (below 2)."
    ]
    assert evaluate_threshold_alerts([DRINK], {"drink": {"drink": {"units": 40}}}, 20) == []  # exactly 2: not below


def test_alert_without_per_uses_the_raw_value():
    assert evaluate_threshold_alerts([RAW], {"raw": {"n": 4}}, None) == ["n=4 below 5"]
    assert evaluate_threshold_alerts([RAW], {"raw": {"n": 5}}, None) == []


@pytest.mark.parametrize("result,alive", [
    (None, 20),                      # the read failed
    ({"drink": {}}, 20),             # field absent
    ({"drink": {"units": "many"}}, 20),
    ({"drink": {"units": True}}, 20),
    ({"drink": {"units": 1}}, 0),    # nobody alive: cannot divide
    ({"drink": {"units": 1}}, None),
])
def test_a_bad_read_or_input_drops_the_line(result, alive):
    assert evaluate_threshold_alerts([DRINK], {"drink": result}, alive) == []


def test_two_alerts_evaluate_independently():
    lines = evaluate_threshold_alerts([DRINK, RAW], {"drink": {"drink": {"units": 0}}, "raw": {"n": 9}}, 20)
    assert len(lines) == 1 and lines[0].startswith("Drink low")


# ---- policy data ----------------------------------------------------------


def test_shipped_policy_holds_the_alerts_as_generic_data():
    alerts = load_policy().threshold_alerts
    assert alerts and all(isinstance(a, ThresholdAlert) for a in alerts)
    assert {a.tool for a in alerts} == {"stocks.food-drink", "zone.list"}
    assert all(a.per == "alive" and a.below > 0 and "{value}" in a.text for a in alerts)


def _policy_file(tmp_path, alerts_yaml):
    base = (load_policy.__globals__["DEFAULT_POLICY_PATH"]).read_text(encoding="utf-8")
    head = base.split("threshold_alerts:")[0]
    path = tmp_path / "policy.yaml"
    path.write_text(head + "threshold_alerts:\n" + alerts_yaml, encoding="utf-8")
    return path


@pytest.mark.parametrize("alerts_yaml,fragment", [
    ("  - {read: {tool: a.b}, below: 1, text: t}\n", "tool and a field"),
    ("  - {read: {tool: a.b, field: f}, below: x, text: t}\n", "below"),
    ("  - {read: {tool: a.b, field: f}, below: 1, text: t, per: dwarves}\n", "per"),
    ("  - {read: {tool: a.b, field: f}, below: 1}\n", "text"),
])
def test_malformed_alert_entries_refuse_to_load(tmp_path, alerts_yaml, fragment):
    with pytest.raises(PolicyError, match=fragment):
        load_policy(_policy_file(tmp_path, alerts_yaml))


def test_a_new_alert_is_one_data_entry(tmp_path):
    path = _policy_file(tmp_path, "  - {name: wood, read: {tool: stocks.x, args: {k: 1}, field: a.b}, below: 3, text: 'wood {value}'}\n")
    (alert,) = load_policy(path).threshold_alerts
    assert (alert.name, alert.tool, alert.args, alert.field, alert.per) == ("wood", "stocks.x", {"k": 1}, "a.b", None)


def test_every_alert_read_is_on_the_conductors_own_allowlist():
    import yaml
    from pathlib import Path

    doc = yaml.safe_load((Path(__file__).resolve().parents[2] / "agents" / "conductor" / "tools.yaml").read_text(encoding="utf-8"))
    granted = {t["id"] for t in (doc.get("read") or [])}
    assert {a.tool for a in load_policy().threshold_alerts} <= granted
    assert "queue.pending_brief" in granted


def test_the_ask_says_to_carry_out_accepted_proposals_until_routing_exists():
    # Live 2026-10-05: "stop when each has a ruling" left an accepted brew
    # unexecuted, since no executor exists before stage 2.
    last = _build().splitlines()[-1]
    assert "carry out each proposal you accept" in last
    assert "queue.project" in last and "queue.executed" in last


# ---- stage P0: the `missing` default and the bedroom alert ------------------

BEDS = ThresholdAlert(
    name="beds", tool="zone.list", args={}, field="counts_by_kind.Bedroom", per="alive", below=1,
    text="Beds {value}, {per_value} each (below {threshold}).", missing_leaf=0,
)
BEDS_NO_DEFAULT = ThresholdAlert(
    name="beds", tool="zone.list", args={}, field="counts_by_kind.Bedroom", per="alive", below=1, text="x",
)


def test_a_missing_default_stands_in_for_an_absent_field_of_a_successful_read():
    # counts_by_kind is {} when no zone of any kind exists.
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {}}}, 20) == [
        "Beds 0, 0.0 each (below 1)."
    ]
    # Other kinds present, no Bedroom key.
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {"Office": 1}}}, 20) == [
        "Beds 0, 0.0 each (below 1)."
    ]


def test_without_a_missing_default_an_absent_field_still_drops_the_line():
    assert evaluate_threshold_alerts([BEDS_NO_DEFAULT], {"beds": {"counts_by_kind": {}}}, 20) == []


def test_a_failed_read_drops_the_line_even_with_a_missing_default():
    assert evaluate_threshold_alerts([BEDS], {"beds": None}, 20) == []
    assert evaluate_threshold_alerts([BEDS], {}, 20) == []


def test_bedrooms_cross_below_one_per_citizen():
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {"Bedroom": 19}}}, 20) == [
        "Beds 19, 0.9 each (below 1)."
    ]
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {"Bedroom": 20}}}, 20) == []
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {"Bedroom": 25}}}, 20) == []


@pytest.mark.parametrize("result", [
    {}, {"error": "x"}, {"error": "x", "counts_by_kind": {}}, {"counts_by_kind": []}, {"counts_by_kind": 3},
    [], "oops",
])
def test_missing_leaf_drops_an_error_shaped_or_malformed_read(result):
    assert evaluate_threshold_alerts([BEDS], {"beds": result}, 20) == []


def test_missing_leaf_applies_only_to_the_last_segment():
    deep = ThresholdAlert(name="d", tool="t.x", args={}, field="a.b.c", below=1, text="c={value}", missing_leaf=0)
    assert evaluate_threshold_alerts([deep], {"d": {"a": {"b": {}}}}, None) == ["c=0"]
    assert evaluate_threshold_alerts([deep], {"d": {"a": {}}}, None) == []


def test_unrounded_ratio_is_compared_21_of_22_crosses():
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {"Bedroom": 21}}}, 22) == [
        "Beds 21, 1.0 each (below 1)."
    ]
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {"Bedroom": 22}}}, 22) == []


def test_quartermaster_lane_lists_its_alerts_explicitly_not_star():
    lane = load_policy().lane_triggers["quartermaster"]
    assert "*" not in lane.alerts
    assert set(lane.alerts) == {"drink_per_citizen", "raw_food_per_citizen"}


def test_bedroom_crossing_wakes_the_architect_and_not_the_quartermaster():
    from conductor import lanes

    policy = load_policy()
    state = lanes.LaneState()
    lanes.apply_alert_edges(policy, state, {"bedrooms_per_citizen": True}, {"bedrooms_per_citizen": "short"})
    assert state.pending.get("architect")
    assert not state.pending.get("quartermaster")


def test_missing_default_does_not_rescue_a_non_container_or_a_bad_alive():
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": None}}, 20) == []
    assert evaluate_threshold_alerts([BEDS], {"beds": {"counts_by_kind": {}}}, 0) == []


def test_shipped_bedroom_alert_is_policy_data_with_a_missing_default():
    policy = load_policy()
    (alert,) = [a for a in policy.threshold_alerts if a.name == "bedrooms_per_citizen"]
    assert (alert.tool, alert.field, alert.per, alert.below, alert.missing_leaf) == (
        "zone.list", "counts_by_kind.Bedroom", "alive", 1.0, 0.0)
    assert dict(alert.args) == {"KIND_FILTER": "", "OWNER_FILTER": "", "VALID_FILTER": "", "NEAR_LANDMARK_FILTER": ""}
    assert "bedrooms_per_citizen" in policy.lane_triggers["architect"].alerts


def test_shipped_bedroom_alert_wakes_the_architect_once_per_edge():
    from conductor import lanes

    policy = load_policy()
    (alert,) = [a for a in policy.threshold_alerts if a.name == "bedrooms_per_citizen"]
    state = lanes.LaneState()

    def tick(bedrooms):
        found = evaluate_threshold_alerts([alert], {alert.name: {"counts_by_kind": bedrooms}}, 22)
        lanes.apply_alert_edges(policy, state, {alert.name: bool(found)}, {alert.name: found[0] if found else ""})

    key = lanes._ALERT + alert.name
    tick({})                                   # no bedrooms at all: crossed
    assert key in state.pending["architect"]
    assert "Bedrooms are short: 0" in state.pending["architect"][key]
    state.pending["architect"].clear()         # the Architect was woken and served
    tick({"Bedroom": 5})                       # still short: no second wake
    assert not state.pending.get("architect")
    tick({"Bedroom": 22})                      # cleared
    tick({"Bedroom": 3})                       # re-crossed: wakes again
    assert key in state.pending["architect"]
