"""Runs the REAL scripts/dfhack/df-overseer-zone.lua `list_zones` summary against
the fake DFHack world (tests/lua_stubs/dfhack_zone_world.lua plus zone
footprints and buildings), using lupa.

handoffs/2026-10-07-planner-p1b.md: the unfiltered summary now carries
`furnished_by_kind` and `furniture_counts_by_kind`, read from the game and
generic per kind, so a plan target on `zones."Bedroom".furnished` reads a real
number. These prove the file's own logic (what counts, what is unknown, that a
filtered list never pays for it), not what the real findAtTile returns: that is
the live check.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
ZONE_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-zone.lua"
STUB = REPO_ROOT / "tests" / "lua_stubs" / "dfhack_zone_world.lua"

EXTRA = r"""
local function enum2(names) local t = {} for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end return t end
df.building_type = enum2({"Chair", "Bed", "Table", "Coffin", "Workshop", "Door"})
function xyz2pos(x, y, z) return {x = x, y = y, z = z} end
TILE_BLD = {}
FIND_FAILS = false
function set_extent(id, x1, y1, x2, y2, z)
  local b = BUILDINGS[id]
  b.x1, b.y1, b.x2, b.y2, b.z = x1, y1, x2, y2, z
end
function add_building(id, kind, tiles, exists)
  local b = {id = id, _type = df.building_type[kind], flags = {exists = exists ~= false},
    contained_items = setmetatable({}, {__len = function() return 0 end}), _stage = 1, _max = 1}
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
-- quickfort's zone table, reached the way the real script reaches it: do_run's
-- upvalue zone_db, its __index's upvalue parse_zone_config, whose upvalue is zone_db_raw.
local function entry(kind)
  return {label = kind, default_data = {type = df.civzone_type[kind]}, min_width = 1, max_width = math.huge,
    min_height = 1, max_height = math.huge, is_valid_tile_fn = function() return true end}
end
local zone_db_raw = {}
for _, kind in ipairs({"Bedroom", "Office", "DiningHall", "Tomb", "MeetingHall", "Pen"}) do
  zone_db_raw[kind:lower()] = entry(kind)
end
local function parse_zone_config() return zone_db_raw end
local zone_db = setmetatable({}, {__index = function(_, k) return parse_zone_config(k) end})
local function do_run() return zone_db end
function reqscript(n)
  if n == 'internal/quickfort/zone' then return {do_run = do_run} end
  return {}
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
        self.lua.globals().ZONE_SRC = ZONE_LUA.read_text(encoding="utf-8")
        self.zone = self.lua.execute(
            """
            local env = setmetatable({}, {__index = _G})
            local chunk = assert(load(ZONE_SRC, 'zone.lua', 't', env))
            chunk()
            return env
            """
        )

    def run(self, code):
        return self.lua.execute(code)

    def list(self, kind="", owner="", valid="", near=""):
        res = self.zone["list_zones"](kind, owner, valid, near, None)
        if isinstance(res, tuple):
            res, err = res
            if res is None:
                return {"error": err}
        out = _py(res)
        # json.lua encodes NULL as a sentinel string
        return out


NULL = "\0"


@pytest.fixture
def w():
    return World()


def zone(world, zid, kind, x1, y1, x2, y2, z=5):
    world.run(f"add_zone({zid}, '{kind}'); set_extent({zid}, {x1}, {y1}, {x2}, {y2}, {z})")


def test_a_bedroom_with_a_built_bed_is_furnished_and_one_without_is_not(w):
    zone(w, 1, "Bedroom", 0, 0, 2, 2)
    zone(w, 2, "Bedroom", 10, 0, 12, 2)
    w.run("add_building(100, 'Bed', {{1, 1, 5}}, true)")
    r = w.list()
    assert r["summary"] is True
    assert r["counts_by_kind"]["Bedroom"] == 2
    assert r["furnished_by_kind"]["Bedroom"] == 1
    assert r["furniture_counts_by_kind"]["Bedroom"] == {"Bed": 1}
    assert not r["read_failures"]


