"""handoffs/2026-09-30-reservation-gaps.md item 1: "Finders skip reserved
ground everywhere." df-overseer-building.lua, df-overseer-zone.lua,
df-overseer-farm.lua, df-overseer-well.lua and df-overseer-workshop.lua each
rank candidate sites without skipping reserved ones before this stream, so
their own build path would choose a reserved tile and then refuse it rather
than skipping to the next candidate. The fix, in every one of the five
files' own ranking function (`ranked_sites`/`ranked_rects`/
`ranked_water_bodies`/`ranked_candidates`), is one call to the shared
`reservations_mod.filter_reserved` -- the exact helper
df-overseer-diggable.lua's and df-overseer-openarea.lua's own ranking
functions already used before this stream (handoffs/2026-09-30-reservation-
holding.md's own "Finders wired" section), so `filter_reserved` itself is
already thoroughly covered by tests/test_reservations_lua_logic.py.

What this file proves, and why only ONE of the five goes through its own
real tool file (the handoff's own "at least one run through the real tool
file where stubs exist; the rest may go through the shared helper, say
which"):

- df-overseer-well.lua's real `ranked_candidates` (shared by find_well and
  build_well), loaded here and run against a small fake DFHack world plus
  the REAL df-overseer-reservations.lua (a dependency-free leaf; see
  tests/lua_stubs/dfhack_well_reservations_world.lua's own header for why
  loading it for real, rather than faking it a second time, is the safer
  choice). This is the "at least one real tool file" case: well's own
  terrain predicate (is_well_tile) is the smallest honest surface to model
  of the five (no quickfort internal validator table the way
  df-overseer-building.lua's tile_ok needs).
- df-overseer-building.lua, df-overseer-zone.lua (both its rectangle and
  water-body ranking), df-overseer-farm.lua and df-overseer-workshop.lua are
  NOT re-proven end to end here: none has an existing fake game-map-world
  stub (building.lua's tile_ok needs 'internal/quickfort/build''s own
  is_valid_tile_fn; zone.lua's zone_tile needs df.civzone_type and
  dfhack.buildings; farm.lua's/workshop.lua's find_candidates need their own
  plant/walkable checks) -- building one under time pressure risks exactly
  the "modelled the wrong field" failure mode this repo's own handoffs
  repeatedly warn about. Instead, each file's own ranking function's source
  is checked by direct inspection (asserted below) to call
  `reservations_mod.filter_reserved` with the same shape used everywhere
  else: raw candidates, the call's own `res_id`, and a `tiles_for` closure
  built from `reservations_mod.rect_tiles` (or, for zone.lua's water-body
  path, a converted `c.tiles` list, since a water body is not rectangular).

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
STUBS = Path(__file__).resolve().parent / "lua_stubs"
WELL_LUA = SCRIPTS / "df-overseer-well.lua"
RESERVATIONS_LUA = SCRIPTS / "df-overseer-reservations.lua"
WELL_STUB = STUBS / "dfhack_well_reservations_world.lua"


def _upvalue_by_name(lua, fn, name):
    getter = lua.eval("""
        function(fn, name)
          local i = 1
          while true do
            local n, v = debug.getupvalue(fn, i)
            if n == nil then return nil end
            if n == name then return v end
            i = i + 1
          end
        end
    """)
    return getter(fn, name)


class WellWorld:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        load = self.lua.eval("function(src, name) return load(src, name) end")
        stub_chunk = load(WELL_STUB.read_text(encoding="utf-8"), "well_world")
        stub_chunk(str(RESERVATIONS_LUA))
        well_chunk = load(WELL_LUA.read_text(encoding="utf-8"), "well.lua")
        well_chunk()
        g = self.lua.globals()
        self.build_well = g["build_well"]
        self.ranked_candidates = _upvalue_by_name(self.lua, self.build_well, "ranked_candidates")
        self.reservations_mod = _upvalue_by_name(self.lua, self.build_well, "reservations_mod")
        assert self.ranked_candidates is not None
        assert self.reservations_mod is not None

    def run(self, code):
        return self.lua.execute(code)

    def set_shape(self, x, y, z, shape):
        self.lua.eval("function(x,y,z,s) return set_shape(x,y,z,s) end")(x, y, z, shape)

    def set_flow(self, x, y, z, flow):
        self.lua.eval("function(x,y,z,f) return set_flow(x,y,z,f) end")(x, y, z, flow)

    def create_reservation(self, **rec):
        table = self.lua.table_from(rec)
        return self.reservations_mod.create(table)

    def candidates(self, level, near, radius, res_id):
        chosen, err, z = self.ranked_candidates(level, near, radius, res_id)
        return chosen, err, z


def _make_candidate(world, x, y, z):
    world.set_shape(x, y, z, "EMPTY")
    world.set_shape(x, y + 1, z, "FLOOR")
    world.set_flow(x, y, z - 1, 7)


def test_well_ranked_candidates_drops_a_reserved_tile_without_res_id():
    """The real ranked_candidates (shared by find_well/build_well): three
    well-eligible tiles near the anchor, closest reserved. Without RES_ID
    the reserved tile never appears at all -- it is not merely re-sorted
    lower, per the handoff's own "RANK N never lands on reserved ground"."""
    w = WellWorld()
    _make_candidate(w, 5, 5, 5)   # dist 0 from anchor (5,5,5) -- reserved below
    _make_candidate(w, 6, 5, 5)   # dist 1
    _make_candidate(w, 7, 5, 5)   # dist 2
    handle = w.create_reservation(x=5, y=5, z=5, w=1, h=1, purpose="a planned bedroom")
    assert handle == "res-1"

    chosen, err, z = w.candidates(0, "Anchor", 10, None)
    assert err is None
    xs = [c["x"] for c in chosen.values()] if hasattr(chosen, "values") else [c["x"] for c in chosen]
    assert 5 not in xs
    assert xs[0] == 6  # the next-closest becomes rank 1, not "rank 2 after a refusal"
    assert 7 in xs


