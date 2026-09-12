# Stream: the MCP transport

**Dispatched** 2026-09-12. **Status:** dispatched.

## Scope

Build `dfmcp/server.py`: the HTTP endpoint that ties the four existing modules
together into an actual MCP server. **This is the last missing piece of the
project's one hard blocker.** Everything it depends on is built, tested, and
merged; nothing in it is a research question any more.

## Read these first, in this order

1. `research/2026-09-12-mcp-server-stack.md` — settles the SDK, the transport,
   the auth hook and the error shape. **Build to it. Do not re-derive it.**
2. `research/2026-09-12-openclaw-mcp-auth.md` — settles the client side. The
   credential is a static bearer token in a header.
3. `docs/AGENT-ARCHITECTURE.md` §13 — the two locked requirements.
4. `dfmcp/README.md` — what the four existing modules already do for you.

## THE NAMING TRAP, read this before you write an import

**The SDK is imported as `mcp`. This repo's package is `dfmcp`.** They were
both `mcp` until 2026-09-12, and a local `mcp/` directory shadows the SDK for
anything running with the repo root on `sys.path`, which is every test run and
the server process itself. That is why the rename happened
(`decisions/DECISIONS.md`, same day).

So: `from mcp.server.lowlevel import Server` is the **SDK**, and
`from dfmcp.roles import load_roster` is **ours**. If you ever find yourself
adding a `sys.path` manipulation to make an import work, stop and report
instead. That is the collision coming back, not a thing to work around.

## What to build

Wire the existing parts; write as little new logic as possible.

- **Low-level `Server` API, not the high-level wrapper.** Per-caller
  `tools/list` is only reachable where per-request identity lives; the
  high-level wrapper returns one static list to every caller. This is the whole
  reason the brief chose it.
- **Transport: streamable HTTP.** Not stdio (client and server are on different
  hosts), not the older SSE transport.
- **Identity: `TokenVerifier`**, resolving the bearer token through
  `dfmcp.auth.resolve` to a role. A token that resolves to nothing is rejected
  at the transport, never passed through as an anonymous caller.
- **Listing: `dfmcp.tools.tool_definitions(registry, roster, role)`** for the
  caller's own role. Do not build a list and filter it afterwards; ask for the
  role's list.
- **Calling:** `Roster.check(role, tool_id)` first, then
  `dfmcp.tools.argv_for_call`, then the connection pool, then parse the JSON
  the tool printed. Every one of those steps already exists.
- **Denials return a tool result carrying `isError`, with the reason string
  `Roster.check` already produces.** Not a protocol-level error: the brief
  found a client raises those inside its own calling code rather than showing
  the model, which would waste a reason string written to be read.
- **Config**: bind address, port, DFHack host/port, and pool size. **Never
  bind `0.0.0.0`.** The bind address is tailnet-only and must be explicit, with
  no default that could accidentally be public. This repo is public: the real
  address goes in `.env`, and `infra/local.example.env` gets a commented
  placeholder, matching what `auth.py` already did for the tokens.
- **Pin the SDK.** The repo pins nothing at the root today; the precedent is
  `evals/*/requirements.txt`. Add `dfmcp/requirements.txt` with an exact pin.
  The brief recommends the 2.x line over the 1.27.1 that happens to be
  installed. **If 2.x will not install or its API differs from the brief's
  reading, stop and report rather than quietly building on 1.x** — that is a
  version decision, not an implementation detail.

## Tests

Against a fake DFHack server, in-process. `dfmcp/tests/test_dfhack_client.py`
already contains one written from the wire spec; reuse it rather than writing
a second.

Four that must exist, because they are the design's actual claims:

1. **An advisor's `tools/list` contains no mutating tool.** Assert it for the
   Architect specifically.
2. **An advisor calling a write tool is refused, and the refusal carries the
   reason string.** This one is load-bearing: `decisions/DECISIONS.md`
   2026-09-12 records that the client-side scoping layer is thin precisely
   because this works, so if it does not, a second layer has to come back.
   Testing only the happy path would leave both layers unexercised.
3. **An unknown or malformed token is rejected**, and the rejection does not
   leak which part was wrong.
4. **A permitted call round-trips**: the right argv reaches the fake DFHack,
   and the JSON it prints comes back parsed.

## Acceptance criteria

1. `pytest` from the repo root passes, count above the current **121**. Report
   both numbers.
2. `tests/test_no_leaked_addresses.py` still passes. Loopback is fine and is
   not a leak; a real bind address in a tracked file is.
3. `dfmcp/README.md` gains a section in the voice of the existing ones,
   including what is still unproven because nothing has met a real DFHack.
4. Write the systemd unit as a file with a comment saying it is undeployed.

## Out of scope

- **No deployment. Do not touch VM 103 or VM 106.** VM 103 runs the live fort.
  Build to the line, then stop and report the exact commands, per rule 2.
- **Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.** Report
  findings; the orchestrator writes the rows.

## Report

Executor report shape, plus **"Findings to record"**. Be specific about
anything in either research brief that turned out wrong when you built against
it. That is the most valuable thing you can return, and both briefs were
source reads that have never been run.
