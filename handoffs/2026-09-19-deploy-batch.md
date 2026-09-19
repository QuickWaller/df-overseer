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
