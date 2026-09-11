# Spatial Perception for an LLM-Driven Dwarf Fortress Agent

Date: 2026-08-25
Scope: DFHack 53.16-r1.1, installed at `C:\Program Files (x86)\Steam\steamapps\common\DFHack`
Status: design spec, not implemented. DF was not running during this research; nothing below was tested against a live game.

## 1. The constraint, restated as a design rule

LessWrong's "Dwarf Fortress and Claude's ASCII Art Blindness" documented Claude confusing selections and missing gross features (rivers) even with row numbers and color coding, and losing position awareness in Angband without constant coordinate lookups. This isn't a prompting problem that better formatting fixes — it's that transformers read a rendered 2D grid as a 1D token sequence, and the positional relationship between token *i* and token *i+row_width* is not something attention reconstructs reliably at the scale of a DF map (fortresses run hundreds of tiles per side, tens of z-levels).

**Design rule: the model is never shown a map. It is shown facts about the map, computed outside the model, in text that is inherently linear** (lists, tables, graphs-as-adjacency-lists, key-value summaries). Every piece of spatial reasoning — "is there room here," "can a dwarf get from A to B," "where's the river" — happens in code before the model sees anything.

This rules out: ASCII map dumps, tile-grid renders, coordinate-grid "read the map and tell me what's at row 12" prompts, and anything where map correctness depends on the model counting characters or rows.

The rest of this document was revised once already, mid-research, on a direct instruction: check whether this is a solved problem elsewhere before designing DF-specific machinery from scratch. It is solved elsewhere, repeatedly, in at least six traditions. Section 2 covers that prior art and says plainly where it changed the design; Section 3 onward is the DF-specific implementation, now informed by it rather than invented in isolation.

## 2. Prior art: this is not a new problem

"Convey navigable 2D/3D space through a serial text channel to a consumer that cannot see it" has been worked on continuously since at least 1978 (MUD1). Six traditions turned out to be directly relevant; three of them (accessibility research, robotics scene graphs, space syntax) changed concrete decisions in this design, not just its framing.

### 2.1 Text adventures / MUDs — the room-and-exits graph

The oldest and most direct precedent. From TinyMUD-era design (Raph Koster's retrospective on early virtual-world spatial models, and the MUD wilderness-systems literature): worlds are built from **rooms and exits**, where "a database entry defines a particular node, and the node has exits on it, which are unidirectional connections to another node... the convention is that exits are reciprocated," typically labeled by compass direction or up/down. Critically, the *canonical* MUD room has **no coordinates at all** — "you are in the dining hall; exits lead north to the stockpile, down to the mason's workshop" is a complete, navigable description with zero (x,y,z) anywhere in it. Coordinate-based "wilderness" systems were bolted on later, specifically for outdoor/overworld areas where the room-per-location model got too sparse, and were treated as the exception, not the rule.

**What transfers directly**: the default unit the model reasons over should be a *named node with named, directed, distance-labeled exits*, not a coordinate. Absolute (x,y,z) is an implementation detail the perception layer needs (to answer "how far" and to drive action tools like `designate_dig`), but it should not be the primary thing printed for the model to read and do arithmetic on — that reintroduces exactly the coordinate-tracking failure mode Angband testing already documented (LessWrong: "could not maintain position awareness without constant coordinate lookups"). **This changed the design**: the original draft of this document put `pos:[x,y,z]` in the model-facing landmark table as the primary field. §5's tool set now demotes coordinates to a code-only field and promotes a computed `exits` list (name, compass direction, distance, path-type) as the thing the model actually reads, mirroring the MUD room object.

**What doesn't transfer**: MUDs are hand-authored — a builder writes "the dining hall" and manually links its exits. DF has no builder; the fortress is discovered/constructed by play, so the room-and-exit graph has to be *extracted*, not authored. That extraction is the DF-specific work in §3–§4; MUDs don't need to solve it because a human already solved it once, by hand, at design time.

### 2.2 Roguelike/game accessibility for blind players — closest problem, most underused source

This is the same problem stated almost word-for-word: render 2D game space into a serial (audio/text) channel for a player with no visual access to a grid. Findings, from a mix of practitioner discussion and a peer-reviewed study of visually-impaired players' stated preferences:

- **NetHack specifically has a known, named failure mode for screen-reader players**: it gives no feedback when a character walks into a wall, whereas ADOM does (per a screen-reader-user discussion thread on itch.io). The lesson generalizes past accessibility: *silent failure on a spatial action is worse than a slow success* — an agent that issues a dig/build/move command needs an explicit, legible failure reason back, not a no-op. This is not something the original draft's tool set addressed at all (it was perception-only); §10 now flags it as a required property of the action-tool layer this document doesn't otherwise design.
- Players explicitly asked for **relative distance-and-direction callouts as the primary spatial primitive** — one participant's ask, quoted directly: report position as e.g. "5 East 3 North" relative to a reference point, not absolute coordinates. This independently corroborates the MUD-derived decision in §2.1 to make direction+distance-from-a-named-thing the model-facing default, from a completely unrelated line of work.
- A peer-reviewed study of visually-impaired gamers' preferences (Gerling et al.-style HCI work, ar5iv 2208.14573) found participants ranked **position/orientation information as the single highest-priority need**, above item/enemy presence — but rated **customizable filtering (controlling what information surfaces, and when) as equally important as raw accuracy**. Concretely, participants liked: a "menu-based exploration" mode — an alphabetical, queryable list of everything in the current area, read on demand rather than pushed continuously; and explicit "look in direction X" scanning rather than an always-on firehose.
- One accessible-roguelike effort (referenced in the ResearchGate paper on low-complexity NLP techniques for visually-impaired roguelike players) replaces the graphical/ASCII view entirely with **automatically generated natural-language descriptions of the same underlying state** — not a transcription of the grid, a re-derivation from the game's own structured data. That is the same move this document makes (derive prose/JSON facts from DFHack's structured API, never transcribe the tile array), independently arrived at by a different field solving a different-shaped instance of the identical serialization problem.

**This changed the design** in three places: (a) coordinates demoted to code-only, direction+distance promoted, per §2.1/§5; (b) the multi-resolution tiering in §7 is now explicitly justified as "customizable filtering," not just a token-budget trick — the accessibility literature treats on-demand, filtered disclosure as a first-class usability requirement, which reframes Tier 2/on-demand zoom as correctness-motivated, not merely cost-motivated; (c) §10 now calls out that action tools (outside this document's scope but assumed to exist) must never silently no-op on a spatial failure, echoing NetHack's documented accessibility bug.

### 2.3 LLM/VLM game-agent research — independent confirmation of the "never render" rule, plus a memory-graph pattern

- **BALROG** (Paglieri et al., arXiv:2411.13543 — a 2025 benchmark suite including the NetHack Learning Environment) found that giving models an *image* of the game state, instead of text, made performance **worse**, not better, across the board — "several models perform worse when visual representations of the environments are provided." This is a second, independent research effort (different games, different models, different year) reaching the same conclusion the LessWrong DF post reached: rendering the board is actively counterproductive for current LLMs, not merely unhelpful.
- **The NetHack Learning Environment** itself (Küttler et al. 2020, arXiv:2006.13760) does not give RL agents the raw terminal screen as the primary channel either — it exposes `glyph` grids *alongside* `blstats`, a flat vector of scalar structured features (position, HP, depth, hunger, etc.), and separately maintains `tty_chars`/`tty_colors` only for compatibility with human-facing tools. For LLM agents specifically, a follow-on "NetHack Language Wrapper" (ResearchGate, "A NetHack Learning Environment Language Wrapper for Autonomous Agents") exists purely to translate NLE's non-language observations (glyphs, blstats, inventory) into text — i.e., the field's own tooling converged on "structured state, translated to text by code" as the interface, not "screen contents." That is this document's central move, arrived at independently by an environment built years before any of this project's constraints existed.
- **Voyager** (Wang et al. 2023, arXiv:2305.16291), the Minecraft LLM agent, never gives the model a rendered view either — it interacts through a JS/Mineflayer API returning structured state, and its most-cited contribution is an **ever-growing skill library**: reusable, named, parameterized code snippets (not raw actions) retrieved by embedding similarity and composed over time. This validates direction 3 (push spatial reasoning into callable tools) as a pattern with a track record, not a novel proposal — Voyager's skills and this document's `find_open_area`/`check_reachable`/etc. are the same idea: the model calls a named capability, code does the spatial work, the model only sees the result.
- **AriGraph** (arXiv:2407.04363) has an LLM agent build and maintain a **persistent knowledge graph** — semantic facts as nodes/edges plus an episodic-memory overlay — while exploring text-adventure environments, explicitly to improve spatial orientation, and reports it "significantly enhances performance" versus giving the agent a raw growing transcript of observations. This directly validates §2.1's graph-not-list framing and §7's diff-based-update design: the graph should persist and be *updated incrementally* turn to turn, not rebuilt or re-dumped from scratch, which is exactly what `get_diff_since` (§5) is for.

**What doesn't transfer**: Minecraft/NetHack-RL environments are either fully synthetic-friendly (Minecraft's world is queryable block-by-block through a real API, no legacy binary to reverse-engineer) or purpose-built for agents (NLE's blstats exist because the environment's authors designed them in for this exact use case). DF/DFHack was not designed with an LLM agent in mind — the "translate structured state to text" layer these environments get for free is the thing §3–§9 of this document has to build.

### 2.4 Robotics — metric maps to topological/semantic scene graphs

