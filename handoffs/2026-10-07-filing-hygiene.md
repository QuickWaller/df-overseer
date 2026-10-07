# Handoff: structural duplicate refusal, and agents read answers to their asks

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git fetch origin && git merge --ff-only origin/main`.

## Why

1. Live 2026-10-07: the Architect filed proposal-0026, the same site-4
   finish as the already-accepted proposal-0024, and the Overseer accepted
   both. `evals/live/2026-10-07-wake-baseline/` found the server's text
   near-duplicate rule caught 0 of 5 real repeats (agents paraphrase); a
   structural rule (M1-struct in `dfqueue/wake_metrics.py`) caught 4.
2. The wake cleanup built an `answer_ready` wake but left it off: no
   advisor can read an answer's text (handoffs/2026-10-07-wake-cleanup.md
   Result, item 8). The Architect asked the Consultant (ask-0007/0008).

## Scope

1. **Structural duplicate refusal at filing** (`dfqueue/store.py`, schema
   if needed): refuse a proposal whose action is the same as an open one
   (pending, accepted not completed, deferred, in a project): same type and
   the same step tool with the same identifying arguments (site/handle/zone/
   workshop/job and item), across all roles. The refusal names the existing
   proposal, its role and status ("already proposed as proposal-0024 by the
   architect, accepted"). Identifying arguments per tool as data (for
   example from TOOLS.yaml execution data `handle_args`), not per-tool code.
   Follow-ups to a project (project_id/after_step) are not duplicates.
   Keep the text rule as a softer flag. Tests include the 0024/0026 case.
2. **Read answers**: extend `queue.my_filings` (or add the smallest read)
   so a role sees its own asks with the answer text and status. Then turn
   on the `answer_ready` lane flag for the roles that can ask (policy
   data), and update tool counts.
3. Briefing display nit: the bedroom alert text rounds 1/22 to "0.0 per
   citizen"; show two decimals or "1 for 22 citizens" (text template only).

## Rules

Touched surfaces: `dfqueue/store.py`, `dfqueue/schema.py`,
`dfmcp/queue_tools.py`, `conductor/policy.yaml` (answers flag, alert text
only), `agents/*/tools.yaml` if a tool is added, `docs/STATE.md`, count
tests, tests, this handoff. Public repo: no hostnames, IPs or tokens. No em
dashes. No attribution lines. Commit after each milestone. Do not write
Working.md, DECISIONS.md, memory or INDEX.md. Full ambient `python -m
pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets)
