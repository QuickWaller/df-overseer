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

## Result

**Status: done.** Deployed and verified by execution; fort untouched throughout,
paused on the same tick before and after.

**Sequencing:** preparation (steps 1-2 below) ran while the sibling
`2026-09-17-farm-still-first-build` stream was still live. Polled its handoff
doc for a `## Result` heading every 60s; it appeared after **~13 minutes**
(under the 20-minute stop threshold). Independently re-verified live rather
than trusting the doc: `paused=true, year=30, cur_year_tick=227008` via
`dfhack.world.ReadPauseState()`/`df.global.cur_year_tick` over SSH, matching
the sibling's own reported end-state exactly, before touching any file.

**Read-only pre-check (step 1), done before waiting:** `dfmcp-server`,
`df-fortress`, `df-xvfb` all `active`. Fort paused, tick **222477** (matches
the sibling's own expected pre-state, confirming no game time had passed since
the last session). **Live per-role `tools/list` captured over a real MCP
client** (`streamable_http_client` + `ClientSession`, run on the VM itself
using its own `httpx2`/`mcp==2.2.0` venv so no port had to be exposed off-box;
role tokens read from `/opt/df/dfmcp-smoke/.env` by key via `source` into
`os.environ`, never echoed): **architect 15, overseer 23, consultant 4** —
byte-for-byte identical to the previous deploy's own recorded live state.

**Expected after-state (step 2), computed locally from `main`** via
`load_registry(native_tools=queue_tools.NATIVE_TOOLS)` → `load_roster(reg)` →
`tool_definitions(reg, roster, role)` (the exact function `dfmcp/server.py`'s
`_on_list_tools` calls, not a hand-rolled reimplementation), `.venv-dfmcp`:
**architect 19 (+4: `orders__list`, `trees__find`, `well__find`,
`zone__find`), overseer 32 (+9: `orders__cancel`, `orders__create`,
`orders__list`, `trees__fell`, `trees__find`, `well__build`, `well__find`,
`zone__find`, `zone__place`), consultant 4 (unchanged).** Cross-checked
against a second computation at the pre-merge commit (`e16927b`, `main`'s tip
before `d795ed9`) in a throwaway detached worktree, removed after: confirmed
byte-for-byte equal to the live pre-check capture above, and confirmed the
before-set is a proper subset of the after-set for all three roles (nothing
dropped).

