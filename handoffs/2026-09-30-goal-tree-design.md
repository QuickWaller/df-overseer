# Handoff: goal trees, draft projects, a step runner, contention and priority (design)

Date: 2026-09-30. **Researcher, Opus, design only (no code).**

## Why

`research/2026-09-28-job-dependency-graph.md` (read it in full first)
designed projects and steps, and they are now built and live: `dfqueue`
project/step/observation records, `queue.project` (overseer, sole writer),
`queue.project_status`, step-level `queue.executed`, the `keeps_access` and
`item_present` guards, and room reservations (`res-N`, tile holds with
template-declared allowed kinds and one-off overrides). See `Working.md` and
the 2026-09-28 to 2026-09-30 rows of `decisions/DECISIONS.md`.

Talking it through with the user on 2026-09-30 produced a larger shape. This
brief records what the user has already decided and asks for the design that
makes it one coherent system, grounded in prior art, mapped onto what exists.

**Motivating evidence** (`evals/live/2026-09-25-first-real-conductor-cycle/`):
across the 2026-09-25 and 2026-09-28 cycles the agents rediscovered one
dependency chain by hand, one expensive cycle at a time. Brewing was proposed
(proposal-0005), failed for lack of empty barrels, a Carpenter's Workshop was
proposed (0006), brewing was deferred then rejected, and the Quartermaster
proposed brewing again (0009, a near-duplicate with a factual error). A goal
tree would have captured the chain once.

## Decisions the user has made (do not reopen; design within them)

1. **Every piece of work is a project.** A one-off job is a one-node project
   (the code already normalises a step-less proposal into one implicit
   step). Two exceptions: **emergencies** (tripwire, threat, flood) are
   reflexes, not plans; and **standing goals** ("keep at least 50 drinks")
   are projects whose goal check is re-read, reactivating their tree when it
   fails.
