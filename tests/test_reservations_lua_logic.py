"""Runs the REAL scripts/dfhack/df-overseer-reservations.lua against a small
fake DFHack world, using lupa.

handoffs/2026-09-30-room-reservations.md: proves this file's own ledger and
overlap logic -- create/get_raw/list_raw/remove/mark_in_use/find_conflicts/
check_tiles/rect_tiles -- against a fake persistent store and a fake
landmarks module. It proves nothing about real DFHack persistent state or
real quickfort; that is df-overseer-blueprint.lua's own live check (this
file is a dependency-free leaf reqscript'd from there, see its header).

Covers, per the handoff and the user's 2026-09-30 correction revising
decision 5 ("no overlaps" -> "a shared wall is fine"):
  - reserve then a conflicting tile refused, naming the handle, no coordinate
    leaked (check_tiles's message/fields);
  - the holder's own tiles are NOT refused (holding_handle);
  - two footprints overlapping only on tiles BOTH mark wall: accepted;
  - an overlap that touches even one interior/carve/unclassified tile:
    refused;
  - unreserve frees the tiles, but a shared wall tile stays held by any
    OTHER reservation still covering it.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-reservations.lua"
STUB = (REPO_ROOT / "tests" / "lua_stubs" / "dfhack_reservations_world.lua").read_text(encoding="utf-8")


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if not keys:
        return []  # an empty Lua table is always treated as an empty list here
    if all(isinstance(k, int) for k in keys) and keys == list(range(1, len(keys) + 1)):
        return [_py(v[k]) for k in keys]
    return {str(k): _py(v[k]) for k in keys}


class World:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB)
        load = self.lua.eval("function(src) return load(src, 'reservations.lua') end")
        chunk = load(LUA.read_text(encoding="utf-8"))
        assert not isinstance(chunk, tuple), chunk
        self.lua.eval("function(f) f() end")(chunk)
        self.g = self.lua.globals()

    def _cells(self, cells):
        t = self.lua.table()
        for k in cells:
            t[k] = True
        return t

    def create(self, x, y, z, w, h, wall_cells=(), blueprint="bp", purpose="test", orient="none",
               allowed_kinds=()):
        rec = self.lua.table_from({
            "x": x, "y": y, "z": z, "w": w, "h": h, "orient": orient,
            "bw": w, "bh": h, "blueprint": blueprint, "purpose": purpose,
            "wall_cells": self._cells(wall_cells),
            "allowed_kinds": self.lua.table_from(list(allowed_kinds)),
        })
        return self.g["create"](rec)

    def kind_allowed(self, handle, kind):
        return self.g["kind_allowed"](handle, kind)

    def record_override(self, handle, tool, kind, reason):
        res = self.g["record_override"](handle, tool, kind, reason)
        if isinstance(res, tuple):
            ok, err = res
        else:
            ok, err = res, None
        return _py(ok), _py(err)

    def get_raw(self, handle):
        return _py(self.g["get_raw"](handle))

    def list_raw(self):
        return _py(self.g["list_raw"]())

    def mark_in_use(self, handle, site_handle):
        return self.g["mark_in_use"](handle, site_handle)

    def remove(self, handle):
        removed, remaining, err = self.g["remove"](handle)
        return _py(removed), _py(remaining), _py(err)

    def find_conflicts(self, x, y, z, w, h, wall_cells=(), other_footprints=()):
        wc = self._cells(wall_cells)
        ofs = self.lua.table_from([self.lua.table_from(f) for f in other_footprints])
        return _py(self.g["find_conflicts"](x, y, z, w, h, wc, ofs, None))

    def check_tiles(self, tiles, holding=None, res_id=None, kind=None, override=None):
        ts = self.lua.table_from([self.lua.table_from(t) for t in tiles])
        return _py(self.g["check_tiles"](ts, holding, res_id, kind, override))

    def override_needed(self, tiles, res_id, kind):
        ts = self.lua.table_from([self.lua.table_from(t) for t in tiles])
        return self.g["override_needed"](ts, res_id, kind)

    def filter_reserved_rects(self, candidates, w, h, z, res_id=None):
        """candidates: a list of (x, y) top-left corners of a shared w x h
        window at level z -- the exact shape df-overseer-diggable.lua's and
        df-overseer-openarea.lua's own ranking functions filter."""
        cs = self.lua.table_from([self.lua.table_from({"x": x, "y": y}) for x, y in candidates])
        tiles_for = self.lua.eval(
            "function(rect_tiles, w, h, z) return function(c) return rect_tiles(c.x, c.y, z, w, h) end end"
        )(self.g["rect_tiles"], w, h, z)
        kept = self.g["filter_reserved"](cs, res_id, tiles_for)
        return [(c["x"], c["y"]) for c in _py(kept)]

    def rect_tiles(self, x, y, z, w, h):
        return _py(self.g["rect_tiles"](x, y, z, w, h))


