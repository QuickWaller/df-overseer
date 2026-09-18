# Handoff: run the extractor against the real 159-reaction corpus

Date: 2026-09-19. Offline stream. **No VM, no SSH, no DFHack, no fort.** The
raws have already been pulled down for you; see "Where the corpus is" below.

Read `CLAUDE.md`, then `docs/PRODUCTION-MODEL.md` §4, §5 and §6, then
`handoffs/2026-09-18-production-package.md` **including its write-up**, then
this.

## Why this stream exists

`production/extract.py` is 799 lines, fully tested, and **has never seen real
data.** Its own stream had no VM, so it ran against a hand-assembled fixture
subset: 6 reactions, 6 plants, 4 material templates, 4 item tools. That write-
up is admirably honest about it:

> "the coverage table below is extraction results against a small hand-
> assembled fixture subset ... not the full 159-reaction vanilla corpus. That
> corpus was never available to this offline stream ... the row counts are not
> a coverage claim about the real install."

So we have a graph engine with no graph in it. This stream fills it and, more
importantly, **produces the first coverage table that is actually a claim
about this install.**

## Where the corpus is

Pulled read-only from VM 103 on 2026-09-19 and unpacked in this session's
scratchpad:

```
<scratchpad>/raws/
  vanilla_reactions/objects/reaction_{adv_carpenter,dyes,other,smelter}.txt
  vanilla_plants/   vanilla_items/   vanilla_materials/   vanilla_buildings/
```

40 files, 830K. Reaction counts per file: adv_carpenter 22, dyes 68, other 46,
smelter 23. **Total 159**, which matches
`research/2026-09-18-schema-extraction-static.md` exactly, so you have the same
corpus the audit read.

The orchestrator will give you the absolute scratchpad path in the dispatch
message. If it is missing or the counts above do not reproduce, **stop and say
so** rather than falling back to the fixtures.

## Do not commit the raws

**This repo is public and these are game data files.** Do not copy them into
`production/tests/fixtures/` or anywhere else under the repo. Read them from
the scratchpad path, in place. The existing fixtures stay exactly as they are:
they are reconstructed-from-audit excerpts with a careful `PROVENANCE.md`, the
existing tests depend on them, and they remain the committed, reproducible test
corpus. Nothing about them changes.

Any SQLite database you build is also out-of-tree (scratchpad), and
`production/` already expects a gitignored db path.

## Deliverable

1. **Run the two-pass extraction over the real corpus** and make it work. The
   interesting output is not "it ran", it is **everything it could not do.**
2. **A real coverage table**, same shape as the one in
   `handoffs/2026-09-18-production-package.md`, but with a header stating
   plainly that these row counts *are* a claim about this install, and naming
   the corpus and the date.
3. **A findings doc** at `research/2026-09-19-real-corpus-extraction.md`
   recording what broke, what was silently wrong, and what the fixture subset
   had hidden.

## What to look hardest at

- **The `GET_MATERIAL_FROM_REAGENT` join.** The audit found **42% of product
  lines** inherit their material from a reagent at job time, which is why
  `material_reaction_product` exists. Six fixture reactions cannot have
  exercised that properly. Report the real percentage you measure, and whether
  the join table populates correctly across all 159.
- **The consumption derivation.** The spec claims the rule
  (`PRESERVE_REAGENT` x whether the reagent is a `PRODUCT_TO_CONTAINER` target)
  has **zero exceptions across 159 reactions**. That claim was made by a
  reader, not by running code. **Verify it by extraction and report any
  exception.** A single genuine exception is a more valuable finding than a
  clean run, so do not smooth one over.
- **Class expansion.** Processes consume classes and produce specifics. With
  the real plant corpus, does one brewing process materialise into one row per
  brewable crop, and how many is that actually?
- **Unparsed or dropped lines.** Count them. A line the parser silently
  ignored is the failure mode that matters most here. If the extractor has no
  way to report unparsed input, **add one**; that is a legitimate change.

## Rules

- No new runtime dependency.
- No coordinates anywhere.
- **Every term keeps its status** (`verified_raws` / `measured` / `prior` /
  `unavailable`) per spec §4. Do not invent a value to make a row complete.
- **A lookup that can silently miss must report the miss.** This project has
  already shipped a probe that printed `0` for a token that did not exist.
- **Verify the verification.** Before reporting a clean extraction, confirm
  your check could have detected a dropped line.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`.
- No em dashes in prose.

## Touched surfaces

`production/extract.py`, `production/tests/test_extract.py`,
`production/tests/test_consumption.py`,
`research/2026-09-19-real-corpus-extraction.md`, and this handoff doc.

**Do not touch** `production/schema.py`, `production/store.py`,
`production/blocker.py`, `production/cover.py`, or
`production/tests/fixtures/**`. A parallel stream owns `production/snapshot.py`
and its tests. If you believe the schema must change, **report it, do not edit
it.**

## Done means

The extractor has run over all 159 real reactions, the full suite still passes
(it is 364 passed / 1 skipped right now, report before and after), the coverage
table is a real claim about this install, and the findings doc states what the
fixture subset had been hiding.
