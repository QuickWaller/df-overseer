# Handoff: make dig-stair honest, and make failed writes real errors

**Dispatched:** 2026-09-17, by the orchestrating session. **Executor:** Sonnet, worktree-isolated. **User go-ahead:** "deploy the sonnet", for this code fix only.
**Stream status:** see `handoffs/INDEX.md`.

## Why

The live test (`handoffs/2026-09-17-farm-stair-live-test.md`, Result) found that `diggable.dig-stair` reported ok for both halves, but designated only the z167 up stair. Its rank-1 spot sits under the fort's Stockpile. `research/2026-09-17-stairs.md` found the cause, and the orchestrator confirmed it in DFHack's `internal/quickfort/dig.lua` at tag 53.16-r1.1: `do_run_impl` skips any tile whose `occupancy.building ~= 0` before any stat increments, so quickfort returns success anyway. The tool's promise to never designate one half without the other is false in practice.

Read the research doc's recommendation section first. Digging stays the primitive; this is a correctness fix, not a redesign.

## Goal

In `scripts/dfhack/df-overseer-diggable.lua`:
1. **Rank out occupied candidates.** `ranked_stair_candidates` excludes any candidate whose upper tile has a building on it (`occupancy.building ~= 0`). Check the lower tile too if it's cheap.
2. **Judge success by tiles designated.** Use the `quickfort_stats` counts for each half, not the ok flag.
3. **Read back inside the tool.** After a real designation, `dig_stair_down` reads both tiles' designations back.
4. **Never leave one half.** Designate the upper half first. If it didn't take, don't designate the lower. If the lower then fails, undo the upper, and say so in the result.
5. **Fail as an error.** A failure returns an error the MCP server surfaces as `isError`, using the same `nil, message` convention the other tools use, not an ok-looking result.

In `scripts/dfhack/df-overseer-farm.lua`: when `set_farm_crop`'s real write doesn't stick, return an error the same way instead of `write_ok: false` inside a normal result. A caller skimming the result could miss that flag.

Update the `TOOLS.yaml` notes for `dig-stair`, `find-stair` and `set-crop` to match, and cite the research doc. Design commitment #1 still holds: no coordinates leave the script.

## Verification without mutating the fort

- **Read-only checks and dry runs against the live fort only.** Confirm `find-stair "Farm Plot"` no longer ranks the Stockpile tile first. Read that tile's occupancy to show why. Confirm a dry run of `dig-stair` picks a clear tile.
- **No real designation, and don't touch the orphan z167 designation.** Removing it is a later, separately approved step.
- **Leave the fort paused.** Check `dfhack.world.ReadPauseState()` before and after. It should be paused at tick 227160.
- **Test from a uniquely named copy.** Use the `dfhack.internal.addScriptPath` method in `docs/TRAPS.md` (2026-09-17). Never replace the deployed script, and delete the copy afterwards.

## Constraints

- **Branch:** your worktree may start from the last pushed commit. Confirm this handoff's commit is in your history. If it isn't, run `git merge --ff-only main`, and stop and report if that fails.
- **Test suites** on `main`: ambient `python -m pytest` gives **306 passed, 1 skipped**, and `.venv-dfmcp` `dfmcp/tests` gives **165**. `.venv-dfmcp` won't exist in your worktree, so say which interpreter you used.
- **Traps:**
  - `dfhack-run lua -e` does nothing; use a file.
  - Strip ANSI prefixes from output.
  - `getCurFocus()` returns a table.
  - MCP arguments are strings.
  - Never set globals.
  - Check every `pcall` result.
- **VM access:** use the `.env` keys `DF_VM_IP` (strip any `/24`) and `DF_SSH_KEY`, user `df`, read with `grep -E '^KEY=' .env` only. No hostnames, addresses or tokens in anything you write.
- **If a harness or classifier refuses you, stop and report it.** Don't reword the command to get past it.
- **Don't edit** `Working.md`, `decisions/`, `memory/`, `CLAUDE.md`, `ROADMAP.md`, `docs/TRAPS.md`, `research/` or `doctrine/`.
- **Don't deploy.**

## Touched surfaces

`scripts/dfhack/df-overseer-diggable.lua`, `scripts/dfhack/df-overseer-farm.lua`, `scripts/dfhack/TOOLS.yaml`, tests only if a test covers these tools, and this doc (a Result section).

## Report

- What you changed.
- The live read-only evidence, with commands.
- What only a real designation or write can prove, as a short test plan.
- New traps.
- Suite counts and the interpreter you used.
- Your branch and commit hashes.
