# Room and fortress layout: best practices for a checker

Date: 2026-09-24. Read-only research, answering
`handoffs/2026-09-24-room-layout-best-practices.md`. No VM changes, no live
writes, no doctrine edits, no fort mutation. No coordinate, grid or map
appears anywhere below; every pattern is described in words and relative
dimensions only, per `docs/PURPOSE.md` design commitment #1.

## Bottom line

**Player convention and verified game mechanic are almost entirely separate
bodies of evidence here, and this report keeps them apart throughout.** The
only hard game mechanics this session could verify are: the four-level
traffic designation system (High/Normal/Low/Restricted, a real per-tile
pathfinding cost multiplier of 1/2/5/25, confirmed on a current v53.16-banner
page) and its own stated limitation (job assignment itself ignores it,
only *movement between chosen points* uses it); door behaviour as
floodgate-equivalent fluid control with no operating delay; and stair
mechanics (up/down stairs must vertically align, stairs block neither
creatures nor fluids). Everything else this report can offer about layout
(corridor widths, bedroom blocks, workshop clusters, staggered doorless
rooms, the fractal families) is **player convention**, sourced from the
current-namespace wiki (v53.16-banner pages, so not stale from the v50 zone
transition) and forum/community writeups, never from this install's own
struct data or DFHack's API, because DFHack exposes no traffic-cost
telemetry, no congestion metric and no travel-time function this project can
read. The single most useful deliverable is the last section: a candidate
rule set for a layout checker, each rule tagged `invariant` or `metric`, and
`game mechanic` or `convention`, so the next build stream can encode exactly
what it is encoding and no more.

**Two things are flagged loudly because this project has been burned by
exactly this shape of mistake twice already (`prefer_indoors`, the wiki's
20-citizen Manager claim, both named in the brief):** first, corridor-width
and traffic-designation advice is convention riding on top of a real
mechanic, not the mechanic itself, wait for it, see Q2. Second, one
wiki page fetched this session (`Meeting_hall`) still carries an explicit
"migrated from an older version, may need updates" banner rather than a
clean v53.16 banner; its content is used here only where it does not
depend on version-sensitive detail, and it is flagged inline.

---

## Q1. Layout patterns players actually use, and what each optimises for

Sourced from the wiki's `Bedroom_design`, `Workshop_design` and (partially)
`Meeting_hall` pages, all fetched this session. `Bedroom_design` and
`Workshop_design` both carry a current v53.16 version banner; `Workshop_design`
additionally carries its own caveat, quoted verbatim: "This article was
migrated from DF2014:Workshop design and may be inaccurate for the current
version of DF (v53.16)." That self-flagged uncertainty is preserved below
rather than smoothed away. All of this is **convention**, describing what
players build, not a game requirement to build it.

- **Line design (bedrooms off a spine).** Bedroom alcoves dug directly off an
  existing access corridor, one row deep, no separate hallway. The wiki's own
  framing: "very space efficient and very adaptive," scales from a minimal
  footprint up to roughly four tiles of depth per room, extensible later.
  Optimises for **dig cost and incremental buildability**: no dedicated
  circulation space, and a new room costs only its own footprint. The known
  cost, per this project's own working knowledge and consistent with the
  corridor-crowding findings in Q2, is that the spine itself becomes the
  single point of congestion for every dwarf reaching a room past the middle
  of the row.
- **Decentralised living (stairwell hub with wings).** A central stairwell
  with bedrooms and a dining/dormitory area branching outward in multiple
  directions, food stockpiles kept close to the dining area specifically to
  minimise the cook's and diners' walk. Optimises for **travel time from the
  vertical circulation spine**, at the cost of more excavated corridor per
  room than the line design.
