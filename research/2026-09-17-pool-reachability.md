# Can the dwarves of Uniboslan reach drinkable water in the surface pools?

> **CORRECTION (orchestrator, 2026-09-17, verified live before commit).** This
> report's central claim, that `getWalkableGroup` is broken around ramps (§2,
> "74 of 98"), does not hold. The test never checked what those ramps held. A
> read-only re-count over the same box (51x51 around the citizens, z168 and
> z169, fort paused at tick 217948) found: **98 RAMP tiles at z168, every one
> underwater** (flow_size above 0); **98 RAMP_TOP tiles at z169, all dry**,
> which are open space over those ramps, not ground a dwarf stands on; **12
> FLOOR tiles at z168, all underwater**; and **no dry ramp, and no dry floor
> outside group 11**, anywhere in the box. So group 0 on these tiles is the
> pathing cache being right: deep water and open space are not walkable. The
> "one confirmed dry (FLOOR) bank tile" in §1 is among the 12 wet floors, so
> fix 1 (a corridor to a dry bank) has no target. What the evidence supports is
> the user's hypothesis: **each pool is a sunken basin of deep-water ramps one
> level below the surface, visible from above, with nowhere at the water's
> level to stand.** Whether a dwarf can drink or fill a bucket from the surface
> over a ramp top is still unestablished; the founders research found that no
> dwarf drank on its own. The depth, stagnant-water and stock figures below
> were not re-checked and stand as reported.

Date: 2026-09-17. Read-only research against the live, paused fort (VM 103,
SSH, `/opt/df/game/dfhack-run` as the `df` user, DFHack 53.16-r1.1). Fort
confirmed paused (`dfhack.world.ReadPauseState()` -> `true`) at
`cur_year=30 cur_year_tick=217948` before the first probe and re-confirmed
**unchanged** (same pause state, same tick) after the last probe — no clock
advanced during this session. Ten small Lua probe scripts were written to
this session's scratchpad, `scp`'d to `/tmp` on the VM, run once each via
`dfhack-run lua -f`, and deleted immediately after (`rm -fv`, confirmed in
output each time; a final `ls /tmp/*.lua` after the last probe found none
left). Every probe used `local` only, never a `dfhack_flags` global. No probe
scanned the whole map at more than one z-level at a time (the widest scans
were a single z=168 layer, 144 blocks, and a handful of bounded 25-tile-radius
box checks); every probe hoisted its functions outside per-tile loops rather
than using a per-tile `pcall`, per `docs/TRAPS.md`'s cost warning. No game
state was written, nothing was unpaused, nothing was designated, built, or
labor-assigned.

## Bottom line

**Reachable in practice, not proven reachable by this project's own
reachability tool.** The pool is not walled off, not frozen, and — per
direct behavioral evidence already on record from the 2026-09-17
founders-not-drinking research (three tick-matched `GiveWater` deliveries) —
a dwarf has physically fetched water from it (or from one of the other 43+
pools) and carried it back, twice this session's evidence reconfirms the
geometry involved. **But `dfhack.maps.getWalkableGroup` — the primitive this
project's connectivity/reachability tooling is built on — is decisively,
live-confirmed **wrong** around RAMP and RAMP_TOP shaped tiles in this
build**, not merely suspected as the 2026-09-16 food-clock research left it.
This session found 74 of 98 RAMP/RAMP_TOP tiles within 25 tiles of the
citizen cluster that are **directly, physically 4-adjacent to a tile in the
fort's own walkable group 11**, yet themselves read walkable group **0**
("not walkable") — a contradiction that cannot be true terrain disconnection
and can only be a caching/computation blind spot for these two shapes.

**A second, independent, and separately load-bearing fact**: every single
water tile in every pool on this map's z=168 layer — all 1239 of them,
checked exhaustively, not sampled — sits at flow depth 6 or 7 out of 7. **Zero
tiles anywhere are shallow (0-3).** Per the DF wiki, version-matched exactly
to this install (v53.16), depth 4+ triggers a "Dangerous terrain" job
cancellation and swimming-skill gain, and depth 7 drowns a dwarf without
sufficient swimming skill. So even setting the cache bug aside, **no dwarf
can safely wade into any of these pools** — any working access has to be from
the dry bank, never by entering the water.

