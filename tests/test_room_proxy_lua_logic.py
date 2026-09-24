"""Runs the REAL scripts/dfhack/df-overseer-nobles.lua (requirements) and
df-overseer-zone.lua (zone contents) against the fake DFHack world in
tests/lua_stubs/dfhack_zone_world.lua, extended here with zone footprints and
buildings, using lupa.

handoffs/2026-09-24-room-proxy-fix.md. The incident: getRoomDescription
returned "" on the Manager's owned office (a chair inside it), and
nobles.requirements read that as not_met while the game's own nobles screen
accepted the room. These tests prove the file's own logic: an empty
description alone never yields not_met; not_met needs independent evidence;
one shared helper answers "is furniture inside this zone". They prove nothing
about what the real getRoomDescription or findAtTile return: that is the live
check in the handoff Result.

NOBLES_LUA_OVERRIDE (env var, a path) points the requirements tests at another
copy of nobles.lua, used once to show the incident test fails on the pre-change
script.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import os
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
ZONE_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-zone.lua"
NOBLES_LUA = Path(os.environ.get("NOBLES_LUA_OVERRIDE") or REPO_ROOT / "scripts" / "dfhack" / "df-overseer-nobles.lua")
STUB = REPO_ROOT / "tests" / "lua_stubs" / "dfhack_zone_world.lua"

# Additions to the zone stub: zone footprints, a building_type enum, tile-keyed
# buildings and findAtTile (which, like the real one, never returns a zone).
EXTRA = r"""
local function enum2(names) local t = {} for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end return t end
df.building_type = enum2({"Chair", "Bed", "Table", "Coffin", "Workshop"})
function xyz2pos(x, y, z) return {x = x, y = y, z = z} end
TILE_BLD = {}
FIND_FAILS = false
function set_extent(id, x1, y1, x2, y2, z)
  local b = BUILDINGS[id]
  b.x1, b.y1, b.x2, b.y2, b.z = x1, y1, x2, y2, z
end
function add_building(id, kind, tiles, exists, stage, max_stage, items)
  local n = items or 0
  local b = {id = id, _type = df.building_type[kind], flags = {exists = exists ~= false},
    contained_items = setmetatable({}, {__len = function() return n end}),
    _stage = stage or 1, _max = max_stage or 1}
  function b:getType() return self._type end
  function b:getBuildStage() return self._stage end
  function b:getMaxBuildStage() return self._max end
  BUILDINGS[id] = b
  for _, t in ipairs(tiles) do TILE_BLD[t[1] .. "," .. t[2] .. "," .. t[3]] = b end
  return b
end
dfhack.buildings.findAtTile = function(pos)
  if FIND_FAILS then error("findAtTile boom") end
  return TILE_BLD[pos.x .. "," .. pos.y .. "," .. pos.z]
