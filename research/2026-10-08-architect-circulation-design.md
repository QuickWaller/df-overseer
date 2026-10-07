# The Architect as blueprint designer, and circulation as a first-class thing

Date: 2026-10-08. Design only, read-only research. No VM touched, no fort
read, no code changed. Brief: the user's direction of 2026-10-08 (register
row "Zoning stays in the Planner; the Architect becomes the blueprint and
placement designer; circulation ... is designed now"), plus two scope
additions from the coordinator the same day: make a failure-mode analysis
the spine of the design (section 2), and give walkways, workshop placement,
dynamically sized workshop rooms, hallway widths, multi-level blueprints and
a pre-dig pathfinder their own sections with a recommendation each.

Provenance tags used throughout:

- **[verified]** read this session in repo code, data, a register row, an
  installed-source research file that quotes file:line, or a fetched
  current-version (v53.16-banner) wiki page.
- **[prior]** a current wiki page or practitioner source, read this session,
  describing game behaviour this project has not measured on its own fort.
- **[inferred]** follows from verified facts; nobody has watched it happen.
- **[proposed]** this design's own choice.
- **[unverified]** a claim I could not check, with the reason.

No coordinate, grid or map of this fort appears below. Small generic shapes
are described in words only (`docs/PURPOSE.md` commitment 1).

---

## 0. The answer, up front

1. **The Architect stops drawing rooms one at a time and starts designing
   a circulation network with rooms hung on it.** Its products are (a)
   template variants, authored as *parameters to code generators*, never as
   hand-drawn grids, and (b) exact placements, named by handles and anchors
   the server issued. Stockpile siting leaves it for Logistics (already
   decided in the Planner design, stage L). Districts and closeness stay
   with the Planner. **Room access rules per kind move to the Architect**
   as template-kind data, since they are circulation design; the Planner
   keeps only per-district overrides (section 1, decision D2).

2. **Prevention is by code, at three gates, not by charter prose.** Every
   room or corridor proposal is checked against a *planned-tile model*
   (today's visible tiles plus every reserved, accepted and proposed dig and
   construction) by a code pathfinder and a circulation-graph checker:
   at **template adoption** (linter plus a synthetic-terrain simulation), at
   **filing** (dry run against the planned model: access rule, private
   pass-through, stranding, sealing, stair alignment, reservation overlap)
   and at **execution** (re-checked against the live tiles, then read back).
   The FMEA in section 2 lists 92 failure modes; 47 have a control that
   prevents them by construction, 33 rely on a filing or execution guard,
   12 can only be detected and recovered. Every Architect-relevant
   incident found (25 by this pass, plus the 59-entry parallel failure
   catalogue) maps to a row or is named out of scope (2.4), and each
   problem the user caught by eye becomes a code check (2.5).

3. **The model reasons over a graph in words, built by code.** Nodes are
   rooms, junctions, stair landings and portals; edges are corridor
   segments with width class, length in walk tiles, level change, door and
   traffic. The model sees "Bedroom row B: 6 rooms, each opens onto
   Corridor 4 (2 wide); 14 walk-tiles to Dining Hall; no room reached
   through another", never a tile. The checks are code and return verdicts,
   not facts to combine (`research/2026-09-25-district-layout-prior-art.md`
   Q5: models compose relations poorly).

4. **Corridors are routed by code and built from generated segments.** The
   Architect requests a corridor by its ends (two handles or landmarks), a
   width class and a door policy. A code router (A* over the planned-tile
   model, with turn and dig-cost penalties) returns a path; a generator
   turns it into quickfort segments (straight runs, junctions, a stair
   landing) with seams and traffic designations. Fixed corridor templates
   tiled by the model were rejected: the model would have to choose and
   count tiles, which is coordinate reasoning by another name.

5. **Walkways, workshop bays, hallway widths and stairwells are each a
   parametric generator** with a validated output, not a fixed CSV library.
   A workshop bay is generated from (workshop kinds, Logistics' pile_spec,
   corridor side, door policy); a bedroom row from (count, door, side);
   a stairwell from (levels, landings). One fixed library survives for
   one-off rooms (office).

6. **A pre-dig pathfinder is the keystone tool.** It predicts path
   existence and walk length for planned routes before a tile is dug, and
   is validated after building against `dfhack.maps.getWalkableGroup` (for
   existence) and against the game's own computed unit paths (for length).
   The model gets numbers and named endpoints only.

7. **Build order: seven stages, C0 to C6**, each live-checkable, starting
   with the read-only circulation graph and the bedroom block's diagnosis,
   and ending with the bedroom retrofit and workshop bays (section 12).
   Thirteen decisions for the user are in section 14, one per line, each with
   a recommendation.

---

## 1. The Architect's redefined charter

### 1.1 One sentence

**The Architect designs how the fort is shaped and moved through: it
authors and revises template variants, routes circulation, and places each
room and corridor exactly, inside the Planner's districts, one ruled step at
a time.**

### 1.2 Owns, does not own, moves

| Concern | Today | After this design | Why |
|---|---|---|---|
| Room siting and phases | Architect [verified, `agents/architect/role.md`] | Architect, now via a circulation-attached site (section 5) | unchanged ownership, new mechanism |
| Template library | humans and executors write `blueprints/templates/` [verified] | **Architect authors variants of code generators**; humans write generators | user's direction 2026-10-08 |
| Corridors, stairs, walkways | Architect (`corridor` type exists, `ARCHITECT_TYPES` [verified, `dfqueue/schema.py:355`]), no corridor tool | Architect, with a router and generators | user's direction |
| Doors (where, whether) | `construction.door` exists, Overseer-only, never run live [verified, TOOLS.yaml `door ZONE_ID`] | **door policy is template/variant data the Architect sets**; the conductor executes | doors are circulation design |
| Room access per kind (opens onto corridor, a named kind, any) | Planner owns policy (Planner design §1 table) [verified]; register 2026-10-06 says "template data" [verified] | **Architect, as per-kind data with a recorded ground**; Planner may override per district | resolves a doc disagreement, decision D2 |
| Traffic designations | nobody; 0 of 6,856,704 tiles non-Normal on this fort [verified, `research/2026-09-23-flood-relevance-and-traffic.md` §2] | Architect, emitted by the corridor generator only | tied to corridor class |
| Stockpile siting | Architect (`stockpile_siting` in `ARCHITECT_TYPES`) | **Logistics** (Planner design stage L) [verified as decided] | already decided |
| Districts, closeness, targets | Planner | Planner | user, 2026-10-08 |
| Sealing for defence, burrows, lockdown | Overseer (role.md "Does NOT own") | Overseer; the Architect only guarantees every district boundary has a door-able throat (section 3.5) | military stays out |
| Execution | conductor, routed `rooms` group [verified, `dfqueue/action_tools.yaml`] | conductor, `rooms` group gains corridor and door tools | unchanged |

### 1.3 What "authoring a template" means

**Recommendation: the model authors parameters, never grids** (decision
D1). A template becomes two layers:

- **A generator** (code, in the repo, human-reviewed, tested): `room-cell`,
  `room-row`, `corridor-run`, `junction`, `stair-column`, `workshop-bay`,
  `dormitory`. A generator takes typed parameters and emits a quickfort CSV
  plus the YAML contract the existing library already uses (footprint,
  edges with roles, entrance, walls intent, phases, provides, requires).
- **A variant** (data, authored by the Architect through a proposal):
  a named, versioned parameter set, for example `bedroom-row` variant
  "row-6-door-south": generator `room-row`, cell kind bedroom, interior 3 by
  3, count 6, door yes with ground `user_standard`, entrance side toward the
  corridor, corridor width class 2. Variants live in `dfqueue` as a new
  record kind `template_variant`, append-only like `fort_plan`.

Why not let the model draw a small CSV: commitment 1 permits small generic
patterns, but the failure catalogue below shows that every geometry defect
this project has shipped was an off-by-one, an orientation or a missing
phase (FMEA T-1 to T-8). A model writing a grid repeats those defects with
less chance of a test catching them. Parameters are checkable by schema; a
generator's correctness is checked once, by tests, for every variant it
will ever emit. This is "tools must be generalisable" applied to templates:
the next bedroom size, workshop kind or row length is one data entry.

The fixed files that exist (`bedroom-cell-v1`, `office-room-v1`,
`office-room-v2`) stay as **legacy fixed templates**, readable and
applicable, and become regression fixtures: the `room-cell` generator must
reproduce `bedroom-cell-v1.csv` and `office-room-v2.csv` byte for byte
(after normalising notes) from the right parameters. That is the
generator's first test.

### 1.4 How a new or changed variant is validated before use

A `template_variant` proposal passes five gates, all code, in order. A
failure at any gate refuses the filing and names every problem at once
(the existing `queue.propose` refusal shape).

| Gate | What it checks | How | Catches |
|---|---|---|---|
| V1 schema | parameter types, ranges (interior 1 to 11 per side, count 1 to 20, width class 1 to 3), closed vocabularies (room kind from `zone.list-kinds`, workshop kind from `building.list-kinds`, door ground from a closed list) | JSON schema in `dfqueue` | typos, invented kinds |
| V2 generate | the generator runs and emits CSV plus YAML | the generator itself, deterministic | impossible combinations |
| V3 lint | footprint matches YAML; every interior tile is dug; every wall-ring tile has `finished` intent; exactly the declared entrances are gaps; doors only on gap tiles orthogonally adjacent to wall [verified rule, `build.lua` `is_tile_generic_and_wall_adjacent`, quoted in `research/2026-09-24-quickfort-hands.md` §3]; zone rectangle contains every value-bearing furniture tile (register rule 1, the Chair incident); furniture never on an entrance or door tile; phases ordered dig, smooth, floor-smooth, build, zone; seam edges marked consistently; no digit pair, no landmark or unit name, no fort token in any text field | a Python linter over the generated CSV and YAML | T-1 to T-8 |
| V4 simulate | on a synthetic block of solid rock with a 1-wide test corridor along the declared entrance side: every interior tile reachable from the corridor after all phases; no furniture blocks the only path; tiled copies (for row/seam generators: 1, 2 and the max count) produce N-1 shared seams and no doubled wall; rotated copies (all four quickfort transforms) keep the entrance on the corridor side | the planned-tile pathfinder (section 8) on synthetic terrain | seam, orientation, blocking |
| V5 first use | the first real application of a variant is a normal ruled room proposal; its status moves `designed` to `applied-live` when the conductor's step lands, and to `verified-live` when the post-build checks (section 4.4) pass | existing step and status machinery | everything the synthetic world cannot show |

The status ladder is the README's own (`designed`, `applied-live`,
`verified-live`) [verified, `blueprints/README.md`], now driven by code
instead of by an executor's report.

**Who rules a variant.** The Overseer, like any proposal, with one
recommended extra: a variant that introduces a *new generator parameter
value never used before* (a first door ground, a first width class) shows
on the Board for the user once (decision D3). Variants that only change a
count or a side do not.

### 1.5 Exact placement

Placement stays one step per proposal, by handle. What changes is what a
site can be named by:

