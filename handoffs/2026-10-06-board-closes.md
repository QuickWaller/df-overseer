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

(executor fills this in; deploy targets expected vm103-stream-publisher, relay-web, relay-web-operator)
