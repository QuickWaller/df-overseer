"""Tests for mcp/tools.py: MCP tool names, tool definitions, and argv
construction.

Two things matter most here, per the task brief:

1. `test_the_overseer_can_act_but_cannot_discover_via_mcp_names` -- the
   Overseer/Architect asymmetry (docs/AGENT-ARCHITECTURE.md §5) must survive
   translation into MCP tool names, not just canonical ids. mcp/tests/
   test_roles.py already pins the underlying Roster fact; this file pins
   that tool_definitions() actually reflects it.
2. The `argv_for_call` positional-optional gap tests -- this is the one real
   trap the task brief calls out, and the failure mode (silently shifting an
   argument into the wrong slot) is the exact class of bug this project has
   already shipped twice (the quickfort top-left-vs-centre bug,
   decisions/DECISIONS.md 2026-09-11).

Ground truth for which argument names are integer-valued was read from each
owning .lua script's dispatch code, not guessed from the name. File:line
references (as of this stream, 2026-09-12; LEVEL/its line numbers updated
2026-09-14 when Z became LEVEL, handoffs/2026-09-14-relative-level-args.md):

  W, H            scripts/dfhack/df-overseer-openarea.lua:365 (tonumber(args[2]), tonumber(args[3]))
  LEVEL           scripts/dfhack/df-overseer-openarea.lua:367 (tonumber(args[4]) sniff; was Z until 2026-09-14)
  RANK, RADIUS_TILES  scripts/dfhack/df-overseer-openarea.lua:383 (tonumber(args[7]), tonumber(args[8]))
  UNIT_ID         scripts/dfhack/df-overseer-connectivity.lua:152 (check-units); df-overseer-labor.lua find_citizen (tonumber(id_str))
  REPORT_ID       scripts/dfhack/df-overseer-diff.lua since_report (tonumber(id_str))
  CURSOR          scripts/dfhack/df-overseer-diff.lua:298 (tonumber(args[2]))
  N               scripts/dfhack/df-overseer-diff.lua recent_combat (n = tonumber(n) or 20)
  MIN_IDLE_TICKS  scripts/dfhack/df-overseer-stuckjobs.lua:111 (tonumber(args[2]))

FROM/TO (connectivity.check) were confirmed as strings, not integers, by the
*absence* of tonumber in df-overseer-connectivity.lua's "check" branch
(landmark names), contrasted with "check-units" right next to it, which does
call tonumber -- see df-overseer-connectivity.lua:142-157.
"""

import textwrap

import pytest

from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS
from dfmcp.registry import RegistryError, load_registry
from dfmcp.roles import load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS
from dfmcp.tools import (
    ArgumentError,
    ToolSchemaError,
    _arg_specs_for_tool,
    argv_for_call,
    build_tool_names,
    tool_definitions,
)


@pytest.fixture(scope="module")
def registry():
    # native_tools=NATIVE_TOOLS: the real roster now grants queue.* ids
    # (handoffs/2026-09-15-queue-into-dfmcp.md); see test_roles.py's
    # registry fixture for the full explanation. NativeTool.args = () keeps
    # test_sweep_every_real_argument_token_is_confidently_typed below happy:
    # it iterates registry.all() generically and expects every tool to have
    # an .args to sweep, even if (as here) there is nothing in it.
    # DOCTRINE_NATIVE_TOOLS merged in too, added
    # handoffs/2026-09-19-get-doctrine-tool.md: agents/consultant/tools.yaml
    # now grants doctrine.get, same rule-1 requirement, and
    # dfmcp.doctrine_tools.NativeTool.args is likewise () for the same reason.
    # SERIES_NATIVE_TOOLS merged in too, added
    # handoffs/2026-09-19-series-mcp-tools.md: agents/overseer/tools.yaml and
    # agents/consultant/tools.yaml now grant series.* ids, same rule-1
    # requirement, and dfmcp.series_tools.NativeTool.args is likewise ().
    return load_registry(native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS})


@pytest.fixture(scope="module")
def roster(registry):
    return load_roster(registry)


# --------------------------------------------------------------------------
# Tool names
# --------------------------------------------------------------------------


