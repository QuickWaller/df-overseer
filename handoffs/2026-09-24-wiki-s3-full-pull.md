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

(filled by the executor, 2026-09-24)

Status: done, offline. Files (all mine): `wikimirror/pull.py`, `wikimirror/__main__.py`,
`wikimirror/tests/test_pull.py` (26 tests). No network was touched: no hand requests were
made at all, and a real pull was not run.

### What it does

- `full_pull(client, out, env=, resume=, discard_staged=, probe_words=, max_missing=, ...)`:
  refuses without `DFWIKI_UA_CONTACT` (before any request or file), reads the version once via
  `wiki_current_version()` (`meta.game_version`), enumerates every ns in
  `ingested_namespace_ids` (ns 0 today), fetches in batches of 50, runs each page through
  `text.extract_page`, writes `<out>.staged` with `apply_revision(..., baseline=True)` (one
  transaction per batch), fills the `redirects` table from `all_redirects`, sets meta
  (`game_version`, `baseline_utc`, `last_full_pull_utc`, `license`, `source`,
  `namespaces_ingested`, `pull_requests`, `pull_state`), then `promote_staged` with
  `expected_page_count = enumerated - missing` and probe words `dwarf`, `water`, `stone`.
  Any raise leaves `out` and its manifest and `.prev` byte-identical (tested by hash).
- **Adapter:** `adapt_chunks` joins `section_path` with `" > "` (an empty path becomes
  "Introduction"). Per-chunk `degraded` flags, reasons and `unlisted_templates` go to the
  report `<out>.pull-report.json`: top 25 unlisted templates by count plus distinct and total,
  degraded reasons by count for chunks and for pages, every page with `section_text_lost`,
  pages with no chunks, pages whose text is a redirect, text-stage exceptions, missing titles,
  pages whose revid moved between enumeration and fetch, dangling and unresolved redirects,
  client warnings. A text-stage exception (should never happen) stores a one-line fallback
  chunk and is listed, never swallowed.
- **Resume or discard:** a failed pull leaves `<out>.staged`. The next pull refuses
  (`StagedExists`) unless `--resume` (re-enumerate, skip pages already staged at the enumerated
  revid, refetch the rest; refuses if the wiki version changed) or `--discard-staged`. On resume
  the report statistics are recomputed from the stored wikitext, so a resumed pull's text-stage
  report equals an uninterrupted one (tested). A staged file that failed verification stays
  resumable too.
- **Missing pages:** a title enumerated but missing at fetch is named in the report. More than
  `max(2, 1% of enumerated)` missing fails the pull before promote. Every enumerated page must be
  stored or named missing, or the pull fails.
- A pull is not a refresh: `start_run`/`finish_run` set `last_refresh_*`, and I reset those two
  meta keys to NULL after `finish_run('ok')`, so `status` shows no last refresh and
  `staleness()` reasons come only from `last_full_pull_utc`. S5 should read `last_full_pull_utc`
  as the baseline time.

### CLI

`python -m wikimirror pull [--dry-run] [--out PATH] [--budget N] [--resume | --discard-staged]`
and `python -m wikimirror status [--db PATH]`; `--out` and `--db` fall back to `DFWIKI_DB`.
Exit 0 ok, 1 failure (named error printed, "live database untouched"), 2 refusal or usage
(no contact, staged exists, no path). `--dry-run` needs no contact, uses only the enumeration
requests (about 9 on the real wiki), prints a projected request count, writes nothing. `status`
uses `Store.open_readonly`, `counts()` and `staleness()`; it exits 1 for a missing file, an
unreadable file, or a database that opens but has no baseline (never an empty ok). Default
budget 800 (the design's full-pull budget).

### Verified (real runs)

- `python -m pytest wikimirror/tests/test_pull.py`: 26 passed. Whole `wikimirror` plus
  `tests/test_no_leaked_addresses.py`: 205 passed. Ambient `python -m pytest`, no lupa on the
  path: **1640 passed, 6 skipped** (the 6 are the lupa-based tests). `dfmcp/tests` not run
  (untouched).
- Mutations, each restored afterwards:
  1. contact check disabled: `test_real_pull_refuses_without_contact` and
     `test_cli_pull_refuses_without_contact` fail.
  2. promote replaced by a plain file copy: 4 fail (baseline test, mid-pull failure leaves live
     untouched, failed verification does not promote, re-pull keeps `.prev`).
  3. staging removed (staged path = live path): 17 fail, but only because the swap collides with
     itself; treat that one as "caught loudly", not as a precise guard test.
- The fake-wiki tests cover: a redirect (resolves via `get_page`), a page with unlisted
  transclusions (counts 2 and 1 asserted), a hostile page (kept as literal text), a deleted
  title in a batch (named; 11 of 12 stored), a colon title in ns 0 (stays current), a `/raw`
  page (kind raw, not searchable), response order differing from request order, a 132-page pull
  (request count exactly 1 version + 1 enumeration + 3 fetch + 2 redirect), a mid-pull outage
  (live hash unchanged, staged kept), resume (only the rest refetched) and discard, a version
  change refused on resume, too many missing, a bad probe word, a real re-pull keeping `.prev`.

### The first real pull (gated on the user's go-ahead; NOT run)

```
DFWIKI_UA_CONTACT=<contact url or address> python -m wikimirror pull --dry-run     # about 9 requests, writes nothing
DFWIKI_UA_CONTACT=<contact url or address> python -m wikimirror pull --out <live db path>
python -m wikimirror status --db <live db path>
```

Expected requests: **about 110** (1 version, about 9 enumeration, about 89 fetch batches for
roughly 4,450 non-redirect pages, plus the redirect join: one allpages redirect list and one
allredirects list, each paging at 500 rows, so several more for the real redirect count). At the
client's 2 s spacing that is under 4 minutes plus text-stage CPU. If interrupted, rerun with
`--resume` (or `--discard-staged`).

### Verified only against canned responses

All of it. The fake wiki answers only the shapes S1 recorded. Not exercised live: a `continue`
inside enumeration or inside a 50-title batch, 429 or 5xx during a long pull, the byte size of a
50-page batch, the redirect join pairing (S1 inferred it, not proven), and FTS5 plus `VACUUM`
timing on a 16 MB corpus and on VM 103's SQLite.

### What the first real pull must check

1. Enumeration count is near 4,450 (nonredirects) and the dry run matches it.
2. The pull report: `missing_titles` small, `text_stage_failures` empty, the size of
   `unlisted_templates_top` (the long tail S2 predicted; feed the top entries back into
   `template_policy.yaml`), `section_text_lost_pages`, `degraded_reasons_*`, and
   `pages_whose_text_is_a_redirect`.
3. `redirects.total` (design 4.6 unknown), `unresolved_target_count`, `target_not_in_mirror_count`.
4. `promote_staged` passes with the default probe words on the real corpus; time taken by its
   VACUUM and integrity check; `status` shows 53.16, the page count, baseline time, `held_changes` 0.
5. The redirect join pairing: spot-check three redirects by title.
6. Raw and `/script` subpage counts against the research (1,574 `/raw`).
7. `revid_moved_during_pull` (edits landing during the pull; expect a handful at most).

### Notes for S4, S5, S6

- Meta keys written by the pull: `game_version`, `baseline_utc`, `last_full_pull_utc`, `license`,
  `source`, `namespaces_ingested`, `pull_requests`, `pull_state` (`verified` after a good pull).
- The `redirects` table has `from_page_id` NULL (the API join gives no source page id).
- Design 3.3 says the client refuses to start without a contact: enforced here for the pull CLI
  and `full_pull`, still only a default inside `WikiClient` itself.
