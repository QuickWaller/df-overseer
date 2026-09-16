# Seed economics for the six fort crops (DF Classic v0.53.16, DFHack 53.16-r1.1)

Date: 2026-09-17. Read-only research against VM 103's live install (SSH,
game root `/opt/df/game`) plus the DF wiki (labelled by namespace, since
pre-v50 and v50+ mechanics differ) and DFHack's own shipped tool docs. No
game state was written, unpaused, saved, or designated. No files were left
on the VM. Method followed `CLAUDE.md`'s "wiki produces hypotheses, not
doctrine" rule: raws and DFHack's own installed docs are treated as primary
sources and read directly; wiki claims are marked `community_prior` with the
namespace they came from and cross-checked against the raws wherever the
raws could settle the question.

## Bottom line

The user's doctrine prior is **half right, and the wrong half matters**.
"Never let seed stock fall, manage the split between methods" is the right
frame. But **"seed return is slightly random" is not true for most of the
methods available to this fort.** Reading the actual reaction raws
(`data/vanilla/vanilla_reactions/objects/reaction_other.txt`) shows that
**brewing, quarry-bush-to-bag processing, and pig-tail papermaking are each
coded as `[PRODUCT:100:1:SEEDS...]`: a guaranteed 100% chance, exactly one
seed, per plant unit consumed, taken from the very plant being consumed**
(`GET_MATERIAL_FROM_REAGENT:plant:SEED_MAT`). Only **cooking** is
raw/tool-confirmed to return zero seed, ever. The genuinely random-sounding
"1 or 2 seeds" claim on the wiki turns out to describe a *different* set of
jobs — milling to powder, pig tail's actual thread output, and sweet pod's
extract/syrup output — which are **hardcoded engine job types
(`MillPlants`, `ProcessPlants`, `ProcessPlantsBarrel`/`Vial`) with no raw
text defining their seed math**, so DF being closed-source means that part
of the claim is genuinely unverifiable from this install and has to stay a
community prior, not doctrine.

The practical formula (§6) is: **the minimum share of a harvest that must
go through a guaranteed-return method is `1 / (yield_per_tile × seed_return_rate)`.**
At this fort's likely skill level (no legendary growers yet), that share is
probably close to 100% — there is currently almost no margin to cook or
destroy anything until either Grower skill or fertilizer raises per-tile
yield well above 1.

## 1. Seeds consumed per tile; harvest yield per tile

**Seeds per tile: 1, consumed at planting.** *Community-reported*, current
namespace (v53.16): "Each farm tile requires a single seed to be planted."
[Farming, dwarffortresswiki.org, v53.16 namespace] — matches the DF2014
(pre-v50) namespace verbatim, so this appears stable across the v50
rewrite, but it is not something the raws expose (farm-plot planting is a
hardcoded job, not a `[REACTION]`) — **not independently verified from this
install's files.**

**Harvest yield: 0-10 plants per tile, from a formula base + fertilizer +
skill, each term added by a coin-flip.** The most detailed statement of the
formula is on the **DF2014 namespace** (pre-v50) page, quoted verbatim:

> "Base yield is set to 1. If the farm plot is at least 25% fertilized,
> increase yield by rand(2). If the farm plot is at least 50% fertilized,
> increase yield by rand(2). If the farm plot is at least 75% fertilized,
> increase yield by rand(2). If the farm plot is 100% fertilized, increase
> yield by rand(2). If rand(5) is less than the Planting skill for the
> seed, increase yield by rand(2). If rand(10) is less than the Planting
> skill for the seed, increase yield by rand(2). If rand(15) is less than
> the Planting skill for the seed, increase yield by rand(2). If rand(20)
> is less than the Planting skill for the seed, increase yield by rand(2).
> If rand(25) is less than the Planting skill for the seed and rand(3) is
> equal to 0, increase yield by rand(2)."
> [DF2014:Farming, dwarffortresswiki.org]

`rand(2)` is a coin flip adding 0 or 1. Base 1, + up to 4 from fertilizer (4
independent coin flips, one per 25% fertilization threshold), + up to 5 from
skill (5 more coin flips, each gated on a random threshold check against
Grower/Planting skill, the fifth also gated by a 1-in-3 chance) — maximum
10, minimum 1. At skill 0, every skill-gated flip's condition
(`rand(N) < 0`) is never true, so an unskilled, unfertilized planter nets
**exactly 1 plant per tile, every time, no randomness** — the floor is
deterministic, not the ceiling.

**Confidence: community_prior, explicitly the pre-v50 (DF2014) namespace.**
The current v53.16 namespace page states only the summary range and two
data points, not the formula: *"each planted tile will yield a stack of
1-10 plants each harvest cycle... Legendary+5 planters more frequently
produce larger stacks — up to 6 plants each (average 3.17) without
fertilizer, or up to 10 plants each (average 5.17) fertilized."* [Farming,
v53.16 namespace] — consistent with the DF2014 formula's 1-10 range and with
a skill-20 cap, which is some evidence the mechanic did not change in the
v50 rewrite, but the exact `rand()` breakdown itself is **not
independently re-published for v53.16 and was not verified against this
install's binary** (DF's simulation code is closed-source; only the raws
are inspectable, and farm-plot yield is not raw-defined).

