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

---

## Result (executor, 2026-09-17)

**Status: done**, one finding worth follow-up (downstair candidate landed on
an occupied tile), one instrumentation bug in this stream's own sampler
(not the deployed code) that cut the supervised unpause short. Fort left
paused, verified. `d2238f2` was already in this worktree's history at
start (no merge needed).

### 1. Deploy

5 files (the exact diff since the last deploy, confirmed via
`git diff --stat 0ae7ad2~1 HEAD -- scripts/dfhack dfmcp dfqueue learning
agents`, which touched only these five): `scripts/dfhack/df-overseer-farm.lua`,
`scripts/dfhack/df-overseer-diggable.lua`, `scripts/dfhack/TOOLS.yaml`,
`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`.

- Built via `git -c core.autocrlf=false archive`, sha256 manifest built
  locally, transferred, `sha256sum -c` on the VM: **all 5 OK**. Backed up
  the 5 pre-existing files to `/opt/df/deploy-backup-2026-09-17c/` before
  overwriting. Installed with `df:df` ownership; re-hashed at the final
  installed paths and confirmed byte-identical to the manifest.
- **Restarted `dfmcp-server` only** (`systemctl restart`): clean
  stop/start in the journal, `ActiveState=active`, `SubState=running`,
  `NRestarts=0`. `df-fortress` (`ActiveEnterTimestamp` 2026-09-16 10:44 UTC)
  and `df-xvfb` (2026-09-11 02:26 UTC) both unchanged, confirming neither
  was touched.
- **Proved the new code is live** two ways: (a) per-role `tools/list` over
  a real MCP session (built a small client on the VM using its own
  `.venv`'s `mcp==2.2.0`/`httpx2` packages, tokens read server-side from
  `/opt/df/dfmcp-smoke/.env` by key, never printed) went from the
  pre-deploy baseline architect 19 / overseer 32 / consultant 4 to
  **architect 21 / overseer 34 / consultant 4** immediately after the
  restart, gaining exactly `diggable__find-stair`+`farm__list` (architect)
  and `diggable__dig-stair`+`farm__list`+`farm__set-crop` (overseer) —
  tools that cannot exist in the old code; (b) `farm.list` and
  `diggable.find-stair`, brand-new commands, both returned real,
  sensible live data (below), which the old code could not have answered
  at all.

### 2. Tool lists

Live, post-restart, over the real MCP server with real role tokens:
**architect 21** (adds `diggable__find-stair`, `farm__list`), **overseer
34** (adds `diggable__dig-stair`, `farm__list`, `farm__set-crop`),
**consultant 4** (unchanged). Matches the handoff's expected totals
exactly. Confirmed `diggable__find-stair` is present for the Architect and
**absent** for the Overseer (overseer only got `diggable__dig-stair`).
Independently cross-checked against `tool_definitions()` computed locally
from this worktree's own `HEAD` via `.venv-dfmcp` (the exact function
`dfmcp/server.py` calls) before touching the VM: architect 21 / overseer
34 / consultant 4, byte-for-byte matching the live result.

### 3. Crop write

Found a second valid crop for plot 4 via the tool's own validation (a
`set-crop` dry run against an invalid crop name first surfaced the real
argument names, `id`/`season`/`crop`/`dry_run` lowercase, and that
`dry_run` must be the *string* `"true"`/`"false"`, not a JSON boolean — a
new trap, see Findings): `BUSH_QUARRY` (quarry bush, one of the fort's six
subterranean-only owned seed types) dry-run-validated against plot 4,
`outside:false`, `would_set_plant_index:177`.

- **Real write**: `farm.set-crop(id=4, season=spring, crop=BUSH_QUARRY,
  dry_run=false)` → `write_ok:true`, `read_back_plant_index:177`.
  Independent `farm.list` read-back confirmed: spring `BUSH_QUARRY`,
  the other three seasons still `MUSHROOM_HELMET_PLUMP`.
- **Restore**: `farm.set-crop(id=4, season=spring,
  crop=MUSHROOM_HELMET_PLUMP, dry_run=false)` → `write_ok:true`,
  `read_back_plant_index:173`. Final `farm.list`: all four seasons
  `MUSHROOM_HELMET_PLUMP`, `exists:true`, `id:4` — plot 4 ends exactly as
  it started.

