"""Loads agents/ROSTER.yaml and each enabled role's tools.yaml, resolves both
against the tool registry, and answers the one question this package
exists for: given a role and a canonical tool id, is the call allowed, and
why or why not.

This is the enforced boundary (docs/AGENT-ARCHITECTURE.md principle 8: "a
role is defined by its tool allowlist"), so every validation rule below is
a hard load-time error, never a warning. A role file that fails one of
these checks must refuse to load, not load with a quietly wrong permission
set.

Nothing here calls DFHack, opens a socket, or knows what SSH is. See
mcp/README.md for what this package deliberately does not do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from .registry import Registry

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AGENTS_DIR = REPO_ROOT / "agents"


class RoleValidationError(Exception):
    """A role's ROSTER.yaml entry or tools.yaml failed a strict validation rule.

    Always a hard load-time failure. See mcp/README.md's "Strict validation"
    section for the full list of rules this raises for.
    """


@dataclass(frozen=True)
class RoleTool:
    """One entry from a role's read/write/deny/planned list, metadata preserved."""

    id: str
    status: Optional[str] = None
    note: Optional[str] = None
    reason: Optional[str] = None
    hazard: Optional[str] = None
    reliability: Optional[str] = None


@dataclass(frozen=True)
class RolePermissions:
    """The resolved, concrete permission set for one enabled role."""

    role: str
    kind: str                          # "actor" or "advisor", from ROSTER.yaml
    is_sole_writer: bool
    read: Dict[str, RoleTool] = field(default_factory=dict)
    write: Dict[str, RoleTool] = field(default_factory=dict)
    deny: List[RoleTool] = field(default_factory=list)
    planned: List[RoleTool] = field(default_factory=list)

    def allows(self, tool_id: str) -> bool:
        return tool_id in self.read or tool_id in self.write

    def deny_entry(self, tool_id: str) -> Optional[RoleTool]:
        """The deny entry matching `tool_id`, exact or wildcard, if any."""
        for entry in self.deny:
            if _deny_matches(entry.id, tool_id):
                return entry
        return None


class Roster:
    """The resolved roster: which roles are enabled, and what each may call."""

    def __init__(self, registry: Registry, sole_writer: str, roles: Dict[str, RolePermissions]):
        self.registry = registry
        self.sole_writer = sole_writer
        self.roles = roles

    def check(self, role: str, tool_id: str) -> Tuple[bool, str]:
        """Allowed or denied, plus a reason string fit to hand back to an agent."""
        perms = self.roles.get(role)
        if perms is None:
            return False, f"'{role}' is not an enabled role on this roster."

        deny_entry = perms.deny_entry(tool_id)
        if deny_entry is not None:
            reason = deny_entry.reason or "explicitly denied for this role"
            return False, reason.strip()

        if tool_id in perms.write:
            return True, "granted: write"
        if tool_id in perms.read:
            return True, "granted: read"

        if perms.kind == "advisor":
            return False, (
                f"'{tool_id}' is not on {role}'s allowlist. Advisors do not act; propose it instead."
            )
        return False, f"'{tool_id}' is not on {role}'s allowlist."


def _deny_matches(pattern: str, tool_id: str) -> bool:
    """"ui.*" matches any id starting with "ui.". Anything else is an exact match."""
    if pattern.endswith(".*"):
        return tool_id.startswith(pattern[:-1])
    return pattern == tool_id


def _role_tool_from_entry(entry: dict) -> RoleTool:
    if not isinstance(entry, dict):
        raise RoleValidationError(f"expected a mapping for a tool entry, got {entry!r}")
    return RoleTool(
        id=entry.get("id", ""),
        status=entry.get("status"),
        note=entry.get("note"),
        reason=entry.get("reason"),
        hazard=entry.get("hazard"),
        reliability=entry.get("reliability"),
    )


def _index_allow(role_name: str, section: str, entries: list, registry: Registry) -> Dict[str, RoleTool]:
    """Index a read/write list by id, refusing any id absent from the registry.

    Rule 1 (mcp/README.md): an allowlist referencing a tool id that does not
    exist in the registry is a hard error. A typo here must never silently
    grant nothing.
    """
    indexed: Dict[str, RoleTool] = {}
    for entry in entries:
        role_tool = _role_tool_from_entry(entry)
        if not role_tool.id:
            raise RoleValidationError(f"'{role_name}' has a {section} entry with no id: {entry!r}")
        if role_tool.id not in registry:
            raise RoleValidationError(
                f"'{role_name}' {section}-lists '{role_tool.id}', which does not exist in "
                "scripts/dfhack/TOOLS.yaml. A typo here must not silently grant nothing."
            )
        indexed[role_tool.id] = role_tool
    return indexed


