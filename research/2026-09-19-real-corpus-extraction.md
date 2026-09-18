# Real-corpus extraction: what the fixture subset was hiding

Date: 2026-09-19. Offline stream, no VM/SSH/DFHack/fort. The real
159-reaction vanilla corpus (`vanilla_reactions`, `vanilla_plants`,
`vanilla_items`, `vanilla_materials`, `vanilla_buildings`; 40 files, 830K)
was pulled read-only from VM 103 by the orchestrator ahead of this stream
and read in place from a session scratchpad path. **Never copied into this
repo**: this repo is public and the raws are game data. Any SQLite database
built from them is also out-of-tree.

Reaction counts reproduced exactly against
`research/2026-09-18-schema-extraction-static.md`: adv_carpenter 22, dyes
68, other 46, smelter 23, total **159**. `production/tests/fixtures/**`
was not touched; all 57 existing fixture-driven tests still pass (2
assertions updated to a corrected, honestly-derived node-id convention,
not to a weaker one; see below).

**Tests: 364 passed / 1 skipped before this stream, 371 passed / 1 skipped
after** (7 new tests in `production/tests/test_extract.py`, inline
literal token strings quoting a handful of real lines, never the fixture
files or the raws themselves).

## Headline: this extractor had never seen real data, and it showed

