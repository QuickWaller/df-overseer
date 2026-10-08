"""df-overseer-circulation.lua reads reservations through
`reservations.tiles_of(handle)` (both stored shapes), not the rectangle
fields, which describe only the lowest level of a multi-level tile set.
Same lupa harness as test_circulation_lua_logic.py."""

import pytest

lupa = pytest.importorskip("lupa")

from test_circulation_lua_logic import Circ, _py  # noqa: E402

LAYER = ["#####", "#...#", "#####"]


@pytest.fixture
def circ():
    return Circ({0: LAYER}, {"sites": [], "reservations": [], "zones": []})


def _fake_modules(circ):
    circ.lua.execute("""
        df.building_type = { Door = 1 }
        FAKE_MODULES["df-overseer-blueprint"] = { all_sites_raw = function() return {} end }
        FAKE_MODULES["df-overseer-reservations"] = {
          -- res-1: a stair column, a tile set over three levels. Its rectangle
          -- fields describe only the lowest level (z=0, 1x1).
          -- res-2: a plain rectangle record with a 3x2 footprint.
          list_raw = function()
            return {
              { handle = "res-1", x = 4, y = 4, z = 0, w = 1, h = 1 },
              { handle = "res-2", x = 10, y = 10, z = 1, w = 3, h = 2 },
            }
          end,
          tiles_of = function(h)
            if h == "res-1" then
              return { {x=4,y=4,z=0,class="strict"}, {x=4,y=4,z=1,class="strict"}, {x=4,y=5,z=2,class="strict"} }
            end
            local out = {}
            for x = 10, 12 do for y = 10, 11 do out[#out+1] = {x=x,y=y,z=1,class="strict"} end end
            return out
          end,
        }
    """)


def test_live_world_reads_reservation_tiles_on_every_level(circ):
    _fake_modules(circ)
    w = _py(circ.lua.eval("(function() local w = live_world(); return w.reservations end)()"))
    by = {(r["id"], r["z"]): r for r in w}
    # the stair column opens a window on all three of its levels, which the
    # rectangle fields (z=0 only) never would
    assert {("res-1", 0), ("res-1", 1), ("res-1", 2)} <= set(by)
    assert by[("res-2", 1)]["w"] == 3 and by[("res-2", 1)]["h"] == 2


def test_live_world_falls_back_to_the_rectangle_when_tiles_unreadable(circ):
    _fake_modules(circ)
    circ.lua.execute("""FAKE_MODULES["df-overseer-reservations"].tiles_of = function() error("boom") end""")
    out = _py(circ.lua.eval("(function() local w, errs = live_world(); return {res = w.reservations, errs = errs} end)()"))
    assert {r["id"] for r in out["res"]} == {"res-1", "res-2"}
    assert any("could not read tiles of reservation res-1" in e for e in out["errs"])


def test_reservation_entries_one_rect_per_level(circ):
    r = _py(circ.lua.eval(
        "(function() return reservation_entries('res-9', {{x=2,y=3,z=1},{x=5,y=3,z=1},{x=2,y=7,z=0}}) end)()"))
    assert r == [
        {"id": "res-9", "x": 2, "y": 7, "z": 0, "w": 1, "h": 1},
        {"id": "res-9", "x": 2, "y": 3, "z": 1, "w": 4, "h": 1},
    ]


def test_private_kinds_and_site_kinds_come_from_the_room_kind_data(circ):
    d = _py(circ.lua.eval("(function() local d = data(); return {p = d.private_kinds, s = d.site_room_kinds} end)()"))
    assert d["p"] == {"Bedroom": True, "Dormitory": True, "Office": True}
    assert d["s"]["bedroom-cell"] == "Bedroom" and d["s"]["office-room"] == "Office"
