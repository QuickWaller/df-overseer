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
    if not keys:
        return []  # an empty Lua table is this codebase's empty list, never an object
    if all(isinstance(k, int) for k in keys) and keys == list(range(1, len(keys) + 1)):
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

    def add_zone(self, id_, x1=None, y1=None, x2=None, y2=None):
        self.lua.eval("function(id, x1, y1, x2, y2) return add_zone(id, x1, y1, x2, y2) end")(
            id_, x1, y1, x2, y2
        )

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

    def add_item(self, id_, item_type, x=None, y=None, z=None, no_pos=False,
                 trader=False, garbage_collect=False, removed=False):
        opts = self.lua.table_from({
            "no_pos": no_pos, "trader": trader,
            "garbage_collect": garbage_collect, "removed": removed,
        })
        self.lua.eval("function(id, t, x, y, z, o) return add_item(id, t, x, y, z, o) end")(
            id_, item_type, x, y, z, opts
        )

    def set_group(self, x, y, z, group):
        self.lua.eval("function(x, y, z, g) return set_group(x, y, z, g) end")(x, y, z, group)

    def set_main_group(self, group):
        self.lua.eval("function(g) return set_main_group(g) end")(group)

    def add_entrance_fixture(self, zone_id, ex=None, ey=None, ez=None):
        self.lua.eval("function(z, x, y, zz) return add_entrance_fixture(z, x, y, zz) end")(
            zone_id, ex, ey, ez
        )

    def set_planned_building(self, x, y, z, building_id, build_stage, max_build_stage, building_type=None):
        self.lua.eval(
            "function(x, y, z, id, s, m, t) return set_planned_building(x, y, z, id, s, m, t) end"
        )(x, y, z, building_id, build_stage, max_build_stage, building_type)

    def add_job_for_tile(self, x, y, z):
        """Attaches a fresh job to whatever building set_planned_building registered at (x, y, z)."""
        self.lua.eval("function(x, y, z) return add_job(BUILDINGS_AT_TILE[x..','..y..','..z]) end")(
            x, y, z
        )

    def job_suspended_for_tile(self, x, y, z):
        return self.lua.eval(
            "function(x, y, z) return job_suspended(BUILDINGS_AT_TILE[x..','..y..','..z]) end"
        )(x, y, z)

    def door(self, zone_id, dry_run=None, res_id=None, override=None):
        return _py(self.g["build_door"](zone_id, dry_run, res_id, override))

    def audit(self, zone_id=None, dry_run=None):
        return _py(self.g["audit_constructions"](zone_id, dry_run))

    def set_reserved(self, reservations):
        arr = self.lua.table_from([self.lua.table_from(r) for r in reservations])
        self.lua.eval("function(r) return set_reserved(r) end")(arr)

    def queue_quickfort(self, output, res=0):
        self.lua.eval("function(o, r) return queue_quickfort(o, r) end")(output, res)

    def quickfort_calls(self):
        return _py(self.g["QUICKFORT_CALLS"]) or []

    def mine_vein(self, zone_id, dry_run=None, res_id=None, override=None):
        return _py(self.g["mine_vein"](zone_id, dry_run, res_id, override))

    def build(self, zone_id, kind, dry_run=None, material_choice=None, res_id=None, override=None):
        return _py(self.g["build_construction"](zone_id, kind, dry_run, material_choice, res_id, override))

    def overrides(self):
        return _py(self.g["OVERRIDES"]) or []

    def set_building_filters(self, filters, enabled=True):
        arr = self.lua.table_from([self.lua.table_from(f, recursive=True) for f in filters])
        self.lua.eval("function(f, e) return set_building_filters(f, e) end")(arr, enabled)

    def applied_filter_calls(self):
        return _py(self.g["APPLIED_FILTER_CALLS"]) or []

    def restore_calls(self):
        return self.g["RESTORE_CALLS"]


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
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)
    res = w.build(13, "wall")  # lower-case
    assert res["kind"]["key"] == "Cw"
    assert res["open_tiles_found"] == 2  # the real tile plus the fixture's own entrance tile
    assert res["results"][0]["ok"] is True


