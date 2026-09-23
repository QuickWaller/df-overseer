# Handoff: generalise `workjob` over every workshop and job, with a count and repeat

Date: 2026-09-21. Live but read-only on VM 103 (fort paused, dry runs only);
no real job is queued by this stream.

**DISPATCHED 2026-09-23** (user's call: "lets generalise workjob"), after
sitting written but undispatched for two days. Five things changed under it
in the meantime, and they narrow the work rather than widening it:

1. **A `REPEAT` param already landed** on `workjob queue` 2026-09-23
   (`handoffs/2026-09-23-order-job-attribution-and-checks.md` item 6),
   untested live. Deliverable 2 below still stands, but REPEAT is now an
   existing parameter to verify and keep working, not one to invent.
2. **`orders.create` already covers twelve job kinds** (blocks, mechanisms,
   barrels, brew_drink, bucket, bed, door, table, chair, splint, crutch,
   soap) while `workjob` still knows three. That asymmetry is the concrete
   shape of the problem: the fort's Chair had to be ordered through
   `orders.create` on 2026-09-23 because `workjob` had no token for it.
   **Twelve is the floor, not the target**: `getJobs` should make the
   vocabulary the game's, not a second hand-maintained table. If you end up
   with a table of twelve, the stream has failed its own point.
3. **Manager orders are no longer hypothetical.** Two real Office zones
   exist (one owned by the Manager, unit 345) and four manager orders exist,
   none yet active. So the "until manager orders work" framing in Why below
   is softened: both routes will be used together, and the user has said so
   explicitly. Direct jobs remain the route that does not depend on a
   Manager, an Office or room value, which is exactly why this tool matters.
4. **`df.job.order_id` links a spawned job back to its manager order**,
   correcting an earlier research claim. If your generic path touches job
   creation, do not break or fake that field: a direct job legitimately has
   no order, and must not pretend to have one.
5. **Suite baselines have moved** since this doc was written. Current:
   ambient **1348 passed / 3 skipped**, `.venv-dfmcp` **652 passed** (both
   measured 2026-09-23). Report before and after against these, not the
   834/475 figures in Done means below.

Two rules to add to the Rules section below, both learned the hard way since
this doc was written: **use `bash scripts/vm-ssh.sh df '<cmd>'` for every VM
command** (do not write your own ssh wrapper and do not read the address from
`.env` yourself: four separate agents have leaked a VM address doing exactly
that), and **no attribution lines in any commit message** (no Co-Authored-By,
no "Generated with Claude Code"). Also: a concurrent research stream owns
`research/2026-09-23-flood-relevance-and-traffic.md` and touches no code, so
`scripts/dfhack/TOOLS.yaml` is yours alone this cycle.

One warning from the most expensive bug of the week, which your work is
directly exposed to: **a `pcall`-guarded read that returns a default on
failure is indistinguishable from a genuine negative reading.** Six creature
tag reads shipped silently broken that way and passed three offline test
layers, because none held a real creature raw. You will be reading reagents,
job definitions and item fields off live raws. Report unreadable fields
explicitly (the pattern is a `read_failures` array plus `dfhack.printerr`),
and treat `docs/TRAPS.md`'s "A pcall-guarded read..." entry as required
reading before you write a single guarded read.

Read `CLAUDE.md` (especially "Tools must be generalisable"),
`scripts/dfhack/df-overseer-workjob.lua` (the three-job tool this replaces, and
its long header on the DFHack code path it followed),
`handoffs/2026-09-19-workshop-add-job.md`, `handoffs/2026-09-21-nobles-appoint.md`
(why manager orders are not available yet), `scripts/dfhack/df-overseer-building.lua`
and `scripts/dfhack/df-overseer-zone.lua` (the pattern: kinds read from the game,
per-kind policy in data, dry run by default), and `docs/TRAPS.md`, then this.

## Why

Manager orders need an appointed Manager **and an Office**; the user confirmed
from play that the office is required, and the fort has none yet. Until that works
(and for anything a player would do by clicking a workshop), the fort's only way to
make things is a direct job queued at a workshop, which is what `workjob` does. It
knows **three jobs** (blocks at the Masons, mechanisms at the Mechanics, brewing at
the Still), queues **one** at a time, and has no repeat. The user's call
(2026-09-21): we need a proper tool for this. It is also on the known list of
single-instance tools that break the generalisability rule.

## Two facts found on the install that change the design

Both read from this install's own files on 2026-09-21, not yet exercised by the tool:

1. **DFHack already builds a workshop's job list generically.**
   `hack/lua/dfhack/workshops.lua` exposes `getJobs(buildingId, workshopId, customId)`,
   the module behind the game's "add job" menu equivalent. It returns, for any
   workshop or furnace kind, the hard-coded job definitions (name, `job_fields`,
   `items`) **plus every reaction the raws attach to that building**, with each
   reagent converted to a `job_item` by `reagentToJobItem` (the reagent cloned with
   defaults, `reaction_id` and `reagent_index` set), and smelting jobs per ore. The
   existing tool's header claims no DFHack script builds a reaction job's items
   generically; **that is wrong for this install** (`addReactionJobs`). The
   Lua-stream's hosting dump (out of tree, in the scratchpad `building-dump/`)
   already found `getJobs` covers only 16 of 33 kinds for hard-coded jobs, so the
   coverage gap is real and must be measured.
2. **A job carries a `repeat` flag** (also `do_now`, `by_manager`, `suspend`), the
   "repeat" toggle in a workshop's job list. That is a workshop-level standing order
   with no manager. It is the honest answer to "keep making these".

## Deliverables

1. **`list-jobs WORKSHOP`**: for an existing workshop (addressed by landmark name, as
   `workjob` does today), every job the game offers there, from `getJobs`, each with
   a token to pass back, its name, and what it needs (the job's `items` summarised:
   class, quantity, material constraint). Coordinate-free. State plainly which job
   kinds `getJobs` does not cover for that workshop; an unreadable field is `null`
   plus an error, never a default.
2. **`queue WORKSHOP JOB [COUNT] [REPEAT] [DRY_RUN]`**, generic over the job token,
   replacing the three-entry table with `getJobs`. Dry run by default. COUNT is how
   many identical jobs (the workshop cap is 10 queued; refuse above it or over the
   room left, with the reason). REPEAT sets the job's `repeat` flag. Keep the
   existing refusals (wrong workshop, unfinished workshop, full queue) and keep
   refusing, rather than guessing, when a reagent cannot be resolved to a concrete
   item. **Keep the old tokens (`blocks`, `mechanisms`, `brew_drink`) working with
   unchanged results.**
3. **Requirements and honesty in the result**, like the building tool: what the job
   needs, the six-deduction availability of each needed item (reuse
   `stocks.availability`'s logic, do not re-derive it), and any gap ("needs 1
   boulder, 0 available"). A job that can be queued but cannot start is reported.
4. **Read-only live verification on VM 103**: `list-jobs` for every workshop and
   furnace the fort has (Masons, Mechanics, Still, Craftsdwarfs and whatever else
   exists), the coverage gap per kind, dry-run `queue` for at least a hard-coded
   job, a reaction job with a concrete reagent, one with a wildcard reagent (say
   what happens), COUNT and REPEAT, and each refusal; pause state and tick
   identical before and after. Quote the output. **No real job.** If a real job is
   needed to settle a question, write the exact supervised test for the
   orchestrator instead of running it.
5. **Manifest and tests**: `scripts/dfhack/TOOLS.yaml` (new commands in the
   optional-args forms; `knowledge_scope` chosen and justified), tests, and the
   proposed role grants written into the report. Do not edit `agents/**` or
   `dfmcp/**` (report any argument-description text needed for `dfmcp/tools.py`).

## Rules

- You own `scripts/dfhack/df-overseer-workjob.lua`, `scripts/dfhack/TOOLS.yaml`, its
  manifest tests and this doc. Do not touch `dfmcp/**`, `production/**`, `agents/**`
  or `gotchas/**`. One live stream at a time on VM 103; check nothing else is running.
- Live, read-only: never unpause, never queue a real job, bound every scan
  (`docs/TRAPS.md`), run scripts from a scratch path and remove it. Stop and report
  on any classifier refusal; do not route around it. SSH as `df`; read secrets by key
  only; no address, hostname or token in any tracked file.
- Unknown is never zero. Do not write `Working.md`, `decisions/DECISIONS.md`,
  `memory/` or `handoffs/INDEX.md`. **Commit after each milestone** and extend this
  doc's report as you go. No em dashes in prose. Use the Write tool for scratch
  scripts rather than long inline shell heredocs.

## Done means

`workjob` lists and dry-runs every job the game offers at every workshop the fort
has, the old three tokens behave as before, COUNT and REPEAT are supported and their
refusals tested, coverage gaps are named per kind, the manifest and tests agree, the
suites pass (baseline **834 passed / 2 skipped** ambient, **475 passed** in
`.venv-dfmcp`, report before and after), and the write-up says what a real
supervised queue test needs.

## Result, 2026-09-23 (executed by the dispatched stream)

**Done.** `scripts/dfhack/df-overseer-workjob.lua`'s three-entry `JOB_INFO`
table is gone. `list-jobs WORKSHOP_LANDMARK_NAME` and a generalised `queue`
now read the job vocabulary live from DFHack's own
`hack/lua/dfhack/workshops.lua` `getJobs(buildingId, workshopId, customId)`
-- the exact module backing the real "q -> add job" menu, read in full off
this install (578 lines, over SSH, not from memory or GitHub) before writing
a line of conversion code. The three old short tokens (`blocks`,
`mechanisms`, `brew_drink`) still resolve, unchanged, via a 3-entry
`LEGACY_ALIASES` table matched against each workshop's own real `getJobs`
output -- not a second hand-maintained job spec.

### Coverage: measured, not estimated

A bounded, read-only probe walked every `df.workshop_type` (25 kinds) and
`df.furnace_type` (8 kinds) via the enum's own `_first_item`/`_last_item`
bounds (`pairs()` over a DFHack enum-type object does NOT yield its
name<->int entries at all -- verified live this session, a real trap worth
recording: it only yields ~11 metadata keys such as `new`/`_identity`/
`attrs`; the int->name reverse lookup via `enum[i]` is the only reliable
enumeration and is now the pattern used in the shipped tool's own
`workshop_kind_ids`/list-jobs code) and called `workshops.getJobs` for each:

- **workshop_type (25 total): 11 have a hard-coded `jobs_workshop` entry**
  (Jewelers, Fishery, Masons, Carpenters, Kitchen, Butchers, Mechanics,
  Loom, Leatherworks, Dyers, Siege). Of the other 14, **10 still get real
  jobs purely from raws reactions** (Ashery 1, Craftsdwarfs 104, Custom 6
  at the wildcard scan, Farmers 2, MagmaForge 15, MetalsmithsForge 15,
  Millstone 2, Quern 2, Still 3, Tanners 2). Only **4 returned zero jobs**:
  Bowyers, Clothiers, Kennels, Tool.
- **furnace_type (8 total): 5 hard-coded** (Smelter, MagmaSmelter,
  GlassFurnace, WoodFurnace, Kiln). Of the other 3, **2 still get real jobs
  from raws reactions** (MagmaGlassFurnace 13, MagmaKiln 20). Only
  **Custom furnace returned zero** at the wildcard scan.
- **Net: 28 of 33 kinds have at least one real, queueable job through
  `getJobs` on this install's own raws; 5 do not** (Bowyers, Clothiers,
  Kennels, Tool workshop; Custom furnace at customId=-1). This is the
  honest generalisation ceiling this stream reached -- not the "16 of 33"
  figure the handoff's own header cited from the out-of-tree hosting dump,
  which measured hard-coded coverage only, not `getJobs`'s real total
  (hard-coded + raws reactions combined). Why those 5 specifically return
  nothing was not independently confirmed from source this stream (Kennels
  trains/assigns animals rather than manufacturing, which is plausibly
  correct by design; the other four are not explained anywhere this stream
  read) -- flagged honestly, not guessed.
- **A genuine gap found in DFHack's OWN hard-coded table, not this tool's
  code**: Mechanics' "construct traction bench" job (`getJobs` entry,
  `job_type=ConstructTractionBench`) lists a MECHANISM reagent as
  `item_type=df.item_type.MECHANISM` in DFHack's own source, but this
  install's `df.item_type` enum has no `MECHANISM` member (superseded by
  `TRAPPARTS` on this DF version, matching `memory/dfhack-environment.md`'s
  own prior finding on this exact naming drift) -- so that field silently
  evaluates to `nil` at DFHack's own module-load time, and the reagent
  reads back `item_type=-1` (wildcard) through no fault of this tool. Live
  evidence: `list-jobs "Mechanic's Workshop"` (quoted below) shows
  `constructtractionbench`'s middle item as `concrete: false`. `queue
  constructtractionbench` would therefore correctly refuse on that reagent
  -- this tool's own honesty contract working exactly as designed against
  an upstream data problem it did not create and cannot fix.
- **Known noise, not a bug here**: `getJobs` for Smelter/MagmaSmelter runs
  DFHack's own `addSmeltJobs`, which calls bare `print`/`printall` for
  every ore in the raws -- upstream DFHack debug output, unsuppressable
  from this file without monkeypatching a shipped module. It lands in the
  dfhack log, never in this tool's own JSON stdout. Not exercised this
  session (the fort has no Furnace built yet), noted for whoever first
  calls `list-jobs`/`queue` at a real Smelter.
- **One thing the generic path does differently from the old code, likely
  more correctly**: `getJobs`'s reaction-derived item specs carry
  `reaction_id`/`reagent_index` (which reagent slot of which reaction a
  job_item satisfies); the OLD hand-written `reagent_job_item` never set
  either field. The new `job_item_from_spec` copies them through when
  present. Whether the engine needs that linkage was not exercised (no
  real reaction job queued this stream either) -- a discovered gap in the
  tool's own prior version, not a claim the old blocks/mechanisms jobs
  (neither reaction-derived) were ever wrong.

### Live, read-only verification on VM 103 (Uniboslan)

Fort paused throughout; `dfhack.world.ReadPauseState()`/`ReadCurrentTick()`
read **`true`, `107874`** before this session's first call and **`true`,
`107874`** after its last -- identical, confirming no mutation and no
unpause. Method: the new `.lua` file was copied to a scratch path
(`/tmp/df-overseer-workjob-test.lua`, never the deployed file) and run
through a 20-line wrapper (`/tmp/run.lua`) that sets `dfhack_flags = {module
= false}` before `loadfile`+`pcall`, the documented workaround for
`dfhack-run lua -f` not setting `dfhack_flags` (`docs/TRAPS.md`, "Extended
2026-09-22"). Both scratch files were removed after. **Not yet deployed as
the live tool** -- this stream's own hard lines are read-only-live +
offline-build, same convention every prior workjob stream followed before
its own first deploy.

**`list` (legacy, unchanged), quoted in full:**
```json
{"jobs": ["blocks", "brew_drink", "mechanisms"]}
```
Byte-identical to the pre-change tool.

**`list-jobs "Mechanic's Workshop"`**: `job_count: 2` --
`constructmechanisms` (BOULDER, concrete, mat_type 0, `flags3.hard`,
availability read via reused `stocks.get_availability`: 4 available of 7
total, 3 `in_building`) and `constructtractionbench` (TABLE concrete + a
non-concrete middle item, the upstream MECHANISM/TRAPPARTS drift above +
CHAIN concrete, 2 available of 3, 1 unreachable).

**`list-jobs Still`**: `job_count: 3`, all three purely reaction-derived,
**two of which the old tool could never reach**: `reaction:
brew_drink_from_plant` (119 PLANT available of 130 total, second reagent a
wildcard empty-food_storage container, correctly `concrete: false`),
`reaction:brew_drink_from_plant_growth` (129 PLANT_GROWTH available of
133), `reaction:make_mead` (1 LIQUID_MISC available of 9, 9 unreachable --
a real, actionable finding: this fort's mead ingredient is sitting almost
entirely unreachable right now).

**`list-jobs "Stoneworker's Workshop"` (Masons)**: `job_count: 19` -- 16
hard-coded tokens (`constructarmorstand`, `constructblocks`,
`constructthrone`, `constructcoffin`, `constructdoor`,
`constructfloodgate`, `constructhatchcover`, `constructgrate`,
`constructcabinet`, `constructchest`, `constructstatue`, `constructslab`,
`constructtable`, `constructweaponrack`, `constructquern`,
`constructmillstone`) plus **3 generated, per-world reactions**
(`reaction:make_ent16 inp1_body`, `reaction:make_ent16 inp2_body`,
`reaction:make_ent18 ins4_body` -- the instrument-piece reactions
`docs/TRAPS.md`'s "the raws are not the whole reaction list" entry already
names; confirms `getJobs` reads `world.raws.reactions.reactions` live, not
static files, exactly as that entry requires). `read_failures: []` on
every one of the three real workshops.

**`queue` dry-runs, quoted:**
- `queue blocks "Stoneworker's Workshop"` (legacy alias, defaults): field-
  for-field identical output shape to the pre-change tool --
  `job_item_count: 1`, `BOULDER` resolved, `would_queue: true`.
- `queue brew_drink Still`: refuses exactly as before -- `"item 2 has no
  concrete item_type (a wildcard/tag-matched reagent ... is not supported
  by this tool; refusing rather than guessing a filter for it)"`.
