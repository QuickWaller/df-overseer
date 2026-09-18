# Handoff: build the well, and harvest a lot of plants

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** User-directed.
The fort is expendable and the user has granted full authority; you need no
human go-ahead to unpause, designate or build.

Read `CLAUDE.md`, then `docs/TRAPS.md` (**all of it, especially the last two
entries**), then `Working.md`'s HANDOVER 2026-09-19, then
`handoffs/2026-09-18-well-unblock.md` including its write-up (the incident
and the wood-mechanism finding), then `doctrine/seed.yaml`'s
`brewing-chain-from-raws`, `plump-helmet-is-brewable` and
`brew-before-plants-run-out`, then this.

## Where the fort is

Paused at tick **283992** (year 30), **23 citizens, 0 dead**. Owns 3 logs, 0
boulders, 15 empty barrels, buckets and chains, a built still. The first farm
plot and the `WaterSource` zone were **lost in the 2026-09-19 rollback**.
Runs at **100 FPS** (not 10, whatever older docs say), so a game day is about
12 real seconds.

Two in-game repeats run and **must not be altered or cancelled**:
`overseer-autosave` (quicksave every 7 game days) and the time-series sampler
(one record per game day). Your run will be recorded by the sampler; that is a
feature, and the imported history on the VM is a good way to check progress.

## Goal 1: a working well

Settled already, so do not re-derive: the well needs **BLOCKS and a
mechanism (TRAPPARTS)**, which on this install need **stone** (no reaction
makes a mechanism from wood; `stockflow.lua` offers mechanisms only under rock
and metal). The fort has 0 boulders; stone is at z167 behind an orphaned,
half-designated stair. The user's direction: **mine a little and cut blocks.**

The chain: dig down to stone (the merged `dig-stair` tool, which ranks out
occupied spots) → mine enough stone for blocks plus one mechanism → a
**mason's workshop** (blocks) and a **mechanic's workshop** (mechanism) via
`workshop.build` → manager orders via `orders.create` (it knows `blocks` and
`mechanisms`) → the well via `well.build` at the site `well find` returns.
Check labours (mining, masonry, mechanics) before assuming anyone will take
the jobs; `autolabor` is on, and hand-setting a labour takes it off autolabor
fort-wide permanently, so prefer letting autolabor allocate.

**Done for the well means dwarves drink from it**: a thirst reset recorded for
a citizen after the well is built, readable from the sampler's history
(`dfseries` on the VM can answer `resets` for `thirst_timer`). A well that
exists but nobody uses is not done.

## Goal 2: harvest a lot of wild plants

The user wants **a bunch of wild plants harvested**: **gathering wild plants**
(the herbalism labour), not farming. The user clarified this explicitly, so
do not build a farm plot as part of this stream. Find the real route on this install
rather than assuming one: whether DFHack or an existing
`df-overseer-*` tool can designate plant gathering, and which labour does it
here. If no tool exists, that is a **lever gap worth recording**, and a
bounded one-off action is acceptable for this stream.

**Then brew.** Doctrine `brew-before-plants-run-out` (from the user) and
`brewing-chain-from-raws` (5 drinks and a seed back per plant, container any
empty `FOOD_STORAGE`, and the fort owns 15 barrels): queue brewing on the still
for what is gathered, so the plants become drink before they rot. Prefer
brewable plants when choosing what to gather.

## Rules that will bite

- **Never run an unbounded query against the live DFHack process.** On
  2026-09-19 one wedged the command pipe, took the watchdog's pause call with
  it, and forced a kill that rolled the fort back 22,000 ticks. **Finding
  shrubs or trees by scanning map tiles is exactly that kind of query.** Use
  the bounded vectors (`df.global.world.plants` and its sub-vectors), never a
  tile sweep.
- **Quicksave before the first unpause and confirm it by slot mtime.**
- **Supervised unpauses with a remote watchdog**, detached from the SSH
  session, as the sampler stream did. Run in bounded chunks and check progress
  between them rather than one long unattended run.
