"""Runs the REAL scripts/dfhack/df-overseer-building.lua `apply_material_filters`
(and `resolve_material_choice`'s new `filter_material_names` output, via
`requirements_for`/`building_filters_and_gaps`) against a small fake DFHack
world, using lupa.

handoffs/2026-10-01-buildingplan-material-filter.md: the register's
2026-09-30 ruling is that this layer chooses a material CLASS and writes it
into buildingplan's own filter (`plugins.buildingplan`'s `setMaterialFilter`/
`getMaterialFilter`, DFHack `53.16-r1` `plugins/buildingplan/buildingplan.cpp`
lines 900-1010ish); the game picks the exact item. Before this fix
`building.build`'s blueprint carried no material at all, so buildingplan
attached the closest item, which could be ore
(evals/live/2026-09-30-reservations-deploy/README.md, correction).

This proves the OFFLINE logic: which materials get written, that a
set-for-the-call-and-restore round trip calls `setMaterialFilter` with the
prior state afterwards, and that an empty class is never written (which
would otherwise mean "no restriction" to buildingplan, not "restrict to
nothing" -- see the file's own header comment on this exact trap). It proves
nothing about the real game: whether `setMaterialFilter`'s material-name
list is honoured by a running fort's item search is a live test
(research/2026-09-30-item-binding-design.md section 5, and this stream's
Result).

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

dfhack = {
  matinfo = {decode = function() error("not used by these tests") end},
  buildings = {
    getFiltersByType = function(_, btype, sub, cust) return FILTERS or {} end,
  },
}

-- Records every call this stream's code makes into plugins.buildingplan's
-- setMaterialFilter/getMaterialFilter, so a test can assert on them directly
-- -- this IS the "stub that fails if the filter call is missing": any test
-- below asserting on #CALLS or a specific recorded call fails outright if
-- apply_material_filters never calls through to these.
CALLS = {}
GET_RESPONSES = {}  -- keyed "type:sub:cust:index" -> {name = "true"/"false", ...} map, or nil

local function key(t, s, c, i) return tostring(t) .. ":" .. tostring(s) .. ":" .. tostring(c) .. ":" .. tostring(i) end

function set_get_response(t, s, c, i, resp)
  GET_RESPONSES[key(t, s, c, i)] = resp
end

-- Plain fields, no metatable indirection: a test that sets one of these to
-- nil must actually remove it, with no fallback lookup resurrecting it.
package.loaded['plugins.buildingplan'] = {
  isEnabled = function() return true end,
  setMaterialFilter = function(t, s, c, i, names)
    CALLS[#CALLS + 1] = {op = "set", type = t, subtype = s, custom = c, index = i, names = names}
  end,
  getMaterialFilter = function(t, s, c, i)
    CALLS[#CALLS + 1] = {op = "get", type = t, subtype = s, custom = c, index = i}
    return GET_RESPONSES[key(t, s, c, i)]
  end,
}

local json = {encode = function() return "" end}
package.loaded['json'] = json
package.loaded['df-overseer-landmarks'] = {}
package.loaded['df-overseer-stocks'] = {
  get_availability = function() return {total_units = 0, available_units = 0} end,
}
function reqscript(name) return package.loaded[name] or {} end
_G.require = function(n) return package.loaded[n] end

function reset_calls()
  CALLS = {}
  GET_RESPONSES = {}
end
"""


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if not keys:
        return []  # an empty Lua table is this codebase's empty list, never an object
    if all(isinstance(k, int) for k in keys) and keys == list(range(1, len(keys) + 1)):
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
        self.apply_material_filters = self.g["apply_material_filters"]
        assert self.apply_material_filters is not None, (
            "apply_material_filters is not exported as a global function; "
            "the filter-write mechanism is missing"
        )
        self.lua.execute("reset_calls()")

    def set_get_response(self, t, s, c, i, resp):
        fn = self.lua.eval("function(t, s, c, i, r) set_get_response(t, s, c, i, r) end")
        self.lua.eval(
            "function(t, s, c, i, r) set_get_response(t, s, c, i, r) end"
        )(t, s, c, i, self.lua.table_from(resp, recursive=True) if resp is not None else None)

    def apply(self, btype, sub, cust, filter_recs):
        recs = self.lua.table_from(
            [self.lua.table_from(r, recursive=True) for r in filter_recs]
        )
        report, restore = self.apply_material_filters(btype, sub, cust, recs)
        return _py(report), restore

    @property
    def calls(self):
        return _py(self.lua.globals()["CALLS"])


