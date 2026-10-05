# Handoff: a stuck-job watch the conductor can actually fire

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.**

## Why

The 2026-10-05 diagnosis (`handoffs/2026-10-05-why-jobs-sit-unclaimed.md`,
`evals/live/2026-10-05-stuck-jobs-diagnosis/`) found a Bed, two digs, a brew
and a Wall stuck for days with nothing able to notice:

- `stuck_job` in `conductor/policy.yaml` can never fire: `conductor/cycle.py`
  maps a `job_stalled` diff event to it, and nothing emits that event
  (`diff.lua` emits JOB_COMPLETED, UNIT_DEATH, REPORT, announcement_slow,
  UNIT_ATTACK only).
- The briefing (`conductor/briefing.py`) says it carries stuck jobs and does
  not.
- The Quartermaster, the only role `stuck_job` wakes, has no
  `stuckjobs.find` (Architect and Overseer do).

Stalled manager orders had the same "no event ever fires" shape and were
solved by polling: `conductor/order_watch.py`. Copy that pattern.

## Tasks, in order (commit after each)

1. **Plan, written here.** Read `conductor/order_watch.py`, its wiring in
   `cycle.py`, `conductor/briefing.py`, `scripts/dfhack/` stuckjobs tool output
   shape, and the new `conductor/pause_watch.py` (merged today; keep its
   early-return behaviour intact). Decide: what counts as stuck (unclaimed or
   suspended past a threshold in ticks, in `policy.yaml` as data), renotify
   cadence, how a job is keyed across cycles, and which role wakes (the
   Quartermaster for production jobs is the precedent; say if a dig or
   construction should wake someone else, and why).
2. **Build `conductor/job_watch.py`**: polls `stuckjobs.find` each cycle
   (no new game-side read unless the tool lacks a field you need; if so, say
   so and stop at the plan for that part), diffs against saved state, emits
   `stuck_job` wakes with a short detail line ("Bed construction suspended
   for 3 game days"). Remove or repoint the dead `job_stalled` mapping.
3. **Briefing digest**: a capped Tier 0 count and up to N short stuck-job
   lines in `build_briefing`, bounded like its other lists.
4. **Allowlist**: `stuckjobs.find` on `agents/quartermaster/tools.yaml`;
   update every hardcoded per-role tool count the tests and docs carry
   (grep for the Quartermaster's current 25).
5. **Wake title**: if you add a wake reason, give it a plain-English title in
   `web/stream/site-text.yaml` `wake_reasons` (that file only, nothing else
   in `web/`).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone; rate-limit cutoffs are routine.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/` (not `runner.py`'s thinking code, not
  `pause_watch.py` beyond wiring order), `agents/quartermaster/tools.yaml`,
  `web/stream/site-text.yaml` (wake title only), tests, docs that state tool
  counts. Not `dfqueue/feed.py`, `dfqueue/live.py`, `scripts/dfhack/`
  (unless the plan proves a field is missing, and then stop and report).
- Set intent, let the game execute: the watch reports and wakes; it never
  unsuspends, reassigns or cancels anything itself. No armok powers.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

The watch, digest and allowlist built with tests, the deploy targets listed
(expect `vm106-conductor`, `vm106-agents`, `vm103-dfmcp` for the allowlist,
and the web target if a wake title was added), and a Result section here.
