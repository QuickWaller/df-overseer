# Why didn't the six founders drink during the supervised 10 FPS test?

Date: 2026-09-17. Read-only research against the live, paused fort (VM 103,
SSH, `/opt/df/game/dfhack-run` as the `df` user, DFHack 53.16-r1.1). Fort
confirmed paused (`dfhack.world.ReadPauseState()` -> `true`) at tick
`year=30 tick=217948` before every probe and re-confirmed unchanged
(same pause state, same tick) after the session's last command. Seven small
Lua probe scripts were copied to `/tmp` on the VM, run once each via
`dfhack-run lua -f`, and deleted immediately after (`rm -fv /tmp/probe*.lua`,
confirmed in output). No probe set a `dfhack_flags` global, no probe scanned
the whole map (each was bounded to 15 named units, the fortress job list, the
announcement/report log, or a 15x14 tile box), and nothing was written to
game state. No unpause was requested or performed.

## Bottom line

**The water that reached five migrants during the test was administered by
a caretaker (the `GiveWater` aid-request job), not fetched by the migrants
themselves — and three of the six founders (192 Zuglar, 193 Kâbuk, 194
Erush) were the caretakers who delivered it.** This is confirmed by primary,
in-game data, not inference: each of those three founders carries a
`GaveWater` entry in their emotional-thought log at a game tick that matches,
to the exact tick, a `ReceivedWater` entry in one specific migrant's thought
log (192 <-> 347 at tick 214730; 193 <-> 353 at tick 215011; 194 <-> 346 at
tick 214307). A fourth founder, 195 Ral, attempted the same job and failed —
the fort's own announcement log records it verbatim: `"Ral Identeshkad,
Metalcrafter cancels Give water: Need empty bucket."` at tick 214135, the
**only** report of any kind logged during the entire ~4326-tick test window.
No founder (192-198) has a `ReceivedWater` thought anywhere in their log.
No unit of either group shows any thought consistent with a plain, self-serve
`Drink`/`DrinkItem` job ever completing during the test.

Being the *worker* on a `GiveWater` job does not satisfy the worker's own
thirst, only the *patient's*. That is sufficient to explain why 192, 193 and
194 personally stayed thirsty despite successfully getting water to someone
else. It does **not** by itself explain 195 (whose own attempt failed), or
196/197/198, who show no `GiveWater`/`ReceivedWater` activity at all and simply
sat idle while their thirst climbed past every migrant's pre-service level.
That remaining piece — why the job-assignment system picked founders as
workers and migrants as patients, when the founders were *thirstier* at the
moment the test began — is this report's top open question, ranked below.

---

## What was checked, and what it showed

### 1. Per-unit state (all 15 units, live struct reads)