**CLUSTERSIZE:5, present on all six crops' raws, is a different mechanic**
(wild-plant clustering density for outdoor/cavern gathering) and does **not**
govern farm-plot harvest size — flagged here because it is easy to
mis-read as a yield-per-tile figure. *Verified from raws.*

## 2. Seed return per fate

**The load-bearing finding: three fates are raw-defined `[REACTION]`s with an
explicit `PRODUCT:100:1:SEEDS` token — guaranteed, not random.**

Read directly from `data/vanilla/vanilla_reactions/objects/reaction_other.txt`
on VM 103 (paths under the game's Linux install root, `/opt/df/game`):

```
[REACTION:BREW_DRINK_FROM_PLANT]
    [REAGENT:plant:1:PLANT:NONE:NONE:NONE]
        [HAS_MATERIAL_REACTION_PRODUCT:DRINK_MAT]
        [UNROTTEN]
    [PRODUCT:100:5:DRINK:NONE:GET_MATERIAL_FROM_REAGENT:plant:DRINK_MAT]
    [PRODUCT:100:1:SEEDS:NONE:GET_MATERIAL_FROM_REAGENT:plant:SEED_MAT]

[REACTION:PROCESS_PLANT_TO_BAG]        <- quarry bush leaves
    [REAGENT:plant:1:PLANT:NONE:NONE:NONE]
        [HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM]
        [UNROTTEN]
    [PRODUCT:100:5:GET_ITEM_DATA_FROM_REAGENT:plant:BAG_ITEM]
    [PRODUCT:100:1:SEEDS:NONE:GET_MATERIAL_FROM_REAGENT:plant:SEED_MAT]

[REACTION:MAKE_SLURRY_FROM_PLANT]      <- pig tail papermaking
    [REAGENT:plant:1:PLANT:NONE:NONE:NONE]
        [HAS_MATERIAL_REACTION_PRODUCT:PRESS_PAPER_MAT]
        [UNROTTEN]
    [PRODUCT:100:1:GLOB...][PRODUCT_PASTE]
    [PRODUCT:100:1:SEEDS:NONE:GET_MATERIAL_FROM_REAGENT:plant:SEED_MAT]
```

Reading the `[PRODUCT:probability:count:...]` token: the first number is a
percent chance, the second a quantity. **`100:1` is not "up to 1", it is
"always exactly 1."** *Verified from raws — the strongest claim in this
report.* This directly answers "does the seed come from the plant being
consumed, or elsewhere": `GET_MATERIAL_FROM_REAGENT:plant:SEED_MAT` ties the
produced seed's material to the very plant reagent being consumed in that
same reaction firing — **it is the same plant, not a separate seed source.**
*Verified from raws.*

All three reactions gate on `[UNROTTEN]` on the plant reagent. **A rotten
plant cannot fire any of these three reactions — it returns zero seed by
construction**, regardless of which method would otherwise have been
chosen. *Verified from raws* (direct inference from the reagent tag, not a
tested live rot).

**Cooking: verified zero, by two independent sources.** DFHack's own
installed tool doc (`hack/docs/docs/tools/seedwatch.txt`, part of the
shipped software, version-exact to this install) states plainly: *"Unlike
brewing and other kinds of processing, cooking plants does not produce a
usable seed."* Cross-checked against `ban-cooking.txt`'s "seeds" item class
existing specifically because "seeds can be cooked, but if you cook them
all, then your farmers will have nothing to plant." **Confidence: high** —
this is the installed software's own documented behavior, not a wiki claim,
though it is DFHack's doc of engine behavior rather than the DF raws
themselves. This corroborates the existing doctrine entry
`never-cook-seed-items` (status `verified`, live `plotinfo.kitchen` read).

**Milling (to powder), pig tail's actual thread output, and sweet pod's
extract/syrup: NOT raw-defined, and NOT verifiable from this install.**
Grepping every `[REACTION:...]` in the shipped reaction raws found no
entry producing flour, sugar, dimple dye, thread, or barrel/vial extract.
Instead, `hack/lua/plugins/workflow.lua` and `hack/data/orders/basic.json`
show these are **hardcoded `df.job_type` values** — `MillPlants`,
`ProcessPlants` (mapped to `'THREAD'`), `ProcessPlantsBarrel`,
`ProcessPlantsVial` — distinct from the raw-driven `CustomReaction` job type
that brewing/bagging/papermaking use. *Verified from
`hack/lua/plugins/workflow.lua:199-202` and `hack/data/orders/basic.json`
that these are separate hardcoded job types; **not verified** whether or
what seed chance they carry, because DF's simulation binary is
closed-source and nothing in the installed text files defines it.* The
wiki's "1 or 2 seeds" claim (`Seed`, v53.16 namespace: *"When a plant is
eaten or used in brewing, milling or plant processing, it leaves one or two
plantable seeds"*) most likely describes exactly this ungated set of jobs —
**community_prior, current namespace, unverified against source.**

**Eating raw:** wiki (`Seed`, v53.16 namespace) lists raw consumption as
seed-producing alongside brewing/milling/processing. The older DF2014
namespace carries a caveat not repeated in the current page — *"presently
dwarves will rather starve than eat a seed raw"* — which on inspection is
about a much older AI-preference quirk (dwarves declining to willingly eat
raw plants) rather than about seeds specifically, and its absence from the
current page suggests it may be stale. **Community_prior, mixed
namespaces, low confidence on the caveat; not independently tested** (would
require watching a live dwarf snack on a raw plant, which this pass did not
do to stay light-touch on the paused fort).

**Left unharvested / destroyed at season end:** *"Immature plants are
destroyed if their crop cannot grow in the next season, yielding neither
seed nor plant."* [Farming, v53.16 namespace] — **community_prior,
current namespace, not raw-verified** (season-transition plant destruction
is hardcoded, not exposed as a reaction).

**Vermin:** *verified from raws.* Every one of the six crops' `SEED`
material carries `[EDIBLE_VERMIN]` (confirmed directly in each crop's raw
block, §3 below) — stored seed stock is structurally vulnerable to vermin
consumption. This is a real, raw-confirmed loss vector, though this pass
could not verify its practical frequency without observing a live
infestation.

## 3. Per-crop differences among the six fort crops

All six read directly from
`data/vanilla/vanilla_plants/objects/plant_standard.txt` on VM 103.
*Verified from raws throughout this table.*

| Crop (raw ID) | GROWDUR | Brewable | Millable | Processable | Edible raw (plant) | Edible cooked (plant) | Seed-specific notes |
|---|---|---|---|---|---|---|---|
| Plump helmet (`MUSHROOM_HELMET_PLUMP`) | 300 (25 days) | Yes → dwarven wine | No | No | Yes | Yes | Only crop with both `EDIBLE_RAW`/`EDIBLE_COOKED` on the structural (mushroom) material *and* the classic brew path. Grows all four seasons. |
| Pig tail (`GRASS_TAIL_PIG`) | 300 (25 days) | Yes → dwarven ale | No (via powder) | Yes — papermaking (verified raw reaction, `[PRODUCT:100:1:SEEDS]`) **and** thread (hardcoded `ProcessPlants` job, unverified seed chance) | No | No | Structural material has **no** `EDIBLE_*` tags at all — the plant itself is not food, only its drink/thread/paper products are. Summer/autumn only. |
| Cave wheat (`GRASS_WHEAT_CAVE`) | 500 (~42 days) | Yes → dwarven beer | Yes → flour (hardcoded `MillPlants`, unverified seed chance) | No | No (structural mat: `EDIBLE_VERMIN` only) | Yes, but only the **milled flour**, not the raw plant | Summer/autumn only. |
| Sweet pod (`POD_SWEET`) | 500 (~42 days) | Yes → dwarven rum | Yes → sugar (hardcoded, unverified) | No (thread/bag) — but has its own `ProcessPlantsBarrel`/`Vial` extract-to-syrup path (hardcoded, unverified) | No | Only via milled sugar or extracted syrup, not the raw plant | Spring/summer only — shortest growing window of the six. |
| Quarry bush (`BUSH_QUARRY`) | 500 (~42 days) | No | No | Yes — `[PROCESS_PLANT_TO_BAG]`, **verified 100%/1-seed raw reaction**, produces leaves + guaranteed seed (rock nut) | No (structural mat) | Only the leaves (`LEAF` growth) and the seed itself | **Its `SEED` material (the rock nut) uniquely carries `EDIBLE_RAW` as well as `EDIBLE_COOKED`/`EDIBLE_VERMIN`, and a `PRESS_LIQUID_MAT` link to oil.** Rock nuts double as edible food/pressable-oil source *and* seed stock — a dwarf snacking on a raw rock nut, or a press-oil job, consumes actual seed stock directly. This is the one crop where "seed" and "food/press item" are the same physical item. |
| Dimple cup (`MUSHROOM_CUP_DIMPLE`) | 500 (~42 days) | No | Yes → midnight-blue dye (hardcoded `MillPlants`, unverified seed chance) | No | No | No — structural material has **zero** `EDIBLE_*` tags | The only fort crop with no food value in any form. Its single use is milling to dye, which the wiki claims still returns seed like other milling — if true, this crop's entire economy is "recycle nearly all of it back to seed, sell/use a little dye," with no cooking option to even accidentally burn seed stock. |

## 4. Seed stock caps and loss mechanisms

**Seed caps: verified directly from this install's own config, not just
the wiki.** `data/init/d_init_default.txt` (the shipped default) and the
**live fort's own** `~/.local/share/Bay 12 Games/Dwarf Fortress/prefs/d_init.txt`
(checked on VM 103, currently unmodified from default) both read:

```
[SPECIFIC_SEED_CAP:200]
[FORTRESS_SEED_CAP:3000]
```

with the shipped comment: *"Use the specific seed cap to set the maximum
number of seeds of each kind generally allowed in the fortress. Use the
fortress seed cap to control the overall number of seeds allowed. Seeds
over the global cap will be periodically removed, starting with the oldest
and most worthless seeds."* **Confidence: verified, this install's own live
config file**, the strongest possible source short of watching it trigger.
This fort (59 seeds total, 34 plump helmet) is nowhere near either cap.

The behavioral detail — that seed-producing reactions simply stop granting
new seed of a type once that type is at/above 200, rather than erroring —
is the wiki's gloss (`Seed`, v53.16 namespace: *"Seed-producing activities
will only produce seeds if your fortress contains fewer than 200 seeds of
that species"*) and is **community_prior**, not independently verified
against source, though it is a plausible reading of the init comment above.

**Seeds do not rot; harvested plants do.** *Verified from raws*:
`SEED_TEMPLATE` in `data/vanilla/vanilla_materials/objects/material_template_default.txt`
(line ~2131) has no `[ROTS]` tag, while `STRUCTURAL_PLANT_TEMPLATE` (the
harvested-plant material every one of the six crops uses) does carry
`[ROTS]` (line ~2129, immediately before). Combined with the `[UNROTTEN]`
reagent requirement on every seed-yielding reaction (§2), this means the
real seed-stock risk is not "seeds rot in storage" but **"harvested plants
rot before being processed, taking their would-be seed return down with
them."** Timely processing after harvest, not seed storage conditions, is
the thing to watch.

**Vermin can eat stored seed.** *Verified from raws* — every crop's `SEED`
material carries `[EDIBLE_VERMIN]` (§3). Not independently observed live.

## 5. Surplus disposal

**Atom smasher (drawbridge):** *community_prior, current v53.16 namespace* —
still functions post-v50 rewrite per the wiki's own current-namespace page,
mechanically: raise a bridge, drop items/creatures beneath it, lower (or
raise onto a walled/enclosed target) to destroy. Documented caveat worth
flagging for seeds specifically, since seeds are commonly bag-stored:
*"Sand or dye in bags don't get erased while the bag does"* — i.e. some
loose granular contents have been reported to survive a smash that destroys
their container. **Whether this applies to seeds specifically was not
confirmed** — the wiki only names sand and dye, and this pass did not test
it live (would require designating a dump/atom-smasher pit on the paused
fort, outside the read-only brief). Treat "atom smasher reliably destroys
bagged seeds" as **unverified**, not confirmed, until tested or until a more
specific source is found. Also verified (community_prior): creatures over
1,200,000 size units block the bridge — irrelevant to seed items.

**Burning (magma or fire): verified plausible from raws + one community
figure.** The `SEED_TEMPLATE` material (§4) carries `[IGNITE_POINT:10400]`
and `[HEATDAM_POINT:10500]` — both *verified from raws*, both finite (not
`NONE`), meaning seed items can catch fire and do take heat damage. Magma's
temperature is commonly cited at **12,000 °Urist** (`Temperature`, current
wiki namespace — *community_prior*, DF's builtin-magma material is not
raw-exposed so this could not be checked against this install's text
files). 12,000 comfortably exceeds both the seed material's ignite point
(10,400) and heat-damage point (10,500), so **dumping surplus seed into
magma should reliably destroy it** — a reasonable inference chaining a
verified raw figure to a community-reported constant, not a live-tested
result.

**Dumping** (marking items for dump to a garbage zone, chasm, or river) is
the standard, well-known DF disposal path; not tested this pass and not
raw-specific to seeds — flagged as **unverified for this report** simply
because it wasn't checked, not because there's reason to doubt it.

**Practical gotcha found in this pass, not the wiki:** because rock nuts
(quarry bush's seed) are also directly `EDIBLE_RAW`/`EDIBLE_COOKED` food and
an oil-press input (§3), "destroy quarry bush surplus" and "quarry bush
gets eaten/pressed" are not cleanly separable the way they are for the
other five crops — a policy that bans cooking seeds fortress-wide (the
existing, verified doctrine entry) will not stop a dwarf from autonomously
snacking on a raw rock nut, since that is governed by `EDIBLE_RAW`, not the
kitchen-banned-item mechanism `ban-cooking`/the live `plotinfo.kitchen`
exclusion covers. This was not tested live; it is a direct reading of the
raw tags cross-referenced against the doctrine's own verification note that
kitchen exclusion covers "every six seed types" — kitchen exclusion is a
different gate from raw-snacking, and this pass did not verify whether DF's
foraging/snack AI is even capable of choosing a `SEEDS`-category item as a
raw snack in practice.

## 6. Break-even formula and reserve

### Model

Per crop, per harvest cycle, assuming a steady planting rate:

- `tiles_planted` — tiles sown this cycle (consumes `tiles_planted` seeds,
  1 per tile, §1).
- `Y` (`plants_per_tile`) — expected harvested plant units per tile (§1,
  formula-derived, driven by Grower skill and fertilization, range 1-10).
- Harvest `H = tiles_planted × Y`.
- Split `H` across fates: fraction `f` goes through a seed-returning method
  (brew / quarry-bush-bag / pig-tail-paper, each verified 100%×1; or
  milling/thread/extract, community-claimed 1-2 but unverified), fraction
  `(1 - f)` goes through cooking or another zero-return fate.
- `r` (`seed_return_rate`) — average seeds returned per plant unit *within
  the seed-returning fraction*. Use `r = 1` for the three raw-verified
  100%-guaranteed methods (brewing, quarry-bush-bagging, pig-tail-paper);
  the community-claimed "1 or 2" for milling/thread/extract is unverified,
  so treat `r = 1` as the safe floor unless/until that number is confirmed
  live.

Seeds produced this cycle: `H × f × r`. Seeds consumed next cycle (steady
state): `tiles_planted`. Stock is level-or-rising when:

```
H × f × r  ≥  tiles_planted
(tiles_planted × Y) × f × r  ≥  tiles_planted
Y × f × r  ≥  1
f  ≥  1 / (Y × r)
```

**Break-even rule: the minimum share of the harvest that must go through a
guaranteed seed-returning method is `f_min = 1 / (Y × r)`, clamped to
`[0, 1]`.** At `r = 1` this is simply `f_min = 1 / Y`. An unskilled,
unfertilized planter (`Y = 1`) needs `f_min = 1.0` — **the entire harvest**,
none cookable, no surplus to destroy. A legendary+fertilized planter
(`Y = 5.17` average, per §1) needs only `f_min ≈ 0.19` — roughly a fifth of
the harvest keeps seed stock level, leaving four-fifths free for cooking,
selling, or deliberate destruction.

### Pure function signatures (for direct implementation/unit-testing)

```
def min_seed_return_fraction(
    plants_per_tile: float,   # Y: expected harvest yield per tile this cycle
    seed_return_rate: float,  # r: avg seeds returned per plant unit by the
                               #    seed-returning method chosen; use 1.0 for
                               #    brew/quarry-bush-bag/pig-tail-paper (verified),
                               #    unverified 1-2 for milling/thread/extract
) -> float:
    """
    Returns f_min in [0, 1]: the minimum fraction of a crop's harvest that
    must be routed through a seed-returning processing method to keep that
    crop's seed stock level or rising, assuming a steady planting rate.

    f_min = clamp(1 / (plants_per_tile * seed_return_rate), 0.0, 1.0)

    Raises or returns 1.0 (fully clamped) if plants_per_tile * seed_return_rate
    <= 1: at that yield/return combination, no fraction can be cooked or
    destroyed without shrinking stock; the harvest barely (or does not)
    replace what was planted.
    """

def seed_action_plan(
    current_stock: int,             # seeds on hand for this crop now
    tiles_planned_next_cycle: int,  # tiles this crop will be sown on next
    plants_per_tile: float,         # Y, same as above
    seed_return_rate: float,        # r, same as above
    reserve_cycles: int = 2,        # buffer, in planting cycles, to hold in reserve
    reserve_floor: int = 30,        # DFHack seedwatch/autofarm's own shipped default
    specific_seed_cap: int = 200,   # this install's SPECIFIC_SEED_CAP (verified, d_init.txt)
) -> dict:
    """
    Returns:
      seeds_needed_to_plant: int    # tiles_planned_next_cycle * 1
      min_return_fraction: float    # min_seed_return_fraction(plants_per_tile, seed_return_rate)
      reserve_target: int           # max(reserve_floor, reserve_cycles * tiles_planned_next_cycle),
                                     # capped at specific_seed_cap
      surplus: int                  # max(0, current_stock - reserve_target)
      action: str                   # "destroy_surplus" if surplus > 0 and
                                     #   current_stock > reserve_target
                                     # "hold" if current_stock == reserve_target
                                     # "increase_seed_returning_fraction" if
                                     #   current_stock < reserve_target, i.e.
                                     #   raise f above min_return_fraction, or
                                     #   raise Y (skill/fertilizer), or shrink
                                     #   tiles_planned_next_cycle
    """
```

### Recommended minimum reserve

**`reserve_floor = 30` per crop type**, taken directly from two independent
DFHack tools' own shipped defaults: `seedwatch`'s doc states *"all types are
watched with a target of 30"*, and `autofarm`'s example sets its default
threshold to the same number — *verified from DFHack's own installed tool
docs*, a converged community-tooling convention rather than an arbitrary
pick. In plots-worth of seed, that is **30 tiles' reserve per crop** (since
1 seed plants 1 tile, §1), well under the per-species cap of 200 (verified,
§4), leaving headroom for the cap-driven "stop granting seed above 200"
behavior to never bind at the reserve level.

### Assumptions this rests on, stated plainly

1. **Steady state.** The formula assumes next cycle's `tiles_planted`
   equals this cycle's. An expanding fort (more farm plot tiles next
   season) needs seed beyond break-even to fund that growth; this formula
   alone will under-provide for it.
