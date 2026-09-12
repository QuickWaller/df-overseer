"""Registry tests.

Two jobs. First, assert the REAL scripts/dfhack/TOOLS.yaml loads cleanly, so
these tests fail if someone edits the manifest into an invalid state. Second,
one failing-case test per structural rule, because a rule with no test asserting
it raises is not implemented in any useful sense.
"""

import textwrap

import pytest

from mcp.registry import Registry, RegistryError, load_registry


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
            "find B":
              lua_function: find_b
              effect: read
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
            "set-labor UNIT_ID LABOR on|off":
              lua_function: set_labor
              effect: mutate
        """)
    reg = load_registry(path)
    assert "labor.unit-status" in reg
    assert "labor.set-labor" in reg
    assert reg.get("labor.set-labor").mutates is True
