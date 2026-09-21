# What every workshop and furnace kind needs

Date: 2026-09-21. Read-only research for
`handoffs/2026-09-21-building-requirements-research.md`, feeding
`docs/BUILDING-TOOL.md` open questions 3 (material filters) and 4 (what a kind
needs to be useful). **The live game was not called.** Files on VM 103 were
read read-only over SSH as `df`; the DF wiki was read through WebFetch.

## Answer first

1. **32 kinds are covered: 25 workshops and 7 furnaces**, every entry of
   `building_db_raw` in quickfort's `build.lua` with `type` Workshop or
   Furnace (counted by reading lines 860-931, not a parsed count). The brief
   said "about 30 workshops"; the table has 25 (Kennels, Siege Workshop, Quern,
   Millstone, Soap Maker and Screw Press included). The three siege engines
   (Ballista, Catapult, Bolt Thrower) are in the same table and are listed in a
   short appendix, not counted. Nothing in scope is "not found".
2. **`dfhack.buildings.getFiltersByType` does NOT return the game's own list.**
   For every standard kind it returns DFHack's own hand-written tables in
   `hack/lua/dfhack/buildings.lua` (`workshop_inputs`, `furnace_inputs`,
   verified by reading the file). Only the two Custom kinds (Soap Maker, Screw
   Press) come from the game's raws, through `df.building_def` `build_items`.
   Twelve-odd standard kinds agree with the wiki on the class of material
   (Ashery, Dyer, Forge, Siege, Mechanic, Millstone), none disagrees, but the
   quantity is unset in the table for every kind except the Siege Workshop
   (3). So the answer to "what does this kind need to build" is "DFHack's
   filter list, agreeing with the wiki where checked", not "the game's list".
3. **Most kinds need exactly one generic building-material item.** The filter
   is `flags2.building_material` plus `non_economic` (plus `fire_safe` for the
   four fuel furnaces, `magma_safe` for the three magma ones). Exceptions that
   need specific pre-made items, and so a bootstrapping order: Metalsmith's
   Forge and Magma Forge (an anvil), Ashery (a block, a barrel, a bucket),
   Dyer's Shop (a barrel and a bucket, no building material at all), Quern (a
   quern), Millstone (a millstone and a mechanism), Screw Press (2
   mechanisms), Soap Maker (a bucket and a worthless stone).
4. **Operating labor: DFHack ships a per-kind list for 17 kinds** in
   `hack/lua/plugins/orders.lua` (`WORKSHOP_LABORS`, `FURNACE_LABORS`), and it
   **resolves the open ConstructBlocks disagreement in `BUILDING-TOOL.md`**:
   the Mason's Workshop's operating labors are `STONECUTTER` and
   `STONE_CARVER`, and `MASON` is not among them. The wiki (v53.16) says the
   same ("masonry ... unused" at the workshop). So
   `df-overseer-workshop.lua`'s `mason` entry (`labor = "MASON"`) is very
   likely the wrong labor to count for staffing that workshop. `MASON` is
   probably the labor to *construct* with stone (wiki Smelter page), which is a
   different question; flagged `prior`. Fifteen kinds have no DFHack list (ten workshops and five of
   the furnaces); their labors below are `prior`. One list is misattributed:
   the Soap Maker inherits the Screw Press's (`Custom`) list.
5. **Two other things worth acting on.** quickfort's placement check has no
   magma test at all (a Magma Forge placed with no magma beneath it builds and
   then idles), and applying a `#build` with buildingplan disabled and no
   materials in stock makes the building silently disappear (quickfort's own
   warning text). Both are in the hazards.

## Method and flags

`verified` = read by me this session in a file on this install
(`/opt/df/game/...`, cited by path and line) or in DFHack's own docs at the
installed version. `prior` = anything from the DF wiki (page banner v53.16,
matching this install, but each page was summarised by a small model through
WebFetch, so quantities and wording are second-hand), from repo documents I did
not re-derive, or from memory. Where a repo document records a live measurement
I did not repeat, the entry says `prior (repo record)`.

Source keys used in the tables and YAML:

