# The fort dossier, per role, and a code search over the crafting graph tied to Logistics

Date: 2026-10-07. **Revision 1, design only, nothing built.** Author: Opus
design pass for the orchestrator. A separate red team follows.

Register row: `decisions/DECISIONS.md` 2026-10-07 "Agents get a per-role
fort dossier ... and a code search over the crafting graph tied to
Logistics" (line 640). Folded in, as first-class sections, the user's later
calls the same day, relayed by the orchestrator:

1. **Formalised, measurable structure** (section 2, section 14): a typed
   schema first, text second, rendered deterministically; completeness,
   accuracy, freshness, size and churn measures, and effect measures through
   `dfqueue/wake_metrics.py`.
2. **The logistics map in words** (section 9): the flow network of piles,
   workshops and links, with computed flags, never coordinates or a grid.
3. **The crafting graph suggests logistics** (section 11): code computes
   gaps and candidate fixes, structured so Logistics can file them; the agent
   chooses. With a walk-through on today's fort (section 12).
4. **One structure, filtered per role as data** (section 5): declarative
   per-role filters plus a per-wake focus filter (the wake's entities and
   their neighbours within N hops), with a slice-miss metric.
5. **Slice waste** (section 14.4) as the mirror of slice miss, and **push
   versus pull decided per role on evidence** (section 5.4, section 14.5):
   each role's slice is `full`, `minimal` or `off`, the dossier is also
   available as read tools so pull always works.

Marking: **[verified]** means read this session in code, data or a register
row at the cited `file:line`; **[live 2026-10-07]** means read this session
on VM 103 through the real MCP server with read-only calls (the fort was not
written to); everything else is **[proposed]**.

---

## 0. The design in one screen

1. **The dossier is a typed graph of the fort as it stands**: entities
   (rooms and zones, workshops, stockpiles, sites, projects, districts,
   landmarks) with stable handles, relations between them (near, reachable,
   feeds, takes_from, outputs_to, located_in, part_of, serves, waiting_on,
   makes, needs), a status per entity (built, in_progress with project and
   step, planned, waiting_on_input), and every fact stamped with the read
   and tick it came from. Code builds it from reads that already exist.
2. **Text is a pure function of the schema.** Same schema, same bytes. Volatile
   numbers are bucketed (a pile is `full`, not `24 of 25`) so the text changes
   only when the fort does.
3. **It is rebuilt on change, not on every wake.** A cheap structural
   fingerprint each cycle; a full rebuild only when the fingerprint moves or a
   known trigger fires (a step done, a building finished, a link made); one
   audit rebuild per game season catches drift the fingerprint missed.
4. **One structure, filtered per role as data** (`dossier/slices.yaml`): which
   entity kinds, relation kinds, statuses and scope each role sees, in mode
   `full`, `minimal` or `off`, plus a per-wake focus (the wake's own entities
   and their neighbours within N hops). Defaults argued per role: Logistics
   full, Planner full at district level, Quartermaster production chains,
   Architect minimal, Overseer focus only. **Settled per role by measurement**,
   not assumed.
5. **Pull always works.** `dossier.get` and `dossier.find` read the same store,
   scoped by the role's visibility filter.
6. **The Chronicler adds meaning code cannot derive**, as separate annotations
   that cite facts or queue records, validated by the server, and dropped when
   a cited fact changes. Parked until the code-built dossier is measured;
   **its charter's "never influence what the fort does" line conflicts with
   this use** (open question 1).
7. **The crafting graph becomes searchable and complete.** First fill the hole
   it has today (hard-coded jobs have no reagent or product rows); then three
   read tools: `craft.how` (how X is made, or what uses X), `craft.blockers`
   (what blocks X here, the existing blocker walk on live stock and built
   workshops), `craft.workshop` (what a kind or a built workshop needs and
   makes).
8. **The graph suggests logistics.** `logistics.gaps` compares, per built or
   planned workshop and per plan flow, the graph's inputs and outputs with the
   live flow network, and emits gaps with candidate fixes shaped as proposal
   drafts; a Logistics proposal may cite `from_gap`, which the server checks
   and the Overseer sees.
9. **One source for "what does this job make".** The unsupplied watch's
   job-name rule, the stockpile tool's hand-authored outputs and the orders
   tool's per-job material defaults all become reads of the graph, with a
   parity test against the live game.
10. **Staged:** D0 graph completion, D1 dossier core and pull tools, D2 slices
    in briefings with metrics, C crafting tools, L+ logistics gaps, D3 the
    push/pull comparison, D4 Chronicler (parked).

---

## 1. What exists to build from, and what is missing

### 1.1 Reads the dossier can assemble from

| Read | What it gives | Status |
|---|---|---|
| `landmarks.list` / `landmarks.get` | every named landmark, kind, and its **3 nearest** others with compass direction, straight-line distance and reachability | **[live 2026-10-07]**; 3 nearest only (`scripts/dfhack/df-overseer-landmarks.lua:125`), straight-line in x and y, z ignored (`:129-134`) **[verified]** |
| `stockpile.list` | per pile: id, accepts (17 coarse categories), occupied and total tiles, containers, links_only, near landmark | **[live 2026-10-07]**: both piles return `links_only` and `containers`, so the list read's new fields are live |
| `stockpile.links` | the four link vectors for a pile or workshop | **[live 2026-10-07]**, both piles have no links |
| `stockpile.health`, `stockpile.plan-feed` | per linked workshop, input classes and output acceptance; a dry-run pile spec per kind | merged, **not deployed**: `live_deployed: false, verified: unverified` (`scripts/dfhack/TOOLS.yaml:3929-3930`, `:3962-3963`) **[verified]** |
| `zone.list` | zones by kind and owner, furnished counts (Planner P1b) | exists; needs `kind_filter` and `owner_filter` **[live 2026-10-07]** |
| `blueprint.sites` | each site: handle, template, footprint size, near landmark, `phases_applied`, ore exposed, reservation | **[live 2026-10-07]**: site-2 office (zone phase applied), site-3 bedroom (shell, finish), site-4/5/6 bedrooms (shell only) |
| `queue.project_status` | open projects, steps and step states | exists (`dfqueue/store.py:1281`) **[verified]** |
| `workjob.unsupplied` | planned buildings waiting on an item kind, its producers by job and kind | **[live 2026-10-07]**: one Bed waits on BED, 0 available, producers `ConstructBed` and reaction `MAKE WOODEN BED` at Carpenters, nothing queued |
| `workjob.list-jobs` | per built workshop, each job's reagents with live availability **after the game's own item filter** (`has_material_reaction_product`, `flags1.unrotten`, `food_storage`) | **[live 2026-10-07]**, the Still's three jobs |
| `stocks.availability` | per item type, available units with all six deductions | **[live 2026-10-07]**: PLANT 117, DRINK 0, WOOD 14 (3 in buildings), BARREL 27 |
| `orders.list` | manager orders, job, reaction, active, validated | **[live 2026-10-07]**: 13 `BREW_DRINK_FROM_PLANT` validated but inactive; the throne order unvalidated |
| `connectivity.check` | reachable or not between two landmarks | exists |
| `plan.read` | the Planner's active plan (targets now, districts from P2) | live on the Quartermaster's list **[live 2026-10-07]** |

### 1.2 Findings that shape the design

- **F1. The crafting graph has no reagents or products for hard-coded jobs.**
  `production/labor_ingest.py` adds hard-coded job processes
  (`JOB:<Kind>:<JobType>:<task>`, `:30-34`) and unextracted reactions, but its
  writes are nodes, processes and attributes only (`:464-473`), never
  `production_flow` rows **[verified]**. So the graph can say a Carpenter's
  Workshop hosts `ConstructBed`, not that `ConstructBed` takes wood and makes a
  BED. "How is a bed made" cannot be answered from the graph today, and the
  blocker walk (`production/blocker.py:379`) would report a bed as having no
  producer.
- **F2. "What does this job make" is derived three times, three ways.** The
  unsupplied read strips the verb from the job name (`ConstructBed` to BED)
  with a two-entry alias table (`scripts/dfhack/df-overseer-workjob.lua:1115-1136`,
  "UNVERIFIED LIVE"); the stockpile tool derives inputs from
  `dfhack.workshops.getJobs` at runtime (`scripts/dfhack/df-overseer-stockpile.lua:1108`)
  but takes built-in job **outputs** from a hand-authored fallback table
  (`scripts/dfhack/df-overseer-stockpile-kinds.lua:216-221`, `OUTPUT_HINTS`
  copied from `FALLBACK_KINDS`); the extractor derives reaction products from
  the raws. Three answers to one question will drift.
- **F3. Landmark names are not unique.** Two landmarks are both named
  `shale Throne` **[live 2026-10-07]**. Handles must be ids; names are for
  display, disambiguated when duplicated. (The Planner red team's F-23 asked for
  unique anchor names for the same reason.)
