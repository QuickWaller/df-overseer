# Red team: the fort dossier and the crafting-graph search

Date: 2026-10-07. Target: `research/2026-10-07-fort-dossier-and-crafting-search.md`
(revision 1, "the design" below). Read-only review: code, docs and register read
at the cited lines; four read-only MCP calls on VM 103 (`stockpile.list`,
`landmarks.list` as the Architect, the per-role `counts`), no game writes.

Marking: **[verified]** read at the cited `file:line` this session; **[live
2026-10-07]** read through the real MCP server this session; otherwise
reasoning.

## Verdict

The direction holds: a code-built, typed, per-role picture of the fort, text as
a pure function of it, the crafting graph made searchable, gaps computed by code
and chosen by an agent. Most of the design's citations check out (list at the
end). But **it is not ready to build as written.** Two premises are wrong in
ways that change the stages:

1. **D0 cannot complete the graph.** Its source for hard-coded jobs,
   `dfhack.workshops.getJobs`, is DFHack's own hand-written advfort table,
   covering 16 of 33 kinds and 50 job types. Craftsdwarf's, both forges,
   Bowyer's, Clothier's, Tanner's and Kennels have no hard-coded jobs in it at
   all (finding 1).
2. **The relation reads the schema is built from cannot produce its relations.**
   Landmark exits are keyed by name, carry no building id, no "exists" flag and
   no level, cover only the 3 nearest named things, and already have a duplicate
   name live. The stockpile list's "near landmark" is the pile itself at
   distance 0, live (findings 3 to 5).

Below those, the measurement plan cannot decide push versus pull at our wake
rate and has no quality guard (finding 13). `visible` does not bound what a role
sees while the legacy reads stay on its allowlist (finding 10). The `full`
flag, which drives the walk-through's headline gap, misreads both the pile data
and the design's own rule (finding 6). All are fixable. The changes required
before D0 and D1 are listed at the end.

Severity counts: 2 blockers, 12 major, 10 minor.

---

## Findings

### 1. D0 cannot complete the graph: `getJobs` is a partial, hand-written table (blocker, D0)

**Claim.** Design 10.1 step 1: reagents of hard-coded jobs "from the game's own
job definitions", via `dfhack.workshops.getJobs`; step 3: a parity test "for
all 33 kinds"; section 0 item 7: "the crafting graph becomes searchable and
complete".