def test_build_refuses_a_tile_still_shaped_wall_not_yet_mined(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0), (2, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "WALL")   # not mined yet
    w.set_tile(2, 1, 0, "FLOOR")  # open, mined
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert res["open_tiles_found"] == 2  # tile 2 plus the fixture's own entrance tile
    assert len(res["refused"]) == 1
    assert "not yet mined" in res["refused"][0]


def test_build_refuses_a_hidden_tile_rather_than_guessing_it_is_open(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR", hidden=True)
    w.add_entrance_fixture(13)

    res = w.build(13, "Wall")
    assert res["open_tiles_found"] == 1  # only the fixture's own entrance tile
    assert len(res["refused"]) == 1
    assert "hidden" in res["refused"][0]
    assert len(w.quickfort_calls()) == 0


# ---------------------------------------------------------------------------
# build guards: keeps_access, item_present
# (handoffs/2026-09-28-keeps-access-guard.md)
# ---------------------------------------------------------------------------


def test_build_holds_a_target_that_would_seal_off_reachable_ore(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    # Ring has one build target, (5,4,0), the ore tile's only currently-open
    # orthogonal neighbour -- its other three neighbours are ordinary,
    # already-known walls (not ore, not open), so building the ring target
    # would cut off the only approach.
    w.set_ring(13, [(5, 4, 0)])
    w.set_tile(5, 4, 0, "FLOOR")           # the ring/build target
    w.set_tile(5, 5, 0, "WALL")            # the ore tile itself
    w.set_vein(5, 5, 0, "ore_or_gem", "HEMATITE")
    w.set_tile(6, 5, 0, "WALL")            # ore's other 3 neighbours: plain
    w.set_tile(5, 6, 0, "WALL")            # rock, already known, not open
    w.set_tile(4, 5, 0, "WALL")
    w.add_entrance_fixture(13)

    res = w.build(13, "Wall")
    assert res["open_tiles_found"] == 2  # (5,4,0) plus the fixture's own entrance tile
    assert len(res["results"]) == 0
    assert len(res["held"]) == 2  # keeps_access (ring_position 1) + entrance (ring_position 2)
    assert "keeps_access" in res["held"][0]
    assert "HEMATITE" in res["held"][0]
    assert "entrance" in res["held"][1]
    assert len(w.quickfort_calls()) == 0


def test_build_does_not_hold_when_ore_keeps_another_open_approach(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(5, 4, 0)])
    w.set_tile(5, 4, 0, "FLOOR")            # the ring/build target
    w.set_tile(5, 5, 0, "WALL")             # the ore tile
    w.set_vein(5, 5, 0, "ore_or_gem", "HEMATITE")
    w.set_tile(6, 5, 0, "FLOOR")            # a SECOND open approach, not in
    w.set_tile(5, 6, 0, "WALL")             # this step's targets -- ore
    w.set_tile(4, 5, 0, "WALL")             # stays reachable regardless
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert len(res["held"]) == 1  # just the fixture's own entrance tile
    assert "entrance" in res["held"][0]
    assert len(res["results"]) == 1
    assert res["results"][0]["ok"] is True


def test_build_holds_on_item_present_and_names_the_item_not_a_coordinate(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_item(1, "BOULDER", 1, 1, 0)
    w.add_entrance_fixture(13)

    res = w.build(13, "Wall")
    assert len(res["results"]) == 0
    assert len(res["held"]) == 2  # item_present (ring_position 1) + entrance (ring_position 2)
    assert "item_present" in res["held"][0]
    assert "BOULDER" in res["held"][0]
    assert "1,1,0" not in res["held"][0]
    assert len(w.quickfort_calls()) == 0


def test_build_ignores_a_trader_or_garbage_item_and_still_proceeds(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_item(1, "BOULDER", 1, 1, 0, trader=True)
    w.add_item(2, "BOULDER", 1, 1, 0, garbage_collect=True)
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert len(res["held"]) == 1  # just the fixture's own entrance tile
    assert res["results"][0]["ok"] is True


def test_build_holds_rather_than_guess_when_an_ore_neighbour_is_unreadable(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(5, 4, 0)])
    w.set_tile(5, 4, 0, "FLOOR")            # the ring/build target
    w.set_tile(5, 5, 0, "WALL")             # the ore tile
    w.set_vein(5, 5, 0, "ore_or_gem", "HEMATITE")
    # (6, 5, 0) deliberately left unset: tile_read fails "no test tile set"
    w.set_tile(5, 6, 0, "WALL")
    w.set_tile(4, 5, 0, "WALL")
    w.add_entrance_fixture(13)

    res = w.build(13, "Wall")
    assert len(res["results"]) == 0
    assert len(res["held"]) == 2  # keeps_access (ring_position 1) + entrance (ring_position 2)
    assert "keeps_access" in res["held"][0]
    assert "could not confirm" in res["held"][0]
    assert len(w.quickfort_calls()) == 0


# ---------------------------------------------------------------------------
# reservation guard (handoffs/2026-09-30-room-reservations.md decision 3)
# ---------------------------------------------------------------------------


def test_mine_vein_holds_a_reserved_ring_tile_rather_than_refusing_the_call(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0), (2, 1, 0)])
    w.set_tile(1, 1, 0, "WALL")
    w.set_vein(1, 1, 0, "ore_or_gem", "HEMATITE")
    w.set_tile(2, 1, 0, "WALL")
    w.set_vein(2, 1, 0, "ore_or_gem", "HEMATITE")
    w.set_reserved([{"x": 1, "y": 1, "z": 0, "handle": "res-1", "purpose": "planned bedroom"}])
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)

    res = w.mine_vein(13, "true")
    assert res["ore_tiles_found"] == 2
    assert len(res["held"]) == 1
    assert "res-1" in res["held"][0]
    assert "reservation" in res["held"][0]
    assert len(res["results"]) == 1  # only the unreserved tile designated
    calls = w.quickfort_calls()
    assert len(calls) == 1


