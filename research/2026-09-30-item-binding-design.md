# How jobs bind materials: claims without double-promising

Date: 2026-09-30. Researcher (Opus), design only: no code changes, no live
access, no VM touched. Brief: `handoffs/2026-09-30-item-binding-design.md`.
Answers red-team finding F-4 (`research/2026-09-30-goal-tree-red-team.md`)
on the goal-tree design's claims model (`research/2026-09-30-goal-tree-design.md`
§8).

Sections: 0 answer; 1 what control exists (verified); 2 the no-armok
question; 3 the claims design; 4 who chooses what; 5 live test plan (not
run); 6 decisions for the user; 7 not verified; 8 sources.

Confidence labels per claim: **[verified: source]** read in code at a named
ref; **[verified: primary doc]** read in DFHack's or the DF wiki's own
text; **[repo record]** from this repo's records, not re-checked live;
**[reasoned]** inference from verified pieces; **[unverified]** could not
confirm, repeated in §7.

Sources were read at their tags, downloaded fresh for this pass: DFHack
`53.16-r1` (whole repository), DFHack/scripts `53.16-r1` (whole
repository), df-structures `53.16-r1` (`df.job.xml`, `df.d_basics.xml`,
`df.building.xml`, `df.workquota.xml`, `df.item.xml`), and DF wiki raw
wikitext (current: Workshop, Forbid, Strange mood, Work orders, Building,
Construction).

---

## 0. The answer, up front

**Neither the first fix nor the alternative is needed in its shaky form.
Claims stop double-promising with two changes that need no new ruling:
count the unbound demand of every live job, ours and foreign, read from
the live job each cycle, before granting anything new; and narrow every
job we issue to a single pool (one item type and material), which is the
vanilla details-button power, so that whichever item DF picks, the count
stays true.** Recompute-never-tally survives intact: every number comes
from one snapshot read per cycle.

What the sources show:

1. **DF binds items at two different moments.** A building or
   construction placed through the vanilla menu gets its items at
   placement, and the vanilla menu offers **specific items** to choose from
   [verified: source, df-structures `build_req_choice_specst`]. A workshop
   job gets its items only when a dwarf takes it, the nearest to that
   dwarf [verified: primary doc, DF wiki Workshop]. `buildingplan` (on this
   fort) attaches the closest screened item to planned buildings every 599
   ticks or on request [verified: source].
2. **Material choice exists at every level** (job filter, job, manager
   order) [verified: source]; **exact items** exist only for jobs, through
   `attachJobItem`, which does not touch the filter's `quantity`. DFHack
   ships one tool that pre-attaches a reagent to a workshop job,
   `autocheese`, tagged `fort auto`, but it also assigns the worker in the
   same call. **Nothing in DFHack attaches a reagent and leaves DF to pick
   the worker**, so whether DF honours that is unverified and needs a live
   test.
3. **This repo's tools control less than their docs say.** `workjob.queue`
   takes no material; `building.build`'s "exclude economic material by
   default" is advisory only, because the generated blueprint carries no
   material and `buildingplan` picks the closest item. The header claims
   otherwise; `construction.lua` and the code agree it is advisory. A
   memory-audit item.
4. **The armok question splits.** For buildings, exact items are the
   vanilla action; I propose it as allowed. For workshop jobs it is a real
   question: the dwarf still does the work, and a player can force the
   item by forbidding the rest or linking a stockpile, but pre-attaching
   also **reserves an item indefinitely for a task no dwarf has started**,
   which vanilla cannot do without side costs. Four options (materials
   only; exact at issue; exact with dispatch; forbid-based holds) are set
   out for the user in §2.3.
5. **A model chooses at most the material or class; code chooses pools
   and exact items**, maximising slack, then uniformity, then shortest
   haul, and never picking economic material without a ruled authority,
   hidden or unreachable items, or anything a human set aside (§4).
6. **Uncoverable**, by any design: the moment of decision of the
   Overseer's direct actions and of a human (until the DF job exists),
   moods (which ignore economic settings and forbidding), and DF's own
   consumption by eating, drinking and planting (§3.5).
7. **Nine live tests** (§5) settle the rest; T1 (DF's own binding
   convention) is needed whatever the user rules, and T2 and T3 decide
   whether exact items for workshop jobs are buildable at all.

---

## 1. What control exists, verified from source

### 1.1 The three moments at which DF binds an item to a job

