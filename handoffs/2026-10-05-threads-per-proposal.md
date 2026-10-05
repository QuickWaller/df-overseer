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

Done 2026-10-06. Offline, no deploys. Asset version v60 -> v61 (index.html, operator.html).

- **Thread now shows**: per turn that wrote here, the title band (why it woke, when, how long), then only this proposal's own receipts: the proposal, its ruling (the ruling's own `public_rationale`, already the item text in feed.py, so no data change), project and executed items, status lines, lessons. The whole-turn summary is gone from threads. The run's full report and thinking stay as collapsed expanders labelled "This turn's full report" and "This turn's thinking".
- **Turn summary lives once on the agent's page**, a new "Turns" tab (`_turnsEl` in `SitePage`, fed by `runs.json` via `_ensureRuns`): newest first, wake reason, date, duration, summary, then Full report and Thinking expanders. Why there: a turn belongs to an agent, not a proposal; the Board is a per-proposal list with no turn list, and the agent page already holds Tools, Recent lines and Charter.
- **`_public_summary` untouched**: the summary is still cut at its existing length, but the uncut (separately redacted) `report` is on the same turn entry behind "Full report", so later items no longer vanish. Safety filter unchanged. `dfqueue/live.py`, `feed.py` and the preview script not touched.
- Tests: `dfqueue/tests/test_site_js_threads.py` gained three node tests (own rationale not another's; summary absent from both threads with expanders labelled; summary exactly once on the Turns tab) and one updated assertion. Ambient `python -m pytest`: 2898 passed, 3 skipped.
- Headless (Chrome via DevTools protocol against `scripts/preview_stream_live.py --no-serve` data, 1280x700 and 390x800): thread has no turn summary, expanders read "This turn's full report/thinking", Turns tab shows one Overseer entry with the summary; console clean apart from a favicon 404. Local server stopped.
- Deploy targets (static web assets only, since live.py is unchanged): relay-web and relay-web-operator. vm103-stream-publisher not needed.
