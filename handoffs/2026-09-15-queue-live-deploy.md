# Stream: deploy the queue tools to VM 103, verify live, architect run #3 (Phase B)

**Written** 2026-09-15. **Status:** dispatched 2026-09-15. Phase A merged to
`main` as `85826c3`. **User go-ahead:** given 2026-09-15 for Working.md item 1,
and **re-confirmed at dispatch time** ("go for it") for this deploy and run.
Peer check-in done at dispatch: no other session on this repo.

## Why

Phase A built `queue.propose`/`pass`/`rule`/`pending` as MCP tools, tested
against a fake DFHack only. This stream puts them in front of the real fort and
a real agent. The question run #3 answers: **does write-time validation fix run
#2's regression**, where the architect dropped the proposal record entirely?

## Read first

1. `handoffs/2026-09-15-queue-into-dfmcp.md`, especially its Result section's
   "Draft Phase B deploy checklist" and "Review fixes".
2. `handoffs/2026-09-14-dfmcp-deploy.md` (how the service was deployed, its
   reversal steps) and `handoffs/2026-09-14-mcp-live-smoke-test.md` (how a
   loopback throwaway instance was run).
3. `evals/live/2026-09-14-architect-second-charter/README.md` (the exact run
   procedure, pinned config, task prompt).
4. `dfmcp/README.md`'s queue tools section.

## Decisions already made, do not relitigate

- **Deploy target:** the existing tree at `/opt/df/dfmcp-smoke`, `df:df`,
  existing venv. **Before touching it, copy it to a dated backup directory**
  under `/opt/df/` so rollback is "restore and restart".
- **Queue data lives outside the code tree.** Prefer systemd's
  `StateDirectory=dfmcp` (creates `/var/lib/dfmcp` owned by the unit's `User`,
  and writable under `ProtectSystem=strict` without a hand-added
  `ReadWritePaths`), with `MCP_SERVER_QUEUE_DB=/var/lib/dfmcp/Uniboslan.sqlite3`.
  Read the **installed** unit first; if it differs from the example in a way
  that makes this wrong, stop and report rather than improvising.
- **`.env`: append one key, never read the file whole.** Check for an existing
  key with `grep -c '^MCP_SERVER_QUEUE_DB=' .env`, then append. Never print a
  token (CLAUDE.md, "Read secrets by the key you need").
- **The live queue gets no test records.** It is append-only and public-report
  material. Every check that writes a valid record runs on a **throwaway
  loopback instance** of the same deployed code, on another port, with a temp
  DB under `/tmp`, deleted afterwards. The live service only receives
  `tools/list` calls and calls that are refused (and so write nothing).
- **Run #3's charter is regenerated from the new `agents/architect/role.md`.**
  Do **not** reuse run #2's `charter-bootstrap.md`: it says "nine read-only
  tools", "no write tool" and "write it as this exact record", which now
  contradict the real tools.

## What to do

1. **Pre-check VM 103, read-only.** `dfmcp-server`, `df-fortress` and `df-xvfb`
   active; the deployed `server.py` hash matches the pre-merge `main`; the venv
   Python's SQLite version and a working `json_extract` (the Phase A fix relies
   on it). If JSON1 is missing, stop.
2. **Back up, then deploy** `dfmcp/`, `dfqueue/`, `learning/` (whole package),
   `agents/`, `scripts/dfhack/TOOLS.yaml`. Exclude `*.sqlite3*`, `.venv*`,
   `__pycache__`. Verify every deployed file by sha256 against merged `main`.
3. **Unit and env:** `StateDirectory=dfmcp` (see above), append
   `MCP_SERVER_QUEUE_DB`, `daemon-reload`, restart. Journal clean, 0 restarts,
   `df-*` units untouched.
4. **Throwaway loopback instance, real DFHack, temp DB.** Architect proposes a
   valid record (`cycle` equals the real absolute tick from `overview.get`);
   overseer `pending` shows it; `defer` keeps it pending; `accept` removes it;
   a second final ruling is refused. Then stop the instance and delete the temp DB.
5. **Live service, from VM 106 with curl:**
   - `tools/list` per role: architect = its 9 reads + `queue__propose` +
     `queue__pass`; overseer = its reads and writes + `queue__rule` +
     `queue__pending`; consultant unchanged.
   - Refusals, each writing nothing: architect calling `queue__rule`;
     `queue__propose` with a `role` argument; a malformed proposal (check that
     the error lists reasons).
   - Confirm the live DB holds zero records afterwards (via the venv's Python
     `sqlite3` module, not a CLI you'd have to install).
6. **Architect run #3 on VM 106.** Same runner, model
   (`deepseek/deepseek-v4-flash`) and pinned-config shape as run #2; `SOUL.md`
   regenerated from the new `role.md`. Task prompt: run #2's verbatim, **unless**
   it tells the model to write the XML record as prose; then make the minimal
   edit that points at the tool, and record the diff in the README. **At most 3
   agent turns, stop at $0.05 total.**
7. **After the run:** read the live queue (every record, `due_game_tick` and the
   current tick), and the journal's `tools/call` lines for the run's session:
   how many `queue__propose` calls were refused, and why. Refusal-then-fix
   retries are the interesting data, not noise.

## Output

`evals/live/2026-09-15-architect-third-charter/`: `README.md` (procedure,
prompt diff if any, the charter check against `role.md`, cost), `run.json`,
`charter-bootstrap.md`, `pinned-config.json` (MCP URL redacted),
`queue-export/` (`dfqueue.store.export_jsonl` of the live DB), and
`tool-calls.jsonl` (the run's call-log lines). **Before committing, scan every
new file for tokens and addresses with a positive control** (plant a known
string, confirm the scan catches it, remove it).

## Hard lines

- **No fort-mutating tool call from any role.** No `df-*` unit change, no DF
  config or save touched, no reboot, **no apt install on VM 103**.
- Public repo: no address, hostname or token in any tracked file or the report.
- Nothing left listening on VM 106. The throwaway instance on VM 103 stopped
  and its temp DB deleted.
- **If any live check in steps 3-5 fails:** restore the backup, restart,
  confirm the old service answers, then stop and report. Do not run step 6
  against a half-working server.
- Do not edit `Working.md`, `decisions/` or `memory/`. Update this doc's Result
  section and its `handoffs/INDEX.md` row only.

## Touched surfaces

VM 103: `/opt/df/dfmcp-smoke/`, its backup, the `dfmcp-server.service` unit,
`/var/lib/dfmcp/`, the service `.env` (one appended key). VM 106:
`/opt/openclaw/` (run files, removed after). Repo:
`evals/live/2026-09-15-architect-third-charter/` (new), this doc,
`handoffs/INDEX.md`.

## Report

Executor shape, plus: exact reversal steps; the run's outcome against the
charter (proposal via the tool or `pass`, the prediction signal used, any scope
slip); and every refusal the model hit, with how it responded.

## Result

(executor fills in)
