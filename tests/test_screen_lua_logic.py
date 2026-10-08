"""df-overseer-screen.lua, loaded as the REAL script against a tiny fake
DFHack (2026-10-08, an open Work Orders panel blocked a scripted resume).

Proves this project's own logic: the data-driven panel table, blocks_resume
derivation, that text is refused unless a readable panel is open (design
commitment 1: never a rendered map), the prose filter, and that clock.lua
names the blocking panel on resume and status.

Not proved here: that the live game reports these focus strings for every
panel. Only dwarfmode/Default and the Work Orders focus are observed.

Skipped when lupa is not installed (it is not a repo dependency).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "dfhack"
SCREEN_LUA = SCRIPTS / "df-overseer-screen.lua"
CLOCK_LUA = SCRIPTS / "df-overseer-clock.lua"

STUB = r"""
WORLD = { foci = { "dwarfmode/Default" }, rows = {}, paused = true }
function set_focus(list) WORLD.foci = list end
function set_rows(rows) WORLD.rows = rows end
dfhack_flags = { module = true }
json = { encode = function() return "{}" end }
dfhack = {
  gui = {
    getDFViewscreen = function() return { _type = "<type: viewscreen_dwarfmodest>" } end,
    getFocusStrings = function() return WORLD.foci end,
    getCurFocus = function() return WORLD.foci end,
  },
  screen = {
    getWindowSize = function() return 40, 6 end,
    readTile = function(x, y)
      local row = WORLD.rows[y + 1] or ""
      local c = row:sub(x + 1, x + 1)
      return { ch = (c ~= "" and c:byte() or 32) }
    end,
  },
}
"""


@pytest.fixture
def lua():
    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    load = rt.eval("function(src, name) return load(src, name) end")
    load(STUB, "stub")()
    load(SCREEN_LUA.read_text(encoding="utf-8"), "screen.lua")()
    return rt


def py(v):
    if hasattr(v, "items"):
        d = {k: py(x) for k, x in v.items()}
        if d and all(isinstance(k, int) for k in d):
            return [d[k] for k in sorted(d)]
        return d
    return v


def read(lua, foci, rows=None, text=False):
    g = lua.globals()
    g["set_focus"](lua.table_from(foci))
    g["set_rows"](lua.table_from(rows or []))
    return py(g["screen_read"](text))


def test_the_plain_map_blocks_nothing(lua):
    out = read(lua, ["dwarfmode/Default"])
    assert out["ok"] and out["blocks_resume"] is False and out.get("panel") is None


def test_the_work_orders_panel_blocks_resume_and_is_named(lua):
    out = read(lua, ["dwarfmode/Info/WORK_ORDERS/Default"])
    assert out["blocks_resume"] is True
    assert out["blocking"]["focus"] == "dwarfmode/Info/WORK_ORDERS/Default"
    assert out["panel"] == "info_panel"


def test_a_new_info_panel_needs_no_code(lua):
    out = read(lua, ["dwarfmode/Info/LABOR/Default"])
    assert out["blocks_resume"] is True


def test_a_screen_outside_the_play_screen_blocks(lua):
    out = read(lua, ["title/Default"])
    assert out["blocks_resume"] is True and out["blocking"]["name"] == "non_play_screen"


def test_a_view_sheet_does_not_block(lua):
    out = read(lua, ["dwarfmode/ViewSheets/UNIT/Default"])
    assert out["blocks_resume"] is False and out["panel"] == "view_sheet"


def test_text_is_refused_on_the_plain_map_even_when_asked(lua):
    rows = ["##..~~..##  ,,,.  ####", "Some prose looking text here"]
    out = read(lua, ["dwarfmode/Default"], rows=rows, text=True)
    assert "lines" not in out
    assert "map" in out["text_refused"]


def test_text_is_refused_on_an_unclassified_mode(lua):
    out = read(lua, ["dwarfmode/Designate/DIG"], rows=["Designate digging here"], text=True)
    assert "lines" not in out and "text_refused" in out


def test_panel_text_is_returned_and_glyph_noise_dropped(lua):
    rows = [
        "Work orders",
        "#.#.~~..,,..##..::;;",
        "must assign a manager for work orders",
        "",
    ]
    out = read(lua, ["dwarfmode/Info/WORK_ORDERS/Default"], rows=rows, text=True)
    assert "must assign a manager for work orders" in out["lines"]
    assert "Work orders" in out["lines"]
    assert all("~~" not in line for line in out["lines"])


def test_text_is_not_returned_unless_asked(lua):
    out = read(lua, ["dwarfmode/Info/WORK_ORDERS/Default"], rows=["Work orders"], text=False)
    assert "lines" not in out and "text_refused" not in out


def test_blocking_panel_helper_for_the_clock(lua):
    g = lua.globals()
    g["set_focus"](lua.table_from(["dwarfmode/Default"]))
    assert g["blocking_panel"]() is None
    g["set_focus"](lua.table_from(["dwarfmode/Info/WORK_ORDERS/Default"]))
    assert py(g["blocking_panel"]())["focus"] == "dwarfmode/Info/WORK_ORDERS/Default"


def test_the_panel_table_is_data_with_a_verified_note_per_rule(lua):
    rules = py(lua.globals()["PANEL_RULES"])
    assert len(rules) >= 4
    for r in rules:
        assert "verified" in r and "blocks_resume" in r and "text_ok" in r


# ---------------------------------------------------------------------------
# the clock names the panel (clock_resume / clock_status), over the real files


def test_clock_source_resume_and_status_call_the_blocking_panel_helper():
    src = CLOCK_LUA.read_text(encoding="utf-8")
    start = src.index("function clock_resume()")
    body = src[start:src.index("\nend", start)]
    assert "read_blocking_panel()" in body and "blocking_panel" in body
    status = src[src.index("function clock_status()"):]
    assert "blocking_panel = read_blocking_panel()" in status
    # Report only: neither path simulates input or closes anything.
    assert "simulateInput" not in src


def test_the_script_requires_json_before_it_prints():
    """Found live 2026-10-08: `read` died with "attempt to index a nil value
    (global 'json')". The stub above defines a global json, so no test that runs
    the module path can see a missing `require`; assert it on the source."""
    src = SCREEN_LUA.read_text(encoding="utf-8")
    assert "local json = require('json')" in src
    assert src.index("local json = require('json')") < src.index("json.encode(screen_read")
    # and after the module-load guard, which tests rely on to load the file without running it
    assert src.index("dfhack_flags.module") < src.index("local json = require('json')")
