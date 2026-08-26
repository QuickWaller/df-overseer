# Perception eval harness

Build-order item #1 (`docs/PURPOSE.md`): *hand-written briefings, questions with
known answers, measure comprehension.* No running game, no agent, no DFHack.

**What it is for.** The whole project rests on one unproven bet: that a model
given facts about a fortress *as linear text* can reason about that fortress
well enough to run it. If that bet is wrong, everything downstream —
`check_reachable`, the landmark graph, the site ranker, the agent loop — is
built on sand. This measures the bet before anything is built on it.

**Status.** The offline paths (fixtures, question generation, grading, the
selftest, `--dry-run`) are built and verified. **No run against a live model has
happened yet** — this machine has no Anthropic credentials. The request path is
verified against a stub, not against the API.

## Running it

```bash
python -m evals.perception.harness.selftest      # checks the harness itself
python -m evals.perception.harness.run --dry-run # builds every prompt, calls nothing
```

Then, with credentials (`ANTHROPIC_API_KEY`, or an `ant auth login` profile):

```bash
pip install -r evals/perception/requirements.txt   # anthropic >= 1.0
python -m evals.perception.harness.run --out evals/perception/results/first.jsonl
python -m evals.perception.harness.report evals/perception/results/first.jsonl
```

Useful flags: `--representations`, `--categories`, `--fixtures`,
`--per-category`, `--repeats`, `--model`, `--effort`, `--limit`,
`--concurrency`. Default matrix is 342 cells; start with `--limit 20`.

## How it is put together

```
fixtures/*.json          hand-authored fortresses: landmarks with true
                         positions, walkable connections, units, resources
harness/fixture.py       loads them; computes ALL ground truth (bearings,
                         distances, BFS routes, connected components)
harness/representations.py  fixture -> the text the model sees
harness/questions.py     question generators; answers derived from the fixture
harness/grade.py         mechanical graders
harness/run.py           the matrix, the API call, JSONL out
harness/report.py        aggregation
harness/selftest.py      checks on the harness's own ground truth
```

Four properties are deliberate:

**No expected answer is written by hand.** Every one is computed from the
fixture. Editing a fixture cannot leave a stale answer behind.

**No LLM judges anything.** Grading is mechanical, matching the register's
standing position (`decisions/DECISIONS.md`, 2026-08-25). An LLM judge here
would be grading exactly the class of spatial claim this harness exists to
establish LLMs are unreliable about.

**Ambiguous questions are refused at generation time.** A bearing on an octant
boundary, a shortest route with a tie, a "nearest" with two equal candidates —
the generators drop them. Grading an ambiguous question measures the grader's
opinion, not the model.

**Answer polarity is balanced.** Left uniform, most `zlevel` questions answer
"same" and most `reachability` questions answer "true", both of which a model
passes by answering the same way every time. `_balanced()` draws round-robin
across the available answers instead.

## The three representations

| | what it carries | why it is here |
|---|---|---|
| `exits_v1` | named landmarks, each with an exit list: direction, distance, z-delta, route type. No coordinates. | The representation `docs/PURPOSE.md` commits to. |
| `coords_v1` | a coordinate table plus a flat connection list. | The control. Strictly more informative — so if it wins, the landmark idiom is not paying for itself. |
| `prose_v1` | exactly `exits_v1`'s facts, as English sentences. | Isolates encoding from content. If it ties `exits_v1`, the JSON structure buys nothing but tokens. |

**None of them renders a map.** That is design commitment #1 and it is not a
variable this harness sweeps. An ASCII-map control arm would be the obvious
fourth cell and is deliberately *not* built: the commitment is a settled
decision, the prior literature (LessWrong, BALROG) already measured it, and
building the arm would mean writing the renderer the project promised never to
write. Worth revisiting only if someone wants to re-open the commitment.

## Which questions each representation is allowed

Each question declares what it `needs`; each representation declares what it
`provides`. The runner **skips** combinations a representation cannot express
rather than scoring them as wrong — a representation that never carried the
fact was never going to answer, and counting that as a wrong answer would make
the comparison meaningless.

