# Handoff: a generic `nobles` tool, and one live test of appointing a Manager

Date: 2026-09-21. **WRITTEN for review, not dispatched.** Live stream: **writes
to the fort on VM 103** (one appointment and one short supervised unpause),
after a quicksave. Never runs at the same time as another stream on VM 103 (see
Sequencing).

Read `CLAUDE.md` (especially "Tools must be generalisable"), `Working.md`
START HERE item 6 (the appointment finding), `docs/TRAPS.md` (the unbounded
query rule and quicksave rule, in full), `research/2026-09-18-work-orders.md`
and the register rows of 2026-09-19 on stalled manager orders, then
`scripts/dfhack/df-overseer-workjob.lua` (the pattern for a dry-run-by-default
write tool), then this.

## Why this stream exists

Manager orders never become jobs on this fort because **no citizen holds the
MANAGER position** (register 2026-09-19). DFHack has no named tool for
appointing, but its own scripts show the mechanism, and a read of the paused
fort (2026-09-21, tick 103055) shows the slot exists and is vacant:

- The fortress entity (id 36) has 12 position assignments: `MANAGER` (assignment
  id 6), `BOOKKEEPER`, `BROKER`, `MAYOR`, `CAPTAIN_OF_THE_GUARD`, `SHERIFF`,
  `MILITIA_COMMANDER`, `CHIEF_MEDICAL_DWARF`, `DUNGEON_MASTER`, `HAMMERER`,
  `CHAMPION` and `EXPEDITION_LEADER`. Only the expedition leader is held
  (histfig 323, unit 198).
- `hack/scripts/make-monarch.lua` appoints by finding the position's assignment in
  `entity.positions.assignments`, setting `assignment.histfig` to the new holder's
  historical figure id, erasing the old holder's `histfig_entity_link_positionst`,
  and inserting a new one (`entity_id`, `link_strength=100`, `assignment_id`,
  `assignment_vector_idx`, `start_year`) into the new holder's `entity_links`.
- `hack/scripts/internal/emigration/unit-link-utils.lua` shows the removal side:
  it clears `histfig` and `histfig2`, replaces the position link with a
  `histfig_entity_link_former_positionst`, and **writes a
  `history_event_remove_hf_entity_linkst`**. The monarch script writes no event.

This is what a player does on the Nobles screen, so it is fair under the armok
rule (`docs/ARMOK-RULINGS.md`). The gap is a tool, and whether it works.

## Deliverables

1. **`scripts/dfhack/df-overseer-nobles.lua`** (new), **generalised over the
   position code**, never manager-only:
   - `list`: for the fortress entity, every position with its code, name,
     assignment id, current holder (unit id) or vacant, and whatever the
     position data says about how it is filled (elected or appointed, any
     population requirement). Read-only. Coordinate-free. A field that cannot
     be read is `null` plus an error, **never a default**.
   - `appoint POSITION_CODE UNIT_ID [DRY_RUN]` and `unappoint POSITION_CODE
     [DRY_RUN]`, **dry-run by default**. Refuse with a named reason when: the code
     does not exist, the position is already held, the unit is not a living
     citizen of this fort, the unit has no historical figure, the position is
     elected (as the mayor is) or its population requirement is unmet, judged
     **from the position's own data, not a guess**. Inspect the position struct
     with a bounded loop first and report which fields you found and used.
   - Follow the monarch script's mechanism for the write. Build the minimal
     version first. If the live test shows inconsistency, add the history event
     as the emigration helper does, and **report which version the game needed**.
2. **Bounded verification, in this order, all on the paused fort** (every step's
   output quoted in the write-up): a **quicksave first**, confirmed by the save
   slot's modified time, not by the command's return (`quicksave` can act tens of
   seconds late, `research/2026-09-11-quicksave-silent-noop.md`); record tick and
   pause state; `list`; `appoint MANAGER <unit> DRY_RUN`; the real appoint; then
   confirm **from both sides**: the assignment's `histfig` is the unit's figure,
   the figure has the position link, and `dfhack.units.getNoblePositions(unit)`
   returns MANAGER. Choose the citizen by a stated rule (an adult, living, not in
   the military) and say why.
3. **One short supervised unpause** to see the effect: does the manager validate
   any order, does a "manage orders" style job appear, does the game complain
   (for example that an office is needed)? Use the existing safety envelope from
   the earlier supervised runs (a watchdog that re-pauses, a hard tick limit, stop
   at once on any death, alarm or error). Do **not** create new orders; observe the
   ones already queued (`orders list`). Re-pause and confirm state and tick.
4. **Leave the fort as you found it unless the test passed.** If every
   consistency check passed and nothing anomalous happened, leave the manager
   appointed and say so. If anything is inconsistent, `unappoint`, verify, and
   **report before restoring any save**; do not restore without saying so.
5. **A proposed `TOOLS.yaml` entry and allowlist lines**, written into this doc for
   the orchestrator to apply (see Rules). Choose `knowledge_scope` deliberately
   and write down why (the Nobles screen shows positions and holders to a
   player, so `player_derivable` is the likely answer; check `dfmcp/roles.py`).

## Sequencing

**One stream at a time on VM 103 and the fort.** The building-tool Lua stream
(`2026-09-21-building-tool-lua.md`) is read-only on the VM but also owns
`scripts/dfhack/TOOLS.yaml`; **run this one after it, or with the user's
explicit go-ahead to overlap.** This stream does not touch `TOOLS.yaml` for that
reason.

## Rules that bite here

- **Quicksave immediately before any write**, and **never run an unbounded query
  against the live process** (`docs/TRAPS.md`; a wedge on 2026-09-19 cost about
  22,000 ticks). Bound every loop.
- Do **not** touch `scripts/dfhack/TOOLS.yaml`, `agents/*/tools.yaml`, `dfmcp/**`,
  `production/**`, `gotchas/**` or any other tool's script.
- Deploy only the new script to VM 103 with `git -c core.autocrlf=false archive`
  and verify by hash. SSH as `df`. Read secrets by the key, never the whole
  `.env`. No address, hostname or token in any tracked file.
- Stop and report on any classifier refusal; do not route around it.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. **Commit after each milestone** and extend this doc's report
  as you go. No em dashes in prose.

## Touched surfaces

`scripts/dfhack/df-overseer-nobles.lua` (new), this doc; on VM 103, that one
script under `hack/scripts/`, and the fort's game state (one appointment, one
short unpause).

## Done means

The tool lists, dry-runs, appoints and unappoints by position code; every refusal
above is exercised or explained; the appointment is verified from both sides and
through `getNoblePositions`; the write-up says which mechanism version the game
needed, what happened during the unpause, whether an appointed manager validates
orders, and what remains unknown; the fort's final state (paused, tick, who holds
MANAGER) is stated; the suite still passes (**552 passed / 1 skipped**, report
before and after); and a proposed manifest entry is ready for the orchestrator.
