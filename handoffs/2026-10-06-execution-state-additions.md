# Handoff: five `queue.execution_state` additions the executor needs

Date: 2026-10-06. **Executor, Sonnet, worktree. Offline; no deploys.**

## Why

Stage 2D (`handoffs/2026-10-06-stage-2d.md` Result, "Design problems") built
the execute phase against keys `queue.execution_state` does not return yet;
each is optional in the conductor, so today the phase idles. Needed before the
2b room cutover:

1. `to_open: [{ruling_id, role}]`: accepted routed rulings with no project.
2. `to_apply: [{proposal_id}]`: accepted or covered follow-ups not yet applied.
3. `issued_steps: [{project_id, step_id}]`: steps in `issued` state for the
   reconciler (today only counts exist).
4. Per open project `role` (store `open_projects` has it; the tool drops it),
   and per ready step its `tool` and `args` (the ore hold needs
   `args.phase` and `args.site`).
5. `routing: {routed_types, unrouted_types, frozen_types}` (the conductor on
   VM 106 cannot import `dfqueue`, so it learns the types over the wire).

Read the 2D Result for the exact shapes its conductor code expects
(`conductor/execute.py`) and match them; if the store lacks a query, add a
read-only one in `dfqueue/store.py` (reads only, no schema change).

## Tasks

Plan in the Result section; build in `dfmcp/executor_tools.py` (and
`dfqueue/store.py` read helpers if needed); tests for each key against a real
store fixture, including a conductor-side round trip with
`conductor/execute.py`'s parser if practical; Result with deploy target
(vm103-dfmcp).

## Rules

- First step: `git merge --ff-only main` (fall back to `git fetch origin &&
  git merge --ff-only origin/main`). Commit after each milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `dfmcp/executor_tools.py`, `dfqueue/store.py` (read-only
  query helpers only), their tests, this handoff. Not `dfqueue/feed*.py` or
  `web/` (another stream), not `conductor/` (report mismatches instead).
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution lines
  in commits. Do not touch the live fort.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

Built, offline, not deployed. Commit `86d0033` on branch
`worktree-agent-a62332fd53fe74732` (code and tests) plus this Result.

**Keys as built** (`queue.execution_state`, `dfmcp/executor_tools.py`; all
read-only; every one lines up with what `conductor/execute.py` reads):

1. `to_open: [{ruling_id, role}]`, from new `store.openable_rulings`: accepting
   ruling of a routed, non-follow-up proposal that has a step, above the
   effective cutover (none set means none listed), not closed, no project yet.
   `role` is the proposer. Mirrors `open_project_from_ruling`'s refusals.
2. `to_apply: [{proposal_id}]`, from new `store.applicable_followups`:
   follow-up accepted or covered, project open and not abandoned, proposal not
   closed, `after_step` in the plan, not already carried by a step. Mirrors
   `apply_followup`'s refusals.
3. `issued_steps: [{project_id, step_id}]`, from new `store.issued_step_ids`:
   steps of open routed projects with a target in `issued`; gone once observed
   done.
4. Open project entries now carry `role`; each ready step carries `tool` and
   `args` (copied from the current plan via new `store.current_plan_steps`, so
   amended follow-up steps are covered).
5. `routing: {routed_types, unrouted_types, frozen_types}`, from `dfqueue.routing`
   (frozen types computed in the tool; `routing.py` untouched).

The summary text also counts issued, to open and to apply.

**Mismatches with conductor/execute.py:** none blocking. Notes: `steps_open` in
`open_projects` is a bool, which the conductor's `int()` accepts; the existing
`test_execution_state_lists_ready_steps...` assertion was widened because ready
steps now carry `tool` and `args`. Not changed (out of surface): the cleanup
wake, the 240 s `step_done` timeout.

**Tests:** 8 new in `dfmcp/tests/test_executor_run.py` (each key, read-only,
and a round trip running `conductor.execute.run_execute` and
`conductor.briefing.routing_from_state` against the real tool: open, run,
observe done, apply follow-up). Ambient `python -m pytest` (lupa present):
3179 passed, 3 skipped. `dfmcp/tests` in `.venv-dfmcp`: 926 passed.

**Deploy target:** vm103-dfmcp (dfmcp plus dfqueue/store.py), before the 2b
room cutover; then vm106-conductor already reads these keys.
