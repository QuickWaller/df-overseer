# Handoff: the generic `building` tool (Lua side) and the game-data dump

Date: 2026-09-21. **WRITTEN for review, not dispatched.** Live stream:
**read-only against VM 103, fort stays paused, no real build, no unpause.**

Read `CLAUDE.md` (especially "Tools must be generalisable"), then
`docs/BUILDING-TOOL.md` **in full** (design, decisions and contract C1), then
`scripts/dfhack/df-overseer-workshop.lua` and `blueprints/starter-*.csv`, then
`docs/TRAPS.md` (the `reqscript` cache trap and the unbounded-query rule), then
this.

## Why this stream exists

`workshop.find/build` covers five hard-coded kinds. The user's minimum for
openclaw includes building workshops, rooms and furniture, and a tool that
only works for a few kinds is not a tool. DFHack's own quickfort table
(`building_db_raw` in `hack/scripts/internal/quickfort/build.lua` on the VM)
already lists roughly 87 buildable kinds with type, subtype and footprint.
This stream builds one tool that takes a kind from that table.

## Deliverables

1. **`scripts/dfhack/df-overseer-building.lua`** (new), with commands
   `list-kinds`, `find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]` and
   `build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]`,
   output per **contract C1**. `KIND` is the table's own key or enum name,
   **never a display label** (the MCP layer refuses apostrophes). Footprint
   comes from the table (3x3 default for workshops, furnaces and siege
   engines; overrides exist), so `W H` are optional for fixed-size kinds and
   validated against min and max for the rest. **The blueprint is generated in
   code**, written where quickfort finds it, following the shape of the
   existing `starter-*.csv` files; do not add per-kind CSVs.
2. **First task, before anything else: find how to read the table at run
   time.** `building_db_raw` is a `local` in `build.lua`. Check whether the
   module exports it or a getter. If not, evaluate the options (read another
   exported structure, or parse the file text) and pick the least fragile.
   **Report the choice and why**, and what a DFHack update would break.
3. **`enabled-counts LABOR [LABOR...]`** added to
   `scripts/dfhack/df-overseer-labor.lua`, per C1: `null` plus an error for a
   failed lookup, **never `0`**. Guessing a labor token's name is unreliable
   (`FEED_WATER_WOUNDED` never existed and printed 0); resolve names through
   `df.unit_labor` and report unknown names as errors.
4. **A data dump for the graph stream**, read-only and bounded, written to the
   scratchpad **out of tree** (raws-derived data stays out of this public
   repo, as the reaction corpus did): (a) for every `df.job_type` value, its
   `attrs.skill` and that skill's `attrs.labor`, with lookups that error
   recorded as errors, not dropped; (b) for each workshop and furnace kind,
   **whichever jobs it hosts, and where that list comes from.** The second is
   the real unknown: find a source (DFHack's `stockflow.lua`, `workorder`,
   `workshop-job`, or a game structure) and report which one and how complete
   it is. Also record the **ConstructBlocks disagreement**: the job attrs map
   it to STONECUTTER while `df-overseer-workshop.lua` says a mason's workshop
   uses MASON. Report which is right for operating a mason's workshop and how
   you know.
5. **`scripts/dfhack/TOOLS.yaml`** entries for the new commands with
   `knowledge_scope` chosen deliberately, and the manifest tests updated.

## Verification

Every command exercised on VM 103 **as a dry run or read only**, on the paused
fort, with each result quoted in the write-up. `find` and `build DRY_RUN` for
at least: a workshop kind, a furnace kind (1x1 and 5x5 kinds included as
footprint checks), a furniture kind, and an unknown kind (must error). Take a
bounded approach: **never run an unbounded query against the live process**.
Confirm the fort's pause state and tick are unchanged at the start and end.
**Do not run `build` without `DRY_RUN`.** The first real build of a
never-built kind is a separate, later stream needing the user's go-ahead.

## Rules that bite here

- Do **not** touch `agents/*/tools.yaml`; report the allowlist lines needed.
- Do not touch `dfmcp/**`, `production/**`, `gotchas/**` or
  `docs/BUILDING-TOOL.md`.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- The `reqscript` module cache is keyed by name across `dfhack-run` calls;
  shadowing an already-loaded script silently returns the stale module.
- Read secrets by the key you need, never the whole `.env`. SSH as `df`; do
  not write any address, hostname or token into a tracked file.
- **Commit after each milestone** and extend this doc's report as you go.
- No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-building.lua` (new),
`scripts/dfhack/df-overseer-labor.lua`, `scripts/dfhack/TOOLS.yaml`, tests
that read the manifest, this doc. The dump lives outside the repo.

## Done means

The tool lists kinds, finds and dry-run-builds at least four kinds of three
categories on the real VM, errors on an unknown kind, `enabled-counts` gives
`null` plus an error for a bad name, the table-access choice and the
job-hosting source are written up, the dump exists out of tree, the suite
still passes (**552 passed / 1 skipped**, report before and after), and the
fort's pause state and tick are unchanged.