**Surprise, found by the handoff's own "any other file... that differs by
hash" instruction:** a full 65-file sweep of `dfmcp dfqueue learning agents
scripts/dfhack` (excluding `*.sqlite3*`, `.venv*`, `__pycache__`, and — unlike
the previous deploy's sweep — also excluding the Lua files, which live under
`hack/scripts` not the server tree) found **5 files differ, not 3**: the
expected `scripts/dfhack/TOOLS.yaml`, `agents/architect/tools.yaml`,
`agents/overseer/tools.yaml`, plus **`dfmcp/tests/test_registry.py` and
`dfmcp/tests/test_roles.py`** (added this stream's own registry/role-allowlist
coverage commit, `7f170dd`). These aren't load-bearing for the running
service, but the handoff's scope language includes them explicitly, so they
were deployed too — 14 files total, not 12.

**All df-overseer-\*.lua hash-compared against `main`, not just the diff
since the last deploy:** `breach`, `chokepoints`, `connectivity`, `diff`,
`diggable`, `farm`, `labor`, `landmarks`, `openarea`, `overview`, `stocks`,
`stuckjobs`, `ui` all matched `main` exactly — no fresh staleness beyond the
previous deploy's own fix. `workshop.lua` differed (extended this stream, as
scoped). `orders.lua`, `trees.lua`, `well.lua`, `zone.lua` had no prior
deployed copy (new). The known out-of-band `df-overseer-embark.lua` (not in
git, flagged by the previous deploy) is still present and was left untouched,
outside this stream's scope.

**Files deployed, hashes verified: 14** (manifest built locally from a
`git -c core.autocrlf=false archive HEAD` extraction, `sha256sum -c` on the
VM immediately after extracting the tarball, then re-hashed a second time at
each file's final installed path — both checks matched the manifest exactly
for all 14 files):
- 5 Lua, to `/opt/df/game/hack/scripts/`: `df-overseer-orders.lua`,
  `-trees.lua`, `-well.lua`, `-zone.lua` (new), `-workshop.lua` (redeployed,
  extended).
- 4 blueprints, to `/opt/df/game/dfhack-config/blueprints/` (flat, additive —
  confirmed by directory listing before/after that nothing else in that
  directory changed): `starter-well-1x1.csv`, `starter-mason-3x3.csv`,
  `starter-mechanic-3x3.csv`, `starter-carpenter-3x3.csv`.
- 5 server-tree files, to `/opt/df/dfmcp-smoke`: `scripts/dfhack/TOOLS.yaml`,
  `agents/architect/tools.yaml`, `agents/overseer/tools.yaml`,
  `dfmcp/tests/test_registry.py`, `dfmcp/tests/test_roles.py`.

Ownership `df:df` on every deployed file, verified with `ls -la` against each
file's pre-existing neighbours.

**Backup:** `/opt/df/deploy-backup-2026-09-17b/{hack-scripts,blueprints-full,server-tree}/`
— the one pre-existing Lua file about to be overwritten (`workshop.lua`), the
whole prior 8-file `blueprints/` directory (nothing there was overwritten;
backed up anyway, matching the previous deploy's own practice), and all 5
server-tree files' prior content — all copied before any write, owned `df:df`.

**Restart:** `dfmcp-server` only, via `systemctl restart`. `NRestarts=0`,
`ActiveState=active`, `SubState=running`, journal clean (clean shutdown/
startup sequence, Uvicorn back up within 1 second, no errors or tracebacks).
`df-fortress` `ActiveEnterTimestamp` (2026-09-16 10:44 UTC) and `df-xvfb`'s
(2026-09-11 02:26 UTC) both unchanged from the previous deploy's own recorded
values — neither was ever touched.

**Live per-role `tools/list` after restart, over the same real MCP client —
exact match to expected, byte for byte:** architect 19, overseer 32,
consultant 4, every name identical to the locally computed expected list.

**How the running code was proven to be the new code (the reqscript-cache
trap):** `zone.lua`, `trees.lua`, `well.lua`, `orders.lua` are brand-new
top-level scripts with no prior deployed copy under any name, so no stale
cache could apply to them by construction — real, sensible live output
(matched water-body geometry between `zone find` and `well find` at the
correct relative levels; live fort-owned material/labor counts in `trees
find`/`orders create`) is itself the proof they loaded. For `workshop.lua`
(redeployed, not new): checked which of its `reqscript`-loaded dependencies
changed this stream (`landmarks`, `openarea`, `stocks` — grepped, all three
unchanged) and found none did, so the cache-invalidation question that
mattered for the previous deploy's `openarea.lua` change doesn't apply here.
The direct proof used instead: `workshop find mason`/`build mason` both
succeeded live with sensible `Mason's Workshop` results (`labor: MASON`,
`citizens_with_labor: 2`) — `mason` was not a supported `KIND` before this
stream, so a stale pre-deploy `workshop.lua` could not have answered this
call at all. Same proof repeated for `mechanic` and `carpenter`.

**Dry runs (step 7), each via `dfhack-run <script> <args>` directly (the CLI
form; the module-style `reqscript(...).fn(...)` form used for the first
attempt returned nothing and was abandoned), fort never mutated:**
- `zone find water_source` at level 0 (surface, z169) near "Embark Site",
  radius 30/60: **`[]` both times** — correct, not broken: at level -1
  (z168, underground) the same call returns 5 real water-body candidates,
  including one at distance 0 from the existing "Activity Zone #1" WaterSource
  zone, so the surface level genuinely has no revealed water tile.
- `zone find water_source` at level -1 near "Embark Site", radius 30: **5
  candidates**, `tile_count` 4-31, all `stagnant:true, salt:false` — matches
  the underground pond/cavern water this fort already has.
- `trees find` near "Embark Site", radius 30: **154 reachable trees**
  (12/34/108 across the three distance bands), `labor: CUTWOOD`,
  `citizens_with_labor: 1`, `fort_owned_axes: 2` — identical to the
  water-and-industry-tools stream's own local-only figures, now live.
- `well find` near "Embark Site" (default level, surface z169), radius 30:
  **5 candidates**, `water_depth` 6-7, `stagnant:true`, all near "Activity
  Zone #1" — the same surface pond the sibling stream's zone covers.
- `orders list`: **`manager_appointed:false, orders:[]`** — matches the
  water-and-industry-tools stream's own live-verified finding that no citizen
  holds the MANAGER position on this fort.
- `workshop find mason`: **5 candidates**, `labor: MASON`,
  `citizens_with_labor: 2`, `building_material.accepts:
  [BOULDER, WOOD, BLOCKS]`, `fort_owned.WOOD: 3`.
