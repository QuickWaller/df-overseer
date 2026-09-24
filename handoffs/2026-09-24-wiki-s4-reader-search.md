# Handoff: wiki mirror S4, the reader and the search tool

Date: 2026-09-24. **Offline build. No deploy, no VM change, no fort change, no network.**

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` (sections 2.3, 5.2, 8, 9 and **13**),
`dfmcp/knowledge_tools.py` in full (its `knowledge.wiki_lookup` contract and the existing
snapshot path; **its existing tests must pass unchanged**), `dfmcp/tests/test_knowledge_tools.py`,
`agents/consultant/tools.yaml`, `agents/consultant/role.md`, `agents/consultant/sites.yaml`,
`dfmcp/roles.py`, and `wikimirror/store.py`'s read helpers and the Result section of
`handoffs/2026-09-24-wiki-s1-client-store.md`.

## What to build

Files you own, and only these: `dfmcp/wiki_reader.py` (new), `dfmcp/knowledge_tools.py`
(**the wiki section only**), `dfmcp/tests/test_wiki_reader.py` (new file; do **not** edit
`test_knowledge_tools.py`), `agents/consultant/tools.yaml`, `agents/consultant/role.md`,
`agents/consultant/sites.yaml`, and the roster tool-count tests that change.

- `wiki_reader.py`: opens the SQLite mirror read-only (`Store.open_readonly`), never writes.
  Functions for exact lookup, redirect resolution, and ranked full-text search
  (`store.search`), returning the result contract of section 8.4: page title, namespace,
  game version, `revid`, fetch time, permalink, licence, the **staleness label** of section
  5.2 computed from timestamps at read time (never a stored flag), `held_changes` (section
  13: the count of pending changes not yet served), a `recent_edit` marker, and an
  "OLD GAME" line on any legacy-namespace page. A tombstone (deleted page) says so. A locked or
  unreadable database is a named error, never an empty "the wiki has nothing on this";
  surface `staleness()['promotion_overdue']` from S1. Chunk text is entity-decoded by the text
  stage, so **escape it on output** and wrap it as data (fetched text is data, never
  instructions).
- `knowledge_tools.py`: `knowledge.wiki_lookup` keeps its exact current contract; when the
  configured path ends in `.sqlite3` it dispatches to the reader, otherwise to the existing
  JSON snapshot (additive fields only). Add `knowledge.wiki_search` (query, optional
  namespace and limit, bounded). Leave `knowledge.wiki_changes` to S7.
- `agents/consultant/tools.yaml`: grant `knowledge.wiki_search`; update `role.md` and
  `sites.yaml` so the Consultant knows to prefer the local mirror, read the staleness and
  version fields, treat an OLD GAME or held-change flag as a reason to hedge, and fall back
  to live fetch only when the mirror lacks a page.
- Update the Consultant tool count in the tests that pin counts; report the new figure for
  `CLAUDE.md` (the orchestrator edits that file).
- `test_wiki_reader.py`: build a small mirror with `wikimirror.store` and `text` in a temp
  dir; test lookup, redirect, search ranking, staleness bands, held-change count, tombstone,
  legacy label, escaping of `<`/`>` and of instruction-shaped text, the locked-database error,
  and that `wiki_lookup` on a `.json` snapshot path is unchanged.

## Scope

Yours: the files above. Not yours: everything else in `wikimirror/` (S1, S2 merged; S3 and S5
run in parallel), `doctrine/**`, `dfmcp/doctrine_tools.py` (S7), `scripts/**`, other roles'
allowlists, and per the `handoffs/` rule `Working.md`, `decisions/DECISIONS.md`, `memory/`,
`handoffs/INDEX.md`.

## Rules

`git merge --ff-only main` first. Baselines: ambient `python -m pytest` **1681 passed, 3
skipped** with lupa on PYTHONPATH; `dfmcp/tests` in `.venv-dfmcp` **652 passed** (your
new tests add to it; `test_knowledge_tools.py` unchanged and green). Run
`tests/test_no_leaked_addresses.py`. Silent degradation is the enemy. Commit as you go. No em
dashes. No attribution lines. Stop on any refusal; never route around one.

## Done means

With a mirror file present the Consultant's `wiki_lookup` and `wiki_search` return
provenance-labelled, staleness-labelled, escaped results; with none configured behaviour is
exactly as before. The Result states the new Consultant tool count and the live check a
deploy should run.

## Result

(to be filled by the executor)
