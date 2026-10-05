"""Stage 2B (handoffs/2026-10-05-stage-2b.md, docs/CONDUCTOR-EXECUTION.md
section 6.2): per-phase completion, `level`, the reserve `finish_plan`, the
`reservation` field on `sites` rows, and `release ... ANY_PENDING`.

Runs the REAL df-overseer-blueprint.lua against the fake DFHack world in
tests/lua_stubs/dfhack_blueprint_world.lua through lupa, like
tests/test_blueprint_lua_logic.py (whose World helper it reuses). It proves
the file's own logic; the first real outputs come from the supervised bedroom.
"""

import pytest

pytest.importorskip("lupa")

from tests.test_blueprint_lua_logic import (  # noqa: E402
    BP, BUILD, DIG_OK, FINISH, FINISH_OK, SHELL, ZONE, World)

OFFICE = "office-room-v2"
O_SHELL, O_FLOOR, O_BUILD, O_ZONE, O_FINISH = (
    "office_room_v2_shell", "office_room_v2_floor", "office_room_v2_build",
    "office_room_v2_zone", "office_room_v2_finish")
OFFICE_FINISH_OK = ("Blueprint statistics:\n  Zones designated: 1\n  Zone tiles designated: 9\n"
                    "  Buildings designated: 1\n  Blueprints applied: 2\n")
INTERIOR = [(x, y) for x in (11, 12, 13) for y in (11, 12, 13)]


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def _built_shell(world, bp=BP, shell=SHELL):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    world.call("apply_phase", bp, shell, "Well", "false")
    world.carve_and_smooth()


def _phase(world, phase, handle="site-1"):
    r, err = world.call("site_status", handle, phase)
    assert err is None, err
    return r["phase"]


def _walk_no_coordinates(v):
    if isinstance(v, dict):
        for k, x in v.items():
            assert k not in {"x", "y", "z", "pos"}, k
            _walk_no_coordinates(x)
    elif isinstance(v, list):
        for x in v:
            _walk_no_coordinates(x)


def test_without_a_phase_status_is_todays_output(world):
    _built_shell(world)
    r, _ = world.call("site_status", "site-1")
    assert "phase" not in r and r["shell_done"] is True


def test_an_unknown_phase_is_an_error_not_a_guess(world):
    _built_shell(world)
    assert "no phase 'nope'" in world.call("site_status", "site-1", "nope")[1]
    assert "no phase" in world.call("site_status", "site-1", "bedroom_cell_v1_notes")[1]
    assert "PHASE must be" in world.call("site_status", "site-1", "../x")[1]


def test_office_shell_reads_done_without_its_floor_phase(world):
    _built_shell(world, OFFICE, O_SHELL)
    shell = _phase(world, O_SHELL)
    assert shell["done"] is True and shell["applied"] is True
    assert shell["cells"]["carve_required"] == 10 and shell["cells"]["smooth_required"] == 15
    # the floor phase's own 9 cells are rough: not done, and not applied
    floor = _phase(world, O_FLOOR)
    assert floor["done"] is False and floor["applied"] is False
    assert floor["cells"]["smooth_required"] == 9 and floor["cells"]["rough"] == 9
    # applied but the interior floor still rough: not done
    world.call("apply_phase", OFFICE, O_FLOOR, "site-1", "false")
    floor = _phase(world, O_FLOOR)
    assert floor["applied"] is True and floor["done"] is False
    # smoothing the floor completes it
    world.lua.execute("for x = 11, 13 do for y = 11, 13 do set_tile(x, y, 5, 'FLOOR', 'STONE', 'SMOOTH') end end")
    assert _phase(world, O_FLOOR)["done"] is True


def test_a_dig_phase_with_a_solid_carve_cell_is_not_done(world):
    _built_shell(world)
    world.lua.execute("set_tile(12, 12, 5, 'WALL', 'STONE', 'NORMAL')")
    p = _phase(world, SHELL)
    assert p["done"] is False and p["cells"]["carve_solid"] == 1


