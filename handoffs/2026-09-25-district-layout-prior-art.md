# Handoff: deciding which area goes where, and describing it without a map

Date: 2026-09-25. **Researcher. Read-only. No VM, no fort.**

Read `CLAUDE.md`, then these, and do not repeat them:
`research/2026-09-24-room-layout-best-practices.md` (its Q6 already covers
circulation, road hierarchy, egress and pairwise travel-weighted facility
layout), `research/2026-09-24-burrow-district-designs.md`,
`research/2026-09-24-df-ai-fort-planner.md`, and
`research/2026-08-25-spatial-perception.md`. Also the 2026-09-24
"ranking system" and "df-ai" rows in `decisions/DECISIONS.md`.

## Why

This is the last prior-art pass before a design session on **districting**:
areas of the fort designated for production, living, tombs and so on,
instead of every placement ranked alone against a landmark. Earlier passes
covered placing one thing near another. Nothing yet covers the step before
that: **deciding the districts and how they relate**, or how to represent a
district plan so an LLM agent can reason about it **without ever being shown
a map** (`docs/PURPOSE.md` commitment 1, a hard rule). The flow between areas
is not measured on this fort; only a proxy exists (workshop kind implies
stockpile kind, `docs/PRODUCTION-MODEL.md`).

## The questions

1. **Systematic Layout Planning and block layout** (industrial engineering):
   the activity relationship chart (closeness ratings such as A/E/I/O/U/X
   with reasons), the relationship diagram, space requirements, and how a
   block layout is derived from them. What inputs does it need, and what
   happens when flow data is missing (the qualitative ratings exist partly
   for that)? What did the field learn about where SLP fails?
2. **Land-use zoning** (urban planning): use classes, permitted and
   conditional uses, buffers between incompatible uses, mixed-use versus
   single-use districts, and how plans are amended as a city grows. Which of
   those ideas map onto a fort that grows by population waves?
3. **Space planning and adjacency in architecture**: adjacency matrices and
   bubble diagrams as a pre-geometry stage. Why do architects decide
   relationships before shapes?
4. **Colony and city-builder games other than df-ai** (RimWorld, Oxygen Not
   Included, Factorio, SimCity, any colony-sim AI or planning mod with
   public design notes): how zoning and area designation work as a player or
   AI primitive. Keep this short; only what is documented.
5. **Representing a spatial plan without geometry**: qualitative spatial
   reasoning (topological relations such as RCC-8, cardinal and
   above/below relations), graph representations of buildings (room
   adjacency graphs, space syntax), and any work on LLMs reasoning over
   such relational descriptions versus coordinates or grids. What does the
   evidence say an LLM handles well?
6. **Synthesis for this project**: sketch, in words, the smallest district
   representation that could carry the relationships from Q1 to Q3 to an
   agent, which relations a tool must compute and check deterministically,
   and which choices are left to the agent. Mark it as a proposal for the
   design session, not a decision.

## What to produce

`research/2026-09-25-district-layout-prior-art.md`: a bottom line first,
then the answers, then the synthesis, then "What could not be verified" and
sources. Each field taken on its own terms, then matched honestly against DF
(say plainly where an idea does not transfer and why). Mark claims by source
kind (textbook or paper, official docs, forum or second-hand). No coordinate,
grid, or map anywhere in the output, including examples.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- You own that research file and this doc's Result section only. Not
  `Working.md`, `decisions/`, `memory/`, `doctrine/`, `handoffs/INDEX.md`.
- No em dashes in prose. **No attribution lines in any commit message.**
- Commit after each milestone. Stop and report on any permission refusal.

## Done means

All six answered or declared unanswerable with what was tried, the flow-data
gap addressed directly in Q1, and a synthesis the design session can argue
with.

## Result

Done. All six questions answered in
`research/2026-09-25-district-layout-prior-art.md`, none skipped.

Bottom line: every field surveyed (Systematic Layout Planning, architectural
adjacency matrices, land-use zoning) converges on deciding relationships
between named areas before anything geometric, and SLP's own current
literature states directly that its qualitative closeness-rating chart is
"suitable... once the layout planning objectives are not quantifiable," i.e.
built for exactly this project's missing-flow-data situation rather than a
degraded stand-in for a number. No colony/city-builder game surveyed (Q4)
computes or recommends adjacency between areas the way SLP or an
architectural matrix does; that question has no game-industry precedent to
borrow from. On representation (Q5), relational/topological graphs measurably
help LLM performance in the fresh literature checked this session, but direct
formal topological reasoning (RCC-8) has a real ceiling, not a clean win,
which argues for tools stating relations directly rather than expecting a
model to compose them.

The proposal (Q6, marked explicitly as a proposal, not a decision): a small
closeness table between named district *kinds* (not instances) carrying a
reason per judgment, plus a per-district-instance list of contained
landmarks and tool-computed relation facts (reachability, overlap/violation
against the closeness table), reusing this project's own existing
reachability and geometric-containment tooling rather than adding new
primitives. Which closeness judgment to assign, when to split a district,
and how to resolve a reported violation stay with the agent.
