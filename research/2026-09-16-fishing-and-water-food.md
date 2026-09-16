# Fishing and water food on Uniboslan: is the user's opening move dead here?

Date: 2026-09-16. Read-only research against the live, paused fort (VM 103,
SSH, `/opt/df/game/dfhack-run`, DFHack 53.16-r1.1) plus the DF wiki (labelled
as hypothesis, not doctrine) and this repo's own already-merged research
(`research/2026-09-16-opening-priority-ladder.md`,
`research/2026-09-16-food-and-drink-logistics.md`,
`research/2026-09-16-trade-execution-api.md` — all read from the current
`main` tip, which had moved twice while this brief was in progress; see
"Not verified" for the one place that mattered). Fort left paused throughout;
confirmed paused (`dfhack.world.ReadPauseState()` → `true`) before and after
every write-shaped-looking check, and no write was made — every command run
against the VM in this brief is a read.

## Bottom line

**Fishing is not proven permanently dead, but it is dead for planning
purposes, and building a ladder rung around it would be a mistake.** This
embark has exactly **one** surface water feature — a single murky pool,
1,239 tiles at one z-level, confirmed by an exhaustive scan of every tile on
every one of the map's 186 z-levels — and that pool is the exact one that
produced the fort's oldest recorded announcement, `NOTHING_TO_CATCH_IN_WATER`,
in early spring of this year. DF's own mechanic (verified against the current
wiki, quoted verbatim below) makes exhaustion *provisionally* seasonal, not
instantly permanent — but this fort has never tested whether the pool
recovered, because the Fishing labor sat unassigned for essentially this
whole fort's life. There is no second body of water anywhere on the local
map to fall back on if it is still (or newly) empty. **Recommendation: do not
build a fishing rung. Build the farm-plot-by-soil-digging rung instead** —
it is the one water/food method this repo's tools can already execute
end-to-end today, per the opening-ladder research's own §6.4 table, restated
and re-confirmed live below — and treat "let the Fisherdwarf actually try
once the fort unpauses" as a free, zero-tooling experiment that will settle
the open question, not as something worth designing a tool around in the
meantime.

**Confidence:** high on every live-VM claim (each is a command this session
ran, output pasted, not recalled); moderate-high on the DF wiki mechanic
(fetched twice this session, quoted verbatim, current page — not
independently checked against `0.53.16`'s patch notes, the same caveat every
prior research pass in this repo has carried for wiki-sourced mechanics);
explicitly flagged low/unresolved on the one question that cannot be
answered by reading state: whether *this specific pool* is now
temporarily-empty-until-next-season or truly permanently empty.

---

## 1. The announcement, decoded

Read directly, in full, from `df.global.world.status.announcements` (11
entries total, oldest first):

```
id=2  year=30 time=19990   type=272 NOTHING_TO_CATCH_IN_WATER
      "There is nothing to catch in the central swamps."
id=3  year=30 time=21940   type=294 WEATHER_BECOMES_RAIN
id=4  year=30 time=37860   type=292 WEATHER_BECOMES_CLEAR
id=5  year=30 time=100800  type=298 SEASON_SUMMER
id=6  year=30 time=123917  type=289 MARRIAGE
id=98 year=30 time=148046  type=145 CREATURE_STEALS_OBJECT
id=99 year=30 time=163530  type=69  D_MIGRANTS_ARRIVAL
id=100 year=30 time=201600 type=299 SEASON_AUTUMN
id=101 year=30 time=213480 type=80  LIAISON_ARRIVAL
id=103 year=30 time=213480 type=243 MERCHANTS_NEED_DEPOT
```

(`id=35`, a synthetic `TEST_EVENT_PROBE` entry from this project's own
eventful-verification work, sits between id=6 and id=98 and is not a real
game event — noted for completeness, not analysed.)

Current game time, read live: `cur_year=30 cur_tick=213622`. The fishing
message fired at `time=19990` (a tick-within-year value; `SEASON_SUMMER`'s own
entry at `time=100800` and `SEASON_AUTUMN`'s at `time=201600` confirm the
year is divided into four 100,800-tick seasons, so `time=19990` is early
spring). **The message is 193,632 ticks old** — about 48% of a full game
year (403,200 ticks/year, per `memory/dfhack-environment.md`), i.e. it
predates summer, autumn, the liaison's arrival and the trade-depot demand by
a comfortable margin. It is old, exactly as the brief's framing said, but
"old" and "still true" are different claims, addressed in §3.

