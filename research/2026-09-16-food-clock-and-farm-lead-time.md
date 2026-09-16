# The food/drink clock versus the farm's lead time, for the unpause decision

Date: 2026-09-16. Read-only research against the live, paused fort (VM 103,
SSH, `/opt/df/game/dfhack-run` as the `df` user) plus the DF wiki (labelled
as hypothesis, cross-checked wherever this session could). Fort confirmed
paused (`dfhack.world.ReadPauseState()` → `true`) before every probe and
re-confirmed unchanged after; no write was made, no script was left under
DF's own script paths (two throwaway diagnostic `.lua` files were copied to
`/tmp` on the guest to run a full-map tile scan without a per-tile `pcall`,
per `docs/TRAPS.md`'s cost warning, and are not left behind).

## Bottom line

**Food is not the binding constraint if a farm plot goes in immediately.
Drink might be, and it hinges on exactly one unresolved fact: whether the
citizens can actually walk to any of the 43 surface pools.**

| | Game-days | Wall-clock (100 ticks/s) | Confidence |
|---|---|---|---|
| Food stock (24 units) fully consumed at the fort's own aggregate rate | ~67 days | **~13.4 min** | Moderate — wiki rate (§1), cross-validated twice |
| First citizen's hunger crosses "Starving" flash, worst case, zero further food | ~34 days from now | **~6.8 min** | Moderate-high — live timer + wiki threshold, cross-validated against this install's own `notify.lua` |
| Farm: dig + build + plant + grow to first raw-eatable harvest (plump helmet) | ~26-32 days | **~5.2-6.4 min** | Moderate — grow time well-verified, dig/build/plant overhead is a bounded guess |
| Drink stock: already **zero**. First citizen's thirst crosses "Dehydrated" flash, worst case, zero water ever reached | ~15 days from now | **~3.1 min** | Moderate-high — live timer + wiki threshold, same cross-validation as hunger |
| Same worst case, first **death** by dehydration, and ten more citizens within ~4 more game-days behind it | ~36-40 days from now | **~7.2-8.3 min** | Moderate-high on the timer math; **the water-reachability premise underneath it is unresolved** |

