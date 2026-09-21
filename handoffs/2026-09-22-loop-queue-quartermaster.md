# Stream: queue execution, ask/answer, and the Quartermaster (agent loop MVP, items 4, 5, 7)

**Written** 2026-09-22. **Status:** dispatched. **User go-ahead:** given
2026-09-22 ("go put a sonnet on those"). Offline only: **no VM, no deploy, no
model call.** Sonnet executor, worktree-isolated.

## Why

`docs/AGENT-LOOP.md` is the design; read it in full. This stream gives the
queue what an unattended loop needs and makes the Quartermaster a real role:

- **Item 4.** Nothing records that an accepted proposal was carried out, and
  a prediction's window runs from when it was written. That is how
  `proposal-0001`'s window elapsed before anything could act. **Windows must
  start at execution.**
- **Item 7.** Advisors may ask the Consultant (register 2026-09-15); the
  Overseer may send a proposal to the Consultant for fact-checking before
  ruling (register 2026-09-17). One ask, one answer, no threads.
- **Item 5.** The Quartermaster is enabled for the MVP (user's call
  2026-09-22). Its closed proposal-type vocabulary: **`work_order`** (a
  manager order or a direct workshop job, standing repeat orders included),
  **`crop_plan`** (what a farm plot grows, per season), **`stock_target`** (a
  par level or cover-day target, `docs/PRODUCTION-MODEL.md` §10). No labor
  proposals: `set_labor` still races `autolabor`.

## First

`git merge --ff-only main` in your worktree (worktrees are cut from
`origin/main`; local `main` is ahead).

## Read first

`docs/AGENT-LOOP.md`; `docs/AGENT-ARCHITECTURE.md` §4 (records, the closed
vocabulary, predictions, the consultant exception, the fact-check); `dfqueue/`
(all of it, plus `dfqueue/README.md`); `dfmcp/queue_tools.py` and its tests;
`learning/live_signals.py`; `agents/quartermaster/` (`role.md`, `tools.yaml`),
`agents/architect/`, `agents/overseer/`, `agents/consultant/tools.yaml`;
`agents/CONFIDENCE-LEGEND.md`; `scripts/dfhack/TOOLS.yaml` for the real ids
of `orders.*`, `workjob.*`, farm, `stocks.*` tools.

## What to build

1. **Execution record** (`queue.executed`, Overseer only): references the
   ruling, the game tick at execution, and what was done (tool ids called and
   their outcome, success or failure; a failed execution is a valid record).
   **The grader measures `check_after_ticks` from the execution tick**; an
   accepted but never-executed proposal is never graded as a miss, it is
   reported as unexecuted. Keep existing records readable (migration or a
   compatible default, tested).
2. **Grading on demand**: whatever entry point the conductor service will call
   once per cycle to grade everything now due (a function, and a CLI if cheap).
   It must be safe to call repeatedly (idempotent).
3. **Ask / answer / fact-check.** `queue.ask` (architect, quartermaster,
   overseer): a question, optional proposal reference. A fact-check is an ask
   from the Overseer referencing a proposal; while one is open, that proposal
   cannot be ruled on. `queue.answer` (consultant only) answers one open ask.
   The Consultant needs a way to list open asks (extend `queue.pending` per
   role, or a new read; your call, justified). Answers are hypotheses: nothing
   in them overrides a graded prediction.
4. **Quartermaster.** The three proposal types above in `dfqueue/schema.py`'s
   per-role vocabulary; live prediction signals it will need (stock counts or
   cover days for a named item class, order completion) added to
   `learning/live_signals.py`, each readable through an existing read tool,
   following how the architect's signals were added; `agents/quartermaster/`
   made complete: `role.md` updated for being enabled, `tools.yaml` with its
   reads plus `queue.propose`/`pass`/`ask`, and a `model.yaml` (DeepSeek, as
   the other roles run live; look at theirs). **Do not flip `enabled` in
   `ROSTER.yaml`**: another stream owns that file; the orchestrator flips it at
   merge. Make sure `dfmcp/roles.py` validation would pass once it is flipped
   (a test that loads a roster with it enabled is ideal).
5. **Allowlists**: `queue.ask` for architect and overseer, `queue.executed`
   for overseer, `queue.answer` for consultant. The Overseer must hold the
   write tools needed to carry out Quartermaster proposals (`orders.create`,
   `workjob.*`, farm crop setting); check which it already has and report.

## Touched surfaces (yours only)

`dfqueue/` (all), `dfmcp/queue_tools.py`, `dfmcp/tests/test_queue_tools.py`,
`learning/live_signals.py`, `learning/tests/`, `agents/quartermaster/`,
`agents/architect/tools.yaml`, `agents/architect/role.md`,
`agents/overseer/tools.yaml`, `agents/overseer/role.md`, this doc, its
`handoffs/INDEX.md` row.

**Not yours:** `agents/ROSTER.yaml`, `agents/consultant/tools.yaml` and
`agents/consultant/role.md` (report the lines to add for answering asks), `dfmcp/roles.py`, `dfmcp/server.py`,
`dfmcp/registry.py`, `scripts/dfhack/`, `dfmcp/README.md` (report lines).

## Hard lines

- No VM, no SSH, no deploy, no model call. No push.
- Do not write `Working.md`, `decisions/` or `memory/`.
- No em dashes in prose.
- **Commit after each milestone** and extend the Result section as you go.

## Done when

Both suites pass (ambient `python -m pytest`, baseline 891 passed / 3
skipped; `dfmcp/tests` in `.venv-dfmcp`, baseline 537), counts reported, and
the Result section lists what was built, how it was verified, the lines owed
to files you do not own, and anything in the design you found wrong.

## Result

(executor fills in)
