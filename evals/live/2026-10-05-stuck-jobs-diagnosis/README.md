# 2026-10-05: why the fort's jobs sit unclaimed (read-only)

All reads against VM 103, fort paused throughout. Every read was taken at
tick 250046 (cur_year_tick, year 31, pause_state true); the tick did not
move between reads, so the evidence is one consistent snapshot. Tools:
`scripts/ops/mcpcall.py` (overseer token) for `labor.quota-status`,
`labor.unit-status`, `stuckjobs.find`; read-only `dfhack-run lua` scripts
(job list, unit labours, item and tile reads, plugin state). No writes.

## Q1. Labour

- Autolabor is on (`dfhack-run enable`: autolabor on, suspendmanager OFF,
  buildingplan on). `labor.quota-status`: MINE automatic min 2 max 200,
  enabled 2; BREWER min 1, enabled 1; CARPENTER 2; MASON 2;
  BUILD_CONSTRUCTION 1; haul labours mode "haulers", 17 enabled.
- Who holds the labours (unit labour flags, tick 250046):
  - MINE: unit 192 (digging job 2872) and unit 346 (idle, at a farm plot).
  - BREWER (labour 30): only unit 353, a gem cutter, idle.
  - BUILD_CONSTRUCTION (labour 80): only unit 353 as well.
  - CARPENTER: units 194 and 453, both idle. MASON: 197 and 345, idle.
- 20 of 22 citizens had no job at the read; 1 sleeping, 1 eating, 1 digging,
  1 brewing (unit 344). So the fort is not short of hands: it is short of
  matching labour, tools or items for the specific jobs.

## Q2. Each stuck job (job id, DFHack job list)

| Job | State | Why |
|---|---|---|
| Brew 2860 (Still) | Worker 344, plant and barrel attached, in progress | Not stuck at the read. 344 has labours DRESSING_WOUNDS, MILK, HERBALIST, METAL_CRAFT and not BREWER: it holds the job from before autolabor moved BREWER to 353. |
| Brew 2861 (Still) | No worker, no items | 353 is the only BREWER and idle, all 22 citizens can path to the Still, 9 free empty barrels and 89 free brewable plants exist. Nothing visible prevents the claim. Cause UNPROVEN: see Result. |
| Bed 2862 | Suspended, no items | There are zero BED items in the fort and no manager order exists (manager_orders empty), so nothing will ever make one. buildingplan is on and holds the job suspended until an item attaches. Also a boulder lies on the site tile. |
| Wall 2705 | Suspended 40470 ticks, one BLOCKS item attached (in_job, at z169, site at z167) | Reachable (all 22 can path to an adjacent tile and to the block). suspendmanager is off, so the game's own suspend (set after a failed attempt) is never cleared. Original cause not recoverable read-only. |
| Dig 2874, 2875 | No worker | Reachable, and unit 346 holds MINE and is idle, BUT there is exactly one pick in the fort (item 118, held by 192). 346 cannot dig without one. |
| Dig 2879 | No worker | Not yet reachable: its only open neighbour is the tile job 2872 is still digging. It will free up when 2872 completes. |
