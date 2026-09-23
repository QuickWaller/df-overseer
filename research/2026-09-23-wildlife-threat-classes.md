# Wildlife and threat classes: what they can do, and when the fort should pause

**Written** 2026-09-23. **For:** `docs/AGENT-LOOP.md` §2/§3 and
`scripts/dfhack/df-overseer-threat.lua`'s admission rule. Read-only research;
no VM writes, no unpause, no push. Every claim below is labelled
**verified** (read directly from the installed game's own raws, DFHack's own
source as already quoted in this repo's prior research, or this repo's own
code and live incident record), **likely** (reasoned from verified material
but not independently tested this session), or **unverified** (web-sourced
prior, or a genuine unknown named as such).

## Method and what was read

Primary sources first, per the brief and `agents/consultant/sites.yaml`:

- The installed creature raws on VM 103, `/opt/df/game/data/vanilla/vanilla_creatures/objects/*.txt`
  (DF 53.16), read directly over the read-only ssh path this session built
  (address resolved inside a script file, never printed; no `hostname` call
  made; fort left paused throughout, no write or unpause).
- This repo's own code: `scripts/dfhack/df-overseer-threat.lua`,
  `df-overseer-clock.lua`, `df-overseer-breach.lua`, `df-overseer-diff.lua`,
  `conductor/briefing.py`, `conductor/cursors.py`, `docs/AGENT-LOOP.md`,
  `docs/AGENT-ARCHITECTURE.md`.
- `research/2026-09-16-player-visibility.md`, this project's own prior
  primary-source read of DFHack's `Units.cpp`/`Maps.cpp` (`isHidden`,
  `isDanger`, `isInvader`, `isAgitated`, `isFortControlled`), cited rather
  than re-derived, since it already did that read against this exact
  install and version.
- `evals/live/2026-09-23-office-and-first-real-build/README.md`, the actual
  kea incident this brief is about.
- One web fetch, the DF wiki's creature-token reference, for token meanings
  the raws themselves don't narrate (`CURIOUSBEAST_ITEM` etc.) — marked
  **unverified**/prior throughout per `sites.yaml`'s own rule that a web
  source supports a prior, never `verified`.

No DFHack command was run against the live process at all this session
(read-only file access over ssh was sufficient); the fort's pause state was
never touched.

---

## Bottom line

The tripwire that stopped the run treats every reachable non-citizen
identically: reachable, therefore pause, full stop
(`df-overseer-clock.lua` `make_check_fn`, step 3 — `threat_mod.find_threats`
returning anything at all writes the latch and pauses). The raws show DF
itself already carries the distinction the tripwire is missing: a fixed,
small set of tags (`CURIOUSBEAST_*`, `LARGE_PREDATOR`, `BENIGN`,
`BUILDINGDESTROYER`, `MISCHIEVOUS`) plus a handful of unit-level invasion
flags (`marauder`, `invader_origin`, `active_invader`, already read from
source in `research/2026-09-16-player-visibility.md`) separate "a kea might
grab something shiny and fly off" from "an ogre is coming to break your
door" from "a goblin squad has arrived." The kea carries **none** of the
dangerous tags. Part E gives the concrete rule: three tiers (record only /
slow / pause), keyed off cheap raw-tag reads plus the reachability this
project already computes, with the kea landing in "record only," and a
standing per-race observation ledger so a repeated harmless visitor becomes
an Overseer-visible pattern instead of either silence or a repeated pause.

---

## A. The taxonomy, from the game's own data

**Verified**, read directly from the installed raws
(`creature_birds_new.txt`, `creature_standard.txt`, and a `grep` census
across all `vanilla_creatures/objects/*.txt` on VM 103):

### A1. Ordinary wildlife (the kea's own class)

`BIRD_KEA`'s full tag set, read verbatim:

