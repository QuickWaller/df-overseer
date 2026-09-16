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
