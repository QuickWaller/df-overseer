# Handoff: Acted and Lessons in the Board's turns

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline; no VM access, no
deploys.**

## Why

The user and the orchestrator redesigned the Board's threads on 2026-10-05
(all on main, see `git log` for that day and `web/stream/app.js`
`_conversationEl`, `_turnBlock`, `_receipt`, `_threadEvent`, `statusLine`).
The look is decided; keep it exactly:

- A thread is a sequence of **turns** at the root, in time order. A turn is
  one agent run: a tinted **title band** saying why it woke (titles from
  `web/stream/site-text.yaml` `wake_reasons`) with the conductor's detail
  line, then the agent's avatar and name, its **summary as the message**,
  then **Full report** and **Thinking** expanders.
- Under it, each record the run wrote is a **subtle panel** (a "receipt"):
  a plain grey **kind word** (PROPOSAL, RULING, PLAN, JOB, QUESTION...) and
  the date on top, the record's own words below, and a **Checked**
  expander (its read calls, from `runs.json` `calls_by_record`).
- Status changes are **full-width lines** placed right after the record that
  caused them (Proposal pending / accepted / deferred / rejected, Project in
  progress / on hold / completed / abandoned).
- Colours: bright DF colours mean agents only; status chips are one filled
  style in dark DF shades; kinds are grey words, never chips. Read
  `C:\Users\wills\.claude\projects\c--website-projects-df-automation\memory\site-ui-preferences.md`.

## Tasks, in order (commit after each)

1. **"Acted" on JOB panels.** A JOB panel (an `executed` record) gets a
   collapsed **Acted** expander listing each write call: the tool's display
   name, what it targeted (a count or short target name), and the outcome
   (ok, or failed with a short reason). Operator items carry
   `record.actions[]` (`tool`, `targets`, `outcome`, `detail`,
   `target_state`); add a public-safe `actions` list to `dfqueue/feed.py`'s
   public projection (tool id, target count, outcome; free text such as
   `detail` only through the feed's public safety net). Tests.
2. **Lessons.** When an agent writes a gotcha, or records an outcome on one,
   during a run, show a **LESSON** panel inside that run's turn (kind word
   "Lesson", text like "Noted: <gotcha title>" or "Confirmed "<title>"
   worked"). Source: the gotcha store the publisher already reads read-only
   (`STREAM_PUBLISHER_GOTCHAS_DB`; entries carry `created_at`,
   `written_by_role`; outcomes carry `at`, `role`, `result`, `note`), matched
   to a run by role and its time window from the run store, like
   `dfqueue/runs.py::records_in_window`. Put the matching in a new
   `dfqueue/lessons.py`; write a per-fort `lessons.json`
   (`{lessons: [{run_id, thread, role, kind: "new"|"outcome", gotcha_id,
   title, result, at}]}`) from `scripts/stream_publisher.py`; public titles go
   through the same safety the public `gotchas.json` applies (unsafe ones are
   skipped). A lesson belongs to every thread its run touched. The page reads
   `lessons.json` like `runs.json`. Tests.
3. **Preview and checks.** The preview (`scripts/preview_stream_live.py`, the
   demo fixture) shows an Acted list and a Lesson panel without hand-edited
   data (mark example data as such). Node tests on the real `app.js` for
   Acted and Lessons; headless check of both pages at 1280x700, no console
   errors, the page never scrolls. Bump the asset version.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `web/stream/`, `dfqueue/feed.py`, new `dfqueue/lessons.py`,
  `scripts/stream_publisher.py` (only to write `lessons.json`),
  `scripts/preview_stream_live.py`, `web/stream/fixtures/`,
  `infra/deploy-manifest.yaml` (only to add `dfqueue/lessons.py` to the
  publisher target), tests. **Not** `dfqueue/live.py`, `dfqueue/runs.py`,
  `dfqueue/schema.py`, `conductor/`, `dfmcp/`, `agents/`, `scripts/dfhack/`.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.
- Full ambient suite green.

## Done when

All three tasks committed with tests, headless results in the Result, the
deploy targets listed, and a Result section here.
