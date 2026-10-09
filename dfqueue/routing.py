"""Which proposal types are routed to the executor, read from
`dfqueue/action_tools.yaml` (`docs/CONDUCTOR-EXECUTION.md` sections 1 and 6.1).

A type is **routed** when its group says `routed: true`. For a routed type a
proposal must carry an exact `step`, the Overseer can no longer write a
project, `executed` or `amend` for it, and the conductor runs the step. For
an unrouted type a `step` is refused and everything behaves as before.

Pure data: no DFHack, no queue access. The file is re-read when its
content changes, so a deploy that flips a flag is seen by a
running server, and tests can point `ACTION_TOOLS_PATH` at a temp file.
"""

from __future__ import annotations

import hashlib
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
    blob = path.read_bytes()
    key = (str(path), hashlib.sha256(blob).hexdigest())
    hit = _cache.get("entry")
    if hit is not None and hit[0] == key:
        return hit[1]
    raw = yaml.safe_load(blob.decode("utf-8")) or {}
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
            # A `ruling_only` group (a type the Overseer rules and nothing
            # executes, e.g. `plan_change`) has no tools to run.
            if key == "tools" and g.get("ruling_only") is True and v in (None, []):
                continue
            if not isinstance(v, list) or not v or not all(isinstance(i, str) and i for i in v):
                raise RoutingError(f"action_tools.yaml: {name}.{key} must be a non-empty list of strings")
        for flag in ("routed", "frozen", "coverage", "ruling_only", "direct"):
            if not isinstance(g.get(flag, False), bool):
                raise RoutingError(f"action_tools.yaml: {name}.{flag} must be a boolean")
        for t in g["types"]:
            if t in seen_types:
                raise RoutingError(f"action_tools.yaml: type {t!r} is in {seen_types[t]!r} and {name!r}")
            seen_types[t] = name
        if g.get("ruling_only") and (g.get("routed") or g.get("tools")):
            raise RoutingError(
                f"action_tools.yaml: group {name!r} is ruling_only, so it has no tools and is not routed"
            )
        if g.get("direct") and (g.get("frozen") or g.get("coverage") or g.get("ruling_only")):
            raise RoutingError(f"action_tools.yaml: group {name!r} is direct, so it is never frozen, covered or ruling_only")
        for t in g.get("tools") or []:
            # A direct group names tools that other groups (or no group) also name: the
            # Overseer still calls them by name, and the call is recorded as an action.
            if g.get("direct"):
                continue
            if t in seen_tools:
                raise RoutingError(f"action_tools.yaml: tool {t!r} is in {seen_tools[t]!r} and {name!r}")
            seen_tools[t] = name
        out[name] = {
            "types": list(g["types"]),
            "tools": list(g.get("tools") or []),
            "ruling_only": bool(g.get("ruling_only", False)),
            "routed": bool(g.get("routed", False)),
            "frozen": bool(g.get("frozen", False)),
            "coverage": bool(g.get("coverage", False)),
            "direct": bool(g.get("direct", False)),
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
    """The conductor runs this type's steps. A direct group is always on (it has no
    cutover to wait for), whatever its `routed` flag says."""
    g = group_of(type_)
    if g is None:
        return False
    grp = _load()["groups"][g]
    return grp["routed"] or grp["direct"]


def is_ruling_only(type_: str) -> bool:
    """A third class beside routed and unrouted (design F-9): a type the
    Overseer rules and nothing executes. It is never on the unexecuted list,
    and the store closes it when the thing it authorises files."""
    g = group_of(type_)
    return g is not None and _load()["groups"][g]["ruling_only"]


def ruling_only_types() -> list[str]:
    return [t for g in _load()["groups"].values() if g["ruling_only"] for t in g["types"]]


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
    """The groups cut over to the conductor, by flag. A direct group is not one of them
    (it is always on): see `executed_groups`."""
    return [n for n, g in _load()["groups"].items() if g["routed"]]


def executed_groups() -> list[str]:
    """Every group whose open projects the conductor's execute phase runs."""
    return [n for n, g in _load()["groups"].items() if g["routed"] or g["direct"]]


def is_direct(type_: str) -> bool:
    """True for the one type of a `direct` group: a ready-ruled one-step action the
    Overseer's own write-tool call records and the conductor runs (2026-10-09, "the
    conductor is the only game writer"). It is routed (the conductor opens and runs
    it) but is never filed or ruled as a proposal by a model."""
    g = group_of(type_)
    return g is not None and _load()["groups"][g]["direct"]


def direct_groups() -> list[str]:
    return [n for n, g in _load()["groups"].items() if g["direct"]]


def direct_type() -> str | None:
    gs = direct_groups()
    return _load()["groups"][gs[0]]["types"][0] if gs else None


def direct_tools() -> list[str]:
    """The tools the Overseer calls by name that are recorded instead of written."""
    return [t for n in direct_groups() for t in _load()["groups"][n]["tools"]]


def routed_types() -> list[str]:
    """The types a model rules and the conductor runs; a direct type is not one."""
    return [t for n in routed_groups() for t in _load()["groups"][n]["types"]]


def routed_tools() -> list[str]:
    """Tools that left the Overseer's allowlist: a direct group's did not."""
    return [t for n in routed_groups() for t in _load()["groups"][n]["tools"]]


def unrouted_types() -> list[str]:
    """Types in a group that is not routed yet: what the ruling ask and the
    unexecuted to-do line name (design section 3, P3-M4)."""
    return [
        t for n, g in _load()["groups"].items()
        if not g["routed"] and not g["ruling_only"] for t in g["types"]
    ]


def retired() -> list[str]:
    return list(_load()["retired"])
