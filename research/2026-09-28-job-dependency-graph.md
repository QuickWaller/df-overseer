# Job dependency graph: a design for tracking work as projects, steps and guards

Date: 2026-09-28. Researcher (Opus), design only. Brief:
`handoffs/2026-09-28-job-dependency-graph-design.md`. Nothing here is built,
nothing in the repo or on the fort was changed. Several read-only live reads
were made on VM 103 (fort paused throughout, tick 209571); each is quoted
where used.

Status: **proposal for the user's review.** Recommendations are stated as
mine, and are meant to be argued with.

Related, read before this: `research/2026-09-22-objective-graph-prior-art.md`
(the strategic layer: objectives, deviation rules, FHIR PlanDefinition, CQL
three-valued logic). This document is one level down: not "what is the fort
trying to achieve" but "what work is in flight, what is it waiting on, and
what must not happen yet."

---

## 0. The answer, up front

1. **Four layers, not one "job" concept.** A *proposal* is a unit of
   decision (exists). A **project** is a unit of intended work, created when
   a proposal is accepted (new; it is the `plan` record `docs/AGENT-ARCHITECTURE.md`
   §9 and `dfqueue/README.md` already say is missing). A **step** is one
   tool action over a named set of targets (new). A **DF job** is the game's
   unit of work, which we observe and attach to a step as evidence but never
   put in the graph as a node. "Every small job is a module of a larger job"
   holds: every DF job we cause belongs to exactly one step, every step to
   one project. The edges live between steps.

2. **Three kinds of edge, deliberately different mechanisms.**
   - `requires` (hard, finish-to-start between steps): the classic DAG edge.
     Its state is **tracked explicitly** in the queue, per the user's
     2026-09-28 ruling.
   - **Guards** (must-not-conflict): a world-state predicate from a closed,
     data-listed vocabulary, checked by code **per target, at designation
     time and on every reconcile**, and able to hold one target while its
     siblings proceed. This is the edge that would have caught building 22.
     It is not an edge to another step; it is a condition on the world, the
     same shape as DFHack's own `suspendmanager` reasons and a CMMN sentry.
   - `prefer_after` (soft): affects which ready step the Overseer picks,
     never blocks.

3. **Recorded state and observed state are two separate fields, never
   merged.** What we did is recorded (append-only queue records, `executed`
   reused). What the world looks like now is observed by a code-run
   reconciler and written beside it. A mismatch is *drift*: flagged, never
   silently overwritten. This is Terraform's state-plus-refresh and
   Kubernetes' spec-versus-status, and it is exactly the user's "track
   explicitly, reconcile via live reads" ruling.

