# Live run: deploy the room proxy fix, zone contents and blueprint status fixes

Date 2026-09-24, HEAD 5d8c3b4, committed bytes. Fort stayed PAUSED at abs_tick 12637400,
22 alive, 1 dead, hunger/thirst fine, before and after. No fort mutation, no refusal.

## Step 0: tick and quicksave decision
`df-overseer-clock status`: paused true, abs_tick 12637400, equal to the last confirmed
autosave tick (`autosave 3`). No quicksave taken (nothing to lose). Vitals: 22 alive, 1 dead.

## Steps 1 and 2: deploy (source = arrival /tmp = installed, all matched)
| File | sha256 first 16 |
|---|---|
| scripts/dfhack/df-overseer-zone.lua | c4bc38dac011c53d |
| scripts/dfhack/df-overseer-nobles.lua | 7b6daf01106fc62e |
| scripts/dfhack/df-overseer-blueprint.lua | 8e3d89cbc0000d2b |
| scripts/dfhack/TOOLS.yaml | 110feba245d2e5b3 |
| dfmcp/tools.py | 9a9abff2290bd8ce |
| agents/architect/tools.yaml | 9cc97548f282804e |
| agents/consultant/tools.yaml | 23de0879318fad06 |
| agents/overseer/tools.yaml | 12bbfae76c8cb57f |
| conductor/runner.py (openclaw VM) | cf19541a58356f74 (previous d21c4468a7b442a3) |

Game VM backups (cp -p, 8 files, path-flattened names): /opt/df/deploy-backup-20260924-fixes.
Openclaw backup: ~/deploy-backup-20260924-fixes/runner.py.orig (home of the ssh user).
dfmcp-server restarted with `sudo -n systemctl restart`: active, 0 RoleValidationError since
restart. conductor.service on the openclaw VM still inactive and disabled; nothing started.

## Step 3: live checks (real DFHack, `./dfhack-run <script> ...` in /opt/df/game)

**a. `nobles requirements MANAGER`: PASS.** Office: required 1, status `cannot_tell`,
zone_ids [13], detail "getRoomDescription came back empty but the owned zone does contain
qualifying furniture (zone 13 holds 1 qualifying building(s), 1 complete). An empty description
is not evidence of a bad room ... the game's own nobles screen is the arbiter." read_failures [].
Expected-versus-actual note: the brief expected furniture counts to read cannot_tell; for the
Manager every furniture requirement (boxes, cabinets, racks, stands) is required 0 and reads
`not_required`, which is correct for this position, not a fault. No coordinates.

**b. `zone contents 13`: PASS.** One building: kind Chair, id 12, exists true, build_stage 1 of
build_stage_max 1, holds_items true, matches_zone_kind true, tiles_inside 1. matching_count 1,
complete_matching_count 1, read_failures [], tiles_scanned 9, 3x3, furniture_kinds [Chair].

**c. `zone list Office "" "" ""`: PASS.** zone 10 unowned not_met; zone 11 unowned not_met;
zone 13 owned by unit 345 `cannot_tell`. read_failures []. This is the first live run of the
zone_room_value_status change.

**d. zone contents on 10 and 11 and negative controls: PASS.** Zones 10 and 11: buildings [],
matching_count 0, complete_matching_count 0, read_failures [], tiles_scanned 9. Refusals, all
named: id 999999 -> "no building with id 999999"; id 0 -> "building id 0 exists but is not an
activity zone"; id 12 (the chair) -> "building id 12 exists but is not an activity zone";
"abc" -> "ZONE_ID must be a number".

**e. `blueprint status site-2`: PARTIAL.** `sites` returns only site-2 (office-room-v1, rot180,
phases applied shell, shell, build, zone). dig.state `none_pending` (no stalled), jobs_in_site 0,
designations 0, ticks_since_apply 1282. shell_done **true**; shell_cells: carve_required 10,
carve_dug 10, carve_solid 0, smooth_required 15, smooth_done 15, rough 0, undesignated 0,
hidden 0, unreadable 0, done true. This agrees with the earlier cell read (0 rough ring tiles,
15 of 15 smooth, interior dug); finish_state already_finished 15, finish_required_met true,
surface boundary_wall smooth 15, rough_natural 0.
**jobs_claimed_by_a_worker is null, not a number.** Read of the source
(`dig_jobs_in_site`, blueprint.lua ~line 723-770): it is null by design whenever no dig job
exists in the site (claimed_known stays 0), so with jobs_in_site 0 this check cannot prove the
worker read works. Separate read-only check: `type(dfhack.job.getWorker)` on this build is
`function`, so the API exists, but no real job was available to exercise it. Unproven live.
The in_progress-with-a-job path (and the rough-ring shell_done false path) also could not be
exercised: the site is finished, and no other site exists.

**f. Fort state: PASS.** After all checks: abs_tick 12637400, paused true, 22 alive, 1 dead,
dfmcp-server active.

## Step 4: runner test (openclaw VM, DockerOpenClawRunner, model deepseek/deepseek-v4-pro): PASS
Same construction as run_consultant.py, relying on RunResult.final_answer only, timeout 600 s.
Note: the runner needed `sudo -n env PYTHONPATH=<repo> python3` (docker access, and the script
lives in /tmp so the repo must be on the path). Result: ok true, status ok, timed_out false,
error null, final_answer a non-empty str, cost_usd 0.00626, wall clock 19.8 s.
final_answer: "A memorial slab commemorates a deceased dwarf; once engraved and placed, it
lays that dwarf's spirit to rest, calming an existing ghost or preventing one from appearing,
and unlike a coffin it needs no body part, so it's the way to memorialize dwarves whose
remains are unrecoverable. Label: standard practice (well-established wiki guidance; not
verified against this fort's own raws)."
The temporary /tmp runner script, output and arrival copy on the openclaw VM were removed.

## Honest gaps
- jobs_claimed_by_a_worker unproven live (see e).
- Whether the game's own nobles screen accepts the office is still not readable from here.
