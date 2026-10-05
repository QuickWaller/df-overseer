# Conductor execution: proposers pick, the Overseer rules, code acts

Date: 2026-10-05, revision 2 (after the red team,
`docs/CONDUCTOR-EXECUTION-REDTEAM.md`, and the user's decisions the same
day). Status: **design, nothing built.** Claims about the current system are
marked **[verified]** (read in code or on a host); everything else is
**[proposed]**. Revision 1 was `2f1bf68`.

Governing: the 2026-10-05 register rows (proposers pick exact actions and
code executes; server refusal over charter prose; trust facts; no fixed
stock lists; advisors may propose amendments). Inputs:
`research/2026-10-05-procedure-briefing-and-bounded-turns.md`,
`research/2026-09-12-multi-agent-architecture-prior-art.md`,
`research/2026-09-28-job-dependency-graph.md`,
`handoffs/2026-10-05-cited-facts-briefing.md` (folded in),
`evals/live/2026-10-05-pause-safety/`.

## 0. The design in one screen

1. **One step per proposal:** one tool, exact arguments. At filing the server
   checks them, dry-runs the step, judges it by the tool's own verdict fields
   (declared per tool in `TOOLS.yaml`) and reads every cited fact itself.
2. **A room is a project that grows.** The first proposal reserves the site
   and may declare the template's later phases. Each later phase is a
   follow-up proposal that **joins the same project** as a new step with a
   `requires` edge, citing the handle the earlier step issued; the server
   writes it as an `amend`, so the Board's graph grows (reserve, dig, finish,
   furnish). A follow-up that is exactly a declared phase on the issued site
   is accepted by the server; anything else goes to the Overseer.
3. **The Overseer only rules,** on content in its briefing, in a bounded
   turn. Its acting tools leave one at a time, as each gets a proposal type.
4. **The conductor executes as code.** `queue.open_project` and
   `queue.run_step` take ids only, so only accepted arguments can run.
   Anything failing after the real call was sent is **Uncertain**, never
   retried blind.
5. **Done means the game says so:** a small reconciler reads real progress
   and only then wakes the proposer: "your step in project P is done, what
   next".
6. **Noticed problems get owners** (`queue.flag`); stuck jobs go to theirs.

Kept: one decider, no peer chat, the queue as write-ahead log, tripwire,
pause watchdog and operator hold, and set intent, let the game execute.

---

## 1. Why, from the live evidence

**[verified]** run-0004 (Overseer, 2026-10-05): 645 s, 37 calls, 3
failures; it re-read stocks, restated proposals, sited bedrooms itself
("overreaching"), skipped `queue.project` and left the stuck Bed unowned.
Live queue on VM 103: 9 accepted rulings, **0 projects ever**;
`ruling-0001` (voided proposal) and `ruling-0006` never executed. Fixes:
content in the briefing and fewer tools; the act to code and the choice to
the proposer; the server as the only path to execution.

---

## 2. Proposals

### 2.1 Shape [proposed]

New proposal fields:

```yaml
public_title: "Bedroom off the dining hall"     # <= 60 chars, required with a step
step:                                           # exactly one
  tool: blueprint.reserve
  args: {template: bedroom-cell-v1, purpose: "bedroom row 1", site: "Dining Hall", rank: 2}
  label: "Reserve bedroom"                      # <= 24 chars
phases: {tool: blueprint.apply, list: [dig, finish, meta]}   # optional, declared now
relies_on:                                      # cited facts, 0..6
  - {tool: stocks.availability, args: {type: BED}, field: available_units}
# a follow-up adds:
project_id: project-0004                        # the proposer's own project
after_step: project-0004/s1                     # becomes this step's requires edge
```

A follow-up phase cites the issued handle literally:
`step: {tool: blueprint.apply, args: {template: bedroom-cell-v1, phase: dig,
site: res-7}}`, then `site: site-12` for the phases after the dig.
`blueprint.apply` already accepts `SITE: res-N` and carves exactly that
reservation, refusing a reservation already carved **[verified]**
(`df-overseer-blueprint.lua`, the `is_reservation_handle` branch).

### 2.2 Validation at filing [proposed]

