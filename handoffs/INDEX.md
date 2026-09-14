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
| dfmcp durable deploy | [2026-09-14-dfmcp-deploy.md](2026-09-14-dfmcp-deploy.md) | **DONE 2026-09-14**: `dfmcp-server.service` active and enabled on VM 103, LAN-bound, and called for real from VM 106 with curl. Two non-dfmcp issues raised (a `.env` over-read, an auto-mode workaround), both in the register. | VM 103 `/etc/systemd/system/`, `/opt/df/dfmcp-smoke/`; no tracked repo files |
| MCP live smoke test | [2026-09-14-mcp-live-smoke-test.md](2026-09-14-mcp-live-smoke-test.md) | **DONE 2026-09-14**, 5 of 6 checks passed. Run 1 blocked on missing `python3.12-venv` (installed with go-ahead); run 2 found a real bug: array tool output breaks `structuredContent`. Fix merged (`f37502c`) and re-run live the same day: **all six checks plus an empty-array case passed**. Stream closed. First contact with real DFHack on VM 103. Loopback bind only, no mutating calls. | VM 103 `/opt/df/dfmcp-smoke/` only; no tracked repo files |
| MCP transport | [2026-09-12-mcp-transport.md](2026-09-12-mcp-transport.md) | **DONE 2026-09-12**, merged (`671ac3a`), 121 tests (ambient env, mcp 1.27.1: 121 passed + 1 skipped by design) to 136 (venv with `dfmcp/requirements.txt`'s `mcp==2.2.0` pin installed). No deployment; no live DFHack. See handoff doc's closing note. | `dfmcp/server.py`, `dfmcp/tests/test_server.py`, `dfmcp/tests/test_dfhack_client.py` (purely additive), `dfmcp/requirements.txt`, `dfmcp/README.md`, `infra/local.example.env`, `infra/dfmcp-server.service.example` |
| DFHack RPC client | [2026-09-12-dfhack-rpc-client.md](2026-09-12-dfhack-rpc-client.md) | **DONE 2026-09-12**, merged, 86 tests to 121. No live verification (barred from VM 103 by design); see handoff doc's closing note for the exact command to run that check. | `dfmcp/dfhack_client.py`, `dfmcp/tests/test_dfhack_client.py`, `dfmcp/README.md` |
| openclaw install + real schema | [2026-09-14-openclaw-install.md](2026-09-14-openclaw-install.md) | **DONE 2026-09-14.** `ghcr.io/openclaw/openclaw:latest` (2026.9.4) run read-only via CLI on VM 106; real `openclaw.json` schema pulled and quoted; MCP entry registered and probed against VM 103 with a placeholder token (real 401, confirmed by curl too); `${VAR}` substitution verified live. Scaffold check: only `OPENCLAW_CONFIG_DIR` and `OPENCLAW_AUTH_PROFILE_SECRET_DIR` are unread (use `OPENCLAW_STATE_DIR`); the executor's wider "nothing matches" claim came from searching the 22 KB launcher only and was corrected by the orchestrator. No paid model call, no real token, no commits, nothing left listening on VM 106. | VM 106 `/opt/openclaw/` only; no tracked repo files (scaffold repo `../openclaw` read but not edited or committed) |

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
