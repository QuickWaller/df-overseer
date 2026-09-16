# An opening priority ladder for a new fortress: representation, learning, required reads

Date: 2026-09-16. Read-only research (no VM/DFHack calls, no game interaction).
Scope: the question the brief poses — what should a coordinate-free,
adjustable, learnable opening-priority ladder look like — plus a verified
check of the user's own habitual opening (fishing, drinking water, three
farm-founding methods), treated as hypotheses, not requirements. Every domain
claim is cited to a fetched source; every claim about this repo's code is
cited to the file this session actually read. Confidence flagged per claim,
not once at the end.

---

## Bottom line

**Represent the ladder as a small, versioned data file of "rungs"**
(`playbooks/opening-ladder.yaml`, the directory `docs/AGENT-ARCHITECTURE.md`
§11 already names for exactly this kind of structured, queue-revised content,
though it does not exist yet) — each rung a closed `type`, coordinate-free
`preconditions` over named facts, one or more ranked `branches` where genuine
method-choice judgment exists, and a `prediction` written in the *exact*
grammar `dfqueue`'s proposals already use
(`learning/live_signals.py` + `dfqueue/grade.py`). A new read-only tool,
`ladder.next`, evaluates every rung's preconditions against the current fact
snapshot and returns ranked, eligible next rungs — the same
"code narrows, model chooses among labelled candidates" shape as
`find_open_area`/`rank_candidate_sites`, never the model computing eligibility
itself. **Adjustment is never a silent file edit.** It happens through three
mechanisms this repo has already committed to elsewhere, applied here rather
than invented fresh: per-rung outcome grading via the existing dfqueue
prediction/grade pipeline (measured track record, §10 of
`docs/AGENT-ARCHITECTURE.md`); threshold/branch-order revision as a queued,
ruled, audited write (the same "no reflex retunes itself... auditable like any
other decision" pattern §6 already specifies for playbooks); and cross-fort
promotion via the hierarchical partial-pooling design
`docs/MEMORY-ARCHITECTURE.md` already commits to. None of this is a fourth new
pattern — it is the existing machinery pointed at one more artifact.

**The single biggest risk to this representation is not the representation —
it is that its most valuable predictions are currently unwritable.** The
ladder's whole reason for existing (per the user's own framing: fishing,
water, food) is food-and-drink security, and `research/2026-09-16-food-and-drink-logistics.md`
already established, independently, that **nothing in this repo distinguishes
fort-owned stores from foreign/caravan-owned goods** and no `stocks.*` tool or
live signal exists. So a rung cannot yet predict "fort-owned drink rises above
zero" — that signal literally does not exist in `learning/live_signals.py`'s
closed registry, and adding it needs the same missing `stocks.food-drink` tool
that food-drink logistics already flagged as the sharpest gap in the whole
project. The ladder design is sound and buildable today for the *spatial*
rungs (farm plot siting/digging); it is data-starved for the *security*
rungs that are the actual point, until that one tool exists. A second, milder
risk: the ladder's own doctrine footprint must share this project's own
**measured**, tighter-than-generic collapse point — `evals/compliance/` found
`deepseek-chat` (a model this project actually runs cheap roles on) collapsing
to 0% perfect-response at **n≥40** simultaneous rules, not the generic
literature's N=80 — so the ladder should be budgeted at well under ten rungs,
not the dozens a naive "cover every case" checklist would produce.

---

## 1. Restating the problem domain-neutrally

*A conditional, partially-ordered plan for an opening phase, executed under
partial observability, whose branch depends on the environment discovered at
the time, and which must revise itself as outcomes accumulate across
episodes.* This is not new; it is worked on continuously across at least five
fields, and — following this repo's own standing rule
(`CLAUDE.md` "Research before designing from scratch",
`decisions/DECISIONS.md` 2026-08-25) — those fields are read before any
DF-specific machinery is proposed.

### 1.1 RTS build-order adaptation — the closest structural analogue