def test_every_real_id_gets_an_mcp_legal_reversible_name(registry):
    """Verified against the real manifest, not assumed: every one of the
    (as of writing) 27 ids round-trips through both dicts."""
    id_to_name, name_to_id = build_tool_names(registry)
    ids = registry.ids()
    assert len(ids) >= 25  # the count this stream's handoff cites; not brittle to +1
    assert set(id_to_name) == set(ids)
    assert len(name_to_id) == len(id_to_name), "a name collision would shrink this dict"
    for tool_id in ids:
        name = id_to_name[tool_id]
        assert name, tool_id
        assert all(c.isalnum() or c in "_-" for c in name), (tool_id, name)
        assert 1 <= len(name) <= 128
        assert name_to_id[name] == tool_id, "reverse lookup must be exact, not derived"


def test_dot_becomes_double_underscore(registry):
    id_to_name, _ = build_tool_names(registry)
    assert id_to_name["openarea.build"] == "openarea__build"
    assert id_to_name["labor.set-labor"] == "labor__set-labor"


def _write_tools_yaml(tmp_path, body):
    path = tmp_path / "TOOLS.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_name_collision_raises(tmp_path):
    """Two different ids that happen to produce the same name after the
    dot -> "__" transform must refuse to build, not silently alias."""
    path = _write_tools_yaml(
        tmp_path,
        """
        df-overseer-a__b.lua:
          commands:
            "c D":
              lua_function: f1
              effect: read
              knowledge_scope: player_visible
        df-overseer-a.lua:
          commands:
            "b__c D":
              lua_function: f2
              effect: read
              knowledge_scope: player_visible
        """,
    )
    reg = load_registry(path)
    # Both ids exist distinctly in the registry; the collision is only in
    # the derived MCP *name*, which is exactly what this module must catch.
    assert "a__b.c" in reg
    assert "a.b__c" in reg
    with pytest.raises(ToolSchemaError) as exc:
        build_tool_names(reg)
    assert "a__b__c" in str(exc.value)


# --------------------------------------------------------------------------
# Argument specs: the documented type/name heuristic
# --------------------------------------------------------------------------


def test_integer_args_by_name(registry):
    build = registry.get("openarea.build")
    specs = {s.name: s for s in _arg_specs_for_tool(build)}
    assert specs["w"].json_type == "integer" and specs["w"].required
    assert specs["h"].json_type == "integer" and specs["h"].required
    assert specs["level"].json_type == "integer" and not specs["level"].required
    assert specs["rank"].json_type == "integer" and not specs["rank"].required
    assert specs["radius_tiles"].json_type == "integer" and not specs["radius_tiles"].required
    assert specs["near_landmark"].json_type == "string" and specs["near_landmark"].required
    assert specs["blueprint_file"].json_type == "string" and specs["blueprint_file"].required


def test_connectivity_check_uses_string_from_to_not_integer(registry):
    """FROM/TO are landmark names (strings), confirmed by the absence of
    tonumber in the "check" branch -- contrast with check-units below."""
    check = registry.get("connectivity.check")
    specs = {s.name: s for s in _arg_specs_for_tool(check)}
    assert specs["from"].json_type == "string"
    assert specs["to"].json_type == "string"


def test_repeated_argument_name_gets_disambiguated(registry):
    """connectivity.check-units has two positional args both literally named
    UNIT_ID in the manifest. Both must survive as distinct, integer-typed
    schema properties."""
    check_units = registry.get("connectivity.check-units")
    specs = _arg_specs_for_tool(check_units)
    names = [s.name for s in specs]
    assert names == ["unit_id_1", "unit_id_2"]
    assert all(s.json_type == "integer" and s.required for s in specs)


def test_literal_choice_tokens_become_enums(registry):
    set_labor = registry.get("labor.set-labor")
    specs = {s.name: s for s in _arg_specs_for_tool(set_labor)}
    assert specs["unit_id"].json_type == "integer"
    assert specs["labor_name"].json_type == "string"
    on_off = specs["on_off"]
    assert on_off.required is True
    assert on_off.json_type == "string"
    assert on_off.enum == ("on", "off")

    unit_status = registry.get("labor.unit-status")
    (filt,) = _arg_specs_for_tool(unit_status)
    assert filt.name == "idle_injured_military_hostile"
    assert filt.required is False
    assert filt.enum == ("idle", "injured", "military", "hostile")


