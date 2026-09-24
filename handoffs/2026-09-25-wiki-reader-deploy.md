# Handoff: deploy the wiki reader and finish the Consultant's switch-over

Date: 2026-09-25. **Executor. A small code fix, then live on VM 103. User's
go-ahead given for the fix, the deploy, a `dfmcp-server` restart and the
switch-over.**

Read `CLAUDE.md`, `handoffs/2026-09-25-wiki-switchover.md` (its Result), the
"Switch-over, 2026-09-25" section of
`evals/live/2026-09-24-wiki-mirror-deploy/README.md`, `dfmcp/wiki_reader.py`
and `dfmcp/knowledge_tools.py`.

## State you start from

The mirror is promoted at `/var/lib/dfwiki/df-wiki.sqlite3`; `df` is already
in the `dfwiki` group (read only; journal mode `delete`). `dfmcp-server` runs
from `/opt/df/dfmcp-smoke/`, env in `/opt/df/dfmcp-smoke/.env`, which still
points `MCP_SERVER_WIKI_SNAPSHOT` at the old JSON snapshot. The S4 reader
code was merged but never deployed: the live `knowledge_tools.py` has no
`wiki_search`, and `wiki_reader.py` is absent. Live tool counts: overseer 79,
architect 49, consultant 27, quartermaster 24, conductor 15.

## Steps

1. `git merge --ff-only main`. The orchestrator checked `ListAgents`: no other
   df-automation session is running.
2. **The bug fix, offline first.** When `_load_wiki_snapshot` (or whatever
   loads the JSON path) is given a file that is not valid UTF-8 JSON, it lets
   `UnicodeDecodeError` escape as a raw MCP error. Make it a clean
   `KnowledgeToolError` with a useful message, add a test that fails without
   the fix, and run `dfmcp/tests` in `.venv-dfmcp` (691 before your test) and
   the ambient suite. Commit.
3. **Work out exactly what to ship.** Diff every file under the live
   `/opt/df/dfmcp-smoke/` tree that S4 or your fix touches against
   `git -c core.autocrlf=false show HEAD:<path>`: at least
   `dfmcp/wiki_reader.py` (new), `dfmcp/knowledge_tools.py`,
   `agents/consultant/tools.yaml`, and anything those import that is also
   missing or stale on the VM. **Report every difference that is not the
   wiki reader or your fix.** If shipping a file would also ship other
   undeployed changes that are not trivially safe, stop and report the list
   before deploying.
4. **Before**: `dfmcp-server` MainPID, per-role tool counts via a real MCP
   client, and one real consultant `knowledge.wiki_lookup` call on the old
   snapshot as a baseline.
5. Deploy with `git -c core.autocrlf=false archive` (committed bytes),
   sha256 committed against landed, back up each overwritten file. Point
   `MCP_SERVER_WIKI_SNAPSHOT` at `/var/lib/dfwiki/df-wiki.sqlite3` (reuse or
   refresh the existing env backup). Restart `dfmcp-server` only.
6. **After**, through the real server:
   - tool counts: consultant expected 28, the other roles unchanged; explain
     any other change.
   - as consultant, `knowledge.wiki_lookup` on "Tomb" and "Office" and
     `knowledge.wiki_search` on a rooms or office query: show revid,
     staleness (`fresh` expected), and a line of real section text.
   - as overseer and quartermaster, the same call is refused.
   - `doctrine.get` still works for the consultant (it reads a separate
     file; confirm nothing regressed).
7. If step 6 fails, restore every backup, restart, confirm the baseline call
   from step 4 behaves identically, and report.
8. Extend the eval README with a "Reader deploy and switch-over, 2026-09-25"
   section. Run `tests/test_no_leaked_addresses.py` before committing.

## Out of scope

Timers (S8), S7, the four `store.py` gaps, `df-fortress`, `df-xvfb`, the fort,
the refresh job, `/var/lib/dfwiki/` permissions (already correct).

## Rules

- You own the fix and its test, that eval README, and this doc's Result
  section. Not `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md`,
  `CLAUDE.md`.
- Read secrets by key, never whole files. No hostname, address or contact
  value in anything committed.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit as you go. Stop and report on any permission or classifier refusal.

## Done means

The Consultant answers from the new mirror, proven by real calls through the
server, consultant at 28 tools, other roles unchanged, the bug fixed with a
test, and a list of anything else found undeployed.

## Result
