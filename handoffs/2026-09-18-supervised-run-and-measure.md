# Handoff: one supervised run that feeds the fort and settles four unknowns

Date: 2026-09-18. **Do not start this stream until the lever-gap tools stream
(`handoffs/2026-09-18-lever-gap-tools.md`) has finished and been merged**, so
that only one stream is touching VM 103 and the fort at a time.

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §3 (the quadrant rule) and
§11 (time), then this. The fort's current state is in `Working.md` under "Live
fort state, read-only, 2026-09-18".

## Why this stream exists

Two reasons that happen to point the same way.

**The fort needs food.** At tick 227160 it holds **8 raw plants for 15
citizens, zero drink, zero prepared meals**, 60 seeds and 3 logs. Water is
solved: thirst is staggered across three bands, so the `WaterSource` zone is
working. Farm plot 4 exists with plump helmet set for all four seasons and
**25 `PlantSeeds` jobs queued**. Those jobs cannot run while the fort is
paused. The fort's survival path is to let them run.

**Four known unknowns can only be settled by watching the fort move.** They
are listed in `docs/PRODUCTION-MODEL.md` §17 and every one of them blocks
something real. A single supervised run answers all four, which is why this
is one stream and not four.

## The four measurements, in priority order

### 1. The `growdur` unit, which blocks the harvest clock

The most valuable output in the whole production design is "cover is N days,
the crop needs M days, planting no longer fixes this". **M is currently
uncomputable.** Plump helmet's `growdur` reads **300** while live plants carry
`grow_counter` values in the tens of thousands, so the two are not the same
unit, and the candidate conversions give a quarter of a day, two and a half
days, or 250 days.

Method: once a `PlantSeeds` job completes, find the planted crop, and record
`(abs_tick, grow_counter)` pairs at **at least three** separated points during
the run. Two pairs give the rate; the third guards against a non-linear
counter. Report the raw pairs, not just your derived conclusion, so the
arithmetic can be checked. If a crop becomes harvestable during the run,
record the `grow_counter` at that moment: that is the answer outright.

Also settle the direction question: does `grow_counter` count **up** or
**down**? Current evidence (consecutive values on neighbouring plants, wild
plants far above 300) suggests up, but that is inference from a sample.

### 2. A real job duration, with its skill level

`docs/PRODUCTION-MODEL.md` treats job time as unavailable, because it is
absent from the raws, from DFHack's docs and from the wiki. But
`job.completion_timer` is real and counts down on a running job.

Method: when a job starts, read `completion_timer` immediately, then again
shortly after, and record the worker's **skill level in that job's skill**.
The spec is explicit that a duration without a skill index rots, so a reading
without the skill level is worth nothing. `PlantSeeds` is the job you will
have most of; take whatever else the fort runs.

This is a `measured`, `site`-scoped Q2 figure, the first this project will
own. **One reading per job type is enough.** Do not build a sampling loop:
the user ruled that out explicitly and the design is built to not need it.

### 3. Whether job claim state means anything over a running interval

Rung 4 of the diagnostic ladder asks whether a job is claimed and, if not,
what the qualified dwarves are doing. A paused fort cannot answer it: 25
planting jobs sat with 2 claimed, which looks like a labour shortage and is
not evidence of one, because only 151 ticks had elapsed.

Method: record claim counts on the `PlantSeeds` queue at the start, middle and
end of the run. Does autolabor assign more planters as the queue persists?
`autolabor` is **enabled**, so the labour counts (planting on 2 of 15) are its
live allocation rather than a configuration. **Do not call `labor.set-labor`**:
its documented hazard is that writing a labour removes it from autolabor's
management fort-wide and permanently, and this stream is here to observe that
mechanism, not to pre-empt it.

### 4. Whether `item.age` survives, and what the announcement channel does

Two smaller ones from the live audit. `item.age` looked like a reliable
creation clock from one sample; record a few items' ages at both ends of the
run and confirm it advances as expected. And re-read
`world.status.announcements` at both ends: the buffer is known to be pruned
(12 entries out of ids reaching 104), so measure how much a real run adds and
loses, which tells us how often a reader would have to poll to catch a
cancellation.

## Safety envelope

This is the part to get right. The fort is the only one and it is expendable
but not disposable, and a previous run stopped early on a sampler false alarm.

- **10 FPS**, the deliberate setting, not the cap.
- **Supervised throughout.** Do not start the run and go and do something
  else. Sample fort state on a short interval.
- **Stop and re-pause immediately** on any of: a citizen death, a hostile
  detected by `threat.scan`, a breach signal, drink or food reaching zero with
  nothing in progress, or anything you do not understand. Report rather than
  interpret.
- **Bound the run.** Long enough for planting jobs to complete and a crop to
  show movement in `grow_counter`, and no longer. State the tick you started
  at, the tick you stopped at, and why you stopped.
- **Re-pause at the end and verify it**, with `ReadPauseState()` returning
  `true` and a tick read that is stable across two calls.
- **Take a save before unpausing** if DFHack can do so without side effects
  on this install; if you are not certain it is side-effect free, do not, and
  say so. Do not experiment with save mechanics during a live run.

**No writes to the fort in this stream** beyond the unpause itself: no
designations, no new orders, no labour changes, no building. You are here to
let the fort run and to watch it. If the run reveals something that needs a
write, report it and stop.

## Rules

- Read secrets by the key you need: `grep -E '^KEY=' .env`, never `cat .env`.
  Note that `DF_VM_IP` carries a CIDR suffix that must be stripped.
- **Never put a tile coordinate in the report.** Landmark names, building
  ids and counts only.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- If a harness, hook or classifier refuses you, **stop and report it.** Do not
  reword the command to get past it.
- No em dashes in prose.

## Touched surfaces

VM 103 game state (one bounded unpause), a write-up at the bottom of this
file, and `research/2026-09-18-run-measurements.md` for the raw readings.
Nothing else.

## Done means

The fort has planted and is paused again with a verified pause state, the raw
`(abs_tick, grow_counter)` pairs are recorded, at least one job duration is
recorded **with its skill level**, claim counts are recorded at three points,
and your write-up says plainly which of the four unknowns you settled and
which you did not. **A stream that settles two of four and says so is a
success. One that settles four by inference is not.**
