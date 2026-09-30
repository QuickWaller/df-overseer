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

**All three tasks done, offline only, not live-verified.**

1. `project_status`'s "done" is now folded per step
   (`store.step_status`/`_step_has_executed_record`), never over the flat
   `step_targets` list: a step with no rows and no `executed` record reads
   `"active"`, never vacuously `"done"`. Regression tests at both the
   `step_status` unit level and the project level.
2. `queue.executed` now refuses (at `store.append`, before anything is
   written) an action whose `tool` does not match the named step's own
   declared `tool`, and a `step_id` whose `requires` are not yet satisfied,
   using the existing unused `step_prerequisites_satisfied` (it was
   correct, just uncalled). Implicit steps are exempt (no tool to match,
   trivial requires).
3. Two new record kinds, `amend` and `abandon` (a single kind with an
   action field was rejected: their required fields differ enough --
   `amend` needs a full replacement `steps` list, `abandon` needs none --
   that one kind would need its own internal branching anyway). `amend`
   carries the FULL new `steps` list per version (never a diff);
   `replaces`/`adds`/`drops` are declarative bookkeeping only, validated
   against the previous version. `project_status` resolves the latest
   `amend`'s own steps and reports a `version` number; a dropped step is
   simply absent from the latest list, no special-casing needed. `abandon`
   sets project status to `"abandoned"` with its `reason`; executed
   history and `step_targets` rows are never touched or rewritten.
   `queue.amend`/`queue.abandon` added to `dfmcp/queue_tools.py`
   (`NativeTool`, `sole_writer_only=True`) and granted only in
   `agents/overseer/tools.yaml`.

**Closed by later instruction (2026-10-01, same day):** the target-seeding
gap above is now enforced, not conventional -- `store.append` refuses an
`amend` that reuses a step id from the previous version unless that step's
whole definition is byte-identical after canonical JSON (`sort_keys=True`),
naming the step id otherwise; a changed step must take a fresh id and list
the old one in `replaces`/`drops`. New tests cover unchanged reuse
(accepted), changed reuse under the same id (refused), and a changed step
under a fresh id (accepted); one existing test that reused an id while
silently changing its target set was fixed to use a fresh id instead.

**Role tool counts** (`agents/*/tools.yaml` entry counts, offline; distinct
from CLAUDE.md's live-measured figures): overseer 92 -> 94 (`queue.amend`,
`queue.abandon`); architect 70, consultant 34, quartermaster 33, conductor
16, all unchanged.

**Tests:** dfqueue 218 -> 255 (37 new: schema validation, store write-time
gates including the byte-identical-reuse enforcement above, render
XML/public-view for `amend`/`abandon`); dfmcp 2 new in `test_roles.py`
(rule 6 for both new tools) plus 9 new in `test_queue_tools.py`. Final
full-suite counts (both reran clean after the enforcement change): ambient
`python -m pytest` 2116 passed, 3 skipped, 0 failures; `dfmcp/tests` in
`.venv-dfmcp` 722 passed, 0 failures (one run hit
`TestWriteSerialisation::test_concurrent_raw_appends_without_serialization_can_collide`,
CLAUDE.md's documented deliberate-race flake; it passed alone immediately
after and the full suite passed clean on rerun, so not a regression). No em
dashes added; no attribution lines; no live VM access; no permission
refusals encountered.