end
"""


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if keys and all(isinstance(k, int) for k in keys) and keys == list(range(1, len(keys) + 1)):
        return [_py(v[k]) for k in keys]
    return {str(k): _py(v[k]) for k in keys}


class World:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB.read_text(encoding="utf-8"))
        self.lua.execute(EXTRA)
        # reqscript returns a module env for the real zone.lua, {} for the rest.
        self.lua.globals().ZONE_SRC = ZONE_LUA.read_text(encoding="utf-8")
        self.lua.execute(
            """
            local zone_env
            function reqscript(n)
              if n ~= 'df-overseer-zone' then return {} end
              if not zone_env then
                zone_env = setmetatable({}, {__index = _G})
                local chunk = assert(load(ZONE_SRC, 'zone.lua', 't', zone_env))
                chunk()
              end
              return zone_env
            end
            """
        )
        self.zone = self.lua.eval("reqscript('df-overseer-zone')")
        src = NOBLES_LUA.read_text(encoding="utf-8").replace("local function requirements(", "function requirements(")
        load = self.lua.eval("function(src) return load(src, 'nobles.lua') end")
        chunk = load(src)
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def run(self, code):
        return self.lua.execute(code)

    def eval(self, code):
        return _py(self.lua.eval(code))

    def requirements(self, code="MANAGER"):
        r = self.g["requirements"](code)
        if isinstance(r, tuple):
            r = r[0]
        return _py(r)

    def contents(self, zone_id):
        res = self.zone["zone_contents"](zone_id)
        if isinstance(res, tuple):
            res, err = res
            if res is None:
                return {"error": err}
        return _py(res)


@pytest.fixture
def w():
    world = World()
    world.run("add_unit(345)")
    # Zone 11: an Office owned by the Manager (unit 345), a 3x3 footprint.
    world.run("add_zone(11, 'Office', 345); set_extent(11, 10, 20, 12, 22, 5)")
    world.run("set_positions({{code='MANAGER', id=1, required_office=1, holder_unit=345}})")
    return world


def office(r):
    return r["assignments"][0]["room_value"]["Office"]


# --- requirements ----------------------------------------------------------

def test_empty_description_with_furniture_inside_is_cannot_tell(w):
    """THE INCIDENT: owned office, a chair inside, description empty. The old
    script said not_met; the game's nobles screen accepted the room."""
    w.run("add_building(50, 'Chair', {{11, 21, 5}}, true, 1, 1, 1); ROOM_DESC = ''")
    r = w.requirements()
    o = office(r)
    assert o["status"] == "cannot_tell"
    assert "contain qualifying furniture" in o["detail"]
    assert "arbiter" in o["detail"]
    assert not r["read_failures"]


def test_empty_description_with_no_furniture_is_not_met(w):
    w.run("ROOM_DESC = ''")
    o = office(w.requirements())
    assert o["status"] == "not_met"
    assert o["zone_ids"] == [11]


def test_a_wrong_kind_of_furniture_is_not_a_chair(w):
    w.run("add_building(51, 'Table', {{10, 20, 5}}); ROOM_DESC = ''")
    assert office(w.requirements())["status"] == "not_met"


def test_furniture_outside_the_footprint_does_not_count(w):
    w.run("add_building(52, 'Chair', {{13, 20, 5}, {10, 20, 6}}); ROOM_DESC = ''")
    assert office(w.requirements())["status"] == "not_met"


def test_nonempty_description_is_met(w):
    w.run("ROOM_DESC = 'a Meager Office'")
    o = office(w.requirements())
    assert o["status"] == "met"
    assert o["zone_ids"] == [11]


def test_no_owned_zone_is_not_met(w):
    w.run("add_unit(400); set_positions({{code='MANAGER', id=1, required_office=1, holder_unit=400}})")
    o = office(w.requirements())
    assert o["status"] == "not_met"
    assert "owns no Office zone" in o["detail"]


def test_failed_description_read_with_furniture_is_cannot_tell_with_failures(w):
    w.run("add_building(50, 'Chair', {{11, 21, 5}}); DESC_FAILS = true")
    r = w.requirements()
    assert office(r)["status"] == "cannot_tell"
    assert any("getRoomDescription failed" in f for f in r["read_failures"])
    assert "getRoomDescription failed" in w.eval("ERRS") or "read failure" in w.eval("ERRS")


def test_failed_contents_read_is_cannot_tell_never_not_met(w):
    w.run("ROOM_DESC = ''; FIND_FAILS = true")
    r = w.requirements()
    assert office(r)["status"] == "cannot_tell"
    assert any("findAtTile failed" in f for f in r["read_failures"])


def test_an_unbuilt_chair_is_still_cannot_tell_not_not_met(w):
    """Conservative: only ABSENCE of the furniture kind is independent evidence."""
    w.run("add_building(50, 'Chair', {{11, 21, 5}}, false, 0, 3); ROOM_DESC = ''")
    o = office(w.requirements())
    assert o["status"] == "cannot_tell"
    assert "0 complete" in o["detail"]


