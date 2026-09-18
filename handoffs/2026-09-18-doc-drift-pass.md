# Handoff: doc drift pass after the production-model design and two audits

Date: 2026-09-18. Stream 4, dispatched alongside three build streams.
Documentation only. **No VM, no SSH, no DFHack, no fort, no code.**

## Why this stream exists

A large design pass plus two feasibility audits landed today and the standing
docs have not caught up. Several files now state things the audits disproved,
and a set of real, dated facts have nowhere to live. This is the same shape as
`handoffs/2026-09-17-doc-drift-pass.md`, which is worth reading first for the
standard this pass is held to: it caught a real contradiction rather than
just refreshing prose.

Read in this order before editing anything: `CLAUDE.md`,
`docs/PRODUCTION-MODEL.md` (today's spec, authoritative),
`research/2026-09-18-schema-extraction-static.md`,
`research/2026-09-18-schema-extraction-live.md`,
`research/2026-09-18-production-figures.md`, and
`decisions/DECISIONS.md`'s six rows dated 2026-09-18.

## Deliverable 1: new `docs/TRAPS.md` entries

These are verified facts from today's audits that will bite whoever writes the
next tool. Each needs a dated entry with its evidence:

- **`item.flags.forbid`, not `forbidden`.** Guessing the obvious name errors
  outright. 218 of 1325 items on Uniboslan carry it.
- **Unconsciousness lives in `unit.counters`, not `counters2`.** `counters2`
  holds the timers (hunger, thirst, sleepiness). There is no single "injured"
  bitflag: a caller has to build that test from several `counters` fields or a
  wound count.
- **`dfhack.world.ReadCurrentTick()` is year-relative.** It returns
  `cur_year_tick`, which resets each spring, so any key or rate built on the
  bare tick silently corrupts across a year boundary. Absolute time is
  `cur_year * 403200 + cur_year_tick`.
- **The announcement buffer is pruned, not a log.** 12 entries survived out of
  ids running to 104. An infrequent reader misses events permanently.
- **Cancellation announcements carry no linkage fields.** `speaker_id`,
  `activity_id` and `activity_event_id` were all `-1` on a real `CANCEL_JOB`
  entry, so the message cannot be joined to a job or unit, only parsed as
  text. A cancelled job itself is removed from `world.jobs.list` entirely and
  leaves nothing structural behind.
- **`building.profile.max_general_orders` read 5 on this install**, not the
  wiki's widely-repeated 10. One incomplete sample, so record it as a
  discrepancy to re-check rather than as a settled figure.
- **42% of reaction product lines inherit their material from a reagent**
  (`GET_MATERIAL_FROM_REAGENT`), so a concrete item id cannot be read off a
  reaction line alone. Anyone parsing raws for a specific output needs the
  material-side join.

## Deliverable 2: `memory/dfhack-environment.md`

Fold in the live-read facts worth keeping as capability knowledge, with their
provenance: `item.flags.in_job` as the exact job-claim signal (no job scan
needed), `item.flags.owned` plus `UNIT_HOLDER` for dwarf ownership,
`grow_counter` on live plant instances, `df.global.cur_season`, the
1,200 / 33,600 / 403,200 tick conversions confirmed against announcement
timestamps, stockpile give/take link fields, and
`dfhack.maps.getTileFlags(pos).traffic` decoded via `df.tile_traffic`.

Keep the file's own scope rule in mind: it is about what works on this
install, not about the production design.

## Deliverable 3: the standing docs that are now wrong or incomplete

- **`ROADMAP.md`**: the production model belongs in the Now bucket with a
  pointer to `docs/PRODUCTION-MODEL.md`. Bump `**Last reviewed:**`, and
  actually re-scan for anything quietly finished or stalled rather than only
  adding a line.
- **`docs/AGENT-ARCHITECTURE.md`**: it discusses calculators as tools and the
  strategy layer without knowing the production model exists. Add a reference
  and, in particular, record the design's own division of labour, that code
  produces the priced choice set while an agent supplies judgement about
  targets, since that sharpens principle 1 rather than restating it.
- **`docs/MEMORY-ARCHITECTURE.md`**: the doctrine store section should note
  that material policy targets (par levels, cover days, reserve floors, band
  classification) now live in doctrine by design, which is a new class of
  entry for that store.
- **`CLAUDE.md`**: refresh the status block. **Do not change the role tool
  counts** (currently 21/34/4): a parallel stream is adding tools and the
  orchestrator will apply those numbers. Say what is true today and note the
  production model as designed-not-built.

## What this pass must do beyond refreshing prose

**Hunt for contradictions and report them rather than silently patching.**
The 2026-09-17 pass earned its keep by finding two files repeating a figure
the register had already corrected. Specific things to check today:

- Any file still describing the production model as three tables, or
  mentioning `capacity_theoretical`, or claiming three consumption semantics.
- Any file claiming the announcement channel is useful for counts or for
  short-circuiting diagnosis.
- Any file that treats wiki container capacities or traffic weights as
  settled facts rather than `prior`, or treats the traffic weights as a
  constant when they are a configurable default.
- Whether anything asserts a job-time figure anywhere, which three
  independent passes have now failed to find.

If docs and repo state disagree in a way you cannot resolve from the sources
above, **flag it in your write-up and leave it alone.** Do not guess.

## Rules

- Do **not** write `Working.md`, `decisions/DECISIONS.md`,
  `handoffs/INDEX.md`, `doctrine/**`, `production/**`, `scripts/dfhack/**`,
  or `agents/**`. Four streams are running in parallel and those belong to
  others or to the orchestrator.
- `doctrine/seed.yaml` is game knowledge and never a repo decision. It is also
  another stream's surface today. Leave it.
- Ambient `python -m pytest` is 306 passed / 1 skipped. Documentation should
  not move it; report before and after anyway.
- No em dashes in prose. Commas, colons or full stops.
- If a harness, hook or classifier refuses you, stop and report it.

## Touched surfaces

`docs/TRAPS.md`, `docs/AGENT-ARCHITECTURE.md`, `docs/MEMORY-ARCHITECTURE.md`,
`ROADMAP.md`, `CLAUDE.md`, `memory/dfhack-environment.md`, this handoff doc.

## Done means

The new traps are recorded with evidence, the memory file carries the new
capability facts, the standing docs no longer contradict today's findings, and
your write-up at the bottom of this file lists every contradiction you found,
including any you deliberately left alone.