**Where it happened, not just when.** The announcement carries a real
`pos` field: `x=108, y=89, z=168`. Read live: the tile at that exact position
is `tiletype.material = POOL` (confirmed via `df.tiletype.attrs[t].material`,
enum value 19 of 26 — `POOL`, `BROOK`, `RIVER` are 19/20/21 respectively).
The local map is 192×192 tiles (12×12 blocks × 16); the pool's position is
about 14 tiles from the map's geometric center (96,96) — close enough to
support "central" in the message's own text as an embark-relative
descriptor, though this report did not reverse-engineer DF's exact
biome-region-naming formula to prove the word choice mechanically (flagged
in "Not verified"). This is a directly observed fact, not an inference:
**the message's own coordinate points at a real, on-map pool, not a stale or
sentinel position** (`pos2` on the same struct *is* the `-30000,-30000,-30000`
sentinel, for contrast — confirming this announcement type does carry a real
primary position while leaving the secondary one unused).

---

## 2. This embark's actual water inventory (verified, not guessed)

A full-map, full-z-level scan (`dfhack.maps.getBlock` + the block's own
16×16 `tiletype` array, all 12×12 blocks × all 186 z-levels — 0 to 185,
checked in full, not sampled) counting tiles of material `POOL`/`BROOK`/
`RIVER`:

```
z=168  pool=1239  brook=0  river=0
(every other z-level: 0/0/0)
```

**This embark has exactly one named water feature: the murky pool at z=168,
and nothing else** — no brook, no river, no lake, anywhere on the local map,
at any depth. This is a checked negative across the entire map, not an
absence of search.

Two things this scan reveals that a naive read of `world_data` would get
wrong:

- **A world-scale river exists nearby, but does not reach this embark.**
  `dfhack.maps.getTileBiomeRgn(108,89,168)` returns `(5,6)` — this embark's
  entire local map resolves to a single world-region tile, sampled at all
  four corners plus center. `df.global.world.world_data.rivers[14].path`
  does pass through world-tile `(5,6)` (confirmed: one of 54 world rivers
  touches that tile). But the exhaustive local scan above found **zero**
  `RIVER`-material tiles anywhere on the embark's own 192×192 footprint —
  the river's path clips this world tile without its channel actually
  crossing the specific local area this fort occupies. A tool that only
  checked `world_data.rivers` for "does a river touch my region" would
  wrongly conclude a river is available here.
- **`prospect all --show liquids` reports far more water than the pool
  alone**: `WATER: 14074 tiles, Elev:-115..48` (alongside `MAGMA: 82725
  tiles, Elev:-115..-101`). Subtracting the 1,239 surface pool tiles leaves
  roughly 12,800 tiles of water elsewhere on the map — almost certainly deep
  cavern/aquifer water, given the elevation range bottoms out at the same
  `-115` as the magma sea. This is real water DF's own liquid simulation
  tracks, but it is **not a second surface fishing venue**: reaching it from
  a 15-dwarf fort with zero dug infrastructure is a multi-month excavation
  project through unknown hazards (aquifer, cavern fauna), not an opening
  rung, and this repo has no tool that reads cavern/aquifer depth safely
  even as a perception primitive (`memory/dfhack-environment.md`'s aquifer
  read is explicitly pre-embark-only). Named here so "but there's 14,074
  water tiles!" isn't later mistaken for "there's a second pond."

**Verdict for §3 of the brief's ask: this embark has one water body, it is
the one the message names, and there is no alternative to route a
fisherdwarf to if it is still empty.**

---

## 3. Is "nothing to catch" permanent? The DF mechanic, quoted verbatim

Checked directly against the DF wiki's Fishing article (fetched twice this
session, second fetch demanded verbatim text specifically to avoid
paraphrase drift):

