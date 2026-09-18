# Community figures for the production graph: containers, job times, hauling, workshop throughput

Date: 2026-09-18. Desk research only: DF wiki (dwarffortresswiki.org) pages
fetched directly (mostly via raw wikitext, `action=raw`, to avoid a
summarizing model's paraphrase where exact digits matter) plus targeted web
search to locate the right pages. No SSH to VM 103, no DFHack call, no
deploy, no game state touched; the fort stayed paused throughout, and
nothing here was read from the live install. This is the follow-up the user
asked for after `research/2026-09-18-production-graph.md` confirmed job
duration, the skill-to-speed curve, hardcoded job-type yield math, and
barrel/bin/bucket capacity are compiled into the DF binary with zero raw
token: gather wiki/community figures for those gaps instead of building a
work-sampling loop (explicit user decision, not revisited here).

**Status vocabulary used below is `doctrine/seed.yaml`'s exactly**: `prior`
(received knowledge, not yet confirmed by this project's play or its own
game-data reads) or `refuted`. Nothing in this report is promoted to
`verified`, because `verified` needs a live-read or game-data source that
describes 53.16, and every figure below traces to the wiki, a
community-tooling convention, or is absent entirely. Every wiki-derived
figure here is `community_prior` in `research/2026-09-17-seed-ratios.md`'s
finer vocabulary, which this report also uses in its tables for
consistency with that precedent.

**Namespace convention** (dwarffortresswiki.org): an unprefixed page name
(`Barrel`, `Skill`, `Time`) is the **current namespace**, covering the
v50+/Steam era including this fort's v53.16, unless the page itself flags
otherwise. A `DF2014:`-prefixed page is the **pre-v50 namespace**, and this
project has already been burned once by treating a DF2014 figure as current
(`docs/MEMORY-ARCHITECTURE.md`; `research/2026-09-17-seed-ratios.md` §1's
yield formula is the concrete precedent). Every row below states which
namespace it came from; a DF2014-only figure is flagged as weaker and nothing
here blends the two silently.

## Bottom line

**Container capacity is the one scope item that came back with real, precise
numbers**, and the reason is structural: the wiki's `Barrel`, `Bin`, and
`Bucket` pages carry an infobox with explicit `size=`/`capacity=` fields in
cm³, the same volume unit the raws already use for `[SIZE:n]` on
raw-moddable items (confirmed live in `research/2026-09-18-production-graph.md`
for jug/large pot). That gives every container figure below a real unit to
join against the hypergraph's existing volume-based nodes, not just a bare
number. **A genuinely new finding this pass**: wheelbarrow and minecart are
*not* in the same hardcoded-with-no-raw-token bucket as barrel/bin/bucket.
The wiki's own `Wheelbarrow` page cites `{{Gamedata|{{raw|v50:item_tool.txt|
ITEM_TOOL|ITEM_TOOL_WHEELBARROW}}}}`, meaning wheelbarrow (and by the same
logic minecart) is a raw-moddable `ITEM_TOOL` entry like jug and large pot,
not a top-level hardcoded `df.item_type` like barrel/bin/bucket. Their
capacity is plausibly raw-verifiable on the live install; this pass did not
do that read, but it names a real, cheap path to promote those two figures
past `prior` later (see per-section "live read" column).

**Job time is close to a total blank, and that blank is itself the finding.**
Every reaction/workshop page checked (`Still`, `Kitchen`, `Reaction`,
current-namespace `Mining`) explicitly discusses inputs, outputs, and
qualitative speed factors but states no tick count, second count, or
abstract time unit for any specific job. The sole concrete number found
anywhere is a **DF2014-namespace-only** worked example on `DF2014:Miner`
(zero-skill vs. Proficient vs. Legendary mining), which the current-namespace
`Mining` page does not restate, corroborate, or contradict, it simply omits
the topic. Treat that one number as the weakest kind of prior in this
report: pre-v50, unconfirmed against 53.16, and the only wiki source for the
whole "job time" scope item.

**Hauling and movement have real figures for vehicles and pathing, none for
a bare-handed dwarf.** Wheelbarrow/minecart capacity, dwarf gait speed
baselines, and (per the coordinator's scope addition) the four traffic-
designation cost multipliers are all wiki-stated with numbers. Hand-hauling
load (how much a dwarf carries unassisted) is not stated anywhere found.

**Workshop throughput and labour availability is the one scope item the user
told this pass to stop cold on rather than force, and that is exactly what
happened.** The wiki states a workshop's task-queue cap (10) and nothing
about concurrent job throughput. It states sleep/thirst/food *decay
intervals* (real numbers, current namespace) but never combines them, or
socializing, into an aggregate "fraction of a dwarf's time actually
productive" figure. **No such figure exists on the wiki. This report does
not construct one from the interval figures**, per the brief's explicit
instruction; synthesizing a percentage from unrelated interval numbers would
be this project's own estimate wearing a wiki citation, which is precisely
the false-precision failure mode the brief warned against.

**The skill-to-speed curve has three data points, all DF2014-namespace, all
about mining specifically, not a general formula.** The current-namespace
`Skill` and `Reaction` pages both discuss skill's effect on **quality**
(`SKILL_ROLL_RANGE`) in numeric detail but are explicit that no formula for
**speed** is stated; this is a real, verified-by-reading-both-namespaces
absence, not a search failure.

## 1. Container capacity: barrel, bin, bucket

| Figure | Value | Unit | Source URL | Namespace | Live read that could settle it later | Status |
|---|---|---|---|---|---|---|
| barrel_size | 20,000 | cm³ (item's own volume) | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | none needed if raw-exposed; confirmed this project's own prior research found barrel has **no raw item definition at all** (`research/2026-09-18-production-graph.md` §2), so this stays wiki-only | community_prior |
| barrel_capacity | 60,000 | cm³ (contents volume) | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | a non-mutating DFHack read of a real full barrel's contained-item list and summed volume once Uniboslan's still actually produces drink, mirroring the exact live-read idea `research/2026-09-18-production-graph.md` §2 already names for this container | community_prior |
| barrel_capacity_meals_plants_cheese | 60 | item count | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | same as above | community_prior |
| barrel_capacity_meat_fish | 30 | item count | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | same as above | community_prior |
| barrel_capacity_lye_milk | 100 | units | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | same as above | community_prior |
| barrel_capacity_eggs | 6000 | item count, "regardless of size" | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | same as above | community_prior |
| barrel_capacity_alcohol | "any number of units... but only a single stack" | drink-dimension units, capped by stack not volume | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | same as above; a live read of an actual brewed barrel's stack size would show what "one stack" tops out at in practice for this fort's own brewing batch sizes | community_prior |
| barrel_capacity_embark_alcohol | 5 | drink units per embark barrel | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | n/a, describes embark-specific stack size, not a general cap | community_prior |
| barrel_value | 10 | ☼ (value) | https://dwarffortresswiki.org/index.php/Barrel | current (v53.16) | raw-verified already: `[VALUE:n]` is raw-exposed for jug/pot per `research/2026-09-18-production-graph.md`; barrel itself has no raw file, so this stays wiki-only | community_prior |
| bucket_size | 3,000 | cm³ | https://dwarffortresswiki.org/index.php/Bucket | current (v53.16) | a live DFHack read of `world.items.other.BUCKET` for the item's own reported size field, if DFHack exposes it structurally even without a raw token | community_prior |
| bucket_capacity | 6,000 | cm³ | https://dwarffortresswiki.org/index.php/Bucket | current (v53.16) | a non-mutating read of a real full bucket's contained liquid volume, next time one is drawn from a water source on this fort | community_prior |
| bin_size | 15,000 | cm³ | https://dwarffortresswiki.org/index.php/Bin | current (v53.16) | same class of live read as barrel, once a bin holds a known quantity of one item type | community_prior |
| bin_capacity | 60,000 | cm³ | https://dwarffortresswiki.org/index.php/Bin | current (v53.16) | same | community_prior |
| bin_capacity_bars_blocks | 12 | item count | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |
| bin_capacity_bolts | 400 | item count | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |
| bin_capacity_coins | 193 | stacks of 500 coins each | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |
| bin_capacity_cloth | 303 | item count | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |
| bin_capacity_leather | 45 | item count | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |
| bin_capacity_small_gems | 305 | item count | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |
| bin_capacity_thread | 205 | item count | https://dwarffortresswiki.org/index.php/Using_bins_and_barrels | current (v53.16) | same | community_prior |

**Unit conflation warning, stated explicitly as the brief asked**: the
per-item-type counts above (60 meals, 12 bars, 400 bolts, etc.) are **item
or stack counts**, not volume, and they do not derive cleanly from the
60,000 cm³ headline capacity figure by simple division (60,000 / 12 = 5,000
cm³ implied per bar/block, which does not match any bar/block size figure
this pass checked). Treat the per-type counts and the cm³ headline as **two
different wiki claims about the same item, not one figure two ways**; do not
average or reconcile them in the schema, store both with their own
provenance and let `production_node`'s `volume` field carry only the cm³
figures, which are the ones directly comparable to the raw `[SIZE:n]`
figures already in the schema.

**A structural nuance worth carrying into the schema**: the alcohol row's
"any number... single stack" phrasing means barrel capacity for drink is
**not actually bound by the 60,000 cm³ figure at all** in the way the meal/
meat/lye/egg rows are; it is bound by whatever one brewing job's product
stack size turns out to be. `research/2026-09-18-production-graph.md`
already established (verified from raws) that one `BREW_DRINK_FROM_PLANT`
firing yields `5 × plant_reagent_count` drink units at 150 cm³ each; a
large single brewing job (a big plant stack) could in principle produce a
drink stack whose volume exceeds 60,000 cm³, and the wiki's own wording
implies the barrel would still hold it as "a single stack," contradicting a
naive read of the capacity field. **This tension is reported, not resolved**:
this pass found no source reconciling "capacity: 60,000 cm³" against
"holds any number of units of alcohol." Flag `barrel_capacity` and
`barrel_capacity_alcohol` as two claims in tension, not two ways of stating
the same fact.

**Wheelbarrow and minecart, an orthogonal but valuable finding**: unlike
barrel/bin/bucket, these two carry a `{{Gamedata|...}}` citation on their
wiki pages pointing at `item_tool.txt`, meaning they are raw-moddable
`ITEM_TOOL` entries, structurally identical to jug and large pot (already
raw-verified in `research/2026-09-18-production-graph.md`), not top-level
hardcoded types. Their figures are reported in §3 (hauling) since that is
their functional role, but the live-read path for them is stronger than for
the three true containers: **a direct grep of this install's own
`item_tool.txt` for `ITEM_TOOL_WHEELBARROW`/`ITEM_TOOL_MINECART`'s
`[SIZE:n]` token would likely settle their capacity as `verified_raws`
outright**, the same read `research/2026-09-18-production-graph.md` already
performed for jug and large pot. This pass did not do that read (desk
research brief, no SSH), but it is worth doing before the wiki figure for
these two specifically, since it could cost nothing and beat `prior` for
free.

## 2. Job times

**No wiki page found states a job's duration in ticks, seconds, or an
abstract "job time unit" for any of the reactions the brief asked about**,
with one narrow, DF2014-only exception for mining. Pages actually checked
and confirmed silent on timing: `Still` (brewing), `Kitchen` (cooking, all
qualities), `Reaction` and `DF2014:Reaction` (the generic reaction
mechanism), current-namespace `Mining`, `Time` and `DF2014:Time`, `Workshop`.
This is a wide, deliberate spot-check across the mechanism-level pages most
likely to state a general job-time formula, not just the six or so
per-reaction pages the brief named, and it came back empty across both
namespaces, which is itself the strongest form of "not documented" this
report can offer short of reading the DF binary.

| Reaction/job (brief's list) | Wiki time figure found | Unit | Source URL | Namespace | Status |
|---|---|---|---|---|---|
| Brew drink | none | n/a | https://dwarffortresswiki.org/index.php/Still | current (v53.16) | not found |
| Prepare meal (easy/fine/lavish) | none (only qualitative: lavish "takes a bit longer" due to hauling/clutter, not job speed) | n/a | https://dwarffortresswiki.org/index.php/Kitchen | current (v53.16) | not found |
| Mill plants | none | n/a | (no dedicated wiki page found; `Still`/`Kitchen`/`Reaction` checked as the closest analogues) | n/a | not found |
| Make barrel | none | n/a | (no dedicated page found beyond the `Barrel` item page, which has no timing content) | current (v53.16) | not found |
| Cut/make blocks | none | n/a | (no dedicated page found) | n/a | not found |
| Make mechanisms | none | n/a | (no dedicated page found) | n/a | not found |
| Make bucket | none | n/a | (no dedicated page found beyond `Bucket` item page) | current (v53.16) | not found |
| Construct a workshop | none (only the unrelated "10-task queue" figure, §4) | n/a | https://dwarffortresswiki.org/index.php/Workshop | current (v53.16) | not found |
| Dig a tile | **DF2014-only**: 20 job ticks at skill 0 ("5 per 'wear'," soil = 5), ~11 frames/tick, ~215 frames total; 12 job ticks (60% of base) at Proficient (skill 5); 4 job ticks (20% of base) at Legendary (skill 15+) | job ticks + frames, at an unstated FPS | https://dwarffortresswiki.org/index.php/DF2014:Miner | **DF2014 (pre-v50)** | community_prior, weak: current-namespace `Mining` page does not restate this |
| Chop a tree | none found | n/a | (checked `Mining` and general woodcutting search; no dedicated timing page found) | n/a | not found |
| Plant seeds | none | n/a | (`Farming`-adjacent pages checked in `research/2026-09-17-seed-ratios.md` cover yield, not job speed) | n/a | not found |
| Harvest | none | n/a | same as above | n/a | not found |

**The one figure in this section, read carefully**: the DF2014:Miner numbers
describe **mining specifically**, not a general job-time formula, and this
report does not generalize them to any other reaction. Reading it as a
*shape* rather than a promise (as the brief's §5 instruction for the skill
curve also asks): base time, ~60% at skill level 5 (Proficient), ~20% at
skill level 15+ (Legendary), a curve that front-loads most of its benefit at
low-to-mid skill and flattens out, consistent with the current-namespace
`Skill` page's own unquantified claim that "skill levels reduce [job time]
significantly" and "legendary skill can eliminate all time required... down
to a single action." The two namespaces agree in direction and rough shape;
neither gives a number this project can treat as anything but `prior`.

**Live read that would settle any of these later**: `job.completion_timer`
is confirmed to exist on real running jobs (`research/2026-09-18-
production-graph.md` §2, read live off Uniboslan's own job queue). The
honest, loop-free path consistent with the user's decision not to build a
work-sampling measurement system is **opportunistic, one-off reads**: the
next time this fort's brewer/cook/miner/etc. naturally starts a job, a
single non-mutating read of `job.completion_timer` immediately after
assignment gives that job's initial duration at that dwarf's current skill,
with zero new infrastructure. Repeated by hand across a few natural job
starts at different skill levels, this could build a small, honestly-labeled
`site`-scoped prior (per `doctrine/seed.yaml`'s `scope` field) without ever
becoming the sampling loop the user rejected. This is the same idea
`research/2026-09-18-production-graph.md` already named for this field;
repeated here because it is the concrete answer to "what would settle job
time" for every row in this table.

## 3. Hauling and movement

### 3.1 Vehicle and hand-hauling capacity

| Figure | Value | Unit | Source URL | Namespace | Live read that could settle it | Status |
|---|---|---|---|---|---|---|
| wheelbarrow_size | 30,000 | cm³ | https://dwarffortresswiki.org/index.php/Wheelbarrow | current (v53.16); page cites `v50:item_tool.txt` | grep this install's `item_tool.txt` for `ITEM_TOOL_WHEELBARROW`'s `[SIZE:n]` token, same method already used for jug/pot | community_prior (but plausibly raw-verifiable cheaply, see §1) |
| wheelbarrow_capacity | 100,000 | cm³ (stated as "one fifth of a minecart's") | https://dwarffortresswiki.org/index.php/Wheelbarrow | current (v53.16) | same | community_prior |
| wheelbarrow_haul_weight_threshold | 75 | ℥ (DF's mass unit, "Γ" glyph in some renders) | https://dwarffortresswiki.org/index.php/Wheelbarrow | current (v53.16) | none named; a live unit/item read comparing wheelbarrow-assist assignment against item weight could confirm the threshold empirically | community_prior |
| wheelbarrow_hauler_speed_effect | dwarves hauling via wheelbarrow move at full/top speed regardless of the wheelbarrow's or its contents' weight | qualitative | https://dwarffortresswiki.org/index.php/Wheelbarrow | current (v53.16) | community_prior |
| wheelbarrow_stairs | can go up and down stairs (unlike minecarts, which need track) | qualitative | https://dwarffortresswiki.org/index.php/Wheelbarrow | current (v53.16) | community_prior |
| minecart_size | 40,000 | cm³ | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16); same `item_tool.txt` raw-moddable class | grep `item_tool.txt` for `ITEM_TOOL_MINECART` | community_prior (plausibly raw-verifiable) |
| minecart_capacity | 500,000 | cm³ | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same | community_prior |
| minecart_capacity_stone | 5 | item count | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same unit-conflation caution as bins: item count, not cm³ | community_prior |
| minecart_capacity_logs | 10 | item count | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same | community_prior |
| minecart_capacity_blocks_bars | 83 | item count | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same | community_prior |
| minecart_capacity_meals | 500 | item count | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same | community_prior |
| minecart_capacity_cloth | 2,500 | item count | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same | community_prior |
| minecart_capacity_spears | 1,250 | item count | https://dwarffortresswiki.org/index.php/Minecart | current (v53.16) | same | community_prior |
| dwarf_hand_haul_capacity | **not found** | n/a | checked https://dwarffortresswiki.org/index.php/Hauling, https://dwarffortresswiki.org/index.php/Equipment | current (v53.16) | none named; this appears to be governed by Strength attribute plus a general "carry capacity" mechanic the wiki describes only qualitatively ("stronger dwarves carry more, speed degrades but never reaches zero over capacity") | not found |

**Minecart velocity/ramp mechanics, reported for completeness though outside
the brief's core ask**: the `Minecart` page states push initial velocity
(20,000 units, losing 10 to friction), roller speed range (10,000-50,000),
a derail threshold (>0.5 tiles/step at unguarded corners), and a downward-
ramp acceleration figure (~4,890 velocity/tick), all current-namespace,
`community_prior`. These are track-cart-specific and not needed for the
hand-haul/wheelbarrow/minecart competing-process comparison the production
graph wants, included here only so a future reader does not have to
re-search for them.

### 3.2 Dwarf movement speed

| Figure | Value | Unit | Source URL | Namespace | Status |
|---|---|---|---|---|---|
| gait_normal_walk | 900 | ticks/100 tiles (= 9 ticks/tile baseline) | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| gait_jog_run | 521-711 | ticks/100 tiles | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| gait_sprint | 293 | ticks/100 tiles | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| gait_stroll | 1,900 | ticks/100 tiles | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| gait_creep | 2,900 | ticks/100 tiles | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| gait_stealth_penalty | -50 (fastest gaits), -20 (faster gaits) | ticks/100 tiles | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| gait_buildup_time | 10 (fastest gaits), 5 (faster gaits) | ticks to reach full speed | https://dwarffortresswiki.org/index.php/Gait | current (v53.16) | community_prior |
| speed_stat_removed | true | boolean/note | https://dwarffortresswiki.org/index.php/Speed | current, a disambiguation/history page | verified as a wiki claim, `community_prior` for the underlying mechanic | the page states "Speed was removed as a stat in v0.40.01" and now redirects to Gait/Combat/Minecart/Gravity topics; flagged so nobody designs against a "Speed" stat that no longer exists post-v0.40 |

**No wiki figure found for**: how carrying a load reduces the 900-tick
baseline (only the qualitative "speed is reduced... never reaches zero" from
the Weight-page search summary, not independently re-confirmed by direct
fetch this pass); how injury modifies speed; how stairs/ramps/z-level
changes cost movement for a walking (non-cart) dwarf specifically. The
`Minecart` page's ramp mechanics (above) are cart-specific and do not
answer this for an ordinary hauler on foot. **Live read that could settle
this later**: consecutive `unit.pos`/current-tick reads for a real dwarf
walking a known, flat, unobstructed corridor versus one with stairs, taken
opportunistically (not a sampling loop) the next time this fort's citizens
are moving under supervision.

### 3.3 Traffic designation cost multipliers (coordinator's scope addition)

| Traffic level | Cost | Unit | Source URL | Namespace | Status |
|---|---|---|---|---|---|
| High traffic | 1 | pathfinding cost points, per tile | https://dwarffortresswiki.org/index.php/Traffic | current (v53.16) | community_prior |
| Normal traffic (undesignated default) | 2 | pathfinding cost points, per tile | https://dwarffortresswiki.org/index.php/Traffic | current (v53.16) | community_prior |
| Low traffic | 5 | pathfinding cost points, per tile | https://dwarffortresswiki.org/index.php/Traffic | current (v53.16) | community_prior |
| Restricted traffic | 25 | pathfinding cost points, per tile | https://dwarffortresswiki.org/index.php/Traffic | current (v53.16) | community_prior |

**Corroboration across namespaces**: `DF2014:Traffic` states the identical
1/2/5/25 figures, which is some evidence (not proof) the mechanic did not
change across the v50 rewrite, the same kind of cross-namespace agreement
`research/2026-09-17-seed-ratios.md` treated as a weak positive signal for
the yield-range figures. Still `community_prior` per this project's rule:
neither namespace page is itself a game-data or live-read source.

**Configurability, answered plainly**: yes. The `Traffic` page states these
are **defaults**, changeable "in settings, or per-fortress values with the
traffic menu." **This means a stored constant of 1/2/5/25 in the production
graph's schema is only valid until someone (a player, or a future automated
agent) changes it in-game**; the schema should carry this as a
`configurable_default`, not a fixed constant, and any consuming tool should
prefer a live read of the fort's actual current settings over the stored
default once such a read exists.

**Restricted is not a hard block, sourced directly**: "Setting Restricted
does not forbid a dwarf from traveling over those squares, but rather makes
them prefer to walk around them, for the normal cost table, 12.5 times
further, or up to 25 times longer if there is an alternative high-traffic
path." (`Traffic`, current namespace.) A hard block requires walls or a
locked door instead, per the same page. This directly answers the
coordinator's question: restricted is expensive, not impassable, for
ordinary pathing.

**Gotcha found and worth flagging exactly as sourced**: "traffic
designations only influence routing preferences, they cannot restrict where
dwarves choose to work or stand during construction/digging tasks. Jobs
requiring entry into restricted zones will override traffic designations
entirely." (`Traffic`, current namespace.) This matters for the production
graph's logistics layer: a restricted-traffic designation shapes *hauling*
routes but will not stop a dwarf from walking into that same tile to perform
an assigned job (mining it, building on it, etc.). Treat traffic cost as a
hauling-route input only, not a general access control.

**Stairs, ramps, z-level interaction with traffic cost: not found.** Neither
the current `Traffic` page nor `DF2014:Traffic` says anything about how the
1/2/5/25 weights combine with vertical movement cost. This is a clean gap,
not a soft one; both pages were read in full and simply do not address it.

**Live read that could settle any of this later**: the traffic *designation*
itself (which of the four levels a tile carries) is very likely a live-
readable map-block field via DFHack (a designation bitfield, structurally
the same class of thing `df-overseer-stocks.lua`-style tools already read
for other per-tile state), so confirming *what is designated where* is
cheap and real. The *cost weights* (1/2/5/25) are pathfinding-internal to
the compiled binary the same way job duration is; the only way this pass can
see to empirically settle them is a controlled comparison (time an identical
hauling job over two routes differing only in one tile's traffic
designation), which is a real experiment, not a single read, and this
report does not recommend building the harness for it given the user's
already-stated preference against a new measurement loop.

## 4. Workshop throughput and labour availability

**Workshop throughput**: the only concrete figure found is the **task
queue** cap, not a concurrency or output-rate figure: "You can queue up to
ten tasks in any workshop, and tell the dwarves to repeat any or all of them
for as long as possible." (`Workshop`, current namespace, https://
dwarffortresswiki.org/index.php/Workshop.) This bounds how many *orders*
can be queued, not how much a workshop can produce per unit time or whether
multiple dwarves can work one workshop concurrently (general DF knowledge
independent of this search says no, one job per workshop at a time, but
that was not independently re-confirmed by a wiki citation this pass, so it
is not tabled as a figure here).

| Figure | Value | Unit | Source URL | Namespace | Status |
|---|---|---|---|---|---|
| workshop_task_queue_cap | 10 | queued task slots | https://dwarffortresswiki.org/index.php/Workshop | current (v53.16) | community_prior |

**Labour availability ("what fraction of a dwarf's time is actually
productive"): not found, and this report stops there rather than
constructing one, per the brief's explicit instruction.** What the wiki
*does* state, as separate, un-combined figures, none of which answer the
productive-fraction question by itself:

| Figure | Value | Unit | Source URL | Namespace | Status |
|---|---|---|---|---|---|
| sleep_frequency | "a few times every season" | qualitative frequency | https://dwarffortresswiki.org/index.php/Sleep | current (v53.16) | community_prior |
| sleep_duration | 2,650-2,900 | ticks per sleep event (≈2d5h-2d10h) | https://dwarffortresswiki.org/index.php/Sleep | current (v53.16) | community_prior |
| sleep_life_fraction | 5 | percent of a dwarf's life | https://dwarffortresswiki.org/index.php/Sleep | current (v53.16), sourced via search summary of this page, not independently re-quoted from raw wikitext this pass | community_prior, slightly weaker evidence trail than the other rows in this table |
| sleep_deprivation_effect | tired dwarves "work more slowly, and produce poorer-quality results" | qualitative | https://dwarffortresswiki.org/index.php/Sleep | current (v53.16) | community_prior |
| drink_frequency | "about once in every three weeks" | ≈21 days | https://dwarffortresswiki.org/index.php/Thirst | current (v53.16) | community_prior |
| thirst_tick_rate | 1 per tick (1,200/day, 33,600/month, 403,200/year) | thirst-meter units | https://dwarffortresswiki.org/index.php/Thirst | current (v53.16) | community_prior |
| eat_frequency | "about 2 units of food each season" | food units/season | https://dwarffortresswiki.org/index.php/Food | current (v53.16) | community_prior |
| need_fulfillment_interval_examples | every 2 years (need level 1) down to every 3 months (need level 10) | calendar time, per need-intensity level | https://dwarffortresswiki.org/index.php/Need | current (v53.16) | community_prior |
| focus_skill_effect_range | up to 50 percent, either direction | skill-roll modifier (quality/output, not confirmed to be job speed) | https://dwarffortresswiki.org/index.php/Need | current (v53.16) | community_prior, and explicitly not verified to affect job *time* rather than quality; reported only because it surfaced in the same page, not because it answers this scope item |

**Why this pass does not turn the table above into a percentage**: sleep,
thirst, and food operate on independent, non-additive timers (a dwarf does
not stop working to sleep, eat, and drink sequentially in neat blocks; per
the `Hauling`/`Need` pages' own qualitative statements, dwarves will delay
all three to finish a job in progress, and personality affects how long).
Computing "X% of time is needs, therefore Y% is productive" from these
numbers would require knowing each activity's *duration* (only sleep's is
stated, at 2,650-2,900 ticks) and *interruption behavior*, neither of which
the wiki states for eating or drinking. Any percentage this report could
compute would be an estimate built from mismatched units and an assumed
model of interruption behavior that no source confirms, exactly the
false-precision failure mode the brief named. **The honest deliverable
here is: no source found, the interval figures above are the closest
material that exists, and they do not compose into the figure asked for.**

**Community measurements (forum threads, spreadsheets, mod-author notes)
for either workshop throughput or productive-time fraction: none found.**
This pass's web searches for this specific combination did not surface a
forum thread, spreadsheet, or mod author's notes attempting to measure
this empirically; it is reported as a plain "nothing turned up," per this
brief's own explicit "nobody really does this is a valid finding" instruction,
not padded into a maybe.

**Live read that could settle any of this later**: none named. This is
squarely the empirical-measurement territory the user already declined to
build (a sampling loop reading job/need state continuously). A single
opportunistic read cannot answer "what fraction of time," which is
inherently a rate over an observation window; naming a fake single-read
path here would misrepresent the difficulty. The honest note is that this
figure has no cheap live-read shortcut, only the sampling loop the user has
already ruled out.

## 5. The skill-to-speed curve

| Figure | Value | Unit | Source URL | Namespace | Status |
|---|---|---|---|---|---|
| skill_rank_names_to_level | Dabbling=0, Novice=1, Adequate=2, Competent=3, Skilled=4, Proficient=5, Talented=6, Adept=7, Expert=8, Professional=9, Accomplished=10, Great=11, Master=12, High Master=13, Grand Master=14, Legendary=15+ | rank name to numeric skill level | https://dwarffortresswiki.org/index.php/Skill | current (v53.16) | community_prior |
| mining_time_skill0 | 100 (baseline: 20 job ticks, 5 per "wear," soil=5 wear) | percent of base job ticks | https://dwarffortresswiki.org/index.php/DF2014:Miner | **DF2014 (pre-v50)** | community_prior, weak |
| mining_time_skill5_proficient | 60 (12 job ticks, 3 per wear) | percent of base job ticks | https://dwarffortresswiki.org/index.php/DF2014:Miner | **DF2014 (pre-v50)** | community_prior, weak |
| mining_time_skill15_legendary | 20 (4 job ticks, 1 per wear) | percent of base job ticks | https://dwarffortresswiki.org/index.php/DF2014:Miner | **DF2014 (pre-v50)** | community_prior, weak |
| skill_speed_qualitative | "skill levels reduce this significantly... legendary skill can eliminate all time required to do a job down to a single action" | qualitative | https://dwarffortresswiki.org/index.php/Skill | current (v53.16) | community_prior |
| skill_quality_formula_SKILL_ROLL_RANGE | `random(range) + random((skill*multiplier)/2+1) + random((skill*multiplier)/2+1)`, default `[SKILL_ROLL_RANGE:11:5]` | quality-roll formula, **not speed** | https://dwarffortresswiki.org/index.php/Reaction | current (v53.16) | community_prior; explicitly the wrong mechanic for job *time*, included only to document that the current-namespace page discusses skill numerically for quality but pointedly not for speed |
| reaction_no_skill_token_current | "will always complete instantly" | qualitative | https://dwarffortresswiki.org/index.php/Reaction | current (v53.16) | community_prior |
| reaction_no_skill_token_df2014 | "will complete in a default amount of time" | qualitative | https://dwarffortresswiki.org/index.php/DF2014:Reaction | DF2014 (pre-v50) | community_prior; **flagged discrepancy**: the two namespaces disagree on this specific edge case (instant vs. "a default amount of time"), a small but real example of exactly the version-drift this project's own doctrine warns about. Not load-bearing for this fort (all its actual reactions carry a `[SKILL:...]` token per `research/2026-09-18-production-graph.md`), noted so nobody later cites "no-skill reactions are instant" as settled across versions |

**Read as a shape, not a promise, per the brief's own instruction**: the
three DF2014 mining data points (100% / 60% / 20% of base time at skill 0 /
5 / 15) describe a curve that is steep in the low-to-mid skill range and
flattens toward a floor, never reaching zero. That shape is consistent with,
and probably the empirical basis for, the current-namespace page's
qualitative claim that legendary skill can reduce time "down to a single
action" without literally reaching zero. **This is the entire skill-speed
curve this pass found**: one worked example, for one skill (mining), in one
namespace this project has already flagged as the weaker one, generalized
to nothing else. Using this shape for any skill other than Mining, or
treating the exact 60%/20% numbers as applicable to 53.16, would be an
unsupported extrapolation this report explicitly declines to make.

**Live read that could settle this later**: the same opportunistic
`job.completion_timer` reads named in §2, taken for the same job type
across two or more dwarves at different skill levels, would give a real,
this-fort, this-version data point without building a sampling loop.

## What could not be found

- **A general job-duration formula or any per-reaction tick/second figure**
  for brew drink, prepare meal (any quality), mill plants, make barrel,
  cut/make blocks, make mechanisms, make bucket, construct a workshop, chop
  a tree, plant seeds, or harvest. Checked directly: `Still`, `Kitchen`,
  `Reaction`, `DF2014:Reaction`, `Time`, `DF2014:Time`, current-namespace
  `Mining`, `Workshop`. The only concrete number in this entire scope item
  is the DF2014-only mining anecdote in §2/§5, which does not generalize.
- **Dwarf hand-hauling load capacity** (how much weight or how many items an
  unassisted dwarf carries at once). Checked `Hauling` and `Equipment`;
  both discuss the mechanic qualitatively (Strength-dependent, speed
  degrades but never to zero) with no number.
- **How stairs, ramps, or z-level changes cost movement for a walking
  dwarf** (as opposed to a minecart on track, which does have documented
  ramp acceleration figures, §3.1). Checked `Gait` and `Minecart`; neither
  answers this for foot traffic.
- **Traffic designation cost interaction with stairs/ramps/z-level.**
  Checked `Traffic` and `DF2014:Traffic` in full; both are silent on this.
- **A workshop's job-concurrency or output-rate figure** beyond the 10-slot
  task queue. Checked `Workshop` directly.
- **Any figure, from the wiki or the community, for "what fraction of a
  dwarf's day/season is actually productive labor."** This is the scope
  item the brief flagged as the largest source of model error and
  explicitly told this pass to stop on rather than estimate. Checked
  `Sleep`, `Thirst`, `Food`, `Need`, plus general web search for forum
  threads or spreadsheets attempting this measurement. Nothing found in
  either category; see §4 for why the adjacent interval figures that were
  found cannot be composed into this number without introducing an
  unsupported model of interruption behavior.
- **A general (non-mining) skill-to-speed curve**, or any current-namespace
  (v53.16) confirmation of the DF2014 mining percentages. Checked `Skill`,
  `DF2014:Skill`, `Reaction`, `DF2014:Reaction`.
- **Reconciliation of the barrel's 60,000 cm³ capacity figure against its
  own "any number of units of alcohol, single stack" claim.** Both are
  wiki-stated, on the same page, and this pass found no source resolving
  the apparent tension; reported as an open contradiction in §1, not
  silently picked one way.
- **Bucket's per-type item counts** (analogous to the bin table in §1).
  Only the cm³ size/capacity pair was found for bucket; no equivalent
  "N units of X fit in a bucket" table like the one `Using bins and
  barrels` has for bins.

## Relevant to

- `research/2026-09-18-production-graph.md` §2's `production_node` schema:
  every container/vehicle figure in §1 and §3.1 here is ready to populate
  that table's `volume` column with `status='community_prior'` and this
  report's URL as `source_ref`, honoring the schema's own rule that
  `status`/`source_ref` must never fabricate a number the install cannot
  back.
- The same document's `production_process`/`production_flow` tables:
  every "not found" job-time row in §2 confirms that
  `job_time_status='unavailable'` (the schema's stated default) is correct
  for every reaction this fort runs, not just the ones spot-checked live
  on VM 103 in the prior research pass.
- A future logistics/routing layer over the production graph (named but
  not built in `research/2026-09-18-production-graph.md` §3's LP): §3's
  wheelbarrow/minecart/hand-haul figures and §3.3's traffic-cost multipliers
  are the raw inputs such a layer would need to rank hauling routes; the
  traffic-designation lever specifically is flagged by the coordinator as
  cheap (no materials, minimal labor) and worth surfacing to an agent once
  a routing tool exists.
- `doctrine/seed.yaml`'s provenance format: every row in every table above
  follows that file's `kind`/`ref`/`describes`/`read`/`accessed` shape in
  substance (source URL as `ref`, namespace as `describes`, `read: opened`
  since raw wikitext was fetched directly for most rows, a few `search-
  summary` exceptions called out explicitly, e.g. `sleep_life_fraction`),
  so this report's rows can be transcribed into that file's YAML shape
  directly if a future doctrine entry wants them, without re-deriving
  provenance.
