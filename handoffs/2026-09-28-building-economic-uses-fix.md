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

