# Policy audit: existing plans and infrastructure against "set intent, let the game execute"

> **Orchestrator corrections, 2026-09-30, after checking the code.**
> 1. `df-overseer-building.lua` does **not** write a material class into a buildingplan filter. It only checks `plugins.buildingplan.isEnabled()` (line 951); `blueprint_text` writes the kind's key with no material, and `resolve_material_choice` only chooses a material for the report. So `building.build` has the same report-only gap as `construction.build`'s `material_report` (change list item 2 applies to both). The "Keep" row for it below is wrong.
> 2. `prioritize` is not armok-tagged (`docs/DFHACK-INVENTORY.md`: `fort, auto, jobs`), and `docs/ARMOK-RULINGS.md` has no ruling on it (the cited line is `lever pull --priority`). As understood from DFHack's docs (unconfirmed on this install), `prioritize` works by setting the `do_now` flag on chosen job types, which collides with the user's ruling that "do now" is reserved for genuine problems. Needs the user's decision before item 4 is built.

Date: 2026-09-30. Reviewer (Sonnet), review only: no code changes, no live access.
Brief: `handoffs/2026-09-30-policy-audit.md`.

## The policy being applied

`decisions/DECISIONS.md` 2026-09-30, in order: "Principle: set intent, let the
game execute" and "Applying ... to what exists" are the two load-bearing rows.
Short form: our layer decides *what* the fort should achieve and *whether it is
working*; DF schedules dwarves, workshops and materials (manager orders with
conditions/repeat/priority, workshop job priority and queues, labor-based job
choice, buildingplan, burrows); we step in only where the game genuinely
cannot. Specific rulings already made (materials as a buildingplan filter
class, manager orders as the main production/standing-goal route with
`workjob.queue` as fallback, autolabor as the default labor engine with
`set-labor` as the exception, priority mapped onto native levers with "do now"
reserved for emergencies and `prioritize` as the routine lever, `production/`
narrowed to one read plus observed rates) are the classification yardstick
below.

## Plan for this document

1. `scripts/dfhack/*.lua` + `TOOLS.yaml`, grouped by file/command, each row
   Keep / Simplify onto native / Fallback only / Unused-ahead-of-need /
   Conflicts with the game, with file:line evidence.
2. `dfmcp/`, `dfqueue/`, `conductor/` (policy, triage, order_watch),
   `production/`, `learning/`, `doctrine/`.
3. `agents/*/role.md` + `tools.yaml` charters.
4. Plans: `ROADMAP.md`, `Working.md`, the four named `research/` design docs.
5. Native mechanisms not yet used, verified/unverified against this install.
6. Ordered change list, smallest/most valuable first, user decisions marked.

Committing this plan now per the brief's instruction, then each section as it
lands.

## Short answer

Most of `scripts/dfhack/` already matches the policy: it is perception
(read tools) or genuine step-ins DF has no menu for (siting a workshop,
assigning a zone owner, placing a farm plot's crop, holding a reserved
tile). The two real conflicts are narrow and already flagged live:
`labor.set-labor` racing autolabor (Working.md START HERE, decisions
register 2026-09-12), and `construction.build`'s material choice being
report-only rather than a real buildingplan filter (Working.md 2026-09-30,
"corrected the same day: the generated blueprint carries no material").
`workjob.queue` and `orders.create` already sit in the right order (direct
job is documented as the fallback, orders.lua is the wrapper around the
real manager-order path) but the code comments still carry the stale
"orders never dispatch" framing the register just retired. The real gap is
absence, not presence: nothing in this repo wraps DFHack `prioritize`,
workshop "do now", or designation priority 1-7 (confirmed by grep, see
Native mechanisms below) even though the priority ruling names them as the
intended levers, and `production/`'s blocker/cover machinery (about 2,100
lines across `blocker.py`/`cover.py`/`labors.py`/`labor_ingest.py`) is a
second AND-OR/thermostat planner sitting beside the very manager-order
conditions the policy now says should do that job — the decision says
"freeze the rest" and this audit agrees it should stay frozen, not be
extended. The goal-tree design line (three long `research/` documents,
2,369 lines in the design doc alone) is almost entirely the deferred half
of the 2026-09-30 "lean core" decision: only projects+checks, reservations,
the conductor step-runner, and the two live bugs are still live work: the
claims allocator, priority maths, preemption, the Marshal and the learning
role are explicitly parked pending a real run.

## 1. `scripts/dfhack/*.lua` and `TOOLS.yaml`, by area

