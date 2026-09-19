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

### 2. Farm plot built (designated), labour decision, plants marked

**Labour decision, stated up front**: **let autolabor respond, do not
hand-set HERBALIST on anyone.** Reason: `harvest find` already reads
**16 of 23 citizens with HERBALIST**, autolabor's own response to the
crisis, far beyond the "one herbalist" the situation report described.
The prior stream's bottleneck (8 of 80 gathered) was the **size of the
marked-plant batch**, not a shortage of gathering labour -- autolabor had
already reallocated most of the fort to it. Hand-setting more citizens with
`labor.set-labor` would strip autolabor's fort-wide management of
HERBALIST **permanently**, for a labour pool that is not the constraint,
which is a worse trade than leaving it alone. This is the deliberate
choice the handoff asked for, not a default.

**Farm plot**: built (designated) at the only viable underground site found,
4x4, near Stockpile #2, using a new blueprint file
(`dfhack-config/blueprints/starter-farmplot-4x4.csv`, written directly to
the VM, not a repo file -- no 4x4 farm blueprint existed before this
stream, only 5x5, and 5x5 does not fit here). `farm build 4 4 -1
"Embark Site" starter-farmplot-4x4.csv 1 40 false`: `quickfort_ok: true`,
`id: 7`, 1 building designated. Crop will be **MUSHROOM_HELMET_PLUMP**
(51 of the fort's 97 seeds, by far the largest holding, and the only
underground-valid crop with meaningful seed stock -- BUSH_QUARRY/
GRASS_TAIL_PIG/GRASS_WHEAT_CAVE/MUSHROOM_CUP_DIMPLE/POD_SWEET each have
only 5). **Not set yet**: `set-crop` requires `flags.exists == true`
(construction finished), confirmed still `false` right after designation
by a direct bounded read (`df.building.find(7).flags.exists`) -- a
zero-material building still needs a citizen to walk over and complete
the construction job, which needs the fort unpaused. Deferred to the first
unpause window.

**Bug found, recorded not fixed (out of this stream's touched surfaces,
which are VM/fort only, no repo changes)**: `df-overseer-farm.lua`'s
`list_farm_plots()` collapses `exists = false` to `nil` in its JSON output
(`ok_exists and exists or nil` -- the same "Lua `false or nil` folds to
nil" trap `docs/TRAPS.md` already documents elsewhere for a different
field). `farm list` printed `{"id":7,"default_name":"Farm Plot","crops":
[]}` with no `exists` key at all right after designation, which reads
exactly like a fully-built plot with no crop set rather than an
unfinished one. Caught only by cross-checking with a direct bounded
`df.building.find(7).flags.exists` read, which returned `false`. Anyone
using `farm list` to decide whether a plot is ready for `set-crop` should
not trust a missing `exists` key as meaning "false" without checking the
building directly, until this is fixed.

**Plants marked**: edibility checked against this install's own raws (see
baseline), OATS excluded (`EDIBLE_COOKED` only, no kitchen exists). All 12
EDIBLE_RAW species' full reachable counts dry-run-verified then marked for
real, one `harvest gather` call per species (the tool takes one species
filter at a time): CRANBERRY 59, MUSKMELON 56, RED_SPINACH 55, WILD_CARROT
52, SPINACH 51, LETTUCE 45, BLACKBERRY 42, KANIWA 34, REED_ROPE 14,
WEED_RAT 12, BERRIES_FISHER 6, BERRY_SUN 3 -- **429 wild plants marked for
real**, every dry run's `would_gather` matching its real `marked` count
exactly (no partial marks, no failures).

### 3. UNPAUSE WINDOW 1: year 31 tick 4257 -> in progress

Detached watchdog armed first (`/tmp/pause_watchdog.sh 300`, reused
verbatim from the well-and-harvest/well-finish streams), confirmed running
by a second connection (`ps`, pid 591436, elapsed 1s at check time).
**Unpaused at year 31, tick 4257**, confirmed by immediate read
(`ReadPauseState() == false`) at 04:12:21Z. Goal of this window: let the
farm plot's own construction job complete (so `set-crop` becomes possible),
let some of the 429 marked plants actually get gathered, and watch whether
any citizen's `hunger_timer` resets (a real meal).

Progress within the window, polled by direct bounded reads:
- Tick 11981 (30s in): still unpaused, no issue.
- Tick 16205 (70s in): **farm plot 7's `flags.exists` reads `true`** --
  construction finished already, fast because it needs no material.
  **PLANT stock jumped from 8 to 44 total units (42 available)** -- real
  gathering happening quickly with 16 citizens on HERBALIST and 429 marked
  targets.