An item is bound to a job when a `job_item_ref {item, role, flags,
job_item_idx}` sits in `job.items` and the item carries a `specific_ref`
of type `JOB` back to it; binding sets `item.flags.in_job` for every role
except `TargetContainer` [verified: source, `Job::attachJobItem`,
`library/modules/Job.cpp` 602-637, commented "Functionality 100%
reverse-engineered from DF code"]. The job's **filters** are a separate
vector, `job.job_items.elements` (`job_item`, DF's `job_req_elementst`),
each with a `quantity` [verified: source, `df.job.xml` 6-43, 1755-1760].
So a job can hold filters and no items, items and no filters, or both.

| Kind of job | When items bind | Who chooses the item | Evidence |
|---|---|---|---|
| **Placed building or construction, vanilla UI** | **at placement**, before any dwarf is involved | the player, from a list that offers both grouped choices and **specific items** | df-structures `buildreq`: `build_req_choice_genst` (item type plus material, a `candidates` vector, `expandable`) and `build_req_choice_specst` (one `candidate` item pointer), each with a `distance`; `ui_build_item_req.candidates` and `candidate_selected` [verified: source, `df.building.xml` 2832-2947]. DFHack's `constructBuilding{items=...}` "replicates programmatically what can be done through the construct building menu in the game ui" [verified: primary doc, `Lua API.rst` 2752-2799]; `constructWithItems` attaches each item `Hauled` at creation [verified: source, `Buildings.cpp` 1170-1207], and `constructWithFilters` notes the game picks up "explicitly listed items" as "the normal ui way" [verified: source, `Buildings.cpp` 1209-1255] |
| **Placed building, through `buildingplan`** (this fort's route: `building.build`, `construction.build`, `blueprint.apply` all go through `quickfort`, which registers plannable buildings with `buildingplan`) | on `buildingplan`'s cycle: every 599 ticks, or on the next update after `scheduleCycle` (quickfort calls it after every run) | `buildingplan`: the **closest** screened item by Chebyshev-plus-z distance to the job site, FIFO per filter bucket | `CYCLE_TICKS = 599`, `plugin_onupdate` [verified: source, `buildingplan.cpp` 72, 336-352]; `quickfort` `build.lua` 1302-1310 and 1352-1353 [verified: source]; `doVector` [verified: source, `buildingplan_cycle.cpp`] |
| **Workshop job** (queued by `workjob.queue`, the vanilla "Add new task", or a manager order's spawned job) | when a dwarf takes the job, one item at a time as they are gathered | the **dwarf**: "the nearest, most suitable base raw material ... nearest to their current location, not the workshop"; "if any stockpiles are set to give to the workshop, only linked stockpiles will be looked in" | [verified: primary doc, DF wiki Workshop, "Operation"]; `job_flags.fetching` "Actually going out to bring; corresponds to items->is_fetching", `bringing` "When actually carrying non-last item to the workshop" [verified: source, `df.job.xml` 1461-1476]. That the whole reagent set is **not** bound at worker assignment but one by one is [reasoned] from those two flag comments and the wiki's "repeats that until all the necessary ingredients are in the workshop"; not observed live |
| **Designation jobs** (dig, chop, gather) and **hauling** | no material input to bind; hauling jobs bind the one hauled item | DF | outside this question except §3.5 |

What `buildingplan` screens out before attaching [verified: source,
`buildingplan_cycle.cpp` `BadFlags` and `itemPassesScreen`]: `dump`,
`forbid`, `garbage_collect`, `hostile`, `on_fire`, `rotten`, `trader`,
`in_building`, `construction`, `in_job`, `owned`, `removed`, `encased`,
`spider_web`; items assigned to a stockpile task; items not in a
walkability group containing any citizen; unusable bars; items in a
wheelbarrow; items in the `buildingplan ignore` burrow. **It does not test
tile visibility**, so nothing in that screen keeps an item on a hidden but
connected tile out [reasoned from the code; whether such an item can pass
the walkability test on this fort is unverified]. It does not know the
repo's "economic" rule either (§1.2).

Two conventions for `job_item.quantity` exist, and they differ:

- **`buildingplan` decrements it** as it attaches each item, so on a
  planned building `quantity` reads "items still to find"; the job is
  "ready" when every filter's `quantity` is 0, and only then is it
  unsuspended [verified: source, `buildingplan_cycle.cpp`
  `--jitems[filter_idx]->quantity`, `isJobReady`, `finalizeBuilding`].
  `registerPlannedBuilding` finalizes at once if every quantity is already
  0, i.e. if all items were attached at creation [verified: source,
  `buildingplan.cpp` 457-477].
- **DFHack's workshop-job viewer counts attached items against an
  undecremented `quantity`** ("Item 1: *n* of *quantity*", counting
  `job.items` by `job_item_idx`) [verified: source, scripts
  `gui/workshop-job.lua` 170-180]. Which convention DF's own workshop-job
  code uses when a dwarf binds a reagent is [unverified]; it decides how a
  pre-attached item must be declared (§1.3).

### 1.2 Level one: material choice

**The fields exist at every level** [verified: source]:

- a job filter (`job_item`): `item_type`, `item_subtype`, `mat_type`,
  `mat_index`, three flag words, and a separate `job_details_mat_type`,
  `job_details_mat_index`, `job_details_item_flags2` with a
  `have_set_job_details` flag (since v0.43.01) [`df.job.xml` 6-38]. The
  flag words carry the classes a player picks by name: `flags3.wood`,
  `flags3.stone`, `flags3.metal`, `flags2.bone`, and **`flags2.non_economic`,
  whose DF name is `WORTHLESS_STONE_ONLY`** [`df.d_basics.xml`
  2800-2922];
- the job itself: `mat_type`, `mat_index`, and a `material_category`
  bitfield (`wood`, `bone`, `shell`, `horn`, `pearl`, `tooth`, `silk`,
  `yarn`, `strand`, `soap`, `cloth`, `plant`) [`df.job.xml` 1740-1747,
  `df.d_basics.xml` 2922-2937];
- a manager order: `mat_type`, `mat_index`, `material_category`, and a
  pointer to its own `job_reqst` (per-order filters) [`df.workquota.xml`
  `manager_order`]. **A manager order has no field for an item**; its
  finest control is material.

**The vanilla actions** [verified: primary doc, DF wiki Workshop]: a
queued workshop task has a details button that "allows you to specify
certain details of the task, such as choosing the material(s) to be used";
a workshop's Workers tab and stockpile links restrict who works and where
items may come from. Which `job_item` fields the details button writes
(`mat_type` directly, or the `job_details_*` shadow fields) is
[unverified]. DFHack's own editor writes `mat_type`/`mat_index` on the
filter and warns that a material without an item type "will be matched
incorrectly in some cases" [verified: source, scripts
`gui/workshop-job.lua` header and `onChangeMat`; that tool is from the v0.47
era and its v50 status was not checked].

**What this repo's tools set today** [verified: source]:

- `workjob.queue` copies each filter from `workshops.getJobs` field for
  field and exposes **no material argument**. Its `REAGENT_CHOICE` resolves
  a wildcard reagent, and even then pins only `item_type`/`item_subtype`
  of the chosen item; its own diagnostic says so: "item_type/subtype only;
  the game picks which matching item, so the instance may differ"
  (`df-overseer-workjob.lua` 636-660).
- `building.build`'s `MATERIAL_CHOICE` is **advisory only**. The header
  says the tool "DEFAULTS to excluding economic materials from the
  material it would actually build with" (lines 98-110), but
  `blueprint_text` writes only the kind's key into each cell (lines
  1061-1069), no material reaches `quickfort`, and nothing calls
  `buildingplan`'s `setMaterialFilter`. `df-overseer-construction.lua`
  says the opposite of the building header, correctly: quickfort and
  buildingplan make "the real choice at build time, this is advisory only"
  (lines 61-73, 477). **The docs disagree and the code sides with
  construction.lua**: the 2026-09-28 hematite-workshop fix reports a
  preferred material but does not enforce it. Flagged for a memory audit,
  not patched here.
- `quickfort`'s `#build` mode at `53.16-r1` has no per-cell material
  syntax; material restriction for a planned building comes only from
  `buildingplan`'s per-building-type filters (`setMaterialFilter`,
  persisted per fort, global to that building type) [verified: source,
  scripts `internal/quickfort/build.lua`, `buildingplan.cpp` 900-960,
  `itemfilter.cpp`].

### 1.3 Level two: exact items attached at creation

**The API** [verified: source and primary doc]:
`dfhack.job.attachJobItem(job, item, role, filter_idx, insert_idx)`
refuses (returns false) if the item is already `in_job` (except for role
`TargetContainer`), else sets `in_job`, adds the item's `JOB` ref and the
job's `job_item_ref` [`Job.cpp` 602-637; `Lua API.rst` 1421-1428: "If the
item needs to be brought to the job site, then the value should be
`df.job_role_type.Hauled`"]. It does **not** change the filter's
`quantity`; callers that want DF to stop searching decrement it themselves
(`buildingplan`) or set it to 0 (`autocheese`).

**Who uses it on which job kind, in DFHack itself** [verified: source,
a whole-tree search of both repositories at `53.16-r1`]:

| Caller | Job | Role | Also | DFHack tags |
|---|---|---|---|---|
| `Buildings::constructWithItems` | `ConstructBuilding` | `Hauled` | the vanilla UI's equivalent | library |
| `buildingplan` | `ConstructBuilding` | `Hauled`, `filter_idx` set | decrements `quantity`, keeps the job suspended until all attached | `fort design productivity buildings` |
| **`autocheese`** | **`MakeCheese` at a Farmer's Workshop: a workshop job** | **`Reagent`, `filter_idx` 0** | sets the filter's `quantity = 0`, then **assigns a worker itself** (`addWorker`, `setPathGoal ... GrabJobResources`, `is_fetching`, `job.flags.fetching`) | `fort auto` |
| `Items::markForTrade`, `stocks` | `BringItemToDepot` | `Hauled` | the vanilla "mark for trade" equivalent | library |
| `entomb`, `store-owned` | `PlaceItemInTomb`, store owned item | `Hauled` | | `fort items buildings` |
| `immortal-cravings` | eat/drink | `Other` | | `fort gameplay` |
| `tweak animaltrap-reuse` | trap | `Hauled` | | |

So **pre-attaching an exact reagent to a workshop job is something DFHack
itself ships, untagged `armok`** (`autocheese`, run on a schedule by
`gui/control-panel`). But `autocheese` also takes the worker choice away
from DF: it creates, attaches, assigns and dispatches in one call. **No
DFHack code at this tag attaches a reagent to a workshop job and then
leaves the job for DF to give to a worker of its own choosing.** Whether DF
honours a pre-attached reagent in that case (fetches it, does not add a
second item for the same filter, does not cancel) is therefore
**[unverified]**, and it is the single most important thing the live test
(§5, T2 and T3) must settle.

**What happens when an attached item goes wrong**:

| Event | What DF does | Confidence |
|---|---|---|
| the item is destroyed or removed | job flag `item_lost`: "set when a Hauled item is removed; causes cancel" | [verified: source, `df.job.xml` 1475]; for role `Reagent` the comment does not say [unverified] |
| the item is forbidden | "Forbidding an item hauled by a dwarf will cause him to drop it once he realizes it is forbidden"; "Forbidding materials clears any in-process hauling jobs"; a moody dwarf whose tasked item is forbidden "will immediately switch to" another | [verified: primary doc, DF wiki Forbid, Strange mood]; whether a forbidden **pre-attached, not yet fetched** item is dropped from the job, cancels it, or blocks it is [unverified] |
| another job wants the item | cannot bind it: `attachJobItem` refuses an `in_job` item, `buildingplan` skips `in_job`, the repo's netting excludes `in_job` | [verified: source] for DFHack paths; that **DF's own** item search skips `in_job` items is [reasoned], it is the flag's whole purpose, and is tested in §5 T4 |
| the item becomes unreachable | DF has a `killjob_exception_type` `CANNOT_REACH_SITE` and job cancellation messages for unreachable items; which one fires for an unreachable attached reagent, and whether the job is cancelled or the item released and re-searched, is not in source | [unverified] |
| the job is cancelled (by DF, a player, or `workjob.cancel`) | `removeJob` disconnects every item and clears `in_job` if no other job refers to it | [verified: source, `Job.cpp` 346-419]; that DF's own cancellation path does the same is [reasoned] |
| a building's plan waits for items | the job stays suspended; the `buildingplan` overlay shows attached and pending items and each pending item's queue position | [verified: primary doc, `buildingplan.rst` "Building status"; source `getQueuePosition`] |

### 1.4 Level three: counting demand until the game binds

Everything needed to count **unbound demand exactly** is readable
[verified: source, the fields above; live reads of `job.items` and
`in_job` exist, `research/2026-09-18-schema-extraction-live.md` §1]:

- **a workshop job's unbound demand** = for each filter *i*,
  `quantity_i` minus the number of `job.items` whose `job_item_idx == i`
  (the `gui/workshop-job` convention), floored at 0. If the live test shows
  DF decrements `quantity` on binding (the `buildingplan` convention), the
  formula becomes `quantity_i` alone; either way it is one read per job.
- **a planned building's unbound demand** = the sum of its filters'
  `quantity` (buildingplan decrements), read from `bld.jobs[0]`.
- **a manager order's unbound demand** = `amount_left` times the
  per-job filter quantities, minus whatever its already spawned jobs hold;
  the spawned jobs carry `order_id` and the `by_manager` flag [verified:
  source, `df.job.xml` 1772, 1477].

The ambiguity F-4 found is not in the reading; it is in **which class of
item a filter will take**. A filter is not an item class: `MakeBarrel`
wants a log of any wood, a bed wants a log of any wood too, a
`building_material` filter takes a boulder, a block **or** a log. Counting
demand therefore double-counts or under-counts whenever one item could
satisfy two different filters, which is exactly the barrel-versus-bed
case. §3 handles that by matching items to filters, not classes to
classes.

---

## 2. The no-armok question, for the user's ruling

The rule (`CLAUDE.md`): banned are powers a player does not have (heal,
teleport, spawn, skip costs, alter the world) and information the game
hides. The rulings table (`docs/ARMOK-RULINGS.md`) applies one test
repeatedly: **does the tool produce a game state some vanilla action
produces, with a dwarf doing the work?** `lever pull --priority` is
allowed because it sets the flag the vanilla priority button sets; `lever
pull --instant` is banned because no dwarf pulls; `geld` is banned because
it writes the gelded state directly instead of the vanilla designation a
dwarf then performs.

The question splits in two, because the vanilla game treats the two job
kinds differently (§1.1).

### 2.1 Buildings and constructions: the vanilla action already chooses items

The vanilla build menu offers **specific items** as choices, each with its
distance, and attaches the chosen items to the construction job at
placement [verified: source, df-structures `build_req_choice_specst`,
`ui_build_item_req.candidates`; DFHack's `constructBuilding` doc]. The
fort already runs `buildingplan`, which attaches exact items to every
building our tools place, automatically, nearest first. A tool that
attaches exact items to a building it places does what the vanilla menu
does and what this fort already does through `buildingplan`. I see no
argument that this is a power; I record it as a proposed ruling for the
user to confirm rather than one I can make.

### 2.2 Workshop jobs: the real question

**Vanilla has no direct "use this log" action for a workshop task.** The
details button chooses material; the dwarf chooses the item, nearest to
himself (DF wiki Workshop). Attaching exact items at issue would give the
agent a choice the task screen does not.

**For "finer control of the same action":**

- The dwarf still walks to the item, carries it and does the work; no time
  or cost is skipped. If anything the chosen item may be farther from the
  dwarf than the one he would have picked.
- A vanilla player **can** force the exact item, indirectly and routinely:
  forbid every other candidate, or link a stockpile holding only that item
  to the workshop ("only linked stockpiles will be looked in"), or use
  burrows. The wiki teaches exactly this to steer a moody dwarf's
  materials ("selectively forbid ... so that only the material you want
  them to use is available"; "burrows allow even better control") [verified:
  primary doc, DF wiki Workshop, Strange mood]. The outcome, this log in
  this barrel, is reachable in vanilla.
- Item-level choices are ordinary vanilla actions elsewhere: building
  items, marking exact items for trade (`Items::markForTrade` is the
  vanilla mark), dumping, melting, forbidding one item.
- DFHack ships a tool that does exactly this to a workshop job,
  `autocheese`, tagged `fort auto`, not `armok` [verified: source]. The tag
  is only a pointer, but the DFHack maintainers did not read it as a cheat.

**For "a power the player lacks":**

- **It reserves an item for a task no dwarf has started.** In vanilla an
  item queued against a workshop task stays free until a dwarf takes the
  task; the only vanilla ways to hold it are forbidding (which also stops
  the task from using it) or a linked stockpile (which costs a stockpile
  and the hauling to fill it). Pre-attachment holds the item indefinitely,
  invisibly to every other job, with none of those costs. That is closer
  to "skip costs" than it first looks: the cost skipped is the
  workaround's.
- **It may produce a job state vanilla never produces**: a workshop task,
  no worker, reagents already bound. Whether vanilla ever creates that
  state (for example after a worker is interrupted mid-gathering) is
  [unverified]. If it does not, the `geld` precedent (state written
  directly rather than through the vanilla route) weighs against it, and
  so does the practical risk that DF handles an unfamiliar state badly (a
  job that never cancels when its bound item becomes unreachable).
- `autocheese` avoids that state: it assigns the worker in the same call,
  so the job never sits with bound items and no worker. Its precedent
  covers "attach and dispatch at once", not "attach and wait".

### 2.3 The options, stated for a ruling

| Option | Buildings and constructions | Workshop jobs | Consequence for claims (§3) |
|---|---|---|---|
| **A. Materials only** | exact items allowed (vanilla does it) | material, class and the `non_economic` flag only; DF picks the item | workshop claims are counted demand plus a matcher (§3.2); exact only from binding onward |
| **B. Exact items at issue** | allowed | exact items attached at issue, dwarf chosen by DF | exact everywhere our jobs go; depends on live test T2/T3 passing |
| **C. Exact items with dispatch (the `autocheese` pattern)** | allowed | attach only together with a worker assignment, so no job waits holding items | exact, but adds worker choice by code, a second question (it overrides DF's labor assignment, which the design deliberately left to DF, §8.5) |
| **D. The vanilla indirect route only** | allowed | hold by forbidding or by a linked stockpile, never by attaching | exact but with vanilla side effects (forbidden items unusable by the holder until un-forbidden at issue: the design's existing §8.4 hard hold) |

My reading of the evidence, not a decision: A is safe under any ruling;
B is arguable either way and I would not build it before T2 and T3; C
settles the engine question (DFHack runs it on real forts) but moves a
second decision (who works) from DF to code; D is what the design already
has and is best-effort by construction.

---

## 3. A claims design that never double-promises

All of this section is [proposed] unless a line says otherwise.

### 3.1 The flaw, and the fix in one line

§8.2 of the goal-tree design grants each **frontier** job from
`available(class)`, trusting `in_job` to remove what issued jobs hold. Two
things break that: an issued workshop job holds nothing until a dwarf
takes it (§1.1), and a filter is not a class, so one log can satisfy two
different jobs' filters (§1.4). The fix: **every live job's unbound demand
is read from the live job and committed before anything new is granted,
and every job we issue is narrowed to a single pool, so that what DF will
do with it can be counted exactly.**

### 3.2 Pools: promises that hold whichever item DF picks

Counting is only exact if it does not matter **which** compatible item DF
picks. DF picks nearest to the dwarf (§1.1), not by our plan, so a promise
must survive any choice DF could make. Matching items to demands (a
bipartite matching) is not enough: a matching can exist in which a broad
`building_material` filter takes the boulder and a log filter takes the
log, while DF's dwarf happens to fetch the log for the broad filter and
starves the other.

The rule that makes counting robust:

- A **pool** is a cell of live stock at the grain the chooser picks: item
  type, subtype, and material (`OAK` logs, `SHALE` boulders), or a
  material class where a filter only supports classes. Pool membership of
  an item is computed with DFHack's own matchers,
  `dfhack.job.isSuitableItem` and `isSuitableMaterial`, plus the flag
  checks `buildingplan`'s `matchesFilters` performs (empty, tool use,
  metal ore, heat safety) [verified: source, those functions exist and are
  what `buildingplan` uses; reusing them from our Lua is proposed].
- **Every job we issue has each filter narrowed to exactly one pool**, by
  setting the filter's `mat_type`/`mat_index` (and `item_type` where the
  filter allows several) before `assignToWorkshop`. That is the vanilla
  details button's power (§1.2) and needs no ruling.
- Then, per pool, `free(P) = supply(P) - committed(P) - granted_this_pass(P)`
  is exact for our own jobs: a filter narrowed to `P` can only ever take
  an item from `P`, whichever one DF picks.
- **A foreign job's filter may span several pools** (the fort's two
  pre-existing `MakeBarrel` jobs want "any wood log"). Its unbound demand
  is charged **in full against every pool it overlaps**. That over-counts
  (two jobs wanting one log each, with oak and pine on hand, reserve one
  of each twice), but it is the only charge that stays true whichever pool
  DF draws from, and it errs toward a hold, never a double promise. The
  hold names the foreign job, and the fix for the over-count is a vanilla
  action the Overseer can take: narrow that job's material, or cancel it
  (§3.5).

### 3.3 The cycle, step by step

1. **One snapshot, in one DFHack call.** A new read (working name
   `claims.snapshot`) returns, from a single Lua invocation: free items by
   pool (the six-flag netting of `production/blocker.py`, plus reachable
   and not on a hidden tile, the rules `df-overseer-stocks.lua` already
   applies); every live job with filters, with each filter's pools,
   `quantity` and bound count (`job.items` by `job_item_idx`); every
   `buildingplan` planned building's remaining `quantity` per filter;
   every manager order's `amount_left` and filters; and the moods in
   progress (§3.5). One call, because a DFHack command runs with the core
   suspended, so supply and demand are read at the same tick [reasoned:
   DFHack runs commands under its core lock; not re-checked for this
   pass], and because F-10's latency makes one call per check
   unaffordable.
2. **Tell ours from foreign.** Ours are the job ids the runner recorded on
   issue (`step_attempt`, and a copy in `dfhack.persistent` so that a
   rollback restores the matching set, per F-7). Everything else is
   foreign.
3. **Commit everything already issued, ours and foreign, before any
   grant.** `committed(P)` is the sum of unbound demand of every live job
   and planned building whose filter is narrowed to `P`, plus the full
   unbound demand of every broad foreign filter that overlaps `P`. Unbound
   demand is `quantity - bound` per filter, or `quantity` alone under the
   decrementing convention; which one DF uses for workshop jobs is live
   test T1. Priority plays no part here: an issued job is not pre-empted
   (the design's §9.1 step 5), so its demand is promised whatever its rank.
4. **Grant new demand in priority order**, all or nothing per job (kept
   from §8.2): for each frontier job, the chooser (§4) proposes a pool per
   filter with `free(P) >= need`; if any filter has none, the job is held
   with a named reason listing that pool's holders: `waiting: OAK log, 1
   free of 3; 2 committed to project-0004 job 2601 (issued, unbound); 0 to
   foreign`.
5. **Issue** the granted jobs with filters narrowed to their pools (and,
   under Option B or C of §2.3, with the chosen items attached). The
   granted amounts are written into the `step_attempt` as evidence, never
   read back as input (kept from §8.1).

**Recompute, never tally, is kept.** Every number in steps 3 and 4 comes
from the snapshot. The only stored inputs are the plan's declared `needs`
and the list of job ids we issued, which is a record of an action, not a
counter: if it were lost, our jobs would be counted as foreign, which
still never double-promises.

**Nothing to release.** A bound item leaves supply by its own `in_job`
flag and leaves unbound demand in the same read, so it is never counted
twice. A completed or cancelled job disappears from the snapshot, and its
demand with it.

### 3.4 Per group

**C. Workshop jobs (`workjob.queue`).**

- Option A (materials only): narrow each filter to its granted pool at
  issue. Demand stays unbound until the dwarf gathers; §3.3 counts it. The
  one gap is **which** item in the pool DF takes, which no promise depends
  on.
- Option B (exact items at issue): attach the chooser's items with
  `attachJobItem`, with the role and `quantity` handling T2 and T3
  establish (`autocheese` uses `Reagent` and `quantity = 0` [verified:
  source]). Demand is bound at issue and `committed` is zero for the job.
  What B adds over A is **which** item; its cost is a hold of unbounded
  length (until a dwarf reaches the job, possibly behind nine others in the
  workshop's queue, F-11). So B should issue only a job that can start
  soon: the F-11 per-workshop cap bounds the hold.
- Option C: as B, plus `addWorker` and dispatch in the same call; needs
  the second ruling in §2.3.
- `REAGENT_CHOICE` today pins only the type of a chosen container. Under
  A it should pin the pool (type and material) and say so; under B it
  attaches the chosen item, and its diagnostic stops saying "the instance
  may differ".

**B. Buildings and constructions (`building.build`, `construction.build`,
`blueprint.apply` build phase).**

- **Our own placements attach exact items at placement, as the vanilla
  menu does** (§2.1): either through `dfhack.buildings.constructBuilding
  {items = ...}`, or by attaching to the planned building's job before
  `buildingplan` registers it (`registerPlannedBuilding` finalizes at once
  when every `quantity` is already 0 [verified: source]). Then
  `buildingplan` has nothing to attach to our buildings and cannot hand
  our granted items to someone else's plan: the second half of F-4 is
  closed by construction, not by predicting `buildingplan`'s schedule.
- **No placement before its materials are granted** (all or nothing,
  §8.2). A building whose items are not in stock is held, not placed, so
  our buildings never wait in `buildingplan`'s FIFO against foreign plans.
- The `MATERIAL_CHOICE` gap (§1.2) closes with the same change: the chosen
  items carry the material, so "exclude economic by default" becomes true
  of the real build rather than only of the report.
- Constructions are buildings until complete, one `ConstructBuilding` job
  per tile [verified: primary doc, wiki Construction, "Constructions which
  have not yet been completed are technically Buildings"; source,
  `linkForConstruct`]; a blueprint's build phase attaches one item per
  tile, all or nothing for the step.
- If the user rules against exact items even here (unlikely, §2.1):
  narrow through `buildingplan`'s material filter for that building type
  while placing, and count planned buildings' remaining `quantity` as
  committed demand. Counting stays exact, but that filter is global per
  building type, so it races a human placing the same kind by hand
  [reasoned].

**D. Manager orders (`orders.create`), parked by the user's ruling.**

- An order has no item field (§1.2), only material. Narrow the order's
  material to its pool and count `amount_left` times its per-job filter
  quantities as committed demand from the moment the order is created,
  minus what its spawned jobs (`order_id`, `by_manager`) already hold;
  §3.3 then counts those jobs like any workshop job.
- Uncoverable: when, and at which workshop, the Manager spawns jobs. The
  count is exact; the timing is not. Orders never dispatch on this fort,
  so nothing here is urgent.

**A, E, F and the rest.** Designations bind no materials. Hauling (E)
binds only the hauled item, which is K8's item handle. Configured standing
work (F: `PlantSeeds`, standing-order jobs) is foreign demand from the
moment DF creates the job. Improvement jobs (F-19's forced grouping)
target one existing item, so they are exact-item claims by nature: under
any option the improved item is named in the plan and held by a hard hold
until issue.

### 3.5 Foreign demand, and what stays uncoverable

| Source | Visible from | Counted as | Stays uncoverable |
|---|---|---|---|
| DF-native jobs already queued (the 2026-09-28 `MakeBarrel` jobs 2592 and 2593 [repo record]) | creation | unbound filters, full charge on every overlapping pool | nothing once they exist; the over-count until the Overseer narrows or cancels them |
| `buildingplan` plans placed by a human, or before this design | placement | remaining `quantity` per filter, full charge on overlapping pools | which waiting plan `buildingplan` fills first (its FIFO, reorderable only by its `makeTopPriority`) |
| manager orders | creation | `amount_left` times filters | timing (above) |
| the Overseer's direct tool calls | the DF job's creation | foreign, like any other job | **the moment of decision**: nothing is visible between intent and call; F-17's fix (direct actions as one-node projects through the allocator) is the only full answer |
| a human on VNC | the DF job's creation | foreign | intent, as above |
| strange moods | the mood (the moody unit, the claimed workshop); items bind as gathered | before binding, the categories and quantities the user's `showmood` wrapper allows (categories, secondary quantities, the primary as the range 1 to 3), charged at the maximum | the exact items: moods "ignore settings regarding economic stone" and forbidding redirects them (DF wiki Strange mood), so no hold of ours is safe against a mood; report, never fight it |
| eating, drinking, planting from farm plots | the job, created and bound by DF | stock levels, not claims | whether a grant of seeds or drink survives the next meal; standing goals (K5) cover it at the level of stock, not items |
| destruction, rot, theft, trade | the next snapshot | supply shrinks | the loss itself; the hold that follows names it |

### 3.6 The F-4 scenario, replayed

Stock: 3 oak logs, reachable and free; the fort's own jobs 2592 and 2593
(`MakeBarrel`, one log of any wood each) still queued. Our barrel job
`p4/j2` needs 2 logs; the bed job of `project-0002` needs 2.

- **Cycle 1.** `supply(OAK log) = 3`; foreign committed 2 (jobs 2592 and
  2593 overlap every wood pool); `free(OAK) = 1`. `p4/j2` is **held**:
  `waiting: OAK log, 1 free of 3; 2 committed to foreign jobs 2592, 2593
  (MakeBarrel, unbound)`. The design as written would have granted it and
  then the bed as well. The Overseer, seeing the named holders, can cancel
  the two orphan jobs (they are the same work) with `workjob.cancel`.
- **Cycle 2**, after that cancel. `free(OAK) = 3`; `p4/j2` is granted 2,
  narrowed to OAK and issued as job 2601 [illustrative id]. The bed job is
  held: `free = 1`.
- **Cycle 3**, no dwarf has started 2601. Job 2601 is ours, unbound 2,
  committed to OAK; `free(OAK) = 3 - 2 = 1`. The bed is still held, `2
  committed to project-0004 job 2601 (issued, unbound)`: the promise the
  design made in words now holds in numbers.
- **Cycle 4**, the carpenter has fetched one log. Supply 2 (one log is
  `in_job`), 2601's unbound demand 1: `free = 1`. Unchanged, as it should
  be.
- Under Option B, cycle 2 attaches two named logs, and cycles 3 and 4 read
  `supply = 1`, `committed = 0`: the same answer, exact from issue.

### 3.7 What changes in the goal-tree design

- §8.1 table, Materials row: the allocation source becomes "the claims
  snapshot: free items by pool, minus the committed unbound demand of
  every live job (ours and foreign), minus grants earlier this pass"; the
  exact record adds "our issued job ids".
- §8.2: split "grant" into **commit** (every issued job's unbound demand,
  whatever its priority) and **grant** (new demand, in priority order, all
  or nothing); delete the sentence that `in_job` removes issued jobs'
  items; add pools and narrowing at issue.
- §8.4: under Option B the un-forbid-then-issue window disappears
  (un-forbid and attach in one call); under A it stays best effort.
- §8.6: add "a narrowed or attached job whose step was abandoned", released
  with the job (cancelling releases its items, §1.3).
- §12.1 step 5: the hold names foreign jobs 2592 and 2593 as holders.
- Tools: `workjob.queue` gains a pool (material) per filter and, under B,
  an item list; `building.build` and `construction.build` pass chosen items
  to the placement; one new read, `claims.snapshot`.

---

## 4. Who chooses what

[proposed throughout]

### 4.1 The split

| Choice | Made by | Where it is recorded |
|---|---|---|
| what to make, how many, for which goal | a model (the drafting role), ruled by the Overseer | the plan's `needs` |
| the **material constraint**: a class (`wood`, "any non-economic stone"), a named material (`SHALE`), or nothing | a model may state it in the draft; the Overseer's ruling fixes it | the job's `needs.material` |
| **permission for economic material** (ore, gem) or a scarce class (seeds, the last barrels) | the Overseer's ruling only, never a drafted default (F-5: authority-bearing fields must be ruled, not accepted by reference) | the ruling |
| the **pool** each filter is narrowed to | code, the chooser | the `step_attempt` (evidence) |
| the **exact items** (Options B and C, and all buildings) | code, the chooser | `job.items` (the game's own record) |
| which dwarf does the work | DF (Options A, B, D); code only under Option C | the job's worker ref |

A model never sees an item id list and never names an item. That keeps the
model's inputs at the level a player reasons in (material, class,
quantity), keeps item lists (which can be long) out of prompts, and keeps
the one choice that must obey the knowledge rule (hidden tiles) in code
that can be tested.

### 4.2 What the chooser must never do

Hard constraints, each a refusal with a named reason, never a silent skip:

1. **Economic material without explicit authority.** Economic means
   `inorganic:isOre()` or `inorganic.material:isGem()`, the test
   `building.lua` already uses after the 2026-09-28 correction [verified:
   source, `df-overseer-building.lua` 735-783], never `economic_uses`. A
   filter that itself requires `non_economic` (`WORTHLESS_STONE_ONLY`)
   wins over any authority.
2. **An item on a hidden tile**, or one whose position cannot be shown to
   be visible when the item is not held inside the fort: the knowledge
   scope rule of 2026-09-16, as `df-overseer-stocks.lua` applies it
   [verified: source, `is_on_hidden_tile`]. `buildingplan` does not apply
   it (§1.1), which is one more reason our placements attach their own
   items.
3. **An unreachable item**: not in the walkability group of the job site
   (the tri-state reachability helper; unknown is not reachable).
4. **Anything a human or DF has set aside**: `forbid` without a
   `hard_holds` row of ours (never un-forbid what we did not forbid),
   `dump`, `melt`, `owned`, `trader`, `in_building`, `construction`,
   `in_job`, artifacts (unless the filter sets `allow_artifact`), items in
   `buildingplan`'s ignore burrow.
5. **An item named by another plan**: another project's hard hold, or an
   improvement job's target.
6. **A scarce class** (a doctrine entry: seeds needed for the next
   planting, the last N empty food containers) unless the job's ruling
   owns that class.
7. **A container that is not empty** when the filter wants `empty`, and
   **never reuse a full container** by emptying it: that is a separate job
   with its own ruling (the 2026-09-28 barrels lesson).

### 4.3 What the chooser optimises, in order

1. **Keep the most slack**: among pools that satisfy the constraints,
   prefer the one with the largest `free(P) - need` after all commitments,
   so a grant drains an abundant pool before a scarce one and future holds
   are rarer. Avoid pools that broad foreign demand overlaps, since those
   are charged twice.
2. **Keep a step's material uniform** where the step says so (a wall run,
   a room's furniture), as a doctrine-settable preference, not a rule.
3. **Shortest haul**: for a workshop job, distance from the item to the
   **workshop**; for a building, to the site, using `buildingplan`'s own
   metric (Chebyshev distance plus z difference) so our choice matches
   what the fort's tooling would have done. Prefer items already in a
   stockpile linked to the workshop.
4. **Lowest value first**, so a rough job does not burn a fine item
   [reasoned; needs an item-value read, not yet checked].
5. **Deterministic tie-break**: lowest item id, as `REAGENT_CHOICE auto`
   already does, so a re-run makes the same choice and the record is
   reproducible.

Under Option A the chooser stops after step 1 (it picks pools only);
under B, C and for buildings it continues to exact items. Every choice is
reported with its reason, in the same shape `REAGENT_CHOICE` already
reports (`chosen_how`).

---

## 5. A live test plan (not run)

For the orchestrator, after the user's go-ahead. Nothing here was run.

### 5.1 Common protocol

- Peer check-in before touching VM 103 (`CLAUDE.md`), fort paused at the
  start, `quicksave` before any write, supervised unpause windows only,
  everything captured to `evals/live/<date>-item-binding-tests/`.
- **An observer, read-only**: a small in-game Lua watcher (DFHack's
  `repeat-util` `scheduleEvery(name, 1, 'ticks', fn)` [verified: source,
  `library/lua/repeat-util.lua` exists at the tag; the call shape is from
  memory and must be checked]) that, for a given list of job ids and item
  ids, appends one line to a log file whenever any of these change: the
  job's existence, worker, `flags` (`suspend`, `fetching`, `bringing`,
  `working`, `item_lost`), each filter's `quantity`, each `job.items`
  entry (item id, role, `is_fetching`, `job_item_idx`), and each watched
  item's `in_job`, `forbid`, position (as a walk group and "in workshop"
  or not, never a coordinate), and existence. It writes nothing to the
  game. It is removed at the end of each test.
- **Where each test runs.** T1, T5, T6, T8 and T9 are safe on the live fort
  (they queue or place something the fort would want anyway, or only
  read). **T2, T3 and T4 create job states vanilla may never create (§2.2)
  and should run in a save-and-reload harness branch**, which the
  2026-09-25 ruling allows only to the test harness, started by a human,
  with results used as evidence and never fed back into play
  (`docs/ARMOK-RULINGS.md`, last row). If the user prefers them live,
  they are still reversible: each consumes at most one log and cancelling
  the job releases its items (§1.3).

### 5.2 The tests

| Test | Settles | Steps | Pass reads |
|---|---|---|---|
| **T1. DF's own binding, observed** (live, read-mostly) | when DF binds a workshop job's items (at worker assignment, or one by one as gathered); which role DF uses; whether DF decrements `quantity` | Pick a job with at least two items or `quantity >= 2` from `workjob.list-jobs` (a two-ingredient meal at the Kitchen, or a brew if an empty container exists); queue it with a dry run then for real, paused. Start the observer. Unpause under supervision until the job completes or 2,400 ticks pass. | The log shows the tick of worker assignment and the tick each item enters `job.items`, with role and `quantity` at each step. This decides the unbound-demand formula (§1.4, §3.3 step 3). |
| **T2. A pre-attached reagent, DF chooses the worker** (harness branch) | whether DF honours a pre-attached item on a workshop job it later gives to a worker of its own choosing | Paused. Queue `MakeBarrel` (1 log). Choose a log `L` that is **not** the nearest to the workshop. Variant a: `attachJobItem(job, L, Reagent, 0, -1)`, `quantity` left at 1. Variant b (reload between): the same with `quantity = 0` (the `autocheese` form). Read `job.items` and `L.in_job`. Start the observer; unpause until done or 2,400 ticks. | Pass: a dwarf fetches `L`, no second log is bound, a barrel is produced, and `L` is consumed. Record which variant passes; a variant that binds a second log, ignores `L`, or never starts fails. |
| **T3. When the attached item goes wrong** (harness branch) | what DF does when a pre-attached, unfetched reagent is forbidden, becomes unreachable, or its job is cancelled | From the T2 setup that passed, three runs, reloading between: (a) forbid `L` before any dwarf takes the job, then unpause; (b) forbid `L` while it is being fetched; (c) forbid passage on the one door on the route to `L` (vanilla door lock) and unpause; (d) cancel the job with `workjob.cancel`. | For each: is the job cancelled, left waiting, or does it bind another log; the announcement text; `L.in_job` afterwards. (d) must clear `L.in_job`. Any run that leaves a job permanently stuck holding `L` is a finding against Option B. |
| **T4. DF's own search never takes an `in_job` item** (harness branch) | the premise of §3's counting for DF-native jobs | Two logs `L1`, `L2`, every other log forbidden. Attach `L1` to job X and suspend X (the vanilla suspend flag). Queue a filter-only `MakeBarrel` Y. Unpause. Then reload and repeat with `L2` also forbidden. | Run 1: Y takes `L2`, never `L1`. Run 2: Y waits or is cancelled for want of a log, and `L1` stays bound to X. |
| **T5. Exact items at building placement** (live) | that a building placed with explicit items is built from them and `buildingplan` leaves it alone; which `use_mode` a building's material gets; whether a construction's item survives with the `construction` flag | Paused. Place one cheap building the fort wants (a door or table in stock) with `constructBuilding{items = {I}}`, and one constructed floor tile from a named boulder `B`. Read `isPlannedBuilding`, `job.items`, `I.in_job`. Unpause until built. | `I` in the building's `contained_items`, with its `use_mode` read; `B` still exists with `flags.construction` (answers the design's §8.3 `[unverified]` item), or not. |
| **T6. When `buildingplan` binds** (live) | whether `buildingplan` attaches items while the game is paused, and how soon after placement | Paused, items in stock. Place one building through `building.build` (quickfort, so `scheduleCycle` is called). Read `job.items` immediately, then after 30 seconds still paused, then after one supervised unpause of a few ticks. | Tells whether "no tick passes" implies "no item binds" (the plugin's `onupdate` may run while paused [reasoned from the overlay developer guide]). Matters for the runner's read-after-issue check. |
| **T7. What the details button writes** (live, needs the user on VNC) | which `job_item` fields the vanilla material choice sets | Queue any job; the user sets its material with the details button; read the filter's `mat_type`, `mat_index` and the `job_details_*` fields before and after. | Tells the runner which fields to write when narrowing (§3.2), so that narrowing is exactly the vanilla state. |
| **T8. Narrowing is honoured** (live) | that DF takes only the narrowed material, not the nearest | With two woods in stock, queue `MakeBarrel` narrowed to the wood that is **not** nearest; observe. Then narrow a second job to a wood with no stock and observe. | The first takes the narrowed wood. The second shows what DF does with an unsatisfiable filter (waits, or cancels with an announcement); both inform the hold logic. |
| **T9. Snapshot cost** (live, read-only) | F-10: can `claims.snapshot` be one call per cycle | Run the snapshot prototype, paused, three times. | Wall-clock time per call, and the tick before and after (must be equal). |

T2 and T3 decide whether Option B is buildable at all; T1 decides the
counting formula every option needs; T7 and T8 make Option A exact. If the
user rules Option A, T2 to T4 can be skipped.

---

## 6. Decisions for the user

1. **Exact items for buildings and constructions.** Proposed: allowed,
   because the vanilla build menu chooses specific items and attaches them
   at placement (§2.1), and `buildingplan` already does it on this fort.
   Confirming it closes F-4's `buildingplan` half and makes the
   economic-material default real (§1.2, §3.4 B).
2. **Workshop jobs: Option A, B, C or D** (§2.3). A (materials only) is
   safe under any reading and is enough to never double-promise; B (exact
   items at issue) is the arguable one; C (attach and dispatch, the
   `autocheese` pattern) also moves the worker choice from DF to code; D
   (forbid-based holds) is what the design has now. B and C wait on T2 and
   T3 in any case.
3. **Foreign jobs.** The conservative charge (§3.2) will hold our jobs
   behind DF-native jobs such as 2592 and 2593. Should the runner ever act
   on foreign jobs itself (cancel or narrow them), or only name them in
   the hold for the Overseer? Proposed: name only; acting on foreign work
   is the Overseer's call.
4. **The Overseer's direct tools** (F-17). While the Overseer can issue
   consuming jobs outside a project, its intent is invisible until the DF
   job exists (§3.5). Routing its direct actions through the allocator as
   one-node projects is the only full fix; the decision is the user's.
5. **Where T2 to T4 run**: in a save-and-reload harness branch (proposed,
   §5.1) or on the live fort.
6. **Economic material and scarce classes as ruled fields only** (§4.1),
   never draft defaults accepted by reference (F-5). Proposed; it
   tightens the ruling contract.

A separate note for a memory audit, not a decision: `building.build`'s
header claims the economic-material default is applied to the real build;
the code makes it advisory only (§1.2).

---

## 7. Not verified

- **Whether DF honours a pre-attached reagent on a workshop job that DF
  later assigns to a worker of its own choosing.** No DFHack code at the
  tag does this; `autocheese` attaches and assigns in one call. T2.
- **Whether DF binds a workshop job's items all at worker assignment or one
  by one**, and which role and `quantity` convention it uses. Reasoned
  from flag comments and the wiki only. T1.
- **What DF does when a pre-attached, unfetched item is forbidden or
  becomes unreachable**, and whether `item_lost` applies to `Reagent` as
  well as `Hauled`. T3.
- **That DF's own item search skips `in_job` items.** The flag's purpose
  and every DFHack path say so; DF's code was not read. T4.
- **Whether vanilla ever produces a workshop job with bound items and no
  worker** (it bears on the armok question, §2.2). Not found in any
  source read.
- **Which fields the vanilla details button writes** (`mat_type` or the
  `job_details_*` shadow fields). T7.
- **The v50 build menu's specific-item choice in practice.** Verified
  from df-structures (`build_req_choice_specst`); not seen in the running
  game or described on a v53 wiki page. The DF wiki Building page read for
  this pass does not describe material selection at all.
- **That a DFHack command sees one consistent tick** (the snapshot's
  premise). Reasoned from DFHack's core lock; not re-read here. T9 checks
  the tick is unchanged across the call.
- **Whether `buildingplan` binds while paused.** Reasoned from the overlay
  developer guide's description of `plugin_onupdate`. T6.
- **Whether a construction keeps its item object.** The wiki's
  Construction page (tagged old) says the game "has to keep track of the
  original item"; df-structures' `construction` has no item id (design
  §8.3). T5.
- **`repeat-util`'s exact call signature** for the observer, written from
  memory; the module exists at the tag.
- **Whether the `gui/workshop-job` counting convention reflects DF's**:
  that script is from the v0.47 era and its v50 status was not checked.
- Nothing about this fort's live state was read for this pass: whether jobs
  2592 and 2593 still exist, the log stock, and whether any stockpile is
  registered with `logistics` are [repo record] or unknown.

---

## 8. Sources

Upstream, read at tag `53.16-r1` (whole repositories downloaded from
GitHub for a tree-wide search):

- DFHack: `library/modules/Job.cpp` (`attachJobItem`, `disconnectJobItem`,
  `removeJob`, `assignToWorkshop`, `isSuitableItem`, `isSuitableMaterial`),
  `library/modules/Buildings.cpp` (`linkForConstruct`,
  `constructWithItems`, `constructWithFilters`), `library/modules/Items.cpp`
  (`markForTrade`), `plugins/buildingplan/buildingplan.cpp`,
  `buildingplan_cycle.cpp`, `itemfilter.cpp`, `plugins/stocks.cpp`,
  `plugins/tweak/tweaks/animaltrap-reuse.h`, `docs/dev/Lua API.rst`
  (job and building functions), `docs/plugins/buildingplan.rst`,
  `docs/plugins/jobutils.rst`, `docs/dev/overlay-dev-guide.rst`,
  `library/lua/repeat-util.lua` (existence only).
- DFHack/scripts: `autocheese.lua` and `docs/autocheese.rst`,
  `idle-crafting.lua`, `husbandry.lua`, `entomb.lua`, `store-owned.lua`,
  `immortal-cravings.lua`, `gui/workshop-job.lua`,
  `internal/quickfort/build.lua`, and the tags in their docs.
- df-structures: `df.job.xml` (`job_item`, `job_role_type`,
  `job_item_ref`, `jobitem_flag`, `job_flags`, `job`), `df.d_basics.xml`
  (`job_item_flags1/2/3`, `job_material_category`), `df.building.xml`
  (`build_req_choice*`, `buildreq`, `ui_build_item_req`,
  `buildingitemst`), `df.workquota.xml` (`manager_order`).

DF wiki, raw wikitext, current: Workshop, Forbid, Strange mood, Work
orders, Building, Construction.

This repo: `scripts/dfhack/df-overseer-workjob.lua`,
`df-overseer-building.lua`, `df-overseer-construction.lua`,
`df-overseer-stocks.lua`, `production/blocker.py`,
`research/2026-09-30-goal-tree-design.md` (§4.2, §8, §9.4, §12.1),
`research/2026-09-30-goal-tree-red-team.md` (F-4, F-5, F-10, F-11, F-17,
F-19, F-20), `research/2026-09-18-schema-extraction-live.md` §1,
`memory/dfhack-environment.md`, `docs/ARMOK-RULINGS.md`,
`decisions/DECISIONS.md` (2026-09-28 rows).
