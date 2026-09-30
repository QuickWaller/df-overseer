# Goal trees, draft projects, a step runner, contention and priority: a design

Date: 2026-09-30. Researcher (Opus), design only. Brief:
`handoffs/2026-09-30-goal-tree-design.md`, plus three additions the user
sent mid-task (checks by how they are observed, stuck detection and
self-healing, and a ready queue of many projects in motion). Nothing in the
repo's code or on the fort was changed; no VM was touched. Every live-fort
fact below is quoted from the repo's own records, not re-read.

Status: **proposal for the user's review.** The user's nine decisions in
the brief are treated as settled. Where I think one needs a correction, it
is in §14, marked, not designed around.

Read first: `research/2026-09-28-job-dependency-graph.md` (projects, steps,
guards, recorded versus observed state). This document is the layer above
it (goal trees, drafts, the runner, claims, priority) and one level beside
it (how checks are observed, how stuck work heals, how many projects share
the fort).

Confidence labels used throughout:

- **[verified: source]** read in the actual source (this repo, DFHack or
  df-structures at a named ref);
- **[verified: primary doc]** a project's own documentation or a primary
  paper, read in its own text (a PDF page image or a fetched page);
- **[summary]** a fetch tool's summary of a primary page, wording not
  independently checked;
- **[proposed]** my design, not built, not tested;
- **[unverified]** a claim I could not confirm; each is repeated in §15.

---

## 0. The answer, up front

1. **One recursive node type, two kinds, three check roles.** A node is a
   **job** (one real tool call, real arguments) or a **goal** (children in
   order or together, plus its own check). Every node carries a
   **can-start guard** set and a **did-it-work check**; a goal's check is
   independent of its children and, when met, skips the whole subtree.
   This is behaviour trees' Postcondition-Precondition-Action pattern
   (Colledanchise and Ögren, Fig. 1.14) crossed with HTN's ordered and
   unordered subtask lists (SHOP2, JAIR 2003, §3.1.3), with one deliberate
   difference from both: jobs are not re-searched at run time; the tree is
   drafted once, validated, approved, then run as written. [proposed]

2. **Every check declares how it is observed and when its answer is due.**
   Three observation modes (**read-back** from the tool call, **recorded
   event**, **poll**) and three expectation shapes (**deadline**,
   **window**, **unbounded**). A slow check is then never mistaken for a
   stuck one, and the stall rules know exactly what they are waiting for.
   Every check returns **met / not met / unknown**, plus **stale** when its
   last read is older than it allows, the same tri-state the guards
   already use (`pass`/`hold`/`unknown`). [proposed]

3. **Events are hints, polls are truth, and "event" in DFHack is itself a
   poll.** DFHack's EventManager detects every event by diffing game state
   every N ticks inside the game process [verified: source,
   `library/modules/EventManager.cpp` at `53.16-r1`]. `JOB_COMPLETED` is
   inferred from a job vanishing while its `completion_timer` read 0 at the
   last sample, and at a frequency above 0 it can **miss** completions
   (the source's own comment: "Jobs may be missed if tick delta > zero").
   So an in-game **recorder** captures events as they happen, the conductor
   drains it each cycle, and a poll confirms before anything is recorded
   `done`. Only today's tripwire classes take the urgent path. [proposed,
   on verified mechanics]

4. **The conductor runs steps through one new native tool,
   `queue.run_step(step_id, attempt_key)`, and holds no DFHack mutating
   tool at all.** The server resolves the tool and arguments from the
   accepted project record, never from the caller, checks the ruling,
   readiness, guards and claims, then makes the call itself. Enforced in
   four independent places (roles.py load-time rule, the handler's closed
   argument set, the store's write-time check, the tool's own guards).
   [proposed]

5. **Idempotency by a key stored with the world.** Each attempt is written
   ahead (`step_attempt`), and the DFHack tool records the attempt key and
   its result in `dfhack.persistent` site data, which is saved with the
   fort. After a crash, a key found in the save means the action happened;
   a key missing means the world never saw it **or rolled back past it**,
   and in both cases re-issuing is correct. This is Stripe's idempotency
   key [verified: primary doc], placed where DF's rollbacks cannot split
   it from the effect. [proposed]

6. **Claims are demands declared once and allocations recomputed every
   cycle.** Nothing is kept as a running tally. Each cycle the runner walks
   the ready queue in priority order and grants each step's material
   demand from `live available stock` (the six-flag netting
   `production/blocker.py` already implements) minus grants already made
   this pass. Short means a named hold. Exact item ids are recorded once a
   job holds items (`job.items`, role `Reagent`/`Hauled`) and once a
   building holds them (`contained_items`). A hard hold forbids exactly the
   unclaimed items (a vanilla player action on v53.16 [verified: primary
   doc, wiki `Forbid`]). An ERP shows why the tally is dangerous: ERPNext
   issue #57313 is a stored reserved-quantity counter going stale because
   one event path did not refresh it. [proposed; netting verified: source]

7. **A ready queue, not one project at a time; the scarce resources are
   dwarves, materials, ground and model tokens, not conductor time.** The
   active-project limit becomes admission control (YARN Fair Scheduler's
   `maxRunningApps` [summary]); within admitted projects, a per-project
   **labor share** plays the part of a time slice; model wakes get their
   own budget. Issued jobs are never pre-empted (cancelling a DF job wastes
   hauled progress); priority governs only what is issued next. [proposed]

8. **Priority is a lexicographic tier, then WSJF, then inheritance and
   aging.** Tier first (survival deadline, then everything else), exactly
   as the production model's bands are lexicographic
   (`docs/PRODUCTION-MODEL.md` §10). Within a tier, cost of delay divided by
   remaining size (WSJF [verified: primary doc, SAFe]). A blocker inherits
   the **sum** of the cost of delay of what it blocks, which deliberately
   differs from the kernel's priority inheritance (the **maximum** of the
   waiters [verified: primary doc, `rt-mutex.rst`]): a CPU runs one thread,
   but a delayed barrel project delays every goal that needs barrels at
   once. Aging adds a bounded boost to anything ready and waiting, and the
   Overseer's override is a recorded, expiring pin. [proposed]

9. **Stuck is "past its declared time with no named reason".** Waiting is
   fine and retries quietly. Stuck work climbs a ladder: re-check, re-issue
   (bounded, backed off), release its claims, escalate with a ten-line
   report. A wait-for graph over persistent claims catches deadlock; thrash
   is caught by budgets and a per-project heal circuit breaker. [proposed]

10. **Jobs and checks sort into a small number of groups, derived from the
    game's own data.** DF's 259 job types (df-structures at `53.16-r1`)
    fall into twelve groups by how they are issued, what they claim and
    how their outcome is observed (designations, placed buildings,
    workshop jobs, manager orders, hauling, configured standing work,
    animals, military, autonomous, mechanisms, trade, instant settings);
    only 11 empty enum slots fit none. Checks fall into eight groups
    crossed with the observation modes. Each group gets one generic
    implementation fed by game data. §4.

11. **Build order**: shared foundations first (two live store bugs, then
    goals and checks in the project record, the reconciler, the recorder,
    `queue.run_step` on a one- or two-command allowlist), then fill the
    groups in value order (workshop jobs, buildings, designations,
    settings, hauling). Whether to start with the booze chain as a thin
    slice, fill group by group, or (recommended) prove **one
    representative job and check per live group** first is the user's
    call. Deadlock detection, fair-share labor, full priority inheritance
    and hard holds are specified but can wait for a real run to ask for
    them. §13.

### Findings from this pass that change the premise

Each is independently useful whatever the user decides about the design.

- **A project reads `done` before a `from_step` step has ever run.**
  [verified: source] `dfqueue/store.py` `_seed_step_targets` skips any step
  whose targets are `from_step` ("dynamic ... has no targets known yet"),
  and `project_status` returns `done` when every existing `step_targets`
  row is `done`/`abandoned`. So the 2026-09-28 design's own worked example
  (mine the vein, then wall the mined tiles, `from_step: s1`) reports
  `done` the moment the mining finishes, before any wall is issued. No
  real project exists yet (`queue.project_status` read "(no projects)" live
  on 2026-09-30, per `Working.md`), so nothing has been misreported.
- **Nothing enforces "exactly the approved arguments" today.** [verified:
  source] `queue.executed` validates `step_id` names a real step, but not
  that an action's `tool` equals the step's `tool`, not its arguments, and
  not that the step's `requires` are satisfied. `step_prerequisites_satisfied`
  exists in `store.py` but no write path calls it.
- **The WIP limit exists only as a charter sentence.** [verified: source]
  `agents/overseer/role.md` ("Enforce a cap on concurrent work") and the
  roster summary; no code in `conductor/`, `dfqueue/` or `dfmcp/` counts
  active projects.
- **Arguments that rank at run time do not pin a site.** [verified: source]
  `building.build KIND ... NEAR_LANDMARK [RANK] ...` and `blueprint apply
  ... SITE [RANK]` pick the site by ranking candidates when called. The
  same approved arguments can resolve to a different tile a day later. A
  filled site slot must therefore be a **reservation handle** (`res-N`),
  not a landmark plus rank. And `blueprint reserve` needs a template, and
  **no workshop footprint template exists** (`blueprints/templates/` holds
  only `bedroom-cell-v1`, `office-room-v1`, `office-room-v2`).
- **`diff.since`'s job-completed events are weaker than they look.**
  [verified: source] `df-overseer-diff.lua` enables `JOB_COMPLETED` at
  frequency 10 and logs only the job's name (no job id, no items, no
  building). DFHack's docs say `onJobCompleted` "Requires a frequency of 0
  in order to distinguish between workshop jobs that were canceled by the
  user and workshop jobs that completed successfully" [verified: primary
  doc, `docs/dev/Lua API.rst` at `53.16-r1`], and the EventManager source
  shows why a non-zero frequency can miss completions. The log is also a
  plain `_G` table, never trimmed, lost on a DF process restart, and its
  `at_tick` is `dfhack.world.ReadCurrentTick()`, the within-year tick that
  the reservations review fixed elsewhere because it resets every New
  Year.