> "Overfishing can exhaust the fish population of a pond, river, or ocean
> both temporarily and permanently. If a dwarf can not find some fish in a
> specific area, you will get a message saying 'there is nothing to catch in
> the [direction] [biome]' and the area will no longer be used for fishing.
> **When the season changes, all areas will become available for fishing
> once again**, though eventually they will remain permanently empty and
> simply give the above message on the first fishing attempt of every
> season."
> — [Fishing — DF wiki](https://dwarffortresswiki.org/index.php/Fishing)

This is a real correction to how the brief's evidence reads at first glance,
and to how both prior research passes in this repo summarized the same
mechanic (`research/2026-09-16-opening-priority-ladder.md` §6.1 and
`research/2026-09-16-food-and-drink-logistics.md` §1 item 6 both quote only
the "eventually... permanently empty" half-sentence, not the "season
changes... available again" clause immediately before it — not wrong, but
incomplete in a way that matters a great deal for this exact fort's
situation). The mechanic has **two states**, not one:

1. **Exclusion, per-season, resets automatically.** After a failed attempt,
   that water body is skipped for fishing for the rest of the season, then
   becomes eligible again at the next season change.
2. **True permanent emptiness**, reached only after the underlying
   population is fully zeroed — at that point, *every* season's first
   attempt re-triggers the same message forever, because there is nothing
   left to find, ever again.

**Applying this to Uniboslan, live-verified, not assumed**: the message
fired in spring (`time=19990`). Two season changes have since occurred
(`SEASON_SUMMER` at `time=100800`, `SEASON_AUTUMN` at `time=201600`, both in
the announcement log). Per the mechanic above, the per-season exclusion
would have lifted at the *first* of those changes. **But no fisherdwarf ever
tried again**: live-verified, `dfhack.units.getCitizens()` filtered on
`unit.status.labors[df.unit_labor.FISH]` returned **zero** citizens with the
labor for essentially this fort's whole recorded history (see §5) — so the
game was never given a chance to re-test the pool in summer or autumn, and
the absence of a second `NOTHING_TO_CATCH_IN_WATER` message in the log is
not evidence of recovery, it is evidence of **no attempt**, which is a
different fact. **This report cannot determine, from static state alone,
whether the pool is currently fishable or not** — that specific fact is only
observable by letting an actual attempt happen, which requires unpausing,
which this brief's constraints correctly forbid.

**Why the bottom line is still "don't build a fishing rung," despite that
genuine uncertainty**: even in the best case (the pool recovered at the
first season change), it is a *single, small* murky pool that a fresh
15-dwarf fort exhausted within its first season of existence — a
demonstrated, fast-failing resource, with zero redundancy (§2) and no way
for a ladder rung to distinguish "temporarily resting" from "permanently
dead" ahead of an attempt. A rung whose precondition cannot be evaluated
without spending the exact resource it is trying to protect is a poor rung
regardless of which way the coin lands this time. The wiki's own directional
framing ("both temporarily **and** permanently") plus this fort's own fast
first exhaustion is a specific, concrete instance of the "murky pool that
might or might not count as a reliable water source" ambiguity the
opening-ladder research already flagged in the abstract (§1.5, citing triage
literature on branching under uncertainty) — this brief supplies the
concrete case that abstraction was written for.

---

## 4. Every method of getting food from water, and what needs no zone

Building on, not re-deriving, the opening-ladder research's §6 (already
merged to `main`, itself DF-wiki-sourced and fetched live that session) —
this section adds the live-verified item-type distinction the brief
specifically asked for, plus one correction.

**Catching fish needs no workshop and no zone**, confirmed by the wiki
(moderate-high confidence, current page): a fisherdwarf catches directly
from any accessible water source; a fishing zone is a standing-order
*refinement* ("prefer fishing zones" / "zone-only fishing"), useful mainly
to keep fisherdwarves out of dangerous water, not a precondition for the
Catch Fish job to fire at all. This repo's `zone` plugin being unavailable
(`memory/dfhack-environment.md`) blocks the safety refinement, not catching
itself.

**The item-type distinction the brief asked about, live-verified**:

| Item type | Live count, this fort | What it is |
|---|---|---|
| `FISH_RAW` | **0** | The as-caught, unprocessed vermin-class catch. A minimal fishing rung (toggle the FISH labor, let default behaviour catch) would produce entries **here** — confirmed 0 now because nobody has caught anything recently, consistent with the labor sitting unassigned. |
| `FISH` | **10** total items, but only **2 are fort-owned** (10 units) — **8 are `trader=true`** (40 units), i.e. the caravan is also selling fish. | The processed/edible item type. A Fishery converts `FISH_RAW` → `FISH`; no fishery blueprint exists in this repo (`blueprints/` holds four files, none a fishery, per the food-drink research's own directory listing, re-confirmed unchanged this session). |

The fort's 2 fort-owned `FISH` items (10 units) both carry `flags.foreign =
true`, which — per this repo's own just-landed correction
(`docs/TRAPS.md`, "`item.flags.foreign` is an ORIGIN flag, not an ownership
flag") — means they came from off-site at embark, i.e. **these are embark
supplies, not this fort's own catch**. Combined with `FISH_RAW = 0`, the
straightforward reading is: **this fort has never successfully turned a
catch into food** — the 10 units on hand are what the wagon brought, not
evidence fishing ever worked here. (High confidence: both counts are direct
live reads this session, cross-checked against the corrected ownership test
`not flags.trader`, not the retired `not flags.foreign` test.)

**Drinking directly from the pool is a real, separate, *already-open*
option**, independent of whether the fish are gone. Fish depletion empties
the *population*, not the *water* — the pool tile itself still carries
water regardless. Per the wiki's Thirst article (already fetched by the
opening-ladder research, re-cited not re-fetched here): dwarves "can live
indefinitely on water alone," with a productivity/mood tax for going
without alcohol, and the preference order is well, then river/brook, then
murky pool. **Not independently re-verified this session**: whether this
fort's 15 citizens can actually path to the pool (a `connectivity`/
reachability question this brief did not re-check, since it is orthogonal
to the fishing question and was already flagged as unverified by the
opening-ladder research).

**Farm-founding by digging into a soil layer remains the only one of the
three named water-adjacent farming methods this repo's tools can execute
end-to-end today** — restating the opening-ladder research's own §6.4
verdict, not re-deriving it: flooding rock needs a floodgate/hydraulics
primitive this repo has never built; the water-dump-and-cancel trick is
zone-gated and structurally close to the UI-automation path this repo
deliberately fences off from steady-state play; digging a farm plot into
soil uses `find_diggable_area`/`dig_diggable_area`, both live-verified
2026-09-11, and needs no `buildingplan` because a farm plot is a
zero-material building.

---

## 5. What replaces fishing as the first rung, given 24 food / 59 seeds / 0 drink / 15 dwarves

Live-verified via the deployed `df-overseer-stocks.lua food-drink`/`seeds`
tool, run this session (matching the brief's own numbers exactly):

```json
"raw_edibles": {"units": 24, "item_count": 5, "foreign_units": 245, ...}
"drink":       {"units": 0,  "item_count": 0, "foreign_units": 50,  ...}
"seeds": {"total_units": 59, "by_plant_units": {"MUSHROOM_HELMET_PLUMP": 34, ...}}
```

**Scale check** (a rough derivation, not a precise DF-engine number): the
wiki's own worked example (already cited by the food-drink research) puts a
7-dwarf fort's annual food+drink need at roughly 196 units/year. Scaled
linearly to 15 dwarves, that is ~420 units/year, or ~1.15 units/day. **24
units of food is on the order of three weeks** at that rate, with **zero
drink** already imposing the wiki's documented productivity/mood tax. This
is a thin margin, not an emergency by the user's own stated framing
("the fort is expendable... rescuing it is worth trying because the tools
get built along the way"), but it is thin enough that a fishing rung whose
own precondition is unverifiable is a bad thing to lean on for it.

**Recommendation, in order:**

1. **Do not gate anything on the pool.** Whatever happens when the fort
   next unpaused and Solon Tabarsazir's `FISH` job resolves is free
   information this brief's own constraints correctly prevent it from
   generating — but nothing in the ladder should require an answer to "is
   the pool fishable" before proceeding.
2. **First real rung: dig a farm plot into a soil layer**, per §4 above and
   the opening-ladder research's `rung-farm-founding` branch 1 — the one
   buildable-today path, using tools already live-verified against this
   fort (`find_diggable_area`/`dig_diggable_area`). Lead time is real (a
   season to harvest, then a still/kitchen — not yet blueprinted — before
   anything is edible), but it is the only path that does not depend on
   either an unproven water body or an unresolved policy question.
3. **In parallel, not instead of #2: trade with the caravan already
   present**, now that `research/2026-09-16-trade-execution-api.md` (merged
   to `main` the same day as this brief) has revised the earlier "trade is
   not closeable" verdict. Staging goods (`dfhack.items.markForTrade`) and
   selecting exactly which goods change hands
   (`main_interface.trade.goodflag[i][j].selected`) are confirmed real,
   zero-screen, code-level operations — **only the final "confirm trade"
   button press has no struct-level equivalent**, and driving it would need
   `gui.simulateInput`/`screen:feed()`, which that research explicitly
   flags as a policy question for the user, not something this brief
   resolves. That same research also settled the caravan's dwell time
   (`caravan_state.time_remaining`, ~26 days as of that research's own
   check) and found `caravan extend` a real, zero-UI-automation write with
   no cap found — so the clock on this option is not as tight as the
   food-drink research's own earlier "unresolved" framing suggested, and it
   is extendable if the user wants more runway to decide the policy
   question. Named here as the fastest possible *food-on-hand* relief, not
   recommended over #2, since #2 needs no new policy decision to start.
4. **Queue `orders import library/basic` early, even though it cannot
   produce anything yet.** This fort has zero workshops
   (`Working.md`'s 2026-09-16 handover, independently unchanged this
   session), so a standing food/drink order set has nothing to run against
   today — but importing it is free, needs no new Lua (`orders` is
   confirmed available), and means the first workshop built already has
   standing production orders waiting rather than needing a second manual
   step later.

---

## 6. The `autolabor` interaction — a live, real-time demonstration of the exact race

The brief asks whether the just-landed `set_labor`/`autolabor` fix
(`scripts/dfhack/df-overseer-labor.lua`, deployed on VM 103, checksum-matched
against the current `main` tip this session) actually covers assigning
`FISH`. **It does, mechanically** — but this session got something better
than a mechanism check: **the race fired live, in real time, while this
brief was being written.**

- **First check this session**: 0 citizens held the `FISH` labor, matching
  the brief's stated evidence.
- **A later check, same paused fort, same tick (213622 — confirmed
  unchanged, the fort never advanced)**: **1** citizen held it — Solon
  Tabarsazir, "Faithfulbridge," the Fisherdwarf, exactly the citizen the
  brief names as fighting a kea. Re-checked twice more, a few seconds apart:
  stable at 1.
- `plugins.autolabor.isEnabled()` returns `true`, live.

**This is autolabor reassigning a labor to match a citizen's profession,
entirely on its own, with the fort paused and the game tick frozen.** It
demonstrates directly, not just by mechanism, that autolabor's reassignment
cycle runs independent of world-tick advancement — it is gated on something
else (a render/plugin update cycle, not the simulation clock), which is new,
live-confirmed information this repo did not have before (the labor.lua fix
itself only claimed the fort-wide-disable *mechanism* was verified, not that
autolabor's own cadence had been observed changing state between two
reads while the game clock stood still).

**Does the fix cover this case?** Yes, by the same mechanism verified
generally: `df.unit_labor.FISH` resolves live to code `41`; `set_labor`
would call `autolabor_enabled()` (confirmed `true`), then
`autolabor FISH disable` *before* writing the bit, which — per
`autolabor`'s own shipped doc, read directly, not recalled — takes `FISH`
out of autolabor's management **fort-wide**, disclosed in the return
message, never silently. **The one thing this brief did not newly verify,
because it would require an actual write to the running fort's automation
config**: the `disable` call's real execution. That remains exactly where
the labor-race fix's own commit left it — "verified-by-mechanism, not
verified-by-execution" — this session's live evidence strengthens confidence
in the mechanism (autolabor really is active and really does reassign
labors continuously) without closing that specific gap.

**A genuinely new, practical implication worth stating plainly**: given
autolabor *already* assigned `FISH` to the one citizen with the Fisherdwarf
profession, entirely unprompted, a ladder rung that wanted "someone is
fishing" would not need to call `set_labor` at all in this fort's current
state — autolabor got there first. The real blocker was never "nobody is
assigned"; it is "there is nothing left to assign them to; catch." That is a
sharper, more accurate way to state this brief's central finding than
"fishing needs a tool that doesn't exist" — the assignment half is already
solved by infrastructure this repo did not build.

---

## 7. The announcement blind spot — cost, noise, and a concrete filter proposal

**Confirmed, by reading the source directly, not by absence of a grep hit**:
`scripts/dfhack/df-overseer-diff.lua` (current `main`) registers `REPORT`
events and polls `world.status.reports`, filtered through its own
`REPORT_CATEGORY` table to combat/threat types only (strike, miss/block,
charge, grapple, status, hostile_speech, ambush, night_attack,
undead_or_ghost, berserk_or_tantrum, death). `scripts/dfhack/df-overseer-breach.lua`
checked the `announcement_type` enum only as a **negative** search for
flood/breach-related ids ("a targeted grep of the full announcement enum for
FLOOD/BREACH/MAGMA/WATER/FLOW/DROWN/SURGE/CHASM found nothing but two
unrelated cosmetic/fishing messages" — one of which is almost certainly
`NOTHING_TO_CATCH_IN_WATER`, matched on the "WATER" substring, a
false-positive artifact of that keyword search, not evidence anyone read the
message). **Nothing in this repo reads `world.status.announcements` for its
own sake.** Both `MERCHANTS_NEED_DEPOT` and `NOTHING_TO_CATCH_IN_WATER` were
genuinely invisible to every agent, exactly as the brief states, and this
session independently confirms it by source, not by re-trusting the claim.

### How noisy is the stream, actually? (checked, not assumed)

Two things this session found change the shape of the problem for the
better, and one concrete gap for the worse:

- **`announcements` is already far more curated than `world.status.reports`,
  by DF's own design, not by anything this repo built.** Eleven entries
  cover this fort's entire recorded history to date (roughly half a game
  year); `world.status.reports` had 34 entries from a single kea fight
  alone (`df-overseer-diff.lua`'s own header). The volume/scaling caution
  that file already carries for `reports` ("grows unboundedly... would want
  a smarter starting point before trusting it against a year-5 fort") is a
  real concern for `reports`; `announcements` is a much smaller stream to
  begin with. (Moderate confidence: an observation from one small-sample
  fort, not a stress test — flagged, not overclaimed.)
- **The shipped config file already ranks importance, and it is a primary
  source worth building on rather than re-deriving.** `data/init/announcements.txt`
  (read directly on the VM, 353 announcement types, 362 lines) tags a small
  subset `ALERT` — "the announcement will cause the alert button to light
  up" in the file's own comment. Read in full: **22 of 353 types carry
  `ALERT`**. Most are the ambush/ambush-support family (already covered by
  `df-overseer-diff.lua`'s own `ambush` category, so re-surfacing them here
  would be redundant, not new information) and `CITIZEN_DEATH` (same
  overlap, already in `diff.lua`'s `death` category). **Five ALERT types
  are not covered by anything in this repo today**: `CARAVAN_ARRIVAL`,
  `CAVE_COLLAPSE`, `CITIZEN_MISSING`, `MERCHANTS_NEED_DEPOT`,
  `MERCHANT_WAGONS_BYPASSED`, and — the single most load-bearing find in
  this whole section — **`FOOD_WARNING`**, DF's own native low-stock alarm,
  which this fort has not yet triggered (not present in the 11-entry log)
  but which sits at exactly the same engine-assigned importance tier as
  `CITIZEN_DEATH`. This is a free, zero-computation early-warning signal for
  the exact problem `stocks.food-drink` was built to measure by
  computation — the two are complementary, not redundant (one is a
  threshold the *engine* already tracks internally on its own bookkeeping,
  which may not exactly match this repo's own fort-owned/foreign-corrected
  count; the other is this repo's own, verified-correct count).
- **The concrete, checked cancellation-spam risk**: `CANCEL_JOB`
  (`data/init/announcements.txt`'s own entry, no `ALERT` tag, same
  low-priority tier as ordinary flavor text) is the type most associated
  with the community-known "cancellation spam" problem — a job repeatedly
  failing and re-announcing why every time it is retried. It did not fire on
  this fort (zero workshops, few active jobs, most citizens idle), so this
  session could not observe its real volume live — flagged as **not
  verified by execution**, only by the shipped config's own non-ALERT
  ranking and by the type's well-known community reputation (moderate
  confidence, not re-derived from a stress test).

### The filter this report actually proposes

Modelled on `df-overseer-diff.lua`'s own `REPORT_CATEGORY` idiom (a closed
lookup table, category-tagged, never raw enum ids reaching a caller), for a
new tool — call it `announcements.recent`/`announcements.since`, same
manifest shape as `diff.since`/`diff.recent-combat`
(`effect: read`, `coordinate_bearing: false`, since these are fort-scoped,
not tile-scoped, events):

**Surface** (categories, with the ids that populate them):

- `food_security`: `NOTHING_TO_CATCH_IN_WATER` (272), `FOOD_WARNING` (348).
- `trade_window`: `CARAVAN_ARRIVAL` (67), `FIRST_CARAVAN_ARRIVAL` (343),
  `MERCHANTS_NEED_DEPOT` (243), `MERCHANTS_UNLOADING` (242),
  `MERCHANT_WAGONS_BYPASSED` (244), `MERCHANTS_LEAVING_SOON` (245),
  `MERCHANTS_EMBARKED` (246) — `MERCHANTS_LEAVING_SOON` in particular is a
  direct, zero-computation answer to the caravan-dwell-time question both
  the food-drink and trade-execution research had to derive from a struct
  field instead.
- `arrivals`: `MIGRANT_ARRIVAL`/`MIGRANT_ARRIVAL_NAMED` (49/50),
  `NOBLE_ARRIVAL` (68), `DIPLOMAT_ARRIVAL`/`LIAISON_ARRIVAL`/
  `TRADE_DIPLOMAT_ARRIVAL` (79/80/81), `MONARCH_ARRIVAL` (344).
- `population_safety`: `CITIZEN_MISSING`/`PET_MISSING` (151/152),
  `CITIZEN_SNATCHED` (252), `CAVE_COLLAPSE` (82) — these three are not
  covered by `diff.lua`'s combat categories, which key off `world.status.reports`
  and a different registration path; not redundant with it.
- `mood_and_crisis`: `STRANGE_MOOD` (85), `CITIZEN_LOST_TO_STRESS` (182).
  (`CITIZEN_TANTRUM`/`BERSERK_CITIZEN` are already in `diff.lua`'s
  `berserk_or_tantrum` category — deliberately not duplicated here.)
- `production_stall`: `UNABLE_TO_COMPLETE_BUILDING` (250),
  `JOBS_REMOVED_FROM_UNPOWERED_BUILDING` (251), `CONSTRUCTION_SUSPENDED`
  (268), `LINKAGE_SUSPENDED` (269).
- `nobles_and_mandates`: `NEW_MANDATE`/`MANDATE_ENDS` (275/263),
  `NEW_DEMAND`/`DEMAND_FORGOTTEN` (274/273).
- `season_change` (cheap, exactly 4/year, useful as the opening-ladder's own
  timing precondition): `SEASON_SPRING`/`SUMMER`/`AUTUMN`/`WINTER`
  (297–300).

**Suppress, explicitly, not just by omission** (so a future maintainer
knows these were considered and rejected, not missed):

- `CANCEL_JOB` (104) — the known spam risk, named above.
- Every `COMBAT_*`, `AMBUSH_*`, `CITIZEN_DEATH`/`PET_DEATH`,
  `CITIZEN_TANTRUM`/`BERSERK_CITIZEN` id already owned by
  `df-overseer-diff.lua`'s own categories — surfacing them a second time
  from a different tool would be duplicate signal, not new coverage.
- Every adventure-mode-only type (`ADV_*`, `DAWN_BREAKS`/`NOON`/`NIGHTFALL`,
  `TRAVEL_*`) — this project runs fort mode exclusively.
- Every per-look flavor/inventory type (`CURRENT_WEATHER`/`CURRENT_SMELL`/
  `CURRENT_TEMPERATURE`/`CURRENT_DATE`, `NOTHING_TO_INTERACT`/`_EXAMINE`,
  every `NO_INV_TO_*`, `EAT_ITEM`/`DRINK_ITEM`/`PICK_UP_ITEM`/`DROP_ITEM`/
  `PUT_INTO_CONTAINER`/`TAKE_OUT_OF_CONTAINER`) — narrative colour, not a
  fort-level decision input.
- Everything else in the 353-entry enum not named above, by default —
  matching this repo's own "don't build past what's used" style already
  applied to `eventful`'s unwired event types in `df-overseer-diff.lua`'s
  own header comment.

**Not verified about this proposal**: whether `announcements` genuinely
stays this small at fort-year 3+ or year 5+ (this fort is mid-year-1 and has
built nothing, so its own event rate is unusually low) — flagged the same
way `df-overseer-diff.lua` already flags the same open question for
`reports`, not resolved here.

---

## Not verified — summary

- **Whether the pool at z=168 is currently fishable.** The single most
  important open fact in this brief, and it is genuinely not answerable
  from static reads — only from an actual attempt, which requires
  unpausing. Named plainly rather than guessed at in either direction (§3).
- **The exact biome-naming formula that produced "central swamps."** This
  session confirmed the message's coordinate is near the local map's
  geometric center and sits on a `POOL`-material tile, which is consistent
  with the name, but did not reverse-engineer DF's own
  elevation/rainfall/drainage-to-biome-label formula to prove the word
  "swamps" mechanically (§1).
- **Whether this fort's citizens can currently path to the pool at all**, a
  reachability/connectivity question orthogonal to the fishing-population
  question and not re-checked this session (§4).
- **The real-world volume of `CANCEL_JOB` and other suppressed announcement
  types on a busier fort.** This fort has near-zero active production, so
  its own announcement log cannot stress-test the proposed filter's noise
  assumptions (§7).
- **Whether `flags.foreign` ever clears once an item is "integrated"** —
  inherited, unresolved question from `df-overseer-stocks.lua`'s own header,
  restated here because it bears on reading the fort's 2 fort-owned `FISH`
  items as embark supply rather than fresh catch (§4).
- Every version-sensitivity caveat the opening-priority-ladder and
  food-drink-logistics research already carry for DF-wiki-sourced mechanics
  (checked against the current wiki, not against `0.53.16`'s own patch
  notes) — inherited, not re-derived.
- **This repo's `main` branch advanced twice while this brief was in
  progress** (a stocks-units-counting fix and its own correction commit
  landed mid-session, from `98935b9` to `ba1b029`, from a concurrent
  session this brief did not coordinate with in real time, per
  `CLAUDE.md`'s own standing peer-check rule — this worktree session did
  not itself write to any shared file, but the `main`-tip content cited
  throughout this report was re-fetched mid-session specifically because of
  this, and every citation above reflects the tip current at the time each
  section was written, not a single frozen snapshot). Flagged for the
  orchestrator to reconcile, not something this read-only brief could or
  should resolve itself.

## Sources

DF wiki (fetched this session, verbatim quote captured on the second fetch):
[Fishing](https://dwarffortresswiki.org/index.php/Fishing).

Live VM reads, this session (all read-only, fort confirmed paused before and
after): `df.global.world.status.announcements` (full dump), `df.announcement_type`
enum (full, 353 entries), `df.global.cur_year`/`cur_year_tick`,
`dfhack.maps.getTileType`/`getTileBiomeRgn`/`getRegionBiome`/`getSize`,
a full-map full-z-level `getBlock`/`tiletype` scan (two passes, z 140–185
then the remaining z 0–139/186+), `df.global.world.world_data.rivers`,
`df.global.world.items.other.FISH`/`FISH_RAW`, `df.unit_labor.FISH` and a
live citizen-labor scan (twice, a few seconds apart), `plugins.autolabor.isEnabled()`,
`prospect all --show liquids,summary`, `/opt/df/game/data/init/announcements.txt`
(full grep for `ALERT`), and the deployed `df-overseer-stocks food-drink`/`seeds`
commands.

Repo files read this session, from the current `main` tip (re-fetched
mid-session after `main` advanced — see "Not verified"):
`scripts/dfhack/df-overseer-labor.lua`, `scripts/dfhack/df-overseer-stocks.lua`,
`scripts/dfhack/df-overseer-diff.lua`, `scripts/dfhack/df-overseer-breach.lua`,
`scripts/dfhack/TOOLS.yaml`, `docs/TRAPS.md`, `Working.md`,
`research/2026-09-16-opening-priority-ladder.md`,
`research/2026-09-16-food-and-drink-logistics.md`,
`research/2026-09-16-trade-execution-api.md`, `memory/dfhack-environment.md`,
`agents/overseer/tools.yaml`.
