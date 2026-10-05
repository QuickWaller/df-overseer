# Conductor execution: proposers pick, the Overseer rules, code acts

Date: 2026-10-05, revision 3 (after red-team passes 1 and 2,
`docs/CONDUCTOR-EXECUTION-REDTEAM.md`, and the user's answers in the last two
2026-10-05 register rows). Status: **design; stage 0 in build**
(`handoffs/2026-10-05-execution-stage-0.md`), nothing else built. **[verified]**
means read in code or on a host; everything else is **[proposed]**.
Revisions 1 and 2: `2f1bf68`, `68fb6aa`.

Governing: the 2026-10-05 register rows. Inputs:
`research/2026-10-05-procedure-briefing-and-bounded-turns.md`,
`research/2026-09-12-multi-agent-architecture-prior-art.md`,
`research/2026-09-28-job-dependency-graph.md`,
`handoffs/2026-10-05-cited-facts-briefing.md` (folded in),
`evals/live/2026-10-05-pause-safety/`.

## 0. The design in one screen

1. **One step per proposal:** one tool, exact arguments. At filing the server
   checks them, dry-runs the step, judges it by the tool's declared verdict
   fields (a missing field refuses), and reads every cited fact itself.
2. **A room is a project that grows.** The first proposal reserves the site
   and may declare the template's later phases. Each later phase is a
   follow-up proposal that joins the same project as a new step, citing the
   handle the earlier step issued; the server writes it as an `amend`, so the
   Board's graph grows (reserve, dig, finish, furnish). A follow-up that is
   exactly the next declared phase is accepted by the server; anything else
   goes to the Overseer.
3. **Rooms are the first type routed to the executor** (user's call); work
   orders follow. A type's tools leave the Overseer when it is routed.
4. **The conductor executes as code.** Its tools take ids only, so only
   accepted arguments can run. Anything failing after the real call was sent
   is **Uncertain** and is reconciled by a declared `landed` read, never
   retried blind.
5. **Done means the game says so:** a reconciler reads real progress per
   phase mode, and only then wakes the proposer.
6. **The Overseer only rules,** on content in its briefing, in a bounded
   turn. **Noticed problems get owners** (`queue.flag`).

Kept: one decider, no peer chat, the queue as write-ahead log, tripwire,
pause watchdog and operator hold, set intent and let the game execute.

**[verified]** Why: run-0004 (Overseer, 2026-10-05) took 645 s and 37 calls,
re-read stocks to check proposals, sited bedrooms itself ("overreaching"),
skipped `queue.project` and left the stuck Bed unowned. The live queue holds
9 accepted rulings and **0 projects ever**.

---

## 1. Routed types

A proposal `type` is **routed** once its tools have left the Overseer and
the executor runs them. Every new rule below applies only to routed types
(P2-H3): for an unrouted type a `step` is refused and step-less proposals
stay valid, and the Overseer acts as today under project-before-executed.
`dfqueue/action_tools.yaml` lists each type's tools and a `routed: true|false`
flag; flipping a type is one data line plus the same deploy that removes its
tools from `agents/overseer/tools.yaml`. A test fails if a mutating tool is
in no type, not on the Overseer's allowlist, and not on a written `retired`
list, or if a tool is both routed and on the Overseer's allowlist (no tool
belongs to both, so no mixed period by charter prose).

Draft table (checked against the charters at build time): `room_siting`,
`workshop_siting`, `corridor`, `smoothing`, `dig_order`: `blueprint.reserve`,
`blueprint.apply`, `blueprint.release`, `blueprint.unreserve`, `zone.place`,
`zone.assign-owner`, `building.build`, `diggable.dig-stair`,
`construction.mine-vein`; `stockpile_siting`: `stockpile.*` writes;
`work_order`: `orders.*` and `workjob.*` writes; `crop_plan`:
`farm.set-crop`; `stock_target`: none.

