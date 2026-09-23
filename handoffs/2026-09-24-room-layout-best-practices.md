# Handoff: best practices for room and fortress layout

Date: 2026-09-24. **Researcher. Read-only.** No code, no doctrine edits, no
deploy, no fort mutation, no unpause.

Read `CLAUDE.md` first, then `research/2026-09-23-room-and-zone-requirements.md`,
`docs/PURPOSE.md` design commitment 1 (never show or reconstruct a map), and
`scripts/dfhack/df-overseer-zone.lua`'s header for what this project can
currently place.

## Why

This project is about to design a layout planner: parameterised layout
families, a traffic hierarchy for hallways, wall reuse scored across adjacent
rooms, and a checker that can score a plan before anything is dug. Before
designing that from scratch, find out what players and other fields already
know. This repo's standing rule applies: state the problem domain-neutrally,
ask which fields already own it, and read those.

**A sibling stream is settling whether enclosure is a game requirement**
(`handoffs/2026-09-24-room-enclosure-and-value.md`). Do not answer that
question or touch `doctrine/seed.yaml`; it owns both. Where your sources make
a claim about enclosure, report it as a claim and point at that stream.

## The questions

1. **What layout patterns do experienced players actually use**, and why?
   Name the recurring ones concretely (bedroom blocks off a spine, double
   loaded corridors, stacked z-levels sharing a stairwell, workshop clusters
   beside their stockpiles) and say what each optimises for. Patterns are the
   deliverable, not anecdotes.
2. **Corridor width and traffic.** What widths are used for what, and what
   actually goes wrong at width 1? Cover congestion, hauling, and the specific
   case of a dwarf unable to pass another. Relate it to DF's own per-tile
   traffic designation (High/Normal/Low/Restricted), which is a real
   pathfinding cost multiplier and which this fort has never set on a single
   tile.
3. **Vertical layout.** Reuse across z-levels may matter more than reuse
   within one. What do stairwell placement, vertical stacking and depth cost
   or save, in dig and in travel?
4. **Doors.** When is a door worth its cost, when is it harmful, and what are
   the real mechanical effects (pathing, privacy, value, fluids, vermin,
   temperature)? Separate mechanics from habit.
5. **What are the classic layout mistakes**, stated so a checker could detect
   them? This is the most directly useful section: each one wants a name, the
   symptom, and the geometric condition that would catch it. A rule a tool can
   evaluate beats a paragraph of wisdom.
6. **Cross-domain prior art.** At minimum: architectural space planning and
   circulation, road hierarchy from urban planning (arterial, collector,
   local, and the rule that a high class never dead-ends into a low one),
   building-code egress and clearance, and facility layout from industrial
   engineering (the travel-weighted adjacency problem, which is exactly the
   "put the workshop near its stockpile" question). Take what fits and say
   plainly what does not.
7. **Two objectives.** Build cost and movement cost conflict. How do these
   fields handle that, and what does the community do in practice? Note that
   real dwarf traffic frequencies are unknown to us, so say what proxies are
   defensible.

## Honesty requirements

Player practice is **opinion and convention**, not game rule, however
confidently it is stated. Keep the two apart everywhere. This project has
twice mistaken a preference for a requirement (`prefer_indoors`, the wiki's
20-citizen Manager claim), and a layout checker built on folklore would
encode it permanently.

Flag anything version-sensitive. The v50 transition changed rooms from
furniture-defined to zones, so older advice may describe a game that no longer
exists. Where a source predates that and you cannot date it, say so.

## What to produce

`research/2026-09-24-room-layout-best-practices.md`, and that file only. Lead
with a verdict paragraph, then the evidence, in the style of the existing
research specs. End with **a candidate rule set for the checker**, each rule
tagged `invariant` (reject) or `metric` (rank), and tagged `game mechanic` or
`convention`. That list is what the next build stream will work from, so it
matters more than the prose above it.

If you want doctrine entries written, propose them in your Result section for
the orchestrating session to route. Do not write them yourself.

## Rules

- Read-only. Prefer the local wiki snapshot and the install's own data; bounded
  live queries only if genuinely needed, nothing mutated, never unpaused.
- Use `bash scripts/vm-ssh.sh df '<cmd>'` for any VM command. Do not write your
  own ssh wrapper and do not read an address out of `.env`.
