"""Runs the REAL scripts/dfhack/df-overseer-circulation.lua (stage C1, the
read-only circulation graph) against small fake maps, using lupa.

Proves the pure logic: window from our own records, the hard tile cap that
refuses rather than truncates, a bedroom-through-bedroom chain, a dead end, a
bridge between named anchors, vertical links, hidden tiles becoming frontier
(unknown) rather than guessed, named walk numbers, and that no output field
carries a coordinate (docs/PURPOSE.md commitment 1). It proves nothing about
real DFHack tile reads; that is the live read-only timing run.

Skipped when lupa is not installed (it is not a repo dependency).
"""

import re
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-circulation.lua"
STUB = REPO_ROOT / "tests" / "lua_stubs" / "dfhack_circulation_world.lua"


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if not keys:
        return []
    if all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
        return [_py(v[k]) for k in sorted(keys)]
    return {str(k): _py(v[k]) for k in keys}


def _lua_literal(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return "[==[" + v + "]==]"
    if isinstance(v, dict):
        return "{" + ",".join("[ %s ] = %s" % (_lua_literal(k), _lua_literal(x)) for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(_lua_literal(x) for x in v) + "}"
    raise TypeError(v)


class Circ:
    def __init__(self, layers, spec):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("ROOMKINDS_LUA_PATH = %r" % str(REPO_ROOT / "scripts" / "dfhack" / "df-overseer-roomkinds.lua"))
        self.lua.execute(STUB.read_text(encoding="utf-8"))
        load = self.lua.eval("function(src, name) return load(src, name) end")
        chunk = load(LUA.read_text(encoding="utf-8"), "circulation.lua")
        assert not isinstance(chunk, tuple), chunk
        chunk()
        self.g = self.lua.globals()
        self.lua.execute("WORLD = make_world(%s, %s)" % (_lua_literal(layers), _lua_literal(spec)))

    def data(self):
        return self.g.data()

    def build(self, cap=None):
        if cap is None:
            return self.lua.eval("(function() return build_graph(WORLD) end)()")
        return self.lua.eval("(function() return build_graph(WORLD, {cap=%d}) end)()" % cap)

    def report(self):
        self.lua.execute("GRAPH = assert(build_graph(WORLD))")
        return _py(self.g.summarize(self.g.GRAPH))

    def walk(self, a, b):
        self.lua.execute("GRAPH = assert(build_graph(WORLD))")
        return _py(self.g.walk_between(self.g.GRAPH, a, b))


# 22 wide.  R1 x1-2, door x3, R2 x4-5, door x6, R3 x7-8 (all y1).  R2 has the
# only door to the corridor (x4,y2).  Dining hall x10-20 y1, reached from the
# corridor by the gap at x20,y2.  A well sits in the wall at x12,y2 with the
# corridor tile below it.  The corridor (y3) ends in a dead-end west tip past a
# stair landing at x2.  Level 1 has the matching stair.
LAYER0 = [
    "######################",
    "#..D..D..#...........#",
    "####D#######w#######.#",
    "#.<..................#",
    "######################",
]
LAYER1 = [
    "######################",
    "######################",
    "######################",
    "#.>.#################.",
    "######################",
]
LAYER1[3] = "#.>.###################"[:21] + "#"

ZONES = [
    {"id": 11, "kind": "Bedroom", "name": "", "x1": 1, "y1": 1, "x2": 2, "y2": 1, "z": 0},
    {"id": 12, "kind": "Bedroom", "name": "", "x1": 4, "y1": 1, "x2": 5, "y2": 1, "z": 0},
    {"id": 13, "kind": "Bedroom", "name": "", "x1": 7, "y1": 1, "x2": 8, "y2": 1, "z": 0},
    {"id": 20, "kind": "DiningHall", "name": "Dining Hall", "x1": 10, "y1": 1, "x2": 20, "y2": 1, "z": 0},
    {"id": 30, "kind": "Pen", "name": "", "x1": 0, "y1": 0, "x2": 5, "y2": 5, "z": 0},
]
SPEC = {
    "sites": [{"id": "site-1", "kind": "bedroom-block", "x": 1, "y": 1, "z": 0, "w": 8, "h": 1}],
    "reservations": [{"id": "res-1", "x": 1, "y": 3, "z": 1, "w": 3, "h": 1}],
    "zones": ZONES,
    "landmarks": [{"id": 7, "name": "Well", "kind": "Well", "x1": 12, "y1": 2, "x2": 12, "y2": 2, "z": 0}],
}


def test_layers_are_rectangular():
    assert all(len(r) == 22 for r in LAYER0), [len(r) for r in LAYER0]
    assert all(len(r) == 22 for r in LAYER1), [len(r) for r in LAYER1]


@pytest.fixture
def circ():
    return Circ({0: LAYER0, 1: LAYER1}, SPEC)


def test_bedroom_chain_flags_rooms_reached_through_a_private_room(circ):
    r = circ.report()
    through = {row["room"]: row for row in r["checks"]["rooms_through_rooms"]}
    # R1 and R3 are only reachable through R2 (a bedroom).
    assert set(through) == {"Bedroom #11", "Bedroom #13"}
    for row in through.values():
        assert row["rooms_crossed"] == 1
        assert row["crosses_private_room"] is True
        assert row["through"][0]["room"] == "Bedroom #12"
        assert row["through"][0]["room_kind"] == "Bedroom"
        assert row["through"][0]["private"] is True
    assert r["flags"]["private_room_reached_only_through_a_private_room"] is True
    assert r["flags"]["room_reached_only_through_another_room"] is True
    assert "Dining Hall" not in through
    # The Pen zone is not a room kind and never becomes a node.
    assert not any(n.get("room_kind") == "Pen" for n in r["nodes"])


def test_bedrooms_opening_onto_each_other_are_listed(circ):
    r = circ.report()
    pairs = {tuple(sorted(o["rooms"])) for o in r["checks"]["private_rooms_opening_onto_each_other"]}
    assert ("Bedroom #11", "Bedroom #12") in pairs
    assert ("Bedroom #12", "Bedroom #13") in pairs
    assert r["flags"]["private_rooms_open_onto_each_other"] is True


def test_dead_end_is_found(circ):
    r = circ.report()
    assert r["flags"]["dead_end_present"] is True
    assert len(r["checks"]["dead_ends"]) >= 1
    assert r["checks"]["dead_ends"][0]["steps"] >= 1


def test_bridge_between_named_anchors_is_reported(circ):
    r = circ.report()
    assert r["flags"]["single_point_of_failure_between_anchors"] is True
    sides = []
    for b in r["checks"]["single_points_of_failure"]:
        assert b["side_a"]["anchors"] and b["side_b"]["anchors"]
        sides.append((set(b["side_a"]["anchors"]), set(b["side_b"]["anchors"])))
    # one stretch alone joins the Dining Hall to the Well side
    assert any(
        ("Dining Hall" in a and "Well" in b) or ("Dining Hall" in b and "Well" in a) for a, b in sides
    ), sides


def test_walk_numbers_to_dining_well_and_stairs(circ):
    r = circ.report()
    rows = {row["room"]: row for row in r["walks"]["rows"]}
    assert set(rows) == {"Bedroom #11", "Bedroom #12", "Bedroom #13"}
    for row in rows.values():
        assert row["dining_steps"] is not None and row["dining_steps"] > 0
        assert row["well_steps"] is not None
        assert row["stairs_steps"] is not None
    # R2 holds the corridor door, so it is the closest bedroom to the dining hall.
    assert rows["Bedroom #12"]["dining_steps"] < rows["Bedroom #11"]["dining_steps"]
    s = r["walks"]["by_room_kind"]["Bedroom"]
    assert s["rooms"] == 3
    assert s["dining"]["rooms_reaching"] == 3


def test_vertical_link_is_certain_for_a_stair(circ):
    r = circ.report()
    verts = [e for e in r["edges"] if e["kind"] == "vertical"]
    assert len(verts) == 1
    assert verts[0]["certainty"] == "certain"
    assert verts[0]["level_change"] == 1
    assert r["counts"]["vertical_edges"] == 1
    assert {n["level"] for n in r["nodes"]} == {0, 1}


def test_walk_between_named_endpoints(circ):
    w = circ.walk("Bedroom #11", "Dining Hall")
    assert w["status"] == "reachable"
    assert w["steps"] > 0
    assert w["rooms_walked_through"] == 1
    assert w["doors_on_path"] >= 2
    assert circ.walk("Bedroom #11", "Nowhere At All")["status"] == "unknown"


def test_cap_refuses_instead_of_truncating(circ):
    res = circ.build(cap=50)
    assert isinstance(res, tuple)
    graph, err = res
    assert graph is None
    assert "refusing" in err and "cap of 50" in err
    assert "not truncated" in err
    assert circ.g.WORLD.reads == 0  # refused before reading a single tile


def test_cap_in_data_cannot_be_raised_by_an_argument(circ):
    circ.data().max_window_tiles = 40
    res = circ.build(cap=10 ** 9)
    assert isinstance(res, tuple) and res[0] is None and "cap of 40" in res[1]


def test_no_records_refuses():
    res = Circ({0: LAYER0}, {}).build()
    assert isinstance(res, tuple) and res[0] is None


def test_hidden_tiles_are_unknown_not_guessed():
    layer = [
        "##########",
        "#........?",
        "##########",
    ]
    spec = {"sites": [{"id": "s", "kind": "k", "x": 1, "y": 1, "z": 0, "w": 8, "h": 1}]}
    r = Circ({0: layer}, spec).report()
    assert r["flags"]["has_unknowns"] is True
    assert any("not revealed" in u for u in r["unknown"])
    assert r["counts"]["nodes_by_kind"].get("frontier", 0) >= 1


def test_forbidden_door_is_recorded_on_the_edge():
    layer = [
        "#########",
        "#..F....#",
        "#########",
    ]
    zones = [
        {"id": 1, "kind": "Bedroom", "name": "", "x1": 1, "y1": 1, "x2": 2, "y2": 1, "z": 0},
        {"id": 2, "kind": "DiningHall", "name": "Hall", "x1": 4, "y1": 1, "x2": 7, "y2": 1, "z": 0},
    ]
    r = Circ({0: layer}, {"zones": zones}).report()
    assert "forbidden" in [d for e in r["edges"] for d in e["doors"]]


def test_ramp_link_is_marked_inferred():
    low = ["#####", "#.v.#", "#####"]
    high = ["#####", "#..^#", "#####"]
    # the ramp at x2 has a ramp top directly above; floor beside the top
    high = ["#####", "#.^.#", "#####"]
    zones = [
        {"id": 1, "kind": "DiningHall", "name": "Low", "x1": 1, "y1": 1, "x2": 1, "y2": 1, "z": 0},
        {"id": 2, "kind": "DiningHall", "name": "High", "x1": 1, "y1": 1, "x2": 1, "y2": 1, "z": 1},
    ]
    r = Circ({0: low, 1: high}, {"zones": zones}).report()
    verts = [e for e in r["edges"] if e["kind"] == "vertical"]
    assert verts and all(v["certainty"] == "inferred" for v in verts)


def _walk_values(v, path=""):
    if isinstance(v, dict):
        for k, x in v.items():
            yield ("key", k, path)
            yield from _walk_values(x, path + "/" + k)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _walk_values(x, path + "[%d]" % i)
    else:
        yield ("value", v, path)


BANNED_KEYS = {"x", "y", "z", "x1", "y1", "x2", "y2", "pos", "position", "tile", "tiles",
               "coords", "coordinates", "grid", "map", "col"}


def test_no_output_field_contains_coordinates(circ):
    r = circ.report()
    for kind, val, path in _walk_values(r):
        if kind == "key":
            assert val not in BANNED_KEYS, (val, path)
        elif isinstance(val, str):
            assert not re.search(r"\(\s*\d+\s*,\s*\d+", val), (val, path)
            assert not re.fullmatch(r"\d+\s*,\s*\d+(\s*,\s*\d+)?", val), (val, path)

    def lists(v):
        if isinstance(v, dict):
            for x in v.values():
                yield from lists(x)
        elif isinstance(v, list):
            yield v
            for x in v:
                yield from lists(x)

    for lst in lists(r):
        assert not (len(lst) in (2, 3) and all(isinstance(i, (int, float)) for i in lst)), lst
    w = circ.walk("Bedroom #11", "Dining Hall")
    for kind, val, path in _walk_values(w):
        if kind == "key":
            assert val not in BANNED_KEYS, (val, path)


def test_site_without_a_zone_stands_in_as_a_room():
    # Two 5x5 bedroom-cell sites (3x3 interior, entrance gap south) off one
    # corridor, shells dug but no zone yet: they are still bedrooms.
    layer = [
        "##########",
        "#...##...#",
        "#...##...#",
        "#...##...#",
        "##.####.##",
        "#........#",
        "##########",
    ]
    sites = [
        {"id": "site-3", "kind": "bedroom-cell-v1", "x": 0, "y": 0, "z": 0, "w": 5, "h": 5},
        {"id": "site-4", "kind": "bedroom-cell-v1", "x": 5, "y": 0, "z": 0, "w": 5, "h": 5},
    ]
    r = Circ({0: layer}, {"sites": sites}).report()
    rooms = {n["name"]: n for n in r["nodes"] if n["kind"] == "room"}
    assert set(rooms) == {"Bedroom (site-3)", "Bedroom (site-4)"}
    assert all(n["room_kind"] == "Bedroom" and n["private"] for n in rooms.values())
    assert r["walks"]["by_room_kind"]["Bedroom"]["rooms"] == 2
    assert r["walks"]["targets_present"]["dining"] == 0