This is the field that has solved "collapse a full 2D/3D geometric map into something a higher-level reasoner can use" as a mainstream, safety-critical, decades-old engineering problem — SLAM systems cannot hand a planner a raw occupancy grid either, for cost and reliability reasons close kin to the token-cost/reliability reasons here.

**Hydra** (Hughes et al., arXiv:2201.13360, MIT) builds a real-time **3D scene graph** with explicit hierarchy layers: "Layer 1 (bottom): a metric-semantic 3D mesh, Layer 2: objects... Layer 3: regions or places, Layer 4: rooms, Layer 5 (top): building." The construction pipeline: build a local Euclidean Signed-Distance Field from raw sensor data, extract a **topological map of places** from it (a places graph — essentially a connectivity skeleton, node per navigable area, edge per adjacency), then **segment the places graph into rooms using a community-detection-style clustering** over that graph. **ConceptGraphs** (cited alongside Hydra in the same search) does the analogous thing with open-vocabulary object labels instead of a fixed taxonomy.

This maps almost exactly onto the DF primitives already inventoried in §3, and the correspondence is worth being explicit about because it validates the architecture rather than just resembling it:

| Hydra layer | DF/DFHack equivalent | Note |
|---|---|---|
| 1: metric-semantic mesh | Raw `MapBlock` tile arrays (RFR) | Never surfaced past the aggregation layer, in both designs |
| 2: objects | `Item`/`UnitDefinition` (RFR), `dfhack.units`/item lists | |
| 3: places (topological skeleton) | `dfhack.maps.getWalkableGroup` connectivity | **DF gives this for free** — Hydra has to *compute* a places graph from raw geometry every run; DF's own pathfinder already maintains one, we just read it (§3.2) |
| 4: rooms (places clustered into rooms) | `dfhack.buildings` (workshops/stockpiles/player-designated rooms) + burrows | **DF also gives most of this for free** — Hydra has to run community detection to find room boundaries from bare geometry; DF already has a first-class `building`/`is_room` object for anything the player has built or zoned. Hydra's clustering step is only needed here for the *leftover* case: freshly-dug, unzoned open space that isn't yet a building or burrow |
| 5: building | Fortress-level `get_overview` | |

