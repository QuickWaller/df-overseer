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

Done offline, nothing deployed.

1. Structural duplicate refusal. `schema.step_identity(record)` builds the key
   (type, step tool, identifying args, phases); identifying args per tool are
   data in the new `dfqueue/step_identity.yaml` (a tool not listed compares on
   all its args; a step with none of its identifying args present is never
   structural). `store._find_structural_duplicate` runs inside `append` for
   proposals and refuses against any live proposal (pending, deferred, accepted
   not completed, in a project) from any role, naming it: "already proposed as
   proposal-0024 by the architect, accepted". Follow-ups (project_id or
   after_step) are exempt. The text near-duplicate rule is unchanged, still the
   softer `duplicate_of` flag. Tests in `dfqueue/tests/test_stage2a.py` include
   the 0024/0026 shape (paraphrase, accepted first); three existing tests that
   filed identical steps now vary the step (`room(n)`, `rig.open_room(purpose=)`).
2. Read answers: `queue.my_filings` takes `asks=true` and returns the caller's
   own asks with status (open or answered) and the answer's full text
   (`store.own_asks`; role filtered in the store). No tool added, so no tool
   count changes. `answers: true` is on in `conductor/policy.yaml` for
   architect, quartermaster and planner (the roles with queue.ask and
   queue.my_filings); the Overseer has no lane. The detection test that
   asserted "off by default" now sets the flag off explicitly.
3. Briefing nit: needed one code line, not template only: `conductor/briefing.py`
   rounded the per-citizen figure to 1 decimal before the template saw it;
   it now rounds to 2 (1 of 22 reads 0.05, 19 of 20 reads 0.95). Two test
   expectations updated. `briefing.py` was not in the declared surfaces; it is
   not in the other stream's list either.

Tests: ambient `python -m pytest` with lupa on PYTHONPATH, 3646 passed, 3 skipped;
`dfmcp/tests` in `.venv-dfmcp`, all passed after the open_room fix.

Deploy targets: dfqueue (store, schema, step_identity.yaml), dfmcp-server
(queue_tools, agents/*/tools.yaml notes), conductor policy.yaml and briefing.py
(VM 106). The role charters do not yet mention `asks=true`; an answer_ready
wake names the ask, and the tool description says where to read it.