Evidence is cited by file:line. Read tools with no scheduling behaviour
(pure `effect: read` perception) are classified from the manifest's own
`effect` tag plus a header-comment read, not a full line-by-line trace of
every function; that is proportionate to the policy question (which asks
about scheduling and stepping in), and is called out per row rather than
implied.

| Area | Files / commands | Classification | Evidence |
|---|---|---|---|
| Connectivity, landmarks, overview, diff, chokepoints, trees, well (find/build), stuckjobs, threat, breach, stocks, surface, vitals, ledger, nobles (list/verify/requirements), ui, fort, clock, announcement-levels | all `effect: read` entries in `TOOLS.yaml` (e.g. `scripts/dfhack/TOOLS.yaml:107-144, 204-293, 1499-1523, 1523-1681, 1681-1902, 2158-2264, 2700-2774, 2774-2828`) | **Keep** — perception, "is it working," never a scheduling decision | Manifest `effect: read` per row, cross-checked against each file's own header comment (e.g. `df-overseer-stockpile.lua:1-16`: "two commands, both read-only... a pile at 80% and rising predicts a backed-up workshop before it happens") |
| `df-overseer-orders.lua` `create JOB AMOUNT`, `cancel`, `check-duplicate` | Wraps `workorder.lua`'s `create_orders()`/`preprocess_orders()`/`fillin_defaults()` directly, `scripts/dfhack/df-overseer-orders.lua:7,20-23`; writes into `df.global.world.manager_orders.all`, line 52 | **Keep** — this already *is* the native manager-order mechanism the policy names as the main route | `df-overseer-orders.lua:1-55`. Header comment (lines 39-55) still frames the Manager-appointment question as live and unresolved; the register (2026-09-30, "Manager" row) has since settled it in the tool's favour ("the user reports manager orders work... orders become the main route"). The comment is now stale relative to the decision, not the code. |
| `df-overseer-orders.lua` hard-coded `JOB TYPES` table (blocks/mechanisms/barrels/brew_drink, 4 entries), lines 25-37 | **Simplify onto native mechanism** — the game's own generic job list | `df-overseer-workjob.lua:26-43` already solved the identical generalisation problem for direct jobs by reading `hack/lua/dfhack/workshops.lua`'s `getJobs()` live instead of hand-listing jobs, explicitly citing this repo's own "tools must be generalisable" rule and naming orders.lua's twelve-entry table as the prior violation (`df-overseer-workjob.lua:26-30`: "the exact shape of CLAUDE.md's 'tools must be generalisable' rule being broken"). `orders.lua`'s 4-entry table (down from twelve after some prior trim, per that same comment) is the same class of hard-coded job list and should read the job-type universe from `df.job_type`/the raws the same way, rather than adding a fifth entry by hand next time a role needs a new order type. |
| `df-overseer-workjob.lua` `queue JOB WORKSHOP_LANDMARK_NAME [REPEAT] [COUNT]` | **Fallback only**, already documented that way | `df-overseer-workjob.lua:16-21`: "a direct job at a workshop is not in that [manager order] queue and never was. This file is that action." This matches the register's ruling verbatim ("`workjob.queue` the fallback") — no change needed, but the file's own header should be updated once manager orders are confirmed live so it stops reading as the *primary* route to production (its comment currently opens with "the only route this project has... none of which any existing tool can produce," predating the order tool). |
| `df-overseer-building.lua` `find`/`build KIND ... [MATERIAL_CHOICE]` | **Keep** — already writes a material *class* filter, game picks the item, exactly the materials ruling | `df-overseer-building.lua:80-152` (design doc), `:840-904` (`resolve_material_choice`, excludes economic materials by default, explicit name always wins) |
| `df-overseer-workshop.lua` `build KIND ... [MATERIAL_CHOICE]` | **Keep** — reuses building.lua's module rather than a second material path | `df-overseer-workshop.lua:130`: `local building_mod = reqscript('df-overseer-building')` |
| `df-overseer-construction.lua` `build ZONE_ID KIND [DRY_RUN]`'s `material_report` | **Conflicts with the game (live gap, already caught)** — advisory text only, not a real filter | `scripts/dfhack/TOOLS.yaml:2321-2325`: "`material_report` is advisory only... quickfort/buildingplan make the real material choice at build time regardless." `Working.md:29` (2026-09-30 deploy line): "the generated blueprint carries no material, so buildingplan still picks the closest item, which can be ore; `building.build`'s ore avoidance is advisory until the blueprint or buildingplan filter carries the material." Already tracked as an open gap, not a new finding, but it is exactly the materials ruling's failure mode (our layer *reports* a class instead of *writing* it) and belongs on the change list below. |
| `df-overseer-labor.lua` `set-labor UNIT_ID LABOR_NAME on|off` | **Conflicts with the game** — the exact case the register already names | `df-overseer-labor.lua:1-20` (autolabor identified as the sensible baseline, "enabling it is a separate decision this script does not make"); `decisions/DECISIONS.md` 2026-09-30 "Labor" row: "`labor.set-labor` becomes the exception tool." `Working.md` START HERE (per `decisions/DECISIONS.md` 2026-09-12) already names `set_labor` racing autolabor as a known single-writer violation. Not a new finding; the ruling has already narrowed this tool to per-dwarf exceptions, matching the policy — no further change needed beyond making sure no role charter still calls it as a routine lever (checked in §3 below). |
| `df-overseer-labor.lua` `enabled-counts LABOR...` | **Keep** — read-only, feeds the not-yet-built `labor.quota` tool the decision calls for | `df-overseer-labor.lua:49-58` |
| — no `labor.quota` (per-labor-target) tool exists | **Unused or ahead of need — actually missing, not frozen** | Grep of `scripts/dfhack/*.lua` and `TOOLS.yaml` for `quota` returns nothing. The decisions register (2026-09-30 "Labor" row) already calls for "a `labor.quota` tool" as the intended interface to autolabor's own per-labor targets; it is not built. This is a genuine to-build item, not a frozen one — listed in the change list. |
| No `prioritize`, workshop "do now," or designation-priority (1-7) wrapper anywhere | **Unused native mechanism, not yet wrapped** | `grep -rn "prioritize\|do_now\|do-now\|priority"` across `scripts/dfhack/*.lua` and `TOOLS.yaml` returns one incidental hit (a comment in `TOOLS.yaml:1806` about job priority in an unrelated stuck-jobs note). Matches the register's own 2026-09-30 "'Do now' reserved..." row dispatching this exact audit because the priority lever is still unbuilt. |
| `df-overseer-zone.lua` `assign-owner`/`clear-owner`/`place`/`build ZONE_ID KIND` | **Keep** — a player action (zone designation, ownership) the game does not do for itself | `TOOLS.yaml:1021-1103` (assign/clear-owner), `:925-977` (place); zone assignment has no autonomous native equivalent, unlike production scheduling |
| `df-overseer-farm.lua` `find`/`build`/`set-crop` | **Keep** — siting a plot and choosing what to grow is fort intent, not something DF decides on its own | `df-overseer-farm.lua:1-16` |
| `df-overseer-blueprint.lua` `reserve`/`reservations`/`unreserve`, `plan`/`preview`/`apply` | **Keep** — a genuine step-in: DF has no "hold this ground for a planned room" concept at all | `decisions/DECISIONS.md` 2026-09-30 reservation rows; `TOOLS.yaml:2465-2512` |
| `df-overseer-construction.lua` `mine-vein`, `keeps_access`/`item_present` guards | **Keep** — a step-in for a gap DF's own suspend-manager reasoning doesn't cover (sealing off reachable, unmined ore) | `TOOLS.yaml:2308-2320`, modelled explicitly on DFHack's own `suspendmanager` reasons per that same comment |