def test_an_unbuilt_bed_is_not_furnishing(w):
    zone(w, 1, "Bedroom", 0, 0, 2, 2)
    w.run("add_building(100, 'Bed', {{1, 1, 5}}, false)")
    r = w.list()
    assert r["furnished_by_kind"]["Bedroom"] == 0
    assert r["furniture_counts_by_kind"]["Bedroom"] == {}


def test_the_defining_furniture_is_data_per_kind_not_a_branch(w):
    zone(w, 1, "Office", 0, 0, 2, 2)
    zone(w, 2, "DiningHall", 10, 0, 13, 3)
    zone(w, 3, "Tomb", 20, 0, 20, 1)
    w.run("add_building(100, 'Chair', {{1, 1, 5}}); add_building(101, 'Table', {{11, 1, 5}}); "
          "add_building(102, 'Coffin', {{20, 0, 5}})")
    f = w.list()["furnished_by_kind"]
    assert (f["Office"], f["DiningHall"], f["Tomb"]) == (1, 1, 1)
    # A Bed in an Office does not furnish it.
    zone(w, 4, "Office", 30, 0, 32, 2)
    w.run("add_building(103, 'Bed', {{31, 1, 5}})")
    assert w.list()["furnished_by_kind"]["Office"] == 1


def test_furniture_counts_cover_any_building_type_inside_the_zone(w):
    zone(w, 1, "DiningHall", 0, 0, 3, 3)
    w.run("add_building(100, 'Table', {{0, 0, 5}}); add_building(101, 'Table', {{2, 2, 5}}); "
          "add_building(102, 'Chair', {{1, 1, 5}}); add_building(103, 'Workshop', {{9, 9, 5}})")
    assert w.list()["furniture_counts_by_kind"]["DiningHall"] == {"Table": 2, "Chair": 1}


def test_a_kind_with_no_defining_furniture_is_unknown_not_zero(w):
    zone(w, 1, "MeetingHall", 0, 0, 4, 4)
    f = w.list()["furnished_by_kind"]
    assert f["MeetingHall"] == NULL
    assert f["Pen"] == NULL  # no zone, no defining furniture: still unknown


def test_a_kind_with_no_zone_has_no_furniture_key_and_a_zero_furnished(w):
    zone(w, 1, "Bedroom", 0, 0, 2, 2)
    r = w.list()
    assert r["furnished_by_kind"]["Tomb"] == 0
    assert "Tomb" not in r["furniture_counts_by_kind"]


def test_an_unreadable_zone_makes_its_kinds_entries_unknown_never_a_low_count(w):
    zone(w, 1, "Bedroom", 0, 0, 2, 2)
    zone(w, 2, "Office", 10, 0, 12, 2)
    w.run("add_building(100, 'Bed', {{1, 1, 5}}); add_building(101, 'Chair', {{11, 1, 5}})")
    w.run("FIND_FAILS = true")
    r = w.list()
    assert r["furnished_by_kind"]["Bedroom"] == NULL and r["furniture_counts_by_kind"]["Bedroom"] == NULL
    assert any("furnishing read failed" in f for f in r["read_failures"])


def test_an_oversized_zone_is_unknown_not_skipped(w):
    zone(w, 1, "Bedroom", 0, 0, 40, 40)  # over the 625-tile contents bound
    zone(w, 2, "Office", 100, 0, 102, 2)
    r = w.list()
    assert r["furnished_by_kind"]["Bedroom"] == NULL
    assert r["furnished_by_kind"]["Office"] == 0  # the other kind is unaffected
    assert any("over the 625-tile bound" in f for f in r["read_failures"])


def test_a_filtered_list_does_not_pay_for_the_furnishing_read(w):
    zone(w, 1, "Bedroom", 0, 0, 2, 2)
    w.run("FIND_FAILS = true")
    r = w.list(kind="Bedroom")
    assert r["summary"] is False
    assert "furnished_by_kind" not in r and "furniture_counts_by_kind" not in r
