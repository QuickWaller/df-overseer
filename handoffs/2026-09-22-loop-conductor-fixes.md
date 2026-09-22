# Stream: conductor pre-deploy fixes (agent loop MVP)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** the MVP
build plan, 2026-09-22. Offline only: **no VM, no deploy, no model call, no
push.** Sonnet executor, worktree-isolated. **No attribution lines in commit
messages** (no Co-Authored-By, no "Generated with Claude Code"): the user's
instruction.

## Why

The conductor stream (`handoffs/2026-09-22-loop-conductor-service.md`, read
its Result section, "Design flags") landed with gaps that would break or
blind the first real run. Fix these before the deploy:

1. **Blocking: the Consultant is never woken.** `queue.pending` branches on
   the caller's authenticated role, so the conductor cannot see open asks.
   An Overseer fact-check blocks `queue.rule` on its proposal until answered,
   so that proposal would sit blocked forever. Give the conductor a read of
   open asks (a conductor-only native tool, or a role argument on a
   conductor-only tool; not a way for any agent to read another role's
   queue), and make the conductor wake the Consultant on open asks, with a
   test that runs ask, wake, answer and then the ruling going through.
2. **Refusals pass as successes.** `dfmcp/server.py` marks a result `isError`
   only when the object is exactly `{"error": ...}`; the clock and quicksave
   tools refuse with `{"ok": false, "error": ..., ...}`. Make a refusal from
   these tools reach the client as `isError: true` with its detail kept, by
   the narrowest fix you can justify (the server rule or the tools' output),
   tested. The conductor's own `ok` checks must still work.
3. **No escalation convention.** Define how the Overseer escalates to the
   human (its charter's Escalation section already lists when): a queue
   record or tool call, not free text, so the conductor detects it
   mechanically and leaves the fort paused. Update `agents/overseer/role.md`
   and the conductor. A clean run with no escalation must no longer be
   treated as one; a failed or timed-out run still leaves the fort paused.
4. **Hostile-reachable signal.** The conductor has no hostile read, so
   `hostile_seen_unreachable` is always false. Grant it the existing
   read-only threat scan if its cost is bounded (check `TOOLS.yaml`'s notes),
   or say why not and leave it documented as a gap.
5. **Small owed items:** `conductor/requirements.txt` (pinned, matching
   `dfmcp/requirements.txt` where shared); `MCP_ROLE_TOKEN_QUARTERMASTER=` in
   `infra/local.example.env`.

## First

`git merge --ff-only main` in your worktree (local `main` is ahead of
`origin/main`).

## Touched surfaces (yours only)

`conductor/` and its tests; `dfmcp/queue_tools.py`,
`dfmcp/tests/test_queue_tools.py`; `dfmcp/server.py`,
`dfmcp/tests/test_server.py` (item 2); `scripts/dfhack/df-overseer-clock.lua`
and `df-overseer-fort.lua` and their `TOOLS.yaml` entries (only if item 2 is
fixed at the tool); `dfqueue/` (only if item 3 needs a record kind);
`agents/overseer/`, `agents/conductor/`; `dfmcp/tests/test_roles.py`;
`infra/local.example.env`; `dfmcp/README.md`, `dfqueue/README.md`; this doc
and its `handoffs/INDEX.md` row.

## Hard lines

- No VM, no SSH, no deploy, no model call, no Docker run. No push.
- No attribution lines in commits.
- Do not write `Working.md`, `decisions/` or `memory/`. No em dashes in prose.
- Commit after each milestone and extend the Result section as you go.

## Done when

Both suites pass (ambient `python -m pytest`, baseline **1175 passed / 3
skipped**; `dfmcp/tests` in the main checkout's `.venv-dfmcp`, baseline
**609**), counts reported, and the Result section lists each fix, its test,
and any change to the deploy steps.

## Result

(executor fills in)