### 4. Aquifer check

**Passed — no aquifer, no liquid.** Independently resolved the rank-1
stair candidate's real coordinates with a standalone read-only Lua script
(an operator-side reimplementation of `ranked_stair_candidates`'
selection predicate — `find_stair_down`/`dig_stair_down` never expose
coordinates by design, so this was necessary to do the check at all; the
script never designates anything). Rank-1 resolved to `x=96 y=96`,
`upper_z=168` (the farm-room level), `lower_z=167` (the dig target),
`dist_to_anchor=0.000` — matching both `diggable.find-stair`'s (Architect)
and `diggable.dig-stair`'s dry-run (Overseer) own rank-1 output exactly
(same `distance_tiles:0`, `direction:"S"`). Checked `water_table`
(aquifer) and `flow_size` (liquid) at the target tile and all 8
neighbours at z167: **`any_aquifer=false`, `any_liquid=false`** across
all 9 tiles. Clear to designate.

### 5. Designation

Called `diggable.dig-stair(level=-1, near_landmark="Embark Site", rank=1,
radius_tiles=30, dry_run=false)` as Overseer. Result: `downstair_ok:true`
with `downstair_stats: {"Tiles designated for digging": 0}`; `upstair_ok:
true` with `upstair_stats: {"Tiles designated for digging": 1}`.

**Read back directly (`dfhack.maps.getTileBlock(...).designation[...].dig`)
against the real tiles, not just the tool's own report:**
- Upper tile (96,96,168), the downstair target: `dig_designation=0`
  (`tile_dig_designation.No`) — **not actually designated**, despite
  `downstair_ok:true`.
- Lower tile (96,96,167), the upstair target: `dig_designation=6`
  (`tile_dig_designation.UpStair`) — designated, matching
  `upstair_stats`.

**Root cause, chased read-only, no further designation attempted:** the
upper tile (96,96,168) is occupied by **Building id=1, type=Stockpile**
(`occupancy.building=2`, `dfhack.buildings.findAtTile` resolves it). This
fort's Stockpile sits exactly at the rank-1 candidate's location.
Quickfort's own `check_tiles_and_extents` (the same function noted in the
2026-09-17 water-industry-tools-deploy Result as silently skipping
"occupied" tiles for `#zone`/`#place`) silently skips a dig designation
under an existing building too, rather than erroring — so
`quickfort run` returned `CR_OK` (hence `downstair_ok:true`) while
designating nothing. **Only the upstair half of the pair exists on the
fort right now**; the pair is incomplete. See Findings for the code gap
this exposes.

### 6. Unpause window

Pre-launch, live-read immediately before starting: `paused=true, year=30,
tick=227008, fps=10, citizens=15` — unchanged from the handoff's own
expected pre-state and from this stream's earlier pre-state check, so no
time passed in between designating and launching.

Ran as `stair_run.sh` via `nohup setsid`, detached from the SSH session,
with a `trap` calling `SetPauseState(true)` on `EXIT INT TERM`, FPS left
at its standing value (10, asserted rather than set), a 450s (7.5 min)
ceiling, 15s sample interval. **Stopped after exactly 1 sample**, tick
**227008 -> 227159** (151 ticks, ~10 ticks/wall-second, ~15 wall-seconds
total), reason `focus_not_dwarfmode`.

**That stop was a false positive from this stream's own sampler, not a
real problem, and not a code issue in the deployed tools:**
`dfhack.gui.getCurFocus()` returns a **table** (a focus-stack list, e.g.
`{"dwarfmode/Default"}`) in this DFHack build, not a string. The
sampler's `tostring(focus):match("^dwarfmode")` check was written
assuming a string return and always failed, `stop`ping on the very first
sample regardless of the real focus. Verified after the fact,
fort-paused, read-only: `getCurFocus(true)[1] == "dwarfmode/Default"` —
the actual focus was fine the whole time; no dialog, no interruption.
This is the handoff's single authorized unpause, already used — **not
retried**, per the "no second unpause" constraint, even though the real
stop reason was an executor bug rather than a game condition.

