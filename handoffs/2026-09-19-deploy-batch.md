# Handoff: deploy the batch of merged-but-undeployed tools, and verify each live

Date: 2026-09-19. **Live stream on VM 103. The fort stays paused; no unpause
is needed or permitted.**

Read `CLAUDE.md` (the deploy trap in its status block), `docs/TRAPS.md`, then
the write-ups of `handoffs/2026-09-19-deploy-and-live-verify.md` (the method
that worked last time), `2026-09-19-get-doctrine-tool.md`,
`2026-09-19-series-mcp-tools.md`, `2026-09-19-in-building-deduction.md` and
`2026-09-19-workshop-add-job.md`, then this.

## What is merged and not live

1. **`df-overseer-stocks.lua`** with six deductions (`in_building`,
   `construction` added). The deployed copy still counts built-in boulders
   as available.
2. **`dfmcp/`**: `doctrine_tools.py` (`doctrine.get`), `series_tools.py` (six
   `series.*` tools), the generalised native-tool routing in `server.py`, and
   the registry changes for `workjob.*`.
3. **`agents/*/tools.yaml`** and **`scripts/dfhack/TOOLS.yaml`** grants for all
   of the above.
4. **`doctrine/seed.yaml`**, which `doctrine.get` reads.

`df-overseer-workjob.lua` itself is already deployed (hash-verified earlier).

## Method

`git -c core.autocrlf=false archive` from `main`, a sha256 manifest, verify on
arrival and again at the installed path, back up anything overwritten, then
restart **`dfmcp-server` only**. Never restart DF or DFHack. Check what is
actually on the VM before deploying rather than assuming.

## Verification, each one that could fail

- **`stocks.availability BOULDER`** now reports the built-in boulders under
  `in_building` and **not** as available, with `flag_read_errors` empty. Right
  now the fort has 7 boulders, 3 built into workshops, so expect about 4
  available; say what you actually see.
- **Real per-role tool lists** over a real MCP client, as the last deploy did.
  Record the new counts (they were 24/37/4) and reconcile `CLAUDE.md` and
  `ROADMAP.md`'s mentions in your write-up for the orchestrator.
- **`doctrine.get`** as the consultant: the topic index, one `refuted` entry
  by id showing its warning, and an unknown topic returning an error.
- **`series.*`** as the overseer against the live database: `series.timelines`,
  and `series.resets` for one citizen's `thirst_timer`. **Watch for the WAL
  problem the MCP stream flagged**: the database opens in WAL mode, which needs
  write access to its directory even for reads, and `dfmcp-server`'s unit may
  be hardened against `/var/lib/dfseries`. If it fails, report the exact error
  and the minimal unit change (for example a `ReadWritePaths=` entry, or a
  read-only URI open), rather than loosening hardening broadly.
- **The architect is refused** `doctrine.get`, `series.*` and
  `workjob.queue`, with the deny reasons from its `tools.yaml`.

## Rules

- **Do not unpause the fort, do not restart DF or DFHack.**
- **Never run an unbounded query against the live DFHack process.**
- If a permission classifier refuses anything (a unit change or restart may
  be), **stop and report it**; do not route around it.
