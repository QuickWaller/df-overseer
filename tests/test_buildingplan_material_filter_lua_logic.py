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
--
-- 2026-10-01 (live silent-no-op fix): apply_material_filters now reads back
-- what it just wrote (verify_material_filter) and refuses+restores on a
-- mismatch, so this fake must behave STATEFULLY -- a getMaterialFilter call
-- after a setMaterialFilter call must reflect that write, exactly like the
-- real plugin, or every "ok is True" test below would spuriously start
-- failing the readback check the fix added. FILTER_STATE holds the currently
-- written set per key (nil = unrestricted, i.e. every UNIVERSE name enabled);
-- UNIVERSE is every name this key has ever seen, seeded by a test's
-- set_get_response (the "prior state" declaration) and grown by every write
-- -- a write's own names always end up in the universe, so a test that never
-- declares a prior state still gets an exact, matching readback.
CALLS = {}
GET_RESPONSES = {}  -- keyed "type:sub:cust:index" -> {name = "true"/"false", ...} map, or nil
FILTER_STATE = {}
UNIVERSE = {}
SEEDED = {}
-- VALID_NAMES[key] = nil means "buildingplan recognises anything written"
-- (every earlier test's assumption); a test that calls set_valid_names
-- restricts this fake to modelling the LIVE bug exactly: setMaterialFilter
-- silently drops any name buildingplan's own mat_cache would not recognise
-- (real ItemFilter::matches semantics -- an unrecognised-only write ends up
-- with zero accepted names, which is the SAME as writing an empty list:
-- "no restriction", never "restrict to nothing").
VALID_NAMES = {}

local function key(t, s, c, i) return tostring(t) .. ":" .. tostring(s) .. ":" .. tostring(c) .. ":" .. tostring(i) end

local function ensure_universe(k, names)
  UNIVERSE[k] = UNIVERSE[k] or {}
  for _, n in ipairs(names or {}) do UNIVERSE[k][n] = true end
end

function set_get_response(t, s, c, i, resp)
  GET_RESPONSES[key(t, s, c, i)] = resp
end

function set_valid_names(t, s, c, i, list)
  local set = {}
  for _, n in ipairs(list) do set[n] = true end
  VALID_NAMES[key(t, s, c, i)] = set
end

-- Plain fields, no metatable indirection: a test that sets one of these to
-- nil must actually remove it, with no fallback lookup resurrecting it.
package.loaded['plugins.buildingplan'] = {
  isEnabled = function() return true end,
  setMaterialFilter = function(t, s, c, i, names)
    local k = key(t, s, c, i)
    CALLS[#CALLS + 1] = {op = "set", type = t, subtype = s, custom = c, index = i, names = names}
    local valid = VALID_NAMES[k]
    local accepted = {}
    for _, n in ipairs(names or {}) do
      if valid == nil or valid[n] then accepted[#accepted + 1] = n end
    end
    ensure_universe(k, accepted)
    if #accepted == 0 then
      FILTER_STATE[k] = nil
    else
      local set = {}
      for _, n in ipairs(accepted) do set[n] = true end
      FILTER_STATE[k] = set
    end
  end,
  getMaterialFilter = function(t, s, c, i)
    local k = key(t, s, c, i)
    CALLS[#CALLS + 1] = {op = "get", type = t, subtype = s, custom = c, index = i}
    if not SEEDED[k] then
      SEEDED[k] = true
      local resp = GET_RESPONSES[k]
      if resp ~= nil then
        local names, restricted, any_false = {}, {}, false
        for name, props in pairs(resp) do
          names[#names + 1] = name
          if props.enabled == "true" then restricted[name] = true else any_false = true end
        end
        ensure_universe(k, names)
        if any_false then FILTER_STATE[k] = restricted end
      end
    end
    local universe = UNIVERSE[k] or {}
    local ret = {}
    for name in pairs(universe) do
      local enabled = (FILTER_STATE[k] == nil) or (FILTER_STATE[k][name] == true)
      ret[name] = {enabled = enabled and "true" or "false", category = "stone", count = "0"}
    end
    return ret
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
  FILTER_STATE = {}
  UNIVERSE = {}
  SEEDED = {}
  VALID_NAMES = {}
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

    def set_valid_names(self, t, s, c, i, names):
        arr = self.lua.table_from(names)
        self.lua.eval("function(t, s, c, i, n) set_valid_names(t, s, c, i, n) end")(t, s, c, i, arr)

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


# ---------------------------------------------------------------------------
# The live silent-no-op bug itself (2026-10-01): a write of names
# buildingplan's own mat_cache does not recognise is accepted by
# setMaterialFilter without error, but silently ends up restricting NOTHING.
# apply_material_filters must catch this by reading back what it just wrote
# and refusing (with a restore) on a mismatch -- never trusting the write
# call's own success alone.
# ---------------------------------------------------------------------------


def test_a_write_of_unrecognised_names_is_caught_by_the_readback_and_restored(w):
    # Models the exact live finding: buildingplan only knows "SHALE" for this
    # filter; a write of names it does NOT know (the shape this file's stock-
    # based naming used to produce) is accepted with no error but ends up
    # restricting nothing at all.
    w.set_valid_names(0, 1, -1, 0, ["SHALE"])
    report, restore = w.apply(
        0, 1, -1, [{"index": 1, "filter_material_names": ["WOOD", "material_0_243"]}]
    )
    entry = report["applied"][0]
    assert entry["ok"] is False, "an unrecognised-name write must never be reported as applied"
    assert "readback mismatch" in entry["error"]
    assert entry["restored_on_mismatch"] is True
    # Nothing to restore later: the mismatch was already fixed on the spot.
    assert _py(restore()) == []


def test_a_write_of_a_recognised_name_succeeds_and_reports_enabled_count(w):
    w.set_valid_names(0, 1, -1, 0, ["SHALE", "MARBLE"])
    report, _ = w.apply(0, 1, -1, [{"index": 1, "filter_material_names": ["SHALE"]}])
    entry = report["applied"][0]
    assert entry["ok"] is True
    assert entry["enabled_count"] == 1


def test_readback_reports_economic_enabled_without_crashing_when_unavailable(w):
    # This stub has no df.global.world.raws.inorganics (unlike
    # test_building_material_and_previously_built_lua_logic.py's stub), so
    # economic_inorganic_names() fails inside apply_material_filters; the
    # write/readback/match logic must still work and economic_enabled must
    # come back as an empty list, never a crash or a missing key.
    w.set_valid_names(0, 1, -1, 0, ["SHALE", "HEMATITE"])
    report, _ = w.apply(0, 1, -1, [{"index": 1, "filter_material_names": ["SHALE", "HEMATITE"]}])
    entry = report["applied"][0]
    assert entry["ok"] is True
    assert entry["economic_enabled"] == []
