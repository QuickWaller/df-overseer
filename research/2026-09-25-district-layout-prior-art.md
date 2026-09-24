# Districting: prior art before the design session

Date: 2026-09-25. Read-only research, answering
`handoffs/2026-09-25-district-layout-prior-art.md`. Read first, not repeated
here: `research/2026-09-24-room-layout-best-practices.md` (circulation, road
hierarchy, egress, travel-weighted facility layout, already covers Q6 of that
brief in depth), `research/2026-09-24-burrow-district-designs.md` (burrows as
the DF-native district mechanism), `research/2026-09-24-df-ai-fort-planner.md`
(df-ai's fixed-template placement, its tags as a coarse district primitive),
`research/2026-08-25-spatial-perception.md` (the graph-not-grid design rule
and its own six-tradition prior-art sweep, including MUD room-and-exit
graphs, robotics scene graphs, BWTA chokepoints and space syntax), and the
2026-09-24 "site-ranking system" and "df-ai" rows in `decisions/DECISIONS.md`.
No coordinate, grid, or map appears anywhere below, including in examples,
per `docs/PURPOSE.md` commitment 1.

## Bottom line

Every field surveyed here agrees on one move this project has not yet made:
**decide which areas relate to which other areas, and how strongly, before
deciding where anything goes.** Industrial engineering calls this the
relationship chart, architecture calls it the adjacency matrix and bubble
diagram, urban planning calls it use compatibility and buffering. All three
are explicit that this decision is qualitative and made by judgment, not
measurement, and all three have a mature answer for exactly the situation
this project is in: **no flow data.** Facility layout's own literature is
direct on this point (cited in Q1): "SLP-based approaches are suitable
alternatives once the layout planning objectives are not quantifiable" — the
letter-rating chart exists specifically to substitute for a flow number that
does not exist, not as a simplified stand-in for one that does. This
project's proxy (workshop kind implies stockpile kind,
`docs/PRODUCTION-MODEL.md`) is already the right shape of answer to that gap;
what is missing is the chart itself: a small, named table of closeness
judgments between district kinds, with a reason recorded for each one.

On the representation question (Q5), the evidence is consistent across
completely different research communities: **relational, graph-shaped
descriptions of space are the tractable representation for a language model;
raw coordinates and grids are not.** This is not a new finding for this
project (`research/2026-08-25-spatial-perception.md` already established the
graph-not-grid rule from six independent traditions) but it is now also
independently confirmed from the LLM-benchmark literature directly, searched
fresh for this report: recent work on room-adjacency and topological-graph
navigation reports it reduces hallucination and improves route planning
compared to coordinate-based state, and even the most direct test of formal
topological reasoning (LLMs answering Region Connection Calculus questions)
finds models "surpass chance... but fall short of exhaustive reasoning,"
which is a real ceiling worth naming rather than a clean pass.

The synthesis (Q6, proposed only) is a **closeness table between named
district kinds, plus a per-district scorecard of what a tool has actually
checked**, deliberately smaller than either the industrial-engineering
relationship chart or df-ai's tag system, because this project's agents
reason over relations, not over geometry, and the smallest structure that
still lets a tool verify something is the right size.

---

## Q1. Systematic Layout Planning and block layout

**Source kind: textbook/field-standard method (Muther's SLP, 1961, still the
name used across current facility-layout literature) plus current review
papers, both found by web search this session, not independently read from
the original monograph.**

The method, as consistently described across sources: start from **Product,
Quantity, Routing, Supporting services, Timing (the "P-Q-R-S-T" inputs)**,
then build an **activity relationship chart**: every pair of activities
(departments, workshops, functions) gets a **closeness rating** — A
(absolutely necessary), E (especially important), I (important), O
(ordinary), U (unimportant), X (undesirable/prohibited) — each with a coded
**reason** (shared personnel, shared equipment, sequence of process, noise,
convenience, safety). The ratings feed a **relationship diagram** (activities
placed so that high-closeness pairs sit near each other, low or negative
pairs sit apart), which is then converted to a **space relationship diagram**
once each activity's own area requirement is known, and finally to a
**block layout** — named areas with approximate shape and adjacency, still
not a dimensioned floor plan.

