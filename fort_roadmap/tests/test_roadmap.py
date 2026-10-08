"""The fort roadmap, V1 (register 2026-10-08): the seed file, its validator,
stage computation with a high-water mark, the game-flag cross-check, the plan
targets a stage supplies, the comply-or-explain deviation check and the
adopt-only exemption. Pure and offline."""

from __future__ import annotations

import copy

import pytest

from dfqueue import plan
from fort_roadmap import roadmap


@pytest.fixture
def data():
    return copy.deepcopy(roadmap.seed())


# ---- the seed file ---------------------------------------------------------------------


def test_the_shipped_seed_validates_with_no_refusal_and_no_flag():
    result = roadmap.validate(roadmap.seed())
    assert result == {"refusals": [], "flags": []}


def test_the_seed_has_the_three_agreed_stages_and_numbers():
    d = roadmap.seed()
    assert d["game_version"] == "53.16"
    assert roadmap.stage_ids(d) == ["founding", "hamlet", "village"]
    assert [roadmap._threshold(s) for s in d["stages"]] == [0, 20, 50]
    wants = {
        (s["id"], t["id"]): t["want"] for s in d["stages"] for t in s["targets"]
    }
    assert wants[("founding", "dormitory_beds")] == {"per_alive": 0.1, "min": 4, "max": 10}
    assert wants[("founding", "dining_tables")] == {"per_alive": 0.2, "min": 2}
    assert wants[("hamlet", "bedrooms")] == {"per_alive": 1.0}
    assert wants[("village", "bedrooms")] == {"per_alive": 1.0, "plus": 2}
    # tables, not chairs, and the zone tool's defining furniture for a dining hall is the Table
    assert all(
        t["signal"] == 'zones."DiningHall".furniture."Table"'
        for s in d["stages"] for t in s["targets"] if t["id"] == "dining_tables"
    )
    assert all(t["owner"] == "architect" and t["confidence"] == "prior" for s in d["stages"] for t in s["targets"])


def test_every_seed_target_cites_sources_in_doctrines_provenance_format():
    for s in roadmap.seed()["stages"]:
        for t in s["targets"]:
            assert t["sources"] and t["rationale"].strip()
    wiki = [src for s in roadmap.seed()["stages"] for t in s["targets"] for src in t["sources"] if src["kind"] == "wiki"]
    assert all("revid" in src for src in wiki)
    assert {src["revid"] for src in wiki} == {320477, 312062}


def test_the_stage_plan_targets_pass_the_plans_own_checks_as_a_fort_would_file_them():
    ctx = plan.PlanContext(zone_kinds={"Bedroom", "DiningHall", "Dormitory"}, landmarks=set())
    for sid in roadmap.stage_ids():
        assert plan.check_sections({"targets": roadmap.plan_targets(sid)}, ctx) == []


# ---- the validator ---------------------------------------------------------------------


def _codes(result):
    return {f["code"] for f in result["flags"]}


def test_a_coordinate_is_refused(data):
    data["stages"][0]["targets"][0]["rationale"] = "dig at x=12, y=40 first"
    assert any("raw-coordinate" in r for r in roadmap.validate(data)["refusals"])


@pytest.mark.parametrize("name", ["Uniboslan", "ragwind", "df-colony"])
def test_a_fort_or_host_name_is_refused(data, name):
    data["stages"][1]["summary"] = f"as {name} did"
    assert any(name.lower() in r for r in roadmap.validate(data)["refusals"])


def test_a_landmark_signal_or_anchor_key_is_refused(data):
    data["stages"][0]["targets"][0]["signal"] = 'zones."Dormitory".near."Wagon"'
    r1 = roadmap.validate(data)
    data["stages"][0]["targets"][0]["signal"] = 'zones."Dormitory".furniture."Bed"'
    data["stages"][0]["targets"][0]["anchor"] = "Wagon"
    r2 = roadmap.validate(data)
    assert any("anchors a target to a place" in r for r in r2["refusals"])
    # whichever way the signal grammar reads the first one, it is never silently clean
    assert r1["refusals"] or r1["flags"]


def test_a_malformed_stage_list_is_refused(data):
    data["stages"][1]["enter_when"] = {"alive_gte": 0}
    assert any("enter_when" in r for r in roadmap.validate(data)["refusals"])
    data = copy.deepcopy(roadmap.seed())
    data["stages"][2]["enter_when"] = {"alive_gte": 20}
    assert any("above the previous" in r for r in roadmap.validate(data)["refusals"])
    assert roadmap.validate({"kind": "fort_roadmap", "stages": []})["refusals"]
    assert roadmap.validate("not a mapping")["refusals"]
    data = copy.deepcopy(roadmap.seed())
    data["stages"][0]["enter_when"] = {"alive_gte": 5}
    assert any("first stage" in r for r in roadmap.validate(data)["refusals"])