All refusals carry a repair message (decision rule steps 2 and 4).

1. **Tool.** `effect: mutate`, not system-class, not `ui.*`, listed for the
   proposal `type` in `dfqueue/action_tools.yaml` (2.4), and **proposable**:
   it takes a `DRY_RUN` argument and `TOOLS.yaml` declares its verdict (2.3).
2. **Arguments.** Checked by the same `argv_for_call` the real call uses.
   Names are canonical lower case **[verified]** (`dfmcp/tools.py`), so any
   argument whose canonical name is `dry_run` is refused (H2); the server sets
   `dry_run` after merging. Override-class arguments (`allow_stranded`,
   `override`) are declared as data and refused unless the type allows them.
   Coordinates are refused by the existing pattern.
3. **Dry run.** The server calls the tool with `dry_run=true` through its
   internal DFHack path (the same bypass `_stamp_cycle_snapshot` uses
   **[verified]**). The result must echo `dry_run: true` (declared field) or
   the filing is refused. The tool's own verdict decides: `ok: false` or
   `blocked: true` refuses, returning the tool's reason (C1). A bounded
   `preview` is stored: verdict, one-line summary, tick, and the tool's
   declared `resolution_fields` (2.3).
4. **Cited facts.** Each tool must be `effect: read` and on the proposer's
   own allowlist; the server reads it and stores `{value, tick}`. An
   unreadable citation refuses the filing.
5. **Declared phases.** `phases.tool` must carry a `phases` entry in
   `TOOLS.yaml`; every listed phase must appear, in order, in the template's
   own phase list, read through that entry's `source` with the carried
   arguments (`template`) taken from this step.
6. **Follow-up checks.** `project_id` must be a project whose original
   proposal has the caller's role; not abandoned or closed; `after_step` must
   be a step of it; every handle argument must equal a handle an earlier step
   of this project issued.
7. **Time bound (M8).** One filing has a total budget (start at 60 s). A
   DFHack timeout or unreachable game returns a distinct "server busy, file
   again" refusal that the refused-filing detector does not count.

### 2.3 Per-tool data in `TOOLS.yaml` [proposed]

Generic, one entry per tool, no per-kind code:

```yaml
blueprint.apply:
  verdict: {ok: ok, blocked: blocked, reason: blocked_reason}
  dry_run_echo: dry_run
  nothing_applied: {field: designated, equals: 0}   # proves a failed call did nothing
  issues_handle: site.handle                       # recorded as a target of the step
  resolution_fields: [site.near_landmark, site.direction, site.distance_tiles, site.footprint]
  phases: {arg: phase, site_arg: site, carry: [template],
           source: {tool: blueprint.plan, args: [template], field: "phases[].label"}}
  progress: {tool: blueprint.status, args: {site_id: "$handle"},
             done_when: {field: dig.state, equals: none_pending},
             moving_when: {field: dig.pending_dig_designations, decreasing: true},
             stalled_when: {field: stalled, equals: true}}
blueprint.reserve:
  verdict: {ok: ok}
  dry_run_echo: dry_run
  issues_handle: handle
  resolution_fields: [site.near_landmark, site.direction, site.distance_tiles]
```

