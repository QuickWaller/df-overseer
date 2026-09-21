# Handoff: make the labor join read the building tool's real result shapes

Date: 2026-09-21. **Offline build stream** (worktree, Sonnet). No VM, no live
game, no deploy.

Read `CLAUDE.md`, `dfmcp/labor_join.py`, `dfmcp/tests/test_labor_join.py`,
`dfmcp/tests/test_gotchas_server.py` (the labor-join-over-the-wire class),
`scripts/dfhack/df-overseer-building.lua` (what `find` and `build` really
return), and the "two labor-join gaps" in the report of
`handoffs/2026-09-21-deploy-building-batch.md`, then this.

## Why

The deploy verified the join live against the real graph and found it reports
unknown, safely but uselessly, in two cases, because the server stream wrote the
join against a stub shape:

1. `building.find` returns an **array** of up to five candidates, each carrying
   its own `requirements` and `gaps`. The join looks for a top-level
   `requirements`, so every find says "the result carried no requirements
   block". For Well it shows top-level `gaps: []` beside a candidate that says
   `needs 1 of TRAPPARTS, 0 available`: an all-clear sitting next to a real gap,
   the exact failure class this repo forbids.
2. `building.build` returns its material requirement as `building_material.filters[]`
   (each with a need and stock); the join expects the workshop tool's older
   shape (`accepts` plus `fort_owned`, `needs_container` plus
   `fort_owned_containers`) and reports "present but not in a shape the server
   understands".

## Deliverables

1. Read the real shapes from the Lua tool (do not guess: quote the field names you
   rely on) and make `dfmcp/labor_join.py` handle them: take `requirements` from the
   candidates of an array result (say how you combine five candidates: all share
   one kind, so the kind's requirements are the same; but each candidate's own
   `gaps` differ and must not be dropped or contradicted), and read
   `filters[]` need and stock for the gap wording. The older shape must keep
   working.
2. **Never an all-clear beside a gap.** If any candidate reports a gap, the joined
   `gaps` must not be an empty list. Unknown stays null plus a reason, never `[]`.
3. Tests with the **real captured shapes** (build fixtures from the deploy report's
   live outputs for Masons, Well, Bed, FarmPlot and a `build` dry run), through the
   real server over a real MCP client as the server stream's tests do, including
   the Well case: candidate `needs 1 of TRAPPARTS, 0 available` must reach the
   agent as a gap.

## Rules

- You own `dfmcp/labor_join.py`, `dfmcp/tests/**` and this doc. Do not touch
  `scripts/dfhack/**`, `production/**`, `agents/**` or `gotchas/**`.