**What SLP needs as input, restated:** a list of activities, a closeness
judgment for every pair (or enough pairs to matter), a reason for each
judgment, and each activity's approximate space requirement. Flow
(quantity moved, trips per period) is one *source* of closeness judgment,
not the only one — the method's own reason codes include several that have
nothing to do with material flow (shared personnel, noise, safety, sequence
convenience).

**What happens when flow data is missing, stated directly by the field
itself:** this is not a degraded case SLP tolerates, it is close to the
case SLP was designed for. A current review found by this session's search
states it plainly: *"SLP-based approaches are suitable alternatives once the
layout planning objectives are not quantifiable, which poses a major
challenge for automated layout planning."* The same source notes the
inverse failure mode as a caution, not a strength: *"taking quantitative
factors as a single-objective function can generate solutions that are not
necessarily feasible because qualitative factors... can be more relevant,
such as closeness ratings among departments, flexibility or security."*
In other words, the field does not treat the letter-rating chart as a poor
substitute for a number; it treats an invented number, forced out of data
that was never really measured, as the more dangerous failure. That is a
direct, on-point answer to this project's own situation (`docs/
PRODUCTION-MODEL.md`'s "only a proxy exists" gap): the honest move is a
judgment table with reasons recorded, not a synthetic flow score dressed up
as measurement.

**Where the field itself says SLP fails**, per the same review literature:
reliance on "expert judgment and iterative manual adjustments," which does
not scale cleanly to "highly complex problems," and a structural tension
between qualitative closeness ratings (easy to elicit, hard to optimise
formally) and quantitative flow scores (easy to optimise, hard to elicit
honestly when the real flow is unknown or unmeasured) — the same tension
Q7 of the 2026-09-24 layout report already named for this project
specifically, now confirmed as a tension the source field names about
itself, not one unique to DF.

**Match against DF, honestly.** The P-Q-R-S-T inputs do not map cleanly:
DF has no "product" moving through a "routing" in the manufacturing sense,
and "quantity/timing" (how much of what, how often) is exactly the flow
data this project has already said it does not have. What transfers
cleanly is the **chart structure itself**: a small set of named district
kinds, a closeness judgment between every pair worth judging, and a reason
recorded per judgment — reasons that, for DF, would be things like "shares
a workforce" (a farmer's district near its dining hall), "produces for"
(a smithing district near an ore-processing district), "must stay apart"
(a tomb district away from anywhere living dwarves gather; the fort's own
recent ghost incident is exactly the kind of thing a well-reasoned X rating
would have flagged in advance), or "no relation" (most pairs, honestly,
which SLP's own U rating exists to record rather than force a decision on).
**What does not transfer**: block layout's later stages (space relationship
diagram, block layout proper) assume a floor plan is eventually drawn and
areas are shaped and sized geometrically — legitimate for the humans who
will read the fort's map, but exactly the step this project's agents must
never be asked to reason about directly (`docs/PURPOSE.md` commitment 1).
The chart stops being useful to hand to the model the moment it turns into
shapes; it stays useful as long as it stays a table of named pairs and
judgments.

## Q2. Land-use zoning

**Source kind: general urban-planning reference material, web search, not a
single authoritative textbook read in full.**

The core apparatus: a **use class** (residential, commercial, industrial,
and so on) defines what a district's land may be used for. Within a use
class, an individual use may be **permitted by right** (allowed everywhere
the use class applies, no extra review), **conditional** (allowed only
after case-by-case review against stated criteria, because it might be
compatible or might not depending on specifics), or **prohibited**. Where
two adjacent districts hold **incompatible** permitted uses (the recurring
example found: a multi-family building next to a single-family district),
a governing body can require a **buffer** — a strip of land, planting, or a
use restriction between them, reducing the conflict without requiring
either district to change. **Mixed-use** districts deliberately allow
several use classes together (rejecting the separation premise for that
one area); **single-use** districts exist for the opposite reason, to keep
incompatible activity apart by geography rather than by rule enforcement
at the boundary. Plans are **amended** as a city grows through a formal
process, sometimes preceded by a temporary moratorium on new applications
in the affected area while the amendment is decided, rather than by silent
drift.

**Which ideas map onto a fort that grows by population waves, stated
directly:**

- **Buffers between incompatible districts** map with almost no
  translation needed. This project's own recent incident (the ghost, laid
  to rest only once a Tomb zone was placed correctly) is exactly the kind
  of incompatibility a stated buffer rule would flag before it happens: a
  living/working district and a tomb district are the DF-native version of
  "residential next to industrial," and the underlying reason (undesired
  proximity causing a real, mechanically bad outcome) is the same shape
  urban buffering exists to prevent, not merely an aesthetic preference.
- **Conditional use** maps onto "a district kind is normally excluded from
  overlapping another kind, but a specific, checkable exception can allow
  it" — a useful vocabulary for cases like a small workshop legitimately
  sitting inside a district otherwise reserved for a different purpose,
  reviewed against a stated rule rather than either forbidden outright or
  silently allowed.
- **Amendment as a growth process, rather than silent drift**, is the
  single most directly applicable idea to a fort that grows by population
  wave: a district's boundary or purpose should change through a
  recorded, checkable step (a new district declared, an old one's
  intended use amended) rather than accreting ad hoc placements that
  eventually make the original district assignment meaningless. This is
  the zoning-field's version of df-ai's own worst-named failure mode
  (`research/2026-09-24-df-ai-fort-planner.md` Q4, Q6: a fixed plan
  silently exhausting its own ceiling with no re-planning step) — zoning
  answers "how do you grow" with an explicit amendment step; df-ai answers
  it with nothing, and breaks.
- **What does not transfer**: permitted-by-right versus conditional-review
  bureaucracy assumes a standing authority adjudicating applications over
  time, with no DF equivalent (there is no zoning board; there is a tool
  and an agent). The **regulatory weight** of a use class (legal
  enforceability, variance hearings) has no DF analogue at all; only the
  *classification and compatibility* idea is portable, not the process
  that enforces it in a real city.

## Q3. Space planning and adjacency in architecture

**Source kind: current architecture-practice web sources (archisoup,
illustrarch and similar practitioner references), web search, not a
citation-grade academic source.**

The **adjacency matrix** is a grid: every space in a building programme
against every other, each cell recording whether (and how strongly) the two
should be near each other. It is explicitly one of the **first** documents
an architectural programme produces, before any sketch. The **bubble
diagram** takes the matrix's relationships and gives them a rough,
non-dimensioned spatial arrangement — circles ("bubbles") sized loosely by
importance or area, connected by lines showing the desired adjacency,
deliberately still abstract, still easy to redraw wholesale. Only after
the bubble diagram is agreed does a schematic plan introduce real
dimensions, structure and site constraints.

**Why architects decide relationships before shapes, stated by the sources
found:** the matrix and bubble diagram are cheap to revise wholesale (a
line moved, a bubble redrawn) in a way a dimensioned floor plan is not;
committing to shape and size before relationships are settled means every
later relationship change forces a geometric rework, while committing to
relationships first means the geometry that follows only has to satisfy
constraints that are already agreed. The factors driving a relationship
judgment, per the same sources: frequency of interaction, operational
dependency, privacy, and security — a superset that includes and extends
SLP's own reason-code list (Q1) with two entries (privacy, security) that
have direct DF analogues (a noble's office wanting separation from general
traffic; a vault or prison wanting controlled access).

**Match against DF.** This is the cleanest transfer of any field surveyed
here, because it is structurally the same problem SLP solves (Q1), stated
in a different field's vocabulary, and because it already answers this
project's own stated design question directly: "decide the districts and
how they relate" **is** the adjacency-matrix step, word for word. The
distinguishing value architecture adds over SLP is the explicit two-stage
separation of *relationship* (the matrix) from *rough spatial gesture*
(the bubble diagram) from *real geometry* (the schematic plan) — three
separate artifacts, each with a different level of commitment. For this
project, the matrix is exactly the artifact worth keeping model-facing;
the bubble diagram's "rough spatial gesture" stage is precisely the one
this project must never build, because a bubble diagram is a drawing, and
`docs/PURPOSE.md` commitment 1 forbids showing a model anything shaped like
one, however abstract. **What does not transfer**: the bubble diagram
itself as an artifact (inherently a 2D drawing) and everything past it;
only the matrix survives as something an agent should ever see.

## Q4. Colony and city-builder games other than df-ai

Kept short per the brief. Only what is documented in each game's own wiki
or forum, web search this session, no game installed or run.

- **RimWorld.** The **Zone/Area** system is the game's own primitive: named
  regions that cannot overlap each other, used for stockpiles (each
  configured to accept specific item categories, with a numeric priority
  that lets a higher-priority stockpile pull items away from a lower one)
  and for **allowed areas** (restricting where a colonist or animal will
  travel; a colonist takes the shortest path inside their allowed area and
  only leaves it if no path exists inside it, mirroring this project's own
  connectivity-graph findings for a different purpose). A **home area** is
  a specific named allowed-area convention (cleaning, firefighting, repair
  happen only inside it) that expands automatically around anything built.
  This is a real, player-facing districting primitive, but it is a
  **restriction and prioritisation mechanism**, not a relationship or
  adjacency mechanism: nothing in the sources found states that RimWorld
  computes or advises on which zone should sit near which other zone; that
  judgment stays entirely with the player, same as this project's own
  burrow-as-district finding (`research/2026-09-24-burrow-district-designs.md`
  Q1) for DF's own burrow mechanic.
- **Oxygen Not Included.** Rooms are recognised automatically by full
  enclosure (walls, doors) rather than by manual player designation, and
  each recognised room kind carries **stated requirements** (the wiki's own
  "Room Requirement" category) that a room overlay can check directly
  against. A separate **priority** system (numeric, 1-9, applied per
  building or job) governs task ordering, not spatial placement. No source
  found describes ONI computing or suggesting adjacency between rooms; like
  RimWorld, placement judgment is left entirely to the player. The
  requirement-checked-room idea is the one piece worth naming as prior art
  this project already has a DF-native analogue for (this project's own
  zone-kind requirements work, `research/2026-09-23-room-and-zone-
  requirements.md`, cited in the 2026-09-24 layout report), not something
  new to import.
- **Factorio.** No zoning or district primitive exists in the base game at
  all, by this session's search: Factorio's spatial organisation is
  entirely emergent from belt/pipe/rail routing between individual
  machines, not from a named-area mechanic. Worth stating plainly as a
  negative finding rather than searching harder for something that is not
  there: Factorio is not evidence for or against a districting approach,
  because it does not have the concept.
- **SimCity (the RCI tradition).** The clearest primitive for demand-driven
  district *classification*: three zone types (Residential, Commercial,
  Industrial), each independently placed by the player, with a **demand
  meter** computed from the interaction between the other two (industrial
  demand rises when residents want jobs, commercial demand rises when
  residents want shops, and so on) and a **density** that grows over time
  driven mainly by the road class bordering the zone. This is the one game
  in this survey with an explicit inter-district relationship the game
  itself computes (demand as a function of the other zones' population and
  balance) rather than leaving entirely to the player, and it is worth
  naming as the nearest thing to an automated relationship judgment found
  in this whole games survey — though it optimises population/economic
  balance, not spatial adjacency, and still says nothing about which zone
  should sit *near* which other zone; SimCity's zones can be anywhere,
  demand is not a proximity term.
- **What this survey did not find anywhere in the genre**: any colony or
  city-builder game whose own mechanics compute or recommend adjacency
  between districts the way SLP or an architectural adjacency matrix does.
  Every game surveyed treats "which area goes where" as entirely a player
  decision, with the game providing only classification (zone kind),
  restriction (allowed area, room requirement) or aggregate demand
  (SimCity's RCI), never a closeness judgment between named areas. Stated
  plainly because it is itself informative: **the district-relationship
  question this project is trying to solve has no game-industry precedent
  to borrow from**; SLP and architecture (Q1, Q3) are the only fields
  surveyed across this whole prior-art pass (including the four earlier
  research files) that actually answer it.

## Q5. Representing a spatial plan without geometry

**Source kind: mixed. The qualitative-spatial-reasoning formalism (RCC-8)
is an established academic field with decades of literature; the LLM
evidence is current (2024-2026) arXiv preprints found by fresh web search
this session, not independently re-run or verified against a live model by
this session.**

**Qualitative spatial reasoning, briefly.** RCC-8 (Region Connection
Calculus) formalises spatial relationships between regions using eight
jointly exhaustive, mutually exclusive base relations — commonly named
disconnected, externally connected, partial overlap, equal, tangential
proper part, non-tangential proper part, and the two inverse "part of"
relations. The formalism deliberately avoids coordinates: two regions'
relationship is stated topologically ("touches," "is inside," "overlaps"),
not by any measured distance or position. Cardinal and above/below
relations form a separate, smaller qualitative vocabulary for orientation
rather than containment/connection. Both traditions share the same design
principle this project has already adopted independently
(`docs/PURPOSE.md` commitment 1, arrived at from a different direction):
relationships, not coordinates, are the unit of representation.

**Graph representations of buildings.** Room-adjacency graphs (nodes are
rooms, edges are direct connections, sometimes annotated with what
separates them — a door, an open threshold, a wall) and space syntax
(covered already, in more depth, in `research/2026-08-25-spatial-
perception.md` §2.6) are both established as the standard way to reduce a
building's geometry to something a non-geometric reasoner can use. Nothing
in this session's search contradicts or meaningfully extends what that
earlier report already found on space syntax; it is not repeated here.

**What the evidence says an LLM handles well, found fresh this session and
therefore reported at more depth than the above:**

- **Room-adjacency and topological graphs measurably help.** Recent
  work on LLM-guided indoor navigation and object search reports that
  "explicit topological encoding through knowledge graphs improves route
  planning, reduces hallucination errors, and strengthens spatial
  consistency" compared to coordinate-based state, and that converting a
  cell-level map into a graph of rooms and connections "enables
  coordination over room instances instead of individual... cells while
  preserving spatial relationships and reducing the reasoning state for
  the language model." This is an independent, more recent confirmation
  of the same finding `research/2026-08-25-spatial-perception.md` already
  drew from AriGraph and Hydra (graph representations outperform raw
  transcripts/grids), now specifically from the room-adjacency-graph
  literature rather than the robotics or MUD literature.
- **Direct topological reasoning (RCC-8 itself) is a real but genuine
  ceiling, not a clean win.** A paper testing current models' ability to
  answer RCC-8 composition and neighbourhood questions directly (asking
  the model to reason formally about the calculus itself, not merely to
  use a graph as context) found models "surpass chance... but fall short
  of exhaustive reasoning, especially under relation anonymization or
  complex composition queries," and separately that models are
  "inconsistent in being able to reason correctly about a relation but not
  its inverse." Even the best-performing model tested did not answer every
  RCC-8 question correctly. **This matters for design, not just as a
  caveat**: it means a tool should not lean on a model to *derive* new
  topological facts by chaining given relations together (composing "A
  connects to B" and "B connects to C" into a claim about A and C) — that
  composition step is exactly where the cited paper found models weakest.
  A tool should hand the model whichever relations it needs already
  computed and stated, not rely on the model to infer an unstated one from
  two stated ones.
- **Coordinate- and grid-based representations underperform relational
  ones for this class of task**, consistent with (not contradicting)
  every finding already in `research/2026-08-25-spatial-perception.md`.
  One grid-reasoning benchmark found this session notes text descriptions
  of space carry their own cost (multiple ways to phrase the same
  relationship, creating "descriptive bias," and a granularity limit before
  the description becomes unwieldy) — a real caution about relational text
  specifically, not just a point in its favour, and worth carrying into
  the synthesis below: a relational representation must still be
  **canonical** (one fixed way to state a given relationship, not left to
  free phrasing) to avoid reintroducing the ambiguity problem the same
  source flags.

**What this does not settle, stated plainly.** No source found this session
tests the exact task this project needs (an LLM reasoning about *named
districts and their declared relationships to each other*, as opposed to
room-to-room navigation or formal RCC-8 puzzle questions). The evidence
above is the closest available proxy, and it points the same direction
`research/2026-08-25-spatial-perception.md` already committed to
independently, which is corroboration, not fresh proof of this project's
specific use case.

## Q6. Synthesis for this project (proposal, not a decision)

**Everything in this section is a proposal for the owed design session, not
a design decision. It is offered as a smallest starting point to argue
with, following the pattern SLP, architecture and zoning all converge on:
relationships and classification before anything geometric.**

**The smallest district representation that could carry the relationships
from Q1 to Q3 to an agent, in words:**

1. A small, fixed vocabulary of **district kinds** (production, living,
   storage, tomb/memorial, administrative, and so on — the exact list is
   the design session's to set, not this report's). Each district a named
   instance of exactly one kind, the same "kind selects behaviour, data not
   code" principle this project already holds as a standing rule
   (`CLAUDE.md`, "tools must be generalisable").
2. A **closeness table** between every pair of district *kinds* (not
   instances — the table is small and fixed even as the fort grows), each
   cell one of a small ordered set of judgments (drawn from SLP's own
   vocabulary, Q1: something like "wants to be near," "no preference,"
   "wants to be apart," "must not overlap"), each judgment carrying a short
   stated **reason** — shared workforce, shared material, noise/disruption,
   or safety, mirroring both SLP's reason codes and architecture's
   adjacency factors (Q1, Q3). This table is small (kinds squared, not
   instances squared) and is exactly the artifact `docs/PRODUCTION-MODEL.md`
   was missing a home for: the "workshop kind implies stockpile kind"
   proxy already in use becomes one populated row of this table rather
   than a special case living only in code.
3. Per **district instance**: its kind, a short list of the buildings or
   zones (already-named landmarks, per `research/2026-08-25-spatial-
   perception.md`'s existing landmark/exit vocabulary) it currently
   contains, and — critically — a small set of **tool-computed relation
   facts** to its neighbouring districts: whether it is reachable from each
   neighbour (this project's existing `check_reachable`), and whether any
   closeness-table rule it participates in is currently satisfied or
   violated (an X-rated pair actually overlapping; an A-rated pair with no
   direct connectivity). This is the district-level equivalent of the
   candidate rule tables the 2026-09-24 layout and burrow reports already
   built for rooms and burrows, extended one level up.

**Which relations a tool must compute and check deterministically:**
reachability between two named districts (already built);
overlap/containment between a district's declared footprint and another
district's or a hazard's footprint (already the same geometric-containment
technique used for the furniture/room-value and burrow-completeness checks
in the two 2026-09-24 reports); and, for every closeness-table rule
involving a pair of district kinds that both currently have an instance,
whether that rule currently reads satisfied or violated. None of this
requires a model to see or infer geometry; all of it is exactly the shape
of check this project's tools already perform elsewhere (`zone.place`'s
refusal to strand, the layout report's `invariant`/`metric` rule tables),
extended from single rooms and burrows to named districts.

**Which choices are left to the agent:** which closeness judgment to assign
a given pair of district kinds in the first place (a genuinely qualitative
call, same as SLP's own reason-coded ratings, not something a tool can
derive); which kind a new district should be, and roughly how large it
should grow before a new district of the same kind is declared instead of
extending the existing one (the zoning field's "amendment" idea, Q2 — an
explicit, agent-visible decision point rather than silent drift, and the
same anti-df-ai lesson `research/2026-09-24-df-ai-fort-planner.md` already
drew about fixed ceilings failing silently); and how to resolve a reported
violation (move something, accept the conflict with a stated reason, or
split a district) once a tool has reported one exists. The tool's job ends
at reporting a fact in words; every judgment call about what that fact
should mean for the plan stays with the agent, the same division of labour
`docs/AGENT-ARCHITECTURE.md` already uses for every other tool in this
project.

---

## What could not be verified

- **Muther's original Systematic Layout Planning monograph** was not read
  directly; every SLP claim above is drawn from current review articles
  and reference pages found by web search, which is standard practice for
  a decades-old, still-cited method but is a second-hand reading of the
  original text, not a primary-source read.
- **No live test of an LLM reasoning over this project's own proposed
  district-closeness table.** Q5's evidence is drawn from published
  benchmarks on adjacent but not identical tasks (room navigation, formal
  RCC-8 puzzles); none of it is a direct test of the representation
  proposed in Q6, which does not exist yet to test.
- **Colony/city-builder survey (Q4) is deliberately shallow**, per the
  brief's own instruction to keep it short and use only what is
  documented. Deeper mechanics (mod ecosystems, any AI-planning mod with
  its own design notes for these specific games) were not searched for
  beyond what surfaced in the queries run this session; a mod-specific
  pass was out of scope here.
- **Whether RimWorld, ONI or SimCity's own community has ever built an
  unofficial adjacency-scoring layer on top of these games** (a mod, a
  spreadsheet tool, a community convention) was not searched for; the
  survey covers only what each game's own mechanics do, per the brief.
- **The RCC-8/LLM paper's exact model list and score table** were not
  independently reproduced; the "surpasses chance but falls short of
  exhaustive reasoning" and "inconsistent on inverse relations" findings
  are taken from the paper's own reported results, read via search-result
  summary rather than the full paper text.
- **Land-use zoning's amendment process** is described generically (per
  the sources found); no single jurisdiction's actual ordinance was read,
  since the brief asks for the field's general shape, not one city's
  specific rules.

## Sources

Repo, read in full this session (not repeated, per the brief):
`research/2026-09-24-room-layout-best-practices.md`,
`research/2026-09-24-burrow-district-designs.md`,
`research/2026-09-24-df-ai-fort-planner.md`,
`research/2026-08-25-spatial-perception.md`,
`decisions/DECISIONS.md` (2026-09-24 "site-ranking system" and "df-ai"
rows), `CLAUDE.md`, `docs/PURPOSE.md` (commitment 1),
`docs/PRODUCTION-MODEL.md` (referenced, not re-read in full),
`docs/AGENT-ARCHITECTURE.md` (referenced, not re-read in full).

Web, searched this session (search-result summaries, not full papers read
end to end unless noted): Systematic Layout Planning / activity
relationship chart overview pages (Wikipedia's "Activity relationship
chart," Richard Muther Associates' own SLP overview PDF, Grokipedia
summaries); facility-layout review literature on SLP's qualitative-versus-
quantitative tension (ScienceDirect and Taylor & Francis review articles,
titles cited inline above); land-use zoning terminology (PropertyMetrics,
Wikipedia's "Zoning," UNC School of Government's conditional-zoning
pages); architectural adjacency matrices and bubble diagrams (archisoup,
illustrarch); RimWorld's own wiki (`rimworldwiki.com`, "Zone/Area,"
"Allowed area," "Home area," "Stockpile zone"); Oxygen Not Included's own
wiki (`oxygennotincluded.wiki.gg`, "Priority," "Category:Room
Requirement"); SimCity 4/2013 zoning and demand references (StrategyWiki,
Wikipedia); RCC-8/region connection calculus (Wikipedia's "Region
connection calculus," and an arXiv paper titled "Can Large Language Models
Reason about the Region Connection Calculus?", read via search-result
summary); room-adjacency/topological-graph LLM navigation papers found by
search (arXiv preprints on topological-graph-guided indoor navigation and
spatial-memory graph construction, titles cited inline above, read via
search-result summary, not fetched in full). No web source's full text was
independently fetched and re-read past the search tool's own summary this
session; where a claim above is load-bearing, that is flagged inline
rather than presented as a direct primary-source read.
