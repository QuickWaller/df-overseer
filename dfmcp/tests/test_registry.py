"""Registry tests.

Two jobs. First, assert the REAL scripts/dfhack/TOOLS.yaml loads cleanly, so
these tests fail if someone edits the manifest into an invalid state. Second,
one failing-case test per structural rule, because a rule with no test asserting
it raises is not implemented in any useful sense.
"""

import textwrap

import pytest

from dfmcp.registry import Registry, RegistryError, load_registry


# --------------------------------------------------------------------------
# The real manifest
# --------------------------------------------------------------------------

def test_real_manifest_loads():
    reg = load_registry()
    assert len(reg) > 0


def test_canonical_ids_are_script_dot_verb():
    reg = load_registry()
    for tool_id in reg.ids():
        assert "." in tool_id, tool_id
        script, verb = tool_id.split(".", 1)
        assert not script.startswith("df-overseer-"), tool_id
        assert not script.endswith(".lua"), tool_id
        assert verb, tool_id


def test_every_real_tool_has_a_summary_and_a_guide():
    """handoffs/2026-10-02-tool-descriptions-split.md task 5: every command
    in the real manifest must carry a non-empty `summary` short enough to
    stand as an MCP description, and a `guide` (the operating detail that
    used to live in `notes` alone). 300 chars is the handoff's own cap;
    `notes` itself is unrestricted and untouched by this test.

    handoffs/2026-10-02-structured-tool-guides.md task 1: `guide` is now a
    structured ToolGuide, not a prose string -- every command must carry a
    non-empty `arguments` list (empty is fine -- a tool that takes none),
    a non-empty `returns`, and list-typed `before_a_real_run`/`traps`
    (either may be empty, but must be a list, never missing or a string)."""
    reg = load_registry()
    for tool in reg.all():
        if not hasattr(tool, "summary"):
            continue  # a native tool (queue.*, gotchas.*, ...), not TOOLS.yaml-backed
        assert tool.summary, f"{tool.id}: missing summary"
        assert len(tool.summary) < 300, f"{tool.id}: summary is {len(tool.summary)} chars, over the 300 cap"
        assert tool.guide, f"{tool.id}: missing guide"
        assert isinstance(tool.guide.arguments, tuple), f"{tool.id}: guide.arguments must be a list"
        assert tool.guide.returns, f"{tool.id}: guide.returns must be non-empty"
        assert isinstance(tool.guide.before_a_real_run, tuple), f"{tool.id}: guide.before_a_real_run must be a list"
        assert isinstance(tool.guide.traps, tuple), f"{tool.id}: guide.traps must be a list"
        for arg in tool.guide.arguments:
            assert arg.name, f"{tool.id}: a guide argument is missing a name"
            assert arg.meaning, f"{tool.id}: guide argument {arg.name!r} is missing a meaning"


def test_guide_text_renders_fixed_section_order():
    """handoffs/2026-10-02-structured-tool-guides.md task 1: guide_text()
    renders the four sections in a fixed order (Arguments, Returns, Before
    a real run, Traps) regardless of how TOOLS.yaml happens to order its
    keys, with one argument per line as "NAME (required|optional, default
    X): meaning"."""
    from dfmcp.registry import GuideArgument, ToolGuide

    guide = ToolGuide(
        arguments=(
            GuideArgument(name="TEMPLATE", required=True, default=None, meaning="A template id."),
            GuideArgument(name="LEVEL", required=False, default="0", meaning="An offset."),
        ),
        returns="What comes back.",
        before_a_real_run=("DRY_RUN defaults to true.",),
        traps=("Quickfort can report success while designating nothing.",),
    )
    text = guide.guide_text()
    for heading in ("Arguments:", "Returns:", "Before a real run:", "Traps:"):
        assert heading in text
    assert text.index("Arguments:") < text.index("Returns:") < text.index("Before a real run:") < text.index("Traps:")
    assert "TEMPLATE (required): A template id." in text
    assert "LEVEL (optional, default 0): An offset." in text
    assert "- DRY_RUN defaults to true." in text
    assert "- Quickfort can report success while designating nothing." in text


