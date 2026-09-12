# Handoff streams

One row per dispatched stream. A stream is one `executor` agent's worth of
work: a written brief, a named set of touched surfaces, and acceptance
criteria it can check itself.

Created 2026-09-12, when the MCP server build was split across parallel
agents. The convention comes from this repo's template (`.claude/agents/executor.md`
refers to this file); it had never actually been needed until there was more
than one stream in flight at once.

**Chokepoint rule:** two streams must never list the same file under "touched
surfaces". If they would, they are one stream.

**Doc ownership, deliberately different from `executor.md`'s default:** the
orchestrator session owns `Working.md`, `decisions/DECISIONS.md` and
`memory/`. Executors do **not** write to them — they report, and the
orchestrator records. That keeps the register in one voice and avoids three
agents conflicting on a 500-line file. Executors *do* update their own row
here and their own handoff doc.

| Stream | Doc | Status | Touched surfaces |
|---|---|---|---|
| MCP tool schema + auth | [2026-09-12-mcp-tool-schema.md](2026-09-12-mcp-tool-schema.md) | **DONE 2026-09-12**, merged, 45 tests to 86 | `mcp/tools.py`, `mcp/auth.py`, `mcp/tests/test_tools.py`, `mcp/tests/test_auth.py`, `mcp/README.md`, `infra/local.example.env` |

**One thing this first run proved, and it is the reason the commit-as-you-go
rule in `.claude/agents/executor.md` exists:** the stream's session ended
mid-run, for the second time in one day. Both deliverables were already
committed to its branch and survived intact; only the final doc pass was lost,
and it was finished from the orchestrator session rather than re-run. **Check
the worktree branch before assuming a terminated stream lost anything** — the
work is usually there.

| DFHack RPC client | [2026-09-12-dfhack-rpc-client.md](2026-09-12-dfhack-rpc-client.md) | dispatched 2026-09-12 | `mcp/dfhack_client.py`, `mcp/tests/test_dfhack_client.py`, `mcp/README.md` |

Research briefs are not streams and are not listed here: they are read-only,
produce a `research/<date>-<slug>.md` file, and are dispatched to the
`researcher` agent directly.