def test_one_zone_with_description_wins_over_an_empty_one(w):
    w.run("add_zone(12, 'Office', 345); set_extent(12, 30, 30, 31, 31, 5); ROOM_DESC = 'Fine'")
    assert office(w.requirements())["status"] == "met"


def test_two_zones_both_bare_is_not_met(w):
    w.run("add_zone(12, 'Office', 345); set_extent(12, 30, 30, 31, 31, 5); ROOM_DESC = ''")
    assert office(w.requirements())["status"] == "not_met"


# --- zone contents ---------------------------------------------------------

def test_contents_lists_the_chair_and_reads_completion(w):
    w.run("add_building(50, 'Chair', {{11, 21, 5}}, true, 2, 2, 1)")
    w.run("add_building(60, 'Workshop', {{10, 20, 5}, {11, 20, 5}, {10, 21, 5}, {11, 21, 5}}, false, 1, 4)")
    # Workshop overwrote the chair's tile; put the chair on a free tile.
    w.run("TILE_BLD['11,21,5'] = BUILDINGS[50]; TILE_BLD['12,22,5'] = BUILDINGS[50]")
    res = w.contents(11)
    assert res["zone_id"] == 11 and res["kind"] == "Office"
    assert res["width"] == 3 and res["height"] == 3 and res["tiles_scanned"] == 9
    assert res["furniture_kinds"] == ["Chair"]
    rows = {b["id"]: b for b in res["buildings"]}
    assert set(rows) == {50, 60}
    chair, shop = rows[50], rows[60]
    assert chair["kind"] == "Chair" and chair["matches_zone_kind"] is True
    assert chair["exists"] is True and chair["build_stage"] == 2 and chair["build_stage_max"] == 2
    assert chair["holds_items"] is True and chair["tiles_inside"] == 2
    assert shop["kind"] == "Workshop" and shop["matches_zone_kind"] is False
    assert shop["exists"] is False and shop["build_stage"] == 1 and shop["build_stage_max"] == 4
    assert shop["holds_items"] is False
    assert res["matching_count"] == 1 and res["complete_matching_count"] == 1


def test_contents_is_kind_generic_via_zone_policy(w):
    w.run("add_zone(20, 'Bedroom'); set_extent(20, 0, 0, 2, 2, 1)")
    w.run("add_building(70, 'Bed', {{1, 1, 1}}); add_building(71, 'Chair', {{0, 0, 1}})")
    res = w.contents(20)
    assert res["kind"] == "Bedroom" and res["furniture_kinds"] == ["Bed"]
    rows = {b["id"]: b for b in res["buildings"]}
    assert rows[70]["matches_zone_kind"] is True
    assert rows[71]["matches_zone_kind"] is False


def test_contents_refuses_an_enormous_zone(w):
    w.run("add_zone(21, 'Office'); set_extent(21, 0, 0, 99, 99, 1)")
    assert "refused" in w.contents(21)["error"]


def test_contents_refuses_a_non_zone_and_a_missing_id(w):
    w.run("add_workshop(99)")
    assert "not an activity zone" in w.contents(99)["error"]
    assert "no building" in w.contents(12345)["error"]


def test_contents_output_carries_no_coordinates(w):
    w.run("add_building(50, 'Chair', {{11, 21, 5}})")
    res = w.contents(11)
    flat = repr(res)
    for banned in ("'x'", "'y'", "'z'", "x1", "y1", "x2", "y2"):
        assert banned not in flat


def test_requirements_and_contents_share_one_helper(w):
    """One implementation: nobles calls the zone module's zone_furniture_report."""
    assert w.eval("type(reqscript('df-overseer-zone').zone_furniture_report)") == "function"
    nobles_src = NOBLES_LUA.read_text(encoding="utf-8")
    if "zone_furniture_report" in nobles_src:
        assert "findAtTile" not in nobles_src
