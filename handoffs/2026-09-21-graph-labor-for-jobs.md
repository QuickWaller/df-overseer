# Handoff: the production graph learns which labor operates each workshop

Date: 2026-09-21. **WRITTEN for review, not dispatched; waits on the Lua
stream's data dump.** Offline build stream, no VM.

Read `CLAUDE.md`, `docs/BUILDING-TOOL.md` (decisions and contract C2),
`docs/PRODUCTION-MODEL.md` sections 3 and 4, then `production/schema.py`,
`production/extract.py` and `production/store.py`, then this.

## Why this stream exists

The user decided operating labor comes from the graph: a workshop's labors are
the labors of the processes it hosts (`production_process.workshop_node` and
`.labor`). Reactions carry their workshop and labor in the raws, but
**hardcoded job types** (`is_hardcoded=1`) do not, and those are where the
gaps and the STONECUTTER-versus-MASON disagreement are. The Lua stream
produces a bounded dump from the live game (job type to skill to labor, and
which jobs each workshop hosts); this stream ingests it.

## Deliverables

1. **Ingest the dump** (path given in the dispatch prompt; it stays out of the
   repo) into `production_process` rows for hardcoded jobs, with
   `workshop_node` and `labor` where known and **null with a stated reason
   where not**. Add whatever `source_ref` scheme is needed. Commit a
   **fixture** of a small, hand-verified subset only.
2. **`production/labors.py`** (new): `labors_for_kind(db_path, kind_token)`
   exactly per **contract C2**. `known` only when every process the kind hosts
   has a determined labor; `partial` if some are null; `unknown` if the kind is
   absent or nothing is determined, each with a reason.
3. **Reconcile the mason's workshop**: report what the data says about
   ConstructBlocks and the workshop's other jobs, and the effect on the
   answer.
4. **A coverage table** in the write-up: kinds by status, and how many
   hardcoded jobs have a null labor and why. An honest table matters more than
   green tests.

## Rules that bite here

- Nothing may be presented as verified that came from a guess. An unresolvable
  labor stays null; never fill with a default.
- Extraction is idempotent and must not erase observations (see the fix in
  `production.store`).
- Do not touch `dfmcp/**`, `scripts/dfhack/**`, `gotchas/**` or
  `docs/BUILDING-TOOL.md`. Do not write `Working.md`,
  `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. **Commit after
  each milestone.** No em dashes.

## Touched surfaces

`production/**` and this doc.

## Done means

`labors_for_kind` matches C2 on real dump data, the fixture tests pass, the
coverage table is written, the suite passes (**552 passed / 1 skipped**,
report before and after), and the mason's-workshop question has an answer or
an honest "unresolved, and why".
