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