def test_guide_text_empty_string_default_has_nothing_to_show():
    """A few arguments (MATERIAL_CHOICE) declare "" as their documented
    default, the Lua CLI's own "not given" convention -- guide_text must not
    render "optional, default )" or similarly empty-looking text for them."""
    from dfmcp.registry import GuideArgument, ToolGuide

    guide = ToolGuide(
        arguments=(GuideArgument(name="MATERIAL_CHOICE", required=False, default="", meaning="Picks one."),),
        returns="Something.",
        before_a_real_run=(),
        traps=(),
    )
    text = guide.guide_text()
    assert "MATERIAL_CHOICE (optional): Picks one." in text
    assert "default " not in text.split("MATERIAL_CHOICE")[1].split("\n")[0]


def test_guide_text_empty_sections_say_so_plainly():
    from dfmcp.registry import ToolGuide

    guide = ToolGuide(arguments=(), returns="Reads a value.", before_a_real_run=(), traps=())
    text = guide.guide_text()
    assert "None." in text  # arguments
    assert "Nothing special." in text  # before_a_real_run
    assert "None known." in text  # traps


def test_malformed_guide_is_a_registry_error():
    """A guide that fails to match the four-section schema is a hard
    load-time failure, same severity as every other structural rule in this
    module -- a silently mis-parsed guide would mislead every caller who
    reads it."""
    from dfmcp.registry import _parse_guide

    with pytest.raises(RegistryError):
        _parse_guide("x.lua", "cmd", {"arguments": "not a list", "returns": "ok"})
    with pytest.raises(RegistryError):
        _parse_guide("x.lua", "cmd", {"returns": ""})  # empty returns
    with pytest.raises(RegistryError):
        _parse_guide("x.lua", "cmd", {"returns": "ok", "unknown_key": 1})
    with pytest.raises(RegistryError):
        _parse_guide("x.lua", "cmd", {"returns": "ok", "arguments": [{"required": True, "meaning": "x"}]})


def test_known_ids_resolve_as_expected():
    """Spot-check ids the allowlists in agents/ actually depend on."""
    reg = load_registry()
    for expected in (
        "overview.get",
        "landmarks.list",
        "openarea.find",
        "openarea.build",
        "diggable.dig",
        "labor.set-labor",
        "stuckjobs.find",
        # handoffs/2026-09-17-water-and-industry-tools.md
        "zone.find",
        "zone.place",
        "trees.find",
        "trees.fell",
        "well.find",
        "well.build",
        "orders.list",
        "orders.create",
        "orders.cancel",
    ):
        assert expected in reg, f"{expected} missing from the registry"


def test_mutating_tools_are_flagged_and_reads_are_not():
    """The `mutates` flag is what roles.py rule 2 rests on, so pin it."""
    reg = load_registry()
    assert reg.get("openarea.build").mutates is True
    assert reg.get("diggable.dig").mutates is True
    assert reg.get("labor.set-labor").mutates is True
    assert reg.get("overview.get").mutates is False
    assert reg.get("stuckjobs.find").mutates is False


def test_water_and_industry_tools_are_flagged_and_scoped_correctly():
    """handoffs/2026-09-17-water-and-industry-tools.md: finds are read,
    places/fells/builds/create/cancel are mutate, and every one carries a
    valid knowledge_scope (player_derivable for the spatial tools,
    player_visible for orders.*, which reads/writes a manager order list a
    player sees on the Jobs/Work Orders screen, not fort geometry)."""
    reg = load_registry()
    assert reg.get("zone.find").mutates is False
    assert reg.get("zone.place").mutates is True
    assert reg.get("trees.find").mutates is False
    assert reg.get("trees.fell").mutates is True
    assert reg.get("well.find").mutates is False
    assert reg.get("well.build").mutates is True
    assert reg.get("orders.list").mutates is False
    assert reg.get("orders.create").mutates is True
    assert reg.get("orders.cancel").mutates is True
    for tool_id in (
        "zone.find", "zone.place", "trees.find", "trees.fell",
        "well.find", "well.build",
    ):
        assert reg.get(tool_id).knowledge_scope == "player_derivable", tool_id
    for tool_id in ("orders.list", "orders.create", "orders.cancel"):
        assert reg.get(tool_id).knowledge_scope == "player_visible", tool_id


