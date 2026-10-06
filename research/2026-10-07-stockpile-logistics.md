# Stockpile logistics for an autonomous fort agent, and Water Source / Fishing zone placement (DF v50)

Date: 2026-10-07. Read-only research, no live VM touched. Confidence tags: [CONFIRMED-SRC] read from primary source this session; [WIKI] DF wiki v50 text, read this session; [USER] direct play observation by the user; [INFERRED]; [RECALLED] from memory, not re-checked.

## Answer up front

1. The user's sentence is right and is also the v50 wiki's own recommended pattern: a **source pile** (takes from anywhere) near the producer, **satellite/feeder piles** at each consuming workshop set to take from links only and linked to take from the source pile. Workshops linked to a pile draw ONLY from linked piles, so a link is a restriction as well as a convenience.
2. Our repo already has the write primitives (`stockpile` place/configure/link/unlink/links/list). What is missing is not a verb but (a) the links-only flag, (b) container counts (max bins/barrels/wheelbarrows), (c) per-industry data saying "this workshop kind needs these input classes linked", and (d) a read that detects a starving linked workshop.
3. Water Source and Fishing zones go on ground tiles ADJACENT to water, not over it. The wiki and the user's direct observation (sunken pool, zone on the upper-level ground beside it, worked) agree. Our zone tool's on-the-water finder and two doctrine entries are the odd ones out.

## 1. Links: give to / take from

- Stockpile to stockpile: each pile can take from any number of piles; two piles cannot feed each other, but longer loops (A to B to C to A) are allowed. Creating "give to" creates the opposite "take from" on the other pile, and deleting one deletes both. [WIKI, Stockpile page]
- Pile to workshop: "the linked workshop will now only take from the stockpiles set to give to that workshop". Workshop page: "If any stockpiles are set to give to the workshop, only linked stockpiles will be looked in"; an unlinked workshop's dwarf looks for the nearest suitable item to the DWARF's position, not the workshop's. [WIKI, Workshop page]
- Incompleteness traps named by the wiki: link only ore to a non-magma smelter and nothing smelts (no fuel linked); link only plants to a still and it fails (no barrels, which come from a furniture pile). A linked workshop needs a pile for EVERY input class, including containers and fuel. [WIKI]
- Output side: items a workshop makes that the linked output pile does not accept are not moved anywhere; they sit in the workshop until some linked pile accepts them. [WIKI] This is the output-pile gotcha: an output link must accept what the workshop produces.
- Links-only toggle: when set, a pile takes only from its linked sources; otherwise it takes from anywhere. DFHack's stockpiles import/export carries it in the "General" block together with the container counts. [WIKI + DFHack docs `stockpiles`]. The wiki sentence on the default is ambiguous about polarity; do not encode a default from it, read the field live.
- Container settings: max barrels, max bins, wheelbarrows. Default is the pile's tile count (the most it can hold anyway). Setting barrels or bins to 0 is the documented way to stop barrel/bin spam. [WIKI]
- Feeder rationale (wiki Stockpile design page): a no-bin feeder that takes from anywhere beside a bin-using long-term pile that takes from links only means heavy bins travel a few tiles. The "seed stockpile problem" (barrels hauled long distances causing job-cancel spam) is solved by disallowing barrels in the source pile or using paired piles with minimal separation. [WIKI]
- Gotchas: a linked workshop starves when its feeder is empty because it will not look elsewhere [INFERRED from "only"]; wheelbarrow assigned but all in use; piles holding only forbidden items count as free space yet block storing [WIKI]. Whether a linked workshop's job is cancelled or left waiting when the feeder empties was NOT found in text.

## 2. Standard layouts

From the wiki Stockpile design page [WIKI], which itself says it emphasises principles over specific layouts:
- Still / kitchen: food-class pile beside them, barrels allowed; a source pile for crops by the farms (barrels disallowed, takes from anywhere), and a satellite pile at each plant-consuming workshop (still, farmer's workshop) set to links-only and linked to take from the source.
- Mason / mechanic / craftsdwarf: one feeder pile hugging the workshop ("place the feeder stockpile immediately around the workshop").
- Butcher and tanner adjacent to each other with a refuse pile for inputs; keep chained workshops close so each intermediate moves little.
- Smelter: ore pile plus fuel pile both linked (see trap above); output bars/blocks pile linked to take from the workshop.
- Central vs distributed: central long-term store (bins, links-only) fed by small no-bin feeders for finished goods; distributed point-of-use piles for workshop inputs.
Forum/reddit practice: searches returned only wiki mirrors; no Reddit or forum thread was reachable. Community claims beyond the wiki are NOT VERIFIED.

## 3. Hauling and DFHack logistics

- Dwarves put items in the empty spot nearest the item, ignoring obstructions, newest items first; the wiki warns of carrying back and forth and workshop slowdown from accumulation. [WIKI]
- Wheelbarrows are a per-pile count; bins and barrels per above. Minecarts: not researched beyond DFHack noting `stockpiles` can export "desired items" for hauling-route stops with `-r`. [DFHack docs]
- DFHack `logistics`: automelt, autotrade (only while a caravan is approaching or present), autodump, autotrain (plus autoretrain); toggled per pile via the overlay or the commandline pile id; checks marked piles twice per in-game day; noble-forbidden-export items are not marked for trade. [DFHack docs, logistics page] The page lists no autochop (a separate tool). `logistics` adds disposal and trade/melt intent, not workshop feeding; it does not replace links.
- Quickfort `#place` can set container counts and link targets per pile via `:key=val` properties; our stockpile tool's header records place.lua line refs for this [from the repo's earlier read, not re-read now]. The public quickfort docs page does not list the property names; confirm against the installed place.lua before building.