def _load_role_permissions(
    role_name: str,
    kind: str,
    tools_yaml_path: Path,
    registry: Registry,
    sole_writer: str,
) -> RolePermissions:
    with tools_yaml_path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}

    def section(name: str) -> list:
        raw = doc.get(name) or []
        if not isinstance(raw, list):
            raise RoleValidationError(f"'{role_name}' tools.yaml: {name!r} must be a list, got {type(raw).__name__}")
        return raw

    read = _index_allow(role_name, "read", section("read"), registry)
    write = _index_allow(role_name, "write", section("write"), registry)

    # Rule 2: a role other than the sole writer may not be granted (via
    # read OR write) any tool the registry marks as mutating. Checked per
    # id against the registry's own `mutates` flag, so a mutating tool
    # placed under `read` by mistake is caught too, not only one under
    # `write`. This is the roster's single most important invariant:
    # advisors are read-only.
    if role_name != sole_writer:
        for section_name, granted in (("read", read), ("write", write)):
            for tool_id in granted:
                tool = registry.get(tool_id)
                if tool.mutates:
                    raise RoleValidationError(
                        f"'{role_name}' is granted '{tool_id}' under {section_name}, and it mutates "
                        f"fort state, but the roster's sole_writer is '{sole_writer}', not "
                        f"'{role_name}'. Advisors are read-only."
                    )

    deny_raw = section("deny")
    deny = [_role_tool_from_entry(e) for e in deny_raw]
    for d in deny:
        if not d.id:
            raise RoleValidationError(f"'{role_name}' has a deny entry with no id: {d!r}")

    # Rule 3: an id may not appear in both an allow list and the deny list,
    # wildcard-aware. A role that denies "ui.*" and allows "ui.click"
    # conflicts even though the two strings differ.
    allow_ids = sorted(set(read) | set(write))
    conflicts = [tid for tid in allow_ids if any(_deny_matches(d.id, tid) for d in deny)]
    if conflicts:
        raise RoleValidationError(
            f"'{role_name}' both allows and denies the same tool id(s): {', '.join(conflicts)}"
        )

    # `planned` entries name capabilities that do not exist in the registry
    # by design (the queue, the sentry endpoint, a future knowledge tool).
    # They are parsed and preserved but never checked against the registry:
    # see mcp/README.md.
    planned = [_role_tool_from_entry(e) for e in section("planned")]

    return RolePermissions(
        role=role_name,
        kind=kind,
        is_sole_writer=(role_name == sole_writer),
        read=read,
        write=write,
        deny=deny,
        planned=planned,
    )


def load_roster(registry: Registry, agents_dir=DEFAULT_AGENTS_DIR) -> Roster:
    """Load agents/ROSTER.yaml and every enabled role's tools.yaml.

    Raises RoleValidationError for any of the strict validation rules in
    mcp/README.md. Disabled roles are parsed only far enough to be skipped;
    a disabled role missing its tools.yaml (the three that deliberately
    have none) is not an error.
    """
    agents_dir = Path(agents_dir)
    roster_path = agents_dir / "ROSTER.yaml"
    with roster_path.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}

    sole_writer = manifest.get("sole_writer")
    if not sole_writer:
        raise RoleValidationError(f"{roster_path}: no sole_writer set")

    roles_section = manifest.get("roles") or {}
    roles: Dict[str, RolePermissions] = {}

    for role_name, role_entry in roles_section.items():
        if not isinstance(role_entry, dict) or not role_entry.get("enabled"):
            continue

        role_dir = agents_dir / role_entry.get("dir", role_name)
        role_md = role_dir / "role.md"
        # Rule 4: ROSTER.yaml naming an enabled role whose directory or
        # role.md is missing is a hard error.
        if not role_dir.is_dir() or not role_md.is_file():
            raise RoleValidationError(
                f"ROSTER.yaml enables '{role_name}' but {role_dir} or its role.md is missing"
            )

        tools_yaml_path = role_dir / "tools.yaml"
        model_yaml_path = role_dir / "model.yaml"
        # Rule 5: an enabled role's tools.yaml or model.yaml being absent is
        # a hard error. Distinct from rule 4: a role can have a charter
        # (role.md) and still be missing the files that make it runnable.
        if not tools_yaml_path.is_file():
            raise RoleValidationError(f"enabled role '{role_name}' has no tools.yaml at {tools_yaml_path}")
        if not model_yaml_path.is_file():
            raise RoleValidationError(f"enabled role '{role_name}' has no model.yaml at {model_yaml_path}")

        kind = role_entry.get("kind", "advisor")
        roles[role_name] = _load_role_permissions(role_name, kind, tools_yaml_path, registry, sole_writer)

    return Roster(registry=registry, sole_writer=sole_writer, roles=roles)
