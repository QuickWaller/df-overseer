# Handoff: an explicit "safe to resume" verdict, and pause alerts on the site

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no unpause, no deploys.** Start only after
`handoffs/2026-10-05-stuck-job-watch.md` has merged (both touch `conductor/`).

## Why (user's calls, 2026-10-05)

The pause watchdog (`handoffs/2026-10-05-pause-safety.md`,
`conductor/pause_watch.py`) wakes the Overseer for an unexplained pause and
currently treats a clean, un-escalated Overseer run as the decision to
resume, copied from the tripwire branch. The user agreed that silence is not
consent here: an unexplained pause may be a threat nobody looked at, and a
clean run cannot tell "it is fine" from "I did not get to it". The register
rule already stands that decisions are read from tool calls, never from
prose (`agents/overseer/role.md`, Escalation).

Also agreed: until Telegram exists, alerts go to the site's live status strip,
and a pause the watchdog attributes to a human is shown there too, so the
user can see it noticed and is waiting. Timings stay as they are (600 s
grace, 1800 s alert interval).

## Tasks, in order (commit after each)

1. **Plan, written here.** Where the verdict lives (preferred: a small
   Overseer-only MCP tool, e.g. `pause.verdict` with `resume: true|false`
   and a required one-line reason, recorded where the conductor can read it
   mechanically for that run, the same way it detects `queue.escalate`).
   The Overseer gets no resume power: the conductor still does the resume,
   once, with the tick verified, and never over a tripwire or escalation.
2. **Build it.** Watchdog rule: after an `unexplained_pause` Overseer run,
   resume only on an explicit `resume: true` verdict from that run; a
   `false` verdict, no verdict, or an escalation keeps the fort paused and
   raises an alert. Update the decision table in the pause-safety handoff
   and `docs/TRAPS.md` if it states the old rule. Charter: one short
   paragraph in `agents/overseer/role.md` saying when and how to give the
   verdict.
3. **Alerts on the site.** The conductor's status block (`conductor/status.py`
   `pause_watch`) already carries the watchdog's state; carry an `alert`
   (reason, since) and a `waiting_on_human` flag through to the publisher's
   live strip (`dfqueue/live.py`, public-safe text only through the feed's
   safety net) and show it in the strip on `web/stream/` in the existing
   status colours (an alert in the red state shade, waiting in the hold
   shade). Keep the strip one line. Bump the asset version.