```
[NATURAL] [LARGE_ROAMING] [CURIOUSBEAST_EATER] [CURIOUSBEAST_ITEM]
[PETVALUE:25] [PET_EXOTIC] [FLIER] [BONECARN] [CHILD:1] [ALL_ACTIVE]
[BIOME:ANY_TEMPERATE_FOREST] [BIOME:SHRUBLAND_TEMPERATE] [BIOME:MOUNTAIN]
```

No `LARGE_PREDATOR`. No `BUILDINGDESTROYER`. No `AGGRESSIVE`. No
`OPPOSED_TO_LIFE`. Body size tops out at 1000 (roughly 1/60th of a dwarf's
adult mass, which is on the order of 60,000 in these units) — a small
animal, not a combatant. `LARGE_ROAMING` is, per the raw census, the tag
that gates whether a creature can spawn as ordinary wandering wildlife on
the embark biome at all (present on birds, deer, and other plainly harmless
fauna alongside apex predators like wolves — it marks "wild animal," not
"dangerous"). `CURIOUSBEAST_ITEM`/`CURIOUSBEAST_EATER` are the theft tags
(behavior in B). This is the class the tripwire actually caught.

### A2. Benign fauna

`[BENIGN]`, found on a large share of the bird raws (`creature_birds.txt`,
`creature_birds_new.txt`) plus grazers elsewhere. **Unverified** (web,
DF wiki, this session): "non-aggressive by default, and will never
automatically be engaged by companions or soldiers... runs from hostile
creatures, defends only when enraged." Structurally the safest class: it
will not initiate anything, and the game's own soldier AI does not either.

### A3. Predatory wildlife

`[LARGE_PREDATOR]`, found (raw census) on trolls, ogres, giants, sasquatch,
yeti, sea serpents, and a long list of large animals across
`creature_large_*.txt`. **Unverified** (wiki, this session): attacks
creatures smaller than itself; in fortress mode only one predator group
appears per map at a time; tamed instances remain hostile toward other
wildlife. This is a genuinely different class from the kea's: it is built
to attack, not to grab and flee.

### A4. Mischievous intruders

`[MISCHIEVOUS]`, confirmed only on `GREMLIN` in the standard-creature raws
this session (`[LOCKPICKER][TRAPAVOID][MISCHIEVOUS]`). **Unverified**
(wiki): "spawns stealthed and will attempt to path into the fortress,
pulling any levers it comes across... invisible until spotted." This class
is a direct collision with the player-visibility rule (§ below): it is
*designed* to be unseen until it acts, the same structural tension
`research/2026-09-16-player-visibility.md` already named as this project's
hardest grey zone for `isHidden`.

### A5. Building-destroyers

`[BUILDINGDESTROYER:2]`, found (raw census) on trolls, ogres, dragons,
giants, cyclops, ettins, minotaurs, yeti, sasquatch, hydra, colossi — every
one of them also carrying `LARGE_PREDATOR`. **Unverified** (wiki): value 1
targets doors/furniture, value 2 (the only value seen in this raw set)
targets essentially any constructed building. In this raw set,
`BUILDINGDESTROYER` and `LARGE_PREDATOR` travel together — a class that can
kill a citizen is, on this install, the same class that can knock down a
wall.

### A6. Semi-sapient / can-learn creatures

`[CAN_LEARN]`, found on kobolds, gremlins, satyrs, merpeople, and most of
the humanoid megabeast-adjacent creatures (troll, ogre, giant, cyclops,
ettin, minotaur). **Verified structurally** (the raw file itself, not the
wiki): this tag correlates with named, individually-skilled creatures
rather than an anonymous animal population — several `CAN_LEARN` entries
also carry `CAN_SPEAK`. Not itself a danger signal (kobolds are thieves more
than fighters), but a proxy for "this is closer to a person than an
animal," relevant to A7/A8 below.

### A7. Invaders, ambushers, sieges, thieves — not raw tags, unit state

**Verified**, quoted directly from `research/2026-09-16-player-visibility.md`,
which read this from DFHack's own `Units.cpp` at the matching build:

```cpp
bool Units::isInvader(df::unit *unit) {
    return (unit->flags1.bits.marauder || unit->flags1.bits.invader_origin ||
            unit->flags1.bits.active_invader) && !isOwnGroup(unit);
}
```

A siege, an ambush squad, and a lone thief are not distinguished by a raw
tag at all — a goblin siege and a kobold thief can share a species raw.
What distinguishes them is **unit-level flags set at spawn by worldgen/the
invasion system** (`marauder`, `invader_origin`, `active_invader`) plus,
separately, `hidden_in_ambush` (the ambush/sneak bit, gated by
`isHidden`/`isFortControlled`, already the subject of this project's
"no armok" ruling — ambushers must not be filtered on directly, see D and
the player-visibility section below). This project's own prior finding
(`decisions/DECISIONS.md` 2026-09-11/12, re-confirmed in
`df-overseer-threat.lua`'s own header) is that `isInvader`/`isDanger` are
unreliable in both directions and must never be the admitting filter —
still true here, unchanged by this research.

### A8. Megabeasts, titans, night creatures, undead, werebeasts

**Not independently raw-read this session** (none is on this embark's
current threat list, and a full raw census of every megabeast/titan-class
creature was out of scope for the time available). What is known from A3/A5
by construction: DF's named megabeasts (dragon, hydra, colossus, etc.) are
drawn from the same `LARGE_PREDATOR` + `BUILDINGDESTROYER` pool already
read above, just spawned through the worldgen/megabeast system rather than
as wandering wildlife — so the raw-tag classification in A3/A5 already
covers what a megabeast *can do*; what's unverified is the spawn/approach
mechanism specifically (title, announcement, whether it's flagged
`invader`-like). Night creatures and undead are noted in
`research/2026-09-16-player-visibility.md` as gated by different flags
(`OPPOSED_TO_LIFE` for undead — **unverified**, wiki, "hostile to all
creatures except undead and other non-living ones") and by the
`night_attack`/`undead_or_ghost` announcement categories already tagged in
`df-overseer-diff.lua`'s `REPORT_CATEGORY` table (ids 136-138, 139, 150 —
**verified**, read directly from that file). Werebeasts: **unverified,
unknown** — not found in the raw grep this session and not chased further;
flagged as a real gap rather than guessed at.

---

## B. What each class can actually do to a fort

**Verified** structural claims (from the raws) plus **unverified** (wiki)
behavioral detail, kept separate:

| Class | Can do | Confidence |
|---|---|---|
| Ordinary wildlife, no `CURIOUSBEAST_*` | Be present. Nothing else — no attack tag, no theft tag. | verified (absence of tags in raw) |
| `CURIOUSBEAST_ITEM` (**the kea**) | Grab "apparently the highest-value item it can find" and leave the map with it. Does not attack citizens to do this. | unverified (wiki), but the tag's presence on the kea is verified |
| `CURIOUSBEAST_EATER` (**also the kea**) | Grab and flee with food specifically. | unverified (wiki); tag presence verified |
| `CURIOUSBEAST_GUZZLER` | Drink alcohol on-site rather than steal it away — a stock loss, not an escape-with-loot. | unverified (wiki) |
| `BENIGN` | Nothing unprovoked; flees from real hostiles; will only fight if cornered/enraged. | unverified (wiki) |
| `LARGE_PREDATOR` | Attacks and can kill a citizen or livestock, sized down. | unverified (wiki) for mechanism; verified that this project's own kea-attack incident (`decisions/DECISIONS.md` 2026-09-11/12, cited in `df-overseer-threat.lua`'s own header) was a real attack from a creature the naive hostility flag missed — but note the kea itself is **not** `LARGE_PREDATOR`; that incident is evidence the flag-based filter is unreliable, not evidence keas are predators. |
| `BUILDINGDESTROYER` | Breaks doors/furniture (value 1) or most constructed buildings (value 2, the value seen here). | unverified (wiki) |
| `MISCHIEVOUS` (gremlin) | Paths into the fort stealthed, pulls levers it finds. Mechanism collision, not violence — the danger is sabotage via whatever the lever is wired to (a bridge, a cage trap), not a direct kill. | unverified (wiki) |
| Invader-flagged (siege/ambush/marauder) | Kill citizens, in numbers, coordinated. This is what the tripwire's whole design intent is about (its own header: "the reachable-but-unflagged failure mode"). | verified as the tool's design intent; the actual damage mechanism is ordinary combat, not separately sourced this session |
| Theft in general (item or livestock) | Removes a specific item/animal from the fort's stock; a stocks-count loss, not a citizen-safety event. | reasoned from A1/A7, not separately measured |

