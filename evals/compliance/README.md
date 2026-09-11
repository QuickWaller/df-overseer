# Compliance eval harness

Research build-order item 1 (`research/2026-08-25-learning-architecture.md`
§7): *replicate "Prompt Design at Scale"'s instruction-count-decay
methodology against this project's own doctrine format and model.* No
running game, no agent, no DFHack, no fort. Same "no game, no agent,
afternoon-sized" shape as `evals/perception/`, applied to memory instead of
perception.

**What it is for.** The overseer's whole memory design
(`docs/MEMORY-ARCHITECTURE.md`) assumes doctrine can be handed to the model in
a system prompt and reliably followed, and that doctrine can grow over many
forts without the model silently dropping rules. A 2026 study
(arXiv:2607.19257) found perfect-response rate collapsing to zero by around 80
simultaneous rules, for every model and format it tested — but that number was
measured on different models, on synthetic tasks unrelated to this project.
Nobody has measured it for the model and doctrine format this project actually
uses. This harness measures that, instead of assuming "small" is safely small
(`research/2026-08-25-learning-architecture.md` §4).

**Status.** Built, selftested, and run for real against two providers —
`deepseek-chat` (complete, 180 cells, `--repeats 1`) and `claude-opus-5`
(180 cells plus a 46-cell partial rerun of n=120/160 at a larger
`max_tokens`, stopped short of the full rerun — see Cost below). Both
providers work end to end via `harness/providers.py`'s adapter split
(Anthropic native Messages API vs. any OpenAI-compatible chat-completions
endpoint). Full results: `evals/compliance/results/deepseek-full-2026-09-11.jsonl`,
`full-2026-09-11.jsonl`, `full-2026-09-11-fix.jsonl`.