def test_furniture_reads_not_done_while_construction_is_pending(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    assert _phase(world, BUILD)["buildings"] == [{"kind": "bed", "complete": False}]
    assert _phase(world, BUILD)["done"] is False
    world.lua.execute("set_building(11, 11, 5, 7, 0, 3)")      # planned, stage 0 of 3
    p = _phase(world, BUILD)
    assert p["buildings"] == [{"kind": "bed", "complete": False}] and p["done"] is False
    world.lua.execute("set_building(11, 11, 5, 7, 2, 3)")
    assert _phase(world, BUILD)["done"] is False
    world.lua.execute("set_building(11, 11, 5, 7, 3, 3)")
    p = _phase(world, BUILD)
    assert p["buildings"] == [{"kind": "bed", "complete": True}] and p["done"] is True
    assert p["zone_required"] is False


def test_an_office_chair_reads_by_its_own_kind(world):
    _built_shell(world, OFFICE, O_SHELL)
    world.qf_output(OFFICE_FINISH_OK)
    world.call("apply_phase", OFFICE, O_FINISH, "site-1", "false")
    world.lua.execute("set_building(12, 12, 5, 9, 4, 4)")
    assert _phase(world, O_BUILD)["buildings"] == [{"kind": "chair", "complete": True}]


def test_zone_present_needs_every_zone_cell_covered(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    z = _phase(world, ZONE)
    assert z["zone_required"] is True and z["zone_present"] is False and z["done"] is False
    for x, y in INTERIOR[:-1]:
        world.lua.execute("set_zone(%d, %d, 5, true)" % (x, y))
    assert _phase(world, ZONE)["zone_present"] is False
    world.lua.execute("set_zone(13, 13, 5, true)")
    z = _phase(world, ZONE)
    assert z["zone_present"] is True and z["done"] is True


def test_a_meta_phase_reads_done_only_when_its_leaves_do(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    assert _phase(world, FINISH)["leaves"] == [ZONE, BUILD]
    assert _phase(world, FINISH)["done"] is False
    world.lua.execute("set_building(11, 11, 5, 7, 3, 3)")
    assert _phase(world, FINISH)["done"] is False        # zone still missing
    for x, y in INTERIOR:
        world.lua.execute("set_zone(%d, %d, 5, true)" % (x, y))
    p = _phase(world, FINISH)
    assert p["done"] is True and p["applied"] is True
    # the building goes away: not done again
    world.lua.execute("TILES['11,11,5'].building = nil")
    assert _phase(world, FINISH)["done"] is False


def test_an_unapplied_phase_is_never_done(world):
    _built_shell(world)
    for x, y in INTERIOR:
        world.lua.execute("set_zone(%d, %d, 5, true)" % (x, y))
    p = _phase(world, ZONE)
    assert p["applied"] is False and p["zone_present"] is True and p["done"] is False


def test_an_applied_meta_covers_its_leaf_phases(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    assert _phase(world, ZONE)["applied"] is True and _phase(world, BUILD)["applied"] is True


def test_a_failed_building_read_is_null_and_holds_done_false(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    world.lua.execute("set_building(11, 11, 5, 7, 3, 3); "
                      "TILES['11,11,5'].building.getBuildStage = function() error('boom') end")
    r, _ = world.call("site_status", "site-1", BUILD)
    assert r["phase"]["buildings"] == [{"kind": "bed", "complete": "\x00"}]
    assert r["phase"]["done"] is False and r["read_failures"]


def test_a_failed_zone_read_is_null_not_false(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    world.lua.execute("TILES['12,12,5'].zone_fails = true")
    z = _phase(world, ZONE)
    assert z["zone_present"] == "\x00" and z["done"] is False


def test_status_phase_never_returns_a_coordinate(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    r, _ = world.call("site_status", "site-1", FINISH)
    _walk_no_coordinates(r["phase"])


# ---- level, reservation, finish_plan ---------------------------------------

def test_reserve_reports_the_level_it_was_given(world):
    world.stone_block(10, 10)
    r, _ = world.call("reserve_site", BP, "p", "Well")
    assert r["level"] == 0


def test_level_flows_from_reserve_to_apply_and_the_stored_site(world):
    world.stone_block(10, 10)
    r, _ = world.call("reserve_site", BP, "p", "Well", "false", 0)
    assert r["level"] == 0
    world.qf_output(DIG_OK)
    a, _ = world.call("apply_phase", BP, SHELL, "res-1", "false")
    assert a["site"]["level"] == 0 and a["site"]["reservation"] == "res-1"
    later, _ = world.call("apply_phase", BP, FINISH, "site-1")
    assert later["site"]["level"] == 0
    rows, _ = world.call("list_sites")
    assert rows[0]["reservation"] == "res-1"


def test_apply_on_a_landmark_reports_the_level_and_a_plain_site_has_no_reservation(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    a, _ = world.call("apply_phase", BP, SHELL, "Well", "false")
    assert a["site"]["level"] == 0
    assert world.call("list_sites")[0][0]["reservation"] == "\x00"


def test_reserve_dry_run_and_refusal_carry_finish_plan(world):
    world.stone_block(10, 10)
    dry, _ = world.call("reserve_site", BP, "p", "Well")
    assert dry["finish_plan"]["required_cells"] == 15 and dry["finish_plan"]["smoothable"] == 15
    assert dry["finish_plan"]["blocked_total"] == 0
    world.call("reserve_site", BP, "p", "Well", "false")
    refused, _ = world.call("reserve_site", BP, "p2", "Well")
    assert refused["refused"] is True and refused["finish_plan"]["required_cells"] == 15


def test_reserve_finish_plan_reports_soil(world):
    world.stone_block(10, 10, soil_column=True)
    dry, _ = world.call("reserve_site", BP, "p", "Well")
    assert dry["finish_plan"]["blocked_by_material"] == {"SOIL": 5}


# ---- release ANY_PENDING ---------------------------------------------------

def _pending_site(world):
    world.stone_block(10, 10, open_sides="s")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    for x, y in [(11, 11), (12, 12)]:
        world.lua.eval("set_dig")(x, y, 5, 1)
    world.lua.execute('set_jobs({{job_type = "Dig", x = 11, y = 11, z = 5}})')


def test_release_without_any_pending_still_refuses_a_site_that_is_not_stalled(world):
    _pending_site(world)
    r, _ = world.call("release_site", "site-1", "false")
    assert r["released"] is False and "not stalled" in r["refused"]


def test_any_pending_withdraws_a_site_that_is_in_progress(world):
    _pending_site(world)
    dry, err = world.call("release_site", "site-1", None, "true")
    assert err is None and dry["dry_run"] is True and dry["any_pending"] is True
    assert dry["released"] is False and dry["dig_before"]["state"] == "in_progress"
    assert world.calls()[-1].startswith("quickfort undo templates/bedroom-cell-v1.csv")
    assert world.calls()[-1].endswith(" -d")

    def clear(cmd, args):
        for x, y in [(11, 11), (12, 12)]:
            world.lua.eval("set_dig")(x, y, 5, 0)
    world.lua.globals().ON_QF = clear
    real, _ = world.call("release_site", "site-1", "false", "true")
    assert real["released"] is True and real["site_forgotten"] is True
    assert real["skipped_phases"] == []
    assert not world.call("list_sites")[0]


def test_any_pending_never_undoes_a_zone_or_building_phase_and_names_it(world):
    _built_shell(world)
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    n = len(world.calls())
    r, _ = world.call("release_site", "site-1", "false", "true")
    assert r["skipped_phases"] == [FINISH]
    assert "not withdrawn" in r["cannot_undo"]
    undo_calls = [c for c in world.calls()[n:] if c.startswith("quickfort undo")]
    assert len(undo_calls) == 1 and "/" + SHELL in undo_calls[0]
    assert "/" + FINISH not in "".join(undo_calls)


def test_any_pending_false_is_not_any_pending(world):
    _pending_site(world)
    r, _ = world.call("release_site", "site-1", "false", "false")
    assert r["released"] is False and "not stalled" in r["refused"]
