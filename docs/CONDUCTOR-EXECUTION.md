# Conductor execution: proposers pick, the Overseer rules, code acts

Date: 2026-10-05. Status: **design, nothing built.** Opus design for a
separate Opus red team, then a staged Sonnet build. Every claim about the
current system is marked **[verified]** (read in code or on a host this
session) or **[proposed]** (this design).

Governing register rows, all 2026-10-05: "Proposers pick exact actions, the
Overseer only rules, the conductor executes accepted actions as code"; "Server
refusal over charter prose; decision rule for each new rule"; "Agents trust
each other's facts; they may challenge each other's reasoning"; "The briefing
carries no fixed per-role stock lists"; "Advisors may propose amendments to
running projects". Inputs: `research/2026-10-05-procedure-briefing-and-bounded-turns.md`
(decision rule section 3.3, R1 to R7), `research/2026-09-12-multi-agent-architecture-prior-art.md`,
`research/2026-09-28-job-dependency-graph.md`, `handoffs/2026-10-05-cited-facts-briefing.md`
(paused, folded in here), `evals/live/2026-10-05-pause-safety/`.

## 0. The design in one screen

1. **A proposal carries its exact action** (`steps`: tool, arguments,
   `requires` edges, labels). At filing the **server** validates the arguments
   the same way a real call would, **dry-runs** every step that can run now,
   reads every **cited fact** itself, and stores what the game said. A
   proposal whose dry run fails is refused, so nothing unrunnable reaches the
   Overseer.
2. **The Overseer only rules.** Its briefing is the pending proposals in a
   fixed shape (action, dry-run result, cited facts with mechanical
   staleness), what is already decided, and the ask last. It holds no
   fort-mutating tool, no `queue.project`, no `queue.executed`. Its turn is
   bounded by a budget it is told and a server cap it cannot exceed.
3. **The conductor executes as code.** It calls `queue.open_project` (the
   server builds the project from the accepted proposal alone) and
   `queue.run_step` (the server reads the step's stored tool and arguments,
   dry-runs, runs for real, records `executed`). The conductor never passes
   a tool argument, so "only the accepted arguments run" holds by
   construction, not by matching.
4. **A step that needs fresh judgment goes back to its proposer** as a short,
   bounded follow-up turn (`step_needs_judgment`), which may refill only the
   arguments the accepted proposal declared open.
5. **Noticed problems get owners** (`queue.flag`), and stuck jobs are routed
   to the role that owns them.

What stays: one decider (the Overseer), advisors with no peer chat, the queue
as the write-ahead log, the tripwire, pause watchdog and operator hold
unchanged in authority, and set intent, let the game execute (DF schedules the
dwarves; we never re-implement its job system).

---

## 1. Why, from the live evidence

**[verified]** run-0004 (Overseer, `queue_pending`, 2026-10-05): 645 s, 37 tool
calls, 3 failures (archived `run-overseer.json` on VM 106). It re-read drink,
barrels, beds and wood to check proposals, restated the three proposals
repeatedly, sited bedrooms itself (six previews, two applies) and judged that
"overreaching", skipped `queue.project`, and deferred the stuck Bed with no
owner. Advisor runs the same day: 483 s, 342 s, 195 s.

**[verified]** Live queue, read-only on VM 103 this session: 15 rulings, 9
accepted, **0 projects ever**, 7 `executed`; two accepted rulings never
executed (`ruling-0001`, whose proposal was voided 2026-09-22, and
`ruling-0006`).

The three faults map to three changes: the Overseer re-derives because it
holds the tools and lacks the content (fix: briefing carries content, tools
removed); it drifts into siting because siting is the act it holds (fix: the
act moves to code, the siting choice to the proposer); it skips steps the
server permits (fix: the server builds the project itself and is the only
path to execution).

---

## 2. The proposal's action format

### 2.1 Shape [proposed]

New optional proposal fields (a proposal without `steps` stays valid only for
`type`s whose data says they have no fort action, see 2.3):