**The kea specifically, concrete:** it carries both item-theft and
food-theft tags and no combat tags. What it does, worst case per the raws
and the wiki prior: it flies in, grabs one valuable item or one food item,
and leaves. It does not maul anyone. The 2026-09-11/12 kea-attack incident
this project already has on record is a different, separate finding (a
flag-based hostility filter missing a real attack) and should not be read
as "keas attack" — it is evidence the *filter*, not the *kea class*, is
unreliable. No raw tag on `BIRD_KEA` supports a kea attacking a citizen; if
that 2026-09-11/12 incident really was a kea, it would be worth a second
look at whether it was in fact a `BIRD_KEA` or a different creature, but
that is outside this brief's scope to re-litigate.

---

## C. How fast each threat develops, in ticks

**Honestly, mostly unverified.** DF's per-tile movement rate is governed by
a creature's gait/speed stat (present in the raws as frame counts, e.g. the
kea's `STANDARD_FLYING_GAITS:900:691:482:251:1900:2900`) and by terrain,
not by a simple ticks-per-tile constant this session could derive with
confidence from the raws alone — the relationship between those frame
numbers and DFHack's own `abs_tick` units was not independently confirmed
against source this session (this is a real gap, not glossed over: an
executor with more time should read `Maps.cpp`'s pathing/movement code or
run a bounded, live-verifiable timing test rather than trust a number
computed here from raw-file frame counts alone).

What **is** verified, from this project's own incident record:

- The one real data point this project has (`evals/live/2026-09-23-office-
  and-first-real-build/README.md`) is that a kea was **68 tiles away**,
  sharing the citizens' walkable group, when the 900-tick window's
  periodic threat check (`threat_check_every_n: 10`, so roughly every 10
  clock-check intervals — `check_interval_ticks: 100` per that run's own
  armed config, i.e. roughly every 1000 ticks) caught it. The tripwire
  fired on reachability, not proximity or motion, so **this data point
  does not tell us how fast the kea was closing** — only that it was
  already reachable at 68 tiles.
- Order-of-magnitude reasoning, **not a measured number**: at 100 FPS
  (`base_fps`), 900 ticks is about 9 real seconds; a "slowed" cycle at
  `think_fps` 10 buys roughly 10x more wall-clock thinking time per game
  tick. Whatever a kea's true tiles-per-tick rate is, 68 tiles is a
  meaningfully large buffer compared to the tripwire's own check cadence
  (every ~1000 ticks in the run that was actually armed) — there is real
  headroom between "first visible/reachable" and "at the door," but this
  project cannot yet put a tick count on it.
- For a genuine combat threat (a `LARGE_PREDATOR`/invader class), the
  honest answer is **unknown and worth calling unknown**: no live-timed
  ambush-to-casualty case exists in this project's record. `UNIT_ATTACK`
  events are logged by `df-overseer-diff.lua` but that file's own header
  says real delivery was "verified only by mechanism... not a real attack
  during a live test window" — so even the detection latency for a real
  attack is unmeasured, let alone the time from first-reachable to
  first-casualty.

