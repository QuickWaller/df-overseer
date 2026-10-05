# Conductor execution: proposers pick, the Overseer rules, code acts

Date: 2026-10-05, revision 4 (after red-team passes 1 to 3,
`docs/CONDUCTOR-EXECUTION-REDTEAM.md`, and the user's 2026-10-05 register
rows). Status: **stages 0 and 1 deployed** (`evals/live/2026-10-05-execution-stage-0/`;
cited facts, `queue.pending_brief` and the ruling ask, per red-team pass 3);
everything from stage 2 on is design. **[verified]** means read in code or on
a host; the rest is **[proposed]**. Earlier revisions: `2f1bf68`, `68fb6aa`,
`ed6f8f5`.

## 0. The design in one screen

1. **One step per proposal:** one tool, exact arguments, dry-run by the
   server at filing and judged by the tool's declared verdict fields (a
   missing field refuses).
2. **A room is a project that grows.** The first proposal reserves the site
   and may declare the template's later phases. Each later phase is a
   follow-up that joins the same project as a new step, citing the handle the
   earlier step issued; the server writes it as an `amend`, so the Board's
   graph grows. Once switched on (2c), a follow-up that is exactly the next
   declared phase needs no new ruling.
3. **Rooms are the first type routed to the executor;** work orders follow.
   A routed type's tools leave the Overseer, and the Overseer can no longer
   write projects or records for it.
4. **The conductor executes as code** through ids-only tools. Anything that
   fails after the real call was sent is Uncertain, resolved by a declared
   `landed` read, never retried blind.
5. **Done means the game says so,** per phase: the phase's own cells dug and
   smoothed, its buildings fully constructed, its zone present.
