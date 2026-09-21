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

## Report (executor, 2026-09-21)

**Status: done.** Read-only against VM 103 throughout: the fort stayed
paused, the pause state and tick were identical at start and end (paused,
year 31, tick 103055, frame counter 292633), nothing was deployed (the scripts
ran from a scratch script path that was removed afterwards; the running game
now reports `df-overseer-building is not a recognized command`), and no
scratch blueprint file is left on the guest. `build` was only ever run as a
dry run.

### Built

- `scripts/dfhack/df-overseer-building.lua` (new): `list-kinds [FILTER]`,
  `find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]`,
  `build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]`.
  175 distinct kinds (177 quickfort keys, two of them aliases). Blueprint
  generated in code, no per-kind CSVs.
- `scripts/dfhack/df-overseer-labor.lua`: `enabled-counts LABOR [LABOR...]`.
- `scripts/dfhack/TOOLS.yaml`: `building.list-kinds`, `building.find`,
  `building.build`, `labor.enabled-counts`.
- `tests/test_building_tool_manifest.py`: 11 offline checks (manifest and
  dispatch parity, server-parser compatibility, the silent-zero guards).

### Deliverable 2: how the kind table is read

`building_db_raw` is a local; the module exports only `do_run`, `do_orders`,
`do_undo`. Chosen: reach it through **Lua upvalues by name**. `do_run` closes
over `building_db`, whose metatable `__index` (`custom_building`) closes over
`building_db_raw`. This gives the table as quickfort actually runs it, with the
defaults pass already applied (the 3x3 workshop footprint is filled in by a
loop after the table, not written in it) and with each kind's own
`is_valid_tile_fn`, which the tool then calls instead of copying. Rejected:
parsing the file text (the table is Lua source with helper calls and a
post-pass, so a parser would re-implement both), and another exported
structure (none exists; the raws hold only the two custom workshops). **What a
DFHack update would break:** renaming the upvalues `building_db` or
`building_db_raw`, renaming `do_run`, or moving the table out of that chain.
Each fails loud: the loader returns an error naming the missing hop (a
structural check of every entry follows), so the tool reports "table layout
changed", never an empty list. A new kind, a new label or a new key costs
nothing here. Tokens: the subtype enum name (`Masons`, `Still`, `Kiln`), the
raws code for a custom workshop (`SOAP_MAKER`, `SCREW_PRESS`), or the type name
(`Bed`, `Well`); direction-variant families (bridge, screw pump, rollers, track
stops) become `<Base>_<key>` (`Bridge_gw`); the bare quickfort key also works.
No token contains an apostrophe.

### Deliverable 3: enabled-counts

`{"counts": {LABOR: n or null}, "errors": {LABOR: message}}`. Names must match
`^[A-Z][A-Z0-9_]*$` and survive a round trip through `df.unit_labor`, so `NONE`
(-1), `_last_item`, numbers and lowercase are errors. Live, in one call:
`BREWER 2, CARPENTER 2, COOK 2, MASON 2, MECHANIC 1, STONECUTTER 1`, and `null`
plus an error for `FEED_WATER_WOUNDED`, `NONE`, `_last_item`, `brewer`, `12`.
Duplicate names are counted once. An independent per-unit read of the
citizens' labor bits gave the same MASON (2), STONECUTTER (1), MECHANIC (1) and
CARPENTER (2). No arguments gives a usage error object; an all-valid call gives
`"errors": {}` (an object, not `[]`).

### Verification, live on VM 103, fort paused (each result is real output)

Every find and dry-run build below ran near "Embark Site", default radius 30,
mostly from level 0 (the surface), about 0.9 to 1.3 s each including the SSH
hop (radius 60, the cap, took 1.3 s). Search blocks report tiles checked and
eligible, so an empty result is distinguishable from a broken check.

