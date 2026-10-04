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

## Result (executor, 2026-10-05)

**Built and tested: tasks 1, 2, 3, 5. Task 4 answered: no reasoning text exists anywhere, nothing built.**

1. **Summaries as replies.** `summaryItems(items, runsDoc)` in `web/stream/app.js`
   turns each run in `runs.json` (via `by_thread`) into a "Summary" post from
   that role, placed after the last record the run wrote in that thread, nested
   one level under the opening post. Meta line: wake reason in words and
   duration ("woke for routine review · 7 min"). A run with no summary (failed,
   or withheld by the safety check) adds nothing. `StreamPage` loads
   `runs.json` in `loadAll` and refreshes it in `pollLive` (redraws only when
   it changed, ignoring `as_of`), since a run's summary lands after its records.
2. **Wake reason in the strip.** Already rendered from the real field
   (`live.awake[].wake_reason`, and `last_runs[role].wake_reason` for the
   last-run line); now both use the shared `wakeWords`. Verified in the preview
   ("Architect 4m 10s zone.list woke for ask open"). No change needed beyond
   the helper.
3. **"What it checked".** `runs.json` gains `calls_by_record: {record_id:
   [{tool, note, n, failed}]}` (public and operator identical). Source: the
   dfmcp call journal the publisher already reads. Reads only (a tool whose
   registry `write` flag is set is dropped), the record's own role, inside the
   run's started..ended window, up to the record's own timestamp, one row per
   tool with a count and an errored flag. **Note chosen: the tool's public
   one-line description (first sentence of the same text `tools.json`
   publishes, capped at 80 chars), never arguments**, on both pages (operator
   shows no arguments either: `parse_call_lines` still drops them). The page
   uses `item.calls` when non-empty (the operator feed always sends `[]`),
   else `calls_by_record[item.id]`. `JOURNAL_LOOKBACK_MIN` raised 30 to 720 so a
   run keeps its checks for about 12 hours; after that the journal no longer
   has them and `calls_by_record` drops that run's entries (summaries stay).
   Publisher (`scripts/stream_publisher.py`) passes calls, the tools map from
   `site_data.build_tools_json()` and each record's `ts` into `build_runs`.
4. **Thinking: does not exist.** Checked read-only on VM 106: (a) the `--json`
   envelope (sample `evals/live/2026-09-14-architect-first-charter/run.json`)
   carries `finalAnswer`/`payloads`, `usage.reasoningTokens` (a count only),
   `toolSummary`, model, `sessionId`; no reasoning text, and the conductor
   keeps only a summary of it anyway (`run-<role>.json`: ok, cost, wall clock,
   `tool_summary` tool names, final answer; `RunResult.raw` is not archived).
   (b) `/var/lib/conductor/runtime/cycle-*/` holds briefings, clock changes,
   `run-<role>.json`, `summary.json`: nothing. (c) `/opt/openclaw/config`:
   `agents/<role>/agent/openclaw-agent.sqlite` has `transcript_events`,
   `trajectory_runtime_events`, `session_transcript_*` tables, all with 0
   rows (untouched since 2026-09-15, only WAL churn since); `state/openclaw.sqlite`
   session tables also 0 rows. So `agent exec --json` runs in an ephemeral
   session that persists no transcript, and the envelope drops the reasoning
   text. **What it would take:** either openclaw persisting the session
   transcript (a config or flag on `agent exec`, unknown, needs reading
   openclaw's docs or source on the host: look for a transcript/trajectory
   option) and the conductor reading it from the mounted state dir after each
   run; or the envelope including reasoning when asked. Then it goes through
   `conductor.report`'s end call like `final_answer` (capped, safety-checked,
   `PUBLIC_*` switch). Not built. `item.thinking` stays empty on real data;
   the preview shows no thinking (no fake data added).
5. **Operator mark.** A small outlined "Operator" tag (existing `.scope`
   style) beside the brand in the site header when `mode === "operator"`.
   Public page has none.

**Tests.** Ambient `python -m pytest` in the worktree: 2588 passed, 3 skipped,
0 failed (it includes `dfmcp/tests`; nothing under `dfmcp/` or `conductor/`
was changed, so `.venv-dfmcp` was not separately run). New: 2 in
`tests/test_stream_publisher_runs.py` (checks: window, role, before-record,
write tools dropped, errors, no arguments), 3 node tests in
`dfqueue/tests/test_site_js_threads.py` (summary placement and nesting,
blank runs skipped, checks incl. operator's empty `calls`).

**Headless check** (Chrome via DevTools protocol, 1280x700, preview data):
both pages load with zero uncaught exceptions or console errors (only 404s
filtered); page does not scroll (scrollHeight <= innerHeight); operator page
shows the Operator mark, public does not; opening "Dig a second stair" shows 2
Summary replies and a "What it checked" box on both pages; screenshots read
correctly. Caveat: the error listener was not itself proven by injecting an
error.

**Preview.** `scripts/preview_stream_live.py` now writes a `runs.json` for
both sides, built by `live.build_runs` from run rows linked to the demo
fixture's records by the real `records_in_window` plus a made-up call journal.
Cache-bust bumped to `?v=37` in both HTML pages.

**Deploy targets (not run, host work is the user's call):**
- Relay web root: `web/stream/app.js`, `index.html`, `operator.html` (v=37).
  `style.css` unchanged.
- VM 103 publisher (`stream_publisher.py` unit): `scripts/stream_publisher.py`
  and `dfqueue/live.py` (the publisher imports `dfqueue` and the
  `dfmcp` registry via `site_data`; it already did). Restart the publisher unit
  so it picks them up; `runs.json` then gains `calls_by_record` on the next
  cycle. The publisher's journal read now looks back 720 minutes (needs
  journal retention at least that; it already reads `dfmcp-server.service`).
- Not needed: `dfmcp-server`, `conductor`, VM 106 (nothing changed there).