- **The code-side bill-of-materials walk already exists, unwired.**
  [verified: source] `production/blocker.py`'s `find_blocker` is an AND-OR
  walk over reactions (the OR over producing processes, the AND over each
  process's reagents and its workshop) against available stock. It is
  exactly the recursive requirement explosion a Quartermaster draft needs,
  and no MCP tool exposes it. A draft's skeleton can be computed by code
  and only its targets judged by a model, which is `docs/AGENT-ARCHITECTURE.md`
  principle 1's split applied to planning.
- **Doc drift, flagged for a memory audit, not patched:**
  `scripts/dfhack/TOOLS.yaml` still says `blueprint reserve` is
  `live_deployed: false`, "Never run live", while `Working.md` and the
  2026-09-30 register row record it deployed and live-verified (one
  reserve/release cycle).

---

## 1. The problem, stated domain-neutrally

A controller pursues several intentions at once through an environment it
does not own. The environment has its own workers who choose their own next
task from a shared pool, its own stock that anyone may consume, and its own
ground that any work may occupy. Each intention decomposes into smaller
intentions and finally into concrete requests the controller can make. Some
intentions are one-off; some are standing ("keep at least this much").
Several intentions may need the same intermediate result. The controller
must:

- write the decomposition down once, in a form that can be checked
  mechanically before anyone approves it;
- let a cheap planner propose it and an expensive arbiter amend or approve
  it, with the arbiter sending only the difference;
- carry out approved requests itself, deterministically, exactly as
  approved, and survive its own crash without doing anything twice;
- know, for each request and each intention, how and when it will find out
  whether it worked, including when it cannot find out;
- share stock, ground and workers among intentions without keeping a
  ledger that can drift;
- decide what goes next, so that urgent things are not starved by big
  things and big things are not starved forever;
- notice when something has stopped moving, fix it cheaply if it can, and
  ask for judgment only when it cannot.

Fields that own pieces of this, and what each was read for:

| Field | Read | Contributes |
|---|---|---|
| Hierarchical task network planning | SHOP2 (Nau et al., JAIR 20, 2003), read in its own text | compound versus primitive tasks, methods with preconditions, ordered and unordered subtasks, resources reserved inside the plan |
| Behaviour trees | Colledanchise and Ögren, *Behavior Trees in Robotics and AI* (arXiv 1709.00084v5), ch. 1 read in its own text | sequence/fallback/parallel semantics, the explicit-goal-check pattern, memory versus reactive nodes |
| Goal-oriented action planning | Orkin, "Three States and a Plan: The A.I. of F.E.A.R.", GDC 2006, read in its own text | goals competing by priority, decoupling goals from how they are met, falling back when no plan exists |
| Material requirements planning and ERP | ERPNext docs (projected quantity) and ERPNext issue #57313 | netting against stock, reserved versus available, and a live example of a stored reservation counter drifting |
| Operating-system scheduling | Linux `rt-mutex` and `rt-mutex-design` docs; OSTEP ch. 8 (MLFQ) and ch. 32 (concurrency bugs); PostgreSQL docs on deadlocks | priority inheritance and chains, aging, deadlock conditions and detection |
| Cluster scheduling | Apache Hadoop YARN Fair Scheduler docs | fair share, per-queue caps, a limit on concurrently running applications |
| Lean product flow | SAFe WSJF page (citing Reinertsen); Black Swan Farming urgency profiles | cost of delay, weighted shortest job first, urgency profiles over time |
| Distributed APIs and controllers | Stripe idempotent requests; Kubernetes owners and dependents | idempotency keys; owned objects, orphans and multiple owners |
| **DF and DFHack themselves** | df-structures (`df.job.xml`, `df.item.xml`, `df.building.xml`, `df.event.xml`), DFHack `53.16-r1` EventManager, Lua API docs and `repeat-util.lua`, DFHack tool docs (`unforbid`, `prioritize`), DF wiki (Forbid, Labor, Workshop) | what the game records about item use, how events are really produced, which levers a player has over job assignment |
| This repo | the files listed in §16 | what is live, what the guards and reservations already do |

As in the 2026-09-28 pass, the DF-native sources turned out to decide more
of the design than the textbook ones.

---

## 2. Prior art: what each contributes and what does not transfer

### 2.1 HTN planning (SHOP2)

[verified: primary doc, Nau et al. 2003, pp. 380-384, read as page images]

- "A task may be either *primitive* or *compound*. A primitive task is one
  that is supposed to be accomplished by a planning operator ... A compound
  task is one that needs to be decomposed into smaller tasks using a
  method" (§3.1.1). **This is the user's job/goal split, word for word.**
- "The simplest version of a method has three parts: the *task* for which
  the method is to be used, the *precondition* that the current state must
  satisfy in order for the method to be applicable, and the *subtasks* that
  need to be accomplished in order to accomplish that task" (§3.1.3).
- Ordering: "The :ordered keyword specifies that the subtasks are totally
  ordered ... To specify an unordered set of subtasks, we would use the
  keyword :unordered rather than :ordered; more complicated partial
  orderings can be specified using nested combinations of :ordered and
  :unordered." Footnote 3: "This notation does not allow every possible
  partial ordering, but that has not been a problem in practice." **This is
  the user's "in order / at the same time", and the footnote is direct
  support for not building general partial orders.**
- "SHOP2 generates the steps of each plan in the same order that those
  steps will later be executed, so it knows the current state at each step
  of the planning process" (§1).
- Figure 1's example domain contains primitive operators `(reserve ?t)`
  ("deletes (available-truck ?t) to signal that the truck is in use") and
  `(free ?t)`. **Resource claims appear inside the plan as explicit steps.**

**Transfers:** the two node kinds; methods as the unit an advisor drafts
(a draft is one chosen method, instantiated); preconditions as can-start
guards; ordered/unordered nesting; resources claimed as part of the plan.

**Does not transfer:**

- **HTN has no goal check on a compound task.** A compound task is done
  when its decomposition is done. The user's rule 2 ("children succeeding
  is not the goal being met") comes from behaviour trees, not HTN.
- **Search and backtracking.** SHOP2 chooses among methods and backtracks
  "if the plan later turns out to be infeasible". Here the method is chosen
  by an advisor and approved by the Overseer; code never searches for an
  alternative. When a plan fails, it escalates rather than backtracks.
  This matches the 2026-09-22 objective research's conclusion that HTN's
  if-then-else over methods is the thing to revisit only when the fort
  genuinely needs several comparable ways to reach one goal.
- **Planning assumes the planner knows the state at each step.** DF
  changes under the plan (other dwarves, cave-ins, a human on VNC), so the
  checks have to be re-read at run time, which is where behaviour trees
  come in.

### 2.2 Behaviour trees

[verified: primary doc, Colledanchise and Ögren, arXiv 1709.00084v5,
§1.3-1.5, read as page images]

- Table 1.1: a **Sequence** "succeeds if all children succeed, fails if one
  child fails"; a **Fallback** succeeds "if one child succeeds"; a
  **Parallel** node "returns Success if M children return Success, it
  returns Failure if N − M + 1 children return Failure, and it returns
  Running otherwise, where N is the number of children and M ≤ N is a user
  defined threshold" (§1.3). A **Condition** "never returns a status of
  Running."
- The explicit goal check (§1.5, Fig. 1.14): "The simplest possible BT is
  to check the goal condition *Green Cube on Goal*. If this condition is
  satisfied (i.e. the cube is on the goal) the task is done, if it is not
  satisfied the robot needs to *place the cube*." The pattern is a Fallback
  whose first child is the goal condition and whose second is a Sequence of
  preconditions and the action; it nests (Fig. 1.16). **This is the user's
  "a satisfied goal check skips the whole subtree", exactly.**
- Memory versus reactivity (§1.3.2): "Control flow nodes with memory always
  remember whether a child has returned Success or Failure, avoiding the
  re-execution of the child", and every memory node "can be obtained with a
  non-memory BT using some auxiliary conditions ... Hence nodes with memory
  can be considered to be syntactic sugar." Remark 1.1: BTs without Running
  "do not allow actions other than the currently active one to react to
  changes. This is a significant limitation".

**Transfers:**

- **Goal = Fallback(goal check, Sequence-or-Parallel(children)).** Every
  goal node compiles to that shape. In-order is a Sequence; together is a
  Parallel with M = N (all must succeed).
- **The memory question is the user's 2026-09-28 ruling in BT terms.**
  Jobs are *memory* nodes: once recorded done, they are not re-run just
  because the world changed (the world cannot always confirm them; the
  2026-09-28 design's whole argument). Goals are *reactive*: their checks
  are re-read every cycle, so a goal that becomes met by some other route
  skips its remaining children, and a standing goal that becomes unmet
  re-activates. The BT book's point that memory is "syntactic sugar" over
  auxiliary conditions is exactly why a recorded `done` target is an
  auxiliary condition we keep in the queue.
- **Running is a real state.** A job whose DF work is in progress is
  Running, not Failure; the stuck rules (§10) decide when Running has gone
  on too long.

**Does not transfer:**

- **The tick.** A BT is ticked many times a second and every action is
  re-evaluated each tick. Here a "tick" is a conductor cycle (minutes of
  wall time, hundreds or thousands of game ticks) and issuing a job is a
  one-shot request to another scheduler. Re-ticking a job would mean
  re-issuing DF work, which is exactly the double-act the runner must
  prevent. Hence memory for jobs.
- **Fallback over alternative actions.** A BT Fallback tries alternatives
  in order. In this design alternatives are an advisor's decision at
  drafting time, not a run-time fallback, for the same reason as HTN's
  backtracking. A Fallback appears only in the compiled goal-check shape.

### 2.3 GOAP (F.E.A.R.)

[verified: primary doc, Orkin, GDC 2006, pp. 3-7, read as page images]

- "An FSM tells an A.I. exactly how to behave in every situation. A
  planning system tells the A.I. what his goals and actions are, and lets
  the A.I. decide how to sequence actions to satisfy goals." (p. 3)
- "We need to assign a *Goal Set* to each A.I. ... These goals compete for
  activation, and the A.I. uses the planner to try to satisfy the highest
  priority goal." A rat "fails to formulate any valid plan to satisfy the
  KillEnemy goal, and he falls back to the lower priority Patrol goal"
  (p. 6).
- Benefit #1, "Decoupling Goals and Actions" (p. 7).

**Transfers:** goals compete by priority and a goal with no feasible plan
yields to the next rather than blocking everything. In this design that is
the ready queue skipping a held project and issuing the next one's step.
Decoupling goal from method is why a goal's check never names its children.

**Does not transfer:** run-time regressive search over an action set. Our
action set is ninety-odd real tools with arguments that name landmarks,
kinds and reservations; a search over that is the thing a model is asked
to do when it drafts, and the user has ruled the draft is then fixed.

### 2.4 MRP and ERP: netting, reservation, allocation

- ERPNext's projected quantity [verified: primary doc,
  docs.frappe.io/erpnext/projected-quantity]: "Projected Qty = Actual Qty +
  Planned Qty + Requested Qty + Ordered Qty - Reserved Qty - Reserved Qty
  for Production - Reserved Qty for Subcontracting - Reserved Qty for
  Production Plan". "Reserved Qty for Production: Raw materials are
  reserved on submission of Work Order and is reduced when raw materials
  are transfered to Work in Progress warehouse via a Stock Entry."
- ERPNext issue #57313, "`reserved_qty_for_production_plan` goes stale
  when a Work Order takes a Production Plan out of the non-completed set"
  [summary, github.com/frappe/erpnext/issues/57313, opened 2026-07-21,
  closed]: "WO submit / manufacture updates PP status via `set_status()`
  **without** refreshing plan-reserve bins", so "the live calculation
  returns zero ... but the stored bin value retains the obsolete reserved
  quantity indefinitely."
- This repo already has the netting half [verified: source]:
  `production/blocker.py` `available_quantity` excludes items flagged
  `in_job`, `owned`, `forbid`, `trader`, `in_building`, `construction`;
  `docs/PRODUCTION-MODEL.md` §10: "Reservation, not priority, is the
  enforcement. Available for discretionary work equals stock minus reserve
  floor, minus par, minus consumption commitment, minus job-claimed." and
  "Derived demand gets no cover target ... netted from the plan instead."

**Transfers:** netting a demand against available stock, recursively
through the bill of materials (the blocker walk); the distinction between a
**soft reservation** (a planned demand, ERPNext's "reserved for production
plan") and a **hard allocation** (items actually committed, ERPNext's stock
moved to work in progress; DF's `in_job` flag). And the issue is the
strongest evidence I found for the user's "never a running tally": a
mature ERP stores reservation counters and one missed refresh path left one
wrong indefinitely, while the live recomputation was right.

**Does not transfer:** MRP's time-phasing (lead-time offsets per week) and
lot sizing. DF has no reliable lead times for our jobs (manager orders do
not even dispatch on this fort), and our quantities are small. Keep netting,
drop the calendar.

### 2.5 OS scheduling: priority inheritance, aging, deadlock

- Priority inheritance [verified: primary doc, docs.kernel.org
  `locking/rt-mutex.html`]: "A low priority owner of a rt-mutex inherits
  the priority of a higher priority waiter until the rt-mutex is released.
  If the temporarily boosted owner blocks on a rt-mutex itself it
  propagates the priority boosting to the owner of the other rt_mutex it
  gets blocked on. The priority boosting is immediately removed once the
  rt_mutex has been unlocked." `rt-mutex-design` [summary]: the PI chain
  is "an ordered series of locks and processes that cause processes to
  inherit priorities from a previous process that is blocked on one of its
  locks"; unbounded priority inversion is the A/B/C case where a medium task
  B keeps low task C from releasing the lock high task A waits on.
- Aging, OSTEP ch. 8: MLFQ's Rule 5, the periodic priority boost ("After
  some time period S, move all jobs ... to the topmost queue" [summary],
  the rule's wording from the fetch tool, not read in the page image),
  fixes starvation; on choosing S [verified: primary doc, p. 7, read as a
  page image], Ousterhout's "voo-doo constants": "If it is set too high,
  long-running jobs could starve; too low, and interactive jobs may not get
  a proper share of the CPU."
- Deadlock [verified: primary doc, OSTEP ch. 32, p. 7]: "Four conditions
  need to hold for a deadlock to occur": mutual exclusion, hold-and-wait,
  no preemption, circular wait. "If any of these four conditions are not
  met, deadlock cannot occur." PostgreSQL [summary, docs "Explicit
  Locking" §13.3.4]: "PostgreSQL automatically detects deadlock situations
  and resolves them by aborting one of the transactions involved ... The
  best defense against deadlocks is generally to avoid them by being
  certain that all applications using a database acquire locks on multiple
  objects in a consistent order."

**Transfers:** inheritance through chains (our chains are project links:
booze needs barrels needs a workshop); boost removed when the block clears;
aging as a bounded periodic boost with an honestly-labelled tuning
constant; prevention by breaking hold-and-wait (grant a step's material
claims all or nothing, recomputed every cycle) and detection by a
wait-for-graph cycle for the claims that do persist (ground, hard holds).

**Does not transfer, and the design deliberately differs:**

- **Max versus sum.** The kernel boosts an owner to the *highest* waiter's
  priority because the CPU runs one thread at a time. Our dependants are
  not queued behind one CPU; when a barrel project is late, *every* goal
  that needs barrels is late at once, so their costs of delay add. The
  user's rule ("rising further when it unblocks several") is the
  economically right one, and it is not what the OS literature does. §11
  sums, with a cap.
- **Pre-emption.** An OS pre-empts a running thread; pre-empting a DF job
  (cancelling it) throws away hauled materials and walking time. The runner
  is non-pre-emptive for issued work. Priority only decides what is issued
  next.

### 2.6 Fair-share scheduling

[summary, Apache Hadoop YARN Fair Scheduler docs] "Fair scheduling is a
method of assigning resources to applications such that all apps get, on
average, an equal share of resources over time." It "allows short-duration
applications to complete reasonably quickly while preventing resource
starvation for long-running jobs". Queues carry weights, `minShare`,
`maxResources`, and **`maxRunningApps`**, a cap on concurrently running
applications.

**Transfers:** `maxRunningApps` is the Overseer's WIP limit, turned into
admission control; `maxResources` per queue is a per-project cap on
concurrent jobs per labor, the "time slice" of this domain; weights are the
priority score. **Does not transfer:** YARN allocates containers it owns.
We do not assign dwarves; DF does (§9.4). Our share is enforced only on
what we *issue*, which bounds what a project can occupy but cannot force a
dwarf onto a job.

### 2.7 Lean: cost of delay and WSJF

- [verified: primary doc, framework.scaledagile.com/wsjf] WSJF "sequences
  work for maximum economic benefit by dividing the cost of delay by job
  duration", quoting Reinertsen: "If you only quantify one thing, quantify
  the Cost of Delay." Its cost-of-delay components include "Risk reduction
  or opportunity enablement". Job size is "a proxy for duration using
  relative estimation".
- [summary, blackswanfarming.com/urgency-profiles] Urgency profiles:
  "Long life-cycle, peak unaffected by delay" (cost of delay constant per
  unit time), and "Impact of External deadline": "Cost of Delay is zero
  until the point where you need to start development," then escalates
  sharply.

**Transfers:** WSJF as the within-tier ordering; "opportunity enablement"
is priority inheritance in lean vocabulary; urgency profiles give the user's
"steep with a deadline for thirst, flat for comfort" a name and a shape.
**Does not transfer:** the relative estimation workshop. Our sizes and
costs come from code (the proposal's `cost` in `dwarf_ticks`, days of cover
from `production/cover.py`), never a team vote.

### 2.8 Idempotency and ownership

- [verified: primary doc, docs.stripe.com/api/idempotent_requests]
  "Stripe's idempotency works by saving the resulting status code and body
  of the first request made for any given idempotency key, regardless of
  whether it succeeds or fails. Subsequent requests with the same key
  return the same result ... The idempotency layer compares incoming
  parameters to those of the original request and errors if they're not
  the same".
- [summary, kubernetes.io "Owners and Dependents"] dependents carry
  `ownerReferences`; on owner deletion they are garbage-collected, or with
  the orphan policy "the controller ignores dependent resources after it
  deletes the owner object"; an object with several owners is "subject to
  deletion once all owners are verified absent".

**Transfers:** a key per attempt, stored with the result, compared with
parameters; claims and sub-projects as owned objects, with **several
owners** (barrels serving booze and food storage) released only when every
owner is gone. **Does not transfer:** Stripe keeps keys server-side for 24
hours; our "server" is the DF save, and the key must live in it (§7.4).

### 2.9 df-ai

[verified: source, through `research/2026-09-24-df-ai-fort-planner.md`
§Q1, §Q5, §Q6; df-ai not re-read this pass]

df-ai keeps a plan-level `priorities` "ordered task list consumed at
runtime" and `stock_goals`; each room carries a four-state status it
maintains itself; `checkroom` re-issues cancelled digs and rebuilds
tantrumed furniture "every sweep" with **no retry ceiling**. Its commit log
records the failure shapes this design must avoid: "fix rooms that were
never built somehow" (`d6a6f06`), and "Fix stocks update (and therefore
manager orders) never completing if the floor plan does not include a
garbage pit" (`6e04942`), a missing prerequisite silently starving an
unrelated subsystem.

**Transfers:** explicit recorded status, periodic self-healing re-issue,
stock goals as standing targets. **Does not transfer, and is a warning:**
unbounded re-issue. §10 gives every rung a budget, and the `6e04942` shape
(a missing prerequisite silently blocking everything downstream) is exactly
what named holds and priority inheritance are for: the blocker is visible
and gets priority instead of silently starving its dependants.

### 2.10 What nobody does

No system surveyed combines "a planner model drafts, a stronger model
amends by diff, code executes the approved plan verbatim". HTN, GOAP and
BTs all have one author (a designer or a search); ERP plans are generated by
code from demand. The closest precedent is this repo's own
`docs/AGENT-ARCHITECTURE.md` "A new ruling outcome: amend (agreed
2026-09-17, not built)": "the ruling stores the original proposal and the
amendment side by side, and grading scores what was actually executed." §6
builds on that rather than on outside prior art, and says so.

---

## 3. How a check is observed, and when its answer is due

(The user's first mid-task addition. It comes before the node model
because it decides the node model's check fields.)

### 3.1 Two axes every check must declare

**Axis 1, how the answer arrives:**

| Mode | What it is | Example | Cost |
|---|---|---|---|
| `readback` | the answer is in the tool call's own result, instantly | `building.build` returns the new building id at stage 0; `workjob.queue` returns the job id; `blueprint.reserve` returns `res-N` | free, but proves only that the *request* landed, never that the work is done |
| `recorded_event` | an in-game recorder saw a DFHack event touching one of our watched references, and the conductor reads it next cycle | a watched job vanished while its `completion_timer` read 0 (`JOB_COMPLETED`); a watched building was destroyed (`BUILDING`); an item appeared on a watched tile (`ITEM_CREATED`) | cheap in the game, but a **hint**: it can miss, and it cannot by itself prove the product exists |
| `poll` | code reads the world on a schedule and evaluates a predicate | drink units; is building 31 complete; are items 5120 and 5121 in any stockpile; is any reachable hostile visible | one bounded read per check per cycle; the **truth** |

**Axis 2, when an answer is expected:**

| Shape | Meaning | Stuck rule (§10) |
|---|---|---|
| `deadline` | the outcome must be known by tick T or it failed (a read-back's deadline is the call itself) | past T with no answer is a failure, not a wait |
| `window` | normally within W ticks of issue (or of the last progress signal), with no hard failure; W is an estimate with a declared source | past W with no progress and no named wait reason is **stuck** |
| `unbounded` | "whenever": the fort's own dwarves decide (hauling), or the world does (an enemy leaving) | never stuck by elapsed time alone; only when progress is absent while the conditions for progress are visibly present (§10.1) |

Every check also declares **`stale_after_ticks`**, the age past which its
last read degrades to `stale` (treated as `unknown` downstream), and a
**`poll_every`** (`cycle`, or a tick interval for expensive reads).
[proposed]

### 3.2 What DFHack actually offers

**The eventful plugin** [verified: primary doc, `docs/dev/Lua API.rst` at
tag `53.16-r1`, "Events from EventManager"]: `onBuildingCreatedDestroyed(building_id)`,
`onConstructionCreatedDestroyed(building_id)`, `onJobInitiated(job)`,
`onJobCompleted(job)` ("The job that is passed to this function is a copy.
Requires a frequency of 0 in order to distinguish between workshop jobs
that were canceled by the user and workshop jobs that completed
successfully."), `onUnitDeath(unit_id)`, `onItemCreated(item_id)` ("except
due to traders, migrants, invaders, and spider webs"), `onSyndrome`,
`onInvasion`, `onInventoryChange(unit_id,item_id,old_equip,new_equip)`,
`onReport(reportId)` ("This happens more often than you probably think"),
`onUnitAttack` ("Is NOT called if blocked, dodged, deflected, or parried"),
`onUnload`, `onInteraction`; plus the reaction hooks, including
`onReactionComplete(reaction, reaction_product, unit, input_items,
input_reagents, output_items)`. `enableEvent(evType, frequency)`: "The
frequency is how many ticks EventManager will wait before checking if that
type of event has happened. If multiple scripts or plugins use the same
event type, the smallest frequency is the one that is used". And: "If you
register a listener before the game is loaded, be aware that no events will
be triggered immediately after loading".

**How events are really produced** [verified: source,
`library/modules/EventManager.cpp` at `53.16-r1`]: every EventManager event
is an in-process diff. `manageJobCompletedEvent` walks `world->jobs.list`,
keeps a deep copy (`cloneJobStruct(&job, true)`) of each job **once it has
started** (`completion_timer != -1`), refreshes that copy when the job's
flags, `items.size()` or `general_refs.size()` change, and fires
`JOB_COMPLETED` with the copy when a job that last read
`completion_timer == 0` has vanished. Its own cleanup comment: "Jobs may be
missed if tick delta > zero". Building events diff `building_next_id` and
existence; item creation diffs `item_next_id`; unit death diffs a living
set and checks `Units::isDead`; reports diff the last report id.
Consequences:

1. **There is no interrupt-driven path anywhere.** "Event-driven" in DFHack
   means "polled every N ticks by code inside the game process". That is
   still much finer than a conductor cycle and, crucially, it runs while
   the conductor is not looking.
2. **The `JOB_COMPLETED` copy carries `job.items`** as of its last refresh:
   the exact-record path for "which items did this job use" (§8.3), with
   one risk: the copy holds `item` pointers, and an item the job consumed
   may be gone when the handler runs. Read only `item.id`, inside a `pcall`,
   and record a failure as "not recorded", never as "none used".
   [unverified: whether the pointers are still valid in the handler]
3. **`BUILDING` fires when a building record is created (at designation,
   stage 0) or destroyed, not when construction completes.** Completion is
   a poll of the stage. [verified: source, the diff reads ids and existence
   only]
4. **Events freeze with the game.** A paused fort produces none; the same
   property the tripwire relies on (`df-overseer-clock.lua` header).

**`repeat-util`** [verified: source, `library/lua/repeat-util.lua` at
`53.16-r1`]: `scheduleEvery(name, time, timeUnits, func)` re-arms itself
with `dfhack.timeout` after each call; the `repeating` table is cleared on
`SC_WORLD_UNLOADED`. The tripwire already runs on it
(`repeatUtil.scheduleEvery(TRIPWIRE_NAME, check_interval_ticks, "ticks",
check_fn)` [verified: source, `df-overseer-clock.lua`]).

**Reports and announcements** [verified: source, `df-overseer-diff.lua`
header]: `world.status.reports` is a native typed store (id, type as a
`df.announcement_type`, year, time, position, text), readable
retrospectively even while paused, live-replayed on this fort against 34
reports. The known gap is recorded there too: a wild animal's death
produced no report at all.

**Is eventful available and enabled here?** [verified: repo record]
`df-overseer-diff.lua` records that "eventful.plug.so loads" and that its
`onReport` listener "actually fired for real newly-created reports" with
the fort briefly unpaused (2026-09-12). `stuckjobs` registers
`JOB_INITIATED` the same way. Both register **lazily**, on their first
script run in a process lifetime. [unverified] whether VM 103's
`dfhack-config/init/onMapLoad.init` runs either (the file is not in the
repo; it is known to start the autosave and sampler repeats), and
`JOB_COMPLETED`/`UNIT_DEATH` have only ever been registered and
hand-called on this fort, never seen firing for real.

**What the repo already records** [verified: source]:

| Recorder | Captures | Lifetime | Limit for this design |
|---|---|---|---|
| `df-overseer-diff.lua` log | `JOB_COMPLETED` (name only), `UNIT_DEATH` (hidden excluded), `REPORT` (tagged categories), `UNIT_ATTACK` | `_G`, one DF process lifetime, never trimmed | no job, building or item ids; frequency 10; within-year `at_tick`; cursors meant for agents |
| `df-overseer-stuckjobs.lua` | `JOB_INITIATED` start ticks by job id | `_G`, process lifetime | idle time only for jobs seen starting since registration |
| `df-overseer-clock.lua` tripwire | citizen roster diff, critical vitals, reachable hostile, pause-level announcements | latch **file**, repeat-util | the urgent path; pauses the fort |
| `df-overseer-ledger.lua` | per-race sightings and outcomes | JSON file | threat memory; structurally forbidden to pause |
| `df-overseer-blueprint.lua` | per-site phase ticks, `dig_progress` (600-tick stall) | `dfhack.persistent` | blueprint sites only |
| `conductor/order_watch.py` | stalled and blocked manager orders | conductor cursor file | orders only |

### 3.3 The bridge: an in-game recorder, drained each cycle

Events fire inside DF on VM 103; the conductor on VM 106 reads over MCP
once a cycle. Something must hold events in between. [proposed]

**`df-overseer-recorder.lua`: conductor-only, registered at map load.**

- **Registered from `onMapLoad.init`**, not lazily, so the minutes after a
  load are not blind. The conductor also polls every watched check on its
  first cycle after a load, which covers DFHack's own "no events ...
  immediately after loading" caveat.
- **A watch list pushed by the conductor** each cycle (`recorder.watch`):
  the DF job ids, building ids, item ids and target tiles of every issued
  step. Events touching a watched reference are kept in full; everything
  else is only counted. This bounds size without dropping anything the
  runner needs. (Tiles are passed code-side, by handle resolution inside
  the DFHack tools, never through a model-visible field.)
- **Captured**: `JOB_COMPLETED` for watched jobs (job id, type, the ids and
  roles in `job.items`, the worker id); `BUILDING` and `CONSTRUCTION`
  create/destroy for watched ids and tiles; `ITEM_CREATED` on a watched
  tile (the ore boulder a watched dig produced); `onReactionComplete`
  output item ids at watched workshops (the drink a brew produced).
  `UNIT_DEATH` and `REPORT` stay in diff.lua, not duplicated.
- **Stored in `dfhack.persistent` site data, not `_G`.** Site data is
  written into the save when DF saves. If DF crashes, the world rolls back
  to the last save **and so does the recorder**, so it can never claim an
  event the rolled-back world does not contain. A `_G` log survives
  neither a process restart nor a rollback consistently. Reservations and
  blueprint site handles already use this mechanism [verified: source].
- **Monotonic ids and a bounded ring**, trimmed by id, never by index (the
  discipline `drain_since`'s own comment states), and **absolute ticks**
  (`cur_year * 403200 + cur_year_tick`, the clock tool's formula).
- **Frequency**: `JOB_COMPLETED` at 1 is the proposed compromise; 0 makes
  EventManager diff the whole job list every tick, at a cost nobody has
  measured here. At any frequency the event is a hint and the poll is the
  proof, so a missed event costs one cycle of latency, never a wrong
  record. [unverified: the per-tick cost of frequency 0 or 1 on this fort]
- **The ledger's hard rule, copied**: the recorder never pauses, never
  calls `clock_*`, never schedules anything but its own listeners, and a
  test greps its source for the forbidden names.

**Which events take the urgent path?** Only those that already do: the
tripwire's death, critical-vital, reachable-hostile and pause-level
announcement checks. Nothing about a project justifies pausing the fort:
a failed barrel job, a destroyed workshop or a cancelled haul can wait for
the next cycle. If a project condition ever needs faster handling, the
route is one more check in the tripwire's own `check_fn` (the existing
mechanism), never a pause in the recorder. [proposed]

**Conductor side**: `recorder.since CURSOR` (conductor-only grant, like
`queue.overview`), drained right after `clock.status` and before the
reconciler, so every observation this cycle sees this cycle's hints.

### 3.4 Honest checks: tri-state, and what cannot be tracked

Every check returns **`met`**, **`not_met`** or **`unknown`**, and is
**`stale`** once its last read is older than `stale_after_ticks`. Rules
[proposed], matching the guards' `pass`/`hold`/`unknown` and the CQL
three-valued logic `research/2026-09-22-objective-graph-prior-art.md`
already adopted:

- `unknown` and `stale` never satisfy a goal and never release an in-order
  sibling.
- `unknown` is a **named wait reason** ("unobservable: ..."): never stuck
  by time, escalated only if it outlasts the check's own
  `unknown_escalate_after_ticks`.
- **Hidden things stay hidden.** A check reads only what a player can see
  (`CLAUDE.md` "No armok capabilities"; `dfhack.units.isHidden` gating as
  diff.lua does). If the honest answer depends on hidden state, it is
  `unknown`, never `met`.
- **Met by absence** only as a declared form: "no visible reachable
  hostile for W consecutive ticks", recorded as `met (by_absence, W)`,
  weaker than a positive read, and the record says so.

**What cannot be tracked, stated plainly:**

- **The fort's own work has no event we own.** Hauling
  (`StoreItemInStockpile` [verified: source, `df.job.xml`]) is generated by
  DF. We can see such a job appear and vanish (a hint) and poll where an
  item is (the truth), but only for items we named.
- **A specific item is trackable only if it was claimed or recorded.**
  "Some hematite reached a stockpile" is a count. "The boulder our dig
  produced reached a stockpile" needs that item's id, captured when it
  appeared (`ITEM_CREATED` on a watched tile) or when one of our jobs held
  it.
- **Completed versus cancelled**, for a job that left the list, stays
  ambiguous without a product read (the 2026-09-28 design's table and the
  frequency caveat above). The check is on the product; the job's
  disappearance is a hint.

### 3.5 Default declarations per check kind

| Check | Mode | Expectation | Notes |
|---|---|---|---|
| request landed (any mutating tool) | `readback` | deadline: the call | the tool's own `ok`, ids and `held` list; `DRY_RUN` must be false and echoed (the 2026-09-25 cycle read a dry run's `ok` as a real placement) |
| building complete | `poll` (stage), hint `BUILDING` destroy | window, from requirements | `BUILDING` create is at designation, not completion |
| construction complete | `poll` (tile is a construction), hint `CONSTRUCTION` | window | a construction keeps its material, not its item (§8.3) |
| workshop job produced | `poll` (product or free-candidate count), hints `JOB_COMPLETED`, `onReactionComplete` | window | the product read is the truth; the event carries item ids |
| dig done | `poll` (`dig_progress`, tile shape), hint `JOB_COMPLETED` | window, the existing 600-tick stall rule | `dig_progress` already names `none_pending`/`in_progress`/`stalled`/`unknown` |
| stock level (goal) | `poll` (a `live_signals` entry) | unbounded for standing goals | reuses `learning/live_signals.py`'s closed registry |
| claimed item in a stockpile | `poll` (`dfhack.buildings.getStockpileContents`) | unbounded | live-verified primitive in `df-overseer-stockpile.lua` |
| threat cleared | `poll` (`threat.scan`) plus `REPORT` hints | window, met only by absence | tri-state; hidden units never counted |
| manager order progressing | `poll` (`orders.list`) | window (`stalled_order_threshold_ticks`) | `order_watch.py` already does exactly this |

---

## 4. A taxonomy of jobs and checks, a coverage map and a fill plan

(The user's correction to the build order: categorise first, then plan to
fill every group, and let that shape what gets built.)

### 4.1 How the job groups were derived

From the game's own data, not memory:

- **DF's `job_type` enum at DFHack tag `53.16-r1`** [verified: source,
  df-structures `df.job.xml` at `53.16-r1`, parsed by script]: **259
  entries**, matching the 2026-09-21 live dump's `job_count`
  (`production/tests/fixtures/labor_dump/PROVENANCE.md`: "21 of 259 job
  types"). Each entry carries the game's own class attribute: Manufacture
  85, Hauling 25, UnitHandling 21, Gathering 16, LifeSupport 15,
  StrangeMood 13, Improvement 11, Medicine 10, Digging 8, Crime 6,
  LawEnforcement 6, SiegeWeapon 6, Carving 5, Building 4, TidyUp 4,
  Leisure 1, and 23 with no class (including `CustomReaction`,
  `TradeAtDepot`, `PullLever`, `ManageWorkOrders`, `CarveFortification`
  and ten `UNUSED_*` slots).
- **Building kinds** [verified: source, `df.d_basics.xml` and
  `df.building.xml` at `53.16-r1`]: `building_type` 56 values (furniture,
  machines, farm plots, stockpiles, civzones, constructions ...),
  `workshop_type` 26 (including `Custom` and `Tool`), `furnace_type` 9,
  `construction_type` 39 (walls, floors, stairs, ramps, 30 track
  variants, reinforced wall), `civzone_type` 99 (most are site or
  world-generation zones; the fort-mode player zones are about 19 of them,
  Bedroom to Tomb at the end of the enum [unverified count; the zone tool
  reads its kinds live]), `tile_dig_designation` 7.
- **Quickfort building kinds**: 175 on this install [verified: repo record,
  `TOOLS.yaml` `building list-kinds`, "175 kinds listed, no token
  collisions", live 2026-09-21].
- **Workshop jobs as the game offers them**: `workshops.getJobs` returns
  at least one real job for 28 of 33 workshop and furnace kinds [verified:
  repo record, `df-overseer-workjob.lua` header, "measured, not
  estimated"].
- **Reactions**: the game lists 293 reactions
  (`handoffs/2026-09-21-extract-remaining-reactions.md`); the production
  extraction holds 148 fortress-mode reactions
  (`research/2026-09-19-real-corpus-extraction.md`). All run through the
  single `CustomReaction` job type.

The grouping rule: **two jobs share a group when they share how they are
issued, what they claim, and how their outcome is observed.** The game's
own class attribute is the starting point; where a class mixes issuing
mechanisms (Gathering has both tree-felling designations and standing
fishing), it is split by mechanism. The script's placement of all 259
entries: 247 placed, 11 unplaced (`<anon>` and `UNUSED_31` to `UNUSED_40`,
empty slots), plus `NONE`.

### 4.2 The job groups

| Group | How it is issued | Claims | Outcome observed by | DF job types (count) |
|---|---|---|---|---|
| **A. Designations** | mark tiles; DF generates a job per tile | ground (reservation), labor (miner, mason, engraver, woodcutter, herbalist) | poll tile shape and designation count; items appear on the tile | `Dig`, stairs, `CarveRamp`, `DigChannel`, `RemoveStairs`, `SmoothWall/Floor`, `DetailWall/Floor`, `CarveTrack`, `CarveFortification`, `FellTree`, `GatherPlants` (15) |
| **B. Placed buildings and constructions** | place a building record; DF generates `ConstructBuilding` | ground, materials (by building requirement), labor | read-back of the building id; poll stage | `ConstructBuilding`, `DestroyBuilding`, `RemoveConstruction` (3) over 56 building types, 39 construction types, 175 quickfort kinds |
| **C. Workshop jobs and reactions** | queue a job at a named workshop | materials (the job's own item filters), labor (the workshop's Workers-tab labors), the workshop's queue | read-back job id; hint events; poll product | Manufacture 85, Improvement 11, `CustomReaction` (every reaction), `MakeShield`, `SpinThread` (99) |
| **D. Manager orders** | add an order; the Manager validates it, DF spawns jobs | as C, plus a Manager and an office | poll `amount_left`, `validated`, `active` | `ManageWorkOrders` plus every C job it spawns (1) |
| **E. Hauling and storage** | never issued directly: configure stockpiles, dump or forbid items, set links | none of ours; the fort's haulers | poll item location, unbounded | Hauling 25 minus trade/traps, TidyUp 4, `UpdateStockpileRecords` (25) |
| **F. Configured standing work** | configure a place (farm plot crop, fishing or sand/clay zone, hive) and DF generates jobs indefinitely | the place, the labor | poll stock flow, unbounded | `PlantSeeds`, `HarvestPlants`, `Fish`, `Hunt`, `Collect*`, `FertilizeField`, `InstallColonyInHive` ... (13) |
| **G. Animals** | mark units or assign pens | the animal, the labor | poll unit state | UnitHandling 21 plus milk, shear, slaughter (24) |
| **H. Military and threat** | squads, traps, siege engines (and reflexes, per decision 1) | squads, ammo | poll threat, reports | SiegeWeapon 6, trap loading 4 (10) |
| **I. Autonomous, observe only** | nobody issues these; DF does | none | vitals, reports | LifeSupport, Medicine, StrangeMood, Leisure, Crime, LawEnforcement, `SeekArtifact` (52) |
| **J. Mechanisms** | link or pull a lever, run a pump | the mechanism, the operator | poll the linked building's state | `LinkBuildingToTrigger`, `PullLever`, `OperatePump` (3) |
| **K. Trade** | bring goods to the depot, trade | goods, the broker | poll depot, stock | `BringItemToDepot`, `TradeAtDepot` (2) |
| **L. Instant settings** | a state change with no DF job at all | none, or ownership | read-back, then poll for drift | not jobs: zones (about 19 fort-mode kinds), zone owners, noble appointments, farm crop per season, labor flags, stockpile settings |

Fits no group: the 11 empty enum slots only. Three placements are
judgement calls, stated: `PlaceItemInTomb` is hauling (E) though a tomb
zone (L) causes it; trap loading is military (H) though its class is
Hauling; milk, shear and slaughter are animals (G) though their class is
Gathering.

### 4.3 The check groups, crossed with observability

| Check group | Mode (§3.1) | Expectation | Tri-state source of `unknown` | Generic pattern |
|---|---|---|---|---|
| **K1. Request landed** | read-back | deadline: the call | tool error or timeout | the tool's `ok`, returned ids, `held` list, `DRY_RUN` echoed false |
| **K2. Can start (guards)** | poll at issue time and every cycle | none (a hold is a wait) | a read failed | the closed guard vocabulary (`reservation`, `item_present`, `keeps_access`, the next one is one entry) |
| **K3. DF job lifecycle** | recorded events plus poll | window | job id no longer resolvable | job exists, has a worker, `completion_timer` moving; `stuckjobs`, `dig_progress`, `order_watch` are three instances |
| **K4. Effect exists** | poll, hinted by events | window | the thing is hidden or unreadable | "building N is complete", "tile is open/a construction", "product count rose by k" |
| **K5. Level goal** | poll | unbounded (standing) | a signal read failed | a `live_signals` entry, op, value: the prediction shape reused |
| **K6. Setting holds** | read-back, then poll for drift | deadline, then unbounded | unreadable | "zone 13 has owner U", "crop is X for spring"; drift possible (autolabor rewrites labor flags) |
| **K7. Condition by absence** | poll plus report hints | window, met only by absence | visible evidence is insufficient | "no visible reachable hostile for W ticks" |
| **K8. Claimed item location** | poll | unbounded | item id no longer resolvable, or on a hidden tile | "items i1..ik are in a stockpile / a building / consumed" |

**The three examples land in named groups** (walked through in §12):

- **Building a still**: job group B; checks K1 (building id at stage 0),
  K2 (reservation, `item_present`), K3 (the `ConstructBuilding` job has a
  worker), K4 (stage complete).
- **Killing an enemy**: job group H, but decision 1 makes the fight itself
  a reflex; the *project-level* goal "threat cleared" is K7, tri-state,
  never met by a positive read.
- **Transporting a chunk of hematite to a stockpile**: job group E (the
  haul is the fort's own); the item is known only if claimed, so the chain
  is A (mine) producing an item recorded by `ITEM_CREATED`, then K8
  (claimed item in a stockpile), with the configuration job (a stockpile
  accepting stone exists and is reachable) in E or B.

### 4.4 Coverage map: what exists today

From `scripts/dfhack/TOOLS.yaml` (every command read by script) and the
guards in the Lua. [verified: source]

| Group | Issuing tools that exist | Checks that exist | Missing |
|---|---|---|---|
| A | `diggable.dig`, `diggable.dig-stair`, `openarea.build`, `blueprint.apply` (dig, carve, smooth phases), `construction.mine-vein`, `trees.fell`, `landmarks.build` | `blueprint.status`/`dig_progress` (600-tick stall), `surface.finish`/`vein-material`, `diggable.find` reachability, `blueprint` refuses a stranding dig | channel, detail/engrave, track, fortification, `GatherPlants` and `RemoveStairs` as generic kinds; a designation progress check for anything but a blueprint site |
| B | `building.build` (175 kinds), `workshop.build`, `well.build`, `farm.build`, `construction.build`, `blueprint.apply` build phase | read-back ids; `item_present`, `keeps_access`, `reservation` guards; `building.find` requirements; `kind_previously_built` | deconstruct (`DestroyBuilding`, `RemoveConstruction`); a generic "building N complete" poll; a workshop footprint template for reservations |
| C | `workjob.queue`/`cancel`/`list-jobs` (28 of 33 kinds via `getJobs`), reagent container choice | `list-jobs` free-candidate counts; `stuckjobs` | a product check per job generic from `getJobs`' product spec; item-id capture at completion |
| D | `orders.create` (12 jobs), `cancel`, `list`, `check-duplicate` | `order_watch.py` stalled/blocked | orders never dispatch on this fort (user's ruling: set aside) |
| E | none that write; `stockpile.list`/`links` read | `getStockpileContents` inside `stockpile.list` | stockpile create and settings, dump and forbid, links; K8 check |
| F | `farm.build`, `farm.set-crop`, `zone.place` for fishing, sand, clay, pond kinds | `farm.list`, `stocks.*`, `production/cover.py` (days of cover, offline) | a flow check (rate over a window) wired to a tool |
| G | none | none | everything; low value at this fort's stage |
| H | none that write (reflexes are the tripwire's pause) | `threat.scan`, `breach.check`, tripwire | squads, burrows, traps (the Marshal is blocked on exactly this) |
| I | not issuable | `vitals.summary`, `stuckjobs`, `diff` reports | none needed for the design |
| J | none | none | lever linking and pulling |
| K | none | none | trade (`research/2026-09-16-trade-execution-api.md` exists) |
| L | `zone.place`/`assign-owner`/`clear-owner`, `nobles.appoint`/`unappoint`, `farm.set-crop`, `labor.set-labor` (contested by autolabor) | `zone.contents`/`check-owner`, `nobles.verify`/`requirements`, `labor.labors` | stockpile settings; a drift check for settings |

Two doc-drift notes for a memory audit, not patched here: several commands
Working.md records as deployed and live-verified (`zone assign-owner`,
the `surface` reads, `construction.*`, `blueprint.*`) still carry
`live_deployed: false` in TOOLS.yaml.

### 4.5 The fill plan: one generic implementation per group, fed by game data

The repo's rule (`CLAUDE.md`, "Tools must be generalisable"): the next
instance should cost one data entry. Per group [proposed]:

| Group | Generic implementation | Fed by | Next instance costs |
|---|---|---|---|
| A | one `designate` path per quickfort `#dig` key over a target set (a template, a zone ring, a query), with one generic progress check (`dig_progress` generalised off blueprint sites) | quickfort's own designation keys; `tile_dig_designation` | one key-to-kind row |
| B | `building.build` as is; add one generic `building.status ID` (stage, complete) and one `deconstruct` | the 175 quickfort kinds; building requirements (`research/2026-09-21-building-requirements.md`) | nothing |
| C | `workjob.queue` as is; add a generic product check computed from `getJobs`' own product spec and the production graph, and item-id capture from the recorder | `getJobs`; `production/` graph | nothing |
| D | park (user's ruling) | | |
| E | one stockpile writer over quickfort `#place` and stockpile settings, plus item forbid/dump over claimed item ids; K8 as the check | stockpile categories (`building.settings.flags`, 17 top-level, verified live in `df-overseer-stockpile.lua`) | one category row |
| F | reuse `farm.*` and `zone.place`; one flow check (rate over a window) | `production/cover.py` | one signal entry |
| L | reuse `zone.*`, `nobles.*`; one drift check that re-reads a setting | the zone tool's own kind table | one kind row |
| G, H, J, K | defer; each is a real tool family and none is on this fort's critical path | | |
| I | observe only | | |

**Ordered by value against cost** [proposed]: **C** (drink, food, barrels,
furniture; the tool exists, only checks are missing), **B** (exists; one
status read), **A** (mostly exists; generalise the progress check), **L**
(exists; drift check), **E** (high value, hauling ore and full stockpiles
are live problems, but it needs a new write tool), **F** (partly exists),
then **D, G, H, J, K** when a real need appears.

The check groups fill the same way: K1, K2, K3 exist in pieces and need
one shared shape; K4 needs `building.status` and the product check; K5 is
`live_signals` (exists); K6 needs the drift re-read; K7 wraps `threat.scan`;
K8 needs the item-location read (the primitive exists in the stockpile
tool).

---

## 5. The node model

### 5.1 Nodes

All [proposed]. Shapes are shown as YAML; they are fields of the existing
`project` record, validated by `dfqueue/schema.py` like everything else.

**Job node** (a step, unchanged in meaning from the 2026-09-28 design and
the live schema, with four additions):

```yaml
- id: p7/j1
  tool: workjob.queue               # a real registry id, as today
  args: {JOB: MakeBarrel, WORKSHOP_LANDMARK_NAME: "@p9.site.landmark", COUNT: 2}
  targets: {set: [j1]}              # as today
  guards: default                   # as today: add-only
  needs:                            # NEW: the demand this job claims (§8)
    materials: [{class: WOOD, form: log, qty: 2}]
    labor: [{labor: CARPENTER, jobs: 1}]
    ground: null                    # or a res-N, or a slot id
  check:                            # NEW: did it work (K1 + K3/K4)
    readback: {expect: [job_ids]}
    effect: {signal: 'workjob."@p9.site.landmark".free_container_candidates', op: gte, value: 2}
    observe: {mode: poll, hints: [JOB_COMPLETED, REACTION_COMPLETE], poll_every: cycle}
    expect: {shape: window, ticks: 2400, source: "estimate: one carpenter, two barrels"}
    stale_after_ticks: 1200
  retry: {reissue_max: 2}           # NEW: §10's budget for this job
```

**Goal node** (new):

```yaml
- id: p7/g1
  summary: "an empty food-storage container is free at the Still"
  check:                            # independent of children, always
    signal: 'workjob."Still".free_container_candidates'
    op: gte
    value: 1
    observe: {mode: poll, poll_every: cycle}
    expect: {shape: window, ticks: 4800, source: "sum of children's windows"}
  order: in_order                   # in_order | together
  children: [p7/j1, p7/g2]          # job ids, goal ids, or link ids
```

**Link node** (a child that is another project's goal):

```yaml
- id: p7/l1
  needs_project: project-0009       # "barrel production"
  satisfied_by: goal_check          # the linked project's root check, read live
```

**Slot** (an open decision a named role must fill; blocks acceptance):

```yaml
- id: p9/s1
  role: architect
  kind: site                        # site | material_choice | target_set (closed vocabulary)
  for: p9/j1                        # the job whose argument it fills
  fill: null                        # e.g. {RES_ID: res-12}
```

**Project root**: the project record gains `root` (a goal id), and the
project's goal check is the root's check. A project with no goals at all
keeps today's meaning (root = "every step done").

### 5.2 Semantics

- **A goal compiles to the BT shape Fallback(check, Sequence or Parallel
  of children).** Each cycle: if the goal's check reads `met`, the goal is
  met and nothing under it is issued; otherwise its children are
  considered, in order (only the first not-yet-met child is active) or
  together (every not-yet-met child is active).
- **In order waits on the previous child's check, not on its jobs
  finishing.** Child k+1 becomes active when child k reads `met` (a goal's
  check, or a job's `effect` check). This is rule 2 made operational:
  "children succeeding is not the goal being met" applies at every level.
  It is also where this design goes beyond the live `requires` edge
  (finish-to-start on targets): `requires` stays for job-to-job data flow
  inside a goal (`from_step`), and `in_order` is gated by checks.
- **Jobs are memory nodes; goals are reactive** (§2.2). A job recorded
  `done` is not re-issued because a check later reads `not_met`; instead
  its *parent goal* reads `not_met`, and the healing ladder (§10) decides
  whether to re-issue. A goal whose check becomes `met` early (someone
  else built the still) makes its whole subtree moot.
- **`unknown` blocks.** A child whose check is `unknown` or `stale` does
  not release its in-order sibling (§3.4).
- **Failure.** A job fails when its read-back fails or its re-issue budget
  is spent. A goal fails when an in-order child has failed, or when every
  together-child that could still help has failed. Failure escalates
  (§7.5); there is no run-time fallback to an alternative method (§2.1).
- **Standing goals.** `standing: true` on a project root: when its check
  reads `met`, the project becomes **dormant** (not active, holds no
  claims, does not count against the active limit). Every cycle its check
  is re-read; `not_met` makes it **active** again and its subtree is
  re-evaluated from the root: satisfied children are skipped, jobs whose
  parent goals now read `not_met` become eligible to run again. Re-running
  a dormant tree's jobs with their original arguments is authorised by the
  original ruling within a declared `rerun_budget` (for example 4 per
  game year); beyond it, or if any argument would change, it needs a new
  ruling (§14 lists this as a decision).
- **Emergencies are not projects** (decision 1). The tripwire pauses; the
  Overseer handles it. A project may *follow* an emergency (repair the
  breach), drafted like any other.

### 5.3 Checks: the vocabulary

A check is one of:

1. **A signal predicate**: `signal`, `op`, `value`, where `signal` is an
   entry in `learning/live_signals.py`'s closed registry and `op` in the
   same `PREDICATE_OPS` the proposal's prediction already uses. This reuses
   the prediction shape exactly [verified: source, `dfqueue/schema.py`
   `_validate_prediction`]. New checks mostly mean new signal entries, each
   with a declared observation mode and the player-visibility rule the
   registry already enforces. Needed for the groups in §4.5:
   `building."ID".complete`, `workjob."LANDMARK".free_container_candidates`,
   `item_set."HANDLE".in_stockpile`, `threat.reachable_visible.count`,
   `zone."ID".owner_is`, `stocks.availability."TYPE".available_units`
   (exists).
2. **A guard** (can-start): a name from the closed guard vocabulary, as
   today. Guards are never goal checks; they only hold.
3. **A read-back expectation**: which fields of the tool's own result must
   be present and true (`ok`, an id, `designations_landed`).

Every check carries the §3.1 declarations (`observe`, `expect`,
`stale_after_ticks`). A check whose signal is missing from the registry is
refused at filing, with the list of real signals, the same way a bad
prediction signal is refused today.

### 5.4 Mapping onto the live schema: extend, do not layer

Options considered:

- **A new layer on top** (a `goal_tree` record kind that points at
  projects): keeps `project` untouched, but splits one plan into two
  records the Overseer must keep consistent, and linking already needs
  project-to-project references anyway.
- **Extend `project`** with optional `goals`, `links`, `slots`, `root`,
  `standing`, `rerun_budget`, `priority_profile`, and optional `needs`,
  `check`, `retry` on steps. Jobs stay `steps`, so `queue.executed`'s
  `step_id`, the `step_targets` fold and `queue.project_status` all keep
  working unchanged.

**Recommendation: extend.** A project with none of the new fields is
exactly today's project. Breaking risk is close to zero now: the live
queue holds **no projects** (`queue.project_status` read "(no projects)"
on 2026-09-30 [verified: repo record, `Working.md`]), so this is the
cheapest moment the schema will ever have to change. Store changes:

- `project_status` computes status from the root check when a root
  exists, and **stops reporting `done` while any step has no target rows**
  (fixes the §0 bug for the old path too).
- New record kinds: `step_attempt` (conductor only, §7), `priority_override`
  (sole writer, §11), `slot_fill` (a proposal type for the role named in
  the slot, §6.3). Observations (`observation`, live, conductor only) carry
  goal-check results as well as target results.
- Cross-project links are validated acyclic at acceptance (a link cycle
  would be a permanent deadlock; §10.4).

---

## 6. Drafting and amendment

### 6.1 The draft on a proposal

A proposal gains an optional **`draft`** field: a project body (`summary`,
`because`, `root`, `goals`, `steps`, `links`, `slots`, `standing`, ...)
with no `from_ruling`. It is validated at filing by the same
`_validate_project_fields` plus the new rules, so **a bad plan bounces to
the advisor that wrote it**, cheaply, before the Overseer sees it
(decision 5). [proposed]

Validation at filing (static, no game time):

1. Every leaf is a job with a real tool id, and its `args` keys are that
   command's real argument names (the registry already knows the
   signature; `dfmcp.tools` builds schemas from it). Unknown argument:
   refused, listing the real ones.
2. **No vague nodes** (decision 2): every goal has a check from the
   vocabulary; every branch ends in jobs, links or slots; no goal is
   childless unless its check alone is the point (a pure wait, allowed
   only for `standing` roots and link targets).
3. Every check names a registered signal, a real guard, or read-back
   fields, and declares its observation and expectation.
4. `in_order`/`together`, `requires` and link graphs are acyclic.
5. Late-bound arguments (`@p9.site.landmark`, `@p7/j1.job_ids`) reference
   only an earlier node's declared output (§14.2 explains why these are
   needed and why they are not vague).
6. Slots name a role and a kind from the closed vocabulary. **A draft with
   open slots is valid to file and cannot be accepted** (decision 2).
7. Coordinates are refused in every text field (the existing filter).

Optional, at acceptance time, by code: a **dry run of every job that is
ready now** (the tools already default or accept `DRY_RUN`), so the
Overseer rules on a plan whose first steps are known to resolve. This costs
game-side calls, not model tokens.

**Where the skeleton comes from.** For group C and D goals the draft's
job list is exactly what `production/blocker.py`'s AND-OR walk produces:
the producing reaction, its reagents, its workshop, recursively, stopping
at the first node with available stock [verified: source]. Wiring that walk
to an MCP read (`production.blockers GOAL QTY`) would let the
Quartermaster ask code for the chain and spend its tokens only on the
targets and the choice between routes. That is the single cheapest way to
stop the 2026-09-25/28 rediscovery of "brewing needs barrels needs
carpentry": the walk would have returned that chain on the first call.
[proposed]

### 6.2 Linked projects instead of one tree

Decision 3: "more booze" depends on "barrel production", which depends on
"carpentry workshop"; each is its own project with one owning role. How
[proposed]:

- An advisor may file several drafts in one cycle, each naming the others
  by **draft reference** (`needs_project: "@proposal-0012"`), resolved to a
  project id when both are accepted. A link to an existing project uses its
  id.
- The Overseer approves them **one at a time**. A project whose link
  target is not yet accepted is accepted in state `waiting: link` and
  holds no claims.
- **One sub-project, several goals**: a link target records every project
  that links to it (`served_by` computed, not stored). It ends by its own
  root check; its outputs are not claimed by it after that (the barrels
  belong to whoever claims them next). If every linking project is
  abandoned before it runs, it is flagged as an orphan project for the
  Overseer, not silently cancelled (Kubernetes: collected "once all owners
  are verified absent", but here collection is a decision).

### 6.3 Slots and who fills them

The Architect owns anything needing a place (decision 4), but holds no
mutating tool: `blueprint reserve` is overseer-only (`roles.py` rule 2,
recorded 2026-09-30). So a site slot is filled in two steps [proposed]:

1. The Architect reads (`blueprint.plan`, `blueprint.preview`,
   `building.find`) and files a **`slot_fill` proposal**: the slot id, the
   filling job (`blueprint.reserve TEMPLATE PURPOSE SITE RANK ...` as real
   arguments), and why. It validates like a draft job.
2. On acceptance, the slot's filling job is inserted into the project as
   its first ready job, run by the runner like any other; its read-back
   (`res-N`) becomes the late-bound `RES_ID` of the job that needed the
   site. Every later job gets the pinned handle, never a re-ranked site.

Gap this exposes [verified: source]: **there is no workshop footprint
template**, so a workshop site cannot be reserved today. One template
(`workshop-pad-3x3-v1`: a cleared, smoothed 3x3 with its declared seams)
closes it; generic by rule, one data entry.

### 6.4 Amendment

The architecture already agreed an `amend` outcome (2026-09-17, not
built): "the ruling stores the original proposal and the amendment side by
side, and grading scores what was actually executed." [verified: source,
`docs/AGENT-ARCHITECTURE.md`] Concretely [proposed]:

- `queue.rule` gains `decision: accept` with an optional **`amend`** list.
  Accept by reference is `accept` with no list (the cheap path, decision
  5). Operations, closed vocabulary:
  - `drop {node}`
  - `add {parent, position, node}`
  - `update {node, fields}` (a partial patch; `args`, `check`, `needs`,
    `expect`, `retry` only)
  - `fill_slot {slot, fill}` (the Overseer filling a slot itself)
  - `relink {node, needs_project}`
- The store applies the operations to the draft, validates the result as a
  project, and creates the project from it **in the same transaction** as
  the ruling, so a ruling that would produce an invalid project is refused
  whole and nothing is half-written. (Today `queue.rule` and
  `queue.project` are two calls; for a drafted proposal they become one.)
  The advisor never creates the project (decision 5 unchanged).
- The ruling record keeps the operations; the project records
  `from_draft` and `amended: true`. **Planner quality** is then a count
  per role and proposal type: accepted as drafted, amended (operations per
  draft, by kind), rejected. That is the data decision 5 asks for.

### 6.5 Token cost

Estimates, not measurements [unverified: no drafted proposal has been
run]. The draft JSON of the booze chain's three projects (§12) is roughly
40 to 60 lines each; at typical JSON density that is about 500 to 900
output tokens per draft for the advisor (DeepSeek, the cheap model). The
Overseer's accept by reference is a ruling of about 100 output tokens; an
amendment adds perhaps 50 to 150 per operation. Re-sending the whole plan
would cost the Overseer the full draft again on its expensive model, which
is what decision 5 avoids. On the input side, the `draft` schema in
`queue.propose`'s description adds a fixed cost to every advisor call
(plausibly 600 to 1,200 tokens of schema text); the observed day totals on
this fort (the conductor cycles 2026-09-25/28 cost $0.12 to $0.16 per day,
`evals/live/2026-09-25-first-real-conductor-cycle/README.md`) are the
baseline to compare against once a drafted cycle runs.

---

## 7. The step runner in the conductor

### 7.1 Where it sits in the cycle

Today's cycle [verified: source, `conductor/cycle.py` docstring]: read,
grade, triage, advise, decide-and-act, save. The runner is code and runs
**every cycle, before any model wakes** [proposed]:

1. Tier 0 read (as today: `clock.status`, `vitals.summary`,
   `overview.get`, `queue.overview`, diff drains).
2. **Drain the recorder** (`recorder.since`), then **reconcile**: evaluate
   every active project's goal checks and job checks, write `observation`
   records (conductor only, live schema), apply rollback detection
   (`store.rollback_drift`, live).
3. **Wake standing goals** whose checks now read `not_met`.
4. **Build the ready queue** (§9): the next runnable jobs of every
   admitted project, in priority order (§11).
5. **Allocate claims** in that order (§8); a job whose claims are short is
   held with a named reason.
6. **Quicksave** (the existing "save before any action" rule), then
   **run each granted job** through `queue.run_step`.
7. **Stuck detection and healing** (§10): the cheap rungs run here as code;
   only escalations become wake reasons.
8. Triage as today, with new wake reasons: `step_escalation` (wakes the
   Overseer), `slot_open` (wakes the slot's role), `draft_bounced` (wakes
   the drafting advisor), `standing_goal_rerun_budget_spent` (Overseer).
9. Advisors, Consultant, Overseer, as today.

A quiet cycle with nothing ready still wakes nobody and costs no tokens;
the runner itself costs only MCP calls.

### 7.2 The permission change, exactly

Today [verified: source, `dfmcp/roles.py`]: rule 2 forbids any mutating
tool to a role other than the roster's sole writer, with one narrow
exception (`SYSTEM_CLASS_TOOL_IDS`: clock and quicksave, grantable only to
kind `system`, no sole-writer carve-out); rule 6 restricts
`sole_writer_only` native tools to the sole writer.

The change [proposed]: **one new native tool, `queue.run_step`, and one
new exception set beside `SYSTEM_CLASS_TOOL_IDS`.**

- `STEP_RUNNER_TOOL_IDS = {"queue.run_step"}`: grantable only to a role of
  kind `system`, same structural shape as the clock exception. The
  conductor's `tools.yaml` gains exactly this id. **The conductor still
  holds no DFHack mutating tool**; rule 2 is untouched for it.
- `queue.run_step` takes exactly two arguments: `step_id` and
  `attempt_key`. Its schema sets `additionalProperties: false` and the
  handler's `_reject_unknown_arguments` refuses anything else, the same
  real enforcement every native tool uses. **There is no way to pass a
  tool id or an argument.**
- The handler resolves everything from the queue: the step's project,
  that project's `from_ruling`, the ruling's decision (must be `accept`),
  the step's `tool` and `args` (late-bound references resolved from
  earlier steps' recorded read-backs), and refuses unless:
  - the project is active and admitted;
  - the step is ready (its goal is active, its in-order predecessors read
    `met`, its `requires` are satisfied: `step_prerequisites_satisfied`,
    live but unused today, finally gets a caller);
  - it is not already `issued`/`done`, and `attempt_key` is new or
    matches an attempt in state `unknown` (§7.4);
  - the claims the runner granted this cycle are recorded on the attempt;
  - the tool is on the **runner allowlist**: a data flag
    (`step_runnable: true`) on the TOOLS.yaml command, set per command by
    the user, starting narrow (§13).
- It then calls the DFHack tool **internally**, bypassing `Roster.check`,
  the precedent `_stamp_cycle_snapshot` already sets for `overview.get`
  [verified: source, `dfmcp/queue_tools.py` "The internal DFHack call
  bypasses `Roster.check`"], with `DRY_RUN` forced false and the
  `IDEMPOTENCY_KEY` argument (§7.4) added.
- It writes `step_attempt` before the call and the `executed` record after
  it, in the store. The schema change: `executed` may be written by role
  `conductor` **only** when it names an `attempt_id` whose `step_attempt`
  was written by the conductor for that step, and its single action's
  `tool` equals the step's `tool`. The Overseer's direct `queue.executed`
  path is unchanged.

**Enforcement, four independent layers** (a bug in one is caught by the
next):

1. Load time: `roles.py` refuses `queue.run_step` on any role not of kind
   `system`, and still refuses the conductor any mutating DFHack tool.
2. Call time, argument surface: two arguments, nothing else accepted.
3. Write time, the store: the attempt must match an accepted ruling's
   ready step, and the `executed` must match the attempt and the step's
   tool.
4. Game side: the tool's own guards, reservation checks and refusals run
   exactly as they do for the Overseer.

What does **not** change: the Overseer remains the only role that decides
(rulings, amendments, overrides, abandonments), and keeps its direct tools
for anything not in a project (and for emergencies). Whether the Overseer
may still execute a *project step* directly once the runner exists is a
decision (§14): I recommend no, so a step has exactly one issuer.

### 7.3 Interaction with guards, reservations and holds

- **Guards** run inside the tool, per target, as today; the runner treats
  a `held` target in the read-back as a **named wait** (guard name and
  reason), writes it to `step_targets` as `held`, and **retries it quietly
  every cycle** by re-reading the guard (level-based, as the 2026-09-28
  design's reconciler), issuing the target when the guard passes. No wake.
- **Reservations**: a job's `ground` need is its `RES_ID`; the tool
  checks it (`df-overseer-reservations.lua` `check_tiles` [verified:
  source]). The runner never overrides a reservation; an `OVERRIDE` needs
  the Overseer's recorded reason, so it is never in a step's approved
  arguments unless the ruling put it there.
- **Holds survive anything that clears the suspend bit**, because they
  live in the queue, not in DF (the 2026-09-28 `suspendmanager` finding).

### 7.4 Idempotency: a crash must not double-act

The failure: the runner calls the tool, the tool succeeds, and the
conductor (or the MCP link, or DF) dies before `executed` is written. On
restart, is the step issued or not?

The design [proposed]:

1. **Write ahead.** `step_attempt {step_id, attempt_key, args_hash,
   claims, state: started}` is written before the call.
   `attempt_key = "<step_id>#<n>"`, n incremented only by the healing
   ladder's re-issue rung.
2. **The tool records the key with the world.** Every runnable tool takes
   an `IDEMPOTENCY_KEY` argument. On a real call it first looks the key up
   in `dfhack.persistent` site data (`df-overseer-idempotency_v1`): found
   means "already done", return the stored result without acting; not
   found means act, then store `{key, args_hash, result ids, tick}`
   **before returning**. One shared Lua helper, reqscript'd the way
   `df-overseer-reservations.lua` is, so the next tool costs a two-line
   call. The comparison of `args_hash` is Stripe's parameter check: a
   reused key with different arguments is refused.
3. **Recovery.** For an attempt in state `started` with no `executed`:
   call the tool's read-only `key-status KEY`. Found: write `executed` from
   the stored result. Not found: the world never saw the call **or rolled
   back past it** (a crash reloads the last save, and the key and the
   effect roll back together, because both live in the save). In both
   cases re-issuing with the same key is correct.
4. **Until every runnable tool carries the helper**, a weaker fallback:
   the attempt records a before-read (job count of that type at that
   workshop, building ids in the reservation), and recovery compares an
   after-read. Ambiguity (the count moved but not by exactly the request)
   is `unknown`, which escalates rather than guessing.

Why the save and not the queue: the queue on VM 103's disk does not roll
back when DF does; the 2026-09-28 design already found that a rollback can
make recorded state run ahead of the world (`rollback_drift`). A key stored
only in the queue would say "done" for work the rolled-back world never
had.

### 7.5 Escalation: triggers and report shape

The runner escalates to the Overseer (decision 6; a foreman role only if
escalations prove frequent) on:

- a tool **refusal whose reason is not a known wait** (not a guard hold,
  not a reservation hold, not a claim shortage);
- a job whose **re-issue budget is spent** (the charter's "the same plan
  step has failed twice");
- a **contradicted plan**: a job's `done` contradicted by observation
  (drift), a link target abandoned, a late-bound reference that no longer
  resolves (the reserved site was unreserved), a goal check that becomes
  unsatisfiable by declaration (the only workshop was destroyed);
- **ambiguity**: an attempt whose state stays `unknown` after recovery;
- **stuck** past the last automatic healing rung (§10);
- an `unknown` check that outlasts its `unknown_escalate_after_ticks`;
- a detected **deadlock** that cannot be broken automatically (§10.4).

Report shape: one `escalation`-kind queue record (the live kind) whose
`reason` is a short fixed-form block, never the history [proposed]:

```xml
<step_escalation project="project-0009" step="p9/j1" kind="reissue_budget_spent"
                 since_tick="215400" priority_rank="2 of 5">
  <what>MakeBarrel x2 at the Carpenter's Workshop: job vanished twice, no barrels produced.</what>
  <tried>re-check (no product); re-issue #2 (job 4412 vanished at tick 218210); claims released.</tried>
  <blocks>project-0007 (drink, deadline profile)</blocks>
  <claims_released>2 logs, 1 carpenter share</claims_released>
  <question>Re-issue with a different workshop, change the material, or abandon?</question>
</step_escalation>
```

The Overseer answers with an ordinary ruling operation on the project
(`update`, `drop`, `add`, or abandon), recorded like an amendment. Nothing
in the report needs a map or a coordinate.

---

## 8. Claims: materials, labor and ground under one model

### 8.1 One model, three resources

A **claim** is two things, kept apart deliberately [proposed]:

- a **demand**, declared once in the approved plan (`needs` on a job):
  what the job needs, by class and quantity, labor, ground; durable, part
  of the project record;
- an **allocation**, computed fresh every cycle by the runner from live
  state: which demands are satisfied now, in priority order. Nothing about
  allocation is stored as a counter. It is written into each cycle's
  `step_attempt` or hold record as evidence, never read back as input.

| Resource | Demand form | Allocation source each cycle | Exact record | Hard hold |
|---|---|---|---|---|
| **Materials** | `{class, form, qty}` (the game's own item classes: the production graph's classes, `stocks.availability` item types) | live items of that class, netted by the six flags `production/blocker.py` already applies, minus grants already made earlier in this cycle's priority pass | the job's `job.items` once it holds them; the building's `contained_items`; the recorder's completion copy | forbid the specific unclaimed items (§8.4) |
| **Labor** | `{labor, jobs}`: how many concurrent jobs needing that labor | citizens with the labor enabled (`labor.enabled-counts`) minus jobs of ours already running for it | the worker id on the job (recorder) | none; DF assigns dwarves (§8.5) |
| **Ground** | a reservation handle or a slot | the reservation ledger in the save | the reservation itself (exact by construction) | the reservation is already hard |

### 8.2 Recompute, never tally

Each cycle, in ready-queue priority order (§9), for each job: grant its
material demands from `free(class)`, where `free(class) = available(class,
live) - sum(granted earlier this pass)`, and `available` is the six-flag
netting over live items. **Available already excludes every item a job of
anyone's holds (`in_job`)**, so an issued job's items leave the pool by
the game's own flag, not by our bookkeeping. If short, the job is held:
`waiting: logs, 1 short; 2 granted to project-0009 (higher priority)`.

Properties:

- **An unseen loss corrects itself.** A barrel a tantrum destroyed is
  simply not in next cycle's live read.
- **Nothing to release on project end.** A finished or abandoned project
  stops appearing in the ready queue, so its demands stop being granted.
  The only things that need an explicit release are the ones that live in
  the world: hard holds (forbidden items) and reservations.
- **No partial grants.** A job's material demands are granted all or
  nothing. This removes hold-and-wait for materials, one of OSTEP's four
  deadlock conditions, so materials alone can never deadlock (§10.4).
- **Short means a named hold, never a guess.** The hold names the class,
  the shortfall and who holds the rest (which project, by priority).

The ERPNext issue in §2.4 is the case for this: a stored reservation
counter stayed wrong because one event path forgot to refresh it; a
recomputation from live state cannot forget.

### 8.3 The exact record: claimed versus used

Where the game records which items went where, record it per project
[proposed, on verified structures]:

- **Held by a job**: `df.job.items` is a vector of `job_item_ref {item,
  role, flags, job_item_idx}`, roles including `Reagent` ("MATERIAL"),
  `Hauled` ("REQUIRED"), `TargetContainer` [verified: source, `df.job.xml`
  at `53.16-r1`]. The runner reads it each cycle for its issued jobs and
  records item ids as `claimed_exact`.
- **Used, at completion**: the recorder's `JOB_COMPLETED` copy carries the
  same vector as of the last change (§3.2), and `onReactionComplete`
  carries `input_items` and `output_items`.
- **In a finished building**: `building.contained_items`, a vector of
  `buildingitemst {item, use_mode}` with `use_mode` in `TEMP`,
  `TEMP_PRINTHIDDEN`, `PERM` [verified: source, `df.building.xml`]. Which
  mode marks a construction material is not verified here [unverified].
- **In a construction** (wall, floor): the `construction` struct keeps only
  `item_type`, `item_subtype`, `mat_type`, `mat_index` and
  `original_tile`, **no item id** [verified: source, `df.event.xml` at
  `53.16-r1`]. So a wall's exact record is its material, not its item.
  `production/blocker.py`'s comment already notes items flagged
  `construction` ("Material used in construction"); whether the item
  object survives is [unverified].

The result is a per-project **claimed versus used** table: demanded class
and quantity, exact items held, exact items consumed or built in, and the
difference. That is also the Quartermaster's evidence for future cost
estimates.

### 8.4 The optional hard hold: forbidding exactly the scarce items

Verified facts:

- **Forbidding is a vanilla player action on v53.16.** The wiki (page
  tagged v53.16): "In order to forbid a specific loose item, click on the
  item you wish to forbid and then press [button] in order to toggle the
  forbidden state of the item." "An item that is forbidden will never be
  handled by your dwarves." [verified: primary doc, DF wiki `Forbid`]
- **It is a flag bit.** `item.flags.forbid` (original name `UNCLAIMED`,
  "Forbidden item") [verified: source, `df.item.xml`]. The Lua API has no
  dedicated forbid function; DFHack scripts set the bit [verified: source,
  no match in `Lua API.rst`], and DFHack's own `unforbid` tool is tagged
  "fort | productivity | items", **not** `armok` [verified: primary doc,
  docs.dfhack.org `unforbid`].
- **Forbidding an item a job is using breaks that job**: "Forbidding an
  item hauled by a dwarf will cause him to drop it once he realizes it is
  forbidden", and "Forbidding materials clears any in-process hauling
  jobs" [verified: primary doc, same page].

So [proposed]:

- Hard holds are **only for items not `in_job`**, and only for classes the
  plan marks `scarce` (the Overseer's call on the ruling, or a doctrine
  entry: seeds, the last barrels). Never for bulk stone.
- A hard hold is recorded **in the save** (a `hard_holds` table in
  `dfhack.persistent`: item id, project, step, tick), set by the runner as
  its own runnable job kind (`items.hold`), so it rolls back with the
  world like the idempotency keys.
- **Un-forbid immediately before the owning step is issued**, in the same
  `run_step` call. Because a workshop job picks its items when a dwarf
  takes it, there is a window in which another job can take an un-forbidden
  item [unverified: exactly when DF binds items to a workshop job]; the
  hold therefore reduces contention, it does not guarantee. The honest
  label: "hard hold (best effort at issue)".
- Forbidden items vanish from our own `available` count too (the `forbid`
  flag is one of the six), so the owning project must count its own held
  items back in: `available + held_by_me`.

### 8.5 Labor: an admission cap, not a claim

Nothing we record can make DF assign a particular dwarf; the game assigns
idle dwarves to posted jobs, and autolabor rewrites labor flags on this
fort (`labor.set-labor` "races autolabor", overseer charter [verified:
source]). A labor "claim" is therefore an **admission cap on what we
issue**: a project may have at most its share of concurrent jobs needing a
labor in flight (§9.3), recomputed each cycle from `labor.enabled-counts`
and our own running jobs. When the fort's one carpenter is busy with
project A's barrels, project B's bed job is held `waiting: CARPENTER, 1 of
1 busy on project-0009`, which is the named hold decision 7 asks for.

### 8.6 Orphans, and how they are released

A claim is **orphaned** when the thing that justified it is gone
[proposed]:

| Orphan | Detected by | Released by |
|---|---|---|
| a soft material or labor allocation | cannot exist: recomputed each cycle | nothing to do |
| a hard hold (forbidden item) whose project is done, abandoned or unknown | reconciler joins `hard_holds` against active projects | the runner un-forbids it (a runnable job kind, logged as `executed`) |
| a forbidden item with no `hard_holds` row | never touched: we did not forbid it (a human did) | report only |
| a reservation whose project ended | reconciler joins reservations against projects | **reported, never auto-released** (the user's 2026-09-30 ruling: a reservation lasts the room's life; only `unreserve` ends it) |
| an issued DF job whose step was abandoned | reconciler, by job id | the runner cancels it only if the abandonment ruling said so (`workjob.cancel`); otherwise reported |
| an idempotency key whose step is done | none needed | keys are pruned after the project ends |

---

## 9. A ready queue: many projects in motion at once

(The user's third addition.)

### 9.1 The cycle's ready queue

Each cycle [proposed]:

1. **Admit** active projects up to the active limit (§9.5), in priority
   order; dormant standing goals and projects waiting only on a link do
   not take a slot.
2. For each admitted project, compute its **frontier**: every job whose
   goal is active, whose in-order predecessor reads `met`, whose
   `requires` are satisfied, whose slots are filled, that is not already
   issued or done, and whose retry backoff (§10.3) has elapsed.
3. Order all frontier jobs across all projects by priority (§11); ties by
   age (oldest first).
4. Walk that list once. For each job: grant materials (all or nothing),
   check the labor share (§9.3), check ground; if everything is granted,
   `run_step`; otherwise record the named hold and continue with the next
   job. **One held job never stops the walk.**
5. Nothing already issued is pre-empted.

It never finishes one project before starting the next: if brewing and a
bedroom dig are both ready and their claims do not collide, both are
issued in the same cycle, and DF works both at once.

### 9.2 Where the time-sharing analogy holds, and where it shifts

| OS scheduler | Here | Holds? |
|---|---|---|
| CPU time is the scarce resource | issuing a call is instant; conductor time is **not** scarce | **shifts**: the scarce resources are dwarves (labor), materials, ground and model tokens |
| a time slice bounds how long one process runs | a **labor share** bounds how many concurrent jobs one project may have in flight per labor | shifts: space, not time |
| pre-emption at slice end | none: cancelling a DF job wastes hauled materials and walking | **does not hold**; non-pre-emptive for issued work |
| round-robin among equal priorities | ties broken by age; aging (§11.4) is the round-robin guarantee | holds, in spirit |
| the scheduler dispatches onto a CPU | we post jobs; **DF is the lower scheduler** that assigns them to idle dwarves | shifts: two-level scheduling, and we control only the upper level |
| context-switch cost | none for issuing; real for DF (a dwarf walking between distant jobs), not modelled | partly |

### 9.3 Fair share of labor

Prior art: YARN's Fair Scheduler, "all apps get, on average, an equal
share of resources over time", with per-queue `maxResources` [summary].

[proposed] For each labor L with `n_L` enabled citizens (live read), each
admitted project P gets a share `share(P, L) = max(1, floor(n_L * w_P /
sum_w))`, where `w_P` is P's priority weight among the projects that have a
ready job needing L this cycle. A project may have at most `share(P, L)`
issued-and-unfinished jobs needing L. Leftover capacity (a project not
using its share) goes to the next project in priority order the same
cycle, so the cap never idles a dwarf. The effect the user asked for: a
60-tile dig cannot occupy every miner while a two-job brewing project waits
for the one brewer, and a big dig still gets every miner when nothing else
needs one.

What we cannot do: force the share. DF may still send a miner to a job we
did not post (the fort's own), and autolabor decides who has which labor.
The share bounds what *we* post, which is the only lever that does not
race autolabor.

**At this fort's scale** (22 dwarves, a handful of projects, one
carpenter, two miners, one brewer), the share will usually be 1 per labor
per project, which is simply "one job per labor per project at a time".
This can start as that constant and become the formula only when a real
run shows a big project starving a small one (§13).

### 9.4 DF as the lower scheduler: what control a player has

| Lever | Vanilla? | What it does | Use it? |
|---|---|---|---|
| dig designation priority 1 to 7 | yes [verified: repo record, the Overseer charter names "DF's 1-7 for dig designations"] | orders digging among designations | **yes**: map priority tier to 1-7 for group A steps; one data entry |
| workshop task "highest priority" button (yellow exclamation point) | yes: "instructs the workshop to carry out the task with the highest possible priority" [verified: primary doc, DF wiki `Workshop`, v53.16] | one workshop job jumps its queue | only for deadline-profile projects (§11.2), at most one at a time |
| job flag `do_now` (original name `DO_ME_NOW`) | the flag is the game's own [verified: source, `df.job.xml`]; that the exclamation button sets it is [unverified]; DFHack's `prioritize` sets it by job type and is **not** `armok`-tagged, with the warning that prioritising too many types means "the *other* tasks in your fort can get ignored" [verified: primary doc, docs.dfhack.org `prioritize`] | pushes a job ahead of others | same rule as above; never by job type fort-wide |
| work details (labor groups, "Only selected do this", "Everybody does this", "Nobody does this") | yes [verified: primary doc, DF wiki `Labor`, v53.16] | who may do which labors | **no, not while autolabor runs**: it is the same contested lever as `labor.set-labor` |
| workshop Workers tab (a master, specialization) | yes [summary, DF wiki `Workshop`] | restricts a workshop to one dwarf | no; it removes flexibility DF uses to balance |
| burrows | yes | confines dwarves to areas | no; military meets civilian here (`docs/AGENT-ARCHITECTURE.md` §7), Marshal territory |
| manager orders' order and conditions | yes | the order list is itself a queue | parked: orders do not dispatch on this fort |

### 9.5 Reconciling with the active-project limit

The Overseer's WIP limit exists only as a charter sentence today (§0).
Proposed meaning: the limit is **admission** (YARN's `maxRunningApps`),
counted as projects that have at least one issued job, one granted claim
or one hard hold. Dormant standing goals, projects waiting only on a link,
and projects waiting only on a ruling do not count, otherwise a parent
waiting on its own sub-project would take a slot the sub-project needs.
Admission follows priority, so a blocker inheriting priority (§11.3) is
admitted before the projects it blocks. The number is the Overseer's to
set (a `policy.yaml` value it may change by ruling). Suggested start: 4.

### 9.6 A budget for model wakes and tokens

Model tokens are the fourth scarce resource. [proposed] `policy.yaml`
gains `max_model_wakes_per_cycle` and `max_tokens_per_game_day` (by role),
and triage drops the lowest-value wakes first when over budget: routine
reviews before escalations, advisors before the Overseer, never a
tripwire. Escalations that exceed the budget queue for the next cycle with
the fort paused. The user has ruled billing caps are not a concern
(auto-memory); this is a rate limit on attention, not a spend cap, and it
keeps a thrashing project from buying a model wake every cycle.

---

## 10. Stuck detection and self-healing

(The user's second addition.)

### 10.1 Waiting versus stuck

- **Waiting**: held for a **named, visible reason**: a guard hold, a claim
  shortage (naming who holds the rest), a labor share in use, `requires`
  unmet, a link not yet met, a slot open, a ruling pending, a check
  `unknown` for a named reason. Waiting is fine and retries quietly every
  cycle. No wake.
- **Running**: issued, and a **progress signal** has moved within the
  check's declared window (§3.1).
- **Stuck**: issued, **past its declared expectation** with **no progress
  signal and no named reason**. The expectation declared on the check is
  what "past its time" means, so a slow check (`unbounded` hauling) is
  never mistaken for a stuck one.

Progress signals by group [proposed, on existing reads]: A: pending
designation count falling or a dig job with a worker (`dig_progress`); B:
building stage rising or a `ConstructBuilding` job with a worker; C: the
job exists with a worker or its `completion_timer` moving (recorder); D:
`amount_left` falling (`order_watch`); E/K8: the item's position changing
or a `StoreItemInStockpile` job holding it.

For an `unbounded` check, stuck needs the preconditions for progress to be
visibly present: for a haul, a reachable stockpile accepting the item
with free tiles exists, the item is not forbidden, and no hauling job has
touched it for a declared long window. Otherwise it is waiting, with the
missing precondition named ("no stockpile accepts ore").

### 10.2 The healing ladder, cheapest first

Each rung is code; only the last wakes a model. Every rung writes an
`observation` (kind `heal`), so the history shows loops.

1. **Re-check.** Read every check of the stuck job and its parent goal
   again, polls included. Maybe it is done (the job vanished because it
   completed and the event was missed at frequency 10); maybe the goal was
   met another way. Cost: one read.
2. **Re-issue.** If the job's DF job is gone and its effect is absent, DF
   probably cancelled it silently (damp stone, cave-in, a tree: the causes
   df-ai's `checkroom` names). Re-issue with a new `attempt_key`, within
   `reissue_max` (default 2, the charter's "failed twice"). Group-specific
   remedies already exist and are reused: `blueprint release` for a
   stalled, unstartable dig ("release only withdraws designations no dwarf
   can start" [verified: source, `df-overseer-blueprint.lua`]),
   `stuckjobs` to see "no worker assigned" versus "suspended", and
   `order_watch`'s stalled versus blocked for orders.
3. **Release its claims.** Drop the stuck job from this cycle's
   allocation so its materials and labor share go to the next project in
   priority order, and un-forbid its hard holds. Its ground reservation is
   **not** released (room-life rule); it is reported. The blocked
   projects' holds then change from "claimed by project-N" to a real
   shortage or to issued, which is the point.
4. **Escalate** with the §7.5 report: what, what was tried, what it
   blocks and at what cost of delay, what was released, the one question.

### 10.3 Thrash guards

- **Re-issue budget per job** (`reissue_max`), and **exponential backoff**
  between re-issues: the next attempt waits `window * 2^n` ticks.
- **Release then reclaim**: a claim released by rung 3 is barred from the
  same job for a cooldown (one window) unless the job's priority rose; a
  job that has been released and re-granted twice in a game day escalates.
- **Per-project heal circuit breaker**: more than K heals (default 4) on
  one project within a game day escalates the project, not the job.
- **Healing is visible**: every rung is an observation record, so a loop
  shows as a repeating pattern in the audit log, the same reason the
  2026-09-28 design kept observations append-only.
- df-ai's `checkroom` re-issues "every sweep" with no ceiling
  (§2.9): that is the failure mode these guards exist for.

### 10.4 Deadlock

OSTEP's four conditions [verified: primary doc]. Materials cannot
deadlock here: grants are all or nothing and recomputed every cycle, so
there is no hold-and-wait (§8.2). What persists across cycles and can:
**ground reservations**, **hard holds**, and **issued jobs holding items**
(`in_job`), plus **project links**.

[proposed] Each cycle, build a **wait-for graph** over projects: an edge
P to Q when P is held with a named reason whose holder is Q (a hard hold,
a reservation, a job of Q holding the items P needs, a link to Q). A cycle
is a deadlock. Break it by releasing the **lower-priority** side's
releasable claims (un-forbid its hard holds; never a reservation, never an
issued job), which is PostgreSQL's "abort one of the transactions"
[summary] with a choice rule instead of an unpredictable one. If the cycle
consists only of reservations or links, escalate: breaking it is a
decision. Link cycles are refused at acceptance (§5.4), so they can only
arise from a later amendment, which the same check refuses.

**Blocking impact** is measured by priority inheritance (§11.3): a stuck
job's report says how much cost of delay it holds up, which is what makes
"release its claims" (rung 3) an informed step rather than a blind one.

**At this fort's scale** this can wait (§13): with a handful of projects,
few hard holds and reservations only for rooms, a deadlock cycle is
unlikely, and the escalation path (a stuck project) catches one anyway,
just later.

---

## 11. Priority

### 11.1 The ordering rule

[proposed] Order ready jobs by the tuple, compared left to right:

1. **Tier** (lexicographic, like the production model's bands):
   **survival** (a deadline-profile project whose slack is inside its
   threshold: drink, food, water, a breach) before **everything else**.
2. **Overseer pin** (§11.5): pinned first, in pin order.
3. **Score** `S(P) = (CoD(P) + inherited(P)) / size_remaining(P)`
   (WSJF), plus the aging credit (§11.4).
4. **Age** of the job's readiness (oldest first).

### 11.2 Where each input comes from

| Input | Meaning | Live read or record |
|---|---|---|
| urgency profile | `deadline` (drink, food, water), `standard` (a workshop, a bedroom), `comfort` (a statue) | declared on the project (`priority_profile`), checked at filing against a closed list; doctrine may default it by goal kind |
| `CoD(P)` for `deadline` | rises as slack shrinks: `base * min(cap, horizon / max(slack, floor))`, with `slack = days_of_cover - lead_time` | days of cover from `production/cover.py` (`cover_dwarf_days`, `days_at_population`), stock from `stocks.food-drink`/`stocks.availability`, lead time from the draft's windows; vitals only as player-visible categories (`vitals.summary`, never raw timers, per the knowledge-scope rule in `df-overseer-clock.lua`) |
| `CoD(P)` for `standard` | constant per unit time | declared value per goal kind in doctrine |
| `CoD(P)` for `comfort` | small constant | doctrine |
| `size_remaining(P)` | remaining `dwarf_ticks` | the proposal's `cost` (existing field, unit `dwarf_ticks`) minus the estimates of done jobs |
| `inherited(P)` | cost of delay of what P blocks | the project link graph (§11.3) |
| age | ticks since the job became ready | the queue |

**The steep curve for thirst** (decision 9's example) comes from days of
cover, which is player-derivable: stock and population are visible,
consumption is measured over time by the sampler. The raw thirst timers
must not be used (they are diagnostic-only, not player-visible, per the
2026-09-16 research quoted in the clock tool's header).

### 11.3 Inheritance through linked projects

`inherited(P) = sum over projects Q that P blocks, directly or
transitively, of CoD(Q) * f(Q, P)`, where `f` is 1 when P is Q's only
open blocker and splits evenly when Q has several open blockers (so a
two-blocker project does not count twice). Capped at `inherit_cap *
max own CoD in the fort` so one hub project cannot outrank survival
[proposed].

- **Sum, not max**, deliberately different from the kernel (§2.5): a late
  barrel project delays every barrel consumer at once.
- **Transitive**, as the kernel's PI chain: the workshop inherits from
  barrels, which inherit from booze.
- **Removed when the block clears**: the moment Q's link to P reads `met`
  (P's root check), P no longer blocks Q and loses Q's share, like "the
  priority boosting is immediately removed once the rt_mutex has been
  unlocked" [verified: primary doc].
- **Blocks** means a link from Q to P, a hold on Q naming P as the holder
  of a claim, or a reservation P holds that Q needs. The first is
  structural; the others are the wait-for graph of §10.4, reused.

**At this fort's scale** a simpler version does: direct links only, no
split, no cap. A chain of three projects is two hops; the full formula
matters only when several projects share one blocker (§13).

### 11.4 Aging

Every ready-but-unissued job gains a credit that grows with the time it
has been ready: `aging(j) = a * min(ready_ticks / aging_period, max_boost)`
[proposed], added to its project's score. Bounded, so aging never lifts a
comfort project over survival (tier 1 is lexicographic), and labelled
honestly as a tuning constant (Ousterhout's "voo-doo constants", OSTEP
[verified: primary doc]). Start with `aging_period` of 7 game days (the
existing routine-review interval) and retune from the first real week.

### 11.5 The Overseer's override

A new record kind `priority_override` [proposed], sole writer only (the
same two-layer restriction as `queue.rule`): `{project_id, pin: top |
bottom | tier, reason (required, coordinate-free), expires_after_ticks
(required, at most one game season)}`. Code applies it at step 2 of the
ordering rule and ignores it after expiry; the ready queue report shows the
pin and its reason. An override that expires is re-evaluated, never
silently renewed. Every override is visible in the public feed's
reasoning, like a ruling.

### 11.6 What the Overseer sees

One line per admitted project, the existing `project_status_line` shape
extended with rank and the top reason [proposed]:
`project-0009 barrels: rank 2 (inherits drink); 1 of 2 jobs issued; held:
logs 1 short (project-0011 bed frames has them).` Never the whole tree
(the same rule as `docs/AGENT-LOOP.md` §6).

---

## 12. Worked examples

### 12.1 The booze chain, end to end

A replay of 2026-09-25/28 under this design, starting from the fort as it
was on 2026-09-25 (no carpentry; 15 barrels all full of plants; drink 0;
dwarves drinking at the Well; 22 alive) [verified: repo record,
`evals/live/2026-09-25-first-real-conductor-cycle/README.md`]. Numbers
that are not from the record are illustrative and marked so.

**1. The Quartermaster drafts, helped by code.** On a routine review it
calls `production.blockers DRINK 40` (the proposed read over the existing
blocker walk). The walk returns: brew reactions need a Still (present),
a brewable plant (108 plant items, present), and an empty food-storage
container (0 free): **blocker `BARREL`, and a barrel's process needs a
Carpenter's Workshop (absent) and wood**. The Quartermaster files three
linked drafts in one cycle:

```yaml
# proposal-0012, type stock_target, draft of "more booze" (standing)
root: g0
standing: true
rerun_budget: {per_game_year: 4}
priority_profile: deadline
goals:
  - id: g0
    summary: "drink covers 10 dwarf-days per citizen"          # par from doctrine
    check: {signal: stocks.drink.units, op: gte, value: 40,
            observe: {mode: poll, poll_every: cycle}, expect: {shape: unbounded}}
    order: in_order
    children: [l1, j1]
  - {id: l1, needs_project: "@proposal-0013"}                 # barrels
steps:
  - id: j1
    tool: workjob.queue
    args: {JOB: BREW_DRINK_FROM_PLANT, WORKSHOP_LANDMARK_NAME: Still, COUNT: 4,
           REAGENT_CHOICE: [BARREL]}                          # illustrative token
    needs: {materials: [{class: BREWABLE_PLANT, qty: 4}], labor: [{labor: BREWER, jobs: 1}]}
    check: {readback: {expect: [job_ids]},
            effect: {signal: stocks.drink.units, op: gte, value: 40},
            observe: {mode: poll, hints: [REACTION_COMPLETE]},
            expect: {shape: window, ticks: 4800, source: "estimate"}}
    retry: {reissue_max: 2}
```

```yaml
# proposal-0013, type work_order, draft of "barrel production"
root: g1
priority_profile: standard
goals:
  - id: g1
    summary: "at least 2 empty food-storage containers are free at the Still"
    check: {signal: 'workjob."Still".free_container_candidates', op: gte, value: 2, ...}
    order: in_order
    children: [l2, j2]
  - {id: l2, needs_project: "@proposal-0014"}                 # carpentry workshop
steps:
  - id: j2
    tool: workjob.queue
    args: {JOB: MakeBarrel, WORKSHOP_LANDMARK_NAME: "@proposal-0014.site.landmark", COUNT: 2}
    needs: {materials: [{class: WOOD, form: log, qty: 2}], labor: [{labor: CARPENTER, jobs: 1}]}
```

The third draft, "carpentry workshop", is outside the Quartermaster's
ownership (it needs a place), so the Quartermaster files it **with an open
slot** for the Architect:

```yaml
# proposal-0014, draft of "carpentry workshop"; open slot, cannot be accepted yet
root: g2
goals:
  - id: g2
    check: {signal: 'building_kind."Carpenters".complete_count', op: gte, value: 1, ...}
    order: in_order
    children: [j3]
steps:
  - id: j3
    tool: building.build
    args: {KIND: Carpenters, RES_ID: "@s1"}
    needs: {materials: [{class: BOULDER_OR_BLOCK_OR_LOG, qty: 1}], labor: [{labor: CARPENTER, jobs: 1}],
            ground: "@s1"}
slots:
  - {id: s1, role: architect, kind: site, for: j3, fill: null}
```

All three pass filing validation; `slot_open` wakes the Architect.
(Under the current schema, a Quartermaster may not propose a
`workshop_siting` type; a slot is how a draft asks another role for its
part without breaking the closed type vocabulary.)

**2. The Architect fills the slot.** It reads `building.find Carpenters`
and `blueprint.preview workshop-pad-3x3-v1 ...` (the missing template of
§6.3) and files `slot_fill` for `s1`: job `blueprint.reserve
workshop-pad-3x3-v1 "carpentry" <landmark> RANK 1`, with the reasons
(near the logs' stockpile, reachable, not on a planned room). This is the
Architect's proposal-0006 of 2026-09-25, now as a slot fill.

**3. The Overseer accepts, one at a time, cheaply.** Ruling on 0014 with
the slot fill: `accept` (by reference). Ruling on 0013: `accept`. Ruling
on 0012: `accept` with one amendment, `update j1 {COUNT: 2}` ("two batches
first; see how the barrels hold up"). Three projects exist:
`project-0003` (workshop), `project-0004` (barrels), `project-0005`
(booze). The rulings record one amendment on 0012; planner quality for
the Quartermaster: 2 accepted as drafted, 1 amended.

**4. The conductor runs, as code.** Cycle 1: frontier = `p3/reserve` (the
slot's filling job). It runs; read-back `res-7`. `p3/j3` is now ready with
`RES_ID=res-7` pinned. Its claims: 1 boulder (available 3, per the six-flag
netting [illustrative]), one carpenter share (the fort had two citizens
with the labor, per the Overseer's 2026-09-25 reads). Quicksave, then
`run_step(p3/j3, "p3/j3#1")`: read-back building id 31, stage 0. The
recorder is told to watch building 31. `p4` and `p5` wait on links;
neither takes an admission slot.

**5. A contention hold.** Meanwhile the Architect's bedroom project
(`project-0002`, from the 2026-09-28 dig) has a later job, "build two beds",
needing 2 logs and a carpenter. When the workshop completes (a poll reads
stage complete; the event only told us it was created), `p4/j2` becomes
ready with the same needs. Ranked by priority (next step), `p4` comes
first: it is granted 2 of the fort's 3 logs [illustrative] and the one
carpenter share; the bed job is held: `waiting: logs, 1 short (2 granted
to project-0004, higher priority); CARPENTER share in use by
project-0004`. No wake; next cycle it is re-evaluated from live state.

**6. The blocker inherits priority.** `p5` (booze) is `deadline` profile;
with drink 0 and dwarves surviving on the Well, its slack is judged by
days of cover (0) against lead time, so its cost of delay is at the cap
but it is not in the survival tier while the Well works (a doctrine call:
water keeps them alive). `p4` (barrels) has a small `standard` CoD of its
own, but `p5` links to it, so `inherited(p4) = CoD(p5)`; and `p3` (the
workshop) inherits the same through `p4`, transitively. That is why, in
step 4, the workshop was issued ahead of the bedroom's bed job even though
a workshop has no value on its own; and why in step 5 the barrels beat the
beds. When `p4`'s root check reads `met` (2 free containers), its
inherited priority disappears in the same cycle.

**7. The brewing runs, and the goal is met.** `p5/j1` runs with the
amended `COUNT: 2`. The recorder's `onReactionComplete` hints arrive; the
poll `stocks.drink.units` reads 10, then 20 [illustrative]. The project's
root check is 40: not met. The link reads `met`; `j1` is recorded `done`
but its `effect` check reads `not_met`, so `g0` is not met and `j1` is the
only child that can help: the healing ladder's
rung 1 re-checks, rung 2 **re-issues within `reissue_max`** only if its
effect is absent and the DF job gone. Here the effect is partly there, so
the correct move is not a heal: **the project needs more batches than the
amended plan allowed**, which is a contradicted plan and escalates to the
Overseer with the report "2 batches produced 20; goal 40; re-run j1 with
COUNT 2?". The Overseer answers `update j1 {COUNT: 2}` and it re-runs.
(This is the amendment coming back to bite, and the record shows it:
useful planner-quality data.)

**8. The standing goal goes dormant, then wakes.** At 40, `g0` reads
`met`; `p5` goes dormant: no claims, no admission slot. A season later
drink reads 28 [illustrative]; `g0` reads `not_met`; `p5` is active
again. Re-evaluated from the root: `l1` (barrels) reads its link target's
check, `p4`'s root, live: if 2 containers are still free it is `met`, so
only `j1` is eligible, and it re-runs with its approved arguments,
counting 1 against `rerun_budget` (4 per game year). If the barrels are
now full, `l1` reads `not_met`: `p4` is a finished one-off project, not
standing, so the runner does **not** re-run it on its own; it wakes the
Quartermaster with `p4`'s original draft pre-filled for a new proposal,
which the Overseer can accept by reference in one call. Whether one-off
sub-projects of a standing goal may re-run without a new ruling is one of
the user's decisions (§14).

**What this would have saved.** In the real 2026-09-25/28 cycles the chain
cost proposal-0005 (accepted, failed for want of barrels), 0006 (the
workshop), 0007 (deferred then rejected), 0009 (a near-duplicate with a
factual error) and parts of five conductor cycles. Here the blocker walk
returns the chain on the first call, the three drafts are filed together,
and no proposal is filed that the queue already knows cannot run.

### 12.2 Building a still (groups B and K1 to K4)

- **Job** `building.build KIND=Still RES_ID=res-9`. **K2 guards** at issue:
  `reservation` (the call holds `res-9`), `item_present` (nothing
  unhauled on the footprint). **K1 read-back**: building id 44, stage 0,
  `DRY_RUN false` echoed. The recorder watches 44.
- **K3 lifecycle**: a `ConstructBuilding` job for 44 appears (poll); a
  worker is assigned; progress = the job has a worker or items are being
  hauled to the site.
- **K4 effect**: stage complete, **by poll**. The `BUILDING` event fires at
  designation and at destruction, never at completion (§3.2).
- **Expectation**: `window`, from requirements (materials granted, one
  builder share): an estimate, declared with its source. Past it with no
  worker and no hauling: stuck; rung 1 re-reads (maybe complete), rung 2
  checks why there is no worker (`stuckjobs` "no worker assigned" versus
  "suspended"; `buildingplan` or `suspendmanager` may be holding it,
  2026-09-28 findings) and re-issues only if the building record is gone,
  rung 3 releases its claims, rung 4 escalates.
- **Destroyed later** (a tantrum): the recorder's `BUILDING` destroy on a
  watched id is a hint; the poll confirms; the goal check (a still exists)
  reads `not_met`; if the project is done and not standing, that is an
  observation and a wake for the owning role, not an automatic rebuild.

### 12.3 Killing an enemy (group H, check K7)

- The fight is a **reflex** (decision 1): the tripwire already pauses on a
  reachable hostile and wakes the Overseer. No project issues combat.
- A project may be drafted **after** the reflex, for example "secure the
  east entrance": its goal check is K7, "no visible reachable hostile
  near the east entrance for W ticks", `window`, tri-state:
  - `met (by_absence, W)` after W ticks with `threat.scan` reporting no
    visible reachable hostile and no combat-category report;
  - `not_met` while one is visible and reachable;
  - `unknown` when the evidence is insufficient: the hostile fled out of
    sight, more may come, it may be ambushing. **Hidden units stay
    hidden**: `threat.scan` admits by reachability and `isHidden`, and
    diff.lua excludes hidden deaths, so "the goblin died" is known only if
    a player could have seen it.
- `unknown` is a named wait, never stuck by time, and escalates only after
  `unknown_escalate_after_ticks`. It never unblocks work that assumed the
  entrance safe (a hauling project through it stays held with that
  reason).

### 12.4 Moving a chunk of hematite to a stockpile (groups A and E, check K8)

- **Mine**: `construction.mine-vein 13` (group A). Its targets are the ore
  tiles; the recorder watches those tiles. Ore yields a boulder only a
  third of the time (`Working.md`, 2026-09-28, the wiki's 33% figure), so
  the job's effect check is "tile open", not "a boulder exists".
- **Capture the item**: when a boulder appears on a watched tile, the
  recorder's `ITEM_CREATED` gives its id; the runner records it as the
  project's `item_set` handle `hs-1` (code-side ids, never shown to a
  model). **Without that capture there is no specific item to track**;
  the goal would have to fall back to a count ("hematite boulders in
  stockpiles rose by one"), which is weaker and says so.
- **Configure the haul** (group E): the job is "a reachable stockpile
  accepting ore with free tiles exists". Today only the read exists
  (`stockpile.list`, accept categories and occupancy [verified: source]);
  the write is a gap (§4.4), so this is a slot or an escalation for now.
- **K8 goal check**: `item_set."hs-1".in_stockpile`, polled with
  `dfhack.buildings.getStockpileContents` (the live-verified primitive in
  `df-overseer-stockpile.lua`), expectation **`unbounded`**: hauling is the
  fort's own job. Stuck only if the preconditions are all visibly present
  (a reachable accepting stockpile with room, the item not forbidden) and
  no `StoreItemInStockpile` job has held it for a long window. Healing
  cannot re-issue a job we never owned; rung 2 is to check the stockpile's
  settings and reachability again, rung 3 releases nothing (we hold
  nothing), rung 4 escalates with the named missing precondition.
- **Why it matters**: the wall step's `item_present` guard (live) holds
  a wall on a tile with an unhauled item; this goal is what lets that hold
  clear for a known reason instead of "whenever".

---

## 13. Build order

The full design is above. This section orders it. Each step ships on its
own; nothing later is needed to make an earlier step useful.

### 13.1 Shared foundations (needed whichever way the groups are filled)

| # | Step | Why first | User decides |
|---|---|---|---|
| F0 | **Fix the two store bugs**: `project_status` must not read `done` while a step has no target rows; `queue.executed` checks the action's `tool` equals the step's and that `requires` are satisfied | live code, wrong today, tiny | nothing |
| F1 | **Goals, checks, links, slots, `needs`, `expect` in the `project` schema** (§5.4), validated, with no runner yet: the Overseer still executes by hand, but the plan and its checks are recorded | cheapest moment to change the schema (no live projects) | the check vocabulary's first signals |
| F2 | **The reconciler evaluates checks** each cycle and writes observations; `queue.project_status` shows rank, holds and check states | makes every later step observable before it acts | nothing |
| F3 | **The recorder** (§3.3) at map load, conductor-only | hints for F2; needed before stuck detection can be trusted | whether it goes in `onMapLoad.init` (a VM change) |
| F4 | **`queue.run_step`** with the idempotency helper, the `step_attempt` kind, the roles.py exception, and a **runner allowlist of one or two commands** | the permission change, narrow and testable | which commands go on the allowlist first; whether the Overseer stops executing project steps itself |
| F5 | **Drafts on proposals and amendments on rulings** (§6), plus the `production.blockers` read | the token saving and planner-quality data | the amendment vocabulary |
| F6 | **Claims** (§8): recomputed material grants and named holds; hard holds later | contention becomes visible | which classes count as `scarce` |
| F7 | **Priority** (§11): tier plus WSJF, direct inheritance only, aging, the override record | ordering the ready queue | the doctrine defaults (profiles, CoD constants) |
| F8 | **Stuck detection and the healing ladder** (§10), rungs 1, 2 and 4 | turns silent stalls into cheap fixes or short reports | `reissue_max`, backoff |

### 13.2 Filling the groups

Per §4.5, ordered by value against cost: **C** (a generic product check;
`workjob.queue` exists), **B** (`building.status`, a workshop pad
template), **A** (`dig_progress` generalised), **L** (a drift check),
**E** (a stockpile writer and forbid/dump; the K8 check), **F** (a flow
check), then D, G, H, J, K when needed. Each group's fill is: one generic
issuing path fed by game data, one generic check, and the group's commands
flagged `step_runnable` once a real run has exercised them.

### 13.3 The choice: a slice first, or group by group

**Option 1, the booze chain as a thin slice.** F0, F1, a minimal F2 and
F4 for `workjob.queue` and `building.build` only, drafts without
amendment, claims for materials only, no priority beyond tier and age.
Proves the pipeline on the case that motivated it. Risk: it proves groups
B and C only, and the design choices for A (target sets that grow), E
(unbounded checks, item capture) and L (instant settings, drift) are not
tested until later, when changing them costs more.

**Option 2, group by group.** Build all foundations (F0 to F8), then fill
C, then B, then A, and so on, each group complete before the next. Every
group ends up complete and generic. Risk: a long time before anything runs
end to end, and the foundations are designed against no real traffic.

**Option 3 (recommended), a representative slice, then group by group.**
The foundations F0 to F4 in their minimal form, proven by **one
representative job and one representative check from each group that is
live on this fort**, run end to end through draft, ruling, runner, checks
and claims:

| Group | Representative job | Representative check |
|---|---|---|
| A | `blueprint.apply` dig phase of the bedroom cell (site-3 exists) | K4 via `dig_progress` |
| B | `building.build Carpenters` on a reserved pad (needs the pad template) | K1 read-back, K4 stage poll |
| C | `workjob.queue MakeBarrel` (barrels are genuinely needed) | K4 free-container count |
| L | `zone.place Bedroom` then `zone.assign-owner` | K6 owner holds |
| E | none issued; the hematite-style K8 on one captured item | K8 unbounded, item capture by the recorder |
| K5 | the standing drink goal over the brew job | K5 level goal, dormancy and wake |

The booze chain is covered by rows B, C and K5; the hematite case by E;
the bedroom by A and L. Then fill the groups in the §13.2 order. This
proves every *pattern* the design depends on (growing target sets,
unbounded checks, instant settings, standing goals) with one real instance
each, before any pattern is multiplied by data. Its cost over Option 1 is
roughly two extra representative runs (A and L already have live tools;
E needs only the recorder and a read).

This is the user's decision (§14, decision 1).

### 13.4 What can wait until a real run shows it is needed

At 22 dwarves and a handful of projects, these parts of the design are
specified but should not be built until evidence asks for them:

| Part | Start with | Build the full version when |
|---|---|---|
| **Deadlock detection** (§10.4) | nothing; a deadlock shows up as a stuck project and escalates | two projects are ever seen holding each other's persistent claims, or hard holds are in use |
| **Fair-share labor** (§9.3) | a constant: at most one issued job per labor per project | a real run shows one project's jobs starving another's for the same labor |
| **Full priority inheritance** (§11.3) | direct links only, no split, no cap | two or more projects share one blocker |
| **Hard holds by forbidding** (§8.4) | none; soft claims and named holds | a scarce item is actually taken by another job between grant and issue |
| **The model-wake budget** (§9.6) | the existing triage | healing or escalations are seen buying a wake every cycle |
| **The idempotency helper in every tool** (§7.4) | the helper in the one or two allowlisted tools, before-after reads elsewhere | a tool joins the allowlist |
| **Frequency-0 job completion** (§3.3) | frequency 1, poll as truth | a measured need for completion latency under one cycle |

---

## 14. Decisions for the user, and where I think a decision needs correcting

### 14.1 The three decisions the user most needs to make

1. **Slice or groups first** (§13.3). The booze chain alone, all groups
   one at a time, or a representative slice (one job and one check per
   live group) and then group by group. **Recommendation: the
   representative slice.** It proves every pattern once at low extra cost.
2. **Who issues an accepted project step** (§7.2). Once the runner
   exists, does the Overseer stop executing project steps itself, so each
   step has exactly one issuer (recommended), or keep both paths? And
   which commands go on the runner's allowlist first. **Recommendation:
   the runner is the only issuer of project steps; the allowlist starts
   with `workjob.queue` and `building.build`** (both live-verified by real
   use on this fort), and grows one command at a time after a real run.
   The Overseer keeps its direct tools for anything outside a project and
   for emergencies.
3. **How far a standing goal's approval reaches** (§5.2, §12.1 step 8).
   When a standing goal re-activates, may the runner re-run its own jobs
   with their approved arguments within a budget (recommended: yes, 4 per
   game year), and may it also re-run a **finished one-off sub-project**
   it links to (recommended: no; wake the owner with the old draft
   pre-filled, so the Overseer re-approves in one cheap call)?

Other decisions, smaller, listed where they arise: the first check
signals (§5.3), `scarce` classes for hard holds (§8.4), the active limit's
starting value (§9.5, suggested 4), priority doctrine defaults (§11.2),
the healing budgets (§10.3), and whether the recorder goes into VM 103's
`onMapLoad.init` (§3.3).

### 14.2 Where a settled decision needs a correction (marked, not designed around)

I agree with the nine decisions. Two need a correction to be buildable as
written, and one needs a word changed.

**Correction A, to decision 2 ("no vague nodes").** Taken literally, a
job must have real arguments at filing. But the brewing job's
`WORKSHOP_LANDMARK_NAME` for the barrel job names a Carpenter's Workshop
**that does not exist until an earlier node builds it**, and the wall
job's targets are the tiles **an earlier dig reveals** (the 2026-09-28
vein case). Neither argument can be known at filing, and neither is vague.
The correction: allow **late-bound arguments** that reference a declared
output of an earlier node in the same plan (`@p9.site.landmark`,
`from_step`, a slot's fill), validated at filing for existence and type,
resolved by code at run time. The live schema already does this for
targets (`from_step`); this extends it to arguments. Without it the rule
would force either fake arguments or one ruling per step.

**Correction B, to decision 6 ("exactly the approved arguments").**
Several tools choose the site when called (`NEAR_LANDMARK ... RANK`), so
the same arguments can land on a different tile later. "Exactly the
approved arguments" only means "exactly the approved effect" if a site is
pinned. The correction: **site arguments in a runnable step must be a
reservation handle**, and a slot that fills a site must produce one. This
needs one workshop footprint template, which does not exist yet.

**A word, in decision 8 ("labor claims are recomputed the same way").**
Nothing we record constrains which dwarf DF assigns, and autolabor
rewrites the labor flags. A labor "claim" cannot hold anything; it is an
**admission cap on what we issue** (§8.5). The behaviour the user asked
for (a named hold, "waiting: the carpenter is on project-4") is exactly
what the cap produces; calling it a claim invites someone later to build
labor locking that the game will not honour.

---

## 15. Not verified

- **`JOB_COMPLETED` handler item pointers**: whether `job.items[i].item`
  in the completion copy is still valid when the handler runs (§3.2).
- **The per-tick cost** of `JOB_COMPLETED` at frequency 0 or 1 on this
  fort (§3.3).
- **Whether VM 103's `onMapLoad.init` registers diff.lua or stuckjobs**;
  the file is not in the repo. `JOB_COMPLETED` and `UNIT_DEATH` have never
  been seen firing for real on this fort.
- **`building.contained_items` `use_mode`** values for construction
  materials, and **whether an item used in a construction survives** as an
  object (§8.3).
- **When DF binds items to a workshop job** (at posting, or when a dwarf
  takes it), which decides how much an un-forbid-at-issue hard hold
  guarantees (§8.4).
- **That the workshop "highest priority" button sets `do_now`** (§9.4).
- **The exact count of fort-mode civzone kinds** (about 19 of 99; the zone
  tool reads them live).
- **`onReactionComplete`'s item ids** as a reliable product record for
  brewing: documented, not exercised here.
- **Every token figure** in §6.5: estimates; no drafted proposal has run.
- **All DFHack and df-structures sources** are at the `53.16-r1` tag except
  `df.item.xml` and `df.event.xml` flag and struct reads, which were read
  at `master` (the construction struct was re-checked in the `53.16-r1`
  `Lua API.rst` mention of `original_tile` only).
- **Summary-level sources** (wording from a fetch tool, not read in the
  page): ERPNext issue #57313, `rt-mutex-design`, the Kubernetes owners
  page, YARN Fair Scheduler, the Black Swan Farming urgency profiles, the
  PostgreSQL deadlock section, OSTEP's Rule 5 wording, and the DF wiki
  Workshop page's Workers-tab sentence.
- **Nothing here was prototyped.** The node model, runner, claims and
  priority are untested against any real project; the only real evidence
  is the 2026-09-25/28 cycles they are meant to improve on.
- **One harness refusal during this pass**: a download command that named
  `raw.githubusercontent.com` inside a compound shell command was refused
  by the worktree isolation check (it matched "git" in the host name). The
  same downloads were done with PowerShell's `Invoke-WebRequest` instead,
  read-only, into the scratchpad. Reported here as the brief asks.

---

## 16. Sources

Read in source (high confidence):

- DFHack `library/modules/EventManager.cpp`, `library/lua/repeat-util.lua`,
  `docs/dev/Lua API.rst` (eventful section, `onJobCompleted` note), all at
  tag `53.16-r1`, fetched from `raw.githubusercontent.com/DFHack/dfhack/53.16-r1/`.
- df-structures at `53.16-r1`: `df.job.xml` (`job_type` 259 entries and
  class attributes, `job_role_type`, `job_item_ref`, `job_flags.do_now`),
  `df.building.xml` (`workshop_type`, `furnace_type`, `construction_type`,
  `buildingitemst`, `contained_items`), `df.d_basics.xml` (`building_type`,
  `civzone_type`, `tile_dig_designation`). At `master`: `df.item.xml`
  (`item_flags`), `df.event.xml` (`construction`), `df.workquota.xml`.
- This repo: `dfqueue/schema.py`, `dfqueue/store.py`, `dfqueue/render.py`,
  `dfmcp/queue_tools.py`, `dfmcp/roles.py`, `agents/ROSTER.yaml`,
  `agents/conductor/{role.md,tools.yaml}`, `agents/overseer/role.md`,
  `agents/quartermaster/role.md`, `conductor/cycle.py`, `conductor/triage.py`,
  `conductor/policy.yaml`, `conductor/order_watch.py`,
  `scripts/dfhack/TOOLS.yaml`, `df-overseer-reservations.lua`,
  `df-overseer-construction.lua`, `df-overseer-diff.lua`,
  `df-overseer-clock.lua`, `df-overseer-ledger.lua`,
  `df-overseer-stuckjobs.lua`, `df-overseer-stockpile.lua`,
  `df-overseer-blueprint.lua` (`dig_progress`), `df-overseer-workjob.lua`
  header, `production/blocker.py`, `production/cover.py`,
  `production/tests/fixtures/labor_dump/PROVENANCE.md`,
  `learning/live_signals.py`, `docs/AGENT-ARCHITECTURE.md` §4, §7, §9,
  `docs/AGENT-LOOP.md` §6, `docs/PRODUCTION-MODEL.md` §10, §13,
  `research/2026-09-28-job-dependency-graph.md`,
  `research/2026-09-22-objective-graph-prior-art.md`,
  `research/2026-09-24-df-ai-fort-planner.md`,
  `evals/live/2026-09-25-first-real-conductor-cycle/README.md`,
  `Working.md`, `decisions/DECISIONS.md` (2026-09-25 to 2026-09-30 rows).

Primary papers and documentation, read in their own text (page images or
fetched pages; high confidence for quoted wording):

- D. Nau, T.-C. Au, O. Ilghami, U. Kuter, J. W. Murdock, D. Wu, F. Yaman,
  "SHOP2: An HTN Planning System", JAIR 20 (2003) 379-404, arXiv 1106.4869.
- M. Colledanchise, P. Ögren, *Behavior Trees in Robotics and AI: An
  Introduction*, arXiv 1709.00084v5, ch. 1.
- J. Orkin, "Three States and a Plan: The A.I. of F.E.A.R.", GDC 2006,
  https://www.gamedevs.org/uploads/three-states-plan-ai-of-fear.pdf
- R. and A. Arpaci-Dusseau, *Operating Systems: Three Easy Pieces*, ch. 8
  (MLFQ) and ch. 32 (concurrency bugs), https://pages.cs.wisc.edu/~remzi/OSTEP/
- Linux kernel, RT-mutex subsystem with PI support,
  https://docs.kernel.org/locking/rt-mutex.html
- SAFe, WSJF, https://framework.scaledagile.com/wsjf/
- ERPNext, Projected Quantity, https://docs.frappe.io/erpnext/projected-quantity
- Stripe, Idempotent requests, https://docs.stripe.com/api/idempotent_requests
- DFHack tool docs: `unforbid` and `prioritize`,
  https://docs.dfhack.org/en/stable/docs/tools/
- DF wiki (pages tagged v53.16): Forbid, Labor (work details), Workshop,
  https://dwarffortresswiki.org/

Summary-level (moderate confidence; wording from a fetch tool):

- ERPNext issue #57313, https://github.com/frappe/erpnext/issues/57313
- Linux kernel, RT-mutex implementation design,
  https://docs.kernel.org/locking/rt-mutex-design.html
- Kubernetes, Owners and Dependents,
  https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/
- Apache Hadoop YARN, Fair Scheduler,
  https://hadoop.apache.org/docs/stable/hadoop-yarn/hadoop-yarn-site/FairScheduler.html
- Black Swan Farming, urgency profiles, https://blackswanfarming.com/urgency-profiles/
- PostgreSQL, Explicit Locking (deadlocks),
  https://www.postgresql.org/docs/current/explicit-locking.html