def test_content_mistakes_are_flagged_not_refused(data):
    t = data["stages"][1]["targets"][0]
    t["signal"] = 'stocks.availability."DRINK".available_units'   # a stock number
    t["confidence"] = "measured"
    del t["rationale"]
    t["sources"] = []
    t["want"] = {"per_alive": 1.0, "min": 9, "max": 3}
    del data["game_version"]
    result = roadmap.validate(data)
    assert result["refusals"] == []
    assert {"stock_number", "bad_confidence", "rationale_missing", "sources_missing", "bad_threshold",
            "game_version_missing"} <= _codes(result)


def test_a_wiki_source_without_a_revid_is_flagged_and_a_bad_source_field_is_flagged(data):
    data["stages"][0]["targets"][1]["sources"][0]["read"] = "guessed"
    del data["stages"][0]["targets"][1]["sources"][0]["revid"]
    result = roadmap.validate(data)
    assert "bad_source" in _codes(result) and "uncited_revision" in _codes(result)
    assert result["refusals"] == []


def test_a_duplicate_target_id_within_a_stage_is_flagged(data):
    data["stages"][0]["targets"].append(copy.deepcopy(data["stages"][0]["targets"][0]))
    assert "duplicate_id" in _codes(roadmap.validate(data))


# ---- stage computation -------------------------------------------------------------------


@pytest.mark.parametrize("alive,stage", [(0, "founding"), (19, "founding"), (20, "hamlet"), (24, "hamlet"),
                                         (49, "hamlet"), (50, "village"), (200, "village")])
def test_the_stage_follows_alive_at_the_thresholds(alive, stage):
    assert roadmap.compute_stage(alive, None)["stage"] == stage


def test_a_dip_never_steps_the_stage_back_down():
    cs = roadmap.compute_stage(19, "hamlet")
    assert cs["stage"] == "hamlet" and cs["held"] is True and cs["entered"] is False and cs["by_alive"] == "founding"


def test_an_unknown_alive_count_keeps_the_stored_stage_and_is_not_read_as_zero():
    cs = roadmap.compute_stage(None, "hamlet")
    assert cs["stage"] == "hamlet" and cs["alive_known"] is False and cs["alive"] is None
    assert roadmap.compute_stage(None, None)["stage"] == "founding"
    assert roadmap.compute_stage(True, None)["alive_known"] is False   # a bool is not a count
    assert roadmap.compute_stage(-3, None)["alive_known"] is False


def test_entering_a_stage_is_reported_once_and_the_mark_is_stored(tmp_path):
    store = roadmap.StageStore(tmp_path / "f.roadmap-stage.json")
    first = roadmap.resolve(18, None, store)
    assert first["stage"] == "founding" and first["entered"] is True      # first sight of the fort
    again = roadmap.resolve(18, None, store)
    assert again["entered"] is False
    up = roadmap.resolve(21, None, store)
    assert up["stage"] == "hamlet" and up["entered"] is True and up["next"] == {"stage": "village", "alive_gte": 50, "alive": 21}
    dip = roadmap.resolve(17, None, store)
    assert dip["stage"] == "hamlet" and dip["held"] is True and dip["entered"] is False
    assert store.load() == ("hamlet", False)


def test_a_dry_resolve_does_not_store_the_mark(tmp_path):
    store = roadmap.StageStore(tmp_path / "f.json")
    roadmap.resolve(30, None, store, persist=False)
    assert store.load() == (None, False)


def test_an_unreadable_stage_file_reads_as_missing_and_says_so(tmp_path):
    p = tmp_path / "f.json"
    p.write_text("{not json", encoding="utf-8")
    block = roadmap.resolve(25, None, roadmap.StageStore(p), persist=False)
    assert block["stage"] == "hamlet" and block["stage_file_unreadable"] is True


def test_the_store_sits_beside_the_fort_database(tmp_path):
    assert roadmap.StageStore.beside(tmp_path / "queue.sqlite3").path == tmp_path / "queue.roadmap-stage.json"


# ---- the game-flag cross-check -------------------------------------------------------------


def _nobles(met, n=50):
    return {"positions": [
        {"code": "MAYOR", "requires_population": n, "population_requirement_met": met},
        {"code": "MANAGER", "requires_population": 0, "population_requirement_met": False},
    ]}


def test_the_game_flag_agrees_when_both_say_not_yet():
    (row,) = roadmap.cross_check(24, _nobles(False))
    assert row["state"] == "agree" and row["stage"] == "village" and row["game_flag_met"] is False


