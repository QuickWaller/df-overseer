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

## Scope change, 2026-10-07 (orchestrator, user's direction)

Build items 1, 2, 3, 6, 7 and 8 only. **Do not build items 4 and 5 (the
notes channel and the WARNING rows as briefing notes):** briefing and inbox
structure is undecided (`research/2026-10-07-session-inbox-options.md`).
Where an item below says "a note, not a wake", implement it as "no wake"
(suppressed, logged at INFO with the reason) and leave a clear seam
(one function) where a future inbox or notes channel would hook in. Do not
add new briefing keys. The goal is that the conductor can run unattended
without re-waking roles every cycle on a running fort (at 100 FPS one game
day is 12 s, so tick-based renotify fires every cycle).

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

Branch `worktree-agent-a5e39f75446ab6474`, items 1, 2, 3, 6, 8 built, item 7
left, items 4 and 5 not in scope. No deploy; offline only.

Per wake reason, before and after:

| Reason | Before | After |
|---|---|---|
| `queue_pending` (Overseer) | level: any pending proposal woke it every cycle, a defer did not clear it | edge: wakes for a proposal it has not already left pending, when an ask open at the defer is answered, or after `overseer_defer_recheck_cycles` (12) conductor cycles. Seen-state and a persisted cycle counter in `lane_state.json`; `lanes.defer_changed` is the one place "changed" is defined; `split_pending_for_overseer` returns the quiet list (logged INFO), the seam for a future inbox. A proposal past the 8-proposal briefing cap is never recorded as seen. Not observable today: a new citation, a defer naming its own condition. |
| `prediction_due`, `migrant_wave`, `caravan_present`, `hostile_seen_unreachable`, `stock_below_target`, Quartermaster `stock_below_threshold` lane event, `EVENT_TYPE_TO_SIGNAL` entries | dead, could never fire | deleted (policy, `Signals`, triage, cycle). `season_change` kept: it is computed from the tick by plan_watch, only its dead diff-event path went. |
| `stalled_order`, `blocked_order` | renotify 1200 ticks (12 s real) | shared backoff, base 12000, doubling, stalled after 3 wakes; resets when the order stops being a candidate. Not merged into one `order_attention` reason (kept two reasons, one rule). |
| `stuck_job` | renotify 12000 ticks, unbounded | same backoff, stalled after 3, still listed in every briefing |
| `ore_exposed` | renotify 12000 ticks, unbounded | same backoff, stalled after 3, re-arms when mined |
| `alert_crossed` | edge only, never repeated | edge, plus renotify on the backoff while still crossed (base `alert_renotify_ticks` 12000), stalled after 3 |
| `unsupplied_building` | own backoff copy | now uses the shared `backoff.advance` (same behaviour) |
| `prediction_graded` | woke both advisors on a miss | wakes the proposer only: `queue.grade` graded rows (via `store.pending_due`) carry `proposer`. A row with no proposer (older server) falls back to both advisors; a proposer the build does not run (Planner while off) wakes nobody. |
| answered ask | no wake existed | `answer_ready`, once per ask, to the asker; learned like proposers. Lane flag `answers`, OFF for every role: no advisor has a read that returns an answer's text, so enabling it would send a role to look for something it cannot read. Enable per role once it can. |
| `routine_review`, Architect `lane_event` (JOB_COMPLETED) | unchanged | item 7 left: `step_done` has never fired live for rooms (rooms were routed in deploy 2b, 2026-10-07, supervised bedroom still owed), so the audit's condition is not met. |

Deploy targets when deployed: `vm106-conductor` (conductor code, policy.yaml)
and `vm103-dfmcp` (`dfqueue/store.py`, `grade.py`: the proposer on graded
rows). Deploy dfmcp first; the conductor falls back safely without it.
Existing `lane_state.json`, `job_watch.json` and cursor files load unchanged
(missing counters read as one prior wake).

Left: items 4 and 5 (notes channel, WARNING rows), item 7, the audit's
`acts_with` check and per-role wake budget, coalescing one wake per (role,
fact), recording all wake reasons per run, merging stalled/blocked into one
reason, and the hold's effect on optional wakes (unchanged).

Tests: full ambient `python -m pytest` and `dfmcp/tests` in `.venv-dfmcp` run
by the executor, results in the report. New: `conductor/tests/test_wake_cleanup.py`,
`test_wake_backoff.py`, `test_wake_proposer_answer.py`.

