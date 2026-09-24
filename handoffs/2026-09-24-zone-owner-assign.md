# Handoff: nothing can assign the owner of a zone that already exists

Date: 2026-09-24. **Offline build. No deploy, no VM mutation, no fort change.**
A deploy and a live assignment need their own go-ahead.

Read `CLAUDE.md`, `evals/live/2026-09-24-office-build-2/README.md` (the live
finding), `scripts/dfhack/df-overseer-zone.lua` (its `place` takes OWNER; its
`check-owner` reads it), `scripts/dfhack/df-overseer-nobles.lua`, and
`research/2026-09-23-room-and-zone-requirements.md`.

## The gap

The office room was built with the blueprint verb, which creates zone 13 with no
owner. `zone place ... OWNER` is the only path that sets an owner, and only at
creation. Nothing assigns an owner to an existing zone, and nothing removes one.
The Manager's requirement counts only zones owned by the holder, so a built,
furnished, enclosed office reads `not_met` until this exists.

## What to build

1. **`zone assign-owner ZONE_ID UNIT_ID [DRY_RUN]`** and **`zone clear-owner
   ZONE_ID [DRY_RUN]`**, generic over every zone kind (no Office branch).
   Read from the game how the owner link works in this install: what
   `dfhack.buildings` and the zone building's fields actually do (owner, the
   unit's owned-buildings vector, the assigned-room links, and the noble
   position's room links), from installed source over ssh with `cat -n`, read-only.
   Set every link the game itself sets, both directions, and nothing more.
2. **Validation before writing**, each a named refusal: zone exists and is a
   civzone; unit exists, is a living citizen, and (for a room-value kind) is not
   already owner of another zone of that kind unless an explicit override; the
   zone's kind matches something that has owners (`check-owner` already knows);
   refuse to change zone 10 or 11's owner implicitly. Dry run by default.
3. **Read-back**: after a real write, re-read via `check-owner` and
   `nobles.requirements` semantics and return whether the holder link now
   resolves; three states, `read_failures` plus `dfhack.printerr`, never a bare
   default.
4. **Where it belongs**: mutating verbs go to the Overseer only
   (`dfmcp/roles.py` rule 2). Say why these belong in `zone` rather than
   `nobles`, and what `clear-owner` cannot undo.
5. **Tests** with the lupa harness pattern in `tests/test_blueprint_lua_logic.py`
   (fake world: zone, unit, owner vectors), including a case that fails on any
   implementation that sets only one direction of the link.

## Scope

Yours: `scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml`,
`dfmcp/tools.py`, `agents/overseer/tools.yaml`, tests, and a short section
appended to `research/2026-09-23-room-and-zone-requirements.md`. Not yours:
everything else, and per the `handoffs/` rule `Working.md`,
`decisions/DECISIONS.md`, `memory/`, `handoffs/INDEX.md`.

## Rules

`git merge --ff-only main` first. Baselines: ambient **1480 passed** (with lupa
on PYTHONPATH from a scratch install; 1449/4 skipped without), `dfmcp/tests`
in `.venv-dfmcp` **652 passed**. Commit as you go. Read-only ssh source reads
only; no live fort change. No em dashes. No attribution lines. Stop on any
refusal; never route around one.

## Done means

Given a zone id and a unit id, a dry run says exactly what links would be
written and what would be refused; a real run sets both link directions and the
read-back confirms them. The Result names the live check to run against
zone 13 and the Manager (unit 345), and what the check cannot see.

## Result

STATUS: done offline. Not deployed, no live change. Branch commits: wip x2 plus the docs commit.