**What this means for the fort**: the pool nearest the citizens (and the
planned farm room) is not a hopeless case, and it does not need a fix aimed
at "connecting" already-connected terrain. The two real, separate problems
are (1) this project's own tools should not trust `getWalkableGroup` near
ramps, and (2) even a perfectly reachable dry bank tile only gets a dwarf
adjacent to 6-7/7 deep water, never into it — which the wiki does not say is
disqualifying for drinking, but which this session could not independently
confirm one way or the other (see §3). The cheapest genuine fixes are ranked
in §4.

---

## 1. The 3D neighbourhood of the nearest pools

### Method

A single z=168 tile scan (144 blocks, matching the 2026-09-16 food-clock
research's own affordability finding for block-level sweeps) collected every
tile whose `tiletype.attrs[t].material == df.tiletype_material.POOL`. This
matched **1239 tiles**, the same total the two 2026-09-16 research passes
already established. A 4-connected flood fill (explicit stack, no recursion,
no per-tile `pcall`) grouped them into **48 separate water bodies** — close
to, but not identical to, the earlier-established **43** (`research/2026-09-16-
fishing-and-water-food.md`'s correction note). **Not chased further**: this
is a small drift (5 more components) that could be genuine (a component that
merged/split slightly since 2026-09-16, since pond geometry is not perfectly
static) or a minor difference in flood-fill connectivity assumptions between
sessions; it does not change any conclusion below, since the same method was
applied consistently within this session.

The 15 citizens' own live positions (`dfhack.units.getCitizens()`) centroid
to roughly the same spot the persisted "Embark Site" landmark centroid
records (`(96,96,169)` — read via `df-overseer-landmarks.lua`'s internal
`get_landmark_centroid`, not the role-facing `list_landmarks`, which strips
coordinates by design per `docs/TRAPS.md`; this diagnostic-only value is
appropriate for this developer report, not for a role-facing tool result).

**The five water bodies nearest the citizen cluster**, ranked by the minimum
distance from any of their own tiles to the citizen centroid:

| Rank | Size (tiles) | Min. distance to citizens | Min. distance to Embark Site landmark |
|---|---|---|---|
| 1 | 27 | 10.9 | 11.7 |
| 2 | 31 | 19.4 | 18.6 |
| 3 | 13 | 23.1 | — |
| 4 | 4 | 23.5 | — |
| 5 | 24 | 25.4 | — |

The nearest pool and the planned farm room sit in the same general
neighbourhood of the map (both close to the Embark Site landmark, within
about a dozen tiles), not directly adjacent to each other.

### Full neighbourhood data, all five pools

For every water tile in each of the five nearest pools, this session read
its 8 (4 orthogonal used for the group-adjacency test, all 8 used for the
dedup neighbour-tile inspection) horizontal neighbours at z=168, and the
tile directly above each water tile at z=169 (plus that tile's own
neighbours, inspected the same way). Findings, all live reads:

- **Depth**: every water tile in all five nearest pools reads `flow_size`
  **6 or 7** (mostly 7). A separate, exhaustive, map-wide (not just the
  nearest five) scan of the same 1239 tiles (§ below) confirms this is
  universal — **zero tiles anywhere on this map's z=168 layer are shallow
  (0-3)**.
- **Stagnant / salt**: every water tile checked in the five nearest pools
  (99/99) carries `designation.water_stagnant = true` and
  `designation.water_salt = false`. Not independently re-checked for the
  other 43 pools this session (bounded probe, per the brief), but this
  matches, and gives a live-struct-level confirmation of, the 2026-09-17
  founders-not-drinking research's own inference (a `NastyWater` thought —
  DF's own "drank stagnant/dirty water" unhappy-thought type — appeared on
  four citizens roughly 8 days before that test).
- **Magma**: `designation.liquid_type` (a plain Lua boolean on this build,
  `false` = water — per `docs/TRAPS.md`'s own load-bearing correction, not
  the `df.tile_liquid` enum) is `false` on every tile checked. Zero magma
  contamination in any of the five nearest pools.
- **Frozen**: no tile in any pool carries `tiletype.attrs[t].material ==
  FROZEN_LIQUID` anywhere on the z=168 layer (a separate exhaustive scan,
  §2). One representative water tile's block-level temperature fields
  (`block.temperature_1`/`temperature_2`) both read **10026** — an ordinary
  ambient reading, nowhere near a freezing value. Confidence: high on "not
  currently frozen"; the block-level temperature array's exact semantics
  (whether it is the tile's own equilibrium temperature or something else)
  were not independently verified beyond this one reading.
- **z=169 directly above every water tile**: uniformly `RAMP_TOP` shape,
  `AIR` material (a small number of tiles instead read `EMPTY`/`AIR`, at
  true gaps in the pool's rim) — **never** a floor or ceiling. This is
  ordinary, unremarkable pond-bank geometry: the water is genuinely open to
  the sky, not covered.
- **Hidden / outside**: every tile checked, at both z-levels, across all
  five pools, reads `designation.hidden = false` — **fully revealed, not a
  fog-of-war gap**, matching the 2026-09-16 research's own transect finding.
  **One observation flagged but not chased**: `designation.outside` reads
  **false** at the pool tiles themselves at z=168, which is a slightly
  surprising reading for an open-air pond exposed to weather — this project's
  established terrain description (z169 = outside surface, z168 = one level
  of hidden SOIL wall) may not map cleanly onto how DF's own `outside` flag
  is actually set for a depression in the surface. Not resolved this
  session; noted as a data point, not a conclusion.
- **getWalkableGroup, every neighbour, every pool**: **zero** of the
  four-orthogonal-neighbour checks across all five nearest pools' water
  tiles (396 checks total: 108+124+52+16+96) returned anything but group
  **0**. This exactly reconfirms the 2026-09-16 finding (0 of 1239) on an
  independent re-scan, extended with the z=169-directly-above check (also
  uniformly group 0).
- **Answer to the brief's specific question**: no pool, among the five
  nearest, has a tile of depth 0-3 anywhere, and no standable tile adjacent
  to water reads walkable group 11 on either z-level — **but see §2**, which
  finds this reading is not trustworthy evidence of real disconnection.

### The one FLOOR-shaped neighbour, examined specifically

The nearest pool's own unique (deduplicated) neighbour tiles break down as:
**25 WALL** (correctly non-walkable, group 0 as expected), **26 RAMP**
(group 0 — see §2, this is the untrustworthy category), and **exactly 1
FLOOR**-shaped tile (also group 0). A single real, flat, dry bank tile
touches this pool. Its own group-0 reading is most simply explained by the
same mechanism as the ramps: whatever route connects it to the rest of the
fort's walkable network necessarily crosses one or more of the miscategorised
RAMP tiles, so it never gets merged into group 11 in the cache even if a real
dwarf could walk there. **Not independently proven** — this is the most
parsimonious reading of the evidence, not a directly observed fact about that
one tile.

---

## 2. Is `getWalkableGroup` trustworthy here? Tested directly, not inferred

### The decisive test

Every RAMP and RAMP_TOP shaped tile within a 25-tile radius of the citizen
cluster, at both z=168 and z=169 (a bounded box, not a map-wide scan), was
checked two ways: its own walkable group, and whether **any of its four
orthogonal neighbours** reads walkable group **11** (the fort's own group,
confirmed live by checking all 15 citizens' own standing tiles — every one
of them is FLOOR-shaped and group 11, which is the sanity check the brief
asked for: **ordinary ground that citizens have evidently walked on reads
correctly**).

**Result**: 98 RAMP/RAMP_TOP tiles were found in the box; all 98 read their
own group as 0. Of those 98, **74 are directly, physically 4-adjacent to a
tile reading group 11.** A tile that is orthogonally touching a walkable-11
tile and is itself a normal, undamaged RAMP or RAMP_TOP shape (not a wall,
not hidden, not a construction-in-progress) cannot genuinely be a separate,
disconnected pathing island — a dwarf can trivially step from one tile to
its immediate neighbour. **This is decisive, live-confirmed evidence that
`getWalkableGroup` returns 0 for RAMP/RAMP_TOP shapes in this area of this
build regardless of true walkability** — extending the 2026-09-16 food-clock
research's own flagged-but-unresolved suspicion ("either a real terrain gap,
or an artifact of how `getWalkableGroup` handles ramp geometry... this
session could not distinguish the two") to a settled finding: **it is the
cache artifact, confirmed by direct physical-adjacency contradiction, not a
real terrain gap.**

### Why this matters beyond this one water question

`docs/TRAPS.md`'s reference note on `getWalkableGroup` (drawn from
`hack/scripts/warn-stranded.lua`) and this install's own `Lua API.txt`
(quoted directly, `hack/docs/docs/dev/Lua API.txt` lines 2233-2239) both
describe the field as "a pathfinding cache maintained by DF" that is "only
updated when the game is unpaused." That caveat is about *staleness after a
change*, not about a shape-specific blind spot — nothing in the shipped docs
says RAMP/RAMP_TOP tiles are excluded from the cache. This session's test
shows they behave as if they are, in this specific area, right now, after
substantial unpaused wall-clock time (the fort ran unpaused from 2026-09-15
23:03 UTC onward, and again during the 2026-09-17 10-FPS supervised test) —
so "it just hasn't had a chance to update" does not fit either. **This is a
real finding for this project's own tooling**: `df-overseer-connectivity.lua`,
`df-overseer-openarea.lua`, `df-overseer-diggable.lua`, `df-overseer-
chokepoints.lua`, and `df-overseer-threat.lua` all build on this same
primitive (confirmed by direct source grep, `memory/dfhack-environment.md`
and the file headers themselves), so any of them making a reachability
judgement across a ramp is at risk of the same false negative this session
just proved. **Not chased further in this brief** (out of scope for a
water-specific research question), but worth a dedicated follow-up.

### Corroborating behavioral evidence (already on record, not re-derived)

The 2026-09-17 founders-not-drinking research (`research/2026-09-17-
founders-not-drinking.md`) already established, from primary in-game data
(exact-tick-matched `GaveWater`/`ReceivedWater` thought-log entries), that
**three `GiveWater` deliveries succeeded** during a supervised 10 FPS
unpause window, and a fourth attempt failed only on "Need empty bucket," not
on any reachability-related cancellation. A dwarf physically fetching water
and returning it to a patient necessarily crosses exactly the RAMP/RAMP_TOP
terrain this session's probe found miscategorised. That report also found a
bounded 15x15 z168/z169 scan around the citizen cluster with **zero** tiles
of `flow_size > 0` nearby — ruling out a convenient rain puddle — which
leaves the real pool(s) as the only plausible source those three fetches
could have drawn from. **Taken together, this is two independent lines of
evidence (a structural adjacency contradiction, and a directly observed
successful fetch) converging on the same conclusion: the water is reachable
in practice; the tool that says otherwise is wrong, not the terrain.**

---

## 3. What does a dwarf actually need to drink from natural water?

**Verified live, this session, high confidence** (direct enum read,
`df.job_type`): the water-related job types that exist in this build are
`Drink` (19), `DrinkItem` (20), `FillWaterskin` (21), `FillWaterskinItem`
(22), `GiveWater` (176), `GiveWaterPet` (178), `DrinkBlood` (221) — this
matches the 2026-09-17 founders-not-drinking research's own enum dump
exactly (cross-check, not re-derived).

**Verified against the DF wiki, and — unusually for this project — genuinely
version-matched, not just "current, unpinned"**: both fetched pages (Water,
Thirst) state they document **v53.16**, which is exactly this install's
DFHack version (53.16-r1.1). Quoted verbatim:

- **Depth threshold, the load-bearing figure for this whole question**: "At
  depth 4 or higher, they will cancel jobs due to 'Dangerous terrain' and
  begin to gain swimming experience. At depth 7, any dwarf that does not
  have sufficient swimming skill will drown."
- **Salt water**: "Dwarves cannot use salt water directly."
- **Stagnant water**: "Dwarves get an unhappy thought if they have to drink
  stagnant water." (Matches this pool's own live-confirmed
  `water_stagnant=true`.)
- **Preference order**: dwarves will drink "from a river, brook, or even
  murky pools if there are no other sources," preferring a well first.
- **Resting/injured dwarves**: "A resting dwarf will... depend on others to
  provide them with food and drink. They will not be given booze but receive
  water carried in buckets." (This is the mechanic the founders-not-drinking
  research already ruled out for this fort's specific case — none of the six
  founders carries any wound or Rest-job state.)