def test_workshop_kind_extension_did_not_remove_the_old_kinds():
    """handoffs/2026-09-17-water-and-industry-tools.md item 3 extended
    workshop.find/build's KIND with mason/mechanic/carpenter -- the
    command signature (and so the canonical id) is unchanged, but this
    pins that the still/kitchen-era ids the farm-and-still-tools stream
    already depended on are still exactly these two ids, not renamed."""
    reg = load_registry()
    assert "workshop.find" in reg
    assert "workshop.build" in reg
    assert reg.get("workshop.find").mutates is False
    assert reg.get("workshop.build").mutates is True


def test_the_two_safety_detectors_are_present_and_not_verified():
    """Added 2026-09-12, never run against a live fort. If this ever starts
    reporting them as verified, someone changed the manifest and the claim
    needs checking against an actual live test, not taken on trust."""
    reg = load_registry()
    for tool_id in ("threat.scan", "breach.check"):
        assert tool_id in reg
        tool = reg.get(tool_id)
        assert tool.mutates is False
        assert tool.is_verified is False, (
            f"{tool_id} now claims to be verified. Was it actually run live?"
        )


def test_stocks_availability_is_read_derivable_and_verified_live():
    """handoffs/2026-09-19-per-item-flags-tool.md: the per-item-flags
    netting tool. Offline build stream -- never run against a live DFHack
    process. UPDATED 2026-09-22: it has since been deployed and run live (a
    `BOULDER` read returned 7 total, 3 in buildings, 4 available: the 2026-09-19
    deploy batch), so `verified` now carries that evidence and Tool.is_verified
    is True. Still guarded: if it reads unverified again, someone reverted the
    manifest. The threat.scan/breach.check test above keeps the unverified pin.
    Takes one positional argument (TYPE, e.g. BUCKET/DRINK/SEEDS/CHAIN/BLOCKS/
    TRAPPARTS)."""
    reg = load_registry()
    assert "stocks.availability" in reg
    tool = reg.get("stocks.availability")
    assert tool.mutates is False
    assert tool.knowledge_scope == "player_derivable"
    assert tool.is_verified is True, (
        "stocks.availability reads unverified again; it was run live "
        "2026-09-19 to 2026-09-20 (register), so the manifest was reverted"
    )
    assert tool.args == ["TYPE"]


# --------------------------------------------------------------------------
# knowledge_scope: added 2026-09-16 (handoffs/2026-09-16-knowledge-scope-audit.md,
# decisions/DECISIONS.md 2026-09-16 "Agents may only know what a vanilla
# player could know"). Every command in the real manifest must carry a valid
# tag; a missing or invalid one is a hard load-time error, same severity as
# a bad `effect`.
# --------------------------------------------------------------------------

def test_every_real_tool_has_a_valid_knowledge_scope():
    reg = load_registry()
    valid = {"player_visible", "player_derivable", "omniscient"}
    for tool in reg.all():
        assert tool.knowledge_scope in valid, (
            f"{tool.id} has knowledge_scope={tool.knowledge_scope!r}"
        )


def test_no_real_tool_is_tagged_omniscient():
    """The whole point of this stream: every tool this manifest could not
    honestly call omniscient was fixed, not merely relabeled. If this ever
    fails, either a tool needs the same fix the others got, or the fix
    regressed and the tool must leave every role's allowlist
    (roles.py rule 7 enforces the second half of that at load time)."""
    reg = load_registry()
    omniscient = [t.id for t in reg.all() if t.is_omniscient]
    assert omniscient == []


