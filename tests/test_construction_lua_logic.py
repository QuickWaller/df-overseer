"""Runs the REAL scripts/dfhack/df-overseer-construction.lua `mine_vein`/
`build_construction` against a small fake DFHack world, using lupa.

handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md: this proves
the NEW tool's own logic (which ring tiles it treats as an ore/gem
candidate, which it refuses and why, that `build` refuses a still-WALL tile
rather than guessing it has been mined, that both verbs apply exactly one
single-cell quickfort blueprint per identified tile) against fake
df-overseer-surface/df-overseer-building modules and a fake quickfort. It
proves NOTHING about the real quickfort CLI or the real vein-decode API --
see df-overseer-surface.lua's own header comment and this stream's Result
section for what remains genuinely unverified.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-construction.lua"
STUB = (REPO_ROOT / "tests" / "lua_stubs" / "dfhack_construction_world.lua").read_text(encoding="utf-8")


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
        load = self.lua.eval("function(src) return load(src, 'construction.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def add_zone(self, id_):
        self.lua.eval("function(id) return add_zone(id) end")(id_)

    def set_ring(self, zone_id, tiles):
        arr = self.lua.table_from([self.lua.table_from(list(t)) for t in tiles])
        self.lua.eval("function(z, t) return set_ring(z, t) end")(zone_id, arr)

    def set_tile(self, x, y, z, shape, ok=True, hidden=False, err=None):
        opts = self.lua.table_from({"ok": ok, "hidden": hidden, "err": err})
        self.lua.eval("function(x, y, z, s, o) return set_tile(x, y, z, s, o) end")(x, y, z, shape, opts)

    def set_vein(self, x, y, z, vein_status, mineral_name=None, error_msg=None):
        self.lua.eval("function(x, y, z, s, m, e) return set_vein(x, y, z, s, m, e) end")(
            x, y, z, vein_status, mineral_name, error_msg
        )

    def set_kinds(self, kinds):
        arr = self.lua.table_from([self.lua.table_from(k) for k in kinds])
        self.lua.eval("function(k) return set_kinds(k) end")(arr)

    def queue_quickfort(self, output, res=0):
        self.lua.eval("function(o, r) return queue_quickfort(o, r) end")(output, res)

    def quickfort_calls(self):
        return _py(self.g["QUICKFORT_CALLS"]) or []

    def mine_vein(self, zone_id, dry_run=None):
        return _py(self.g["mine_vein"](zone_id, dry_run))

    def build(self, zone_id, kind, dry_run=None):
        return _py(self.g["build_construction"](zone_id, kind, dry_run))


@pytest.fixture
def w():
    return World()


# ---------------------------------------------------------------------------
# mine-vein
# ---------------------------------------------------------------------------


def test_mine_vein_finds_ore_skips_open_and_refuses_unknown(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0), (2, 1, 0), (3, 1, 0)])
    # tile 1: real ore, still a wall -> candidate
    w.set_tile(1, 1, 0, "WALL")
    w.set_vein(1, 1, 0, "ore_or_gem", "HEMATITE")
    # tile 2: ore-classified but already dug open -> not a candidate
    w.set_tile(2, 1, 0, "FLOOR")
    w.set_vein(2, 1, 0, "ore_or_gem", "HEMATITE")
    # tile 3: could not classify -> refused, never guessed
    w.set_tile(3, 1, 0, "WALL")
    w.set_vein(3, 1, 0, "unknown", None, "no matching vein event")

    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)
    res = w.mine_vein(13, "true")

    assert res["ore_tiles_found"] == 1
    assert len(res["already_open"]) == 1
    assert "already open" in res["already_open"][0]
    assert len(res["refused"]) == 1
    assert "unknown" in res["refused"][0]
    assert len(res["results"]) == 1
    assert res["results"][0]["ok"] is True
    assert res["results"][0]["mineral_name"] == "HEMATITE"


def test_mine_vein_dry_run_defaults_true_and_passes_d_flag(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "WALL")
    w.set_vein(1, 1, 0, "ore_or_gem", "HEMATITE")
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)

    res = w.mine_vein(13, None)  # DRY_RUN omitted
    assert res["dry_run"] is True
    calls = w.quickfort_calls()
    assert len(calls) == 1
    assert calls[0][-1] == "-d"


def test_mine_vein_real_run_omits_d_flag_only_on_explicit_false(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "WALL")
    w.set_vein(1, 1, 0, "ore_or_gem", "HEMATITE")
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)

    res = w.mine_vein(13, "false")
    assert res["dry_run"] is False
    calls = w.quickfort_calls()
    assert "-d" not in calls[0]


def test_mine_vein_never_designates_ordinary_stone(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "WALL")
    w.set_vein(1, 1, 0, "not_mineral")
    res = w.mine_vein(13, "true")
    assert res["ore_tiles_found"] == 0
    assert not res["already_open"]
    assert not res["refused"]
    assert len(w.quickfort_calls()) == 0


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_build_refuses_unknown_kind_and_lists_known_ones(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"},
                 {"type": "Construction", "subtype": "Floor", "token": "Floor", "key": "Cf"}])
    res = w.build(13, "Nonsense")
    assert "error" in res
    assert "Wall" in res["error"] and "Floor" in res["error"]


def test_build_resolves_kind_case_insensitively_by_token(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    w.queue_quickfort("  Buildings designated: 1\n", res=0)
    res = w.build(13, "wall")  # lower-case
    assert res["kind"]["key"] == "Cw"
    assert res["open_tiles_found"] == 1
    assert res["results"][0]["ok"] is True


def test_build_refuses_a_tile_still_shaped_wall_not_yet_mined(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0), (2, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "WALL")   # not mined yet
    w.set_tile(2, 1, 0, "FLOOR")  # open, mined
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert res["open_tiles_found"] == 1
    assert len(res["refused"]) == 1
    assert "not yet mined" in res["refused"][0]


def test_build_refuses_a_hidden_tile_rather_than_guessing_it_is_open(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR", hidden=True)

    res = w.build(13, "Wall")
    assert res["open_tiles_found"] == 0
    assert len(res["refused"]) == 1
    assert "hidden" in res["refused"][0]
    assert len(w.quickfort_calls()) == 0


def test_build_reports_a_material_report_without_gating_the_real_call(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert "material_report" in res
    assert "note" in res["material_report"]
    # No stock configured in this fake world at all -> reports that, and
    # still designates the building regardless (advisory only, see header).
    assert res["results"][0]["ok"] is True
