# Handoff: generalise job/task dependency tracking, design only

Date: 2026-09-28. **Researcher, Opus. Design and research, no code changes, no
live mutation.** Read-only against this repo, DFHack's source/docs, and
external prior art.

## Context

Today, live, on the real fort: `scripts/dfhack/df-overseer-construction.lua`'s
`mine-vein`/`build` split fixed a smoothed-over hematite vein in the Manager's
Office (zone 13). Right after building the 5 replacement walls for real, a
wider ad hoc scan (a one-off `dfhack-run lua` script, not a tool) found the
vein continues well past that single ring: 26 more unmined ore wall tiles
nearby, 5 already exposed. One of the 5 wall buildings just designated (id 22)
turned out to sit directly next to unmined ore. Its build job had to be found
and suspended by hand (`job.flags.suspend = true` via a raw script) as a
stopgap, because nothing in this codebase's model of "a job" knows that a
wall-build job at tile T should not proceed while a neighbouring tile still
holds unmined economic ore, or more generally, that some jobs have real
prerequisites on other jobs or on world state that today are only enforced by
a human noticing and hand-editing game state.

This is not a new problem. `Working.md`'s "still open" list already carries an
agenda item (2026-09-28, user's call) that a room's own build order should be
modeled as a dependency graph with explicit prerequisite edges rather than a
fixed ordered stage list, motivated by the exact same vein-smoothed-into-a-wall
root cause (`decisions/DECISIONS.md` 2026-09-24). That item also already
settled one design point worth carrying forward: **node-completion state
should be tracked explicitly, not derived live** (the user overrode the
orchestrator's "derive it from the game" instinct) — reusing the existing
queue's `executed-000X` record shape rather than inventing a new one, with live
reads used only to reconcile/catch drift, never as the primary source of
truth. A separate, older item (`decisions/DECISIONS.md` 2026-09-24, the
site-ranking/`ranked_rects` critique) is explicitly deferred to "a dedicated
design session with an Opus model and the user," not an incremental patch —
the same posture applies here.

**Today the user widened the ask past room-build stages specifically**: track
every small job as a module of a larger job, generally, not just the
mine-then-wall sequence. The user has asked for an Opus session on this,
generalised, given how narrowly the room-build framing was scoped before.

## The question

Design (do not build) a generalised model for representing jobs, their
composition into larger jobs, and dependency/prerequisite relationships
between them, usable across this codebase's very different existing job-like
concepts:

- DF's own native job system (`Dig`, `SmoothWall`, `ConstructBuilding`,
  `MakeBarrel`, etc. — `scripts/dfhack/df-overseer-stuckjobs.lua`,
  `df-overseer-workjob.lua`, `df-overseer-orders.lua` read these).
- This project's own multi-step tool-driven sequences (mine-vein then build,
  a room's dig-shell then furniture then zone then owner).
- The proposal/ruling/execution queue (`dfqueue/`, `docs/AGENT-ARCHITECTURE.md`
  §4) — proposals already carry rulings and executions; is a "job" a new
  concept layered on top, a specialisation of what's there, or something the
  queue schema should absorb directly?
- Manager work orders (`df-overseer-orders.lua`) — known broken/inert
  (`decisions/DECISIONS.md` 2026-09-24, user's ruling to set aside investigating
  *why*), but still a fourth "unit of intended work" shape worth accounting
  for in a general model even if not investigating its bug.

## What to produce

A design document, `research/2026-09-28-job-dependency-graph.md` (or a `docs/`
design doc if that fits this repo's convention better — check `docs/` first),
covering:

1. **Prior art first** (`CLAUDE.md` rule: research before designing from
   scratch, state the problem domain-neutrally). This is a task/job dependency
   graph problem — the same shape as build systems (Make, Bazel, Buck), CI/data
   pipeline DAGs (Airflow, Dagster, Prefect), game engine job/task graphs, and
   classic project-management critical-path/PERT scheduling. Read at least a
   few of these for real (source or primary docs, not just search summaries —
   this codebase's own research files get marked down for relying on search
   summaries, see `research/2026-09-25-district-layout-prior-art.md`'s
   caveat). What do they use for: representing a node's completion state,
   representing "blocked on" edges, handling a completed node whose physical
   evidence later becomes ambiguous (this project's specific wrinkle: a mined
   vein tile is indistinguishable from ordinary floor), and re-checking/
   invalidating a graph when the world underneath it changes without warning
   (a dwarf could un-do a wall, a caravan could remove stock, etc.)?
2. **A concrete data model**: what a job node is, what a dependency edge means
   (must-complete-before vs must-not-conflict-with vs soft-preference), where
   it's stored (extend `dfqueue`'s schema? a new sibling store? file-based?),
   and how it reconciles against live game state per the user's already-settled
   "track explicitly, reconcile via live reads" ruling.
3. **How each of the four existing "unit of work" shapes above maps onto it**,
   concretely, not abstractly — walk the actual zone-13 mine-then-wall case
   end to end through the proposed model, showing what would have made
   building 22's job get created already-suspended (or refused at
   designation time) instead of needing a human's one-off scan.
