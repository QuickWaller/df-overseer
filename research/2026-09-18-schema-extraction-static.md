# Feasibility audit: can this install's raws populate the production schema?

Date: 2026-09-18. Read-only research against VM 103's live install (SSH,
`df@`, key from `.env`, game root `/opt/df/game`, DF v0.53.16 linux64,
DFHack 53.16-r1.1). `dfhack.world.ReadPauseState()` returned `true` before
the two `dfhack-run lua` calls this session made (one enum-listing batch, one
repeat check) and `true` again after; nothing else touched the VM, no raw
file was written, no fort state changed. All reaction-file analysis below
was done against local copies of the four shipped reaction files, pulled
read-only via `scp` into this session's scratchpad and never modified.
Method follows `CLAUDE.md`'s rule of reading the actual install rather than
trusting docs; where DFHack's own shipped docs were silent (most of §1),
that absence is reported as a finding, not papered over.

Cites, and does not re-derive: `research/2026-09-18-production-graph.md`
(the schema's original design and its 3-table precursor), `research/
2026-09-18-production-figures.md` (wiki figures pass), `research/
2026-09-17-seed-ratios.md` (settled brew/seed yield figures).
`doctrine/seed.yaml`'s header supplies the `prior`/`verified`/`refuted`
status vocabulary used below; this audit also uses `research/2026-09-17-
seed-ratios.md`'s finer `verified_raws`/`community_prior` split where it
sharpens the point.

## Bottom line

**Three of the five tables have at least one column that cannot be
populated as designed, and the schema's own most important column
(`production_flow.consumption`) needs a fourth value the current three-way
enum does not have room for.**

- **`production_node.id` and `production_flow.node_id` (item type ×
  material) fail as a primary key for a real, large minority of rows.**
  41% of all `[PRODUCT:...]` lines across the shipped reaction files (67 of
  163) fix the item type but inherit the material from a reagent at run
  time (`GET_MATERIAL_FROM_REAGENT`), and one line inherits *both* item type
  and material (`GET_ITEM_DATA_FROM_REAGENT`). Every food/drink reaction
  this project actually cares about (brewing, mead, plant-to-bag, the paper
  press) is in this inherited-material bucket. A static extraction cannot
  emit a single node id for these rows; it must instead join against a
  hand-built "which materials can fill this reagent" lookup (§2).
- **`production_flow.consumption` is derivable, but the raws express four
  outcomes, not the three the schema names**, and the fourth
  (`[IMPROVEMENT]`-only reactions, no `[PRODUCT]` line at all) affects real
  reactions (glaze jug/pot/statue/craft, 4 of 159 vanilla reactions, plus
  the DFHack-plugin `reaction_spatter.txt` mechanism) that the current
  three-value enum simply has no slot for (§1).
- **`production_process.capacity_theoretical` is not derivable at all**,
  confirming `research/2026-09-18-production-graph.md` §2's finding again
  from a different angle (no reaction file, and now also no producing
  reaction at all for lye/potash, carries any duration or throughput
  figure).
- **`production_flow.unit` is derivable for the bulk-material item types
  (`BAR`, `POWDER_MISC`, `DRINK`, one `LIQUID_MISC` case) via
  `PRODUCT_DIMENSION`, but is genuinely absent from the raws for three
  pressed-liquid products** (oil/dye press, honeycomb press) and requires a
  join against item-raw `[SIZE:n]` for every `TOOL`-subtype product
  (jug, pot, wheelbarrow, minecart). Not "extractable," "extractable with a
  lookup," and "not derivable" all apply to different rows of the *same*
  column (§4).
- **The two free wins landed clean**: `ITEM_TOOL_WHEELBARROW` and
  `ITEM_TOOL_MINECART` in this install's `item_tool.txt` carry exact,
  literal `[SIZE:...]` and `[CONTAINER_CAPACITY:...]` tokens that match the
  wiki figures in `research/2026-09-18-production-figures.md` §1/§3.1
  digit-for-digit. Both promote to `verified_raws` (§8).
- **No cycle was found**, and the specific one the design worried about
  (ash/lye/potash feeding soap-making) cannot occur in the extractable
  static graph at all: nothing in the four shipped reaction files *produces*
  lye or potash, so they are raw-external inputs to this graph, not
  intermediate loop nodes (§9).

The rest of this report works through the brief's nine questions in order,
then gives a verdict for every column in all five tables.

## 1. `production_flow.consumption`: the reagent-tag vocabulary, verified

**Full reagent-side tag vocabulary found across all four shipped reaction
files** (`reaction_adv_carpenter.txt`, `reaction_dyes.txt`,
`reaction_other.txt`, `reaction_smelter.txt`; 159 `[REACTION:...]` blocks,
314 `[REAGENT:...]` lines total), by direct grep of local copies pulled from
`/opt/df/game/data/vanilla/vanilla_reactions/objects/` this session:

`PRESERVE_REAGENT` (120), `EMPTY` (82), `UNROTTEN` (67), `ANY_PLANT_MATERIAL`
(24), `HAS_MATERIAL_REACTION_PRODUCT` (23), `HAS_EDGE` (32),
`DOES_NOT_DETERMINE_PRODUCT_AMOUNT` (98, this project's earlier report did
not list it), `REACTION_CLASS` (13), `USE_BODY_COMPONENT` (10),
`ANY_BONE_MATERIAL` (8), `CONTAINS` (6), `FOOD_STORAGE_CONTAINER` (3),
`DOES_NOT_ABSORB` (3), `HAS_TOOL_USE` (3), `NOT_PRESSED` (4),
`NOT_IMPROVED` (4), `NOT_WEB` (1), `NO_EDGE_ALLOWED` (2), `FORCE_EDGE` (1),
`CAN_USE_ARTIFACT` (1), `CAN_USE_LOCATION_RESERVED` (1),
`HAS_WRITING_IMPROVEMENT` (1). **Confidence: verified from raws**, exact
counts from this session's grep, not a wiki claim.

**What DFHack's own installed docs say about these**: nothing, checked
directly. `grep -rli PRESERVE_REAGENT /opt/df/game/hack/docs/` turned up
only changelog/history pages that happen to contain the string
"PRESERVE_REAGENT" in a release note, not a definition; `hack/docs/library/
xml/SYNTAX.txt` (the df-structures XML format doc) and `hack/docs/docs/
guides/modding-guide.txt` (the one file that shows a worked `[REACTION:...]`
example, `MAKE_SIEGE_CROSSBOW`) neither defines `PRESERVE_REAGENT` nor any
of the container tags. **This install's own DFHack documentation is silent
on reagent-tag semantics; every semantic claim below is inferred from
raw-usage patterns on this install, cross-checked for internal consistency,
not read from an authoritative definition.** This is the honest limit the
brief asked to be named plainly.

**The pattern that does hold, with zero exceptions found in 314 reagent
lines**: whether `[PRESERVE_REAGENT]` is present on a reagent, and whether
that reagent's name also appears as the target of a `[PRODUCT_TO_CONTAINER:
name]` token elsewhere in the same `[REACTION:...]` block, together
determine the outcome:

| Pattern (both checked against this same session's local copies) | Real examples | Outcome |
|---|---|---|
| No `PRESERVE_REAGENT` at all | `plant` (brewing, papermaking), `tallow`/`oil`/`lye` (soap), `log` (carpentry, when not the tool reagent), every `BAR`-consuming smelter reagent | **consumed**: no ambiguity, the plant/material physically becomes the product |
| `PRESERVE_REAGENT` present, and the reagent's own name is the target of a `[PRODUCT_TO_CONTAINER:...]` on a product in the same block | `barrel/pot` in `BREW_DRINK_FROM_PLANT` (`reaction_other.txt:271-278`, `[PRODUCT_TO_CONTAINER:barrel/pot]` on the `DRINK` product), `bag` in `PROCESS_PLANT_TO_BAG`, `bucket` in `MAKE_MILK_OF_LIME`, `liquid container` in the three press reactions | **occupied_until_released**: the item is not destroyed but is re-purposed to hold the new product; the raws show *that* it becomes occupied, never *when* it is freed (that trigger, e.g. "freed once the drink is fully drunk," is engine behavior, not a raw token — flagged, not verified) |
| `PRESERVE_REAGENT` present, reagent's name never targeted by any `PRODUCT_TO_CONTAINER` in the block, usually paired with `[CONTAINS:x]` | `lye container`/`oil container`/`honey container`/`quicklime container`/`lime container` in the soap/lye/milk-of-lime reactions, `tool` in nearly every carpenter reaction (`[PRESERVE_REAGENT][HAS_EDGE]`) | **occupied_job**: held for the reaction's duration, returned unchanged (empty, in the `CONTAINS` case) once the job completes, no further linkage to the product |
| `PRESERVE_REAGENT` present, `[NOT_IMPROVED]` present, **no `[PRODUCT:...]` line in the whole reaction at all** | `jug`/`large pot`/`statue`/`craft` in the four `GLAZE_*` reactions (`reaction_other.txt`), the `object` reagent in DFHack's own `hack/raw/reaction_spatter.txt` | **a fourth case the schema's enum has no value for**: the reagent is modified in place via `[IMPROVEMENT:...]`, never destroyed, never re-occupied by a tracked product row, remains the same node identity throughout. 4 of 159 vanilla reactions (2.5%) land here; this is not a rounding error to absorb into `occupied_job`, since (unlike `occupied_job`) there is no `[PRODUCT]` row for `production_flow` to even attach a `direction='product'` entry to |

**`[EMPTY]` and `[CONTAINS:x]` are match-time preconditions, not consumption
signals**, verified by their co-occurrence pattern: `[EMPTY]` only ever
appears alongside `[PRESERVE_REAGENT]` (it constrains *which* candidate item
can fill the reagent slot — must currently hold nothing — not what happens
to it afterward), and `[CONTAINS:x]` likewise only appears with
`PRESERVE_REAGENT`, naming the sibling reagent (`x`) whose material the
container must currently hold. Neither tag by itself says consumed vs.
preserved; `PRESERVE_REAGENT`'s presence or absence is the load-bearing
signal, `EMPTY`/`CONTAINS` only narrow which item qualifies.

**`[DOES_NOT_DETERMINE_PRODUCT_AMOUNT]`** (98 occurrences, on almost every
container/preserved reagent) is a different axis entirely: it tells the
engine this reagent's own quantity field should not scale the product yield
(so a job needing exactly 1 barrel doesn't multiply output by "how many
barrels you had"). It does not bear on consumption at all; flagged here only
because the brief's phrase "reagent tags" would otherwise leave a reader
wondering why it wasn't used above.

**Bottom line for this column**: `consumption` is derivable for the three
schema values by a simple, well-evidenced rule (presence of
`PRESERVE_REAGENT` × whether the name is a `PRODUCT_TO_CONTAINER` target),
**but the schema needs a fourth value** (`modified_in_place`, or similar)
for the `[IMPROVEMENT]`-only case, and the *release trigger* for
`occupied_until_released` is never raw-stated, only inferable from general
DF mechanics knowledge, so that half of the semantics stays a documented
assumption, not a verified fact, even once the column is populated.

## 2. Node identity: does item type × material work as a primary key?

**No, not for a large minority of rows, and not for the rows this project
cares about most.** Read every `[PRODUCT:probability:quantity:item_type:
subtype:material_source:...]` line across all four files (163 total) and
classified the material-source field (5th colon-separated token):

| Material-source pattern | Count | Meaning | Node id resolvable at extraction time? |
|---|---|---|---|
| `PLANT_MAT:<species>:<part>` | 68 | Fixed, specific species/part named directly in the reaction (all 68 `reaction_dyes.txt` entries, one per species×dye-part combination) | Yes |
| `METAL:<alloy>` | 21 | Fixed alloy name (smelter alloy reactions) | Yes |
| `INORGANIC:<mat>` | 3 | Fixed | Yes |
| `COAL`, `PEARLASH` (bare) | 3 | Fixed | Yes |
| `GET_MATERIAL_FROM_REAGENT:<reagent>:<token>` | 67 | Material copied from whichever concrete item actually filled `<reagent>` at job time | **No** — the node id is parametric, not fixed |
| `GET_ITEM_DATA_FROM_REAGENT:<reagent>:<token>` | 1 | Both item type *and* material copied from the reagent | **No**, on both axes |

67 + 1 = 68 of 163 product lines (42%) cannot yield a concrete node id from
the reaction text alone. **This is not evenly spread across the domain**:
`reaction_adv_carpenter.txt` is 22/22 reagent-inherited (every piece of
furniture/tool made from `log` inherits whatever wood the carpenter used),
and, more importantly for this project, **`BREW_DRINK_FROM_PLANT`,
`BREW_DRINK_FROM_PLANT_GROWTH`, `MAKE_MEAD`, `PROCESS_PLANT_TO_BAG`, and
`MAKE_SLURRY_FROM_PLANT`** (drink, seeds, bagged leaves, paper pulp — the
entire food/drink/seed production chain this project's doctrine cares
about) **are all in the inherited bucket**, e.g. `[PRODUCT:100:5:DRINK:
NONE:GET_MATERIAL_FROM_REAGENT:plant:DRINK_MAT]` (`reaction_other.txt:277`).

**What this means for extraction**: a node id like `ITEM:DRINK` cannot be
emitted as one row. The extractor must instead cross-reference the
reagent's own matching constraint (here, `[HAS_MATERIAL_REACTION_PRODUCT:
DRINK_MAT]`, §3) against every material in the raws that actually declares
a `[MATERIAL_REACTION_PRODUCT:DRINK_MAT:...]` token (confirmed present on
all five brewable crops' structural materials in `plant_standard.txt`,
e.g. line 13 for plump helmet) to enumerate the *set* of concrete node ids
(`ITEM:DRINK:MATERIAL:PLUMP_HELMET_WINE`, `...:PIG_TAIL_ALE`, etc.) a single
reaction line can actually produce. **This is a real, non-trivial expansion
step the schema's flat `production_flow.node_id → production_node.id`
foreign key does not model**: one reaction-product row corresponds to *N*
concrete node rows, N determined by a join this schema has no table for.
Verified from raws: `plant_standard.txt` lines 13-14, 69-71, 117-118,
164-165, 282-283 (`MATERIAL_REACTION_PRODUCT:DRINK_MAT`/`SEED_MAT` on
plump helmet, pig tail, cave wheat, sweet pod, dimple cup — corroborating
`research/2026-09-17-seed-ratios.md`'s per-crop brewability table).

## 3. Classes: reagents-as-class, products-as-specific — tested against real data

**The claim holds directionally (products in this schema's food/drink scope
are indeed material-inherited from class-matched reagents, per §2), but the
raws express "class" through three unrelated mechanisms, not one token**,
so `production_class`'s vocabulary cannot be built from a single tag family:

1. **`[REACTION_CLASS:X]`** on a reagent, matched against a material's own
   `[REACTION_CLASS:X]` declaration (not read this session on the material
   side, inferred from the reagent-side usage pattern and the standard DF
   raw-modding convention of declaring class membership on the material).
   Real values found, verified from raws (`grep -ohE` across all four
   files): `CALCIUM_CARBONATE` (3), `CAN_GLAZE` (12), `FAT` (3), `FLUX` (2),
   `GYPSUM` (3), `PAPER_PLANT` (3), `PAPER_SLURRY` (3), `TALLOW` (3),
   `WAX` (3). Real example: `[REAGENT:B:1:BOULDER:NO_SUBTYPE:NONE:NONE]
   [REACTION_CLASS:FLUX]` (`reaction_smelter.txt:143`) — "any boulder whose
   material is tagged flux," the class-membership mechanism smelting flux
   actually uses.
2. **`[HAS_MATERIAL_REACTION_PRODUCT:X]`** on a reagent, matched against a
   material that itself declares `[MATERIAL_REACTION_PRODUCT:X:...]`
   (verified both sides from raws for `DRINK_MAT`: reagent side
   `reaction_other.txt:269`, material side `plant_standard.txt:13`). Real
   values, verified from raws: `DRINK_MAT` (6), `SEED_MAT` — wait, `SEED_MAT`
   is only ever a **product**-side material source, never a
   `HAS_MATERIAL_REACTION_PRODUCT` reagent filter (checked directly, zero
   hits), `BAG_ITEM` (3), `FIRED_MAT` (18, the clay/kiln class), `GLAZE_MAT`
   (12), `HONEYCOMB_PRESS_MAT` (3), `PARCHMENT_MAT` (3), `PRESS_LIQUID_MAT`
   (9), `PRESS_PAPER_MAT` (3), `RENDER_MAT` (3), `SOAP_MAT` (6), `TAN_MAT`
   (3). **One inconsistency worth flagging as a genuine finding, not
   resolved by this pass**: `PROCESS_PLANT_TO_BAG`'s reagent filter is
   `[HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM]`, but the matching definition
   on quarry bush's material (`plant_standard.txt:223`) is
   `[ITEM_REACTION_PRODUCT:BAG_ITEM:...]`, a **different token family**
   (item reaction product, not material reaction product) with the same
   name. Whether the reagent-matching filter `HAS_MATERIAL_REACTION_PRODUCT`
   actually checks both `MATERIAL_REACTION_PRODUCT` and
   `ITEM_REACTION_PRODUCT` tokens by name, or whether this is a raw-author
   naming looseness the engine papers over some other way, could not be
   settled from text files alone (would need DF's own source, closed).
   **Not verified; flagged as an open question for whoever writes the
   extractor**, since `production_class`'s vocabulary would silently drop
   `BAG_ITEM` if the extractor naively looks only for
   `MATERIAL_REACTION_PRODUCT` definitions.
3. **`[ANY_PLANT_MATERIAL]` / `[ANY_BONE_MATERIAL]`**, a hardcoded
   material-origin flag independent of any raw-authored class list (matches
   any material the engine itself considers plant-derived or bone-derived).
   24 and 8 occurrences respectively, verified from raws, e.g.
   `modding-guide.txt`'s own worked example: `[REAGENT:handle 1:1:BLOCKS:
   NONE:NONE:NONE][ANY_PLANT_MATERIAL]`.

**The barrel-or-pot container reagent** (the brief's second concrete
example) is written as a **fourth pattern again**, distinct from all three
class mechanisms above: `[REAGENT:barrel/pot:1:NONE:NONE:NONE:NONE]
[EMPTY][FOOD_STORAGE_CONTAINER][PRESERVE_REAGENT]` — `FOOD_STORAGE_CONTAINER`
is its own single-purpose flag (3 occurrences total, only ever on this exact
reagent), carrying the raw author's own inline comment `barrel or any
non-absorbing tool with FOOD_STORAGE` (`reaction_other.txt:273`, a
human-readable comment in the file itself, not a parsed token, but a strong
corroborating citation). The liquid-press container instead uses
`[HAS_TOOL_USE:LIQUID_CONTAINER]` (a tool-use flag, not a container-class
flag), and the bag/bucket reagents rely on nothing but their **fixed item
type** (`BAG`, `BUCKET`) being narrow enough on its own. **So
`container_class` cannot be populated from one token family either**: it is
`FOOD_STORAGE_CONTAINER` for barrels/pots, the bare item type for bags and
buckets, and `HAS_TOOL_USE:LIQUID_CONTAINER` for jugs/other liquid tools,
three different raw mechanisms an extractor must special-case by hand.

**Are there reagents naming one specific item with no class at all?** Yes,
common: `[REAGENT:lye:150:LIQUID_MISC:NONE:LYE]` names the exact material
`LYE` directly, no class matching at all (`reaction_other.txt`, in both
soap reactions). Verified from raws.

## 4. `production_flow.unit`

Classified every `[PRODUCT:...]` line's item type by whether a
`[PRODUCT_DIMENSION:n]` token appears anywhere in its (possibly
multi-line) block, correcting an earlier same-session miscount that only
checked the physically-next line (the real token often follows
`[PRODUCT_TO_CONTAINER:...]` first):

| Item type | With `PRODUCT_DIMENSION` | Without |
|---|---|---|
| `BAR` | 26/26 | 0 |
| `POWDER_MISC` | 70/70 | 0 |
| `DRINK` | 3/3 | 0 |
| `LIQUID_MISC` | 1/4 (`MAKE_MILK_OF_LIME` only) | 3 |
| everything else (`SEEDS`, `TOOL`, `WEAPON`, `GLOB`, furniture, jewelry, `SHEET`, `CRAFTS`, `SHIELD`, `SKIN_TANNED`, `ROCK`, ...) | 0 | all |

**`PRODUCT_DIMENSION` is not drink-specific**; it is used for exactly the
item types that have no fixed per-unit `[SIZE:n]` of their own in the item
raws (`BAR`, `POWDER_MISC`, `DRINK` are all hardcoded, non-raw-moddable item
types the same way `BARREL`/`BIN`/`BUCKET` are, confirmed by their absence
from `df.item_type`'s raw-moddable subset and their presence as bare enum
values in the same live read that confirmed `BARREL`/`BUCKET`/`BIN`, §8).
For item types that *do* carry a raw `[SIZE:n]` (every `TOOL` subtype: jug,
large pot, wheelbarrow, minecart, stepladder, ...), no `PRODUCT_DIMENSION`
appears anywhere, because the item's own raw size already answers the
question — an extractor must join against `item_tool.txt` (and siblings)
for these, not read the reaction file alone.

**Three `LIQUID_MISC` products have neither `PRODUCT_DIMENSION` nor any
other raw volume figure**: the plant/paste/honeycomb press reactions
(`reaction_other.txt`, all three `[PRODUCT:100:1:LIQUID_MISC:...]
[PRODUCT_TO_CONTAINER:liquid container]` lines, quantity fixed at 1 with no
dimension token anywhere in the block). **This is a genuine "not derivable"
case, not a lookup-away gap**: nothing in the raws states what one unit of
pressed oil or dye actually measures in cm³. An extractor's honest answer
for these three flow rows is `unit = unknown, status = unavailable`, not a
guessed figure.

**Net answer to "how would an extractor decide the unit for an arbitrary
row"**: three-way branch, all three branches real: (a) `PRODUCT_DIMENSION`
present → volume, direct read; (b) item type is a raw-moddable `TOOL`
subtype → volume via a join against the item raws (a lookup this project
must author, mirroring the jug/pot/wheelbarrow/minecart pattern already
established); (c) neither → `unit` is not derivable from any file on this
install (the three pressed-liquid cases, plus `SEEDS`/discrete countables
where "unit = plain item count" is the only sane default, itself an
authored convention rather than a read fact).

## 5. `production_process` coverage

**159 `[REACTION:...]` blocks** across the four shipped vanilla files
(`reaction_adv_carpenter.txt` 22, `reaction_dyes.txt` 68, `reaction_other.txt`
46, `reaction_smelter.txt` 23), confirmed by both `grep -c` and an
independent Python parse (the first parse pass under-counted at 135/44
because reaction codes can contain spaces, e.g. `[REACTION:ASSEMBLE STONE
AXE]` and `[REACTION:MAKE WOODEN CHAIR]`, which a naive `\S+` regex
misses — corrected and re-verified against the `grep -c` figure).

**`[BUILDING:...]`**: 148 of 159 (93%) carry it. The 11 that do not
(`MAKE_SHARP_ROCK`, seven `CARVE_BONE_*` reactions, `CARVE_WOODEN_HELVE`,
`ASSEMBLE STONE AXE`) **all carry `[ADVENTURE_MODE_ENABLED]`** (verified
directly, e.g. `reaction_other.txt`'s `MAKE_SHARP_ROCK`/`CARVE_BONE_
FIGURINE`/`ASSEMBLE STONE AXE` blocks read in full), i.e. they are
by-hand adventurer crafts with no fortress workshop at all, not a data gap.
An extractor filtering on `ADVENTURE_MODE_ENABLED` absence would correctly
get 100% `BUILDING` coverage for fortress-mode reactions.

**`[SKILL:...]`**: 158 of 159 (99%) carry it. The sole exception,
`ASSEMBLE STONE AXE`, is also adventure-mode-only and has no skill check at
all in its raw text (verified directly, no `[SKILL:...]` line in the block).

**Multi-building reactions** (fireable at more than one workshop type): 2
found, `MILL_SEEDS_NUTS_TO_PASTE` and `MAKE_SLURRY_FROM_PLANT`, both listing
`[BUILDING:QUERN:NONE][BUILDING:MILLSTONE:NONE]`. This means
`production_process.workshop_node` cannot always be a single scalar either;
a process can legitimately have more than one valid workshop, a smaller
version of the same "one row, multiple real answers" problem §2 found for
node identity.

**Hardcoded `df.job_type` values with no raw text**, confirmed directly
from `/opt/df/game/hack/lua/plugins/workflow.lua:198-204` this session (a
richer list than `research/2026-09-17-seed-ratios.md` found, which named
four): `MillPlants` → `'MILL'`, `ProcessPlants` → `'THREAD'`,
`ProcessPlantsBarrel` → `'EXTRACT_BARREL'`, `ProcessPlantsVial` →
`'EXTRACT_VIAL'`, and **`ExtractFromPlants` → `'EXTRACT_STILL_VIAL'`, not
previously documented in this project's research**. All five need
hand-authored `production_process` rows with `is_hardcoded = 1` and no
`source_ref` pointing at raw text, since none exists.

**A fifth reaction source exists on this install, outside the vanilla
raws, worth naming for completeness though it does not affect the
food/drink domain**: `/opt/df/game/hack/raw/reaction_spatter.txt` (7
`[REACTION:SPATTER_ADD_*]` blocks) and a sibling `reaction_steam_engine.txt`,
both DFHack-plugin-conditional raws loaded only if the relevant plugin is
active, not counted in the 159 above and not relevant to this project's
production graph, but real files an extraction script scanning `**/*.txt`
under `/opt/df/game` indiscriminately would pick up unless scoped to
`data/vanilla/vanilla_reactions/`.

## 6. `production_node.durability`

**A real raw token exists (`[ROTS]`), but it lives on the *material
template*, never on an item definition, and never on a plant definition
directly** (confirmed: `grep ROTS` against every file under
`vanilla_items/objects/` returned zero matches; `plant_standard.txt`
likewise has zero direct `ROTS` lines). Plants and items acquire rot status
by inheritance through `[USE_MATERIAL_TEMPLATE:...]`.

Verified from `material_template_default.txt` this session: `[ROTS]`
present on `STRUCTURAL_PLANT_TEMPLATE` (raw harvested plant matter, line
~2129, confirming `research/2026-09-17-seed-ratios.md`'s earlier read) and
30 other templates (skin, fat, muscle, organs, blood/ichor/goo/slime/pus,
tallow, milk, creature cheese, and the plant part templates: leaf, fruit,
bud, mushroom, flower). **Confirmed absent** (checked each template's full
block) from `SEED_TEMPLATE` (already known), and, **newly confirmed this
session**, from `PLANT_ALCOHOL_TEMPLATE` (drink — 60-line block, no `ROTS`
anywhere) and `PLANT_POWDER_TEMPLATE` (milled flour/sugar/dye powder —
41-line block, no `ROTS`). **This settles, as raw-verified rather than
inferred, that drink and milled powder products do not rot in this
install's raws**, a mechanic this project's doctrine has assumed but not
previously cited to a specific template read.

**So durability is extractable, but only conditionally on node identity
being resolvable at all**: for the 58% of product rows with a fixed
material (§2), the durability lookup is a clean join against that
material's template. For the 42% with a reagent-inherited material, the
same "which template" ambiguity from §2 applies — though in practice this
resolves more cleanly than node identity does, because (as just shown) an
entire product *class* (all drink, regardless of which crop) shares one
template and therefore one durability answer, so `durability` can often be
computed at the process level even when the concrete node id cannot. Worth
noting as a genuine asymmetry between the `id` and `durability` columns,
not previously flagged in the design.

## 7. `production_attribute` vocabulary

Real token names and real values, all raw-verified this session or citing
this session's/the prior sessions' direct reads:

| Attribute | Real token | Real example | Source |
|---|---|---|---|
| `growdur` | `[GROWDUR:n]` | `300` (plump helmet, pig tail), `500` (cave wheat, sweet pod, quarry bush, dimple cup) | `plant_standard.txt`, re-confirmed this session at lines 28/74/121/168/227 |
| `valid_seasons` | bare `[SPRING][SUMMER][AUTUMN][WINTER]` flags | plump helmet: all four; pig tail/cave wheat: `[SUMMER][AUTUMN]`; sweet pod: `[SPRING][SUMMER]` | `plant_standard.txt` lines 53/91/147/206, this session |
| `plant_value` | `[VALUE:n]` (plant-level, distinct from the material-level token below) | `2` on every one of the six fort crops | `plant_standard.txt` line 28 etc., this session |
| `material_value` | `[MATERIAL_VALUE:n]` | `2` (plant structural material), `8` (hematite, prior session) | `plant_standard.txt`/`inorganic_stone_mineral.txt` |
| `solid_density` | `[SOLID_DENSITY:n]` | `2670` granite, `7850` stainless steel, `5260` hematite (all prior session, re-cited not re-read) | `material_template_default.txt`/`inorganic_stone_mineral.txt` |
| `size` (item volume) | `[SIZE:n]` | `300` jug, `5000` large pot, `30000` wheelbarrow, `40000` minecart | `item_tool.txt`, this session for wheelbarrow/minecart (§8) |
| `container_capacity` | `[CONTAINER_CAPACITY:n]` — **a genuine raw token, not previously confirmed to exist in this project's research**, which had only ever cited the *wiki's* "capacity" figures | `10000` jug, `60000` large pot, `100000` wheelbarrow, `500000` minecart | `item_tool.txt` lines 159/170/223/211, this session |
| `ignite_point`/`heatdam_point` | `[IGNITE_POINT:n]`/`[HEATDAM_POINT:n]` | `10400`/`10500` (seeds, prior session) | `material_template_default.txt` |

**Attributes the design would want, for which no token exists on this
install**, reconfirmed rather than newly found: job duration, the
skill-to-speed curve, and (newly checked this session, see §9) **any figure
at all for lye/potash production** — there is no `[REACTION:...]` producing
either material anywhere in the shipped files, so there is no yield/ratio
attribute to extract for that step; it must be treated as entirely outside
the raw-derivable graph, not merely an attribute with an unavailable value.

## 8. Two free wins and the enum vocabularies

**(a) Wheelbarrow and minecart, promoted to `verified_raws`.** Direct read
of `item_tool.txt` this session:

```
[ITEM_TOOL:ITEM_TOOL_WHEELBARROW]
[VALUE:50]
[SIZE:30000]
[MATERIAL_SIZE:6]
[CONTAINER_CAPACITY:100000]

[ITEM_TOOL:ITEM_TOOL_MINECART]
[VALUE:50]
[SIZE:40000]
[MATERIAL_SIZE:6]
[CONTAINER_CAPACITY:500000]
```

Both `SIZE` and `CONTAINER_CAPACITY` match `research/2026-09-18-production-
figures.md` §1/§3.1's wiki-sourced figures (wheelbarrow 30,000/100,000,
minecart 40,000/500,000) exactly. **These four figures (plus `VALUE:50`
for both, not previously reported) move from `community_prior` to
`verified_raws`**, citing `item_tool.txt` lines 213-223 (wheelbarrow) and
200-211 (minecart) on this install. Also newly confirmed: jug and large pot
both carry `CONTAINER_CAPACITY` too (`10000` and `60000` respectively,
lines 159 and 170), which `research/2026-09-18-production-graph.md`'s
original pass did not report (it only read `SIZE` for those two). Barrel,
bin, and bucket remain **confirmed absent** from every file under
`vanilla_items/objects/` (re-checked this session, zero matches for
`ITEM_TOOL_BARREL`/`_BIN`/`_BUCKET` or any `ITEM_BARREL`/`ITEM_BIN`/
`ITEM_BUCKET` variant), so this finding does not extend to the three
containers this project's own tooling depends on most.

**(b) Enum vocabularies**, read live via `dfhack-run lua`, fort paused
before and after (`ReadPauseState()` → `true`, both checks):

- **`df.item_type`**: 93 values (`_first_item=-1` through `_last_item=92`).
  Full list: `NONE, BAR, SMALLGEM, BLOCKS, ROUGH, BOULDER, WOOD, DOOR,
  FLOODGATE, BED, CHAIR, CHAIN, FLASK, GOBLET, INSTRUMENT, TOY, WINDOW,
  CAGE, BARREL, BUCKET, ANIMALTRAP, TABLE, COFFIN, STATUE, CORPSE, WEAPON,
  ARMOR, SHOES, SHIELD, HELM, GLOVES, BOX, BAG, BIN, ARMORSTAND,
  WEAPONRACK, CABINET, FIGURINE, AMULET, SCEPTER, AMMO, CROWN, RING,
  EARRING, BRACELET, GEM, ANVIL, CORPSEPIECE, REMAINS, MEAT, FISH,
  FISH_RAW, VERMIN, PET, SEEDS, PLANT, SKIN_TANNED, PLANT_GROWTH, THREAD,
  CLOTH, TOTEM, PANTS, BACKPACK, QUIVER, CATAPULTPARTS, BALLISTAPARTS,
  SIEGEAMMO, BALLISTAARROWHEAD, TRAPPARTS, TRAPCOMP, DRINK, POWDER_MISC,
  CHEESE, FOOD, LIQUID_MISC, COIN, GLOB, ROCK, PIPE_SECTION, HATCH_COVER,
  GRATE, QUERN, MILLSTONE, SPLINT, CRUTCH, TRACTION_BENCH,
  ORTHOPEDIC_CAST, TOOL, SLAB, EGG, BOOK, SHEET, BRANCH,
  BOLT_THROWER_PARTS`. Confirms `BARREL`/`BUCKET`/`BIN` are indeed
  top-level hardcoded values, same enum tier as `TOOL`, not a `TOOL`
  subtype (re-confirming, from the enum side this time, the earlier
  raw-side absence finding).
- **`df.workshop_type`**: 26 slots (`_first_item=-1` through `_last_item=24`):
  `NONE, Carpenters, Farmers, Masons,
  Craftsdwarfs, Jewelers, MetalsmithsForge, MagmaForge, Bowyers, Mechanics,
  Siege, Butchers, Leatherworks, Tanners, Clothiers, Fishery, Still, Loom,
  Quern, Kennels, Kitchen, Ashery, Dyers, Millstone, Custom, Tool`.
- **`df.unit_labor`**: 94 slots, all named except several `UNUSED_*`
  entries: `NONE, MINE, HAUL_STONE, HAUL_WOOD, HAUL_BODY, HAUL_FOOD,
  HAUL_REFUSE, HAUL_ITEM, HAUL_FURNITURE, HAUL_ANIMALS, CLEAN, CUTWOOD,
  CARPENTER, STONECUTTER, STONE_CARVER, ENGRAVER, MASON, ANIMALTRAIN,
  ANIMALCARE, DIAGNOSE, SURGERY, BONE_SETTING, SUTURING, DRESSING_WOUNDS,
  FEED_WATER_CIVILIANS, RECOVER_WOUNDED, BUTCHER, TRAPPER, DISSECT_VERMIN,
  LEATHER, TANNER, BREWER, SOAP_MAKER, WEAVER, CLOTHESMAKER, MILLER,
  PROCESS_PLANT, MAKE_CHEESE, MILK, COOK, PLANT, HERBALIST, FISH,
  CLEAN_FISH, DISSECT_FISH, HUNT, SMELT, FORGE_WEAPON, FORGE_ARMOR,
  FORGE_FURNITURE, METAL_CRAFT, CUT_GEM, ENCRUST_GEM, WOOD_CRAFT,
  STONE_CRAFT, BONE_CARVE, GLASSMAKER, EXTRACT_STRAND, SIEGECRAFT,
  SIEGEOPERATE, BOWYER, MECHANIC, POTASH_MAKING, LYE_MAKING, DYER,
  BURN_WOOD, OPERATE_PUMP, SHEARER, SPINNER, POTTERY, GLAZING, PRESSING,
  BEEKEEPING, WAX_WORKING, HANDLE_VEHICLES, HAUL_TRADE, PULL_LEVER,
  UNUSED_13, HAUL_WATER, GELD, BUILD_ROAD, BUILD_CONSTRUCTION,
  PAPERMAKING, BOOKBINDING, UNUSED_20...UNUSED_30`. **Note**:
  `POTASH_MAKING` and `LYE_MAKING` exist as labor codes even though (§9)
  no raw `[REACTION:...]` in the shipped files actually produces potash or
  lye — the labor exists, the raw recipe producing the thing that labor is
  for does not, on this install's text files.

## 9. Cycles

**No cycle found, and the specific candidate the design named (ash → lye →
soap) cannot occur in the raw-derivable static graph at all**, for a clean
structural reason: **nothing in the four shipped reaction files produces
lye or potash.** `lye` and `lye container` appear only as `[REAGENT:...]`
lines (both soap reactions); grepping every file for `LYE`/`POTASH` as a
`[PRODUCT:...]` target returns zero hits. `[REACTION:MAKE_PEARLASH]`
*consumes* a `POTASH` bar but nothing produces one. `POTASH_MAKING` and
`LYE_MAKING` exist as `df.unit_labor` codes (§8) with no corresponding raw
reaction, the same hardcoded-mechanic pattern already established for
milling (§5) — potash/lye production is presumably a hardcoded
ashery/kiln job this install's text files simply do not expose, not a
missing file. **From the extractable graph's point of view, `LYE` and
`POTASH` are source nodes with zero raw-defined producers, not intermediate
nodes a cycle could route through.** `FERTILIZER` does not appear as a
token anywhere in the reaction files either (confirming the same
hardcoded-mechanic pattern `research/2026-09-17-seed-ratios.md` already
found for the fertilizer yield formula).

A coarse, deliberately over-inclusive check was also run: every
reagent-item-type → product-item-type edge across all 159 reactions
(conflating different materials of the same item type, which can only
*add* spurious edges, never hide a real cycle) found **zero** two-node
cycles. Since this check is a strict superset of the real, material-precise
graph, the absence of a cycle in the coarse version is a valid (if not
exhaustive at the material level) argument that no cycle exists in the real
one either — the smelter alloy reactions, the only place with enough
material variety to make a cycle plausible, were checked directly and
confirmed acyclic: the set of metals consumed (`IRON, SILVER, TIN, ZINC,
COPPER, NICKEL, GOLD, BISMUTH, LEAD`) and the set of alloys produced
(`ADAMANTINE, BILLON, BRASS, BRONZE, ELECTRUM, STEEL`) do not overlap.

**Answered, not deferred**: this pass could answer the cycle question
without building the full extraction, because the question turned out to
hinge on whether a producer exists at all (an easy grep), not on tracing a
multi-hop path through a fully expanded graph. **Caveat**: this check
covers only the 159 vanilla reactions in the four files read; it says
nothing about a cycle that might involve the hardcoded (non-raw) job types
(milling, lye-making) whose actual input/output ratios are not in any text
file to check (§5, §9's own finding above).

## Column-by-column verdict

**`production_node`**

| Column | Verdict | Basis |
|---|---|---|
| `id` (item type × material) | **extractable with a lookup we must author, for 58% of cases; not derivable as a single value for the other 42%** | §2: 67/163 product lines inherit material via `GET_MATERIAL_FROM_REAGENT`, 1 inherits both axes; a node id for these is a *set*, resolved by joining the reagent's class filter against every matching material, not a scalar read |
| `kind` | extractable | Determined by which raw object type (`PLANT`, `ITEM_TOOL`, `INORGANIC`, `REACTION`'s `BUILDING`) defined the row |
| `display_name` | extractable | `[NAME:...]` tokens present throughout |
| `durability` | **extractable with a lookup we must author, conditional on `id` being resolvable (§6)** | `[ROTS]` lives on material templates only; resolvable per-process even when concrete node id is not (drink/powder are uniformly non-rotting regardless of which crop) |
| `status` | extractable (meta, assigned by the extractor per this project's own vocabulary) | n/a |
| `source_ref` | extractable (meta) | n/a |

**`production_class`**

| Column | Verdict | Basis |
|---|---|---|
| `node_id` | Same caveat as `production_node.id` | §2 |
| `class` | **extractable with a lookup we must author** | §3: three unrelated raw mechanisms (`REACTION_CLASS`, `HAS_MATERIAL_REACTION_PRODUCT`, `ANY_PLANT_MATERIAL`/`ANY_BONE_MATERIAL`) plus a fourth ad hoc flag (`FOOD_STORAGE_CONTAINER`) must be unified by hand into one vocabulary; one naming inconsistency (`BAG_ITEM` defined via `ITEM_REACTION_PRODUCT` but matched via `HAS_MATERIAL_REACTION_PRODUCT`) is unresolved |

**`production_process`**

| Column | Verdict | Basis |
|---|---|---|
| `id` | extractable | Reaction code, direct read, 159 found (note: can contain spaces) |
| `workshop_node` | **extractable, with a real one-to-many case (2/159 reactions list two `BUILDING`s)** | §5 |
| `labor` | extractable (158/159; `ASSEMBLE STONE AXE` has none) | §5, `[SKILL:...]` → `df.unit_labor` enum (§8) |
| `is_hardcoded` | **extractable for the 159 raw reactions (0); the 5 hardcoded job types must be hand-seeded (1), since nothing in the raws enumerates them** — found only by reading `workflow.lua` | §5 |
| `capacity_theoretical` | **not derivable** | No file on this install states job duration or throughput; reconfirmed, not just carried forward |
| `source_ref` | extractable (meta) | n/a |

**`production_flow`**

| Column | Verdict | Basis |
|---|---|---|
| `process_id` | extractable | n/a |
| `direction` | extractable | `REAGENT`/`PRODUCT` token distinguishes directly |
| `node_id` | Same caveat as `production_node.id` | §2 |
| `quantity` | extractable | Direct read of the count token; note `DOES_NOT_DETERMINE_PRODUCT_AMOUNT` reagents' quantity is a matching requirement, not a yield-scaling figure — still a literal, extractable number, just not one that means "yield" |
| `unit` | **mixed**: extractable via `PRODUCT_DIMENSION` for `BAR`/`POWDER_MISC`/`DRINK`/some `LIQUID_MISC`; extractable with a lookup (join to item raws) for `TOOL`-subtype products; **not derivable** for 3 pressed-liquid products | §4 |
| `consumption` | **extractable with a lookup we must author, and the schema's 3-value enum is short one value** | §1: the `PRESERVE_REAGENT` × `PRODUCT_TO_CONTAINER`-target rule resolves 3 of the 4 real outcomes; the `[IMPROVEMENT]`-only case (4/159 reactions) has no product row to even attach a value to |
| `probability` | extractable for products (the literal `PRODUCT:probability:...` field, always seen at 100 in this install's shipped files); **reagents carry no probability token at all**, so `direction='reagent'` rows get a constant default (100, "required"), not a read value | §1 raw format |
| `container_class` | **extractable with a lookup we must author** | §3: three different raw mechanisms, no unified token |
| `status` | extractable (meta) | n/a |
| `source_ref` | extractable (meta) | n/a |

**`production_attribute`**

| Column | Verdict | Basis |
|---|---|---|
| `subject_id` | extractable (FK) | n/a |
| `name` | **extractable with a lookup we must author** | §7: no raw-stated "this is an attribute" marker; the extractor must decide which tokens (`GROWDUR`, `VALUE`, `MATERIAL_VALUE`, `SOLID_DENSITY`, `SIZE`, `CONTAINER_CAPACITY`, season flags, `IGNITE_POINT`/`HEATDAM_POINT`) become rows |
| `value` | extractable for the tokens in §7's table; **not derivable** for job-time/skill-curve/hardcoded-yield attributes | §7, §9 |
| `unit` | **extractable with a lookup we must author** | The unit each attribute name implies (cm³ for `SIZE`/`CONTAINER_CAPACITY`, growdur-ticks for `GROWDUR`, °Urist for the ignite/heatdam points) is convention, not a raw-stated field |
| `status` | extractable (meta) | n/a |
| `source_ref` | extractable (meta) | n/a |

## What could not be verified

- **Whether `HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM` actually matches
  `ITEM_REACTION_PRODUCT:BAG_ITEM` definitions on the material side**
  (§3). The naming mismatch is real and directly readable; whether the
  engine treats the two token families as interchangeable for matching
  purposes would need DF's own (closed) source or a live test (designating
  and running the actual job on the paused fort, out of scope for a
  read-only audit).
- **The exact release trigger for `occupied_until_released` reagents**
  (§1) — that a barrel becomes occupied by drink is raw-derivable; that it
  is freed specifically when the drink is fully consumed is general DF
  mechanics knowledge, not confirmed against any file read this session.
- **Whether every occurrence of `PRESERVE_REAGENT` without a matching
  `PRODUCT_TO_CONTAINER` really does mean "returned unchanged"** as opposed
  to some other engine-side effect not visible in raw text (e.g. wear or
  quality change on a used tool). The pattern is internally consistent
  across all 314 reagent lines checked, but internal consistency is not the
  same as an authoritative definition, and none was found (§1).
- **Whether `PLANT_ALCOHOL_TEMPLATE`'s and `PLANT_POWDER_TEMPLATE`'s
  absence of `[ROTS]` is the complete rot story for drink/powder**, versus
  some other tag family (not found in this search) also governing spoilage.
  Absence of `[ROTS]` was checked directly and thoroughly for both
  templates' full blocks; a broader spoilage mechanism outside the `ROTS`
  tag family, if one exists, was not searched for.
- **Whether `df.job_type` (not enumerated this session, only named
  individual hardcoded values via `workflow.lua`) contains further
  food/drink-relevant hardcoded jobs beyond the five listed in §5.** The
  brief asked specifically for milling/plant-processing job types, which
  are covered; a full `df.job_type` enum dump was not performed, since it
  was not asked for and the five found already fully account for every
  hardcoded job this project's doctrine currently references.
- **Whether the `hack/raw/reaction_spatter.txt` and `reaction_steam_engine.txt`
  plugin reactions are ever actually active on this install** (i.e.
  whether the relevant DFHack plugins are enabled in this fort's config).
  Not checked; noted only as a scanning-scope trap for a future extraction
  script (§5).