**Built** (`scripts/dfhack/df-overseer-zone.lua`, generic, no kind branch, policy still only in `ZONE_POLICY`):
- `assign-owner ZONE_ID UNIT_ID [DRY_RUN] [OVERRIDE]` and `clear-owner ZONE_ID [DRY_RUN]`, both `effect: mutate`, dry run by default (only the exact word `false` writes, same `truthy_dry_run` as `place`). OVERRIDE is the exact word `true`.
- Named refusals, each returned as a result with `refused`, `reason` and `applied:false`, never a write: `bad_zone_id`, `zone_not_found`, `not_a_civzone`, `kind_has_no_owner`, `bad_unit_id`, `unit_not_found`, `unit_not_alive`, `unit_not_citizen`, `already_owner`, `zone_has_other_owner`, `unit_already_owns_kind_zone`, `zone_owner_unreadable` (the zone's two owner reads disagree or failed), `duplicate_check_unreadable`, and for clear `zone_has_no_owner`. OVERRIDE unlocks only `zone_has_other_owner` (the old owner is released first) and `unit_already_owns_kind_zone`.
- Writes only through `dfhack.buildings.setOwner` (clear-then-set when replacing), never a field by hand. Read-back reports both directions: `zone.assigned_unit_id` and `getOwner` on the zone side, `unit.owned_buildings` on the unit side, and the previous owner's release, under `links_confirmed`. If only one direction reads back: `applied:false`, `one_direction_only:true`, and the named repair is the game's own `fix/ownership`. `holder` block: `holder_link_resolves` (resolved / not_resolved / cannot_tell, the exact test `nobles.requirements` applies), whether the unit holds a position asking this kind's room value, and `room_value_status` via the existing `zone_room_value_status`. Every failed read is `cannot_tell` plus `read_failures` plus `dfhack.printerr`.
- Registered: `scripts/dfhack/TOOLS.yaml` (both commands), `dfmcp/tools.py` (an `OVERRIDE` arg description; `ZONE_ID`/`UNIT_ID` already existed), `agents/overseer/tools.yaml` (both, `status: planned`; `agents/overseer` tool count should go 63 to 65 on deploy, not verified by a count test), `tests/test_zone_tool_manifest.py`.

**The link, from the install** (full notes appended to `research/2026-09-23-room-and-zone-requirements.md`, Q7 addendum): `building_civzonest.assigned_unit_id` (zone to unit), `owner_unit_cached_index`, `retained_owner`; `unit.owned_buildings` (unit to zone). Nothing else holds a room link: `entity_position` has only `required_*` values, so a noble's room is just the zone naming the holder plus preserve-rooms' own reservation state. `fix/ownership.lua` repairs a missing unit-side entry with `setOwner(zone,nil)` then `setOwner(zone,unit)`, which is the evidence that `setOwner` maintains both sides. The DFHack C++ is not installed on the game VM, so that `setOwner` writes both sides is inferred from its callers, not read: the read-back is what proves it live.

**Why `zone`, not `nobles`:** it changes a zone, and the owner policy (`ZONE_POLICY.owner`), owner reads and room-value read it reuses are this file's; `nobles` changes positions and holders and only reads zones. Mutating, so Overseer-only (`dfmcp/roles.py` rule 2); the Architect and others get no grant.

**What `clear-owner` cannot undo:** the unit's lost-room reaction, and any preserve-rooms role reservation (not readable from Lua, and the plugin may re-apply its own choice on its next cycle). It returns `previous_owner_unit_id` so `assign-owner` can set the owner again.

**Judgement call to flag:** the brief says refuse to change zone 10 or 11's owner "implicitly". Code cannot name fort ids, so the generic rule is: an existing different owner is never replaced without OVERRIDE (covers zone 11, owned by the Manager). Zone 10 is unowned, and assigning an owner to an unowned zone is the tool's purpose, so it is allowed like any zone, still dry-run-first.

**Verified:** ambient `python -m pytest` with lupa from a scratch install: **1494 passed, 3 skipped** (baseline 1480 plus 14 new). `dfmcp/tests` in `.venv-dfmcp`: **652 passed**. New: `tests/test_zone_owner_lua_logic.py` (14 tests, real Lua in lupa against `tests/lua_stubs/dfhack_zone_world.lua`): dry run writes nothing, only `false` writes, real run leaves both directions in the fake world, one-direction fake `setOwner` (zone-only and unit-only) is reported not trusted, every refusal, override releases the previous owner's side, clear-owner, failed reads refuse and are logged, failed room read is `cannot_tell` after a real write. The fake proves the tool's logic, not the game's `setOwner`. Lua was loaded under Lua 5.4; DFHack embeds 5.3, and the code avoids 5.4-only syntax, but that is not machine-checked.

**Live check after a deploy** (needs its own go-ahead; fort paused is fine, this is a state write, no ticks needed). Note the Manager (unit 345) already owns Office zone 11, so a plain assign to 13 refuses `unit_already_owns_kind_zone`. The check therefore is either (a) `zone assign-owner 13 345 true true` (dry run, OVERRIDE) to see the plan, then `zone assign-owner 13 345 false true` for a second office, or (b) `zone clear-owner 11 false` first, then `zone assign-owner 13 345 false`. Prefer (a): it is reversible with `clear-owner 13`. Pass if the result has `applied:true`, `links_confirmed.zone_side` and `unit_side` both true, `holder.holder_link_resolves` resolved. Then run `nobles requirements MANAGER` and `zone list Office "" "" ""`: the Manager's `required_office` should now count zone 13 (`room_value_status` met or not_met with the link resolved; a still-`not_met` then means the room, not the owner, is the gap).

**What the check cannot see:** the room-value number a position's requirement is compared against (only the quality word via `getRoomDescription`); whether the game's own noble logic accepts the room (only observable through the Manager's mandates, orders and mood); any preserve-rooms role reservation; and whether `owner_unit_cached_index` is updated (no read of it is made).

