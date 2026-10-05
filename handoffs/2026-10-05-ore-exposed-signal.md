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

