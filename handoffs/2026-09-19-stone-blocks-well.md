# Handoff: mine free stone, make blocks and a mechanism, build the well

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** The user has
granted full authority; the fort is expendable.

Read `CLAUDE.md`, all of `docs/TRAPS.md`, the write-ups in
`handoffs/2026-09-19-well-and-harvest.md`, `2026-09-19-well-finish.md`,
`2026-09-19-feed-the-fort.md` and `2026-09-19-workshop-add-job.md`, then the
last three rows of `decisions/DECISIONS.md`, then this.

## Where things are

Paused at **year 31, tick 40916**. 22 alive, 1 dead (starved), nobody above
about 40,000 hunger. Stair dug to stone at z167/z166. Mason's workshop
("Stoneworker's Workshop"), mechanic's workshop ("Mechanic's Workshop"),
still, and a 4x4 farm plot (plump helmet) exist.

**There are zero free boulders.** The three mined earlier are all
`in_building`, the building material of the three workshops. **The deployed
`stocks.availability` still counts them as available** (a fix is being built
in parallel and is not deployed): **do not trust its BOULDER figure; check
`flags.in_building` yourself** with a bounded read of
`df.global.world.items.other.BOULDER`.

**The workshop job tool works** (`df-overseer-workjob.lua`, deployed): a real
`queue blocks "Stoneworker's Workshop" false` created one job, a dwarf took it,
and it cancelled only because no free boulder existed.

## Deliverable

1. **Mine a small amount of free stone**, enough for at least 1 block and 1
   mechanism with margin (a few boulders), using the existing dig tools near
   the dug stair. Confirm free boulders exist by the `in_building` check.
2. **Queue one blocks job and one mechanisms job** with `df-overseer-workjob`,
   **dry run first**, and run the fort until BLOCKS and TRAPPARTS (mechanism)
   each reach at least 1.
3. **Build the well** with `well.build` at the site `well find` returns.
4. **Prove a dwarf drank from it**: a `thirst_timer` reset after the well
   exists, from the sampler's history
   (`python3 -m dfseries.cli resets /var/lib/dfseries/uniboslan.series.sqlite3
   unit:<id> thirst_timer`, from `/opt/df/dfmcp-smoke`; `python3`, not
   `python`, on this VM). The fort already drinks from an unlocated source, so
   **a reset alone does not prove the well**: say what evidence ties a drink to
   the well (for example a well-drinking job or announcement), or say you
   cannot tell.

**Do not brew in this stream**: `workjob queue brew_drink` refuses on the
container reagent by design, and fixing that is separate work.

## Rules that will bite

- **Never set `validated` on anything, and never queue manager orders.**
- **Never run an unbounded query against the live DFHack process.** Bounded
  vectors only, never a tile scan.
- **Quicksave before the first unpause, confirmed by slot mtime.**
- **Supervised unpauses with a detached remote watchdog, in bounded chunks**,
  checking hunger, thirst and the dead count between them.
- **Stop and report at once if a citizen dies**, with tick, unit, hunger and
  thirst.
- `"Stoneworker's Workshop"` contains an apostrophe: pass it through a script
  file on the VM, not inline shell quoting. The MCP layer refuses it outright.
- Do not alter or cancel the `overseer-autosave` or sampler repeats. Do not
  resume a long-suspended job without expecting it to run to its failure.
- If a permission classifier refuses anything, **stop and report it**.
- SSH as `df`. `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key.
  **Never write an IP address, hostname or port into any committed file.**

## Write as you go

Commit on `main` (not worktree-isolated; own files only, `git status` first)
and append to this file's write-up at every milestone, **always the moment you
unpause and the moment you re-pause, with the tick**. Do **not** write
`Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. No em
dashes in prose.

## Touched surfaces

VM 103 and the fort, and this handoff doc. No repo source changes.

## Done means

Free stone exists and is proven free; a block and a mechanism were made by
workjob-queued jobs; the well exists; drinking from it is evidenced or
honestly marked unknown; no citizen has died (or any death is reported at
once); the fort is paused again; stock before and after is recorded.

## Write-up (2026-09-19, executed live)

### 0. Baseline, before any action

Read live, paused, **year 31, tick 40916**, `ReadPauseState() == true`,
matching the handoff's own figure exactly.

- `stocks availability BOULDER`: `total_units 3`, `available_units 3`
  (**not trustworthy**, per the handoff's own warning: this tool does not
  net `in_building`). `BLOCKS` and `TRAPPARTS` both 0 total/available. `WOOD`
  3/3.
- **Bounded read of `df.global.world.items.other.BOULDER` directly** (3
  items, the whole vector, not a tile scan): all three carry
  `flags.in_building = true`, `in_job = false`, `forbid = false`,
  `owned = false`, `construction = false`. **Zero free boulders, confirmed
  by the field the deployed `stocks.availability` still misses**, matching
  the handoff's root-cause finding exactly.
- `landmarks list`: Embark Site, Farm Plot, Mechanic's Workshop, Still,
  Stockpile #1, Stockpile #2, Stoneworker's Workshop, Wagon. Matches
  expectations; no well yet.

