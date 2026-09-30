# Handoff: how jobs bind materials (claims without double-promising)

Date: 2026-09-30. **Researcher, Opus, design only.**

## Why

Red team finding F-4 (`research/2026-09-30-goal-tree-red-team.md`) on the
goal-tree design (`research/2026-09-30-goal-tree-design.md` §8): claims
double-grant, because a workshop job queued with only item filters holds no
items until a dwarf starts it, so its logs look free and get promised again;
`buildingplan` (enabled on this fort) attaches items on its own schedule.

The user judged the first fix ("count a job's demand until the game binds
items") and the alternative ("attach exact items at issue, like
buildingplan") both shaky, and asked for a proper design. Read both research
documents' claims sections and F-4 in full first.

## Questions to answer

1. **What control exists, verified from source** (DFHack at `53.16-r1`,
   df-structures, the DF wiki), at three levels:
   - **material choice** for a job (vanilla: workshop job details, manager
     order material): how it is set, what `job_item` fields carry it, what
     DFHack's `workjob`-style job creation can set;
   - **exact items attached at creation** (`dfhack.job.attachJobItem` or
     equivalent; how `buildingplan` does it for buildings): does DF honour
     pre-attached items on a **workshop** job, when does DF itself bind items
     (at posting or when a worker takes the job), what happens if an attached
     item becomes unreachable, forbidden, or is used first by something else;
   - **counting** demand until binding, as the fallback.
2. **The no-armok question, framed for the user's ruling.** A vanilla player
   chooses material, not the exact log, for a workshop job. Is attaching
   exact items a power a player lacks, or finer control of the same action
   (the dwarf still fetches and works)? Compare with `buildingplan`, which
   this fort already uses, and with `docs/ARMOK-RULINGS.md`. Present it as a
   question with both sides; do not decide it.
3. **A claims design** that never double-promises, for each group in the
   design's taxonomy that consumes materials (at least workshop jobs,
   buildings and constructions, manager orders), with the recompute-never-
   tally rule kept, and what stays uncoverable (moods, manager orders, the
   Overseer's direct actions, DF's own consumption).
4. **Who chooses what**: a model chooses at most the material or "any
   non-economic"; code chooses exact items (nearest free unclaimed match?).
   Say what the chooser should optimise and what it must never do (economic
   materials without explicit authority, hidden-tile items).
5. **A live test plan** that settles every unverified point, with the exact
   read-only or reversible steps (for example: attach two specific logs to a
   barrel job while paused, unpause briefly under supervision, read which
   items the job holds). Do not run it; the orchestrator runs it after the
   user's go-ahead.

## Deliver

`research/2026-09-30-item-binding-design.md`, marked verified versus
proposed, with a short answer up front, and this handoff's Result section
(about 200 words plus the decisions the user must make).

## Rules

- Design only: no code changes, no live access.
- First step `git merge --ff-only main`; make an early commit of the
  document's plan, then commit after each section.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Stop and report on any permission refusal.

## Result

(to be filled in by the researcher)
