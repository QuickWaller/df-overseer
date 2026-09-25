"""Runs the REAL scripts/dfhack/df-overseer-workjob.lua `queue_job` against a
small fake DFHack world, using lupa.

handoffs/2026-09-25-tool-gaps-from-first-cycle.md item 1: a wildcard
(tag-matched) reagent, such as the empty food storage container every brew
reaction carries, can be resolved to a real free item by an explicit
`N:ITEM_ID` or `N:auto` choice, and is still refused, with the exact argument
that would resolve it, when no choice is given.

This proves the file's own logic (candidate selection from data, refusals,
what is written into the job_item). It proves nothing about the real game:
the real item flags, `isFoodStorage`, and DF accepting the resulting job are
the live check in the handoff Result.

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
local ITEM_TYPES = enum({"BARREL", "BLOCKS", "POT", "BOX"})
df = {
  item_type = ITEM_TYPES,
  job_type = enum({"CustomReaction", "ConstructBlocks"}),
  building_type = enum({"Workshop", "Furnace"}),
  workshop_type = enum({"Still"}),
  furnace_type = enum({}),
  job_item = {new = function() return {flags1 = {}, flags2 = {}, flags3 = {}} end},
  global = {world = {items = {all = {}}, buildings = {all = {}}}},
}
CONTAINED = {}          -- item id -> list of contained items
STORAGE = {}            -- item id -> isFoodStorage result (true/false/"error")
ATTACHED = {}
dfhack = {
  buildings = {getName = function(b) return b.name end},
  items = {getContainedItems = function(item) return CONTAINED[item.id] or {} end},
  job = {
    createLinked = function() return {job_items = {elements = {insert = function(self, _, ji) table.insert(ATTACHED, ji) end}}, flags = {}, id = 77} end,
    assignToWorkshop = function() return true end,
    removeJob = function() end,
  },
  printerr = function() end,
}
local json = {encode = function() return "" end}
package.loaded['json'] = json
package.loaded['utils'] = {listpairs = function() return function() end end}
package.loaded['dfhack.workshops'] = {getJobs = function() return BREW_JOBS end}
function reqscript(name)
  if name == 'df-overseer-textutil' then return {to_utf8 = function(x) return x end} end
  return {}
end
_G.require = function(n) return package.loaded[n] end

function add_item(id, kind, flags, storage)
  local it = {id = id, flags = flags or {}}
  function it:getType() return ITEM_TYPES[kind] end
  function it:getSubtype() return -1 end
  function it:isFoodStorage()
    local v = STORAGE[id]
    if v == "error" then error("boom") end
    return v
  end
  STORAGE[id] = storage
  table.insert(df.global.world.items.all, it)
  return it
end

function reset_world()
  df.global.world.items.all = {}
  CONTAINED = {}; STORAGE = {}; ATTACHED = {}
  df.global.world.buildings.all = {{
    name = "Still", flags = {exists = true}, jobs = {}, type = 0,
    getType = function() return df.building_type.Workshop end,
  }}
  -- the three-brew shape: one wildcard container reagent (item_type -1)
  BREW_JOBS = {[1] = {
    name = "Brew drink from plant",
    job_fields = {job_type = df.job_type.CustomReaction, reaction_name = "BREW_DRINK_FROM_PLANT"},
    items = {{item_type = -1, item_subtype = -1, mat_type = -1, mat_index = -1, quantity = 1,
              min_dimension = -1, metal_ore = -1, has_tool_use = -1, flags4 = 0, flags5 = 0,
              flags1 = {empty = true}, flags2 = {}, flags3 = {food_storage = true}}},
  }}
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
        self.g = self.lua.globals()
        self.lua.execute("reset_world()")

    def run(self, code):
        return self.lua.execute(code)

    def queue(self, dry_run="true", choices=None, count=None):
        arr = self.lua.table_from(choices or [])
        r = self.g["queue_job"]("reaction:brew_drink_from_plant", "Still", dry_run, None, count, arr)
        if isinstance(r, tuple):
            r, err = r
            return {"error": err} if r is None else _py(r)
        return _py(r)

    def attached(self):
        return _py(self.lua.eval("ATTACHED"))


@pytest.fixture
def w():
    return World()


def test_with_no_choice_the_wildcard_is_refused_naming_the_exact_argument(w):
    w.run("add_item(10, 'BARREL', {}, true); add_item(11, 'POT', {}, true)")
    r = w.queue()
    msg = r["error"]
    assert "wildcard reagent" in msg and "refusing to guess" in msg
    assert '"1:10"' in msg and '"1:auto"' in msg
    assert "10 (BARREL)" in msg and "11 (POT)" in msg


def test_auto_takes_the_lowest_id_and_says_why_and_narrows_the_job_item(w):
    w.run("add_item(12, 'POT', {}, true); add_item(10, 'BARREL', {}, true)")
    r = w.queue(choices=["1:auto"])
    assert "error" not in r, r
    d = r["job_item_diagnostics"][0]
    assert d["chosen_item_id"] == 10 and d["item_type"] == "BARREL"
    assert "auto" in d["chosen_how"] and "2 free candidate" in d["chosen_how"]
    assert r["would_queue"] is True and r["dry_run"] is True


def test_an_explicit_item_id_is_honoured_and_written_into_the_real_job_item(w):
    w.run("add_item(10, 'BARREL', {}, true); add_item(11, 'POT', {}, true)")
    r = w.queue(dry_run="false", choices=["1:11"])
    assert r["create_ok"] is True, r
    assert r["job_item_diagnostics"][0]["chosen_item_id"] == 11
    ji = w.attached()[0]
    # narrowed to the chosen item's type, the recipe's own flags kept
    assert ji["item_type"] == 2 and ji["flags1"]["empty"] is True and ji["flags3"]["food_storage"] is True


def test_items_that_are_not_free_or_do_not_satisfy_the_flags_are_never_offered(w):
    w.run(
        "add_item(1, 'BARREL', {in_job = true}, true);"       # already in a job
        "add_item(2, 'BARREL', {forbid = true}, true);"       # forbidden
        "add_item(3, 'BOX', {}, false);"                      # not food storage
        "add_item(4, 'BARREL', {}, true); CONTAINED[4] = {{}};"  # not empty
        "add_item(5, 'BARREL', {}, 'error');"                  # unreadable: unknown is not a yes
        "add_item(6, 'POT', {}, true)"
    )
    r = w.queue(choices=["1:auto"])
    assert r["job_item_diagnostics"][0]["chosen_item_id"] == 6
    bad = w.queue(choices=["1:4"])
    assert "not a free item" in bad["error"] and "1 such candidate" in bad["error"]


def test_no_free_candidate_says_so_instead_of_guessing(w):
    w.run("add_item(1, 'BARREL', {in_job = true}, true)")
    assert "nothing to choose" in w.queue()["error"]
    assert "found no free item" in w.queue(choices=["1:auto"])["error"]


def test_a_flag_with_no_check_is_unverifiable_and_refused_even_with_auto(w):
    w.run(
        "BREW_JOBS[1].items[1].flags3 = {food_storage = true, some_unknown_tag = true};"
        "add_item(10, 'BARREL', {}, true)"
    )
    for choices in ([], ["1:auto"], ["1:10"]):
        msg = w.queue(choices=choices)["error"]
        assert "some_unknown_tag" in msg and "cannot" in msg


def test_a_reagent_with_no_flags_never_offers_every_item(w):
    w.run("BREW_JOBS[1].items[1].flags1 = {}; BREW_JOBS[1].items[1].flags3 = {}; add_item(10, 'BARREL', {}, true)")
    assert "no flags at all" in w.queue(choices=["1:auto"])["error"]


def test_malformed_choice_words_are_refused_by_name(w):
    w.run("add_item(10, 'BARREL', {}, true)")
    for bad in ("auto", "1:", "x:5", "0:5", "1:bar"):
        assert bad in w.queue(choices=[bad])["error"]


def test_a_choice_for_a_concrete_reagent_is_ignored_not_an_error(w):
    w.run("BREW_JOBS[1].items[1].item_type = 1")  # BLOCKS: concrete
    r = w.queue(choices=["1:auto"])
    assert "error" not in r and "chosen_item_id" not in r["job_item_diagnostics"][0]
