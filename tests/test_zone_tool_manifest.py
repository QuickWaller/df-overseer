"""Manifest and dispatch checks for the generalised zone tool.

handoffs/2026-09-21-zone-tool-generalise.md. The Lua cannot be executed in the
test suite (it needs a DFHack process), so these tests pin what CAN be checked
offline and has already gone wrong elsewhere in this repo:

1. Every TOOLS.yaml command for `df-overseer-zone.lua` has a matching dispatch
   branch in the Lua file and a defined function, and the other way round (a
   command in one and not the other is a tool nobody can call, or one nobody
   described).
2. The manifest signatures are the Lua CLI's own usage lines, are expressible
   by the MCP server's argument parser, and `[W H]` is skippable only because
   the Lua reads leading numbers by count (the same claim the building tool
   makes, pinned to the same code shape).
3. The rule the handoff exists for: per-kind policy lives in ONE data table
   (`ZONE_POLICY`), not in branches. No kind token appears in the code outside
   that table and the comments, so the next kind costs a table entry.
4. The silent-zero guard: the quickfort table reader fails loud, naming each
   hop, and never returns an empty list.
5. No raw coordinate reaches a result table (design commitment #1), and the
   blueprint is generated in code.
6. The old water-source output keys are still produced.

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
from dfmcp.tools import _arg_specs_for_tool  # noqa: E402

ZONE_LUA = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-zone.lua"

ZONE_IDS = {"zone.list-kinds", "zone.find", "zone.check-owner", "zone.place"}


def _text():
    return ZONE_LUA.read_text(encoding="utf-8")


def _code_without_comments_and_policy():
    """The Lua source with `--` comments, the ROOM_VALUE_EXTERNAL string and
    the ZONE_POLICY table removed: what is left is code that must be
    kind-agnostic."""
    src = _text()
    start = src.index("local ZONE_POLICY = {")
    end = src.index("local function policy_for")
    src = src[:start] + src[end:]
    start = src.index("local ROOM_VALUE_EXTERNAL")
    end = src.index("local function requirements_for")
    src = src[:start] + src[end:]
    return "\n".join(re.sub(r"--.*$", "", line) for line in src.splitlines())


def _dispatch_verbs(lua_text):
    return set(re.findall(r'cmd == "([a-z-]+)"', lua_text))


def test_zone_commands_are_in_the_manifest():
    reg = load_registry()
    for tool_id in ZONE_IDS:
        assert tool_id in reg, f"{tool_id} missing from scripts/dfhack/TOOLS.yaml"


def test_manifest_and_dispatch_agree():
    reg = load_registry()
    manifest = {t.id.split(".", 1)[1] for t in reg.all() if t.script == "df-overseer-zone.lua"}
    assert manifest == {i.split(".", 1)[1] for i in ZONE_IDS}
    assert manifest == _dispatch_verbs(_text())


def test_lua_functions_named_in_the_manifest_exist():
    reg = load_registry()
    src = _text()
    for tool_id in ZONE_IDS:
        tool = reg.get(tool_id)
        assert re.search(rf"function\s+{re.escape(tool.lua_function)}\s*\(", src), (
            f"{tool_id}: lua_function {tool.lua_function!r} not defined in df-overseer-zone.lua"
        )


def test_signatures_are_expressible_by_the_server_parser():
    reg = load_registry()
    for tool_id in ZONE_IDS:
        specs = _arg_specs_for_tool(reg.get(tool_id))
        for spec in specs:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", spec.name), (
                f"{tool_id}: token {spec.raw!r} became property name {spec.name!r}"
            )
        assert len({s.name for s in specs}) == len(specs)


def test_argument_names_and_order():
    reg = load_registry()
    names = lambda i: [s.name for s in _arg_specs_for_tool(reg.get(i))]  # noqa: E731
    assert names("zone.list-kinds") == ["filter"]
    assert names("zone.find") == ["kind", "w", "h", "level", "near_landmark", "radius_tiles"]
    assert names("zone.check-owner") == ["kind", "owner"]
    assert names("zone.place") == [
        "kind", "w", "h", "level", "near_landmark", "rank", "radius_tiles", "dry_run", "owner"]


def test_footprint_is_an_optional_pair_and_owner_is_optional():
    reg = load_registry()
    for tool_id in ("zone.find", "zone.place"):
        tool = reg.get(tool_id)
        assert tool.args[:2] == ["KIND", "[W H]"], tool.args
        by = {s.name: s for s in _arg_specs_for_tool(tool)}
        assert not by["w"].required and not by["h"].required
        assert by["w"].group == by["h"].group == "[W H]"
    by = {s.name: s for s in _arg_specs_for_tool(reg.get("zone.place"))}
    assert not by["owner"].required
    by = {s.name: s for s in _arg_specs_for_tool(reg.get("zone.check-owner"))}
    assert by["owner"].required


def test_manifest_signatures_match_the_lua_usage_lines():
    reg = load_registry()
    usage = _text()
    for tool_id in ZONE_IDS:
        tool = reg.get(tool_id)
        verb = tool_id.split(".", 1)[1]
        line = f"df-overseer-zone {verb}"
        if tool.args:
            line += " " + " ".join(tool.args)
        assert line in usage, tool.command


def test_w_h_is_skippable_because_the_lua_reads_leading_numbers_by_count():
    reg = load_registry()
    for tool_id in ("zone.find", "zone.place"):
        assert reg.get(tool_id).skippable == ("[W H]",)
    src = _text()
    parser = src[src.index("local function parse_site_args"): src.index("local args = {...}")]
    assert "#nums == 1 then level = nums[1]" in parser
    assert "#nums == 2 then w, h = nums[1], nums[2]" in parser
    assert "#nums == 3 then w, h, level" in parser


def test_effects_and_scopes():
    reg = load_registry()
    assert reg.get("zone.list-kinds").effect == "read"
    assert reg.get("zone.find").effect == "read"
    assert reg.get("zone.check-owner").effect == "read"
    assert reg.get("zone.place").effect == "mutate"
    assert reg.get("zone.place").coordinate_bearing == "internal-only"
    for tool_id in ZONE_IDS:
        assert not reg.get(tool_id).is_omniscient
        assert reg.get(tool_id).knowledge_scope in ("player_visible", "player_derivable")


def test_no_kind_token_appears_in_code_outside_the_policy_table():
    """The generalisability rule: the next kind is a data entry, so the code
    may not branch on a kind's name."""
    code = _code_without_comments_and_policy()
    tokens = [
        "Office", "Bedroom", "DiningHall", "MeetingHall", "Dormitory", "Barracks", "Tomb",
        "WaterSource", "water_source", "FishingArea", "SandCollection", "ClayCollection",
        "PlantGathering", "Pen", "Pond", "Dump", "Dungeon", "AnimalTraining", "ArcheryRange",
    ]
    for tok in tokens:
        assert not re.search(rf'["\']{tok}["\']', code), f"kind {tok!r} is named in code, not in ZONE_POLICY"
        assert not re.search(rf"token\s*==\s*", code), "code compares a kind token"


