# Handoff: conductor.report, so wake reasons and run summaries reach the site

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.**

## Why

The site's "who's awake" strip (`handoffs/2026-10-05-board-order-year-live-view.md`,
`dfqueue/live.py`) can see live tool calls on VM 103 but not why a role woke,
and nothing shows each agent's end-of-run summary (the conductor keeps
`final_answer`, duration and cost in its run archive on VM 106 only). The
publisher runs on VM 103, and VM 106 has no way to send files there.

**Decided with the user (2026-10-05), option 1:** the conductor sends these
through the MCP server it already calls every cycle, using its existing token.
No new SSH key, port or credential. Rejected: an SSH key from VM 106 to VM 103
(it would give the least-trusted machine, where the LLM containers run, a shell
on the fort VM) and routing through the user's workstation (not always on).

## Tasks, in order (commit after each)

1. **Design, written here first.** A conductor-only MCP write tool,
   `conductor.report` (name may change), in the `conductor` role's allowlist
   (`agents/conductor/tools.yaml`; no agent role gets it). Two calls per run:
   at launch (role, wake reason and detail, cycle id, started time) and at the
   end (status, duration, cost, `final_answer`, timed_out, error). Storage on
   VM 103 next to the queue (a table in the queue database via `dfqueue`, or a
   small store of its own: choose and justify; the publisher reads it
   read-only, and remember the queue database is SQLite WAL). Bound sizes
   (cap `final_answer`), and never let a failed report break a cycle: a
   report failure is logged, the run goes on.
2. **Link runs to records.** The user wants each run's summary to appear as a
   reply in the threads of the proposals and projects that run touched. The
   MCP server already logs every call with its session; find the simplest
   reliable way to record which queue records a run wrote (for example the
   server noting record ids written per session, or the conductor listing
   them) and store that with the end-of-run report.
