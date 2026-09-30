# Handoff: let agents use projects (MCP tools over dfqueue's project/step records)

Date: 2026-09-30. **Executor, Sonnet, worktree.**

## Context

`dfqueue` gained `project`/`step`/`observation` records on 2026-09-28
(`handoffs/2026-09-28-dfqueue-project-step-schema.md`, commit `b6afd13`):
schema, store (`store.project_status`, `step_prerequisites_satisfied`,
`rollback_drift`), and XML renderers (`render.project_status_line`). Nothing
exposes them over MCP, so no agent can create or read a project today. The
design is `research/2026-09-28-job-dependency-graph.md`; read §6 (roles and
who writes what) and §7 (what agents see) in full before starting.

## What to build

1. **`queue.project` (write, overseer only).** Creates a project from an
   accepted ruling, following the design's rule that the Overseer's ruling
   instantiates the project. Enforce it through the same `sole_writer`
   machinery `queue.rule`/`queue.executed` use in `dfmcp/roles.py`, not a
   role-name check. Validation is the store's own (one project per ruling,
   ruling must be accepted, step tool ids from the registry, `requires`
   acyclic). Surface store errors the way the other queue tools do.
2. **`queue.project_status` (read).** One line per project, per design §6,
   using `render.project_status_line`. Grant it to overseer and architect.
   Grant it to the conductor too if its allowlist takes queue reads today;
   check `agents/conductor/` and say what you did.
3. **Step execution records.** Check whether `queue.executed` already
   accepts `step_id` and per-action `targets`/`game_refs`/`target_state`
   end to end (the schema supports them). If the tool's input schema
   strips or rejects them, fix that. Coordinates stay filtered as today.
4. **`observation` stays conductor-only.** Do not expose an observation
   write to any model role. If the conductor needs an MCP path to write
   one, say so in your Result; do not build the reconciler (out of scope).
5. **Docs.** Name the `project` record in `docs/AGENT-ARCHITECTURE.md` §9,
   where it is listed as missing today, pointing at the schema and design
   doc. Update the tool descriptions in `dfmcp/tools.py`/`queue_tools.py`,
   the role allowlists under `agents/*/tools.yaml`, and any test that pins
   role tool counts.

## Since this brief was written

- `dfmcp/tools.py` now scopes argument descriptions per command, then per
  script, then bare (`handoffs/2026-09-30-reservation-gaps.md`, merged
  `36d9c67`); `_describe` takes an optional `tool_id`. Use that, do not
  assume the older shape.
- Everything through `36d9c67` is deployed on VM 103; live role counts are
  overseer 85, architect 51, consultant 29, quartermaster 24, conductor 15.
  Report the new counts your grants would give.
- Read the codebase-wide rules list in
  `handoffs/2026-09-30-reservation-gaps.md` and follow it.

## Out of scope

- The conductor reconciler and blueprint template `steps:` blocks (design
  build-order items 3 and 4).
- Any deploy to VM 103 or live mutation.
- Guard predicate implementations beyond what exists.

## Rules

- `git merge --ff-only main` first.
- `dfmcp/tests` in `.venv-dfmcp` (the main checkout's venv; worktrees carry
  none) and ambient `python -m pytest` (lupa on `PYTHONPATH`) stay green;
  report both counts. Add tests for: overseer creates a project from an
  accepted ruling; a non-writer is refused by the roles layer; a second
  project for the same ruling refused; status renders one line per project
  and never a coordinate; `queue.executed` with a `step_id` round-trips.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in the Result section below, including the new per-role tool counts.

## Result

(to be filled in by the executor)
