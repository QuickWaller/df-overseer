# The stream page: chat, projects, operator view, and the data behind them

Date: 2026-10-01. Researcher (Opus), design only, from
`handoffs/2026-10-01-stream-page-design.md`. Nothing here is built. Every
claim about existing code is marked **verified** (read in this repo at
`9fa7fde`) or **proposed**; departures from what the user agreed are marked
**DEPARTURE** so they can be accepted or struck one by one.

## Plan (committed first, in case this run is cancelled)

1. Short answer.
2. What exists today (verified): records, links, stamps, the conductor's
   events, the call log, vitals, the relay, the portfolio site.
3. Q1, the data: sources, the public and operator projections, the schema
   additions ("about", "reply to", project public fields, conductor events).
4. Q2, the pipeline: publisher, push or poll, snapshot plus incremental,
   history, ordering, restarts, kill switch, cost at a year.
5. Q3, where the page lives and how the operator view is gated.
6. Q4, the UI: the mockup critiqued, threading, a project's life, mobile,
   the season archive, the ten-second test, ambient mode.
7. Q5, safety.
8. Q6, the slice plan.
9. Departures from the brief, collected.
10. Decisions for the user.
11. What could not be verified.

## 1. Short answer

- **One store, one publisher, static files.** Everything the page shows is
  (or becomes) a record in the queue on VM 103, including the conductor's
  wakes, which today live only in journald and a cycle archive on VM 106. A
  publisher on VM 103 reads the queue (plus the `dfmcp` call log for the
  operator side), builds two projections, and **pushes static JSON files
  outbound** to the relay over a second, directory-restricted SSH key. The
  browser **polls** a tiny head file; history is **immutable segment files**
  fetched on demand. No new server process, no inbound port anywhere, the
  queue itself never reachable from outside.
- **The page lives on the relay, beside noVNC, same origin.** The public
  page is served under the existing public viewer hostname; the operator
  page is the same code served under the existing admin hostname, behind the
  Cloudflare Access application that already gates it. The portfolio site
  (GitHub Pages, static) links to it, as it links the viewer today.
  **DEPARTURE**: the mockup's Public / Operator switch does not appear on the
  public page at all. Operator data is never at a public URL, so a switch on
  the public page could only ever be decoration or a leak.
- **Schema additions are few, because most links already exist or can be
  derived.** Stored: `reply_to` on the kinds that have no link today (asks,
  escalations, passes, proposals answering a commission, user and Overseer
  messages), a `run_id` stamped server-side on every record (the join to tool
  calls and to the wake that caused it), new kinds for the conductor's
  `wake` and `run`, the season `goal` and its `review`, and the user's
  messages; public fields on projects (`public_title`, a short `label` per
  step, hold **codes** from a closed vocabulary). Derived by the publisher,
  never stored: each item's thread root, and which project, step or goal it
  is about.
- **Safety is layered, and the allowlist stays the guard.** Public text is
  only ever a field written for an audience (`public_rationale` and the new
  public fields), never tool output, never a hold reason a tool wrote. On top
  of that: a write-time refusal of URLs, addresses, paths and token-shaped
  strings in public fields (the model rewrites, nothing is redacted); a
  publish-time canary check against the estate's real hostnames and token
  prefixes (kept in gitignored `infra/local.*`), which **withholds** a record
  rather than editing it; and three kill switches at three layers.
- **The UI keeps the mockup's shape and fixes what a first-time viewer would
  trip on**: a "right now" line saying who is thinking and why (the fort is
  paused or quiet most of the time, and an empty chat reads as broken), a
  one-sentence explainer, game dates as the primary clock, proposals whose
  verdict badge updates in place, reply quotes instead of indented threads,
  a project timeline (commissioned, drafted, accepted, held, amended, done or
  abandoned, checked), a season archive that becomes the chronicle, and an
  ambient mode for the screen on the wall that `docs/PURPOSE.md` names.
- **Build private first.** The first live slice is the operator view only,
  from the records that already exist; the public view follows once the
  user has read what it would show. Slices in §8.

## 2. What exists today (verified at `9fa7fde`)

**The queue** (`dfqueue/schema.py`, `dfqueue/store.py`). One SQLite database
per fort on VM 103, written only through `dfmcp` tools. Eleven kinds:
`proposal`, `pass`, `ruling`, `executed`, `ask`, `answer`, `escalation`,
`project`, `observation`, `amend`, `abandon`. Every record carries `id`
(a per-kind counter, `proposal-0004`), `ts` (wall clock UTC), `kind`, `role`,
`cycle` and `snapshot`. **`cycle` is the absolute game tick**
(`year * 403200 + tick within year`, `dfqueue/grade.py`
`game_tick_from_overview`), stamped server-side by a live `overview.get`
read on every write (`dfmcp/queue_tools.py`, "cycle/snapshot: a stand-in").
There is **no global sequence field**; the only total order is SQLite's
`rowid` (`store.load` orders by it). Records are append-only and never
deleted, so `rowid` is stable in practice.

**Links that already exist** (all verified in `schema.py` `KIND_FIELDS`):

| Kind | Points at |
|---|---|
| `ruling` | `proposal_id` |
| `executed` | `ruling_id`, optional `step_id` |
| `answer` | `ask_id` |
| `ask` | optional `proposal_id` (a fact-check) |
| `project` | `from_ruling`, optional `objective_id` |
| `observation`, `amend`, `abandon` | `project_id` (and `step_id` for observation) |
| `proposal` | nothing (only `duplicate_of`) |
| `pass`, `escalation` | nothing |

So a chain proposal, ruling, project, executed, observation, amend, abandon
is fully linked already. What has no link is exactly what the brief
suspected: why a proposal was made (a commission, a wake), what an ask or an
escalation is about, and anything involving the user or a season goal.

