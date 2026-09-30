# Goal-tree design: red-team review

Date: 2026-09-30. Reviewer: independent researcher (Opus), not the author of
`research/2026-09-30-goal-tree-design.md` (commit `395175f`). Brief:
`handoffs/2026-09-30-goal-tree-red-team.md`. Review only: no code changes,
no live access, no VM touched.

Read in full: the design (2,369 lines), its brief
(`handoffs/2026-09-30-goal-tree-design.md`),
`research/2026-09-28-job-dependency-graph.md`, `dfqueue/schema.py`,
`dfqueue/store.py`, `dfmcp/queue_tools.py`, `dfmcp/roles.py`,
`scripts/dfhack/df-overseer-reservations.lua`, `docs/ARMOK-RULINGS.md`, both
eval READMEs, the 2026-09-24 to 2026-09-30 register rows. Read in the parts
that bear on the design: `docs/AGENT-ARCHITECTURE.md` (§1, §4 amend and
learning role, §7, §9, §10), `docs/PURPOSE.md` (purpose, commitments),
`agents/overseer/role.md`, `agents/conductor/tools.yaml`,
`conductor/cycle.py` (escalation path), `conductor/policy.yaml`,
`learning/live_signals.py`, the relevant `TOOLS.yaml` entries and
`df-overseer-building.lua`, `df-overseer-blueprint.lua`,
`df-overseer-workjob.lua`. Upstream, read at DFHack tag `53.16-r1`:
`library/modules/Persistence.cpp`, `library/Core.cpp` (save trigger),
`library/modules/EventManager.cpp`, `docs/plugins/logistics.rst`,
`docs/plugins/buildingplan.rst`; df-structures `df.job.xml` at `53.16-r1`;
DF wiki pages Workshop, Still, Barrel (raw wikitext, current).

Confidence labels, per claim: **[verified: source]** read in code (this repo
or upstream at a named ref); **[verified: primary doc]** read in the
project's own documentation or the DF wiki; **[repo record]** taken from
this repo's own eval or register text, not re-checked live; **[reasoned]**
my inference from verified pieces, not tested; **[unverified]** could not
confirm, repeated in §9.