def test_policy_table_is_the_only_special_case():
    src = _text()
    table = src[src.index("local ZONE_POLICY = {"): src.index("local function policy_for")]
    # every policy field used is one DEFAULT_POLICY defines
    default = src[src.index("local DEFAULT_POLICY = {"): src.index("local ZONE_POLICY = {")]
    defined = set(re.findall(r"^\s+([a-z_]+)\s*=", default, flags=re.M))
    used = set(re.findall(r"\b(finder|default_dims|prefer_indoors|owner|position_field|caveat)\s*=", table))
    assert used <= defined, used - defined
    # a room field named in the policy is a real entity_position field
    for field in re.findall(r'position_field = "([a-z_]+)"', table):
        assert field in {"required_office", "required_bedroom", "required_dining", "required_tomb"}
    # owner-capable kinds are exactly the four the preserve-rooms docs name
    owners = set(re.findall(r"^\s+([A-Za-z]+) = \{[^\n]*owner = true", table, flags=re.M))
    assert owners == {"Office", "Bedroom", "DiningHall", "Tomb"}


def test_quickfort_table_reader_fails_loud_not_empty():
    src = _text()
    reader = src[src.index("local function load_quickfort_table"): src.index("local function norm")]
    for hop in ("zone_db", "custom_zone", "parse_zone_config", "zone_db_raw", "do_run"):
        assert hop in reader
    assert reader.count("return nil, ") >= 8
    assert "empty" in reader
    # hops are found by name, never by slot number
    assert "debug.getupvalue(fn, i)" in src and "n == want" in src


def test_blueprint_is_generated_in_code():
    src = _text()
    assert "local function blueprint_text" in src
    assert '"#zone generated by df-overseer-zone"' in src


def test_no_raw_coordinates_in_result_tables():
    """A structural guard for design commitment #1, not proof: the result
    tables must not carry x/y/z fields."""
    src = _text()
    tail = src[src.index("local function rect_site_info"): src.index("-- Same module-load guard")]
    for forbidden in ("x = c.x", "y = c.y", "z = z", "coordinate =", "min_x =", "pos = "):
        for m in re.finditer(re.escape(forbidden), tail):
            line = tail[tail.rfind("\n", 0, m.start()) + 1: tail.find("\n", m.end())]
            # a local variable or a string.format argument is fine; a table field is not
            assert not re.match(r"^\s+(x|y|z|pos|min_x)\s*=", line), f"possible coordinate leak: {line.strip()}"


def test_water_source_keeps_its_old_output_keys():
    src = _text()
    for key in ("depth_min", "depth_max", "stagnant", "salt", "tile_count", "would_zone_tiles",
                "near_landmark", "distance_tiles", "direction", "dry_run"):
        assert key in src, key
    # and its dry run still never touches quickfort
    place_water = src[src.index("local function place_water"): src.index("-- Rectangle kinds: site search")]
    dry_branch = place_water[: place_water.index("-- Real mutation")]
    assert "quickfort" not in dry_branch


def test_owner_refusals_are_named():
    src = _text()
    resolver = src[src.index("local function resolve_owner"): src.index("local function owner_block")]
    for phrase in ("cannot have an owner", "is not alive", "is not a citizen", "no unit with id",
                   "unknown position code", "OWNER must be a unit id"):
        assert phrase in resolver, phrase
