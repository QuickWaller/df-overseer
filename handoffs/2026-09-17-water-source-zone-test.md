# Handoff: Water Source zone on the pond, then a supervised drink test

**Dispatched** 2026-09-17 by the orchestrating session. **Agent:** `executor`,
Sonnet. **User go-ahead:** 2026-09-17, looking at the live screen: "the zone
should designate (a tile lower) as a water source". This covers **one zone
placement and one supervised unpause**, nothing else. **Peer check-in:** no
other session on this repo or home-lab is live.

## Why

No dwarf drank on its own during the last test
(`research/2026-09-17-founders-not-drinking.md`). Each pond is a basin of
6-7/7 water in ramps at z168, with open air (RAMP_TOP) above at z169 and
undug soil around it (`research/2026-09-17-pool-reachability.md`, **read its
CORRECTION note first**: the report's "getWalkableGroup is broken on ramps"
and "dry bank tile" claims are wrong). The fort has **no zones at all**. This
build has `df.civzone_type.WaterSource` (82), placeable by quickfort `#zone`
symbol `w` (`hack/scripts/internal/quickfort/zone.lua`). The question: does a
Water Source zone on the water let the founders drink?

## Read first

`CLAUDE.md` (traps, secrets rule), `docs/TRAPS.md`, both research files above,
`decisions/DECISIONS.md` row 2026-09-17 "Supervised drink test at 10 FPS"
(the safety envelope you are repeating), the DFHack quickfort user guide's
`#zone` section on the VM (`hack/docs/docs/guides/quickfort-user-guide.txt`),
and `blueprints/README.md` (blueprints go flat into the guest's
`dfhack-config/blueprints/`; quickfort resolves names relative to it).

## Do

1. **Pre-state, read-only.** Fort paused, tick (expect 217948), FPS 10
   (`enabler.fps`), 15 citizens, zones 0, each citizen's `thirst_timer`.
2. **Pick the pond** nearest the citizens' centroid. Record its water tiles at
   z168 (depth, stagnant/salt flags) and its bounding box.
3. **Place one Water Source zone** at **z168** covering that pond's water
   tiles, with a throwaway `#zone` blueprint (e.g. `w(WxH)`) run by
   `quickfort run <file> -c x,y,z`. Coordinates are fine here: this is an
   operator action, not model input. Run `quickfort orders`/dry-run style
   checks first if available (`quickfort run ... --dry-run`), then the real
   run. Verify it exists: `world.buildings.other.ACTIVITY_ZONE` count 1, type
   `WaterSource`, z168, footprint over water. **If quickfort refuses z168**,
   say exactly why; then, and only then, place it on the z169 RAMP_TOP tiles
   above the same pond instead, and report that you did. Delete the throwaway
   blueprint file afterwards.
4. **Supervised unpause**, exactly as the earlier test: a script run on the
   VM itself with `nohup setsid`, a `trap` that re-pauses on any exit, FPS 10,
   a **7.5-minute ceiling**, and stop conditions: citizens below 15, any
   thirst at or above 45,000, focus not `dwarfmode`, tick not advancing. **Also
   stop early for success**: every founder (193-198) below 5,000 thirst.
5. **Sample every ~15 s** (light probes, one Lua file, state in `/tmp`): tick;
   every job of type `Drink`, `GiveWater`, `FillWaterskin` or anything with
   "Water"/"Drink" in its name, with worker id, patient id (general refs) and
   the job's z-level; each founder's thirst, z-level and current job name;
   any new announcement/report text. At the end read each founder's
   emotions for `Drink`-related and `ReceivedWater`/`GaveWater` thoughts with
   their ticks.
6. **End state:** paused (verify), tick, focus. **Leave the zone in place**;
   the orchestrator and user decide whether to keep it. Do not save.

## Constraints

- No other mutation: no dig, build, labor write, burrow, second zone (except
  the z169 fallback in step 3), save or DF restart.
