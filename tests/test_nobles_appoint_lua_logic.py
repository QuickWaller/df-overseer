"""Runs the REAL scripts/dfhack/df-overseer-nobles.lua (appoint, unappoint, verify)
against a small fake DFHack world, using lupa.

evals/live/2026-10-08-manager-appointment/README.md. The incident: a MANAGER
appointed by this tool (make-monarch's recipe: ids only) read as consistent from
`verify`, and the Work Orders screen said "must assign a manager". The game's own
Nobles-screen appointment also sets two cached indexes (the holder link's
entity_vector_idx and the assignment's position_vector_idx) and writes a history
event. These tests prove the file's own logic: a tool-made appointment carries
the same fields a game-made one does, and `verify` fails an appointment that
lacks the cached indexes. They prove nothing about what the real game accepts:
that is the live check in the eval README.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import os
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
NOBLES_LUA = Path(os.environ.get("NOBLES_LUA_OVERRIDE") or REPO_ROOT / "scripts" / "dfhack" / "df-overseer-nobles.lua")

STUB = r"""
local function enum2(names) local t = {} for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end return t end

-- A 0-based fake df vector: `#` is the count, [0..n-1] are the items.
local VMETA = {}
VMETA.__index = VMETA
VMETA.__len = function(v) return rawget(v, "_n") end
function VMETA:insert(where, item)
  local n = rawget(self, "_n")
  local obj = item
  if type(item) == "table" and item.new then
    obj = {}
    for k, v in pairs(item.new.defaults or {}) do obj[k] = v end
    for k, v in pairs(item) do if k ~= "new" then obj[k] = v end end
    obj._cls = item.new
    obj.delete = function() end
  end
  rawset(self, n, obj)
  rawset(self, "_n", n + 1)
end
function VMETA:erase(i)
  local n = rawget(self, "_n")
  for k = i, n - 2 do rawset(self, k, rawget(self, k + 1)) end
  rawset(self, n - 1, nil)
  rawset(self, "_n", n - 1)
end
function newvec(items)
  local v = setmetatable({_n = 0}, VMETA)
  for _, it in ipairs(items or {}) do v:insert("#", it) end
  return v
end

local function cls(defaults)
  local c = {defaults = defaults}
  function c:is_instance(o) return type(o) == "table" and o._cls == self end
  return c
end

df = {}
df.histfig_entity_link_type = enum2({"MEMBER", "POSITION", "FORMER_POSITION"})
df.histfig_entity_link_positionst = cls({entity_vector_idx = -1, assignment_vector_idx = -1})
df.histfig_entity_link_former_positionst = cls({entity_vector_idx = -1})
df.history_event_add_hf_entity_linkst = cls({})
df.history_event_remove_hf_entity_linkst = cls({})
df.global = {cur_year = 31, cur_year_tick = 5000, hist_event_next_id = 100}

local function mkpos(id, code, flags)
  return {id = id, code = code, name = newvec({code:lower()}), flags = flags or {},
    requires_population = 0, number = 1, required_office = 0, description = ""}
end
local function mkassign(id, position_id, hf)
  return {id = id, position_id = position_id, histfig = hf or -1, histfig2 = hf or -1,
    position_vector_idx = -1, flags = {active = true}}
end

local civ = {id = 12, positions = {own = newvec({mkpos(1, "KING")}), assignments = newvec({})}}
local fort = {id = 36, positions = {
  own = newvec({mkpos(4, "MILITIA_COMMANDER"), mkpos(10, "MANAGER"), mkpos(13, "BOOKKEEPER"),
                mkpos(20, "MAYOR", {ELECTED = true})}),
  assignments = newvec({mkassign(0, 4), mkassign(6, 10), mkassign(3, 13), mkassign(7, 20)})}}
