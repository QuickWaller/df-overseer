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

ZONE_IDS = {"zone.list-kinds", "zone.find", "zone.check-owner", "zone.place", "zone.list",
            "zone.assign-owner", "zone.clear-owner", "zone.contents"}


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
    assert names("zone.find") == [
        "kind", "w", "h", "level", "near_landmark", "radius_tiles", "around_furniture"]
    assert names("zone.check-owner") == ["kind", "owner"]
    assert names("zone.place") == [
        "kind", "w", "h", "level", "near_landmark", "rank", "radius_tiles", "dry_run", "owner",
        "around_furniture"]
    assert names("zone.list") == [
        "kind_filter", "owner_filter", "valid_filter", "near_landmark_filter", "radius_tiles"]
    assert names("zone.assign-owner") == ["zone_id", "unit_id", "dry_run", "override"]
    assert names("zone.clear-owner") == ["zone_id", "dry_run"]
    assert names("zone.contents") == ["zone_id"]


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
    assert reg.get("zone.place").skippable == ("[W H]",)
    # zone.find also declares RADIUS_TILES skippable (2026-09-23,
    # handoffs/2026-09-23-zone-inventory-and-validity.md item 3): the CLI
    # tells RADIUS_TILES apart from AROUND_FURNITURE by whether the next
    # word parses as a number, so AROUND_FURNITURE can be given without it.
    assert reg.get("zone.find").skippable == ("[W H]", "[RADIUS_TILES]")
    src = _text()
    parser = src[src.index("local function parse_site_args"): src.index("local args = {...}")]
    assert "#nums == 1 then level = nums[1]" in parser
    assert "#nums == 2 then w, h = nums[1], nums[2]" in parser
    assert "#nums == 3 then w, h, level" in parser
    furniture_parser = src[
        src.index("local function parse_radius_and_furniture"): src.index("local args = {...}")]
    assert "tonumber(args[i]) ~= nil" in furniture_parser


def test_effects_and_scopes():
    reg = load_registry()
    assert reg.get("zone.list-kinds").effect == "read"
    assert reg.get("zone.find").effect == "read"
    assert reg.get("zone.check-owner").effect == "read"
    assert reg.get("zone.place").effect == "mutate"
    assert reg.get("zone.place").coordinate_bearing == "internal-only"
    assert reg.get("zone.list").effect == "read"
    assert reg.get("zone.assign-owner").effect == "mutate"
    assert reg.get("zone.clear-owner").effect == "mutate"
    assert reg.get("zone.contents").effect == "read"
    assert reg.get("zone.contents").coordinate_bearing is False
    assert reg.get("zone.list").coordinate_bearing is False
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


# --------------------------------------------------------------------------
# handoffs/2026-09-23-zone-inventory-and-validity.md: inventory, per-zone
# validity, and AROUND_FURNITURE siting. Same offline, source-level style as
# the tests above -- the Lua cannot run without a live DFHack process.
# --------------------------------------------------------------------------


def test_furniture_kinds_are_only_on_the_owner_capable_room_kinds():
    """Data-driven, not a per-kind branch: furniture_kinds lives in the same
    ZONE_POLICY entries as position_field/owner, and nowhere else names a
    building kind like Chair/Bed/Table/Coffin."""
    src = _text()
    table = src[src.index("local ZONE_POLICY = {"): src.index("local function policy_for")]
    expected = {"Office": "Chair", "Bedroom": "Bed", "DiningHall": "Table", "Tomb": "Coffin"}
    for furniture in expected.values():
        assert f'furniture_kinds = {{"{furniture}"}}' in table, furniture
    # exactly these four kinds carry a furniture_kinds entry, nowhere else
    assert table.count("furniture_kinds = {") == len(expected)
    # not named anywhere else in the code (same discipline as kind tokens)
    code = _code_without_comments_and_policy()
    for building_kind in expected.values():
        assert not re.search(rf'["\']{building_kind}["\']', code), (
            f"building kind {building_kind!r} is named in code, not in ZONE_POLICY"
        )


def test_around_furniture_refuses_a_kind_with_no_furniture_kinds_entry():
    src = _text()
    find_fn = src[src.index("function find_zone_area"): src.index("function check_owner")]
    assert "furniture_type_ids_for" in find_fn
    assert "AROUND_FURNITURE is only meaningful for a kind with furniture_kinds" in find_fn
    # the resolver itself never hardcodes a kind name -- it reads
    # ZONE_POLICY[token].furniture_kinds through df.building_type at call time
    resolver = src[src.index("local function furniture_type_ids_for"): src.index("local function overlaps")]
    assert "df.building_type[token]" in resolver
    for tok in ("Office", "Bedroom", "DiningHall", "Tomb", "Chair", "Bed", "Table", "Coffin"):
        assert f'"{tok}"' not in resolver and f"'{tok}'" not in resolver


