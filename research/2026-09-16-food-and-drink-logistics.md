# Food and drink logistics: what an agent needs to keep a fort fed, and what this repo would have to build

Date: 2026-09-16. Read-only research, no VM/DFHack calls, no model calls beyond
this session's own reasoning. Scope: the question in the brief, against the
live state of Uniboslan reported to this session (VM 103, DF Classic v50-line
build tagged `0.53.16`, DFHack 53.16-r1.1, tick 12309480, 15 citizens, fort-owned
food 0, fort-owned drink 0, 119 seeds, zero farm plots, zero workshops, no
trade depot, a caravan and outpost liaison present and waiting, game frozen
by an undismissed popup). Every domain claim below is cited to the DF wiki or
DFHack's own shipped docs; every claim about this repo's actual code is cited
to the file and line this session read, not recalled. Confidence is flagged
per claim, not once at the end.

**A note on the DFHack docs used as sources.** `docs.dfhack.org`'s "stable"
alias currently serves **53.16-r1**, an exact version match to this install's
documented `53.16-r1.1` (`memory/dfhack-environment.md`). Fetches against
`docs.dfhack.org/en/stable/...` in this report are therefore version-exact
primary sources, not "current docs, hope it matches." Fetches against the DF
wiki are not version-pinned the same way; the wiki content used below (farm
plots, alcohol, trading, fishing) describes mechanics that have been stable
since the 2023 v50 engine rewrite and nothing in this session's research
suggests a point-release change, but that is an inference, not a verified
match to `0.53.16` specifically, and is flagged inline where it matters most.

---

## 1. The domain: nothing to sustainable food and drink

### The dependency chain

