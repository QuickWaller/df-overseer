# The production model

Status, 2026-09-18: **design settled, nothing built.** This is the build spec
for the production and logistics model. It supersedes nothing; it is the
implementable form of `research/2026-09-18-production-graph.md`, corrected by
the two feasibility audits (`research/2026-09-18-schema-extraction-static.md`,
`research/2026-09-18-schema-extraction-live.md`) and by the figures pass
(`research/2026-09-18-production-figures.md`). Decisions are recorded in
`decisions/DECISIONS.md` 2026-09-18; this file is the design, not the history.

Read this before writing any of it. Three things in here were wrong in the
first design and are corrected below: node identity, the consumption enum,
and the observation key.

---

## 1. What this is for

Three questions, in descending order of how well we can answer them:

1. **What is blocking a goal?** Answerable exactly, today, with no figures at
   all. This is the highest-value piece and the cheapest.
2. **How long can the fort last, and do we need another workshop?** Answerable
   in the present and past tense from exact reads. Not answerable in the
   future tense.
3. **Which production route is cheapest?** Answerable for ranking only, never
   as a forecast, because the figures it needs do not exist.

A fourth question, "will this decision work", is explicitly not in scope.
Counterfactuals need rates the game will not give us.

## 2. Formalism

A **directed hypergraph**, stored as ordinary SQLite tables following
`dfqueue`'s schema-plus-store pattern. No graph database, no graph library,
no new dependency.

A process is not an edge. Brewing consumes a plant *and* a barrel and yields
drink *and* a seed, firing together, once. A hyperedge expresses that; a
graph edge cannot. Two read-only queries run over the one stored structure:

- **AND-OR traversal** from a goal, for blocking. A node needs all of its
  process's reagents (AND); a node with several producing processes offers a
  choice (OR). This is the hypergraph read backwards, not a second model.
- **Min-cost flow**, later, for route pricing. A direct linear solve is
  sufficient: the static audit found **no cycle** in the extractable graph, so
  `scipy` is not needed. That conclusion is proven for raw-defined reactions
  only, and the hardcoded job types have not been enumerated (see §11).

DF's own vocabulary is used throughout, because our rows must stay joinable to
the files they came from: a **reaction** is a recipe, a **reagent** is an
ingredient, a **product** is an output. Not every job is a reaction; some are
hardcoded job types with no recipe text, hence `is_hardcoded`.

## 3. The rule that governs every figure

Four quadrants. This is the spine of the design, and the fourth rule is not
negotiable.

| | Contents | Rule |
|---|---|---|
| **Q1 static, known** | Stoichiometry, reagent lists, workshop and labour per reaction, growdur, seasons, densities, values, container classes | Free and exact. Do maximum arithmetic here |
| **Q2 static, measurable** | Job duration, true container capacity, hand-haul load, traffic weights | Constants *of this install*. One opportunistic measurement pays forever. Every row carries the worker's skill level or the figure rots |
| **Q3 dynamic, exact** | Stock, claims, queue depth, stockpile occupancy, labour flags, distances, tick | Cheap and exact. **Two snapshots make an exact rate** |
| **Q4 dynamic, inferential** | Happiness effect on work rate, interruption behaviour, time lost to needs, migration | **Never a formula term.** Detected as a residual, never modelled |

**The asymmetry everything leans on: demand is exact, supply capacity is not.**
Consumption is two stock reads and a subtraction. Production capacity needs job
durations, which are compiled into the binary. So pose every question from the
demand side.

**Q4 as a residual.** Build the expectation from Q1 and Q3, then report the gap
as "below expectation, cause unattributed". No fabricated term, and the
divergence is itself the alert. Attributing it is judgement, which makes it the
handoff point to an agent.

**Weak figures rank, they never forecast.** A shared bias cancels in a
comparison, not in a prediction. And before measuring any Q2 figure, test
whether the decision flips under it: if a route wins under the wiki figure and
under three times that figure, the figure is irrelevant and can stay unknown.
If the ranking flips, the tool reports "this depends on a figure we do not
have" rather than picking.

## 4. Schema

Seven tables. Every row carries `status` (`verified_raws` | `prior` |
`measured` | `unavailable`) and `source_ref` (the file:line or struct path
actually read). That pair is load-bearing: it lets a query degrade honestly,
and it *is* the quadrant taxonomy, since Q4 never gets a row.