@pytest.fixture
def w():
    return World()


# ---------------------------------------------------------------------------
# apply_material_filters: the write
# ---------------------------------------------------------------------------


def test_writes_the_class_into_buildingplans_filter(w):
    report, _ = w.apply(0, 1, -1, [{"index": 1, "filter_material_names": ["SHALE", "MARBLE"]}])

    calls = w.calls
    set_calls = [c for c in calls if c["op"] == "set"]
    assert len(set_calls) == 1, "setMaterialFilter was never called: the class was not written"
    c = set_calls[0]
    assert c["type"] == 0 and c["subtype"] == 1 and c["custom"] == -1
    # index is 1-based in this file's own rec shape; buildingplan's own API
    # is 0-based (see the source quoted in the header comment).
    assert c["index"] == 0
    assert set(c["names"]) == {"SHALE", "MARBLE"}
    assert report["applied"][0]["ok"] is True


def test_reads_the_prior_state_before_writing(w):
    w.apply(2, -1, -1, [{"index": 1, "filter_material_names": ["OAK"]}])
    calls = w.calls
    assert calls[0]["op"] == "get", "prior state must be read before the new class is written"
    assert calls[1]["op"] == "set"


def test_an_empty_class_is_never_written(w):
    # An empty names list would tell buildingplan "no restriction" (see the
    # file's own header comment on ItemFilter::matches's empty-list branch),
    # the opposite of what an empty resolved class should mean here.
    report, _ = w.apply(0, 0, -1, [{"index": 1, "filter_material_names": {}}])
    assert w.calls == []
    assert report["applied"] == []


def test_a_filter_rec_with_no_filter_material_names_key_is_skipped(w):
    # e.g. a plain item-type filter that never went through
    # resolve_material_choice at all.
    report, _ = w.apply(0, 0, -1, [{"index": 1}])
    assert w.calls == []


# ---------------------------------------------------------------------------
# restore(): the "set for the call, restore after" contract
# ---------------------------------------------------------------------------


def test_restore_writes_back_the_exact_prior_material_list(w):
    w.set_get_response(0, 1, -1, 0, {
        "SHALE": {"enabled": "true"},
        "HEMATITE": {"enabled": "false"},
        "MARBLE": {"enabled": "false"},
    })
    _, restore = w.apply(0, 1, -1, [{"index": 1, "filter_material_names": ["OAK"]}])
    restored = _py(restore())

    set_calls = [c for c in w.calls if c["op"] == "set"]
    assert len(set_calls) == 2, "restore() must call setMaterialFilter a second time"
    restore_call = set_calls[-1]
    assert restore_call["names"] == ["SHALE"]  # the one name that was enabled before
    assert restored[0]["ok"] is True


def test_restore_writes_back_empty_when_prior_state_was_unrestricted(w):
    # Every name reads "true": buildingplan.cpp's own semantics for an empty
    # mat_filter (matches anything) -- see the header comment's reasoning.
    w.set_get_response(0, 1, -1, 0, {
        "SHALE": {"enabled": "true"},
        "HEMATITE": {"enabled": "true"},
    })
    _, restore = w.apply(0, 1, -1, [{"index": 1, "filter_material_names": ["OAK"]}])
    restore()

    set_calls = [c for c in w.calls if c["op"] == "set"]
    assert set_calls[-1]["names"] == []


def test_restore_is_a_noop_when_nothing_was_applied(w):
    _, restore = w.apply(0, 0, -1, [{"index": 1, "filter_material_names": {}}])
    assert _py(restore()) == []
    assert w.calls == []


def test_buildingplan_unavailable_is_reported_not_silently_skipped(w):
    w.lua.execute("package.loaded['plugins.buildingplan'].setMaterialFilter = nil")
    report, restore = w.apply(0, 0, -1, [{"index": 1, "filter_material_names": ["OAK"]}])
    assert "skipped" in report
    assert "buildingplan" in report["skipped"]
    assert _py(restore()) == []
