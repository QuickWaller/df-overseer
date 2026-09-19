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

`dfmcp-server` not yet restarted at this point in the write-up -- next step.
