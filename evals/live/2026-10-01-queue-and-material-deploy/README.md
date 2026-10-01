# Deploy and live check: queue fixes, amend/abandon, buildingplan material filter

Date: 2026-10-01. Repo `f2058dd` deployed to VM 103 with
`scripts/ops/deploy-vm103.sh 2026-10-01-ab`: 14 files, hashes verified on
arrival and at the install path, no CRLF, SQLite online backup and file
backups under the tag's backup directory. Imports and `doctrine.validate`
passed in the server venv; `dfmcp-server` restarted `active`. The fort stayed
paused throughout; nothing in it was built or changed.

## Queue (handoffs/2026-10-01-queue-bugs-and-amend.md)

- Role tool counts over a real MCP client: overseer 89 (was 87: `queue__amend`,
  `queue__abandon`), architect 52, consultant 29, quartermaster 24,
  conductor 16.
- `queue.abandon` on a nonexistent project, as the overseer: refused before
  any write ("does not refer to an existing project"). As the architect:
  refused by the allowlist. `queue.project_status`: "(no projects)".
- Not exercised live: a real amend or abandon (it would leave permanent test
  records in the fort's queue); the offline suites cover the logic.

## Material filter (handoffs/2026-10-01-buildingplan-material-filter.md)

**Found live: the write is a silent no-op.** A dry run of `building.build`
for a constructed wall (`Cw`) near the Well reported
`filter_material_names: ["WOOD", "material_0_243"]`. A reversible
`dfhack-run lua` check (`bpcheck.lua` here) on Construction/Wall filter 0:

| Step | Enabled materials |
|---|---|
| before | 367 of 367 |
| set `WOOD`, `material_0_243` (what the tool writes) | 367: both names dropped, filter unrestricted |
| set `shale` (the real `MaterialInfo:toString()` name of 0:243) | 1 |
| set `{}` (restore) | 367 of 367 |

Cause: `buildingplan.cpp:918-921` keeps only names in its `mat_cache`, keyed
by `MaterialInfo::toString()`; an empty result resets the filter to
unrestricted (`:926`). The offline stub accepted any name, so the tests could
not see it. Also confirmed: the tool's own read of `getMaterialFilter`
(`props.enabled == "true"`) is correct, and `df.construction_type` reverse
lookup works (`Wall` = 1). The deployed code is harmless meanwhile (it writes
names that are dropped, then restores). Sent back to the stream to build the
list from buildingplan's own vocabulary and read it back after writing.

My own first read of the check miscounted (it treated each returned table as
true); corrected by reading `props.enabled`, as recorded above.

## After the fix (deploys `2026-10-01-c` at `baa283b` and `2026-10-01-d` at `09b5256`)

The stream rebuilt the class from buildingplan's own vocabulary with a
read-back. The first live dry run then showed 223 names with no hematite, but
including metals (adamantine, aluminum) and wool: the default took every
non-economic name buildingplan accepts for a wall. The orchestrator narrowed
the default to the register's class, stone and wood only (`DEFAULT_CLASS_CATEGORIES`,
data), with a category name (`stone`, `wood`) accepted as the choice, plus
three tests. Live dry run after: 143 names, stone and wood only, no metal,
no hematite.

Reversible write on the real game (`bpapply.lua`, calling the tool's own
exported `building_filters_and_gaps` and `apply_material_filters`):

| Step | Construction/Wall filter 0 |
|---|---|
| before | 367 of 367 enabled, hematite and adamantine among them |
| tool writes its class | `ok true`, read-back 143 enabled, no hematite, no adamantine |
| restore | 367 of 367 |

Stockpile tools deployed (overseer now 93 tools) but only as code; no live
call yet.

**Still unverified:** that a dwarf fetching for a real planned building
honours the narrowed filter (needs a real build and an unpause), and that
quickfort registers the building with buildingplan inside the write-restore
window (`buildingplan.cpp:636` copies the filter at add time; quickfort's
call timing not re-read).

## Manager orders live test (deploys `2026-10-01-e`, `2026-10-01-f`)

- Dry run then real `orders.create MakeBarrel 2 Daily`, item condition
  `AtMost:20:BARREL` (17 barrels in stock): order 4 created and read back
  from the game exactly (Daily, AtMost 20 BARREL, amount 2).
- **Bug found live:** `workorder.lua` prints `Queuing MakeBarrel x2` to
  stdout before the tool's JSON, so a successful create came back from MCP
  as `isError` (an agent would retry and duplicate). Fixed (`0be8c2a`): the
  line is captured into `workorder_output`; regression test fails without
  the fix.