### 1. More stone designated, both candidates confirmed STONE before digging

`diggable find 3 3 -2 "Embark Site" 20`: 5 candidates; rank 5 (near "Still",
distance 0) already shows `material: STONE` (revealed by the earlier dig).
Wrote a new blueprint directly to the VM's blueprint directory (per
`docs/TRAPS.md`, quickfort resolves bare filenames there, not a repo path):
`starter-room-3x3.csv`, a plain 3x3 all-`d` dig, since no 3x3 dig-only
blueprint existed (only workshop/farm/room blueprints). Designated it:
`diggable dig 3 3 -2 "Embark Site" starter-room-3x3.csv 5 20` →
`quickfort_ok: true`, 9 tiles.

`diggable find 5 5 -2 "Embark Site" 25`: rank 1 (near "Still", distance 1)
also `material: STONE`, a fresh area (not overlapping the 3x3 above; the
tool ranks out occupied spots). Designated it too, for margin, since the
earlier 5x5 dig at this same depth produced only 3 boulders from 25 tiles
(~12% yield) and 2 free boulders are the bare minimum needed (1 for
`blocks`, 1 for `mechanisms`): `diggable dig 5 5 -2 "Embark Site"
starter-room-5x5.csv 1 25` → `quickfort_ok: true`, 25 tiles. **34 tiles
designated total**, both confirmed stone before digging, not assumed.

### 2. Quicksave confirmed, watchdog armed

`dfhack-run quicksave` issued at wall-clock epoch 1789795339. Polled the
save directory every 6s for 90s: rotated to **`autosave 1`**, `world.sav`
mtime **1789795347**, stable across all 15 polls. Confirmed written before
any unpause. Tick unchanged at 40916, still paused.

Reused the existing detached watchdog from prior streams verbatim
(`/tmp/pause_watchdog.sh 300`, `/tmp/pause_now.lua`), armed via
`setsid nohup ... < /dev/null & disown`, then **confirmed running from a
second connection** (`ps -eo pid,etimes,cmd`, pid 599290, 7s elapsed at
check time) rather than trusted from the arming command's own return.

### 3. UNPAUSE WINDOW 1: tick 40916 -> in progress

**Unpaused at tick 40916**, confirmed by immediate read
(`ReadPauseState() == false`) at 05:25:04Z. Watchdog armed for a 300s
fallback re-pause. Goal of this window: let the 34 designated tiles get
mined out, producing free boulders, then dry-run and queue one `blocks`
and one `mechanisms` job with `df-overseer-workjob`.

Progress check at tick 46426 (bounded read, `getCitizens()` plus the
`BOULDER` vector, no map scan): **22 citizens, 0 new deaths** (matches the
handoff's own "22 alive, 1 dead" baseline exactly), worst hunger 38205,
worst thirst 34970, nowhere near crisis levels. **`BOULDER` vector now 7
items total, 3 free** (not `in_building`/`in_job`/`forbid`) -- the new
designations are already producing free stone.

### 4. Blocks and mechanisms jobs queued for real

Dry runs first, both `would_queue: true`, `job_item_diagnostics` resolved
(`BOULDER, mat_type=0, flags3.hard`): `workjob queue blocks
"Stoneworker's Workshop" true` and `workjob queue mechanisms
"Mechanic's Workshop" true` (via the raw CLI over SSH, never the MCP
apostrophe path, per `TOOLS.yaml`'s own recorded finding).

Real calls: `workjob queue blocks "Stoneworker's Workshop" false` ->
`create_ok: true, job_id: 1998`. `workjob queue mechanisms
"Mechanic's Workshop" false` -> `create_ok: true, job_id: 2003`. Both
report `jobs_queued_before: 0`, one job item each, resolved. No
`validated` field touched anywhere; this route needs no manager order at
all.

### 5. Both jobs completed: BLOCKS and TRAPPARTS both real stock

Poll at tick 54500 (bounded read): 22 citizens, 0 new deaths, worst hunger
36384, worst thirst 32223 (all falling, fort healthy). `stocks
availability BLOCKS`: **total_units 4, available_units 4** (from 0).
`stocks availability TRAPPARTS`: **total_units 1, available_units 1**
(from 0; a bounded read of the item vector directly confirms the one
TRAPPARTS item carries `in_building=false, in_job=false, forbid=false`,
genuinely free, not a stocks-tool miscount this time). Both jobs the
workjob tool created ran to completion and produced real, usable stock.

### 6. Well built

`well find "Embark Site" 20`: 5 candidates, all `requirements.fort_owned`
now reading `BLOCKS: 4, BUCKET: 3, CHAIN: 3, TRAPPARTS: 1` -- **every
requirement met**. Dry run at rank 1 (`water_depth 7`, not salt, stagnant
true): `would_run_blueprint: starter-well-1x1.csv`, no error. Real build:
`well build "Embark Site" starter-well-1x1.csv 1 20 false` ->
`quickfort_ok: true`, 1 building designated. **The well is designated**;
its construction still needs a citizen to walk the materials over and
build it, which needs the fort kept running (see below).
