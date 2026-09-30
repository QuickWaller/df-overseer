# Handoff: audit existing plans and infrastructure against "set intent, let the game execute"

Date: 2026-09-30. **Researcher, Sonnet, review only (no code changes).**

## The policy (the user's call, 2026-09-30)

**Our layer decides *what* the fort should achieve and *whether it is working*.
How dwarves, workshops and materials get scheduled is the game's job. We only
step in where the game genuinely cannot.** Read the 2026-09-30 rows at the end
of `decisions/DECISIONS.md` in full first, especially "Principle: set intent,
let the game execute" and "Applying ... to what exists". Specific rulings
already made there:

- **Materials:** our layer chooses a material class and writes it into
  buildingplan's own filter; the game picks items.
- **Manager work orders work** (the user's observation) and are the main route
  for workshop production and standing goals; `workjob.queue` is the fallback;
  workshops may be dedicated to purposes natively.
- **Labor:** autolabor (enabled on this fort) is the default engine; we set its
  per-labor targets; per-dwarf `set-labor` is the exception.
- **Priority:** our computed level maps onto native levers (designation
  priority 1 to 7, manager order sequence, DFHack `prioritize`, burrows).
  **"Do now" is reserved for genuine problems and emergencies**, never routine
  ordering. `prioritize` is worth using (its armok status still to confirm).
- **`production/`:** wire the bill-of-materials walker as one read and observed
  consumption/production rates; freeze the rest.
- **Lean core** to build next; everything else agreed on 2026-09-30 is deferred
  direction.

## What to review

Every component, sorted into exactly one of these, with evidence (file and
line, or a doc quote):

- **Keep**: perception ("is it working?") or a legitimate step-in the game
  cannot do (say why the game cannot);
- **Simplify onto a native mechanism**: name the DF or DFHack mechanism, what
  our code would become, and what it would no longer need to do;
- **Fallback only**: keep, but not the default path;
- **Unused or ahead of need**: nothing calls it, or it serves a deferred
  feature; freeze, do not extend;
- **Conflicts with the game**: two systems writing the same thing (as
  `set-labor` versus autolabor did).

Scope, all of it:

1. `scripts/dfhack/*.lua` with `scripts/dfhack/TOOLS.yaml` (every command).
2. `dfmcp/`, `dfqueue/`, `conductor/` (including `policy.yaml`, triage,
   `order_watch`), `production/`, `learning/`, `dfseries` references,
   `gotchas`, `doctrine/`.
3. `agents/*/role.md` and `tools.yaml`: charters that tell a role to do what
   the game should do, or that omit the native route.
4. **Plans**: `ROADMAP.md`, `Working.md`, and the designs
   `research/2026-09-28-job-dependency-graph.md`,
   `research/2026-09-30-goal-tree-design.md`,
   `research/2026-09-30-goal-tree-red-team.md`,
   `research/2026-09-30-item-binding-design.md`, plus any other `research/` or
   `docs/` design still marked as planned: which parts the policy makes
   unnecessary, which it changes, which it leaves.

Also list **native mechanisms we are not using but should consider** (for
example work-order conditions, workshop profiles, stockpile links and
settings, burrows, designation priority), each marked verified or unverified
on this install (`memory/dfhack-environment.md`, `docs/DFHACK-INVENTORY.md`,
`docs/ARMOK-RULINGS.md`, the local DFHack docs if present in the repo).

## Deliver

`research/2026-09-30-policy-audit.md`: a short answer up front, the table per
area, the native-mechanism list, and a proposed ordered change list (smallest,
most valuable first), each marked as a user decision where it is one. Fill in
this handoff's Result section (about 200 words).

## Rules

- Review only: no code changes, no live access.
- First step `git merge --ff-only main`; commit the document's plan early,
  then after each section.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Mark verified versus unverified. Do not guess DF behaviour; say "unverified".
- Stop and report on any permission refusal.

## Result

(to be filled in by the reviewer)
