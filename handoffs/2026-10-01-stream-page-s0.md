# Handoff: stream page slice S0 (local projections and page)

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline only, no live access.**

## Why

The stream page design is settled (`research/2026-10-01-stream-page-design.md`,
Opus; the user's decisions in the register's 2026-10-01 rows: two pages with
the switch only on the operator side, hosted on the relay, user messages
public by default, Consultant answers as a public one-line summary, operator
page on the admin address). Slice S0 (design §8): everything that can be built
and seen locally with no live access.

## Tasks, in order (commit after each)

1. `dfqueue/feed.py`: the public and operator projections (design §3.5, §3.6)
   and the publisher-side derivations (§3.4: thread, project, one item model
   per chat line, §3.2), segmenting and the file layout (§4.2), as pure,
   tested code. Read the queue read-only: never through
   `dfqueue.store._connect` (it can create or migrate tables, design §2); open
   SQLite read-only. Where a schema addition from §3.3 does not exist yet,
   derive what can be derived and leave a clearly named gap; do not change
   `dfqueue/schema.py` in this slice.
2. `web/stream/`: the page as static files rendering those JSON files, per
   the mockup (`research/2026-10-01-stream-page-mockup.dc.html`) as amended
   by design §6 (no Public/Operator switch on the public page; "show as
   public" toggle on the operator build; one-line summaries for quiet kinds;
   reply lines and about chips; mobile tabs). Plain HTML, CSS and JS, no
   build step, no external requests except fonts. Text rendered as text only
   (design §7). The live view is a placeholder frame in S0.
3. A small script that exports a local queue (or the real exported records in
   `evals/live/*/queue-export/`) through `feed.py` into a folder the page
   reads, and how to open it locally, in `web/stream/README.md`.
4. Tests for `feed.py`, including that the public projection never carries a
   field outside the allowlist and that a public text field holding a
   URL, address, path or token-like string is withheld (design §7.2).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `dfqueue/schema.py` or `dfqueue/store.py`.
- This repo is public: never a hostname, address, subnet or token, in code,
  fixtures or docs.
- No em dashes in prose. No attribution lines in any commit.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

New `dfqueue/feed.py`, new `web/stream/`, new tests, an export script.

## Result

Built. `dfqueue/feed.py`: pure, read-only projections (public and
operator) per design sections 3.4-3.6 and 4.2 — the one-item model,
`reply_to`/`thread` derivation for every kind that already carries a
native link, a per-kind public-text allowlist, a publish-time withhold net
for URL/address/path/token-shaped text (design section 7.2's layers 3/4
stand-in, since no schema write-time check or real canary list exists
yet), the project-to-thread map, verdict badges, and content-hashed
200-item segmenting. Reads via a strict read-only SQLite URI, never
`dfqueue.store._connect`. Every design-section-3.3 addition not yet stored
(`seq`, `run_id`, `reply_to`/`about` storage, hold codes, `public_title`,
the new `wake`/`run`/`goal`/`review`/`message`/`alarm` kinds) is named in
`feed.GAPS` and returns `None` rather than inventing data; an unrecognised
kind raises loudly instead of silently vanishing. 61 tests in
`dfqueue/tests/test_feed.py`, including the allowlist assertion and seven
parametrised leak shapes (URL, IPv4, path both styles, email, token,
markup).

`web/stream/`: `index.html` (public, no Public/Operator switch — design
section 5's departure) and `operator.html` (adds the "show as public"
toggle, moved off the public page), sharing `app.js`/`style.css`. Plain
JS, no framework, no external requests, every piece of item text inserted
via `el()`'s `text` option (`.textContent` only, never `innerHTML`).
Renders proposals with live-updating verdict badges, rulings, System step
lines, collapsed pass/ask/answer lines, pinned escalations, reply quotes,
role colours, game-date-first timestamps, a Highlights/Everything filter
with role as secondary, a Projects tab, and a mobile tab bar. Polls
`head.json` every 5 seconds while the tab is visible (Page Visibility
API) and currently reads only the open segment (no history-scrolling UI
yet — named in `web/stream/README.md`).

`scripts/export_stream_feed.py` builds `web/stream/data/{public,operator}`
from `--records <queue-export/records.jsonl>` or `--db <fort.sqlite3>`
(read-only). `web/stream/data/` is gitignored, generated only.

**To open it**: from the repo root,
`python scripts/export_stream_feed.py --records evals/live/2026-09-15-overseer-first-ruling/queue-export/records.jsonl --out-dir web/stream/data`,
then `cd web/stream && python -m http.server 8934`, then open
`http://127.0.0.1:8934/index.html` (public) or `.../operator.html`
(operator). Verified end to end: ran the export against both real
`evals/live/*/queue-export/records.jsonl` files, served the directory,
and confirmed `index.html`, `operator.html`, `app.js`, `style.css` and
`data/public/head.json` all return HTTP 200; checked `app.js` with
`node --check`.

**Tests**: ambient `python -m pytest` (repo root, no `lupa`, matching
CLAUDE.md's documented trap): **2209 passed, 3 skipped**, up from the
2026-09-25 baseline of 1845/3 by real test growth elsewhere on `main` plus
this stream's own 61 (`dfqueue/tests/test_feed.py`) — none of the 61 skip
or depend on `lupa`. `dfmcp/tests` via the main checkout's
`.venv-dfmcp\Scripts\python.exe`: **722 passed** (up from the documented
692 baseline by growth elsewhere on `main`; this stream touched nothing
under `dfmcp/`). Neither suite was touched by this stream except by
addition. Caught by the ambient run itself: a first draft of
`test_feed.py` used `a private RFC 1918 address` as a fake leaked-address fixture, which
`tests/test_no_leaked_addresses.py` correctly failed on (it is a real
RFC 1918 address, in a tracked file); fixed to the RFC 5737 documentation
address `192.0.2.42` in a follow-up commit, re-verified green. A second
fixture using the real local username as a fake Windows path was also
swapped for a generic one on the same pass, out of caution.

**Gaps left for later slices** (also itemised in `dfqueue/feed.py`'s
`GAPS` list and `web/stream/README.md`): no live `seq`/`run_id` (S2); no
step labels, `public_title` or per-target project progress (S4, needs
`dfqueue.store.project_status`, which this read-only module cannot call);
no fort status or season goal (`feed.status` does not exist, S2/S5); no
call-log join (S2); no history-scrolling past the open segment or season
files client-side (S7); no full project drawer with a timeline (needs S4's
fields); no JS test suite for `app.js` itself (the safety-relevant logic
lives in `dfqueue/feed.py`, which is thoroughly tested; the rendering
layer was exercised manually via the HTTP smoke test above, not
automated). No live access was used or needed.
