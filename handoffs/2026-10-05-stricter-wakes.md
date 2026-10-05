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

### Plan (committed before building)

Today: `conductor/policy.yaml` `wake_reasons` name the roles each reason wakes.
`routine_review`, `prediction_due`, `prediction_graded`, `season_change`,
`migrant_wave` wake both advisors; `stuck_job`, `stock_below_target`,
`vital_nearing_threshold`, `caravan_present`, `stalled_order`, `blocked_order`
wake the Quartermaster only. `prediction_graded` fires on any graded count
(hit or miss), which is why both advisors woke nearly every cycle.

What the conductor can observe today (and what it cannot):

- Observable: each role's own `diff.since` drain (event types JOB_COMPLETED,
  UNIT_DEATH, REPORT, announcement_slow, the migrant/caravan/season/stock
  types); `queue.grade` (graded entries carry prediction id and status only);
  `queue.overview` (pending proposal and ask ids, no proposer); the stuck-job
  watch (job type is the first field of each job key); the order watch;
  threshold alert reads.
- NOT observable: a new landmark (no landmark read on the conductor's
  allowlist; `agents/` is outside this stream's surfaces); who proposed a
  graded prediction (`queue.grade` omits the record id); who proposed a ruled
  proposal (`queue.overview` has ids only).
- Substitutes: a landmark change is approximated by dig and construction
  completions in the Architect's own drain; a graded miss wakes both advisors
  (hits wake nobody); a proposer is learned by diffing `queue.overview`
  before and after each advisor run (new pending ids belong to that advisor),
  and a ruling is a learned proposal leaving the pending list.

Build: lane triggers as data (`lane_triggers:` in `policy.yaml`, parsed in
`policy.py`), evaluated by a new module `conductor/lanes.py` (new file, no
shared surface) holding the pure matching and a small state file
`lane_state.json` beside the cursor store (alert edge state, proposer map,
pending per-role lane flags cleared when that role completes a run).
`cycle.py` only builds signals from it; `triage.py` gains per-role carried
roles on `stuck_job` and a generic `lane_wakes` signal. Pause watchdog,
tripwire, hold and Overseer paths are not edited.


### Built

Lane triggers as data (`lane_triggers` in `conductor/policy.yaml`, parsed by
`conductor/policy.py`), evaluated by new `conductor/lanes.py`; state in
`lane_state.json` beside the cursor store. `triage.py` gained `LaneWake`,
per-signal roles for `stuck_job`, and a miss-only `prediction_graded`.
`cycle.py` changes are signal building plus a proposer-attribution step after
each advisor run. Pause watchdog, tripwire, hold, Overseer and Consultant
paths are not edited.

Triggers and what each reads:

- Architect: JOB_COMPLETED events in its OWN drain whose detail matches
  dig, channel, carve, smooth, engrave, construct, build or detail (the
  stand-in for a new landmark); a due stuck job of those kinds (stuck-job
  watch); a ruling on a proposal it filed.
- Quartermaster: `stock_below_threshold` diff events; a threshold alert newly
  crossed (alert reads, edge-triggered in `lane_state.json`); a due stuck job
  of a production kind; a ruling on a proposal it filed. Orders: the existing
  stalled and blocked order watch still wakes it (unchanged).
- Both advisors: `prediction_graded` only for a graded MISS (`queue.grade`
  `graded[].status == graded_false`); `migrant_wave`; routine review.
  `season_change` now wakes the Quartermaster only.
- Consultant, Overseer: unchanged.

Not observable by the conductor, and the substitute:

- A new landmark: no landmark read on its allowlist, and `agents/` is outside
  this stream. Dig and construction completions stand in.
- The proposer of a graded prediction: `queue.grade` omits it, so a miss wakes
  both advisors rather than only the proposer. Narrowing needs the grade
  result to carry the prediction's role (a `dfmcp` change).
- The proposer of a proposal: `queue.overview` has ids only. The conductor
  attributes a new pending id to the advisor whose run added it (re-reading
  the overview after each advisor run); a proposal filed by anyone else, or
  before this deploys, is never attributed and so never wakes its author on a
  ruling. Rulings are detected as a learned id leaving the pending list (a
  deferral stays pending).
- A due stuck job matching no lane wakes nobody; the routine review is its
  backstop.

Tests: new `conductor/tests/test_lane_wakes.py` (21: each lane trigger wakes
only its role, hit wakes nobody, miss wakes the advisors, alert once until it
clears and re-crosses, failed read is not a clear, an unserved alert survives
a failed run, ruling wakes only the proposer once, routine review wakes all,
quiet cycle wakes nobody). One existing test moved its stuck job from a Bed to
a brew (a Bed is now the Architect's). Full ambient `python -m pytest`: 2846
passed, 3 skipped. `dfmcp/tests` in `.venv-dfmcp`: 828 passed.

Deploy target: `vm106-conductor` (conductor code and `policy.yaml`). Not
deployed. Live check: count wakes per role over a window of cycles from the
cycle archives (`summary.json` `roles_woken`) against the 2026-10-05 baseline
(advisors on nearly every cycle); expect advisor wakes only with a lane
change, a miss, a migrant wave, or the 7-day review.
