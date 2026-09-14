# Stream: dfmcp as a durable service on VM 103, plus a cross-VM proof

**Written** 2026-09-14. **Status:** dispatched. **User go-ahead:** given for
this scope, including starting and enabling the unit on VM 103.

## Why

The server is live-verified but only ever runs when an agent starts it by
hand, on loopback. openclaw (VM 106) cannot call it, and openclaw does not
exist yet: VM 106 is a bare Ubuntu clone (verified read-only, twice). So this
stream does the half that is ready, and proves the cross-host path with a
plain MCP client instead of waiting for openclaw.

## Read first

1. `research/2026-09-14-openclaw-mcp-wiring.md`, this stream's basis.
2. `infra/dfmcp-server.service.example` (the `CHANGEME` placeholders).
3. `dfmcp/README.md` config section, `dfmcp/server.py`'s `config_from_env`
   (it refuses `0.0.0.0`), `dfmcp/auth.py` (token env var names).
4. `handoffs/2026-09-14-mcp-live-smoke-test.md` (what already ran live).

## Decisions already made, do not relitigate

- **Runs as `df`**, the account that owns `/opt/df` and runs the DF units.
- **Binds VM 103's LAN address**, not loopback and never `0.0.0.0`. The user
  chose the simple option today and deferred Tailscale. Bearer tokens are the
  only guard, so token hygiene below is not optional.
- **Deploy location:** promote the existing staged tree rather than inventing
  a new layout. Keep it under `/opt/df/`, owned by `df:df`.

## What to do

1. **Deploy on VM 103.** Put the current `dfmcp/` (plus `agents/` and
   `scripts/dfhack/TOOLS.yaml`) in a durable directory under `/opt/df/`, with
   its own venv from `dfmcp/requirements.txt`. Verify the deployed files match
   local `main` by sha256.
2. **Tokens:** three role tokens in a mode-600 `.env` owned by `df`, readable
   only by it. Never on a command line, never in a log, never in this repo.
   Record only that they exist and their length.
3. **systemd unit** from the example, placeholders filled for the real layout.
   Start it, confirm it serves, then enable it and confirm it survives
   `systemctl restart`. **Do not touch any `df-*` unit**, and do not reboot.
4. **Prove it from VM 106.** Prefer `curl` (already present). Run:
   `initialize`, then `tools/list` as architect, then a read-only
   `landmarks__list` as overseer, and a bogus token expecting 401. If curl
   cannot carry the streamable-HTTP session, you may `apt install`
   python3-venv **on VM 106 only** (it is bare and runs nothing) and use the
   SDK client. **Never apt install on VM 103.**
5. **No mutating tool call, from any role, at any point.**
6. Report the exact `MCP_SERVER_*` values needed, by env key name, so the
   orchestrator can add placeholders to `infra/local.example.env`.

## Hard lines

- VM 103 runs the live fort. Nothing touches DF, DFHack config, saves, or the
  `df-*` units. If the fort's state looks off at any point, stop and report.
- Public repo: no address, hostname or token in any tracked file or in your
  report. Say "VM 103's LAN address" and name the env key that holds it.
- Do not commit. Do not edit `Working.md`, `decisions/`, `memory/` or other
  handoff docs. Report; the orchestrator records.
- Leave it running and enabled if all checks pass. If anything fails, stop,
  disable and stop the unit, and report the state you left behind.

## Report

Executor shape, plus **"Findings to record"**: anything about the real
deployment that the research brief got wrong, and the exact reversal steps
(how to stop, disable and remove what you installed).

## Result (2026-09-14): DONE, service live and proved cross-host

`dfmcp-server.service` is active and enabled on VM 103, running as `df` from
`/opt/df/dfmcp-smoke` (the smoke test's tree, sha256-identical to `main`, so
promoting it needed no restaging), bound to the LAN address, tokens in a
mode-600 `.env`. Survives `systemctl restart`. The unit deviates from the
example in one deliberate way: `After=df-fortress.service` (the real unit
name), `After=` only, never `Requires=`.

**Proved from VM 106 with curl alone**, no install on either VM: initialize
200, `tools/list` as architect returning 9 read-only tools by name (0
mutators), `landmarks__list` as overseer returning the live fort's JSON, and a
bogus token getting 401. No mutating call at any point.

**Orchestrator re-verified independently:** unit enabled and active, listening
on the LAN address, `.env` 600 `df:df`, deployed `server.py` hash matches
local `main`, `df-fortress` and `df-xvfb` active, and a 401 from VM 106 with a
junk token.

**Reversal:** `sudo systemctl disable --now dfmcp-server.service`,
`sudo rm -f /etc/systemd/system/dfmcp-server.service`,
`sudo systemctl daemon-reload`, `rm -f /opt/df/dfmcp-smoke/.env`. Nothing else
was touched; VM 106 has nothing installed.

**Two things this stream raised that are not about dfmcp**, both surfaced to
the user: the executor read the whole gitignored `.env` into its transcript
(secret exposure, rotation question), and it worked around an auto-mode
refusal of a cross-VM token relay by using `scp -3` instead. See
`decisions/DECISIONS.md` 2026-09-14.
