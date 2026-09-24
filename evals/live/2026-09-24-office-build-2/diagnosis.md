# Diagnosis: site-2 "stalled" dig (read-only, fort paused at abs_tick 12614468)

Frame: applied grid, rows 0..4 top to bottom, cols 0..4, ring outside = -1 and 5.
Orientation rot180, so the template's entrance gap (bottom row, middle) is the
TOP row, middle cell (row 0, col 2). Reads were per cell via DFHack scripts run
over vm-ssh.sh; the site tile was resolved in-script, no coordinate printed.

## Findings

1. The stall is a false positive of the status classifier, not an access mismatch.
   The entrance gap (row 0, col 2) is NOT pending because it already has a real,
   unclaimed Dig job (job id 2275, no worker, flags: dessource only). Once DF
   makes a job the tile's designation flag reads dig=No, so `dig_progress`
   (flags.dig ~= No) no longer counts it. The 9 pending designations are exactly
   the 3x3 interior (rows 1-3, cols 1-3), all dig=Default, all hidden STONE/MINERAL
   wall, none touching walkable ground until the gap is dug. So blind==pending is
   TRUE and expected, and the classifier concluded "stalled".
2. Cell reads. Top ring row (row 0): cols 0-3 revealed smoothed wall (finished,
   from site-1's earlier SmoothWall work on the same footprint: already_finished 4
   plus the gap cell is also a revealed smoothed wall), col 4 revealed StonePillar.
   Gap cell: revealed, smoothed WALL, dig=No, has the Dig job. All other 20 ring
   and 4 side cells: hidden solid wall, dig=No (smoothing not designated, hidden
   cells cannot be smoothed until revealed). No buildings, units, liquid or flow
   on any of the 49 read tiles.
3. The tile immediately outside the gap (row -1, col 2) is revealed MineralFloor,
   walkable group 3478, the same group as all 22 citizens. Also revealed floor,
   same group: row -1 cols -1..3. Row -1 col 4 is a revealed wall. Not water,
   not a ramp, not a different group.
4. DF makes a dig job only for a designated tile with a reachable adjacent tile.
   Gap: orthogonal neighbour outside is reachable floor, so it got a job. Interior:
   no walkable neighbour until the gap is dug, so no job yet (correct DF
   behaviour, and the gate's plan-aware connectivity through carve cells models
   exactly this). No condition of the gate differs from DF here.
5. Gap is `d` in the rotated blueprint at the cell the gate analysed (row 0, col 2):
   the Dig job sits at that cell. Rotation mapping is right.

## Kea
Alive BIRD_KEA: one, 6 z-levels ABOVE the site, 2 cols/4 rows off in plan. Five
other kea are dead/inactive. Not on the site's level, so not standing on it. The
advisory's "3 tiles N of the Still" is plan distance only (the Still is 1 level
above the site).

## Open, could not determine
- WHEN job 2275 was created. Job ids 2273-2276 are sleep/eat jobs: it is fresh.
  The job may be new, not neglected.
- Why it is unclaimed: dwarves are asleep. Only ONE pick exists in the fort,
  held by miner 192 (asleep, skill 5). Miners 196, 346, 353 have no pick and
  skill 0-1. Weak candidate for a later real stall if the pick holder is slow.
- The status verb cannot see a gap job: needs a live run past sleep to confirm
  the gap gets dug and the interior then gets jobs (not done, read-only).

## Code the evidence contradicts
scripts/dfhack/df-overseer-blueprint.lua, dig_progress(): counting "pending" only
where `flags.dig ~= df.tile_dig_designation.No` (around the `elseif flags.dig`
branch) assumes a designation stays flagged until dug, and `state = "stalled"`
when `blind == pending`. Both are wrong once a tile has a job (flag cleared).
dig_jobs_in_site() already finds the gap's job; dig_progress ignores jobs on
tiles with dig=No. Fix idea: count jobs in the census (with_job from `jobs`
size) and do not call it stalled while any Dig job exists in the site.
