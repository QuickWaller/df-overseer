# Live run: deploy the generalised `workjob`, and queue the fort's first real direct job for a Chair

Date: 2026-09-23. Orchestrating session, user go-ahead: "yes deploy ad check".
Stream that built it: `handoffs/2026-09-21-workjob-generalise.md`.

## What was deployed

Five files, each hash-checked as **committed bytes** (`git -c
core.autocrlf=false show HEAD:<path>`), then again on arrival in `/tmp`, then
again at the installed path. All three readings matched for all five.

| File | sha256 (first 16) | Installed to |
|---|---|---|
| `scripts/dfhack/df-overseer-workjob.lua` | `3605b444f6f5b4db` | the game's DFHack scripts dir |
| `scripts/dfhack/TOOLS.yaml` | `c96f9db23599e4eb` | the dfmcp install |
| `agents/overseer/tools.yaml` | `50d3fe81ca42a0a1` | the dfmcp install |
| `agents/architect/tools.yaml` | `eb12308996b66e80` | the dfmcp install |
| `agents/quartermaster/tools.yaml` | `283b055680e9abfc` | the dfmcp install |

The previous copies of all five were backed up first, to a dated backup
directory, with timestamps preserved. `conductor` and `consultant` allowlists
were deliberately not touched and their hashes differ, as expected.

## Live checks, in the order they were run

1. **Quicksave before any fort action**, per the standing rule. Issued, then
   polled: the first poll returned `confirmed: false` (quicksave is
   render-loop gated), the second returned `confirmed: true` with
   `current_save_dir: "autosave 3"`, up from `"autosave 2"`. The slot comes
   from DF's own `cur_savegame.save_dir`, never a guess and never mtime
   (`docs/TRAPS.md`, the broken `dfhack.filesystem.mtime` entry).
2. **`list-jobs` against the Masons**, the new command, read-only:
   **19 jobs**, `read_failures: []`. Tokens include `constructthrone`,
   `constructblocks`, `constructcoffin`, `constructdoor`, `constructfloodgate`,
   `constructstatue`, `constructquern`, `constructmillstone` and three
   generated per-world `reaction:make_ent*` entries. The old tool knew three
   jobs in total, across all workshops.
3. **Dry run** of `queue constructthrone "Stoneworker's Workshop" true false 1`:
   `would_queue: true`, `job: ConstructThrone`, `job_name: "construct throne"`,
   `count: 1`, `read_failures: []`.
4. **The real job**, `DRY_RUN=false`: returned `job_id: 2249`, no refusal,
   `read_failures: []`. This is the first real (non-dry-run) direct job this
   tool has queued since it was generalised, and the first ever for a job kind
   that was not one of the original three tokens.
5. **Independent read-back**, not trusting the tool's own return value: walked
   the live job list directly and found `id=2249 type=ConstructThrone
   order_id=-1 repeat=false suspend=false`. **`order_id` is -1**, which is the
   correct value for a direct job: the tool did not invent a manager-order
   link it does not have (`df.job.order_id`, register 2026-09-23).
6. **MCP server restarted** so the three new role grants load. Clean start, no
   errors in its journal.
7. **Fort state before and after: identical.** Paused, year 31, tick 107874,
   100 FPS, tripwires armed. Nothing was unpaused at any point.

## What this does and does not prove about the role grants

The server **validates every role allowlist at startup** and refuses to start
on a grant naming a tool that does not exist in `TOOLS.yaml` (the error class
is `RoleValidationError`, observed directly while probing). It started
cleanly with the three new `workjob.list-jobs` grants and the new command in
the manifest, so both the manifest entry and the grants are internally
consistent as the server itself sees them.

**Not proven here:** an actual `tools/list` over a real MCP client as each
role, which would need a role bearer token. That was not done, so the tool
counts are not re-measured in this run. An attempt to load the registry and
roster ad hoc on the VM failed for an unrelated reason (that path loads only
`TOOLS.yaml` without the native tool set the server merges in, so
`queue.pending` and friends read as missing); that failure says nothing about
the grants.

## Open after this run

- **The job cannot progress while the fort is paused.** Job 2249 exists and is
  not suspended, but no Chair item can be produced until the fort runs. The
  built Chair from `evals/live/2026-09-23-office-and-first-real-build/` is
  still buildingplan-suspended waiting for exactly that item. Running a window
  needs its own go-ahead.
- `COUNT` and `REPEAT` were exercised at `1` and `false` respectively. Neither
  a multi-count queue nor a repeating job has been run for real.
- The five workshop kinds with no `getJobs` coverage are named in
  `scripts/dfhack/TOOLS.yaml`; none of them exists on this fort, so the gap
  was not exercised either way.