- today: a landmark name plus RANK (the Nth candidate near it) or a
  `site-N` / `res-N` handle [verified, TOOLS.yaml `preview`];
- added: a **portal handle** `portal-N`, a code-issued attachment point on
  a planned or built corridor ("Corridor 4, north side, 3rd free portal"),
  and a **junction handle** `junc-N`. Rooms are placed *at a portal*, so
  their entrance opens onto circulation by construction (FMEA A-1).

The model chooses which portal; code computes where it is. No offset, no
coordinate, no tile count from the model.

---

## 2. Failure-mode analysis (the spine)

### 2.1 How to read this

Structured like an FMEA (failure mode and effects analysis, the
reliability-engineering method of listing each way a component can fail,
its effect, how it is detected, and the controls that prevent it). Columns:

- **Mode**: the concrete failure.
- **Effect**: what goes wrong in the fort.
- **Detect**: the read or check that sees it.
- **Prevent**: the guard. `C` = prevented **by construction** (the bad
  state cannot be expressed or generated). `F` = refused **at filing** by a
  code check against the planned-tile model. `X` = refused **at execution**
  by the tool against live tiles. `K` = charter text only (used only where
  no code check is possible, and flagged).
- **Recover**: what happens if it occurs anyway.
- **Inc**: a real incident from this project's history (section 2.3), or
  `-` if none yet.
- **Now**: `exists` (in code today), `partial`, or `new` (this design).

Severity is not scored numerically: this project has no failure-rate data
to multiply, and an invented RPN would be the "number dressed as
measurement" the SLP literature warns against
(`research/2026-09-25-district-layout-prior-art.md` Q1). Instead each class
is ordered most-severe first, judged by reversibility (a death or a sealed
dwarf before a rough floor).

### 2.2 The table

**G. Geometry and siting**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| G-1 | Anchor offset: tool applies at centre where quickfort expects top-left | room dug beside the validated box, possibly unreachable | read back designated tiles vs the planned set | C: one shared anchor function, tested against quickfort's top-left rule; every apply reads back its designations | `release`, re-apply | I1 | partial (fixed in two tools) |
| G-2 | Rotation lands the blueprint up-left of the cursor (quickfort rotates about `-c`) | wrong place, overlaps | same read-back | C: transform math in one place, all four rotations in V4 | release | - (found in source, `quickfort-hands` §9) | partial |
| G-3 | Footprint overlaps another room's interior | doubled dig, broken room | reservation check | X: reservations refuse interior overlap [verified, register 2026-09-30]; F: planned model includes accepted and pending proposals, not only reservations | unreserve | - | partial (F is new) |
| G-4 | Site chosen by straight-line distance, poor for its purpose | long walks, burned good space (the coffin) | path length in the circulation graph | F: siting ranks by planned walk length to the district anchor and the declared partners, not by `ranked_rects` straight-line distance | relocate before dig; after dig, accept with a note | I9 | new |
| G-5 | Room straddles soil and stone: ring cannot be finished | rough or unfinished walls | `preview` `finish_plan` and `remedy` [verified, TOOLS.yaml] | F: refuse a variant/site whose ring has standing soil unless the variant's finish allows `dig-then-construct`; X: verb reports soil tiles | two-step finish (dig, wait, `Cw`) | I10 | partial |
| G-6 | Site on hidden tiles that turn out to be open (cavern, chasm) | dig into a cavern, invaders | after-dig reveal; breach detector | none by construction (sensing hidden is banned, register 2026-09-16); F: report "assumes N hidden tiles" as risk | wall off with `Cw`, door | - | new (risk line) |
| G-7 | Two placements in one cycle both pass alone, conflict together | overlap, one stranded | planned model includes the earlier proposal | F: proposals are checked against all pending proposals, not only the live map | refuse the second | - | new |
| G-8 | Zone or room sited onto liquid or the wrong side of a feature (water tiles offered for a Water Source zone; dwarves standing in deep water) | drowning risk, unusable zone | planned model liquid depth | F: siting refuses liquid tiles for kinds whose rule says `beside: water`, and resolves the shore tile (including the level above a sunken pool) | re-site | catalogue (2026-09-17, 10-07) | new |

