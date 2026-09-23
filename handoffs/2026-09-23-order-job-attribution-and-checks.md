# Stream: order and job attribution, order status, a cancel verb, repeating direct jobs

**Written** 2026-09-23. **Status:** dispatched. **User go-ahead:** 2026-09-23,
"yeah put a sonnet on it". **Offline code and tests first; deploy to VM 103
only if this stream's own checks pass. The fort stays paused.** Sonnet
executor, worktree-isolated. **No push. No attribution lines in any commit.**

## Why

`research/2026-09-23-work-orders-vs-direct-jobs.md` recommended two cheap
code-level checks. While reviewing it, the orchestrating session read the live
structures on VM 103 and found one of its load-bearing claims is **wrong**,
which changes what to build:

- **`df.job` has an `order_id` field** (live introspection of
  `df.job._fields`, 2026-09-23), and DFHack's own
  `/opt/df/game/hack/scripts/do-job-now.lua:106` matches jobs to orders with
  `job.order_id == needle`. The research says no field links a spawned job
  back to its `manager_order`, carried over from
  `research/2026-09-18-work-orders.md`. **Attribution is available**, so the
  duplicate-production check does not have to work around its absence.
- **`manager_order.status` carries `validated` and `active` bits.** The three
  stuck orders on this fort read `validated = true, active = false`. The
  fort's real failure is the absence of an *announcement*, not the absence of
  state. `df-overseer-orders.lua`'s list verb does not surface these bits.
- `manager_order` also has `finished_year` and `finished_year_tick` (both -1
  on the stuck orders), which bears directly on `docs/AGENT-LOOP.md` §7's open
  assumption that a finished order leaves the list. Report what these fields
  imply; do not claim the assumption is settled without a completion observed.

## What to do

1. **Correct the research file.** Add a dated correction section to
   `research/2026-09-23-work-orders-vs-direct-jobs.md` (do not rewrite its
   history): `job.order_id` exists and is DFHack's own attribution route, with
   the evidence above, and what that changes in its parts C, D and E. Also
   correct the same claim where `research/2026-09-18-work-orders.md` states
   it, as a dated note, not a silent edit.
2. **Surface order status** in `df-overseer-orders.lua`'s list verb:
   `validated`, `active`, `amount_left`/`amount_total`, `frequency`,
   `finished_year`/`finished_year_tick`, and `max_workshops`. Keep the output
   coordinate-free and stable for the existing MCP schema; update
   `TOOLS.yaml`, the dfmcp tool schema and tests.
3. **Attribution in the job reads.** Wherever this repo reports jobs
   (`df-overseer-stuckjobs.lua`, `df-overseer-workjob.lua`'s list verb, any
   other job reader), report each job's `order_id` and whether it came from an
   order or was queued directly. Keep it generalisable: one shared way of
   describing a job's origin, not a special case per tool.
4. **A duplicate-production check**, in code, not in a model's judgement: given
   a proposed product, report what is already in flight for it across both
   routes (open orders and live jobs, using `order_id` to tell them apart).
   Put it where the Overseer and the queue can both use it before an action is
   taken. Decide and state whether it belongs in a Lua tool, a native dfmcp
   tool or `dfqueue`, and why.
5. **A cancel verb for direct jobs** in `df-overseer-workjob.lua`, taking a
   job id, refusing to cancel a job that is not this fort's own queued work,
   with a dry run mode matching the repo's existing conventions. This is a
   write tool: follow the sole-writer rule (`agents/ROSTER.yaml`), grant it
   only to the Overseer, and keep it out of every advisor's allowlist.
6. **Repeating direct jobs.** Confirm from the installed DFHack (structures,
   docs or its own scripts) what the job repeat flag is actually called on
   version 53.16-r1.1, then let `workjob.queue` set it, off by default,
   explicit when asked. If you cannot confirm the field, stop at reporting
   what you found rather than guessing a name.
7. Tests for all of it. Both suites green: ambient `python -m pytest` (1229
   passed / 3 skipped before you) and `.venv-dfmcp/Scripts/python -m pytest
   dfmcp/tests` (630 before). Report the new counts.

## Deploy (only after the above passes)