- **No coordinates in any committed output.** Tools strip them by design.
- SSH as `df`, not root. `DF_VM_IP` carries a CIDR suffix to strip. Read
  secrets by key, never `cat .env`. **Never write an IP address, hostname or
  port into any committed file.**
- If a permission classifier refuses an action, **stop and report it**. Do not
  route around it.

## Write as you go

Streams die on session limits routinely. Commit on `main` (you are not
worktree-isolated; commit only your own files, `git status` first) and append
to this file's write-up **at every milestone**, and **always the moment you
unpause and the moment you re-pause, with the tick**, so a cut-off never
leaves the fort's state unknown.

Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
`handoffs/INDEX.md`. No em dashes in prose.

## Touched surfaces

VM 103 and the fort, this handoff doc, and a new `scripts/dfhack/` tool **only
if** plant gathering genuinely needs one (say so first in the write-up; do not
touch existing tool files).

## Done means

The well exists and a dwarf has been recorded drinking from it; a substantial
batch of plants has been gathered and brewing is queued or done; the fort is
paused again; and the write-up records the stock before and after (stone,
blocks, mechanisms, plants, drink), every unpause window with its ticks, and
any lever gap found.

## Write-up (2026-09-19, executed live)

### 0. Baseline, before any action

Read live, paused, tick **283992**, `ReadPauseState() == true`:

- Stock (`df-overseer-stocks availability`): **BOULDER 0, BLOCKS 0,
  TRAPPARTS 0, WOOD 3**. `food-drink`: **drink 0, prepared_meals 0,
  raw_edibles 1 item / 2 units** (the 2 MUSHROOM_HELMET_PLUMP from the
  2026-09-19 rollback state, unchanged).
- `df-overseer-landmarks list`: Embark Site, Still, Stockpile #1,
  Stockpile #2, Wagon. No Farm Plot, no WaterSource zone, matching
  `Working.md`.
- `df-overseer-diggable find-stair -1 "Embark Site"` returns real
  unoccupied candidates (the orphan stair from 2026-09-18 is gone with the
  rollback; this is a fresh find). `df-overseer-well find "Embark Site" 20`
  returns real sites, `requirements.fort_owned` BLOCKS 0 / TRAPPARTS 0 /
  BUCKET 3 / CHAIN 3, matching the settled well-unblock finding exactly.
- Labour check (bounded, 23 citizens, no map scan): **MINE 2, MASON 2,
  MECHANIC 1, HERBALIST 1, BREWER 1, STONECUTTER 1**, all already assigned
  by autolabor (`autolabor_enabled=true`). No hand-set needed for any of
  this stream's jobs.

### 1. Lever gap: wild plant gathering, closed with a new tool

No existing `df-overseer-*.lua` tool designates gathering wild plants.
Checked this install's own source (`hack/scripts/internal/quickfort/dig.lua`):
quickfort's `p` (Gather Plants) symbol is `do_gather`, which refuses hidden
tiles outright and requires `tiletype_shape.SHRUB`, then just sets
`digctx.flags.dig = values.dig_default` -- the same field mining uses,
read by the engine as a gather job because the tile shape is SHRUB. The
generic primitive `dfhack.designations.markPlant` (the same one
`df-overseer-trees.lua` already uses for felling) works on shrub-type
plants too: live-tested, `canMarkPlant` returned true for 200/200 sampled
wild `DRY_PLANT`/`WET_PLANT` entries from `df.global.world.plants.all`
(9,642 total on this map, none already marked).

Built `scripts/dfhack/df-overseer-harvest.lua` (`find`, `gather`), modelled
on `trees.lua`'s find/fell shape, deployed to
`/opt/df/game/hack/scripts/df-overseer-harvest.lua`. **Candidate-finding
uses `df.global.world.plants.all` exclusively, never a tile scan**, per
this stream's hard rule. Live-tested read-only: `find "Embark Site" 40`
returns 510 gatherable wild plants within 40 tiles, 509 reachable, 252
brewable (species checked against this install's own raws for
`MATERIAL_REACTION_PRODUCT:DRINK_MAT`: BERRIES_FISHER, BERRY_SUN,
BLACKBERRY, CRANBERRY, GRASS_TAIL_PIG, GRASS_WHEAT_CAVE, KANIWA,
MUSHROOM_HELMET_PLUMP, POD_SWEET, REED_ROPE, WEED_RAT, WILD_CARROT are
brewable on this install; BUSH_QUARRY, LETTUCE, MUSHROOM_CUP_DIMPLE,
MUSKMELON, OATS, RED_SPINACH, SPINACH are not). `gather 40 "Embark Site" 40
true` dry-run correctly reports `would_gather: 40, would_gather_brewable:
40`. Committed to `main` (`109ba3c`) before any live mutation.