**Order (user's call): siting first.** Siting is the bulk of the Overseer's
measured turn and the user's explicit call; the reservations, follow-ups and
progress reads it needs are built with it. Work orders come second, not
together: they need `landed` reads (4.3) whose design depends on stage 0's
latency data, and one type per cutover keeps a failed cutover small.

---

## 2. Proposals

### 2.1 Shape [proposed]

```yaml
public_title: "Bedroom off the dining hall"     # <= 60 chars, required with a step
step:
  tool: blueprint.reserve
  args: {template: bedroom-cell-v1, purpose: "bedroom row 1", site: "Dining Hall", rank: 2}
  label: "Reserve bedroom"                      # <= 24 chars
phases: {tool: blueprint.apply, list: [dig, finish, meta]}   # optional
relies_on:                                      # cited facts, 0..6
  - {tool: stocks.availability, args: {type: BED}, field: available_units}
# a follow-up adds:
project_id: project-0004
after_step: project-0004/s1                     # becomes this step's requires edge
```

A follow-up cites the issued handle literally: the dig phase with
`site: res-7`, later phases with `site: site-12`. `blueprint.apply` carves
exactly a `res-N` and refuses one made for another template or already
carved **[verified]** (`df-overseer-blueprint.lua`, reservation branch).

### 2.2 Validation at filing [proposed]

Every refusal carries a repair message.

1. **Tool:** mutating, not system-class or `ui.*`, in a **routed** type's
   list, takes `DRY_RUN`, and has a verdict declaration (2.3).
2. **Arguments:** checked by `argv_for_call`, as a real call is. A canonical
   `dry_run` argument is refused (names are lower-cased **[verified]**,
   `dfmcp/tools.py`); the server sets it after merging. Override-class
   arguments (`allow_stranded`, `override`) are refused unless the type's
   data allows them. Coordinates are refused by the existing pattern.
3. **Dry run** through the server's internal DFHack path (the bypass
   `_stamp_cycle_snapshot` uses **[verified]**). The result must echo
   `dry_run: true`. The declared verdict decides; **a declared field that is
   absent refuses** (fail closed, P2-H1). A bounded `preview` is stored:
   verdict, one-line summary, tick, declared `resolution_fields`.
4. **Cited facts:** a read tool on the proposer's own allowlist; the server
   reads and stores `{value, tick}`; an unreadable citation refuses.
5. **Declared phases:** `phases.tool` has a `phases` entry (2.3); every
   listed phase appears, in order, in the template's own phase list read
   through that entry's source.
6. **Follow-ups:** `project_id` is a project the caller's role proposed, not
   closed; `after_step` is one of its steps; every handle argument was issued
   by a step of this project.
7. **Time bound:** 60 s per filing; a DFHack timeout returns a distinct
   "server busy, file again" refusal, not counted as a refused filing.

### 2.3 Per-tool data in `TOOLS.yaml` [proposed]

Example entries (field paths to confirm by the test below):

```yaml
blueprint.apply:
  verdict: {ok: ok, refused_if_true: [blocked], reason: blocked_reason}
  dry_run_echo: dry_run
  nothing_applied: {all_zero: [designated.dig_tiles, designated.zones, designated.buildings]}
  issues_handle: site.handle
  resolution_fields: [site.near_landmark, site.direction, site.distance_tiles,
                      site.footprint, site.orientation, level]
  phases: {arg: phase, site_arg: site, carry: [template],
           source: {tool: blueprint.plan, args: [template], list: phases, label: label, mode: mode}}
  progress: {tool: blueprint.status, args: {site_id: "$handle"}, by_mode: {...}}   # 4.4
  landed: {tool: blueprint.sites, match: {phase_applied: "$phase", handle: "$handle"}}
blueprint.reserve:
  verdict: {refused_if_true: [refused], refused_if_present: [would_strand], reason: blocked_reason}
  dry_run_echo: dry_run
  issues_handle: handle
  resolution_fields: [near_landmark, direction, distance_tiles, orientation, level]
  landed: {tool: blueprint.reservations, match: {purpose: "$purpose"}}
```

**[verified]** `blueprint.reserve` has no `ok` field: a conflict returns
`refused: true`, and a stranded footprint only sets `would_strand` and still
reserves; `designated` on `blueprint.apply` is a table of three counts. Both
fixed above (P2-H1, P2-M2 data). `would_strand` refuses because a stranded
reservation can only feed a dig the access gate will block.

**Build-time test (P2-H1):** each routed tool has recorded real outputs
(dry run, success, refusal) as fixtures, captured live during its stage; the
test fails if any declared verdict, echo, handle, resolution, progress or
landed path is absent from them.

**Tools without `DRY_RUN`** **[verified]**: `landmarks.build`,
`openarea.build`, `diggable.dig`, `labor.set-labor`, `ledger.record`. None is
proposable; adding `DRY_RUN` to the first three is stage 5 work.

