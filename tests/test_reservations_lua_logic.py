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

    def create(self, x, y, z, w, h, wall_cells=(), blueprint="bp", purpose="test", orient="none"):
        rec = self.lua.table_from({
            "x": x, "y": y, "z": z, "w": w, "h": h, "orient": orient,
            "bw": w, "bh": h, "blueprint": blueprint, "purpose": purpose,
            "wall_cells": self._cells(wall_cells),
        })
        return self.g["create"](rec)

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

    def check_tiles(self, tiles, holding=None):
        ts = self.lua.table_from([self.lua.table_from(t) for t in tiles])
        return _py(self.g["check_tiles"](ts, holding))

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