- **F4. Relations from the landmark read are partial.** Three nearest
  neighbours, straight-line, no level difference **[verified]**. The dossier
  can state "Still: Stockpile #1 is 4 tiles N, reachable" but not "Still is two
  levels below the farm". The relation read the Planner design owes before P2
  (F-23: horizontal distance, level difference, reachability, per pair) is the
  fix, and the dossier should consume it, not build a second one.
- **F5. "Connects via" has no source beyond links and reachability.** No read
  names the corridor or stair a path uses. Links are explicit connections; walk
  connectivity is a tri-state; a named via (stair, door, chokepoint) needs the
  relation read to report it. Stated as a gap, not composed by the model
  (`research/2026-09-25-district-layout-prior-art.md` Q5, cited in the Planner
  design 3.1).
- **F6. The architecture already names this tier.** `docs/AGENT-ARCHITECTURE.md:603`:
  "Tier 1, briefing: named-landmark / exits-graph summary, scoped to one domain,
  O(landmarks), read by a woken specialist" **[verified]**. The briefing module
  today carries Tier 0 only, "nothing that grows with the fort"
  (`conductor/briefing.py:3-4`) **[verified]**. The dossier is that Tier 1,
  bounded by caps, not a breach of the Tier 0 rule.
- **F7. `docs/MEMORY-ARCHITECTURE.md`'s fort dossier was a one-row idea**:
  "Working state: landmarks, plans, open problems; dies with the fort; always
  loaded; in context" (`:18`), distilled into an epitaph at the end (`:30`),
  site-scoped facts live there (`:178`), each turn "assembles a fresh context
  from memory: doctrine, dossier, ..." (`:396-399`) **[verified]**. This design
  keeps all four intents (working state, dies with the fort, in context, fresh
  per turn) and narrows "always loaded" to "loaded per role as measured".
- **F8. The Chronicler's charter says it "must never be in a position where the
  story it wants to tell could influence what the fort does"**
  (`agents/chronicler/role.md:17-18`) **[verified]**. An annotation in a
  dossier that deciders read is exactly such a position. Open question 1.
- **F9. Today's fort, read live**: four workshops (Carpenter's, Mechanic's,
  Still, Stoneworker's), two 25-tile piles that both accept food, furniture,
  stone, wood, finished goods and bars/blocks, one full and one 24 of 25, no
  links anywhere, 27 barrels, 117 plants, **0 drink**, 13 brew orders inactive,
  one Bed waiting on a BED nothing makes **[live 2026-10-07]**. Section 12 walks
  it. (The orchestrator's sketch, "Still beside the farm, Stockpile #2 plants,
  no drink pile; Carpenter with wood in Stockpile #1", is close but not exact:
  the farm is not among the Still's three nearest landmarks, and both piles
  accept the same six categories, so "plants" and "wood" are what they may
  hold, not what they are set for. The walk-through uses the live reads.)

---

## 2. The dossier as a typed schema

### 2.1 Entities and handles

| Kind | Handle | Display name | Source of identity |
|---|---|---|---|
| `workshop` | `ws-<building id>` | landmark name, plus ` (2)` when duplicated | building id |
| `stockpile` | `pile-<building id>` | `Stockpile #N` | building id |
| `zone` (room, farm, tomb, office, dining, water source, ...) | `zone-<building id>` | landmark name or zone kind | civzone id |
| `furniture` (placed, inside a zone) | `furn-<building id>` | kind and material (`shale Throne`) | building id; only listed as a zone's contents, never on its own line |
| `site` | `site-N` | template id | `blueprint.sites` handle (already stable, **[live]**) |
| `project` | `proj-N` | proposal summary | queue record |
| `district` | `dist-<plan id>` | plan district name | `fort_plan` (P2) |
| `landmark` (other: well, wagon, embark site, wall) | `lm-<kind>-<id>` | landmark name | building or seed id |
| `item_kind` (only as an endpoint: BED, DRINK) | `item-<ITEM_TYPE>` | item type | game enum |

Handles never encode a position. A handle survives renames; a building
destroyed and rebuilt gets a new id and a new handle, which is the honest
answer (it is a different building).

### 2.2 Status

One of, per entity, always with the fact it rests on:

