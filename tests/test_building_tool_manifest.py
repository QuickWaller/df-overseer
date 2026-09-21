"""Manifest and dispatch checks for the generic building tool.

handoffs/2026-09-21-building-tool-lua.md. The Lua cannot be executed in the
test suite (it needs a DFHack process), so these tests pin what CAN be checked
offline and has already gone wrong elsewhere in this repo:

1. Every TOOLS.yaml command for `df-overseer-building.lua` and for the new
   `labor enabled-counts` has a matching dispatch branch in the Lua file, and
   every dispatch branch is in the manifest (a command in one and not the
   other is a tool nobody can call, or one nobody described).
2. Each new signature is one the MCP server's argument parser can express.
   `dfmcp/tools.py` reads whitespace-separated tokens and only understands a
   bare PLACEHOLDER or a single `[PLACEHOLDER]`: `[W H]` or `[LABOR...]` would
   become properties named `[w` and `labor...`, and the sweep in
   `dfmcp/tests/test_tools.py` would fail. The Lua CLI is more flexible than
   the manifest on purpose (optional W H for fixed-size kinds, several labors),
   and the manifest notes say so.
3. The Lua files keep the two silent-zero guards: `enabled-counts` reports a
   failed lookup as the null sentinel, never as 0, and the building tool's
   table reader returns an error, not an empty list, when quickfort's layout
   changes.

Placed at top level (`tests/`), not under `dfmcp/tests/`: it reads the Lua
scripts and the manifest, it does not test the server.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfmcp.registry import load_registry  # noqa: E402
from dfmcp.tools import _arg_specs_for_tool  # noqa: E402

BUILDING_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-building.lua"
LABOR_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-labor.lua"

NEW_IDS = {
    "building.list-kinds",
    "building.find",
    "building.build",
    "labor.enabled-counts",
}


def _text(path):
    return path.read_text(encoding="utf-8")


def _dispatch_verbs(lua_text):
    """Verbs handled by `cmd == "..."` branches at the bottom of a script."""
    return set(re.findall(r'cmd == "([a-z-]+)"', lua_text))


def test_new_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in NEW_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_building_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-building.lua"}
    assert manifest == _dispatch_verbs(_text(BUILDING_LUA))


def test_labor_enabled_counts_is_dispatched():
    assert "enabled-counts" in _dispatch_verbs(_text(LABOR_LUA))


def test_lua_functions_named_in_the_manifest_exist():
    reg = load_registry()
    building = _text(BUILDING_LUA)
    labor = _text(LABOR_LUA)
    for tool_id in NEW_IDS:
        tool = reg.get(tool_id)
        src = building if tool.script == "df-overseer-building.lua" else labor
        assert re.search(rf"function\s+{re.escape(tool.lua_function)}\s*\(", src), (
            f"{tool_id}: lua_function {tool.lua_function!r} not defined in {tool.script}"
        )


def test_new_signatures_are_expressible_by_the_server_parser():
    reg = load_registry()
    for tool_id in NEW_IDS:
        tool = reg.get(tool_id)
        specs = _arg_specs_for_tool(tool)
        for spec in specs:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", spec.name), (
                f"{tool_id}: token {spec.raw!r} became property name {spec.name!r}, "
                "which the server cannot express (optional pairs and variadics do not parse)"
            )
        assert len({s.name for s in specs}) == len(specs)


def test_building_find_and_build_take_kind_first_and_site_arguments():
    reg = load_registry()
    find = [s.name for s in _arg_specs_for_tool(reg.get("building.find"))]
    build = [s.name for s in _arg_specs_for_tool(reg.get("building.build"))]
    assert find == ["kind", "w", "h", "level", "near_landmark", "radius_tiles"]
    assert build == ["kind", "w", "h", "level", "near_landmark", "rank", "radius_tiles", "dry_run"]


def test_building_effects_and_scopes():
    reg = load_registry()
    assert reg.get("building.list-kinds").effect == "read"
    assert reg.get("building.find").effect == "read"
    assert reg.get("building.build").effect == "mutate"
    assert reg.get("building.build").coordinate_bearing == "internal-only"
    assert reg.get("labor.enabled-counts").effect == "read"
    for tool_id in NEW_IDS:
        assert not reg.get(tool_id).is_omniscient


def test_enabled_counts_never_reports_a_failed_lookup_as_zero():
    src = _text(LABOR_LUA)
    body = src[src.index("local function labor_code_for"): src.index('if cmd == "unit-status"')]
    # every failure path in the lookup returns nil plus a message
    assert body.count("return nil, ") >= 4
    # and a failed name is stored as the null sentinel, not 0
    assert "counts[name] = NULL" in body
    assert "errors[name] = err" in body


def test_building_table_reader_fails_loud_not_empty():
    src = _text(BUILDING_LUA)
    reader = src[src.index("local function load_quickfort_table"): src.index("-- Game structure only")]
    # each hop that a DFHack update could rename returns an error naming it
    for hop in ("building_db", "building_db_raw", "do_run"):
        assert hop in reader
    assert reader.count("return nil, ") >= 6
    # and an empty table is an error too
    assert "empty" in reader


def test_building_lua_generates_blueprints_not_per_kind_files():
    src = _text(BUILDING_LUA)
    assert "local function blueprint_text" in src
    assert not any(
        p.name.startswith("starter-") and "generic" in p.name
        for p in (REPO_ROOT / "blueprints").glob("*.csv")
    )


def test_building_lua_uses_no_raw_coordinates_in_output_tables():
    """A structural guard for design commitment #1, not proof: the result
    tables built in find_kind/build_kind must not carry x/y/z fields."""
    src = _text(BUILDING_LUA)
    tail = src[src.index("function find_kind"): src.index("-- Same module-load guard")]
    for forbidden in ("x = c.x", "y = c.y", "z = z", "pos =", "coordinate"):
        assert forbidden not in tail, f"possible coordinate leak in result: {forbidden!r}"
