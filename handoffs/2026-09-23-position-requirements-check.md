# Handoff: nothing here checks whether a position's room requirements are met

Date: 2026-09-23. **Offline. No VM, no deploy, no fort mutation, no unpause.**
The deploy and the live build need their own go-ahead and the orchestrating
session will ask separately.

Read `CLAUDE.md` first, then `research/2026-09-23-room-and-zone-requirements.md`
(written today, the evidence), the new `rooms` entries in `doctrine/seed.yaml`,
`scripts/dfhack/df-overseer-nobles.lua`'s `verify`, and
`scripts/dfhack/df-overseer-zone.lua`'s header.

## The gap, stated exactly

This fort appointed a Manager, placed two Office zones, and then spent two days
investigating why no manager order ever validated. The answer, found today:
`MANAGER` carries `required_office=1`, room value comes from what is inside
the room, and both offices are empty rectangles on the surface with the fort's
only Chair sitting outside both of their footprints.

**No tool here would have caught that, and one looked like it should have.**
`nobles.verify` reports whether an appointment is internally consistent: the
assignment's histfig links, `getNoblePositions` listing it, the vector index
matching. It never reads `required_office` at all. So it correctly reported a
properly appointed Manager, and we read that as "the Manager is set up".

Separately, `zone.place` reads `getRoomDescription` back after placement, and
on both offices that read returned empty every time. That was the correct
answer (no furniture, no room) and this project read it as the tool being
unable to see room value.

## What to build

Both halves are data-driven reads of what the game already knows. **No
per-position branches**: the requirement fields are on the position struct,
so one loop covers every position that exists, including ones this fort has
never appointed.

1. **A position requirements check.** Read every requirement field on the
   position and report, per requirement, whether it is met and what it is
   measured against. The fields found live today are `required_office`,
   `required_bedroom`, `required_dining`, `required_tomb` (room values) and
   `required_boxes`, `required_cabinets`, `required_racks`, `required_stands`
   (furniture counts). The live table for this fort:

   ```
   SHERIFF              off=100 bed=100 din=100 box=1 cab=1 rack=1 stand=1 pop=0
   CAPTAIN_OF_THE_GUARD off=250 bed=250 din=250 box=1 cab=1 rack=1 stand=1 pop=50
   MAYOR                off=500 bed=500 din=500 box=2 cab=1 rack=1 stand=1 pop=50
   MANAGER              off=1   bed=0   din=0   box=0 cab=0 rack=0 stand=0 pop=0
   BOOKKEEPER           off=1   bed=0   din=0   box=0 cab=0 rack=0 stand=0 pop=0
   DUNGEON_MASTER       off=250 bed=250 din=250 box=1 cab=1 rack=1 stand=1 pop=50
   ```

   Read the field names off the struct yourself rather than trusting this
   table's spelling. Decide whether this extends `nobles.verify` or becomes
   its own verb, and say why; extending it risks conflating two questions
   (is the appointment sound, versus is the post equipped), and a caller may
   well want them apart.

2. **An honest answer about room value.** Today's research found DFHack
   exposes **no numeric room value anywhere**: a full key scan of
   `dfhack.buildings` found only `getRoomDescription`, which returns a
   quality word or empty. So a check cannot compare a number against
   `required_office=1` directly. Work out what the strongest available proxy
   is, and be exact about what it does and does not prove. An empty
   description on a zone that should be a room is strong evidence the room
   is not counting; a non-empty one is evidence it is. **Do not invent a
   numeric value.** If the honest answer is "met / not met / cannot tell",
   return three states, and make `cannot tell` distinguishable from `not
   met`, per this project's read-failure discipline.

3. **Make an empty room description loud where it matters.** `zone.place`
   already reads it back. A zone of a kind that requires contents, placed
   with nothing in it, should say so in its own return value rather than
   leaving a null for a human to misread. Per-kind expectations belong in
   data, not branches.

## Scope

Yours: `scripts/dfhack/df-overseer-nobles.lua`,
`scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml`, the
matching `dfmcp` schema if a new command needs registering, the role
allowlists in `agents/*/tools.yaml` for any new read (a new tool absent from
every allowlist is unreachable, `docs/AGENT-ARCHITECTURE.md` principle 8), and
tests. New reads go to the advisors read-only; no new write verbs.

Not yours: `conductor/**`, `doctrine/**`, `dfqueue/**`, any other `.lua`, and
per the `handoffs/` rule `Working.md`, `decisions/DECISIONS.md`, `memory/`
and `handoffs/INDEX.md`. Collect owed register lines in your Result section.

## Rules

- **Offline only.** The fort is paused with a confirmed quicksave and stays
  that way. If you believe a live read is needed, stop and say so in the
  Result rather than taking it.
- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green with numbers quoted: ambient `python -m pytest` (baseline
  **1398 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`, not `py -3`.
- A pcall-guarded read that returns a default is indistinguishable from a
  genuine negative: use the `read_failures` plus `dfhack.printerr` pattern.
- Keep output coordinate-free and never render a map.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

Given a position code, this project can say which of that position's
requirements are met, which are not, and which cannot be determined, with the
numbers read from the game rather than from this brief. Running it against
`MANAGER` on this fort must report the office requirement as unmet or
undeterminable, never as met. The Result names the live check a deploy should
run, and states plainly what the check still cannot see.

## Result

(to be filled by the stream)