**A. Access and circulation**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| A-1 | Room's entrance opens into another room's interior | private pass-through (up to 5 bedrooms crossed) | circulation graph: entrance edge's other side is a room node | C: rooms are placed at portals on circulation; F: access rule per kind checked on the planned graph | retrofit corridor (section 6.4) | I11 | new |
| A-2 | A room reachable only through a room of a kind its rule forbids | same, deeper | graph: every shortest path from the fort's hub to room R passes through a private node | F: the "no private pass-through" invariant on the planned graph | retrofit | I11 | new |
| A-3 | Corridor dead-ends with many rooms behind one throat | everyone stranded if blocked; long walks | graph articulation points and bridges; dead-end depth | F (metric, flagged not refused): report; refused only above a hard cap (decision D7) | add a loop link | - | new |
| A-4 | Width too small for traffic | queuing at a spine | segment width vs served-load estimate | F: generator picks width from load class; metric flag on legacy segments | widen (dig the side run) | - | new |
| A-5 | Furniture or a workshop's blocking tile on the only path | room unreachable after build | pathfinder over the planned model with building occupancy | C: generator never places furniture on portals, entrances, door tiles or the 1-tile approach; F: blocking-tile check per building kind from the game's own building size data | deconstruct | - | new |
| A-6 | Stockpile laid across a corridor | haul congestion, items in the way | pile footprint vs circulation tiles | X (Logistics' `stockpile.place` must refuse circulation tiles once corridors are reserved); C: corridors are reserved | remove pile | - | new |
| A-7 | Long walk from bedrooms to dining or the well | wasted time, thirst | graph walk-length metric | F metric: reported per room at filing; threshold only as a flag (no source gives a number, `room-layout` Q3) | add a link or a second hub | - | new |
| A-8 | Entrance reachable only once an undug hallway is finished, refused as stranded | valid tiled plans refused | access gate | F: plan-aware gate: an entrance touching a *planned and accepted* corridor counts as reachable if the corridor is startable (register 2026-09-24, the user's point) | n/a | I4 | new |
| A-9 | A check proves an adjacent property: a walkable tile beside the footprint, not reachability from the fort's hub | room placed in a pocket the fort cannot reach | graph reachability from the hub node | C: every siting check is "reachable from the hub on the planned graph", never "a walkable neighbour exists" | connector corridor | catalogue (`building find`, 2026-09-21) | new |

**V. Vertical and stairs**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| V-1 | Up and down stairs misaligned | levels not connected | planned model: vertical edge requires up-capable below a down-capable [prior, wiki Staircase] | C: `stair-column` generator emits `j` top, `i` middle, `u` bottom in one column | dig the missing piece | - | new |
| V-2 | `i` dug on an already-open floor becomes a down stair only [verified, register 2026-09-17] | no way up | generator per-tile rule table; read back tiletype | C: generator picks the symbol from the tile's current shape; an up stair into an open tile needs a *constructed* stair (material) | construct a stair | I2 | new |
| V-3 | Stair tile has a building on it: quickfort skips silently and reports success [verified, register 2026-09-17] | no stair, tool says ok | read back designations, compare to requested | X: occupancy check before apply; read back after; `ok` alone never trusted | clear building, redo | I2 | partial |
| V-4 | One stairwell is the fort's only vertical link | whole fort cut by one blockage; congestion | graph: vertical bridges | F metric: flag; Planner may want a second shaft per N alive (decision D8) | second stair column | - | new (chokepoints only flags stairs, unproven as sole connector) |
| V-5 | Ramp read as walkable at its top tile | false unreachable | tri-state reachability "adjacent" [verified, live 2026-09-23] | C: pathfinder implements ramp rules, validated against the tri-state helper | n/a | - (the Well ramp false negative) | exists for reads |
| V-6 | A floor dug below a down stair without a matching up stair: never becomes a job, or never connects | lower level unreachable | read back; graph vertical edges | C: `stair-column` always emits the pair | dig the stair | catalogue (2026-09-10) | new |
| V-7 | Down stair on a grass floor designates 0 tiles with no error (mechanism never found in source) | no stair | read back counts | none by construction (cause unknown); X: refuse a stair step whose read-back count is 0, report the surface material | choose a non-grass tile | catalogue (2026-09-10) | new (detect only) |

**D. Digging order and stranding**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| D-1 | Dig designated with no walkable start | jobs never created; site stalled | `status` `dig.state: stalled` after 600 ticks [verified] | X: `entrance_reachable` refusal unless `ALLOW_STRANDED` [verified live preview-side]; F: plan-aware chain check (A-8) | `release` | I3 | exists (apply side unproven live) |
| D-2 | A dig cuts the only path to a working area while in progress | dwarves stuck behind | pathfinder on the planned model per phase | F: each phase is checked for "every currently reachable named place stays reachable during and after" | stop, re-route | - | new |
| D-3 | Hallway and rooms applied out of order | rooms stall | step dependency | C: the corridor project's step `requires` precedes its rooms' (job dependency graph, `research/2026-09-28-job-dependency-graph.md` §0) | reorder | I4 | partial (projects exist) |
| D-4 | Blind designations on hidden tiles linger | half-dug pockets | `status` hidden counts [verified] | K + X: allowed (acting on hidden is fine, register 2026-09-16), but `release` after grace | release | I3 | exists |

**S. Sealing in items, dwarves or ore**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| S-1 | A wall or door closure seals a room's last entrance | dwarves or items trapped, starvation | `construction.audit` [verified, TOOLS.yaml: checks a wall that would seal an activity zone's last entrance] | X: audit at designation; F: the seal check on the planned graph for every `Cw` and every door set to locked | suspend the job, deconstruct | - | partial |
| S-2 | A constructed wall seals exposed ore | ore lost to the forge | `surface.vein-material`, `blueprint.sites` `ore_exposed` [verified] | X: "keep exposed ore reachable" guard evaluated over all of a step's constructions jointly (job graph §3) | deconstruct, mine | I7 | partial |
| S-3 | Smoothing over an ore vein in a ring | ore hidden in a smooth wall | `vein-material` (names the mineral) | C: finish phase waits while `ore_exposed` non-empty [verified, role.md] → make it X: `apply _finish` refused while exposed ore remains | mine later (smoothing does not destroy it) | I6 | partial (charter only; to X) |
| S-4 | Retrofit closes an old opening before the new entrance exists | room sealed with its occupant | planned model ordering | C: retrofit generator emits "open new, then close old" as two steps with `requires` | reopen | - | new |
| S-5 | A unit standing in a tile being walled | job cancels or unit trapped | game cancels construction when occupied [inferred] | X: unit occupancy check before closure steps | retry | - | new |
| S-6 | A wall-the-ring step treats every open ring tile as "mined, needs a wall", including the doorway | room walled shut | code read | C: wall targets come from the template's own edges (entrance tiles excluded), never inferred from "is open" | deconstruct | catalogue (2026-09-28 code read; 2026-10-01 office sealed during build) | new |
| S-7 | A hand-held construction (wall beside ore) released by `suspendmanager` or an unsuspend | ore sealed after all | suspension reason read | X: guard holds are recorded with a reason the conductor re-asserts on reconcile; no unsuspend of a held job | deconstruct | catalogue (2026-09-28) | new |

**W. Water, magma, cave-in**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| W-1 | Dig breaches water or magma | flood, deaths | breach detector (flags `update_liquid` at the working face, `flood-relevance` §1 [verified]) | F: refuse digs adjacent to *visible* liquid or known aquifer layers; hidden is unknowable by rule | door or floodgate at a throat; wall | - | partial |
| W-2 | No closable throat between a risky dig and the fort | flood spreads freely | graph: is there a door-able 1 to 2 wide segment between the dig face and living districts | F metric: corridor generator leaves a door-ready throat at each district boundary (3.5) | build door there | - | new |
| W-3 | Item on a door tile props it open | fluid passes a closed door [prior, wiki Door, `room-layout` Q4] | read items on door tiles | X: door tiles marked `on`, no pile overlap; periodic read | dump items | - | new |
| W-4 | Removing support causes a cave-in | collapse, deaths | DF's support rule [unverified for this design: not read] | F: refuse a dig that leaves an unsupported construction or floor island (needs a support read, missing) | none good | - | new, research owed |
| W-5 | Channelling or ramps open a level to the one below | falls, flooding paths | planned model | C: generators never emit channels; corridor generator never emits `h` | construct floor | - | new |

**M. Materials and buildingplan**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| M-1 | Furniture placed with no item to build it; suspended forever | room never finished; WIP held | `stuckjobs`, `building` stage 0 with no item | F: a finish phase cites stock or an open order for each `requires` item; the Planner's derived inputs wake the Quartermaster (Planner design 2.2, F-1) | queue the item | I12 | partial |
| M-2 | `Cw` or door with buildingplan disabled disappears without material | wall silently missing | read back buildings | X: verb checks buildingplan state; F: material availability cited | re-place | - | new |
| M-3 | Constructed stair or wall needs blocks the fort lacks | stalled | stock read | F: material count for the step's constructions vs `stocks.availability` | order blocks | - | new |
| M-4 | Door kind or material unspecified, buildingplan picks a poor one | value, not function | n/a | K: acceptable (`construction.door` leaves material to buildingplan by design) | swap later | - | exists |
| M-5 | A long-suspended construction lacking material is unsuspended and DF deletes the building | building lost | building vanishes | X: no unsuspend for a construction whose item is missing; the step reports "needs item" instead | re-place | catalogue (2026-09-19, the Still) | new |
| M-6 | One scarce tool (a single pick) throttles every dig | digs stall for thousands of ticks | dig stalls with no claimed worker | F: a dig step cites picks and enabled miners (`labor.enabled-counts`, stocks); refuses more parallel dig steps than diggers | order picks | catalogue (2026-09-24) | new |

**R. Reservation and concurrency**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| R-1 | Two roles designate the same tiles | corrupted work | reservations | X: every designating tool refuses another's reservation [verified]; C: single writer (conductor) [verified register 2026-09-12] | unreserve | - | exists |
| R-2 | Corridor tiles unreserved, a pile or workshop lands on them | blocked circulation | planned graph | C: corridors are reserved as kind `circulation`; allowed kinds: door, traffic, nothing else | remove intruder | - | new |
| R-3 | Dry run mutates persistent state | phantom records | tests | C: dry runs write nothing [verified fixed, register 2026-09-30] | n/a | I24 | exists |
| R-4 | Tick arithmetic resets at New Year | ages wrong, false stalls | tests | C: absolute ticks [verified fixed] | n/a | I25 | exists |
| R-5 | Duplicate room proposals for the same need | double rooms or churn | `dfqueue/step_identity.yaml` action match, live since 2026-10-07 [verified: file read; it lists `blueprint.apply` by site and phase, but **not** `blueprint.reserve`, so two reserves at different ranks for one need are not caught] | F: exists for identical actions; add `blueprint.reserve` by `portal-N`, and count a target's in-flight rooms by `serves` (Planner F-6) for the same-need case | refuse | I13 | partial |
| R-6 | A reservation handle permits a build on the reservation but does not place it exactly on the reserved footprint | room drifts off its reserved ground | read back footprint vs reservation | C: a `res-N` or `portal-N` handle resolves to its exact footprint; the step has no site search when a handle is given | release, re-apply | catalogue (2026-09-30 red team) | new |

**T. Template authoring and seams**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| T-1 | Missing phase (floor smoothing) | rough floor | V3 lint: every dug interior tile has a floor-finish intent | C: generators emit all phases | add phase | I5 | new |
| T-2 | Zone rectangle excludes value furniture | room value 0 / not counted | V3 lint; `zone.contents` live | C: generator derives the zone from the interior | re-zone | I8 | partial (live read exists) |
| T-3 | Door not adjacent to a wall | door refused | V3 lint (quickfort rule) | C | n/a | - | new |
| T-4 | Seam wall designated twice or not at all | doubled wall or hole | V4 tiled simulation | C: row generator owns seams; reservation allows wall overlap only on seam tiles [verified] | Cw the hole | - | partial |
| T-5 | Furniture before smoothing | unsmoothable walls | V3 phase order | C | deconstruct, smooth | - | exists in templates |
| T-6 | Template carries a fort coordinate or name | commitment 1 broken, leaks | V3 grep-like lint | C: variants are parameters; lint on text fields | reject | - | new (human check today) |
| T-7 | YAML contract and CSV disagree | wrong signals, wrong `provides` | V3 | C: one generator emits both | regenerate | - | new |
| T-8 | Entrance edge declared but gap missing, or extra gap | sealed room or pass-through | V3 + V4 | C | Cw / dig | - | new |

**B. Retrofit of built rooms**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| B-1 | Retrofit corridor digs through a built room's furniture or zone | broken room | planned model with buildings and zones | F: route cost infinite through room interiors | n/a | - | new |
| B-2 | New wall on an old opening has an item or unit on it | job cancels | X: occupancy | X | retry | - | new |
| B-3 | Retrofit of a legacy room with no site handle | untracked | `blueprint.sites` | C: legacy rooms are claimed into the graph by a one-time code pass (sites, zones) before retrofit | n/a | - | new |
| B-4 | Retrofit changes a room the Planner's district binding covers | plan drift | binding table (Planner F-10) | F: a retrofit that moves an entrance is a physical change only; it does not change the binding; refused only if it removes the room | n/a | - | new |

**P. Perception errors (a read lies)**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| P-1 | quickfort returns success while skipping tiles | believed done | read back per tile | C: never trust `ok`; read-back counts in every apply result | redo | I2 | partial |
| P-2 | Null read as zero (or zero as null) | false "done" | tests | C: tri-state everywhere [verified pattern] | n/a | I18 | exists |
| P-3 | A proxy says a room is invalid when it is fine | churn, rebuilding | cross-check with the game's own text | C: verdicts carry `cannot_tell` [verified] | n/a | I19 | exists |
| P-4 | Landmark distance is straight-line x/y, ignores levels; only 3 nearest exits | wrong closeness facts | Planner red team F-23 [verified] | C: graph walk length replaces landmark distance for every circulation fact | n/a | I15 | new |
| P-5 | Hidden tiles counted as known | armok leak, wrong plans | knowledge-scope audit | C: planned model marks hidden as `unknown`, never ore or open [verified rule] | n/a | I20 | exists in tools |
| P-6 | Pathfinder disagrees with the game | false confidence | post-build validation (section 8.5) | C: every prediction is checked against walkable groups after build; drift raises a gotcha | fix the simulator | - | new |
| P-7 | Perception scan too large hangs DF | fort frozen, kill-lua fails [verified, register 2026-09-12] | timing | C: bounded window, tile cap, chunked reads, no per-tile closures | restart DF | I17 | new constraint |
| P-8 | `#meta` swallows a failing section with a printerr only; a building on a tile silently drops `s`/`d` | phase believed applied | per-section read back | C: the verb applies sections one by one and reads each back; a section with zero effect is a failure | redo | catalogue (2026-09-24) | new |
| P-9 | A liquid read that does not distinguish water from magma (the magma sea counted as water) | wrong flood or water reasoning | explicit liquid type read | C: the planned model stores liquid type and depth separately | n/a | catalogue (2026-09-16/18) | new |
| P-10 | Offline fakes model the wrong DFHack fields, so tests pass and the live run crashes or reads wrong | a guard that never fires live | live negative control | none by construction; each stage's live check includes one deliberately refused case (process rule, the 2026-09-24 lesson) | fix fixture from a live capture | catalogue (2026-09-14 to 09-28) | process |

**L. Model errors**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| L-1 | Model writes a coordinate | commitment 1 broken | schema | C: no field accepts one; refused [verified] | n/a | - | exists |
| L-2 | Model names a landmark that does not exist or is ambiguous | wrong site | server resolves names; duplicates refused | F: every name resolved at filing; ambiguous names refused naming the candidates; handles preferred | n/a | I15 | partial |
| L-3 | Landmark name with an apostrophe cannot be passed | tool unusable for that place | live | C: handles (`junc-N`, `portal-N`, `site-N`) instead of names in steps | n/a | I14 | new |
| L-4 | Model invents a handle | refused | server | F: exists [verified, role.md] | n/a | - | exists |
| L-5 | Model proposes outside its role (doors for defence, traps) | scope creep | type vocabulary | C: closed types; `door` only as a variant/corridor parameter with a ground from a closed list that excludes `defence` | n/a | I16 | partial |
| L-6 | Model chains relations wrongly ("A near B, B near C, so A near C") | wrong siting | n/a | C: every relation it needs is computed and stated (section 4) | n/a | - | new |
| L-7 | Prose instead of a proposal | nothing filed | queue | C: proposals are tool calls only [verified] | n/a | I16 | exists |
| L-8 | Model searches one level and concludes "nothing to dig"; absolute level guessed off-map | stalled expansion | review | C: the graph and route reads span every level of the window; finders take relative LEVEL [verified fixed] | n/a | catalogue (2026-09-11 to 09-15) | partial |
| L-9 | Folklore becomes a rule (door for privacy, enclosure for value, roughly sized rooms) | wrong templates | review | C: door grounds are a closed list; a variant has exact parameters; folklore entries sit in doctrine as non-rules | revise variant | catalogue (2026-09-24, rematch office) | new |

**N. Plan and Architect disagree**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| N-1 | Room sited outside its target's district | plan drift | district membership of the site's portal | F: `district` field validated (Planner P2) | flag | - | new (P2) |
| N-2 | District anchor gone or duplicated | no guidance | Planner F-23 | flag, suspend that district's guidance | Planner re-anchors | - | new (P2) |
| N-3 | Closeness X pair joined by a short corridor | noise next to bedrooms | graph walk length per closeness pair | F metric: corridor proposals report each closeness pair they shorten | Planner or Overseer rules | - | new |
| N-4 | Plan wants N rooms but no portal capacity exists in the district | stalled target | portal count per district | F: the Architect's pass reason is code-filled "no free portal in district living; a corridor extension is needed" | file a corridor | - | new |

**Q. Game-side refusal or silent failure**

| # | Mode | Effect | Detect | Prevent | Recover | Inc | Now |
|---|---|---|---|---|---|---|---|
| Q-1 | Job cancelled (interrupted, material missing) | step stalls | `status`, `stuckjobs` | grace windows plus stall wakes [verified] | re-queue | I12 | exists |
| Q-2 | Zone placement refused on hidden tiles | room without zone | `zone.place` result | C: zone phases depend on shell done [verified ordering] | re-apply | - | exists |
| Q-3 | A dug room stays rough because smoothers have no labor | unfinished | `surface.finish` | F: finish phase cites enabled labor count | enable labor | - | partial |
| Q-4 | Door built but forbidden or locked by default, blocks pathing | rooms cut off | door state read | X: doors placed passable; read back | toggle | - | new |
| Q-5 | Predicted path differs from the game's (traffic, crowding) | metrics wrong | section 8.5 | C: metrics stated as estimates with source | recalibrate | - | new |

Counts: 92 rows. 47 have a `C` control; 33 rely on an `F` or `X` guard
only; 12 are detect-and-recover (G-6, A-3, A-7, V-4, V-7, W-2, N-2, N-3,
Q-1, P-10 and the two `K` rows). The rows whose only control is `K`
(charter text) are M-4 and D-4, both judged acceptable because the failure
is cheap. W-4 (cave-in) has a planned `F` guard that needs a read nobody
has built.

### 2.3 Incident cross-check

Every incident below was found in this project's own records this session.
The parallel catalogue (`research/2026-10-08-architect-failure-catalogue.md`)
landed while this was being written; 2.4 maps it.

| Inc | Date | What happened | Source | Rows |
|---|---|---|---|---|
| I1 | 2026-09-11 | dig and build passed the box centre to quickfort's top-left `-c`; the dug box had no walkable neighbour | register 2026-09-11 root-cause row | G-1 |
| I2 | 2026-09-17 | `dig-stair` reported success while quickfort skipped a building-occupied tile; `i` on open floor gives only a down stair | register 2026-09-17 stairs row | V-2, V-3, P-1 |
| I3 | 2026-09-24 | office site-1 applied where its entrance was unreachable; 10 blind designations stalled; released | register 2026-09-24 access rows, `evals/live/2026-09-24-blueprint-deploy` | D-1, D-4 |
| I4 | 2026-09-24 | the access gate would refuse tiled rooms whose hallway is still being dug (user's point) | register 2026-09-24 access row | A-8, D-3 |
| I5 | 2026-09-24 | office v1 floor left rough (no floor phase) | `office-room-v2.yaml` `floor.note` | T-1 |
| I6 | 2026-09-24 | hematite in the office ring smoothed instead of mined | register 2026-09-24 ore row | S-3 |
| I7 | 2026-09-28 | constructed walls (buildings 21, 22) about to seal exposed ore | `research/2026-09-28-job-dependency-graph.md` §3 | S-2 |
| I8 | 2026-09-23 | Chair built outside both Office zones | `research/2026-09-24-room-layout-best-practices.md` Q5 #4 | T-2 |
| I9 | 2026-09-24 | coffin sited by straight-line distance into a poor spot | register 2026-09-24 site-ranking row | G-4 |
| I10 | 2026-09-24/25 | soil ring tiles cannot be smoothed; `Cw` cannot go on a standing wall | register 2026-09-24 hands row | G-5 |
| I11 | 2026-10-05 | bedroom block: entrances open into each other, up to five bedrooms crossed | register 2026-10-06 | A-1, A-2 |
| I12 | 2026-10-07 | bed placed with no BED item ever made; finish suspended; Overseer deferred bedrooms | `evals/live/2026-10-07-stuck-bed` | M-1, Q-1 |
| I13 | 2026-10-05/07 | bedrooms re-proposed though accepted and dug | `evals/live/2026-10-05-execution-stage-0`, register 2026-10-07 duplicates row | R-5 |
| I14 | 2026-09-30 | landmark names with an apostrophe cannot be passed | register 2026-09-30 reservations deploy row | L-3 |
| I15 | 2026-10-07 | landmark names repeat; exit distances are x/y only, 3 nearest | Planner red team F-23 | P-4, L-2 |
| I16 | 2026-09-14 | Architect run #2 proposed a door or trap (defence) and filed no proposal record | register 2026-09-14 | L-5, L-7 |
| I17 | 2026-09-12 | a full-map Lua scan pegged DF for nine minutes; kill-lua hung | register 2026-09-12 | P-7 |
| I18 | 2026-09-24 | `jobs_claimed_by_a_worker` null for "no jobs" | register 2026-09-24 | P-2 |
| I19 | 2026-09-24 | room-value proxy false negative | register 2026-09-24 | P-3 |
| I20 | 2026-09-28 | an ore scan counted hidden tiles | job dependency graph §0 | P-5 |
| I21 | 2026-09-14 | first `prefer_indoors` and similar kind-level booleans baked into the ranker | register 2026-09-24 site-ranking row | G-4 |
| I22 | 2026-10-02 | a finish phase applied before its item existed held WIP (rooms waiting on items) | Planner F-2 | M-1 |
| I23 | 2026-09-24 | rotated previews: three of four orientations unreachable at a site; orientation chosen by the verb | register 2026-09-24 access-live row | G-2 |
| I24 | 2026-09-30 | reservation override recorded on a dry run | register 2026-09-30 | R-3 |
| I25 | 2026-09-30 | reservation ages built on tick-within-year | register 2026-09-30 | R-4 |

### 2.4 Cross-check against the failure catalogue

`research/2026-10-08-architect-failure-catalogue.md` Part 1 (59
deduplicated incidents, second-hand: its miners did not re-read code).
Two of its guard statuses are out of date, per the coordinator and checked
where possible: a duplicate-action detector **does** exist
(`dfqueue/step_identity.yaml`, read this session), and paused-versus-broken
now has `screen.read` and a resume check that names a blocking panel
(deployed 2026-10-08 per the coordinator; I saw `resume_and_verify` in
`conductor/pause_watch.py`, not the deploy).

| Catalogue entry | Rows |
|---|---|
| founding dialog freezes the fort | out of scope (UI) |
| down stair on grass designates 0 tiles | V-7 |
| floor under a down stair needs a stair | V-6 |
| `-c` centre vs top-left | G-1 |
| dig candidate with no walkable border | D-1, A-9 |
| blueprint entrance in hidden rock facing away | D-1, G-2 |
| access gate refuses tiled rooms before the hallway | A-8, D-3 |
| absolute Z off-map; "nothing diggable" five times | L-8 |
| "nothing to dig" from its own level | L-8 |
| Well ramp-top reachability false negative | V-5 |
| room-value proxy false negative | P-3 |
| two Office zones placed outdoors, unfurnished | G-4, T-2 |
| furniture blocked a Tomb zone; coffin outside any zone | T-2, Q-2, G-4 |
| static site-ranking sort | G-4, section 5 (rooms leave the ranker) |
| finder offered water tiles for water zones | G-8 |
| pond channel flooded; sunken basin | W-1, W-5 |
| Water Source zone in deep water | G-8 |
| breach detector read as inert | W-1 (detection) |
| ore smoothed into the office wall | S-3 |
| wall step infers "mined" from "is open" | S-6 |
| office sealed during build | S-1, S-6 |
| bedroom block rooms open into each other | A-1, A-2 |
| `building find` proves only a walkable neighbour | A-9 |
| door folklore | L-9, 3.4 |
| enclosure believed required | L-9 |
| soil wall cannot be finished; `#meta` swallows failures | G-5, P-8 |
| blueprint has no orientation | G-2 |
| 5x5 room landed on soil not stone | G-5, G-6 |
| `workshop find` no candidate after the farm took the room | N-4 (portal capacity), G-7 |
| Chair and Bed suspended, bed never ordered | M-1 |
| Still unsuspended by hand and deleted | M-5 |
| hand-suspended wall beside ore could be released | S-7 |
| Overseer deferred bedrooms as "no unsuspend tool" | M-1 (cause); Overseer charter, out of scope |
| standing order that never runs | out of scope (Quartermaster) |
| manager orders with no material | out of scope (Quartermaster) |
| `RES_ID` does not pin a site | R-6 |
| duplicate proposals | R-5 (detector exists; same-need gap remains) |
| bedroom alert double counting | R-5, M-1 (Planner F-6) |
| one pick throttles digging | M-6 |
| `zone.assign-owner` in no allowlist | out of scope (allowlist decision) |
| misrouted ask, escalation nowhere | out of scope (Overseer) |
| paused fort read as broken | out of scope (now `screen.read`, conductor) |
| Architect dropped the record, proposed a door/trap | L-5, L-7 |
| rematch office "roughly 5x5" | L-9 |
| magma counted as water | P-9 |
| unbounded scans wedged the pipe | P-7 |
| offline fakes with wrong fields | P-10 |
| `reqscript` cache, stale code | out of scope (deploy process) |
| chokepoint stair flags any stair | V-4 |
| stuck job vanished: finished or cancelled | Q-1 |
| announcements unread | out of scope (perception generally) |
| `set_labor` races autolabor | out of scope (labor) |
| apostrophe argument refused | L-3 |
| material names print as raw ids | out of scope (cosmetic); matters for ore lines in the graph |
| links-only pile takes nothing | out of scope (Logistics) |
| `plan.read` file not shipped | out of scope (deploy) |
| per-kind hard-coded workshop kinds | generalisability test, section 12 |
| ghost attack during a dig | out of scope (threat) |
| tick printing bug | out of scope (tooling) |

All 59 are accounted for: 44 map to rows, 15 are outside the Architect's
domain and named so. The catalogue's recurring patterns line up with this
design's main moves: "silent success on a no-op" is P-1/P-8 and the
read-back rule; "a check that proves an adjacent property" is A-9 and the
graph; "order of operations is data the tools do not model" is the
planned-tile model with virtual phase application (D-2, S-4); "siting is a
static heuristic" is section 5; "offline tests cannot see the game" is P-10
and every stage's live negative control.

### 2.5 The user's catches, turned into code checks

The catalogue's last pattern: geometry and circulation problems are found
by the user more often than by code. Each past catch becomes a check that
runs at filing and on every graph rebuild, so the next one is found by
code first.

| What the user saw | Check that would have caught it | Where | Stage |
|---|---|---|---|
| bedrooms opening into each other, up to five crossed | `opens_onto` rule and private pass-through invariant | `check-plan`, graph | C1 (report), C3 (refuse) |
| tiled rooms refused because the hallway is not dug yet | plan-aware reachability over pending phases | `check-plan` | C3 |
| a dig with no walkable border never starts (first diagnosis wrong, then over-corrected) | reachable-from-hub on the planned graph, with the chain through pending digs | `check-plan` | C3 |
| ore smoothed over in a ring | finish refused while `ore_exposed` is non-empty (to X) | blueprint verb | C3 |
| water zones offered on water tiles | liquid-aware siting, shore resolution | planned model | C2 |
| coffin and offices placed by straight-line distance | walk length from the graph replaces straight-line distance for siting facts | graph, section 5 | C1 |
| doors and enclosure folklore | closed door-ground list; doctrine non-rules | data | C0 |
| bed never ordered behind a suspended finish | finish phase cites each required item's stock or open order | filing | C3 |

A standing rule follows (proposed, D13): **every future user catch of a
geometry or circulation problem gets a `check-plan` rule and a regression
case before the fix ships**, the same way a bug gets a failing test.

---

## 3. Circulation as a first-class thing

### 3.1 Vocabulary

| Element | Meaning | Kinds |
|---|---|---|
| **Spine** | the fort's main horizontal artery on a level, joining the stair hub to district throats | width class 3 (decision D6) |
| **Collector** | joins a district's rooms or bays to the spine | width class 2 |
| **Branch** | short dead end serving a few private rooms | width class 1 |
| **Hub** | a junction where a spine meets a stair column | a `stair-column` landing, at least 3 by 3 open |
| **Portal** | a tile on a corridor's side where a room may attach | code-issued handle |
| **Throat** | a 1 or 2 wide segment at a district boundary where a door can go | flagged in the graph |
| **Walkway** | circulation on the surface or across open space (section 9) | wagon route, entrance approach, bridge |

This is the road hierarchy (arterial, collector, local) the layout
research already imported (`room-layout` Q6, rule 12) [verified as a
cited convention], and the hospital-planning rule of separating flows
(below) reduced to what DF needs.

### 3.2 Widths by expected traffic

**Mechanic [prior, wiki Path, v53.16 banner, fetched this session]:**
creatures can walk over each other, but "moving over occupied tiles in this
manner is much slower, and dwarves will try to path so that they avoid it";
the page recommends routes "at least 2 tiles wide". Traffic costs are
per-tile pathfinding costs, High 1, Normal 2, Low 5, Restricted 25, and
"can be changed in settings or per fortress" [prior, wiki Traffic,
v53.16]. Job choice ignores traffic: "if a dwarf has an important job to
do, he/she will ignore any traffic designations" [prior, same page].

**Load estimate (code, static, the most defensible proxy per `room-layout`
Q2):** a segment's served load is the number of rooms, beds, workshops and
piles whose shortest path to the hub crosses it, weighted by kind (a
workshop bay counts as its piles' hauling, a bedroom as one dwarf). Width
class from load:

| Class | Width | Use | Load (proposed, invented, label as such) |
|---|---|---|---|
| 1 | 1 tile | branch to at most 4 private rooms, dead end | at most 4 bedrooms |
| 2 | 2 tiles | collector: a bedroom row, a workshop wing, a dining approach | up to about 20 dwarf-loads |
| 3 | 3 tiles | spine, hub approaches, depot route | more, or any route a wagon or a hauling chain shares |

The thresholds are this project's own convention, labelled so in the
data file, with a "10 dwarves per 1-wide branch" community figure as the
only external anchor [prior, `room-layout` Q2]. They become measurable
later (section 8.5: stuck and crowding reads).

### 3.3 Traffic designations

**Recommendation (D9):** the corridor generator writes `oh` on spines and
collectors, nothing on branches, and nothing (Normal) everywhere else at
first. No `or` (Restricted) anywhere until measured: a restricted dead end
is harmless but a restricted tile on a needed path costs 25 per tile and
the model cannot see why a dwarf detours. Designations ride in the
corridor's own `#dig` blueprint (`on/ol/oh/or` symbols [verified,
`quickfort-hands` §2]), so they need no new tool. `surface.traffic`
already reads them back [verified, TOOLS.yaml].

### 3.4 Doors: where, which kind, why

**Mechanics [prior, wiki Door via `room-layout` Q4]:** an unlocked door is
as passable as floor; a door blocks fluid like a floodgate with no
operating delay and destroys fluid on its tile when it closes; an item on
the tile props it open; forbidden doors block most creatures, with named
exceptions (thieves, building destroyers, ghosts). Bedroom privacy is not a
mechanic: "dwarves suffer no penalties from others traveling through their
bedrooms while sleeping" [prior, wiki Bedroom_design]. Miasma and
temperature: **[unverified]** whether a closed door stops miasma spread;
the earlier research found no source and neither did this pass. DF has no
room-temperature comfort model I know of, so "temperature" is not a door
reason here [unverified].

Door grounds as a **closed list** in data (the template README already
requires a justification for a door [verified]):

| Ground | Where | Basis |
|---|---|---|
| `fluid_containment` | throats between a risky dig face or a water feature and living districts | mechanic |
| `access_control` | district throats (door-ready, not locked by the Architect), vaults, jails | mechanic; the locking decision is the Overseer's |
| `user_standard` | bedrooms (user's stated preference, register 2026-09-24 design thoughts row) | user's call, explicitly not a mechanic |
| `hygiene` | refuse, tomb, butcher areas, if miasma containment is ever verified | unverified, so disabled until verified |

Never a door: on a spine or collector mid-run (a forbidden toggle there cuts
the fort), on a dining hall's main opening (the user's own example), or on
a portal that is a room's only entrance unless the room kind's rule says so.

### 3.5 Throats at district boundaries

The brief asked for "door at each district boundary". **Recommendation:
a door-ready throat, not a door.** The corridor generator narrows to a 1
or 2 wide, wall-flanked segment wherever a corridor crosses from one
district to another; the graph marks it `throat: door_ready`. Building a
door there is a separate, cheap, later step (fluid_containment or
access_control ground). Reason: a door is only useful once a reason exists,
and locking is military (Overseer). This gives the Overseer a known,
named lockdown point per district without the Architect deciding defence.

### 3.6 How rooms attach: access per kind

Per room kind, data (`blueprints/access.yaml`, proposed), each with a
ground:

| Kind | `opens_onto` | Ground |
|---|---|---|
| Bedroom | `corridor` | the bedroom-block defect; user |
| Office | `corridor` | traffic to a noble |
| Bedroom (noble) | `suite_of: Office` allowed | the user's "some rooms should open onto each other" |
| Dining hall, meeting hall | `corridor` or `hub`, many entrances allowed | crowding |
| Workshop bay | `corridor` (collector or spine) | hauling |
| Stockpile (inside a bay) | `room_of: workshop_bay` | Logistics' adjacency |
| Tomb | `corridor` or `any` | low traffic |
| Barracks, dormitory | `corridor` | |
| Farm | `corridor` or `hub` | |

Checked by code at filing (A-1, A-2) and on every graph rebuild. The
Planner may add a per-district override in its `access` section (stage P4
shape kept), which code applies on top.

### 3.7 Handing off from the Planner

The Planner gives districts (kind, anchor, level band) and a closeness
table between district kinds. The Architect turns that into circulation:

1. **Spine first.** For each level band in use, a spine joining the stair
   hub to each district's anchor area, routed by code (section 6).
2. **Closeness to corridor topology.** An A pair gets a direct collector
   (shortest walk); E and I share a spine segment; O and U need nothing;
   an X pair must not share a collector and must be separated by at least a
   throat (noise, safety). Code reports each pair's walk length on the
   planned graph; the Architect's corridor proposal carries those numbers
   (N-3). This answers the Planner red team's F-23 by replacing straight-
   line anchor distance with graph walk length.
3. **District throats** as in 3.5.
4. **Portals per district** become the capacity measure the Planner's
   shortfall can be answered against (N-4).

---

## 4. Representation: a graph the model can reason about without a map

### 4.1 What code builds

A **circulation graph** per fort, rebuilt on demand and on step completion:

- **Nodes:** `room` (a site, reserved footprint or zone: kind, district,
  private or public, handle), `junction` (corridor tiles of degree 3 or
  more after thinning), `landing` (stair column per level), `portal` (free
  attachment points), `open_area` (walkable space not explained by any
  room or corridor, for legacy and surface areas), `exit` (map edge,
  depot).
- **Edges:** `segment` (corridor between two nodes: width class and
  min/median width, walk length in tiles, level change, door id and state,
  traffic levels present, `planned|built|in_progress`), `entrance` (room to
  segment, or room to room), `vertical` (landing to landing).
- **Source of truth, two layers:** what we built and planned (sites,
  reservations, accepted corridor projects, variants) gives node identity
  and intent; a bounded live tile read confirms or contradicts it (recorded
  vs observed, never merged, `research/2026-09-28-job-dependency-graph.md`
  §0 item 3).

**How code segments legacy or surface space** where we have no records:
the robotics room-segmentation literature's simplest robust method is a
distance transform on free space with thinning to a skeleton, then cutting
at narrow points (Bormann et al. 2016, "Room segmentation: survey,
implementation, and analysis", ICRA) [from memory, not fetched this
session]. Here: free tiles not inside any known room footprint form
circulation components; skeleton tiles of degree 3 or more are junctions;
the run between them is a segment; its width is twice the distance
transform's median along the skeleton. This only has to work for the
leftover space; most structure comes from our own records.

### 4.2 What the model sees

Canonical sentences (one fixed phrasing per relation, the "descriptive
bias" caution in `district-layout` Q5):

```
Corridor 4 (collector, 2 wide, built, 18 walk-tiles, level 0): joins Hub A to junc-7.
  Rooms on it: 6 Bedroom (site-11..site-16), each opens onto it. Free portals: 3 (portal-21..portal-23), north side.
  Throat at junc-7 (living | industry), door-ready, no door.
Bedroom site-5: reached through 3 private rooms (site-2, site-3, site-4). Rule Bedroom: opens_onto corridor. VIOLATED.
Walk: Bedroom row B to Dining Hall 14 tiles (median), 22 (max). To Well 31.
```

Numbers, handles and names; no tile, no direction vector. Directions are
allowed only as the existing coarse words (north/south) the landmark tools
already use, never as offsets.

### 4.3 Checks code evaluates

| Check | Kind | Basis |
|---|---|---|
| Every room's entrances satisfy its kind's `opens_onto` | invariant (refuse) | user, register 2026-10-06 |
| No room's shortest path from the hub passes through a private room (justified graph depth: a private room must be a leaf, space syntax "a-type" in Hillier's terms [from memory: the a/b/c/d classification was not found in this session's search results]) | invariant | user, space syntax |
| Every named place reachable on the planned graph, during and after each phase | invariant | D-1, D-2 |
| Stairs vertically consistent | invariant | wiki Staircase |
| No closure seals a room, unit, item or exposed ore | invariant | S-1, S-2 |
| Walk length bedrooms to dining, to well, to their district hub | metric | `room-layout` rule 10 |
| Width class vs load | metric | rule 7 |
| Dead-end depth (rooms behind one throat) and common path (walk before two independent routes exist) | metric, hard cap optional (D7) | building egress codes, below |
| Articulation points and bridges among high-load nodes | metric | rule 5 |
| Each district boundary has a door-ready throat | metric | 3.5 |
| X closeness pairs sharing a collector | metric | Planner closeness |
| Circulation tiles per room tile (dig cost) | metric | rule 13 |

**Cross-domain anchors for the metrics:** the International Building Code
limits dead-end corridors to 20 feet (50 feet in several sprinklered
occupancies), exempts a dead end shorter than 2.5 times its least width,
and limits the "common path of egress travel" (the walk before two
independent routes exist) to 75 feet in Group B, 100 sprinklered; corridors
serving more than 50 occupants are at least 44 inches wide [prior, from
search-result summaries of practitioner pages, not the code text; section
16]. What transfers is the *shape* of the rule: limit dead-end depth and
common path, scale width with occupant load. The numbers do not transfer.

### 4.4 Reads that exist and reads that are missing

| Need | Tool today | State |
|---|---|---|
| Walkable groups, reachability between named places | `connectivity.report`, `connectivity.check` (tri-state) | exists, live-verified 2026-09-23 [verified] |
| Room footprints we made | `blueprint.sites`, `blueprint.reservations` | exists [verified] |
| Zones and their furniture | `zone.list`, `zone.contents` | exists |
| Entrance gaps of a zone ring | `surface.enclosure` | exists |
| Traffic on a zone's tiles | `surface.traffic` | exists (zone-scoped only) |
| Stairs as chokepoints | `chokepoints.find` (stair kind verified; corridor kind unproven; **coordinate-bearing by design**) | exists, must not feed the model directly |
| Building sizes per kind | `building.list-kinds` | exists |
| Seal check for walls | `construction.audit` | exists, never run live |
| Landmark distances | `landmarks.list` (x/y straight line, 3 exits) | exists, **unfit for circulation** (F-23) |
| **Circulation graph** | none | **missing**: `circulation.graph` |
| **Planned-tile model and path query** | none | **missing**: `circulation.route`, `circulation.check-plan` |
| **Door state** (passable, forbidden, open) | none beyond `surface.enclosure` | **missing**, part of the graph read |
| **Unit path oracle** (the game's own computed path for a walking unit) | none | **missing**, internal validation only (8.5) |
| **Support / cave-in read** | none | **missing**, research owed (W-4) |

---

## 5. How a room is placed under this design

1. The Planner's shortfall wakes the Architect (unchanged).
2. The Architect reads `circulation.graph` for the target's district:
   free portals and their walk numbers. If none, the code-filled pass
   reason says a corridor extension is needed (N-4) and the Architect files
   a corridor proposal first.
3. It files `room_siting` naming a variant and a `portal-N`. The server
   dry-runs: footprint fits behind the portal on the planned model, access
   rule, no pass-through, reservation overlap, stranding, finish plan, item
   requirements. Refusal names every problem.
4. The Overseer rules; the conductor executes phases; each phase's
   completion re-runs the graph checks against live tiles.

The siting finder (`ranked_rects`) is no longer used for rooms that attach
to circulation; it remains for things that genuinely sit "near a landmark"
(a coffin near a tomb, a well). This retires the register's "too rickety
to patch" ranker for rooms without patching it.

---

## 6. How a corridor gets built

### 6.1 Two options compared

| | (a) Generic corridor templates tiled from a path the model requests by anchors | (b) Code path-finder routes, generator emits segments |
|---|---|---|
| Who chooses the path | the model, by choosing which straight, T, cross, landing pieces and how many | code (A*), the model chooses ends, width, door policy |
| Coordinate reasoning by the model | implicit: counting tiles, choosing turns | none |
| Failure modes | every tiling mistake is a geometry bug (G-1, T-4) | router bugs, caught once by tests |
| Fits around existing rooms | the model would need to see where rooms are | the router reads the planned model |
| Generalisable | piece library grows per shape | one router, one segment generator |
| Prior art | df-ai's `find_typed_corridor` is a BFS router, and its corridor bugs were connection bugs [verified, `df-ai` research Q5 commit list] | VLSI maze routing (Lee 1961; A* with bend penalties), dungeon generators' MST plus loops [prior: TinyKeep] |

**Recommendation: (b), with (a)'s pieces kept as the generator's output
vocabulary.** The router returns a path; the generator decomposes it into
straight runs, junctions and landings, each a known-good segment with seams
on its ends, written as one generated quickfort file per corridor project
(multi-level with `#>`/`#<` where it changes level, 6.3).

### 6.2 The router

- Graph: the planned-tile model (section 8), bounded to the fort window.
- Cost per tile: dig cost (solid rock 1, already open 0.2, soil 1.2, ore
  or gem **infinite unless the request says mine through**, hidden tiles
  1 plus a risk count), plus a bend penalty (straight corridors are
  cheaper to reason about and to widen), plus an infinite cost through
  room interiors, reserved footprints and visible liquid; a penalty for
  passing within one tile of a private room's wall (keeps a later portal
  row possible).
- Width: the router finds a centreline and checks clearance for the width
  class (a tile is usable only if the class's cross-section fits).
- Ends: handles (`site-N` entrance, `junc-N`, `portal-N`, landing) or a
  landmark name resolved by the server.
- Loops: when the new corridor would make a dead end deeper than the cap or
  create a bridge on a high-load path, the router offers one extra link
  (the TinyKeep "add back 8 to 15 percent of edges" idea [prior], here
  driven by measured dead-end depth rather than a percentage).
- Output to the model: walk length, tiles to dig, ore crossed (named, from
  visible tiles only), hidden tiles assumed, closeness pairs shortened or
  lengthened, rooms that gain portals. Never the path.

### 6.3 Stair landings and level changes

A corridor between levels uses a `stair-column` variant at a hub: a
column of stair tiles with a 3 by 3 (or wider) landing per level. The
generator emits quickfort's multilevel form: "separating Z-levels of the
blueprint with `#>` (go down one z-level) or `#<` (go up one z-level) at
the end of each floor", `#>2` for two levels, and `repeat(down N)` as a meta
marker [prior, DFHack quickfort user guide, `docs.dfhack.org/en/stable`,
fetched this session; **the stable docs may be newer than this install's
53.16-r1.1; check the installed guide before relying on `repeat`**].
Symbol choice per level is by tile state (V-1, V-2): top `j`, middle `i`,
bottom `u` when carved from rock; a constructed stair where the tile is
already open and an up stair is needed.

### 6.4 Retrofit of the existing bedroom block

Generic, not a hand fix (the geometry is not described here and must not
be):

1. **Diagnose (stage C1, read-only):** the graph lists each bedroom's
   entrance edges and the private rooms on its shortest path. Expected:
   chained entrances, depth up to five (I11).
2. **Plan (code):** for each room that violates its rule, find the cheapest
   new entrance tile on its ring that the router can join to circulation
   (prefer one corridor along the row's entrance side, so all rooms share
   it), then the closure set (old openings into another room's interior).
3. **Steps, ordered by construction (S-4):** dig the corridor and the new
   entrances; when each new entrance is reachable (read back), close that
   room's old opening with `Cw` (an open tile, so `Cw` is legal [verified
   rule]); optional door on the new entrance under `user_standard`.
4. **Checks before each closure:** no unit or item on the tile (B-2); the
   room stays reachable through its new entrance on the live graph (S-1);
   no bed or other furniture on the new entrance tile (A-5).
5. **Model sees:** "Retrofit plan for Bedroom block: 1 corridor (2 wide,
   14 tiles), 4 new entrances, 4 closures, 0 ore crossed, 2 hidden tiles
   assumed. After: no room reached through another; median walk to
   Dining Hall from 19 to 12." It files one `corridor` proposal with the
   retrofit as phases.

---

## 7. Workshop placement

**Recommendation:** a workshop is never placed alone; it is placed as a
**workshop bay** (section 8.1 generator) at a portal on a collector, inside
the Planner's industry district, with:

- **Inputs and outputs:** its feeder and output piles inside the bay,
  sized by Logistics' `pile_spec` (Planner design 6.3, already decided as a
  required citation for kinds with linked inputs). The bay's walk from each
  pile to the workshop is at most a few tiles by construction; the wiki's
  workshop-wing example caps "maximum walk to stockpile on same wing" at 18
  [prior, `room-layout` Q1].
- **Relative to storage:** the collector serving the bay should join the
  spine on the storage district's side; the router reports the walk from
  the bay to the nearest pile of each input class's source (a closeness
  number, not a rule).