def test_sweep_every_real_argument_token_is_confidently_typed(registry):
    """Every argument token in the real, current manifest is either a plain
    UPPER_CASE placeholder (typed via _INTEGER_ARG_NAMES or defaulted to
    string) or one of the two known literal-choice tokens. If a future
    manifest edit adds a token shaped some third way, this test should be
    the thing that notices."""
    from dfmcp.tools import _BRACKET_RE

    for tool in registry.all():
        for token in tool.args:
            inner = token
            m = _BRACKET_RE.match(token)
            if m:
                inner = m.group(1)
            assert inner, f"{tool.id}: empty argument token {token!r}"
            is_plain_placeholder = all(c.isalnum() or c == "_" for c in inner) and inner[0].isalpha()
            is_literal_choice = "|" in inner
            assert is_plain_placeholder or is_literal_choice, (
                f"{tool.id}: argument token {token!r} is neither a plain UPPER_CASE "
                "placeholder nor a literal-choice token -- the heuristic table does "
                "not confidently cover this, see mcp/tools.py's module docstring"
            )


def test_chokepoints_level_is_optional_integer(registry):
    """chokepoints.find's Z argument was REQUIRED (no default at all) until
    2026-09-14 (handoffs/2026-09-14-relative-level-args.md) -- the one
    command among the three this stream touched where a caller had no
    coordinate-free way to call it at all. LEVEL keeps the same position
    (first argument) but is now optional, matching openarea.find/
    diggable.find."""
    find = registry.get("chokepoints.find")
    (level,) = [s for s in _arg_specs_for_tool(find) if s.name == "level"]
    assert level.json_type == "integer"
    assert level.required is False


# --------------------------------------------------------------------------
# Argument descriptions
# --------------------------------------------------------------------------


def test_level_description_states_relative_meaning_and_never_a_coordinate(registry):
    """The gap this stream closed: the schema used to give the model an
    argument named z with no description at all, so nothing told a caller
    it was an absolute DF map coordinate rather than something small and
    relative. LEVEL's description must say what 0/-1/1 mean and must say
    plainly it is not a coordinate."""
    build = registry.get("openarea.build")
    (level,) = [s for s in _arg_specs_for_tool(build) if s.name == "level"]
    assert level.description is not None
    text = level.description.lower()
    assert "relative" in text
    assert "not" in text and "coordinate" in text
    assert "-1" in level.description and "1" in level.description


def test_near_landmark_description_says_never_a_coordinate(registry):
    build = registry.get("openarea.build")
    (near_landmark,) = [s for s in _arg_specs_for_tool(build) if s.name == "near_landmark"]
    assert near_landmark.description is not None
    assert "coordinate" in near_landmark.description.lower()


def test_documented_argument_tokens_all_have_descriptions(registry):
    """Every token the task brief named explicitly (LEVEL, NEAR_LANDMARK,
    RADIUS_TILES, W, H, RANK, BLUEPRINT_FILE) must carry a description on
    every tool that uses it, not just openarea.build."""
    build = registry.get("openarea.build")
    specs = {s.name: s for s in _arg_specs_for_tool(build)}
    for name in ("level", "near_landmark", "radius_tiles", "w", "h", "rank", "blueprint_file"):
        assert specs[name].description, f"{name!r} has no description"


def test_input_schema_carries_description_when_present(registry, roster):
    defs = {d["name"]: d for d in tool_definitions(registry, roster, "overseer")}
    props = defs["openarea__build"]["inputSchema"]["properties"]
    assert "description" in props["level"]
    assert "description" in props["near_landmark"]
    assert "description" in props["blueprint_file"]


def test_input_schema_omits_description_key_when_none_documented(registry, roster):
    """An argument token this stream did not add a description for (e.g.
    UNIT_ID) must not get a synthesised or empty description -- the same
    honest-gap default _INTEGER_ARG_NAMES uses for type."""
    defs = {d["name"]: d for d in tool_definitions(registry, roster, "overseer")}
    props = defs["labor__set-labor"]["inputSchema"]["properties"]
    assert "description" not in props["unit_id"]


# --------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------


