"""The plan tools with the fort roadmap (register 2026-10-08, `fort_roadmap/`):
the stage in `plan.status` and `plan.read`, version 1 composed from the current
stage, comply-or-explain deviations, and the adopt-only season exemption. Uses
the fake fort of `test_plan_tools.py`."""
from __future__ import annotations

import pytest

from dfmcp import plan_tools, queue_tools
from dfmcp.tests.test_plan_tools import (  # noqa: F401 -- fixtures and helpers shared with that file
    BEDROOMS, SEASON, Fort, _plan, _write, db, planner_roster,
)
from dfqueue import store
from fort_roadmap import roadmap

pytestmark = pytest.mark.asyncio


class RoadmapFort(Fort):
    """The same fort plus `nobles.list`; `nobles` None makes that read fail."""

    def __init__(self):
        super().__init__()
        self.nobles = None

    async def __call__(self, tool_id, arguments):
        if tool_id == "nobles.list":
            self.calls.append((tool_id, dict(arguments)))
            if self.nobles is None:
                raise RuntimeError("nobles.list is down")
            return {"entity_id": 1, "positions": self.nobles}
        return await super().__call__(tool_id, arguments)


@pytest.fixture
def fort():
    return RoadmapFort()


def _positions(met):
    return [
        {"code": "MAYOR", "requires_population": 50, "population_requirement_met": met},
        {"code": "MANAGER", "requires_population": 0, "population_requirement_met": True},
    ]


def _stage_targets(stage):
    return roadmap.plan_targets(stage)


async def test_status_carries_the_roadmap_stage_and_holds_it_across_a_dip(db, fort):
    fort.alive, fort.nobles = 24, _positions(False)
    st = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    rm = st["roadmap"]
    assert rm["stage"] == "hamlet" and rm["entered"] is True and rm["alive"] == 24
    assert rm["next"] == {"stage": "village", "alive_gte": 50, "alive": 24}
    assert rm["cross_check"][0]["state"] == "agree" and rm["line"].startswith("ROADMAP stage hamlet")
    fort.alive = 17                                   # deaths: the stage does not step back down
    st = await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    assert st["roadmap"]["stage"] == "hamlet" and st["roadmap"]["held"] is True and st["roadmap"]["entered"] is False


async def test_the_game_population_flag_disagreeing_is_reported_and_never_moves_the_stage(db, fort):
    fort.alive, fort.nobles = 24, _positions(True)    # the game says 50 is met; alive says 24
    rm = (await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort))["roadmap"]
    assert rm["stage"] == "hamlet" and rm["cross_check"][0]["state"] == "disagree"
    assert "disagrees" in rm["line"]


async def test_an_unreadable_nobles_read_is_reported_unreadable_not_guessed(db, fort):
    fort.alive = 24                                   # nobles is None: the read raises
    rm = (await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort))["roadmap"]
    assert rm["stage"] == "hamlet" and rm["cross_check"][0]["state"] == "unreadable"


async def test_an_unreadable_alive_count_never_advances_or_regresses_the_stage(db, fort):
    fort.alive = 24
    await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)
    fort.fail.add("vitals.summary")
    rm = (await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort))["roadmap"]
    assert rm["stage"] == "hamlet" and rm["alive_known"] is False and rm["alive"] is None


async def test_version_one_is_the_current_stage_and_stamps_it(db, fort):
    fort.alive = 24
    out = await _write(db, fort, {"base_version": 0})
    assert out["filed"] and out["changes"] == [] and out["roadmap"]["stage"] == "hamlet"
    active = store.active_plan(db)
    assert [t["id"] for t in active["targets"]] == ["bedrooms", "dining_tables"]
    assert active["roadmap_stage"] == "hamlet" and active["deviations"] == []
    assert all(t["roadmap_ref"] == t["id"] for t in active["targets"])


async def test_a_deviation_without_a_reason_is_flagged_not_refused_and_with_one_it_is_recorded(db, fort):
    fort.alive = 24
    await _write(db, fort, {"base_version": 0})
    fort.tick = SEASON + 5
    base = store.active_plan(db)["targets"]
    wider = {**base[0], "want": {"per_alive": 1.2}}
    out = await _write(db, fort, {"base_version": 1, "set": {"targets": [wider, base[1]]}, "reason": "grow the share"})
    flag = next(f for f in out["flags"] if f["code"] == "unexplained_deviation")
    assert out["filed"] and flag["inert"] is False and flag["id"] == "bedrooms"
    assert out["roadmap"]["deviations"] == [{"id": "bedrooms", "ref": "bedrooms", "kind": "up", "reason": None}]
    assert out["inert_entries"] == []                 # the target still runs
    fort.tick = 2 * SEASON + 5
    why = {**wider, "deviation_reason": "migrants arrive in waves of ten"}
    out = await _write(db, fort, {"base_version": 2, "set": {"targets": [why, base[1]]}, "reason": "explain it"})
    assert not [f for f in out["flags"] if f["code"] == "unexplained_deviation"]
    assert store.active_plan(db)["deviations"] == [
        {"id": "bedrooms", "ref": "bedrooms", "kind": "up", "reason": "migrants arrive in waves of ten"}
    ]