**Recommendation given this gap (folds into E):** since tick-level timing
for combat classes cannot honestly be given a number, the clock policy for
dangerous classes should not depend on a specific tick budget at all — it
should pause immediately and let the Overseer decide with the fort stopped,
which is exactly what `docs/AGENT-LOOP.md` §2's existing "closing in"
mechanism already does for vitals with a computable deadline and defaults to
for everything else. Only the *harmless* classes benefit from a computed
budget, because there the cost of being slow to react is bounded (an item,
not a life).

---

## D. What is cheaply readable at runtime

**Verified**, from the raws and this project's own code:

- **Race name and a fixed tag set are per-species, static, and already
  computed once at world-load** — reading a unit's raw tags is not a
  per-tick world scan, it is a lookup against the creature's `df.creature_raw`
  object, the same cost class as `race_name(unit)` in
  `df-overseer-threat.lua` today (already an O(1) read per candidate, not
  a search). Adding `is_large_predator`, `is_buildingdestroyer`,
  `is_curiousbeast_item`/`_eater`/`_guzzler`, `is_benign`, `is_mischievous`
  as booleans read off the unit's `creature_raw.flags` is the same cost
  shape as the existing `danger_flags()` helper — cheap, per-candidate,
  no map scan. This is the concrete, low-cost lever this report
  recommends exercising.
- **Reachability is already computed** by `find_threats` (`shares_walkable_
  group_with_citizens`, `within_bounded_distance_of_landmark`) — nothing
  new needed there; class-tagging composes with the existing reachability
  filter rather than replacing it.
- **What would be expensive and should not be added:** resolving a unit's
  full invasion/squad membership, its exact intent, or anything requiring
  a search over `world.units.active` beyond the single already-bounded
  pass `find_threats` does. The existing `isInvader`/`isDanger`/
  `isAgitated`/`isGreatDanger` calls are already cheap per-unit predicates
  (confirmed by their use today) but, per this project's own prior finding,
  unreliable as a *filter* — fine to keep reading and reporting as
  `HEURISTIC`, per `docs/AGENT-ARCHITECTURE.md`'s existing
  MECHANICAL/DERIVED/HEURISTIC vocabulary, never as the admission gate.
- **`isHidden`/ambush detection is explicitly out of bounds**, unchanged by
  this report: the 2026-09-16 knowledge-scope fix already excludes
  `isHidden` units from `find_threats`'s candidate list entirely, and nothing
  in this report proposes reading it as a class signal. `MISCHIEVOUS`
  (A4)'s stealth spawn means this project has **no legal way to see a
  gremlin before it acts** — the honest, vanilla-legal fallback is the
  same one `research/2026-09-16-player-visibility.md` already names: DF's
  own announcement layer (a lever pulled, an item missing) rather than
  reading the creature directly.

---

## E. Recommendations

### E1. Three tiers, not one, keyed off raw tags the tool can already read cheaply

