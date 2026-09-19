# Handoff: feed the fort

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** User-directed,
urgent. The user has granted full authority; the fort is expendable, but **a
starving fort is exactly what this project should be able to fix.**

Read `CLAUDE.md`, all of `docs/TRAPS.md`, then
`handoffs/2026-09-19-well-and-harvest.md` and
`handoffs/2026-09-19-well-finish.md` (both write-ups), then this.

## The situation, read live by the orchestrator

Paused at **year 31, tick 4257**. 23 citizens, 0 dead.

- **Every citizen is hungry, and 11 are past 75,000 on `hunger_timer`**, the
  worst at 121,585. This is the crisis.
- **Food stock is effectively zero**: FOOD 0, MEAT 0, FISH 0; PLANT 8 (kaniwa)
  and 97 seeds. **Kaniwa is `EDIBLE_RAW`** and brewable per this install's
  raws (`plant_crops.txt`), so those 8 are food.
- Thirst is milder: 8 citizens at about 31,000 to 35,000, none higher, and the
  values prove drinking happens (the newest migrants would read about 135,000
  if they had never drunk). Not the priority.
- **No farm plot exists.** It was lost in the 2026-09-19 rollback, and the
  mechanic's workshop was later built on the empty site.
- Wild-plant gathering works but is slow: **one herbalist gathered only 8 of 80
  marked plants** in about 42 game days. Throughput is the bottleneck, not the
  tool (`df-overseer-harvest.lua`, already live).

## Goals, in priority order

1. **Food flowing now.** Mark a large batch of **`EDIBLE_RAW`** wild plants
   (check edibility from the raws, not by name) with the harvest tool, and
   raise gathering throughput. Autolabor currently gives HERBALIST to one
   citizen. Options, and **you must pick and state the reason**: let autolabor
   respond to the larger job pool, or set HERBALIST on more citizens with
   `labor.set-labor`, which **removes that labour from autolabor fort-wide,
   permanently**. In a starvation crisis the second may be right; record it as
   a deliberate trade, not a default.
2. **A farm, for food that keeps coming.** Rebuild a farm plot with
   `farm.*` tools, on soil (the old plot was at the pond level, z168), and set
   a crop the 97 seeds support. Check what those seeds actually are before
   choosing.
3. **Fishing or hunting**, only if a tool supports it cheaply; record the gap
   if not.

**Do not queue manager work orders**, and **never set `validated` on
anything**: orders are dead on this fort without a Manager, and a hand
validation was a cheat that achieved nothing. A separate stream is building a
proper one-off workshop-job tool.

## Proof that it worked

**Hunger falling, measured**: `hunger_timer` resets for citizens after food
becomes available, from the sampler's history
(`python -m dfseries.cli resets /var/lib/dfseries/uniboslan.series.sqlite3
unit:<id> hunger_timer`, run from `/opt/df/dfmcp-smoke`). Note that **hunger
resets are reported interval-bounded, not exact**, because reset-to-zero is
unverified for hunger; **a real meal here is the first chance to verify it.**
Record the pre- and post-meal values for at least one citizen: if hunger drops
to near zero and then rises exactly 1 per tick, that confirms it, and the
orchestrator will update the registry.

**Stop and report immediately if a citizen dies.** Record the tick, the unit,
and its hunger and thirst at death.

## Rules that will bite

- **Never run an unbounded query against the live DFHack process.** Bounded
  vectors only (`df.global.world.plants`, `units.all`, item vectors). No tile
  scans.
- **Quicksave before the first unpause, confirmed by slot mtime.**
- Supervised unpauses with a detached remote watchdog, in bounded chunks,
  checking hunger between them.
- Do not alter or cancel the `overseer-autosave` or sampler repeats.
- **Do not resume a long-suspended job** without expecting it to run to its
  failure: that is how a previous stream lost the still.
- If a permission classifier refuses anything, **stop and report it**.
- SSH as `df`. `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key.
  **Never write an IP address, hostname or port into any committed file**
  (`tests/test_no_leaked_addresses.py` fails the suite).

## Write as you go

Commit on `main` (not worktree-isolated; own files only, `git status` first)
and append to this file's write-up at every milestone, **always the moment you
unpause and the moment you re-pause, with the tick**. Do **not** write
`Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. No em
dashes in prose.

## Touched surfaces

VM 103 and the fort, and this handoff doc. No repo source changes.

## Done means

Citizens have eaten (hunger resets recorded), the hungriest citizen's hunger
is falling, a farm plot exists with a crop set, the labour decision is
recorded with its reason, no citizen has died (or any death is reported at
once), the fort is paused again, and food stock before and after is recorded.

## Write-up (2026-09-19, executed live)

### 0. Baseline, before any action

