# Research: every announcement the game can make, and what level of attention each deserves

**Date:** 2026-09-23. **Scope:** all 357 `df.announcement_type` values on this
install, each assigned exactly one level
(`research/data/2026-09-23-announcement-severity.yaml`). Read-only throughout;
the fort stayed paused, no VM write, no unpause, no push. Answers
`research/BRIEF-2026-09-23-announcement-severity.md`.

**Ownership boundary, stated up front:** this report owns the taxonomy and
the level assignment. It does **not** own wildlife classes, the kea verdict,
or the warnings list's own aggregation/decay/storage shape — that is
`research/BRIEF-2026-09-23-wildlife-threat-classes.md`'s territory (a sibling
stream, running in parallel). Where this report's own classification touches
that ground (the `AMBUSH_MISCHIEVOUS` finding below, in particular) it is
named as a finding for that stream to confirm or override, not settled here.

---

## Bottom line

| Level | Count | Meaning |
|---|---:|---|
| `pause` | 25 | Fort stops, an agent looks now |
| `slow` | 23 | Slow to `think_fps`, wake a role |
| `notice` | 139 | Warnings list, read at the next wake |
| `log_only` | 93 | Recorded, never surfaced unless asked |
| `ignore` | 77 | Adventure mode, menu chatter, or unused enum slots |

The largest single finding is **not a count, it's an absence** (§C): this
fort's sharpest observed failure — manager orders queued and never run —
produces **no announcement of any kind**, across every type in this
vocabulary. The channel this brief classifies cannot see that failure mode at
all. No level assignment fixes that; only polling does.

The second-largest finding is that **DF's own installed source already
classifies every one of these 357 types**, via an `alert_type` enum-attribute
this project had not previously read, and that classification is a genuinely
useful cross-check, not a substitute, for the level assignment below (§A.1).

---

## Method and sources, ranked

1. **The live install's own enum**, already read by the orchestrating session
   2026-09-23 and saved at `research/data/2026-09-23-announcement-types.tsv`
   (357 ids and names, `df.announcement_type` on VM 103). Not re-read this
   session, per the brief's instruction. `[live]`, highest confidence.
2. **DFHack's own installed source**: `scripts/dfhack/df-overseer-diff.lua`'s
   `REPORT_CATEGORY` table (ids 6–48, 53–66, 95–96, 106–107, 136–139, 150,
   166–167, 177, 183, 285, 322), built and **live-verified against 21 real
   reports that reconstructed the kea fight** (this file's own header,
   2026-09-12/22). Reused directly wherever it already covers an id, rather
   than re-deriving a classification the project already trusts. `[code,
   live-verified]`, high confidence.
3. **A fresh shallow clone of `DFHack/df-structures`** (`master`, cloned this
   session into scratch, not committed to this repo — same method
   `research/2026-09-16-player-visibility.md` used for the same source).
   `df.g_src.basics.xml`'s `announcement_type` enum carries an `alert_type`
   enum-attribute **per entry** — DF's own internal grouping for which
   toggle in the in-game "announcements" settings menu controls that type
   (`GENERAL`, `MONSTER`, `AMBUSH`, `CRIME`, `AGREEMENT`, `UNDERGROUND`, …).
   **Verified this session:** joining this master-branch enum against the
   live install's 357 names (not ids — matched by name, the safer key) found
   **all 357 names present with identical ids on both sides**, so this
   master clone's ordering matches the exact installed 53.16-r1.1 enum, not
   just a nearby version. `[C-XML, cross-checked by name against a live
   read]`, high confidence for the join itself; the *meaning* DFHack intends
   for each `alert_type` bucket was not separately read from DFHack's own
   settings-menu code, so treat `alert_type` as a directional cross-check
   ("this project already thinks these are related"), not as this report's
   own severity judgment.
4. **This project's own docs**: `docs/AGENT-LOOP.md` §2/§3 (clock levels,
   tripwires), `docs/AGENT-ARCHITECTURE.md` §4 (closed wake-event vocabulary,
   its own 2026-09-12 check against DFHack's real event types) and §5 (Tier
   0/1/2 information architecture), `conductor/{policy.yaml,triage.py,
   briefing.py,cycle.py}` (what the conductor already wires and what it
   admits is still a gap), `research/2026-09-16-player-visibility.md`
   (the visibility boundary, applied to every level below), `docs/TRAPS.md`
   (the cancellation-report linkage gap, the announcement-buffer pruning).
