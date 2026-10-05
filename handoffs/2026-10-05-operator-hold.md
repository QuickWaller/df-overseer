# Handoff: an operator hold, so agents can plan on a fort paused on purpose

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.**

## Why (user's call, 2026-10-05)

The supervised dry run (`evals/live/2026-10-05-pause-safety/`, section 2) showed
that the pause watchdog (`conductor/pause_watch.py`, wired in
`conductor/cycle.py` around `_pause_watch` / `_paused_cycle_result`) treats every
pause as something to resolve. A fort the operator keeps paused on purpose
therefore blocks every ordinary cycle: the pause path returns early, no role
wakes, the stuck-job watch never polls. After the 600 s grace it would wake the
Overseer with `unexplained_pause`, and a `resume: true` verdict would have the
conductor resume the fort. Nothing lets the operator say "paused on purpose,
keep planning". Until now the agents always planned on a paused fort and a
human ran supervised unpauses; that mode must keep working.

## What to build

An explicit, operator-set hold the watchdog respects.

- **Set and clear by the operator only**, on VM 106, through a small CLI in
  the conductor package (for example `python -m conductor.hold set --reason
  "..."`, `clear`, `show`). Stored as a small JSON file in the conductor's
  runtime state directory beside `pause_watch.json` (same atomic-write pattern
  as `PauseWatchStore`): reason (required, one line), set time, who
  (free text, default the OS user). No agent and no MCP tool can set or clear
  it. Decide in your plan whether it needs an optional expiry; if you add one,
  an expired hold reads as no hold and is logged.
- **Watchdog rule while held:** the conductor never resumes the fort (not on a
  harmless notice, not on a verdict), and does not wake the Overseer for a
  plain pause. A plain pause under a hold takes the **ordinary path**: roles
  wake on their usual signals, the stuck-job watch polls, the briefing is
  built, all with the fort paused. Anything that is not a plain pause (a
  tripwire, a popup, an unknown viewscreen, a threat announcement) still goes
  through the watchdog as today, except that resuming is suppressed and logged
  ("held by operator"). Popups may still be read; decide in the plan whether
  `pause.dismiss` still runs under a hold (preferred: yes, closing a notice
  is not resuming).
- **Visible:** the hold appears in the dry-run plan output, the cycle's status
  log line, and the `pause_watch` block of `conductor/status.py` (`held`:
  reason, since). Do not change `dfqueue/live.py` or `web/` in this stream
  (the site's pause data path to VM 103 is a separate open gap).
- **Docs:** one short note in `docs/TRAPS.md` (or wherever the pause watchdog
  is described for operators) on how to set and clear a hold, and the decision
  table in `handoffs/2026-10-05-pause-safety.md` gains a row for "held".

## Tasks, in order (commit after each)

1. Plan, written in this file's Result section, before building.
2. Build the store, CLI and watchdog rule, with the wiring in `cycle.py`.
3. Tests: held plus plain pause takes the ordinary path (roles can wake, job
   watch polls); held plus harmless notice does not resume; held plus a
   `resume: true` verdict does not resume; held plus tripwire behaves as today
   minus resume; clearing the hold restores today's behaviour; dry run reports
   the hold and writes nothing; corrupt hold file fails safe (decide which
   way is safe and say why: the safe direction is "never resume", so a
   corrupt file should read as held).
4. Result section: what was built, tests run, deploy target (expect
   `vm106-conductor` only), and the exact commands the operator will run.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone; rate-limit cutoffs are routine.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/` (not `runner.py`'s thinking code),
  `docs/TRAPS.md`, `handoffs/2026-10-05-pause-safety.md` (decision table row
  only), this handoff, tests.
- Never resume the fort from the hold code; the hold only ever removes resume
  paths. No armok powers. Public repo: no hostnames, IPs or tokens. No em
  dashes. No attribution lines in commits.
- Full ambient `python -m pytest` and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

Hold store, CLI, watchdog rule and status field built with tests, deploy
target and operator commands listed, and a Result section here.

## Result

(executor fills this in)
