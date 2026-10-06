# Handoff: wake the Quartermaster when a planned building waits on an item nobody makes

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`. **Dispatch after the P0 bedroom alert
merges** (both touch `conductor/policy.yaml`).

## Why

`evals/live/2026-10-07-stuck-bed/README.md`: the fort's only Bed is a
buildingplan-planned building waiting 38 game days for a BED item that never
existed. Nobody ever queued `ConstructBed`, although a Carpenter's Workshop,
24 wood and 2 carpenters were there. The Overseer deferred four bedroom
proposals meanwhile. User's call 2026-10-07: add a general signal, not a bed
fix.

## Scope

A conductor watch modelled on `conductor/ore_watch.py` (and
`order_watch.py`/stuck-job watch for the polling pattern):

- **Signal:** a planned building (buildingplan) needs item kind X, X has 0
  available (free) in the fort, and no active job or manager order produces
  X. Wake the **Quartermaster** with reason `unsupplied_building`, one line
  per item kind: the kind, how many buildings wait, the longest wait, and
  the producing job(s) and workshop kind the game data names (for BED:
  ConstructBed at a Carpenter's Workshop).
- **Generalisable:** item kind to producing job/workshop comes from game data
  (the job/reaction product tables `workjob.list-jobs` already reads), never
  a per-item table in code. If a needed read does not exist (for example a
  list of planned buildings with their unmet item filters), add it to the
  right Lua tool as a read-only command with TOOLS.yaml data, coordinate-free.
- Edge-triggered like the lane alerts (wake once when it appears, again
  only after it clears and re-appears); suppressed under an operator hold
  like the other watches if they are.
- Quartermaster charter: one line naming the wake and the expected
  response (queue the producing job or order), only if the charter does not
  already cover it.
- Add a gotcha/doctrine-style note only if there is an existing home for
  "BED 0 plus a suspended Bed means missing supply"; do not invent a store.
- Tests: fires for a planned building with no supply; silent when a job or
  order produces the item, or when the item is available; edge behaviour;
  an unreadable read drops the line rather than waking.

## Rules

Touched surfaces: new `conductor/<name>_watch.py`, `conductor/cycle.py`
(wiring), `conductor/policy.yaml`/`policy.py` (if it needs policy),
`scripts/dfhack/` (one read command if needed) and `TOOLS.yaml`,
`agents/conductor/tools.yaml` (if a new read), `agents/quartermaster/role.md`
(one line), tool-count docs/tests, tests, this handoff. Public repo: no
hostnames, IPs or tokens. No em dashes. No attribution lines. Commit after
each milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md.
Full ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets)