**This changed the design**: it demoted the bespoke maximal-rectangle scan (§4.3 originally) from "the algorithm" to "the algorithm for one case." Rectangle search answers "does a WxH rectangle fit," which is the right question for DF's grid-and-blueprint construction style in *built* areas, but it's the wrong question for **irregular natural spaces — caverns** — where "rectangular" isn't how the space is shaped and a rectangle-fit search will under-report usable area or reject a perfectly good cavern floor for not being rectangular. §5/§9 now note that cavern-scale open-area queries should use Hydra's actual technique — cluster the walkable-group tile set into sub-regions (e.g., a distance-transform/watershed-style split, the same family of technique Hydra's ESDF-based place extraction uses) rather than rectangle-fitting — and flags this as a harder, later build than the rectangle case.

### 2.5 Game AI terrain analysis — BWTA and chokepoint detection

**BWTA** (Brood War Terrain Analyzer; Perkins, AIIDE — ojs.aaai.org/index.php/AIIDE/article/view/12405) decomposes a StarCraft map into polygonal regions and **chokepoints** using a Voronoi diagram of the walkable space as the starting structure, then extracts the narrow connectors between regions as chokepoints. Validated against human map-readers: it found 97% of the chokepoints human participants identified. Its successor, BWTA2, is reported at least 10x faster via contour-tracing instead of full Voronoi construction — the original was slow enough (over a minute per map) to matter, which is itself a useful cost data point: even a mature, purpose-built region-decomposition algorithm on maps far smaller than a DF fortress was expensive enough that its performance became a headline feature of the sequel.

**This is a genuinely new addition, not just corroboration**: nothing in the original DFHack-only draft produced chokepoint/bottleneck data, and chokepoints are directly useful for a DF agent — they're the natural place to put a door, a drawbridge, a trap corridor, or a guarded checkpoint, and "where are our fortress's chokepoints" is a real question for both defense planning and traffic-flow ("is everyone funneling through one 1-wide hallway"). §5 adds `find_chokepoints`, deliberately specified as a **cheap heuristic approximation** of BWTA rather than a full Voronoi-based port: for DF's tile-grid (versus StarCraft's continuous walkable polygon), a chokepoint candidate is a walkable tile that (a) sits on the boundary between two different named regions (burrows/buildings) and (b) has a narrow local cross-section (e.g., both tiles perpendicular to the region-to-region axis are non-walkable). This is weaker than BWTA's Voronoi-skeleton approach but is O(region-boundary tiles), not O(map), and BWTA's own performance history (§ above) is a caution against reaching for the full algorithm before it's shown to be necessary.

### 2.6 Space syntax — the missing piece: scoring, not just describing, a location

Space syntax (Hillier & Hanson's architectural tradition) is the one source here that's about **evaluating** spatial configuration, not just representing it — which is precisely this design's weakest point, per the redirect that prompted this section: even with a perfect landmark graph, *choosing where to put a new room* is still a judgment call the model can't make well from raw geometry.

Core mechanism, from the space-syntax literature (spatialanalysisonline.com; isovists.org; the arXiv urban-morphology papers on axial-line generation): reduce a space to a graph — an **axial map** (nodes = the longest straight sightlines/movement-lines covering the free space, edges = where two lines cross) or a finer **visibility graph** — then compute **connectivity** (how many other nodes a node touches directly) and **integration** (roughly, the reciprocal of a node's mean topological/graph distance to every other node — "how many turns away is this location from everywhere else," normalized). High-integration spaces are predicted, and empirically found, to correlate with pedestrian through-movement and natural gathering points; low-integration spaces are the ones people (and, the tradition argues, activity) don't pass through by default. A related primitive, the **isovist**, is the polygon of everything visible from a single point — used as a per-location descriptor of openness/enclosure.

Directly relevant precedent for applying this to procedurally-scored placement, not just human-building analysis: **"Exploring Minecraft Settlement Generators with Generative Shift Analysis"** (arXiv:2309.05371) reports settlement-generation systems from the GDMC (Generative Design in Minecraft) competition that **score a large number of candidate structures/placements against terrain and configuration features, to select the best candidate to generate next**, and explicitly frames the evaluation using space-syntax-style network measures of the resulting settlement (how placement affects movement/connectivity patterns).

**This is the section that most directly answers the redirect's stated concern**, and it changes the design concretely: §6 (new) adds a `rank_candidate_sites` tool that does not ask the model to pick a location — it generates N candidate placements (from `find_open_area`'s output, or a grid sample over a bounded query region), scores each one on a small weighted formula, and returns a ranked, reasoned top-K for the model to choose among by name, never by coordinate arithmetic. The scoring formula's terms are a direct translation of the two independent traditions above:

- an **integration-style centrality term**: topological distance (edge-count, not tile-count) from the candidate to the landmark graph's existing high-traffic nodes (main stair, trade depot, current stockpiles) — computed over the same buildings+burrows adjacency graph §4 already builds, cheaply, since that graph is small (tens to low hundreds of nodes, not tiles);
- a **frontier/next-best-view-style cost-and-gain term**, borrowed from the robotics exploration literature (Yamauchi's original frontier-based exploration, and next-best-view planning — emergentmind.com/topics/next-best-view-problem — which score candidate viewpoints by combining travel cost with expected information gain): here, "cost" is travel distance/effort from the fortress's main circulation, and "gain" is proxied by proximity to whatever resource the room-type cares about (ore for a smelter, farmland for a farm plot, distance-from-threat for a barracks), each of which is already a fact this design's other tools can supply (`get_landmark`, `get_connectivity_report`, the resource summary in `get_overview`);

  **Addendum 2026-09-11, flagged before this tool gets built so it isn't missed**: the examples above are all "gain = proximity to a raw resource," but a real fort's placement logic is at least as often "gain = proximity to *another already-built room of a given kind*" — the concrete case that prompted this: a brewery should be sited near the farming room, not near ore. This is a cheaper signal than the resource-proximity terms above, not a harder one — it's `distance to nearest landmark where kind == X` over the exact same buildings/burrows adjacency graph §4 already builds and `df-overseer-landmarks.lua` already tags every building with (`kind`, confirmed live 2026-09-11: real values include `"Stockpile"`, `"Wagon"`), so no new perception primitive is needed, only a scoring term added to `rank_candidate_sites` once it's built. `purpose: str` in the signature below should resolve to a small lookup table (room-type → the landmark `kind`(s) it wants to be near/far from), not just a resource-type lookup — e.g. `purpose="brewery"` → gain term rewards proximity to `kind="FarmPlot"`, a bedroom's `purpose` might instead reward *distance* from `kind="Workshop"` (noise). Keep the two gain families (raw-resource proximity, built-room-kind proximity) as separate, addable terms in the same weighted sum, since a real placement often cares about both at once (a smelter wants to be near ore *and* near the stockpile that feeds it).
- an **isovist-adjacent size/shape-fit term**: does the candidate rectangle (or, for irregular cavern space per §2.4, clustered region) actually fit the requested WxH with margin, which `find_open_area`/the cavern-clustering variant already compute as a byproduct.

None of these terms individually is novel engineering — the point is that all three traditions independently converged on "reduce the space to a small graph, then score candidate nodes by a cheap weighted combination of graph-distance and local features," which is a strong signal that this is the right shape for the site-selection answer, not a from-scratch invention.

**What doesn't transfer**: space syntax's axial-map/isovist machinery is built for *continuous*, largely open, 2D urban space where "longest sightline" is a meaningful primitive. DF's fortress interior is discrete, gridded, heavily partitioned by walls, and often stacked across z-levels connected only by stairs — an axial map in the strict space-syntax sense doesn't obviously apply below-ground. What transfers is the *measure* (integration ~ centrality-in-the-connectivity-graph), computed instead over the buildings/burrows adjacency graph this design already produces, not over a geometric axial map. That's a deliberate substitution, not a direct port, and is flagged as such in §6.

## 3. What DFHack actually exposes — verified inventory

I did not take any of this on faith. Method: read the plain-text docs shipped at `hack/docs/docs/`, read the actual Lua source of stock scripts at `hack/scripts/`, and — where the local docs were too thin (they are, for RemoteFortressReader) — extracted the real compiled symbol table from the installed plugin DLL with `strings`, then cross-checked the message field layouts against the upstream DFHack source tagged `53.16-r1.1` (matching this exact install) to fill in fields the local docs don't list. Every claim below says which of those three sources backs it.

### 3.1 Remote/RPC layer (RemoteFortressReader) — for a truly external client

`hack/docs/docs/dev/Remote.txt` describes the wire protocol only (protobuf-over-TCP, port 5000, handshake, `BindMethod`/`RunCommand` as the only two hardcoded methods, everything else bound dynamically). It does **not** enumerate RemoteFortressReader's methods or messages — `hack/docs/docs/tools/RemoteFortressReader.txt` is 26 lines and only documents `RemoteFortressReader_version` and `load-art-image-chunk`.

The **actual RPC surface is not documented locally**. I recovered it directly from the shipped binary:

```
strings -n 6 hack/plugins/RemoteFortressReader.plug.dll | grep -iE "^(Get|Send)[A-Za-z]*$"
```

confirmed these RPC methods exist in the installed build (verified: DLL symbol table, `hack/plugins/RemoteFortressReader.plug.dll`):

```
GetBlockList, GetTiletypeList, GetMaterialList, GetPlantList, GetUnitList,
GetUnitListInside, GetMapInfo, GetItemList, GetBuildingDefList, GetWorldMap,
GetWorldMapNew, GetRegionMaps, GetRegionMapsNew, GetPlantRaws, GetPartialPlantRaws,
GetCreatureRaws, GetPartialCreatureRaws, GetLanguage, GetReports, GetViewInfo,
GetSideMenu, SetSideMenu, GetPauseState, SetPauseState, SendDigCommand,
CopyScreen, ResetMapHashes
```

and this full list of `RemoteFortressReader.*` protobuf message types (verified: same DLL, string table of message full-names, which protobuf embeds for reflection):

```
MapBlock, MapInfo, BlockList, BlockRequest, UnitDefinition, UnitList,
BuildingInstance, BuildingList, BuildingDefinition, MatPair, Coord,
Tiletype, TiletypeList, MaterialDefinition, MaterialList, Item,
PlantDef, PlantInstance, PlantList, PlantRaw, CreatureRaw, RegionMap,
RegionMaps, RiverTile, RiverEdge, FlowInfo, TreeInfo, TreeGrowth,
Report, ViewInfo, WorldMap, DigCommand, ...
```

The DLL strip level didn't retain field-level names (no `walkable`, `tile_dig_designation`, etc. showed up as separate reflection strings — release protobuf builds commonly keep message/RPC names but drop per-field descriptor strings). To get field-level schema I fetched the matching-tag source `plugins/remotefortressreader/proto/RemoteFortressReader.proto` from `github.com/DFHack/dfhack` at ref `53.16-r1.1` (the exact tag this install reports) via a web fetch, and had it return specific message bodies verbatim. **This is not a local file** — flagging it clearly as fetched from the internet, not shipped with the install, and I could not diff it byte-for-byte against the DLL to triple-confirm since the DLL has no field strings. Confidence: high (RPC/message *names* independently verified from the binary; the *field lists* below come from the single upstream source, unconfirmed by a second source). Key fields, as fetched:

```protobuf
message BlockRequest {
  optional int32 blocks_needed = 1;
  optional int32 min_x = 2; optional int32 max_x = 3;
  optional int32 min_y = 4; optional int32 max_y = 5;
  optional int32 min_z = 6; optional int32 max_z = 7;
  optional bool force_reload = 8;
}

message MapBlock {
  required int32 map_x = 1; required int32 map_y = 2; required int32 map_z = 3;
  repeated int32 tiles = 4;                     // tiletype id per tile (16x16 block)
  repeated MatPair materials = 5;
  repeated MatPair layer_materials = 6;
  repeated MatPair vein_materials = 7;
  repeated MatPair base_materials = 8;
  repeated int32 magma = 9;
  repeated int32 water = 10;
  repeated bool hidden = 11;
  repeated bool light = 12;
  repeated bool subterranean = 13;
  repeated bool outside = 14;
  repeated bool aquifer = 15;
  repeated bool water_stagnant = 16;
  repeated bool water_salt = 17;
  repeated MatPair construction_items = 18;
  repeated BuildingInstance buildings = 19;
  repeated int32 tree_percent = 20; repeated int32 tree_x/y/z = 21-23;
  repeated TileDigDesignation tile_dig_designation = 24;  // enum: NO_DIG/DEFAULT_DIG/UP_DOWN_STAIR_DIG/CHANNEL_DIG/RAMP_DIG/DOWN_STAIR_DIG/UP_STAIR_DIG
  repeated Item items = 26;
  repeated bool tile_dig_designation_marker = 27;
  repeated bool tile_dig_designation_auto = 28;
  repeated int32 grass_percent = 29;
  repeated FlowInfo flows = 30;
}

message BuildingInstance {
  required int32 index = 1;
  optional int32 pos_x_min/pos_y_min/pos_z_min = 2-4;
  optional int32 pos_x_max/pos_y_max/pos_z_max = 5-7;
  optional BuildingType building_type = 8;
  optional MatPair material = 9;
  optional uint32 building_flags = 10;
  optional bool is_room = 11;
  optional BuildingExtents room = 12;
  ...
}
```

**Implication for design**: `MapBlock` is delivered as a flat 16x16-tile array per block (256 ints for `tiles`, 256 bools for each flag array, etc.). A block-list request over any nontrivial area is exactly the grid data the model must never see raw — this RPC exists to feed *renderers* (Armok Vision), not agents. If we use RFR at all, it's exclusively on the code side of the boundary, aggregated down to a handful of facts before anything reaches the model. `BuildingInstance`, by contrast, is already a rectangle (`pos_x_min..pos_x_max`, `is_room`) — buildings are naturally graph nodes with no flood-fill needed, which is the DF-specific instance of the Hydra "rooms layer already solved" observation in §2.4.

### 3.2 In-process Lua API — the good stuff, and where most of the design should live

`hack/docs/docs/dev/Lua API.txt` (6888 lines) is exhaustive and, unlike RFR, fully documents the modules. Everything here runs *inside* the DF process (no serialization of map arrays over a socket) and can be invoked via `RunCommand` (the same RPC method `dfhack-run` uses) against a custom script, returning only whatever small text/JSON the script chooses to print. This is the cheap path.

**Connectivity — verified, and already computed by the game for free (this is DF's version of Hydra's "places" layer, §2.4):**

- `dfhack.maps.getWalkableGroup(pos)` (Lua API.txt:2233) — "Returns the walkability group for the given tile position. A return value of 0 indicates that the tile is not walkable. The data comes from a pathfinding cache maintained by DF." This *is* connected-component labeling — DF's own pathfinder already flood-fills the map into walkability groups every unpaused tick. We don't need to implement flood fill for reachability; we need to read a field.
- `dfhack.maps.canWalkBetween(pos1,pos2)` (Lua API.txt:2241) — checks both tiles walkable and share a group. Direct answer to "can a dwarf get from the stockpile to the workshop."
- Caveat, from the same doc entry: the cache only updates while unpaused, doesn't account for climbing/flying, and doesn't know about burrows or invader presence. `gui/pathable`'s doc (`hack/docs/docs/tools/gui/pathable.txt`) repeats the climbing/flying caveat.
- **Proof this is a real, working pattern, not just a doc promise**: `hack/scripts/warn-stranded.lua` (stock script, read in full) implements exactly the "is anyone stuck" check using this API. It calls `dfhack.units.getCitizens(true)`, gets each citizen's walkability group via `getWalkableGroup`, groups citizens by group id, and reports every group except the largest as stranded. This is a complete, working reference implementation for connectivity-based semantic assertions — no map rendering, ~40 lines of Lua, O(citizens) not O(tiles).

**Named regions — DF already has a "landmark" primitive: burrows**

`hack/docs/docs/tools/burrow.txt` and the Burrows module (Lua API.txt:2290-2333) give a named, persistent, arbitrary-shaped tile region with:
- `burrow tiles box-add <name> <pos1> <pos2>` — rectangle add (CLI, also has a Lua-level equivalent via the doc'd module functions `clearTiles`/`listBlocks`/`isAssignedTile`/`setAssignedTile`)
- `burrow tiles flood-add <name>` — flood fill that **explicitly uses walkability groups**: per burrow.txt, flood fill "match[es] the walkability group of the starting tile OR (if walkable) is adjacent to a tile with the same walkability group," and stops at inside/outside and hidden/revealed boundaries. This is DFHack's own connected-component room/area extractor, already built, already exposed as a command.
- `dfhack.burrows.getName(burrow)`, `findByName(name)`, `listBlocks(burrow)` — enumerate a burrow's tiles/blocks by name.
- `dfhack.persistent.saveSiteData` / `getSiteData` (used by `warn-stranded.lua` for its own state) is the mechanism to persist arbitrary Lua-table metadata (e.g., a landmark's declared purpose, creation turn) tied to the save.

This directly satisfies direction 4 (landmark anchoring), and lines up with the MUD room object (§2.1): a "Dining Hall" is a burrow named `Dining Hall`, created once via `flood-add`, and referenced forever by name. `listBlocks` gives its extent cheaply (block coordinates, not per-tile), and `dfhack.buildings.getSize`/`containsTile` (below) handle the finer-grained furniture inside it.

**Buildings/rooms/stockpiles — already segmented, no flood fill needed**

Buildings module (Lua API.txt:2338-2510):
- `dfhack.buildings.getSize(building)` → `width, height, centerx, centery` — already a rectangle.
- `dfhack.buildings.getName(building)`, `getRoomDescription(building[,unit])` — e.g. "Royal Bedroom."
- `dfhack.buildings.findAtTile(pos)`, `findCivzonesAt(pos)` — point→building/zone lookup.
- `dfhack.buildings.getStockpileContents(stockpile)` — item list on a stockpile, ignoring empty containers.
- `dfhack.buildings.containsTile(building,x,y)` — respects non-rectangular extents.

Every workshop, stockpile, zone and player-designated room in DF is already a `building` object with a bounding box (and the RFR `BuildingInstance` message mirrors this: `pos_x_min/max`, `pos_y_min/max`, `is_room`, `room` extents). **This means "rooms" as graph nodes largely don't require any custom segmentation algorithm** — enumerate buildings, each one is a node with a rectangle, a type, and (via `findAtTile` on its border or via burrows) adjacency to corridors. Only *un-built, un-zoned open space* (a freshly dug corridor with nothing placed in it yet, or natural cavern floor) needs an actual geometric scan — that's the one place a real "find open area" algorithm (§5.3) is needed, and per §2.4 it's two different algorithms depending on whether the space is grid-regular (rectangle scan) or cavern-irregular (cluster the walkable-group tile set).

**Units / jobs — for "is anything stuck," "is there a threat"**

Units module (Lua API.txt:1412 onward, partially read): `dfhack.units.isCitizen`, `isSane`, `isCrazed`, `isHidden`, `getCitizens([exclude_residents[,include_insane]])` (1653), `getPosition(unit)` (1657, preferred over raw `unit.pos` "since that field can be inaccurate when the unit is caged"), `getVisibleName`, `getProfessionName`.

Job module (Lua API.txt:1276-1412): `dfhack.job.getWorker(job)`, `getHolder(job)` (building holding it), `getName(job)`. Raw struct fields confirmed in use across multiple stock scripts (`do-job-now.lua`, `gui/advfort.lua`): `job.pos` (x/y/z) and `job.flags.working` (boolean). I could **not** find a stock script that walks the full `df.global.job_list` linked list to enumerate every job fortress-wide — that idiom (`df.global.job_list.next.item...`) is standard, widely-documented DF-structures knowledge but I have no local script exercising it to point to, so I'm flagging it as **unverified-locally-but-standard**: use with a touch more caution, and validate the traversal against a live game before relying on it. Detecting "no citizen is dedicated to job X" or "job X has been waiting N ticks with no worker" is a straightforward filter over that list once traversal is confirmed (`job.flags.working == false` and no `getWorker` result). **Corrected 2026-09-10, verified live**: this field does not exist on this build (53.16-r1.1) — `df.global.job_list` errors with "not found." The real fortress-wide job list is **`df.global.world.jobs.list`**, same linked-list shape (`.next`/`.item`, confirmed live traversing it against a real running fort), just nested under `world.jobs` rather than sitting directly on `global`. Update any future code against the real field name, not this one.

**Event-driven diffs (this matters a lot for the caching design in §7, and is DF's real-world version of AriGraph's incrementally-updated memory graph, §2.3)**

`hack/docs/docs/tools/eventful.txt` points at the eventful plugin's Lua API (Lua API.txt ~6420-6460): `eventful.enableEvent(evType, frequency)` plus per-event callback tables (e.g. `eventful.onItemContaminateWound`, reaction hooks). Grepping actual event-type usage across stock scripts (not just the doc) confirms these event types are real and used in shipping code:

```
grep -rhoE "eventful\.eventType\.[A-Z_]+" hack/scripts →
BUILDING, INTERACTION, INVENTORY_CHANGE, JOB_COMPLETED, JOB_INITIATED,
REPORT, SYNDROME, UNIT_ATTACK, UNIT_DEATH, UNIT_NEW_ACTIVE, UNLOAD
```
`hack/scripts/prioritize.lua` (stock script, read in full) is a working example: it calls `eventful.enableEvent(eventful.eventType.JOB_INITIATED, 5)` and reacts to individual job-start events rather than polling all jobs every tick.

This means diffs (direction 6) don't have to be computed by re-snapshotting the world and comparing — DF can push them. A perception service can register `JOB_COMPLETED`, `UNIT_DEATH`, `INVENTORY_CHANGE`, `BUILDING` handlers, accumulate a small append-only log in a Lua table between agent turns, and hand the model *only that log* plus whatever crossed an alert threshold. This is materially cheaper than full-state diffing and maps well onto "volatile content last" prefix-caching.

**JSON and CLI text output — the actual transport**

`hack/lua/json.lua` exists and exposes `json.encode(table)` / `json.decode(string)` (confirmed by reading the file: `function encode(data, options, msg)`, `function decode(data, msg)`). Combined with `RunCommand`'s text-capture (per `Remote.txt`: the server sends zero-or-more `text` (`CoreTextNotification`) messages before the final `result`, and `dfhack-run` is the reference client for exactly this flow), a custom Lua script can `print(json.encode(fact_table))` and any RPC client — including the trivial case of shelling out to `dfhack-run <script>` — gets structured JSON back over stdout/text-notification, with **no protobuf client library needed at all** for anything except the rare case where raw MapBlock geometry is genuinely required. This is functionally the same role NLE's "Language Wrapper" (§2.3) plays for NetHack: a code layer that turns environment-native structured state into agent-facing text, on our own terms, once, rather than per-call.

### 3.3 Stock tools as reference implementations (compiled plugins, docs read, source not always available)

- `prospect` (`hack/docs/docs/tools/prospector.txt`) — "Shows a summary of resources that exist on the map" (layers, ores, gems, veins, shrubs, trees, liquids, features), filterable by `--show`. This is a pre-aggregated, code-computed, small-text semantic summary — exactly the shape direction 2 asks for. It's a compiled plugin (`hack/lua/plugins/prospector.lua` is a 40-line CLI-arg-parsing wrapper, `hack/plugins/prospector.plug.dll` does the real work) — I could read the wrapper (confirms the `--show`/`-v` interface) but not the aggregation logic itself. Output is CLI text, not JSON; a perception service either parses that text or reimplements the aggregation in Lua against `MapBlock`-equivalent per-tile material fields, which the RFR proto (§3.1) shows are the same fields (`base_materials`, `layer_materials`, `vein_materials`) `prospect` itself must read.
- `pathable` / `gui/pathable` (`hack/docs/docs/tools/pathable.txt`, `gui/pathable.txt`) — visual highlighting only (ASCII green/red tile overlay or a graphics-mode icon); the Lua wrapper (`hack/lua/plugins/pathable.lua`) exposes one native function, `paintScreen(cursor[,skip_unrevealed])`, which paints, it doesn't return structured data. Not directly reusable for text output — `getWalkableGroup`/`canWalkBetween` are the reusable primitives underneath it.
- `probe`/`bprobe`/`cprobe` (`hack/docs/docs/tools/probe.txt`) — dumps low-level tile/building/unit properties for one target, driven by the in-game cursor or `--cursor x,y,z`. Fine for interactive debugging by a human; too fine-grained and manually-cursored to be a per-turn agent tool, but useful as a "zoom" fallback (direction 5) for a single tile the model has asked about by name/coordinate resolved from a landmark.
- `blueprint` (`hack/docs/docs/tools/blueprint.txt`) — exports a live map region to quickfort's `.csv` blueprint format (dig/carve/construct/build/place/zone phases). This is structured, but it's still fundamentally a per-tile grid serialized as CSV rows — useful for round-tripping a *known* rectangular area, not for search or reasoning, and not something to hand the model unless the area is small and the model's task is literally "describe this blueprint back."
- `quickfort` (`hack/docs/docs/tools/quickfort.txt`) — the write-side counterpart to `blueprint`: applies a blueprint (dig/build/place/zone) to the map. Relevant to the agent's *action* tools, not perception.
- `stocks`, `zone` — UI/management-focused; underlying data (stockpile contents, zone assignment) already covered by the Buildings/Units module functions above.
- `getplants` — designation tool (chop/gather), not perception; relevant only as an action-tool.

## 4. Recommended design, and verdicts on the six directions

With §2's prior art folded in, here is where each of the prompt's six directions lands.

**1. Space as a graph, not a grid — yes, and mostly already built, both in DF and elsewhere.** `getWalkableGroup` gives free connected-component labels for reachability at the whole-map scale — this is literally Hydra's "places" layer (§2.4), pre-computed by DF's own pathfinder rather than something we extract from raw geometry the way a robot has to. `BuildingInstance`/`dfhack.buildings` gives free rectangle nodes for every workshop/stockpile/zone/room — Hydra's "rooms" layer, also pre-computed, because DF already models rooms as first-class objects (a robot mapping an unknown building doesn't get this for free; we do). Burrows give a free named/flood-fillable region primitive for everything else, functioning as the MUD "room" object (§2.1) for space DF itself doesn't already segment. The genuinely new code needed: turning "list of buildings + list of burrows" into an adjacency list with named, directed, distance-labeled edges (mirroring a MUD room's exit list, not a coordinate table — §2.1/§2.2), and the open-space finder for un-zoned corridors and caverns (§5.3, now two algorithms per §2.4: rectangle-scan for built/gridded space, cluster-the-places-graph for natural cavern space). This is cheap and should be built first.

**2. Semantic assertions instead of geometry — yes.** This is the natural output shape of everything in §3.2/§3.3, and it's also just what NLE's Language Wrapper and the accessible-roguelike NLP layer (§2.2, §2.3) already do for their respective games: derive prose/JSON facts from structured state, never transcribe a grid. "No path from stockpile A to workshop B" = one `canWalkBetween` call. "12x8 unobstructed area 20 tiles east of the main stair" = the rectangle-finder in §5.3, scoped to a query window. "River runs north-south at x=45" is the one item I could **not** verify a ready-made primitive for: RFR's `RiverTile`/`RiverEdge` messages exist (DLL-verified names, §3.1) but field-level detail is unverified. Fallback: `prospect --show liquids` (verified) reports surface water/magma presence, coarser but confirmed-real.

**3. Spatial reasoning pushed into code as tools — yes, and this is the load-bearing recommendation, not one of six equally-weighted options.** Every primitive in §3 is a code-side call. §2.3 shows this is also the field-standard pattern for LLM game agents specifically — Voyager's skill library and NLE's language wrapper are the same move in two other environments, independently. §5 gives the concrete tool set.

**4. Landmark anchoring + relative directions — yes, and per §2.1/§2.2, this should be the *primary* representation, not a formatting nicety layered over coordinates.** Burrows (persistent, named, arbitrary shape) plus buildings (persistent, named-by-type, rectangular) are the nodes; the perception service computes direction+distance edges between them once and serves that graph, the same shape as a MUD room's exit list and the same primitive blind-gamer accessibility research asked for directly ("5 East 3 North" instead of absolute position, §2.2).

**5. Multi-resolution — yes, and per §2.2 this is a correctness requirement (accessibility research's "customizable filtering," rated as important as raw accuracy), not just a cost optimization.** §7 defines three tiers.

**6. Diff-based updates — yes, and DFHack's `eventful` plugin (verified, §3.2) makes this push-based, the same shape as AriGraph's incrementally-updated memory graph (§2.3) rather than a snapshot-diff.** §7 covers the DeepSeek-caching-specific ordering requirement.

**New, from prior art, not in the original six**: chokepoint detection (§2.5, BWTA) and candidate-site scoring (§2.6, space syntax + Minecraft GDMC + robotics frontier/NBV) are added to the tool set below because they directly address the redirect's flagged weak point — site selection — which none of the original six directions actually solves on their own. "Landmark anchoring" tells the model where things *are*; nothing in the original draft told it where things *should go*.

## 5. Minimal tool set

All tools are implemented **server-side** as one custom DFHack Lua script (or a small family of them) exposed over `RunCommand`, returning JSON via `json.encode`. The model only ever sees the tool name, its arguments, and the JSON result — never a map render, and per §2.1/§2.2, coordinates are demoted to a code-usable field rather than the primary thing printed for the model. Cost tier: 🟢 cheap (sub-millisecond to a few ms, O(1) or O(regions)), 🟡 moderate (tens of ms, O(bounded query area)), 🔴 expensive / must be scoped or cached (O(map), avoid calling on every turn or over the whole map).

```
get_overview() -> {
  turn, in_game_date, population, alerts: [str],
  landmarks: [{name, kind, exits: [{to, direction, distance_tiles, via}]}],
  resource_summary: {...}
}
```
🟢 Backing: `dfhack.world.ReadCurrentYear/Month/Day/Tick` (verified, §3.2) for date; `dfhack.units.getCitizens` count for population; burrow/building enumeration for landmarks (§3.2); `prospect` text or a Lua reimplementation over `base_materials`/`layer_materials` for resources. Landmark entries deliberately lead with `exits`, not `pos` — pos still exists as a field for code consumers (action tools need it) but is not the field the model is expected to reason from, per §2.1/§2.2.

```
list_landmarks(kind?: "room"|"workshop"|"stockpile"|"zone"|"custom", near?: str, radius?: int) -> [
  {name, kind, exits: [...]}
]
```
🟢 Backing: enumerate `df.global.world.buildings.all` filtered by type (via `dfhack.buildings.*` helpers) + `dfhack.burrows.findByName`/iteration over defined burrows. Filtering "near" a named landmark is a centroid-distance filter in code.

```
get_landmark(name: str) -> {
  name, kind, dims:[w,h], contents: [...], exits: [{to, direction, distance_tiles, via}]
}
```
🟢 Backing: `dfhack.buildings.getSize/getStockpileContents/getRoomDescription/containsTile`, `dfhack.burrows.listBlocks`. `pos`/centroid available but secondary.

```
check_reachable(from: str, to: str) -> {
  reachable: bool, from_group: int, to_group: int, note?: str
}
```
🟢 Backing: `dfhack.maps.canWalkBetween` / `getWalkableGroup` (verified, §3.2). Named endpoints resolve via `get_landmark`'s centroid internally, never exposed to the model as coordinates.

```
get_connectivity_report() -> {
  stranded_groups: [{unit_names: [str], near_landmark: str, group_id: int}],
  main_group_id: int
}
```
🟢 Backing: direct reuse of `warn-stranded.lua`'s `getStrandedGroups()` logic (verified, read in full, §3.2) — close to a drop-in. `approx_pos` from the original draft is replaced with `near_landmark` (nearest named landmark + direction/distance), computed the same way as everywhere else.

```
find_open_area(w: int, h: int, z: int, near?: str, radius_tiles?: int, terrain: "built"|"cavern") -> [
  {near_landmark: str, direction: str, distance_tiles: int, dims:[w,h], walkable_group: int}
]
```
🟡 Backing: no ready-made DFHack primitive — new code. `terrain="built"` uses the maximal-rectangle scan (§5.3); `terrain="cavern"` uses places-graph clustering per §2.4's Hydra correspondence, a harder, later build (§8). Must be bounded by `near`+`radius_tiles` (mirroring RFR's own `BlockRequest` box shape, §3.1) — see §8 for the cost math on why this guardrail is non-optional.

```
find_chokepoints(near?: str, radius_tiles?: int) -> [
  {between: [landmark_a, landmark_b], pos_for_action_tools: [x,y,z], width_tiles: int}
]
```
🟡 Backing: new code, a deliberately simplified heuristic version of BWTA (§2.5) — not a full Voronoi-skeleton port. A candidate tile is walkable, borders two different named regions, and has a narrow local cross-section. `pos_for_action_tools` is the one place in this tool set where a raw coordinate is the point of the output (a door/trap has to be built *somewhere specific*) — that's fine, it's still code computing it and handing the model a small, bounded list, not the model deriving it from geometry.

```
rank_candidate_sites(w: int, h: int, z: int, purpose: str, near?: str, radius_tiles?: int) -> [
  {rank: int, near_landmark: str, direction: str, distance_tiles: int, dims:[w,h],
   score: float, reasons: [str]}
]
```
🟡 Backing: new code, composing `find_open_area`'s candidates with the scoring formula from §6. This is the direct answer to the flagged weak point: the model never picks a location by geometry, it picks a rank/name from a pre-scored, pre-reasoned list.

```
get_unit_status(filter?: "idle"|"injured"|"military"|"hostile") -> [
  {name, profession, near_landmark: str, status, current_job?}
]
```
🟢/🟡 Backing: `dfhack.units.getCitizens`, `isCitizen/isSane/isCrazed`, `getPosition`, `getProfessionName` (all verified, §3.2). "idle" = citizen with no `current_job`; "hostile" = non-own-civ active units — **unit flags (`flags1/2/3` in `UnitDefinition`, or the equivalent raw `unit.flags1` bitfield) carry invader/hostile status but I did not verify the exact bit names against local docs or source; treat as standard DF-structures knowledge, confirm against a live game before trusting the classification.**

**Corrected 2026-09-11** (`decisions/DECISIONS.md` same date, two rows): built and verified this primitive as `scripts/dfhack/df-overseer-labor.lua`'s `unit-status`. The raw-flag question above turned out moot — `dfhack.units.isDanger`/`isInvader`/`isOwnCiv` are real, documented, present-on-this-install functions, no raw bit reading needed. But the resulting "hostile" filter is a **worse signal than this section assumed, not just an implementation detail to pin down** — confirmed with two independent live cases the same day: `isDanger` flagged 4 harmless deep-cavern demons the fort will never encounter (too broad), then completely missed a real kea attack that killed the kea and wounded a dog at the fort's own door, before, during, and after the fight (too narrow — see the DECISIONS.md row, "First real combat on Uniboslan"). The actual signal a fort-defense caller needs — "something is attacking something, right now" — is an event, not a static-world-state predicate; `get_diff_since` (item 5, `eventful`-backed, not built yet) is the more likely correct home for this than a better `isDanger`-style filter here.

```
get_stuck_jobs(min_idle_ticks: int) -> [
  {job_type, near_landmark: str, building?, waiting_on?: str, idle_ticks: int}
]
```
🟡 Backing: `df.global.job_list` traversal (raw struct, **unverified locally**, §3.2) cross-referenced with `dfhack.job.getWorker`. Build and test this one against a live save before relying on it. **Corrected 2026-09-10**: the real field is `df.global.world.jobs.list`, not `df.global.job_list` — see §3.2's correction.

```
get_diff_since(cursor: str) -> {
  cursor: str,
  events: [{type, at_tick, near_landmark?, unit?, building?, detail}]
}
```
🟢 Backing: `eventful.enableEvent` handlers (verified event types, §3.2) appending to a ring buffer keyed by a monotonic tick/sequence cursor; `get_diff_since` drains everything after the given cursor. This is the DF implementation of the AriGraph incremental-memory-graph pattern (§2.3).

```
create_landmark(name: str, method: "box"|"flood", pos1: [x,y,z], pos2?: [x,y,z]) -> {ok: bool, name, tiles_added}
designate_dig(shape: "room"|"corridor"|"stairs", pos, dims) -> {ok: bool, quickfort_ref?, failure_reason?}
```
Action tools, not perception, included because "where to dig" decisions are closed-loop with the landmark system. Backing: `burrow tiles box-add`/`flood-add` (verified CLI, §3.2) for the first; `quickfort`/direct dig-designation flag writes for the second. Per §2.2's NetHack wall-bump lesson, `designate_dig` (and any other action tool) **must** return an explicit `failure_reason` on failure rather than silently no-op-ing — this is a correctness requirement surfaced by the accessibility literature, not a nice-to-have, and it's the one place this document deliberately reaches past pure perception to flag a requirement on the action layer it otherwise doesn't design.

### 5.3 The core algorithms

**`find_open_area`, `terrain="built"`** — scoped query only (never whole-map):

```
function find_open_area(w, h, z, box)  -- box = {min_x,max_x,min_y,max_y} from near+radius
  local grid = {}  -- 2D boolean, box-sized, true = usable
  for x = box.min_x, box.max_x do
    for y = box.min_y, box.max_y do
      local walkable = dfhack.maps.getWalkableGroup(xyz2pos(x,y,z)) ~= 0
      local free = walkable and not dfhack.buildings.findAtTile(xyz2pos(x,y,z))
      grid[x][y] = free
    end
  end
  return largest_rectangles(grid, w, h)  -- classic maximal-rectangle scan, O(box_area)
end
```
Standard "maximal rectangle in a binary matrix" scan (histogram/stack method), O(box_area), bounded by construction to the caller-supplied box — enforce the radius cap at the tool-schema level (e.g. cap `radius_tiles` at 60), not just as a recommendation.

**`find_open_area`, `terrain="cavern"`** — per §2.4, not a rectangle scan. Sketch: take the set of walkable tiles in the query box sharing a `getWalkableGroup` id (DF's places-graph equivalent), compute a distance-transform from the nearest non-walkable tile for each member, and split the region at local minima of that transform (a watershed-style split — Hydra's own place→room segmentation is a community-detection variant of the same family of idea, applied to a graph rather than a raster; either is workable here). This is meaningfully more implementation work than the rectangle case and should be built after everything else in §5 is working (§8).

**`find_chokepoints`** — heuristic BWTA (§2.5): for each pair of adjacent named regions (from the landmark adjacency graph), scan their shared boundary tiles; a boundary tile is a chokepoint candidate if the two tiles perpendicular to the boundary-crossing direction are both non-walkable (i.e., the passage is exactly one tile wide at that point). O(boundary length), not O(map) — cheap because it only runs over the tiles bordering already-known regions, never a blind full-map scan.

**`rank_candidate_sites`** — see §6 for the scoring formula; the function itself is just `find_open_area(...)` (or the cavern variant) followed by a `score()` call per candidate and a sort.

## 6. Site selection: scoring candidate locations

This section exists because the redirect that shaped this document's second draft identified it as the weakest link, and because §2.6's cross-domain research gives a concrete, cheap answer rather than leaving it as an open problem.

The formula, computed entirely in code over the landmark adjacency graph and the resource/threat facts other tools already produce — the model never sees or adjusts raw weights mid-reasoning, it sees the *output* (ranked candidates with reasons) and can ask for a re-rank with different `purpose`/weights as a new tool call if the first ranking doesn't fit:

```
score(candidate, purpose) =
    w1 * centrality_term(candidate)      -- space-syntax "integration," §2.6
  + w2 * proximity_term(candidate, purpose)  -- frontier/NBV "gain," §2.6
  - w3 * travel_cost_term(candidate)     -- frontier/NBV "cost," §2.6
  - w4 * threat_exposure_term(candidate) -- distance from known threats/chokepoints, §2.5
```

- `centrality_term`: mean topological (edge-count, not tile-count) distance from `candidate` to a fixed set of high-traffic landmarks (main stair, trade depot, existing stockpiles) over the buildings+burrows adjacency graph §4 builds — cheap, since that graph has tens to low hundreds of nodes. High-traffic room types (dining hall, main stockpile) want this term maximized (low distance = high integration); low-traffic/sensitive room types (prison, isolated workshop, quarantine) want it minimized.
- `proximity_term`: purpose-specific — distance to nearest relevant resource (ore vein for a smelter site, farmable soil for a farm plot, magma for a magma forge), sourced from `get_overview`'s resource summary or a targeted `prospect`-equivalent query.
- `travel_cost_term`: tile-distance-along-the-walkable-graph (not straight-line) from the fortress's main circulation, i.e. actual walk cost, not displacement — directly borrowed from frontier-exploration cost terms (§2.6).
- `threat_exposure_term`: proximity to known chokepoints/cavern breaches/unexplored-hostile areas — pulls dangerous-adjacent room types (barracks, traps) toward the term and safe/sensitive ones (nursery, hospital) away from it; sign flips by `purpose`.

Weights (`w1..w4`) are a per-`purpose` lookup table (dining hall weights centrality heavily and threat lightly; magma forge weights proximity-to-magma heavily and accepts higher travel cost) — this is configuration, not model-facing reasoning, and is the kind of thing that should start as a small hand-tuned table and only become learned/adjustable later.

**Honest caveat**: this formula is a synthesis of patterns from three fields that validate *the shape* of the answer (reduce to a small graph, score candidates by a cheap weighted combination of graph-distance and local features) — none of the three fields' exact formulas are being ported verbatim, because none of them target DF's specific mix of discrete tile-grid, multi-z-level stacking, and DF-specific room semantics (a "dining hall" has no equivalent evaluation target in space syntax or GDMC's Minecraft settlement scoring). Treat the weight table as a starting point to be tuned against actual play outcomes, not a validated result.

## 7. Multi-resolution + diff-based context, structured for DeepSeek prefix caching

DeepSeek's context cache hits only on a byte-identical prefix, matched in 64-token blocks starting at token 0. Two consequences that must be designed for, not bolted on:

1. **Ordering**: anything that changes between calls must be placed strictly after everything that doesn't, in the same message. If the volatile alert line is interleaved with stable landmark data, the entire block containing it — and everything after it — misses cache, even though most of the content didn't change.
2. **Determinism**: "doesn't change" must mean byte-identical, not semantically-equivalent. JSON key order, whitespace, and number formatting must be pinned — Lua table iteration order is not guaranteed, so the encoder must sort keys explicitly or the "stable" section will silently re-shuffle and bust the cache every turn for no reason.

Three tiers, ordered stable-to-volatile within a single system/context block. Per §2.2, this tiering is doing double duty: it's a cost optimization for the cache, and it's independently the correctness pattern accessibility research calls "customizable filtering" — controlling what surfaces, and when, rated by visually-impaired players as equally important as raw data accuracy.

- **Tier 0 — session-constant (goes first, essentially never changes)**: tool schemas, ruleset/embark parameters, fortress name and starting site facts. Cache hit rate should approach 100% after turn 1.
- **Tier 1 — slow-changing overview (changes every few dozen turns)**: the landmark table (names/kinds/exits), population count, resource summary. Re-serialize deterministically; it will usually match the previous turn's bytes exactly and extend the cached prefix.
- **Tier 2 — volatile tail (changes every turn, goes last)**: `get_diff_since` event log, current alerts, idle/stuck-job counts, the in-game date/tick counter. This is deliberately the *only* part expected to miss cache each turn — keep it short.

On-demand zoom (direction 5's second half) is just Tier-2-shaped tool calls issued mid-turn (`get_landmark`, `find_open_area`, `rank_candidate_sites`, a `probe`-equivalent single-tile query) rather than part of the standing context — the MUD/accessibility "menu-based exploration, queried on demand" pattern (§2.1/§2.2) applied directly.

## 8. Cost/complexity notes — what's cheap, what's expensive, build order

| Piece | Cost | Why |
|---|---|---|
| `getWalkableGroup`/`canWalkBetween` reachability | 🟢 free | DF already maintains this cache every unpaused tick; we just read a field (verified, §3.2, and used live in `warn-stranded.lua`) |
| Building/burrow enumeration → landmark table | 🟢 cheap | O(number of buildings/burrows), typically low hundreds even in a large fort, not O(tiles) |
| `get_connectivity_report` (stranded citizens) | 🟢 cheap | O(citizens), reuses `warn-stranded.lua`'s exact algorithm |
| `get_diff_since` (event-driven) | 🟢 cheap, amortized | Push-based via `eventful`, not snapshot-diff |
| `prospect`-equivalent resource summary | 🟡 moderate, but infrequent | Fine to run occasionally, not every turn; rarely changes turn-to-turn anyway (Tier 1) |
| `find_chokepoints` | 🟡 moderate | O(boundary tiles between known regions), not O(map) — but only as cheap as the landmark graph it's scoped to; a fortress with very few named regions makes this cheap almost by accident, one with hundreds of tiny burrows would make it expensive — worth capping region count, not just tile count |
| `find_open_area`, `terrain="built"`, scoped | 🟡 moderate | O(box_area); cheap if callers are forced to pass a bounded radius, expensive/dangerous if not — BWTA's own history (§2.5: a mature, purpose-built algorithm was slow enough on StarCraft-sized maps to justify a 10x-faster sequel) is a caution against assuming any region-decomposition algorithm is free by default |
| `find_open_area`, `terrain="cavern"` | 🔴 build last | Distance-transform/clustering over a places graph is real algorithmic work, not a field lookup — treat as the hardest single piece in this tool set |
| `rank_candidate_sites` | 🟡 moderate | Dominated by its `find_open_area` call; the scoring pass itself is O(candidates), trivial |
| `GetBlockList` (RFR) over any nontrivial region | 🔴 avoid on the hot path | Flat per-tile arrays (§3.1); tolerable as an internal input to a code-side aggregator over a bounded window, never as text handed to the model, never over a full fortress footprint in one call |
| `df.global.world.jobs.list` full traversal per turn (named `df.global.job_list` here originally — corrected 2026-09-10, see §3.2) | 🟢 confirmed live | Job lists in a mid-game fort are hundreds, not millions, of entries; the field itself and its linked-list traversal (`.next`/`.item`) are now verified live against a real running fort, not just standard-but-unconfirmed DF-structures knowledge |

**Build order**: (1) `check_reachable`/`get_connectivity_report` — nearly free, directly copies a working stock script, highest confidence. (2) Landmark system on burrows + `list_landmarks`/`get_landmark`, exits-first representation — cheap, high value, unlocks named-reference for everything else. (3) `get_overview`/Tier 0-1 context assembly with deterministic JSON encoding — needed before any prefix-caching benefit exists. (4) `get_diff_since` via `eventful` — needed before Tier 2 is worth having. (5) `find_open_area` (`terrain="built"`) — the first new algorithm, hard radius cap from day one. (6) `find_chokepoints` — cheap once the landmark graph exists. (7) `rank_candidate_sites` — composes (5) and the §6 formula; this is the item the redirect flagged as most needed, but it's sequenced after the cheaper connectivity/landmark primitives it depends on, not before them. (8) `get_stuck_jobs` — deliberately last among the "core" tools, since the underlying job-list traversal is the least-verified primitive in the whole design. (9) `find_open_area` (`terrain="cavern"`) — last overall, per §2.4/§5.3, the one piece that's genuinely hard.

## 9. Worked example: mid-game fortress briefing

Scenario: ~18 in-game months in, ~55 citizens, a few named rooms, one active problem (a stranded hauler behind a collapsed bridge) and one idle-crafter alert.

```json
{
  "tier0": {
    "fortress": "Bronzemurmur",
    "embark_biome": "temperate broadleaf forest, river",
    "tools_version": "perception-svc/0.2"
  },
  "tier1": {
    "population": 55,
    "landmarks": [
      {"name": "Main Stair", "kind": "custom",
       "exits": []},
      {"name": "Dining Hall", "kind": "room",
       "exits": [{"to": "Main Stair", "direction": "NE", "distance_tiles": 9, "via": "corridor"}]},
      {"name": "Central Stockpile", "kind": "stockpile",
       "exits": [{"to": "Dining Hall", "direction": "S", "distance_tiles": 12, "via": "corridor"},
                 {"to": "Mason Row", "direction": "W", "distance_tiles": 8, "via": "corridor"}]},
      {"name": "Mason Row", "kind": "workshop",
       "exits": [{"to": "Central Stockpile", "direction": "E", "distance_tiles": 8, "via": "corridor"}]},
      {"name": "Trade Depot", "kind": "custom",
       "exits": [{"to": "Main Stair", "direction": "S", "distance_tiles": 28, "via": "surface path"}]},
      {"name": "East Bedrooms", "kind": "room",
       "exits": [{"to": "Dining Hall", "direction": "E", "distance_tiles": 15, "via": "corridor"}]}
    ],
    "resource_summary": {
      "layers": ["limestone", "shale"],
      "ores": ["native copper", "magnetite"],
      "liquids": ["river (surface)", "no magma found"]
    }
  },
  "tier2": {
    "cursor": "evt-04821",
    "in_game_date": "18th Slate, year 253",
    "alerts": [
      {
        "type": "stranded",
        "detail": "1 citizen stranded (group 7, separate from main group)",
        "unit_names": ["Urist Ironbeard, Hauler"],
        "near_landmark": "Trade Depot",
        "direction": "SW", "distance_tiles": 6,
        "likely_cause": "bridge between here and Trade Depot appears retracted or destroyed"
      },
      {
        "type": "idle",
        "detail": "3 citizens idle > 200 ticks",
        "unit_names": ["Zas Goldwhisker", "Ilral Copperfist", "Onul Steelbeard"]
      }
    ],
    "events_since_cursor": [
      {"type": "JOB_COMPLETED", "detail": "Construct Wall x4 completed", "at_tick": 8811},
      {"type": "UNIT_DEATH", "detail": "Stray cat died", "at_tick": 8790}
    ]
  }
}
```

**Token estimate**: the JSON above is ~1,750 characters (the exits-based representation costs a little more than the flat coordinate table the first draft used, because each edge repeats a landmark name — a real implementation should consider a compact adjacency-list encoding, e.g. numeric landmark IDs with a name lookup in Tier 0, if this becomes a meaningful fraction of the budget). Using the common ~4 chars/token heuristic gives **~440 tokens**. This is a rough estimate, not a DeepSeek-tokenizer count — I don't have that tokenizer available locally to verify exactly; treat 420-550 tokens as the realistic band. Compare to a rendered ASCII map of even a modest 80×40 visible viewport: 3,200 characters of map body alone before any legend/coordinates — already comparable to or larger than this entire structured briefing — and the LessWrong and BALROG findings (§1, §2.3) agree that render still gets misread or actively hurts performance. With prefix caching, Tier 0+1 (roughly 1,150 of the 1,750 characters, ~65%) should be a cache hit on every turn where no landmark changed, leaving the ~600-character Tier 2 tail as new tokens most turns — call it **~150 fresh tokens/turn** in steady state, plus whatever on-demand zoom tools the model chooses to call.

## 10. Prototype: structure of the perception-service Lua script

Not executable against a real game in this session (DF is not running) — this establishes the shape and the exact API calls, all verified above, wired together. Save as `hack/scripts/llm-brief.lua` to run via `dfhack-run llm-brief` or the `RunCommand` RPC.

```lua
-- llm-brief.lua
-- Assembles a small, deterministic JSON perception briefing for an LLM agent.
-- All heavy lifting stays server-side; only this script's printed JSON crosses
-- the RPC boundary, per research/2026-08-25-spatial-perception.md.

local json = require('json')

-- deterministic encode: json.encode's own key order isn't guaranteed to be
-- stable across Lua table implementations, so callers relying on prefix
-- caching MUST verify (or force) sorted-key output here before shipping.
local function encode_stable(tbl)
    return json.encode(tbl)  -- TODO: confirm hack/lua/json.lua's key ordering
                              -- behavior against a live instance; sort keys
                              -- manually before encode if it isn't stable.
end

-- ---- direction/distance helper, the MUD/accessibility-derived primitive --
-- (see research doc §2.1/§2.2 for why this, not raw coordinates, is what
-- gets serialized to the model.)
local COMPASS = {"N","NE","E","SE","S","SW","W","NW"}
local function direction_and_distance(from_xy, to_xy)
    local dx, dy = to_xy[1]-from_xy[1], to_xy[2]-from_xy[2]
    local dist = math.floor(math.sqrt(dx*dx+dy*dy) + 0.5)
    local angle = math.atan(dy, dx)  -- Lua 5.3+/DFHack's Lua: atan(y,x) form
    local idx = math.floor(((angle + math.pi) / (2*math.pi)) * 8 + 0.5) % 8 + 1
    return COMPASS[idx], dist
end

-- ---- Tier 1: landmarks -----------------------------------------------
-- Buildings are already-segmented rectangles (verified: Buildings module,
-- Lua API.txt:2338+). Burrows are named, possibly-irregular regions
-- (verified: Burrows module, Lua API.txt:2290+, and burrow.txt's
-- flood-add semantics).
local function raw_landmarks()
    -- returns {name, kind, centroid={x,y,z}} per landmark; centroid stays
    -- server-side, used only to compute exits below, never serialized raw.
    local out = {}
    for _, bld in ipairs(df.global.world.buildings.all) do
        if bld:getName and bld:getName() ~= '' then
            local w, h, cx, cy = dfhack.buildings.getSize(bld)
            table.insert(out, {
                name = dfhack.buildings.getName(bld),
                kind = df.building_type[bld:getType()] or 'unknown',
                centroid = {cx, cy, bld.z},
            })
        end
    end
    -- burrows: df.global.world.burrows.all is the analogous list; each
    -- entry's name via dfhack.burrows.getName, centroid from listBlocks
    -- (average of block coords * 16, left as an exercise here).
    return out
end

local function build_landmark_graph(landmarks, max_edges_per_node)
    -- naive O(n^2) nearest-neighbor edge build; fine for the tens-to-low-
    -- hundreds of landmarks a fortress actually has (see research doc §8).
    for _, a in ipairs(landmarks) do
        local dists = {}
        for _, b in ipairs(landmarks) do
            if a ~= b then
                local dir, dist = direction_and_distance(a.centroid, b.centroid)
                table.insert(dists, {to=b.name, direction=dir, distance_tiles=dist, via='corridor'})
            end
        end
        table.sort(dists, function(x,y) return x.distance_tiles < y.distance_tiles end)
        a.exits = {}
        for i = 1, math.min(max_edges_per_node or 3, #dists) do
            table.insert(a.exits, dists[i])
        end
    end
end

-- ---- Connectivity: near-verbatim port of warn-stranded.lua's core -----
-- (hack/scripts/warn-stranded.lua, getStrandedGroups(), read in full;
-- reused here rather than reinvented.)
local function getWalkGroup(pos)
    local g = dfhack.maps.getWalkableGroup(pos)
    return g ~= 0 and g or nil
end

local function connectivity_report()
    local byGroup = {}
    for _, unit in ipairs(dfhack.units.getCitizens(true)) do
        local pos = xyz2pos(dfhack.units.getPosition(unit))
        local g = getWalkGroup(pos) or 0
        byGroup[g] = byGroup[g] or {}
        table.insert(byGroup[g], dfhack.units.getVisibleName(unit))
    end
    local mainGroup, mainSize = nil, -1
    for g, units in pairs(byGroup) do
        if #units > mainSize then mainGroup, mainSize = g, #units end
    end
    local stranded = {}
    for g, units in pairs(byGroup) do
        if g ~= mainGroup then
            table.insert(stranded, {group_id = g, unit_names = units})
        end
    end
    return stranded, mainGroup
end

-- ---- Tier 2: diff log, drained from an eventful-fed ring buffer -------
if not _G.__llm_brief_events_registered then
    _G.__llm_brief_event_log = {}
    local eventful = require('plugins.eventful')
    eventful.enableEvent(eventful.eventType.JOB_COMPLETED, 30)
    eventful.enableEvent(eventful.eventType.UNIT_DEATH, 30)
    eventful.onJobCompleted.llm_brief = function(job)
        table.insert(_G.__llm_brief_event_log, {
            type = 'JOB_COMPLETED',
            at_tick = dfhack.world.ReadCurrentTick(),
            detail = dfhack.job.getName(job),
        })
    end
    _G.__llm_brief_events_registered = true
end

local function drain_events_since(cursor)
    -- sketch only: array index as cursor. A real implementation should use
    -- a monotonic id, not array index, so entries can be trimmed without
    -- invalidating outstanding cursors.
    local log = _G.__llm_brief_event_log
    local events = {}
    for i = (cursor or 0) + 1, #log do
        table.insert(events, log[i])
    end
    return events, #log
end

-- ---- Assemble and print ------------------------------------------------
local args = {...}
local since_cursor = tonumber(args[1]) or 0

local landmarks = raw_landmarks()
build_landmark_graph(landmarks, 3)
for _, l in ipairs(landmarks) do l.centroid = nil end  -- strip before serializing

local stranded, main_group = connectivity_report()
local events, new_cursor = drain_events_since(since_cursor)

local briefing = {
    tier1 = {
        population = #dfhack.units.getCitizens(true),
        landmarks = landmarks,
    },
    tier2 = {
        cursor = tostring(new_cursor),
        in_game_date = ('year %d, tick %d'):format(
            dfhack.world.ReadCurrentYear(), dfhack.world.ReadCurrentTick()),
        alerts = stranded,
        events_since_cursor = events,
    },
}

print(encode_stable(briefing))
```

Notes on the sketch, honestly: `df.global.world.buildings.all`/`burrows.all` field names and `bld:getName()`/`bld.x1/y1/z` are standard DF-structures idioms consistent with how `dfhack.buildings.*` wrappers are documented to operate, but I have not independently confirmed those exact raw-struct field names against a local source the way I did for `getWalkableGroup` or `warn-stranded.lua`'s pattern — this script needs a run against a live DF instance before trusting the field names verbatim. Everything routed through the documented `dfhack.*` wrapper functions (getSize, getCitizens, getPosition, getVisibleName, getWalkableGroup, getName, ReadCurrentTick/Year) is higher-confidence since those signatures come straight from Lua API.txt. The naive O(n²) nearest-neighbor edge builder is a placeholder — it will produce geometrically-nearest edges, not necessarily *walkably*-nearest ones (a landmark on the other side of a wall could show up as a close "exit" it isn't actually possible to use); a real version should filter candidate edges by `canWalkBetween` before ranking by distance.

## 11. What this can't do — honest limitations

- **No verified river/water-body geometry primitive.** `RiverTile`/`RiverEdge` exist as message names (DLL-verified) but field layout is unconfirmed. Fallback: `prospect --show liquids` (coarser, confirmed-real) or a bespoke scan of `MapBlock.water`/`water_stagnant`/`water_salt`.
- **`getWalkableGroup` staleness while paused, and blindness to climbing/flying/burrow restrictions/invader presence** (documented caveats, §3.2). "Reachable" is DF's-pathfinder-reachable, not "safe."
- **No automatic room *type* inference.** Nothing tells you a rectangle is "the dining hall" — that's the model's decision via `create_landmark`. Landmark quality is only as good as the model's naming discipline; a room renamed in-fiction but not re-tagged will silently mislead future turns.
- **`get_stuck_jobs`'s core traversal is the one primitive in this whole design with no working local example to point to.** Build and test it in isolation first. **Partially resolved 2026-09-10**: the underlying field (`df.global.world.jobs.list`, not `df.global.job_list` as guessed here) is now confirmed live, traversal included — see §3.2/§8's corrections. `get_stuck_jobs` itself (the `min_idle_ticks` filter over that list) is still unbuilt.
- **Multi-z-level adjacency (stairs/ramps connecting landmarks on different floors)** is handled by `getWalkableGroup` for reachability (3D-aware) but the naive nearest-neighbor edge builder in §10 is inherently per-z-level in spirit; two rooms stacked on different floors and linked by a stairwell need an explicit z-transition rule (treat a stairwell/ramp landmark as bridging whichever landmarks touch it above and below), not designed in detail here.
- **Everything RFR-related (§3.1 field lists) rests on a single fetched source, unconfirmed against a second one.** High confidence on RPC/message *names* (independently pulled from the installed DLL); moderate confidence on exact field lists.
- **The `find_chokepoints` and `rank_candidate_sites` algorithms (§5.3, §6) are original synthesis from cross-domain prior art, not ports of any cited system's actual code**, and have zero track record on DF specifically. BWTA (§2.5) is validated on StarCraft maps against human map-readers; the scoring formula in §6 is validated nowhere — it's a reasonable starting structure, explicitly flagged in §6 as needing tuning against real play, not a result.
- **Action-tool failure feedback (the NetHack wall-bump lesson, §2.2) is a requirement this document states but doesn't design.** `designate_dig`'s `failure_reason` field is sketched as a schema note in §5, not a specification of every failure mode an action layer needs to surface.
- **The `terrain="cavern"` open-area finder (§5.3) is the least-developed piece of the whole tool set** — a real distance-transform/watershed or graph-community-detection implementation is nontrivial engineering, deliberately sequenced last (§8), and the sketch in §5.3 is a description of the right family of technique, not a design.

## Sources (cross-domain prior art, §2)

- LessWrong, "Dwarf Fortress and Claude's ASCII Art Blindness" (cited in the original task prompt; not re-fetched in this pass).
- Raph Koster, "A Spatial Representation of the Virtual World" — https://www.raphkoster.com/games/insubstantial-pageants/a-spatial-representation/
- "Wilderness Systems for Muds," Alex Kallend — http://tharsis-gate.org/articles/imaginary/WILDER~1.HTM
- Accessibility suggestions for screen reader users (itch.io community thread) — https://itch.io/t/3031776/accessibility-suggestions-for-screen-reader-users
- "Uncovering Visually Impaired Gamers' Preferences for Spatial Awareness Tools Within Video Games" — https://ar5iv.labs.arxiv.org/html/2208.14573
- "Developing Open-Source Roguelike Games for Visually-Impaired Players by Using Low-Complexity NLP Techniques" — https://www.researchgate.net/publication/343763872
- Roguelike Radio, Episode 48: "Designing for the Visually Impaired" — http://www.roguelikeradio.com/2012/10/episode-48-designing-for-visually.html
- BALROG: Benchmarking Agentic LLM and VLM Reasoning On Games — https://arxiv.org/abs/2411.13543
- The NetHack Learning Environment — https://arxiv.org/pdf/2006.13760
- "A NetHack Learning Environment Language Wrapper for Autonomous Agents" — https://www.researchgate.net/publication/371559869
- Voyager: An Open-Ended Embodied Agent with Large Language Models — https://arxiv.org/abs/2305.16291
- AriGraph: Learning Knowledge Graph World Models with Episodic Memory for LLM Agents — https://arxiv.org/abs/2407.04363
- Hydra: A Real-time Spatial Perception System for 3D Scene Graph Construction and Optimization — https://arxiv.org/abs/2201.13360
- Terrain Analysis in Real-Time Strategy Games: An Integrated Approach to Choke Point Detection and Region Decomposition (BWTA) — https://ojs.aaai.org/index.php/AIIDE/article/view/12405
- Improving Terrain Analysis and Applications to RTS Game AI (BWTA2) — https://ojs.aaai.org/index.php/AIIDE/article/download/12889/12737/16406
- Space syntax / isovist analysis overview — https://spatialanalysisonline.com/HTML/isovist_analysis_and_space_syn.htm ; https://isovists.org/2021/04/15/grid-free-integration/
- Exploring Minecraft Settlement Generators with Generative Shift Analysis — https://arxiv.org/abs/2309.05371
- Next-Best-View problem overview — https://www.emergentmind.com/topics/next-best-view-problem
- Near-optimal Hierarchical Path-finding (HPA*) — https://www.researchgate.net/publication/228785110
