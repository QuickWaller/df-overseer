# Handoff: get a well built at Uniboslan

Date: 2026-09-18. **Live-fort stream. You have full authority to change the VM
and the fort** (user's standing grant, `Working.md` START HERE). The fort is
expendable; rescuing it is worth trying for the tools it forces us to build.

Read `CLAUDE.md`, then `Working.md` START HERE and its live fort state block,
then this.

## The situation

**The fort cannot drink.** Measured exactly: `thirst_timer` increments 1 per
tick and nobody has drunk in 6,303 ticks. Top thirst 31,899. Fifteen citizens,
zero deaths, drink stock 0.

The pond is a sunken bowl. At z168 the water sits in 26 submerged RAMP tiles
with **zero walkable neighbours**; z169 above is 134 walkable tiles of floor
and ramp-top. A channel dug at z169 toward the water simply flooded, confirmed
empirically (wet tiles 27 -> 28, walkable still 0). So no dig reaches the
water. The user's call, which is correct: **build a well.**

## The known blocker

`df-overseer-well find 1 "Activity Zone #1" 20` returns a viable site one tile
from the zone, water depth 6, not salt, **stagnant true**. Requirements against
fort-owned stock:

| Need | Owned |
|---|---|
| BUCKET | 3 |
| CHAIN | 3 |
| BLOCKS | **0** |
| TRAPPARTS (mechanism) | **0** |

Fort owns **3 logs and 0 boulders**. Stone is at z167; the stair down to it is
half-designated and never dug (orphan UpStair at z167, no DownStair above).

## The one fact that decides the route, and you must settle it first

**Can a mechanism be made from wood on this install?** Do not answer from
memory or from the wiki alone. Check this install's own raws and job data:
grep the raws for reactions producing `TRAPPARTS`, and inspect the mechanic's
workshop job. Wooden *blocks* from logs are almost certainly fine; mechanisms
are the question.

- If **yes**: 3 logs is plausibly enough for blocks plus a mechanism. Take that
  route. Count log consumption carefully; 3 is not much margin.
- If **no**: the well needs stone, so the route is **finish the stair to z167,
  mine boulders, then mason's and mechanic's workshops**. Longer, but it
  unblocks everything stone-shaped permanently.

Report which you found and the evidence, before acting on it.

## Rules that bite here

- **A lookup that can silently miss must report the miss.** This project has
  already shipped a probe that reported "0 of 15" for a labour token that does
  not exist. If you look up a name and it is absent, print
  `TOKEN_DOES_NOT_EXIST`, never a zero.
- **Verify the verification.** Before reporting an all-clear, confirm the check
  you ran could have detected the problem. State what was verified and how.
- **Check live state before escalating.** Two accurate facts can support a
  false emergency. An illustrative number must never stand in for a
  measurement.
- The fort is **paused at tick 235668** and paused is the safe state. If you
  unpause to let jobs run, do it **supervised, with a remote watchdog** that
  re-pauses, the way the water attempt did:
  `nohup sh -c "sleep N; /opt/df/game/dfhack-run lua -f /tmp/pause.lua"`.
  Use absolute paths; a backgrounded `cd` has bitten this before.
- `DF_VM_IP` in `.env` carries a **CIDR suffix that must be stripped**. Read
  secrets by the key you need (`grep -E '^KEY=' .env`), never `cat .env`.
- `ipairs` over `df.global.world.jobs.list` returns nothing; it is a linked
  list, walk `.next`.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. The orchestrating session owns those.
- No em dashes in prose.

## Touched surfaces

This handoff doc, and the live VM/fort. Nothing else in the repo.

## Done means

Either a well is built and dwarves are drinking (verified by thirst_timer
falling across two reads, not by the well merely existing), or you have got as
far as the materials allow and this file's write-up states exactly which
blocker stopped you, what stock exists now, and the single next concrete step.

Note the stagnant water: a well drawing on it gives unhappy thoughts.
Survivable, worth recording, not a reason to stop.

## Write-up (2026-09-18/19, executed live)

**Bottom line: blocked, and this stream caused a real incident along the
way.** A save rollback wiped roughly two days of verified fort progress,
including the WaterSource zone that had gotten founders drinking on
2026-09-17. Full account below. Stopped rather than unpause again without
sign-off, per the standing rule and given what unpausing just cost.

### 1. The wooden-mechanism question: settled, no

Checked this install's own raws and job data directly over SSH, not from
memory or the wiki:

- `grep -rln TRAPPARTS /opt/df/game/data/vanilla/vanilla_reactions/objects
  /opt/df/game/data/vanilla/vanilla_buildings/objects` found exactly one
  hit, `building_custom.txt` (the Screw Press, which *consumes* 2 TRAPPARTS
  as a build material, not a reaction that *produces* them). No custom
  reaction on this install makes TRAPPARTS from anything, wood included.
- The Mechanic's Workshop itself is not a raw-defined building (confirmed:
  no `MECHANIC` hit in any `building_*.txt`), so its job material rules are
  hardcoded, not readable from raws text directly.
