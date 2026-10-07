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

Done, offline, nothing deployed.

- **Publisher** (`scripts/stream_publisher.py`): `metrics.json` (`wake_metrics.compute` over the live queue and runs DBs, read-only) written to `forts/<fort>/metrics.json` on both sides, same staging and rsync path. Cadence as data: `metrics_interval_seconds` (default 3600, `STREAM_PUBLISHER_METRICS_SECONDS` or `--metrics-interval`, 0 = every cycle); between recomputes the staged file is reused (`cursor.metrics_last`). Folded into the change hash minus `generated_at`. A compute failure never stops a cycle. No run store, no file. `dfqueue/live.py` needed no change.
- **Board** (`web/stream/app.js`, `style.css`): a Metrics nav tab (`#metrics`), one screen. Left pane scrolls: repeats per day (stacked bars: defers, duplicates, M1-struct proposals, labelled approximate), rounds per wake, cost per wake, pass rate (lines per role, hollow points where a day has under 3 wakes). Right pane: role tabs and the tool list sorted by calls, then never-called. Every card says how many wakes it rests on and says "Thin" under 10. Epochs are dashed verticals (start = first day an epoch appears in the per-wake rows). Inline SVG, no library. Asset version bumped 64 to 65 in `index.html` and `operator.html`.
- **Preview**: `scripts/preview_stream_live.py` writes a real `compute` report over the committed window fixture as `metrics.json`.
- **Extra (coordinator's request)**: the who-is-awake strip now stacks one row per awake role (pause row first, about 5 rows then inner scroll, reason ellipsised); single-role and "Last run" look unchanged. Separate commit; node test `test_two_awake_roles_render_as_two_rows_one_line_each` in `dfqueue/tests/test_live_pause_strip.py`.
- **Tests**: `tests/test_stream_publisher_metrics.py` (6: both sides written, schema keys and safe strings, no store, cadence, failure isolation, no push on generated_at alone, env/flag), `dfqueue/tests/test_site_js_metrics.py` (6 node tests). Ambient suite 3522 passed, 3 skipped (run before the strip commit; dfqueue tests re-run after: 712 passed); `dfmcp/tests` in `.venv-dfmcp`: 970 passed.
- **Not checked**: layout in a real browser (only node DOM stubs); judge it with `python scripts/preview_stream_live.py` then `#metrics`.
- **Deploy targets**: publisher host (`scripts/stream_publisher.py`, `dfqueue/` already there) and the web relay (`web/stream/`: app.js, style.css, index.html, operator.html). Metrics only appear once the publisher can see the runs DB.
