"""The confidence file: `gotchas/confidence.yaml` (tool id, optionally kind,
to a level), and its loader.

Design: `docs/BUILDING-TOOL.md`, "Confidence per tool and kind". A level is
confidence that a tool works **and** that it is intuitive for an agent to use.
It is a **static setting** with no mechanism to raise it: this module only
reads a file we edit. There is no write path here and none anywhere else.

The loader refuses, at load time and never silently: an unknown level, an
unknown key, a malformed entry, and (through `validate_against`) a tool id
that is not in the registry, because a typo'd id would otherwise leave a tool
quietly at the default while looking configured.

A **missing** file is also an error, not "everything is medium": the default
is written inside the file, so the file is required. Same reasoning as
`dfmcp/doctrine_tools.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIDENCE_PATH = REPO_ROOT / "gotchas" / "confidence.yaml"

LEVEL_FULL = "full"
LEVEL_MEDIUM = "medium"
LEVEL_LOW = "low"
LEVELS = (LEVEL_FULL, LEVEL_MEDIUM, LEVEL_LOW)

#: The few-word reminder each result carries with its level. A per-entry
#: `note` in the YAML overrides it.
DEFAULT_NOTES: Dict[str, str] = {
    LEVEL_FULL: "works and is intuitive: just use it",
    LEVEL_MEDIUM: "read the description closely, check the gotchas, watch the result",
    LEVEL_LOW: "untested or unintuitive: dry-run first, check every step",
}

_TOP_KEYS = {"default", "tools"}
_ENTRY_KEYS = {"level", "note", "kinds"}
_KIND_KEYS = {"level", "note"}


class ConfidenceError(Exception):
    """`gotchas/confidence.yaml` is absent, unreadable or invalid."""


@dataclass(frozen=True)
class Confidence:
    level: str
    note: str
    #: "kind", "tool" or "default": which entry decided the level.
    source: str


def _entry(where: str, raw: Any, allowed: set, default_level: Optional[str]) -> Dict[str, Any]:
    if isinstance(raw, str):
        raw = {"level": raw}
    if not isinstance(raw, dict):
        raise ConfidenceError(f"{where}: expected a level or a mapping, got {type(raw).__name__}")
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfidenceError(f"{where}: unknown key(s) {unknown}; allowed {sorted(allowed)}")
    level = raw.get("level", default_level)
    if level not in LEVELS:
        raise ConfidenceError(f"{where}: level {level!r} is not one of {list(LEVELS)}")
    note = raw.get("note")
    if note is not None and (not isinstance(note, str) or not note.strip() or len(note) > 120):
        raise ConfidenceError(f"{where}: note must be a non-empty string of at most 120 chars")
    return {"level": level, "note": note, "kinds": raw.get("kinds")}


class ConfidenceConfig:
    def __init__(self, default: Dict[str, Any], tools: Dict[str, Dict[str, Any]]):
        self._default = default
        self._tools = tools

    @property
    def tool_ids(self):
        return sorted(self._tools)

    def lookup(self, tool_id: str, kind: Optional[str] = None) -> Confidence:
        """The level for a tool, and for a kind of it when one is given. A
        kind with no entry inherits the tool's level; a tool with no entry
        gets the default. Never raises for an unknown id (an id outside the
        file is simply at the default); `validate_against` is where a typo is
        caught."""
        entry = self._tools.get(tool_id)
        if entry is None:
            level, note, source = self._default["level"], self._default["note"], "default"
        else:
            level, note, source = entry["level"], entry["note"], "tool"
            if kind is not None and kind in entry["kinds"]:
                k = entry["kinds"][kind]
                level, note, source = k["level"], k["note"], "kind"
        return Confidence(level=level, note=note or DEFAULT_NOTES[level], source=source)

    def validate_against(self, tool_ids: Iterable[str]) -> None:
        known = set(tool_ids)
        unknown = sorted(set(self._tools) - known)
        if unknown:
            raise ConfidenceError(
                f"confidence file names tool id(s) not in the registry: {unknown}"
            )


def parse_confidence(data: Any, source: str = "confidence") -> ConfidenceConfig:
    if not isinstance(data, dict):
        raise ConfidenceError(f"{source}: expected a mapping at the top level")
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise ConfidenceError(f"{source}: unknown top-level key(s) {unknown}; allowed {sorted(_TOP_KEYS)}")
    if "default" not in data:
        raise ConfidenceError(f"{source}: 'default' is required (the level a tool with no entry gets)")
    default = _entry(f"{source}: default", data["default"], {"level", "note"}, None)
    raw_tools = data.get("tools") or {}
    if not isinstance(raw_tools, dict):
        raise ConfidenceError(f"{source}: 'tools' must be a mapping of tool id to entry")
    tools: Dict[str, Dict[str, Any]] = {}
    for tool_id, raw in raw_tools.items():
        where = f"{source}: tools.{tool_id}"
        entry = _entry(where, raw, _ENTRY_KEYS, default["level"])
        kinds_raw = entry["kinds"]
        kinds: Dict[str, Dict[str, Any]] = {}
        if kinds_raw is not None:
            if not isinstance(kinds_raw, dict):
                raise ConfidenceError(f"{where}.kinds must be a mapping of kind token to entry")
            for kind, kraw in kinds_raw.items():
                kinds[str(kind)] = _entry(f"{where}.kinds.{kind}", kraw, _KIND_KEYS, entry["level"])
        entry["kinds"] = kinds
        tools[str(tool_id)] = entry
    return ConfidenceConfig(default, tools)


def load_confidence(path: str | Path = DEFAULT_CONFIDENCE_PATH) -> ConfidenceConfig:
    p = Path(path)
    if not p.is_file():
        raise ConfidenceError(
            f"confidence file not found at {p} -- set MCP_SERVER_CONFIDENCE_PATH or deploy "
            "gotchas/confidence.yaml. Refusing rather than treating everything as one level."
        )
    try:
        with p.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfidenceError(f"{p} is not valid YAML: {exc}") from exc
    return parse_confidence(data, source=p.name)
