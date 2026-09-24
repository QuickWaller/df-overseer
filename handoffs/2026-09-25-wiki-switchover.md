# Handoff: switch the Consultant's wiki tools over to the new mirror

Date: 2026-09-25. **Executor. Live on VM 103. User's go-ahead given for this
switch-over, including a `dfmcp-server` restart.**

Read `CLAUDE.md`, `docs/CONSULTANT-WIKI.md` section 10,
`evals/live/2026-09-24-wiki-mirror-deploy/README.md` (its "What the
dfmcp-server switch-over and timers would still need" section especially),
and `dfmcp/wiki_reader.py` plus the wiki section of `dfmcp/knowledge_tools.py`.

## State you start from

The mirror is promoted at `/var/lib/dfwiki/df-wiki.sqlite3` (4,450 pages,
59 MB), directory owned `dfwiki:dfwiki` mode 750. `dfmcp-server` runs as `df`
and currently points `MCP_SERVER_WIKI_SNAPSHOT` at the old 30-page JSON
snapshot (backed up under `/var/lib/dfwiki/backup-2026-09-24/`). No timers.

## Steps

1. `git merge --ff-only main`. The orchestrator checked `ListAgents`: no other
   df-automation session is running.
2. **Before**: record `dfmcp-server`'s MainPID, its current environment for
   `MCP_SERVER_WIKI_SNAPSHOT` (where it is set: unit file, drop-in or env
   file; find it, don't assume), and the live tool count per role (overseer,
   architect, consultant, quartermaster, conductor). CLAUDE.md records
   consultant as 28 but the last live read was 27; list the consultant's
   actual tool names so the discrepancy can finally be explained.
3. **Read access.** The chosen approach is to add `df` to the `dfwiki` group
   (read-only by group; `dfwiki` stays the only writer). Check what the
   reader actually needs from SQLite: how `wiki_reader.py` opens the file
   (read-only URI? `immutable`?) and whether the database is in WAL mode,
   since a WAL database opened read-only by another user needs the `-shm`
   and `-wal` files to exist and be readable, or the open fails. Set group
   read on the directory and files accordingly. Never give `df` write access.
   If the only working route needs write access for `df`, stop and report.
4. Point `MCP_SERVER_WIKI_SNAPSHOT` at `/var/lib/dfwiki/df-wiki.sqlite3` in
   whichever place it is set, back up the old file first, restart only
   `dfmcp-server`. A group change needs the restart to take effect.
5. **After**: the new MainPID, service active, per-role tool counts again,
   and **real calls through the MCP server as the consultant role**:
   `knowledge.wiki_lookup` and `knowledge.wiki_search` on "Tomb" and on a
   query about offices or rooms, showing results carry revid, staleness
   `fresh` and real section text, not the old snapshot. Also check a call as
   a non-consultant role is still refused.
6. Rollback is the backed-up env and restart. If step 5 fails, roll back,
   confirm the old behaviour returned, and report.
7. Extend `evals/live/2026-09-24-wiki-mirror-deploy/README.md` with a
   "Switch-over, 2026-09-25" section: commands and trimmed real output. Run
   `tests/test_no_leaked_addresses.py` before committing.

## Out of scope

Timers (S8), S7, any code change (report bugs, don't fix), `df-fortress`,
`df-xvfb`, the fort, and the refresh job itself.

## Rules

- You own that eval README and this doc's Result section only. Not
  `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md`, `CLAUDE.md`.
- Read secrets by key, never whole files. No hostname, address or contact
  value in anything committed.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit as you go. Stop and report on any permission or classifier refusal.

## Done means

The Consultant's wiki tools answer from the new mirror, proven by real calls
through the server, with before/after tool counts and the consultant's tool
list recorded, and nothing else on the VM changed.

## Result

**Not completed as scoped; blocked on a real code-deploy gap, not a
permissions problem.** Full detail and every command/output:
`evals/live/2026-09-24-wiki-mirror-deploy/README.md`, "Switch-over,
2026-09-25" section.

Summary: step 2's before-state read matched CLAUDE.md's live counts
(overseer 79, architect 49, consultant 27, quartermaster 24, conductor 15).
The 27-vs-28 discrepancy is explained: `dfmcp/wiki_reader.py` and the
`knowledge.wiki_search` dispatch in `dfmcp/knowledge_tools.py` (both
committed to this repo, the S4 stream) have never been deployed to VM 103 --
the deployed `NATIVE_TOOL_IDS` tuple omits `WIKI_SEARCH` entirely and
`wiki_reader.py` does not exist on disk there. Step 3 (read access) was
completed and kept: `df` added to the `dfwiki` group (group membership only,
no mode/ownership change; the database is confirmed journal_mode `delete`,
not WAL, so no `-wal`/`-shm` sidecar concern). Step 4 was attempted for real
per the handoff's own design (env pointed at the new mirror, `dfmcp-server`
restarted) and failed exactly as step 6 anticipates: `knowledge.wiki_lookup`
throws an unhandled `UnicodeDecodeError` (old code tries to `json.load` the
binary SQLite file) and `knowledge.wiki_search` is `"unknown tool"` --
confirming the tool was never registered, not merely stale. Rolled back per
step 6, verified clean (old snapshot behaviour returned, tool counts
unchanged, `df-fortress`/`df-xvfb` untouched throughout). One accidental
finding: the old `snapshot.json` read had been silently broken by the prior
day's wikimirror deploy locking down `/var/lib/dfwiki/`'s directory mode;
this stream's group grant plus restart fixed that as a side effect.

**Next step for the orchestrator:** schedule a code-deploy stream to ship
`dfmcp/wiki_reader.py`, the `knowledge_tools.py` wiki-search wiring, and
`agents/consultant/tools.yaml` to VM 103, then re-run this switch-over's
steps 4-5. The `dfwiki` group grant from step 3 does not need to be redone.
