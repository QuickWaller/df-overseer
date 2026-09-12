"""Loads and validates scripts/dfhack/TOOLS.yaml into an in-memory registry.

This is the "what tools exist and what do they do" half of the MCP seam
(see mcp/README.md). It knows nothing about roles, agents, or which caller
may use which tool; that boundary lives in roles.py. It also does not call
DFHack, open a socket, or touch a VM: it is a pure read of a YAML file
already in this repo.

Canonical id scheme (full rationale in mcp/README.md): strip the script's
`df-overseer-` prefix and `.lua` suffix for a short script name, take the
leading verb of the command signature (up to the first whitespace or `(`,
lowercased), and join the two with a dot: `openarea.build`, `overview.get`,
`labor.set-labor`. Two commands normalising to the same id is a hard error
at load time, never a silent overwrite.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOOLS_YAML = REPO_ROOT / "scripts" / "dfhack" / "TOOLS.yaml"

_SCRIPT_PREFIX = "df-overseer-"
_SCRIPT_SUFFIX = ".lua"

# A leading verb is a run of letters, digits, underscores or hyphens that
# starts with a letter: "unit-status", "check-units", "since-report" all
# need to survive whole, since the hyphen is part of the verb, not a
# separator between two tokens.
_VERB_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)")

_VALID_EFFECTS = ("read", "mutate")


class RegistryError(Exception):
    """A structural problem in TOOLS.yaml itself.

    Always a hard load-time failure. A registry that loaded despite a bad
    command signature, an unrecognised `effect`, or a canonical-id collision
    would be a registry that quietly hides the exact mistakes this module
    exists to catch.
    """


@dataclass(frozen=True)
class Tool:
    """One DFHack command, as described by TOOLS.yaml, under its canonical id."""

    id: str
    script: str                      # raw filename, e.g. "df-overseer-openarea.lua"
    command: str                     # raw signature, kept verbatim
    lua_function: str
    effect: str                      # "read" or "mutate"
    coordinate_bearing: Any          # False / True / "internal-only", as written
    live_deployed: bool
    verified: str                    # the manifest's raw string, "unverified" included
    notes: Optional[str] = None
    args: list = field(default_factory=list)
    build_order_item: Any = None

    @property
    def mutates(self) -> bool:
        return self.effect == "mutate"

    @property
    def is_verified(self) -> bool:
        """False unless the manifest states something other than "unverified".

        Deliberately conservative in both directions: a missing `verified`
        field is treated the same as an explicit "unverified", never as a
        clean pass. Never launder an unverified tool into looking verified
        (CLAUDE.md's "mark verified vs proposed" rule).
        """
        if not self.verified:
            return False
        return self.verified.strip().lower() != "unverified"

    @property
    def description(self) -> str:
        """Human description. TOOLS.yaml has no dedicated `description`
        field; `notes` is the closest analogue (the manifest's own header
        says notes carry "the honest caveats"), so it is reused here rather
        than inventing a second field that could drift out of sync with it.
        """
        return self.notes or ""


class Registry:
    """An in-memory, load-once table of tools, keyed by canonical id."""

    def __init__(self, tools: dict):
        self._tools = tools

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def get(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError:
            raise KeyError(f"no such tool id in the registry: {tool_id!r}") from None

    def all(self) -> list:
        return list(self._tools.values())

    def ids(self) -> list:
        return list(self._tools.keys())

    def ids_for_script(self, script_short: str) -> list:
        """Every canonical id whose script prefix matches `script_short`.

        Used for expanding a wildcard deny pattern like "ui.*" into its
        concrete ids, and for tests that assert wildcard coverage.
        """
        prefix = f"{script_short}."
        return [tid for tid in self._tools if tid.startswith(prefix)]


def _script_short_name(filename: str) -> str:
    """"df-overseer-openarea.lua" -> "openarea"."""
    name = filename
    if name.endswith(_SCRIPT_SUFFIX):
        name = name[: -len(_SCRIPT_SUFFIX)]
    if name.startswith(_SCRIPT_PREFIX):
        name = name[len(_SCRIPT_PREFIX):]
    return name


def _leading_verb(command_signature: str) -> str:
    match = _VERB_RE.match(command_signature.strip())
    if not match:
        raise RegistryError(
            f"cannot derive a leading verb from command signature {command_signature!r}"
        )
    return match.group(1).lower()


def _parse_args(command_signature: str, verb: str) -> list:
    """A light tokenisation of the signature's trailing arguments.

    Not a full grammar: this repo's signatures are simple enough that
    whitespace-splitting the text after the verb is enough to answer "what
    arguments does this take", which is all the registry promises. A
    parenthetical like "(or no args)" is descriptive text, not a real
    argument, and is treated as an empty argument list.
    """
    rest = command_signature.strip()[len(verb):].strip()
    if not rest or rest.startswith("("):
        return []
    return rest.split()


def load_registry(path=DEFAULT_TOOLS_YAML) -> Registry:
    """Load and validate scripts/dfhack/TOOLS.yaml.

    Raises RegistryError for any structural problem: a command signature no
    verb can be extracted from, an `effect` that is not read/mutate, or two
    commands normalising to the same canonical id.
    """
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)

    if not isinstance(manifest, dict):
        raise RegistryError(f"{path}: expected a mapping at the top level, got {type(manifest).__name__}")

    tools: dict = {}
    # canonical id -> list of "script: command" strings that produced it.
    # More than one entry per id is the collision this module must refuse.
    seen: dict = defaultdict(list)

    for script_name, script_body in manifest.items():
        if not isinstance(script_body, dict) or "commands" not in script_body:
            # Trailing comment-only or metadata-only top-level keys, if any
            # ever appear, are not a script block and carry no commands.
            continue

        script_short = _script_short_name(script_name)
        build_order_item = script_body.get("build_order_item")
        commands = script_body.get("commands") or {}

        for command_sig, spec in commands.items():
            if not isinstance(spec, dict):
                raise RegistryError(
                    f"{script_name} {command_sig!r}: command spec must be a mapping, got {type(spec).__name__}"
                )

            verb = _leading_verb(command_sig)
            tool_id = f"{script_short}.{verb}"
            seen[tool_id].append(f"{script_name}: {command_sig}")

            effect = spec.get("effect")
            if effect not in _VALID_EFFECTS:
                raise RegistryError(
                    f"{script_name} {command_sig!r}: effect must be one of {_VALID_EFFECTS}, got {effect!r}"
                )

            lua_function = spec.get("lua_function")
            if not lua_function:
                raise RegistryError(f"{script_name} {command_sig!r}: missing lua_function")

            tools[tool_id] = Tool(
                id=tool_id,
                script=script_name,
                command=command_sig,
                lua_function=lua_function,
                effect=effect,
                coordinate_bearing=spec.get("coordinate_bearing"),
                live_deployed=bool(spec.get("live_deployed", False)),
                verified=str(spec.get("verified", "unverified")),
                notes=spec.get("notes"),
                args=_parse_args(command_sig, verb),
                build_order_item=build_order_item,
            )

    collisions = {tid: sigs for tid, sigs in seen.items() if len(sigs) > 1}
    if collisions:
        detail = "; ".join(
            f"{tid!r} <- {', '.join(sigs)}" for tid, sigs in sorted(collisions.items())
        )
        raise RegistryError(
            f"canonical id collision(s) in {path}, refusing to load: {detail}"
        )

    if not tools:
        raise RegistryError(f"{path}: no tools parsed; manifest is empty or malformed")

    return Registry(tools)
