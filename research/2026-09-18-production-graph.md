# Representing DF logistics and manufacturing as a graph

Date: 2026-09-18. Read-only research: raws and DFHack source read directly on
VM 103 over SSH (`df@`, key from `.env`), plus a handful of non-mutating
`dfhack-run lua` reads with the fort confirmed paused throughout
(`dfhack.world.ReadPauseState()` returned `true` before and is not touched by
anything below). No files were written to the VM, no game state changed, no
deploy. This is the design input for `decisions/DECISIONS.md` 2026-09-17,
"Game figures belong in a database with calculators, not in prose."

## Bottom line

**Use a directed hypergraph of typed nodes (items/materials) and typed
hyperedges (processes with N inputs and M outputs), stored as ordinary
relational tables (SQLite, following `dfqueue`'s own pattern), not a graph
database and not a graph library.** A process is not representable as a
normal graph edge because it can have several inputs and several outputs at
once (brewing consumes a plant *and* an empty barrel, produces drink *and* a
seed), this is exactly the case a plain directed graph cannot express
without either fan-out tricks that break "an edge is one process" or a
Petri-net-style bipartite encoding that is heavier than this project needs.
The **AND-OR graph** is the right mental model for "what's blocking a goal"
(question 1): every node is an AND of its hyperedge's reagents, and a node
with multiple producing hyperedges is an OR of routes. It is the same
structure a hypergraph already is, viewed from the goal side, so it costs
nothing extra to add. **A small linear program (not MIP, not a graph
shortest-path)** answers "make 100 drink at least cost" (question 3),
because the real question is a flow-balance/cost-minimization problem over
a network with several routes to one good, which is textbook LP, and this
fort's scale (dozens of item types, a handful of processes) makes even a
naive simplex adequate, a MIP only earns its keep once whole-workshop
integer decisions (build N more stills) enter the objective, which is a
later increment, not v1.

**Extraction is asymmetric, and that shapes the whole design.** Reactions,
their reagents/products/skills/workshop links, plant properties, and
material densities/values are raw text, exact for this game version, and
already partly extracted (`research/2026-09-17-seed-ratios.md`). But four of
the user's named attributes are simply not raw-extractable at all: **job
duration, skill's exact speed effect, hardcoded engine job types'
(milling/thread/extract) seed and yield math, and container capacity for the
three most common containers (barrel, bin, bucket)** are compiled into DF's
closed-source binary with no corresponding raw token. This is not a gap in
this research pass; it is a hard ceiling this project has hit before
(`research/2026-09-17-seed-ratios.md`, "What could not be verified"), newly
confirmed here for a wider slice of the model.

## 1. Formalism

The concrete requirement, restated domain-neutrally: model a bipartite
production system where **transformations (not just relationships) connect
sets of resources**, several transformations can produce the same resource,
and the system must answer reachability/blocking, alternative-route
enumeration, weighted route costing, and flow-over-time questions.

| Candidate | Fits the "N inputs, M outputs" case? | Fits "several ways to the same good"? | Fits weighted route costing? | Fits flow over time? | Verdict |
|---|---|---|---|---|---|
| **Plain directed graph, node = item, edge = "produces"** | No. An edge is one input, one output; a real reaction with 2 reagents and 2 products cannot be one edge. Modelling it as several edges loses the fact that they fire *together, once* | Multiple in-edges to a node already model this, so this part is fine | Shortest-path works only if each edge is truly independent, which reactions are not (the barrel used by one brew is not consumed by an unrelated brew) | No native concept of throughput | The reason "just do a graph" fails first, and the reason the user's own framing (see below) already reaches past it |
| **Directed hypergraph** (a hyperedge connects a *set* of input nodes to a *set* of output nodes) | Yes, exactly. A hyperedge *is* a reaction: reagents in, products out, one atomic unit | Yes: a node with in-degree (in hyperedge terms) > 1 has multiple producing processes, each independently rankable | Yes: attach cost/time/yield to the hyperedge itself; a "route" is a subhypergraph selected from among the options at each node | Not built in, but the hyperedge is the natural place to attach a rate (throughput per unit time), turning it into a capacitated flow problem (below) | **Best fit for the static structure** |
| **Petri net** (places = items, transitions = processes, tokens = quantity) | Yes, and slightly more expressive: models concurrency, in-flight jobs (a workshop holding a job that has consumed reagents but not yet produced), and container occupancy as its own place | Yes | Costing needs to be bolted on (Petri nets are about firing/reachability, not optimization) | Yes, natively, Petri nets are literally a token-flow model and are the standard tool for analysing throughput/bottlenecks in manufacturing systems (this is the direct academic lineage: Petri nets are how manufacturing systems engineering already formalises exactly this problem, which is what "restate domain-neutrally, ask which field owns it" (`CLAUDE.md` project rule) turns up) | **Best fit if the goal were simulating the fort's dynamics**, which it is not: this project already has DF itself as the simulator and only wants to *reason about* the structure and *measure* real flow (question 4) from DFHack reads. A Petri net earns its complexity when you need to simulate; here it would duplicate machinery DF already runs. Worth knowing this is the "real" model livingunderneath, useful vocabulary for §4 below, not worth implementing |
| **AND-OR graph** (a goal node is satisfied by an AND of its prerequisites; alternative ways to satisfy it are OR'd) | Yes, and it is literally the hypergraph read backwards from a goal | This *is* the OR | Costing an AND-OR tree ("cheapest way to satisfy this AND-OR goal") is a well-studied search problem (AO*) | No | **Best fit for question 1 specifically** ("what's blocking a well"): walk the AND-OR expansion from the goal, and the first unsatisfied leaf with no producing hyperedge at all is the blocker, with the missing quantity read off the hyperedge's reagent count. This is not a separate data structure from the hypergraph, it is a traversal of it, rooted at a goal instead of at raw materials |
| **Bill of Materials / MRP** (manufacturing's own standard tool: an item's BOM lists its immediate components and quantities; MRP nets that against on-hand inventory and lead time to produce a build plan) | Yes for single-recipe items; BOMs assume **one** recipe per item by convention (a BOM is *a* bill, not *the* choice among bills), DF's "several ways to brew a drink" (four brewable crops) breaks the one-recipe assumption unless you keep several BOMs per item and pick one, which just re-invents the OR-node | This is exactly where classic BOM/MRP is weakest, it is designed for one sourcing decision per part number, made once at design time, not chosen dynamically per production run | MRP's lead-time offsetting is directly the right idea for "when do I need to start" | MRP is literally built for period-by-period requirements planning, produced/consumed/backlog per period is MRP's native output shape | **The right vocabulary for question 4** (periodic planning) even though the *structure* underneath still needs to be a hypergraph with OR-nodes, not a strict one-recipe-per-part BOM. Borrow MRP's period-bucket netting logic, not its single-recipe assumption |
| **Flow network / max-flow-min-cut** (capacitated edges, source/sink) | Only if every process is coerced into single-input/single-output, which loses the AND semantics (a reaction needs *both* a plant and a barrel, not either) | Multiple parallel edges model this adequately | Min-cost flow is a real, standard formulation for "N units of output at minimum cost through a network," and is a special case of the LP in §3 | Yes, natively, flow *is* a rate | **Good for the specific "min-cost drink" query once the hypergraph is linearised into flow-conservation constraints** (§3), not a replacement for the hypergraph as the source-of-truth model. A hyperedge with 2 inputs is expressed in the LP as two flow-conservation equations sharing one "batches run" variable, not as a graph edge |

**Where a plain DAG or shortest-path breaks down, concretely**: shortest-path
assumes each edge is used or not, independently of every other edge's use.
DF violates this constantly, brewing plump helmet and cooking plump helmet
compete for the *same upstream plant supply*, so the "edge cost" of one
depends on how much of the other is already claimed. That is a resource-
contention problem, not a path problem, which is precisely why LP (§3), not
Dijkstra, is the right tool once costing enters the picture. A DAG is fine
for the *pure reachability* question (question 1) precisely because
reachability doesn't need to allocate a scarce resource, only to ask whether
a path of any width exists at all.

**Recommendation**: store the hypergraph (nodes + hyperedges) as the single
source of truth. Treat "AND-OR blocking search" and "min-cost flow LP" as
two different **read-only queries over the same stored structure**, not two
different data models to keep in sync. This is the same "one snapshot, many
projections" principle `docs/AGENT-ARCHITECTURE.md` §5 already uses for
fort-state queries, applied to static domain data instead of live state.

## 2. What is actually extractable from this install

Verified live against VM 103 this session (DF v0.53.16 linux64 ITCH,
DFHack 53.16-r1.1), reading `/opt/df/game/data/vanilla/` raws directly and,
for a handful of enum/struct facts no raw file could answer, non-mutating
`dfhack-run lua` reads with the fort paused throughout. Where
`research/2026-09-17-seed-ratios.md` already settled a figure, that is
cited rather than re-derived.

| User's attribute | Status | Evidence |
|---|---|---|
| **Job time** | **Hardcoded, unavailable.** No raw token for reaction duration exists anywhere in the shipped reaction files (`grep`'d `reaction_other.txt`, `reaction_smelter.txt`, `reaction_adv_carpenter.txt`, `reaction_dyes.txt` for `DURATION`/`WORK_TIME`/`JOB_TIME`: zero hits). DFHack's own docs tree has no job-timing doc either (`grep -il` across `hack/docs/docs/` for job speed/time turned up only unrelated hits: `fire-rate.txt`, `gui/quickfort.txt`, `prioritize.txt`, `History.txt`). Live-verified that a job struct *does* carry a live countdown field (`job.completion_timer`, read off real jobs in Uniboslan's own queue, e.g. job 371 `Sleep` mid-flight at `completion_timer=1`, several `PlantSeeds` jobs queued at `-1`/not started), so DF computes a duration at job start and counts it down, but the **formula that sets the initial value is compiled into the binary**, not in any file this install ships. **Verified: no raw source exists. Assumed: the wiki's qualitative "skill halves time up to a cap" description is directionally right, not independently confirmed against source** (DF is closed-source; the wiki's own figures are community reverse-engineering, unattributed to a specific patch). |
| **Food/drink yield per unit** | **Data, verified for the raw-defined reactions.** `[PRODUCT:100:5:DRINK...]` on `BREW_DRINK_FROM_PLANT` (read directly, `reaction_other.txt` line 265) gives an exact, unconditional 5 drink units + 1 seed per plant unit brewed, with `[PRODUCT_DIMENSION:150]` fixing the produced material's per-unit volume (also read directly). This is the strongest-evidence figure in the whole model: 100% chance, not a range. Cooking's zero seed return is corroborated by DFHack's own shipped tool doc, not a raw token (`hack/docs/docs/tools/seedwatch.txt`, already cited by `research/2026-09-17-seed-ratios.md`). **Verified for brew/quarry-bush-bag/pig-tail-paper. Assumed/unavailable for milling, thread, and sweet-pod extract**: these are hardcoded `df.job_type` values (`MillPlants`, `ProcessPlants`, `ProcessPlantsBarrel`/`Vial`, confirmed present in `hack/lua/plugins/workflow.lua` by `research/2026-09-17-seed-ratios.md`) with no corresponding raw text, so their yield is a wiki claim only. |
| **Weight for hauling** | **Data, computable.** Item weight in DF is volume × material density (a documented DF mechanic; the arithmetic itself is not exposed as one raw field, but both inputs are raw data). Volume: raw-defined `[SIZE:n]` per item type where the item type is raw-moddable (verified live: `ITEM_TOOL_JUG` carries `[SIZE:300]`, `ITEM_TOOL_LARGE_POT` carries `[SIZE:5000]`, read directly from `item_tool.txt`). Density: `[SOLID_DENSITY:n]` per material (verified live for granite `2670`, stainless steel `7850`, and per-crop plant materials at `500`/`900`/`1000` in `material_template_default.txt`; verified for a real ore, hematite at `5260`, in `inorganic_stone_mineral.txt`). **Gap found this session, not previously flagged in this project's docs: barrel, bin and bucket carry NO raw item definition at all.** `grep`ing every `vanilla_items/objects/*.txt` file for `ITEM_TOOL:ITEM_TOOL_BARREL`/`_BIN`/`_BUCKET` found nothing, and a live enum read of `df.item_type` confirms `BARREL`, `BUCKET`, and `BIN` are their own top-level hardcoded item-type values (alongside `CAGE`, `ANVIL`, and others), distinct from `TOOL` (which is where jug and pot live as raw-moddable subtypes). **So the three containers this project's own doctrine and tools most depend on (barrel for brewing/food storage, bin for stockpiles, bucket for water-hauling) have no raw-exposed size or capacity, those numbers are hardcoded and unavailable from any file on this install.** Wiki figures for their capacity exist but are unverified against this install's source. |
| **Value** | **Data, verified.** `[MATERIAL_VALUE:n]` per material (verified live, hematite `8`) and `[VALUE:n]` per raw-moddable item type (verified live, jug and large pot both `10`). Combines with the same density/volume path above for a computed item value; DF's exact value formula (multipliers for quality, size, craftedness) is community-documented, not raw-exposed, so the *combination* formula is an assumption even though each input figure is verified data. |
| **Seed return** | **Data for 3 of ~7 fates, hardcoded/unavailable for the rest.** Already fully settled by `research/2026-09-17-seed-ratios.md`: brewing, quarry-bush-bagging, and pig-tail papermaking are raw-verified 100%×1; cooking is verified-zero from a DFHack tool doc; milling/thread/sweet-pod-extract are hardcoded job types with no raw seed math, a genuine ceiling on what this install can answer, not a research gap. |
| **Container needs** | **Data, verified for which reactions need one, hardcoded for what "one" means physically (see weight row above).** Every container-consuming reaction reads as an explicit reagent line with `[EMPTY]`/`[CONTAINS:x]`/`[PRESERVE_REAGENT]` tags (verified directly: `BREW_DRINK_FROM_PLANT`'s `barrel/pot` reagent, `MAKE_SOAP_FROM_TALLOW`'s `lye container`, `PROCESS_PLANT_TO_BAG`'s `bag` reagent, all read from `reaction_other.txt`). So "does this process need a container, and of what functional class (`FOOD_STORAGE_CONTAINER`, a bag, a bucket)" is fully raw-derivable; "how much fits in one" is not, per the row above. |
| **Workshop needed** | **Data, verified, and structurally interesting.** Every `[REACTION:...]` block names its workshop via `[BUILDING:WORKSHOP_TOKEN:hotkey_or_custom]` (verified directly across dozens of reactions: `STILL`, `KITCHEN`, `TANNER`, `FARMER`, `KILN`, `SOAP_MAKER`). But **the workshop types themselves are hardcoded, not raw-defined**, live-read the `df.workshop_type` enum (24 entries: `Carpenters`, `Farmers`, `Masons`, ..., `Still`, `Kitchen`, ..., `Custom`) and confirmed the only raw-authorable workshop file on this install, `vanilla_buildings/objects/building_custom.txt`, defines exactly the small set of `CUSTOM_*` workshop tokens the reactions above reference (`CUSTOM_T` for tanner, etc.) layered on top of the fixed enum, not a mechanism for adding a wholly new workshop kind. This means "which workshop does X need" is data; "what workshop kinds exist at all" is a fixed, version-pinned list this project should treat as a constant to refresh on a DF update, not something to parse generically. |
| **Labor** | **Data, verified.** `[SKILL:BREWING]` etc. on every reaction (verified directly, dozens of examples) maps 1:1 to a `df.unit_labor` code, already exploited live by this project's own `df-overseer-workshop.lua` (BREWER code 30, COOK code 38, confirmed live per that file's own header). |
| **Skill's effect on speed/yield** | **Hardcoded, unavailable**, same ceiling as job time. The harvest-yield formula the seed-ratios research quotes (`rand(2)` coin flips gated on skill thresholds) is sourced from the pre-v50 DF2014 wiki namespace, not this install's files, and explicitly flagged there as unverified against v53.16 source. Nothing found this session changes that. |
| **Growing time/seasons** | **Data, verified.** `[GROWDUR:n]` and season tags per crop, already fully tabulated in `research/2026-09-17-seed-ratios.md` §3 from `plant_standard.txt`, re-confirmed present this session. |

**Net honest answer to "which of the user's desired attributes can we not
have"**: job duration, the exact skill-to-speed curve, the seed/yield math
for every hardcoded (non-`CustomReaction`) job type, and the physical
capacity of the three commonest containers. All four are compiled into the
DF binary. Where the wiki states a number for these, it is usable only as a
`prior` under this project's own doctrine status vocabulary
(`doctrine/seed.yaml`'s header), never `verified`, because no source
describing 53.16 backs it.

## 3. Route choice: what solves "100 drink at minimum cost"

**Recommendation: a small linear program, solved with `scipy.optimize.linprog`
or a hand-rolled simplex if the dependency is unwanted; not a MIP, not a
graph search.**

Reasoning through the candidates:

- **Greedy (always pick the cheapest single route)** is wrong the moment two
  goals share an upstream resource: greedily brewing plump helmet for drink
  can starve the kitchen's plump helmet supply, and greedy has no way to see
  that cost until it has already committed. It only works when goods do not
  compete for shared inputs, which is not this fort's situation (plump
  helmet feeds drink, food, and seed stock at once, exactly the case the
  user's brief calls out).
- **Critical-path / longest-path methods** answer "when will this be done,"
  not "what's the cheapest mix," and DF's production graph is not a
  project schedule with a single deadline; it is a recurring, steady-state
  flow. Not the right tool for this specific query, though relevant to
  question 4's period-based framing.
- **Mixed-integer programming** earns its cost only when a decision variable
  must be a whole unit that cannot be fractionally chosen and where that
  matters to the answer, e.g., "build 2 more stills" as a discrete
  capital decision. For "how much of the harvest goes through which
  process," the natural variables (tiles planted, plants routed to fate X)
  are usefully continuous/fractional at the planning-fidelity this project
  operates at (a 15-dwarf fort measured in seasons, not units), so relaxing
  to LP loses nothing decision-relevant and buys an easy, fast, always-
  optimal solve. Reserve MIP for a later increment once "how many workshops
  to build" becomes a live question, and even then, a fort this size has so
  few integer choices that branch-and-bound would find the answer instantly
 , proportionality still points at LP for the routing question and MIP only
  for the (separate, smaller) sizing question.
- **Min-cost flow** (a special LP structure) is the closest textbook match:
  nodes are items, "edges" are runs of a hyperedge (a reaction), and the
  objective is cost per unit of final output subject to flow conservation
  at every node and the reagent ratios a hyperedge fixes. This is literally
  what Helmod and FactorioLab (§5) already do for Factorio, and DF's
  production structure (finite recipe list, multiple recipes per output,
  occasional cycles like fertilizer-from-plant-byproducts) is the same
  shape, at a much smaller scale.

**What answers "what does choosing this crop cost elsewhere"**: this is a
shadow-price / opportunity-cost question, which an LP answers for free once
solved, the dual value on the "plump helmet available" constraint *is* the
marginal cost of committing one more unit of plump helmet to (say) brewing,
which is exactly "what I give up by choosing this route." This is a genuine
reason to prefer LP over a bespoke greedy heuristic: the answer to the
user's second sub-question falls out of the same solve as the first,
rather than needing separate logic.

**Proportionality for a 15-dwarf fort**: the LP here has at most a few dozen
variables (one per reaction × plausible crop, plus container/labor
constraints) and a few dozen constraints. Any LP solver handles this in
microseconds; the "at scale" concern that motivates Helmod/FactorioLab's
simplex tooling is a Factorio megabase with thousands of recipe instances,
not a 15-citizen fort with six crops and a dozen reactions. **Do not import
a general-purpose LP/MIP library speculatively.** Concretely:

| Option | New dependency | Verdict |
|---|---|---|
| `scipy.optimize.linprog` | `scipy` (confirmed **not installed** in this repo's ambient Python this session, a real new dependency, not already paid for) | Reasonable if the project accepts one well-known, actively maintained scientific dependency; battle-tested simplex/interior-point implementation, no need to write or verify a solver by hand |
| `pulp` (LP/MIP modelling layer over CBC) | `pulp` (also confirmed **not installed**) | Heavier than needed for pure LP; earns its place only when MIP (integer workshop-count decisions) is actually wanted, per the staged build order below |
| Hand-rolled simplex (a few dozen lines, well-known algorithm, this fort's scale makes even an unoptimized implementation fast) | none | **Recommended for v1.** Keeps the project's `pytest`-only dependency footprint (PyYAML is the only real one today, confirmed by grep of the repo's requirements files) and matches this project's own stated caution about adding a solver being "a real cost." A from-scratch simplex is unit-testable the same way `learning/predictions/`'s calculator functions already are, and the problem sizes here make performance a non-issue |
| `networkx` for the underlying graph/hyperedge bookkeeping | `networkx` (confirmed **not installed**) | Not needed. The hypergraph is small enough that plain Python dicts/dataclasses over the SQLite tables (§ data model) do the job, and `dfqueue`'s own precedent is plain SQLite with hand-written schema/store modules, not a graph library |

**Recommended v1 path**: no new dependency at all. Implement the LP as a
small, hand-written simplex (or even simpler: for the acyclic, small-cycle
case DF actually presents, a direct linear solve via Gaussian elimination
over the flow-conservation equations may suffice without a general simplex,
mirroring Kirk McDonald's original Factorio calculator's own history of
starting non-simplex and only adding a real solver once cycles demanded it,
per §5). Escalate to `scipy.optimize.linprog` only if a real cycle (DF does
have some, e.g., byproduct materials feeding back into fertilizer/dye
production) actually breaks the direct-solve approach in practice, which
should be discovered by a unit test on real extracted data, not assumed
upfront.

## 4. Measurement over time

**The honest floor, stated first: this project has no scheduler
(`docs/AGENT-ARCHITECTURE.md`, "Strategy" layer notes this explicitly,
2026-09-17: "today only point-in-time stock reads exist... trends need
history, which ties this to the still-missing scheduler"). Nothing below
changes that. A measurement loop with no cron/systemd timer calling it is a
function that exists and is never invoked.**

What DFHack can actually expose, checked this session:

- **Periodic stock snapshots and deltas.** `df-overseer-stocks.lua` already
  does this for a point in time (`get_food_drink`/`get_seeds`, verified
  live). A **produced-per-period** number is not natively tracked anywhere
  in DF's own state; it must be derived as `snapshot(t2) - snapshot(t1) +
  consumed_in_between`, which needs consumption tracked separately (below)
  or it silently conflates "we made more" with "we made some and ate some."
- **Job completion records.** `eventful`'s `JOB_COMPLETED` event is real and
  already relied on (`docs/AGENT-ARCHITECTURE.md` §3, "verified: live
  `eventful` callback firing confirmed, `decisions/DECISIONS.md`
  2026-09-11"). A completed job carries its `job_type` and (for
  `CustomReaction`) its `reaction_name`, so **"how many BREW_DRINK_FROM_PLANT
  jobs completed since t1" is a real, cheap, event-driven count**, this is
  the cleanest primary signal for *produced*, better than snapshot deltas
  because it does not need consumption netted out. This session additionally
  live-confirmed the underlying mechanism it depends on: a running job
  carries a real `completion_timer` field (read off Uniboslan's own live job
  queue, e.g., a `Sleep` job at `completion_timer=1`), consistent with
  `JOB_COMPLETED` firing off a real countdown rather than being a synthetic
  event.
- **Item creation timestamps, newly confirmed this session, not previously
  in this project's docs.** A live-read barrel item (`world.items.other.
  BARREL[0]`, Uniboslan, fort paused) carries a plain `age` field (read as
  `21036`, a tick count). Subtracting `age` from the current game tick
  (`dfhack.world.ReadCurrentTick()`, standard DFHack call) at read time
  gives an item's creation tick without needing to have been watching when
  it was made, useful for a **retrospective produced-in-period** count that
  does not depend on the measurement loop having been running continuously,
  which matters given the "no scheduler" constraint: a late-starting loop
  can still reconstruct history for anything not yet destroyed/consumed.
  **Not verified**: whether `age` is reset by any event short of
  destruction (e.g., does moving an item or a stockpile re-sort reset it?)
 , only one item was sampled this session.
- **Hauling jobs specifically.** `StoreItemInStockpile`/`StoreItemInVehicle`-
  family jobs exist as ordinary `df.job_type` values and would fire
  `JOB_COMPLETED` the same as any other job, not independently live-tested
  this session for a real haul, but structurally identical to the
  `ConstructBuilding`/`PlantSeeds` jobs actually observed in Uniboslan's live
  queue. This is the mechanism for **actually transported to destination**:
  a completed haul job names its destination building/stockpile, so
  "produced but never hauled" (the user's stated failure mode: a fort that
  produces enough and still starves because nothing reaches the right
  stockpile) is answerable as "count of production-job completions minus
  count of haul-job completions whose source item traces to that
  production," not natively tracked by DF as one number.
- **The gamelog and announcements.** Confirmed live this session
  (`world.status.announcements`, 11 real entries on Uniboslan) that this
  channel exists and is cheap to read, but it does not carry
  produced/consumed *counts*, it is event narration ("a merchant needs the
  depot"), not a production ledger. Not useful for quantity measurement,
  useful only as a coarse "something happened" signal, consistent with
  `research/2026-09-16-player-visibility.md`'s own characterization of this
  channel.

**Cheapest honest measurement loop, given no scheduler exists**:

1. A single DFHack read tool, `production_diff(since_tick)`, built the same
   way `get_diff_since` already works (`eventful`-backed), counting
   `JOB_COMPLETED` events by `job_type`/`reaction_name` since the last call.
   This is produced, directly.
2. Consumed is the mirror: reagent-consuming jobs of the same event stream,
   or (simpler, and matching `df-overseer-stocks.lua`'s existing pattern) a
   stock-snapshot delta with produced subtracted out, since `consumed =
   produced - Δstock` is cheap arithmetic once produced is known from step 1.
3. Transported is the gap between production-job completions and the
   corresponding haul-job completions, per the hauling-jobs paragraph above
  , genuinely not built anywhere in this project yet, and the piece most
   worth prototyping first given it directly answers the user's named
   failure mode.
4. **What this cannot see, regardless of build effort**: anything that
   happened between two calls of the tool if the tool is not actually being
   invoked on a schedule. `eventful` callbacks fire only while DFHack's Lua
   environment is alive and the callback is registered; a callback-based
   design accumulates state correctly across a long *running* period but
   loses everything if the DF process itself restarts before a call drains
   it (mirrors the caution already recorded for `eventful`-based diffing
   elsewhere in this project). The `age`-field approach (item 3 above) is
   the honest fallback for exactly this gap: it can reconstruct existence-
   and-creation-time retrospectively even after a cold start, at the cost of
   not seeing anything already consumed/destroyed by the time anyone looks.

## 5. Prior art

**Factorio planners (Helmod, FactorioLab), confidence: moderate, verified
via web search of each project's own forum/wiki/GitHub pages this session,
not by reading their source directly.** Both converge on the same answer
this report reaches independently: production-chain math with cycles and
multiple recipes per output is solved with the **simplex algorithm** (linear
programming), not a graph search or a bespoke heuristic. FactorioLab's own
history is directly instructive: it began as (and Kirk McDonald's original,
widely-used Factorio calculator remains) a **non-simplex, direct
matrix/graph solve for the acyclic case**, and a true simplex solver was
added specifically because **recipe loops** (his own example: iron plates
need iron gears, iron gears need iron plates) break a simple forward
computation. This is exactly the escalation path recommended in §3: start
direct, add simplex only if a real cycle demands it. Helmod's own
documentation states the same trigger condition (multi-output recipes and
circular dependencies) for when its matrix solver is needed versus when a
simpler calculation suffices.

**Manufacturing and operations research** already owns this problem more
broadly than the two Factorio tools: Bill of Materials / MRP is the
decades-old industrial-engineering answer to "what does producing X need,
netted against on-hand stock, over time" (§1's table), and min-cost flow /
LP is the standard OR formulation for "cheapest mix of processes to hit a
target output" once multiple recipes and shared resources are in play. This
project's own "restate the problem domain-neutrally, ask which field owns
it" rule (`CLAUDE.md`) is well served here: nothing about DF's production
economy is novel enough to need new theory, only enough restraint to apply
old theory at the right scale.

**Petri nets**, per §1, are the academic home of "manufacturing system flow
and bottleneck analysis" specifically, and are worth knowing about as
vocabulary (a "place" is exactly a stockpile/item count, a "transition" is
exactly a workshop reaction) even though this project should not implement
one, DF itself is already the token-flow simulator; re-implementing that
in a Petri net would duplicate the game rather than reason about it.

**The Factorio Learning Environment (2025), confidence: moderate-high,
verified via web search of the paper's own abstract/arXiv listing
(arXiv:2503.09617) this session.** FLE is **an agent benchmark, not a
planner and not a solver.** It evaluates LLM agents on long-horizon
automation and program synthesis inside Factorio (a "lab-play" set of eight
fixed tasks, plus open-ended "build the largest factory" scoring), accepted
at NeurIPS 2025. It has no relationship to computing production routes , 
it measures whether an *agent* can build a factory well, using whatever
methods the agent brings, not whether a particular route-computation
algorithm is good. **Citing it as prior art for "how to compute production
graphs" would be a category error**; it belongs, if anywhere, in this
project's own agent-evaluation thinking (`evals/`), not in the production-
graph design.

**Is there a tuned ML model for recipe/production graphs that would beat a
solver? No, and this is a plain finding, not a hedge.** Nothing turned up
in this pass, and there is a structural reason not to expect one: LP/min-
cost-flow already finds the exact, provably optimal answer for this problem
class in microseconds at this scale. An ML model could only match that
(never beat it on the metric that matters, cost), while adding training
data requirements, a maintenance burden, and non-determinism this project
has already rejected elsewhere for good, evidenced reasons (self-reported
LLM confidence is "confident, plausible, largely uncorrelated with truth,"
`docs/MEMORY-ARCHITECTURE.md`; the same logic applies to trusting a learned
model over an exact solver here). "Nobody really does this" is the honest
read: Helmod and FactorioLab, the two most mature tools in the closest
adjacent domain, both reach for simplex, not a model.

## 6. Fit with this project's rules

- **Never a rendered map, never coordinates.** Nothing in this model touches
  space at all, nodes are items/materials, hyperedges are processes; the
  graph is topologically about *what feeds what*, not *where*. This is a
  clean fit with design commitment #1 by construction, not by discipline:
  there is no coordinate field anywhere in the schema for anyone to
  accidentally leak.
- **Player-visibility policy.** The extraction sources (raws, reaction
  definitions, material properties) are exactly the class of information
  `research/2026-09-16-player-visibility.md` calls "fully visible, no
  spatial hiding", general game-mechanical knowledge any player can read
  from the raws folder or learn from playing, not tied to any hidden tile
  or hidden unit. The *live* half of the model (current stock levels,
  which workshops are actually built, job completion counts) must still
  route through the same visibility-safe tools this project already built
  (`df-overseer-stocks.lua`'s `is_on_hidden_tile` check is the precedent to
  reuse, not reinvent, if a future "what's blocking my well" tool needs to
  check whether the fort actually possesses a resource versus merely
  knowing the recipe exists).
- **Code does mechanics, the model does judgment.** The hypergraph
  extraction, the AND-OR blocking search, and the LP solve are all
  deterministic code, exactly the "if it is computable, it is a tool"
  principle (`docs/AGENT-ARCHITECTURE.md` principle 1). What needs an
  agent: **which objective to optimize for** (cheapest drink, most
  variety, fastest to a target, safest against a single point of failure
  like relying on one crop) is a judgment call with tradeoffs a fort's
  current situation should inform, and **interpreting a blocked-goal report
  in context** (is stone access actually worth digging for right now, given
  everything else in flight) is exactly the kind of "judgment under
  uncertainty" that principle 1 reserves for an agent. Concretely: a new
  read tool (`production.find_blocker(goal)`, `production.route_options
  (good, quantity)`, `production.min_cost_plan(targets)`) belongs in
  `scripts/dfhack/` plus a Python-side calculator module alongside
  `dfqueue`, in the same "calculators are pure, unit-tested functions
  exposed as read tools" shape the 2026-09-17 decision already specifies , 
  never in an agent's own reasoning.

## Recommended data model

Two tables, following `dfqueue`'s own SQLite-plus-schema-module precedent
(`dfqueue/schema.py`, `dfqueue/store.py`) rather than a graph database or a
Python graph library, justified in §3's dependency table.

```
-- nodes: items and materials
CREATE TABLE production_node (
  id            TEXT PRIMARY KEY,   -- e.g. 'PLANT:MUSHROOM_HELMET_PLUMP', 'ITEM:BARREL', 'MATERIAL:GRANITE'
  kind          TEXT NOT NULL,      -- 'plant' | 'item_type' | 'material' | 'creature_product' ...
  display_name  TEXT NOT NULL,
  -- Attributes below are nullable on purpose: many are hardcoded/unavailable
  -- (§2) and the schema must not force a fabricated number into a field
  -- this install cannot actually answer.
  volume        INTEGER,            -- raw SIZE, where the item type is raw-moddable
  density       INTEGER,            -- raw SOLID_DENSITY, where applicable
  base_value    INTEGER,            -- raw VALUE / MATERIAL_VALUE
  status        TEXT NOT NULL,      -- 'verified_raws' | 'community_prior' | 'unavailable', per doctrine/seed.yaml's vocabulary
  source_ref    TEXT NOT NULL       -- file:line or struct field this session actually read
);

-- hyperedges: processes. One row per REACTION (or hardcoded job type).
CREATE TABLE production_process (
  id                TEXT PRIMARY KEY,   -- reaction code, e.g. 'BREW_DRINK_FROM_PLANT'
  workshop_type     TEXT NOT NULL,      -- from the fixed df.workshop_type enum
  labor             TEXT,               -- df.unit_labor code, e.g. 'BREWER'
  is_hardcoded_job  INTEGER NOT NULL,   -- 1 if this is a df.job_type with no raw text (milling etc.), 0 if a real [REACTION]
  job_time_status   TEXT NOT NULL DEFAULT 'unavailable',  -- always 'unavailable' per §2 unless DF ever exposes it
  source_ref        TEXT NOT NULL
);

-- reagents/products: the N-in, M-out edges of a hyperedge, with the
-- container/quantity/probability detail the raws actually carry.
CREATE TABLE production_flow (
  process_id     TEXT NOT NULL REFERENCES production_process(id),
  direction      TEXT NOT NULL,      -- 'reagent' | 'product'
  node_id        TEXT NOT NULL REFERENCES production_node(id),
  quantity       INTEGER NOT NULL,   -- the raw PRODUCT/REAGENT count token
  probability    INTEGER NOT NULL DEFAULT 100,  -- the raw PRODUCT probability token
  requires_empty_container INTEGER NOT NULL DEFAULT 0,  -- [EMPTY] reagent
  container_class TEXT,              -- e.g. 'FOOD_STORAGE_CONTAINER', 'BAG'
  status         TEXT NOT NULL,
  source_ref     TEXT NOT NULL
);
```

`status`/`source_ref` on every row is the load-bearing design choice: it
lets `production.find_blocker`/`min_cost_plan` degrade honestly (report "no
verified cost, hardcoded job" rather than inventing a number), and it is
literally the same discipline `doctrine/seed.yaml`'s header already
mandates project-wide, applied to this new table instead of invented fresh.

## Extraction plan

| Source | What it yields | Refresh cost on a DF version bump |
|---|---|---|
| `data/vanilla/vanilla_reactions/objects/*.txt` | Every `[REACTION:...]`: reagents, products, quantities, probabilities, workshop, skill, container requirements | Low. Plain text, `grep`-able, format has been stable; a version bump needs a re-read for new/changed reactions, not a rewrite of the parser |
| `data/vanilla/vanilla_plants/objects/plant_standard.txt` | Growdur, seasons, biome flags, brewable/millable/processable flags, `EDIBLE_*` tags | Low, same reasoning; already exercised by `research/2026-09-17-seed-ratios.md` |
| `data/vanilla/vanilla_materials/objects/material_template_default.txt`, `inorganic_*.txt` | Density, value, ignite/melting points | Low |
| `data/vanilla/vanilla_items/objects/item_tool.txt` (and siblings) | Volume/size and value for raw-moddable item types (jug, pot, etc.) | Low |
| `dfhack-run lua` reads of `df.workshop_type`, `df.item_type`, `df.job_type` enums | The fixed hardcoded vocabularies these raws reference | **Medium**: these are compiled enums, not text files, so a DF/DFHack version bump needs a fresh live read (or a df-structures XML diff) to catch additions/removals, not a `grep`. This is exactly the kind of drift `memory/dfhack-environment.md` already tracks for tool availability; the same discipline applies here |
| Wiki (community_prior only) | Job-time formula, skill's speed curve, milling/thread/extract seed math, container capacities | N/A to "refresh cost" since it is never promoted past `prior`, the version-namespace trap (`docs/MEMORY-ARCHITECTURE.md`) applies exactly as documented there |

A one-time extraction script (Python, reading a checked-out copy of the
raws the same way `research/2026-09-17-seed-ratios.md` did over SSH, or a
local raws mirror) populating the three tables above is proportionate; a
live-sync-on-every-fort-load mechanism is not needed since the raws for a
given DF version do not change mid-fort.

## Concrete queries

1. **"What's blocking a well?"** (user's use 1). AND-OR expansion from the
   goal node `BUILDING:WELL`: its dependencies (per `memory/dfhack-
   environment.md`'s already-verified well requirements: BLOCKS, BUCKET,
   CHAIN/rope, TRAPPARTS/mechanism) are each themselves either fort-owned
   (query live stock via `df-overseer-stocks.lua`-style tools) or need a
   producing hyperedge. Walk each unmet dependency's own reagent list
   recursively; the first node with **zero fort-owned stock and zero
   completable hyperedge** (e.g., no mason's workshop built yet, so no route
   to BLOCKS) is the named blocker, with the missing quantity read straight
   off that hyperedge's reagent count. This is a plain recursive/BFS
   traversal over the stored hypergraph joined against a live stock read,
   no solver needed.
2. **"What are the routes to drink?"** (use 2). `SELECT DISTINCT process_id
   FROM production_flow WHERE direction='product' AND node_id='ITEM:DRINK'`
   returns `BREW_DRINK_FROM_PLANT` (×4 crops), `BREW_DRINK_FROM_PLANT_GROWTH`,
   `MAKE_MEAD`, a plain join, not a search.
3. **"Price those routes."** For each route from query 2, join its
   `production_flow` rows against `production_node`'s attributes (yield,
   weight, value, seed return) to build the comparison table the user
   described; where an attribute's `status` is `unavailable` (job time),
   the query returns that honestly rather than a fabricated number.
4. **"Make 100 drink at minimum cost."** The LP from §3, over exactly the
   routes query 2 returns, subject to fort-owned stock as the resource
   bound.
5. **"What does choosing this crop cost elsewhere?"** The same LP's dual
   values / shadow prices on the shared-resource constraints (e.g., "plump
   helmet available this season"), per §3.
6. **"Measure flow."** The `production_diff(since_tick)` tool from §4,
   joined against `production_process` to label each `JOB_COMPLETED` event
   by which node(s) it produced/consumed.

## Measurement plan

Covered in full in §4. Summary: `JOB_COMPLETED` events (via `eventful`,
already a verified mechanism in this project) for produced; stock-snapshot
deltas netted against produced for consumed; haul-job completions matched
against production-job completions for transported. All three need the
still-missing scheduler to run continuously; the `age` item field is the
one piece that partially survives a cold start. None of this is built yet.

## Staged build order, cheapest useful thing first

1. **Extraction script + the three SQLite tables above**, seeded from the
   raws already read this session and `research/2026-09-17-seed-ratios.md`.
   No solver, no live DFHack calls needed for this step. Directly unblocks
   query 2 and 3 (route listing and pricing) with zero new runtime
   dependency.
2. **`production.find_blocker(goal)`** (query 1): a recursive traversal
   joined against the existing `df-overseer-stocks.lua`/`df-overseer-
   workshop.lua` live-read tools. This is the single highest-value, lowest-
   cost addition, since it directly answers the motivating "well" example
   and needs no new math, only a join over data step 1 already produced.
3. **The direct/hand-rolled LP solve** (§3) for query 4 and 5, unit-tested
   against the extraction from step 1 the same way `learning/predictions/`
   already unit-tests its calculators. Escalate to `scipy.optimize.linprog`
   only if a real cycle in the extracted data breaks the direct solve.
4. **`production_diff(since_tick)`** (§4 item 1), the produced/consumed
   half of measurement, reusing the `eventful` mechanism already verified
   live elsewhere in this project.
5. **Haul-job matching for transported** (§4 item 3): the genuinely new,
   unbuilt piece, and the one that most directly answers the user's stated
   failure mode ("produce enough and still starve because nothing reaches
   the right stockpile"). Left last because it needs step 4's event
   plumbing working first and is the least precedented of the five.

Steps 1 to 3 need no scheduler and no live fort at all, they are pure data
plus a solver, testable entirely offline. Steps 4 to 5 are gated on the
project's still-missing scheduler, same honest limitation as every other
per-cycle measurement idea in `docs/AGENT-ARCHITECTURE.md`.

## What could not be verified, and what DF simply does not expose

- **Job duration and the exact skill-to-speed curve.** Confirmed absent
  from every raw file and DFHack doc checked this session; a hard ceiling
  from DF being closed-source, not a research gap. `job.completion_timer`
  proves a duration exists at runtime but not how it is computed.
- **Container capacity for barrel, bin, and bucket.** Newly found this
  session: these three item types have no raw definition file at all
  (confirmed by both a raw-tree grep and a live `df.item_type` enum read),
  unlike jug and large pot, which are raw-moddable `ITEM_TOOL` entries with
  explicit `SIZE`/`CONTAINER_CAPACITY` tokens. Wiki figures for these exist
  but were not checked against source this session and should stay
  `community_prior`.
- **Seed/yield math for hardcoded (non-`CustomReaction`) job types**
  (milling, thread, sweet-pod extract), already fully documented as
  unavailable by `research/2026-09-17-seed-ratios.md`, reconfirmed rather
  than re-derived here.
- **Whether the `age` item field ever resets short of destruction**, only
  one item was sampled live this session (a barrel). Flagged as an
  assumption behind the "item creation timestamp" measurement idea in §4,
  not a confirmed property.
- **Whether a real cycle in DF's own reaction graph (e.g., ash/pearlash/
  lye feeding back into soap-making, or dye/fertilizer byproduct loops)
  actually breaks a direct (non-simplex) solve in practice**, not tested
  against the full extracted reaction set this session, since the
  extraction itself (step 1 of the build order) has not been built yet.
  This is exactly the kind of thing a unit test against real extracted
  data should settle before deciding whether `scipy` is ever actually
  needed, per §3.
- **Fine-grained hauling-job telemetry** (§4 item 3) is reasoned from the
  existence of ordinary `df.job_type` values for storage/hauling jobs and
  the already-verified `JOB_COMPLETED` mechanism, but no real haul job was
  observed completing live this session (the fort is paused). Flagged as
  structurally plausible, not empirically confirmed.