```sql
-- Items, materials and buildings.
CREATE TABLE production_node (
  id            TEXT PRIMARY KEY,  -- item type × material, e.g. 'DRINK:PLUMP_HELMET_WINE'
  kind          TEXT NOT NULL,     -- plant | item_type | material | building
  display_name  TEXT NOT NULL,
  durability    TEXT,              -- durable | perishable; splits days of cover
  status        TEXT NOT NULL,
  source_ref    TEXT NOT NULL
);

-- Class membership. Reagents point at a class, products at a specific node.
CREATE TABLE production_class (
  node_id   TEXT NOT NULL REFERENCES production_node(id),
  class     TEXT NOT NULL,         -- DRINK, FOOD_STORAGE_CONTAINER, BREWABLE_PLANT
  mechanism TEXT NOT NULL,         -- reaction_class | material_reaction_product | hardcoded_flag
  source_ref TEXT NOT NULL
);

-- CORRECTED, and the reason extraction needs two passes. 42% of product lines
-- inherit their material from a reagent at job time
-- (GET_MATERIAL_FROM_REAGENT), including every food and drink reaction. The
-- concrete ids are not on the reaction line; they are on the material.
CREATE TABLE material_reaction_product (
  material_id  TEXT NOT NULL,      -- e.g. the plump helmet structural material
  token        TEXT NOT NULL,      -- e.g. 'DRINK_MAT', 'SEED_MAT', 'BAG_ITEM'
  result_node  TEXT NOT NULL,      -- the concrete node this yields
  token_family TEXT NOT NULL,      -- material_reaction_product | item_reaction_product
  source_ref   TEXT NOT NULL
);

-- One row per reaction, or per hardcoded job type.
CREATE TABLE production_process (
  id            TEXT PRIMARY KEY,  -- reaction code, e.g. 'BREW_DRINK_FROM_PLANT'
  workshop_node TEXT REFERENCES production_node(id),
  labor         TEXT,
  is_hardcoded  INTEGER NOT NULL DEFAULT 0,
  source_ref    TEXT NOT NULL
);
-- NOTE: capacity_theoretical was designed here and is DELIBERATELY ABSENT.
-- No job-time figure exists in the raws, in DFHack's docs, or on the wiki. A
-- column nothing can fill invites a guess.

-- The N-in, M-out edges.
CREATE TABLE production_flow (
  process_id   TEXT NOT NULL REFERENCES production_process(id),
  direction    TEXT NOT NULL,      -- reagent | product
  node_id      TEXT,               -- a class for reagents, a node for products; NULL if parametric before pass 2
  quantity     INTEGER,
  unit         TEXT,               -- units | stacks | volume
  unit_source  TEXT NOT NULL,      -- product_dimension | item_size_lookup | absent
  consumption  TEXT,               -- see §5; reagents only
  probability  INTEGER NOT NULL DEFAULT 100,
  container_class TEXT,
  status       TEXT NOT NULL,
  source_ref   TEXT NOT NULL
);

-- One row per fact, so a prior can be promoted without a migration.
CREATE TABLE production_attribute (
  subject_id TEXT NOT NULL,        -- a node or a process
  name       TEXT NOT NULL,        -- growdur | valid_seasons | capacity | density | value
  value      TEXT NOT NULL,
  unit       TEXT,
  status     TEXT NOT NULL,
  source_ref TEXT NOT NULL
);

-- The time series. Every rate in this design needs two of these rows.
CREATE TABLE production_observation (
  abs_tick    INTEGER NOT NULL,    -- CORRECTED: cur_year * 403200 + cur_year_tick
  subject_id  TEXT NOT NULL,       -- a node, process, workshop, stockpile, or 'fort'
  metric      TEXT NOT NULL,       -- stock | queue_depth | population | job_duration | tiles_occupied
  value       REAL NOT NULL,
  unit        TEXT,
  skill_level INTEGER,             -- REQUIRED for job_duration, or the figure rots
  status      TEXT NOT NULL,
  source_ref  TEXT NOT NULL
);
```

**Why `abs_tick` and not `tick`.** `dfhack.world.ReadCurrentTick()` returns
`cur_year_tick`, which resets each year. Uniboslan is at 227160 of 403200, so
next spring the same key recurs and every rate computed across the boundary is
garbage. Verified live.

**Three properties of the observations table that earn it:**