def test_place_now_takes_the_same_opt_in_around_furniture_flag_as_find():
    """Fixed live 2026-09-24: place shared ranked_rects with find but was never given
    find's furniture exemption, so it could never choose a site whose tile already held
    the furniture a room needs (e.g. a Tomb zone over an already-built Coffin -- the
    same room-over-furniture pattern this fort's Office/Chair case already showed).
    The flag is opt-in and defaults false, so an ordinary place is unchanged."""
    src = _text()
    place_fn = src[src.index("function place_zone"): src.index("-- zone contents (handoffs")]
    assert "truthy_around_furniture(around_furniture)" in place_fn
    assert "ranked_rects(k, p, dw, dh, level, near, radius_tiles, furniture_ids)" in place_fn
    assert "result.contains_qualifying_furniture" in place_fn
    find_fn = src[src.index("function find_zone_area"): src.index("function check_owner")]
    assert "ranked_rects(k, p, dw, dh, level, near, radius_tiles, furniture_ids)" in find_fn


def test_zone_tile_default_behaviour_is_unchanged_when_furniture_not_requested():
    """Every existing caller (find without AROUND_FURNITURE, and place) still
    passes nil, so an occupied tile is rejected exactly as before."""
    src = _text()
    tile_fn = src[src.index("local function zone_tile"): src.index("-- Returns chosen (list of")]
    assert "if furniture_type_ids then" in tile_fn
    assert "if not matched then" in tile_fn
    assert "stats.occupied = stats.occupied + 1" in tile_fn


def test_list_zones_uses_the_same_three_state_discipline_as_nobles():
    src = _text()
    # kinds_by_type_id through the end of list_zones: the helpers that define
    # the state strings (zone_owner_status/zone_room_value_status) plus
    # list_zones itself, which only ever compares against them by name.
    fn = src[src.index("local function kinds_by_type_id"): src.index("-- DRY_RUN defaults to true. See the header")]
    for status in ("not_applicable", "met", "not_met", "cannot_tell"):
        assert f'"{status}"' in fn, status
    assert "read_failures" in fn
    # owner_status is reported separately from room_value_status, never
    # collapsed into one field (handoff: "distinct from an invalid room value")
    assert "owner_status" in fn and "room_value_status" in fn


def test_list_zones_identity_is_the_zone_id_never_a_coordinate():
    src = _text()
    fn = src[src.index("function list_zones"): src.index("-- DRY_RUN defaults to true. See the header")]
    assert "id = z.id" in fn
    # centroid coordinates (z.x1/x2/y1/y2/z) are read only as transient
    # locals to compute a distance/landmark lookup, same as ranked_rects
    # elsewhere in this file -- never assigned to a `row.` field or a
    # `x =`/`y =`/`z =` table key (the discipline
    # test_no_raw_coordinates_in_result_tables pins for the site-search
    # functions).
    for line in fn.splitlines():
        assert not re.match(r"^\s*row\.(x|y|z|pos)\s*=", line), f"coordinate leak: {line.strip()}"
        assert not re.match(r"^\s*(x|y|z|pos)\s*=\s*z\.(x1|x2|y1|y2|z)\b", line), (
            f"possible coordinate leak: {line.strip()}"
        )


def test_list_summarises_by_default_and_details_on_filter():
    src = _text()
    fn = src[src.index("function list_zones"): src.index("-- DRY_RUN defaults to true. See the header")]
    assert "any_filter" in fn
    assert "result.summary = true" in fn
    assert "result.summary = false" in fn
    assert "needs_attention" in fn
    assert "MAX_LIST" in fn  # bounded detail, same cap used elsewhere in this file


def test_list_is_one_bounded_pass_never_a_tile_scan():
    src = _text()
    fn = src[src.index("function list_zones"): src.index("-- DRY_RUN defaults to true. See the header")]
    assert "ACTIVITY_ZONE" in fn
    assert "MAX_ZONE_SCAN" in fn
    # no tile-level call anywhere in the inventory path
    for tile_call in ("isTileVisible", "getTileFlags", "getWalkableGroup", "xyz2pos"):
        assert tile_call not in fn, f"list_zones appears to scan tiles ({tile_call})"


def test_owner_and_valid_filters_use_the_empty_string_sentinel():
    """Same convention check-owner's OWNER already established: '' means
    'no filter', not an error."""
    src = _text()
    owner_resolver = src[
        src.index("local function resolve_owner_filter"): src.index("local function owner_filter_matches")]
    assert 's == nil or s == ""' in owner_resolver
    valid_resolver = src[
        src.index("local function resolve_valid_filter"): src.index("function list_zones")]
    assert 's == nil or s == ""' in valid_resolver


# --------------------------------------------------------------------------
# handoffs/2026-09-24-furniture-aware-ranking.md: a furniture-containing
# site must outrank a furniture-free one for AROUND_FURNITURE, and a plain
# find's ranking must be untouched. Same offline, source-level style: the
# Lua cannot run without a live DFHack process.
# --------------------------------------------------------------------------