4. **Tests**: watchdog decisions for each verdict case, the tool's role gate
   (Overseer only), the strip's rendering in the node tests on the real
   `app.js`, and a headless check at 1280x700, no console errors.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early and after
  every milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`.
- Touched surfaces: `conductor/pause_watch.py` and its wiring, `conductor/status.py`,
  `dfmcp/` (the new tool only; not `gotchas_store.py`),
  `agents/overseer/tools.yaml`, `agents/overseer/role.md` (one paragraph),
  `scripts/dfhack/TOOLS.yaml` only if the tool registry needs the entry there,
  `dfqueue/live.py` (strip fields only), `web/stream/` (strip only),
  `docs/TRAPS.md`, tests, tool-count docs.
- No armok powers. Public repo: no hostnames, IPs or tokens. No em dashes.
  No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green.

## Done when

The verdict tool, the watchdog rule, the charter paragraph and the strip
alerts built with tests, deploy targets listed, and a Result section here.

## Result

### Plan (task 1, written before building)

Verdict design. The conductor sees only tool NAMES from a run
(`toolSummary.tools`), never arguments, so a true/false verdict cannot be read
from the run envelope. The verdict therefore lives server-side, where the
conductor can read it mechanically over the MCP connection it already holds:

- `pause.verdict` (native, Overseer only via `sole_writer_only`): `resume`
  (bool, required) and `reason` (one line, required). The server stamps the
  time and stores one row in a small SQLite file beside the queue database
  (`<stem>.pause.sqlite3`). It does nothing to the fort and cannot resume it.
- `pause.verdict_read` (native, conductor only, allowlist plus a handler
  refusal): `since_id` returns the verdicts written after that id plus the
  latest id. The conductor reads a baseline id before the Overseer run and the
  verdicts after it, so only a verdict from THIS run counts (no clock
  comparison across hosts).
- Both live in `dfmcp/conductor_tools.py` (the conductor-owned native module),
  so the existing native-tool wiring picks them up.
- Watchdog rule (`finish_after_overseer`): resume (once, tick verified) only
  when the run was clean, did not escalate, and the last new verdict has
  `resume: true`. A `false` verdict, no verdict, an unreadable verdict, or an
  escalation keeps the fort paused and raises an alert. The tripwire branch is
  untouched. The Overseer gains no `clock.resume`.
- Site: `pause_watch` status carries `alert` (reason, since) and
  `waiting_on_human` (the plain-pause grace wait) through `dfqueue/live.py`
  into the strip on `web/stream/`.

### Built (all tasks done)

- **Verdict tools** (`dfmcp/conductor_tools.py`, native): `pause.verdict`
  (Overseer only: `sole_writer_only` plus a handler check; `resume` bool and a
  one-line `reason`, both required, reason capped at 300 chars) and
  `pause.verdict_read` (conductor only: allowlist plus a handler refusal).
  Verdicts live in `<queue stem>.pause.sqlite3` beside the queue database, the
  server stamping time and id. Allowlists: `agents/overseer/tools.yaml`
  (`pause.verdict`), `agents/conductor/tools.yaml` (`pause.verdict_read`).
  Neither is in `SYSTEM_CLASS_TOOL_IDS` and the Overseer still has no
  `clock.resume` (a test asserts it).
- **Watchdog rule** (`conductor/pause_watch.py`, `conductor/cycle.py`): the
  conductor reads a baseline verdict id before the Overseer's `unexplained_pause`
  run and the verdicts after it; `finish_after_overseer` resumes (once, tick
  verified) only on `resume: true` from that run. `false`, no verdict, an
  unreadable store/baseline, an escalation or an unclean run: stay paused and
  alert. The tripwire branch is untouched. Pause-safety table row 5 and its
  open-question bullet, and `docs/TRAPS.md`, updated; charter paragraph
  ("Unexplained pauses: the verdict") added to `agents/overseer/role.md`.
- **Site**: `WatchState` keeps `alert_reason`/`alert_since` for the episode;
  `pause_watch` in the status block now carries `alert` {reason, since} and
  `waiting_on_human` (the plain-pause grace wait). `dfqueue/live.py`
  (`build_pause`, `read_conductor_dir`) puts `live.pause` in the feed: the
  public reason goes through `feed.find_unsafe_pattern` (generic fallback),
  capped at 160 chars; ignored once `status.json` is older than 1800 s.
  `web/stream/app.js` (`pauseStripSegment`) and `style.css`: alert in the
  `--bad` red, waiting in the hold shade; one line; with a role awake the
  alert shows a short "Paused" plus age (reason in a tooltip), idle it replaces
  the last-run line and shows the reason. Asset version bumped to v59 in
  `index.html` and `operator.html`.
- Tool counts: overseer 99 to 100, conductor 20 to 21 (`dfmcp/tests/
  test_gotchas_tools.py`, `docs/STATE.md` by hand: it is generated, so rerun
  `scripts/drift_check.py --write-state` after deploy).

### Verified

- `python -m pytest` (ambient, `lupa` on PYTHONPATH): 2718 passed, 3 skipped
  (after fixing one leaked-address hit in my own test; the known
  `test_wiki_check` failure did not fire).
- `dfmcp/tests` in `.venv-dfmcp`: 797 passed. Race test not hit.
- Headless Chrome at 1280x700 against the preview data (`web/stream/data`,
  port 8957 since 8934 may be taken): alert and waiting states, with and
  without a role awake, one 28 px line, no horizontal overflow, console clean
  (only the preview server's favicon 404).

### Deploy targets (nothing deployed)

In order: `vm103-dfmcp` (new tools; restart `dfmcp-server.service`; do this
first, since a conductor without the read tool treats every run as silent, the
safe direction), `vm103-stream-publisher` (`dfqueue/live.py`), `vm106-agents`
(overseer `role.md`, `tools.yaml`, conductor `tools.yaml`), `vm106-conductor`
(`conductor/`), `relay-web` and `relay-web-operator` (`web/stream`, v59). Then
re-measure live tool counts (overseer 100, conductor 21). Unverified live: a
real Overseer calling `pause.verdict` through openclaw.
