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

Done, offline. All five tasks built in `scripts/dfhack/df-overseer-construction.lua`
and `scripts/dfhack/TOOLS.yaml`; never run against a live fort (no VM access
this stream, per the handoff).

**1. Find the entrance.** `find_entrances` (new, in construction.lua):
generic over zone kind, reuses the shared tri-state reachability helper
(`df-overseer-reachability.lua`'s `group_matches`, reqscript'd, never a new
pathfind) rather than any new path check. A ring tile is the entrance if its
inside neighbour is the zone's own footprint rectangle (structural -- true
for any non-corner ring tile, by `ring_tiles`'s own geometry) and its
outside neighbour belongs to the fort's main walkable group -- read via
`df-overseer-connectivity.lua`'s existing `get_connectivity_report().
main_group_id` (the group most citizens are in), also reqscript'd rather
than re-derived. A ring corner structurally can never qualify (neither of
its two orthogonal neighbours lies inside the footprint) -- see
`ring_edge_neighbours`.

**2. `construction.build` never walls an entrance.** Computes this zone's
entrances before designating anything. Zero entrances among the open ring
tiles refuses the WHOLE call by name ("... has no detectable entrance among
its open ring tiles; refusing to build here, this would seal the room"),
mirroring the exact 2026-09-28 incident (all five ring walls, including the
way out, were designated and four got built). Any found entrance tile is
pulled out of the candidate set before item_present/keeps_access/
reservation ever see it, reported in the existing `held` list with guard
`"entrance"` (named, never silent) -- for every KIND, not just Wall, per
CLAUDE.md's generalisability rule (this guard does not try to know which
construction subtypes block walking and which do not; that would be
per-kind branching in code). New response field `entrances_found`.

**3. A door goes there.** New verb `construction.door ZONE_ID [DRY_RUN]
[RES_ID] [OVERRIDE]`, a sibling of `build`/`mine-vein` in the same file,
**not** a documented `building.build Door` call. Chose this because
`building.build`'s own site search (`ranked_sites`, NEAR_LANDMARK plus a
search radius) answers "find an open area that fits a building" -- the
wrong question for "put a door at THIS exact, already-known entrance tile".
`construction.lua` already owns the exact-ring-tile-targeting machinery
(`apply_single_cell`, the reservation/item_present guards) `build`/
`mine-vein` use; `door` reuses it rather than bending `building.build`'s
tool to a job it was not built for. Resolves the Door kind through
`df-overseer-building.lua`'s own `list_kinds` (never a hard-coded building
number), places one Door at every tile `find_entrances` identifies, never
anywhere else. Refuses the same way `build` does when there is no entrance.
Scope cut stated plainly: MATERIAL_CHOICE is not threaded through for Door
(unlike `build`); buildingplan's own default applies.

**4. Seal check on planned constructions.** New verb `construction.audit
[ZONE_ID] [DRY_RUN]`, the backstop for walls designated before the guard in
task 2 existed -- exactly the 2026-09-28 office walls. For a zone (or every
activity zone if ZONE_ID is omitted), classifies each ring tile as `built`
(shape already WALL), `planned` (a Construction building sits here, not yet
at `bld:getBuildStage() == bld:getMaxBuildStage()` -- the same live-verified
check `df-overseer-building.lua`'s `kind_previously_built` and
`df-overseer-zone.lua`'s `content_row` already use -- the job has not
finished, the tile has not become a wall yet) or `open` (neither). Asks
`find_entrances` whether an entrance would still exist among the open tiles
once every planned tile also finishes (`would_strand`); if not, the planned
tile(s) that would themselves have qualified as the entrance are named in
`at_risk` (building id, never a coordinate -- `df-overseer-stuckjobs.lua`'s
`job_origin`/coordinate-free convention). A real (non-dry) call suspends
the first at-risk building's own job via `job.flags.suspend` -- the exact
hand stopgap used live on building 22, 2026-09-28, now a named tool action
-- found through `dfhack.job.getHolder` over `utils.listpairs(df.global.
world.jobs.list)`, the identical traversal `df-overseer-stuckjobs.lua`'s
`get_stuck_jobs` already confirmed live. Deterministic first-in-ring-order
tie-break, same rule `keeps_access` already established ("hold/suspend just
enough to keep one approach open"). DRY_RUN defaults to true: a bare read
never suspends anything.

**5. Tests, stubs, TOOLS.yaml.** `tests/lua_stubs/dfhack_construction_world.lua`
extended: zone footprint (x1/y1/x2/y2, defaulting to a far-away single cell
so none of the pre-existing tests collide with it), `GROUPS`/`MAIN_GROUP`
plus fake `df-overseer-reachability`/`df-overseer-connectivity` modules, a
`BUILDINGS_AT_TILE` + `JOBS` world for planned-construction/
`job.flags.suspend`, and `add_entrance_fixture`, a one-call helper every
pre-existing `build()` test now uses so the new entrance guard does not
refuse their call. All 25 pre-existing tests updated (their `open_tiles_found`/
`held` counts shift by the fixture's own extra tile) and still pass. Seven
new tests use the **office's own real geometry** from
`evals/live/2026-10-01-queue-and-material-deploy/README.md` ("Month window,
a sealed office"): a literal 3x3 interior, 16-tile ring, with the real
north-side exit tile as the entrance -- proving `build` identifies it and
builds the rest, refuses outright when the whole ring (including the
entrance) is already sealed (the incident itself), refuses when the main
walkable group can't be read, `door` places exactly one Door at the
entrance and refuses with none, and `audit` reports no risk while the
entrance is untouched but finds and suspends the one planned building that
would seal the last exit (dry run first, proving nothing is suspended, then
a real run, proving `job.flags.suspend` fires). 32/32 passing.
`scripts/dfhack/TOOLS.yaml` documents `build`'s new entrance-guard behaviour
and both new commands (`door`, `audit`).

**What the stub cannot prove, stated plainly:** everything here is offline/
lupa-tested against a fake world, never a real DFHack process. In
particular: `dfhack.maps.getWalkableGroup`/`getTileType` (used by
`group_matches`/`resolve_group` in production) are faked away entirely here
(the reachability module itself is faked, not exercised) -- the reachability
helper's own live-verified behaviour is this stream's existing claim, not a
fresh one; this stream only proves construction.lua calls it correctly with
the shape it expects. `dfhack.buildings.findAtTile`/`bld:getBuildStage()`/
`bld:getMaxBuildStage()` are live-verified call sites ELSEWHERE in this
codebase (cited above) but not freshly confirmed by this stream.
`dfhack.job.getHolder`/`job.flags.suspend` similarly cite
`df-overseer-stuckjobs.lua`'s own live confirmation, not a new one. The
`audit` no-ZONE_ID path (iterate every civzone via
`df.building_civzonest:is_instance`) is written to match `find_zone`'s own
real check but is not exercised by any test here (every audit test names
its ZONE_ID explicitly) -- a real multi-zone fort's `audit` call is
therefore the single biggest unverified surface of this stream.

**Role grants (not written here; `agents/*/tools.yaml` is out of scope for
this stream per the handoff's own rule):**
- `construction.door`: overseer only (mutates fort state, matches
  `construction.mine-vein`/`construction.build`'s own existing grant,
  dfmcp/roles.py rule 2).
- `construction.audit`: overseer only. DRY_RUN defaults to true and a
  dry call never mutates, but this repo's allowlist grants by tool id, not
  by argument (stated in TOOLS.yaml) -- the same reasoning already applied
  to `mine-vein`/`build`, both DRY_RUN-default-true and both overseer-only.
  If the orchestrator wants the read usable more broadly (e.g. architect/
  quartermaster, matching `labor.quota-status`'s own precedent), that is a
  judgement call for whoever edits `agents/*/tools.yaml`, not this stream.

**Tests (this stream, offline):**
- Ambient `python -m pytest` (repo root, worktree, `lupa` added to
  `PYTHONPATH` via `pip install --target <scratch dir>` per CLAUDE.md's own
  trap note): **2270 passed, 3 skipped** (CLAUDE.md's own baseline,
  2026-09-25, was 1845/3 -- growth is prior streams' work plus this one's
  32 new construction tests, not a discrepancy).
- `dfmcp/tests` run with the **main checkout's** `.venv-dfmcp` interpreter
  against this worktree's files (`.venv-dfmcp/Scripts/python.exe -m pytest
  dfmcp/tests -q`, run from the worktree so it exercises the worktree's own
  `TOOLS.yaml`): **722 passed** -- confirms `dfmcp/registry.py` parses the
  two new TOOLS.yaml entries without error.
- `tests/test_construction_lua_logic.py` alone: **32 passed** (25
  pre-existing + 7 new).

**The live test that would confirm this** (for the orchestrator, after
merge, with VM access -- none of this was run here):
1. On Uniboslan, pick (or re-create) a zone shaped like the office, with its
   ring still fully open (nothing designated yet). Run
   `construction.build ZONE_ID Wall` (DRY_RUN true first). Confirm
   `entrances_found` is exactly 1 and matches the tile a human would call
   the room's own doorway, and that tile appears in `held` with guard
   `entrance`, not in `results`.
2. Run `construction.door ZONE_ID` (DRY_RUN true, then false) and confirm a
   real Door building appears at that exact tile afterward (`dfhack.
   buildings.findAtTile` or the game's own UI), nowhere else on the ring.
3. The direct regression test: re-stage the 2026-09-28 scenario (a ring with
   every tile but the entrance already built) and confirm
   `construction.build ZONE_ID Wall` now refuses the whole call instead of
   walling the last tile.
4. Run `construction.audit` (DRY_RUN true) over a zone with a still-pending
   ring construction job sitting on what `find_entrances` would call the
   entrance; confirm `would_strand` is true and `at_risk` names that
   building. Then DRY_RUN false and confirm the job shows suspended in-game
   (DFHack's own job list, or the building's own UI) -- the thing the
   2026-09-28 hand stopgap did manually, now exercised as a real tool call
   for the first time.