- **Relative to bedrooms:** never on a collector shared with a living
  district if the Planner rates living/industry X (reason noise). Whether DF
  models workshop noise disturbing sleep is **[unverified]**; the rule rides
  on the Planner's judgment row, not on a mechanic.
- **Workshop's blocking tiles:** read from the game's building data per
  kind (`building.list-kinds`), so the bay never puts the workshop's
  impassable tiles on the bay's internal walk (A-5).
- **Many of a kind:** two workshops of the same kind may share one bay and
  its piles (Logistics decides the piles).

---

## 8. Parametric generators, dynamically sized bays, and the pre-dig pathfinder

### 8.1 Dynamically sized workshop rooms: parametric beats a fixed library

The user asked whether a workshop room holding x workshops and x piles,
piles sized dynamically, is better generated from parameters than drawn from
a fixed library. **Recommendation: generated (D4).**

| | Fixed library | Parametric generator |
|---|---|---|
| New workshop kind | new CSV per combination | one data row (size read from the game) |
| Pile sizes from Logistics | cannot follow; closest fit wastes or starves | exact |
| Validation | each file reviewed by hand | the generator is tested once over a parameter sweep; every output also goes through V3 and V4 |
| Risk | few, reviewed files | a generator bug hits every variant, so tests matter more |
| Model's job | pick a file | pick parameters; code validates |

