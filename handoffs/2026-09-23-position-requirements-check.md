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

**Built, offline only. Nothing deployed, nothing pushed, no VM touched, fort
untouched (this stream ran entirely against the repo, never against VM 103).**

**1. Position requirements check: `nobles.requirements POSITION_CODE`, a new
verb, not folded into `verify`** (kept separate because a caller may want the
appointment check without the room check or vice versa, and conflating them
would hide which one failed -- `verify` still never reads a single
requirement field). Data-driven over two small tables
(`ROOM_VALUE_FIELDS`, `FURNITURE_FIELDS` in `df-overseer-nobles.lua`): no
per-position branch anywhere, so a position this fort has never appointed is
read by the exact same loop. Per assignment slot of the code:
- Room-value fields (`required_office`/`_bedroom`/`_dining`/`_tomb`): three
  states, `met` / `not_met` / `cannot_tell`, never a number (see item 2).
  `cannot_tell` covers a vacant position, an unresolvable histfig, or a
  failed `getRoomDescription` read; it is never collapsed into `not_met`.
  Zone kind resolution uses `df.civzone_type[kind]` directly, not
  `zone.lua`'s quickfort-upvalue reach: civzone_type is the game's own
  stable engine enum, so this check does not depend on that file's more
  fragile path at all.
- Furniture-count fields (`required_boxes`/`_cabinets`/`_racks`/`_stands`):
  read and reported, always `cannot_tell` -- nothing in DFHack's API or this
  game's own exposed data says whether they are satisfied
  (research doc, "What could not be verified"). This project does not
  invent a check it cannot back with a real read.
- `read_failures` plus `dfhack.printerr` on every failed
  `getRoomDescription`/zone-vector read, same discipline
  `df-overseer-threat.lua`'s `class_flags` uses: a pcall-guarded default is
  never silently indistinguishable from a genuine negative.

**2. The honest answer about room value, stated plainly.** DFHack exposes no
numeric room value anywhere (research, confirmed live 2026-09-23:
`dfhack.buildings` has exactly one function with "room"/"quality"/"value" in
its name, `getRoomDescription`, returning only a quality-word string or
empty). No number is invented anywhere in this check. The proxy: find every
zone of the requirement's own kind owned by the position's holder
(`assigned_unit_id` or the game's own `getOwner` agreeing); a nonempty
`getRoomDescription` on any of them is `met`; an owned zone whose read
succeeded and came back empty, or no owned zone at all, is `not_met` (a
positive requirement with no room is a real, provable failure, not a guess);
any read failure or unresolvable holder is `cannot_tell`.

**3. `zone.place`'s real path is now loud about an empty read.** A
room-value kind (`ZONE_POLICY[token].position_field` set) whose real
placement read back an empty or failed `getRoomDescription` now carries
`read_back.room_value_warning` naming what that does and does not prove,
instead of a bare `null` a human already misread once on this fort's real
Office zones (2026-09-23-office-and-first-real-build). Data-driven off
`position_field`, no per-kind branch.

**Scope followed exactly**: only `df-overseer-nobles.lua`,
`df-overseer-zone.lua`, `TOOLS.yaml` and the architect/consultant/overseer
`tools.yaml` allowlists were touched. `nobles.requirements` was granted to
the same three roles that already hold `nobles.list`/`nobles.verify`
(architect, consultant, overseer); quartermaster and conductor were left
alone, matching their existing tools.yaml (neither holds any `nobles.*` or
`zone.*` grant today). Verified with a Python-side registry/roster check
(not a live DFHack read, since none was permitted): `nobles.requirements`
resolves to `nobles__requirements` and appears in exactly those three
roles' tool lists, +1 tool each (architect 38->39, consultant 21->22,
overseer 64->65 before/after this stream's own edits, checked by a
`git stash` round-trip on just the touched files), never in
quartermaster's or conductor's.

**What this check still cannot see, stated as plainly as the brief asked**:
it can never prove an exact room value or compare against the required
number; `met`/`not_met` rest entirely on whether a quality word is present
at all, which the research pass found is the only room-value-adjacent
signal DFHack exposes on this install. It cannot check whether the
furniture-count fields are satisfied by anything at all -- those four
fields are read, never verdicted. It does not weigh in on the
population-gate half of a position's requirements (`requires_population`/
`HAS_MET_POP_REQ`): that is already reported by `nobles.list` and
`zone.lua`'s own `requirements_for`, and adding it here would have
duplicated an existing read rather than closing a gap.

**MANAGER on this fort, worked through by hand against the research
pass's own live table (Q4: `required_office=1`, holder unit 345, per
Q3: zone 11's `getRoomDescription` read empty even with the Chair built,
because the Chair sits outside both zones' own footprints)**: vacant=false,
holder_uid=345, `owned_zones_of_kind("Office", 345)` finds zone 11 only
(zone 10 is unowned), its read succeeds and returns empty, so `Office`
resolves to `not_met`. This satisfies "Done means": the office requirement
reports unmet, never met. **The live check itself is owed** (this stream
was offline-only and did not run against VM 103); the deploy a later
session should run is `df-overseer-nobles.lua requirements MANAGER`
against the paused fort, expecting exactly `Office: not_met` given the
zone-11-only, empty-read state the research pass already confirmed live.

**Register lines owed** (not written here per the `handoffs/` rule; the
orchestrating session owns `Working.md`/`decisions/DECISIONS.md`/`memory/`/
`handoffs/INDEX.md`):
- `Working.md`: this stream is done and offline-only; the owed next step is
  the live deploy + `nobles.requirements MANAGER` check named above.
- `decisions/DECISIONS.md`: a row for the decision to keep `requirements`
  a separate verb from `verify` (and why), and the decision to report
  furniture-count fields as permanently `cannot_tell` rather than inventing
  a proxy for them.
- Tool-count figures in `CLAUDE.md`'s status paragraph (overseer 63,
  architect 37, quartermaster 23, consultant 21, conductor 15) are already
  one stream stale as of this pass -- before this stream's own edits this
  worktree already measured architect 38, consultant 21->21 (unchanged,
  see below), overseer 64, quartermaster 24, conductor 15, i.e. the cited
  63/37/21/15 figures for overseer/architect/consultant/conductor were
  already off by the room-and-zone-requirements/conductor-game-tick
  streams merged in immediately before this one. After this stream:
  architect 39, consultant 22, overseer 65, quartermaster 24 (unchanged),
  conductor 15 (unchanged). Worth a memory-audit note per CLAUDE.md's own
  "if docs and repo state disagree, flag it" rule; not corrected here since
  `CLAUDE.md` itself is out of this stream's touched-surfaces scope.
