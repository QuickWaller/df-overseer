"""Runs the REAL scripts/dfhack/df-overseer-building.lua `requirements_for`
and `kind_previously_built` against a small fake DFHack world, using lupa.

handoffs/2026-09-28-building-material-choice-and-repeat-kind.md: the
2026-09-25 live run built the fort's first Carpenter's Workshop out of
economic hematite blocks while shale sat available, because a
`building_material` filter was only counted by item type, never by material
or economic status. This proves the fix's own logic (material breakdown,
default economic exclusion, an explicit override, the `kind_previously_built`
live fact) against a fake world. It proves nothing about the real game: the
exact DFHack field names (`dfhack.matinfo.decode`, `.material.id`,
`inorganic:isOre()`, `inorganic.material:isGem()`, `bld.type`/
`bld.custom_type`/`bld:getBuildStage()`) are a live check, called out in this
stream's Result.

handoffs/2026-09-28-building-economic-uses-fix.md: the original version of
this test (and the stub it drove) modelled the economic flag as a non-empty
`inorganic.economic_uses`, mirroring the exact wrong-field mistake
research/2026-09-28-ore-detection.md later proved live and that
df-overseer-surface.lua's decode_vein_tile already had to correct once. The
stub and every test below now model `inorganic:isOre()` /
`inorganic.material:isGem()` instead, matching the corrected .lua code.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

LUA = Path(__file__).resolve().parent.parent / "scripts" / "dfhack" / "df-overseer-building.lua"

STUB = r"""
dfhack_flags = {module = true}

local function enum(names)
  local e = {}
  for i, n in ipairs(names) do e[n] = i - 1; e[i - 1] = n end
  return e
end

df = {
  item_type = enum({"BOULDER", "WOOD", "BLOCKS"}),
  job_item_vector_id = enum({"BOULDER", "WOOD", "BLOCKS"}),
  building_type = enum({"Workshop", "Furnace", "Construction", "Trap", "SiegeEngine", "Bed"}),
  workshop_type = enum({"Masons", "Custom"}),
  furnace_type = enum({}),
  construction_type = enum({}),
  trap_type = enum({}),
  siegeengine_type = enum({}),
  global = {
    world = {
      items = {other = {}},
      buildings = {all = {}},
      raws = {buildings = {all = {}}},
    },
  },
}

MATINFO = {}   -- item id -> {material = {id=...}, inorganic = {isOre=fn, material={isGem=fn}}} or "error"