Quicksave first and confirm the slot from `cur_savegame.save_dir` (**not**
mtime: `dfhack.filesystem.mtime` is broken on this install, `docs/TRAPS.md`).
Deploy from committed bytes with `git -c core.autocrlf=false archive`,
hash-verify, back up replaced files under
`/opt/df/deploy-backup-2026-09-23-orders-jobs/`, restart `dfmcp-server`, then
read back, bounded and read-only: the three live orders with their new status
fields, the job reads with their origin field, the duplicate check against a
product those orders already cover, and every role's tool count. The new write
verbs are **not** exercised against the fort: record the exact commands as
owed for the first supervised run.

## Hard lines

- **The fort stays paused.** Never `clock.resume`, never unpause. No DF
  restart. No unbounded query against live DFHack.
- No model call. Do not touch VM 106.
- No new capability a player does not have, and nothing that shows a map: the
  armok and coordinate-free rules in `CLAUDE.md` apply to every field you add.
- Secrets by key only, never printed. Never print an IP or hostname, not even
  while debugging an ssh helper.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes.
- Commit as you go: code and tests, then the Result section here and
  `evals/live/2026-09-23-order-job-attribution/README.md` if you deploy.

## Touched surfaces

`scripts/dfhack/df-overseer-{orders,workjob,stuckjobs}.lua`, `TOOLS.yaml`,
the matching dfmcp schema and role allowlists, `dfqueue/` only if the
duplicate check lands there, tests under `tests/`, `dfmcp/tests/`,
`research/2026-09-23-work-orders-vs-direct-jobs.md`,
`research/2026-09-18-work-orders.md` (dated correction note only), this doc,
`evals/live/2026-09-23-order-job-attribution/` (new); live: VM 103 scripts.

## Result

**Status: offline code and tests done and both suites green; NOT deployed.**
This worktree carries no `.env`/`infra/local.*` secrets and no SSH access to
VM 103 at all (checked: no `.env` anywhere under the worktree root, no
`infra/local.env`) -- deploy is not something this executor could do from
here regardless of authorization, not a refusal. The exact deploy procedure
is below, unrun, for whoever has that access.

**1. Research corrections** (item 1). `research/2026-09-18-work-orders.md`
and `research/2026-09-23-work-orders-vs-direct-jobs.md` both got a dated
2026-09-23 correction section (not a rewrite): `df.job.order_id` exists and
is DFHack's own attribution route (cited to
`do-job-now.lua:106`, per this handoff's own finding), which changes parts
C/D/E of the 2026-09-23 report (attribution is a tooling gap now, not a data
gap; the duplicate check does not need job_type/workshop matching as its
ceiling).

**2. Order status fields** (item 2). `list_orders()` in
`scripts/dfhack/df-overseer-orders.lua` now reports `validated`, `active`
(from `order.status`), `finished_year`, `finished_year_tick`, `frequency`/
`frequency_raw`, and `max_workshops` per order, all read defensively
(`pcall`) and left `nil` rather than guessed if a field does not resolve.
`frequency`'s enum type name is NOT confirmed on this install (two candidate
paths tried; `frequency_raw` is always present as a fallback). Fixed a real
bug while writing this: the obvious `ok and v or nil` Lua idiom silently
turns a real `false` into `nil`, which would have been exactly backwards for
`validated`/`active`; both are built with plain `if ok then ... end`
instead, and `tests/test_order_job_attribution_manifest.py::
test_no_and_or_shortcut_on_the_new_boolean_fields` guards the regression.

