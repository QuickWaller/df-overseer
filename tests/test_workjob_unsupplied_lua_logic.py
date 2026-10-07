"""Runs the REAL scripts/dfhack/df-overseer-workjob.lua `unsupplied_buildings`
against a small fake DFHack world, using lupa.

handoffs/2026-10-07-unsupplied-building-watch.md: a buildingplan-planned
building (the live case: a Bed waiting 38 game days for a BED item nobody
made) is read as "needs item kind X, N free, these jobs at these workshops make
it, this many are queued". The product of a hard-coded job comes from its name
(the verb stripped), a reaction job's from the reaction's own products.

This proves the file's own logic against a fake world. It proves nothing about
the real game: `plugins.buildingplan.isPlannedBuilding`, `job.job_items.
elements` and the job-name-to-item rule are the live check in the handoff
Result.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

LUA = Path(__file__).resolve().parent.parent / "scripts" / "dfhack" / "df-overseer-workjob.lua"

STUB = r"""
dfhack_flags = {module = true}
local function enum(names)
  local e = {}
  for i, n in ipairs(names) do e[n] = i - 1; e[i - 1] = n end
  return e
end
df = {
  item_type = enum({"BED", "CHAIR", "BARREL", "DRINK", "BOX"}),
  job_type = enum({"CustomReaction", "ConstructBed", "ConstructThrone", "MakeBarrel", "ConstructChest",
                   "ConstructBlocks", "DestroyBuilding"}),
  building_type = enum({"Workshop", "Furnace", "Bed"}),
  workshop_type = enum({"Carpenters", "Still", "Custom"}),
  furnace_type = enum({"Kiln"}),
  global = {world = {buildings = {all = {}}, raws = {reactions = {reactions = {}}}}},
}
AVAIL = {}              -- item name -> available units, or "error"
JOBS_BY_KIND = {}       -- workshop kind name -> list of getJobs entries
PLANNED = {}            -- building -> true
dfhack = {printerr = function() end, buildings = {getName = function(b) return b.name end}}
package.loaded['json'] = {encode = function() return "" end}
package.loaded['utils'] = {}
package.loaded['dfhack.workshops'] = {getJobs = function(btype, sub, custom)
  local kind = (btype == df.building_type.Workshop) and df.workshop_type[sub] or df.furnace_type[sub]
  local jobs = JOBS_BY_KIND[kind]
  if jobs == "error" then error("boom") end
  return jobs
end}
BUILDINGPLAN = {isPlannedBuilding = function(b) return PLANNED[b] == true end}
package.loaded['plugins.buildingplan'] = BUILDINGPLAN
package.loaded['df-overseer-stocks'] = {get_availability = function(name)
  local v = AVAIL[name]
  if v == "error" then error("boom") end
  if v == nil then return nil, "no such item" end
  return {available_units = v, total_units = v}
end}
function reqscript(name) return package.loaded[name] or {} end
_G.require = function(n) return package.loaded[n] end

function workshop(kind, jobs, built)
  local b = {name = kind, flags = {exists = built ~= false}, jobs = jobs or {}, type = df.workshop_type[kind]}
  function b:getType() return df.building_type.Workshop end
  table.insert(df.global.world.buildings.all, b)
  return b
end

function planned(item_name, quantity, extra_elements)
  local els = {{item_type = df.item_type[item_name], quantity = quantity or 1}}
  for _, e in ipairs(extra_elements or {}) do table.insert(els, e) end
  local b = {jobs = {{job_items = {elements = els}}}}
  function b:getType() return df.building_type.Bed end
  PLANNED[b] = true
  table.insert(df.global.world.buildings.all, b)
  return b
end

function entry(job_name, reaction)
  return {name = job_name, job_fields = {job_type = df.job_type[job_name], reaction_name = reaction}, items = {}}
end