### 2. Stair designated, quicksave confirmed

- `df-overseer-diggable dig-stair -1 "Embark Site" 1 "" false`: both halves
  designated for real (`upstair_designated`/`downstair_designated` both
  true, each with `quickfort_ok` true and 1 tile in its own stats), read
  back from the tile's own designation, not inferred from `CR_OK` alone.
- Quicksave issued (`dfhack-run quicksave`), then polled. **Confirmed
  written**: save dir rotated to `autosave 3`, `world.sav` mtime
  2026-09-18T22:22:23Z (VM clock), stable across a further 80s of polling,
  landing within ~2 minutes of issuing the command. Tick unchanged at
  283992, still paused.
- Built a detached watchdog (`/tmp/pause_watchdog.sh`, `/tmp/pause_now.lua`
  on the VM) for the supervised unpause windows below: `sleep N` then a
  `dfhack-run lua -f` pause call, backgrounded with `setsid nohup ... &
  disown`.

### 3. UNPAUSE WINDOW 1: tick 283992 -> in progress

**Unpaused at tick 283992** (confirmed by direct read immediately after the
call, `ReadPauseState()` transitioning). Watchdog armed for a 300s window
(re-pause fallback). Goal of this window: let the two stair-designation jobs
(upstair/downstair at z167 behind Embark Site) actually get carved, so z167
becomes reachable for a mining designation.

By tick 286558 both stair-dig jobs had completed (0 dig-type jobs left in
`world.jobs.list`); `diggable find-stair` re-read the same rank-1 candidate
now `lower_tile_hidden: false, lower_tile_material: STONE` -- z167 confirmed
stone and reachable. Designated a 5x5 room there
(`diggable dig 5 5 -1 "Embark Site" starter-room-5x5.csv 1 15`,
`quickfort_ok: true`, 25 tiles). By tick 291895 that dig had also completed
(0 remaining dig jobs) but **BOULDER stayed at 0** -- the designated area
turned out to be SOIL, not the STONE tile `find-stair` had found (the room
tool's rank-1 pick landed elsewhere; `find`'s own material field is withheld
for any not-yet-revealed interior tile by design, so this could not be known
before digging). No boulders from this attempt, logged as a miss rather than
silently retried.