2. **1 seed per tile is unverified from this install's raws** (§1) — it is
   a stable-seeming community claim across two wiki namespaces, not a
   `[REACTION]` this pass could read.
3. **`r = 1` is a conservative floor, not a proven average**, for any
   crop relying on milling/thread/extract (cave wheat, sweet pod, dimple
   cup's *only* method, and pig tail's thread path) — those are hardcoded
   job types with no raw-exposed seed math (§2). If the community's "1 or
   2" claim is right, `f_min` for those paths is actually lower (more
   forgiving) than this formula computes; this pass could not confirm that,
   so the formula deliberately does not assume the more optimistic number.
4. **Rot and vermin loss are not modeled.** Both are real, raw-confirmed
   loss vectors (§2, §4) sitting outside this formula; the `reserve_cycles`
   buffer is the only cushion against them, not a calculated one.
5. **Quarry bush is a genuine exception to the model as stated**, because
   its "seed" (rock nut) is simultaneously directly-edible food and an
   oil-press input (§3, §5) — raw consumption of rock nuts by dwarves or an
   oil-press job depletes seed stock outside of any of the fates this
   formula's `f`/`(1-f)` split accounts for. Apply the formula to quarry
   bush with extra caution, or track its seed stock net of press/eaten-raw
   losses separately.
