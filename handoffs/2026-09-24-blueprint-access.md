# Handoff: a blueprint's designations can be blind, and nothing says so

Date: 2026-09-24. **Offline build. No deploy, no VM mutation, no fort change.**
A live redeploy and re-attempt need their own go-ahead.

Read `CLAUDE.md`, `evals/live/2026-09-24-office-build/README.md` (the live
failure, with a per-cell read and job census), `scripts/dfhack/df-overseer-blueprint.lua`,
`research/2026-09-24-quickfort-hands.md`, `blueprints/templates/office-room-v1.*`.

## The failure

The first real apply (`site-1`, office template, near a stockpile) got 15
designations. The 5 visible north-ring tiles were smoothed. The other 10
(interior and the south entrance gap) sat in hidden solid rock with no walkable
neighbour, so DF never made a dig job for them, ever. The template's only
opening faces south into unrevealed rock while the reachable side was north.
`preview` warned only via `interior_fully_revealed: false`; `status` reported
pending designations with no hint that none had a job.

## What to build

1. **Orientation.** Quickfort has a transform module (`hack/scripts/internal/quickfort/transform.lua`;
   read it, and the `quickfort run` transform argument, from the installed
   source over ssh with `cat -n`). Let the verb choose among the four rotations
   (and flips only if the template allows) so the entrance tile is adjacent to
   a revealed walkable tile, and report which orientation it chose. Templates
   stay generic: no per-room code. A site where no orientation gives a reachable
   entrance must be reported, not applied.
2. **Preview must say whether the dig can start.** Add a field per candidate
   such as `entrance_reachable` (entrance tile adjacent to revealed walkable
   ground) and refuse a real `apply` of a dig phase that would leave interior
   cells unreachable, unless an explicit override is given. Coordinate-free.
3. **`status` must flag a stall**: pending dig designations with no job and no
   walkable neighbour, distinct from "in progress". Use the read_failures
   pattern; three states, never a bare default.
4. **Cleanup of the stalled site.** Work out, from quickfort's source, how to
   withdraw designations that never got a job (site-1 holds 10 blind dig
   designations and 5 smoothed north wall tiles; the fort is paused and must
   stay so). Offer a `release` verb or document the quickfort route, and say
   what it can and cannot undo. Do not run it live.
5. Tests: extend `tests/test_blueprint_lua_logic.py` for a fake world where the
   south side is hidden and the north is open (orientation must flip; a fully
   hidden site must be refused), and a stalled-status case.

## Scope

Yours: `scripts/dfhack/df-overseer-blueprint.lua`, `scripts/dfhack/TOOLS.yaml`,
`dfmcp/tools.py`, the two allowlists only if a new verb is added (a mutating
verb goes to the overseer only, `dfmcp/roles.py` rule 2), the blueprint tests
and `research/2026-09-24-quickfort-hands.md` (append). Not yours: everything
else, and per `handoffs/` rule `Working.md`, `decisions/DECISIONS.md`,
`memory/`, `handoffs/INDEX.md`.

## Rules

`git merge --ff-only main` first. Baselines: ambient **1449 passed, 4 skipped**,
`dfmcp/tests` in `.venv-dfmcp` **652 passed**; lupa on PYTHONPATH from a scratch
install for the Lua tests. Commit as you go. Bounded reads only, no live fort
changes (read-only ssh source reads are fine). No em dashes. No attribution
lines in commits. Stop on any refusal; never route around one.

## Done means

A preview says, per candidate, which orientation works and whether the dig can
start; a real apply cannot silently strand designations; `status` names a
stall; the Result states how to release site-1. Verify the verification: show
the new tests fail on the old behaviour.

## Result

(to be filled by the executor)
