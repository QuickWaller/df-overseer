# Handoff: fix the two live project bugs, then add amend and abandon

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live access.**

## Why

The user's bar for a minimal starting point (register 2026-10-01): the agents
run the fort for one game year hands-off. Projects are how accepted work is
tracked. Two live bugs make a project's status wrong, and the red team's F-3
(`research/2026-09-30-goal-tree-red-team.md`) found that nothing can change an
accepted project, so an escalation answer ("update, drop, abandon") has
nowhere to go. Read F-3, the register's 2026-09-30 rows, and
`handoffs/2026-09-30-project-mcp-tools.md` first.

## Tasks, in order (commit after each)

1. **Premature `done`.** `dfqueue/store.py` `project_status` (around line
   913) reports a step `done` when all its target rows are done or abandoned,
   so a step with **no target rows yet** reads `done` (`all([])` is true), and
   so can the whole project. A step with no rows and no `executed` record is
   `active` (or `pending`, match the existing vocabulary). Test both the step
   and the project level.
2. **`queue.executed` does not check the step.** An `executed` record with
   `step_id` is accepted even when its actions use a tool other than the
   step's declared tool, or when the step's `requires` are not yet
   satisfied. Refuse both at write time, naming the reason.
   `step_prerequisites_satisfied` (line 800) exists and has no callers: use it
   if it is right, fix it if not. Implicit steps (`implicit: true`, no tool)
   keep their current rules.
3. **Amend and abandon.** New record kinds (or one kind with an action
   field, your choice, justify it in the Result):
   - **amend**: the Overseer only (sole writer, same rule as `queue.project`)
     writes a new numbered plan version of an accepted project. Nothing is
     overwritten; the old version stays readable. Steps already executed
     keep their records; the amendment says which steps it replaces, adds or
     drops. Reason is required.
   - **abandon**: the Overseer only; the project and its open steps become
     `abandoned` with a reason; executed history is untouched.
   - `project_status` reads the latest version and shows the version number.
   - MCP tools in `dfmcp/queue_tools.py` for both, granted to the overseer
     only in `agents/overseer/tools.yaml`; update role counts in the
     Result (do not edit `CLAUDE.md`).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Follow existing idiom in `dfqueue/schema.py` (validated at write time) and
  `dfmcp/queue_tools.py` (NativeTool, `_reject_unknown_arguments`).
- Tests: ambient `python -m pytest` (with `lupa` on `PYTHONPATH` if you have
  it) and `dfmcp/tests` in `.venv-dfmcp` (at the main checkout). Report both
  counts. The known flaky race test is noted in `CLAUDE.md`.
- Stop and report on any permission refusal.

## Touched surfaces

`dfqueue/schema.py`, `dfqueue/store.py`, `dfqueue/render.py`,
`dfmcp/queue_tools.py`, `agents/overseer/tools.yaml`, `dfqueue/README.md`,
tests.

## Result

(fill in, about 200 words)