- `git merge --ff-only main` first; this brief is committed on main.
- **Never render or reconstruct a map**, and keep every output
  coordinate-free. Describe a pattern in words and dimensions, never as a grid.
- You own that one research file and this doc's Result section. Not
  `doctrine/**` (the sibling stream owns it), not `Working.md`,
  `decisions/DECISIONS.md`, `memory/` or `handoffs/INDEX.md`.
- No em dashes in prose. **No attribution lines in any commit message.**
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

A named set of layout patterns with what each optimises for, a corridor and
traffic section grounded in DF's own designation enum, the classic mistakes
expressed as conditions a tool could check, cross-domain prior art that earns
its place, and a candidate rule set tagged invariant or metric and mechanic or
convention. Honest about what is convention and what is version-sensitive.

## Result

Done, read-only, `research/2026-09-24-room-layout-best-practices.md` written
(and only that file, plus this Result section). No VM commands were run;
this session found the questions answerable from the repo's own prior
research (`research/2026-09-23-room-and-zone-requirements.md`) and current
v53.16-banner wiki pages, so no live query was needed and none was made.
`doctrine/seed.yaml` and the enclosure question were not touched.

**Verdict, restated briefly**: almost everything in DF layout folklore
(corridor width numbers, named patterns like the line design, fractal
families, staggered doorless rooms, workshop wings) is player convention,
current-namespace-sourced (v53.16 banners) so not stale from the v50 zone
transition, but never confirmed against this install's own data because
DFHack exposes no congestion, travel-time or traffic-cost telemetry this
project can read. Only a handful of things are verified game mechanic: the
four-tier traffic designation system and its real per-tile pathfinding cost
multiplier (1/2/5/25) plus its own stated limit (job choice itself ignores
it); door behaviour as a floodgate-equivalent with no operating delay; stair
vertical-alignment constraints; and, install-verified from yesterday's
stream, that a room-value zone's own footprint must contain its
value-bearing furniture (this fort's real, live failure).

**The one finding worth flagging loudest**: `Bedroom_design` (current
v53.16 banner) states plainly that dwarves take no penalty from others
walking through their bedroom while sleeping, which directly undercuts the
common "add a door for privacy" habit for bedrooms specifically. Proposed
as a doctrine entry (not written) in the research file's own section, in
the same family as the `prefer_indoors` correction this project has already
made once.

**The candidate rule set** (research file, final section before "What could
not be verified") has 13 numbered rules, each tagged invariant/metric and
game mechanic/convention, plus an explicit list of what was deliberately
not proposed and why (door-for-value, meeting-hall/animal-conflict, any
absolute travel-distance threshold, anything about enclosure). Two doctrine
entries are proposed for the orchestrating session to route, not written
here: traffic designation being real but unused on this fort, and the
bedroom-door-privacy correction above.

**Not verified, said plainly in the file**: live congestion/traffic-cost
data from the actual fort (none readable from DFHack); whether a door
contributes to room value (sibling stream's question); vermin/temperature
door effects; any numeric stairwell-count-per-population threshold; the
`Meeting_hall` page's animal-conflict claim (older-version banner, not
independently confirmed); whether DF literally deadlocks two dwarves
meeting on a 1-wide corridor versus one yielding (relied on this project's
own prior working knowledge, not re-checked this session). A dedicated
`Corridor` wiki page does not exist at the URL tried (404); corridor
guidance was drawn from `Bedroom_design`, `Workshop_design` and search
results instead.

**Owed register lines** (not written here, per the `handoffs/` rule -- the
orchestrating session owns `Working.md`, `decisions/DECISIONS.md`,
`memory/` and `handoffs/INDEX.md`):
- `Working.md`: this handoff done, read-only, research file at
  `research/2026-09-24-room-layout-best-practices.md`; the next build
  stream (layout checker) should start from its candidate rule set, and two
  doctrine entries are proposed and awaiting routing (traffic-designation
  status; bedroom-door-privacy correction).
- `decisions/DECISIONS.md`: worth a row noting the bedroom-door-privacy
  finding as a corrected assumption, parallel to the existing
  `prefer_indoors` and 20-citizen-Manager rows, since it is the same shape
  of mistake (folklore treated as requirement) caught before it was
  encoded anywhere.
- `handoffs/INDEX.md`: flip this handoff's row to done.
