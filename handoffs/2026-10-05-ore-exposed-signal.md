# Handoff: an ore-exposed signal, so exposed ore gets mined

Date: 2026-10-05. **Executor, Sonnet, worktree. Offline build; read-only on
hosts; no deploys.** User's call: register 2026-10-05, "Exposed ore is
mined".

## Why

The user saw hematite exposed in the corners of two bedrooms dug today
(site-5 and site-6 near Activity Zone #5). Nothing tells an agent a dig
uncovered ore, smoothing appears to stall on those faces, and the fort has one
pick and no forge, so the ore matters later. Decide what, let the game execute:
the Architect proposes mining the vein; dwarves dig and haul.

## What to build

1. **A player-visible read** (no armok: only faces a player can see, never
   hidden tiles): which ore materials are exposed on walls adjacent to dug
   tiles of a given area (a blueprint site, a zone, or near a landmark), using
   `inorganic_raw:isOre()` (`research/2026-09-28-ore-detection.md`). Generic
   over any ore; output is counts and names per material plus a handle the
   existing `construction.mine-vein` (or whatever tool mines a vein today; find
   it) can take. Coordinate-free in what models see, like every other tool.
   Prefer extending an existing tool (`surface.vein-material`, blueprint
   status) over a new one; say which and why.
2. **The signal**: the conductor polls that read for recent room sites and
   areas dug since the Architect's last run, edge-triggered (a vein wakes once
   until it is mined or the proposal is ruled), and wakes the Architect through
   the lane-trigger data in `conductor/policy.yaml` (`conductor/lanes.py`).
   Its briefing gets one line per exposure.
3. **Finish waits for ore**: say in the plan how a room's finish phase should
   wait until its exposed ore is mined (the stage 2 design's per-phase status,
   `docs/CONDUCTOR-EXECUTION.md` 4.3, is the natural place; if that is stage 2
   work, record it as a note for stage 2D rather than building it here).
4. Allowlists: the Architect gets the read and the mining proposal path if it
   lacks them; the conductor gets the read for polling. Update tool counts.
5. Test on site-5/site-6 shapes with the Lua stub; live check after deploy
   (read the two rooms, expect hematite).

## Rules

