# Handoff: red-team the goal-tree design (find the cracks)

Date: 2026-09-30. **Researcher, Opus, review only (no code).** Dispatched
only after `research/2026-09-30-goal-tree-design.md` lands
(`handoffs/2026-09-30-goal-tree-design.md`). You are not its author: your
job is to find where it goes wrong, not to improve its prose.

## Why

The user's call: this is a large rework of how every piece of fort work is
planned, authorised, run and prioritised, so an independent Opus should look
for the cracks before anything is built. Assume the design is wrong
somewhere important and find where.

## Read first, in full

The design document and its brief; `research/2026-09-28-job-dependency-graph.md`;
`docs/AGENT-ARCHITECTURE.md`; `docs/ARMOK-RULINGS.md`; `docs/PURPOSE.md`;
`dfqueue/schema.py`, `dfqueue/store.py`, `dfmcp/queue_tools.py`,
`dfmcp/roles.py`; `scripts/dfhack/df-overseer-reservations.lua`;
`evals/live/2026-09-25-first-real-conductor-cycle/README.md` and
`evals/live/2026-09-30-reservations-deploy/README.md`; the 2026-09-28 to
2026-09-30 rows of `decisions/DECISIONS.md`. The user's settled decisions
are listed in the design brief; you may argue one is wrong, but say so
explicitly and separately from findings about the design itself.

## Where to look (at minimum)

1. **Authority and safety.** The conductor running steps changes the
   sole-writer model. Can a step do something no ruling authorised
   (argument drift, a template or target set resolving differently at run
   time than at ruling time, a replayed or duplicated step, a stale ruling
   after the world changed)? Can an advisor's draft smuggle authority
   through the Overseer's accept-by-reference? Does anything widen what a
   model can make the fort do?
2. **Liveness.** Deadlock (two projects each holding what the other needs),
   livelock (a step retried forever, a hold that never clears), starvation
   despite aging, priority inversion that inheritance does not fix, a
   standing goal that thrashes (reactivates, overshoots, reactivates),
   cycles through linked sub-projects.
3. **Truth and drift.** Where recorded state and game state can disagree
   undetected; claims that "self-heal" into the wrong answer; what DF does
   that the model assumes it will not (dwarves using claimed stock, jobs
   cancelled and recreated, items moved or destroyed, forbid flags cleared
   by other tools or the player); the no-armok and hidden-information rules.
4. **Failure and recovery.** A conductor crash mid-step, a server restart,
   a save reload (a test-harness power), a half-built structure, an
   escalation nobody answers, a model that never replies.
5. **Cost and scale.** Where tokens are still spent needlessly; whether
   drafts and amendments stay small in practice; how the priority
   computation and recompute-every-cycle claims scale with many projects.
6. **Gaps.** Anything the design needs but does not specify, anything it
   specifies that the existing code cannot support without unacknowledged
   work, anything verified-sounding that is actually unverified.
7. **Observability and timing.** For each kind of check: can it actually be
   observed the way the design says (instant read-back, event, poll), is
   the event bridge from the DF process on VM 103 to the conductor on VM
   106 sound (lost events, duplicates, a restart between event and read),
   and are "unknown" or "stale" results handled rather than forced to
   true or false? Test the user's three contrasting examples: building a
   still, killing an enemy, hauling a chunk of hematite to a stockpile.
8. **The worked example.** Walk the booze chain adversarially: what breaks
   it?

For each finding: severity (blocks building, must fix before a given build
step, or watch), a concrete failure scenario (inputs, state, what goes
wrong), where in the design it lives, and a proposed fix or the question
the user must answer. Rank most severe first. Say plainly when you checked
something and found it sound, so silence is not mistaken for approval.

## Deliver

`research/2026-09-30-goal-tree-red-team.md`, and this handoff's Result
section: a ranked summary of the top findings (about 250 words) and which
design build steps each blocks.

## Rules

- Review only: no code changes, no live access.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.

## Result

(to be filled in by the reviewer)
