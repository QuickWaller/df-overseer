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

**Tests (first pass)**: 8 new (`test_buildingplan_material_filter_lua_logic.py`,
a fake `plugins.buildingplan` recording every call, failing if the
write/restore calls go missing), 5 new in `test_construction_lua_logic.py`,
plus assertions added to the existing building-material tests. Ambient
`python -m pytest`: 2082 passed, 3 skipped at that point.

## Correction, same day: the first pass was a silent no-op

A live `dfhack-run lua` test on VM 103 (reversible, restored after, run by
the orchestrator against Construction/Wall index 0) found the first pass's
write did **nothing**: `filter_material_names` for a real wall was
`["WOOD", "material_0_243"]`, neither name recognised by buildingplan's own
`mat_cache` (keyed by `MaterialInfo:toString()`, confirmed live,
`dfhack.matinfo.decode(0,243):toString() == "shale"`, `0:182 == "hematite"`),
so `setMaterialFilter` silently reset to "no restriction" (367 of 367
materials stayed enabled). Writing `{"shale"}` directly left exactly 1
enabled, `getMaterialFilter`'s `props.enabled` read was already correct, and
`df.construction_type` reverse lookup (`[1] == "Wall"`) worked. Root cause:
the class was built from this file's own **stock scan** (`decode_item_material`'s
`.material.id`, empty for a boulder on this fort, falling back to the
`material_0_N` shape), which has no reason to match buildingplan's naming at
all.

**Fix**: the class is now resolved from buildingplan's **own vocabulary**
(`getMaterialFilter(type, sub, cust, index)`, which already lists every name
valid for that exact filter, tagged with its category and current count),
never from stock. New helpers in `building.lua`: `vocabulary_for_filter`
(wraps `getMaterialFilter`), `economic_inorganic_names` (scans every
inorganic via `dfhack.matinfo.decode(0, idx)`, the same overload
`decode_vein_tile` already uses, flagging `isOre()`/`isGem()`), and
`resolve_filter_class` (the vocabulary minus economic names, or the whole
vocabulary under `allow_economic`, or one named material validated against
the vocabulary, never against stock). `resolve_material_choice` now takes a
`filter_ctx` (`vocab`, `vocab_err`, `economic_names`, `economic_err`) and
sets `rec.filter_material_names`/`rec.filter_class_error` from it,
independent of every stock-based branch (those stay as the advisory
`chosen_material`/`available`/`materials` fields, unchanged). Every write in
`apply_material_filters` is now **read back and verified**: if the enabled
set does not exactly match what was written, the prior filter is restored
immediately and the rec is reported `ok: false` with the mismatch, never
silently counted as applied. `decode_item_material` now prefers
`MaterialInfo:toString()` for its report name too (falling back to the old
shape), so the advisory report also stops showing `material_0_243`.

**Stub changes**: `test_building_material_and_previously_built_lua_logic.py`'s
stub gained a two-overload `dfhack.matinfo.decode` (item-based and
index-based), a fake `raws.inorganics.all`, and a `getMaterialFilter` backed
by a settable `VOCAB`/`INORGANICS`, with sensible defaults so its existing
16 tests needed only the `filter_material_names` assertions updated to the
new vocabulary-based values (they now include materials with zero stock,
which is the fix's whole point).
`test_buildingplan_material_filter_lua_logic.py`'s stub became **stateful**
(`FILTER_STATE`/`UNIVERSE`/`SEEDED`) so a `getMaterialFilter` read after a
`setMaterialFilter` write reflects it, plus a `VALID_NAMES` mechanism that
reproduces the live bug exactly: `set_valid_names` declares which names
buildingplan actually recognises, and a write of anything else is silently
dropped, so `test_a_write_of_unrecognised_names_is_caught_by_the_readback_and_restored`
fails without the readback fix and passes with it, directly proving the
regression guard.

**Tests (final)**: `test_buildingplan_material_filter_lua_logic.py` now has
11 (3 new: the unrecognised-names catch, a recognised-name success with
`enabled_count`, and an economic-enabled report that degrades cleanly when
the economic scan is unavailable). `test_construction_lua_logic.py` and
`test_building_material_and_previously_built_lua_logic.py` unchanged in
count. Ambient `python -m pytest`: **2131 passed, 3 skipped**. `dfmcp/tests`:
this worktree has no `.venv-dfmcp` (fresh worktree, not carried over);
ambient Python gave **643 passed, 3 skipped**, not the isolated-venv count
CLAUDE.md records. dfmcp needed no code change either pass: it reads
`TOOLS.yaml` command strings generically, with no per-tool argument schema
to update.

**Only a live test can settle**: whether the corrected write, once verified
by readback, is actually honoured by DF's own item search on a running fort
(the readback proves buildingplan's bookkeeping changed, not that a dwarf
will draw from the narrowed set); whether the write/restore window is wide
enough relative to quickfort's own `buildingplan` registration timing during
`#build`; and whether a material with zero current stock, now correctly
included in the written class since it comes from buildingplan's raws-backed
vocabulary rather than stock, actually gets picked once it later appears
in stock.