- Each row carries its own tick, so **irregular reads lose sample density but
  never correctness.** This demotes the still-missing scheduler from a
  precondition to an improvement. An `eventful` callback, by contrast, loses
  everything on a restart.
- Every read the agents already perform can append for free. The fort being
  inspected *is* the measurement. No measurement programme, and no work
  sampling, which the user ruled out deliberately.
- It is where opportunistic Q2 figures land, with the skill index.

## 5. Consumption: four outcomes, derivable

The first design had three. The raws express four. The derivation rule is
clean and had zero exceptions across 159 reactions and 314 reagent lines:

| Rule | Outcome | Example |
|---|---|---|
| No `PRESERVE_REAGENT` | `consumed` | the plant in brewing |
| `PRESERVE_REAGENT`, and the reagent's name is the target of a `PRODUCT_TO_CONTAINER` in the same block | `occupied_until_released` | the barrel in brewing |
| `PRESERVE_REAGENT`, name never a `PRODUCT_TO_CONTAINER` target, usually with `CONTAINS` | `occupied_job` | the tool in carpentry, the lye container in soap |
| `PRESERVE_REAGENT`, `NOT_IMPROVED`, and **no `PRODUCT` line at all** | `modified_in_place` | the four `GLAZE_*` reactions |

`EMPTY` and `CONTAINS` are match-time preconditions, not consumption signals:
they constrain which item qualifies, not what happens to it.
`DOES_NOT_DETERMINE_PRODUCT_AMOUNT` is a yield-scaling flag and unrelated.

**A documented assumption, not a fact.** The raws prove a barrel *becomes*
occupied. Nothing in any file states *when it is freed*. That it is freed when
the drink is drunk is engine behaviour. Anything built on
`occupied_until_released` inherits that assumption and must say so.

**Why the distinction matters at all:** reusable resources do not obey flow
conservation and cannot be priced as flows. They obey Little's Law, *units
busy = rate of use × time held*. Both terms are rates, which is why rates here
are measured and never read.

## 6. Extraction, in two passes

**Pass 1, parse.** Read the four shipped reaction files, the plant file, the
material files and the item files. Emit processes, flows, attributes and
classes. Flows whose product material is parametric
(`GET_MATERIAL_FROM_REAGENT`) are written with `node_id` NULL.

**Pass 2, materialise.** For each parametric flow, join the reagent's own
filter against `material_reaction_product` to enumerate the concrete nodes,
then expand one flow row into N. One brewing recipe becomes five drinks.

Materialise at extraction rather than at query time, because the design's
selling point is that "what are the routes to drink" is a plain join and not a
search, and the expansion is small at this fort's scale.

**Class membership comes from three unrelated token families**, not one:
`REACTION_CLASS`, `HAS_MATERIAL_REACTION_PRODUCT` matched against a material's
`MATERIAL_REACTION_PRODUCT`, and the hardcoded `ANY_PLANT_MATERIAL` /
`ANY_BONE_MATERIAL` flags. Record which mechanism a row came from.

**One unresolved inconsistency, do not paper over it.**
`PROCESS_PLANT_TO_BAG` filters on `HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM`,
while quarry bush declares `ITEM_REACTION_PRODUCT:BAG_ITEM`, a different token
family with the same name. An extractor looking only for
`MATERIAL_REACTION_PRODUCT` silently drops that class. Hence `token_family` on
the join table. Whether the engine matches across families could not be
settled from text files.

## 7. The live layer, and where space lives

Static truth is **placeless**. The raws have no concept of location, so the
extracted tables must not either. Location lives entirely in the live layer,
joined at query time and never stored:

- **Sites** are discovered, not extracted. A first-version site is a coarse
  area of the fort, not an individual stockpile. Per-stockpile is deferred
  until coarse areas prove too blunt.
- **Three process kinds are generated at query time**: *moving* something
  between sites, *installing* an item as a building, and *trading* with a
  caravan that is actually present, priced from its real goods. None is
  extracted, and trade therefore needs no seasonal special case.

**Installation is a process** (item plus labour in, building out). A bed is an
item until installed, then it is a building. Par levels apply to the
**installed** count while flows produce the item. Miss this and the fort has
fifteen beds in a stockpile, dwarves on the floor, and every stock query
reporting it well supplied.

**Available stock is never total stock.** Four deductions, all exact:

| Deduction | Read |
|---|---|
| claimed by a pending job | `item.flags.in_job` (a plain flag, no job scan needed) |
| owned by a dwarf | `item.flags.owned` plus the `UNIT_HOLDER` ref |
| forbidden | `item.flags.forbid` (**not** `forbidden`) |
| caravan-owned | `flags.trader`, already implemented in `df-overseer-stocks.lua` |

An item moved to a trade depot for sale is a fifth case and is **unverified**,
because Uniboslan has never had a depot.

## 8. Logistics without a time model

Hand-haul load per trip is the one figure no source states. Four ways not to
need it:

1. **Design it out.** The strongest logistics fact is adjacency, not distance.
   A stockpile next to the workshop drives the hauling term to roughly zero,
   and then unit-based planning is valid because the thing it ignores no
   longer exists.
2. **Bound trips, do not estimate them.** Item count is exact and the worst
   case is one item per trip, so "at worst 40 trips over 22 tiles" contains no
   unknown. Not knowing the tiers makes the bound loose, never wrong. An upper
   bound decides whenever the worst case is acceptable.
3. **Minimise distance, not time.** Distance between landmarks is an exact
   read with existing precedent (`landmark.exit.distance_tiles`).
4. **Detect starvation rather than predict it.** If every dwarf with a labour
   enabled is carrying things, hauling is the bottleneck, observed.

**Days of cover is immune to all of this**, because it measures consumption
where consumption happens. Drink that exists but never reaches anyone shows up
as cover falling regardless. The top-level number does not care whether the
failure was production or transport; attribution comes from the ladder.

**Haul tiers**, as they stand:

| Tier | Load | Status |
|---|---|---|
| Bare hands | one item or stack; Strength-driven, and over capacity a dwarf slows but never stops | **not found** |
| With a bin | 12 bars or blocks, 400 bolts, 45 leather, 305 small gems | `prior` |
| With a barrel | 60 meals, 30 meat, 100 lye or milk | `prior` |
| Wheelbarrow | `SIZE` and `CONTAINER_CAPACITY` read from this install's `item_tool.txt`, matching the wiki digit-for-digit | **`verified_raws`** |
| Minecart | same | **`verified_raws`** |

**Traffic** costs 1 / 2 / 5 / 25 per tile for high / normal / low /
restricted, corroborated across both wiki namespaces, readable per tile via
`dfhack.maps.getTileFlags(pos).traffic`. Two caveats, both load-bearing: these
are **configurable defaults**, so the schema holds them as a configurable
default and prefers a live read of the fort's own settings; and traffic shapes
hauling routes but **does not stop a dwarf entering a restricted tile to do an
assigned job**, so it is a hauling input, not access control.

**Stockpile occupancy** is one of the few *leading* indicators in the design:
a stockpile at 80% and rising predicts a backed-up workshop before it happens.
Report **occupied tiles over total tiles**, not percentage of capacity,
because per-tile capacity depends on containers and that figure is not
established. Appended to the observations table, so the trend is free.

## 9. Diagnosis: capacity shortage is the last rung

A blocker is a zero; a bottleneck is a slowest link. We find the first
properly, detect the second, and predict neither.

**Blocking** is the AND-OR walk from a goal: the first node with zero
available stock and no completable process, named, with the quantity short.
Never a coordinate.

**A growing queue** proves insufficient capacity without any knowledge of
service time, but it has six causes and only one is capacity. Building a
workshop is the most expensive fix and the rarest cause, so it sits at the
bottom. Every rung is an exact Q3 read:

1. **Reagents available?** No → material shortage, hand to the blocker walk.
2. **Reachable and linked?** No → misconfigured stockpile link, or no route.
3. **Output has a destination?** No → output backed up.
4. **Job claimed?** No → who holds the labour, and what are they doing now?
   - nobody has it enabled → one-line fix
   - on a need, asleep or eating → transient, **do nothing**
   - hauling → reprioritise, do not build
   - another job, or squad duty → competing priorities
5. **Claimed, running, still falling behind** → genuine capacity shortage.

Suspended jobs exit at rung 1. It is a fault tree, so it belongs entirely in
code, returning a named cause plus its evidence.
`df-overseer-stuckjobs.lua` already implements part of it.