| Key | Source |
|---|---|
| S1 | `hack/lua/dfhack/buildings.lua`: `building_inputs` 34-198, `furnace_inputs` 202-210, `workshop_inputs` 214-294, `getFiltersByType` 432-443, custom kinds `get_custom_inputs` (reads `df.building_def.build_items`) |
| S2 | `hack/scripts/internal/quickfort/build.lua`: tile checks 38-217, workshop and furnace table 860-931, footprint defaults 1073-1081, buildingplan warning 1326-1331 |
| S3 | `hack/lua/plugins/orders.lua`: `WORKSHOP_LABORS` 465-485, `FURNACE_LABORS` 488-491 (labors a workshop profile can block) |
| S4 | `hack/lua/dfhack/workshops.lua`: `jobs_furnace` 30-90, `jobs_workshop` 91-467. **Partial**: it has no entry for Craftsdwarfs, Bowyers, Forges, Still, Ashery, Kennels, Quern, Millstone, and one line (`defaults={item_type=SKIN_TANNED}`, Leatherworks) references an undefined global, so it is not maintained as authoritative |
| S5 | `data/vanilla/vanilla_buildings/objects/building_custom.txt` (Soap Maker, Screw Press) |
| S6 | `data/vanilla/vanilla_reactions/objects/*.txt`, `[BUILDING:...]` lines counted by grep on 2026-09-21 |
| S7 | DFHack docs installed under `hack/docs/docs`: `dev/Lua API.txt` (getFiltersByType, constructBuilding), `tools/buildingplan.txt`, `guides/quickfort-user-guide.txt` |
| S8 | `hack/init/dfhack.tools.init` (`enable buildingplan` at startup) |
| W | DF wiki page for the kind, banner v53.16, read 2026-09-21 via WebFetch |
| R1 | `docs/BUILDING-TOOL.md` |
| R2 | `scripts/dfhack/df-overseer-workshop.lua` header comments (record of an earlier live `getFiltersByType` call on five kinds) |
| R3 | `doctrine/seed.yaml` |
| R4 | `research/2026-09-18-schema-extraction-static.md` section 8 (record of a live `df.unit_labor` and `df.workshop_type` enum read) |
| M | memory / general knowledge, no source opened |

The class shorthand: **BM** = one item matching `flags2.building_material`
(any boulder, log or block, and bars if the building tool allows; per S7
buildingplan the defaults are blocks, boulders and logs on, bars off) and
`non_economic`. **FS** adds `fire_safe`, **MS** adds `magma_safe`. R2 records a
live call returning exactly the BM filter for Still, Kitchen, Masons,
Mechanics and Carpenters, accepting BOULDER, WOOD and BLOCKS.

## Table by kind

Size is quickfort's footprint (S2: default 3x3, overrides below). "Labors" are
operating labors: S3 where marked (s3), otherwise `prior`. Quantity is unset in
S1 for every row unless stated (the `job_item` default of 1 is not verified;
the wiki says "one" for several kinds).

