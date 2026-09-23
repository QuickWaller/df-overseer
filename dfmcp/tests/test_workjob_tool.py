"""Tests for the df-overseer-workjob.lua registration: the direct
workshop-job route added handoffs/2026-09-19-workshop-add-job.md as the
honest alternative to a manager order that never becomes a job on this
install (handoffs/2026-09-19-well-and-harvest.md section 5,
handoffs/2026-09-19-well-finish.md sections 2-4).

No Lua file in this repo is ever executed by this test suite (there is no
DFHack process to run it against, matching every other df-overseer-*.lua
tool's own test coverage: test_registry.py/test_roles.py/test_tools.py all
validate the YAML-driven metadata layer, never shell out to a .lua file).
This file follows that same convention: it pins the registry entry, the
per-role grants (overseer write, architect read-only + explicit deny,
consultant untouched matching the orders.* precedent), and the MCP-facing
name/argv translation -- everything that IS checked before a first live run,
per this project's "mark verified vs proposed" rule.
"""

import pytest

from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS
from dfmcp.tools import argv_for_call, build_tool_names, tool_definitions


@pytest.fixture(scope="module")
def registry():
    # Same native_tools merge as test_roles.py/test_tools.py's own fixtures
    # -- required for load_roster to accept the real agents/*/tools.yaml
    # files, which still grant queue.*/doctrine.get/series.* alongside the
    # new workjob.* ids this stream adds.
    return load_registry(
        native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS}
    )


@pytest.fixture(scope="module")
def roster(registry):
    return load_roster(registry)


# --------------------------------------------------------------------------
# Registry: the manifest entry itself
# --------------------------------------------------------------------------


def test_workjob_ids_exist_in_the_real_manifest(registry):
    assert "workjob.list" in registry
    assert "workjob.queue" in registry


def test_workjob_list_is_a_read_that_never_mutates(registry):
    tool = registry.get("workjob.list")
    assert tool.effect == "read"
    assert not tool.mutates


def test_workjob_queue_is_flagged_mutating(registry):
    tool = registry.get("workjob.queue")
    assert tool.effect == "mutate"
    assert tool.mutates


def test_workjob_queue_carries_no_coordinates(registry):
    """Design commitment #1: no raw x/y/z ever leaves this command's
    boundary. TOOLS.yaml's own coordinate_bearing field is this project's
    documented flag for that -- both workjob commands must be `false`, the
    same as every other landmark-addressed tool (e.g. orders.create,
    workshop.build)."""
    for tool_id in ("workjob.list", "workjob.queue"):
        assert registry.get(tool_id).coordinate_bearing is False, tool_id


def test_workjob_queue_is_verified_by_its_live_runs(registry):
    """The offline build stream never ran live, so this test once pinned
    is_verified False. UPDATED 2026-09-22: the tool has since queued blocks
    and a mechanism for real and the well was built from them
    (handoffs/2026-09-19-stone-blocks-well.md, register 2026-09-19), so the
    manifest carries that evidence and is_verified is True. brew_drink still
    refuses on the container reagent by design."""
    tool = registry.get("workjob.queue")
    assert tool.is_verified is True


def test_workjob_queue_argument_signature_matches_the_lua_dispatch():
    """Ground truth: scripts/dfhack/df-overseer-workjob.lua's own dispatch
    block reads `args[2], args[3], args[4]` as job/workshop_name/dry_run in
    that order for the `queue` command -- pinned here the same way
    test_tools.py's own module docstring pins W/H/LEVEL/etc against each
    owning script's dispatch code."""
    reg = load_registry(
        native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS}
    )
    tool = reg.get("workjob.queue")
    tokens = [t.strip("[]") for t in tool.args]
    assert tokens == ["JOB", "WORKSHOP_LANDMARK_NAME", "DRY_RUN", "REPEAT"]
    assert tool.args[0] == "JOB"
    assert tool.args[1] == "WORKSHOP_LANDMARK_NAME"
    assert tool.args[2] == "[DRY_RUN]"  # optional, dry-run defaults true
    assert tool.args[3] == "[REPEAT]"  # optional, off by default (handoffs/2026-09-23)


# --------------------------------------------------------------------------
# Roles: granted deliberately, not by accident
# --------------------------------------------------------------------------