- No address, hostname or token in any tracked file. Do not write `Working.md`,
  `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. **Commit after each
  milestone** and extend this doc's report as you go. No em dashes in prose. Use
  the Write tool for scratch scripts rather than long inline shell heredocs.

## Done means

The join reads array `find` results and `build`'s `filters[]`, the Well gap
reaches the agent, no result shows an empty `gaps` beside a candidate gap, the
suites pass (baseline **834 passed / 2 skipped** ambient, **475 passed** in
`.venv-dfmcp`, report before and after), and the report says what a redeploy
needs (dfmcp only).

## Report (executor, 2026-09-21)

**Status: done, offline. Worktree tip on entry was 739335c.**

### The real shapes (from `scripts/dfhack/df-overseer-building.lua`, `requirements_for`, `find_kind`, `build_kind`)

- `find` returns a bare array (the server wraps it `{"result": [...]}`). Each
  candidate: `kind {token, key, label, type, subtype}`, `dims`, `site {rank,
  near_landmark, direction, distance_tiles}`, `search {...}`, `requirements`,
  `gaps`. `requirements_for` runs **once** per call, so the five candidates carry
  identical `requirements` and `gaps`; the server does not rely on that.
- `build` returns one object with `kind`, `dims`, `site`, `dry_run`, `search`,
  `requirements`, `gaps`, `blueprint`, and `validation` (dry run) or
  `quickfort_ok`/`read_back` (real).
- `requirements` is `{building_material: {source, buildingplan_enabled, filters[],
  note?, error?}}`. Each filter: `index`, `quantity` (may be negative: depends on
  footprint), `flags`, `count_scope`, `need` (text: an item type name, or "any
  building material (boulder, log or block)"), `item_type?`, `stock?`
  `{TYPE: {total, available, unnetted, in_building, in_job, error?}}`,
  `available` (int or null), `count_error?`, `vector_name_disagrees?`,
  `quantity_note?`. `gaps` is a list of plain strings in the forms
  `needs Q of NEED, N available`, `NEED: quantity depends on size, N available`,
  `could not count stock for NEED (...)`.
- There is no `accepts`, `fort_owned`, `needs_container` or `fort_owned_containers`
  in the real tool: those were the stub. The older shape is still read.

### What changed

- `dfmcp/labor_join.py`: `_material_filters_gaps` reads `filters[]` (short stock
  is a gap in the tool's own wording, null `available` or missing fields is an
  unknown with the tool's reason, `error` is an unknown, an empty list with the
  tool's note is nothing needed). `combined_gaps` takes any number of
  requirements blocks plus the tool's own gap strings. `join_input` reads an
  object or the `{"result": [...]}` wrapper (exactly one key, a list), takes the
  kind from the candidates when they agree, and turns anything unreadable
  (non-object candidate, empty list, `gaps` not a list, different kinds) into an
  unknown. `LaborJoin.join_result` is the whole-result entry.
- **How five candidates combine**: every candidate's requirements are read and
  every candidate's own `gaps` is kept; the joined `gaps` is their union in order,
  de-duplicated, tool's own entries first, then gaps read from the requirements,
  then labor gaps. Identical candidates collapse to one line (the derived wording
  equals the tool's). A gap on any one candidate makes the result's `gaps`
  non-empty. Unknown stays null plus a reason.
- `dfmcp/tool_guidance.py` (not on the handoff's list, but the array case is
  unreachable without it: `enrich` passed only a top-level `requirements`): it now
  calls `join_result(structured, kind)`, and when the tool's own `gaps` is a list
  it is replaced by the joined list (a superset that begins with the tool's own
  entries) with a note only if it differs. Before, an object result such as a
  `build` kept the tool's `gaps` and dropped the server's, which lost every labor
  gap beside a tool gap list; that is fixed as a side effect.
- Tests: `dfmcp/tests/building_shapes.py` (fixture builders in the Lua field
  names), `test_labor_join_real_shapes.py` (57 tests, transport-free, run
  ambient), `test_labor_join_real_shapes_wire.py` (5 tests through the real server
  and MCP client, run in `.venv-dfmcp`). Mutation check: dropping the tool's gaps
  from the union fails 3 tests, disabling the requirements branch fails 15.

### Fixture provenance (honest limit)

The deploy report kept descriptions, not raw JSON. Field names are copied from the
Lua; the values it states (Well `needs 1 of TRAPPARTS, 0 available`, Bed `needs 1
of BED, 0 available`, Masons and FarmPlot no gap, five candidates, dry-run
`validation`) are used as stated; other stock numbers are plausible, chosen to fit
those gaps. Not a live capture (this stream is offline).

### Verified

- Before: ambient 834 passed / 2 skipped; `.venv-dfmcp` 475 passed (given).
- After: ambient **891 passed / 3 skipped** (+57; the third skip is the new wire
  module, skipped where the pinned SDK is absent, as its siblings are);
  `.venv-dfmcp` **537 passed** (+57 +5).
- The Well gap reaches the agent over a real `call_tool`: `structured.gaps ==
  ["needs 1 of TRAPPARTS, 0 available"]`, no "carried no requirements block"
  unknown, the tool's first text block untouched, the XML block carries the gap.
  Also a Bed `build` dry run: gaps `[BED gap, "nobody has the BREWER labor
  enabled"]`, no "not in a shape" unknown.

### Things to know

- The tool's own `gaps` strings pass through unchanged, including its `could not
  count stock ...` and `quantity depends on size` lines, which are really unknowns
  or notes but sit in the tool's `gaps`. Reclassifying by string would be brittle,
  so they stay in `gaps` (conservative direction); the join's own unknown wording
  can appear beside them. A size-dependent quantity with stock is a tool "gap" even
  when plentiful. That is the Lua tool's wording, not the join's.
- A wrapper is recognised as exactly `{"result": <list>}`. A tool object that
  happened to have only a `result` list key would be read as candidates.

### Redeploy needs

**dfmcp only**: `dfmcp/labor_join.py` and `dfmcp/tool_guidance.py` (tests are not
deployed), then `systemctl restart dfmcp-server`. No Lua, no graph rebuild, no
DFHack or game restart, no unit-file change, no new state directory. Deploy with
`git -c core.autocrlf=false archive` per CLAUDE.md; the deploy is gated on the
user's go-ahead.
