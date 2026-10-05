# Handoff: conductor-executes stage 0, measure, stabilise, ship safety

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.** User's go-ahead for stage 0: register 2026-10-05,
"Conductor-executes design: the user's answers".

## Why

`docs/CONDUCTOR-EXECUTION.md` (revision 2, stage table row 0) and
`docs/CONDUCTOR-EXECUTION-REDTEAM.md` (pass 1 M7, pass 2 P2-L2). Before the
Overseer's turns are reshaped we need a baseline: cost, tokens, cache reads and
rounds per run on DeepSeek, and a stable prompt prefix so the cache can work.
The briefing's fixed stock lists were rejected by the user and must go before
the conductor ships again; the operator hold rides along.

## Tasks, in order (commit after each)

1. **Plan** in this file's Result section, after reading the design's stage 0
   row and section 3.1, `conductor/runner.py`, `conductor/cycle.py` (the run
   archive, around the `toolSummary` handling), `conductor/briefing.py`,
   `conductor/policy.yaml`/`policy.py`, `conductor/hold.py`.
2. **Archive usage.** Keep the openclaw envelope's `usage` and
   `assistantTurns` (or whatever the envelope really calls them; read the
   code that parses it, and say if a field is absent) in the per-run archive
   beside `toolSummary`, bounded. Derive per run: input, output, cache-read
   tokens, reasoning tokens if present, rounds. If `conductor.report` already
   carries run metadata to VM 103, add these as numbers there too, so the
   operator page can show them later (no web change in this stream).
3. **Fixed hostname.** Pass `--hostname <role>` (or the equivalent the runner's
   container launch takes) so the prompt prefix does not change per run.
   Check P2-L2 offline as far as the code allows: does a fixed hostname
   collide with openclaw's shared state directory or lock file across roles
   or concurrent runs? Say what you could and could not verify.
4. **Remove the fixed stock lists** merged earlier today
   (`handoffs/2026-10-05-better-briefing.md`): `briefing_extras` in
   `conductor/policy.yaml`/`policy.py` and the stock `facts` blocks in
   `conductor/briefing.py` and their wiring in `cycle.py`. Keep anything
   generic that a later stage uses only if the design says so. Remove the
   conductor's three stock read grants from `agents/conductor/tools.yaml` if
   nothing uses them any more, and update every hardcoded conductor tool count
   (expect back to 21; `dfmcp/tests/test_gotchas_tools.py`, docs).
5. **Operator hold** is already merged (`conductor/hold.py`); confirm its tests
   still pass with the above and that nothing in this stage changes it.
6. **Tests**, then a Result section: what was built, tests, deploy targets
   (expect `vm106-conductor`, plus `vm103-dfmcp` and `vm106-agents` if the
   allowlist changed), and the live check to run after deploy (dry-run cycle;
   one real advisor wake; read the archived usage; whether a second run reads
   cache tokens).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone; rate-limit cutoffs are routine.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, or `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `conductor/` (runner, cycle, briefing, policy, tests),
  `agents/conductor/tools.yaml`, `dfmcp/tests/test_gotchas_tools.py` (count),
  `dfmcp/conductor_tools.py` only if `conductor.report` needs the usage numbers,
  docs that state the conductor tool count, this handoff. Not `web/`,
  `dfqueue/feed.py`, `pause_watch.py`, `hold.py` logic.
- Host access read-only, and only if needed to see the openclaw envelope's
  real shape: `scripts/vm-ssh.sh openclaw` with
  `DF_ENV_FILE=c:/website-projects/df-automation/.env`. Read secrets by key
  only; never print tokens. No sudo or docker on hosts.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution lines
  in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

### Plan (written before building)

Findings that shape it, read from the code and from the committed live
envelopes (`evals/live/2026-09-15-overseer-first-ruling/run.json`, the
2026-09-24 consultant runs) and a read-only look at the agent VM:

- The envelope's keys are `ok, status, final, payloads, usage, costUsd,
  codeModeEngaged, assistantTurns, toolSummary, model, provider, sessionId`.
  `usage` is `{input, output, cacheRead, cacheWrite, reasoningTokens, total,
  cost: {total}}`. Cache-read tokens are present.
- The archive today writes `RunResult` minus `raw`, so `usage` and
  `assistantTurns` are dropped. Confirmed on the live archive: a recent
  `run-<role>.json` has only cost, error, final answer, ok, role, status,
  timed_out, tool_summary, wall clock.

Steps:
1. `runner.py`: `usage_from(envelope)` and `turns_from(envelope)`, total and
   bounded (numbers only, known keys only); new `RunResult.usage` and
   `assistant_turns`; carried through the cleanup-failed path.
2. `cycle.py` archive: write `usage` and `assistant_turns` in each run dict.
   Report them as numbers on `conductor.report` only if its schema already
   takes run metadata beyond the summary (checked in step 2).
3. `build_command`: `--hostname <role>`. Check the state-dir and lock question.
4. Remove `briefing_extras`, `BriefingExtras`, `build_facts` and the stock,
   order, availability and seed helpers, `_read_fact_sources`, `_facts_for`,
   and the `facts` argument; drop the three `stocks.*` grants from the
   conductor allowlist; update counts and docs.
5. Confirm hold tests; run the full suites; Result.

