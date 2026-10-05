# Handoff: threads show their own proposal; the turn summary lives once

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline; no deploys.** User's
call: register 2026-10-05, "A proposal's thread shows only its own items".

## Why

On the Board, a proposal's thread shows the Overseer's whole-turn summary
("Done. Every pending proposal has a ruling ... Rulings: proposal-0017 ...")
under every thread that turn touched, and the public summary is cut so later
items vanish. The proposal-specific text exists already: each ruling's
`public_rationale`, and each run's `records` list (record id plus `thread`) in
`runs.json`.

## What to build

- In a proposal's thread (`web/stream/app.js`, the thread view): the proposal,
  then its ruling as the Overseer's reply using the ruling's own
  `public_rationale`, then its project and executed items (what was carried
  out). Not the turn's summary.
- The run's Thinking and Full report stay available in a thread as collapsed
  expanders, labelled so it is clear they cover the whole turn (for example
  "This turn's thinking", "This turn's full report").
- The whole-turn summary and full report shown once, on a turn entry: pick the
  natural home from the current page structure (the Board's activity/turn
  list, or the agent's page) and say why in the Result.
- Check the public summary cut in `dfqueue/live.py` (`_public_summary`): if a
  turn summary is shown in full on the turn entry, its cut length may need to
  grow; keep the safety filter exactly as strict.
- Bump the asset version (currently v60).

## Tests

Node tests on the real `app.js` in the style of `dfqueue/tests/test_site_js_threads.py`:
a thread for one proposal shows its ruling rationale and not another
proposal's; the turn summary appears once; expanders are labelled. A headless
check at 1280x700 and phone width against the preview data, console clean.

## Rules

- First step: `git merge --ff-only main`. Commit after each milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `web/stream/` (app.js, style.css, html version),
  `dfqueue/live.py` and `dfqueue/feed.py` (only if the thread data needs a
  field), `scripts/preview_stream_live.py` if the preview needs data, tests.
  Not `dfqueue/` store or schema (another stream is building there).
- Never `innerHTML`; use the existing Markdown renderer. Public repo: no
  hostnames, IPs or tokens. No em dashes. No attribution lines in commits.
  Stop any local server you start before finishing.
- Full ambient `python -m pytest` green.

## Result

(executor fills this in; deploy targets expected relay-web, relay-web-operator, vm103-stream-publisher if live.py changes)
