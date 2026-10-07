"""df-overseer-labor.lua `unit-status`: every output path is ONE JSON object.

Found live 2026-10-08 (evals/live/2026-10-08-manager-appointment/README.md,
side findings): the idle filter printed "CITIZEN id=..." text lines plus a
"-- N result(s) --" trailer, which the MCP layer could not parse, so the
Overseer's call errored. Loads the REAL script against a small fake world and
captures what `print` receives for the unfiltered, idle, injured, military,
hostile, empty-result and bad-filter paths, then json.loads the captured stdout.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import json
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

LABOR_LUA = (Path(__file__).resolve().parent.parent
             / "scripts" / "dfhack" / "df-overseer-labor.lua")

STUB = r"""
dfhack_flags = {module = true}
df = {unit_labor = {_first_item = -1, _last_item = -1}}
df.global = {world = {units = {active = {
  {id = 90, race = "GOBLIN", danger = true, own = false, hidden = false, invader = true},
  {id = 91, race = "DWARF", danger = true, own = true, hidden = false, invader = false},
  {id = 92, race = "TROLL", danger = true, own = false, hidden = true, invader = false},
}}}}

package.loaded["json"] = {encode = function(t) return PY_ENCODE(t) end}

local function unit(id, job, wounds, squad)
  return {id = id, job = {current_job = job}, body = {wounds = wounds},
          military = {squad_id = squad}}
end
CITIZENS = {
  unit(1, nil, {}, -1),          -- idle
  unit(2, {name = "Mine"}, {1, 2}, -1),  -- busy, injured
  unit(3, {name = "Haul"}, {}, 5),       -- busy, military
}

function require(n) return package.loaded[n] or {} end
function reqscript(n)
  if n == "df-overseer-textutil" then
    return {to_utf8 = function(s) return s end}
  end
  return {nearest_landmark = function() return {name = "the Well", direction = "N", distance_tiles = 4} end}
end

dfhack = {
  units = {
    getCitizens = function() return CITIZENS end,
    getPosition = function() return 1, 2, 3 end,
    getProfessionName = function() return "Miner" end,
    getRaceName = function(u) return u.race end,
    isHidden = function(u) return u.hidden end,
    isDanger = function(u) return u.danger end,
    isOwnCiv = function(u) return u.own end,
    isInvader = function(u) return u.invader end,
  },
  job = {getName = function(j) return j.name end},
}
"""


def _to_py(v):
    if hasattr(v, "items"):
        items = dict(v.items())
        if items and all(isinstance(k, int) for k in items):
            return [_to_py(items[k]) for k in sorted(items)]
        return {k: _to_py(x) for k, x in items.items()}
    return v


def run(*args, citizens=None):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().PY_ENCODE = lambda t: json.dumps(_to_py(t))
    printed = []
    lua.globals().print = lambda *a: printed.append(" ".join(str(x) for x in a))
    load = lua.eval("function(src, name) return load(src, name) end")
    load(STUB, "stub")()
    if citizens == []:
        lua.execute("CITIZENS = {}")
    # Script reads its arguments through `{...}`.
    chunk = load(LABOR_LUA.read_text(encoding="utf-8"), "labor.lua")
    chunk(*args)
    return printed


def one_object(printed):
    assert len(printed) == 1, printed
    obj = json.loads(printed[0])
    assert isinstance(obj, dict)
    return obj


def test_idle_filter_is_one_json_object():
    obj = one_object(run("unit-status", "idle"))
    assert obj["count"] == 1
    assert [c["id"] for c in obj["citizens"]] == [1]
    assert obj["citizens"][0]["idle"] is True
    assert obj["citizens"][0]["near_landmark"] == "the Well"


def test_unfiltered_lists_all_citizens_as_json():
    obj = one_object(run("unit-status"))
    assert obj["count"] == 3
    assert [c["id"] for c in obj["citizens"]] == [1, 2, 3]


def test_injured_and_military_filters():
    assert [c["id"] for c in one_object(run("unit-status", "injured"))["citizens"]] == [2]
    assert [c["id"] for c in one_object(run("unit-status", "military"))["citizens"]] == [3]


def test_hostile_filter_json_excludes_own_civ_and_hidden():
    obj = one_object(run("unit-status", "hostile"))
    assert obj["count"] == 1
    assert [t["id"] for t in obj["threats"]] == [90]
    assert obj["threats"][0]["invader"] is True


def test_empty_result_is_still_json():
    obj = one_object(run("unit-status", "idle", citizens=[]))
    assert obj["count"] == 0


def test_bad_filter_is_json_error():
    obj = one_object(run("unit-status", "bogus"))
    assert "usage" in obj["error"]
