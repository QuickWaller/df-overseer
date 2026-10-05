"""Runs the REAL scripts/dfhack/df-overseer-surface.lua `vein_material`/
`decode_vein_tile` against a small fake DFHack world, using lupa.

handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md: an ore vein
smoothed into a room's wall reads as ordinary MINERAL-class stone to every
existing surface tool. This proves the new `vein-material` read's OWN logic
(ring walk, three-state classification, honest "unknown" on any read
failure or unmatched vein event) against a fake world shaped like this
stream's best understanding of the real DFHack vein API. It proves NOTHING
about whether that API shape is real -- see the .lua file's own header
comment on `decode_vein_tile` and this stream's Result section.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-surface.lua"
STUB = (REPO_ROOT / "tests" / "lua_stubs" / "dfhack_surface_vein_world.lua").read_text(encoding="utf-8")


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
        load = self.lua.eval("function(src) return load(src, 'surface.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()
        get_upvalue = self.lua.eval("function(fn, n) return upvalue_by_name(fn, n) end")
        self._decode_vein_tile = get_upvalue(self.g["vein_material"], "decode_vein_tile")
        assert self._decode_vein_tile is not None

    def add_zone(self, id_, x1, y1, x2, y2, z=0):
        self.lua.eval("function(id, x1, y1, x2, y2, z) return add_zone(id, x1, y1, x2, y2, z) end")(
            id_, x1, y1, x2, y2, z
        )

    def set_tile(self, x, y, z, shape, material, special=None):
        self.lua.eval("function(x, y, z, s, m, sp) return set_tile(x, y, z, s, m, sp) end")(
            x, y, z, shape, material, special
        )

    def set_hidden(self, x, y, z, hidden=True):
        self.lua.eval("function(x, y, z, h) return set_hidden(x, y, z, h) end")(x, y, z, hidden)

    def set_vein_event(self, x, y, z, inorganic_idx, present=True):
        self.lua.eval("function(x, y, z, i, p) return set_vein_event(x, y, z, i, p) end")(
            x, y, z, inorganic_idx, present
        )

    def set_no_vein_event(self, x, y, z):
        self.lua.eval("function(x, y, z) return set_no_vein_event(x, y, z) end")(x, y, z)

    def set_block_read_error(self, x, y, z):
        self.lua.eval("function(x, y, z) return set_block_read_error(x, y, z) end")(x, y, z)

    def set_inorganic(self, idx, id_, is_ore=False, is_gem=False):
        self.lua.eval("function(i, id, o, g) return set_inorganic(i, id, o, g) end")(idx, id_, is_ore, is_gem)

    def vein_material(self, zone_id):
        r = self.g["vein_material"](zone_id)
        return _py(r)

    def decode_vein_tile(self, x, y, z):
        r = self._decode_vein_tile(x, y, z)
        return _py(r)


@pytest.fixture
def w():
    return World()


# ---------------------------------------------------------------------------
# decode_vein_tile: the single-tile classifier
# ---------------------------------------------------------------------------


def test_ordinary_stone_is_not_mineral(w):
    w.set_tile(0, 0, 0, "WALL", "STONE")
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "not_mineral"
    assert rec["material_class"] == "STONE"
    assert rec["economic"] is False
    assert "error" not in rec or rec.get("error") is None


def test_hidden_tile_is_reported_hidden_never_guessed(w):
    w.set_tile(0, 0, 0, "WALL", "MINERAL")
    w.set_hidden(0, 0, 0, True)
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "hidden"
    assert rec.get("hidden") is True


def test_a_real_economic_ore_is_decoded_and_classified(w):
    w.set_tile(0, 0, 0, "WALL", "MINERAL")
    w.set_vein_event(0, 0, 0, 7, present=True)
    w.set_inorganic(7, "HEMATITE", is_ore=True)
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "ore_or_gem"
    assert rec["mineral_name"] == "HEMATITE"
    assert rec["economic"] is True


def test_a_non_economic_mineral_is_named_but_not_ore(w):
    w.set_tile(0, 0, 0, "WALL", "MINERAL")
    w.set_vein_event(0, 0, 0, 3, present=True)
    w.set_inorganic(3, "SOME_MINERAL")
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "not_economic"
    assert rec["mineral_name"] == "SOME_MINERAL"
    assert rec["economic"] is False


def test_mineral_class_tile_with_no_matching_vein_event_is_unknown_not_guessed(w):
    w.set_tile(0, 0, 0, "WALL", "MINERAL")
    w.set_no_vein_event(0, 0, 0)
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "unknown"
    assert "mineral_name" not in rec or rec.get("mineral_name") is None
    assert rec.get("error")


def test_a_vein_event_present_false_does_not_match_this_tile(w):
    # present=False simulates tile_bitmask:get(...) returning false: this
    # tile's block has A vein event, but not covering this specific tile.
    w.set_tile(0, 0, 0, "WALL", "MINERAL")
    w.set_vein_event(0, 0, 0, 7, present=False)
    w.set_inorganic(7, "HEMATITE", is_ore=True)
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "unknown"


def test_getTileBlock_failure_is_unknown_not_a_crash(w):
    w.set_tile(0, 0, 0, "WALL", "MINERAL")
    w.set_block_read_error(0, 0, 0)
    rec = w.decode_vein_tile(0, 0, 0)
    assert rec["vein_status"] == "unknown"
    assert "boom" in rec["error"]


def test_an_unreadable_tile_is_unreadable_not_guessed(w):
    # No set_tile call at all: getTileType errors inside the stub.
    rec = w.decode_vein_tile(5, 5, 5)
    assert rec["ok"] is False
    assert rec["vein_status"] == "unreadable"


# ---------------------------------------------------------------------------
# vein_material: the zone-anchored ring walk
# ---------------------------------------------------------------------------


def test_ring_reports_one_entry_per_boundary_tile_never_a_coordinate(w):
    # A 1x1 zone at (5,5,0): ring is the 8 surrounding tiles.
    w.add_zone(13, 5, 5, 5, 5, 0)
    for x in range(4, 7):
        for y in range(4, 7):
            if (x, y) == (5, 5):
                continue
            w.set_tile(x, y, 0, "WALL", "STONE")
    res = w.vein_material(13)
    assert res["zone_id"] == 13
    assert res["boundary_ring_tiles"] == 8
    assert len(res["tiles"]) == 8
    positions = sorted(t["ring_position"] for t in res["tiles"])
    assert positions == list(range(1, 9))
    for t in res["tiles"]:
        for forbidden in ("x", "y", "z", "pos"):
            assert forbidden not in t
    assert res["counts"]["not_mineral"] == 8


def test_ring_finds_the_ore_tile_among_ordinary_stone(w):
    w.add_zone(13, 5, 5, 5, 5, 0)
    for x in range(4, 7):
        for y in range(4, 7):
            if (x, y) == (5, 5):
                continue
            w.set_tile(x, y, 0, "WALL", "STONE")
    # One ring tile is real hematite ore.
    w.set_tile(4, 4, 0, "WALL", "MINERAL")
    w.set_vein_event(4, 4, 0, 1, present=True)
    w.set_inorganic(1, "HEMATITE", is_ore=True)

    res = w.vein_material(13)
    assert res["counts"]["ore_or_gem"] == 1
    assert res["counts"]["not_mineral"] == 7
    ore_entries = [t for t in res["tiles"] if t["vein_status"] == "ore_or_gem"]
    assert len(ore_entries) == 1
    assert ore_entries[0]["mineral_name"] == "HEMATITE"


def test_unreadable_ring_tile_is_counted_and_logged_not_silently_dropped(w):
    w.add_zone(13, 5, 5, 5, 5, 0)
    # Leave every ring tile unset except one: getTileType errors for the rest.
    w.set_tile(4, 4, 0, "WALL", "STONE")
    res = w.vein_material(13)
    assert res["counts"]["unreadable"] == 7
    assert len(res["read_failures"]) == 7
    assert res["counts"]["not_mineral"] == 1


# ---------------------------------------------------------------------------
# exposed: handoffs/2026-10-05-ore-exposed-signal.md (the site-5/site-6 shape:
# hematite in the corners of a freshly dug bedroom)
# ---------------------------------------------------------------------------


def _ring_of_stone(w, zone=13, at=(5, 5)):
    w.add_zone(zone, at[0], at[1], at[0], at[1], 0)
    for x in range(at[0] - 1, at[0] + 2):
        for y in range(at[1] - 1, at[1] + 2):
            if (x, y) != at:
                w.set_tile(x, y, 0, "WALL", "STONE")


def _ore(w, x, y, idx, name, **kw):
    w.set_tile(x, y, 0, "WALL", "MINERAL")
    w.set_vein_event(x, y, 0, idx, present=True)
    w.set_inorganic(idx, name, **kw)


def test_exposed_reports_corner_ore_by_material_with_counts(w):
    _ring_of_stone(w)
    _ore(w, 4, 4, 1, "HEMATITE", is_ore=True)  # a corner, the case the user saw
    _ore(w, 6, 6, 1, "HEMATITE", is_ore=True)
    exp = w.vein_material(13)["exposed"]
    assert exp["total_tiles"] == 2
    assert exp["materials"] == [{"mineral_name": "HEMATITE", "kind": "ore", "tiles": 2}]
    assert exp["mine_with"] == "construction.mine-vein"
    assert exp["unclassified_tiles"] == 0


def test_exposed_is_empty_when_there_is_no_ore(w):
    _ring_of_stone(w)
    exp = w.vein_material(13)["exposed"]
    assert exp["total_tiles"] == 0
    assert not exp["materials"]  # empty Lua table: {} or [] after json


def test_exposed_separates_materials_and_names_gems(w):
    _ring_of_stone(w)
    _ore(w, 4, 4, 1, "HEMATITE", is_ore=True)
    _ore(w, 6, 4, 2, "NATIVE_GOLD", is_ore=True)
    _ore(w, 4, 6, 3, "CUT_THING", is_gem=True)
    exp = w.vein_material(13)["exposed"]
    assert exp["total_tiles"] == 3
    assert [(m["mineral_name"], m["kind"]) for m in exp["materials"]] == [
        ("CUT_THING", "gem"), ("HEMATITE", "ore"), ("NATIVE_GOLD", "ore"),
    ]


def test_exposed_ignores_non_economic_veins(w):
    _ring_of_stone(w)
    _ore(w, 4, 4, 9, "MICROCLINE")
    assert w.vein_material(13)["exposed"]["total_tiles"] == 0


def test_exposed_ignores_ore_already_mined_open(w):
    _ring_of_stone(w)
    w.set_tile(4, 4, 0, "FLOOR", "MINERAL")
    w.set_vein_event(4, 4, 0, 1, present=True)
    w.set_inorganic(1, "HEMATITE", is_ore=True)
    res = w.vein_material(13)
    assert res["counts"]["ore_or_gem"] == 1  # still ore by material
    assert res["exposed"]["total_tiles"] == 0  # but nothing left to mine


def test_exposed_never_reads_a_hidden_tile(w):
    _ring_of_stone(w)
    _ore(w, 4, 4, 1, "HEMATITE", is_ore=True)
    w.set_hidden(4, 4, 0, True)
    assert w.vein_material(13)["exposed"]["total_tiles"] == 0


def test_exposed_counts_a_smoothed_vein_wall(w):
    _ring_of_stone(w)
    _ore(w, 4, 4, 1, "HEMATITE", is_ore=True)
    w.set_tile(4, 4, 0, "WALL", "MINERAL", "SMOOTH")
    assert w.vein_material(13)["exposed"]["total_tiles"] == 1


def test_exposed_reports_unclassifiable_tiles_apart_never_as_ore(w):
    _ring_of_stone(w)
    w.set_tile(4, 4, 0, "WALL", "MINERAL")
    w.set_no_vein_event(4, 4, 0)
    exp = w.vein_material(13)["exposed"]
    assert exp["total_tiles"] == 0
    assert exp["unclassified_tiles"] == 1
