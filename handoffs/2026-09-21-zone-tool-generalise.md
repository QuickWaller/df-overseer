# Handoff: generalise the `zone` tool over every zone kind, with an optional owner

Date: 2026-09-21. **WRITTEN, gated: dispatch after the optional-and-variadic-args
stream merges** (both edit `scripts/dfhack/TOOLS.yaml`). Live but read-only on
VM 103 (fort paused, dry runs only); one real placement is a separate,
supervised step that needs the user's go-ahead.

Read `CLAUDE.md` (especially "Tools must be generalisable"),
`scripts/dfhack/df-overseer-zone.lua` (the water-source-only tool this
replaces), `scripts/dfhack/df-overseer-building.lua` (the pattern: kind read at
run time from quickfort's own table, blueprint generated in code, dry run by
default, the result carrying `requirements` and `validation`),
`docs/BUILDING-TOOL.md`, `handoffs/2026-09-21-nobles-appoint.md` (its report:
why this exists) and `docs/TRAPS.md`, then this.

## Why

The nobles test showed an appointed Manager did not start the queued orders in
three game days. The position's own data says the Manager needs an office
(`required_office` 1) and the fort has **no zones at all**. Rooms are also on the
user's minimum bar for openclaw (build workshops, rooms, furniture). Today
`zone.find/place` handles Water Source only. The file's own header says other
kinds should be a table entry, not a rewrite; quickfort already knows **17 zone
kinds** (`zone_db_raw` in `hack/scripts/internal/quickfort/zone.lua`: Meeting
Area, Bedroom, Dining Hall, Pen/Pasture, Pit/Pond, Water Source, Dungeon,
Fishing, Sand, **Office**, Dormitory, Barracks, Archery Range, Garbage Dump,
Animal Training, Tomb, Gather, Clay) and a zone can carry an `assigned_unit`
property that quickfort hands to `preserve-rooms` as a **position code**, which
reserves the room for whoever holds that role.

## Deliverables

1. **Zone kinds from the game, not from a branch.** Read the kind table at run
   time the way the building tool does (Lua upvalues of quickfort's zone
   module; fail loud naming the missing hop), expose `list-kinds`, and make
   `find`/`place` take the kind as an argument. **Per-kind policy lives in data**:
   Water Source keeps its existing water-body policy (its own candidate finder,
   unchanged in behaviour); every other kind is a rectangle the caller sizes
   (W H, optionally defaulted), placed on revealed, walkable, building-free
   floor near a landmark using the same site-selection the building tool uses,
   with quickfort's own tile rule for the kind. The next kind must cost one data
   entry, no new code. Existing `water_source` calls must keep working with the
   same output.
2. **An optional owner on placement.** Investigate and report **both** paths
   that exist on this install, then implement the one that matches what a
   player does (assigning a room to a unit or a position on the room's own
   screen): `preserve-rooms`' `assignToRole` with a position code, and
   `dfhack.buildings.setOwner` with a unit id. Verify by read-back after a real
   placement (the zone's `assigned_unit_id` or the role reservation), and refuse
   with a named reason for an unknown code, a dead or non-citizen unit, or a kind
   that cannot have an owner. Do not assume; say what each path did.
3. **What an office needs to count.** The Manager's `required_office` is a room
   value, and a bare zone may not reach it. From the game's own data (and the
   DFHack docs), find what makes an Office meet a required value (furniture in
   the room), and put it in the result's `requirements` (as the building tool
   does) or say plainly that the game does not expose it. Do not guess.
4. **Verify, read-only, on VM 103**: `list-kinds` (17 kinds), `find` and dry-run
   `place` for at least Office, Bedroom, Dining Hall and Water Source (which must
   match today's output), the error cases, and that pause state and tick are
   identical before and after. Quote the output. No real placement.
5. **Manifest**: entries in `scripts/dfhack/TOOLS.yaml` for the new commands
   (arguments in the forms the optional-args stream added), `knowledge_scope`
   chosen and justified (a player sees zones on their own map), and the proposed
   grants written into this doc's report for the orchestrator (do not edit
   `agents/**`).

## Rules

- You own `scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml`, its
  manifest tests, and this doc. Do not touch `dfmcp/**`, `production/**`,
  `agents/**` or `gotchas/**`.
- Live, read-only: **never unpause, never place for real**, never run an
  unbounded query (`docs/TRAPS.md`), bound every scan. Stop and report on any
  classifier refusal; do not route around it. SSH as `df`; read secrets by key
  only; no address, hostname or token in any tracked file. Deploy nothing (run
  scripts from a scratch script path and remove it afterwards, as the building
  stream did).
- Unknown is never zero. Do not write `Working.md`, `decisions/DECISIONS.md`,
  `memory/` or `handoffs/INDEX.md`. **Commit after each milestone** and extend
  this doc's report as you go. No em dashes in prose. Use the Write tool for
  scratch scripts rather than long inline shell heredocs.

## Done means

`zone` lists and dry-runs every kind quickfort has, `water_source` behaves as
before, an owner can be given by position code or unit (dry-run verified, real
read-back path written and reasoned), the office-value question is answered from
data or reported unknown, the manifest and tests agree, the suites pass
(report before and after), and the write-up says what a real Office placement
test needs.
