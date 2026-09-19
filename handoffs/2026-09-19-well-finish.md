# Handoff: finish the well and the brews, now that the orders are validated

Date: 2026-09-19. **Live stream. Owns VM 103 and the fort.** Continues
`handoffs/2026-09-19-well-and-harvest.md`; **read its whole write-up first**,
including the still-loss incident.

Read `CLAUDE.md`, then `docs/TRAPS.md` (all of it), then
`handoffs/2026-09-19-well-and-harvest.md`, then this.

## What changed since that stream stopped

Its three manager orders (1 blocks, 1 mechanism, 8 `BREW_DRINK_FROM_PLANT`)
never became jobs. The cause was found by a bounded read: **all three sat at
`status.validated=false`**. DF only turns validated orders into jobs, and
approval needs a Manager, which this fort lacks, or small-fort
auto-validation, which a 23-citizen fort has outgrown.

**The orchestrator set `validated=true` on those three orders, with the
user's explicit approval**, with the fort paused. It is a **one-off, labelled
exception**, because a real player cannot approve an order without a Manager.
**Do not set `validated` on any other order, and do not change
`df-overseer-orders.lua` to do it.** If you need a new order, it will stall the
same way; say so and stop, rather than validating it yourself.

The fort is **paused at tick 356606**. It owns 3 boulders' worth of stone
already mined, a mason's and a mechanic's workshop, the still, 8 gathered wild
plants, and 15 barrels.

## Deliverable

1. **Supervised unpauses until the three orders are fulfilled**: 1 block, 1
   mechanism, and brewed drink. Check `orders.list` and the stocks between
   bounded chunks. If an order is `validated=true` but still never becomes a
   job, **that is a new finding**: report it rather than guessing.
2. **Build the well** with `well.build` at the site `well find` returns, once
   BLOCKS and TRAPPARTS are both at least 1.
3. **Redeploy `dfseries/` to VM 103** from `main`, which you need for step 4:
   the VM runs a version from before the reset fix, which is why the last
   stream found no `resets` command. Same method as before
   (`git -c core.autocrlf=false archive`, hash-verify), same path
   (`/opt/df/dfmcp-smoke/dfseries`). The import timer keeps running; the
   database needs no rebuild (the reset fix changed no schema).
4. **Prove a dwarf drank from the well**: a `thirst_timer` reset after the
   well exists, from the sampler's history:
   `python -m dfseries.cli resets <db> unit:<id> thirst_timer` from
   `/opt/df/dfmcp-smoke`, with the database at
   `/var/lib/dfseries/uniboslan.series.sqlite3`. **Subjects are `unit:<id>`**,
   not `citizen`; `dfseries.cli timelines` and `series` help find ids. A drink
   could be water from the well **or** the new brewed drink, so say which, or
   say you cannot tell.

## Rules that will bite

- **Never run an unbounded query against the live DFHack process.** Bounded
  vectors only.
- **Quicksave before the first unpause, confirmed by slot mtime.**
- Supervised unpauses with a detached remote watchdog, in bounded chunks.
- **Do not resume a long-suspended job** without expecting it to run to its
  failure: that is how the last stream lost the still.
- Do not alter or cancel the `overseer-autosave` or sampler repeats.
- If a permission classifier refuses anything, **stop and report it**.
- SSH as `df`. `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key.
  **Never write an IP address, hostname or port into any committed file**; a
  test (`tests/test_no_leaked_addresses.py`) will fail the suite if you do.

## Write as you go

Commit on `main` (not worktree-isolated; own files only, `git status` first)
and append to this file's write-up at every milestone, **always the moment you
unpause and the moment you re-pause, with the tick**. Do **not** write
`Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. No em
dashes in prose.

## Touched surfaces

VM 103 and the fort, `dfseries/` deployed copy on the VM, and this handoff doc.
No repo source changes.

## Done means

The well exists, a thirst reset is recorded after it was built (with whether
it was water or brewed drink, or honestly unknown), the brews ran or the reason
they did not is stated, the fort is paused again, and stock before and after is
recorded.

## Write-up (2026-09-19, executed live)

### 0. Baseline, before any action

Read live, paused, tick **356606**, `ReadPauseState() == true`, matching the
prior stream's handback exactly.

- `df.global.world.manager_orders.all`, read directly by field (not just
  `orders.list`, which does not expose `status.validated`): all three orders
  confirmed **`status.validated = true`** (id 0 `ConstructBlocks` 1/1, id 1
  `ConstructMechanisms` 1/1, id 2 `CustomReaction` `BREW_DRINK_FROM_PLANT`
  8/8), matching the prior commit's claim.
- `df-overseer-orders list`: `manager_appointed: false` (unchanged, expected;
  the validation was hand-set, not a Manager appointment).
