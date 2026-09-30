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
tick       absolute game tick (rendered as "12 Granite, Autumn, year 31")
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
