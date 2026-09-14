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

**Status: DONE, 2026-09-15.** All of steps 1-7 completed, no hard-stop
condition hit. Worktree was fast-forwarded from `72c7e2d` to `1fb00d8`
(missing this handoff's own dispatch commit and the Phase A merge) before
anything else, per the brief's own instruction, and confirmed a plain
fast-forward (no divergent commits).

### Step 1: pre-check, read-only

`dfmcp-server`, `df-fortress`, `df-xvfb` all active. Deployed `server.py`'s
sha256 did not match any single local commit by raw hash -- diagnosed, not
just reported as a mismatch: the VM's copy carries CRLF line endings (from
an earlier plain `scp` of a Windows-checked-out working-tree file, this
workstation's git has `core.autocrlf=true`), while `git show`/`git archive`
blobs are LF. After normalizing CRLF->LF, the deployed file was
byte-identical to commit `2472cdf` (the last `dfmcp/server.py` change before
Phase A, matching the 2026-09-14 call-log deploy) -- confirmed no
undocumented drift, a real but harmless line-ending inconsistency, not a
content difference. Venv: Python 3.12.3, SQLite 3.45.1, a real
`json_extract` round-trip confirmed working (not just version-checked).

### Step 2: backup and deploy

Backup: `cp -a /opt/df/dfmcp-smoke /opt/df/dfmcp-smoke-backup-2026-09-15`
(kept, not yet deleted -- see "Reversal" below for using it).

**Deploy method, and why it differs from the VM's existing convention**: to
get a true byte-for-byte match to merged `main` (this stream's own explicit
requirement), the deploy used `git archive HEAD dfmcp dfqueue learning
agents scripts/dfhack/TOOLS.yaml` (canonical LF blob content, no
working-tree checkout filters) piped into a local tarball, scp'd to VM 103,
and extracted over the existing tree (not deleting first -- `.venv`, `.env`,
`server.log` and the smoke-test's own scratch scripts were left alone,
nothing in the archive's path list overlaps them). 65 files.
`sha256sum -c` on the VM against a manifest built from the same archive
**passed for all 65 files** -- verified on the VM itself, not inferred from
a local hash comparison.

### Step 3: unit and env

Installed unit (read first, per the brief): a plain `Type=simple` unit,
`ProtectSystem=strict`, `ReadWritePaths=/opt/df/dfmcp-smoke` only, no
`StateDirectory=`. Nothing about it made the `StateDirectory=dfmcp` plan
wrong, so no stop was needed. New unit adds `StateDirectory=dfmcp` (creates
`/var/lib/dfmcp`, owned `df:df`, implicitly writable under
`ProtectSystem=strict` per `systemd.exec(5)`, no hand-added
`ReadWritePaths` entry needed) with a one-line comment explaining why.
`.env`: confirmed `MCP_SERVER_QUEUE_DB` absent first
(`grep -c` -> 0), then appended `MCP_SERVER_QUEUE_DB=/var/lib/dfmcp/
Uniboslan.sqlite3` (never printed). `daemon-reload`, `restart`. After:
`NRestarts=0`, `ActiveState=active`, `SubState=running`,
`/var/lib/dfmcp` created `df:df`, journal shows a clean startup with no
errors, `df-fortress`/`df-xvfb` untouched (both still `active`).

### Step 4: throwaway loopback instance

**A real gap found and fixed before this step could work at all**:
`dfmcp.auth.load_role_tokens` always reads tokens from `REPO_ROOT/.env`
(`Path(__file__).resolve().parent.parent / ".env"`), **never from process
environment variables**, regardless of what a caller's shell exports. A
first attempt (same code tree, different port, throwaway env vars set
before `python -m dfmcp.server`) silently authenticated against the
**live** tokens instead (`REPO_ROOT` is fixed by the package's own file
location, not affected by which env vars are set), confirmed by curl
getting a real 401 against a token that should have worked. Fixed by
standing up a **second, fully isolated copy** of the same sha256-verified
deploy tarball under `/opt/df/dfmcp-throwaway/` (its own `REPO_ROOT`, its
own `.env`, its own three throwaway tokens, `MCP_SERVER_QUEUE_DB` under
`/tmp`), reusing the existing venv by absolute path. This is the real
mechanism a "throwaway instance" needs on this codebase, not just a
different port -- worth remembering for any future throwaway run.

Verified end to end via a real `mcp` SDK client (`streamable_http_client`,
real network calls, not the in-process ASGI transport `dfmcp/tests` uses):
architect `overview.get` (baseline tick), architect `queue.propose` (a
valid record: `type=corridor`, real signal/op/value/check_after_ticks,
valid cost/preconditions/public_rationale) -- **cycle stamped as 12274877,
equal to `game_tick_from_overview` computed independently from the same
`overview.get` call**, confirming the stamped tick is real and not a
placeholder; overseer `queue.pending` showed it; overseer `queue.rule
defer` kept it pending (the Phase A review's fix, live-verified for the
first time); overseer `queue.rule accept` dropped it from pending; a second
final ruling (`reject`, after the `accept`) was refused with the exact
message `dfqueue.schema` documents. All 6 checks passed on the first
attempt. Instance stopped, `/opt/df/dfmcp-throwaway/` and
`/tmp/dfmcp-throwaway/` both deleted, verified gone.

### Step 5: live-service checks from VM 106

VM 106 has no `mcp` SDK/venv, but does have ambient `python3`+`requests`
and `jq` already -- no install needed, none was done. A small script
(`mcp_probe.py`, kept only in this session's scratchpad, never committed)
did the raw streamable-HTTP JSON-RPC exchange (`initialize` ->
`notifications/initialized` -> `tools/list`/`tools/call`, session id from
the `Mcp-Session-Id` response header).

**Token relay**: the three live role tokens were `scp -3`'d directly from
VM 103 to VM 106 (never landing on this workstation's disk as a file),
staged briefly in `/tmp/dfmcp-relay103/` on VM 103 and deleted immediately
after the relay, held in `/tmp/dfmcp-relay106/` on VM 106 only for the
duration of the checks, then deleted. This is the same `scp -3` pattern
CLAUDE.md's 2026-09-14 row already covers for exactly this scenario
(reversible, own hosts, authorised task) -- disclosed here, not routed
through anything else.

- **Per-role `tools/list`**: architect 11 (the 9 reads + `queue__propose` +
  `queue__pass`, zero mutators); overseer 16 (its reads/writes +
  `queue__rule` + `queue__pending`, no `queue__propose`/`queue__pass`);
  consultant 2, unchanged. Exactly as the brief specified.
- **Refusal 1**: architect calling `queue__rule` -> `isError: true`,
  `"'queue.rule' is not on architect's allowlist. Advisors do not act;
  propose it instead."` -- a `Roster.check` denial, before `dfqueue` is ever
  touched.
- **Refusal 2**: architect calling `queue__propose` with a `role` argument
  (plus an otherwise-valid record) -> `isError: true`,
  `"queue.propose: unexpected argument(s) ['role']; ..."` -- refused by
  `_reject_unknown_arguments` before `store.append` is ever called.
- **Refusal 3**: architect calling `queue__propose` with `{}` -> `isError:
  true`, all 8 missing required fields listed by name
  (`record.summary`/`.rationale`/`.public_rationale`/`.type`/`.cost`/
  `.suggested_priority`/`.preconditions`/`.prediction`).
- **Live DB after all three**: confirmed **0 records** via the deployed
  venv's own `sqlite3` module (`select count(*) from records`), not a CLI --
  the DB file itself existed (schema created on connect) but held no rows,
  consistent with `dfqueue.store.append`'s own validate-before-insert order.

Relay artifacts (`/tmp/dfmcp-relay106/`) deleted after; confirmed gone.

### Step 6: architect run #3

See `evals/live/2026-09-15-architect-third-charter/README.md` for the full
write-up; summary here per the Report section's ask.

**Charter**: a new `charter-bootstrap.md` was built from the *current*
`agents/architect/role.md` verbatim (plus a "Your tools" section naming the
real, current 11-tool list) -- run #2's own saved `charter-bootstrap.md` was
**not reused**, exactly per the brief's warning: it said "nine read-only
tools", "no write tool" and "write it as this exact record" as a literal
instruction, all three now false. **Task prompt: verbatim from run #2,
unedited** -- it says "make exactly one proposal in the required format"
without specifying the mechanism, so no edit was needed (prompt diff: none).

**One real config-schema break found and fixed, $0**: `pinned-config.json`
(reused from run #2's shape) carries a `_note` documentation key that the
live config schema now rejects (`Unrecognized key: "_note"`) --
attempt 1 failed locally on this, before any network call, $0 cost.
Stripped the key from the VM 106 working copy (the repo copy here keeps
`_note` for readability, with the caveat written into this run's README) and
retried.

**Attempt 2 succeeded immediately.** `queue.propose` called **once**, first
try, **zero refusals** -- the regression run #2 exists to describe (dropping
the record and writing markdown prose instead) did not recur. Every
required field present and correctly typed: `type="workshop_siting"`
(in-vocabulary), a real falsifiable prediction
(`fort.landmarks.count gt 4`, `check_after_ticks=1200`), a named cost (600
`dwarf_ticks`), 3 well-formed preconditions, a `public_rationale` distinct
from `rationale`. **2 of 2 real tool failures this run were unrelated to the
queue tools**: `diggable.find`/`openarea.find` both once rejected a call
that supplied `radius_tiles` without the earlier positional `level`
argument (a pre-existing DFHack CLI positional-slot quirk), and the model
self-corrected on its very next call to each, successfully. Refusal-then-fix
retries, exactly the interesting data the brief asked to capture -- just not
on the queue tools this run, since the propose call itself needed none.

**Independently verified against the live queue DB, not just the model's
own text**: `proposal-0001` exists in `/var/lib/dfmcp/Uniboslan.sqlite3`,
`cycle=12274877` matching the fort's real absolute tick at write time, and a
matching `predictions` row (`due_game_tick=12276077`, `status=pending`).
Both exported via `dfqueue.store.export_jsonl` into this run's
`queue-export/`.

**Turns and cost**: 2 of the 3 allowed `agent exec` attempts used (1 free
local failure, 1 real success), real cost **$0.0033133688**, well under the
$0.05 cap. 1 attempt left unspent.

**Nothing left listening on VM 106**: `docker ps -a` empty, `ss -tlnp`
identical to this stream's own pre-run baseline (5 listeners: `:22` sshd
dual-stack, two DNS-stub loopback listeners, one other loopback port --
no new port). `/home/df/architect-run-3/` and
`/opt/openclaw/config/architect-workspace/SOUL.md` deleted after, both
confirmed empty. One snag along the way: `architect-workspace/` was
`root:root` from earlier, unrelated work, which refused a plain `scp` of
`SOUL.md` with `Permission denied` -- fixed with `sudo chown df:df`
(passwordless sudo already confirmed available), a one-line, reversible,
own-host fix, not a security-boundary workaround.

### Step 7: after the run

Queue export and journal lines captured above and in the eval `README.md`;
no `queue__propose` refusals occurred during the run itself (see step 6),
so there is no refusal-then-fix data *from the queue tools* this run --
noted as a finding, not glossed over.

### Positive-control evidence (secret/address scan)

Two regexes (`([0-9]{1,3}\.){3}[0-9]{1,3}` for IPv4, `(sk-[A-Za-z0-9]{20,}
|Bearer [A-Za-z0-9_.\-]{20,})` for token-shaped strings), proven against a
synthetic line (`ip=192.0.2.50` TEST-NET-1, a fake `sk-...` key, a fake
`Bearer ...` token) **before** trusting them: both regexes matched, 1 hit
each. Run against every new file in `evals/live/2026-09-15-architect-third-
charter/` (`run.json`, `run-stderr.txt`, `charter-bootstrap.md`,
`pinned-config.json`, `README.md`, `tool-calls.jsonl`,
`queue-export/*.jsonl`): **zero real matches**. `pinned-config.json`'s only
address-shaped text is the literal `<df-vm-lan-ip>` placeholder (correctly
not matched by the IP regex); `README.md`'s one match is the documented
positive-control example itself (`192.0.2.50`, TEST-NET-1, the same
convention run #2's README used).

### Exact reversal steps (not run -- all checks passed)

If steps 3-5 had failed, or if this deploy needs rolling back later:

```
# On VM 103, as df:
sudo systemctl stop dfmcp-server
sudo rm -rf /opt/df/dfmcp-smoke
sudo mv /opt/df/dfmcp-smoke-backup-2026-09-15 /opt/df/dfmcp-smoke
```
Then restore the pre-Phase-B unit (the installed unit read in step 1,
reproduced here since it was not separately file-backed before being
overwritten):
```
[Unit]
Description=df-overseer MCP server (dfmcp.server)
After=network-online.target df-fortress.service
Wants=network-online.target

[Service]
Type=simple
User=df
Group=df
WorkingDirectory=/opt/df/dfmcp-smoke
EnvironmentFile=/opt/df/dfmcp-smoke/.env
ExecStart=/opt/df/dfmcp-smoke/.venv/bin/python -m dfmcp.server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/df/dfmcp-smoke

[Install]
WantedBy=multi-user.target
```
```
sudo systemctl daemon-reload
sudo systemctl restart dfmcp-server
systemctl is-active dfmcp-server df-fortress df-xvfb   # confirm old service answers
```
The restored backup's own `.env` has no `MCP_SERVER_QUEUE_DB` key, so no
separate removal step is needed. `/var/lib/dfmcp/` would be left in place
(harmless, unreferenced by the restored unit) unless explicitly removed too.

### Commits on this branch

All on `worktree-agent-ad1d420a2ceed0f46`, after the `git merge --ff-only
main` fast-forward (which brought in `1fb00d8`, not a new commit of this
stream's own):
- `evals/live/2026-09-15-architect-third-charter/` (new: `README.md`,
  `run.json`, `run-stderr.txt`, `charter-bootstrap.md`, `pinned-config.json`,
  `tool-calls.jsonl`, `queue-export/records.jsonl`,
  `queue-export/predictions.jsonl`)
- this handoff doc's Result section
- `handoffs/INDEX.md`'s Phase B row

(Exact commit SHAs: see `git log` on this branch after this Result section
is committed -- this paragraph is written before that commit.)

### Findings worth carrying forward

1. **Token isolation for a throwaway instance needs a separate code
   directory, not just a separate port/env** --
   `dfmcp.auth.load_role_tokens`'s `REPO_ROOT/.env` default is fixed by the
   package's own file location. Worth a comment in `dfmcp/auth.py` itself
   pointing future throwaway runs at this.
2. **The VM's deployed code had carried CRLF line endings since an earlier
   plain-`scp` deploy** (this workstation's `core.autocrlf=true`). Harmless
   (Python and SQLite don't care), but it broke a naive sha256 comparison
   and would break one again for any future deploy that doesn't use
   `git archive`. Worth standardizing the deploy method on `git archive`
   going forward, not just for this one stream.
3. **`pinned-config.json`'s `_note` key is rejected by the live openclaw
   config schema**, even though runs #1/#2's saved copies both carry it.
   Documented in this run's own README so a future run does not rediscover
   it the same way.
4. **`/opt/openclaw/config/architect-workspace/` was `root:root`** before
   this run, for a reason not traced (not something this stream did).
   Fixed; if it recurs, it is worth tracing which prior process leaves it
   that way.
