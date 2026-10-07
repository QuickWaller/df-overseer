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

(executor fills this in, with deploy targets)
