"""C3 placement access gate (register 2026-10-08 D2 and D7).

Part 1 runs the REAL scripts/dfhack/df-overseer-access.lua (pure rules) with the
REAL generated df-overseer-roomkinds.lua. Part 2 runs the REAL
df-overseer-blueprint.lua against the fake world (preview / apply / reserve).

What is implemented is the ENTRANCE-CELL check: each entrance of a new room may
not open into a private room's footprint (D7), and must satisfy the kind's
access rule (D2). It is not a planned-state graph search. These tests prove the
logic offline; the live dry run is in the handoff report.
"""

import re
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

from test_blueprint_lua_logic import BP, DIG_OK, SHELL, World, _py  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts" / "dfhack"


# ---------------------------------------------------------------------------
# Part 1: the pure rules
# ---------------------------------------------------------------------------

@pytest.fixture
def rules():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        function load_mod(path, name)
          local f = io.open(path, "r"); local src = f:read("*a"); f:close()
          local env = setmetatable({}, {__index = _G})
          assert(load(src, name, "t", env))()
          return env
        end
    """)
    lua.execute("ROOMKINDS = load_mod(%r, 'roomkinds')" % str(SCRIPTS / "df-overseer-roomkinds.lua"))
    lua.execute("""
        function reqscript(n)
          if n == "df-overseer-roomkinds" then return ROOMKINDS end
          error("unexpected reqscript " .. n)
        end
        ACCESS = load_mod(%r, 'access')
    """ % str(SCRIPTS / "df-overseer-access.lua"))

    def check(kind, portals, others, z=5):
        lua.globals().ARGS = lua.table_from({
            "placement": lua.table_from({"kind": kind, "z": z, "portals": lua.table_from([
                lua.table_from({"x": p[0], "y": p[1], "outward": lua.table_from(
                    [lua.table_from({"x": o[0], "y": o[1]}) for o in p[2]])}) for p in portals])}),
            "others": lua.table_from([lua.table_from(
                {k: v for k, v in o.items()}) for o in others]),
        })
        return _py(lua.eval("ACCESS.check_entrances(ARGS.placement, ARGS.others)"))

    check.lua = lua
    return check


def room(name, kind, x1, y1, x2, y2, z=5):
    return {"name": name, "kind": kind, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "z": z}


def test_bedroom_entrance_into_another_bedroom_is_refused(rules):
    v = rules("bedroom", [(12, 14, [(12, 15)])], [room("Bedroom #24", "bedroom", 10, 15, 14, 19)])
    assert v["verdict"] == "refused"
    assert v["refusals"][0]["rule"] == "private_pass_through"
    assert "Bedroom #24" in v["refusals"][0]["text"]


def test_clean_corridor_is_clear(rules):
    v = rules("bedroom", [(12, 14, [(12, 15)])], [room("Bedroom #24", "bedroom", 20, 15, 24, 19)])
    assert v["verdict"] == "clear" and v["refusals"] == []


def test_a_non_private_room_may_not_open_into_a_private_one_either(rules):
    # D7: a room reached through a private room is the bad case, whatever the new kind
    v = rules("dining_hall", [(1, 1, [(1, 0)])], [room("Bedroom #3", "bedroom", 0, -4, 4, 0)])
    assert v["verdict"] == "refused"
    assert v["refusals"][0]["rule"] == "private_pass_through"


def test_office_is_corridor_only_so_opening_into_a_dining_hall_is_refused(rules):
    v = rules("office", [(1, 1, [(1, 0)])], [room("Dining Hall", "dining_hall", 0, -6, 6, 0)])
    assert v["verdict"] == "refused"
    assert v["refusals"][0]["rule"] == "access"
    assert "corridor" in v["refusals"][0]["text"]


def test_opens_onto_allows_listed_kinds_only(rules):
    ok = rules("tavern", [(1, 1, [(1, 0)])], [room("Dining Hall", "dining_hall", 0, -6, 6, 0)])
    bad = rules("tavern", [(1, 1, [(1, 0)])], [room("Hospital", "hospital", 0, -6, 6, 0)])
    assert ok["verdict"] == "clear"
    assert bad["verdict"] == "refused" and "opens_onto" in bad["refusals"][0]["text"]


def test_any_access_ignores_non_private_rooms_but_never_private_ones(rules):
    barracks = rules("tomb", [(1, 1, [(1, 0)])], [room("Barracks #1", "barracks", 0, -6, 6, 0)])
    bedroom = rules("tomb", [(1, 1, [(1, 0)])], [room("Bedroom #1", "bedroom", 0, -6, 6, 0)])
    assert barracks["verdict"] == "clear"
    assert bedroom["verdict"] == "refused"


def test_another_level_is_not_a_hit(rules):
    v = rules("bedroom", [(12, 14, [(12, 15)])], [room("Bedroom #24", "bedroom", 10, 15, 14, 19, z=4)])
    assert v["verdict"] == "clear"


def test_an_unclassified_kind_applies_no_rule_and_says_so(rules):
    v = rules("spaceport", [(1, 1, [(1, 0)])], [room("Bedroom #3", "bedroom", 0, -4, 4, 0)])
    assert v["verdict"] == "unclassified"


def test_refusal_text_names_rooms_and_the_rule_never_a_coordinate(rules):
    v = rules("bedroom", [(12, 14, [(12, 15)])], [room("Bedroom #24", "bedroom", 10, 15, 14, 19)])
    text = v["refusals"][0]["text"]
    assert not re.search(r"\d+\s*,\s*\d+", text)
    assert "private room" in text


# ---------------------------------------------------------------------------
# Part 2: the gate inside blueprint preview / apply / reserve
# ---------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    w.lua.execute("ZONES = {}")
    yield w
    w.close()


def set_zones(world, zones):
    world.lua.globals().ZONES_PY = world.lua.table_from(
        [world.lua.table_from(z) for z in zones])
    world.lua.execute("ZONES = ZONES_PY")


def bedroom_zone(zid, x1, y1, x2, y2):
    return {"id": zid, "kind": "Bedroom", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "z": 5}


# the block sits at x10..14, y10..14; its entrance is mid-edge on whichever
# side the chosen orientation puts it. A bedroom zone (3x3 interior, wall ring
# around it) on each side covers the tile just outside that side's entrance.
SOUTH = bedroom_zone(24, 11, 16, 13, 18)
NORTH = bedroom_zone(25, 11, 4, 13, 8)
WEST = bedroom_zone(26, 4, 11, 8, 13)
EAST = bedroom_zone(27, 16, 11, 20, 13)


def test_entrance_into_a_bedrooms_wall_is_refused_and_names_it(world):
    world.stone_block(10, 10)
    set_zones(world, [SOUTH, NORTH, WEST, EAST])
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None, err
    assert r["blocked"] is True and r["ok"] is False
    assert "Bedroom #24" in r["blocked_reason"] or "Bedroom #25" in r["blocked_reason"]
    assert "private room" in r["blocked_reason"]
    assert not re.search(r"\d+\s*,\s*\d+", r["blocked_reason"])
    assert r["placement_access"]["verdict"] == "refused"
    assert world.calls() == [], "quickfort must not run on a refused placement"


def test_a_real_apply_is_refused_the_same_way_and_designates_nothing(world):
    world.stone_block(10, 10)
    set_zones(world, [SOUTH, NORTH, WEST, EAST])
    world.qf_output(DIG_OK)
    r, err = world.call("apply_phase", BP, SHELL, "Well", "false")
    assert err is None, err
    assert r["blocked"] is True
    assert world.calls() == []
    sites, _ = world.call("list_sites")
    assert sites == []


def test_a_clean_orientation_is_chosen_over_a_refused_one(world):
    world.stone_block(10, 10)
    set_zones(world, [SOUTH])     # only the default orientation's entrance is bad
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None, err
    assert not r.get("blocked")
    assert r["site"]["orientation"] != "none"
    assert r["placement_access"]["verdict"] == "clear"
    tried = {t["orientation"]: t["placement_access"] for t in r["site"]["orientations_tried"]}
    assert tried["none"] == "refused"


def test_a_clean_spot_is_not_refused(world):
    world.stone_block(10, 10)
    far = bedroom_zone(40, 50, 50, 52, 52)
    set_zones(world, [far])
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None, err
    assert not r.get("blocked")
    assert r["placement_access"]["verdict"] == "clear"
    assert r["placement_access"]["rooms_considered"] == 1


def test_reserve_is_gated_too(world):
    world.stone_block(10, 10)
    set_zones(world, [SOUTH, NORTH, WEST, EAST])
    r, err = world.call("reserve_site", BP, "planned bedroom", "Well", "false")
    assert err is None, err
    assert r["refused"] is True and "private room" in r["blocked_reason"]
    listing, _ = world.call("list_reservations")
    assert listing == []


def test_later_phases_of_an_existing_site_are_never_gated(world):
    world.stone_block(10, 10)
    world.qf_output(DIG_OK)
    r, err = world.call("apply_phase", BP, SHELL, "Well", "false")
    assert err is None and r["ok"] is True
    # now bedrooms appear all around the existing site; reading, previewing a
    # later phase and listing must not be blocked by the new-placement rule
    set_zones(world, [SOUTH, NORTH, WEST, EAST])
    r2, err2 = world.call("preview_phase", BP, "bedroom_cell_v1_zone", "site-1")
    assert err2 is None, err2
    assert "placement_access" not in r2
    sites, _ = world.call("list_sites")
    assert len(sites) == 1


def test_unreadable_zones_are_reported_not_treated_as_a_refusal(world):
    world.stone_block(10, 10)
    world.lua.execute("df.global.world.buildings = nil")
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None, err
    assert not r.get("blocked")
    assert r["placement_access"]["zones_unreadable"] is True


def test_corridor_only_office_into_a_dining_hall_is_refused(world):
    world.stone_block(10, 10)
    dining = lambda i, *r: {"id": i, "kind": "DiningHall", "x1": r[0], "y1": r[1], "x2": r[2], "y2": r[3], "z": 5}
    set_zones(world, [dining(30, 11, 16, 13, 18), dining(31, 11, 4, 13, 8),
                      dining(32, 4, 11, 8, 13), dining(33, 16, 11, 20, 13)])
    plan, _ = world.call("plan_template", "office-room-v2")
    label = plan["phases"][0]["label"]
    r, err = world.call("preview_phase", "office-room-v2", label, "Well")
    assert err is None, err
    assert r["blocked"] is True
    assert "must open onto a corridor" in r["blocked_reason"]
    assert r["placement_access"]["refusals"][0]["rule"] == "access"
