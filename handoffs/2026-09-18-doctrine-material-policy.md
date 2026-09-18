# Handoff: doctrine entries for material policy and the water chain

Date: 2026-09-18. Stream 3 of 3 from the production-model design pass.
**Read `docs/PRODUCTION-MODEL.md` §10 (bands) and §12 (water) first**, then
`doctrine/seed.yaml`'s own header, which defines the provenance format and the
rule that `verified` requires a live-read or game-data source describing
53.16. The spec is authoritative.

Offline stream. **No VM, no SSH, no DFHack, no fort.**

## Why this stream exists

The design deliberately moved every *target* out of code and into doctrine, so
that a par level or a cover margin can be argued with and revised by an agent
rather than sitting buried in a constant. None of those entries exists yet.
This stream writes them.

It also writes the one entry with a live medical reason behind it: Uniboslan
has a citizen reading unconscious, owns no bucket, and logged a cancelled
"Give water" job for want of one.

## Deliverable: new entries in `doctrine/seed.yaml`

Follow the file's existing entry shape exactly, including per-source
provenance (`kind`, `ref`, `describes`, `read`, `accessed`) and `topics`.
**Nothing in this stream may be `verified`**: these are policy judgements and
community figures, so `prior` throughout, with the reasoning recorded rather
than implied.

### 1. The band vocabulary itself

One entry explaining the banded policy structure so later entries can
reference it rather than restating it: reserve floor, par, cover target,
surplus, and the rule that **class is a property of intended use, not of the
item** (stone below the block reserve is a resource, the same stone above it
is clutter). Also record that **bands are lexicographic, not weighted**, and
that **derived demand gets no cover target** (charcoal is needed only if you
are smelting, so it is netted from a plan instead; give it a cover target and
the fort stockpiles fuel for a furnace nobody built).

### 2. Buckets, as insurance

- A par level of at least two buckets, held permanently.
- The water-carrying labour enabled on **more than one** dwarf, because a
  single point of failure here is a death.
- **Placement: near the route, not at the water.** Uniboslan's ponds sit one
  level below the surface and are likely open to the sky, so a bucket at the
  waterside is exposed to theft by wildlife. A store inside the secured area
  on the way down gives the same travel saving without the exposure.
- The second kind of theft is internal: another job claims the bucket. DF's
  own answer is the hospital zone, which reserves its own supplies. **Record
  that as `prior` and flag it as needing verification**, because it is
  recollection of v50 mechanics and nothing in this project has tested it.
  What *is* certain, and worth recording alongside, is that a claimed bucket
  is now detectable: `item.flags.in_job` came back exact in
  `research/2026-09-18-schema-extraction-live.md`.

### 3. Migration headroom

Cover targets carry a stated margin, with the reason recorded: migration
waves are exogenous and large (a 15-dwarf fort can double in one wave), and
population is Q4, so it must never enter a formula. The margin is a doctrinal
judgement, and the entry should say that plainly so nobody later "corrects"
the padding as arbitrary. Express cover in **dwarf-days**, not days, so a
population jump rescales it automatically.

### 4. The irreplaceable reserve, and what inherits it

Seeds have a hard floor that overrides even survival, because zero is
unrecoverable without a caravan and cooking the last seeds is a locally
rational, permanently fatal decision. Record that **any future breeding pair
inherits the same band automatically**, so the fort's first livestock needs no
new policy.

### 5. Wear, parked with a trigger

Clothing decays and dwarves in rags become unhappy, but it takes roughly two
years to bite and this fort is in year one. Record it as parked **with the
trigger written down**: the first item that reads tattered, or the start of
year two, whichever comes first. Record the method too, so it is not
rediscovered: **count the state, do not model the rate**, the same approach
the spec takes for spoilage.

### 6. Durability, for the cover split

Which food and drink classes are durable (barrelled drink, prepared meals)
versus perishable (raw edibles, especially outside). This is what lets days of
cover split honestly instead of reporting one blended number. Where the
distinction is a judgement rather than a raw token, say so: the static audit
found no reliable rot token, which is precisely why this lives in doctrine.

