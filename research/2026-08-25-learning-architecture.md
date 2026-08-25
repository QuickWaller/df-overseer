# Learning Architecture for an LLM-Driven Dwarf Fortress Agent

Date: 2026-08-25
Companion to `docs/MEMORY-ARCHITECTURE.md` (the design under review — renamed from
`docs/MEMORY.md` mid-research, content unchanged) and `docs/PURPOSE.md`.
Sibling document: `research/2026-08-25-spatial-perception.md` (not revisited here).

Status: research and design critique, not implemented. Nothing below was tested
against a running game or a running agent.

## 0. How to read this document

`docs/MEMORY-ARCHITECTURE.md` is treated throughout as a strawman under attack, not
a spec being elaborated. Each of its claims gets a verdict — **keep**, **replace**,
or **kill** — with the prior art that justifies the verdict. The four problems the
brief asked for are answered by going to the field that has spent decades on the
domain-neutral version of the problem, not by searching for "Dwarf Fortress" or
"LLM agent" and stopping there. Citations are primary sources where I could reach
them; where I couldn't verify a claim independently I say so.

The single most important finding, stated up front because it reframes everything
else: **`docs/MEMORY-ARCHITECTURE.md`'s hypothesis-promotion mechanism (§4, "N=1 is
not a lesson") assumes credit assignment is a solved sub-problem when it feeds
evidence counters, but the brief's own priority-1 problem says it isn't.** A
"support: 2, contradict: 0" counter can only be filled in once you already know
*which* of ~200 decisions in a 10-year fort caused its death — and nothing in the
current design produces that judgment. This is fixed below (§3), and it is the
load-bearing fix; everything else is secondary to it.

---

## 1. Verdicts on the strawman

| Piece | Verdict | Why |
|---|---|---|
| Four memory stores (chronicle/doctrine/playbooks/dossier) | **Keep** | Matches a well-established cognitive-architecture split, not an ad hoc one — see §1.1 |
| "Outcome tracking, not self-critique" | **Keep, strongly** | Directly validated by recent LLM self-evaluation research — see §1.2 |
| Predictions with a check date | **Keep, but make it pre-registration properly** | Right instinct, needs to borrow the actual discipline behind it — see §1.3 |
| Hypothesis + evidence counter, promote at support≥3 | **Replace** | The weakest piece; naive vote-counting with an arbitrary threshold, blind to confounds — see §3 |
| Scope tags (universal/world/site) | **Keep the concept, replace the mechanism** | Right taxonomy, wrong data structure — should be a hierarchical model, not three discrete buckets — see §3.3 |
| Fort ledger | **Keep, and it's the most important piece to build early** | This is a trial registry / case base; without it, nothing above is checkable — see §3.2 |
| Wiki as hypothesis source, entering at "support: 2" | **Keep the instinct, replace the arithmetic** | Right to treat it as an informative prior; "2" should be a stated prior strength, not a magic number — see §3.4 |
| "Doctrine must stay small" | **Keep, and it is more load-bearing than the document realizes** | This is not a style preference — it is close to a hard ceiling on how many simultaneous rules a model will actually obey. See §4 |
| Active experimentation ("probably not v1") | **Promote to v1, in a cheap form** | Passive learning at N≈20 is close to unworkable; a one-variable-at-a-time discipline is nearly free once the ledger exists — see §5 |

### 1.1 The four stores: keep, and here is the prior art that validates them

The chronicle/doctrine/playbooks/dossier split is not a novel taxonomy — it is a
close match to two independent traditions that converged on the same shape:

- **Tulving's episodic/semantic memory distinction** (1972): episodic memory is
  context-specific, tied to a particular time and place, and supports "mental time
  travel"; semantic memory is context-free, general knowledge stripped of the
  episode that produced it. The chronicle is episodic memory; doctrine is semantic
  memory. This is not a metaphor of convenience — it is the standard distinction in
  memory research, and the practical argument for separating them (you retrieve
  each differently, and conflating them makes both retrieval tasks worse) transfers
  directly.
