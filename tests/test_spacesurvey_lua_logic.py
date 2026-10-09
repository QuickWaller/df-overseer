"""Runs the REAL scripts/dfhack/df-overseer-spacesurvey.lua (read-only unused
dug space survey behind openarea.survey) against small fake maps, using lupa.

Proves the pure logic: regions are connected unclaimed open floor, claimed
tiles (zones, stockpiles, buildings, reservations) split or remove regions,
width-1 corridors are not regions but are reported as touched, the minimum
size filter and result cap, rectangularity and tiles-to-square, level offset
to the nearest landmark, a stable coordinate-free id, and the hard window cap
that refuses rather than truncates. It proves nothing about real DFHack tile
reads (the live check owed).

Skipped when lupa is not installed (it is not a repo dependency).
"""

import re
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

REPO_ROOT = Path(__file__).resolve().parent.parent
LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-spacesurvey.lua"

PRELUDE = """
dfhack_flags = { module = true }
dfhack = {}
df = {}
function make_world(layers, landmarks)
  -- layers: {[z] = {rows}}; '.' open, 'o' claimed, 'c' corridor reservation,
  -- '#' solid. A box is the whole layer.
  local boxes = {}
  for z, rows in pairs(layers) do
    boxes[#boxes + 1] = { z = z, x1 = 0, y1 = 0, x2 = #rows[1] - 1, y2 = #rows - 1 }
  end
  local w = { boxes = boxes, landmarks = landmarks }
  w.tile = function(x, y, z)
    local rows = layers[z]
    local row = rows and rows[y + 1]
    local ch = row and row:sub(x + 1, x + 1)
    if ch == '.' then return "open" end
    if ch == 'o' then return "claimed" end
    if ch == 'c' then return "corridor" end
    return nil
  end
  return w
end
"""


