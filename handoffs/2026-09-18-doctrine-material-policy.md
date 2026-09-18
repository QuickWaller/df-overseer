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
