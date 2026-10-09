"""research/2026-10-09-auto-mine.md: df-overseer-automine.lua, loaded as the REAL
script against a fake DFHack world (tests/lua_stubs/dfhack_automine_world.lua).

Proves this project's own logic: the auto bit goes only on Default-dig tiles
(never a stair, ramp or channel); the exposed-ore pass designates only revealed
vein tiles of a wanted kind that touch a tile we dug, skips hazard tiles,
reports (does not skip) reserved ones, never decodes a hidden tile, and is
bounded; the cavern reaction clears undug auto tiles near a report (and falls
back to the last digs when the report has no position); and the census helper
tells a followed tile from one of ours.

What this does NOT prove: that the game follows a vein from the bit, at what
priority, or that FEATURE_DISCOVERY carries a position. Those are the live
checks in the research file. Skipped when lupa is not installed.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
STUB = Path(__file__).resolve().parent / "lua_stubs" / "dfhack_automine_world.lua"
AUTOMINE_LUA = SCRIPTS / "df-overseer-automine.lua"

DEFAULT, CHANNEL, DOWNSTAIR, RAMP = 1, 3, 5, 7
FEATURE_DISCOVERY = 2


class World:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        load = self.lua.eval("function(src, name, env) return load(src, name, 't', env) end")
        load(STUB.read_text(encoding="utf-8"), "automine_world", self.lua.globals())()
        env = self.lua.eval("setmetatable({}, {__index = _G})")
        chunk = load(AUTOMINE_LUA.read_text(encoding="utf-8"), "automine.lua", env)
        assert not isinstance(chunk, tuple), chunk
        chunk()
        self.mod = env
        self.g = self.lua.globals()
        self.g["reset_world"]()

    def tile(self, x, y, z, shape, **kw):
        opts = self.lua.table_from(
            {k: (self.lua.table_from(v) if isinstance(v, dict) else v) for k, v in kw.items()}
        )
        self.g["set_tile"](x, y, z, shape, opts)

    def get(self, x, y, z):
        return self.lua.eval(f"TILES['{x},{y},{z}']")

    def report(self, rtype, year, time, pos=None):
        p = self.lua.table_from(pos) if pos else None
        self.g["add_report"](rtype, year, time, p)

    def to_py(self, v):
        if hasattr(v, "items"):
            d = {k: self.to_py(val) for k, val in v.items()}
            if d and all(isinstance(k, int) for k in d):
                return [d[k] for k in sorted(d)]
            return d
        return v

    def mark(self, tiles, opts=None):
        lt = self.lua.table_from([self.lua.table_from(t) for t in tiles])
        return self.to_py(self.mod.mark(lt, self.lua.table_from(opts) if opts else None))

    def scan(self, mx=None):
        return self.to_py(self.mod.scan(mx))


@pytest.fixture
def w():
    return World()


def xyz(x, y, z):
    return {"x": x, "y": y, "z": z}


# --------------------------------------------------------------------- mark


def test_mark_sets_the_bit_only_on_default_dig_tiles(w):
    w.tile(1, 1, 5, "wall", dig=DEFAULT)
    w.tile(2, 1, 5, "wall", dig=CHANNEL)
    w.tile(3, 1, 5, "wall", dig=DOWNSTAIR)
    w.tile(4, 1, 5, "wall", dig=RAMP)
    w.tile(5, 1, 5, "wall")  # no dig at all
    out = w.mark([xyz(i, 1, 5) for i in range(1, 6)])
    assert out["marked"] == 1 and out["skipped_non_default"] == 4
    assert w.get(1, 1, 5)["auto"] is True
    for x in (2, 3, 4, 5):
        assert w.get(x, 1, 5)["auto"] is False, x


def test_mark_sets_the_designated_block_flag_only_when_it_marks(w):
    w.tile(1, 1, 5, "wall", dig=CHANNEL)
    w.mark([xyz(1, 1, 5)])
    assert w.lua.eval("BLOCKS['0,0,5'] and BLOCKS['0,0,5'].flags.designated") in (None, False)
    w.tile(2, 1, 5, "wall", dig=DEFAULT)
    w.mark([xyz(2, 1, 5)])
    assert w.lua.eval("BLOCKS['0,0,5'].flags.designated") is True


def test_mark_is_idempotent_and_counts_already_auto(w):
    w.tile(1, 1, 5, "wall", dig=DEFAULT)
    assert w.mark([xyz(1, 1, 5)])["marked"] == 1
    again = w.mark([xyz(1, 1, 5)])
    assert again["marked"] == 0 and again["already_auto"] == 1


def test_mark_rect_covers_a_rectangle(w):
    for x in range(10, 13):
        for y in range(10, 12):
            w.tile(x, y, 5, "wall", dig=DEFAULT)
    out = w.to_py(w.mod.mark_rect(10, 10, 5, 3, 2))
    assert out["marked"] == 6 and out["requested"] == 6


def test_mark_off_the_map_is_unreadable_not_a_crash(w):
    out = w.mark([xyz(-5, -5, 5)])
    assert out["skipped_unreadable"] == 1 and out["marked"] == 0


# ------------------------------------------------------------------- census


def test_followed_checker_separates_ours_from_followed(w):
    w.tile(1, 1, 5, "wall", dig=DEFAULT)
    w.mark([xyz(1, 1, 5)])                                   # ours
    w.tile(2, 1, 5, "wall", dig=DEFAULT, auto=True)          # the game followed onto it
    w.tile(3, 1, 5, "wall", dig=DEFAULT)                     # plain, not auto
    chk = w.mod.followed_checker()
    assert chk(1, 1, 5) is False
    assert chk(2, 1, 5) is True
    assert chk(3, 1, 5) is False


# --------------------------------------------------------------------- scan


def _room(w, z=5):
    """A 3x3 room at (10..12, 10..12) that we designated (recorded by mark_rect)
    and the dwarves then dug out, ringed by wall."""
    for x in range(9, 14):
        for y in range(9, 14):
            w.tile(x, y, z, "wall")
    for x in range(10, 13):
        for y in range(10, 13):
            w.tile(x, y, z, "wall", dig=DEFAULT)
    assert w.to_py(w.mod.mark_rect(10, 10, z, 3, 3))["marked"] == 9
    for x in range(10, 13):
        for y in range(10, 13):
            w.tile(x, y, z, "floor")   # dug: the game cleared the designation and the bit


def test_scan_designates_revealed_ore_touching_our_dig(w):
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan()
    assert out["designated"] == 1 and out["by_mineral"] == {"HEMATITE": 1}
    t = w.get(13, 11, 5)
    assert t["dig"] == DEFAULT and t["auto"] is True
    assert w.lua.eval("BLOCKS['0,0,5'].flags.designated") is True


def test_scan_leaves_non_economic_veins_and_plain_rock_alone(w):
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "MICROCLINE"})   # not ore or gem
    out = w.scan()
    assert out["designated"] == 0
    assert w.get(13, 11, 5)["dig"] == 0


def test_scan_gems_follow_the_kind_policy_data(w):
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "DIAMOND", "kind": "gem"})
    out = w.scan()
    assert out["designated"] == 1
    w.g["reset_world"]()
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "DIAMOND", "kind": "gem"})
    w.mod.POLICY.kinds["gem"] = False
    assert w.scan()["designated"] == 0
    w.mod.POLICY.kinds["gem"] = True


def test_scan_never_reads_a_hidden_tile(w):
    _room(w)
    w.tile(13, 11, 5, "wall", hidden=True, vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan()          # the stub raises if decode_vein is asked about a hidden tile
    assert out["designated"] == 0
    assert "13,11,5" not in list(w.g["DECODE_CALLS"].values())
    assert w.get(13, 11, 5)["dig"] == 0


def test_scan_ignores_a_vein_beside_a_natural_cave_not_our_dig(w):
    _room(w)
    # a natural open floor 2 tiles outside our rect, with ore beside it only
    w.tile(15, 11, 5, "floor")
    w.tile(14, 11, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan()
    assert out["designated"] == 0


def test_scan_requires_the_vein_to_touch_a_tile_we_dug(w):
    _room(w)
    # far from the dug room, inside the widened rect? No: well outside it
    w.tile(30, 30, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan()
    assert out["designated"] == 0
    assert w.get(30, 30, 5)["dig"] == 0


def test_scan_skips_a_tile_in_a_hazard_band(w):
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    w.lua.execute("HAZARD['13,11,5'] = true")
    out = w.scan()
    assert out["designated"] == 0 and out["skipped_hazard"] == 1
    assert w.get(13, 11, 5)["dig"] == 0


def test_scan_reports_but_does_not_skip_a_reserved_tile(w):
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    w.lua.execute("RESERVED['13,11,5'] = 'res-3'")
    out = w.scan()
    assert out["designated"] == 1 and out["in_reservation"] == 1
    assert out["reserved_handles"][0]["handle"] == "res-3"
    assert w.get(13, 11, 5)["dig"] == DEFAULT


def test_scan_skips_an_already_designated_vein_tile(w):
    _room(w)
    w.tile(13, 11, 5, "wall", dig=DEFAULT, vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan()
    assert out["designated"] == 0 and out["already_designated"] >= 1


def test_scan_is_bounded_per_call(w):
    _room(w)
    for y in (10, 11, 12):
        w.tile(13, y, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan(2)
    assert out["designated"] == 2 and out["capped"] is True
    # the next call finishes the job
    assert w.scan(2)["designated"] == 1


def test_scan_returns_no_coordinates(w):
    _room(w)
    w.tile(13, 11, 5, "wall", vein={"name": "HEMATITE", "kind": "ore"})
    out = w.scan()
    assert all(k not in out for k in ("x", "y", "z", "tiles"))
    assert all(isinstance(v, (int, bool, str, dict, list)) for v in out.values())


def test_scan_with_the_surface_leaf_missing_reports_an_error(w):
    _room(w)
    w.lua.execute("MISSING_SURFACE = true")
    out = w.scan()
    assert out["ok"] is False and "decode_vein" in out["error"]


# ------------------------------------------------------------ cavern reaction


def test_a_cavern_breach_clears_undug_auto_tiles_near_the_report(w):
    _room(w)
    w.tile(14, 11, 5, "wall", dig=DEFAULT, auto=True)       # followed, undug, near
    w.tile(80, 80, 5, "wall", dig=DEFAULT, auto=True)       # followed, far away
    w.tile(13, 12, 5, "wall", dig=CHANNEL)                  # not Default: untouched
    w.report(FEATURE_DISCOVERY, 100, 2000, {"x": 12, "y": 11, "z": 5})
    out = w.scan()
    assert out["cavern"]["breaches"] == 1 and out["cavern"]["cleared_tiles"] == 1
    assert "Cavern breach" in out["cavern"]["note"]
    near = w.get(14, 11, 5)
    assert near["auto"] is False and near["dig"] == 0
    far = w.get(80, 80, 5)
    assert far["auto"] is True and far["dig"] == DEFAULT
    assert w.get(13, 12, 5)["dig"] == CHANNEL


def test_a_breach_report_is_handled_once(w):
    _room(w)
    w.report(FEATURE_DISCOVERY, 100, 2000, {"x": 12, "y": 11, "z": 5})
    assert "cavern" in w.scan()
    assert "cavern" not in w.scan()


def test_a_breach_without_a_position_falls_back_to_the_last_digs(w):
    _room(w)
    w.tile(14, 11, 5, "wall", dig=DEFAULT, auto=True)       # near the recorded dig rect
    w.report(FEATURE_DISCOVERY, 100, 2000, None)
    out = w.scan()
    assert out["cavern"]["breaches"] == 1 and out["cavern"]["located"] == 0
    assert out["cavern"]["cleared_tiles"] == 1
    assert w.get(14, 11, 5)["auto"] is False


def test_other_announcements_do_not_trigger_the_reaction(w):
    _room(w)
    w.tile(14, 11, 5, "wall", dig=DEFAULT, auto=True)
    w.report(4, 100, 2000, {"x": 12, "y": 11, "z": 5})       # STRUCK_MINERAL
    out = w.scan()
    assert "cavern" not in out
    assert w.get(14, 11, 5)["auto"] is True


def test_a_breach_already_in_the_log_before_the_first_scan_is_not_replayed(w):
    # The ledger starts at the current tick: history is not a fresh breach.
    _room(w)
    w.tile(14, 11, 5, "wall", dig=DEFAULT, auto=True)
    w.report(FEATURE_DISCOVERY, 99, 5, {"x": 12, "y": 11, "z": 5})
    assert "cavern" not in w.scan()


# ----------------------------------------------------------- source guards


def test_the_script_is_a_module_and_requires_json_before_it_prints():
    """docs/TRAPS.md "Lua test stubs hide two live-only failures": the stub
    defines json and ignores --@module, so assert both on the source."""
    src = AUTOMINE_LUA.read_text(encoding="utf-8")
    assert src.splitlines()[1].strip() == "--@module = true"
    assert "local json = require('json')" in src
    assert src.index("local json = require('json')") < src.index("json.encode(scan(")
    assert src.index("local json = require('json')") < src.index("json.decode_file")


def test_the_script_never_touches_the_clock():
    src = AUTOMINE_LUA.read_text(encoding="utf-8")
    for forbidden in ("SetPauseState", "clock_pause", "clock_resume", "repeatUtil"):
        assert forbidden not in src


def test_the_dig_tools_call_mark_only_after_quickfort_is_ok():
    bp = (SCRIPTS / "df-overseer-blueprint.lua").read_text(encoding="utf-8")
    dg = (SCRIPTS / "df-overseer-diggable.lua").read_text(encoding="utf-8")
    assert "automine_mod.mark_rect" in bp and "automine_mod.mark_rect" in dg
    assert bp.index("local run = run_quickfort(bp, phase, site, dry)") < bp.index("automine_mod.mark_rect")
    assert dg.index("local quickfort_ok = ok_run and result == CR_OK") < dg.index("automine_mod.mark_rect")
    # the stair path is not auto-marked: stairs are never Default digs
    assert dg.count("automine_mod.mark_rect") == 1


# ------------------------------------------------- blueprint apply integration


def test_a_real_blueprint_dig_apply_marks_its_tiles_after_quickfort_is_ok(tmp_path):
    from tests.test_blueprint_lua_logic import BP, DIG_OK, SHELL, World as BpWorld

    bw = BpWorld(tmp_path)
    try:
        bw.lua.execute("AUTOMINE_FAKE = true")
        bw.stone_block(10, 10)
        bw.qf_output(DIG_OK)
        r, err = bw.call("apply_phase", BP, SHELL, "Well", "false")
        assert err is None and r["ok"] is True
        assert r["auto_mine"]["marked"] == 25
        calls = bw.lua.eval("AUTOMINE_CALLS")
        assert len(calls) == 1 and calls[1]["w"] * calls[1]["h"] == 25
    finally:
        bw.close()


def test_a_dry_run_and_an_opt_out_do_not_mark(tmp_path):
    from tests.test_blueprint_lua_logic import BP, DIG_OK, SHELL, World as BpWorld

    bw = BpWorld(tmp_path)
    try:
        bw.lua.execute("AUTOMINE_FAKE = true")
        bw.stone_block(10, 10)
        bw.qf_output(DIG_OK)
        dry, _ = bw.call("apply_phase", BP, SHELL, "Well")                 # default is a dry run
        assert "auto_mine" not in dry
        out, _ = bw.call("apply_phase", BP, SHELL, "Well", "false", None, None, None, None, "false")
        assert out["auto_mine"]["skipped"].startswith("opted out")
        assert bw.lua.eval("AUTOMINE_CALLS") is None
    finally:
        bw.close()


def test_an_undeployed_automine_leaf_never_fails_the_apply(tmp_path):
    from tests.test_blueprint_lua_logic import BP, DIG_OK, SHELL, World as BpWorld

    bw = BpWorld(tmp_path)
    try:
        bw.stone_block(10, 10)
        bw.qf_output(DIG_OK)
        r, err = bw.call("apply_phase", BP, SHELL, "Well", "false")
        assert err is None and r["ok"] is True
        assert "not deployed" in r["auto_mine"]["skipped"]
    finally:
        bw.close()