- Supervised unpause, 10 FPS, 300 s, tripwire armed: tick 209571 to 212610
  (about 2.5 game days), 22 alive, 0 warnings, re-paused and restored.
- **After the window, nothing dispatched:** order 4 `validated: false,
  active: false`; orders 0 to 2 (from weeks earlier) `validated: true,
  active: false`; order 3 never validated; barrels still 17. The Manager
  (appointed, with an office) is not turning orders into jobs on this fort,
  consistent with the 2026-09-24 finding and not with the 2026-09-30 report
  that orders work. Cause unknown; order 4 left in place as a live case.

### Read-only diagnosis after the window (`research/2026-10-01-orders-not-dispatching.md` checks)

- Manager: unit 345, alive, citizen, position from the fort's own site
  government, owns zone 13 (the office), no squad, 17 labours, idle at the
  pause. The research's leading theory (no Manager appointed) is wrong.
- All four workshops (Still, Masons, Mechanics, Carpenters): profile
  `block_general_orders false`, `max_general_orders 5`, no worker limits.
- Jobs: zero with an `order_id`, and no `ManageWorkOrders` job exists: the
  Manager has never started the job that validates orders. Two orders
  unvalidated.
- Open: why the Manager never takes `ManageWorkOrders`. The longest
  unpaused stretch this fort has had is a few game days; a one-month
  supervised window watching for that job is proposed to the user.

## labor.quota (deploys `2026-10-01-g`, `2026-10-01-h`)

Granted: `labor.quota` overseer only; `labor.quota-status` overseer,
architect, quartermaster. Live counts: overseer 97, architect 53,
consultant 29, quartermaster 25, conductor 16.

- `quota-status HAUL_ITEM` first read `mode: unrecognised`: autolabor's
  real line is `haulers, currently 18 dwarfs`, the stub had invented a bare
  `haulers`. Parser and stub fixed (`dfe796b`); the corrected stub fails the
  old parser. Live after: HAUL_ITEM `haulers`, 18 by autolabor and 18 by
  independent count; MINE `automatic`, minimum 2, maximum 200, 2 and 2.
- `quota HAUL_ITEM 1 200` dry run: reports `would_set` without writing. No
  real write yet.

## Month window, a sealed office, and the rescue (2026-10-01)

User go-ahead for a one-month supervised window. Quicksave first (confirmed,
`autosave 2`). `labor.quota MINE 3 200 200` written for real, read back
minimum 3. Window: 100 FPS, 420 s, tick 212612 to 243881 (about 26 game
days), tripwire armed, re-paused cleanly.

- **labor.quota works live:** citizens with MINE went from 2 to 3 during
  the window (watcher, every 25 s). Not yet reset to 2.
- **The Manager never took `ManageWorkOrders`** in 26 days; orders
  unchanged (0-2 validated inactive, 3 and 4 unvalidated).
- **Cause found, and it is ours.** The user saw DFHack's "stranded
  citizens" notification. Walkable groups: 20 citizens in one, 2 in
  another: the Manager (345) and a miner (346), inside the office, zone 13
  (interior 103,102 to 105,104, z167). Four of the five ring walls
  designated by `construction.build` on 2026-09-28 (buildings 18 to 21)
  had been built, including the two on the north side touching the main
  fort; the room's way out was walled. This is the defect the 2026-09-28
  dependency-graph design predicted ("treats every open ring tile as
  buildable, which would wall a room's own doorway"); `keeps_access` was
  added after these walls were designated and nothing re-checked them.
  Very likely also why no order was ever validated: the Manager could
  not reach anything (not proven; orders were stuck before the walls were
  finished).
- **Rescue (user's go):** `dfhack.constructions.designateRemove` on the
  wall at 103,101 (the player's remove-construction designation). 10 FPS
  window: the wall became floor about 870 ticks in; the Manager drank
  (thirst 40664 to 37) and ate, the miner too; all 22 citizens in one
  walkable group after, nobody hungry or thirsty; re-paused. The DFHack
  notification cleared at the same time.
- Building 22 (102,104) still planned and suspended next to unmined ore.

**Follow-ups:** re-check every still-planned construction against
`keeps_access`, not only new ones; read DFHack's own notification list
(stranded and the rest) in the conductor as wake reasons; reset MINE to its
previous minimum 2; watch whether the Manager now validates orders.
