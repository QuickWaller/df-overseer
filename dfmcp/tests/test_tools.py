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
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS
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
    return load_registry(native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS})


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
    """Every argument token in the real, current manifest is one of the forms
    dfmcp/tools.py documents: a plain placeholder, a literal choice, an
    all-or-nothing group of plain placeholders, or a repeated placeholder
    (last in its signature). Each must resolve to specs whose names are legal
    JSON-Schema property names. If a future manifest edit adds a token shaped
    some other way, this test should be the thing that notices (the parser
    itself raises ToolSchemaError, which fails the sweep loudly)."""
    import re

    from dfmcp.tools import _parse_arg_tokens

    name_re = re.compile(r"^[a-z][a-z0-9_]*$")
    for tool in registry.all():
        for token in tool.args:
            specs = _parse_arg_tokens(token, tool.id.split(".", 1)[0])
            assert specs, f"{tool.id}: empty argument token {token!r}"
            for spec in specs:
                assert name_re.match(spec.name) or spec.enum is not None, (
                    f"{tool.id}: token {token!r} became property name {spec.name!r}"
                )
                if spec.group is not None:
                    assert not spec.required and not spec.repeated and spec.enum is None
        # a repeated argument is always last; the full-signature resolver enforces it
        specs = _arg_specs_for_tool(tool)
        assert all(not s.repeated for s in specs[:-1]), tool.id
        assert len({s.name for s in specs}) == len(specs), f"{tool.id}: duplicate property names"


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


def test_supplying_a_later_optional_without_an_earlier_one_fills_the_default(registry):
    """RANK supplied, LEVEL omitted (this argument was named Z until
    2026-09-14, see handoffs/2026-09-14-relative-level-args.md). Until
    2026-09-25 this was refused; TOOLS.yaml now declares LEVEL's default (0),
    so the skipped slot is filled with it (handoffs/2026-09-25-tool-gaps-
    from-first-cycle.md item 2)."""
    tool = registry.get("openarea.build")
    argv = argv_for_call(
        tool,
        {"w": 5, "h": 4, "near_landmark": "MainHall", "blueprint_file": "stock.csv", "rank": 1},
    )
    assert argv == ["df-overseer-openarea", "build", "5", "4", "0", "MainHall", "stock.csv", "1"]


def test_a_skipped_slot_with_no_declared_default_is_still_refused(registry):
    """zone.place's OWNER has no declared default (there is no safe value to
    guess), so naming the later AROUND_FURNITURE without it is still a named
    gap that says why."""
    tool = registry.get("zone.place")
    assert "OWNER" not in tool.defaults
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(
            tool, {"kind": "Tomb", "near_landmark": "Wagon", "around_furniture": "true"}
        )
    msg = str(exc.value)
    assert "around_furniture" in msg and "owner" in msg and "no default" in msg


def test_dry_run_alone_skips_every_earlier_optional_with_its_default(registry):
    """The Overseer's six failed calls: dig-stair with only dry_run named."""
    tool = registry.get("diggable.dig-stair")
    assert argv_for_call(tool, {"near_landmark": "Wagon", "dry_run": "false"}) == [
        "df-overseer-diggable", "dig-stair", "0", "Wagon", "1", "30", "false"
    ]
    # nothing optional named: unchanged, nothing filled
    assert argv_for_call(tool, {"near_landmark": "Wagon"}) == [
        "df-overseer-diggable", "dig-stair", "Wagon"
    ]
    # every optional named in order: unchanged
    assert argv_for_call(
        tool, {"level": -1, "near_landmark": "Wagon", "rank": 2, "radius_tiles": 9, "dry_run": "true"}
    ) == ["df-overseer-diggable", "dig-stair", "-1", "Wagon", "2", "9", "true"]


