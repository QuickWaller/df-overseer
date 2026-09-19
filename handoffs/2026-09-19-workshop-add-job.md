# Handoff: queue a one-off job at a workshop, the way a player clicks it

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy, no live
run.** User-directed.

Read `CLAUDE.md`, then `handoffs/2026-09-19-well-and-harvest.md` (its section
on the direct-job route and the draft Lua it reproduces), then
`handoffs/2026-09-19-well-finish.md`'s write-up, then
`scripts/dfhack/df-overseer-workshop.lua` and `df-overseer-orders.lua`, then
this.

## Why

Manager work orders stall on this fort: with no Manager appointed, they are
never validated, and even hand-validated they never became jobs in 42 game
days. **The user pointed out the honest alternative: a player can also queue a
one-off job directly at a workshop by clicking it** (the workshop's own "add
job" menu), which needs no Manager at all. That is a legitimate player action,
unlike setting an order's `validated` flag by hand, which was a cheat and is
not to be repeated.

A previous stream drafted exactly this, **sourced verbatim from this install's
own `hack/scripts/idle-crafting.lua` and `hack/lua/dfhack/workshops.lua`**
(`dfhack.job.createLinked` plus `assignToWorkshop`), and was refused by the
permission classifier when it tried to *run* it ad hoc. This stream turns it
into a **proper, reviewed, tested tool**; running it live is a separate,
user-approved step.

## Deliverable

A new command (a new file, `scripts/dfhack/df-overseer-workjob.lua`, or a new
subcommand on `df-overseer-workshop.lua` if that file's structure clearly
wants it; say which and why) that queues **one** job at **one** named
workshop, for at least:

- `ConstructBlocks` at a mason's workshop,
- `ConstructMechanisms` at a mechanic's workshop,
- `BREW_DRINK_FROM_PLANT` at a still (a reaction job, so its `job_item`
  spec comes from the reaction's own reagents; read how DFHack's own scripts
  build reaction jobs rather than guessing),
- a cooking or processing job only if cheap.

Addressed by landmark name, as every other tool is. **No coordinates in any
input or output.**

## Rules that matter here

- **A `DRY_RUN` default of true**, as `orders.create` and `harvest gather` do:
  report what would be queued and whether the workshop exists, is built, and
  has a free job slot, without mutating.
- **Refuse, never guess**: an unknown workshop, a workshop still under
  construction, a full job queue, or an unknown job name is an explicit error.
- **Follow DFHack's own code path**, not a hand-built job struct, and cite the
  file and line you followed, as `df-overseer-orders.lua`'s header does.
- **Never set `validated` on anything** and never touch manager orders.
- Register it in `scripts/dfhack/TOOLS.yaml` as a **mutating** tool, and grant
  it deliberately per role in `agents/*/tools.yaml`, with reasons. Add tests
  alongside the existing registry and role tests.
- **Write as you go**: commit on your branch after each milestone and append
  to this file's write-up each time.
- Never write an IP address, hostname or port into any committed file. Do not
  write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. No em dashes in prose.

## Touched surfaces

The new tool file (or the one subcommand), `scripts/dfhack/TOOLS.yaml`,
`agents/*/tools.yaml`, `dfmcp/tests/`, `tests/`, and this handoff doc.

## Done means

The command exists with a dry-run default, refuses every bad input
explicitly, follows a cited DFHack code path, is registered as mutating and
granted with reasons, the full suite passes (report before and after), and the
write-up states exactly what the first live run must check. **It is not run
live by this stream.**

## Write-up (2026-09-19, offline build stream, no VM touched)

### 0. Reading order followed

Read `CLAUDE.md`, `handoffs/2026-09-19-well-and-harvest.md` (especially
section 6, "Blocked: direct workshop job creation refused by the permission
classifier", which cites `idle-crafting.lua`'s `makeRockCraft` and
`library/lua/dfhack/workshops.lua`'s Masons/Mechanics job definitions from
this install's own source), `handoffs/2026-09-19-well-finish.md` (sections
2-4, which independently ran the fort ~50,851 ticks with the three orders
`validated=true` and never saw one become a job), then
`scripts/dfhack/df-overseer-workshop.lua` and `df-overseer-orders.lua`, then
this handoff. No local vendored copy of DFHack's own source exists in this
repo, so the DFHack code path itself was re-confirmed against the public
`DFHack/dfhack` and `DFHack/scripts` GitHub repositories (both public,
canonical upstream) via `WebFetch`/`WebSearch` this session, rather than
trusted from the prior stream's prose alone -- see section 2 below for what
that re-check found.

### 1. New file, not a df-overseer-workshop.lua subcommand

Built `scripts/dfhack/df-overseer-workjob.lua`, a new file, not a
subcommand on `df-overseer-workshop.lua`. Reason, stated in the new file's
own header too: `df-overseer-workshop.lua`'s own header is explicit that its
job is finding and building workshop STRUCTURES, sharing
`df-overseer-openarea.lua`'s site-selection machinery with
farm/zone/trees/well. Queuing a job at an ALREADY-BUILT workshop has no
site-finding step at all -- the workshop is addressed by landmark name, the
same way `df-overseer-landmarks.lua`'s own building enumeration already
names it. Folding this into `workshop.lua` would blur two concerns
(siting/building vs. queuing/manufacturing) that `df-overseer-orders.lua`
already keeps separate from `df-overseer-workshop.lua` today. Matches the
separation the handoff itself flagged as the more likely shape.

### 2. The DFHack code path, re-confirmed against public source, cited by file

Fetched `idle-crafting.lua` from `github.com/DFHack/scripts` (raw, master
branch) and `library/lua/dfhack/workshops.lua` from `github.com/DFHack/dfhack`
(raw, master branch) directly this session, rather than trusting the prior
stream's prose alone. Confirmed exactly what that stream reported:

- `idle-crafting.lua`'s `makeRockCraft` function:
  `local job = dfhack.job.createLinked()`, then a `df.job_item:new()` with
  `item_type = df.item_type.BOULDER`, `mat_type = 0`, `quantity = 1`,
  `vector_id = df.job_item_vector_id.BOULDER`, `flags2.non_economic = true`,
  `flags3.hard = true`, inserted via
  `job.job_items.elements:insert('#', jitem)`, then
  `dfhack.job.assignToWorkshop(job, workshop)`.
- `library/lua/dfhack/workshops.lua`'s own Masons "construct blocks" and
  Mechanics "construct mechanisms" job definitions: an identical job_item
  (`item_type=BOULDER, vector_id=BOULDER, mat_type=0, mat_index=-1,
  quantity=1, flags3={hard=true}`) for both.
- `dfhack.job.assignToWorkshop` is registered in `library/LuaApi.cpp`'s
  `dfhack_job_module` table (`github.com/DFHack/dfhack`) and is documented
  (DFHack's own Lua API reference, `dfhack.job` section) to do nothing and
  return `false` once a workshop already has 10 jobs queued -- the
  `MAX_WORKSHOP_JOBS` refusal in the new tool checks this itself, before
  attempting the call, rather than relying on a silent no-op.

`df-overseer-workjob.lua` reproduces this sequence exactly for `blocks`
(ConstructBlocks @ Masons) and `mechanisms` (ConstructMechanisms @
Mechanics).

**BREW_DRINK_FROM_PLANT is different, and this is stated honestly rather
than papered over**: no DFHack script this session could find builds a
reaction job's `job_items` GENERICALLY from a reaction's own reagents.
`idle-crafting.lua` hand-writes exactly one known reagent (BOULDER); fetched
`gui/workshop-job.lua` (`github.com/DFHack/scripts`) and confirmed it only
READS an already-populated job's existing `job_items`/`contains` back
against `df.reaction.find(iobj.reaction_id).reagents[ri]` -- it never
constructs a new job_item from a reagent. The vanilla "add job" screen does
this construction inside the DF engine's own C++ binary, not in any DFHack
Lua script found this session. So `reagent_job_item()` in the new file is
this project's OWN code, not a reused DFHack path -- the file's header says
so explicitly. It does the one thing that is a direct field copy, not a
guess: `item_type`/`item_subtype`/`mat_type`/`mat_index`/`quantity` read
straight off each live `df.reaction_reagent` entry in
`df.global.world.raws.reactions.reactions[i].reagents` (the same fields the
raw `[REAGENT:name:quantity:item_type:item_subtype:mat_type:mat_index]`
token populates, per DF's own documented modding format). It REFUSES,
rather than guesses, on any reagent whose own `item_type` is a
wildcard/tag-matched `NONE` -- brewing's own vanilla second reagent (an
empty barrel or bag, matched by a `[CONTAINER]`-style tag rather than a
concrete item type on the community-documented wiki token) is the suspected
shape of exactly this case, **unconfirmed against this install's own live
raws**, since this stream never touched the VM. The practical, honestly
stated consequence: `queue brew_drink <still> true` may well refuse with a
named "cannot build job_items for reaction BREW_DRINK_FROM_PLANT: reagent
N has no concrete item_type" message on first live use, and that refusal is
this tool doing exactly what it was asked to do (refuse rather than guess),
not a defect to route around.

A cooking/processing job was considered ("only if cheap") and left out,
reasoned through in the file's own header: a meal job's ingredient count
and quality tier are chosen at queue time in the real UI (1-5 ingredients
depending on meal quality), not fixed by the job type or derivable from one
reaction's reagents the way brewing is -- building that correctly would
mean guessing a meal-quality-to-ingredient-count mapping with no live
install to check it against. Not cheap; left out rather than guessed.

### 3. Refusals built, all explicit, none silent

`queue_job(JOB, WORKSHOP_LANDMARK_NAME, DRY_RUN)` refuses with a named
reason, never a guess or a silent success, for:

- an unknown JOB name (lists the known ones, matching `orders.create`'s own
  error shape);
- an unknown workshop landmark name (no building with that
  `dfhack.buildings.getName()` exists);
- a landmark that resolves to a building, but not a Workshop at all;
- a workshop of the wrong kind (e.g. `queue blocks` against the Still);
- a workshop still under construction (`bld.flags.exists` false -- the same
  field `df-overseer-farm.lua`'s own construction-gate already uses,
  confirmed live in a prior session, reused here rather than re-derived);
- a full job queue (`#bld.jobs >= 10`, DFHack's own documented cap on
  `assignToWorkshop`, checked before attempting the call);
- (reaction jobs only) any reagent this tool cannot resolve to a concrete
  item_type, named by reagent index and reaction code.

`DRY_RUN` defaults to `true` (same contract as `orders.create`/
`build_workshop`). Only an explicit `false` calls
`dfhack.job.createLinked`/`assignToWorkshop` for real -- **never exercised
this stream; no VM, no SSH, no deploy, per the handoff's own scope.** If the
real mutation path fails after `createLinked` (bad job_item attach, or
`assignToWorkshop` returning false), the code calls
`dfhack.job.removeJob(job)` to avoid leaving an orphaned, unassigned job in
`world.jobs.list` -- mirrored on `df-overseer-orders.lua`'s own
`cancel_order` cleanup convention, itself UNTESTED live there too.

`status.validated` is never touched, and
`df.global.world.manager_orders.all` is never read or written anywhere in
this file -- a wholly separate route from `df-overseer-orders.lua`'s queue,
confirmed by re-reading the finished file rather than assumed.

### 4. Registered in TOOLS.yaml, granted per role with reasons

`scripts/dfhack/TOOLS.yaml` gained a `df-overseer-workjob.lua` block:
`list` (read, `list_jobs`) and `queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN]`
(mutate, `queue_job`), both `knowledge_scope: player_visible` (a vanilla
player sees the "q -> add job" menu's own job vocabulary and can queue this
exact action), both `coordinate_bearing: false`, both `verified: unverified`
(honest -- this stream never ran against a live DFHack process).

Role grants, each with its own reason recorded in the YAML, not just here:

- **`agents/overseer/tools.yaml`** (the sole writer): `workjob.list` under
  `read`, `workjob.queue` under `write`. Reason: the same reasoning that
  put every other fort-mutating tool under the Overseer alone
  (`sole_writer: overseer`, `agents/ROSTER.yaml`) -- this is the one role
  permitted to act on the fort at all.
- **`agents/architect/tools.yaml`**: `workjob.list` under `read` (so a
  proposal can name the direct-job route as an alternative when
  `orders.list` already shows `manager_appointed: false`), `workjob.queue`
  explicitly under `deny` with reason "Advisors do not act. Propose it." --
  the identical wording every other Overseer-only write already gets there
  (`orders.create`, `well.build`, ...).
- **`agents/quartermaster/tools.yaml`** (disabled role, `write_authority:
  none` regardless): `workjob.queue` added to `deny`, matching that file's
  own pre-existing `orders.create`/`orders.cancel` denials verbatim in
  spirit -- "this role is not enabled and holds no write authority
  regardless... listed explicitly... since [this] is squarely this role's
  future domain," arguably more so here since brewing is literally "food
  and drink security," this role's own stated charter.
- **`agents/consultant/tools.yaml`**: left untouched, deliberately, matching
  the established precedent that `orders.*` also has no consultant entry at
  all (neither grant nor explicit deny) -- this role's domain is knowledge,
  not fort action or work-order administration, and padding its file with a
  deny for every out-of-domain tool was not this project's existing
  convention.

### 5. Tests added, mirroring existing conventions

No `.lua` file in this repo is ever executed by the test suite (confirmed
by reading `dfmcp/tests/test_registry.py`/`test_roles.py`/`test_tools.py`
before writing anything: all three validate the YAML-driven registry/role/
argv-translation layer only, never shell out to a real DFHack process).
Added `dfmcp/tests/test_workjob_tool.py`, 19 tests, following that same
convention: the manifest entry's fields (effect, mutates, coordinate
bearing, unverified), the argument signature against the `.lua` file's own
dispatch code (`args[2], args[3], args[4]`), the per-role grants (overseer
write, architect read + explicit deny with a reason string read back from
the YAML directly, quartermaster's deny read back the same way since it is
never reachable through `load_roster` while disabled, consultant's
deliberate non-entry), MCP name round-tripping (`workjob.queue` ->
`workjob__queue`), and `argv_for_call` happy-path construction.

**One real finding surfaced by writing these tests, not fixed here**:
`dfmcp/tools.py`'s own `_SHELL_METACHAR_RE` (a pre-existing, deliberate
security boundary, unrelated to this stream, and `dfmcp/tools.py` is not a
touched surface for this stream) refuses any string argument containing a
literal apostrophe, because it becomes a literal word on a live command
line. DF's own vanilla default workshop names carry apostrophes ("Mason's
Workshop", "Mechanic's Workshop"), and
`handoffs/2026-09-19-well-and-harvest.md`'s own live write-up names this
fort's actual Mason's Workshop **"Stoneworker's Workshop"** (the in-game
display name for a Masons subtype built of stone). So **the very first
live `blocks` call, if routed through the MCP server rather than the raw
CLI, will be refused by `dfmcp/tools.py` before it ever reaches
`df-overseer-workjob.lua` at all.** The raw
`./dfhack-run df-overseer-workjob queue blocks "Stoneworker's Workshop"
true` CLI path has no such restriction and will work. Recorded in
`TOOLS.yaml`'s own notes and pinned by
`test_apostrophed_workshop_names_are_refused_by_the_mcp_layer` rather than
worked around, since loosening that sanitizer is a security-relevant
decision for a separate stream, not this one.

