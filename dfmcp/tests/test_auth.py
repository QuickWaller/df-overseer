"""Tests for mcp/auth.py: bearer-token -> role resolution.

This is the credential half of docs/AGENT-ARCHITECTURE.md §13's trust
boundary ("role identity must be a credential, not a claim"), so as with
mcp/tests/test_roles.py, the failing cases matter as much as the happy path.
Every strict validation rule gets a test that proves it actually raises
(mcp/README.md's existing standard, per the task brief).

A recurring assertion below: **no error message contains a real token
value.** mcp/auth.py's own rule is "report lengths and role names only", and
that rule is only worth anything if a test would catch a future violation.
"""

from pathlib import Path

import pytest

from dfmcp.auth import AuthConfigError, load_role_tokens, resolve
from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS

GOOD_OVERSEER_TOKEN = "overseer-token-abcdefghij"  # 26 chars, well over the minimum
GOOD_ARCHITECT_TOKEN = "architect-token-klmnopqrst"  # 26 chars
GOOD_CONSULTANT_TOKEN = "consultant-token-uvwxyz1234"  # 27 chars


@pytest.fixture(scope="module")
def registry():
    # native_tools=NATIVE_TOOLS: the real roster now grants queue.* ids
    # (handoffs/2026-09-15-queue-into-dfmcp.md); see test_roles.py's
    # registry fixture for the full explanation. DOCTRINE_NATIVE_TOOLS
    # merged in too, added handoffs/2026-09-19-get-doctrine-tool.md: the
    # real agents/consultant/tools.yaml now grants doctrine.get, which
    # roles.py rule 1 requires to exist in the registry. SERIES_NATIVE_TOOLS
    # merged in too, added handoffs/2026-09-19-series-mcp-tools.md: the real
    # agents/overseer, agents/consultant and agents/quartermaster
    # tools.yaml files now grant series.* ids, same rule 1 requirement.
    return load_registry(native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS})


@pytest.fixture(scope="module")
def roster(registry):
    """The real roster: overseer, architect, consultant enabled; marshal
    (among others) defined but not enabled (agents/ROSTER.yaml)."""
    return load_roster(registry)