- **Crop set immediately once `exists` went true**: `farm set-crop 7
  <season> MUSHROOM_HELMET_PLUMP false` for all four seasons, each
  `write_ok: true` and `read_back_plant_index: 173` (matches the seed
  stock's own MUSHROOM_HELMET_PLUMP mat_index convention). **The farm plot
  is now fully built and planted.**

### 4. STOP: a citizen died during this window

At tick 23787 (~150s into the window), a routine hunger/thirst poll showed
**`citizen_count` had dropped from 23 to 22**, with id=454 missing from
`getCitizens()`. Checked immediately: `df.unit.find(454)` still resolves,
`dfhack.units.isDead(unit) == true`, `dfhack.units.isCitizen(unit) ==
false`. Cross-checked against the announcement buffer: report id 322,
year 31, **tick 15143**: **"Kadol Zulbanurdim, Gem Setter has been found,
starved to death."** `dfhack.units.getReadableName` on unit 454 confirms
the identity: `Kadol Zulbanurdim "Bannertower", Gem Setter`.

**Per this handoff's own hard rule, stopped immediately and re-paused the
fort**: `dfhack.world.SetPauseState(true)` issued at 04:16:51Z, confirmed
by immediate read (`ReadPauseState() == true`), **fort paused at year 31,
tick 29445**. End of unpause window 1: **4257 -> 29445**, 25,188 ticks
(~21 game days). Checked the announcement buffer again after re-pausing:
no second death, `citizen_count` confirmed still 22 (not falling further).

**The death, stated plainly**: unit 454's own baseline (this stream's own
tick-4257 read, section 0) was **hunger 105911, thirst 32322** -- the
second-highest hunger in the fort, already deep into starvation before
this stream took any action. It died at tick 15143, **10,886 ticks (~9
game days) after this stream's baseline read and after this stream's own
unpause**, before the marked-plant gathering had scaled up enough to
reach it -- the farm plot did not finish construction until roughly tick
16205 and `PLANT` stock was still only 8 units at baseline. **This reads
as a citizen who was very likely already past saving by the time this
stream started reading the fort, not a consequence of any action taken
here** -- no plant was unmarked, no labour was pulled, nothing this stream
did could plausibly have fed unit 454 faster than tick 15143 given travel
and job-completion time. Recorded honestly rather than argued away: this
is exactly the scenario the situation report's own crisis framing warned
about (11 citizens already past 75000 hunger at baseline, one at 121585),
and the fort's food pipeline, even responding immediately, was not fast
enough to save the second-worst case.