def test_a_disagreement_is_reported_not_acted_on():
    (row,) = roadmap.cross_check(24, _nobles(True))
    assert row["state"] == "disagree"
    block = roadmap.resolve(24, _nobles(True), None)
    assert block["stage"] == "hamlet"                      # the flag never moves the stage
    assert "disagrees with alive 24" in block["line"]
    (row,) = roadmap.cross_check(55, _nobles(False))
    assert row["state"] == "disagree"


@pytest.mark.parametrize("alive,nobles,state", [
    (24, None, "unreadable"), (None, _nobles(False), "unreadable"),
    (24, {"positions": []}, "no_position"), (24, {"error": "no entity"}, "unreadable"),
])
def test_an_unreadable_flag_is_never_a_guess(alive, nobles, state):
    (row,) = roadmap.cross_check(alive, nobles)
    assert row["state"] == state


# ---- the plan targets a stage supplies and the comply-or-explain check --------------------------


def test_plan_targets_are_the_stage_entries_with_a_roadmap_ref():
    hamlet = roadmap.plan_targets("hamlet")
    assert [t["id"] for t in hamlet] == ["bedrooms", "dining_tables"]
    assert hamlet[0] == {
        "id": "bedrooms", "signal": 'zones."Bedroom".furnished', "want": {"per_alive": 1.0},
        "reorder_gap": 2, "owner": "architect", "max_in_flight": 2, "roadmap_ref": "bedrooms",
    }
    assert "rationale" not in hamlet[0] and "sources" not in hamlet[0]
    assert [t["id"] for t in roadmap.plan_targets()] == ["dormitory_beds", "dining_tables"]   # the first stage


def test_a_target_equal_to_its_entry_does_not_deviate():
    t = roadmap.plan_targets("hamlet")
    res = roadmap.check_refs(t, "hamlet", 24)
    assert res == {"deviations": [], "flags": [], "missing": []}


def test_up_down_and_shape_deviations_are_computed_by_code():
    base = roadmap.plan_targets("hamlet")[0]
    up = {**base, "want": {"per_alive": 1.2}}
    down = {**base, "want": {"per_alive": 0.8}}
    shape = {**base, "want": 24, "per": None}   # a scalar where the entry has the mapping form
    assert roadmap.deviation(up, base, 24) == "up"
    assert roadmap.deviation(down, base, 24) == "down"
    assert roadmap.deviation({**base, "want": 30}, base, 24) == "shape"
    assert roadmap.deviation({**base, "signal": 'zones."Bedroom".counts'}, base, 24) == "shape"
    assert roadmap.deviation({**base, "reorder_gap": 3}, base, 24) == "shape"
    assert roadmap.deviation(base, base, 24) is None
    assert shape  # constructed for the readability of the cases above


def test_a_deviation_without_a_reason_is_flagged_but_never_inert():
    base = roadmap.plan_targets("hamlet")[0]
    res = roadmap.check_refs([{**base, "want": {"per_alive": 0.5}}], "hamlet", 24)
    assert res["deviations"] == [{"id": "bedrooms", "ref": "bedrooms", "kind": "down", "reason": None}]
    (flag,) = res["flags"]
    assert flag["code"] == "unexplained_deviation" and flag["inert"] is False   # the target still runs
    explained = roadmap.check_refs(
        [{**base, "want": {"per_alive": 0.5}, "deviation_reason": "half the fort sleeps in the dormitory"}], "hamlet", 24,
    )
    assert explained["flags"] == [] and explained["deviations"][0]["reason"] == "half the fort sleeps in the dormitory"
    blank = roadmap.check_refs([{**base, "want": {"per_alive": 0.5}, "deviation_reason": "   "}], "hamlet", 24)
    assert blank["flags"][0]["code"] == "unexplained_deviation"


def test_a_ref_to_no_entry_of_the_stage_is_an_information_flag_and_a_dropped_entry_is_listed():
    t = {**roadmap.plan_targets("hamlet")[0], "roadmap_ref": "dormitory_beds"}
    res = roadmap.check_refs([t], "hamlet", 24)
    assert res["flags"][0]["code"] == "roadmap_ref_unknown" and res["flags"][0]["inert"] is False
    assert res["missing"] == ["bedrooms", "dining_tables"]
    # a target with no ref is a fort-local target: allowed, never compared
    assert roadmap.check_refs([{"id": "x"}], "hamlet", 24) == {"deviations": [], "flags": [], "missing": ["bedrooms", "dining_tables"]}


# ---- the adopt-only exemption ----------------------------------------------------------------


def _changes(old, new):
    return plan.diff_changes({"targets": old}, {"targets": new})


def _active(stage, targets):
    a = {"version": 1, "targets": targets}
    if stage is not None:
        a["roadmap_stage"] = stage
    return a