**The public allowlist** (`dfqueue/render.py` `ALLOWED_PUBLIC_FIELDS`):
`id, ts, kind, role, type, public_rationale, decision, suggested_priority`.
Only `proposal` and `ruling` carry `public_rationale`. So today's allowlist
publishes **nothing readable** for an `executed`, `ask`, `answer`, `pass`,
`escalation`, `project`, `amend` or `abandon` record, only its kind and role.
That is the correct failure (silent omission, not a leak), and it is also
why most of the chat needs new public fields rather than a longer allowlist.

**Project state** (`store.project_status`). Status is `active`, `done` or
`abandoned`, computed; `counts` of step targets by state (`waiting`,
`ready`, `held`, `issued`, `done`, `failed`, `abandoned`); `top_blocker`
with the held target's `reason`; `version` (1 plus the number of amends).
**The hold `reason` is text a tool or the executing role wrote**, not text
written for an audience; it cannot be published as is (§7).

**The conductor's events are not in the queue.** They live on VM 106:
journald lines (`conductor/status.py` `log_cycle`), an always-overwritten
`status.json` (state, last cycle, clock level, roles woken, tripwire,
escalated), and a per-cycle archive directory (`conductor/archive.py`:
`summary.json`, briefings, clock changes, one `run-<role>.json` per role
with cost, wall clock, tool summary and final answer). **The wake reasons
themselves are not archived on a real run**: `_archive` in
`conductor/cycle.py` writes `roles_woken` but not the `wakes` list (reason,
detail, roles, clock), which is kept only in the dry-run `plan`. The mockup's
"Season change. Waking the Overseer" line has no stored source today.
The conductor cycles every 60 s by default (`conductor/config.py`), so
most cycles are quiet: about half a million a year if it ran continuously.
Quiet cycles must never become chat lines.