@pytest.fixture
def w():
    return World()


def wall(*cells):
    """0-based (dx, dy) pairs -> the 'dx,dy' key strings wall_cells uses."""
    return [f"{dx},{dy}" for dx, dy in cells]


# ---------------------------------------------------------------------------
# rect_tiles / basic create+get+list
# ---------------------------------------------------------------------------


def test_rect_tiles_enumerates_every_cell_of_the_box(w):
    tiles = w.rect_tiles(10, 20, 5, 2, 3)
    assert len(tiles) == 6
    assert {(t["x"], t["y"], t["z"]) for t in tiles} == {
        (10, 20, 5), (11, 20, 5), (10, 21, 5), (11, 21, 5), (10, 22, 5), (11, 22, 5),
    }


def test_create_assigns_sequential_handles_and_stamps_the_tick(w):
    h1 = w.create(0, 0, 0, 3, 3, purpose="first")
    h2 = w.create(100, 0, 0, 3, 3, purpose="second")
    assert h1 == "res-1" and h2 == "res-2"
    rec = w.get_raw(h1)
    assert rec["purpose"] == "first" and rec["created_tick"] == 1000
    assert rec.get("site_handle") is None  # nil in Lua: the key is simply absent


def test_list_raw_is_sorted_by_handle_and_carries_every_field(w):
    w.create(0, 0, 0, 3, 3, purpose="a")
    w.create(50, 0, 0, 4, 4, purpose="b")
    rows = w.list_raw()
    assert [r["handle"] for r in rows] == ["res-1", "res-2"]
    assert rows[1]["w"] == 4 and rows[1]["purpose"] == "b"


# ---------------------------------------------------------------------------
# check_tiles: the shared refusal every designating tool calls
# ---------------------------------------------------------------------------


def test_check_tiles_refuses_a_tile_inside_a_reservation_naming_the_handle(w):
    w.create(10, 10, 0, 5, 5, purpose="planned bedroom row 3")
    conflict = w.check_tiles([{"x": 12, "y": 12, "z": 0}])
    assert conflict is not None
    assert conflict["handle"] == "res-1"
    assert conflict["purpose"] == "planned bedroom row 3"
    assert conflict["near_landmark"] == "Well"
    # no coordinate anywhere in the conflict object or its message
    assert "12" not in str(conflict["message"])
    assert "10" not in str(conflict["message"])
    assert "res-1" in conflict["message"]
    assert "planned bedroom row 3" in conflict["message"]


def test_check_tiles_is_clear_for_an_unreserved_tile(w):
    w.create(10, 10, 0, 5, 5)
    assert w.check_tiles([{"x": 0, "y": 0, "z": 0}]) is None


def test_check_tiles_lets_the_holder_through_its_own_reservation(w):
    handle = w.create(10, 10, 0, 5, 5)
    assert w.check_tiles([{"x": 12, "y": 12, "z": 0}], holding=handle) is None


def test_check_tiles_still_refuses_a_non_holder_even_if_some_other_call_holds_it(w):
    handle = w.create(10, 10, 0, 5, 5)
    # a DIFFERENT handle than the one covering this tile does not exempt it
    conflict = w.check_tiles([{"x": 12, "y": 12, "z": 0}], holding="res-999")
    assert conflict is not None and conflict["handle"] == handle


def test_check_tiles_ignores_a_different_z_level(w):
    w.create(10, 10, 0, 5, 5)
    assert w.check_tiles([{"x": 12, "y": 12, "z": 1}]) is None


# ---------------------------------------------------------------------------
# find_conflicts: the shared-wall correction (user's 2026-09-30 revision of
# decision 5)
# ---------------------------------------------------------------------------


def test_two_rooms_sharing_a_wall_line_are_accepted(w):
    # A 3x3 footprint at (0,0): column x=2 (dx=2) is its east wall.
    # A second 3x3 footprint at (2,0): column x=2 (dx=0 of the new one) is
    # its west wall -- the SAME world tiles as the first footprint's east
    # wall. Every overlapping tile is wall on both sides.
    first_wall = wall((2, 0), (2, 1), (2, 2))
    w.create(0, 0, 0, 3, 3, wall_cells=first_wall, purpose="cell A")
    new_wall = wall((0, 0), (0, 1), (0, 2))
    conflicts = w.find_conflicts(2, 0, 0, 3, 3, new_wall)
    assert conflicts == []


