"""Circulation hands (red team B2 and B3), blueprint verb side.

Runs the REAL scripts/dfhack/df-overseer-blueprint.lua (and the real parse,
reservations and hazard leaves) under lupa, with the fake world of
test_blueprint_lua_logic.py. Proves:

  B2  the verb REFUSES a multi-level CSV (`#>` / `#<`, a meta repeating up or
      down) with a clear message instead of silently reading it as an empty
      row; a template reservation marks its entrance tile a portal and hangs
      on a tile-set corridor reservation, one room per portal.
  B3  a generated blueprint (registered by name, held in persistent state) is
      planned, previewed and applied through quickfort.apply_blueprint with
      NO file and NO command-line quickfort run, and every existing safety
      check (siting hazard, reservations, order guard, read-back) applies to
      it exactly as to a CSV.

lupa-skipped when not installed.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

from tests.test_blueprint_lua_logic import BP, World, _no_coordinate_keys  # noqa: E402

GEN = "gen-room-a"
SHELL_ROWS = [
    "s,s,s,s,s,#",
    "s,d,d,d,s,#",
    "s,d,d,d,s,#",
    "s,d,d,d,s,#",
    "s,s,d,s,s,#",
    "#,#,#,#,#,#",
]
GEN_CSV = (
    "#dig label(gen_shell) generated shell\n" + "\n".join(SHELL_ROWS) + "\n\n"
    "#build label(gen_build) one bed\n"
    "`,`,`,`,`,#\n`,b,`,`,`,#\n`,`,`,`,`,#\n`,`,`,`,`,#\n`,`,`,`,`,#\n#,#,#,#,#,#\n"
)
SHELL = "gen_shell"
BUILD = "gen_build"
API_DIG = [("Tiles designated for digging", 25)]


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def api_calls(world):
    c = world.lua.eval("API_CALLS")
    return [] if c is None else [c[i] for i in range(1, len(c) + 1)]


def set_api_stats(world, stats):
    t = world.lua.table_from([world.lua.table_from(list(s)) for s in stats])
    world.lua.globals().API_STATS = t


def write_template(name, text):
    d = Path("dfhack-config") / "blueprints" / "templates"
    (d / f"{name}.csv").write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# B2: multi-level CSV is refused, not misread
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("marker", ["#>", "#<", "#> 2", "#<  3", "# >"])
def test_a_level_change_line_is_refused_with_a_clear_message(world, marker):
    text = "#dig label(up) two levels\nd,d,#\nd,d,#\n" + marker + "\nd,d,#\nd,d,#\n"
    write_template("two-level", text)
    r, err = world.call("plan_template", "two-level")
    assert r is None
    assert "changes levels" in err and "ONE level" in err


def test_the_same_blueprint_without_the_level_line_still_plans(world):
    write_template("one-level", "#dig label(a) one\nd,d,#\nd,d,#\n")
    r, err = world.call("plan_template", "one-level")
    assert err is None and r["footprint"] == {"width": 2, "height": 2}


def test_a_meta_that_repeats_up_is_refused(world):
    write_template("rep", "#dig label(a) one\nd,d,#\n\n#meta label(m) stack\n/a repeat(up 3),#\n")
    r, err = world.call("plan_template", "rep")
    assert r is None and "changes levels" in err


def test_every_verb_that_loads_a_blueprint_refuses_it(world):
    write_template("two-level", "#dig label(up) x\nd,d,#\n#>\nd,d,#\n")
    world.stone_block(10, 10)
    assert "changes levels" in world.call("preview_phase", "two-level", "up", "Well")[1]
    assert "changes levels" in world.call("reserve_site", "two-level", "p", "Well", "false")[1]


def test_deployed_templates_still_load(world):
    r, err = world.call("plan_template", BP)
    assert err is None and r["footprint"] == {"width": 5, "height": 5}


# ---------------------------------------------------------------------------
# B2: a room hung on a corridor through its portal
# ---------------------------------------------------------------------------


def test_template_reservation_marks_its_entrance_as_a_portal_and_a_room_role(world):
    world.stone_block(10, 10)
    world.call("reserve_site", BP, "bedroom", "Well", "false")
    rs = world.lua.eval("function() return reqscript('df-overseer-reservations') end")()
    rec = rs.get_raw("res-1")
    assert rec.role == "room"
    portals = [k for k in rec.portal_cells.keys()]
    assert portals == ["2,4"]            # column 3 of row 5: the entrance gap


def test_a_room_hangs_on_a_corridor_tile_set_and_a_second_room_is_refused(world):
    world.stone_block(10, 10)       # the room stands at (10..14, 10..14), entrance (12,14)
    rs = world.lua.eval("function() return reqscript('df-overseer-reservations') end")()
    # a corridor along y=15, whose wall row y=14 runs under the room's ring
    tiles = {}
    for x in range(8, 17):
        tiles[f"{x},15,5"] = "strict"
        tiles[f"{x},14,5"] = "wall"
        tiles[f"{x},16,5"] = "wall"
    # the corridor must not claim the room's own ring tiles as walls it shares
    # except as walls: ring tiles (10..14,14) are wall in both -> allowed;
    # the entrance (12,14) is wall for the corridor and portal for the room.
    handle = rs.create_tile_set(world.lua.table_from(
        {"tiles": world.lua.table_from(tiles), "role": "corridor", "purpose": "spine"}))
    assert handle == "res-1"
    r, err = world.call("reserve_site", BP, "bedroom one", "Well", "false")
    assert err is None, err
    assert r.get("refused") is not True, r
    assert r["handle"] == "res-2"
    # a second identical room at the same place would share every tile: refused
    world.stone_block(10, 10)
    r2, _ = world.call("reserve_site", BP, "bedroom two", "Well", "false")
    assert r2.get("refused") is True


def test_reserve_tile_set_checks_the_sharing_rule_and_hides_coordinates(world):
    world.stone_block(10, 10)
    world.call("reserve_site", BP, "bedroom", "Well", "false")
    clash = world.lua.table_from({"12,12,5": "strict"})
    r, err = world.call("reserve_tile_set", "route", "corridor", clash, "false")
    assert err is None and r["refused"] is True
    assert [c["handle"] for c in r["conflicts"]] == ["res-1"]
    _no_coordinate_keys(r)
    free = world.lua.table_from({"30,30,5": "strict", "31,30,5": "strict"})
    r, _ = world.call("reserve_tile_set", "route", "corridor", free, "false")
    assert r["handle"] == "res-2" and r["tile_count"] == 2
    _no_coordinate_keys(r)


def test_reserve_tile_set_respects_the_aquifer_policy(world):
    world.lua.execute("set_tile(30, 30, 5, 'WALL', 'STONE', 'NORMAL', {aquifer = true})")
    r, _ = world.call("reserve_tile_set", "route", "corridor", world.lua.table_from({"30,30,5": "strict"}), "false")
    assert r["refused"] is True and "aquifer" in r["blocked_reason"]


# ---------------------------------------------------------------------------
# B3: a generated blueprint through quickfort.apply_blueprint
# ---------------------------------------------------------------------------


def register(world, name=GEN, csv=GEN_CSV):
    return world.call("register_generated", name, csv)


def test_register_then_plan_reads_the_generated_sections(world):
    r, err = register(world)
    assert err is None and r["registered"] is True
    assert r["footprint"] == {"width": 5, "height": 5}
    assert [p["label"] for p in r["phases"]] == [SHELL, BUILD]
    plan, err = world.call("plan_template", GEN)
    assert err is None and plan["footprint"] == {"width": 5, "height": 5}
    assert [p["label"] for p in plan["phases"]] == [SHELL, BUILD]


@pytest.mark.parametrize("name", ["room-a", "gen-", "gen-a/b", "gen-../x", "GEN-a"])
def test_a_generated_name_must_start_gen_and_be_a_bare_identifier(world, name):
    r, err = register(world, name=name)
    assert r is None and "gen-" in err


def test_a_generated_name_cannot_shadow_a_deployed_template(world):
    write_template("gen-taken", "#dig label(a) x\nd,d,#\n")
    r, err = register(world, name="gen-taken")
    assert r is None and "collides" in err


def test_register_refuses_a_multi_level_blueprint(world):
    r, err = register(world, csv="#dig label(a) x\nd,d,#\n#>\nd,d,#\n")
    assert r is None and "changes levels" in err


def test_register_refuses_a_meta_section_and_unknown_modes(world):
    r, err = register(world, csv="#dig label(a) x\nd,d,#\n\n#meta label(m) y\n/a,#\n")
    assert r is None and "meta" in err


def test_register_is_idempotent_and_refuses_a_conflicting_rewrite_when_in_use(world):
    assert register(world)[1] is None
    assert register(world)[1] is None                       # same text: fine
    world.stone_block(10, 10)
    set_api_stats(world, API_DIG)
    world.call("apply_phase", GEN, SHELL, "Well", "false")  # a site now uses it
    r, err = register(world, csv="#dig label(gen_shell) x\nd,d,#\n")
    assert r is None and "already registered" in err


def test_preview_goes_through_the_api_dry_run_and_never_the_command_line(world):
    register(world)
    world.stone_block(10, 10)
    set_api_stats(world, API_DIG)
    r, err = world.call("preview_phase", GEN, SHELL, "Well")
    assert err is None, err
    assert world.calls() == [], "no quickfort command line for a generated blueprint"
    calls = api_calls(world)
    assert len(calls) == 1
    c = calls[0]
    assert c.mode == "dig" and c.dry_run is True and c.command == "run"
    assert (c.pos.x, c.pos.y, c.pos.z) == (10, 10, 5)
    assert c.data[0][1][1] == "d" and c.data[0][0][0] == "s" and c.data[0][4][2] == "d"
    assert r["dry_run"] is True and r["ok"] is True and r["would_designate"] == 25
    assert r["finish_plan"]["smoothable"] == 15
    _no_coordinate_keys(r)


def test_an_api_error_is_reported_not_swallowed(world):
    register(world)
    world.stone_block(10, 10)
    world.lua.execute("API_ERROR = 'boom'")
    r, _ = world.call("preview_phase", GEN, SHELL, "Well")
    assert r["ok"] is False and r["quickfort"]["ran"] is False and "boom" in r["quickfort"]["error"]


def test_a_non_progress_counter_makes_a_generated_run_not_ok(world):
    register(world)
    world.stone_block(10, 10)
    set_api_stats(world, API_DIG + [("Tiles outside map boundary", 2)])
    r, _ = world.call("preview_phase", GEN, SHELL, "Well")
    assert r["ok"] is False and any("outside map" in p for p in r["quickfort"]["problems"])


def test_a_generated_blueprint_is_never_rotated(world):
    register(world)
    world.stone_block(10, 10, open_sides="e")      # only the east side is open
    set_api_stats(world, API_DIG)
    r, err = world.call("preview_phase", GEN, SHELL, "Well")
    assert err is None
    assert r["site"]["orientation"] == "none"
    assert [t["orientation"] for t in r["site"]["orientations_tried"]] == ["none"]


def test_the_siting_hazard_policy_applies_to_generated_data(world):
    register(world)
    world.stone_block(10, 10)
    world.lua.execute("set_tile(9, 12, 5, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")
    set_api_stats(world, API_DIG)
    r, _ = world.call("preview_phase", GEN, SHELL, "Well")
    assert r["blocked"] is True and r["siting_hazard"]["kind"] == "aquifer"
    assert api_calls(world) == []


def test_reservations_apply_to_generated_data(world):
    register(world)
    world.stone_block(10, 10)
    world.call("reserve_site", BP, "planned bedroom", "Well", "false")
    set_api_stats(world, API_DIG)
    r, _ = world.call("apply_phase", GEN, SHELL, "Well", "false")
    assert r["blocked"] is True and r["reservation_conflict"]["handle"] == "res-1"
    assert api_calls(world) == []


def test_a_generated_blueprint_can_be_reserved_and_carved_as_the_holder(world):
    register(world)
    world.stone_block(10, 10)
    r, err = world.call("reserve_site", GEN, "generated room", "Well", "false")
    assert err is None and r["handle"] == "res-1"
    set_api_stats(world, API_DIG)
    r, err = world.call("apply_phase", GEN, SHELL, "res-1", "false")
    assert err is None and r["ok"] is True and r["site"]["handle"] == "site-1"
    assert len(api_calls(world)) == 1 and api_calls(world)[0].dry_run is False


def test_order_guard_and_read_back_apply_to_generated_data(world):
    register(world)
    world.stone_block(10, 10)
    set_api_stats(world, API_DIG)
    r, _ = world.call("apply_phase", GEN, SHELL, "Well", "false")
    assert r["read_back"]["designations_landed"] is False     # the fake marks nothing
    n = len(api_calls(world))
    r, _ = world.call("apply_phase", GEN, BUILD, "site-1", "false")
    assert r["blocked"] is True and "still solid" in r["blocked_reason"]
    assert len(api_calls(world)) == n, "the API must not be called when the guard refuses"


def test_release_undoes_a_generated_dig_through_the_api(world):
    register(world)
    world.stone_block(10, 10)
    set_api_stats(world, API_DIG)
    world.call("apply_phase", GEN, SHELL, "Well", "false")
    # a stalled site: designations the stub never turned into a job
    world.lua.execute("NOW = 1234 + 5000")
    r, _ = world.call("release_site", "site-1", "true", "true")     # DRY_RUN, ANY_PENDING
    cmds = [c.command for c in api_calls(world)]
    assert cmds[-1] == "undo" and api_calls(world)[-1].dry_run is True
    assert r["dry_run"] is True
