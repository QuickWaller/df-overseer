# Handoff: deploy the water and industry tools to VM 103

**Dispatched** 2026-09-17 by the orchestrating session. **Agent:** `executor`,
Sonnet. **User go-ahead:** "go ahead" (2026-09-17), for this deploy only.
**Peer check-in:** no other session on this repo or home-lab. One sibling
executor may still be mutating the fort (see Sequencing).

## Why

`handoffs/2026-09-17-water-and-industry-tools.md` merged to `main`: zones, tree
felling, work orders, well, and mason/mechanic/carpenter workshops. Until they
are on the VM no agent can use them, and the well chain (the permanent fix for
drinking stagnant pond water) cannot start.

## Read first

`CLAUDE.md` (traps, secrets rule), `docs/TRAPS.md`, and
**`handoffs/2026-09-17-farm-tools-deploy.md` including its Result**: this
repeats that procedure exactly, and its Result records what is already live.

## Sequencing (this deploy is not first in the queue)

`handoffs/2026-09-17-farm-still-first-build.md` is building a farm plot and
still in the live fort and running a supervised unpause. **Do all preparation
first** (steps 1 and 2 below), then **wait** until that stream's Result section
is appended to its handoff doc **and** the fort reads paused, before copying
any file. Poll lightly (a read every minute or two, not a tight loop). If it is
still running after 20 minutes, report and stop rather than deploying over it.
Never pause or unpause the fort yourself.

## Scope

Diff since the last deploy (`git diff --stat` against the deployed state; the
previous deploy's Result lists what is live):

- **Lua, to `/opt/df/game/hack/scripts/`:** `df-overseer-zone.lua`,
  `-trees.lua`, `-orders.lua`, `-well.lua` (all new), and
  `-workshop.lua` (extended). As before, **sha256-compare every deployed
  `df-overseer-*.lua` against `main`** and redeploy any that differ; report any
  that were stale.
- **Blueprints, to the guest's `dfhack-config/blueprints/`, flat:**
  `starter-well-1x1.csv`, `starter-mason-3x3.csv`, `starter-mechanic-3x3.csv`,
  `starter-carpenter-3x3.csv`.
- **Server tree, to `/opt/df/dfmcp-smoke`:** `scripts/dfhack/TOOLS.yaml`,
  `agents/architect/tools.yaml`, `agents/overseer/tools.yaml` (and any other
  file under `dfmcp dfqueue learning agents` that differs by hash). Then
  `sudo systemctl restart dfmcp-server`.

## Procedure

1. **Read-only pre-check:** services active; fort state and tick recorded;
   live per-role `tools/list` captured (tokens by key from the VM's own `.env`,
   `grep -E '^MCP_ROLE_TOKEN_...='`, never printed).
2. **Compute the expected after-state locally** from `main` exactly as the
   server does: `load_registry(native_tools=queue_tools.NATIVE_TOOLS)`,
   `load_roster(reg)`, `build_tool_names(reg)`, each role's read and write keys,
   using `.venv-dfmcp` in the main checkout. Previous live state was
   architect 15 / overseer 23 / consultant 4; state the expected new counts and
   confirm the old sets are subsets (nothing dropped).
3. **Wait for the fort** per Sequencing.
4. **Back up** everything you will overwrite to
   `/opt/df/deploy-backup-2026-09-17b`.
5. **Deploy** with `git -c core.autocrlf=false archive`, sha256 manifests built
   locally, **`sha256sum -c` on the VM**, files owned `df:df`.
6. **Restart `dfmcp-server` only.** Never restart `df-fortress`.
7. **Verify by execution:** live per-role `tools/list` equals expected exactly;
   then run **reads and dry runs only**: `zone find water_source`,
   `trees find`, `well find`, `orders list`, `workshop find mason`, and the
   dry-run path of `zone place`, `trees fell`, `well build`, `orders create`.
   **A known trap applies here:** DFHack caches scripts by name in the running
   process (`reqscript`), so a newly copied file may not be what answers you.
   Prove the live code is the new code, for example by checking a string or
   behaviour only the new version has, and say how you proved it.

## Constraints

- **No fort mutation**: no real zone, fell, build, order, dig, labor write,
  unpause, save or DF restart. Those need their own go-ahead.
- If a hash, tool list or dry run disagrees with expectation, **stop and
  report**; restore from the backup only if the service is unhealthy.
- No hostnames, addresses or tokens in anything you write. Delete `/tmp` files
  and tarballs on both ends.
- Do not edit `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`,
  `research/`, `doctrine/`. **Do not commit**: append your Result to this doc.

## Touched surfaces

VM 103's `hack/scripts/df-overseer-*.lua`, `dfhack-config/blueprints/`,
`/opt/df/dfmcp-smoke`, `/opt/df/deploy-backup-2026-09-17b`; this doc.

## Report back

Files deployed with hashes verified, backup path, per-role tool counts before /
expected / live, how you proved the running code is the new code, each dry
run's result in a line, service health, fort state before and after, how long
you waited for the sibling stream, and anything that surprised you.