Every command signature in `TOOLS.yaml` was enumerated (see the command-key
grep in this session's trail); the rows above group them by the policy
question rather than repeating all ~90 one at a time, since the large
majority (every pure-`read` perception tool) share one classification and
one reason.

## 2. `dfmcp/`, `dfqueue/`, `conductor/`, `production/`, `learning/`, `dfseries`, `gotchas`, `doctrine/`

| Component | Classification | Evidence |
|---|---|---|
| `dfmcp/registry.py`, `roles.py`, `tools.py`, `server.py`, `auth.py` | **Keep** — the tool boundary itself (allowlists, knowledge-scope refusal, sole-writer enforcement); it enforces the policy, it isn't itself a scheduling decision | `dfmcp/roles.py` (sole-writer, omniscient-refusal rules cited throughout the register, e.g. 2026-09-30 "the architect could not be granted `reserve`/`unreserve`... `dfmcp/roles.py` refuses any mutating grant to a non-sole-writer role") |
| `dfmcp/series_tools.py` (`series.*`) | **Keep** — read-only history, perception | `dfmcp/series_tools.py:1-9`: "read-only, no write of any kind" |
| `dfmcp/gotchas_tools.py`/`gotchas_store.py` (`gotchas.get`/`gotchas.write`) | **Keep, out of policy scope** — this is the project's own notes on tool reliability, not fort scheduling | `dfmcp/gotchas_tools.py:1-16` |
| `dfmcp/doctrine_tools.py`, `doctrine/seed.yaml`, `doctrine/validate.py`, `doctrine/wiki_check.py` | **Keep** — a game-facts database (crop/water/material rules with provenance), explicitly not a decision-maker | `doctrine/seed.yaml:1-4`: "Seed doctrine: game knowledge for the agents, not repo decisions." `CLAUDE.md`'s own status line makes the same distinction ("Game knowledge... goes in `doctrine/seed.yaml`, not the register"). |
| `dfqueue/` (`schema.py`, `store.py`, `grade.py`, `render.py`) — proposal/pass/ruling/executed/ask/answer/escalation/project/observation | **Keep** — this *is* the "what should the fort achieve, and is it working" layer the policy assigns to us; nothing here schedules a job or picks a material | `dfqueue/schema.py:1-30` (nine record kinds, none of them a scheduling primitive); the 2026-09-30 project/observation additions implement exactly the "projects with checks" piece of the lean core, not something the policy retires |
| `conductor/policy.yaml`, `triage.py` | **Keep** — wake rules and clock policy are the "is it working" watchdog, data-driven, no scheduling logic of their own | `conductor/policy.yaml:1-13` ("Nothing in conductor/cycle.py branches on a literal wake-reason string"); `conductor/triage.py:1-12` |
| `conductor/order_watch.py` | **Keep** — exactly the step-in DF cannot do for itself: a stalled/blocked manager order produces no announcement at all, so someone has to poll and diff | `conductor/order_watch.py:1-11`: "a manager order that never dispatches a job produces **no announcement of any kind**... The only way to see this class of failure is to poll `orders.list` and diff." This is squarely "whether it is working," the half of the policy our layer keeps regardless of the manager-orders ruling. |
| `conductor/cycle.py`, `runner.py`, `mcp_client.py`, `game_tick.py`, `service.py`, `status.py`, `briefing.py`, `archive.py`, `cursors.py`, `config.py` | **Keep** — the loop shell (snapshot read, wake, dispatch to advisors, clock control); none of it re-implements job scheduling | Not independently re-read line by line this pass; classified from `conductor/policy.yaml`'s own description of the loop's shape and the 2026-09-30 register rows describing five real `--once` cycles running through this code without incident. Flagged as a lighter-touch check, per this document's evidence-standard note in §1. |
| `production/schema.py`, `store.py`, `extract.py`, `snapshot.py` | **Keep** — the bill-of-materials graph itself: read raws once, store a graph, translate live tool output into the shape `blocker`/`cover` expect. This is the "one read" the 2026-09-30 decision explicitly keeps. | `production/schema.py:1-10` (schema is a straight copy of the design doc, corrections load-bearing); `production/store.py:1-11` ("the extractor populates the whole database in one run"); `decisions/DECISIONS.md` 2026-09-30 "Applying..." row: "wire the bill-of-materials walker as one read and observed consumption/production rates from the series store... freeze the rest." |
| `production/blocker.py` (AND-OR walk: "what's blocking this goal") | **Simplify onto native mechanism / freeze** — this is a second planner sitting beside manager-order conditions and repeat orders, which the policy now assigns this exact job to the game | `production/blocker.py:1-10`: "A goal needs *all* of its reagents... [the walk reports] the first node with zero available stock." That is precisely "how workshops/materials get scheduled," which decision 570/569 assigns to DF's own manager-order conditions and repeat jobs, not to a second bespoke walker. Matches the decision's own "freeze the rest" instruction verbatim; not a new finding, but confirms the freeze is correctly scoped and should not be quietly extended. |
| `production/cover.py` (days-of-cover, thermostat targets) | **Simplify onto native mechanism / freeze, with one piece kept** — the rate *measurement* (`production_observation` deltas) is the "observed consumption/production rate" decision 570 explicitly wants wired; the *target/threshold* logic (low-mark/high-mark, `days_at_population`) duplicates the still-deferred "standing goals as thermostat" design (goal-tree walk-through item 8, register 2026-09-30, itself explicitly parked pending a real run) | `production/cover.py:1-20` ("a measured per-dwarf consumption rate... `days_at_population`"); `decisions/DECISIONS.md` 2026-09-30 goal-tree item 8 row: thermostat targets are designed, not built, and folded into the deferred half of the lean-core decision |
| `production/labors.py`, `labor_ingest.py` (which labor operates a workshop kind) | **Keep** — this answers a *requirements* question (what labor does building X need, for the building tool's gap-reporting), not an ongoing scheduling question; autolabor still decides who actually works | `production/labors.py:1-10`: "contract C2 of `docs/BUILDING-TOOL.md`... a workshop's operating labors are the labors of the processes it hosts." Feeds `building.lua`'s `requirements_for` gap list (`df-overseer-building.lua:945`), not a live labor-scheduling loop. |
| `learning/live_signals.py` | **Keep** — perception for prediction grading, reads existing tools, no scheduling | `learning/live_signals.py:1-14`: "reads live tool output... never touch[es]" the ledger or predictions store |
| `learning/ledger/`, `learning/predictions/` | **Not independently re-read this pass** | Out of the handoff's explicit code list (`conductor/`, `production/`, `learning/`, `dfseries`, `gotchas`, `doctrine/` were named; `learning/ledger`/`learning/predictions` are named only as siblings in `live_signals.py`'s own docstring). Flagged as unverified rather than silently assumed clean. |

No component in this section writes a second scheduler that competes with
DF's own job dispatch, *except* `production/blocker.py` and the
target/threshold half of `production/cover.py`, both of which the
2026-09-30 decision already orders frozen. The audit's contribution here is
confirming that freeze is the right scope (not too broad — the graph and
the rate measurement stay live and useful — not too narrow — the AND-OR walk
and thermostat targets really do duplicate what manager-order conditions and
repeat orders are meant to do now).

## 3. `agents/*/role.md` and `tools.yaml`

| Charter | Classification | Evidence |
|---|---|---|
| `agents/quartermaster/role.md:24-30`, `work_order` proposal type | **Keep the mechanism, fix stale text** — the charter already frames manager order vs. direct job as a real choice with a rationale requirement, which is the right shape; its factual claim is out of date | Lines 27-28: "this fort's own history is that queued manager orders do not currently run (no Office for the appointed Manager)". `decisions/DECISIONS.md` 2026-09-30 "Manager" row supersedes this: "the user reports manager orders work... orders become the main route for workshop production and standing goals, `workjob.queue` the fallback." The charter should say manager orders are the default choice now, with direct job as fallback, not present them as a live coin-flip. |
| `agents/architect/tools.yaml:398-409`, `agents/quartermaster/tools.yaml:198-203` (`labor.set-labor` withheld) | **Keep — already correctly aligned, no change needed** | Both files explicitly withhold `labor.set-labor` from the advisor with the reason "it races autolabor regardless." This is the policy's autolabor ruling already implemented, not a gap. |
| `agents/overseer/tools.yaml:501-511` (`labor.set-labor` granted, sole exception) | **Keep** — matches "the exception tool" ruling exactly | Line 511: "Treat any set-labor call as 'this labor is now hand-managed for [this unit]'" |
| `agents/overseer/role.md:17-19`, priority section | **Simplify onto native mechanism (once built)** — correctly distinguishes DF's two priority mechanisms today, but has no hook for `prioritize` or workshop "do now" because neither tool exists yet (§1 above) | Lines 17-19: "priority is two different mechanisms: DF's 1-7 for dig designations, and list position for manager work orders." Needs a third line once `prioritize`/`do now` tools are built, and should state the "do now reserved for genuine problems" rule from `decisions/DECISIONS.md` 2026-09-30 explicitly, since nothing in this charter currently says that. |
| `agents/marshal/role.md` | **Already frozen, matches the paused ruling** | Line 3: "**NOT ENABLED.** Blocked on a trustworthy threat signal *and* on write tools. No `tools.yaml` or `model.yaml` yet." Matches `decisions/DECISIONS.md` 2026-09-30 ("the Marshal... its emergency authority is paused for a later session") without needing a change. |
| `agents/consultant/tools.yaml:228` (`labor.*` wildcard) | **Not independently re-verified this pass** — plausible (Consultant only answers questions, never acts) but the wildcard's exact tool set was not enumerated against the allowlist rules | Grep only; flagged rather than assumed |
| `agents/conductor/role.md`, `agents/conductor/tools.yaml` | **Not independently re-read this pass beyond what §2's `conductor/` review covered** | Time-boxed; the code review (`conductor/policy.py`, `triage.py`, `order_watch.py`) is the stronger evidence for this component, and the charter itself was not diffed against it line by line |

The pattern across charters is reassuring: every place a role is asked to
respect autolabor or "advisors do not act" is already correct. The one real
drift is quartermaster's stale factual claim about manager orders, which is
a one-line text fix following an already-made ruling, not a new decision.

## 4. Plans: `ROADMAP.md`, `Working.md`, the four `research/` designs

**`ROADMAP.md`** — **stale, needs a review pass, not a policy conflict.**
`ROADMAP.md:1-13`'s own "Last reviewed" stamp is 2026-09-25; the Now bucket's
top item (`ROADMAP.md:120-149`) still frames "Manager work orders still
never dispatch a job; the user's ruling is to set this aside" as current and
does not mention reservations, the goal-tree design/red-team, item-binding,
the lean-core decision, or this policy audit at all — five days and roughly
a dozen register rows of work. `CLAUDE.md`'s own update trigger ("a
Now-bucket item starting or finishing... a lightweight full-review pass at
least every ~2 weeks regardless") calls for a pass here; this is a finding
to hand to the orchestrating session, not something this review edited
(out of scope: review only).

**`Working.md`** — **current and internally consistent with the policy**,
already narrating the lean-core decision, the deferred goal-tree pieces,
and the still-open item-binding decisions accurately (`Working.md:33`: "the
walk-through with the user 2026-09-30... settled on a lean core... Open:
item-binding's six decisions, Marshal emergency authority, the designer's
slice-or-groups and runner-only-issuer questions, a live test of manager
orders."). No conflict found; this file is doing its job.

**The four research designs**, cross-checked against the register's own
2026-09-30 walk-through rows (562-571), which already record the user's
line-by-line acceptance/deferral of each design's pieces:

- **`research/2026-09-28-job-dependency-graph.md`** (projects, steps, guards)
  — **mostly built, not superseded.** Its core recommendation (proposal →
  project → step, `requires`/`guards`/`prefer_after` edges) is exactly what
  landed as `dfqueue`'s `project`/`observation` records and the
  `keeps_access`/`item_present` guards (`decisions/DECISIONS.md` 2026-09-30
  "Project MCP tools merged" row; `Working.md:26`). The lean-core decision
  keeps this whole layer (item 1 of the five kept pieces: "projects with
  checks plus amend and abandon records").
- **`research/2026-09-30-goal-tree-design.md`** — **mostly deferred
  direction, one slice kept.** The lean-core decision (`decisions/
  DECISIONS.md` 2026-09-30 "Principle" row) explicitly keeps only: projects
  with checks, reservations, the conductor running approved steps with
  preview/named-holds/one-snapshot-read, and standing goals as manager
  orders with our check as a fallback watcher. Everything else this design
  covers — the claims allocator, priority/slack maths, preemption, fair
  share, deadlock detection, the learning role, the Marshal, filling the 12
  job groups beyond what one real run needs — is "deferred until a real run
  shows the need." The policy does not so much change this design as defer
  most of it; nothing in it conflicts with "set intent, let the game
  execute" since it was written as the layer *above* native scheduling, not
  a replacement for it.
- **`research/2026-09-30-goal-tree-red-team.md`** — **its must-fix findings
  (F-1 through F-5) are the parts already acted on**, independent of how
  much of the parent design is deferred: `RES_ID` pinning a site (F-1),
  amend/abandon records (F-3), idempotency keys (F-2), and claims/lane
  enforcement (F-4/F-5) are named in the register as items to fix "before
  building" and are already reflected in the reservation and project-record
  work above. The red team's other 15 findings are deferred along with the
  parent design.
- **`research/2026-09-30-item-binding-design.md`** — **still open, six
  decisions pending the user**, per `Working.md:33`. Not itself in tension
  with the policy (claims/binding is about avoiding double-promising a
  specific item, which stays our layer's job even once the game schedules
  the work); the register does not record it as superseded or built.

No design document reviewed asks a role or the conductor to schedule
workshop jobs, pick concrete items, or manage per-dwarf labor directly —
all four already assume the game does that, and layer projects/claims/checks
on top. The policy mainly prunes scope (defer the claims allocator, priority
maths, preemption, Marshal, learning role) rather than correcting a
direction that was wrong.

## 5. Native mechanisms not yet used but the policy names

| Mechanism | Status on this install | Evidence |
|---|---|---|
| `prioritize` (script, "Automatically boost the priority of important job types") | **Verified present, no armok tag; live behaviour unverified** | `docs/DFHACK-INVENTORY.md:531`: `prioritize \| script \| yes \| fort, auto, jobs`. No `armok` tag, so allowed under the no-armok rule; never called by any tool in this repo (§1). `decisions/DECISIONS.md` 2026-09-30's own last row: "DFHack `prioritize` is worth using for routine priority (armok status still to confirm)" — this audit confirms the *tag* question (no armok tag present) but not whether calling it behaves as documented, since no VM access this pass. |
| Workshop "do now" flag (`job.flags.do_now`) | **Verified as a real field, one precedent already ruled on** | `docs/ARMOK-RULINGS.md:23`: `lever pull --priority` sets `do_now`, ruled **allowed** 2026-09-21 for "emergency drawbridges and traps" — the same flag the 2026-09-30 ruling now restricts to "genuine problems and emergencies, never routine ordering." The existing ruling and the new one agree; no tool wraps it for workshop jobs yet. |
| Designation priority 1-7 (dig/build order priority) | **Referenced correctly in `agents/overseer/role.md:17-19`**, no dedicated tool exists to set or read it explicitly beyond whatever `blueprint`/`diggable` set by default | Not independently verified this pass whether any tool ever sets a non-default priority; grep found no `priority=` write in the reviewed Lua files. |
| Burrows (`df.global.plotinfo.burrows.list`) | **Verified present and read**, 0 burrows on this fort as of 2026-09-23 | `memory/dfhack-environment.md:176-177,410-412`: correct path confirmed live, distinct from the nonexistent `world.burrows.all`. Not used by any current tool for confinement or labor-zone scoping; `Working.md:39` still lists "the burrow confinement ruling" as an open item. |
| Manager work order conditions and repeat (`manager_order.frequency`, condition items) | **Partially verified**: `orders.lua` already writes `frequency` (`fillin_defaults`, `OneTime` default, `df-overseer-orders.lua:18-19`); condition-item support (order only when a stock threshold is crossed) is not confirmed read or written by any tool | `df-overseer-orders.lua:1-55` for the frequency path; the "goal-tree walk-through item 8" register row treats native conditional/repeating orders as still to be live-tested ("Test: one conditional order during the next supervised unpause, cancelled after") — this is the register's own open item, not a new finding. |
| Workshop `building.profile` (per-workshop order limits, give/take links) | **Verified present, one field read live** | `docs/TRAPS.md:171`: "`building.profile.max_general_orders` read 5 on this install"; `memory/dfhack-environment.md:273-275`: give/take links "a real struct on both sides... the mirrored `building.profile.links` on a workshop." Not yet used by any tool to dedicate a workshop to a purpose, which decision 570 flags as a "(verify)" item — this audit confirms the underlying struct is real and already read once, which is a head start on that verification, not the verification itself (no live call to set it was found). |
| Stockpile give/take links and settings (`stockpiles` plugin) | **Verified present**, `docs/DFHACK-INVENTORY.md:573` (`yes`, no armok tag); `df-overseer-stockpile.lua` already reads links read-only | Read-only today (`stockpile.links`); no tool writes a link or a stockpile setting. A native lever the policy's "let the game execute" principle would favour over hand-managed hauling logic, and currently unused for writes. |
| `logistics` plugin ("Automatically mark and route items in monitored stockpiles") | **Verified present**, `docs/DFHACK-INVENTORY.md:465` (`yes`, tags `fort, auto, animals, items, stockpiles`, no armok) | Never referenced anywhere in this repo's Lua, `dfmcp/`, or `conductor/`. A candidate native replacement for any hand-rolled item-routing logic, should one ever be proposed. |
| `stockflow` ("Queue manager jobs based on free space in stockpiles") | **Verified unavailable on this install** | `docs/DFHACK-INVENTORY.md:572`: `doc only \| no` — ruled out as an option, which is exactly why the standing-goal design (goal-tree item 8) has to build its own thermostat logic around manager orders rather than relying on this plugin. |

The pattern: every mechanism the 2026-09-30 rulings point toward
(`prioritize`, `do_now`, burrows, order frequency, workshop profiles,
stockpile links) is confirmed present and armok-clean on this install by
the existing inventory docs; none has a tool wrapping it yet except order
frequency (partially) and stockpile links (read-only). That gap, not a
policy conflict, is the main actionable finding of this whole audit.

## 6. Ordered change list (smallest, most valuable first)

1. **Fix `agents/quartermaster/role.md:27-28`'s stale manager-order claim**
   to match the 2026-09-30 ruling (orders are now the default route, direct
   job the fallback). One-line text edit, no code change, applies an
   already-made ruling. *Not a user decision — just applying 570.*
2. **Wire `construction.build`'s material choice into a real buildingplan
   filter** instead of the current report-only `material_report`
   (`scripts/dfhack/TOOLS.yaml:2321-2325`; `Working.md:29`). Closes a live
   gap already caught, matches the materials ruling exactly, and is scoped
   (one command). *Not a user decision — the materials ruling already
   settled the target behaviour; this is the known remaining gap against
   it.*
3. **Live-test one conditional/repeating manager order** during the next
   supervised unpause (the register's own item-8/9 "next step," not new
   scope) to move the manager-order-as-standing-goal-engine ruling from
   "the user's observation" to independently confirmed, and to settle
   whether `frequency`/condition items behave as `orders.lua`'s header
   comment assumes. *User decision: needs a supervised unpause window,
   i.e. the user's go-ahead to run it.*
4. **Build a `prioritize`/`do_now`/designation-priority wrapper** (the
   actual gap this handoff was dispatched over, `decisions/DECISIONS.md`
   2026-09-30 last row) so the priority ruling has a real lever instead of
   only a role-charter description of one. Small, additive, no conflict
   with anything existing. *Not a user decision to build the read/write
   wrapper itself, but the "do now is only for emergencies" rule should be
   spelled out in `agents/overseer/role.md` once it exists, which is a
   charter edit the orchestrating session can make directly.*
5. **Update `ROADMAP.md`'s Now bucket** to fold in 2026-09-25 through
   2026-09-30 (reservations, project/observation records, the goal-tree
   design and red team, the lean-core decision, this audit) per `CLAUDE.md`'s
   own update trigger. Documentation only, out of this review's own scope
   (review only) but flagged here since it was found stale. *Not a user
   decision — routine maintenance the orchestrating session owns.*
6. **Build the `labor.quota` tool** the labor ruling calls for
   (`decisions/DECISIONS.md` 2026-09-30 "Labor" row), reading `enabled-counts`
   as its perception half (`df-overseer-labor.lua:49-58`, already built).
   *Not a user decision — the ruling already specifies the interface; this
   is implementation.*
7. **Try `building.profile` writes to dedicate a workshop to a purpose**
   (native order-limit/link fields, verified present, §5) as a live
   experiment before building any further workshop-claim bookkeeping in
   code, per decision 570's own "(verify)" flag. *User decision: this is a
   live-VM experiment, needs the same go-ahead any fort mutation does.*
8. **Decide whether to extend or retire `production/blocker.py` and
   `production/cover.py`'s target/threshold half** now that the freeze is
   confirmed correctly scoped (§2): the register already says "freeze," this
   audit found nothing to add or subtract from that scope, so no action is
   needed beyond not extending it. *Not a decision to make now — recorded
   as a non-finding so a future session doesn't have to re-derive it.*
9. **Resolve the six open item-binding decisions**
   (`research/2026-09-30-item-binding-design.md`) and the goal-tree design's
   remaining deferred pieces, when a real conductor run shows the need
   (per the lean-core decision's own stated trigger: "get a real team cycle
   running and let it pick the next piece"). *User decision, already framed
   that way in the register; not newly raised by this audit.*

Items 1, 2, 5 and 6 are small, scoped, and directly implied by rulings
already made — no new user decision needed to do them. Items 3 and 7 need
the user's go-ahead to touch the live fort. Items 4 needs a build (not a
decision). Items 8 and 9 are deliberately not-yet-decisions, recorded so
they aren't rediscovered from scratch.

## Not verified

- Whether `prioritize`, `do_now`, or `manager_order` condition items
  actually behave as their doc strings/header comments claim when called
  live — this pass had no VM access (review only), so every "verified
  present" claim in §5 is about the mechanism *existing and being armok-clean
  on this install*, never about its *live behaviour*.
- `conductor/cycle.py`, `runner.py`, `mcp_client.py`, `game_tick.py`,
  `service.py`, `status.py`, `briefing.py`, `archive.py`, `cursors.py`,
  `config.py`, `agents/conductor/role.md` and `tools.yaml`,
  `agents/consultant/tools.yaml`'s full `labor.*` grant, and
  `learning/ledger/`/`learning/predictions/` were not read line by line;
  classified from adjacent evidence (policy.yaml, register rows, sibling
  docstrings) rather than a direct code trace, and called out as such in
  §2/§3 rather than silently treated as fully audited.
- Whether any tool currently sets a non-default designation priority
  (1-7) anywhere; only a targeted grep was run, not a full trace of every
  `dig`/`build` command's blueprint-generation path.
- The full extent of `agents/consultant/tools.yaml`'s wildcard grants
  and whether any of them cross into scheduling/mutation territory
  (Consultant is documented as read-only throughout the register, but this
  pass did not enumerate every wildcard expansion).

