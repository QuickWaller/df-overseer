"""2026-10-08: the aquifer / magma siting policy (scripts/dfhack/df-overseer-
hazard.lua) and the game's own dig cancellations (df-overseer-digcancel.lua).

User decision 2026-10-08: "for now lets only choose spots with no aquifer",
and a dig the game cancels for damp or warm stone must never be misread as a
stuck dig. These tests run the REAL hazard and digcancel leaves, and the REAL
df-overseer-blueprint.lua, against the blueprint fake world (tests/lua_stubs/
dfhack_blueprint_world.lua). The blueprint stub fakes the diggable finder, so
what is proven here for sites is the code-enforced refusal at preview/apply
(the layer a stale or stored site cannot dodge); the finders' and the stair
tool's wiring is asserted at source level below, since diggable.lua has no fake
world.

The no-armok half: a hidden tile's aquifer bit must never be consulted. A test
puts an aquifer flag on a HIDDEN tile and shows the policy does not see it.
Skipped when lupa is not installed.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

from tests.test_blueprint_lua_logic import BP, DIG_OK, SHELL, World  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def _hazard(world):
    return world.lua.eval("function() return reqscript('df-overseer-hazard') end")()


def test_a_revealed_aquifer_tile_beside_the_site_refuses_the_dig(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(9, 12, 5, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")
    world.qf_output(DIG_OK)
    r, err = world.call("preview_phase", BP, SHELL, "Well")
    assert err is None
    assert r["blocked"] is True and r["ok"] is False
    assert "siting policy" in r["blocked_reason"] and "aquifer" in r["blocked_reason"]
    assert r["siting_hazard"]["kind"] == "aquifer"
    assert world.calls() == []          # quickfort was never asked


def test_a_real_apply_is_refused_and_registers_nothing(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(12, 9, 6, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")  # directly above the north ring
    world.lua.execute("set_tile(12, 10, 6, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")  # above a dig tile
    world.qf_output(DIG_OK)
    r, _ = world.call("apply_phase", BP, SHELL, "Well", "false")
    assert r["blocked"] is True and "aquifer" in r["blocked_reason"]
    assert world.calls() == []
    assert world.call("list_sites")[0] == []


def test_a_revealed_magma_tile_beside_the_site_refuses_the_dig(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(15, 12, 5, 'FLOOR', 'STONE', 'NORMAL', {magma = true})")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["blocked"] is True and "magma" in r["blocked_reason"]
    assert r["siting_hazard"]["kind"] == "magma"


def test_a_clear_site_is_not_blocked(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(40, 40, 5, 'FLOOR', 'STONE')")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert not r.get("blocked") and r["ok"] is True


def test_a_hidden_tiles_aquifer_bit_is_never_read(world):
    # Every cell but the north row is hidden, and the hidden ones carry the
    # aquifer flag. A player cannot see that, so the policy must not either.
    world.stone_block(10, 10, hidden_below_north=True)
    world.lua.execute(
        "for x = 10, 14 do for y = 11, 14 do TILES[x .. ',' .. y .. ',5'].aquifer = true end end")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert not r.get("blocked")


def test_hidden_rock_on_a_level_band_with_revealed_aquifer_is_unknown_and_refused(world):
    world.stone_block(10, 10, hidden_below_north=True)
    # revealed aquifer far away on the same level: the band rule
    world.lua.execute("set_tile(90, 90, 5, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["blocked"] is True
    assert r["siting_hazard"]["via"] == "unknown_band"
    assert "unrevealed" in r["blocked_reason"]


def test_the_band_margin_is_policy_data(world):
    world.stone_block(10, 10, hidden_below_north=True)
    world.lua.execute("set_tile(90, 90, 7, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")  # 2 levels up
    world.qf_output(DIG_OK)
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert not r.get("blocked")             # margin is 1, aquifer is 2 away
    hz = _hazard(world)
    hz.POLICY.unknown_band_margin = 2
    world.lua.execute("CLOCK_MS = 10 * 60 * 1000")   # past the band cache
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert r["blocked"] is True


def test_the_policy_can_be_relaxed_in_data_without_code(world):
    world.stone_block(10, 10)
    world.lua.execute("set_tile(9, 12, 5, 'FLOOR', 'STONE', 'NORMAL', {aquifer = true})")
    world.qf_output(DIG_OK)
    hz = _hazard(world)
    hz.POLICY.exclude_aquifer = False
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert not r.get("blocked")
    hz.POLICY.exclude_aquifer = True
    hz.POLICY.adjacency_radius = 0       # tile itself only: a neighbour no longer counts
    r, _ = world.call("preview_phase", BP, SHELL, "Well")
    assert not r.get("blocked")


# ---------------------------------------------------------------- dig cancels


def _applied_site_with_no_pending(world):
    world.stone_block(10, 10, open_sides="s")
    world.qf_output(DIG_OK)
    world.call("apply_phase", BP, SHELL, "Well", "false")


def test_a_damp_cancellation_is_cancelled_by_the_game_not_stalled_or_done(world):
    _applied_site_with_no_pending(world)
    # the game removed the designation (nothing pending, no job) and said why
    world.lua.execute("REPORTS = {{type = 52, x = 12, y = 12, z = 5, year = 0, time = 1300}}")
    st, err = world.call("site_status", "site-1")
    assert err is None
    assert st["dig"]["state"] == "cancelled_by_game"
    assert st["stalled"] is False and st["cancelled_by_game"] is True
    assert st["dig"]["cancelled_by_game"]["damp"] == 1
    assert "cancelled by the game: damp" in st["cancel_note"]
    assert "never retried" in st["cancel_note"]
    tile = st["dig"]["cancelled_by_game"]["tiles"][0]
    assert tile["near_landmark"] == "Well" and tile["status"] == "cancelled by the game: damp"
    assert not any(k in tile for k in ("x", "y", "z"))   # landmark-relative, no coordinates


def test_a_warm_cancellation_is_named_warm(world):
    _applied_site_with_no_pending(world)
    world.lua.execute("REPORTS = {{type = 51, x = 11, y = 11, z = 5, year = 0, time = 1300}}")
    st, _ = world.call("site_status", "site-1")
    assert st["dig"]["state"] == "cancelled_by_game"
    assert "cancelled by the game: warm" in st["cancel_note"]


def test_a_cancellation_from_before_the_apply_or_elsewhere_is_ignored(world):
    _applied_site_with_no_pending(world)
    world.lua.execute("REPORTS = {{type = 52, x = 12, y = 12, z = 5, year = 0, time = 100},"
                      "{type = 52, x = 99, y = 99, z = 5, year = 0, time = 1300},"
                      "{type = 52, x = 12, y = 12, z = 9, year = 0, time = 1300}}")
    st, _ = world.call("site_status", "site-1")
    assert st["dig"]["state"] == "none_pending" and st["cancelled_by_game"] is False


def test_a_cancel_never_masks_live_work(world):
    _applied_site_with_no_pending(world)
    world.lua.execute("REPORTS = {{type = 52, x = 12, y = 12, z = 5, year = 0, time = 1300}}")
    world.lua.execute('set_jobs({{job_type = "Dig", x = 12, y = 14, z = 5}})')
    st, _ = world.call("site_status", "site-1")
    assert st["dig"]["state"] == "in_progress"
    assert st["dig"]["cancelled_by_game"]["total"] == 1     # still reported


def test_release_accepts_a_game_cancelled_site(world):
    _applied_site_with_no_pending(world)
    world.lua.execute("REPORTS = {{type = 52, x = 12, y = 12, z = 5, year = 0, time = 1300}}")
    r, _ = world.call("release_site", "site-1", "true")
    assert "not stalled or cancelled" not in str(r.get("refused", ""))


def test_kind_at_reads_one_tile(world):
    world.lua.execute("REPORTS = {{type = 52, x = 1, y = 2, z = 3, year = 0, time = 5}}")
    dc = world.lua.eval("function() return reqscript('df-overseer-digcancel') end")()
    assert dc.kind_at(1, 2, 3, None) == "damp"
    assert dc.kind_at(1, 2, 4, None) is None
    assert dc.label("warm") == "cancelled by the game: warm"


# ----------------------------------------------------- source-level wiring


def _src(name):
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_every_dig_path_consults_the_hazard_policy():
    dig = _src("df-overseer-diggable.lua")
    assert "reqscript('df-overseer-hazard')" in dig
    # the per-tile test every finder shares
    body = dig[dig.index("local function is_diggable"):dig.index("local function find_candidates")]
    assert body.count("hazard_mod.check_tile") == 2          # the hidden branch and the revealed branch
    # stair upper tile, and designation-time refusal for both dig and dig-stair
    assert "hazard_mod.check_tile(x, y, upper_z)" in dig
    assert dig.count("hazard_mod.message(hz") == 2
    assert dig.count("hazard_mod.begin_scan()") == 2
    construction = _src("df-overseer-construction.lua")
    assert "hazard_mod.check_tile(x, y, z)" in construction and "hazard_mod.begin_scan()" in construction
    bp = _src("df-overseer-blueprint.lua")
    assert bp.count("site_hazard_refusal(site)") == 3        # definition use in run_phase and reserve_site


def test_stuck_dig_reads_know_the_games_cancellations():
    stuck = _src("df-overseer-stuckjobs.lua")
    assert "reqscript('df-overseer-digcancel')" in stuck
    assert "digcancel_mod.label(cancel_kind)" in stuck
    assert "cancelled_by_game = cancel_kind" in stuck
    dc = _src("df-overseer-digcancel.lua")
    assert "DIG_CANCEL_DAMP" in dc and "DIG_CANCEL_WARM" in dc
