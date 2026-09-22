# Stream: the conductor service (agent loop MVP, items 3 and 6, plus a queue void)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** the MVP
build plan, 2026-09-22 ("go put a sonnet on those"; the conductor was named
as the last build stage). Offline only: **no VM, no deploy, no model call,
no push.** Sonnet executor, worktree-isolated.

## Why

`docs/AGENT-LOOP.md` is the design; read it in full, especially §1 (the
cycle), §2 (the clock policy), §4 (build items) and §7 (flags from the
earlier streams). Three streams have landed: the in-game clock, tripwires and
the `conductor` MCP role; queue execution, grading on demand, ask/answer and
the Quartermaster; Consultant retrieval. This stream builds the code that
runs the loop: it reads the fort, grades, triages, sets the clock, wakes the
roles as one-shot openclaw runs and archives everything. **No model is inside
the conductor.**

## First

`git merge --ff-only main` in your worktree (worktrees are cut from
`origin/main`; local `main` is well ahead). Then read the Result sections of
the three `handoffs/2026-09-22-loop-*.md` streams: they describe exactly what
exists and what was deliberately deferred.

## Read first

`docs/AGENT-LOOP.md`; `docs/AGENT-ARCHITECTURE.md` §4-§6 and §9;
`docs/MEMORY-ARCHITECTURE.md` ("the overseer is not a long-running
conversation": fresh context per run); `agents/*/role.md` and `tools.yaml`
for the four agent roles and `agents/conductor/`; `dfmcp/server.py`,
`dfmcp/auth.py`, `dfmcp/queue_tools.py`; `dfqueue/grade.py`
(`run_grading_cycle`), `dfqueue/store.py`; `scripts/dfhack/TOOLS.yaml` for the
`clock.*`, `fort.quicksave`, `vitals.summary`, `diff.since`, `overview.get`
entries; `evals/live/2026-09-15-overseer-first-ruling/` (`README.md`,
`pinned-config.json`, `charter-bootstrap.md`: exactly how a one-shot
`agent exec` was run on VM 106, including the traps it hit);
`research/2026-09-18-openclaw-capabilities.md`; `docs/TRAPS.md`.

## What to build

1. **A `conductor/` Python package** (name as you justify; not `queue` or
   `mcp`, see `CLAUDE.md`) that runs on VM 106 as a systemd service and talks
   to dfmcp on VM 103 **only over MCP**, with `MCP_ROLE_TOKEN_CONDUCTOR`.
   - **The cycle** (`docs/AGENT-LOOP.md` §1): read (vitals, `clock.status`,
     `diff.since` per role cursor, queue state), grade, triage, advise
     (architect, quartermaster), consultant (only on open asks), overseer
     (only when the queue holds something for it), quicksave before the
     Overseer runs whenever it may act.
   - **Triage rules and the clock policy as data** (one YAML config file):
     wake reasons, their clock level, thresholds, the routine-review interval
     in game days, `base_fps`, `think_fps`, the ticks-to-consequence multiple.
     Implement the §2 rule: slow only when ticks to a computable consequence
     fall under the configured multiple of expected thinking time in ticks;
     the fallback table otherwise; the most urgent live reason wins; restore
     `base_fps` when nothing urgent is being deliberated. Expected thinking
     time starts as a config value and is **measured** from each run's
     wall-clock and updated (a moving figure, logged).
   - **Tripwires:** poll `clock.status`; on a latch, wake the Overseer with
     the latch detail; `clock.clear` and `clock.resume` only after the
     Overseer's run completes, and never if it escalated to the human.
     Re-assert the frame cap and re-`arm` the watcher after a game restart.
   - **The briefing** (item 6): Tier 0 only, rendered per role into the
     run's prompt: vitals, what changed since that role last woke, queue
     items relevant to it, why it was woken. Must not grow with fort size.
   - **Launching a role:** one `docker run --rm ... agent exec --json` per
     role per cycle, fresh context, charter from `agents/<role>/role.md` as
     the workspace `SOUL.md`, following the 2026-09-16 run's mechanism and
     its recorded traps. Timeout per run. Secrets only by environment or
     `--env-file`, never argv or a tracked file.
   - **Archive:** each cycle under a gitignored `runtime/` directory: the
     briefing, each run's JSON envelope, cost, wall-clock, and the clock
     changes made. A daily cost total in the log (no spend cap: the user's
     standing call).
   - **Status and alerts:** a status JSON (state, last cycle, clock level and
     why, latched tripwire) and journald lines. An escalation from the
     Overseer leaves the fort paused and says so loudly.
   - **Dry-run mode:** prints what it would read, wake and change, without
     calling any model or changing the clock.
2. **Grading reachable over MCP.** The queue database lives on VM 103 and the
   conductor on VM 106, so add a conductor-only native tool that runs
   `run_grading_cycle` and returns what was graded and what is unexecuted.
   Idempotent. Grant it in `agents/conductor/tools.yaml`.
3. **A void mechanism for the queue** (register 2026-09-22: the user chose to
   void `proposal-0001` with a note rather than grade it). Admin-only, by
   code, never an agent tool: a store function plus a CLI that marks a
   proposal's prediction `void` with a required note, keeps the record
   visible with its reason, and makes the grader skip it. Tested. **Do not
   run it against any real database**; the deploy runs it on VM 103.
4. **A systemd unit example** and an env-file example for the service
   (`infra/*.example`), no real values.
5. **Tests** with a fake MCP server and a fake agent runner: a quiet cycle
   wakes nobody and changes no clock; each wake reason picks the right
   level; a tripwire pauses, wakes the Overseer and clears only after; the
   ticks-to-consequence rule both ways; the briefing's size is independent of
   fort size; the Overseer is woken only when the queue holds something.

## Touched surfaces (yours only)

New `conductor/` package and its tests; `dfmcp/queue_tools.py` and
`dfmcp/tests/test_queue_tools.py` (the grading tool); `dfqueue/store.py`,
`dfqueue/grade.py`, `dfqueue/tests/` (the void); `agents/conductor/`;
`dfmcp/tests/test_roles.py` and `dfmcp/tests/test_server.py` (only where the
new grant forces it); new `infra/*.example` files; `.gitignore` (the
`runtime/` line); `dfmcp/README.md` and `dfqueue/README.md` (sections for what
you add); this doc and its `handoffs/INDEX.md` row.

## Hard lines

- No VM, no SSH, no deploy, no model call, no Docker run of openclaw. No push.
- Nothing secret in any file, commit, output or report.
- Do not write `Working.md`, `decisions/` or `memory/`.
- No em dashes in prose.
- **Commit after each milestone** and extend the Result section as you go.

## Done when

Both suites pass (ambient `python -m pytest`, baseline **1035 passed / 3
skipped**; `dfmcp/tests` in the main checkout's `.venv-dfmcp`, baseline
**604**), counts reported, and the Result section lists what was built, how
it was verified, the exact deploy steps (VM 103 and VM 106, including the two
openclaw agent entries and tokens that do not exist yet for the quartermaster
and consultant), and anything in the design you found wrong.

## Result

**DONE 2026-09-22, offline, no VM, no SSH, no deploy, no model call, no
Docker run of openclaw, no push.** Commits on this worktree's branch (see
`git log`, each one a milestone): dfqueue void mechanism; `queue.grade`
native tool; conductor policy/triage/briefing/cursors; conductor
archive/runner; runner charter threading; conductor mcp_client;
conductor/cycle.py (the full cycle); conductor status/config;
conductor/service.py; infra examples, READMEs, `handoffs/INDEX.md`.