- `zone place water_source` dry-run (level -1, rank 1, near "Embark Site",
  radius 30): resolved the same rank-1 candidate as `find`, `dry_run:true`,
  `would_zone_tiles:27`.
- `trees fell` dry-run (n=3, near "Embark Site", radius 30): `dry_run:true`,
  `would_fell:3`, `nearest_distance_tiles:5.39`, `farthest_distance_tiles:7.62`.
- `well build` dry-run (near "Embark Site", `starter-well-1x1.csv`, rank 1,
  radius 30): resolved the same rank-1 candidate as `find`, `dry_run:true`,
  `would_run_blueprint:"starter-well-1x1.csv"` — proof the blueprint this
  deploy just placed now resolves, where before it would have failed on a
  missing file.
- `orders create brew_drink` dry-run (amount 1): `dry_run:true,
  workshop_exists:1`, `would_queue:{job:"CustomReaction",
  reaction:"BREW_DRINK_FROM_PLANT"}` — first attempt with `CARVE_ROUGH_GEM`
  was correctly refused (`"unknown job... expected one of: barrels, blocks,
  brew_drink, mechanisms"` — a real job-name allowlist, not a silent
  no-op), so this is proof of a live refusal path as well as a live success
  path.
- `workshop build mason` / `build mechanic` dry-run (near "Embark Site",
  their new starter blueprints, rank 1): both resolved, `dry_run:true`,
  `would_run_blueprint` set to the just-deployed blueprint file for each.

One self-caused snag, not a code bug: two of the above (`zone place`, `well
build`) initially errored `"no candidate at rank 1 (found 0 near ...)"` on
this executor's first attempt, from passing `"Activity Zone #1"` and an
explicit `level -1` as the search anchor/level — copied from the *result*
field of an earlier `find` call rather than its *input*. Re-run with the
correct anchor (`"Embark Site"`, the same landmark the working `find` calls
used) resolved immediately. Traced by reading `ranked_candidates`/`find_well`
side by side and confirming `build_well` calls the identical function with
identical arguments as `find_well` — so a mismatch could only be a caller-side
argument error, not a build-vs-find code divergence. No code changed to
investigate this.

**Fort paused tick before and after — identical:** `true`, year 30,
`cur_year_tick` **227008**, both immediately after the sibling stream's
re-pause (independently verified before this stream touched anything) and
after every dry run above. No mutation occurred; this stream never called
`SetPauseState`.

**Verified by execution:** all 14 file hashes at final installed paths;
per-role live `tools/list` before and after, exact, over a real MCP protocol
round-trip (not inferred from file contents); `dfmcp-server` health, restart
count, and journal; `df-fortress`/`df-xvfb` untouched
(`ActiveEnterTimestamp` unchanged); all 13 dry-run/find calls above and their
outputs; the mason/mechanic/carpenter `workshop find`/`build` calls as direct
proof of new code running; fort pause state and tick unchanged before/after;
the sibling stream's reported end-tick, independently re-read rather than
trusted from its doc.

**Verified only by mechanism (source read, not exercised live):** the exact
reqscript cache-invalidation behaviour DFHack uses internally for a changed
dependency (not exercised this stream, since none of the deployed files'
`reqscript` dependencies changed); `well.lua`/`zone.lua`/`orders.lua`/
`trees.lua`'s real (non-dry-run) mutation paths
(`dfhack.designations.markPlant`, the quickfort `#zone`/well-blueprint runs,
`workorder.lua`'s `create_orders`) — this stream never ran one, by design,
matching the constraint.

**Cleanup:** all `/tmp` payload files, tarballs, manifests, and the one-off
Python MCP-client script deleted on both the VM and this workstation, checked
by directory listing on both ends after (the VM's `/tmp` still carries
`drinktest.log` and systemd private dirs — pre-existing, not this stream's,
left alone). No hostnames or addresses appear above; the LAN bind address and
role tokens seen while building the live MCP client were read into shell/env
variables only, never printed or written to any file this stream leaves
behind.

**Test counts:** not re-run this stream — no code changed, only already-`main`
content deployed.

**Not done, deliberately:** no real `zone.place`, `trees.fell`, `well.build`,
`orders.create`/`cancel`, or `workshop.build` mutation; no unpause (none of
this stream's business — the sibling owned the one supervised unpause today);
no `df-fortress` restart. Those need their own go-ahead per the handoff's
constraints.