def test_build_holds_a_reserved_target_before_the_other_guards_run(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.set_reserved([{"x": 1, "y": 1, "z": 0, "handle": "res-7", "purpose": "planned corridor"}])
    w.add_entrance_fixture(13)

    res = w.build(13, "Wall")
    assert len(res["results"]) == 0
    assert len(res["held"]) == 2  # reservation (ring_position 1) + entrance (ring_position 2)
    assert "reservation" in res["held"][0]
    assert "res-7" in res["held"][0]
    assert len(w.quickfort_calls()) == 0


def test_build_reports_a_material_report_without_gating_the_real_call(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert "material_report" in res
    assert "note" in res["material_report"]
    # No stock configured in this fake world at all -> reports that, and
    # still designates the building regardless (no filter to write).
    assert res["results"][0]["ok"] is True


# ---------------------------------------------------------------------------
# 2026-10-01 (handoffs/2026-10-01-buildingplan-material-filter.md): the
# resolved CLASS is now WRITTEN into buildingplan's own filter for a real
# build, via building.lua's exported building_filters_and_gaps/
# apply_material_filters (faked here -- see the stub's own header comment;
# the real write/restore mechanism is proven against the REAL building.lua by
# tests/test_buildingplan_material_filter_lua_logic.py). A test here asserts
# on APPLIED_FILTER_CALLS/RESTORE_CALLS directly: if construction.lua stops
# calling through, these assertions fail outright -- the "stub that fails if
# the filter call is missing" the handoff asked for.
# ---------------------------------------------------------------------------


def test_build_writes_the_resolved_class_into_buildingplans_filter(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_entrance_fixture(13)
    w.set_building_filters([{"index": 1, "filter_material_names": ["SHALE", "MARBLE"]}])
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false")

    assert res["results"][0]["ok"] is True
    calls = w.applied_filter_calls()
    assert len(calls) == 1, "apply_material_filters was never called: the class was not written"
    assert set(calls[0]["names"]) == {"SHALE", "MARBLE"}
    assert w.restore_calls() == 1, "the filter must be restored once the real build finishes"
    assert res["material_filter"]["restored"] == []


def test_build_never_writes_the_filter_on_a_dry_run(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_entrance_fixture(13)
    w.set_building_filters([{"index": 1, "filter_material_names": ["SHALE"]}])
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="true")

    assert res["dry_run"] is True
    assert w.applied_filter_calls() == []
    assert w.restore_calls() == 0


def test_build_never_writes_an_empty_class(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    # A filter rec with no eligible material at all (e.g. only economic stock
    # and no override) carries no filter_material_names key at all -- see
    # building.lua's resolve_material_choice, which returns early on that gap
    # without ever setting it.
    w.add_entrance_fixture(13)
    w.set_building_filters([{"index": 1}])
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false")
    assert w.applied_filter_calls() == []


def test_build_skips_the_write_when_buildingplan_is_disabled(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_entrance_fixture(13)
    w.set_building_filters([{"index": 1, "filter_material_names": ["SHALE"]}], enabled=False)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false")
    assert w.applied_filter_calls() == []


# ---------------------------------------------------------------------------
# handoffs/2026-09-30-reservation-holding.md item 2/review: OVERRIDE is only
# ever valid together with RES_ID -- both verbs refuse it up front, before
# any zone/ring resolution runs, if OVERRIDE is given without RES_ID.
# ---------------------------------------------------------------------------


def test_mine_vein_rejects_override_without_res_id(w):
    # No zone registered at all: if this reached zone resolution it would
    # fail with a different error ("no zone"), so getting exactly the
    # OVERRIDE/RES_ID message proves the guard runs first.
    res = w.mine_vein(13, override="needed for X")
    assert res == {"error": "OVERRIDE requires RES_ID"}


def test_build_rejects_override_without_res_id(w):
    res = w.build(13, "Wall", override="needed for X")
    assert res == {"error": "OVERRIDE requires RES_ID"}


def test_build_accepts_override_together_with_res_id_and_records_it_once_on_success(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.set_reserved([{"x": 1, "y": 1, "z": 0, "handle": "res-1", "purpose": "planned corridor"}])
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false", res_id="res-1", override="needed for X")
    assert res != {"error": "OVERRIDE requires RES_ID"}
    # the tile was held-then-let-through by the override, not refused, and
    # actually got designated -- so the override is recorded exactly once.
    # (the only remaining hold is the fixture's own entrance tile)
    assert len(res["held"]) == 1
    assert "entrance" in res["held"][0]
    assert res["results"][0]["ok"] is True
    assert w.overrides() == [
        {"handle": "res-1", "tool": "construction.build", "kind": "Wall", "reason": "needed for X"}
    ]


def test_build_does_not_record_an_override_never_actually_needed(w):
    # RES_ID given, but nothing in this call is actually reserved at all --
    # the override is never consumed, so it must never be recorded (handoff
    # review, 2026-09-30: recording only when it was actually needed).
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false", res_id="res-1", override="needed for X")
    assert res["results"][0]["ok"] is True
    assert w.overrides() == []


def test_build_does_not_record_an_override_on_a_dry_run(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.set_reserved([{"x": 1, "y": 1, "z": 0, "handle": "res-1", "purpose": "planned corridor"}])
    w.add_entrance_fixture(13)
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="true", res_id="res-1", override="needed for X")
    assert res["dry_run"] is True
    assert w.overrides() == [], "a dry run must never write to persistent reservation state"


# ---------------------------------------------------------------------------
# entrance guard / door / audit (handoffs/2026-10-01-entrances-get-doors.md)
#
# Fixture below is the real office's own geometry from
# evals/live/2026-10-01-queue-and-material-deploy/README.md ("Month window,
# a sealed office"): a 3x3 interior (the eval's 103,102 to 105,104), z
# dropped to 0 (irrelevant to this guard's own logic). The ring is the
# office's real 16-tile boundary; (104, 101, 0) stands in for the eval's
# 103,101 -- the actual north-side wall the live rescue had to remove --
# kept at the north edge's MIDDLE tile here only so it is unambiguously a
# straight edge, never a corner, in a geometry-agnostic test. ring_position
# 3 in the fixed order below.
# ---------------------------------------------------------------------------

OFFICE_X1, OFFICE_Y1, OFFICE_X2, OFFICE_Y2 = 103, 102, 105, 104
OFFICE_ENTRANCE = (104, 101, 0)  # ring_position 3 in OFFICE_RING below
OFFICE_RING = [
    (102, 101, 0), (103, 101, 0), (104, 101, 0), (105, 101, 0), (106, 101, 0),  # north (incl. 2 corners)
    (102, 105, 0), (103, 105, 0), (104, 105, 0), (105, 105, 0), (106, 105, 0),  # south (incl. 2 corners)
    (102, 102, 0), (102, 103, 0), (102, 104, 0),                               # west
    (106, 102, 0), (106, 103, 0), (106, 104, 0),                               # east
]


def _setup_office(w, zone_id=99, entrance_shape="FLOOR", other_shape="FLOOR"):
    w.add_zone(zone_id, OFFICE_X1, OFFICE_Y1, OFFICE_X2, OFFICE_Y2)
    w.set_ring(zone_id, OFFICE_RING)
    for xyz in OFFICE_RING:
        w.set_tile(*xyz, entrance_shape if xyz == OFFICE_ENTRANCE else other_shape)
    # The entrance's own outside neighbour (one step further north) belongs
    # to the fort's main walkable group -- "the group most citizens are in",
    # read live in production via connectivity.report's main_group_id.
    ex, ey, ez = OFFICE_ENTRANCE
    w.set_group(ex, ey - 1, ez, 1)
    w.set_main_group(1)


def test_find_entrances_identifies_the_offices_real_north_exit_and_builds_the_rest(w):
    _setup_office(w)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    for _ in range(len(OFFICE_RING) - 1):  # every tile except the entrance gets built
        w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(99, "Wall")

    assert res["open_tiles_found"] == len(OFFICE_RING)
    assert res["entrances_found"] == 1
    assert len(res["held"]) == 1
    assert "ring tile 3" in res["held"][0]
    assert "entrance" in res["held"][0]
    assert "this zone's own entrance" in res["held"][0]
    assert len(res["results"]) == len(OFFICE_RING) - 1
    assert all(r["ok"] for r in res["results"])
    # the entrance's own ring_position (3) never appears among built results
    assert all(r["ring_position"] != 3 for r in res["results"])


def test_build_refuses_the_whole_call_when_the_entrance_is_already_sealed(w):
    # Exactly the 2026-09-28 incident: every ring tile, including the
    # entrance, already built as a wall (shape WALL) -- no open tile is left
    # that could still serve as the way out, so the WHOLE call is refused,
    # never silently proceeding to wall the (already walled) rest.
    _setup_office(w, entrance_shape="WALL", other_shape="WALL")
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])

    res = w.build(99, "Wall")

    assert "error" in res
    assert "no detectable entrance" in res["error"]
    assert len(w.quickfort_calls()) == 0


def test_build_refuses_when_main_group_cannot_be_read(w):
    # connectivity.report itself unavailable (no citizens, or a read
    # failure) -- refuse rather than guess which tile is safe to leave open.
    w.add_zone(99, OFFICE_X1, OFFICE_Y1, OFFICE_X2, OFFICE_Y2)
    w.set_ring(99, OFFICE_RING)
    for xyz in OFFICE_RING:
        w.set_tile(*xyz, "FLOOR")
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    # set_main_group deliberately never called: MAIN_GROUP stays nil.

    res = w.build(99, "Wall")

    assert "error" in res
    assert "main walkable group" in res["error"]
    assert len(w.quickfort_calls()) == 0


def test_door_places_a_door_at_the_entrance_only(w):
    _setup_office(w)
    w.set_kinds([{"type": "Door", "subtype": None, "token": "Door", "key": "d"}])
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.door(99)

    assert res["kind"]["token"] == "Door"
    assert res["entrances_found"] == 1
    assert len(res["results"]) == 1
    assert res["results"][0]["ring_position"] == 3  # OFFICE_ENTRANCE's own ring_position
    assert res["results"][0]["ok"] is True


def test_door_refuses_when_the_zone_has_no_entrance(w):
    _setup_office(w, entrance_shape="WALL", other_shape="WALL")
    w.set_kinds([{"type": "Door", "subtype": None, "token": "Door", "key": "d"}])

    res = w.door(99)

    assert "error" in res
    assert "no detectable entrance" in res["error"]
    assert len(w.quickfort_calls()) == 0


def test_audit_reports_no_risk_when_the_entrance_is_untouched(w):
    _setup_office(w)
    # Build 4 of the office's ring tiles for real (buildings 18-21 in the
    # eval's own numbering) -- shape now WALL, fully built (no job pending).
    for xyz in OFFICE_RING:
        if xyz != OFFICE_ENTRANCE:
            w.set_tile(*xyz, "WALL")

    res = w.audit(99)

    assert res["zones_checked"] == 1
    zone = res["zones"][0]
    assert zone["zone_id"] == 99
    assert zone["open"] == 1       # just the untouched entrance
    assert zone["built"] == len(OFFICE_RING) - 1
    assert zone["planned"] == 0
    assert zone["would_strand"] is False
    assert zone["at_risk"] == []
    assert zone["suspended"] == []


def test_audit_finds_and_suspends_the_building_that_would_seal_the_last_exit(w):
    # Exactly building 22's own situation on 2026-09-28: every OTHER ring
    # tile already a finished wall, and the entrance tile itself has a
    # Construction building sitting on it that has NOT finished yet (build
    # stage below max) -- the tile's own shape has therefore not become WALL
    # yet, so it still reads as "open" to tile_read, but it is NOT a safe
    # open tile: finishing this one job would seal the room.
    _setup_office(w)
    for xyz in OFFICE_RING:
        if xyz != OFFICE_ENTRANCE:
            w.set_tile(*xyz, "WALL")
    ex, ey, ez = OFFICE_ENTRANCE
    w.set_planned_building(ex, ey, ez, 22, 1, 3)  # build_stage 1 of 3: not finished
    w.add_job_for_tile(ex, ey, ez)

    dry_res = w.audit(99)  # DRY_RUN defaults to true: never suspends anything
    zone = dry_res["zones"][0]
    assert zone["open"] == 0
    assert zone["planned"] == 1
    assert zone["would_strand"] is True
    assert zone["at_risk"] == [{"ring_position": 3, "building_id": 22}]
    assert zone["suspended"] == []
    assert w.job_suspended_for_tile(ex, ey, ez) is False

    real_res = w.audit(99, "false")
    zone = real_res["zones"][0]
    assert zone["suspended"] == [{"building_id": 22, "ok": True}]
    assert w.job_suspended_for_tile(ex, ey, ez) is True


# --- handoffs/2026-10-05-ore-exposed-signal.md: mine-vein for a site handle ---


def _site_blueprint_module(w, handle="site-1", err=None):
    w.lua.execute(
        "package.loaded['df-overseer-blueprint'] = {site_room_rect = function(h) "
        "if h ~= %r then return nil, 'no site ' .. h end "
        "return {id = h, x1 = 1, y1 = 1, x2 = 1, y2 = 1, z = 0} end}" % handle
    )


def test_mine_vein_takes_a_site_handle_and_mines_its_corner_ore(w):
    _site_blueprint_module(w)
    w.set_ring("site-1", [(0, 0, 0), (2, 2, 0)])
    w.set_tile(0, 0, 0, "WALL")
    w.set_vein(0, 0, 0, "ore_or_gem", "HEMATITE")
    w.set_tile(2, 2, 0, "WALL")
    w.set_vein(2, 2, 0, "ore_or_gem", "HEMATITE")
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)
    res = w.mine_vein("site-1", "true")
    assert res["zone_id"] == "site-1"
    assert res["ore_tiles_found"] == 2
    assert [r["mineral_name"] for r in res["results"]] == ["HEMATITE", "HEMATITE"]


def test_mine_vein_site_handle_unknown_is_a_named_error(w):
    _site_blueprint_module(w)
    res = w.mine_vein("site-7", "true")
    assert "no site" in res["error"]


def test_mine_vein_site_handle_without_the_blueprint_module_says_so(w):
    w.lua.execute("package.loaded['df-overseer-blueprint'] = nil")
    res = w.mine_vein("site-1", "true")
    assert "not available" in res["error"]


# --- handoffs/2026-10-07-route-ore-mining.md: the conductor's verdict on the REAL Lua output ---


def _mine_specs():
    from dfmcp import action_data as ad
    from dfmcp.registry import load_registry

    specs = ad.load_all(load_registry())
    return ad, specs["construction.mine-vein-site"], specs["construction.mine-vein"]


def test_the_conductors_verdict_reads_the_real_mine_vein_output(w):
    ad, site_spec, zone_spec = _mine_specs()
    _site_blueprint_module(w)
    w.set_ring("site-1", [(0, 0, 0), (2, 2, 0)])
    for xy in ((0, 0), (2, 2)):
        w.set_tile(xy[0], xy[1], 0, "WALL")
        w.set_vein(xy[0], xy[1], 0, "ore_or_gem", "HEMATITE")
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)
    dry = w.mine_vein("site-1", "true")
    assert ad.judge(site_spec, dry, dry=True).ok
    # the same output is not a real run: the echo must match the call
    assert ad.judge(site_spec, dry, dry=False).kind == "invalid"
    for path in site_spec.preview_fields:
        assert ad.get_path(dry, path)[0], path
    # the zone form shares the function and the declaration
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "WALL")
    w.set_vein(1, 1, 0, "ore_or_gem", "HEMATITE")
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)
    assert ad.judge(zone_spec, w.mine_vein(13, "true"), dry=True).ok