`workshop-bay` parameters: `workshops: [{kind, count}]`, `piles: from
pile_spec answer ask-N` (purpose, classes, tiles, adjacent_to),
`corridor_side`, `door_policy`, `walls: finished`. Deterministic layout
rule (no search, so it is testable): workshops in a row along the back
wall, an internal 1-wide work aisle in front, feeder piles between aisle
and corridor in the order the pile_spec lists them, output pile nearest the
entrance; bay depth and width follow from the sums. If the sizes do not
fit the generator's maximum (quickfort's and `stockpile.place`'s 31 by 31
cap [verified, Planner design 6.3]), it refuses and says by how much.

**How Logistics states pile space:** already decided in shape: a
`pile_spec` answer listing purpose, classes, tiles and adjacency (Planner
design 6.3) [verified as a design]. This design consumes it unchanged and
adds one rule: the bay is generated from the *cited* answer, so the piles
the Architect leaves room for are the piles Logistics later places,
reserved inside the bay as kind `stockpile` (A-6 by construction). Stage L
is not built; until it is, the bay takes a default pile_spec from the
per-kind input table, flagged as a default.

### 8.2 The planned-tile model

A code-side model of the fort window: per tile, a passability class.

- **Inputs:** visible tiles from a bounded live read (tiletype shape and
  material class, building occupancy class, liquid depth and type,
  hidden flag, traffic level, door building and its flags); plus every
  reservation, accepted and pending proposal's generated blueprint applied
  *virtually* in step order.
