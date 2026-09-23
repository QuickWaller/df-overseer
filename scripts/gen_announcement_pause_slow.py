#!/usr/bin/env python
"""Generates scripts/dfhack/df-overseer-announcement-levels.lua from
research/data/2026-09-23-announcement-severity.yaml.

handoffs/2026-09-23-attention-tiers-ingame.md item 2: the fifth tripwire's
pause-id table must be "generated from the YAML rather than hand-copied,
with the generator committed" -- this is that generator. It also emits the
23 `slow`-level ids the same way, per item 2's instruction to expose them
for the sibling conductor stream to consume rather than acting on them here.

Usage:
    python scripts/gen_announcement_pause_slow.py            # regenerate
    python scripts/gen_announcement_pause_slow.py --check    # verify the
        committed .lua file is exactly what this script would produce; exits
        1 and prints a diff-free message on mismatch (used by
        tests/test_announcement_levels_generated.py so the generator and the
        committed file can never silently drift apart).

Only two levels are read out of the 357-entry classification (`pause` and
`slow`); `notice`/`log_only`/`ignore` stay in the YAML only, per that
research doc's own recommendation (S:E, "should never even reach the
tripwire's own id check").
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = REPO_ROOT / "research" / "data" / "2026-09-23-announcement-severity.yaml"
LUA_PATH = REPO_ROOT / "scripts" / "dfhack" / "df-overseer-announcement-levels.lua"

HEADER = '''-- df-overseer-announcement-levels.lua
--@module = true
--
-- GENERATED FILE. Do not hand-edit -- run
-- `python scripts/gen_announcement_pause_slow.py` to regenerate from
-- research/data/{yaml_name} (the source classification;
-- read research/2026-09-23-announcement-severity.md first for method and
-- caveats). tests/test_announcement_levels_generated.py fails if this file
-- and a fresh run of the generator ever disagree.
--
-- handoffs/2026-09-23-attention-tiers-ingame.md item 2: exposes exactly the
-- two report-level id sets this project's fifth tripwire and the sibling
-- conductor stream need.
--
-- PAUSE_REPORT_IDS ({pause_count} ids): df-overseer-clock.lua's fifth
-- tripwire pauses the fort on a newly-arrived df.status.reports entry whose
-- `type` is one of these -- the same "literal id table" shape
-- df-overseer-diff.lua's own REPORT_CATEGORY already uses, generated here
-- instead of hand-copied.
--
-- SLOW_REPORT_IDS ({slow_count} ids): NOT acted on by this repo's Lua side
-- at all (handoffs/2026-09-23-attention-tiers-ingame.md item 2: "not yours
-- to act on"). Exposed read-only, via the `slow-ids` CLI command below and
-- the `announcement-levels.slow-ids` MCP tool that command becomes
-- (scripts/dfhack/TOOLS.yaml), so the sibling conductor stream
-- (docs/AGENT-LOOP.md ss3's "wake the role named in wake, through
-- conductor/triage.py's existing machinery") can route them without this
-- stream touching conductor/. Field shape (also recorded in this stream's
-- handoff Result):
--   pause-ids -> {{"ids": [{{"id": N, "name": "..."}}, ...]}}
--   slow-ids  -> {{"ids": [{{"id": N, "name": "...", "wake": ["overseer", ...]}}, ...]}}

local json = require('json')

'''

FOOTER = '''
function is_pause_report(rtype)
  return PAUSE_REPORT_IDS[rtype] ~= nil
end

function is_slow_report(rtype)
  return SLOW_REPORT_IDS[rtype] ~= nil
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local function sorted_ids(tbl)
  local ids = {}
  for id, _ in pairs(tbl) do table.insert(ids, id) end
  table.sort(ids)
  return ids
end

local args = {...}
local cmd = args[1]

if cmd == "pause-ids" then
  local out = {}
  for _, id in ipairs(sorted_ids(PAUSE_REPORT_IDS)) do
    table.insert(out, { id = id, name = PAUSE_REPORT_IDS[id] })
  end
  print(json.encode({ ids = out }))
elseif cmd == "slow-ids" then
  local out = {}
  for _, id in ipairs(sorted_ids(SLOW_REPORT_IDS)) do
    local info = SLOW_REPORT_IDS[id]
    table.insert(out, { id = id, name = info.name, wake = info.wake })
  end
  print(json.encode({ ids = out }))
elseif cmd == "level" then
  local id = tonumber(args[2])
  if PAUSE_REPORT_IDS[id] then
    print(json.encode({ id = id, level = "pause", name = PAUSE_REPORT_IDS[id] }))
  elseif SLOW_REPORT_IDS[id] then
    print(json.encode({ id = id, level = "slow", name = SLOW_REPORT_IDS[id].name, wake = SLOW_REPORT_IDS[id].wake }))
  else
    print(json.encode({ id = id, level = "not_pause_or_slow" }))
  end
else
  print("usage: df-overseer-announcement-levels <pause-ids|slow-ids|level TYPE_ID>")
end
'''


def _load_types() -> Dict[str, Any]:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    return data["types"]


def _lua_string(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_lua_source() -> str:
    types = _load_types()

    pause_rows: List[Dict[str, Any]] = []
    slow_rows: List[Dict[str, Any]] = []
    for name, entry in types.items():
        level = entry.get("level")
        if level == "pause":
            pause_rows.append({"id": entry["id"], "name": name})
        elif level == "slow":
            slow_rows.append({"id": entry["id"], "name": name, "wake": entry.get("wake") or []})

    pause_rows.sort(key=lambda r: r["id"])
    slow_rows.sort(key=lambda r: r["id"])

    lines = [HEADER.format(
        yaml_name=YAML_PATH.name,
        pause_count=len(pause_rows),
        slow_count=len(slow_rows),
    )]

    lines.append("PAUSE_REPORT_IDS = { -- id -> announcement_type name (df.announcement_type)")
    for row in pause_rows:
        lines.append(f'  [{row["id"]}] = {_lua_string(row["name"])},')
    lines.append("}")
    lines.append("")

    lines.append("SLOW_REPORT_IDS = { -- id -> { name = ..., wake = {role, ...} }")
    for row in slow_rows:
        wake_lua = "{" + ", ".join(_lua_string(w) for w in row["wake"]) + "}"
        lines.append(f'  [{row["id"]}] = {{ name = {_lua_string(row["name"])}, wake = {wake_lua} }},')
    lines.append("}")

    lines.append(FOOTER)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                         help="verify the committed file matches a fresh regeneration; exit 1 on mismatch")
    args = parser.parse_args()

    generated = build_lua_source()

    if args.check:
        if not LUA_PATH.exists():
            print(f"MISSING: {LUA_PATH}", file=sys.stderr)
            return 1
        current = LUA_PATH.read_text(encoding="utf-8")
        if current != generated:
            print(f"STALE: {LUA_PATH} does not match a fresh regeneration. "
                  f"Run: python scripts/gen_announcement_pause_slow.py", file=sys.stderr)
            return 1
        print(f"OK: {LUA_PATH} matches the generator.")
        return 0

    LUA_PATH.write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {LUA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
