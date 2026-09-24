# Live run: office room build for the Manager, 2026-09-24 (STOPPED at stage 3)

HEAD 0aed89c, user go-ahead for one staged build. Result: **the shell did not
dig; stopped and reported at stage 3 with the fort paused.** No throne, no
build phase, no zone, no owner change was attempted. Nothing else touched.

## Stage 0: deploy and quicksave

- Start: `clock status` abs_tick 12611557, paused, 22 alive, 1 dead, hunger
  and thirst "fine". Orders 0/1/2 validated:true active:false, id 3 as before.
- `blueprints/templates/office-room-v1.csv` from `git show HEAD:` (autocrlf
  off) placed in `dfhack-config/blueprints/templates/`. sha256 at source, on
  arrival in /tmp, and installed all `8f5b2f5f1f9c161f...` (match).
- Quicksave: `df-overseer-fort quicksave` (issued, prior slot `autosave 2`),
  then polled `quicksave "autosave 2"` until `confirmed: true`, `slot:
  autosave 3` (cur_savegame.save_dir, not mtime). Tick 12611557.
  (`df-overseer-clock` has no quicksave command; it lives in `df-overseer-fort`.)

## Stage 1: plan and preview

`plan office-room-v1`: footprint 5x5, room 3x3, 15 finish cells, four phases.
`preview office_room_v1_shell Still -1 {1,2,3}`: rank 1 (NE 2, Stockpile #2)
15 designated / hidden 10 / smoothable 5; rank 2 (E 5, Activity Zone #1) the
same; rank 3 (E 2, Activity Zone #2) 14 / hidden 11 / smoothable 4. All
`ok:false`, `finish_required_met:false`. Chose rank 1: tied for fewest hidden
(10) and blocked 0 (stone), nearest the Still. Expected the hidden ring cells
to reveal once the interior was dug.

## Stage 2: real apply

`apply office-room-v1 office_room_v1_shell Still false -1 1` -> handle
**site-1**, designations_landed true, pending 15, `shim_restored: true`
(first live run of the rectangle shim: it restored). `status site-1`: carve
cells 10, still_solid 10, shell_done false.

## Stage 3: the dig stalled (failure)

Windows via `clock resume`, poll, `clock pause` (script `window.sh`):
12611557 -> 12612085 -> 12612947 -> 12613978 (2421 ticks total). Vitals
unchanged each time (22 alive, 1 dead, fine/fine), no tripwire or advisory.

- The 5 visible ring cells got SmoothWall jobs and finished (pending 15 -> 10,
  smoothable 5 -> 0).
- **No dig job was ever created.** Job census (`jobs-census.lua`) showed only
  the 5 SmoothWall jobs, then none. The 10 blind dig designations (interior 9
  plus the entrance gap) remain pending, still_solid 10.
- Cause (`diag-site1.lua`, per-cell read, output not coordinate-bearing):
  only the site's north ring row is visible, with open floor beyond it. All
  20 other cells are hidden solid wall. The interior and the entrance gap
  (south ring row) touch no walkable tile, so DF creates no job for the blind
  designations. The template's only opening (the entrance gap) faces south,
  into unrevealed rock, while the site's reachable face is its north edge.
  Nothing orients a blueprint (known gap), and `preview` does not report which
  edge is reachable. `interior_fully_revealed: false` was the warning sign.

Not done, deliberately: opening the north ring row (would make a second
opening and break the enclosure the brief asks for), or choosing another rank
(would leave more blind designations; orientation is not previewable).
Stopped as instructed. Stages 4 to 6 not run. Ticks used 2421 of 5000.

## State left

Fort paused at abs_tick 12613978. 10 pending blind dig designations and 5
smoothed north-row wall tiles at site-1. Old outdoor office zones, orders,
labor untouched.
