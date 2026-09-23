# Burrows as districts: what players actually do

Date: 2026-09-24. Read-only research, answering
`handoffs/2026-09-24-burrow-district-designs.md`. Deliberately small; does
not repeat the cross-domain sweep in
`research/2026-09-24-room-layout-best-practices.md`. No coordinate, grid or
map appears below.

## Verdict

Burrow usage is thin, mechanical and mostly about **restriction and safety**,
not about logistics design. The wiki states clear mechanics for what a
burrow contains and how hauling-into-a-burrow works, but there is **no
community guidance at all on sizing** (dwarves per burrow, when to split a
district) and only sparse, low-confidence material on inter-district
material flow. The most load-bearing, best-attested content here is Q5, the
failure modes, because the wiki states them as direct mechanical
consequences (a job cancels, a hauler abandons a wheelbarrow, a dwarf
starves) rather than as folklore. Everything below keeps `game mechanic`
(the wiki's stated behaviour, current v53.16-banner unless flagged) separate
from `convention` (how players actually configure burrows, which turned out
to be thinly sourced).

## Q1. What burrows are actually used for

- **Civilian alert / safety, the dominant real use, emergency-only.**
  Pre-v50, a civilian alert confined all civilians to a burrow and pulled
  anyone outside back in immediately (`game mechanic`, DF2014-era). **v50
  removed the alert UI**; the wiki states this plainly ("civilian alerts are
  missing in current versions"). Two replacements exist, both convention:
  assign everyone to a burrow kept suspended by default and activate it only
  when a threat appears, or use DFHack's `gui/civ-alert`, which the docs
  describe as toggling a single alert state that rushes non-military
  citizens to a configured burrow. **This is the one burrow use this session
  found strong, repeated sourcing for, and it is explicitly emergency-only,
  not routine.**
- **Restricting hauling / keeping a workforce local to its industry,
  routine.** The wiki states burrows can "limit the jobs for a dwarf or
  group of dwarves" and "limit where they go," and separately that
  restricting a broker's movement to the trade depot is a named use.
  `convention`, but stated on the current-banner page as the mechanic's own
  intended purpose, not just inferred by players.
- **Keeping dwarves out of danger generally** (not just alert-triggered):
  a standing burrow that simply excludes a hazardous area. `convention`,
  weakly sourced (implied by the mechanic's description, not a specific
  cited example).
- **No source found** describing burrows used the way this project's
  "district" framing implies: a named, permanent per-industry region with
  its own population, workshops and stockpiles, configured and left running
  as routine fortress structure rather than as an exception-handling tool.
  Stated plainly: **that specific "district as burrow" pattern is this
  project's own design, not an attested player convention.** It is a
  reasonable use of the mechanic (nothing found contradicts it), but nobody
  in the sources this session read describes running a fortress that way.

## Q2. Per-burrow logistics: keeping a district self-sufficient

- **The core rule the wiki states directly**: a burrow must contain
  everything its assigned dwarves need to live and work: "all places they
  work at, sleep, eat, drink," plus "all tools, raw materials, fuel and
  items they need," including the relevant stockpiles. `game mechanic`
  (current banner). This is a hard requirement, not a nice-to-have: burrow
  assignment does not grant an exception for materials found just outside
  the boundary.
- **Local versus central storage.** No dedicated guidance found beyond the
  above completeness rule; the practical consequence (stated, not merely
  inferred) is that anything a burrow's workforce needs regularly should
  have a stockpile *inside* the burrow, because a burrow "will not generate
  jobs, nor will it keep items inside it from being hauled away to a
  stockpile elsewhere" if that stockpile sits outside. `game mechanic`.
- **Quantum/feeder stockpiles.** Real and well documented, but as a general
  storage-compaction technique, not a burrow-specific one; no source ties it
  to burrow/district design specifically. Mechanically: one or more
  "feeder" stockpiles feed a one-tile minecart/track-stop dump onto a
  single-tile stockpile, which the DFHack `gui/quantum` docs and the wiki
  both describe, and which the wiki calls a "developer tolerated exploit"
  (worth flagging: it is a legitimate mechanic but an acknowledged edge of
  intended design, not neutral). `game mechanic`, current-generation
  sources; whether players commonly place a quantum stockpile *inside* a
  burrow to keep it self-sufficient is unverified, `convention`-shaped but
  unsourced.
- **Hauling into a burrow when normal hauling would cross the boundary.**
  The wiki's own recommendation: "limit their stockpiles to links only, and
  use minecart hauling systems to move the requisite goods from outside the
  burrow to in." `game mechanic`/stated convention on the current page. This
  is the one clearly-sourced answer to "how does material get into a
  self-sufficient district without breaking burrow restriction."

## Q3. Imports and exports between districts

- **Give/take stockpile links exist and move material stockpile-to-
  stockpile** without a dwarf needing to leave a burrow, confirmed as a
  real mechanic; if a workshop is linked to specific stockpiles it will
  draw only from them ("it must get everything it needs from them...and
  will no longer find items anywhere else"). `game mechanic`. This is the
  direct answer to "how does ore get from a mining district to a smithing
  one without breaking a burrow boundary": a give/take-linked stockpile
  pair straddling (or a minecart route crossing) the boundary, not raw
  proximity.
- **Minecart/track-stop routes** are the wiki's own stated mechanism for
  bulk transfer across a burrow boundary (see Q2). No source describes
  minecart routing specifically framed as inter-*district* logistics (mine
  district to forge district); it is documented as inter-burrow/general
  hauling infrastructure and this project would be extending it to the
  district framing itself.
- **What goes wrong at scale, per the sources found**: two named failure
  patterns, both `game mechanic` consequences, not vague "hauling is slow"
  complaints: (a) haulers check only whether the *destination* stockpile is
  inside the burrow, not whether the *item itself* currently sits inside it,
  producing spurious cancellations; (b) a hauler crossing out of a burrow
  while pushing a wheelbarrow abandons it at the boundary. Both found on the
  wiki page itself, not independently confirmed against a v53 changelog this
  session.
- **No source found** describing a large multi-district fortress's material
  flow holistically. Everything above is mechanic-level (how one crossing
  works), not convention-level (how players route material at fortress
  scale). Stated plainly rather than inventing a pattern.

## Q4. Sizing

**No community guidance found, at any confidence level.** Multiple targeted
searches (dwarves-per-burrow, when to split a district/site) returned
nothing beyond the mechanic description; one search result noted only that
a burrow can be split across multiple non-contiguous areas and dwarves will
walk between them, which is a capability, not a sizing rule. This question
is **explicitly unanswerable from the sources this session could reach**,
not merely under-sourced. If this project wants a working number, it will
have to derive one itself (e.g., from travel-distance and workshop-count
data it can already read) rather than import one, and should not present a
derived number as player convention.

## Q5. Failure modes, as conditions a checker could detect

Each stated as the wiki's own claimed mechanic where marked so, else
flagged as forum-level convention.

1. **Starvation/dehydration inside a restrictive burrow.** *Mechanic*: a
   burrow that omits a food or drink source (or the stockpile holding it)
   leaves its assigned dwarves unable to eat or drink without breaking
   burrow restriction, and the wiki states this outright as a foreseeable
   consequence of the completeness requirement in Q2. *Condition a checker
   could test*: for every burrow with dwarves assigned, does its footprint
   (its declared area(s), which `plotinfo.burrows.list` exposes) contain at
   least one food stockpile/source and one water source (a well tile or a
   pond/river tile within the burrow boundary), by geometric containment,
   the same technique the layout report's rule 1 already uses for
   furniture.
2. **No access to a well (or any drink source) specifically.** A special
   case of 1, worth its own check because water is dwarves' more frequent
   need. *Condition*: burrow boundary contains no tile this project's own
   well-reachability tooling already treats as a valid drink source.
3. **Job cancellation from item-outside-burrow.** *Mechanic, wiki-stated*:
   a needed tool, raw material or fuel item sitting outside the burrow
   boundary causes the assigned dwarf's job to fail to find it, producing a
   cancellation, even when a stockpile of that item type exists just
   outside. *Condition*: for a burrow with hauling labor restricted to
   members of that burrow, does every workshop inside it have its required
   material kinds (from this project's own requirements data, per
   `research/2026-09-23-room-and-zone-requirements.md`) satisfied by a
   stockpile whose own footprint is inside the same burrow, or by a
   confirmed give/take link crossing the boundary.
4. **Hauling deadlock at the burrow edge.** *Mechanic, wiki-stated*: haulers
   check only the destination stockpile's burrow membership, not the item's
   current location, which can strand items that are technically outside
   the intended path. *Condition*: harder to check statically (this is a
   runtime pathing behaviour, not a placement fact); flag as a rule this
   project cannot pre-verify by geometry alone, only reduce the odds of by
   keeping stockpile pairs and their linked workshops on the same side of a
   boundary.
5. **Wheelbarrow abandonment at the boundary.** *Mechanic, wiki-stated*: a
   hauler using a wheelbarrow drops it at the burrow edge when crossing out.
   *Condition*: a burrow-restricted stockpile that relies on wheelbarrow-
   using labor (stone/ore hauling with wheelbarrows enabled) with its source
   material outside the boundary is a foreseeable friction point; checkable
   only as a configuration flag (is wheelbarrow hauling enabled for a
   stockpile whose source lies outside its burrow), not a hard invariant.
6. **Dwarves unable to reach their own job site.** Named directly in a
   forum discussion ("assigned a burrow that prevents them from accessing
   their job sites") but not independently sourced beyond that; treat as
   `convention`, weakly attested. *Condition*: a dwarf's workshop or
   designated job location falls outside every burrow they are currently
   restricted to, a set-membership check this project's own labor/workshop
   tooling could run directly (dwarf's burrow assignment(s) versus the
   burrow footprint(s) containing their job).
7. **Civilian-alert burrow with no real safe interior.** *Convention*, one
   forum source, low confidence: a burrow built to receive fleeing civilians
   that itself contains a hazard (the surface, a cavern breach) fails at the
   one job it exists for. *Condition*: the emergency/safety burrow (however
   this project marks one, e.g. by name or doctrine convention) must not
   overlap any tile this project's own hostile-reachability tripwire
   tooling currently flags as reachable by a threat.

## Failure modes not adopted, with reasons

- **"Dwarves half-heartedly respond to burrow orders / loiter instead of
  retreating"**, from one forum thread. Framed as a live-UI/pathing
  complaint about the emergency-alert feature itself, not a structural
  district-design mistake this project's tools could detect by geometry;
  out of scope for a static checker.
- **Any numeric threshold for burrow size or population.** Not proposed,
  per Q4: no source exists to ground one, and inventing one repeats this
  project's own named mistake pattern of treating folklore as a requirement.

## What could not be verified

- **Sizing (Q4) at all.** Explicitly unanswerable from sources reached this
  session; see above.
- **Whether experienced players actually run permanent per-industry burrows
  as routine fortress structure** (the "district" framing itself), as
  opposed to using burrows only for the emergency/restriction uses Q1
  found. No source affirms or denies this at fortress-design scale; treat
  the district-as-burrow mapping as this project's own extension of the
  mechanic, not a validated community pattern.
- **Inter-district material flow at fortress scale** (Q3's last point): only
  single-crossing mechanics were found, not a described macro pattern.
- **The wheelbarrow-abandonment and item-location-check claims** (Q5 #3-4,
  #5) are wiki-stated but this session did not independently confirm either
  against a current changelog or a live test; both carry the current
  v53.16 page banner, so they are at least not stale from the v50
  transition, but they are not install-verified on this fort (which has
  zero burrows).
- **DFHack's `gui/civ-alert` tool** was found only in its own docs, not
  checked against `memory/dfhack-environment.md`'s tool inventory; whether
  it is present/available on this install is unconfirmed this session.

## Candidate rules for a burrow/district checker

| # | Rule | Type | Basis | Grounding |
|---|---|---|---|---|
| 1 | A burrow with dwarves assigned must contain at least one food stockpile/source and one drink source within its own footprint | invariant | game mechanic | Wiki `Burrow`, current v53.16 banner, stated completeness requirement (Q2, Q5 #1) |
| 2 | A burrow's drink source must be a tile this project's own well/water-reachability tooling already treats as valid | invariant | game mechanic | Q5 #2, reuses existing tooling, no new game-data read |
| 3 | A workshop inside a burrow with restricted hauling must have its required material kinds satisfiable by an in-burrow stockpile or a confirmed give/take link across the boundary | invariant | game mechanic | Wiki `Burrow`, Q2/Q3/Q5 #3 |
| 4 | A dwarf's currently assigned job-site building must fall inside at least one burrow they are restricted to | invariant | convention (forum-sourced), riding on a real membership mechanic | Q5 #6, weakest-sourced invariant in this table, flag accordingly |
| 5 | A burrow marked as the fortress's emergency/safety burrow must not overlap any tile currently flagged reachable by a hostile (this project's existing tripwire tooling) | invariant | convention | Q1, Q5 #7, single forum source |
| 6 | Flag (do not reject) a burrow-restricted stockpile with wheelbarrow hauling enabled whose source stockpile lies outside the same burrow | metric | game mechanic | Q5 #5 |
| 7 | No sizing rule (population-per-burrow or footprint-per-population) proposed | n/a | n/a | Q4, explicitly unanswerable; do not invent a number |

## Proposed doctrine entries (for the orchestrating session to route, not written here)

1. **A burrow must contain everything its dwarves need (food, drink, tools,
   raw materials, fuel, relevant stockpiles), or jobs will cancel and
   dwarves can starve.** `prior`, current v53.16-banner wiki source. This is
   the single most directly actionable, best-sourced fact in this report and
   the one most likely to prevent a real incident if an architect/overseer
   agent ever assigns dwarves to a burrow.
2. **Civilian alerts are removed from the base v50 UI; the working
   replacement is a suspended-by-default burrow activated on threat, or
   DFHack's `gui/civ-alert`.** `prior`, current-banner wiki plus DFHack docs.
   Worth doctrine only once this project actually builds an emergency-burrow
   response, to stop an agent from looking for a alert UI that no longer
   exists.
3. **Hauling into a burrow-restricted stockpile from outside should use a
   link-only stockpile plus a minecart/track-stop route, not open hauling
   across the boundary.** `prior`, current-banner wiki. Directly informs the
   district logistics design this project is building toward.

All three are proposals only; this stream did not touch `doctrine/seed.yaml`.

## Sources

Install/repo: `CLAUDE.md` (status banner), `research/2026-09-24-room-layout-
best-practices.md` (read in full to avoid repeating its sweep and to match
its format), `memory/dfhack-environment.md` (burrow-related entries: zero
burrows on this fort, `plotinfo.burrows.list` as the correct path, traffic
designation unused).

Web, fetched or searched this session, each cited above by version banner
where one was visible (`prior`, never `verified`, per doctrine's own
provenance rule): [Burrow](https://dwarffortresswiki.org/index.php/Burrow)
(current, v53.16 banner), [Quantum stockpile](https://dwarffortresswiki.org/index.php/Quantum_stockpile),
[gui/civ-alert (DFHack docs, 50.11-r3/r7)](https://docs.dfhack.org/en/50.11-r3/docs/tools/gui/civ-alert.html),
[gui/quantum (DFHack docs)](https://docs.dfhack.org/en/stable/docs/tools/gui/quantum.html),
plus Steam community discussion threads on civilian-alert replacement
behaviour and burrow-entrapment anecdotes, cited above at forum-level
confidence only, never treated as mechanic.