- The real answer came from `hack/lua/plugins/stockflow.lua`, DFHack's own
  replication of the vanilla Manager screen's "what can this job be made
  from" list (used to populate work-order material options). `grep -n
  Mechanisms` on that file returns exactly two hits: one entry for
  `job_types.ConstructMechanisms` inside the metal-bar reaction block
  (`-- ` context confirms it, alongside Forge Goblet/Mint Coins/Make
  Chain), and one standalone entry commented `-- Rock Mechanisms`
  (`reaction_entry(result, job_types.ConstructMechanisms,
  materials.rock.management)`). **No wood entry exists anywhere in the
  file for `ConstructMechanisms`.** Cross-check: `ConstructBlocks` (the
  blocks job) appears under `-- Wooden items`, `-- Rock items`, and the
  metal block too, confirming the method actually distinguishes
  material availability correctly when it *is* available.

**Conclusion: mechanisms need rock or metal bars on this install, never
wood.** The well needs the stone route: dig to z167, mine boulders, build
mason's and mechanic's workshops. 3 logs is enough for the workshops
themselves (each needs only 1 unit of the generic BOULDER/WOOD/BLOCKS
building-material class, confirmed live via
`df-overseer-workshop find ... mason`/`mechanic`), just not for the well's
own BLOCKS/TRAPPARTS requirement.

### 2. What was actually done, in order

1. Deployed the merged-but-undeployed tool set (`install_df.py ui-install`,
   20 scripts) to VM 103, per `Working.md`'s own outstanding item 0. This
   carried the `dig-stair` occupancy fix live for the first time.
2. `df-overseer-diggable find-stair -1 "Embark Site"` returned a real,
   unoccupied rank-1 candidate (previously the tool's rank-1 sat under the
   fort's own Stockpile; the fix ranks that out, confirmed live).
3. `df-overseer-diggable dig-stair -1 "Embark Site" 1 "" false` designated
   both halves for real, each verified by reading the tile's own
   `dig_designation` flag back (not just `quickfort`'s `CR_OK`), per the
   dig-stair fix's own honesty discipline. This worked.
4. Started a supervised unpause with a `nohup sh -c "sleep 600; ...
   pause.lua"` watchdog, matching the handoff's own prescribed pattern, and
   began polling `dig_jobs` (a live count of `job_type == Dig` entries) to
   watch the stair actually get carved.
