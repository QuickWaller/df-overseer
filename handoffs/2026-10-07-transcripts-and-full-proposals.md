# Handoff: public agent transcripts (collapsed tab) and full proposal details

Date: 2026-10-07. **Executor, Sonnet, worktree. Offline; no deploys.**
First: `git merge --ff-only main`.

## Why

User's call 2026-10-07: show each agent run's full transcript on the Board,
on a separate tab, collapsed by default like the tools-used view; and show
the full proposal (not just its one-line `public_rationale`), collapsed in
its thread. Both pass the same public safety filter as everything else
(`dfqueue/feed.py` `_UNSAFE_PATTERNS`, `_safe_public_text`); never route
around a refusal: a withheld span is shown as withheld.

Known gap (`research/2026-10-07-cross-run-cache.md`): no per-turn transcript
is stored today. openclaw's state DBs hold no session transcripts; the
conductor archives only `run-<role>.json` envelopes
(`conductor/archive.py`, `conductor/runner.py`).

## Scope

1. **Capture.** Find where the full turn sequence is available at run time
   (openclaw's JSON output the runner parses, its session files, or a
   per-run flag that keeps them; read `conductor/runner.py` and what openclaw
   returns). Archive per run: each round's tool calls (name, arguments),
   tool results (truncated to a cap, policy data), reasoning text if the
   provider returns it, and per-round usage (this also closes the cache
   study's "no per-turn data" gap). Size caps and retention as data. If
   capture needs an openclaw setting you cannot confirm offline, implement
   against the documented shape, mark it unverified, and list the live
   check.
2. **Publish.** The publisher (`dfqueue/live.py` or wherever run data
   reaches the site) carries each run's transcript to the Board through the
   safety filter, public and operator variants as for other text.
3. **Board.** `web/stream/app.js`/`style.css`: a Transcript tab per run (next
   to the Turns tab), each run collapsed by default, tool calls collapsed
   inside it like the tools-used view; and in each proposal's thread a
   collapsed "Full proposal" block: summary, rationale, preconditions,
   prediction, the step (tool and arguments, coordinate-free as filed),
   cited facts. Markdown rendering via the existing safe renderer (DOM only,
   never innerHTML). Bump the asset version. Follow
   `memory`-recorded UI preferences: one screen, inner panes scroll, tabs
   over long lists, dark only.
4. Tests: capture shape, caps, filter applied to every new public field, a
   withheld span shown as withheld, Board rendering tests if the repo has
   them.

## Rules

Touched surfaces: `conductor/runner.py`, `conductor/archive.py`,
`conductor/policy.yaml` only for transcript caps (another stream edits
policy.yaml: add a separate top-level block only), `dfqueue/feed.py`,
`dfqueue/live.py`, `web/stream/`, tests, this handoff. Public repo: no
hostnames, IPs or tokens; transcripts must never carry them (the filter
plus a test). No em dashes. No attribution lines. Commit after each
milestone. Do not write Working.md, DECISIONS.md, memory or INDEX.md. Full
ambient `python -m pytest` (lupa on PYTHONPATH) and `dfmcp/tests` in
`.venv-dfmcp` green.

## Result

(executor fills this in, with deploy targets and the live checks)
