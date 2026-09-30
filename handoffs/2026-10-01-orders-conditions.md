# Handoff: manager orders with conditions, repeat and material class, generic over job type

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

Standing goals are manager orders with conditions and repeat (register
2026-09-30 and 2026-10-01: set intent, let the game execute; the Manager
works, per the user). `df-overseer-orders.lua` today creates orders for a
hardcoded table of 12 jobs, with an amount only. The mechanism is settled
from source in `research/2026-10-01-quartermaster-levers.md` §1 (read it in
full, with its file and line citations, first).

## Tasks, in order (commit after each)

1. `orders.create` generic over job type: any live `df.job_type` name (and
   reaction name for custom reactions), per-kind detail read from the game or
   data, never a per-job branch (`CLAUDE.md`, tools must be generalisable).
   Keep the existing duplicate check and `DRY_RUN` default true.
2. Optional arguments, each through the `workorder` JSON path the research
   verified: frequency (OneTime, Daily, Monthly, Seasonally, Yearly), item
   conditions (item type, material or material class, comparison op, value),
   order conditions (another order id and its Activated or Completed state),
   and material category (the class filter; stone and wood for building
   materials by default, matching `DEFAULT_CLASS_CATEGORIES` in
   `df-overseer-building.lua`). Arguments stay flat strings the model can
   write (design a compact syntax and document it); refuse malformed ones
   with a named reason.
3. `orders.reorder ID POSITION` and `orders.recheck ID`, per the research's
   shapes (§1), `DRY_RUN` default true.
4. Reports read back the order as the game holds it (conditions, frequency,
   validated and active bits), never an echo of the request.
5. `TOOLS.yaml` entries, and tests in the existing lupa style; a stub that
   rejects what the real `workorder` path would reject. Say plainly what the
   stub cannot prove.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `agents/*/tools.yaml` (say in the Result which role gets which command).
- No em dashes in prose. No attribution lines in any commit. No armok
  capabilities.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-orders.lua`, `scripts/dfhack/TOOLS.yaml`, tests
and stubs.

## Result

(fill in, about 200 words, and the live test that would confirm it)
