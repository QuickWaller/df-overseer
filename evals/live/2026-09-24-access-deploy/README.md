# Live run: deploy blueprint access fix (PARTIAL, stopped at a permission refusal)

Date 2026-09-24, HEAD 1aa452c, committed bytes only. Fort left paused.

## Step 0
Peek: paused, abs_tick 12613978. Quicksave issued via `df-overseer-fort quicksave`
(prior save_dir `autosave 1`), confirmed by cur_savegame.save_dir changing to
`autosave 2` (never mtime).

## Step 1: deploy (source = arrival = installed for all four)
| File | sha256 first 16 |
|---|---|
| scripts/dfhack/df-overseer-blueprint.lua | e9a856f32bd24236 |
| scripts/dfhack/TOOLS.yaml | a68f16d0a8db1ceb |
| dfmcp/tools.py | 66f851c38fafa3bc |
| agents/overseer/tools.yaml | 2547a58910846659 |
Backups (cp -p) in /opt/df/deploy-backup-20260924-access. dfmcp-server restarted
with sudo -n systemctl; is-active = active; 0 RoleValidationError lines since restart.

## Step 2: previews (dry, level -1, radius 40; the verb is `preview TEMPLATE PHASE SITE LEVEL RANK RADIUS`)
Real DFHack ran the new Lua with no error. Pending dig designations (bounded
map_blocks read, pending-count.lua) 45 before, 45 after all previews.
office-room-v1 / office_room_v1_shell near Still:
- rank 1 NE 2: orientation rot180 (none, rotcw, rotccw all entrance_reachable false), entrance_reachable true, dig_can_start true, hidden 11, ok false
- rank 2 E 5: rotcw, entrance_reachable true, dig_can_start true, hidden 11, smoothable 4, ok false
- rank 3 E 2: none, entrance_reachable true, dig_can_start true, hidden 11, smoothable 4, ok false
(Rank 1 now reports hidden 11 vs 10 earlier because site-1's own designations are in the census.)
Scan for a natural negative: Still -1 rank 5, Well -1 rank 1, Well -2 ranks 1 and 5 return
dig_can_start false with `would_strand` ("the dig cannot start: in the chosen orientation
the template's entrance ..."). Raw previews for ranks 1 to 3: preview-r1..3.json.

## Step 2 negative control: NOT COMPLETED
The batch that ran preview (Still -1 rank 5), `apply ... true` (dry) and
`apply ... false` (real, no ALLOW_STRANDED, meant to prove `blocked`) was DENIED by the
auto mode classifier (reason: Modify Shared Resources) before any part ran. I stopped.
It was probably the `apply ... false` call: the go-ahead excluded any new apply.
Nothing was routed around. The preview-only refusal (`ok:false`, `would_strand`) is
proven above; the apply-side `blocked`, no handle, no quickfort call is UNPROVEN live.

## Steps 3 and 4: NOT RUN (release site-1 status, dry run, real release).

## Continuation (coordinator-scoped)
- Dry-run apply on Still -1 rank 5: DENIED again by the classifier (Modify Shared Resources); not run, not routed around. Apply-side refusal remains UNPROVEN. No real apply was attempted.
- Lua backup confirmed by sha256 of the backup files: lua `77bc5f1749f010fb` (the previous blueprint-deploy version), TOOLS.yaml `78b1a31c3ff89a10` (previous). 2 files in the backup dir.
- `status site-1`: dig.state stalled, blind 10, pending 10, with_job 0, startable 0, stalled true, stall_remedy text present (files: status-site1.json).
- `release site-1 true`: ran, would undesignate 10 (quickfort undo, stats "Tiles undesignated for digging 10"), released false (release-dry.json).
- `release site-1 false`: released true, undesignated 10, dig_after none_pending, pending 0, cannot_undo note present (release-real.json).
- After: `sites` returns `[]` (handle forgotten); pending dig designations 45 -> 35 (bounded map_blocks read).
- NOT verified: the 5 smoothed north wall tiles by a direct read (release cannot touch smoothing per its cannot_undo note; no tile read was run).
- Clock after: abs_tick 12613978, paused true (same tick). Vitals (alive/dead/hunger/thirst) were NOT re-read.
