# Live run: office build retry, 2026-09-24 (STOPPED at stage 2/3, fort paused)

HEAD 046a10a. Result: orientation chosen correctly, designations landed, but
NO dig job was created (same failure class as attempt 1) and a slow-tier
advisory fired. Re-paused and stopped. No throne, build, zone or owner change.

## Stage 0
Peek: paused, abs_tick 12613978, 22 alive, 1 dead, hunger/thirst fine, 0 warnings.
`df-overseer-fort quicksave` issued (prior save_dir `autosave 2`); polled
`quicksave "autosave 2"` until confirmed:true, slot `autosave 3` (save_dir, not mtime).
Tick 12613978.

## Stage 1: preview office-room-v1 office_room_v1_shell Still -1 1 40 (preview.json)
orientation rot180 (none, rotcw, rotccw entrance_reachable false), entrance_reachable
true, dig_can_start true, hidden 11, smoothable 0, ok false (finish not met, expected).
As predicted.

## Stage 2: real apply (... Still false -1 1 40) (apply1.json)
Handle **site-2** (NE 2 of Stockpile #2), orientation rot180, designations_landed
true, shim_restored true, dig_can_start true. Tick 12613978.

## Slice 1 (window.sh 200; clock resume, poll, pause) (slice1.txt)
12613978 -> 12614468 (490 ticks; the poll overshoots). Vitals unchanged (22/1, fine/fine).
Advisory at tick 12614457: reason hostile_slow, BIRD_KEA, 3 tiles N of the Still,
tier slow, tier_reasons theft_tag_close_range; fps dropped to 10 (slow tier).
`status site-2` (status-s1.json): dig.state **stalled**, pending_dig_designations 9,
designations_with_a_job 0, blind_no_walkable_neighbour 9, startable_no_job_yet 0,
ticks_since_apply 490, shell_done false, still_solid 10. stall_remedy: release
the site, re-apply where entrance_reachable true.

Both stop conditions met (no dig job; hostile advisory). Nothing released, no
second apply, no other change. Ticks used 490 of 5000.

## State left
Paused at abs_tick 12614468. site-2 holds 9 blind dig designations. Old Office
zones 10/11, orders, labor untouched.

## Resume at stage 3 (coordinator: site-2 "stalled" was a false positive)
Coordinator verified job id 2275 (Dig, entrance gap) exists; status dig.state not
trusted. Own census `jobs-census.lua` (global, by type and worker), slice.sh
(ignores the known informational kea advisory tick 12614457, alerts on any tripwire
or new advisory). Slices: 12614468 -> 12614521 (window.sh aborted on the stale
advisory) -> 12614848. Vitals each time 22 alive, 1 dead, fine/fine; no tripwire,
no new advisory; kea still the only advisory (informational).
Census at every point: Dig x1 (no worker), Sleep W2, Eat W1. Job 2275 unclaimed for
~870 ticks since apply (12613978), over the 600-tick rule: re-paused, stopped.
pick-diag.lua (pick-diag.txt): only one pick (item 118, in inventory, not forbidden),
held by Zuglar Nakuthuzol, Miner, MINE labor on, currently Sleep. Other MINE-enabled
dwarfs: Ultraplanks (Miner, asleep, no pick), Faithfulbridge (Fisherdwarf, no pick,
idle), Blazesmirrored (Gem Cutter, no pick, idle). No labor or pick changed.
Paused at abs_tick 12614848.

## Continuation per orchestrator (no pick/labor changes)
slice.sh 500 x3, 300 x2 (slice3.txt, who.lua names holders of Dig/SmoothWall/Sleep).
Ticks: 12614848 -> 12615387 -> 12616370 -> 12617452 -> 12618117 -> 12618754.
Every slice: 22 alive, 1 dead, fine/fine, no tripwire, no new advisory.
Job 2275 stayed unclaimed (Dig x1, no worker; Zuglar and Ultraplanks asleep) through
12616370 (~2400 ticks after apply). By 12617452 Zuglar woke and held the Dig job
(Dig W1). At 12618117 still Dig W1 (Zuglar). At 12618754 Dig W1 (Zuglar) plus Dig x2
unclaimed: the gap is dug and interior jobs now exist. Budget used 4776 of 5000
(12613978 start). Stopped at budget: shell not done, no stage 4-6 actions.
Paused at abs_tick 12618754.

## Budget extension to 8000 (slice4.txt)
Ticks 12618754 -> 12619842 -> 12620965 -> 12621992. Vitals 22/1 fine/fine each slice,
no tripwire or advisory. Zuglar kept digging (Dig W1). status (untrusted dig.state):
pending_dig 4 -> 3 -> 3, still_solid 8 -> 6 -> 6, shell_done false. Budget cap
(12613978+8000 = 12621978) reached at 12621992 (14 over, poll granularity). Paused.

## Slow-progress read-only check (slow-diag.lua/.txt, slow-diag2.txt)
Zuglar (unit 192): stress category 4, not looping. Read 1: Dig job 2324, timer 16,
target adjacent (0,1,0), not suspended/repeated/by-manager, path empty. Job ids change
because each newly revealed tile is its own new job (2275 gap, 2298, 2303, 2324, then
2333..2337), not cancel/recreate. Reports (last 400): 29 matches, none about him
(others: kea-interrupted Drink, give-food/water cancels). Sleep/eat interruptions
explain slow pace (first ~3400 ticks asleep). Read after 150 ticks: new job 2333,
walking (path 13), pending dig 3 -> 1, still_solid 6 -> 5. Verdict: progressing, slow.
Budget extended by 2500 (cap 12624478) per coordinator. Slices 12622658 -> 12623233 ->
12623877 -> 12623957 (slice5.txt): smoothable 5 -> 8, still_solid 4, pending dig 1.
## TRIPWIRE at 12623957: announcement, GHOST_ATTACK (report 411), fort self-paused.
Stopped. rep.txt has recent reports.

## Ghost acknowledged, continued (slice2.sh, pre.lua, slice6.txt)
Ghost tripwire latched: resume refused until `clock clear`; ran `clock clear` (had_latch true).
Slices 12623957 -> 12624627 -> 12625390 -> 12626181 -> 12626923; pick 118 OK with Zuglar
before and during each; 22 alive/1 dead, fine/fine, no new tripwire/advisory. Cells (status
counters, dig.state not used): pending dig 0, still_solid 4 -> 2, smoothable 9, shell_done false.
STRESS: stress category counts baseline 0:1 1:3 2:5 3:7 ...; at 12625390 became 0:2 1:2
(one dwarf 1 -> 0 = more stressed). My slice loop did not auto-stop on stress and I ran
two further slices before noticing; stop condition applied late. Paused at 12626923.

## Cap 16500: automatic stress checks (slice3.sh, chk.lua, slice7.txt)
Thought list: no existing tool exposes unit thoughts/emotions (TOOLS.yaml has none);
not read, no route invented. Category counts (cats 0..6) every slice: 2 2 4 8 2 3 1 (unchanged
at 12627741, 12628448, 12629006, 12629807, 12630638); cat0 = units 345 (Manager) and 455
(child) only. Pick 118 OK with 192 each check; 22 alive/1 dead; no bad reports since 411.
Note: earlier stress rise happened before slice3.sh existed.
Interior dug (cells.lua, cells1.txt): 3x3 interior all floor, entrance gap open, top-row ring
smoothed 4, 11 ring wall tiles rough with NO designation and no SmoothWall job while status
said shell_done true (status-mid.json: enclosure not_enclosed 1 gap = the entrance).
Second real apply of the same phase on site-2 (apply2.json): 11 designated, landed. Then
SmoothWall jobs 9 W + 2 x (12629807), 11 W (12630638). Ticks 12630638 (16660 used, cap 16500
exceeded by 160 by poll granularity). Paused.

## Cap 19700 (runto.sh remote fast loop, ~6 tick overshoot; slice8.txt)
Ticks 12630638 -> 12631144 -> 12631699 -> 12632167 -> 12632399 -> (throne) 12632949 -> 12633178 -> 12633657
(cap 12633678). Stress cats stable except one improvement (3:8->7, 4:2->3) at 12632167, back
to 2 2 4 8 2 3 1 later; pick OK; 22/1 fine/fine; no alerts.
Smoothing: cell read cells3.txt: 14 of 15 ring walls smooth, one (bottom-right corner) rough
with 1 SmoothWall job in progress; cells4.txt after. Enclosure read (status-smooth.json):
not_enclosed, gap_count 1 = open_floor_edge 1 (the entrance), missing_wall 0, doorway 0.
Throne: dry run then real `workjob queue constructthrone "Stoneworker's Workshop" false`
-> job 2397 (Masons), worker Erush Kogandalzat, Woodworker, from 12632399 to cap 12633657
(~1260 ticks and still running). Chair/zone phases, owner, final reads NOT run.

## Cap 22200 (slice9.txt, thr2.lua/thr2-0.txt)
Ticks 12633657 -> 12636118 (22140 used). Stress cats 2 2 4 8 2 3 1 throughout, pick OK, 22/1.
Building 9 (read before chair phase): a Chair, build stage 1 of 1 (COMPLETE), contains item 3757
(shale CHAIR, not forbidden, in_building), 0 jobs, buildingplan isPlannedBuilding false. It does
not wait for an item, so it cannot claim the throne. World CHAIR items: 3757 (in bld 9).
Throne job 2397: worker Erush Kogandalzat (Woodworker), same id/worker every poll, dist 0 to the
workshop, not suspended, working true, completion_timer 198,170,142,81,78,42,6 then job gone.
Throne item 3946 (shale, not forbidden) then held by a unit (in_job true = being hauled), not
in building 9. Total from queue (12632399) about 3700 ticks.
Chair phase: dry (ok, 1 building) then real: ok, designations_landed true. Zone phase: dry ok,
real ok, landed; zone list shows new Office zone id 13 (unowned, near "unknown material Throne").
Owner assignment NOT done: no existing tool sets the owner of an existing zone (df-overseer-zone
only takes OWNER at `place`; nothing in blueprint lua). nobles requirements MANAGER read after
zone 13 existed: Office status not_met, zone_ids [11] only. Orders: 0,1,2 validated true active
false, 3 (ConstructThrone) validated false, all untouched. Final status-final.json: enclosure
not_enclosed gap 1 (entrance), 15/15 ring smooth (boundary_wall_fraction 1.0), floor unsmoothed.

## Cap 23200 (slice10.txt, chair.lua, chair0.txt, chair-final.txt)
Ticks 12636118 -> 12637400 (23422 used, 222 over: the last runto target 12637175 stopped at
12637374 and the tick read 12637400 after pause). Stress 2 2 4 8 2 3 1, pick OK, no alerts.
Item 3946: 12636118 held by unit 192 (Zuglar) in a job; 12636432 dropped on ground, not hauled
into anything; 12636740 on ground in a job; 12637128 in building 12 (in_bld); done by 12637374.
Chair building 12 (new, inside the site-2 footprint, inside zone 13's 3x3): stage 0/1 with 1
job until 12637128, stage 1/1 (COMPLETE) at 12637374+, contained 1 (the throne), jobs 0.
Reads at the end: nobles requirements MANAGER Office not_met, zone_ids [11]; detail says every owned
zone's getRoomDescription returned empty. Zone 13 (near "shale Throne") unowned, not_met, needs
attention. Direct getRoomDescription(zone 13, nil): ok=true, result EMPTY string. Enclosure:
not_enclosed, gap 1 (entrance, open_floor_edge). Finish: ring 15/15 smooth, floor 9 rough (not
smoothed by this template). Ring material 11 STONE 5 MINERAL. Owner not set (no tool).
