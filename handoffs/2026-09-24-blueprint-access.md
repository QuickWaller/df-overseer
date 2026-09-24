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

STATUS: done offline. Nothing deployed, no live call, fort untouched.

Built (all in `scripts/dfhack/df-overseer-blueprint.lua`):
- **Orientation.** Four rotations tried in preference order (none, rotcw,
  rot180, rotccw), each with its own site rectangle (swapped for quarter
  turns), the -c cursor moved to the right corner and the cell mapping
  rotated (`orient_cell`, `cursor_for`, `cell_xy`). Flips are never tried (the
  csv carries no mirror permission). The chosen orientation and every
  candidate come back as `site.orientation` and `site.orientations_tried`.
  Orientation, blueprint size and footprint are stored on the site, so later
  phases and status use the same mapping (including the room rectangle).
- **Access gate.** `entrance_analysis`: entrances are the dig sections' own
  carve cells on the footprint edge; reachable means open ground, or touching
  revealed walkable ground outside the rectangle, with every carve cell
  connected to one. Tri-state (false, true, null on a read failure recorded in
  `read_failures`). `entrance_reachable`, `dig_can_start`, `access` are on
  every preview and apply of a dig phase. A real dig that cannot start in any
  orientation is REFUSED (`blocked`, no quickfort call, no handle); a preview
  returns `ok:false` plus `would_strand`. The override is the explicit 8th
  argument `ALLOW_STRANDED=true` only, and the result carries
  `stranded_override_used`.
- **Post-apply proof.** `status` now has `dig` (none_pending, in_progress,
  stalled, unknown) from a bounded job census of dig, carve and smooth jobs in
  the site against pending dig designations, split into with-a-job, blind (no
  walkable neighbour) and startable. Startable-without-job becomes `stalled`
  600 ticks after the recorded apply tick. Top-level `stalled` and
  `stall_remedy`.
- **`release SITE_ID [DRY_RUN]`** (mutating, overseer only, dry run default):
  quickfort undo of each dig phase in the site's orientation; refuses a site
  that is not stalled or has any non-dig phase; forgets the handle when no
  designation remains. Cannot undo tiles already dug or walls already smoothed.
- Manifest: `apply` gains `[ALLOW_STRANDED]`, new `release` command,
  `blueprint.ALLOW_STRANDED` arg text in `dfmcp/tools.py`, `blueprint.release`
  on the overseer allowlist only (status planned, like apply). The overseer's
  granted tool count therefore rises by one once the registry is deployed.

How to release site-1 (needs its own go-ahead, not run): after deploying the
new script, `status site-1` (expect `dig.state: stalled`), `release site-1`
(dry run), then `release site-1 false`. The 5 smoothed north wall tiles cannot
be undone and are harmless. Without the deploy: `quickfort undo
templates/office-room-v1.csv -c X,Y,Z -n /office_room_v1_shell` with the
site's coordinates, unrotated (research doc section 9).

Verified: `tests/test_blueprint_lua_logic.py` has 31 tests (16 old, 15 new)
that run the real Lua in lupa. Negative control: the same 31 tests against
the pre-change script (`git show main:scripts/dfhack/df-overseer-blueprint.lua`,
via `BLUEPRINT_LUA_UNDER_TEST`) give 15 failed, 16 passed, including the
site-1 pattern test (5 visible north tiles, 20 hidden, entrance facing the
hidden side), which the old code applies unrotated with no warning. Ambient
`python -m pytest` 1480 passed, 3 skipped (lupa on PYTHONPATH);
`dfmcp/tests` in `.venv-dfmcp` 652 passed. Read-only ssh source reads of
transform.lua, parse.lua, command.lua and dig.lua on VM 103; nothing else.

Not proven (offline only): real `getWalkableGroup` on unrevealed tiles (the
code requires revealed first), iteration of `df.global.world.jobs.list`, and
quickfort's actual `-t` combined with `-n /label` and with `undo`. For a
non-square template a quarter turn searches a separate rectangle for the
swapped shape, so RANK is not strictly the same candidate across
orientations (the bedroom and office are square).

Live check to run after deploy (each needs its own go-ahead):
1. `plan`, then `preview` the office shell near the Still, ranks 1 to 3:
   expect `orientation` and `orientations_tried`; note whether rank 1 now says
   `entrance_reachable: true`.
2. NEGATIVE CONTROL, dry run first: preview a site with no revealed walkable
   ground touching its ring (or a candidate where only the forced-bad
   orientation is offered). It must report `dig_can_start: false`, `ok: false`,
   `would_strand`. Then `apply ... false` on it without ALLOW_STRANDED must
   return `blocked` with no new handle in `sites`. If either does not refuse,
   stop.
3. `status site-1`: expect `dig.state: stalled`, 10 blind. Then `release
   site-1` dry run, review, real run with go-ahead; expect pending 0 and the
   handle gone.
4. One real apply where preview shows `entrance_reachable: true`; run a tick
   window; `status` must show `in_progress` with jobs. Success is jobs
   existing, never `designations_landed` alone.