def _write_env(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_loads_one_token_per_enabled_role_and_resolves_each(roster, tmp_path):
    path = _write_env(
        tmp_path,
        f"""
        # a comment, and a blank line above should both be skipped
        MCP_ROLE_TOKEN_OVERSEER={GOOD_OVERSEER_TOKEN}
        MCP_ROLE_TOKEN_ARCHITECT={GOOD_ARCHITECT_TOKEN}
        MCP_ROLE_TOKEN_CONSULTANT={GOOD_CONSULTANT_TOKEN}
        """.strip()
        + "\n",
    )
    tokens = load_role_tokens(roster, path=path)
    assert tokens == {
        GOOD_OVERSEER_TOKEN: "overseer",
        GOOD_ARCHITECT_TOKEN: "architect",
        GOOD_CONSULTANT_TOKEN: "consultant",
    }

    assert resolve(GOOD_OVERSEER_TOKEN, tokens) == "overseer"
    assert resolve(GOOD_ARCHITECT_TOKEN, tokens) == "architect"
    assert resolve("not-a-real-token-at-all-00000", tokens) is None
    assert resolve("", tokens) is None


def test_unrelated_env_keys_are_ignored(roster, tmp_path):
    path = _write_env(
        tmp_path,
        f"""
        PVE_TOKEN_SECRET=something-unrelated-entirely
        MCP_ROLE_TOKEN_OVERSEER={GOOD_OVERSEER_TOKEN}
        DF_VM_IP=203.0.113.5/24
        """.strip()
        + "\n",
    )
    tokens = load_role_tokens(roster, path=path)
    assert tokens == {GOOD_OVERSEER_TOKEN: "overseer"}


def test_single_quoted_value_is_stripped(roster, tmp_path):
    """Matches scripts/pve.py's load_env convention exactly (needed there
    because the Proxmox password contains '$E', which bash would otherwise
    expand away): a value wrapped in matching quotes has them stripped."""
    path = _write_env(tmp_path, f"MCP_ROLE_TOKEN_OVERSEER='{GOOD_OVERSEER_TOKEN}'\n")
    tokens = load_role_tokens(roster, path=path)
    assert tokens == {GOOD_OVERSEER_TOKEN: "overseer"}


# --------------------------------------------------------------------------
# Strict validation, each with a failing case
# --------------------------------------------------------------------------


def test_two_roles_sharing_a_token_raises(roster, tmp_path):
    path = _write_env(
        tmp_path,
        f"""
        MCP_ROLE_TOKEN_OVERSEER={GOOD_OVERSEER_TOKEN}
        MCP_ROLE_TOKEN_ARCHITECT={GOOD_OVERSEER_TOKEN}
        """.strip()
        + "\n",
    )
    with pytest.raises(AuthConfigError) as exc:
        load_role_tokens(roster, path=path)
    msg = str(exc.value).lower()
    assert "overseer" in msg and "architect" in msg
    assert GOOD_OVERSEER_TOKEN not in str(exc.value), "must never quote the token value itself"


def test_token_for_a_disabled_role_raises(roster, tmp_path):
    """marshal is defined in agents/ROSTER.yaml but not enabled -- a token
    for it must refuse to load, not be silently ignored, since a stale token
    left over from before a role was disabled is exactly the kind of drift
    this check exists to catch."""
    path = _write_env(tmp_path, "MCP_ROLE_TOKEN_MARSHAL=some-long-enough-token-value\n")
    with pytest.raises(AuthConfigError) as exc:
        load_role_tokens(roster, path=path)
    assert "marshal" in str(exc.value)


def test_token_for_a_completely_unknown_role_raises(roster, tmp_path):
    """A typo (MCP_ROLE_TOKEN_OVERSEEER) must not silently grant nothing --
    same failure shape as roles.py's rule 1 for an unknown tool id."""
    path = _write_env(tmp_path, "MCP_ROLE_TOKEN_OVERSEEER=some-long-enough-token-value\n")
    with pytest.raises(AuthConfigError) as exc:
        load_role_tokens(roster, path=path)
    assert "overseeer" in str(exc.value)


def test_empty_token_raises(roster, tmp_path):
    path = _write_env(tmp_path, "MCP_ROLE_TOKEN_OVERSEER=\n")
    with pytest.raises(AuthConfigError):
        load_role_tokens(roster, path=path)


def test_whitespace_only_token_raises(roster, tmp_path):
    path = _write_env(tmp_path, "MCP_ROLE_TOKEN_OVERSEER='   '\n")
    with pytest.raises(AuthConfigError):
        load_role_tokens(roster, path=path)


def test_token_below_minimum_length_raises(roster, tmp_path):
    path = _write_env(tmp_path, "MCP_ROLE_TOKEN_OVERSEER=short\n")
    with pytest.raises(AuthConfigError) as exc:
        load_role_tokens(roster, path=path)
    msg = str(exc.value)
    assert "5" in msg  # len("short") == 5, reported
    assert "short" not in msg, "must never quote the token value itself"


def test_minimum_length_is_configurable(roster, tmp_path):
    path = _write_env(tmp_path, "MCP_ROLE_TOKEN_OVERSEER=twelvecharas\n")
    tokens = load_role_tokens(roster, path=path, minimum_length=8)
    assert tokens == {"twelvecharas": "overseer"}


# --------------------------------------------------------------------------
# resolve(): constant-effort comparison, never a leak
# --------------------------------------------------------------------------


def test_resolve_does_not_short_circuit_on_first_entry(roster):
    """Not a timing-side-channel test (that would be flaky); a functional
    check that a match anywhere in the mapping is found, not only a match in
    the first position -- proves the loop doesn't return early on a miss."""
    tokens = {
        "aaaaaaaaaaaaaaaaaaaaaaaa": "consultant",
        "bbbbbbbbbbbbbbbbbbbbbbbb": "architect",
        GOOD_OVERSEER_TOKEN: "overseer",
    }
    assert resolve(GOOD_OVERSEER_TOKEN, tokens) == "overseer"


def test_resolve_returns_none_for_empty_mapping():
    assert resolve(GOOD_OVERSEER_TOKEN, {}) is None
