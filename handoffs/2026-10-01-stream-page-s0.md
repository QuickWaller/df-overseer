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

(fill in, about 200 words, and how the user opens the page locally)
