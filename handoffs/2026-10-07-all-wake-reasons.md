# Handoff: record every wake reason per run

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git fetch origin && git merge --ff-only origin/main`.

## Why

`conductor/triage.py` `wake_for` keeps only the first Wake per role, so the
runs table and archive record one reason per run (wake audit finding 8;
wake cleanup Result "not done"). The metrics (`dfqueue/wake_metrics.py`) and
the Board need every reason a role was woken for.

## Scope

- Keep all wake reasons per role run (ordered, deduplicated), pass them to
  the runs store (`conductor.report` start/end args, `dfqueue/runs.py`
  column, auto-migrated) and the archive; the briefing behaviour is
  unchanged (it already lists them; check).
- `dfqueue/wake_metrics.py`: use the full list where it now uses the one
  reason; keep the published schema compatible (bump the minor version if
  a field is added).
- The Board shows all reasons where it shows one today (Turns tab, awake
  strip) if it is a small change; else note it.
- Tests.

## Rules

Touched surfaces: `conductor/triage.py`, `conductor/cycle.py`,
`dfmcp/conductor_tools.py`, `dfqueue/runs.py`, `dfqueue/live.py`,
`dfqueue/wake_metrics.py`, `web/stream/` (small), tests, this handoff. Do
not touch `dfqueue/store.py` or `dfmcp/queue_tools.py` (another stream).
Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
lines. Commit after each milestone. Do not write Working.md, DECISIONS.md,
memory or INDEX.md. Full ambient `python -m pytest` (lupa on PYTHONPATH)
and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

Done, offline. Branch `worktree-agent-a16bf5a104a6168ff`.

- `conductor/triage.py`: `TriageResult.reasons_for(role)`, every reason in wake
  order, deduplicated. `wake_for` and the briefing are unchanged (the briefing
  already carried the headline reason plus the planner's merged detail).
- `conductor/cycle.py`: `_run_role(..., wake_reasons=)` sends `wake_reasons`
  (headline first, then the rest) on `conductor.report` start, and on a
  start-less end. Tripwire and pause-verdict runs send their one reason.
- `dfmcp/conductor_tools.py`, `dfqueue/runs.py`: new optional `wake_reasons`
  array arg (max 12, each at most 64 chars) and a `wake_reasons` JSON column,
  auto-migrated by `ALTER TABLE`; `wake_reason` stays the first.
  `runs.decode_wake_reasons(row)` falls back to the single reason for old rows.
  The archive is this runs table (no separate archive code carries the reason).
- `dfqueue/live.py`: `runs.json` entries, the awake strip and `last_runs`
  (report source) gain `wake_reasons` beside `wake_reason`; public output keeps
  plain codes only. The `conductor` status-file archive `last_runs` is left
  with its single reason (the report source overrides it when present).
- `dfqueue/wake_metrics.py`: per-wake rows gain `wake_reasons` (safe words).
  Nothing aggregated keyed on the one reason, so no other change. The schema id
  is the integer `wake_metrics/1` (no minor exists); the doc says additions are
  not breaking, so it is NOT bumped.
- `web/stream/app.js`: `wakeList`/`wakeTitle` helpers; the live strip, the
  Turns title band, the per-role turns list and the feed line show all reasons
  joined with " + ", falling back to `wake_reason` for an older feed.
- Tests added in test_triage, test_report, test_conductor_tools, test_live,
  test_wake_metrics. Ambient full run: 3643 passed, 3 skipped (lupa on path;
  the known date-sensitive failure did not fail). `dfmcp/tests` in
  `.venv-dfmcp`: 987 passed.

Deploy targets and ORDER: dfmcp server (VM 103) FIRST, because the old
`conductor.report` schema has `additionalProperties: false` and would refuse
the new `wake_reasons` arg (the conductor logs a warning and the run goes
unreported); then the conductor (VM 106) and the stream publisher host (new
`runs.json` fields, `app.js`). The runs DB migrates itself on first write.