| Tier | Trigger (raw tags + reachability, all cheap per-candidate reads) | Clock | Who wakes |
|---|---|---|---|
| **Record only** | Reachable, but the race carries none of `LARGE_PREDATOR`/`BUILDINGDESTROYER`/`MISCHIEVOUS`/invader-flagged (`isInvader` true). Covers ordinary wildlife, `BENIGN`, and `CURIOUSBEAST_*`-only creatures — **the kea, concretely, lands here.** | Full speed, unchanged | Nobody synchronously; goes to the observation ledger (E3) for the Overseer's next ordinary wake |
| **Slowed** | Reachable **and** the race carries `CURIOUSBEAST_ITEM`/`_EATER`/`_GUZZLER` **and** distance is closing or already inside the citizen-occupied walkable group at close range (a computable, cheap re-check: compare `distance_tiles` across two consecutive scans, matching §2's "closing in" pattern) — i.e. an actual theft looks imminent, not just theoretically possible at 68 tiles. Also: any race carrying `isInvader==true` (worldgen invasion flags) but **not yet** sharing a walkable group with a citizen (visible, not yet reachable) — the existing "hostile seen but not yet able to reach the fort" row in §2's table, now given a concrete raw-tag trigger instead of none. | `think_fps` | Overseer (advisory: a theft in progress is a stocks decision, not a life-safety one) |
| **Pause** | Reachable **and** (`LARGE_PREDATOR` **or** `BUILDINGDESTROYER` **or** `isInvader==true` while already sharing a walkable group with a citizen). Covers predators, building-destroyers, and any confirmed invader/marauder/ambush-origin unit that has actually reached the citizen network. | Paused, as today | Overseer, exactly as `docs/AGENT-LOOP.md` §3 already specifies |

**The kea case, explicit verdict:** a `BIRD_KEA` reachable at any distance
should **not** pause the fort. It has no `LARGE_PREDATOR`, no
`BUILDINGDESTROYER`, and `isInvader` is false for ordinary wildlife (no
`marauder`/`invader_origin`/`active_invader` flags on a wandering animal).
It belongs in "record only" until and unless it is actually closing on the
fort with a theft tag while close — at which point it is a "slowed, wake
the Overseer" case at most, never a full stop. This directly overturns the
tripwire's current behaviour on this exact incident.

**Cost of being wrong, both directions, named as the brief asked:**

- **Pausing on every bird** (today's behaviour): the fort never runs long
  enough to be evaluated, which is the actual, already-observed failure —
  one 900-tick window, one kea, stop. This is the cost this report is
  written to fix.
- **Ignoring a thief entirely** (if "record only" were made truly silent):
  loses items and food with no record at all, and the Overseer never learns
  a pattern exists — this is why "record only" still writes to the
  observation ledger (E3) rather than discarding the event; the fix is not
  "stop watching," it's "stop reacting synchronously to every sighting."
- **Ignoring an ambush** (if the invader/reachability pause were loosened):
  loses dwarves, the worst-case and the reason the pause tier keeps the
  invader-flagged-and-reachable case unconditional, with no tick-budget
  reasoning attached (per C's honest gap — no safe number exists to trade
  against a life).

### E2. Player-visibility check, against each tier

- **Record-only tier:** reads only race name and static raw tags plus the
  existing reachability computation, both already legal per
  `research/2026-09-16-player-visibility.md`'s classification of
  `find_threats`'s reachability machinery. A vanilla player watching the
  fort would see the same kea, at the same distance, the same way this
  project's own tools do (nothing here reads `isHidden`, world features, or
  anything spatially gated). **Legal.**
- **Slowed tier (closing-in theft, or a visible-but-not-yet-reachable
  invader):** same fields, same legality — distance closing is derived from
  two legal reachability reads, not a new capability. **Legal.**
- **Pause tier:** unchanged from today's mechanism, already covered by the
  existing `find_threats` player-visibility classification. **Legal.**
- **The one class this report cannot make legally visible at all:**
  `MISCHIEVOUS` (A4/D). No rule proposed here reaches for it, on purpose —
  doing so would reproduce the exact `isHidden` violation
  `research/2026-09-16-player-visibility.md` already flagged as this
  project's hardest grey zone. The only legal fallback remains the
  announcement layer (a lever pulled, an item gone missing), which is a
  **different, existing** mechanism (`df-overseer-diff.lua`'s
  `REPORT_CATEGORY`), not a threat-tier change — flagged here as a real,
  accepted blind spot, not solved by this report.

### E3. A standing observation ledger, not a second tripwire

The coordinator's added question, folded in here rather than as a separate
document.

**(1) Where it lives, and why not the existing diff/cursor mechanism as-is.**
`df-overseer-diff.lua` plus `conductor/cursors.py` already gives each role
"what happened since I last woke," but by construction it is a **flat,
capped, per-role list** (`conductor/briefing.py`'s `MAX_DIFF_EVENTS = 20`,
oldest-truncated) with **no aggregation** — 14 kea sightings would either
blow the cap and silently drop older ones, or crowd out everything else in
the briefing. The right layer is a **new, small, keyed store**, but it
should still be *fed by* the same event stream `df-overseer-diff.lua`
already taps (unit sightings from `find_threats`, and theft-shaped `REPORT`
events once `CREATURE_STEALS_OBJECT` is added to `REPORT_CATEGORY` — it is
not there today, a real gap this report found, see D/A7's citation of
`research/2026-09-16-player-visibility.md`'s §9 "grey zones" list), not a
second independent scan. Concretely: a small JSON/SQLite table analogous to
`CursorStore`'s own file-per-conductor pattern (single-writer, atomic
replace), separate from the cursor file because its lifecycle is different
— cursors are consumed and advance; this ledger accumulates and decays.

**(2) The aggregation key, and what "14 sightings, 3000 ticks, nothing
taken" looks like.** Key on **(race, "what happened")**, not on individual
unit ids — a wandering kea population turns over individuals, and per-unit
tracking would fragment the count without adding anything a player-visible
observer could use either (a vanilla player watching wildlife wander
doesn't track individual bird identities). Each ledger row: `{race,
first_seen_tick, last_seen_tick, sighting_count, closest_distance_tiles,
outcomes: {present: N, theft: N, ...}}`. A new `find_threats` result for a
race already in the ledger increments `sighting_count` and updates
`last_seen_tick`/`closest_distance_tiles` in place — no growth per
sighting, which is what keeps this bounded regardless of how often the
tripwire's periodic scan runs.

**(3) What's worth keeping versus letting decay.** A pure "present, did
nothing" row should decay: once `last_seen_tick` is more than some
multiple of the fort's own scan cadence in the past with no new sighting,
drop the row (or, cheaper still, let the next full-ledger read simply skip
rows older than a window rather than actively sweeping — same "ephemeral,
session-scoped, bounded" discipline `df-overseer-diff.lua`'s own event log
and `df-overseer-breach.lua`'s baseline table already use, both cited in
their own headers as the accepted pattern for this project). A row with
any non-"present" outcome (a theft, a kill, a building-destroyer event)
should **not** decay on the same schedule — it graduates into the register/
`Working.md`'s existing narrative machinery once acted on, same as any
other decision-worthy event, not into this ledger's own longer-term
storage.

**(4) Telling "present" from "did something."** This is exactly what tier
E1's own trigger conditions already compute, so the ledger should record
the *same* distinction the tripwire tiers use rather than invent a second
one: a sighting with no accompanying theft-shaped `REPORT` event in the
same window is `present`; a sighting that lines up with a
`CREATURE_STEALS_OBJECT`-family report (once tagged, see (1)) is `theft`.
This reuses `df-overseer-diff.lua`'s own report/announcement machinery as
the source of truth for "did something," rather than asking the ledger to
infer intent from position alone.

**(5) The line that keeps this from becoming a second tripwire.** The
ledger **never** triggers a clock change, a pause, or a wake by itself —
that is the whole point of putting sightings here instead of in the
tripwire path. It is read-only, consulted by the Overseer (or any advisor)
on its **next ordinary wake** (a routine review, a stuck job, whatever
already woke it for another reason), the same way `docs/AGENT-LOOP.md`'s
own triage table already treats "routine review... at full speed" as a
distinct category from a tripwire. If a future rule ever wants "N sightings
in M ticks escalates to a wake," that escalation belongs back in E1's tier
table as an explicit, named trigger — not as an emergent property of the
ledger being polled aggressively. Keeping the ledger's own write path
free of any pause/wake call is the structural guarantee, not a policy note
that could be forgotten later.

**(6) What this gives the Overseer that a snapshot cannot, and whether it's
proposal material.** A single `find_threats` call only ever answers "is
something reachable right now." A ledger answers "has this fort had a kea
problem" — the shape of a stocking-loss trend a snapshot cannot show,
because no single snapshot contains a rate. **Yes, repeated sightings over
time are exactly the kind of pattern a queue proposal should come from**:
"kea sighted 14 times over 3000 ticks, 2 confirmed thefts, 0 confirmed
kills" is a legitimate `dfqueue` proposal input for the Architect
(fence/trap the yard) or the Quartermaster (stock the lost item type
higher), in the same way `docs/AGENT-LOOP.md` §6's objective-graph design
already wants "viewable logic... every objective carries its history."
This is squarely inside the player-visibility rule: every field in the
ledger (race, tick, distance, outcome) is already something `find_threats`
and the report log legally expose today; aggregating them over time adds
no new capability, only memory.

### E4. What should not be a tripwire at all

Per the brief's own last question: `CURIOUSBEAST_GUZZLER`-only creatures
(drinks on-site, no escape with loot), any `BENIGN` creature regardless of
distance, and any race with a "record only" tier classification under E1
generally. None of these should ever reach the clock-policy code path at
all — they are `find_threats` output that goes straight to the ledger
(E3), never to `df-overseer-clock.lua`'s latch mechanism.

---

## Not verified, and why (collected)

- **Tick-to-tile movement conversion** for any creature class (C) — the
  raw gait frame counts were read, but their relationship to DFHack's
  `abs_tick` was not independently confirmed from source this session. A
  real number here would need either a source read of the movement/pathing
  code or a bounded, timed live test; guessing one would be worse than
  this gap, per the brief's own instruction.
- **Combat/casualty timing** for a `LARGE_PREDATOR` or invader-class threat
  — no live-timed case exists in this project's record; `UNIT_ATTACK`'s own
  delivery is separately unverified per `df-overseer-diff.lua`'s own header.
- **Wiki-sourced token behavior** (`CURIOUSBEAST_*`, `LARGE_PREDATOR`,
  `BENIGN`, `BUILDINGDESTROYER`, `MISCHIEVOUS`, `OPPOSED_TO_LIFE`) — the
  tags' *presence* on specific creatures is verified directly from the
  installed raws; their *behavioral effect* rests on one web fetch of the
  DF wiki's token reference, treated as a prior throughout, never promoted
  to verified.
- **Megabeasts/titans/night creatures/undead/werebeasts as a live spawn
  mechanism** (A8) — raw-tag membership in the same `LARGE_PREDATOR`/
  `BUILDINGDESTROYER` pool is reasoned, not separately confirmed; the
  worldgen/announcement path that brings one onto this specific map was not
  traced this session.
- **Whether the 2026-09-11/12 recorded kea attack was in fact `BIRD_KEA`**
  — flagged in B as worth a second look, not resolved here; the raw record
  for `BIRD_KEA` supports no attack behavior at all.
- **Whether `CREATURE_STEALS_OBJECT` is genuinely absent from
  `df-overseer-diff.lua`'s `REPORT_CATEGORY` table** — confirmed absent by
  grep this session (no match), consistent with
  `research/2026-09-16-player-visibility.md`'s own §9 listing it as a named
  grey zone rather than something already wired in; not independently
  re-derived from the live announcement enum this session (that enum read
  was `research/2026-09-16-player-visibility.md`'s own, cited not repeated).
- **Whether the sibling reachability-fix stream
  (`handoffs/2026-09-23-landmark-reachability.md`) changes anything this
  report depends on.** It targets `df-overseer-landmarks.lua`'s
  centroid-based `walkable` flag on named landmarks, not
  `df-overseer-threat.lua`'s own `shares_walkable_group_with_citizens`
  check (which already uses citizens' own tiles directly, not a landmark
  centroid) — so this report's tiers, which key off `find_threats`'s
  existing reachability output, are **likely** unaffected by that fix, but
  this was reasoned from reading both files' code, not confirmed by
  running the fixed version.
