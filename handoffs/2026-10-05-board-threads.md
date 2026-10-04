# Handoff: finish the Board's forum threads and list every proposal

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline; no VM access, no
deploys.**

## Why

The user designed the Board's project and proposal panel with the orchestrator
on 2026-10-05 and approved a prototype, committed on main as `1d95040`
("Board prototype (user-approved look)"). Run `python scripts/preview_stream_live.py`
to see it; `web/stream/README.md` explains the preview. The look is decided:
**keep it**. This stream makes it real, tested and complete. The user's UI
rules: read `C:\Users\wills\.claude\projects\c--website-projects-df-automation\memory\site-ui-preferences.md`
(one screen, inner panes scroll, minimal text, dark only, counts spelled out).

## What the prototype does (keep all of it)

- `_conversationEl` in `web/stream/app.js`: the conversation is a forum
  thread, oldest first. The founding proposal is the opening post; every other
  item in the thread replies to it one level in; an answer nests under its
  question. Replies are hidden behind a "+ N replies · who · last <date>"
  toggle, and the open state survives re-renders (`this._openReplies`).
- Posts: initial-letter avatar in the role colour, name, a kind label
  (proposal type, Question, Answer, Plan change), the ruling's verdict as a
  chip with the "Accepted:" prefix stripped, the date, and two expanders when
  data exists: "What it checked" (`item.calls`) and "Thinking" (`item.thinking`,
  operator only; nothing produces it yet, leave the hook).
- Events, one line, grey square (amber for hold or failure), naming who and
  which job: "Overseer made this a project with 2 jobs: Dig shell, Make bed",
  "Overseer started job "Dig shell" · 4 of 12 targets ordered", finished,
  failed, on hold.
- Smaller job graph at natural size, arrows leaving and entering vertically.

## Tasks, in order (commit after each)

1. **Public step data.** The public feed item for an `executed` record carries
   no record, so the public page cannot name the job. In `dfqueue/feed.py`'s
   public projection, add `step_label`, `step_targets` (targets acted on) and
   `step_total`, plus `target_state` outcome words if needed for
   started/finished/failed. Labels are agent-written display text: run them
   through the same public-text safety the feed already applies. Tests.
2. **"What it checked" from real data.** Decide whether the feed can fill
   `item.calls` today (the operator feed has a `calls` field, always empty in
   the fixtures; find what it is meant to hold and where it would come from).
   If it needs data only the MCP server has, say so in the Result and leave
   the hook; do not invent a data path.
3. **Every proposal in the board list, with filters.** Today the Board's
   tabs split projects and proposals by state. The user wants every proposal
   listed (accepted, rejected, deferred, pending), each opening its thread,
   with filters (by state at least; by agent if it fits) instead of hiding the
   rejected ones. A proposal that becomes a project is one entry, not two.
   Keep the board's tabs-with-counts look; the user liked it.
4. **Titles that grow.** A proposal's entry is titled from the proposal (its
   summary or type); once a project exists, its `public_title` replaces it,
   and a later amend that changes the title updates it. Check what the
   records already carry before adding anything.
5. **Tidy and test.** Remove the unused `_conversationElFlat` and `.fdepth`
   CSS if nothing uses them; node-based tests on the real source for the
   thread tree (root, nesting, collapsed by default, event wording) like
   `dfqueue/tests/test_site_js_order.py` does. Keep the preview data helpers
   working (`scripts/preview_stream_live.py`); extend the demo fixture
   (`web/stream/fixtures/`) with a question and answer in a project thread and
   a rejected proposal, so the preview shows every case without hand-edited
   data. Bump the asset version.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `web/stream/`, `dfqueue/feed.py`, `dfqueue/site_data.py`
  (only if titles need it), `scripts/preview_stream_live.py`, tests. **Not**
  `dfqueue/live.py`, `scripts/stream_publisher.py`, `conductor/`, `dfmcp/`,
  `agents/` or `infra/deploy-manifest.yaml` (another stream owns them); if
  you need a manifest change, list it in the Result.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.
- Full ambient suite green; `node --check web/stream/app.js` clean; check the
  public and operator pages headless at 1280x700 (no console errors, a thread
  opens and its replies expand).

## Done when

All five tasks committed with tests, screenshots described in the Result,
the deploy targets listed, and a Result section here.