| Kind (token) | Category, footprint | find | build DRY_RUN validation |
|---|---|---|---|
| Craftsdwarfs, Masons, Still, SOAP_MAKER | workshop 3x3 | 5 sites | ok, 1 building designated |
| Kiln, Smelter | furnace 3x3 | 5 sites | ok |
| Quern, Millstone, SCREW_PRESS | workshop 1x1 | 5 sites | ok |
| Kennels, Siege, TradeDepot | workshop or depot 5x5 | 5 sites | ok |
| Bed, Door, Table, Chair, Cabinet, Box, Statue, Coffin, WindowGlass, Bookcase, Cage, GrateFloor, Hive, Well | furniture 1x1 | 5 sites | ok |
| Wall, Lever, Weapon, Ballista | construction, trap, siege engine | 5 sites | ok |
| FarmPlot 5x5, RoadPaved 3x2 | variable size | 5 sites | ok |
| Bridge_gw 3x2, ScrewPump_Msu 1x2 | per-window and directional | 5 sites | ok |

`find` and `build` DRY_RUN were both run for every row except Wall, Lever,
Bookcase, Ballista, Cage, GrateFloor, Statue, Hive, Weapon, WindowGlass and
Coffin, which had only the dry run (it runs the same site search internally).

Details worth quoting. There is no 1x1 or 5x5 furnace in quickfort's table
(all seven furnaces are 3x3), so the footprint checks used workshops, a depot
and siege kinds. The kind's own tile rule visibly differs per kind on the same
3721 tiles: eligible tiles were 3389 for a workshop, 568 for a door (beside a
wall), 380 for a bed (indoors), 96 for a well, 3098 for a farm plot (soil, with
87 fitting 5x5 sites). Level -1 (underground) had only 24 eligible tiles: a
bed found 5 sites, while a 3x3 kiln and a 5x5 farm plot correctly found none,
reported as `no site for Kiln (3x3) near Embark Site; search: 3721 tiles
checked, 24 eligible, 0 check errors`.

Errors, all as `{"error": ...}` objects:

- `find Widget ...` gives `unknown building kind: Widget (run list-kinds)`;
  `find Stil` adds `did you mean: Still`.
- `find Masons 4 4` gives `Masons footprint 4x4 is outside the allowed width
  3..3, height 3..3`; `find FarmPlot` with no dims gives `FarmPlot needs W and
  H (width 1..31, height 1..31)`; 40x40 gives an out-of-range error.
- Unknown landmark, level outside the map, missing arguments and rank 9 of 5
  each give a specific message.
- `find Bridge_gw 10 10` at radius 30 refuses (`search area too large for a
  per-window kind; lower RADIUS_TILES`) rather than running an unbounded scan.

**Verifying the verification.** quickfort returns result 0 even when it
designates nothing. A negative control (an indoor-only Bed on the outdoor
landmark tile, `quickfort run -d`) printed `Buildings designated: 0`,
`Unsuitable tiles for building: 1` and result CR_OK. So the tool's
`validation.ok` is computed from the statistics (at least one building
designated and every other counter zero), and the same function, exported for
this, was fed both real outputs on the VM: the negative gave `ok false` with the
problem named, the positive `ok true`. A real build additionally reads the tile
back (`read_back`); that branch is untested live.

Requirements, real: a Craftsdwarfs find reported the game's own filter ("any
building material") with `BOULDER total 7, in_building 3, available 4`,
`BLOCKS total 4, available 3`, `WOOD total 3, in_building 3, available 0`, and
`buildingplan_enabled: true`. A Well reported four filters (BLOCKS, BUCKET,
CHAIN, TRAPPARTS) with the single gap `needs 1 of TRAPPARTS, 0 available`
(total 1, in_building 1), consistent with the register's 2026-09-19 finding.
`FarmPlot` has zero filters and says so.

A trap found on the way: the filters' `vector_id` is a `df.job_item_vector_id`,
whose numbers do not line up with `df.items_other_id` (54 is BED in one and
CHAIN in the other). The tool maps by name from the filter's item type.

### Deliverable 4: the dump (out of tree)

