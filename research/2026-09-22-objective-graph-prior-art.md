# Objective graph prior art: default flow with conditional deviations

Date: 2026-09-22
Companion to `docs/AGENT-LOOP.md` §6 ("Objectives: a default flow with
deviations"), `docs/MEMORY-ARCHITECTURE.md` (doctrine provenance, playbooks,
cross-fortress learning) and `docs/AGENT-ARCHITECTURE.md` §4 and §10 (closed
vocabularies, predictions, measured track record).

Status: research, not implemented. Dispatched from a design conversation
still in progress (`docs/AGENT-LOOP.md` §6 is marked "in design"); this spec
feeds that design, it does not replace it.

## 0. Recommendation, stated first

Adopt a hybrid of three things, each independently verified against a
primary source this session:

1. **FHIR PlanDefinition's action/condition/relatedAction shape** for the
   objective graph itself: typed applicability conditions, a closed set of
   ordering relations with an offset, and a selection-behavior vocabulary for
   "these are alternatives" versus "these all happen." PlanDefinition is a
   purpose-built standard for exactly this problem (a template applied per
   instance) and its template-versus-applied-plan split is the same split
   this repo already proposed independently: a progression template that
   survives across forts, and a per-fort agenda instantiated from it.
2. **CQL's three-valued logic** (true / false / null-meaning-unknown) as the
   semantics for evaluating a deviation rule's `when` clause. This is a
   ready-made, standards-body-specified answer to the brief's requirement
   that a rule "report unknown rather than guess": an unknown input makes the
   rule not fire, and the miss gets logged, rather than silently defaulting
   to false.