Severity scale (the brief's): **BLOCKS** building as designed; **before Fn**
must be fixed before build step Fn of the design's §13.1; **watch**.

The author's own findings are not re-reported: premature `done`,
`queue.executed` not checking tool or `requires`, the charter-only WIP
limit, unpinned sites, diff.lua's weak completion events, unwired
`blocker.py`. Where I build on one, I say so.

---

## 0. The answer, up front

The design's shape is right: one recursive node, checks that declare how
and when they are observed, a runner that holds no DFHack tool of its own,
claims recomputed rather than tallied, priority by code. Most of the prior
art is correctly read and correctly scoped. But it is wrong in five places
that matter before anything is built, and each of them is a place where the
design reasons about DF or about this repo's live code from the design's own
model rather than from what the code and the game actually do:

1. **Its fix for unpinned sites does not pin sites.** `building.build`
   with `RES_ID` still ranks candidates near a landmark and keeps windows
   outside the reservation; a generic workshop pad template would allow no
   building kind inside it; and the slot-filling `blueprint.reserve` itself
   ranks at run time. Correction B, as written, moves the problem rather
   than solving it. (F-1, verified in source.)
2. **Its idempotency key makes every legitimate re-run a silent no-op.**
   A standing goal's reactivation and a post-amendment re-run reuse
   `<step_id>#<n>`, which the tool will find in the save and answer "already
   done" without acting. (F-2.)
3. **Nothing can carry a change to an accepted project.** Every escalation
   answer the design routes to the Overseer ("update, drop, add, or
   abandon") has no record kind: `queue.rule` rules once per proposal and a
   project is written once per ruling. (F-3, verified in source.)
4. **The claims model double-grants.** Items bind to a workshop job only
   when a dwarf starts it, so an issued job's demand disappears from the
   allocation pass until then, and the same logs are granted again next
   cycle; buildingplan attaches items to our own planned buildings on its
   own schedule. (F-4, verified in source and primary doc.)
5. **Accept-by-reference hands authority-bearing fields to the advisor.**
   Reservation overrides, economic material, workshop repeat, standing
   status and re-run budget, priority profile, cost, windows and retry
   budgets are all fields in a draft the Overseer can approve without
   reading. (F-5.)

Then, in rank order, the rest of the top ten: execution-time judgement the
Overseer applies today (staleness, first-build-of-a-kind go-ahead, dry run
first) silently disappears when execution moves to code (F-6); DF ids and
our own handles roll back and are reused, and the tick comparison that
detects a rollback races the game (F-7); standing goals thrash with one
threshold and their supply chain cannot re-run (F-8); in-order gating on
reactive checks breaks whenever a later sibling consumes what an earlier
one produced, which is exactly the booze chain (F-9); and the per-cycle
observation cost is one DFHack round trip per check plus one per queue
write, on a channel observed at 45 to 80 seconds a call (F-10).

| # | Finding | Severity | Blocks |
|---|---|---|---|
| F-1 | Reservation handles do not pin a site; the pad template cannot admit a workshop; the slot fill re-ranks | BLOCKS | F4 (and Correction B, the B representative of Option 3) |
| F-2 | Idempotency key collides with standing re-runs and post-amendment re-runs | before F4 | F4, and standing goals (K5) |
| F-3 | No record kind for changing an accepted project; abandonment unimplemented | BLOCKS | F4 escalation answers, F5 amendments after acceptance, F8 rung 4 |
| F-4 | Claims double-grant between issue and item binding; DF-native demand invisible | before F6 | F6 |
| F-5 | Accept-by-reference authorises advisor-chosen authority fields | before F5 | F5 (and F4, whose inputs F5 produces) |
| F-6 | Overseer execution-time checks are lost when the runner executes | before F4 | F4 |
| F-7 | Rollback and reload: ids and handles are reused; tick-based detection races; harness branches leak | before F3/F4 | F3, F4 |
| F-8 | Standing goals thrash; their one-off supply chain cannot re-run | before standing goals ship (F1 schema, K5 representative) | F1, F8 |
| F-9 | In-order progression on reactive checks breaks when a sibling consumes a predecessor's check | before F1 | F1, F2 |
| F-10 | Observation and write cost scale with checks times DFHack latency | before F2 | F2, F4 |
| F-11 | The workshop is a resource the claims model omits; labor share does not bound | before F6/F7 | F6, F7 |
| F-12 | Admission starves: no aging before admission, no survival bypass of the WIP cap | before F7 | F7 |
| F-13 | Held-target retry needs target-subset calls the tools do not offer | before F4 (groups A, B) | F4 |
| F-14 | Recorder bridge: cursor rollback, watch-registration gap, conductor grant for a persistent write | before F3 | F3 |
| F-15 | Runner escalation reuses the human-escalation kind; unanswered escalations have no policy | before F4 | F4, F8 |
| F-16 | Expectation windows in ticks versus cycle cadence and model wake length | before F8 | F8 |
| F-17 | Two issuers of consumption: the Overseer's direct path and DF's own work bypass claims and inheritance | watch (before F6) | F6 |
| F-18 | A retrospective cannot be built from what the design records | before F1 (cheapest now) | F1, F2 |
| F-19 | Taxonomy omissions and one forced grouping | watch | none |
| F-20 | Smaller schema and consistency gaps | before the step named in each | various |

Separately (§5), three settled decisions I argue need a change: the
standing-goal reach of decision 3 and 1 together, accept-by-reference under
decision 5, and the fair-share unit in decision 12.

---

## 1. The top ten findings

### F-1. Reservation handles do not pin a site (BLOCKS F4)

**Where:** §6.3 (slots filled by `blueprint.reserve`), §12.1 steps 2 and 4,
§13.3 Option 3 row B, §14.2 Correction B ("site arguments in a runnable
step must be a reservation handle").

**What the code does** [verified: source]:

- `building.build`'s signature is `build KIND [W H] [LEVEL] NEAR_LANDMARK
  [RANK] [RADIUS_TILES] [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]`
  (`TOOLS.yaml` line 777). `NEAR_LANDMARK` is required and `RES_ID` does not
  replace it. The worked example's `args: {KIND: Carpenters, RES_ID: "@s1"}`
  (§12.1) would not even parse.
- With `RES_ID`, the site is still chosen by ranking windows near the
  landmark: `ranked_sites` (`df-overseer-building.lua` 575-653) calls
  `reservations_mod.filter_reserved(candidates, res_id, ...)`, which keeps a
  candidate whenever `check_tiles(tiles, res_id)` returns nil
  (`df-overseer-reservations.lua` 461-468). `check_tiles` returns nil for
  tiles covered by **no** reservation. So every unreserved window stays in
  the ranking beside the ones inside `res_id`, and rank 1 is whichever is
  nearest the landmark. `RES_ID` is an entitlement ("you may build on this
  reservation"), not a pin ("build only here").
- Inside the reservation, `build_kind` then calls `check_tiles(rect_tiles,
  nil, res_id, k.token, override)` (line 1210), which refuses any tile in
  `res_id` unless the kind is in the reservation's `allowed_kinds` or an
  `OVERRIDE` reason is given. `allowed_kinds` is read from the template's
  own `#build` and `#zone` cells (`template_allowed_kinds`,
  `df-overseer-blueprint.lua` 422-443). The design's proposed
  `workshop-pad-3x3-v1` is "a cleared, smoothed 3x3 with its declared seams"
  (§6.3): no `#build` cell, so `allowed_kinds` is empty and a Carpenter's
  Workshop inside it is refused. Combined with the previous point, the
  ranking then lands the workshop on an unreserved window, typically next to
  the pad.
- `reserve_site` refuses a template with no `#dig` section ("nothing to
  reserve a footprint for", line 1496), and resolves "a NEW site ... the
  identical way a new dig phase would". A pad on ground that is already open
  floor, which is where workshops usually go, may not resolve at all
  [unverified: whether `resolve_new_site` accepts smoothing-only dig cells
  on open floor; not run].
- `blueprint.reserve`'s own signature is `reserve TEMPLATE PURPOSE SITE
  [DRY_RUN] [LEVEL] [RANK] [RADIUS_TILES]` (`TOOLS.yaml` 2465): it ranks at
  run time too. The design's slot fill job is `blueprint.reserve
  workshop-pad-3x3-v1 "carpentry" <landmark> RANK 1` (§12.1 step 2). The
  Architect justified rank 1 when it previewed; the runner reserves
  whatever is rank 1 when it runs. The 2026-09-30 deploy showed ranks shift
  as soon as anything is reserved ("after reserving it was skipped and the
  old rank 2 became rank 1", `evals/live/2026-09-30-reservations-deploy/`)
  [repo record]. Two slot fills accepted in one cycle, both "RANK 1 near
  Stockpile #1", reserve two different sites than the two previews showed.

**Failure scenario.** The Architect previews a pad beside the logs'
stockpile (rank 1) and files `slot_fill`. Before the runner reaches it, the
Overseer accepts a bedroom reservation near the same stockpile. The runner
reserves the old rank 2, 30 tiles away, as `res-7`. It then runs
`building.build Carpenters <landmark> ... RES_ID=res-7`: the pad refuses the
kind, so rank 1 is an unreserved window beside the landmark, and the
workshop is built there, on no reservation, in a place nobody reviewed. All
of this is "exactly the approved arguments".

**Fix.** Three pieces, all small, none optional:

1. A **pin mode** in every site-choosing tool: `SITE=res-N` (the way
   `blueprint apply SITE=res-1` already resolves its site from the holder,
   verified live 2026-09-30) that resolves the placement **from** the
   reservation's footprint and refuses if the kind does not fit it, instead
   of ranking. `RES_ID` stays as the entitlement argument for tools that
   already chose their tiles. A runnable step's site argument must be the
   pin form.
2. **Reserve at slot-fill acceptance, not later.** The Overseer runs the
   reservation itself when it accepts the `slot_fill`, so preview, judgement
   and reservation are one act; or the slot fill carries a dry-run
   fingerprint (footprint size, orientation, nearest landmark, distance)
   that the real reserve must match or refuse.
3. **A pad must admit its kind.** Either one pad template per workshop and
   furnace kind (35 kinds from `workshop_type` 26 and `furnace_type` 9: not
   "one data entry"), or `reserve` takes an `ALLOWED_KINDS` argument that
   the Overseer's ruling sets, which keeps one generic pad template.

**Also:** the recommended first allowlist (`workjob.queue`,
`building.build`, §14.1 decision 2) does not contain `blueprint.reserve`,
but the worked example's first runner action is exactly that
(`p3/reserve`, §12.1 step 4). One of the two must change.

### F-2. The idempotency key collides with every legitimate re-run (before F4)

**Where:** §7.4 ("`attempt_key = "<step_id>#<n>"`, n incremented only by the
healing ladder's re-issue rung"; the tool returns the stored result "without
acting" when it finds the key; keys "pruned after the project ends"), §5.2
standing goals, §12.1 steps 7 and 8.

**Failure scenarios** [reasoned from the design's own text]:

- **Standing reactivation.** `p5/j1` ran once as `p5/j1#1`; the key is in
  the save. A season later `g0` reads `not_met` and the runner re-runs `j1`
  "with its approved arguments". Same step, same n, same args: the tool
  finds `p5/j1#1` and returns the old job ids without queuing anything. The
  runner records success. The drink check never moves, the job is stuck by
  its window, rung 2 re-issues as `#2` (spending the re-issue budget on a
  run that should have been free), and the next reactivation collides with
  `#2`. Keys are pruned "after the project ends", and a standing project
  never ends.
- **Post-amendment re-run.** In §12.1 step 7 the Overseer answers `update
  j1 {COUNT: 2}` and "it re-runs". The key `p5/j1#1` exists with a different
  `args_hash` (if the amendment changed anything), so the Stripe-style check
  refuses; a refusal that is "not a known wait" escalates (§7.5), and the
  Overseer's answer produces the same refusal again. If the amendment left
  the arguments identical (the example's `COUNT: 2` to `COUNT: 2`), the
  tool returns "already done" instead.
- **Late binding.** `args_hash` is not specified as hashing resolved or
  unresolved arguments. Hashing unresolved templates (`@p9.site.landmark`)
  misses a resolution that changed between attempts; hashing resolved ones
  makes a legitimate re-resolution look like key reuse.

**Fix.** The key is `<project>/<step>@<generation>#<n>`, where the
**generation** increments on every standing reactivation and every accepted
revision of the project (F-3), and n counts re-issues within a generation.
Hash the **resolved** arguments, store them with the key, and have
`key-status` return them so recovery can tell "same call" from "different
call under a reused key". A change in resolution between two attempts of
one generation is a contradicted plan, not a key error.

### F-3. Nothing can carry a change to an accepted project (BLOCKS F4, F5, F8)

**Where:** §6.4 (amendments applied "in the same transaction as the
ruling"), §7.5 ("The Overseer answers with an ordinary ruling operation on
the project (`update`, `drop`, `add`, or abandon), recorded like an
amendment"), §10.2 rung 4, §12.1 steps 7 and 8.

**What the code does** [verified: source]: a `ruling` names a
`proposal_id`; `store.append` refuses a second final ruling on the same
proposal ("already has a final ruling", lines 452-462). A `project` is
written once per ruling and never again ("a ruling gets exactly one", lines
539-548). Records are append-only. `project_status`'s docstring says
project-level `abandoned` is "a decision, and this stream does not
implement writing one". There is no record kind that means "this accepted
project now has a different step list". The design's amendment path works
only at the moment of acceptance, which is the one moment escalations never
happen.

**Failure scenario.** A barrel job's re-issue budget is spent (§7.5's own
example). The runner escalates; the Overseer wakes, decides "change the
material", and has no tool to say so. It can reject nothing (the proposal is
closed), write no new project for the ruling, and `queue.executed` records
actions, not plan changes. The project sits `stuck` with a model wake spent
every cycle until the wake budget (§9.6) drops it.

**Fix.** A new sole-writer record kind, `project_revision {project_id,
revision, ops, reason}`, using the same closed operation vocabulary as
§6.4, validated by applying the ops to the current effective plan. The
**effective project** is the base record folded with its revisions, and
every reader must use it: `_find_project_for_ruling`, `_step_ids`,
`_seed_step_targets` (new steps need target rows), `project_status`,
`run_step`'s argument resolution, and the idempotency generation (F-2).
An attempt records the revision it ran under, and `run_step` refuses an
attempt whose revision is no longer current. `abandon` is one of the ops.
Decide who may write one: the Overseer only (the sole writer rule), with
the runner allowed only the mechanical ops the design already gives it
(releasing claims, un-forbidding its own holds), which are not revisions.

### F-4. The claims model double-grants (before F6)

**Where:** §8.2 ("**Available already excludes every item a job of anyone's
holds (`in_job`)**, so an issued job's items leave the pool by the game's
own flag"), §8.1 table, §12.1 step 5.

**What the game and the code do:**

- `workjob.queue` creates each job with `job_items` **filters**
  (`job.job_items.elements:insert`), then `assignToWorkshop`; it attaches
  no concrete item [verified: source, `df-overseer-workjob.lua` 964-1008].
- A workshop job gets its items only after a dwarf takes it: "When the
  dwarf is found ... The dwarf finds the nearest, most suitable base raw
  material ... gets that material and hauls it to the workshop"
  [verified: primary doc, DF wiki Workshop, "Operation"]. Until then no item
  is `in_job`. The design itself marks this binding time `[unverified]` in
  §8.4 but builds §8.2 on the opposite assumption.
- `buildingplan` is enabled on this fort [repo record, 2026-09-28 live
  read], and our own `building.build` placements go through it (the Chair of
  2026-09-23 "sits buildingplan-suspended", `TOOLS.yaml` line 783). It
  "will periodically scan for appropriate items and attach them to the
  planned building" [verified: primary doc, DFHack `buildingplan.rst` at
  `53.16-r1`], on its own schedule, whoever's claim the item was granted to.

**Failure scenario.** Cycle 1: `p4/j2` (2 barrels) is granted 2 of 3 logs
and issued; its jobs sit in the Carpenter's Workshop queue with no worker
because the one carpenter is hauling. Cycle 2: `p4/j2` is issued, so it is
no longer on the frontier and its demand is not granted; its logs are not
`in_job`; `free(WOOD)` reads 3 again, and the bed job of `project-0002`
(needing 2) is granted and issued. Three log demands of 4 now sit against 3
logs, and the named hold the design promises ("2 granted to project-0004")
never appears. Whichever job the carpenter reaches first takes the logs,
which is DF's order (F-11), not ours.

**Fix.** The allocation pass subtracts, in priority order, the demand of
every **issued job whose items are not yet bound** (its `job.items` empty,
or fewer than its filters need), until the job binds, completes or
vanishes. Add a **foreign demand** line: the unfilled filters of planned
buildings `buildingplan` is waiting on and of DF-native jobs already queued
(the pre-existing `MakeBarrel` jobs 2592 and 2593 of 2026-09-28 are live
examples outside any project [repo record]), reported by name so a hold can
say "1 log is wanted by an unowned planned Chair".

### F-5. Accept-by-reference hands authority-bearing fields to the advisor (before F5)

**Where:** §6.1 (draft validated "by the same `_validate_project_fields`
plus the new rules"), §6.4 (accept by reference is the cheap path), §7.2
(the ruling fixes the arguments), §7.3 ("an `OVERRIDE` ... is never in a
step's approved arguments unless the ruling put it there"), §11.2 (profile,
cost and lead time as priority inputs), §5.2 (`standing`, `rerun_budget`).

**The problem.** Under accept-by-reference, "the ruling put it there" and
"the advisor wrote it" are the same thing. Every field below is written by
the (cheaper, less trusted) advisor, validated only for shape, and becomes
authority the moment the Overseer accepts without reading:

| Field | What it authorises |
|---|---|
| `OVERRIDE` reason on a site tool | building a non-allowed kind inside someone's reservation (recorded, but done) |
| `MATERIAL_CHOICE: allow_economic` | the hematite workshop of 2026-09-25 again |
| `workjob.queue REPEAT` | an unbounded standing job at a workshop (REPEAT is untested live, `TOOLS.yaml` 1367); no check can ever read it "done" |
| `COUNT` up to the 10-job cap | filling a workshop queue (F-11) |
| `standing: true`, `rerun_budget` | recurring authority with no further ruling |
| `priority_profile: deadline`, `cost`, `expect.ticks` (lead time) | survival-tier placement and WSJF rank; lead time feeds `slack` directly (§11.2) |
| `retry.reissue_max`, `scarce` classes | thrash budget; which items get forbidden |

This is `docs/AGENT-ARCHITECTURE.md` principle 6 ("never self-reported into
a decision") in a new place: an advisor's own estimates become the priority
inputs, and its own flags become permissions.

**Fix.** (1) Server-side policy caps in `policy.yaml` for every numeric
field (`COUNT`, `rerun_budget`, `reissue_max`, window lengths), refused at
filing above the cap. (2) A closed list of **escalating fields** (`OVERRIDE`,
`allow_economic`, `REPEAT`, `standing`, `deadline` profile, `scarce`) that a
draft may not set at all; only the Overseer's amendment ops may add them,
so enabling one is always a recorded decision. (3) Priority inputs from
code where code can compute them (size from the blocker walk and
requirements, lead time from measured history once F-18 records it), with
the advisor's figure kept as a graded estimate, not an input.

### F-6. The Overseer's execution-time judgement is lost when the runner executes (before F4)

**Where:** §7.2 ("the Overseer remains the only role that decides"), §7.1
step 6, §14.1 decision 2 (runner as the only issuer of project steps).

**What is lost** [verified: source unless noted]:

- "**Never act on a stale proposal.** Preconditions are re-validated at
  execution time; if the world moved, the proposal is void"
  (`agents/overseer/role.md`). A proposal's `preconditions` are free text
  (`{landmark|area, state}`, `dfqueue/schema.py` 486-514); the runner cannot
  evaluate them, and `run_step`'s refusal list (§7.2) does not mention them.
  A standing goal's jobs, or a step whose predecessor took a season, run on
  preconditions nobody re-read.
- "`kind_previously_built` ... **ask the user before the real build of a
  kind that is not yet built for real**" (`TOOLS.yaml` building.build
  notes). This is a tool-documented gate the Overseer honoured on
  2026-09-25 (it stopped short and asked, `evals/live/2026-09-25-...`)
  [repo record]. It is prose, not a refusal, so the runner would pass it.
- The Overseer's practice of a dry run before the real call, which is how
  the 2026-09-25 cycle's container problem and the hematite workshop were
  caught [repo record]. `run_step` forces `DRY_RUN` false.
- The charter's escalation trigger "a tool returns something that
  contradicts a previous verified fact" has no code equivalent in §7.5's
  list.

**Fix.** Before F4, enumerate every execution-time rule in the Overseer's
charter and in `TOOLS.yaml` notes and give each a code form or a ruling-time
form: preconditions become typed guards or checks in the draft (a draft
with free-text preconditions is refused, or the preconditions are compiled
into a K2 guard at acceptance); every ruling carries a **maximum age** in
ticks and the world epoch (F-7) it was made in, and `run_step` refuses past
either; the first-build gate becomes a real tool refusal that the runner
maps to a named hold "needs the user's go-ahead" (and an escalation to the
human, not the Overseer); `run_step` runs the tool's dry run first and
refuses the real call if the dry run's resolved site, kind or material
differs from the one recorded at acceptance.

### F-7. Rollback and reload: identities are reused and detection races (before F3, F4)

**Where:** §3.3 (recorder ids "monotonic"), §7.4 (keys in the save), §8.6,
the reliance on the live `rollback_drift` (§7.1 step 2), §15 (silent on the
harness).

**Facts:**

- DFHack persistent data is written into `save/current/dfhack-*.dat` when a
  manual save, an autosave request or a save screen is detected, and loaded
  from the save folder on load [verified: source, `Persistence.cpp`
  `Internal::save`/`Internal::load`, `Core.cpp` 1543-1548 at `53.16-r1`].
  So persistent state rolls back with the world, as the design says. That
  includes `df-overseer-reservations_v1`'s `next_id` (`create`, lines
  215-235) and every other handle counter we keep there.
- DF's own id counters (`building_next_id`, `job_next_id`,
  `item_next_id`) are world globals that are saved and roll back too
  [reasoned: EventManager diffs exactly these globals, `EventManager.cpp`;
  not read in df-structures here].
- The queue does not roll back. `rollback_drift` detects a rollback only
  while `last_tick > current_tick` (`store.py` 847-873), and `last_tick` is
  the record's `cycle`, the tick stamped at write time (`queue_tools.py`
  918-936). The cycle quicksaves immediately before acting (§7.1 step 6),
  so the gap between save tick and recorded tick is small; once the
  reloaded fort runs past it (at 100 FPS, seconds), the rollback is
  undetectable by this test.

**Failure scenarios.**

- After a crash reload, the runner's recorded read-back says building 31 is
  our Carpenter's Workshop. In the replayed world, id 31 is the next
  building anyone places, perhaps a bed from another project. K4 "building
  31 complete" reads the bed. The recorder's watch list watches it.
- `res-7` was created after the save. In the replay, the next reservation
  created (a bedroom, by another project) is also `res-7`. The workshop
  step's pinned `RES_ID=res-7` now resolves to the bedroom; if its template
  allows the kind or the step carries an override, the tool builds there.
- The save-and-reload harness (`docs/ARMOK-RULINGS.md` 2026-09-25, allowed
  for the harness only) reloads deliberately. The 2026-09-28 design flagged
  that the harness must snapshot and restore the queue "if it does not,
  records from a discarded branch would leak into the live fort's history"
  (§4.4 there). This design does not pick that up, and it makes the leak
  active: the runner acts on the branch's `executed` records, attempts and
  claims. That breaks the ruling's "results from a reloaded branch never
  feed back into the live fort's decisions".

**Fix.** A **world epoch**: a random nonce written into persistent site data
at map load and re-written after each detected load; every tool result and
every queue record written by the runner carries it; the reconciler compares
it each cycle, and any change is a rollback regardless of ticks. Handles we
mint get a creation fingerprint (epoch plus creation tick) that `run_step`
checks on resolution; DF ids are always stored with an identity fingerprint
(building type and our handle, job type and workshop) and re-verified before
use. The harness must snapshot the queue database with the save and restore
both, or mark the branch's records with the branch epoch so the live runner
ignores them. Recovery after a detected rollback is itself unspecified in
the design (re-observe, then what?): state it, per step state.

### F-8. Standing goals thrash, and their supply chain cannot re-run (before standing goals ship)

**Where:** §5.2 (standing goals, `rerun_budget`), §12.1 steps 1 and 8,
§14.1 decision 3.

**Facts** [verified: primary doc, DF wiki Still and Barrel]: "Brewing
alcohol requires an available empty barrel or large pot"; "A single stack
of plants will be brewed for each task, and the resulting booze will be
placed into a single barrel". Every brew consumes one empty container. The
fort has 22 dwarves drinking [repo record].

**Failure scenario.** `g0` is `drink >= 40`, both the target and the
reactivation line. Drink reaches 40, `p5` goes dormant; within about a game
day consumption takes it to 39; `g0` reads `not_met`; `p5` reactivates and
spends one of its 4 per-year re-runs. The budget is gone in about four game
days, and the fifth reactivation wakes the Overseer (`standing_goal_rerun_
budget_spent`), every time, for the rest of the year. Worse: the re-run
needs an empty barrel, and `l1` links to `p4` (barrels), a finished one-off
whose root check ("2 free containers") went `not_met` the moment the
previous brews filled them. Under the design's recommended answer to
decision 3 (no re-run of a finished one-off), every reactivation wakes the
Quartermaster to re-draft barrels and the Overseer to re-approve them. The
standing goal, whose whole point was "captured once", costs two model wakes
per reactivation. And new barrels do not stay empty: the fort's own 15
barrels were all filled with plants by stockpile hauling [repo record,
2026-09-25/28], so "2 free containers" can be met at completion and gone by
the time brewing is issued, with no project holding them.

**Fix.** (1) **Two thresholds**, the inventory (s, S) policy: reactivate
below a reorder point s, fill to S; both from doctrine (the production
model's par and reserve floor, `docs/PRODUCTION-MODEL.md` §10). (2) A
standing goal's supply dependencies must themselves be standing (a
standing "keep k empty containers" project) or declared as **consumed
inputs** of the job (claimed at issue, not a gating link). Refuse at
acceptance a link from a standing project to a non-standing one. (3) Count
the re-run budget in units the goal cares about (drink produced per year),
not activations. (4) Empty containers a standing goal depends on are the
first real case for a hard hold (§8.4): forbid them on completion, or they
fill with plants.

### F-9. In-order progression on reactive checks breaks when a sibling consumes a predecessor's check (before F1)

**Where:** §5.2 ("Child k+1 becomes active when child k reads `met`";
goals are reactive, jobs are memory nodes), §12.1 step 7 ("The link reads
`met`").

**The flaw.** The design's in-order is a Sequence whose earlier children
are re-read every cycle. When child k+1 is the consumer of whatever made
child k `met`, issuing k+1 makes k `not_met`, which by the design's own rule
makes k+1 inactive again. The booze chain is exactly this: `g0 =
in_order[l1 (free barrels), j1 (brew)]`. The worked example says after two
brews "The link reads `met`"; by the wiki fact in F-8 the two brews filled
the two barrels, so `l1` reads `not_met`, `j1` leaves the frontier, and the
step 7 re-run the example describes cannot be issued. The worked example
contradicts its own semantics. [reasoned, on the verified brewing fact]

In behaviour-tree terms (the design's §2.2 source), this is the known
reason reactive sequences halt running children: a reactive Sequence
re-evaluates earlier conditions and aborts later ones. The design takes the
reactive half for goals and the memory half for jobs, and the combination
is not defined for a consumer after its precondition.

**Fix.** Latch in-order progression: once child k has read `met` and child
k+1 has been issued in this generation (F-2), k+1 stays active until its own
check settles, and k is re-read only when the parent goal reactivates. Keep
reactive reads for the goal's own check (skip the subtree when met) and for
invariants, declared as such. Let a job declare `consumes: <sibling>` so the
validator knows the drop is expected and does not escalate it as drift.

### F-10. Observation and write cost scale with checks times DFHack latency (before F2)

**Where:** §3.1 ("one bounded read per check per cycle"), §7.1 ("the
runner itself costs only MCP calls"), §7.2 (`step_attempt` then `executed`
per step), §5.4 ("Observations ... carry goal-check results").

**Facts** [verified: source]:

- `learning.live_signals.read` makes one DFHack tool call per signal
  (`overview.get`, `stocks.food-drink`, `stocks.availability`, ...).
- Every queue write stamps `cycle` by calling `overview.get` through DFHack
  first (`_stamp_cycle_snapshot`, `queue_tools.py` 918-936). `run_step`
  would write at least a `step_attempt` and an `executed` per step, plus
  observations: each one another DFHack round trip.
- DFHack serialises every call through one suspend window that opens once
  per simulation tick, with no fairness, and the project has measured 45
  to 80 seconds per call under load (`docs/AGENT-ARCHITECTURE.md` §7,
  "Resolved 2026-09-12") [repo record].
- The store assigns ids by `SELECT COUNT(*) ... WHERE kind = ?` with no
  index on `kind` (`store.py` 240-242) and finds projects and executions by
  unindexed `json_extract` scans (`_find_project_for_ruling`,
  `_arm_prediction_on_first_execution`). An observation per check per cycle
  makes every write scan a table that grows without bound.

**Failure scenario.** Five active projects with six checks each and three
ready steps: 30 signal reads, 6 step writes, 30 observation writes, each
stamped by an `overview.get`, about 90 DFHack round trips a cycle. At the
low end of the measured latency that is tens of minutes per reconcile, on
the same serialised channel the tripwire's clock calls and the Overseer's
tool calls use.

**Fix.** One batched, read-only reconcile tool (`reconcile.read` taking a
list of check specs, returning all values at one tick, one DFHack call);
one tick stamp per cycle passed to every write the runner makes that cycle;
observations written **on transition only** (a check's value or status
changed), with a periodic heartbeat; an index on `records(kind)` and on the
JSON fields the store looks up. Measure the per-cycle DFHack call count as
an F2 acceptance criterion.

---

## 2. Further findings

### F-11. The workshop is a resource the claims model omits (before F6, F7)

**Where:** §8.1 (three resources: materials, labor, ground), §9.3 (labor
share), §8.5 example, §4.2 row C (which lists "the workshop's queue" as a
claim, then §8 drops it).

**Facts:** "Tasks are carried out in the order they are listed, with the
current task being the topmost in the list"; "the workshop goes to the next
queued task"; "You can queue up to ten tasks in any workshop" [verified:
primary doc, DF wiki Workshop]. `workjob.queue` refuses a full queue
(`#bld.jobs >= 10`) and a COUNT that would overflow it, and COUNT creates N
separate DF jobs [verified: source, `TOOLS.yaml` 1383-1390,
`df-overseer-workjob.lua` 964-1008].

**Failure scenarios.**

- **Inversion in DF's own queue.** A comfort project issues `COUNT: 8` beds
  at the one Carpenter's Workshop. A cycle later the survival-tier barrel
  job is issued behind them. Our ready queue ranked barrels first; DF works
  the beds first, in list order, and our non-pre-emption rule (§9.1 step 5)
  forbids fixing it by cancelling. Priority inheritance raises what we
  issue next, not what DF runs next.
- **Refusal instead of a hold.** With 9 bed jobs queued, a `COUNT: 2`
  barrel job is refused by the tool. That refusal is not a guard, reservation
  or claim reason, so §7.5 escalates it to the Overseer.
- **The share formula does not bound.** `share(P, L) = max(1, floor(n_L *
  w_P / sum_w))` gives every project at least 1, so with one carpenter and
  three projects, three carpenter jobs are in flight. §8.5's example
  ("CARPENTER, 1 of 1 busy on project-0009", B held) is a global capacity
  rule, not this per-project formula; the two sections disagree.

**Fix.** Make the workshop a claimed resource: at most one of our jobs
queued per workshop ahead of anything of higher priority, a per-workshop cap
on our in-flight DF jobs (count DF jobs, not steps), and a "queue full" read
before issue that becomes a named hold. Use the vanilla priority arrow or
`do_now` only for survival tier (the design's own §9.4 rule). Pick one of
the two labor rules and delete the other.

### F-12. Admission starves, and survival waits behind the WIP cap (before F7)

**Where:** §9.1 step 1 (admit up to the limit "in priority order"), §9.5
(a project counts once it has an issued job, a granted claim or a hard
hold), §11.4 (aging credit for "every ready-but-unissued job").

**Failure scenarios** [reasoned]:

- Aging credits only jobs on the frontier, and the frontier is computed only
  for admitted projects. A low-priority project that is never admitted is
  never ready, never ages, and starves: exactly what aging was for.
- Admission is non-pre-emptive in practice: four long projects (a 60-tile
  smoothing, a dig, two furniture batches) with issued jobs keep their slots
  until they finish. A drink crisis becomes a survival-tier project and
  cannot be admitted. The tier is lexicographic only among admitted work.

**Fix.** Age at admission (the waiting-to-be-admitted queue gets the same
bounded credit), and let survival tier bypass the WIP limit (it is a limit
on half-finished discretionary work, the charter's own words: "Forts die of
ten half-finished projects").

### F-13. Held-target retry needs target-subset calls the tools do not offer (before F4, groups A and B)

**Where:** §7.3 ("retries it quietly every cycle by re-reading the guard
..., issuing the target when the guard passes"), §10.2 rung 2.

**Facts** [verified: source, `TOOLS.yaml`]: `construction.build ZONE_ID
KIND [DRY_RUN] [RES_ID] [OVERRIDE]`, `construction.mine-vein ZONE_ID ...`,
`building.build KIND ... NEAR_LANDMARK [RANK] ...`, and the several
`build W H [LEVEL] NEAR_LANDMARK ...` forms take no target handle list. A
retry of one held target is therefore a fresh call over the whole zone or a
fresh ranking, which re-derives the target set from the world: the
"`construction.build` infers 'was mined' from 'is open'" hazard the
2026-09-28 design named (its §3 item 4) and wanted closed by explicit
targets.

**Failure scenario.** Wall step s2 issued 4 of 5 walls, target 5 held by
`keeps_access`. The vein is mined out; the guard passes; the runner calls
`construction.build 13 Wall` again with a new attempt key. The tool walls
every open ring tile it finds, including the doorway a dwarf opened since,
and whatever of the first four are not yet constructions.

**Fix.** Before a group A or B tool goes on the runner allowlist, it must
accept a target handle set (the 2026-09-28 design's owed item) and refuse
anything outside it. Until then, a held target's release is an Overseer
action, not a quiet retry.

### F-14. The recorder bridge: rolled-back cursors, a registration gap, a missing grant (before F3)

**Where:** §3.3.

- **Cursor rollback.** The recorder's ids and ring live in persistent data
  and roll back with a reload (F-7); the conductor's cursor lives on VM 106
  and does not. After a rollback the recorder re-issues ids the conductor
  already consumed, for different events, and `recorder.since CURSOR` skips
  them. Fix: the cursor carries the world epoch; a mismatch resets it and
  forces the "poll every watched check" first-cycle rule the design already
  has for loads.
- **Registration gap.** The conductor pushes the watch list "each cycle",
  after `run_step` returns. Events between the tool's own mutation and the
  next watch push are counted but not kept. A short job, or a building
  destroyed early, falls in the gap. Fix: the runnable tool registers its
  own created ids with the recorder inside the same Lua call (the same
  helper that records the idempotency key), so the watch is atomic with the
  effect.
- **The grant.** `recorder.watch` writes persistent data, so its
  `TOOLS.yaml` effect is `mutate`, which `roles.py` rule 2 refuses on the
  conductor (not the sole writer) [verified: source]. The design adds
  several conductor-side DFHack commands (`recorder.watch`,
  `recorder.since`, `key-status`, the runner's `items.hold`) without saying
  how each is admitted. Each needs either a read classification that is
  honest or an entry in a named exception set like `SYSTEM_CLASS_TOOL_IDS`.
- **Checked and sound:** EventManager does reset its own item, job and
  building baselines on map unload and load [verified: source,
  `EventManager.cpp` `onStateChange`], so DFHack's side of a reload does not
  lose events; only our cursor does.

### F-15. Runner escalation reuses the human-escalation kind; unanswered escalations have no policy (before F4)

**Where:** §7.5 ("one `escalation`-kind queue record (the live kind)").

**Facts** [verified: source]: `escalation` is sole-writer only
(`schema.py` 1208-1214), so the conductor cannot write one; its meaning is
"the Overseer alerting the human", and `conductor/cycle.py` treats the
Overseer's `queue.escalate` call as "leave the fort paused" (lines 432-446,
617-632). Reusing the kind would either be refused or, if the role rule
were widened, conflate "wake the Overseer" with "stop and call a human".

**Gap.** Nothing says what happens when the Overseer does not answer: it
times out (the 2026-09-25 Overseer hit the 600 s cap), answers without an
op (F-3), or answers wrongly. The report re-fires every cycle and the wake
budget (§9.6) then queues it "with the fort paused", which halts every
other project for one stuck step.

**Fix.** A new `step_escalation` kind (conductor-written) with a state
(open, answered, expired); after N unanswered cycles or one timed-out wake,
the runner holds only that project (not the fort) and raises a real
`escalation` to the human through the Overseer's normal path.

### F-16. Expectation windows versus cycle cadence (before F8)

**Where:** §3.1 axis 2, §10.1, §10.3 (backoff `window * 2^n`).

**Facts** [verified: source, `conductor/policy.yaml`]: `base_fps: 100`,
`think_fps: 10`; a game day is 1200 ticks, so 12 s real at base speed; the
Overseer's wake cap is 1200 s, during which the fort runs at 10 FPS, about
12,000 ticks (10 game days). The runner runs only at the start of a cycle
(§7.1), never during model wakes.

**Failure scenario.** The worked example's barrel window is 2400 ticks
(24 s at base speed). Any cycle that includes an Overseer wake lets five
windows elapse unobserved; the next reconcile sees "past window, no
progress signal" for every job issued before the wake, even though the
recorder may hold the progress hints. Backoff intervals shorter than a
cycle collapse into "every cycle".

**Fix.** Validate that every window is at least k times the maximum
observation interval (a policy value), measure progress from recorder hints
with their own ticks rather than from the reconcile time, and run the
reconcile on its own timer so a long model wake does not blind it.

### F-17. Two issuers of consumption (watch; before F6 if the Overseer keeps direct tools)

**Where:** §7.2 ("keeps its direct tools for anything not in a project and
for emergencies"), §10.4 wait-for graph, §11.3 "blocks".

The Overseer's direct calls, the fort's own jobs (the two pre-existing
`MakeBarrel` jobs, `PlantSeeds`, hauling), buildingplan and a human on VNC
all consume materials, labor and workshop slots, and none of them appears in
the allocation pass or the wait-for graph. A hold whose real holder is one
of them names the wrong holder or none, and priority inheritance has no node
to boost. Decision 1 ("every piece of work is a project") already implies
the fix for the Overseer's own work: its direct actions become one-node
projects routed through the same allocator (issued by the Overseer if the
user prefers, but claimed). For DF-native and human work, report "foreign
demand" (F-4) as a named holder.

### F-18. A retrospective cannot be built from what the design records (before F1)

The brief's item 10. What a learning role would need, what the design
records, and what is missing:

| Needed | Recorded by the design? | Missing, and where it fits |
|---|---|---|
| Draft versus amendments | Yes: ruling keeps ops, project records `from_draft`, `amended` (§6.4) | Post-acceptance revisions (F-3) and who authored each op; planner quality counts ops but never their outcome |
| Outcome of the goal check afterwards | Partly: goal-check observations each cycle | A per-project **outcome record** at close: met / abandoned / failed, the tick met, and whether it was met **by our jobs' products or another route** (the design's "met another way" skip leaves no trace; the pre-existing `MakeBarrel` jobs would make p4 look successful for work it never did) |
| Claimed versus used | Promised (§8.3) but no record kind named: `claimed_exact` has no home | An `allocation` field on `step_attempt` plus a close-out `consumption` record from `job.items`, `onReactionComplete` inputs and `contained_items` |
| Each check's expected time versus actual | `expect` is declared; observations exist | The **transition ticks**: issued, first progress, met; with the declared window and its `source`. Transition-only observations (F-10) give exactly this cheaply |
| Holds, re-issues, escalations | Heal rungs "write an observation (kind heal)" (§10.2), but `observation` has no kind field and its statuses are `consistent/contradicted/not_observable` only (`schema.py` 222-225) | Hold opened/closed records with reason and holder; `heal` as a real record kind; escalation state (F-15) |
| Standing re-runs graded | No: a proposal's prediction arms only on the **first** `executed` for its ruling (`_arm_prediction_on_first_execution`, `store.py` 669-715) | Per-generation prediction rows (F-2's generation), or each re-run is never graded |
| Attribution to the drafting role | Proposal `role` and `type` (closed vocabulary) | Linked sub-projects drafted in one cycle by one role should share a **chain id** so the learning role can score the chain, not three isolated proposals |

Where it fits: node-level check outcomes are graded predictions in all but
name (a signal, an op, a value, a window), so they belong beside
`learning/predictions/` and the `predictions` table, keyed by project,
step and generation; chain-level lessons ("brewing needs barrels needs
carpentry") belong in the gotchas store or doctrine, derived, never written
by the drafting role (`docs/AGENT-ARCHITECTURE.md` §10, "Only 1 to 3 are
recorded; doctrine is derived"). Cheapest to add now, while the schema has
no live projects (§5.4's own argument).

### F-19. Taxonomy: omissions and one forced grouping (watch)

Checked [verified: source]: `job_type` has exactly 259 entries at
`53.16-r1` (df-structures `df.job.xml`), matching the design. The job
groups cover every job type. What the **action** groups miss is player
actions with no DF job at all beyond the ones in L:

- traffic designations (high, normal, low, restricted), which change
  pathing and are instant, like group L, but are tile designations like A;
- burrows (listed in §9.4 as a lever, in no group);
- kitchen allow-lists (which plants may be brewed or cooked, the Labor
  menu's Kitchen tab [verified: primary doc, wiki Still]), directly on the
  booze chain's path: a brew job fails if the plants are excluded;
- standing orders (auto-butcher, auto-collect webs, [verified: primary
  doc, wiki Workshop]);
- item designations beyond dump and forbid (melt, hide).

One forced grouping: group C puts the 11 `Improvement` jobs (encrust,
decorate) with manufacture, but an improvement targets **one specific
existing item**, a claim on an item id, not an item class. It needs the K8
item-handle pattern, not C's class netting. `FellTree` and `GatherPlants`
in A target plants, not tiles, which regrow and vanish independently of
designation state; A's "tile shape" completion check does not fit them.

### F-20. Smaller gaps (before the step named)

- **Observation schema** requires `step_id` naming a real step
  (`store.py` 550-570); goal checks and links are not steps. F1 must add a
  node id. (before F2)
- **`executed` by the runner for work outside any accepted step** (orphan
  un-forbids, §8.6; hard-hold forbids, §8.4) has no ruling or step to name;
  the design's own write-time rule would refuse it. (before F6 hard holds)
- **`run_step` registered as `mutates: False`** like every native tool
  would hide the conductor as a fort writer from registry-driven audits and
  role counts; register it as mutating with its own exception set. (F4)
- **`step_attempt` uniqueness**: two concurrent `run_step` calls with one
  key (a client timeout and retry while the first call is still waiting on
  DFHack's 45 to 80 s window) both insert a `started` row unless the store
  enforces a unique `(step, generation, n)`. The game side is safe (see
  §6, checked); the queue side needs the constraint. (F4)
- **Size per job**: WSJF's `size_remaining` subtracts "the estimates of
  done jobs", but only the proposal carries a `cost`. (F7)
- **Template drift**: a runnable step names a template by id; editing
  `bedroom-cell-v1.csv` in place changes what an old ruling authorises.
  Pin the template's content hash on the ruling. (F4)
- **Poll interval versus staleness**: validation should refuse a check
  whose `poll_every` exceeds its `stale_after_ticks`, or it is permanently
  `stale`. (F1)
- **`logistics claim`** can un-forbid items in monitored stockpiles
  [verified: primary doc, DFHack `logistics.rst`, `forbid|claim` option];
  whether any stockpile on this fort is registered is [unverified]. A hard
  hold must be re-asserted, not assumed, the same lesson the 2026-09-28
  design drew from `suspendmanager`. (hard holds)

---

## 3. The user's three examples, tested against the observation model

| | Building a still | Killing an enemy | Hauling hematite to a stockpile |
|---|---|---|---|
| Design's route | B job; K1 id read-back, K2 guards, K3 job has a worker, K4 stage poll (§12.2) | reflex, then a project with a K7 absence check (§12.3) | A dig, `ITEM_CREATED` captures the boulder id, K8 poll, unbounded (§12.4) |
| Can it be observed that way? | Yes: stage by poll is right; `BUILDING` fires at designation and destruction only [verified: source, EventManager diffs ids and existence] | Only by absence, and "absence of a visible hostile" is also exactly what an ambush looks like | Yes, if the watch is registered before the dig completes (usually true: a designation waits for a miner) |
| Where it breaks | (1) The read-back id is reused after a rollback (F-7). (2) The site is not pinned (F-1). (3) A still placed through buildingplan waits for a non-economic block or boulder nobody is making: that is `waiting` only if the reconciler reads buildingplan's planned state and names the missing item; otherwise it reads "no worker, past window" and is `stuck`, and rung 2's "re-issue only if the building record is gone" correctly does nothing, so it escalates. It should instead become a demand on the Quartermaster (a slot) | `met (by_absence, W)` releases any dependant that waits on it. The design keeps `unknown` for "it may be ambushing", but code cannot tell an ambush from a departure without hidden information, so in practice absence reads `met`. A hauling project through the entrance would resume | (1) The boulder id is reused after a rollback (F-7). (2) The ore boulder is only one of several claimants: a smelter job, a building's material choice, or `buildingplan` can take it before any haul; K8 then reads "consumed", which the design lists but does not say whether that is `met`, `not_met` or failed. (3) Mining ore yields a boulder only about a third of the time (§12.4, repo record), so "no boulder" is a valid outcome, not a stuck step |
| Unknown and stale handled? | Yes for the stage read | Yes in principle; see fix | Yes for an unresolvable id; not for "consumed by another job" |
| Fix | F-1, F-7; map buildingplan's planned-and-unfilled state to a named hold with the missing item class | A dependant must declare whether it accepts `by_absence`; safety-gated dependants (hauling through the entrance) should not, and stay held until a positive check or the Overseer releases | Declare K8's outcome set: in stockpile (met), consumed by a named job (a separate outcome, reported), destroyed or unresolvable (unknown), with the claimant named |

**The event bridge overall.** Sound in principle and well sourced: events
are hints, polls are truth, and the recorder stores hints where a rollback
takes them back too. The gaps are the cursor, the registration window and
the grant (F-14), plus cost (F-10). **Duplicates**: a re-issued job
produces a new job id, so a stale `JOB_COMPLETED` for the old id is
harmless if the recorder keys by job id and the runner by attempt
generation (F-2); state that explicitly.

---

## 4. The booze chain, walked adversarially

Following §12.1 step by step, on this fort's recorded state:

1. **Drafting.** The Quartermaster files three drafts. The third, the
   workshop, has no type in its vocabulary (`work_order`, `crop_plan`,
   `stock_target`, `schema.py` 258-269); filing it under `work_order`
   pollutes that type's hit rate with a construction the Quartermaster does
   not own, and the design notes the type problem only for the slot. Fix:
   the linked draft for another role's domain is a **stub with a slot**
   owned by that role, typed by that role when filled. (F-18 chain id.)
2. **The slot fill.** Re-ranks at run time, the pad admits no workshop, and
   `building.build` with `RES_ID` lands outside the pad (F-1).
3. **Acceptance.** Draft 0013's `WORKSHOP_LANDMARK_NAME:
   "@proposal-0014.site.landmark"` is a cross-project reference, which the
   design's own filing rule 5 forbids ("only an earlier node's declared
   output ... in the same plan"). And a workshop's landmark name is its DF
   display name, "Carpenter's Workshop": landmarks resolve by the **first**
   exact name match (`df-overseer-landmarks.lua` 299-319) [verified:
   source], so a second Carpenter's Workshop makes the reference ambiguous,
   and dfmcp refuses any argument containing an apostrophe, which already
   blocks three of this fort's landmarks including this one
   (`evals/live/2026-09-30-reservations-deploy/`, `TOOLS.yaml` 1403-1410)
   [repo record]. The barrel step cannot address its workshop through MCP
   today. Fix: workshop jobs take a building handle (minted at build time,
   fingerprinted per F-7), not a display name.
4. **The runner's first cycle.** Needs `blueprint.reserve` on the allowlist,
   which the recommendation excludes (F-1). The quicksave before acting is
   fire-and-forget (`agents/conductor/tools.yaml`, `fort.quicksave` note) and
   can silently no-op (`research/2026-09-11-quicksave-silent-noop.md`, cited
   there) [repo record]; the idempotency design survives that (key and
   effect are saved together whenever a save happens), but "save before any
   action" is best effort, which the design should say.
5. **The contention hold.** Never appears: the barrel job's demand leaves
   the pass once issued and before a carpenter binds the logs, so the bed
   job is granted the same logs (F-4). In DF, whichever job sits higher in
   the one workshop's queue runs first (F-11).
6. **Inheritance.** Correct as far as it goes; it changes what we issue,
   not what DF runs next in the workshop (F-11), and it cannot boost the
   pre-existing unowned barrel jobs 2592 and 2593 (F-17), which may satisfy
   `p4`'s root check without any project job running. `p4` then reads `met`
   and its own jobs, possibly already issued, keep running: the design
   skips a met subtree but never cancels issued work (correctly), so the
   fort makes barrels nobody now needs, and the claimed-versus-used record
   credits `p4` with success (F-18).
7. **Brewing.** Each brew fills one of the two new barrels; `l1` reads
   `not_met` as soon as the brew jobs bind them, the opposite of the
   example's "The link reads `met`" (F-9). The amendment `update j1
   {COUNT: 2}` then either collides with the old idempotency key or is
   refused as a key reuse (F-2), and there is no record to carry it (F-3).
8. **Dormancy and wake.** One threshold at 40 reactivates within a game day;
   the barrels are full; `p4` is a finished one-off; the Quartermaster and
   the Overseer are woken for every reactivation (F-8). Meanwhile any new
   barrel is filled with plants by stockpile hauling before brewing can take
   it, the fort's actual history.

**What survives the walk:** the blocker walk as the draft skeleton (the
single most valuable idea in the design, and cheap), the three-project
split, named holds as the reporting surface, the survival tier's refusal to
treat drink as survival while the Well works, and the rule that a met goal
skips its subtree without cancelling issued work.

---

## 5. Settled decisions I think need a change (argued separately)

These are the user's decisions, not the design's. Each is argued from a
finding above.

1. **Decisions 1 and 3 together: a standing goal's links.** Decision 1 makes
   standing goals projects; decision 3 makes sub-projects separate and
   shareable. Together, and with the design's recommended "no re-run of a
   finished one-off" (its decision 3 for the user), a standing goal whose
   supply is consumed by use (barrels, fuel, seeds) re-asks for its supply
   chain on every reactivation (F-8). Proposed correction: **a standing
   project may link only to standing projects or declare consumed inputs**;
   one-off sub-projects are for things that stay built (a workshop).
2. **Decision 5: accept by reference.** Keep the cheap path, but it should
   not reach authority-bearing fields (F-5). Proposed correction: accept by
   reference covers the plan's structure and ordinary arguments; a closed
   list of escalating fields can only enter through the Overseer's own
   amendment ops.
3. **Decision 12: the fair-share unit.** "A fair share of labor per
   project" is the wrong unit on this fort. The binding resource for group C
   is the **workshop** (one job at a time, a FIFO queue of ten), not the
   labor (F-11): two carpenters and one Carpenter's Workshop serialise on
   the workshop. Proposed correction: share per workshop for group C, per
   labor for groups A and B (designations and constructions, where the
   worker, not a building, is the bottleneck).

I found no reason to argue with decisions 2 (recursive rule, no vague
nodes, with the design's Correction A), 4, 6 (with F-6's additions), 7, 8
(with F-4's addition and the design's own labor-cap rewording), 9, 10, 11
or 13.

---

## 6. Checked and found sound

Stated so silence is not read as approval. Each was checked against the
source named, not taken from the design's text.

- **Keys and effects roll back together.** DFHack writes persistent data to
  `save/current/dfhack-*.dat` exactly when DF saves (manual save, autosave
  request, save screen) and loads it from the save folder [verified:
  source, `Persistence.cpp`, `Core.cpp` 1543-1548 at `53.16-r1`]. The
  design's §7.4 argument (a key found in the save means the effect is in
  the save; a key missing means re-issue is correct) holds. Its weakness
  is identity reuse after re-issue (F-7), not the key mechanism.
- **The game-side key check is atomic with the effect**, provided the
  helper records the key inside the same command: DFHack runs each command
  under the core suspend lock, and concurrent callers serialise on it
  (`docs/AGENT-ARCHITECTURE.md` §7, from the 2026-09-12 source read)
  [repo record, not re-read here]. The queue side needs a uniqueness
  constraint (F-20).
- **"Events are polls" and its consequences** [verified: source,
  `EventManager.cpp`]: item creation diffs `item_next_id` and skips foreign,
  trader, owned and web items; building events diff existence; baselines
  reset on map load. The design's reading is accurate.
- **The two-argument `run_step` with server-side resolution** is the right
  shape and matches the existing native-tool pattern
  (`_reject_unknown_arguments`, closed argument sets). The internal call
  bypassing `Roster.check` has a real precedent (`_stamp_cycle_snapshot`).
- **Materials cannot deadlock under all-or-nothing grants recomputed each
  cycle** (no hold-and-wait on our side). DF itself cancels a workshop job
  that cannot find its items, so DF-side hold-and-wait is short-lived
  [reasoned]. The design is right to defer deadlock detection.
- **Never pre-empting issued work** is right for DF (hauled progress is
  real), and the design says so plainly.
- **Sum-not-max inheritance with a cap, and bounded, lexicographic aging**
  are coherent and honestly labelled as tuning constants. The problems are
  where they apply (F-11, F-12), not the rules.
- **Tri-state checks, hidden information and absence** are handled in line
  with the no-armok rule; K7 is honestly weaker than a positive read (see
  §3 for what a dependant should do with it).
- **Extend the `project` schema rather than layer on top**, now, while the
  live queue has no projects: sound, and the cheapest moment, as the
  design says. It is also the cheapest moment for F-3, F-9 and F-18.
- **The taxonomy's count and coverage of job types**: 259 entries at
  `53.16-r1` [verified: source]; every one lands in a group or is an empty
  slot. The gaps are in actions without jobs (F-19).
- **The author's own findings** that this review builds on:
  `step_prerequisites_satisfied` has no caller outside tests [verified:
  source, grep]; `_seed_step_targets` skips `from_step` steps [verified:
  source]. Both as described.
- **The recorder never pausing** (the ledger's rule copied) and only
  tripwire classes taking the urgent path: sound.
- **Escalation report shape**: short, fixed-form, coordinate-free: sound,
  once it has its own kind (F-15).

---

## 7. Coverage against the brief's eleven areas

| Area | Findings |
|---|---|
| 1. Authority and safety | F-1 (run-time site resolution), F-2 (key reuse), F-5 (draft smuggling), F-6 (stale ruling, lost gates), F-7 (handle reuse after rollback), F-13 (re-derived targets), F-20 (template drift) |
| 2. Liveness | F-8 (standing thrash), F-9 (in-order consumer), F-11 (workshop inversion), F-12 (admission starvation), F-15 (unanswered escalation). Link cycles are refused at acceptance: sound, but see F-3 (revisions must re-run the check) |
| 3. Truth and drift | F-4 (unbound items, buildingplan), F-7, F-17 (foreign work), F-20 (`logistics claim`), §3 (consumed boulder) |
| 4. Failure and recovery | F-7 (rollback detection, harness), F-14 (cursor), F-15, F-2; crash mid-step and server restart are handled by the key design (§6) |
| 5. Cost and scale | F-10; drafts' token estimates are plausible but unmeasured (the design says so) |
| 6. Gaps | F-3, F-14 (grants), F-18, F-20 |
| 7. Observability and timing | §3, F-14, F-16 |
| 8. Stuck, healing, scheduling | F-2 (re-issue burns budget), F-11, F-12, F-13, F-16; release-then-reclaim cooldown is sound |
| 9. Taxonomy | F-19 |
| 10. Learning | F-18 |
| 11. Worked example | §4 |

---

## 8. What to change in the build order

The design's F0 to F8 order is sound in shape. Insertions:

- **Before F1:** decide F-9 (latched in-order), F-8's two-threshold and
  standing-link rule, the revision record (F-3), node ids on observations
  (F-20), and the learning fields (F-18). All are schema questions and all
  are cheapest now.
- **Before F2:** the batched reconcile read and transition-only
  observations (F-10); the world epoch (F-7).
- **Before F3:** the recorder cursor epoch, atomic watch registration and
  the conductor grant (F-14).
- **Before F4:** the pin mode and pad admission (F-1), the generation key
  (F-2), the execution-time gates (F-6), `step_escalation` (F-15),
  target-subset calls for any A or B tool on the allowlist (F-13), a
  building handle for workshop jobs (§4 step 3), and a consistent first
  allowlist (F-1).
- **Before F5:** policy caps and the escalating-field list (F-5).
- **Before F6:** unbound-demand and foreign-demand accounting (F-4), the
  workshop as a resource (F-11).
- **Before F7:** aging at admission and the survival bypass (F-12).
- **Before F8:** windows against cadence (F-16).

For the user's slice-or-groups choice (§13.3 of the design): Option 3's
row B (`building.build Carpenters on a reserved pad`) cannot run as
designed until F-1 is fixed, and the fort already has a Carpenter's
Workshop (built 2026-09-25) [repo record], so a second one is a test, not a
need. Row C (`MakeBarrel`) already has two unowned live jobs in the way
(F-17). Row K5 (the standing drink goal) exercises F-2, F-8 and F-9 at
once, which makes it the most informative representative and the one most
likely to fail first.

---

## 9. Not verified

- **Whether `resolve_new_site` can reserve a smoothing-only pad on open
  floor** (F-1): read, not run.
- **DF's id counters rolling back and being reused** (F-7): reasoned from
  EventManager diffing those globals and from DF saving world state; not
  read in df-structures here, not observed live.
- **Whether `logistics` has any stockpile registered on this fort**
  (F-20): not read live (review only).
- **DFHack command atomicity under the suspend lock** (§6): taken from the
  repo's 2026-09-12 source read, not re-read at `53.16-r1` here.
- **That DF works workshop tasks strictly in list order when the top task
  cannot start** (F-11): the wiki says tasks "are carried out in the order
  they are listed" and a paused task "is simply skipped over"; what DF does
  with a top task whose materials are missing (skip or block) is not
  stated there.
- **The quicksave silent no-op** (§4 step 4): cited from the repo's own
  research, not re-read.
- **Kitchen allow-lists affecting brew jobs** (F-19): from the wiki Still
  page's sentence, not tested.
- **Every scenario marked [reasoned]** is an inference from verified parts;
  none was run. Nothing here was prototyped.
- **No harness refusals** occurred during this review. Downloads used
  PowerShell `Invoke-WebRequest` into the scratchpad; git commands were run
  plainly.

---

## 10. Sources

Read in source (high confidence):

- This repo at `17c1a5f`: `dfqueue/schema.py`, `dfqueue/store.py`,
  `dfmcp/queue_tools.py`, `dfmcp/roles.py`,
  `scripts/dfhack/df-overseer-reservations.lua`,
  `df-overseer-building.lua` (575-669, 1155-1264),
  `df-overseer-blueprint.lua` (405-443, 1467-1530),
  `df-overseer-workjob.lua` (964-1008), `df-overseer-landmarks.lua`
  (14-53, 299-320), `scripts/dfhack/TOOLS.yaml` (777-808, 1362-1411,
  2465-2504, the `build`/`mine-vein` signatures), `learning/live_signals.py`
  (`read`), `conductor/cycle.py` (escalation handling),
  `conductor/policy.yaml`, `agents/conductor/tools.yaml`,
  `agents/overseer/role.md`.
- DFHack at tag `53.16-r1`, fetched from
  `raw.githubusercontent.com/DFHack/dfhack/53.16-r1/`:
  `library/modules/Persistence.cpp`, `library/Core.cpp`,
  `library/modules/EventManager.cpp`, `docs/plugins/logistics.rst`,
  `docs/plugins/buildingplan.rst`.
- df-structures at `53.16-r1`: `df.job.xml` (`job_type`, 259 entries).

Primary documentation (high confidence for quoted wording):

- DF wiki, raw wikitext fetched 2026-09-30: Workshop ("Operation", tasks
  in list order, ten-task cap), Still (empty container per brew, 5 units
  per plant, kitchen allow-list), Barrel (one log per wooden barrel, one
  stack of alcohol per barrel).

Repo records (taken as recorded, not re-checked live):

- `evals/live/2026-09-25-first-real-conductor-cycle/README.md`,
  `evals/live/2026-09-30-reservations-deploy/README.md`,
  `decisions/DECISIONS.md` 2026-09-24 to 2026-09-30,
  `docs/AGENT-ARCHITECTURE.md` §7 (DFHack call serialisation and latency),
  `research/2026-09-28-job-dependency-graph.md` §4.4 (harness snapshot
  warning).