function reset_world()
  df.global.world.buildings.all = {}
  df.global.world.raws.reactions.reactions = {}
  AVAIL = {BED = 0, CHAIR = 0, BARREL = 3, DRINK = 0, BOX = 0}
  PLANNED = {}
  BUILDINGPLAN.isPlannedBuilding = function(b) return PLANNED[b] == true end
  JOBS_BY_KIND = {
    Carpenters = {[1] = entry("ConstructBed"), [2] = entry("ConstructThrone"), [3] = entry("MakeBarrel"),
                  [4] = entry("ConstructChest"), [5] = entry("DestroyBuilding")},
  }
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
        load = self.lua.eval("function(src) return load(src, 'workjob.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.lua.execute("reset_world()")

    def run(self, code):
        return self.lua.execute(code)

    def read(self):
        r = self.lua.globals()["unsupplied_buildings"]()
        if isinstance(r, tuple):
            r, err = r
            return {"error": err} if r is None else _py(r)
        return _py(r)

    def rows(self):
        return {row["item"]: row for row in self.read()["unsupplied"]}


@pytest.fixture
def world():
    return World()


def test_a_planned_bed_with_no_bed_is_read_with_the_carpenters_job_that_makes_it(world):
    world.run("workshop('Carpenters'); planned('BED')")
    row = world.rows()["BED"]
    assert row["available"] == 0 and row["buildings_waiting"] == 1 and row["units_needed"] == 1
    assert row["producers"] == [{"job": "ConstructBed", "workshop_kind": "Carpenters"}]
    assert row["jobs_queued_now"] == 0


def test_a_job_name_that_does_not_spell_its_product_comes_from_the_alias_list(world):
    world.run("workshop('Carpenters'); planned('CHAIR'); planned('BOX')")
    rows = world.rows()
    assert rows["CHAIR"]["producers"] == [{"job": "ConstructThrone", "workshop_kind": "Carpenters"}]
    assert rows["BOX"]["producers"] == [{"job": "ConstructChest", "workshop_kind": "Carpenters"}]


def test_two_planned_beds_are_one_row_counting_both(world):
    world.run("workshop('Carpenters'); planned('BED'); planned('BED')")
    row = world.rows()["BED"]
    assert row["buildings_waiting"] == 2 and row["units_needed"] == 2


def test_a_queued_workshop_job_that_makes_it_is_counted(world):
    world.run("workshop('Carpenters', {{job_type = df.job_type.ConstructBed}}); planned('BED')")
    assert world.rows()["BED"]["jobs_queued_now"] == 1


def test_a_queued_job_that_makes_something_else_is_not_counted(world):
    world.run("workshop('Carpenters', {{job_type = df.job_type.MakeBarrel}}); planned('BED')")
    assert world.rows()["BED"]["jobs_queued_now"] == 0


def test_free_stock_is_reported_not_filtered_out(world):
    world.run("workshop('Carpenters'); planned('BARREL')")
    assert world.rows()["BARREL"]["available"] == 3


def test_no_built_workshop_that_makes_it_means_no_producers(world):
    world.run("workshop('Carpenters', nil, false); planned('BED')")  # still under construction
    assert world.rows()["BED"]["producers"] in ([], {})  # an empty Lua table is either


def test_a_reaction_job_is_matched_by_the_reactions_own_products(world):
    world.run("""
      df.global.world.raws.reactions.reactions = {{code = 'BREW_DRINK_FROM_PLANT', products = {{item_type = df.item_type.DRINK}}}}
      JOBS_BY_KIND.Still = {[1] = entry('CustomReaction', 'BREW_DRINK_FROM_PLANT')}
      workshop('Still'); planned('DRINK')
    """)
    assert world.rows()["DRINK"]["producers"] == [
        {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT", "workshop_kind": "Still"}
    ]


def test_a_wildcard_element_names_no_kind_and_is_skipped(world):
    world.run("workshop('Carpenters'); planned('BED', 1, {{item_type = -1, quantity = 1}})")
    assert set(world.rows()) == {"BED"}


def test_a_building_that_is_not_planned_is_ignored(world):
    world.run("workshop('Carpenters'); local b = planned('BED'); PLANNED[b] = nil")
    assert world.read()["unsupplied"] == {} or world.read()["unsupplied"] == []


def test_an_unreadable_stock_read_leaves_available_null_and_says_so(world):
    world.run("workshop('Carpenters'); planned('BED'); AVAIL.BED = 'error'")
    r = world.read()
    row = r["unsupplied"][0]
    assert "available" not in row
    assert any("BED" in f for f in r["read_failures"])


def test_a_failed_getjobs_is_reported_not_silently_empty(world):
    world.run("workshop('Carpenters'); planned('BED'); JOBS_BY_KIND.Carpenters = 'error'")
    r = world.read()
    assert any("getJobs failed" in f for f in r["read_failures"])


def test_without_buildingplans_lua_api_it_errors_rather_than_reading_nothing(world):
    world.run("BUILDINGPLAN.isPlannedBuilding = nil; workshop('Carpenters')")
    assert "buildingplan" in world.read()["error"]