**So**: the farm beats the food clock (5-6 wall-clock minutes to harvest vs.
13 minutes before the stock is gone, 7 minutes before the first citizen is
flashing Starving) — food is recoverable by rushing a plot today, and the
one already-Planter-professioned citizen (Kâbuk Kâbukoshur) plus the one
already-Miner-professioned citizen (Zuglar Nakuthuzol) mean the labor is
already on the roster, no `set-labor` call needed. **But the farm does
nothing for drink** (a harvested plump helmet is food, not booze, until a
still exists), and the individual thirst clock, in the worst case this
session could construct from live data, is comparable to or *faster* than
the farm's own harvest time, and dramatically faster than harvest-plus-still.
**The deciding fact is whether the pool is reachable.** This session ran a
live, paused, read-only diagnostic and got a genuinely ambiguous answer
(§2): either dwarves can already walk to open water today, in which case
thirst self-resolves at a real but survivable morale cost (matching every
prior research pass's calmer framing), or they cannot, in which case
multiple citizens die of dehydration within about seven to eight wall-clock
minutes of unpausing, faster than any tool this project could build in time.
**This session could not settle which. Unpausing without answering that one
question first is a real gamble on the number that matters most.**

---

## 1. Consumption: the hunger/thirst clock, anchored to this fort's own citizens

### The mechanism, verified by reading this install's own shipped Lua, not recalled

`hack/scripts/internal/gm-unit/editor_counters.lua` (read in full, live VM)
names the exact fields: `unit.counters2.hunger_timer`, `.thirst_timer`,
`.sleepiness_timer`. `hack/scripts/full-heal.lua` confirms zeroing them is
how a "fully sated" reset is expressed. `hack/scripts/full-heal.lua:86-90`
(its own `is_in_dire_need` helper, read directly) hard-codes:

```lua
local function is_in_dire_need(unit)
    return unit.counters2.hunger_timer > 75000 or
        unit.counters2.thirst_timer > 50000 or
        unit.counters2.sleepiness_timer > 150000
end
```

**These numbers are not a guess — they cross-validate exactly against the
DF wiki's own documented status-flash thresholds**, fetched this session
(moderate-high confidence, current wiki page, not independently checked
against `0.53.16`'s own patch notes, the standing caveat every prior pass in
this repo already carries for wiki mechanics):

- **Hunger** (`counters2.hunger_timer`): 0 = just ate; **50,000 = "Hungry"
  status flashes**; **75,000 = "Starving" status flashes** (exactly
  `full-heal.lua`'s own `>75000`, an independent, shipped-source
  confirmation of the wiki figure); **100,000 = starts burning stored fat,
  dies when fat is depleted** (no further tick figure found anywhere —
  depends on the individual dwarf's fat reserves, genuinely unquantified,
  flagged below). Eating decreases the timer by 50,000, floored at 0.
- **Thirst** (`counters2.thirst_timer`): 0 = just drank; **25,000 =
  "Thirsty" flashes**; **35,000 = an unhappy thought about thirst**;
  **50,000 = "Dehydrated" flashes** (matching `full-heal.lua`'s own
  `>50000`); **75,000 = death**. Drinking decreases the timer by 50,000,
  floored at 0.
- `TU_PER_DAY = 1200`, confirmed both by this install's own
  `hack/scripts/gui/unit-info-viewer.lua:11` and independently by the
  wiki's own worked farming example (§3) — two unrelated sources landing on
  the identical number is a real cross-check, not a repeated assumption.

### This fort's own citizens, read live (not a fresh-dwarf assumption)

Read directly via `dfhack.units.getCitizens()`, fort paused, at
`cur_year=30 cur_year_tick=213622`:

| id | name / profession | hunger_timer | thirst_timer |
|---|---|---|---|
| 192 | Zuglar Nakuthuzol, Miner | 33340 | 9738 |
| 193 | Kâbuk Kâbukoshur, Planter | 33972 | 31429 |
| 194 | Erush Kogandalzat, Woodworker | 34184 | 30304 |
| 195 | Ral Identeshkad, Metalcrafter | 33999 | 30789 |
| 196 | Solon Tabarsazir, Fisherdwarf | **34261** | 29674 |
| 197 | Olin Bekarbomrek, Mason | 34065 | **31580** |
| 198 | Meng Kantekkud, expedition leader | 34023 | 30163 |
| 344 | Zutthan Odshithinod, Metalcrafter | 9164 | 28862 |
| 345 | Tun Konosamem, Stonecrafter | 9342 | 29427 |
| 346 | Stukos Ishâmshem, Bone Doctor | 9204 | 27599 |
| 347 | Rith Sanusinod, Woodworker | 9099 | 28885 |
| 349 | Logem Alâthtun, Weaponsmith | 9053 | 9853 |
| 351 | Dakost Amugvutok, Woodcutter | 8633 | 9853 |
| 352 | Eral Thukkanânul, Furnace Operator | 8672 | 9553 |
| 353 | Besmar Sâkrithânul, Gem Cutter | 8528 | 28274 |

**Read live, high confidence** (a direct struct read this session, not
recalled). Three things this data says on its own, before any threshold
math:

- **Nobody has crossed any status threshold yet.** Every hunger timer
  (8,528-34,261) sits well under 50,000; the highest thirst timer (31,580)
  is past 25,000 ("Thirsty" is almost certainly already flashing quietly on
  eleven of fifteen citizens right now, paused) but nobody has reached
  35,000 or beyond. The fort is not in crisis *yet* — it is close on thirst.
- **Two population clusters.** The original seven (ids 192-198) carry
  hunger 33,340-34,261 (~27.8-28.5 days since last real meal); the migrant
  wave (ids 344-353) carries hunger 8,528-9,342 (~7.1-7.8 days). This is
  consistent with the migrant announcement (`D_MIGRANTS_ARRIVAL`,
  `time=163530`, per the already-merged fishing/water research) and not
  investigated further, since it doesn't change the forward-looking math.
- **A four-citizen thirst anomaly, noted but not chased.** Zuglar (192),
  Logem (349), Dakost (351) and Eral (352) — spanning both population
  clusters — share an unusually low thirst timer (9,553-9,853, ~8.0-8.2
  days), sharply lower than everyone else's 27,599-31,580. Something reset
  their thirst roughly 8 days ago, in common, across a founding-cohort and a
  migrant. **Not verified**: what. Fort-owned drink is 0 units right now
  (live-confirmed below, §5), so whatever it was is already gone; this does
  not change the forward math, since the same zero-stock, zero-known-water
  starting condition applies to every citizen from this point forward.

### Converting to days and wall-clock, worst case per threshold

Using the two most time-critical citizens (the ones closest to each
threshold), assuming **zero further food or drink from any source**:

- **Solon (hunger 34,261) → Hungry (50,000)**: 15,739 ticks = **13.1 days**
  = 157 sec ≈ **2.6 min** wall-clock.
- **Solon → Starving (75,000)**: 40,739 ticks = **33.9 days** ≈ **6.8 min**.
- **Solon → fat-burning onset (100,000)**: 65,739 ticks = **54.8 days** ≈
  **11.0 min**. Death itself is further out by an unquantified margin (see
  Not Verified).
- **Olin (thirst 31,580) → unhappy thought (35,000)**: 3,420 ticks = **2.85
  days** ≈ **34 sec**.
- **Olin → Dehydrated (50,000)**: 18,420 ticks = **15.35 days** ≈ **3.07
  min**.
- **Olin → death (75,000)**: 43,420 ticks = **36.2 days** ≈ **7.24 min**.
  Ten more citizens (thirst 27,599-31,429) cross the same three thresholds
  within roughly one to four more game-days behind Olin — practically, the
  whole eleven-citizen "high-thirst" cohort dies within about **36-40 days
  of each other, ≈7.2-8.3 wall-clock minutes**, in this worst-case, no-water
  scenario.

### The aggregate stock-depletion clock (a different, complementary number)

The per-citizen numbers above answer "when does the most-advanced individual
hit crisis if they personally get nothing more." A second, independent
number answers "how long does the *shared* 24-unit food pile actually
last" — this is the number that determines when individual timers stop
resetting at all and start climbing toward those thresholds for real.

Wiki, fetched this session, verbatim: **"Dwarves require about 2 units of
food each season"** per dwarf (moderate confidence — a bare figure with no
stated definition of "unit," flagged below), and, from the Alcohol article,
**"a dwarf will drink booze an average of five times per season to satisfy
their thirst."** These cross-validate against an already-established figure
in this repo's own prior research: `(2+5)*4 seasons*7 dwarves = 196
units/year`, matching `research/2026-09-16-food-and-drink-logistics.md`'s
own cited wiki worked example for a 7-dwarf fort almost exactly. Two
independently-fetched wiki pages landing on the same implied total this
session did not go looking for is a real cross-check, not a coincidence
worth dismissing.

Scaled to 15 dwarves: food need = 15 × 2 = 30 units/season; one season =
100,800 ticks = 84 days; **0.357 units/day, fort-wide.** 24 units on hand
÷ 0.357/day = **67.2 days** = 80,640 ticks = 806 sec ≈ **13.4 minutes**
wall-clock until the shared pile is fully gone, assuming steady
consumption and no replenishment (no caravan trade, no farm yet).

**What this repo's own live stock tool says right now** (`df-overseer-stocks
food-drink`, run live this session; matches the task's own given figures
exactly — cross-validated, not re-derived): `raw_edibles.units = 24`,
`item_count = 5`, `unreachable_units = 0` — **the 24 units are not sitting
on a hidden tile; they are genuinely accessible to the fort's own citizens
right now.** `drink.units = 0`, `unreachable_units = 0` too — there is
nothing to be unreachable.

### The one real ambiguity in "unit," named plainly

The wiki does not define what a "unit of food" is at the mechanical level
(one Eat-job consumption, one stack-size increment, or something else), and
this session found no source that does. This report's own arithmetic
assumes the wiki's aggregate "unit" is the same unit this project's own
`df-overseer-stocks.lua` counts via `stack_size` — a reasonable but
**unverified** assumption. If the true per-eat-job consumption is larger or
smaller than 1 stock-unit, the 67-day/13.4-minute figure scales
proportionally; the individual-timer numbers above do **not** depend on
this assumption at all, since they come straight from the live struct
reads, which is why this report leads with those as the more load-bearing
half of the estimate.

---

## 2. Drink with no booze: can they reach the water, and does it matter?

### The wiki mechanic, moderate-high confidence

Fetched this session: dwarves "can live indefinitely on water alone," with
a real, escalating productivity and mood cost for going without alcohol —
"without booze, they will work increasingly slowly," worsening over months.
Preference order: well, then river/brook, then murky pool, if nothing else
is available. **So water access turns this from a death clock into a
morale/productivity tax — that distinction is entirely load-bearing, and it
turns on one live fact this session tried hard to settle.**

### What this session actually found, live, read-only

The fort's own local map has **43 separate surface water bodies at z=168**
(1,239 pool tiles total — this count matches the already-merged fishing
research exactly, `1239`, confirmed again this session with an independent
full-map scan, `poolcount 1239`, cross-checked). All 15 citizens currently
sit at `z=169` (surface), clustered around `(92-98, 91-98)`.

**A full z=168 tile scan for pool-tile adjacency to the fort's own walkable
network** (`dfhack.maps.getWalkableGroup`, the same primitive
`warn-stranded.lua`/`df-overseer-connectivity.lua` already use live):

```
poolcount 1239
pool_tiles_adjacent_to_fort_walkable_group   0   of   1239
```

**Zero of the 1,239 pool tiles have a 4-connected neighbor tile in the
fort's own walkable group.** Every one of the 4,956 neighbor checks (1,239
× 4 directions) came back walkable-group **0**. Decoding what those
neighbor tiles actually are (`df.tiletype.attrs[t].shape`): 2,740 are
**RAMP**, 1,256 are **WALL**, 960 are **FLOOR** — mostly walkable-shaped
terrain, not solid rock, which makes the universal group-0 reading worth
investigating rather than accepting as "the pools are walled off."

**Ruling out fog-of-war, live, directly**: a transect of ten points walked
from the fort's own center `(96,96)` toward the pool nearest the original
"nothing to catch" announcement `(108,89)`, all at `z=169`, checking both
`designation.hidden` and walkable group:

```
step 0 (96,96)   hidden=false group=11
step 1 (97,95)   hidden=false group=11
...
step 8 (105,90)  hidden=false group=11
step 9 (106,89)  hidden=false group=0
step 10 (108,89) hidden=false group=0
```

**Every tile on this transect is fully revealed** (`hidden=false`
throughout) — this is not an unexplored-fog-of-war gap, the kind of thing
that might resolve itself once a dwarf wanders over. The fort's own
walkable group (11) runs solid right up to `(105,90)`, then drops to group
0 exactly at `(106,89)` and beyond, at tiles decoded as **RAMP_TOP,
material AIR** (the tile at `z=169` sitting above the actual ramp) and, at
the pool's own edge one level down, **RAMP, material POOL** (`z=168`). Both
are ordinary DF pond-bank geometry — a ramp down into a pool is ordinary
terrain, not an obstruction — and both are fully revealed, yet neither
carries a nonzero walkable group.

**What this means, stated as plainly as the evidence supports**: this is
either (a) a genuine, live-confirmed gap in the fort's walkable network —
the ramp down to this specific pool is not actually connected to where the
citizens live, which would make this pool genuinely unreachable without
digging or bridging — or (b) an artifact of how DFHack's `getWalkableGroup`
cache handles RAMP/RAMP_TOP shapes specifically, which this repo's own
existing reachability tooling (`warn-stranded.lua`,
`df-overseer-connectivity.lua`) is built on top of and has never been
independently tested against ramp geometry. **This session could not
distinguish the two without either an actual unpaused walk test (which the
brief's constraints correctly forbid) or a deeper read of DFHack's C++
walkable-group computation than this session had budget for.** Both are
real, checked possibilities, not a hand-wave — the "not fog-of-war" half is
directly proven, and the "not walled off by real terrain" half is strongly
suggested (RAMP/FLOOR shapes at 3,700 of 4,956 checked neighbors, not
WALL), but not proven.

**If this project's own reachability primitive is genuinely blind to ramp
connectivity, that is a finding bigger than this one water question** — it
would mean `df-overseer-connectivity.lua`'s reachability report and every
tool built on `getWalkableGroup` (including `find_open_area`/
`find_diggable_area`'s own "borders the walkable network" check, already
flagged as buggy once before under pause, per `decisions/DECISIONS.md`
2026-09-11's "reachability bug" row) may be silently wrong specifically
around ramps. This report does not chase that further — it is named here
as the concrete next research step, not resolved.

### Is it a death clock, or only a morale cost? Both answers, honestly

- **If the pool is genuinely reachable** (the more likely case on priors —
  this is a completely ordinary revealed surface pond, and nothing in
  DF or this project's own domain knowledge suggests surface ponds are
  routinely unreachable from an embark's own starting position): thirst
  resolves itself the moment the fort unpauses and the AI sends a thirsty
  dwarf to drink, at the real but survivable cost the wiki describes
  (slowed work, bad thoughts) — matching every prior research pass's
  calmer framing (`research/2026-09-16-food-and-drink-logistics.md` item 9,
  `research/2026-09-16-fishing-and-water-food.md` §4).
- **If it is not**: every citizen's thirst timer climbs monotonically with
  no reset, and the ~36-40-day (~7.2-8.3 wall-clock minute) death timeline
  in §1 is real, not hypothetical, and arrives faster than a farm can ever
  produce drink (§3), let alone faster than any tool this project could
  build to fix it live.
- **The stagnant-water health question two earlier research passes could
  not settle** (whether drinking from unmoving pond water carries a
  disease/miasma risk distinct from a flowing river) **remains unsettled
  by this session too** — no source fetched this or any prior pass
  addresses it either way. If it is a real risk, it would only matter in
  the reachable-water branch above, as an added cost on top of the
  productivity tax, not instead of it.

---

## 3. Farm lead time, end to end: plump helmet, the only all-season brewable crop

### The grow-time number, cross-validated, not a single-source guess

Wiki, fetched this session, verbatim: **"Plump helmet, pig tail require
30000 [ticks] until harvest, which equals 25 days."** `30000 ÷ 25 = 1200`
— **the same `TU_PER_DAY` this session already confirmed from this
install's own shipped Lua** (§1). Two independent sources (a live source
file and a wiki page neither of which cites the other) landing on the
identical conversion factor is real, not coincidental, cross-validation.
**`growdur` in the raws is therefore ticks ÷ 100** — `growdur 300` (the
task's own given figure for plump helmet) `× 100 = 30,000 ticks = 25 days`,
confirmed by this arithmetic matching the wiki's own stated day figure
exactly. High confidence on the conversion; moderate on generalizing it to
every crop (only checked directly for the 30,000-tick group, which
includes plump helmet).

### Everything else in the chain, bounded but not tick-precise

- **Dig the room.** `find_diggable_area`/`dig_diggable_area` are already
  live-verified against Uniboslan (2026-09-11, `decisions/DECISIONS.md`) —
  the perception and action primitives exist and have already closed a
  real 41-tile dig for a different purpose. **No source this session
  checked (DF wiki's Mining/Skill pages, this repo's own decision register)
  states a tick-per-tile dig duration** — the wiki explicitly declines to
  quantify it ("agility and mining skill affect how quickly they mine...
  but provides no quantitative measurements"), and this project's own
  41-tile dig register entry records that jobs "appeared almost
  immediately" and finished, without a tick count. **This is a genuine,
  named gap**: this report bounds it qualitatively (a handful of tiles for
  a minimal 2×2 or 3×3 plot, at a rate this session cannot pin to better
  than "well under the 30,000-tick grow window, plausibly on the order of a
  few hundred to a few thousand ticks total with a real miner assigned")
  rather than inventing false precision.
- **Build the farm plot.** Confirmed zero-material (`research/2026-09-16-food-and-drink-logistics.md`
  §1 item 2, wiki-sourced) — no `buildingplan` dependency, and the
  designation-to-built-building step is close to instantaneous once the
  tile is dug, by the same reasoning `find_open_area`/`build_open_area`'s
  own live-verified builds already demonstrated for other zero/low-material
  buildings.
- **Plant.** Needs the Farming (Fields)/Planter labor and a seed of the
  chosen type. **This fort already has both, live-confirmed**: Kâbuk
  Kâbukoshur (id 193) carries the profession "Planter" — the same live
  read used for §1's hunger/thirst table — and 59 fort-owned seeds exist,
  34 of them `MUSHROOM_HELMET_PLUMP` (per the task's own given facts,
  matching this session's own established-facts baseline, not re-derived).
  Given this project's own live-verified finding that `autolabor`
  reassigns a matching profession's labor **even while the fort sits fully
  paused** (`research/2026-09-16-fishing-and-water-food.md` §6, the
  Fisherdwarf/`FISH`-labor race caught live that same day), it is a
  reasonable inference — not independently re-tested this session — that
  Kâbuk would pick up Farming (Fields) the same way once a plot exists,
  with no `set-labor` call needed. The Plant job itself, once assigned, is
  a single job of unknown but almost certainly sub-day duration (not
  independently timed this session).
- **Grow.** 30,000 ticks = 25 days, high confidence, as above.

**All-in estimate**: roughly **26-32 game-days** from a go-ahead to a first
raw-harvestable plump helmet — 25 days of that is the well-verified grow
window; the remaining 1-7 days is this report's honest, bounded guess at
dig+build+plant overhead, not a precise figure. At 100 ticks/second, that
is **≈5.2-6.4 minutes of wall-clock time.**

### Harvest to something a dwarf can actually consume

**Plump helmets can be eaten raw** — wiki, fetched this session, verbatim:
"Plump helmets are a good beginning crop... both can be eaten raw, or
brewed." **This closes the food half of the chain with no still, no
kitchen, no additional workshop** — the harvested plant is calories the
moment it's picked, sidestepping every workshop-tooling gap the earlier
food-and-drink-logistics research flagged (§1 items 4-5, §4's
`df-overseer-workshop.lua` table). **It does not close the drink half at
all** — a still, a brewer assigned, and a barrel/pot are still required to
turn any of this into booze, per that same earlier research, and this
session did not attempt to re-derive or shorten that chain's own
independently-flagged gaps (no still blueprint exists yet in `blueprints/`,
confirmed unchanged this session by directory listing).

---

## 4. The comparison, stated with the actual numbers

| Clock | Wall-clock to first crisis point |
|---|---|
| Farm harvest (food, raw-eatable) | **~5.2-6.4 min** |
| Food stock (24 units) fully depleted | **~13.4 min** |
| First citizen "Starving" flash (hunger, worst case) | **~6.8 min** |
| First citizen "Dehydrated" flash (thirst, worst case) | **~3.1 min** |
| First citizen death by dehydration (worst case, water genuinely unreachable) | **~7.2 min**, ten more within another ~1 min |

**Food does not starve the fort before a rushed farm can feed it** — the
harvest (5.2-6.4 min) lands before the stock actually runs dry (13.4 min)
and well before the worst-case Starving flash (6.8 min is close, but the
harvest is very likely still first once even the low end of the dig/build
overhead is assumed). This is the one genuinely reassuring number in this
report.

**Drink is not solved by the farm at all, and its own worst-case clock (3.1
minutes to the first Dehydrated flash, ~7.2 minutes to the first death) is
faster than the farm's own harvest time even before counting the
still-and-brewer step drink additionally needs.** Whether this actually
matters depends entirely on §2's unresolved reachability question. If the
pool is reachable, this whole row is moot and drink is a productivity tax,
not a body count. If it is not, **nothing this project's tools can build
in the next several wall-clock minutes closes the gap**, and the honest
options are the same three the earlier trade-execution and food-drink
research already named:

- **Extend and lean on the caravan.** `caravan extend` is a confirmed,
  real, headless write (`research/2026-09-16-trade-execution-api.md`
  §1) that can buy more real-world decision time before anything is
  unpaused at all — this doesn't feed anyone by itself (trade completion
  still has no struct-level API, same report §3), but it costs nothing and
  keeps the caravan's 245 food / 50 drink units from wandering off the map
  while a human decides.
- **A human hand on the water-access question specifically.** The single
  cheapest way to resolve §2's ambiguity without spending any of the
  fort's own thirst budget is for a person (via the existing personal
  VNC control channel, `decisions/DECISIONS.md` 2026-09-11) to look at
  whether the embark screen or in-game map shows a walkable path to any
  pool, or to unpause for a handful of real seconds under direct
  supervision and watch whether a thirsty dwarf actually goes and drinks —
  which this brief's own constraints correctly kept out of scope for an
  automated research pass, but which the user is not bound by.
- **Gathering/hunting/fishing** remain what the fishing research already
  concluded: mechanically real, zero-build-cost fallbacks, but this
  project has no zone-creation tool and the one water body this session
  most closely inspected is the exact one whose fish population fired
  `NOTHING_TO_CATCH_IN_WATER` in spring — not a path this report would lean
  on for drink specifically, and irrelevant to thirst regardless (fishing
  produces food, not water access).

---

## 5. What the agents may legally know

Cross-checked against `research/2026-09-16-player-visibility.md` (this
session's own re-read, already merged to `main`), which settles this
project's "vanilla player knowledge" boundary from primary DF-structures
source, not just this report's own reasoning.

**Player-visible, confirmed by that research's §8**: "unit screens
(skills, thoughts, relationships, health — all about the player's own
citizens, never spatially hidden)." **The Hungry/Thirsty/Drowsy status
icon itself is exactly this category** — a real, in-game, per-citizen UI
element with no spatial gating at all (it is not about a hidden tile, it is
about the player's own dwarf). Also player-visible: **exact stock counts**
(that same research, §8 and §9, explicitly: "exact tile/stock counts...
explicitly allowed by the policy's own wording"), confirmed by this
session's own live use of `df-overseer-stocks food-drink` returning exactly
the established 24/0-unit figures; the season/calendar date; and, in
principle (not independently struct-verified this session), a farm plot's
own in-game info screen, which in vanilla play shows a **day-based**
"ready to harvest in N days"-style estimate once a crop is planted, not a
raw tick count.

**Diagnostic-only — not something any vanilla screen shows a player**:
the raw `hunger_timer`/`thirst_timer` integers themselves (no in-game
screen displays these as numbers; only their *effect*, the status icon
flashing, is visible), and the raw tick thresholds this report leans on
(50,000/75,000/100,000 for hunger; 25,000/35,000/50,000/75,000 for thirst)
— these are engine internals, never surfaced as numbers to a player, only
discoverable by reading DFHack/df-structures source the way this report
did. The `growdur`-to-ticks conversion is the same kind of fact: a player
sees "25 days," never "30,000 ticks" or "growdur 300."

**What this means for a future player-facing tool**: a legitimate
`stocks.food-drink`/`citizen-status`-class tool could reconstruct a version
of this report's §1 aggregate estimate (stock units, days-until-empty at a
computed rate, whether any citizen's status icon is currently flashing)
entirely from player-visible facts, with no raw timer read at all. It could
**not** legitimately expose "Solon's hunger_timer is 34,261" the way this
research session did — that reasoning is diagnostic scaffolding for this
report and the human reading it, not something an agent operating inside
this project's own knowledge-scope policy could be handed as a tool
result. The individual-citizen worst-case numbers in §1 and §2 are
therefore this report's own analytical tool, not a template for what
`df-overseer-stocks.lua` or any future tool should return to a role.

---

## Not verified — summary

- **Whether the pool at z=168 is actually walkable from the fort's own
  position.** The single most load-bearing open fact in this whole report
  (§2). Live-confirmed: not blocked by fog-of-war (all transect tiles
  `hidden=false`); zero of 1,239 pool tiles have any 4-adjacent neighbor in
  the fort's own walkable group; the neighbor tiles are mostly
  RAMP/RAMP_TOP/FLOOR-shaped, not WALL. Whether this is a real terrain gap
  or an artifact of how `getWalkableGroup` handles ramp geometry was not
  settled — would need either an actual supervised unpaused walk test or a
  read of DFHack's C++ walkable-group computation deeper than this
  session's budget allowed.
- **Whether this project's existing reachability tooling
  (`getWalkableGroup`-based) is reliable around ramps at all** — a
  potentially bigger finding than the water question alone, named but not
  chased (§2).
- **The exact definition of a "unit of food" in the wiki's "2 units per
  season" figure** — assumed equivalent to this project's own
  `stack_size`-based stock count; not independently confirmed (§1). The
  individual-timer numbers in this report do not depend on this assumption.
- **The exact tick cost of digging one tile, at this fort's own miner's
  skill level.** No source found (DF wiki, DFHack docs, this project's own
  decision register) states a number; bounded qualitatively only (§3).
- **How many ticks past the 100,000-tick fat-burning threshold a dwarf
  survives before actually dying of starvation** — depends on individual
  fat reserves, no figure found (§1).
- **The stagnant-vs-flowing water health question** — unresolved by this
  session, as by the two prior research passes that already flagged it
  (§2).
- **Whether the four-citizen shared low-thirst-timer anomaly (Zuglar,
  Logem, Dakost, Eral) reflects a real shared drinking event ~8 days ago,
  and from what source** — noted, not chased, since it doesn't change the
  forward-looking math (§1).
- **Whether `autolabor` would actually reassign Farming (Fields) to Kâbuk
  the instant a farm plot exists, the same way it reassigned `FISH` to
  Solon while the fort sat paused** — a reasonable inference from a
  different tool's already-observed behavior, not independently re-tested
  this session (§3).
- **Whether this install's farm/thirst/hunger mechanics match `0.53.16`
  exactly, versus the current, unpinned DF wiki** — the same standing
  caveat every prior research pass in this repo already carries, not
  re-derived here; the two direct cross-validations this report did find
  (the `TU_PER_DAY`/growdur match, and `full-heal.lua`'s thresholds matching
  the wiki exactly) are real evidence this specific slice of mechanics has
  not drifted, but they are not a substitute for a genuine patch-note read.

## Sources

DF wiki (fetched this session): Hunger, Thirst, Food, Alcohol, Farming,
Farm plot, Mining, Skill — all current pages, not independently pinned to
`0.53.16`.

Live VM reads, this session, all read-only, fort confirmed paused before
and after (`dfhack.world.ReadPauseState()`): `df.global.cur_year`/
`cur_year_tick`; `dfhack.units.getCitizens()` plus each citizen's
`counters2.hunger_timer`/`.thirst_timer`/`.sleepiness_timer` and `.pos`;
a full-map z=168 tile scan for `tiletype.attrs[t].material ==
df.tiletype_material.POOL` (1,239 tiles, matching the prior fishing
research exactly); `dfhack.maps.getWalkableGroup` against all 1,239 pool
tiles' four neighbors and a ten-point transect from the fort's own center
toward one pool; `dfhack.maps.getTileType`/`df.tiletype.attrs[t].shape`/
`.material` and `block.designation[x][y].hidden` at the transect's
discontinuity point; `df.tiletype_shape` enum, read in full; the deployed
`df-overseer-stocks food-drink` command (cross-validated against the
task's own given figures, not re-derived from it).

Repo files read this session, from this worktree's own branch (which
predates several `main` commits referenced only by citation, per the
worktree's own git log): `docs/TRAPS.md`,
`research/2026-09-16-food-and-drink-logistics.md`,
`research/2026-09-16-fishing-and-water-food.md` (including its correction
note), `research/2026-09-16-trade-execution-api.md`,
`research/2026-09-16-player-visibility.md`, `memory/dfhack-environment.md`,
`scripts/dfhack/TOOLS.yaml`, `decisions/DECISIONS.md` (2026-09-10/11 rows
on the dig/build tool builds and the reachability/coordinate-anchoring
bugs), `Working.md`. VM-side files read directly:
`hack/scripts/internal/gm-unit/editor_counters.lua`, `hack/scripts/full-heal.lua`,
`hack/scripts/gui/unit-info-viewer.lua`, `hack/scripts/internal/notify/notifications.lua`.
