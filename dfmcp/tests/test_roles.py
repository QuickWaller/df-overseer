"""Role-scoping tests.

This module is the enforced security boundary once the brain and the fort sit on
separate hosts (docs/AGENT-ARCHITECTURE.md §13), so the failing cases matter more
than the happy path. Every strict validation rule gets a test that asserts it
actually raises.

The single most important test here is
`test_advisor_granted_a_mutating_tool_is_refused`, in both its variants: it is
what makes "advisors are read-only" a property of the system rather than a
sentence in a charter.
"""

import textwrap

import pytest
import yaml

from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS
from dfmcp.registry import load_registry
from dfmcp.roles import RoleValidationError, SYSTEM_CLASS_TOOL_IDS, load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS


@pytest.fixture(scope="module")
def registry():
    # native_tools=NATIVE_TOOLS: the real agents/architect/tools.yaml and
    # agents/overseer/tools.yaml now grant real queue.* ids
    # (handoffs/2026-09-15-queue-into-dfmcp.md), which roles.py rule 1
    # requires to exist in the registry -- load_roster(registry) below would
    # otherwise fail to load the real roster for every test in this file.
    # DOCTRINE_NATIVE_TOOLS merged in too, added
    # handoffs/2026-09-19-get-doctrine-tool.md: agents/consultant/tools.yaml
    # now grants doctrine.get, same rule-1 requirement. SERIES_NATIVE_TOOLS
    # merged in too, added handoffs/2026-09-19-series-mcp-tools.md:
    # agents/overseer/tools.yaml and agents/consultant/tools.yaml now grant
    # series.* ids and agents/architect/tools.yaml denies them, same rule-1
    # requirement for the two enabled grantee roles.
    return load_registry(native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS})


# --------------------------------------------------------------------------
# The real roster
# --------------------------------------------------------------------------

def test_real_roster_loads(registry):
    """Fails if anyone edits an allowlist in agents/ into an invalid state."""
    roster = load_roster(registry)
    assert roster.sole_writer == "overseer"
    # "conductor" added handoffs/2026-09-22-loop-clock-conductor-role.md:
    # kind: system, code never an agent -- see the system-kind tests below.
    assert set(roster.roles) == {"overseer", "architect", "consultant", "conductor"}


def test_only_the_sole_writer_has_fort_mutating_write_entries(registry):
    """Updated `handoffs/2026-09-15-queue-into-dfmcp.md`: architect now
    legitimately holds `write` entries too (`queue.propose`/`queue.pass`),
    but only to dfqueue's own ledger, never the fort -- none of them
    `mutates`. `test_no_advisor_holds_a_mutating_tool_by_any_route` below is
    the generic version of this same property; this test pins the specific,
    concrete shape so a future edit that quietly grants architect a
    fort-mutating write is still caught even if that generic sweep were
    ever loosened."""
    roster = load_roster(registry)
    assert roster.roles["overseer"].write
    assert set(roster.roles["architect"].write) == {"queue.propose", "queue.pass"}
    for tool_id in roster.roles["architect"].write:
        assert not registry.get(tool_id).mutates
    assert not roster.roles["consultant"].write


def test_no_advisor_holds_a_mutating_tool_by_any_route(registry):
    """Belt-and-braces over the loader's own rule 2: re-derive it from the
    registry rather than trusting that the loader checked.

    Updated handoffs/2026-09-22-loop-clock-conductor-role.md: a system-class
    tool id (SYSTEM_CLASS_TOOL_IDS) is the one sanctioned exception, and only
    for a role of kind "system" -- checked precisely, not just skipped, so
    this test still catches an ADVISOR quietly picking one up."""
    roster = load_roster(registry)
    for name, perms in roster.roles.items():
        if name == roster.sole_writer:
            continue
        for tool_id in list(perms.read) + list(perms.write):
            if tool_id in SYSTEM_CLASS_TOOL_IDS:
                assert perms.kind == "system", (
                    f"{name} (kind {perms.kind!r}) holds system-class {tool_id}, "
                    "but only a kind: system role may"
                )
                continue
            assert not registry.get(tool_id).mutates, f"{name} holds mutating {tool_id}"