- **Window and cost (P-7):** the union of walkable groups that contain our
  landmarks, plus planned footprints, plus a margin; capped (proposed:
  200,000 tiles), read in chunks with yields, no per-tile closure. The
  full-map scan that hung DF read 6.86 million tiles with a closure each
  [verified]; the window is about thirty times smaller and must still be
  measured on the live fort before it is trusted.
- **Where it runs:** the Lua side extracts compact passability rows
  (internal-only coordinates, never returned to a model, the
  `coordinate_bearing: internal-only` convention [verified, TOOLS.yaml]);
  the Python side on the same VM (the MCP server) builds the model, runs
  A*, builds the graph and answers in words.

### 8.3 Passability and cost rules

| Tile | Passable | Notes and source |
|---|---|---|
| floor, open ground, smooth floor | yes | |
| wall, fortification | no (fortification passes fluids, not creatures [prior, general]) | |
| up stair | up to a tile above that is a down or up/down stair | wiki Staircase, `room-layout` Q3 [prior] |
| down stair | down to a tile below that is up or up/down | same |
| up/down stair | both | same |
| ramp | up to the tile diagonally or orthogonally adjacent one level up, where a wall supports the ramp | wiki Ramp [unverified this session: rule from memory; the planned-model test suite must encode it from the installed source or wiki before use] |
| door | yes if not forbidden; no if forbidden or locked | wiki Door [prior] |
| building | per occupancy class: none, passable, floored pass; obstacle, impassable, well block | DFHack tile occupancy enum [inferred from df-structures naming, not read this session] |
| liquid | depth at or above a threshold blocks non-swimmers | **[unverified]**: threshold not checked this session; treat depth 4+ as blocking and validate (8.5) |
| hidden | unknown: passable only if planned to be dug | knowledge rule [verified] |

