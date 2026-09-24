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

(filled by the executor, 2026-09-24)

**Public function for S3, S4 and S5:**

```python
from wikimirror.text import extract_page
page = extract_page(wikitext, policy=None, max_chunk_chars=2000)   # -> PageText
```

`PageText` (frozen dataclasses, `to_dict()` for JSON): `chunks` (tuple of `Chunk`: `index`,
`section_path` tuple, `part`, `parts`, `text`, `degraded`, `degraded_reasons`), `categories`,
`degraded_reasons` (page union), `unlisted_templates` ({normalised name: count}, for measuring
what to add to the policy), `is_redirect`, `redirect_target`. `load_policy(path)` loads an
alternative policy file; `PolicyError` is raised at load only. `extract_page` never raises on
page content (only `ValueError` for `max_chunk_chars` under 100). Output carries no revid or
fetch time. Text is entity-decoded, so S4 must still escape it when embedding in a prompt.

**Files (all new, all mine):** `wikimirror/text.py`, `wikimirror/template_policy.yaml` (43 entries,
each with a `source:` note naming the sampled page), `wikimirror/tests/test_text.py` (59 tests),
`wikimirror/tests/fixtures/wikitext/*.wikitext` (well, mason, ghost, water_buffalo_raw, dwarf,
aquifer, hostile; each with a source and licence header comment). I created no
`wikimirror/__init__.py`; the test file puts the repo root on `sys.path` and imports
`wikimirror.text` as a namespace package, so it works with or without S1's `__init__.py`.
The old `scripts/build_wiki_snapshot.py` is untouched.

**Behaviour worth knowing:**
- Split on `=`..`======` headings, path kept, lead is "Introduction". Chunks are bounded by
  paragraph, then line and sentence, then whitespace, then a hard cut; no overlap (the design
  asks for none).
- Templates: policy actions `drop`, `keep_body`, `keep_parameters`, `name_only`, `category`,
  with per-entry `label`, `only`/`exclude` (fnmatch), `positional_labels`, `block`. Unknown
  template: default `keep_parameters`, rendered inline as ` [Name: key: value; ...]`
  (parentheses when nested). Depth cap 4 (flagged, text kept).
- Never evaluated: `{{#if:}}`, `{{#invoke:}}`, magic functions and variables, `{{:Page}}`
  transclusions. Each is flagged `degraded` (reason names it) and rendered as plain text where
  honest. A section whose text is entirely lost emits a one-line "(no text could be
  extracted)" chunk flagged `section_text_lost`, never nothing.
- Other degraded reasons: `unbalanced_template_open`, `unbalanced_braces`, `unbalanced_link`,
  `unclosed_table`, `unclosed_comment`, `unclosed_nowiki_tag`/`unclosed_pre_tag`,
  `html_table_flattened`, `link_depth_exceeded`, `template_depth_exceeded:<name>`,
  `no_text_extracted`.
- `<nowiki>` and `<pre>` bodies are stashed and restored literally, unparsed. Control, zero-width
  and bidi characters are stripped; private-use characters in input are stripped so a page
  cannot forge the stash placeholder. Unknown tags (e.g. `<system>`, `</wiki_page>`) stay as
  literal text. HTML comments and `<ref>` are removed (documented policy, not silent loss of
  facts).
- Parsing is linear (single-pass brace and link pair maps): 20,000 unclosed `{{` runs in 10 ms.
  The first draft was quadratic (27 to 83 s on 40 KB of hostile input); found by a fuzz run,
  fixed, and pinned by tests.

**Verified (real runs):**
- `python -m pytest wikimirror/tests/test_text.py`: 59 passed.
- Ambient `python -m pytest` with lupa on PYTHONPATH: **1580 passed, 3 skipped** (baseline 1521
  plus my 59, no regression). Without lupa: 1513 passed, 6 skipped.
- `python -m pytest tests/test_no_leaked_addresses.py`: 19 passed.
- `dfmcp/tests` in `.venv-dfmcp` not re-run (untouched, no dfmcp file changed).
- Ran the stage over the ten real sampled pages (fetched by hand: 2 API requests, well under
  the 15 allowed, project-style User-Agent, no bulk): 9 of 10 clean with zero unlisted
  templates; `Trading` is flagged (its `{{:Trading/Flowchart}}` transclusion cannot be
  expanded here, its section says so). Scratch copies in the session scratchpad, not
  committed. Old-stripper defect proved by test: `_strip_markup` deletes a template with no
  nested template whole, parameters included; the new stage keeps them.
- A 3,000-case seeded random markup fuzz (never raises, deterministic) and six pathological
  inputs (time bound 5 s).

**Checked only against fixtures, not against the whole wiki:** the template policy covers the
templates seen in ten pages; the real main namespace has 1,000+ templates. Expect a long tail
of unlisted templates on the first full pull (they get the default rule and are counted in
`unlisted_templates`), so S3 should aggregate that field and report the top of it. The ratio of
facts kept (research unverified item 3) is unmeasured. `Cavern` and `Engraver` were run for
crashes and cleanliness only, with no fixture assertions. HTML `<table>` markup is flattened
without cell separators (flagged). Nothing about `{{#invoke}}` (Lua modules) beyond being
inert. `PyYAML` is the one non-stdlib import (already used by `dfmcp` and `doctrine`); "stdlib
only" in the design should read "stdlib plus PyYAML".