**Cancellation announcements are a lossy hint, not a shortcut.** DF does name
the reason ("Need empty bucket"), but every linkage field is unset
(`speaker_id = -1`, `activity_id = -1`), so it cannot be joined to a job or a
unit, only parsed as text. And the buffer is **pruned**: 12 entries survived
out of ids running to 104. An infrequent reader misses cancellations
permanently. A cancelled job itself leaves nothing: it is removed from the
queue entirely.

## 10. Material policy: bands, held in doctrine

An LP is only optimal with respect to an objective, and minimising dwarf-time
versus barrels versus seeds gives different answers from identical data. A
weight vector is unreviewable; **targets are**. So the objective is replaced by
bands on one quantity axis, and they live in `doctrine/seed.yaml` with normal
provenance, never in code.

| Band | Policy |
|---|---|
| below **reserve floor** | hard stop, overrides even survival |
| floor to **par** | keep on hand, produce toward it; par may be per-capita |
| par to **cover target** | working stock, in days for consumed goods |
| above par | **surplus**: doctrine says discretionary value, or liability |

**Class is a property of intended use, not of the item.** Stone below the
block reserve is a valuable intermediate; the same stone above it is clutter
occupying tiles that drink needs. Which is why bands beat categories, and why
the grey areas are a threshold question rather than a category argument.

Seven policy shapes emerge from which fields an entry sets:

| Shape | Target | Reviewable |
|---|---|---|
| Irreplaceable reserve (seeds, breeding pairs) | hard floor | never, the point is that nothing happens |
| Consumed (food, drink) | days of cover, per dwarf | days |
| Keep on hand (blocks, ingots, beds) | a level, per capita | weeks |
| Insurance (weapons, soap, buckets, coffins) | a level against a threat model | only after an event, so on decision quality |
| Capital (well, bridge, stair) | coverage and reachability | once, on whether it got used |
| Discretionary (crafts, trade goods) | none; residual capacity only | on value realised |
| Liability (rock, refuse, worn clothing) | dispose | on hauling load |

**Bands are lexicographic, not weighted**, so the cost vector disappears for
every cross-class decision.

**Derived demand gets no cover target.** Dwarves drink regardless of your
plans; charcoal is needed only if you are smelting, so it is netted from the
plan instead. Give a derived good a cover target and the fort stockpiles fuel
for a furnace nobody built. That netting is the half of MRP worth borrowing.

**Reservation, not priority, is the enforcement.** Available for discretionary
work equals stock minus reserve floor, minus par, minus consumption
commitment, minus job-claimed.

**The mechanical test for capital versus stock:** if it can sit in a
stockpile it is stock; if it is built in place it is capital.

## 11. Time

**Calendar time** gates: planting windows, caravan arrival, which season it
is. `df.global.cur_season` is exact. **Elapsed time** measures growth,
spoilage, residency and queue growth.

Conversions, confirmed live against announcement timestamps: **1,200 ticks a
day, 33,600 a month, 403,200 a year.**

**Harvest arrival is exact arithmetic** and is the most valuable single output
here: `GROWDUR` from raws plus the plant's own `grow_counter`, which exists on
live plant instances and is a better anchor than catching a `PlantSeeds` job
completion, because it works even if nobody was watching. Its exact direction
and post-maturity behaviour are **unconfirmed**, since nothing is planted on
Uniboslan to observe. Confirm before relying on it.

That yields a sentence with no estimate anywhere in it: *drink cover is 9
days; a plump helmet crop needs 11 days to grow before it can even be brewed;
planting no longer fixes this.*

**Spoilage without a decay constant.** Classify durability (Q1) and use the
rot flags `df-overseer-stocks.lua` already reports as the live check. Cover
then splits into durable (barrelled drink, prepared meals) and perishable
(raw edibles, especially outside). "Eleven days of cover, of which three are
raw edibles already flagged rotten" is more honest than any single number, and
every term is exact.

## 12. Water, which no reaction produces

Water has no reaction, so a raws-derived graph will never contain it. It is a
**source node**, an external input, the same shape the audit found for lye and
potash.

For an able dwarf the chain is solved: the `WaterSource` zone got the founders
drinking. For an **immobile** dwarf it is a different chain and the first
design had no representation of it at all: a bucket that exists and is neither
forbidden nor claimed, a dwarf with the water-carrying labour enabled, and a
reachable source.

- **A triggered check, not a standing query.** Whenever any citizen reads
  unconscious or hospitalised, run that three-link walk. It is the blocker
  walk with a fixed goal, so it needs no new machinery.
