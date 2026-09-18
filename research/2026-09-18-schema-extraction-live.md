# Live-state schema audit: what DFHack can actually read off Uniboslan

Date: 2026-09-18. Read-only research against VM 103 (Uniboslan, DF v0.53.16
linux64 ITCH, DFHack 53.16-r1.1), all reads non-mutating `dfhack-run lua -f`
scripts uploaded to `/tmp` over SSH and deleted after each run. **Pause state:
`dfhack.world.ReadPauseState()` returned `true` before the first read and
`true` after the last one; `dfhack.world.ReadCurrentTick()` read `227160` at
the start of this session's probes and `227160` again at the very end** — no
drift, confirming nothing in this pass advanced the fort. No file was written
to the VM outside `/tmp` (all deleted), no designation, no struct write, no
deploy. This is the live half of the audit commissioned alongside
`research/2026-09-18-schema-extraction-static.md` (the static/raws half, not
touched here) for `research/2026-09-18-production-graph.md`.

Companion documents read first, cited rather than re-derived where they
already settled something: `memory/dfhack-environment.md`,
`scripts/dfhack/df-overseer-stocks.lua`, `scripts/dfhack/TOOLS.yaml`,
`scripts/dfhack/df-overseer-stuckjobs.lua`, `scripts/dfhack/df-overseer-farm.lua`.

## Bottom line

**Nine of the twelve items are exactly readable by a plain struct field or a
documented DFHack call, several more cheaply and more directly than the
production-graph design assumed.** The two best surprises: **item-level job
claims are a plain per-item flag** (`item.flags.in_job`, live-matched to a
real job's `job.items[i].item`), so the design's worry about "scanning every
job's reagents" is unfounded — the flag is already there, no scan needed. And
**a growing plant carries its own tick counter** (`grow_counter` on the live
plant instance, `df.global.world.plants.all`), a materially better anchor for
the harvest clock than the job-completion fallback the design proposed,
though its exact zero-point and post-maturity behavior were not confirmed
live (nothing is currently planted on Uniboslan to watch).

**What is NOT exactly readable, or is heuristic rather than exact, stated
plainly up front:**

- **Cancellation announcements carry no structured job/unit ID.** The one
  real `CANCEL_JOB` entry this fort has produced has `speaker_id = -1`,
  `activity_id = -1`, `activity_event_id = -1` — every candidate linkage
  field is unset. The only content is free text
  ("`Ral Identeshkad, Metalcrafter cancels Give water: Need empty bucket.`").
  A caller gets to know *that* a cancellation happened and can parse *why*
  and *who* from the string, but cannot join it back to a `job.id` or
  `unit.id` programmatically. This measurably weakens the "DF's own message
  short-circuits the diagnostic ladder" idea: it still requires text
  parsing, not a struct join.
- **The announcement buffer is bounded/pruned, not a full log.** Only 12 of
  what must be well over 100 real announcement ids (2 through 104 observed,
  with large gaps) remain in `world.status.announcements`. A poller that
  runs infrequently can miss a cancellation before it ever reads it.
- **Item-in-depot marking is unverified.** Uniboslan has never had a trade
  depot built (`TradeDepot` absent from `df.global.world.buildings.all` this
  session), so the "item sitting in a depot" sub-case of question 1 could
  not be exercised live. `flags.trader` (already verified exact by
  `df-overseer-stocks.lua`) covers caravan ownership regardless of location,
  but a fort-owned item *moved to* the depot for sale is a separate,
  unverified case.
- **`unit_inventory_item.mode`'s enum labels do not resolve via reflection
  on this install.** The field is a plain int (values `1` and `2` observed
  fort-wide, `0` never observed), but neither `df.unit_inventory_item_mode`
  nor `df.unit_inventory_item.T_mode` exists as a queryable name table this
  session found. Which numeric mode means "worn" vs "wielded" vs "hauled" is
  inferred from population pattern, not confirmed by name.
- **`grow_counter`'s exact semantics (direction of counting, behavior at/after
  `GROWDUR`) are inferred from the field's name and plausible magnitudes, not
  proven by a controlled before/after observation** — the fort must stay
  paused and nothing is currently planted in Uniboslan's own farm plot.