def test_an_interior_overlap_is_refused_naming_the_conflict(w):
    first_wall = wall((2, 0), (2, 1), (2, 2))
    w.create(0, 0, 0, 3, 3, wall_cells=first_wall, purpose="cell A")
    # The new footprint's own west column (its wall) lines up with the
    # existing footprint's SECOND column (its interior, x=1) instead of its
    # wall column -- a real overlap that is not wall-on-both-sides anywhere
    # it touches an existing cell.
    new_wall = wall((0, 0), (0, 1), (0, 2))
    conflicts = w.find_conflicts(1, 0, 0, 3, 3, new_wall)
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == "reservation"
    assert conflicts[0]["handle"] == "res-1"
    assert conflicts[0]["purpose"] == "cell A"


def test_an_unclassified_tile_is_never_assumed_compatible(w):
    # No wall_cells declared for either side -- overlap on an unclassified
    # tile is refused, the strict/never-assume-compatible default.
    w.create(0, 0, 0, 3, 3, wall_cells=[])
    conflicts = w.find_conflicts(2, 0, 0, 3, 3, [])
    assert len(conflicts) == 1


def test_find_conflicts_also_checks_supplied_other_footprints_eg_blueprint_sites(w):
    site = {"x": 100, "y": 100, "z": 0, "w": 3, "h": 3, "wall_cells": w._cells([]), "label": "site-1"}
    conflicts = w.find_conflicts(101, 101, 0, 2, 2, [], other_footprints=[site])
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == "site"
    assert conflicts[0]["handle"] == "site-1"


def test_find_conflicts_is_clear_when_footprints_do_not_overlap_at_all(w):
    w.create(0, 0, 0, 3, 3, purpose="cell A")
    assert w.find_conflicts(100, 100, 0, 3, 3, []) == []


# ---------------------------------------------------------------------------
# lifecycle: mark_in_use / remove / shared-wall tile stays held
# ---------------------------------------------------------------------------


def test_mark_in_use_records_the_carved_site_handle(w):
    handle = w.create(0, 0, 0, 3, 3)
    assert w.get_raw(handle).get("site_handle") is None
    w.mark_in_use(handle, "site-7")
    assert w.get_raw(handle)["site_handle"] == "site-7"


def test_unreserve_frees_an_unshared_tile(w):
    handle = w.create(10, 10, 0, 5, 5)
    removed, remaining, err = w.remove(handle)
    assert removed is True and remaining == [] and err is None
    assert w.check_tiles([{"x": 12, "y": 12, "z": 0}]) is None
    assert w.get_raw(handle) is None


def test_a_shared_wall_tile_stays_held_after_one_holder_unreserves(w):
    # Two adjacent cells sharing the wall at world x=2 (first's east, dx=2;
    # second's west, dx=0), exactly the accepted-overlap shape above.
    h1 = w.create(0, 0, 0, 3, 3, wall_cells=wall((2, 0), (2, 1), (2, 2)), purpose="cell A")
    h2 = w.create(2, 0, 0, 3, 3, wall_cells=wall((0, 0), (0, 1), (0, 2)), purpose="cell B")
    assert w.find_conflicts is not None  # (sanity: creation itself never checks conflicts)

    # Before removal: the shared wall tile is covered by BOTH -- h1's own
    # apply may proceed there (holding h1), and so may h2's.
    assert w.check_tiles([{"x": 2, "y": 1, "z": 0}], holding=h1) is None
    assert w.check_tiles([{"x": 2, "y": 1, "z": 0}], holding=h2) is None

    removed, remaining, err = w.remove(h1)
    assert removed is True and err is None
    assert remaining == [h2], "the shared wall tile is still covered by cell B"

    # h1 is gone; the shared tile is STILL reserved -- now only by h2.
    conflict = w.check_tiles([{"x": 2, "y": 1, "z": 0}])
    assert conflict is not None and conflict["handle"] == h2
    # h2 itself may still build/designate it.
    assert w.check_tiles([{"x": 2, "y": 1, "z": 0}], holding=h2) is None
    # A tile that was ONLY inside h1's own footprint (not shared) is freed.
    assert w.check_tiles([{"x": 0, "y": 0, "z": 0}]) is None


def test_remove_rejects_a_malformed_or_unknown_handle(w):
    removed, remaining, err = w.remove("not-a-handle")
    assert removed is False and err is not None
    removed2, _, err2 = w.remove("res-999")
    assert removed2 is False and "no reservation" in err2


