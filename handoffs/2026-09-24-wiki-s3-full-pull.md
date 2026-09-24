# Handoff: wiki mirror S3, the full pull and its CLI

Date: 2026-09-24. **Offline build. No deploy, no VM change, no fort change, and NO live
pull.** Tests use S1's fake transport. You may make at most 10 hand requests to the
public wiki API to check a response shape, at least a second apart, with the project
User-Agent and `DFWIKI_UA_CONTACT` unset (the contactless default is for tests and
probes only).

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` (sections 3, 4.7, 5.1, 6, 8, 9, 10 and **13**),
`research/2026-09-24-wiki-mirror-feasibility.md`, the merged `wikimirror/` package
(`api.py`, `schema.py`, `store.py`, `text.py`, `template_policy.yaml`) and the Result
sections of `handoffs/2026-09-24-wiki-s1-client-store.md` and
`handoffs/2026-09-24-wiki-s2-text-stage.md` (the exact interfaces you call).

## What to build

Files you own, and only these: `wikimirror/pull.py`, `wikimirror/__main__.py`,
`wikimirror/tests/test_pull.py`.

- `pull.py`: the full pull, section 5.1. Enumerate the allow-listed namespaces
  (`namespaces.yaml`, main namespace only in v1), fetch revisions in batches of 50,
  run every page through `text.extract_page`, write into a **staged** database file
  with `Store.apply_revision(..., baseline=True)` (the baseline is visible immediately,
  section 13), verify, then `promote_staged` atomically. On any failure the live file is
  untouched. Record the game version from `wiki_current_version()` (a version bump is a
  deliberate re-pull into a new file, never automatic, section 4.7). Resume-safe: an
  interrupted pull can restart or be discarded without a half-written live database.
- **The adapter** between S2's `Chunk` (`index`, `section_path` tuple, `part`, `parts`,
  `text`, `degraded`, `degraded_reasons`) and S1's `store.Chunk(heading_path: str, text)`.
  The schema has no per-chunk `degraded` column and you may not edit `schema.py` or
  `store.py`. So: join the section path with the separator the design names, and fold
  every degraded reason and every `unlisted_templates` count into the **pull report**
  (top 25 unlisted templates by count, degraded reasons by count, pages with a
  `section_text_lost` chunk listed) written next to the database. Silent loss is not
  allowed: the report is how a human sees what the text stage could not handle.
- `__main__.py`: `python -m wikimirror pull [--dry-run] [--out PATH] [--budget N]` and
  `python -m wikimirror status [--db PATH]`. **A non-dry-run pull refuses to start unless
  `DFWIKI_UA_CONTACT` is set** (the user-approved politeness rule); `--dry-run` enumerates
  and reports what it would fetch, using at most the enumeration requests, and writes
  nothing. `status` prints game version, page count, baseline time, last refresh, held
  change count and staleness from the store's own read helpers, and exits non-zero if the
  database is missing or unreadable (never an empty "ok").
- `tests/test_pull.py`: an end-to-end pull over a small fake wiki (a dozen pages
  including a redirect, a page with a transclusion, a hostile page, a deleted title in a
  batch), asserting the baseline is visible, chunks have paths, the report lists the
  degraded and unlisted counts, an injected failure mid-pull leaves the live file
  untouched, a second interrupted pull can be resumed or discarded, and the UA-contact
  refusal. Show one mutation of each guard failing (promote skipped, contact check
  removed).

## Scope

Yours: the three files above. Not yours: everything else in `wikimirror/`, `dfmcp/**`,
`doctrine/**`, `scripts/**`, `agents/**`, and per the `handoffs/` rule `Working.md`,
`decisions/DECISIONS.md`, `memory/`, `handoffs/INDEX.md`. S4, S5 and S6 run in parallel
and own their own files; do not touch them.

## Rules

`git merge --ff-only main` first. Baselines: ambient `python -m pytest` **1681 passed, 3
skipped** with lupa on PYTHONPATH (a scratch `pip install --target`; without lupa the
lupa-based tests are skipped). `dfmcp/tests` in `.venv-dfmcp` **652 passed**. Also run
`python -m pytest tests/test_no_leaked_addresses.py`. Silent degradation is the enemy
(`docs/TRAPS.md`). Commit as you go. No em dashes in prose. No attribution lines. Stop on
any refusal and never route around one.

## Done means

The pull code, its CLI and the report exist and are proven on the fake wiki; the Result
states the exact command for the first real pull, its expected request count (about 110
per the research), what is verified only against canned responses, and what the first real
pull must check. The real pull itself is **gated on the user's go-ahead** and is not run.

## Result

(to be filled by the executor)
