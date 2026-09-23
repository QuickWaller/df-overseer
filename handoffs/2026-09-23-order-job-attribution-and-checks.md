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

(executor fills in)
