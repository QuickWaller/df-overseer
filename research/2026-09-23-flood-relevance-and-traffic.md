# Flood relevance, and whether traffic designations and burrows are the shared capability

Date: 2026-09-23. Researcher stream, read-only throughout. No file on VM 103 was
written, no tile was designated, no burrow was created or modified, the fort
was never unpaused. `scripts/dfhack/df-overseer-breach.lua`,
`scripts/dfhack/TOOLS.yaml`, `dfmcp/**` and `agents/**` were read but not
edited. All live commands ran through `scripts/dfhack/vm-ssh.sh df` (this
session used `DF_ENV_FILE=<repo-root>/.env bash scripts/vm-ssh.sh df ...`
because the worktree carries no `.env` of its own; no address was read,
printed or committed). Every scratch script used for a live diagnostic was
copied to `/tmp` on the VM, run once, and deleted immediately after; none is
part of this commit.

## Verdict on the user's hypothesis, stated up front

**Refuted as a poll-scope filter, confirmed as a tier signal, and extended.**
The user's own framing already named the fault line correctly ("this fort has
no traffic designations at all, so the footprint would currently be empty").
Measured live (§2): traffic designations are **0 of 6,856,704 tiles** non-Normal
and burrows are **0** on Uniboslan today. A pure occupancy filter built on
either would gate away *everything*, including a real breach, which is exactly
backwards. The coordinator's mid-task refinement reframes the same evidence
correctly: traffic and burrows are real, cheap, already-designed-for-this
signals, but they set **how loudly the system reacts**, not **whether it looks
at all**. Section 4 below extends this with a third footprint element the
brief's own logic implies but did not name: **pending dig designations**, which
are the one part of this whole footprint that is non-empty on this fort right
now (36 tiles, verified live) and the only part that is *predictive* rather
than retrospective, matching the cross-domain literature in §3 (mine water
inrush monitoring is sited at the advancing working face, not uniformly) far
more closely than traffic or burrows do.

The logistics half of the hypothesis (§6) holds on its own terms and does not
depend on the flood case: traffic designations are real, well-documented
pathfinding cost multipliers, independent of anything to do with water.

---

## 1. Is there a working rising-liquid gate on this install?

**Yes, confirmed live, with the earlier "zero of 26,784" reading now shown to
be a snapshot of a different moment, not proof the flag never fires.**