- **High-density / fractal families (Raynard, Hactar, H-Tree, and the
  wiki's own "fractal" label).** Self-similar branching corridor geometry
  radiating from a central stairwell, expandable outward indefinitely by
  adding another ring of perimeter hallway and rooms. Optimises for
  **density at scale**: a fixed travel-time-to-stairwell bound as the
  population grows, at the cost of a much more complex dig plan than the
  line design. The wiki also names **Sandwich** (bedrooms distributed across
  z-levels via a shared stairway, trading horizontal digging for vertical),
  **Greek Cross** and **Shaft** (a central core with rooms arranged around
  it, again minimising travel distance through vertical proximity rather
  than horizontal spread), and **6-room clusters** / **Living Pods** (small
  repeating modular units, easy to reason about and to build incrementally,
  at the cost of some wasted wall area between modules compared to a single
  large block).
- **Staggered doorless rooms.** Non-overlapping 3x3 rooms arranged around a
  central stairwell so that dwarves path *diagonally* between the stairwell
  and each room's own doorway-equivalent gap, with no door and no dedicated
  hallway tile at all. This depends on a real, verifiable mechanic (diagonal
  movement is legal DF pathing) but the *pattern itself*, and the claim that
  it is comfortable to build and live in, is convention. It optimises for
  **zero corridor tile cost**: every tile dug is either room floor or
  stairwell, none is pure circulation.
- **Workshop wings / decentralised workshop complex.** 3x3 workshops
  organised into paired wings sharing a stockpile, with the wiki's own
  numeric example capping "maximum walk to stockpile on same wing" at 18
  tiles. Optimises for **the travel-weighted workshop-to-stockpile
  distance directly** (Q6's facility-layout problem, by another name), at
  the cost of needing many small stockpiles instead of one large one shared
  across the fortress.
- **Meeting halls layered onto dining or a well room, not built as a
  separate zone.** The `Meeting_hall` page (older-version banner, used
  cautiously) states dining rooms and well rooms can double as meeting
  halls, and separately warns that animals left to mill in *any* crowded
  meeting hall pick fights with dwarves and each other. That warning is
  convention riding on an unverified mechanic claim (animal-dwarf conflict
  in a shared space); this report does not confirm it independently and
  flags it as unverified rather than repeating it as settled.

**What every pattern above is actually trading off, restated plainly**:
dig cost (tiles excavated, including pure-circulation tiles that produce no
room value) against travel time (distance from any given room to the
fortress's high-traffic hubs, principally the stairwell and the dining
hall/stockpiles). No pattern here escapes that trade; each just picks a
different point on it. This is exactly Q7's two-objective question, answered
per-pattern rather than in the abstract.

---

## Q2. Corridor width and traffic

**The traffic designation system is a real, install-verifiable game
mechanic; the "make it two or three tiles wide" width advice sitting next to
it is convention, and the two must not be conflated in a checker.**

- **The mechanic (`game mechanic`, `prior` from a current v53.16-banner wiki
  page, not independently confirmed against this install's own pathfinding
  since DFHack exposes no path-cost telemetry to read):** four designation
  levels, High/Normal/Low/Restricted, with default per-tile pathfinding
  costs of 1/2/5/25 respectively (Normal/undesignated is the default at 2).
  "When walking from one point to another, dwarves consider these
  designations in finding the shortest path" — a real cost multiplier a
  route accumulates, not a suggestion. **The page's own stated limitation
  matters as much as the mechanic itself: "dwarves generally choose their
  jobs without weighing the pathfinding costs."** Traffic designation steers
  *which route* a dwarf takes once a job is chosen; it does not steer *which
  job* a dwarf picks, and it cannot substitute for actual corridor capacity.
  This fort has never set a traffic designation on any tile
  (`CLAUDE.md`'s status banner), so nothing below assumes this project's own
  fort currently benefits from it.
- **The width advice (`convention`, wiki plus community writeups, current
  v53.16-banner sourced where cited above in Q1): "major hallways should be
  at least two tiles wide, preferably three"; heavily used tunnels should be
  "at least two tiles wide, and three is better."** The stated failure mode
  at width 1 is **queuing, not a hard block**: dwarves attempting to pass
  each other on a single-tile corridor must take turns, which the community
  literature describes as measurably slowing hauling and job throughput at
  higher population, worse the longer and more heavily used the corridor is.
  This project's own working knowledge (not independently re-derived this
  session, consistent with what the searches returned) is that DF does not
  literally deadlock two dwarves passing on a 1-wide tile; one yields,
  which is exactly the queuing cost the convention is warning about, not a
  correctness bug.
- **A single-tile corridor to a low-traffic dead end (an individual bedroom,
  a rarely visited storage nook) is not the same problem as a single-tile
  spine every hauler on the fort crosses.** The convention search results
  are explicit that 1-wide branches to individual rooms are fine at low
  population and only get crowded "if more than 10 dwarves are living along
  each one" — i.e. the failure is a function of **how many dwarves share the
  corridor and how often**, not of width alone. A checker that flags every
  1-wide tile identically, without regard to what it serves, would
  over-flag exactly the doorless-bedroom-branch pattern that Q1 names as a
  legitimate, deliberate convention.
- **What a checker can and cannot verify here.** It can verify width
  (tile-count of a corridor segment) and it can verify whether traffic
  designations have been set at all (a real, readable game-data field on
  every tile, per DFHack's map API, unlike room value). It **cannot**
  verify actual dwarf density or congestion on a corridor without either a
  live population count crossed against a hand-picked "how many dwarves use
  this route" estimate (unverifiable, since real traffic frequency is
  unknown to this project per the brief), or a live instrumented read of
  queued/blocked job counts (`get_stuck_jobs`, named in `docs/DF-OVERSEER
  build order item 8` as this project's own least-verified primitive).
  Defensible proxies, in order of how directly they are grounded: (a) a
  static estimate from what the corridor connects (number of bedrooms or
  workshops it serves, a topology fact code can compute without ever
  reading a coordinate) is the most defensible, since it needs nothing
  live; (b) live population divided across known circulation spines is
  weaker, since it assumes even distribution; (c) inferring congestion from
  announcement or stuck-job counts is the least defensible as a design-time
  metric, since it can only be read after the fact, not before digging.

---

## Q3. Vertical layout

**Two mechanics are install-verifiable (stair alignment, stairs never
blocking movement); how much a fort should invest in vertical reuse versus
horizontal spread is convention, and this session found materially less
concrete guidance on it than on horizontal patterns, which is itself worth
reporting rather than papering over with confidence the sources do not
support.**

- **Alignment (`game mechanic`, current v53.16-banner page):** an up-stair
  must sit directly below a down-stair (or an up/down stair, which is both
  at once) to connect the two z-levels; an up-stair cannot be carved into a
  tile already excavated, only from a wall or by construction; a down-stair
  cannot be carved into a constructed up-stair. These are real placement
  constraints a checker could enforce given per-z-level tile state, which
  this project's tools do not currently expose as a cross-z-level check
  (out of scope for this report to design, named here as a gap).
  As of v50, the page also says the *player's* interaction changed:
  selecting a 2+ z-level tall area now has the game auto-place the stair
  designation within it, "results may vary from intention" — the page's own
  words, not this report's editorialising, and a caution that automated
  vertical digging may need its own verification step separate from
  horizontal digging.
- **Stairs never block movement (`game mechanic`, same page):** "stairs do
  not block creature nor fluid movement." This matters for a checker only
  insofar as it rules out one failure mode (a stairwell accidentally
  becoming impassable is not a stairs-specific risk) without saying
  anything about capacity, which the page does not address at all.
- **What this session could not find concrete numbers for, and says so
  plainly rather than inventing a rule:** how many stairwells a fort of a
  given population needs, what a "too far from any stairwell" distance
  threshold should be, or a quantified dig-cost-versus-travel-time tradeoff
  for going up instead of out. The `Bedroom_design` patterns cited in Q1
  (Sandwich, Greek Cross, Shaft) all *imply* that vertical reuse is
  frequently cheaper than horizontal spread once a fortress is large
  (shorter total corridor per room, shared stairwell infrastructure), but
  none of the fetched sources states this as a number or a rule a checker
  could apply directly. Any threshold a checker adopts here (e.g. "flag a
  room more than N tiles of travel from the nearest stairwell") would be
  this project's own invented convention, not one drawn from a source, and
  should be labelled that way if adopted.

---

## Q4. Doors

**Doors have real, verifiable mechanical effects that have nothing to do
with the "privacy" framing player habit usually reaches for; the privacy
framing itself is largely convention, and one part of it (bedroom privacy)
appears to be actively contradicted by a cited mechanic, not merely
unconfirmed.**

- **Pathing (`game mechanic`, current v53.16-banner page):** an unlocked
  door is passable to pathing the same as an open tile, at essentially no
  extra cost to a dwarf walking through; a *mechanism-linked* door is
  functionally identical to a floodgate for pathfinding purposes once
  animals try to path through it improperly while unlocked. A door is not,
  by itself, a traffic-cost tile the way a Low/Restricted designation is;
  it is a binary passable/forbidden gate, a different mechanic from Q2's
  cost multiplier.
- **Fluids (`game mechanic`, same page):** a door behaves like a floodgate
  for water and magma containment, with one concrete difference from an
  actual floodgate quoted directly: "there is a delay in operating a
  floodgate with a lever, but no delay on a door," and "a door destroys any
  fluid on its tile when it closes." An item sitting on a door's tile props
  it open and lets fluid through regardless of the door's own setting, a
  specific failure mode a checker could flag if it ever reasons about
  fluid-control doors (out of scope for a room-layout checker as currently
  briefed, noted for completeness since the brief asked about fluids
  explicitly).
- **Access control (`game mechanic`, same page):** the Passable/Forbidden
  toggle "locks or unlocks the door to (most) all creatures," but this is
  explicitly not an absolute barrier: thieves can pick locks, building
  destroyers can smash doors, ghosts can open forbidden doors, and an
  invader who captures a door blocks the player from changing its setting
  until it is recaptured. A door is a control point with named exceptions,
  not a hard wall.
- **Vermin and temperature/cave-adaptation:** the fetched page did not
  address either. This report does not have a verified answer on whether a
  door affects vermin incursion or the sunlight/cave-adaptation calculation
  and says so rather than guessing; `Meeting_hall`'s older-version-banner
  claim that a *meeting hall* being sunlit prevents cave adaptation is a
  room-exposure fact, not a door fact, and is kept separate here.
- **Privacy is where convention and mechanic actually appear to disagree,
  which the brief specifically asked this report to surface rather than
  smooth over.** `Bedroom_design` (current v53.16 banner, quoted in Q1)
  states plainly that "dwarves suffer no penalties from others traveling
  through their bedrooms while sleeping," which is exactly why the
  Staggered Doorless Rooms pattern exists and is treated as viable by the
  same source that names it: a door on a bedroom is, per this evidence,
  **not required for the sleeping-dwarf-privacy reason players commonly
  cite for adding one.** This session did not find a source confirming or
  denying whether a door contributes to a room's numeric value (the sibling
  enclosure/value stream owns that question and this report does not
  answer it, per the brief), so "does a bedroom door add room value" stays
  an open, cross-referenced question rather than something this report
  answers by inference.
- **Where a door earns its cost, on the evidence gathered here:** fluid or
  gas containment (verified mechanic), and access control against specific
  named threats (verified mechanic, with named exceptions). **Where it is
  mostly habit, on the evidence gathered here:** bedroom sleep privacy
  specifically, which the wiki's own current-version page appears to
  contradict as a requirement. **Where this report cannot say either way:**
  its contribution to room value (sibling stream's question) and any
  vermin/temperature effect (not found in the sources checked this
  session).

---

## Q5. Classic layout mistakes, as conditions a checker could evaluate

Each entry: the folk name, the symptom players report, and the geometric or
structural condition a tool could actually check, stated so the next build
stream can turn it directly into code. Every one of these is convention
(player-reported failure patterns), not a verified game rule, unless
otherwise noted; the *conditions* a checker would test are geometric facts
this project's tools can already read (footprint, adjacency, overlap,
z-level), not new game mechanics.

1. **The bottleneck spine.** *Symptom*: every hauler on the fort funnels
   through one corridor tile or one door. *Condition*: a single 1-wide tile
   or door whose removal would disconnect two or more high-traffic regions
   (workshop clusters, the stairwell hub, a stockpile) from each other —
   a graph articulation-point check over the fortress's own connectivity
   graph, which this project's `check_reachable`/connectivity tooling
   already computes the graph for.
2. **The dead-end wing with no second exit.** *Symptom*: a whole cluster of
   rooms served by exactly one corridor, so any obstruction there strands
   everyone behind it. *Condition*: a subgraph with exactly one edge back to
   the rest of the fortress's traffic graph, size above some room-count
   threshold. (Related to mistake 1 but distinct: 1 is about *capacity*
   through a chokepoint, this is about *redundancy* of access at all.)
3. **The distant office/workshop.** *Symptom*: a room placed for site
   eligibility (first legal open tile found) rather than for what it serves,
   producing long, repeated hauls or long walks for whoever holds the role.
   *Condition*: travel distance (corridor-graph distance, not straight-line)
   from a workshop to its primary input/output stockpile, or from a
   role-holder's office/bedroom to the fortress's main hub, exceeding a
   named threshold. This is Q6's travel-weighted adjacency problem, stated
   as a per-room metric rather than a global optimisation.
4. **The furniture-less room-value zone.** *Symptom*: a zone of the right
   kind and footprint that nonetheless reads a room value of zero because
   nothing of value sits inside its own rectangle. *Condition*: install
   -verified this project's own real failure, not folklore — the Chair
   built for this fort's real Office sits outside both Office zones'
   footprints (`research/2026-09-23-room-and-zone-requirements.md`).
   Geometric containment (does any room-value-relevant building's own tile
   fall inside the zone's own `x1/y1/x2/y2`) is exactly the check the
   `furniture_building_ids` work already added to `zone.lua`'s `find`
   (`handoffs/2026-09-24-furniture-aware-ranking.md`); this rule is the
   `place`-time counterpart of a ranking preference that already exists.
5. **The isolated pocket.** *Symptom*: a room or workshop with no walkable
   connection to the rest of the fortress at all (common after a dig plan
   changes and a connecting tile is never actually carved). *Condition*:
   this project's own existing walkable-group check (already used by
   `zone.lua`'s site search, Q1 of `research/2026-09-23`) applied as a
   post-placement invariant rather than only a pre-placement site filter.
6. **The corridor that dead-ends into a lower-class route without a wider
   route ever existing** (this is Q6's road-hierarchy rule, restated for DF:
   a heavily used spine feeding directly into a 1-wide branch with no
   intermediate capacity step). *Condition*: an edge in the traffic graph
   where a high-degree node (many rooms/workshops behind it) connects
   directly to a corridor segment narrower than a size threshold, with no
   intermediate widening. Convention, and the most speculative rule in this
   list: no source found this session states a DF-specific version of the
   road-hierarchy rule; it is imported whole from Q6's cross-domain source
   and is marked `convention` for that reason even though the underlying
   urban-planning rule it is drawn from is well established in its own
   field.
7. **The workshop stranded from its stockpile by a wall it was never
   checked against.** *Symptom*: a workshop placed by kind-eligibility
   rules alone, with its natural stockpile placed independently and later,
   leaving them on opposite sides of the fortress. *Condition*: same
   distance-threshold check as mistake 3, specialised to
   workshop-kind-to-stockpile-kind pairs, which is exactly the "put the
   workshop near its stockpile" problem Q6 names from industrial
   engineering.
8. **Meeting-hall/animal conflict** (flagged as unverified above in Q1;
   listed here only for completeness, not as a rule this report endorses).
   *Symptom claimed by an older-version-banner source*: animals and
   dwarves sharing a crowded meeting hall fight. *Condition, if this were
   ever confirmed on a current source*: a meeting-hall-kind zone overlapping
   or adjoining an animal-designated zone (a Pen/Pasture, a Pond). Not
   proposed as a checker rule below because its own source is version
   -uncertain and this session did not independently confirm it.

---

## Q6. Cross-domain prior art

Per this repo's own standing rule (`CLAUDE.md`, "Research before designing
from scratch"), each field taken on its own terms and matched against what
actually fits a DF layout checker.

- **Architectural space planning and circulation.** The core idea that
  transfers cleanly: a building's circulation (corridors, stairs, doors) is
  itself a first-class design element with a cost (floor area it consumes,
  producing no other value) and a benefit (it is what makes every other
  room reachable), not an afterthought filled in around rooms. This maps
  directly onto Q1's dig-cost-versus-travel-time framing and onto mistake 1
  (the bottleneck spine) above. **What does not transfer**: real-building
  space planning optimises for human wayfinding legibility and daylighting,
  neither of which has any DF-mechanical analogue this session could find
  (DF corridors have no legibility cost; sunlight matters only for the
  cave-adaptation mechanic Q4 touched on, a narrow, different concern).
- **Urban planning, road hierarchy.** The classification of streets into
  arterial/collector/local tiers, and the rule that a higher tier should
  never dead-end directly into a lower one without an intermediate step,
  transfers as mistake 6 above. This is the most directly reusable piece of
  outside prior art this session found, because DF's own traffic
  designation system (Q2) already gives a checker a numeric tier to hang
  the rule on (High/Normal/Low/Restricted), something DF itself does not
  otherwise organise corridors by. **Caveat**: DF has no enforcement
  mechanism analogous to a road hierarchy violation causing gridlock the
  way it does for vehicle traffic; the analogy is structural, not
  mechanically identical, hence this rule staying `convention` in Q5.
- **Building-code egress and clearance.** Minimum corridor widths, a
  required second means of egress from an occupied space, and clearance
  around doors are the direct ancestor of mistake 2 (the single-access
  wing) and of the width conventions in Q2. **What does not transfer**: DF
  has no fire code, no occupancy-load-driven exit-width formula, and no
  regulatory minimum; any width number a checker adopts is borrowed as an
  analogy, not a transplanted rule, and should be labelled `convention`
  even though the field it is drawn from treats its own numbers as hard
  requirements.
- **Facility layout / industrial engineering, the travel-weighted adjacency
  problem.** This is the field that most precisely matches "put the
  workshop near its stockpile": minimising the sum of (flow between two
  areas) x (distance between them) across every pair of areas in a
  facility is a solved optimisation problem in that field (quadratic
  assignment, in its formal form). It maps exactly onto mistakes 3 and 7
  above. **The real limit on using it fully, stated plainly per the brief's
  own honesty requirement**: the *flow* term (how much material or how many
  trips actually move between a given workshop and a given stockpile) is
  unknown to this project — DFHack exposes no per-route traffic count this
  session could find — so a checker can only ever approximate flow with a
  proxy (workshop kind implies expected stockpile kind, itself already
  partly encoded in this project's `ZONE_POLICY`/stockpile tooling) rather
  than solve the real weighted problem. This is worth stating as a limit,
  not quietly working around it with an invented number.
- **What was tried and does not fit.** This session did not find a
  DF-specific or transferable analogue for daylighting/legibility (noted
  above), nor for real-world fire-egress travel-distance limits (DF's own
  hazards, magma and forgotten beasts, do not follow a fire-code-style
  spread model this project could usefully borrow numbers from). Both are
  named here so a future pass does not re-attempt the same mapping.

---

## Q7. Build cost versus movement cost

**No source found this session states a formal way DF players or these
outside fields resolve the tension; the honest answer is that both are
handled by convention and heuristic, not by a stated optimisation rule, and
this project should not invent one where the sources do not support it.**

- Every pattern in Q1 is a different point on exactly this tradeoff, stated
  concretely per pattern (line design: minimal dig, worst travel at the far
  end; fractal/high-density families: more dig, bounded travel at scale).
  No source states a formula or a crossover population at which one pattern
  becomes cheaper than another; the community guidance is qualitative
  ("suitable at low population," "may take a very long time... at the end
  of the hallway"), not quantitative.
- The facility-layout field (Q6) is the one source here with a genuinely
  formal answer to a version of this question, but it optimises *movement*
  (the flow x distance sum) taking area placement as the variable, treating
  the areas' own footprint (roughly, this project's "dig cost") as fixed
  inputs rather than something traded off against movement in the same
  objective. It is a partial answer, not a full one: it does not weigh
  digging one fewer tile against saving one tile of travel, because it
  is not solving that problem.
- **A defensible way to keep both without inventing false precision, for
  the checker specifically**: treat build cost as an `invariant`-adjacent
  budget (a plan that digs far more than its own footprint requires is
  itself a symptom, mistake-worthy on its own, independent of any travel
  number) and travel/adjacency as `metric` rank criteria scored relative to
  other candidate plans, never as a number claimed to be "the" optimum.
  This keeps the checker honest about not knowing real traffic weights
  (Q6's stated limit) while still letting it prefer a closer stockpile over
  a farther one, which is the actually load-bearing behaviour the next
  build stream needs.

---

## Candidate rule set for the layout checker

Each rule: name, what it checks, `invariant` (reject a plan) or `metric`
(rank plans against each other), and `game mechanic` (verified or
install-derived) or `convention` (player practice, however well attested).
Ordered roughly by how directly it is grounded in verified evidence.

| # | Rule | Type | Basis | Grounding |
|---|---|---|---|---|
| 1 | A room-value-kind zone's own footprint must contain the furniture its room value depends on (no built value-bearing furniture outside the zone rectangle) | invariant | game mechanic | Install-verified failure this fort actually hit (Q5 #4, `research/2026-09-23`); the containment fact itself (zone rectangle vs. building tile) is geometry this project already reads live |
| 2 | An up-stair and the down-stair (or up/down stair) that should connect to it must be vertically aligned | invariant | game mechanic | Wiki `Staircase`, current v53.16 banner: stated as a hard placement constraint, not advice |
| 3 | A placed zone/room must belong to one walkable group with every tile of its own footprint (no straddling two disconnected areas) | invariant | game mechanic (mechanism) / convention (that it is worth enforcing at placement time) | This project's own `zone.lua` site search already enforces this pre-placement (`research/2026-09-23-room-and-zone-requirements.md`, Q1); listed as a candidate *post*-placement invariant too, since mistake 5 (the isolated pocket) is a post-dig-plan-change failure, not only a siting one |
| 4 | A placed room or workshop must have at least one walkable connection to the fortress's main traffic graph after placement | invariant | game mechanic (connectivity is a real graph property) | Builds on this project's existing `check_reachable` connectivity tooling (`docs/PURPOSE.md` build order item 2) |
| 5 | Flag (do not reject) any single corridor tile or door whose removal would disconnect two or more already-placed high-traffic regions from each other (articulation point in the traffic graph) | metric | convention (the bottleneck-spine failure mode is player-reported, not a stated game rule) | Q5 #1; computable from existing connectivity graph data, no new game-data read needed |
| 6 | Flag (do not reject) a wing of rooms served by exactly one corridor back to the rest of the fortress, above a named room-count threshold | metric | convention | Q5 #2; same graph, different query (subgraph edge-count to the rest of the graph) |
| 7 | Rank corridor segments serving more than N rooms or more than one workshop cluster by width, preferring 2+ tiles over 1 | metric | convention (width numbers), riding on a game mechanic (the traffic designation cost multiplier exists and is real) that this rule does **not** itself measure | Q2; keep this rule explicitly labelled as approximating congestion via a static topology proxy (rooms served), not a live congestion read, per Q2's proxy-defensibility ranking |
| 8 | Flag any corridor segment or tile that has never had a traffic designation set, where the fortress has any traffic designation set anywhere (consistency check, not a correctness check) | metric | game mechanic (the field itself and its cost multiplier are real and readable) | Q2; distinct from rule 7 — this checks whether the *mechanic* is being used at all, independent of width |
| 9 | Rank a workshop-and-its-natural-stockpile pair by corridor-graph distance (not straight-line), lower is better | metric | convention, importing a solved formal problem (Q6, travel-weighted facility layout) without its real flow weights | Q5 #7, Q6; must be documented as a proxy (workshop kind implies expected stockpile kind) standing in for unmeasurable real flow, not a claim of optimality |
| 10 | Rank an office/bedroom for a role-holder by corridor-graph distance to the fortress's main circulation hub (nearest major stairwell or the busiest corridor node), lower is better | metric | convention | Q5 #3, Q3; no source gave a numeric threshold, so this stays a relative ranking between candidate sites, never an absolute pass/fail |
| 11 | Do not reject a bedroom for lacking a door on privacy grounds | invariant-of-omission (an explicit non-rule) | game mechanic contradicting the common convention | Q4: `Bedroom_design`'s own current-v53.16-banner text states no penalty for others traveling through a sleeping dwarf's bedroom; encoding a door requirement here would repeat this project's own named mistake pattern (`prefer_indoors`) |
| 12 | Flag a high-traffic corridor (serves more than N rooms/workshops per rule 7's own count) that narrows directly at a heavily used junction with no intermediate width step | metric | convention, imported whole from the road-hierarchy analogy | Q5 #6, Q6; the most speculative rule in this table, marked as such — no DF-specific source states this, only the cross-domain analogy |
| 13 | Rank a plan by total excavated/constructed tile count relative to its own room footprint total (lower ratio of circulation-only tiles to room tiles is better, all else equal) | metric | convention | Q7; the build-cost half of the two-objective tension, kept as a relative rank rather than an absolute budget since no source gives a target ratio |

**Deliberately not proposed as checker rules**, with reasons: door-on-every-
room-for-value (Q4, unanswered, belongs to the sibling enclosure/value
stream); meeting-hall/animal-conflict avoidance (Q5 #8, source is version
-uncertain); any absolute travel-distance or stairwell-count threshold (Q3,
no source gave one, and inventing one would repeat exactly the
folklore-as-requirement mistake this project has made twice already);
enclosure/indoor-requirement rules of any kind (explicitly out of scope,
owned by `handoffs/2026-09-24-room-enclosure-and-value.md`).

## Proposed doctrine entries (for the orchestrating session to route, not written here)

Two items look like durable operational rules the doctrine system's own
scope (small, always-resident, cached operational rules, not layout design
detail) would actually want, both clearly labelled by provenance if added:

1. **Traffic designation exists and is unused on this fort** (`prior`,
   current v53.16-banner wiki source for the mechanic itself; the "unused on
   this fort" half is install-verified, per `CLAUDE.md`'s own status
   banner). Worth a doctrine line only if the project intends the
   conductor/architect to ever set traffic designations; otherwise this is
   better left as a `Working.md`/roadmap note than doctrine, since doctrine
   is operational rules an agent needs at decision time, not a to-do.
2. **Bedroom doors are not required for sleeping-dwarf privacy** (`prior`,
   current v53.16-banner wiki source, Q4/Q5 rule 11 above). This one *is*
   doctrine-shaped: it directly prevents a specific, plausible future
   mistake (an architect agent adding a door to every bedroom on the belief
   that it is required), in the same family as the existing `prefer_indoors`
   correction this project has already made once.

Both are proposals only; this stream did not touch `doctrine/seed.yaml` per
the brief.

## What could not be verified

- **Any live congestion, traffic-cost or per-route travel data from this
  project's own fort.** DFHack exposes no such telemetry this session could
  find; every width/congestion claim above is wiki/community convention,
  not confirmed against this install.
- **Whether a door contributes to a room's numeric value.** Not found in
  any source this session checked; explicitly the sibling stream's
  question, not answered here.
- **Vermin and temperature/cave-adaptation effects of doors specifically**
  (as distinct from room exposure generally). Not addressed by the page
  fetched this session.
- **A numeric stairwell-count-per-population or maximum-travel-distance
  threshold.** No source found gave one; Q3 and rule 10 above say this
  plainly rather than inventing a number.
- **The `Meeting_hall` page's animal-conflict claim**, which carries an
  older-version banner and was not independently confirmed; used only as a
  flagged, unendorsed data point (Q1, Q5 #8).
- **Whether DF's own pathfinding literally deadlocks two dwarves meeting on
  a 1-wide corridor, versus one yielding.** This report relies on this
  project's own prior working knowledge for the "one yields" claim, not on
  a source re-checked this session; flagged as weaker than the
  wiki-and-community-sourced claims above it.
- **`Corridor` as a dedicated wiki page.** The URL this session tried
  (`dwarffortresswiki.org/index.php/Corridor`) returned HTTP 404; corridor
  guidance above is drawn instead from `Bedroom_design`, `Workshop_design`
  and general search results that quote wiki and community text on hallway
  width, not from a page dedicated to corridors as their own topic. No such
  page may exist under that name; this was not exhaustively re-searched
  under alternate titles given the other sources already covering the same
  ground.

## Sources

Install/repo, read in full or in the relevant section this session:
`CLAUDE.md` (status banner), `docs/PURPOSE.md` (design commitments and build
order), `research/2026-09-23-room-and-zone-requirements.md` (full),
`scripts/dfhack/df-overseer-zone.lua` (header), `handoffs/2026-09-24-room-
enclosure-and-value.md`, `handoffs/2026-09-24-furniture-aware-ranking.md`
(both read to avoid duplicating sibling-stream scope, not to answer their
questions).

Web, fetched this session, each cited above by its own version banner
(`prior`, never `verified`, per doctrine's own provenance rule):
[Traffic](https://dwarffortresswiki.org/index.php/Traffic) (v53.16),
[Door](https://dwarffortresswiki.org/index.php/Door) (v53.16),
[Staircase](https://dwarffortresswiki.org/index.php/Staircase) (v53.16),
[Bedroom design](https://dwarffortresswiki.org/index.php/Bedroom_design)
(v53.16), [Workshop design](https://dwarffortresswiki.org/index.php/Workshop_design)
(v53.16, with its own "may be inaccurate" self-caveat, preserved above),
[Meeting hall](https://dwarffortresswiki.org/index.php/Meeting_hall)
(older-version banner, "migrated... may need updates for v53.16," used only
where flagged). `Corridor` (`dwarffortresswiki.org/index.php/Corridor`)
returned HTTP 404 and was not used. General web search results (not a single
page each, so no individual version banner) contributed the "two-tile
minimum, three preferred" hallway-width figure, the "double loaded corridor"
and workshop-wing description, and the "maximum walk to stockpile on same
wing: 18" figure, all attributed to the wiki/community pages named in the
search results themselves and treated with the same `prior` status as the
directly-fetched pages above.

Cross-domain fields (Q6) drawn from this session's own general knowledge of
architectural space planning, urban road-hierarchy classification,
building-code egress conventions, and industrial-engineering facility
layout (the quadratic assignment / travel-weighted adjacency problem); none
of these is DF-specific and none was independently re-verified against a
primary source this session, since the brief's own scope is "take what fits
and say plainly what does not," not a citation-grade survey of those fields.
