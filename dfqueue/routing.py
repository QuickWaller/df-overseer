"""Which proposal types are routed to the executor, read from
`dfqueue/action_tools.yaml` (`docs/CONDUCTOR-EXECUTION.md` sections 1 and 6.1).

A type is **routed** when its group says `routed: true`. For a routed type a
proposal must carry an exact `step`, the Overseer can no longer write a
project, `executed` or `amend` for it, and the conductor runs the step. For
an unrouted type a `step` is refused and everything behaves as before.

Pure data: no DFHack, no queue access. The file is re-read when its
modification time changes, so a deploy that flips a flag is seen by a
running server, and tests can point `ACTION_TOOLS_PATH` at a temp file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ACTION_TOOLS_PATH = Path(__file__).resolve().parent / "action_tools.yaml"

#: The cutover "group" for everything that predates the executor
#: (deploy 2a): it is not in the yaml, it only names a cutover.
LEGACY_GROUP = "legacy"

_cache: dict = {}


class RoutingError(Exception):
    """`action_tools.yaml` is malformed."""


def _load() -> dict:
    path = Path(ACTION_TOOLS_PATH)
    key = (str(path), path.stat().st_mtime_ns)
    hit = _cache.get("entry")
    if hit is not None and hit[0] == key:
        return hit[1]
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    data = _validate(raw)
    _cache["entry"] = (key, data)
    return data


def _validate(raw: dict) -> dict:
    groups = raw.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise RoutingError("action_tools.yaml: 'groups' must be a non-empty mapping")
    seen_types: dict = {}
    seen_tools: dict = {}
    out: dict = {}
    for name, g in groups.items():
        if name == LEGACY_GROUP:
            raise RoutingError(f"action_tools.yaml: {LEGACY_GROUP!r} is reserved for cutovers")
        if not isinstance(g, dict):
            raise RoutingError(f"action_tools.yaml: group {name!r} must be a mapping")
        for key in ("types", "tools"):
            v = g.get(key)
            if not isinstance(v, list) or not v or not all(isinstance(i, str) and i for i in v):
                raise RoutingError(f"action_tools.yaml: {name}.{key} must be a non-empty list of strings")
        for flag in ("routed", "frozen", "coverage"):
            if not isinstance(g.get(flag, False), bool):
                raise RoutingError(f"action_tools.yaml: {name}.{flag} must be a boolean")
        for t in g["types"]:
            if t in seen_types:
                raise RoutingError(f"action_tools.yaml: type {t!r} is in {seen_types[t]!r} and {name!r}")
            seen_types[t] = name
        for t in g["tools"]:
            if t in seen_tools:
                raise RoutingError(f"action_tools.yaml: tool {t!r} is in {seen_tools[t]!r} and {name!r}")
            seen_tools[t] = name
        out[name] = {
            "types": list(g["types"]),
            "tools": list(g["tools"]),
            "routed": bool(g.get("routed", False)),
            "frozen": bool(g.get("frozen", False)),
            "coverage": bool(g.get("coverage", False)),
        }
    retired = raw.get("retired") or []
    if not isinstance(retired, list) or not all(isinstance(i, str) for i in retired):
        raise RoutingError("action_tools.yaml: 'retired' must be a list of strings")
    return {"groups": out, "retired": list(retired),
            "type_to_group": seen_types, "tool_to_group": seen_tools}


def groups() -> list[str]:
    return list(_load()["groups"])


def group_of(type_: str) -> str | None:
    """The group a proposal type belongs to, or `None` (e.g. `stock_target`)."""
    return _load()["type_to_group"].get(type_)


def group_of_tool(tool_id: str) -> str | None:
    return _load()["tool_to_group"].get(tool_id)


def _group(group: str) -> dict:
    g = _load()["groups"].get(group)
    if g is None:
        raise RoutingError(f"no such routing group: {group!r}")
    return g


def is_routed(type_: str) -> bool:
    g = group_of(type_)
    return g is not None and _load()["groups"][g]["routed"]


def is_frozen(type_: str) -> bool:
    g = group_of(type_)
    return g is not None and _load()["groups"][g]["frozen"]


def coverage_on(type_: str) -> bool:
    g = group_of(type_)
    return g is not None and _load()["groups"][g]["coverage"]


def tools(group: str) -> list[str]:
    return list(_group(group)["tools"])


def types(group: str) -> list[str]:
    return list(_group(group)["types"])


def routed_groups() -> list[str]:
    return [n for n, g in _load()["groups"].items() if g["routed"]]


def routed_types() -> list[str]:
    return [t for n in routed_groups() for t in _load()["groups"][n]["types"]]


def routed_tools() -> list[str]:
    return [t for n in routed_groups() for t in _load()["groups"][n]["tools"]]


def unrouted_types() -> list[str]:
    """Types in a group that is not routed yet: what the ruling ask and the
    unexecuted to-do line name (design section 3, P3-M4)."""
    return [t for n, g in _load()["groups"].items() if not g["routed"] for t in g["types"]]


def retired() -> list[str]:
    return list(_load()["retired"])