3. **RTS build-order "blocks" and "convergent points"** (a community
   practitioner concept, not academic, but the closest structural match
   found to "default flow plus swap-at-a-trigger that rejoins the main
   line") for the idea that a deviation should be understood as: leave the
   default flow at a named point, and rejoin it at a named point, rather
   than diverging permanently. Recommend adopting "convergent point" as a
   design term: every deviation names where it rejoins the default flow.

Deviation actions that recur across every field surveyed: **insert, skip,
reorder (move earlier / move later), substitute, repeat**. Construction
scheduling adds a distinct fifth that is worth keeping separate from those:
**timing_shift**, a deviation that changes only *when* without touching the
graph's shape at all. A schema that conflates "the date moved" with "the
plan changed" loses information a baseline-versus-as-built discipline treats
as fundamentally different.

Applicability conditions should be **boolean expressions over a fixed,
named set of facts, never a scripting language**, evaluated with three-valued
logic. Every computer-interpretable guideline (CIG) formalism surveyed
converges on some version of this; the one directly-verified finding about a
formalism failing by over-expressiveness is subtler than "it broke": a
peer-reviewed comparison of six CIG languages found none of them approach
general business-process-modeling expressiveness, and the authors floated
whether guideline modeling should just adopt general BPM tooling instead.
That the field's own answer leaned toward staying narrower rather than
generalizing is corroborating evidence for this repo's existing instinct
(the doctrine-size compliance ceiling in `docs/MEMORY-ARCHITECTURE.md`), by
a different mechanism (analyzability and predictability of a closed
vocabulary, rather than context-window budget), which makes it worth citing
as independent support rather than a restatement.

Variance capture: record ad hoc Overseer departures with the same action
vocabulary as a deviation rule (insert/skip/substitute/...), a required
reason, and an optional evidence reference. Promotion of a recurring variance
into a real deviation rule should **reuse the doctrine revision path this
repo already settled on** (`docs/MEMORY-ARCHITECTURE.md`, "Doctrine store";
`research/2026-08-25-learning-architecture.md`'s diagnosticity-weighted
evidence, not a vote count), not invent a second promotion mechanism. This
repo already rejected `support >= 3` counters once; nothing in clinical
variance analysis, which is the field that has actually run this loop at
scale for decades, gives a reason to reconsider that rejection. Notably, the
literature search this session could not pin down a single well-cited
primary source for a specific evidence-threshold rule in clinical pathway
variance-to-revision practice either. Where sources describe the step at
all, they describe *committee review of aggregated variance data*, not a
formula. Treat this as mild corroboration that a mechanical count-threshold
is not actually the field-standard approach anywhere it was checked, medical
practice included.

Timing: keep two separate mechanisms rather than one. **Ordering** is
structural (prerequisite edges, same idea as a construction CPM dependency
graph: the graph shape *is* the ordering, no separate "order" field needed).
**Deadlines and windows** ("before winter") are a relative offset from a
named reference fact or objective, the same shape as Asbru's time
annotation, simplified: `(offset_ticks, reference)` rather than Asbru's full
seven-component uncertainty-bounded tuple, which is more machinery than this
project needs since the uncertainty in this domain is about the game state,
not about the timing model itself.

A minimal schema sketch is in §6. What to leave out of an MVP is in §6 too,
with reasons per omission rather than a bare list.

---

## 1. Clinical pathways and integrated care pathways (ICPs)

**What a variance is**, moderately well corroborated across several
sources: a documented deviation between the pathway's expected course and
what actually happened, recorded with an occurrence date, a classification
code, and free text describing the reason
([Ovid/DCCN, "Using variance tracking to improve outcomes"](https://www.ovid.com/jnls/dccnjournal/abstract/00003465-200103000-00009~using-variance-tracking-to-improve-outcomes-and-reduce-costs);
[PubMed 11207952, "Variance analysis in clinical pathways for total hip and
knee joint arthroplasty"](https://pubmed.ncbi.nlm.nih.gov/11207952/);
[ScienceDirect, "Integrated Care Pathway" overview](https://www.sciencedirect.com/topics/nursing-and-health-professions/integrated-care-pathway)).
Confidence: moderate. These were read via search-result summaries, not
independently fetched full text (several are paywalled or ResearchGate-gated
and refused a direct fetch), so the exact wording is not independently
checked, but the description is consistent across four to five unrelated
sources.

**Classification.** Multiple secondary summaries describe variances as
categorized "by source" and split into serious/non-serious, and gesture at
a patient/clinician/system-style split without a source that states it
cleanly as a named taxonomy with attribution. I ran several targeted
searches specifically to pin down a primary citation for a
patient/practitioner/system three-way split (a shape I expected to find,
given how often it is alluded to in nursing literature) and could not
independently verify one this session. **This is a real gap, not a
paper-over**: report it as unverified rather than asserting the taxonomy as
settled. What is corroborated, from the same set of sources, is only the
coarser claim that variances get a source/category code and a
serious/non-serious flag.

**How variance feeds pathway revision.** The clearest single sentence found
was from the Wikipedia "Clinical pathway" article's variance section: "The
combined variances for a sufficiently large population of patients are then
analysed to identify important or systematic features, which can be used to
improve the next iteration of the pathway"
([Wikipedia, Clinical pathway](https://en.wikipedia.org/wiki/Clinical_pathway)).
Flag confidence low-to-moderate: this is a tertiary source and its own
variance section carries no inline citation, though the claim is consistent
with everything else surveyed. Multiple independent summaries additionally
describe a "pathway committee" or "pathway team" doing this review on a
cadence, not per-instance
([ScienceDirect ICP overview](https://www.sciencedirect.com/topics/nursing-and-health-professions/integrated-care-pathway)).
No source gave a mechanical promotion threshold; where a mechanism is
described at all, it is committee judgment over aggregated data, which is
closer to this repo's existing doctrine-revision design (proposal, ruling,
evidence) than to a vote counter.

**Relevance to this repo's design.** Corroborates the existing plan rather
than adding a new mechanism: variance is captured at the instance level, tied
to a specific step, carries a reason, and is reviewed in aggregate rather
than acted on the moment it recurs a fixed number of times.

**Not verified**: the specific patient/clinician/system variance taxonomy;
any specific avoidable/unavoidable or positive/negative variance
sub-classification (alluded to in search summaries of the ScienceDirect
overview but not confirmed by an independently fetched primary source); any
quantitative revision-trigger threshold (none found, possibly because none
exists as a general standard).

---

## 2. Computer-interpretable guideline (CIG) formalisms

This is the best-verified section: four primary sources were fetched and
read directly rather than summarized secondhand.

### FHIR PlanDefinition (verified: fetched directly from the HL7 spec)

Read from [`hl7.org/fhir/R4/plandefinition.html`](https://hl7.org/fhir/R4/plandefinition.html)
directly, high confidence:

- `action.condition[]`: `kind` is a closed code, `applicability | start |
  stop`, paired with an `expression` (a boolean-valued CQL or FHIRPath
  expression). The `kind` field is itself a small closed vocabulary for
  *when in the action's lifecycle* the condition is checked, distinct from
  the condition's content.
- `action.trigger[]`: a `TriggerDefinition`, fired by a named event or a
  workflow point being reached.
- `action.relatedAction[]`: `actionId` (reference to another action) +
  `relationship`, a closed code with nine values (`before-start | before |
  before-end | concurrent-with-start | concurrent | concurrent-with-end |
  after-start | after | after-end`) + an optional `offset` (`Duration` or
  `Range`). This single field is where ordering and timing live together:
  "30 to 60 minutes before" is `relationship: before-end, offset: 30-60 min`.
  It directly answers the brief's "how do these fields handle timing
  alongside ordering" question: they do not treat them as separate
  mechanisms, they attach a magnitude to a relation.
- `action.selectionBehavior`: `any | all | all-or-none | exactly-one |
  at-most-one | one-or-more`, applied to a group of child actions. This is
  the structural answer to "is this an insertion alongside the default, or
  a substitution for it": mutually exclusive alternatives are
  `exactly-one`, an addition is `any` or `all`.
- Actions nest hierarchically into groups, each of which can carry its own
  condition and selection behavior.

**Why this earns first place in the recommendation**: PlanDefinition is
explicitly built for "a pre-defined group of actions to be taken in
particular circumstances, often including conditional elements, options,
and other decision points," applied to a specific patient through a
`$apply` operation that produces a `CarePlan`/`RequestGroup` instance. That
template-to-applied-instance split is exactly the "two lifetimes" shape
`docs/AGENT-LOOP.md` §6 already proposes (a progression template that
survives across forts, a per-fort agenda instantiated from it), arrived at
independently by a different design process. Treat this as corroboration of
an already-agreed direction, not a new idea to evaluate.

### PROforma (verified: fetched directly, "The Syntax and Semantics of the
PROforma Guideline Modeling Language," PMC)

Read from [`pmc.ncbi.nlm.nih.gov/articles/PMC212780`](https://pmc.ncbi.nlm.nih.gov/articles/PMC212780/)
directly, high confidence:

- Four task classes: **Action**, **Enquiry**, **Decision**, **Plan**.
- A `Decision` holds `candidates[]`, and each candidate holds `arguments[]`:
  a truth-valued expression plus a caption, for or against that candidate.
  A recommendation rule combines the arguments into which candidate is
  recommended. This is notable because it collapses two things the brief
  asks for separately, the applicability condition and the retained
  rationale, into one structure: the "because" a decision fired *is* its set
  of arguments, not a free-text field bolted on afterward. Worth stealing
  directly: a deviation rule's `because` could literally be the set of facts
  that made its `when` clause true, rendered as prose, rather than a
  human-authored sentence that can drift out of sync with the logic.
- Preconditions and scheduling constraints are both **truth-valued
  expressions over a closed relation vocabulary**, not arbitrary code: "task
  X must wait until task Y has completed" is the shape, not a general
  scripting hook.
- Task states are a closed set: `dormant -> in_progress ->
  completed | discarded`; plans additionally carry abort/termination
  conditions, themselves truth-valued expressions.

### Asbru (verified: fetched directly, Miksch and Shahar's primary Asbru
paper)

Read from [`cvast.tuwien.ac.at/.../mik_keml97.pdf`](https://www.cvast.tuwien.ac.at/sites/default/files/bibcite/220/mik_keml97.pdf)
directly, high confidence:

- **Time annotation**: `([ESS, LSS], [EFS, LFS], [MinDu, MaxDu],
  REFERENCE)`, bounds on earliest/latest start, earliest/latest finish, and
  minimum/maximum duration, all anchored to a `REFERENCE`, which may be
  absolute, relative, or domain-dependent (an external event). This is the
  formal, citable answer to "before winter": `REFERENCE` is the
  season-change-to-winter fact, and the start bounds are negative offsets
  from it, rather than a hardcoded tick number computed once and left to
  rot as the world's actual pace changes. Recommend simplifying rather than
  adopting whole: this project does not need uncertainty bounds on its own
  timing model (DF's clock is exact), so a two-field `(offset_ticks,
  reference)` captures the useful part without the four-bound machinery
  Asbru needed for a domain with genuine scheduling uncertainty.
- **Intentions**: goals a plan should maintain, achieve, or avoid, stated as
  temporally extended patterns attached above the level of individual
  actions. The paper's own example: two actions that look contradictory
  (insulin dosing and carbohydrate reduction) are both explained by one
  intention ("avoid more than two hyperglycemic episodes a week"). This is a
  second, complementary rationale mechanism to PROforma's arguments, at a
  different granularity: PROforma's arguments explain one decision, Asbru's
  intentions explain what a whole sub-plan is *for*. Worth noting because
  this repo's `because` field, as currently sketched, is per-node or
  per-rule; Asbru suggests a group of objectives sharing one intention
  ("keep the fort fed") is a real, separately worth-naming structure, not
  just several nodes that each happen to cite similar doctrine.

### Cross-formalism pattern comparison (verified: fetched directly, a
pattern-based analysis of Asbru / EON / GLIF / GUIDE / PRODIGY / PROforma)

Read from [`pmc.ncbi.nlm.nih.gov/articles/PMC2213484`](https://pmc.ncbi.nlm.nih.gov/articles/PMC2213484/)
directly, high confidence for what it reports, though note this is one
comparison study, not a field-wide consensus statement:

- All of the languages analyzed converge on a **task-network model**, and
  all support the same four to five baseline control-flow patterns:
  sequence, parallel split, synchronization, exclusive choice, simple
  merge. This is the strongest single piece of convergence evidence in this
  whole survey: six independently developed formalisms, built by different
  research groups over roughly two decades, landed on the same minimal
  control-flow core.
- None of the six support "multiple instance" patterns (many concurrent
  instances of the same sub-plan). Irrelevant to this repo (one fort, one
  running instance of the graph at a time), but worth noting as a
  deliberately-not-needed capability rather than an oversight to worry
  about replicating.
- Coverage of the full 43-pattern generic workflow taxonomy varies widely:
  PROforma covers 22, Asbru 20, GLIF 17, EON 11. The paper's authors
  explicitly raise whether the field should stop building bespoke
  guideline languages and adopt general business-process tooling instead,
  given how much more expressive general workflow engines are. That the
  clinical-guideline field's own literature raised, rather than dismissed,
  the option of going more general, and yet the formalisms that actually
  got used stayed narrow, is the closest this survey found to a direct
  answer to "where have formalisms failed by becoming too expressive": the
  finding is not a formalism that broke from over-expressiveness, but a
  field that had the option in front of it and mostly didn't take it.

### GLIF, surveyed only secondhand

Search summaries describe GLIF3 using GELLO, an object-oriented expression
language, for decision criteria, and supporting "multiple entry and exit
points" for dynamic re-routing. **Not independently verified**: no GLIF
primary source was fetched this session. Treat this paragraph as a lead for
later, not a settled finding.

### Arden Syntax, surveyed only secondhand, and a genuine scope mismatch

One search summary states Arden Syntax has been excluded from some
comparative CIG studies specifically because it models a single decision
(a Medical Logic Module), not a guideline unfolding over time. **Not
independently verified against a primary source**, but worth recording as
a negative finding regardless: Arden Syntax is very likely the wrong
granularity for this project's problem (a multi-step progression), even
though it is one of the most-cited names in this space.

### CQL three-valued logic (verified: fetched directly from the official
HL7 CQL specification)

Read from [`cql.hl7.org`](https://cql.hl7.org/04-logicalspecification.html)
and related pages directly, high confidence:

- CQL's `Boolean` type has three values: `true`, `false`, `null` (meaning
  unknown), not two.
- Logical operators propagate this in a defined, closed way, not ad hoc:
  for `And`, if either argument is `false` the result is `false`
  regardless of the other; if both are `true` the result is `true`;
  otherwise the result is `null`. Comparison operators (other than
  equivalence) return `null` if either operand is `null`.
- Dedicated "nullological" operators exist for handling this explicitly:
  `IsNull`, `IsTrue`, `IsFalse`, `Coalesce`.

This is a ready-made, standards-specified semantics for the exact
requirement in `docs/AGENT-LOOP.md` §6: "code evaluates rules against a
closed vocabulary of site and state facts... reporting `unknown` rather
than guessing." Recommend adopting CQL's propagation rules directly rather
than inventing a bespoke unknown-handling scheme: a deviation rule whose
`when` clause touches an unread fact should evaluate to `unknown`, not
`false`, and an `unknown` result should be visibly distinct from "checked
and did not fire" in whatever the rule's fired/not-fired log records.

---

## 3. RTS build orders

### The academic planning literature treats this as pure search, not as a
default-flow-plus-deviation representation

Churchill and Buro, "Build Order Optimization in StarCraft" (AIIDE 2011).
**Moderate confidence**: the original PDF returned binary/compressed data
to the fetch tool and could not be read directly; content below comes from
a mirrored HTML rendering
([readkong.com](https://www.readkong.com/page/build-order-optimization-in-starcraft-4580919))
cross-checked against several independent search-result summaries of the
same paper, which agree on the substance, so treat this as probably
faithful but not independently verified word for word against the original
PDF.

- A build order action is modeled as a tuple `(duration, required
  resources, borrowed resources, consumed items, produced outputs)`; game
  state is `(time, resources, in-progress actions, income rate)`; the tech
  tree is a closed prerequisite graph.
- The goal is minimal-makespan search: find the fastest action sequence
  reaching a target state, computed fresh, not represented as a template
  with named deviation points.
- Per the paper itself (via the mirror), scouting-driven adaptation and
  adversarial replanning were **explicitly left as future work**, not
  solved. This is a genuine negative finding worth stating plainly: the
  academic RTS-planning literature does not itself supply the "default flow
  plus deviation rule" representation this brief is looking for. It solves
  a different, narrower problem (optimal makespan from a known target),
  and treats adaptation as outside its scope.

### Where the actual pattern lives: human practitioner build-order guides

This is a genuine domain-neutral find, from outside academia, that matches
the brief's target shape better than the academic literature does.
**Moderate confidence, single community source read directly, not
peer-reviewed**, but the concept it describes recurs across several
independently-run guide sites found in search (Liquipedia, multiple SC2
build-order-guide sites), which corroborates that this is a real,
widespread practitioner convention rather than one author's idiosyncratic
scheme.

Read directly from [TerranCraft, "Understanding build orders in
blocks"](https://terrancraft.com/2014/08/30/understanding-build-orders-in-blocks/):

- A build order is decomposed into **blocks**: an opening block, one or
  more middle blocks, a late block, each a self-contained, memorizable
  segment.
- Blocks are joined at **convergent points**: specific game moments where
  different possible build paths arrive at the same state. A player
  choosing among several possible next blocks is choosing "the appropriate
  block to bridge the gap" to the next convergent point.
- Blocks get **substituted** based on scouted information: "if you scouted
  no gas" is the article's own example trigger, prompting a defensive block
  in place of the default one, while the rest of the build order (the parts
  before and after) stays unchanged.

This is a strong structural match for what the brief wants and, unlike the
CIG formalisms, it comes from people solving exactly this problem under
real time pressure with no tooling at all, which is its own kind of
evidence: this is what the representation collapses to when humans have to
hold it in their heads and act on it live. Two things worth adopting by
name:

- **"Convergent point"** as a design term: every deviation should specify
  where it rejoins the default flow, not just where it leaves it. A
  deviation with no named rejoin point is a fork, not a deviation, and the
  brief's framing ("a default flow with deviations," not "a tree of
  alternative flows") argues for making convergence a required field rather
  than an emergent property.
- The observation that a block substitution replaces a *contiguous run* of
  the default flow between two convergent points, not a single node. The
  schema in §6 should allow a deviation's `target` to name a span, not just
  one objective, since real deviations (in this source and in the clinical
  literature) are often "skip this whole sub-sequence," not "skip one
  step."

General community convention, lower confidence (search-summarized across
several sites, not independently fetched): guide authors commonly write the
trigger and the adaptation inline, next to the step it modifies ("if you
scout X, do Y instead"), the same instinct as the brief's own "fishing
requires a river" example. No single citation pins this down, but the
pattern recurred across every build-order guide site this search touched,
so treat the aggregate as reasonably solid even without one strong source.

---

## 4. Other fields surveyed

### CMMN (Case Management Model and Notation, OMG standard)

**Moderate confidence, search-summary only**: the primary OMG/arXiv sources
attempted
([arxiv.org/pdf/1608.05011](https://arxiv.org/pdf/1608.05011)) returned
binary PDF data the fetch tool could not extract text from. What follows is
from consistent search-result summaries across several independent
explainer sites
([Visual Paradigm](https://skills.visual-paradigm.com/docs/cmmn-vs-bpmn-when-to-use-which/cmmn-bpmn-comparison/cmmn-vs-bpmn-conceptual-differences/),
[Flowable](https://www.flowable.com/solutions/cmmn),
[ProcessMaker](https://www.processmaker.com/blog/intro-to-case-management-model-and-notation-cmmn/)),
which agree on the shape even though no primary spec text was independently
read.

- A **Sentry** gates entry to or exit from a stage or task: an `OnPart`
  (an event) combined with an `IfPart` (a boolean condition).
- **Milestones** mark achieved business states, independent of which tasks
  ran.
- CMMN is explicitly **declarative**: it describes what is allowed, not a
  fixed sequence, and is contrasted directly against BPMN's imperative,
  fixed-order model.

**Why it does not earn the primary structural role here**, despite being
the closest named standard to "adaptive case management": CMMN solves a
different problem than this brief poses. It models *many possible task
activations with no privileged default order*, decided live by a human case
worker as circumstances unfold. This repo's brief explicitly wants the
opposite: **one stated default flow** that deviation rules perturb, visible
as a diff against that default. A CMMN case has no "default flow" concept
to diff against; everything is conditionally available from the start. The
Sentry's `(event, condition)` pairing is still worth reusing as the shape
for evaluating a deviation rule's trigger, but the surrounding declarative,
no-default-order model is a worse fit than the CIG task-network plus FHIR
PlanDefinition combination recommended in §0. Recorded as surveyed and
deliberately not adopted at the whole-model level, with the specific piece
worth keeping named explicitly so the rejection isn't total.

### HTN planning (method preconditions)

**Moderate-to-high confidence on the substance** (this is standard,
long-settled AI planning textbook material, low risk of being simply
wrong), but **no primary paper was independently fetched this session**;
content is from search-result summaries of well-established secondary
descriptions.

- A compound task has one or more **decomposition methods**, each carrying
  its own declarative **preconditions** (a set of literals that must hold).
- State-based HTN planners select the first method whose precondition
  holds in the current state, an if/then/else ladder over methods, not a
  single privileged default with named exceptions.

**Considered and not recommended as the primary shape**, for a readability
reason specific to this project rather than a general critique of HTN: an
objective with N candidate methods, precondition-ranked, has no notion of
"the" default, only "whichever matched first." That is a worse fit for
`docs/AGENT-LOOP.md` §6's explicit goal ("fishing requires a river" should
be readable as a *named exception to a named default*, visible whether or
not it fired) than a model with one designated default edge plus a
separate list of deviation rules. If this project ever needs "several
genuinely different, comparably-valid ways to reach the same objective"
(not just "the normal way, with named exceptions"), that is a bigger design
change than an MVP objective graph, and HTN's method-precondition shape is
the thing to revisit then, not now.

### Incident command system (ICS) playbooks

**Search-summary confidence only, and reported here mainly as a negative
finding**, per the researcher brief's instruction to report plainly when a
field turns up little. No source found in this search gives ICS a
structured, closed deviation-classification vocabulary comparable to
clinical variance coding, or an evidence-threshold mechanism for revising a
standard operating procedure. What ICS materials do describe consistently
is a **fixed-cadence replanning cycle**, the Incident Action Plan (IAP), and
an explicit tolerance for local modification of the standard command
structure "to fit mission and resources," paired with a caution against
*major* deviation
([USDA ICS-100 overview](https://www.usda.gov/sites/default/files/documents/ICS100.pdf);
[FEMA ICS review](https://training.fema.gov/emiweb/is/icsresource/assets/ics%20review%20document.pdf)).
The fixed-cadence replanning idea is already effectively present in this
repo's design (the Overseer keeps the agenda through queue proposals; the
conductor's per-cycle triage in `docs/AGENT-LOOP.md` §1 to §4 is itself a
fixed-cadence review), so ICS mostly corroborates an already-made choice
rather than adding anything new. Given the low yield relative to clinical
pathways and the CIG formalisms, this field was not pursued further.

### Construction scheduling (baseline versus as-built, CPM)

**Search-summary confidence only.** Consistent description across several
industry sources
([SmartPM, "Schedule Variance in Construction"](https://smartpm.com/blog/schedule-variance-in-construction);
[Long International, "Calculating the As-Built Critical Path"](https://www.long-intl.com/articles/as-built-critical-path/);
[Quollnet, "As-Planned vs. As-Built"](https://quollnet.com/article/as-planned-vs-as-built)):
the Critical Path Method fixes a dependency graph up front (the "default
flow," in this project's terms, is structurally identical to a CPM
network's task-dependency ordering); field practice then compares the
baseline schedule against the as-built record purely on the **timing axis**
(dates slip, the critical path itself can shift which tasks are on it) under
a formal "baseline change control process" with logged root-cause variance
analysis for audits and claims.

**Why it earns a narrow place**: this is the cleanest example found of
treating "the graph's shape changed" and "only the timing changed" as two
genuinely different kinds of deviation, worth two different action types
rather than one. That is the direct source of the `timing_shift` action
recommended separately from `insert` / `skip` / `substitute` / `reorder` in
§0 and §6: a rule that only delays an objective (says "wait for winter to
pass") without touching the graph's shape at all is common in this domain
too (a farm plan waiting on a season), and conflating it with a
shape-changing deviation in the schema would lose exactly the distinction
construction scheduling treats as fundamental enough to log separately.

---

## 5. Direct answers to the brief's questions

**Node, edge and rule structure these fields converge on.** A task-network
model (verified across six independently developed CIG formalisms): nodes
are typed activities (action / decision / enquiry / plan, in PROforma's
terms; an "objective" here), edges are a closed set of ordering relations
(before/after/concurrent, optionally offset), and a separate rule layer
(conditions, in FHIR's terms; deviation rules here) perturbs which nodes run
and when, rather than being baked into the edges themselves as branches.
RTS build-order practice converges on the same shape from a completely
different, non-academic tradition: a linear default sequence (blocks joined
at convergent points) plus a separate, named set of trigger-to-substitution
mappings.

**Deviation actions that recur**: insert, skip, reorder (move earlier / move
later), substitute, repeat. Construction scheduling's practice argues for
keeping a sixth, `timing_shift`, distinct from the rest, since it changes
only the "when," never the "what" or "in what order."

**How applicability conditions stay a closed, checkable vocabulary rather
than a scripting language.** Every formalism checked (FHIR, PROforma, CQL)
expresses a condition as a boolean-valued expression over a declared set of
facts or resource references, evaluated by a fixed interpreter, never as
arbitrary executable code. CQL additionally specifies the semantics for
missing information (three-valued logic, propagated by fixed rules, with
dedicated null-handling operators) rather than leaving "what if a fact is
unread" to convention. The one directly-verified finding on formalisms and
over-expressiveness (§2, the pattern-based comparison study) is that the
CIG field considered going more general and mostly did not, which reads as
a field-level judgment that staying narrow was worth more than the extra
expressiveness, for reasons of analyzability more than of raw capability.

**How variances are captured and classified, and what turns recurring
variances into a pathway change.** Captured at the instance level, tied to
the specific step, with a reason and (where recorded) a classification
code; reviewed in aggregate, by a committee or equivalent, on a cadence.
**No source found gives a specific, well-cited evidence threshold** for
promoting a recurring variance into a pathway change; where the mechanism is
described at all it is committee judgment over aggregated data, not a
formula. This is mild corroboration, not proof, that this repo's existing
rejection of a mechanical count threshold (`research/2026-08-25-learning-architecture.md`)
is not swimming against an established field norm; the field that has run
this exact loop longest does not appear to use a count threshold either,
at least not one this search could find documented.

**How rationale for a rule stays attached and visible.** Two complementary
mechanisms, both verified directly. PROforma attaches rationale at the
*single-decision* grain: a candidate's `arguments[]` are simultaneously the
applicability logic and the stated reasons for and against, so "why did
this fire" is a direct readout of the same structure that decided whether
it fired. Asbru attaches rationale at the *group* grain: an `intention`
(maintain / achieve / avoid) sits above several actions that jointly serve
it, explaining why a set of nodes exists at all, not just why one fired.
Recommend both: a `because` on each deviation rule (PROforma grain) and an
optional shared `intention` label a cluster of objectives can carry (Asbru
grain), rather than only the first.

**How timing is handled alongside ordering.** Kept as two mechanisms, not
one, consistently across sources: ordering is structural (a dependency
graph, whether that's FHIR's `relatedAction`, PROforma's scheduling
constraints, or a CPM network), and deadlines/windows are a magnitude
attached to a relation or a reference point (FHIR's `offset` on a relation;
Asbru's four-bound time annotation anchored to a `REFERENCE`). The
recommendation in §0 and §6 mirrors this: prerequisite edges for ordering,
a simplified `(offset_ticks, reference)` pair for deadlines.

---

## 6. Schema sketch for this project, and what to leave out of an MVP

This is a sketch, not a finished spec; it is meant to hand the design
conversation something concrete to react to, not to preempt it.

```yaml
objective:
  id: string
  done_when: <closed predicate over state facts> | "manual"   # manual = Overseer-graded
  prerequisites: [objective_id, ...]      # structural ordering, CPM-style
  default_next: objective_id | null       # the ONE designated normal successor,
                                            # needed because prerequisites alone
                                            # can leave more than one legal next
                                            # step and "default flow" must be
                                            # well-defined, not just legal
  because: string                          # always shown, one line
  intention: intention_id | null           # optional Asbru-style shared rationale
  sources: [ref, ...]                      # optional, doctrine-style provenance

intention:                                 # optional grouping, Asbru-style
  id: string
  statement: string                        # "keep the fort fed"

deviation_rule:
  id: string
  when: <closed boolean expression over site/state facts>   # three-valued (CQL-style):
                                                              # true | false | unknown
                                                              # unknown => does not fire,
                                                              # logged as unknown, never
                                                              # silently treated as false
  action: insert | skip | reorder_before | reorder_after | substitute | repeat | timing_shift
  target: [objective_id, ...]              # a span, not just one node (RTS-block finding)
  insert_at: objective_id | null           # anchor for insert/reorder
  offset_ticks: int | null                 # for timing_shift and for insert with a delay
  reference: objective_id | event_fact | null   # Asbru-style anchor for offset_ticks
  rejoins_at: objective_id                 # REQUIRED: the convergent point, RTS-block-style;
                                            # a deviation with no rejoin point is a fork,
                                            # not a deviation
  because: string                          # always shown, whether or not it fired
  sources: [ref, ...]
  # written by code each cycle it's checked, not by the rule author:
  last_evaluated_tick: int
  last_result: fired | not_fired | unknown

variance_record:                           # ad hoc Overseer departure, NOT rule-driven
  id: string
  objective_id: string
  what_changed: <same action vocabulary as deviation_rule>
  reason: string                           # required
  evidence: prediction_ref | null          # optional at write time
  proposed_by: role
  # promotion to a real deviation_rule reuses the existing doctrine revision
  # path (queue proposal, Overseer ruling, diagnosticity-weighted evidence),
  # not a new mechanism
```

**`agenda.get(id)`** (already named in `docs/AGENT-LOOP.md` §6) returns one
objective's full history: what changed, who proposed it, the ruling, the
evidence. The per-cycle prompt shows the top few objectives whose
prerequisites are satisfied and `done_when` is false, plus a one-line index
of the rest. That "top few open objectives" set must be code-computed as a
direct property lookup, not a walk of the whole graph, for the "prompt size
does not grow with the graph" promise to actually hold as the graph grows.

**Leave out of the MVP, with reasons:**

- **Asbru's full seven-component time annotation.** This project's timing
  uncertainty is about game state, not about the timing model itself; the
  two-field `(offset_ticks, reference)` simplification captures the useful
  part (deadlines relative to an event, not an absolute tick) without the
  bound-uncertainty machinery Asbru needed for a domain with genuinely
  uncertain durations.
- **CMMN's full sentry/stage/discretionary-task model.** This project wants
  one stated default flow with named exceptions, not an open field of
  always-available, no-default tasks. Revisit only if the Overseer ends up
  wanting many concurrently-open tasks with no sensible default ordering,
  which looks unlikely for a colony progression.
- **HTN's multiple-methods-per-objective alternative-decomposition shape.**
  Rejected above for readability: it has no notion of "the" default, only
  "whichever method's precondition matched first," which is a worse fit for
  this project's explicit goal of a graph readable as "normally X, except
  when Y."
- **PROforma's full rule-in/rule-out scored recommendation logic.** A
  deviation rule should either fire or not (three-valued: true / false /
  unknown), with no numeric scoring layer. This matches
  `docs/AGENT-ARCHITECTURE.md` §10's existing rejection of self-reported or
  averaged numeric confidence in favor of measured track record; a scored
  applicability check would quietly reintroduce the same kind of
  unearned-precision number at a different layer of the system.
- **GLIF's dynamic multiple entry/exit re-routing and the GELLO expression
  language.** Not independently verified this session (secondhand only);
  plausibly more machinery than needed even if verified. Treat as a lead
  for later, not MVP grounding.

---

## Sources

Fetched and read directly (high confidence for the claims attributed to
them above):

- [FHIR R4 PlanDefinition](https://hl7.org/fhir/R4/plandefinition.html), HL7
- [PROforma: "The Syntax and Semantics of the PROforma Guideline Modeling Language"](https://pmc.ncbi.nlm.nih.gov/articles/PMC212780/), PMC
- [Asbru: Miksch and Shahar, primary paper](https://www.cvast.tuwien.ac.at/sites/default/files/bibcite/220/mik_keml97.pdf), TU Wien
- [Pattern-based analysis of Asbru/EON/GLIF/GUIDE/PRODIGY/PROforma](https://pmc.ncbi.nlm.nih.gov/articles/PMC2213484/), PMC
- [CQL Logical Specification](https://cql.hl7.org/04-logicalspecification.html), HL7
- [TerranCraft, "Understanding build orders in blocks"](https://terrancraft.com/2014/08/30/understanding-build-orders-in-blocks/)
- [Wikipedia, "Clinical pathway"](https://en.wikipedia.org/wiki/Clinical_pathway) (tertiary, uncited inline in its own variance section)

Read via a mirror or via consistent search-result summaries, not the
original primary text (moderate confidence, flagged inline above):

- Churchill and Buro, "Build Order Optimization in StarCraft," AIIDE 2011,
  via [readkong.com mirror](https://www.readkong.com/page/build-order-optimization-in-starcraft-4580919)
- [PubMed 11207952, variance analysis in hip/knee arthroplasty pathways](https://pubmed.ncbi.nlm.nih.gov/11207952/)
- [ScienceDirect, "Integrated Care Pathway" overview](https://www.sciencedirect.com/topics/nursing-and-health-professions/integrated-care-pathway)
- CMMN: [arxiv.org/pdf/1608.05011](https://arxiv.org/pdf/1608.05011) (fetch
  returned unreadable binary; description via
  [Visual Paradigm](https://skills.visual-paradigm.com/docs/cmmn-vs-bpmn-when-to-use-which/cmmn-bpmn-comparison/cmmn-vs-bpmn-conceptual-differences/),
  [Flowable](https://www.flowable.com/solutions/cmmn),
  [ProcessMaker](https://www.processmaker.com/blog/intro-to-case-management-model-and-notation-cmmn/))
- ICS: [USDA ICS-100](https://www.usda.gov/sites/default/files/documents/ICS100.pdf),
  [FEMA ICS review](https://training.fema.gov/emiweb/is/icsresource/assets/ics%20review%20document.pdf)
- Construction scheduling: [SmartPM, schedule variance](https://smartpm.com/blog/schedule-variance-in-construction),
  [Long International, as-built critical path](https://www.long-intl.com/articles/as-built-critical-path/),
  [Quollnet, as-planned vs as-built](https://quollnet.com/article/as-planned-vs-as-built)
- HTN method preconditions: standard AI-planning textbook material,
  summarized consistently across several secondary sources
  ([GeeksforGeeks HTN overview](https://www.geeksforgeeks.org/artificial-intelligence/hierarchical-task-network-htn-planning-in-ai/),
  [ScienceDirect HTN topic overview](https://www.sciencedirect.com/topics/computer-science/hierarchical-task-network));
  no primary paper (e.g. Erol/Hendler/Nau) independently fetched this
  session

Named but not independently verified against any source this session
(secondhand only, flagged inline where used above): GLIF3's GELLO
expression language and multiple entry/exit re-routing; Arden Syntax's
exclusion from some CIG comparisons on granularity grounds; a specific
patient/clinician/system variance taxonomy in clinical pathway literature.

## What could not be verified, rolled up

- A single, well-cited primary source for a three-way (or any specific)
  clinical variance source taxonomy. Searched for directly, several times,
  with no clean hit; the shape is alluded to across secondary summaries but
  never pinned to one citation.
- Any quantitative evidence threshold used anywhere in surveyed fields to
  promote a recurring deviation into a permanent rule change. None found;
  where the mechanism is described, it is committee/expert judgment over
  aggregated data, which is itself the finding.
- The exact text of the Churchill and Buro paper (read via a mirror, not
  the original PDF, which the fetch tool could not parse as text) and of
  the CMMN primary spec/arXiv paper (same PDF-extraction failure,
  description from secondary sources only).
- GLIF's actual applicability-condition machinery (GELLO) and its "multiple
  entry/exit" re-routing claim, both secondhand only.
- Whether ICS or any other incident-response doctrine has a formal,
  closed deviation-classification vocabulary comparable to clinical
  variance coding: searched for specifically and not found; reported as a
  negative finding rather than left silent.
