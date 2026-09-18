# Handoff: the days-of-cover calculator

Date: 2026-09-18. **Gated on the `production/` package stream
(`handoffs/2026-09-18-production-package.md`) landing and merging**, because
this builds on its tables and would otherwise collide on the same files.

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §1, §3, §10 and §11, then
this. Step 5 of the spec's build order.

Offline stream. **No VM, no SSH, no DFHack, no fort.**

## Why this stream exists

This is the design's flagship output, the one number a quartermaster would
actually be asked for: **how long can the fort last, and is that longer than
it takes to make more.** It needs no solver, no job times, no scheduler and no
new dependency. Everything it consumes is either Q1 (raws) or Q3 (exact live
reads), which is exactly why it is worth building before anything cleverer.

It also has to be the model citizen for honest degradation, because one of its
terms is currently unavailable and the temptation to fill it with a plausible
number is precisely the failure this project keeps catching itself in.

## Deliverable

A pure calculator in `production/`, unit-tested the way
`learning/predictions/` already tests its own calculators. **It takes a
snapshot structure and returns a report. It does not make live calls.** The
caller assembles the snapshot; that boundary is what makes it testable and
what keeps the live-read layer joined rather than merged (spec §7).

### What it computes

**Cover, in dwarf-days.** Stock divided by measured per-dwarf consumption,
expressed in dwarf-days rather than days so a population change rescales it
automatically (`doctrine/seed.yaml`, `cover-target-migration-headroom`).

**Split durable from perishable**, per spec §11 and the
`durability-splits-cover-target` doctrine entry. One blended number is
dishonest when part of the stock will be mush. The target output shape is
closer to: *eleven dwarf-days of cover, of which three are raw edibles, and of
those, some already flagged rotten.* Every term in that sentence is exact.

**Consumption rate from two observations**, not from a wiki figure. Two
`production_observation` rows for the same metric at different `abs_tick`
values give an exact rate: this is the design's central asymmetry, that demand
is exact while supply capacity is not (spec §3). If only one observation
exists, the rate is **unknown**, and the report says so rather than falling
back to a per-dwarf wiki figure. A wiki fallback would be a `prior` masquerading
as a measurement, and worse, it would hide the fact that nobody has taken a
second reading.

**Compare cover against resupply lead time.** This is the whole point: a cover
figure alone does not tell you whether to act. Cover of nine days matters
entirely differently depending on whether more food is four days away or
forty.

### The term that is currently unavailable, and how to handle it

**Resupply lead time for a crop is not computable yet.** Plump helmet's
`growdur` reads 300 while live `grow_counter` values are in the tens of
thousands, so the unit is unsettled: candidate conversions give a quarter of
a day, two and a half days, or 250 days (spec §11).

**Do not pick one. Do not use a wiki figure. Do not interpolate.** The
calculator must return this term as explicitly unavailable, carrying the
reason, and the overall report must still be useful without it: cover itself
is computable and valuable on its own. When the unit is settled by
`handoffs/2026-09-18-supervised-run-and-measure.md`, the term fills in with a
`measured` status and nothing else about the calculator changes. **Write the
test that asserts the unavailable path returns a report rather than raising,
and that it never emits a number for that term.**

### Targets come from doctrine, never from code

Cover targets, their migration margin, and the durability classification are
doctrine entries written today: `material-policy-bands`,
`cover-target-migration-headroom`, `durability-splits-cover-target`. Read them;
do not restate their numbers as constants. A target buried in code cannot be
argued with, which is the entire reason the design moved them out (spec §10).

The report should say whether cover is **above the target, below it, or below
the reserve floor**, since those three are different decisions, and the bands
are lexicographic rather than weighted.

### Every term carries a status

`verified_raws`, `measured`, `prior` or `unavailable`, per spec §4. A consumer
reading this report must be able to tell a measured rate from a raws figure
from a gap. That is the same discipline as every other table in the model, and
here it is load-bearing, because a cover report is exactly the kind of output
that gets quoted back without its provenance.

## Tests that matter more than coverage

- **Two observations give an exact rate; one observation gives `unknown`**, not
  a wiki fallback.
- **The unavailable lead-time path returns a usable report** and emits no
  number for that term.
- **Perishable and durable are reported separately**, and a stock that is
  entirely perishable does not silently inflate cover.
- **A population change rescales cover** without the consumption rate being
  re-measured, which is what dwarf-days buys.
- **Below-target, below-floor and above-target** each produce a distinct
  verdict.

## Rules

- No new runtime dependency.
- No coordinates anywhere.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- Ambient `python -m pytest` is 307 passed / 1 skipped as of the doctrine and
  docs merges. Report before and after.
- If a harness, hook or classifier refuses you, **stop and report it.**
- No em dashes in prose.

## Touched surfaces

`production/**` and this handoff doc. Nothing else.

## Done means

The calculator exists as pure functions with the named tests passing, a cover
report can be produced from a synthetic snapshot, the lead-time term is
honestly unavailable rather than estimated, every term carries a status, and
the write-up at the bottom of this file states what the report can and cannot
tell a reader today.
