# Handoff: how df-ai plans a fort, and what we can learn from it

Date: 2026-09-24. **Researcher. Read-only. No VM, no fort.**

Read `CLAUDE.md` first, then `research/2026-09-24-room-layout-best-practices.md`
and `research/2026-09-24-burrow-district-designs.md` (do not repeat them), and
the 2026-09-24 "ranking system" row in `decisions/DECISIONS.md`.

## Why

A design session is owed on **districting** (areas of the fort designated for
production, living, tombs and so on) together with the openclaw agent
architecture. Today every placement is ranked on its own against a landmark
(`ranked_rects` in `scripts/dfhack/df-overseer-zone.lua`), and that is judged
too rickety to patch. **df-ai** (github.com/BenLubar/df-ai, a DFHack plugin
that plays a whole fort unattended) plans its layout up front and is the
closest prior art that exists. No research pass here has read it.

## The questions

1. **The plan as data.** What is the schema of a room template and a plan
   (`rooms/templates/`, `rooms/instances/`, and the blueprint/plan code)?
   Fields for shape, furniture, exits, counts, constraints, variants. Quote
   real files with paths and commit.
2. **Fitting a plan to terrain.** This is the most important question. How
   does it choose where the plan goes and adapt it to what it finds (aquifer,
   caverns, magma, ore, the surface, a map edge)? Search, fallback, variant
   choice, or giving up? What does it do when a room will not fit?
3. **Districts or relationships.** Does it encode "this kind of room belongs
   near that kind" (adjacency, floor bands, a central stair) explicitly, or is
   it implicit in one fixed layout? How are workshops matched to stockpiles?
4. **Growth.** How does the plan grow with population (more bedrooms, a second
   dining hall, new industries), and what triggers that?
5. **Execution.** The task pipeline from plan to dug, built, furnished and
   assigned room; how it checks a room is done; how it recovers a failed step.
6. **Known failures.** From issues, commit messages and any stream or forum
   write-ups: what went wrong in real unattended play, especially layout
   failures. This and question 2 are worth most.
7. **Currency.** Which DF and DFHack versions it supports, when it was last
   meaningfully updated, whether it runs on v50+/53.x Classic at all.

## What to produce

`research/2026-09-24-df-ai-fort-planner.md`: a verdict paragraph first, then
the answers, then a short section **"What transfers to df-overseer"** that is
honest about the difference: df-ai is hand-coded logic, we have models that
must reason about space **without ever being shown a map** (`docs/PURPOSE.md`
commitment 1). Say which of its ideas survive that constraint and which do
not. Also a "What could not be verified" section.

Mark each claim with how you know it: read in source (path, commit), read in
docs, or forum/second-hand. Short quotes only, no large source blocks.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- You own that research file and this doc's Result section only. Not
  `Working.md`, `decisions/`, `memory/`, `doctrine/`, `handoffs/INDEX.md`.
- Never render or reconstruct a map or grid in the output.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit after each milestone (a drafted section is a milestone).
- Stop and report on any permission or classifier refusal.

## Done means

All seven questions answered or declared unanswerable with what was tried,
sources marked, and the transfer section written.

## Result