A probe script read, for units 192-198 and 344-353 (excluding 348/350, not
in the task's named cohort), directly from `df.global.world.units.active`:
`counters2.hunger_timer`/`thirst_timer`/`sleepiness_timer`, `counters.*`
(unconscious, winded, stunned, pain, nausea, dizziness, suffocation),
`#unit.body.wounds`, `unit.military.squad_id`, `unit.job.current_job`,
position, and `unit.flags1`/`flags2`/`flags3` (only true flags printed).

**Findings, high confidence (direct live reads):**

- **Nobody has a current job right now.** All 15 show `job=none, jobid=-1` —
  expected, since the fort auto-paused into a fully idle state and no probe
  ran while a job was active.
- **Nobody is wounded, unconscious, stunned, in pain, caged, or chained.**
  Every counter is 0 for all 15 units; `#wounds = 0` for all 15;
  `flags1.caged`/`flags1.chained` both false for all 15. This directly rules
  out the wiki-sourced "resting in bed due to injury" lead named in the
  task brief: none of the six founders carries any wound, health flag, or
  incapacitation state that would explain needing water administered rather
  than fetched. (Also directly checked against `job_type.Rest`: nobody is
  running a Rest job right now, and nobody's wound count is nonzero — a unit
  that had been bed-resting from injury would show wounds even after the
  job ended, and none do.)
- **Nobody is in a squad or has a military role.** `squad_id = -1` for all
  15. Rules out a training-schedule/barracks-restriction explanation.
- **Thirst timers, read right now (tick 217948):** founders 193-198 sit at
  34630-35906 (still climbing, matches the decision register's own endpoint
  figures almost exactly); founder 192 sits at 14064 (he was never in the
  >25,000 cohort the task names); migrants 344,345,346,347,353 sit at
  2937-3880 (freshly reset, climbing again since the drink); the anomaly
  trio 349/351/352 sit at 13879-14179 (also low, also climbing since an
  earlier reset). This matches the decision register's own numbers and adds
  nothing new on its own, but anchors the timeline below.
- **Flags are essentially identical between the two groups** — both carry
  `move_state, can_swap, important_historical_figure` (flags1);
  `calculated_nerves, calculated_bodyparts, important_historical_figure,
  calculated_insulation, vision_good, breathing_good` (flags2);
  `size_modifier_computed, stuck_weapon_computed, body_temp_in_range`
  (flags3). The only flag difference found (`vision_cone_set`, present on
  193-197 but absent on 192, 198, and every migrant) tracks with a
  rendering/vision computation, not anything drink-related — checked, not
  chased further.
- **No burrows exist on this fort at all** (`plotinfo.burrows.list` is
  empty). Rules out a burrow-membership restriction outright.

### 2. Personality needs and thoughts (the wiki's "alcohol dependence" lead)

Every one of the 15 units — founders and migrants alike, including the five
who successfully drank plain water — carries an **Intense (level 10)**
`DrinkAlcohol` personality need with a strongly negative, unmet `focus_level`
(-560 to -7710). **This need is present and unfulfilled in both groups
equally**, and the migrants drank water anyway. This directly rules out
the hypothesis that dwarves refuse water while their alcohol-craving need is
unmet — the need and the physical thirst mechanic are independent, matching
what `hack/scripts/modtools/set-need.lua` and `hack/scripts/immortal-cravings.lua`
(read in full, live VM) show: `DrinkAlcohol` is a psychological/mood need
driven by the `IMMODERATION` personality trait, satisfied only by an
alcoholic drink, and is a completely separate system from `counters2.thirst_timer`.
`immortal-cravings.lua`'s own `needs_alcohol()` check only fires a synthetic
drink-seeking job for creatures with the `NO_DRINK`/`NO_EAT` caste flags
(vampires etc.) — already confirmed in the 2026-09-17 decision register that
no dwarf caste on this build carries `NO_DRINK`. **Confidence: high** (read
directly from this install's own shipped Lua, cross-checked against live
per-unit need dumps).

The per-unit **thought/emotion log**
(`unit.status.current_soul.personality.emotions`, a `personality_moodst`
vector — this DF version's mechanism for both "thoughts" and "emotions",
there is no separate `.thoughts` field) is where the real signal is. Each
entry carries a `thought` id (`df.unit_thought_type`), a `subthought`, a
`year`/`year_tick`, and a `strength`. **Important caveat discovered while
reading it: this list appears to hold at most one entry per distinct
(thought, subthought) pair — the *most recent* occurrence, not a full
history** (inferred from list lengths: founders, who have been in the fort
since founding, show ~25-30 entries; migrants, present a fraction as long,
show ~15-25; no unit's list is anywhere near what a full multi-day log would
contain). This means an earlier `GaveWater` by the same unit could have been
overwritten by a later one — the three founder-to-migrant pairings below are
therefore a **firm lower bound** on how many successful deliveries founders
made, not necessarily the complete count.

**The key correlated pairs found, high confidence (exact-tick matches
between independent units' logs, not an inference):**

| Worker (founder) | `GaveWater` tick | Patient (migrant) | `ReceivedWater` tick |
|---|---|---|---|
| 192 Zuglar | 214730 | 347 Rith | 214730 |
| 193 Kâbuk | 215011 | 353 Besmar | 215011 |
| 194 Erush | 214307 | 346 Stukos | 214307 |
| 195 Ral | — (job cancelled 214135, "Need empty bucket") | — | — |

344 (Zutthan, `ReceivedWater` at 214068) and 345 (Tun, `ReceivedWater` at
214168) also received water inside the same ~950-tick window, but no unit
among the 15 checked shows a matching `GaveWater` entry at those exact
ticks — consistent with the overwrite caveat above (192, 193 or 194 could
have delivered to them too, earlier, and had that entry replaced by their
later, still-visible delivery), or with an untraced worker outside the
15-unit cohort this probe checked. **Not resolved**, flagged rather than
guessed at.

**No founder (192-198) has a `ReceivedWater` entry anywhere in their log**,
at any tick, past or present. Founder 192 does show a much older `NastyWater`
thought at tick 204173 — DF's own thought for drinking stagnant/dirty
water — which lines up with the "four-citizen thirst anomaly" the
2026-09-16 food-clock research flagged and could not explain: 192, 349, 351
and 352 all carry a `NastyWater` thought clustered at ticks 204069-204197,
roughly 9,500 ticks (about 8 days) before this test began, which is exactly
that earlier research's own estimate of "something reset their thirst about
8 days ago." **This settles that open question, moderate-high confidence**:
those four drank once, together, from a stagnant/dirty source, at that time
— which is also, independently, evidence that *some* water access existed on
this fort well before the supervised test, undercutting a pure
"permanently unreachable" reading of the pool.

`DrinkWithoutCup` (drinking without a proper vessel — a separate DF quirk,
unrelated to this question) appears widely across both groups at various
pre-test ticks, confirming vessel-less drinking has happened fort-wide at
some point; not chased further, since it doesn't bear on the founders/
migrants split.

### 3. The `GiveWater` job, its patient, and the buckets

`df.job_type` (enum dumped live, full names, high confidence): the
drink/water-related job types in this build are `Drink` (19), `DrinkItem`
(20), `FillWaterskin` (21), `FillWaterskinItem` (22), `GiveWater` (176),
`GiveWaterPet` (178), `DrinkBlood` (221). No plain self-serve `Drink` or
`DrinkItem` job was found in the world job list at read time (the job list
is empty right now, fort fully idle) — consistent with, but not conclusive
proof beyond, the decision register's own live sampling during the test
itself.

`GiveWater`'s general-purpose refs use `general_ref_unit_workerst` and
`general_ref_unit_patientst` (confirmed by reading `hack/scripts/gui/advfort.lua`
lines 377-408 live, which construct exactly these two ref types with a
`unit_id` field for hand-built jobs of this shape) — `dfhack.job.getWorker(job)`
resolves the former. No `GiveWater` job exists right now to read a live
patient ref from (the only such job in the whole test cancelled and no
longer exists as a job object); the announcement text is the only surviving
record of who was involved, and it names only the worker (Ral), which is
DF's own convention for a `CANCEL_JOB` message.

**The fort's three buckets** (item ids 81, 149, 150; two further bucket
items, ids 1680/1788, are `flags.trader = true` — caravan property, off-map
at the `-30000` sentinel, irrelevant here): **all three sit completely
empty, unforbidden, not `in_job`, held by no building, owned by no unit,
right now.** This proves nothing was left mid-delivery or fouled *as of
now*, but it cannot settle whether they were transiently fouled or simply
all momentarily claimed **during** the test — see hypothesis ranking below.

**A directly relevant DFHack-shipped fix exists for a related bug**:
`hack/scripts/fix/dry-buckets.lua` (read in full, live) exists specifically
because a bucket can retain a leftover `LIQUID_MISC` water item after use
and become unusable as an "empty" bucket for the next `GiveWater`/well job
until manually cleared. This is documented, shipped evidence that
"need empty bucket" failures are a known category of engine friction around
this exact job type — but it is evidence the *category* of failure exists
in this DFHack build, not evidence that *this specific* failure was caused
by that specific bug rather than ordinary resource contention (see below).

**Timeline reconstruction, from the two independent primary sources above
(the report log and the thought-tick matches), high confidence on the
ordering, moderate on the causal interpretation:**

```
213622  test unpaused (10 FPS), all 15 citizens already have thirst >25,000
        except 192, 349, 351, 352 (recently reset ~8 days earlier)
214068  344 Zutthan receives water (worker unidentified)
214135  195 Ral's Give Water job CANCELS: "Need empty bucket" (only report
        of any kind logged in the whole ~4326-tick test)
214168  345 Tun receives water (worker unidentified)
214307  346 Stukos receives water <- delivered by 194 Erush
214730  347 Rith receives water  <- delivered by 192 Zuglar
215011  353 Besmar receives water <- delivered by 193 Kâbuk
215011..217948  (~2937 ticks, ~2.4 game days) — total silence. No further
        report, no further GaveWater/ReceivedWater thought at any tick in
        this range for any of the 15 units checked. Auto-pause fires at
        217948 with 196/197/198 never having been either worker or patient,
        and 195 never retrying successfully.
```

All five successful deliveries and the one failure cluster inside a single
~950-tick window (about 0.8 game days) right at the start of the unpause;
nothing water-related happens in the remaining ~75% of the test's wall
clock. **This dense-then-silent shape is itself evidence**, not just
scene-setting: whatever mechanism produces `GiveWater` jobs evaluated and
acted on a backlog of already-thirsty citizens almost immediately after
unpausing, then stopped generating or servicing any further request for the
rest of the observed window, even though six founders' thirst kept rising
past every serviced migrant's pre-service level in that same time. A pure
"ran out of buckets forever" story does not fit well on its own, because
three of the five successes land *after* Ral's failure at 214135, using
presumably the same three buckets — so buckets were being freed and reused
successfully within the window, not permanently fouled by that one failure.

### 4. Reachability (bounded check, not a full-map scan)

A 15x15-tile box around the citizen cluster (`x=90..104, y=90..104`) at both
`z=168` and `z=169` was checked for `designation.flow_size > 0` (any current
surface water/puddle). **Zero tiles in either layer currently carry any
flow** — there is no puddle or open water anywhere near the fort's own
position right now. This eliminates one candidate explanation for the five
successful deliveries: a temporary rain puddle sitting conveniently close to
the fort during the test. Checking the timeline against the announcement
log: the most recent `Rain`-tagged thought across all 15 units clusters at
ticks 203738-204149, roughly 9,500-10,000 ticks (about 8 days) **before**
the test's 213622 start, and no `WEATHER_BECOMES_RAIN`/`WEATHER_BECOMES_CLEAR`
announcement fired inside the test window itself (checked directly against
the full announcement log). **So it was not raining during the test**, and
the "rain puddle" explanation for how the buckets got filled is not
supported by the evidence found — weakening, not strengthening, that
hypothesis relative to how promising it looked before this check.

That leaves the real, permanent pool (or the ~12,800 tiles of other water
this repo's 2026-09-16 research already found on this map) as the only
candidate source the three successful founder-caretakers could have drawn
from. **A citizen did, provably, get water into a bucket and deliver it —
this is itself new evidence that the pool (or some accessible water) is
reachable in practice**, at least for whatever code path fills a bucket for
`GiveWater`, which is the actual unpaused test the 2026-09-16 food-clock
research said would be needed to settle its own open reachability question.
That question is not fully closed (a `GiveWater` fetch may use different
reachability logic than plain unit movement — e.g. it may not require the
fetching unit to walk *to* the water tile the same way `getWalkableGroup`
models it), but "the pool is completely unreachable by any mechanism" is now
harder to sustain than it was on 2026-09-16.

### 5. Two structural differences between founders and migrants worth naming, neither chased to a conclusion

- **`df.misc_trait_type.Migrant` is a real trait DFHack's own scripts check**
  (`hack/scripts/husbandry.lua:30`, `hack/scripts/workorder.lua:574`, both
  read live, both use it to *exclude* migrants from certain automatic-labor
  assignments). This confirms migrants are a distinguishable category
  in-engine, not just a description this repo made up — but this report did
  not find that trait actually set on any of the five migrants' own
  `misc_traits` list (it wasn't present in the dump), so its practical
  relevance to *this* question is unconfirmed, only its existence as a
  concept the engine tracks.
- **`GetDrinkCooldown` appears on all six founders (192-198) and on no
  migrant. `RequestWaterCooldown` appears on all five migrants who drank
  (value 0 in every case) and on no founder.** Both are `misc_trait_type`
  entries (full enum dumped live: 84 entries) with no doc string and no
  reference anywhere in this install's shipped Lua beyond the enum
  definition itself — their exact semantics are **not confirmed from any
  primary source this session could reach** (no df-structures source, no
  DFHack changelog entry, nothing in `hack/docs/`). The naming and the
  clean split by group is suggestive — `RequestWaterCooldown` reset to
  exactly 0 lines up tick-for-tick with each migrant's `ReceivedWater`
  thought, which is a real, observed correlation, not just plausible
  naming — but the interpretation offered below (patient-side vs.
  self-serve-side cooldown) is inference from naming plus correlation,
  **not a confirmed mechanism**, and is flagged as such in the ranking.

---

## Ranked hypotheses

### 1. Founders were repeatedly recruited as the aid-job's *worker*, not its *patient* — confirmed for three of six, unresolved for the rest (leading hypothesis)

**For:** Exact-tick-matched `GaveWater`/`ReceivedWater` pairs for 192->347,
193->353, 194->346 (primary source, in-game thought log, cross-checked
against two independently-read units' data each time — not a single
source's claim). The one report in the whole test names a fourth founder
(195, Ral) failing at exactly this job. No founder anywhere shows a
`ReceivedWater` thought. `GetDrinkCooldown` (recently, frequently reset)
appears on exactly the six founders and no migrant, consistent with founders
repeatedly running *some* drink-related utility check that never completes
into a logged success.

**Against / unresolved:** Doesn't explain why 196, 197, 198 were never
selected as either worker or patient at all, nor why the whole mechanism
went completely silent for the last ~2,900 ticks (2.4 game days) of the test
while six founders' thirst kept climbing well past every serviced migrant's
pre-service level (29,674-31,580 at test start vs. the migrants' serviced
27,599-29,427) — if anything, the founders should have crossed any shared
thirst-triggered threshold *first*, not last or never.

**What would confirm it further:** re-run with `dfhack.job.list`/
`dfhack.job.getWorker` and `getGeneralRef(job, df.general_ref_type.UNIT_PATIENT)`
polled every few ticks (not just at pause) during a short unpause, to catch
every `GiveWater` job's worker and patient while it exists, rather than
reconstructing after the fact from a thought log that only keeps the latest
entry per type. This needs the clock to run — proposed as a minimal test
below, not run in this session.

### 2. A citizen-processing/job-assignment scan order that finds low-numbered unit IDs first, and a busy worker's own need-check is deferred (moderate confidence, inferred from ID pattern only)

**For:** The three confirmed successful workers (192, 193, 194) are exactly
the three *lowest*-numbered unit IDs among the six founders; Ral (195), the
fourth-lowest, is the one recorded failure; the two *highest*-numbered
founders (197, 198) — and 196, tied with 195 for the third position from
the top — never appear as either worker or patient at all. If the engine's
own per-tick "find an idle, capable unit for this job" scan walks the unit
list in ascending ID order and grabs the first match, low-ID founders would
systematically be swept into caretaking before their own need is ever
separately evaluated, and once busy, DF's normal job-priority behaviour
(don't interrupt an active job for a lower-priority personal need) would
keep deferring their own thirst.

**Against:** This is a pattern inferred from six data points, not read from
any source that states the scan order — no df-structures source or DFHack
doc was available on this install to check the actual C++ unit-update loop
(the DF binary itself is closed-source; df-structures' schema only gives
field/enum *names*, not the game logic that consumes them). Proximity
between the three confirmed worker/patient pairs is not obviously tighter
than the *unused* founders' proximity to the same patients (checked: 195 and
196, both at tile (96,96), are exactly as close to patient 347 as worker 192
was), which weakens a pure-proximity variant of this idea without ruling out
a pure ID-order-of-scan variant.

**What would confirm it:** the same live job-polling test as hypothesis 1,
specifically checking whether new `GiveWater` jobs, when created, always
pick their worker from the lowest available unit ID among idle citizens.

### 3. Founders' own self-serve drink attempts fail silently every time (reachability), while the aid-request path that serviced migrants draws water through a different, more permissive check (moderate confidence)

**For:** `GetDrinkCooldown` resets frequently and only on founders, consistent
with a self-serve "should I go get a drink" utility check that keeps firing
and keeps failing without ever producing a job (a failed *pathfinding*
attempt inside a utility evaluation would not necessarily generate any
report at all, unlike the `GiveWater` job's own explicit
`CANCEL_JOB`/"Need empty bucket" message, which fires only once a job object
already exists and then can't complete). This would be consistent with the
2026-09-16 food-clock research's own finding that zero of 1,239 surface
pool tiles have a walkable-group-adjacent neighbor from the fort's own
position — if that finding is real rather than a `getWalkableGroup`/ramp
artifact (that report's own flagged uncertainty), ordinary unit movement to
the water genuinely fails, while a `GiveWater` fetch (which this session
confirmed *did* succeed three times) may use a different reachability
model internally (e.g. treating the pool tile itself, not an adjacent floor
tile, as the fetch target).

**Against:** This would predict founders never getting water by *any* route,
but 192 has a `NastyWater` thought from roughly 8 days before the test,
proving he personally reached water (or was given it) at least once before.
It also doesn't explain why the founders were never made *patients* of the
same successful `GiveWater` mechanism that worked for migrants three times
in this very test — if `GiveWater` can reach the water at all (proven, three
times), there's no obvious reason it couldn't have targeted a founder
instead of a migrant.

**What would confirm or rule it out:** the reachability-artifact question
this repo already flagged on 2026-09-16 needs settling on its own terms —
either a deeper read of DFHack's C++ `getWalkableGroup` handling of RAMP/
RAMP_TOP shapes (out of this session's reach without the DF/DFHack C++
source, which is not present on this install either), or a live-polled
unpause test that watches whether any founder's own `Drink`/`DrinkItem` job
is ever *created* (not just whether it succeeds).

### 4. The wiki's "resting dwarves must be given water by a caretaker" mechanic (ruled out for this specific test)

**Against, directly:** every one of the six founders has zero wounds, zero
active health-counter values (unconscious/stunned/pain/nausea/dizziness/
suffocation all 0), is not caged or chained, and is not currently running a
`Rest` job. This lead, named in the task brief and in the 2026-09-17
decision register as "not a conclusion," is now ruled out as the mechanism
for *this* test: there is no incapacitation state on record for any founder
that would force a caretaker-only drinking path. The `GiveWater` job clearly
exists and clearly ran in this test, but its trigger here was not injury/
bed-rest — it ran for citizens who were, by every checked health field,
perfectly mobile.

### 5. Alcohol-need dependency blocking water acceptance (ruled out)

**Against, directly:** every one of the 15 units, migrants included, carries
an unmet Intense `DrinkAlcohol` need, and five of them drank plain water
anyway. The need system and the physical thirst mechanic are independent
(confirmed by reading `modtools/set-need.lua` and `immortal-cravings.lua`
live); this lead is closed.

---

## What would confirm the top hypothesis, and whether it needs the clock to run

**Yes, confirming hypothesis 1 (and adjudicating between 1, 2 and 3) needs
the clock to run.** Everything gathered in this session came from
after-the-fact state and a thought log that only retains the latest entry
per (thought, subthought) pair — it cannot show every job that was created,
assigned, or attempted, only the ones whose outcome happens to still be the
most recent of its type. Settling this needs to watch job *creation* and
*assignment* live, not just outcomes.

**Proposed minimal test, not run in this session:**

1. Unpause under the same 10 FPS cap and the same safety envelope as the
   2026-09-17 test (script-on-the-VM with a re-pause trap, a hard tick
   ceiling, stop conditions on citizen-count drop / thirst above 45,000 /
   non-fortress focus / stalled tick).
2. Every ~50-100 ticks (not every tick — cheap enough not to matter, frequent
   enough to catch a `GiveWater` job before it completes or cancels), read
   `df.global.world.jobs.list` for any `job_type == GiveWater` or
   `job_type == Drink`/`DrinkItem`, and for each, resolve
   `dfhack.job.getWorker(job)` and the `UNIT_PATIENT` general ref's
   `unit_id`. Log every `(tick, job_id, worker_id, patient_id, outcome)`
   tuple seen, not just the ones that happen to still be visible at the end.
3. Stop as soon as either every founder has been a patient at least once, or
   a fixed tick ceiling (matching or shorter than the prior test) is
   reached.
4. This directly answers: does a `GiveWater` job ever target a founder as
   patient at all (settling hypothesis 1 vs. 3), and if one is created, is
   its worker always the lowest-ID idle citizen (settling hypothesis 2).

This report does not run that test — the task's constraints forbid
unpausing, and this write-up is confined to what static, paused-state and
historical-log reads could establish.

---

## What a vanilla player could and could not have known

Per this repo's existing player-visibility policy
(`research/2026-09-16-player-visibility.md`, not re-read line-by-line this
session but cited from the 2026-09-16 food-clock research's own already-settled
summary): the in-game "Thirsty" status icon and a citizen's thought/
"complaints" screen (which does show entries like "gave someone water" or
similar in the actual game UI, in readable English, not as a raw enum) are
player-visible. **Everything else in this report is diagnostic-only** — raw
`thirst_timer`/`GetDrinkCooldown`/`RequestWaterCooldown` values, the
`general_ref_type` enum, `misc_trait_type` names, and the exact-tick
correlation method used to pair `GaveWater` and `ReceivedWater` entries
across two different units' internal logs are all engine internals no
vanilla screen exposes as numbers. A future player-facing tool could
legitimately say "citizen X gave citizen Y water" if DF's own UI already
phrases it that way (unconfirmed this session whether it does, since this
session never opened the actual game UI) but could not legitimately expose
the misc-trait cooldown values or the enum ids themselves.

---

## Sources

Live VM reads, this session, all read-only, fort confirmed paused before and
after (`dfhack.world.ReadPauseState()`): `df.global.world.units.active`
filtered to units 192-198, 344-347, 349, 351-353 for `counters2`/`counters`/
`body.wounds`/`military.squad_id`/`job.current_job`/`pos`/`flags1`/`flags2`/
`flags3`; `df.job_type` (full enum); `unit.status.misc_traits` per unit;
`df.misc_trait_type` (full enum, 84 entries); `unit.status.current_soul.personality.needs`
per unit; `unit.status.current_soul.personality.emotions` per unit (the
thought/mood log; field names `thought`, `subthought`, `strength`, `year`,
`year_tick`, confirmed via `printall` on one live instance);
`df.global.plotinfo.burrows.list` (empty); `df.global.world.items.other.BUCKET`
(5 items: 3 fort-owned and empty, 2 caravan-owned and off-map);
`df.general_ref_type` (full enum); `df.global.world.jobs.list` (empty at
read time); `df.global.world.status.reports` (104 entries, full scan for
water/bucket/drink/thirst keywords and for the test's own tick window);
`df.global.world.status.announcements` (cross-checked against the same
report); a bounded 15x15-tile, two-z-level `designation.flow_size` scan
around the citizen cluster (no full-map scan run).

VM-side script files read directly, this session (all from the live
install, not recalled): `hack/scripts/full-heal.lua`,
`hack/scripts/fix/dry-buckets.lua`, `hack/scripts/prioritize.lua` (the
`GiveWater`/`GiveFood` medical-job grouping), `hack/scripts/modtools/set-need.lua`,
`hack/scripts/immortal-cravings.lua`, `hack/scripts/husbandry.lua`,
`hack/scripts/workorder.lua` (both for the `Migrant` misc-trait check),
`hack/scripts/gui/advfort.lua` (for `general_ref_unit_workerst`/
`general_ref_unit_patientst` construction), `hack/scripts/internal/gm-unit/editor_personality.lua`,
`hack/scripts/internal/gm-unit/editor_wounds.lua`, `hack/docs/docs/dev/Lua API.txt`
(grepped for `getGeneralRef`, `dfhack.job.*`, `dfhack.units.*`). No
df-structures XML was found on this install (only the compiled
`hack/symbols.xml` and stonesense's unrelated art-asset XML files exist on
disk) — struct and enum field *names* used throughout this report come from
DFHack's own live Lua reflection (`printall()` on real struct instances) and
from the shipped Lua scripts above that reference them, not from a
structures schema file, which this session confirmed is not present in this
distribution.

Repo files read this session: `CLAUDE.md`, `docs/TRAPS.md`,
`memory/dfhack-environment.md`, `research/2026-09-16-food-clock-and-farm-lead-time.md`,
`research/2026-09-16-fishing-and-water-food.md` (including its correction
note), `decisions/DECISIONS.md` (the two 2026-09-17 rows on thirst-death and
the supervised drink test), `infra/local.example.env`,
`infra/local.df-vm-install.md` (which describes the VM as "104"; the
`.env`'s actual `DF_VM_IP` and this session's live SSH connection confirm
the fort now runs on the host CLAUDE.md and Working.md call VM 103 —
noted as a naming drift between that older infra doc and current practice,
not chased further here since it doesn't bear on this question).

## Not verified

- **Who delivered water to migrants 344 and 345.** No `GaveWater` entry at
  their exact `ReceivedWater` ticks (214068, 214168) was found among the 15
  units checked, most likely because the emotions/thoughts list appears to
  retain only the latest entry per (thought, subthought) pair and an earlier
  delivery by 192/193/194 could have been overwritten by their later,
  still-visible one. Not resolved.
- **The actual semantics of `GetDrinkCooldown` and `RequestWaterCooldown`.**
  Inferred from naming and from one tight timestamp correlation
  (`RequestWaterCooldown = 0` exactly matching each migrant's serviced
  moment); no source on this install documents either trait's true trigger
  condition, and the DF binary that implements the logic is closed-source.
- **Why founders were never selected as `GiveWater` patients at all**,
  despite entering the test thirstier than every citizen who was serviced —
  the central open question of this report, ranked as hypotheses 1-3 above,
  none confirmed.
- **Whether the three confirmed buckets were transiently contended or
  genuinely fouled** by the `dry-buckets.lua`-documented bug at the moment
  Ral's job failed. The buckets sit empty and usable right now, and three
  more deliveries succeeded after Ral's failure using presumably the same
  three buckets, which fits transient contention at least as well as
  permanent fouling.
- **Whether a `GiveWater` fetch uses a different reachability model than
  ordinary unit movement** — the fact that it succeeded three times is new
  evidence against "the pool is flatly unreachable," but doesn't by itself
  explain the 2026-09-16 research's `getWalkableGroup` finding of zero
  adjacent walkable tiles; that finding's own flagged ramp-artifact
  possibility remains open.
- **Whether founders' `GetDrinkCooldown` resets reflect real, repeated,
  failing self-serve attempts, or a periodic utility re-check that fires on
  a timer regardless of any attempt at all.** Not distinguishable from
  static state; needs the live job-creation poll proposed above.
