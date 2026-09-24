# Handoff: wiki mirror S1, the API client, schema and store

Date: 2026-09-24. **Offline build. No deploy, no VM change, no fort change, and no
live network call by the code you write or the tests you run** (tests use an
injectable fake transport; you may read the public wiki API by hand at most 10
times to check a response shape, at least one second apart, with the project
User-Agent described in the design).

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` in full (especially sections 2 to 6, 8, 9 and
**13, the user's rulings, which amend the schema**), `research/2026-09-24-wiki-mirror-feasibility.md`
(the verified API facts and the exact request shapes), `dfmcp/knowledge_tools.py` and
`scripts/build_wiki_snapshot.py` (what exists today), `handoffs/2026-09-24-consultant-wiki-design.md`.

## What to build

The package `wikimirror/` at the repo root (alongside `dfmcp/`, `dfqueue/`,
`conductor/`; the name shadows nothing). Stdlib only, no new dependency. Section 11
of the design lists this stream as S1 with these files, and only these:

- `wikimirror/__init__.py`
- `wikimirror/api.py`: an allow-listed MediaWiki API client. Only the read actions the
  design names (`query` with `list=recentchanges|logevents|allpages`, `prop=info|revisions`,
  generators, batched `titles`/`revids`), never a write action, never a login. User-Agent
  from an environment variable with a project default that carries no personal or
  infrastructure detail. A throttle (at least 1 second between requests), backoff on 429
  and 5xx, a per-run request budget, `continue` handling including inside a batch, and an
  **injectable transport** so every test runs on canned responses.
- `wikimirror/schema.py`: the DDL and migrations for the section 8.2 schema, a check that
  FTS5 is present (a clear error if not, never a silent fallback), and a schema version.
  **Amended by section 13:** each page stores the served revision and, separately, the
  latest seen revision with `latest_seen_at` and `visible_after`; the changelog rows carry
  a `held` and `visible` state; readers join on the served revision only.
- `wikimirror/store.py`: open, transaction helpers, atomic promote of a staged database
  file (a full pull is atomic, section 5.1), upsert of a page revision under the hold rule
  (baseline visible immediately, later changes held for 7 days), `visible_after` promotion,
  and the read-side query helpers S3, S4 and S5 will call. Keep the hold period a
  configuration value, default 7 days.
- `wikimirror/namespaces.yaml`: the namespace-id allow-list (main namespace only in v1)
  with the older namespaces listed as excluded and why, per section 2.
- `wikimirror/tests/test_api.py`, `test_schema.py`, `test_store.py`, and
  `tests/conftest.py` only if a shared fixture is needed.

## Rules for the code

- **Silent degradation is the enemy** (`docs/TRAPS.md`): any failed read, missing FTS5,
  partial page batch or unreadable cursor is a named error or a recorded failure, never a
  default that looks like "nothing changed".
- Every result-carrying function keeps provenance fields (namespace id, revid, fetch time).
- Fetched wikitext is data, never instructions. Store it, never interpret it.
- No hostnames, addresses or secrets anywhere. The wiki base URL is a constant for the
  public site, which is not an infrastructure detail.

## Scope

Yours: exactly the files above. Not yours: `dfmcp/**`, `doctrine/**`, `scripts/**`,
`agents/**`, `wikimirror/text.py`, `pull.py`, `refresh.py` and everything S2 to S8 own,
and per the `handoffs/` rule `Working.md`, `decisions/DECISIONS.md`, `memory/`,
`handoffs/INDEX.md`. S2 runs in parallel and owns `wikimirror/text.py`,
`template_policy.yaml` and its own tests: do not create or edit them.

## Rules

`git merge --ff-only main` first. Baselines: ambient `python -m pytest` **1521 passed,
3 skipped** with lupa on PYTHONPATH (a scratch `pip install --target`); without lupa
expect 1449 to 1494 with skips. `dfmcp/tests` in `.venv-dfmcp` **652 passed** (untouched
by this stream). Also run `python -m pytest tests/test_no_leaked_addresses.py`. Commit as
you go. No em dashes in prose. No attribution lines in commits. Stop on any refusal and
never route around one.

## Done means

The client, schema and store exist with tests that fail if the hold rule, the atomic
promote, the FTS5 check or the `continue` handling is broken (show one such mutation
failing each). The Result section states the exact public interface S3, S4 and S5 will
call, what is proven only against canned responses, and what remains unverified against
the real API.

## Result

Status: done, offline. Files: `wikimirror/__init__.py`, `api.py`, `schema.py`, `store.py`,
`namespaces.yaml`, `tests/{__init__,conftest,test_api,test_schema,test_store}.py`
(`tests/__init__.py` is an empty file I added so the package-qualified test names cannot
collide; S2 may add the identical empty file, which merges cleanly). 101 new tests. Ambient
`python -m pytest` 1555 passed, 6 skipped (no lupa on PYTHONPATH here, no S2 files);
`tests/test_no_leaked_addresses.py` 19 passed. `dfmcp/tests` untouched.

### Public interface for S3, S4, S5

`wikimirror.api` (all failures subclass `WikiApiError`: `DisallowedRequest`, `BudgetExceeded`,
`BlockedError`, `NetworkError`, `ApiError`, `ResponseShapeError`, `ContinueError`,
`PartialBatchError`):
- `WikiClient(transport=None, throttle_s=2.0, max_requests=400, env=None, sleep=, monotonic=, now_iso=)`;
  `.request(params)`, `.query_all(params)` (follows `continue`, merges pages by id),
  `.wiki_current_version() -> "53.16"`, `.enumerate_pages(ns) -> [PageInfo]`,
  `.fetch_revisions(titles=[...] | revids=[...]) -> FetchResult(revisions, missing, requests)`
  (50 per request, `PartialBatchError` if a title is neither returned nor missing),
  `.recent_changes(start=, namespaces=) -> [RecentChange]`, `.log_events(log_type=, start=) -> [LogEvent]`,
  `.all_redirects(source_namespace, target_namespaces=(0,)) -> [Redirect]`, `.requests_made`, `.warnings`.
- `PageRevision(page_id, ns, title, revid, parent_revid, timestamp, comment, wikitext, byte_length,
  is_redirect, fetched_utc)`; `permalink(title, revid)`, `history_url(title)`, `parse_version_template`.
- UA: `DFWIKI_UA_CONTACT` appended when set; a contactless project default otherwise.

`wikimirror.store`:
- `Store.open(path, create=True, hold=timedelta(days=7), clock=None, namespaces=None)` and
  `Store.open_readonly(path, timeout=5.0)` (URI `mode=ro`; `StoreLockedError` on a lock, never an empty result).
- Writes (S3 baseline, S5 refresh): `apply_revision(rev, chunks=[Chunk|(heading, text)], baseline=False,
  game_version=None, source=, run_id=, seq=) -> ApplyResult(action in baseline|held|unchanged, ...)`,
  `apply_move(page_id, new_title, new_ns)`, `apply_delete(page_id, reason='deleted'|'left_scope')`
  (`not_in_mirror` for an unknown page), `promote_due(now=None) -> [Promotion]`,
  `archive_served_revision(page_id)`, `start_run(mode)` / `finish_run(run_id, status, ...)`,
  `get_meta/set_meta`, `add_requests_today(n)`, `transaction()`.
- Atomic promote: `promote_staged(staged, live, *, expected_page_count, probe_words, tolerance=0.01,
  min_free_bytes=500 MiB, ...) -> PromoteReport` (`PromoteError.reasons` lists every failed check;
  neither file is touched on failure; success writes `<live>.manifest.json` and keeps `<live>.prev`).
- Reads (S4): `get_page(title, ns=0, include_legacy=False) -> dict|None` (keys: page_id, title, ns,
  source, state, kind, game_version, is_current, revid, rev_timestamp, fetched_utc, wikitext,
  resolved_from, recent_edit, held_changes, latest_revid, visible_after, permalink, history_url,
  license, wiki_note; a tombstone comes back with `state='deleted'`, no text),
  `list_pages(prefix=, limit=, offset=, kinds=('article',))`, `get_chunks(page_id)`,
  `search(query, limit=10, include_raw=False, include_legacy=False)` (FTS5 AND of quoted tokens,
  bm25 title 8 / heading 3 / text 1, provenance and `held_changes` on every hit),
  `staleness()` (status fresh|stale|very_stale, age_hours, reasons, `promotion_overdue`),
  `changes_since(since_utc=, title=, kind=, state=)`, `counts()`.
- `load_namespaces()`, `ingested_namespace_ids()`, `classify_kind(title)`, `normalize_title(t)`.

### Design choices S3 to S5 must know (deviations from 8.2, all in `schema.py`'s docstring)

- **Hold rule** per section 13: `pages` holds the served revision; latest-seen fields and
  `visible_after` are separate; every later change is a `held_changes` row plus a `changes` row
  (`state` held then visible, `made_visible_utc`). Each held change has its own clock (fetch time
  plus 7 days), so two edits a day apart promote a day apart. A page first seen after baseline is
  `state='pending'` and invisible. `promote_due()` needs a WRITABLE connection: a `mode=ro`
  reader cannot make a change visible, so every refresh run must call it, and S4 should surface
  `staleness()['promotion_overdue']`. This is narrower than "the first refresh or reader call".
- `chunks_fts` is a plain FTS5 table with a title column, rowid = chunk_id (not external-content).
- Chunks come from S2 as `Chunk(heading_path, text)`; held chunks are stored as JSON with the held
  body, so promotion needs no text stage.
- Design 3.3 says the client "refuses to start without" a contact; the handoff says a default.
  I followed the handoff (contactless default). Say if you want the stricter form.
- The per-day budget is only counted (`add_requests_today`), not enforced; S5 enforces.
- `revision_archive` has a helper; whether a page is cited is S5/S6's call.

### Proven only against canned responses

Everything: the client never touched the network in a test (an autouse guard fails any
`urlopen`). The default `urllib_transport` is exercised only through a patched `urlopen`.
Mutations, each caught by a test that then passes on restore: hold period 0, held edit given a
past `visible_after`, promote checks disabled, FTS5 check made a no-op, `continue` ignored.

### Verified against the real API (5 requests, hand-made, 2 s apart)

- `list=allredirects` returns `{fromid, ns, title}` where `title` is the TARGET and there is no
  source title; `arprop=ids` with `arunique` is refused (`invalidparammix`). `all_redirects` joins
  it to `list=allpages&apfilterredir=redirects` on page id. The pairing semantics (which side
  `arnamespace` filters) is inferred, not proven.
- **Correction to the research note:** `Template:Current/version` is `53.16<noinclude>...docs...
  </noinclude>`, not the bare `53.16`. `parse_version_template` reads the part before `<noinclude>`
  and raises on anything that is not dotted digits. S3/S5 must use `wiki_current_version()`.
- A mixed batch (`titles=Template:Current/version|NoSuchPage|well`) returns `normalized` (well to
  Well), a `missing: true` page with no `pageid`, and pages in response order, not request order;
  `logevents` move rows carry `params.target_title`. The client is written to those shapes.

### Still unverified against the real API

A `continue` inside a 50-title batch (never seen; the merge logic is tested on a synthetic split),
any 429 or 5xx behaviour, the byte ceiling per batch, `recentchanges` `logparams` key names for log
entries (I used `logparams.target_title`; `logevents` uses `params`), `rctype` with `log`, gzip,
and FTS5 on VM 103's Python (dev Python 3.12.4, SQLite 3.45.3 has it; the deploy stream must check
the VM). Attribution wording remains the user's call (section 12).