**Cost, stated plainly.** The `claude-opus-5` run cost **roughly $9-13** in
real API spend across ~250 calls, almost entirely `thinking`-token *output*
(adaptive thinking burned 3,000-3,900+ tokens per call reasoning through a
120-160-rule doctrine, at $25/MTok output). The `deepseek-chat` run cost
**cents**. This is not incidental — it is itself a finding: eval design that
loops a large system prompt through adaptive-thinking Opus at scale is
expensive by default, and the user's explicit call afterward was to stop
further Opus spend and make **DeepSeek the harness's default provider**
(`run.py`'s `--provider` default is now `deepseek`; pass `--provider
anthropic` explicitly when a real Claude number is actually needed). No
further Anthropic runs happen without asking first.

## Findings so far

**`deepseek-chat` (clean, complete data — the one to trust)**: perfect-
response rate is 70-83% at n=10/20, then **collapses to 0% at every n≥40**
— far earlier than "Prompt Design at Scale"'s own ~80-rule collapse point for
the models it tested, which is exactly the point of measuring this
project's own model rather than reusing that number. Per-rule pass rate
tells a more useful story: it degrades gently, 97% at n=10 down to 72% at
n=160 — meaning most individual rules are still mostly followed even where
*perfect* compliance is already impossible. The category breakdown makes the
mechanism concrete: at n=160, `required_word` compliance is **20.6%**
(340/1650) while `banned_word` compliance is **100%** (2399/2400). This model
is dramatically better at reliably *not* doing something across many
simultaneous rules than at reliably inserting many specific required words —
a real, actionable asymmetry for how DF doctrine should be phrased (prefer
"never X" over "always include Y" where the choice is free).

**`claude-opus-5` (real data, but noisier and partly compromised — read with
the caveats below)**: per-rule pass rate stays remarkably high throughout,
93.7% at n=10 up to 99.8% at n=160 — Opus does not show DeepSeek's
`required_word` weakness at all (99.5% at the largest n in this file).
Perfect-response rate, however, is noisy and non-monotonic (36.7% / 56.7% /
50.0% / 20.0% / 16.1% / 69.6% at n=10/20/40/80/120/160) rather than a clean
collapse curve — with `--repeats 1` (30 runs per doctrine size, split three
ways across formats), a single unlucky format/scenario pairing swings the
perfect-rate by tens of points, and the by-format table shows exactly that:
n=160 ranges from 61.5% (markdown) to 83.3% (plain) *within the same doctrine
size*. Read this as "Opus does not show a clean collapse point in this
sample," not as "Opus doesn't collapse" — a real run needs more repeats to
tell those apart, which is exactly the next-step gap below.

**A real harness bug, not a finding, is baked into the raw `claude-opus-5`
numbers above and already fixed for future runs**: the original 180-cell
sweep used `max_tokens=4000`, and adaptive thinking at n=120/160 sometimes
consumed the entire budget before emitting any text — 27 of 180 cells (77%
of n=160, 13% of n=120) came back with **zero text content**, not a
compliance failure. `max_tokens` is now `16000` by default
(`evals/compliance/harness/run.py`), confirmed live: a 46-cell rerun of
n=120/160 at `max_tokens=12000` produced **zero** empty responses before it
was stopped partway through (cost). The `n_runs` column in the report is the
tell for this class of problem — always check it before trusting a
per-doctrine-size row, it silently drops below the intended sample size when
a provider fails a chunk of a batch.

Model choice is a scientific parameter here, not an implementation detail:
"where does *this* project's compliance collapse" only means something once
it is asked of whichever model(s) are actually candidates for the driving
brain — `ROADMAP.md`'s still-deferred "`openclaw` vs `hermes-agent`" question
and, more directly, which vendor's model ends up running the fort. Running
this against more than one provider from the start is why `providers.py`
exists as a seam rather than a hardcoded Anthropic call — and why the cost
asymmetry between providers is itself part of that question, not a detail to
optimize away later.

## Running it

```bash
python -m evals.compliance.harness.selftest   # checks the harness itself
python -m evals.compliance.harness.run --dry-run --limit 1
```

Then, with `DEEPSEEK_API_KEY` set (the default provider — cheap, a full
180-cell sweep costs cents):

```bash
pip install openai   # DeepSeek speaks the OpenAI-compatible chat-completions API
python -m evals.compliance.harness.run --out evals/compliance/results/first.jsonl
python -m evals.compliance.harness.report evals/compliance/results/first.jsonl
```

Anthropic is fully supported but **not the default** — a single 180-cell
`claude-opus-5` sweep with adaptive thinking cost $9-13 in one session, almost
entirely `thinking`-token output (see Cost above). Ask before running it, and
pass it explicitly:

```bash
pip install -r evals/compliance/requirements.txt   # anthropic >= 1.0
python -m evals.compliance.harness.run --provider anthropic \
    --out evals/compliance/results/opus1.jsonl
```

Passing both providers' output files to `report.py` together renders a
side-by-side comparison, split by model.

Useful flags: `--rule-counts`, `--formats`, `--scenarios`, `--repeats`,
`--provider`, `--model`, `--effort`, `--limit`, `--concurrency`. Default
matrix (the paper's own rule counts, 10/20/40/80/120/160, x 3 formats x 10
scenarios) is 180 cells; start with `--limit 20`.

## How it is put together

```
harness/rules.py         the synthetic doctrine pool: ~170 independently
                          verifiable rules, one fixed shuffle so rule_set(n)
                          nests inside rule_set(2n)
harness/formats.py       doctrine -> the text the model sees (markdown/
                          plain/prose)
harness/scenarios.py     the (deliberately non-DF) tasks the model performs
                          while holding the doctrine
harness/providers.py     one call shape in, (text, usage, error) out, per
                          provider — Anthropic native, DeepSeek (and anything
                          else OpenAI-compatible) via a shared adapter
harness/run.py           the matrix, the API call, JSONL out
harness/report.py        aggregation, split by model when a file mixes them
harness/selftest.py      checks on the harness's own ground truth
```

## The rule pool

Every rule governs the *form* of a free-text response only — wording,
structure, punctuation — never its substance, so compliance can be checked by
code against the raw response text. **No LLM ever grades another model's
compliance here**, matching the register's standing position
(`decisions/DECISIONS.md`, 2026-08-25: "All learning grading is mechanical")
— an LLM judge would be grading exactly the kind of instruction-following
this harness exists to measure as unreliable.

| category | example | how many |
|---|---|---|
| `banned_word` | never use "however" | 80 |
| `required_word` | must include "outcome" | 60 |
| `banned_char` | never use a semicolon | 7 |
| `min_word_count` / `max_word_count` | at least 20 / at most 80 words | 5 + 5 |
| singletons | exact prefix, exact suffix, exactly 3 sentences, single paragraph, all-lowercase, no contractions, no digits, no first person, ends with `?` | 9, one each |

**Nested, not independently sampled.** `rule_set(n)` is always the first `n`
rules of one fixed shuffled order, so `rule_set(20)` is a strict subset of
`rule_set(40)`. This isolates what changed when doctrine grew from N to 2N to
the rules actually added, rather than confounding rule count with which rules
happened to be drawn.

**Jointly satisfiable by construction, not by assumption.** A pool containing
both "always end with '?'" and "never use '?'" would make perfect compliance
impossible regardless of model quality. Categories that are inherently
mutually exclusive (a required prefix, a required suffix, an exact sentence
count...) contribute exactly one concrete rule each, never competing variants.
`selftest.py` proves this by actually constructing one response that passes
every rule in the largest configured set and checking it against every
`.check` callable — it already caught two real bugs building this harness: a
test string that accidentally contained a word it was banning, and a max-word
cap (60) that was tighter than the 60 mandatory required-word rules plus
prefix/suffix overhead could ever fit under, which forced widening the
`max_word_count` bank's floor to 80.

## Reading the report

- **Headline** — perfect-response rate against doctrine size, the same shape
  as the paper's own collapse curve.
- **Per-rule pass rate** — the mean fraction of *active* rules a response
  actually obeyed. Perfect-rate can hit zero well before this does: a response
  that fails 1 of 80 rules and one that fails 40 of 80 both score "0%
  perfect," and only this number tells them apart.
- **By format** — whether markdown/plain/prose change where the collapse
  happens. The paper found format barely mattered; this checks it against
  this project's own model rather than assuming the finding transfers.
- **By category** — which rule *types* degrade first at the largest doctrine
  size in the file. A design-relevant finding in its own right: if, say,
  `exact_sentence_count` degrades long before `banned_word` does, that says
  something about what kind of doctrine rule is actually safe to accumulate.

## What this cannot tell you

- **It measures raw instruction-following capacity, not doctrine
  effectiveness.** A rule like "never use the word 'however'" is easy to
  verify mechanically but says nothing about whether real DF doctrine
  ("never dig a downstair on a grass tile") is the kind of rule that degrades
  the same way — only that *some* large simultaneous rule set does, at some N,
  for this model.
- **Scenarios are deliberately generic**, not fortress-flavoured, so that
  rule-following isn't confounded with domain reasoning load. Doctrine
  competing with genuine DF-decision complexity (the real deployment
  condition) may collapse earlier than this measures.
- **`exact_sentence_count`'s checker is an approximate sentence splitter**, not
  a real parser — it counts terminal-punctuation runs. Good enough to grade a
  model that is actually trying; noted so a report reader knows its ceiling.
- **This is one model, one effort level, one max-token budget per run** unless
  swept explicitly via `--model`/`--effort`. The collapse point is a property
  of a specific configuration, not a universal constant — that is the entire
  point of measuring it here rather than reusing the paper's own number.