| Kind (enum, qf key) | Size | To build (S1 unless noted) | Operating labors | Needs to be useful | Idle if |
|---|---|---|---|---|---|
| Carpenters `wc` | 3x3 | BM | CARPENTER, TRAPPER (s3) | logs | no logs, nobody on CARPENTER |
| Farmers `ww` | 3x3 | BM | PROCESS_PLANT, MAKE_CHEESE, MILK, SHEARER, SPINNER, PAPERMAKING (s3) | crops, milk, wool; empty bags, barrels, buckets or vials per job (W) | no input or no empty container |
| Masons `wm` | 3x3 | BM | STONECUTTER, STONE_CARVER (s3); not MASON | hard stone boulders (clay boulders do not work, W) | nobody on STONECUTTER/STONE_CARVER |
| Craftsdwarfs `wr` | 3x3 | BM | STONE_CRAFT, WOOD_CRAFT, BONE_CARVE, WAX_WORKING, BOOKBINDING, EXTRACT_STRAND, LEATHER, CLOTHESMAKER, METAL_CRAFT, GLASSMAKER (s3) | stone, wood, bone, cloth, leather, wax | no crafting labor enabled |
| Jewelers `wj` | 3x3 | BM | CUT_GEM, ENCRUST_GEM (s3) | rough gems; gems plus a finished good to encrust | no rough gems, nobody on CUT_GEM |
| Metalsmiths Forge `wf` | 3x3 | 1 anvil (fire_safe) + FS | FORGE_WEAPON, FORGE_ARMOR, FORGE_FURNITURE, METAL_CRAFT, TRAPPER (s3) | metal bars; fuel (charcoal or coke) per job except studding (W) | no fuel, no bars, no smith |
| MagmaForge `wv` | 3x3 | 1 anvil (magma_safe) + MS | as Forge (s3) | metal bars; magma at depth 4/7 or more beneath one of the 8 outer tiles, no fuel (W) | magma below 4/7, even briefly (W) |
| Bowyers `wb` | 3x3 | BM | BOWYER (prior, R4 name) | wood or bone | nobody on BOWYER |
| Mechanics `wt` | 3x3 | BM | MECHANIC (prior) | hard stone boulders for mechanisms (S4); table, mechanism, chain for a traction bench | no stone, nobody on MECHANIC |
| Siege `ws` | 5x5 | 3 x BM (explicit quantity) | SIEGECRAFT (prior) | wood; arrowheads | nobody on SIEGECRAFT |
| Butchers `wu` | 3x3 | BM | BUTCHER, DISSECT_VERMIN (s3) | butcherable animals or corpses within about 20 tiles, same z (W) | none in range |
| Leatherworks `we` | 3x3 | BM | LEATHER (prior) | tanned hides | no tanned hides |
| Tanners `wn` | 3x3 | BM | TANNER (prior) | raw hides; raw reaction MAKE_PARCHMENT needs milk of lime (S6, W) | no hides |
| Clothiers `wk` | 3x3 | BM | CLOTHESMAKER (prior) | cloth outside bins (W) | cloth only in bins |
| Loom `wo` | 3x3 | BM | WEAVER (prior) | thread (plant, silk, yarn) | no thread |
| Dyers `wd` | 3x3 | 1 empty barrel + 1 bucket (lye_milk_free), **no BM** | DYER (prior) | dye plus thread or cloth; 68 raw dye reactions (S6) | no dye, no thread |
| Fishery `wh` | 3x3 | BM | FISH, CLEAN_FISH, DISSECT_FISH (s3) | FISH_RAW; animal traps for live catch (W) | no raw fish, nobody on CLEAN_FISH |
| Still `wl` | 3x3 | BM | BREWER, HERBALIST (s3) | plant with DRINK_MAT plus an empty food-storage container (barrel or rock pot, R3) | no empty container, no brewable plant |
| Kitchen `wz` | 3x3 | BM | COOK (prior, R1 measured PrepareMeal to COOK) | solid ingredients; seeds must be excluded in kitchen settings (R3) | nobody on COOK, or seeds cooked |
| Ashery `wy` | 3x3 | 1 BLOCK + 1 empty barrel + 1 bucket (lye_milk_free) | POTASH_MAKING, LYE_MAKING (s3) | ash, lye, quicklime per job; empty buckets | no ash, nobody on either labor |
| Kennels `k` | **5x5** | BM | ANIMALTRAIN (prior) | animal trap holding vermin (W) | no trapped vermin |
| Quern `wq` | **1x1** | 1 QUERN item | MILLER, PAPERMAKING (s3) | millable plants; empty bags for seed byproducts (W) | no plants, mixed inputs |
| Millstone `wM` | **1x1** | 1 MILLSTONE item + 1 mechanism | MILLER, PAPERMAKING (s3) | plants, an empty bag per job, 10 power units (W) | unpowered (W) |
| Screw Press (Custom 1) `wp` | **1x1** | 2 TRAPPARTS (S5) | PRESSING, PAPERMAKING (s3); BUILD_LABOR MECHANIC (S5) | seed paste, olives, honeycomb; empty jugs (S5 tooltip) | no jugs, no paste |
| Soap Maker (Custom 0) `wS` | 3x3 | 1 empty bucket + 1 worthless stone, stone only (S5) | SOAP_MAKER (prior; S5 BUILD_LABOR). S3 wrongly gives it PRESSING, PAPERMAKING | tallow or oil, plus lye (S5 tooltip) | no lye, no fat |
| Wood Furnace `ew` | 3x3 | FS | BURN_WOOD (prior) | logs; no fuel (W). S4: jobs MakeCharcoal, MakeAsh | no logs, nobody on BURN_WOOD |
| Smelter `es` | 3x3 | FS | SMELT (prior) | ore, flux; fuel (S4: smelt jobs carry a coal item) | no fuel |
| Magma Smelter `el` | 3x3 | MS | SMELT (prior) | ore; **no fuel** (S4: `addSmeltJobs(c_jobs, false)`); magma 4/7 (W) | no magma |
| Glass Furnace `eg` | 3x3 | FS | GLASSMAKER (prior) | sand bags (S4: CollectSand job), fuel, pearlash for clear glass (W) | no sand, no fuel |
| Magma Glass Furnace `ea` | 3x3 | MS | GLASSMAKER (prior) | sand; no fuel; magma | no magma, no sand |
| Kiln `ek` | 3x3 | FS | SMELT, POTTERY, GLAZING (s3, FURNACE_LABORS) | clay (S4: CollectClay), fuel; empty bags for plaster and quicklime (W) | no clay, no fuel |
| Magma Kiln `en` | 3x3 | MS | SMELT, POTTERY, GLAZING (s3) | clay; no fuel; magma | no magma, no clay |

Appendix, outside the brief's scope but in the same table (S1, S2): Ballista `ib`
3 x BALLISTAPARTS; Catapult `ic` 3 x CATAPULTPARTS; Bolt Thrower `it` 1
BOLT_THROWER_PARTS + an empty BIN + a mechanism + a chain. All 3x3.

## Hazards, seeding the gotcha list

Each is titled by its condition. Source and flag in brackets.

1. **Applying a `#build` with buildingplan disabled and the materials not in
   stock: the building disappears.** quickfort prints exactly this warning
   (S2:1326-1331, verified). buildingplan is enabled at DFHack start (S8,
   verified in the file); whether it is on in the running game was not checked.
2. **Placing any workshop on a footprint containing magma, hidden tiles, a
   building, or liquid deeper than 1: refused.** quickfort's `is_valid_tile_base`
   (S2:38-47, verified). Reading `liquid_type == true` as magma is my
   interpretation. Shape must also be floor, boulder, pebbles, twig, sapling
   or shrub (S2:49-58, verified).
