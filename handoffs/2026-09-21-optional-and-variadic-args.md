# Handoff: let a manifest signature express optional and repeated arguments

Date: 2026-09-21. **Offline build stream** (worktree, Sonnet). No VM, no live
game, no deploy.

Read `CLAUDE.md` (especially "Tools must be generalisable"), `dfmcp/tools.py`
(the module docstring and `_parse_arg_token`, `_INTEGER_ARG_NAMES`,
`_ARG_DESCRIPTIONS`), `dfmcp/tests/test_tools.py`,
`scripts/dfhack/TOOLS.yaml` (the `df-overseer-building.lua` and
`df-overseer-labor.lua` blocks), `tests/test_building_tool_manifest.py`, the
Lua stream's report in `handoffs/2026-09-21-building-tool-lua.md` (its notes for
the orchestrator, item 1), and `docs/BUILDING-TOOL.md`, then this.

## Why

The generic building tool takes a kind and should read the kind's footprint from
the game. Today the manifest signature is `find KIND W H [LEVEL] NEAR_LANDMARK
[RADIUS_TILES]`, with W and H **required**, because `dfmcp/tools.py` cannot
express an optional pair. So an agent asking for a Still must already know it is
3x3, which is per-kind knowledge the game already holds (`building.list-kinds`
returns it). That breaks the project's generalisability rule: the next kind
should cost one data entry, not a caller who memorised its size. The Lua CLI
already accepts W H omitted for a fixed-size kind and refuses them for a
fixed-size kind if wrong; only the manifest and the MCP schema are in the way.

Same limit: `labor.enabled-counts` takes one labor per call in the manifest
(`LABOR`), though the Lua CLI takes several (`LABOR [LABOR...]`).

## Deliverables

1. **Teach `dfmcp/tools.py` a way to express both, minimally.** Choose the
   smallest design that works and say why (for example: an optional group
   written `[W H]` that is either both present or both absent, and a repeated
   argument written `LABOR...` that becomes an array of strings expanded into
   argv). It must keep every existing signature working unchanged. Tokens must
   still become valid JSON-schema properties, and the existing sweep in
   `dfmcp/tests/test_tools.py` must still pass and must cover the new forms.
   A caller giving only one of an all-or-nothing pair gets a named error, not a
   silent default.
2. **Update the manifest to use it:** `find KIND [W H] [LEVEL] NEAR_LANDMARK
   [RADIUS_TILES]`, `build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK]
   [RADIUS_TILES] [DRY_RUN]`, and `enabled-counts LABOR...` in
   `scripts/dfhack/TOOLS.yaml`, with the notes corrected (they currently say the
   signature carries W H only because the parser cannot express an optional
   pair). Add `_ARG_DESCRIPTIONS` entries for `KIND`, `FILTER` and `LABOR`
   (and `W`/`H` if useful): that the width and height default to the kind's own
   footprint, when to pass them (variable-size kinds such as farm plots), and
   that a wrong size for a fixed-size kind is an error.
3. **Check the server's consumers of the changed signatures**: `dfmcp/labor_join.py`
   and `dfmcp/server.py` read the result of `building.find`/`build`, and the
   server tests in `dfmcp/tests/test_gotchas_server.py` call `building__find`
   with `w` and `h`; make them cover both the omitted and the given forms.
   `tests/test_building_tool_manifest.py` must keep passing and cover the new
   signatures.
4. **Prove it end to end through the real registry and roster over a real MCP
   client** (as the server stream did): `building.find` with only KIND and
   NEAR_LANDMARK reaches the fake DFHack as the command line a real call would
   send, `enabled-counts` with two labors expands to two arguments, and each
   malformed form is refused with a named error.

## Rules

- You own `dfmcp/tools.py`, `dfmcp/tests/**`, `scripts/dfhack/TOOLS.yaml`,
  `tests/test_building_tool_manifest.py` and this doc. Do **not** change
  `scripts/dfhack/*.lua` (report if the Lua CLI would need a change), `agents/**`,
  `production/**` or `gotchas/**`. No other stream is running.
- Unknown is never zero. No address, hostname or token in any tracked file. Do
  not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. **Commit after each milestone** and extend this doc's
  report as you go. No em dashes in prose. Use the Write tool for scratch
  scripts rather than long inline shell heredocs.

## Done means

The building manifest carries an optional footprint and `enabled-counts` takes
several labors; the schema, tests and manifest agree; existing tools are
unchanged; the suites pass (baseline **786 passed / 2 skipped** ambient and
**430 passed** in `.venv-dfmcp`, report before and after); and the write-up says
what design was chosen, what it rejected, and whether the Lua CLI already
satisfied the new signatures.
