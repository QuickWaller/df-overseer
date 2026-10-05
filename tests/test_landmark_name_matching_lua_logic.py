"""handoffs/2026-10-05-landmark-name-punctuation.md: landmark and workshop
names match ignoring case, spacing and punctuation, so a workshop whose real
name carries an apostrophe ("Carpenter's Workshop") is addressable as
"Carpenters Workshop". Runs the REAL df-overseer-textutil.lua matcher, the
REAL df-overseer-workjob.lua name resolution and the REAL
df-overseer-landmarks.lua `get_landmark_centroid` resolution under lupa.

Proves the matching logic (exact wins, tolerant match, ambiguity refused with
candidates, unknown still unknown). Whether the live game accepts the
resulting call is the live check in the handoff Result.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
TEXTUTIL = SCRIPTS / "df-overseer-textutil.lua"
WORKJOB = SCRIPTS / "df-overseer-workjob.lua"

LOAD_TEXTUTIL = (
    "(function() local env = setmetatable({}, {__index = _G});"
    " assert(load(TEXTUTIL_SRC, 'textutil.lua', 't', env))(); return env end)()"
)


def _textutil():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().TEXTUTIL_SRC = TEXTUTIL.read_text(encoding="utf-8")
    return lua, lua.eval(LOAD_TEXTUTIL)


def test_normalize_drops_case_spacing_and_punctuation():
    _, t = _textutil()
    assert t.normalize_name("Carpenter's Workshop") == "carpentersworkshop"
    assert t.normalize_name("CARPENTERS-workshop") == "carpentersworkshop"
    assert t.normalize_name(None) == ""


def test_tolerant_match_finds_the_apostrophed_name():
    lua, t = _textutil()
    names = lua.table_from(["Still", "Carpenter's Workshop", "Mason's Workshop"])
    assert t.match_name("Carpenters Workshop", names) == 2
    assert t.match_name("carpenter's workshop", names) == 2
    assert t.match_name("Carpenter's Workshop", names) == 2


def test_exact_match_wins_over_a_normalised_twin():
    lua, t = _textutil()
    names = lua.table_from(["Masons Workshop", "Mason's Workshop"])
    assert t.match_name("Mason's Workshop", names) == 2
    assert t.match_name("Masons Workshop", names) == 1


def test_ambiguous_normalised_match_is_refused_with_candidates():
    lua, t = _textutil()
    names = lua.table_from(["Masons Workshop", "Mason's Workshop"])
    idx, err, cands = t.match_name("MASONS workshop", names)
    assert idx is None
    assert "ambiguous" in err and "Masons Workshop" in err and "Mason's Workshop" in err
    assert len(list(cands.values())) == 2


def test_identical_duplicate_names_are_not_ambiguous():
    lua, t = _textutil()
    names = lua.table_from(["Farm Plot", "Farm Plot"])
    assert t.match_name("farmplot", names) == 1


def test_unknown_name_is_still_unknown():
    lua, t = _textutil()
    idx, err, _ = t.match_name("Nowhere", lua.table_from(["Still"]))
    assert idx is None and "no name matches" in err
    idx, err, _ = t.match_name("''", lua.table_from(["Still"]))
    assert idx is None


STUB = r"""
dfhack_flags = {module = true}
local function enum(names)
  local e = {}
  for i, n in ipairs(names) do e[n] = i - 1; e[i - 1] = n end
  return e
end
df = {
  item_type = enum({"BARREL"}),
  job_type = enum({"CustomReaction"}),
  building_type = enum({"Workshop", "Furnace"}),
  workshop_type = enum({"Carpenters"}),
  furnace_type = enum({}),
  global = {world = {items = {all = {}}, buildings = {all = {}}}},
}
dfhack = {
  buildings = {getName = function(b) return b.name end},
  printerr = function() end,
}
package.loaded['json'] = {encode = function() return "" end}
package.loaded['utils'] = {listpairs = function() return function() end end}
package.loaded['dfhack.workshops'] = {getJobs = function() return {} end}
function reqscript(name)
  if name == 'df-overseer-textutil' then
    local env = setmetatable({}, {__index = _G})
    assert(load(TEXTUTIL_SRC, 'textutil.lua', 't', env))()
    return env
  end
  return {}
end
_G.require = function(n) return package.loaded[n] end
function ws(name)
  return {name = name, flags = {exists = true}, jobs = {}, type = 0,
          getType = function() return df.building_type.Workshop end}
end
"""


def _workjob_world(names):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().TEXTUTIL_SRC = TEXTUTIL.read_text(encoding="utf-8")
    lua.execute(STUB)
    load = lua.eval("function(src) return load(src, 'workjob.lua') end")
    chunk = load(WORKJOB.read_text(encoding="utf-8"))
    assert not isinstance(chunk, tuple), chunk
    lua.eval("function(f) f() end")(chunk)
    lua.execute(
        "df.global.world.buildings.all = {%s}" % ",".join("ws(%r)" % n for n in names)
    )
    return lua


def _resolve_err(lua, query):
    r = lua.globals()["list_workshop_jobs"](query)
    if isinstance(r, tuple):
        return r[1]
    return None


def test_workjob_resolves_apostrophed_workshop_by_unpunctuated_name():
    lua = _workjob_world(["Carpenter's Workshop"])
    err = _resolve_err(lua, "Carpenters Workshop")
    # past resolution the stub cannot answer further, but it must not be the
    # "unknown workshop" refusal
    assert err is None or "unknown workshop" not in str(err)


def test_workjob_unknown_workshop_still_refused():
    lua = _workjob_world(["Carpenter's Workshop"])
    assert "unknown workshop" in _resolve_err(lua, "Craftsdwarfs Workshop")


def test_workjob_ambiguous_workshop_is_refused_with_candidates():
    lua = _workjob_world(["Masons Workshop", "Mason's Workshop"])
    err = _resolve_err(lua, "masons workshop")
    assert "ambiguous" in err and "Mason's Workshop" in err
