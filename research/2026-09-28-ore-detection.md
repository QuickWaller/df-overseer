# Ore/gem-worthiness ground truth vs `economic_uses`/`metal_ore`

Date: 2026-09-28. Read-only research against VM 103's live raws and running
DFHack process, plus a local df-structures/DFHack source clone
(`/tmp/df-structures-1dd01aad64219afa0578f1328cf15bd0c6006d5a`,
`/tmp/dfhack-53.16-r1.1`).

## Headline finding

`df-overseer-surface.lua`'s `vein_material` had two independent bugs, not
one, and the orchestrator's MINERAL-vs-STONE fallback hypothesis is also
wrong on its own terms. The correct, already-built, DFHack-native check is
`inorganic_raw:isOre()` (and `.material:isGem()` for gems), both live-tested
on this fort and both working exactly as expected.

## 1. The raw tag (ground truth, this world's actual file)

`/opt/df/game/data/vanilla/vanilla_materials/objects/inorganic_stone_mineral.txt`,
`[INORGANIC:HEMATITE]` block:

```
[METAL_ORE:IRON:100]
[IS_STONE]
```

Confirmed: this world uses the standard vanilla tag, `[METAL_ORE:<METAL>:<chance>]`,
to mark ore. No world-specific/generated raw override; the running fort reads
the vanilla file directly (no per-save `raw/` copy exists under
`save/current` or `save/region2` — checked, none found).

## 2. Why the code's reads came back empty: two separate bugs

Per `df.matgloss.xml`'s `inorganic_raw` struct-type, both `metal_ore` and
`economic_uses` are **top-level fields of `inorganic_raw` itself**, not
nested under its `.material` sub-compound:

```xml
<compound name='metal_ore'>          <!-- top-level, IS the METAL_ORE tag data -->
    <stl-vector ... name='str' original-name='smelt_inorganic_token'/>
    <stl-vector type-name='int16_t' name='mat_index' original-name='smelt_inorganic'/>
    <stl-vector type-name='int16_t' name='probability' original-name='smelt_inorganic_chance'/>
</compound>
<stl-vector type-name='int32_t' name='economic_uses' original-name='involved_reaction'/>
<compound type-name='material' name='material'/>
<custom-methods><cmethod name='isOre'/></custom-methods>
```

Live-tested against hematite (index 182) on the running fort:

```
i.material.economic_uses         -- ERRORS: "Cannot read field material.economic_uses: not found"
i.economic_uses (top-level)      -- 0 entries (real, not a bug -- see below)
i.metal_ore                      -- a compound (userdata), not a vector itself
i.metal_ore.mat_index            -- 1 entry: [156] (IRON), probability [100]
i:isOre()                        -- true
```

- **`inorg.material.economic_uses`** (what the code actually read) doesn't
  exist as a path at all -- it errors, it doesn't return an empty vector.
  Wrong nesting: `economic_uses` lives on `inorganic_raw` directly.
- **`.inorganic.metal_ore`** (the field the handoff says was tried directly
  and came back "0 entries") is a *compound*, not a vector -- `#metal_ore`
  on the compound itself does not give the tag count. The real vector is
  one level down, `metal_ore.mat_index`, and it correctly holds 1 entry
  for hematite. This is an access-pattern bug, not a missing-field one.
- **`economic_uses` (top-level, correctly read) is genuinely empty for
  hematite** -- confirmed live, not a bug. `economic_uses` means
  "reactions that reference this material" (`involved_reaction`), a
  runtime/discovery-driven bookkeeping field, unrelated to whether a
  mineral is ore. Even read correctly, it was never the right signal.

## 3. The correct live-readable mechanism: `isOre()` / `isGem()`

`inorganic_raw` is declared `custom-methods='true'` with a `cmethod
name='isOre'`, which DFHack's codegen exposes directly to Lua as a callable
method on the struct instance -- no manual vector-length arithmetic needed.
This is the exact mechanism DFHack's own bundled `prospector` plugin uses
(`plugins/prospector.cpp:239`, `printVeins`):

```cpp
if (gloss->material.isGem())      ores/gems/rest classification
else if (gloss->isOre())
else ...
```

Live-tested on VM 103 against a spread of materials:

| material | isOre() | isGem() | material_class |
|---|---|---|---|
| HEMATITE | true | false | MINERAL |
| NATIVE_GOLD | true | false | MINERAL |
| MICROCLINE | false | false | MINERAL |
| KAOLINITE | false | false | MINERAL |

Recommended Lua, replacing the `economic_uses` block in
`df-overseer-surface.lua`:

```lua
local ok_ore, is_ore = pcall(function() return inorg:isOre() end)
local ok_gem, is_gem = pcall(function() return inorg.material:isGem() end)
if not ok_ore or not ok_gem then
  return {ok = true, material_class = mclass, mineral_name = name, vein_status = "unknown",
    error = "isOre/isGem unreadable: " .. tostring(is_ore) .. "/" .. tostring(is_gem)}
end
local economic = is_ore or is_gem
```

## 4. The orchestrator's MINERAL-vs-STONE hypothesis: a good filter, not a proxy for ore

`material_class == MINERAL` correctly separates vein-event tiles from
ordinary layer stone (that's what it's for -- `tiletype_material`, not a
material property). But it does **not** distinguish ore from non-ore within
veins: MICROCLINE and KAOLINITE are both `MINERAL`-class vein tiles and both
`isOre() == false`. Using MINERAL-vs-STONE alone would flag every vein
tile, ore or not, as worth mining before smoothing -- exactly the
false-positive the "economic" sub-classification was trying to avoid, just
achieved by the wrong field. Verdict: keep `material_class == MINERAL` as
the existing "is this a vein tile at all" gate (it's fine for that), but
`ore_or_gem` itself must come from `isOre()`/`isGem()`, not from
`material_class` and not from `economic_uses`.

## Not verified

- Whether `isOre()`/`isGem()` are the exact method names DFHack's Lua
  wrapper exposes on every DFHack build (checked against the specific
  clone versions on disk, `dfhack-53.16-r1.1` matched to this world's
  df-structures snapshot, and confirmed live on VM 103's actual running
  process -- so this is live-verified, not just source-read, for this
  fort's exact DFHack build).
- The C++ implementation source for `df::inorganic_raw::isOre()` itself
  (the codegen'd custom-method body) was not found in the local
  df-structures tarball snapshot; only the XML declaration and the legacy
  `t_matglossInorganic::isOre()` wrapper in `Materials.cpp` were found.
  This does not weaken the finding: the live call was tested directly
  against the running game and returned correct, raw-file-consistent
  results for both ore and non-ore materials.

## Recommendation

Fix `df-overseer-surface.lua`'s `vein_material` (and any other classifier
using `economic_uses`/`metal_ore`) to call `inorg:isOre()` and
`inorg.material:isGem()` directly, keep `material_class == MINERAL` only as
the pre-filter for "is this a vein tile," and drop `economic_uses` entirely
as an ore signal -- it answers "has a reaction been registered against this
material," not "is this ore."