StarCraft AI research treats an opening as exactly this shape: a pre-committed
build order, revised on new information gathered by a costly scouting action
under fog-of-war. The mechanism found in the literature: any candidate build
order in a simulated set that contradicts an observation is discarded, and the
survivors are ranked by a Bayesian model over the remaining evidence — i.e.
**observations prune a candidate set; they do not re-derive a plan from
scratch.** ("Replay-based strategy prediction and build order adaptation for
StarCraft AI bots", Yonsei University; "Design Adaptive AI for RTS Game by
Learning Player's Build Order", IJCAI 2020.) A pointed finding, worth stating
because it complicates the "just adapt more" instinct: **competition-grade AI
bots pre-select a build order and rarely change it mid-game, unlike human
experts who are "familiar with the relationships between two build orders"
and switch deliberately** — i.e. build-order switching is itself a skill that
requires *known relationships between orders*, not ad-hoc improvisation on
each new fact. This transfers directly: the ladder's branches should be a
small, pre-enumerated, *known-relationship* set (method A vs B vs C for
"found a farm"), not a system that improvises a fresh plan from raw facts each
time. (Moderate confidence — search-engine-summarized academic abstracts, not
the full papers; the qualitative shape is corroborated across multiple
independent sources so is trusted more than any single claim in it.)

### 1.2 HTN planning and GOAP — decomposition vs. reactive re-planning, and why neither alone fits

Hierarchical Task Network planning decomposes a compound task into simpler
tasks until only primitive, directly-executable actions remain, with task
networks usable as preconditions for other tasks — this is structurally very
close to what a "rung" already is (a compound goal like "have working
farming" decomposing into "find a plot" → "dig or muddy it" → "assign a
crop" → "build a still or kitchen"). GOAP (used in F.E.A.R.) instead adapts
STRIPS: a flat action space with preconditions/effects, and a planner searches
for *any* sequence of actions that satisfies the goal at plan time, which
makes it more reactive to novel situations but less able to encode "this is
how competent players actually sequence this" domain knowledge. Contemporary
game AI has moved toward HTN over GOAP specifically because pure GOAP produces
technically-valid but human-illegible orderings, and some engines hybridize
both to avoid GOAP's predictability problems while keeping HTN's designed
structure. (Moderate confidence, search-summarized; corroborated across
multiple independent industry/academic sources — F.E.A.R.'s own GOAP
postmortem, a HTN-in-games survey, and a stated industry drift toward HTN in
titles like Killzone 2 and Dying Light.)

**What this changes about the design**: the ladder should be HTN-shaped
(designed decomposition with named sub-goals, `docs/AGENT-ARCHITECTURE.md`'s
own preference for designed structure over emergent search), not GOAP-shaped
(a flat action soup a planner searches at runtime) — consistent with this
repo's repeated principle that code should narrow to *ranked, pre-computed*
candidates rather than have the model (or a search process) discover
structure at call time.

### 1.3 PDDL / prerequisite graphs and precedence-constrained scheduling — the ordering primitive itself

Classical STRIPS/PDDL operators are precondition-effect pairs, the same shape
`dfqueue`'s own `<preconditions>` block already uses
(`docs/AGENT-ARCHITECTURE.md` §4). The scheduling literature adds the concrete
answer to "how strict should the order be": **Precedence Constraint Posting**
builds a **Partial Order Schedule** — a set of activities under a partial
(not total) order, such that *any* total order consistent with the partial
order remains feasible, deliberately preserving flexibility to respond to
runtime disruption rather than committing to one linear sequence up front.
("1 From Precedence Constraint Posting to Partial Order Schedules", CMU;
critical-path literature more broadly.) **This directly contradicts the
naive "ordered checklist" framing the brief itself flags as a risk**: a
rigid, numbered 1-2-3 list is a *total* order and is the wrong data structure.
The right one is a **DAG of precedence constraints** ("digging a plot precedes
assigning a crop precedes harvesting precedes brewing") with several
mutually-substitutable methods hanging off some nodes (three ways to get a
muddy or soil floor), not a numbered list. (High confidence for the
scheduling-theory claim itself — this is settled operations-research
material, not a contested finding — moderate confidence in how cleanly it
maps onto this specific domain, which is this session's own inference.)

### 1.4 Aviation and surgical checklists — read-do vs. do-verify, and "killer items"

Checklist design research (Degani & Wiener 1993, cited across multiple
aviation-safety sources fetched this session) distinguishes **read-do**
(read one item, perform it, for unfamiliar or high-workload procedures) from
**do-verify / flow-then-check** (perform a memorized sequence, then use the
checklist only to confirm nothing was missed) — and recommends checklists
stay short enough to hold in working memory (their own figure: ~5-9 items is
the classic cognitive-load ceiling cited across this literature, with actual
aviation checklists often longer but explicitly flagged as a tension, not a
solved problem). Both aviation and the WHO surgical-safety-checklist tradition
single out a small subset of **"killer items"** — steps that have historically
caused real harm when skipped (fuel, flaps, trim in aviation) — and design the
checklist to make *those specific steps* impossible to silently skip, rather
than treating every item as equally critical. **This transfers as a concrete
design rule**: not every rung needs a hard gate, but the ones with a real
fort-ending failure mode (losing the last of a seed type permanently, per
`agents/quartermaster/role.md`'s own existing doctrine line) deserve to be
flagged distinctly from routine sequencing, the same way "fuel" is flagged
distinctly from "cabin lighting" on a pre-flight list.

### 1.5 Clinical triage protocols — branching under uncertainty, and a real caution

Triage algorithms (START and its relatives) are literally "for any given
chief complaint, a series of observations and questions lead down a specific
decision tree" — structurally the closest existing thing to "branch the
opening plan on what you observe." The caution worth carrying over: the
literature on this notes decision trees "struggled to handle the uncertainty
and ambiguity present" in real cases, and modern systems increasingly favor
probabilistic (Bayesian) triage over rigid trees specifically because a
clean branch-on-fact tree is brittle when the fact itself is ambiguous or
partially observed (a "murky pool" that might or might not count as a
reliable water source, an aquifer flag that this repo cannot yet even read
mid-fort — §5). **This is a real tension with 1.3's DAG-of-preconditions
recommendation**, not a footnote: a rung whose precondition depends on a fact
this repo cannot yet observe (see §5's availability table) should degrade to
"ask the Consultant" or "flag as unknown, propose the cheapest fact-gathering
step first" rather than silently defaulting one way, mirroring triage
practice of an explicit "insufficient information" branch rather than forcing
a guess. (Moderate confidence — practitioner and review-article summarized,
not the primary triage-algorithm specifications themselves.)

### 1.6 What none of the above solves: the self-modification question

None of the five traditions above has to answer "should the plan revise
*itself*, and if a model is involved, is that safe" — RTS bots are typically
retrained offline between matches, HTN/GOAP domains are hand-authored once by
developers, checklists are revised by a safety board after an incident
review, and triage protocols are revised by clinical governance bodies. In
every case, **the entity executing the plan in the moment is not the same
process that revises the plan afterward**, and revision is a deliberate,
reviewed, out-of-band act. This is the strongest cross-domain support this
research found for the repo's own already-decided position
(`memory/agent-memory-standards.md`, "The deliberate divergence: the model
does not edit its own memory") — every field that has actually solved this
problem for real stakes keeps authoring and execution institutionally
separate, which is precisely what §4 below proposes doing here, mechanically
rather than institutionally.

---

## 2. In-domain prior art

### 2.1 The DF community's own opening checklists

Community guidance was checked directly (Steam Community guides, the
official wiki's Embark article, and forum discussion), not assumed. The
consistent finding across sources: **there is no single canonical opening
order** — the wiki's embark material and multiple guides explicitly frame
their own advice as one of several contradictory playstyles rather than a
single correct sequence, and a recurring practical rule ("bring twice as much
booze as food, split across the four alcohol types") is about embark
*packing*, not about first-year build sequencing. This is itself a finding:
**the domain does not actually have a single standard checklist to encode**,
which supports building the ladder as a small set of conditional
alternatives rather than a single fixed sequence — it would be inventing
false consensus to encode one "correct" order when the community's own
material disagrees. (Moderate confidence: several independent guides
checked, consistent absence of one standard order across all of them.)

### 2.2 DFHack's `orders` library — shipped precedent for "priority order as data, not code"

`orders` ships a **built-in library**, `library/basic`, explicitly covering
"prepared meals and food products... booze/mead" plus containers — a
maintained, versioned, importable *data* file of standing production
priorities, distinct from any Lua script that would hard-code the same
logic. Confirmed available on this install
(`memory/dfhack-environment.md`, `research/2026-09-16-food-and-drink-logistics.md`
§2's tool table, this session's own re-read). This is the strongest
in-domain precedent for the brief's own framing ("the Overseer can adjust,
adapt and learn from it") being expressed as **importable, editable data**
rather than logic embedded in a script — exactly what §4 proposes for the
ladder, and evidence the pattern already has real DFHack-side buy-in rather
than being invented fresh for this project.

---

## 3. The proposed representation

### 3.1 Where it lives

`playbooks/opening-ladder.yaml` — the directory `docs/AGENT-ARCHITECTURE.md`
§11 already reserves for exactly this ("structured data, not prose. Owned by
the Overseer, revised through the queue.") The directory does not exist yet
(`playbooks/` and `doctrine/` were both checked this session; neither is
present in the repo), so this is a proposal to use the already-declared home,
not a new directory invention.

**Scope tag**: `universal` (per `docs/MEMORY-ARCHITECTURE.md`'s scope
taxonomy) — an opening ladder is meant to generalise across worlds and
embarks, unlike a site-specific fact ("aquifer at z-3"), which belongs in the
fort dossier instead, referenced by the ladder's preconditions rather than
baked into it.

### 3.2 The rung shape

Each rung reuses `dfqueue`'s existing grammar verbatim rather than inventing
a parallel one — the same `preconditions` shape (`landmark`/`area` +
`state`, `dfqueue/schema.py:239-267`), the same `prediction` shape (`signal`/
`op`/`value`/`check_after_ticks`, validated against `learning/live_signals.py`,
`dfqueue/schema.py:270-341`), and a closed `type` vocabulary extended per role
exactly as `TYPE_VOCAB_BY_ROLE` already is (`dfqueue/schema.py:107-142`).

```yaml
schema_version: 1
scope: universal
rungs:
  - id: rung-water-access
    type: water_security            # NEW closed vocabulary entry, owned by
                                     # quartermaster (not yet enabled -- see §6)
    goal: "A citizen can reach drinkable water without a dedicated haul."
    preconditions:
      - fact: "water.reachable_open_source"
        state: "true"
    branches:                        # ranked; the model chooses among these,
                                     # never derives one from raw geometry
      - when: {fact: "water.source_kind", state: "river_or_lake"}
        action: "none"               # dwarves path to open water by default
        note: "Cheapest possible rung: a satisfied precondition, no build."
      - when: {fact: "water.source_kind", state: "pond_or_murky_pool"}
        action: "none"
        note: "Same, lower-quality source; wiki: dwarves drink from either."
      - when: {fact: "water.source_kind", state: "none_reachable"}
        action: "BLOCKED"
        note: >
          A well needs a channel-to-water dig plus a well blueprint; neither
          exists in this repo's tools today (see §6, §7).
    prediction:
      signal: 'fort.thirst_related_bad_thoughts.count'   # NOT YET REGISTERED
      op: "eq"
      value: 0
      check_after_ticks: 33600      # ~1 month
    killer_item: false               # aviation/surgical "killer item" flag, §1.4
  - id: rung-farm-founding
    type: food_security
    goal: "A farm plot exists on a legal, muddied or soil floor."
    preconditions:
      - fact: "farm_plot.exists"
        state: "false"
    branches:
      - when: {fact: "soil_layer.reachable_near_fort"}
        action: "diggable.find + diggable.dig, then farmplot.build"
        cost_note: "-75% yield on pure soil-layer floor, wiki-confirmed (§8)."
      - when: {fact: "movable_water_source.adjacent"}
        action: "BLOCKED: no floodgate/hydraulics tool exists"
      - when: {fact: "zone_tooling.available"}
        action: "BLOCKED today: zone plugin unavailable, no zone-write tool"
    prediction:
      signal: 'landmark."Farm Plot #1".exists'
      op: "exists"
      check_after_ticks: 100800     # ~3 months, one growing cycle
    killer_item: false
  - id: rung-seed-protection
    type: food_security
    goal: "The fort never cooks its last seed of a plant type."
    preconditions:
      - fact: "seedwatch_or_equivalent.available"
        state: "unknown"            # honest: status unverified, §6
    branches: []                    # no action possible until §6's gap closes
    prediction: null                # cannot be written until stocks.seeds exists
    killer_item: true                # per §1.4 -- an irreversible failure mode
```

Three things about this shape deserve to be named rather than left implicit:

- **`action: "none"` is a legitimate, even preferred, rung outcome.** The
  cheapest possible rung is a precondition that is already satisfied and
  needs no build at all — the user's own stated preference for drinking from
  an existing river/lake/pond before ever building anything is exactly this
  case, and it should be recognised as such rather than the ladder always
  reaching for a construction action.
- **`action: "BLOCKED"` is written into the data, not discovered by the
  model at runtime.** Per `docs/AGENT-ARCHITECTURE.md` principle 1 ("if it is
  computable, it is a tool"), whether a branch is currently buildable is a
  fact about this repo's tool surface, not a judgment call — so it is
  recorded in the ladder's own data (and kept current the same way
  `TOOLS.yaml`/`memory/dfhack-environment.md` already are), never left for
  the model to rediscover by trial and error each cycle.
- **`prediction: null` is allowed, and is itself informative.** A rung whose
  learning signal cannot yet be expressed (§6's biggest gap) should say so
  explicitly rather than being given a fake proxy signal just to satisfy the
  schema — this is the same honesty `dfqueue/schema.py`'s refusal-with-reason
  behaviour already models for a malformed prediction.

### 3.3 The scheduler: `ladder.next`, a new read tool

A new coordinate-free read tool (same manifest shape as `scripts/dfhack/TOOLS.yaml`'s
existing entries): `ladder.next() -> [ {rung_id, eligible_branches: [...],
reasons: [...]} ]`. It evaluates every rung's `preconditions` against
whatever fact-reading tools currently exist (§6 names exactly which facts are
and are not readable today), and returns only the rungs whose preconditions
are satisfiable or already true, each with its eligible branches pre-filtered
by the same mechanism. This is structurally identical to
`rank_candidate_sites`/`find_open_area`: **code narrows a large space to a
short, ranked, labelled list; the model chooses among the list and states
why, never deriving eligibility itself.** No such tool exists today — this is
new, and its build cost is dominated entirely by how many of §6's facts are
actually readable, not by the scheduling logic itself (a fixed-point
evaluation over a handful of boolean facts is trivial once the facts exist).

### 3.4 Doctrine budget, made concrete

`docs/MEMORY-ARCHITECTURE.md`'s "Compliance" section and
`decisions/DECISIONS.md` 2026-08-25 cite the generic literature's **N=80**
collapse point, but this project has its own, tighter, **measured** number:
`evals/compliance/` found **`deepseek-chat` collapsing to 0% perfect-response
at n≥40 simultaneous rules**, with per-rule pass rate degrading gently from
97% (n=10) to 72% (n=160) even as the *perfect*-response rate collapses
(`evals/compliance/README.md:45-46`, `docs/AGENT-ARCHITECTURE.md:849`, this
session's own re-read). Claude Opus did not show a clean collapse point in
the same sample size, so **which number applies depends on which model runs
the role holding the ladder** — and this project already runs its cheap
roles (the architect) on DeepSeek for cost (register, 2026-09-16, the first
real architect proposal). **Concrete recommendation: budget the whole ladder
at no more than roughly eight to ten rungs**, each a few structured fields,
not a paragraph — comfortably under the tighter n≥40 figure, and leaving
headroom in the same budget for the rest of doctrine the executing role
already carries (workshop adjacency, aquifer-sealing, and the rest of
`docs/AGENT-ARCHITECTURE.md` §5's existing doctrine list, all of which shares
the same context window and the same collapse curve). This is a design
constraint on scope, not a suggestion: a ladder that tries to cover every
named fact in §6 as its own rung would already exceed this budget on its
own, before any other doctrine is added, which is itself an argument for
collapsing several of §6's facts into one composite rung's precondition
(e.g. one `farm-founding` rung with three branches, as drafted in §3.2,
rather than three separate rungs).

---

## 4. The learning and adjustment mechanism — the central question

The brief is explicit that this is the most important design question, and
that "the Overseer adjusts and learns from it" cannot mean the model
silently rewriting its own ladder (register, 2026-08-25, diverging from
Letta/MemGPT's core-memory-editing pattern specifically because
self-managed memory is where "unfaithfulness and sycophancy live",
`memory/agent-memory-standards.md`). Three mechanisms answer it, none of
them new inventions — each is an existing repo commitment, applied here.

### 4.1 Per-rung outcome grading — reuses `dfqueue` exactly as built

Executing a rung's chosen branch is written to the queue as an ordinary
proposal (or, if the Overseer itself chooses without an enabled advisor
proposing, as a plan step under the write-ahead-log discipline
`docs/AGENT-ARCHITECTURE.md` §9 already specifies). Its `prediction` is
graded by the existing `dfqueue/grade.py` against `learning/live_signals.py`
— **no new grading code**, only new signal kinds (§6). This gives a measured
hit rate *per rung, per branch* exactly the way §10 already gives one *per
proposal type* — "the Architect's `stockpile_siting` predictions have held
11 of 13" becomes "the `rung-farm-founding` / soil-dig branch has held 6 of
6, the never-attempted flooding branch has 0 samples." That is earned
confidence, mechanical, matching this project's existing "confidence in
proposals comes from measured track record" rule verbatim.

### 4.2 Threshold and branch-order revision — a queued, ruled write, never a silent edit

`docs/AGENT-ARCHITECTURE.md` §6 already answers this exact problem for
playbooks in general: *"no reflex retunes itself... the Overseer proposes
threshold changes through the normal queue, auditable like any other
decision. Silent self-modification would destroy the ability to explain what
the fortress did."* Applied here without modification: when the Overseer
wants to reorder branches, retire a permanently-blocked one, or add a rung,
that revision is itself a queued, timestamped, audited write — a `plan` step
under the same write-ahead-log discipline as any fort mutation — before
`playbooks/opening-ladder.yaml` actually changes. This is not a new record
kind to invent; it is the existing plan-execution mechanism pointed at a
data file instead of at DF's game state, and it is why the answer to "does
the model edit its own memory" is **no, the sole writer executes a
previously-logged, revisable decision**, the same distinction this project
already draws everywhere else between judgment (proposing) and execution
(the one writer, logged).

### 4.3 Mechanical cross-fort promotion — reuses the hierarchical partial-pooling design

A rung's measured hit rate across many forts (not just the current one) is
exactly the cross-fortress learning problem `docs/MEMORY-ARCHITECTURE.md`
already designed for: hierarchical partial pooling rather than a vote
counter, scope-tagged (universal / world / site), Bradford-Hill-style
stratification by covariates rather than naive counting. A ladder rung is
just one more thing the fort ledger can carry a covariate for ("which
farm-founding branch was chosen"), and promotion/demotion of a branch's
default rank is a mechanical read of that ledger, never a model's
self-assessment. **Honest gap, inherited rather than new**: this promotion
path is gated on the same prerequisite `docs/MEMORY-ARCHITECTURE.md` already
names — "the fort dossier (mid-fort state) is still uncoded" — so it is
correct today to say the *design* for this layer exists and the *substrate*
does not yet, exactly the caveat already on record for the learning
architecture generally.

### 4.4 What this rules out, stated plainly

No mechanism above ever has the model open and rewrite
`playbooks/opening-ladder.yaml` directly in response to its own reasoning
about how a cycle went. Every adjustment path is: **measured outcome → a
queued, sole-writer-executed, logged write.** This is the same shape §4 of
`docs/AGENT-ARCHITECTURE.md` already uses for the fort itself (the Overseer
is the only writer, and even it writes through a queue for crash-consistency
reasons); the ladder is just one more thing under that same discipline
rather than a special case needing new rules.

---

## 5. Required reads — every fact the ladder needs to branch on

Checked against `scripts/dfhack/TOOLS.yaml`, `memory/dfhack-environment.md`,
and `research/2026-09-16-food-and-drink-logistics.md`'s own tool survey
(re-read, not re-derived, where that report already answered the question).
This table is written to be directly usable as a requirements list for a
tool-building stream, per the brief.

| Fact | Readable today? | Evidence |
|---|---|---|
| Season / in-game date | **Yes** | `overview.get` tier2 `in_game_date` (mechanism verified via its sub-tools; `get_overview` itself has no separate live-run record, `TOOLS.yaml`); `season_change` wake event confirmed real via `REPORT` (`docs/AGENT-ARCHITECTURE.md` §4 wake-event table). |
| Citizen count | **Yes** | `overview.get` tier1 `population`, verified. |
| Citizen skills (e.g. who already has Fishing) | **No** | No tool reads unit skill levels. `list_labors` (verified) reads assigned labor on/off, not skill rating — a different read. |
| Soil layer presence, ranked near a landmark | **Yes** | `diggable.find` / `is_diggable`, live-verified 2026-09-11 (`df-overseer-diggable.lua`), already classifies SOIL material. |
| Reachability of any candidate site from the fort's walkable network | **Yes** | `check_reachable` / `getWalkableGroup`, verified mechanism, reused throughout. |
| River / lake / pond / murky pool presence, ranked/named | **No, not wrapped** | `prospector --show liquids` is confirmed **available** and reports surface water presence in free text (`research/2026-09-16-food-and-drink-logistics.md` §2); no coordinate-free structured wrapper exists. RFR's `RiverTile`/`RiverEdge` messages exist by name (DLL-verified) but field-level detail is unverified (`research/2026-08-25-spatial-perception.md` §3.1) — this is a real "how would we even read it" open question, not just an unwrapped-but-easy case. |
| Flowing vs. stagnant water | **No** | RFR `MapBlock.water_stagnant` exists per a single upstream-source field fetch (`research/2026-08-25-spatial-perception.md` §3.1), unverified field-level, per-tile raw data with no aggregation into a named fact. No tool touches it. |
| Aquifer presence, mid-fort | **No** | RFR `MapBlock.aquifer` exists per the same single-source fetch. The only aquifer read this repo has (`hover_info`, `TOOLS.yaml`) is explicitly pre-embark, out of scope for a running fort. |
| Does a farm plot / still / kitchen / fishery / butcher shop already exist | **Likely, mechanism exists; specific kinds unverified** | `landmarks.list`/`get` already tags buildings by `kind` via the same `dfhack.buildings.getType` enumeration that produces confirmed live values like `"Stockpile"`/`"Wagon"` (`research/2026-08-25-spatial-perception.md` §2.6 addendum, `2026-09-11` register). Whether it currently surfaces farm-plot/workshop-subtype kinds specifically has not been checked. |
| Does an activity zone (fishing, gather-plants, pond) exist | **No — checked negative** | `zone` plugin confirmed **unavailable** on this install; no struct-level or UI-automation path to the vanilla zone screen has ever been built (`memory/dfhack-environment.md`, `research/2026-09-16-food-and-drink-logistics.md` §3/§4, explicit "named as a gap, not a tool"). |
| Does a well exist, and is it functioning (reaches water) | **No** | Enumeration-by-kind mechanism plausibly extends here (same as workshops above) but is unverified for this building type; "does it reach water" is a deeper struct read never attempted. |
| Fort-owned (not caravan-owned) food/drink stock levels | **No — the single biggest named gap** | `research/2026-09-16-food-and-drink-logistics.md` §4: `stocks.food-drink`/`stocks.seeds` proposed, not built; nothing in this repo filters items by ownership. |
| Seed stock per plant type | **No** | Same gap, `stocks.seeds`. |
| Barrel / bin / container counts | **No, not even previously proposed** | A real gap this brief surfaces on top of the food-drink report: containers are load-bearing for both brewing and food/drink stockpiling (`research/2026-09-16-food-and-drink-logistics.md` §1 item 7), and no tool anywhere counts them. |
| Caravan presence, and how long it will stay | **No** | `depot.status` proposed, not built (`research/2026-09-16-food-and-drink-logistics.md` §4); the domain fact itself (on-map dwell time) is a checked negative even in wiki terms, that report's own §3. |
| Biome (whether surface farming is possible at all) | **Likely via `prospector`, unwrapped** | `prospector` (confirmed available) reports a resource summary that plausibly includes biome-relevant data; no coordinate-free structured wrapper confirmed. |

**Summary for the tool-building stream**: of sixteen named facts, **five are
already readable** with a verified mechanism (season/date, citizen count,
soil layer, reachability, and — with lower confidence — building-kind
enumeration), and **the remaining eleven are gaps**, three of which
(fort-owned stock levels, seeds, caravan/depot status) were already named by
`research/2026-09-16-food-and-drink-logistics.md` and are simply re-confirmed
here, and the rest (skills, water-source classification, flowing/stagnant,
mid-fort aquifer, zone existence, well function, containers, biome) are new
findings from this brief's specific angle on the domain.

---

## 6. The DF specifics, verified

### 6.1 Fishing

Checked directly against the DF wiki's Fishing article (fetched this
session). **No fishery workshop is needed to catch fish** — it is needed only
to process a caught fish (a vermin-class item) into something cookable/
edible; "fisherdwarves catch fish directly from water sources without
equipment." **Zones are optional, not mandatory**: dwarves fish from any
available water by default, and a fishing zone is a *standing-order refinement*
("prefer fishing zones" vs "zone-only fishing"), primarily useful to keep
fisherdwarves out of dangerous water rather than a prerequisite for fishing to
happen at all. **Two real, verified gotchas match the user's own framing**:
(1) local fish populations can be **permanently exhausted** by overfishing a
specific pond/river/ocean — the wiki's own words, "eventually they will
remain permanently empty" — so a fishing-first strategy has a real,
time-bounded shelf life, not an infinite one; (2) catching fish only yields
**vermin-class items**, not food — a fort that fishes but never builds a
fishery accumulates uncookable catch, a plausible silent-failure mode
distinct from the "nothing to catch" message the wiki separately documents
for empty water. (Moderate-high confidence: current wiki article, fetched
directly this session, not recalled or assumed; not independently
cross-checked against `0.53.16`'s own patch notes, same caveat the food-drink
report already carried for mechanics of this vintage.)

**Buildability with this repo's tools**: assigning the Fishing labor uses the
same mechanism `set-labor` already exercises live (`unit.status.labors`
confirmed indexable/settable, `TOOLS.yaml`), though this specific labor code
has no separate live-test claim on record. Because zoning is optional, **a
minimal fishing rung (toggle the labor, let default behaviour handle the
rest) is plausibly buildable today without any zone tool at all** —
contradicting an assumption that fishing is fully blocked on the zone gap;
only the *safety refinement* (zone-restricted fishing) is actually gated on
it.

### 6.2 Drinking water

Confirmed via the wiki's Thirst article (fetched this session): dwarves "can
live indefinitely on water alone," with a real, ongoing productivity and mood
cost for going without alcohol ("bad thoughts, reduced movement speed/
workrate, and combat abilities"), matching this repo's own food-drink
research and the general framing already in `agents/quartermaster/role.md`
("dwarves work badly without it"). Source preference order, wiki-stated:
**well first, then river/brook, then murky pools** if nothing else is
available — the user's own habitual choice (river/lake/pond first, before
booze) matches the wiki's own fallback-acceptable tier, just skipping the
well tier, which is consistent with a fast, low-build-cost opening. **Not
verified, in either direction, in any source fetched this session**: whether
stagnant water is treated differently from flowing water for drinking
purposes — this exact gap was already flagged, independently, in
`research/2026-09-16-food-and-drink-logistics.md`, and remains unresolved
here.

**Well construction**, checked directly (DF wiki's Well article, fetched
this session): needs 1 block, 1 bucket, 1 chain or rope, 1 mechanism, and "a
clear vertical pathway straight down" to a water source at least 3/7 deep
(river, lake, aquifer, or an artificial reservoir/channel) — **wells cannot
function through a stairwell**, and **no activity zone is required** for the
well building itself. This is a genuinely positive finding for buildability:
a well is, in principle, exactly the kind of zero-ambiguity, quickfort-
placeable furniture building this repo's existing `build_at_landmark`/
`quickfort` idiom already handles for other buildings. **What actually
blocks it today**: no well blueprint exists in `blueprints/` (four files,
none a well — same gap pattern as the missing still/kitchen/depot blueprints
`research/2026-09-16-food-and-drink-logistics.md` already found), and
"channel down to expose water at a known depth" is a different perception
primitive than anything `find_diggable_area`/`dig_diggable_area` currently
targets (those rank *solid, diggable* material; exposing open water is the
opposite operation and has never been designed for). **Bottom line: if the
embark already has open water reachable by the walkable network, the
cheapest correct opening rung needs no well at all** — this is the "action:
none" case in §3.2's example, and it is the option that most directly
matches the user's own stated habit.

### 6.3 Farm plots — the three named methods, each checked

All three checked against the wiki's Farming article plus a targeted web
search for the specific "water-dump-and-cancel" trick, since the wiki's own
Farming article does not describe it.

**Method 1: flooding rock.** Confirmed real and wiki-documented: "muddying a
stone floor requires temporarily covering it with water; common methods
include a bucket brigade or controlled flooding by temporarily diverting a
river or pool, using a floodgate or door to stop the flow." This needs a
movable water source adjacent to the target, plus a floodgate/hydraulics
setup this repo has never built any tool for, and — bluntly — uncontrolled
water routing is a classic DF fort-killer, which is exactly why this is
usually described in community material as an intermediate technique, not a
beginner-safe default. **Verdict: blocked on tooling (no floodgate/hydraulics
primitive exists), and independently risky enough that it should not be the
ladder's default branch even once a tool existed** — this is a case where
§1.4's "killer item" framing cuts the other way: this method itself is close
to a killer-item risk (an uncontrolled breach), not just a step to protect
against one.

**Method 2: the water-dump-spot-then-cancel trick.** This is real and is
documented in player discussion (not the wiki's own Farming article, which
this session confirmed does not mention it): **channel a small area, flag it
as a pond/pit zone set to fill, let dwarves haul buckets of water into it,
which spreads mud to the floor below as buckets are dumped; then farm on the
resulting mud.** The "cancel" the user refers to is the channel/zone
designation being removed once muddying is done, so the tile is not actually
carved through. **This is squarely blocked by the same zone-tooling gap named
throughout this report and in `research/2026-09-16-food-and-drink-logistics.md`**:
the muddying step is triggered by dwarves autonomously responding to a zone
designation (bucket-hauling AI), not by a placement this repo's
`quickfort`-based tools could drive directly. Even setting the zone gap
aside, this method is exactly the kind of one-off, human-improvised,
UI-driven manipulation `docs/AGENT-ARCHITECTURE.md` §7 already restricts to
embark bootstrap and explicitly does not want built for steady-state play.
**Bluntly, per the brief's own instruction to be blunt where a method is a
human trick that does not survive the no-coordinates rule: this one does
not, today, and should not be a default branch even once zone tooling
exists** — it remains a designation-then-behavior-then-designation-removal
sequence, closer to the UI-automation path this repo deliberately keeps
out of steady-state play than to the clean fused perceive-then-act tools
(`find_open_area`/`build_open_area`) everything else in this ladder should
look like. (Moderate confidence: corroborated by multiple independent forum
threads found via search, not the wiki itself, which is silent on this
specific technique — flagged accordingly, "the community believes" rather
than "verified here.")

**Method 3: digging into a soil layer.** This is, by a wide margin, the
method that already matches this repo's real tool surface. Confirmed via the
wiki: a farm plot is a **zero-material building** — placed directly on a
qualifying floor, sidestepping the `buildingplan`-availability question
entirely (`research/2026-09-16-food-and-drink-logistics.md` §2 already made
this exact point). `find_diggable_area`/`dig_diggable_area` are live-verified
(2026-09-11) to rank and dig SOIL-material candidates near a named landmark
— the perception and action primitives this method needs already exist and
have already closed a real coordinate-free decision-to-mutation loop for a
different purpose. The one real cost, wiki-confirmed: farm tiles on a pure
soil-layer floor (not muddied stone) are "poor" and take a flat **75% yield
reduction**, "even if covered in mud" — a known, quantifiable trade-off, not
a hidden one, and one the ladder's rung (§3.2's `rung-farm-founding`) should
carry as an explicit cost note rather than silently omit. **Verdict: the only
one of the three methods genuinely coordinate-free-buildable with this
repo's tools today**, and — worth stating plainly because it is a pleasant
alignment rather than a coincidence — it is also the method the user's own
habitual ordering already reaches for third, after trying the other two,
which suggests the "easiest to automate" and "what a competent player already
falls back to" answers agree here rather than conflict.

### 6.4 What is blocked by tooling versus by knowledge — summary

| Gap | Blocked by tooling (zone/workshop/farm), or by knowledge? |
|---|---|
| Reliable/restricted fishing | **Tooling** (zone gap) — but *unrestricted* fishing is not blocked at all; only the safety refinement is. |
| Turning any harvest (fish, crop) into food/drink a dwarf can eat | **Tooling** — no still/kitchen/fishery/butcher blueprint exists yet, per `research/2026-09-16-food-and-drink-logistics.md` §4. |
| Farm plot siting and digging (soil-layer method) | **Not blocked** — buildable today with existing tools; a thin `farmplot.build` wrapper plus a blueprint is the only missing piece, already scoped in the food-drink report. |
| Flooding-rock method | **Tooling** (no floodgate/hydraulics primitive) — and independently a design choice not to default to it, per §6.3. |
| Water-dump-and-cancel method | **Tooling** (zone gap) — and independently a design choice not to build toward it, per §6.3. |
| Knowing whether any of this is even necessary right now (food-days/booze-days) | **Tooling** — `stocks.food-drink` gap, the same one food-drink logistics already flagged as the project's sharpest missing read. |
| Grading any rung's prediction about fort-owned stock levels | **Tooling**, and a direct consequence of the row above — this is this brief's own central finding, restated. |
| Well construction | **Tooling** (no blueprint, no channel-to-water perception primitive) — not a knowledge gap; the domain mechanism is fully understood (§6.2). |
| Whether stagnant vs. flowing water matters for drinking | **Knowledge** — genuinely not established by any source checked, twice now (this report and the food-drink report independently). |

---

## Not verified — summary

Collected here for scanning; each is also flagged individually above.

- Whether this install's fishing/farming/well mechanics match `0.53.16`
  exactly, versus a generic current-wiki description — inferred from
  mechanic stability since the v50 rewrite, not confirmed against this
  build's own patch notes (same caveat the food-drink report already
  carries, not re-derived here).
- Whether stagnant water is treated differently from flowing water for
  drinking purposes — checked in two independent sources this session
  (Thirst article, Well article) and in the prior food-drink report; no
  source addresses it either way.
- Whether `landmarks.list`/`get`'s building-kind enumeration currently
  surfaces farm-plot, still, kitchen, fishery, butcher-shop, or well as
  distinct `kind` values — the underlying mechanism is verified for other
  kinds (`"Stockpile"`, `"Wagon"`); these specific values were not checked
  this session.
- Whether `dfhack.buildings` exposes a struct-level path to civzone
  construction (the mechanism a zone-creation tool would need) — flagged as
  the concrete next research step by `research/2026-09-16-food-and-drink-logistics.md`
  and not re-investigated here; this report treats the zone gap as a
  standing, previously-established fact rather than re-deriving it.
- The exact field-level detail of RFR's `RiverTile`/`RiverEdge` messages and
  `MapBlock.water_stagnant`/`.aquifer` — named by a single upstream source
  fetch in `research/2026-08-25-spatial-perception.md`, not independently
  confirmed against this install's own binary (that report's own stated
  limitation, carried forward here since it directly bears on §5's water/
  aquifer rows).
- The RTS/HTN/GOAP/triage cross-domain claims in §1 are search-engine-
  summarized secondary sources (abstracts, industry retrospectives, review
  articles), not the primary papers read in full — flagged as moderate
  confidence throughout §1, consistent with how this session actually
  gathered them, and distinct from the DF-specific claims in §6, which were
  fetched and read as full page content.

## Sources

DF wiki (fetched this session): [Fishing](https://dwarffortresswiki.org/index.php/Fishing),
[Farming](https://dwarffortresswiki.org/index.php/Farming),
[DF2014:Thirst](https://dwarffortresswiki.org/index.php/DF2014:Thirst),
[Well](https://dwarffortresswiki.org/index.php/Well),
[Embark](https://www.dwarffortresswiki.org/index.php/Embark).

Cross-domain (web search, secondary-source summaries, this session):
StarCraft build-order adaptation and strategy prediction (Yonsei University;
IJCAI 2020, "Design Adaptive AI for RTS Game by Learning Player's Build
Order"); HTN vs. GOAP in game AI (F.E.A.R. GOAP postmortem, Game Developer;
"Planning with Hierarchical Task Networks in Video Games"; Wikipedia's HTN
summary); Precedence Constraint Posting / Partial Order Schedules (CMU, "From
Precedence Constraint Posting to Partial Order Schedules"); aviation
checklist design (Degani & Wiener 1993 as cited across multiple fetched
summaries; code7700.com "Checklist Philosophy"; SKYbrary); clinical triage
algorithms and decision trees (multiple PMC review articles on triage
computational systems).

Repo files read in full or in cited sections this session: `CLAUDE.md`,
`docs/PURPOSE.md`, `docs/AGENT-ARCHITECTURE.md`, `docs/MEMORY-ARCHITECTURE.md`,
`memory/dfhack-environment.md`, `memory/agent-memory-standards.md`,
`research/2026-08-25-spatial-perception.md`,
`research/2026-09-16-food-and-drink-logistics.md`, `scripts/dfhack/TOOLS.yaml`,
`dfqueue/schema.py`, `dfqueue/grade.py`, `learning/live_signals.py`,
`agents/architect/role.md`, `agents/quartermaster/role.md`,
`agents/ROSTER.yaml`, `blueprints/README.md` and directory listing,
`evals/compliance/README.md`, `decisions/DECISIONS.md` (2026-08-25 rows).