- **`queue constructthrone "Stoneworker's Workshop" true false 3`** -- the
  literal motivating case from the handoff's own opening line (the fort's
  real Chair had to be ordered through `orders.create` because `workjob`
  had no token for it). Now dry-runs cleanly: `job: "ConstructThrone"`,
  `count: 3`, `BOULDER` resolved, `would_queue: true`.
- Same call with `REPEAT=true`: `repeat_requested: true`, otherwise
  identical -- confirms the REPEAT plumbing (landed 2026-09-23, untested
  live until now) at least reaches the dry-run result correctly.
- `queue constructthrone "Stoneworker's Workshop" true false 11`: refused
  -- `"COUNT 11 would exceed workshop 'Stoneworker's Workshop''s job queue
  cap (0 queued now, room for 10 more, cap 10)"` (cosmetic double-apostrophe
  in the message from the format string, harmless, not fixed this pass).
- `queue nosuchjob "Stoneworker's Workshop"`: refused, and **more
  informative than the old fixed message** -- names every real token the
  workshop actually offers (all 19, quoted in the tool's own error text).
- `queue blocks NoSuchWorkshop`: `"unknown workshop: NoSuchWorkshop"`.
- `queue blocks Well`: `"landmark 'Well' is not a workshop or furnace"`
  (Well confirmed via `landmarks.list`, a Civzone-adjacent building, not a
  workshop).

No real job was queued; `DRY_RUN=false` remains untested live, as stated.

### Suites, before and after

Both baselines matched the dispatch brief's corrected figures exactly
before this stream's first edit:

| Suite | Before | After |
|---|---|---|
| ambient `python -m pytest` | 1348 passed, 3 skipped | 1361 passed, **1 failed**, 3 skipped |
| `.venv-dfmcp python -m pytest dfmcp/tests` | 652 passed | 651 passed, **1 failed** |

**The one failure in each is the same test**,
`dfmcp/tests/test_workjob_tool.py::test_workjob_queue_argument_signature_matches_the_lua_dispatch`,
which pins `workjob.queue`'s args to the old 4-token list
(`["JOB","WORKSHOP_LANDMARK_NAME","DRY_RUN","REPEAT"]`). It is an
**expected, correctly-out-of-scope consequence** of adding COUNT as a fifth
positional argument -- `dfmcp/**` is explicitly not a touched surface for
this stream. The fix is a one-line change to that test file (append
`"COUNT"` to the expected list at
`dfmcp/tests/test_workjob_tool.py:100`) plus, separately, wiring
`dfmcp/tools.py` to actually expose `list-jobs` and the new `COUNT`
argument through the MCP server (neither of which exists there yet --
`workjob.list-jobs` is not callable via MCP until that stream runs).
**Argument-description text needed for `dfmcp/tools.py`**, for whoever
picks that up: `COUNT` -- "how many identical jobs to queue (default 1,
refused above the workshop's remaining queue room)"; `list-jobs`'s
`WORKSHOP_LANDMARK_NAME` -- same description as `queue`'s own workshop
argument, already in `dfmcp/tools.py` for that command.

**The ambient delta arithmetic, spelled out**: baseline 1348 passed. This
stream added 14 new tests (`tests/test_workjob_generalise_manifest.py`,
all passing: +14) and edited 2 existing assertions in
`tests/test_order_job_attribution_manifest.py` to match the new arg list
(both still pass, net +0 -- they were already counted in the 1348
baseline). The one dfmcp-owned test above flips from passing to failing
(-1 passed, +1 failed) as an unavoidable, correctly out-of-scope
consequence, since `dfmcp/tests/` is itself inside the ambient collection
tree and cannot be excluded from that count. Net: 1348 + 14 - 1 = **1361
passed**, **1 failed**, 3 skipped unchanged -- matching what actually ran,
confirmed above.

### What a real supervised queue test needs (owed, not run this stream)

Exact command sequence for the orchestrator, all on VM 103, `df` user, via
`scripts/vm-ssh.sh`:

1. Confirm pause/tick unchanged from this report's own values as a sanity
   floor, then **quicksave and verify the save landed** by reading every
   save slot's `world.sav` mtime plus `cur_savegame.save_dir` fresh
   (`docs/TRAPS.md`'s quicksave-slot-rotation entries -- do not trust a
   single fixed slot).
2. Deploy the reviewed `df-overseer-workjob.lua` for real (replacing the
   live file, hash-verified per `CLAUDE.md`'s `core.autocrlf=false`
   archive rule), or re-run it from the same scratch-copy + wrapper this
   stream used if a full deploy is not yet wanted.
3. **The single most useful real test, tied to the fort's own actual open
   need**: `queue constructthrone "Stoneworker's Workshop" false false 1`
   (`DRY_RUN=false`, `REPEAT=false`, `COUNT=1`) -- this produces exactly
   the Chair item the fort's real, already-built Chair building is
   buildingplan-suspended waiting on (`CLAUDE.md`'s own status block), by
   the direct-job route rather than the stalled manager-order route
   (order id 3, `validated: false`). Lower-risk than a brand new job kind:
   the underlying `ConstructBlocks`-shaped job_item spec (BOULDER,
   mat_type 0, `flags3.hard`) is the same shape already live-verified for
   real on 2026-09-19.
4. Immediately after, still paused: read `df.global.world.jobs.list` for
   the new job (a `ConstructThrone` job with `order_id == -1`, confirming
   it is NOT misattributed to the existing manager order 3) and `#bld.jobs`
   on the Masons workshop (expect 1). Do **not** unpause during this check.
5. Only once step 4 confirms a clean single job: a **second, separate**
   supervised call testing `COUNT` and `REPEAT` together against a
   cheap, reversible case (e.g. `queue blocks "Stoneworker's Workshop"
   false true 2` -- 2 real blocks jobs, `repeat` flag set), reading
   `job_ids` (both present), `repeat_set` (true), and `job.flags['repeat']`
   read back live (the one part of REPEAT's own citation, "confirmed from
   DFHack source, not this install's live `df.job._fields`", that only a
   real write can close). Since `repeat` jobs keep re-queuing, follow with
   `workjob.cancel` on both ids once confirmed, rather than leaving a
   standing order running unsupervised.
6. Report both checks' exact output in `evals/live/`, per this project's
   existing convention, and update this handoff's own `verified:` field in
   `scripts/dfhack/TOOLS.yaml` for `list-jobs`/`queue` from "dry-run/read-
   only live" to a real citation once step 3 lands.

### What could not be verified

- Why exactly Bowyers/Clothiers/Kennels/Tool workshop and the Custom
  furnace return zero jobs from `getJobs` on this install's raws --
  plausible for Kennels (animal training, not "add job" manufacturing),
  unconfirmed for the other three; no source this stream read explains it.
- Whether `reaction_id`/`reagent_index` on a reaction job's job_items
  actually matter to the engine's own item-to-reagent binding (see above)
  -- no real reaction job has ever been queued by this tool, old or new.
- Whether the deployed (not just dry-run) `queue`/`list-jobs` behave
  identically once actually pushed to VM 103 as the live tool -- this
  stream tested the exact file that will be deployed, from a scratch copy,
  but never replaced the live file itself (out of scope: read-only this
  stream).
- The exact reason `df.item_type.MECHANISM` is absent on this build (see
  the traction-bench finding above) -- flagged as consistent with
  `memory/dfhack-environment.md`'s prior TRAPPARTS finding, not
  independently re-derived from raws this session.
- Whether `dfmcp/tools.py` wiring `list-jobs`/`COUNT` through MCP hits the
  same apostrophe-in-workshop-name refusal `queue`'s own notes already
  document for "Stoneworker's Workshop" -- likely yes (same
  `_SHELL_METACHAR_RE` gate, same argument), not independently re-tested
  since `dfmcp/**` is out of scope for this stream.
