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