**Source-confirmed semantics** (`df.block.xml` at df-structures commit
`1dd01aad`, the same pinned tag `df-overseer-breach.lua`'s own header cites):

```
<flag-bit name='update_liquid' original-name='FLOW_ADJUST'/>
<flag-bit name='update_liquid_twice' original-name='FLOW_MAINTAIN_ADJUST'/>
```

`Maps::enableBlockUpdates(block, flow, temperature)` (`library/modules/Maps.cpp`,
dfhack `53.16-r1.1`), read in full:

```cpp
void Maps::enableBlockUpdates(df::map_block *blk, bool flow, bool temperature)
{
    if (!blk || !(flow || temperature)) return;
    if (temperature) blk->flags.bits.update_temperature = true;
    if (flow) {
        blk->flags.bits.update_liquid = true;
        blk->flags.bits.update_liquid_twice = true;
    }
    ...
}
```

is the API every liquid-writing DFHack tool calls after touching a tile
(`plugins/liquids.cpp`'s paint tool, `modtools/spawn-liquid.lua`) to tell the
engine's own flow step "recompute this block." That is a real, native-engine
consuming flag, not a DFHack-only bookkeeping bit: DFHack's **own shipped
diagnostic tool, `flows`**, uses exactly this field as its definition of "map
blocks with flowing liquid" (`plugins/flows.cpp`, read in full):

```cpp
if (cur->flags.bits.update_liquid) flow1++;
if (cur->flags.bits.update_liquid_twice) flow2++;
...
if (cur->designation[x][y].bits.flow_size == 0) continue;
```

**Live cross-check, run twice, VM 103, fort paused throughout:**

```
$ ./dfhack-run flows
Blocks with liquid_1=true: 3
Blocks with liquid_2=true: 3
Blocks with both:          3
Water tiles:               14074
Magma tiles:               82725

$ ./dfhack-run df-overseer-breach check
{"blocks_flowing": 3, "blocks_scanned": 26784, "first_call": true, "severity": "none", ...}
$ ./dfhack-run df-overseer-breach check   (second call, same process)
{"blocks_flowing": 3, "blocks_scanned": 26784, "first_call": false,
 "note": "stage 1 tripped ... but nothing rose since the last poll -- likely known/stable (e.g. a well, a river)", "severity": "info"}
```

**DFHack's own official tool and this project's own tool agree exactly (3/3/3),
independently.** This is the checked positive the earlier "zero of 26,784
across 11 polls" reading needed and did not have. A bounded, coordinate-free
diagnostic (single-use, deleted after) resolved which 3 blocks and confirmed
they are the fort's own **Well**, `flow_size` 6-7 (topped out, settled):

```
block#1: water_tiles=25 magma_tiles=0 flow_min=6 flow_max=7 near=Well SW 3
block#2: water_tiles=2  magma_tiles=0 flow_min=7 flow_max=7 near=Well N 14
block#3: water_tiles=0  magma_tiles=0 (no wet tile; still flagged) near=Well SW 3
```

This is precisely the "well's water is real, present, and would be noisy
forever" case `df-overseer-breach.lua`'s header already designed the
baseline-delta fix for, and it is working as designed: stage 1 trips (3 of
26,784 blocks, cheap), stage 2 scans only those 3 blocks (768 tiles, not
6.8M), and severity reads `info` because nothing *rose*.

**What changed between the two readings, reasoned not confirmed:** the
`first_call: true` on this session's first call means the breach script's
`_G` baseline was freshly seeded, i.e. the DFHack process had recently
restarted (a redeploy, most likely). A plausible mechanism, not verified
against DF's closed-source engine: on save/world load the engine marks a
small number of blocks (plausibly the ones with a live water source, like a
well) for a recompute pass, and since the fort has sat paused since, no tick
has run to clear that mark. This would explain 3-nonzero-here vs.
zero-in-the-earlier-session's-11-polls as two different points in a
restart/pause cycle rather than a contradiction about what the flag means.
**Not independently verified**: whether `update_liquid` reliably sets and
clears during genuinely active flow at this install's own tick rate — there is
no real breach on this fort to observe, and inducing one is out of scope for a
read-only stream. What would settle it: watch `flows`' own count across a
short unpaused window while a dwarf is actively hauling water or a real leak
exists.

**Cost, measured, not just reasoned:** the 26,784-block stage-1 scan is
unchanged from the prior session's own measurement (~0.057s CPU, `docs/TRAPS.md`).
Both live `dfhack-run flows` and `df-overseer-breach check` calls above
returned promptly with no timeout. **The gate is real, cheap, and currently
non-vacuous; the earlier "zero" reading was a false negative of that specific
sampling window, not evidence the flag never fires.**

---

## 2. What is actually readable about traffic designations and burrows?

Both source-confirmed against `df.d_basics.xml` (df-structures `1dd01aad`,
the shared bitfield file `tile_designation` and its sibling enums are defined
in — not `df.block.xml`, which only references the type by name) and
cross-checked against `plugins/filltraffic.cpp` and `plugins/burrow.cpp`
(dfhack `53.16-r1.1`).

### Traffic — a per-tile designation, confirmed not a zone

```xml
<flag-bit name='traffic' original-name='TRAFFIC' count='2' type-name='tile_traffic'/>
...
<enum-type type-name='tile_traffic' ...>
  Normal / Low / High / Restricted
</enum-type>
```

Lives on `designation[x][y]`, the **same struct `flow_size`/`liquid_type`/
`hidden`/`dig` already live on** — already known and live-confirmed in
`memory/dfhack-environment.md` (`dfhack.maps.getTileFlags(pos).traffic`,
0-3). `filltraffic.cpp`'s plugin writes it with `des.bits.traffic = target`,
flood-filling from a cursor tile outward while the target tile is passable —
mechanically identical to what a player does with the traffic-paint tool.
**Cost weights (1/2/5/25) are compiled into the binary**, not directly
readable, matching the prior finding in `memory/dfhack-environment.md`.

**Live, verified, fort paused, full-map tile sweep (bounded by fixed map
geometry, ~6.86M tiles, single diagnostic run, not a per-poll cost — see the
cost discussion in §4):**

```
total_tiles=6856704
traffic[Normal]=6856704
traffic[Low]=0  traffic[High]=0  traffic[Restricted]=0
```

**Zero traffic designations exist on Uniboslan.** The hypothesis's own
caveat is correct as a fact about this fort today.

### Burrows — a real object, with a tile set and a unit list, confirmed not a zone either

```
Burrows::setAssignedTile(burrow, pos, enable)   -- per-tile, via a per-block bitmask
Burrows::setAssignedUnit(burrow, unit, enable)  -- per-unit membership
Burrows::clearUnits(burrow)
```

`df::burrow` carries a `name` and a `units` vector (unit ids); tile membership
is **not** a field on the burrow object itself but a per-map-block
`block_burrow` bitmask (`tmask->tile_bitmask`), reached via
`Burrows::getBlockMask(burrow, block, create)`. This matches
`memory/dfhack-environment.md`'s already-verified path,
`df.global.plotinfo.burrows.list` (not `world.burrows.all`, which does not
exist).

**Live, verified:**

```
burrow_count=0
```

**Zero burrows exist on Uniboslan.** Reading a burrow's tile set or member
list is a plain field/bitmask read, no different in kind from every other
read-only tool in this repo. **Nothing here is armok-tagged or hides
information**: §3's ruling section covers the write side.

---

## 3. Can traffic and burrows be written, and is it within the rules? (priority question)

**Neither `burrow` nor `filltraffic` carries DFHack's own `armok` tag**
(`docs/DFHACK-INVENTORY.md`: `burrow` — `fort, auto, design, productivity,
units`; `filltraffic` — `fort, design, productivity, map`). Read against
`CLAUDE.md`'s actual rule rather than the tag (the tag is only a pointer,
per `docs/ARMOK-RULINGS.md`'s own framing): banned is "powers a player does
not have... and information the game hides." Setting a tile's traffic
designation or a burrow's tile membership is **exactly** what a player does
with the mouse on the Traffic and Burrows screens — no different in kind from
`lever pull` (already ruled `allowed`, `docs/ARMOK-RULINGS.md`) or the
building tool's own dry-run-then-real quickfort placement. **Writing traffic
designations or a burrow's tile set is not an armok capability under this
project's rule, on the evidence read this session.**

**Assigning a specific dwarf to a burrow (confinement) is mechanically the
same class of action** (`Burrows::setAssignedUnit`, exactly what the
Burrows screen's unit-assignment UI calls) and is **also not armok** by the
same test: a player restricts a dwarf's movement to a burrow routinely, for
exactly this reason (keeping civilians out of a dangerous area), and the game
does not hide this information or grant a power the player lacks.

**But per the brief's explicit instruction, this is flagged as a decision for
the user regardless of the armok analysis, not slipped in as a tooling
detail**: confining a dwarf is a real, consequential fort action in the same
category this project has already treated with extra care elsewhere (the
Manager appointment, the first real Chair build) — it changes what a citizen
can do, autonomously, without a human's turn-by-turn awareness, which is a
different kind of stakes than reading a field. **Recommendation for the
register** (not written here, per the "own nothing but the research file and
this handoff's Result section" rule): treat "is an agent allowed to assign a
citizen to a burrow, and under what condition (e.g. only in direct response
to a `pause`-tier finding, never as a standing policy)" as its own decision
line, separate from "is writing traffic/burrow structures armok" (which this
research answers no to). **A tool that only reads burrow/traffic state, or
that writes traffic designations (which reroute pathing but confine no one),
needs no such ruling** by the same reasoning `docs/ARMOK-RULINGS.md` already
applies tool-by-tool rather than blanket.

---

## 4. The right footprint for flood relevance (refined per the coordinator's mid-task note)

**The refinement is correct and is adopted over the brief's original framing.**
Using occupancy as the *poll scope* was the design error the coordinator
named: a breach happens in a tile seconds old that belongs to no zone, no
burrow, and (on this fort) no traffic designation either, so a pure occupancy
filter would gate away the exact case flood detection exists for. The fix is
that stage 1 (§1, cheap, global, unconditional) stays exactly as designed —
it must, since it is the only thing watching the unvisited dark — and the
**footprint decides tier**, applied only to tiles that already passed stage 1
and stage 2's rise-since-baseline filter. That reordering matters for cost:
see below.

### The footprint's three elements, each checked against live data

1. **Traffic designations** (`designation[x][y].traffic ~= Normal`). Verified
   empty today (§2). Real and cheap when populated: same struct as the
   liquid fields, no extra fetch.
2. **Burrow membership** (`Burrows::getBlockMask` / per-block bitmask).
   Verified empty today (§2). Real when populated, same cost profile.
3. **Active dig designations** (`designation[x][y].dig ~= tile_dig_designation.No`),
   the element the coordinator's refinement asked to add. **Verified live,
   and non-empty right now**, unlike the other two:

```
dig[Default]=36   (the other five dig kinds: 0)
```

This is the fort's own, currently populated, machine-readable statement of
"here is where a dwarf is about to open new ground" — the one part of the
candidate footprint that is predictive of where a breach can *start*, not
just where citizens already walk. It matches the mine-water-inrush literature
in §3.4 more closely than traffic or burrows do: that field sites monitoring
at the advancing working face specifically because that is where the hazard
is created, not because it is where people already are.

**A genuine, checked negative worth reporting**: I looked for a cheap
block-level gate for dig designations, symmetric to `update_liquid`'s role
for liquid (§1), and it does not hold up. `block.flags.designated`
(`HAS_DESJOB`, `df.block.xml`, comment "for jobs etc") looked like exactly
that gate. **Live test, bounded full-map scan, fort paused:**

```
blocks_scanned=26784
blocks_flagged_designated=0
dig_tiles_in_flagged_blocks=0
dig_tiles_in_UNflagged_blocks=36   <- the gate missed every one
```

**`block.flags.designated` did not correlate with the 36 real, live dig
designations at all.** A second live check explains why, and is itself a
finding: `df.global.world.jobs.list` (the fortress-wide job list this repo
already reads elsewhere) carried **zero** dig-type jobs (`Dig`,
`CarveUpwardStaircase`, `CarveDownwardStaircase`, `CarveUpDownStaircase`,
`CarveRamp`, `DigChannel`) despite the 36 designated tiles — only `Fish` and
`ConstructBuilding`. **Reasoned, not confirmed**: both `designated` and the
job list plausibly reflect the same tick-gated pipeline (a raw designation
becomes a `df::job` object, and the block flag that says "a job exists here,"
only once the engine actually processes it — which needs the fort to be
*running*, not paused). Uniboslan has sat paused. **What would settle it**:
re-run both checks during or immediately after a brief, supervised unpause
window and see whether `designated`/the job list catch up to the raw
designation count. Until then, **the only currently-reliable way to read
pending dig designations is the per-tile `designation.dig` field directly**,
not the job list and not the block flag.

### Why this does not reopen the cost problem (the key reconciliation)

The full-map tile sweep above (6,856,704 tiles) was a **one-off diagnostic
query**, run once to answer "how many designated tiles exist right now,"
never something the live design needs to run per poll. **In the actual
tiered design, dig-designation and footprint classification never needs a
map-wide sweep**: it is applied only to the tiles that *already* passed stage
1 (update_liquid, ~0.057s, 3 blocks today) and stage 2's rise-since-baseline
filter (§1) — normally zero tiles, rarely more than a handful. For each such
already-identified tile, reading `designation[x][y].traffic`,
`designation[x][y].dig`, and its burrow-block membership is **three extra
field reads on a struct the code already has open**, not a new scan. The
genuinely expensive full-tile sweep is not on the poll's hot path at all.

**What this means concretely**: keep stage 1 exactly as `df-overseer-breach.lua`
already built it (unconditional, every poll, cheap, watches everywhere,
including the unvisited dark). Add, only at the point a tile is already a
confirmed *finding* (flow_size rose since baseline): a lookup of that one
tile's traffic designation, burrow membership, and dig-designation status,
plus (proposed, not built — see below) whether that tile or an immediate
neighbor was the site of a `Dig`-class job completion in roughly the last N
polls. All four checks are O(number of findings), not O(map size).

### The predictive extra: job-completion listening for the dig frontier

There is **no native "changed since last poll" flag** on `tile_designation`
(checked: `flow_forbid` and `liquid_static` are the only other liquid-adjacent
bits, and both are write-only in every DFHack tool that touches them — no
tool in the pinned source tree reads them as a discriminator, so their native
engine semantics could not be confirmed and neither is a "changed" signal).
This project's own established pattern for "since last poll" is event-driven,
session-scoped baselines — exactly what `df-overseer-breach.lua`'s own
`flow_size` baseline already is, and what `df-overseer-diff.lua` already does
for job completions and unit deaths (`eventful.onJobCompleted`,
**already live-deployed and verified in this exact codebase**,
`scripts/dfhack/df-overseer-diff.lua:224-287`). **Proposed, reasoned from this
precedent, not built or live-tested this session**: register a listener the
same way, filtered to the six `Dig`/`Carve*` job types (§4 above), and on
completion, stage-2-scan the completed job's own tile plus its same-z
neighbours immediately, rather than waiting for the next stage-1 poll to
notice. This is the one part of the footprint that is genuinely predictive —
it fires at the instant a wall opens, which is the instant a breach becomes
possible, not on the next periodic sweep. It is unverified whether
`onJobCompleted` actually fires for `Dig`-class jobs specifically (only
`diff.lua`'s general registration is confirmed live); the general mechanism
is confirmed, the specific job-type coverage is not.

### Caching

None of the above needs a cache or a recompute schedule. Stage 1 already
polls fresh every cycle (cheap). Footprint classification happens per-finding,
freshly, at the moment of the finding, since a finding is already rare. The
only state carried between polls is what `df-overseer-breach.lua` already
carries: the `_G` flow_size baseline table (§1, unbounded growth already
flagged as a known, accepted limit in that file's own header) and, if the
job-completion listener above is built, a small bounded ring of "recent dig
completions," aged out after a fixed number of polls, matching
`df-overseer-diff.lua`'s own event-log pattern.

---

## 5. Severity and tiers

Mapping onto the existing three-tier system (`pause`/`slow`/`record_only`,
`research/2026-09-23-wildlife-threat-classes.md`, `docs/AGENT-LOOP.md` §3),
argued from §1/§2/§4's evidence, not the hypothesis:

| Finding (a tile whose flow_size rose since baseline, stage 1+2 already fired) | Tier | Why |
|---|---|---|
| Magma, reachable (existing `adjacent_to_citizen_network`/landmark-radius check) | **pause** | Unchanged from the existing `critical` severity; magma is categorically worse, matching the file's own existing logic. |
| Water or magma, inside a burrow's tile set, or on a tile whose traffic is non-Normal | **pause** | The fort's own stated intent says dwarves are there or are meant to be; this is the hypothesis's original claim, correctly scoped to *tier* rather than *scope*. Currently unreachable in practice (§2: both are empty on this fort), but load-bearing the moment either is populated. |
| Water or magma, on or immediately adjacent to a pending dig designation, or at a tile a Dig-class job completed at in roughly the last few polls | **slow** | The predictive case (§4): this is where a breach is created, not where it has already arrived. Currently the only populated element of the footprint (36 tiles). Not `pause` because a rise here is exactly what a normal, safe channel-digging or aquifer-piercing operation *also* looks like in its opening moments — `slow` buys attention without halting a routine dig. |
| Water or magma, adjacent to the general citizen walkable network (existing `adjacent_to_citizen_network`) but none of the above | **slow** | Existing behaviour, unchanged; someone could plausibly reach it soon even without a stated designation. |
| Water or magma, none of the above (the unvisited cavern case) | **record_only** | Feeds the observation ledger (`research/2026-09-23-wildlife-threat-classes.md`'s pattern), wakes nobody. This is scenery *until* something in the rows above also becomes true — which stage 1's unconditional, global poll guarantees it will eventually notice, since it never stops watching the whole map. |

**Honesty on tick-rate numbers, per the brief's own instruction**: no
"findings per N ticks" or "how many polls before pause-worthy" figure is
given here, because none was measured. The only measured cost figures in
this document are the ones in §1 and §4 (block-scan CPU time, tile-sweep
completion within an SSH round trip). Anything about *how fast* a real
breach would climb through this tier table is unmeasured, would need a real
rising-water event to observe, and should not be assumed from this research
alone.

---

## 6. The logistics half, briefly

Traffic designations are a real, independent capability with no dependency
on the flood case. `dfhack.maps.getTileFlags(pos).traffic` decodes to the
`tile_traffic` enum (Normal/Low/High/Restricted) and the game applies fixed
pathfinding cost weights (1/2/5/25, compiled into the binary, not
independently readable — `memory/dfhack-environment.md`, unchanged this
session) to route hauling and general dwarf pathing around cheaper terrain.
`filltraffic`'s flood-fill-from-cursor mechanism (§2) is the same mechanic a
player uses to mark a busy corridor `High` so haulers prefer it, or a
workshop's messy back corner `Restricted` so idlers stop cutting through it.

**Uniboslan cannot demonstrate a measurable win today**: `memory/dfhack-environment.md`
already records that stockpile give/take links read empty (nothing
configured) and no Manager has ever validated a real order. A traffic tool
built now would have nothing to optimize against, so any "pays for itself"
claim is **reasoned from the documented mechanic, not measured on this
fort**. It would pay for itself the moment real hauling volume exists
(multiple stockpiles, a working Manager, active work orders), independent of
whether the flood case ever fires — which is exactly the user's framing, and
nothing found this session contradicts it. A generalisable `traffic` tool
(kind = the four enum values, per `CLAUDE.md`'s "tools must be generalisable"
rule, matching `df-overseer-zone.lua`'s own kind-as-argument convention)
would serve both uses from one capability, which is the actual basis for the
hypothesis's "one designation capability... balances into logistics" claim.

---

## Cross-domain prior art

Read and cited per `CLAUDE.md`'s "research before designing from scratch"
rule, not gestured at.

1. **Flood gauge network siting.** Stream/rain gauge placement is driven by
   representing "critical risk location[s]" and the contributing watershed,
   not uniform coverage; gauges are sited away from confounds (wind
   obstruction, unrepresentative microclimate) and distributed to capture
   real variation (elevation bands, aspect) rather than clustered wherever is
   convenient to reach. ["Optimal Stream Gauge Network Design Using Entropy
   Theory and Importance of Stream Gauge Stations"](https://pmc.ncbi.nlm.nih.gov/articles/PMC7514323/);
   ["Designing an Effective Rain Gauge Network"](https://agriculture.institute/hydrology/effective-rain-gauge-network-design/).
   **What transfers**: siting by where the hazard *starts and is consequential*,
   not by convenience or uniform density — the same argument for weighting
   the dig frontier over a blanket sweep. **What does not**: gauge networks
   assume a known, mostly-fixed watershed topology; a fort's dig frontier
   moves with play, so the footprint has to be recomputed from live state
   (§4's per-finding approach), not laid out once.

2. **Fire/gas detector placement by occupancy and egress.** Detectors are
   required densely on **means-of-egress routes and specific occupied room
   types** (corridors, mechanical rooms, kitchens), explicitly *not* uniformly
   throughout a building; egress-route coverage is prioritized because that
   is where the hazard (smoke blocking escape) and the population intersect.
   [NFPA 72 / smoke detector commercial requirements](https://getsafeandsound.com/blog/commercial-smoke-detector-requirements/);
   [specific location requirements, UpCodes](https://up.codes/s/specific-location-requirements).
   **What transfers directly**: this is the closest real-world analogue to
   the user's original "traffic/burrow = where dwarves are and go" framing,
   and it is a real, standard practice, not a stretch — egress routes are
   exactly what traffic designations *would* mark if this fort had any.
   **What does not transfer as cleanly**: egress routes in a building are
   near-static (the building doesn't grow); a fort's walkable network and dig
   frontier are not, which is why §4 leans on a live per-finding check rather
   than a precomputed egress map.

3. **Industrial alarm management (ISA-18.2).** The standard's central
   design principle, read directly from a secondary but standards-citing
   source: not every deviation becomes an alarm. "There is a temptation to
   alarm every possible deviation, even when the deviation doesn't require
   immediate attention" — conditions needing immediate operator action are
   alarms; everything else is "reclassified as events to be recorded... for
   later review, instead of as items requiring immediate operator attention."
   An **alarm flood** is formally defined (more than 10 alarms in 10 minutes)
   as the specific failure mode that erodes operator trust and causes missed
   real alarms. [Yokogawa, "Implementing Alarm Management per the ANSI/ISA-18.2
   Standard"](https://www.yokogawa.com/us/library/resources/media-publications/implementing-alarm-management-per-the-ansi-isa-182-standard-control-engineering/).
   **What transfers directly, and is the strongest single justification for
   the tier table in §5**: the `record_only`/`slow`/`pause` split *is* ISA-18.2's
   alarm-vs-event distinction, already adopted by this project
   (`research/2026-09-23-wildlife-threat-classes.md`) for wildlife and now
   extended here to liquid. The standard's own recommendation (no more than
   3-4 priority tiers, ≤5% of alarms at the highest priority) matches this
   project's existing three tiers structurally.

4. **Mine water inrush monitoring.** Directly on point, and the strongest
   support for the coordinator's refinement over the brief's original framing.
   Monitoring is explicitly **not** uniform across a mine; it targets "key
   monitoring areas," sited to match "the spatial matching of the monitoring
   position... and the location of potential water inrush points," concentrated
   at the **active working face and its immediate floor geology** — i.e. at
   the advancing extraction front, because that is where the hazard is
   *created*, not merely where miners already are.
   ["Evaluation technology for key monitoring area of early warning of water
   inrush from the floor of working face in coal mine"](https://cge.researchcommons.org/journal/vol47/iss5/3/);
   corroborated by the microseismic-monitoring literature, which instruments
   the rock ahead of and beneath active extraction specifically because
   fracture propagation precedes the inrush event.
   ["Real-Time Monitoring and Early Warning of Water Inrush in a Coal Seam
   Floor: A Case Study"](https://link.springer.com/article/10.1007/s10230-021-00767-1).
   **What transfers directly**: this is the real-world precedent for
   §4's dig-designation/dig-frontier footprint element, and it is a domain
   where "wait for occupancy" is not an option at all (nobody occupies rock
   before it is mined), which is exactly this project's own "unvisited dark"
   problem. **What does not transfer**: mine inrush monitoring uses continuous
   physical instruments (microseismic sensors, fiber Bragg gratings) reading
   a real geological signal; a Fortress read-only tool has no equivalent
   continuous physical channel and must substitute the game's own designation
   and job-completion data as the nearest analogue to "where extraction is
   advancing."

---

## What could not be verified, and what would settle each one

1. **Whether `update_liquid` reliably sets (and clears) during genuinely
   active liquid flow at this install's own tick rate**, as opposed to only
   correlating with a post-restart/pause artifact (§1). Settle by watching
   `dfhack-run flows`' own count across a short, supervised unpause window
   with a real leak or active hauling, comparing before/after.
2. **Whether `block.flags.designated` and `world.jobs.list` catch up to raw
   dig designations once the fort actually ticks** (§4) — both read empty/zero
   against 36 real, live-designated tiles while paused. Settle the same way:
   re-run both diagnostics during or right after a brief supervised unpause.
3. **Whether `eventful.onJobCompleted` fires specifically for `Dig`-class
   job types** (§4's predictive proposal) — only `df-overseer-diff.lua`'s
   general, unfiltered registration is confirmed live; no Dig-type completion
   was observed this session (fort paused, no jobs of that type exist right
   now). Settle by registering the filtered listener and watching it fire
   against a real dig job completing, live.
4. **The native engine's read/write semantics of `liquid_static` and
   `flow_forbid`** — both are write-only in every DFHack tool this session's
   source read touched; no tool reads either as a discriminator, so whether
   the closed-source engine itself treats `liquid_static` as a genuine
   "settled" signal (which would be a cheaper, tile-level complement to the
   block-level `update_liquid` gate) is unknown, not zero.
5. **Any tick-rate or "how many polls until pause-worthy" figure** for a real
   rising-water event (§5) — explicitly not measured, and flagged as such
   rather than estimated, per the brief's own instruction.
6. **Whether a real breach's tile is reliably within reach of the
   dig-designation/job-completion footprint** (§4) as opposed to sometimes
   starting from natural collapse or aquifer exposure with no prior
   designation at all. Reasoned as very likely (a breach cannot start except
   where a tile was opened, and opening a tile in this game is always either
   a dig job or a cave-in, and cave-ins are covered by the existing
   `CAVE_COLLAPSE` announcement channel per `research/2026-09-12-dfhack-capability-checks.md`
   §5), not independently confirmed against a real breach.
