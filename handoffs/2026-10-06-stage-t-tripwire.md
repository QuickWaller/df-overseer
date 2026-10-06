# Handoff: conductor-executes stage T, the tripwire sequence

Date: 2026-10-06. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.** User's calls: register 2026-10-05, "the user's answers to
the revision-2 questions" items 3 and 4.

## Scope

`docs/CONDUCTOR-EXECUTION.md` revision 4, section 6.6 item T and 4.5:

- `tripwire_owners` as data in `conductor/policy.yaml`: thirst and hunger wake
  the Quartermaster; hostiles wake the Overseer until a military role exists.
  An unknown cause wakes the Overseer.
- After a tripwire the fort resumes **only** on an explicit Overseer
  `pause.verdict` with `resume: true` from that run (the same verdict path the
  unexplained-pause branch already uses, `conductor/pause_watch.py`
  `finish_after_overseer`), never on a clean run. Today's tripwire branch in
  `conductor/cycle.py` clears the latch and resumes after a clean,
  non-escalated Overseer run: that changes. The owner's run (Quartermaster for
  thirst) happens first and may file proposals; the Overseer then rules and
  gives the verdict.
- A per-cause repeat counter: the same cause re-latching N times in a window
  escalates to the human alert instead of re-running the sequence (data in
  policy). Check whether the in-game tripwire watcher has hysteresis
  (`scripts/dfhack/` clock/tripwire script, read only) and say so.
- The operator hold still suppresses every resume; a pause the watchdog owns
  is unchanged.
- Overseer charter: one line on giving the verdict after a tripwire.

## Tasks (commit after each)

1. Plan in the Result section: today's tripwire branch, exactly what changes,
   how the owner wake and the Overseer verdict sequence within one cycle.
2. Build. 3. Tests: thirst wakes the Quartermaster then the Overseer; no
   verdict keeps the fort paused and alerts; `resume: true` resumes once with
   the tick verified; `false` keeps paused; hold suppresses resume; a repeat
   escalates; hostiles wake only the Overseer. 4. Result with deploy targets
   (vm106-conductor, vm106-agents) and the live check (a forced test tripwire
   on the paused fort, described step by step for the orchestrator, not run).

## Rules

- First step: `git merge --ff-only main` (fall back to `git fetch origin &&
  git merge --ff-only origin/main`). Commit plan early and after each
  milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `conductor/cycle.py` (tripwire branch), `conductor/pause_watch.py`
  (only to reuse the verdict path), `conductor/policy.*`, `conductor/triage.py`
  if owners need it, `conductor/tests/`, `agents/overseer/role.md` (one line),
  this handoff. Not `dfmcp/` (stage 2C is building there), not `dfqueue/`,
  not `scripts/dfhack/` (read only).
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution lines
  in commits. Do not touch the live fort.
- Full ambient `python -m pytest` and `dfmcp/tests` green.

## Result

### Plan (executor, 2026-10-06)

Today's tripwire branch (`conductor/cycle.py`, `_run_cycle`): on a latch it
quicksaves, runs the Overseer alone, and after a clean, non-escalated run
calls `clock.clear` then (unless held) `clock.resume`. Silence is consent.

What changes:

1. `policy.yaml` gains `tripwire_owners` (reason to owner roles; thirst and
   hunger: quartermaster; hostile_reachable: overseer; unlisted reasons, so an
   unknown cause: overseer) and `tripwire_repeat` (limit, window in game
   ticks). `policy.py` loads and validates both.
2. New `conductor/tripwire.py`: `TripwireStore` (a small JSON file beside the
   cursors) holding per-cause latch episodes keyed by (reason, latch tick), and
   the pure repeat-count check.
3. Sequence in one cycle: quicksave, owner run(s) (a `tripwire` wake, may file
   proposals), then the Overseer (ruling briefing over a fresh
   `queue.pending_brief`, so it sees what the owner filed). The Overseer's
   `pause.verdict` baseline is read just before its run.
4. Resume only on an explicit verdict: reuse `finish_after_overseer`. On
   `resume: true` and not held: `clock.clear` first (resume refuses under a
   latch), then `finish_after_overseer` resumes once with the tick verified. On
   a held fort with `resume: true`: clear, never resume (as before). No
   verdict, `false`, an escalation or an unclean run: the latch stays, the fort
   stays paused, a human alert is raised.
5. Repeat counter: a new (reason, tick) latch is recorded; when the same cause
   has latched more than `limit` times within `window_ticks` the cycle skips the
   sequence, alerts the human and leaves the latch standing.
6. Overseer charter: the verdict section also covers a tripwire.

### Result (executor, 2026-10-06)

Built offline; no deploy, no live call.

**New tripwire sequence** (`conductor/cycle.py` `_tripwire_cycle`):

