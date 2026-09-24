# Live run: deploy zone assign-owner / clear-owner, move the Manager's office to zone 13

Date 2026-09-24, HEAD 1811a45, committed bytes. Fort stayed PAUSED at abs_tick 12637400
throughout (before and after). No failures.

## Step 0
Peek: paused, abs_tick 12637400, 22 alive, 1 dead, hunger/thirst fine.
`df-overseer-fort quicksave` issued (prior save_dir `autosave 2`), polled with
`quicksave "autosave 2"` until confirmed:true, current_save_dir `autosave 3` (save_dir, not mtime).

## Step 1: deploy (source = arrival /tmp = installed, all matched)
| File | sha256 first 16 |
|---|---|
| scripts/dfhack/df-overseer-zone.lua | a1a3651a34a8580a |
| scripts/dfhack/TOOLS.yaml | 9962114f275dfe08 |
| dfmcp/tools.py | f9b4a7f6f93731e3 |
| agents/overseer/tools.yaml | 76819d2f21b7259c |
Backups (cp -p): /opt/df/deploy-backup-20260924-owner. dfmcp-server restarted
(sudo -n systemctl), is-active active, 0 RoleValidationError since restart.

## Step 2: reads before writing
`zone list Office '' '' ''` (zone-list-before.json): zone 10 unowned; zone 11 owned by
unit 345; zone 13 unowned (near "shale Throne"); all room_value_status not_met.
Note: `zone check-owner` takes KIND OWNER (a policy check), not a zone id, so per-zone
owners came from `zone list`; `check-owner Office 345` returned owner_capable true.
`nobles requirements MANAGER` before: Office required 1, not_met, zone_ids [11].

## Step 3: dry runs
- `assign-owner 13 345`: refused `unit_already_owns_kind_zone`, other_zone_ids [11], applied false.
- `clear-owner 11`: dry_run true, previous_owner_unit_id 345, would_write zone.assigned_unit_id
  none + unit 345 owned_buildings loses the zone, read_failures [].

## Step 4: real writes
- `clear-owner 11 false` (clear-real.json): applied true, set_owner_call ok, after zone_side
  unowned, links_confirmed zone_side_cleared true, previous_owner_released "yes".
- `assign-owner 13 345 false` (assign-real.json): applied true, links_confirmed zone_side true
  and unit_side true, holder_link_resolves "resolved", before unit_side_holds_zone no, after yes,
  read_failures [], holder room_value_status not_met. No restore needed, none run.

## Step 5: final reads
- `nobles requirements MANAGER` Office: required 1, status **not_met**, zone_ids **[13]**,
  detail "every owned zone's getRoomDescription read succeeded and returned empty; the
  strongest evidence available that this room's value has not cleared the lowest quality tier,
  not proof of an exact number ...".
- `zone list Office`: 10 unowned, 11 unowned, 13 owned by 345; all three not_met.
- Bounded read: `dfhack.buildings.getRoomDescription(building 13)` -> ok, string, "" (EMPTY).
  Unit 345 owned_buildings count 1.
- Clock paused at 12637400 (unchanged), 22 alive, 1 dead, fine/fine.

## Verdict
Owner link works end to end on real DFHack (both directions read back). The Office
requirement now counts zone 13 but is still not_met: the room's description is empty, so
the remaining gap is the room's value, not the owner link. Not proven: whether the game's
own noble logic accepts the room, and any preserve-rooms reservation (unreadable here).