-- entities.all: index != id on purpose, so a test that confuses the two fails.
local filler = {}
for i = 1, 5 do filler[#filler + 1] = {id = 900 + i} end
df.global.world = {entities = {all = newvec({filler[1], filler[2], civ, filler[3], fort, filler[4]})},
  history = {events = newvec({})}}
df.global.plotinfo = {main = {fortress_entity = fort}}
ENT_INDEX_OF_FORT = 4

local figs = {}
local function mkfig(id, unit_id)
  local f = {id = id, unit_id = unit_id, entity_links = newvec({})}
  figs[id] = f
  return f
end
FIG_A = mkfig(331, 345)
FIG_B = mkfig(333, 347)
df.historical_figure = {find = function(id) return figs[id] end}

local units = {}
local function mkunit(id, hf)
  units[id] = {id = id, hist_figure_id = hf}
  return units[id]
end
mkunit(345, 331); mkunit(347, 333)
df.unit = {find = function(id) return units[id] end}

dfhack = {units = {}, }
dfhack.units.isAlive = function(u) return true end
dfhack.units.isCitizen = function(u) return true end
dfhack.units.isAdult = function(u) return true end
dfhack.units.getReadableName = function(u) return "unit" .. u.id end
-- getNoblePositions as the real one: id search only, never a cached index.
dfhack.units.getNoblePositions = function(u)
  local fig = figs[u.hist_figure_id]
  local out = {}
  for i = 0, #fig.entity_links - 1 do
    local l = fig.entity_links[i]
    if df.histfig_entity_link_positionst:is_instance(l) then
      local ents = {[12] = civ, [36] = fort}
      local e = ents[l.entity_id]
      local a, p
      if e then
        for k = 0, #e.positions.assignments - 1 do
          if e.positions.assignments[k].id == l.assignment_id then a = e.positions.assignments[k] end
        end
        if a then for k = 0, #e.positions.own - 1 do
          if e.positions.own[k].id == a.position_id then p = e.positions.own[k] end
        end end
      end
      if a and p then out[#out + 1] = {entity = e, assignment = a, position = p} end
    end
  end
  return out
end

function reqscript(n) return {to_utf8 = function(s) return s end} end
json = {encode = function(v) return "" end}
package.preload["json"] = function() return json end
dfhack_flags = {module = true}
"""


class World:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB)
        # the module exposes only its non-local functions; expose the locals we call
        src = NOBLES_LUA.read_text(encoding="utf-8")
        for name in ("appoint", "unappoint", "verify"):
            src = src.replace("local function %s(" % name, "function %s(" % name)
        load = self.lua.eval("function(src) return load(src, 'nobles.lua') end")
        chunk = load(src)
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def ev(self, code):
        return self.lua.eval(code)

    def ex(self, code):
        self.lua.execute(code)

    def call(self, name, *args):
        r = self.g[name](*args)
        if isinstance(r, tuple):
            return r
        return r, None


@pytest.fixture
def w():
    return World()


def test_dry_run_writes_nothing(w):
    plan, err = w.call("appoint", "MANAGER", 345)
    assert err is None and plan["dry_run"] is True
    assert w.ev("#FIG_A.entity_links") == 0
    assert w.ev("df.global.plotinfo.main.fortress_entity.positions.assignments[1].histfig") == -1


def test_appoint_writes_what_the_game_writes(w):
    plan, err = w.call("appoint", "MANAGER", 345, "false")
    assert err is None and plan["dry_run"] is False
    e = "df.global.plotinfo.main.fortress_entity.positions.assignments[1]"
    assert w.ev(e + ".histfig") == 331 and w.ev(e + ".histfig2") == 331
    # the cached index of the position in entity.positions.own: MANAGER is index 1
    assert w.ev(e + ".position_vector_idx") == 1
    link = "FIG_A.entity_links[0]"
    assert w.ev("df.histfig_entity_link_positionst:is_instance(%s)" % link)
    assert w.ev(link + ".assignment_id") == 6
    assert w.ev(link + ".assignment_vector_idx") == 1
    # entities.all index of the fortress entity (4), NOT its id (36)
    assert w.ev(link + ".entity_vector_idx") == 4
    assert w.ev(link + ".entity_id") == 36
    # the add event, like the game's
    assert w.ev("#df.global.world.history.events") == 1
    ev = "df.global.world.history.events[0]"
    assert w.ev("df.history_event_add_hf_entity_linkst:is_instance(%s)" % ev)
    assert w.ev(ev + ".histfig") == 331 and w.ev(ev + ".position_id") == 10
    assert w.ev(ev + ".link_type") == w.ev("df.histfig_entity_link_type.POSITION")
    assert w.ev(ev + ".civ") == 36
    assert plan["event_written"] is True
    assert plan["verification"]["consistent"] is True


def test_minimal_version_writes_indexes_but_no_event(w):
    plan, err = w.call("appoint", "MANAGER", 345, "false", "minimal")
    assert err is None
    assert w.ev("FIG_A.entity_links[0].entity_vector_idx") == 4
    assert w.ev("df.global.plotinfo.main.fortress_entity.positions.assignments[1].position_vector_idx") == 1
    assert w.ev("#df.global.world.history.events") == 0


def test_generic_over_position_codes(w):
    plan, err = w.call("appoint", "BOOKKEEPER", 347, "false")
    assert err is None
    link = "FIG_B.entity_links[0]"
    assert w.ev(link + ".assignment_vector_idx") == 2
    assert w.ev(link + ".entity_vector_idx") == 4
    assert w.ev("df.global.plotinfo.main.fortress_entity.positions.assignments[2].position_vector_idx") == 2


def test_verify_fails_an_appointment_without_the_cached_indexes(w):
    """The incident: ids all right, cached indexes at -1."""
    w.ev("""(function()
      local a = df.global.plotinfo.main.fortress_entity.positions.assignments[1]
      a.histfig = 331; a.histfig2 = 331
      FIG_A.entity_links:insert('#', {new = df.histfig_entity_link_positionst,
        entity_id = 36, link_strength = 100, assignment_id = 6, assignment_vector_idx = 1, start_year = 31})
      return true end)()""")
    res, _ = w.call("verify", "MANAGER")
    row = res["assignments"][1]
    # everything an id-based check sees is fine ...
    assert row["figure_has_position_link"] is True
    assert row["get_noble_positions_lists_it"] is True
    assert row["link_vector_index_matches"] is True
    # ... and the new checks catch what it cannot
    assert row["link_entity_cached_index_matches"] is False
    assert row["assignment_position_cached_index_matches"] is False
    assert res["consistent"] is False


def test_verify_passes_a_fully_cached_appointment_and_reports_the_event(w):
    w.call("appoint", "MANAGER", 345, "false")
    res, _ = w.call("verify", "MANAGER")
    row = res["assignments"][1]
    assert res["consistent"] is True
    assert row["link_entity_cached_index_matches"] is True
    assert row["assignment_position_cached_index_matches"] is True
    assert row["position_add_event_found"] is True


def test_verify_partial_cache_still_fails(w):
    w.call("appoint", "MANAGER", 345, "false")
    w.ex("FIG_A.entity_links[0].entity_vector_idx = -1")
    res, _ = w.call("verify", "MANAGER")
    assert res["consistent"] is False
    w.ex("FIG_A.entity_links[0].entity_vector_idx = 4")
    w.ex("df.global.plotinfo.main.fortress_entity.positions.assignments[1].position_vector_idx = -1")
    res, _ = w.call("verify", "MANAGER")
    assert res["consistent"] is False


def test_unappoint_leaves_what_the_game_leaves(w):
    w.call("appoint", "MANAGER", 345, "false")
    plan, err = w.call("unappoint", "MANAGER", "false")
    assert err is None
    a = "df.global.plotinfo.main.fortress_entity.positions.assignments[1]"
    assert w.ev(a + ".histfig") == -1
    # as the civ entity's vacated assignments: last holder kept in histfig2, index kept
    assert w.ev(a + ".histfig2") == 331
    assert w.ev(a + ".position_vector_idx") == 1
    link = "FIG_A.entity_links[0]"
    assert w.ev("df.histfig_entity_link_former_positionst:is_instance(%s)" % link)
    assert w.ev(link + ".entity_vector_idx") == -1
    assert w.ev(link + ".assignment_id") == 6
    assert w.ev("#FIG_A.entity_links") == 1
    assert w.ev("df.histfig_entity_link_positionst:is_instance(FIG_A.entity_links[0])") is False
    ev = "df.global.world.history.events[1]"
    assert w.ev("df.history_event_remove_hf_entity_linkst:is_instance(%s)" % ev)
    assert w.ev(ev + ".position_id") == 10 and w.ev(ev + ".histfig") == 331


def test_unappoint_then_appoint_the_same_unit_again(w):
    w.call("appoint", "MANAGER", 345, "false")
    w.call("unappoint", "MANAGER", "false")
    plan, err = w.call("appoint", "MANAGER", 345, "false")
    assert err is None
    res, _ = w.call("verify", "MANAGER")
    assert res["consistent"] is True
    assert res["assignments"][1]["holder_unit_id"] == 345


def test_refusals_unchanged(w):
    _, err = w.call("appoint", "MAYOR", 345, "false")
    assert "elected" in err
    _, err = w.call("appoint", "NOPE", 345, "false")
    assert "unknown position code" in err
    _, err = w.call("unappoint", "MANAGER", "false")
    assert "vacant" in err
    w.call("appoint", "MANAGER", 345, "false")
    _, err = w.call("appoint", "MANAGER", 347, "false")
    assert "already held" in err
    _, err = w.call("appoint", "BOOKKEEPER", 345, "false", "bogus")
    assert "VERSION" in err
