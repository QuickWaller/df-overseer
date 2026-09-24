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

(to be filled by the executor)