1. **Ground and location.** A farm plot needs either soil/muddy stone exposed
   to sunlight (above-ground, seasonal, weather- and biome-dependent — many
   biomes such as glacier, tundra or ocean support no above-ground crops at
   all) or any underground floor with a layer of mud on it, stone or soil
   alike, which grows crops year-round regardless of season. **The one
   underground exception that matters for yield**: farm tiles that are
   literal soil-layer floor (not stone-with-mud) count as "poor soil" and
   yield is cut 75%. Muddied *stone* in a stone layer is full yield. The six
   "dwarven" crops (plump helmet etc.) are the only ones available at a fresh
   embark and only grow underground. [Farming — DF wiki](https://dwarffortresswiki.org/index.php/Farming)
   (moderate-high confidence: current wiki page, not independently re-verified
   against `0.53.16`, but this exact mechanic predates and survived the v50
   rewrite).
2. **A farm plot is a zero-material building**: it is designated/built
   directly on the qualifying floor tile, not constructed from an item, which
   matters later (§4) because it is one of the few buildings that does not
   need `buildingplan`'s "wait for materials" behaviour at all.
3. **Crop assignment is per-plot, per-season.** "Each farm plot can only grow
   one kind of plant per season" — you assign one crop (or leave fallow) for
   each of the four seasons, separately, per plot. [Farming — DF wiki](https://dwarffortresswiki.org/index.php/Farming)
   (same confidence note as above).
4. **Harvest to alcohol: the Still.** A still turns a harvested plant into
   alcohol; **each brewing job produces five units of alcohol per plant
   brewed and returns the plant's seed into the same container**, which is
   the mechanism that regenerates the seed stock a fort is otherwise burning
   down. [Alcohol — DF wiki](https://dwarffortresswiki.org/index.php/Alcohol)
   (moderate-high confidence, current wiki, mechanic pre-dates v50).
5. **Harvest to meals: the Kitchen.** A kitchen cooks plants (and other
   ingredients) into prepared meals. **Cooking a plant destroys its seed** —
   there is no seed recovery from cooking, which is the whole reason a seed
   stock needs active protection (§2). [Farming — DF wiki](https://dwarffortresswiki.org/index.php/Farming)
6. **Meat and fish need their own workshops.** A Butcher's shop turns a
   slaughtered animal into meat, fat, bone and hide. A Fishery is required to
   turn a *raw* fish into an edible/cookable one — raw fish is not directly
   consumable food. [Fishery — DF wiki](https://www.dwarffortresswiki.org/index.php/Fishery)
   (moderate confidence, current wiki).
7. **Containers are load-bearing, not incidental.** Brewing needs an empty
   watertight container (barrel or large pot) to brew into. [Alcohol — DF wiki](https://dwarffortresswiki.org/index.php/Alcohol)
   Food stockpiles specifically use **barrels and large pots**, not bins, by
   default. [Using bins and barrels — DF wiki](https://dwarffortresswiki.org/index.php/DF2014:Using_bins_and_barrels)
   A fort founded with zero barrels cannot brew or store food/drink at
   fortress scale even once it has plants, which is a second, independent
   failure mode from "no farm plot."
8. **Seeds are a finite, self-consuming resource unless replenished.** A fort
   that cooks or otherwise burns through its last seed stock of a plant has
   lost the ability to grow that plant *permanently* for that playthrough —
   there is no other seed source once embark stock and caravan purchases are
   exhausted. This is exactly the risk `agents/quartermaster/role.md` already
   names ("a fort that eats its last plump helmet seeds has lost farming
   permanently," `agents/quartermaster/role.md:14-15`, this session's own
   read).
9. **What actually happens with no drink.** Dwarves prefer alcohol and will
   drink it roughly five times a season to satisfy thirst; **they can
   subsist on water instead**, but without booze **they work increasingly
   slowly**, and being denied a drink of choice or forced into monotony
   produces bad thoughts. [Alcohol — DF wiki](https://dwarffortresswiki.org/index.php/Alcohol),
   [Thirst — DF wiki](https://new.dwarffortresswiki.org/index.php/Thirst)
   So "zero drink" is not itself lethal the way "zero food and no water
   access" is, but it is a real, compounding productivity and mood tax, and
   it degrades a fort's ability to dig itself out of the exact hole it is
   in. **Not verified**: whether this install's water-access mechanics
   (a well, an open water tile reachable by the walkable network) are
   actually in place on Uniboslan — that is a `connectivity`/`landmarks`
   question this report did not check.
10. **Scale, with real numbers.** The wiki's own worked example: a 7-dwarf
    starting fortress needs roughly 196 units of food-and-drink per year; a
    3×3 plump helmet plot can produce up to ~2700 units of alcohol per year
    (enough for ~95 dwarves), a 5×5 plot up to ~7500 (enough for ~265
    dwarves). [Farming — DF wiki](https://dwarffortresswiki.org/index.php/Farming)
    For today's 15 citizens, a single well-sited 3×3 or even 2×2 plot,
    correctly seasoned, is not a scale problem — the problem is *zero* plots,
    not too few.

### Version-sensitivity flagged plainly

Everything in this section is standard DF mechanic knowledge, cross-checked
against the current DF wiki, not against `0.53.16`'s own patch notes (which
this session did not read). `memory/dfhack-environment.md`'s own standing
warning — "the v50 transition invalidated a lot of older community
knowledge" — is about DFHack *tool availability*, not core game mechanics
like farm plots and brewing, which are DF engine behaviour untouched by
DFHack's own version. Nothing found in this research suggests the farm
plot/still/kitchen/butcher/fishery chain has changed shape since v50; that is
an inference from absence of any contrary signal, not a positive
confirmation from this install's own changelog.

---

## 2. The logistics: why this is not just "build a farm"

### What makes it hard

- **Stockpile links are the actual production chain.** A still or kitchen
  pulls its raw material from a stockpile via a `take_from`/`give_to`
  relationship set at the stockpile (or workshop) level; without a link, a
  workshop can still be manually given one-off jobs but has no standing
  supply. Quickfort's own blueprint syntax expresses this directly in a
  `#place`/`#build` cell, e.g. `f{name="Seeds feeder" give_to=Seeds}:=seeds`
  paired with `f{name=Seeds links_only=true take_from="Seeds feeder"}:=seeds`.
  [Quickfort blueprint guide, 53.16-r1](https://docs.dfhack.org/en/stable/docs/guides/quickfort-user-guide.html)
  (high confidence: version-exact fetch). **This repo has no tool that
  creates or edits a link between two already-built stockpiles/workshops**
  (confirmed by `research/2026-09-12-write-conflict-matrix.md`'s Conclusion 3,
  this session's own re-read: "none of them touch stockpile *settings* in the
  sense of item filters, take/give links, or bin/barrel toggles").
- **Barrels and bins are a real material cost**, not a formality — a fort
  needs actual barrel/pot items made (wood, or bought) before a food/drink
  stockpile or a still can function at scale, and quickfort's own stockpile
  syntax has explicit `nobins`/`nobarrels`/`maxbarrels`/`maxbins` controls
  because getting this wrong either starves a stockpile of containers or
  hoards containers a fort cannot spare. [Quickfort blueprint guide, 53.16-r1](https://docs.dfhack.org/en/stable/docs/guides/quickfort-user-guide.html)
- **Hauling distance is a real, compounding cost**, which is exactly the
  reasoning already recorded in this repo's own queue example proposal
  (`docs/AGENT-ARCHITECTURE.md:329-341`, "Hauling distance from the still is
  the largest single contributor to current idle-hauler time") — siting a
  still or kitchen far from its stockpile is a self-inflicted throughput tax,
  and this repo's Architect role already treats stockpile-workshop adjacency
  as doctrine (`docs/AGENT-ARCHITECTURE.md:478`, "workshops need stockpile
  adjacency").
- **Food does not rot in a stockpile, at all** — the only places food never
  spoils are a stockpile, the trade depot, the embark wagon, a minecart, mid-
  reaction, or while actively being carried. [Using bins and barrels — DF wiki](https://dwarffortresswiki.org/index.php/DF2014:Using_bins_and_barrels)
  So "food rot" is not the risk it would be in a simpler game; the real risk
  this repo needs to guard against is food sitting *unstockpiled* on the
  ground (which does rot) because no stockpile of the right type exists yet
  or a hauling job never gets picked up (`get_stuck_jobs`, already built,
  is the existing detector for the latter half).
- **Manager work orders vs one-off jobs, and the priority trap this repo
  already documented.** A one-off job (right-click a workshop, queue one
  brew) is fire-and-forget; a **manager work order** is what keeps
  production standing (e.g. "brew booze, repeat, until stock ≥ N"). The
  underlying `manager_order` struct has **no numeric priority field at
  all** — order is realised purely as position in the ordered
  `world.manager_orders.all` vector, confirmed by reading the struct
  directly at the pinned version tag
  (`research/2026-09-12-dfhack-capability-checks.md` §4, this session's own
  re-read). This is already flagged as a trap for "whoever builds this" in
  `agents/quartermaster/role.md:41-44`.
- **Conditions and repeat.** Orders support item conditions
  (`"item_conditions":[{"condition":"AtLeast","value":5}]`) and DFHack's
  `repeat` command can re-issue an order on a schedule (e.g. re-check every
  14 days). [workorder — DFHack 53.16-r1](https://docs.dfhack.org/en/stable/docs/tools/workorder.html)
  (high confidence, version-exact fetch).

### What a competent player automates, and what DFHack already automates

All availability tags below are checked against **this install's own
tracked list**, `memory/dfhack-environment.md` (audited 2026-08-25/27 against
the local Windows install, then against the VM 2026-08-27, both this
session's own re-read). That file names each tool it checked and tags it
`available` or `unavailable`; several tools relevant here are **named by
neither list**, which under this repo's own convention ("grep for
`unavailable` before designing around any tool," `memory/dfhack-environment.md:75`)
means **status genuinely unknown**, not "probably fine."

| Tool | What it does (cited) | Availability on this install |
|---|---|---|
| **`orders`** | Import/export/sort manager work orders; ships a **built-in library**, `library/basic`, explicitly covering "prepared meals and food products... booze/mead" plus containers. [orders — DFHack 53.16-r1](https://docs.dfhack.org/en/stable/docs/tools/orders.html) | **Confirmed available** — named directly in `memory/dfhack-environment.md`'s available list. |
| **`workorder`** | Programmatic manager-order creation (`create_orders()`), the actual struct-construction path a future tool would call. [workorder — DFHack 53.16-r1](https://docs.dfhack.org/en/stable/docs/tools/workorder.html) | **Confirmed available**, added to the tracked list 2026-09-12 specifically because it was checked and found present (`memory/dfhack-environment.md:88-91`). |
| **`autobutcher`** | Auto-designates excess livestock for slaughter against per-species population targets, with real protections (named/tame/pregnant/military animals excluded). [autobutcher — DFHack 53.16-r1](https://docs.dfhack.org/en/stable/docs/tools/autobutcher.html) | **Confirmed available** — named in `memory/dfhack-environment.md`'s available list and in `docs/PURPOSE.md`'s "Anti-decay suite" (`docs/PURPOSE.md:203`). |
| **`logistics` (autotrade sub-feature)** | Monitors a stockpile and marks its contents for hauling to the trade depot whenever a caravan is present or approaching; does **not** execute the trade itself. `logistics add trade -s <stockpile>`. [logistics — DFHack 53.16-r1](https://docs.dfhack.org/en/stable/docs/tools/logistics.html) | **Confirmed available** — named in `memory/dfhack-environment.md`'s available list. |
| **`workflow`** | The classic stock-based production throttle (e.g. stop making X once N are in stock) and, historically, seed protection during cooking. | **Confirmed unavailable** on this install (`memory/dfhack-environment.md:93-95`; independently re-confirmed by `research/2026-09-12-write-conflict-matrix.md` and `agents/quartermaster/role.md:32-33`). |
| **`stocks`** | The in-game-adjacent stock summary/management screen DFHack exposes. | **Confirmed unavailable** (same citation as `workflow`). |
| **`seedwatch`** | Sets a per-type seed target; protects a plant from being cooked once its seed stock is below target. [seedwatch — DFHack docs](https://docs.dfhack.org/en/stable/docs/tools/seedwatch.html) | **Status unknown on this install** — not named in either of `memory/dfhack-environment.md`'s lists. Must be checked (`hack/docs/docs/tools/seedwatch.txt`'s own `Tags:` line) before any tool is built to depend on it. |
| **`buildingplan`** | Lets you place a building (workshop, farm plot, etc.) before materials exist; the plan sits suspended and auto-fills materials as they become available, then unsuspends. [buildingplan — DFHack docs](https://docs.dfhack.org/en/stable/docs/tools/buildingplan.html) | **Status unknown on this install** — not named in either list. This matters a lot: it is the standard answer to "the fort has zero of everything, so nothing can be built yet," and this repo cannot currently claim it. |
| **`autofarm`** | Periodically scans plant/seed stock and assigns crops to farm plots automatically, per configurable per-type or global thresholds, so crop choice tracks what is actually running low. [autofarm — DFHack docs](https://docs.dfhack.org/en/stable/docs/tools/autofarm.html) | **Status unknown on this install** — not named in either list. |

**The practical upshot for this repo, stated plainly.** Of the tools that
would do the most work automatically, **three of six have unknown
availability on the exact install this project runs**, including the two
most relevant to "never run out of seeds or crop variety" (`seedwatch`,
`autofarm`) and the one most relevant to "the fort has nothing yet"
(`buildingplan`). This is not a criticism of the domain research; it is a
gap this report cannot close without a live check this task's constraints
forbid, and it should be the first thing whoever builds the Quartermaster's
tools does, using exactly the method `memory/dfhack-environment.md` already
established (`grep -l "Tags:.*unavailable" hack/docs/docs/tools/{buildingplan,seedwatch,autofarm}.txt`
against the VM's own install).

---

## 3. The immediate rescue path for Uniboslan's exact state

Ranked, with the load-bearing uncertainty named up front: **this report
could not determine how much in-game time remains before the present
caravan departs.** The DF wiki gives only the loose seasonal cadence for
caravan *arrival* (dwarven caravans generally arrive with "at least 22 weeks"
of advance notice before autumn), not a documented on-map dwell time once
arrived. [Trading — DF wiki](https://dwarffortresswiki.org/index.php/Trading)
Whether the current caravan leaves in days or weeks of game time is
genuinely unknown from this research and is exactly the kind of fact a
`depot.status`-class tool (§4) should surface before anyone commits to the
trade path.

### Rank 1: Trade with the caravan already present

**Why it is fastest in principle.** The caravan's wagons already contain 234
food items and 50 drink items — a live, non-production dependent food
source sitting on the map right now. Nothing needs to grow.

**What it actually needs, and where this repo already has a real gap.**

1. A **trade depot**, built and reachable — mandatory; if merchants cannot
   path to it, they leave without trading at all. [Trading — DF wiki](https://dwarffortresswiki.org/index.php/Trading)
   This repo can build it (`quickfort` is confirmed available and this
   repo's own `openarea.build`/`landmarks.build` idiom already builds
   arbitrary quickfort `#build` blueprints), but **no trade depot blueprint
   exists yet** in `blueprints/` (confirmed: `blueprints/` holds exactly four
   files, none a depot, this session's own directory listing).
2. Goods physically hauled to the depot — `logistics add trade -s
   <stockpile>` is a real, confirmed-available mechanism for this
   (`logistics`, above), **but it moves items already sitting in a named
   stockpile**, and this fort has zero stockpiled fort-owned goods of any
   kind (drink 0, food 0; whatever else exists to trade with, e.g. surplus
   starting equipment or stone, is unknown — no tool in this repo inventories
   fort-owned tradeable goods either).
3. A **broker** is not strictly required, but without one the trade is
   conducted by "a random, probably unskilled dwarf" with badly inaccurate
   valuations. [Trading — DF wiki](https://dwarffortresswiki.org/index.php/Trading)
   No tool in this repo assigns a broker (a noble-position assignment, not a
   labor toggle, and outside anything `df-overseer-labor.lua` touches).
4. **The genuinely load-bearing gap: executing the trade transaction has no
   found DFHack struct API.** This research found `dfhack.items.isRequestedTradeGood()`
   (a valuation helper) and generic viewscreen access
   (`dfhack.gui.getViewscreen()`), but no function that marks goods for
   trade, accepts an offer, or completes a transaction at the struct level —
   only the ordinary player interaction with `viewscreen_tradegoodsst`.
   [DFHack Lua API Reference, 53.16-r1](https://docs.dfhack.org/en/stable/docs/dev/Lua%20API.html)
   That means, on the evidence this research could gather, **completing a
   trade would require the same UI-automation mechanism this repo already
   built for embark** (`df-overseer-ui.lua`'s `click`/buffer-scan idiom),
   which this repo's own docs deliberately restrict to embark bootstrap and
   flag as the least sliceable, most collision-prone write path in the
   codebase (`docs/AGENT-ARCHITECTURE.md:687-693`, `research/2026-09-12-write-conflict-matrix.md`'s
   Conclusion 1). **This is a checked negative, not an unexamined gap**: it
   is the reason Rank 1 is ranked first for *speed of the food itself
   existing* but is not a fully closeable loop with this repo's current
   design commitments.

**Bottom line on trade**: buildable depot, no verified way to haul goods to
it beyond staging (need a stockpile to stage *from*, which does not exist),
no verified way to execute the transaction without either a human on the
admin VNC channel or a new UI-automation tool this repo has so far
deliberately avoided building for steady-state play.

### Rank 2: Gather and hunt

Wild plant gathering, hunting and fishing are all real, DFHack-independent,
vanilla food sources that need **zero constructed buildings** to start (a
fishery is needed only to process raw fish, not to catch it). DF's own
mechanic requires an **activity zone** for systematic plant gathering and for
fishing specifically to be reliable ("Automating plant-gathering jobs in an
area is necessary"; the Catch Live Fish job needs an active fishing zone,
though fisherdwarves will opportunistically fish outside one too by
default). [Activity zone — DF wiki](https://dwarffortresswiki.org/index.php/DF2014:Activity_zone),
[Fishing industry — DF wiki](https://dwarffortresswiki.org/index.php/DF2014:Fishing_industry)
(moderate confidence, current wiki, not independently checked against
`0.53.16`). Hunting needs the Hunting labor plus a ranged weapon and ammo
assigned to a hunter — not guaranteed to exist at this embark without
checking starting equipment, which this research did not do.

**This repo has no zone-creation tool at all.** DFHack's own `zone`
automation plugin is confirmed **unavailable** on this install
(`memory/dfhack-environment.md:93-95`), and that is a convenience plugin on
top of the vanilla zone-designation screen, not the only path to creating
one — but this repo has never built a struct-level or UI-automation path to
the vanilla zone screen either. So gather/hunt/fish are mechanically the
cheapest rescue in DF's own terms (no material cost) and currently **the
least buildable of the three with this repo's existing tools**, because the
one primitive all three need (a zone) does not exist here.

### Rank 3: Rush a farm plot

Correct long-term (self-sustaining, no dependency on a caravan showing up
again), but has the longest lead time of the three: dig or clear a plot,
build it (zero material cost, so this is genuinely fast once a legal tile is
found — reusing `diggable.find`/`openarea.find`'s existing candidate-ranking
logic), assign a crop, wait a full growing cycle, then still needs a still
or kitchen built and linked before the harvest becomes food or drink a
dwarf can actually eat or drink. Every workshop in that chain is new tool
surface this repo does not have yet (§4).

### Is a save with zero stores normally recoverable?

**Not independently verified by this research** — no wiki page or forum
source was found that directly addresses recoverability from a specific
"zero food, zero drink, caravan present" state as a class. What this
research *can* say with the sources gathered: the domain mechanics
(alcohol's productivity-not-lethality framing, food's rot-only-when-
unstockpiled rule, gather/hunt/fish requiring no buildings) all suggest this
state is recoverable in DF's own terms **given dwarf-hours and calendar
time**, and the presence of a caravan with 234 food and 50 drink items
sitting on the map right now is a stroke of favorable timing rather than a
guaranteed rescue, since the actual transaction path is the part this
report could not confirm end-to-end. The honest statement is: **recoverable
in principle, given time; the caravan is an opportunity this repo cannot yet
reliably seize, not a guaranteed save.**

---

## 4. Tools this repo would need

Same shape as `scripts/dfhack/TOOLS.yaml` and `agents/*/tools.yaml`: id,
args in landmark-relative terms, what it returns, the underlying DFHack
mechanism, and whether that mechanism is verified present on this install.
`effect`/`coordinate_bearing` follow the existing manifest's own vocabulary
(`scripts/dfhack/TOOLS.yaml:23-43`, this session's own re-read).

### `df-overseer-stocks.lua` (new file — the most load-bearing gap of all)

| id | args | returns | mechanism | availability |
|---|---|---|---|---|
| `stocks.food-drink` | none | fort-owned (not caravan/foreign-owned) food and drink item counts, converted to **food-days**/**booze-days** given current citizen count — one integer each, per `docs/AGENT-ARCHITECTURE.md`'s own doctrine (§5, "Food-days is the exemplar, one integer replacing an entire inventory listing") | Iterate `df.global.world.items.other.FOOD`/`.DRINK`, filter by ownership/civ flag against the fort's own civ | **Not verified.** No script in this repo touches item-ownership filtering at all (`research/2026-09-12-write-conflict-matrix.md` Conclusion 4: "no food/drink stock-level query at all"). `prospector`, confirmed available, is **not a substitute** — it reports embark-region resource *potential*, not current fort-owned stock, which is exactly the distinction the live prompt for this report needed a human to make by hand ("the 50 drink and 234 food items... all belong to the merchant caravan, flagged foreign"). |
| `stocks.seeds` | none | per-type seed counts, fort-owned | same item-iteration mechanism as above, over `df.global.world.items.other.SEEDS` | Not verified, same reasoning. |

`effect: read`, `coordinate_bearing: false` for both — neither touches tile
geometry at all, which is itself worth noting: this is a new *kind* of
perception primitive for this repo, closer to `overview.get`'s aggregate
counters than to any of the spatial `find_*` tools.

### `df-overseer-workshop.lua` (new file)

| id | args | returns | mechanism | availability |
|---|---|---|---|---|
| `workshop.find` | `W H [LEVEL] NEAR_LANDMARK KIND [RADIUS_TILES]` | ranked candidate boxes, scored for adjacency to the nearest stockpile of the relevant type (extends `find_open_area`'s existing scan with a stockpile-distance term) | Reuses `is_free`/`getWalkableGroup` from `df-overseer-openarea.lua:101-109` (this session's own re-read, same primitive `openarea.find` already uses live) | The **spatial-candidate mechanism is verified** (same code path as `openarea.find`, verified 2026-09-11 per `TOOLS.yaml:190-194`). The **stockpile-adjacency scoring term is new and unverified.** |
| `workshop.build` | `W H [LEVEL] NEAR_LANDMARK KIND BLUEPRINT_FILE [RANK] [RADIUS_TILES]` | build result, coordinate resolved internally | `quickfort run <blueprint> -c <top-left>`, the same fused resolve-and-act idiom `build_open_area` already uses (`df-overseer-openarea.lua:294-296`) | `quickfort` itself is **confirmed available**. The blueprints it would run (`starter-still-*.csv`, `starter-kitchen-*.csv`, `starter-butchershop-*.csv`, `starter-fishery-*.csv`, `starter-farmersworkshop-*.csv`) **do not exist yet** — `blueprints/` holds four files, none a workshop, this session's own directory listing. Quickfort's `#build` symbol table (`ws`=still, `wf`=farmer's workshop, `wk`=kitchen, `wb`=butcher shop, per the fetched quickfort guide) is confirmed by a version-exact doc fetch, so authoring these is mechanical, not researched-from-scratch. |

`effect`: read for `find`, mutate for `build`. `coordinate_bearing: false`
for `find`, `internal-only` for `build` — same pattern as every existing
fused find/build pair.

### `df-overseer-farmplot.lua` (new file)

| id | args | returns | mechanism | availability |
|---|---|---|---|---|
| `farmplot.find` | `W H [LEVEL] NEAR_LANDMARK SURFACE\|UNDERGROUND [RADIUS_TILES]` | ranked candidates filtered for soil/muddable-stone floor, tagged with expected yield class (full vs "poor soil") | Extends `is_diggable`'s existing material/shape read (`df-overseer-diggable.lua:121-137`) with the soil-vs-muddable-stone-vs-poor-soil classification the farming domain research above describes | The **tile-material read mechanism is verified** (same primitive `diggable.find` already uses live, verified 2026-09-11). The **farmability classification logic itself is new and unverified** — nobody has checked this repo's read of soil-layer floor against DF's own "poor soil" flag. |
| `farmplot.build` | `W H [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]` | build result | Same `quickfort run -c <top-left>` idiom as every other `build` tool here | `quickfort` confirmed available; farm plots are a zero-material building so this sidesteps the `buildingplan` question entirely (§2) — a real, load-bearing point in this tool's favour. Blueprint itself needs authoring. |
| `farmplot.assign-crop` | `NAME SEASON CROP` (landmark name, not coordinates) | confirmation of the crop now assigned | **Genuinely unsettled which mechanism to use.** Three candidates found, none confirmed against this install: (a) quickfort's own farm-plot query aliases, which the shipped guide describes as only choosing "the first or last type of seed in the list of available seeds," i.e. **not a named-crop selector** — too coarse for a real Quartermaster tool; (b) the `autofarm` plugin, which reassigns crops fortress-wide by seed-stock threshold rather than per-named-plot, and whose availability on this install is **unknown** (§2 table); (c) a direct struct write to the farm plot building's own per-season plant-id field, by analogy with this repo's existing pattern of writing unit/building struct fields directly (`set_labor` writes `unit.status.labors[code]` directly, `memory/dfhack-environment.md:144-149` documents reading building-local fields directly) — **this field was never read from df-structures this session** and is the single most concrete next research step this report can name. | **Not verified by any of the three candidate mechanisms.** Flagged rather than guessed at. |

### `df-overseer-stockpilelinks.lua` (new file, or folded into `df-overseer-landmarks.lua`)

| id | args | returns | mechanism | availability |
|---|---|---|---|---|
| `stockpilelinks.link` | `GIVER_NAME RECEIVER_NAME` | confirmation of the link | Quickfort's own `take_from`/`give_to` syntax is documented **only as a blueprint-authoring-time property** (baked into a `#place` cell before the stockpile is built), not as a live "link two already-built stockpiles" command — [Quickfort blueprint guide, 53.16-r1](https://docs.dfhack.org/en/stable/docs/guides/quickfort-user-guide.html). Whether re-running a `#query` blueprint against existing buildings can add a link after the fact, versus needing a direct struct write to the stockpile's own link vectors, is **unresolved by this research** and needs either a live check or a deeper read of the quickfort alias guide this session did not fetch. | **Not verified.** This is the clearest example in this whole list of "the domain mechanism is well documented, but exactly how to drive it from outside the interactive blueprint-authoring workflow is not," and it should not be assumed solved just because quickfort itself is confirmed available. |

### `df-overseer-manager.lua` (new file)

| id | args | returns | mechanism | availability |
|---|---|---|---|---|
| `manager.list` | none | pending manager orders: job type, amount left/total, queue position, resolved via `dfhack.job.getManagerOrderName` | Read `world.manager_orders.all` (a plain exposed vector, confirmed by direct struct read, `research/2026-09-12-dfhack-capability-checks.md` §4) | **Confirmed present as an API surface** (struct read directly at the pinned version tag). Not yet wrapped by any script in this repo. |
| `manager.create` | `JOB_TYPE AMOUNT [CONDITION...]` | the new order's id and queue position | Wraps `workorder.lua`'s `create_orders()`, itself confirmed present and callable (`memory/dfhack-environment.md:88-91`) | **Confirmed available as an underlying mechanism.** This is the single highest-leverage new tool in this list: it is a thin wrapper over an already-blessed DFHack Lua module, not new game-state-reading logic. |
| `manager.reorder` | `ORDER_ID POSITION` | new queue order | `world.manager_orders.all:insert(idx, order)`/`:erase(idx)` — confirmed as a *supported vector operation* by the same idiom `workorder.lua` itself uses for insertion (`insert('#', order)`), per `research/2026-09-12-dfhack-capability-checks.md` §4 | **Mechanically plausible, not live-exercised.** That research brief's own words: "not actually called against a running fort, only confirmed as a supported vector operation." Given the doc's own finding that priority *is* position here, this tool is how a future Quartermaster's `suggested_priority` field (`docs/AGENT-ARCHITECTURE.md:362-368`) would actually take effect for a work order, as opposed to a dig designation. |
| `manager.import-library` | `NAME` (e.g. `basic`) | list of orders imported | Shells to `orders import library/<name>`, itself confirmed present (`orders`, above) and specifically documented to cover "prepared meals and food products... booze/mead" for `library/basic` | **Confirmed available**, and arguably the cheapest possible fix for "the fort produces nothing standing": this needs no custom Lua at all, only a wrapper around an existing DFHack-authored, food-and-drink-focused standing-order set. |

`effect`: read for `list`, mutate for `create`/`reorder`/`import-library`.
`coordinate_bearing: n/a` for all four — this is the first tool surface in
this repo that touches **no tile geometry whatsoever**, worth naming
explicitly in the manifest's own vocabulary if these are ever added for real
(the existing `n/a` marking on `df-overseer-ui.lua type` is the closest
existing precedent, `TOOLS.yaml:384`).

### `df-overseer-depot.lua` (new file)

| id | args | returns | mechanism | availability |
|---|---|---|---|---|
| `depot.build` | `W H [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]` | build result | Same `quickfort run -c <top-left>` idiom | `quickfort` confirmed available; depot blueprint needs authoring (not present in `blueprints/` today). |
| `depot.status` | none | whether a depot exists and is reachable; whether a caravan/wagon is present, resolved to a named landmark and direction/distance (reusing `nearest_landmark`, the same idiom `threat.scan` already uses live); whether an outpost liaison is present | New Lua, composing existing landmark/reachability primitives over caravan- and liaison-specific unit/building reads | **Not verified** — no script in this repo currently distinguishes a caravan wagon or a liaison unit from any other unit; this is new classification logic, not just a new call site. |
| `depot.stage-goods` | `STOCKPILE_NAME` | confirmation | Wraps `logistics add trade -s <stockpile>`, confirmed available and confirmed to do exactly this ("items will be marked for trading only when a caravan is approaching or is already at the trade depot," it "does not execute trades itself") [logistics — DFHack 53.16-r1](https://docs.dfhack.org/en/stable/docs/tools/logistics.html) | **Confirmed available as an underlying mechanism.** Genuinely cheap to wrap. |
| `depot.execute-trade` | — | — | **No tool proposed.** This research found no struct-level DFHack API for completing a trade transaction (§3). The only known path is UI automation against `viewscreen_tradegoodsst`, which this repo's own design deliberately restricts (`docs/AGENT-ARCHITECTURE.md:687-693`). Naming a tool here that this research cannot back with a real mechanism would misrepresent what is actually buildable; this is recorded as an open research question instead (§5's judgment discussion returns to it). | **Explicitly not verified present, in either direction** — a checked absence in the Lua API reference read, not an unexamined gap. |

`effect: read` for `status`, `mutate` for `build`/`stage-goods`.
`coordinate_bearing: internal-only` for `build`, `false` for the other two.

### Zone creation — named as a gap, not a tool

No tool is proposed here for creating an activity zone (needed for
gather-plants and reliable fishing, §3 Rank 2), because this research could
not confirm a mechanism. DFHack's `zone` automation plugin is confirmed
**unavailable** on this install, and this repo has never built either a
struct-level path (`dfhack.buildings` civzone construction, by loose analogy
to workshop construction, was not checked against df-structures this
session) or a UI-automation path to the vanilla zone-designation screen.
This is the same honesty this list owes `depot.execute-trade`: naming a tool
without a confirmed mechanism underneath it would be worse than naming the
gap plainly.

---

## 5. The judgment question: computable versus genuinely agentic

Applying this repo's own rule verbatim: **"If it is computable, it is a
tool. An agent exists only where there is judgment under uncertainty."**
(`docs/AGENT-ARCHITECTURE.md:78-79`, principle 1, itself restating
`docs/PURPOSE.md` design commitment #2.)

### Computable — belongs in code or DFHack automation, not in a model call

- **Food-days and booze-days arithmetic.** Exactly the existing doctrine
  (`docs/AGENT-ARCHITECTURE.md:523-526`): "arithmetic over many rows is
  precisely what models are worst at." `stocks.food-drink` (§4) is the tool;
  no agent should ever be asked to sum item counts.
- **Seed-stock protection and crop rotation by threshold**, once
  `seedwatch`/`autofarm`'s availability is settled (§2) — these are
  precisely the kind of "an agent that remembers to check a threshold"
  role this repo has already explicitly rejected as an agent job
  (`docs/AGENT-ARCHITECTURE.md:1019-1020`, "an agent that runs efficiency
  algorithms... both are code").
- **Excess-livestock butchering** — `autobutcher`, already running fort-wide
  per the anti-decay suite (`docs/PURPOSE.md:203`), needs no agent
  involvement at all for the routine case.
- **Hauling goods to a depot once a policy decision (what to sell) has been
  made** — `logistics add trade` is a standing, code-level answer once told
  which stockpile to watch.
- **Candidate siting for a workshop or farm plot** (ranked, scored,
  labelled) — this is the exact pattern this repo already proved out for
  open-area and diggable-area siting (`find_open_area`/`find_diggable_area`,
  both live-verified, `TOOLS.yaml:190-206`, `228-237`). The ranking is code;
  only the choice among ranked, labelled candidates is ever the model's job,
  per design commitment #2 (`docs/PURPOSE.md:81-83`) verbatim.
- **Work-order mechanics once told what to produce** — `manager.create`/
  `manager.reorder` are pure code once given a job type and amount; no
  judgment is needed to append a struct to a vector.
- **Rot itself needs no tool at all** — DF's own rule (food never rots in a
  stockpile) means this repo's actual exposure is *unstockpiled* food
  sitting on the ground, which `get_stuck_jobs` (already built, verified
  2026-09-11) already has a hook into via stalled hauling jobs.

### Genuinely judgment-under-uncertainty — where an agent actually earns its place

- **Which rescue path to take right now, in this exact fort's state.** §3's
  own ranking is a one-off situational call weighing an uncertain caravan
  departure window, an incomplete accounting of what the fort has to trade,
  and a still-unbuilt zone/depot/workshop tool surface, against each other —
  not a formula that produces the same answer on every fort. This is
  precisely the "plan under resource contention" the Overseer's
  write-ahead-log design already assumes it will do
  (`docs/AGENT-ARCHITECTURE.md:826-830`).
- **What to buy and what to give up for it, if trade is chosen.** Broker
  valuation is inherently a priced-uncertainty problem (the wiki's own
  framing: without a broker, valuations are "extremely inaccurate," implying
  even *with* one there is a real negotiation, not a lookup table)
  [Trading — DF wiki](https://dwarffortresswiki.org/index.php/Trading).
  No amount of code turns "what should we give up for 234 units of food" into
  arithmetic; that is exactly why this repo's design keeps advisors
  read-only and lets only the Overseer decide (`docs/AGENT-ARCHITECTURE.md:82-83`,
  principle 3).
- **Which crop to plant, and when to accept a mood cost for variety versus a
  seed-preservation risk for monoculture.** This is a real trade-off between
  two things code can each measure (calorie/booze yield, seed-stock
  headroom) but cannot rank against each other without a value judgment
  about *this* fort's priorities right now — early survival versus dwarf
  happiness. That is squarely the Quartermaster's charter
  (`agents/quartermaster/role.md:9-11`, "Booze matters as much as food:
  dwarves work badly without it").
- **Setting a threshold the first time, and revising it after evidence.** A
  threshold itself (seed target, autobutcher population cap, food-days
  floor that triggers a wake event) is code once chosen — but *choosing* it,
  and revising it when the reflex log shows it firing too often or too
  rarely, is exactly the "writing and revising playbooks" work this repo
  already assigns to the Overseer during quiet cycles
  (`docs/AGENT-ARCHITECTURE.md:155, 622-635`), not something a formula
  derives from first principles.
- **Whether to attempt the depot/trade path at all given the open
  `execute-trade` gap.** Given this research's own finding that trade
  execution has no confirmed struct API, a real decision-maker has to weigh
  "wait for a human on the VNC channel," "build a UI-automation tool this
  repo has so far deliberately avoided outside embark," or "abandon trade and
  rush gather/farm instead" — three genuinely different-cost paths with no
  formula to pick among them. This is squarely a judgment call, and this
  report deliberately does not make it.

### Where this leaves the roster today

`agents/quartermaster/role.md:1-4` already states the charter is blocked on
tools, not on a decision, and that writing an allowlist against tools that
do not exist would misrepresent a capability this repo does not have. This
report's tool list (§4) is exactly the material that charter is waiting on.
`dfqueue/schema.py`'s `TYPE_VOCAB_BY_ROLE` (this session's own read,
`dfqueue/schema.py:107-124`) currently defines a closed proposal-type
vocabulary only for the Architect; enabling a Quartermaster for real would
need its own vocabulary added there (candidates suggested by this report's
own findings: `food_security`, `stockpile_link`, `work_order`,
`crop_assignment`, `trade_priority`), which is a small, mechanical follow-on
once the tools themselves exist, not a new design question.

---

## Not verified — summary

Named individually above; collected here for scanning:

- Whether `seedwatch`, `buildingplan`, and `autofarm` are available or
  tagged unavailable on this specific install (§2, §4) — genuinely unknown,
  not inferred either way.
- The exact mechanism for `farmplot.assign-crop` (three candidates named,
  none confirmed) and for `stockpilelinks.link` (quickfort's own docs cover
  only blueprint-authoring time, not live re-linking).
- Whether a struct-level trade-execution API exists anywhere in DFHack's Lua
  surface beyond the valuation helper found — a real search was made and
  came up empty, which this report treats as a checked negative, not
  proof of absence.
- How long the caravan currently on Uniboslan's map will remain before
  departing — no source found gives an on-map dwell time, only an arrival
  cadence.
- Whether this install's farm plot/still/kitchen/butcher/fishery mechanics
  match the current DF wiki exactly at `0.53.16` specifically — inferred
  from mechanic stability since the v50 rewrite, not confirmed against this
  build's own patch notes.
- Whether Uniboslan has any water access at all for the "dwarves can
  subsist on water" fallback, or any starting equipment/animals worth
  trading — neither was checked, both matter to §3's ranking.
- Zone creation mechanism (struct-level civzone construction vs UI
  automation) — not read this session, named as the concrete next research
  step for Rank 2 of §3.

## Sources

DF wiki: [Farming](https://dwarffortresswiki.org/index.php/Farming),
[Alcohol](https://dwarffortresswiki.org/index.php/Alcohol),
[Thirst](https://new.dwarffortresswiki.org/index.php/Thirst),
[Using bins and barrels](https://dwarffortresswiki.org/index.php/DF2014:Using_bins_and_barrels),
[Fishery](https://www.dwarffortresswiki.org/index.php/Fishery),
[Fishing industry](https://dwarffortresswiki.org/index.php/DF2014:Fishing_industry),
[Activity zone](https://dwarffortresswiki.org/index.php/DF2014:Activity_zone),
[Trading](https://dwarffortresswiki.org/index.php/Trading).

DFHack docs, version 53.16-r1 (`docs.dfhack.org/en/stable/...`, confirmed
exact-version match to this install per `memory/dfhack-environment.md`):
[buildingplan](https://docs.dfhack.org/en/stable/docs/tools/buildingplan.html),
[workorder](https://docs.dfhack.org/en/stable/docs/tools/workorder.html),
[orders](https://docs.dfhack.org/en/stable/docs/tools/orders.html),
[seedwatch](https://docs.dfhack.org/en/stable/docs/tools/seedwatch.html),
[autobutcher](https://docs.dfhack.org/en/stable/docs/tools/autobutcher.html),
[autofarm](https://docs.dfhack.org/en/stable/docs/tools/autofarm.html),
[logistics](https://docs.dfhack.org/en/stable/docs/tools/logistics.html),
[quickfort blueprint guide](https://docs.dfhack.org/en/stable/docs/guides/quickfort-user-guide.html),
[Lua API Reference](https://docs.dfhack.org/en/stable/docs/dev/Lua%20API.html).

Repo files read in full or in the cited sections: `CLAUDE.md`,
`docs/PURPOSE.md`, `docs/AGENT-ARCHITECTURE.md`, `memory/dfhack-environment.md`,
`scripts/dfhack/TOOLS.yaml`, `agents/quartermaster/role.md`,
`agents/architect/tools.yaml`, `agents/overseer/tools.yaml`,
`research/2026-09-12-write-conflict-matrix.md`,
`research/2026-09-12-dfhack-capability-checks.md`, `blueprints/README.md`
and directory listing, `dfqueue/schema.py`, `decisions/DECISIONS.md`
(2026-09-15/16 rows).