4. **What changes for the agents** (`agents/*/role.md`, `docs/AGENT-ARCHITECTURE.md`):
   who creates a job graph, who queries "is this blocked," whether "no armok
   capabilities" or "tools must be generalisable" constrain the design (they
   should — check `docs/ARMOK-RULINGS.md` and the generalisability rule in
   `CLAUDE.md` project-specific rules before proposing anything job-kind-
   specific).
5. **An honest scope call**: is this one graph across the whole fort, one per
   room/zone, one per "project" (a user- or agent-declared unit of intended
   work spanning many tiles/jobs)? State your recommendation and why, and say
   plainly what you're not confident about.

This is a design document to bring back for the user's review, not a
green-lit build — do not write implementation code, do not touch
`dfqueue/schema.py` or any tool file, do not deploy or touch the live fort.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Read-only against this repo and the live fort (if you check anything live,
  read-only `dfhack-run` calls only, no writes) — the zone-13/building-22
  situation above is already handled, do not touch it further.
- Do NOT touch `Working.md`, `decisions/DECISIONS.md`, `memory/`, or
  `handoffs/INDEX.md` (the orchestrating session owns those and will fold
  your findings in).
- No em dashes in prose. No attribution lines in any commit.
- Commit your research file when done. Stop and report on any permission
  refusal.
- Fill in this handoff's own Result section with the headline recommendation
  in under 250 words, pointing at the full document for detail.

## Result

Done, design only: `research/2026-09-28-job-dependency-graph.md`.

Recommendation: four layers. A proposal (decision) becomes a **project** when
accepted (the `plan` record §9 already says is missing), made of **steps**
(one generic tool action over a target set); DF jobs are observed evidence
attached to steps, never graph nodes. Three edge kinds: `requires`
(finish-to-start, recorded explicitly, `executed` reused with a `step_id`),
**guards** (closed, data-listed world predicates checked per target by code,
modelled on DFHack `suspendmanager`'s reason enum), and soft `prefer_after`.
Recorded and observed state stay separate fields; mismatch is drift for the
Overseer, never auto-overwritten (Terraform refresh, Kubernetes conditions).
Scope: one store per fort in `dfqueue`, organised by project; guards
fort-wide.

A reachability-based `keeps_access` guard in `construction.build`, evaluated
jointly over the step, would have refused building 22 at designation time.
Proposed build order: that guard first (no schema change), then projects,
then the reconciler.

Live findings (read-only): mined vein floor still reads HEMATITE, so the
premise is partly wrong (the ruling stands on who/when/intent instead);
`build` walls any open ring tile, a doorway hazard; `suspendmanager`
(currently off) would unsuspend job 2705 if enabled; the "26 ore tiles"
scan counted hidden tiles, which no agent-facing tool may.

