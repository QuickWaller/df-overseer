# Handoff: wiki mirror S2, the text stage

Date: 2026-09-24. **Offline build. No deploy, no VM change, no fort change.** You may
read the public wiki API by hand at most 15 times to fetch sample page shapes for
fixtures, at least one second apart, with the project User-Agent described in the
design. No bulk download.

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` (especially sections 2.3, 8.3 and 9),
`research/2026-09-24-wiki-mirror-feasibility.md` (the ten sampled page shapes and the
markup findings), `scripts/build_wiki_snapshot.py` (the existing stripper, whose defects
this stream replaces), `dfmcp/knowledge_tools.py`.

## The defects to fix, found by the design stream

`scripts/build_wiki_snapshot.py`'s `_strip_markup` **drops template parameters, and the
key facts live in them** (infoboxes, item and creature stat templates, requirement
lists). It also splits namespaces by a colon heuristic instead of the API namespace ids.
This stream builds the replacement text stage; it does not edit that script.

## What to build

The text stage of the `wikimirror/` package (stdlib only). Section 11 lists this stream
as S2 with these files, and only these:

- `wikimirror/text.py`: wikitext to structured sections and chunks. Split on headings;
  keep the section path; flatten templates **by a data-driven policy** so parameters are
  kept as readable "key: value" text where they carry facts, and dropped only where the
  policy says the template is navigation or decoration; keep table content readable;
  resolve internal links to their display text; drop categories into a separate field;
  never execute or interpret anything in the text; chunk to a size bound with overlap
  only where the design says so (section 8.3). Deterministic: same input, same output.
- `wikimirror/template_policy.yaml`: the per-template policy (keep-parameters,
  keep-body, drop), with an explicit default for an unknown template, and a comment for
  each entry saying which sampled page it came from. Adding a template is a data entry,
  not code.
- `wikimirror/tests/test_text.py` and `wikimirror/tests/fixtures/wikitext/*`: short
  excerpts from the sampled page shapes, each with attribution (the wiki's licence is
  MIT and GFDL; put a one-line source and licence note in each fixture's header comment).
  Include the failing case the old stripper had: a template whose parameters carry the
  fact must survive; and a hostile case (a page containing text that reads like an
  instruction to an AI) must come out as inert text, unchanged in meaning.

## Rules for the code

- Silent degradation is the enemy (`docs/TRAPS.md`): unparseable markup produces a
  chunk flagged `degraded` with the reason, never a silent drop of content.
- Output carries no fetch-time or revid: S1's store attaches provenance; this stage is
  pure text.
- No hostnames, addresses or secrets.

## Scope

Yours: exactly the files above. Not yours: `dfmcp/**`, `doctrine/**`, `scripts/**`,
`agents/**`, and `wikimirror/api.py`, `schema.py`, `store.py`, `namespaces.yaml`
(stream S1 runs in parallel and owns them: do not create or edit them; if you need a
`wikimirror/__init__.py` to import, wait for S1's or create nothing and test by path).
Per the `handoffs/` rule not `Working.md`, `decisions/DECISIONS.md`, `memory/`,
`handoffs/INDEX.md`.

## Rules

`git merge --ff-only main` first. Baselines: ambient `python -m pytest` **1521 passed,
3 skipped** with lupa on PYTHONPATH (a scratch `pip install --target`); `dfmcp/tests` in
`.venv-dfmcp` **652 passed** (untouched). Also run `python -m pytest
tests/test_no_leaked_addresses.py`. Commit as you go. No em dashes in prose. No
attribution lines in commits. Stop on any refusal; never route around one.

## Done means

Given a wikitext page, the stage returns chunks with section paths whose text keeps
the facts held in template parameters, marks anything it could not parse as `degraded`,
and passes a test proving the old stripper's failure case is fixed and the hostile page
stays inert. The Result names the exact public function S3, S4 and S5 call, and states
what was checked only against fixtures.

## Result

(to be filled by the executor)