def test_well_ranked_candidates_keeps_the_holders_own_reservation():
    """With the reservation's own handle as RES_ID, the reserved tile is
    kept (and, being closest, is rank 1) -- decision 4/item 2's "with RES_ID,
    candidates inside that reservation are kept"."""
    w = WellWorld()
    _make_candidate(w, 5, 5, 5)
    _make_candidate(w, 6, 5, 5)
    handle = w.create_reservation(x=5, y=5, z=5, w=1, h=1, purpose="a planned bedroom")

    chosen, err, z = w.candidates(0, "Anchor", 10, handle)
    assert err is None
    xs = [c["x"] for c in chosen.values()] if hasattr(chosen, "values") else [c["x"] for c in chosen]
    assert xs[0] == 5


def test_well_ranked_candidates_unaffected_by_an_unrelated_reservation():
    """A reservation elsewhere on the map never drops a candidate outside
    it -- filter_reserved only drops what actually overlaps."""
    w = WellWorld()
    _make_candidate(w, 5, 5, 5)
    w.create_reservation(x=40, y=40, z=5, w=2, h=2, purpose="somewhere else entirely")

    chosen, err, z = w.candidates(0, "Anchor", 10, None)
    assert err is None
    xs = [c["x"] for c in chosen.values()] if hasattr(chosen, "values") else [c["x"] for c in chosen]
    assert xs == [5]


# ---------------------------------------------------------------------------
# building.lua / zone.lua / farm.lua / workshop.lua: no fake game-map-world
# stub exists for any of these four files' own ranking functions (see this
# file's own module docstring for why one was not built under time
# pressure). Each is instead checked by direct source inspection: its own
# ranking function calls the same `reservations_mod.filter_reserved` helper,
# with the same "raw candidates, this call's own res_id, a rect_tiles (or,
# for zone's water path, a converted tile-list) closure" shape already
# proven correct by tests/test_reservations_lua_logic.py's own dedicated
# filter_reserved tests.
# ---------------------------------------------------------------------------

def _source(name):
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_building_ranked_sites_calls_filter_reserved_before_sorting():
    src = _source("df-overseer-building.lua")
    fn = src[src.index("local function ranked_sites"): src.index("local function site_info")]
    assert "reservations_mod.filter_reserved(candidates, res_id," in fn
    assert "reservations_mod.rect_tiles(c.x, c.y, z, w, h)" in fn
    # find_kind passes nil (no RES_ID argument exists on that command);
    # build_kind passes its own res_id.
    assert "ranked_sites(k, dw, dh, level, near, radius_tiles, nil)" in src
    assert "ranked_sites(k, dw, dh, level, near, radius_tiles, res_id)" in src


def test_zone_ranked_rects_and_water_bodies_call_filter_reserved():
    src = _source("df-overseer-zone.lua")
    rects_fn = src[src.index("local function ranked_rects"): src.index("local function rect_site_info")]
    assert "reservations_mod.filter_reserved(candidates, res_id," in rects_fn
    assert "reservations_mod.rect_tiles(c.x, c.y, z, w, h)" in rects_fn
    assert "ranked_rects(k, p, dw, dh, level, near, radius_tiles, furniture_ids, nil)" in src
    assert "ranked_rects(k, p, dw, dh, level, near, radius_tiles, furniture_ids, res_id)" in src

    water_fn = src[src.index("local function ranked_water_bodies"): src.index("-- Writes a throwaway")]
    assert "reservations_mod.filter_reserved(components, res_id, function(c)" in water_fn
    assert "t.x = t[1], t[2], z" not in water_fn  # sanity: not asserting a typo'd conversion
    assert "tiles[#tiles + 1] = {x = t[1], y = t[2], z = z}" in water_fn
    assert "ranked_water_bodies(level, near, radius_tiles, nil)" in src
    assert "ranked_water_bodies(level, near, radius_tiles, res_id)" in src


def test_farm_ranked_candidates_calls_filter_reserved():
    src = _source("df-overseer-farm.lua")
    fn = src[src.index("local function ranked_candidates"): src.index("for _, c in ipairs(candidates) do\n    local dx, dy = c.x - ax")]
    assert "reservations_mod.filter_reserved(candidates, res_id," in fn
    assert "reservations_mod.rect_tiles(c.x, c.y, z, w, h)" in fn
    assert "ranked_candidates(w, h, level, near, radius_tiles, nil)" in src
    assert "ranked_candidates(w, h, level, near, radius_tiles, res_id)" in src


def test_workshop_ranked_candidates_calls_filter_reserved():
    src = _source("df-overseer-workshop.lua")
    fn = src[src.index("local function ranked_candidates"): src.index("local function parse_quickfort_stats")]
    assert "reservations_mod.filter_reserved(candidates, res_id," in fn
    assert "reservations_mod.rect_tiles(c.x, c.y, z, w, h)" in fn
    assert "ranked_candidates(w, h, level, near, radius_tiles, nil)" in src
    assert "ranked_candidates(w, h, level, near, radius_tiles, res_id)" in src