1. Repeat check first. The latch is recorded as an episode keyed by
   (reason, latch tick) in `tripwire_state.json` beside the cursors, so a
   standing latch seen every cycle counts once. More than
   `tripwire_repeat.limit` (3) episodes of the same cause within
   `window_ticks` (4800 game ticks) means: no quicksave, no run, a human alert
   (the `pause_watch._alert` sink and the status block's standing alert), the
   latch and the pause left standing, and the same refusal on every later cycle
   for that latch. An unreadable counter file is treated the same way.
2. `fort.quicksave`, then the owners from `tripwire_owners` in order (thirst and
   hunger: quartermaster, with a `tripwire` wake and its normal briefing), then
   the Overseer with the ruling briefing over a fresh `queue.pending_brief`
   (so it sees what the owner filed) and a wake detail telling it to rule and
   then give its `pause.verdict`. `hostile_reachable`, any unlisted reason and
   an unknown cause: the Overseer alone. A failed owner run is logged and does
   not stop the Overseer. The `pause.verdict` baseline is read just before the
   Overseer runs.
3. Verdict through `finish_after_overseer` (reused; it gained an optional
   `what` argument so alerts say "tripwire thirst_critical", default unchanged).
   `resume: true`, not held: `clock.clear` first (resume refuses under a
   latch), then one `clock.resume` with the tick verified, an unmoved tick
   re-pauses and alerts. `resume: true` while held: the latch is cleared, the
   fort stays paused (as before). No verdict, `false`, a `queue.escalate`, or an
   unclean or timed-out run: no clear, no resume, latch stands, alert. A latch
   with no verdict is retried (owner and Overseer again) on the next cycle, as
   an escalated latch was before; only a re-latch counts toward the limit.

Dry run plans the sequence (`would_wake`) and writes nothing.

**Hysteresis in the in-game watcher: none.** `df-overseer-clock.lua`: while a
latch file stands it re-asserts pause and keeps the first reason; once
`clock.clear` removes it the next check re-derives from scratch, so a dwarf
still past `thirst_critical` or `hunger_critical` re-latches on the next
interval with a new latch tick. There is no cooldown or recovery band (its own
header says slow-tier clearing is likewise immediate). The repeat counter is
therefore the only brake. Not changed (`scripts/dfhack/` is read only here).

**Files:** `conductor/cycle.py`, `conductor/tripwire.py` (new),
`conductor/policy.py`, `conductor/policy.yaml` (`tripwire_owners`,
`tripwire_repeat`), `conductor/pause_watch.py` (`what` argument only),
`agents/overseer/role.md` (verdict paragraph, and its old "never over a
tripwire" clause corrected), tests: new `conductor/tests/test_tripwire.py`
(22), old tripwire tests in `test_cycle.py`, `test_hold.py`,
`test_pause_watch.py`, `test_report.py` updated to the new contract (a clean
run no longer resumes). `FakeFort` in `test_pause_watch.py` gained `clock.clear`.

**Tests:** `conductor/tests` 393 passed. Full ambient `python -m pytest` with
lupa: 3023 passed, 3 skipped (the known date-sensitive wiki test passed on
this date). `dfmcp/tests` in `.venv-dfmcp`: 828 passed.

**Deploy targets:** vm106-conductor (the `conductor/` package: `cycle.py`,
`tripwire.py`, `policy.py`, `policy.yaml`, `pause_watch.py`; restart the
transient `--once` unit, the service is disabled) and vm106-agents (the
Overseer charter, `agents/overseer/role.md`, through the usual soul sync).
Nothing for vm103: `pause.verdict` and `pause.verdict_read` are already live.
Confirm both tools still answer before the check.

**Live check (for the orchestrator, not run):** on the paused fort with the
conductor held off the live loop:
1. `clock.status` shows no latch, `armed` true; note `abs_tick`.
2. Force one test latch by lowering `thirst_critical` through
   `clock.arm` so a real citizen is past it (no armok power), let the watcher
   latch and pause; `clock.status` shows `tripwire.reason = thirst_critical`.
3. Run one `--once` cycle with no hold. Expect: quicksave, a Quartermaster run,
   an Overseer run (ruling briefing), and, if the Overseer files no verdict,
   the fort stays paused with the latch standing and a CRITICAL "HUMAN ALERT".
4. Run another `--once`: the Overseer should give `pause.verdict`; with
   `resume: true` expect `clock.clear` then `clock.resume`, `abs_tick`
   advancing in the cycle's `pause_watch.actions`, `resumed: true`.
5. Repeat the latch three more times inside 4800 ticks: the fourth cycle must
   run nothing and alert on the repeat.
6. Finally re-arm with the normal thresholds and pause the fort again.