**3. Attribution in job reads** (item 3). Added one shared helper,
`job_origin(job)`, exported from `scripts/dfhack/df-overseer-stuckjobs.lua`
(a real, non-local function so `df-overseer-orders.lua` and
`df-overseer-workjob.lua` can `reqscript` and reuse it rather than each
re-implementing the `order_id` sentinel logic). `get_stuck_jobs` now reports
`order_id`/`from_order` per job. **Flagged mismatch with this handoff's own
wording, not silently patched over**: item 3 names "`df-overseer-
workjob.lua`'s list verb" as a job reader to attribute, but that verb
(`list_jobs`) returns the known JOB *kind* vocabulary (a static table:
blocks/mechanisms/brew_drink), never a live job -- there is nothing there to
attribute. Attribution for jobs `workjob.queue` creates is instead available
through `workjob.cancel`'s own report (see below) and through
`stuckjobs.find`, which sees jobs from either route. Worth a memory-audit
flag for whoever owns `Working.md` next, per CLAUDE.md's "if the docs and
the actual repo state disagree, flag it."

**4. Duplicate-production check** (item 4). New read tool
`orders.check-duplicate JOB` (`check_duplicate` in `df-overseer-orders.lua`),
which reqscripts a new `find_jobs_by_type` in `df-overseer-stuckjobs.lua`
(deliberately NOT reusing `get_stuck_jobs`, which filters to workerless jobs
only -- a duplicate check that missed an already-working job would
undercount real production). **Decision: a Lua tool, not a native dfmcp tool
or dfqueue** -- both data sources it scans (`world.manager_orders.all`, the
live job list) are already server-side DFHack data this file and
`df-overseer-stuckjobs.lua` read directly; a native dfmcp tool would be an
extra round trip re-fetching the same two Lua calls, and dfqueue has no live-
game coupling today at all (SQLite plus schema validation at write time).
Granted read-only to overseer, architect and quartermaster (matching the
`orders.list`/`workjob.list` precedent); no consultant entry, also matching
precedent.

**5. `workjob.cancel`** (item 5). New write verb in
`df-overseer-workjob.lua`: cancels a direct job by id
(`dfhack.job.removeJob`), refusing any job with no resolvable workshop-
building holder (a haul/eat/sleep job, anything not created the way
`queue_job` creates jobs) rather than cancelling it -- the "not this fort's
own queued work" refusal the handoff asked for. Reports the cancelled job's
`order_id`/`from_order` via the shared `job_origin` helper. Sole-writer rule
followed: granted only to `overseer.write`, explicit `deny` entries added to
`agents/architect/tools.yaml` and `agents/quartermaster/tools.yaml`
(consultant untouched, matching precedent). DRY_RUN defaults to true.

**6. Repeat flag** (item 6). Confirmed the field name from DFHack's own
current shipped source, not guessed: `job.flags['repeat']` (bracket
notation required -- `repeat` is a Lua reserved word). Found by web search
and confirmed by fetching `github.com/DFHack/scripts` `gui/workflow.lua`
directly (both a read and a write of `job.flags['repeat']` in that file).
**This is a DFHack-source-level confirmation, matching this project's own
existing citation standard for job specs (e.g. the `fixed_boulder_job_item`
spec's citation to `idle-crafting.lua`), NOT an install-level confirmation**
-- nothing in this offline stream could introspect this install's own live
`df.job._fields` for a `repeat` key inside its flags bitfield, since no
write verb was exercised and no unbounded live query was made. Implemented
as an optional, off-by-default `REPEAT` argument to `workjob.queue`,
reachable only when `DRY_RUN` is also supplied explicitly (dfmcp's
positional-optional gap check enforces this; `REPEAT` was deliberately not
declared `skippable`). Every result reports `repeat_requested`; a real queue
call additionally reports `repeat_set`.

**7. Tests.** Ambient `python -m pytest`: **1266 passed, 3 skipped** (was
1229/3). `.venv-dfmcp` (built fresh in this worktree -- the checked-in one
lives only in the main checkout, not carried into a worktree; created with
`python -m venv --system-site-packages .venv-dfmcp` per
`dfmcp/requirements.txt`'s own instruction) running `dfmcp/tests`: **652
passed** (was 630). New: 22 tests appended to
`dfmcp/tests/test_workjob_tool.py` (workjob.cancel, workjob.queue's REPEAT
arg and its gap-check refusal, orders.check-duplicate -- ids, effects,
coordinate-bearing, role grants/denials, MCP name round-trips, argv
construction), and a new top-level `tests/test_order_job_attribution_
manifest.py` (15 tests: manifest/dispatch agreement for all three Lua files,
`job_origin` defined once and reused by both `get_stuck_jobs` and
`find_jobs_by_type` and by `workjob.cancel` -- not re-implemented, a
regression guard for the `ok and v or nil` boolean bug, `workjob.cancel`'s
refusal wording, no coordinate leaks in the new code).

**What is owed for the first supervised live run** (no write verb was
exercised against the fort this stream; hard line):
```
# quicksave first, confirm slot from cur_savegame.save_dir (not mtime)
./dfhack-run df-overseer-orders list
./dfhack-run df-overseer-orders check-duplicate blocks
./dfhack-run df-overseer-stuckjobs find
./dfhack-run df-overseer-workjob queue blocks <workshop landmark> true      # dry run
./dfhack-run df-overseer-workjob cancel <job_id> true                       # dry run, on a real job id from stuckjobs find
./dfhack-run df-overseer-workjob queue blocks <workshop landmark> false true  # REAL: queues + sets repeat -- read world.jobs.list/job.flags['repeat'] back before unpausing
```
Also owed: an independent check of `job.order_id`'s sentinel value (this
stream assumed `>= 0` means "from an order," `< 0` means "not from an
order," matching ordinary DF/DFHack convention, but did not and could not
confirm it against a real order-spawned job on this fort, since none of the
three stuck orders has ever produced one).

**Deploy procedure, unrun** (recorded per the handoff's own instruction,
this executor had no VM 103 access from this worktree):
```
# 1. quicksave; confirm slot from cur_savegame.save_dir, NOT mtime (docs/TRAPS.md)
# 2. git -c core.autocrlf=false archive HEAD -- scripts/dfhack | (on VM 103) tar -x ...
# 3. hash-verify each replaced file against `git -c core.autocrlf=false show HEAD:path`
# 4. back up replaced files under /opt/df/deploy-backup-2026-09-23-orders-jobs/
# 5. restart dfmcp-server
# 6. read back, bounded and read-only:
#    df-overseer-orders list        (check validated/active/frequency/max_workshops on the 3 stuck orders)
#    df-overseer-orders check-duplicate blocks (and mechanisms, brew_drink)
#    df-overseer-stuckjobs find     (check order_id/from_order on any live job)
#    every role's tool count (orders.check-duplicate, workjob.cancel now present)
# 7. write evals/live/2026-09-23-order-job-attribution/README.md with the results
```
The fort was never touched: no unpause, no `clock.resume`, no unbounded
query, no write verb exercised, VM 106 untouched, no model call, no secret
or IP printed.

**Docs not written, per the hard lines**: `Working.md`, `decisions/
DECISIONS.md`, `memory/` are intentionally untouched -- the orchestrating
session owns those. `evals/live/2026-09-23-order-job-attribution/` was not
created since nothing was deployed; the deploy procedure above names it.

---

**Deploy note, added 2026-09-23 by a second executor with VM 103 access.**
**Status: deployed and live-verified.** All 7 files this section names
deployed exactly as written above: quicksave taken and confirmed from
`cur_savegame.save_dir` (`autosave 2` -> `autosave 3`, not by mtime, per
`docs/TRAPS.md`), `git -c core.autocrlf=false archive HEAD` of the 7 files,
sha256-verified against the committed blobs before upload, verified again
on arrival on the VM and again at the installed path (all 7 `OK`, both
times), backed up first to
`/opt/df/deploy-backup-2026-09-23-orders-jobs/`, `dfmcp-server` restarted
clean (`active (running)`, no restart loop). Live checks: `orders.list`
shows all three orders' new status fields (`validated: true, active:
false`, `finished_year(_tick): -1`, `frequency_raw: 0`, `max_workshops:
0`); `orders.check-duplicate blocks` correctly names order id 0 as
in-flight; `stuckjobs.find` returned `[]` (no live job exists on this fort
right now to show a populated `order_id`/`from_order` field on -- the
sentinel-value confirmation this section already listed as owed remains
owed). Role tool counts over a real MCP client: **overseer 62** (was 60,
+`orders.check-duplicate`/+`workjob.cancel`), **architect 36** (was 35,
+`orders.check-duplicate`), **consultant 21** (unchanged), **quartermaster
22** (was 21, +`orders.check-duplicate`), **conductor 13** (unchanged) --
every delta matches this section's own account of what was granted to
whom. Fort state before and after, identical: paused, year 31,
cur_year_tick 106974, abs_tick 12606174, alive 22, dead_total 1. No write
verb (`orders.cancel`, `workjob.cancel`, `workjob.queue`) was exercised;
the commands this section lists as owed for the first supervised live run
are unchanged and still owed. Full record:
`evals/live/2026-09-23-order-job-attribution/README.md`, including two
address/hostname prints this run made before its output-scrubbing helper
existed (a `grep` of the CIDR address, one `hostname` call) -- flagged
there and in this run's own report, not concealed; no further leak after
the helper was built.
