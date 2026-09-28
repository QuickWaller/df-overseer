# Handoff: fix `building.build`/`find`'s material filter (same bug already fixed in `surface.lua`)

Date: 2026-09-28. **Executor, Sonnet, worktree.**

## Context

`decisions/DECISIONS.md` 2026-09-25 row: after a real Carpenter's Workshop
got built from hematite (iron ore) by mistake, `building.build`/`find` were
changed to default to a non-economic material, using
`dfhack.matinfo.decode(item).inorganic.economic_uses` as the "is this stone
economic" signal.

`research/2026-09-28-ore-detection.md` (ground-truthed live, read it in full)
proved this is the wrong field for exactly this question, in the exact same
codebase: `economic_uses` answers "which reactions are registered against
this material," not "is this ore/gem worth treating specially." It read
empty for hematite live even though hematite is definitely iron ore. The
correct, live-verified signal is `inorganic_raw:isOre()` and
`.material:isGem()` (the same calls DFHack's own bundled `prospector` plugin
uses) — this is already fixed and live-verified in
`scripts/dfhack/df-overseer-surface.lua`'s `vein_material`/`decode_vein_tile`
(commits `be0ab31`, `365f17b`). **This handoff applies the identical fix to
`scripts/dfhack/df-overseer-building.lua`, which has the same bug in a
different tool.**

## What to do

1. Read `df-overseer-building.lua`'s current material-choice logic (find
   wherever it calls `.economic_uses` or reads "is this material economic" —
   grep the file) and read `df-overseer-surface.lua`'s already-fixed
   `decode_vein_tile` for the exact working pattern:
   `dfhack.matinfo.decode(0, idx).inorganic` (not direct
   `df.global.world.raws.inorganics[idx]` indexing, which errors live —
   `research/2026-09-28-ore-detection.md` and this stream's own commits
   document why), then `:isOre()` / `.material:isGem()`.
2. `building.build`/`find`'s existing item-based access pattern differs from
   `surface.lua`'s tile-based one (an item's material versus a vein tile's
   material) — do not copy-paste blindly. Confirm live (read-only
   `dfhack-run lua`, via `scripts/vm-ssh.sh df`) that `isOre()`/`isGem()` are
   reachable the same way from an item's decoded material as they are from a
   tile's, before committing to the fix. If the access path differs for an
   item versus a tile vein event, say so in your Result section.
