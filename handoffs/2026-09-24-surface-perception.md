# Handoff: the Architect cannot see a wall, a finished surface, or a traffic designation

Date: 2026-09-24. **Offline build. No deploy, no fort mutation, no unpause.**
Bounded read-only live queries are allowed and expected for verification. The
deploy needs its own go-ahead.

Read `CLAUDE.md` first, then `research/2026-09-24-room-layout-best-practices.md`
(the 13-rule candidate table), `research/2026-09-23-room-and-zone-requirements.md`,
`scripts/dfhack/df-overseer-diggable.lua` (especially its KNOWLEDGE-SCOPE FIX
and ACT/SENSE FIX header blocks, which bind this work), and
`scripts/dfhack/df-overseer-zone.lua`'s new `zone.list`.

## Why

An audit of the Architect's 39 read grants against the fort-design standards
agreed with the user found it blind to nearly all of them. It cannot see a
wall as a wall, so **enclosure is unanswerable**. It cannot see whether a
surface is smoothed or engraved, so **the user's standard that every room is
at least smoothed is invisible**. It cannot read a traffic designation, so
**the whole hallway hierarchy is both unreadable and unsettable**. Material it
can only get incidentally, through `diggable.find`'s candidate search.

This is the perception layer. Without it, no layout checker or planner above
it can evaluate anything, and the Architect keeps proposing against standards
it cannot measure.

## Bindings you must respect

- **The act/sense rule** (`decisions/DECISIONS.md` 2026-09-16, and
  `df-overseer-diggable.lua`'s own header): an agent may designate a dig into
  unrevealed ground, but **may not know an unrevealed tile's material or
  state**. Every read here is subject to that. A hidden tile is reported as
  unknown, never as its true value, and never silently as a default.
- **Never render or reconstruct a map** (`docs/PURPOSE.md` commitment 1).
  Report properties and counts, never a grid, never a per-tile dump a caller
  could reassemble into one.
- **Bounded always.** Never scan the map. The flood research's one-off
  6,856,704-tile sweep is exactly what must not become a tool. Anchor reads on
  a zone id or a bounded region and cap them.
- A pcall-guarded read returning a default is indistinguishable from a real
  negative: use `read_failures` plus `dfhack.printerr`, the established
  pattern.

## What to build

Prefer **question-level verbs over raw tile reads.** A caller wants "is zone
11 enclosed and are its surfaces finished", not a list of tiles it must
interpret. Anchor on the zone ids `zone.list` now exposes.

1. **Enclosure, per zone.** Is this zone's footprint enclosed, and if not, how
   badly: a count of boundary gaps, and whether a gap is a doorway, an open
   floor edge, or a missing wall. Bounded to the zone's own footprint plus its
   boundary ring. Report the three-state discipline (`nobles.requirements`
   established it): enclosed, not enclosed, cannot tell.
2. **Finished surfaces, per zone.** How many of the zone's floor tiles and
   boundary wall tiles are smooth, engraved, rough natural, or constructed.
   This is what makes the user's "every room at least smoothed, or walls
   built" standard checkable. Counts and fractions, never a tile list.
3. **Material, per zone boundary.** What the boundary is made of, at the
   granularity the game exposes (stone, soil, mineral, constructed and so on),
   because it decides whether a wall can be smoothed or must be built.
4. **Traffic designations, read only.** What traffic classes are set over a
   bounded region or a zone. **Read only in this stream**: designating traffic
   is an action and belongs with the stage 3 work, not here. Report the
   counts per class. Note that this fort currently has none set anywhere, so
   expect a uniform answer and make sure that reads as "none set" rather than
   as an error.

## A question to settle while you are in there

**Can soil be smoothed in 53.16?** This project has been assuming not, and a
design rule rests on it ("smooth where stone, construct a wall where soil").
The install's own tiletype data should answer it: look for whether soil wall
tiletypes have a smooth variant at all. Settle it from game data if you can,
and say plainly if you cannot. This is worth more than any single verb here.

## Scope

Yours: a new `scripts/dfhack/df-overseer-*.lua` for this (name it for what it
reads, not for the office case), `scripts/dfhack/TOOLS.yaml`, the `dfmcp`
schema for the new commands, read-only grants in `agents/*/tools.yaml` (a tool
in no allowlist is unreachable, principle 8), and tests.

Not yours: `df-overseer-zone.lua`, `df-overseer-nobles.lua`,
`df-overseer-diggable.lua` (read its header, do not edit it), `conductor/**`,
`doctrine/**`, and per the `handoffs/` rule `Working.md`,
`decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`. Collect owed
register lines in your Result.

## Rules

- **Live reads are read-only and bounded.** The fort is paused at
  `abs_tick 12611557` with a confirmed quicksave and must stay paused.
  Quote every command and its output. Its two Office zones (ids 10 and 11,
  both empty, both `room_value_status: not_met`) are your worked examples.
- Use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM command. Do not write
  your own ssh wrapper and do not read an address out of `.env`.
- **Do not deploy.** Test against the installed scripts only by reading; if
  you need your new script on the VM to test it, stop and say so rather than
  installing it.
- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green, numbers quoted: ambient `python -m pytest` (baseline
  **1413 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (**652**).
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal.

## Done means

Given a zone id, this project can answer whether it is enclosed, how much of
its surface is finished and by which means, what its boundary is made of, and
what traffic classes cover it, with unknowns reported as unknown and nothing
reconstructable into a map. The soil-smoothing question is settled or
explicitly declared unsettled. The Result names the live checks a deploy
should run against zones 10 and 11.

## Result

(to be filled by the stream)