- First step: `git merge --ff-only main` (fall back to `git fetch origin &&
  git merge --ff-only origin/main`). Commit plan early and after each
  milestone.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md`, `docs/CONDUCTOR-EXECUTION*.md`.
- Touched surfaces: `scripts/dfhack/` (the read; TOOLS.yaml entry if a new
  tool), `dfmcp/` registry/tools only as needed for the read (not
  `queue_tools.py`, not `dfqueue/`: stage 2A is building there),
  `conductor/lanes.py`, `conductor/policy.*`, `conductor/cycle.py` (signal
  wiring only), `conductor/briefing.py` (one line), `agents/*/tools.yaml`,
  tool-count tests and docs, tests, this handoff.
- No armok powers (no hidden tiles). Never show a model a rendered map. Tools
  generalisable. Public repo: no hostnames, IPs or tokens. No em dashes. No
  attribution lines in commits.
- Full ambient `python -m pytest` (with `lupa`) and `dfmcp/tests` green.

## Result

### Plan (executor, 2026-10-06)

1. **The read extends `surface.vein-material`** (it already decodes every ring
   tile with `isOre()`/`isGem()`; a second tool would duplicate it). Adds an
   `exposed` block: ore or gem tiles still shaped WALL and player-visible
   (smoothed walls count; already-mined floor and hidden tiles do not), as a
   list of `{mineral_name, kind, tiles}` plus the `mine_with` handle. Ring
   corners are included (the site-5/site-6 case).
2. **Sites without a zone**: `blueprint.status` and `blueprint.sites` re-read
   through the existing find_zone rectangle shim (room rectangle from the
   blueprint), so a freshly dug room reports `ore_exposed` before any zone
   exists. `construction.mine-vein` accepts a `site-N` handle as well as a
   zone id, resolved to the same room rectangle.
3. **Signal**: `conductor/ore_watch.py` parses `blueprint.sites`; edge state in
   `lane_state.json` (`lanes.apply_ore_edges`); wake reason `ore_exposed`
   through `lane_triggers.architect.ore_exposed` in `policy.yaml`. Edge rule:
   a (site, mineral) wakes once on first sight, re-arms when it leaves the
   read (mined) or after `ore_renotify_ticks` still exposed (the backstop for
   a ruled-but-not-mined case). A failed poll keeps state.
4. Briefing: one line per standing exposure, Architect only.
5. Allowlists: conductor gains `blueprint.sites`; Architect already holds
   `surface.vein-material`, `blueprint.sites/status`; Overseer holds
   `construction.mine-vein`. Counts and docs updated.
6. Finish-waits-for-ore: recorded below as a note for stage 2D, not built.


### Result (executor, 2026-10-06): built offline, not deployed

**The read, as built.** It extends `surface.vein-material` (it already decodes
each ring tile with `isOre()`/`isGem()`; a second tool would duplicate that).
Its result gains `exposed`: `total_tiles`, `materials` (`mineral_name`, `kind`
ore or gem, `tiles`, sorted), `unclassified_tiles` (the unknown count, never
folded into ore) and `mine_with`. Exposed means ore or gem still shaped WALL
and visible to the player: a vein smoothed into a wall counts, a tile already
mined open or still hidden does not. The ring includes the corners (the
site-5/site-6 case). `blueprint.sites` rows now carry `ore_exposed` and
`blueprint.status`'s `surface` gains `vein_material` (summary only, no tile
list), both read through the existing room-rectangle shim, so a freshly dug room
with no zone yet reports ore (the shim's `find_zone` upvalue is shared by
`vein_material`, which a manifest test now pins). A site's `mine_with` is
`construction.mine-vein-site`. An unreadable site reports `{unreadable: true}`,
never an empty exposure.

**The handle.** New command `construction.mine-vein-site SITE_ID [DRY_RUN]
[RES_ID] [OVERRIDE]`, same function and guards as `mine-vein` (dry run default,
reservations, refuses what it cannot classify). It exists because `ZONE_ID` is
an integer argument in the MCP schema (type is by argument name) and a site
handle is not; the shared `mine_vein` resolves `site-N` through the new
`site_room_rect` in `df-overseer-blueprint.lua` (lazy reqscript, one direction).

**The signal.** `conductor/ore_watch.py` parses one `blueprint.sites` poll per
cycle into `(site, material)` exposures. The edge rule is in `conductor/lanes.py`
(`apply_ore_edges`, state `ore` in `lane_state.json`), data-driven by
`lane_triggers.architect.ore: true` and `ore_renotify_ticks: 12000` in
`policy.yaml`; wake reason `ore_exposed` (full_speed). A pair wakes the Architect
once on first sight; it re-arms when the pair leaves the read (mined), or after
12000 ticks (10 game days) still exposed, which stands in for "or the proposal is
ruled" (the conductor cannot tell an accepted ruling from a rejected one, and
re-arming on any ruling would double-propose after an accept; the existing
`ruling_on_own` wake already tells the Architect of the ruling). A site the poll
could not read keeps its state; a failed poll changes nothing; a save reload
(tick going backwards) re-arms. The Architect's briefing carries `ore_exposed`,
one line per standing exposure (capped at 5), only for a role whose lane has
`ore` and only while something is exposed.

**Not covered.** Areas dug outside a blueprint site (a bare `diggable.dig`)
have no room rectangle and are not polled; the Architect reads any zone on
demand with `surface.vein-material`.

**Finish waits for ore (note for stage 2D, not built).** Per the stage 2 design
section 4.3, `queue.observe` already runs `blueprint.status SITE PHASE`. For a
finish phase (smooth, build or zone) the executor should, before `blueprint.apply`
and in `observe`, read `surface.vein_material.exposed.total_tiles` from that same
status result and treat a non-zero value as "waiting on ore": hold the step (not
fail, not retry), send `step_attention` to the proposer naming the materials, and
release it when the count reads 0 (a vein mined open leaves the read). It needs
no new tool: the status call is already made, and `exposed.unclassified_tiles`
non-zero should hold too rather than guess. A tool-level alternative (refusing a
finish apply in `blueprint.py`'s order guard while ore shows) was not built, since
it would change the live smoothing path without the executor's hold semantics.

**Files.** `scripts/dfhack/df-overseer-surface.lua`, `-blueprint.lua`,
`-construction.lua`, `TOOLS.yaml`; `conductor/ore_watch.py` (new), `lanes.py`,
`policy.py`, `policy.yaml`, `cycle.py` (wiring only), `briefing.py` (one key);
`agents/overseer/tools.yaml` (+`construction.mine-vein-site`),
`agents/conductor/tools.yaml` (+`blueprint.sites`), `agents/architect/role.md`
(a charter bullet); tests; `docs/STATE.md` counts. Real output shape of
`blueprint sites` checked read-only on VM 103 (a bare JSON array of rows, as
parsed); the deployed copy predates this change so `ore_exposed` is not yet
there.

**Tool counts.** overseer 97 to 98, conductor 23 to 24, architect 53,
quartermaster 26, consultant 29 unchanged (the Architect already held
`surface.vein-material`, `blueprint.sites` and `blueprint.status`).

**Deploy targets (not done).** VM 103: `scripts/dfhack/` (surface, blueprint,
construction, TOOLS.yaml) and dfmcp (allowlists, registry); VM 106: `conductor/`
(vm106-conductor) and the agent charter (vm106-agents). The conductor allowlist
needs `blueprint.sites` live on dfmcp before the conductor change goes out (an
undeployed entry only logs and skips the watch). **Live check after deploy:**
`blueprint sites` should list `ore_exposed.materials` with HEMATITE for site-5
and site-6; then `construction mine-vein-site site-5` as a dry run.