Location: a `building-dump` directory in the executing session's scratchpad,
outside the repo (the orchestrator has the full path from the executor's final
message; it is deliberately not recorded in this public file). Files: `job_types.json` (all
259 `df.job_type` values, -1 to 257, with `attrs.skill`, the skill's labor,
`skill_stone/wood/metal` overrides, `attrs.labor`, plus the 94 labor names and
captions; **0 lookup errors**), `workshop_hosting.json` (33 workshop, furnace
and custom kinds with three sources each, plus a join of every hard-coded job to
its derivable labors), `constructblocks_finding.json`, `quickfort_kinds.json`.
Lookup errors are recorded in the file, not dropped; the earlier errors for
`BrewDrink` and `MakeTrapParts` were **names that do not exist** in
`df.job_type` on this build (brewing is reaction-defined, the Still hosts 3
reactions; trap parts is `MakeTrapComponent`), so enumerating the enum range
cannot fail that way.

**Where "which jobs does a kind host" comes from: no single complete source.**

- S1, `dfhack.workshops.getJobs`: a hand-written table (from DFHack's advfort)
  plus the raws' reactions. Hard-coded jobs cover only **16 of 33 kinds and 50
  distinct job types**; Craftsdwarfs, Metalsmith's and Magma Forge, Bowyers,
  Clothiers, Tanners, Kennels and Still have none, and its own comments mark
  the forges unfinished. Its reaction entries are exact.
- S3, my own scan of `world.raws.reactions.reactions[*].building`: complete for
  reaction-defined jobs (304 reactions) and identical to S1's reaction entries
  on every kind where S1 was run. It is the authoritative source for those.
- S2, `plugins.orders.get_profile_labors`: the labor set the game's Workers tab
  offers per kind, non-empty for 17 of 33 kinds (empty for kitchen, mechanic,
  loom, siege, furnaces other than kiln and so on, which is the absence of a
  restriction UI, not of a labor).
- Not used: the game's own workshop "add task" list (`main_interface.building`
  buttons) exists only while a building is selected in the UI, so reading it
  means driving UI state.
- **Gap for the graph stream:** 193 of 259 job types are attributed to no
  kind by S1, of which 66 look like workshop work (MakeCrafts, forging
  weapons, armor and ammo, milling, cheese, lye and potash, gem and glass
  work, fishing, spinning, dyeing, siege and trap loading, MakeTool and so on).
  Of the 74 hard-coded (kind, job) rows, **39 have no labor in the game's job
  table** (skill -1): every Masons and Carpenters furniture job (ConstructDoor,
  ConstructThrone, ConstructTable, ...). The game applies those labors in code,
  from the item material. They are not derivable from any structure read here;
  S2 gives only a hint (Masons offers STONECUTTER and STONE_CARVER).
- Smelter and Magma Smelter were read from the static table only, because
  `getJobs` would also generate one SmeltOre job per metal ore and `printall`
  each one to the console. S3 lists 23 reactions on each.

**The ConstructBlocks disagreement: STONECUTTER is right; MASON is not an
operating labor of the Mason's Workshop.** Three concordant static sources: (1)
`df.job_type.attrs[ConstructBlocks].skill` is `CUT_STONE`, whose labor is
`STONECUTTER` ("Stone Cutting"), the same as SmoothWall, SmoothFloor,
CarveFortification and CarveTrack; (2) `get_profile_labors(Workshop, Masons)`
returns `[STONECUTTER, STONE_CARVER]`, with no MASON; (3) **no job type in the
game's table has a skill that maps to MASON at all.** The only skill with labor
MASON is `MASONRY` (id 4) and nothing in `attrs` references it, so the game
applies it in code. One consistent live observation: citizen 345 has MASONRY
experience 400 with only the MASON labor and no CUT_STONE entry, which fits
MASON/MASONRY being earned by constructing buildings from stone (the fort has
built three workshops from stone), not by running a workshop. **Not proven by
watching a dwarf make blocks**: the one live blocks job was cancelled for lack
of free boulders (register 2026-09-19). Consequence for the old tool:
`df-overseer-workshop.lua`'s `mason` entry (`labor = "MASON"`) is the wrong
labor for block work. The Carpenters' block job also maps to STONECUTTER in the
table, which is a job-table quirk (the table does not distinguish material).

### Findings the orchestrator needs (outside my touched surfaces)