6. **Species and fortress-wide caps are not incorporated into `f_min`
   itself** — they only affect the `reserve_target`/cap ceiling in
   `seed_action_plan`. Near the 200 cap, the marginal value of routing more
   harvest through a seed-returning method drops to near zero (the game
   won't grant the seed anyway, per the wiki's gloss on the cap, §4,
   unverified against source) — the formula does not currently detect or
   exploit that saturation point.
7. **Dimple cup has `f = 1` forced**, not chosen — milling is its only
   method, so there is no cooking/destroying lever for it short of
   deliberately not harvesting it or atom-smashing surplus after the fact.

## Figures table

| figure | subject | value | unit | condition | source | game_version | status |
|---|---|---|---|---|---|---|---|
| seeds_per_tile_planted | ALL | 1 | seed/tile | at planting | Farming, dwarffortresswiki.org | v53.16 wiki namespace | community_prior |
| harvest_yield_base | ALL | 1 | plant/tile | skill 0, 0% fertilized | DF2014:Farming, dwarffortresswiki.org | DF2014 (pre-v50) namespace | community_prior |
| harvest_yield_max | ALL | 10 | plant/tile | skill ≥20 (legendary+5), 100% fertilized | DF2014:Farming + Farming (v53.16), dwarffortresswiki.org | DF2014 formula; range corroborated on v53.16 page | community_prior |
| harvest_yield_avg_unfertilized_legendary | ALL | 3.17 | plant/tile | Grower skill legendary+5, 0% fertilized | Farming, dwarffortresswiki.org | v53.16 wiki namespace | community_prior |
| harvest_yield_avg_fertilized_legendary | ALL | 5.17 | plant/tile | Grower skill legendary+5, 100% fertilized | Farming, dwarffortresswiki.org | v53.16 wiki namespace | community_prior |
| fertilizer_yield_bonus_max | ALL | 4 | plant/tile | 100% fertilized, 4 independent rand(2) checks at 25/50/75/100% thresholds | DF2014:Farming, dwarffortresswiki.org | DF2014 (pre-v50) namespace | community_prior |
| fertilizer_potash_cost | ALL | floor(plot_size/4)+1 | potash/season | per fertilized plot | DF2014:Farming, dwarffortresswiki.org | DF2014 (pre-v50) namespace | community_prior |
| seed_return_chance_brew | MUSHROOM_HELMET_PLUMP, GRASS_TAIL_PIG, GRASS_WHEAT_CAVE, POD_SWEET | 100 | percent | per plant unit reagent, [UNROTTEN] required | reaction_other.txt, REACTION:BREW_DRINK_FROM_PLANT, `[PRODUCT:100:1:SEEDS...]` | 53.16 raws | verified_raws |
| seed_return_count_brew | MUSHROOM_HELMET_PLUMP, GRASS_TAIL_PIG, GRASS_WHEAT_CAVE, POD_SWEET | 1 | seed/plant unit | same reaction | reaction_other.txt, REACTION:BREW_DRINK_FROM_PLANT | 53.16 raws | verified_raws |
| drink_yield_per_plant_brew | same 4 crops | 5 | drink-dimension units/plant unit | PRODUCT_DIMENSION:150 per barrel | reaction_other.txt, REACTION:BREW_DRINK_FROM_PLANT | 53.16 raws | verified_raws |
| seed_return_chance_quarry_bush_bag | BUSH_QUARRY | 100 | percent | per plant unit, [UNROTTEN] required | reaction_other.txt, REACTION:PROCESS_PLANT_TO_BAG | 53.16 raws | verified_raws |
| seed_return_count_quarry_bush_bag | BUSH_QUARRY | 1 | seed/plant unit | same reaction | reaction_other.txt, REACTION:PROCESS_PLANT_TO_BAG | 53.16 raws | verified_raws |
| seed_return_chance_pigtail_paper | GRASS_TAIL_PIG | 100 | percent | per plant unit, [UNROTTEN] required, papermaking path only (not thread) | reaction_other.txt, REACTION:MAKE_SLURRY_FROM_PLANT | 53.16 raws | verified_raws |
| seed_return_count_pigtail_paper | GRASS_TAIL_PIG | 1 | seed/plant unit | same reaction | reaction_other.txt, REACTION:MAKE_SLURRY_FROM_PLANT | 53.16 raws | verified_raws |
| seed_return_on_cook | ALL | 0 | seed | cooking in a kitchen | hack/docs/docs/tools/seedwatch.txt (DFHack, installed) | DFHack 53.16-r1.1 | verified (tool doc, not raw) |
| seed_return_milling_thread_extract | GRASS_WHEAT_CAVE (flour), POD_SWEET (sugar/syrup), MUSHROOM_CUP_DIMPLE (dye), GRASS_TAIL_PIG (thread) | 1-2 | seed/plant unit (claimed) | hardcoded job types MillPlants/ProcessPlants/ProcessPlantsBarrel/Vial; no raw text defines this | Seed, dwarffortresswiki.org; cross-ref hack/lua/plugins/workflow.lua:199-202 for job-type names only | v53.16 wiki namespace (claim); 53.16 install (job-type names only) | community_prior (chance/count unverified; job-type existence verified) |
| seed_return_eat_raw | ALL edible-raw crops | unspecified (claimed nonzero) | seed/plant unit | dwarf eats plant raw | Seed, dwarffortresswiki.org | v53.16 wiki namespace | community_prior |
| seed_return_unharvested | ALL | 0 | seed | immature plant destroyed at season change | Farming, dwarffortresswiki.org | v53.16 wiki namespace | community_prior |
| seed_source_is_same_plant | ALL | true | boolean | seed material tied via GET_MATERIAL_FROM_REAGENT:plant:SEED_MAT | reaction_other.txt, all three verified reactions | 53.16 raws | verified_raws |
| specific_seed_cap | ALL | 200 | seeds/species | fortress-wide, this crop's type | d_init_default.txt AND live fort's own d_init.txt on VM 103 | 53.16 install (live-config verified) | verified_raws (config file) |
| fortress_seed_cap | ALL | 3000 | seeds total | fortress-wide, all species | d_init_default.txt AND live fort's own d_init.txt on VM 103 | 53.16 install (live-config verified) | verified_raws (config file) |
| seed_cap_enforcement | ALL | seeds not granted above species cap; global-cap overflow "periodically removed, starting with the oldest and most worthless" | behavior | at/above cap | d_init_default.txt comment (mechanism description); Seed wiki page (per-species gloss) | 53.16 install config comment (verified) + v53.16 wiki namespace (gloss, community_prior) | mixed — cap values verified_raws, exact trigger behavior community_prior |
| seed_material_rots | ALL | false | boolean | SEED_TEMPLATE has no [ROTS] tag | material_template_default.txt, MATERIAL_TEMPLATE:SEED_TEMPLATE | 53.16 raws | verified_raws |
| harvested_plant_rots | ALL | true | boolean | STRUCTURAL_PLANT_TEMPLATE has [ROTS] | material_template_default.txt, MATERIAL_TEMPLATE:STRUCTURAL_PLANT_TEMPLATE | 53.16 raws | verified_raws |
| seed_vulnerable_to_vermin | ALL | true | boolean | SEED material carries [EDIBLE_VERMIN] | plant_standard.txt, each crop's SEED material block | 53.16 raws | verified_raws |
| seed_requires_unrotten_to_process | MUSHROOM_HELMET_PLUMP, GRASS_TAIL_PIG, GRASS_WHEAT_CAVE, POD_SWEET, BUSH_QUARRY | true | boolean | [UNROTTEN] reagent tag on all 3 verified seed-yielding reactions | reaction_other.txt | 53.16 raws | verified_raws |
| growdur_plump_helmet | MUSHROOM_HELMET_PLUMP | 300 | growdur units (~25 days) | year-round (all 4 seasons) | plant_standard.txt, [GROWDUR:300] | 53.16 raws | verified_raws |
| growdur_pig_tail | GRASS_TAIL_PIG | 300 | growdur units (~25 days) | summer/autumn | plant_standard.txt, [GROWDUR:300] | 53.16 raws | verified_raws |
| growdur_cave_wheat | GRASS_WHEAT_CAVE | 500 | growdur units (~42 days) | summer/autumn | plant_standard.txt, [GROWDUR:500] | 53.16 raws | verified_raws |
| growdur_sweet_pod | POD_SWEET | 500 | growdur units (~42 days) | spring/summer | plant_standard.txt, [GROWDUR:500] | 53.16 raws | verified_raws |
| growdur_quarry_bush | BUSH_QUARRY | 500 | growdur units (~42 days) | spring/summer/autumn | plant_standard.txt, [GROWDUR:500] | 53.16 raws | verified_raws |
| growdur_dimple_cup | MUSHROOM_CUP_DIMPLE | 500 | growdur units (~42 days) | year-round (all 4 seasons) | plant_standard.txt, [GROWDUR:500] | 53.16 raws | verified_raws |
| rock_nut_edible_raw | BUSH_QUARRY | true | boolean | quarry bush's SEED material uniquely carries [EDIBLE_RAW] | plant_standard.txt, BUSH_QUARRY SEED block | 53.16 raws | verified_raws |
| seed_ignite_point | ALL | 10400 | °Urist | SEED_TEMPLATE material | material_template_default.txt, [IGNITE_POINT:10400] | 53.16 raws | verified_raws |
| seed_heatdam_point | ALL | 10500 | °Urist | SEED_TEMPLATE material | material_template_default.txt, [HEATDAM_POINT:10500] | 53.16 raws | verified_raws |
| magma_temperature | n/a | 12000 | °Urist | builtin magma material, not raw-exposed | Temperature, dwarffortresswiki.org | current wiki namespace | community_prior |
| atom_smasher_survivors | n/a (sand, dye in bags) | container destroyed, granular contents reportedly survive | behavior | bagged granular items | Dwarven atom smasher, dwarffortresswiki.org | v53.16 wiki namespace | community_prior (not confirmed for seeds specifically) |
| dfhack_seedwatch_default_target | ALL | 30 | seeds | DFHack seedwatch tool default | hack/docs/docs/tools/seedwatch.txt | DFHack 53.16-r1.1 (installed) | verified (tool doc) |
| dfhack_seedwatch_reenable_threshold | ALL | target+20 | seeds | cooking re-allowed above this | hack/docs/docs/tools/seedwatch.txt | DFHack 53.16-r1.1 (installed) | verified (tool doc) |
| dfhack_autofarm_default_threshold_example | ALL | 30 | seeds | autofarm tool usage example | hack/docs/docs/tools/autofarm.txt | DFHack 53.16-r1.1 (installed) | verified (tool doc) |
| break_even_min_return_fraction | ALL | f_min = 1/(Y×r) | fraction, [0,1] | derived, see §6 | derived in this report from §1+§2 figures | n/a (derived) | derived |