Read live, paused, **year 31, tick 4257** (matches the orchestrator's read and
the prior stream's own final pause exactly), `ReadPauseState() == true`.

- **Hunger/thirst, all 23 citizens** (bounded read, `dfhack.units.getCitizens()`
  only, no map scan): worst hunger id=346 at **121585** (matches the
  orchestrator's figure exactly). 11 citizens above 75000:
  346 (121585), 349 (111068), 454 (105911), 192 (110510), 195 (94532),
  196 (95672), 455 (92070), 459 (92760), 345 (88141), 347 (77230), 344 (75480).
  Thirst all in the 2960-34777 range, none critical. Full baseline table:

  | id | hunger | thirst |
  |---|---|---|
  | 192 | 110510 | 10736 |
  | 193 | 62596 | 11583 |
  | 194 | 62371 | 23302 |
  | 195 | 94532 | 2960 |
  | 196 | 95672 | 34777 |
  | 197 | 55648 | 5022 |
  | 198 | 54862 | 18370 |
  | 453 | 61570 | 32401 |
  | 454 | 105911 | 32322 |
  | 344 | 75480 | 9001 |
  | 345 | 88141 | 8866 |
  | 346 | 121585 | 8568 |
  | 347 | 77230 | 8660 |
  | 349 | 111068 | 19367 |
  | 351 | 57224 | 19490 |
  | 352 | 52773 | 18869 |
  | 353 | 66834 | 15856 |
  | 455 | 92070 | 32105 |
  | 456 | 64632 | 31491 |
  | 457 | 64194 | 17688 |
  | 458 | 50113 | 31198 |
  | 459 | 92760 | 31597 |
  | 460 | 55988 | 31694 |

  23 citizens, 0 dead (`getCitizens()` count matches).
- **Stock** (`df-overseer-stocks availability`): PLANT (wild-gathered)
  **8 available** (the KANIWA from the prior stream), FOOD 0, MEAT 0, FISH 0,
  all totals/available/forbid/in_job/unreachable zero except PLANT.
  `stocks food-drink`: drink 0, prepared_meals 0, raw_edibles 0 (the
  `ANY_EDIBLE_RAW` bucket reads 0 even with 8 real PLANT units on hand --
  matches the well-and-harvest stream's own recorded discrepancy, not
  re-chased here).
- **Seeds** (`stocks seeds`, 97 total, matching the orchestrator's figure
  exactly): MUSHROOM_HELMET_PLUMP 51, WILD_CARROT 13, BUSH_QUARRY 5,
  GRASS_TAIL_PIG 5, GRASS_WHEAT_CAVE 5, MUSHROOM_CUP_DIMPLE 5, POD_SWEET 5,
  APRICOT 4, BERRY_SUN 3, PECAN 1.
- **Landmarks**: Embark Site, Wagon, Stockpile #1, Stockpile #2, Still,
  Stoneworker's Workshop, Mechanic's Workshop. No farm plot (confirmed by
  `farm list` returning `[]`) -- matches the situation report ("the
  mechanic's workshop was later built on the empty site").
- **Wild-plant candidates near Embark Site, radius 40** (`harvest find`):
  510 total gatherable, 495 within this specific radius call, 494 reachable.
  By species: OATS 65 (EDIBLE_COOKED only, not EDIBLE_RAW -- see below),
  CRANBERRY 59, MUSKMELON 56, RED_SPINACH 55, WILD_CARROT 52, SPINACH 51,
  LETTUCE 45, BLACKBERRY 42, KANIWA 34, REED_ROPE 15, WEED_RAT 12,
  BERRIES_FISHER 6, BERRY_SUN 3.
- **Edibility checked from this install's own raws directly**
  (`/opt/df/game/data/vanilla/vanilla_plants/objects/plant_{crops,garden,
  standard}.txt` over SSH, grepped per species, not assumed from the
  harvest tool's own `brewable` tag or from species names): **OATS carries
  only `[EDIBLE_COOKED]`, no `[EDIBLE_RAW]` tag at all** -- and this fort
  has no kitchen (landmarks list has none), so a raw OATS plant cannot
  become food right now. Every other candidate species (MUSKMELON,
  RED_SPINACH, SPINACH, LETTUCE, KANIWA, CRANBERRY, WILD_CARROT, BLACKBERRY,
  REED_ROPE, WEED_RAT, BERRIES_FISHER, BERRY_SUN) carries `[EDIBLE_RAW]`
  confirmed by direct grep. **OATS is excluded from the gather batch below
  for this reason, not by name-guessing.**
- **Labour**: `harvest find`'s own `citizens_with_labor` for HERBALIST reads
  **16 of 23** already -- far more than the "one herbalist" the situation
  report described. This is autolabor's own response to the crisis, not
  something this stream set.
- **Farm-plot soil search** (`farm find`, several W/H and levels near
  "Embark Site"): level 0 (outside) has several 3x3 candidates supporting
  only APRICOT/BERRY_SUN/PECAN/WILD_CARROT (4/3/1/13 seeds -- thin).
  **Level -1 (underground, near Stockpile #2) has exactly one candidate,
  up to 4x4** (5x5 returns none), supporting BUSH_QUARRY, GRASS_TAIL_PIG,
  GRASS_WHEAT_CAVE, MUSHROOM_CUP_DIMPLE, **MUSHROOM_HELMET_PLUMP**, and
  POD_SWEET -- and the fort holds 51 MUSHROOM_HELMET_PLUMP seeds against
  single digits for everything else. This is the plot and crop this stream
  builds (see below). No blueprint file existed for 4x4 (only
  `starter-farmplot-5x5.csv`); a `starter-farmplot-4x4.csv` was written
  directly into `dfhack-config/blueprints/` on the VM (not a repo file, per
  `docs/TRAPS.md`'s note that quickfort resolves bare filenames there).
- **Fishing/hunting**: no `df-overseer-*.lua` tool designates a fishing zone
  or a hunting target (`df-overseer-zone.lua`'s only implemented `KIND` is
  `water_source`; `TOOLS.yaml` lists no fish/hunt tool). **Recorded as a
  lever gap, not closed this stream** -- the handoff's own instruction is
  "only if a tool supports it cheaply," and building a new zone kind is not
  cheap under a starvation-crisis time budget. Not chased further.

### 1. Quicksave, confirmed by slot mtime

Issued `dfhack-run quicksave` at 04:08:02Z. Polled the save directory's
mtimes every 6s for 90s: rotated to **`autosave 1`**, mtime
**2026-09-19T04:08:11Z**, stable across all 15 polls, and
`df.global.world.cur_savegame.save_dir` confirms `autosave 1`. Confirmed
written before any mutation. Tick unchanged at year 31, 4257, still paused.
