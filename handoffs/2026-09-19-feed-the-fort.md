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