3. **Placing a Magma Forge, Magma Smelter, Magma Glass Furnace or Magma Kiln
   with quickfort: no magma check is made.** The four use the generic tile
   check (S2, verified by reading; no magma function exists in the file).
   The building will construct and then sit idle if magma is not at depth 4/7
   or more beneath an outer tile (W, prior). Site finding must test magma
   itself.
4. **Building a Metalsmith's Forge or Magma Forge with no anvil in stock: it
   cannot start** (S1:220-237, verified). Where anvils come from in a fort with
   none was not verified (prior: made at a forge, so only embark stock or
   trade can seed it).
5. **Building an Ashery from rough stone or logs: only a finished block is
   accepted**, plus an empty barrel and a bucket (S1:251-268 verified; W agrees).
6. **Building a Dyer's Shop expecting a building material: it takes a barrel
   and a bucket and nothing else** (S1:269-282, verified; W agrees). A count of
   "boulders, logs, blocks" gives a false gap for this kind.
7. **Building a Soap Maker from logs or blocks: the second input is worthless
   stone only** (`[BUILDMAT][WORTHLESS_STONE_ONLY]`, S5, verified in the raws;
   how DFHack translates those two tags into a filter was not read). It also
   needs an empty bucket. `BUILD_LABOR` is SOAP_MAKER, so someone with that
   labor must construct it (S5, verified).
8. **Building a Quern, Millstone or Screw Press with none in stock: it needs a
   pre-made item** (a quern or millstone: S1:248, 283-293; 2 mechanisms: S5).
   The quern and millstone are made at a Masons' workshop (S4 jobs
   ConstructQuern, ConstructMillstone, verified), mechanisms at a Mechanics'
   workshop. So the order Carpenter (barrels, buckets) then Mason then
   Mechanic then these is forced.
9. **Counting MASON as the operating labor of a Mason's Workshop: it is
   probably the wrong labor.** S3 lists STONECUTTER and STONE_CARVER (verified);
   the wiki says masonry is unused there (prior); S4 lists ConstructBlocks under
   the Mason's shop, and `BUILDING-TOOL.md` measured ConstructBlocks mapping to
   STONECUTTER (repo record). Three sources agree; none is a live staffing test.
10. **Assuming a labor list exists for every kind: it does not.** S3 returns
    `{}` for Bowyers, Mechanics, Siege, Leatherworks, Tanners, Clothiers, Loom,
    Kennels, Kitchen, Dyers and the five non-kiln furnaces (verified by
    reading), so quickfort's `labor` and `labor_mask` properties are a no-op for
    those kinds. **It maps every `Custom` workshop to PRESSING and PAPERMAKING**
    (the comment says it is written for the Screw Press only), so the Soap Maker
    gets the wrong list and `labor=SOAP_MAKER` on it would be applied against a
    profile that does not contain that labor. The kiln list includes SMELT, which is the "Furnace Operating"
    labor in the wiki's wording (prior).
11. **Reading `getFiltersByType` as the game's list.** It is DFHack's table,
    with `quantity` unset (S1, verified). It can drift from the game on a
    version bump. Custom kinds are the exception and read the raws (S1).
12. **Using `dfhack.buildings.constructBuilding` and expecting the UI's
    checks.** DFHack's docs say it "does less environment constraint checking"
    (S7, verified). The tile checks come from quickfort, not from the call.
13. **Bars as building material: allowed by the filter class, off by default in
    buildingplan** (S7, verified: "bars" default false). A fort with only bars
    will show a gap under buildingplan while the raw filter says satisfied.
14. **Passing a Custom kind's `custom` index.** quickfort hard-codes 0 for the
    Soap Maker and 1 for the Screw Press (S2:911-916, verified). The index is
    the order in `building_custom.txt`; a raws change re-numbers it.
15. **Kind tokens with an apostrophe** are refused by the MCP server today
    (R1, prior repo record). The enum names (`Masons`, `Craftsdwarfs`) avoid it.
16. **Kitchen with seed items not excluded: seeds get cooked** (R3 doctrine,
    prior; R2 has the read-only check).
17. **Still with no empty food-storage container: the brew job never runs.**
    The container may be a rock pot, not only a barrel (R3, verified from the
    raws by an earlier stream; I did not re-read the reaction).
18. **Kiln without a Clay collection zone, Glass Furnace without a Sand zone:
    the CollectClay and CollectSand jobs have no source.** The zone types exist
    in quickfort's zone table (`SandCollection`, `ClayCollection`, S2 sibling
    `zone.lua:115,127`, verified). That the jobs need them is from the wiki
    (prior). The Kiln also hosts 13 raw reactions for jugs, large pots and
    bricks (S6, verified), so it is the source of clay food-storage containers.