Full suite: **529 passed / 1 skipped before this stream** (ambient
`python -m pytest`, ground truth read live at the start of this stream, not
assumed from `CLAUDE.md`'s status header, though it matched exactly) ->
**548 passed / 1 skipped after** (19 new tests, 0 regressions, 1 skip
unchanged -- the pinned transport-SDK-import guard, per `CLAUDE.md`).

### 6. What the first live run must check, in order

Never run by this stream; this is the checklist for whoever runs it next,
fort paused throughout the read-only steps:

1. `./dfhack-run df-overseer-workjob list` -> confirm it returns exactly
   `{"jobs": ["blocks", "brew_drink", "mechanisms"]}` (sorted).
2. `./dfhack-run df-overseer-workjob queue blocks "Stoneworker's Workshop"
   true` (dry run, **CLI directly, not via MCP** -- see the apostrophe
   finding above) -> confirm it resolves the real Mason's Workshop, reports
   `job_item_count: 1`, and does not mutate anything (`would_queue: true`,
   no job appears in `world.jobs.list`).
3. Same dry run for `mechanisms` against the real Mechanic's Workshop.
4. `queue brew_drink Still true` (dry run) -> read whether it resolves
   cleanly (`job_item_count` equal to the reaction's own reagent count) or
   names exactly which reagent it refuses and why. Either outcome is a
   valid, informative result; neither is a bug in itself.
5. Only once all three dry runs look right and the fort is freshly
   quicksaved (per this project's standing discipline, `docs/TRAPS.md`):
   ONE real call, `DRY_RUN=false`, for `blocks` or `mechanisms` (the
   simpler, single-reagent case, not `brew_drink`) against the target
   workshop. Immediately after, with the fort still paused: confirm a new
   `ConstructBlocks`/`ConstructMechanisms` job exists in
   `world.jobs.list`, `#bld.jobs` on the target workshop increased by
   exactly one, and `job.job_items.elements` has exactly the one BOULDER
   entry this tool built. Only once that is confirmed should the fort be
   unpaused to see whether a citizen with the matching labour actually
   picks the job up (this is the step well-and-harvest/well-finish's own
   manager-order route never reached: a job existing in the queue at all).
6. If and only if step 5 succeeds, repeat the same real-call-then-pause
   discipline for `brew_drink`, expecting it may instead surface the
   refused-reagent finding from section 2 above -- in which case the next
   step is confirming that reagent's real shape against this install's own
   live raws (which this offline stream could not do) before extending
   `reagent_job_item` to handle it, not guessing a fix blind.

### 7. Touched surfaces, final

`scripts/dfhack/df-overseer-workjob.lua` (new),
`scripts/dfhack/TOOLS.yaml`, `agents/overseer/tools.yaml`,
`agents/architect/tools.yaml`, `agents/quartermaster/tools.yaml`,
`dfmcp/tests/test_workjob_tool.py` (new), this handoff doc.
`agents/consultant/tools.yaml` deliberately left untouched (section 4).
No VM, no SSH, no deploy; nothing in this stream ran against a live
DFHack process. `Working.md`, `decisions/DECISIONS.md`, `memory/` and
`handoffs/INDEX.md` were not written, per this handoff's own rule --
the orchestrator owns those.