- SSH as `df`, except where a system unit genuinely needs root, and say where.
  `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key, never
  `cat .env`. **Never write an IP address, hostname or port into any committed
  file**; the leak-guard test fails the suite.
- **Write as you go**: commit on `main` (own files only, `git status` first)
  and append to this file's write-up at each milestone. Do **not** write
  `Working.md`, `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`. No
  em dashes in prose.

## Touched surfaces

VM 103 (deployed files, `dfmcp-server` restart, a minimal unit change only if
the WAL check demands it), and this handoff doc.

## Done means

Everything listed is live and hash-verified, every check above passed or its
failure is reported with the exact error, the real tool counts are recorded,
and the fort is still paused at the same tick.

## Write-up (executor, in progress)

### What was on VM 103 before this stream touched anything

Checked by grep/ls, not assumed:

- `/opt/df/game/hack/scripts/df-overseer-stocks.lua` (DF's own script dir,
  separate from the `dfmcp-smoke` checkout), dated 2026-09-18 20:57, **0**
  occurrences of `in_building`/`construction` -- the old four-deduction
  version, matching the header's claim exactly.
- `/opt/df/game/hack/scripts/df-overseer-workjob.lua`, dated 2026-09-19
  04:31, present -- **already deployed**, confirming the header's claim; not
  touched by this stream.
- `/opt/df/dfmcp-smoke/dfmcp/` had no `doctrine_tools.py` and no
  `series_tools.py` at all, and `server.py` was dated 2026-09-16 10:18 (pre-
  dating both features).
- `/opt/df/dfmcp-smoke/doctrine/` **did not exist**.
- `/opt/df/dfmcp-smoke/scripts/dfhack/TOOLS.yaml` (the copy the MCP server's
  registry actually reads) had **0** occurrences of `workjob`, `doctrine.get`
  or `series.`.
- `/opt/df/dfmcp-smoke/agents/{architect,overseer,consultant}/tools.yaml` had
  **0** occurrences of `doctrine.get` or `series.` grants/denials.
- `dfmcp-server.service`'s live unit (`/etc/systemd/system/`, read via
  `sudo -n cat`, no write) confirmed the WAL risk in advance:
  `ProtectSystem=strict`, `ProtectHome=true`,
  `ReadWritePaths=/opt/df/dfmcp-smoke` only, plus `StateDirectory=dfmcp`
  (giving `/var/lib/dfmcp`). Nothing grants `/var/lib/dfseries`.
- **Flagged, not fixed, out of this stream's touched surfaces**: the VM's
  deployed `dfseries/` package (`/opt/df/dfmcp-smoke/dfseries/`, last
  touched 2026-09-19 03:37) is genuinely stale relative to local `main`.
  Direct byte comparison of `dfseries/metrics.py` (after stripping this
  workstation's CRLF) shows the VM copy is **missing** the
  `feed-the-fort` stream's hunger `reset_to_zero_verified=True` update, and
  `dfseries/aggregate.py` differs by more than line endings too. This
  stream's handoff does not list `dfseries/` as a deploy target (only
  `series-mcp-tools`'s own handoff touches it, and that one's touched
  surfaces explicitly exclude `dfseries/`), so it was left alone rather than
  silently redeployed as a drive-by fix. Whoever owns `dfseries/` next should
  check whether this drift matters for anything beyond hunger's exactness
  flag.

### Deployed, hash-verified twice

`git -c core.autocrlf=false archive HEAD` of exactly 12 files: the four
`agents/*/tools.yaml`, `dfmcp/{doctrine_tools,series_tools,server}.py`,
`doctrine/{__init__,validate}.py` + `seed.yaml`, and
`scripts/dfhack/{TOOLS.yaml,df-overseer-stocks.lua}`. A `sha256sum` manifest
was built from the extracted tarball locally, the tar copied to the VM by
`scp`, `sha256sum -c` run immediately after extracting there (all 12 `OK`),
existing files backed up to
`/opt/df/deploy-backup-2026-09-19-batch/` (stocks.lua, TOOLS.yaml, server.py,
the four tools.yaml -- `doctrine/` had nothing to back up, being new), then
copied into place (`chown df:df`), then **hashed again at the final
installed path** against the same manifest: all 12 `OK`. `file` confirmed no
CRLF crept in (`ASCII text` / `UTF-8 text`, no "with CRLF line terminators").
SSH as `df` throughout (root was never used); `DF_VM_IP`'s CIDR suffix
stripped before connecting.

### `dfmcp-server` restarted

Baseline fort state read first, bounded `dfhack-run lua` call only
(`dfhack.world.ReadPauseState()`, `df.global.cur_year`,
`df.global.cur_year_tick`): **paused, year 31, tick 103055** -- matching the
tick the stone-blocks-well stream's own write-up left the fort at. `sudo -n
systemctl restart dfmcp-server` (the one restart this handoff authorises,
never `df-fortress`) came back up clean in about a second with no crash
loop, confirmed by `systemctl status` showing `Active: active (running)`
and a fresh `Uvicorn running on http://<bind-host>:<port>` log line. This
alone proves the registry/roster loaded without a Python exception at
startup (both are loaded once, at process start, per `server.py`'s own
docstring) -- a bad `doctrine.get`/`series.*` wiring or a bad `tools.yaml`
grant referencing a nonexistent id would have made this restart fail
outright, and it didn't.

### Real per-role tool lists, over a real MCP client

A throwaway script (scratchpad only, not committed), built the same way the
2026-09-19 deploy-and-live-verify stream did: `mcp==2.2.0`'s real
`ClientSession` + `streamable_http_client`, run from
`/opt/df/dfmcp-smoke/.venv` against the actual running server over real
network HTTP (not an in-process ASGI transport), authenticated per role with
that role's own bearer token read **by key** from `/opt/df/dfmcp-smoke/.env`
(`MCP_ROLE_TOKEN_ARCHITECT`/`_OVERSEER`/`_CONSULTANT`), never the whole
file. `initialize()` then `list_tools()` per role -- no DFHack round trip in
`tools/list` at all, so this alone touched nothing on the fort.

- **architect: 25** (was 24). The one addition is `workjob__list` (read-only
  discovery of the job vocabulary); `doctrine__get` and every `series__*` id
  are **absent from the list entirely**, not merely refused -- the deny
  works at the listing layer too, not just at call time.
- **overseer: 45** (was 37). Eight additions: `workjob__list`,
  `workjob__queue`, and all six `series__*` ids. `doctrine__get` is absent
  from this role's list too, matching its withheld-by-design status.
- **consultant: 11** (was 4). Seven additions: `doctrine__get` and all six
  `series__*` ids.

`CLAUDE.md`'s and `ROADMAP.md`'s tool-count mentions (23/36/4, then 24/37/4)
are now stale; reconciling them is for the orchestrator, per this stream's
own touched-surfaces limit (VM 103 and this doc only).

### `stocks.availability BOULDER`, live

```
total_units: 7, in_building_units: 3, available_units: 4,
construction_units: 0, forbid_units: 0, owned_units: 0, trader_units: 0,
unnetted_units: 0, rotten_units: 0, unreachable_units: 0,
flag_read_errors: [], owned_ref_check.verified_offline: true
```

Matches the handoff's own prediction exactly: 7 total, 3 in buildings, 4
genuinely available, no read errors. What would have failed this: any
nonzero `flag_read_errors`, `in_building_units` staying 0 (the old bug this
whole stream traces back to), or `available_units` still reading 7. Also
caught and fixed a real usability finding, not a bug in the tool itself: the
MCP argument name is lowercase `type`, not the `TYPE` the TOOLS.yaml command
signature (`"availability TYPE"`) suggests -- the first call with `TYPE`
came back a clean, explicit `unknown argument(s) ['TYPE']; this tool accepts
['type']`, exactly the "refuse, never guess" behaviour this project
requires, not a silent failure.

### `doctrine.get`, as the consultant

- **Topic index** (`doctrine.get()`, no arguments): all nine closed topics
  present with `count`/`prior`/`verified`/`refuted` broken out, e.g.
  `water count="8" prior="6" verified="1" refuted="1"`. Matches a direct
  count of the deployed `seed.yaml`.
- **One refuted entry by id** (`id="water-source-zone-for-ponds"`): returned
  with `status="refuted"` and the exact
  `<warning>REFUTED: kept only so this mistake is not repeated. Do NOT treat
  as current guidance.</warning>` line, full `note` and `sources` intact,
  unflattened.
- **Unknown topic** (`topic="nonsense-topic"`): refused with `isError=true`
  and an explicit message naming the valid nine-topic list, never an empty
  result.

### `series.*`, as the overseer against the live database -- **blocked by the flagged WAL risk, confirmed exactly as predicted**

`series.timelines()` and `series.resets(subject="unit:192",
metric="thirst_timer")` (a real citizen: confirmed first, by a read-only
`sqlite3` URI open of `/var/lib/dfseries/uniboslan.series.sqlite3` with
`mode=ro`, that `unit:192` has 199 live `thirst_timer` rows -- not a guess)
both failed identically:

```
mcp.shared.exceptions.MCPError: unable to open database file
```

Root cause, confirmed rather than assumed: `dfseries.store.connect` issues
`PRAGMA journal_mode=WAL`, which needs to create/rewrite `-wal`/`-shm`
sibling files in the database's own directory even for what the caller
experiences as a read. `/var/lib/dfseries/` is owned `df:df` with mode
`755` -- **plain Unix permissions would allow the write**, since the service
runs as `User=df Group=df` and df owns the directory. The actual block is
`dfmcp-server.service`'s own sandboxing: `ProtectSystem=strict` plus
`ReadWritePaths=/opt/df/dfmcp-smoke` and `StateDirectory=dfmcp` (giving
`/var/lib/dfmcp`) only -- `/var/lib/dfseries` is covered by neither, so
`ProtectSystem=strict`'s blanket read-only mount applies to it. Read
confirmed from the live unit (`/etc/systemd/system/dfmcp-server.service`,
via `sudo -n cat`, no write) before ever attempting the call, so this is a
predicted-then-confirmed result, not a surprise.

**Not fixed by this stream.** A unit-file change plus a restart is a
live-production-state change to VM 103 (the same VM the fort runs on, per
`docs/AGENT-ARCHITECTURE.md` and this repo's own "check in again before
modifying a VM or any live-prod state" rule), and this handoff itself asks
for the minimal fix to be *reported*, not applied on the stream's own
judgment. **STOP-and-report, per this executor's own hard rules on gated
live-infra changes.**

The minimal fix, exactly as the handoff anticipated, one of:

1. **Add one `ReadWritePaths=` entry.** In
   `/etc/systemd/system/dfmcp-server.service`'s `[Service]` block, add a
   second `ReadWritePaths=/var/lib/dfseries` line (or extend the existing
   one to `ReadWritePaths=/opt/df/dfmcp-smoke /var/lib/dfseries`), then:
   ```
   sudo systemctl daemon-reload
   sudo systemctl restart dfmcp-server
   ```
   This grants exactly the one additional directory the WAL open needs and
   nothing else; `ProtectSystem=strict`, `ProtectHome=true` and
   `NoNewPrivileges=true` are all otherwise untouched. Reversible by
   removing the line and repeating the two commands.
2. **Or, a code-side fix instead of loosening the unit**: open the series
   database with a read-only SQLite URI (`file:...?mode=ro`, skipping the
   `PRAGMA journal_mode=WAL` call `dfseries.store.connect` currently always
   issues) so no write is ever attempted for a read-only tool call. This is
   a `dfseries/store.py` change, outside this stream's touched surfaces
   (this handoff and `series-mcp-tools`'s own both leave `dfseries/`
   untouched), so it is named as the alternative rather than attempted.

Option 1 is the one this stream recommends: it needs no code change, is a
single reversible line, and matches exactly what the handoff asked to be
reported rather than done. **Neither has been applied.** `series.*` remains
undeployed-in-effect (the code is live and correctly wired -- the tool
appears in the right role lists and is refused correctly for the architect
-- but no successful live database read has been demonstrated) until the
user approves one of the two and it is carried out and re-verified.

### The architect, refused

Live, not inferred from `tools.yaml` alone:

- `doctrine.get()` -> `isError=true`, message is the exact `tools.yaml` deny
  reason verbatim ("Withheld handoffs/2026-09-19-get-doctrine-tool.md, not
  for lack of use -- ... Revisit when that field exists.").
- `series.timelines()` -> `isError=true`, exact deny reason verbatim
  ("Withheld handoffs/2026-09-19-series-mcp-tools.md. ... Revisit if a
  proposal type ever needs to cite a measured trend directly...").
- `workjob.queue(...)` -> `isError=true`, `"Advisors do not act. Propose
  it."` -- the same wording every other Overseer-only write already gets.

None of the three even appear in the architect's `tools/list` (see tool
counts above) -- the deny holds at both layers.

### Fort state, start to finish

Read once before touching anything and once at the very end, both bounded
`dfhack-run lua` calls reading only pause state and the two tick fields:
**paused, year 31, tick 103055 -- unchanged, both times.** No unpause was
needed or run. Every DFHack-side check in this stream was either a
`tools/list` call (no DFHack round trip at all) or one bounded read; no
full-map sweep, no unbounded query.

### What was NOT touched, and why

- **`dfseries/` itself.** Direct comparison (this workstation's CRLF
  stripped first) showed the VM's deployed `dfseries/metrics.py` and
  `aggregate.py` are stale relative to local `main` -- missing at least the
  `feed-the-fort` stream's hunger `reset_to_zero_verified=True` update.
  Flagged above; not this stream's touched surface to fix.
- **`infra/local.example.env`.** Neither `MCP_SERVER_DOCTRINE_PATH` nor
  `MCP_SERVER_SERIES_DB` needed setting on VM 103: both default sensibly to
  in-tree paths (`doctrine_tools.DEFAULT_DOCTRINE_PATH` resolves to
  `/opt/df/dfmcp-smoke/doctrine/seed.yaml`, exactly where this stream
  deployed it; `series_tools.DEFAULT_SERIES_DB_PATH` is the absolute
  `/var/lib/dfseries/uniboslan.series.sqlite3` already in place). Confirmed
  by grep: `/opt/df/dfmcp-smoke/.env` sets neither variable, and the server
  still found both files correctly.
- **The systemd unit.** See the WAL section above -- diagnosed and a minimal
  fix proposed, deliberately not applied.

### Status: mostly done, one item handed back

Deployed and hash-verified: all 12 files, twice. Live-verified and passing:
`stocks.availability` (six-deduction fix confirmed with the exact predicted
numbers), the real tool counts (25/45/11), `doctrine.get` (index, refuted
entry, unknown-topic refusal), and the architect's three-way refusal.
**Blocked, reported rather than routed around**: `series.*` against the
live database, because of the systemd hardening gap this handoff correctly
anticipated. Fort confirmed paused at year 31 tick 103055, unchanged,
throughout.

**Handback for the user**: approve one of the two fixes above (recommended:
add `ReadWritePaths=/var/lib/dfseries` to
`/etc/systemd/system/dfmcp-server.service`, then `sudo systemctl
daemon-reload && sudo systemctl restart dfmcp-server`), after which
`series.timelines`/`series.resets(unit:192, thirst_timer)` should be
re-run to confirm the fix actually closes the gap rather than assuming it
will.
