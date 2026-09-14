# Stream: get openclaw running on VM 106 and learn its real config schema

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** given for
continuing the openclaw seam. VM 106 is bare and runs nothing, so this is the
low-risk half.

## Why

`dfmcp` is a live, enabled service on VM 103 and VM 106 has already called it
with curl. The only thing left is the real client. **openclaw is not
installed anywhere**, and the `mcp.servers` / `agents.entries` schema in
`research/2026-09-12-openclaw-mcp-auth.md` was read from upstream source and
has never been confirmed against a running build. The scaffold at
`../openclaw` uses an unrelated `agent.yaml` shape with no `mcp` key at all.
**So the deliverable here is knowledge, not a wired client.**

## Read first

1. `research/2026-09-14-openclaw-mcp-wiring.md` (the recon, and its own
   correction note at the end).
2. `research/2026-09-12-openclaw-mcp-auth.md` (the schema claims to test).
3. `C:\website-projects\openclaw` (the scaffold: `docker-compose.yml`,
   `config/*/agent.yaml`). It is a separate repo. **Do not commit in it.**
4. `docs/AGENT-ARCHITECTURE.md` §13 (the two locked requirements).

## What to do

1. **Install Docker on VM 106** (apt is fine here, it is a bare VM). Nothing
   else on that host matters, so prefer the distro packages unless the image
   needs newer.
2. **Get openclaw running**: pull `ghcr.io/openclaw/openclaw:latest` and start
   it. **If the image does not exist or needs credentials, stop and report** —
   that is a fact worth more than a workaround.
3. **Learn the real config schema.** Whatever the running build actually
   reads: config file locations, the shape for registering an MCP server over
   HTTP with an `Authorization` header, and the shape for per-agent tool
   allow/deny lists. Prefer primary evidence, in this order: a JSON schema or
   `--help` from the binary, the image's own docs or example configs, then
   source inside the image. **Quote what you find, with the path inside the
   container.**
4. **Test that it parses**, not that it talks to a model: add our server as an
   MCP entry pointing at VM 103's LAN address with a **placeholder** token,
   and get openclaw to validate or list its config. A "server registered,
   auth failed" style result is a pass here.
5. **Write up the diff** between what the 2026-09-12 brief claimed and what
   the running build actually wants, entry by entry.

## Hard lines

- **No real role tokens on VM 106**, and no LLM API key anywhere on that host.
  This stream must not make a single paid model call. Wiring a real token and
  running an agent is a separate, gated step.
- **Do not touch VM 103.** The live fort and the MCP service are on it. You
  may point config at its address, but change nothing there.
- Public repo: no address, hostname or token in any tracked file or in your
  report. Name env keys instead.
- Do not commit, in this repo or the scaffold. Do not edit `Working.md`,
  `decisions/`, `memory/` or other handoff docs.
- If the estate gains a listening service, say so plainly in the report: it is
  a `home-lab` `inventory/services.yaml` obligation.

## Report

Executor shape, plus **"Findings to record"**: the schema as it really is, the
per-entry diff against the old brief, what openclaw needs that we have not
planned for (secrets handling, model config, storage), and the exact reversal
steps for everything you installed.
