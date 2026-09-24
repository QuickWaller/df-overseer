# Direct Mason job split test, 2026-09-24 (live, Uniboslan; uncommitted)

Result: the direct job DISPATCHED (worker assigned within about 1000 ticks) and was working at
budget end, but had NOT completed after 2043 ticks (budget 2000). Fort left PAUSED. No manager order,
labor, zone, owner, building or setting change, no second job.

## Step 0
Peek: paused, abs_tick 12640193, 22 alive, 1 dead, hunger/thirst fine, pick 118 held by 192.
Quicksave: `df-overseer-fort quicksave` issued (prior save_dir `autosave 2`); confirm call read
`cur_savegame.save_dir`: `autosave 3`, confirmed true (not mtime).
Before: orders 0 ConstructBlocks, 1 ConstructMechanisms, 2 brew drink (8/8) all validated true active false;
3 ConstructThrone validated false. Job census: no jobs at all. Masons workshop (id 5, "Stoneworker's
Workshop") complete, 0 jobs. Free boulders 10, blocks 4. Manager 345 no job, stress cat 0.
Stress cats 0..6: 2 2 4 8 2 3 1, cat0 = 345 and 455. Files: blocks-dry.json, blocks-real.json.

## Calls
Dry run: `workjob queue constructblocks "Stoneworker's Workshop" true` -> would_queue true, one BOULDER
item resolved, jobs_queued_before 0, read_failures [].
REAL call (the only mutation): `workjob queue constructblocks "Stoneworker's Workshop" false`
-> create_ok true, **job_id 2419**, Masons, no repeat.

## Slices (mj.sh + mj.lua + chk.lua: auto re-pause on pick, cat0 count or new id, bad report text, death,
any tripwire/advisory beyond kea, order_id job, job gone, kea within 8 tiles)
| Slice | End tick | Worker | Job state | Manager 345 job | Orders | order_id jobs | Stress cats |
|---|---|---|---|---|---|---|---|
| 0 | 12640193 | none (queued) | ws 5, not suspended, timer -1 | none | unchanged | none | 2 2 4 8 2 3 1 |
| 1 | 12641250 | Erush Kogandalzat (unit 194, Woodworker) | working true, timer 228 | none | unchanged | none | same |
| 2 | 12641494 | 194 | working, timer 206 | none | unchanged | none | same |
| 3 | 12641740 | 194 | working, timer 184 | none | unchanged | none | same |
| 4 | 12641954 | 194 | working, timer 164 | none | unchanged | none | same |
| 5 | 12642236 | 194 | working, timer 139 | Drink | unchanged | none | same |
Every poll: 22 alive, 1 dead, hunger/thirst fine, pick OK with 192, no bad report (max report id 411), kea never
on a dwarf's level, no new tripwire or advisory. No unexplained self-pause this run (no slice ended on a
self-pause; every stop was my own target).
Notes: slice 1 overshot by about 850 ticks (first poll interval was 2 s; later polls 0.2 s). The runto `tick()`
helper strips zeros from printed ticks (12641740 prints 1264174); real ticks read from clock status.
Timer drained about 0.09 per tick (228 to 139 over 1000 ticks), so about 1500 more ticks were needed.

## End state
Paused at 12642236. 22 alive, 1 dead, fine/fine, pick 118 with 192. Stress cats 2 2 4 8 2 3 1 (cat0 345, 455).
Blocks 4 before and 4 after (job not yet complete), boulders 10. Job 2419 still held by unit 194.

## Interpretation
- Supported: a direct job at the same Masons workshop that the never-dispatched orders 0 and 1 could use got a worker
  and started work with the Manager doing nothing (Manager job none at every poll except one Drink), while orders
  0-2 stayed validated true / active false with no order_id job ever appearing. So workshop, boulders and a willing
  worker are not what blocks orders 0 and 1: capacity (in the sense of a free workshop, material, worker) exists.
  This is result (a) in the brief, with the block sitting in the manager-order layer (order never moving to
  active / never generating a job).
- Weaker: the first assignment took up to about 1000 ticks (the first check was at 1057 ticks; the exact tick of
  assignment was not observed), and the worker is a Woodworker, so "quick" is not established. The job did NOT complete
  in 2043 ticks, so "completes" is unproven for this job; the earlier throne job (2397) is the completion evidence.
- Cannot conclude: why orders do not activate (Manager paperwork, validation staleness, the gate the previous run
  guessed at); orders 0-2 were hand-validated and may need something this run did not test. This run did not touch
  orders, so it says nothing about whether a differently created order would dispatch.