## Validator

`doctrine/validate.py` already enforces the provenance rules and has 12 tests.
**Run it, and make sure every new entry passes.** If a new entry shape needs a
validator change, make it and add a test; do not weaken an existing rule to
let an entry through. If you cannot express something the spec asks for within
the current format, say so rather than bending it.

## Rules

- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- Ambient `python -m pytest` is 306 passed / 1 skipped before you start.
  Report before and after, including the doctrine validator's own tests.
- Every figure you cite from the wiki or from another research file keeps its
  provenance. Do not restate a figure without its source.
- If a harness, hook or classifier refuses you, **stop and report it.**
- No em dashes in prose.

## Touched surfaces

`doctrine/seed.yaml`, `doctrine/validate.py` and `doctrine/tests/` only if a
format change is genuinely required, this handoff doc. Nothing else: two other
streams are running in parallel.

## Done means

The entries exist, the validator passes on all of them, no entry is
`verified`, every judgement records its reasoning rather than just its number,
and a write-up at the bottom of this file lists what was added and what you
refused to state for lack of a source.

## Write-up (executed 2026-09-18)

**Entries added, all `status: prior`, in `doctrine/seed.yaml`:**

1. `material-policy-bands` (topics: `material`) — the band vocabulary itself:
   reserve floor / par / cover target / surplus, class as a property of
   intended use not of the item, bands lexicographic not weighted, derived
   demand gets no cover target. Reference entry the other five point back to.
2. `bucket-par-and-labor-redundancy` (topics: `water`, `health`, `labor`) —
   par of at least two, the labour on more than one dwarf, placement near the
   route not the water, and the existence-vs-availability lesson (job-claimed,
   forbidden, and caravan-owned deductions can all hide stock a raw count
   shows present). Rewritten mid-stream, see below.
3. `cover-target-migration-headroom` (topics: `material`, `food`, `drink`) —
   cover targets carry a stated margin, expressed in dwarf-days, grounded in
   the wiki's actual `Migrant` wave-size figures rather than an invented one;
   the specific margin (50%) is labelled explicitly as this entry's own
   judgement call, not a cited number.
4. `irreplaceable-reserve-inherited-by-future-classes` (topics: `seeds`,
   `material`) — generalises `seed-stock-never-falls`'s hard floor to any
   future breeding pair, per the design doc's own framing.
