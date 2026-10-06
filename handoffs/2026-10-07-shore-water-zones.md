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

(executor fills this in, with deploy targets)