- **`item.age`'s behavior across a calendar-year boundary is untested.**
  Internally consistent within this fort's first (and so far only) year —
  see item 9 — but this fort has never crossed a year boundary, so whether
  `age` is a true absolute tick-since-creation counter or something
  year-relative cannot be distinguished from this session's data alone.
- **The workshop "10-task cap"'s real name and value are uncertain.** Found
  `building.profile.max_general_orders = 5` on Uniboslan's one (still
  under-construction, never-completed) workshop — a real, exact field, but
  whether this is the same concept community folklore calls "10 tasks," and
  whether it holds the same value on a finished/different workshop kind,
  is unconfirmed with only one, incomplete, sample.

## 1. Available stock versus total stock

**Exact, and cheaper than assumed: `item.flags.in_job` is a real per-item
flag, no reagent-scan needed.**

Live-verified this session: job 372 (`PlantSeeds`, `fetching`, has a worker)
carries `job.items[0].item.id == 67`, and item 67 (a `SEEDS` item) itself
reads `flags.in_job == true`. Job 375 matches the same way against item 113.
`job.items` is a real vector field on `df.job` (confirmed by direct read,
each entry exposing `item`, `role`, `flags`, `job_item_idx`). So the
direction the design brief worried about (job → item only, forcing a scan)
is wrong: the item carries its own claim flag, checkable in isolation with no
job traversal at all.

Fort-wide flag scan (`df.global.world.items.other.IN_PLAY`, 1325 items):
`in_job = 2`, `owned = 120`, `forbid = 218`, `in_building = 3`. All four are
real, distinct bitfield members on `item.flags` (**note the exact spelling is
`forbid`, not `forbidden`** — `forbidden` errors as a nonexistent field; found
live this session, not documented anywhere in this repo before now).

- **`forbid`**: exact, a plain bool. Not cross-checked against a specific
  known-forbidden item this session (218 exist fort-wide, none individually
  inspected for *why*), but the field itself is confirmed real and readable.
- **`owned` (per-dwarf ownership)**: exact, and **now confirmed**, not just
  believed. `df-overseer-stocks.lua`'s header flagged this as "believed to
  track personal ownership... not exhaustively confirmed." This session
  sampled 5 `owned=true` items fort-wide; every one resolves (via its
  `UNIT_HOLDER` general_ref) to unit 192, and `dfhack.units.isMerchant(unit)`
  reads `false` for that unit — a real citizen, not a trader. That closes the
  open question in `df-overseer-stocks.lua`'s own comment.
- **Caravan ownership (`trader`)**: already verified exact by
  `df-overseer-stocks.lua` (cited per the brief, not re-derived).
- **Depot**: unverified, no depot exists on this fort (see Bottom line).

## 2. Job claim state