| Status | Meaning | From |
|---|---|---|
| `built` | exists and complete | building `flags.exists`; zone furnished per kind (P1b's furnished read) |
| `in_progress` | a project step is open on it | `queue.project_status`: project, step i of n, step state; `blueprint.sites.phases_applied` |
| `planned` | reserved site, accepted proposal not yet a project, or a plan target slot | `blueprint.sites.reservation`, queue records, `plan.read` |
| `waiting_on_input` | its only unfinished work waits on an item kind | the Planner design's `waiting_on_input` observation (2.7), `workjob.unsupplied` |
| `under_construction` | a building placed and not finished, with no project (a hand-placed or game-placed one) | building `flags.exists` false |

### 2.3 Relations

| Relation | Between | Attributes | Source | Status |
|---|---|---|---|---|
| `near` | any two landmarked entities | direction, distance_tiles, reachability, `level: unknown` until F-23 | `landmarks.list` exits | exists, partial (F4) |
| `reachable` | two entities | tri-state | `connectivity.check`, the shared reachability helper | exists |
| `via` | path between two entities through a named stair, door or chokepoint | named entity | relation read (F-23 extended) | **gap** (F5) |
| `takes_from` | pile to pile, workshop to pile | | `stockpile.links` | exists |
| `gives_to` | pile to pile, pile to workshop | | `stockpile.links` | exists |
| `outputs_to` | workshop to pile (`give_to_pile` on the workshop) | | `stockpile.links` on the workshop | exists |
| `located_in` | site, workshop or pile to district; furniture to zone | | P2 binding table (stamped at reserve), `zone.contents` | district: P2; zone: exists |
| `part_of` | zone or furniture to site | | `blueprint.sites` plus zone overlap the server already computes | exists in the store; not a tool output today |
| `serves` | project to plan target | | `serves` on proposals (Planner P1) | P1 |
| `waiting_on` | site or building to `item_kind` | units | `workjob.unsupplied` | exists |
| `makes` | workshop kind to item class | process count | crafting graph (section 10) | after D0 |
| `needs` | workshop kind to item class, with role input, container or fuel | jobs needing it of all | crafting graph | after D0 |
| `built_for` | entity to the proposal and project that produced it | | queue records via site handle and project | exists in the store |

A relation is **stated by a tool or by the store, never composed by the
model**, and never derived by geometry in this code either: two entities with
no stated relation have none in the dossier. The dossier does not compute "the
farm is two tiles from the still" from coordinates on its own; it reports what
a tool states.

### 2.4 Facts and provenance

Every entity attribute and every relation carries a fact reference:

```yaml
fact:
  id: f-000412                   # stable within a fort
  source: {tool: stockpile.links, args: {id: 2}}   # or {store: queue, record: proposal-0017}
  read_tick: 209571              # abs tick of the read
  value_hash: 9c1e...            # of the canonical value, so a re-read that changed is detectable
  status: verified_read | derived | prior   # derived: computed by code from other facts (listed in derived_from)
  derived_from: [f-000401, f-000402]          # only for derived
```

A computed flag (section 9.2) is a `derived` fact naming its inputs, so the
Overseer can follow any line back to reads.

### 2.5 The schema in one example (abridged)

```yaml
dossier_version: dv-0042
built_tick: 209571
fingerprint: 4f2a...
entities:
  - {handle: ws-5, kind: workshop, workshop_kind: Still, display: Still, status: built, facts: [f-0101]}
  - {handle: pile-1, kind: stockpile, display: "Stockpile #1", status: built,
     accepts: [food, furniture, stone, wood, finished_goods, bars_blocks],
     fill: full, tiles: 25, links_only: false, containers: {bins: 25, barrels: 25, wheelbarrows: 0},
     facts: [f-0110, f-0111]}
  - {handle: site-4, kind: site, template: bedroom-cell-v1, status: in_progress,
     project: proj-12, step: "2 of 4", step_state: waiting, facts: [f-0130, f-0131]}
relations:
  - {kind: near, from: ws-5, to: pile-1, direction: N, distance_tiles: 4, reachability: reachable, level: unknown, fact: f-0140}
  - {kind: needs, from: ws-5, to: class-plant-brewable, role: input, jobs: "2 of 3", fact: f-0201}
  - {kind: waiting_on, from: lm-bed-31, to: item-BED, units: 1, fact: f-0150}
annotations: []                  # section 7
```

---

## 3. Assembly: sources, triggers, versions

### 3.1 One aggregator read, no new game logic

A new `scripts/dfhack/df-overseer-dossier.lua` with two commands, both
read-only, both built by `reqscript` over the existing modules
(`df-overseer-landmarks`, `df-overseer-stockpile` `list_stockpiles` and link
reads, `df-overseer-zone`, `df-overseer-blueprint` sites,
`df-overseer-workjob` unsupplied), adding **no new game interpretation**:

- `fingerprint`: a hash over structural state only: building ids with type and
  `flags.exists`, zone ids and kinds, pile ids with accepts, links_only,
  container counts and the four link vectors, site handles with
  `phases_applied`, planned-building waits by item kind. Fill levels are not in
  it. One call, small output.
- `structure`: the same reads in one JSON object, so the server makes one
  DFHack call instead of one `stockpile.links` per pile.

Coordinates never leave Lua, as everywhere else (`docs/PRODUCTION-MODEL.md`
section 16) **[verified rule]**.

### 3.2 Server-side assembly

A new Python package `dossier/` (checked name: nothing on the path is called
`dossier`; same check as `production/__init__.py:5-8` records), pure like
`production/snapshot.py`: tool-shaped data in, schema out, no live call inside.
`dfmcp` calls the Lua read, the queue store, the plan store and the production
graph, hands the results to `dossier.assemble`, and writes the version.

### 3.3 When it rebuilds

| Trigger | How it is known | Why |
|---|---|---|
| Fingerprint changed | `dossier.refresh` (conductor-only) runs the `fingerprint` read each cycle | catches every structural change, whoever made it, including the player |
| A routed step done or attention | the conductor's existing `step_done`/`step_attention` lane events | a project moved; queue state is not in the Lua fingerprint |
| A ruling or project opened, closed or abandoned | queue record ids since the last version | `planned` and `in_progress` change |
| A plan version filed | `fort_plan` record | districts and targets change |
| A fill bucket crossed (section 3.5) | a cheap fill read for piles only, every N cycles (policy) | a pile went from `low` to `empty` |
| Season audit | the computed season cursor (Planner P1b) | a full rebuild plus the accuracy audit (section 14.2) |

**Not** on every wake. When nothing changed, `dossier.refresh` returns the same
version id and the conductor puts the same bytes in the briefing.

### 3.4 Versions

A version is written only when the canonical schema (sorted, volatile values
bucketed, provenance excluded from the hash) differs from the previous one.
Each version stores its parent and a computed **change list** (entities and
relations added, removed or changed status), which is the source of the
`recent_changes` section and of the churn measure.

### 3.5 Volatile values are bucketed

| Value | Shown as | Exact value |
|---|---|---|
| pile fill | `empty` (0), `low` (below a third), `half`, `high` (two thirds or more), `full` (all tiles) | `dossier.get` returns occupied and total |
| stock counts on a chain line | `none`, `some` (1 to the job need), `enough` (above), with the exact count only when it is 0 | `craft.blockers`, `stocks.availability` |
| distances | as the tool states, integer tiles | |

Hysteresis is not designed in; the churn measure (section 14.1) says whether it
is needed. If a pile flaps between `high` and `full` each cycle, add a one-tile
band, not before.

### 3.6 History: what changed in the fort, not what the agent did

The `recent_changes` section is the last K structural changes from version
diffs, game day first, at most 5 lines (policy):

```
day 211: Still built.
day 214: site-4 (bedroom) shell done; finish step waiting.
day 219: Bed placed in site-3, waiting on BED.
```

Each line cites the version pair it came from. It is the fort's history in the
dossier's own terms; the agent's filings stay in the separate
"your recent filings" block (`conductor/briefing.py:179`) **[verified]**.

---

## 4. Rendering: deterministic text

### 4.1 Rules

- `render(schema, filter) -> str` is a pure function. Sorted by section order,
  then entity kind order (fixed list), then handle number. Relations sorted by
  kind, then target handle. No tick, wall time or version id inside the body;
  one stamp line at the **end** (`dossier dv-0042, game day 219`), so the body's
  bytes are stable while the fort is.
- Lines are plain sentences with handles in brackets, so an agent can quote a
  handle into a tool call and the transcript metrics can match it.
- Every capped list ends with one deterministic overflow line naming the pull
  call: `+3 more workshops: dossier.find kind=workshop`.
- No coordinates, no grid, no arrangement on the page that reflects geography
  (`docs/PRODUCTION-MODEL.md` section 16: "the site layer is not a map")
  **[verified rule]**. Order is by kind and handle, never by position.

### 4.2 Example, today's fort, full view (illustrative, from the live reads)

```
FORT DOSSIER
Built
- Still [ws-5]. Needs brewable plants (2 of 3 jobs) and empty food-storage barrels (all jobs); makes drink. No links: takes from anywhere. Near: Stoneworker's Workshop W 3, Stockpile #1 N 4.
- Carpenter's Workshop [ws-?]. Needs wood; makes furniture, beds, barrels, bins. No links. Near: Stockpile #1 S 2.
- Stoneworker's Workshop [ws-?], Mechanic's Workshop [ws-?]: no links. Near: Stockpile #2 W 2; Stockpile #2 SE 1.
- Stockpile #1 [pile-1]: full, 25 tiles, accepts food, furniture, stone, wood, finished goods, bars/blocks; bins 25, barrels 25; takes from anywhere; no links.
- Stockpile #2 [pile-2]: full (24 of 25), same settings; no links.
- Farm Plot [zone-4], Well, office site-2 (Throne, zoned).
In progress
- site-4, site-5, site-6 (bedroom-cell-v1): shell done, next phase not started.
- site-3 (bedroom-cell-v1): finished; its Bed waits on BED: 0 free, made at Carpenter's Workshop, nothing queued.
Recent changes
- (from version history once D1 runs)
dossier dv-0001, game day N
```

(`ws-?` marks building ids not read in this session; the Still's id 5 is from
the 2026-09-18 live record in `scripts/dfhack/TOOLS.yaml:3476` **[verified]**.)

---

## 5. Slices: one structure, filtered per role, as data

### 5.1 The filter

`dossier/slices.yaml`, one entry per role, validated at load (unknown kinds
refused, the way `agents/*/tools.yaml` is validated):

```yaml
logistics:
  mode: full                      # full | minimal | off
  entity_kinds: [workshop, stockpile, item_kind]
  relation_kinds: [gives_to, takes_from, outputs_to, needs, makes, near]
  near_between: [[workshop, stockpile], [stockpile, stockpile]]   # which near-pairs to keep
  statuses: [built, in_progress, planned, under_construction]
  scope: {districts: all}
  sections: [flow_network, flow_flags, chain_gaps, recent_changes]
  visible: [workshop, stockpile, zone, site, item_kind, district]  # what pull tools may return
  focus_hops: 1
  caps: {entities: 40, lines: 60, chars: 6000}
architect:
  mode: minimal
  entity_kinds: [site, zone, workshop]
  relation_kinds: [near, waiting_on, located_in, part_of]
  statuses: [in_progress, planned, waiting_on_input]
  sections: [in_progress, focus]
  visible: [site, zone, workshop, stockpile, landmark, district]
  focus_hops: 1
  caps: {entities: 12, lines: 16, chars: 1600}
```

`minimal` means: the `in_progress` list for the role's own entity kinds plus the
focus (5.2), nothing else. `off` means no slice; pull tools still work.

### 5.2 The per-wake focus

Each wake line names what it is about; code maps the wake to seed handles and
takes their neighbours within `focus_hops` over the role's admitted relation
kinds:

| Wake reason | Seed handles |
|---|---|
| `step_done`, `step_attention` | the project's site and its zone |
| `workshop_ready`, `feeder_starved`, `output_blocked` (Logistics, Planner design 6.2) | the workshop and its linked piles |
| `flow_unrealised` | both industries' workshops |
| `plan_shortfall`, `plan_input_short` | the target's district anchor and in-flight sites; the input `item_kind` |
| `unsupplied` | the waiting buildings' sites and the `item_kind` |
| `ore` | the site exposing it |
| `ruling_on_own`, `answer`, `ask` | entities named in the proposal or ask by handle |
| Overseer ruling wake | entities named in each pending proposal |

The focus is rendered first in the slice (it is per-wake, so it breaks the
cache from there on; the rest of the slice stays stable before it only if the
focus is rendered last; see 8.3 for the placement trade).

### 5.3 Need-to-know

`visible` bounds what the pull tools return for a role; the push slice is
always a subset of it. The server enforces it, not the charter (the
`dfmcp/roles.py` allowlist pattern). A refused pull says which role sees that
kind, so a role asks rather than guesses.

### 5.4 Per-role defaults, argued

| Role | Default | Why | What would change it |
|---|---|---|---|
| **Logistics** | `full`: flow network, flags, chain gaps | It reasons over the whole network (which pile feeds which workshop, what is linked, what is missing). Pulling it costs one `stockpile.links` per pile and workshop plus `stockpile.list` plus `landmarks.get` per workshop: many reads for a picture that fits in about 40 lines. The user's own view. | slice waste above threshold on a section (drop it) |
| **Planner** | `full` at district level: districts, their anchors, industries and the workshops in them, chain status per plan flow (built, unlinked, starved), room counts per kind | Its job is the whole fort at low resolution; it wakes about 4 times a game year, so a pushed picture replaces a dozen reads each time. Room-level detail stays pull. | slice miss on room-level facts (add a section) |
| **Quartermaster** | production chains only: per built workshop, what it makes, inputs available (bucketed), orders pinned or not, chains with a missing link or a waiting building | It decides what gets made; spatial facts are not its lane. | slice miss on stock lines (add), waste on near-relations (drop) |
| **Architect** | `minimal`: its in-progress sites and the wake's focus | Its work is spatial search with `find`, `plan` and `preview`; a summary cannot contain the candidate sites those tools compute. A full picture may add reading without removing calls. The user's own doubt. | rounds to first write and read calls fall in a `full` arm |
| **Overseer** | focus only: entities its pending proposals name, 1 hop | It rules, it does not search; the facts that matter are the ones each proposal touches. Its tool list is being cut toward ruling-only (register 2026-10-07). | none expected |
| **Consultant** | `off` | It answers questions from the wiki and doctrine. | an ask that needed fort state |
| **Chronicler** (parked) | `full`, plus `recent_changes` at a larger cap | It narrates the fort. | |
| **Conductor** | n/a, code | | |

The defaults are a starting point. Section 14.5 says how each is settled.

### 5.5 Caps

Item caps per section and a character cap per slice, policy data. A slice is
never truncated mid-line: lists are cut at a whole entity with the overflow
line. Starting caps (characters, about 4 per token): Logistics 6,000, Planner
4,000, Quartermaster 3,200, Architect 1,600, Overseer 1,200. These bound cost
(section 16) and are themselves measured (section 14.1).

---

## 6. Pull tools

| Tool | Args | Returns | Roles |
|---|---|---|---|
| `dossier.get` | `handle` or `name` (resolves duplicates by listing them), `hops` (0 to 2, default 1), `exact: bool` | the entity, its relations within hops, exact volatile values when `exact`, every fact's source and tick | every role with a slice mode other than `off`, plus the Chronicler |
| `dossier.find` | `kind`, `status`, `district`, `near` (handle), `limit` (default 10) | matching entities, one line each, sorted as in rendering | Planner, Logistics, Chronicler; others only if a slice-miss measure shows they need it |
| `dossier.changes` | `since_version` or `days` | the change list | Chronicler; the Board |
| `dossier.slice` | `role`, `wake` | the rendered slice and its version | conductor only |
| `dossier.refresh` | none | version id, whether it changed | conductor only |

All read-only, all native in `dfmcp` (no game write path exists in the
module), all filtered by the caller's `visible` set. Pull works whatever the
slice mode: a role whose slice is `off` can still get the same facts.

---

## 7. The Chronicler: meaning code cannot derive

### 7.1 What code already derives, so the Chronicler need not

- **Purpose from provenance.** `built_for` links a workshop or room to the
  proposal and project that made it; the proposal's summary and public
  rationale say why ("a still for drink"). Code renders "built for proposal-0009
  (drink)" with no model.
- **Group names from the plan.** From P2 and P3, districts and industries name
  groupings ("brewing" industry, its workshop is the Still, in district
  `workshops`).

So "the brewing corner" exists, deterministically, as soon as the Planner names
an industry. The Chronicler is for what neither source says: the fort's own
nicknames, the reason a thing was left as it is, a story that ties several
changes together ("the bedrooms east of the farm were dug after the first
migrants slept on the floor").

### 7.2 Annotations, cited and validated

```yaml
annotation:
  id: ann-0007
  about: [ws-5, pile-2]           # existing handles, checked
  kind: purpose | name | note
  text: "The brewing corner: the Still and the plant pile beside the Mechanic's."   # 160 characters at most
  cites: [f-0140, f-0201, proposal-0009]   # facts or queue records, at least one, each must exist
  author: chronicler              # stamped
  tick: 209800
  state: valid | stale            # stale when any cited fact's value_hash changes
```

Server checks at write (`dossier.annotate`, Chronicler only): every handle in
`about` exists in the current version; every citation resolves; no coordinate
(the `dfqueue/schema.py` `_COORDINATE_PATTERN` refusal, reused); length caps;
at most one valid annotation of each kind per entity (a new one supersedes).
When a rebuild changes a cited fact, the annotation turns `stale` and leaves
every slice until the Chronicler re-confirms or replaces it. Annotations render
in their own marked line (`note (chronicler, cites f-0140, proposal-0009): ...`),
never merged into code-built lines, so a reader always knows which is which.

### 7.3 Why parked

The code-built dossier must be measured first: if it alone lowers rounds and
reads, annotations add cost (a Chronicler wake per change) for a benefit
nobody has shown. And the charter conflict (F8) needs the user's call first.

---

## 8. Storage and delivery

### 8.1 Store

A SQLite file per fort on VM 103, `/var/lib/dfdossier/<fort>.sqlite3`, beside
`/var/lib/dfproduction` and `/var/lib/dfseries`, opened by the server.
Tables: `version`, `entity`, `relation`, `fact`, `annotation`, `slice_render`
(role, version, focus key, hash, chars). **Trap carried forward:** the server
runs under `ProtectSystem=strict`, and a WAL-mode SQLite needs a
`ReadWritePaths` line or every write fails (register 2026-09-20, recorded in
`production/labors.py` header) **[verified]**.

Why not a `dfqueue` record kind, as the Planner used for `fort_plan`: the queue
is the audit log of decisions, written by roles and checked at write; the
dossier is machine-built state rewritten on every structural change. Mixing
them would flood the Board's record stream and the JSONL export with
non-decisions. The queue keeps pointers: a proposal or ruling can cite a
dossier fact id, and `built_for` points the other way.

Why not rebuilt in memory each cycle: versions are what make churn, freshness,
`recent_changes`, the season audit and the Chronicler's citations possible,
and the store is small (tens of entities).

**Dies with the fort** (`docs/MEMORY-ARCHITECTURE.md:30`): at fort end the last
version and the change list feed the epitaph; the file is archived, not
deleted, for the public report (memory `reporting-goal`).

### 8.2 Delivery today: the briefing

The conductor calls `dossier.slice(role, wake)` while assembling each woken
role's briefing and passes the text to `build_briefing` as a new optional
argument, rendered as a `fort_dossier` key. Cost of the read: one native call,
no DFHack call unless a refresh is due.

### 8.3 Placement and caching

The Planner design put season-stable plan text first in the briefing, before
`game_tick`, and live numbers last (its F-21) **[verified]**. The dossier
follows: stable dossier body first (it changes only with the fort), then the
plan slice, then the per-wake parts (game tick, wake reason, focus, alerts,
filings). The per-wake focus goes **after** the stable body, which keeps the
body byte-identical across wakes while the fort is unchanged.

Honesty about the gain: cache reads are 3% of cost and the briefing is the last
positional argument (`research/2026-10-07-cross-run-cache.md`, "Answer")
**[verified]**; openclaw's system prompt carries the date, so a day change
invalidates the prefix anyway (`research/2026-10-07-openclaw-source-sessions.md`
section 3) **[verified]**. Byte stability matters here mostly for diffs and
churn measurement, and within a wake (every later round re-reads the slice from
cache). The real lever is fewer rounds (section 16).

### 8.4 Delivery under the undecided inbox and session options

`research/2026-10-07-session-inbox-options.md` recommends design A (inbox as
data, one-shot run per wake, grouped rendering) and leaves B, C and D (session
per wake, long-lived session, hybrid) to the openclaw test **[verified]**. The
dossier fits each without change to its own design:

| Option | Where the dossier goes |
|---|---|
| Today (no inbox) | `fort_dossier` key at the start of the briefing |
| A, inbox as data | the dossier is **state, not an item**: it is not acked, struck or expired. It renders as the docket's header, before the grouped items. Changes since the role's last wake (the version diff, filtered by its slice) may also be **note-class items** coalesced by entity handle, so "Still built" is one item however many cycles saw it |
| B, session per wake, items per turn | the slice in the first user turn; a mid-wake version change is pushed as one change item, not a re-render |
| C, long-lived session wiped between wakes | the slice in the first turn after each wipe, which is the same as A |
| D, hybrid | as A for advisors, as B for the Overseer |

Nothing in the dossier depends on which is chosen.

---

## 9. The logistics map, in words

### 9.1 The flow network section

Rendered for Logistics (full), Planner (district level, counts only) and the
Quartermaster (chain lines only). One block per workshop, then free piles, then
pile chains:

```
FLOW NETWORK
Workshops
- Still [ws-5] (brewing): inputs: brewable plants: no linked source (takes from anywhere; fort has 117); empty barrels: no linked source (fort has 27). Output: drink: no output link; piles that accept food: Stockpile #1 full, Stockpile #2 full.
- Carpenter's Workshop [ws-?]: inputs: wood: no linked source (fort has 14). Output: furniture, beds, barrels: no output link; piles that accept furniture: both full.
Piles
- Stockpile #1 [pile-1]: full, 25 tiles, accepts food, furniture, stone, wood, finished goods, bars/blocks; bins 25, barrels 25, wheelbarrows 0; takes from anywhere. Links: none. Nearest workshop: Carpenter's 2 N.
- Stockpile #2 [pile-2]: full, same settings. Links: none. Nearest workshop: Mechanic's 1 NW.
Chains (pile to pile): none.
Flags
- [full-output] Still, Carpenter's, Stoneworker's, Mechanic's: every pile that accepts their products is full.
- [no-drink] drink 0 fort-wide; the brew chain has plants and barrels; 13 brew orders are inactive (Quartermaster's).
```

### 9.2 Computed flags

Each flag is a `derived` fact with its inputs listed, and a fixed routing rule
(the Planner design's boundary notes: available fort-wide is Logistics',
absent fort-wide is the Quartermaster's, `research/2026-10-07-planner-design.md`
section 1) **[verified]**:

| Flag | Rule | Routed to |
|---|---|---|
| `unlinked-input` | a workshop **with** input links has an input class (role input, container or fuel, from the graph) with no linked source | Logistics |
| `linked-source-empty` | a linked source exists and is empty, the class is available fort-wide | Logistics |
| `absent-input` | the class is 0 fort-wide and nothing queued or ordered makes it | Quartermaster |
| `output-rejected` | the workshop's output link accepts none of a product class | Logistics |
| `full-output` | no pile with a free tile accepts a product class (links or not) | Logistics |
| `starved` | a linked workshop with a waiting job or active pinned order and an input flag above | Logistics or Quartermaster per the input rule |
| `long-haul` | the nearest pile accepting an input class is further than `long_haul_tiles` (policy, start 15) by the stated distance, or is not among the workshop's stated near-relations at all | Logistics (only with a reason; see 11.3) |
| `waiting-building` | a planned building waits on an item kind | Quartermaster (the unsupplied watch) |

A workshop with no links takes from anywhere, so no `unlinked-input` flag is
raised for it: "link only when there is a reason" (Planner design 6.1)
**[verified]**. `long-haul` is the only flag that can suggest a first link.

---

## 10. Searching the crafting graph

### 10.1 D0: complete the graph first (F1, F2)

1. **Reagents of hard-coded jobs from the game's own job definitions.** The
   building-tool dump (`production/labor_ingest.py`, "Deliverable 4") already
   reads `workshop_hosting` per kind. Extend that bounded live read to emit, per
   kind and per `dfhack.workshops.getJobs` entry, the job type, reaction code,
   and each item spec (`item_type`, flag sets, quantity,
   `has_material_reaction_product`, reaction class, material category) **the
   same fields `derive_kind` reads** (`scripts/dfhack/df-overseer-stockpile.lua:1108`)
   **[verified]**. `labor_ingest` writes them as `production_flow` reagent rows
   on the `JOB:` processes, with a class node per distinct spec
   (`CLASS:<ITEM_TYPE>:<flags>` or the material reaction product class).
2. **Products of hard-coded jobs, from game data first.** Probe once, read-only,
   whether DFHack's `df.job_type.attrs[<job>].item` names the product (a job
   type attribute in df-structures, recalled, **not verified**; the workjob
   header says the job type "carries no queryable product attribute",
   `df-overseer-workjob.lua:1115-1116`, but cites a file where this session
   found no such statement). If it reads, products come from it with status
   `verified_raws`-equivalent `game_data`. If it does not, the name rule moves
   into the ingest **once**, products marked `prior` with
   `source_ref: name_rule`, and the two aliases move with it as data.
3. **One source.** The workjob unsupplied read, `stockpile.health`/`plan-feed`
   and `orders.create`'s material defaults read the graph through the server
   (the `dfmcp/labor_join.py` pattern: Lua returns live facts only, the server
   joins game-data answers from the graph) **[verified pattern,
   `dfmcp/labor_join.py:1-10`]**. The Lua runtime derivation stays as the
   fallback when the graph is absent, and a **parity test** in the deploy check
   compares graph classes per kind against a live `derive_kind` run for all 33
   kinds, so drift is caught rather than hidden.
4. **The 145 generated `MAKE_ENT` reactions** already come from the running
   game (register 2026-09-21) **[verified]**; with D0 they gain flows too.

The cycle check (`production/extract.py:1157` `find_cycle`) runs over the
completed graph; the "no cycles" claim is still unproven for hard-coded jobs
(`docs/PRODUCTION-MODEL.md` section 17) **[verified]**, and D0 settles it.

### 10.2 `craft.how`

```
craft.how {item: "BED" | "DRINK" | node or class id, direction: make | use, depth: 1..4 (default 2), here: bool (default true)}
```

- Resolves `item` against node ids, classes and item types, case-insensitive;
  no match returns the three nearest names (the `zone.list-kinds` refusal
  shape).
- `make`: the OR set of processes producing it, each with workshop kind, labor
  (with the C2 status, never a bare empty list), reagents (class, quantity,
  consumption: consumed, occupied until released, occupied by the job,
  modified in place), products, and status; reagents expand to their own
  producers up to `depth`.
- `use`: the processes that consume it, and what they make.
- `here: true` adds, per process: built workshops of that kind (count and
  handles from the dossier), and per reagent a bucketed availability. That is
  the join; the walk itself stays in `production/`.
- Bounded: at most 6 routes per level, `+N more` line. No coordinates anywhere.

Example answer (from the live reads and the raws as the graph would hold
them; illustrative):

```
DRINK is made by BREW_DRINK_FROM_PLANT (and 2 more brew reactions) at Still [ws-5, built]:
  needs 1 brewable plant (consumed; fort: some, 117) and 1 empty food-storage barrel (occupied until the drink is drunk; fort: some, 27); labor BREWER (known).
  makes 5 DRINK of the plant's drink material, in the barrel, and the plant's seeds.
```

### 10.3 `craft.blockers`

```
craft.blockers {item, quantity (default 1)}
```

Runs `production.blocker.find_blocker` (`production/blocker.py:379`)
**[verified]** over a snapshot the server assembles:

- **Stock**: for reagents at a **built** workshop kind, the availability the
  game computes through its own item filter, from `workjob.list-jobs`
  (`has_material_reaction_product`, `unrotten`, `food_storage` applied by the
  game, **[live 2026-10-07]**), status `measured`. For a kind not built, the
  coarser `stocks.availability` by item type, status `prior`, because the
  filter is not applied. Both pass through `available_quantity`'s six
  deductions (`production/blocker.py` `DEDUCTION_FLAGS`) **[verified]**.
- **Buildings**: the workshop node's available count is the number of built
  workshops of that kind from the dossier (`blocker._requirements` treats the
  workshop as a reagent with quantity 1, `production/blocker.py:279`)
  **[verified]**.
- **Labor**: the labor join's status per process (`dfmcp/labor_join.py`), a
  separate line, since the walk does not model labor.
- Result: blocked or not; the named blocker (target, short by, path); each
  dead branch and why; the route that works; the weakest status touched; and
  the routing fact (absent fort-wide: Quartermaster; present but unlinked to a
  linked workshop: Logistics; no workshop of the kind: Planner or Architect).

Every read the snapshot needs is bounded by the walk's depth: one
`list-jobs` per built kind touched and one availability per item type touched.

### 10.4 `craft.workshop`

```
craft.workshop {kind | handle}
```

For a kind: hosted processes (count, the first 10 by name with `+N more`),
input classes aggregated (stockpile categories, role input, container or fuel,
how many of the kind's jobs need each, from the graph), output classes,
operating labors with their C2 status. For a built workshop handle,
additionally: its links, each input class's linked-source status, its output
link's acceptance and its open jobs and pinned orders. This is the graph view
`stockpile.plan-feed` and `stockpile.health` need; they become thin renderings
of it (section 11).

### 10.5 Generalisable by construction

No tool branches on a kind or item. Per-kind facts come from the game (job
definitions, reaction raws, Workers-tab labors); the only hand data are what
the game does not expose: item type to stockpile category
(`ITEM_TYPE_CATEGORIES`, `df-overseer-stockpile-kinds.lua:31`), fuel overlays
for non-magma furnaces, and feeder sizes (`FEEDER_TILES`, `:59`) **[verified]**.
Those move to one data file both the Lua tool and the server read, with a
parity test. The next workshop, item or reaction costs no code.

---

## 11. The crafting graph suggests logistics

### 11.1 `logistics.gaps`

```
logistics.gaps {scope: all | handle | kind | flow, include_planned: bool (default true)}
```

For each built workshop, each planned workshop (an accepted `workshop_siting`
or a reserved site of a workshop template), and from P3 each plan flow: take
the graph's input and output classes (10.4), compare them with the flow network
(9.1), and emit gaps. It subsumes `stockpile.health` (the per-linked-workshop
status) and `stockpile.plan-feed` (the per-kind dry-run spec); both stay as
names for compatibility until the Logistics role lands, then go.

### 11.2 A gap and its candidate fix

```yaml
gap:
  id: gap-3f9a1c              # hash of (kind, workshop handle or kind, class): stable while the gap persists
  kind: full_output | missing_feeder | missing_link | missing_output_pile | output_rejected
        | container_setting | long_haul | starved | absent_input
  workshop: ws-5
  class: {id: "product:food", label: "drink, in barrels", categories: [food]}
  evidence: [f-0110, f-0111, f-0201]          # dossier facts
  routed_to: logistics                         # or quartermaster for absent_input
  suggestion:                                  # null when no fix is computable
    proposal_type: stockpile_siting            # | stockpile_link | stockpile_settings
    draft:
      purpose: output
      classes: [food]
      finer: [drink]                           # only once finer filters are verified live
      size_tiles: 5
      adjacent_to: ws-5
      links: [{pile: new, target: ws-5, direction: take}]
      containers: {barrels: keep}
    sizing:
      basis: order_queue | measured_rate | default
      figure: "13 brew jobs queued x 5 drinks per barrel, 1 barrel per tile = 13 barrels; capped at 5 tiles by policy"
      status: prior | measured
  alternatives: ["reconfigure Stockpile #1 to drop stone (frees space for food)"]
```

**Sizing** follows the feeder rule (`research/2026-10-07-stockpile-logistics.md`
section 4: consumption rate times replenishment latency) **[verified]**:

- A **measured rate** from two observations (`production/cover.py`
  `depletion_rate_per_day`, two stock reads make an exact rate;
  `docs/PRODUCTION-MODEL.md` section 3) **[verified]** times a replenishment
  latency in days (policy, start 1), divided by items per tile. A feeder is
  no-bin, no-barrel (plan-feed's own rule, `df-overseer-stockpile.lua:1961-1968`)
  **[verified]**, so one item or stack per tile, which makes tiles an exact
  bound, not a guess.
- Without a measured rate: the queued demand (jobs plus order amounts left at
  that workshop), or `FEEDER_TILES` defaults. Marked `prior`.
- Always capped by policy and by `stockpile.place`'s 31 by 31 limit.

**Containers**: a suggested `container_setting` only from the stockpile
research's two named cases (feeders with bins and barrels at 0; a plant source
pile with barrels at 0, the "seed stockpile problem") **[verified]**, never a
number invented per kind.

### 11.3 What code does and does not do

- Code **computes** gaps and candidate fixes, deterministically, from facts.
- Code **does not file**. Logistics chooses: file the draft as is, change it,
  pick an alternative, or pass with a reason. The "link only with a reason"
  rule holds: a workshop with no links and no flag gets no suggestion to link.
- Code **routes**: an `absent_input` gap goes to the Quartermaster's lane (the
  unsupplied line), never to Logistics.

### 11.4 Provenance to the Overseer

Logistics proposals gain an optional `from_gap` field. At filing the server
checks the gap id exists in the current or previous dossier version and renders
it under the proposal in the Overseer's briefing and on the Board:
`from gap-3f9a1c (full_output, Still, drink): code suggested 5 tiles, sized from 13 queued brews (prior)`.
A proposal that changes the draft shows the diff. Not required: Logistics may
propose what code did not suggest (the plan's own flows, material policy).

### 11.5 Wakes

The Planner design's `logistics_watch.py` (`workshop_ready`, `feeder_starved`,
`output_blocked`, `flow_unrealised`, section 6.2) reads `logistics.gaps`
instead of `stockpile.health`, edge-triggered on gap ids, with the same F-8
backoff **[verified design]**. Its wake line carries the gap line and the
draft, so a typical wake is: read the line, file the draft or pass.

---

## 12. Walk-through on today's fort

Facts are the live reads of 2026-10-07 (section 1.1, F9). Logistics is not
enabled; this is what code would compute and show.

1. **Dossier core.** Four workshops built, two piles both full and both
   accepting six categories, no links anywhere, five bedroom and office sites
   (one finished with its Bed waiting on BED, three at shell), the farm, the
   well, the office zone. Rendered as section 4.2.
2. **Flow network.** As section 9.1. No workshop has a link, so there is no
   `unlinked-input`, `linked-source-empty` or `starved` flag: every workshop
   takes from anywhere, which is correct with no reason to restrict.
3. **Flags raised:**
   - `full-output` on every workshop: both piles that accept their products are
     full (25 of 25, 24 of 25). A Still that brews would leave drink in the
     workshop or on the floor; a Carpenter that makes a bed has nowhere to store
     it until it is installed.
   - The brewing chain (no flag: DRINK is a product, not an input). The chain
     line reads: brewing has plants (117) and barrels (27) and a built Still;
     drink is 0; the 13 brew orders are validated and **inactive**. That is the
     Quartermaster's (orders), and the orders handoff's live repair
     (`handoffs/2026-10-07-valid-manager-orders.md` item 5) is the fix in
     flight **[verified]**.
   - `waiting-building`: BED, 1 waiting, made at Carpenter's (built), nothing
     queued. Quartermaster, the unsupplied watch's existing line.
   - `long-haul`: the Still's nearest stated pile is Stockpile #1 at 4 tiles;
     the Carpenter's at 2. Below the 15-tile policy: no flag.
4. **Gaps and drafts `logistics.gaps` would emit:**
   - `gap (full_output, Still, food/drink)`: draft `stockpile_siting`, purpose
     output, classes food (finer: drink once verified), adjacent to the Still,
     size from the queue: 13 brew jobs at 5 drinks a barrel is 13 barrels,
     capped at 5 tiles by policy, status prior; barrels kept (drink is stored
     in its barrel). Alternative: reconfigure one pile to drop stone, freeing
     space for food.
   - `gap (full_output, Carpenter's, furniture)`: draft `stockpile_siting`,
     purpose output, classes furniture, adjacent to the Carpenter's, 4 tiles
     (default, prior). This also gives the bed somewhere to wait for
     installation.
   - No feeder drafts: no workshop is linked and none is far from its inputs.
     A plant source pile by the farm with barrels at 0 (the stockpile research's
     still pattern) would be a **plan flow** suggestion once the Planner names
     `farming -> brewing` (P3), not a gap today.
5. **What each role would see.**
   - Logistics (full): the flow network, two gap lines, two drafts. One wake,
     two `queue.propose` calls citing `from_gap`, or a pass.
   - Quartermaster (chains): "brewing: Still built, plants some, barrels some,
     drink 0, 13 orders inactive; beds: Carpenter's built, wood some (14), BED
     0, 1 building waiting, nothing queued." That is the whole decision, with no
     read.
   - Architect (minimal): site-4, 5, 6 at shell, site-3 finished and waiting on
     BED. Its focus on a `step_done` for site-4 adds site-4's near-relations.
   - Overseer (focus): for a Logistics proposal `from_gap`, the Still, both
     piles and the gap line.
6. **The difference from the sketch** (F9): the live fort has no dedicated
   plant or wood pile, so "the Carpenter takes wood from Stockpile #1" is not
   something the dossier may say; it may say "the nearest pile that accepts
   wood is Stockpile #1, 2 tiles", because which pile holds the 14 logs is not
   read by any tool today (`stockpile.list` gives accepts and fill, not
   contents by class). A per-pile contents-by-category read is a small gap
   (section 17, D1 item).

---

## 13. The unsupplied watch and the orders tool on the graph

### 13.1 Unsupplied watch

Today: the Lua read names producers by stripping the verb from the job name
(`df-overseer-workjob.lua:1115-1166`), and the conductor matches orders to
producers by job name and reaction (`conductor/unsupplied_watch.py:117`)
**[verified]**. The live read worked for BED **[live 2026-10-07]**, and it
listed a reaction `MAKE WOODEN BED` beside `ConstructBed`, which the name rule
alone would have missed or doubled depending on the order's fields.

With D0:

- The Lua read returns only live facts: needed item kinds and counts per
  planned building, built workshop kinds, queued job types and reaction codes,
  availability. No product table in Lua.
- The server joins producers from the graph: processes whose product node has
  item type X, with their workshop kinds, split into **built** (from the
  dossier) and **not built**. "BED: made at Carpenter's (built)" routes to the
  Quartermaster as now; "X: made only at a kind not built" routes to the Planner
  (an industry the plan lacks) or the Architect (a workshop to site), a case the
  watch cannot express today ("no built workshop offers a job making it").
- Queued jobs map to products through the same process ids, so "is a job
  making X now" uses the graph too.
- Order matching uses the process id (job type plus reaction), not a
  lower-cased name comparison.
- The conductor's `unsupplied_read` keeps its contract (rows in, items out);
  only the producer source changes. Its tests keep passing with graph-built
  fixtures.

### 13.2 Orders' material defaults

The orders handoff (in progress, `handoffs/2026-10-07-valid-manager-orders.md`)
owns `df-overseer-orders.lua` and a per-job data file for "which job types need
a material or material category, and its default" **[verified]**. This design
does not touch it. The relation:

- The ingested job item specs (D0 step 1) carry the job's material category
  (wood for `ConstructBed` at a Carpenter's, stone for `ConstructBlocks` at a
  Mason's), which is the same fact the handoff's data file encodes.
- After D0, a parity test checks the handoff's per-job table against the graph's
  material categories for every supported job; later the server can fill the
  default from the graph and the data file shrinks to the exceptions DFHack's
  order library shows (INORGANIC for stone jobs).
- `craft.how ... here: true` can then say which materials are on hand for the
  order, so the Quartermaster picks a category that exists.

---

## 14. Measures

### 14.1 Structural measures (per version, per role slice)

| Measure | Definition | Target to start |
|---|---|---|
| Completeness | live entities present in the dossier over live entities found by the **audit read** (14.2), per kind | 100% for workshops, piles, zones, sites |
| Accuracy | relations and statuses re-verified by the audit read and found equal, over all checked | 100%; any miss is a bug with the fact id |
| Freshness | per fact, ticks since its source changed (fingerprint or audit) and the dossier caught up; report max and median, and **stale facts** (source changed, version not yet rebuilt) | stale count 0 at each wake |
| Size | characters and tokens per role slice, per version | under the role cap |
| Churn | lines changed between consecutive rendered slices over total lines, and versions per game day | low; above about 30% a day says bucketing or hysteresis is wrong |

### 14.2 The accuracy audit must be able to fail

"Verify the verification" (`CLAUDE.md` rules): an audit that re-reads through
the aggregator that built the dossier can only agree with it. So the season
audit uses the **existing per-tool reads**, not `df-overseer-dossier.lua`:
`stockpile.list`, `stockpile.links` per pile and per workshop, `landmarks.list`,
`zone.list`, `blueprint.sites`, `queue.project_status`. A test seeds a fake
world where the aggregator and the per-tool reads disagree (a link added
between the two reads) and checks the audit reports it.

### 14.3 Effect measures, through `dfqueue/wake_metrics.py`

Already computed per wake **[verified, `dfqueue/wake_metrics.py:443-500` and
its schema header]**: `rounds`, `first_write_round` (rounds to first write),
`orientation_reads` (read calls before the first write), `read_calls`,
`redundant_reads`, the repeat measures M1, M2, M3 and R, `cost_usd`, tokens, and
per-tool call counts. Added for this design, as additive keys (no schema bump):

- per wake: `slice_mode`, `slice_version`, `slice_chars`, `slice_miss`,
  `slice_covered_reads`, `slice_sections_referenced`;
- per role and window: `slice_waste` per section.

### 14.4 Slice miss and slice waste

From the stored transcripts (captured per the 2026-10-07 transcripts decision)
plus the `slice_render` table (which handles each delivered slice showed):

- **Slice miss**: a read call in the wake whose arguments or result name an
  entity handle or display name that the role's `visible` filter admits and
  that was **absent** from the delivered slice, or present with a status or
  relation the read contradicted (stale). Counted per wake and per section the
  entity's kind belongs to. Meaning: the slice lacked something the role needed.
- **Covered read**: a read whose target entity was in the slice with the same
  facts. Meaning: the role pulled what it had been pushed (it did not trust or
  did not find it). Counted separately; a high rate says the rendering is
  unclear, not that the content is wrong.
- **Slice waste**: per section of a role's slice, across a window of W wakes
  (policy, start 10, the M1 window), the share of shown handles never
  referenced in the role's reasoning text, tool arguments or filing fields. A
  section with **zero** references in the window is dropped from that role's
  filter (a reviewed data change, not automatic); a section below a threshold is
  flagged.
- Matching is exact on handles and on display names (with duplicates resolved
  by handle); reasoning text is searched only for these strings. The published
  report carries counts and section ids only, never text, keeping
  `wake_metrics`'s "safe to publish by construction" rule.
- Tool-to-entity mapping is data (`dossier/tool_entities.yaml`: for each read
  tool, which argument or result field names an entity), so a new tool costs a
  data line.

### 14.5 Push versus pull, settled per role

For each role, two or three arms (`full`, `minimal`, `off`), switched by the
slice filter's `mode` (policy data, logged per wake in `slice_mode`):

- **Measures compared:** median rounds to first write, read calls per wake,
  orientation reads, slice miss and waste, cost per wake, and the repeat rate R.
- **Assignment:** epochs (`dfqueue/wake_epochs.yaml` already exists for exactly
  this) rather than random per-wake assignment, because a role's wakes cluster
  by fort state.
- **Power, honestly:** the notebook red team found an A/B could not show a
  repeat-rate effect at this wake rate (register 2026-10-07, "Agents stay
  one-shot") **[verified]**. Rounds and read calls vary less than repeats and
  move per wake, so they are the primary measures; R is reported, not decided
  on. For a role with few wakes (the Planner, about 4 a game year) no
  comparison is possible in reasonable time; its default stands on argument
  and on slice miss alone.
- **Decision rule (proposed, for the user to adjust):** after at least 15 wakes
  per arm for a role, keep the cheaper mode unless the richer one lowers median
  rounds to first write by at least 1 or read calls per wake by at least 2,
  with slice miss under 1 per 5 wakes. Otherwise the cheaper mode wins. Record
  the result in the register per role.

---

## 15. Tool counts per role

Live counts **[live 2026-10-07]**: overseer 82, architect 55, consultant 29,
quartermaster 28, conductor 37; planner 13 once enabled (`docs/STATE.md`)
**[verified]**; Logistics 14 as designed (Planner design 6.4).

| Role | Now | Added | Removed | After | Note |
|---|---|---|---|---|---|
| Logistics | (14 designed) | `logistics.gaps`, `craft.workshop`, `dossier.get` | `stockpile.health`, `stockpile.plan-feed` (subsumed) | **15** | full slice replaces most `stockpile.list`/`links` calls; those two are first in line for the evidence cut |
| Planner | 13 | `dossier.get`, `dossier.find`, `craft.how` | | **16** | P3 adds its own 3 (Planner design section 8) |
| Quartermaster | 28 | `craft.how`, `craft.blockers`, `dossier.get` | `workjob.list-jobs` (used inside `craft.blockers`; candidate, by evidence) | **30 or 31** | |
| Architect | 55 | `dossier.get` | | **56** | stockpile tools leave at stage L (Planner design) |
| Overseer | 82 | none | | **82** | focus slice only; ruling-only direction unchanged |
| Consultant | 29 | `craft.how` (recommended: it answers "how is X made" asks from game data instead of the wiki) | | **30** | |
| Conductor | 37 | `dossier.refresh`, `dossier.slice`, `logistics.gaps` | `stockpile.health` (if it was planned for the conductor) | **40** | code, width costs nothing per wake |
| Chronicler | (parked) | `dossier.get`, `dossier.find`, `dossier.changes`, `dossier.annotate`, `queue.project_status` | | **5** | |

New tools in total: `dossier.get`, `dossier.find`, `dossier.changes`,
`dossier.slice`, `dossier.refresh`, `dossier.annotate`, `craft.how`,
`craft.blockers`, `craft.workshop`, `logistics.gaps` (ten, all native reads
except `dossier.annotate`, a store write). Every per-role addition is a pull
tool the tool-cut rule may remove again if a role never calls it.

---

## 16. Cost per wake

Rates from the cross-run cache study: $0.435 per M uncached input, $0.0036 per
M cache read, $0.87 per M output; 17 measured runs cost $0.81, about $0.048 a
wake; output is 52% of cost, uncached input 45% **[verified,
`research/2026-10-07-cross-run-cache.md`]**.

- **Added cost of a slice**: at the caps (section 5.5, about 1,500 tokens for
  Logistics, 1,000 Planner, 800 Quartermaster, 400 Architect, 300 Overseer),
  round 1 pays it uncached at worst: $0.00065, $0.00044, $0.00035, $0.00017,
  $0.00013. Each later round re-reads it from cache: about $0.000005 a round.
  Per wake, under $0.001 for every role, about 1 to 2% of the average wake.
- **Saved cost of an avoided read round**: one round's output (reasoning plus
  the call, typically several hundred to 1,500 tokens, $0.0003 to $0.0013) plus
  the tool result entering later rounds uncached once (1,000 to 3,000 tokens,
  $0.0004 to $0.0013), roughly $0.001 to $0.003, more for wide reads like
  `landmarks.list`. **Break-even is one avoided read every one to three wakes.**
  Logistics replacing `stockpile.list` plus a `links` call per pile clears that
  easily; the Architect's minimal slice may not, which is why it is minimal.
- **Rebuild cost** is DFHack and SQLite time on VM 103, no model tokens: one
  fingerprint call per cycle, a full aggregator read only on change.
- **Chronicler** (parked): one cheap-model wake per batch of changes, a few
  cents, only if enabled.

---

## 17. Staged build plan

Every stage: one or more handoffs in the usual style (`git merge --ff-only
main` first, commit after each milestone, full ambient pytest with `lupa` on
`PYTHONPATH` and `dfmcp/tests` in `.venv-dfmcp` green, executors never write
`Working.md`, the register or `memory/`, no attribution lines, no em dashes).
Deploy targets use the names the Planner design uses.

### D0. Complete the graph (offline, then one bounded live read)

- **Files:** the building-tool dump script (extend with per-job item specs and,
  if the probe reads, `df.job_type.attrs` products); `production/labor_ingest.py`
  (reagent and product flows for `JOB:` processes, class nodes, the name rule as
  a marked fallback); `production/extract.py` cycle check over the result; a
  shared data file for `ITEM_TYPE_CATEGORIES`, overlays and feeder sizes.
- **Live:** one read-only probe of `df.job_type.attrs` for a dozen job types,
  and the extended dump, on VM 103; then the graph DB rebuilt at
  `/var/lib/dfproduction` per `handoffs/2026-09-21-deploy-building-batch.md`.
- **Tests:** `ConstructBed` at Carpenters has a wood reagent and a BED product;
  a `JOB:` flow from the name rule is `prior` with `source_ref: name_rule`;
  `find_blocker("BED")` finds Carpenters as producer; `MAKE_ENT` reactions keep
  their rows; cycle check reports none or names the cycle; the parity test
  (graph classes per kind against `derive_kind` on the fake world) passes and
  fails when one side changes.
- **Deploy:** the graph DB on VM 103 (vm103-dfmcp reads it). Nothing agent-facing
  changes.

### D1. Dossier core and pull tools

- **Files:** `scripts/dfhack/df-overseer-dossier.lua` (`fingerprint`,
  `structure`, by `reqscript`) and `TOOLS.yaml`; a per-pile contents-by-category
  read (small, in the stockpile tool, for "which pile holds the wood"); new
  `dossier/` package (`schema.py`, `assemble.py`, `render.py`, `store.py`,
  `slices.yaml`, `tool_entities.yaml`); native `dossier.get`, `dossier.find`,
  `dossier.changes`, `dossier.refresh`, `dossier.slice` in `dfmcp/`; the
  `ReadWritePaths` line for `/var/lib/dfdossier`; roles' `tools.yaml`
  (pull tools only; no slice in briefings yet).
- **Tests:** the same schema renders the same bytes (golden file); bucketing
  keeps the body stable when a pile goes 24 to 25 of 25 under the same bucket;
  duplicate landmark names get distinct handles and a `(2)` display;
  coordinates refused anywhere in the store; a fingerprint change triggers a
  version and an unchanged one does not; the change list is right;
  `recent_changes` is capped; `visible` refuses a kind outside the role's set
  naming who sees it; a removed building turns a relation off, not stale.
- **Deploy:** vm103-dfhack-scripts, vm103-dfmcp; regenerated `docs/STATE.md`
  counts and a live probe that tool counts match. **Live check:** `dossier.get`
  on the Still and both piles agrees with the per-tool reads (the audit,
  section 14.2), run by hand.

### D2. Slices in briefings, and the metrics

- **Files:** `conductor/briefing.py` (`fort_dossier` key first, focus after the
  stable body); `conductor/cycle.py` (call `dossier.refresh` once a cycle, then
  `dossier.slice` per woken role with the wake's seeds); policy for caps and
  trigger cadence; `dfqueue/wake_metrics.py` (slice keys, slice miss, covered
  reads, slice waste, by section); the stream publisher carrying the new keys.
- **Tests:** each wake reason maps to the expected seed handles; focus hops
  respect the role's relation kinds; a slice over its cap ends in the overflow
  line; slice miss counts a read of an admitted absent entity and not a read of
  a non-admitted one; covered reads counted apart; waste zero-reference
  sections reported; published report has no free text.
- **Deploy:** vm106-conductor, vm103-dfmcp, vm103-stream-publisher. Start with
  the defaults of section 5.4 except Logistics (not yet a role).
- **Live check:** a supervised `--once` cycle; the briefing shows the slice;
  the stable body's bytes equal across two cycles with no fort change.

### C. Crafting search tools (needs D0; parallel with D1 and D2)

- **Files:** native `craft.how`, `craft.blockers`, `craft.workshop` in
  `dfmcp/` over `production/` (snapshot assembly from `workjob.list-jobs`,
  `stocks.availability`, the dossier's built-workshop counts, the labor join);
  allowlists per section 15.
- **Tests:** `craft.how DRINK` lists the brew reactions at Still with the
  barrel's consumption `occupied_until_released`; `use PLANT` includes brewing;
  an unknown item names three nearest; `craft.blockers BED` with no wood names
  wood short; with wood and no Carpenters names the workshop; with both, not
  blocked, route `ConstructBed` or the reaction; a reagent read from
  `list-jobs` is `measured`, one from `stocks.availability` is `prior`; labor
  `unknown` is never an empty list; no coordinate in any result.
- **Deploy:** vm103-dfmcp, vm106-agents. **Live check:** the three tools on the
  Still, the Carpenter's and BED against section 12.

### L+. Logistics gaps (lands with the Planner design's stage L)

- **Files:** native `logistics.gaps` (graph plus dossier plus `cover.py`
  sizing); `dfqueue/schema.py` (`from_gap` on Logistics proposal types,
  validated against the dossier); Board and Overseer briefing rendering of the
  gap under the proposal; `conductor/logistics_watch.py` reading gaps by id;
  `stockpile.health` and `plan-feed` retired from allowlists.
- **Tests:** each gap kind on a fake fort; a workshop with no links raises no
  feeder gap; `absent_input` routes to the Quartermaster; sizing from a
  measured rate, from the order queue, and from the default, each with its
  status; the gap id is stable across rebuilds while the gap persists; a
  proposal citing a gap id that never existed is refused; a draft changed by
  Logistics shows the diff.
- **Deploy:** with stage L's (vm103-dfhack-scripts, vm103-dfmcp, vm106-agents,
  vm106-conductor).

### U+. Unsupplied watch and orders on the graph (after D0)

- **Files:** `df-overseer-workjob.lua` unsupplied (product table removed, live
  facts only), the server join, `conductor/unsupplied_watch.py` (process-id
  order matching, not-built routing); a parity test against the orders
  handoff's per-job material table.
- **Tests:** BED with a built Carpenter's routes to the Quartermaster; an item
  made only at an unbuilt kind routes to the Planner (when enabled) or the
  Architect; an inactive order for the process is named; existing
  `unsupplied_watch` tests pass on graph-built fixtures.
- **Deploy:** vm103-dfhack-scripts, vm103-dfmcp, vm106-conductor.

### D3. Push versus pull, per role

- Run the epochs of section 14.5 during the unattended stretches the rollout
  order already plans (`Working.md`, order agreed 2026-10-07, item 4)
  **[verified]**. Report per role; the user rules; the slice filter data
  changes. Waste-driven section drops reviewed at the same time.

### D4. Chronicler annotations (parked)

- Only after D3 shows the code-built dossier pays, and after open question 1.
  `agents/chronicler/{role.md,tools.yaml,model.yaml}`, `dossier.annotate`, the
  staleness rule, the rendering of annotations.

---

## 18. Open questions for the user

1. **May the Chronicler's notes reach the agents who decide?** Its charter says
   it must never be able to influence what the fort does
   (`agents/chronicler/role.md:17-18`); a note in a dossier slice does. (a) Yes,
   rewrite that line to "never proposes or rules; its notes cite their sources
   and are marked as notes"; (b) no, notes go only to the Board and the
   chronicle, never into slices. **Recommendation: (b) for now.** Code already
   derives purpose from provenance and the plan (7.1); notes can join slices
   later if the measured dossier shows a gap only meaning fills.
2. **The push/pull decision rule** (14.5): at least 15 wakes per arm; the richer
   mode stays only if it saves a round to first write or two read calls per
   wake with few misses. **Recommendation: accept it as the default rule**,
   with the Planner's mode decided by argument (too few wakes to measure).
3. **Do `stockpile.health` and `stockpile.plan-feed` retire into
   `logistics.gaps`** before they are ever deployed, rather than going live and
   being replaced? **Recommendation: yes**: deploy them only for the live
   verification of the stockpile verbs (Planner design 6.6 item 7), keep them
   off every role's allowlist, and give Logistics `logistics.gaps` from the
   start, so no role learns two tools for one job.

---

## 19. Risks and what is not verified

- **Not verified:** whether `df.job_type.attrs[job].item` names the product
  (D0's probe decides; the fallback is the name rule, marked `prior`); whether
  the extended dump's item specs match `derive_kind`'s reading field for field
  (the parity test decides); the level difference between any two entities
  (F4, needs the F-23 relation read); any "via" (F5); which pile holds which
  items (needs the contents read in D1); `links_only` polarity and container
  write verbs live (Planner design 6.6 item 7).
- **A wrong dossier misleads more than no dossier.** A stale "linked" relation
  could make Logistics skip a fix. Mitigations: rebuild on fingerprint change,
  the season audit through independent reads, freshness at each wake, and the
  pull tools' `exact` mode. A slice is never shown with a stale fact unmarked:
  a fact whose source changed and is not yet rebuilt renders with `(checking)`.
- **The slice becomes a map by accident.** Lists sorted by geometry, or a
  "north side / south side" grouping, would arrange text to mirror the layout.
  The renderer sorts only by kind and handle, and a test checks that the order
  of entities does not depend on position.
- **Too much push.** A role reading a large slice may reason longer. The waste
  measure and the per-role arms exist to catch it; the caps bound the worst
  case.
- **Three derivations become four.** If D0 is skipped and the crafting tools
  read the graph while the Lua tools keep their own rules, a fourth answer
  appears. D0 first, and the parity test in the deploy check, are the guard.
- **Live finding outside this design:** the fort has 0 drink, with plants,
  barrels and a Still, and 13 inactive brew orders **[live 2026-10-07]**. The
  fort is paused; this is the orders handoff's repair, flagged here so it is not
  lost.