3. Update `materials`/`excluded_materials`/`chosen_material` reporting (the
   2026-09-25 fix's existing fields, do not rename them) to use the corrected
   classification.
4. Update `scripts/dfhack/TOOLS.yaml`'s entry for `building.build`/`find` if
   its notes describe the old (wrong) field.

## Rules

- `git merge --ff-only main` first.
- Update or add offline `lupa` tests the same way `surface.lua`'s fix did:
  a test with a real ore item choosing a different (non-economic) material,
  and one confirming a non-ore MINERAL-class material is not wrongly
  excluded. If an existing test stub for this file models `economic_uses`
  the wrong way (mirroring the exact mistake already found and fixed once in
  `tests/lua_stubs/dfhack_surface_vein_world.lua`), fix the stub too, and say
  so in your Result section — this is a known, recurring risk in this
  codebase (`Working.md`, twice already).
- Live-check is welcome (read-only) but this stream should not deploy to VM
  103 or touch the live fort's buildings — a live-verification pass with a
  real dry-run call is the orchestrator's job after merging, the same way the
  surface.lua fix's live check was done independently after the code
  landed.
- No em dashes in prose. No attribution lines in any commit.
- Ambient `python -m pytest` (lupa on `PYTHONPATH`) should stay green; rerun
  and report the count.
- Commit as you go. Stop and report on any permission refusal.
- Fill in this handoff's own Result section: what changed, whether the
  item-material access path matched `surface.lua`'s tile-material path or
  needed something different, and test counts.

## Result

Done, offline. Fixed `decode_item_material` in
`scripts/dfhack/df-overseer-building.lua` to classify an item's material as
"economic" using `inorganic:isOre()` or `inorganic.material:isGem()` (both
called only when `mi.inorganic` reads truthy, i.e. the material is
inorganic at all), replacing the non-empty-`inorganic.economic_uses` check
that `research/2026-09-28-ore-detection.md` proved wrong for this exact
question. `materials`/`excluded_materials`/`chosen_material` and every other
field name from the 2026-09-25 fix are unchanged; only the classification
feeding `economic` changed.

**Item-material access path vs. surface.lua's tile-material path.** They
differ in how the material index is obtained, not in the shape of what
comes back. `surface.lua`'s `decode_vein_tile` calls
`dfhack.matinfo.decode(0, idx)` (mat_type 0 = inorganic, `idx` read off a
map tile's vein event) and gets `.inorganic` (the raw itself) and
`.inorganic.material` (the nested material struct) from that. This file's
`decode_item_material` calls the item-based overload,
`dfhack.matinfo.decode(item)`, which DFHack's own API resolves through the
item's own material/index pair before doing the identical lookup -- per
DFHack's documented `matinfo.decode` contract, both overloads return the
same `MaterialInfo` shape, so `.inorganic` should carry the same
`inorganic_raw` type either way and the same `:isOre()`/`.material:
isGem()` accessors should apply unchanged. **This is not live-verified**: no
`.env`/VM credentials are present in this worktree, so `scripts/vm-ssh.sh df`
cannot reach VM 103 from here (tried; it correctly refused with "no
readable .env at the expected path" rather than guessing at connection
details). The header comment above `decode_item_material` says so plainly
and asks for the same live confirmation `decode_vein_tile`'s tile path
already got, before either code path is trusted in a real decision. Per
this handoff's own rules, that live check is left to the orchestrator's
post-merge pass, the same way `surface.lua`'s fix was verified live
independently after landing.

**Tests.** `tests/test_building_material_and_previously_built_lua_logic.py`
modelled the exact same wrong-field mistake in its own STUB
(`MATINFO`/`set_matinfo` built a `{economic_uses = {...}}` table) --
exactly the "known, recurring risk in this codebase" flagged in the handoff
rules (this is the second time: `tests/lua_stubs/dfhack_surface_vein_world.lua`
was the first, already fixed for `surface.lua`). Fixed the stub to build a
fake `inorganic_raw` via a new `make_inorganic(is_ore, is_gem)` Lua helper
exposing `:isOre()` and `.material:isGem()` methods, and updated
`World.set_matinfo` to take `is_ore`/`is_gem`/`inorganic` instead of
`economic_uses`. Converted every existing call site
(`economic_uses=["SMELT_ORE"]` -> `is_ore=True`, `economic_uses=[]` ->
`is_ore=False`) and added two new tests: one gem material that is
`isGem()`-true but `isOre()`-false is still classified economic (proving
the fix reads both accessors, not just `isOre`), and one non-inorganic
material (no `.inorganic` at all, the wood/organics branch) is classified
`economic: false` and never excluded or errored. All 16 tests in this file
pass. Also updated `scripts/dfhack/TOOLS.yaml`'s `find`/`build` entries
(the `verified` and `notes` fields) to describe the corrected
`isOre()`/`isGem()` check and point at this handoff instead of the old
`economic_uses` language; the `vein-material` entry for `surface.lua`
(around line 2231) still describes the pre-fix "non-empty economic_uses"
rule even though that file's own code comment says it was corrected --
that entry is `surface.lua`'s, out of this handoff's scope, but is worth a
follow-up doc fix since it is now misleading about both tools.

**Ambient `python -m pytest`** (lupa installed to a scratch dir on
`PYTHONPATH`, not the repo, per CLAUDE.md): **1932 passed, 3 skipped**, one
run, no flake in the deliberate-race test this run. This is higher than the
2026-09-25-measured 1845 passed/3 skipped baseline in CLAUDE.md, consistent
with the intervening commits (job-dependency-graph research/handoffs, zone
work) adding tests since that baseline was taken, not a regression from
this change.

No live deploy or VM mutation was made or attempted (worktree has no VM
credentials at all, so this was never in reach here regardless of the
handoff's scope limit). No permission refusal encountered other than the
expected `.env`-missing message from `vm-ssh.sh` itself.

