# Handoff: audit this repo for claims presented as measured that are not

Date: 2026-09-19. **Read-only research stream.** No VM, no SSH, no fort, and
**no file edits at all** except the one research doc you produce.

Read `CLAUDE.md`, then `docs/PURPOSE.md`, then this.

## Why this stream exists

This project's entire thesis is honest measurement, and it has caught itself
in the same class of error at least four times in two weeks:

1. **An invented figure became data.** A draft of `docs/PRODUCTION-MODEL.md`
   used "11 days" as an illustrative harvest time. It was quoted back as
   though measured, within a day. §11 now records this against itself.
2. **A probe that could not fail.** A labour audit reported
   `FEED_WATER_WOUNDED` enabled on "0 of 15". **That token does not exist.**
   The probe looked the name up, skipped on failure, and printed its untouched
   counter as `0`, so a missing field and a real zero were indistinguishable.
   The real labour, `FEED_WATER_CIVILIANS`, was enabled on **all 15**.
3. **A medical emergency that did not exist.** Two accurate facts ("1 of 15
   unconscious", "no bucket") supported a false conclusion. The citizen was a
   **sleeping miner** (`pain=0`, `wounds=0`, `job=Sleep`) and the fort owned
   **three** usable buckets; the bucket figure came from a diagram's
   illustrative number.
4. **"The fort drinks."** Asserted in `CLAUDE.md` and `ROADMAP.md` from
   2026-09-17 until 2026-09-19, when measurement showed **nobody had drunk at
   all**: delta tick 6,303 equalled delta thirst 6,303 across all 15 citizens.

Four instances is a pattern, not bad luck. **This stream looks for the rest of
them before they are quoted back as data.**

## Deliverable

One document: `research/2026-09-19-unverified-claims-audit.md`. **Change
nothing else.** Not a doc, not a doctrine entry, not a comment. Findings only;
the orchestrator routes fixes.

## What you are hunting

Sweep `docs/`, `research/`, `doctrine/`, `decisions/DECISIONS.md`,
`Working.md`, `working-archive/`, `handoffs/`, `memory/`, `CLAUDE.md` and
`ROADMAP.md` for:

- **Numbers with no provenance.** A figure stated as fact with no citation to
  a raw file, a live read with a tick, a wiki URL, or a named tool run. Flag
  every one. Illustrative numbers inside examples are the highest-risk class,
  because that is exactly how "11 days" escaped: say whether each is clearly
  marked as illustrative or could be mistaken for a measurement.
- **Claims of the form "X is solved / working / verified"** where you cannot
  find the evidence. §12's "the chain is solved" is the known example; find
  the others.
- **`status: verified` in `doctrine/seed.yaml`** on anything whose cited
  source does not actually establish it. Doctrine's own rule is that almost
  nothing should be `verified`.
- **Probes and checks that cannot fail**, in `scripts/dfhack/*.lua` and any
  Python that reads live state: a lookup that falls through to a default
  instead of reporting a miss, a counter printed whether or not it was
  touched, a check whose success and failure paths produce the same output.
  **This is the highest-value category**, because it manufactures false data
  rather than merely repeating it.
- **Contradictions between documents.** Where two files disagree, say which is
  better evidenced; do not assume the newer one is right.

## How to report each finding

A table, ordered **most dangerous first**, where dangerous means "most likely
to be quoted as data by a future session". Per row: the file and line, the
claim as written, what evidence exists, what is missing, and your confidence.

Then a short section: **which of these are cheap to settle**, and with what
single observation or command. That section is what turns this audit into
work, so make it concrete.

## Rules

- **Do not fix anything.** Report only. A fix inside an audit is unreviewable.
- **Do not guess at what a claim was based on.** If you cannot find evidence,
  the finding is "no evidence found", not "probably came from the wiki".
- **Apply the standard to yourself.** Every finding you report must cite a
  file and line you actually opened. If you infer, say so.
- **Distinguish "unsourced" from "wrong".** Most of what you find will be
  true but uncited. Rank an uncited-but-plausible claim below a claim you can
  show is contradicted.
- No em dashes in prose.

## Touched surfaces

`research/2026-09-19-unverified-claims-audit.md` only, plus a write-up at the
bottom of this handoff doc. **Nothing else, at all.**

## Done means

The audit doc exists, every finding cites a real file and line, the ordering
reflects danger rather than volume, and the cheap-to-settle section names
specific observations. A short honest audit beats a long speculative one.