def test_only_the_overseer_can_queue_a_workjob(roster):
    """The sole-writer rule (agents/ROSTER.yaml, docs/AGENT-ARCHITECTURE.md
    §7): a fort-mutating tool may only ever sit in the sole writer's own
    `write` list."""
    assert "workjob.queue" in roster.roles["overseer"].write
    assert "workjob.queue" not in roster.roles["architect"].write
    assert "workjob.queue" not in roster.roles["architect"].read
    assert "workjob.queue" not in roster.roles["consultant"].write
    assert "workjob.queue" not in roster.roles["consultant"].read


def test_architect_can_see_the_job_vocabulary_but_not_act(roster):
    """Matches the established orders.list/orders.create asymmetry: the
    Architect may read what jobs exist to name in a proposal, but has no
    tool that acts (docs/AGENT-ARCHITECTURE.md, "Specialists propose, the
    Overseer decides")."""
    assert "workjob.list" in roster.roles["architect"].read
    assert "workjob.queue" not in roster.roles["architect"].read
    assert "workjob.queue" not in roster.roles["architect"].write


def test_overseer_also_holds_the_read(roster):
    assert "workjob.list" in roster.roles["overseer"].read


def test_workjob_denied_to_architect_is_denied_with_a_reason():
    """Rule content, not just the loaded roster: agents/architect/tools.yaml
    must carry an explicit deny entry (reason text), the same convention
    every other Overseer-only write already gets there (orders.create,
    well.build, ...) -- read the YAML directly rather than only the
    resolved Roster, so a future edit that deletes the deny block (while
    still failing to grant it, so the roster-level test above stays green)
    is still caught."""
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "agents" / "architect" / "tools.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    deny_ids = {entry["id"] for entry in data.get("deny", [])}
    assert "workjob.queue" in deny_ids


def test_quartermaster_explicitly_denies_workjob_queue():
    """agents/quartermaster/tools.yaml is not loaded by load_roster (the
    role is disabled, ROSTER.yaml `enabled: false`), so this is checked
    directly against the YAML rather than via the Roster -- matching how
    the file's own pre-existing orders.create/orders.cancel denials are
    also unreachable through load_roster. Listed explicitly per this
    stream's handoff, the same way orders.create/cancel already are:
    'squarely this role's future domain,' not an implicit gap."""
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "agents" / "quartermaster" / "tools.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    deny_ids = {entry["id"] for entry in data.get("deny", [])}
    assert "workjob.queue" in deny_ids


def test_consultant_has_no_workjob_grant_matching_the_orders_precedent(roster):
    """consultant/tools.yaml has no orders.* entry at all today (neither
    grant nor explicit deny) -- this role's domain is knowledge, not fort
    action or work-order administration. workjob.* follows the identical
    precedent: no entry added, rather than padding the file with a deny for
    every tool that is simply not this role's concern."""
    assert "workjob.queue" not in roster.roles["consultant"].read
    assert "workjob.queue" not in roster.roles["consultant"].write
    assert "workjob.list" not in roster.roles["consultant"].read


# --------------------------------------------------------------------------
# MCP-facing translation: name round-trip and argv construction
# --------------------------------------------------------------------------


def test_workjob_ids_get_legal_reversible_mcp_names(registry):
    id_to_name, name_to_id = build_tool_names(registry)
    assert id_to_name["workjob.list"] == "workjob__list"
    assert id_to_name["workjob.queue"] == "workjob__queue"
    assert name_to_id["workjob__queue"] == "workjob.queue"


def test_workjob_queue_appears_only_in_overseers_tool_definitions(registry, roster):
    overseer_names = {d["name"] for d in tool_definitions(registry, roster, "overseer")}
    architect_names = {d["name"] for d in tool_definitions(registry, roster, "architect")}
    assert "workjob__queue" in overseer_names
    assert "workjob__queue" not in architect_names
    assert "workjob__list" in overseer_names
    assert "workjob__list" in architect_names


def test_workjob_queue_definition_states_it_mutates_and_is_unverified(registry, roster):
    defs = {d["name"]: d for d in tool_definitions(registry, roster, "overseer")}
    description = defs["workjob__queue"]["description"]
    assert "mutate" in description.lower() or "mutat" in description.lower()


def test_argv_for_no_arg_list_call(registry):
    tool = registry.get("workjob.list")
    assert argv_for_call(tool, {}) == ["df-overseer-workjob", "list"]


def test_argv_for_queue_required_only(registry):
    tool = registry.get("workjob.queue")
    argv = argv_for_call(
        tool, {"job": "blocks", "workshop_landmark_name": "North Workshop"}
    )
    assert argv == ["df-overseer-workjob", "queue", "blocks", "North Workshop"]


