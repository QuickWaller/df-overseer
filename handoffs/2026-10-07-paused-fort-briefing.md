# Handoff: every briefing says when the fort is paused or held

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git fetch origin && git merge --ff-only origin/main` (the own-filings
stream must be merged first; it edits `conductor/briefing.py`).

## Why

Live, 2026-10-07: on a paused, operator-held fort the Overseer read
"no worker assigned" on queued Carpenter jobs and every manager order
`active=false`, concluded both routes were broken, deferred a bed and
recorded a gotcha that the manager route is stuck. Its captured reasoning
loops ("wait... let me reconsider..."). No briefing says the fort is
paused: `conductor/briefing.py` has no pause or hold field. A paused fort
assigns no workers and runs no manager orders, which is normal.

## Scope

- A short fixed-wording `fort_state` line in every role's briefing
  (advisors, Overseer ruling briefing, Planner, Consultant), built by the
  conductor from what it already reads (clock state, pause watch, hold):
  - paused: "The fort is PAUSED. While paused no dwarf claims jobs and
    manager orders are not validated or run, so 'no worker assigned' and
    inactive orders are normal, not faults. Plan and rule for when it
    runs."
  - held (operator hold): add "An operator hold is on: nothing you accept
    executes until it lifts."
  - running: omit the line (or one short "running" word if the layout
    needs a constant key; keep the prompt prefix byte-stable before
    `game_tick`).
  Wording as policy data, not code.
- Overseer charter: one sentence under Known hazards: do not record a
  gotcha or defer on "stuck" jobs or orders while the briefing says paused.
- `gotchas.write`: refuse (server-side) a new gotcha while the fort is
  paused if feasible cheaply, or flag it `observed_while_paused`; pick the
  simpler, say which in the Result.
- Tests: the line appears paused/held, absent running; prefix stability;
  the gotcha rule.

## Rules

Touched surfaces: `conductor/briefing.py`, `conductor/cycle.py`,
`conductor/policy.yaml` (own small block), `agents/overseer/role.md` (one
sentence), `dfmcp/gotchas_*` only for the gotcha rule, tests, this handoff.
Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
lines. Commit after each milestone. Do not write Working.md, DECISIONS.md,
memory or INDEX.md. Full ambient `python -m pytest` (lupa on PYTHONPATH)
and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets)
