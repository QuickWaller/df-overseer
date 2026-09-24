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

(to be filled by the executor)
