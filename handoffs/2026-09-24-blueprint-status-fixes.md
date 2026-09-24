# Handoff: the blueprint verb's status misreported twice on the live fort, and the runner drops a real answer

Date: 2026-09-24. **Offline build. No deploy, no VM mutation, no fort change.**
Read-only ssh source reads on the game VM are allowed.

Read `CLAUDE.md`, `evals/live/2026-09-24-office-build-2/README.md` and
`diagnosis.md`, `evals/live/2026-09-24-consultant-ghost/` and
`evals/live/2026-09-24-consultant-room-description/` (the runner defect),
`scripts/dfhack/df-overseer-blueprint.lua` (`dig_progress`, `dig_jobs_in_site`,
the `shell_done` computation, `status`), `conductor/runner.py`.

## Defects, each found live

1. **`dig_progress()` false stall.** It counts a designation as pending only while
   the tile's dig flag is set, but DF clears the flag once a job exists. Site-2's
   entrance gap had a real Dig job (unclaimed, id 2275) and status read `stalled`
   because the 9 interior cells were correctly job-less until the gap was dug.
   Fix: a site with any Dig job in it is never `stalled`; report `in_progress`
   with the job count and whether any has a worker; report `stalled` only when
   startable designations exist with no job for the grace period.
2. **`status shell_done` false positive.** It read true while 11 of 15 ring tiles
   were rough and undesignated. Fix: `shell_done` must be computed from the cells
   the template requires (dug, smoothed) read directly, per cell, not from
   designation or job counts; return the per-cell counts (dug, smooth, rough,
   undesignated) so a caller can see why.
3. **`conductor/runner.py` drops the answer.** `RunResult.final_answer` reads the
   envelope keys `finalAnswer` and `final_answer`, but this openclaw envelope
   returns the answer under `final` (and `payloads[0].text`). A real Consultant
   run returned null and had to be repeated. Fix: read all of them in a defined
   order, and add a test with a recorded real envelope shape (the raw envelope is in
   `evals/live/2026-09-24-consultant-ghost/run-output.json`; use its structure,
   not its text).

## Scope

Yours: `scripts/dfhack/df-overseer-blueprint.lua`, `conductor/runner.py`,
`tests/test_blueprint_lua_logic.py`, `tests/lua_stubs/dfhack_blueprint_world.lua`,
a conductor runner test, and a short addendum to
`research/2026-09-24-quickfort-hands.md`. **Do not edit `scripts/dfhack/TOOLS.yaml`**
(another stream owns it): if status field notes need updating, list them in your
Result. Not yours: `df-overseer-nobles.lua`, `df-overseer-zone.lua`, and per the
`handoffs/` rule `Working.md`, `decisions/DECISIONS.md`, `memory/`,
`handoffs/INDEX.md`.

## Rules

`git merge --ff-only main` first. Baselines: ambient **1494 passed, 3 skipped**
(lupa on PYTHONPATH from a scratch `pip install --target`), `dfmcp/tests` in
`.venv-dfmcp` **652 passed**. Commit as you go. No live fort change. No em dashes,
no attribution lines, coordinate-free output, stop on any refusal and never route
around one.

## Done means

Tests reproduce both incidents (a fake world with a Dig job present and the flag
clear must not be `stalled`; a fake world with 11 rough ring tiles must not be
`shell_done`) and fail on the old code, which the Result shows. A runner test
with the `final` envelope yields the answer. The Result names the post-deploy live
check.

## Result

Done offline, three commits on the executor branch. Ambient 1503 passed, 3 skipped (baseline 1494 plus 5 Lua plus 4 runner).
- dig_progress: any dig/carve/smooth job in the site means in_progress, never stalled. New dig fields: jobs_in_site, jobs_claimed_by_a_worker (null if getWorker unreadable).
- site_status: shell_done now from shell_cells (per-cell read): carve_required/dug/solid, smooth_required/done, rough, undesignated, hidden, unreadable.
- runner: _final_answer reads finalAnswer, final_answer, final, payloads[].text in that order.
- Old code fails the new tests (5 Lua via BLUEPRINT_LUA_UNDER_TEST on the prior file; 2 runner tests on the prior runner).
- TOOLS.yaml notes to update by its owner: status gains dig.jobs_in_site, dig.jobs_claimed_by_a_worker, shell_cells; shell_done semantics changed (per-cell, needs smoothing done).
- Post-deploy live check: status on site-2 (Dig job on the gap) must read in_progress with jobs_in_site >= 1; status on the site with 11 rough ring tiles must read shell_done false, rough 11, undesignated 11 (or current live equivalents); confirm jobs_claimed_by_a_worker is a number, not null (proves dfhack.job.getWorker exists on the build); a Consultant run must return a non-null final_answer.