def test_defaults_declared_in_the_manifest_only_name_optional_placeholders(tmp_path):
    from dfmcp.registry import RegistryError, load_registry as _load

    def manifest(defaults):
        p = tmp_path / "t.yaml"
        p.write_text(
            "df-overseer-x.lua:\n  commands:\n    \"go NAME [A] [B]\":\n"
            "      lua_function: f\n      effect: read\n      coordinate_bearing: false\n"
            f"      knowledge_scope: player_visible\n      defaults: {defaults}\n",
            encoding="utf-8",
        )
        return p

    tool = _load(manifest('{A: "1"}')).get("x.go")
    assert tool.defaults == {"A": "1"}
    assert argv_for_call(tool, {"name": "n", "b": "z"}) == ["df-overseer-x", "go", "n", "1", "z"]
    with pytest.raises(RegistryError):
        _load(manifest('{NAME: "1"}'))  # required, not optional
    with pytest.raises(RegistryError):
        _load(manifest('{A: true}'))  # unquoted boolean is not a command-line word


def test_trailing_optionals_fill_every_skipped_middle_slot(registry):
    """RADIUS_TILES supplied while RANK (and LEVEL) are omitted: both skipped
    slots are filled from TOOLS.yaml's declared defaults, in signature order."""
    tool = registry.get("openarea.build")
    argv = argv_for_call(
        tool,
        {
            "w": 5,
            "h": 4,
            "near_landmark": "MainHall",
            "blueprint_file": "stock.csv",
            "radius_tiles": 20,
        },
    )
    assert argv == ["df-overseer-openarea", "build", "5", "4", "0", "MainHall", "stock.csv", "1", "20"]


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


# --------------------------------------------------------------------------
# Optional groups `[A B]` and repeated arguments `NAME...`
# (handoffs/2026-09-21-optional-and-variadic-args.md)
# --------------------------------------------------------------------------


def _tool_for(tmp_path, signature, *, skippable=None, verb_id="t.run"):
    """A one-command registry built from a synthetic signature, so the
    grammar is tested independently of whatever the real manifest says."""
    extra = f"\n              skippable: {skippable}" if skippable is not None else ""
    path = _write_tools_yaml(
        tmp_path,
        f"""
        df-overseer-t.lua:
          commands:
            "{signature}":
              lua_function: f{extra}
              effect: read
              knowledge_scope: player_visible
        """,
    )
    return load_registry(path).get(verb_id)


def test_registry_keeps_a_bracketed_group_as_one_token(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] [LEVEL] NEAR [ITEM...] [a|b] LABOR...")
    assert tool.args == ["KIND", "[W H]", "[LEVEL]", "NEAR", "[ITEM...]", "[a|b]", "LABOR..."]


def test_group_members_are_flat_optional_typed_properties(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] NEAR")
    specs = {s.name: s for s in _arg_specs_for_tool(tool)}
    assert list(specs) == ["kind", "w", "h", "near"]
    for name in ("w", "h"):
        assert specs[name].json_type == "integer"
        assert specs[name].required is False
        assert specs[name].group == "[W H]"
    assert specs["kind"].group is None
    from dfmcp.tools import _input_schema

    schema = _input_schema(tool)
    assert schema["properties"]["w"]["type"] == "integer"
    assert schema["properties"]["h"]["type"] == "integer"
    assert schema["required"] == ["kind", "near"]


def test_group_given_whole_or_left_out_expands_normally(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] NEAR")
    assert argv_for_call(tool, {"kind": "Still", "near": "Wagon"}) == [
        "df-overseer-t", "run", "Still", "Wagon"
    ]
    assert argv_for_call(tool, {"kind": "Still", "w": 3, "h": 3, "near": "Wagon"}) == [
        "df-overseer-t", "run", "Still", "3", "3", "Wagon"
    ]


def test_one_member_of_a_group_is_a_named_error_never_a_default(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] NEAR")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"kind": "Still", "w": 3, "near": "Wagon"})
    msg = str(exc.value)
    assert "[W H]" in msg and "'w'" in msg and "'h'" in msg and "go together" in msg
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"kind": "Still", "h": 3, "near": "Wagon"})
    assert "'h'" in str(exc.value) and "'w'" in str(exc.value)


