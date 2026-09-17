# Handoff: deploy the farm and stair fixes, then prove their real writes live

**Dispatched:** 2026-09-17, by the orchestrating session. **Executor:** Sonnet, worktree-isolated.
**User go-ahead:** given 2026-09-17 ("push and then have a sonnet do the tests") for the deploy, the real writes below, and one supervised unpause. Nothing beyond that.
**Peer check-in:** `ListAgents` shows no other session on this machine.

## Why

Two fixes are merged and pushed (`main` at `52deabe`) but not deployed, and only their dry-run paths have been verified (`handoffs/2026-09-17-farm-tool-fixes.md` and `handoffs/2026-09-17-dig-down-to-stone.md`; each has a Result section with its own test plan):
- `farm.list`, and `farm.set-crop` taking a plot ID, with a construction gate and read-back.
- `diggable.find-stair` / `diggable.dig-stair`: a stair pair from the z168 farm room down to z167 stone.

Reaching stone unblocks blocks, mechanisms and the well.

## Read first

- **`handoffs/2026-09-17-water-industry-tools-deploy.md`, the proven deploy procedure.** Follow it:
  - `git -c core.autocrlf=false archive`, sha256 manifests built locally, `sha256sum -c` on the VM, files owned `df:df`.
  - **Restart `dfmcp-server` only; never `df-fortress`.**
  - Prove the running code is the new code by behaviour only the new version has. DFHack caches scripts by name.
- **`handoffs/2026-09-17-water-source-zone-test.md`, the proven supervised-unpause method.**
  - A script on the VM run with `nohup setsid`.
  - A `trap` that re-pauses on any exit.
  - FPS 10, a hard ceiling, and stop conditions, with the fort verified paused afterwards.
- **`docs/TRAPS.md`, especially the 2026-09-17 entries.**

## Steps

1. **Pre-state, read-only.** Confirm the fort is paused, and record the tick (expect 227008), `enabler.fps` (expect 10) and the citizen count (expect 15). Record `dfmcp-server`'s state.
2. **Deploy** `scripts/dfhack/df-overseer-farm.lua`, `scripts/dfhack/df-overseer-diggable.lua`, `scripts/dfhack/TOOLS.yaml`, `agents/architect/tools.yaml` and `agents/overseer/tools.yaml`, plus anything else the deploy procedure says the server loads, to where the previous deploy put them. Verify the hashes, restart `dfmcp-server`, and confirm it is active.
3. **Prove the new code and registry are live, through the real MCP server with the real role tokens.** Read tokens by key only; never print them.
   - Per-role `tools/list` shows `farm.list` for both roles, `diggable.find-stair` for the Architect and `diggable.dig-stair` for the Overseer, and **does not** show `diggable.find-stair` for the Overseer.
   - The expected totals are 21 for the Architect and 34 for the Overseer.
   - `farm.list` returns plot id 4, and `farm.set-crop` uses the `ID` argument. Neither exists in the old code.
4. **Real crop write (Overseer role, over MCP).**
   - Use `farm.find` or the tool's own validation to find a second valid crop for plot 4. If plump helmet is the only valid crop, write plump helmet to one season and say so; a same-value write proves less.
   - Set one season to that crop with `DRY_RUN=false`, confirm `write_ok: true` and the read-back, then restore plump helmet and confirm again.
   - Plot 4 must end with plump helmet in all four seasons, verified with `farm.list`.
5. **Safety check before digging** (an operator check, not agent-facing).
   - Run `diggable.find-stair` (Architect role) and take its rank-1 candidate. Run `diggable.dig-stair` as a dry run (Overseer role) to see exactly what it would designate.
   - Then, **read-only on the VM**, check the z167 target tile and its 8 neighbours for the aquifer flag (`designation.water_table`) and for any liquid.
   - **If there's an aquifer or liquid, stop here, designate nothing, and report.**
6. **Real stair designation.** Call `diggable.dig-stair` with `DRY_RUN=false` (Overseer role, over MCP). Confirm both halves designated (each half's ok field and `quickfort_stats`). Read both tiles' designation back.
7. **One supervised unpause**, using the proven method.
   - **Limits:** FPS 10 and a **7.5-minute ceiling**.
   - **Stop early for success** when both tiles are dug: STAIR_DOWN (or UP_DOWN) at z168, and STAIR_UP at z167.
   - **Stop immediately if:** citizens drop below 15, any death, any liquid on either stair tile or its neighbours at z167, or a dig job is cancelled.
   - **Record:** ticks, wall time, why it stopped, and whether a miner took the job.
   - **Planting may start on plot 4 during the window.** That's fine; note it.
8. **After, with the fort paused (verify):**
   - Run `diggable.find` at z167 near the farm room, the first time it could return anything there.
   - Run `farm.list` again.
   - Record the end tick, citizen count and focus.

## Constraints

- **Allowed:** exactly the deploy, the two real crop writes (set and restore), one stair designation, and one supervised unpause.
- **Not allowed:**
  - no other builds or designations
  - no second unpause
  - no save and no DF restart
  - no work orders or labor changes
- **If anything refuses you** (the harness, a classifier or a tool), stop and report. Don't route around a refusal of a write or the unpause.
- **Leave the fort paused** at the end, whatever happens, and verify it.
- **Commits:** branch from `main` (confirm `52deabe` is in your history, or stop) and commit only your Result section in this doc.
- **Don't edit** `Working.md`, `decisions/`, `memory/`, `CLAUDE.md`, `ROADMAP.md`, `docs/TRAPS.md` or any code. If code is wrong, report it; don't fix it.
- **VM access:** use the `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user `df`, read with `grep -E '^KEY=' .env` only. Find the MCP endpoint and token keys the same way the previous deploy did. No hostnames, addresses or tokens in anything you write.
- **`dfhack-run lua -e` silently does nothing**; use a file. Strip ANSI prefixes before matching output.

## Touched surfaces

VM 103: the deployed script and registry files, `dfmcp-server` restart, game state as listed above. Repo: this doc only.

## Report

1. **Deploy:** hashes, the restart, and how you proved the new code runs.
2. **Tool lists:** per-role `tools/list` results.
3. **Crop write:** calls, read-backs and the final plot state.
4. **Aquifer check:** result.
5. **Designation:** result.
6. **Unpause window:** ticks, wall time, stop reason, whether the stair got dug.
7. **After the unpause:** `diggable.find` at z167, and the end state verified paused.
8. **Findings:** anything wrong in the code, and new traps.
9. **Commit:** the hash.