`resolution_fields` are existing coordinate-free output fields (they
replace revision 1's Lua `resolved_key`); field paths are confirmed against
real output at build time. A tool with no `progress` entry is done at its
first success (an order exists once created; the prediction grades it).

**Tools without `DRY_RUN`** **[verified]**: `landmarks.build`,
`openarea.build`, `diggable.dig`, `labor.set-labor` and `ledger.record`
(L1). None is proposable. Adding `DRY_RUN` to the first three is stage work
(stage 5); `labor.set-labor` stays out (it races autolabor); `ledger.record`
is code-only.

### 2.4 Action tools per type [proposed]

`dfqueue/action_tools.yaml`, one line per type (draft, to check against the
charters at build time): `room_siting` and `workshop_siting`:
`blueprint.reserve`, `blueprint.apply`, `zone.place`, `zone.assign-owner`,
`building.build` (plus `workshop.build`); `stockpile_siting`:
`stockpile.place`, `.configure`, `.link`; `corridor`, `smoothing`,
`dig_order`: `blueprint.apply`, `diggable.dig-stair`,
`construction.mine-vein`; `work_order`: `orders.create`, `.reorder`,
`.cancel`, `.recheck`, `workjob.queue`, `.cancel`; `crop_plan`:
`farm.set-crop`; `stock_target`: none. A test fails if a mutating tool is in
neither this table, nor the Overseer's allowlist, nor a written `retired`
list (H5).

---

## 3. The Overseer's ruling turn

### 3.1 Prompt layout [proposed, M7 corrected]

**[verified by the red team in the openclaw image on VM 106]** openclaw puts
its framework text and `SOUL.md` before a cache boundary, then a dynamic
tail ending in a `## Runtime` line with `host=` and `sessionId=`; the runner
sets no `--hostname` **[verified]** (`conductor/runner.py`), so `host=` is a
fresh container id each run; no date line is added. Stage 0 passes a fixed
`--hostname <role>` and measures; `sessionId` stays per run, so the
cross-run prefix ends at that boundary at best, while within a turn the
prefix grows round by round (most of the saving). Order regardless: charter
(nothing volatile), tools, per-wake briefing, ask last.

### 3.2 Allowlist, removed per tool [proposed]

| Keeps throughout | Why |
|---|---|
| `queue.rule`, `queue.abandon`, `queue.escalate`, `pause.verdict` | its decisions |
| `queue.ask`, `queue.flag`, `queue.flag_close` | mechanics questions; owned follow-ups |
| `queue.pending`, `queue.project_status` | detail behind a briefing line |
| `overview.get`, `threat.scan`, `breach.check`, `stuckjobs.find` | tripwire and pause wakes |
| `gotchas.get`, `gotchas.write` | unchanged |

**Mutating tools leave per tool (H5).** When a type routing a tool goes
live (2.4), the tool leaves the Overseer's allowlist in the same deploy, so
no tool is ever both the Overseer's and the executor's (M11, by allowlist,
not prose). Tools with no type stay the Overseer's under today's
project-before-executed rule; `queue.project` and `queue.executed` leave
with the last. **Stock reads** leave when cited facts land (stage 1, user's
call); **siting reads** leave with the siting tools (stage 4), since until
then the Overseer still sites with them. An uncited fact is a defer naming
it.

### 3.3 Briefing, fixed order [proposed]

Replaces the merged-but-undeployed `facts` blocks and `briefing_extras`.

1. **Header:** wake reason and detail, tick, clock, severity word.
2. **Vitals** plus **threshold alerts** (a line only while a `policy.yaml`
   threshold is crossed; shape `{read: {tool, args, field}, per: alive|null,
   below: N, text}`; each distinct read once per cycle; a failed read drops
   its line). Same alerts for every role.
3. **Decided, do not redo:** open projects one line each (title, steps done
   of total, top blocker), open count against the WIP cap, last five rulings.
4. **Pending proposals,** fixed shape, capped at 8, count always shown: id,
   role, type, summary; the step (tool, all arguments, override-class ones
   always shown); declared phases; for a follow-up, its project and prior
   step; the filing verdict line; each cited fact as `value at tick T`, plus
   `now V` only if it changed; prediction, cost, priority; flags
   (`duplicate_of`, `overlaps proposal-N` when resolution fields match).
5. **Open items addressed to the Overseer** (flags), owner and next action.
6. **The ask, last:** "Rule on each pending proposal: accept (with urgency),
   reject, or defer naming what would change your mind; a defer closes the
   proposal and tells the proposer. Cited facts are checked and refreshed;
   judge the reasoning. Stop when each has a ruling. Expected about N calls."

The pending block comes from a conductor-only read, `queue.pending_brief`,
so citation refreshes run as server reads and the conductor's allowlist does
not grow. `docs/AGENT-LOOP.md` item 6 gains one line: bounded proposal text
is allowed alongside Tier 0 figures.

### 3.4 Bounding the turn [proposed]

- **Told:** expected calls in the ask.
- **Server cap, independent of openclaw sessions (M6).** The conductor calls
  a conductor-only `run.begin(role, cap)` before launching a role and
  `run.end` after (roles run one at a time in a cycle **[verified]**,
  `conductor/cycle.py`). The server counts that role's calls between the
  two, whatever sessions openclaw opens. Past the cap it refuses with "this
  wake's call budget is spent: defer what is unruled and stop". **Never
  refused:** `queue.rule`, `queue.escalate`, `pause.verdict`. A manual run
  with no `run.begin` has no cap.
- **Wall clock:** per wake reason in `policy.yaml`, `queue_pending` 300 s,
  but **only from the stage where the Overseer holds no mutating tool** (H6):
  a kill between an act and its record is the failure to avoid. Until then
  the current 1200 s stands **[verified]**.
- **Effort:** a per-role `reasoning_effort` only if openclaw passes one
  (unverified; stage 0 checks).

### 3.5 Ruling changes [proposed]

- `urgency` on the ruling (`normal`, `elevated`, `high`).
- **WIP cap (user's call):** accept refused while 3 projects are open unless
  urgency is `high` ("3 projects are open: defer this, or abandon one
  first"). Follow-ups joining an open project are not new projects.
- **Defer closes (H3).** Today a deferred proposal stays pending
  **[verified]** (`store.pending_proposals`). New: it closes, and the server
  opens a flag to the proposer with the defer reason as `next_action`; the
  proposer re-files when it no longer holds. `queue_pending` then fires only
  for unruled proposals.
- After the cutover (9.1), accepting a proposal with no `step` is refused
  when its type has action tools.

---

## 4. The conductor as executor

### 4.1 Authority [proposed]

- **ROSTER:** `sole_writer: overseer` keeps meaning "the one decider"
  (`ruling`, `escalation`, `abandon`). New `executor: conductor`. `project`,
  `executed`, `observation` and `amend` become executor-only (schema check
  plus an `executor_only` registry flag, the two layers `sole_writer_only`
  already uses **[verified]**). During the transition (3.2) `project` and
  `executed` also stay open to the sole writer, for its remaining tools.
- **roles.py Rule 2** becomes: a mutating DFHack tool may be held only by the
  sole writer and only while it is not in `action_tools.yaml`; system-class
  tools stay `kind: system` only.
- **Executor-only native tools, ids only, no step content ever:**
  - `queue.open_project(ruling_id)`: builds the project from the accepted
    proposal (its step, label, `public_title`; urgency and public rationale
    from the ruling). Refused if not accepted, a project exists, or the
    ruling predates the cutover.
  - `queue.apply_followup(proposal_id)`: builds an `amend` from an accepted
    or covered follow-up proposal alone: the current steps unchanged plus the
    new step with `requires: [after_step]` (the existing fresh-id rule is
    satisfied because no earlier step changes **[verified]**,
    `store.py` amend checks).
  - `queue.run_step(project_id, step_id)`: section 4.2.
  - `queue.observe(project_id, step_id)`: the reconciler, 4.4.
- A stolen conductor token can run only accepted steps, which is narrower
  than today's Overseer token.

### 4.2 `run_step`, with the issuing marker (C2) [proposed]

In one server call, strictly in this order:

1. **Preconditions,** the store's full check run **before** anything is sent
   (C3): ruling accepted; project open; step in the current version;
   `requires` satisfied; step not already succeeded; no unresolved run row
   for it; tripwire not latched unless the ruling's urgency is `high` (4.6).
2. **Dry run,** judged by the tool's verdict. Blocked: the step is classed
   Waiting or Needs judgment (4.3), nothing recorded as executed.
   `resolution_fields` differing from the stored preview: Needs judgment.
3. **Marker:** read the tick (`overview.get`), then write a `step_runs` row
   (project, step, attempt, tick, `state: issuing`) in the queue's own SQLite
   file. Both happen before the real call, so nothing after it needs a
   DFHack read.
4. **Real call** with `dry_run=false`.
5. **Record:** append `executed` (role `conductor`, outcome from the tool's
   verdict, bounded detail, the issued handle as the step's target and in
   `game_refs`) using the tick from step 3, and mark the run row `recorded`.
   Any exception from step 4 onward (timeout, unreachable, protocol error,
   a failed append) leaves the row `issuing`.

Why: the DFHack client times out at 10 s **[verified]**
(`dfmcp/dfhack_client.py`) against 45 to 80 s tick-gated latencies, and a
client timeout does not cancel a queued command.

### 4.3 Outcomes [proposed]

| Class | When | Next |
|---|---|---|
| Success | verdict ok | `executed` success; target `issued`; reconciler takes over |
| Transient | failure **before** the real call was sent (precondition read, dry run unreachable) | nothing recorded; retry next cycle; third in a row becomes Needs judgment |
| Waiting | dry run blocked while a prerequisite step's progress is still moving (4.4) | retry next cycle, no time limit while progress moves |
| Needs judgment | dry run blocked with no moving prerequisite; resolution fields changed | step held `needs_judgment`; proposer woken (5.3) |
| Failed | verdict not ok **and** the tool's `nothing_applied` holds | `executed` failure; one retry next cycle; second failure: step `failed`, proposer flagged, Overseer briefed |
| Uncertain | anything at or after the real call that is not a clean verdict, including a not-ok verdict without `nothing_applied` (M2), or a run row left `issuing` | never retried. Reconcile first: `queue.observe` reads the tool's progress or status; if it proves the call landed, record success; if it proves nothing landed, Transient; else held `uncertain` and flagged to the proposer (L2), who holds the reads |

Hold codes go in `dfqueue/public_text.yaml` as data.

### 4.4 The reconciler: done means the game says so [proposed]

Each cycle the conductor calls `queue.observe(project_id, step_id)` for
issued, not-done steps (capped). The server runs the tool's declared
`progress` read, writes an `observation` (an existing kind with no MCP path
today **[verified]**) and moves the step's target `issued` to `done` when
`done_when` holds. For `blueprint.apply`: `blueprint.status` on the issued
`site-N`, done at `dig.state: none_pending` **[verified]** that status
reports this per site, with `pending_dig_designations` and `stalled`.
**Slow digs (M3):** a step stays issued while `moving_when` holds or the dig
is `in_progress`; only `stalled_when` (the tool's own stall rule) flags the
proposer, whose remedy may be a `blueprint.release` follow-up. The dependent
step's dry run stays the final gate (`blueprint.apply` refuses a phase while
the shell is unfinished **[verified]**). The follow-up wake fires only on
done (5.1).

### 4.5 The execute phase in a cycle [proposed]

Ordinary path: read, grade, triage, advisors, Consultant, Overseer,
**execute**, archive. Execute: open projects for accepted post-cutover
rulings; apply accepted or covered follow-ups; observe issued steps; collect
ready steps (urgency, then ruling age), capped by `max_steps_per_cycle`
(start 4); quicksave once if any will run (moved from before the Overseer,
which no longer acts on proposal-routed tools); `run_step` each. A step made
ready by this phase waits for the next cycle. Execute runs even when nobody
woke, so accepted work proceeds without a model turn, **once the conductor
runs as a service** (today it is run by hand, L5).

### 4.6 Tripwire, pause, hold (H4) [proposed]

The executor never calls `clock.resume` or `clock.set-speed`; designations
and orders work paused **[verified]** (every dry run so far ran paused).

- **Tripwire.** Today a clean Overseer run with no escalation clears and
  resumes **[verified]** (`cycle.py`); with an Overseer that cannot act that
  could be "nothing done, resumed". New: quicksave; wake the owning advisor
  for the tripwire reason (data `tripwire_owners` in `policy.yaml`) with the
  fort paused; the Overseer rules and must give `pause.verdict` (silence is
  not consent, as for unexplained pauses); execute steps accepted this
  episode with urgency `high` (`run_step` allows those while latched); clear
  and resume only on `resume: true` with no escalation, else stay paused and
  alert.
- **Watchdog-owned pause, or an escalation this cycle:** no execute phase.
- **Operator hold:** no execute phase unless set with `--allow-execution`.

---

## 5. Follow-ups: one project per room

### 5.1 The wake [proposed]

When the reconciler marks a step done, the conductor raises `step_done` for
the project's proposer role, once per step. Briefing: header; the project's
line; the done step, its handle and progress read; declared phases left. Ask:
"File the next step as a follow-up naming project P and step S, or
`queue.pass` naming P to close it." Bound: 240 s and the 3.4 call cap. Same
charter and tools as its routine wakes, so the same cached prefix. Replaces
the 2026-10-01 cheap executor model (user's call).

### 5.2 Declared phases skip re-ruling [proposed]

The Overseer's accept of the first proposal accepts its declared phases. A
follow-up is **covered** when the server checks all of: same proposer role;
tool equal to `phases.tool`; arguments exactly the carried ones (equal to the
first step's), the phase argument (the next declared phase not yet applied)
and the site argument (a handle a step of this project issued), nothing
else.
A covered follow-up is closed with `covered_by: <ruling id>` and goes
straight to `apply_followup`; the Overseer's briefing shows it under
Decided. Any difference sends it to the Overseer as an ordinary pending
proposal. Phases come from the template's own data through the declared
phase source, never per-kind code.

### 5.3 Judgment at execution [proposed]

Needs judgment, Failed after its retry, and Uncertain all reach the
proposer as a flag on its project. Its moves: a follow-up with
`replaces_step: S` (the amend drops S and adds the new step; this goes to the
Overseer, since it differs from what was accepted), a recovery follow-up
(for example `blueprint.release` on a stalled site, once routed), or
`queue.flag_close` with a reason, after which the Overseer sees the project
in Decided and may abandon it.

### 5.4 Closing a project [proposed]

A project is closed when abandoned, or when every step is done and its
proposer passed on it (or no follow-up arrived within
`follow_up_window_ticks`, data). Closed projects stop counting toward the
WIP cap and refuse follow-ups.

---

## 6. Owned follow-ups and stuck jobs

### 6.1 `queue.flag` [proposed]

Any model role writes; fields `what`, `evidence`, `owner`, `next_action`,
`expires_after_ticks`; the server refuses without owner and next action.
The owner's briefing lists its open flags. **The wake is edge-triggered
(M10):** once when a flag opens, once at expiry, never every cycle. An
expired flag moves to the Overseer, which may close or reassign it. The
owner closes with `queue.flag_close(flag_id, outcome)` or a proposal naming
`flag_id`.

### 6.2 Stuck jobs [proposed]

Today `stuck_job` wakes only the Quartermaster **[verified]**. Proposed: a
stuck job whose id matches a step's `game_refs` belongs to that project's
proposer (needs `job_id` in `stuckjobs.find` rows, already a named follow-up
of the stuck-job watch); otherwise a `stuck_job_owner` table in
`policy.yaml` maps job class to role. At the renotify threshold the
conductor opens a flag with the owner pre-filled.

---

## 7. Schema and store changes (C3, M1), stated explicitly [proposed]

`dfqueue/schema.py`: proposal fields `public_title`, `step` (`tool`, `args`,
`label`), `phases`, `relies_on`, `project_id`, `after_step`, `replaces_step`,
server-set `preview`, `cited`, `covered_by`; ruling `urgency`; a server-set
`proposal_id` step key (who added the step); every executor step gets one
synthetic target, `targets: {set: ["<step id>"]}`, so target validation is
unchanged; `executed`, `project`, `amend`, `observation` get the executor as
writer (plus the sole writer for `project` and `executed` in the
transition); new kinds `flag`, `flag_close`.

`dfqueue/store.py`:

- **One completion rule.** The synthetic target is seeded `waiting` at
  project or amend time, set `issued` by a success record, `done` by an
  observation (or at success when the tool has no `progress`), `failed` by a
  final failure. `step_prerequisites_satisfied` and `step_status` then work
  unchanged, since both judge a step by its rows when rows exist
  **[verified]**. For legacy implicit steps, `_step_has_executed_record`
  counts only `outcome: success`.
- **`check_step_runnable`**: the full precondition check as one function,
  used by `run_step` before the real call and by `append`, so they agree.
- **`step_runs`** table for the C2 markers, in the same file.
- **Prediction arming (M1).** Today the first `executed` for a ruling arms
  it, failure included **[verified]**. New: a proposal arms when its own
  step first reaches `done`; one with declared phases, when its last declared
  phase is done or the project closes, whichever is first; never on a
  failure. Legacy rulings keep today's rule.
- `pending_proposals` excludes deferred and covered proposals; WIP-cap and
  follow-up refusals (3.5, 2.2 item 6).

---

## 8. What each charter keeps and loses

| Role | Keeps | Loses | Server refusals replacing prose |
|---|---|---|---|
| Overseer | rulings on reasoning, urgency, WIP judgment, escalation, verdicts (now on tripwires too), abandon, flags | each acting tool as its type lands; then `queue.project`, `queue.executed`; `queue.amend`; stock and siting reads | WIP cap; call cap; no step-less accept after cutover; allowlist load check |
| Architect, Quartermaster | their domains, now as exact single steps with declared phases and follow-ups | nothing | everything in 2.2; follow-up ownership |
| Conductor (code) | clock, tripwire, quicksave, triage, briefing; now execution and reconcile | quicksave before the Overseer (moves before execute) | ids-only tools; preconditions before the real call |

Charters shrink to lane, rubric and stop condition, tested on DeepSeek.

---

## 9. Migration and stages

### 9.1 Migration (H7) [proposed]

- **Cutover id:** the deploy enabling execution records the highest ruling
  id; `open_project` refuses rulings at or below it.
- **The 9 accepted rulings with no project:** before execution is enabled, a
  one-off operator script on VM 103 (after a SQLite online backup) writes,
  through `store.append` with today's required role (the sole writer), a
  `project` per ruling with `from_ruling` and no steps (`normalize_project`
  makes one implicit step **[verified]**) and `because: "Operator migration:
  accepted before projects existed"`. The 7 executed then read done; it then
  writes `abandon` for `ruling-0001` and `ruling-0006` naming their new
  project ids (abandon needs one **[verified]**). Open question 1.
- **Pending pre-cutover proposals with no step:** `reject`, public reason
  "re-file as an exact action", written the same way.

### 9.2 Stages

Each stage is one handoff, tests green, commit as you go, then a live check.
**Stage 1 is safe alone:** it adds reads, a field and briefing order, and
changes no write path or timeout.

| Stage | Build | Deploy targets | Live check |
|---|---|---|---|
| 0. Measure, stabilise, ship safety | Archive the envelope's `usage` and `assistantTurns` (the archive keeps `toolSummary` but drops these **[verified by the red team]**); fixed `--hostname <role>` in `runner.py`; remove `briefing_extras` and the stock `facts` blocks; ship the operator hold | vm106-conductor | dry-run cycle; one real advisor wake: cache-read tokens on later rounds, and whether a second run hits the prefix |
| 1. Cited facts and briefing | `relies_on` with server reads; `queue.pending_brief`; threshold alerts; fixed order, ask last; defer closes with a flag (H3); Overseer loses stock reads | vm103-dfmcp, vm106-conductor, vm106-agents | a ruling wake: re-fetches of cited facts (target 0) |
| 2. Actions at filing (deploys with 3, M11) | single `step`, `action_tools.yaml`, `TOOLS.yaml` verdict and dry-run data for the routed tools, filing dry run and time bound, `public_title`; proposer charters | with stage 3 | offline tests; then with 3: a blocked dry run refused with the tool's reason |
| 3. Executor for work orders | ROSTER `executor`; schema split; `step_runs`; `open_project`, `run_step`; execute phase; cutover and migration; `orders.*`, `workjob.*` and `farm.set-crop` leave the Overseer | vm103-dfmcp, vm106-conductor, vm106-agents | supervised: accept, project, run, record; a forced timeout lands as Uncertain |
| 4. Rooms grow as projects | `queue.observe` and the progress data; `step_done` wake; follow-ups, declared phases, `apply_followup`; prediction arming; WIP cap; tripwire sequence; room-type tools leave the Overseer | vm103-dfmcp, vm106-conductor, vm106-agents | one bedroom: reserve, dig, finish, meta, the Board's graph growing; a slow dig stays Waiting |
| 5. Ownership and remaining tools | `queue.flag`, edge-triggered wakes, stuck-job owners, `job_id` in `stuckjobs.find`; `DRY_RUN` added to `landmarks.build`, `openarea.build`, `diggable.dig`; types for the remaining Overseer tools or a `retired` list | vm103-dfmcp (incl. Lua), vm106-conductor, vm106-agents | a stuck job yields a flag and a close |
| 6. Bounds | `run.begin`/`run.end` call cap; the 300 s `queue_pending` timeout once the Overseer holds no mutating tool (H6); effort per role if exposed | vm103-dfmcp, vm106-conductor | compare with the stage 0 baseline |

Stages 1 and 2 both touch `queue.propose`: build in sequence. Stage 2 ships
only with stage 3, so no proposal step exists that the Overseer would run by
hand.

---

## 10. Red-team findings: where each landed

C1: verdict fields per tool (2.3, 4.3). C2: marker and tick before the call,
Uncertain never retried blind (4.2, 4.3). C3: synthetic target per step, one
completion rule, preconditions before the call (7). H1, M4, M5, M9: gone with
`open`, `fill_step`, `from_step`. H2: canonical `dry_run` refused, set after
merge, echo required (2.2). H3: defer closes and flags the proposer (3.5).
H4: owning advisor woken, verdict required, high-urgency execution while
latched (4.6). H5: per-tool removal with a mapping test (2.4, 3.2). H6: the
300 s timeout only in stage 6. H7: cutover id plus operator migration (9.1).
M1: arm on the step's done (7). M2: not-ok without `nothing_applied` is
Uncertain (4.3). M3: progress-based waiting (4.4). M6: `run.begin`/`run.end`,
decision tools exempt (3.4). M7: `--hostname`, toolSummary claim corrected
(3.1, stage 0). M8: filing time bound, busy refusal (2.2). M10:
edge-triggered flag wakes (6.1). M11: no tool is ever both the Overseer's and
the executor's (3.2). L1, L2, L5: 2.3, 4.3, 4.5.

**Deferred, L3:** the overlap flag matches identical resolution fields only;
adjacent sites are left to reservations, which refuse overlapping footprints
at reserve time **[verified]** (`reserve_site`). **For the orchestrator, L4:**
a register line that accepted amendment proposals are applied by the
executor, not by the Overseer's own `queue.amend`.

---

## 11. Risks, open questions, measures

### 11.1 Risks

- **Rubber-stamping:** dry runs, guards, reservations, quicksave and
  per-proposer grades are the backstop; watch accept rate against hit rate.
- **More rulings per room:** four proposals per room, three of them covered
  by declared phases; measure rulings per finished room.
- **Reserve drift:** a reserve by landmark and rank can resolve differently
  at execution; the `resolution_fields` comparison stops it before the call.
- **Wrong `progress` data** reads done too early or never: each entry is
  live-checked once before its tool is routed.
- **Filing latency:** dry runs are tick-gated; the busy refusal keeps a slow
  game from reading as a wrong proposal.

### 11.2 Open questions for the user

1. **Migration authorship.** The operator script writes the 9 projects, two
   abandons and any pre-cutover rejects with role `overseer`, because today's
   store allows only the sole writer; each says in its text that an operator
   wrote it. Acceptable, or wait for the executor role and write them as
   `conductor`?
2. **Tripwire verdict.** Requiring an explicit `pause.verdict` on tripwires
   changes today's rule that a clean run resumes. Confirm.
3. **Tripwire owners.** Thirst and hunger to the Quartermaster; anything
   else, and should a hostile wake anyone before a military role exists?
4. **Follow-up window.** How long a done step waits for its proposer's next
   step before the project closes (start: one routine-review interval, 7
   game days)?

### 11.3 What to measure

Baseline **[verified]**: Overseer 645 s, 37 calls; advisors 195 to 483 s.
From stage 0, per run: wall clock, tool calls and failures,
`assistantTurns`, input, output and cache-read tokens (openclaw's DeepSeek
provider prices `cacheRead` **[verified]**; whether the envelope reports it
is what stage 0 finds out). Detectors: re-fetches of briefed facts; refused
and busy filings; follow-up turns per room and their length; steps per class
in 4.3; Uncertain count; flags opened, closed, expired. Targets, not
promises: a three-proposal ruling wake under 120 s and 10 calls, and
cache-read share above half from the second round of a turn.
