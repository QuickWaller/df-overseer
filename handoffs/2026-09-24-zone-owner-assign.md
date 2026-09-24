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

(to be filled by the executor)
