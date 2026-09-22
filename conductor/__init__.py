"""The conductor: the code that runs the agent loop (`docs/AGENT-LOOP.md`).

Named `conductor`, not `queue` or `mcp` -- this repo's CLAUDE.md flags both
as names that shadow a stdlib module or the MCP SDK for anything importing
with the repo root on `sys.path` (the same trap `dfmcp`/`dfqueue` were
already renamed to avoid). See `conductor/service.py` for the entry point
and `docs/AGENT-LOOP.md` §1 for the cycle this package implements.

No model is inside the conductor: every module here is deterministic code,
run by a service account, never by an agent. `agents/conductor/role.md`
documents the MCP role this service authenticates as; nothing in this
package is a prompt or is ever read by a model.
"""
