"""Tile-set reservations and the `portal` class (circulation hands, red team B2).

Runs the REAL scripts/dfhack/df-overseer-reservations.lua under lupa, reusing
the fake world of test_reservations_lua_logic.py. Proves:
  - a reservation can be any set of tiles on any levels, reads back with a
    bounding box, and is held per level;
  - a room hung on a corridor is allowed through a portal tile, but only one
    room per portal, only a room with a corridor, and never a role-less portal;
  - the original shared-wall rule and every pre-2026-10-08 rectangle record
    still behave as before.

Skipped when lupa is not installed.
"""

import pytest

pytest.importorskip("lupa")

from test_reservations_lua_logic import World, _py, wall  # noqa: E402


class TileWorld(World):
    def create_tile_set(self, tiles, role="corridor", purpose="route"):
        rec = self.lua.table_from({
            "tiles": self.lua.table_from({f"{x},{y},{z}": c for (x, y, z), c in tiles.items()}),
            "role": role, "purpose": purpose,
        })
        res = self.g["create_tile_set"](rec)
        if isinstance(res, tuple):
            return _py(res[0]), _py(res[1])
        return res, None

    def tile_conflicts(self, tiles, role=None):
        t = self.lua.table_from({f"{x},{y},{z}": c for (x, y, z), c in tiles.items()})
        return _py(self.g["find_conflicts_tiles"](t, role, None, None))

    def tiles_of(self, handle):
        return _py(self.g["tiles_of"](handle))

    def rect_conflicts(self, x, y, z, w, h, wall_keys=(), portal_keys=(), role=None):
        got = self.g["find_conflicts"](x, y, z, w, h, self._cells(wall_keys), None, None,
                                       self._cells(portal_keys), role)
        return _py(got)


@pytest.fixture
def w():
    return TileWorld()


def corridor_row(z=0):
    """A 1-wide corridor along y=10, x 0..9, with a wall row above and below."""
    tiles = {}
    for x in range(10):
        tiles[(x, 10, z)] = "strict"
        tiles[(x, 9, z)] = "wall"
        tiles[(x, 11, z)] = "wall"
    return tiles


def test_tile_set_spans_levels_and_reports_a_bounding_box(w):
    tiles = {(5, 5, 0): "strict", (5, 6, 0): "strict", (5, 6, 1): "strict", (6, 6, 2): "strict"}
    handle, err = w.create_tile_set(tiles)
    assert err is None and handle == "res-1"
    rec = w.get_raw(handle)
    assert (rec["x"], rec["y"], rec["z"], rec["w"], rec["h"], rec["z_max"]) == (5, 5, 0, 2, 2, 2)
    assert w.check_tiles([{"x": 5, "y": 6, "z": 1}]) is not None
    assert w.check_tiles([{"x": 5, "y": 5, "z": 1}]) is None
    assert len(w.tiles_of(handle)) == 4


def test_tile_set_rejects_a_bad_class_and_an_empty_set(w):
    assert w.create_tile_set({(1, 1, 0): "floor"})[0] is None
    assert w.create_tile_set({})[0] is None


def test_unreserving_a_tile_set_frees_it_but_a_shared_wall_stays_held(w):
    corr, _ = w.create_tile_set(corridor_row())
    other = w.create(0, 8, 0, 10, 2, wall_cells=wall(*[(x, 1) for x in range(10)]))  # y=8,9
    removed, remaining, err = w.remove(corr)
    assert removed and remaining == [other]
    assert w.check_tiles([{"x": 3, "y": 10, "z": 0}]) is None
    assert w.check_tiles([{"x": 3, "y": 9, "z": 0}]) is not None


def test_a_room_hung_on_a_corridor_is_allowed_through_a_portal(w):
    w.create_tile_set(corridor_row())
    room = {(x, y, 0): "strict" for x in range(3, 6) for y in range(6, 9)}
    room[(4, 9, 0)] = "portal"      # the entrance gap sits on the corridor's wall row
    assert w.tile_conflicts(room, role="room") == []


def test_without_the_portal_class_the_same_room_is_refused(w):
    """The bug this fixes: the entrance tile read 'strict' and clashed with the wall."""
    w.create_tile_set(corridor_row())
    conflicts = w.tile_conflicts({(4, 9, 0): "strict"}, role="room")
    assert [c["handle"] for c in conflicts] == ["res-1"]


def test_a_portal_on_a_corridor_floor_tile_is_refused(w):
    w.create_tile_set(corridor_row())
    conflicts = w.tile_conflicts({(4, 10, 0): "portal"}, role="room")
    assert [c["handle"] for c in conflicts] == ["res-1"]


def test_a_second_room_on_the_same_portal_is_refused(w):
    w.create_tile_set(corridor_row())
    room1, _ = w.create_tile_set({(4, 9, 0): "portal", (4, 8, 0): "strict"}, role="room")
    conflicts = w.tile_conflicts({(4, 9, 0): "portal", (4, 8, 0): "strict"}, role="room")
    assert room1 in [c["handle"] for c in conflicts]


def test_a_second_corridor_on_a_room_and_corridor_portal_is_refused(w):
    w.create_tile_set(corridor_row())
    w.create_tile_set({(4, 9, 0): "portal"}, role="room")
    conflicts = w.tile_conflicts({(4, 9, 0): "portal"}, role="corridor")
    # clashes with the first corridor (same role as the newcomer) at least
    assert "res-1" in [c["handle"] for c in conflicts]


def test_a_portal_with_no_role_never_shares(w):
    w.create_tile_set(corridor_row())
    assert w.tile_conflicts({(4, 9, 0): "portal"}, role=None) != []


def test_two_rooms_still_share_only_walls(w):
    w.create_tile_set({(0, 0, 0): "wall"}, role="room")
    assert w.tile_conflicts({(0, 0, 0): "wall"}, role="room") == []
    assert w.tile_conflicts({(0, 0, 0): "portal"}, role="room") != []


def test_a_template_rect_with_a_portal_cell_hangs_on_a_corridor(w):
    w.create_tile_set(corridor_row())
    # a 5x5 cell at (1,5): its south ring row is y=9 (the corridor's wall row),
    # entrance gap at column index 2 of that row, every other ring tile wall.
    ring = [f"{x},{y}" for x in range(5) for y in range(5)
            if (x in (0, 4) or y in (0, 4)) and (x, y) != (2, 4)]
    assert w.rect_conflicts(1, 5, 0, 5, 5, wall_keys=ring, portal_keys=["2,4"], role="room") == []
    # the same cell with no portal declared is refused on its entrance tile
    ring_all = ring + ["2,4"]
    got = w.rect_conflicts(1, 5, 0, 5, 5, wall_keys=ring, portal_keys=[], role="room")
    assert [c["handle"] for c in got] == ["res-1"]
    assert ring_all  # (kept for readability of the case above)


def test_legacy_rect_records_still_read_and_conflict_as_before(w):
    w.create(10, 10, 0, 5, 5, wall_cells=wall((0, 0)))
    assert w.tile_conflicts({(12, 12, 0): "strict"}) != []
    assert w.tile_conflicts({(10, 10, 0): "wall"}) == []
    assert w.tile_conflicts({(10, 10, 0): "portal"}, role="room") != []
    assert [t["class"] for t in w.tiles_of("res-1") if (t["x"], t["y"]) == (10, 10)] == ["wall"]
