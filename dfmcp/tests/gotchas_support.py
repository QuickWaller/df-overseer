"""Shared test scaffolding for the gotcha / enrichment / labor-join tests.

Not a test module (no `test_` prefix). Builds a **real** registry and roster
from the repo's own `scripts/dfhack/TOOLS.yaml` and `agents/`, then adds, in a
temp copy only, what the orchestrator has not yet granted:

- the building tool's two ids (`building.find`, `building.build`), because the
  Lua stream owns `TOOLS.yaml` and this stream must not touch it. The entries
  mimic contract C1's command signatures.
- `gotchas.get` and `gotchas.write` for the architect and overseer, and
  `building.find` for the architect, `building.build` for the overseer (the
  sole writer), because `agents/*/tools.yaml` are the orchestrator's.

Nothing here writes into the repo. The temp copies are the point: they prove
the tools are reachable through the one `Roster.check` boundary exactly as
they will be once the real allowlists gain the lines.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS as QUEUE_NATIVE_TOOLS
from dfmcp.registry import DEFAULT_TOOLS_YAML, load_registry
from dfmcp.roles import DEFAULT_AGENTS_DIR, load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS

ALL_NATIVE_TOOLS = {
    **QUEUE_NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS,
    **KNOWLEDGE_NATIVE_TOOLS,
}

_BUILDING_SCRIPT = {
    "df-overseer-building.lua": {
        "commands": {
            "find KIND [W] [H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]": {
                "effect": "read",
                "lua_function": "find",
                "coordinate_bearing": False,
                "live_deployed": False,
                "verified": "unverified",
                "knowledge_scope": "player_derivable",
                "notes": "Test stand-in for the generic building tool's find (contract C1).",
            },
            "build KIND [W] [H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]": {
                "effect": "mutate",
                "lua_function": "build",
                "coordinate_bearing": False,
                "live_deployed": False,
                "verified": "unverified",
                "knowledge_scope": "player_derivable",
                "notes": "Test stand-in for the generic building tool's build (contract C1).",
            },
        }
    }
}


def build_registry_and_roster(tmp_path: Path):
    """`(registry, roster)`: the real manifest plus the test building ids, and
    the real agents directory plus the grants described in the module docstring."""
    manifest = yaml.safe_load(Path(DEFAULT_TOOLS_YAML).read_text(encoding="utf-8"))
    for script, body in _BUILDING_SCRIPT.items():
        if script in manifest:  # the Lua stream has merged; do not shadow it
            continue
        manifest[script] = body
    tools_yaml = tmp_path / "TOOLS.yaml"
    tools_yaml.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    registry = load_registry(tools_yaml, native_tools=ALL_NATIVE_TOOLS)

    agents = tmp_path / "agents"
    shutil.copytree(DEFAULT_AGENTS_DIR, agents)
    for role, section, ids in (
        ("architect", "read", ["gotchas.get", "gotchas.write", "building.find"]),
        ("overseer", "read", ["gotchas.get", "gotchas.write", "building.find"]),
        ("overseer", "write", ["building.build"]),
    ):
        path = agents / role / "tools.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        have = {e["id"] for e in data.get(section, [])}
        for tool_id in ids:
            if tool_id not in have:
                data.setdefault(section, []).append({"id": tool_id, "status": "exists"})
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    roster = load_roster(registry, agents_dir=agents)
    return registry, roster
