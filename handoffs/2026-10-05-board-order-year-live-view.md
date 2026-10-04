# Handoff: board newest-first, the year off by one, and a live "who's awake" view

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; no VM writes,
no deploys** (the orchestrator deploys after review). Read-only reads of the
live hosts through `scripts/vm-ssh.sh` are fine where a task says so.

## Why

The user watched the first conductor cycle on the public site
(dwarf-fortress.willsmith.nz, the Board view) on 2026-10-02 and asked for
three things. See `Working.md` (the 2026-10-02 notes) and
`evals/live/2026-09-25-first-real-conductor-cycle/` for how a cycle runs.

## Tasks, in order (commit after each)

1. **Newest first.** The Board's feed lists entries oldest first, grouped
   under game-date headings. Make it newest first: newest date group at the
   top, newest entry first within a group. Applies to the public and
   operator pages. Keep reply threading readable (a ruling still shows
   against its proposal).
2. **The year reads one out.** Feed entries are headed e.g. "6 Galena, year
   32" while the fort's clock (`clock.status` / `vitals.summary`:
   `cur_year` 31, `cur_year_tick` about 247k) says year 31. Find where the
   feed turns a tick into a game date (`dfqueue/feed.py` or nearby) and
   prove with a test which is right, using DF's own calendar (1200 ticks a
   day, 28 days a month, 12 months, 403,200 ticks a year) and the absolute
   tick (`abs_tick` 12,746,121 at year 31 tick 246,921 is a real pair to
   check against). Fix the wrong side. Do not guess: if the records only
   carry a cycle or abs tick, show the arithmetic.
3. **Live "who's awake" view (stream page slice S2, conductor wake and run
   records).** Today the site shows nothing while an agent is mid-turn, so a
   6-minute Architect run looks stalled. Wanted: on the Board, a compact
   strip showing whether a cycle is running, which role is awake, why it
   woke (the wake reason), how long it has been going, and its most recent
   tool call by display name; plus, after a run, its duration and cost.
   Sources: the conductor writes `status.json` and an archived per-run record
   on VM 106 (`conductor/status.py`, `CONDUCTOR_STATUS_PATH`,
   `CONDUCTOR_RUNTIME_ROOT`); tool calls are logged by `dfmcp-server` on VM
   103 (journald, one JSON line per call with role and tool). The publisher
   runs on VM 103 every 5 s (`scripts/stream_publisher.py`). Design the data
   path (which host produces what, how it reaches the publisher, what is
   public versus operator only) and write it into this handoff before
   building. Prefer the simplest path that needs no new open port and no new
   credential; if every path needs one, stop and say so in the Result
   rather than adding one. Public output carries no tool arguments, no
   costs, no hostnames; operator output may carry costs.

## UI rules (the user's, firm)

Read `C:\Users\wills\.claude\projects\c--website-projects-df-automation\memory\site-ui-preferences.md`.
In short: the page never scrolls, only inner panes; minimal text, no
intros; dark Terminal 2 look only; counts spelled out. The strip must fit
without pushing the board's tabs off one screen at about 700px height.
Bump the asset version in `web/stream/index.html` and `operator.html`.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `web/stream/` (app.js, style.css, html), `dfqueue/feed.py`,
  `scripts/stream_publisher.py`, `conductor/status.py` (only if the view
  needs a field it lacks), `infra/deploy-manifest.yaml` (only new files this
  stream ships), and tests. Not `agents/`, not `infra/*.service*`.
- Public repo: no hostnames, IPs or tokens. No em dashes. No attribution
  lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green before done.

## Done when

All three tasks committed with tests, a local preview recipe (how the
orchestrator can serve it on localhost with sample data showing a running
cycle), the exact deploy targets needed, and a Result section here.

## Result (executor, 2026-10-05)

### Task 2 (year): done. `feed.render_game_date` added 1 to the year.
The fort's absolute tick is built as `cur_year * 403,200 + cur_year_tick`
(`conductor/game_tick.py`), so `tick // 403,200` already IS `cur_year`:
12,746,121 = 31 * 403,200 + 246,921, year 31, day 205 of the year = the
10th of Sandstone. The `+ 1` made it "year 32". Fixed (no offset), tests pin
the real pair, and the old year-1 expectations became year 0.

### Task 1 (newest first): done.
`groupByDay` in `web/stream/app.js` now sorts newest day first and newest
entry first within a day; undated ("Now") lines sit on top. A ruling that
answers a proposal now sits above it in a thread, so each such line carries a
faint "re: <proposal type>" tag. Applies to the project and proposal
conversations and the Agents tab's recent lines. The public and operator pages
share `app.js`, so both change. Node-based test in
`dfqueue/tests/test_site_js_order.py`.

### Task 3 design (written before building): the data path
Facts found. (a) The conductor writes `status.json` and the cycle archive
(`summary.json`, `briefings.json` with each role's `wake_reason`,
`run-<role>.json` with `wall_clock_seconds` and `cost_usd`) only at the END of
a cycle, so nothing on VM 106 says "running" mid-turn. (b) `dfmcp-server` on
VM 103 logs every call as one JSON line (role, tool_id, ts, duration_ms,
arguments). (c) The publisher is on VM 103 and already writes a per-fort
`status.json` (today a placeholder) that the page already fetches.
(d) Any 106 -> 103 transport (publisher pulling over ssh, or the conductor
pushing files) needs a new credential; the only existing 106 -> 103 channel
is the conductor's MCP token, and a new MCP tool means an `agents/` allowlist
edit, outside this stream.