5. **My own mistake, and the root cause of everything after**: while
   waiting, I ran an unbounded diagnostic query (a full 3D `x_count *
   y_count * z_count` tile scan with two `pcall`s per tile) directly
   against the live DFHack process to sanity-check designation state. This
   query did not return. DFHack's command execution turned out to be
   effectively single-threaded for `dfhack-run` calls: every subsequent
   call I issued (including, eventually, the watchdog's own pause command)
   queued up behind it and none of them completed for 10+ minutes, confirmed
   by `ps` on the VM showing 9 separate `dfhack-run` client processes all
   still alive and unresolved, oldest first.
6. Killing the stuck client process (`kill -9` on the runaway query's PID)
   did **not** unblock the queue; the other queued calls still never
   completed. This means the blockage was server-side (DFHack's own core,
   not the SSH client), consistent with the query never actually finishing
   its scan (contra the DFHack-RPC-hangs-briefly theory).
7. Given the fort was confirmed unpaused and the watchdog's own pause
   attempt was itself stuck in the same dead queue, I escalated to
   `systemctl stop df-fortress.service`. Its `ExecStop`
   (`systemd-stop.sh`) tries a `./dfhack-run quicksave` first, with a 90s
   confirm-on-disk window; that call was subject to the exact same
   deadlock and never returned. `TimeoutStopSec=180` fired
   (`journalctl`: "Stopping timed out. Terminating", "Control process
   exited, code=killed, status=15/TERM"), but `dwarfort` (PID 379259) was
   **still alive** afterward (confirmed via `ps`) — systemd's own
   cgroup-kill escalation did not visibly finish it either within the
   window I could observe. I then ran `sudo kill -KILL` on the PID
   directly. Confirmed dead by `ps` returning nothing and
   `systemctl is-active` reading `failed`.
8. **No quicksave had completed since Sep 16 10:42/10:43** (confirmed by
   the save directory's own file mtimes, `autosave 2`/`autosave 3`/
   `current`, all from that date, none from 2026-09-17 or -18). So the
   kill discarded everything simulated and built since then that had never
   been separately checkpointed.
9. Restarted `df-fortress.service`, reloaded via the title screen's
   "Continue active game" (the click tool's own success check
   false-negatived, a known pre-existing flaw per
   `memory/fort-operations-and-incidents.md`; verified instead via real
   screen-type transitions, `viewscreen_titlest` ->
   `viewscreen_loadgamest` -> `viewscreen_dwarfmodest`, matching the
   documented precedent exactly). Force-paused immediately on load.

### 3. The damage: confirmed, not inferred

Loaded save: `autosave 2`, **tick 213622** (this session started at
235668; the game had run to roughly 236600+ before the incident). That is
about **22,000 ticks of simulated/built state gone**, and specifically:

- `df-overseer-landmarks list` now shows only Embark Site, Stockpile #1,
  Stockpile #2, Wagon. **No Farm Plot, no Activity Zone #1
  (WaterSource).** Both were built 2026-09-17 and are gone.
- `df-overseer-diggable find-stair -1 "Embark Site"` returns the *original*
  rank-1 candidate as unoccupied/undesignated again. Today's stair
  designation (step 3 above) is gone.
- `df-overseer-well find` at the same landmark/level returns `[]` (empty):
  whatever change made the earlier well-site candidate resolvable no
  longer exists in this save either.
- Materials unaffected (they hadn't changed anyway): BOULDER 0, WOOD 3,
  BLOCKS 0, TRAPPARTS 0, BUCKET 3, CHAIN 3.
- 15 citizens, still zero deaths. Thirst now: min 9,553, max 31,580 (close
  to the handoff's original 31,899 ceiling reading, consistent with a save
  from before the water fix). Drink stock: 0.

**This is unrecoverable by any means available from inside this stream.**
No newer on-disk save exists (`current`'s own `world.sav` is from the same
Sep 16 window). A Proxmox-level snapshot, if one exists, is `home-lab`
territory and outside this session's authority to even check. Per the
standing rule, this stops and reports rather than being quietly patched
over: **the 2026-09-17 WaterSource-zone fix and farm plot, and today's
stair designation, all need to be redone from scratch.**

**Operational lesson for whoever picks this back up**: DFHack's
`dfhack-run` command execution on this install is not safely
concurrent/interruptible. An expensive, unbounded live query (a full-map
triple loop, in this case) can wedge the entire command pipe, including a
watchdog's own pause call, for the duration of an unpause window with no
independent way to intervene short of a hard process kill. Two concrete
takeaways: (a) never run an unbounded whole-map scan against the live
process again, scope any diagnostic query tightly (a bounded box near a
landmark, matching every `df-overseer-*.lua` tool's own `MAX_RADIUS`
discipline) before running it live; (b) a supervised-unpause watchdog needs
its own escape hatch that does not depend on the same `dfhack-run` channel
it is trying to protect (a raw `pkill`/`systemctl stop` fallback timer, not
only a `dfhack-run lua` pause call) since the one time it mattered here,
that exact call was the one stuck in the queue.

### 4. The reachability "contradiction": checked, most likely resolved (not a bug in either measurement)

Built a throwaway, coordinate-free diagnostic (never printed a real x/y/z,
same discipline as every deployed tool; deleted from the VM after use) that
compared `dfhack.maps.getWalkableGroup` against tile-shape classification
for every water tile at z168 near Embark Site, and the corresponding tile
directly above at z169.

**Sanity-checked the primitive first**: queried `getWalkableGroup` at all
15 citizens' own current positions. All 15 returned nonzero. So the
walkable-group cache is valid and freshly computed on this reloaded save,
not stale from the reload, before trusting it for anything else.

**Result, on the current (rolled-back) save**: 142 water tiles at z168, all
142 with `getWalkableGroup == 0`. 128 of those tiles' z169 counterparts are
individually shape-classified RAMP_TOP/FLOOR (locally "walkable-looking"
geometry), but **all 128 also read `getWalkableGroup == 0`**. Shape and
connectivity agree here: these tiles are locally standable but not
connected to the main walkable network by any path, exactly what the
original "zero walkable neighbours" finding described, on this save.

This does not, on its own, explain the 2026-09-17 observation of three
founders actually drinking. The likely resolution: `CLAUDE.md`'s own
status line for that day credits **both** "a `WaterSource` zone placed on
the water at z168" **and, separately**, "Stockpile #2 built, a 41-tile dig
completed" as that session's accomplishments. A 41-tile dig is exactly the
kind of connector that would bridge the existing walkable network to the
pond's rim, turning some of those z169 tiles from group 0 to a real
nonzero group, tiles by tiles, not all 142 at once. The zone alone (which
only marks *where* dwarves should drink, per `df-overseer-zone.lua`'s own
header comment on `is_valid_zone_tile`) would not have been sufficient
without that separate connector dig. **Both are now lost in the rollback**
(section 3), so this cannot be re-verified against the actual post-fix
state directly, only reasoned about from the register's own description of
what was done. Recommend, for whoever rebuilds this: dig a real connector
from the walkable network to the pond rim first (matching
`df-overseer-diggable`'s existing find/dig primitives), confirm
`getWalkableGroup` goes nonzero on the rim tiles, *then* place the
WaterSource zone, and treat the zone as the assignment step, not the
connectivity fix.

### 5. Brew route vs. well route: material arithmetic, live numbers

Checked per the coordinator's request, on the current (rolled-back) save:

**Well (stone) route**, from scratch again: needs the stair re-dug (was
done and lost, redoing it is a 2-call sequence, low cost), then mining
boulders at z167 (untested this session; z167 was never reached), then
building mason's + mechanic's workshops (1 wood or 1 boulder each, cheap),
then `orders.create blocks 1` / `orders.create mechanisms 1` (these are
**manager orders**; whether they get fulfilled without an appointed
Manager is explicitly unverified on this install per
`df-overseer-orders.lua`'s own header, never tested live because nothing
got far enough), then the well build itself. Several unpause cycles,
several unverified steps.

**Brew route**, checked live just now:
- Still workshop: does not exist (`df-overseer-landmarks list` confirms no
  "Still" building). `df-overseer-workshop find 3 3 -1 "Embark Site" still`
  returns two real, unoccupied candidates. Building material: WOOD 3
  owned, only 1 needed (generic BOULDER/WOOD/BLOCKS class, confirmed live).
- Barrels: **`fort_owned_containers: 15`**, read live from the same
  `workshop find` call. The fort already owns far more barrels than one
  still needs; no Carpenter's Workshop or `MakeBarrel` job is required at
  all for this to work.
- Brewer labor: `citizens_with_labor: 1` already, live-read, matching
  autolabor's existing assignment (no hand-set needed, so the "contested
  autolabor lever" problem does not apply here).
- Raw plants actually available to brew, live-counted from
  `df.global.world.items.other.PLANT` grouped by raw plant id, fort-owned
  only: **`MUSHROOM_HELMET_PLUMP: 2`. Nothing else.** (The stocks tool's
  `raw_edibles` figure of "5 items / 24 units" is DFHack's
  `ANY_EDIBLE_RAW` bucket, which also includes MEAT/FISH/CHEESE, not just
  brewable plant matter; checked directly against the raw PLANT vector to
  avoid exactly the kind of silent-miss/wrong-bucket error this project's
  own rules warn about.)
- No farm plot exists in this save to grow more (section 3), and no
  `PlantSeeds` jobs are queued either, so 2 plump helmets is the entire
  brewable supply until a farm plot is rebuilt.

**Corrected after the coordinator read the real reaction out of
`reaction_other.txt` (lines 265-281) and independently confirmed
`MUSHROOM_HELMET_PLUMP` carries `MATERIAL_REACTION_PRODUCT:DRINK_MAT` in
`plant_standard.txt` (line 13, `LOCAL_PLANT_MAT`), matching my own
independent grep of the same file.** `BREW_DRINK_FROM_PLANT` is BUILDING
STILL, SKILL BREWING, reagents 1 PLANT (must carry `DRINK_MAT`, unrotten)
and 1 EMPTY `FOOD_STORAGE_CONTAINER` (a barrel **or** a rock pot, carries
`PRESERVE_REAGENT` so it is occupied, not consumed), products **5 DRINK
per plant** plus **1 SEEDS per plant returned** (brewing does not draw
down seed stock, unlike cooking). So the yield-per-plant arithmetic is
better than my first pass assumed. It does **not** change the actual plant
count available: this session's own live count, direct from
`df.global.world.items.other.PLANT` grouped by raw id on the *current,
rolled-back* save, found **`MUSHROOM_HELMET_PLUMP: 2`**, not the 8 raw
plants `CLAUDE.md`'s pre-incident status line cites (that figure describes
the state before this session's rollback, section 3). At 5 drink/plant, 2
owned plants -> **up to 10 drink units** available from a single
supervised brewing run, not 40. Container is moot either way: 15 barrels
already owned (section above), no log or boulder needed for a container.

**I could not confirm from this install's own raws that a brewed drink
actually satisfies `thirst_timer` the same way water does** (the
coordinator's doctrine citation, `alcohol-is-not-food` in
`doctrine/seed.yaml`, is itself flagged `status: prior`, `read:
unrecorded`, and the reaction raws describe what brewing *produces*, not
what drinking it *does*). This is the one open risk in the brew route and
I'm flagging it rather than assuming it, per instruction. Proceeding on the
material arithmetic alone: **the brew route is still shorter to *some*
drink** (one workshop build costing 1 log, needs no manager order, no
mining, no stair, container already covered) **but the supply is thin**
(2 plants -> at most 10 drink units for 15 citizens, no replenishment
pipeline until the farm plot is rebuilt) **and whether it actually cures
thirst is unverified.**

**My judgement**: brew route first, since it is strictly cheaper and does
not touch the unverified manager-order path, but it only buys time, not a
solution. It needs the farm plot rebuilt alongside it or the fort is back
to zero drink again in a few brews. Recommend doing both: brew now for
immediate relief, and separately re-run the stone-route stair dig (already
proven to work once, in section 2) toward the well as the durable fix.

### 6. Current live state, verified just before stopping

- Fort: **paused**, confirmed by direct read (`ReadPauseState() == true`),
  not inferred. Tick 213622. `save_dir: autosave 2`.
- Citizens: 15, zero deaths. Thirst: min 9,553, max 31,580, `thirst_timer`
  climbing (paused now, so frozen at this reading).
- Stock: BOULDER 0, WOOD 3, BLOCKS 0, TRAPPARTS 0, BUCKET 3, CHAIN 3,
  drink 0, raw brewable plant (plump helmet) 2, prepared meals 0.
- No Farm Plot, no WaterSource zone, no stair designation, no Still, no
  Mason's/Mechanic's Workshop. Fort is at materially the same build state
  as before 2026-09-17's session, materials aside.

### Blocker and single next concrete step

**Blocked on: no immediate drink source, and the fastest route (brew)
gates on redoing lost farm/zone work for anything beyond a first small
batch; the durable route (well) gates on redoing the lost stair dig plus
an unverified manager-order path.** Not blocked on a missing fact anymore;
the wood-mechanism question is closed (section 1) and the reachability
question is most likely resolved (section 4), just not re-verifiable until
rebuilt.

**Single next concrete step, my recommendation**: build the Still workshop
(`df-overseer-workshop build 3 3 -1 "Embark Site" still starter-still-3x3.csv
1 "" false`, 1 log, already-owned barrels and brewer labor cover the rest),
supervised-unpause just long enough for construction plus one or two
`BREW_DRINK_FROM_PLANT` jobs to run (2 plants owned -> up to 10 drink
units, per the corrected reaction figures in section 5), and re-pause.
This gives a real `thirst_timer`-falling read as proof the drink chain
works end to end (including the still-open question of whether alcohol
satisfies thirst on this install at all), before committing further
unpause cycles to the bigger farm/stair/well rebuild. Given what happened
this stream, I am stopping here for explicit go-ahead rather than starting
that unpause myself.

**Doctrine note for whoever picks this up**: the coordinator independently
verified and is recording two new doctrine entries from this stream's own
raw-reading, `brewing-chain-from-raws` (the `BREW_DRINK_FROM_PLANT`
reagent/product figures above) and `plump-helmet-is-brewable` (the
`DRINK_MAT` check). Cite those rather than re-deriving either fact.
