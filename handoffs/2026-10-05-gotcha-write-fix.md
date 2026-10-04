# Handoff: gotchas.write fails live ("no such table: main.entries_v1_old")

Date: 2026-10-05. **Executor, Sonnet, worktree. Read-only on hosts; no live
writes, no deploys** (the orchestrator repairs the live store and deploys).

## Why

Every `gotchas.write` on VM 103 has failed since the gotcha store's schema v2
migration (2026-10-02, `dfmcp/gotchas_store.py`, lazy migration on open,
`python -m dfmcp.gotchas_store migrate PATH`). The 2026-10-02 conductor cycle's
Overseer reported it, and the MCP journal shows the error text:
`the gotcha store is unavailable: no such table: main.entries_v1_old`.
`gotchas.get` still works. Agents cannot record what they learn until this is
fixed, so it blocks the next cycle.

Likely shape (prove it, don't assume): the v1 to v2 migration renamed the old
table to `entries_v1_old`, and something still refers to it (a trigger, an FTS
table or its triggers, a view, or an index), e.g. SQLite's
`ALTER TABLE ... RENAME` rewriting references inside triggers, which then
dangle once the old table is dropped.

## Tasks, in order (commit after each)

1. **Reproduce on a real copy.** Pull a read-only copy of the live store:
   `DF_ENV_FILE=c:/website-projects/df-automation/.env scripts/vm-ssh.sh df 'base64 -w0 /var/lib/dfgotchas/uniboslan.gotchas.sqlite3'`
   (decode locally; the file is not secret, it holds agent-written gotchas).
   Dump its schema (`sqlite_master`) and reproduce the failing write through
   the same code path `gotchas.write` uses. Record the exact cause here.
2. **Fix the migration** so a v1 store migrates to a v2 store that accepts
   writes, and so a store already broken in this exact way is repaired when
   opened (or by the `migrate` command). Never drop entries: compare entry
   counts and contents before and after on the live copy.
3. **Tests:** a v1 fixture built like the real one (same triggers, FTS, etc.)
   migrates and accepts a write; a store broken like the live one is repaired
   and accepts a write; existing entries survive both.
4. **Live repair plan for the orchestrator:** the exact commands to back up
   the live file, run the repair, and verify (a real `gotchas.write` via
   `scripts/ops/mcpcall.py` then `gotchas.get` showing it), plus which deploy
   target ships the fixed code (`vm103-dfmcp`; `dfmcp-server` restart).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- Touched surfaces: `dfmcp/gotchas_store.py` and its tests only. If the fix
  truly needs another file, say so in the Result rather than editing it.
- Read `.env` by key only. Public repo: no hostnames, IPs or tokens; do not
  commit the copied database. No em dashes. No attribution lines in commits.
- Full ambient suite and `dfmcp/tests` (in `.venv-dfmcp`) green before done.

## Done when

Cause proven on the live copy, fix and tests committed, the live repair plan
written here, and a Result section.
