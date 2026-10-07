# Handoff: wake cleanup, notes instead of wakes

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`. **Dispatch after the P0 bedroom alert
and the unsupplied-building watch merge** (all touch `conductor/policy.yaml`).

## Why

User's call 2026-10-07: review every wake; some are overkill, some should be
warnings not wakes. `research/2026-10-07-wake-audit.md` is the spec: follow
its section 3 classification, section 5 mechanism and section 6 order.
Biggest live costs: a deferred proposal re-wakes the Overseer every cycle
(queue_pending is a level trigger), and one fact (drink 0) produced five
wake kinds and nine Quartermaster runs.

## Scope, in this order, a commit per item

1. `queue_pending` becomes an edge: a proposal already ruled `defer` with
   nothing changed since is a note, not a wake (define "changed" from the
   audit: new citation, new answer, or the defer's own condition named).
2. Delete the dead reasons (season_change, migrant_wave, caravan_present
   event paths, prediction_due, hostile_seen_unreachable stub, the
   Quartermaster stock_below_threshold lane event). Leave the seasonal tick
   computation to the Planner stream.
3. Renotify in wakes, not ticks: exponential backoff, `stalled` after 3,
   for stalled_order/blocked_order (merged into `order_attention`),
   stuck_job, ore_exposed and alerts.
4. The notes channel (audit section 5): per-reason `delivery: wake | note |
   log | wake_once_then_note`, `fact`, `acts_with` (validated at policy load
   against `agents/<role>/tools.yaml`), `mandatory`, `escalate_after_shows`;
   a `notes:` block with a line cap and `ttl_cycles`/`max_shows` defaults;
   coalesce one wake per (role, fact) per window; record every wake reason
   per role run (fix `triage.wake_for` keeping only the first).
5. Apply the classification as data: the WARNING and MERGE rows.
6. `prediction_graded` wakes only the proposer.
7. Retire the Architect routine_review and JOB_COMPLETED lane event only if
   `step_done` is live for rooms; otherwise leave them and say so.
8. The answer wake (audit finding 7): an answered ask wakes the asker once
   (or a note if the asker has a pending wake anyway).

Keep: tripwire, unexplained pause, open asks, step_done/attention, alerts as
the single owner of a stock fact. The operator hold's effect on optional
wakes is an open user question: do not change hold behaviour.

## Rules

Touched surfaces: `conductor/` (policy.yaml, policy.py, lanes.py, triage.py,
cycle.py, briefing.py, the watches), `dfqueue/store.py` (grade proposer,
defer-change test) if needed, `docs/AGENT-LOOP.md`, tests, this handoff.
Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
lines. Commit after each milestone. Do not write Working.md, DECISIONS.md,
memory or INDEX.md. Full ambient `python -m pytest` (lupa on PYTHONPATH) and
`dfmcp/tests` in `.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets and what was left)
