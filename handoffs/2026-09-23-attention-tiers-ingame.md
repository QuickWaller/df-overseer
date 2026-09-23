# Stream: the in-game half of the attention system (tiers, the fifth tripwire, theft, the ledger)

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
"agreed", to building the attention system and the stalled-order poller.
**Offline code and tests only. No deploy, no VM, no unpausing.** A sibling
stream (`handoffs/2026-09-23-stalled-order-poller.md`) owns everything under
`conductor/`; you own the in-game side. Sonnet executor, worktree-isolated.
**No push. No attribution lines in any commit.** No em dashes.

## Why

Today's research settled what should stop the fort and what should merely be
written down. Read these first:

- `research/2026-09-23-wildlife-threat-classes.md`: a kea carries only the
  curious-beast tags, no LARGE_PREDATOR, no BUILDINGDESTROYER, and is not an
  invader, so it must never pause the fort at any distance. Recommends three
  tiers and an observation ledger that never pauses or wakes anything.
- `research/2026-09-23-announcement-severity.md` and
  `research/data/2026-09-23-announcement-severity.yaml`: all 357 announcement
  types levelled (pause 25, slow 23, notice 139, log only 93, ignore 77),
  validated by the orchestrator as complete and exact against the live list.
- `evals/live/2026-09-23-office-and-first-real-build/`: the run a kea 68 tiles
  away ended after 900 ticks.

## What to do

1. **Three tiers in `scripts/dfhack/df-overseer-clock.lua`**, replacing "any
   reachable candidate pauses". Follow the researcher's rule as written:
   **pause** for a large predator, a building destroyer, or a confirmed
   invader or marauder that has actually reached the citizens' walkable
   network; **slow** for a theft-tagged creature closing in, or an invader
   visible but not yet reachable, waking the Overseer; **record only** for
   anything else, including a kea. Read the tags per candidate, the same cheap
   reads `df-overseer-threat.lua` already makes. Put the tier table in data,
   not in branches, so the next creature class is one entry.
2. **The fifth tripwire: announcements.** Fire on a newly arrived report whose
   type is one of the 25 `pause` ids, held as a literal table in the same
   shape `df-overseer-diff.lua`'s `REPORT_CATEGORY` already uses, generated
   from the YAML rather than hand-copied, with the generator committed. It is
   a **separate** tripwire, not folded into the hostile one. The 23 `slow` ids
   are not yours to act on: expose them so the sibling conductor stream can
   route them, and record the agreed field shape in your Result.
3. **Theft is currently invisible.** `CREATURE_STEALS_OBJECT` is not in
   `df-overseer-diff.lua`'s report categories, so a kea actually taking
   something never reaches us. Add it, and any sibling ids the YAML marks
   `notice` or higher that the table omits. Say which you added and why.
4. **The observation ledger.** A small store keyed by creature race plus
   outcome, not per unit, aggregating in place: sighting count, last seen
   tick, closest approach, outcome counts. Presence-only rows decay on a
   window; a row recording a theft or a kill graduates to the permanent record
   instead of decaying. **Hard rule: the ledger's write path never pauses and
   never wakes.** It is only ever read. Provide a read verb and grant it to
   the roles that should see it.
5. **The death tripwire listens too widely.** It uses the raw `UNIT_DEATH`
   event, which `research/2026-09-16-player-visibility.md` tags omniscient.
   `CITIZEN_DEATH` and `PET_DEATH` are the player-visible channel. Re-point or
   dual-arm it, and say plainly which you did and what changes.
6. **Player visibility applies to every tier and every ledger row.** A rule
   that reacts to something the player could not see is out, whatever it is
   called. State how you checked.
7. Tests, including: a kea-shaped candidate does not pause; a large predator
   that has reached the citizens does; an unreachable invader slows rather
   than pauses; the ledger aggregates rather than appends; the ledger's write
   path cannot reach a pause or wake call; the generated pause-id table
   matches the YAML. Both suites green: ambient `python -m pytest` (1281
   passed / 3 skipped before you) and `.venv-dfmcp/Scripts/python -m pytest
   dfmcp/tests` (652 before). Report the new counts.

## Hard lines

- **Offline only.** No ssh, no VM, no deploy, no live DFHack call, no
  unpausing. The fort is paused and stays paused.
- **Do not touch `conductor/`**: the sibling stream owns it.
- No model call. No armok capability, nothing a player could not know, no map,
  coordinate-free output.
- Tripwires run on a tick timer: no unbounded scan (`docs/TRAPS.md`).
- Secrets by key only, never printed. Never print an IP or hostname.
- Do not write `Working.md`, `decisions/` or `memory/`.
- Commit as you go and fill in the Result section.

## Touched surfaces

`scripts/dfhack/df-overseer-{clock,diff,threat}.lua`, a new ledger module and
its generator, `TOOLS.yaml`, the matching dfmcp schema and role allowlists,
tests under `tests/` and `dfmcp/tests/`, this doc.

## Result

(executor fills in)
