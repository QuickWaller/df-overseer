# Red team: the Architect circulation design

Date: 2026-10-08. Read-only red team of
`research/2026-10-08-architect-circulation-design.md` (commit 920a8d3). No VM
touched, no fort read, no code changed. Tags used below:

- **[verified]** read this session in repo code or data, in the locally
  installed DFHack (its NEWS lists **53.16-r2** at the top; the VM runs
  53.16-r1.1, so a source read here is one point release newer than the
  fort's), or on a fetched DF wiki page carrying the v53.16 banner.
- **[prior]** a wiki or practitioner statement about game behaviour this
  project has not measured.
- **[inferred]** follows from verified facts; not observed.
- **[unverified]** could not be checked, with the reason.

No coordinate, grid or fort map appears below.

---

## 0. Verdict

**Build after fixes, with cuts.** The core moves are right: rooms attach at
code-issued portals so access is correct by construction, corridors are
routed by code from named ends, the model reads a graph in words, and every
apply is read back. But four things block building as written, and about a
third of the machinery (a DF-faithful path simulator, unit-path validation,
a separate variant record kind with five gates and a Board review) buys
precision nobody consumes, since the design's own D7 makes every walk
metric report-only.

**Blockers (fix before the stage named):**

1. **Districts have no boundary** (before C1). The Planner's districts are an
   anchor landmark plus a relative level (`below|same|above`) [verified,
   Planner design revision 1 in `ac75b05`, kept "unchanged in shape" in
   revision 2]. The design's throats "at each district boundary", district
   membership of a portal (N-1), portals per district (N-4) and X-pair
   separation (3.7) all need a spatial extent that does not exist.
2. **The hands are single-level rectangles** (before C4). Reservations are
   one-z rectangles [verified, `df-overseer-reservations.lua` header and
   `rect_tiles(x, y, z, w, h)`]; the blueprint verb's site is one z and every
   read uses `site.z` [verified]; its CSV parser treats a `#>` line as an
   empty grid row of the current section [verified,
   `df-overseer-blueprint-parse.lua` `parse_sections`: `^#(%a+)` does not
   match `#>`, and a cell starting `#` ends the row], so a multi-level
   blueprint would be read as one tall single-level footprint and every
   read-back, reservation and finish check would be wrong. And the portal
   attachment itself is refused by today's overlap rule (finding B2b).
3. **Generated blueprints have no route to the game** (before C4). The verb
   loads a named CSV from `dfhack-config/blueprints/` on the guest, put there
   by a deploy step [verified, verb header "WHERE THE BLUEPRINT FILE COMES
   FROM"]. A routed corridor is unique per project; the design never says how
   its generated file reaches the guest at run time.
4. **The tile window as defined can freeze the fort** (before C1, the first
   live stage). "The union of walkable groups that contain our landmarks"
   includes the surface group (and any breached cavern), whose extent spans
   the whole map width across many levels; and finding a group's members
   needs the very full-map scan that hung DF for nine minutes (I17).

**Changes to D1 to D13:** disagree with D3 (cut), D9 (defer), D11 (not
needed once length validation is cut); change D6 (2 wide is the default
spine at this population), D12 (retrofit right after C1 with narrow hands,
not after the generator stack); conditions on D4 and D5. Agree with D1, D2,
D7, D8, D10, D13. Table in section 6.

---

## 1. Findings ranked by severity

### Blockers

**B1. District boundaries are undefined, so throats, membership and X
separation cannot be computed.** [verified for the Planner shape; inferred
consequence]
- Evidence: Planner revision 1 `districts:` entries are `{name, kind,
  purpose, anchor: "<landmark>", level: below|same|above}`; revision 2 says
  "unchanged in shape". The Planner's own P2 binding is a table stamped from
  the proposal's `district` field at `blueprint.reserve`, not a geometry.
- Effect: 3.5 (throat per boundary), N-1, N-4, 3.7 step 2 (X pairs "separated
  by at least a throat") and the C6 "throats" item have nothing to evaluate.
  A code-invented boundary (nearest anchor) would quietly become plan policy
  the Planner never wrote.
- Fix: before C1, choose one of: (a) membership is only the binding table
  (a room belongs to the district its proposal named), and a throat is placed
  where a collector leaves the spine, not at a "boundary"; or (b) the Planner
  design grows a membership rule (nearest anchor by graph walk within the
  level band), decided by the user as a Planner change. Recommend (a): it
  needs no new Planner concept and is checkable today.

**B2. Reservations and the blueprint verb are single-level rectangles; portal
attachment is refused by the overlap rule.** [verified]
- (a) Single level: reservations store `(x, y, z, w, h)`; the verb's site,
  reads and quickfort call (`-c x,y,z`) use one z; the parser folds `#>`
  levels into one footprint. Routed corridors are L-shaped or longer than
  any sensible rectangle; stair columns and `room-stack` span levels. The
  design (11) says "the blueprint verb's read-back covers every level (P-1)"
  as if it already did.
- (b) Overlap rule: two reservations may overlap **only on tiles both
  classify as wall** [verified, reservations header "SHARED-WALL OVERLAP"].
  `bedroom-cell-v1` puts its entrance gap in its own ring, row 5 [verified,
  CSV and YAML]. A room hung on a corridor therefore has its carve tile on
  the corridor's side-wall row. If the corridor reserves its side walls
  (it must, or piles and rooms can eat them, R-2), the room's reserve is
  refused; if it does not, nothing protects the corridor's edge.
- Fix: before C4, (1) reservations become tile sets with z (or lists of
  per-level rectangles) and a third tile class `portal` that one room carve
  may take; (2) the verb refuses `#>`/`#<` and multi-level metas explicitly
  until multi-level reads exist, rather than silently mis-reading them;
  (3) until then, levels are joined by the existing `diggable.dig-stair`
  pair, which is already live and in the `rooms` group [verified,
  `dfqueue/action_tools.yaml`]. Multi-level blueprints become a later stage.

**B3. No runtime path for generated blueprints to reach quickfort.**
[verified for today's path; inferred gap]
- The verb resolves `NAME` to a deployed CSV; deploys go only through
  `scripts/deploy.py` (Working.md rule). A generator output per corridor
  project cannot ride a deploy.
- Fix, choose one: (a) apply generated content through
  `quickfort.apply_blueprint{mode=..., data=data[z][y][x], pos=...}`,
  which takes a sparse multi-level map natively [verified, installed
  `docs/tools/quickfort.txt` API section]. This also removes the need for
  `#>` text at all, and keeps coordinates Lua-side. (b) dfmcp writes
  `dfhack-config/blueprints/generated/<hash>.csv` and the step carries the
  hash. (a) is cleaner; note the API has no preview tiles (`p.preview =
  false` [verified, `api.lua`]), only stats and `dry_run`.

**B4. The bounded window is neither bounded nor cheap.** [inferred, from
verified numbers]
- The map is 6,856,704 tiles [verified, flood research §2]. The surface
  walkable group spans the full map width across every level the terrain
  crosses; a breached cavern merges a cavern layer into the fort's group.
  Either blows through the proposed 200,000-tile cap, and computing "the
  union of groups" means visiting tiles to learn their group, which is the
  full scan of I17. Shipping 200,000 tiles of rows from Lua to Python also
  runs into the "unbounded scans wedged the pipe" class (catalogue P-7).
- Fix: the window is the bounding box of **our own records** (sites,
  reservations, underground landmarks, planned corridors) per level in use,
  plus a small margin, with a hard cap that refuses rather than truncates,
  read per level with yields, timed first on the paused fort with an abort.
  Surface walkways (D10) get their own narrow read, not the fort window.
  Consider running the router in Lua over that window and returning words,
  so tile rows never cross the pipe.

### Major

**M1. Missing FMEA rows: the game's own damp and warm dig cancellation, and
aquifers.** [verified: `DIG_CANCEL_DAMP` and `DIG_CANCEL_WARM` are in this
version's announcement enum, `research/data/2026-09-23-announcement-types.tsv`;
quickfort's API takes `marker {warm, damp}` defaulting false, installed
quickfort docs; prior: wiki Aquifer (v53.16) "the aquifer tile will be
revealed as damp soil or stone and the dig designation cancelled for that
tile", heavy aquifers "effectively halting excavation"]
- A routed corridor through hidden rock near an aquifer or magma will have
  digs cancelled by the game. The design's stall detector reads that as
  `stalled` and its recovery is "release" or a stranding diagnosis (D-1),
  which is the wrong cause. The planned-tile model (8.2) has no aquifer field.
- Good news, in the spirit of "set intent, let the game execute": the game
  already stops the dangerous dig. The design should rely on that, never set
  the `damp`/`warm` markers, and read the cancellation reason.
- Fix: new rows W-6 (dig cancelled as damp or warm: detect from the
  announcement or report, recover by re-routing, prevent by never setting
  the markers) and W-7 (corridor dug through a light aquifer that seeps:
  detect liquid on circulation tiles, recover by walling). Add aquifer to
  the model **only for revealed tiles** (`dfhack.maps.isTileAquifer` exists
  [verified, Lua API doc]); on hidden tiles it is game-hidden information and
  banned by the no-armok rule.

**M2. Missing row: a corridor that breaks out to the surface or into open
space creates an unplanned fort entrance.** [inferred]
- The router costs hidden tiles at 1 plus a risk count and visible liquid at
  infinity, but says nothing about tiles adjacent to visible open air,
  a hillside face, or a revealed cavern. Digging one tile beside such space
  joins the fort to it: a second entrance for invaders and wildlife, and an
  `outside` change for any room beside it. Defence is the Overseer's, but
  making an entrance by accident is the Architect's failure.
- Fix: row G-9; the router refuses (infinite cost) any tile orthogonally
  adjacent to visible open space that is not the requested walkway end, and
  reports "would open onto the surface/cavern" as a named refusal.

**M3. The seal check protects named places, not whoever is standing in the
pocket.** [inferred; the "walled in" class is common player knowledge,
unverified for v53 since the wiki Construction page fetched this session
says nothing about builder position or occupied sites]
- S-1 and 4.3 refuse closures that cut a room, unit, item or exposed ore off.
  A closure that creates a walkable pocket containing nothing named (a stub
  corridor end, the far side of a closed old opening) passes, and the
  builder, or a hauler passing through, can be inside it when the wall
  completes. S-5's unit check runs at designation time; the wall is built
  later.
- Also: today's closure hand cannot target one tile. `construction.build`
  takes `ZONE_ID KIND` and walls ring tiles it infers were mined from "is
  open" [verified, TOOLS.yaml signature; catalogue S-6 code read]; run on a
  bedroom during the retrofit it would wall the new entrance too.
- Fix: the seal invariant becomes "after this closure, every walkable tile
  that was connected to the hub stays connected", with zero exceptions, so
  any pocket refuses. Closures go through a generated `#build` with explicit
  tiles (B3 route), not `construction.build`. Check the live walkable group
  just before the closure lands (see M5), not at filing.

**M4. Two implementations of quickfort's geometry.** [inferred, from the
design's 8.2 plus verified history]
- 8.2 applies every pending blueprint "virtually" in Python. That needs a
  Python copy of the anchor rule, the four transforms, and quickfort's
  per-symbol rules (`i` on open floor gives down only; digs under buildings
  silently skipped [verified, `dig.lua` occupancy branch]). G-1 (I1) and G-2
  (I23) were exactly this math being wrong in one tool. Two copies drift.
- Fix: one source of truth. Either the Lua verb expands a step into its
  tile set (internal-only) and the planned model consumes that, or the
  pending-proposal model is dropped in favour of reservations (M5).

**M5. Over-engineering: the DF-faithful simulator and its validation buy
nothing the design consumes.** [inferred]
- What needs a tile search: **routing a corridor** (where to dig) and
  **existence** (will this be connected). What does not: DF path cost
  (traffic sums), diagonal and stair travel factors, unit-path length
  sampling, timed walks (8.3 costs, 8.5 items 2 and 3, D11). Every walk
  number is report-only under the design's own D7, and the thresholds are
  invented (3.2). Calibrating them to 10 percent is precision for a metric
  that refuses nothing.
- Answer to the brief's question "pre-dig pathfinder vs dig, then check
  with the game's walkable groups before sealing": **both, split by
  reversibility.** Digging is cheap to leave and the access mistakes it can
  make are prevented by portal attachment and the existing entrance gate.
  Sealing is the irreversible step. So: a small router (BFS/A* over dig
  cost on the window, existence only) before digging; and before every
  closure, the game's own `getWalkableGroup` on the live tiles, which is
  authoritative. Caveat: DFHack documents that this cache "is only updated
  when the game is unpaused, and thus can get out of date if doors are
  forbidden or unforbidden" [verified, Lua API doc], so the pre-closure check
  must follow an unpaused window after the last dig or door change.
- Also replace "check against all pending proposals in a virtual model"
  (G-7) with what exists: a filed proposal holds a reservation (or a
  pending-reservation record), and overlap is a reservation conflict. That
  removes the virtual model's main reason to exist.
- Cut: 8.5 items 2 and 3, the `df_cost` output, D11, success criterion 3's
  length half. Keep: 8.5 item 1 (existence vs walkable groups).

**M6. The variant machinery and stage order delay the user-visible fix.**
[inferred]
- C0 to C4 (data, graph, simulator, filing guards, five generators, a new
  `template_variant` record kind, lint, synthetic simulation, Board review)
  all precede the bedroom retrofit (C5), the one problem the user actually
  caught. Meanwhile the rooms are still bedless: BED stock 0, one planned
  Bed waiting [verified, `Working.md` fort line; `evals/live/2026-10-07-stuck-bed`],
  so closing old openings now risks no beds or sleepers' furniture and is
  the cheapest it will ever be.
- Cut and reorder: variant parameters ride inline in the room or corridor
  step (schema-checked, V1 to V4 still run in code); a named variant record
  only when a parameter set is reused. Order: C0, C1 (graph and diagnosis),
  then the retrofit with a corridor-run generator plus explicit-tile closures
  and the pre-closure walkable check, then filing guards, then `room-row`,
  then the rest. Workshop bays (C6) wait for Logistics stage L and a real
  workshop need.

**M7. Interfaces: doors and closures have no hand in the `rooms` group.**
[verified]
- `rooms` group tools: reserve, apply, release, unreserve, `zone.place`,
  `zone.assign-owner`, `building.build`, `diggable.dig-stair`, the two
  `mine-vein` tools [verified, `dfqueue/action_tools.yaml`]. No
  `construction.build`, no `construction.door`.
- `construction.door ZONE_ID` places a door at **every** entrance of a zone,
  needs a zone (throats and corridors have none), is Overseer-only and has
  never run against a real DFHack [verified, TOOLS.yaml entry: "Never run
  against a real DFHack process"].
- Fix: doors and closure walls are `#build` cells (`d`, `Cw`) in the
  generated blueprint, applied by the verb as a later phase, with buildingplan
  supplying material. One hand, already in the group, already read back.

**M8. Races and identity: portals and pending work.** [inferred, plus
verified step identity]
- Portals on a *planned* corridor dangle if the corridor is rejected,
  released or re-routed; a room accepted at that portal then strands
  (the very D-1 class). Portal lifecycle (issue, expire, invalidate) is
  unspecified.
- `requires` orders steps inside a project (D-3); a corridor and a room in
  **different** projects accepted in one cycle have no ordering edge.
- `dfqueue/step_identity.yaml` lists `blueprint.apply: [site, phase]` but no
  `blueprint.reserve` [verified, file read]; with portals, two rooms for one
  need at two portals are two distinct actions. The design names this (R-5)
  but leaves it partial.
- Fix: portals issued only on accepted and reserved corridors; a room step
  naming a portal gets an automatic cross-project `requires` on that
  corridor's dig step; add `blueprint.reserve: [template, site]` to
  step identity now, and the same-need count by `serves` (Planner F-6).

**M9. Measurability: several criteria grade the design with itself, and
some lack a baseline.** [inferred]
- Criterion 1 (0 pass-throughs) is measured by the new graph. Cross-check it
  with an independent read: `surface.enclosure` gaps per bedroom zone and
  whether the tile beyond each gap is inside another zone.
- Criterion 4 compares a simulator prediction with a simulator measurement.
  With M5's cuts it goes; if kept, measure with something else.
- Criterion 2 ("next 20 room or corridor proposals") has no time bound; at
  hand-run `--once` cadence that may take months. Use a window (N cycles or
  a game season) and report the count reached.
- Criterion 6 needs transcripts, whose capture was only dispatched
  2026-10-07 [verified, register]; there is no baseline yet.
- Missing: the user's actual worry. Count **geometry or circulation
  problems found by the user versus by code** per period, starting from the
  catalogue's history as baseline (the catalogue says user catches dominate).
  Also time each graph build on the paused fort (B4).

**M10. The design adds tools to the Architect against a standing decision
to cut them.** [verified, register 2026-10-07 "Cut every role's tools hard"]
- C1 to C4 add `circulation.graph`, `circulation.route`,
  `circulation.check-plan`, `template.lint`, `template.preview`.
- Fix: `check-plan` and lint run server-side at filing and are never agent
  tools; give the Architect `circulation.graph` (and `route` only if the
  model genuinely needs to ask "what would this corridor cost" before filing,
  which the filing dry run already answers).

### Minor

- **W-4 is over-weighted.** Wiki Cave-in (v53.16): "Any disconnected
  construction or section of rock or soil will cave in" [prior, fetched];
  digging rooms and corridors in solid rock leaves everything connected.
  With no channels or ramps emitted (W-5) and no support removal, the
  "research owed before any retrofit" gate can drop; keep a rule: never
  channel, never deconstruct a construction that carries anything.
- **Traffic needs its own section and confuses the stats.** A quickfort cell
  holds one key, so `d` and `oh` on one tile need two `#dig` sections; and
  traffic tiles increment the same `dig_designated` counter as digs
  [verified, `dig.lua` loop]. The verb's `assess` would count traffic as
  designated digs. Also, in a tree-shaped fort with no alternative routes,
  traffic cost changes no path. See D9.
- **Workshop blocking tiles are not in `building.list-kinds`.** It reports
  footprint size and the token only [verified, TOOLS.yaml summary]. For
  built-in workshops the impassable pattern is not exposed pre-build
  [unverified where DF holds it]. Read occupancy after the first build of a
  kind and store it as data, or leave a free aisle the full width.
- **Ore at infinite route cost is backwards for corridors.** Digging through
  ore yields ore; the loss case is smoothing ore in a *wall*. Charge ore
  normally on the corridor's own tiles and report ore left exposed on its
  side walls (the existing `ore_exposed` path).
- **Boulders.** Digging stone leaves boulders; an item on a door tile props
  it open (W-3) [prior, wiki Door via `room-layout` Q4], so a freshly dug
  throat's door is likely propped. Natural boulders, traps and tracks block
  wagons [prior, wiki Trade depot].
- **Wagon check details.** The game shows no wagon-accessibility indicator
  [prior, wiki Trade depot: "There is no visual indicator of wagon
  accessibility"], so a code check is justified; add the 3 by 4 parking space
  beside the depot and the blockers above.
- **Stair columns through intermediate rooms.** A column passing a room on
  a middle level makes a vertical pass-through; the router's infinite
  interior cost must apply on every level the column crosses.
- **Trees grow.** Surface walkway edges go stale as saplings mature; re-check
  on graph rebuild, not once.
- **The Planner's own example anchor has an apostrophe** ("Carpenter's
  Workshop", revision 1) [verified]: L-3 bites the Planner too. Handles, not
  names, in district anchors.
- **Access table disagreement.** Planner revision 1 says Office
  `opens_onto: any`; this design says `corridor` [verified both]. D2 should
  settle the value, not only the owner.
- **Multi-level syntax is present on this install** (`#>`, `#<`,
  `repeat(down N)` in the installed user guide and `parse.lua`) [verified on
  r2]; very likely on r1.1 too since multi-z is an old feature [inferred].
  The API's `data[z]` map (B3) makes it unnecessary for generated content.
- **Unit paths and armok** (D11): vanilla shows where a dwarf is, not its
  planned route [inferred, unverified for v53's UI]; moot once cut (M5).

---

## 2. FMEA rows whose "prevented by construction" claim does not hold

| Row | Claim | Why it fails | Fix |
|---|---|---|---|
| A-1 | C: rooms at portals open onto circulation | holds only while the portal's corridor exists; a portal on a planned corridor that is later rejected or re-routed strands the room; legacy rooms are outside it | portals only on accepted, reserved corridors; cross-project `requires` (M8) |
| A-5 | C: furniture never on the approach; blocking tiles from game data | the game data read named does not report blocking tiles (minor above) | data per kind from a post-build occupancy read |
| S-4 | C: retrofit opens new before closing old | ordering is right, but "reachable" is checked on the planned graph; the closing step needs a live walkable-group check after an unpaused window (M5 caveat) | X check on live groups before each closure |
| S-6 | C: wall targets from template edges | true for generated blueprints, false for the only closure hand that exists today (`construction.build` infers from "is open") | closures only via explicit-tile `#build` (M3, M7) |
| V-2 | C: generator picks the stair symbol from the tile's shape | makes generation depend on live tile state, so it is not a pure parameter function and V4's synthetic rock cannot test it | generate at apply time Lua-side; keep `diggable.dig-stair` until then |
| V-6 | C: `stair-column` always emits the pair | blocked on B2 (multi-level hands) | as B2 |
| G-1, G-2 | C: one shared anchor and transform function | the design adds a second one in Python (M4) | one source of truth |
| R-2 | C: corridors reserved as `circulation` | reservation model cannot hold a non-rectangular, multi-level corridor, and the overlap rule blocks portals (B2) | tile-set reservations with a `portal` class |
| P-7 | C: bounded window | the window definition is not bounded (B4) | records-based window, hard cap |
| T-6 | C: no fort token in text | holds for parameters; generated files written to the guest (B3) are new text no lint sees unless the generator runs the lint on every output | lint every generated output, not only the variant |

Counts in 2.2 (92 rows) re-counted: 8+9+7+4+7+5+6+6+8+4+10+9+4+5 = 92
[verified]. The split into 47 C / 33 F-X / 12 detect was not re-derived.

---

## 3. FMEA gaps (rows to add)

| New row | Mode | Prevent / detect | Basis |
|---|---|---|---|
| W-6 | dig cancelled by the game as damp or warm | rely on it; never set markers; read the cancellation reason; re-route | verified enum and API; prior wiki Aquifer |
| W-7 | corridor through a light aquifer seeps water onto circulation | liquid on circulation tiles as a graph flag; wall off | prior wiki Aquifer |
| G-9 | corridor breaks out to the surface or a revealed cavern | router refuses tiles beside visible open space | inferred |
| S-8 | closure leaves an unnamed walkable pocket with a unit inside | seal invariant over all hub-connected tiles | inferred |
| S-9 | closure checked at filing, built later after units moved | live walkable check just before the closure phase | inferred, verified cache caveat |
| R-7 | dangling portal after its corridor is rejected or released | portal lifecycle tied to the corridor reservation | inferred |
| R-8 | room and corridor in different projects execute out of order | automatic cross-project `requires` | inferred |
| P-11 | walkable-group read stale after a paused door or dig change | read only after an unpaused window | verified Lua API doc |
| T-9 | generated blueprint differs from what was ruled (regenerated against changed tiles) | step carries the generated content hash; apply refuses a mismatch | inferred |
| V-8 | stair column crosses a room on a middle level | per-level interior cost | inferred |
| Q-6 | depot not wagon-accessible (trees, natural boulders, tracks, no 3 by 4 parking) | wagon check including parking | prior wiki Trade depot |

Considered and judged not needing rows: cave-in from ordinary digging (wiki
v53.16 rule above); forbidden doors by default (doors are not forbidden when
built, as far as any source says; Q-4's read-back already covers it);
pet passability through doors [unverified, low stakes]; magma beyond W-1 and
the game's warm cancel.

---

## 4. Feasibility notes

- **Reads the design assumes:** `getWalkableGroup` and `canWalkBetween` exist
  [verified, Lua API doc]; `isTileAquifer` exists [verified]; the tri-state
  helper exists [verified per register]; door state read, support read and
  unit-path read do not exist (as the design says). Workshop blocking tiles:
  not exposed by our tools (above).
- **Bounded read performance:** unmeasured anywhere; B4.
- **Quickfort multi-level on 53.16:** syntax present on r2 [verified]; our
  verb cannot use it (B2); the API `data[z]` route avoids the syntax (B3).
- **Generator correctness:** the byte-for-byte fixture test against
  `bedroom-cell-v1` and `office-room-v2` is a good first test; note
  `bedroom-cell-v1` resolves every ring tile as `s` and documents that seam
  tiles opened by a neighbour need `Cw` instead [verified, its YAML
  `walls.resolution`], so `room-row` cannot reproduce N copies of v1 and
  must resolve seams per tile at apply time (same live-state dependency as
  V-2).
- **Coordinates and the model:** the router design keeps paths code-side and
  answers in words, consistent with commitment 1. The one leak risk is the
  generated file (B3 option b) and its notes; option (a) keeps everything
  Lua-side. `chokepoints.find` is coordinate-bearing by design and must stay
  off the Architect's list, as the design says.

---

## 5. Interfaces and races, summary

- Planner districts: B1. Planner `access` (P4) vs Architect access data:
  D2, plus the Office value disagreement.
- Logistics `pile_spec`: bays wait for stage L (D4); the default spec should
  be explicitly inert in the plan (flagged, not counted as Logistics' answer).
- Overseer rulings: throats are door-ready only, so lockdown stays the
  Overseer's; good. Doors on bedrooms are the user's standard, not defence;
  good.
- Conductor execution groups: M7.
- Reservations: B2.
- Duplicate detection: M8.
- Roles racing: the Planner revising districts mid-season while the
  Architect files rooms is already governed by the binding table and
  `plan_change` rulings (Planner design); the design adds no new race there
  once B1 option (a) is taken.

---

## 6. D1 to D13

| D | Design's recommendation | Red team | Reason |
|---|---|---|---|
| D1 | parameters only | **agree** | grids by the model repeat T-1 to T-8; tell the user plainly that "the Architect designs blueprints" becomes "the Architect parameterises generators humans write", and let it file a *request for a new generator* as a note |
| D2 | Architect owns access per kind, Planner overrides | **agree**, and settle the Office value (any vs corridor) in the same ruling | access is circulation geometry |
| D3 | Board shows a first-use parameter value | **disagree: cut** | parameter values already come from closed vocabularies a human wrote; the human gate is the vocabulary edit |
| D4 | parametric workshop bay | **agree in shape, defer the build** until Logistics stage L and a real workshop need | a default pile spec builds the wrong bay confidently |
| D5 | bedroom doors by default | **agree with conditions** | door is a separate later phase that never gates the room's `provides`; placed as a `#build` cell (M7); its item reaches the Quartermaster through derived inputs, since the fort has never made a bed (I12) |
| D6 | width classes 1/2/3 by load | **change** | keep the classes, but 2 wide is the default spine at about 24 dwarves with one pick (M-6); 3 wide only for the depot/wagon route; revisit with measurement |
| D7 | report only, refuse private pass-through | **agree** | |
| D8 | second stair column flagged, Planner decides | **agree** | |
| D9 | `oh` on spines and collectors | **defer** | no loops yet, so traffic changes no path; costs a second `#dig` section and confuses the verb's counters (minor above) |
| D10 | wagon check and entrance throat only | **agree**, add 3 by 4 parking and the blockers | wiki Trade depot |
| D11 | read unit paths for validation | **not needed** | cut length validation (M5); if ever revived, the planned path is not shown to a player [inferred], so ask the user then |
| D12 | retrofit the bedroom block as C5 | **agree to retrofit, change the timing** | do it right after C1 with a corridor generator, explicit-tile closures and the live pre-closure check, while rooms are still bedless (M6) |
| D13 | every user catch becomes a check plus regression case | **agree** | record as a register rule; where a catch is not code-checkable, a doctrine non-rule instead |

---

## 7. What could not be verified

- Builder position and occupied-site behaviour for constructions: the wiki
  Construction page (fetched) is silent; S-8/S-9 rest on inference.
- Whether built-in workshop blocking patterns are exposed anywhere in
  DFHack: not searched in df-structures (not installed locally as XML).
- Behaviour on 53.16-r1.1 specifically: sources read here are r2.
- Tile-read cost on the live fort: no VM access by brief.
- The 47/33/12 control split in design 2.2: not re-derived row by row.
- Whether DF's walkable groups treat deep water as walkable: not checked.

## 8. Sources

Repo: the design under review; `research/2026-10-08-architect-failure-catalogue.md`
(Part 1); `research/2026-10-07-planner-design.md` (revision 2, and revision 1
via `git show ac75b05`); `research/2026-09-17-stairs.md`;
`research/2026-09-24-quickfort-hands.md` (section index);
`agents/architect/role.md`; `dfqueue/step_identity.yaml`;
`dfqueue/action_tools.yaml`; `dfqueue/schema.py` (`ARCHITECT_TYPES`);
`scripts/dfhack/df-overseer-blueprint.lua` (header, `run_quickfort`, z use);
`scripts/dfhack/df-overseer-blueprint-parse.lua`;
`scripts/dfhack/df-overseer-reservations.lua` (header, functions);
`scripts/dfhack/TOOLS.yaml` (construction commands, `door`, `list-kinds`);
`blueprints/templates/bedroom-cell-v1.csv` and `.yaml`;
`decisions/DECISIONS.md` rows 2026-10-06 to 2026-10-08; `Working.md` fort
line; `evals/live/2026-10-07-stuck-bed/README.md`;
`research/data/2026-09-23-announcement-types.tsv`.

Installed DFHack (local, 53.16-r2): `hack/scripts/internal/quickfort/dig.lua`
(traffic actions, occupancy skip, `dig_designated` counter), `parse.lua` and
`command.lua` (`repeat`), `api.lua` (`preview = false`);
`hack/docs/docs/guides/quickfort-user-guide.txt` (`#>`, `#<`, `repeat`);
`hack/docs/docs/tools/quickfort.txt` (API `data[z][y][x]`, markers);
`hack/docs/docs/dev/Lua API.txt` (`getWalkableGroup` cache note,
`isTileAquifer`).

Web, fetched this session: DF wiki Cave-in (v53.16), Aquifer (v53.16),
Trade depot, Construction.