4. **Scope: one store per fort, organised into projects; guards are
   fort-wide.** Not one graph per room or zone (the vein that caused this
   crosses zone 13's boundary, which is the whole lesson), and not one
   monolithic fort plan (the objective graph owns that level and prompts
   must not grow with it). The Overseer's existing WIP limit becomes a cap
   on active projects.

5. **Build order, if the user agrees: guards first, as tool-layer refusals.**
   A reachability-based "keep exposed ore reachable" guard inside
   `construction.build` (and `blueprint apply`'s build phases) would, on its
   own, have refused building 22 at designation time with a reason. It
   needs no graph, no schema change and no new agent behaviour, and it
   follows the roster's own rule that a safety veto is "refusals in the tool
   layer" (`agents/ROSTER.yaml`, rejected-roles comment). Projects and steps
   in `dfqueue` come second; the reconciler third.

Two findings from this pass that change the premise slightly, both verified
live and both detailed in §3:

- **A mined vein tile is not indistinguishable from ordinary floor.** The
  five mined tiles on zone 13's ring still read `HEMATITE, ore_or_gem`
  through `surface.vein-material 13` (live, just now), because the floor
  keeps the vein's material; and DF's `construction` struct keeps an
  `original_tile` field, so the evidence survives even a wall built on top.
  What the world cannot tell you is **who** did it, **when**, **why**, and
  whether an open tile was *meant* to be open (a doorway) or is merely open.
  The user's ruling stands, for those reasons rather than the one it was
  first argued from.
- **The "26 unmined ore tiles, 5 exposed" scan counted hidden tiles.** Only
  the 5 exposed ones are information a player has. A guard or tool that an
  agent can see must treat hidden tiles as unknown, never as ore
  (`CLAUDE.md`, "No armok capabilities": information the game hides). This
  constrains the design and is written into it.

---

## 1. The problem, stated domain-neutrally

A controller issues work to an environment it does not own. The environment
executes that work on its own schedule, with its own agents (dwarves),
sometimes cancels it, and sometimes changes underneath it for unrelated
reasons (a cave-in, a tantrum, a human on VNC, a crash that rolls the world
back to the last save). The controller needs to know:

- what it asked for, and why, and as part of what larger intention;
- which pieces are allowed to start, given other pieces;
- which pieces must not start *yet*, given the state of the world;
- which pieces are done, including when the world no longer shows it
  clearly;
- when its belief about any of the above has stopped matching the world.

Fields that own this shape, and what each was read for:

| Field | System read | What it contributes |
|---|---|---|
| Build systems | GNU make manual, Bazel Skyframe reference | Completion as a recorded artefact (stamp files), invalidation of dependants, discovering dependencies mid-evaluation |
| Data pipelines | Apache Airflow docs, Dagster docs | A closed task-state vocabulary; trigger rules; recorded materialisation versus passive observation |
| Infrastructure as code | Terraform docs | An explicit state file because the world cannot be relied on to say what you did; refresh and drift |
| Cluster control loops | Kubernetes controller docs and API conventions | Desired versus observed state; level-triggered reconciliation; conditions with True/False/Unknown |
| Game engine job graphs | Unity job system docs | Plain finish-to-start handles; useful mostly as a contrast |
| Project scheduling (CPM) | Microsoft Project link-type docs | The four precedence types and lag; which of them this domain needs |
| **DF itself** | DFHack `suspendmanager` source (53.16-r1 tag), df-structures, df-ai (via this repo's own source read) | The game's own gating vocabulary, and a working precedent in exactly this domain |

The DF-native prior art turned out to be the most directly useful, which is
worth saying because it was not on the brief's list.

---

## 2. Prior art: what each answers

Confidence labels: **[source]** read in the actual source code;
**[primary doc]** fetched from the project's own documentation, quoted;
**[summary]** a fetch tool's summary of a primary page, wording not
independently checked.

### 2.1 How a node's completion is represented

- **GNU make** [primary doc, manual §4.8 "Empty Target Files to Record
  Events"]: when a rule's output does not exist as a durable artefact, make's
  own answer is to invent one: "The purpose of the empty target file is to
  record, with its last-modification time, when the rule's recipe was last
  executed. It does so because one of the commands in the recipe is a touch
  command." That is a **stamp file**: explicit completion bookkeeping,
  adopted by the oldest build tool precisely where deriving completion from
  outputs fails. This is the user's 2026-09-28 ruling, arrived at by make in
  the 1970s.
- **Terraform** [primary doc, "Purpose of Terraform State"]: "Terraform
  requires some sort of database to map Terraform config to the real
  world." It tried deriving it from the world first: early versions used
  cloud tags and this failed because "not all resources support tags, and
  not all cloud providers support tags." State also carries what the world
  cannot: "When you delete a resource from a Terraform configuration,
  Terraform must know how to delete that resource from the remote system",
  and ordering the world does not record. Direct analogue: an open tile
  cannot say it was a mined vein that still owes a wall.
- **Dagster** [primary doc, asset observations]: a *materialisation* records
  that Dagster produced or changed an asset; an *observation* "records
  metadata about a given asset" and "do[es] not signify that an asset has
  been mutated." For assets Dagster does not produce, an observation
  function returns a data version, and a downstream asset is flagged when
  "an asset is observed to have a newer data version than the data version
  it had when a downstream asset was materialized." [summary] Staleness is
  computed by comparing versions recorded on materialisation events, not by
  inspecting the stored data. **This is the cleanest split found between
  "what we did" (materialisation, our `executed`) and "what we saw"
  (observation, the reconciler's record).** Adopt the split by name.
- **Airflow** [primary doc, Tasks]: a closed state set. The ones that matter
  here: `none` ("dependencies are not yet met"), `scheduled`, `running`,
  `success`, `failed`, `skipped`, `upstream_failed` ("An upstream task
  failed and the Trigger Rule says we needed it"), `up_for_reschedule` ("a
  Sensor that is in reschedule mode", i.e. waiting on the world),
  `deferred`, `removed` ("vanished from the Dag since the run started").
  Two lessons: waiting-on-the-world is a distinct state from
  waiting-on-a-task, and "removed" is a real outcome distinct from failed.
- **df-ai** [source, via `research/2026-09-24-df-ai-fort-planner.md` §Q5]:
  each room carries an explicit four-state status (`plan`, `dig`, `dug`,
  `finished`) that df-ai itself maintains, plus a periodic `checkroom` sweep
  that re-issues cancelled digs and rebuilds "tantrumed" furniture. So the
  one mature DF automation project found also tracks state explicitly and
  reconciles periodically. Its commit log also records the failure shape to
  design against: "fix rooms that were never built somehow" (`d6a6f06`).

### 2.2 How "blocked on" is represented

- **Finish-to-start dependency** is universal: Unity ("The job system won't
  run the dependent job until the job it depends upon is finished"
  [primary doc]), Airflow's default trigger rule `all_success` ("All
  upstream tasks have succeeded" [primary doc]), make prerequisites, and
  Microsoft Project's default link type [primary doc]: "The dependent task
  (B) can't begin until the task that it depends on (A) is complete."
- **The other three CPM link types** [primary doc, Microsoft Project]:
  start-to-start, finish-to-finish, start-to-finish, plus lag and lead
  ("type a negative value in the Lag column"). For this domain I can find
  a real use only for finish-to-start. Start-to-start ("haul while digging")
  is DF's own business, not ours. **Recommendation: finish-to-start only;
  add others when a real case appears.** `research/2026-09-22-objective-graph-prior-art.md`
  already recommends FHIR's nine-value `relatedAction` for the *objective*
  layer; the step layer does not need it.
- **Trigger rules** [primary doc, Airflow]: 13 variants (`all_success`,
  `one_success`, `none_failed`, `all_done`, ...). One is worth keeping: the
  difference between "all prerequisites succeeded" and "all prerequisites
  finished, whatever the outcome" (`all_done`), because "mine the vein"
  can end with some tiles unmineable and the wall step should still run on
  the ones that were. Keep two: `all_success` (default) and `all_done`.
- **Waiting on the world, not on a task.** Airflow models this as a sensor
  (a task that polls). Kubernetes as a condition. CMMN as a sentry's
  `IfPart` (from the 2026-09-22 research). **DFHack's `suspendmanager` as a
  closed enum of reasons** [source, `plugins/suspendmanager.cpp` at tag
  53.16-r1, lines 67-79]: `UNDER_WATER`, `BUILDINGPLAN`, `RISK_BLOCKING`
  ("May block another build job"), `ERASE_DESIGNATION` ("Waiting for
  carve/smooth/engrave"), `DEADEND` ("Blocks another build job"),
  `UNSUPPORTED` ("Would collapse immediately"), `ITEM_IN_JOB`. Each is a
  predicate over the world, evaluated per construction job, that holds that
  one job. `ERASE_DESIGNATION` is structurally identical to our case: "a
  construction on this tile would destroy something still pending here".
  Ours is "a construction on this tile would cut off something still pending
  next door". **This is the direct model for guards.**

### 2.3 How a completed node with ambiguous evidence is handled

**"Nobody really does this" is close to the honest finding.** Every system
surveyed assumes a completed node's output is durable and inspectable (a
file, a table, a resource). None has a first-class notion of "done, and the
world now cannot confirm it". What they do instead, consistently, is **not
ask the world**: make writes a stamp, Terraform keeps state, Dagster
compares recorded versions, df-ai keeps its own status. The world is
consulted to *detect change* (make's mtime comparison, Terraform refresh,
Dagster observation, Bazel's `stat()` of inputs), never as the sole record
of completion. That is corroboration for the user's ruling from every field
checked, and I found no counterexample.

What this project needs on top, which none of them has, is an explicit third
value for the observation: `consistent`, `contradicted`, or
`not_observable`. Kubernetes' condition `Status` already has exactly this
shape [primary doc, API conventions]: "one of True, False, Unknown", with a
`Reason`, a `Message`, and `ObservedGeneration` ("the .metadata.generation
that the condition was set based upon"). Adopt it: every observation carries
the game tick it was read at.

### 2.4 How a graph is re-checked when the world changes without warning

- **Kubernetes** [primary doc]: "your cluster never reaches a stable state.
  As long as the controllers for your cluster are running and able to make
  useful changes, it doesn't matter if the overall state is stable or not."
  And from the API conventions: "the system's behavior is *level-based*
  rather than *edge-based*. This enables robust behavior in the presence of
  missed intermediate state changes." **Adopt level-based reconciliation:**
  the reconciler compares recorded state to the current world every cycle
  and does not depend on having seen every event. DFHack events (`eventful`
  `JOB_COMPLETED`, already used by `df-overseer-stuckjobs.lua` for
  `JOB_INITIATED`) are useful hints for timeliness, never the truth.
- **Terraform** [primary doc, `plan`]: by default it "Reads the current state
  of any already-existing remote objects to make sure that the Terraform
  state is up-to-date", and has a separate `-refresh-only` mode "to update
  the Terraform state ... to match changes made to remote objects outside of
  Terraform", which the operator approves. **Adopt the separation:** the
  reconciler writes observations and flags drift; it does not rewrite a
  recorded step state on its own. Accepting drift into the record is a
  decision (the Overseer's).
- **Bazel Skyframe** [primary doc]: bottom-up invalidation "all the nodes are
  invalidated that transitively depend on changed files", and change pruning,
  where a re-evaluated node whose value is unchanged "resurrects" its
  dependants. Useful for one rule: when a `done` step is contradicted, its
  dependants that have not started go back to waiting; dependants already
  done are flagged for review, not undone. Also **dynamic dependency
  discovery**: "A SkyFunction can request SkyKeys in multiple passes if it
  cannot tell in advance all of the nodes it needs to do its job." That is
  the vein: you do not know the next ore tile until you mine the current one
  and it is revealed. §3.4 uses this.
- **suspendmanager** [source, same file, lines 648-721] is the cautionary
  half. Its `refresh()` starts with `suspensions.clear()` and recomputes every
  reason from the world, every cycle: fully level-based, no memory. And its
  `do_cycle()` then does, verbatim:

  ```cpp
  if (job->flags.bits.suspend && !suspensions.contains(job->id)) {
      unsuspend(job); // suspended for no reason
  ```

  DF's suspension is a single bit with no reason attached (df-structures
  `job_flags`: `suspend`, original name `SUSPENDED`), so a tool that owns
  suspension cannot tell *our* deliberate hold from a stale one, and clears
  it. **Consequence for this fort, verified live:** `suspendmanager` is
  currently **off** (`dfhack-run enable`, `suspendmanager is disabled`), so
  the hand suspension of job 2705 is safe today. Anyone enabling it, or
  running `unsuspend`, would release building 22's wall with no warning.
  And more generally: **a hold whose only record is the suspend bit is not
  a durable hold.** Our holds must live in our own record, and be
  re-asserted by our reconciler.

### 2.5 The game's own dependency model

- **Manager work orders already have native dependencies** [source,
  df-structures `df.workquota.xml`, master branch, not checked against the
  53.16 tag]: each `manager_order` has `order_conditions`, each naming another
  `order_id` and a condition `Activated` or `Completed` (Bay12's
  `ON_ACTIVE`/`ON_COMPLETE`): start-to-start and finish-to-start, between
  orders only. And `item_conditions`, which are stock predicates: DF's own
  guards. So the game itself converged on the same two mechanisms (edges
  between work units, predicates over the world). This project's
  `df-overseer-orders.lua` reads and writes neither field today, and every
  order on this fort has had both empty (`handoffs/2026-09-19-well-finish.md`).
- **Ordinary jobs have no prerequisite edges at all**, only the suspend bit,
  `do_now`, and the building or tile they hang off. DF expresses ordering for
  digs and constructions only implicitly (a construction on a wall-shaped tile
  cannot be placed, `research/2026-09-24-quickfort-hands.md`).

---

## 3. The motivating case, read live

All reads below were read-only `dfhack-run lua` or existing read tools, fort
paused at tick 209571.

**The five walls** (buildings 18 to 22, all `Construction`, stage 0, z 167):

| Building | Job | Suspended | Notes |
|---|---|---|---|
| 18 | 2701 | no | |
| 19 | 2702 | no | |
| 20 | 2703 | no | |
| 21 | 2704 | no | diagonally adjacent to the exposed ore tile |
| 22 | 2705 | **yes** (by hand) | orthogonally adjacent to it; `buildingplan` no longer manages it (`isPlannedBuilding: false`, one item attached), so buildingplan will not unsuspend it either |

**The ore tile's neighbourhood**, at the exposed hematite tile west of
building 22 (tiletype shape / material class; B = building):

```
STONE wall      STONE wall      FLOOR (B21)
MINERAL wall    MINERAL wall*   FLOOR (B22)
MINERAL wall    MINERAL wall    STONE wall
```

`*` is the exposed ore tile. The left column is **hidden**
(`designation.hidden = true`), so its material is information a player does
not have. I read it in this research pass (a human-run read, not an agent),
and it must never reach an agent; I note it only to show the vein continues.

What this shows:

1. **The exposed ore tile has exactly two open neighbours on its level, and
   both are the sites of new walls.** Building both seals it. Building 22's
   tile is its only orthogonal approach; building 21's is diagonal. Whether a
   DF miner can dig from a diagonal neighbour is **not verified here**. If it
   can, building 22 alone was never the problem, the pair was; if it cannot,
   holding 22 alone is exactly right. Either way the correct rule is about
   **reachability of the ore after all of a step's constructions complete**,
   evaluated jointly over the step, not "is this one tile adjacent to ore".
2. **Once the exposed tile is mined, the vein behind it is reached only
   through that same pocket.** Walling building 22's tile then seals the
   rest of the vein. So the hold is not "until one tile is mined"; it is
   "until no exposed economic ore depends on this approach", which a
   reachability guard expresses and an adjacency rule does not.
3. **Mined ore tiles still read as ore.** `surface.vein-material 13` today
   returns `ore_or_gem, HEMATITE` on all five ring tiles, which are now
   open floor (the tool classifies the tile's vein material, not its shape).
   Mined-out vein floor keeps its material. So the claim in the brief and in
   `Working.md` ("once a vein is mined the tile is just open floor") is
   **partly wrong**: a later read can tell "this is open floor over
   hematite". It cannot tell who mined it, when, whether the ore item was
   recovered, or whether an open ring tile is open on purpose.
4. **`construction.build` infers "was mined" from "is open".** Code read,
   `df-overseer-construction.lua` lines 447-460: every ring tile that is not
   wall-shaped becomes a build candidate. On zone 13 that happened to be
   exactly the five mined tiles (`open_tiles_found: 5`). On a room whose
   ring includes its doorway, the same call would wall the doorway. That is
   the derived-state failure the user's ruling exists to prevent, sitting in
   today's tool, and it is a better argument for explicit tracking than the
   vein-floor one: **the wall step's targets should be the mine step's
   completed targets, handed forward as data, not re-derived by a scan.**

Also noted: `df.construction.original_tile` (df-structures `df.event.xml`,
original name `old_tile`) records the tiletype a construction replaced, so
even a built wall keeps evidence of what was under it. Not read live (no
completed construction on this ring yet), so treat as likely, not verified
on 53.16.

---

## 4. The data model

### 4.1 Nodes

**Project** (new record kind; the missing §9 `plan` record):

```yaml
project:
  id: project-0004
  from_ruling: ruling-0031          # the accepted proposal that created it
  objective_id: null                # optional link up to the objective graph
  template: null                    # e.g. "office-room-v2" when instantiated from one
  summary: "Recover the hematite in the Manager's Office ring and finish its walls"
  status: active | done | abandoned # derived from steps, except abandoned (a decision)
  because: string                   # one line, always shown
```

**Step** (defined inside the project record; its state changes are
separate records, see 4.4):

```yaml
step:
  id: project-0004/s2
  tool: construction.build          # a real tool id from TOOLS.yaml; never free text
  args: {kind: Wall}                # the tool's own kind argument
  targets:                          # a target SET, code-side, see 4.3
    from_step: project-0004/s1      # data flow: s1's DONE targets become s2's
    select: done                    #   (or: a zone ring, a site handle, a query)
  requires: [project-0004/s1]       # finish-to-start
  trigger: all_done                 # all_success (default) | all_done
  prefer_after: []                  # soft, scheduling only
  guards: default                   # from data for this tool (4.2), plus any extras by name
```

**Target** (the unit a guard can hold): one tile, one building, one order,
depending on the tool. Each target has its own state inside its step, so
"four of five walls issued, one held" is representable. Targets are named
code-side by opaque handles (the blueprint verb's `site-N` pattern), never by
a coordinate in any field an agent sees.

**DF job**: not a node. A step's `issued` record lists the DF job ids and
building ids it caused (the construction tool already returns enough to get
these), and the reconciler follows them. Jobs DF creates or recreates on its
own are attached by matching building id or tile, and jobs we did not cause
are never adopted.

Why not make DF jobs nodes: they are ephemeral (cancelled and recreated by
the game), they sometimes do not exist yet when we act (a dig designation has
no job until a miner claims it, which is exactly the `dig_progress` false
positive in the 2026-09-24 register row), and at fort scale there are
hundreds. A graph whose nodes the game can delete or duplicate would be
reconciled forever.

### 4.2 Edges, and what each one means

| Edge | Meaning | Checked by | Blocks? | State |
|---|---|---|---|---|
| `requires` | Step B may not issue until step A is done (FS). `trigger: all_done` relaxes "done" to "finished, with any outcome" | Code, from the record | Yes, whole step | **Recorded** |
| **guard** | Target T of step B must not be issued (or, if already issued, must be held) while predicate P is true of the world | Code, live read, per target, jointly over the step | Yes, per target | **Observed**, with the hold itself recorded |
| `prefer_after` | Prefer to issue B after A; never blocks | Overseer's scheduling | No | none |

**Guards are a closed vocabulary in data, not code in each tool.** One file
(say `scripts/dfhack/guards.yaml`, or a section of `TOOLS.yaml`) lists each
guard kind and which tools and kinds it attaches to by default. First entry,
generic by construction:

```yaml
keeps_access:
  applies_to: [construction.build, blueprint.apply:build]   # any construction kind
  protects:                                                 # what must stay reachable
    - exposed_tiles: {vein_status: ore_or_gem}             # isOre()/isGem(), the fixed classifier
    - pending_designations: {kind: [dig, channel, smooth, engrave]}
  hidden_tiles: ignore                                     # armok rule: a player does not know them
  evaluate: jointly_over_step                              # all of the step's constructions at once
  hold_policy: keep_orthogonal_approach_first              # deterministic choice of which target to hold
  reason_text: "would cut off {what} that is still to be worked"
```

The next guard costs one entry and one predicate function: say
`not_over_pending_designation` (suspendmanager's `ERASE_DESIGNATION`, for
furniture placed before smoothing finishes, which the blueprint verb's order
guard handles today for its own phases only), or `stock_at_least` (DF's own
`item_conditions` shape) for a work-order step. **The honest cost line:** a
new guard *kind* is new code (a predicate); attaching an existing guard to a
new tool or kind is data. That meets `CLAUDE.md`'s generalisability rule in
the same way `workjob` does: nothing in a guard names hematite, walls or
offices.

**Three-valued evaluation**, reused from the 2026-09-22 CQL recommendation:
a guard returns `pass`, `hold`, or `unknown`. `unknown` (a read failed, a
reachability query timed out) holds the target and says so; it never
defaults to pass. Hidden tiles are not `unknown` for `keeps_access`, they
are simply outside what the guard may consider, the same rule `prospect`'s
default mode follows (`docs/ARMOK-RULINGS.md`).

### 4.3 Target sets, including ones that grow

A target set is one of: a zone's ring (today's `construction` tools), a
blueprint site handle's cells, another step's done targets (`from_step`),
or a **query** re-evaluated on each reconcile. The last one is Bazel's
dynamic dependency discovery applied to the map: "exposed economic ore
connected to zone 13's ring" yields one tile today and more as each mined
tile reveals its neighbours. A query-targeted step is `done` when its query
returns empty (and the last issued targets are done), or when the Overseer
closes it with a reason. That is how "mine the whole vein" (owed item 2 of
the 2026-09-24 ore register row) becomes expressible without knowing the
vein's extent in advance, and without reading hidden tiles.

### 4.4 State: recorded, observed, and drift

**Recorded state** (append-only records in `dfqueue`; current state is a
fold over them, materialised in a table like `predictions` is today):

| Target / step state | Meaning | Written by |
|---|---|---|
| `waiting` | a `requires` edge is not yet satisfied | code, at project creation |
| `ready` | prerequisites satisfied, not yet issued | code |
| `held` | a guard says no; carries guard kind, reason text, the protected target's handle | the tool at designation time, or the reconciler |
| `issued` | tool call made; DF designations/jobs/buildings listed | **`executed` record** (reused, see below) |
| `done` | completion recorded, with the observation that justified it | Overseer via `executed`, or code on an unambiguous observation |
| `failed` | tool refused or the game cancelled and it was not retried | `executed` with outcome `failure` |
| `abandoned` | deliberately dropped (the vein is not worth it; a better access route chosen) | Overseer, with a reason; Airflow's `removed`/`skipped` distinction kept |

**Reusing `executed`, per the user's ruling.** Today an `executed` record has
`ruling_id`, `actions` (tool, outcome, detail) and `notes`. The smallest
extension: an optional `step_id`, and per-action optional `targets` (handles)
and `game_refs` (job and building ids, code-only fields like the coordinate
rule already requires). No new kind for "we did it". The `executed` record
already arms the proposal's prediction window, so a project's prediction
starts at its first issued step, which is the right semantics.

**Observed state** (new record kind `observation`, written only by code, the
conductor role, never by a model): per target, `consistent`, `contradicted`
or `not_observable`, the reason, and the game tick. Observations never
change recorded state. When they disagree, the step shows **drift**, and
triage wakes the Overseer.

**What "done" means, per target kind** (this is where the vein subtlety
lands):

| Target | Recorded done when | Observation can confirm | Observation cannot confirm |
|---|---|---|---|
| mined ore tile | Dig job for it completed (event hint) and the tile reads open | open, and floor material is the vein mineral | who mined it; whether the ore boulder was kept; whether it was *our* job |
| constructed wall | Building's construction stage completes / tile becomes a constructed wall | tile is a construction; `original_tile` (if confirmed readable) | nothing important |
| furniture placed | building exists and is complete | yes | whether it was later deliberately removed or tantrumed (both read "gone") |
| zone / owner | zone exists, owner set | yes | intent (deferred versus forgotten) |
| direct workshop job | job left the list **and** the product appeared | product count rose | job left the list alone is ambiguous: completed and cancelled look the same, which is why the event hint and the product read are both needed |

**Rollback.** DF crashing reloads the last save, so the world can go
backwards while our records do not. The reconciler compares the fort's
current absolute tick to the tick on each target's latest record; anything
recorded after the current tick is marked `contradicted: world_rolled_back`
and re-observed. The same rule makes the save-reload test harness
(`docs/ARMOK-RULINGS.md`, 2026-09-25, harness only) safe, provided the
harness snapshots and restores the queue database alongside the save; if it
does not, records from a discarded branch would leak into the live fort's
history. Flagged, not designed further here.

### 4.5 Where it is stored

**Recommendation: in `dfqueue`, the same SQLite database, as new record
kinds (`project`, `step_update` if needed, `observation`) plus the extended
`executed`.** Reasons:

- It is already the audit log and the write-ahead log (`docs/AGENT-ARCHITECTURE.md`
  §4 and §9); a project is literally the missing `plan` record.
- One writer, one transaction model, one export to JSONL for the public
  report, one XML render for prompts.
- Rulings and executions already reference each other there; steps need
  exactly those references.

Alternatives considered:

- **A sibling store** (a new SQLite next to the queue). Cleaner schema
  separation, but it splits the audit narrative the queue exists to keep in
  one place, and `executed` would have to live in both. Rejected.
- **`dfhack.persistent` inside the save**, as the blueprint verb stores
  `site-N` handles. Its one real advantage: it rolls back with the world on a
  crash, so graph and world can never disagree about a rollback. Its
  disadvantages are larger: no history (a rollback silently erases the
  record that work was done and undone), no queries, not reachable from the
  conductor on VM 106 without a tool call, and agent-visible state would
  live in two places. Rejected as the system of record; **the per-target
  handle table (handle to real tile) should stay code-side in the save**,
  as the blueprint verb already does, because coordinates must not live in
  the queue.
- **Files** (YAML per project). Only for templates (see 5.4), never for live
  state.

---

## 5. The four existing "unit of work" shapes, mapped

### 5.1 The zone-13 case, end to end

**What actually happened** (2026-09-24 to 09-28, from the register and
`Working.md`): the office's ring was smoothed including five hematite tiles;
`construction.mine-vein 13` designated three (a dwarf had already dug two);
`construction.build 13 wall` then designated all five walls; a separate
ad hoc script found ore beyond the ring; a human found building 22's job and
suspended it by raw script.

**The same sequence under this model:**

1. **The Architect proposes** (`type: room_finish`, or the existing
   `smoothing`), with a step list. With a template (5.4) the steps come from
   data; here, for a recovery, the Architect writes them:
   - `s1`: `construction.mine-vein`, targets = zone 13 ring, ore tiles only.
   - `s2`: `construction.build`, `args: {kind: Wall}`, targets
     `from_step: s1, select: done`, `requires: [s1]`, `trigger: all_done`.
     Guards: default for `construction.build`, which includes `keeps_access`.
2. **The Overseer accepts** (`ruling`), and the store creates
   `project-0004` with `s1 ready`, `s2 waiting`.
3. **The Overseer issues s1**: `construction.mine-vein 13`, real. `executed`
   records three targets `issued` with their dig designations, and two
   targets whose tiles were already open. Those two are recorded as
   `done, not_ours` (open floor over hematite, no job of ours), not silently
   folded in: the record says we did not mine them.
4. **The fort runs.** The reconciler, each cycle, sees the three dig
   designations become jobs, then sees the tiles open (and, if wired, the
   `JOB_COMPLETED` hints). It writes observations; the Overseer (or code, for
   an unambiguous "designated tile now open over the vein mineral") records
   the three targets `done`. `s1` is now done.
5. **Also on that reconcile**: a query guard input changes. Mining the ring
   tiles exposed the hematite tile west of building 22's future site. The
   reconciler records an observation "exposed economic ore adjacent to
   project-0004's area, not in any step's targets", which is a triage wake
   reason (a new fact the plan did not foresee), not a silent event.
6. **`s2` becomes ready. The Overseer issues it.** `construction.build`
   receives its five targets from `s1`'s done list (not from "whatever is
   open on the ring", which closes the doorway hazard in §3 item 4). Before
   designating anything, it evaluates `keeps_access` **jointly over all five
   planned walls**: with all five built, the exposed ore tile has no open
   approach left. The hold policy keeps its orthogonal approach: target 5
   (building 22's tile) is `held`, reason "would cut off exposed ore that is
   still to be worked". Targets 1 to 4 are designated. `executed` records
   four `issued`, one `held`. **Building 22 is never created, so there is no
   job 2705 to find and suspend by hand, and nothing for `suspendmanager` to
   un-suspend.**
7. **`s2` is now `partially issued, 1 held`**, and the project cannot be
   `done` while a target is held. The Overseer's next prompt shows exactly
   one line for it: "project-0004: walls 4 of 5 issued; 1 held, keeps_access
   (exposed hematite beyond the office wall)."
8. **Someone decides what to do about the ore.** The Architect (or the
   Overseer) either:
   - adds `s3`: `construction.mine-vein`, targets = query "exposed economic
     ore reachable through this project's held target", re-evaluated each
     reconcile. As each tile is mined and its neighbours revealed, the query
     grows (dynamic discovery, §4.3). `s2`'s held target stays held while
     that query is non-empty, because the approach is still needed; or
   - proposes a different access route to the vein (a corridor from
     elsewhere) so the office wall can close now; or
   - abandons the vein with a reason, which releases the hold as a recorded
     decision.
9. **When the guard passes** (vein exhausted or access rerouted), the
   reconciler records the guard's change, `s2`'s target 5 goes `ready`, the
   Overseer issues it, and the project completes.

**The one-line version**: the tool would have refused building 22 at
designation time, with a reason, and the project record would have kept the
refusal visible until someone decided about the vein.

**What step 6 needs that does not exist today**: a reachability query of the
form "after these N tiles become walls, is this tile still reachable by a
miner", over a bounded area. The shared tri-state reachability helper
(`df-overseer-reachability.lua`, `CLAUDE.md` status block) is the natural
home; whether it can evaluate a hypothetical ("as if these tiles were
walls") without mutating the map is **not verified** and is the main
technical risk of the guard-first build.

### 5.2 DF's native jobs (`stuckjobs`, `workjob`)

- A `workjob.queue` call is a one-target step whose target is the workshop
  job. `issued` lists the DF job id; `done` needs both the job leaving the
  list and the product appearing (table in 4.4), because a cancelled job also
  leaves the list.
- `stuckjobs` becomes a **reconciler input**: a step target whose job has no
  worker for long enough gets an observation `stalled`, the same honest
  label `stuckjobs` already uses, now attached to the step that caused it,
  so the Overseer sees "project X is stalled because its job has no worker"
  rather than an anonymous stuck job.
- Jobs the fort generates on its own (smoothing jobs from designations,
  `PlantSeeds`, hauling) are not adopted. They matter to guards (a guard sees
  the whole world, like `suspendmanager` does) but not to the graph.

### 5.3 The proposal, ruling and execution queue

Not a new concept layered on top, and not the queue absorbing "job" as a
new thing either: **the queue gains the layer it already said it lacked.**

- proposal (decision requested) -> ruling (decision) -> **project** (the
  accepted intent, with steps) -> `executed` (per step, reused) ->
  **observation** (code's view of the world, new).
- A proposal with no steps block is a one-step project, so every existing
  proposal type keeps working unchanged.
- The Overseer's charter already says "Writes the ordered plan to the queue
  **before** acting, then marks each step done as it goes"
  (`agents/overseer/role.md`). Today that sentence has no record to write.
  This is that record.

### 5.4 Manager work orders, and room templates

- **Work orders**: a step whose DF-side artefact is an order, not a job.
  Its `issued` record names the order id; the reconciler reads `amount_left`
  and the jobs that carry that `order_id` (`df-overseer-stuckjobs.lua`
  already attributes jobs to orders). Because orders are inert on this fort
  (the user's 2026-09-24 ruling), a work-order step will simply sit `issued`
  with an observation `not_progressing`, which is honest and needs no
  special case. **Later option, not now:** when two order-steps are linked
  by `requires`, the tool could also write DF's native `order_conditions`
  (`Completed`) so the game enforces it too. Worth doing only once orders
  dispatch at all.
- **The room build order** (the 2026-09-28 agenda item this brief widened):
  a template in `blueprints/templates/` gains a `steps:` block in its
  `.yaml` metadata, generic by rule, which instantiates into a project when
  the Architect proposes the room. For the office template, roughly: dig
  shell -> finish (branch per tile, decided by what the dig revealed: smooth
  stone, or mine ore then construct wall) -> furniture -> zone -> owner. The
  "branch per tile" is a target-level split inside one step, not two
  alternative graphs. This is the FHIR PlanDefinition-to-CarePlan split the
  2026-09-22 research already recommended for objectives, applied one level
  down.

---

## 6. What changes for the agents

| Role | Change |
|---|---|
| **Architect** | Proposes projects (a steps block) for anything multi-step, instead of one action per proposal. Declares `requires` edges and target sets. **Cannot remove a default guard**; may add one from the vocabulary by name. Gets a read tool for project status to avoid re-proposing held work. |
| **Quartermaster** | Same, for work-order and workjob chains (barrels before brewing is the live example from 2026-09-28: `MakeBarrel` then the brew job, `requires`). |
| **Overseer** | Instantiates projects on accept; issues steps whose prerequisites are done, in its own priority order; **the WIP limit counts active projects**; can release a hold only by recording a reason (an override is a decision, audited like a ruling); can abandon a project or target with a reason. Its "Execution" charter paragraph becomes literally true. |
| **Conductor** (code) | Runs the reconciler each cycle: read-only reads, writes `observation` records, re-asserts holds (so a hold survives anything that clears the suspend bit), and adds triage wake reasons: a target moved `held -> ready`, drift on a done target, a world rollback, a new exposed fact near an active project. |
| **Consultant** | None, beyond being asked whether a guard's rule is right (for example, whether diagonal mining is possible). |

**Who creates a graph:** advisors propose it, the Overseer's ruling creates
it, code maintains its state. **Who asks "is this blocked":** code, at the
tool (refuse and record) and in the reconciler; the Overseer reads the answer,
it never computes it. That keeps `docs/AGENT-ARCHITECTURE.md` principle 1's
split: code produces the facts and the priced choices, agents judge.

**Prompt size:** the Overseer sees one line per active project (status,
counts, the top blocker's reason), and full detail only for projects with a
state change this cycle. Never the whole graph, the same rule §6 of
`docs/AGENT-LOOP.md` sets for objectives.

**Constraints checked:**

- **No armok capabilities** (`CLAUDE.md`, `docs/ARMOK-RULINGS.md`): guards
  read only what a player can see. Hidden tiles are outside every guard's
  scope; the "26 ore tiles" count must not be reproducible by any
  agent-facing tool. Holding a job uses the vanilla suspend action (a
  player's button), or better, not designating at all. Reachability is
  already accepted as fair (the threat detector admits by it). Nothing here
  needs a power a player lacks.
- **Tools must be generalisable**: guards are data entries over game-derived
  classes (`isOre`/`isGem`, designation kinds, construction kinds), attached
  to tools by data. Step kinds are the existing generic tool verbs. No
  per-room, per-mineral or per-workshop branch is proposed anywhere.
- **Design commitment #1** (no map shown to a model): targets are handles;
  reasons are relative prose ("beyond the office wall"); the existing
  coordinate filter in `dfqueue/schema.py` applies to every new text field.
- **Single writer**: unchanged. The reconciler writes only observations and
  re-asserts holds the Overseer's own records already established; it never
  issues work.

---

## 7. Scope: one graph, per zone, or per project

**Recommendation: one store per fort, organised into projects, with guards
evaluated fort-wide.**

- **Not per room or zone.** The failure that started this crossed zone 13's
  boundary: the ore was outside the office, the harm was to the office's
  wall. A per-zone graph cannot express "this wall waits on that vein".
- **Not one monolithic fort graph as the unit of work.** The objective graph
  already owns "what the fort is for"; a second whole-fort graph at job
  level would grow without bound and invite showing it to a model.
- **Per project** is the unit a human or agent declares, rules on, limits
  (WIP), and reads. Edges may cross projects (`requires` another project's
  step) because real dependencies do, but that should be rare and is shown
  explicitly.
- **Guards are not per project.** A guard asks about the world, and the world
  includes other projects' work, the fort's own jobs, and whatever a human
  did on VNC. `suspendmanager` evaluates every construction job for the same
  reason.

**What I am not confident about:**

1. **Whether a hypothetical reachability query is cheap and correct.** The
   whole guard-first step depends on "if these tiles were walls, could a
   miner still reach that ore". Not checked against the reachability helper's
   actual API.
2. **Diagonal mining.** Whether a miner can dig from a diagonal neighbour
   decides whether building 21 was also part of the problem. Unverified; a
   Consultant ask or a wiki-mirror read would settle it.
3. **Whether target-level state inside steps is too fine.** It is needed for
   "4 of 5 issued, 1 held", but a 60-tile dig step would carry 60 target
   rows. Probably fine in SQLite; possibly noisy in the audit export.
4. **Whether DeepSeek advisors will write sensible step lists.** Nothing has
   tested an agent composing a multi-step proposal. Templates (5.4) reduce
   how often they must.
5. **Foreign work.** If a human designates a wall on VNC that seals ore, the
   guard sees it but the graph does not own it. I recommend report-only
   (an observation, a wake), never touching work we did not cause. The user
   may want otherwise.
6. **Folding versus a mutable state table.** I recommend append-only records
   folded into a materialised table (the `predictions` pattern). A simpler
   mutable table is tempting; it would lose the history the public report
   wants.
7. **`original_tile` on 53.16** and the manager-order condition struct were
   read from df-structures `master`, not the install's own tag.

**Build order I would propose, each independently useful:**

1. `keeps_access` as a tool-layer refusal in `construction.build` and
   `blueprint apply`'s build phases, plus `build` taking explicit targets
   rather than "every open ring tile". Would have prevented building 22 and
   the doorway hazard with no schema change. (Also owed: `building.build`'s
   material filter still uses `economic_uses`, `Working.md`; separate fix.)
2. `project` records and step-aware `executed` in `dfqueue`, with a
   `project.status` read tool. Makes holds and partial progress visible and
   durable.
3. The reconciler in the conductor. Makes drift, rollback and held-to-ready
   transitions automatic wake reasons.
4. Template `steps:` blocks, starting with the office and bedroom-cell
   templates.

---

## 8. Sources

Read in source (high confidence):

- DFHack `plugins/suspendmanager.cpp` at tag `53.16-r1`, downloaded from
  `raw.githubusercontent.com/DFHack/dfhack/53.16-r1/plugins/suspendmanager.cpp`;
  reason enum lines 67-79, `refresh()` and `do_cycle()` lines 648-721.
- DFHack `hack/lua/plugins/suspendmanager.lua` and
  `hack/docs/docs/tools/suspendmanager.txt`, read on VM 103's install.
- df-structures `df.workquota.xml` (`manager_order_condition_order`,
  `workquota_order_condition_type`: `Activated`, `Completed`) and
  `df.event.xml` (`construction.original_tile`), both from `master`, not the
  53.16 tag.
- df-structures `df.job.xml` (`job_flags.suspend`, `do_now`).
- This repo: `scripts/dfhack/df-overseer-construction.lua`,
  `df-overseer-blueprint.lua` (header, order guard, persistent site handles),
  `df-overseer-stuckjobs.lua`, `df-overseer-workjob.lua`,
  `df-overseer-orders.lua`, `df-overseer-ledger.lua`, `dfqueue/schema.py`,
  `dfqueue/README.md`, `docs/AGENT-ARCHITECTURE.md` §4, §7, §9, §10,
  `docs/AGENT-LOOP.md` §4 and §6, `docs/ARMOK-RULINGS.md`,
  `agents/ROSTER.yaml`, `agents/overseer/role.md`.
- df-ai, through `research/2026-09-24-df-ai-fort-planner.md` §Q5 and §Q6
  (that report's own source read at `701ea36`; not re-read here).

Live reads on VM 103, read-only, fort paused, tick 209571:

- `dfhack-run enable`: `suspendmanager off`, `buildingplan on`,
  `autolabor on`.
- Buildings 18 to 22 and their jobs (table in §3); building 22
  `isPlannedBuilding false`, job 2705 suspended, one item, no worker.
- Tiletype shape and material around the exposed ore tile, and hidden flags.
- `df-overseer-surface vein-material 13`: 5 `ore_or_gem HEMATITE`, 11
  `not_mineral`, on tiles now open.

Primary documentation, fetched and quoted (high confidence for the quoted
wording):

- GNU make manual §4.8, Empty Target Files to Record Events,
  https://www.gnu.org/software/make/manual/html_node/Empty-Targets.html
- Apache Airflow, Tasks (task instance states),
  https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/tasks.html
- Apache Airflow, DAGs (trigger rules),
  https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html
- Terraform, Purpose of state,
  https://developer.hashicorp.com/terraform/language/state/purpose
- Terraform, `plan` command (refresh, refresh-only),
  https://developer.hashicorp.com/terraform/cli/commands/plan
- Kubernetes, Controllers, https://kubernetes.io/docs/concepts/architecture/controller/
- Kubernetes API conventions (level-based, conditions),
  https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md
- Bazel, Skyframe, https://bazel.build/reference/skyframe
- Dagster, asset observations,
  https://docs.dagster.io/guides/build/assets/metadata-and-tags/asset-observations
- Unity, job dependencies, https://docs.unity3d.com/Manual/job-system-job-dependencies.html
- Microsoft Project, Link tasks in a project,
  https://support.microsoft.com/en-us/office/link-tasks-in-a-project-31b918ce-4b71-475c-9d6b-0ee501b4be57

Summary-level only (moderate confidence): Dagster's asset versioning page
(https://docs.dagster.io/guides/build/assets/asset-versioning-and-caching);
the statement that staleness compares recorded versions rather than stored
data came from the fetch tool's summary, not a quoted sentence.

## 9. Not verified

- Whether a DF miner can dig a wall tile from a diagonal neighbour.
- Whether the reachability helper can answer a hypothetical ("as if these
  tiles were walls") without touching the map.
- `construction.original_tile` and `order_conditions` on the 53.16 install
  itself (read from df-structures `master`).
- How often `suspendmanager` cycles, and whether `buildingplan` would ever
  re-suspend or unsuspend a job it no longer plans (it reports building 22
  as not planned, so probably not, but not read in its source).
- Airflow pools or any other surveyed system's native "must not run
  concurrently" primitive: not read; guards are modelled on `suspendmanager`
  and Kubernetes conditions instead.
- Nothing here was prototyped. The model is untested against a real project
  of more than the one worked example.