**Everyone else improved sharply in the same window.** Re-reading all
(now 22) citizens at the moment of re-pause: hunger fell across the board,
often by 60,000-80,000 ticks more than the ~25,000 elapsed alone would
explain (proof of real eating, not just less time passing) -- e.g. id=344
75480 -> 3281, id=347 77230 -> 6472, id=353 66834 -> 263, id=346 (the
fort's own worst case at baseline) 121585 -> 45773. `stocks
availability PLANT`: **118 total units (88 available)**, up from 8.
`stocks food-drink`: **`raw_edibles` now reads 175 units / 166 items**,
up from 0 -- the fort has real, eatable food again.

### 5. Hunger-reset proof, and the reset-to-zero question finally answered

`python3 -m dfseries.cli resets /var/lib/dfseries/uniboslan.series.sqlite3
unit:344 hunger_timer --start 12503000 --end 12530000` (run from
`/opt/df/dfmcp-smoke`, `python3` not `python` on this VM) reports **three
resets** for citizen 344 in this stream's own window, and the same query
for citizen 346 reports **two**. Both confirm real eating happened, fort-
wide, immediately after food became available.

**The reset-to-zero question this project's own tooling had left open**
(`reset_to_zero_verified` stayed `False` because no real hunger reset had
ever been observed) **is answered by this stream's own data.** Fine-
grained series for unit 344 around its third reset
(`dfseries.cli series ... --start 12523000 --end 12530000`):

```
12523406: 44429.0 ticks
12524606: 45629.0 ticks
12525806: 442.0 ticks     <- the reset: dropped from 45629 to near zero
12527006: 1642.0 ticks    <- 442 + 1200 (the sampler's own tick gap) exactly
12528206: 2842.0 ticks    <- 1642 + 1200 exactly
```

**Hunger drops to near zero on a real meal, then rises exactly 1 tick per
tick afterward** -- both post-reset deltas match the sampler's 1200-tick
gap exactly, with no drift. This is the same signature thirst_timer
already had verified; hunger now has it too, for the first time, from a
real meal this stream's own actions produced. Recording this as new,
verified evidence for the registry (not written here per this handoff's
own scope restriction -- the orchestrator owns `decisions/DECISIONS.md`).

### 6. Stopped here, per the death rule. Not resumed this session.

Per this handoff's own instruction, this stream stops at the death report
rather than opening a second unpause window. Final state, verified live at
the re-pause:

| Item | Before this stream (tick 4257) | After this stream (tick 29445) |
|---|---|---|
| FOOD | 0 | 0 (no `FOOD`-type items produced; food is all raw `PLANT`) |
| MEAT | 0 | 0 |
| FISH | 0 | 0 |
| PLANT (wild-gathered) | 8 total / 8 available | **118 total / 88 available** |
| `raw_edibles` bucket (units) | 0 | **175** |
| Drink | 0 | 0 (not brewed this stream; out of scope -- see below) |
| Seeds | 97 (unchanged; none consumed by gathering) | 97 |
| Farm plots | 0 | **1** (id 7, 4x4, underground, MUSHROOM_HELMET_PLUMP all 4 seasons) |
| Citizens | 23, 0 dead | **22, 1 dead** (unit 454, tick 15143, starved) |
| Worst hunger | id=346, 121585 | id=346 (still worst), **45773** |
| Citizens > 75000 hunger | 11 | **0** (highest remaining is 45773) |

**Labour decision**: let autolabor respond (16/23 already on HERBALIST at
baseline); no `labor.set-labor` call made. Reasoning in section 2.

**Farm plot and crop**: id 7, 4x4, underground near Stockpile #2,
MUSHROOM_HELMET_PLUMP set for all four seasons, write-confirmed by
read-back. 51 of the fort's 97 seeds are this species.

**Plants marked and gathered**: 429 marked across 12 EDIBLE_RAW species
(OATS excluded, EDIBLE_COOKED only). By the time of re-pause, real
gathered stock had reached 118 PLANT units (from 8) -- gathering is
genuinely working at a much higher throughput than the prior stream's 8-
of-80, consistent with 16 citizens on HERBALIST against a much larger
marked pool.

**Fishing/hunting**: no tool exists for either (`df-overseer-zone.lua`
only implements a `water_source` zone kind; no fish/hunt designation tool
in `TOOLS.yaml`). Recorded as a lever gap, not closed -- building one was
not "cheap" under this crisis's time budget, and this stream stopped early
regardless once the death was found.

**Brewing**: not attempted this stream. The situation report's priority
order was food-flowing-now (done), a farm (done), then fishing/hunting
(gap, recorded); brewing the gathered KANIWA/CRANBERRY/WILD_CARROT/
BLACKBERRY/REED_ROPE/WEED_RAT/BERRIES_FISHER/BERRY_SUN was not in this
handoff's own priority list and was not reached before the death stopped
the stream. The still exists and is idle; a future stream could queue
brewing directly at it (not via a manager order -- `decisions/DECISIONS.md`
and both prior well streams established manager orders are dead on this
fort without an appointed Manager, and hand-validating one was explicitly
forbidden by this handoff).

**Unpause windows, exact ticks**:
- Window 1: year 31, tick 4257 -> tick 29445 (25,188 ticks, ~21 game
  days). Started 04:12:21Z, ended (re-paused on the death finding)
  04:16:51Z.

**Fort left paused at year 31, tick 29445**, confirmed live
(`ReadPauseState() == true`). No further unpause attempted this session.

### 7. Done-criteria verdict

**Food flowing now: done, and proven.** 429 EDIBLE_RAW wild plants marked
(edibility checked from this install's own raws, not by name), real
gathered stock rose from 8 to 118 PLANT units / 175 raw-edible units in
one 25,188-tick window, and hunger fell sharply fort-wide -- 11 citizens
above 75000 at baseline, zero above 75000 at re-pause. Hunger resets
recorded for two citizens via `dfseries`, and the reset-to-zero mechanism
is now verified for the first time (section 5), not just inferred.

**A farm, for food that keeps coming: done.** Farm plot 7, 4x4,
underground, MUSHROOM_HELMET_PLUMP set for all four seasons, construction
confirmed complete and the crop write confirmed by read-back.

**Fishing/hunting: gap recorded, not closed.** No tool exists; not
attempted, per the handoff's own "only if cheap" instruction.

**One citizen died: unit 454, Kadol Zulbanurdim, Gem Setter, tick 15143
(year 31), hunger 105911 / thirst 32322 at this stream's own baseline
(tick 4257), starved before this stream's own food response could reach
it.** Reported per the handoff's hard rule; the fort was re-paused
immediately on discovery (tick 29445) and no further unpause was
attempted this session.
