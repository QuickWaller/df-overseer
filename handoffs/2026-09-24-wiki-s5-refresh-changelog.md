# Handoff: wiki mirror S5, refresh, changelog and digest

Date: 2026-09-24. **Offline build. No deploy, no VM change, no fort change, and no live
refresh.** Tests use S1's fake transport. At most 10 hand requests to the public wiki API
to check a response shape, at least a second apart.

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` (sections 4, 5, 6, 9 and **13**),
`research/2026-09-24-wiki-mirror-feasibility.md`, the merged `wikimirror/` (`api.py`,
`schema.py`, `store.py`, `text.py`) and the Result sections of
`handoffs/2026-09-24-wiki-s1-client-store.md` and `handoffs/2026-09-24-wiki-s2-text-stage.md`.

## What to build

Files you own, and only these: `wikimirror/refresh.py`, `wikimirror/changelog.py`,
`wikimirror/digest.py`, `wikimirror/tests/test_refresh.py`, `wikimirror/tests/test_changelog.py`.

- `refresh.py`: one refresh run, sections 4.2 to 4.6. Read the cursor from the store, pull
  `recentchanges` and `logevents` (delete, move; anonymous, 500 per request, about 90 days of
  retention) since the cursor, **fold** multiple events per page into one target, fetch only
  the changed revisions, run them through `text.extract_page`, and apply each with
  `Store.apply_revision` (after the baseline every change is **held**, section 13),
  `apply_move`, `apply_delete`. **Every run calls `Store.promote_due()`** (S1: it needs a
  writable connection, so this is where held changes become visible after their week).
  Handle: an edit to a page not in the mirror (in scope or not), a move that changes
  namespace (leaves scope), a delete then restore, an event burst on one page, a cursor older
  than the feed's retention (fall back to the weekly sweep and record it, never silently skip),
  network failure mid-run (the transaction rolls back; the cursor does not advance), and a
  request budget. The weekly `revid` sweep (section 4.4) via `list=allpages&generator/prop=info`
  detects anything the feed missed. Record a `refresh_runs` row with counts and status.
  Aggregate `unlisted_templates` and degraded reasons into the run record.
- `changelog.py`: the immutable JSONL export of the changes table per run (section 6.1):
  added, changed, moved, deleted, with title, old and new `revid`, timestamps, the wiki's own
  edit summary, and the `held` or `visible` state with `visible_after`, and a `visible`
  transition record when a held change is promoted. Append-only; never rewrite a line.
- `digest.py`: the human-readable Markdown digest (section 6.2), listing held changes
  separately from visible ones and flagging a page changed repeatedly in a short window.
- Tests: a fake feed covering the cases above; a network failure leaves the cursor unmoved;
  a held change is invisible to readers until `promote_due` after the hold; a stale cursor
  triggers the sweep; the JSONL is append-only; show one mutation of each guard failing
  (promote not called, cursor advanced on failure, hold skipped).

## Scope

Yours: the five files above. Not yours: everything else in `wikimirror/` (S3 owns `pull.py`
and `__main__.py`; S1 and S2 are merged: if you need a change there, record it in your
Result instead), `dfmcp/**`, `doctrine/**`, `scripts/**`, `agents/**`, and per the `handoffs/`
rule `Working.md`, `decisions/DECISIONS.md`, `memory/`, `handoffs/INDEX.md`. S3, S4 and S6
run in parallel.

## Rules

`git merge --ff-only main` first. Baselines: ambient `python -m pytest` **1681 passed, 3
skipped** with lupa on PYTHONPATH (a scratch `pip install --target`); `dfmcp/tests` in
`.venv-dfmcp` **652 passed**. Run `tests/test_no_leaked_addresses.py`. Silent degradation is
the enemy (`docs/TRAPS.md`). Commit as you go. No em dashes. No attribution lines. Stop on any
refusal; never route around one.

## Done means

A refresh run over the fake feed keeps the mirror correct, holds changes for the week,
records every event in the changelog, and fails loudly and safely. The Result names the exact
command a timer would run, what is proven only on canned responses (notably `logparams`
key names and 429/5xx behaviour, unverified against the real API), and the live check for the
first refresh.

## Result

Status: done, offline. Files (all new, all mine): `wikimirror/refresh.py`,
`wikimirror/changelog.py`, `wikimirror/digest.py`, `wikimirror/tests/test_refresh.py` (39 tests),
`wikimirror/tests/test_changelog.py` (18 tests). Nothing else was edited.

### The command a timer runs

    DFWIKI_UA_CONTACT=<contact url> python -m wikimirror.refresh --db /var/lib/dfwiki/df-wiki.sqlite3 --out /var/lib/dfwiki

Every 6 hours with a random delay of up to 30 minutes (design 4.2). Exit 0 for `ok`, a dry run, or a
run skipped because another holds the lock; exit 1 for `failed` or `blocked`; exit 2 for a refused
start (no `DFWIKI_UA_CONTACT`, database missing). Prints one JSON object (status, run id, counts,
sweep reasons, top 25 unlisted templates, warnings, output paths). `--dry-run` reads the feed and
listing, prints the plan (titles to fetch, deletes) and writes nothing (no run row, no promotion).
`--force-sweep`, `--budget N` (per run, default 400), `--daily-budget N` (default 2000),
`--hold-days N` (default 7, the user's ruling; change deliberately). S3's `__main__.py` can call
`wikimirror.refresh.main(argv)` for a `refresh` subcommand; the module is also runnable directly.

Python: `run_refresh(store, client, RefreshConfig(out_dir=...)) -> RefreshResult` (never raises for a
fetch, store or plan failure; the result and the `refresh_runs` row carry the status; `.ok`).

### Contract with S3 (the pull) and the operator

`meta` keys READ here and not written here: `last_full_pull_utc`, `install_version`. Written here:
`rc_cursor_ts`, `rc_cursor_ids` (JSON list of `rc:<id>` and `log:<id>`), `last_sweep_utc`,
`wiki_current_version`, `version_status` (`current`, `wiki_ahead`, `wiki_behind`, `unknown`),
`last_digest_utc`, `last_run_summary`, `last_lock_skip_utc`. **S3 should set `rc_cursor_ts` (the pull's
start time) and `last_full_pull_utc`; if `rc_cursor_ts` is absent the first refresh runs a sweep
(9 requests) and says `no_cursor`, which is safe.** A mirror with no pages and no
`last_full_pull_utc` fails as `no_baseline`, touching nothing.

### What a run does (as built)

1. Lock: a young `running` row makes the run exit as `locked` (recorded in `last_lock_skip_utc`); a row
   older than 2 hours is broken and named (`stale_lock_broken:<id>`). The lock is the `refresh_runs`
   row, not a lock file.
2. `start_run`, then **`Store.promote_due()` every run, before any network work**, so a dead network
   never freezes the one-week hold. A promotion failure does not stop the fetch but the run ends
   `failed` / `promote_failed`.
3. `wiki_current_version()`, then plan: the feed (`recentchanges` edit|new, `logevents` delete and
   move, from cursor minus 10 minutes, already-seen ids skipped) folded to one target per page in
   time order (edit/new/restore fetch, move fetches the TARGET title, delete deletes, a later edit
   cancels an earlier delete), or a **sweep** (`enumerate_pages` per ingested namespace against the
   store: added, changed, renamed, absent, plus the redirect table). Sweep reasons, all recorded:
   `no_cursor`, `cursor_older_than_60_days` (feed skipped), `no_successful_refresh_for_7_days`,
   `weekly_sweep_due`, `operator_requested`, and feed-driven `move_target_unknown`,
   `delete_unresolved`, `feed_logevents_disagree`.
4. All bodies are fetched before anything is written; the text stage runs; then ONE transaction
   applies deletes, revisions (`apply_revision`, with `apply_move` when the store sees a rename with
   an unchanged revid), the version record, the redirect table and the cursor. Any failure before the
   commit leaves data and cursor untouched. `unlisted_templates` and degraded reasons are aggregated
   into the result, the run header and `meta.last_run_summary`.
5. `finish_run`, changelog JSONL (`--out`/changelog/YYYY/MM/<run_id>.jsonl, exclusive create, no
   overwrite, end record with a count), digest when due (a change, a failure or a warning, or a week
   of quiet; `digest/<date>.md` regenerated for the day, plus `LATEST.md`). If the changelog or digest
   cannot be written the run is re-finished `failed` / `output_failed` (the data stands; regenerate
   with `changelog.export_run(store, run_id, out_dir)`).

### Deviations and choices (also in `refresh.py`'s docstring)

- One transaction per run, not per batch of 50 (stronger: nothing partial). Memory is one run's bodies.
- Redirect table refreshed only by the sweep, immediately and not held. A page turning into a redirect
  is held as a delete (`became_redirect:<title>` warning).
- A body reported missing after an edit or move event is NOT deleted on the spot
  (`missing_after_event:<title>`, `race_missing`); a delete event or the sweep decides.
- A sweep that would hold more deletes than max(25, 2 percent of the mirror) aborts
  (`sweep_implausible`): a truncated listing must not mass-delete.
- A moved page's target namespace is learned by fetching the target (the API returns `ns`), because
  `api.LogEvent` carries only `target_title`. A move out of scope becomes a held `left_scope` delete;
  into scope from outside, an add.
- Version bump: a `changes` row of kind `version_bump` (old and new version in `old_title` and
  `new_title`, title `Template:Current/version`), `version_status` set, first line of the digest.
- Digest window is the UTC day of the run (cumulative per day); held changes are always all listed,
  in their own section; pages with 3 or more changes in 48 hours are flagged (baseline rows excluded);
  full-pull rows are counted, not listed; tables cap at 200 rows.
- Budget: the client's `max_requests` is clamped for the run to the daily headroom (then restored) and
  the day's count is added via `add_requests_today`; `BudgetExceeded` is `failed` / `budget`, a 403 or
  repeated 429 is `blocked`.

### Gaps in S1 that S5 could only name, not fix (recorded, per the scope rule)

1. **A restore of a page whose delete has already been promoted is silently not applicable.**
   `Store.apply_revision` returns `unchanged` when `rev.revid <= latest_revid`, and a restored page
   keeps its old revid, so the mirror keeps the tombstone. The run names it (`restore_not_applied:<title>`
   warning, counted, in the digest) but cannot repair it; a test asserts the warning. Fix in `store.py`:
   skip the revid idempotency test when the stored row is `deleted`.
2. There is no way to cancel a held change. A held delete for a page that then reappears will still
   promote. The refresh avoids creating such holds on guesses (see the race rule above) but not on real
   delete-then-restore across two runs.
3. `api.LogEvent` drops `params.target_ns`, which the real API returns for moves.
4. `Store` has no redirect write method; `refresh.py` writes the `redirects` table with SQL inside its
   own transaction.

### Verified

- `python -m pytest wikimirror/tests/test_refresh.py wikimirror/tests/test_changelog.py`: 57 passed.
- Ambient `python -m pytest` (no lupa on PYTHONPATH here): 1671 passed, 6 skipped (the skips are the
  lupa tests). `tests/test_no_leaked_addresses.py`: 19 passed. `dfmcp/tests` not run (untouched).
- **Mutations, each caught, then restored (`git diff` clean afterwards):** `promote_due` never called
  (caught by the held-then-promoted test); cursor advanced before the fetch (the network-failure test);
  hold skipped, `baseline=True` in the refresh (the held-then-promoted test); stale-cursor sweep
  disabled (the stale-cursor test); the write transaction removed (the rollback test).
- Covered on the fake feed: edit, new page, edit outside scope, burst folded to one fetch, second run
  refetches nothing, move in scope, move out of scope, delete, delete then restore in one window,
  restore after promotion (warning), move with no target (forced sweep), page turned redirect, feed and
  logevents disagreement, stale cursor, no cursor, weekly sweep finding what the feed missed,
  sweep-confirmed delete, implausible sweep, redirect table, network failure then clean re-run, write
  failure rollback, 403 blocked, request budget, daily budget, no baseline, lock and stale lock,
  promotion with the network down, promotion failure, version bump, unlisted and degraded aggregation,
  dry run, hostile edit summary (JSONL one line per record, digest fence longer than any backtick run,
  Markdown escapes), digest due rules, changelog immutability (exclusive create, link race, crash
  while writing, truncation detected, source never opens a file for append), `main` refusals and exit code.
- Hand-made real-API probe, 4 of the 10 allowed requests, 2.5 s apart, project User-Agent: (1)
  `recentchanges` with `rcprop=...|loginfo` returns edit rows as the client expects; log rows carry
  `logid`, `logtype`, `logaction`, `logparams` (verified for `upload` and `newusers`; none of
  delete or move was inside the 8 most recent log rows, so the RC-side `logparams.target_title` for a
  move is still unproven); (2) `logevents` `letype=delete` rows have `pageid: 0` and the real page id in
  `logpage` (the client reads `logpage`: correct); (3) `letype=move` rows carry `logpage` (the moved
  page), `params.target_title` and `params.target_ns`, and their `pageid` is the redirect left behind.

### Proven only on canned responses

`FakeWiki` is my reading of the response shapes. Not proven against the real API: 429 and 5xx
behaviour (the client's own backoff is S1's, tested there); a `continue` inside a 50-title batch;
`recentchanges` `logparams` key names for move and delete rows; whether `restore` events carry the
original page id; `rcstart` accepting `...Z` with an `rcdir=newer` on this wiki (used by the S1 tests
and the design, but no refresh has run); FTS5 and the hold on VM 103's Python; behaviour with thousands
of changed pages in one run (memory, one long write transaction).

### The live check for the first refresh (gated on the user, and after S3's pull exists)

1. `python -m wikimirror.refresh --db <db> --dry-run` (about 6 to 15 requests): read the plan; expect a
   handful of titles and an empty `sweep_absent`.
2. Confirm `meta` holds `last_full_pull_utc`, `rc_cursor_ts` and `install_version` (`python -m wikimirror status`).
3. A real run with `--out`: expect status `ok`, `held_*` counts equal to the plan, served revisions
   UNCHANGED (`get_page` still returns the pull's revid, `held_changes` at least 1), a JSONL with a
   header, `change` lines in state `held` and an `end` line, and a digest whose Held section lists them.
4. Run it again at once: expect zero fetches and no new change rows.
5. Note `warnings` (especially `install_version_unset`, `restore_not_applied`, `missing_after_event`,
   `feed_log_row_not_in_logevents`) and the top unlisted templates in `last_run_summary`.
6. Only then enable the timer. After a week, check a held change became visible and a `visible` record
   appears in that later run's JSONL.