def test_null_member_counts_as_absent(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] NEAR")
    assert argv_for_call(tool, {"kind": "Still", "w": None, "h": None, "near": "Wagon"}) == [
        "df-overseer-t", "run", "Still", "Wagon"
    ]
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"kind": "Still", "w": 3, "h": None, "near": "Wagon"})


def test_group_member_values_are_typed(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] NEAR")
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"kind": "Still", "w": "wide", "h": 3, "near": "Wagon"})


def test_omitted_group_blocks_a_later_optional_unless_declared_skippable(tmp_path):
    """The positional-shift trap, for groups: without a declaration an omitted
    [W H] followed by LEVEL would put LEVEL in W's slot."""
    sig = "run KIND [W H] [LEVEL] NEAR"
    (tmp_path / "a").mkdir()
    strict = _tool_for(tmp_path / "a", sig)
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(strict, {"kind": "Still", "level": -1, "near": "Wagon"})
    msg = str(exc.value)
    assert "'level'" in msg and "[W H]" in msg and "positional" in msg

    (tmp_path / "b").mkdir()
    lenient = _tool_for(tmp_path / "b", sig, skippable='["[W H]"]')
    assert lenient.skippable == ("[W H]",)
    assert argv_for_call(lenient, {"kind": "Still", "level": -1, "near": "Wagon"}) == [
        "df-overseer-t", "run", "Still", "-1", "Wagon"
    ]
    assert argv_for_call(lenient, {"kind": "Still", "w": 3, "h": 3, "level": -1, "near": "Wagon"}) == [
        "df-overseer-t", "run", "Still", "3", "3", "-1", "Wagon"
    ]


def test_skippable_does_not_excuse_other_gaps(tmp_path):
    tool = _tool_for(tmp_path, "run KIND [W H] [LEVEL] NEAR [RANK]", skippable='["[W H]"]')
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"kind": "Still", "near": "Wagon", "rank": 2})
    assert "'rank'" in str(exc.value) and "'level'" in str(exc.value)
    assert argv_for_call(tool, {"kind": "Still", "near": "Wagon", "level": 0, "rank": 2}) == [
        "df-overseer-t", "run", "Still", "0", "Wagon", "2"
    ]


def test_skippable_must_name_an_optional_token_of_the_signature(tmp_path):
    with pytest.raises(RegistryError):
        _tool_for(tmp_path, "run KIND [W H] NEAR", skippable='["[LEVEL]"]')
    (tmp_path / "b").mkdir()
    with pytest.raises(RegistryError):  # a required token cannot be skippable
        _tool_for(tmp_path / "b", "run KIND [W H] NEAR", skippable='["KIND"]')


def test_repeated_argument_is_an_array_expanded_into_argv(tmp_path):
    from dfmcp.tools import _input_schema

    tool = _tool_for(tmp_path, "run LABOR...")
    (spec,) = _arg_specs_for_tool(tool)
    assert spec.name == "labor" and spec.repeated and spec.required
    prop = _input_schema(tool)["properties"]["labor"]
    assert prop["type"] == "array" and prop["items"] == {"type": "string"} and prop["minItems"] == 1
    assert _input_schema(tool)["required"] == ["labor"]
    assert argv_for_call(tool, {"labor": ["MASON", "CARPENTER"]}) == [
        "df-overseer-t", "run", "MASON", "CARPENTER"
    ]
    assert argv_for_call(tool, {"labor": ["MASON"]}) == ["df-overseer-t", "run", "MASON"]


def test_repeated_argument_accepts_a_bare_scalar_as_one_item(tmp_path):
    tool = _tool_for(tmp_path, "run LABOR...")
    assert argv_for_call(tool, {"labor": "MASON"}) == ["df-overseer-t", "run", "MASON"]


