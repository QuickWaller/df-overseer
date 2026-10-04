# Handoff: real data in the Board's threads (summaries, what it checked, thinking)

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build plus
read-only host reads; no host writes, no deploys.**

## Why

The Board's threads (`web/stream/app.js`, `_conversationEl`, `_threadPost`;
`handoffs/2026-10-05-board-threads.md`) have the look the user approved, with
two expanders under each agent post: "What it checked" (`item.calls`, a list
of `{tool, note}`) and "Thinking" (`item.thinking`). Both show only sample
data today. `conductor.report` (`handoffs/2026-10-05-conductor-report.md`) is
deployed: the publisher now writes `forts/<id>/runs.json` with each run's
role, wake reason, times, public summary and the records it wrote, and the
strip's `live.awake[].wake_reason`. **User's call 2026-10-05 (register):
summaries and thinking are public**, behind the feed's safety check.

## Tasks, in order (commit after each)

1. **Run summaries as replies.** Render each run from `runs.json` as a reply
   in the thread of every record it wrote (`by_thread`), as a post from that
   role: kind label "Summary", its wake reason in plain words, its duration,
   and the summary text. Keep the approved look; it nests one level under the
   opening post like the other replies.
2. **Wake reason in the strip.** Check `live.awake[].wake_reason` renders in
   the strip ("woke for routine review") from the real field, and the last
   run line shows it too.
3. **"What it checked" from real calls.** For each agent post (proposal,
   ruling, ask, answer, amend), list the read calls that role made in the run
   that wrote it, before the write: tool id plus a short note. The run gives
   role and time window; `dfmcp-server`'s journal on VM 103 has one JSON line
   per call (role, tool_id, ts, is_error, result_chars, arguments). The
   publisher already reads that journal (`dfqueue/live.py`). Decide the note:
   tool arguments are not public (`dfqueue/live.py` drops them today), so the
   public note may be only the tool's display name and whether it errored;
   operator may show arguments. Say what you chose. Carry it as `calls` on the
   feed item or in `runs.json` keyed by record id, whichever fits the feed's
   existing shape; the page reads `item.calls`.
4. **Thinking: find out first.** Does openclaw keep the model's reasoning
   (DeepSeek returns `reasoning_content`) anywhere: the `--json` output the
   conductor parses (`conductor/runner.py`), session files under
   `/opt/openclaw/config`, or the run archive under
   `/var/lib/conductor/runtime/` on VM 106 (read-only)? Report exactly what
   exists. If it is available, carry it like the summary (through
   `conductor.report`'s end call, capped, safety-checked, public) and fill
   `item.thinking` on the records that run wrote. If it is not, say what it
   would take, and do not build a workaround.
5. **Operator page label.** The operator and public pages look identical; the
   user could not tell which they were on. Add a small, quiet "Operator" mark
   in the operator page's header. Minimal text.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Read the UI rules: `C:\Users\wills\.claude\projects\c--website-projects-df-automation\memory\site-ui-preferences.md`.
- Touched surfaces: `web/stream/`, `dfqueue/feed.py`, `dfqueue/live.py`,
  `dfqueue/runs.py`, `scripts/stream_publisher.py`, `conductor/` (task 4
  only), `dfmcp/conductor_tools.py` (task 4 only),
  `scripts/preview_stream_live.py` and the demo fixture (so the preview shows
  summaries, checks and thinking without hand-edited data), tests.
- Your worktree has no `.env`: use `DF_ENV_FILE=c:/website-projects/df-automation/.env`
  for `scripts/vm-ssh.sh`; read `.env` by key only. Host access is read-only.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green; headless
  check of both pages at 1280x700, no console errors.

## Done when

Tasks 1, 2, 3 and 5 built and tested, task 4 answered (and built if the data
exists), the deploy targets listed, and a Result section here.

## Plan (executor, 2026-10-05)

- Task 3 carries checks in `runs.json` as `calls_by_record: {record_id: [{tool, note, n, failed}]}`:
  reads only (registry `write` flag from `tools.json`), the record's role, inside
  the run window, before the record's own timestamp. Note is the tool's public
  one-line description; no arguments ever. Journal lookback raised so older runs keep theirs.
- Task 1 renders `runs.json` as "Summary" replies built client side from `by_thread`.
- Task 4: read-only investigation first, no workaround built.
- Task 5: small "Operator" mark in the operator header.
