# Handoff: the `production/` package, schema and two-pass extraction

Date: 2026-09-18. Stream 2 of 3 from the production-model design pass.
**Read `docs/PRODUCTION-MODEL.md` first**, then
`research/2026-09-18-schema-extraction-static.md`, which is the feasibility
audit this stream implements. The spec is authoritative; where this handoff
and the spec disagree, the spec wins and you say so in your write-up.

Offline stream. **No VM, no SSH, no DFHack, no fort.** Everything here is
pure data plus tests.

## Why this stream exists

The schema is designed and audited and nothing exists in code. Steps 3 of the
spec's build order (§14) needs no scheduler and no live fort, so it can be
built and unit-tested entirely offline, which makes it the safest real code to
write first.

## Deliverable

A new package, `production/`, following `dfqueue`'s own precedent exactly:
`schema.py` (DDL plus validation), `store.py` (read and write), `extract.py`
(the two-pass extractor), and `production/tests/`.

**Name it `production`, and check first that the name shadows nothing** on
`sys.path`, the way `mcp/` shadowed the MCP SDK and `queue/` would shadow the
stdlib. That collision has bitten this repo twice and is documented in
`CLAUDE.md`. If `production` is unsafe, pick another name and say why.

### The seven tables

Copy them from `docs/PRODUCTION-MODEL.md` §4 verbatim. Three corrections in
there are load-bearing and were wrong in the earlier design, so do not
"simplify" them back:

1. **`material_reaction_product` exists** because 42% of product lines inherit
   their material from a reagent at job time, including every food and drink
   reaction. Without this table there is no way to emit a concrete node id for
   brewing.
2. **`consumption` has four values**, not three. `modified_in_place` is for
   the `[IMPROVEMENT]`-only reactions that have no `[PRODUCT]` line at all.
3. **`production_observation.abs_tick`** is `cur_year * 403200 +
   cur_year_tick`, never the bare tick, which resets annually.

`capacity_theoretical` is deliberately absent. Do not add it.

### The two passes

**Pass 1** parses the raws and writes processes, flows, attributes and
classes, leaving `production_flow.node_id` NULL where the product material is
parametric (`GET_MATERIAL_FROM_REAGENT`).

**Pass 2** joins each parametric flow's reagent filter against
`material_reaction_product` and expands one row into N concrete rows. One
brewing recipe becomes one row per brewable crop.

Consumption is derived by the rule in spec §5, which had zero exceptions
across 159 reactions. Implement it as a single documented function with a test
per branch, including the `modified_in_place` branch.

### Raw inputs

The audit read these from `/opt/df/game/data/vanilla/`. **You are not going to
the VM.** Either work from a local raws mirror if one exists in the repo, or
commit a small, clearly-labelled set of real fixture files (the four reaction
files plus the plant file are the minimum) under `production/tests/fixtures/`
and extract from those. Say which you did. Fixtures must be genuine excerpts
with their source path recorded, never hand-written approximations.

## Tests that matter more than coverage

- **`BREW_DRINK_FROM_PLANT` end to end**: one reaction row in, five concrete
  drink nodes out, 5 drink units and 1 seed each, the barrel flow tagged
  `occupied_until_released`, the plant flow `consumed`. This single test
  exercises both passes and three of the four consumption branches.
- **A `GLAZE_*` reaction** produces a `modified_in_place` reagent and **no**
  product row.
- **`abs_tick`** ordering across a synthetic year boundary: two observations
  with the same `cur_year_tick` in different years must not collide and must
  sort correctly.
- **The `BAG_ITEM` inconsistency** (spec §6): `PROCESS_PLANT_TO_BAG` filters on
  `HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM` while quarry bush declares
  `ITEM_REACTION_PRODUCT:BAG_ITEM`. An extractor matching only the first token
  family silently drops the class. Write the test that catches it, record
  `token_family` on the row, and **do not resolve the underlying question**:
  it needs DF's own source, which is closed.

## What to report, beyond "it works"

- **Every column that came out null or guessed, with counts.** The point of
  the audit was honesty about coverage; the extractor must preserve it. A table
  of "rows extracted per table, of which N have status `prior`" is the headline
  number.
- **Whether a cycle appears in the extracted graph.** The audit found none and
  concluded a direct solve suffices, so `scipy` is never needed. Confirm or
  refute against the full extraction, and note that the conclusion covers
  raw-defined reactions only: hardcoded job types are unenumerated (spec §17).

## Rules

- No new runtime dependency. PyYAML is the only real one today. No `scipy`, no
  `networkx`, no graph library. The spec explains why.
- No coordinates anywhere in the schema or output. By construction there is no
  place for one; keep it that way.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- Ambient `python -m pytest` is 306 passed / 1 skipped before you start.
  Report before and after. `py -3` is a 3.13 without pytest: use `python`.
- If a harness, hook or classifier refuses you, **stop and report it.** Do not
  reword to get past it.
- No em dashes in prose.

## Touched surfaces

`production/**` (all new), this handoff doc. Nothing else. If you find
yourself needing to edit a file outside `production/`, stop and report it
instead: two other streams are running in parallel and file overlap is how
they collide.

## Done means

`python -m production.extract` populates a SQLite database from real fixtures,
the named tests pass, the coverage table is written up at the bottom of this
file, and the cycle question is answered for the extractable graph.