def test_required_repeated_argument_needs_at_least_one(tmp_path):
    tool = _tool_for(tmp_path, "run LABOR...")
    for missing in ({}, {"labor": []}, {"labor": None}):
        with pytest.raises(ArgumentError) as exc:
            argv_for_call(tool, missing)
        assert "labor" in str(exc.value) and "at least one" in str(exc.value)


def test_repeated_items_get_the_same_checks_as_single_values(tmp_path):
    tool = _tool_for(tmp_path, "run LABOR...")
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"labor": ["MASON", "A;B"]})
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"labor": ["MASON", True]})
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"labor": ["MASON", ["NESTED"]]})
    (tmp_path / "b").mkdir()
    ints = _tool_for(tmp_path / "b", "run UNIT_ID...")
    assert argv_for_call(ints, {"unit_id": [4, "5"]}) == ["df-overseer-t", "run", "4", "5"]
    with pytest.raises(ArgumentError):
        argv_for_call(ints, {"unit_id": [4, "five"]})


def test_a_list_for_a_single_value_argument_is_refused(tmp_path):
    tool = _tool_for(tmp_path, "run KIND")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"kind": ["Still", "Kennel"]})
    assert "single value" in str(exc.value)


def test_optional_repeated_argument(tmp_path):
    from dfmcp.tools import _input_schema

    tool = _tool_for(tmp_path, "run KIND [ITEM...]")
    assert "minItems" not in _input_schema(tool)["properties"]["item"]
    assert argv_for_call(tool, {"kind": "Still"}) == ["df-overseer-t", "run", "Still"]
    assert argv_for_call(tool, {"kind": "Still", "item": []}) == ["df-overseer-t", "run", "Still"]
    assert argv_for_call(tool, {"kind": "Still", "item": ["a", "b"]}) == [
        "df-overseer-t", "run", "Still", "a", "b"
    ]


def test_repeated_argument_must_be_last(tmp_path):
    tool = _tool_for(tmp_path, "run LABOR... NEAR")
    with pytest.raises(ToolSchemaError) as exc:
        _arg_specs_for_tool(tool)
    assert "last" in str(exc.value)


@pytest.mark.parametrize(
    "signature",
    [
        "run [W",  # unbalanced (the registry keeps "[W" as a plain token)
        "run A..B",
        "run [A... B]",  # repeated inside a group
        "run [a|b c]",  # literal choice inside a group
        "run 9LIVES",
    ],
)
def test_malformed_tokens_are_a_named_schema_error_not_a_junk_property(tmp_path, signature):
    tool = _tool_for(tmp_path, signature)
    with pytest.raises(ToolSchemaError):
        _arg_specs_for_tool(tool)


def test_supplying_a_repeated_optional_after_an_omitted_optional_is_a_gap(tmp_path):
    tool = _tool_for(tmp_path, "run [LEVEL] [ITEM...]")
    with pytest.raises(ArgumentError) as exc:
        argv_for_call(tool, {"item": ["a"]})
    assert "'item'" in str(exc.value) and "'level'" in str(exc.value)


# ---- the real manifest -----------------------------------------------------


def test_real_building_signatures_use_the_optional_footprint_group(registry):
    for tool_id, expected in (
        (
            "building.find",
            ["kind", "w", "h", "level", "near_landmark", "radius_tiles"],
        ),
        (
            "building.build",
            ["kind", "w", "h", "level", "near_landmark", "rank", "radius_tiles", "dry_run"],
        ),
    ):
        tool = registry.get(tool_id)
        assert "[W H]" in tool.args and tool.skippable == ("[W H]",)
        specs = _arg_specs_for_tool(tool)
        assert [s.name for s in specs] == expected
        by = {s.name: s for s in specs}
        assert by["w"].required is False and by["h"].required is False
        assert by["kind"].required and by["near_landmark"].required


