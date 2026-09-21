# Handoff: extract the reactions the graph extractor never read

Date: 2026-09-21. **Offline build stream** (worktree, Sonnet). One read-only
copy of raw files from VM 103 into the scratchpad; no live game, no fort
change, no deploy.

Read `CLAUDE.md`, `docs/PRODUCTION-MODEL.md` (the extraction sections),
`production/extract.py`, and the "What remains unknown" section of
`handoffs/2026-09-21-graph-labor-for-jobs.md` (item 2 and item 6), then this.

## Why

`production/extract.py` reads only four reaction files
(`DEFAULT_REACTION_FILES`: `reaction_other`, `reaction_adv_carpenter`,
`reaction_dyes`, `reaction_smelter`). The game lists 293 reactions; the labor
ingest found **145 the extractor never read** (instrument and craft reactions,
`MAKE_ENT...` and similar, from other raw files). Until they are extracted,
Craftsdwarfs (104 reactions), Metalsmith's Forge and Magma Forge (15 each),
Leatherworks (6), the glass furnaces (13 each) and 7 Kiln reactions cannot be
resolved by `labors_for_kind`, so those kinds stay `unknown` for a reason that
is only missing input.

## Deliverables

1. **Find which raw files hold the 145.** Read-only copy of the install's
   reaction raw files (`raw/objects/reaction_*.txt` under the DF install, read
   over SSH as `df`, into the scratchpad, **never committed**: game data, public
   repo). Name every file the extractor does not read and how many reactions
   each holds; check the total against the graph report's 145.
2. **Extend the extractor** so it reads them, with the same discipline as the
   existing four: consumption rule checked, nothing fabricated, an unparsable
   reaction reported and counted rather than skipped silently. Extend
   `DEFAULT_REACTION_FILES` or replace it with discovery of every
   `reaction_*.txt`; say which and why.
3. **Reconcile with `production/labor_ingest.py`.** It currently adds a process
   row for each reaction the game lists that the extractor missed (source_ref
   starting `dump:`). After this change those reactions come from the extractor
   instead. The ingest must stay idempotent and must not double-count or
   duplicate a process. Re-run the ingest on a real extraction plus the real
   dump (path in `handoffs/2026-09-21-graph-labor-for-jobs.md`, out of tree) and
   report the **before and after coverage table** (known / partial / unknown
   per kind, and determined versus undetermined processes; before: 2 / 18 / 13
   and 129 of 366).
4. **Fixtures.** Add a filtered verbatim subset of the newly covered real
   reactions as a test fixture with a `PROVENANCE.md`, as the graph stream did.
   The old `reaction_*.txt` fixtures disagree with the real raws (graph report
   item 6); do not build on them.

## Rules

- You own `production/**` and this doc only. Do not touch `dfmcp/**`,
  `scripts/dfhack/**`, `agents/**`, `gotchas/**`, `docs/PRODUCTION-MODEL.md`
  (report what needs correcting instead).
- Unknown is never zero; a labor is determined only from the game's own tables.
- Read secrets by key only; no address, hostname or token in any tracked file.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. **Commit after each milestone** and extend this doc's
  report as you go. No em dashes in prose. Use the Write tool for scratch
  scripts rather than long inline shell heredocs.

## Done means

The extractor reads every reaction file, the 145 are accounted for (extracted,
or named with a reason), the ingest is idempotent with no duplicates, the
before and after coverage table is in this doc, and the suite passes (report
before and after; ambient baseline is 762 passed / 2 skipped, and
`dfmcp/tests` in `.venv-dfmcp` 430 passed).