**Costs (what DF does, as far as can be sourced):**

- Pathfinding is A* with an admissible heuristic, so the found path is
  optimal for DF's cost function [prior, wiki Path, v53.16].
- Per-tile traffic cost: High 1, Normal 2, Low 5, Restricted 25 by default,
  changeable per fort [prior, wiki Traffic, v53.16]. The model reads the
  fort's own values if DFHack exposes them [unverified field].
- Diagonal steps are legal [prior, wiki Path]. **Travel time** for a
  diagonal step is 362/256 of an orthogonal one per a wiki page found by
  search in an older namespace [unverified for v53: the current Gait page,
  fetched this session, does not state it; it gives 900 ticks per 100 tiles
  for a normal walking dwarf]. Whether the *path cost* charges diagonals
  extra is not stated anywhere I found [unverified].
- Stairs and ramps: no extra time stated on the current Gait page [prior,
  absence of a statement, not a confirmed zero].
- Crowding: walking over a creature is "much slower" and avoided [prior,
  wiki Path]; not modelled statically.
- Material search for jobs uses Manhattan distance in an expanding cube,
  not path length [prior, wiki Path]. **This matters for workshop bays:**
  DF picks materials by cube distance, so a pile on another level directly
  above can win over a nearer-by-walk pile on the same level. Links
  (Logistics) override this; the bay design leans on links for that reason.

So the simulator reports two numbers per route: **DF cost** (traffic cost
sum, as DF ranks paths) and **walk tiles** (orthogonal steps plus 1.41 per
diagonal plus 1 per level), both labelled estimates.

### 8.4 What the model gets

`circulation.route FROM TO [PLANNED]` returns: `exists: yes|no|unknown`
(with the reason: blocked by liquid, hidden assumption, forbidden door),
`walk_tiles`, `df_cost`, `levels_changed`, `doors_crossed`,
`throats_crossed`, `rooms_crossed` (must be 0 for public routes), and
`depends_on` (the pending steps the route needs). `circulation.check-plan
PROPOSAL_OR_STEP` returns every invariant and metric of 4.3 as verdicts.
Named endpoints and numbers only.

### 8.5 Validating the simulator against the live game

1. **Existence:** after every phase lands, for every pair of named places
   the planned model said are connected, `getWalkableGroup` must agree
   (same group), through the existing tri-state helper [verified exists].
   Disagreement is a gotcha record and a P-6 detection.
2. **Length:** DF stores a walking unit's computed path on the unit
   (df-structures `unit.path`, a destination and a vector of path
   positions) [inferred: from memory of df-structures, not read this
   session]. A validation read (code-only, internal coordinates, never
   shown to a model; a player can see where a dwarf walks, so this is
   not an armok read, but confirm the ruling, D11) samples dwarves already
   walking, takes their start and destination, runs our A* between the
   same tiles, and compares length and cost. Target: path length within
   10 percent on 95 percent of samples before metrics are trusted
   (proposed acceptance).
3. **Time:** for a few samples, read the unit's position each N ticks until
   arrival and compare elapsed ticks to `walk_tiles` times the gait rate;
   this calibrates the diagonal and stair factors the wiki does not state.
4. **No unpausing for validation alone:** samples are taken during the
   fort's normal supervised runs.

---

## 9. Walkways, surface and underground

**Underground walkways are corridors** (sections 3 and 6). Surface
walkways are a different thing and mostly not worth building:

- **Wagon route (build it, as a check first):** caravans need a wide clear
  route from the map edge to the trade depot; the common figure is 3 tiles
  wide [prior, general wiki knowledge, not fetched this session]. The
  router checks it with a 3-wide clearance class; the result is a `walkway`
  edge from `exit` to the depot. Trees on the route are the usual blocker;
  `trees.fell` exists.
- **Entrance approach:** one surface-to-fort route, ending in a throat with
  a door-ready tile (defence and flood control for the Overseer to use).
- **Paths to surface work:** farms, wood, the well. The surface is
  walkable anyway; record these as `walkway` edges for walk numbers, build
  nothing unless the route crosses water or a cliff (a bridge or a stair).
- **Roads (constructed floor):** **not recommended** now; no verified
  benefit to walking found this session [unverified].
- **Covered walkways** against weather or cave adaptation: not recommended
  without a verified mechanic; the earlier research only found a meeting
  hall sunlight claim on an older-banner page [`room-layout` Q4].

Recommendation (D10): build only the wagon-route check and the entrance
throat now; everything else is graph edges, not construction.

---

## 10. Hallways of different sizes

Covered in 3.2 and 3.3. In one line each:

- **1 wide:** dead-end branches to at most 4 private rooms; never a
  through route; never a spine. Mechanic behind it: crowding is slow and
  avoided [prior, wiki Path].
- **2 wide:** collectors (a bedroom row, a workshop wing, the dining
  approach); the wiki's own minimum for routes [prior, wiki Path].
- **3 wide:** spines, hub approaches, the depot route; "three is better"
  for heavily used tunnels [prior, convention, `room-layout` Q2].
- **Traffic:** `oh` on 2 and 3 wide, none on 1 wide, no Restricted until
  measured.
