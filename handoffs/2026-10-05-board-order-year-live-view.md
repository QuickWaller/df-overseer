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