def test_the_overseer_can_act_but_cannot_discover_via_mcp_names(registry, roster):
    """The same structural property mcp/tests/test_roles.py pins at the
    Roster level, re-pinned here at the MCP-name level actually returned to
    a client. docs/AGENT-ARCHITECTURE.md §5."""
    overseer_names = {d["name"] for d in tool_definitions(registry, roster, "overseer")}
    architect_names = {d["name"] for d in tool_definitions(registry, roster, "architect")}

    assert "openarea__build" in overseer_names
    assert "diggable__dig" in overseer_names
    for discovery in ("openarea__find", "diggable__find", "chokepoints__find"):
        assert discovery not in overseer_names, (
            f"the Overseer's MCP tool list now includes {discovery}; that removes its "
            "dependency on the Architect and should be a deliberate, recorded decision"
        )
        assert discovery in architect_names

    assert "openarea__build" not in architect_names
    assert "diggable__dig" not in architect_names


def test_tool_definitions_shape(registry, roster):
    defs = tool_definitions(registry, roster, "overseer")
    assert defs, "the overseer should have at least one tool"
    for d in defs:
        assert set(d) == {"name", "description", "inputSchema"}
        assert isinstance(d["name"], str) and d["name"]
        assert isinstance(d["description"], str) and d["description"]
        schema = d["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_description_states_mutation_and_verification_status(registry, roster):
    defs = {d["name"]: d for d in tool_definitions(registry, roster, "overseer")}

    build_desc = defs["openarea__build"]["description"]
    assert "Mutates fort state." in build_desc
    assert "Verified against a live fort: 2026-09-12" in build_desc

    landmarks_build_desc = defs["landmarks__build"]["description"]
    assert "Mutates fort state." in landmarks_build_desc
    assert "NOT VERIFIED" in landmarks_build_desc

    read_desc = defs["overview__get"]["description"]
    assert "Read-only" in read_desc


def test_unknown_role_yields_no_tools_not_an_error(registry, roster):
    assert tool_definitions(registry, roster, "nobody") == []


def test_native_queue_tools_use_describe_and_are_role_scoped(registry, roster):
    """dfmcp.tools.tool_definitions' native-tool branch
    (handoffs/2026-09-15-queue-into-dfmcp.md): a tool exposing `.describe`
    is described through it, never through the DFHack-shaped
    _tool_description/_input_schema pair, and queue.propose's schema is
    built fresh per calling role."""
    from dfqueue.schema import TYPE_VOCAB_BY_ROLE

    architect_defs = {d["name"]: d for d in tool_definitions(registry, roster, "architect")}
    overseer_defs = {d["name"]: d for d in tool_definitions(registry, roster, "overseer")}

    assert {"queue__propose", "queue__pass"} <= set(architect_defs)
    assert "queue__rule" not in architect_defs
    assert "queue__pending" not in architect_defs

    assert {"queue__rule", "queue__pending"} <= set(overseer_defs)
    assert "queue__propose" not in overseer_defs
    assert "queue__pass" not in overseer_defs

    propose_schema = architect_defs["queue__propose"]["inputSchema"]
    assert propose_schema["additionalProperties"] is False
    assert propose_schema["properties"]["type"]["enum"] == list(TYPE_VOCAB_BY_ROLE["architect"])
    assert "role" not in propose_schema["properties"]
    assert "id" not in propose_schema["properties"]
    assert "cycle" not in propose_schema["properties"]


# --------------------------------------------------------------------------
# argv_for_call: the happy paths
# --------------------------------------------------------------------------


def test_no_arg_tool(registry):
    tool = registry.get("overview.get")
    assert argv_for_call(tool, {}) == ["df-overseer-overview", "get"]


def test_required_only(registry):
    tool = registry.get("openarea.find")
    argv = argv_for_call(tool, {"w": 5, "h": 4, "near_landmark": "MainHall"})
    assert argv == ["df-overseer-openarea", "find", "5", "4", "MainHall"]


def test_leading_optional_supplied(registry):
    tool = registry.get("openarea.find")
    argv = argv_for_call(
        tool, {"w": 5, "h": 4, "level": -1, "near_landmark": "MainHall", "radius_tiles": 30}
    )
    assert argv == ["df-overseer-openarea", "find", "5", "4", "-1", "MainHall", "30"]


def test_repeated_name_args_map_to_disambiguated_positions(registry):
    tool = registry.get("connectivity.check-units")
    argv = argv_for_call(tool, {"unit_id_1": 10, "unit_id_2": 20})
    assert argv == ["df-overseer-connectivity", "check-units", "10", "20"]


def test_enum_argument_accepts_a_valid_choice(registry):
    tool = registry.get("labor.set-labor")
    argv = argv_for_call(
        tool, {"unit_id": 7, "labor_name": "MINE", "on_off": "on"}
    )
    assert argv == ["df-overseer-labor", "set-labor", "7", "MINE", "on"]


# --------------------------------------------------------------------------
# argv_for_call: the positional-optional gap trap
# --------------------------------------------------------------------------


def test_supplying_a_later_optional_without_an_earlier_one_raises(registry):
    """The exact scenario named in the task brief: RANK supplied, LEVEL
    omitted (this argument was named Z until 2026-09-14, see
    handoffs/2026-09-14-relative-level-args.md)."""
    tool = registry.get("openarea.build")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(
            tool,
            {
                "w": 5,
                "h": 4,
                "near_landmark": "MainHall",
                "blueprint_file": "stock.csv",
                "rank": 1,
            },
        )
    msg = str(exc.value)
    assert "rank" in msg and "level" in msg


def test_trailing_optionals_cannot_skip_a_middle_slot(registry):
    """RADIUS_TILES supplied while RANK (and LEVEL) are omitted -- same trap,
    entirely among trailing optionals this time."""
    tool = registry.get("openarea.build")
    with pytest.raises(ArgumentError):
        argv_for_call(
            tool,
            {
                "w": 5,
                "h": 4,
                "near_landmark": "MainHall",
                "blueprint_file": "stock.csv",
                "radius_tiles": 30,
            },
        )


def test_omitting_all_optionals_is_fine(registry):
    tool = registry.get("openarea.build")
    argv = argv_for_call(
        tool,
        {"w": 5, "h": 4, "near_landmark": "MainHall", "blueprint_file": "stock.csv"},
    )
    assert argv == ["df-overseer-openarea", "build", "5", "4", "MainHall", "stock.csv"]


def test_supplying_every_optional_in_order_is_fine(registry):
    tool = registry.get("openarea.build")
    argv = argv_for_call(
        tool,
        {
            "w": 5,
            "h": 4,
            "level": -3,
            "near_landmark": "MainHall",
            "blueprint_file": "stock.csv",
            "rank": 1,
            "radius_tiles": 30,
        },
    )
    assert argv == [
        "df-overseer-openarea",
        "build",
        "5",
        "4",
        "-3",
        "MainHall",
        "stock.csv",
        "1",
        "30",
    ]


# --------------------------------------------------------------------------
# argv_for_call: validation
# --------------------------------------------------------------------------


def test_unknown_argument_rejected(registry):
    tool = registry.get("overview.get")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"bogus": "1"})
    assert "bogus" in str(exc.value)


