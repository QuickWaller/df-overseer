# Order status, job attribution, duplicate check and workjob.cancel deployed, 2026-09-23

**Status: deployed and live-verified.** The order/job attribution batch
(`handoffs/2026-09-23-order-job-attribution-and-checks.md`) was built and
tested offline by an earlier executor in this same stream, with both test
suites green and no live access from that worktree. This run had VM 103
access, carried out the deploy procedure that handoff's own Result section
recorded as owed, and verified it live. The fort stayed paused throughout;
no write verb (`orders.cancel`, `workjob.cancel`, `workjob.queue`) was
exercised against the fort.

## What was deployed

Seven files, built from committed bytes (`git -c core.autocrlf=false
archive HEAD`), matching exactly what the offline stream's Result section
named:

- `scripts/dfhack/TOOLS.yaml` -> `/opt/df/dfmcp-smoke/scripts/dfhack/TOOLS.yaml`
- `scripts/dfhack/df-overseer-orders.lua` -> `/opt/df/game/hack/scripts/`
- `scripts/dfhack/df-overseer-stuckjobs.lua` -> `/opt/df/game/hack/scripts/`
- `scripts/dfhack/df-overseer-workjob.lua` -> `/opt/df/game/hack/scripts/`
- `agents/architect/tools.yaml` -> `/opt/df/dfmcp-smoke/agents/architect/tools.yaml`
- `agents/overseer/tools.yaml` -> `/opt/df/dfmcp-smoke/agents/overseer/tools.yaml`
- `agents/quartermaster/tools.yaml` -> `/opt/df/dfmcp-smoke/agents/quartermaster/tools.yaml`

No `dfmcp/*.py` file changed in this batch (confirmed from the merge diff),
so no native-code redeploy was needed; the registry reads tool metadata
from the deployed `TOOLS.yaml` alone, matching every prior deploy's
pattern.

## Hash verification (twice)

Local hashes were taken two ways and agreed: `git -c core.autocrlf=false
show HEAD:<path> | sha256sum` (committed-bytes hash, per `CLAUDE.md`'s
deploy trap) matched a `sha256sum` manifest built from the archive's own
extracted bytes, for all 7 files. On the VM, `sha256sum -c` against that
manifest passed all 7 (`OK`) immediately after extraction, and passed again
after installing into the live paths (`sha256sum` at each installed path,
compared by eye against the same manifest values -- all 7 identical). `file`
on all 7 installed paths reported `UTF-8 text`/`ASCII text`, no CRLF.

| file | sha256 (committed bytes) |
|---|---|
| `agents/architect/tools.yaml` | `353a1bb3fc8077e5393ebb2fb6cc05e61492281d505d2b972326ea15584bc9e0` |
| `agents/overseer/tools.yaml` | `eca8fa12e88d3dc85111e4e3c779ba44e36057a422e2f6277fbf07fc88a16336` |
| `agents/quartermaster/tools.yaml` | `9dc38ecfbf5d390413b1c61a04cebfc06c762b44bab88f56b8fc66cdd4c91661` |
| `scripts/dfhack/TOOLS.yaml` | `693e7be2a021dc297c2c3da91db8862690e82d61f3ea38986e106898040310b3` |
| `scripts/dfhack/df-overseer-orders.lua` | `846da6f619f29957e0aa9ed5a1cc9432d54e1085c238d821de6a351409b1add0` |
| `scripts/dfhack/df-overseer-stuckjobs.lua` | `adad95bfe1c467fc0d3d7c97251a3c02b250e2743a5972fe93b077797067d99e` |
| `scripts/dfhack/df-overseer-workjob.lua` | `990a9533cd283486690b08e52388f5ce149a1a7bac2f190fc0430cbdc444232b` |

All 7 backed up first (with `cp -p`, preserving mode/mtime) under
`/opt/df/deploy-backup-2026-09-23-orders-jobs/` on VM 103, mirroring the
two deploy roots (`scripts/dfhack/` for the Lua trio,
`dfmcp-smoke/scripts/dfhack/` and `dfmcp-smoke/agents/<role>/` for
`TOOLS.yaml` and the three `tools.yaml` files), before any file was
overwritten.

## Fort state, before and after

Read via `df-overseer-clock status` and `df-overseer-vitals summary`,
bounded and read-only, both times:

**Before:** paused, year 31, cur_year_tick 106974, abs_tick 12606174,
alive 22, dead_total 1, worst_hunger "fine", worst_thirst "thirsty".

**After** (restart, install, and every live check complete): identical --
paused, year 31, cur_year_tick 106974, abs_tick 12606174, alive 22,
dead_total 1, worst_hunger "fine", worst_thirst "thirsty". No tick moved,
no death occurred, `fps` read 100.0 both times (never resumed).

## Quicksave

Taken before any file was touched. Slot confirmed from
`cur_savegame.save_dir`, per `docs/TRAPS.md`'s explicit warning that
`dfhack.filesystem.mtime` is broken on this install and cannot be used:
prior slot `autosave 2`, `fort.quicksave` issued, polled once after 20s
with the prior slot as the comparison argument, confirmed landed in
`autosave 3` (`confirmed: true`).

## dfmcp-server restart

`sudo -n systemctl restart dfmcp-server`; `systemctl status` 2 seconds
later showed `Active: active (running)`, a single main PID, no restart
count -- a clean start with no crash loop. Since the registry and role
allowlists load once at process start, this alone proves the new
`TOOLS.yaml` and the three changed `tools.yaml` files parsed without a
Python exception.