**Not found on either wiki page, explicitly checked and absent**: whether a
dwarf must stand adjacent to a water tile on the *same* z-level to drink or
fetch from it, or can do so from one level below/above via a ramp top;
whether the Drink/GiveWater job requires the acting unit to step onto the
water tile itself or can act on it from an adjacent dry tile. **This is a
genuine gap in the available primary and community sources** — this
install has no df-structures XML (confirmed absent by the founders-not-
drinking research's own file-system check, re-confirmed not re-checked this
session since nothing suggests it appeared), and DF's own engine logic is
closed-source.

**Best-available inference, clearly marked as inference, not a confirmed
mechanism**: the Drink/GiveWater job model most likely does **not** require
entering the water tile itself. Two pieces of evidence point the same way:
(a) three `GiveWater` fetches succeeded with no drowning report and no
"Dangerous terrain" cancellation logged anywhere in the fort's own
announcement/report history for that window (per the founders-not-drinking
research's own exhaustive report-log check), despite every accessible water
tile being 6-7/7 deep; (b) the standard vanilla well mechanic (§4) works by
a dwarf standing on a dry tile and lowering a bucket into a qualifying water
tile below, never by entering it. Both are consistent with "approach from
the bank, reach into the adjacent tile" being how this actually works — but
neither directly proves it, and this report does not claim it as settled.

---

## 4. Fixes, ranked by cost and risk

Fort stock, live-checked this session (`flags.trader == false` as the
fort-vs-caravan discriminator, per `docs/TRAPS.md`'s own corrected rule —
`not flags.foreign` was already shown wrong for this exact purpose):

| Item | Fort-owned units |
|---|---|
| Bucket | 3 |
| Chain | 3 |
| Barrel | 15 |
| Wood | 3 |
| Blocks | 0 |
| Mechanisms (`TRAPPARTS`) | 0 |
| Boxes | 0 |

Buildings on the whole map, live-checked: **one Wagon, two Stockpiles.**
Zero workshops of any kind, zero wells, zero farm plots — matching
`Working.md`'s already-established state exactly, not re-derived.

### 1. Cheapest, zero material: dig a short corridor/stair to the pool's dry bank edge

Digging costs no material (an established fact from the 2026-09-16 food-
clock research, confirmed unchanged). The fort already has a miner on
roster (Zuglar Nakuthuzol). This would formally connect the fort's explored
territory to the one confirmed dry (FLOOR-shaped) bank tile at the nearest
pool's edge, without ever breaching the water tile itself — **zero flooding
risk**, since it never opens a tile that carries water.

**Real caveat, not glossed over**: this fixes a *cache-level* reachability
question this session has just shown is probably not the real blocker
(§2's evidence says the water is already reachable in practice). The
founders-not-drinking research's own top three ranked hypotheses for why six
founders never got water (job-assignment scan order, a self-serve-vs-
caretaker job-routing difference, or a still-unexplained pathing quirk) are
all still open and none of them is a terrain problem this dig would resolve.
**This is the cheapest fix, but it is not guaranteed to fix the actual
observed symptom.**

### 2. Moderate cost, the standard vanilla fix: build a well over the pool

Verified against the wiki (version-matched, v53.16): a well needs **1
block, 1 bucket, 1 chain or rope, 1 mechanism**, and "a clear vertical
pathway straight down to their water source," which must be "at least 3/7
deep." This pool's water is 6-7/7 everywhere — comfortably qualifies.

**Against current stock**: the fort already has the bucket (3 on hand) and
the chain (3, substitutes for rope) a well needs. It is missing the other
two: **0 blocks, 0 mechanisms**, and has **zero workshops** to make them —
a mason's or carpenter's workshop for the block, a mechanic's workshop for
the mechanism, both zero-material buildings once dug/built (per the
2026-09-16 research's own established fact), but real, multi-step
construction, not a single action. Once built, **the well sidesteps the
disputed `getWalkableGroup`-around-ramps question entirely**, because the
draw point sits inside the fort's own unambiguous interior floor, not out on
the pool's own RAMP-shaped bank — the standard reason vanilla players build
wells rather than routing dwarves out to open water at all.

### 3. Higher cost and real risk: breach the pool directly for an interior intake

Not recommended without a floodgate, which this project has no tooling for
(confirmed absent, `research/2026-09-16-food-clock-and-farm-lead-time.md` §4
lists "flooding rock needs a floodgate/hydraulics primitive this repo has
never built"). **Flooding estimate, stated as domain/community knowledge,
not a specific cited source** (no wiki page fetched this session addressed
flow-equalization math directly): DF water spreads to equalize across all
currently-open, connected tiles up to the source body's own level. The
nearest pool alone holds roughly 27 tiles at 6-7/7 depth — on the order of
180-190 water-units of volume. Breaching it without a lock would let that
volume pour into and through any newly-dug, connected corridor until either
the water reaches the pool's own level throughout the connected space or
hits a dead end/drain — for a fort with no existing drainage, this risks
flooding well beyond the single tile intended, matching the general
"reservoir breach" hazard this project's own breach-detector work is already
aware of (`docs/TRAPS.md`, `df-overseer-breach.lua`). **Not recommended.**

### Not a fix: waiting for it to self-resolve

The 2026-09-17 supervised test already ran a real unpause window and found
six founders' thirst climbing with zero self-serve `Drink`/`DrinkItem` job
ever observed completing, while three `GiveWater` deliveries succeeded for
migrants. Whatever gates ordinary self-serve drinking is not obviously fixed
by terrain work alone, per that report's own still-open hypotheses. This
report does not add new evidence resolving that question; it narrows the
terrain half of it.

---

## Not verified

- **Whether the Drink/GiveWater job requires entering the water tile or can
  act from an adjacent dry tile.** Explicitly absent from both wiki pages
  fetched this session; no df-structures source exists on this install to
  check directly. §3's inference is reasonable but not proven.
- **Why `getWalkableGroup` specifically miscategorises RAMP/RAMP_TOP shapes
  in this build/area.** This session proved the *symptom* decisively (74/98
  physically-adjacent contradiction) but did not read DFHack's C++
  implementation of the walkability cache (not present as readable source on
  this install; would need the DFHack GitHub source at the matching tag).
- **Whether this same blind spot affects every deployed tool that calls
  `getWalkableGroup`** (`df-overseer-connectivity.lua`,
  `df-overseer-openarea.lua`, `df-overseer-diggable.lua`,
  `df-overseer-chokepoints.lua`, `df-overseer-threat.lua`) in practice, at
  scale, beyond this one area — named as a real follow-up, not chased here.
- **The 48-vs-43 water-body count drift** against the 2026-09-16 research's
  own figure. Not chased; does not change any conclusion in this report.
- **The exact meaning of `designation.outside = false` at the pool tiles
  themselves.** Flagged in §1 as an unexplained but non-load-bearing
  observation.
- **Whether the other ~43 pools not in the nearest-five set share the same
  100% stagnant / 0% salt / all-deep-water profile.** Only directly checked
  for the five nearest; the map-wide flow-depth scan (§1, confirming zero
  shallow tiles anywhere) is the one claim in this report verified across
  all 1239 tiles, not just the nearest five.
- **The precise flooding-spread distance** if the pool were breached
  directly — §4's estimate is domain/community reasoning about DF's general
  liquid-equalization behavior, not a specific cited source or a live test
  (which the brief's constraints correctly forbid).

## Sources

Live VM reads, this session, all read-only, fort confirmed paused before and
after (`dfhack.world.ReadPauseState()`, tick unchanged at 217948 throughout):
`dfhack.units.getCitizens()` and each citizen's `pos`; a full z=168,
144-block `getBlock`/`tiletype`/`designation` scan for `material ==
df.tiletype_material.POOL` (1239 tiles, matching prior research) and a
parallel scan for `material == FROZEN_LIQUID` (0 tiles); a 4-connected flood
fill into 48 components with per-component min-distance-to-citizen-centroid
and min-distance-to-Embark-Site-centroid; per-tile `flow_size`,
`liquid_type`, `water_stagnant`, `water_salt`, `hidden`, `outside`,
`subterranean` designation fields and `tiletype.attrs[t].shape`/`.material`
for every water tile and its 8 neighbours in the five nearest components, at
both z=168 and the directly-above z=169 tile; `block.temperature_1`/
`temperature_2` at one representative pool tile; `dfhack.maps.
getWalkableGroup` (via the shipped `xyz2pos` helper, `hack/lua/dfhack.lua:
448`) for every tile checked above, plus a dedicated bounded (25-tile-radius)
box scan of every RAMP/RAMP_TOP tile at z=168 and z=169 near the citizen
cluster, cross-checked against each such tile's four orthogonal neighbours'
own groups; every citizen's own standing tile's shape and group (all 15:
FLOOR, group 11); `df.tiletype_shape` and `df.tiletype_material` enums (read
in full by index, not `pairs()`, since the DFHack enum-table iterates only
its `_first_item`/`_last_item` sentinels under `pairs`); `df-overseer-
landmarks.lua`'s internal `get_landmark_centroid("Embark Site")` (not the
role-facing, coordinate-stripped `list_landmarks`); fort-owned item counts
(`flags.trader == false`) for `BUCKET`, `BLOCKS`, `CHAIN`, `TRAPPARTS`,
`BOX`, `BARREL`, `WOOD` (`ROPE` is not a valid `df.item_type` name on this
build — not chased further); `df.global.world.buildings.all` building-type
counts (Wagon: 1, Stockpile: 2, nothing else).

VM-side files read directly, this session: `hack/docs/docs/dev/Lua API.txt`
(the `getWalkableGroup`/`canWalkBetween` entries, quoted verbatim);
`hack/scripts/df-overseer-openarea.lua` and `hack/scripts/df-overseer-
threat.lua` (their own comments quoting/extending the same caveat, and
`threat.lua`'s own named, still-open "BLIND SPOT" flag for a different
reachability edge case, read for context); `hack/lua/dfhack.lua` (`xyz2pos`
definition, line 448); a `grep` across `hack/scripts/` confirming which
five `df-overseer-*.lua` files call `getWalkableGroup`.

DF wiki (fetched this session, both pages stating they document **v53.16**,
which matches this install's DFHack version exactly — a real, not assumed,
version match, unlike the "current, unpinned" caveat most of this project's
earlier wiki citations carry): Water, Thirst, Well. A third fetch (Liquids)
returned no usable content on flow-equalization mechanics; that gap is
carried into §4 as explicitly domain/community reasoning, not a citation.

Repo files read this session: `CLAUDE.md`, `docs/TRAPS.md`, `memory/
dfhack-environment.md`, `research/2026-09-16-food-clock-and-farm-lead-time.md`,
`research/2026-09-16-fishing-and-water-food.md` (including its correction
note), `research/2026-09-17-founders-not-drinking.md`, `Working.md`,
`decisions/DECISIONS.md` (skimmed for context, not cited directly), `.env`
(only the `DF_VM_IP` and `DF_SSH_KEY` keys, per the project's secrets-reading
rule).