def test_the_conductors_verdict_refuses_an_unclassifiable_or_held_ring_tile(w):
    ad, site_spec, _ = _mine_specs()
    _site_blueprint_module(w)
    w.set_ring("site-1", [(0, 0, 0), (2, 2, 0)])
    w.set_tile(0, 0, 0, "WALL")
    w.set_vein(0, 0, 0, "unknown", None, "no matching vein event")
    w.set_tile(2, 2, 0, "WALL")
    w.set_vein(2, 2, 0, "ore_or_gem", "HEMATITE")
    w.queue_quickfort("  Tiles designated for digging: 1\n", res=0)
    refused = w.mine_vein("site-1", "true")
    assert ad.judge(site_spec, refused, dry=True).kind == "refused"

    w2 = World()
    _site_blueprint_module(w2)
    w2.set_ring("site-1", [(2, 2, 0)])
    w2.set_tile(2, 2, 0, "WALL")
    w2.set_vein(2, 2, 0, "ore_or_gem", "HEMATITE")
    w2.set_reserved([{"x": 2, "y": 2, "z": 0, "handle": "res-1", "purpose": "planned bedroom"}])
    held = w2.mine_vein("site-1", "true")
    assert held["held"] and ad.judge(site_spec, held, dry=True).kind == "refused"
    # a script error object is a refusal with its message
    assert ad.judge(site_spec, w2.mine_vein("site-9", "true"), dry=True).kind == "refused"