`production/extract.py`'s own stream (`handoffs/2026-09-18-production-
package.md`) ran only against a hand-assembled 6-reaction fixture subset,
built by *guessing* at raw argument shapes the offline audit hadn't been
able to quote in full. That write-up was honest about the risk. Running
the same code against the real corpus found six genuinely distinct real
bugs, ranging from "silently loses information" to "silently fabricates a
wrong answer and marks it `verified_raws`". None were hypothetical; each
is demonstrated below with the real file:line and the row it used to
produce.

## 1. The `GET_MATERIAL_FROM_REAGENT` join: 42% confirmed, and its one exception found and fixed

**Measured: 68 / 163 real product lines (41.7%) are parametric**
(`GET_MATERIAL_FROM_REAGENT` or `GET_ITEM_DATA_FROM_REAGENT`), across all
159 reactions; this matches the static audit's "42%" almost exactly (the
audit's own rounding; 41.7% is the precise count). Restricted to the 148
fortress-mode reactions this extractor actually loads into the graph (11
adventure-mode-only reactions excluded, matching audit §5), the figure is
57/152 = 37.5%, a real, lower, and more operationally relevant number
that the "42%" headline doesn't distinguish, worth carrying forward.

**One of those 68 is not `GET_MATERIAL_FROM_REAGENT` at all.**
`PROCESS_PLANT_TO_BAG` (`reaction_other.txt:328`, real corpus) reads:

```
[PRODUCT:100:5:GET_ITEM_DATA_FROM_REAGENT:plant:BAG_ITEM]
```

Five args total. Every other real product line this extractor was built
against has the marker in the **material-source** position (arg 5),
item type staying explicit (e.g. `DRINK:NONE:GET_MATERIAL_FROM_REAGENT:
plant:DRINK_MAT`). Here `GET_ITEM_DATA_FROM_REAGENT` sits in the **item
type** position instead: there is no explicit item type at all; DF
derives both the type and the material from the reagent's own match.
Before the fix, `extract.py`'s `mat_source_type in (...)` check never
fired for this shape (its `mat_source_type` position holds the literal
string `"BAG_ITEM"`), so the product fell through to the *non-parametric*
path and `_fixed_node_id` built a node id straight out of the raw token
text, `"GET_ITEM_DATA_FROM_REAGENT:plant:BAG_ITEM"`, stamped
`status='verified_raws'`. That is worse than the already-known BAG_ITEM
token-family mismatch (`docs/PRODUCTION-MODEL.md` §6) it was meant to be
one instance of: not merely unresolved, actively wrong and confidently
labelled. Fixed: `extract.py`'s pass1 now detects this shape explicitly
(checked in *both* the item-type and material-source positions, belt and
suspenders) and routes it through the same honest "stay unresolved"
machinery as every other unmatched parametric flow. Confirmed the ONLY
occurrence of this shape across all 159 real reactions.

**The join table itself is real and populates correctly**: 37
`material_reaction_product` rows from `plant_standard.txt` alone (`DRINK_MAT`
×16, `SEED_MAT` ×17, `PRESS_PAPER_MAT` ×2, `PRESS_LIQUID_MAT` ×1, plus the
one `item_reaction_product`-family `BAG_ITEM` row). See §4 for why its own
real argument shape was also wrong before this stream.

## 2. Consumption derivation: the zero-exceptions claim held, verified by running code

`docs/PRODUCTION-MODEL.md` §5 claims the four-outcome consumption rule
(`PRESERVE_REAGENT` × `PRODUCT_TO_CONTAINER` target × `NOT_IMPROVED` ×
whether the reaction has any product) has **zero exceptions across 159
reactions and 314 reagent lines**, a claim made by a human reader, never
by running code, and the handoff explicitly asked for it to be checked
rather than smoothed over.

**Ran `derive_consumption` against all 314 real reagent lines. Zero
exceptions.** Every line's four-way input tuple resolved to exactly one
bucket, with no ambiguous or contradictory combination (checked for: a
`PRODUCT_TO_CONTAINER` target reagent without `PRESERVE_REAGENT`, and a
`NOT_IMPROVED` reagent on a reaction that unexpectedly does have products;
neither occurred):

| Outcome | Count (all 159 reactions, 314 lines) | Count (148 fortress-mode reactions actually loaded, 292 lines) |
|---|---|---|
| `consumed` | 194 | 182 |
| `occupied_until_released` | 78 | 78 |
| `occupied_job` | 38 | 28 |
| `modified_in_place` | 4 | 4 |

The four `modified_in_place` reagents are exactly the four real `GLAZE_*`
reactions (`GLAZE_JUG`, `GLAZE_STATUE`, `GLAZE_LARGE_POT`, `GLAZE_CRAFT`),
each with zero `[PRODUCT]` lines and one `PRESERVE_REAGENT` +
`NOT_IMPROVED` reagent, matching the spec's own example exactly. **This is
a clean run, reported as one**, per the handoff's own instruction not to
manufacture an exception that isn't there.

## 3. Class expansion: the real number is 16 (or 76), not 5

The predecessor stream's fixture illustrated `BREW_DRINK_FROM_PLANT`
materialising into 5 concrete drinks (the traditional five fort crops:
plump helmet, pig tail, cave wheat, sweet pod, dimple cup), an
**illustrative**, never audit-verified number
(`production/tests/fixtures/PROVENANCE.md`).

**Measured against the real `plant_standard.txt` (the file `docs/
PRODUCTION-MODEL.md` §6 scopes extraction to, "the plant file", singular,
matching what the static audit actually read): 16 plants carry
`DRINK_MAT`, not 5.** `plant_standard.txt` includes many brewable
wild/cavern plants beyond the five canonical farm crops (berries, muck
root, sliver barb, reed rope, and more; full list in the extraction run).
`BREW_DRINK_FROM_PLANT` genuinely materialises into **16 concrete drink
nodes** from this one file alone, each with its own 5-drink/1-seed product
pair, all `status='verified_raws'`. 17 plants carry `SEED_MAT` (the same
16 plus quarry bush, which has no `DRINK_MAT`).

**A further, larger number the spec's own wording surfaces as a real
ambiguity, not resolved by this stream**: the real `vanilla_plants/
objects/` directory has **five** plant files (`plant_standard.txt`,
`plant_crops.txt`, `plant_garden.txt`, `plant_grasses.txt`,
`plant_new_trees.txt`, 225 `[PLANT:...]` blocks combined), not the "the
plant file" §6's prose implies. Measured across all five: **76 plants
carry `DRINK_MAT`**. This extractor's default scope was deliberately kept
to `plant_standard.txt` only, matching the audit's own read scope and the
spec's literal wording, rather than silently widening it: extending to
all five is a real design decision (does a farmer ever cultivate a cavern
grass? does `CLUSTERSIZE`/growdur semantics hold the same across files?)
that this stream is not positioned to make unilaterally. Flagged for the
next production-model stream to decide explicitly, with both real numbers
now on record instead of the illustrative "5".

## 4. The real `MATERIAL_REACTION_PRODUCT` shape carries no item type at all

The single most consequential fix. Real corpus, `plant_standard.txt:13-14`:

```
[MATERIAL_REACTION_PRODUCT:DRINK_MAT:LOCAL_PLANT_MAT:DRINK]
[MATERIAL_REACTION_PRODUCT:SEED_MAT:LOCAL_PLANT_MAT:SEED]
```

Three args: `token`, a material-lookup family (`LOCAL_PLANT_MAT` in every
real occurrence read this session: "look up this plant's own material
list"), and a material name **local to this same plant** (here, the
material declared elsewhere on the same plant by
`[USE_MATERIAL_TEMPLATE:DRINK:PLANT_ALCOHOL_TEMPLATE]`). There is no item
type anywhere on this line. Proof the two lines above aren't reusing the
same vocabulary by coincidence: `SEED_MAT`'s material name is `SEED`
(singular), but the real reaction's own product item type for the same
flow is `SEEDS` (plural): different strings, different purposes.

The predecessor stream's fixture (`production/tests/fixtures/
plant_standard.txt`, frozen, untouched by this stream) used its own
invented 3-arg form, `token:item_type:node_suffix`, e.g.
`MATERIAL_REACTION_PRODUCT:DRINK_MAT:DRINK:PLUMP_HELMET_WINE`, which
happened to also be 3 args, so it looked plausible, but positions 2 and 3
meant something else entirely, and the plant id itself
(`PLUMP_HELMET`) was invented too (the real raw id is
`MUSHROOM_HELMET_PLUMP`). That write-up was explicit this was a guess
("the exact argument list DF uses internally was not quoted in the audit
and is not reproduced here"): this is that guess being checked against
real data for the first time, and it was wrong in exactly the way a
9-year-old game engine's data usually is when nobody's checked: not
absurd, just specific in ways nobody had verified.

**Fix**: `pass1` no longer builds an item-shaped node id from the MRP
line at all: it builds a `production_node(kind='material')` row (`e.g.
MATERIAL:MUSHROOM_HELMET_PLUMP:DRINK`), honestly representing only what a
bare MRP line states: a material local to a plant. `pass2` combines that
material with the *reaction's own* `[PRODUCT:...]` item type (`DRINK`,
read off the real product line, not invented) to build the concrete item
node, `DRINK:MUSHROOM_HELMET_PLUMP`, the first time this id has ever
been built from raw facts rather than an illustrative example. The
existing fixture-driven end-to-end test (`test_brew_drink_from_plant_end_
to_end`) is updated to this convention (`DRINK:PLUMP_HELMET` etc., using
the fixture's own frozen (if also invented) plant ids), not weakened:
it still proves 5 concrete drinks and 5 seed nodes out of the fixture's 5
plants, one reaction in, three of the four consumption branches exercised,
exactly as the predecessor handoff specified.

## 5. The reagent-material collapse: 88 distinct materials were indistinguishable, not just the 2 cases this stream set out to check

The handoff asked specifically about the `GET_MATERIAL_FROM_REAGENT` join
(product side). Verifying `derive_consumption` against real reagent lines
surfaced a **product-independent** bug on the reagent side that turned out
far larger in scope than the two cases that led to finding it.

`_reagent_class`'s own docstring claimed a reagent naming a fixed material
directly (its example: `lye`) returned `(None, None, None)`, untested,
since no fixture exercised it. **It did not.** It fell into the bare-
item-type fallback and returned a value, just a lossy, material-blind one:
every reagent of a given item type collapsed to the identical class
string regardless of material. Two shapes proved it:

- `[REAGENT:B:1:METAL_ORE:COPPER]` (real corpus, `reaction_smelter.txt`,
  12 occurrences): DF's short reagent form for an ore. `METAL_ORE` has no
  subtype/mat-category slots of its own; the material lands directly in
  what this parser treats as the subtype position. Before the fix, every
  metal-ore reagent of every smelting reaction extracted as the identical
  bare class `"METAL_ORE"`: copper, silver, gold, tin and zinc ore
  reagents were indistinguishable from each other in the extracted graph.
- `[REAGENT:lye:150:LIQUID_MISC:NONE:LYE]` (2 occurrences): the standard
  shape with a bare material name in the mat-category slot. Extracted as
  the bare class `"LIQUID_MISC"`.

**Measuring the fix's actual real-corpus impact (not assumed from the two
cases that motivated it): 88 distinct reagent classes across 122 reagent
flow rows are now material-qualified that were not before**: this is
larger than either of the two prompting cases, and larger than this
stream initially scoped the fix as. Before the fix, all of these would
have collapsed into 9 bare item-type buckets:

| Bare class before the fix | Distinct materials now qualified | Examples |
|---|---|---|
| `WOOD` | 23 | `WOOD:OAK`, `WOOD:PINE`, `WOOD:MAHOGANY`, ... |
| `PLANT_GROWTH` | 32 | `PLANT_GROWTH:APPLE`, `PLANT_GROWTH:GRAPE`, `PLANT_GROWTH:TOMATO`, ... |
| `BAR` | 12 | `BAR:IRON`, `BAR:COPPER`, `BAR:PIG_IRON`, `BAR:POTASH`, ... |
| `METAL_ORE` | 5 | `METAL_ORE:COPPER`, `METAL_ORE:GOLD`, `METAL_ORE:SILVER`, ... |
| `PLANT` | 6 | `PLANT:POTATO`, `PLANT:RICE`, `PLANT:WILD_CARROT`, ... |
| `LIQUID_MISC` | 3 | `LIQUID_MISC:LYE`, `LIQUID_MISC:MILK_OF_LIME`, `LIQUID_MISC:CREATURE_MAT` |
| `BOULDER` | 2 | `BOULDER:COAL_BITUMINOUS`, `BOULDER:LIGNITE` |
| `THREAD` | 1 | `THREAD:ADAMANTINE` |
| `POWDER_MISC` | 1 | `POWDER_MISC:QUICKLIME` |

Every wood-species reagent (carpentry, dye-making), every fruit/growth
reagent (dye-making), every metal bar and ore reagent (alloying,
smelting) would have been extracted as materially indistinguishable from
every other reagent of the same item type, undermining the exact "what
feeds what" precision the whole production-model design exists to
provide. Fixed by reusing `_fixed_node_id`'s already-correct family/
bare-material handling inside `_reagent_class`'s fallback branch, rather
than inventing new logic.

One genuinely uncertain case, **not resolved by this stream, flagged
rather than acted on**: two real smelter product lines read
`[PRODUCT:100:9:BAR:NO_SUBTYPE:COAL:COKE]`
(`reaction_smelter.txt:9,17`) and two real reagent lines read
`[REAGENT:C:150:BAR:NO_SUBTYPE:COAL:NO_MATGLOSS]`
(`reaction_smelter.txt:144,155`). The `COAL:NO_MATGLOSS` /
`COAL:COKE` pairing looks exactly like the same family-then-material
pattern this stream fixed for `PLANT_MAT`/`METAL`/`INORGANIC`, but the
predecessor audit (`research/2026-09-18-schema-extraction-static.md` §2)
explicitly classified `COAL` as a **bare material name**, not a family,
after its own real-file read. This stream's evidence (a wildcard-looking
`NO_MATGLOSS` trailing arg on the reagent side) is suggestive but not
strong enough to unilaterally overturn a documented, cited prior finding
without a second source (DF's own engine source is closed; the wiki was
not re-checked this session). Left as the existing, audited "COAL" bare-
material behaviour (`BAR:COAL`, both COKE reactions collapse together);
flagged here rather than silently changed either direction.

## 6. Two reactions were silently over-resolved by matching on token *name* alone

Found while double-checking §5's fix against the full corpus, not one of
the four things the handoff named to look hardest at, but exactly the
kind of exception the handoff said was worth more than a clean run.

`pass2`'s join matches a parametric product against
`material_reaction_product` purely by **token name**. That is correct
when the reagent the product actually names was itself filtered via
`HAS_MATERIAL_REACTION_PRODUCT` (the only mechanism that table's rows are
ever sourced from in this corpus (all of them come from plant files).
It is **not** correct when the token name happens to collide with one
from a completely unrelated material family. Two real reactions do
exactly that:

- **`MAKE_MEAD`** (`reaction_other.txt:299-314`): the real product line
  is `[PRODUCT:100:5:DRINK:NONE:GET_MATERIAL_FROM_REAGENT:honey:
  DRINK_MAT]`. The `honey` reagent it names is
  `[REAGENT:honey:150:LIQUID_MISC:NONE:CREATURE_MAT:HONEY_BEE:HONEY]`, a
  **fixed** creature material, no `HAS_MATERIAL_REACTION_PRODUCT` flag at
  all. DF resolves `DRINK_MAT` here against honey's own creature-material
  declaration, which lives in a creature raw file this corpus does not
  have (only `vanilla_reactions`/`vanilla_plants`/`vanilla_items`/
  `vanilla_materials`/`vanilla_buildings` were pulled down). Before the
  fix, because 16 unrelated *plants* happen to also declare a token
  literally named `DRINK_MAT`, `pass2` joined mead's product against all
  16 of them, materialising **16 spurious "mead" drink nodes**, one per
  brewable plant species, every one stamped `verified_raws`.
- **`MAKE_SHEET_FROM_PLANT`** (`reaction_other.txt`): its second product
  line similarly names a `plant` reagent filtered via `REACTION_CLASS:
  PAPER_PLANT` (not `HAS_MATERIAL_REACTION_PRODUCT`), but the token
  happens to be `SEED_MAT`, a real token 17 plants declare. Same
  collision, same failure mode: **17 spurious seed-product nodes**
  before the fix.

**Fix**: `pass1` now records, per reagent name within a reaction, which
mechanism actually resolved that reagent's class (already computed by
`_reagent_class` for the reagent's own flow row, reused, not
recomputed). A parametric product only attempts the
`material_reaction_product` join if the reagent it names was resolved via
`MECH_MATERIAL_REACTION_PRODUCT`; otherwise it stays honestly
`unavailable`, regardless of whether the token string happens to match
something in the join table. Verified against the real corpus: both
reactions' affected products now read `node_id=NULL,
status='unavailable'`; the 16+17=33 spurious rows are gone;
`production_flow` drops from 570 to 539 rows and `production_class`'s
duplicate `DRINK` rows drop from 48 to 32 (still one per reaction that
legitimately uses the plant-sourced token, `BREW_DRINK_FROM_PLANT` and
`BREW_DRINK_FROM_PLANT_GROWTH`, ×16 plants each). No fixture-driven test
depended on the old, wrong behaviour: `BREW_DRINK_FROM_PLANT` and
`PROCESS_PLANT_TO_BAG`'s "plant" reagent both genuinely do carry
`HAS_MATERIAL_REACTION_PRODUCT`, so they still resolve exactly as before.

## 7. Reaction-level tokens were being silently misattributed, not dropped

`CATEGORY`/`CATEGORY_NAME`/`CATEGORY_DESCRIPTION` (real corpus: 98 of 159
reactions carry one, e.g. `reaction_dyes.txt:12`, `[CATEGORY:MAKE_DYE]`)
and `NAME` (all 159) are reaction-level UI-grouping/display tokens that
sit textually **after** the reaction's last `[REAGENT:...]`/
`[PRODUCT:...]` block. Before this fix, `parse_reactions`'s catch-all
("attach to whichever reagent/product is currently open") silently
misattributed every one of them onto the **last-parsed product's own
flags list**, never corrupting a value any computed field actually read
(nothing consumed a `"CATEGORY"` flag), but real per-reaction metadata was
being lost/mislabelled rather than captured, and, more importantly,
this is exactly the class of bug ("attaches somewhere plausible-looking
but wrong") this stream was asked to hunt hardest for. `NAME`, being the
*first* token after every `[REACTION:...]` line before any reagent/product
has opened at all, was **silently dropped outright**: the catch-all's
`target = cur_product if ... else cur_reagent` was `None` for every one
of the 159 real reactions, every time.

Fixed: both are now recognised explicitly and captured as
`production_attribute` rows on the reaction itself (`display_name`,
`category`, `category_name`, `category_description`), the same treatment
this schema already gives `workshop_alt` overflow, no schema change
needed. Real result: 148 reactions (all fortress-mode ones) now carry a
`display_name` attribute, 90 carry `category` (98 raw occurrences minus 8
belonging to the 11 filtered adventure-mode-only reactions).

## 8. Unparsed-line reporting: added, verified detectable, zero on the real corpus

The extractor previously had no mechanism to report a line it could not
place anywhere. Added: `parse_reactions` and `parse_plants` now collect
every bare token that reaches the catch-all branch with **no** open
reagent/product **and** no recognised reaction-level home, plus every
`MATERIAL_REACTION_PRODUCT`/`ITEM_REACTION_PRODUCT` line whose arg count
matches neither the real nor the legacy-fixture shape, into an `unparsed`
list threaded through `pass1` → `pass2` → `extract_from_sources`/`extract`
(NOT one of `store.write_all`'s kwargs; callers pop it first, as `main`
now does).

**Verified the check could actually have caught something**, per the
handoff's "verify the verification" rule: `test_unparsed_tracking_
catches_a_genuinely_orphaned_token` feeds a synthetic malformed token
through the real code path and confirms it is caught, not silently
absorbed. Only after that passed is the real-corpus "0 unparsed" result
meaningful rather than a check that would have said 0 regardless.

**Real corpus result: 0 unparsed lines**, once `NAME`/`CATEGORY*` were
recognised explicitly (before that fix, `NAME` alone would have reported
159 false-positive "unparsed" entries, itself informative: it is exactly
how this stream noticed `NAME` was being dropped, see §7).

## 9. A minor, incidental correction to the static audit

The static audit (§5) counted "22/22" real reactions where furniture/tool
items made from `log` inherit whatever wood species the carpenter used,
with no `MATERIAL_REACTION_PRODUCT`-style token to resolve it (the same
"genuinely unresolved" texture as `MAKE_WOODEN_CHAIR`, spec §6). The real
count, measured against the actual extracted graph: **23** distinct
`MAKE WOODEN *`-family processes carry an unavailable reagent+product pair
this way (45 of the 76 total `unavailable` flow rows, 59%). A one-reaction
undercount in a hand-count, not a design problem; flagged for the
record, not because it changes any conclusion.

## Real coverage table (a claim about this install, corpus = real
`vanilla_*` raws pulled from VM 103, 2026-09-19)

| Table | Rows | `status='prior'` | `status='unavailable'` | Notable NULL columns |
|---|---|---|---|---|
| `production_node` | 241 | 0 | 0 | `durability`: 101/241 (buildings, materials, and item types outside the four-entry `ITEM_TYPE_TEMPLATE` lookup, unchanged gap from the fixture stream, now measured at real scale) |
| `production_class` | 48 | n/a (no `status` column) | n/a | none: 32 `DRINK` rows (16 real brewable plants × the 2 reactions that legitimately reference the plant-sourced `DRINK_MAT` token, `BREW_DRINK_FROM_PLANT` and `BREW_DRINK_FROM_PLANT_GROWTH`; see §6 for why this is 32 and not 48), 16 `BREWABLE_PLANT` |
| `material_reaction_product` | 37 | n/a | n/a | none: `DRINK_MAT` ×16, `SEED_MAT` ×17, `PRESS_PAPER_MAT` ×2, `PRESS_LIQUID_MAT` ×1, `BAG_ITEM` ×1 (item_reaction_product family, the known unresolved mismatch) |
| `production_process` | 148 | n/a | n/a | `is_hardcoded`: 0/148 (all raw-defined; no hardcoded job type enumerated by this extraction, matching spec §17) |
| `production_flow` | 539 | 0 | 76 (48 product, 28 reagent; see §6/§9 above for composition) | `node_id`: 76 (the unavailable rows); `unit`: 400/539; `consumption`: 247/539 (reagent-only by design); `container_class`: 461/539 |
| `production_attribute` | 394 | 0 | 0 | `unit`: 347/394 (`display_name`/`category*`/season/value attributes carry no natural unit) |
| `production_observation` | 0 | 0 | 0 | purely offline; the live layer writes no observations, by design |

**These row counts are a claim about this install**, extracted from the
real `vanilla_reactions`/`vanilla_plants`(`plant_standard.txt` only, see
§3)/`vanilla_materials`/`vanilla_items` raws pulled read-only from VM 103
on 2026-09-19, not the fixture subset. The database itself lives out of
tree, in this session's scratchpad, never committed.

## What still needs a decision, not an extraction fix

- **Plant-file scope** (§3): extend to all five `vanilla_plants/objects/`
  files, or keep `plant_standard.txt` only? Real numbers now on record
  either way (16 vs 76 brewable plants).
- **`COAL` as bare material vs. family** (§5): flagged, not resolved.
- **Multi-building reactions, `production_class.mechanism`'s wider
  vocabulary, the reagent `node_id`/product `node_id` type mismatch**:
  all carried over unchanged from `handoffs/2026-09-18-production-
  package.md`'s own write-up; nothing in the real corpus contradicted
  those findings, this stream just had no reason to revisit them.
