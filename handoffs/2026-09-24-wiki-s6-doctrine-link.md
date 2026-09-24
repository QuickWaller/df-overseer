# Handoff: wiki mirror S6, the doctrine link

Date: 2026-09-24. **Offline build. No deploy, no VM change, no fort change, no network.**

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` (section 7 and **13**), `doctrine/validate.py`,
`doctrine/seed.yaml` (the header and the provenance fields of a few entries that cite
wiki pages), `doctrine/tests/`, `dfmcp/doctrine_tools.py` (read only: S7 owns it), and the
merged `wikimirror/store.py` read helpers.

## What to build

Files you own, and only these: `doctrine/validate.py`, `doctrine/wiki_check.py` (new), the
**header comment only** of `doctrine/seed.yaml`, `doctrine/tests/test_validate.py`,
`doctrine/tests/test_wiki_check.py` (new).

- **Citation format** (section 7.1): a doctrine source of `kind: wiki` may carry optional
  `revid`, `page_ns` and `page_title`. Update the validator so these are accepted and
  checked when present (`revid` a positive integer, `page_ns` an integer) and never required,
  so no existing entry becomes invalid. Document the fields in the `seed.yaml` header comment
  (do not edit any entry).
- `wiki_check.py`: a pure, read-only check `check_doctrine(doctrine_entries, store_reader) ->
  report` that, for every wiki source with a `revid`, compares it with the mirror's **served**
  revision (never the latest seen, section 13) and reports: unchanged; changed (served revision
  newer); **a newer held revision exists** (so a re-read can be planned before it goes live);
  moved; deleted; legacy-namespace; page missing from the mirror; mirror unavailable or stale
  (report this as `cannot_check`, never as "unchanged"). It never edits doctrine
  (revisions are proposals, section 7.5). It reads the mirror through S1's read-only store
  helpers only. Provide the flag structure S7 will attach at `doctrine.get` time and put in
  the digest.
- **Nothing silently overwritten** (section 7.3): specify and implement the check that a cited
  page's prior body is archived by S1's `archive_served_revision` before a served revision
  changes; here, test that the check reports the cited revision is no longer the served one
  and that its archived body is retrievable.
- Tests: each report state above; an entry with no `revid` is skipped and listed as
  uncited, not as unchanged; a mirror that is missing or unreadable yields `cannot_check`;
  the validator accepts old and new shapes; show one mutation (reading the latest seen instead
  of the served revision) failing.

## Scope

Yours: the files above. Not yours: `dfmcp/**` (S4 and S7), `wikimirror/**` (do not edit; record
any change you need in your Result), `agents/**`, `scripts/**`, any doctrine entry, and per the
`handoffs/` rule `Working.md`, `decisions/DECISIONS.md`, `memory/`, `handoffs/INDEX.md`.
S3, S4 and S5 run in parallel.

## Rules

`git merge --ff-only main` first. Baselines: ambient `python -m pytest` **1681 passed, 3
skipped** with lupa on PYTHONPATH (a scratch `pip install --target`); `dfmcp/tests` in
`.venv-dfmcp` **652 passed**. Run `tests/test_no_leaked_addresses.py`. Silent degradation is
the enemy. Commit as you go. No em dashes. No attribution lines. Stop on any refusal; never
route around one.

## Done means

Doctrine can cite a wiki revision; the check reports, per cited page, whether the served
revision moved, a newer one is held, or the page moved, was deleted or is legacy, and says
`cannot_check` when it cannot tell. The Result gives the exact report structure S7 consumes.

## Result

Built offline; 231 passed (`doctrine`, `wikimirror`, `tests/test_no_leaked_addresses.py`).
`python -m doctrine.validate` on the real `seed.yaml`: ok (no entry edited, header comment only).

**Validator** (`doctrine/validate.py`): `kind: wiki` sources accept optional `revid` (positive
int, bool rejected), `page_ns` (int), `page_title` (non-empty str); the same fields on a
non-wiki source are an error; none required. Section 7.1's "opened should carry revid" warning
and the `describes` vs `game_version` check were left out (handoff: never required); they
belong with the migration slice.

**`doctrine/wiki_check.py`**: `check_doctrine(entries, store_reader)` where `store_reader` is an
open `Store`, a path (opened `open_readonly`, closed after), or None. Also `wiki_flags_for_entry(entry,
reader)` (what S7 attaches as `wiki_flags`), `check_archive`, `read_archived_revision`,
`cited_page_ids` (for S5's "is this page cited" test before `archive_served_revision`), and a CLI
`python -m doctrine.wiki_check --db P [--doctrine P] [--json]` (exit 1 if anything needs re-read
or cannot be checked).

Report, for S7 (also in the module docstring):
`{mirror:{available,reason,freshness:{status,age_hours,reasons,promotion_overdue}|None},
summary:{state:count}, sources:[...], uncited:[{entry_id,source_index,ref,read}],
flags_by_entry:{entry_id:[flag]}, needing_reread:[entry_id]}`.
States: `unchanged, changed, held_newer, moved, deleted, legacy, missing, cannot_check`
(doc 7.2 says `current`/`uncheckable`; this uses the handoff's names). Flag keys: source_index, ref,
title, ns, cited_revid, state, severity (`reread` changed/moved/deleted, `warn` held_newer/legacy/
missing, `info` cannot_check, `note` for a `verified` entry), served_revid, newer_held_revid,
visible_after, moved_to, held_kinds, cited_revision_archived (True/False/None), reason, message.
`unchanged` yields no flag. Compares with the SERVED `revid` from `get_page`, never `latest_revid`.
Choices: a very_stale or never-pulled mirror downgrades `unchanged` to `cannot_check`
(`mirror_very_stale`) but keeps positive findings; a cited revid above the served one is
`cannot_check` (`cited_revision_not_yet_served`); a pending held move/delete shows in
`held_changes`/`held_kinds` while the state stays as served.

**7.3 archive check**: `check_archive` is True only if the cited revision is in `revision_archive`
and its sha256 matches its text; changed/moved/deleted results carry `cited_revision_archived`,
so a refresh that skipped `archive_served_revision` is visible as False.

**Change wanted in `wikimirror/store.py` (not edited)**: no public getter for `revision_archive`;
I SELECT through `store.conn`. Add e.g. `Store.get_archived_revision(page_id, revid)`, then swap
`read_archived_revision`. Also `Store.get_page` on a legacy namespace returns None (no NamespaceNotIngested),
so legacy detection uses `store.namespaces` first.

**Mutation**: `test_reads_the_served_revision_not_the_latest_seen` monkeypatches `_served_revid`
to return `latest_revid`; the state flips from `held_newer` to a false `changed`.