6. **Abandoning a room** releases what that project reserved and
   designated, never the dug tiles (user's call).
7. **Old work is closed first (user's call):** deploy 2a closes every
   accepted ruling from before its cutover, under the executor's name,
   touching no game state.

Kept: one decider, no peer chat, the queue as write-ahead log, tripwire,
pause watchdog and operator hold, set intent and let the game execute.

---

## 1. Routed types

A proposal `type` is **routed** when `dfqueue/action_tools.yaml` says
`routed: true`; its tools then leave `agents/overseer/tools.yaml` in the same
deploy. New rules apply only to routed types: for an unrouted type a `step`
is refused, step-less proposals stay valid, and the Overseer acts as today.
For a routed type the store refuses a sole-writer `project`, `executed` or
`amend` (P3-B1). A test fails if a mutating tool is in no type and not on
the Overseer's allowlist or a written `retired` list, or if a routed tool is
still on the Overseer's allowlist.

```yaml
# dfqueue/action_tools.yaml (draft; check against charters when built)
rooms:      {types: [room_siting, workshop_siting, corridor, smoothing, dig_order],
             tools: [blueprint.reserve, blueprint.apply, blueprint.release, blueprint.unreserve,
                     zone.place, zone.assign-owner, building.build, diggable.dig-stair,
                     construction.mine-vein],
             routed: false, frozen: false, coverage: false}
stockpiles: {types: [stockpile_siting], tools: [stockpile.place, stockpile.configure, stockpile.link], routed: false}
orders:     {types: [work_order, crop_plan], tools: [orders.create, orders.reorder, orders.cancel,
             orders.recheck, workjob.queue, workjob.cancel, farm.set-crop], routed: false}
```

**Order (user's call):** rooms first; work orders second (stage 3), because
their `landed` reads are designed from stage 0's latency data and one group
per cutover keeps a failed cutover small.

---

## 2. Proposals

### 2.1 Shape

```yaml
public_title: "Bedroom off the dining hall"
step:
  tool: blueprint.reserve
  args: {template: bedroom-cell-v1, purpose: "bedroom row 1", site: "Dining Hall", rank: 2}
  label: "Reserve bedroom"
phases: {tool: blueprint.apply, list: [bedroom_cell_v1_shell, bedroom_cell_v1_finish]}
relies_on: [{tool: stocks.availability, args: {type: BED}, field: available_units}]
# a follow-up adds:
project_id: project-0004
after_step: project-0004/s1
```

Real phase labels **[verified]** (`blueprints/templates/bedroom-cell-v1.csv`):
`_shell` (dig), `_zone`, `_build`, and `_finish`, a meta of zone then build.
Listing `_finish` together with `_zone` or `_build` would apply them twice
and is refused (2.2 item 5).
A follow-up cites the issued handle: the shell phase with `site: res-7`,
later phases with `site: site-12`.

### 2.2 Validation at filing

1. **Tool** in a routed group, takes `DRY_RUN`, has a verdict declaration.
2. **Arguments** via `argv_for_call`; canonical `dry_run` refused (set by
   the server after merging); override-class arguments refused unless the
   group allows them; coordinates refused. For `blueprint.reserve` the server
   appends ` <proposal id>` to `purpose` (P3-B4).
3. **Dry run** through the server's internal path; must echo `dry_run:
   true`; the declared verdict decides; **an absent declared field
   refuses**. A bounded `preview` is stored (verdict, summary, tick,
   `finish_plan` for a reserve, P3-M1).
4. **Cited facts** as deployed in stage 1.
5. **Declared phases:** each listed phase exists in the template's phase
   list, in order; a list in which a `meta` phase's leaves repeat another
   listed phase is refused (P3-B2).
6. **Follow-ups:** `project_id` is a project the caller's role proposed, not
   closed; `after_step` is one of its steps; each handle was issued by this
   project. **A first proposal** may cite an existing `site-N` that no open
   project issued: that is how the Architect re-proposes finishing a
   legacy room from its handles (user's call).
7. **Time bound** 60 s; a DFHack timeout returns "server busy, file again".

### 2.3 Per-tool data in `TOOLS.yaml`

```yaml
blueprint.reserve:
  verdict: {refused_if_true: [refused], refused_if_present: [would_strand], reason: blocked_reason}
  dry_run_echo: dry_run
  issues_handle: handle
  resolution_fields: [near_landmark, direction, distance_tiles, orientation, level]   # level added by B
  landed: {tool: blueprint.reservations, new_handle_where: {purpose_ends_with: "$proposal_id"}}
blueprint.apply:
  verdict: {ok: ok, refused_if_true: [blocked], reason: blocked_reason}
  dry_run_echo: dry_run
  nothing_applied: {all_zero: [designated.dig_tiles, designated.zones, designated.buildings]}
  issues_handle: site.handle
  phases: {arg: phase, site_arg: site, carry: [template], source: {tool: blueprint.plan, args: [template]}}
  progress: {tool: blueprint.status, args: {site_id: "$handle", phase: "$phase"}, done_field: phase.done}
  landed: {carve:   {tool: blueprint.reservations, handle_field: site_handle, of: "$site"},
           on_site: {tool: blueprint.sites, phase_applied: "$phase", of: "$site"}}
```

**Resolution check (P3-H1):** `resolution_fields` are compared only for a
step whose site is resolved by landmark and rank (a reserve). A step on
`res-N` or `site-N` cannot drift, and `near_landmark` changes whenever a
nearer landmark appears, so pinned steps skip the check.

**Fixtures (P3-M2):** the fixture test runs on outputs built from the Lua
source and the real templates in B. The first real outputs come from 2b's
supervised bedroom, which records them and re-runs the test. Until then a
wrong path fails closed (refused at filing, Uncertain at execution), so no
operator-run apply is needed.

**Unproposable** (no `DRY_RUN`, **[verified]**): `landmarks.build`,
`openarea.build`, `diggable.dig`, `labor.set-labor`, `ledger.record`.

---

## 3. The Overseer's turn

Stages 0 and 1 shipped the fixed hostname, usage measurement, cited facts,
`queue.pending_brief` and the ruling ask. Remaining changes:

- **Ask and to-do line per routed type (P3-M4):** the ruling ask and the
  unexecuted line name only unrouted types, read from `action_tools.yaml`;
  for routed types the line becomes "accepted; the conductor runs it".
- **Unexecuted wake (P3-B1):** the deployed wake (`conductor/cycle.py`
  `to_carry_out`, from `queue.grade`'s `unexecuted_proposal_ids`; the
  briefing line "carry each out now (queue.project, act, queue.executed)" in
  `conductor/briefing.py`) **[verified]** must exclude routed types and key
  on the step's `proposal_id`, and is suppressed under an operator hold
  (P3-L1). Once 2a has closed every pre-cutover ruling, closed rulings no
  longer count as unexecuted, so the wake sees only post-cutover work and
  the `unexecuted_wake_ignore` stopgap is removed.
- **WIP cap 3, `high` may exceed (user's call),** with one definition of an
  open project shared by the cap and `pending_brief` (P3-M3): not closed,
  from a ruling above its group's cutover, and with a step not done or a
  declared phase not yet applied.
- **Allowlist:** siting tools and siting reads leave at 2b; work-order tools
  at stage 3; `queue.project`, `queue.executed` stay for unrouted types.
- **Call cap and 300 s timeout:** stage 6, unchanged from revision 3.

---

## 4. The executor

### 4.1 `run_step`

One server call: (1) `check_step_runnable` (ruling accepted, project open,
step current, `requires` done, not succeeded, no unresolved run, tripwire not
latched unless urgency `high`, and **the step's content equals its
`proposal_id`'s `step`**, P3-B1); (2) dry run, judged by the verdict; (3)
read the tick and the `landed` baseline (for a reserve, the set of
reservation handles), write a `step_runs` row `issuing`; (4) the real call;
(5) append `executed` with the step's `proposal_id` and the issued handle,
row `recorded`. Any exception from (4) on leaves the row `issuing`. The
DFHack client times out at 10 s against 45 to 80 s latencies **[verified]**,
and a timeout does not cancel the command.

### 4.2 Outcomes

| Class | When | Next |
|---|---|---|
| Success | verdict ok | target `issued`; reconciler takes over |
| Transient | failed before the real call | retry next cycle; third: needs judgment |
| Waiting | dry run blocked while a prerequisite is issued, not done | retry next cycle |
| Needs judgment | blocked with prerequisites done; a reserve's resolution changed | held; `step_attention` to the proposer |
| Failed | verdict not ok and `nothing_applied` | one retry; then `failed`, proposer told |
| Uncertain | anything else from the real call on, or a row left `issuing` | `landed` read against the baseline: a new reservation ending in this proposal id, or the `res-N`'s `site_handle`, or the phase on the site, is success with that handle; nothing new is Transient; unreadable is held and the proposer told |

### 4.3 Done per phase (P3-B2)

`queue.observe` runs `blueprint.status SITE PHASE`, which after B reports
for **that phase's own leaves**: dig cells dug and smooth cells smoothed or
constructed; every building the phase placed at full construction stage
(not merely existing); the phase's zone present. `phase.done` is true when
all its leaves' rules hold; a meta phase uses its leaves. Not done while
`dig.state` is `in_progress`; `stalled`, three `unknown` reads, or an
unsmoothable wall (`finish_state.blocked_total`) sends `step_attention`. Only
`done` fires `step_done`.

### 4.4 Abandon cleanup (P3-H2, user's call)

When the Overseer abandons a project, the next execute phase calls
`queue.cleanup_project`: for each handle the project issued, `blueprint.release`
withdraws that site's outstanding designations (B extends release to do so
for any pending designation of the site, not only a stalled one) and
`blueprint.unreserve` frees each `res-N` it reserved. Dug tiles are never
touched. Each call uses the `step_runs` marker as a `cleanup:<handle>` run;
results are listed on the `close` record.

### 4.5 Execute phase, hold, tripwire

Execute (after the Overseer): open projects for accepted post-cutover rulings
(not follow-ups); apply accepted or covered follow-ups; resolve Uncertain
runs; observe issued steps; cleanup abandoned projects; run ready steps by
urgency then age, at most 4, quicksaving once first. No execute phase under a
watchdog-owned pause, an escalation this cycle, or an operator hold without
`--allow-execution`. The tripwire sequence is its own stage (T, 6.2); there,
high-urgency routed steps accepted in the episode may run while latched.

---

## 5. Follow-ups

- **`step_done` wake** to the project's proposer, once per step: the
  project line, the done step and handle, declared phases left; "file the
  next step as a follow-up naming project P and step S, or `queue.pass`
  naming P to close it". 240 s.
- **Coverage (from 2c, user's call on timing):** a follow-up is covered when
  it has the same proposer role, tool `phases.tool`, exactly the carried
  arguments, the next declared phase, a handle this project issued, and
  `after_step` is the done step of the previous declared phase. Covered
  follow-ups skip the Overseer. Before 2c every follow-up is ruled.
- **Idle (user's call):** a project with every step done and no follow-up
  gets one `project_idle` wake after 7 game days and is closed (`completed`,
  `idle`) after another 7; `queue.pass` naming it closes it at once.
- **`replaces_step`** is deferred: a `release` follow-up plus abandon covers
  recovery for now (pass 3).

---

## 6. Stage 2 build: five handoffs, then deploys

A and B run in parallel; C needs A's store API and B's outputs; D needs C's
tool contracts (fakes suffice); E last. Every handoff: `git merge --ff-only
main` first, commit after each milestone, full ambient pytest and
`dfmcp/tests` in `.venv-dfmcp` green, no edits to `Working.md`, the register
or `memory/`.

### 6.1 A. Queue model

**Files:** `dfqueue/schema.py`, `dfqueue/store.py`, new
`dfqueue/action_tools.yaml` and `dfqueue/routing.py`, `dfqueue/tests/`.

**Schema:** proposal `step`, `phases`, `project_id`, `after_step`, server-set
`preview`, `covered_by`; `executed.proposal_id`; step key `proposal_id`; a
synthetic target per executor step (`targets: {set: ["<step id>"]}`); kind
`close` (`project_id` or `proposal_id` or `ruling_id`, `outcome`
`completed|not_done|abandoned|superseded`, `reason`, `cleanup`); roster
`executor: conductor` writes `project`, `executed`, `amend`, `observation`,
`close`; sole-writer `project`/`executed`/`amend` refused for routed groups.

**Store API (C calls only these):**

```python
routing.group_of(type) -> str | None;  routing.is_routed(type) -> bool;  routing.tools(group)
open_project_from_ruling(path, ruling_id) -> dict          # refuses follow-ups, unrouted, <= cutover, existing
apply_followup(path, proposal_id) -> dict                  # amend: old steps + new step; base check
check_step_runnable(path, project_id, step_id, *, latched: bool) -> list[str]   # [] = runnable
begin_step_run(path, project_id, step_id, *, tick, baseline) -> int
finish_step_run(path, run_id, executed: dict) -> dict       # appends executed, row recorded
unresolved_step_runs(path) -> list[dict];  resolve_step_run(path, run_id, outcome, handle=None)
record_observation(path, project_id, step_id, *, tick, done: bool, detail: dict) -> dict
close(path, *, target_id, outcome, reason, cleanup=None) -> dict
close_legacy(path, target_id, *, reason) -> dict   # ruling, project or pending proposal at or below its cutover;
                                                  # outcome computed: completed if an executed record exists, else not_done
legacy_targets(path, group) -> list[dict]          # every accepted ruling (and, per group, open project or
                                                  # pending proposal) at or below the cutover not yet closed
set_cutover(path, group, ruling_id) / cutover(path, group) -> str | None   # "legacy" is a group
open_projects(path) -> list[dict]                           # the one WIP definition (section 3)
unexecuted_accepted_proposals(path) -> list[dict]           # unrouted only, keyed by proposal_id
issued_handles(path, project_id) -> list[str]
```

Plus: one completion rule (synthetic target `waiting`, `issued`, `done` by
observation, `failed`), `step_runs` table and a `meta` table for cutovers,
prediction arming on a proposal's own step reaching `done` (never a failure;
legacy keeps today's rule), amend base check, `pending_proposals` excludes
covered and closed.

**Tests:** `close_legacy` computes `completed`/`not_done` and makes no
DFHack call; routed refusal for each sole-writer kind; a step whose content
differs from its proposal is not runnable; prerequisites through synthetic
targets; arming on done only; unexecuted excludes routed and follow-up
rulings; WIP count; `close_legacy` refused above the legacy cutover; amend
base check; step-run lifecycle. **Deploy:** vm103-dfmcp, with 2a.

### 6.2 B. Lua reads

**Files:** `scripts/dfhack/df-overseer-blueprint.lua`,
`df-overseer-reservations.lua` if needed, Lua logic tests (lupa). Not
`TOOLS.yaml` (C owns it; B states each new signature and output in its
Result).

**Outputs:**
- `blueprint.status SITE_ID [PHASE]`: with a phase, `phase: {label, mode,
  leaves, cells: {...}, buildings: [{kind, complete}], zone_present, done}`,
  computed over that phase's own leaves (`leaf_sections`); completion from
  the building's construction stage. Without a phase, today's output.
- `level` (relative to the landmark, like the `LEVEL` argument) in reserve
  and apply outputs; `reservation` in `blueprint.sites` rows.
- Reserve dry run returns `finish_plan` (the `finish_state` classification).
- `blueprint.release SITE [DRY_RUN] [ANY_PENDING]`: with `ANY_PENDING`,
  withdraws every outstanding designation of the site, not only a stalled
  one; never touches dug tiles. A player can erase designations; no armok.
- Fixture outputs for dry run, success and refusal of reserve, apply (each
  phase of `bedroom-cell-v1` and `office-room-v2`) and status, derived from
  the source, saved under `dfmcp/tests/fixtures/blueprint/`.

**Tests:** `office-room-v2`'s shell reads done without its floor phase;
furniture reads not done while its construction is pending; a meta phase
reads done only when its leaves do. **Deploy:** vm103-dfmcp (Lua), before
2b (reads only, safe).

### 6.3 C. Server tools

**Files:** new `dfmcp/executor_tools.py` and `dfmcp/action_data.py`,
`dfmcp/queue_tools.py` (`queue.propose` filing, `pending_brief` WIP),
`dfmcp/registry.py` (per-tool data fields), `dfmcp/roles.py` (Rule 2:
no routed tool on any model role; `executor_only` flag), `dfmcp/server.py`
(route the new module), `scripts/dfhack/TOOLS.yaml` (B's signatures, the
per-tool data), `agents/conductor/tools.yaml`, `dfmcp/tests/`.

**Tool contracts (executor-only, ids only; D uses only these):**

| Tool | Arguments | Returns |
|---|---|---|
| `queue.open_project` | `ruling_id` | `{project_id, step_ids}` or error text |
| `queue.apply_followup` | `proposal_id` | `{project_id, version, step_id}` |
| `queue.run_step` | `project_id, step_id` | `{class, executed_id?, handle?, detail}`; `class` in success, transient, waiting, needs_judgment, failed, uncertain, not_runnable (with `reasons`) |
| `queue.resolve_uncertain` | `run_id` | `{class: success|transient|uncertain, handle?}` |
| `queue.observe` | `project_id, step_id` | `{state: issued|done|stalled|unknown|blocked_material, observation_id}` |
| `queue.cleanup_project` | `project_id` | `{released: [...], unreserved: [...], failed: [...]}` |
| `queue.close` | `project_id, outcome, reason` | `{close_id}` (idle and pass closes) |
| `queue.close_legacy` | `target_id, reason` | `{close_id, outcome}`; outcome computed by the store; never calls DFHack |
| `queue.cutover` | `group, apply: bool` | `{ok, blockers: [...], cutover_id?}`; check only unless `apply` |
| `queue.execution_state` | none | open projects, ready steps, unresolved runs, abandoned awaiting cleanup, steps done since last read |

**Tests:** filing refusals (each 2.2 item, absent verdict field, `dry_run`
smuggling, meta repeat); fixture test over B's fixtures; `run_step` order
(a fake DFHack that times out after the call yields Uncertain, never a
second call); Rule 2 load refusal; WIP from `pending_brief` equals the
store's. **Deploy:** vm103-dfmcp: the close tools with 2a, the rest before
2b (inert while nothing is routed).

### 6.4 D. Conductor

**Files:** new `conductor/execute.py` (the phase, pure over a tool caller),
new `conductor/cutover.py` (`python -m conductor.cutover legacy|rooms
--check|--apply`), `conductor/cycle.py` (wire execute; unexecuted wake per
section 3), `conductor/briefing.py` (ask per unrouted type; `step_done`,
`step_attention`, `project_idle` briefings; the freeze line),
`conductor/triage.py`, `conductor/policy.py`, `conductor/policy.yaml` (new
wake reasons, `max_steps_per_cycle`, idle ticks, remove
`unexecuted_wake_ignore`), `conductor/hold.py` (`--allow-execution`),
`conductor/tests/`.

**Tests:** execute order and cap; no execute under hold, escalation or an
owned pause; Uncertain resolved before any rerun; `step_done` once per step;
idle wake then close; the unexecuted wake ignores routed types and fires no
wake under a hold; the cutover check reports blockers. **Deploy:**
vm106-conductor: `cutover.py` and the unexecuted-wake change with 2a, the
rest before 2b.

### 6.5 E. Charters and allowlists

**Files:** `agents/architect/role.md` and `tools.yaml` (the `queue.propose`
description: one step, declared phases, follow-ups, citing handles, re-
proposing a legacy room from its handles), `agents/overseer/role.md` and
`tools.yaml` (siting tools and reads removed; rooms are ruled, not
executed), `docs/STATE.md` (regenerated tool counts). **Tests:** roles load;
the routed-tool test passes with `rooms: routed: true`. **Deploy:**
vm106-agents and vm103-dfmcp, with 2b.

### 6.6 Deploys

- **2a, first and as early as possible (touches nothing in the game):**
  A, plus C's `close_legacy`, `cutover` and the conductor allowlist entries,
  plus D's `conductor/cutover.py` and the unexecuted-wake change; the rest of
  B, C and D ships later. Nothing is routed. Live: `conductor.cutover
  legacy --check` sets nothing and lists **every accepted ruling** up to the
  current highest (user: "the current projects could just be nixed"), not
  only the 9 with no project; `--apply` records the legacy cutover and closes
  each under the conductor's name, `completed` where an `executed` record
  exists and `not_done` otherwise, with no DFHack call. The Board shows the
  conductor's closes; the unexecuted wake is empty; `unexecuted_wake_ignore`
  is then removed.
- **T, tripwire alone:** `tripwire_owners` (thirst and hunger: Quartermaster;
  hostiles: the Overseer), explicit `pause.verdict` to resume, the per-cause
  repeat counter. `conductor/cycle.py`, `policy.yaml`, the Overseer
  charter's verdict line. Deploy vm106-conductor, vm106-agents; live check
  by a forced test tripwire on the paused fort.
- **2b, rooms routed:** first set `rooms.frozen: true`; the Architect's
  briefing then says room work waits for the next deploy and it skips room
  work (user's call: skipped, not refused). After at least one Overseer wake
  under the freeze, `conductor.cutover rooms --check` lists what remains:
  accepted room rulings without `executed`, open room projects, pending room
  proposals. `--apply` closes all of them through `close_legacy` (user's
  call for accepted work; the Architect may re-propose from the same
  handles), sets the rooms cutover, and the same deploy flips `routed: true`
  and ships E. Then the supervised bedroom, every follow-up ruled, recording
  the first real outputs as fixtures.
- **2c, coverage on:** `rooms.coverage: true` after the supervised bedroom
  works (user's call on timing).

Later stages as in revision 3: 3 work orders routed (with their `landed`
reads), 4 `queue.flag` and defer-closes and stuck-job owners, 5 `DRY_RUN`
for the unproposable tools and the `retired` list, 6 call cap and the 300 s
timeout.

---

## 7. Findings: where each landed

Pass 3: B1 sections 1, 3, 4.1 and A; B2 2.1, 2.2, 4.3 and B; B3 6.6 (freeze,
broadened precondition, `close_legacy` for what remains); B4 2.2, 2.3, 4.2;
H1 2.3; H2 4.4 (user's call); M1 2.2 and B; M2 2.3; M3 section 3 and A; M4
section 3; L1 section 3 and D. Passes 1 and 2: as listed in revision 3 (9),
with `replaces_step` now deferred.

**Deferred:** `replaces_step` (recovery by `release` plus abandon is enough
until a real case needs it); pass-1 L3 (overlap flag matches only identical
resolution fields; reservations refuse overlapping footprints at reserve
time **[verified]**).

## 8. Risks, questions, measures

**Risks.** Rubber-stamping (dry runs, guards, reservations, quicksave,
per-proposer grades). Fixtures built from source until 2b (fail closed). The
freeze stalls new rooms for as long as 2b takes. `ANY_PENDING` release must
never erase another project's designations: it acts only on the site's own
footprint, which reservations keep exclusive.

**Open question for the user.** Pending room proposals at the 2b cutover
(not yet ruled): close them through `close_legacy` with "re-file as an exact
action" (proposed, consistent with your call on accepted work), or have the
Overseer rule them first?

**Measures.** Stage 0 baseline **[verified]**: Overseer 13 rounds, 323 s;
Quartermaster 9 rounds, about 300 s; 90 to 93% of input tokens cache reads.
Track rounds, reasoning tokens and calls per wake; rulings and follow-up
turns per finished room; steps per outcome class; Uncertain and how `landed`
resolved it; cleanup results per abandon.
