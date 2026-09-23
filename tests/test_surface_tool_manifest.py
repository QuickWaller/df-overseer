"""Manifest and dispatch checks for the surface perception tool.

handoffs/2026-09-24-surface-perception.md. The Lua cannot be executed in the
test suite (it needs a DFHack process), so these tests pin what CAN be
checked offline and mirrors tests/test_zone_tool_manifest.py's own shape for
the same reason that file gives: a command in TOOLS.yaml with no matching
Lua dispatch branch (or the other way round) is a tool nobody can call, or
one nobody described.

1. Every TOOLS.yaml command for `df-overseer-surface.lua` has a matching
   dispatch branch in the Lua file and a defined function, and vice versa.
2. The manifest signature (ZONE_ID, required, integer) is expressible by the
   MCP server's argument parser.
3. effect/knowledge_scope: every command is read, never omniscient (this
   tool reads only revealed tiles -- the ACT/SENSE rule the .lua file's own
   header describes).
4. No raw coordinate reaches a result table (design commitment #1): the
   result-building code never assigns an x/y/z/pos field.
5. The three read-only advisor/arbitration roles (architect, overseer,
   consultant) are granted all four commands; a role with no spatial
   remit (quartermaster) and the system-kind conductor are not.

Placed at top level (`tests/`), not under `dfmcp/tests/`: it reads the Lua
script and the manifest, it does not test the server.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfmcp.registry import load_registry  # noqa: E402
from dfmcp.roles import load_roster  # noqa: E402
from dfmcp.tools import _arg_specs_for_tool  # noqa: E402
from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS  # noqa: E402
from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS  # noqa: E402
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS  # noqa: E402
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS  # noqa: E402
from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS  # noqa: E402

SURFACE_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-surface.lua"

SURFACE_IDS = {"surface.enclosure", "surface.finish", "surface.material", "surface.traffic"}


def _text():
    return SURFACE_LUA.read_text(encoding="utf-8")


def _dispatch_verbs(lua_text):
    return set(re.findall(r'cmd == "([a-z-]+)"', lua_text))


def _all_native_tools():
    return {
        **QUEUE_NATIVE_TOOLS,
        **DOCTRINE_NATIVE_TOOLS,
        **SERIES_NATIVE_TOOLS,
        **GOTCHAS_NATIVE_TOOLS,
        **KNOWLEDGE_NATIVE_TOOLS,
    }


def test_surface_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in SURFACE_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-surface.lua"}
    assert manifest == {i.split(".", 1)[1] for i in SURFACE_IDS}
    assert manifest == _dispatch_verbs(_text())


def test_lua_functions_named_in_the_manifest_exist():
    reg = load_registry()
    src = _text()
    for tool_id in SURFACE_IDS:
        tool = reg.get(tool_id)
        assert re.search(rf"function\s+{re.escape(tool.lua_function)}\s*\(", src), (
            f"{tool_id}: lua_function {tool.lua_function!r} not defined in df-overseer-surface.lua"
        )


def test_signature_is_one_required_integer_zone_id():
    reg = load_registry()
    for tool_id in SURFACE_IDS:
        tool = reg.get(tool_id)
        assert tool.args == ["ZONE_ID"], (tool_id, tool.args)
        specs = _arg_specs_for_tool(tool)
        assert len(specs) == 1
        spec = specs[0]
        assert spec.name == "zone_id"
        assert spec.required is True
        assert spec.json_type == "integer"
        assert spec.description, "ZONE_ID must carry an argument description"


def test_manifest_signatures_match_the_lua_usage_lines():
    reg = load_registry()
    usage = _text()
    for tool_id in SURFACE_IDS:
        tool = reg.get(tool_id)
        verb = tool_id.split(".", 1)[1]
        line = f"df-overseer-surface {verb}"
        if tool.args:
            line += " " + " ".join(tool.args)
        assert line in usage, tool.command


def test_effects_and_knowledge_scopes():
    reg = load_registry()
    for tool_id in SURFACE_IDS:
        tool = reg.get(tool_id)
        assert tool.effect == "read", tool_id
        assert not tool.mutates, tool_id
        assert not tool.is_omniscient, tool_id
        assert tool.coordinate_bearing is False, tool_id
    # enclosure/finish/material derive a computed answer over revealed tiles
    # (the same structural guard diggable.find's player_derivable tag rests
    # on); traffic reads a real designation off a real screen a player set
    # themselves, so it is directly player_visible, not derived.
    assert reg.get("surface.enclosure").knowledge_scope == "player_derivable"
    assert reg.get("surface.finish").knowledge_scope == "player_derivable"
    assert reg.get("surface.material").knowledge_scope == "player_derivable"
    assert reg.get("surface.traffic").knowledge_scope == "player_visible"


def test_no_raw_coordinates_in_result_tables():
    """A structural guard for design commitment #1, not proof: the four
    verb functions' own result tables must not carry x/y/z/pos fields.
    Scoped to the four `function NAME(zone_id) ... end` bodies, not the
    whole file (the per-tile helpers legitimately hold x/y/z locals to do
    the reads; they never appear inside a `{ ... }` result table)."""
    src = _text()
    for fn in ("enclosure", "finish", "boundary_material", "traffic"):
        start = src.index(f"\nfunction {fn}(")
        end = src.index("\nend", start)
        body = src[start:end]
        for forbidden in (" x = ", " y = ", " z = ", "pos = ", "coordinate ="):
            for m in re.finditer(re.escape(forbidden), body):
                line = body[body.rfind("\n", 0, m.start()) + 1: body.find("\n", m.end())]
                assert not re.match(r"^\s+(x|y|z|pos)\s*=", line), (
                    f"{fn}: possible coordinate leak: {line.strip()}"
                )


def test_ring_and_footprint_helpers_are_bounded():
    """MAX_FOOTPRINT_TILES/MAX_RING_TILES exist and every verb that walks a
    zone's tiles checks against them before iterating -- 'never scan the
    map' as a structural property, not just a comment."""
    src = _text()
    assert "local MAX_FOOTPRINT_TILES = " in src
    assert "local MAX_RING_TILES = " in src
    for fn in ("enclosure", "finish", "boundary_material", "traffic"):
        start = src.index(f"\nfunction {fn}(")
        end = src.index("\nend", start)
        body = src[start:end]
        assert "MAX_FOOTPRINT_TILES" in body or "MAX_RING_TILES" in body, (
            f"{fn}: no bound check found in its own body"
        )


def test_granted_to_the_three_spatial_read_roles():
    reg = load_registry(native_tools=_all_native_tools())
    roster = load_roster(reg)
    for role in ("architect", "overseer", "consultant"):
        for tool_id in SURFACE_IDS:
            allowed, reason = roster.check(role, tool_id)
            assert allowed, f"{role} should be granted {tool_id}: {reason}"


def test_not_granted_to_non_spatial_or_system_roles():
    reg = load_registry(native_tools=_all_native_tools())
    roster = load_roster(reg)
    for role in ("quartermaster", "conductor"):
        for tool_id in SURFACE_IDS:
            allowed, _reason = roster.check(role, tool_id)
            assert not allowed, f"{role} should not be granted {tool_id}"
