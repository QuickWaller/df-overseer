# Handoff: the room-value proxy called a working office `not_met`, and nothing can list what is inside a zone

Date: 2026-09-24. **Offline build. No deploy, no VM mutation, no fort change.**
Read-only ssh source reads on the game VM are allowed.

Read `CLAUDE.md`, the register row dated 2026-09-24 beginning "The room-value
proxy gave a false negative", `scripts/dfhack/df-overseer-nobles.lua`
(`requirements`, `ROOM_VALUE_FIELDS`, `owned_zones_of_kind`), and
`scripts/dfhack/df-overseer-zone.lua` (`ZONE_POLICY`, `furniture_type_ids_for`,
`zone_tile`, `list`).

## The failure

`nobles requirements MANAGER` reported Office `not_met` because
`getRoomDescription` returned an empty string on the owned zone. In the game the
Manager is assigned to that office and the nobles screen accepts it. The check
treated empty as evidence of `not_met`; that inference is falsified. Empty
was also returned with the Manager passed as the unit argument, and on the
outdoor zone 11, all while the fort was paused.

## What to build

1. **`nobles requirements`: an empty description alone never yields `not_met`.**
   For a room-value field, three states with these rules, in data, no per-kind
   branch: `met` if the description is non-empty; `not_met` ONLY with independent
   evidence (no owned zone of the kind exists, or the owned zone contains none of
   the furniture kinds that `ZONE_POLICY` lists for it); otherwise `cannot_tell`,
   with `detail` saying the description was empty and the zone does contain
   qualifying furniture, and that the game's own nobles screen is the arbiter.
   Keep `read_failures` plus `dfhack.printerr`.
2. **`zone contents ZONE_ID`**: a new read-only verb that lists the buildings
   whose tiles fall inside the zone's extents: building kind, id, completion
   (stage of total, `flags.exists`), whether any item sits inside it, and whether
   the kind matches the zone kind's `furniture_kinds`. Bounded by the zone's own
   size (refuse an enormous zone); no coordinates in output; kind-generic via
   `ZONE_POLICY`, no Office branch. Use the same tile-in-zone test the
   surface layer and `zone_tile` use rather than inventing a second one, and say
   which one you reused.
3. **Wire it**: `nobles.requirements` calls the same helper for its independent
   evidence, so there is one implementation of "is furniture inside this zone".
4. **Manifest and allowlists**: `scripts/dfhack/TOOLS.yaml`, `dfmcp/tools.py`,
   and grant `zone.contents` to architect, consultant, overseer (read only).
5. **Tests**: lupa harness pattern (`tests/test_zone_owner_lua_logic.py`,
   `tests/lua_stubs/`). Cases: empty description with furniture inside gives
   `cannot_tell` (this is the incident and must fail on the old code); empty with
   no furniture gives `not_met`; non-empty gives `met`; no owned zone gives
   `not_met`; a failed read gives `cannot_tell` plus `read_failures`. Show the
   incident test fails on the pre-change script.

## Scope

Yours: `scripts/dfhack/df-overseer-nobles.lua`, `scripts/dfhack/df-overseer-zone.lua`,
`scripts/dfhack/TOOLS.yaml`, `dfmcp/tools.py`, `agents/{architect,consultant,overseer}/tools.yaml`,
tests, and a short addendum to `research/2026-09-23-room-and-zone-requirements.md`.
Not yours: `scripts/dfhack/df-overseer-blueprint.lua`, `conductor/**`, everything
else, and per the `handoffs/` rule `Working.md`, `decisions/DECISIONS.md`,
`memory/`, `handoffs/INDEX.md`.

## Rules

`git merge --ff-only main` first. Baselines: ambient **1494 passed, 3 skipped**
(lupa on PYTHONPATH from a scratch `pip install --target`; 1449/4 skipped without),
`dfmcp/tests` in `.venv-dfmcp` **652 passed**. Commit as you go. No live fort
change. No em dashes, no attribution lines, coordinate-free output, stop on any
refusal and never route around one.

## Done means

`nobles requirements MANAGER` on this fort would report `cannot_tell` for the
Office (owned zone, chair inside, description empty), never `not_met`, and
`zone contents 13` would list the chair building inside the zone. The Result
names the live check and says what it cannot see.

## Result

(to be filled by the executor)