**The `dfmcp` call log** (`dfmcp/server.py`, register 2026-09-14). One JSON
line per `tools/call` to journald on VM 103: `ts`, MCP `session_id`,
`request_id`, **`client` (the caller's network address)**, `role`, `tool`,
`tool_id`, full `arguments`, `is_error`, `error` (up to 500 chars),
`result_chars`, `duration_ms`. Queue records do **not** carry the session
id, so records cannot be joined to the calls that produced them today
except by role and time window.

**Vitals** (`vitals.summary`, read by the conductor every cycle): alive,
dead total, worst hunger and thirst as categories, warning count. **No food
or drink counts**: the mockup's status strip (Drinks 34, Food 120) needs a
stock read the conductor does not make each cycle.

**The live view** (ROADMAP "Live human viewing", `scripts/provision_relay.py`).
VM 103's x11vnc reaches the relay's loopback through a reverse SSH tunnel on
a key restricted with `permitopen` to one port; websockify and noVNC on the
relay serve the viewer; a dashboard-managed Cloudflare Tunnel publishes it
under the public viewer hostname. A second, separate tunnel publishes a
full-control channel under an admin hostname, gated by a Cloudflare Access
application (the user's own account only). Today the relay serves noVNC
through websockify's own built-in web server; there is no general static
file server on it.

**The portfolio site** (sibling checkout, read only): React and Vite,
deployed to GitHub Pages by GitHub Actions (its README). Its
`public/dwarf-fortress/index.html` is a static page with a screenshot slot
that was never wired up (the image base URL is empty) and a link to the
live viewer. It cannot run server code or sit behind Access without extra
Cloudflare configuration.

## 3. Q1, the data

### 3.1 Sources

| Source | Where | Feeds | Today |
|---|---|---|---|
| Queue records | VM 103, SQLite | chat, projects, goal, archive | exists, links partial |
| Conductor wakes and role runs | VM 106, journald and archive | "System" chat lines, the "right now" line, operator cost and timing | not in the queue; wake reasons not even archived |
| Fort status (clock, vitals, who is running) | conductor's per-cycle reads | status strip, "right now" line, paused state | `status.json` on VM 106 only |
| Season goal measure | a live signal | goal bar | no goal exists yet |
| `dfmcp` call log | VM 103, journald | operator only: calls under each message | exists, not joinable to records |
| Stock counts (food, drink) | `stocks.food-drink` | status strip | exists as a tool, not read per cycle |
| Live DF job under a step | the reconcile snapshot (register 2026-09-30 item 10) | project drawer | not built |

**Proposed: the conductor's events become queue records**, written through
two new conductor-only `dfmcp` tools, so the page has one ordered store and
the publisher needs no second source on a second VM. Rejected alternative:
a second publisher on VM 106 reading the cycle archive, merged with VM 103's
by wall clock. Two clocks, two publishers and a merge are exactly the
"ordering and gaps" problem the brief asks about; one store removes it.

**Proposed: fort status is not a record.** It changes every cycle (about
half a million times a year) and only its latest value matters, so the
conductor pushes it through a third conductor-only tool, `feed.status`,
which overwrites one file on VM 103 and makes **no** DFHack call. The
conductor already holds every value it carries (vitals, clock level, tick,
who it is about to launch), so this costs no extra game reads. Stock counts
and the goal's measure are added to the conductor's per-cycle read set only
when a goal exists (slice S5), not before.

### 3.2 One item model for every chat line

The publisher turns each record into one **item** (or none):

```
seq        global order (see 3.3), the only ordering key the page uses
id         the record id (proposal-0004)
kind       record kind, or wake / goal / review / message / alarm
speaker    overseer | architect | quartermaster | consultant | executor
           | conductor (shown as "System") | user (shown as the user's name)
tick       absolute game tick (rendered as "12 Limestone (autumn), year 31")
ts         wall clock UTC (rendered as "4 min ago", exact on hover)
reply_to   an item id, or null
thread     the root item of this reply chain (derived, 3.4)
about      [project-0007, project-0007/s3, goal-0002, fort], derived or stored
text       public text only (3.5); absent means the item shows its kind only
badge      e.g. proposal verdict, step outcome, hold code (joined live, 6.3)
```

The operator projection adds the full record, `run_id`, and the tool calls
that share its `run_id` (3.6).

### 3.3 Schema additions that must be stored

Stored only where the link or text cannot be derived.

1. **`seq`, an explicit append counter** (store column, published as
   `seq`). **DEPARTURE from "use what exists"**: `rowid` looks sufficient
   but SQLite's `VACUUM` may renumber the `rowid` of any table without an
   explicit `INTEGER PRIMARY KEY` (SQLite documentation, known behaviour,
   not re-checked in this pass), and `records` keys on a text `id`. A
   published ordering key must never move. Migration: backfill from `rowid`
   order once.
2. **`run_id`, stamped server-side on every record** and added to the call
   log line. Set by the conductor per role run as an MCP request header
   (openclaw's per-server static header map can read an environment
   variable, `research/2026-09-12-openclaw-mcp-auth.md`; per-run use is
   **unverified**). Never a tool argument, same rule as `role` and `cycle`.
   This is the join the 2026-09-25 observability requirement asks for: a
   message, the wake that caused it, and the calls it made all share it.
   Records written outside a conductor run (a manual run, the Telegram
   bridge) get a `run_id` naming their source (`manual-...`,
   `telegram-...`).
3. **`reply_to`** (optional record id), stored only on kinds with no link
   today: `proposal` (the commission it answers), `ask`, `pass`,
   `escalation`, and the new message kinds. Validated to exist at write
   time, like `ruling.proposal_id`. For kinds already linked (ruling,
   answer, executed, project, amend, abandon, observation) the publisher
   derives it; storing it twice would invite the two to disagree.
4. **`about`** (optional, a typed id: `project-0007`, `project-0007/s3`,
   `goal-0002`, or `fort`), stored only on `ask`, `escalation` and message
   kinds, where a model is the only one who knows what it is asking about.
   Validated to exist.
5. **Commissions: `ask` gains `to` (a role) and `expects`
   (`answer` or `proposal`)**, matching the register's 2026-10-01 row that a
   commission is "the same mechanism as a scoped question, with a project as
   the answer". Today `ask` can only reach the Consultant (`ANSWER_ROLE`).
   A proposal whose `reply_to` is a commission is that commission's answer.
6. **Project public fields**: `public_title` (60 characters at most) and
   `public_rationale` (why, one or two sentences) on `project`; the same
   `public_rationale` on `amend` and `abandon`; an optional `label` on each
   step (60 characters, public). Written by the Overseer, who already writes
   the project. A step without a label shows its tool's display name from
   `TOOLS.yaml` data (never its arguments).
7. **Hold codes**: a held target carries `hold_code` from a closed
   vocabulary (`no_material_in_reach`, `site_unreachable`, `site_flooded`,
   `no_worker`, `waiting_for_haul`, `preview_failed`, `tool_refused`,
   `other`), set by the code that records the hold; the free-text `reason`
   stays, operator only. Public text for each code lives in one data file
   (`dfqueue/public_text.yaml`, proposed), the same "one data entry, no new
   code" rule the project applies to tools.
8. **New kinds**, each validated like the rest, each with a single writing
   role:

| Kind | Writer | Carries | Public? |
|---|---|---|---|
| `wake` | conductor | reasons as codes with safe parameters, roles woken, clock level, one `run_id` per role | yes, as a System line from a text table |
| `run` | conductor | `run_id`, role, ok or status, timed out, cost, wall clock, tool count | no (operator) |
| `goal` | overseer | season, measure (`signal`, `op`, `value`, validated against `learning.live_signals` exactly as a prediction is), `public_title`, `public_rationale`, private `reason` | yes |
| `review` | overseer | `goal_id`, result (`met`, `partly`, `missed`), measured value, `public_rationale`, private `lesson`, whether it was a good goal | yes |
| `message` | user (via the Telegram bridge) or overseer | `to`, `text`, `mode` (`message` or `interrupt`, user only), `visibility` (`public` or `private`) | per `visibility` |
| `alarm` | conductor or the watchdog (code) | `alarm_code` from a closed list, private `detail` | code text only |

`user` must become a roster entry of a new kind (`human`), since
`schema.validate` refuses any role not enabled in `agents/ROSTER.yaml`. The
`executor` role, when built, needs nothing new: it reuses `executed` with a
`public_rationale` for the action it chose.

### 3.4 Derived by the publisher, never stored

- **`reply_to` for linked kinds**: ruling to its proposal, answer to its
  ask, executed to its ruling, project to its ruling, amend, abandon and
  observation to their project, review to its goal.
- **`thread`**: follow `reply_to` to the root. Because `reply_to` never
  changes, the thread root never changes, so a published item never needs
  rewriting.
- **`about`**: a proposal becomes "about" the project its ruling founded,
  **retroactively**. The item itself does not change: the page resolves
  `thread` to a project through `projects.json` (4.2), which does change.
  That is how the mockup's chip on the commission line ("Second still") can
  exist before the project did, without mutating history.
- **Project status for display**: `drafting` (commission open, no
  proposal), `awaiting decision` (proposal pending), `active`, `held`
  (active with a held target), `done`, `abandoned`. Only `active`, `done`
  and `abandoned` exist in `store.project_status` today; the rest are joins.
- **Progress as steps, not targets**: "3 of 5 steps", with the current
  step's target count beneath it ("12 of 12 tiles"). Target counts alone
  mislead (a dig step has twelve targets, a build step one).

### 3.5 The public projection

A per-kind allowlist in `dfqueue/render.py` beside `ALLOWED_PUBLIC_FIELDS`,
which it extends rather than replaces.

| Kind | Public text | Never public |
|---|---|---|
| `proposal` | `public_rationale`; `type` as a label | summary, rationale, prediction, preconditions, cost |
| `ruling` | decision, `public_rationale` | reason |
| `executed` | generated: "Step N done: <label>", or the executor's `public_rationale` | actions, arguments, targets, game refs, notes |
| `ask`, `answer` | generated only: "The Architect asked the Consultant a question" | question and answer text (written by one model for another) |
| `pass` | generated: "The Architect had nothing to propose" (collapsed) | reason |
| `escalation` | generated: "The Overseer has asked the user for help" | reason |
| `project`, `amend`, `abandon` | `public_title`, `public_rationale`, step labels | summary, because, steps' tools and arguments |
| `observation` | no line; feeds progress | everything |
| `wake` | text table keyed by reason code | detail text |
| `goal`, `review` | `public_title`, `public_rationale`, result | reason, lesson |
| `message` | `text` when `visibility` is public | private messages entirely |
| `alarm` | text table keyed by alarm code | detail |

Consultant answers are some of the most readable text in the queue and are
wiki-grounded game knowledge, not fort secrets. Publishing them would need a
one-line public summary on `answer`, written by the Consultant for the
audience. The default above keeps them private; it is a decision for the
user (§10).

### 3.6 The operator projection

Everything in every record, plus: the `run` record's cost and timing, the
wake's detail text, and per item the tool calls sharing its `run_id` (tool,
arguments, error, duration). **Minus the call log's `client` field**: it is
a network address, useless on this page, and the operator files sit on the
relay, the most exposed host in the estate (`docs/AGENT-ARCHITECTURE.md`
§13). Briefings and final answers from the cycle archive stay on VM 106 in
v1; the operator page names a run's archive directory only.

The operator page also gets a **"show as public"** toggle: the same page
rendering the public projection, so the user reads exactly what the public
would see before anything goes public. This is the mockup's Public /
Operator switch, moved to where it is safe.

## 4. Q2, the pipeline

### 4.1 Shape

```
VM 106 conductor ──(dfmcp: queue.wake, queue.run, feed.status)──┐
openclaw roles   ──(dfmcp: queue.* writes, run_id header)───────┤
Telegram bridge  ──(dfmcp: queue.message, later)────────────────┤
                                                                ▼
VM 103: queue SQLite   dfmcp call log (journald)   status file
            └──────────────┬───────────────────────────┘
                   publisher (systemd, read only)
                           │  rsync over SSH, OUTBOUND, key restricted
                           ▼  to one directory on the relay
relay: static files ── small static web server (loopback) ── two Cloudflare
       /data/public/                                         tunnels
       /data/operator/                                       (existing)
```

Proposed, all of it. Properties:

- **VM 103 only dials out.** The publisher pushes with `rsync` over SSH
  using a second dedicated key, restricted on the relay side to writing one
  directory (OpenSSH `restrict` plus rsync's `rrsync` helper, the same
  pattern as the viewer tunnel's `permitopen` key). Nothing on the relay
  can reach the queue, and viewer traffic never touches VM 103.
- **The publisher is read only.** It must open the queue with a read-only
  SQLite connection, **not** through `dfqueue.store._connect`, which runs
  `_ensure_schema` and would create tables or migrate on open (verified in
  `store.py`). WAL mode is already on (`PRAGMA journal_mode=WAL`, verified),
  so a reader never blocks the writer.
- **Deterministic output.** Given the same records the publisher writes the
  same bytes, so every file can be rebuilt from the queue at any time. Its
  own state is one cursor (last `seq` published), and losing it costs one
  rebuild, not data.

### 4.2 Files

```
data/public/head.json        state (on | off), generation, last_seq,
                             published_at, the open segment's name, the
                             last 50 closed segments, the season index name
data/public/status.json      fort status, public fields only (from feed.status)
data/public/projects.json    live projects, recent finished ones, the season
                             goal, and the thread-to-project map (3.4)
data/public/open.json        the open segment: items since the last close
data/public/seg/<generation>-<first_seq>-<last_seq>-<hash>.json
                             closed segments of 200 items, immutable
data/public/seasons/index.json, seasons/<year>-<season>.json
                             one file per finished season (6.5), immutable
data/operator/...            the same layout from the operator projection,
                             plus runs/<run_id>.json (the calls of one run)
```

### 4.3 Push or poll

**Poll, from the browser, of static files.** The browser fetches
`head.json` every 5 seconds while the tab is visible (Page Visibility API;
paused when hidden), with `If-None-Match`, and only when `last_seq` moves
does it fetch `open.json` (and any segment closed since). `status.json` on
the same beat. Rejected: Server-Sent Events or WebSockets. They need a
long-lived process on the relay holding one connection per viewer, a new
thing to keep patched and alive, for latency nobody can see: records arrive
at the pace of model runs (a role takes 90 s to 10 minutes,
`evals/live/2026-09-25-first-real-conductor-cycle/`), so a 5 s poll is
invisible. Static files also mean the page keeps working, with its whole
history, when VM 103 or the conductor is down.

Between the publisher and the relay it is push, on change, at most every
5 seconds, plus a heartbeat rewrite of `head.json` every minute so the page
can tell "quiet" from "stale".

**Caching (public only).** `head.json`, `open.json`, `status.json`: a
few seconds at Cloudflare's edge, so a thousand viewers cost the relay one
request per few seconds. Closed segments and finished seasons: long-lived,
immutable, since their names carry a content hash. Operator files: never
cached (they are behind Access; caching authenticated responses at the edge
is a leak waiting to happen).

### 4.4 A new viewer, history, ordering, gaps

- **First load**: `head.json`, then `open.json` plus the newest closed
  segment (the last 200 to 400 items), `projects.json`, `status.json`. Four
  or five small files.
- **Scrolling back**: the next older segment named in `head.json`, then in
  the season index; a "jump to season" menu loads a season's first segment.
- **Ordering**: by `seq` only, never by `ts` or game tick. Game ticks are
  monotonic within a generation but can repeat across a save restore; wall
  clocks drift between hosts. The page merges by `seq` and deduplicates by
  `id`.
- **Gaps**: private items leave holes in the public `seq`, by design. A
  segment is defined by its `seq` range and contains every public item in
  it, so a hole never means a missed item, and the page needs no gap
  detection.
- **Save restores** (register 2026-09-30 item 7: a generation marker per
  save, a queue per generation). A new generation starts new segments; the
  old generation's history stays readable, and the page draws a divider:
  "The fort was restored from an earlier save. The story continues from
  late Autumn, year 31." Honest, and good material for the public report.

### 4.5 Restarts and failure

| Failure | Effect | Recovery |
|---|---|---|
| Publisher restarts | nothing visible | recomputes the open segment from its cursor |
| Publisher loses its cursor | nothing visible | full rebuild; identical bytes, so no churn |
| VM 103 down | page shows history; status goes stale | `head.json`'s `published_at` ages; page says "No news from the fort for 20 minutes" |
| Conductor down (VM 106) | no new wakes; status file stops changing | status carries `updated_at`; page shows "the conductor is not running", which is the truth |
| Relay down | page and video both gone | same as the viewer today |
| Push fails | page stale | publisher retries; an `alarm` after N minutes |

### 4.6 The kill switch, three layers

1. **Cloudflare, from a phone** (proposed): a custom rule, built once and
   left disabled, that blocks `/data/public/` on the public hostname.
   Enabling it stops every viewer at the edge within seconds, independent
   of every VM. Needs the user's dashboard (§10).
2. **Publisher, on VM 103**: `public_enabled: false` in the publisher's
   config. It writes `head.json` as `{"state": "off"}`, deletes the public
   segments from the relay (`rsync --delete`), and keeps the operator side
   running. The page shows "The public feed is paused" and drops any items
   it holds in memory.
3. **Automatic, fail closed**: a canary hit (§7) withholds that item and
   raises an `alarm`; three canary hits within an hour switch layer 2 off by
   itself until the user switches it back on.

No agent can reach any of the three: the switches live in files and
dashboards, not in any role's tool allowlist. Withholding one item is a
fourth, smaller control: an operator `withhold` list the publisher reads;
it rewrites the affected segment under a new hashed name. A cached copy of
the old name persists at the edge until purged, so real removal is layer 1
or a cache purge, not the list alone.

### 4.7 Cost at a year of history

No measured event rate exists; one real eventful cycle (2026-09-25) wrote
about ten records across three roles and made about 25 tool calls for the
Overseer alone. Two assumptions, stated so they can be replaced by
measurements after a week of real running:

| | Quiet (one eventful cycle an hour) | Busy (one every 5 minutes, all year) |
|---|---|---|
| Records per year | about 90,000 | about 1,000,000 |
| Public items, raw JSON (about 300 bytes each) | about 25 MB | about 300 MB |
| Same, gzip (JSON compresses roughly 5x, estimate) | about 5 MB | about 60 MB |
| Closed segments | about 450 | about 5,000 |
| Operator call records (1 KB each, 25 per role run) | about 0.7 GB | about 8 GB |

A viewer's first load stays constant (four or five files, tens of KB)
however long the history grows; only the season index grows, one line per
season. The public side is trivial at either rate. **The operator call log
is the only real volume**, and it has a durability problem worth naming:
it lives in journald on VM 103, which rotates by size, so today the call
log is not a durable record at all. The publisher should copy each call it
reads into its own store (its operator files, or a small SQLite beside the
queue), and the relay should keep operator run files for a window (90
days, the user's call) with the full set kept on VM 103.

## 5. Q3, where the page lives

| | On the relay, beside noVNC (recommended) | On the portfolio site (GitHub Pages) |
|---|---|---|
| Video | same origin: embed noVNC directly | cross origin: iframe the relay; whether the relay allows framing is unverified |
| Feed files | same origin, no CORS | cross origin: the relay must send CORS headers |
| Operator view | same page on the admin hostname, already behind Access | Pages cannot sit behind Access without proxying the domain through Cloudflare and adding a path rule |
| Deploy | a directory on the relay, from this repo | a build of another repo |
| Survives a portfolio rebuild | yes | no |

**Recommended: the relay.** Concretely (proposed): a small static web
server (Caddy or nginx) on the relay, **bound to loopback**, in front of the
existing websockify, serving the page, noVNC's assets, `/data/public/`, and
proxying the websocket path to websockify. The public tunnel's ingress
points at it instead of at websockify directly. A second server block, also
loopback only and reachable only through the admin tunnel, serves the same
page with `/data/operator/`. The loopback binding is the lesson of the
2026-09-11 control channel (`scripts/provision_relay.py` `cmd_webvnc`):
Access must be the whole gate, so the operator files must be unreachable by
any path that skips it. **The operator directory must never be served by the
public server block**; the page chooses its data root by the origin it was
loaded from, and the public block simply has no operator directory to
serve.

**The static-site constraint** is met fully: the page is plain HTML, CSS and
JavaScript, and everything dynamic is a file. If the user later prefers the
portfolio as the home of the page, the page moves as is; only the video
iframe and CORS questions above need answering. The portfolio page itself
should change in slice S2 to link the stream page (and could later show the
season goal and the last three public items by fetching `head.json` cross
origin, which needs one CORS header).

**The operator gate** needs nothing new if the existing Access application
covers the whole admin hostname (**unverified**: whether it is scoped to the
hostname or a path). One consequence to accept or change: the operator page
and full mouse and keyboard control then share one hostname and one login.
That is right for one user. If the user ever wants to show the operator view
to someone without handing them the fort, it needs its own hostname and
Access application (§10).

## 6. Q4, the UI

### 6.1 What the mockup gets right (keep)

The two-column shape with the video left and the conversation right; role
colours with names; the status strip and season goal under the video; the
Chat / Projects split; project chips on messages that open a drawer; the
drawer's steps, current job and the project's own conversation; operator
detail as a monospace line under each message. The palette and IBM Plex
type suit the subject and the user liked them; keep both.

### 6.2 What to change, and why

Each is marked **DEPARTURE** where it changes what the user saw and agreed.

1. **DEPARTURE: no Public / Operator switch on the public page** (§5). The
   operator page has a "show as public" toggle instead.
2. **Add a "right now" line under the video**, the most important addition.
   The fort is paused or quiet most of the time (it has been paused for
   most of its life so far), a model run takes minutes, and an empty chat
   reads as broken. From `status.json`: "The Quartermaster is thinking
   (woken for the season change), 2 min", "Paused: the Overseer is deciding
   what to do about a hostile", "Running at full speed; nobody needs to
   decide anything", "No news from the fort for 20 minutes". This is §8's
   third condition (Sentry state published, so a pause reads as deliberation
   rather than a crash), which the mockup has no place for.
3. **The LIVE badge tells the truth**: Live, Paused (with why), Slowed, or
   Offline, from the same status.
4. **"Run by six agents" is not accurate.** Today: four model roles
   (Overseer, Architect, Quartermaster, Consultant), a scheduler that is
   code (the conductor), and, planned, a cheap executor model woken only on
   a hold. Say "run by four AI agents and a scheduler" and add a small
   **"Who's who"** popover: each role's one-line job, model, and what it may
   and may not do (its allowlist, in words). Viewers cannot follow a
   conversation without the cast list.
5. **Step completions are the System speaking, not the Executor.** The
   register's 2026-10-01 executor row: code runs every approved step; the
   executor model wakes only on a hold. So "Step 2 done: the still site is
   dug" is a System line, and the Executor appears only when it is choosing
   what to do about a hold.
6. **"You" is operator wording.** On the public page the user's own messages
   show under the user's chosen display name, marked as the human; "You"
   only on the operator page.
7. **Sender and recipient on directed messages** ("Overseer to
   Quartermaster"), from the new `to` field. The 2026-09-25 requirement is
   exactly this: who talked to whom.
8. **The season goal is not always a progress bar.** "Drinks never below
   30" is a floor held over time, and a bar at 62% of it means nothing. The
   goal card draws by the measure's operator: a floor or ceiling as a small
   season-long line with the threshold marked ("lowest 31, now 34"); a
   target to reach as a bar with a time marker; a count to build as "4 of
   6". Data driven, one renderer per operator, not per goal.
9. **Game date first, wall clock second.** "Autumn 1" is ambiguous; show
   "12 Limestone, year 31" with "4 min ago" beside it and the exact time on
   hover. The day is derivable from the tick: 1,200 ticks a day, 28-day
   months, 403,200 a year.
10. **Filters: "Highlights" and "Everything" first, roles second.**
    Highlights (the default) hides passes, routine step completions, quiet
    wakes and lookups, and groups runs of System lines ("3 steps done on
    Second still"). The role chips move into a small menu. **DEPARTURE**
    (minor): the agreed design had role filters as the primary control.
11. **"Jump to latest" appears only when the reader has scrolled up**, with
    a count of new items. The chat never scrolls under a reader who is
    reading.
12. **Projects tab gains two groups**: "Waiting for a decision" (proposals
    not yet ruled, commissions not yet drafted) and "Recently finished" (done
    and abandoned, with why). The workforce line needs a labour read that no
    cycle makes today; it moves to a later slice.

### 6.3 A grammar for messages

Each kind gets one visual treatment, so a reader learns it once:

| Kind | Treatment |
|---|---|
| Proposal | a card: role, type label, public text, and a **verdict badge that updates in place** (Pending, Accepted, Rejected, Deferred), joined live from the later ruling, so a reader scrolling past an old proposal sees how it ended without hunting |
| Ruling | the Overseer's line with a stamp (Accepted as version 1), quoting the proposal it answers |
| Step done or held | a compact System line with the step label; holds amber with the hold code's text |
| Wake | a thin divider line ("Season change: waking the Overseer"), not a message |
| Escalation, alarm | red, pinned at the top of the chat until resolved |
| Goal set, goal reviewed | a wide card spanning the chat, since it opens or closes a chapter |
| User and Overseer messages | a distinct bubble, the only chat-app looking element on the page, because it is the only real conversation |

### 6.4 Threading and reply lines

**Reply quotes, not indentation.** A message that answers another shows
one quoted line above it ("replying to Quartermaster: A second still near
the farm...") that scrolls to and highlights the original. Nested threads in
a live, time-ordered feed fragment it and hide the interleaving that is the
point (the Overseer ruling on two advisors' proposals in one breath). The
per-project and per-goal views are the "threaded" reading: the same items
filtered by `thread`, shown in the drawer.

### 6.5 How a project's life reads

The drawer adds a **timeline** above the steps, one line per event, drawn
from records that already exist or are proposed in §3:

```
Commissioned by the Overseer          1 Limestone    serves: drinks never below 30
Drafted by the Quartermaster (v1)     3 Limestone    "A second still near the farm..."
Accepted                              3 Limestone
Step 2 done: Dig the site             9 Limestone
Held: no wood in reach                14 Limestone   the Executor is trying the next grove
Amended to v2                         15 Limestone   "Build with stone instead of wood"
Done                                  2 Sandstone
Checked: drinks held above 30         end of season
```

The steps list shows the current version, with a small "changed in v2"
marker on steps an amendment replaced or added, and dropped steps struck
through under a "Dropped in v2" fold. Abandoned projects keep their timeline
and end with the Overseer's public reason. Nothing is ever edited, only
appended, which is how the queue already works.

### 6.6 The season archive, as the chronicle

A **Seasons** tab (and a shareable page per season): newest first, one card
per finished season, built from the immutable season files (4.2):

- the goal and its stamp (Met, Partly, Missed), with the Overseer's review
  in its own public words and whether it thought it was a good goal;
- projects finished and abandoned, each linking its drawer;
- the population line: arrivals, births, deaths by name (names are what a
  player sees; they are the fort's story);
- escalations and pauses, counted, each linking its moment;
- "Read this season's conversation", which opens the chat at the season's
  first segment.

This is the chronicle's skeleton. When the Chronicler role is enabled, it
adds one written paragraph per season to the same card; the card has room
reserved for it and needs no redesign. Season files are immutable, so they
are also stable citations for the public report.

### 6.7 Mobile

One column: the video (16:10, full width) with the status line pinned just
beneath it, then three tabs: **Chat, Projects, Season**. The project drawer
becomes a full-screen sheet with a back button that returns to the same
scroll position. Filters open in a bottom sheet. Tap targets 44 px, as the
mockup already has for tabs. On a narrow phone the video can collapse to a
thumbnail strip so the chat gets the screen; tapping it expands.

### 6.8 The ten-second test

A first-time viewer should be able to answer three questions without
scrolling:

1. **What is this?** One sentence under the title: "A Dwarf Fortress colony
   run by AI agents. Nobody is playing. This is what they are saying to each
   other."
2. **What are they trying to do?** The season goal card.
3. **What is happening right now?** The "right now" line.

The mockup answers the second only. A dismissible "How to read this" strip
for first visits (remembered in the browser) explains roles, proposals and
rulings in three lines.

### 6.9 Ambient mode, for the screen on the wall (**addition**)

`docs/PURPOSE.md` names four surfaces: the Pi on the wall, a phone,
the website and a shareable artifact. The mockup serves two. `?ambient`
gives the wall a full-bleed video, the season goal and the right-now line as
a lower third, and the latest public item as a caption that fades after a
minute; large type, no controls, a daily self-reload. Shareable artifacts
come from permalinks: every item, project and season has an anchor URL.

### 6.10 Accessibility

Role is always a name as well as a colour; text contrast at least 4.5:1
(the mockup's secondary grey on its panel colour is close and must be
checked); new items announced politely to screen readers only while the
reader is at the bottom, and throttled; motion respects reduced-motion
settings; the drawer traps and returns focus. A light theme follows the
system setting for the page chrome; the video frame stays dark.

## 7. Q5, safety

### 7.1 Where a leak could come from

| Source | Example | Reaches the public projection? |
|---|---|---|
| Tool output and errors | a file path in an error, a stack trace | no: never in any public field (allowlist) |
| Tool call arguments | coordinates, item ids | no: operator only; coordinates already refused in text fields (`schema._COORDINATE_PATTERN`) |
| The call log's `client` field | a network address | no: dropped even from the operator files |
| Hold reasons | a guard's refusal text | no: replaced by hold codes (3.3 item 7) |
| **Model-written public text** | `public_rationale` echoing an error, a URL from a wiki page, a host name it saw in its context | **yes, by design**: this is the one real channel |
| The user's own messages | something personal | yes if public; the user chooses (§10) |
| Game-generated text | dwarf and artifact names | yes, and fine: player-visible, the fort's own story |

### 7.2 Layers, strongest first

1. **The per-kind allowlist** (3.5). Structural: a field not named cannot be
   published, whatever it contains. Unchanged in spirit from
   `render.public_view`; extended per kind.
2. **Public fields are written for an audience, and short.** Charters say
   so (they already do for `public_rationale`); the schema caps each public
   field (280 characters for rationale, 60 for titles and labels).
3. **Write-time refusal in public fields** (proposed, `dfqueue/schema.py`,
   beside the coordinate check): refuse a URL or scheme, anything shaped
   like a domain name, an IPv4 or IPv6 address, a file path (either slash
   style), an email address, a long unbroken token-shaped string, and markup
   (angle brackets, backticks, markdown links). The model is told why and
   rewrites in plain words. This is a pattern list, which §8 warns against
   as a *filter*; here it is a *refusal before storage*, so nothing is ever
   silently edited, a miss is still caught by layer 4, and a false positive
   costs one rewrite. The allowlist remains the guard.
4. **Publish-time canary check** (proposed, in the publisher): exact-match
   and prefix-match every public text against a list of the estate's real
   secrets and identifiers (host names, addresses and subnet prefixes, token
   prefixes, the user's email), kept in gitignored `infra/local.*` on VM 103
   and never shipped to the page. A hit **withholds** the item (the page
   shows "one message withheld"), raises an `alarm`, and counts toward the
   automatic kill switch (4.6). Withholding, never editing.
5. **Rendering is inert.** The page inserts every text with `textContent`,
   never as HTML; no link detection, no markdown. A model that writes
   `<script>` shows the reader the characters `<script>`. This is the
   defence against a model (or a wiki page the Consultant read) injecting
   into viewers' browsers, and it costs nothing.
6. **Kill switches and the withhold list** (4.6).
7. **The user reads it before anyone else does.** The public view ships
   only after the operator view has run with its "show as public" toggle and
   the user has read it; going public gets its own go-ahead and register
   row, as §8 and the 2026-09-14 rows require.

### 7.3 When model text says something it should not

Secrets are layers 3 and 4. The rest is judgement: an unkind line, a claim
about a real person, a paragraph a wiki page talked a model into. Consultant
answers and ask text are the likeliest carriers, since they are written from
wiki content, and they are private by default (3.5). For the rest, the
answer is the withhold list and the kill switch, and the record stays in the
queue for the learning loop: a public rationale that had to be withheld is
itself useful data about the role that wrote it. **The publish delay**
(waived by the user on 2026-09-14) is still not needed with layers 3 to 5
in place; reinstating it is the remedy if a withheld item ever reaches a
viewer first.

### 7.4 Two commitments this page must not bend

- **Nothing on the page is ever read by an agent.** The page is for humans;
  the video and every rendering of the fort stay out of every model's input
  (`docs/PURPOSE.md` commitment 1). A future Chronicler writes from the
  queue and the season files, never from the page or the video.
- **Only what a player could see.** Every public fact on the page (vitals,
  stock counts, names, jobs) comes from tools marked `player_derivable`
  in `TOOLS.yaml`, the same test the no-armok rule applies to agents.

### 7.5 The operator view's own exposure

Operator files hold call arguments, costs, private reasons and lessons; no
tokens (the call log was checked to carry none, register 2026-09-14) and,
with `client` dropped, no addresses. They sit on the relay behind Access. A
compromised relay would expose them. That is a real but modest cost, and
the alternative (serving the operator view from VM 103 through a new
tunnel) adds a path into the fort host, which is worse. A decision for the
user (§10).

## 8. Q6, the slice plan

Smallest valuable first. Each slice names what it needs from the user.
Order reasoning: private before public, and the conductor's events before
public, because a public page without the "right now" line would show an
empty chat beside a paused fort, which is the worst first impression.

| Slice | What | Value | Needs from the user |
|---|---|---|---|
| **S0** local | `dfqueue/feed.py` (proposed): the public and operator projections, the derivations of 3.4, segmenting and the file layout, as pure code; the page as static files (`web/stream/`, proposed) rendering them. Tested against the real exported records in `evals/live/*/queue-export/` | the user opens the page locally and reads real past agent conversation in it | nothing; no live access |
| **S1** operator live | the publisher on VM 103 (read only), a directory-restricted key on the relay, a loopback static server there, the admin hostname serving the page; existing records only | "everything visible to the user" is met for everything already in the queue | go-ahead to deploy to VM 103 and the relay; confirm the Access application covers the path; peer check-in before touching either host |
| **S2** conductor and joins | `seq`; the `run_id` header and stamp; `wake` and `run` kinds; `feed.status`; `reply_to` and `about` on ask and escalation; archive the wake reasons; the operator page shows calls under each message and the right-now line works | the page comes alive: who is thinking and why, and every message joined to its calls | go-ahead to deploy to VM 103 and VM 106; a supervised conductor run to see it (the service is disabled by the user's choice) |
| **S3** public | per-kind public allowlist and text tables, write-time public-field checks, the canary, the three kill switches, the public server block, the portfolio link | the public stream exists | explicit go-ahead to publish, with its own register row; the Cloudflare rule built (dashboard); the user has read the "show as public" view; decisions 2 and 3 in §10 |
| **S4** projects | `public_title`, step `label`, `public_rationale` on amend and abandon, hold codes, `projects.json`, the drawer with its timeline, verdict badges | the Projects panel and the drawer | review of the Overseer charter change (it writes the new fields) |
| **S5** season goal | render `goal`, `review` and commissions (`ask.to`, `expects`); stock counts and the goal measure in the status push | the season goal card and the goal-first project outline | the seasonal review feature itself, which is its own stream (register 2026-10-01); this slice only renders it |
| **S6** the user's line | `message` kind, the `user` roster entry, the Telegram bridge writing through `dfmcp` | the user and the Overseer talk on the page | a bot token (the user creates the bot); the open register question of how much authority a user message carries; decision 2 |
| **S7** chronicle and wall | the Seasons tab and files, ambient mode, the live DF job under a step, the workforce line, Executor lines | the chronicle's skeleton and the screen on the wall | a finished season to show; the reconcile snapshot (lean core item 3) for live jobs |

S0 can start now and in parallel with anything; S1 needs nothing new in the
schema. S2 and S4 touch `dfqueue/` and `dfmcp/`, which other streams also
touch, so each must be its own stream with its own touched surfaces
(`handoffs/` rule).

## 9. Departures from the brief, collected

1. **No Public / Operator switch on the public page**; a "show as public"
   toggle on the operator page instead (§5, 6.2).
2. **The page lives on the relay**, not the portfolio site, which links to
   it (§5). The brief left this open; recorded as a recommendation.
3. **Not every record becomes a chat message.** Observations feed progress
   only; asks, answers, passes and escalations show generated one-liners;
   Consultant text stays private by default (3.5).
4. **The conductor's events become records, but fort status does not**
   (3.1): the brief's "conductor events as records or not" answered both
   ways, by kind of event.
5. **An explicit `seq` column**, not `rowid` (3.3).
6. **Step completions are the System, not the Executor** (6.2 item 5),
   following the register's own executor rows rather than the mockup.
7. **"Six agents" becomes "four AI agents and a scheduler"**, with a Who's
   who (6.2 item 4).
8. **Highlights / Everything is the primary filter**, roles secondary (6.2
   item 10).
9. **The goal card draws by measure type**, not always a bar (6.2 item 8).
10. **Hold reasons are published as codes**, never as the tool's text (3.3).
11. **Additions not in the brief**: the right-now line, verdict badges that
    update in place, the project timeline, the Seasons tab, ambient mode,
    permalinks, the canary check, inert rendering, and durable storage of
    the call log.

## 10. Decisions for the user

1. **Where the page lives**: the relay, same origin as the video
   (recommended), or the portfolio site.
2. **The user's Telegram messages and the Overseer's replies**: public by
   default with a way to mark one private (recommended, matching the
   register's "displayed on screen"), or private by default.
3. **Consultant answers**: stay private (default), or public through a one
   line summary the Consultant writes for the audience.
4. **The operator view's gate**: share the admin hostname and its Access
   login with full game control (recommended for one user), or its own
   hostname and Access application so it can be shown without handing over
   the fort.
5. **Operator data on the relay** (call arguments, costs, private reasons),
   with run files kept 90 days there and in full on VM 103: accept, or
   change the window.
6. **Build the Cloudflare kill-switch rule** (dashboard work only the user
   can do) before S3.
7. **Public launch waits for S2** (the right-now line) rather than
   following S1 directly.
8. **Wording**: "four AI agents and a scheduler", and the display name the
   user wants on the public page for their own messages.

## 11. What could not be verified

No live access was used (design only, per the brief).

- **SQLite `VACUUM` renumbering `rowid`** on tables without an explicit
  `INTEGER PRIMARY KEY`: from SQLite's documented behaviour as known, not
  re-read in this pass. The `seq` recommendation stands either way (an
  explicit key is cheap), but its urgency rests on this.
- **A per-run MCP header from openclaw**: the static header map reading an
  environment variable is from `research/2026-09-12-openclaw-mcp-auth.md`
  (a source read, not run); setting it per role run through the conductor's
  container launch is unverified.
- **The Access application's scope** (whole admin hostname or a path), and
  whether Access-protected responses are ever cached at Cloudflare's edge.
- **Whether the relay's current web server allows framing** (only matters
  for the portfolio option), and **whether `rrsync` ships with the relay's
  Debian 12 rsync package** at a usable path.
- **Cloudflare custom rules on the user's plan**, for kill switch layer 1.
- **Event rates and every cost figure in 4.7**: estimates from one real
  cycle, to be replaced after a week of real running.
- **journald retention on VM 103** for the call log (persistent journal is
  on, per the incident-capture work; its size cap was not read).
- **The game's month names** in the examples are from the game's calendar
  as known, not read from this install.
- **Colour contrast of the mockup's palette**: not measured.

