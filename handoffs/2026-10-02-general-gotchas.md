# Handoff: general gotchas and vents (no tool named)

Date: 2026-10-02. **Executor, Sonnet, worktree. Offline only: build and test,
deploy nothing.**

## Why

Register 2026-10-02, "General gotchas and vents": an agent may write a
gotcha, vent or unexplained error about how the work goes (process, timing,
other agents, its own wake-ups) without naming a tool. Game knowledge is not
one of these: it belongs in doctrine, through the Consultant.

## Tasks, in order (commit after each)

1. `dfmcp/gotchas_store.py`: an entry may have no tool. Represent it as
   `tool = NULL` (the site stream reads general entries as `tool: null`;
   keep that shape). Migrate the existing SQLite table safely (SQLite cannot
   drop NOT NULL in place: rebuild the table in a transaction, preserving
   every row, id and outcome), idempotent on restart, tested on a copy of a
   populated store. `kind` stays meaningless without a tool: refuse a kind
   with no tool.
2. `dfmcp/gotchas_tools.py`: `gotchas.write` accepts an omitted tool
   (general); `gotchas.get` can ask for general entries (and still returns
   a tool's own entries exactly as today). Tool descriptions say plainly
   what a general entry is for, and that game knowledge goes to the
   Consultant/doctrine instead. Per-role tool counts must not change.
3. `agents/CONFIDENCE-LEGEND.md` (or wherever the shared gotcha guidance
   lives): one or two lines on general entries and the doctrine line.
4. Tests: write and read a general entry, outcomes on it, refusal of a
   kind without a tool, the migration preserving rows, unchanged behaviour
   for tool entries, tool counts unchanged.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`.
- **Touched surfaces:** `dfmcp/gotchas_store.py`, `dfmcp/gotchas_tools.py`,
  `agents/CONFIDENCE-LEGEND.md`, their tests. Not `web/stream/*`,
  `dfqueue/*`, the publisher or export scripts (a sibling stream owns those).
- Public repo: no hostnames, IPs or tokens. No em dashes in prose. No
  attribution lines in commits.

## Done when

`dfmcp/tests` in `.venv-dfmcp` green (report the count), the migration tested
on a populated copy, and a Result section appended here, including the exact
steps the orchestrator runs to migrate the live store on VM 103 at deploy.

## Result (executor, 2026-10-02)

Done. All four tasks completed, offline only (no VM access, no deploys, no
`web/stream/*`/`dfqueue/*`/publisher/export-script touches).

**What changed**

- `dfmcp/gotchas_store.py`: `entries.tool` is nullable (`SCHEMA_VERSION` 1 to
  2). `validate_new_entry` makes `tool` optional (`None` = general entry) and
  refuses a `kind` with no tool ("kind is meaningless without a tool").
  Every tool-keyed query (`entries_for_tool`, the near-duplicate lookup in
  `add_entry`) uses `tool IS ?`, not `tool = ?`, since SQL `=` never matches
  `NULL`. `tool_index` groups general entries under the key `None`.
  A version-1 store is migrated automatically the first time anything opens
  it (`_connect`, and `init_store`'s existing-file branch), inside one
  transaction: rename `entries`, recreate it with `tool TEXT` (nullable),
  copy every row across unchanged, drop the renamed copy, recreate its two
  indexes, bump `schema_version`. `outcomes` and `status_history` are
  untouched (they reference entries only by id). The migration checks
  `PRAGMA table_info(entries)` first and is a no-op if already nullable, so
  it is safe to run on every open (idempotent on restart) and rolls back
  cleanly on any failure, leaving the store at version 1 for the next
  attempt. Also added: `migrate_store(path)` (explicit, idempotent) and a
  `python -m dfmcp.gotchas_store migrate PATH` CLI command, for running the
  migration by hand before restarting the server rather than relying on the
  lazy path.
- `dfmcp/gotchas_tools.py`: `gotchas.write`'s new-entry mode no longer
  requires `tool`; omitting it writes a general entry (`kind` must also be
  omitted, enforced by the store). `gotchas.get` gains a `general: boolean`
  argument (mutually exclusive with `tool`, and with `kind`, since a general
  entry has none); `general: true` lists general entries with the same
  `list`/`status`/`include_rejected` filters a tool listing already has. The
  no-argument index now also reports general entries (key `None`, rendered
  as `id="" general="true"` in the index XML) rather than crashing on
  sorting a mix of `None` and strings. `entry_xml` renders a tool-less entry
  as `tool=""` plus a new `general="true"/"false"` attribute (every entry
  gets this attribute now, not just general ones). Both tool descriptions
  say plainly what a general entry is for and that game knowledge goes to
  doctrine/the Consultant instead, never here. `NATIVE_TOOL_IDS` is
  unchanged (`gotchas.get`, `gotchas.write`): no new tool was added, only
  new optional arguments on the existing two.
- `agents/CONFIDENCE-LEGEND.md`: one short paragraph, "General entries",
  with the doctrine line. Had to trim it once: the module's own word-cap
  test (`test_confidence.py`) caps the legend at 450 words for prompt
  budget, and my first draft pushed it to 487; the committed version is 445.
- Tests: `dfmcp/tests/test_gotchas_store.py` gained `TestGeneralEntries`
  (write/read a general entry, kind-without-tool refusal, empty-string tool
  is refused rather than silently treated as general, `entries_for_tool`
  with `tool=None`, outcomes/near-duplicate/`tool_index` all working on a
  general entry, same title as general and as tool-scoped is not a
  duplicate) and `TestMigrationV1ToV2` (a hand-built, populated
  schema-version-1 store, built with the literal old `tool TEXT NOT NULL`
  DDL so the test exercises the real upgrade path rather than a store
  `init_store` already created at the current version; checks every row,
  its outcome and its `status_history` entry survive; checks the migration
  is idempotent across repeated opens and via the explicit `migrate_store`/
  CLI command; checks a fresh v2 store is untouched by `migrate_store`).
  `dfmcp/tests/test_gotchas_tools.py` gained `TestGeneralEntries` (the same
  shape over `gotchas.get`/`gotchas.write`, plus the `general`+`tool` and
  `general`+`kind` argument refusals, the `general` field needing to be a
  bool, and the index listing general entries separately) and
  `TestRoleToolCountsUnchanged` (see below).

**Tests, `.venv-dfmcp`**

`"$REPO_ROOT/.venv-dfmcp/Scripts/python.exe" -m pytest dfmcp/tests -q`, run
with the working directory set to this worktree (confirmed first that this
resolves `dfmcp` to the worktree's copy, not the main checkout's, via
`python -c "import dfmcp; print(dfmcp.__file__)"`):

- **752 passed** on this branch (HEAD, commit `5b3e5c8`).
- **728 passed** on the merge base (`52494c9`), measured by `git archive`-ing
  that commit into a scratch directory and running the identical command
  against it, to get an apples-to-apples before/after baseline. Net: +24
  tests (all new, all green), 0 regressions, 0 skips either side.
  (CLAUDE.md's "1845 passed, 3 skipped" / "692" figures are from
  2026-09-25 and already stale regardless of this stream's work; I did not
  update them, since Working.md/decisions/memory are explicitly not mine to
  write per this handoff and CLAUDE.md's own header.)
- Also ran `dfmcp/tests/test_gotchas_store.py` and
  `dfmcp/tests/test_gotchas_tools.py` directly under the ambient `python`
  (no `lupa`, no venv) as I went, per the two modules' own docstrings
  ("imports nothing from the MCP SDK, so it runs under the ambient
  interpreter"): 41 then 53 (store) and 67 then 38-new/105-total (tools),
  all green throughout.

**How I verified tool counts unchanged**

Per-role tool counts are not a simple grep target (the live figures in
CLAUDE.md are "measured live over a real MCP client," which applies
filtering this offline check cannot reproduce), so I verified the thing the
task actually cares about: that this handoff's code changes do not add,
remove, or rename any tool id, or change which roles can reach one.

1. `NATIVE_TOOL_IDS` in `gotchas_tools.py` is untouched: still exactly
   `("gotchas.get", "gotchas.write")`. I changed argument schemas and
   descriptions on those two, never the registry surface.
2. I computed `len(tool_definitions(registry, roster, role))` for
   overseer/architect/consultant/quartermaster/conductor against the real
   `DEFAULT_TOOLS_YAML` and `agents/*/tools.yaml` (not the
   `gotchas_support.py` test stand-ins, which add extra building-tool grants
   on top) at HEAD, then did the same against a `git archive` of the merge
   base `52494c9` in a scratch directory. Both gave identical numbers:
   overseer 99, architect 53, consultant 29, quartermaster 25, conductor 16.
   This confirms no net change from my edits. (These numbers are a static,
   offline measurement and intentionally do not match CLAUDE.md's live
   87/52/29/24/16: that note itself says "measured live... over a real MCP
   client," which filters further than a static registry/roster load can.
   I did not try to reconcile the two; reconciling live vs. static tool-count
   methodology is outside this handoff's scope and not something I can check
   without the live server.)
3. Locked this in as `TestRoleToolCountsUnchanged::
   test_role_tool_counts_match_pre_handoff_baseline` in
   `test_gotchas_tools.py`, so a future change to the registry or an
   agent's `tools.yaml` that silently shifts one of these roles' tool list
   will fail a test rather than go unnoticed.

**Exact live migration steps for VM 103 (for the orchestrator to run; not run
here, no VM access)**

The code change is backward-compatible and self-migrating (any process that
opens the store with the new code upgrades it on first open, automatically
and idempotently), so the simplest safe path is: deploy the new code, then
either restart the server (lazy migration happens on its first store access)
or run the explicit command first for a supervised, auditable migration
before flipping the service over. Recommended as the explicit path:

```
# On VM 103, as whatever user runs dfmcp-server:
GOTCHAS_DB=/var/lib/dfgotchas/uniboslan.gotchas.sqlite3

# 1. Stop the server so nothing writes during the migration.
sudo systemctl stop dfmcp-server

# 2. Back up the store (the migration is transactional and safe, but a
#    schema rebuild on the live store is exactly the kind of thing to keep
#    a copy of first).
sudo cp "$GOTCHAS_DB" "$GOTCHAS_DB.pre-v2-backup-$(date +%Y%m%d%H%M%S)"

# 3. Deploy the new dfmcp code (per the repo's existing deploy process,
#    `git -c core.autocrlf=false archive`; not part of this change).

# 4. Run the migration explicitly and check its reported version.
python -m dfmcp.gotchas_store migrate "$GOTCHAS_DB"
# expected output: "gotcha store at /var/lib/dfgotchas/uniboslan.gotchas.sqlite3 is schema_version 2"

# 5. Sanity-check row counts match the backup (adjust the table/column
#    names only if this store has been through other migrations since):
sqlite3 "$GOTCHAS_DB" "SELECT COUNT(*) FROM entries;"
sqlite3 "$GOTCHAS_DB.pre-v2-backup-"* "SELECT COUNT(*) FROM entries;"
# these two counts must match.

# 6. Restart the server.
sudo systemctl start dfmcp-server
```

Running step 4 is optional in principle (step 6 alone would trigger the same
migration lazily, the first time the server opens the store), but doing it
explicitly, between the backup and the restart, means a migration failure is
caught by this command's own exit code and error message before the service
is back up, rather than surfacing later as a confusing server-startup error.
If step 4 is skipped, `check_store` runs the identical migration path the
first time the server opens the database at startup, so no server restart is
needed afterward either way.

**Unverified / not done**

- Not run against the live store on VM 103 or any other VM: no VM access per
  this handoff's constraints. The migration path above is exercised only
  against a hand-built, populated schema-version-1 store in the test suite
  (`TestMigrationV1ToV2`), not against an actual export or copy of the real
  `uniboslan.gotchas.sqlite3`. If that live file has diverged from the
  schema this module assumes in some way my hand-built fixture does not
  reproduce, the migration could still surprise; running step 4 above with a
  backup in hand, as written, is the mitigation.
- I did not update `Working.md`, `decisions/DECISIONS.md`, or `memory/`, per
  this handoff's rules (the orchestrator owns those).
- I did not reconcile the offline role-tool-count numbers in this result
  (99/53/29/25/16) against the live numbers CLAUDE.md records
  (87/52/29/24/16); see above. Both consultant counts match (29); the other
  three differ by a small, consistent-looking margin that smells like a
  live-only filter (e.g. DFHack-availability or `verified`/`live_deployed`
  gating applied only when actually talking to DFHack), but I have not
  traced that filter's code path to confirm it, since doing so is outside
  this handoff's surfaces and was not necessary to prove my own change was
  neutral.
- I did not touch `web/stream/*`, `dfqueue/*`, the publisher, or the export
  scripts, and did not check whether the site stream's existing reader
  already expects `tool: null` correctly (the handoff states it does; I
  relied on that and did not re-verify it against that stream's code, which
  is explicitly not mine to touch or audit here).