def test_created_tick_is_absolute_so_age_survives_a_year_boundary():
    # ReadCurrentTick alone is the tick within the current year and wraps to
    # 0 at New Year; created_tick must be absolute (cur_year * 403200 +
    # cur_year_tick, df-overseer-clock.lua's formula) or an age read after
    # the boundary goes negative.
    w = World()
    w.lua.execute("YEAR = 3; NOW = 403000")
    handle = w.create(10, 10, 0, 3, 3)
    assert w.g["get_raw"](handle)["created_tick"] == 3 * 403200 + 403000
    w.lua.execute("YEAR = 4; NOW = 100")
    assert w.g["abs_tick"]() - w.g["get_raw"](handle)["created_tick"] == 300


def test_abs_tick_is_nil_when_the_year_cannot_be_read():
    w = World()
    w.lua.execute("YEAR = nil")
    assert w.g["abs_tick"]() is None


# ---------------------------------------------------------------------------
# handoffs/2026-09-30-reservation-holding.md: allowed_kinds, RES_ID/OVERRIDE
# ---------------------------------------------------------------------------


def test_kind_allowed_reads_the_stored_list_and_is_false_for_unknown_handle_or_kind(w):
    handle = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed", "bedroom"])
    assert w.kind_allowed(handle, "bed") is True
    assert w.kind_allowed(handle, "bedroom") is True
    assert w.kind_allowed(handle, "carpenter") is False
    assert w.kind_allowed("res-999", "bed") is False


def test_create_defaults_allowed_kinds_and_overrides_to_empty_never_nil(w):
    handle = w.create(10, 10, 0, 5, 5)
    rec = w.get_raw(handle)
    assert rec["allowed_kinds"] == []
    assert rec["overrides"] == []


def test_check_tiles_with_res_id_allows_a_kind_the_reservation_lists(w):
    handle = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed", "bedroom"])
    tile = [{"x": 11, "y": 11, "z": 0}]
    assert w.check_tiles(tile, res_id=handle, kind="bed") is None
    assert w.check_tiles(tile, res_id=handle, kind="bedroom") is None


def test_check_tiles_with_res_id_refuses_a_kind_not_on_the_list_naming_the_allowed_ones(w):
    handle = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed", "bedroom"])
    conflict = w.check_tiles([{"x": 11, "y": 11, "z": 0}], res_id=handle, kind="carpenter")
    assert conflict is not None
    assert conflict["handle"] == handle
    assert "carpenter" in conflict["message"]
    assert "bed" in conflict["message"] and "bedroom" in conflict["message"]
    assert "OVERRIDE" in conflict["message"]
    # no coordinate leaked
    assert "10" not in conflict["message"] and "11" not in conflict["message"]


def test_check_tiles_with_res_id_and_override_allows_any_kind_and_does_not_record_by_itself(w):
    handle = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed"])
    tile = [{"x": 11, "y": 11, "z": 0}]
    assert w.check_tiles(tile, res_id=handle, kind="carpenter", override="needed for X") is None
    # check_tiles is a pure query: it never appends to overrides on its own.
    assert w.get_raw(handle)["overrides"] == []


def test_record_override_appends_tick_tool_kind_reason_and_leaves_purpose_and_kinds_unchanged(w):
    handle = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed"])
    ok, err = w.record_override(handle, "workshop.build", "carpenter", "needed for X")
    assert ok is True and err is None
    rec = w.get_raw(handle)
    assert len(rec["overrides"]) == 1
    o = rec["overrides"][0]
    assert o["tool"] == "workshop.build" and o["kind"] == "carpenter" and o["reason"] == "needed for X"
    assert o["tick"] == 1000
    # A one-off override never changes the reservation's own purpose or its
    # allowed kinds -- re-purposing is unreserve plus a new reserve, never this.
    assert rec["purpose"] == "planned bedroom"
    assert rec["allowed_kinds"] == ["bed"]

    ok2, err2 = w.record_override(handle, "workshop.build", "carpenter", "a second one-off")
    assert ok2 is True
    assert len(w.get_raw(handle)["overrides"]) == 2


def test_record_override_rejects_a_malformed_or_unknown_handle(w):
    ok, err = w.record_override("not-a-handle", "t", "k", "r")
    assert ok is False and "RES_ID" in err
    ok2, err2 = w.record_override("res-999", "t", "k", "r")
    assert ok2 is False and "no reservation" in err2