async def test_a_ref_that_is_not_a_string_is_a_flagged_field(db, fort):
    fort.alive = 24
    bad = {**_stage_targets("hamlet")[0], "roadmap_ref": 7}
    out = await _write(db, fort, {"base_version": 0, "set": {"targets": [bad]}})
    assert any(f["code"] == "bad_field" and "roadmap_ref" in f["message"] for f in out["flags"])


async def test_a_revision_that_only_adopts_a_new_stage_skips_the_season_interval(db, fort):
    fort.alive = 12
    await _write(db, fort, {"base_version": 0})       # founding, season 0
    fort.alive, fort.tick = 24, 5000                  # same season: hamlet is entered
    # any other change this season is refused, as before ...
    with pytest.raises(queue_tools.QueueToolError, match="already has plan version 1"):
        await _write(db, fort, {"base_version": 1, "set": {"targets": [BEDROOMS]}, "reason": "mine"})
    # ... a revision that exactly adopts the stage is not
    out = await _write(db, fort, {"base_version": 1, "set": {"targets": _stage_targets("hamlet")}, "reason": "hamlet entered"})
    assert out["filed"] and out["season"] == {"ok": True, "reason": "adopt_stage"}
    assert store.active_plan(db)["roadmap_stage"] == "hamlet"


async def test_adopting_and_deviating_in_one_revision_waits_for_the_season(db, fort):
    fort.alive = 12
    await _write(db, fort, {"base_version": 0})
    fort.alive, fort.tick = 24, 5000
    targets = _stage_targets("hamlet")
    targets[0] = {**targets[0], "want": {"per_alive": 1.5}, "deviation_reason": "a bigger fort is coming"}
    with pytest.raises(queue_tools.QueueToolError, match="already has plan version 1"):
        await _write(db, fort, {"base_version": 1, "set": {"targets": targets}, "reason": "hamlet, but more"})


async def test_the_exemption_does_not_apply_once_the_stage_is_the_plans_own(db, fort):
    fort.alive = 12
    await _write(db, fort, {"base_version": 0})
    fort.alive, fort.tick = 24, 5000
    await _write(db, fort, {"base_version": 1, "set": {"targets": _stage_targets("hamlet")}, "reason": "hamlet entered"})
    fort.tick = 6000                                   # the plan is now hamlet's: a second change waits
    with pytest.raises(queue_tools.QueueToolError, match="already has plan version 2"):
        await _write(db, fort, {"base_version": 2, "set": {"targets": _stage_targets("hamlet")[:1]}, "reason": "trim"})


async def test_a_plan_filed_before_stages_existed_can_adopt_the_current_stage_at_once(db, fort):
    """The live fort's case: version 1 is the retired default (bedrooms and dining_seats, no stage stamp)."""
    fort.alive = 24
    legacy = [
        {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "per": "alive", "want": 1.0, "reorder_gap": 2,
         "owner": "architect", "max_in_flight": 2},
        {"id": "dining_seats", "signal": 'zones."DiningHall".furniture."Chair"', "per": "alive", "want": 1.0,
         "reorder": 0.7, "owner": "architect", "max_in_flight": 1},
    ]
    await _write(db, fort, {"base_version": 0, "set": {"targets": legacy}})
    assert "roadmap_stage" in store.active_plan(db)    # stamped now; strip it to model an older record
    fort.tick = 5000
    import sqlite3
    import json
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT rowid, payload FROM records WHERE kind = 'fort_plan'").fetchone()
        payload = json.loads(row[1])
        payload.pop("roadmap_stage"), payload.pop("deviations")
        conn.execute("UPDATE records SET payload = ? WHERE rowid = ?", (json.dumps(payload), row[0]))
    out = await _write(db, fort, {"base_version": 1, "set": {"targets": _stage_targets("hamlet")}, "reason": "adopt the roadmap"})
    assert out["filed"] and out["season"]["reason"] == "adopt_stage"
    assert [t["id"] for t in store.active_plan(db)["targets"]] == ["bedrooms", "dining_tables"]


