# Handoff: stricter, lane-specific wakes

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline; read-only on hosts;
no deploys.** User's call: register 2026-10-05, "Stricter wakes".

## Why

Live today (`evals/live/2026-10-05-execution-stage-0/README.md`): the
Architect and Quartermaster woke on `prediction_graded` nearly every cycle,
each run 3 to 10 minutes of mostly reasoning, and the Architect re-proposed
bedrooms that were accepted and dug that morning. Waking a role when nothing
in its lane changed is the biggest avoidable cost and time.

## The rule

- A role wakes only on a change in its own lane since its last completed run.
  Starting triggers (refine in the plan from what the conductor can actually
  observe today: diff events, the stuck-job watch, the order watch, threshold
  alerts, queue state):
  - Architect: a new landmark, a dig or room-phase job completing, a ruling
    on its own proposal, a stuck job of a construction or dig kind.
  - Quartermaster: a threshold alert newly crossed, an order stalling, a stuck
    job of a production kind, a ruling on its own proposal.
  - Consultant: unchanged (open asks).
  - Overseer: unchanged (pending proposals, accepted not yet carried out,
    tripwire, pause paths).
- `prediction_graded` wakes only the proposer of a graded prediction, and only
  when it missed. Hits are recorded, nobody wakes.
- The routine review still wakes every role every
  `routine_review_interval_game_days` (now 7), so nothing goes unchecked long.
- Lane triggers held as data in `conductor/policy.yaml` (event kinds and
  signal names per role), not branches per role in code. "Newly crossed" means
  edge-triggered: the same crossed threshold does not re-wake every cycle.

## Tasks (commit after each)

1. Plan in the Result section: today's wake reasons and who they wake
   (`conductor/policy.yaml`, `conductor/triage.py`, `conductor/cycle.py`
   signal building), what each lane trigger reads, what needs per-role
   "since last run" state and where it lives (the cursor store already tracks
   per-role cursors).
2. Build, keeping the pause watchdog, tripwire, hold and Overseer paths
   untouched.
3. Tests: each lane trigger wakes only its role; a graded hit wakes nobody, a
   miss wakes only its proposer; an alert wakes once until it clears and
   re-crosses; routine review still wakes all; a quiet cycle wakes nobody.
4. Result: built, tests, deploy target (`vm106-conductor`), and the live check
   (count wakes per role over a window, compared with today's).

## Rules

- First step: `git merge --ff-only main`. Commit plan early and after each
  milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `conductor/triage.py`, `conductor/cycle.py` (signal
  building only), `conductor/policy.yaml`/`policy.py`, `conductor/tests/`,
  `web/stream/site-text.yaml` (wake titles only, if a reason is added), this
  handoff. Not `briefing.py`, `pause_watch.py`, `hold.py`, `runner.py`,
  `dfmcp/`, `dfqueue/`.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution lines
  in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` green.

## Result

(executor fills this in)
