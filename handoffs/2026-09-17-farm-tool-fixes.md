# Handoff: fix the two live bugs in df-overseer-farm.lua

**Dispatched:** 2026-09-17, by the orchestrating session. **Executor:** Sonnet, worktree-isolated.
**Stream status:** see `handoffs/INDEX.md`.

## Why

Two bugs were found live on 2026-09-17 while building Uniboslan's first farm plot. Both were worked around by hand and are recorded in `docs/TRAPS.md`, but neither is fixed in code (`Working.md`, HANDOVER 2026-09-17, START HERE item 2):

1. **`plant_id` written before construction completes is lost.** Set before the plot finished building, all four seasons read back as -1. The order that worked: build, wait for `flags.exists`, then set the crop, then read it back. This was verified live, but the mechanism was not read from source.
2. **`build_farm_plot` calls `dfhack.buildings.setName`, which does not exist on this install**, through an unchecked `pcall` (around line 529). The tool reports a name ("Farm Plot #n") that was never set, and the game keeps its default name. `set_farm_crop` finds plots by name (`find_farm_plot_by_name`), so check whether this also breaks finding a plot.

## Goal

The farm tools tell the truth and can't silently lose a crop setting:
- **`farm.build`** never claims a name or crop it didn't set. It either names the plot through an API that exists here, or it stops claiming a name and reports how the plot can actually be identified.
- **`farm.set-crop`** refuses a plot that isn't constructed yet (`flags.exists` false), with an error saying what to do (wait for construction to finish). After a real write, it reads `plant_id` back and reports failure if the value didn't stick.
- **Finding plots** works for plots whose name was never set, including the existing plot on Uniboslan.
- **Every `pcall`** in the file has its result checked.

Design commitment #1 still holds: no raw coordinates leave the script.

## Verification without mutating the fort

- **Read-only checks against the live fort (VM 103) only.** Examples: whether any naming API exists (`dfhack.buildings`, the building struct's own name field), how the existing plot reads, and whether `find_farm_plot_by_name` can find it. Dry runs are fine.
- **No real build and no real crop write.** The orchestrator runs those later, with the user aware.
- **Leave the fort paused.** Confirm `dfhack.world.ReadPauseState()` is true before your first read and after your last. If it's ever false, stop and report.
- **Test your changed script without replacing the deployed one.** DFHack caches scripts by name in the running process (`docs/TRAPS.md`), so a same-name copy may not even load. Run your version from a temporary, uniquely named copy in `/tmp` with `dfhack-run lua -f` or an equivalent, and delete it afterwards. Never leave files under DF's script paths.

## Constraints

- **Branch** from current `main` and commit on your worktree branch.
- **Test suites** on `main`: the ambient `python -m pytest` gives **306 passed, 1 skipped**, and `.venv-dfmcp` `dfmcp/tests` gives **165**. `.venv-dfmcp` won't exist in your worktree, so say which interpreter you used.
- **Traps:**
  - `dfhack-run lua -e` silently does nothing on this build; use `-f` with a file.
  - Every output line carries an ANSI prefix.
  - Never set DFHack globals; use `local` only.
  - Check every `pcall` result.
- **VM access:**
  - Use the `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user `df`.
  - **Read those keys only**, with `grep -E '^KEY=' .env`. Never `cat` or filter the whole file.
  - No hostnames, addresses or tokens in anything you write.
- **Don't edit** `Working.md`, `decisions/`, `ROADMAP.md`, `CLAUDE.md`, `memory/`, `research/`, `doctrine/`, or `docs/TRAPS.md`. The orchestrator records traps: put any new ones in your report.
- **Don't deploy** to VM 103.

## Touched surfaces

`scripts/dfhack/df-overseer-farm.lua` and this doc. **Not** `scripts/dfhack/TOOLS.yaml` (another stream owns it today): if the `farm.*` entries' notes or arguments need to change, put the exact proposed text in your report.

## Report

- What you changed and why.
- What you verified live, with the command for each check.
- What could only be verified by a real build or crop write, written as a short test plan for the orchestrator's next supervised run.
- Proposed `TOOLS.yaml` text, if any.
- New traps.
- Suite counts and the interpreter you used.
- Your branch name and commit hashes.