def test_missing_knowledge_scope_raises(tmp_path):
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "find A":
              lua_function: find_a
              effect: read
        """)
    with pytest.raises(RegistryError) as exc:
        load_registry(path)
    assert "knowledge_scope" in str(exc.value)


def test_invalid_knowledge_scope_raises(tmp_path):
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "find A":
              lua_function: find_a
              effect: read
              knowledge_scope: mostly_fine
        """)
    with pytest.raises(RegistryError) as exc:
        load_registry(path)
    assert "knowledge_scope" in str(exc.value)


def test_omniscient_tag_is_valid_and_flagged_by_is_omniscient(tmp_path):
    """omniscient is a legal tag for load_registry to accept -- it's roles.py's
    job to refuse granting it to anyone, not registry.py's job to refuse
    loading it (a manifest needs to be able to name the problem before the
    tool is fixed or removed)."""
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "find A":
              lua_function: find_a
              effect: read
              knowledge_scope: omniscient
        """)
    reg = load_registry(path)
    assert reg.get("thing.find").is_omniscient is True


# --------------------------------------------------------------------------
# Structural rules, each with a failing case
# --------------------------------------------------------------------------

def _write(tmp_path, body):
    path = tmp_path / "TOOLS.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_canonical_id_collision_raises(tmp_path):
    """Two commands normalising to one id must not silently overwrite."""
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "find A":
              lua_function: find_a
              effect: read
              knowledge_scope: player_visible
            "find B":
              lua_function: find_b
              effect: read
              knowledge_scope: player_visible
        """)
    with pytest.raises(RegistryError) as exc:
        load_registry(path)
    assert "thing.find" in str(exc.value)


def test_unrecognised_effect_raises(tmp_path):
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "find A":
              lua_function: find_a
              effect: sideways
        """)
    with pytest.raises(RegistryError):
        load_registry(path)


def test_missing_lua_function_raises(tmp_path):
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "find A":
              effect: read
        """)
    with pytest.raises(RegistryError):
        load_registry(path)


def test_command_signature_with_no_leading_verb_raises(tmp_path):
    path = _write(tmp_path, """
        df-overseer-thing.lua:
          commands:
            "123 nope":
              lua_function: f
              effect: read
        """)
    with pytest.raises(RegistryError):
        load_registry(path)


def test_hyphenated_verbs_survive_whole(tmp_path):
    """`unit-status` and `set-labor` must not be split at the hyphen."""
    path = _write(tmp_path, """
        df-overseer-labor.lua:
          commands:
            "unit-status [idle]":
              lua_function: unit_status
              effect: read
              knowledge_scope: player_visible
            "set-labor UNIT_ID LABOR on|off":
              lua_function: set_labor
              effect: mutate
              knowledge_scope: player_visible
        """)
    reg = load_registry(path)
    assert "labor.unit-status" in reg
    assert "labor.set-labor" in reg
    assert reg.get("labor.set-labor").mutates is True


# --------------------------------------------------------------------------
# native_tools: dfmcp/queue_tools.py's non-DFHack tools, merged additively
# (handoffs/2026-09-15-queue-into-dfmcp.md)
# --------------------------------------------------------------------------


def test_load_registry_defaults_to_no_native_tools():
    """The default, no-argument call stays exactly what every other test in
    this file already assumes: the real DFHack manifest only. A caller must
    opt in to native tools explicitly."""
    reg = load_registry()
    assert "queue.propose" not in reg


def test_native_tools_are_merged_in_when_passed():
    from dfmcp.queue_tools import NATIVE_TOOLS

    reg = load_registry(native_tools=NATIVE_TOOLS)
    for tool_id in NATIVE_TOOLS:
        assert tool_id in reg
        assert reg.get(tool_id) is NATIVE_TOOLS[tool_id]
    # And the real manifest's own tools are still all there alongside them.
    assert "overview.get" in reg


def test_native_tool_id_colliding_with_a_real_id_raises():
    class _Fake:
        mutates = False

    with pytest.raises(RegistryError) as exc:
        load_registry(native_tools={"overview.get": _Fake()})
    assert "overview.get" in str(exc.value)