**The trap fired and re-paused correctly**: `PAUSED tick=227160` in the
trap log, one tick past the last sample.

**Whether the stair got dug: no.** Re-read both tiles after: upper
(96,96,168) still `dig_designation=0`, `tile_shape=1` (FLOOR, unchanged);
lower (96,96,167) still `dig_designation=6` (UpStair, still queued, not
completed), `tile_shape=4` (WALL, uncarved). The single sample taken
during the window (`job_present=false`, `citizens=15`,
`any_liquid=false`) is consistent with no miner having reached the job
yet in ~15 wall-seconds — 151 ticks is too short to expect it. No death,
no citizen-count drop, no liquid appeared. No planting occurred on plot 4
(farm.list unchanged after) — expected, given the tiny window.

### 7. After the unpause

`diggable.find(w=3, h=3, level=-2, near_landmark="Embark Site",
radius_tiles=30)` (Architect role) near z167: **`[]`** — correct, not
broken: z167 is still fully hidden/undug there (no walkable-network tile
exists yet for `find_diggable_area`'s adjacency requirement), matching
the stair readback above.

**End state, verified live, fort paused:** `paused=true, year=30,
tick=227160, fps=10, citizens=15`, focus `dwarfmode/Default` (confirmed
directly, correcting the sampler's own misreading above). `farm.list`
plot 4 unchanged (all four seasons plump helmet). Stair designation
intact: upstair still queued at z167, downstair still never designated
at z168.

### 8. Findings

- **Code gap, `diggable.dig_stair_down`/`ranked_stair_candidates`
  (`scripts/dfhack/df-overseer-diggable.lua`): candidate selection checks
  `walkable_group`+`is_diggable` but never building occupancy at the
  candidate's own (upper) tile.** A tile fully covered by an existing
  building (here, the fort's Stockpile) can rank first, and the real
  `dig-stair` call then reports `downstair_ok:true` while quickfort
  silently designates 0 tiles there — the `ok` field alone is not proof
  of a real designation; `*_stats`' tile count (or, as this stream did, a
  direct designation read-back) has to be checked too. This is the same
  `check_tiles_and_extents` occupied-tile skip the water-industry-tools
  deploy stream already found for `#zone`/`#place`, now shown to affect
  `#dig` as well. Not fixed here, per this handoff's "report, don't fix"
  constraint.
- **New trap: the MCP tool schema wants `dry_run` as the string
  `"true"`/`"false"`, not a JSON boolean** — passing a real boolean
  through the MCP client raises `'dry_run' must not be a boolean, got
  True`. Worth a `docs/TRAPS.md` line (not added here — out of this
  stream's touched-surfaces).
- **New trap: `dfhack.gui.getCurFocus()` (no args, and with `true`) returns
  a Lua table (a focus-stack list), not a string, on this DFHack build.**
  Any supervised-unpause sampler checking "focus is dwarfmode" must index
  the table (`getCurFocus(true)[1]`) rather than `tostring()`-matching it,
  or it will false-stop on the very first sample, as this stream's did.
  Worth a `docs/TRAPS.md` line (not added here, same reason as above).
- **MCP tool argument names are lowercase and exact** (`id`, `season`,
  `crop`, `dry_run` for `farm.set-crop`; `near_landmark`, `radius_tiles`,
  `level` for the diggable/farm finders) and DFHack's positional CLI
  parsing means an optional `LEVEL` slot can't be skipped once a later
  optional argument is supplied — confirmed by trial against the live
  server's own error messages, which name the accepted argument list
  directly and are reliable to develop against.
- **`mcp.client.streamable_http.streamable_http_client`'s exported name in
  this install's `mcp==2.2.0` is `streamable_http_client`, not
  `streamablehttp_client`**, takes `http_client` (a pre-built
  `httpx2.AsyncClient`, not a bare `headers=` kwarg) instead of `headers`
  directly, and its async context manager yields a 2-tuple
  `(read, write)`, not the 3-tuple some other `mcp` versions document.
  Useful for the next stream that needs to script an MCP client here.

### 9. Commit

See this commit's own hash in the executor's final report to the
orchestrator (this Result section is committed together with the
handoff's own history, so the commit that adds it necessarily postdates
it).