### What was built

**1. `conductor/` (new package, `conductor/tests/` alongside it).**

- **`policy.py` + `policy.yaml`** -- the clock levels (`full_speed`,
  `slowed`, `paused`) and every wake reason's fallback clock and role(s) as
  data (`docs/AGENT-LOOP.md` §2/§4), never a literal-reason branch in code.
  `clock_for_reason` picks the computed ticks-to-consequence rule
  (`ticks_to_consequence_clock`) when a reason is `computable: true` and a
  real tick count was supplied, the table entry otherwise (§2: "the table
  is the fallback for wake reasons with no computable deadline").
  `most_urgent` implements "the most urgent live reason wins", and
  `update_expected_thinking_seconds` turns the config starting value into a
  measured, moving figure (an EWMA, never a plain overwrite) from each
  run's own wall-clock.
- **`triage.py`** -- pure triage over an already-read `Signals` snapshot:
  `triage(signals, policy)` never calls a tool itself. A default
  `Signals()` (a quiet cycle) always wakes nobody at `full_speed`. Ordering
  is fixed: advisors, then Consultant, then Overseer (§4). **Tripwires are
  deliberately NOT triaged here** -- a latched tripwire pauses the fort
  directly inside the game loop (§3) and `conductor/cycle.py` reads
  `clock.status`'s own latch and wakes the Overseer for it directly.
- **`briefing.py`** -- item 6, Tier 0 only (vitals, this role's own diff
  since last wake, queue state, why it was woken), with hard caps
  (`MAX_DIFF_EVENTS`, `MAX_QUEUE_IDS`) so the briefing's size is
  independent of fort size regardless of how large `diff.since`'s own event
  list or the queue's pending list happen to be that cycle -- proven with a
  5,000-event and a 9,000-proposal input, not just asserted.
- **`cursors.py`** -- `CursorStore`, one small JSON file
  (`{role: cursor}`), atomic write (temp file + `os.replace`), per-role
  `diff.since` cursor persistence (`docs/AGENT-ARCHITECTURE.md` §4: "each
  role keeps its own cursor"). Refuses (does not silently ignore) a corrupt
  file.
- **`mcp_client.py`** -- `ToolCaller` protocol; `FakeToolCaller` (fixed or
  callable-per-call results, records every call, used by every test in this
  package); `StreamableHTTPMCPClient`, the real implementation (`mcp.client
  .streamable_http` + `ClientSession`, one session per call, bearer token)
  -- **never opened against a real server in this stream.** The MCP SDK
  import is lazy, inside `call_tool` only, so every other conductor module
  imports with no SDK dependency. `tool_name()` re-implements
  `dfmcp.tools._tool_name`'s id-to-name rule (`"clock.status" ->
  "clock__status"`) rather than importing it, since this package talks to
  `dfmcp` only over the wire (a different host, per
  `docs/AGENT-ARCHITECTURE.md` §13).
- **`runner.py`** -- `RoleRunner` protocol (`run(role, prompt, *, model,
  timeout_seconds, charter=None)`); `FakeRoleRunner` (records every call,
  the double `conductor/cycle.py`'s own tests use); `DockerOpenClawRunner`,
  the real launcher matching `evals/live/2026-09-15-overseer-first-ruling/
  README.md`'s own mechanism exactly: one pinned openclaw config per role
  (each carrying its own `agents.defaults.systemAgent.agentId`, since
  `--agent` does **not** select the role for `agent exec` in a multi-agent
  config -- found the hard way in that run), secrets only via
  `--env-file`, `SOUL.md` written fresh before a run and removed after
  (success, failure, or timeout -- `try`/`finally`). **Hard line: no Docker
  run of openclaw anywhere in this stream, including tests** -- every
  `DockerOpenClawRunner` test injects a fake `subprocess_exec` that never
  starts a real process.
- **`archive.py`** -- `CycleArchive`: one directory per cycle under a root
  (`summary.json`, `briefings.json`, `clock_changes.json`,
  `run-<role>.json` per launched role) and a durable, accumulating daily
  cost total (`<root>/cost/<date>.json`).
- **`status.py`** -- an atomically-written status JSON (state, last cycle,
  clock level, latched tripwire, escalated) and journald-bound logging.
  **An escalation logs at `ERROR`**, unconditionally louder than a handled
  tripwire (`WARNING`) or an ordinary cycle (`INFO`) -- proven with
  `caplog`, not just eyeballed.
- **`config.py`** -- `ConductorConfig`/`config_from_env`/`load_config`: no
  default for anything naming a live host, an out-of-tree path, or a
  secret (same discipline as `dfmcp.server.ServerConfig`). A per-role model
  override (`CONDUCTOR_MODEL_<ROLE>`), defaulting to
  `deepseek/deepseek-v4-flash` for every role per `docs/AGENT-LOOP.md` §4.
  Its own tiny local `.env` reader, deliberately **not** importing
  `dfmcp.auth._read_dotenv`, since this service runs on a different host
  (VM 106) and this package otherwise depends on nothing from `dfmcp` at
  all.
- **`cycle.py`** -- `run_cycle(cycle_index, deps)`, the full sequence:
  read (Tier 0: `vitals.summary`, `clock.status`, `overview.get`,
  `queue.pending`, one `diff.since` per role), re-arm the tripwire watcher
  if it is somehow not armed (covers a game restart per §2/§3 without
  needing to detect the restart itself -- re-arming an already-armed
  watcher is documented as a safe no-op), grade (`queue.grade`, skipped in
  a dry run), triage, set the clock (`clock.set-speed`, only if it would
  actually change), advise/decide-and-act in roster order with a
  `fort.quicksave` immediately before the Overseer ever runs, and archive.
  **Tripwire handling is a separate, priority path**: on a live latch,
  only the Overseer wakes (at `paused`, overriding whatever ordinary
  triage would have said this cycle), quicksaved first, and
  `clock.clear`/`clock.resume` are called **only after** that run
  completes **and only if it did not escalate** -- proven for a clean run,
  a failed run, and a timed-out run, each a separate test. Dry-run mode
  performs every read (so the plan reflects real state) but calls no write
  tool, launches no role, and archives nothing.
- **`service.py`** -- `load_charters` (reads `agents/<role>/role.md` fresh
  every cycle, never cached, so an edited charter takes effect on the next
  cycle with no restart); `build_deps` (constructs the real
  `StreamableHTTPMCPClient`/`DockerOpenClawRunner` -- never called by any
  test, per the hard line); `run_forever(deps, ...)` (the loop itself, over
  an already-built `CycleDeps`, so its own loop/status/`--once` logic is
  fully tested against a fake `deps`); a `--dry-run`/`--once`/`--env-file`
  CLI, `python -m conductor.service`.

**2. `dfmcp/queue_tools.py`: `queue.grade`.** A new native tool id running
`dfqueue.grade.run_grading_cycle` over MCP (the queue database lives on VM
103, the conductor on VM 106, so a local import was never an option).
Idempotent. Bridges `run_grading_cycle`'s **synchronous**
`call_tool(tool_id, args) -> result` contract onto this module's own async
`_call_dfhack` by running the whole grading pass in a worker thread
(`asyncio.to_thread`) and, from inside that thread, handing each actual
DFHack call back to the SAME event loop via
`asyncio.run_coroutine_threadsafe(...).result()` -- never a second event
loop. Granted only in `agents/conductor/tools.yaml`; **not**
`sole_writer_only` (that flag means specifically "the roster's
sole_writer", a different restriction than "the conductor") -- restricted
by allowlist only, since grading never mutates fort state
(`NativeTool.mutates` is always `False`, the same class of write every
other `queue.*` native tool already makes). `dfmcp/tests/test_roles.py`'s
pinned conductor-tools assertion updated for the new grant.

**3. `dfqueue/store.py`: `void_prediction` + a CLI.** Marks a proposal's
prediction `VOID` with a required, non-empty note; the proposal's own
`records` row is completely untouched (still visible, still exported).
Refuses an empty note, an unknown proposal id, or a prediction already
graded or already voided. `dfqueue/grade.py` needed **no code change**:
`pending_due` already selects only `status = PENDING`, so a voided row is
skipped by every future grading cycle for free. The CLI
(`python -m dfqueue.store --db PATH --proposal-id ID --note "..."`) is
admin-only, by code, never an agent tool -- no role's `tools.yaml` can ever
grant it, because there is no MCP tool here to grant. **Not run against any
real database in this stream**; the deploy runs it once against VM 103's
live queue for `proposal-0001`.

**4. `infra/conductor.service.example` and `infra/conductor.example.env`**
(new). Undeployed, same "never enable before this checklist" convention as
`infra/dfmcp-server.service.example`.

**5. `.gitignore`**: a `runtime/` line for the conductor's own per-fort
operational archive (cycles, cost log, cursors).

**6. `dfmcp/README.md`**: fixed the `queue_tools.py` section, which had
said "Four MCP tools" since 2026-09-15 and was never updated through two
later streams that each added more (`queue.executed`/`ask`/`answer`) --
now names all eight, plus a new paragraph on `queue.grade`'s sync/async
bridge and why it is allowlist-only rather than `sole_writer_only`.
**`dfqueue/README.md`**: a new "Voiding a prediction" section.

### How it was verified

- **Every module above has direct, offline tests** (`conductor/tests/*.py`,
  121 files' worth of behaviour in 6 test modules plus `test_cycle.py`/
  `test_service.py`): policy (20 tests: both directions of the
  ticks-to-consequence rule, `most_urgent`, the real committed `policy.yaml`
  loading cleanly, a bad clock level refused at load time), triage (13:
  a quiet cycle wakes nobody, each wake reason's role(s)/clock, ordering,
  the Overseer/Consultant's own narrow wake conditions), briefing (5,
  including the two size-independence tests), cursors (9), archive (6),
  runner (18, including SOUL.md lifecycle across success/timeout/no-charter,
  and every `DockerOpenClawRunner` path via an injected fake subprocess
  exec that never starts a real process), mcp_client (6), status (8,
  including the escalation-logs-at-ERROR proof via `caplog`), config (17),
  **cycle (19: the handoff's own full test list -- see below), service
  (5)**.
- **`dfmcp/tests/test_queue_tools.py`** (5 new): `queue.grade` through the
  real `queue_tools.call()` path end to end (propose, rule, execute, then
  grade, with an "advancing overview" fake proving the async/sync bridge
  actually reaches DFHack through the injected `call_dfhack`), idempotency,
  the unexecuted-proposal report, argument rejection, and a storage-error
  refusal.
- **`dfqueue/tests/test_store.py`** (9 new): every `void_prediction`
  behaviour plus the CLI's stdout/stderr/exit-code contract.
- **Both full suites, before and after every commit.** Final: ambient
  `python -m pytest` **1175 passed, 3 skipped** (baseline 1035/3, +140:
  126 in `conductor/tests/`, 5 in `dfmcp/tests/test_queue_tools.py`, 9 in
  `dfqueue/tests/test_store.py`). `dfmcp/tests` run via the main checkout's
  `.venv-dfmcp` interpreter with this worktree as `cwd`
  (`/c/website-projects/df-automation/.venv-dfmcp/Scripts/python.exe -m
  pytest dfmcp/tests`, confirmed by `import dfmcp, conductor; print(...)`
  to resolve to THIS worktree's own packages, not the main checkout's):
  **609 passed** (baseline 604, +5).
- **Each of the handoff's own five test requirements, directly**:
  `test_a_quiet_cycle_wakes_nobody_and_changes_no_clock`; four
  `test_*_wakes_*`/`test_caravan_present_slows_*`/
  `test_vital_nearing_threshold_slows_*` cases for "each wake reason picks
  the right level"; `test_a_tripwire_wakes_the_overseer_and_clears_and_
  resumes_after_a_clean_run` plus its failed- and timed-out-run siblings
  and `test_a_tripwire_takes_priority_over_ordinary_triage_this_cycle` for
  the tripwire requirement; `test_ticks_to_consequence_close_in_slows`/
  `test_ticks_to_consequence_far_off_stays_full_speed` (both directions,
  unit-level in `test_policy.py`, exercised through a real cycle too via
  the stuck-job tests); `test_briefing_size_is_independent_of_the_number_
  of_diff_events`/`..._of_the_queue_size` (both directions, with 5,000 and
  9,000-item inputs); `test_overseer_not_woken_when_the_queue_is_empty`/
  `test_overseer_woken_and_quicksaved_before_running_when_the_queue_holds_
  something`.
- **Secret scan**: `grep -rEn "sk-[A-Za-z0-9]{10,}|Bearer [A-Za-z0-9]{10,}"`
  and a private-IPv4-literal sweep over every new/changed file in this
  stream -- zero hits beyond documented placeholders (`<vm-103-tailnet-
  addr>`) and `127.0.0.1` in tests (loopback, not real infra).

### Exact deploy steps

**VM 103 (dfmcp, the queue database):**
1. Redeploy `dfmcp` (`git -c core.autocrlf=false archive`, per CLAUDE.md's
   own trap) so `queue_tools.py`'s new `queue.grade` id is live; restart
   `dfmcp-server.service`.
2. Grant `queue.grade` to the conductor role: already done in this
   stream's `agents/conductor/tools.yaml` (part of the same redeploy --
   `dfmcp.roles.load_roster` is called at server startup, no separate
   step).
3. **Void `proposal-0001` before the conductor's first grading cycle ever
   runs** (`decisions/DECISIONS.md` 2026-09-22): on VM 103, with
   `dfmcp-server.service` stopped or the database otherwise not being
   written concurrently,
   `.venv-dfmcp/bin/python -m dfqueue.store --db /var/lib/dfmcp/
   Uniboslan.sqlite3 --proposal-id proposal-0001 --note "<the real,
   user-approved reason>"`. **Needs explicit user go-ahead per CLAUDE.md**
   (a live-state change to the real queue database) -- not run here.
4. Mint `MCP_ROLE_TOKEN_CONDUCTOR` (already placeholder-present in
   `infra/local.example.env`, from the clock/conductor-role stream) if not
   already minted, and place it in VM 103's `dfmcp-server.service` env
   file.

**VM 106 (openclaw + the new conductor service):**
1. **Checked directly against `infra/local.example.env` rather than
   trusting the handoff's own premise that both are missing**: it already
   carries placeholders for `MCP_ROLE_TOKEN_OVERSEER`,
   `MCP_ROLE_TOKEN_ARCHITECT`, `MCP_ROLE_TOKEN_CONSULTANT` and
   `MCP_ROLE_TOKEN_CONDUCTOR` (four lines, confirmed by `grep`). **Only
   `MCP_ROLE_TOKEN_QUARTERMASTER` is genuinely missing**, even though
   `agents/quartermaster/` was enabled by a sibling stream today -- a real
   gap, and the one token that must actually be minted before this deploy
   can run for real. Flagged as a line owed to `infra/local.example.env`
   below (not touched here, outside this stream's declared surfaces)
   rather than silently added.
2. Install a dedicated venv (`python -m venv --system-site-packages
   .venv-conductor` or similar) and `pip install` whatever
   `conductor/` needs (the `mcp` SDK, `pyyaml` -- a `conductor/
   requirements.txt` was not written this stream; it should mirror the
   relevant subset of `dfmcp/requirements.txt`, flagged as owed).
3. Create one pinned openclaw config per role under
   `CONDUCTOR_PINNED_CONFIG_DIR` (`architect.json`, `quartermaster.json`,
   `consultant.json`, `overseer.json`), each shaped like
   `evals/live/2026-09-15-overseer-first-ruling/pinned-config.json`
   (this repo's own working example) but with **exactly one** entry under
   `agents.entries` and `agents.defaults.systemAgent.agentId` set to that
   role, its own `mcp.servers.df-overseer.url` pointing at VM 103's real
   tailnet address, and `tools.allow` matching that role's real
   `agents/<role>/tools.yaml` grant (`openclaw mcp probe df-<role> --json`
   against the real server is the $0 way to confirm the tool count before
   any paid run, per every prior eval's own practice).
4. Fill in `infra/conductor.example.env` -> a real, gitignored
   `conductor.env` on VM 106: `CONDUCTOR_MCP_URL`,
   `MCP_ROLE_TOKEN_CONDUCTOR`, `CONDUCTOR_PINNED_CONFIG_DIR`,
   `CONDUCTOR_OPENCLAW_STATE_DIR=/opt/openclaw/config`,
   `CONDUCTOR_WORKSPACE_ROOT=/opt/openclaw`,
   `CONDUCTOR_SECRETS_ENV_FILE=/opt/openclaw/secrets/
   openclaw_secrets.env`, `CONDUCTOR_POLICY_PATH` (in-tree,
   `conductor/policy.yaml`), `CONDUCTOR_CURSOR_STORE_PATH`,
   `CONDUCTOR_RUNTIME_ROOT`, `CONDUCTOR_STATUS_PATH` (all three under
   `/var/lib/conductor`, created with the right ownership first).
5. Install `infra/conductor.service.example` ->
   `/etc/systemd/system/conductor.service`, filling in `User`/`Group`/
   `WorkingDirectory`/`EnvironmentFile`/`ExecStart`. **Add `--dry-run` to
   `ExecStart` for the first supervised run** and review its status JSON
   and journald output before removing it.
6. Confirm this account's own access to the Docker socket (every prior
   openclaw run on this host needed `sudo` for it,
   `research/2026-09-15-openclaw-secret-storage.md`).
7. **`systemctl start conductor.service` needs the user's explicit
   go-ahead, per CLAUDE.md, each time** -- not run here, and this stream
   was barred from it regardless.
8. Once dry-run output looks right: remove `--dry-run`, restart, and watch
   the first several real cycles' `journalctl -u conductor.service`
   output and `CONDUCTOR_STATUS_PATH` closely, given `docs/AGENT-LOOP.md`
   §5's own "known risk, accepted": most write tools have never done a
   real build, so early cycles will surface tool failures by design.

### Lines owed to files this stream does not own

- **`infra/local.example.env`**: add `MCP_ROLE_TOKEN_QUARTERMASTER=`
  (genuinely missing, see deploy step VM106-1 above) with the same
  commented style as the other `MCP_ROLE_TOKEN_*` lines.
- **`docs/AGENT-LOOP.md`** §7 "Open": most of that section's own bullets
  (grading reachable over MCP, the void mechanism, a systemd unit example)
  are now built by this stream and could be marked done; not edited here,
  since this doc is not in this stream's declared touched surfaces and no
  sibling stream claims it either.
- **`dfmcp/README.md`**'s `native_tools` paragraph (around "the queue,
  doctrine, series and gotchas natives") should also name
  `knowledge_tools` -- a gap the consultant-retrieval stream already
  flagged as owed to itself; left as found, not fixed here (unrelated to
  this stream's own edit to that same file).

### Anything in the design I think is wrong, or found wrong while building

1. **`queue.pending`'s role branch is keyed to the CALLER's own
   authenticated identity, never an argument** (`dfmcp/queue_tools.py`'s
   `_pending`: `if role == "consultant": ... else: pending_proposals`).
   The conductor authenticates as `conductor`, so it can only ever see
   `pending_proposals()` through this tool -- there is **no way, from the
   conductor's own token, to ask "is there an open ask for the
   Consultant?"** `Signals.open_ask_for_consultant` is therefore always
   `False` in this build, and the Consultant can currently never be woken
   by the conductor's own triage. This is a real, load-bearing gap, not a
   simplification: fixing it needs either a new native tool (a
   conductor-only "queue overview" returning both `pending_proposals()`
   and `open_asks()` regardless of caller role, the same pattern
   `queue.grade` already established) or a role-override argument
   restricted to the conductor. Deliberately not built here: this stream's
   touched-surfaces grant for `dfmcp/queue_tools.py` is scoped to "the
   grading tool," and adding a second, unrelated native tool id would
   exceed that scope without a fresh go-ahead.
2. **The conductor holds no hostile-reachability read at all**
   (`threat.scan` is advisor/overseer-only per every `agents/*/tools.yaml`
   today), so `hostile_seen_unreachable` is always `False` too, and
   whatever `diff.since` drains may or may not even carry a
   distinguishable event for it --
   `docs/AGENT-ARCHITECTURE.md` §4's own finding that `hostile_detected` is
   "dangerously narrow" applies with equal force to whatever the conductor
   itself could see. Not fixed here for the same touched-surfaces reason
   as gap 1.
3. **`clock.resume`'s (and every other `clock.*`/`fort.quicksave` tool's)
   own refusal shape does not surface as an MCP `isError`.** Read from
   source (`scripts/dfhack/df-overseer-clock.lua`'s `clock_resume`):
   `{"ok": false, "error": "...", "tripwire": {...}}`. `dfmcp/server.py`'s
   `_run_dfhack_tool` only treats a result as an error when it is
   **exactly** `{"error": "<string>"}`, a single key -- a three-key
   `ok`/`error`/`tripwire` object passes straight through as an ordinary,
   successful `isError=False` result. So the whole `clock`/`fort` family
   uses an `"ok"`-field convention that a generic MCP client (including
   this conductor) must check explicitly, never relying on the transport's
   own error flag. `conductor/cycle.py` does check it (`resume_result.get
   ("ok", False)`, logged at `ERROR` if false), but this is worth fixing at
   the source: either `dfmcp/server.py`'s special case should also
   recognise an `"ok": false` shape generically, or every `df-overseer-
   clock.lua`/`df-overseer-fort.lua` refusal should be changed to the
   plain `{"error": "..."}` shape every other DFHack tool in this repo
   already uses. Neither file is in this stream's touched surfaces; found
   and worked around here, not silently assumed correct.
4. **No established, tested contract exists for how the Overseer signals
   "I am escalating to the human" inside openclaw's own JSON envelope.**
   `agents/overseer/role.md` (not in this stream's touched surfaces) would
   need to define this. This stream's `_overseer_escalated` treats any run
   that did not complete cleanly (`ok=False` or timed out) as equivalent to
   an escalation -- conservative (never silently resumes past an unclear
   outcome) but a real gap: a run that completes cleanly and genuinely
   *should* have escalated (the model decided the situation needs a human,
   said so in its final answer, but the call itself succeeded) is currently
   NOT detected as an escalation unless the envelope happens to carry a
   literal `"escalated": true` key, which nothing sets today. Needs
   coordination with the Overseer's own charter/output contract before
   this is trustworthy for a real siege-class decision.
5. **`prediction_due` and `prediction_graded` collapse into one
   observable event.** `docs/AGENT-LOOP.md`'s own triage table lists them
   as two separate wake reasons, but `queue.grade`'s one call grades
   everything due in the same pass that discovers it is due -- there is no
   way, from this design's own tools, to observe "became due" separately
   from "was graded" (they are the same instant). This build folds
   `prediction_due` away (`Signals.prediction_due` is always `False`,
   `prediction_graded` carries the real signal) rather than inventing a
   distinction the underlying mechanism cannot actually make.
6. **`StreamableHTTPMCPClient` opens a fresh MCP session per tool call**,
   never a held-open one. Judged acceptable against the conductor's own
   cycle cadence (several calls per cycle, cycles roughly a minute apart
   per the default `CONDUCTOR_CYCLE_INTERVAL_SECONDS`), but this was
   **never measured live** (no VM this stream) -- the real per-call
   handshake overhead, and whether it matters at the conductor's actual
   read volume (up to ~9 reads plus writes per cycle: 4 `diff.since` +
   `vitals.summary` + `clock.status` + `overview.get` + `queue.pending` +
   `queue.grade` + any `clock.*`/`fort.quicksave` writes), is unknown.
   Worth measuring on the first real deploy before optimising either way.
7. **`conductor/requirements.txt` was not written this stream** (see
   deploy step VM106-2) -- `conductor/mcp_client.py` needs the same `mcp`
   SDK `dfmcp/server.py` depends on, `conductor/config.py`/`policy.py`
   need `pyyaml`; every other module needs nothing beyond the stdlib. A
   thin requirements file (or reusing `dfmcp/requirements.txt` wholesale,
   since this repo's Python packages already share one venv style) is a
   five-minute follow-up, not done here since it did not exist as its own
   deliverable in the handoff's own "What to build" list.
8. **The routine-review interval's "due immediately" behaviour on a
   never-reviewed fort** (`conductor/cycle.py`'s `_game_days_since`) means
   a freshly-deployed conductor's very first cycle always fires a routine
   review, waking both advisors, regardless of whether anything else is
   happening. This is very likely the right default (a fresh service
   should look the fort over once before settling into a cadence) but was
   a judgement call this stream made, not something `docs/AGENT-LOOP.md`
   states explicitly -- flagged rather than silently assumed obviously
   correct.
