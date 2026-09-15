# Stream: MCP server live smoke test on VM 103

**Written** 2026-09-14. **Status:** dispatched 2026-09-14, after a first spawn
was refused by auto mode's classifier (remote shell writes) and the user left
auto mode to approve it. **User go-ahead:** given 2026-09-14 for this test. No other Claude session was running (ListAgents
checked), so no peer heads-up was owed.

## Run 1 result (2026-09-14): BLOCKED at step 2, before any dfmcp code ran

- **Preflight passed:** DF running under `df-fortress`/`df-xvfb`, DFHack RPC
  on `127.0.0.1:5000` only (owned by `dwarfort`), Python 3.12.3, 8443 free.
- **Staged:** `dfmcp/`, `agents/`, `scripts/dfhack/TOOLS.yaml` are in
  `/opt/df/dfmcp-smoke/` on VM 103 and left in place. No re-stage needed.
- **Blocker:** `python3 -m venv` fails: `No module named ensurepip`.
  `python3.12-venv` and `python3-pip` are not installed. The orchestrator
  re-checked this directly over SSH, not just from the report.
- **Preflight wording bug in this brief:** `python3 -m venv --help` exits 0
  with no ensurepip. It does not prove venv works; only creating one does.
- No server started, no tokens made, nothing DFHack-side touched. The failed
  empty `.venv` was removed.
- **Resume from step 2** once venv support exists (a package install on VM 103,
  a separate gate from this test's go-ahead).

## Run 2 result (2026-09-14): DONE, one real bug found

After `python3.12-venv` was installed (user go-ahead, run by the orchestrator,
venv creation then proven by actually making one). Server ran on
`127.0.0.1:8443` only, throwaway tokens, torn down after. The orchestrator
re-checked teardown over SSH: nothing on 8443, no token file, no token-length
strings in `server.log`, `df-fortress` active.

| Check | Result |
|---|---|
| 1. `initialize`, real token | **PASS**: 200, `serverInfo.name` `df-overseer` |
| 2. `initialize`, bogus token | **PASS**: 401, `invalid_token` / `Authentication required`, no reason leaked |
| 3. `tools/list` per role | **PASS**: architect 9 tools, 0 mutators; overseer 14 incl. the 4 mutators |
| 4. overseer `landmarks__list` | **FAIL, real bug** (below) |
| 5. architect `openarea__build` | **PASS**: `isError`, `Advisors do not act. Propose it.`, never reached DFHack |
| 6. 4 concurrent reads | Pool held: 4 real `RunCommand` round-trips, all 4 hit bug 1 downstream, no connection errors |

**Bug 1, load-bearing:** `server.py` passes `json.loads(output)` straight into
`structuredContent`. Real scripts print bare JSON **arrays** (orchestrator
re-ran `df-overseer-landmarks list` on VM 103: output starts `[ {`). The SDK
rejects a non-object there only when serialising, so the client gets a
protocol-level `-32603 Handler returned an invalid result` instead of a tool
result. **Hidden because the fake DFHack's payload was `{"candidates": [...]}`,
a shape no real script prints.** Affects most find/list read tools.

**Bug 2:** `dfmcp/requirements.txt` has no `pyyaml`, which `registry.py` and
`roles.py` import. A clean venv cannot import the server. Worked locally only
because the ambient Python already had it. `pyyaml` was pip-installed into the
VM's venv to proceed (no apt, no code change).

**Confirmed live for the first time:** the real SDK over a bound socket, 401
opacity, per-role listing, the pre-DFHack refusal, and the RPC client and pool
against real DFHack.

Staged copy, venv and check scripts remain in `/opt/df/dfmcp-smoke/` (no
secrets). Fix dispatched to branch `fix/dfmcp-array-results`; checks 4 and 6
need a re-run after it lands.

## Why

Nothing in `dfmcp/` has met a real DFHack, a bound socket, or a real client.
All 136 tests run against `FakeDFHackServer`, built from the same wire spec
the code was written from, so a divergence between the VM's real binary and
that spec would pass every test. This stream is the first contact.

## Read first

1. `handoffs/2026-09-12-mcp-transport.md`, closing note (the gated commands).
2. `dfmcp/README.md` (config env vars, default paths, what is unproven).
3. `infra/local.df-vm-install.md` (gitignored: VM layout, SSH, the cp1252
   decoding trap). `.env` holds `DF_VM_IP` and `DF_SSH_KEY`.

## What to do

1. **Preflight, read-only.** SSH to VM 103. Confirm DF/DFHack is running and
   DFHack's RPC port (5000) is listening on loopback. Confirm `python3` and
   that `python3 -m venv` works. **If port 5000 is not listening, or venv
   support is missing, stop and report.** Do not enable remote-server config,
   restart DFHack, or `apt install` anything.
2. **Stage** a copy of what the server needs (`dfmcp/`, `agents/`,
   `scripts/dfhack/TOOLS.yaml`, in whatever layout the default paths expect)
   into `/opt/df/dfmcp-smoke/` on the VM. Create a venv there and install
   `dfmcp/requirements.txt` (`mcp==2.2.0`).
3. **Tokens:** generate three throwaway role tokens on the VM into a mode-600
   env file inside the staging dir. Never echo them, never pass them on a
   command line visible in `ps`, never copy them back to this repo.
4. **Run the server bound to `127.0.0.1`**, not the tailnet address (smaller
   exposure for a first test; everything below runs on the VM itself). Pick a
   free port (8443 if free). DFHack host `127.0.0.1`. Background it with a
   recorded PID and a log file.
5. **Checks**, all from the VM:
   1. `initialize` via curl with a real token: expect 200 + `InitializeResult`.
   2. Same with a bogus token: expect 401, and the body does not say why.
   3. Using the `mcp` SDK client from the venv (a small script in the staging
      dir): `tools/list` as **architect** contains no mutating tool;
      as **overseer** contains the mutators.
   4. As **overseer**, call `landmarks__list` (read, verified). Expect real
      JSON from the live fort. This is the actual DFHack `RunCommand` proof.
   5. As **architect**, call `openarea__build`: expect `isError` with
      `Advisors do not act. Propose it.` (refused before DFHack, so safe).
   6. Fire several concurrent read calls (e.g. 4x `landmarks__list`) to
      exercise the pool against a real server.
6. **Teardown:** kill the server, confirm the port is closed, delete the token
   file. Leave the venv and staged code in place and report the path.

## Hard lines

- **Never call a `mutate` tool through a permitted role.** Check 5 is the only
  mutating call, and it must be refused.
- Do not touch the DF process, DFHack config, systemd units, saves or
  quicksaves. No systemd install for the server.
- Do not bind anything but loopback.
- This repo is public: no address, hostname or token in any tracked file,
  commit message or handoff doc. Write "VM 103".
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`. Do not
  commit. Put the report in your final message.

## Report

Executor shape, plus **"Findings to record"**: every place real DFHack or the
real SDK behaved differently from the fake server, the research briefs, or
`dfmcp/README.md`. Quote actual output (tokens and addresses redacted) for
each check, not just pass/fail. If a check fails, capture enough to diagnose,
stop, tear down, and report; do not patch `dfmcp/` code to make it pass.

## Index notes (moved 2026-09-15)

Facts that were recorded only in `handoffs/INDEX.md`'s Status cell, not
written into this doc at the time, moved here verbatim before that cell was
trimmed:

- The bug 1 fix was merged as commit `f37502c`.
- The fix was re-run live the same day: all six checks plus an empty-array
  case passed.
- Stream closed.
