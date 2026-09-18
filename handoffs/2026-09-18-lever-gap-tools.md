# Handoff: close the two worst lever gaps (bucket order, stockpile read)

Date: 2026-09-18. Stream 1 of 3 from the production-model design pass.
**Read `docs/PRODUCTION-MODEL.md` first**, especially §13 (the lever
catalogue), §12 (water) and §8 (stockpile occupancy). That file is the spec;
this handoff is scope and sequence only.

## Why this stream exists

The design produces ten named diagnoses and only four of them have a tool
that can act on the fix. This stream converts two of the six dead ones into
live ones. One of them is not theoretical: **a citizen of Uniboslan is
unconscious right now, the fort owns no bucket, and a "Give water" job was
cancelled for want of one** (announcement id 104, tick 214135). No existing
tool can make a bucket.

## Deliverable 1: `orders.create` learns more jobs

`scripts/dfhack/df-overseer-orders.lua` currently accepts
`blocks/mechanisms/barrels/brew_drink` only. Add at minimum **`bucket`**, and
while you are in there add the other jobs this fort plausibly needs soon:
`bed`, `door`, `table`, `chair`, `splint`, `crutch`, `soap`. Use your
judgement on the exact set; justify what you add and what you leave out in
the handoff write-up.

- Follow the file's own existing pattern for job construction. Do not invent a
  second mechanism alongside it.
- `DRY_RUN` defaults to `true`, as every write tool here does. Keep that.
- The `manager_appointed` field is reported on every call and is not enforced
  as a refusal. Leave that behaviour alone; it is a deliberate decision
  (`decisions/DECISIONS.md`).
- Verify each new job actually constructs a valid `manager_order` on the live
  install via **dry run**, and report what the dry run returned per job. A job
  name that silently produces a malformed order is the failure mode to catch.

## Deliverable 2: a stockpile read tool

New file `scripts/dfhack/df-overseer-stockpile.lua`, read-only, two commands:

**`stockpile list`** — every stockpile with: its id, a landmark-relative name,
**occupied tiles over total tiles** (see below), and what it accepts at a
coarse level.

**`stockpile links ID`** — the give/take links for one stockpile or workshop,
from `building_stockpilest.links.{give,take}_{to,from}_{pile,workshop}` and
`building.profile.links`. The live audit confirmed these are exact and that
Uniboslan's two stockpiles are entirely unlinked (all four vectors 0).

**Report occupied tiles over total tiles, NOT percentage of capacity.**
Per-tile capacity depends on what container sits there, and that figure is not
established anywhere (see `research/2026-09-18-production-figures.md`).
Claiming "% full" with an unknown denominator is exactly the false precision
this project forbids. If you cannot read tile occupancy exactly, say so and
report what you *can* read, rather than substituting an estimate.

This is one of the very few **leading** indicators in the whole design: a
stockpile at 80% and rising predicts a backed-up workshop before it happens.
That is why it is worth a tool of its own.

## Rules that apply to both

- **`knowledge_scope` is mandatory** in `TOOLS.yaml` for every command
  (`player_visible` / `player_derivable`; `omniscient` is refused at load
  time). Stockpile contents and links are player-visible. Do not report
  anything from a hidden tile: reuse `df-overseer-stocks.lua`'s
  `is_on_hidden_tile` check rather than reinventing it.
- **Never return a coordinate.** Landmark names, ids and counts only. This is
  the project's hardest commitment (`docs/PURPOSE.md` #1).
- Register both in `scripts/dfhack/TOOLS.yaml` and add allowlist entries:
  `stockpile.*` reads to architect, overseer and quartermaster; the new
  `orders.create` jobs need no new allowlist entry, but update the existing
  entry's note. Update the pinned role counts in `dfmcp/tests/test_roles.py`
  if they change.
- Deploy to VM 103 when the code is verified: `git -c core.autocrlf=false
  archive` (this workstation's `autocrlf=true` otherwise ships CRLF and breaks
  hash checks). Restart `dfmcp-server.service` and confirm the new commands
  resolve live.
- **The fort must stay paused.** Check `dfhack.world.ReadPauseState()` before
  and after and report both. Dry runs only: **do not create a real order, do
  not build anything, do not unpause.** The live fort action is a separate
  stream that runs after yours.
- Ambient `python -m pytest` is 306 passed / 1 skipped before you start. Run
  `dfmcp/tests` in `.venv-dfmcp` too. Report both counts before and after.
- Read secrets by the key you need: `grep -E '^KEY=' .env`, never `cat .env`.
- If a harness, hook or classifier refuses you, **stop and report it.** Do not
  reword the command to get past it.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. The orchestrating session owns those.
- No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-orders.lua`,
`scripts/dfhack/df-overseer-stockpile.lua` (new),
`scripts/dfhack/TOOLS.yaml`, `agents/*/tools.yaml`, `dfmcp/tests/`, VM 103
deploy, this handoff doc.

## Done means

Both tools deployed and live-resolving on VM 103, every new order job dry-run
verified individually, stockpile list and links returning real values for
Uniboslan's two stockpiles, tests green, fort still paused at the tick you
started from, and a write-up at the bottom of this file saying what you
verified and how.
