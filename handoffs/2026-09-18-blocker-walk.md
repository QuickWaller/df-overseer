# Handoff: the blocker walk

Date: 2026-09-18. **Gated on the `production/` package stream
(`handoffs/2026-09-18-production-package.md`) landing and merging.** Runs
before or alongside `handoffs/2026-09-18-days-of-cover.md`; both touch
`production/**`, so **only one of them may be in flight at a time.**

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §1, §2, §7 and §9, then
this. Step 4 of the spec's build order.

## Why this stream exists

Of the three questions the model exists to answer, this is the one the spec
says is answerable **exactly, today, with no figures at all**, and it is the
cheapest. It is also the piece that turns a static database into something
that says a useful sentence about the fort: *the well is blocked on blocks,
because no mason's workshop exists and there is no other route.*

## What it is

An AND-OR traversal of the stored hypergraph, rooted at a goal instead of at
raw materials. A node needs **all** of its process's reagents, which is the
AND. A node with several producing processes offers a choice, which is the OR.
Walk down and the answer is **the first node with zero available stock and no
completable process**, named, with the quantity short.

This is not a second data model. It is the hypergraph read backwards, which is
why it costs nothing extra beyond the traversal itself.

## The three things that make it correct rather than plausible

### 1. Available stock, never total stock

Spec §7. A stock count is not plannable until four deductions are applied, and
all four are exact reads:

| Deduction | Read |
|---|---|
| claimed by a pending job | `item.flags.in_job`, a plain flag, **no job scan needed** |
| owned by a dwarf | `item.flags.owned` plus the `UNIT_HOLDER` ref |
| forbidden | `item.flags.forbid` (**not** `forbidden`, which errors outright) |
| caravan-owned | `flags.trader`, already implemented in `df-overseer-stocks.lua` |

A fifth case, an item moved to a trade depot for sale, is **unverified**
because the fort has never had a depot. Handle it as unknown rather than
assuming it behaves like one of the four.

**This is the failure the fort already demonstrated**: it held three empty
buckets and still failed to deliver water. A walk that reads totals would have
reported no problem.

### 2. Buildings are nodes, so a missing workshop is a blocker rather than a footnote

Spec §4. "No mason's workshop" has to fall out of the traversal, not be a
special case bolted on. If it needs a special case, the node model is being
worked around and that is worth reporting rather than patching.

### 3. Hardcoded processes must be in the graph

Spec §17. `MakeAsh` (185), `MakeLye` (186), `MakePotashFromLye` (187),
`MakePotashFromAsh` (189) and the milling family (`MillPlants` 106,
`ProcessPlants` 110, `ProcessPlantsVial` 112, `ProcessPlantsBarrel` 113) are
real job types with **no reaction text**. If the extraction did not give them
`production_process` rows with `is_hardcoded = 1`, the walk will confidently
report soap as unreachable, which is wrong. **Check this before trusting any
result**, and report what you found rather than fixing it silently: it is the
other stream's surface.

## Interface

A pure function over a snapshot plus the stored graph, returning a structured
result. **No live calls inside the traversal**: the caller assembles the
snapshot. Same boundary as the cover calculator, same reason.

The result must carry, per the spec's constraints:

- the **named** blocker and the quantity short
- the **path** taken to reach it, so a reader can see why
- for each OR branch not taken, **why** it was not completable
- a `status` on every figure used, so a blocker derived from a `prior` cannot
  be mistaken for one derived from raws
- **never a coordinate.** Landmark names, node ids and counts only. This is
  the project's hardest commitment.

## Cases worth testing

- **The well**, which is the motivating example: blocks, bucket, chain or
  rope, mechanism, with blocks expanding into competing stone and wood routes.
- **A goal that is already satisfied**, returning "nothing blocks this" rather
  than an empty result that reads like a failure.
- **A goal blocked by a missing building** rather than a missing material.
- **A goal with two routes where one is dead and one is live**, asserting the
  walk reports the live one rather than stopping at the first dead branch.
  This is the OR semantics and it is the easiest thing to get wrong.
- **A cycle, if the extraction found one.** The static audit found none in the
  raw reactions and the hardcoded chain appears to be a chain rather than a
  loop, but the traversal must terminate regardless, and a depth or
  visited-set guard is cheaper than trusting the data.
- **Available versus total**: the same fort state with and without a
  job-claimed item must give different answers. If it does not, the deductions
  are not wired in.

## Rules

- No new runtime dependency. No coordinates. No live calls in the traversal.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- Ambient `python -m pytest` is 307 passed / 1 skipped. Report before and
  after.
- If a harness, hook or classifier refuses you, **stop and report it.**
- No em dashes in prose.

## Touched surfaces

`production/**` and this handoff doc. Nothing else.

## Done means

The walk returns a named blocker with its path and quantity for the well case,
the OR semantics test passes, the available-versus-total test passes, the
traversal terminates on adversarial input, and the write-up states which of
the hardcoded processes were present in the extraction and which were missing.
