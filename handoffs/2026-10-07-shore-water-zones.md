# Handoff: Water Source and Fishing zones go on the shore, not the water

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User, from play (2026-10-07): a sunken pool's Water Source zone works when
painted on the ground beside the pool on the UPPER level; the wiki Zone page
says the same ("a ground tile next to the water, not over the water
itself"), and its fishing line accepts water one z-level below the zone
tile. `research/2026-10-07-stockpile-logistics.md` section 6. Our
`scripts/dfhack/df-overseer-zone.lua` WaterSource finder
(`is_water_source_tile`, `finder = "water_body"`) only offers wet tiles, and
`FishingArea` has no terrain check. Doctrine entries
`water-source-zone-for-ponds` (refuted, wrongly) and
`water-source-needs-walkable-neighbour` (over-strict) in
`doctrine/seed.yaml` encode the same mistake. See also
`research/2026-09-17-pool-reachability.md` (27 wet tiles at z168 with no
walkable neighbour at that level, ramp tops at z169 above).

## Scope

- The finder for WaterSource and FishingArea returns walkable ground tiles
  adjacent to water: at the water's own level, and on the level directly
  above a sunken pool (a walkable floor or ramp top whose neighbour below
  or beside is water). Per-kind data, one finder shared by both kinds.
  Coordinate-free outputs, as the tool already does. Mark the exact
  adjacency rule (diagonals, z+1) as unverified-live where the sources do
  not settle it.
- `place` for those kinds accepts that ground and no longer requires wet
  tiles; refuse a placement with no water in reach.
- Doctrine: amend both entries with the user's play and the wiki as
  sources, keeping history notes; correct the "refuted" status reasoning.
- TOOLS.yaml notes for the zone kinds updated.
- Tests (lupa fake world): upper-level shore beside a sunken pool offered;
  same-level shore offered; open water itself not offered; a tile with no
  water in reach refused.

## Rules

Touched surfaces: `scripts/dfhack/df-overseer-zone.lua`,
`scripts/dfhack/TOOLS.yaml` (zone section only), `doctrine/seed.yaml` (the
two entries), tests, this handoff. Public repo: no hostnames, IPs or tokens.
No em dashes. No attribution lines. Commit after each milestone. Do not
write Working.md, DECISIONS.md, memory or INDEX.md. Full ambient
`python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp`
green.

## Result

Executor, 2026-10-07, offline, not deployed.

- `scripts/dfhack/df-overseer-zone.lua`: WaterSource and FishingArea share one per-kind-data finder, `finder = "shore"` (the old `water_body` finder is gone). It offers dry, unbuilt, revealed, standable ground (nonzero walkable group, or a RAMP/RAMP_TOP shape, since the group reads 0 for ramps on this build) with water on an offset in `SHORE_OFFSETS`: the four orthogonal neighbours at the same level, and the tile directly below plus the four beside-and-below. Wet tiles are never offered. Diagonals and water two levels down are NOT counted: unverified live, the sources do not settle them (marked in the code, TOOLS.yaml and doctrine). LEVEL is now the level of the ground (a sunken pool is found from the level above). Results keep the old keys (depth_*, stagnant, salt, tile_count, dims, near_landmark) describing the adjacent water, and add `water_same_level`, `water_one_level_below`, `adjacency_rule`. No coordinates. FishingArea lost its "no terrain check" caveat. `place` refuses outright when no ground beside water is in reach; the real path zones the shore tiles through the same blueprint writer as before.
- `scripts/dfhack/TOOLS.yaml` zone section: finder name, shore rule, LEVEL meaning, W H refusal for both kinds, place refusal.
- `doctrine/seed.yaml`: `water-source-zone-for-ponds` stays refuted, but its note now gives the corrected reason (the zone was on the water, not unreachability), with the user's play and the wiki research as sources and the old note kept as history. `water-source-needs-walkable-neighbour` statement rewritten to the shore rule (the level above a sunken pool counts), same sources, original statement kept in the note as history. `python -m doctrine.validate` ok.
- Tests: new `tests/test_zone_shore_lua_logic.py` with `tests/lua_stubs/dfhack_shore_world.lua` (10 tests: upper-level shore over a sunken pool offered, same-level shore offered and the water not, all-water offers nothing, FishingArea shares the finder, no water in reach refused for both kinds, dry-run place, diagonal-only not offered, building/hidden/already-zoned skipped, ramp top standable, W H still refused). One signature pin updated in `tests/test_finder_reservation_skip_lua_logic.py` (`ranked_water_bodies` now takes `k` first).
- Related, left alone: `sunken-basin-recognition` still says "treat as a well case, not a digging case"; a separate claim.
- Deploy target (orchestrator's call): `scripts/dfhack/df-overseer-zone.lua` to VM 103, hash-verified from `git archive` bytes. Live check afterwards: `zone.find` WaterSource and FishingArea near a landmark beside the pool, LEVEL 0 on the upper ground, then a real placement to confirm the game accepts the tiles and whether diagonals matter. No MCP argument schema changed, so no dfmcp redeploy.
- Tests: ambient `python -m pytest` 3214 passed, 3 skipped, 0 failed (lupa installed); `dfmcp/tests` in `.venv-dfmcp` 930 passed.