def test_adopting_a_newly_entered_stage_exactly_is_exempt():
    old = roadmap.plan_targets("founding")
    new = roadmap.plan_targets("hamlet")
    assert roadmap.adopts_stage(_active("founding", old), _changes(old, new), {"targets": new}, "hamlet")


def test_a_plan_that_predates_stages_may_drop_its_old_default_targets_when_adopting():
    old = [
        {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "per": "alive", "want": 1.0, "reorder_gap": 2,
         "owner": "architect", "max_in_flight": 2},
        {"id": "dining_seats", "signal": 'zones."DiningHall".furniture."Chair"', "per": "alive", "want": 1.0,
         "reorder": 0.7, "owner": "architect", "max_in_flight": 1},
    ]
    new = roadmap.plan_targets("hamlet")
    assert roadmap.adopts_stage(_active(None, old), _changes(old, new), {"targets": new}, "hamlet")


def test_a_plan_stamped_with_a_null_stage_counts_as_predating_stages():
    """Live 2026-10-09: version 1 carried `roadmap_stage: null` (key present), so dropping its old
    default target was treated as touching a fort-local one and the adoption was refused."""
    old = [
        {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "per": "alive", "want": 1.0, "reorder_gap": 2,
         "owner": "architect", "max_in_flight": 2},
        {"id": "dining_seats", "signal": 'zones."DiningHall".furniture."Chair"', "per": "alive", "want": 1.0,
         "reorder": 0.7, "owner": "architect", "max_in_flight": 1},
    ]
    new = roadmap.plan_targets("hamlet")
    active = {"version": 1, "targets": old, "roadmap_stage": None}
    assert roadmap.adopts_stage(active, _changes(old, new), {"targets": new}, "hamlet")


def test_an_exact_copy_of_a_mapping_want_is_not_a_deviation():
    for t in roadmap.plan_targets("hamlet"):
        entry = {k: v for k, v in t.items() if k != "roadmap_ref"}
        assert roadmap.deviation(t, entry, 24) is None
    assert roadmap.check_refs(roadmap.plan_targets("hamlet"), "hamlet", 24)["deviations"] == []


def test_adopting_and_deviating_is_not_exempt():
    old = roadmap.plan_targets("founding")
    new = roadmap.plan_targets("hamlet")
    new[0] = {**new[0], "want": {"per_alive": 1.1}}
    assert not roadmap.adopts_stage(_active("founding", old), _changes(old, new), {"targets": new}, "hamlet")


def test_an_unrelated_change_or_the_same_stage_is_not_exempt():
    new = roadmap.plan_targets("hamlet")
    extra = new + [{"id": "extra", "signal": 'zones."Office".furnished', "want": 1, "reorder_gap": 1, "owner": "architect"}]
    assert not roadmap.adopts_stage(_active("founding", []), _changes([], extra), {"targets": extra}, "hamlet")
    assert not roadmap.adopts_stage(_active("hamlet", []), _changes([], new), {"targets": new}, "hamlet")
    assert not roadmap.adopts_stage(None, _changes([], new), {"targets": new}, "hamlet")
    assert not roadmap.adopts_stage(_active("founding", new), [], {"targets": new}, "hamlet")


def test_removing_a_fort_local_target_is_not_part_of_an_adoption_after_stages_exist():
    local = {"id": "mine", "signal": 'zones."Office".furnished', "want": 1, "reorder_gap": 1, "owner": "architect"}
    old = roadmap.plan_targets("founding") + [local]
    new = roadmap.plan_targets("hamlet")
    assert not roadmap.adopts_stage(_active("founding", old), _changes(old, new), {"targets": new}, "hamlet")


def test_the_guardrail_lets_an_adoption_through_a_busy_season_and_nothing_else():
    old = roadmap.plan_targets("founding")
    new = roadmap.plan_targets("hamlet")
    active = {**_active("founding", old), "season_index": 0, "flags": []}
    changes = _changes(old, new)
    assert plan.guardrail(active, 50, changes)["ok"] is False
    verdict = plan.guardrail(active, 50, changes, adopt_stage=True)
    assert verdict == {"ok": True, "reason": "adopt_stage"}


# ---- the one-line summary ------------------------------------------------------------------------


def test_the_status_line_names_the_stage_the_next_threshold_and_the_top_targets():
    block = roadmap.resolve(24, _nobles(False), None)
    assert block["line"] == (
        "ROADMAP stage hamlet (alive 24, village at 50): bedrooms 1/alive; dining_tables 0.2/alive min 4."
    )
    assert len(block["line"]) < 160


def test_the_line_for_the_last_stage_has_no_next_threshold_and_an_unknown_alive_says_so():
    assert "village at" not in roadmap.resolve(60, None, None)["line"]
    assert "alive unknown" in roadmap.resolve(None, None, None)["line"]
