# Handoff: a briefing that saves the agents their first ten lookups

Date: 2026-10-05. **Executor, Sonnet, worktree. Read-only on hosts; offline
build; no deploys.**

## Why (user agreed, 2026-10-05)

The Overseer's 2026-10-05 turn (run-0004) took 11 minutes. Its captured
thinking (`evals/live/2026-10-05-pause-safety/runs-public.json`) restates the
three proposals about four times and opens with a round of lookups (stock,
orders, a gotcha, landmarks, the Still's jobs, stuck jobs, labours) for facts
the conductor could have handed it. The briefing (`conductor/briefing.py`)
should carry what each role routinely looks up first, so turns start from the
facts instead of rediscovering them.

## Tasks, in order (commit after each)

1. **Measure first.** From the four runs in `runs-public.json` and VM 103's
   `dfmcp-server` journal for 2026-10-05 05:20 to 05:52 UTC (read-only:
   `scripts/vm-ssh.sh df 'sudo -n journalctl -u dfmcp-server --since ... --until ... --no-pager'`,
   `DF_ENV_FILE=c:/website-projects/df-automation/.env`), list per role
   which read tools were called, in what order, how often the same read
   repeated, and which of those results the briefing already carries. Write
   the table into this file's Result section. Do not copy addresses or
   hostnames from the journal into the repo.
2. **Plan.** Which facts go into each role's briefing (bounded, short lines,
   same caps style as the existing `stuck_jobs` block), where each comes from
   (the conductor's own MCP reads, as it already polls `stuckjobs.find` and
   `orders.list`), and the token cost. Prefer facts every role needs (drink,
   food, alive, worst hunger/thirst, stalled orders, stuck jobs, pending
   proposals with one line each) plus a small per-role extra, held as data
   in `conductor/policy.yaml` if it varies by role. Generic, never a rendered
   map (`docs/PURPOSE.md` commitment 1).
3. **Build** in `conductor/briefing.py` and its wiring; reads must be total
   (a failed read drops that line and the cycle carries on).
4. **Tests**, and the conductor's tool allowlist (`agents/conductor/tools.yaml`)
   if it needs a new read; update every hardcoded conductor tool count.
5. Result: what was built, the expected saving per role (lookups the
   briefing now answers), deploy targets.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/briefing.py`, `conductor/cycle.py` (wiring
  only), `conductor/policy.yaml`/`policy.py`, `agents/conductor/tools.yaml`,
  tests, docs that state the conductor's tool count, this handoff. Not the
  role charters, not `dfmcp/`, `dfqueue/`, `web/`, not `runner.py`'s
  thinking code, not `conductor/hold.py` or `pause_watch.py`.
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Result

(executor fills this in)