## What could not be verified

- The exact seed-return probability/count for milling (flour, sugar, dye),
  pig tail's thread output, and sweet pod's extract/syrup — these are
  hardcoded engine job types with no corresponding text in the installed
  raws; DF's simulation binary is closed-source, so this is a hard ceiling
  on what a raws-and-docs read can settle, not a gap in this pass's effort.
- Whether the community's "1 or 2 seeds" figure for those same jobs is
  accurate for v53.16 specifically, versus carried forward unchanged from
  an older namespace.
- Whether the atom smasher's reported "bagged granular contents survive"
  quirk (documented for sand and dye) applies to bagged seeds.
- Whether dumping (designated dump + garbage zone/chasm/river) actually
  destroys or merely relocates seed items — not checked this pass.
- Whether a dwarf can and will autonomously eat a raw rock nut (quarry
  bush's dual-purpose seed) in practice, and how often — flagged as a
  structural possibility from the raws (§3, §5), not observed live.
- The DF2014-namespace claim that dwarves historically declined to eat
  seeds raw ("will rather starve than eat a seed raw") — unclear if this
  is still true, stale, or was never really about seeds as opposed to raw
  plants generally; not repeated on the current namespace page.
- Live confirmation of vermin actually depleting stored seed on this fort,
  or of a rotten harvest failing to yield seed when actually attempted —
  both are direct, high-confidence inferences from raw tags (§2, §4) but
  neither was staged and observed on the live, paused fort, consistent with
  the read-only brief.

## Relevant to

- `doctrine/seed.yaml`'s `seed-stock-never-falls` and
  `cooking-plants-costs-seeds` entries — this report both confirms
  (cooking costs seed stock, verified two ways) and refines
  ("randomness" applies to a narrower set of methods than the doctrine
  currently implies, and three methods are provably deterministic) the
  existing priors. Not edited here per the research brief; left for the
  orchestrator to fold in.
- Any future `get_doctrine`/farm-management tool that needs a
  machine-checkable rule instead of "manage the split carefully" — §6's
  function signatures are written to be implemented directly.
- A prospective structured game-figures database/calculator (this session's
  addition to the brief) — the Figures table above is meant to seed exactly
  that.
