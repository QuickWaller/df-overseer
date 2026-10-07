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

(executor fills this in, with deploy targets)
