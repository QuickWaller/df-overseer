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