- **Doctrine, as insurance:** buckets on hand with a par level, and the labour
  enabled on more than one dwarf, permanently.
- **Placement: near the route, not at the water.** Uniboslan's ponds sit one
  level below the surface and are likely open to the sky, so a bucket at the
  waterside is exposed to theft by wildlife. A store inside the secured area on
  the way down gives the same travel saving without the exposure.
- **The other theft is internal**: another job claims the bucket. DF's own
  answer is the hospital zone, which reserves its own supplies. That mechanism
  is `prior` and needs verification. What is certain is that we can now
  *detect* it, since `item.flags.in_job` came back exact.

**This gap was found by accident, and then my own reading of it was wrong.**
Corrected by a live read at tick 227160, fort paused:

- **The fort owns three usable buckets** (ids 81, 149, 150: empty, not
  forbidden, not claimed, no holder). Two more are `trader=true`, held by the
  caravan's yak pack animals. The earlier "owns no bucket" claim came from an
  illustrative figure in a diagram, not from a read.
- **The "unconscious citizen" is a sleeping miner**: `unconscious=2`,
  `pain=0`, `wounds=0`, `current_job=Sleep`. No injury, no medical emergency.
  The live audit's count was accurate; the inference drawn from it was not.

**What survives, and is more interesting than the version I got wrong:** the
fort held three empty buckets and still logged "Give water: Need empty bucket"
(announcement 104, tick 214135). So that failure was **availability or
reachability at that moment, not absence**, which is precisely the
available-versus-total distinction in §7, demonstrated live before the code to
detect it exists. The water chain still needs representing, and buckets still
deserve an insurance par level, because existence is not availability.

The lever gap is also real independently: `orders.create` knows blocks,
mechanisms, barrels and brew_drink only, so no tool can make a bucket.

**Method note, recorded because it is the design's own rule broken by its own
author:** two true facts (a cancellation message, a nonzero unconscious count)
were combined into a false conclusion without a read. The design says detect,
do not infer, and treat a residual as unattributed rather than explained. That
applies to whoever writes the reports, not only to the code.

## 13. Levers: what the fort can actually change

The ladder names what is wrong. It does not say what can be done about it, and
until this table existed nobody had checked that a tool exists for each fix.

| Diagnosis | Lever | Tool | Exists? |
|---|---|---|---|
| Material shortage | produce it | `orders.create`, `workshop.build`, `farm.*` | **yes** |
| Not reachable, or hidden | dig or connect | `diggable.dig`, `dig-stair`, `openarea.build` | **yes** |
| No labourer enabled | labour flag | `labor.set-labor` | **yes**, fort-wide side effect |
| Capacity shortage | build another workshop | `workshop.build` | **yes** |
| Stockpile link misconfigured | set take-from / give-to | — | **no** |
| Output backed up | new stockpile, or disposal | partial | **no** |
| Labourer busy hauling | job priority, or a burrow | — | **no** |
| Squad duty conflict | military schedule | — | **no** |
| Stockpile full | expand or dispose | — | **no** |
| Water to an immobile dwarf | make a bucket | `orders.create` lacks the job | **no** |

**Four actionable, six not.** The majority of diagnoses this design can
produce are ones nobody can act on. That is the sharper form of "nothing
executes", and it reorders the work: two small tool builds convert two dead
diagnoses into live ones, and they are worth more than the solver.

## 14. Build order

1. **Tools that close the worst lever gaps**: a bucket job on
   `orders.create`, and a stockpile read (occupancy and links).
2. **Doctrine entries** for the bands agreed in §10 and §12.
3. **Extraction and the schema**, offline, no fort needed.
4. **The blocker walk**, joined against existing live reads.
5. **Days of cover**, durable and perishable, against harvest lead time.
6. **The diagnostic ladder**, reusing `stuckjobs` where it already overlaps.
7. **Route listing and pricing**, with a sensitivity flag.
8. The solver, if sensitivity ever shows it is needed.

Steps 3 to 5 need no scheduler and no live fort. Step 1 is the only one with a
live medical reason to happen first.

## 15. Parked, with triggers