-- Builds a fake `inorganic_raw`-shaped table: `:isOre()` and
-- `.material:isGem()` are the two live-verified accessors the real .lua
-- code calls (see df-overseer-building.lua's decode_item_material).
function make_inorganic(is_ore, is_gem)
  local inorg = {}
  function inorg:isOre() return is_ore end
  inorg.material = {}
  function inorg.material:isGem() return is_gem end
  return inorg
end

dfhack = {
  matinfo = {
    decode = function(item)
      local mi = MATINFO[item.id]
      if mi == "error" then error("boom: unreadable material") end
      if mi == nil then error("no material info for item " .. tostring(item.id)) end
      return mi
    end,
  },
  buildings = {
    getFiltersByType = function(_, btype, sub, cust) return FILTERS or {} end,
  },
}

local json = {encode = function() return "" end}
package.loaded['json'] = json
package.loaded['df-overseer-landmarks'] = {}
-- Out of scope for this stream (it fixes the material-aware selection, not
-- the plain item-type aggregate stocks_mod.get_availability already
-- provides): stubbed generous so its own, separate gap-check never fires
-- and confounds a test of the NEW material-choice gap logic that follows it.
package.loaded['df-overseer-stocks'] = {
  get_availability = function(type_name)
    return {total_units = 1000000, available_units = 1000000, unnetted_units = 0,
            in_building_units = 0, in_job_units = 0}
  end,
}
package.loaded['plugins.buildingplan'] = {isEnabled = function() return true end}
function reqscript(name) return package.loaded[name] or {} end
_G.require = function(n) return package.loaded[n] end

-- A vector shaped like a real DFHack items.other[TYPE]: 0-indexed, __len
-- reports the true count (a plain Lua table's # operator is undefined over
-- a 0-based run -- see test_room_proxy_lua_logic.py's own contained_items
-- fake for the same fix).
local function make_vec(items)
  local t = {}
  for i, it in ipairs(items) do t[i - 1] = it end
  return setmetatable(t, {__len = function() return #items end})
end

function add_material_item(id, flags)
  local it = {id = id, flags = flags or {}}
  df.global.world.items.other.BOULDER = df.global.world.items.other.BOULDER or make_vec({})
  return it
end

function reset_world()
  df.global.world.items.other = {BOULDER = make_vec({}), WOOD = make_vec({}), BLOCKS = make_vec({})}
  df.global.world.buildings.all = make_vec({})
  MATINFO = {}
  FILTERS = {{quantity = 1, flags1 = {}, flags2 = {building_material = true}, flags3 = {}}}
end

-- Puts `items` (each {id=, flags=}) into df.global.world.items.other[type_name].
function set_items(type_name, items)
  df.global.world.items.other[type_name] = make_vec(items)
end

function set_filter(f)
  FILTERS = {f}
end

function make_bld(btype, subtype, custom_type, stage, max_stage)
  local b = {type = subtype, custom_type = custom_type}
  function b:getType() return btype end
  function b:getBuildStage()
    if stage == "ERROR" then error("boom: build stage unreadable") end
    return stage
  end
  function b:getMaxBuildStage()
    if max_stage == "ERROR" then error("boom: max build stage unreadable") end
    return max_stage
  end
  return b
end

-- buildings.all is walked with ipairs elsewhere in this file (a plain
-- 1-based array, unlike items.other's 0-based vectors), so a plain table
-- is the right fake here -- no 0-based shift.
function set_buildings(list)
  local t = {}
  for i, b in ipairs(list) do t[i] = b end
  df.global.world.buildings.all = t
end

-- `requirements_for` and `kind_previously_built` are file-level `local`s,
-- never exported (the module guard below `return`s bare, no module table).
-- find_kind/build_kind (global) close over both as upvalues -- the same
-- debug.getupvalue trick this file itself uses to reach quickfort's own
-- local table, reused here to reach into the file under test rather than
-- guess at re-implementing its logic.
function upvalue_by_name(fn, name)
  local i = 1
  while true do
    local n, v = debug.getupvalue(fn, i)
    if n == nil then return nil end
    if n == name then return v end
    i = i + 1
  end
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
        self.lua.execute(STUB)
        load = self.lua.eval("function(src) return load(src, 'building.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()
        get_upvalue = self.lua.eval("function(fn, n) return upvalue_by_name(fn, n) end")
        self._requirements_for = get_upvalue(self.g["find_kind"], "requirements_for")
        self._kind_previously_built = get_upvalue(self.g["find_kind"], "kind_previously_built")
        assert self._requirements_for is not None
        assert self._kind_previously_built is not None
        self.lua.execute("reset_world()")

    def run(self, code):
        return self.lua.execute(code)

    def item(self, id_, **flags):
        return self.lua.eval("function(id, flags) return add_material_item(id, flags) end")(
            id_, self.lua.table_from(flags)
        )

    def set_items(self, type_name, items):
        arr = self.lua.table_from(items)
        self.lua.eval("function(t, items) set_items(t, items) end")(type_name, arr)

    def set_matinfo(self, id_, material=None, is_ore=False, is_gem=False, inorganic=True,
                     error=False):
        if error:
            self.lua.globals()["MATINFO"][id_] = "error"
            return
        mi = self.lua.table_from({"material": {"id": material}}, recursive=True)
        if inorganic:
            make_inorganic = self.lua.eval(
                "function(is_ore, is_gem) return make_inorganic(is_ore, is_gem) end"
            )
            mi["inorganic"] = make_inorganic(is_ore, is_gem)
        self.lua.globals()["MATINFO"][id_] = mi

    def set_filter(self, **f):
        self.lua.eval("function(f) set_filter(f) end")(self.lua.table_from(f, recursive=True))

    def requirements(self, k=None, choice=None):
        k = k or self.lua.table_from(
            {"token": "Masons", "entry": self.lua.table_from({"type": 0, "subtype": 0})}
        )
        r = self._requirements_for(k, choice)
        if isinstance(r, tuple):
            req, gaps = r
        else:
            req, gaps = r, None
        return _py(req), (_py(gaps) if gaps is not None else [])

    def kind_previously_built(self, k):
        r = self._kind_previously_built(k)
        if isinstance(r, tuple):
            status, note = r
            return status, note
        return r, None

    def make_bld(self, btype, subtype, custom_type, stage, max_stage):
        return self.lua.eval(
            "function(t, s, c, st, mx) return make_bld(t, s, c, st, mx) end"
        )(btype, subtype, custom_type, stage, max_stage)

    def set_buildings(self, blds):
        arr = self.lua.table_from(blds)
        self.lua.eval("function(bs) set_buildings(bs) end")(arr)


@pytest.fixture
def w():
    return World()


def _item(w_, id_, flags=None):
    return w_.item(id_, **(flags or {}))


# ---------------------------------------------------------------------------
# Material breakdown and economic default
# ---------------------------------------------------------------------------


def test_economic_material_is_excluded_by_default_and_reported_why(w):
    a = w.item(1)  # HEMATITE, 1 unit
    b = w.item(2)  # SHALE
    c = w.item(3)  # SHALE
    w.set_items("BOULDER", [a, b, c])
    w.set_matinfo(1, material="HEMATITE", is_ore=True)
    w.set_matinfo(2, material="SHALE", is_ore=False)
    w.set_matinfo(3, material="SHALE", is_ore=False)

    req, gaps = w.requirements()
    f = req["building_material"]["filters"][0]
    by_name = {m["name"]: m for m in f["materials"]}
    assert by_name["HEMATITE"]["economic"] is True and by_name["HEMATITE"]["units"] == 1
    assert by_name["SHALE"]["economic"] is False and by_name["SHALE"]["units"] == 2
    assert f["excluded_materials"] == ["HEMATITE"]
    assert f["chosen_material"] == "SHALE"
    assert f["available"] == 2
    assert "default" in f["material_choice"] and "non-economic" in f["material_choice"]
    assert not gaps
    # 2026-10-01 (handoffs/2026-10-01-buildingplan-material-filter.md): the
    # CLASS written into buildingplan's filter is every eligible material,
    # not just the single reported chosen_material -- HEMATITE (economic)
    # must never appear.
    assert f["filter_material_names"] == ["SHALE"]


def test_a_gem_material_is_economic_via_isGem_even_when_not_an_ore(w):
    # handoffs/2026-09-28-building-economic-uses-fix.md: the fix reads BOTH
    # inorganic:isOre() and inorganic.material:isGem(), not isOre() alone --
    # a material can be a gem (economic) without being a metal ore.
    a = w.item(1)  # a gem, not an ore
    b = w.item(2)  # neither ore nor gem
    w.set_items("BOULDER", [a, b])
    w.set_matinfo(1, material="ROCK_SALT_VAR", is_ore=False, is_gem=True)
    w.set_matinfo(2, material="SHALE", is_ore=False, is_gem=False)

    req, gaps = w.requirements()
    f = req["building_material"]["filters"][0]
    by_name = {m["name"]: m for m in f["materials"]}
    assert by_name["ROCK_SALT_VAR"]["economic"] is True
    assert by_name["SHALE"]["economic"] is False
    assert f["chosen_material"] == "SHALE"
    assert not gaps


def test_a_non_inorganic_material_is_never_economic(w):
    # Wood and other organics have no `.inorganic` at all: decode_item_material
    # must treat that as economic=false (never an unreadable error, never
    # excluded). BUILDING_MATERIAL_TYPES scans WOOD as well as BOULDER for a
    # building_material-class filter (the default filter this stub sets up).
    a = w.item(1)
    w.set_items("WOOD", [a])
    w.set_matinfo(1, material="WILLOW", inorganic=False)

    req, gaps = w.requirements()
    f = req["building_material"]["filters"][0]
    by_name = {m["name"]: m for m in f["materials"]}
    assert by_name["WILLOW"]["economic"] is False
    assert f["chosen_material"] == "WILLOW"
    assert not gaps


def test_allow_economic_overrides_the_default_and_can_pick_the_economic_material(w):
    a = w.item(1)  # HEMATITE, more stock than the non-economic option
    b = w.item(2)  # SHALE
    w.set_items("BOULDER", [a, b])
    w.set_matinfo(1, material="HEMATITE", is_ore=True)
    w.set_matinfo(2, material="SHALE", is_ore=False)
    # stack_size defaults to 1 unit per item; add extra HEMATITE items to
    # make it the higher-stock material once allowed.
    extra = [w.item(10 + i) for i in range(4)]
    for it in extra:
        w.set_matinfo(int(w.lua.eval("function(i) return i.id end")(it)), material="HEMATITE",
                       is_ore=True)
    w.set_items("BOULDER", [a, b] + extra)

    req_default, _ = w.requirements()
    f_default = req_default["building_material"]["filters"][0]
    assert f_default["chosen_material"] == "SHALE"  # economic excluded despite more stock

    req_allowed, _ = w.requirements(choice="allow_economic")
    f_allowed = req_allowed["building_material"]["filters"][0]
    assert f_allowed["chosen_material"] == "HEMATITE"
    assert "excluded_materials" not in f_allowed
    assert "caller" in f_allowed["material_choice"]
    # allow_economic widens the CLASS written to buildingplan to include the
    # economic material alongside the non-economic one.
    assert set(f_allowed["filter_material_names"]) == {"HEMATITE", "SHALE"}
    assert set(f_default["filter_material_names"]) == {"SHALE"}


def test_naming_a_material_explicitly_is_honoured_even_if_economic(w):
    a = w.item(1)
    b = w.item(2)
    w.set_items("BOULDER", [a, b])
    w.set_matinfo(1, material="HEMATITE", is_ore=True)
    w.set_matinfo(2, material="SHALE", is_ore=False)

    req, gaps = w.requirements(choice="hematite")  # case-insensitive
    f = req["building_material"]["filters"][0]
    assert f["chosen_material"] == "HEMATITE"
    assert f["available"] == 1
    assert "caller named HEMATITE explicitly" in f["material_choice"]
    assert not gaps
    # An explicitly named material is a class of one.
    assert f["filter_material_names"] == ["HEMATITE"]


def test_a_filters_own_non_economic_flag_beats_an_allow_economic_override(w):
    a = w.item(1)
    w.set_items("BOULDER", [a])
    w.set_matinfo(1, material="HEMATITE", is_ore=True)
    w.set_filter(quantity=1, flags1={}, flags2={"building_material": True, "non_economic": True}, flags3={})

    req, gaps = w.requirements(choice="hematite")
    f = req["building_material"]["filters"][0]
    assert "material_choice_error" in f and "non_economic" in f["material_choice_error"]
    assert any("non_economic" in g for g in gaps)


def test_only_economic_material_available_is_a_named_gap_not_a_silent_zero(w):
    a = w.item(1)
    w.set_items("BOULDER", [a])
    w.set_matinfo(1, material="HEMATITE", is_ore=True)

    req, gaps = w.requirements()
    f = req["building_material"]["filters"][0]
    assert f["available"] == 0
    assert "material_choice_error" in f and "economic" in f["material_choice_error"]
    assert any("economic" in g for g in gaps)


def test_an_unreadable_material_is_reported_not_silently_dropped_or_crashed(w):
    a = w.item(1)
    b = w.item(2)
    w.set_items("BOULDER", [a, b])
    w.set_matinfo(1, error=True)
    w.set_matinfo(2, material="SHALE", is_ore=False)

    req, gaps = w.requirements()
    f = req["building_material"]["filters"][0]
    assert f["chosen_material"] == "SHALE"
    assert any("boom" in e for e in f["material_scan_errors"])


def test_items_that_are_not_available_never_count_toward_any_material(w):
    a = w.item(1, in_job=True)
    b = w.item(2, forbid=True)
    c = w.item(3, owned=True)
    d = w.item(4, in_building=True)
    e = w.item(5, construction=True)
    f_ = w.item(6, trader=True)
    free = w.item(7)
    w.set_items("BOULDER", [a, b, c, d, e, f_, free])
    for i in range(1, 7):
        w.set_matinfo(i, material="SHALE", is_ore=False)
    w.set_matinfo(7, material="SHALE", is_ore=False)

    req, _ = w.requirements()
    f = req["building_material"]["filters"][0]
    assert f["available"] == 1
    assert f["materials"][0]["item_count"] == 1


# ---------------------------------------------------------------------------
# kind_previously_built
# ---------------------------------------------------------------------------


def _entry(w_, btype=0, subtype=None, custom=None):
    d = {"type": btype}
    if subtype is not None:
        d["subtype"] = subtype
    if custom is not None:
        d["custom"] = custom
    return w_.lua.table_from({"token": "k", "entry": w_.lua.table_from(d)})


def test_no_matching_building_at_all_is_false(w):
    w.set_buildings([])
    status, note = w.kind_previously_built(_entry(w))
    assert status is False and note is None


def test_a_completed_building_of_the_kind_is_true(w):
    bld = w.make_bld(0, 0, None, 3, 3)  # Workshop, Masons, stage == max
    w.set_buildings([bld])
    status, note = w.kind_previously_built(_entry(w, subtype=0))
    assert status is True


def test_a_building_still_under_construction_does_not_count(w):
    bld = w.make_bld(0, 0, None, 1, 3)  # stage < max: not finished
    w.set_buildings([bld])
    status, note = w.kind_previously_built(_entry(w, subtype=0))
    assert status is False


def test_a_different_subtype_does_not_count(w):
    bld = w.make_bld(0, 1, None, 3, 3)  # Custom workshop, not Masons
    w.set_buildings([bld])
    status, note = w.kind_previously_built(_entry(w, subtype=0))  # asking about Masons
    assert status is False


def test_custom_workshop_matches_by_custom_type(w):
    bld = w.make_bld(0, 1, 42, 3, 3)  # Custom workshop, raws index 42
    w.set_buildings([bld])
    assert w.kind_previously_built(_entry(w, subtype=1, custom=42))[0] is True
    assert w.kind_previously_built(_entry(w, subtype=1, custom=99))[0] is False


def test_unreadable_build_stage_is_unknown_not_false(w):
    bld = w.make_bld(0, 0, None, "ERROR", 3)
    w.set_buildings([bld])
    status, note = w.kind_previously_built(_entry(w, subtype=0))
    # The file's own NULL sentinel ("\0", never Lua nil/false): calling the
    # function directly bypasses the json.encode step that would otherwise
    # turn it into a JSON null, so it is compared verbatim here.
    assert status == "\x00"
    assert note and "could not confirm" in note


def test_a_type_with_no_subtype_at_all_matches_on_type_alone(w):
    bld = w.make_bld(2, None, None, 1, 1)  # Bed: not in SUBTYPE_ENUMS
    w.set_buildings([bld])
    status, note = w.kind_previously_built(_entry(w, btype=2))
    assert status is True
