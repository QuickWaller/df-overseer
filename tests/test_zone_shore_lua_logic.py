"""Runs the REAL scripts/dfhack/df-overseer-zone.lua (find and place for
WaterSource and FishingArea) against a fake tile world
(tests/lua_stubs/dfhack_shore_world.lua) using lupa.

handoffs/2026-10-07-shore-water-zones.md. Proves the finder's own logic: a
Water Source or Fishing zone is offered on dry ground beside water (the same
level, or the level above a sunken pool), never on the water itself, and a
placement with no water in reach is refused. It proves nothing about what the
real game accepts for any adjacency the sources do not settle (diagonals):
that is the live check.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-zone.lua"
STUB = REPO_ROOT / "tests" / "lua_stubs" / "dfhack_shore_world.lua"


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
        load = self.lua.eval("function(src) return load(src, 'zone.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def run(self, code):
        return self.lua.execute(code)

    def call(self, name, *args):
        r = self.g[name](*args)
        if isinstance(r, tuple):
            return _py(r[0]), _py(r[1])
        return _py(r), None

    def find(self, kind, **kw):
        return self.call("find_zone_area", kind, None, None, kw.get("level"), "Spring", kw.get("radius", 12))

    def place(self, kind, **kw):
        # kind, w, h, level, near, rank, radius_tiles, dry_run
        return self.call("place_zone", kind, None, None, kw.get("level"), "Spring", kw.get("rank"),
                         kw.get("radius", 12), "true")


@pytest.fixture
def w():
    return World()


def tile_count(results):
    return sum(r["tile_count"] for r in results)


def sunken_pool(w):
    """Landmark on ground z5. A pool of water at z4 (x 20..22, y 20..22) ringed
    by walls at z4, with dry ground at z5 over everything."""
    w.run("fill(10, 10, 30, 30, 5, {shape='FLOOR'})")
    w.run("fill(18, 18, 24, 24, 4, {shape='WALL'})")
    w.run("fill(20, 20, 22, 22, 4, {shape='FLOOR', water=7})")


def test_upper_level_ground_beside_a_sunken_pool_is_offered(w):
    sunken_pool(w)
    res, err = w.find("WaterSource")
    assert err is None, err
    assert res, "the ground over and beside the pool must be offered"
    r = res[0]
    assert r["water_one_level_below"] is True
    assert r["water_same_level"] is False
    assert r["depth_max"] == 7
    # directly over the 3x3 pool plus its orthogonal ring one tile out
    # (below, or beside-and-below), never a diagonal-only corner
    assert r["tile_count"] == 9 + 12


def test_same_level_shore_is_offered_and_the_water_is_not(w):
    w.run("fill(10, 10, 30, 30, 5, {shape='FLOOR'})")
    w.run("fill(20, 20, 22, 22, 5, {shape='FLOOR', water=7})")
    res, err = w.find("WaterSource")
    assert err is None, err
    r = res[0]
    assert all(c["water_same_level"] is True for c in res)
    # the ring of orthogonal neighbours of a 3x3 pool is 12 tiles; the pool's own 9 are not offered
    assert tile_count(res) == 12


def test_open_water_itself_is_never_offered(w):
    # all water, no ground anywhere beside it
    w.run("fill(15, 15, 25, 25, 5, {shape='FLOOR', water=7})")
    res, err = w.find("WaterSource")
    assert err is None
    assert res == [] or res is None or len(res) == 0


def test_fishing_area_shares_the_finder(w):
    sunken_pool(w)
    ws, _ = w.find("WaterSource")
    fa, err = w.find("FishingArea")
    assert err is None, err
    assert tile_count(ws) == tile_count(fa) > 0
    assert fa[0]["token"] == "FishingArea"
    assert "caveat" not in fa[0]


def test_tile_with_no_water_in_reach_is_refused(w):
    w.run("fill(10, 10, 30, 30, 5, {shape='FLOOR'})")
    for kind in ("WaterSource", "FishingArea"):
        res, err = w.place(kind)
        assert res is None
        assert "refused" in err and "beside water" in err


def test_place_dry_run_on_shore_reports_without_writing(w):
    sunken_pool(w)
    res, err = w.place("WaterSource")
    assert err is None, err
    assert res["dry_run"] is True
    assert res["would_zone_tiles"] == 21


def test_diagonal_only_ground_is_not_offered(w):
    # one water tile at z5; the only candidate would be diagonal to it
    w.run("fill(18, 18, 22, 22, 5, {shape='WALL'})")
    w.run("set_tile(20, 20, 5, {shape='FLOOR', water=7})")
    w.run("set_tile(21, 21, 5, {shape='FLOOR'})")
    res, err = w.find("WaterSource")
    assert err is None
    assert not res


def test_building_hidden_and_already_zoned_ground_is_skipped(w):
    w.run("fill(10, 10, 30, 30, 5, {shape='FLOOR'})")
    w.run("set_tile(20, 20, 5, {shape='FLOOR', water=7})")
    w.run("add_building(21, 20, 5)")
    w.run("set_tile(19, 20, 5, {shape='FLOOR', hidden=true})")
    w.run("add_zone_at(20, 21, 5, 'WaterSource')")
    res, err = w.find("WaterSource")
    assert err is None
    assert tile_count(res) == 1   # only (20, 19) survives
    # a Fishing zone is a different type, so the Water Source zone does not block it
    res, _ = w.find("FishingArea")
    assert tile_count(res) == 2


def test_ramp_top_beside_water_counts_as_standable(w):
    # getWalkableGroup reads 0 for ramp shapes on this build; the shape rescues them
    w.run("fill(10, 10, 30, 30, 5, {shape='WALL'})")
    w.run("set_tile(20, 20, 5, {shape='FLOOR', water=7})")
    w.run("set_tile(21, 20, 5, {shape='RAMP_TOP'})")
    res, err = w.find("WaterSource")
    assert err is None
    assert res[0]["tile_count"] == 1


def test_w_h_still_refused(w):
    sunken_pool(w)
    res, err = w.call("find_zone_area", "FishingArea", 3, 3, None, "Spring", 12)
    assert res is None and "takes no W H" in err