**Evidence.**
- `handoffs/2026-09-21-building-tool-lua.md:240-244` **[verified]**: "S1,
  `dfhack.workshops.getJobs`: a hand-written table (from DFHack's advfort) plus
  the raws' reactions. Hard-coded jobs cover only **16 of 33 kinds and 50
  distinct job types**; Craftsdwarfs, Metalsmith's and Magma Forge, Bowyers,
  Clothiers, Tanners, Kennels and Still have none, and its own comments mark the
  forges unfinished."
- `research/2026-09-21-building-requirements.md:71` **[verified]**: the same
  table "is not maintained as authoritative", with one line referencing an
  undefined global.
- `production/labor_ingest.py:31-34` **[verified]**: the graph's `JOB:`
  processes come from that same S1 dump, so for the uncovered kinds there are
  not even processes to hang flows on.
- Register 2026-09-19 (`decisions/DECISIONS.md:403`) **[verified]**: the first
  live blocks job copied DFHack's spec faithfully (`flags3.hard=true`) and the
  dwarf cancelled it on shale, so even where the table exists it can be stricter
  than the game.
- `scripts/dfhack/df-overseer-stockpile-kinds.lua:216-221` **[verified]**: for
  kinds where `derive_kind` fails it falls back to `FALLBACK_KINDS`,
  "HAND-AUTHORED from the wiki, unverified". A parity test "for all 33 kinds"
  therefore compares graph data against hand data for about half the kinds.

**Why it matters.** After D0, `craft.how` answers "how is a bed made" but not
"how is a pick made", and a pick was the actual blocker on 2026-10-05: one pick
in the fort and no Forge to make another (`Working.md` line 35, the 2026-10-05
diagnosis) **[verified]**. The walk-through only touches Carpenter's and Still,
which hides the hole.

**Fix.**
- Restate D0's goal as "complete where a game-side source exists, and say per
  kind where it does not". Every `craft.*` answer carries a per-kind
  `coverage: game_table | dfhack_table | observed | wiki_prior | none`, and
  `none` is a stated answer ("no source for Forge jobs"), never an empty list.
- Add a read-only **observed route**: when the game itself creates a job (from a
  manager order or a player add-job), its `job_items` are the game's own reagent
  specs. Harvest them from live jobs into the graph with status `observed` and
  the job id as provenance. This fills kinds as the fort uses them, with no
  writes.
- For the rest, the Consultant's wiki mirror supplies `prior` reagent lists,
  labelled as such (`docs/PRODUCTION-MODEL.md` section 16, "status stays visible
  in every view").
- Scope the parity test to the kinds with a getJobs entry, and name the others
  as "parity not applicable: fallback hand data".

### 2. The D0 probe is better founded than the design says, and aimed at the wrong jobs (minor, D0)

**Evidence.** The design says the workjob header cites a file "where this
session found no such statement". The cited file does make a statement, and it
contradicts the workjob header: `scripts/dfhack/df-overseer-orders.lua:51-54`
**[verified]** lists `df.job.xml`'s `job_type` enum-attrs at the pinned tag as
"caption/type/labor/item/possible_item/material/skill*/is_designation". So an
`item` attribute is recorded as existing. `df.job_type.attrs[job].skill` is
already read live (`docs/BUILDING-TOOL.md:83-84`) **[verified]**, so the attrs
table is reachable.

**Why it matters.** The probe is likely to succeed for one-product jobs, and
that makes the name rule's retirement realistic. But the hard cases are jobs
whose product is not one item type: `MakeCrafts` (several craft types), and
`MakeTool`, `MakeWeapon`, `MakeArmor`, `MakeTrapComponent`, `MakeAmmo`, whose
product depends on the item subtype of the job or order. A probe on "a dozen
job types" that picks easy ones will pass and prove nothing about these.

**Fix.** Fix the workjob header's citation. Name the probe set: at least
`ConstructBed`, `ConstructThrone`, `ConstructChest` (the two aliases),
`MakeBarrel`, `MakeCrafts`, `MakeTool`, `MakeWeapon`, `MakeTrapComponent`,
`ConstructBlocks`, and read `possible_item` beside `item`. Products that depend
on subtype take the subtype from the getJobs entry or the order, and are marked
so.

### 3. Relations from existing reads cannot be keyed by handle (blocker, D1)

**Claim.** Design 2.1: handles are building ids, names are display only; 2.3: a
relation is "stated by a tool or by the store"; 2.5:
`{kind: near, from: ws-5, to: pile-1, ...}`.

**Evidence.**
- Landmark exits are keyed by name: `to = b.name`
  (`scripts/dfhack/df-overseer-landmarks.lua:243`) **[verified]**, and the
  model-facing list strips coordinates and carries no id
  (`:285-294`) **[verified]**. Nothing in `landmarks.list` names a building id.
- Same-name landmarks are excluded from each other's exits:
  `if a ~= b and a.name ~= b.name` (`:238`) **[verified]**.
- Two landmarks are named `shale Throne` **[live 2026-10-07]**. `Activity Zone
  #3`'s first exit is "shale Throne, S, 0 tiles": which one cannot be told from
  the read.
- Landmarks enumerate every named building with no `flags.exists` check
  (`:160-175`) **[verified]**; the live list includes a `Bed` that the design
  itself says is a planned building waiting on BED **[live 2026-10-07]**. So
  near-relations already run to and from buildings that do not exist yet,
  rendered like built ones.
- `stockpile.list`'s `near_landmark` is the pile itself: both piles return
  `near_landmark: "Stockpile #N", distance_tiles: 0` **[live 2026-10-07]**,
  because `nearest_landmark` (`landmarks.lua:415-432`) **[verified]** does not
  exclude the querying building.
- `blueprint.sites` reports `near_landmark` by name only
  (`df-overseer-blueprint.lua:1544-1547`) **[verified]**.

**Why it matters.** The dossier would have to join relations to handles by
display name, which fails exactly where F3 says it must not. "Coordinates never
leave Lua" is right, and it means the join must happen in Lua too: the server
cannot recover ids afterwards.

**Fix (before D1, small).** In `df-overseer-landmarks.lua`: carry the building
id (or zone id, site handle, seed id) on each landmark and on each exit
(`to_id`), carry `exists`, drop the `a.name ~= b.name` exclusion (compare ids),
and exclude the caller in `nearest_landmark`. The design's "no new game
interpretation" rule for the aggregator survives; this is a change to an
existing read, with its own tests. Use the same ids in `stockpile.list` and
`blueprint.sites`.

### 4. Top-3 nearest exits will not hold the workshop-to-pile relations (major, D1)

**Evidence.** `MAX_EXITS_PER_LANDMARK = 3` (`landmarks.lua:125`), sorted by
straight-line distance across every named building, zone and burrow
(`:234-264`) **[verified]**. Live today, with 20 landmarks and one Bed
**[live 2026-10-07]**: the Mechanic's third exit is a `Wall` construction; the
Still's are the Stoneworker's, `Activity Zone #4` and Stockpile #1; five
`Activity Zone #N` entries and the furniture take most slots. Each bedroom adds
a bed, a door, perhaps a cabinet and a zone.

**Why it matters.** The flow network section (9.1) and its `long-haul` flag
lean on these relations. The flag's second clause, "or is not among the
workshop's stated near-relations at all" (9.2), will fire whenever a door is
built next to a workshop. That would be a false flag, sent to Logistics with a
draft.

**Fix.** A typed relation read, computed in Lua, for the pairs the slices
actually use: per workshop, per input and output class, the nearest pile that
accepts it, with distance, level difference and reachability; per pile, its
nearest workshop. This is the F-23 relation read the Planner design already
owes (`research/2026-10-07-planner-design.md:74`) **[verified]**, given
purpose-typed targets instead of "closeness pairs". Delete the "not among
near-relations" clause from `long-haul`.

### 5. Distances ignore levels, and this fort spans levels (major, D1)

**Evidence.** `direction_and_distance` uses `dx, dy` only
(`landmarks.lua:129-135`) **[verified]**; so does `nearest_landmark`. The fort
has dug rooms below the surface: `df-overseer-chokepoints.lua` header records
the sole stair between z168 and z169 on Uniboslan **[verified]**. The design
admits `level: unknown` (F4) but still renders "Stockpile #1 N 4" as if it were
a distance.

**Why it matters.** A pile directly above or below a workshop reads 0 tiles and
"adjacent". `long-haul` and gap sizing both read this number.

**Fix.** The level difference is already in hand in Lua. Add `levels: n` (a
signed count, not a coordinate) to every exit and relation in the same change
as finding 3, so D1 need not wait for F-23. Until then, render a cross-level
pair as "on another level, reachable", without a tile count.

### 6. "Full" and the `full-output` flag misread the pile data, and the walk-through contradicts its own rule (major, D1 and L+)

**Evidence.**
- `occupied_tiles` counts distinct item positions (`df-overseer-stockpile.lua:331-348`)
  **[verified]**. A tile holding a bin or barrel can take more items of a
  bin- or barrel-stored class. `docs/PRODUCTION-MODEL.md` section 8 says it in
  as many words: "Report occupied tiles over total tiles, not percentage of
  capacity, because per-tile capacity depends on containers and that figure is
  not established" **[verified]**.
- `containers` are the pile's **maximum** settings: live `max_bins: 25,
  max_barrels: 25` **[live 2026-10-07]**. Design 2.5, 4.2 and 9.1 render them
  as "bins 25, barrels 25", as if present.
- Design 3.5 defines `full` as "all tiles"; 4.2, 9.1 and 12 render Stockpile #2
  at 24 of 25 as `full`. Rule 9.2 raises `full-output` when "no pile with a free
  tile accepts a product class". Stockpile #2 has a free tile, so by the
  design's own rule section 12's headline gap does not fire.

**Why it matters.** The walk-through's main output (two `stockpile_siting`
drafts) rests on this flag. A computed flag that disagrees with its own
definition on the one live example is what a model will learn to distrust.

**Fix.** Rename the fact to `tiles_free` and render it as such. Raise
`full-output` only when `tiles_free = 0` for every accepting pile **and** the
product class is not container-stored, or when observed: finished products of
the class lying outside any pile or on the workshop tile (a small read, to add
beside the contents read). Render container settings as "up to N bins". Correct
4.2, 9.1 and 12.

### 7. Staleness: the fingerprint misses connectivity, and the "(checking)" promise is circular (major, D1)

**Evidence.** The fingerprint (3.1) covers building ids, types, `exists`, zones,
pile settings, links, site phases and planned-building waits. It has no
reachability term. Digging, a channel, a removed stair, a locked door, a
flooded corridor or a finished construction change reachability without
changing any of those. (A finished wall leaves `buildings.all`; the design
would see that one, but not a dug passage.) Risk 19 promises that "a fact whose
source changed and is not yet rebuilt renders with `(checking)`". Only the
fingerprint can tell that a source changed, and when it does, it triggers a
rebuild. So `(checking)` can only appear for changes nothing detects.

**Why it matters.** "A wrong dossier misleads more than no dossier" (design 19).
A `reachable` relation that has gone false is the costly lie: Logistics or the
Architect would act on a path that no longer exists, and nothing would notice
before the season audit.

**Fix.** Add per entity the walkability group id of its standable tile to the
fingerprint (the shared reachability helper already resolves it), so any change
in connectivity among dossier entities triggers a rebuild. Make the existing
`connectivity.report` stranded alerts a trigger. Replace `(checking)` with an
honest per-slice line: "built at game day N, structural check this cycle". Keep
volatile facts (fill, stock) out of the reachability claim.

### 8. The accuracy audit cannot catch the errors that matter (major, D1)

**Evidence.** Design 14.2 runs the audit through "the existing per-tool reads,
not `df-overseer-dossier.lua`". But the aggregator is built "by `reqscript`
over the existing modules" (3.1): it calls the same `list_stockpiles`,
`list_landmarks` and link reads. Completeness's denominator, "live entities
found by the audit read", comes from the same enumeration, which lists only
buildings with a non-empty `getName` (`landmarks.lua:160-175`).

**Why it matters.** The audit catches assembly, serialisation and timing bugs.
It cannot catch an interpretation error shared by both paths: z-blindness
(finding 5), unbuilt buildings as landmarks (finding 3), occupied-tile
semantics (finding 6), or wildcard reagents skipped by the unsupplied read
(`df-overseer-workjob.lua:1112-1113`) **[verified]**. By construction it
reports 100% completeness. That is exactly the case "Verify the verification"
(CLAUDE.md) forbids.

**Fix.** Add an independent enumerator: a few lines over
`world.buildings.all`, `world.buildings.other.ACTIVITY_ZONE` and the
blueprint store by type and `exists`, sharing no code with the landmark path.
Use it as completeness's denominator. At each stage's live check, add one
comparison against the user's own view on VNC (memory: trust the user's direct
observation over an inferred read). State in the design which error classes the
audit can and cannot detect.

### 9. The per-wake focus has nothing structured to seed from (major, D2)

**Evidence.** `Wake` is `reason, detail, roles, clock`, with `detail` free text
(`conductor/triage.py:46-53`) **[verified]**. When several wakes name a role,
`merged_wake_for` concatenates their details into one string under the first
reason (`:159-170`) **[verified]**. Design 5.2's table maps reasons to seed
handles as if wakes carried entity references. They do not.

**Fix.** Before D2, add a `subjects` tuple of typed references (project id, site
handle, building id, item type) to `Wake`, `LaneWake` and `PlanWake`, filled by
each watch that already knows them. Keep it through merging. This is also the
natural key of an inbox item, so settle its shape in the owed inbox and session
design session rather than separately (finding 19).

### 10. `visible` does not bound what a role sees (major, D1 and D2)

**Evidence.** Design 5.3: "`visible` bounds what the pull tools return for a
role ... The server enforces it." But the legacy reads stay on the allowlists:
the Quartermaster holds `stockpile.list` and `stockpile.links`
(`agents/quartermaster/tools.yaml:113-120`); the Consultant, slice `off`, holds
`landmarks.list` and `overview.get` (`agents/consultant/tools.yaml:18-21`); every
role holds `overview.get`, whose tier1 is the full landmark table
(`df-overseer-overview.lua` header, "list_landmarks() for tier1")
**[verified]**.

**Why it matters.** The per-role filter is a filter on one tool among many, not
a need-to-know boundary. The slice-miss measure is also biased: a role that
reads `landmarks.list` instead of `dossier.get` produces a "miss" only if
`tool_entities.yaml` maps that result, which truncation prevents (finding 12).

**Fix.** Say what is true: `visible` scopes the dossier tools. Pair each slice
entry in `slices.yaml` with a `replaces:` list of the legacy reads it is meant
to make unnecessary. Feed those to the evidence-based tool cut (register
2026-10-07, line 638) **[verified]**, so the boundary becomes real once the
legacy reads go.

### 11. A `full` Logistics slice is Tier 2 by the architecture's own table, and truncation drops the newest buildings (major, D2)

**Evidence.** `docs/AGENT-ARCHITECTURE.md:603-608` **[verified]**: Tier 2 is
"per-unit, per-stockpile, per-job drill-down ... never in a default prompt,
which is what keeps principle 7 true". F6 places the dossier in Tier 1, but the
Logistics `full` slice pushes per-pile fill, accepts, containers and links:
per-stockpile drill-down. Caps (5.5) cut lists "at a whole entity", and entity
order is "kind, then handle number" (4.1). Handle numbers are building ids,
assigned in build order, so a capped list keeps the oldest buildings and drops
the newest.

**Why it matters.** Today's fort (4 workshops, 2 piles) fits; the measurement
in D3 will be taken on it. A mature fort has dozens of each. There `full` stops
being full, and what it drops is the workshop that was just built, the one a
`workshop_ready` wake is about. A D3 verdict reached at 4 workshops does not
carry over to 30.

**Fix.** Either record an amendment to the tier rule in the register (a
Logistics-scoped Tier 1.5, capped), or push only flagged entities plus the
focus, with the rest pull. In both cases, truncate by relevance (focus, then
flagged, then recently changed, then the rest by handle), not by handle alone.
Re-run the D3 comparison when the fort crosses a size threshold set in policy.

### 12. Slice miss and slice waste are not computable as specified from stored data (major, D2)

**Evidence.**
- Transcript caps (`conductor/runner.py:131-137`) **[verified]**: tool results
  clipped at 800 characters, round text and reasoning at 2,000, the whole
  transcript at 60,000 with later rounds dropped (`:256-262`). A live
  `landmarks.list` result is about 10 KB **[live 2026-10-07]**, so slice miss
  "by result" sees only its first few entries.
- Display-name matching (14.4) against reasoning text: four of today's names are
  common English words (`Still`, `Well`, `Wall`, `Bed`) **[live 2026-10-07]**.
  "Still" alone will match most reasoning paragraphs, so waste will be
  undercounted.
- `wake_metrics.compute` reads two SQLite files, the queue and the runs store
  (`dfqueue/wake_metrics.py:9-14`) **[verified]**. The `slice_render` table
  that says which handles a wake was shown lives in a third store on VM 103
  (design 8.1). The join is unspecified.

**Fix.** The conductor writes, per run row: `slice_mode`, `slice_hash`,
`slice_version` and the shown handle list (ids only, so publishable). Match on
structured tool arguments and on bracketed handles only; match a display name
only when it is unique and not a dictionary word, or not at all. Count a read
toward miss only when its arguments name the entity, or its result is
untruncated. Report the share of wakes where truncation made the measure
undefined.

### 13. The push-versus-pull rule cannot decide anything at our wake rate, and it ignores decision quality (major, D3)

**Evidence.**
- The notebook red team sized rounds at "about 80 per arm per stratum"
  (`research/2026-10-07-notebook-red-team.md:463-464`) **[verified]**. The
  design's rule uses 15 per arm, with a fixed threshold on a median. The design
  cites the same red team for R but not for rounds.
- Wake rate: the conductor is disabled and runs only by hand (CLAUDE.md status;
  `Working.md` "Order agreed 2026-10-07" item 4: "a short unattended stretch
  with the user watching") **[verified]**. The cache study measured 17 runs in
  total. Two to three arms, times four roles, times 15 wakes, is 120 to 180
  wakes, before stratifying by wake reason.
- Epoch assignment confounds the arm with fort state and with deploys, which
  are frequent (notebook red team finding 13, cited at `:467-468`).
- Logistics has no roster entry (`agents/ROSTER.yaml`, no `logistics` key)
  **[verified]**, so its "likely full" default cannot be measured either.
- The measures are effort only: rounds, reads, cost. A role that reads nothing
  and files a poor proposal wins the rule.

**Fix.** Use a **paired, same-state design** instead of epochs. The fort sits
paused most of the time. Run the same wake twice, back to back, on the same
paused state: once per arm, under the operator hold, with the proposal filed to
a scratch queue (or `dry_run`), not the live queue. Every pair shares fort
state, so the confound goes and the variance halves. About 15 to 20 pairs per
role becomes a defensible number. Cost is about $0.05 a run (design 16). Add a
quality guard: the paired proposals are compared blind, by the user or a
grader, and the richer arm may not lose on quality. Keep epochs only as a
confirmation once a mode is chosen.

### 14. `logistics.gaps` sizing has no measured-rate data, and "two reads make an exact rate" is the wrong rate (major, L+)

**Evidence.** `cover.depletion_rate_per_day` needs two `production_observation`
rows (`production/cover.py:22-25, 164-196`) **[verified]**. The only writer of
that table is the extractor's `write_all` (`production/store.py:173`)
**[verified]**; nothing writes live stock observations. `dfseries` holds unit
vitals, not stock by class (`dfseries/metrics.py` header) **[verified]**. And
what two fort-wide stock reads give is net change, harvests minus every
consumer. It is not one workshop's draw on one input class, which is what a
feeder's size needs. The walk-through's figure, "13 brew jobs queued", is 13
**inactive orders** (F9), not queued jobs.

**Fix.** At L+, size from queued demand (open jobs plus order amounts left at
that workshop) or from `FEEDER_TILES`, both marked `prior`. Defer
`measured_rate` until a per-class stock series exists. Measure a workshop's draw
from job completions at that workshop (diff events), not from net stock. Fix
the walk-through's wording.

### 15. Tool growth runs against the user's narrow-agents and "cut it down" calls (major, D1 and C)

**Evidence.** Live counts match the design: overseer 82, architect 55,
consultant 29, quartermaster 28, conductor 37 **[live 2026-10-07]**. The design
adds ten tools. The Planner goes from 13 to 16 (19 with P3's own three), the
Quartermaster to 30 or 31, the Consultant to 30. Pull tools go to roles whose
slice is `full`, which is redundant by the design's own logic. `dossier.changes`
and `dossier.annotate` serve only a parked role. The register's latest calls:
"narrow agents, short turns" and "cut every role's tools hard, by evidence"
(`decisions/DECISIONS.md:630, 638`) **[verified]**.

**Fix.**
- Build `dossier.get` only, with `kind` and `status` filters absorbing
  `dossier.find`.
- Merge `craft.how`, `craft.blockers` and `craft.workshop` into one `craft`
  tool with a `mode`, or ship `craft.how` alone first.
- Grant pull tools only to roles in `minimal` or `off` mode. Add one elsewhere
  only on a refusal or a measured slice miss.
- Do not build Chronicler-only tools until D4.

Net per role: +1 at most at D1.

### 16. `waiting_on` cannot be per building from the existing read (minor, D1)

**Evidence.** `unsupplied_buildings` returns per item kind a count of planned
buildings and units, no building ids (`df-overseer-workjob.lua:1185-1220,
1286-1293`) **[verified]**. It sees only buildingplan-planned buildings
(`:1180-1183`) and skips wildcard elements such as "any wood" (`:1112-1113`).

**Fix.** Add the building ids per row in D1's small read changes, and render a
wildcard wait as "waits on any wood", not as no wait.

### 17. "They connect via z" is the user's sentence and has no delivery plan (minor, design)

**Evidence.** F5 and 2.3 mark `via` as a gap. The only candidate source,
`chokepoints`, "flags EVERY stair/ramp tile in the box, without proving it is
the SOLE connector" (`df-overseer-chokepoints.lua` header) **[verified]**. The
reachability helper's `from_via`/`to_via` mean "at or adjacent", not a path.

**Fix.** Say at the top of the design that D1 delivers "built, linked, reachable,
same or other level" and that "via" waits on the relation read. Ask the user
whether that is acceptable for now, since it is their own sentence. When it
comes, the cheapest honest "via" is a graph-cut check on the stair candidates
chokepoints already lists, for pairs on different levels.

### 18. Small factual drift in the design (minor)

- `zone.list` "needs `kind_filter` and `owner_filter`" (1.1): it already has
  both, `list KIND_FILTER OWNER_FILTER VALID_FILTER NEAR_LANDMARK_FILTER`
  (`scripts/dfhack/TOOLS.yaml:2276`; `df-overseer-zone.lua:1615`) **[verified]**.
- `queue.project_status` takes one project id (`dfqueue/store.py:1281`); the
  list of open projects is `open_projects` (`:3047`) **[verified]**.
- 4.2 and 9.1 render pile 2 (24 of 25) as `full` (finding 6).

### 19. "Nothing in the dossier depends on which inbox option is chosen" is too strong (minor, D2 and D3)

**Evidence.** Design 8.4. Focus seeds come from wake subjects, which are the
inbox items (finding 9). Under options B and C the slice persists in context
across turns, so `full` versus `pull` means something different there than in a
one-shot run. And rounds to first write, the primary measure, changes with
delivery. The inbox and session design is owed with the user (`Working.md:7-9`)
**[verified]**.

**Fix.** D1 and C can proceed now. D2 waits for the owed session or ships
behind a flag, and every run row stamps the delivery mode. D3 must not span a
delivery change.

### 20. Server-side writes and gap provenance are under-specified (minor, D1 and L+)

- `dossier.refresh` writes a SQLite store, so it is not a read. Register it as a
  conductor-only, non-game write in the registry, the way the system-class
  tools are (`agents/ROSTER.yaml` conductor note) **[verified]**. The
  `ReadWritePaths` trap is noted correctly.
- `from_gap` is checked "against the current or previous dossier version"
  (11.4), but gaps are computed on demand and are not stored in a version.
  Store each version's gap set, or check against a recomputation and say so.

### 21. Chain lines omit the blockers that actually stopped the fort (minor, D2)

**Evidence.** The 2026-10-05 diagnosis (`Working.md` line 35) **[verified]**:
the bed and the digs were blocked by "no bed item and no order", "one pick and no
Forge", a game-suspended construction, and one citizen with BREWER enabled. The
Quartermaster's chain line in design 12.5 ("That is the whole decision, with no
read") shows stock and orders but not labor or stuck and suspended jobs.

**Fix.** Per chain, add the labor join's status (C2, already in
`dfmcp/labor_join.py`) and the count of stuck or suspended jobs at that
workshop (from `stuckjobs.find`, already polled by the conductor).

### 22. Cost and cache claims: honest, but the decimal precision misleads (minor)

The rates and the 3% cache share are cited correctly
(`research/2026-10-07-cross-run-cache.md` "Answer") **[verified]**. With
DeepSeek, the openclaw transport moves the Runtime region into the first user
turn, and the date is the only per-day change in the system message
(`research/2026-10-07-openclaw-source-sessions.md:107-129`) **[verified]**, so
the body-first placement does keep same-day prefixes. But slice tokens are
noise: under $0.001 a wake against about $0.048. The real costs are:

- output tokens, if a larger prompt lengthens reasoning (the design names this
  risk but does not measure it; add output tokens per wake to the D3 measures);
- the engineering: a Lua aggregator, a package, a versioned store and ten tools.

Break-even per avoided read is closer to one every 1.5 to 5 wakes than "one to
three".

### 23. A dense relation set is a map in all but name (minor, design)

**Evidence.** Section 16 of `docs/PRODUCTION-MODEL.md` forbids arranging named
boxes to reflect geography **[verified]**. The renderer sorts by kind and
handle, which is right. But if the F-23 relation read gives every pair a
direction and a distance, the set of facts lets a model trilaterate positions:
a map rendered as a table.

**Fix.** Keep relations purpose-typed and capped per entity (finding 4's
typed read), never all-pairs. Add a test that the number of `near` facts per
entity is bounded.

### 24. "Fort dossier" now means two things (minor, docs)

`docs/MEMORY-ARCHITECTURE.md:18` and `:176-178` **[verified]** define the fort
dossier to include site facts ("Aquifer at z-3", "magma at z-42") and open
problems, "always loaded". The design narrows it to built structure, per role.
Note the narrowing in that document, or name the new thing differently, so the
memory design does not carry two meanings. On open question 1 (the Chronicler),
this review agrees with the design's recommendation (b).

---

## A simpler path worth weighing

The walk-through itself shows where the value is. The Quartermaster's whole
decision fits in two chain lines. Logistics' real lever is a wake line carrying
the gap and its draft (design 11.5), not a full slice. A smaller first step:

1. **D0 as restated** (finding 1), plus the D1 read fixes (findings 3, 5, 16).
2. **An in-memory, conductor-built "fort facts" block for the Quartermaster
   only**: chain lines with labor and stuck jobs. Built from the fixed reads each
   cycle, with no store and no versions. The run row records its hash and shown
   ids.
3. **The paired same-state comparison** (finding 13) on the Quartermaster: block
   on versus off.
4. Build the versioned store, `recent_changes`, the per-role filter file and
   `dossier.get` only if step 3 shows the block pays, and only then for other
   roles.

This keeps most of the design's ideas and defers the versioned store, about
eight tools and the slice framework until there is evidence. It also avoids
measuring a framework on a 4-workshop fort.

---

## Changes required before D0

1. Restate D0's goal and tests per finding 1: per-kind coverage field, parity
   scoped to getJobs kinds, the observed-job route, wiki `prior` for the rest.
2. Fix the probe set and the workjob header's citation (finding 2).
3. Add a test that `craft.how` on an item made only at an uncovered kind (a pick
   at the Metalsmith's) returns `coverage: none` with the kind named, never an
   empty producer list.

## Changes required before D1

1. Landmark read: ids on landmarks and exits, `exists`, signed level difference,
   no name-based self-exclusion, `nearest_landmark` excludes the caller
   (findings 3 and 5). Same ids in `stockpile.list` and `blueprint.sites`.
2. A purpose-typed relation read for workshop and pile pairs, replacing top-3
   exits as the source of `near` in the flow network; drop the "not among
   near-relations" clause of `long-haul` (finding 4).
3. `tiles_free` in place of `full`, container settings rendered as maxima,
   `full-output` redefined, and sections 4.2, 9.1 and 12 corrected (finding 6).
4. Walkability-group ids in the fingerprint; `(checking)` replaced (finding 7).
5. An independent enumerator for the audit and completeness, plus a statement of
   what the audit cannot catch (finding 8).
6. Building ids in `workjob.unsupplied` rows (finding 16).
7. Pull tools cut to `dossier.get` for minimal and off roles only;
   `dossier.changes` and `dossier.annotate` deferred (finding 15).
8. `visible` described as scoping the dossier tools only; `replaces:` lists in
   `slices.yaml` (finding 10).
9. `dossier.refresh` registered as a conductor-only server-state write
   (finding 20).

## Changes required before D2 and D3 (for the record)

- Structured `subjects` on wakes (finding 9), shaped in the owed inbox session
  (finding 19).
- Per-run slice hash and shown ids in the runs store; matching rules and
  truncation reporting (finding 12).
- Relevance-ordered truncation and a tier-rule amendment or a narrower Logistics
  push (finding 11).
- The paired same-state design with a quality guard, replacing epochs as the
  primary method (finding 13); output tokens added to the measures (finding 22).

---

## Citations checked and found correct

`production/labor_ingest.py` writes no `production_flow` rows (inserts at
`:464-475` are nodes, processes, attributes only); `MAX_EXITS_PER_LANDMARK = 3`
at `landmarks.lua:125`; `derive_kind` at `df-overseer-stockpile.lua:1108`; plan-feed's
no-container feeder rule at `:1961-1967`; `ITEM_TYPE_CATEGORIES` at
`df-overseer-stockpile-kinds.lua:31`; `OUTPUT_HINTS` at `:216-221`;
`stockpile.health` and `plan-feed` `live_deployed: false` at
`TOOLS.yaml:3929-3930, 3962-3963`; the Still as building 5 at `TOOLS.yaml:3476`;
`conductor/briefing.py:3-4` (Tier 0 only); `_order_matches` at
`conductor/unsupplied_watch.py:117`; `project_status` at `dfqueue/store.py:1281`;
`find_blocker` at `production/blocker.py:379` and the workshop-as-reagent at
`:279-281`; `find_cycle` at `production/extract.py:1157`; the labor join's
pattern at `dfmcp/labor_join.py:1-10`; `wake_metrics` fields at `:443-500`;
`docs/AGENT-ARCHITECTURE.md:603`; `docs/MEMORY-ARCHITECTURE.md:18, 30, 178,
396-399`; `agents/chronicler/role.md:17-18`; the per-role tool counts
**[live 2026-10-07]**; the duplicate `shale Throne` **[live 2026-10-07]**; both
piles' `links_only` and `containers` fields present **[live 2026-10-07]**.
