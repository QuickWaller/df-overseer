# Handoff: every proposing role sees its own filings, without asking

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`. **Part 2 waits for Planner P1b to merge**
(both edit `conductor/briefing.py`/`cycle.py`); do part 1 first and merge
origin/main before part 2.

## Why

Live, 2026-10-07: the Architect asked the Consultant (ask-0008) "what was
proposal-0024 ... I need to know my open proposals and their state", then
filed proposal-0026, a duplicate of the already-accepted proposal-0024.
Advisors see only pending ids (`conductor/briefing.py`, `cycle.py`) and no
advisor allowlist has a queue read (only conductor, consultant, overseer
hold `queue.pending`). Red team `research/2026-10-07-notebook-red-team.md`
finding 6. User's call 2026-10-07: agents should see the proposals they
need themselves, without asking someone or jotting notes.

## Scope

1. **Read tool** `queue.my_filings` (native, read-only, in `dfmcp/`): the
   calling role's own proposals (role from the credential, never an
   argument), newest first, each with id, type, summary, status (pending,
   accepted, rejected, deferred, closed, completed, in project N with step
   state), urgency, the latest ruling's decision and reason, linked
   project and close outcome; filters `status`, `proposal_id`, `limit`
   (capped). Grant it to every proposing role (architect, quartermaster,
   and planner) in `agents/<role>/tools.yaml`; update counts.
2. **Briefing block** "YOUR RECENT FILINGS" for each proposing role
   (server-built, like the Overseer's "DECIDED, DO NOT REDO"): the last N
   (policy data, small) of its own proposals with status and the ruling
   reason clipped; accepted-not-done and deferred ones always included.
   Placed after the stable prefix (cache: after `game_tick`, before the
   ask). A charter line: check it before filing; do not re-file what is
   accepted or in a project.
3. Tests: role isolation (a role never sees another's filings through the
   tool), statuses computed correctly for each lifecycle, caps, the block's
   placement keeps the prompt prefix byte-stable, the 10-07 duplicate
   (0024 then 0026) shows 0024 as accepted in the block.

## Rules

Touched surfaces: `dfmcp/queue_tools.py` (or a new module), `dfqueue/store.py`
read helpers, `agents/architect|quartermaster|planner/tools.yaml` and
`role.md` (one line each), `conductor/briefing.py`, `conductor/cycle.py`,
`conductor/policy.yaml` (own block), `docs/STATE.md`, count tests, tests,
this handoff. Public repo: no hostnames, IPs or tokens. No em dashes. No
attribution lines. Commit after each milestone. Do not write Working.md,
DECISIONS.md, memory or INDEX.md. Full ambient `python -m pytest` (lupa on
PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

Done offline, 2026-10-07 (executor, worktree; Planner P1b was merged first).

Part 1: `queue.my_filings` (native, read-only, `dfmcp/queue_tools.py`) over
`store.own_filings` (`dfqueue/store.py`). Role from the credential, no role
argument (an unexpected `role` is refused); newest first; filters `status`,
`proposal_id`, `limit` (default 10, cap 25). Statuses are computed, never
stored: pending, accepted (accepted, not executed, no project), rejected,
deferred, in_project (with the project's step state), completed (executed, or
project done), closed (a `close` naming the proposal, its ruling or its
project, with outcome and reason). Granted to architect, quartermaster and
planner (`tools.yaml`).

Part 2: the briefing key `your_recent_filings` (note plus capped lines),
placed straight after `game_tick`, built server-side. The conductor cannot use
the role-scoped tool, so a conductor-only native `queue.filings_brief` (roles,
recent) was added, backed by `store.briefing_filings`: the `recent` newest
plus every filing still pending, accepted, deferred or in a project.
`conductor/cycle.py` reads it per proposer (architect, quartermaster, planner)
before building the briefing; a failed read omits the block and never blocks
the role. Policy data: `conductor/policy.yaml` `own_filings.recent: 5`
(0 turns it off). One charter line each in the three `role.md` files.
Not implemented, per the orchestrator: need-to-know visibility changes.

Counts: architect 55, quartermaster 28, conductor 37 (the new conductor tool),
planner 13 once enabled; `docs/STATE.md` hand-edited, regenerate after deploy.

Deploy targets (not done): dfmcp-server on VM 103 (new native tools, the three
allowlists and the conductor allowlist, new `store` code), and the conductor
code and `policy.yaml` plus the three `role.md` charters on VM 106. The
openclaw role configs need no change (tool lists are server-side).

Tests: new `dfmcp/tests/test_my_filings.py` (all lifecycles, role isolation,
caps, grants, the 0024-then-0026 shape, conductor-only brief), briefing tests
(placement after `game_tick`, prefix byte-stable, cap), cycle tests (block
present; read failure omits it). Ambient `python -m pytest` with lupa: 3615
passed, 3 skipped, 0 failed. `.venv-dfmcp` `dfmcp/tests`: 983 passed.