**Exact.** `dfhack.job.getWorker(job)` returning non-nil is the has-worker
test (already used by `df-overseer-stuckjobs.lua`, re-confirmed live this
session across the real 27-job queue). `job.flags.suspend` is a real bool
field, live-observed true on job 366 (`ConstructBuilding`, the still, no
worker, `BUILDING_HOLDER` ref only). The **full set of real `job.flags`
field names**, read directly off a live job this session:
`bringing, by_manager, could_not_find_building_use_1, dessource, do_now,
fetching, item_lost, noise, non_fluid, on_break, quality, repeat, special,
store_item, suspend, working` (plus several numeric-only reserved slots).
**`working` is confirmed to exist as a real field**, matching
`df-overseer-stuckjobs.lua`'s citation of it from `internal/notify/
notifications.lua`; not observed `true` on anything in this session's queue
(nothing is actively executing while paused).

`job.completion_timer`: confirmed live on two more real jobs beyond the
`Sleep` job the production-graph research already cited. `-1` on every
not-yet-started job in the 27-job queue (all the un-worked `PlantSeeds`
jobs); the one job mid-flight in this session's own read of a `Sleep` job
elsewhere was `1`.

Job → unit and back: `dfhack.job.getWorker(job)` (job → unit) and
`dfhack.job.getHolder(job)` (job → building) are both real, live-confirmed.
The reverse (unit → job) is `unit.job.current_job` per DFHack convention
(not independently re-verified this session, since every worker found this
session was reached job-first, but this is standard, stock-script-confirmed
DFHack usage, not new).

**Cancelled job persistence: nothing persists.** The one real cancellation
this fort has ever logged ("Ral Identeshkad, Metalcrafter cancels Give
water: Need empty bucket," `job_type` `GiveWater`/176 per
`memory/dfhack-environment.md`) has **no matching job anywhere in the current
27-entry `world.jobs.list`**. DF removes a cancelled job from the live queue
entirely; the announcement text is the only surviving trace (and even that
carries no job id — see item 3). This answers the brief's question directly:
a cancelled job looks like *nothing* structurally, only narration.

## 3. Cancellation announcements

**Confirmed real, confirmed present on this exact install, confirmed weaker
than hoped.** `world.status.announcements` held 12 entries this session
(ids 2–104, with large gaps — see Bottom line on pruning), one genuinely new
since the production-graph research's own 11-entry count:

```
id=104, year=30, time=214135, type="CANCEL_JOB"
text="Ral Identeshkad, Metalcrafter cancels Give water: Need empty bucket."
```

Full field list on that entry (read directly): `activity_event_id,
activity_id, bright, color, duration, flags, id, pool_id, pos, pos2,
repeat_count, speaker_id, text, time, type, year, zoom_type, zoom_type2`.
On this entry: `speaker_id = -1`, `activity_id = -1`, `activity_event_id =
-1`, `repeat_count = 0`, `duration = 100`. **Every field that could link
this announcement back to a specific job or unit struct is unset.** `pos`/
`pos2` exist (not reported here, per the coordinate ban) but a coordinate is
not the same as a job/unit id and would need a reverse lookup against
whatever was standing there at the time, which is not reliable after the
fact. **So: real, cheap, confirmed to fire for a genuine engine cancellation
on this exact install — but text-only. A caller must pattern-match the
string for the dwarf's name and DF's own stated reason; there is no
`job_id`/`unit_id` field to join on.**

## 4. Workshop queue depth

**Exact, and directly on the building, not via a global job-list scan.**
`building.jobs` is a real vector field, confirmed live on Uniboslan's one
workshop (`Still`, `id=5`, `workshop_type=15` decoded via
`df.workshop_type[15] == "Still"`, `flags.exists = false` since it is still
under construction). `#ws.jobs == 1` (the `ConstructBuilding` job itself,
the only job referencing this workshop while it's unbuilt). The same count
is independently obtainable by scanning `world.jobs.list` for a
`BUILDING_HOLDER` general_ref matching the building's id (also confirmed
live — every `PlantSeeds`/`ConstructBuilding` job this session read carried
exactly this ref type toward its building), but `building.jobs` is the
direct, cheaper path.

**The "10-task cap"**: found `building.profile.max_general_orders = 5` on
this workshop — a real, exact int field, structured for exactly this
purpose (`workshop.profile` also carries `blocked_labors, links, max_level,
min_level, permitted_workers`). **Value is 5, not the commonly cited 10.**
Only one workshop exists on this fort, and it has never finished
construction, so this could not be cross-checked against a different or
completed workshop kind — flagged as a real, exact reading with an uncertain
scope of applicability, not a confirmed universal constant.

## 5. Stockpile links