5. **Live eval evidence**: `evals/live/2026-09-23-office-and-first-real-build/`
   (this fort's only unattended run to date; the kea tripwire and the
   zero-announcement 900-tick manager-order silence both come from here).
6. The DF wiki was not needed for this pass — the primary sources above
   were sufficient for every id. Nothing here rests on `[C-Wiki]` or
   `[WebSearch]`.

---

## A. All 357 classified

Full data: `research/data/2026-09-23-announcement-severity.yaml`, keyed by
enum name, each entry carrying `id`, `level`, `alert_type` (DF's own
grouping, §method item 3), `reason`, `wake` (role list, only where
non-empty), `context_dependent` (bool, only where true), and `confidence`
(`verified`/`likely`/`unverified` — **per entry**, not a blanket figure for
the file, per the brief's own instruction).

### A.1 How the assignment was actually made

Four families of evidence, applied in this order per id:

1. **Already fort-verified.** Where `df-overseer-diff.lua`'s
   `REPORT_CATEGORY` already tags an id (combat detail, ambush, night
   attack, undead/ghost, berserk/tantrum, death), that tag's own real-world
   verification (§method item 2) is reused directly. This covers the combat
   blow-by-blow family (`COMBAT_*`, 45 ids) as `log_only` — the aggregate
   ambush/death/berserk signal is the decision-relevant level, the
   punch-by-punch text is the full-report tier only (§D).
2. **DF's own severity framing, read structurally.** A type whose *name*
   states an irreversible or fort-threatening outcome (`CITIZEN_SNATCHED`,
   `BUILDING_DESTROYED_OR_TOPPLED`, `BODY_TRANSFORMATION`,
   `MEGABEAST_ARRIVAL`) is `pause` regardless of `alert_type`, because the
   consequence is already named in the enum and needs no inference.
3. **Precursor-to-tripwire reasoning.** Several types are not themselves
   the bad outcome but are DF's own advance warning of one already in this
   project's tripwire set: `STRESSED_CITIZEN`/`CITIZEN_TANTRUM` precede
   `CITIZEN_LOST_TO_STRESS`/`BERSERK_CITIZEN`; `INTERACTION_ACTOR`/
   `INTERACTION_TARGET`/`EMBRACE` precede `BODY_TRANSFORMATION`. These are
   `slow`, not `pause`, on the same logic §2 of `docs/AGENT-LOOP.md`
   already states for "vital nearing its threshold": early enough to act,
   not yet the emergency itself.
4. **Everything else**, by domain: routine population/economy/social
   events are `notice` (background information genuinely worth a briefing
   line, matching `docs/AGENT-ARCHITECTURE.md` §5's Tier 1); flavor/status
   detail with no decision attached is `log_only`; adventure-mode-only
   text (`ADV_*`, `YOU_*`, `NO_INV_*`, most `CANNOT_*`, the whole
   inventory/travel/conversation UI-response family) is `ignore`, since
   this project runs fortress mode exclusively and none of that vocabulary
   can fire here — flagged `likely`, not `verified`, since no adventure-mode
   session exists to confirm the negative.

### A.2 The most consequential individual finding: `AMBUSH_MISCHIEVOUS`

The `AMBUSH_*` family (ids 53–66, plus `BEAST_AMBUSH` at 95) is not one
severity. DF's own naming already splits it: `AMBUSH_SNATCHER` (a
child-snatcher — `pause`, same consequence as `CITIZEN_SNATCHED`),
`AMBUSH_AMBUSHER`/`AMBUSH_DEFENDER`/`AMBUSH_RESIDENT` (a real combat
ambush — `pause`), `AMBUSH_THIEF` and its support variants (item loss,
real but recoverable — `slow`), and **`AMBUSH_MISCHIEVOUS`** — DF's own
name for exactly the "mischief-class creature causing minor disruption"
case the sibling wildlife-threat brief is investigating from the kea
incident (`evals/live/2026-09-23-office-and-first-real-build/`, a kea 68
tiles away tripped `hostile_reachable` and ended the run at 900 of an
allowed 2000 ticks). **This report classifies `AMBUSH_MISCHIEVOUS` as
`slow`, not `pause`** — DF is already telling the fort, in its own
vocabulary, that this is the low-severity ambush variant, distinct from
the ones that cost a citizen or a fight. This is offered to the sibling
stream as a candidate answer to "what should the kea case actually be,"
not asserted as the final verdict — that call is the sibling brief's to
make, since it owns the wildlife taxonomy and what a kea can concretely
do.

### A.3 The second most consequential finding: `CITIZEN_DEATH`/`PET_DEATH` vs. the existing death tripwire

`docs/AGENT-LOOP.md` §3's built death tripwire fires on the raw DFHack
`UNIT_DEATH` eventful event. `research/2026-09-16-player-visibility.md`
already flags that event `omniscient`: it "fires engine-wide for *any*
unit's death... broader than the announcement layer and not gated by
visibility at all" — its own worked example is that "the kea's own death
generated no report at all." The `CITIZEN_DEATH`/`PET_DEATH` report ids
(106/107) are the other channel: the actual player-visible death
announcement, already tagged `"death"` in `REPORT_CATEGORY` and gated by
construction to events DF itself decided to tell the player about.
**Recommendation, carried into §E:** the existing tripwire is not wrong to
pause on a death, but it is currently pausing on a broader, ungated signal
than the vanilla-legal one sitting right next to it. Worth checking whether
switching (or adding) the report-based signal changes anything observed in
practice — not urgent, since both fire `pause` and a false negative here is
the dangerous direction, not a false positive.

### A.4 A structural cross-check: DF's own `alert_type` against this classification

`alert_type` distribution across the 357 (§method item 3): `GENERAL` 194,
`NOBLE` 14, `CRIME` 13, `MONSTER` 11, `WEATHER` 11, `AGREEMENT` 11, `AMBUSH`
10, `ANIMAL` 9, `UNDERGROUND` 8, `JOB_FAILED` 7, `MIGRANT` 6, `TRADE` 6,
`ART_DEFACEMENT` 6, `MASTERPIECE` 6, `MILITARY` 5, `DEATH` 5, and eighteen
more groups of 1–4. This is a genuinely different axis than the level
assignment — it groups by "which settings toggle," not "how urgent" — but
it is a useful sanity check: every id this report marked `pause` for a
combat/threat reason (`MONSTER`, `AMBUSH`, `DEATH`, `UNDEAD_ATTACK`,
`MILITARY`) falls in a small alert_type set DF itself treats as
player-configurable-visibility-worthy, and nothing this report marked
`ignore` carries a combat-adjacent `alert_type`. No contradiction found
between the two axes; recorded as a cross-check that passed, not as
independent proof.

---

## B. The conditional ones

Every type whose real severity depends on context outside the announcement
itself, and what that context is:

| Type | Depends on | Cheap at tick-timer cost? |
|---|---|---|
| `CANCEL_JOB` | Whether it repeats at the same job/location. **`docs/TRAPS.md` already records that cancellation reports carry no linkage fields** — `speaker_id`, `activity_id`, `activity_event_id` are all `-1` on a real entry, and the cancelled job itself is removed from `world.jobs.list` entirely, leaving nothing structural behind. So "did this repeat" cannot be answered by joining the report to a job; it can only be answered by text-matching the report's own string across a rolling window. | **No, not cheaply.** Text-matching a growing buffer against itself is not the O(1) tick-timer check this project's tripwires need; it belongs in the conductor's own bounded diff-drain step, not inside the in-game Lua tripwire. |
| `CONSTRUCTION_SUSPENDED`, `LINKAGE_SUSPENDED` | Whether the fort is actually waiting on that specific construction (the brief's own example: "the one the fort is waiting on"). A single suspension is routine and often self-resolves (buildingplan waiting on material, exactly `evals/live/2026-09-23-office-and-first-real-build/`'s own Chair). Repeated suspension of the *same* building over a long window is the real signal. | **Partially.** `stuckjobs.find` already exists and is a bounded, targeted read (`docs/TRAPS.md`'s own "never run an unbounded query" rule); the missing piece is duration/repeat tracking across calls, which belongs in the conductor's cursor state (`conductor/cursors.py`), not a fresh scan each time. |
| `AGREEMENT_WARNING` | How close the agreement is to `AGREEMENT_ABANDONED`. Nothing in this fort's history has touched an agreement yet (`alert_type: AGREEMENT`, 11 ids total, none live-observed), so this is unverified rather than reasoned from evidence — flagged `unverified` in the YAML, not asserted. | Unknown; no live case to check against. |
| `FOOD_WARNING` | Whether it duplicates the vitals-based hunger/thirst cover-days figures the briefing already computes (`conductor/briefing.py`'s own `vitals` block). If it is DF's own independent low-food alarm, it is corroborating; if it fires on a different threshold than this project's own `hunger_critical`/food-days math, the two could disagree and one of them needs to win. | Cheap to read (single report id), but the *comparison* against the vitals figures needs both values in hand at once, which the conductor's read step already does. |
| `AMBUSH_MISCHIEVOUS` vs. `AMBUSH_THIEF` vs. `AMBUSH_SNATCHER` vs. `AMBUSH_AMBUSHER` | Which specific sub-type fired — **not actually conditional once the id is known**, since DF's own naming already resolves it (§A.2). Listed here only to say plainly: this family looks like it needs context but does not; the id alone is the signal. | N/A — already resolved by id. |
| `CITIZEN_MISSING`, `PET_MISSING` | Whether the unit later turns up dead, trapped, or off-map with a caravan/migrant group. A single instance is `slow`/`notice`; a unit still missing after a bounded window (say, the next few routine-review cycles) escalates. | Cheap in principle (a unit-id watch list), not yet built. |

---

## C. What the announcement channel cannot tell us at all

This is the real finding the brief asked for, and it is a finding about
absence, not about any of the 357 ids.

**The evidence:** `evals/live/2026-09-23-office-and-first-real-build/`
watched all four of this fort's manager orders (ids 0–3) across a 900-tick
unattended window. None changed state — no order moved from
`validated: true, active: false` to `active: true`, none finished, the one
job spawned by a direct build call sat `suspended` the whole window
(`stuckjobs.find`, already a working, bounded tool). **Zero announcements
fired for any of it.** No `CANCEL_JOB`, no `JOB_OVERWRITTEN`, no
`CONSTRUCTION_SUSPENDED` for the manager-order path specifically (that one
did fire, but only for the directly-built Chair, not for a manager order —
manager orders that never dispatch a job in the first place have nothing
to cancel or suspend). `CLAUDE.md`'s own status line names the same fact
from the earlier, longer window: "the queued manager orders still do not
run" across a wider stretch of fort time, with the leading suspected cause
being the fort's missing Office (since partially addressed the same day).

**What this means structurally:** DF's announcement layer is a log of
things that *happened*. A manager order that never dispatches a job is
something that **did not happen**, and DF has no announcement type for "an
order has been sitting unrun for N ticks" — there is no id in this
vocabulary that means that, and there structurally cannot be one, because
announcements are generated by the game's own event pipeline firing, and
a non-event fires nothing by construction. Searching the full 357 for a
near-miss candidate (`QUOTA_FILLED`, `JOB_OVERWRITTEN`, `NEW_WORK_MANDATE`)
turned up nothing that means "this order is stalled" either — those cover
adjacent but different concepts (a stockpile quota being met, a job being
replaced by a newer one, a mandate being issued).

**So this class of failure is structurally invisible to the announcement
channel and must be found by polling instead** — reading `orders.list`
across two conductor cycles and diffing `validated`/`active` state, exactly
as this eval did by hand. That comparison is already cheap (a small,
bounded list read, not a scan) and already exists as a tool
(`df-overseer-orders.lua`). What is missing is wiring it into
`conductor/triage.py`'s `stock_below_target`/`stuck_job` computable-reason
machinery as a first-class signal ("an order has been active/pending for
more than N ticks with no state change"), not adding anything to the
announcement vocabulary, since there is nothing there to add.

**A second, narrower gap of the same shape:** `docs/AGENT-ARCHITECTURE.md`
§4's own 2026-09-12 audit already found this pattern once before —
`breach` (a flood) has **no signal of any kind**, announcement or event, and
is still (`docs/AGENT-LOOP.md` §3) "not covered" by any tripwire. The
manager-order silence is the same shape of gap in the labor/production
domain that the flood gap is in the physical-hazard domain: **both need a
poller, and no amount of refining the announcement classification in this
report closes either one.**

---

## D. Levels of detail

The brief asks for three depths per event, and what decides which survive
when many compete for room in `conductor/briefing.py`'s already-capped
prompt (`MAX_DIFF_EVENTS = 20`, `MAX_QUEUE_IDS = 20`).

**One-line briefing entry** (what fits in the capped list): `<level icon or
word> <type name>, tick <T>, <one clause>` — e.g. `pause: CITIZEN_SNATCHED,
tick 12607074, a citizen was taken`. This is deliberately the *type name
plus a fixed one-clause gloss from this report's own `reason` field*, not
free text generated per event — the classification YAML already carries
exactly this string for all 357, so the briefing layer can look it up
rather than compose it, keeping cost at read time, not generation time.

**Expanded entry** (for anything a role actually opens, matching
`docs/AGENT-ARCHITECTURE.md` §5's Tier 1): counts and timing — how many of
this type since the role last woke, the tick of the first and most recent,
and (where computed) ticks-to-consequence the way `conductor/policy.py`
already derives it for `vital_nearing_threshold`/`stuck_job`. This is
where the `AMBUSH_THIEF` vs. `AMBUSH_SNATCHER` distinction actually earns
its keep in a real cycle: two `AMBUSH_THIEF` events in the last 200 ticks
reads differently from one `AMBUSH_SNATCHER`, and only the expanded tier
needs to show that count.

**Full report text** (Tier 2, `docs/AGENT-ARCHITECTURE.md` §5: "never in a
default prompt... only on a flagged anomaly, on request"): the actual
`report.text` string, exactly as `df-overseer-diff.lua` already reads it
(`rep.text`). This is where the `log_only` tier (93 types, mostly
`COMBAT_*` blow-by-blow) belongs by design — recorded, retrievable, never
pushed into a prompt unless a role specifically asks to reconstruct what
happened, the same way `recent-combat`/`since-report` already work
retrospectively over `world.status.reports` without needing registration.

**What decides which survive the cap:** level first (every `pause` and
`slow` event survives before any `notice` is admitted), then recency
within a level, then — only once the cap is still not reached —
`notice`-level events in the same order. `log_only` and `ignore` never
enter the briefing at all; they exist only for the full-report-text tier
and, for `ignore`, arguably not even there (an `ignore` event could be
dropped at the diff-drain step rather than merely deprioritized, since
nothing in this project's design ever reads it back). This matches the
existing cap shape in `conductor/briefing.py` — `_capped()` already
truncates and reports `truncated: true` — the only change this report
recommends is that the *ordering* fed into `_capped()` be level-first,
which `build_briefing` does not currently do (it receives `diff_events` in
whatever order `diff.since` drained them, not sorted by this
classification).

---

## E. Recommendation

### What the never-built announcement tripwire should fire on

**A concrete rule, over this report's own `level` field:** the in-game Lua
tripwire (`docs/AGENT-LOOP.md` §3, "a new announcement of an alert class,"
still owed) should pause the fort on any newly-arrived report whose `type`
resolves to `level: pause` in `research/data/2026-09-23-announcement-severity.yaml`
— 25 ids, a fixed, small set the Lua script can hold as a literal id table
the same shape as `REPORT_CATEGORY` already uses, no runtime lookup needed.
This is a direct extension of a pattern this project already trusts
(`REPORT_CATEGORY`'s own live-verified table), not a new mechanism.

**What should never be a tripwire:** anything this report marked
`log_only` or `ignore` (170 of 357) should never even reach the tripwire's
own id check — filtered at the same point `REPORT_CATEGORY`'s
`category_of()` already filters, so an uncategorized report costs nothing.
The `slow` tier (23 ids) should specifically **not** pause — it should set
`clock: slowed` and wake the role named in `wake`, through
`conductor/triage.py`'s existing machinery, not through the in-game Lua
pause path at all. This is the direct fix for the `AMBUSH_MISCHIEVOUS`
finding (§A.2): if the tripwire only pauses on the 25 `pause`-level ids,
and `AMBUSH_MISCHIEVOUS` is not one of them, a kea-class encounter slows
the fort and wakes the Overseer instead of stopping the whole run —
without weakening coverage of the fort-ending cases DF's own naming
already flags as different (`AMBUSH_SNATCHER`, `AMBUSH_AMBUSHER`).

**What I would change about the existing four tripwires, in light of the
full list:**

1. **The announcement tripwire (this one, still owed) should be built as
   the fifth, not folded into an existing one.** It covers a genuinely
   different failure mode than death/critical-vital/reachable-hostile: all
   three of those are numeric-threshold or reachability checks over live
   game state, while this one is a fixed-id lookup over the report stream.
   Different mechanism, deserves its own entry in `docs/AGENT-LOOP.md` §3's
   table, not a special case bolted onto `hostile_reachable`.
2. **The death tripwire is worth re-pointing at `CITIZEN_DEATH`/`PET_DEATH`
   (report ids 106/107) rather than, or in addition to, the raw
   `UNIT_DEATH` eventful event** (§A.3) — the report-based signal is the
   one actually gated to player-visible deaths, and switching or
   dual-arming it costs nothing since both already resolve to `pause`.
3. **The reachable-hostile tripwire's threat-scan admission rule
   (`shares_walkable_group_with_citizens` or near-a-landmark) has no
   severity judgment at all**, per `df-overseer-threat.lua`'s own header
   and this fort's own kea incident. This report cannot fix that — the
   sibling wildlife-threat brief owns what should gate it (creature class,
   `BENIGN`/`MISCHIEVOUS` raw flags, size) — but it can say plainly that
   **the announcement-level classification in this report and the
   reachability tripwire are answering two different questions
   (`"is DF telling us something happened"` vs. `"can a unit physically get
   here"`) and neither substitutes for the other.** A fort could have a
   `pause`-level `AMBUSH_SNATCHER` announcement fire from a unit the
   reachability check has not yet flagged reachable (announced before it
   is adjacent), or a reachable, harmless kea trip the reachability
   tripwire with no announcement at all (ordinary wildlife triggers no
   report). Both tripwires are needed; this report only fixes the
   announcement one.
4. **No tripwire should be built for the manager-order silence (§C)** —
   there is no announcement to hook, by construction. That gap needs a new,
   fifth *kind* of check entirely: a polled state-diff over `orders.list`
   inside `conductor/triage.py`'s existing computable-reason machinery
   (`stuck_job`/`stock_below_target`'s own pattern), not a Lua-side
   announcement tripwire at all. Flagging this explicitly so it is not
   quietly expected to fall out of this report's own deliverable — it
   cannot.

---

## Not verified, and why

- **`alert_type`'s exact intended meaning per bucket** was read as an enum
  value, not traced into DFHack's own settings-menu C++ to confirm what
  each bucket actually gates in the UI. Used here only as a directional
  cross-check (§A.4), never as the level assignment itself.
- **Real firing of several report ids this fort has never triggered**:
  `EMERGENCY_TACTICAL_CONTROL`, every `AGREEMENT_*` id, `NIGHT_ATTACK_*`,
  `BODY_TRANSFORMATION`/`INTERACTION_ACTOR`/`INTERACTION_TARGET` (werebeast/
  vampire mechanics), and the world-tier `ENDGAME_EVENT_*` ids have never
  been observed live on Uniboslan. Their `level`/`reason` in the YAML is
  reasoned from the enum name and DF's general mechanics, not confirmed
  against a real report; each is marked `confidence: unverified` or
  `likely` in the data file, never `verified`, for exactly this reason.
- **Whether every adventure-mode-tagged id (`ignore`, 77 of 357) is truly
  unreachable from fortress mode.** Reasoned from DF's well-known mode
  split and the names themselves (`ADV_*`, `YOU_*`, the inventory/travel
  UI-response family), not confirmed by running adventure mode against
  this install or reading the game's own dispatch code for each id. If one
  of these somehow fires in fortress mode, it would currently be silently
  dropped rather than misclassified as urgent — the safe direction of
  error, but worth naming as unverified rather than assumed.
- **The exact key a drained `diff.since` event carries its `type`
  classification under**, needed to wire this report's `level` lookup into
  `conductor/cycle.py`'s `EVENT_TYPE_TO_SIGNAL` machinery. That file's own
  header already flags this exact gap ("unverified against a real
  diff.since payload... no VM this stream") — this report inherits, not
  resolves, that open question.
- **Whether `CANCEL_JOB`'s repeat-detection (§B) is worth building at all**
  given the linkage-field gap `docs/TRAPS.md` already documents. This
  report names the constraint; whether text-matching a rolling window of
  cancellation strings is worth the engineering against how often it would
  actually change a decision was not evaluated — no live frequency data
  exists for how often `CANCEL_JOB` repeats at the same site on this fort.