async def test_a_null_stamped_v1_adopts_at_once_even_when_the_stage_was_already_entered(db, fort):
    """Live 2026-10-09: v1 had `roadmap_stage: null`, the stage mark was already hamlet (entered false)."""
    fort.alive = 24
    legacy = [
        {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "per": "alive", "want": 1.0, "reorder_gap": 2,
         "owner": "architect", "max_in_flight": 2},
        {"id": "dining_seats", "signal": 'zones."DiningHall".furniture."Chair"', "per": "alive", "want": 1.0,
         "reorder": 0.7, "owner": "architect", "max_in_flight": 1},
    ]
    await _write(db, fort, {"base_version": 0, "set": {"targets": legacy}})
    import json
    import sqlite3
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT rowid, payload FROM records WHERE kind = 'fort_plan'").fetchone()
        payload = json.loads(row[1])
        payload["roadmap_stage"] = None
        conn.execute("UPDATE records SET payload = ? WHERE rowid = ?", (json.dumps(payload), row[0]))
    fort.tick = 5000
    dry = await _write(db, fort, {"base_version": 1, "dry_run": True, "reason": "adopt",
                                  "set": {"targets": _stage_targets("hamlet")}})
    assert dry["roadmap"]["entered"] is False and dry["season"]["reason"] == "adopt_stage" and dry["would_file"]
    assert dry["roadmap"]["deviations"] == []          # an exact mapping-want copy is no deviation
    # adopting with scalar wants is a different want form: a flagged deviation, and not exempt
    scalar = [{**t, "want": 1.0} if t["id"] == "bedrooms" else t for t in _stage_targets("hamlet")]
    dry = await _write(db, fort, {"base_version": 1, "dry_run": True, "reason": "adopt", "set": {"targets": scalar}})
    assert dry["roadmap"]["deviations"][0]["kind"] == "shape" and dry["season"]["ok"] is False


async def test_a_dry_run_does_not_store_the_stage_mark(db, fort):
    fort.alive = 24
    out = await _write(db, fort, {"base_version": 0, "dry_run": True})
    assert out["dry_run"] and out["roadmap"]["stage"] == "hamlet"
    assert roadmap.StageStore.beside(db).load() == (None, False)


async def test_the_planner_and_overseer_read_the_roadmap_block_others_do_not(db, fort):
    fort.alive = 24
    pre = await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)
    assert pre["roadmap"]["stage"] == "hamlet"
    assert [t["id"] for t in pre["default"]["targets"]] == ["bedrooms", "dining_tables"]
    await _write(db, fort, {"base_version": 0})
    for role, sees in (("planner", True), ("overseer", True), ("architect", False)):
        out = await _plan(plan_tools.PLAN_READ, role, {}, db, fort)
        assert ("roadmap" in out) is sees, role
    out = await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)
    assert out["roadmap"]["plan_stage"] == "hamlet" and out["roadmap"]["deviations"] == []
    assert out["roadmap"]["targets"][0]["rationale"]


async def test_roadmap_wants_copied_verbatim_keep_their_floor_and_are_no_deviation(db, fort):
    """Regression (2026-10-09 plan v2): the roadmap's {per_alive, min} want is
    stored as the mapping, read back intact, and is not a `shape` deviation."""
    from dfqueue import plan

    fort.alive = 24
    await _write(db, fort, {"base_version": 0})
    fort.tick = SEASON + 5
    entries = {t["id"]: t for t in roadmap.plan_targets("hamlet")}
    tables = entries["dining_tables"]
    assert tables["want"] == {"per_alive": 0.2, "min": 4}
    # the plain numeric form still files (backward compatible), then the verbatim want replaces it
    plain = {k: v for k, v in tables.items() if k != "want"} | {"want": 0.2, "per": "alive"}
    await _write(db, fort, {"base_version": 1, "set": {"targets": [entries["bedrooms"], plain]}, "reason": "numeric"})
    fort.tick = 2 * SEASON + 5
    out = await _write(db, fort, {"base_version": 2, "set": {"targets": [entries["bedrooms"], tables]}, "reason": "adopt"})
    assert out["filed"] and out["roadmap"]["deviations"] == []
    stored = {t["id"]: t for t in store.active_plan(db)["targets"]}
    assert stored["dining_tables"]["want"] == {"per_alive": 0.2, "min": 4}
    assert plan.want_units(stored["dining_tables"], 10) == 4.0     # the floor holds at small populations
    assert plan.want_units(stored["dining_tables"], 24) == pytest.approx(4.8)


async def test_status_carries_the_roadmap_check_the_conductors_planner_to_do_list_reads(db, fort):
    fort.alive = 24
    assert "roadmap_check" not in await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort)   # no plan yet
    await _write(db, fort, {"base_version": 0})
    chk = (await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort))["roadmap_check"]
    assert chk == {"stage": "hamlet", "deviations": [], "missing": []}
    active = store.active_plan(db)
    targets = [t for t in active["targets"] if t["id"] != "dining_tables"]
    fort.tick = SEASON + 5
    await _write(db, fort, {"base_version": active["version"], "set": {"targets": targets}, "reason": "drop the hall"})
    chk = (await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort))["roadmap_check"]
    assert chk["missing"] == ["dining_tables"]