## 4. Domain-neutral view (warehouse / lean supply chain) [INFERRED, standard operations-management practice, not DF sources]

Transferable principles:
1. **Point-of-use storage with a bounded line-side buffer** (kanban): a small feeder pile at the workshop sized to a few jobs, replenished from the bulk store. Size it by consumption rate times replenishment latency, not "as big as possible".
2. **Pull, not push**: the downstream pile takes from the upstream one, so upstream bulk does not flood the line. In DF a pile's take-from is the pull signal; the bounded feeder is the kanban card count.
3. **Separate input and output flows, keep the chain acyclic and short**: a dedicated outbound buffer so the station is never blocked by its own output (the "sits in the workshop" gotcha is blocked-output starvation), minimal travel between chained stations.
Also worth stealing: a starvation monitor (feeder near empty while the downstream station idles is the alarm), which is the missing read in section 5.

## 5. What our repo already has

Primary read of `scripts/dfhack/df-overseer-stockpile.lua` (1005 lines) and `scripts/dfhack/TOOLS.yaml`:
- `list`: every pile, occupied/total tiles, accepts (17 coarse categories). Live-verified 2026-09-18.
- `links ID`: the four vectors (give_to/take_from by pile/workshop) for a pile or workshop. Live-verified 2026-09-18.
- `place W H [LEVEL] NEAR_LANDMARK CATEGORIES ...`, `configure ID CATEGORIES`, `link ID TARGET give|take`, `unlink ...`: added by handoffs/2026-10-01-stockpile-writing.md. link/unlink encode the four-case rule as one data table (LINK_RULE), no per-kind branches. Check TOOLS.yaml for each verb's live-verification status before relying on it; I did not.
- Quartermaster role.md (line 56) says pile creation is the Architect's.

Missing for chaining [CONFIRMED by grep over scripts/dfhack: no links-only, bins/barrels/wheelbarrows or container handling; the file header says container counts and finer filters are not exposed]:
- The links-only flag, read or write. Without it a "feeder" pile made by `place` is an any-source pile and the chain is not enforced.
- Max bins/barrels/wheelbarrows, read or write.
- Finer item filters than 17 coarse categories (a still feeder wants plants plus the container class, not "food").
- Industry data: no table "workshop kind to input classes needing a link (including containers, fuel) and output classes". `link` will happily create the single-class starvation trap the wiki warns about.
- A health read: per linked workshop, does every input class have a non-empty linked source, does the output link accept what it makes. docs/PRODUCTION-MODEL.md line 643 calls the link row "diagnosable, not fixable"; the fix half now exists, diagnosis is still only `links`.

**Correction to earlier research.** research/2026-09-24-df-ai-fort-planner.md records that no give/take link creation was found in df-ai. That is wrong. A code search this session found `plan_construct.cpp` in BenLubar/df-ai (develop branch, around lines 1396 to 1436, comment "setup stockpile links with adjacent level") which, for each new stockpile room, links same-type piles on adjacent levels by pushing onto `links.take_from_pile` and `links.give_to_pile` directly, with a duplicate check; workshop-attached piles force the direction. [CONFIRMED-SRC] So df-ai chains piles (a vertical same-type feeder chain) but never touches the workshop link vectors and never sets links-only.

## 6. Water Source and Fishing zones: where they go