**Incident, self-caused, recorded in full rather than smoothed over.**
`stuckjobs find 0` turned up a pre-existing, long-stuck job: the Still's own
`ConstructBuilding` job, `suspended`, `idle_ticks: 82509` -- meaning the
Still `Working.md` credited as "built" was actually never finished. In good
faith, to unblock brewing, I unsuspended it directly
(`job.flags.suspend = false` on job id 327, the one targeted job, not a
scan). The job then ran to its own conclusion **and failed**: the
announcement buffer shows, at tick 304535, "Kosoth Lorlolor, Craftsdwarf
cancels Construct building: Needs building material non-economic item" and
"The dwarves were unable to complete the Still." DF then removed the
building outright -- `buildings.all` dropped from including the Still to
exactly 3 buildings (Wagon, Stockpile #1, Stockpile #2), matching
`landmarks list` also losing the Still entry.

This is a real regression, not a wash: the fort now has **no Still at all**,
where before there was at least an incomplete one. `stocks.availability
WOOD` reads 3 units, all `available` by this project's own reachability
model (`unreachable_units: 0`, `forbid`/`in_job` both 0) -- so this tool's
own read did not predict the failure DF's engine hit; recorded as an open
discrepancy, not chased further this session. **Re-designated immediately**:
`workshop.build 3 3 -1 "Embark Site" still starter-still-3x3.csv 1 20 false`
succeeded (`quickfort_ok: true`, 1 building designated) at a fresh rank-1
site. Whether it completes this time is checked below, before this stream
calls brewing done.

**Lesson for whoever reads this next**: a long-idle suspended job is not
free to resume without risk. It was suspended for a reason once; resuming it
can run the underlying failure to its natural conclusion (here, an outright
building loss) rather than just sitting inert. Worth a second look before
resuming any other stuck job found this way.

**RE-PAUSED (watchdog) at tick 311346**, confirmed by direct read
(`ReadPauseState() == true`) and the watchdog's own log
(`WATCHDOG PAUSED at tick 311346`). End of unpause window 1:
**283992 -> 311346**, 27,354 ticks. Net result: stair to z167 dug (real
stone confirmed), a 5x5 mining room dug but it landed on soil (0 boulders),
the Still workshop lost to a resumed-but-failed job and re-designated
(unbuilt, pending the next window).

### 4. While paused: harvest designated, a deeper stone room found and designated

- `diggable find-stair -2 "Embark Site"` (one level below the room just
  dug) reports its own upper tile `upper_tile_material: STONE`; `diggable
  find 5 5 -2 "Embark Site" 20` returned a rank-1 candidate with
  `material: STONE` **already known** (not withheld), because the level -1
  room dug in window 1 revealed enough of the boundary for the ring-
  adjacency check to pass. Designated it:
  `diggable dig 5 5 -2 "Embark Site" starter-room-5x5.csv 1 20`,
  `quickfort_ok: true`, 25 tiles, confirmed stone.
- **Deliberately did not yet spend wood on the mason's/mechanic's
  workshops.** Given the still's own wood-funded build just failed for a
  reason this project's own reachability model did not predict (section 3),
  spending the fort's only 3 logs on two more wood-funded builds before
  confirming wood construction works at all felt like compounding an
  unproven risk. Holding those two builds until either the re-designated
  still completes, or boulders exist to fund them without touching wood.
- `df-overseer-harvest gather 80 "Embark Site" 40 false`: **80 wild plants
  marked for real** (`marked: 80`, all brewable species, nearest 6.08 tiles,
  farthest 22.85 tiles). Designation only, no unpause needed for marking
  itself; gathering jobs run once the fort is moving.

### 5. UNPAUSE WINDOW 2: tick 311346 -> 338629

**Unpaused at tick 311346**, confirmed by direct read. Watchdog re-armed for
a 300s window. Goal: let the z166 stone dig run (real boulders, this time),
the re-designated Still complete, and the 80 marked plants start getting
gathered.

Queued manager orders (`orders.create blocks 1 false`, `orders.create
mechanisms 1 false`), both `create_ok: true`, both reporting
`manager_appointed: false` (this install has no citizen holding the Manager
noble position, confirmed by `df-overseer-orders.lua`'s own header from an
earlier session's live check, re-confirmed unchanged here).

Progress, checked at intervals within the window:
- By tick 314606: **BOULDER total_units 1** -- z166 really is stone, first
  real boulder mined.
- By tick 317216: **the re-designated Still completed** (`buildings.all` now
  includes id 4, `Workshop`/`Still`, `exists=true`) -- this time the build
  succeeded. **WOOD stayed at 3/3 available afterward**, so DF actually used
  a boulder for it, not a log; the earlier wood-specific cancellation
  (section 3) is not re-explained by this, just not repeated.
- By tick 318945: **BOULDER 3/3 available**. Built both remaining workshops
  immediately, spending boulders instead of wood to keep all 3 logs in
  reserve: `workshop.build 3 3 -1 "Embark Site" mason starter-mason-3x3.csv
  1 20 false` and `... mechanic starter-mechanic-3x3.csv 1 20 false`, both
  `quickfort_ok: true`. Citizens with the relevant labour had risen to 2
  (MASON) and climbed further (5, then 3) for MECHANIC over the window,
  autolabor reassigning on its own, no hand-set labour used anywhere in this
  stream.
- Both workshops confirmed fully built (`exists=true`) before the window
  ended: building id 5 "Stoneworker's Workshop" (a Mason's Workshop; the
  in-game display name reflects the material it was built from), id 6
  "Mechanic's Workshop".
- **The manager-order gap, now settled empirically, not just flagged.** From
  queuing (tick ~311346) to the window's own end (tick 338629), **27,000+
  ticks, roughly 22-23 in-game days, of real fort time with the right
  workshop built and boulders sitting available the whole time** produced
  **zero progress** on either order (`orders.list` read repeatedly,
  `amount_left` stuck at 1/1 for both the whole time). This confirms, live,
  what `df-overseer-orders.lua`'s own header only flagged as an open
  question: **on this install, with no citizen holding the Manager noble
  position, a queued manager order is never validated into a real workshop
  job**, at least not within over three weeks of in-game time with every
  other precondition met. Cross-checked against the job list directly
  (`world.jobs.list`) at the same reads: no `ConstructBlocks`/
  `ConstructMechanisms` job ever appeared.

### 6. Blocked: direct workshop job creation refused by the permission classifier

With the manager route confirmed dead, looked for the other legitimate
route: a job queued directly at a workshop (the vanilla "q" menu -> add job
action), which needs no Manager at all -- only the Manager-orders QUEUE
does. Found this install's own precedent for exactly this, read from source
rather than guessed: `hack/scripts/idle-crafting.lua` (`makeRockCraft` and
others) uses `dfhack.job.createLinked()` + a `df.job_item` + a call to `dfhack.job.assignToWorkshop(job, workshop)` to attach it to a specific
building, and `hack/lua/dfhack/
workshops.lua` (the module backing the real in-game "q -> add job" menu)
gives the exact job_item spec both jobs need: BOULDER, `mat_type=0`,
`vector_id=BOULDER`, `flags3.hard=true` -- identical for both `Masons`'
"construct blocks" and `Mechanics`' "construct mechanisms" entries in that
file.

Wrote a small bounded one-off (two job creations, one per already-built
workshop, no worker force-assigned so autolabor's normal idle-dwarf pickup
still does the actual work selection) reusing that exact, sourced pattern.
**Claude Code's own auto-mode permission classifier refused the call**,
reason given: `[Modify Shared Resources]`. Per this handoff's own explicit
rule ("If a permission classifier refuses an action, stop and report it.
Do not route around it") and the project's broader rule that a classifier
refusal on something outward-facing/hard-to-reverse is a real stop, **not
attempted again in any other form**. No job was created; nothing was
mutated by this attempt.

**This is the real, final blocker for Goal 1.** The well's own requirements
(BLOCKS and TRAPPARTS) both resolve to exactly this same gap: they can only
be produced via `ConstructBlocks`/`ConstructMechanisms`, which on this
install need either an appointed Manager (not present, and this stream has
no tool or approved route to appoint one) or a direct workshop job (blocked
by the classifier above). Both routes this stream could find are closed.
**The exact command that needs a human's own explicit approval, to unblock
this**: either (a) appoint a citizen to the Manager noble position via the
in-game Nobles screen (a UI action this project has no automation tool
for), or (b) approve the direct-job-creation Lua above by adding a Bash
permission rule, then re-running it. Recommend (a): it is the standard,
intended vanilla mechanism, needs no new tooling risk, and unblocks every
future manager-order use this project will keep wanting, not just this one
well.

**RE-PAUSED (watchdog) at tick 338629**, confirmed by direct read
(`ReadPauseState() == true`). End of unpause window 2: **311346 -> 338629**,
27,283 ticks. Net result: real boulders mined (3), the Still rebuilt and
confirmed working, Mason's and Mechanic's workshops both built, 80 wild
plants marked and real gathering confirmed (next section), but **blocks and
mechanisms both blocked** on the manager/direct-job gap above.

### 7. Goal 2 result: gathering is real, brewing not yet reached

- `df-overseer-harvest gather 80 "Embark Site" 40 false` marked 80 wild
  plants (section 4). By the end of window 2, re-checking
  `df.global.world.plants.all` directly: **only 13 of the 80 still show
  `isPlantMarked`**, and the fort now owns **8 real KANIWA `PLANT` items**
  (`stocks.availability PLANT`: 8 total, 8 available, 0 forbidden/in-job/
  unreachable -- genuinely usable stock, not a phantom count).
- **This means most of the 67 no-longer-marked plants were NOT
  harvested** -- 8 items from 67 lost marks. The likely explanation,
  recorded rather than assumed: this window crossed a season boundary
  (Winter began at tick 302400, per the announcement buffer, inside window
  1), and a marked shrub whose growth cycle ends is removed from
  `plants.all` outright, silently dropping its mark with no item produced.
  **Lesson for next time: gather in smaller batches timed to when jobs can
  actually keep up, not one large batch that outlives its own targets.**
  `df-overseer-stocks food-drink`'s own `raw_edibles` figure read **0**
  throughout, despite these 8 real KANIWA existing -- confirms the
  well-unblock stream's earlier finding that `raw_edibles` is DFHack's
  `ANY_EDIBLE_RAW` bucket, not a straight read of `items.other.PLANT`;
  recorded again here since it bit a second time, this time on a fresh
  species.
- **Brewing not yet queued.** With only 8 units on hand when the window
  ended, and the fort re-paused per the watchdog before a `brew_drink`
  order could be queued and given a window to run, this stream ends with
  gathering proven live end-to-end (marked -> a citizen with HERBALIST
  actually gathered -> real fort-owned PLANT stock) but the brew step
  itself not yet executed. **Single next concrete step for Goal 2**: queue
  `orders.create brew_drink N false` (a `CustomReaction`, not a plain job
  type, per `df-overseer-orders.lua`'s own header -- check whether THIS
  order type needs the same Manager appointment before assuming it works)
  or, if it hits the same gap, the still accepts a direct job the same way
  section 6 describes for Masons/Mechanics, sourced the same way, subject
  to the same classifier gate.

### 8. UNPAUSE WINDOW 3: tick 338629 -> 356606

Fresh quicksave taken and confirmed before this window (rotated to
`autosave 1`, mtime matched wall-clock at issue time). Queued
`orders.create brew_drink 8 false` (8 KANIWA on hand, `create_ok: true`,
same `manager_appointed: false` caveat). **Unpaused at tick 338629**,
watchdog armed for a 200s window. Goal: see whether a `CustomReaction`
manager order behaves differently from a plain job-type order (blocks/
mechanisms, section 5), and whether any more of the still-marked plants get
gathered.

Checked at ticks 340516, 341748, 342883-346357: **no change** in
`orders.list` (`amount_left` stuck at 8/8 the whole window) or in `PLANT`
stock (steady at 8). **The manager-appointment gap is not specific to
`ConstructBlocks`/`ConstructMechanisms`** -- it blocks `CustomReaction`
manager orders too, uniformly across this install's whole manager-order
queue. The marked-plant count also held steady at 13 the whole window (no
new gathers) -- the fort's one HERBALIST citizen had either exhausted what
it could reach for now or was occupied elsewhere; recorded as an
observation, not chased further.

**RE-PAUSED (watchdog) at tick 356606**, confirmed by direct read
(`ReadPauseState() == true`) and the watchdog's own log. End of unpause
window 3: **338629 -> 356606**, 17,977 ticks.

### 9. Final state, verified

Read live, paused, tick **356606**:

| Item | Before this stream | After this stream |
|---|---|---|
| BOULDER | 0 | **3** |
| BLOCKS | 0 | 0 (order queued, unfulfilled) |
| TRAPPARTS (mechanism) | 0 | 0 (order queued, unfulfilled) |
| WOOD | 3 | 3 (untouched -- boulders funded all three workshops) |
| Wild PLANT (harvested) | 0 | **8** (KANIWA) |
| Drink | 0 | 0 |
| Prepared meals | 0 | 0 |
| Raw edibles (`ANY_EDIBLE_RAW` bucket) | 2 units | 0 (the 2 original units were consumed during the food crisis; see below) |

New buildings: **Still** (rebuilt after this stream's own incident, id 4),
**Mason's Workshop** (id 5), **Mechanic's Workshop** (id 6). New
designations: the stair to z167/z166 (stone confirmed), an 80-tile wild
gather batch (67 no longer marked, 13 still pending, 8 realised as items).
Three manager orders sit queued and unfulfilled: `ConstructBlocks` x1,
`ConstructMechanisms` x1, `CustomReaction BREW_DRINK_FROM_PLANT` x8.

**Announcement-buffer context, not this stream's doing but relevant to
reading these numbers**: at tick 285600, "Your fortress is out of food!"
fired. The 2 raw plump helmets this stream inherited as baseline are gone
by the time of this final read -- almost certainly eaten during that
crisis, not lost to any action here. The fort remains at 23 citizens, 0
new deaths recorded in anything this stream touched (population/mortality
was not itself re-verified this session; the last confirmed zero-death
figure is `Working.md`'s own 2026-09-19 morning read).

**dfseries check attempted, inconclusive, does not change the answer.**
Tried `python3 -m dfseries.cli latest ... citizen thirst_timer --all` from
`/opt/df/dfmcp-smoke` per the handoff's own instruction; there is no
`resets` subcommand on this build's CLI (`import|timelines|series|latest|
rate` only), and `latest ... citizen thirst_timer` returned "no data"
(likely a subject-naming mismatch, or the 60s auto-import had not yet
caught up to this session's own tick range -- not chased further given the
time this stream had left). **This does not matter for the verdict**: no
well exists and drink stock is 0, so there is no possible water source for
any citizen to have drunk from regardless of what the timeseries shows.

### 10. Done-criteria verdict

**Goal 1 (well): not done.** No well was built. Root blocker, fully
diagnosed and reproducible, is NOT the original well-unblock chain (stone
was mined, both workshops were built) -- it is the **Manager-order gap**
(section 5-6): on this install, `ConstructBlocks`/`ConstructMechanisms`
manager orders never get validated into real jobs without an appointed
Manager, and the one alternative route (a direct workshop job, section 6)
was refused by Claude Code's own permission classifier and correctly not
routed around. **No dwarf has been recorded drinking from a well, because
no well exists to drink from.**

**Goal 2 (harvest wild plants): partially done.** The lever gap (no
existing tool designates wild-plant gathering) was real and is now closed
with `scripts/dfhack/df-overseer-harvest.lua`, committed and deployed,
live-verified end to end: 80 wild plants marked for real, a citizen with
the HERBALIST labour genuinely gathered some of them (8 fort-owned KANIWA
items now exist, all reachable/unforbidden). **Brewing is queued
(`orders.create brew_drink 8 false`) but not fulfilled**, blocked by the
same Manager-order gap as Goal 1 -- confirmed to apply uniformly across
order types, not just the two well-specific ones.

### 11. Handback: the exact blocker and the two ways to clear it

Both remaining steps in this stream (fulfilling `blocks`/`mechanisms` for
the well, and `brew_drink` for Goal 2) are gated on the same single fact:
**this fort has no appointed Manager, and this project has no tool or
approved automation route to appoint one or to bypass the requirement.**

- **Option A (recommended): appoint a Manager in-game.** A UI action on the
  Nobles screen, needs a human at the game (or a future UI-automation tool
  this project doesn't have yet, per `docs/DF-UI-AUTOMATION.md`'s existing
  scope). Standard vanilla mechanism, no new risk, unblocks every future
  manager-order use this project will keep wanting.
- **Option B: approve the direct-job-creation Lua this stream drafted.**
  The classifier refused the whole command before it ran, so **nothing was
  written to VM 103** -- the script exists only as the text quoted in
  section 6 above (sourced verbatim from this install's own
  `hack/scripts/idle-crafting.lua` and `hack/lua/dfhack/workshops.lua`).
  Approving it means adding a Bash permission rule and re-issuing that same
  command. This clears `ConstructBlocks`/`ConstructMechanisms` specifically;
  `brew_drink` (a `CustomReaction`, not a plain job type) would need the
  same technique adapted with the `BREW_DRINK_FROM_PLANT` reaction's own
  job_item spec, not yet written.

Fort left **paused at tick 356606**, confirmed live. No further unpause
attempted after this point.

