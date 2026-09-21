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

## Report (executor, 2026-09-21)

**Status: done.** Branch tip is the last of three commits on top of main
`4f42a10`. No VM, no live game, no deploy. No `.lua`, `agents/**`,
`production/**` or `gotchas/**` file changed.

### Design chosen

Two new token forms in a manifest signature, and one per-command declaration.

1. **`[W H]`, an optional group, all or nothing.** The registry now keeps a
   bracketed run as a single `Tool.args` token (`_ARG_TOKEN_RE`), where it used
   to split on whitespace. `dfmcp/tools.py` turns each member into its own
   **flat** optional integer property (`w`, `h`), so `{"w": 3, "h": 3}` from an
   existing caller is unchanged. `argv_for_call` refuses one member without the
   other with `building.find: [W H] go together: got ['w'] without ['h']...`.
2. **`LABOR...` (required, one or more) and `[LABOR...]` (optional).** Must be
   the last token. An `array` property (`minItems: 1` when required) named like
   any token (`labor`), one argv word per item, each item checked like a single
   value (integer type, no booleans, shell metacharacters, no nested lists). A
   bare scalar is accepted as a one-item array; an empty array counts as
   missing.
3. **`skippable: ["[W H]"]`, a per-command key in `TOOLS.yaml`**, validated by
   the registry against the signature (must be an optional token). This is the
   part not in the brief and the reason `dfmcp/registry.py` changed. The
   existing positional-gap rule (a later optional cannot be given while an
   earlier one is omitted) would refuse `find KIND LEVEL NEAR` because `[W H]`
   is omitted, and for a purely positional CLI it would be right to: LEVEL would
   land in W's slot. `df-overseer-building.lua` reads up to three leading
   numbers after KIND and decides by count (1 = LEVEL, 2 = W H, 3 = W H LEVEL),
   so for that CLI only, the omission is safe. Only the CLI can say so, so the
   command declares it. Without the key a group is strict like any optional.
   `RANK` without `LEVEL`, and `DRY_RUN` without `RANK`, are still refused.
4. Malformed tokens (`[w`, `A..B`, `[A... B]`, `[a|b c]`, a repeated name not
   last) are now a `ToolSchemaError`, not a property with a junk name.
5. `_ARG_DESCRIPTIONS` takes **scoped keys** (`"building.KIND"`, `"zone.KIND"`,
   `"workshop.KIND"`, `"building.W"`, `"building.H"`, `"building.FILTER"`) that
   win over the bare token for that script's tools, because `KIND` and `W`/`H`
   mean different things in building, zone, workshop and openarea. Bare
   `LABOR` added.

### Rejected

- **Nested object for the pair** (`footprint: {w, h}`): breaks every existing
  caller and is a worse shape for a model than two flat integers.
- **`dependentRequired` in the JSON schema** to state the pairing: not every
  client or provider honours it; the descriptions say it and the server enforces
  it.
- **Making the gap rule silently ignore omitted groups**: an implicit
  convention that a future positional CLI with a group would break by shifting
  arguments, the exact bug class the gap check exists for. Explicit per-command
  declaration instead.
- **Forbidding `LEVEL` without `[W H]`** (no registry change): would force
  `w=3 h=3` back onto a caller whenever it wants a level offset, which is the
  per-kind knowledge this stream exists to remove.
- **A plural property name** (`labors`): would need a plural heuristic; the
  bare-scalar acceptance keeps a caller written against the old one-labor
  signature working instead.
- **Hard-coding the building tool's skippable group in `tools.py`**: per-tool
  policy in code, against the generalisability rule.

### Did the Lua CLI already satisfy the new signatures?

Yes, no Lua change needed. `df-overseer-building.lua` usage lines are literally
`find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]` and `build KIND [W H]
[LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]`; `resolve_dims` accepts
both omitted for a fixed-size kind, errors on a lone W or H, on a size outside
min..max (so any wrong size for a fixed kind), and on both omitted for a
variable-size kind (naming the range). `df-overseer-labor.lua` takes
`enabled-counts LABOR [LABOR...]`. Both are pinned by tests in
`tests/test_building_tool_manifest.py`, which read the Lua source.

### What changed

- `dfmcp/registry.py`: bracketed groups kept whole in `Tool.args`; `Tool.skippable`
  read from an optional `skippable:` list and validated (`RegistryError`).
- `dfmcp/tools.py`: grammar (`_parse_arg_tokens`, `ArgSpec.repeated/group`),
  schema for arrays, `argv_for_call` (group check, unit-based gap check honouring
  `skippable`, repeated expansion), scoped descriptions, module docstring
  section, list-in-scalar refusal.
- `scripts/dfhack/TOOLS.yaml`: `find`/`build` take `[W H]` with `skippable`,
  `enabled-counts LABOR...`, notes corrected (the "parser cannot express"
  sentences removed), header documents the token grammar and `skippable`.
- `dfmcp/README.md`: one paragraph.
- Tests: `dfmcp/tests/test_tools.py` (sweep rewritten to use the parser, 29 new
  grammar and real-manifest tests), `dfmcp/tests/test_gotchas_server.py` (13 new
  over the real SDK client and in-process app: find with only KIND and
  NEAR_LANDMARK reaches the fake DFHack as `find Still Wagon`, given size
  unchanged, LEVEL alone sends one leading number, a lone `w` or `h` refused and
  nothing sent, RANK without LEVEL still a named gap, `enabled-counts MASON
  BREWER` sends two words, malformed lists refused and nothing sent, the labor
  join works with no size on the call, `tools/list` shows the schema),
  `tests/test_building_tool_manifest.py` (pins the manifest to the Lua's usage
  lines and leading-number parser).

### Consumers checked

`dfmcp/labor_join.py` and `dfmcp/tool_guidance.py` read the kind from the
result's `kind.token` (fallback the call's `kind`), never `w`/`h`; `dfmcp/server.py`
calls `enabled-counts` directly with `*labors` and needs no change. The existing
`test_gotchas_server.py` calls with `w` and `h` still pass unchanged; the omitted
form is now covered next to them.

### Tests

Before: **786 passed / 2 skipped** ambient, **430 passed** in `.venv-dfmcp`.
After: **818 passed / 2 skipped** ambient, **475 passed** in `.venv-dfmcp`. No
existing test needed changing except the manifest sweep (rewritten, not
loosened) and two fixtures in my own new tests that asked for a gap.

### Unknown / for the orchestrator

- `dfmcp/tests/gotchas_support.py` still carries a stand-in `df-overseer-building`
  script (signatures `[W] [H]`) that is skipped whenever the real manifest has the
  script, which it now does. Dead scaffolding; left alone, safe to delete.
- `docs/BUILDING-TOOL.md` (outside my surfaces) and the decision register row of
  2026-09-21 ("requires W and H ... open") are now stale; the row can be closed.
- Not exercised live: nothing here touches a VM. The leading-number rule is read
  from the Lua source and was live-verified only as far as the Lua stream's own
  read-only tests went.
- A `NEAR_LANDMARK` whose name is entirely numeric would be read by the Lua CLI
  as a leading number (pre-existing, unchanged, and landmark names are words).
- Two adjacent identical group tokens in one signature would merge into one
  group; no manifest has one and nothing guards it.
- Landmark names with an apostrophe still cannot pass the shell-metacharacter
  check (register 2026-09-19), unchanged.