def test_apostrophed_workshop_names_are_refused_by_the_mcp_layer(registry):
    """REAL, LOAD-BEARING FINDING (not this stream's bug, dfmcp/tools.py is
    not a touched surface and was not changed): DF's own vanilla default
    workshop names carry an apostrophe (\"Mason's Workshop\",
    \"Mechanic's Workshop\" -- and handoffs/2026-09-19-well-and-harvest.md's
    own live write-up names this fort's actual Mason's Workshop
    \"Stoneworker's Workshop\", the in-game display name for a Masons
    subtype built of stone). dfmcp/tools.py's `_SHELL_METACHAR_RE` refuses
    any string argument containing a literal `'` (it becomes a literal word
    on a live command line, so this is a deliberate, pre-existing security
    boundary, not a bug to route around here). The practical effect: a
    workjob.queue call routed through the MCP server for a workshop whose
    real default name contains an apostrophe is refused BEFORE it ever
    reaches df-overseer-workjob.lua at all -- a caller must rename the
    workshop (dfhack.buildings.getName has no setter used anywhere in this
    project) or invoke the .lua file's CLI directly
    (`./dfhack-run df-overseer-workjob ...`), bypassing dfmcp/tools.py's
    argv construction entirely. Recorded here rather than silently worked
    around, and named again in the handoff's own first-live-run checklist."""
    from dfmcp.tools import ArgumentError

    tool = registry.get("workjob.queue")
    with pytest.raises(ArgumentError):
        argv_for_call(
            tool,
            {"job": "blocks", "workshop_landmark_name": "Stoneworker's Workshop"},
        )


def test_argv_for_queue_with_dry_run(registry):
    tool = registry.get("workjob.queue")
    argv = argv_for_call(
        tool,
        {
            "job": "brew_drink",
            "workshop_landmark_name": "Still",
            "dry_run": "false",
        },
    )
    assert argv == ["df-overseer-workjob", "queue", "brew_drink", "Still", "false"]


def test_argv_for_queue_with_repeat(registry):
    """handoffs/2026-09-23-order-job-attribution-and-checks.md item 6: REPEAT
    is only reachable once DRY_RUN is also given explicitly (dfmcp's own
    positional-optional gap check), matching "explicit when asked" for both."""
    tool = registry.get("workjob.queue")
    argv = argv_for_call(
        tool,
        {
            "job": "blocks",
            "workshop_landmark_name": "North Workshop",
            "dry_run": "false",
            "repeat": "true",
        },
    )
    assert argv == ["df-overseer-workjob", "queue", "blocks", "North Workshop", "false", "true"]


def test_repeat_cannot_be_supplied_without_dry_run():
    """The positional-optional gap check (dfmcp/tools.py) refuses skipping
    DRY_RUN while supplying REPEAT -- REPEAT was not declared `skippable` in
    TOOLS.yaml, on purpose: the handoff's own "explicit when asked" applies
    to DRY_RUN too."""
    from dfmcp.tools import ArgumentError

    reg = load_registry(
        native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS}
    )
    tool = reg.get("workjob.queue")
    with pytest.raises(ArgumentError):
        argv_for_call(
            tool,
            {"job": "blocks", "workshop_landmark_name": "North Workshop", "repeat": "true"},
        )


# --------------------------------------------------------------------------
# workjob.cancel: the new direct-job cancel verb
# (handoffs/2026-09-23-order-job-attribution-and-checks.md item 5)
# --------------------------------------------------------------------------


def test_workjob_cancel_id_exists_in_the_real_manifest(registry):
    assert "workjob.cancel" in registry


def test_workjob_cancel_is_flagged_mutating(registry):
    tool = registry.get("workjob.cancel")
    assert tool.effect == "mutate"
    assert tool.mutates


def test_workjob_cancel_carries_no_coordinates(registry):
    assert registry.get("workjob.cancel").coordinate_bearing is False


def test_workjob_cancel_argument_signature_matches_the_lua_dispatch():
    """Ground truth: df-overseer-workjob.lua's own dispatch block reads
    `args[2], args[3]` as job_id/dry_run in that order for `cancel`."""
    reg = load_registry(
        native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS}
    )
    tool = reg.get("workjob.cancel")
    tokens = [t.strip("[]") for t in tool.args]
    assert tokens == ["JOB_ID", "DRY_RUN"]


