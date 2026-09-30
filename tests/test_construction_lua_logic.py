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

    def add_item(self, id_, item_type, x=None, y=None, z=None, no_pos=False,
                 trader=False, garbage_collect=False, removed=False):
        opts = self.lua.table_from({
            "no_pos": no_pos, "trader": trader,
            "garbage_collect": garbage_collect, "removed": removed,
        })
        self.lua.eval("function(id, t, x, y, z, o) return add_item(id, t, x, y, z, o) end")(
            id_, item_type, x, y, z, opts
        )

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

    res = w.build(13, "Wall")
    assert res["open_tiles_found"] == 1
    assert len(res["results"]) == 0
    assert len(res["held"]) == 1
    assert "keeps_access" in res["held"][0]
    assert "HEMATITE" in res["held"][0]
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
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert len(res["held"]) == 0
    assert len(res["results"]) == 1
    assert res["results"][0]["ok"] is True


def test_build_holds_on_item_present_and_names_the_item_not_a_coordinate(w):
    w.add_zone(13)
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_ring(13, [(1, 1, 0)])
    w.set_tile(1, 1, 0, "FLOOR")
    w.add_item(1, "BOULDER", 1, 1, 0)

    res = w.build(13, "Wall")
    assert len(res["results"]) == 0
    assert len(res["held"]) == 1
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
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall")
    assert len(res["held"]) == 0
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

    res = w.build(13, "Wall")
    assert len(res["results"]) == 0
    assert len(res["held"]) == 1
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

    res = w.build(13, "Wall")
    assert len(res["results"]) == 0
    assert len(res["held"]) == 1
    assert "reservation" in res["held"][0]
    assert "res-7" in res["held"][0]
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
    w.set_building_filters([{"index": 1}])
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false")
    assert w.applied_filter_calls() == []


def test_build_skips_the_write_when_buildingplan_is_disabled(w):
    w.add_zone(13)
    w.set_ring(13, [(1, 1, 0)])
    w.set_kinds([{"type": "Construction", "subtype": "Wall", "token": "Wall", "key": "Cw"}])
    w.set_tile(1, 1, 0, "FLOOR")
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
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="false", res_id="res-1", override="needed for X")
    assert res != {"error": "OVERRIDE requires RES_ID"}
    # the tile was held-then-let-through by the override, not refused, and
    # actually got designated -- so the override is recorded exactly once.
    assert len(res["held"]) == 0
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
    w.queue_quickfort("  Buildings designated: 1\n", res=0)

    res = w.build(13, "Wall", dry_run="true", res_id="res-1", override="needed for X")
    assert res["dry_run"] is True
    assert w.overrides() == [], "a dry run must never write to persistent reservation state"
