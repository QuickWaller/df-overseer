# Handoff: labor.quota over autolabor

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

The register (2026-09-30, "set intent, let the game execute"): autolabor,
enabled on this fort, is the labour engine; our layer sets its per-labour
targets, and per-dwarf `set-labor` is the exception. The mechanism is
settled in `research/2026-10-01-quartermaster-levers.md` §2 (read it in full
first): autolabor is built and working at 53.16-r1, per-labour min, max and
talent pool are set through its CLI only (`autolabor LABOR MIN MAX POOL`),
with no Lua accessor; v50 work details have no headcount targets.

## Tasks, in order (commit after each)

1. `labor.quota LABOR MIN MAX [POOL] [DRY_RUN]` in
   `scripts/dfhack/df-overseer-labor.lua`: generic over every labour
   (validated against `df.unit_labor`), shells to the autolabor CLI the way
   the research proposes, refuses when autolabor is disabled (reuse the
   file's own `autolabor_enabled()` pattern), `DRY_RUN` default true.
2. `labor.quota-status [LABOR]`: reads autolabor's current settings per
   labour (parse its own text output, as the research says), plus how many
   dwarves currently hold each labour, so a model can see target versus
   actual.
3. The report after a real write reads the setting back from autolabor,
   never an echo.
4. `TOOLS.yaml` entries (mutating one tagged like the others), tests in the
   existing lupa style with a stub that models autolabor's CLI output; say
   plainly what the stub cannot prove.

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `agents/*/tools.yaml` (say in the Result which role gets which command;
  only the overseer may hold a mutating one).
- No em dashes in prose. No attribution lines in any commit. No armok
  capabilities.
- Tests: ambient `python -m pytest` and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-labor.lua`, `scripts/dfhack/TOOLS.yaml`, tests
and stubs.

## Result

(fill in, and the live test that would confirm it)