def test_real_building_find_with_only_kind_and_landmark(registry):
    tool = registry.get("building.find")
    assert argv_for_call(tool, {"kind": "Still", "near_landmark": "Wagon"}) == [
        "df-overseer-building", "find", "Still", "Wagon"
    ]
    # a farm plot still says its size
    assert argv_for_call(tool, {"kind": "FarmPlot", "w": 4, "h": 5, "near_landmark": "Wagon"}) == [
        "df-overseer-building", "find", "FarmPlot", "4", "5", "Wagon"
    ]
    # LEVEL without a footprint: the Lua CLI reads one leading number as LEVEL
    assert argv_for_call(tool, {"kind": "Still", "level": -1, "near_landmark": "Wagon"}) == [
        "df-overseer-building", "find", "Still", "-1", "Wagon"
    ]
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"kind": "Still", "w": 3, "near_landmark": "Wagon"})
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"w": 3, "h": 3, "near_landmark": "Wagon"})  # KIND is required


def test_real_building_build_only_stays_positional_after_the_landmark(registry):
    tool = registry.get("building.build")
    assert argv_for_call(tool, {"kind": "Still", "near_landmark": "Wagon"}) == [
        "df-overseer-building", "build", "Still", "Wagon"
    ]
    assert argv_for_call(
        tool,
        {"kind": "Still", "level": 0, "near_landmark": "Wagon", "rank": 2, "radius_tiles": 20, "dry_run": "false"},
    ) == ["df-overseer-building", "build", "Still", "0", "Wagon", "2", "20", "false"]
    # RANK without LEVEL: LEVEL's declared default (0) fills the skipped slot
    assert argv_for_call(tool, {"kind": "Still", "near_landmark": "Wagon", "rank": 2}) == [
        "df-overseer-building", "build", "Still", "0", "Wagon", "2"
    ]
    assert argv_for_call(tool, {"kind": "Still", "near_landmark": "Wagon", "dry_run": "false"}) == [
        "df-overseer-building", "build", "Still", "0", "Wagon", "1", "30", "false"
    ]


def test_real_enabled_counts_takes_several_labors(registry):
    tool = registry.get("labor.enabled-counts")
    assert tool.args == ["LABOR..."]
    assert argv_for_call(tool, {"labor": ["MASON", "BREWER"]}) == [
        "df-overseer-labor", "enabled-counts", "MASON", "BREWER"
    ]
    assert argv_for_call(tool, {"labor": "MASON"}) == ["df-overseer-labor", "enabled-counts", "MASON"]
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {})
    with pytest.raises(ArgumentError):
        argv_for_call(tool, {"labor": []})


def test_scoped_descriptions_reach_the_schema(registry):
    from dfmcp.tools import _input_schema

    find = _input_schema(registry.get("building.find"))["properties"]
    assert "building.list-kinds" in find["kind"]["description"]
    w = find["w"]["description"].lower()
    assert "footprint" in w and "together" in w and "variable-size" in w and "error" in w
    assert "footprint" in find["h"]["description"].lower()
    listed = _input_schema(registry.get("building.list-kinds"))["properties"]
    assert "substring" in listed["filter"]["description"]
    counts = _input_schema(registry.get("labor.enabled-counts"))["properties"]["labor"]
    assert counts["type"] == "array" and "never as 0" in counts["description"]
    # another script's KIND and W keep their own text, not the building tool's
    zone = _input_schema(registry.get("zone.find"))["properties"]
    assert "zone.list-kinds" in zone["kind"]["description"]
    assert "Only water_source exists" not in zone["kind"]["description"]
    open_area = _input_schema(registry.get("openarea.find"))["properties"]
    assert "footprint" not in open_area["w"]["description"].lower()


def test_the_architect_sees_the_optional_footprint_in_tools_list(registry, roster):
    (find,) = [
        d for d in tool_definitions(registry, roster, "architect") if d["name"] == "building__find"
    ]
    schema = find["inputSchema"]
    assert schema["required"] == ["kind", "near_landmark"]
    assert schema["properties"]["w"]["type"] == "integer"
    assert "w" not in schema["required"] and "h" not in schema["required"]
