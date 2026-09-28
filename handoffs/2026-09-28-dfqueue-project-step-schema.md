# Handoff: `project`/`step` records in `dfqueue` (the missing `plan` record)

Date: 2026-09-28. **Executor, Sonnet, worktree.**

## Context

`research/2026-09-28-job-dependency-graph.md` (Opus design, committed
`b0d3072`, reviewed by the user) is the design this implements. Read it in
full before writing any schema, especially §4 (the data model), §4.4-4.5
(state and storage), and §5.3 (how this maps onto the existing
proposal/ruling/execution queue). This handoff is item 2 of the design's
recommended build order (item 1, a standalone tool-layer guard, is a
parallel, independent stream and does not block this one).

`docs/AGENT-ARCHITECTURE.md` §9 and `dfqueue/README.md` already say a `plan`
record is missing between a ruling and its executions. This handoff builds
it, named `project` per the design (a `plan` record with steps), plus the
supporting pieces the design specifies.

## What to build

Read `dfqueue/schema.py`, `dfqueue/store.py`, and `dfmcp/queue_tools.py`
first to match this codebase's existing validation-at-write-time,
append-only, single-writer conventions (`docs/AGENT-ARCHITECTURE.md` §4) —
do not invent a different persistence style.

1. **`project` record** (design §4.1): id, `from_ruling` (the ruling that
   created it), optional `objective_id`, optional `template`, `summary`,
   `status` (derived from steps except `abandoned`, which is a decision),
   `because` (one line, always shown). A project holds an ordered list of
   **steps**, each: id, `tool` (must be a real tool id, validate against
   `scripts/dfhack/TOOLS.yaml` or however this codebase already validates a
   tool reference elsewhere — do not accept free text), `args`, a `targets`
   spec (either a literal set, or `{from_step, select}` meaning "this step's
   done targets"), `requires` (a list of other step ids, finish-to-start
   only, per the design's §2.2 recommendation — do not build the other three
   CPM link types, they were explicitly rejected), `trigger`
   (`all_success` default, or `all_done`), `prefer_after` (soft, list, never
   blocks), `guards` (a list of guard names from the tool's own default plus
   any named extras — this stream does not implement guard predicates
   themselves, that is the parallel `keeps-access-guard` stream; here you
   only need to store which guards apply to a step, as data).
2. **Extend `executed`, per the design's explicit instruction** (§4.4): add
   an optional `step_id`, and per-action optional `targets` (opaque handles,
   never coordinates — this repo's existing coordinate filter in
   `dfqueue/schema.py` must cover this new field, add a test that a
   coordinate-shaped string in it is rejected the same way it already is
   elsewhere) and `game_refs` (job/building ids, code-only). **Do not add a
   new record kind for "we did it"** — the design is explicit that `executed`
   already carries this correctly and a project's own prediction window
   starts at its first issued step.
3. **New `observation` record kind** (design §4.4): written only by code
   (never a model-authored field — validate this the same way other
   code-only fields in this schema are already protected, if such a
   mechanism exists; if not, flag that gap rather than silently skipping it).
   Per target: `consistent` / `contradicted` / `not_observable`, a reason, and
   the game tick it was read at (design §4.3's Kubernetes-conditions
   parallel — `ObservedGeneration`, `Status`, `Reason`). Observations never
   change recorded state (`project`/step status); they are compared against
   it separately, and a mismatch is drift, which this stream should represent
   but not act on (no reconciler yet, see below).
4. **Target-level state inside a step** (design §4.4's table): `waiting`,
   `ready`, `held`, `issued`, `done`, `failed`, `abandoned`, one per target,
   not just one per step — "4 of 5 issued, 1 held" must be representable
   (this is what would have shown building 22's hold as a durable, visible
   record instead of a hand edit). Fold from append-only records into a
   materialised table the same way `predictions` already works in this
   schema, per the design's explicit recommendation (§4.5) — read how
   `predictions` does it and mirror it, do not invent a second pattern.
5. **A `project.status` read tool** in `dfmcp/queue_tools.py` (or wherever
   read tools for the queue already live), returning one line per project:
   status, target counts by state, and the top blocker's reason if any is
   held — this is what design §6 says the Overseer's prompt should see, not
   the whole graph.
6. **Rollback handling** (design §4.4, "Rollback"): the design says compare
   the fort's current absolute tick to the tick on each target's latest
   record; anything recorded after the current tick is `contradicted:
   world_rolled_back`. Implement the comparison logic in the store (it needs
   the current game tick passed in, it should not itself call out to
   DFHack — keep this layer's existing separation between the queue store
   and any live-game access intact).

## Explicitly out of scope for this handoff

- Any guard **predicate** implementation (`keeps_access`, `item_present`) —
  a parallel stream owns those; you only store which guard names apply to a
  step, as an opaque list of strings.
- The reconciler (design build-order item 3) — no live-fort reads, no
  automatic observation-writing loop. That is `conductor/`'s job, later,
  once this schema exists for it to write into.
- Blueprint template `steps:` blocks (design build-order item 4) — later,
  once this schema is proven.
- `agents/*/role.md` charter changes for how the Architect/Overseer actually
  use projects day to day — flag what you think should change in your Result
  section, but do not edit charters in this stream.

## Rules

- `git merge --ff-only main` first.
- Match this codebase's validation-at-write-time and single-writer
  conventions exactly; do not introduce a second way of doing something this
  schema already does one way.
- Tests: one that a proposal with no `steps` block still becomes a valid
  one-step project unchanged (design §5.3, "every existing proposal type
  keeps working"); one that a coordinate-shaped string in a new `targets`/
  `game_refs` field is rejected by the existing coordinate filter; one that
  target-level state folds correctly from append-only records (mirroring
  however `predictions`'s own fold is tested); one for the rollback
  comparison; one for `all_success` vs `all_done` trigger semantics.
- No live mutation, no `dfhack-run` calls needed for this stream at all.
- No em dashes in prose. No attribution lines in any commit.
- Ambient `python -m pytest` (lupa on `PYTHONPATH`) and the `dfmcp` suite
  (`.venv-dfmcp`) should both stay green; rerun both, report counts.
- Commit as you go. Stop and report on any permission refusal.
- Fill in this handoff's own Result section: what you built, any place you
  deviated from the design document and why, test counts, and what you think
  is the right next step for `docs/AGENT-ARCHITECTURE.md` §9's charter text
  now that the `plan` record it describes actually exists.

## Result