def _ranked_rects_body():
    src = _text()
    return src[src.index("local function ranked_rects"): src.index("local function rect_site_info")]


def test_furniture_sorts_before_distance_and_indoors():
    """The has_furniture split must run BEFORE the existing prefer_indoors/
    distance comparison, and only when furniture_type_ids is truthy, so a
    plain find (furniture_type_ids == nil) never takes this branch."""
    body = _ranked_rects_body()
    sort_call = body[body.index("table.sort(candidates"):]
    furniture_line = "if furniture_type_ids and a.has_furniture ~= b.has_furniture then return a.has_furniture end"
    indoors_line = "if p.prefer_indoors and a.indoors ~= b.indoors then return a.indoors end"
    assert furniture_line in sort_call
    assert indoors_line in sort_call
    assert sort_call.index(furniture_line) < sort_call.index(indoors_line), (
        "furniture must be sorted ahead of the indoor/distance tiebreak, not after it"
    )


def test_has_furniture_is_computed_from_the_same_furniture_ids_as_the_row_flag():
    """has_furniture must track furniture_building_ids exactly (non-nil and
    non-empty), the same test the per-row contains_qualifying_furniture flag
    applies in rect_site_info, so the two never disagree."""
    body = _ranked_rects_body()
    assert "has_furniture = furniture_ids ~= nil and #furniture_ids > 0" in body


def test_default_ranking_is_unchanged_without_around_furniture():
    """A plain find or place (AROUND_FURNITURE omitted or false) both call
    ranked_rects with furniture_type_ids nil (both now share the identical
    call, test_place_now_takes_the_same_opt_in_around_furniture_flag_as_find
    pins the call sites); this pins that the sort comparator itself is a
    no-op for that case: the furniture branch is gated on furniture_type_ids,
    and no other line in the comparator was touched by this change."""
    body = _ranked_rects_body()
    sort_call = body[body.index("table.sort(candidates"): body.index("local chosen = {}")]
    # exactly the three comparator lines: furniture guard, indoors, distance
    assert sort_call.count("return a.has_furniture") == 1
    assert sort_call.count("return a.indoors") == 1
    assert sort_call.count("return a.dist < b.dist") == 1


def test_overlap_filter_runs_after_the_furniture_sort():
    """Item 2: confirms from the code that the greedy overlap dedup (which
    eliminates any candidate overlapping an already-chosen one, stopping at
    MAX_RESULTS) runs AFTER candidates are sorted, so sorting
    furniture-containing sites first is what keeps one of them from being
    overlapped away -- the mechanism the brief traced before dispatch."""
    body = _ranked_rects_body()
    sort_at = body.index("table.sort(candidates")
    overlap_at = body.index("if overlaps(c, e, w, h) then ok = false")
    assert sort_at < overlap_at


def test_find_wraps_output_only_when_furniture_requested():
    """A plain find (furniture_requested false) must keep returning the bare
    `results` array unchanged; only AROUND_FURNITURE gets the new
    {results, any_contains_furniture, furniture_note} wrapper, so existing
    callers see byte-for-byte identical shape and ranking."""
    src = _text()
    find_fn = src[src.index("function find_zone_area"): src.index("function check_owner")]
    assert "return results\nend" in find_fn
    assert "if furniture_requested then" in find_fn
    assert "any_contains_furniture = any_furniture" in find_fn
    assert "wrapped.furniture_note" in find_fn
    # the wrap happens strictly inside the furniture_requested branch, after
    # the plain `return results` fallback is still reachable for the
    # non-furniture path
    wrap_block = find_fn[find_fn.index("if furniture_requested then\n    local wrapped"):]
    assert "return wrapped" in wrap_block


def test_furniture_note_only_appears_when_no_candidate_has_furniture():
    src = _text()
    find_fn = src[src.index("function find_zone_area"): src.index("function check_owner")]
    note_block = find_fn[find_fn.index("if not any_furniture then"): find_fn.index("return wrapped")]
    assert "furniture_note" in note_block
    assert "none of the" in note_block


def test_zone_list_room_value_status_never_reads_an_empty_description_as_not_met():
    """Register 2026-09-24: an empty getRoomDescription on an owned office was a false
    negative (the game accepted the room). zone list's room_value_status must not map
    empty to not_met by itself; it needs the independent evidence zone_furniture_report
    gives. A source-level guard (list_zones needs a zone-vector stub the harness lacks),
    so it proves the mapping was removed and the helper is consulted, not the runtime
    behaviour, which is the live check in handoffs/2026-09-24-room-proxy-fix.md."""
    src = ZONE_LUA.read_text(encoding="utf-8")
    start = src.index("local function zone_room_value_status")
    fn = src[start: src.index("\nend\n", start)]
    assert 'if desc == "" then return "not_met" end' not in fn
    assert "zone_furniture_report" in fn
    assert 'return "cannot_tell"' in fn
