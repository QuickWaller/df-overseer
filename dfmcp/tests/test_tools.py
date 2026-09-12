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
references (as of this stream, 2026-09-12):

  W, H            scripts/dfhack/df-overseer-openarea.lua:325 (tonumber(args[2]), tonumber(args[3]))
  Z               scripts/dfhack/df-overseer-openarea.lua:327 (tonumber(args[4]) sniff)
  RANK, RADIUS_TILES  scripts/dfhack/df-overseer-openarea.lua:343 (tonumber(args[7]), tonumber(args[8]))
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

from dfmcp.registry import RegistryError, load_registry
from dfmcp.roles import load_roster
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
    return load_registry()


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
        df-overseer-a.lua:
          commands:
            "b__c D":
              lua_function: f2
              effect: read
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
    assert specs["z"].json_type == "integer" and not specs["z"].required
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
        tool, {"w": 5, "h": 4, "z": 12, "near_landmark": "MainHall", "radius_tiles": 30}
    )
    assert argv == ["df-overseer-openarea", "find", "5", "4", "12", "MainHall", "30"]


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
    """The exact scenario named in the task brief: RANK supplied, Z omitted."""
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
    assert "rank" in msg and "z" in msg


def test_trailing_optionals_cannot_skip_a_middle_slot(registry):
    """RADIUS_TILES supplied while RANK (and Z) are omitted -- same trap,
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
            "z": 3,
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
        "3",
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
