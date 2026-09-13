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
| MCP tool schema + auth | [2026-09-12-mcp-tool-schema.md](2026-09-12-mcp-tool-schema.md) | **DONE 2026-09-12**, merged, 45 tests to 86 | `dfmcp/tools.py`, `dfmcp/auth.py`, `dfmcp/tests/test_tools.py`, `dfmcp/tests/test_auth.py`, `dfmcp/README.md`, `infra/local.example.env` |
| MCP live smoke test | [2026-09-14-mcp-live-smoke-test.md](2026-09-14-mcp-live-smoke-test.md) | **DONE 2026-09-14**, 5 of 6 checks passed. Run 1 blocked on missing `python3.12-venv` (installed with go-ahead); run 2 found a real bug: array tool output breaks `structuredContent`. Fix merged (`f37502c`); checks 4 and 6 still to re-run live. First contact with real DFHack on VM 103. Loopback bind only, no mutating calls. | VM 103 `/opt/df/dfmcp-smoke/` only; no tracked repo files |
| MCP transport | [2026-09-12-mcp-transport.md](2026-09-12-mcp-transport.md) | **DONE 2026-09-12**, merged (`671ac3a`), 121 tests (ambient env, mcp 1.27.1: 121 passed + 1 skipped by design) to 136 (venv with `dfmcp/requirements.txt`'s `mcp==2.2.0` pin installed). No deployment; no live DFHack. See handoff doc's closing note. | `dfmcp/server.py`, `dfmcp/tests/test_server.py`, `dfmcp/tests/test_dfhack_client.py` (purely additive), `dfmcp/requirements.txt`, `dfmcp/README.md`, `infra/local.example.env`, `infra/dfmcp-server.service.example` |
| DFHack RPC client | [2026-09-12-dfhack-rpc-client.md](2026-09-12-dfhack-rpc-client.md) | **DONE 2026-09-12**, merged, 86 tests to 121. No live verification (barred from VM 103 by design); see handoff doc's closing note for the exact command to run that check. | `dfmcp/dfhack_client.py`, `dfmcp/tests/test_dfhack_client.py`, `dfmcp/README.md` |

**One thing this first run proved, and it is the reason the commit-as-you-go
rule in `.claude/agents/executor.md` exists:** the stream's session ended
mid-run, for the second time in one day. Both deliverables were already
committed to its branch and survived intact; only the final doc pass was lost,
and it was finished from the orchestrator session rather than re-run. **Check
the worktree branch before assuming a terminated stream lost anything** — the
work is usually there.

Research briefs are not streams and are not listed here: they are read-only,
produce a `research/<date>-<slug>.md` file, and are dispatched to the
`researcher` agent directly.
