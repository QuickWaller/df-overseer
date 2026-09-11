# Prediction log

Research build order item 3 (`research/2026-08-25-learning-architecture.md`
§7): *mechanical prediction grading — a scripted comparison of a `signal`
field against recorded state at `check_at`.* Implements
`docs/MEMORY-ARCHITECTURE.md`'s own worked example as real, gradeable data:

```
decision:    dig a second farm level on z-4
expectation: food stores stop falling within 2 seasons
check_at:    year 253, Autumn
signal:      food_stores trend
```

**Why this exists at all.** §1.2 of the research spec found that LLM
self-assessment is confident and largely uncorrelated with truth, and that a
model can produce a fluent, convincing account connecting any decision to any
outcome *after the fact* (Turpin et al., unfaithful chain-of-thought). §1.3
names the actual discipline this is: **pre-registration** — committing to a
prediction and how it will be checked *before* the outcome is known, the same
practice clinical trials and Registered Reports use against HARKing
(Hypothesizing After the Results are Known). A prediction log with no
mechanical grading is not a defense against this; it is a diary.

## Running it

```bash
python -m learning.predictions.selftest              # checks the schema and grader
python -m learning.predictions.report                # what the log currently shows
```

## Layout

```
schema.py     the Prediction record, predicate ops, write-time validation
store.py      JSONL read/write — register() (append-only) vs. rewrite_all()
              (how a grading pass persists an update)
grade.py      the mechanical comparison — no model involved, ever
report.py     status counts, hit rate, overdue-but-ungraded. No calibration.
selftest.py   checks, including negative ones — reuses ledger's own worked
              example rather than inventing a second fixture
predictions.jsonl   the log. Empty.
```

## The two things `research/2026-08-25-learning-architecture.md` §1.3 asks for, enforced in code

**1. Grading is mechanical, never the model re-reading its own prediction.**
`grade.grade()` reads only `ledger.store.get_path` against a ledger row, plus
the prediction's own `predicate_op`/`predicate_value`. It never reads
`decision` or `expectation` — those are prose, kept for the eventual epitaph,
and structurally cannot influence a grade.

**2. A prediction must be falsifiable at write time, not just at grading
time.** `schema.validate()` calls `ledger.store.field_source()` on `signal`
and refuses to validate — so `store.register()` refuses to write — a
prediction whose signal:
- doesn't resolve to any real ledger field at all (a typo, or a fact that
  doesn't exist yet), or
- resolves to a `HUMAN`- or `AGENT`-sourced field (grading a person's or the
  agent's own prose would smuggle self-report back in through the signal,
  exactly the loophole this module exists to close).

This is the literal implementation of §1.3's second requirement: *"reject
predictions at write-time that don't resolve to a ledger/dossier field."*
`predicate_op` is also a small, closed vocabulary (`eq`/`ne`/`gte`/`lte`/
`gt`/`lt`/`in`/`contains`/`exists`/`not_exists`) rather than an arbitrary
expression language — an "eval this" predicate would reopen exactly the
unfalsifiability problem the spec warns about ("things should improve" is
worthless because nothing can contradict it).

## The scope this is deliberately built at — and the gap it does not paper over

`signal` can only resolve against **the fort ledger** (`ledger/`), because
that is the only mechanical store that exists in code. The spec's own phrase
is "ledger **or dossier** state" — a **fort dossier** (working state that
dies with the fort: landmarks, plans, open problems) is still just a design
concept in `docs/MEMORY-ARCHITECTURE.md`, with no module. Concretely, that
means:

- **Covered for real**: predictions about embark covariates, design choices,
  or fort outcome/threat fields. The design doc's other example — "seal the
  caverns before year 3" — maps directly onto `design.caverns_sealed` /
  `design.caverns_sealed_year`, both already in the ledger schema.
- **Not yet expressible**: the design doc's *own* headline example,
  "food stores stop falling within 2 seasons," has no matching field anywhere
  in the ledger. Mid-fort trend data is exactly what a dossier would carry and
  the ledger, being one row written mostly at embark and at the end, does not.

Building a dossier module just to make that one example work would have been
scope creep beyond this build item; it is named here as the next real gap,
not silently assumed away.

## A subtlety worth knowing before writing a `not_exists` prediction

Several ledger fields are legitimately `null` as a *fact* (`threat_log.N.
breach_location` is `null` precisely when there was no breach — see
`ledger/schema.py`), not because the field is unrecorded. `grade()` treats
this correctly for the presence ops: `not_exists` on a legitimately-null field
grades `true`. But for every other op (`eq`, `gte`, ...), a `null` value —
whether "genuinely not yet known" or "genuinely doesn't apply" — grades as
`unresolvable`, on purpose: the grader cannot tell those two cases apart
without per-field domain knowledge, and guessing would be exactly the kind of
silent judgement call this module exists to avoid. **If a prediction is about
whether something happened at all, use `exists`/`not_exists`; only use a
value comparison once the field is expected to hold a real value regardless
of outcome.**

## What this deliberately does not do

**No calibration score.** Build order item 6 (a Brier score, or hit-rate on
falsifiable predictions) needs a model-stated confidence per prediction, which
this schema doesn't carry — `predicate_op`/`predicate_value` is a binary
claim, not a probability. `report.py`'s `graded_true`/`graded_false` split is
the raw material a future calibration metric would consume, not the metric
itself.

**No connection to hypothesis promotion yet.** The evidence model (research
§3.3, build item 4 — the hierarchical Beta-Bernoulli replacement for the flat
evidence counter) is not built. A graded prediction sits in the log; nothing
yet feeds it into a hypothesis's posterior.

**No write path from a live agent loop.** Like the ledger before the
perception layer, `register()` exists and is tested against a hand-built
fixture; nothing yet calls it from an actual overseer session making an
actual decision. That wait is intentional — this schema had to exist and be
right before any prediction gets written under it, for the same reason the
ledger's own schema came first.
