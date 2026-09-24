# Manager acceptance check, 2026-09-24 (live, Uniboslan)

Result: **no manager order dispatched.** 2793 ticks run (12637400 -> 12640193), budget 3000.
No job with a populated `order_id` appeared at any poll; orders 0-3 read identically before and after.
Fort left PAUSED. No change to orders, labor, zones, owners, buildings or the Manager's appointment.
`clock clear` was NOT needed (resume was accepted with the ghost latch not showing in status).

## Step 0
Peek: paused, abs_tick 12637400, 22 alive, 1 dead, hunger/thirst fine.
Quicksave: `df-overseer-fort quicksave` issued (prior save_dir `autosave 3`); confirmed by the
confirm call reading `cur_savegame.save_dir`: slot `autosave 1`, confirmed true (not mtime).

Before: orders (`orders list`, plus raw read in ordscan.lua): 0 ConstructBlocks, 1 ConstructMechanisms,
2 CustomReaction BREW_DRINK_FROM_PLANT (8 of 8 left) all validated true, active false, left = total,
finished -1, no item or order conditions, workshop_id -1 (any workshop), max_workshops 0;
3 ConstructThrone validated FALSE, active false. Manager Tun Konosamem (unit 345): stress category 0,
no job. Stress counts (cats 0..6) 2 2 4 8 2 3 1; cat0 = units 345 and 455. Pick item 118 held by 192.
Stocks (stock.lua, bounded, none forbidden, none in a job): boulders 10, blocks 4, mechanisms 1,
barrels 15, plants 124, drink 0. Workshops: Still (4), Masons (5), Mechanics (6), all complete, no jobs.
Labors enabled (count of dwarves): MASON 2, BREWER 1, MECHANIC 1, CARPENTER 2, STONE_CRAFT 2.
Job census at start: Sleep x6 only.

## Slices (mrun.sh: resume, poll ~1 s, auto re-pause on any alert or order event; stop rules per the brief)
| Slice | End tick | Stress cats | Orders | order_id jobs | Job census / Manager |
|---|---|---|---|---|---|
| 1 | 12637923 | 2 2 4 8 2 3 1 | unchanged | none | Sleep x4; 345 no job |
| 2 | 12638249 | same | unchanged | none | Sleep x2 |
| 3 | 12638577 | same | unchanged | none | Sleep x1 |
| 4 | 12638685 (self-paused) | same | unchanged | none | Sleep x1 |
| 5 | 12639124 | same | unchanged | none | no jobs at all |
| 6 | 12639447 | same | unchanged | none | Eat x1 (345 eating) |
| 7 | 12639772 | same | unchanged | none | Eat x1 (345 eating) |
| 8 | 12640193 (self-paused) | same | unchanged | none | no jobs at all |
Every poll: 22 alive, 1 dead, pick 118 OK with unit 192, cat0 only 345 and 455, no bad or manager/mandate/order
report text (max report id stayed 411), kea never on a dwarf's level (KEASAMEZ 999), no new tripwire/advisory.

## The two self-pauses (unexplained, flagged)
The fort was paused by something other than my loop at 12638685 (about 108 ticks after resume) and at
12640193 (about 120 ticks after resume in slice 8, which had run ~1200 ticks first). Both times: clock status
showed no tripwire and no advisory, no new report or announcement, no popup, focus dwarfmode/Default, stress,
vitals and pick unchanged. Cause not identified. I resumed after the first as a bounded, authorised
action with all checks clean; at the second I stopped because the budget was spent.
Harness note: the runto/mrun `tick()` helper strips zeros (`tr -d '\r[0m'`), so one slice printed
"1264193" for 12640193; targets were still honored (overshoot up to ~140 ticks from poll granularity).

## Diagnosis (read-only, existing reads only)
- Stocks and workshops do not explain it: 10 free boulders, 4 blocks, a complete Masons and Mechanics workshop
  and Still, none busy, no forbidden stock, MASON, MECHANIC and BREWER labors each have at least 1 worker.
  Order 0 (blocks) and 1 (mechanisms) are `validated true` with no conditions, so nothing in the order blocks them.
  `orders check-duplicate blocks`: duplicate_risk true, order 0 in flight, jobs_in_flight empty.
- Order 3 (ConstructThrone) is `validated false`, and no order went from unvalidated to validated.
- The game has a job type `ManageWorkOrders` (job_type id 195). It never appeared in any census in the 2793 ticks
  (polls were about 100 ticks apart, so a very short job could be missed, but no order state changed either).
  The Manager never did anything except Eat and Sleep-adjacent idle: no job near an office.
- Most likely reason, from the evidence: the Manager is not doing the paperwork. Unit 345 is in the highest
  stress category, sits idle between meals, and the game's own gate for an office (our proxy still reads
  `cannot_tell`, getRoomDescription is empty for zone 13) may not be satisfied, so no `ManageWorkOrders`
  job is created and orders stay `active false`. This is an inference: nothing here read the game's own nobles
  screen, the Manager's thoughts, or why the game skips creating that job.
- Not ruled out: order 0-2 dispatch also needs the manager to have "validated" recently rather than the stale
  `validated true`; a longer run, or a Manager who reaches his office (his z offset to zone 13 was not read; my
  read of the zone's assigned unit failed on a missing field), may behave differently.

## Final state
Paused at abs_tick 12640193. 22 alive, 1 dead, worst hunger and thirst fine, 0 warnings. Stress cats 2 2 4 8 2 3 1
(cat0 345 and 455). Pick 118 held by Zuglar (192), in inventory. Files here: ordscan.lua, stock.lua, mrun.sh, slice1-8.txt.