def _py(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    keys = list(v.keys())
    if not keys:
        return []
    if all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
        return [_py(v[k]) for k in sorted(keys)]
    return {str(k): _py(v[k]) for k in keys}


def _lit(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return "[==[" + v + "]==]"
    if isinstance(v, dict):
        return "{" + ",".join("[ %s ] = %s" % (_lit(k), _lit(x)) for k, x in v.items()) + "}"
    return "{" + ",".join(_lit(x) for x in v) + "}"


class Survey:
    def __init__(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(PRELUDE)
        load = self.lua.eval("function(src, name) return load(src, name) end")
        chunk = load(LUA.read_text(encoding="utf-8"), "spacesurvey.lua")
        assert not isinstance(chunk, tuple), chunk
        chunk()

    def run(self, layers, landmarks=(), **opts):
        self.lua.execute("WORLD = make_world(%s, %s)" % (_lit(layers), _lit(list(landmarks))))
        self.lua.execute("RESULT, ERR = survey(WORLD, %s)" % _lit(opts))
        g = self.lua.globals()
        return _py(g.RESULT), g.ERR


LM = [{"name": "Well", "x": 0, "y": 0, "z": 5}]


def test_open_block_is_one_region_with_numbers():
    s = Survey()
    r, err = s.run({5: ["######", "#....#", "#....#", "#....#", "######"]}, LM)
    assert err is None
    assert r["found"] == 1
    reg = r["regions"][0]
    assert reg["tiles"] == 12
    assert reg["bbox"] == {"w": 4, "h": 3}
    assert reg["rectangularity"] == 1.0
    assert reg["tiles_to_square"] == 0
    assert reg["level_vs_nearest_landmark"] == 0
    assert reg["nearest_landmarks"][0]["name"] == "Well"
    assert re.fullmatch(r"region-[0-9a-f]{6}", reg["id"])


def test_l_shape_rectangularity_and_square_off():
    s = Survey()
    r, _ = s.run({5: ["#######", "#.....#", "#.....#", "#..####", "#..####", "#######"]}, LM, min_tiles=4)
    reg = r["regions"][0]
    assert reg["tiles"] == 14
    assert reg["bbox"] == {"w": 5, "h": 4}
    assert reg["tiles_to_square"] == 6
    assert reg["rectangularity"] == 0.7


def test_claimed_tiles_are_excluded_and_split():
    s = Survey()
    rows = ["#########", "#...o...#", "#...o...#", "#...o...#", "#########"]
    r, _ = s.run({5: rows}, LM, min_tiles=4)
    assert r["found"] == 2
    assert sorted(x["tiles"] for x in r["regions"]) == [9, 9]


def test_corridor_not_a_region_but_touched():
    s = Survey()
    # A 4x3 room (rows 1-3) with a one-wide corridor leaving along row 3.
    rows = ["##########", "#....#####", "#....#####", "#.........", "##########"]
    r, _ = s.run({5: rows}, LM, min_tiles=4)
    assert r["found"] == 1
    reg = r["regions"][0]
    assert reg["tiles"] == 12
    assert reg["touches_corridor"] is True


def test_corridor_reservation_touch_and_min_filter():
    s = Survey()
    rows = ["######", "#..c##", "#..###", "######"]
    r, _ = s.run({5: rows}, LM, min_tiles=4)
    assert r["found"] == 1 and r["regions"][0]["touches_corridor"] is True
    r, _ = s.run({5: rows}, LM, min_tiles=5)
    assert r["found"] == 0


def test_isolated_room_does_not_touch_corridor():
    s = Survey()
    r, _ = s.run({5: ["####", "#..#", "#..#", "####"]}, LM, min_tiles=4)
    assert r["regions"][0]["touches_corridor"] is False


def test_level_offset_and_nearest_order():
    s = Survey()
    lms = [{"name": "Far", "x": 90, "y": 90, "z": 5}, {"name": "Near", "x": 2, "y": 2, "z": 7}]
    r, _ = s.run({5: ["####", "#..#", "#..#", "####"]}, lms, min_tiles=4)
    reg = r["regions"][0]
    assert [n["name"] for n in reg["nearest_landmarks"]] == ["Near", "Far"]
    assert reg["level_vs_nearest_landmark"] == -2


def test_result_cap_orders_by_size_times_squareness():
    s = Survey()
    rows = ["###############", "#...#..#.....##", "#...#..#.....##", "#...#..#.....##", "###############"]
    r, _ = s.run({5: rows}, LM, min_tiles=4, max_results=2)
    assert r["found"] == 3 and r["shown"] == 2
    assert [x["tiles"] for x in r["regions"]] == [15, 9]


def test_cap_refuses_instead_of_truncating():
    s = Survey()
    r, err = s.run({5: ["....", "...."]}, LM, cap=4)
    assert r is None and "refusing" in err


def test_id_is_stable_and_report_has_no_coordinates():
    s = Survey()
    layers = {5: ["####", "#..#", "#..#", "####"]}
    a, _ = s.run(layers, LM, min_tiles=4)
    b, _ = s.run(layers, LM, min_tiles=4)
    assert a["regions"][0]["id"] == b["regions"][0]["id"]
    flat = repr(a)
    for banned in ("'x'", "'y'", "'z'", "grid"):
        assert banned not in flat


def test_make_boxes_pads_and_merges_per_level():
    s = Survey()
    s.lua.execute(
        "BOXES = make_boxes({{x1=20,y1=20,x2=22,y2=22,z=1},{x1=25,y1=20,x2=27,y2=22,z=1},"
        "{x1=20,y1=20,x2=22,y2=22,z=2}}, 2, 1)"
    )
    boxes = _py(s.lua.globals().BOXES)
    assert [b["z"] for b in boxes] == [1, 2]
    assert boxes[0]["x1"] == 18 and boxes[0]["x2"] == 29


def test_source_declares_module_and_does_not_use_json():
    src = LUA.read_text(encoding="utf-8")
    assert src.splitlines()[1].strip() == "--@module = true"
    assert "json." not in "\n".join(l for l in src.splitlines() if not l.strip().startswith("--"))
