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

## Result

**Status: done.** Documentation only; no VM, no SSH, no DFHack, no fort, no
code. Branch already contained `bd6bddc` (worktrees here branch from the last
pushed commit, so checked first per the known trap; no merge needed). Read
`CLAUDE.md`, this handoff, `docs/PRODUCTION-MODEL.md`,
`research/2026-09-18-schema-extraction-static.md`,
`research/2026-09-18-schema-extraction-live.md`,
`research/2026-09-18-production-figures.md`, `decisions/DECISIONS.md`'s
2026-09-18 rows (twelve total that date; the six on the production
model/audits are rows for "Production graph designed in full", "Three
consumption semantics, not one" (title now stale, see contradiction below),
"The four-quadrant rule", "Capacity shortage is the diagnosis of last
resort", "Material policy is banded", "An observations table was the
missing piece"; the other six that date are unrelated topics, not this
pass's brief), and `handoffs/2026-09-17-doc-drift-pass.md` for the standard.

**Per file:**
- `docs/TRAPS.md`: added a dated `## Added 2026-09-18` section, all seven
  traps from Deliverable 1, each with its evidence and source.
- `memory/dfhack-environment.md`: added a dated block under "Game-side
  facts" with the six capability facts from Deliverable 2
  (`item.flags.in_job`, `item.flags.owned`/`UNIT_HOLDER`, `grow_counter`,
  `cur_season`/`cur_season_tick`, the tick-conversion confirmation, stockpile
  link fields, `getTileFlags(pos).traffic` via `df.tile_traffic`).
- `docs/AGENT-ARCHITECTURE.md`: added a dated note to §4's Strategy-layer
  bullet pointing at `docs/PRODUCTION-MODEL.md` and stating the design's
  division of labour (code prices the choice set, an agent sets the
  target), framed as sharpening principle 1.
- `docs/MEMORY-ARCHITECTURE.md`: added a paragraph to the doctrine store
  section noting material-policy targets (bands, par levels, cover days,
  reserve floors) as a new class of doctrine entry, same format and
  revision path as before.
- `ROADMAP.md`: added a new top Now item for the production model
  (designed, nothing built, pointer to `docs/PRODUCTION-MODEL.md`),
  pointed the existing "Game figures database and calculators" Next item
  at it, bumped `Last reviewed` to 2026-09-18 with a note, and re-scanned
  the rest of the Now/Next buckets. Nothing else found quietly finished or
  stalled. Left the 19/32/4 tool-count figure in the 2026-09-17 Now item
  untouched (see contradiction below, deliberately not fixed).
- `CLAUDE.md`: added a new top status bullet for the production model
  (designed-not-built, the two figures worth knowing up front: four
  consumption outcomes not three, no job-duration figure found anywhere)
  and bumped the status date to 2026-09-18. Fixed the fort's tick (227008
  to 227160, see contradiction below). Role tool counts left untouched
  (21/34/4), as instructed.

**Contradictions found, and what was done about each:**

1. **`Working.md`'s "In flight" section (lines 94-139) is now stale against
   the audits it itself commissioned, and I could not fix it: `Working.md`
   is explicitly off my touched surfaces.** It says "six tables" (now
   seven, `material_reaction_product` was added as a correction) and
   "Three consumption semantics" (now four, `modified_in_place` for the
   `GLAZE_*` reactions). This is exactly the shape of contradiction the
   brief asked me to hunt for, and I traced it precisely
   (`docs/PRODUCTION-MODEL.md` §4 and §5 are the corrected versions), but
   left the file untouched per this handoff's own rule and flagged it here
   plus with a pointer note in the new `ROADMAP.md` Now item. **Whoever
   owns `Working.md` next should rewrite that section from
   `docs/PRODUCTION-MODEL.md` directly rather than patch the old numbers.**