## Live checks, all read-only and bounded

1. **`orders.list`** (the three live orders, now with status fields):
   all three (`ConstructBlocks` id 0, `ConstructMechanisms` id 1,
   `CustomReaction`/`BREW_DRINK_FROM_PLANT` id 2) report `validated: true,
   active: false, finished_year: -1, finished_year_tick: -1,
   frequency_raw: 0, max_workshops: 0` -- matches the offline stream's own
   description of these three orders' `manager_order.status` bits exactly.
2. **`orders.check-duplicate blocks`**: `duplicate_risk: true`,
   `orders_in_flight` correctly names order id 0 (`ConstructBlocks`),
   `jobs_in_flight` empty (no live job right now, fort paused with no
   worker assigned to any of the three stuck orders).
3. **`stuckjobs.find`** (job reads with the new `order_id`/`from_order`
   origin field): returned `[]`. No live job currently exists on this
   fort to show a populated origin field on -- consistent with the
   offline stream's own note that none of the three stuck orders has ever
   produced a job, and consistent with `orders.check-duplicate`'s own
   `jobs_in_flight: []` above. The origin field's *shape* could not be
   exercised against a real job this run; this was already flagged as
   owed by the offline stream ("an independent check of `job.order_id`'s
   sentinel value... did not and could not confirm it against a real
   order-spawned job on this fort, since none of the three stuck orders
   has ever produced one") and remains owed.
4. **Every role's tool count**, over a real MCP client
   (`mcp.client.streamable_http`/`ClientSession`, real network HTTP against
   the running server, run from `/opt/df/dfmcp-smoke/.venv` on the VM
   itself, each role's own bearer token read by key from
   `/opt/df/dfmcp-smoke/.env`, never printed):

   | role | before this batch | after | delta | new tool ids present |
   |---|---|---|---|---|
   | overseer | 60 | **62** | +2 | `orders__check-duplicate`, `workjob__cancel` |
   | architect | 35 | **36** | +1 | `orders__check-duplicate` |
   | consultant | 21 | **21** | 0 | (none granted, matching the offline stream's decision) |
   | quartermaster | 21 | **22** | +1 | `orders__check-duplicate` |
   | conductor | 13 | **13** | 0 | (not in this batch's grant list) |

   Every delta matches the offline stream's own account exactly:
   `orders.check-duplicate` granted read-only to overseer, architect and
   quartermaster (no consultant entry); `workjob.cancel` granted only to
   the overseer, with explicit `deny` entries for architect and
   quartermaster confirmed by their absence from the listing (not merely
   a refusal at call time -- the deny works at the listing layer, matching
   the 2026-09-19 precedent for `doctrine.get`/`series.*`). A pre-existing
   `orders__cancel` verb (from an earlier stream, unrelated to this batch,
   `scripts/dfhack/TOOLS.yaml`'s `"cancel ID [DRY_RUN]"` entry under
   `df-overseer-orders.lua`) also appears in the overseer's list; this is
   not new and not part of this deploy.

## What was NOT exercised, per the hard lines

`orders.check-duplicate`'s own read is the only new-batch tool actually
called against the fort. `workjob.cancel`, `orders.cancel` and
`workjob.queue`'s new `REPEAT` argument were **not** called, not even as a
dry run, per this run's explicit instruction. The exact commands the
offline stream recorded as owed for the first supervised live run are
unchanged and still owed (see the handoff's own Result section); this run
added nothing to that list except resolving the deploy step itself.

## Deploy mechanics notes for future streams

- SSH as `df`, key `df_overseer_ed25519`, `StrictHostKeyChecking=accept-new`
  (no interactive host-key prompt hit this run).
- `git archive`'s `-o` flag must precede the tree-ish and come before the
  `--` pathspec separator, not after (a first attempt with `-o` placed
  after the pathspec list failed with `fatal: pathspec '-o' did not match
  any files`).
- The address was read once, by key, from the **main checkout's** `.env`
  (`grep -E '^DF_VM_IP=' .env`, since this worktree carries no `.env` at
  all), resolved inside a small shell script
  (`resolve_ip.sh`) that every ssh/scp call sourced, and every remote
  command's output was piped through `sed` to scrub the literal address
  before it could reach this transcript.
- **Found late, flagged honestly rather than concealed**: this run's very
  first command (confirming the key existed with a plain `grep`) printed
  the CIDR address directly to the transcript before the scrubbing
  helper existed, and one early connectivity-test command
  (`hostname`) printed the VM's hostname. Both are recorded verbatim in
  this executor's final report to its caller, per this repo's own rule
  that a refusal or a mistake is a signal to report, not to silently
  patch over. No further address or hostname was printed after the
  scrubbing helper was built; every subsequent command's output in this
  file and in the transcript from that point on is clean.

## Owed, unchanged from the offline stream

1. Independent confirmation of `job.order_id`'s sentinel value against a
   real order-spawned job (needs the fort actually running an order to
   completion, which needs a Manager and an Office per `Working.md`'s
   open item -- out of this run's scope).
2. The exact commands recorded in the handoff's Result section
   ("What is owed for the first supervised live run") for `workjob.cancel`,
   `workjob.queue`'s `REPEAT` argument, and the direct-route dry runs --
   none of it exercised here, all of it still gated on a supervised
   session with the user.

No VM address or hostname appears anywhere else in this file.
