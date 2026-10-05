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

## Q3. Who should have caught it

- The per-cycle briefing (`conductor/briefing.py::build_briefing`) holds
  vitals, the role's drained diff events and queue ids. **It carries no
  stuck jobs**, although its own docstring says "stuck jobs" are in Tier 0.
  No agent receives `stuckjobs.find` output unless it calls the tool.
- `stuckjobs.find` is on the Architect's and Overseer's allowlists. It is
  NOT on the Quartermaster's, and the Quartermaster is the only role the
  `stuck_job` wake reason wakes (`conductor/policy.yaml`).
- The `stuck_job` wake can never fire: `conductor/cycle.py` sets it only when
  a drained `diff.since` event has type `job_stalled`
  (`EVENT_TYPE_TO_SIGNAL`), and nothing emits that type. Grep of the whole
  repo (excluding tests) finds the string only in that mapping and in docs;
  `scripts/dfhack/df-overseer-diff.lua` emits JOB_COMPLETED, UNIT_DEATH,
  REPORT, announcement_slow and UNIT_ATTACK only. (docs/AGENT-ARCHITECTURE.md
  §4 itself says `job_stalled` was "never an event", to be polled.)
- `stalled_order` cannot see these either: `conductor/order_watch.py` watches
  manager orders (`orders.list`), and there are none (manager_orders is empty
  at tick 250046); the brew jobs were direct `workjob.queue` jobs, the Bed is
  a blueprint building, the digs are designations.
- Did an agent see them and do nothing? No. The last agent run in the queue
  database (`/var/lib/dfmcp/Uniboslan.sqlite3`, records table, read-only) is
  the 2026-10-02 cycle, last record `executed-0005` at 03:58 UTC; that cycle
  itself created the brew jobs (2860, 2861, `executed-0004`) and the bedroom
  Bed (`executed-0005`, a blueprint apply). No agent has run since, and the
  2026-10-05 window was a supervised unpause with no conductor, so no agent
  has yet had a chance to look at them. The Wall (idle 40470 ticks, so
  suspended since about tick 209.6k) predates and was not mentioned in the
  records read (payloads truncated to 420 characters here).

## Q4. Ranked fixes

1. **Second pick (tool gap / fort state).** Two idle-capable miners, one
   pick. The fort has no Forge, no smelter and one iron bar, so a pick
   cannot be made yet. Agent next cycle: can build a Forge only if
   `workshop.build` supports it (not verified) and would still need fuel;
   otherwise nothing an agent can do. Setting `labor.quota` MINE max 1 would
   at least stop idle second-miner churn but fixes nothing.
2. **Bed has no item (agent behaviour, doable now).** No manager order for a
   Bed exists; a Carpenters workshop exists with 27 logs. An agent can
   `orders.create` a bed order (Quartermaster or Overseer, both have it);
   once a BED item exists buildingplan attaches it and the job unsuspends.
   Honours "set intent, let the game execute".
3. **Wall 2705, suspended 40k ticks (tool gap).** Reachable, block attached,
   BUILD_CONSTRUCTION holder (353) idle. suspendmanager is off and no tool
   unsuspends a job (`workjob.cancel` exists; cancel then re-designate is
   the only agent route today, losing the block assignment). Fix: a read-only
   suspend-reason read is the first gap; an `unsuspend`/enable of
   suspendmanager is a code change (new tool, or a policy decision to enable
   the DFHack plugin). Setting: enabling suspendmanager is one command but is
   a game-state write, so needs the user.
4. **Brew job 2861 unclaimed (cause unproven; setting).** 353 is the only
   BREWER and the labour moved off the previous holder 344 (min 1 max 200
   pool 200 gives autolabor freedom to move it). Raising BREWER minimum to
   2 via `labor.quota` (agent can do this now) gives a second holder and
   removes the single-point dependency. Not proven to be the cause: all
   reads say 353 could claim it.
5. **Wake and briefing gaps (code change).** Add stuck jobs to the briefing
   (a bounded `stuckjobs.find` digest by the conductor), give the
   Quartermaster `stuckjobs.find` (it is the role `stuck_job` wakes), and
   replace the dead `job_stalled` event with a conductor-side poll of
   `stuckjobs.find` (the same shape as `order_watch`). Agents cannot do this
   themselves.
6. **Digs 2879 (no action).** Waits behind 2872; resolves itself.