- **Widening later:** a collector is generated with its widening side kept
  free of portals (the router's one-tile margin), so 2 to 3 is a dig, not
  a rebuild.

---

## 11. Blueprints spanning levels

- **Syntax:** `#>` / `#<` between floors, optional count, `repeat(down N)`
  [prior, stable docs; check the installed guide, 6.3].
- **Templates:** `stair-column` (levels, landing size per level, landing
  sides) and `room-stack` (a bedroom row repeated on N levels around one
  column, the wiki's "Sandwich" family [prior, `room-layout` Q1]).
- **Connection rule:** every level of a multi-level variant has its own
  landing, and V4 simulates every level's reachability from every other.
- **Apply order:** quickfort applies one z-level at a time inside a file
  [verified, `quickfort-hands` §1, the API path]; the blueprint verb's
  read-back covers every level (P-1).
- **Hidden levels:** the column may designate stairs into hidden tiles
  (acting on hidden is allowed, register 2026-09-16); the result reports
  levels that were hidden as `assumed`.
- **Vertical redundancy:** one column per hub; a second column per district
  is proposed when the graph shows a vertical bridge carrying more than the
  class-3 load (V-4), flagged, the Planner decides (D8).

---

## 12. Build order

Each stage is live-checkable on its own, adds no write path until C3, and
follows the user's "set intent, let the game execute": nothing here
schedules dwarves; code computes geometry and checks; DF does the work.

| Stage | What | Live check | Tools |
|---|---|---|---|
| **C0** | Access data file, door grounds, width classes (data only); `opens_onto` added to template YAMLs; README table fixed | none (offline, tests) | none |
| **C1** | `circulation.graph` read: bounded window, nodes from our records plus segmentation, entrance and pass-through checks, walk numbers | run on the fort: the bedroom block shows the pass-through (I11 reproduced); scan time under a measured bound; every node's reachability agrees with `connectivity.check` | `circulation.graph` (read, Architect, Planner) |
| **C2** | Planned-tile model and `circulation.route` / `check-plan` (read): virtual application of pending blueprints, A*, invariants of 4.3 | predict two routes between existing landmarks; compare existence to walkable groups; compare length to a sampled unit path (8.5) | `circulation.route`, `circulation.check-plan` (read) |
| **C3** | Filing-time guards: `room_siting` and `corridor` dry runs call `check-plan`; plan-aware access gate (A-8); finish-phase ore guard to X (S-3) | file a deliberately violating proposal (a bedroom opening into a bedroom) and see it refused; file a valid one | server checks, no new agent tool |
| **C4** | Generators: `room-cell` (reproduces v1/v2 fixtures), `room-row`, `corridor-run` and router, `junction`, `stair-column`; `template_variant` record; linter V3 and simulation V4 | generate and preview (dry run) a corridor and a row on the live fort; no apply | `template.lint`, `template.preview` (read); `queue.propose` type `template_variant` |
| **C5** | Bedroom block retrofit, supervised | after: the graph shows no pass-through; walk numbers improve as predicted; no sealed room | uses `corridor` routed steps; `construction.door` joins the `rooms` group if D5 says doors |
| **C6** | `workshop-bay` with pile_spec (default spec until stage L), wagon-route check, throats | one bay built supervised; Logistics or the default spec's piles fit; walk inside bay as predicted | generator, no new tool |

**Generalisability test, per new tool:**

| Tool | "What does the next instance cost?" |
|---|---|
| `circulation.graph` | a new room kind: its access row in data; nothing in code |
| `circulation.route` | a new passability case (a new building kind): its occupancy class comes from the game |
| `check-plan` | a new invariant: one rule entry with a code predicate from a small closed set (reachable, leaf, aligned, sealed, width) |
| generators | a new workshop kind: size and blocking tiles from the game's building data; a new room kind: one variant |
| `template_variant` | a new variant: one record, no code |

**Measurable success criteria:**

1. After C5, the circulation graph reports **0 rooms reached through a
   private room** on the fort, and every bedroom's entrance satisfies its
   rule.
2. Over the next 20 room or corridor proposals, **0 executed steps leave a
   room, unit, item or exposed ore unreachable** (read back), and 0 stalls
   from stranding.
3. Simulator existence predictions match walkable groups on **100 percent**
   of checked pairs; length within 10 percent on 95 percent of sampled unit
   paths.
4. Median walk from bedrooms to the dining hall falls by the amount the
   retrofit plan predicted, within 15 percent.
5. Every template variant applied in that period reaches `verified-live`
   with **no** hand-fix, and none needed a post-build geometry correction.
6. Architect turns per room do not grow: the portal flow should cut
   finder rounds (measured from captured transcripts).

---

## 13. Cross-domain prior art, what each gave

| Field | Idea used | Where |
|---|---|---|
| Building egress codes (IBC) | dead-end limits, common path of travel, width scaled to occupant load; dead end exempt when short relative to width | 4.3 metrics, 3.2 [prior, practitioner summaries] |
| Architecture space planning, space syntax | justified access graph and depth from a root; private spaces as leaves | 4.3 pass-through invariant [prior, UCL and Buffalo summaries; a/b/c/d types from memory] |
| Hospital planning | separate circulation by flow (public, staff, supply) so one does not cross another's private space | 3.1 hierarchy, 3.6 access rules [from memory, not fetched] |
| Facility layout, warehouse aisles | aisle width by traffic; cross aisles cut travel (Roodbergen and de Koster on multiple cross aisles) | 3.2, 6.2 loops [from memory, not fetched] |
| Urban road hierarchy | arterial, collector, local; no direct drop from arterial to local | 3.1 [verified as cited in `room-layout` Q6] |
| Game level design | critical path plus loops; mission graph first, space second (Dormans 2010) | 3.7 (relations first, corridors second), 6.2 loops [prior: Dormans abstract, TinyKeep write-up] |
| Procedural dungeon generation | Delaunay, minimum spanning tree, add back some edges for loops | 6.2 |
| VLSI and PCB routing | maze routing with bend penalties; vias as level changes; wire width by current | 6.2, 3.2 [from memory] |
| Robotics room segmentation | distance transform and skeleton to split free space into rooms and corridors (Bormann et al. 2016) | 4.1 [from memory] |
| df-ai | typed exits on templates, router for corridors; its corridor bugs were connection bugs | 6.1 [verified, `df-ai` research] |

**Nobody does this, honestly stated:** no colony or city-builder game found
in the earlier survey computes adjacency or circulation for the player
(`district-layout` Q4), and I found nothing in this pass that plans DF
corridors from a traffic model. df-ai routes corridors but ignores traffic
and width. The combination here is new; the pieces are not.

---

## 14. Decisions for the user (one per line, with recommendation)

- **D1** Does the Architect author templates as parameters to code generators (recommended) or may it also draw small CSV grids? **Recommend parameters only for now.**
- **D2** Who owns room access rules per kind: the Architect as kind data (recommended), with Planner per-district overrides, or the Planner alone as its design says? **Recommend the Architect, Planner overrides.**
- **D3** Should a variant that introduces a new parameter value (first door ground, first width class) show on the Board for you once before first use? **Recommend yes.**
- **D4** Workshop rooms as a parametric `workshop-bay` generator sized from Logistics' pile_spec, instead of a fixed library? **Recommend yes, with a default spec until stage L.**
- **D5** Bedrooms get doors by default under your stated standard (`user_standard`), knowing the wiki says sleep is not disturbed? **Recommend yes, as the recorded ground, and doors join the `rooms` execution group.**
- **D6** Width classes 1/2/3 by load with the thresholds in 3.2 (labelled as our own convention)? **Recommend yes, revisit after measurement.**
- **D7** Dead-end depth and common-path: report only, or refuse above a cap? **Recommend report only, refuse only a private pass-through.**
- **D8** A second stair column per district when the graph shows a heavily loaded vertical bridge: Planner decides from a flag? **Recommend yes, flag only.**
- **D9** Traffic designations: `oh` on spines and collectors, nothing else, no Restricted until measured? **Recommend yes.**
- **D10** Surface walkways: only a wagon-route check and an entrance throat now, no roads? **Recommend yes.**
- **D11** Is reading a walking dwarf's computed path (internal validation only, never shown to a model) within the no-armok rule? **Recommend yes: a player sees where dwarves walk; confirm.**
- **D12** Retrofit the bedroom block as the first live use (C5), supervised, opening new entrances before closing old ones? **Recommend yes.**
- **D13** Every future user catch of a geometry or circulation problem becomes a `check-plan` rule plus a regression case before its fix ships? **Recommend yes.**

---

## 15. What could not be verified, and drift found

**Not verified this session:**

- The failure catalogue's guard statuses are as its sources state them
  (its own caveat); I re-checked only the duplicate detector
  (`step_identity.yaml`) and saw the resume check's function, not its
  deploy. Its Part 4 ledger (370 raw mentions) was not walked entry by
  entry, only its 59-entry Part 1, so a distinct incident missing from
  Part 1 could still lack a row.
- Diagonal travel factor 362/256 (older-namespace source via search
  summary; current Gait page silent), whether path cost charges diagonals,
  stair and ramp time: all to be measured (8.5).
- Ramp passability rule, liquid depth walk threshold, building occupancy
  enum names, and the `unit.path` structure: from memory, not read.
- Whether doors stop miasma; whether workshop noise disturbs sleep in v53;
  wagon route width on v53; any walking benefit of constructed roads.
- Quickfort `repeat()` and `#>` on this install's 53.16-r1.1: read from the
  stable online docs, which may be newer.
- IBC numbers: from practitioner summaries in search results, not the code
  text. Space syntax a/b/c/d types, hospital flow separation, warehouse
  cross-aisle results, VLSI routing and robotics segmentation: from memory,
  not fetched.
- The bounded tile read's cost on the live fort: unmeasured; C1's first
  run must time it under a pause.
- The actual bedroom block geometry: deliberately not read (no VM access;
  and the model must never be shown it anyway). The retrofit is designed
  generically; its numbers in 6.4 are illustrative.
- Cave-in and support rules (W-4): not researched; owed before any
  retrofit that removes material near constructions.

**Drift found (flag, suggest a memory or doc audit):**

- `blueprints/README.md` "Templates in this tier" lists only
  `bedroom-cell` as `designed`, "never applied"; the bedroom cell was
  applied live (site-3, register and `evals/live/2026-10-07-stuck-bed`),
  and `office-room-v1/v2` exist and are not listed. `bedroom-cell-v1.yaml`
  still says `status: designed`.
- `scripts/dfhack/TOOLS.yaml` marks `blueprint plan` `live_deployed: false`
  with an offline-only verified line, though the blueprint script was
  deployed and used live from 2026-09-24 (register). Possibly per-command
  staleness; worth a check.
- `research/2026-10-07-planner-design.md` §1 gives room-access policy to the
  Planner; the register's 2026-10-06 row calls it template data. This
  design resolves it as D2; whichever way the user rules, one of the two
  needs updating.

---

## 16. Sources

Repo, read this session: `CLAUDE.md`; `agents/architect/role.md`,
`tools.yaml`; `blueprints/README.md`; `blueprints/templates/*` (all six
files); `decisions/DECISIONS.md` rows 2026-09-11, 09-12, 09-14, 09-17,
09-24 (blueprint, access, site-ranking, df-ai, ore, design thoughts),
09-30 (reservations), 10-06 (room access), 10-07 (Planner, Logistics,
open questions, duplicates), 10-08 (this brief's row);
`research/2026-09-24-room-layout-best-practices.md` (full);
`research/2026-09-25-district-layout-prior-art.md` (Q1 to Q6);
`research/2026-09-24-df-ai-fort-planner.md` (Q1 to Q5);
`research/2026-09-24-quickfort-hands.md` (§1 to §3, §9);
`research/2026-09-24-room-enclosure-and-value.md` (verdict);
`research/2026-09-23-flood-relevance-and-traffic.md` (verdict, §1);
`research/2026-09-28-job-dependency-graph.md` (§0, §3);
`research/2026-10-07-planner-design.md` (§0 to §2.2, §6.3 to 6.5, §10, §12,
§13) and its revision 1 in git (`ac75b05`);
`research/2026-10-07-planner-red-team.md` (F-10, F-23);
`scripts/dfhack/TOOLS.yaml` (connectivity, landmarks, chokepoints,
surface, construction, blueprint entries); `dfqueue/schema.py`
(`ARCHITECT_TYPES`); `dfqueue/action_tools.yaml` (`rooms`, `stockpiles`);
`dfqueue/templates.py` (header); `evals/live/2026-10-07-stuck-bed`,
`2026-09-25-first-real-conductor-cycle`, `2026-10-05-execution-stage-0`
(bedroom lines).

Web, fetched or searched this session:

- [DFHack quickfort user guide (stable)](https://docs.dfhack.org/en/stable/docs/guides/quickfort-user-guide.html): multilevel `#>`/`#<`, `repeat()`, `transform()`, traffic symbols, door after walls. Fetched; may be newer than the install.
- [DF wiki: Path](https://dwarffortresswiki.org/index.php/Path) (v53.16): A*, admissible heuristic, diagonals legal, crowding slower, 2-wide advice, Manhattan cube material search. Fetched.
- [DF wiki: Traffic](https://dwarffortresswiki.org/index.php/Traffic) (v53.16): costs 1/2/5/25, changeable, important jobs ignore designations, dead-end advice. Fetched.
- [DF wiki: Gait](https://dwarffortresswiki.org/index.php/Gait) (v53.16 and v0.47.05): 900 ticks per 100 tiles walking; no diagonal or stair factor stated. Fetched.
- [DF wiki: 40d Time](https://dwarffortresswiki.org/index.php/40d:Time): the 362/256 diagonal factor, via search summary only, older namespace.
- [IBC egress corridor requirements (datadrivenaec)](https://datadrivenaec.com/insights/ibc-egress-corridor-requirements) and [exit count, travel distance and dead ends (open-exam-prep)](https://open-exam-prep.com/study-guides/are/ch12-ppd-codes-life-safety-accessibility/ppd-exit-count-remoteness-capacity): dead-end 20/50 ft, 2.5x width exemption, common path 75/100 ft, 44 in for more than 50 occupants. Search summaries.
- [TinyKeep dungeon generation (Game Developer)](https://gamedeveloper.com/programming/procedural-dungeon-generation-algorithm): Delaunay, MST, add back about 15 percent of edges. Search summary.
- [Dormans 2010, Adventures in level design](https://www.pcgworkshop.com/archive/dormans2010adventures.pdf): missions and spaces generated separately, graph grammar then shape grammar. Search summary.
- Space syntax justified graph and depth: [UCL discovery working paper](https://discovery-pp.ucl.ac.uk/1113/1/1113.pdf), [Buffalo architecture notes](https://www.acsu.buffalo.edu/~arced/arch&society/organiz/syntax.htm). Search summaries.

From memory, not fetched (labelled inline): Bormann et al. 2016 room
segmentation; Hillier's a/b/c/d space types; hospital flow separation;
Roodbergen and de Koster on warehouse cross aisles; Lee 1961 maze routing;
DF ramp rule, liquid walk threshold, occupancy enum, `unit.path`.
