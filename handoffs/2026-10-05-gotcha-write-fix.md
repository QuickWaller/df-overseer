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

## Result (2026-10-05, executor)

**Proven cause.** Read-only copy of the live store (3 entries, 3 outcomes,
0 status_history rows, schema_version 2, SQLite 3.45.3). Its `sqlite_master`
shows `outcomes` and `status_history` declared `entry_id TEXT NOT NULL
REFERENCES "entries_v1_old"(id)`. The v1 to v2 migration did `ALTER TABLE
entries RENAME TO entries_v1_old`; SQLite (3.26+, `legacy_alter_table` off)
rewrites the foreign keys of child tables to follow a renamed parent, so the
migration's later `DROP TABLE entries_v1_old` left them dangling. No triggers,
views or FTS tables are involved. Reproduced on the copy through the real
code: `add_entry` (with or without a tool) still succeeds, but `add_outcome`
and `set_status` fail with `no such table: main.entries_v1_old` (they insert
into the child tables with `PRAGMA foreign_keys=ON`). So the failing
`gotchas.write` is the outcome-recording form (the call that passes an entry
`id`); a fresh-entry write works. The handoff's "every write" was slightly wide.

**Fix (`dfmcp/gotchas_store.py`).** (1) The migration now builds
`entries_new`, copies, drops `entries`, renames `entries_new` into place
(foreign keys off for the swap), so child references stay `entries(id)`.
(2) New `_repair_dangling_entries_refs`, run from `_ensure_current_schema`
(every open, and via `migrate`): if `outcomes` or `status_history` SQL
mentions `entries_v1_old`, each is rebuilt with the right FK, rows copied with
`seq` unchanged, AUTOINCREMENT counter preserved, one transaction, rollback on
failure; a no-op on a healthy store; unreadable files are left to
`_check_schema`.

**Tests.** New `dfmcp/tests/test_gotchas_repair.py` (6 tests): fixture guard
proving the old migration breaks a store, v1 migrates with correct FKs and
accepts outcome and status writes, broken store repaired on open with
identical rows, indexes and seq, `migrate` command repairs and is idempotent,
healthy store untouched. Counts: `dfmcp/tests` in `.venv-dfmcp` 773 passed;
ambient with lupa 2537 passed, 3 skipped, 0 failed. Verified on the live copy:
`python -m dfmcp.gotchas_store migrate COPY` left entries, outcomes,
status_history and schema_version identical (only change: an empty
`status_history` row with seq 0 appears in `sqlite_sequence`, harmless);
`foreign_key_check` and `integrity_check` clean; `add_outcome` then succeeds.

**Live repair plan (orchestrator; each step needs the user's go-ahead).**
Only `dfmcp/gotchas_store.py` ships; no other file changes.
1. Back up on VM 103: `sudo cp -a /var/lib/dfgotchas/uniboslan.gotchas.sqlite3
   /var/lib/dfgotchas/uniboslan.gotchas.sqlite3.bak-20261005`.
2. Deploy the fixed code once this branch is merged and pushed:
   `python scripts/deploy.py --target vm103-dfmcp --dry-run`, then `--yes`
   (refuses a dirty tree or a commit not on `origin/main`). It restarts
   `dfmcp-server`; startup `check_store` runs the repair on open, so the
   restart alone repairs the store.
3. Optionally repair explicitly first, as the service user from the deployed
   tree: `python -m dfmcp.gotchas_store migrate
   /var/lib/dfgotchas/uniboslan.gotchas.sqlite3` (prints `schema_version 2`;
   idempotent).
4. Verify: `sqlite3 FILE "select name from sqlite_master where sql like
   '%entries_v1_old%'"` returns nothing; `PRAGMA foreign_key_check` empty;
   still 3 entries and 3 outcomes. Then over MCP:
   `mcpcall.py call overseer gotchas.write '{"id":"gotcha-0002","result":"worked","note":"repair check"}'`
   (the outcome path is the one that was broken), then
   `mcpcall.py call overseer gotchas.get '{"id":"gotcha-0002"}'` showing the
   new outcome. That outcome is a real live row; note it as a repair check, or
   run the pair against a copy first.
