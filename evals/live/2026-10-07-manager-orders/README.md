# Why manager work orders never run, 2026-10-07 (read-only diagnosis, live Uniboslan)

Fort stayed paused. Nothing was created, changed, cancelled, validated, assigned or unpaused.
All live reads were `dfhack-run` Lua and the existing `df-overseer-nobles requirements` read.

## Verdict (honest)

No single cause is proven. What is verified: the manager has **never done the manager's job**, and
**two defects on our side make a normal player order differ from ours**. What is inferred: which of
the two actually stops `validated` going to `active`.

1. **Verified: the manager has never validated anything.** Unit 345 holds MANAGER, owns Office zone 13
   (a complete chair inside, reachable from the manager and all 24 citizens by walk check), and has no
   job, but his skill list has **no ORGANIZATION skill at all**. Per the wiki mirror (page "Manager",
   section Office) the manager gains organizer experience "when validating the order, not when the order
   is finished". Zero experience means no `ManageWorkOrders` (job type 195) job has ever completed for him.
   No job of that type exists now (the whole job list is 6 jobs: PlantSeeds, Sleep, ConstructBuilding).
2. **Verified: orders 0-2 read `validated=true` without him.** Orders 3 and 4 (created later) are
   `validated=false`. So the true flags on 0-2 did not come from the manager doing paperwork. Inferred:
   they were validated at creation (wiki "Disadvantages": validation is only required once a fort reaches
   20 citizens, and orders 0-2 predate that on the fort's history); not independently proven.
3. **Verified: ours differ from a player's order in material.** Every order has `mat_type -1`,
   `mat_index -1`, empty `material_category` (exact reads below). That is the "Make unknown material ..."
   the user sees. DFHack's own shipped order library (`hack/data/orders/*.json`) sets `"material":
   "INORGANIC"` on its ConstructBlocks, ConstructMechanisms and ConstructThrone orders, and reaction
   orders (BREW_DRINK_FROM_PLANT) carry no material, so for the brew order -1/-1 is normal and
   material cannot be its cause. Whether -1/-1 stops the game creating jobs for the item orders is
   **not verified** (the direct barrel jobs also display "unknown material" and did complete, but direct
   jobs carry their own job_items; manager orders build theirs from the order's material).
4. **Ruled out** (live reads): workshop profile refusals. All four workshops (Still 4, Masons 5,
   Mechanics 6, Carpenters 17) are complete (stage 3/3), have 0 jobs, `permitted_workers` empty,
   `min_level 0`, `max_level 3000`, `max_general_orders 5`, `block_general_orders false`,
   `blocked_labors` 0 of 94. v50 has no profile work-order restriction beyond "general orders allowed"
   (wiki: Workshop Profiles removed). `max_workshops 0` is "unlimited" in the tool's own contract and in
   DFHack's order import; not a block. Stocks are fine (20 free boulders, 27 barrels). Path to the office
   is fine. Manager is not in a squad, not inactive.
5. **Not ruled out**: the room-value check. `df-overseer-nobles requirements MANAGER` still says Office
   `cannot_tell` (getRoomDescription empty). The wiki says the Nobles screen's Study icon must be green for
   the manager to work; the user can read that icon, the tool cannot. Also the manager is a mother who
   gave birth this run (report 500), and has MASON and STONE_CRAFT labors on, so he may be eligible for
   labor jobs competing with paperwork. Neither is shown to matter.

## Exact reads

Orders (`world.manager_orders.all`; next id 5):

| id | job | freq | left/total | validated | active | workshop_id | max_workshops | mat_type/idx | material_category | item_conditions |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | ConstructBlocks | OneTime | 1/1 | true | false | -1 | 0 | -1/-1 | none | 0 |
| 1 | ConstructMechanisms | OneTime | 1/1 | true | false | -1 | 0 | -1/-1 | none | 0 |
| 2 | CustomReaction BREW_DRINK_FROM_PLANT | OneTime | 8/8 | true | false | -1 | 0 | -1/-1 | none | 0 |
| 3 | ConstructThrone | OneTime | 1/1 | false | false | -1 | 0 | -1/-1 | none | 0 |
| 4 | MakeBarrel | Daily | 2/2 | false | false | -1 | 0 | -1/-1 | none | 1 (compare 1, value 20, item_type 17) |

Item_type and item_subtype -1 on all. Manager: unit 345, holds MANAGER (entity 36, assignment 6), no job,
standing at z 169, office zone 13 at z 167 holds Chair 12 (complete); path exists.

## Tool comparison (`scripts/dfhack/df-overseer-orders.lua`, `create_order`)

The tool calls DFHack's own `workorder.preprocess_orders`, `fillin_defaults`, `create_orders` (lines
716-717), so struct construction is the same as `orders import`. It sets only what the caller passes:
`material` only if given (lines 626-632), `material_category` only if given (634-641), `workshop_id`
(643-652), `max_workshops` (654-660), conditions (662-678). It never defaults a material for item jobs,
so an agent that omits MATERIAL queues exactly the -1/-1 order seen above. It never writes `validated`
or `active` (only `recheck`, line 900, clears `validated`). `create_orders` leaves status bits false, so
validation is left entirely to the game.

## Is gotcha-0002 wrong?

Partly. "Manager route stuck (validated=true, active=false)" is a true observation, but it is not the
whole story: two of five orders are not validated at all, and the manager has never validated anything.
It should not read as "validation works, dispatch fails". The code comment at the tool's line 298
("the failure is a missing announcement, not a missing state") is also unsupported.

## Least fix, in order

Player side (no code): open the Nobles screen and read the manager's Study icon. If red, fix the office
(more furniture or value) and see whether a `ManageWorkOrders` job appears; the user already reported
seeing orders validated in the UI, so check which orders. Then untick MASON and STONE_CRAFT on the manager.

Tool side (small): require or default MATERIAL for item-job orders (INORGANIC for stone items, as DFHack's
library does) and give `orders.list` a `material_unknown` warning when mat is -1/-1 on a non-reaction job.
Cheapest experiment once unpaused and approved: queue one new ConstructBlocks order with MATERIAL
INORGANIC and see whether it activates while order 0 stays stuck; that separates material from validation.

## Not verified

Why order 3 and 4 are never picked up for validation (no `ManageWorkOrders` job ever seen); whether
-1/-1 stops activation; whether 0-2 were validated at creation. Source for DF's job-assignment logic is
closed; only wiki text and DFHack data files were read.