**Exact, on both sides.** `building_stockpilest.links` is a real struct with
exactly the four fields the brief named:
`give_to_pile, give_to_workshop, take_from_pile, take_from_workshop`
(confirmed live by direct field enumeration on Uniboslan's real stockpile).
The mirror exists on the workshop's own side too:
`building.profile.links` carries the same four field names. Both read as
empty (count 0) on Uniboslan today — the fort's two stockpiles and one
(unbuilt) workshop have no configured links yet, an honest, real "not
configured," not a read failure. Each field is presumably a vector of
building pointers (consistent with the field naming and with DF's own
stockpile-workshop link UI); not independently exercised against a nonzero
real link this session since none exists on this fort to read.

## 6. Installed versus item

**Exact by construction, not cross-validated with a nonzero example on this
fort.** Loose furniture items and installed furniture buildings are
independently countable: `df.global.world.items.other.BED` /
`.DOOR` / `.TABLE` / `.CHAIR` / `.COFFIN` for items, versus iterating
`df.global.world.buildings.all` filtered by `df.building_type.Bed` (value 1),
`.Door` (8), `.Table` (2), `.Chair` (0), `.Coffin` (3) — **all five confirmed
as real top-level `building_type` enum members this session**, not assumed
from naming convention. On Uniboslan today both sides read **0** for all
five kinds (no furniture item exists, none is installed), which proves the
mechanism is real and well-typed but does not demonstrate the two counts
actually diverging on this specific fort, since neither case has happened
yet. Confidence: high on the mechanism (two genuinely disjoint DF concepts,
consistent with the item-becomes-consumed-into-building pattern this
project already relies on for barrels), unverified-live on the
divergent-count scenario the design actually wants to distinguish.

## 7. Time

**Exact, with one correction to how "current tick" behaves.**
`dfhack.world.ReadCurrentTick()` read `227160` this session — and **is
numerically identical to `df.global.cur_year_tick`, also `227160`**. This
means `ReadCurrentTick()` is **year-relative, resetting at each spring**, not
a monotonic absolute tick count since embark. `df.global.cur_year` reads
`30`. `df.global.cur_season` reads `2` (confirmed `df.season` convention,
Spring=0..Winter=3, per `df-overseer-farm.lua`'s already-verified mapping:
`2` = Autumn). `df.global.cur_season_tick` reads `2556`.

**The 1200/33600/403200 figures are confirmed, not just cited**, via two
independent exact matches in this fort's own real announcement log: a
`SEASON_SUMMER` announcement fired at `time = 100800` (exactly one season,
`403200 / 4`) and `SEASON_AUTUMN` fired at `time = 201600` (exactly two
seasons). Both match the year-relative tick field exactly, not
approximately. The per-month figure (33600) was not independently
re-confirmed by a real `SEASON_*`-equivalent monthly announcement (DF does
not appear to announce month boundaries the same way), so it stands only as
arithmetic (`403200 / 12`), consistent with but not separately observed
this session.

**Found and not previously flagged in this project's docs**:
`cur_season_tick` (`2556`) does not equal `cur_year_tick` minus the season's
start tick (`227160 − 201600 = 25560`) — it is exactly **that value divided
by 10** (`25560 / 10 = 2556`). Consistent with DF's well-known internal
"updates every 10 ticks" cadence for several subsystems, but this is
inferred from one data point's arithmetic, not proven by a controlled test.
**Practical implication for any future tool**: `cur_year_tick` /
`ReadCurrentTick()` is safe as "ticks so far this calendar year" but **is not
usable as a cross-year absolute clock** — it will reset toward 0 at the next
spring. A design that wants a true monotonic clock across a multi-year fort
needs `cur_year * 403200 + cur_year_tick`, not `ReadCurrentTick()` alone.
This matters directly for item 9's `age`-field retrospective-measurement
idea, which implicitly assumed a monotonic current-tick reference.

## 8. Farm plot state for the harvest clock

**Better than the design assumed: a live plant carries its own growth
counter, not just the farm plot building.** `building_farmplotst`'s own
fields (read directly, real farm plot `id`, Uniboslan's actual built plot):
`activities, age, centerx, centery, construction_stage, contained_items,
creation_bld_num, current_fertilization, design, farm_flags, flags,
general_refs, id, job_claim_suppress, jobs, last_season, location_id,
mat_index, mat_type, material_amount, max_fertilization, name, plant_id,
race, relations, room, site_id, specific_refs, terrain_purge_timer,
world_data_id, world_data_subid, x1, x2, y1, y2, z`. **No per-tile planted-on
tick lives on the building itself** — `plant_id` (the per-season crop
assignment, already used by `df-overseer-farm.lua`) and `last_season` are
the only calendar-adjacent fields, and neither is a planting timestamp.

But a **live plant instance** (`df.global.world.plants.all`, the actual
grown/growing objects, distinct from the raws) carries: `contaminants,
damage_flags, grow_counter, hitpoints, material, pos, site_id, srb_id,
tree_info, type, update_order`. **`grow_counter` is real and present on
every sampled plant** (9,100 live plant instances exist map-wide right now —
this includes wild trees/shrubs, not just farm crops, since Uniboslan's own
plot has nothing planted yet per the current status line). Sampled values:
`21036`, `18480`, `18481`, `4764795` (almost certainly a mature tree, whose
`grow_counter` semantics likely differ from an annual crop's), `18482`.

**This is a materially better harvest-clock anchor than the design's
job-completion fallback**: once a `PlantSeeds` job creates a plant instance
at a tile, reading that plant's `grow_counter` at any later time should give
elapsed growth directly, without needing to have observed the planting event
itself. **Not proven this session**: Uniboslan's own plot has nothing
planted (confirmed: the fort's real `PlantSeeds` jobs are still queued,
several `fetching`, none completed), so no crop-specific `grow_counter` was
observed, and whether it counts up from 0 at germination, what it does once
it passes the crop's `GROWDUR`, and whether it is even the same field
semantically for a farmed crop versus a wild plant, are all inferred from
the field's name and structural position, not watched happening.

**Design-relevant caution found in passing, not asked for but worth
flagging**: reading `world.plants.all` directly is naively omniscient (it
returns every plant on the map including any under an undiscovered tile);
any future tool built on `grow_counter` needs the same
`dfhack.maps.isTileVisible` guard this project already applies elsewhere
(`df-overseer-diggable.lua`, `df-overseer-trees.lua`), not demonstrated here
since this was a one-off research read, not a shipped tool.

## 9. Rot flags and item age

**`rotten`**: already cited correctly by `df-overseer-stocks.lua`
(`item.flags.rotten`, a real bitfield member, confirmed present in this
session's own full flag-name dump off a live item). Not independently
re-sampled non-zero this session (nothing rotten among the specific items
this session's own probes happened to touch); the mechanism itself is not
in question, `df-overseer-stocks.lua` already exercised it live and
non-trivially (per its own header).

**`age` reliability, now sampled far more broadly than the one barrel the
production-graph research checked.** Five buckets, multiple items each:

| Bucket | Sample ages | Reading |
|---|---|---|
| `BARREL` (embark stock) | `21036` × 5 | Identical across every embark-origin item sampled |
| `SEEDS` (embark stock) | `21036` × 5 | Same |
| `WEAPON` (embark stock) | `21036` × 5 | Same |
| `ANY_EDIBLE_RAW`, embark-origin items | `21036` × 4 | Same |
| `ANY_EDIBLE_RAW`, one caravan-held (`trader=true`) item | `1368` | Much younger, consistent with recent caravan arrival |
| `ANY_REFUSE` (produced on-site, post-embark) | `18879, 18370, 18064, 15971, 15311` | All distinct, all less than `21036` |

This is internally consistent with `age` being a true elapsed-ticks-since-
creation counter: every embark-origin item across five unrelated buckets
reads the *exact same* value (`21036`), as expected if they were all
created at the same moment (fort founding); on-site refuse (created later,
at varying points as the fort progressed) reads smaller and mutually
different values, each less than the embark baseline; the one caravan item
reads smallest of all, consistent with a caravan that arrived recently
(matching the `LIAISON_ARRIVAL`/`MERCHANTS_NEED_DEPOT` announcements at
`time=213480`, close to the current `227160`). **This is much stronger
circumstantial support than the single-barrel sample the production-graph
research had**, but it is still not a controlled create-and-observe test
(the fort must stay paused), and **whether `age` behaves correctly across a
calendar-year rollover is genuinely untested** — Uniboslan has not yet
completed one full year (see item 7's correction about `cur_year_tick`
resetting yearly; if `age` were somehow tied to the same reset, which is not
expected but was not ruled out, the "creation tick = current_tick − age"
arithmetic would break after a year boundary).

## 10. Labour and availability

**Exact for the calls checked, one new fact found.** Full live scan of all
15 citizens (`dfhack.units.isCitizen`), fort-wide:

- **Children/babies**: `dfhack.units.isChild`/`isBaby`, both real, both
  read `0` on this fort right now (an adult-only founding population).
- **Military**: `unit.military.squad_id ~= -1` is the real, direct test
  (confirmed field, reads `-1`/not-in-squad for all 15 citizens today — no
  squad has been formed).
- **Injured**: not resolvable as one clean flag. `unit.counters` (distinct
  from `counters2`, found live this session by direct field enumeration)
  carries `pain, nausea, dizziness, stunned, unconscious, suffocation,
  webbed`, real int/countdown fields, not the bool this session first
  guessed at (`counters2.unconscious` does not exist — `counters2` actually
  holds `paralysis, numbness, fever, exhaustion, hunger_timer, thirst_timer,
  sleepiness_timer, stomach_content, stomach_food, vomit_timeout,
  stored_fat`). A caller's "injured" test needs to be built from `counters`
  fields being non-zero, or from a wound-count check, not one bitflag.
- **Unconscious**: `unit.counters.unconscious > 0`. **Found real and
  currently non-zero on this fort**: 1 of 15 citizens reads unconscious
  right now — a genuine, live positive case, not a zero-result guess.
- **Nobles**: `dfhack.units.getNoblePositions(unit)` (per-unit call, not the
  no-arg form `df-overseer-orders.lua` used for its own different check).
  **Found 1 of 15 citizens holds a noble position right now** — this is a
  different (and more encouraging) result than `df-overseer-orders.lua`'s
  existing "nobody holds Manager" finding; the two are not in conflict,
  since a fort can have a Mayor/Broker/etc. filled while Manager
  specifically stays empty. Which position was not decoded further this
  session (out of scope for this item).
- **`labor.unit-status`'s own known-wrong filter** (`hostile`, via
  `isDanger`/`isInvader`): unchanged from `TOOLS.yaml`'s own existing
  verdict, "proven UNRELIABLE... missed a real kea attack entirely." Not
  re-tested this session; cited, not re-derived, per the brief's own
  instruction to check what is being reused.

## 11. Traffic designations

**Mechanism confirmed, no coordinates reported below.** `df.tile_traffic` is
a real four-member enum: `0=Normal, 1=Low, 2=High, 3=Restricted` (decoded
live by direct numeric probing of the enum, not assumed from the wiki). The
per-tile value is read via `dfhack.maps.getTileFlags(pos).traffic`, the same
call every other tool in `scripts/dfhack/` already uses for tile flags
generally. One live read (an internal, non-reported tile) returned
`"Normal"`, confirming the field resolves to a real value, not `nil`, on
this fort's own map data.

## 12. Unit inventory

**Exact field, enum labels unresolved, real fort-wide answer obtained.**
`unit.inventory` is a real vector on `df.unit`; each entry
(`df.unit_inventory_item`) carries `item, mode, body_part_id, pet_seed,
wound_id` (confirmed live by direct field enumeration). `mode` is a plain
int — **neither `df.unit_inventory_item_mode` nor
`df.unit_inventory_item.T_mode` exists as a name table on this install**, so
the numeric value cannot be resolved to a label ("Hauled"/"Worn"/etc.)
through reflection this session found. Fort-wide scan of every citizen's
full inventory: **mode value `2` appears 120 times, mode value `1` appears 3
times, mode value `0` (the conventional "Hauled" slot by DF community
numbering) appears zero times.** **This directly answers the brief's
question: no, a real loaded hauler was not observable this session** — the
complete absence of mode-`0` entries across all 15 citizens' full inventories
is consistent with "nothing is currently mid-haul," which is exactly
expected of a paused fort, not a read failure (the field itself works fine,
it is simply reporting an empty case for this specific mode).

## Summary table

| Fact | Readable | Call / struct path | Real value observed | Cost | What breaks if unavailable |
|---|---|---|---|---|---|
| Job-claimed item | **Yes, exact** | `item.flags.in_job`; cross-checked via `job.items[i].item` | `in_job=true` on item 67, matched to job 372's `job.items[0]` | One field read per item | Design's "scan every job" fallback is unnecessary — cheaper than assumed |
| Dwarf-owned item | **Yes, exact** | `item.flags.owned` + `UNIT_HOLDER` ref resolved via `dfhack.units.isMerchant` | 120 owned items fort-wide; 5 sampled all resolve to citizen 192, non-merchant | One field + ref walk per item | Closes an open question in `df-overseer-stocks.lua`'s own header |
| Forbidden item | **Yes, exact** | `item.flags.forbid` (not `forbidden`) | 218 of 1325 items fort-wide | One field read | Naive code guessing the field name (`forbidden`) errors outright |
| Item in depot | **Not verified** | Unknown — no `TradeDepot` exists on this fort | n/a | n/a | Can't confirm the sub-case of question 1 that matters for trade-pending goods |
| Job has worker | **Yes, exact** | `dfhack.job.getWorker(job) ~= nil` | 4 of 27 live jobs have a worker | One call per job | Already the `df-overseer-stuckjobs.lua` mechanism |
| Suspended job | **Yes, exact** | `job.flags.suspend` | `true` on job 366 (`ConstructBuilding`, the still) | One field read | — |
| Cancelled job trace | **No, by design** | n/a — removed from `world.jobs.list` entirely | Confirmed: the `GiveWater` job behind the one real `CANCEL_JOB` announcement is absent from the live queue | n/a | "What a cancelled job looks like" is answered as "nothing persists" |
| Cancellation announcement | **Yes, but text-only** | `world.status.announcements`, `type="CANCEL_JOB"` | 1 real entry, `speaker_id=-1`/`activity_id=-1` (unlinked) | Cheap, already-read channel | Short-circuiting the diagnostic ladder needs text parsing, not a struct join |
| Workshop job queue depth | **Yes, exact** | `building.jobs` (vector) | `#jobs == 1` on Uniboslan's one (unbuilt) workshop | One field read | — |
| Workshop task cap | **Yes, exact, scope uncertain** | `building.profile.max_general_orders` | `5` (not the folklore `10`) | One field read | Only one, incomplete, workshop sampled this fort |
| Stockpile give/take links | **Yes, exact** | `building_stockpilest.links.{give,take}_{to,from}_{pile,workshop}` | All 0 (fort's 2 stockpiles unlinked) | One field walk | Ladder rungs 2/3 fully answerable |
| Workshop's own pile restriction | **Yes, exact** | `building.profile.links` (same 4 fields) | Not configured (0) | Same | — |
| Installed vs item furniture | **Yes, exact mechanism, not cross-validated non-zero** | `items.other.BED/DOOR/TABLE/CHAIR/COFFIN` vs `buildings.all` filtered by `building_type.Bed/Door/Table/Chair/Coffin` | Both sides 0/0 for all 5 kinds | Two vector scans | Design's par-level-vs-flow-item split needs a nonzero fort to see it distinguish anything |
| Current tick | **Yes, exact, year-relative** | `dfhack.world.ReadCurrentTick()` == `df.global.cur_year_tick` | `227160` | One call | Not usable as a cross-year absolute clock without adding `cur_year * 403200` |
| Season | **Yes, exact** | `df.global.cur_season` | `2` (Autumn) | One field read | — |
| 1200/33600/403200 figures | **Yes, confirmed live** | Two `SEASON_*` announcement `time` fields | `100800` and `201600` exactly | Free (already-read channel) | Month figure (33600) stays arithmetic-only, not separately observed |
| Plant growth timer | **Yes, field exists; semantics inferred** | `df.global.world.plants.all[i].grow_counter` | Sampled `18480`–`4764795` (wild plants; no crop currently planted) | One vector scan | Better anchor than job-completion fallback, but direction/maturity behavior unconfirmed |
| Rotten flag | **Yes, exact, cited not re-derived** | `item.flags.rotten` | Confirmed present as a field; non-zero elsewhere per `df-overseer-stocks.lua` | One field read | — |
| Item age reliability | **Heuristic, strongly supported** | `item.age` | Embark items all `21036`; refuse `15311`–`18879`; one caravan item `1368` | One field per item | Retrospective "produced in period" measurement depends on this holding across a year boundary, untested |
| Injured/unconscious | **Yes, exact, not a single flag** | `unit.counters.{pain,unconscious,stunned,...}` | 1 of 15 citizens currently unconscious | One field-group read per unit | `counters2` (a different struct) does NOT carry these — a real trap for anyone guessing the field |
| Children/babies/military | **Yes, exact** | `dfhack.units.isChild/isBaby`, `unit.military.squad_id` | All 0 on this fort | One call/field per unit | — |
| Noble position | **Yes, exact** | `dfhack.units.getNoblePositions(unit)` | 1 of 15 citizens holds one | One call per unit | Differs from, doesn't contradict, the existing "no Manager" finding |
| Traffic designation | **Yes, exact, mechanism only reported** | `dfhack.maps.getTileFlags(pos).traffic`, decoded via `df.tile_traffic` | Enum confirmed `Normal/Low/High/Restricted`; one internal sample read `Normal` | One field read per tile | — |
| Unit inventory / hauling | **Yes, field exact; enum labels unresolved** | `unit.inventory[i].mode` | `120` at mode `2`, `3` at mode `1`, `0` at mode `0` fort-wide | One vector scan per unit | No real hauler observed; consistent with a paused fort, not a gap in the read |

## What could not be verified

- **Item-in-depot marking** — no `TradeDepot` exists on Uniboslan this
  session; the mechanism for "fort-owned item currently sitting in the
  depot awaiting trade" is unknown, not just unread.
- **`grow_counter`'s exact semantics** — direction of counting, and what
  happens once a crop passes its `GROWDUR` — inferred from field name and
  plausible magnitudes only; nothing is currently planted on Uniboslan to
  watch, and the fort cannot be unpaused to find out.
- **`item.age` across a calendar-year boundary** — internally consistent
  within this fort's first (and only, so far) year; behavior after a year
  rollover is untested, and matters directly to the production-graph
  design's retrospective-measurement plan.
- **`unit_inventory_item.mode`'s enum labels** — values `0/1/2` exist;
  which is "Hauled" vs "Worn" vs "Wielded" is not resolvable by name on this
  install via any reflection path this session tried.
- **The workshop `max_general_orders` cap's generality** — read as `5` on
  the only workshop this fort has, which has never finished construction;
  not cross-checked against a complete or differently-typed workshop.
- **`unit.job.current_job` (unit → job reverse lookup)** — not independently
  re-verified this session; standard DFHack convention, cited rather than
  freshly proven, since every job/worker pair this session touched was
  reached job-first via `dfhack.job.getWorker`.
- **Stockpile/workshop links with a real non-zero value** — the struct
  fields are confirmed real and correctly named, but Uniboslan has never
  configured one, so no live nonzero link was read.
- **Depot-specific item flags beyond `trader`** — `for_trade` and
  `locked_in_for_trading` were found live this session, but on a **unit**
  struct (`unit.flags2`), not an item struct — apparently for livestock/
  animals offered for trade, not generic goods. Whether an analogous
  per-item flag exists for ordinary trade goods sitting in a depot was not
  determined.

**Pause state: `true` before the first read, `true` after the last read.
`dfhack.world.ReadCurrentTick()` read `227160` at both the start and the end
of this session's probes — unchanged throughout.**