def test_check_tiles_res_id_does_not_exempt_a_tile_covered_by_a_different_reservation(w):
    other = w.create(0, 0, 0, 3, 3, purpose="office", allowed_kinds=["chair", "office"])
    mine = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed"])
    # A tile inside `other`'s footprint, checked with `mine`'s own RES_ID and
    # a kind `other` would have allowed: still refused, naming `other`.
    conflict = w.check_tiles([{"x": 1, "y": 1, "z": 0}], res_id=mine, kind="chair")
    assert conflict is not None
    assert conflict["handle"] == other


def test_check_tiles_rejects_a_malformed_or_unknown_res_id(w):
    conflict = w.check_tiles([{"x": 0, "y": 0, "z": 0}], res_id="not-a-handle", kind="bed")
    assert conflict is not None and "RES_ID" in conflict["message"]
    conflict2 = w.check_tiles([{"x": 0, "y": 0, "z": 0}], res_id="res-999", kind="bed")
    assert conflict2 is not None and "no reservation" in conflict2["message"]


def test_override_needed_true_only_when_a_tile_is_in_res_id_and_kind_is_not_allowed(w):
    handle = w.create(10, 10, 0, 5, 5, purpose="planned bedroom", allowed_kinds=["bed", "bedroom"])
    tile_inside = [{"x": 11, "y": 11, "z": 0}]
    tile_outside = [{"x": 0, "y": 0, "z": 0}]
    # kind not allowed, tile inside res_id -> needed.
    assert w.override_needed(tile_inside, handle, "carpenter") is True
    # kind already allowed -> never needed, even though the tile is inside.
    assert w.override_needed(tile_inside, handle, "bed") is False
    assert w.override_needed(tile_inside, handle, "bedroom") is False
    # tile not inside res_id at all -> never needed, whatever the kind.
    assert w.override_needed(tile_outside, handle, "carpenter") is False
    # a mixed tile list: needed if AT LEAST ONE tile is inside and unallowed.
    assert w.override_needed(tile_outside + tile_inside, handle, "carpenter") is True


def test_override_needed_is_false_for_a_malformed_or_unknown_res_id(w):
    tile = [{"x": 0, "y": 0, "z": 0}]
    assert w.override_needed(tile, "not-a-handle", "carpenter") is False
    assert w.override_needed(tile, "res-999", "carpenter") is False
    assert w.override_needed(tile, None, "carpenter") is False


def test_filter_reserved_drops_a_candidate_overlapping_any_reservation_without_res_id(w):
    # A 3x3 reservation at (10, 10); one candidate window overlaps it, two
    # do not.
    w.create(10, 10, 0, 3, 3, purpose="planned bedroom")
    candidates = [(0, 0), (9, 9), (100, 100)]  # (9,9)-(11,11) overlaps (10,10)-(12,12)
    kept = w.filter_reserved_rects(candidates, 3, 3, 0)
    assert kept == [(0, 0), (100, 100)]


def test_filter_reserved_keeps_a_candidate_inside_res_id_but_still_drops_others(w):
    mine = w.create(10, 10, 0, 3, 3, purpose="planned bedroom")
    other = w.create(50, 50, 0, 3, 3, purpose="planned office")
    candidates = [(9, 9), (49, 49), (100, 100)]
    kept = w.filter_reserved_rects(candidates, 3, 3, 0, res_id=mine)
    assert kept == [(9, 9), (100, 100)], "the OTHER reservation's candidate is still dropped"


def test_filter_reserved_never_ranks_a_reserved_candidate_a_finder_would_have_offered(w):
    # The exact scenario the handoff names: a finder's raw candidate list
    # includes one sitting on reserved ground; filter_reserved is what a
    # finder calls BEFORE ranking/choosing, so RANK 1 never lands there.
    w.create(5, 5, 0, 4, 4, purpose="planned bedroom row 3")
    raw_candidates_by_distance = [(5, 5), (20, 20), (40, 40)]  # closest first
    kept = w.filter_reserved_rects(raw_candidates_by_distance, 4, 4, 0)
    assert kept[0] == (20, 20), "the closest candidate was reserved and must not become rank 1"


def test_filter_reserved_returns_everything_unchanged_when_nothing_is_reserved(w):
    candidates = [(0, 0), (10, 10)]
    assert w.filter_reserved_rects(candidates, 2, 2, 0) == candidates


def test_holding_handle_still_bypasses_every_check_regardless_of_res_id_kind(w):
    # The TRUE holder (df-overseer-blueprint.lua's own apply) is unaffected
    # by the new res_id/kind/override machinery: it was, and remains, a full
    # bypass on its own reservation's own tiles.
    handle = w.create(10, 10, 0, 5, 5, allowed_kinds=["bed"])
    assert w.check_tiles([{"x": 11, "y": 11, "z": 0}], holding=handle, kind="anything-at-all") is None