| Parked | Why it is safe to park | Trigger to revisit |
|---|---|---|
| Rooms, and room-dependent furniture | a layer above installation | when bedrooms or a dining room are built |
| Quality levels | breaks only discretionary value ranking | when crafts are produced for trade |
| Wear and clothing | takes ~2 years to bite; this fort is in year 1 | the first tattered item, or year 2 |
| Animals | demand is measured anyway, and breeding pairs inherit the reserve band automatically | the fort's first livestock |
| Migration headroom | Q4, must not enter a formula | never as code; a stated margin in doctrine |
| Trade | a transient hyperedge, generated when a caravan is present | a caravan arriving |
| Per-stockpile sites | coarse areas are enough to see the gap | when coarse areas prove too blunt |
| The solver, and the integer question | no cycle exists, so a direct solve suffices; rail-versus-wheelbarrow is the only true integer decision | when sensitivity shows a ranking flips |
| Pareto frontiers instead of collapsed objectives | not hard: a dozen LP solves with one objective held at successive levels gives the frontier, and it needs no weights and no priority order. Premature for a different reason: **a frontier is only meaningful if its axes are trustworthy**, and our cost axes are exactly the ones the figures pass could not fill. A frontier over guessed axes is precision theatre | when the cost axes are measured rather than guessed. Then it composes with the bands: lexicographic where the ordering is not negotiable (a seed floor is not a tradeoff), a frontier only inside the discretionary band |
| Utility bundles | dwarves do not value goods independently: variety matters and satiation is real (enough beds is enough), which is *why* bands exist rather than a single "maximise value". But preference structure is Q4, so it can never be a formula term. It enters as a **constraint** (at least three distinct drinks, one bed per dwarf), the same move used for spoilage and diversity | as constraints, whenever a specific bundle effect is worth naming |
| Differentiation through the graph | already present twice, so there is nothing to build: an LP's **dual values are exact derivatives** (the shadow price on a resource *is* the objective's gradient with respect to it), and because the calculators are deterministic, **finite differences** answer the same marginal question with no solver at all. What backprop proper would need is a differentiable model of the fort with known parameters, and DF is neither | the genuinely backprop-shaped problem in this project is **credit assignment over time**, which belongs to the retrospective court, not to production |

## 16. Constraints the build must honour

- **No coordinates leave a tool, ever.** Sites are named, distances are
  scalars, a blocker report names a landmark.
- **The site layer is not a map.** Named boxes in arbitrary positions is fine;
  arranging them to reflect fort geography is a rendered map, which is the one
  commitment this project does not bend. Easy to do by accident when drawing a
  transport layer.
- **Status stays visible in every view.** A route priced from raw data and one
  priced from a wiki guess must not look alike.
- **Consumption semantics stay visible.** Otherwise the picture lies about
  barrels.
- **Rates are measured, never read.** The cheap sanity check is jobs completed
  per able dwarf per season against what the model predicted: it will not give
  per-job costs, but it will catch being wrong by 5x.
- **Targets live in doctrine, not in code.** A number buried in a constant
  cannot be argued with.

## 17. Known unknowns carried into the build

- `grow_counter`'s direction and post-maturity behaviour (nothing planted to
  watch).
- Whether `item.age` survives a year boundary (this fort has never crossed
  one).
- The release trigger for `occupied_until_released` (engine behaviour, never
  raw-stated).
- The `BAG_ITEM` token-family inconsistency.
- ~~The hardcoded job types have not been enumerated.~~ **Settled 2026-09-18
  by a live enum read.** The ashery chain is hardcoded, not absent:
  `MakeAsh` (185), `MakeLye` (186), `MakePotashFromLye` (187),
  `MakePotashFromAsh` (189), alongside the already-known milling family
  `MillPlants` (106), `ProcessPlants` (110), `ProcessPlantsVial` (112),
  `ProcessPlantsBarrel` (113). So the static audit's finding that lye and
  potash are raw-external is correct **about the reaction files** and would be
  a modelling error if read as "the fort cannot make lye". These need
  `production_process` rows with `is_hardcoded = 1`.
  **The no-cycles conclusion is not yet fully settled.** Reasoning over the
  chain, wood feeds ash, ash feeds lye and potash, lye feeds soap, and potash
  is fertiliser, none of which returns to wood, so there is no loop. But that
  is reasoning, not extraction. The definitive check belongs to the extractor
  once hardcoded processes are rows, which is why the build order keeps the
  cycle question as an output of extraction rather than an assumption.
- Whether an item moved to a trade depot is distinguishable (no depot exists).
- Hospital zone supply reservation.
- The workshop task cap reads 5 on this install, not the wiki's 10, from one
  incomplete sample.
