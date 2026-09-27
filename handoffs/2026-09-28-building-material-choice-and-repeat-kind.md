# Handoff: building.build honours material flags (non_economic default) and reports whether a kind has already been built for real

Date: 2026-09-28. **Executor, Sonnet, worktree-isolated. Code and tests only. NO deploy, no VM, no live game call.**

## Context

The 2026-09-25 live run (`evals/live/2026-09-25-first-real-conductor-cycle/README.md`)
surfaced two real gaps in `scripts/dfhack/df-overseer-building.lua` / `TOOLS.yaml`'s
`building.build`/`building.find`:

1. **Material blindness.** The tool's own header (line ~74) already says: "a
   filter's own flags (empty, screw, fire_safe, non_economic) are listed but not
   applied, and the result says so." Because of this, the Overseer built the
   fort's first Carpenter's Workshop out of 8 hematite blocks (an economic/ore
   stone) while shale blocks/boulders sat available, because the tool only
   reported counts by item type (BLOCKS/BOULDER/WOOD), never by material, and
   never distinguished economic from ordinary stone. The user caught this live
   and it is not the end of the world here, but it is a real waste the tool
   should prevent by default.
2. **Stale go-ahead gate.** `TOOLS.yaml`'s `building.build` notes say, verbatim:
   "NEVER RUN LIVE for any kind yet: the first real build of a kind this project
   has not built before needs the user's go-ahead." This is static text with no
   live check behind it, so it keeps saying "never" even after a real kind (the
   Carpenter's Workshop) has actually been built. The Overseer read this text and
   correctly refused to build without asking, which was right at the time but is
   now stale for any kind already completed live.

## Fixes

1. **Report and let the caller choose material, generalisable across every
   building-material filter, not special-cased to stone/hematite.** For each
   `building_material`-flagged filter, read each candidate item's material via
   `dfhack.matinfo.decode` and break the stock counts down by material name (not
   just item type). Read whether a material carries the game's own economic flag
   (the filter's own `non_economic` flag on the filter versus the material's own
   flags — read the real DFHack API, do not guess the field name) and **default
   to excluding economic materials from what the build path will actually
   select**, unless the caller explicitly passes an argument to allow them (or
   names a specific material). Report in the result which materials were
   available, which were excluded and why (economic, by default), and which
   material was actually used for the real build. This is the same shape as
   `workjob.queue`'s reagent-choice fix from 2026-09-25 (candidates listed,
   resolved by explicit choice or a safe default, never silently guessed) — read
   that diff in `scripts/dfhack/df-overseer-workjob.lua` for the established
   pattern in this codebase and follow it for consistency in argument style and
   result shape.
2. **Replace the static "never run live" text with a live, per-kind fact.** Add
   a read-only check (bounded: iterate `df.global.world.buildings.all`, filter to
   the requested KIND/subtype, same shape as other bounded reads in this file)
   that reports whether a building of this exact kind has already been completed
   for real by this fort (build stage == max stage), as a field in `build`'s own
   JSON result (e.g. `kind_previously_built: true/false`) and in `find`'s result
   too if that fits its existing shape. Update the `TOOLS.yaml` notes so the
   language is conditional on this fact ("ask the user before the real build of a
   kind not yet built for real; once `kind_previously_built` is true for a kind,
   proceed on your own judgement like any other accepted proposal") rather than a
   blanket "never." Do not remove or weaken any other part of the tool's existing
   safety behaviour (dry-run default, gaps reporting, quickfort validation).

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `scripts/dfhack/df-overseer-building.lua`, its `TOOLS.yaml`
  entries, and their tests. Do NOT touch `dfqueue/`, `dfmcp/queue_tools.py`,
  `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md` (a separate stream
  owns the queue-side duplicate-proposal fix).
- Verify offline only (this repo's existing Lua-logic test pattern with a fake
  world); do not call the live fort. Say plainly what still needs a live check
  after deploy (in particular: the exact economic-material field name and
  whether `dfhack.matinfo` exposes it the way you assumed).
- `python -m pytest` with `lupa` on `PYTHONPATH` (see `CLAUDE.md`'s traps section
  for the exact incantation) before and after; report counts.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after each fix. Do not push. Stop and report on any permission refusal.
- Fill in the Result section: what changed, the real DFHack field names you
  found (or could not confirm) for the economic flag, test counts, what needs a
  live check.

## Result

(pending)