19. **Millstone built unpowered or powered from below: idle or never
    completes** (W, prior, "must be powered from above or from the side";
    10 power units).
20. **Loom with automatic web collection on and open caverns: weavers die**
    (W, prior). **Clothiers ignore cloth stored in bins** (W, prior).
21. **Fuel furnaces with no charcoal or coke: idle.** Verified only in that S4's
    Smelter jobs carry a coal item and the magma variant's do not. The Wood
    Furnace itself needs no fuel and burns logs (W, prior), so building it
    competes with building material for logs.
22. **`max_general_orders` reads 5 on this install, not the wiki's 10** (TRAPS.md,
    one incomplete sample; prior repo record). Not tested per kind.
23. **Manager work orders never run without a Manager** (CLAUDE.md, prior repo
    record), so "the workshop is built, queue a job" is a second step for every
    kind above.
24. **A workshop restricted to a burrow with materials outside it shows all
    options red** (W Smelter page, prior).

## What could not be verified

- **Nothing was run.** No building was placed, no live filter call was made,
  so every "needs" row is from files and pages, not from a build. The five
  kinds the repo's tools have built (Still, Kitchen, Mason, Mechanic,
  Carpenter) carry R2's record of a live filter read that I did not repeat.
- **The `job_item` default quantity.** S1's table leaves `quantity` unset;
  the game's own quantity for a workshop (1 or 3) is not in any file on the
  install I could read (the game binary holds it). Wiki text says "one" for
  Craftsdwarfs, Fishery, Jeweler, Mechanic and Kennels and 3 for the Siege
  Workshop, which matches S1 for the Siege Workshop only.
- **The game's own build list.** It lives in the game binary, not the raws
  (BUILDING-TOOL.md, checked earlier: the raws define only two workshops). So
  "does getFiltersByType match the game" is answered by agreement with the
  wiki on about a dozen kinds, not by a diff.
