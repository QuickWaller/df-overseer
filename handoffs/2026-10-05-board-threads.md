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

## Result (extended as the work lands)

Plan: (1) feed gets `step_label`/`step_targets`/`step_total`/`step_outcome` on
executed items; (2) check what `calls` could hold; (3) board lists every
proposal with state filters; (4) titles grow from proposal to project to amend;
(5) tidy, node tests, fixture, asset bump. Commit after each.

### Done (all five tasks committed on the worktree branch)

1. **Public step data.** `dfqueue/feed.py`: `executed_step_info` adds `step_label`
   (the step's label, newest plan version wins, humanised tool id as the
   fallback, run through `_safe_public_text`, `None` when unsafe), `step_targets`,
   `step_total` (literal target count, `None` for dynamic targets) and
   `step_outcome` (started, finished, failed) to public AND operator executed
   items; all four are in `PUBLIC_ITEM_FIELDS`. `eventLine` in `app.js` words the
   event from them.
2. **"What it checked".** Not fillable from the feed today. The operator item's
   `calls: []` is the design's section 3.6 join (tool calls sharing the item's
   `run_id`), which needs the `run_id` stamp (slice S2, a GAPS entry) and
   dfmcp's call journal, both outside the feed and outside this stream. The JS
   hook (`item.calls`, entries `{tool, note}`) is left; no data path invented.
3. **Every proposal listed.** `boardEntries` (pure) gives one entry per proposal
   thread, newest first; a proposal that became a project is one entry. Tabs by
   state with counts: All, Under way, On hold, Done, Pending, Deferred, Rejected
   (empty states hidden), plus an "All agents" select when more than one agent
   has proposed. Cards show a state chip for pending/deferred/rejected and the
   proposing agent. Abandoned projects stay under Done ("Abandoned" label).
4. **Titles that grow.** Public and operator proposal items now carry `title`
   (a truncated `summary`, safety-checked on the public side, the same last-resort
   rule projects already use). Entry name: project `public_title` once a project
   exists, else the proposal `title`, else its type. `build_projects_view` lets a
   later amend's `public_title` rename the project. **Gap:** `dfqueue/schema.py`
   gives `amend` no `public_title` field (and the dfmcp amend tool no argument),
   so no real record can carry one yet; the feed reads it when present (tested
   on raw records). Adding it is a schema plus dfmcp change, not done here
   (not in my surfaces).
5. **Tidy and tests.** Removed `_conversationElFlat`, `_replyTag`, `_sectionEl`,
   the card builders and `.fdepth`. New `dfqueue/tests/test_site_js_threads.py`
   (7 tests, node, real `app.js` with a tiny DOM stub): thread root and
   nesting, event wording for started/finished/failed/hold/plan, replies
   collapsed by default with the open state surviving a re-render, one entry per
   proposal, project title replacing proposal title, orphan project entry.
   `dfqueue/tests/test_feed.py` +9 tests. Demo fixture now has a pending
   proposal (0010), a deferred one (0011, ruling-0011) and `ask-0001` joined to
   proposal-0004's project thread (the rejected proposal-0002 already existed);
   `test_site_data.py` counts updated for the extra ruling and proposal. Asset
   version bumped to `?v=33` in `index.html` and `operator.html`.

### Checks
- `python -m pytest dfqueue -q`: 435 passed. `node --check web/stream/app.js`: clean.
- Headless Chrome 1280x700 (CDP script, scratchpad, not committed), public and
  operator pages: no console errors (public shows only a favicon 404 from the
  bare http.server), page does not scroll, tabs All 7 / Under way 1 / On hold 1 /
  Done 2 / Pending 1 / Deferred 1 / Rejected 1, Rejected tab lists the
  rejected proposal, agent filter Quartermaster gives its 2 entries, a project
  thread opens with "+ 4 replies" collapsed, expands to "- 4 replies", events
  read 'Overseer finished job "Dig down-stair" · 1 of 1 target done' on the
  PUBLIC page too (task 1 working), the Question and Answer nest under each
  other once expanded.

### Deploy targets
- Relay web (`relay-web` target, already in `infra/deploy-manifest.yaml`):
  `web/stream/index.html`, `app.js`, `style.css`; operator target adds
  `operator.html`. No manifest change needed.
- Feed export on VM 103 (`dfqueue/feed.py`, already listed in the manifest): the
  public page needs the new feed fields (`step_label` etc., `title`) or events
  fall back to "carried out a job" and proposals to their type. Deploy the
  feed with the web files; old data stays readable.