def test_the_overseer_can_act_but_cannot_discover(registry):
    """A structural property of the design, currently expressed only in YAML:
    the Overseer builds and digs but holds no *find* tool, so it depends on the
    Architect to discover candidates. Pinned here so a future allowlist edit
    that quietly grants discovery is a visible decision, not a slip.
    See docs/AGENT-ARCHITECTURE.md §5."""
    roster = load_roster(registry)
    overseer = roster.roles["overseer"]
    assert "openarea.build" in overseer.write
    assert "diggable.dig" in overseer.write
    assert "diggable.dig-stair" in overseer.write
    for discovery in ("openarea.find", "diggable.find", "diggable.find-stair", "chokepoints.find"):
        assert not overseer.allows(discovery), (
            f"the Overseer now holds {discovery}; that removes its dependency on "
            "the Architect and should be a deliberate, recorded decision"
        )
        assert roster.roles["architect"].allows(discovery)


def test_water_and_industry_tools_follow_the_farm_find_pairing(registry):
    """handoffs/2026-09-17-water-and-industry-tools.md: unlike
    openarea.find/diggable.find/chokepoints.find (Architect-only, see the
    test above), zone.find/trees.find/well.find/orders.list follow the
    farm.find/workshop.find precedent instead -- granted to BOTH roles,
    since the Overseer needs to read its own build's own precondition, not
    just act on an Architect's say-so. The four new writes
    (zone.place/trees.fell/well.build/orders.create/orders.cancel) are
    Overseer-only, denied to the Architect exactly like every other write
    in this project."""
    roster = load_roster(registry)
    overseer = roster.roles["overseer"]
    architect = roster.roles["architect"]

    for discovery in ("zone.find", "trees.find", "well.find", "orders.list"):
        assert overseer.allows(discovery), f"overseer should hold {discovery}"
        assert architect.allows(discovery), f"architect should hold {discovery}"

    for write_id in ("zone.place", "trees.fell", "well.build", "orders.create", "orders.cancel"):
        assert write_id in overseer.write, f"overseer should hold write {write_id}"
        assert registry.get(write_id).mutates is True
        assert not architect.allows(write_id), f"architect must not hold {write_id}"


def test_stocks_availability_follows_the_stocks_food_drink_pairing(registry):
    """handoffs/2026-09-19-per-item-flags-tool.md: a read tool, so it
    follows stocks.food-drink/stocks.seeds' existing precedent of being
    granted to BOTH advisory roles (unlike openarea.find/diggable.find,
    which are Architect-only per the test above) -- the Overseer needs to
    read its own build's own precondition (a stalled water/bucket job) just
    as much as the Architect needs it to write a proposal. This stream did
    not touch agents/consultant/tools.yaml (not in its touched surfaces),
    so that role is not asserted here."""
    roster = load_roster(registry)
    overseer = roster.roles["overseer"]
    architect = roster.roles["architect"]

    assert overseer.allows("stocks.availability")
    assert architect.allows("stocks.availability")
    assert registry.get("stocks.availability").mutates is False


# --------------------------------------------------------------------------
# The conductor: kind: system, the SYSTEM_CLASS_TOOL_IDS exception
# (handoffs/2026-09-22-loop-clock-conductor-role.md)
# --------------------------------------------------------------------------


def test_conductor_is_kind_system_and_holds_exactly_the_clock_writes(registry):
    """Pins the concrete shape, same style as
    test_only_the_sole_writer_has_fort_mutating_write_entries above: a future
    edit that quietly grants conductor something beyond the clock/quicksave
    group, or drops kind: system, is a visible test failure, not a slip."""
    roster = load_roster(registry)
    conductor = roster.roles["conductor"]
    assert conductor.kind == "system"
    assert set(conductor.write) == SYSTEM_CLASS_TOOL_IDS
    for tool_id in conductor.write:
        assert registry.get(tool_id).mutates is True
    assert "clock.status" in conductor.read
    assert "vitals.summary" in conductor.read


