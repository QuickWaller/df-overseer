# Handoff: load transcripts on demand

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call 2026-10-07. `handoffs/2026-10-07-transcripts-and-full-proposals.md`
ships the newest 8 runs' transcripts inside the polled `runs.json` (up to
about 320 KB per poll). Load each transcript only when its run is expanded.

## Scope

- Publisher (`dfqueue/live.py`): write each run's filtered transcript to its
  own file (public and operator variants, as today), named by run id;
  `runs.json` carries only `transcript: {available, size, withheld_count}`
  per run. Keep transcripts for more than the newest 8 if size allows
  (retention as data), and prune old files.
- Relay: the new files are served next to `runs.json` (check how the
  publisher's outputs reach the relay and that the new path is covered by
  both relay-web targets and the caching headers).
- Board (`web/stream/app.js`): fetch the transcript when a run is first
  expanded, show a loading state, cache it for the session, handle a
  missing file. Bump the asset version.
- `scripts/preview_stream_live.py`: a demo transcript and a demo full
  proposal so the Board can be checked locally.
- Tests: runs.json no longer carries transcript bodies; file written and
  filtered; pruning; Board fetch on expand (node tests if present).

## Rules

Touched surfaces: `dfqueue/live.py`, publisher and relay deploy config if
the new path needs it, `web/stream/`, `scripts/preview_stream_live.py`,
tests, this handoff. Public repo: no hostnames, IPs or tokens. No em
dashes. No attribution lines. Commit after each milestone. Do not write
Working.md, DECISIONS.md, memory or INDEX.md. Full ambient `python -m
pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in `.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets)