1. **The MCP server's argument parser cannot express two things contract C1
   asks for.** `dfmcp/tools.py` reads whitespace-separated tokens and only
   understands `PLACEHOLDER` or `[PLACEHOLDER]`. An optional pair `[W H]`
   would become properties named `[w` and `h]`, and a variadic `[LABOR...]`
   becomes `labor...`; the sweep in `dfmcp/tests/test_tools.py` would fail. So
   the manifest signatures are `find KIND W H [LEVEL] NEAR_LANDMARK
   [RADIUS_TILES]`, `build KIND W H [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES]
   [DRY_RUN]` and `enabled-counts LABOR` (one labor). The Lua CLI keeps the
   flexible forms (W H omitted for a fixed-size kind; several labors), and the
   manifest notes say so. **If the optional pair and the variadic matter,
   `dfmcp/tools.py` needs a group syntax**; a stream that owns `dfmcp/**`
   should decide it. Also missing there: `_ARG_DESCRIPTIONS` entries for
   `KIND`, `FILTER` and `LABOR`; integer typing is already right for `W`, `H`,
   `LEVEL`, `RANK` and `RADIUS_TILES`.
2. **Allowlist lines to add** (`agents/*/tools.yaml`, untouched by me),
   following the farm and workshop pairing rule (finds on the architect,
   builds on the overseer): architect read `building.list-kinds`,
   `building.find`, `labor.enabled-counts`; overseer read the same three and
   write `building.build`; consultant read `building.list-kinds` only if it is
   meant to answer "what can we build". Not added to any role, so role tool
   counts are unchanged (architect 25, overseer 45, consultant 11).
3. **The find result repeats `requirements`, `gaps` and `search` on every
   candidate** (up to five copies, about 2 KB each), matching the old
   workshop tool's per-candidate shape. If the token cost matters, the server
   could hoist them.
4. Landmark names such as "Mechanic's Workshop" contain an apostrophe, so the
   MCP layer still cannot pass them as `NEAR_LANDMARK` (register 2026-09-19);
   this tool does not change that.
5. `df-overseer-workshop.lua` still reports a plain fort-owned count without
   the `in_building` deduction; the new tool uses `stocks.availability`.
6. C1 additions, all additive: `gaps` (decision 5 of the design note),
   `search`, `blueprint`, `validation` (dry run only, so `quickfort_ok` stays
   reserved for a real build), `read_back`, `quickfort_problems`, and
   `requirements.building_material.filters[]` with per-filter stock. C1's
   `"building_material": {...}` interior shape was unspecified; this is what
   I chose.

### Tests

Before: **552 passed, 1 skipped** (ambient `python -m pytest`), **271 passed**
(`dfmcp/tests` in `.venv-dfmcp`). After: **563 passed, 1 skipped** (11 new in
`tests/test_building_tool_manifest.py`), **271 passed**. No existing test needed
changing. The new guard was checked to fail for the shapes it exists to catch (a
`[W H]` and a `[LABOR...]` token produce invalid property names).

### What remains unknown

- **The real build path has never run**: writing the blueprint, `quickfort run`
  without `-d`, the `read_back`, and whether `buildingplan` picks the materials
  up. The dry run proves the blueprint and the site pass quickfort's own tile
  rules; it cannot prove the game accepts the job. A never-built kind still
  needs its own supervised stream and the user's go-ahead.
- `find` does not prove a site is reachable from the fort's main area (only
  that a walkable tile is in or beside the footprint), and a kind that goes on
  open space (machine shafts, bridges over chasms) is found only beside
  walkable tiles.
- Stock counts are by item type only: the filters' own flags (empty bucket,
  screw component, fire-safe, non-economic) are listed, not applied, and the
  result says so. `Weapon` (upright spear) has a filter the tool cannot count by
  type and reports it as a gap.
- The operating labors of the 39 hard-coded jobs with no table labor, and the
  hosting of the 66 uncovered workshop-like jobs, are open (see the dump).
- DFHack's `--dry-run` for quickfort is documented as changing no game state;
  I observed no state change (pause state and tick identical), but did not
  diff the whole fort.
