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

(executor fills in)