- Wiki Zone page, Water Source: "Only tiles adjacent to water qualify as usable water sources - thus, if you want to place a single-tile zone, place the zone onto a ground tile next to the water, not over the water itself." With no Water Source zone any water is used; if at least one exists, dwarves drink only from those zones. [WIKI, fetched twice, wording identical]
- Fishing zone: "As with water sources, only tiles adjacent to water qualify as usable tiles"; "Dwarves can fish through a grate or even a well, provided there is water in the tile 1 z-level below the activity zone." A search excerpt of the wiki adds that a single tile drawn on open water does nothing except on a brook tile or above grate/floor bars [WIKI via search excerpt, not the page fetch].
- **User, direct play, treated as primary [USER]**: sunken pool (water one level below ground); zone marked on the upper-level ground beside the pool; it worked. Consistent with the wiki: "adjacent" evidently covers the tile one z-level above and beside the water, and the grate/well sentence shows the engine accepts water at z-1 of the activity tile.
- Verdict: wiki and user agree; on-the-water placement is not what the game documents. A dwarf CAN draw water and fish from a tile one z-level above the water, per the user's run. The exact adjacency rule (orthogonal only? diagonals? z+1/z-1 combinations) is not stated by the wiki. NOT VERIFIED.
- research/2026-09-17-pool-reachability.md, relevant findings: (i) all 27 wet tiles at z168 had zero walkable neighbours at that level, with z169 directly above them uniformly RAMP_TOP (dry, walkable-adjacent); (ii) `getWalkableGroup` returned 0 for ramp shapes that were physically adjacent to the walkable network, so walkability judgments near ramps were unreliable; (iii) it lists as not found whether Drink/GiveWater needs the same z or can act from a tile above, and infers (labelled inference) that it probably does not need to enter the water. The user's observation supports that inference. It also suggests the refuted doctrine entry's real fault was putting the zone on the water in a basin plus the walkable-group error, not that sunken ponds are undrinkable. [INFERRED, the link is mine]
- Repo conflict: `doctrine/seed.yaml` `water-source-zone-for-ponds` (status refuted) still says "place the zone on the water", contradicted by wiki and user. `water-source-needs-walkable-neighbour` requires a walkable tile adjacent at the water's OWN z-level; probably over-strict, since the user's working case used ground on the level ABOVE. Its measurement (27 wet tiles, 0 walkable neighbours at z168) remains a true read, but "no dwarf can reach it" was never tested with a zone on z169. `scripts/dfhack/df-overseer-zone.lua` `is_water_source_tile` (about line 505) demands the tile BE water (flow_size at least 1) and is the finder for WaterSource (line 227) and FishingArea (line 248 caveat), so the tool can never emit the adjacent-ground placement the game wants.
- Design reminder: no rendered map needed. A finder computes "walkable, building-free ground tile orthogonally adjacent to a water tile, or directly above a tile adjacent to water" from tile flags and shapes and returns it landmark-relative, as today.

## Not verified

- No Reddit/forum content reachable; community practice beyond the wiki is unconfirmed.
- Links-only default, exact UI naming, and the building field name (recalled as `use_links_only`, not read this session). DFHack docs do confirm a links-only preference in the stockpile settings serializer.
- What a linked workshop does when its feeder empties (job cancelled vs waiting).
- Exact adjacency rule for Water Source/Fishing zones.
- Quickfort `#place` property names for container counts, links and links-only.
- Minecarts and hauling routes beyond one DFHack docs line.
- df-ai finding comes from one code-search hit and about 60 lines read; searches for `give_to_workshop` and `links_only` returned nothing, but other paths could exist.

## Recommendations (data/tool changes)

1. Extend `stockpile` `list`/`links` (read) and `configure` (write) with two generic per-pile settings: links-only (boolean) and container counts (max bins, max barrels, wheelbarrows). Read the field live; do not hard-code a default.
2. Add a data table, workshop kind to {input classes, output classes}, derived from game data (job and reaction item requirements) with per-kind policy only for exceptions (still needs a container class; smelter needs fuel unless magma). A dry-run `stockpile plan-feed WORKSHOP_ID` then emits the piles and links needed for any kind with no new code per kind.
3. Add a `links-health` read: per workshop with any give-to link, the input classes with no non-empty linked source and whether the output link accepts the workshop's products.
4. Make `link` warn loudly in dry run (or refuse) when it would create the single-class trap: one input pile linked to a workshop whose requirement row lists unlinked classes.
5. Write the pattern into doctrine as data: source pile near the producer (any-source, barrels off for seed/plant piles), links-only satellite at each consumer, bounded size, short chain, output pile that accepts the workshop's products. Cite the wiki Stockpile design page and df-ai's adjacent-level same-type linking.
6. Rework the WaterSource and FishingArea finder to return walkable, building-free ground tiles adjacent to water (orthogonal, plus the level above a sunken pool), keeping the water-tile check as the anchor, not the placement.
7. Doctrine: amend `water-source-zone-for-ponds` (zone goes beside the water, on the upper level for a sunken pool) and soften `water-source-needs-walkable-neighbour` to "a walkable tile next to the zone, which for a sunken pool may be the level above". Cite the wiki Zone page and the user's observation. Test once on the fort's own pond when live work is next allowed.
8. Correct research/2026-09-24-df-ai-fort-planner.md: df-ai does set pile-to-pile links; only workshop links and links-only are absent.
