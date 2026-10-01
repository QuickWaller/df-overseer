# Handoff: a room's entrance gets a door, and no construction seals anyone in

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

Live incident, 2026-10-01 (`evals/live/2026-10-01-queue-and-material-deploy/README.md`,
"Month window, a sealed office"; register row of that date): ring walls
`construction.build` designated around the office on 2026-09-28 walled the
room's way out and trapped the Manager and a miner. The user: "that wall
didn't even make sense to put, may as well have put a door." `keeps_access`
(`df-overseer-construction.lua`) now refuses new walls that cut off
unmined ore, but it does not know a room's entrance, and walls designated
before it existed were never re-checked.

## Tasks, in order (commit after each)

1. **Find the entrance.** For a zone's ring, an entrance is a ring tile
   whose outside neighbour is in the same walkable group as the fort's
   main area (the group most citizens are in) and whose inside neighbour
   is the room's interior. Generic over zone kind. Reuse the shared
   reachability helper rather than a new path check. The live diagnosis in
   the eval README shows the reads that found it by hand.
2. **`construction.build` never walls an entrance.** It reports the
   entrance tiles and skips them (a named skip, never silent). A room with
   no entrance at all is refused with a named reason.
3. **A door goes there.** A way for the overseer to place a door on the
   entrance: either a `door` kind in `construction.build` that targets only
   entrance tiles, or a documented call to `building.build Door` at that
   tile. Choose the one that fits the existing code and generalises to any
   room; say why.
4. **Seal check on planned constructions.** A read command (for example
   `construction.audit [ZONE_ID]`) listing every planned, not yet built
   construction that would, once built, leave any citizen or any room
   interior without a walkable path to the main area, and a mutating,
   `DRY_RUN`-default-true way to suspend those (the hand stopgap used on
   building 22 on 2026-09-28 was `job.flags.suspend`). This is the backstop
   for walls designated before the guard existed.
5. `TOOLS.yaml` entries and lupa tests, including the office's real
   geometry from the eval as a fixture (3x3 interior, the north ring walls
   as the way out). Say plainly what the stub cannot prove.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then
  after each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `agents/*/tools.yaml` (say which role gets which command; only the
  overseer may hold a mutating one).
- No em dashes in prose. No attribution lines in any commit. No armok
  capabilities; never read hidden tiles.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-construction.lua`, `scripts/dfhack/TOOLS.yaml`,
tests and stubs (read-only use of the reachability helper and building.lua).

## Result

(fill in, and the live test that would confirm it)