Today that means `exits_v1` and `prose_v1` skip `bearing_far` and `zlevel_far`
(geometry between landmarks that are *not* directly connected), which
`coords_v1` answers.

**That skip list is the most useful thing this harness produces before it is
even run.** It is a precise statement of what the agent will not be able to
work out for itself, and therefore of which zoom tools it must be given. No
amount of prompting recovers a fact the briefing never carried.

The report's headline number is accuracy on the **shared** question set — the
categories every representation could express. Comparing on full sets would
reward `coords_v1` for merely being asked more.

## Question categories

| category | needs | tests |
|---|---|---|
| `bearing` | connected geometry | reading a direction off an exit list, in both directions |
| `bearing_far` | global geometry | composing directions across the fort |
| `distance`, `walk_distance` | connected geometry | straight-line vs. actual walking distance, kept distinct |
| `zlevel`, `zlevel_far` | connected / global geometry | multi-z, flagged in the research spec as the weakest point |
| `adjacency` | topology | what connects to what, with no over-listing |
| `hops`, `route` | topology | multi-step pathing over the landmark graph |
| `reachability` | topology | the `check_reachable` question, asked of the model instead |
| `nearest_connected` | connected geometry | ranking by distance |
| `count_kind`, `kind_present` | facts | aggregation, and absence |
| `stranded` | topology + facts | which citizens are cut off, deduced from the graph |
| `absent_landmark` | facts | **hallucination probe** — asks a bearing to a place that does not exist |

`absent_landmark` is the one that matters most for safety. A model that invents
a bearing there would, in the real system, invent a reason to send dwarves
somewhere that is not there. Correct behaviour is the abstention literal
`UNKNOWN`, which the report counts separately from a wrong answer.

## Reading the report

- **Headline** — accuracy per representation on the shared set.
- **By category** — `correct% (abstentions / near-misses / API errors)`. A
  near-miss is an adjacent compass point, a single wrong element in a set, or a
  route with the right rooms in the wrong order. Near-misses and wild misses are
  different failures and are worth telling apart.
- **Calibration** — mean stated confidence when right vs. when wrong.
  Separation near zero means the model cannot tell when it is lost, so a zoom
  tool it decides to call *on its own initiative* will not save it. That would
  be a design finding, not a scoring detail.
- **Cache** — whether requests read cached tokens. Zero across a run means the
  briefing is not serialising byte-identically, which the prefix-caching design
  (research spec, section 7) depends on.

## What this cannot tell you

- **It does not test the real briefings.** These fixtures are hand-authored.
  The production `exits_v1` will be *lossy* in a way this one is not — the Lua
  sketch keeps only the three nearest neighbours per landmark, and picks them by
  geometric distance rather than walkable distance. This harness measures
  whether a representation is **legible**; it does not measure whether the real
  generator will **fill it correctly**. Re-run against real briefings once
  `llm-brief.lua` exists.
- **It does not test judgment**, only comprehension. "Where should the dining
  hall go" is a different eval.
- **`stranded` is answered by reasoning here; in production it is precomputed**
  by `check_reachable` (build item #2). It is kept because an overseer that can
  see which *parts of the fort* are cut off makes better calls than one handed a
  list of names.
- **Fifteen landmarks is not a large fortress.** A late fort has far more, and
  the failure mode may be length rather than structure. Add a bigger fixture
  before concluding a representation scales.
- **`integer` and `boolean` questions have no abstention channel** — the answer
  schema has nowhere to put `UNKNOWN`. Only string and list answers can abstain.

## Adding a fixture

Drop a JSON file in `fixtures/`. Positions are `[x, y, z]` with **+x east, +y
south, +z up**. Prefer axis-aligned and exact-diagonal offsets between connected
landmarks: `validate()` rejects any connected pair whose bearing sits within 10
degrees of an octant boundary, because such a question has no defensible answer.
Run the selftest afterwards — it is what catches a fixture that generates
nothing, or ground truth that disagrees with the coordinates.