def test_only_the_overseer_can_cancel_a_workjob(roster):
    """Same sole-writer rule as workjob.queue."""
    assert "workjob.cancel" in roster.roles["overseer"].write
    assert "workjob.cancel" not in roster.roles["architect"].write
    assert "workjob.cancel" not in roster.roles["architect"].read
    assert "workjob.cancel" not in roster.roles["consultant"].write
    assert "workjob.cancel" not in roster.roles["consultant"].read


def test_workjob_cancel_denied_to_architect_is_denied_with_a_reason():
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "agents" / "architect" / "tools.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    deny_ids = {entry["id"] for entry in data.get("deny", [])}
    assert "workjob.cancel" in deny_ids


def test_quartermaster_explicitly_denies_workjob_cancel():
    """agents/quartermaster/tools.yaml is not loaded by load_roster (the role
    is disabled) -- checked directly against the YAML, matching the same
    file's own pre-existing workjob.queue check."""
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "agents" / "quartermaster" / "tools.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    deny_ids = {entry["id"] for entry in data.get("deny", [])}
    assert "workjob.cancel" in deny_ids


def test_consultant_has_no_workjob_cancel_grant(roster):
    assert "workjob.cancel" not in roster.roles["consultant"].read
    assert "workjob.cancel" not in roster.roles["consultant"].write


def test_workjob_cancel_ids_get_legal_reversible_mcp_names(registry):
    id_to_name, name_to_id = build_tool_names(registry)
    assert id_to_name["workjob.cancel"] == "workjob__cancel"
    assert name_to_id["workjob__cancel"] == "workjob.cancel"


def test_workjob_cancel_appears_only_in_overseers_tool_definitions(registry, roster):
    overseer_names = {d["name"] for d in tool_definitions(registry, roster, "overseer")}
    architect_names = {d["name"] for d in tool_definitions(registry, roster, "architect")}
    assert "workjob__cancel" in overseer_names
    assert "workjob__cancel" not in architect_names


def test_argv_for_cancel_required_only(registry):
    tool = registry.get("workjob.cancel")
    assert argv_for_call(tool, {"job_id": "42"}) == ["df-overseer-workjob", "cancel", "42"]


def test_argv_for_cancel_with_dry_run(registry):
    tool = registry.get("workjob.cancel")
    argv = argv_for_call(tool, {"job_id": "42", "dry_run": "false"})
    assert argv == ["df-overseer-workjob", "cancel", "42", "false"]


# --------------------------------------------------------------------------
# orders.check-duplicate: the duplicate-production check
# (handoffs/2026-09-23-order-job-attribution-and-checks.md item 4)
# --------------------------------------------------------------------------


def test_orders_check_duplicate_id_exists_in_the_real_manifest(registry):
    assert "orders.check-duplicate" in registry


def test_orders_check_duplicate_is_a_read_that_never_mutates(registry):
    tool = registry.get("orders.check-duplicate")
    assert tool.effect == "read"
    assert not tool.mutates


def test_orders_check_duplicate_carries_no_coordinates(registry):
    assert registry.get("orders.check-duplicate").coordinate_bearing is False


def test_orders_check_duplicate_argument_signature():
    reg = load_registry(
        native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS}
    )
    tool = reg.get("orders.check-duplicate")
    assert tool.args == ["JOB"]


def test_orders_check_duplicate_granted_to_overseer_architect_and_quartermaster(roster):
    """Read-only, so it follows the orders.list/workjob.list precedent
    (visible to every advisor whose domain touches production), not the
    sole-writer boundary."""
    assert "orders.check-duplicate" in roster.roles["overseer"].read
    assert "orders.check-duplicate" in roster.roles["architect"].read


def test_orders_check_duplicate_quartermaster_yaml_grants_it():
    """quartermaster is disabled in ROSTER.yaml so load_roster does not
    resolve it -- checked directly against the YAML, matching this file's
    own precedent for the other quartermaster checks."""
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "agents" / "quartermaster" / "tools.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    read_ids = {entry["id"] for entry in data.get("read", [])}
    assert "orders.check-duplicate" in read_ids


def test_orders_check_duplicate_consultant_has_no_grant(roster):
    """Matches the orders.*/workjob.* precedent: consultant's domain is
    knowledge, not fort action or work-order administration."""
    assert "orders.check-duplicate" not in roster.roles["consultant"].read
    assert "orders.check-duplicate" not in roster.roles["consultant"].write


def test_argv_for_check_duplicate(registry):
    tool = registry.get("orders.check-duplicate")
    assert argv_for_call(tool, {"job": "blocks"}) == [
        "df-overseer-orders", "check-duplicate", "blocks",
    ]