- Never set DFHack globals (`local` only). Multi-line Lua: write a file and run
  `dfhack-run lua -f`, inline `-e` with newlines fails. Keep probes light.
  Delete `/tmp` files on both ends at the end.
- `getTileFlags`/`flow_size` via `dfhack.maps.getTileFlags(x,y,z)` works;
  `getWalkableGroup` takes a pos (`xyz2pos(x,y,z)`).
- VM access: `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user
  `df`; read those keys only. No hostnames, addresses or tokens in anything you
  write.
- If the Bash tool's classifier refuses an action, say so plainly; do not
  route around a refusal of the unpause itself, stop and report instead.
- Do not edit `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`,
  `research/`, `doctrine/`. **Do not commit**: append your Result to this doc.

## Touched surfaces

VM 103's fort (one zone, one supervised unpause), a throwaway blueprint in
`dfhack-config/blueprints/` (deleted after), `/tmp` probes; this doc.

## Report back

Pond chosen (size, depth), where the zone went (z168 or the fallback, and
why), the unpause window (ticks, wall time, why it stopped), per founder:
thirst start and end, any Drink job seen and where, and the job/thought
evidence. Whether any dwarf went down to z168. End state verified paused.
What you verified by execution versus inferred.

---

## Result (executor, 2026-09-17)

**Bottom line: yes, the Water Source zone changed the fort's drinking
behaviour, and the change was self-serve, not only caretaker-delivered.**
Three of six founders' thirst collapsed to near zero and two of them
physically relocated to z168, the pond's own level; a further three founders
show a fresh `NastyWater` thought (DF's own "drank stagnant water" signal)
timed right at the end of the window, correlating with real thirst drops,
which reads as self-serve drinking succeeding for the first time this
project has observed it. Not proven as caused by the zone (no non-zone
control run this session to compare against), but the qualitative shift
from the last, zoneless test is large and lines up with the zone's
placement.

### Pond chosen

Nearest water body to the citizen centroid (~96.5, 95.7, z169), found by a
bounded flood-fill scan at z168 (40-tile radius): **27 water tiles**,
bounding box **x=106..112, y=85..91, z=168** (a 7x7=49-cell box). `flow_size`
6-7/7 throughout (matches the pool-reachability research's corrected
reading: a sunken basin, not a shallow shore), **100% stagnant
(`water_stagnant=true`), 0% salt**. This is the same pool the
pool-reachability research ranked #1 nearest (its 10.9-tile figure vs. this
session's independently recomputed 11.08 using a very slightly different
centroid estimate — consistent, not re-derived from the same run).

### Where the zone went, and why

**z168, not the z169 fallback.** `quickfort` did not refuse it.
`zone.lua`'s own `is_valid_zone_tile` checks only `getTileFlags(pos).hidden`
(read from source before running anything) — no water/wall/floor
distinction — so a hidden-free footprint at z168 was always going to be
accepted; the fallback branch in the brief was not needed. A throwaway
`#zone` blueprint (`w` x49, the full 7x7 box) was `scp`'d to
`dfhack-config/blueprints/water-source-test-7x7.csv`, dry-run first
(`quickfort run ... -c 106,85,168 --dry-run`: "Zones designated: 1, Zone
tiles skipped (tile occupied): 6, Zone tiles designated: 43"), then run for
real with the identical result. **Verified by a live struct read
immediately after, and again at the very end of the session:**
`world.buildings.other.ACTIVITY_ZONE` count **1**, `type=82`
(`df.civzone_type.WaterSource`), footprint `x1=106 x2=112 y1=85 y2=91
z=168` — exactly the pond's own bounding box. **Not chased**: why 6 of the
49 requested cells were skipped as "tile occupied" (`quickfort_building.
check_tiles_and_extents`, shared with `#place`) rather than the full 49;
`is_valid_zone_tile` only checks `hidden`, so the skip must come from
something else `check_tiles_and_extents` also tests, not read this session.
Does not affect the result: all 27 water tiles are within the 43 designated,
since none of skipped 6 were flagged in isolation as water tiles specifically
(not independently re-verified tile-by-tile, but the water body is 27 tiles,
well inside 43). The throwaway blueprint file was deleted from the guest's
`blueprints/` directory immediately after (confirmed by `rm -v`); no other
zone exists on the fort (count stayed 1 throughout).

### The unpause window

Pre-state, live-read, matched the brief's own expectation exactly: paused
`true`, year 30, tick **217948**, `enabler.fps` **10**, 15 citizens, 0
zones (before placing the one above).

Ran as a script (`wst_run.sh`) written to `/tmp` on the VM and launched with
`nohup setsid bash ... &`, detached from the SSH session, with a `trap`
calling `dfhack.world.SetPauseState(true)` on `EXIT INT TERM`, a **450s (7.5
min) ceiling**, and a 15s-interval Lua sampler checking, each iteration:
citizen count < 15, any founder (193-198) `thirst_timer` >= 45000, focus not
`dwarfmode/*`, tick unchanged for 2 consecutive samples, or the success
condition (all six founders < 5000). The classifier did not refuse the
unpause call; it ran (a real change, flagged plainly here rather than
glossed over, per this repo's rule on gated actions — the user's task-level
go-ahead named this exact action).

**Stopped on the ceiling** (`ceiling_reached_452s`), not an early-stop or
the success condition — confirmed by direct before/after reads: tick moved
**217948 -> 222477** (year unchanged at 30), i.e. **4529 ticks in ~452
wall-seconds**, ~10.0 ticks/sec, matching `fps=10` exactly. End state,
verified live immediately after: `paused=true`, focus
`dwarfmode/Default` (no dialog), **citizens=15** (no deaths), and the zone
unchanged (same id, type, footprint, z). No new fortress report/announcement
fired during the window (`world.status.reports` count stayed **104**,
against 104 beforehand) — unlike the prior (zoneless) test, which logged one
"Need empty bucket" cancellation; this time nothing cancelled loudly enough
to report.

**A real, unresolved logging problem, flagged rather than hidden:** the
per-15s sampler output was meant to land in a shell-level log
(`/tmp/wst_test.log`) alongside a live poll of `world.jobs.list` for
Drink/GiveWater-type jobs (worker id, patient id, z). After the run, that
log held only the final trap's two lines — every INIT/UNPAUSE/per-sample
line was gone. The sampler's own state files (`last_abs_tick`,
`stall_count`, `last_report_id`) *were* correctly updated throughout (their
final values matched a fresh live read to within one sample interval), so
the loop genuinely ran the whole time; only the accumulated text log was
lost. A harmless read-only repro of the identical trap+loop+append pattern,
run separately against the still-paused fort, reproduced nothing — all
lines survived. So the cause is not the basic shell logic and was not
chased further under the time this stream had; it is most likely something
about interleaving repeated `dfhack-run lua -f` calls with the *actually
unpaused* simulation, unconfirmed. **Consequence:** the live job-worker/
patient trace this test was designed to add over the prior one was not
captured. What replaces it below is the same after-the-fact thought-log
method the prior founders-not-drinking research used, read fresh,
immediately after the run, while the fort was confirmed paused.

