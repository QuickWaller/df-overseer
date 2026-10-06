# Handoff: the Board shows closed work as closed

Date: 2026-10-06. **Executor, Sonnet, worktree. Offline; no deploys.**

## Why

Deploy 2a (2026-10-06) closed every accepted pre-cutover ruling under the
conductor's name (`close-0001` to `close-0010`, outcomes `completed` or
`not_done`; the user: "the current projects could just be nixed"). The
publisher already carries the `close` records, but the Board's status comes
from `dfqueue/feed.py` `build_proposal_badges`, which reads only the latest
ruling, so every closed proposal still shows as accepted (ongoing).

## What to build

- A `close` record decides the proposal's final status, after any ruling: a
  close names a ruling, a proposal or a project (`dfqueue/feed.py` around line
  252 resolves which); map it to its proposal.
  - outcome `completed` -> the existing **completed** state (green).
  - `not_done`, `superseded`, `abandoned` -> a new **closed** state: the same
    filled chip style as the others (register 2026-10-05, "Board status
    looks"), in a neutral grey shade, never a glyph.
- Anywhere the Board lists ongoing or open work, closed and completed items
  leave it (they stay findable under their state tab or filter).
- The thread for a closed proposal shows the close as its last item, using the
  existing public close text (`_CLOSE_PUBLIC_TEXT`), never the close `reason`.
- Bump the asset version (currently v61).

## Tests

Feed tests for the badge mapping (ruling then close, close of a ruling id, of a
project id); node tests on the real `app.js` that a closed proposal is not in
the ongoing list and shows the closed chip; headless check at 1280x700 and
phone width against the preview, console clean. Stop any server you start.

## Rules

- First step: `git merge --ff-only main` (fall back to `git fetch origin &&
  git merge --ff-only origin/main`). Commit after each milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `dfqueue/feed.py`, `dfqueue/feed_status.py` (if status
  lives there), `web/stream/` (app.js, style.css, version), their tests,
  `scripts/preview_stream_live.py` if the preview needs a close, this handoff.
  Not the store or schema.
- Never `innerHTML`. Public repo: no hostnames, IPs or tokens. No em dashes.
  No attribution lines in commits.
- Full ambient `python -m pytest` green.

## Result

Done (executor, offline, no deploy). Asset version **v62**. Deploy targets:
vm103-stream-publisher (feed.py), relay-web, relay-web-operator (app.js,
style.css, index.html, operator.html).

- `dfqueue/feed.py`: new `close_proposal_map` and `close_badge`;
  `build_proposal_badges` now lets the last `close` override the ruling badge
  (`completed` for outcome completed, `closed` for not_done, superseded,
  abandoned). A close naming a proposal, a ruling or a project all map to the
  proposal (a project via its founding ruling). `build_projects_view` also sets
  a closed project's `status` (`done` or the new `closed`), so `projects.json`
  agrees with the badge.
- `web/stream/app.js`: new Closed state and tab (after Completed); closed
  and completed work leaves the In progress tab (stays under All and its own
  tab); `closed`/`completed` proposal and project chips; closed project detail
  shows no live jobs; a thread ends with the close receipt (existing public
  close text, never the reason) and a full-width "Closed" status line (grey,
  or green "Closed as completed"). `style.css`: filled grey `ps-closed`,
  `js-closed`, `chip closed`, plus green `ps-completed`; no glyph.
- Preview: `scripts/preview_stream_live.py` appends two example close records
  to a temp copy of the demo records (the committed fixture is untouched).
- Tests: `test_feed.py` (+7: ruling then close, close of a ruling id, of a
  project id, of a proposal, projects view), new
  `test_site_js_closed.py` (6, node on the real `app.js`).
- Headless (Edge via CDP, 1280x700 and 390x800, public and operator): tabs
  show Closed 1 and Completed 2, In progress lists only the live project, the
  closed card shows the grey chip, the thread ends with the close and its status
  line, no horizontal scroll, desktop page never scrolls, console clean (only
  a favicon 404). On the phone width the page itself scrolls (stacked mobile
  layout; not compared against v61, flag if it matters). Preview server and browser stopped.
- Note for the deploy: the publisher must be deployed first, or the page keeps
  showing closed work as accepted (the badge comes from the feed).
