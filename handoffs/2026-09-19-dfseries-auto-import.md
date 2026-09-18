# Handoff: samples flow into the store automatically

Date: 2026-09-19. **Live stream. Owns VM 103** (not the fort: **no unpause is
needed or permitted**). A parallel offline stream is changing `dfseries/`
(`handoffs/2026-09-19-dfseries-resets.md`); **you must not edit anything under
`dfseries/`.**

Read `CLAUDE.md`, then `docs/TIMESERIES.md`, then `dfseries/cli.py` and
`dfseries/store.py`, then `infra/dfmcp-server.service.example` (the existing
systemd precedent), then this.

## The goal

Today the sampler writes JSONL on VM 103 and a human copies it off and imports
it. Make import **automatic, on the VM**, so the store is always current
without anyone touching it.

## The principle that makes this safe

**The JSONL files are the canonical record. The SQLite database is a derived
cache.** The sampler's files are append-only and are never modified by
anything but the sampler, so the database can always be rebuilt from them,
exactly, by re-importing. Consequences:

- If `dfseries`'s schema changes (the parallel stream may change it), the fix
  is to **delete the database and re-import**. Nothing is lost. Make that a
  documented one-command operation.
- **Never** have the import path modify, move, rotate or delete a JSONL file.
- The importer is already idempotent (progress tracking plus a unique
  `(source_file, source_line)` constraint), so running it often is safe.

## Deliverable

1. **`dfseries/` deployed to VM 103** from `main` at the time you deploy, next
   to where the MCP server's code lives, so the server can import it later (a
   following stream builds MCP tools on it). Use
   `git -c core.autocrlf=false archive` and hash-verify, as every deploy has.
2. **A systemd timer on the VM that imports every 60 seconds**, running
   `python -m dfseries.cli import <db> <files>` over the sampler's directory.
   `ExecStart` does not expand globs, so wrap it. Add committed
   `.example` counterparts for the unit files beside
   `infra/dfmcp-server.service.example`, following its conventions. Harden it
   the way that unit is hardened; **it needs read access to the sample
   directory and write access only to the database's directory.**
3. **The database location** chosen deliberately (the MCP server's unit may
   restrict writable paths; read how it does before choosing) and recorded.
4. **A rebuild command**: delete the database and re-import everything,
   documented in the write-up.

## Verification, each check one that could fail

- **Import happens without you.** Record the row count, wait for two timer
  runs, and show the timer's own journal lines. Since the fort is paused, no
  new samples arrive, so **prove freshness a different way**: append nothing,
  but confirm the timer ran and imported 0 new rows (idempotency, live). Then,
  if a real sample can be produced **without unpausing** (the sampler's
  `sample` command can be invoked directly by a bounded call, which writes one
  record at the current tick), do it once and confirm the timer picks it up
  within a minute.
- **The real run is in the store**: the 9-game-day file imports, and
  `unit:193` thirst gives +1 per tick over 10 samples, as it did on the
  workstation.
- **A rebuild reproduces the same row counts** as the incremental import.
- **The timer survives a reboot of the unit**: `systemctl restart` it and
  confirm it resumes, without restarting DF itself.

## Rules

- **Do not unpause the fort, and do not restart DF or DFHack.** This stream
  touches systemd units and files only.
- **Never run an unbounded query against the live DFHack process**
  (`docs/TRAPS.md`, last entry). The one `sample` call above is bounded.
- SSH as `df`, not root, except where a systemd unit genuinely needs root, and
  say where. `DF_VM_IP` carries a CIDR suffix to strip. Read secrets by key,
  never `cat .env`.
- **Never write an IP address, hostname or port into any committed file.** The
  `.example` files use placeholders.
- **Write as you go.** Commit on `main` (you are not worktree-isolated; commit
  only your own files, check `git status` first) after each milestone and
  append to this file's write-up each time.
- **home-lab**: a new systemd service on VM 103 may need recording in
  `../home-lab/inventory/services.yaml`. **You may not edit that repo.** Say in
  the write-up exactly what was added, so the orchestrator can route it.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md` or `docs/TIMESERIES.md`. No em dashes in prose.

## Touched surfaces

VM 103 (deploy, systemd units, database), new `infra/*.example` unit files, and
this handoff doc. **Not** `dfseries/`, `dfmcp/`, `scripts/`, or the fort.

## Done means

The timer runs on its own, the store on the VM holds the real run, a rebuild
reproduces it, the fort is still paused at the same tick, and the write-up
records the database path, the rebuild command, and what home-lab needs to
know.