def test_missing_required_argument_rejected(registry):
    tool = registry.get("openarea.find")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"w": 5, "h": 4})
    assert "near_landmark" in str(exc.value)


def test_shell_metacharacter_in_string_argument_rejected(registry):
    tool = registry.get("ui.click")
    for bad in ('"; rm -rf /', "`whoami`", "$(id)", "a|b", "a&b"):
        with pytest.raises(ArgumentError):
            argv_for_call(tool, {"text": bad})


def test_pipe_is_rejected_even_though_it_looks_like_an_enum_separator(registry):
    """Not a real DFHack pipe/enum syntax for an ordinary string argument --
    a shell metacharacter caught the same as any other string field."""
    tool = registry.get("landmarks.get")
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"name": "a|b"})


def test_non_numeric_string_rejected_for_integer_argument(registry):
    tool = registry.get("openarea.find")
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"w": "five", "h": 4, "near_landmark": "MainHall"})


def test_boolean_rejected_for_integer_argument(registry):
    tool = registry.get("openarea.find")
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"w": True, "h": 4, "near_landmark": "MainHall"})


def test_invalid_enum_choice_rejected(registry):
    tool = registry.get("labor.set-labor")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"unit_id": 7, "labor_name": "MINE", "on_off": "sideways"})
    assert "on_off" in str(exc.value)


def test_numeric_string_accepted_for_integer_argument(registry):
    """A caller may reasonably hand a numeric string; DFHack's own tonumber()
    would accept it too."""
    tool = registry.get("openarea.find")
    argv = argv_for_call(tool, {"w": "5", "h": "4", "near_landmark": "MainHall"})
    assert argv == ["df-overseer-openarea", "find", "5", "4", "MainHall"]
