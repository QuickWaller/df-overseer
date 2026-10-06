# Stuck bed and no beds: read-only diagnosis, 2026-10-07

Fort Uniboslan, paused throughout. Read tools only (stuckjobs, building, workjob, stocks, orders, labor, blueprint, construction audit) plus a read-only open of the queue database. Nothing was designated, queued, cancelled or changed.

## Answer

1. **Why the bed is suspended.** The one "Bed" is not a finished or in-progress bed. It is a planned Bed building (the `bedroom_cell_v1_finish` phase of site-3, applied by the Overseer in executed-0005 on 2026-10-02, "1 building + 1 zone designated") that is waiting for a BED item to be attached. No BED item has ever existed on the fort (BED stock 0 total, 0 in building, 0 in job), so its ConstructBuilding job sits suspended. It will stay suspended indefinitely: nothing in the fort makes a BED item.
2. **Why there are no beds.** Nobody has ever asked for one. The Carpenter's Workshop exists and is usable, wood is on hand, two carpenters are enabled, and the Carpenter's job catalogue includes `ConstructBed`. But no bed work order and no direct bed job was ever created. The only bed-related action in the queue was the blueprint's own bed placement, which creates demand for an item but does not order its manufacture. Later bedroom proposals (0013, 0017) and rulings (0015, 0020, 0021, 0025) all stated the symptom ("BED stock 0, bed is a suspended construction") but concluded that "no unsuspend or bed-supply tool" exists, and deferred.
3. **Least fix.** One direct job: `workjob.queue` of `ConstructBed` (quantity 1) at the Carpenter's Workshop. When the BED item exists, buildingplan should attach it to the waiting Bed building and the suspended ConstructBuilding job becomes runnable. No cancel, no rebuild, no unsuspend needed.

## Evidence

Confidence tags: V = read directly from a live tool this session; I = inferred.

- V. `stuckjobs.find`: the Bed entry is `ConstructBuilding`, `waiting_on: suspended`, `idle_ticks: 38702`. The old Wall is the same state with `idle_ticks: 76052`. Also 10 `MakeBarrel` jobs and 2 Still brew jobs at the Carpenter's/Still, all `no worker assigned` (consistent with a paused game; see below).
- V. `building.find` (kind Bed, near the Bed landmark): `gaps: ["needs 1 of BED, 0 available"]`, `buildingplan_enabled: true`, `stock.BED = {available 0, in_building 0, in_job 0, total 0}`. So the item type the building needs has zero existing items anywhere. `stocks.availability BED` confirms total 0.
- V. Queue database: executed-0005 (2026-10-02) applied `bedroom_cell_v1_finish (meta: zone + bed)` to site-3. `blueprint.sites` shows site-3 `phases_applied: [shell, finish]`. This is the origin of the planned Bed. ruling-0015/0020/0021/0025 cite the suspended bed and BED stock 0; ruling-0021 says "no unsuspend or bed-supply tool". No proposal ever asks for a bed to be made.
- V. Carpenter's Workshop exists (landmark present; jobs sit queued at it; proposal-0006/ruling-0006 sited it 2026-09-25). `workjob.list-jobs` for it returns 45 jobs including `ConstructBed construct bed [WOOD x1, 24 available]` (also a `CustomReaction MAKE WOODEN BED`).
- V. Wood: `stocks.availability WOOD`: 24 available of 27 total (3 in buildings), 1 unreachable, 0 forbidden. Wood is not the blocker.
- V. Labor: `labor.enabled-counts CARPENTER = 2` (HAUL_FURNITURE and HAUL_ITEM 20 each). Not a blocker.
- V. `orders.list`: five orders only (ConstructBlocks, ConstructMechanisms, brew x8, ConstructThrone, MakeBarrel daily), all `active: false`; throne and barrel orders `validated: false`. No bed order. This is also the known manager-order weakness; it is why direct workjobs are the route.
- V. Barrels: executed-0009 (2026-10-06) queued 8 direct MakeBarrel jobs at the Carpenter's, each resolved a WOOD reagent. They are unstaffed now because the fort is paused (inferred from pause, not from a game-speed read this session). The same wood and carpenters will serve a bed job; barrel jobs queued earlier will run first or alongside.
- V. The hint about building 22 (an old Wall holding hematite blocks): the Wall is a separate stuck job, not the Bed. It shows buildingplan/game item choice can attach different items than a tool intended. For the Bed there is nothing to attach at all, so the hematite issue does not apply to it.

## Inferred, not verified

- I. That a buildingplan-planned building with no matching item is exactly what keeps this ConstructBuilding job `suspended`. Strongly supported (the building's own requirement read shows 0 items, buildingplan enabled) but I did not read the job's suspend flag or the planned-building record directly; no read tool exposes it.
- I. That queuing `ConstructBed` will auto-attach the new bed to this building. buildingplan normally does this for the oldest matching planned building, but the Wall case shows items can be chosen unexpectedly. The new bed could also, in principle, be taken by a different planned bed if one existed (none does; building.find shows one).
- I. The made bed's material: the ConstructBed catalogue shows a WOOD reagent. If the fort wants stone or other, that is a separate choice; wood is available.
- Not checked: whether the carpenters' labor is actually idle and unrestricted at the next unpause, any workshop job-material restrictions, or the apostrophe issue in `workjob.queue` for the workshop name (executed-0009 queued by name successfully on 2026-10-06, so it works from at least one role; earlier rejections 0016/0017 cited it, so name handling may be role- or version-dependent).
- Not checked: whether the 1 unreachable WOOD unit or the 3 in-building units matter (they do not change the 24 available).

## Recommended proposal

- **Who:** Quartermaster (filing a `work_order` proposal; it has `workjob.queue`, `workjob.list-jobs` and the stock reads), ruled on by the Overseer. The Architect can file the same if it holds `workjob.queue`.
- **Action:** `workjob.queue` with `workshop_landmark_name: "Carpenter's Workshop"`, job `ConstructBed` (alias for catalogue token `constructbed`), quantity 1 to start (the one waiting Bed building), then more as bedrooms are carved (the five planned shells need five).
- **Preconditions:** Carpenter's Workshop exists and reachable; `stocks.availability WOOD` available >= 1; `building.find kind=Bed` still reports `needs 1 of BED`.
- **Prediction:** `stocks.availability BED` total >= 1 within a few thousand ticks of unpaused play, and `stuckjobs.find` no longer lists the Bed as `suspended`; check `building.find` that the Bed's gap is gone.
- **Order of work:** barrel jobs from executed-0009 may be ahead in the queue; a bed job adds one job at a workshop already holding 8 barrels, so expect it after those unless the queue order is changed.
- **Follow-on for the agents' memory:** a gotcha that "BED stock 0 plus a suspended Bed construction means missing item supply, not a lock; queue ConstructBed", so the Overseer stops deferring bedroom proposals on "no unsuspend tool".