5. `clothing-wear-parked-with-trigger` (topics: `material`) — parked, with
   the trigger (first tattered item, or year 2) written down and the method
   (count the state, don't model the rate) recorded.
6. `durability-splits-cover-target` (topics: `material`, `food`, `drink`) —
   durable/perishable classification for an honest cover split, with drink
   and milled powder settled as durable by a raw-confirmed absence of
   `[ROTS]` on their material templates.

**Validator/format change:** added `material` to `doctrine/validate.py`'s
`TOPICS` (and documented it in `seed.yaml`'s header) because entries 1, 3, 4,
5 and 6 describe goods-management policy that isn't about one specific
consumable — none of the eight existing topics fit. Added
`test_material_topic_is_accepted`; no existing rule weakened.
`doctrine/tests`: 12 passed → 13 passed. Ambient `python -m pytest`: 306
passed / 1 skipped → 307 passed / 1 skipped.

**Refused to state for lack of a source:**
- The wear-level thresholds for `x` vs `X` vs `XX` on clothing. The wiki's
  `Clothing` page states the tattered thoughts fire on `X`/`XX` but never
  gives the level count that reaches each symbol; recorded as an open gap in
  entry 5's note rather than guessed.
- Why the tick-214135 "Give Water: Need empty bucket" job failed despite
  three fort-owned buckets existing at the later re-read (reachability? a
  claim released just after the cancel? a stale read?). Left open in entry
  2's note; explicitly not attributed to any single cause without a live
  trace of that specific job, which this offline stream cannot run.
- Whether prepared meals carry the same `[ROTS]`-absence guarantee this
  stream raw-confirmed for drink and milled powder. Entry 6 asserts meals
  durable on the design doc's own framing but flags this as the one
  unconfirmed half rather than folding it in as equally settled.
- A specific migration-wave multiplier ("can double in one wave") as fact:
  not sourced anywhere in this repo, so entry 3 uses the wiki's actual
  `Migrant` figures instead (see "judged wrong" below) and states its own
  50% padding recommendation as a labelled judgement call, not a citation.

**Mid-stream correction — the bucket entry was rewritten:** the orchestrating
session read the live fort after dispatching this stream and found that its
own handoff's stated justification was wrong: Uniboslan owns three
fort-owned, unclaimed, unforbidden buckets (ids 81, 149, 150), and the "1 of
15 citizens unconscious" figure is a sleeping miner
(`unconscious=2, pain=0, wounds=0, current_job=Sleep`), not an injury or a
medical emergency. My first draft of entry 2 had repeated the handoff's false
premise (fort owns no bucket, a citizen at risk of dying of thirst). I
rewrote the entry's statement and note to argue from the true incident
instead: three buckets existed and the Give Water job still cancelled at
tick 214135, which is the available-vs-total distinction
`docs/PRODUCTION-MODEL.md` §7 already names, demonstrated live. The doctrine
guidance itself (par ≥ 2, labour on more than one dwarf, route placement)
did not need to change; only its justification did.

**Judged wrong in the handoff / in `docs/PRODUCTION-MODEL.md`:**
- Item 2's framing ("the one entry with a live medical reason") was wrong per
  the correction above, before I even started — not something this stream
  introduced, but worth naming since it shaped the original brief.
- `docs/PRODUCTION-MODEL.md` §15's "takes ~2 years to bite" figure for
  clothing wear is stale. The current DF wiki `Clothing` page (version
  banner `v53.16`, matching this install exactly) states worn clothing now
  gains one wear level every **ten** years, explicitly calling out the
  two-year figure as the *previous* version's behaviour: "This is a change
  from previous versions, where worn clothing gained one level of wear every
  two years." Storage slows decay further (about a century in a stockpile or
  personal quarters, twenty years under DFHack), and reaching "tattered"
  needs more than one wear level on top of that. Entry 5 records the
  corrected figure and flags that §15 should probably be corrected too; the
  year-2 trigger itself is still fine as a deliberately early, conservative
  check, just not for the reason originally stated.
- The "community figures" for migration wave size were not actually present
  anywhere in the repo (the "can double in one wave" line lived only in this
  handoff's prose, uncited). Rather than restate it without provenance, I
  fetched the wiki's `Migrant` page directly (version banner `v53.16`) and
  used its real numbers instead: each of the first two waves capped 1–10,
  later waves wealth-scaled, capped down from a local population of 1000,
  stopping entirely at 3000.

**Format observation, not acted on:** `SOURCE_KINDS` has no clean category
for "a repo design/build doc" (`docs/*.md`) as distinct from "a repo research
doc" (`research/*.md`) — the `research` kind's own description says "a repo
research doc, which carries its own citations." I cited
`docs/PRODUCTION-MODEL.md` under `kind: research` throughout as a pragmatic
fit (both are opened, dated, repo-internal, citation-bearing text) rather
than adding a new source kind for a distinction the validator has no other
reason to police. Flagging it rather than deciding it unilaterally, since
touched-surfaces discipline argues against widening the schema further than
the six entries actually required.

**Deliverable status:** done. All six entries validate clean, all are
`prior`, `doctrine/validate.py` and `doctrine/tests` are green, and the
ambient suite is green. Two commits on this stream's branch: the `material`
topic addition, and the six entries (the second commit includes the bucket
rewrite — no separate commit was made for the pre-correction version, since
the correction arrived before that commit).