# ---- the flat want form (live 2026-10-09: oneOf was flattened to `number` by openclaw) ------

def _no_union(node, path="schema"):
    """Every `oneOf`/`anyOf`/`allOf` in a schema, since a client may flatten any of them."""
    bad = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("oneOf", "anyOf", "allOf"):
                bad.append(f"{path}.{k}")
            bad += _no_union(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad += _no_union(v, f"{path}[{i}]")
    return bad


def test_the_plan_write_schema_has_no_union_types_and_want_is_a_plain_number():
    from dfmcp.plan_tools import _SCHEMAS

    schema = _SCHEMAS[plan_tools.PLAN_WRITE]
    assert _no_union(schema) == []
    props = schema["properties"]["set"]["properties"]["targets"]["items"]["properties"]
    assert props["want"]["type"] == "number"
    for k in ("want_plus", "want_min", "want_max"):
        assert props[k]["type"] == "number"


async def test_the_flat_want_form_files_as_the_roadmap_mapping_and_is_no_deviation(db, fort):
    fort.alive = 24
    await _write(db, fort, {"base_version": 0})
    fort.tick = SEASON + 5
    # move off the roadmap's mapping first (v2 numeric, the live state), then file the flat form
    numeric = [
        {**t, "want": 1.0 if t["id"] == "bedrooms" else 0.2, "per": "alive"}
        for t in roadmap.plan_targets("hamlet")
    ]
    await _write(db, fort, {"base_version": 1, "set": {"targets": numeric}, "reason": "numeric"})
    fort.tick = 2 * SEASON + 5
    flat_bed = {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "want": 1.0, "per": "alive",
                "want_plus": 0, "reorder_gap": 2, "owner": "architect", "max_in_flight": 2,
                "roadmap_ref": "bedrooms"}
    flat_tables = {"id": "dining_tables", "signal": 'zones."DiningHall".furniture."Table"', "want": 0.2,
                   "per": "alive", "want_min": 4, "reorder_gap": 1, "owner": "architect", "max_in_flight": 1,
                   "roadmap_ref": "dining_tables"}
    out = await _write(db, fort, {"base_version": 2, "set": {"targets": [flat_bed, flat_tables]}, "reason": "adopt"})
    assert out["filed"] and out["roadmap"]["deviations"] == [] and out["flags"] == []
    stored = {t["id"]: t for t in store.active_plan(db)["targets"]}
    assert stored["bedrooms"]["want"] == {"per_alive": 1.0} and "per" not in stored["bedrooms"]
    assert stored["dining_tables"]["want"] == {"per_alive": 0.2, "min": 4} and "want_min" not in stored["dining_tables"]


async def test_a_numeric_per_alive_want_equals_the_per_alive_mapping_for_the_deviation_check(db, fort):
    """The plain numeric form (what v2 holds) is the same level as the roadmap's `{per_alive}`."""
    fort.alive = 24
    await _write(db, fort, {"base_version": 0})
    fort.tick = SEASON + 5
    plain = {"id": "bedrooms", "signal": 'zones."Bedroom".furnished', "want": 1.0, "per": "alive",
             "reorder_gap": 2, "owner": "architect", "max_in_flight": 2, "roadmap_ref": "bedrooms"}
    await _write(db, fort, {"base_version": 1, "set": {"targets": [plain]}, "reason": "plain"})
    chk = (await _plan(plan_tools.PLAN_STATUS, "conductor", {}, db, fort))["roadmap_check"]
    assert [d for d in chk["deviations"] if d["id"] == "bedrooms"] == []


async def test_plan_read_and_the_roadmap_block_show_targets_in_the_flat_form_that_files_back_verbatim(db, fort):
    fort.alive = 24
    await _write(db, fort, {"base_version": 0})
    out = await _plan(plan_tools.PLAN_READ, "planner", {}, db, fort)
    tables = next(t for t in out["targets"] if t["id"] == "dining_tables")
    assert tables["want"] == 0.2 and tables["per"] == "alive" and tables["want_min"] == 4
    assert not any(isinstance(t["want"], dict) for t in out["targets"])
    block = next(t for t in out["roadmap"]["targets"] if t["id"] == "dining_tables")
    assert (block["want"], block["per"], block["want_min"]) == (0.2, "alive", 4)
    # a plan.read target sent straight back changes nothing: the stored mapping is identical
    echoed = await _write(
        db, fort, {"base_version": 1, "set": {"targets": out["targets"]}, "reason": "echo", "dry_run": True})
    assert echoed["changes"] == [] and echoed["season"]["reason"] == "no_change" and echoed["flags"] == []
