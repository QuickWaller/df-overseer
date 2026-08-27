# Fort ledger

One structured row per fortress, written when the fort ends. A **trial
registry**. `decisions/DECISIONS.md` (2026-08-25) moved this to the earliest
build item because *"nothing else in the learning design is checkable without
it, and its schema determines what can ever be learned."*

The epitaph is the prose. The ledger row is the data. They are deliberately
separate objects.

**Status: schema built, no rows.** `forts.jsonl` is empty and will stay empty
until the game side exists. That is the intended order: section 3.2 of
`research/2026-08-25-learning-architecture.md` warns that *retrofitting
covariates onto old rows after the fact defeats the purpose*, so the fields
have to be right before the first fort, not after the twentieth.

**Nothing here is verified against DFHack.** Every field marked `MECHANICAL`
is a claim that code will be able to read it from game state. No such code
exists, so `schema.MECHANICAL_PATH_VERIFIED` is `False`. Expect some fields to
turn out unreadable and need replacing. That discovery is the next real test
of this schema, and it is cheaper now than after twenty forts.

## Running it

```bash
python -m ledger.selftest              # checks the schema and the validator
python -m ledger.report                # what is currently learnable, and what isn't
```

## Layout

```
schema.py     field definitions, controlled vocabularies, validation
store.py      JSONL read/write, dotted-path access, stratification
report.py     coverage and descriptive survival. No inference.
selftest.py   checks, including negative ones
forts.jsonl   the ledger. Empty.
examples/     one worked row, deliberately outside forts.jsonl
```

## The four rules the fields come from

Three are from the research spec's section 3.2. The fourth is ours.

**1. Attribution is at the feature level, never the decision level.** With ~20
forts you cannot honestly say a decision in year 4 killed a fort. You can
compare coarse recorded features across forts. So every feature is a closed
vocabulary: free text does not stratify, and a field that cannot stratify can
never become a lesson.

**2. Covariates at the time of the event, not only at embark.** "This fort had
two entrances and died" is worth almost nothing. `threat_log` records the year,
the population, the military strength, the attacker count and the breach
location *at the moment of each threat*; `embark` records the fixed confounds,
including distance to the nearest hostile civ, the design docs' own example of
a confound that ruins a naive comparison.

**3. Plural, ranked contributing factors, never one `cause_of_death` string.**
A fort dies of a chain. `validate` refuses a fort that ended with an empty
factor list, and refuses tied or gapped ranks.

**4. Every field declares how it gets populated.** `MECHANICAL` (code reads it
from game state), `DERIVED` (computed from other fields), `HUMAN`, or `AGENT`.
This is the fourth rule and the research does not state it: a field with no
mechanical path is a field that will be empty or wishful in six months.

## Three design choices worth arguing with

### Orthogonal feature axes, not `entrance_design`

The doc's sketch had a single `entrance_design` field. This schema splits it
into `entrance_count`, `entrance_seal` and `entrance_traps`, and does the same
elsewhere.

The reason is build item 8, the one-variable-at-a-time experiment selector:
**you cannot "vary one variable" when the variable is a portmanteau.** A fort
recorded as `entrance_design: "sealed trap corridor"` differs from the next one
in three ways at once, and no comparison between them means anything. At N≈20,
where the whole learning design rests on holding confounds constant, a bundled
field silently destroys the only trials we get.

### `unrecorded` is a sentinel that stratification refuses to pool

Every vocabulary includes `unrecorded`, and `store.stratify` **drops** those
rows rather than making them a bucket, reporting how many it dropped as part of
the result. Section 3.2's central warning is that an unrecorded feature can
never become a lesson; this makes the ledger say that out loud instead of
letting "we did not look" be quietly coded as a measurement. The dropped count
is the honest denominator: a comparison of two strata of 3 that discarded 9
rows is a different claim from one that discarded none.

### The schema enforces "never grade the agent's own account"

`docs/MEMORY-ARCHITECTURE.md` commits to grading being mechanical, never the
model's self-report. That is easy to state and easy to erode one convenient
field at a time. `store.assert_gradeable(path)` raises unless the named field
is `MECHANICAL` or `DERIVED`, so any future grading or evidence-update code
that reaches for `notes` or for a `HUMAN`-written `rationale` fails loudly
rather than quietly incorporating narration as evidence.

The corollary: `observations[]`, the diagnosticity-tagged evidence links, are
`HUMAN`-sourced and therefore *not* gradeable. They carry `supporting_fields`,
a list of dotted paths into the mechanical record, precisely so a claim can be
checked against data instead of taken on trust.

## The ledger has to be able to record our own failures

`CONTRIBUTING_FACTOR` includes `agent_error`, `human_intervention`,
`fps_collapse` and `crash_or_corruption`; `FORT_STATUS` includes
`run_ended_technical`. The selftest asserts these exist.

This is not defensive completeness. The project's stated goal is a public
report built from accumulated experiment data, and a ledger that structurally
cannot record "the overseer walled its own dwarves in" or "we stopped because
FPS collapsed" will produce a flattering, wrong account of how this went. The
worked example in `examples/` deliberately ranks `agent_error` as its second
contributing factor for the same reason.

`docs/MEMORY-ARCHITECTURE.md`'s own warning applies here: *a system that is
genuinely learning should occasionally be embarrassed by its own past
doctrine.* It cannot be, if the schema has nowhere to write the embarrassment.

## What this deliberately does not do

**No inference.** `report.py` prints coverage and descriptive survival with the
denominators visible, and says in its own output that it is not evidence.
Hypothesis promotion is the hierarchical Beta-Bernoulli model with
diagnosticity-weighted updates and a credible-interval rule (research section
3.3, build item 4). Reading a survival difference off the report and calling it
a lesson is precisely the flat-counter mistake the register rejected on
2026-08-25.

**No database.** JSONL, git-tracked. At N≈20 a full scan is instant, rows diff
individually in `git log`, and the file stays readable with `cat`, which is
what a public report needs. If queries ever outgrow it, build SQLite as a
*derived read model* rebuilt from the JSONL, never as the system of record.

**No write path from the game.** Populating a row from a live fort is the piece
that will actually test whether these fields are readable. It waits on the
perception layer.

## Open questions

- **`hypothesis_id` has no registry yet.** Observations reference hypotheses by
  string id, and nothing validates that the id exists or that two rows mean the
  same thing by it. That registry belongs with build item 4, but a typo'd id
  before then silently orphans evidence.
- **The diagnosticity rubric is prose, not code.** `DIAGNOSTICITY`'s docstring
  states the four Van Evera classes and the example boundary between
  straw-in-the-wind and smoking-gun, but a human still applies it. This is the
  field most exposed to motivated reasoning, which is why `rationale` is
  required and why observations are excluded from grading.
- **Which vocabularies are actually observable.** `defense_depth`,
  `primary_industry` and `surface_footprint` are judgement calls that may have
  no clean mechanical reading. If they cannot be populated by code they should
  be demoted to `AGENT`, and then, per rule 4, treated as colour rather than
  evidence.
- **One row per fort assumes forts end.** A fort that runs for the entire
  project never produces a row. `status: "alive"` exists so an interim row can
  be written, but nothing yet decides when.
