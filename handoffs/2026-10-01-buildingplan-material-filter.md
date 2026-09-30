# Handoff: write the chosen material class into buildingplan's filter

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

The register's 2026-09-30 ruling: our layer chooses a material **class** (any
non-ore stone, any wood) and writes it into buildingplan's own filter; the
game picks the items. Today `building.build` and `construction.build` compute
a non-economic choice but only report it: the generated blueprint carries no
material (`blueprint_text` in `df-overseer-building.lua` writes the kind key
only), so buildingplan attaches the closest item, which can be ore
(`evals/live/2026-09-30-reservations-deploy/README.md`, correction). Read
`research/2026-09-30-policy-audit.md` (with its orchestrator corrections at
the top) and `research/2026-09-30-item-binding-design.md` first.

## Tasks, in order (commit after each)

1. **Find the real mechanism, from source at DFHack `53.16-r1`** (GitHub
   `DFHack/dfhack`, `plugins/buildingplan/`, `plugins/lua/buildingplan.lua`,
   and quickfort's material syntax in `docs/guides/quickfort-*`). Answer, with
   file and line: how a script sets buildingplan's material filter for a
   planned building (per building, or per building type as a default); whether
   quickfort `#build` cells can carry a material filter directly; what
   "not ore, not gem" can be expressed as (material mask, a category such as
   `stone`/`wood`, a specific-material list); what happens when no item
   matches (the building waits, the named hold we want, or falls back). Write
   this up in the Result; say "unverified" where source does not settle it.
2. **Implement** in `building.build` and `construction.build`: the chosen
   class goes into the filter by the mechanism found, so buildingplan can no
   longer pick ore or gem. Prefer a per-building filter over changing the
   fort-wide default; if only a default exists, set it for the call and
   restore it, and say so. The report states the filter actually written,
   not the intended one.
3. **Tests** in the existing lupa style, including a stub that fails if the
   filter call is missing. Note plainly which parts the stub cannot prove
   (the offline fake world has disagreed with the real API twice: vector
   indexing, `tile_bitmask`).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Generalisable: take the kind and class as arguments, no per-kind branches
  (`CLAUDE.md` project rules). No armok capabilities.
- Update `scripts/dfhack/TOOLS.yaml` entries for both commands.
- Tests: ambient `python -m pytest` and `dfmcp/tests` in `.venv-dfmcp`;
  report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-building.lua`,
`scripts/dfhack/df-overseer-construction.lua`, `scripts/dfhack/TOOLS.yaml`,
their tests and lua stubs.

## Result

**Mechanism**, from DFHack `53.16-r1` source (fetched fresh, GitHub raw):
`plugins/buildingplan/buildingplan.cpp` exposes Lua commands
`setMaterialFilter(building_type, subtype, custom, index, material_names)`
and `getMaterialFilter(...)` (lines 900-956, 957-1010ish; registered in
`DFHACK_PLUGIN_LUA_COMMANDS`, lines 1236-1247). The filter is keyed by
`BuildingTypeKey(type, subtype, custom)` only: fort-wide per building type,
never per instance, and quickfort's `#build` has no per-cell material syntax
at this tag. "Not ore, not gem" must be an explicit material NAME list
(`ItemFilter::matches`: empty list matches anything; a coarser category mask,
`setMaterialMaskFilter`, can only mean a whole class, economic or not, so it
cannot express the exclusion alone). No source settles what happens when
nothing matches (suspended-and-waiting is the existing `buildingplan`
behaviour for any unfilled filter, not independently re-confirmed here).

**Built**: `building.lua` now exports `building_filters_and_gaps` (the real
per-filter breakdown, generalised off raw type/subtype/custom) and
`apply_material_filters` (writes the resolved class, reads/restores the
prior state). `resolve_material_choice` now also returns
`filter_material_names`, every eligible material under the current
choice/default, not just the single reported `chosen_material`.
`build_kind` (building.build) and `build_construction` (construction.build,
now also taking `MATERIAL_CHOICE`) write this class into buildingplan for
the duration of a real (non-dry) call and restore afterward; an empty class
is never written (that would mean "no restriction" to buildingplan).
`TOOLS.yaml` updated for both commands.

**Tests**: 8 new (`test_buildingplan_material_filter_lua_logic.py`, a fake
`plugins.buildingplan` recording every call — fails if the write/restore
calls go missing), 5 new in `test_construction_lua_logic.py`, plus
assertions added to the existing building-material tests. Ambient
`python -m pytest`: 2082 passed, 3 skipped (up from the prior 1845/3 baseline
by other merged work plus these additions). `dfmcp/tests`: this worktree has
no `.venv-dfmcp`; ambient Python gave 634 passed, 3 skipped (not the
isolated-venv count CLAUDE.md records; dfmcp has no per-tool argument
schemas, it reads `TOOLS.yaml` command strings generically, so the CLI
signature change needed no dfmcp code change).

**Only a live test can settle**: whether `setMaterialFilter`'s name list is
honoured as a real whitelist against a running fort's item search (no
DFHack code exercises "attach nothing, let DF search under a narrowed
filter" at this tag, per `research/2026-09-30-item-binding-design.md`);
whether the write/restore window is wide enough relative to quickfort's own
`buildingplan` registration timing during `#build`; whether
`df.construction_type` is genuinely bidirectional for the name->number
reverse lookup `construction_type_numbers` relies on; and whether a material
with zero current stock (never in the written list, since the list is built
from live stock, not the raws catalogue) causes a visible gap once it later
appears.