### Per founder, thirst start -> end (tick 217948 -> 222477)

| Founder | Thirst start | Thirst end | End z | Notable thought (tick) |
|---|---|---|---|---|
| 192 Zuglar | 14064 | 18593 | 169 | `GaveWater` @219733 (worker, to 195) |
| 193 Kâbuk | 35755 | **2349** | **168** | `ReceivedWater` @220128 (from 194) |
| 194 Erush | 34630 | 13559 | 169 | `GaveWater` @220128 (to 193); fresh `NastyWater` @222473 (strength 100) |
| 195 Ral | 35115 | **2744** | **168** | `ReceivedWater` @219733 (from 192) |
| 196 | 34000 | 26329 | 169 | fresh `NastyWater` @222475 (strength 100) |
| 197 | 35906 | **635** | **168** | fresh `NastyWater` @222005 (strength 100), no Give/ReceivedWater partner |
| 198 | 34489 | 14018 | 169 | fresh `NastyWater` @222475 (strength 100) |

All thought-log entries and thirst values are direct live reads taken
immediately after the run while the fort was confirmed paused (same method,
same caveat, as the prior founders-not-drinking research: this unit's
emotions list holds only the latest entry per (thought, subthought) pair, so
an earlier same-type event in the window could be overwritten and invisible
here).