3. **Build it:** the tool (registry, schema, role allowlist, tests); the
   conductor calls it before and after each role run (`conductor/cycle.py`,
   replacing the `status_running` stub's role); the publisher
   (`scripts/stream_publisher.py`, `dfqueue/live.py`) reads the store and
   fills the strip's wake reason, and writes the run reports to the per-fort
   output (operator: summary, cost, records touched; public: role, wake
   reason, duration, records touched, and the summary **only** after the same
   public-text safety the feed applies; if that check is not good enough for
   free model text, keep summaries operator-only and say so).
   Per-role tool counts change only for `conductor`; update the pinned count
   test and anything `docs/STATE.md` generation compares.
4. **Deploy plan for the orchestrator:** which manifest targets ship what
   (`vm103-dfmcp`, `vm106-conductor`, `vm106-agents`,
   `vm103-stream-publisher`), restarts needed, and the order (server first).
   Add new files to `infra/deploy-manifest.yaml`.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `dfmcp/` (new tool module, registry, roles; **not**
  `dfmcp/gotchas_store.py`, another stream is fixing it), `agents/conductor/`,
  `conductor/`, `dfqueue/` (storage only; **not** `dfqueue/feed.py`),
  `dfqueue/live.py`, `scripts/stream_publisher.py`, `infra/deploy-manifest.yaml`,
  tests. **Not** `web/stream/` (another stream owns the page; describe the JSON
  you produce so the page can render it next).
- Read `.env` by key only. Public repo: no hostnames, IPs or tokens. No em
  dashes. No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green before done.

## Done when

Design written here, the tool, conductor calls and publisher output committed
with tests, the JSON shape documented for the page, the deploy plan, and a
Result section.

## Design (written before building, 2026-10-05)

**Tool.** One native MCP tool, `conductor.report`, with a `phase` argument
(`start` | `end`), in `dfmcp/conductor_tools.py`, granted only in
`agents/conductor/tools.yaml` (`write:`). Two layers, as `queue.rule` does:
the allowlist, and a refusal in the handler if the authenticated role is not
`conductor`. Not `mutates` (it never touches the fort), not `sole_writer_only`.
Arguments are closed (`additionalProperties: false`, unknown keys refused).

- `start`: `role` (architect|overseer|quartermaster|consultant), `wake_reason`
  (a short code, capped 64), `wake_detail` (capped 300), `cycle` (the
  conductor's cycle index, int). The server stamps `started_at` itself (its own
  clock, so there is no cross-host skew) and returns `{"run_id": "run-NNNN"}`.
- `end`: `run_id` (from `start`; if the start call failed the conductor sends
  `role`, `wake_reason`, `cycle` again instead and the server creates the row,
  with `started_at = now - duration_s`), `status`, `ok`, `timed_out`,
  `duration_s`, `cost_usd` (null means unknown), `error` (capped 500),
  `final_answer` (**capped at 4000 chars**, truncated with a marker). The
  server stamps `ended_at`.

**Storage: a small store of its own, not a queue table.** `dfqueue/runs.py`,
one SQLite file next to the queue database
(`<queue-db-stem>.runs.sqlite3`, derived from `queue_db_path`, so no new
server config and no new path to deploy). Why not a queue table: the queue is
an append-only ledger of *decisions* with a schema version, a validator, a
grader and a feed that all walk `records`; a run report is mutable operational
telemetry (a row is created at launch and completed at the end) and putting it
in the ledger would touch `schema.py`/`store.py` migrations and
`dfqueue/feed.py` (another stream's file). A separate file also cannot slow or
corrupt the ledger. WAL mode; the writer is the MCP server (one process, under
its own lock); the publisher opens it `mode=ro` exactly as
`feed.load_records_readonly` does. Table `runs`: `run_id` PK, `role`,
`wake_reason`, `wake_detail`, `cycle`, `started_at`, `ended_at`, `status`,
`ok`, `timed_out`, `duration_s`, `cost_usd`, `error`, `final_answer`,
`records_json`. Retention: the writer prunes to the newest 500 rows.

**Linking runs to records (task 2): the server resolves it, by role and time
window, at `end`.** The conductor runs roles one at a time and each role holds
its own token, so every queue record a run wrote carries `role == run.role` and
a server-stamped `ts` inside `[started_at, ended_at]` (both from the same
server clock). At `end` the server reads the queue read-only for that window,
and stores `records_json`: a list (capped 50) of `{id, kind, thread}`.
`thread` is the record the page should nest the summary under: the record's own
`proposal_id`/`project_id` if it has one; an `executed` record resolves
through its ruling's `proposal_id`; a proposal, ask or project is its own
thread. Rejected alternatives: the MCP session id (openclaw may reuse or split
sessions, and `_run_id` itself says the "one run is one session" assumption is
unconfirmed live) and the conductor listing records (it does not see what the
role wrote, and a model-reported list would be unverifiable). Known limit: a
role that is woken twice in one cycle would be two windows, not overlapping,
so it stays exact; two roles never overlap in one conductor.

**Failure never breaks a cycle.** The conductor wraps both calls in a helper
that catches everything (including `MCPToolError`), logs a warning and goes on;
a missing `run_id` just makes the `end` call self-contained. A server without
the tool yet (conductor deployed before the server) is the same case: logged,
ignored.

**Conductor side.** `conductor/cycle.py`: a `_run_role` helper replaces the two
direct `deps.role_runner.run` calls (the tripwire Overseer run and the ordinary
loop), calling `conductor.report` start before and end after. `status_running`
stays for the local `status.json` but is no longer the source the page needs.

**Publisher side.** `dfqueue/live.py` gains `read_runs_readonly(path)` and
`build_runs(rows, *, public)`; `scripts/stream_publisher.py` reads the runs
store each cycle (optional: `STREAM_PUBLISHER_RUNS_DB`, default the
`.runs.sqlite3` sibling of the queue db if it exists), fills the strip's
`wake_reason` from the open run (and `last_runs[role]` from the newest closed
one, overriding the conductor-dir path), and writes `runs.json` next to each
projection's `head.json`. **Public summaries**: free model text is the worst
case for the feed's pattern check (it catches urls, paths, tokens, markup, not
meaning: a model can name a coordinate or quote a tool error). Decision:
public `runs.json` carries role, wake reason code, duration, outcome and the
linked record ids/threads, and the **summary only after
`feed.find_unsafe_pattern` passes AND it is cut to 280 chars at a sentence
boundary**; any failed check withholds that summary (the entry says
`summary_withheld: true`, never why). Cost and `error` are operator-only.
Reported to the user in Result as a judgement call: if they want summaries
operator-only, it is one flag (`PUBLIC_SUMMARIES` in `dfqueue/live.py`).

**Counts.** Only `conductor` gains a tool: 16 -> 17. The pinned count in
`dfmcp/tests/test_gotchas_tools.py` and the per-role counts in
`docs/STATE.md` (generated; regenerated offline by its own command) change.

## Result (2026-10-05, executor, offline; no host writes, no deploys)

**Built as designed**, with these points settled while building:

- `dfqueue/runs.py` (store, `runs_path`, `start_run`/`end_run`/`window_for`,
  `read_runs_readonly`, `queue_records_readonly`, `records_in_window`),
  `dfmcp/conductor_tools.py` (the tool; `server.py` routes it with its own
  write lock), `agents/conductor/tools.yaml` (`write:` grant, conductor only;
  the handler also refuses any other role), `conductor/cycle.py`
  (`_report`, `_run_role`: both role-run sites, the tripwire Overseer run and
  the ordinary loop, are bracketed; a dry run reports nothing; a report failure
  is one warning and never touches the run or the cycle),
  `dfqueue/live.py` (`read_runs`, `build_runs`, `build_live(..., runs=)`),
  `scripts/stream_publisher.py` (reads the store, fills the strip, writes
  `runs.json`, folds it into change detection), `infra/deploy-manifest.yaml`
  (`dfqueue/runs.py` added to `vm103-stream-publisher`; the other targets ship
  whole directories already).
- Wiring that had to follow the new native tool: `scripts/drift_check.py` and
  `dfqueue/site_data.py` build a registry with the native-tool merge (without
  `conductor_tools` the roster refuses to load, `tools.json` included), and
  every test fixture that builds its own registry now merges it too.
- **Public summaries: kept, behind the same safety the feed uses, plus a
  280-char sentence cut, one switch to turn off.** `feed.find_unsafe_pattern`
  catches urls, domains, addresses, paths, markup and token-shaped strings; it
  does not understand meaning, so a model could still put a coordinate or a
  quoted tool error in prose. If the user is not comfortable, set
  `dfqueue/live.py::PUBLIC_SUMMARIES = False` (public `runs.json` then carries
  `summary_withheld: true` and no text; operator is unaffected). Public never
  carries cost, `wake_detail`, `error` or cycle, and a `wake_reason` that is
  not a plain lowercase code is nulled.
- Records are linked by role and server-stamped time window at `end` (design
  above). Verified in a test against a real `records` table, not mocks.

**Tests.** Ambient `python -m pytest`: 2561 passed, 3 skipped, 0 failed (the
date-sensitive wiki test happened to pass). `.venv-dfmcp` `dfmcp/tests`: 782
passed (764 plus 18 new). New: `dfmcp/tests/test_conductor_tools.py` (13),
one over-the-wire case in `dfmcp/tests/test_server.py`,
`conductor/tests/test_report.py` (6), `tests/test_stream_publisher_runs.py`
(10). Pinned conductor count 16 to 17 in `dfmcp/tests/test_gotchas_tools.py`
and `tests/test_drift_check.py`; `test_roles.py` now pins that only the
conductor holds `conductor.report`. `docs/STATE.md` is generated from live
probes and was not regenerated; it will show conductor 17 offline vs 16 live
until the deploy, then regenerate with `python scripts/drift_check.py --write-state`.

### JSON the page reads

All under the per-fort directory, next to `head.json` (`forts/<fort_id>/`),
both projections.

`status.json`, `live` block (existing; additions marked NEW):
```
live.source            "journal+reports" etc. ("+reports" suffix when the store exists)
live.running           true while a role is awake OR a report is open
live.awake[]           { role, since, elapsed_s, last_tool, last_call_at,
                         wake_reason,            // now filled from the open run report
                         run_id }                // NEW, joins to runs.json (absent if no open report)
live.last_runs[role]   { run_id, duration_s, ended_at, wake_reason, ok,
                         source: "report" }      // operator adds cost_usd
```

`runs.json` (NEW; absent until a run store exists; newest first, max 40):
```
{ "available": true, "as_of": "<iso>",
  "runs": [ {
    "run_id": "run-0007", "role": "architect",
    "wake_reason": "routine_review",   // code; public nulls anything not [a-z0-9_]
    "status": "running|ok|failed|timed_out|lost",
    "started_at": "<iso>", "ended_at": "<iso>|null", "duration_s": 42|null,
    "records": [ { "id": "proposal-0003", "kind": "proposal", "thread": "proposal-0003" } ],
    // public only:   "summary": "<=280 chars"  OR  "summary_withheld": true
    //                (summary only when status is ok and the text passed the safety check)
    // operator only: "summary": "<full final answer, 4000 cap>", "wake_detail", "cycle",
    //                "cost_usd" (null = unknown), "error"
  } ],
  "by_thread": { "proposal-0003": ["run-0007", "run-0005"] } }   // thread id -> run ids, newest first
```
`thread` is the id of the feed item to nest the run's summary under: a
proposal, ask or project is its own thread; a ruling or amend resolves to its
`proposal_id`/`project_id`; an `executed` record resolves through its ruling.
The page should match `thread` against its existing thread ids and ignore any
it cannot find. A `lost` run is one with no end for over 20 minutes.

### Deploy plan (orchestrator; nothing here was deployed)

Order: **server first, then the publisher, conductor last.** A conductor that
calls a tool the server lacks only logs a warning, so the order is forgiving,
but the strip stays empty until all three are live.

1. `vm103-dfmcp` (`dfmcp/`, `dfqueue/`, `agents/`): ships the tool, the grant,
   `dfqueue/runs.py`, and the registry wiring in `dfqueue/site_data.py`.
   **Restart `dfmcp-server.service`** (low risk). Check: conductor tool count
   16 to 17, every other role unchanged (overseer 99, architect 53, consultant
   29, quartermaster 25); an architect calling `conductor__report` is refused.
   The first `start` creates `<queue-db-stem>.runs.sqlite3` beside the queue
   database. Confirm the service can write in that directory (SQLite WAL adds
   `-wal` and `-shm` files, so a unit that whitelists only the one file in
   `ReadWritePaths` would fail).
2. `vm103-stream-publisher` (`scripts/stream_publisher.py`, `dfqueue/live.py`,
   `dfqueue/runs.py`, `dfqueue/site_data.py`, all already in or added to that
   target). No env needed: the publisher finds the store as the queue db's
   `.runs.sqlite3` sibling (override `STREAM_PUBLISHER_RUNS_DB`). Confirm its
   user can read that file and open the `-shm` (WAL read-only needs both). If
   `mode=ro` fails the code returns nothing and the strip stays as before
   without an error, so check that `runs.json` appears. Restart
   `stream-publisher.timer` (low risk). Deploy this after step 1 so the
   publisher's registry (`site_data`) knows the new tool.
3. `vm106-agents` (`agents/`, bookkeeping: the conductor does not read it at
   run time) and `vm106-conductor` (`conductor/`). `conductor.service` is
   disabled and inactive, so there is nothing to restart; the next manual
   `--once` run picks the code up. First real check: one `--once` cycle that
   wakes a role, then read `runs.json` on VM 103 and the strip.
4. After: `python scripts/drift_check.py --write-state` (conductor 17).

**Not done / for the orchestrator:** `Working.md`, `decisions/DECISIONS.md` and
`memory/` are untouched by rule. Suggested register row: run reports ride the
conductor's MCP connection into a store of their own beside the queue db,
records are linked server-side by role and time window, public summaries are
gated by the feed's safety check with a one-flag off switch. The page work
(`web/stream/`) is the next stream: render `live.awake[].wake_reason` and
`runs.json` replies nested by `thread`.