2. **The recursive rule.** Every node has its own checks, and every node is
   either (a) a **job**: one real tool call with real arguments, with checks
   for can-it-start (guards) and did-it-work (the tool's read-back), or (b) a
   **goal**: children arranged **in order** or **at the same time**, plus
   **its own check**, independent of its children (children succeeding is
   not the goal being met; a satisfied goal check skips the whole subtree).
   **No vague nodes**: a draft is rejected at filing unless every branch
   bottoms out in real jobs with checks. The one exception is an **open
   slot** a named role must fill (for example "needs a site for a
   Carpenter's Workshop", the Architect's to fill); a project with open
   slots cannot be accepted.
3. **Separate linked projects**, not one giant co-authored tree: "more
   booze" depends on "barrel production", which depends on "carpentry
   workshop". Each stays small with one owning role, the Overseer approves
   them one at a time, and a sub-project can serve several goals (barrels
   also store food).
4. **Role ownership.** The Quartermaster owns goals and supply chains; the
   Architect owns anything needing a place; the Overseer approves; the
   conductor runs and re-checks.
5. **Advisors draft, the Overseer amends or accepts.** A proposal can carry
   a full **draft project**. The Overseer may accept by reference (the cheap
   path) or amend and then accept, sending only changes (drop, add, update
   steps or nodes), never re-sending the whole plan. Amendments are recorded
   on the ruling (useful data on planner quality). Drafts are validated at
   filing, so bad plans bounce to the cheaper advisor. The advisor still
   never creates the project itself: that stays with the ruling.
6. **The conductor runs accepted steps, as code, not a model.** Each cycle
   it runs any step whose prerequisites are met, with exactly the approved
   arguments, reads the result, records `queue.executed`, and retries held
   steps quietly. It **escalates** only on real failure, ambiguity or a
   contradicted plan, waking a model with a short report, not the history.
   Escalation goes **straight to the Overseer** to start; a cheaper
   "foreman" role only if escalations prove frequent. This **changes the
   permission model** (today only the Overseer holds mutating tools,
   `dfmcp/roles.py`); design it narrowly (the conductor may run only a step
   an accepted ruling authorised, with exactly its arguments) and say
   precisely how it is enforced.
7. **Parallel where safe; contention is the real problem.** Tool calls are
   instant and dwarves work in parallel anyway. Conflicts over ground
   (solved: reservations), **materials** and **labor** must be claimed, and
   a conflict is a named hold ("waiting: logs claimed by project-4").
8. **Claims: exact where the game records it, self-healing elsewhere.**
   Exact: once a job holds items, DFHack shows which, and a finished
   building shows its materials; record what actually went where per
   project (claimed versus used). Self-healing: an unassigned claim is a
   count against free stock, and **never a running tally**: recompute every
   cycle from live state minus open claims, so an unseen loss corrects
   itself. Short means a named hold, never a guess. Claims release on
   project end; orphans are caught by the reconciler. **Optional hard hold
   for scarce items** by forbidding exactly those items (an ordinary player
   action, not armok) and un-forbidding when the job runs. Labor claims are
   recomputed the same way (the game, not us, assigns dwarves).
9. **Priority is computed by code, not decided fresh by a model.** Inputs:
   urgency as cost of delay (steep with a deadline for thirst, flat for
   comfort; the fort's vitals give real numbers), value over size (weighted
   shortest job first), **priority inheritance** (a blocker takes the
   priority of what it blocks, rising further when it unblocks several),
   aging (nothing starves), the existing active-project limit, and an
   Overseer override with a recorded reason.

10. **Checks declare how and when they are observed** (added mid-run by the
    user, sent to the researcher as a message): instant read-back, event or
    poll, and an expected time or "whenever"; an in-game event recorder
    bridges the DF process to the conductor; goals that cannot be checked
    exactly return met, not met or unknown/stale. Examples: building a
    still, killing an enemy, hauling hematite to a stockpile.

11. **Stuck versus waiting, with self-healing** (added mid-run): waiting is
    held for a named reason; stuck is no progress past the check's expected
    time with no reason. Healing ladder: re-check, re-issue, release claims
    so blocked projects proceed, escalate. Deadlock found by a wait-for graph
    over claims and broken on the lower-priority side.
12. **A ready queue across all active projects** (added mid-run): each cycle
    run every runnable step of every active project in priority order, never
    one project at a time. The scarce resources are labor, materials, space
    and model tokens, so the "time slice" is a fair share of labor per
    project plus a per-cycle model budget; DF itself assigns jobs to idle
    dwarves one level below.

## What to produce

`research/2026-09-30-goal-tree-design.md`: a design document, cited, honest
about what is unverified, marking verified versus proposed. Cover:

1. **Prior art, researched from primary sources**, restated domain-neutrally
   first (CLAUDE.md "research before designing"): hierarchical task network
   planning (compound versus primitive tasks, methods, preconditions),
   behaviour trees (sequence/parallel composition, success/failure
   semantics), MRP/bill of materials (recursive requirements against stock,
   netting, allocation versus reservation), OS scheduling (priority
   inheritance, aging, priority inversion), lean prioritisation (cost of
   delay, WSJF), and any game-AI planner work (GOAP, df-ai if relevant).
   Say what each contributes and what does not transfer.
2. **The node model**: goal and job nodes, in-order and at-the-same-time
   composition, the check vocabulary (goal checks, can-start guards,
   did-it-work read-backs; reuse the existing closed guard vocabulary where
   possible), open slots, linked sub-projects, standing goals. How it maps
   onto the existing `project`/`step` schema: extend it, or add a layer on
   top? Minimise breaking what is live.
3. **Drafting and amendment**: the proposal's draft shape, validation at
   filing, the amendment operations and their record, and token cost.
4. **The step runner** in the conductor: its cycle, the exact permission
   change and its enforcement, escalation triggers and report shape,
   idempotency (a step retried after a crash must not double-act), and the
   interaction with guards, reservations and holds.
5. **Claims**: materials, labor and ground under one model; recompute
   semantics; the exact-record path from job item references; the optional
   forbid-based hard hold (verify it is a player-visible action and how
   DFHack exposes it); what "orphan" means and how it is released.
6. **Priority**: the formula or ordering rule, where each input comes from
   (which live reads), how inheritance propagates through linked projects,
   and how the Overseer's override is recorded.
7. **The booze chain as the worked example**, end to end: the
   Quartermaster's draft, the Architect filling the workshop slot, the
   Overseer's acceptance, the conductor running steps, a contention hold, a
   blocker inheriting priority, and the standing goal reactivating later.
8. **Build order**, cheapest and most valuable first, each step shippable on
   its own, and what the user must decide at each point.
9. **Not verified**: every claim about DFHack or DF behaviour you could not
   confirm from source or a primary doc.

## Rules

- Design only: no code changes, no live mutation, no VM access needed. You
  may read DFHack source and docs (for example the job/item reference and
  forbid flag APIs) and the DF wiki.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in this handoff's Result section with a headline summary (about 250
  words) and the three decisions you think the user most needs to make.

## Result

(to be filled in by the researcher)
