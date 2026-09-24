"""Runs the REAL scripts/dfhack/df-overseer-blueprint.lua against a fake DFHack
world (tests/lua_stubs/dfhack_blueprint_world.lua) using lupa.

handoffs/2026-09-24-blueprint-hands.md. No DFHack process exists in the test
suite, so this is the closest offline thing to running the verb: it proves the
file's own logic (blueprint parse, footprint and room rectangle, the soil rule,
the order guard, statistics assessment including a swallowed #meta section,
site handles, the surface shim's swap and restore, and that nothing hands a
coordinate back). It proves nothing about real quickfort or real tiles: that is
the live check in the handoff Result.

lupa is a Lua 5.4 host and DFHack embeds 5.3; the file avoids the differences
(no assignment to a loop variable, no integer-division syntax). Skipped when
lupa is not installed (it is not a repo dependency).
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = Path(os.environ.get("BLUEPRINT_LUA_UNDER_TEST")
           or REPO_ROOT / "scripts" / "dfhack" / "df-overseer-blueprint.lua")
STUB = REPO_ROOT / "tests" / "lua_stubs" / "dfhack_blueprint_world.lua"
TEMPLATE = REPO_ROOT / "blueprints" / "templates" / "bedroom-cell-v1.csv"

SHELL, ZONE, BUILD, FINISH = (
    "bedroom_cell_v1_shell", "bedroom_cell_v1_zone", "bedroom_cell_v1_build", "bedroom_cell_v1_finish")
BP = "bedroom-cell-v1"


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if keys and all(isinstance(k, int) for k in keys) and keys == list(range(1, len(keys) + 1)):
        return [_py(v[k]) for k in keys]
    return {str(k): _py(v[k]) for k in keys}


class World:
    def __init__(self, tmp_path):
        guest = tmp_path / "guest"
        (guest / "dfhack-config" / "blueprints" / "templates").mkdir(parents=True)
        shutil.copy(TEMPLATE, guest / "dfhack-config" / "blueprints" / "templates" / TEMPLATE.name)
        self._old = os.getcwd()
        os.chdir(guest)
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB.read_text(encoding="utf-8"))
        load = self.lua.eval("function(src) return load(src, 'blueprint.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk  # (nil, syntax error)
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def close(self):
        os.chdir(self._old)

    def call(self, name, *args):
        r = self.g[name](*args)
        if isinstance(r, tuple):
            return _py(r[0]), (_py(r[1]) if len(r) > 1 else None)
        return _py(r), None

    def stone_block(self, x0, y0, z=5, soil_column=False, open_sides="nsew", hidden_below_north=False):
        """A 5x5 standing-stone block, with revealed walkable floor touching the
        sides named in open_sides (n, s, e, w). hidden_below_north reproduces
        the live site-1 pattern: only the north ring row is revealed, the other
        20 cells are unrevealed solid rock."""
        self.lua.eval(
            "function(x0, y0, z, soil, sides, hide) "
            "for x = x0, x0 + 4 do for y = y0, y0 + 4 do "
            "set_tile(x, y, z, 'WALL', (soil and x == x0) and 'SOIL' or 'STONE', 'NORMAL', "
            "{hidden = hide and y > y0}) end end "
            "for i = 0, 4 do "
            "if sides:find('n') then set_tile(x0 + i, y0 - 1, z, 'FLOOR', 'STONE') end "
            "if sides:find('s') then set_tile(x0 + i, y0 + 5, z, 'FLOOR', 'STONE') end "
            "if sides:find('w') then set_tile(x0 - 1, y0 + i, z, 'FLOOR', 'STONE') end "
            "if sides:find('e') then set_tile(x0 + 5, y0 + i, z, 'FLOOR', 'STONE') end "
            "end end"
        )(x0, y0, z, soil_column, open_sides, hidden_below_north)

    def qf_output(self, text):
        self.lua.execute("QF_OUTPUT = %r" % text)

    def calls(self):
        return [self.lua.eval("CALLS")[i] for i in range(1, len(self.lua.eval("CALLS")) + 1)]

    def carve_and_smooth(self):
        self.lua.execute(
            "for x = 10, 14 do for y = 10, 14 do "
            "local inner = (x >= 11 and x <= 13 and y >= 11 and y <= 13) or (x == 12 and y == 14) "
            "if inner then set_tile(x, y, 5, 'FLOOR', 'STONE') "
            "else set_tile(x, y, 5, 'WALL', 'STONE', 'SMOOTH') end end end"
        )


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


DIG_OK = "Blueprint statistics:\n  Tiles designated for digging: 25\n"
FINISH_OK = ("Blueprint statistics:\n  Zones designated: 1\n  Zone tiles designated: 9\n"
             "  Buildings designated: 1\n  Blueprints applied: 2\n")


def test_plan_reads_everything_from_the_csv(world):
    r, err = world.call("plan_template", BP)
    assert err is None
    assert r["footprint"] == {"width": 5, "height": 5}
    assert r["room"] == {"width": 3, "height": 3}
    assert r["finish_required_cells"] == 15
    phases = {p["label"]: p for p in r["phases"]}
    assert list(phases) == [SHELL, ZONE, BUILD, FINISH]
    assert phases[SHELL]["needs_dug_shell"] is False
    assert phases[ZONE]["needs_dug_shell"] and phases[BUILD]["needs_dug_shell"]
    assert phases[FINISH]["applies"] == [ZONE, BUILD]


def test_a_name_cannot_be_a_path_and_a_missing_blueprint_says_so(world):
    r, err = world.call("plan_template", "../etc")
    assert r is None and "bare identifier" in err
    r, err = world.call("plan_template", "nosuch")
    assert r is None and "no blueprint 'nosuch'" in err


def test_preview_asks_quickfort_with_dry_run_and_slash_label(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None
    assert world.calls() == ["quickfort run templates/bedroom-cell-v1.csv -c 10,10,5 -n /" + SHELL + " -d"]
    assert r["dry_run"] is True and r["ok"] is True and r["would_designate"] == 25
    assert r["finish_required_met"] is True
    assert r["finish_plan"]["smoothable"] == 15 and r["finish_plan"]["blocked_total"] == 0


def test_soil_walls_are_reported_by_material_never_silently_left(world):
    world.stone_block(10, 10, soil_column=True)   # the first column is soil: 5 of the 15 s cells
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["finish_required_met"] is False
    assert r["finish_plan"]["blocked_by_material"] == {"SOIL": 5}
    assert r["finish_plan"]["smoothable"] == 10
    assert "cannot smooth" in r["remedy"]


def test_a_building_on_a_smooth_cell_is_counted_because_quickfort_drops_it_uncounted(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(10, 10, 5, 'WALL', 'STONE', 'NORMAL', {occupied = true})")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["finish_plan"]["occupied_by_building"] == 1 and r["finish_required_met"] is False


def test_a_trees_smooth_slot_is_not_read_as_finished(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(10, 10, 5, 'WALL', 'TREE', 'SMOOTH')")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["finish_plan"]["already_finished"] == 0
    assert r["finish_plan"]["blocked_by_material"] == {"TREE": 1}


def test_hidden_cells_are_reported_not_assumed(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(10, 10, 5, 'WALL', 'STONE', 'NORMAL', {hidden = true})")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["finish_plan"]["hidden"] == 1 and r["finish_required_met"] is False


def test_site_errors(world):
    world.stone_block(10, 10)
    assert "phases are:" in world.call("preview_phase", BP, "nope", "Well")[1]
    assert "landmark not found" in world.call("preview_phase", BP, SHELL, "Nowhere")[1]
    assert "no candidate at rank 9" in world.call("preview_phase", BP, SHELL, "Well", None, 9)[1]
    # a phase that does not start by digging cannot find a new site
    assert "site-N handle" in world.call("preview_phase", BP, FINISH, "Well")[1]
    assert "no site 'site-4'" in world.call("preview_phase", BP, FINISH, "site-4")[1]


def test_a_real_apply_registers_a_handle_and_proves_designations_from_the_game(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    r, err = world.call("apply_phase", BP, SHELL, "Well", "false")
    assert err is None and r["dry_run"] is False
    assert r["site"]["handle"] == "site-1"
    # the fake quickfort claims 25 but marks nothing: the game read says so
    assert r["read_back"]["designations_landed"] is False
    listing, _ = world.call("list_sites")
    assert listing[0]["handle"] == "site-1" and listing[0]["phases_applied"] == [SHELL]
    # a default apply is a dry run and registers nothing
    world.stone_block(30, 10)
    r2, _ = world.call("apply_phase", BP, SHELL, "Well", None, None, 2)
    assert r2["dry_run"] is True
    assert len(world.call("list_sites")[0]) == 1


def test_order_guard_refuses_furniture_on_a_solid_shell_before_calling_quickfort(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    n_calls = len(world.calls())
    r, _ = world.call("apply_phase", BP, FINISH, "site-1", "false")
    assert r["blocked"] is True and r["ok"] is False
    assert "still solid" in r["blocked_reason"]
    assert len(world.calls()) == n_calls, "quickfort must not be called when the guard refuses"


def test_a_handle_rejects_site_finding_arguments(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    assert "only apply when SITE is a landmark" in world.call("apply_phase", BP, FINISH, "site-1", "false", 0)[1]


def test_finished_shell_then_furnishing_then_status(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    world.carve_and_smooth()
    world.qf_output(FINISH_OK)
    r, err = world.call("apply_phase", BP, FINISH, "site-1", "false")
    assert err is None and r["ok"] is True
    assert r["prerequisites"] == {"carve_cells": 10, "pending_designations": 0, "still_solid": 0}
    assert r["designated"] == {"dig_tiles": 0, "zones": 1, "buildings": 1}
    assert r["read_back"]["finish_state"]["already_finished"] == 15
    surf = r["read_back"]["surface"]
    assert surf["shim_restored"] is True
    assert surf["enclosure"]["w"] == 3 and surf["finish"]["h"] == 3   # the 3x3 room rectangle, via the shim
    assert "zone_id" not in surf["enclosure"] and "zone_id" not in surf["finish"]
    st, err = world.call("site_status", "site-1")
    assert err is None and st["shell_done"] is True and st["finish_required_met"] is True
    assert st["phases_applied"] == [SHELL, FINISH]


def test_a_swallowed_meta_section_is_a_problem(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    world.carve_and_smooth()
    world.qf_output("Blueprint statistics:\n  Zones designated: 1\n  Blueprints applied: 1\n")
    r, _ = world.call("preview_phase", BP, FINISH, "site-1")
    assert r["ok"] is False
    assert any("Blueprints applied: 1 of the 2" in p for p in r["quickfort"]["problems"])


def test_any_non_progress_counter_makes_the_run_not_ok(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK + "  Tiles that could not be designated for digging: 3\n")
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["ok"] is False
    assert r["quickfort"]["problems"] == ["Tiles that could not be designated for digging: 3"]


def test_nothing_designated_is_not_ok(world):
    world.stone_block(10, 10)
    world.qf_output("Blueprint statistics:\n")
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["ok"] is False and r["would_designate"] == 0


def test_no_result_carries_a_coordinate_key(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    outs = [
        world.call("preview_phase", BP, SHELL, "Well")[0],
        world.call("apply_phase", BP, SHELL, "Well", "false")[0],
        world.call("list_sites")[0],
        world.call("site_status", "site-1")[0],
        world.call("plan_template", BP)[0],
    ]

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                assert k not in {"x", "y", "z", "pos"}, k
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for o in outs:
        walk(o)
    assert "10,10,5" not in json.dumps(outs)


# ---------------------------------------------------------------------------
# handoffs/2026-09-24-blueprint-access.md: orientation, the access gate, stall
# ---------------------------------------------------------------------------

CARVE = [(x, y) for x in (11, 12, 13) for y in (11, 12, 13)] + [(12, 14)]   # site at (10,10)


def incident(world):
    """The live site-1 pattern: only the north ring row revealed (with open floor
    beyond it), the other 20 cells unrevealed solid rock, and the template's one
    entrance facing SOUTH, into the hidden side."""
    world.stone_block(10, 10, open_sides="n", hidden_below_north=True)
    world.qf_output(DIG_OK)


def test_the_incident_site_flips_to_face_the_reachable_side(world):
    incident(world)
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None
    assert r["site"]["orientation"] == "rot180"
    assert r["entrance_reachable"] is True and r["dig_can_start"] is True and r["ok"] is True
    tried = {t["orientation"]: t for t in r["site"]["orientations_tried"]}
    assert tried["none"]["entrance_reachable"] is False
    assert tried["rot180"]["entrance_reachable"] is True and tried["rot180"]["carve_cells_unreachable"] == 0
    assert world.calls() == ["quickfort run templates/bedroom-cell-v1.csv -c 14,14,5 -n /" + SHELL + " -t rotcw,rotcw -d"]


@pytest.mark.parametrize("side,orient,cursor,flag", [
    ("s", "none", "10,10,5", None),
    ("n", "rot180", "14,14,5", "rotcw,rotcw"),
    ("w", "rotcw", "14,10,5", "rotcw"),     # rotcw sends the south entrance to the west edge
    ("e", "rotccw", "10,14,5", "rotccw"),   # rotccw sends it to the east edge
])
def test_each_open_side_picks_the_orientation_that_faces_it(world, side, orient, cursor, flag):
    world.stone_block(10, 10, open_sides=side)
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["site"]["orientation"] == orient and r["dig_can_start"] is True
    call = world.calls()[-1]
    assert " -c " + cursor + " " in call
    assert (" -t " + flag + " " in call) if flag else (" -t " not in call)


def test_a_fully_hidden_site_is_refused_on_apply_and_flagged_in_preview(world):
    world.stone_block(10, 10, open_sides="")
    world.qf_output(DIG_OK)
    pv, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert pv["ok"] is False and pv["entrance_reachable"] is False and pv["dig_can_start"] is False
    assert "cannot start" in pv["would_strand"]
    n = len(world.calls())
    r, _ = world.call("apply_phase", BP, SHELL, "Well", "false")
    assert r["blocked"] is True and r["ok"] is False and r["stranded_override_used"] is False
    assert "cannot start" in r["blocked_reason"]
    assert len(world.calls()) == n, "quickfort must not run on a refused apply"
    assert not world.call("list_sites")[0], "a refused apply must register no site"


def test_the_override_is_explicit_named_and_reported(world):
    world.stone_block(10, 10, open_sides="")
    world.qf_output(DIG_OK)
    r, _ = world.call("apply_phase", BP, SHELL, "Well", "false", None, None, None, "true")
    assert r.get("blocked") is None and r["stranded_override_used"] is True
    assert r["site"]["handle"] == "site-1" and "cannot start" in r["would_strand"]
    # anything but an explicit true is not an override
    w2, _ = world.call("apply_phase", BP, SHELL, "Well", "false", None, None, None, "maybe")
    assert w2["blocked"] is True


def _stalled_site(world):
    world.stone_block(10, 10, open_sides="")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false", None, None, None, "true")
    for x, y in CARVE:
        world.lua.eval("set_dig")(x, y, 5, 1)


def test_status_names_a_stall_when_designations_have_no_job_and_no_walkable_neighbour(world):
    _stalled_site(world)
    st, err = world.call("site_status", "site-1")
    assert err is None
    assert st["stalled"] is True and st["dig"]["state"] == "stalled"
    assert st["dig"]["pending_dig_designations"] == 10 and st["dig"]["designations_without_a_job"] == 10
    assert st["dig"]["blind_no_walkable_neighbour"] == 10
    assert "release" in st["stall_remedy"]


def test_status_reads_in_progress_when_a_dig_job_exists(world):
    _stalled_site(world)
    world.lua.execute('set_jobs({{job_type = "Dig", x = 12, y = 14, z = 5}})')
    st, _ = world.call("site_status", "site-1")
    assert st["stalled"] is False and st["dig"]["state"] == "in_progress"
    assert st["dig"]["designations_with_a_job"] == 1


def test_startable_designations_without_a_job_stall_only_after_the_grace_period(world):
    world.stone_block(10, 10, open_sides="s")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    for x, y in CARVE:
        world.lua.eval("set_dig")(x, y, 5, 1)
    world.lua.execute("NOW = 1234 + 100")
    st, _ = world.call("site_status", "site-1")
    assert st["dig"]["state"] == "in_progress" and st["dig"]["startable_no_job_yet"] >= 1
    world.lua.execute("NOW = 1234 + 5000")
    st, _ = world.call("site_status", "site-1")
    assert st["dig"]["state"] == "stalled" and st["dig"]["blind_no_walkable_neighbour"] < 10
    assert st["dig"]["designations_with_a_job"] == 0


def test_no_pending_designations_is_none_pending_not_stalled(world):
    world.stone_block(10, 10, open_sides="s")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    st, _ = world.call("site_status", "site-1")
    assert st["dig"]["state"] == "none_pending" and st["stalled"] is False


def test_release_undoes_only_a_stalled_sites_dig_phases_in_its_orientation(world):
    _stalled_site(world)
    dry, err = world.call("release_site", "site-1")
    assert err is None and dry["dry_run"] is True and dry["released"] is False
    assert world.calls()[-1] == "quickfort undo templates/bedroom-cell-v1.csv -c 10,10,5 -n /" + SHELL + " -d"

    def clear(cmd, args):
        for x, y in CARVE:
            world.lua.eval("set_dig")(x, y, 5, 0)
    world.lua.globals().ON_QF = clear
    real, _ = world.call("release_site", "site-1", "false")
    assert real["released"] is True and real["site_forgotten"] is True
    assert "already dug out" in real["cannot_undo"]
    assert not world.call("list_sites")[0]


def test_release_refuses_a_site_that_is_not_stalled(world):
    world.stone_block(10, 10, open_sides="s")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    n = len(world.calls())
    r, _ = world.call("release_site", "site-1", "false")
    assert r["released"] is False and "not stalled" in r["refused"]
    assert len(world.calls()) == n


def test_release_will_not_undo_a_zone_or_building_phase(world):
    world.stone_block(10, 10, open_sides="s")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")
    world.carve_and_smooth()
    world.qf_output(FINISH_OK)
    world.call("apply_phase", BP, FINISH, "site-1", "false")
    r, _ = world.call("release_site", "site-1", "false")
    assert r["released"] is False and "not a dig phase" in r["refused"]


def test_a_second_dig_on_a_stored_site_is_gated_by_its_stored_orientation(world):
    incident(world)
    world.call("apply_phase", BP, SHELL, "Well", "false")     # flips to rot180, registers it
    listing, _ = world.call("list_sites")
    assert listing[0]["handle"] == "site-1"
    r, _ = world.call("preview_phase", BP, SHELL, "site-1")
    assert r["site"]["orientation"] == "rot180" and r["dig_can_start"] is True
    assert " -t rotcw,rotcw" in world.calls()[-1]
