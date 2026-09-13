# Stream: MCP server live smoke test on VM 103

**Written** 2026-09-14. **Status:** not yet dispatched; the first spawn was
refused by the harness's permission layer (remote shell writes), pending the
user's call. **User go-ahead:** given 2026-09-14 for this test. No other Claude session was running (ListAgents
checked), so no peer heads-up was owed.

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