- **Cognitive architectures (ACT-R, Soar)** independently split long-term memory
  into declarative (further split into semantic and episodic in Soar's case) and
  procedural stores, plus a working-memory buffer. Soar's declarative-semantic /
  declarative-episodic / procedural / working-memory split is a four-way partition
  that maps almost one-to-one onto doctrine / chronicle / playbooks / fort dossier.
  I could not verify field-level detail of Soar's memory APIs beyond what secondary
  sources describe (arXiv:2201.09305, "An Analysis and Comparison of ACT-R and
  Soar," was the best source found; I did not read Soar's own technical manual).

**Verdict: keep as designed.** This is the one part of the strawman that is
already doing what six decades of cognitive-architecture and memory research
converged on independently.

### 1.2 Outcome tracking over self-critique: keep, strongly validated

`docs/MEMORY-ARCHITECTURE.md` asserts, correctly, that "asking an LLM to critique
its own reasoning produces confident, plausible, largely uncorrelated-with-truth
self-assessment." Recent measurement backs this up more specifically than the
document states:

- Self-reported LLM confidence is poorly calibrated and models are "consistently
  overconfident, especially when they are incorrect," with overconfidence gaps of
  20–60 percentage points reported across studies, and models change feasibility
  judgments on lightly perturbed versions of the same task in **over 45% of
  cases** — evidence the self-assessment tracks surface memorization, not genuine
  self-knowledge (arXiv:2506.18998, "Mirage of Mastery").
- Intrinsic self-correction (asking a model to check its own reasoning with no
  external signal) "often fails to improve and can even degrade performance" — a
  model cannot reliably self-correct without an external check.
- Chain-of-thought explanations can be systematically unfaithful: Turpin et al.
  2023 (arXiv:2305.04388, NeurIPS) showed models produce fluent justifications for
  answers that were actually determined by a superficial prompt artifact (e.g.
  option ordering) the explanation never mentions. A model narrating "why" it made
  a fortress decision is not reliable evidence that the stated reason is the actual
  cause of the decision.

**Verdict: keep, and treat this as one of the best-supported parts of the whole
document.** The corollary is stronger than stated in the strawman: not just "don't
ask the model to grade its own reasoning" but "don't trust the model's narration of
*why* it did something, even when grading against an external outcome" — the
outcome check must be computed in code against ledger/state data, never elicited
from the model's own account of events (this becomes the central defense against
the "narrates learning" failure mode in §6).

### 1.3 Predictions-with-check-dates: keep, but recognize what it actually is

The prediction/check_at mechanism is, without naming it, **pre-registration** —
the practice, standard in clinical trials (ClinicalTrials.gov) and increasingly in
psychology (Open Science Framework "Registered Reports"), of committing to a
hypothesis and analysis plan before the outcome is known. The problem it solves is
**HARKing** — Hypothesizing After the Results are Known, a term coined by Norbert
Kerr (1998), where a post-hoc explanation is written up as if it had been predicted
in advance. HARKing is trivial for an LLM to do silently and convincingly (per
§1.2, a model can produce a fluent narrative connecting any decision to any
outcome after the fact) — which makes pre-registration not a nice-to-have here but
close to the only defense available.

**Two things the current design is missing that the actual discipline requires:**

1. **The prediction must be graded by code against recorded state, never by the
   model re-reading its own prediction and judging itself** — this follows
   directly from §1.2's calibration findings, and the current design doesn't say
   explicitly that grading is mechanical rather than model-judged. Make it
   explicit: `check_at` triggers a scripted comparison against ledger/dossier
   fields (e.g. `food_stores` trend, computed the same way `find_open_area` or
   `check_reachable` compute facts — in code, never asserted by the model), and
   the model only sees the graded result.
2. **A prediction log needs an audit for unfalsifiability.** A prediction vague
   enough to always look "correct" in hindsight ("things should improve") is
   worthless and is exactly what an ungraded LLM would drift toward. Require a
   `signal` field bound to a specific queryable fact (as the current schema
   already does) and reject predictions at write-time that don't resolve to a
   ledger/dossier field — this is a cheap, code-enforceable check, not a policy.

---

## 2. Recommended architecture (concrete)

Keep the four stores and the fort ledger. Replace the promotion mechanism with a
**hierarchical evidence model** (§3.3) fed by **causally-annotated ledger rows**
(§3.2) that a **within-episode process-tracing pass** (§3.1) produces at the death
of each fort. Treat the wiki as a **stated Bayesian prior**, not a hard-coded
starting count (§3.4). Keep doctrine under a **measured compliance ceiling**, not
just "small" by feel (§4). Add a **cheap one-variable-at-a-time experiment
selector** driven by expected value of information (§5). Add a **measurement
harness with a control arm that doesn't cost extra episodes**, via seeded reruns
(§6).

Concretely, per fort death:

```
1. Process-tracing pass (code-assisted, model-drafted, code-checked)
   → produces: candidate causal chain, confound list, diagnosticity-tagged
     evidence for each active hypothesis this fort could speak to
2. Ledger row written (mechanical, from game state — never model-asserted)
   → fort_id, world_id, embark covariates, timeline of major decisions,
     cause-of-death candidates with diagnosticity tags, hypotheses touched
3. Hierarchical evidence update (code, not model judgment)
   → each touched hypothesis's Beta/hierarchical posterior updated by the
     diagnosticity-weighted evidence, not a flat +1/-1
4. Promotion/demotion by posterior threshold, not by raw count
   → doctrine edited in place; scope determined by posterior variance across
     world/site levels, not by a human-picked bucket
5. Epitaph written (prose, for the reader and for retrieval) — separate from
   and secondary to the ledger row, which is what promotion actually reads
```

---

## 3. Problem 1 — Credit assignment (priority 1, and correctly so)

### 3.1 What the relevant fields actually recommend

The domain-neutral problem: **an agent makes ~200 sequential, interacting
decisions over a long episode that ends in one outcome; which decisions mattered?**
This is not a Dwarf-Fortress-specific problem or even an RL-specific one — it has
independent, mature treatments in at least four fields, and they agree on more
than the strawman's design uses.

**Reinforcement learning — temporal credit assignment.** The formal statement:
"how does the execution of particular actions from specific states impact
observed future outcomes," complicated in practice by delayed effects,
transpositions (different action sequences reaching the same state), and weak
action influence (arXiv:2312.01072, "A Survey of Temporal Credit Assignment in
Deep Reinforcement Learning"). Two mechanisms from this literature are directly
portable to a non-differentiable, non-RL-trained agent:

- **Counterfactual/hindsight credit assignment**: condition a value estimate on
  future events that are known not to depend on the action being evaluated, to
  separate "this action caused the outcome" from "this outcome happened and this
  action also occurred" (Mesnard et al. 2021, arXiv:2011.09464, "Counterfactual
  Credit Assignment in Model-Free Reinforcement Learning"; Harutyunyan et al. 2019,
  "Hindsight Credit Assignment," NeurIPS). The core move — reweight the credit a
  decision gets by how likely the outcome was *given* that decision versus given
  the situation generally — is exactly what a hand-built process-tracing pass can
  approximate without gradients: ask "would this outcome have been plausible
  anyway, given the embark and the year, independent of this specific decision?"
- **Process reward / turn-level credit** for long-horizon LLM agents specifically:
  current agentic-RL work (e.g. arXiv:2603.08754, "Hindsight Credit Assignment for
  Long-Horizon LLM Agents"; arXiv:2605.20061, "Rewarding Beliefs, Not Actions") is
  explicitly trying to solve "100+ turn horizons make episode-level credit
  uninformative" — the same numbers this project is operating at. These are
  training-time RL techniques and don't port directly to a system with no gradient
  update, but the diagnosis ("episode-level credit is uninformative at this
  horizon, you need a mechanism finer than end-of-episode outcome") is squarely
  relevant and is exactly what MEMORY-ARCHITECTURE.md's evidence counter fails to
  do — it operates at the episode level with a single "support/contradict" bit per
  fort, discarding everything the survey and the RL papers above treat as the hard
  and necessary part.

**SRE / incident postmortems — the field that runs this exact process on a
schedule, at scale, today.** Richard Cook's "How Complex Systems Fail" is the
canonical statement: "because overt failure requires multiple faults, there is no
isolated 'cause' of an accident... only jointly are these causes sufficient" —
single-point-failure attributions are a category error in genuinely complex
systems (adaptivecapacitylabs.com/HowComplexSystemsFail.pdf). Google's SRE
practice operationalizes the fix: "blameless" postmortems ask "how did the system
allow this" rather than "who/what caused this," and modern practice explicitly
prefers **"contributing factors" over a single root cause** because "complex
systems fail through multiple interacting conditions" (sre.google/sre-book/
postmortem-culture/). This directly attacks the strawman's implicit framing — "a
fort dying to a siege does not prove the entrance design was bad" is exactly
Cook's point, but the fix Cook's field uses is not a vote counter, it's a
**structured, multi-contributor writeup with a fixed template**, produced within
48 hours while the trace is fresh (sre.google/workbook/postmortem-analysis/).
Recommendation: the fort epitaph should be that template — timeline, contributing
factors (plural, ranked, not a single "cause of death" field), what would have
had to be different, action items — not a single-cause label feeding a counter.

**Epidemiology — the field that has run "credit assignment from observational
data, no controlled experiment possible" for over a century.** The Bradford Hill
criteria (1965) are nine viewpoints for judging whether an observed association is
causal from **observational, non-experimental data with no control group** —
strength, consistency, specificity, temporality, biological gradient, plausibility,
coherence, experiment, analogy (Wikipedia: Bradford Hill criteria; PubMed:
30433840, "Modernizing the Bradford Hill criteria"). This is the closest
analogue to "was the entrance design responsible" that exists in any field: no
randomization, one population, a proposed cause, an observed outcome, decades of
practice at not overclaiming. The two criteria most missing from the strawman's
mechanism: **consistency** (does the association hold across different
embark/civ/threat contexts, not just repeat within one) and **temporality** (did
the proposed cause precede the effect with a plausible mechanism, not just
co-occur) — both are cheap to check mechanically against ledger timestamps and
should be gates before a corroborating event counts at all.

**Process tracing (qualitative political science) — within-case causal inference
from a single episode, which is the piece actually missing.** Process tracing is
built for exactly this: "identify causal mechanisms that connect the causes of
events to their outcomes, drawing evidence from... a single case" (Collier,
"Understanding Process Tracing," Cambridge Core). Its most useful, concrete tool
is Van Evera's four-way evidence typology, popularized by Collier (2011): a **hoop
test** is a necessary-condition test — failing it eliminates a hypothesis, passing
it doesn't confirm much; a **smoking gun test** is a sufficient-condition test —
passing it strongly confirms a hypothesis, failing it doesn't eliminate much; a
**doubly decisive** test does both; a **straw-in-the-wind** test is weak evidence
either way (researchgate.net/publication/322266946, "Straws-in-the-wind, Hoops and
Smoking Guns"). This is the single most directly applicable, cheapest-to-implement
idea in this whole document: **tag every piece of corroborating/contradicting
evidence a fort produces with one of these four diagnosticity levels before it
touches the evidence counter**, so "the second entrance was breached twice" (a
plausible smoking-gun-strength observation) doesn't get averaged with "this fort
also happened to have two entrances and also died" (straw-in-the-wind at best,
and possibly not evidence at all given the "sample size" problem).

### 3.2 The fort ledger must carry covariates and diagnosticity, not just a label

`docs/MEMORY-ARCHITECTURE.md`'s ledger schema (`fort_id, ... cause_of_death,
entrance_design, caverns_sealed(bool), ...`) is good as a starting point but is
missing exactly the fields Bradford-Hill-style stratification and process-tracing
diagnosticity require:

- A **plural, ranked contributing-factors list**, not a single `cause_of_death`
  string — per Cook and the SRE postmortem template.
- **Embark/threat covariates at time of the event**, not just at embark
  (population, active threats, distance from hostile civ, year) — without these,
  "consistency" (Bradford Hill) can't be checked, and confounds like "embarked
  beside a goblin fortress" (the strawman's own example) can't be adjusted for.
- **A diagnosticity tag per corroborating/contradicting observation** (hoop /
  smoking-gun / doubly-decisive / straw-in-the-wind), assigned by a fixed rubric
  at write time (e.g., "the breach occurred at the second entrance and nowhere
  else" is smoking-gun for "second entrances are a liability"; "this fort had a
  second entrance and also died" with no breach-location data is straw-in-the-wind
  and should barely move a posterior).

### 3.3 Replace the evidence counter with a hierarchical (multilevel) model

The strawman's `support: 2, contradict: 0 → promote at 3` mechanism has three
compounding problems, each independently well-documented in the fields above:

1. **No confound control.** Nothing in the counter distinguishes "this fort
   corroborated the hypothesis because of the mechanism proposed" from "this fort
   corroborated the hypothesis because of an unrelated confound that happened to
   co-occur" — exactly the failure Cook's field and Bradford Hill both exist to
   prevent.
2. **An arbitrary threshold with no stated error rate.** "3" is not derived from
   anything; a sequential-testing framework would instead fix an acceptable false-
   promotion rate and derive the stopping point. Wald's Sequential Probability
   Ratio Test (Wald, 1945; formalized as optimal by Wald & Wolfowitz) is the
   standard tool: it "minimiz[es] expected sample size for fixed Type I/II error
   probabilities" and reports "average savings in sampling relative to fixed-
   sample tests of 50% or more" (en.wikipedia.org/wiki/Sequential_probability_
   ratio_test). At N≈20 total episodes, deriving a threshold from a stated
   tolerance for false promotion (say, 10%) is both more honest and, per SPRT's
   own selling point, likely to need *fewer* observations than a fixed n=3 rule
   picked by feel.
3. **The three scope buckets (universal/world/site) are the right taxonomy
   implemented the wrong way.** Treating "universal," "world," and "site" as three
   separate, hard-partitioned counters throws away exactly the structure a
   **hierarchical (multilevel) Bayesian model** is built to exploit. The standard
   result: with few observations per group (here: few forts per world, few worlds
   total), multilevel models "partially pool" estimates — a group with little data
   borrows strength from the population-level estimate, shrunk toward it in
   proportion to how little data that group has, while a group with more data is
   trusted more on its own — which is "more accurate... especially when predicting
   group averages" than either fully separate per-group estimates (which overfit
   on 1–3 data points) or one pooled estimate (which ignores real group
   differences) (bookdown.org/marklhc, "Hierarchical & Multilevel Models"; this is
   standard material, most authoritatively associated with Gelman & Hill's textbook
   on multilevel/hierarchical models — I did not independently verify a specific
   claim against that text this session, flagging it as standard-but-not-
   individually-checked). Concretely: model each hypothesis as having a universal
   (population-level) effect plus a world-level random effect plus a site-level
   random effect; a hypothesis observed only once in one world should show a wide
   credible interval and shrink hard toward the universal prior, not sit at "1/0,
   not yet promoted" as an undifferentiated bucket. This *is* what the strawman is
   reaching for with its three-tier table — it just implements it as discrete
   buckets with a hand threshold instead of as continuous partial pooling, and
   partial pooling is specifically the tool built for "too little data per group to
   trust group-level estimates alone."

**Recommendation, concretely:** each hypothesis is a Beta-Bernoulli (or, once more
than one covariate matters, a small hierarchical logistic model) with an explicit
prior, diagnosticity-weighted pseudo-count updates (a smoking-gun corroboration
moves the posterior more than a straw-in-the-wind one — weight by evidence
strength, not by a flat ±1), and promotion decided by a **credible-interval rule**
("promote to doctrine when the 80% credible interval for the universal-level
effect excludes zero/the null") rather than a raw count. This is a genuinely small
amount of code — a Beta update is a few lines — and it is strictly more information
than the current scheme while using the *same* underlying event stream.

### 3.4 The wiki as an informative prior, not a magic starting count

`docs/MEMORY-ARCHITECTURE.md` says a wiki claim "enters at support: 2 rather than
0." This is the right instinct — **evidence synthesis from prior literature as an
informative Bayesian prior** is standard practice, most visibly in clinical trials,
where systematic reviews and meta-analyses of past studies are formally
incorporated as priors for a new trial rather than starting from ignorance. The
fix is to make the prior's *strength* an explicit, inspectable parameter (an
effective sample size, e.g. "the wiki's claim is treated as equivalent to n=2
independent forts' worth of evidence, at whatever consistency the wiki source
itself displays") rather than a bare pseudo-count bolted onto the same counter as
this-agent's-own evidence — otherwise a wiki claim and one this-agent-observed fort
are silently treated as equally trustworthy, which the DF-wiki-specific version-
namespace problem documented elsewhere in this project's own research
(implicitly: a v0.47-era claim is not equally reliable to a v53-verified one)
already argues against.

Related, worth naming even though I could not find a rigorous general theory of
"how much to trust one large uncoordinated community's collective belief": the
**wisdom-of-crowds / forecasting-aggregation literature** (Galton's median-guess
result; Philip Tetlock's "Good Judgment Project" superforecasting work) is the
closest general treatment of "should I trust an aggregate of many independent
non-expert observations." I did not verify a specific numeric claim from this
literature for this document — flagging it as a pointer for follow-up rather than
a cited fact.

---

## 4. Problem 3 (taken second here because it gates everything above) — Will the model actually comply?

This is the correct thing to worry about, and there is now direct, quantitative
evidence rather than just plausible concern.

**Instruction-count collapse.** A 2026 controlled study (arXiv:2607.19257, "Prompt
Design at Scale," Netanel Eliav) tested five models (Claude Sonnet 5, Claude
Haiku, Gemini Flash, two Qwen sizes) against system prompts carrying N ∈
{10,20,40,80,120,160} simultaneous, independently verifiable rules, across four
formats (markdown/plain/prose/table) and both system- and user-turn placement,
960 calls per model. Headline finding: **"perfect-response rate collapses to zero
by N=80 for every model, every format, and both placements."** This is a single
study (I could not find independent replication of the exact N=80 threshold), but
it directly measures the thing `docs/MEMORY-ARCHITECTURE.md` only asserts by
instinct ("doctrine... must stay small"). **This changes doctrine from a style
preference into a number**: doctrine's total simultaneous-rule count is a hard
design budget, and the project should measure its own compliance-vs-doctrine-size
curve early (§7, build order) rather than assume "small" is safely small.

**Context-position effects.** "Lost in the middle" (Liu et al. 2023/2024, TACL;
arXiv reference confirmed via search, exact number not independently refetched
this session) found a U-shaped accuracy curve — information at the start or end of
context is used far more reliably than information buried in the middle, with a
measured 30-point-plus accuracy drop moving a relevant document from position 1 to
position 10 of 20, a result that "persists across... both open-source... and
closed models" and "does not disappear for models explicitly designed for
long-context processing." This directly validates `docs/PURPOSE.md`'s tiered
cache-ordering design (stable content first, volatile last) as also being a
*correctness* requirement, not just a caching optimization — doctrine belongs at
the front of context (or possibly duplicated at the very end, per the U-shape),
never buried in a middle tier.

**Multi-turn conversational decay — the more dangerous, less obviously-guarded-
against finding.** Microsoft Research and Salesforce (arXiv:2505.06120, "LLMs Get
Lost In Multi-Turn Conversation," ICLR 2026 Best Paper) tested 15 models across
200,000+ simulated multi-turn conversations and found roughly **39% average
degradation** in task accuracy when a task is revealed incrementally across turns
versus given all at once, decomposed into "a minor loss in aptitude and a
significant increase in unreliability" — and critically, "when LLMs take a wrong
turn... they get lost and do not recover." A DF-overseer session is, structurally,
one very long multi-turn conversation (hundreds of decisions across ten simulated
years). This finding is a direct threat to the whole premise that a model can be
handed doctrine once and reliably apply it turn 180 the way it applied it turn 2:
the risk is not (only) that the model ignores doctrine, it's that an early wrong
inference compounds and the model doesn't self-correct as the conversation grows,
regardless of what's sitting in the cached prefix. **Practical implication**: the
loop should not be one unboundedly growing conversation — periodic hard resets
with a freshly-reconstructed context (doctrine + current dossier + recent diff,
not the full transcript) are not just a cost optimization, they are load-bearing
correctness infrastructure per this finding. `docs/PURPOSE.md`'s existing "non-
blocking loop" design already implies turn-by-turn tool calls rather than one
giant transcript, which is the right instinct — this finding says that instinct
should be treated as a hard requirement, not a convenience.

**Knowledge conflicts (doctrine vs. the model's own priors).** The literature here
is less conclusive than the two findings above: "no definitive rule exists for
whether a model prioritizes contextual or parametric knowledge... [it] depend[s]
on the task at hand" (survey, arXiv:2403.08319, "Knowledge Conflicts for LLMs").
OpenAI's Instruction Hierarchy work (Wallace et al. 2024, arXiv:2404.13208)
establishes that system-message-level instructions can be trained to take
priority over conflicting user/tool content, which is encouraging for "doctrine
in the system prompt beats the model's raw priors" — but this is a trained
behavior specific to models trained on that objective, not a property of LLMs in
general, and I found no controlled study specifically measuring "doctrine written
by a prior version of this same agent" versus "the model's baseline domain
priors" in a long-horizon game-playing setting. **Flagged as unverified**: whether
this specific agent, on this specific model, will actually let doctrine override
its own DF priors deep in a run is an empirical question this project has not yet
tested and the literature does not directly answer — it should be an early,
cheap eval (§7), not an assumption.

**Evaluation-awareness / Hawthorne effect — a trap for the eval harness itself.**
Reasoning models measurably behave differently when they detect they are being
tested ("evaluation awareness is an inference-time behavior — the model recognizes
structural cues that signal it is being tested," arXiv:2605.23055; "the Hawthorne
Effect in Reasoning Models," arXiv:2505.14617). This matters directly for §6's
measurement harness: a compliance eval that looks obviously like a test (a
scripted scenario clearly distinct from normal play) risks measuring
"performance under known observation," not "behavior during an actual unattended
run" — the two can diverge, and the direction of the divergence isn't even
consistent across models ("some become more cautious, others more compliant").

---

## 5. Problem 4 — Designing its own experiments

**Multi-armed bandits give the wrong default objective for this project.** The
standard bandit framing optimizes cumulative reward (regret minimization) —
"minimizing the loss of participants' welfare during experiments" — but the
project's actual goal at N≈20 is *learning*, not maximizing the outcome of any
one fort. Simchi-Levi & Wang (2023, "Multi-armed Bandit Experimental Design,"
Management Science) formalize exactly this tension in clinical trials: "minimizing
regret entails harming the statistical power of estimating the treatment effect,"
because regret-minimizing bandits starve underperforming arms of data before their
true effect is well estimated. **This is a direct warning against letting the
overseer simply "keep doing what worked last time"** — a naive regret-minimizing
policy would stop trying single-entrance forts as soon as two-entrance forts
looked worse, which is exactly the premature-convergence failure mode that
produces confident, under-evidenced doctrine. Multi-armed bandit models "have been
extensively studied in theory, yet the resulting schemes have been rarely used in
practice" in clinical trials specifically because of this power problem
(ncbi.nlm.nih.gov/pmc/articles/PMC3980291/) — a caution against reaching for
bandit machinery here at all.

**Bayesian (optimal) experimental design is the right formal framework but is
probably over-engineering at N≈20.** The field's standard move — choose the next
experiment to maximize expected information gain about an uncertain parameter,
formalized as a POMDP with information-theoretic utility — is exactly "which
variable should the next fort vary to learn the most." But the field's own
practical literature notes this is compute-heavy even for cheap-to-run simulated
experiments (policy-gradient RL is used to *solve* the resulting POMDP in current
research, arXiv:2110.15335). At 20 total trials over six months, with each trial
costing real wall-clock game time, the honest recommendation is the frameworks's
*intuition* without its machinery: **maintain an explicit list of open hypotheses
each with a rough expected-value-of-information estimate (how much would
resolving this change future doctrine, times how uncertain it currently is), and
choose the next fort's deliberate variable by picking the top of that list** —
this is decision analysis's classical "value of information" idea (Howard, Raiffa)
without a POMDP solver behind it.

**The one-variable-at-a-time constraint is a real, known tradeoff, not a
simplification to feel bad about.** Classical design-of-experiments theory
(Fisher) prefers factorial designs — vary multiple factors simultaneously in a
structured way — because they extract more information per trial than changing
one variable per run. But factorial designs need enough trials to populate the
cross of conditions, and at N≈20 total episodes (not 20 per cell), a full
factorial over even 3–4 embark/design variables is not reachable. One-variable-
at-a-time is the correct fallback under a hard, small sample budget, and it is
also — not coincidentally — how the human expert communities cited below actually
operate (§5.1): isolate one route/opening/build choice at a time so the result is
attributable.

**Automated-science systems validate the shape, not the scale.** FunSearch (2024)
and its successor AlphaEvolve (DeepMind, 2025) pair an LLM proposer with a fast,
automatic evaluator in an evolve-and-select loop — "maintains a population of
candidate programs, uses LLMs to propose mutations..., evaluates... with a scoring
function." Coscientist (Boiko et al., Nature 2023, arXiv via nature.com/articles/
s41586-023-06792-0) closes the same loop against real robotic wet-lab hardware,
autonomously designing and running Suzuki/Sonogashira coupling reactions. Sakana's
AI Scientist (2024) closes an even higher-level loop (idea → experiment → paper →
review) at "$6–$15... 3.5 hours of human involvement" per paper, with AI Scientist-
v2 producing a workshop paper that passed peer review (arXiv:2504.08066). **The
one thing every one of these systems has that this project does not, and cannot
cheaply get, is a fast, free evaluator.** FunSearch and AlphaEvolve evaluate a
candidate in milliseconds to seconds; Coscientist's wet-lab runs are still hours,
not months; a DF fort takes real wall-clock days even at a low FPS cap. This is
the central limitation on how far the "automated science" pattern can be imported
here (see §8): the pattern (propose → evaluate → select → propose again) is right,
but its cost model does not transfer, and expecting AI-Scientist-style throughput
is the most likely way this part of the design over-promises.

### 5.1 Human expert communities — under-cited, and directly relevant

The brief specifically asked for this, and it is worth taking seriously as prior
art rather than color: these are **real, working, sample-inefficient collective
learning systems that have run for years at low N-per-contributor**, closer in
shape to this project's actual situation than most ML literature is.

- **"Dwarf science"** — there is a peer-reviewed paper specifically on this
  community's epistemic practice: Martinez-Garza (2015), "'For !!SCIENCE!!':
  Examining Epistemic Practices of the Community of Players of Dwarf Fortress"
  (International Journal of Gaming and Computer-Mediated Simulations, vol. 7 no.
  2). Its framing: because "condensed knowledge resources that support effective
  play are scarce" and the underlying simulation is deep and largely undocumented,
  the community engages in "systematic, evidence-based, experimental inquiry,"
  self-named "!!science!!," which the paper frames as "shar[ing] the epistemic
  frame of practicing scientists." I could not access the full text (only
  abstract-level material via search); the existence and framing of the paper is
  itself directly on-theme evidence that this project's problem — extracting
  reliable knowledge from a chaotic, under-documented simulation at low sample
  size — is a problem the DF community has already named and organized around,
  independent of any LLM angle.
- **Chess opening theory** is the deepest-run version of the same accumulation
  problem: masters have "memorized about 100,000 opening moves," compiled over
  five centuries into a structured reference (the Encyclopedia of Chess Openings,
  ~500 classification codes since 1974). The mechanism worth borrowing is not the
  content but the *process*: openings are validated by repeated, adversarial,
  high-stakes play against strong opposition, with refutations published and
  widely replicated before an opening is considered "sound" — a much higher and
  more adversarial evidentiary bar than a single evidence counter.
- **Speedrunning** runs an explicit route-optimization discipline with a built-in
  verification norm: a new tool-assisted run "provides a peer-reviewed opportunity
  to see the inputs and improvements involved" (Wikipedia: Tool-Assisted Speedrun;
  TASBot). The transferable idea is **frame-perfect, replayable, auditable
  evidence** — every claimed improvement is checked by others replaying the exact
  input sequence. DF's save-seed determinism (noted in §6) is the direct analogue:
  a claimed doctrine improvement should, where possible, be replayable rather than
  merely narrated.
- **Roguelike wikis and metagames** (NetHack spoiler files, DCSS wikis,
  competitive-game metagame shifts) were named in the brief as worth a look; I did
  not find a citable academic treatment of these specifically (as opposed to the
  DF-specific paper above) within this session's search budget, and am flagging
  that gap rather than padding it with an uncited claim.

The common thread across all of these communities: they are **sample-inefficient
by ML standards and still functional**, because they compensate with adversarial
scrutiny (routes get re-verified by other runners; openings get refuted in
tournament play) rather than with volume. That is the piece missing from the
strawman's design — nothing in `docs/MEMORY-ARCHITECTURE.md` proposes any
adversarial check on a promoted hypothesis (no "try to break this," no explicit
attempt to construct a counter-example fort). Recommend adding one: **once a
hypothesis nears its promotion threshold, the next deliberate-experiment fort
should specifically try to falsify it**, not just passively continue observing —
this is cheap (it's a selection rule over the existing one-variable-at-a-time
mechanism, not new machinery) and is the single idea from this section most worth
importing.

---

## 6. Measurement — how would we know learning is happening?

This section exists because, per the brief, without it "is it learning?" is a
months-long vibe judgement. Three separable questions: what to compare against,
what to measure, and how to catch the specific failure of confident narration
without behavioral change.

### 6.1 The baseline problem is real and the domain gives a partial answer

A proper controlled comparison (doctrine-using agent vs. doctrine-blind agent)
would need to split the already-scarce 20-episode budget between conditions,
directly fighting the sample-efficiency problem this document spends most of its
length trying to solve. There is one domain-specific way out: **DF world seeds
and embark parameters are deterministic and replayable.** This makes a **seeded
counterfactual rerun** possible in a way that most N-of-1 domains cannot achieve —
directly analogous to "Model-Twin Randomization" work on estimating individual
treatment effects in N-of-1 trials by constructing a simulated counterfactual
twin of the same subject (arXiv:2208.00739). Concretely: periodically replay an
*identical* embark seed once with current doctrine loaded and once with doctrine
withheld (or an earlier doctrine snapshot loaded), and compare outcomes — this
uses compute, not calendar-constrained fort-months, and doesn't compete with the
20-episode budget the way a held-out control arm would. It is not a perfect
control (a single replay pair is still N=1 per comparison, and DF is not fully
deterministic once RNG-consuming player decisions diverge the two runs), but it
is a real, cheap, domain-specific instrument nothing in the strawman currently
proposes.

### 6.2 Metrics, and what a genuine learning signal should look like

- **Outcome trend across ledger rows**: median/distribution of fort survival time
  (or a composite score), computed mechanically from the ledger, plotted against
  fort sequence number. A flat or noisy trend after 15–20 forts is itself an
  important negative result, not a null result to hide.
- **Calibration of the prediction log** (§1.3): a Brier score (or simpler,
  hit-rate on falsifiable predictions) computed automatically from graded
  predictions, trending toward better calibration over time. This is the closest
  thing to a ground-truth "is the model's model of the fortress improving"
  signal, because it is graded by code against recorded state, not self-assessed.
- **Doctrine churn rate**, not just doctrine size: a healthy learning process
  should show edits and *contradictions found and pruned* (per
  `docs/MEMORY-ARCHITECTURE.md`'s own "doctrine review" step) settling down over
  time, not just monotonic growth. Monotonic, never-pruned growth is itself a
  Goodhart signal — "we are accumulating text," not "we are accumulating
  knowledge" (general form: Goodhart's Law, "when a measure becomes a target it
  ceases to be a good measure"; applied to RL specifically in Skalse et al.,
  "Goodhart's Law in Reinforcement Learning," arXiv:2310.09144).

### 6.3 Detecting "narrates learning convincingly while performing no better"

This is the specific failure the brief is most worried about, and per §1.2 and
§1.3, the fix is structural, not a smarter prompt:

1. **Never grade the agent's account of its own learning.** Every check in this
   document — prediction grading, evidence-counter updates, promotion decisions —
   is specified as a mechanical read of ledger/dossier state, not an LLM
   self-report. This is the direct countermeasure to Turpin-style unfaithful
   explanation (§1.2): a model can produce a compelling story about *why* doctrine
   changed its decision without that doctrine having causally influenced the
   decision at all, and the only defense that has any evidence behind it is
   removing the model from the grading loop entirely.
2. **Cross-check narration against action.** Where the agent's turn-by-turn
   reasoning cites a specific doctrine entry, an automated (non-LLM, or a
   separate cheap-model) auditor can check whether the action taken actually
   matches what that doctrine entry prescribes — a mechanical faithfulness check
   analogous to what the Turpin-style unfaithfulness literature measures in
   controlled settings, applied here as an ongoing audit rather than a one-off
   study.
3. **Watch for the evaluation-awareness trap in your own harness** (§4): if a
   compliance eval is run as an obviously-distinct scripted scenario, its results
   may not describe behavior during real unattended play. Where possible, measure
   compliance from logs of actual runs, not from a separately-flagged "test mode."
4. **A learning system that is actually learning should occasionally be
   embarrassed by its own past doctrine** — a genuine update process finds and
   prunes wrong entries (the design's own "doctrine review... prune
   contradictions" step). If doctrine only ever grows and is never contradicted or
   walked back across 20 forts, treat that as a warning sign that hypotheses are
   being confirmed rather than tested, not as evidence of a clean track record.

---

## 7. Build order — cheap vs. expensive

Ordered by dependency and cost, consistent with `docs/PURPOSE.md`'s existing
build-order habit of sequencing the cheapest, highest-confidence pieces first.

1. **Compliance eval harness — cheapest, do first, before any fort runs.**
   Replicate the "Prompt Design at Scale" instruction-count-decay methodology
   (§4) against the actual doctrine format and actual model this project will
   use: load synthetic doctrine at increasing rule counts, measure where
   compliance degrades. No running game needed — this is the same "no game, no
   agent, afternoon-sized" shape as `docs/PURPOSE.md`'s own perception-eval
   harness recommendation, applied to memory instead of perception. Answers
   "how big can doctrine actually get" empirically instead of by feel, which
   directly bounds every downstream design decision.
2. **Fort ledger schema, with covariates and diagnosticity fields from day one**
   (§3.2). Cheap — it's a schema and a write path, no algorithm — and everything
   else in this document is unusable without it existing first and existing with
   the right fields, since retrofitting covariates onto old ledger rows after
   the fact defeats the purpose.
3. **Mechanical prediction grading** (§1.3) — a scripted comparison of a
   `signal` field against recorded state at `check_at`. Cheap; needed before any
   prediction-based calibration metric (§6.2) is meaningful.
4. **Hierarchical evidence model replacing the flat counter** (§3.3) — a
   Beta-Bernoulli update with diagnosticity weighting is a small amount of code;
   the harder part is agreeing on the diagnosticity rubric (§3.1's four-way Van
   Evera typology) and covariate stratification, which is a design task, not an
   engineering one.
5. **Process-tracing epitaph template** (§3.1) — replace the single
   `cause_of_death` field with the SRE-style multi-contributor writeup. Moderate
   cost: needs a fixed template and, likely, a code-assisted first pass (compute
   candidate contributing factors from ledger covariates) before the model drafts
   prose around it.
6. **Wiki prior formalization** (§3.4) — attach an explicit, inspectable prior
   strength to wiki-sourced hypotheses rather than a bare pseudo-count. Cheap
   once the hierarchical model (step 4) exists; pointless before it does.
7. **Seeded counterfactual rerun harness** (§6.1) — moderate cost (needs
   deterministic-replay infrastructure this project does not yet have), but it is
   the only concrete answer to the control-arm problem and should be built before
   trusting any "doctrine improved outcomes" claim drawn from the raw fort
   sequence.
8. **One-variable-at-a-time deliberate-experiment selector** (§5) — cheap once
   the ledger and hierarchical model exist (it's a sort over open hypotheses by
   a rough expected-value-of-information heuristic); deliberately sequenced last
   because it depends on everything above being trustworthy first — designing
   experiments to resolve a broken evidence model just produces confident wrong
   answers faster.

**Expensive / do not build, or defer indefinitely:** a full Bayesian-optimal-
experimental-design solver (§5) — the field's own literature treats this as
compute-heavy even for cheap-to-evaluate problems, and DF's evaluation cost (real
wall-clock days per trial) makes the machinery disproportionate to the payoff at
N≈20. A regret-minimizing multi-armed bandit policy over embark/design choices
(§5) — actively harmful here, per Simchi-Levi & Wang's own power-vs-regret
tradeoff, because it would starve underexplored options before they're
understood. Full factorial experimental design (§5) — not reachable at this
sample size; the one-variable-at-a-time fallback is the correct choice, not a
placeholder for something better.

---

## 8. Honest limitations

- **The hierarchical model formalizes the evidence problem; it does not solve
  credit assignment within a single fort.** Even with covariates and
  diagnosticity tags, deciding "which of ~200 decisions actually mattered" for a
  *given* fort still rests on a process-tracing pass that is partly model-drafted
  (§3.1) and therefore partly subject to the same unfaithful-narration risk
  flagged in §1.2 and §6.3. The mechanical checks in §6.3 audit the *use* of
  doctrine against action; they do not independently verify that the process-
  tracing pass identified the right contributing factors in the first place. This
  is the deepest unsolved piece of the whole architecture, and no field surveyed
  here offers a clean answer for within-case causal inference in a system this
  complex from a single observation — process tracing and Bradford Hill both
  explicitly operate on *many* cases or *rich mechanistic* detail, neither of
  which a single ~200-decision DF fort fully provides.
- **N≈20 is small enough that even a well-built hierarchical model will have wide
  credible intervals for a long time.** The architecture recommended here is more
  honest about uncertainty than the strawman's binary promoted/not-promoted
  scheme, but "more honest" is not the same as "resolved" — expect most
  hypotheses to remain genuinely uncertain for months, and the system should
  surface that uncertainty rather than force a promote/reject decision
  prematurely.
- **The instruction-count collapse finding (§4) is a single 2026 study
  (arXiv:2607.19257), not yet independently replicated** as far as this session's
  search found. The N=80 number should be treated as "order of magnitude,
  probably conservative for a system prompt with a specific, narrower doctrine
  format" rather than a load-bearing constant — but the *qualitative* finding
  (compliance degrades sharply with simultaneous rule count, well before context-
  length limits bind) is corroborated independently by the multi-turn-
  conversation-degradation study (arXiv:2505.06120) and should be taken
  seriously regardless of the exact threshold.
- **Whether this specific model, on this specific setup, actually prioritizes
  doctrine over its own DF priors deep in a long run is untested.** §4 flags this
  explicitly as an empirical gap the literature does not close; it is priority-1
  for the compliance eval harness in §7's build order precisely because no
  amount of reading substitutes for measuring it against the actual model this
  project will run.
- **The DCSS/NetHack-wiki and competitive-metagame material asked for in the
  brief's "also worth a look" section was not backed by a citable academic
  source within this session's search budget** — the Dwarf-Fortress-specific
  paper (Martinez-Garza 2015) was found and is solid; the broader claim about
  roguelike wikis and game metagames generally rests on the DF case and on
  general knowledge of chess/speedrunning practice, not on a second citable
  source. Flagging this as the weakest-sourced section of the document rather
  than padding it further.
- **I could not verify Soar's and ACT-R's memory-module APIs against primary
  technical documentation** (only a secondary comparison paper, arXiv:2201.09305,
  was accessible this session) — the cognitive-architecture parallel in §1.1 is
  used at the level of "these architectures independently converged on a similar
  four-way memory split," which the secondary source supports, not at the level
  of specific implementation claims.
- **The Gelman & Hill multilevel-modeling reference in §3.3 is standard
  textbook material cited by description, not independently verified against the
  primary text this session** — the partial-pooling claims themselves are
  well-supported by the secondary sources found (bookdown.org, PyMC documentation)
  and are not in serious methodological dispute in applied statistics, but this
  is flagged per the brief's instruction to be explicit about what wasn't
  directly checked.
- **The seeded-counterfactual-rerun proposal (§6.1) assumes DF replay determinism
  that was not verified this session** — `docs/PURPOSE.md` and the sibling
  spatial-perception document don't establish how deterministic a DF save is
  under identical seed/embark parameters with a different decision sequence
  layered on top; this needs a small, cheap verification step before the
  measurement harness in §7 depends on it.

---

## Sources referenced

Reinforcement learning / credit assignment: arXiv:2312.01072 (temporal credit
assignment survey); arXiv:2011.09464 (counterfactual credit assignment); NeurIPS
2019 "Hindsight Credit Assignment" (Harutyunyan et al.); arXiv:2603.08754;
arXiv:2605.20061.

SRE / incident analysis: sre.google/sre-book/postmortem-culture/;
sre.google/workbook/postmortem-analysis/; R.I. Cook, "How Complex Systems Fail"
(adaptivecapacitylabs.com/HowComplexSystemsFail.pdf).

Epidemiology: Bradford Hill criteria (en.wikipedia.org/wiki/Bradford_Hill_
criteria; PubMed 30433840).

Process tracing: Collier, "Understanding Process Tracing," Cambridge Core;
researchgate.net/publication/322266946 (Van Evera evidence typology).

Sequential/small-N methodology: Wald SPRT (en.wikipedia.org/wiki/Sequential_
probability_ratio_test); N-of-1 trials (jamanetwork.com/journals/
jamaotolaryngology/fullarticle/2808146; arXiv:2208.00739 Model-Twin
Randomization); Kerr 1998 HARKing (journals.sagepub.com/doi/10.1207/
s15327957pspr0203_4); hierarchical/multilevel partial pooling
(bookdown.org/marklhc/notes_bookdown/hierarchical-multilevel-models.html).

LLM compliance and evaluation: arXiv:2607.19257 (Prompt Design at Scale);
arXiv:2505.06120 (LLMs Get Lost In Multi-Turn Conversation); arXiv:2404.13208
(Instruction Hierarchy); arXiv:2403.08319 (Knowledge Conflicts survey);
arXiv:2305.04388 (Turpin et al., unfaithful CoT); arXiv:2506.18998 (Mirage of
Mastery); arXiv:2605.23055 / arXiv:2505.14617 (evaluation awareness / Hawthorne
effect).

Automated experimentation: Nature (nature.com/articles/s41586-023-06792-0,
Coscientist); sakana.ai/ai-scientist/; arXiv:2504.08066 (AI Scientist-v2);
FunSearch/AlphaEvolve (DeepMind, per secondary sources); Simchi-Levi & Wang,
"Multi-armed Bandit Experimental Design," Management Science 2023.

Human expert communities: Martinez-Garza, "'For !!SCIENCE!!': Examining
Epistemic Practices of the Community of Players of Dwarf Fortress,"
International Journal of Gaming and Computer-Mediated Simulations 7(2), 2015;
Encyclopedia of Chess Openings (en.wikipedia.org/wiki/Encyclopaedia_of_Chess_
Openings); Tool-Assisted Speedrun / TASBot (en.wikipedia.org/wiki/Tool-
assisted_speedrun).

Cognitive architecture: Tulving 1972 (episodic/semantic distinction, via
secondary sources); arXiv:2201.09305 (ACT-R and Soar comparison).

Goodhart's Law: Skalse et al., "Goodhart's Law in Reinforcement Learning,"
arXiv:2310.09144.