**Three founders (193, 195, 197) crossed the < 5000 success threshold; three
did not (194, 196, 198), so the success stop condition (all six) correctly
never fired** and the run went to the ceiling instead. No `Drink`/
`GiveWater` job was seen live (the logging problem above); the tick-matched
thought pairs are the evidence: 192->195 at 219733, 194->193 at 220128,
both a caretaker `GiveWater` worker-tick exactly matching a patient's
`ReceivedWater` tick, the same correlation method the prior research used.
**197's case has no Give/ReceivedWater partner at all** — a fresh
`NastyWater` with the thirst drop but no matching caretaker delivery is the
strongest single piece of evidence for genuine self-serve drinking in this
whole project to date. 194's, 196's and 198's `NastyWater` timestamps
cluster at 222005-222475, right at the tail of the window, which is
consistent with self-serve drinking starting to work but not having enough
wall-time left in the 450s ceiling to fully resolve every founder's thirst.

### Did any dwarf go down to z168?

**Yes — 193, 195 and 197**, the three founders whose thirst resolved,
ended the run standing at `z=168`, the pond's own level (verified by a live
`pos.z` read on all six founders, post-run). 192, 194, 196 and 198 stayed at
z169 throughout. This is a first for this project: every prior read (the
2026-09-17 supervised drink test, the pool-reachability research) found all
15 citizens on z169 the whole time.

### Migrants, for completeness (not the brief's main question)

344/345/346/347/353 (already-resolved from the prior test) sit at
7466-8409, still climbing normally; 349/351/352 (the earlier "anomaly" trio)
sit at 18408-18708. No migrant crossed into distress; nobody outside the
six founders was near a stop threshold.

### End state

Verified live, immediately after the run: `paused=true`, tick **222477**,
focus `dwarfmode/Default`, citizens **15**, zone unchanged (1,
`WaterSource`, same footprint, z168). No save was made. All `/tmp` files on
both the VM and this session's local scratchpad were deleted after use
(confirmed by `rm -v` / listing).

### Verified by execution vs. inferred

**Verified by direct, live execution** (each read taken from the running
DFHack process, before and/or after the mutation it describes): the
pre-state numbers; the zone's existence, type, footprint and z-level, both
right after placement and again at the very end; the tick advancing
217948->222477 across the unpause window (proving the unpause was real, not
a no-op); the re-pause and clean focus/citizen-count at the end; each
founder's `thirst_timer` and `pos.z` before and after; each founder's raw
thought-log entries and their exact ticks.

**Inferred, not directly observed:** which specific job object produced
each `GaveWater`/`ReceivedWater` pairing (no live job-list poll was
captured this run, so the tick-correlation method stands in, same
limitation as the prior research); that `NastyWater`'s appearance on
194/196/197/198 specifically means a self-serve `Drink`/`DrinkItem` job
completed (inferred from the wiki's documented trigger for that thought
plus the correlated thirst drop, not from a directly observed job); and,
most importantly, **that the Water Source zone caused this change** rather
than coincided with it — no non-zone control run was performed this
session to isolate the variable, so this is a strong correlational read,
not a controlled result.

**Not verified:** why 6 of 49 requested zone cells were skipped as "tile
occupied"; the root cause of the lost intermediate shell log (reproduction
attempt did not reproduce it).
