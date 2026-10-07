# Handoff: a Metrics tab on the Board

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call 2026-10-07: put the agent metrics on the site. The module is
merged: `dfqueue/wake_metrics.py`, pure `compute(queue_db, runs_db, ...)`,
published schema `wake_metrics/1` (see its docstring and
`handoffs/2026-10-07-wake-metrics.md` Result). Every string in it is an id,
role, day, keyword or tool id; a test enforces that.

## Scope

- Publisher (`dfqueue/live.py`, `scripts/stream_publisher.py`): call
  `compute()` on the live DBs (read-only), write `metrics.json` for public
  and operator sides on the existing cadence or slower (it need not run
  every tick: a cadence as data), with the same staging/rsync path as the
  other files.
- Board (`web/stream/app.js`, `style.css`): a Metrics tab (one screen,
  inner panes scroll, dark only, per `memory` UI preferences). Per role:
  small charts or sparklines over days for R (repeat defers, duplicates,
  repeat proposals by the M1-struct rule, labelled as approximate), rounds
  per wake, cost per wake, pass rate; per-role tool usage as a sorted list
  (called vs never called), noting how many wakes it rests on. Mark epochs
  (deploys that changed what roles see) on the charts. Say plainly when a
  number rests on few wakes. No chart library unless one is already used;
  inline SVG is fine. Bump the asset version.
- `scripts/preview_stream_live.py`: demo metrics so it can be checked
  locally.
- Tests: publisher writes the file and it validates against the schema;
  the safety test still holds; Board node tests if present.

## Rules

Touched surfaces: `dfqueue/live.py`, `scripts/stream_publisher.py`,
`web/stream/`, `scripts/preview_stream_live.py`, tests, this handoff.
Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
lines. Commit after each milestone. Do not write Working.md, DECISIONS.md,
memory or INDEX.md. Full ambient `python -m pytest` (lupa on PYTHONPATH)
and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets)