- **Operating labors for 15 kinds** (no S3 entry, plus the Soap Maker's wrong one): from my knowledge and R4's
  enum names. The labor-to-workshop mapping for those is `prior`, not read.
  The offline production-graph stream (BUILDING-TOOL.md open question 1) is the
  designated source.
- **What quickfort does with `[BUILDMAT][WORTHLESS_STONE_ONLY]`** in a custom
  kind's `build_items` (not read: it is in the C++ side of `df.building_def`).
- **Whether buildingplan is enabled in the running game**, and its
  per-fort material settings (persisted in the save, not readable offline).
- **Wiki quantities and pitfalls**: each page was summarised by a small model.
  Two were internally odd: it named the Mason's page "Stoneworker's Workshop"
  and the Kennels page "Vermin Catcher's Shop"; the material and labor claims
  were cross-checked against S1 and S3 where those exist.
- **Adjacency requirements**: none found in any source for any kind beyond the
  Millstone's power direction and the magma variants' magma tile. This is
  "nothing found", not "confirmed none".
- **Water access**: no kind in scope needs water to operate in any source
  read. Same caveat.
- **Not read**: DFHack `orders`/`workorder` tool docs, `hack/data/orders/*.json`
  (they name jobs but not workshops), `advfort.lua`, the wiki pages for
  Wood Furnace's labor caption, and `df.unit_labor.attrs[...].caption` values
  (needs the live game).

## Machine-readable entries

Fields per kind: `token` (the enum subtype, which survives the MCP layer),
`qf_key`, `type`, `size`, then `build`, `labors`, `useful`, `idle_if`,
`hazards` (numbers refer to the list above). Every value has a `[source(s),
flag]` in the trailing comment or the `src`/`conf` keys. `conf` is `verified` or
`prior`; a mixed entry says which field is which.

```yaml
# schema: kind -> {token, qf_key, type, size, build, labors, useful, idle_if, hazards}
# every field carries src (keys from the Method table) and conf (verified | prior)
kinds:
  Carpenters:
    qf_key: wc
    type: Workshop
    size: [3, 3]
    size_src: S2:1079-1081
    size_conf: verified
    build: {filters: [{class: BM}], src: S1:215, conf: verified}
    labors: {list: [CARPENTER, TRAPPER], src: S3, conf: verified}
    useful: {inputs: [logs], src: W, conf: prior}
    idle_if: [no logs, nobody on CARPENTER]
    hazards: [1, 2, 13, 23]
  Farmers:
    qf_key: ww
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:216, conf: verified}
    labors: {list: [PROCESS_PLANT, MAKE_CHEESE, MILK, SHEARER, SPINNER, PAPERMAKING], src: S3, conf: verified}
    useful: {inputs: [crops, milk, wool], containers: [empty bag, barrel, bucket, vial per job], src: W, conf: prior}
    idle_if: [no input, no empty container]
    hazards: [1, 2, 13, 23]
  Masons:
    qf_key: wm
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:217, conf: verified}
    labors: {list: [STONECUTTER, STONE_CARVER], not: [MASON], src: S3, conf: verified, note: "wiki agrees (prior); see hazard 9"}
    useful: {inputs: [hard stone boulders], note: "clay boulders do not work", src: [S4, W], conf: [verified, prior]}
    idle_if: [no stone, nobody on STONECUTTER or STONE_CARVER]
    hazards: [1, 2, 9, 13, 23]
  Craftsdwarfs:
    qf_key: wr
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:218, conf: verified}
    labors: {list: [STONE_CRAFT, WOOD_CRAFT, BONE_CARVE, WAX_WORKING, BOOKBINDING, EXTRACT_STRAND, LEATHER, CLOTHESMAKER, METAL_CRAFT, GLASSMAKER], src: S3, conf: verified}
    useful: {inputs: [stone, wood, bone, cloth, leather, wax], src: W, conf: prior}
    idle_if: [no crafting labor enabled]
    hazards: [1, 2, 13, 23]
  Jewelers:
    qf_key: wj
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:219, conf: verified}
    labors: {list: [CUT_GEM, ENCRUST_GEM], src: S3, conf: verified}
    useful: {inputs: [rough gems, cut gems plus a finished good to encrust], src: [S4, W], conf: [verified, prior]}
    idle_if: [no rough gems, nobody on CUT_GEM]
    hazards: [1, 2, 13, 23]
  MetalsmithsForge:
    qf_key: wf
    type: Workshop
    size: [3, 3]
    build: {filters: [{item: ANVIL, flags: [fire_safe]}, {class: BM, flags: [fire_safe]}], src: S1:220-228, conf: verified}
    labors: {list: [FORGE_WEAPON, FORGE_ARMOR, FORGE_FURNITURE, METAL_CRAFT, TRAPPER], src: S3, conf: verified}
    useful: {inputs: [metal bars], fuel: [charcoal or coke per job, except studding], src: W, conf: prior}
    idle_if: [no fuel, no bars, no smith]
    hazards: [1, 2, 4, 13, 23]
  MagmaForge:
    qf_key: wv
    type: Workshop
    size: [3, 3]
    build: {filters: [{item: ANVIL, flags: [magma_safe]}, {class: BM, flags: [magma_safe]}], src: S1:229-237, conf: verified}
    labors: {list: [FORGE_WEAPON, FORGE_ARMOR, FORGE_FURNITURE, METAL_CRAFT, TRAPPER], src: S3, conf: verified}
    useful: {inputs: [metal bars], magma: "depth 4/7 or more under one of the 8 outer tiles; no fuel", src: W, conf: prior}
    idle_if: [magma below 4/7, even briefly]
    hazards: [1, 2, 3, 4, 13, 23]
  Bowyers:
    qf_key: wb
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:238, conf: verified}
    labors: {list: [BOWYER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [wood, bone], src: W, conf: prior}
    idle_if: [nobody on BOWYER]
    hazards: [1, 2, 10, 13, 23]
  Mechanics:
    qf_key: wt
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:239, conf: verified}
    labors: {list: [MECHANIC], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [hard stone boulders], traction_bench: [table, mechanism, chain or rope], src: [S4, W], conf: [verified, prior]}
    idle_if: [no stone, nobody on MECHANIC]
    hazards: [1, 2, 10, 13, 23]
  Siege:
    qf_key: ws
    type: Workshop
    size: [5, 5]
    size_src: S2:894-896
    size_conf: verified
    build: {filters: [{class: BM, quantity: 3}], src: S1:240, conf: verified}
    labors: {list: [SIEGECRAFT], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [wood, ballista arrowheads], src: [S4, W], conf: [verified, prior]}
    idle_if: [nobody on SIEGECRAFT]
    hazards: [1, 2, 10, 13, 23]
  Butchers:
    qf_key: wu
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:241, conf: verified}
    labors: {list: [BUTCHER, DISSECT_VERMIN], src: S3, conf: verified}
    useful: {inputs: [butcherable animals or corpses within about 20 tiles on the same z], src: W, conf: prior}
    idle_if: [none in range]
    hazards: [1, 2, 13, 23]
  Leatherworks:
    qf_key: we
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:242, conf: verified}
    labors: {list: [LEATHER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [tanned hides], src: W, conf: prior}
    idle_if: [no tanned hides]
    hazards: [1, 2, 10, 13, 23]
  Tanners:
    qf_key: wn
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:243, conf: verified}
    labors: {list: [TANNER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [raw hides], raw_reactions: [TAN_A_HIDE, MAKE_PARCHMENT], src: [S6, W], conf: [verified, prior]}
    idle_if: [no hides]
    hazards: [1, 2, 10, 13, 23]
  Clothiers:
    qf_key: wk
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:244, conf: verified}
    labors: {list: [CLOTHESMAKER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [cloth kept outside bins], src: W, conf: prior}
    idle_if: [cloth only in bins]
    hazards: [1, 2, 10, 13, 20, 23]
  Loom:
    qf_key: wo
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:247, conf: verified}
    labors: {list: [WEAVER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [thread], src: [S4, W], conf: [verified, prior]}
    idle_if: [no thread]
    hazards: [1, 2, 10, 13, 20, 23]
  Dyers:
    qf_key: wd
    type: Workshop
    size: [3, 3]
    build: {filters: [{item: BARREL, flags: [empty]}, {item: BUCKET, flags: [lye_milk_free]}], no_building_material: true, src: S1:269-282, conf: verified}
    labors: {list: [DYER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [dye, thread or cloth], raw_reactions: 68, src: [S4, S6], conf: verified}
    idle_if: [no dye, no thread]
    hazards: [1, 2, 6, 10, 13, 23]
  Fishery:
    qf_key: wh
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: S1:245, conf: verified}
    labors: {list: [FISH, CLEAN_FISH, DISSECT_FISH], src: S3, conf: verified}
    useful: {inputs: [FISH_RAW], live_catch: [animal traps], src: [S4, W, R3], conf: [verified, prior, prior]}
    idle_if: [no raw fish, nobody on CLEAN_FISH]
    hazards: [1, 2, 13, 23]
  Still:
    qf_key: wl
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: [S1:246, R2], conf: [verified, "prior (repo record)"]}
    labors: {list: [BREWER, HERBALIST], src: S3, conf: verified}
    useful: {inputs: [plant with DRINK_MAT], containers: [empty barrel or rock pot], src: R3, conf: "verified (earlier stream, from raws; not re-read)"}
    idle_if: [no empty container, no brewable plant]
    hazards: [1, 2, 13, 17, 23]
  Kitchen:
    qf_key: wz
    type: Workshop
    size: [3, 3]
    build: {filters: [{class: BM}], src: [S1:250, R2], conf: [verified, "prior (repo record)"]}
    labors: {list: [COOK], src: [R1, W], conf: prior, note: "no S3 entry; R1 measured PrepareMeal to COOK"}
    useful: {inputs: [solid food ingredients], setting: "exclude seeds from cooking", src: [R3, W], conf: prior}
    idle_if: [nobody on COOK, seeds not excluded]
    hazards: [1, 2, 10, 13, 16, 23]
  Ashery:
    qf_key: wy
    type: Workshop
    size: [3, 3]
    build: {filters: [{item: BLOCKS}, {item: BARREL, flags: [empty]}, {item: BUCKET, flags: [lye_milk_free]}], src: S1:251-268, conf: verified}
    labors: {list: [POTASH_MAKING, LYE_MAKING], src: S3, conf: verified}
    useful: {inputs: [ash, lye, quicklime per job], containers: [empty buckets], src: W, conf: prior}
    idle_if: [no ash, nobody on either labor]
    hazards: [1, 2, 5, 13, 23]
  Kennels:
    qf_key: k
    type: Workshop
    size: [5, 5]
    size_src: S2:860-862
    size_conf: verified
    build: {filters: [{class: BM}], src: S1:249, conf: verified}
    labors: {list: [ANIMALTRAIN], src: W, conf: prior, note: "no S3 entry; wiki also lists small-animal dissection and trapping"}
    useful: {inputs: [animal trap holding vermin], src: W, conf: prior}
    idle_if: [no trapped vermin]
    hazards: [1, 2, 10, 13, 23]
  Quern:
    qf_key: wq
    type: Workshop
    size: [1, 1]
    size_src: S2:865-867
    size_conf: verified
    build: {filters: [{item: QUERN}], src: S1:248, conf: verified}
    labors: {list: [MILLER, PAPERMAKING], src: S3, conf: verified}
    useful: {inputs: [millable plants, oil seeds, plant fibre], containers: [empty bags for seed byproducts], raw_reactions: [MILL_SEEDS_NUTS_TO_PASTE, MAKE_SLURRY_FROM_PLANT], src: [S6, W], conf: [verified, prior]}
    idle_if: [no plants, mixed inputs]
    hazards: [1, 2, 8, 13, 23]
  Millstone:
    qf_key: wM
    type: Workshop
    size: [1, 1]
    size_src: S2:868-870
    size_conf: verified
    build: {filters: [{item: MILLSTONE}, {item: TRAPPARTS, name: mechanism}], src: S1:283-293, conf: verified}
    labors: {list: [MILLER, PAPERMAKING], src: S3, conf: verified}
    useful: {inputs: [plants], containers: [empty bag per job], power: "10 units, from above or the side", src: W, conf: prior}
    idle_if: [unpowered]
    hazards: [1, 2, 8, 13, 19, 23]
  ScrewPress:
    token: "Custom:SCREW_PRESS"
    custom_index: 1
    qf_key: wp
    type: Workshop
    size: [1, 1]
    size_src: [S2:914-916, S5]
    size_conf: verified
    build: {filters: [{item: TRAPPARTS, quantity: 2}], src: S5, conf: verified, build_labor: MECHANIC}
    labors: {list: [PRESSING, PAPERMAKING], src: S3, conf: verified}
    useful: {inputs: [seed paste, olives, honeycomb], containers: [empty jugs], raw_reactions: [PRESS_OIL, PRESS_OIL_FRUIT, PRESS_HONEYCOMB, PRESS_PLANT_PAPER], src: [S5, S6], conf: verified}
    idle_if: [no jugs, no paste]
    hazards: [1, 2, 8, 13, 14, 23]
  SoapMaker:
    token: "Custom:SOAP_MAKER"
    custom_index: 0
    qf_key: wS
    type: Workshop
    size: [3, 3]
    build: {filters: [{item: BUCKET, flags: [empty]}, {class: "BUILDMAT, worthless stone only"}], src: S5, conf: verified, build_labor: SOAP_MAKER, note: "the BUILDMAT plus WORTHLESS_STONE_ONLY translation was not read"}
    labors: {list: [SOAP_MAKER], src: [R4, S5], conf: prior, note: "S3 gives Custom workshops PRESSING and PAPERMAKING, which is the Screw Press's list, wrong for this kind"}
    useful: {inputs: [tallow or oil, lye], raw_reactions: [MAKE_SOAP_FROM_TALLOW, MAKE_SOAP_FROM_OIL], src: [S5, S6], conf: verified}
    idle_if: [no lye, no fat]
    hazards: [1, 2, 7, 10, 13, 14, 23]
  WoodFurnace:
    qf_key: ew
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [fire_safe]}], src: S1:203, conf: verified}
    labors: {list: [BURN_WOOD], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [logs], fuel: none, jobs: [MakeCharcoal, MakeAsh], src: [S4, W], conf: [verified, prior]}
    idle_if: [no logs, nobody on BURN_WOOD]
    hazards: [1, 2, 10, 13, 21, 23]
  Smelter:
    qf_key: es
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [fire_safe]}], src: S1:204, conf: verified}
    labors: {list: [SMELT], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [ore, flux], fuel: [coal item on smelt jobs], src: [S4, W], conf: [verified, prior]}
    idle_if: [no fuel, burrow limit with materials outside]
    hazards: [1, 2, 10, 13, 21, 23, 24]
  MagmaSmelter:
    qf_key: el
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [magma_safe]}], src: S1:207, conf: verified}
    labors: {list: [SMELT], src: [R4, W], conf: prior}
    useful: {inputs: [ore], fuel: none, magma: "4/7 at an outer tile", src: [S4, W], conf: [verified, prior]}
    idle_if: [no magma]
    hazards: [1, 2, 3, 10, 13, 23]
  GlassFurnace:
    qf_key: eg
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [fire_safe]}], src: S1:205, conf: verified}
    labors: {list: [GLASSMAKER], src: [R4, W], conf: prior, note: "no S3 entry"}
    useful: {inputs: [sand bags], fuel: [charcoal or coke], jobs: [CollectSand], zone: "Sand collection zone", src: [S4, W, S2-zone], conf: [verified, prior, verified]}
    idle_if: [no sand, no fuel]
    hazards: [1, 2, 10, 13, 18, 21, 23]
  MagmaGlassFurnace:
    qf_key: ea
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [magma_safe]}], src: S1:208, conf: verified}
    labors: {list: [GLASSMAKER], src: [R4, W], conf: prior}
    useful: {inputs: [sand bags], fuel: none, magma: "4/7 at an outer tile (assumed same rule as the Magma Smelter)", src: W, conf: prior}
    idle_if: [no magma, no sand]
    hazards: [1, 2, 3, 10, 13, 18, 23]
  Kiln:
    qf_key: ek
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [fire_safe]}], src: S1:206, conf: verified}
    labors: {list: [SMELT, POTTERY, GLAZING], src: S3, conf: verified}
    useful: {inputs: [clay], fuel: [charcoal or coke], containers: [empty bags for plaster and quicklime], jobs: [CollectClay], zone: "Clay collection zone", raw_reactions: 13, src: [S4, S6, W], conf: [verified, verified, prior]}
    idle_if: [no clay, no fuel]
    hazards: [1, 2, 13, 18, 21, 23]
  MagmaKiln:
    qf_key: en
    type: Furnace
    size: [3, 3]
    build: {filters: [{class: BM, flags: [magma_safe]}], src: S1:209, conf: verified}
    labors: {list: [SMELT, POTTERY, GLAZING], src: S3, conf: verified}
    useful: {inputs: [clay], fuel: none, magma: "4/7 at an outer tile (assumed same rule as the Magma Smelter)", src: W, conf: prior}
    idle_if: [no magma, no clay]
    hazards: [1, 2, 3, 13, 18, 23]
```

The `size` for every kind without a `size_src` is the quickfort default of 3x3
(S2:1073-1081, verified). Line numbers in S1 are from the installed file as
read on 2026-09-21; a DFHack update will move them.
