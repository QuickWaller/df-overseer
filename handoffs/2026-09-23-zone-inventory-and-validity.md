# Handoff: nothing can list the zones that exist, or say which of them are valid

Date: 2026-09-23. **Offline. No VM, no deploy, no fort mutation, no unpause.**
The deploy needs its own go-ahead and the orchestrating session will ask
separately.

Read `CLAUDE.md` first, then `research/2026-09-23-room-and-zone-requirements.md`,
the `rooms` entries in `doctrine/seed.yaml`, `scripts/dfhack/df-overseer-zone.lua`,
and the `nobles.requirements` verb added earlier today in
`scripts/dfhack/df-overseer-nobles.lua` (its three-state met / not_met /
cannot_tell discipline is the pattern to follow, not to reinvent).

## How this was found, which matters for how you fix it

The Architect was given a real task today: give the Manager a working office.
It was deliberately told nothing about why the previous attempt failed. It
worked out the mechanism unaided and correctly, and then stated as fact:

> "there is no Office zone anywhere"

There are two. Ids 10 and 11, both Office, both owned, confirmed by dropping
to raw Lua because **no tool in this project can enumerate existing zones**.
It reached "none" from `landmarks.list`, which does not list zones, because
that is the closest thing it had.

That is not a model failure. `zone` today offers `list-kinds` (what kinds can
be placed), `find` (candidate empty areas), `check-owner` and `place`. Nothing
answers "what zones exist right now", so every role is structurally blind to
the fort's own rooms.

The same run found a second defect, in its own words:

> "`zone.find` for Office only returns empty rectangles (it rejects occupied
> tiles, which is where the chair sits); a bare empty office would have no
> chair to work at and a room value of 0"

A room needs furniture inside its footprint to have any value. `zone.find`
structurally cannot propose such a site, so a room sited from its output is
reliably worthless. That is how this fort ended up with two empty offices.

## What to build

### 1. An inventory of the zones that exist

A read that answers "what zones does this fort have". **Design it for fifty
bedrooms, not for two offices**, because that is where this fort is going and
a tool that returns fifty rows of detail is a tool nobody can use:

- **Filters**, so a caller can ask a narrow question: by kind, by owner
  (including unowned), by validity (below), and by proximity to a named
  landmark. Filters compose.
- **Summarise by default, detail on request.** An unfiltered call should
  return counts per kind plus the entries that need attention, not every
  zone. State your chosen default and defend it.
- **Identity without coordinates.** A caller must be able to refer to one
  specific bedroom out of fifty in a later call, while
  `docs/PURPOSE.md` commitment 1 forbids coordinates. The zone's own id is an
  opaque identifier and is already the precedent (`order."ID".exists`,
  `landmark."NAME"`). Nearest-landmark plus a stable ordinal is the other
  candidate. Pick one, say why, and make it stable across calls.
- **Bounded.** One pass over the civzone list, never a tile scan.

### 2. A validity check over zones

The user's framing: a way to confirm which zones are actually valid. Per zone,
answer whether it is doing its job, in the same three states
`nobles.requirements` uses, with `cannot_tell` never collapsed into a failure:

- A zone of a kind with a `room_value_field` whose `getRoomDescription` reads
  empty is **not valid**: it is a rectangle, not a room. This is the exact
  condition that went unnoticed on this fort for two days.
- An `owner_capable` kind with no owner is worth reporting as its own state,
  distinct from invalid.
- A failed read is `cannot_tell`, with `read_failures` and `dfhack.printerr`,
  per the established discipline.

This wants to work fleet-wide in one call: "which of my rooms are not really
rooms" is the question, and at fifty bedrooms it is the only way anyone will
ever notice.

### 3. Let `find` site a room around furniture that already exists

`zone.find` must be able to propose a footprint that **contains** qualifying
furniture rather than rejecting every occupied tile. Decide the interface: a
mode or flag, or a separate verb, and justify it. Two properties matter:

- For a kind with a `room_value_field`, a site containing no qualifying
  furniture should be reported as such rather than returned as if it were
  fine. The caller may still want it (they may intend to build furniture
  after), so inform, do not refuse.
- Per-kind knowledge of what furniture qualifies belongs in data, not in
  branches. The existing `ZONE_POLICY` table is the natural home.

**Do not hardcode the office case.** A bedroom needs a bed, a dining room a
table, a tomb a coffin. One table, one code path.

## Scope

Yours: `scripts/dfhack/df-overseer-zone.lua`, `scripts/dfhack/TOOLS.yaml`, the
`dfmcp` schema for any new command, read-only grants in `agents/*/tools.yaml`
(a tool in no allowlist is unreachable, principle 8), and tests. No new write
verbs; `zone.place` keeps its current single-writer position.

Not yours: `df-overseer-nobles.lua` (just changed, and its
`nobles.requirements` is the consumer of this work, not part of it),
`conductor/**`, `doctrine/**`, any other `.lua`, and per the `handoffs/` rule
`Working.md`, `decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`.

## Rules

- **Offline only.** The fort is paused with a confirmed quicksave and stays
  that way. The live fort has exactly two zones, both Office, ids 10 and 11,
  both owned, both empty of furniture, with the fort's only Chair outside both
  footprints. That is your worked example; you may not read it live.
- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green with numbers quoted: ambient `python -m pytest` (baseline
  **1398 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`, not `py -3`.
- Keep every output coordinate-free and never render or reconstruct a map.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

A role can ask what zones exist, narrow that question by kind, owner,
validity and landmark, refer to one specific zone afterwards without a
coordinate, and be told which zones are not really rooms. `zone.find` can
propose a site around furniture that already exists. Every answer scales to
fifty bedrooms without flooding the caller. The Result names the live checks a
deploy should run, starting with this fort's two known-invalid Office zones.

## Result

(to be filled by the stream)