def test_overseer_holds_no_system_class_tool_despite_being_sole_writer(registry):
    """THE central invariant this exception exists to protect: the Overseer
    is the sole_writer, which would ordinarily let it hold any mutating
    tool, but SYSTEM_CLASS_TOOL_IDS has no sole_writer carve-out. Pinned
    directly rather than only via the generic sweep above, since this is the
    one property the whole exception was built to guarantee (docs/AGENT-LOOP.md:
    "the Overseer's charter line 'never unpause' is unchanged")."""
    roster = load_roster(registry)
    overseer = roster.roles["overseer"]
    assert overseer.kind == "actor"
    for tool_id in SYSTEM_CLASS_TOOL_IDS:
        assert not overseer.allows(tool_id), f"overseer must not hold {tool_id}"
    assert not overseer.allows("clock.resume")


def test_advisors_hold_no_system_class_tool(registry):
    roster = load_roster(registry)
    for name in ("architect", "consultant"):
        role = roster.roles[name]
        for tool_id in SYSTEM_CLASS_TOOL_IDS:
            assert not role.allows(tool_id), f"{name} must not hold {tool_id}"


def test_rule_system_class_tool_granted_to_a_non_system_role_refuses_to_load(registry, tmp_path):
    """The loader's own check, not just the belt-and-braces sweep above:
    an advisor granted a system-class tool must fail to LOAD."""
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        architect:
          enabled: true
          dir: architect
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    _role_dir(agents, "architect", """
        write:
          - id: "clock.pause"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    msg = str(exc.value)
    assert "architect" in msg and "clock.pause" in msg and "system" in msg


def test_rule_system_class_tool_granted_to_the_sole_writer_also_refuses_to_load(registry, tmp_path):
    """THE property the exception exists for: even the sole_writer (kind:
    actor here, not system) cannot be granted clock.resume. No carve-out."""
    agents = _roster(tmp_path, BASIC_ROLES)  # overseer, kind: actor, sole_writer
    _role_dir(agents, "overseer", """
        read:
          - id: "overview.get"
        write:
          - id: "clock.resume"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    msg = str(exc.value)
    assert "overseer" in msg and "clock.resume" in msg and "system" in msg


def test_rule_system_class_tool_granted_to_a_system_kind_role_loads_fine(registry, tmp_path):
    """The positive case: a role explicitly marked kind: system may hold one."""
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        conductor:
          enabled: true
          dir: conductor
          kind: system
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    _role_dir(agents, "conductor", """
        write:
          - id: "clock.pause"
          - id: "clock.resume"
        """)
    roster = load_roster(registry, agents_dir=agents)
    assert "clock.resume" in roster.roles["conductor"].write


def test_check_returns_legible_reasons(registry):
    roster = load_roster(registry)

    ok, why = roster.check("architect", "openarea.find")
    assert ok and "granted" in why

    ok, why = roster.check("architect", "openarea.build")
    assert not ok
    assert "propose" in why.lower()

    ok, why = roster.check("architect", "ui.click")
    assert not ok

    ok, why = roster.check("nobody", "overview.get")
    assert not ok and "not an enabled role" in why


def test_wildcard_deny_covers_every_command_of_a_script(registry):
    roster = load_roster(registry)
    for tool_id in registry.ids_for_script("ui"):
        ok, _ = roster.check("overseer", tool_id)
        assert not ok, f"the UI path must stay denied, but {tool_id} was allowed"


# --------------------------------------------------------------------------
# Strict validation rules, each with a failing case
# --------------------------------------------------------------------------

def _roster(tmp_path, roles_yaml, sole_writer="overseer"):
    """Build a throwaway agents/ dir. Emits ROSTER.yaml via safe_dump rather
    than by string indentation, which is easy to get subtly wrong."""
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    doc = {
        "schema_version": 1,
        "sole_writer": sole_writer,
        "roles": yaml.safe_load(textwrap.dedent(roles_yaml)) or {},
    }
    (agents / "ROSTER.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return agents


def _role_dir(agents, name, tools_yaml, *, model=True, role_md=True, tools=True):
    d = agents / name
    d.mkdir(parents=True, exist_ok=True)
    if role_md:
        (d / "role.md").write_text(f"# {name}\n", encoding="utf-8")
    if model:
        (d / "model.yaml").write_text("model: anthropic/claude-sonnet-5\n", encoding="utf-8")
    if tools:
        (d / "tools.yaml").write_text(textwrap.dedent(tools_yaml), encoding="utf-8")
    return d


BASIC_ROLES = """
overseer:
  enabled: true
  dir: overseer
  kind: actor
"""


def test_rule1_unknown_tool_id_refuses_to_load(registry, tmp_path):
    """A typo must not silently grant nothing."""
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", """
        read:
          - id: "overview.gett"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "overview.gett" in str(exc.value)


def test_rule2_advisor_granted_a_mutating_tool_is_refused_under_write(registry, tmp_path):
    """THE central invariant: advisors are read-only."""
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        architect:
          enabled: true
          dir: architect
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    _role_dir(agents, "architect", """
        write:
          - id: "openarea.build"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    msg = str(exc.value)
    assert "architect" in msg and "openarea.build" in msg


def test_rule2_also_catches_a_mutating_tool_hidden_under_read(registry, tmp_path):
    """The likelier mistake: filing a write tool under `read` by accident.
    Caught by checking the registry's own mutates flag, not the section name."""
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        architect:
          enabled: true
          dir: architect
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    _role_dir(agents, "architect", """
        read:
          - id: "diggable.dig"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "diggable.dig" in str(exc.value)


def test_rule3_allow_and_deny_conflict_refuses(registry, tmp_path):
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", """
        read:
          - id: "overview.get"
        deny:
          - id: "overview.get"
            reason: contradictory
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "overview.get" in str(exc.value)


def test_rule3_conflict_detection_is_wildcard_aware(registry, tmp_path):
    """Denying `ui.*` while allowing `ui.click` is a conflict even though the
    two strings differ, which a naive set intersection would miss."""
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", """
        read:
          - id: "ui.click"
        deny:
          - id: "ui.*"
            reason: embark bootstrap only
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "ui.click" in str(exc.value)


def test_rule4_enabled_role_with_no_directory_refuses(registry, tmp_path):
    agents = _roster(tmp_path, BASIC_ROLES)   # no role dir created at all
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "overseer" in str(exc.value)


def test_rule5_enabled_role_missing_model_yaml_refuses(registry, tmp_path):
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n", model=False)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "model.yaml" in str(exc.value)


def test_rule5_enabled_role_missing_tools_yaml_refuses(registry, tmp_path):
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", "", tools=False)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "tools.yaml" in str(exc.value)


def test_disabled_role_with_no_tools_yaml_is_fine(registry, tmp_path):
    """The three unenabled roles deliberately have charters and no tools.yaml.
    That must not be an error, or the real roster could never load."""
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        marshal:
          enabled: false
          dir: marshal
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    (agents / "marshal").mkdir()
    (agents / "marshal" / "role.md").write_text("# marshal\n", encoding="utf-8")

    roster = load_roster(registry, agents_dir=agents)
    assert "marshal" not in roster.roles


def test_rule6_sole_writer_only_tool_granted_to_non_sole_writer_refuses_to_load(registry, tmp_path):
    """New rule, `handoffs/2026-09-15-queue-into-dfmcp.md`: queue.rule may
    only be granted to the roster's sole_writer, independent of `mutates`
    (queue.rule does not mutate fort state -- Tool.mutates stays "mutates
    fort state" only -- so rule 2 would not catch this on its own)."""
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        architect:
          enabled: true
          dir: architect
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    _role_dir(agents, "architect", """
        write:
          - id: "queue.rule"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    msg = str(exc.value)
    assert "architect" in msg and "queue.rule" in msg


def test_rule6_also_catches_the_sole_writer_only_tool_hidden_under_read(registry, tmp_path):
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        architect:
          enabled: true
          dir: architect
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"overview.get\"\n")
    _role_dir(agents, "architect", """
        read:
          - id: "queue.rule"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(registry, agents_dir=agents)
    assert "queue.rule" in str(exc.value)


def test_rule6_sole_writer_may_hold_the_sole_writer_only_tool(registry, tmp_path):
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", """
        write:
          - id: "queue.rule"
        """)
    roster = load_roster(registry, agents_dir=agents)
    assert "queue.rule" in roster.roles["overseer"].write


def _registry_with_omniscient_tool(tmp_path):
    """A throwaway registry with one omniscient tool alongside a real
    tool, for rule 7's tests -- the real manifest has none by design
    (test_registry.py's test_no_real_tool_is_tagged_omniscient), so rule 7
    needs a synthetic fixture to exercise at all."""
    tools_yaml = tmp_path / "TOOLS.yaml"
    tools_yaml.write_text(textwrap.dedent("""
        df-overseer-safe.lua:
          commands:
            "get NAME":
              lua_function: get_safe
              effect: read
              knowledge_scope: player_visible
        df-overseer-leaky.lua:
          commands:
            "scan":
              lua_function: scan_leaky
              effect: read
              knowledge_scope: omniscient
        """), encoding="utf-8")
    return load_registry(tools_yaml)


def test_rule7_omniscient_tool_granted_to_an_advisor_refuses_to_load(tmp_path):
    reg = _registry_with_omniscient_tool(tmp_path)
    agents = _roster(tmp_path, """
        overseer:
          enabled: true
          dir: overseer
          kind: actor
        architect:
          enabled: true
          dir: architect
          kind: advisor
        """)
    _role_dir(agents, "overseer", "read:\n  - id: \"safe.get\"\n")
    _role_dir(agents, "architect", """
        read:
          - id: "leaky.scan"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(reg, agents_dir=agents)
    msg = str(exc.value)
    assert "architect" in msg and "leaky.scan" in msg and "omniscient" in msg


def test_rule7_omniscient_tool_granted_to_the_sole_writer_also_refuses_to_load(tmp_path):
    """Unlike rule 2 (mutation), rule 7 has no sole-writer exception: an
    omniscient tool has no legitimate holder at all, not even the sole
    writer."""
    reg = _registry_with_omniscient_tool(tmp_path)
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", """
        read:
          - id: "safe.get"
          - id: "leaky.scan"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(reg, agents_dir=agents)
    msg = str(exc.value)
    assert "overseer" in msg and "leaky.scan" in msg and "omniscient" in msg


def test_rule7_omniscient_tool_granted_under_write_also_refuses_to_load(tmp_path):
    reg = _registry_with_omniscient_tool(tmp_path)
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", """
        write:
          - id: "leaky.scan"
        """)
    with pytest.raises(RoleValidationError) as exc:
        load_roster(reg, agents_dir=agents)
    assert "leaky.scan" in str(exc.value)


def test_rule7_a_non_omniscient_tool_loads_fine(tmp_path):
    """The negative case: rule 7 must not false-positive on player_visible/
    player_derivable tools."""
    reg = _registry_with_omniscient_tool(tmp_path)
    agents = _roster(tmp_path, BASIC_ROLES)
    _role_dir(agents, "overseer", "read:\n  - id: \"safe.get\"\n")
    roster = load_roster(reg, agents_dir=agents)
    assert "safe.get" in roster.roles["overseer"].read


def test_no_role_in_the_real_roster_holds_an_omniscient_tool(registry):
    """Belt-and-braces over the loader's own rule 7: re-derive it from the
    real roster and registry rather than trusting that the loader checked,
    matching this file's own style for rule 2's equivalent test."""
    roster = load_roster(registry)
    for name, perms in roster.roles.items():
        for tool_id in list(perms.read) + list(perms.write):
            tool = registry.get(tool_id)
            assert not getattr(tool, "knowledge_scope", None) == "omniscient", (
                f"{name} holds omniscient {tool_id}"
            )


def test_missing_sole_writer_refuses(registry, tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "ROSTER.yaml").write_text("schema_version: 1\nroles: {}\n", encoding="utf-8")
    with pytest.raises(RoleValidationError):
        load_roster(registry, agents_dir=agents)