- `df-overseer-stocks food-drink`: drink 0, prepared_meals 0, raw_edibles 0
  (all fields, all buckets zero).
- Stair/room dig from the prior stream still in place; BOULDER 3 per that
  stream's final read (not re-checked by item type yet this stream; will be
  in the requirements() call below).

### 1. Quicksave, confirmed by slot mtime

Real save path is the XDG one per `docs/TRAPS.md`
(`/home/df/.local/share/Bay 12 Games/Dwarf Fortress/save/`), not
`/opt/df/game/data/save/`. Issued `dfhack-run quicksave` at 03:12 UTC.
Polled `df.global.world.cur_savegame.save_dir` and the save file's own mtime
every 6s: rotated from `autosave 1` (stale, 2026-09-18T22:50:38Z) to
**`autosave 2`**, `world.sav` mtime **2026-09-19T03:13:30Z**, stable across
9 further polls (54s). Confirmed written before any mutation.

### 2. UNPAUSE WINDOW 1: tick 356606 -> in progress

Detached watchdog armed first (`/tmp/pause_watchdog.sh 300`, reused verbatim
from the prior stream, `/tmp/pause_now.lua` unchanged). **Local `ssh.exe`
hung backgrounding it** (the known trap: detaching a long-running process
over this workstation's ssh still blocks the local client even with
`setsid nohup ... < /dev/null &`), moved to Claude Code's own background job
queue rather than treated as a server failure. **Confirmed armed from a
second connection**: `pause_watchdog.sh 300` running, pid 579112, already
128s into its sleep at check time.

**Unpaused at tick 356606** (confirmed by immediate read,
`ReadPauseState() == false`), at 03:17:20Z. Watchdog will fire a fallback
pause call around 300s after it started (~03:17:38Z start, so ~03:22:38Z),
overlapping this window rather than cutting it short since the window's own
goal-check loop re-paces itself; if the watchdog fires before the goal check
does, the window simply ends early and that is fine, it is the safety net,
not the primary stop. Goal of this window: watch whether the three
hand-validated orders actually turn into jobs now that `validated=true`, and
if a job appears, let it run to product.

Polled every ~20s throughout (11 reads total, tick 360011 through 372270):
`status.active` read **`false` on all three orders at every single poll**,
`amount_left` never moved off 1/1/1/8. Cross-checked against
`world.jobs.list` directly mid-window (tick ~367000): 5 jobs present, all
`job_type 27` (`HuntVermin`, a stray dog vs. an emu, confirmed by
`df.job_type[27]`), **zero** `ConstructBlocks`/`ConstructMechanisms`/
`CustomReaction` jobs at any point. Checked the concrete preconditions this
research doc's own failure-mode table (`research/2026-09-18-work-orders.md`
§5) lists, all satisfied, not just assumed:
- **Material present**: `stocks availability BOULDER` reads 3 available, 0
  forbidden/in-job/unreachable.
- **Workshops built and idle**: `Stoneworker's Workshop` (id 5),
  `Mechanic's Workshop` (id 6), `Still` (id 4) all `exists=true`, 0 jobs
  each (`#building.jobs == 0`).
- **Labour holders idle**: citizen 460 (Urist Ralushul, Gem Cutter) carries
  `MASON=true, MECHANIC=true, BREWER=true` and `job=nil` (genuinely idle) at
  the mid-window check; several others also carry the labours but were
  doing `HuntVermin` at the time.
- **Order struct itself**: `workshop_id=-1`, `max_workshops=0`,
  `mat_type=-1`, `mat_index=-1` on all three, i.e. unrestricted, exactly
  what `create_orders`'s own default path produces (per
  `research/2026-09-18-work-orders.md` §2-3, not hand-rolled).

**This is the new finding the handoff asked for, not a guess: `validated =
true` alone does not convert a manager order into a job on this install**,
at least not within 15,664 ticks (~13 game days) with every other
precondition this project can check satisfied. `status.active` staying
`false` the whole time (§5 of the research doc: "no jobs spawned") is the
same signature the doc lists for "no matching workshop" or "conditions
never satisfied," neither of which applies here, so whatever the engine
checks before spawning a job is not fully captured by the `manager_order`
struct's own fields, and setting `validated` by hand does not stand in for
whatever else it checks. **RE-PAUSED (watchdog) at tick 372270**, confirmed
by direct read (`ReadPauseState() == true`) and `/tmp/watchdog.log`
("WATCHDOG PAUSED at tick 372270", fired 03:20:04Z). End of unpause window
1: **356606 -> 372270**, 15,664 ticks. Net result: no order progressed; the
hand-set `validated=true` did not unblock any of the three.