2. **The fort's tick in `CLAUDE.md` (227008) was stale against two live
   reads from today's live-state audit** (`ReadCurrentTick()` read 227160
   at the start and end of that session's probes, independently corroborated
   by `docs/PRODUCTION-MODEL.md` §3 stating the same figure). Fixed in
   `CLAUDE.md`.
3. **`ROADMAP.md`'s 2026-09-17 Now item states tool counts as 19/32/4,
   while `CLAUDE.md`'s current status block (also dated 2026-09-17, until
   this pass) states 21/34/4** "after the farm-list and stair tools; not
   yet deployed". This predates today's audits, is not one of the four
   things this brief named, and fixing it means touching a tool count,
   which this handoff explicitly forbids in both directions ("a parallel
   stream is adding tools and the orchestrator applies those numbers
   afterwards"). **Left alone on purpose, flagged here for whoever
   reconciles tool counts once that stream lands.**

**The four specific checks the brief named, each run against every file I
read or touched:**
- Three tables / `capacity_theoretical` / three consumption semantics:
  none of my six touched files made either claim before this pass (they
  predate the production model entirely). The one real hit was
  `Working.md` (contradiction 1 above), outside my surfaces.
- Announcement channel useful for counts or short-circuiting diagnosis:
  checked `docs/AGENT-ARCHITECTURE.md`'s wake-events table (§4) and
  `docs/TRAPS.md`; neither makes this claim. `docs/AGENT-ARCHITECTURE.md`
  already correctly scopes `CANCEL_JOB`-style announcements to the real,
  narrow event types it lists; today's audit's finding (unlinked fields,
  pruned buffer) doesn't contradict anything there, it only adds detail,
  now recorded in `docs/TRAPS.md`.
- Wiki container capacities or traffic weights as settled fact rather than
  `prior`, or traffic weights as a hardcoded constant: grepped the whole
  repo for capacity/traffic figures; every hit outside `research/` and
  `decisions/` was in files outside my touched surfaces
  (`research/2026-09-09-reverse-vnc-relay.md` is an unrelated VNC
  bandwidth figure, not a DF container). None of my six files made this
  claim. `memory/dfhack-environment.md`'s new traffic entry states the
  weights are compiled-in and configurable, not a constant, matching
  today's figures pass.
- A job-time figure asserted anywhere: grepped the whole repo for
  `job.?time`/`job_time`; every hit is in `research/2026-09-18-*`,
  `decisions/DECISIONS.md`, or other streams' handoffs, all of which
  already state it as `unavailable`/not found. None of my six files
  asserted one before or after this pass.

**Traps recorded:** the seven listed in Deliverable 1, in `docs/TRAPS.md`'s
new `## Added 2026-09-18` section (forbid-not-forbidden, `unit.counters`
not `counters2`, year-relative `ReadCurrentTick()`, the pruned announcement
buffer, unlinked cancellation fields, the `max_general_orders` discrepancy,
the 42% reagent-inherited material problem).

**Test counts:** ambient `python -m pytest`, run three times across this
pass (baseline, mid-pass, and after the em-dash fix): **306 passed, 1
skipped** every time, unchanged throughout. `.venv-dfmcp/dfmcp/tests` not
run (documentation changes touch nothing that suite reads; the ambient
baseline this pass was actually verified against is the one CLAUDE.md
names).

**Commits, all on this branch, none pushed:**
- `aac6cf2` docs: record production-model audit traps and capability facts
- `19dd3ad` docs: add production-model Now item, point calculators item at it
- `db116ed` docs: refresh CLAUDE.md status block for 2026-09-18
- `f47d1bd` docs: remove em dashes from today's additions, house style
- (this doc's own Result, committed after)

**Not done, deliberately:** no `Working.md`, `decisions/DECISIONS.md`,
`handoffs/INDEX.md`, `doctrine/**`, `production/**`, `scripts/dfhack/**` or
`agents/**` write, per the handoff's rules. No new `decisions/DECISIONS.md`
row is owed by this stream (nothing here is a new decision, only
documentation brought into line with decisions already recorded today by
other streams). No harness or hook refusal encountered.
