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

(executor fills this in)