Chosen, no new port, no new credential:
- **Tier A (live, built):** the publisher reads `dfmcp-server`'s journal on
  its own host (`journalctl -u dfmcp-server.service -o cat --since ...`,
  needs only journal-read group membership for the publisher's user). A role
  is "awake" while its latest call is under 240 s old; its run started at the
  first call of the burst (gaps under 240 s); its last tool is the latest
  call's tool id. A cycle is "running" while any role (or the conductor) is
  awake. Arguments are never copied. This answers "is anyone working, who,
  doing what, for how long" with no help from VM 106.
- **Tier B (built, inert until fed):** the publisher can also read a local
  directory laid out like the conductor's runtime root (`--conductor-dir`):
  `status.json` plus `cycles/cycle-*/{summary,briefings}.json` and
  `run-<role>.json`. From it: the wake reason and the last completed run's
  duration (public) and cost (operator only). It also honours an optional
  `running` block in `status.json` ({role, wake_reason, started_at}); a small
  helper `conductor.status.status_running` defines that contract, but the
  conductor does not call it yet (that is a `cycle.py` edit, outside this
  stream's surfaces). **Getting those files from 106 to 103 needs one
  restricted credential or an MCP tool; NOT added, orchestrator's call.**
- Output rides the existing per-fort `status.json` (`live` key) in both the
  public and operator trees; the page polls it every 4 s on its own, separate
  from the `head.json` gate, so the strip moves between feed changes. Public
  `live` carries role, awake flag, elapsed, tool id, wake reason, last
  duration. Operator adds cost and the call's error flag. Nothing carries
  arguments, hostnames or addresses.

### Task 3 as built
- `dfqueue/live.py` (journal parse, journal reader, conductor-dir reader,
  `build_live`, `live_hash_payload`); publisher flags `--live-journal`,
  `--conductor-dir` (env `STREAM_PUBLISHER_LIVE_JOURNAL`,
  `STREAM_PUBLISHER_CONDUCTOR_DIR`), both OFF by default so status.json stays
  the placeholder until switched on. The change hash ignores `as_of` and
  `elapsed_s`, so an idle clock does not republish.
- `conductor/status.py::status_running` defines the mid-run block; the
  conductor does not call it yet (cycle.py, not in this stream's surfaces).
  Until it does, a live run shows no wake reason; the last finished run's
  reason shows once its archive is on this host.
- Page: persistent one-line strip above the Season goal line
  (`.e-live-strip`, 28px, never wraps), polls `status.json` every 4 s apart
  from the head.json gate, elapsed ticks each second. Hidden when there is no
  live data. Checked headless at 1280x700 on both pages, running and idle.
- Assets bumped to v21 in both html files.

### Checks
Ambient `python -m pytest`: 2517 passed, 3 skipped (the date-sensitive wiki
test passed today). `dfmcp/tests` in `.venv-dfmcp`: 768 passed. New tests:
`dfqueue/tests/test_live.py` (11), `tests/test_stream_publisher_live.py` (5),
`conductor/tests/test_status_running.py` (2), `dfqueue/tests/test_site_js_order.py`
(2), plus the year tests in `test_feed.py`.

### Preview recipe
`python scripts/preview_stream_live.py` (add `--idle` for the last-run line,
`--no-serve` to only write data): exports the board demo fixture to the
gitignored `web/stream/data/`, writes a `live` block (Architect awake about
four minutes, last tool zone.list, an earlier Overseer run), serves
`web/stream/` on http://127.0.0.1:8934/index.html and `/operator.html`.

### Deploy targets (orchestrator; nothing deployed)
1. Relay web public and operator (`/srv/stream/web-public`, `/srv/stream/web-operator`
   manifest blocks): `web/stream/app.js`, `style.css`, `index.html`,
   `operator.html` (v21).
2. VM 103 `vm103-stream-publisher` manifest block: `scripts/stream_publisher.py`,
   `dfqueue/feed.py`, `dfqueue/live.py` (new, added to the manifest). Then add to
   `/etc/stream-publisher/env`: `STREAM_PUBLISHER_LIVE_JOURNAL=true`, make sure the
   publisher's user can read the journal (`systemd-journal` group; verify
   with `journalctl -u dfmcp-server.service -n 1` as that user), and the
   timer picks it up on its next 5 s run. Year fix and ordering take effect
   with the same deploy; published feed items re-render the new year
   automatically (dates are computed each cycle, not stored).
3. Not done, needs a decision: delivering the conductor's runtime files
   (`status.json`, `cycles/`) from VM 106 to the publisher host so
   `STREAM_PUBLISHER_CONDUCTOR_DIR` has something to read (needs a restricted
   credential or an MCP tool), and a `status_running` call in
   `conductor/cycle.py` before each runner launch so a live run shows its
   wake reason.
