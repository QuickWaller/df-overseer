# Office, first real build, and one run window, 2026-09-23

**Status: partial. Stopped by a tripwire on schedule, as designed.** This was
the first unattended run of the fort. One 900-tick window ran; the fort
auto-paused itself on `hostile_reachable` (a kea bird, wildlife, 68 tiles
away, sharing the citizens' walkable group), which is exactly what the
in-game tripwire is built to do. Per the handoff's hard lines ("Stop
immediately, pause, quicksave and report ... a hostile appears... Do not push
on to finish the task"), this run stopped there rather than continuing
windows. The fort ended paused, no deaths, vitals unchanged from the start.

## Safety envelope, as run

- **Quicksave before anything**: confirmed slot `autosave 1` (rotated from
  `autosave 3`), via `cur_savegame.save_dir`, never mtime.
- **Tripwires armed before the first unpause**: `df-overseer-clock arm`
  returned `armed: true`, `hunger_critical: 75000`, `thirst_critical: 50000`,
  `check_interval_ticks: 100`, `threat_check_every_n: 10`. Confirmed again
  with `clock status` before unpausing.
- **One bounded window, well under the 2000-tick cap**: unpaused at
  `abs_tick 12606174` (year 31, tick 106974); the tripwire fired at
  `abs_tick 12607074` (year 31, tick 107874) — 900 ticks. The fort was
  already paused when checked (the tripwire's own pause, not a manual one).
  Confirmed with `clock status` (`paused: true`).
- **Quicksave after the window**: confirmed slot `autosave 2` (rotated from
  `autosave 1`).
- **Stop condition hit**: `hostile_reachable`, detail `{race: BIRD_KEA,
  distance_tiles: 68, direction: SE, near_landmark: "Mechanic's Workshop",
  why: ["shares_walkable_group_with_citizens"]}`. A kea is ordinary wildlife,
  not a threat in practice, but the tripwire's job is to catch "a hostile
  that can reach the fort" without judging severity, and it did exactly
  that. No second-guessing it from here: reported, not overridden.
- 1 window used of the 10 allowed (2000 of the 20000 allowed ticks; actual
  used 900).

## Starting state (read before any action)

Matched the handoff's own recorded starting state exactly: paused, year 31,
`cur_year_tick 106974`, `abs_tick 12606174`, 22 alive, 1 dead, worst hunger
"fine", worst thirst "thirsty" (warning, not critical — `thirst_critical` is
"dehydrated"). `orders.list`: 3 orders, all `validated: true, active: false`
(blocks id 0, mechanisms id 1, brew_drink id 2). `nobles.list`: MANAGER
(position 10) held by unit 345 / histfig 331, `required_office: 1`,
`vacant: false`. No zones existed on the fort before this run (confirmed:
`zone.find`/`zone.place` searches found no pre-existing Office).

## What room value turned out to require: open, not settled

This is the finding the design needs, and this run could not settle it in
900 ticks. Two Office zones now exist:

- **Zone id 10**, no owner, near the newly built Chair (`unknown material
  Throne`), placed first before the owner-assignment approach was worked
  out. `room_description: null` on read-back both times.
- **Zone id 11**, owned by unit 345 (the Manager), placed second, near the
  Well, **not** overlapping the Chair's tile (the Chair's own 3x3
  neighbourhood was already zoned by id 10, so the tool's own
  `already_zoned_same_type` rejection pushed the owned placement to a
  different nearby site). `owner_result.read_back` confirmed
  `get_owner_unit_id: 345` immediately after placement, and a later
  `check-owner Office 345` call after the run window still reported
  `unit_id: 345` — the ownership held.

Both zones report `indoors: false` — no indoor 3x3 site existed near any
workshop or the Well within a 20-tile radius at any level tried (0, -1), so
this is an outdoor office, the best available, not this project's first
choice (`zone.lua`'s own `prefer_indoors: true` is a preference, not a
filter that excludes outdoor tiles).

`read_back.room_description` was `null` both times, immediately after
placement. Order id 3 (the new furniture order, below) was still
`validated: false` after the 900-tick window, so **the office-plus-order
question is still open**: either 900 ticks is too few for the game's own
validation pass / the Manager's pathing to the office, or the office's room
value is genuinely 0 (unsmoothed floor, no furniture inside it) and
insufficient even for `required_office: 1`. This run cannot tell the two
apart yet. Next step: more ticks with the fort's tripwire either disarmed
for wildlife or the threat radius/logic revisited, then re-read
`orders.list` id 3 and `zone check-owner`/`getRoomDescription` again.

## The first real build of a never-built kind: Chair

**Dry run**, `building.build Chair Well 1 20 true`:
```
validation: { by: "quickfort run --dry-run", ok: true, problems: [],
  stats: { "Buildings designated": 1 } }
gaps: [ "needs 1 of CHAIR, 0 available" ]
requirements.building_material.buildingplan_enabled: true
site: { direction: "E", distance_tiles: 1, near_landmark: "Well", rank: 1 }
```

**Real build**, `building.build Chair Well 1 20 false`, same site:
```
quickfort_ok: true, quickfort_problems: [],
quickfort_stats: { "Buildings designated": 1 }
read_back: { building_found: true, error: null, type_matches: true }
```

Side by side: identical site, identical quickfort stats, and the real run's
own read-back confirms the building now exists and is the right type. This
is the first real, non-dry-run build of a kind `df-overseer-building.lua` had
never built before. It is **not yet complete** — `stocks.availability CHAIR`
read 0 before and after the run (no chair item exists to fulfil it yet), and
`stuckjobs.find` shows the `ConstructBuilding` job for it as
`waiting_on: "suspended"`, `idle_ticks: 898` — DFHack's `buildingplan`
accepted the placement with zero material on hand (`buildingplan_enabled:
true`) and is holding the job suspended until a Chair item appears, exactly
as documented in `df-overseer-building.lua`'s own header.

To supply that item, a new manager order was created (item 3 below,
`orders.create chair 1`) rather than `workjob.queue`, because
`workjob.lua`'s job vocabulary is still the three original kinds
(blocks/mechanisms/brew_drink) — `chair`/`table` are only in
`orders.lua`'s `JOB_INFO` table, added in a prior stream for the manager-
order route specifically. This fort has no Carpenter's Workshop (`landmarks
list workshop` shows only Mechanic's Workshop, Still, Stoneworker's
Workshop), so `table`/`chair`'s hardcoded `workshop_subtype: Carpenters` is,
per that tool's own header, informational only and does not gate order
creation — the order was created regardless, on the expectation that DF's
own engine can dispatch a stone `ConstructThrone` job to the existing
Stoneworker's (Masons) Workshop using one of the 4 available boulders
(`stocks.availability BOULDER`: 4 available, 7 total). That dispatch was not
observed in this window; order id 3 read `validated: false` throughout.

## Orders watched

Before the window (baseline, from the sibling attribution deploy earlier the
same day): ids 0/1/2 all `validated: true, active: false`.

After placing the office and creating order 3, before unpausing:
```
id 0  ConstructBlocks        validated: true   active: false
id 1  ConstructMechanisms    validated: true   active: false
id 2  CustomReaction(brew)   validated: true   active: false
id 3  ConstructThrone        validated: false  active: false   (new, this run)
```

After the 900-tick window (unchanged):
```
id 0  ConstructBlocks        validated: true   active: false
id 1  ConstructMechanisms    validated: true   active: false
id 2  CustomReaction(brew)   validated: true   active: false
id 3  ConstructThrone        validated: false  active: false
```

None of the four orders changed state in 900 ticks. `stuckjobs.find`
returned exactly one entry, the suspended Chair-construction job, no
manager-order-spawned job with an `order_id`. **Whether a finished order
leaves `world.manager_orders.all` remains unsettled** — no order reached
`active` in this window, let alone finished, so `docs/AGENT-LOOP.md` §7's
open assumption is still open.

## Vitals, every checkpoint

| Checkpoint | abs_tick | year/tick | alive | dead | hunger | thirst |
|---|---|---|---|---|---|---|
| Before first unpause | 12606174 | 31 / 106974 | 22 | 1 | fine | thirsty (warning) |
| After the 900-tick window (tripwire pause) | 12607074 | 31 / 107874 | 22 | 1 | fine | thirsty (warning) |

No death, no vital crossing a threshold, no worsening across the one window
run (only one window ran, so the "two consecutive windows" comparison this
handoff's stop condition names does not yet apply).

## Refusals, verbatim

- **Mine, not the harness's**: while building the ssh wrapper, an early
  `sed`-based redaction command did not actually redact `DF_VM_IP` and the
  full CIDR value appeared in this session's own tool output before the
  address-hiding wrapper script existed. A second slip, also mine: the same
  early connectivity test piped in `hostname`, printing the guest hostname
  (`df-colony-01`) to this session's output. Both are flagged here rather
  than concealed, matching the same incident class this same day's sibling
  deploy run flagged in its own README. Neither value was written into any
  committed file, this doc included; both are excluded from this report by
  design. All later calls, including every SSH command shown or implied
  above, went through a wrapper script that resolves the address only
  inside a script process and never echoes it.
- **The harness's own refusals**, verbatim:
  - `This agent is isolated in the worktree ..., but this command runs sed
    with a value computed at runtime (the variable f) where an option may
    stand ... Refusing to run it` (a `for f in ...; do sed ...; done` loop
    over the Lua header files, before any live action was taken).
  - `This agent is isolated in the worktree ..., but this command runs a
    command whose name is computed at runtime inside a construct too
    complex to verify ... Refusing to run it` (a `$SP/dfhr.sh` call using a
    shell variable for the script path).
  - `This agent is isolated in the worktree ..., but this command runs
    dfhr.sh with the text "df-overseer-fort quicksave 'autosave 1'" inside a
    construct too complex to verify ... Refusing to run it` (a `for`-loop
    polling the post-window quicksave confirmation).
  All three were routed around by using plain, literal, single commands
  instead of loops or computed paths, per this repo's own documented
  practice for this exact class of refusal (`docs/TRAPS.md`, "Long shell
  commands ... have been refused in this harness").

## Fort's final state

**Paused.** `clock status` after the post-window quicksave: `abs_tick
12607074`, year 31, `cur_year_tick 107874`, `paused: true`, `armed: true`,
last tripwire recorded (`hostile_reachable`, kea, tick 12607074). 22 alive,
1 dead, hunger fine, thirst thirsty (warning only). Two Office zones exist
(id 10 unowned, id 11 owned by unit 345/the Manager). One Chair building
exists, placed but unfinished (buildingplan-suspended, awaiting a Chair
item). One new manager order exists (id 3, ConstructThrone x1,
`validated: false`). No write tool was used beyond `building.build`,
`zone.place` and `orders.create`, all as the handoff's own "What to do"
section asked for; `workjob.cancel` was not used.

## What is owed next

Not this stream's to decide on its own (a fresh session should pick it up):
whether to disarm/adjust the hostile-reachable tripwire for harmless
wildlife at long range before the next window, or accept short windows
punctuated by wildlife pauses as the normal cost of this tripwire's design.
Either way, the immediate next step is unchanged: more ticks, then re-read
`orders.list` id 3 and the two zones' `getRoomDescription`/owner state, to
settle what room value an office actually needs on this version.