```yaml
public_title: "Five bedrooms off the dining hall"   # <= 60 chars, now the proposer's
steps:                                              # 1..MAX_STEPS (8)
  - id: dig                                         # unique in this proposal
    label: "Dig bedroom"                            # <= 24 chars, required
    tool: blueprint.apply                           # a fort-mutating tool id
    args: {TEMPLATE: bedroom-cell-v1, PHASE: dig, SITE: "Dining Hall", RANK: 2}
    open: [RANK]                                    # args a follow-up may refill; default []
  - id: furnish
    label: "Place bed"
    tool: blueprint.apply
    args: {TEMPLATE: bedroom-cell-v1, PHASE: build, SITE: {from_step: dig, field: site}}
    requires: [dig]
    confirm: false                                  # true: proposer re-confirms at run time
relies_on:                                          # cited facts, 0..MAX_CITED (6)
  - {tool: stocks.availability, args: {type: BED}, field: available_units}
```

Rules, each a server refusal with a repair message (decision rule step 2 or 4):

- `tool` must be a registry tool with `effect: mutate`, not system-class, not
  `ui.*`, and listed for this proposal `type` in the action-tool table (2.3).
- `args` are checked by the same `argv_for_call` the real call uses
  (`dfmcp/tools.py`), so a malformed argument is refused at filing, not at
  execution. Coordinates are refused by the existing pattern check.
- `DRY_RUN` must not appear: the server owns it.
- An argument value may be `{from_step: <id>, field: <path>}`: the server
  substitutes that field from the named step's stored result at run time.
  `<id>` must be a transitive `requires` of this step. This is how a later
  phase gets the site handle (`site-N`) an earlier `blueprint.apply` issued,
  with no judgment and no coordinate.
- `requires` reuses the existing project step validation (`_validate_step`,
  `_find_requires_cycle` in `dfqueue/schema.py`) unchanged.
- `open` names arguments a follow-up turn may change (2026-10-01 executor
  bounds: the next-ranked candidate from the same finder is the usual case).
  The Overseer sees `open` when it rules, so a refill within it is inside the
  ruling. Everything else is fixed.
- `confirm: true` marks a step that always needs a look at run time (placing
  furniture by `NEAR_LANDMARK` after a dig, when the site may have moved).

### 2.2 Validation at filing: the dry run [proposed]

`queue.propose` gains, after schema validation and before the write:

1. For every step with no `requires` and no `from_step` argument, call the
   tool server-side with `DRY_RUN=true` (through the internal `call_dfhack`,
   the same bypass `_stamp_cycle_snapshot` already uses **[verified]**). An
   error result refuses the proposal and returns the tool's own refusal text
   (a refusal is the best-placed prompt, research 3.2). A step that depends on
   an earlier one cannot be previewed before that one has happened; it is
   argument-checked now and dry-run at execution.
2. Store a bounded `preview` per previewed step: `ok`, a one-line summary,
   the game tick, and `resolved_key` when the tool supplies one (2.4).
3. Read each `relies_on` fact: the tool must be `effect: read`, on the
   **proposer's own** allowlist, and the field path must resolve. Store
   `{value, tick}`. A failed or unresolved read **refuses** the proposal: a
   fact the server cannot read cannot be vouched for, and the repair (drop or
   fix the citation) is one call. This settles the open question in the
   cited-facts handoff.

**Which tools can be proposed.** **[verified]** From the registry, every
mutating DFHack tool except `landmarks.build`, `openarea.build`,
`diggable.dig` and `labor.set-labor` takes a `DRY_RUN` argument. **[proposed]**
Rule: a tool is proposable only if it takes `DRY_RUN`, read from its signature
(no list to maintain). The four without one are refused as actions with a
message naming `blueprint.apply` (which supersedes the two dig tools for rooms)
until they gain a dry run. `labor.set-labor` is already outside every
proposal type (`set_labor` races autolabor).

### 2.3 Generic by data, never per-kind code [proposed]

One table, `dfqueue/action_tools.yaml`, maps proposal `type` to the tools its
steps may use:

```yaml
room_siting:      [blueprint.apply, blueprint.reserve, zone.place, zone.assign-owner, building.build]
workshop_siting:  [building.build, workshop.build, blueprint.apply]
stockpile_siting: [stockpile.place, stockpile.configure, stockpile.link]
corridor:         [blueprint.apply, diggable.dig-stair]
smoothing:        [blueprint.apply]
dig_order:        [blueprint.apply, diggable.dig-stair, construction.mine-vein]
work_order:       [orders.create, orders.reorder, orders.cancel, orders.recheck, workjob.queue, workjob.cancel]
crop_plan:        [farm.set-crop]
stock_target:     []          # sets a threshold; no fort action (see 6.3)
```

A new tool or kind is one line here (and the tool's own `DRY_RUN`); a new
building, crop or workshop kind is an argument value, no entry at all. The
exact lists above are a starting draft for the build to check against each
role's charter.

### 2.4 Site drift between filing and execution [proposed]

**[verified]** Site-bearing tools resolve a place as "the RANK-th candidate
near a landmark" at call time; nothing pins it, and pinning a build to a
reservation ("a build given `RES_ID` goes exactly on it") is listed as next
work in `Working.md`, not built. So the same arguments can resolve to a
different place a day later.

Proposed, generic: each site-resolving Lua tool adds an opaque `resolved_key`
to its dry-run and real output (a hash of the resolved footprint and level,
computed by one shared helper; code-only, never a coordinate, never shown to a
model). `queue.run_step` compares the execution-time dry run's key with the
filing-time key; a mismatch is not run but sent to the proposer as
`step_needs_judgment` ("the RANK 2 site is no longer the one you previewed").
A tool that supplies no key runs as written and the record says drift was not
checkable. Once reservations pin sites, a proposer may cite a `res-N` as an
argument and the key check becomes a backstop.

---

## 3. The Overseer's ruling turn

### 3.1 Prompt layout, stable to volatile [proposed]

DeepSeek caches by exact prefix (research 7.4, **[H]** there). **[verified]**
openclaw sends `SOUL.md` (the charter, written per run by
`conductor/runner.py`) and the MCP tool list, and the conductor's briefing is
the user message. So:

| Position | Content | Changes when |
|---|---|---|
| 1. System (SOUL.md) | Charter: lane, ruling rubric, urgency and WIP definitions, escalation, stop condition, what is not yours (names the roles) | charter edit |
| 2. Tools | The reduced allowlist (3.2), summaries only | allowlist edit |
| 3. User message, JSON | Volatile per-wake briefing (3.3) | every wake |
| 4. User message, last line | The ask | every wake |

Nothing volatile (tick, date, counts) goes in the charter. Whether openclaw
injects anything volatile into its own system prompt is **not verified**;
stage 0 measures it (8.2). The same rule applies to every role: a proposer's
follow-up turn (section 5) uses its ordinary charter and tools, so it shares
the cached prefix of its routine wakes.

### 3.2 Reduced allowlist [proposed]

| Keeps | Why |
|---|---|
| `queue.rule`, `queue.abandon`, `queue.escalate`, `pause.verdict` | its decisions |
| `queue.ask` | mechanics questions to the Consultant (not fact re-checks) |
| `queue.flag` (new, 6.1) | hand a noticed problem to an owner |
| `queue.pending`, `queue.project_status` | detail behind a briefing line |
| `overview.get`, `threat.scan`, `breach.check`, `stuckjobs.find` | tripwire and pause-verdict wakes need a look at danger |
| `gotchas.get`, `gotchas.write` | unchanged practice |

**Loses** every fort-mutating tool (35 of its 43 write grants today **[verified]**),
`queue.project`, `queue.executed`, `queue.amend`, and the siting, surface,
blueprint, stock, farm and finder reads. If a ruling needs a fact nobody
cited, the move is **defer with the missing fact named**, and the proposer
re-files citing it; that keeps "trust facts, challenge reasoning" and costs
one cycle only when a proposer under-cited.

### 3.3 Briefing content, fixed order [proposed]

Replaces the merged-but-undeployed `facts` blocks and `briefing_extras`
(**[verified]** in `conductor/briefing.py` and `conductor/policy.yaml`).

1. **Header:** wake reason and detail, game tick, clock, severity word
   (`routine`, `elevated`, `urgent`, from the wake table).
2. **Vitals** (as today) plus **threshold alerts**: a line only while a
   `policy.yaml` threshold is crossed. Shape, one entry per alert:
   `{read: {tool, args, field}, per: alive|null, below: N, text: "..."}`.
   The conductor reads each distinct tool+args once per cycle (total: a
   failed read drops its line). Every role gets the same alerts.
3. **Decided, do not redo:** open projects one line each (title, status,
   top blocker), open count against the WIP cap, the last five rulings.
4. **Pending proposals,** each in one fixed shape, capped at 8 with the count
   always shown: id, role, type, summary; one line per step (`tool` plus its
   key arguments, `open`, `requires`); the filing dry run's one-line result;
   each cited fact as `value at tick T` and, only if it changed,
   `now V` (the server re-reads each distinct citation once per brief);
   prediction, cost, suggested priority; computed flags (`overlaps
   proposal-N` when two pending proposals share a `resolved_key` or the same
   tool and landmark; `duplicate_of` as today).
5. **Open items addressed to the Overseer** (flags, 6.1), each with owner and
   next action.
6. **The ask, last:** "Rule on each pending proposal: accept (with urgency),
   reject, or defer naming what would change your mind. Cited facts are
   already checked and refreshed; judge the reasoning. Stop when each has a
   ruling. Expected about N tool calls." N = 1 per proposal plus 2.

The pending block is produced server-side by a new conductor-only read,
`queue.pending_brief`, so citation refreshes run under the server's own
reads and the conductor's allowlist does not grow per cited tool. This
resolves the research's "Tier 0 figures only" tension explicitly: proposal
summaries are bounded text, capped, and `docs/AGENT-LOOP.md` item 6 gets one
line saying so.

### 3.4 Bounding the turn [proposed]

- **Told:** the expected call count in the ask (research 5.2, BATS).
- **Wall clock per wake reason**, data in `policy.yaml`: `queue_pending` 300 s,
  `tripwire` and `unexplained_pause` 600 s. Today the repo sets the Overseer
  to 1200 s **[verified]**.
- **Server cap:** per MCP session (`_run_id`, already used for the gotcha
  write cap **[verified]**), the Overseer's calls are refused past a data
  number (start at 20), with the text "this wake's call budget is spent:
  defer what is unruled and stop." Its one-to-one session assumption is
  unverified; if sessions are reused the cap is only stricter.
- **Effort:** a per-role `reasoning_effort` if openclaw passes one; **not
  verified** that it does (research 7.3). Stage 0 checks.

### 3.5 Ruling record changes [proposed]

`queue.rule` gains optional `urgency` (`normal`/`elevated`/`high`, the
project's urgency, the Overseer's call) and keeps `public_rationale`.
Refusals: accepting a proposal with no `steps` whose type has action tools
(post-migration only); accepting while open projects are at the WIP cap
(open question 4).

---

## 4. The conductor as executor

### 4.1 Authority: how the server knows [proposed]

- **ROSTER:** `sole_writer: overseer` keeps meaning "the one decider" (it
  gates `ruling`, `escalation`, `abandon` in `dfqueue/schema.py`). New
  `executor: conductor`. `project`, `executed` and `amend` records become
  executor-only (schema write check plus a new `executor_only` registry flag,
  the same two layers as `sole_writer_only` **[verified]** in
  `dfmcp/roles.py`).
- **roles.py Rule 2 becomes:** no role may hold a fort-mutating DFHack tool
  (load-time refusal), except system-class tools for kind `system`. The
  Overseer's allowlist then fails to load if anyone re-adds `blueprint.apply`,
  which is the structural answer to research 5.1's siting ambiguity.
- **Two new native tools, executor-only:**
  - `queue.open_project(ruling_id)`: builds the `project` record from the
    accepted proposal alone (steps, labels, `public_title` from the proposal;
    `urgency` and `public_rationale` from the ruling). No other argument
    exists, so there is nothing to get wrong and no hollow record (research
    3.3 caution a). Refused if the ruling is not `accept` or a project exists.
  - `queue.run_step(project_id, step_id)`: the only path to a fort mutation.
    The server reads the step's stored tool and arguments, resolves any
    `from_step` values, then checks in order: ruling accepted; project not
    abandoned; step in the current version; `requires` satisfied; not
    already succeeded; no `issuing` marker outstanding; tripwire not latched
    (server reads `clock.status`, defence in depth). It writes an `issuing`
    marker, dry-runs, compares `resolved_key` (2.4), runs with
    `DRY_RUN=false`, and appends the `executed` record (role `conductor`,
    `actions` with outcome, bounded detail, `targets`/`game_refs` taken from
    result fields named by data) in one server call.
- The conductor's token holds no DFHack mutating tool, so a stolen conductor
  token can run only accepted steps. That is narrower than today's Overseer
  token, which can run anything on its allowlist.

The considered alternative, granting the conductor the acting tools and having
the server match each call's arguments to an accepted step, was rejected:
matching needs a canonical-argument comparison and a ticket to stop replays,
and still lets code pass arguments. Removing the choice is decision rule
step 3.

### 4.2 The execute phase in a cycle [proposed]

`conductor/cycle.py`'s ordinary path becomes: read, grade, triage, advisors,
Consultant, Overseer, **execute**, archive. Execute:

1. `queue.overview` already lists accepted rulings; for each accepted ruling
   without a project, `queue.open_project`.
2. Collect ready steps across open projects (prerequisites done, not
   succeeded, not held, not awaiting a follow-up). Order: ruling urgency
   (`high`, `elevated`, `normal`), then ruling age, then step order. Cap
   `max_steps_per_cycle` in `policy.yaml` (start at 4: every call is
   tick-gated, research and `docs/AGENT-ARCHITECTURE.md` record 45-80 s
   latencies).
3. If any step will run: `fort.quicksave` once (this replaces today's
   quicksave before the Overseer runs **[verified]** in `cycle.py`, since the
   Overseer no longer acts).
4. `queue.run_step` for each, in order; a step that becomes ready because an
   earlier one in this phase succeeded waits for the next cycle (one snapshot
   per cycle).
5. Each outcome is classified (4.4) and recorded in the cycle archive and
   `conductor.report`.

Execute also runs on cycles where nobody woke, so accepted work proceeds
without spending a model turn.

### 4.3 Completion and `requires` [proposed]

A step with no tracked targets counts as done once it has a successful
`executed` record (`step_status` already works this way **[verified]** in
`dfqueue/store.py`). Whether the game has *finished* the work (a dig dug out)
is left to the game and to the dependent step's own dry run: `blueprint.apply`
already refuses a phase while the shell's dig is outstanding **[verified]**
(its guide). So a dependent step whose execution-time dry run refuses within
`wait_after_prereq_ticks` of its prerequisite's issue is classed **waiting**,
not failed, and retried each cycle. This is the 2026-10-01 bound "wait out a
clearly temporary hold up to a set limit", and it avoids a second completion
layer. The Board will show a dig step "done" once designated; the unbuilt
reconciler (`research/2026-09-28-job-dependency-graph.md` section 6) can
refine that later.

### 4.4 Outcomes, retries, failure [proposed]

| Outcome | Classified by | Next |
|---|---|---|
| Success | real call not an error | `executed` success; step done |
| Transient | DFHack unreachable, timeout, protocol error | no record; retry next cycle; third consecutive becomes Failed |
| Waiting | dry run refuses within the prerequisite wait window | retry next cycle; past the window becomes Needs judgment |
| Needs judgment | dry run refuses outside the window, `resolved_key` mismatch, or `confirm: true` | step held (`hold_code: needs_judgment`), proposer woken (section 5) |
| Failed | real call errors after a passing dry run | `executed` failure; one retry next cycle; a second failure marks the step failed, opens a flag to the proposer and wakes the Overseer with `step_failed` (abandon, or escalate: its charter's "same plan step failed twice") |
| Uncertain | an `issuing` marker with no `executed` (a crash mid-call) | never re-run blindly; step held `uncertain`, flag to the Overseer |

Hold codes are added to `dfqueue/public_text.yaml` as data.

### 4.5 Tripwire, pause watchdog, operator hold [proposed]

The executor never calls `clock.resume` or `clock.set-speed`; designations,
orders and builds work while paused (every dry run this project has run was
on a paused fort **[verified]**, e.g. `evals/live/2026-10-05-pause-safety/`).

- **Tripwire branch:** returns early as today; no execute phase. The server
  also refuses `run_step` while latched.
- **Pause watchdog:** when it owns a pause (`_paused_cycle_result`), no
  execute phase: an unexplained pause may be an unseen threat.
- **Ordinary escalation this cycle:** no execute phase.
- **Operator hold:** no execute phase by default (a hold only removes
  things). Open question 2: an operator flag `--allow-execution` for "paused
  on purpose, keep building".

---

## 5. Judgment at execution: back to the proposer [proposed]

This supersedes the 2026-10-01 "cheap executor model woken on a hold": the
proposer, who already holds the siting context and the tools, is the one
woken. The 2026-10-01 executor bounds still apply to what it may change.

- **Wake:** new reason `step_needs_judgment` in `policy.yaml`, waking the
  proposal's own role, clock `full_speed` (nothing is at risk while a step
  waits). One wake per held step; several held steps for one role go in one
  turn, capped at 3.
- **Briefing:** header; the project's one line; the step (tool, arguments,
  `open`); why it was held (the dry-run refusal text, or "the previewed site
  changed"); the filing-time preview line. Ask, last: "Call `queue.fill_step`
  with new values for the open arguments (the server previews them), or
  `queue.release_step` with a reason. Expected about 4 calls."
- **`queue.fill_step(project_id, step_id, args)`** [new, proposer-only]:
  refused unless the caller is the proposal's role, every key is in `open`,
  and the dry run passes. On success it appends an `amend` record (a new step
  id replacing the old, the existing rule that a changed step takes a fresh
  id **[verified]** in `store.py`), so history stays append-only and the
  Board shows the change. The step runs on the next execute phase.
- **`queue.release_step(project_id, step_id, reason)`** [new, proposer-only]:
  the proposer cannot make it work within `open`; the step is held
  `released` and a flag goes to the Overseer, who abandons or awaits an
  amendment proposal (register 2026-10-05, advisors may propose
  amendments).
- **Bound:** 240 s wall clock and a session call cap like 3.4.

---

## 6. Owned follow-ups and stuck jobs

### 6.1 `queue.flag` [proposed]

Research R4. Any model role may write; fields `what`, `evidence` (a tool
call or record id), `owner` (a role), `next_action`, `expires_after_ticks`.
The server refuses without an owner and a next action. Open flags appear in
the owner's briefing "open items" block, and a new `flag_open` wake wakes the
owner (data: same clock as the owner's routine wake). The owner closes it with
`queue.flag_close(flag_id, outcome)` or by filing a proposal naming
`flag_id` (closes it). An expired flag moves to the Overseer's open items.
"Worth a look next wake" stops being possible because it stops being needed.

### 6.2 Stuck-job ownership [proposed]

Today `stuck_job` wakes the Quartermaster only **[verified]**
(`conductor/policy.yaml`), and the 2026-10-05 Bed sat with nobody acting.
Proposed, data-driven:

1. A stuck job whose job id matches a `game_refs` entry of an issued step is
   owned by that step's proposer. Needs `job_id` in `stuckjobs.find` rows
   (already a named follow-up of the stuck-job watch).
2. Otherwise `policy.yaml` maps the job class to an owner
   (`stuck_job_owner: {construction_waiting_item: quartermaster, dig:
   architect, ...}`, one line per class).
3. At the renotify threshold the conductor opens a flag (owner pre-filled,
   `next_action` from the same table) instead of a bare wake, so the owner
   sees "yours, do X or close with why".

### 6.3 `stock_target` [proposed, optional]

An accepted `stock_target` has no fort action. Later, its one-step project can
write a threshold alert entry (3.3 shape) the briefing reads: stock targets as
live alerts with no per-item code.

---

## 7. What each charter keeps and loses

Applied through the decision rule (research 3.3): a rule the server can see
becomes a refusal and the charter states it in one line pointing at the
order of operations.

| Role | Keeps | Loses | Server refusals that replace prose |
|---|---|---|---|
| Overseer | ruling on reasoning; priority via urgency; WIP judgment; escalation; pause verdict; abandon; flags; Consultant asks | all acting; `queue.project`, `queue.executed`, `queue.amend`; most reads; the Execution paragraph | no mutating tool loads on its allowlist; call cap per session; accept refused without steps (post-migration); accept refused at WIP cap (if chosen) |
| Architect | siting judgment, now down to the exact step; dig order; previews | nothing | action tool must fit the type; `DRY_RUN` server-owned; dry run must pass; citations must be its own reads; `public_title` and labels required |
| Quartermaster | orders, crops, stock targets, now as exact actions | nothing | same as Architect |
| Conductor (code) | clock, tripwire, quicksave, triage, briefing | quicksave before the Overseer (moves before execute) | `run_step` checks in 4.1; `open_project` takes nothing but a ruling id |

Charter edits are short: the Overseer's drops from 129 lines to a lane, a
rubric, escalation and verdict rules, a stop condition; each proposer gains
three lines (steps with labels and `open`, cite what you rely on, a refused
filing tells you what to fix). Wording is tested on DeepSeek, not assumed
from Claude guidance (research 7.1).

---

## 8. Migration and staged build

### 8.1 From today

- **Accepted rulings with no project** **[verified live]**: seven executed by
  the Overseer before the refusal; two unexecuted (`ruling-0001`, voided
  proposal; `ruling-0006`). Executed ones are history: no project is
  backfilled (a backfilled project would claim a plan nobody wrote).
  `ruling-0006` gets an operator-run `queue.abandon` with reason "pre-
  executor ruling with no action; re-propose if still wanted" after the
  Overseer's charter changes, or is left to the Overseer's first briefing as
  an open item. `ruling-0001` is abandoned the same way.
- **The deployed project-before-executed refusal** stays. It is satisfied by
  construction once `queue.executed` is executor-only and `run_step` writes
  it after `open_project`. Its repair text changes to name the executor.
- **Merged, not deployed:** the better-briefing `facts`/`briefing_extras`
  must not ship as is (superseded); the operator hold and the pause watchdog
  changes should ship (stage 0). Any conductor deploy ships HEAD, so stage 1
  lands before the next conductor deploy, or stage 0 removes the extras.
- **Mixed period:** between stages 2 and 3 the Overseer still acts, but its
  charter says to run exactly the proposal's steps. Keep it short.

### 8.2 Stages (each: commit as you go, full test suites green, then a live check)

| Stage | Build | Deploy targets | Live check |
|---|---|---|---|
| 0. Measure and ship safety | Archive the openclaw envelope's `usage`, `assistantTurns` and `toolSummary` per run (today the archive keeps neither **[verified]**); remove `briefing_extras` and the stock `facts` blocks; deploy the operator hold | vm106-conductor | one dry-run cycle; one real advisor wake to read usage fields and cache hits |
| 1. Cited facts, alerts, briefing order | `relies_on` with server reads; `queue.pending_brief`; threshold alerts as data; fixed briefing order with ask last; per-reason timeouts | vm103-dfmcp, vm106-conductor, vm106-agents (charters) | a ruling wake: count re-fetch reads (target 0 for cited facts) |
| 2. Actions at filing | `steps`, `action_tools.yaml`, server dry run, `public_title`/labels, overlap flag; proposer charters | vm103-dfmcp, vm106-agents | Architect files a one-step room, Quartermaster an order; a refused dry run read back |
| 3. Executor, single step | ROSTER `executor`; schema write split; Rule 2 change; `open_project`, `run_step` (no `from_step` yet); execute phase; Overseer allowlist cut and charter | vm103-dfmcp, vm106-conductor, vm106-agents | supervised cycle: accept, project, run, record, prediction armed; tripwire and hold skip execute |
| 4. Multi-step and follow-ups | `from_step` args, waiting class, `resolved_key` in the site tools' Lua, `step_needs_judgment`, `fill_step`, `release_step` | vm103-dfmcp (incl. Lua), vm106-conductor, vm106-agents | a two-phase room; a forced key mismatch reaches the Architect |
| 5. Ownership | `queue.flag`, `flag_open` wake, stuck-job owner table, `job_id` in `stuckjobs.find` | vm103-dfmcp, vm106-conductor, vm106-agents | a stuck job yields a flag to its owner and a close |
| 6. Bounds and amendments | Overseer session call cap; effort per role if exposed; amendment proposals applied by the executor | vm103-dfmcp, vm106-conductor | compare stage 0 baseline |

Each stage is one handoff with disjoint touched surfaces, per
`handoffs/` rules. Stages 1 and 2 both touch `queue.propose`; run them in
sequence, not in parallel.

---

## 9. Risks, open questions, measures

### 9.1 Risks

- **The Overseer rubber-stamps.** It no longer checks facts or acts, so a bad
  proposal with confident reasoning passes. Mitigations: server dry run,
  guards and reservations at execution, quicksave, graded predictions per
  proposer type. Watch the accept rate and the grade hit rate per role.
- **Proposer turns lengthen.** Siting work moves to where it belongs, but a
  dry run inside `queue.propose` is tick-gated, and refused filings may loop.
  Detector: refused `queue.propose` calls per run; promote to a per-session
  cap after two real loops (decision rule step 6).
- **Rank drift without a key.** Tools lacking `resolved_key` run as written;
  the wrong site is possible until reservations pin sites.
- **Nested arguments on DeepSeek.** Steps with `requires` and `from_step` are
  the nested JSON research 7.2 warns about; every refusal names the path.
- **Collisions between accepted proposals.** Two proposals picking RANK 1 at
  one landmark. The overlap flag shows it to the Overseer; the second step's
  execution-time dry run or key check catches what slips through.
- **Server surface.** `run_step` is powerful; it is executor-only, takes no
  arguments, and is logged per call like every tool.
- **Crash between real call and record.** Rare; handled by the `issuing`
  marker as Uncertain, never re-run blindly.

### 9.2 Open questions for the user

1. **Overseer emergency acts:** none (recommended: military is deferred and
   no emergency tool is in use), or a small named set it may call directly?
2. **Execution under an operator hold:** off by default; add an
   `--allow-execution` flag?
3. **Site drift:** add `resolved_key` to the site tools (recommended), or
   wait for reservation pinning and run as written meanwhile?
4. **WIP cap as a refusal at accept:** yes, with what number, and may
   `urgency: high` exceed it?
5. **Superseding the cheap executor model** (2026-10-01): confirm the
   proposer follow-up replaces it.
6. **Overseer reads:** drop stock and siting reads entirely (defer for a
   missing citation), or keep a few?
7. **Tools without `DRY_RUN`** (`diggable.dig`, `openarea.build`,
   `landmarks.build`): unproposable until they gain one (recommended)?

### 9.3 What to measure live

Baseline from 2026-10-05 **[verified]**: Overseer 645 s and 37 calls; advisors
195 to 483 s. Per run, from stage 0: wall clock; tool calls and failures;
`assistantTurns` (rounds); input, output and cache-read tokens.
**[verified]** openclaw's DeepSeek provider package on VM 106 carries a
`cacheRead` price, so openclaw accounts cache reads; **not verified** that the
`agent exec --json` envelope exposes them, and the conductor archive drops
the raw envelope today. Detectors from the run record: reads whose answer the
briefing already held; refused filings per proposal; follow-up turns per
executed step and their length; steps per class in 4.4; flags opened, closed
and expired. Targets to beat, not promises: an Overseer ruling wake under
120 s and 10 calls for three proposals, and cache-read share of input above
half on the second and later rounds of a turn.