---

## 3. The Overseer's ruling turn

### 3.1 Prompt layout [proposed]

**[verified by the red team, openclaw image on VM 106]** openclaw puts its
framework text and `SOUL.md` before a cache boundary, then a dynamic tail
with `host=` and `sessionId=`; the runner sets no `--hostname`, so `host=` is
a new container id each run. Stage 0 fixes the hostname and measures. Order
regardless: charter (nothing volatile), tools, per-wake briefing, ask last.

### 3.2 Allowlist [proposed]

Keeps throughout: `queue.rule`, `queue.abandon`, `queue.escalate`,
`pause.verdict`, `queue.ask`, `queue.pending`, `queue.project_status`,
`overview.get`, `threat.scan`, `breach.check`, `stuckjobs.find`,
`gotchas.get`, `gotchas.write`; `queue.flag` and `queue.flag_close` from
stage 4. **Stock reads** leave in stage 1 (cited facts land). **Siting tools
and siting reads** leave together at the stage 2 cutover (user's call).
Work-order tools leave at stage 3. `queue.project` and `queue.executed`
leave with its last mutating tool. A ruling that needs an uncited fact is a
defer naming it.

### 3.3 Briefing, fixed order [proposed]

Replaces the fixed stock lists (removed in stage 0).

1. **Header:** wake reason and detail, tick, clock, severity word.
2. **Vitals** plus **threshold alerts** (a line only while a `policy.yaml`
   threshold is crossed: `{read: {tool, args, field}, per: alive|null,
   below: N, text}`; a failed read drops its line). Same for every role.
3. **Decided, do not redo:** open projects one line each (title, steps done
   of total, top blocker), the WIP count against its cap, last five rulings.
4. **Pending proposals,** capped at 8, count shown: id, role, type, summary;
   the step (tool, every argument, override-class ones always shown);
   declared phases; for a follow-up, its project and prior step; the filing
   verdict line; cited facts as `value at tick T`, plus `now V` only if
   changed; prediction, cost, priority; `duplicate_of`; `overlaps
   proposal-N` when resolution fields match.
5. **Open items addressed to the Overseer.**
6. **The ask, last:** "Rule on each pending proposal: accept (with urgency),
   reject, or defer naming what would change your mind. Cited facts are
   checked and refreshed; judge the reasoning. Stop when each has a ruling.
   Expected about N calls."

Block 4 comes from a conductor-only read, `queue.pending_brief`, so
citation refreshes are server reads. `docs/AGENT-LOOP.md` item 6 gains one
line: bounded proposal text is allowed beside Tier 0 figures.

### 3.4 Bounding the turn [proposed]

- **Told:** expected calls in the ask.
- **Server call cap (M6, P2-M1).** The conductor calls `run.begin(role, cap,
  expires_at)` before a role and `run.end` after (roles run one at a time
  **[verified]**, `conductor/cycle.py`). The server counts that role's calls
  between them, whatever sessions openclaw opens. A new `run.begin` replaces
  any open run; an expired one counts nothing (expiry = role timeout plus
  grace), so a crash never caps the next or a manual run. Past the cap:
  "this wake's call budget is spent: defer what is unruled and stop".
  **Exempt:** `queue.rule`, `queue.escalate`, `pause.verdict`, `queue.pass`,
  `queue.abandon`, `queue.flag_close`.
- **Wall clock:** `queue_pending` 300 s only once the Overseer holds no
  mutating tool (H6); 1200 s until then **[verified]**.
- **Effort:** a per-role `reasoning_effort` only if openclaw passes one.

### 3.5 Ruling changes [proposed]

- `urgency` on the ruling (`normal`, `elevated`, `high`).
- **WIP cap (user's call):** accept refused while 3 projects are open,
  unless urgency is `high`. Counts only projects from rulings above the
  cutover id (P2-H4); follow-ups joining a project are not new projects.
- **Defer closes, from stage 4 (P2-M6):** with `queue.flag`, a deferred
  proposal closes and the proposer gets a flag carrying the reason. Until
  then a defer behaves as today (stays pending). Before that deploy, the
  live deferred proposals are listed in the stage's evals record.
- For a routed type, accepting a proposal with no `step` is refused.

---

## 4. The conductor as executor

### 4.1 Authority [proposed]

- **ROSTER:** `sole_writer: overseer` stays "the one decider" (`ruling`,
  `escalation`, `abandon`). New `executor: conductor`, which writes
  `project`, `executed`, `amend`, `observation` and the new `close` record
  (schema check plus an `executor_only` registry flag, the two layers
  `sole_writer_only` uses **[verified]**). For unrouted types the sole writer
  still writes `project` and `executed`.
- **roles.py Rule 2:** a mutating DFHack tool may be held only by the sole
  writer, and never if it belongs to a routed type.
- **Executor-only tools, ids only:**
  - `queue.open_project(ruling_id)`: builds the project from the accepted
    proposal alone. Refused if not accepted, a project exists, the ruling is
    at or below the cutover, or the proposal carries `project_id` (a
    follow-up, P2-M3).
  - `queue.apply_followup(proposal_id)`: builds an `amend` from an accepted
    or covered follow-up alone: current steps unchanged plus the new step
    (with its `proposal_id`) requiring `after_step`. Runs under the one
    write lock (P2-L1).
  - `queue.run_step(project_id, step_id)` (4.2), `queue.observe(project_id,
    step_id)` (4.4), `queue.close(project_id, outcome, reason)` (5.4, 8.1).

### 4.2 `run_step` [proposed]

One server call, in order:

1. **Preconditions** (`check_step_runnable`, also used by `append`): ruling
   accepted; project open; step current; `requires` done; not succeeded; no
   unresolved `step_runs` row; tripwire not latched unless urgency `high`.
2. **Dry run,** judged by the verdict; blocked means Waiting or Needs
   judgment (4.3). `resolution_fields` differing from the preview: Needs
   judgment.
3. **Marker:** read the tick and, if the tool declares `landed`, the
   landed read's baseline; write a `step_runs` row (project, step, attempt,
   tick, baseline, `issuing`) in the queue's SQLite file.
4. **Real call** with `dry_run=false`.
5. **Record** `executed` (role `conductor`, `ruling_id` of the project,
   `step_id`, the step's `proposal_id`, outcome from the verdict, the issued
   handle as target and `game_refs`) with the tick from 3; row `recorded`.
   Any exception from 4 onward leaves the row `issuing`.

Why: the DFHack client times out at 10 s **[verified]**
(`dfmcp/dfhack_client.py`) against 45 to 80 s tick-gated latencies, and a
client timeout does not cancel a queued command.

### 4.3 Outcomes [proposed]

| Class | When | Next |
|---|---|---|
| Success | verdict ok | target `issued`; reconciler takes over |
| Transient | failure before the real call was sent | retry next cycle; third in a row: Needs judgment |
| Waiting | dry run blocked while a prerequisite is still issued (not done) | retry next cycle |
| Needs judgment | dry run blocked with all prerequisites done; resolution fields changed | held; proposer flagged (5.3) |
| Failed | verdict not ok and `nothing_applied` holds | `executed` failure; one retry; second: step `failed`, proposer flagged |
| Uncertain | anything from the real call on that is not a clean verdict, a not-ok verdict without `nothing_applied`, or a row left `issuing` | never retried blind: run the `landed` read against the stored baseline; landed is success, not landed is Transient, unreadable is held `uncertain` and flagged to the proposer |

**`landed` (P2-M2):** every routed tool declares one. For orders it is
`orders.list` matched on job, amount and material, compared with the count
stored before the call; for blueprint phases, the phase listed as applied on
the handle. A tool without a usable `landed` read cannot be routed. Stage 0's
live runs give real-call latency from the existing per-call `duration_ms`
in the server's journal **[verified]** (`_call_log_line`), with no change to
stage 0's scope.

### 4.4 The reconciler: done per phase mode (P2-H2) [proposed]

Each cycle the conductor calls `queue.observe` for issued, not-done steps
(capped). The server runs the declared progress read, writes an
`observation`, and sets the step's target `done` when the rule for the
step's **mode** holds. The mode comes from `blueprint.plan`'s
`phases[].mode` **[verified]** (meta phases list their leaves under
`applies`). `blueprint.apply`'s `progress.by_mode`, as data:

| Mode | Done when (fields from `blueprint.status` **[verified]**) |
|---|---|
| `dig` (including smoothing) | `shell_done` true: read cell by cell, carve cells dug and smooth cells smoothed or constructed. A wall quickfort cannot smooth (`finish_state.blocked_total` above 0, with a `remedy`) flags the proposer instead |
| `build`, `place` | the phase's buildings exist on the site (field to add to `blueprint.status` if absent, stage 2 work) |
| `zone` | the phase's zone exists on the site (same) |
| `meta` | the rule of every leaf mode it applies holds |

**[verified]** `dig_progress` counts only dig flags, not smoothing, and a
build or zone phase makes no dig designations, which is why one rule per
tool read done too early. **Slow work (M3):** a step stays issued while it
is not done and `dig.state` is `in_progress` or pending counts fall.
`stalled` flags the proposer (remedy: a `blueprint.release` follow-up).
**`state: unknown`** three reads in a row flags the proposer. A tool with no
`progress` entry is done at its first success. The follow-up wake fires only
on done.

### 4.5 The execute phase [proposed]

Ordinary cycle: read, grade, triage, advisors, Consultant, Overseer,
**execute**, archive. Execute: open projects for accepted post-cutover
non-follow-up rulings; apply accepted or covered follow-ups; observe issued
steps; run ready steps by urgency then age, capped at 4; quicksave once if
any will run. A step made ready by this phase waits a cycle. Execute runs
when nobody woke, once the conductor runs as a service (today by hand).

### 4.6 Tripwire, pause, hold [proposed]

The executor never calls `clock.resume` or `clock.set-speed`; designations
and orders work paused **[verified]**.

- **Tripwire** (user's calls): quicksave; wake the owner from
  `tripwire_owners` in `policy.yaml` (thirst and hunger: Quartermaster;
  hostiles: the Overseer until a military role exists) with the fort paused;
  the Overseer rules and must give `pause.verdict`; execute routed steps
  accepted this episode with urgency `high` (allowed while latched); clear
  and resume **only on `resume: true`** with no escalation.
- **Repeated tripwires (P2-M5):** a per-cause episode counter in the
  conductor's state; a second episode of the same cause within
  `tripwire_repeat_ticks` (data) is escalated, not re-run.
- **Watchdog-owned pause or an escalation this cycle:** no execute phase.
- **Operator hold:** no execute phase unless set with `--allow-execution`.

---

## 5. Follow-ups: one project per room

### 5.1 The wake [proposed]

When a step reaches done, the conductor raises `step_done` for the
project's proposer, once per step. Briefing: the project line, the done step,
its handle and progress read, declared phases left. Ask: "File the next step
as a follow-up naming project P and step S, or `queue.pass` naming P to close
it." Bound: 240 s and the call cap. Same charter and tools as routine wakes,
so the same cached prefix. Replaces the 2026-10-01 cheap executor model.

### 5.2 Declared phases skip re-ruling [proposed]

The Overseer's accept of the first proposal accepts its declared phases. A
follow-up is **covered** when the server checks all of: same proposer role;
tool equal to `phases.tool`; arguments exactly the carried ones (equal to
the first step's), the next declared phase not yet applied, and a site
handle this project issued; and **`after_step` is the step that applied the
previous declared phase (or, for the first, the reserve step), and it is
done** (P2-M5). A covered follow-up is closed `covered_by: <ruling id>` and
goes to `apply_followup`; the briefing shows it under Decided. Anything else
goes to the Overseer.

### 5.3 Judgment at execution [proposed]

Needs judgment, Failed after retry, Uncertain unreadable, stalled and
unknown progress all flag the proposer on its project. Its moves: a recovery
follow-up (for example `blueprint.release`), a follow-up with
`replaces_step: S`, allowed only when S has no dependents and no `issued` or
`issuing` run (P2-M4; otherwise release first), or a close request
(`queue.pass` naming the project), after which the Overseer may abandon it.

### 5.4 Idle and closed projects [proposed]

**User's call:** a project with every step done and no next step is idle;
after 7 game days idle the proposer gets a `project_idle` wake (once), and
if it is still idle 7 game days later the executor closes it
(`queue.close`, outcome `completed`, reason `idle`). A proposer's
`queue.pass` naming the project closes it at once. Closed projects leave the
WIP count and refuse follow-ups. Abandoned projects are closed too.

---

## 6. Owned follow-ups and stuck jobs (stage 4) [proposed]

**`queue.flag`:** any model role writes `what`, `evidence`, `owner`,
`next_action`, `expires_after_ticks`; refused without owner and next action.
The owner's briefing lists open flags; the wake is edge-triggered (once at
open, once at expiry). An expired flag goes to the Overseer, which may close
or reassign it. Closed by `queue.flag_close` or a proposal naming
`flag_id`. Until stage 4, "flags the proposer" in 4 and 5 means a
`step_attention` wake to the proposer carrying the same fields, once per
event.

**Stuck jobs:** a stuck job whose id matches a step's `game_refs` belongs to
that project's proposer (needs `job_id` in `stuckjobs.find` rows); otherwise
`stuck_job_owner` in `policy.yaml` maps job class to role. At the renotify
threshold the conductor opens a flag with the owner filled in.

---

## 7. Schema and store changes [proposed]

`dfqueue/schema.py`: proposal fields `public_title`, `step`, `phases`,
`relies_on`, `project_id`, `after_step`, `replaces_step`, and server-set
`preview`, `cited`, `covered_by`; ruling `urgency`; `executed` gains
`proposal_id`; a server-set `proposal_id` key on steps; each executor step
gets one synthetic target, `targets: {set: ["<step id>"]}`; new kinds
`close` (executor), `flag` and `flag_close` (stage 4); executor writers as
in 4.1.

`dfqueue/store.py`:

- **One completion rule:** the synthetic target is seeded `waiting`, set
  `issued` by a success record, `done` by an observation (or at success for
  a tool with no `progress`), `failed` by a final failure.
  `step_prerequisites_satisfied` and `step_status` judge a step by its rows
  when rows exist **[verified]**, so they work unchanged. Legacy implicit
  steps count only `outcome: success`.
- **`check_step_runnable`**, shared by `run_step` and `append`.
- **`step_runs`** table (markers and `landed` baselines), same file.
- **Mapping by proposal (P2-M3):** a follow-up's ruling, or its `covered_by`,
  maps to the parent project through the step's `proposal_id`.
  `unexecuted_accepted_proposals` and prediction arming key on the step's
  `proposal_id` (falling back to `ruling_id` for legacy records), so a
  follow-up's own ruling is never listed as unexecuted forever.
- **Prediction arming (M1):** each proposal, covered follow-ups included,
  arms when its own step first reaches `done`; never on a failure. Legacy
  rulings keep today's rule.
- **Amend base check (P2-L1):** an amend that omits a previous step not
  named in `drops` or `replaces` is refused.
- `pending_proposals` excludes covered proposals, and from stage 4 deferred
  ones; WIP and follow-up refusals as above.

---

## 8. Migration and stages

### 8.1 Legacy rulings (H7, P2-H4, P2-L4) [proposed]

User's call: the 9 accepted rulings with no project are closed **only by
the executor, under its own name**, never as `overseer`. At the stage 2
cutover, after a SQLite online backup, the conductor runs a one-off
`queue.close_legacy(ruling_id, reason)` (executor-only, refused above the
cutover id) for each: it writes an implicit `project` with role `conductor`
(`normalize_project` makes one implicit step **[verified]**) and a `close`
record, outcome `completed` for the 7 executed ("pre-executor history") and
`not_done` for `ruling-0001` and `ruling-0006`. They never count toward the
WIP cap (cutover rule) and the Board shows them as the conductor's
housekeeping. Pending pre-cutover proposals of the newly routed type get an
open item in the Overseer's briefing: rule them as they are (the Overseer
still executes them under the old path for that type until the cutover, so
the cutover waits until none is pending), or the proposer re-files.

### 8.2 Stages

Each stage is one or more handoffs; tests green; commit as you go; a live
check before the next. A type cutover is one deploy.

| Stage | Build | Deploy targets | Live check |
|---|---|---|---|
| 0 (in build, scope fixed) | `handoffs/2026-10-05-execution-stage-0.md`: usage and turn measurement, fixed hostname, fixed stock lists removed, operator hold shipped | vm106-conductor | per that handoff; read real-call latency from the server journal for 4.3 |
| 1. Cited facts and briefing | `relies_on` with server reads; `queue.pending_brief`; threshold alerts; fixed order, ask last; Overseer loses stock reads | vm103-dfmcp, vm106-conductor, vm106-agents | a ruling wake: re-fetches of cited facts (target 0) |
| 2. Rooms routed | filing format and validation; `TOOLS.yaml` data and fixtures for the room tools (and the build/zone fields `blueprint.status` lacks); `action_tools.yaml`; ROSTER `executor`, schema and store changes; `open_project`, `apply_followup`, `run_step`, `observe`, `close`, `close_legacy`; execute phase; follow-ups, declared phases, `step_done`, `step_attention`, `project_idle`; WIP cap; tripwire sequence and repeat counter; legacy closes; siting tools and reads leave the Overseer | vm103-dfmcp (incl. Lua), vm106-conductor, vm106-agents | supervised: one bedroom through reserve, dig, finish, meta, the Board's graph growing; a forced timeout lands Uncertain and its `landed` read resolves it; a slow dig stays Waiting |
| 3. Work orders routed | `landed` reads for orders and workjobs (designed from stage 0 latency), their data and fixtures; `work_order` and `crop_plan` routed; their tools leave the Overseer | vm103-dfmcp, vm106-conductor, vm106-agents | an order through the executor; a timed-out create resolved by `landed`, never doubled |
| 4. Ownership | `queue.flag`, edge-triggered wakes, defer closes, stuck-job owners, `job_id` in `stuckjobs.find` | vm103-dfmcp (incl. Lua), vm106-conductor, vm106-agents | a defer reaches its proposer; a stuck job yields a flag and a close |
| 5. Remaining tools | `DRY_RUN` for `landmarks.build`, `openarea.build`, `diggable.dig`; types for the Overseer's remaining tools or the `retired` list | vm103-dfmcp (incl. Lua), vm106-agents | each newly routed tool through the executor once |
| 6. Bounds | `run.begin`/`run.end` cap; 300 s `queue_pending` once the Overseer holds no mutating tool; effort if exposed | vm103-dfmcp, vm106-conductor | compare with stage 0's baseline |

**Stage 1 is safe alone:** it adds a proposal field, server reads, a
conductor-only read and briefing order. No write path, timeout, routing or
defer behaviour changes (P2-M6 moved defer-closes to stage 4).

---

## 9. Findings: where each landed

Pass 1: C1 2.2-2.3, 4.3; C2 4.2-4.3; C3 7; H1, M4, M9 removed with `open`,
`fill_step`, `from_step`; H2 2.2; H3 3.5 (stage 4); H4 4.6; H5 1; H6 3.4;
H7 8.1; M1 7; M2 4.3; M3 4.4; M5 5.3; M6 3.4; M7 3.1 and stage 0; M8 2.2;
M10 6; M11 1; L1 2.3; L2 4.3; L4 register (2026-10-05); L5 4.5.

Pass 2: H1 2.2-2.3 and fixture test; H2 4.4; H3 1; H4 3.5 and 8.1; M1 3.4;
M2 4.3 (stage 0 data, no scope change); M3 4.1 and 7; M4 5.3; M5 5.2 and
4.6; M6 3.5 and stage 4; L1 4.1 and 7; L2 in stage 0's handoff (task 3);
L3 orientation and level added to `resolution_fields` (2.3); L4 8.1.

**Deferred:** pass-1 L3 (overlap flag matches only identical resolution
fields; adjacent sites are left to reservations, which refuse overlapping
footprints at reserve time **[verified]**, `reserve_site`).

---

## 10. Risks, open questions, measures

**Risks.** Rubber-stamping (backstop: dry runs, guards, reservations,
quicksave, per-proposer grades; watch accept rate against hit rate). Stage 2
is large: it carries the whole executor plus rooms, so its handoffs must
land and pass offline before one cutover deploy. Wrong `progress` or
`landed` data (each tool's fixtures and one live run before routing). Filing
latency (busy refusal). Rooms cost one ruling plus covered follow-ups;
measure rulings per finished room.

**Open questions for the user.**

1. **Pending room proposals at the cutover** (8.1): hold the stage 2 deploy
   until no pre-cutover room proposal is pending (recommended), or reject
   them with "re-file as an exact action"?
2. **`build`/`zone` done fields:** if `blueprint.status` lacks a per-phase
   "buildings and zone exist" read, stage 2 adds it to the Lua tool (a read
   of what a player can see). Agreed?

**Measures.** Baseline **[verified]**: Overseer 645 s, 37 calls; advisors 195
to 483 s. Per run from stage 0: wall clock, calls and failures,
`assistantTurns`, input, output and cache-read tokens, and real-call
latency. Detectors: re-fetches of briefed facts; refused and busy filings;
rulings and follow-up turns per finished room; steps per outcome class;
Uncertain count and how `landed` resolved it. Targets, not promises: a
three-proposal ruling wake under 120 s and 10 calls; cache-read share above
half from a turn's second round.
