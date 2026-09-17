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

---

## Result (executor, 2026-09-17)

**Status: done.** All four `dig-stair` fixes and the `set_farm_crop` error-
convention fix landed, live-verified read-only against VM 103 (Uniboslan,
paused throughout), no real designation, no deploy, orphan z167 upstair
untouched. `c43fe4f` was missing from this worktree's initial history (only
`d2238f2`); `git merge --ff-only main` fast-forwarded cleanly to it before
any edits.

**1. What changed** (`scripts/dfhack/df-overseer-diggable.lua`):

- `tile_unoccupied(x,y,z)` and `read_dig_designation(x,y,z)` (new helpers,
  same `getTileFlags` returns `designation, occupancy` pattern already used
  in `df-overseer-farm.lua`/`well.lua`) plus `dig_designation_name(v)` for
  a defensive reverse-enum lookup used only in diagnostic text.
- `ranked_stair_candidates`: a candidate is now rejected unless
  `tile_unoccupied` is true on both the upper tile (the actual live bug --
  quickfort's `#dig` mode silently skips a tile with any building on it,
  still reports `CR_OK`) and, defensively, the lower tile (structurally
  near-impossible per the research doc, checked anyway per the handoff's
  own "if it's cheap"). Each result now reports `tiles_unoccupied: true`,
  matching the existing `borders_walkable_network: true` convention (both
  are selection preconditions, not filters a caller can see fail).
- `dig_stair_down`'s real-mutation path is now sequential and judged by
  read-back, not `*_ok`: designate the upper half, read `flags.dig` back
  directly, and only proceed to the lower half if that read confirms a
  real stair designation (not `df.tile_dig_designation.No`). If the upper
  half didn't take, return `nil, message` immediately -- upstair is never
  attempted, matching "never leave one half" in the direction the live bug
  actually happened. If the upper half took but the lower half doesn't,
  run `quickfort undo` on the **downstair** blueprint at the upper tile
  (quickfort's own documented inverse: "dig tiles are undesignated"),
  read the tile back again to confirm the undo itself actually took, and
  return `nil, message` either way, noting in the message whether the
  rollback was confirmed.
  Every failure path returns `nil, message`, the same convention every
  other tool in this file already uses -- `dfmcp/server.py`'s exact-shape
  `{"error": "<message>"}` rule (confirmed by reading `server.py` lines
  ~509-539 this session) is what turns that into `isError=True` for a real
  MCP client, no server-side change needed.
- One thing I got wrong on the first pass and fixed before committing:
  my first draft of the rollback-failure message embedded the real
  `c.x,c.y,upper_z` coordinate in the returned error string -- a direct
  violation of design commitment #1 ("real coordinates never leave this
  file"), copied from habit out of the live-test handoff's own read-back
  language rather than checked against the rule. Caught on review, not by
  a test; fixed to say "the rank N candidate's upper tile" instead, no
  coordinate. Flagging this in case it's worth a doctrine/lint check later
  (nothing currently greps returned strings for coordinate-shaped
  patterns).

`scripts/dfhack/df-overseer-farm.lua`: `set_farm_crop`'s real-write branch
now returns `nil, "write did not stick..."` instead of a normal-looking
result with `write_ok=false` inside it, matching the same convention. The
success shape (`write_ok=true`, `read_back_plant_index`) is unchanged.

`scripts/dfhack/TOOLS.yaml`: `find-stair`, `dig-stair`, `set-crop` entries
updated citing `research/2026-09-17-stairs.md`. Also caught and corrected
a stale claim while I was in that file: `set-crop`'s `verified` line said
the real write was "UNTESTED live", but
`handoffs/2026-09-17-farm-stair-live-test.md` Result section 3 already
proved it (BUSH_QUARRY written to plot 4, read back, restored) -- flagging
per CLAUDE.md's "if docs and repo state disagree" rule rather than quietly
patching it; the corrected line says so and cites the live-test handoff.

**2. Live read-only evidence** (VM 103, Uniboslan; fort read `paused=true,
year=30, tick=227160` before I touched anything and again after -- verified
unchanged with `dfhack.world.ReadPauseState()`/`ReadCurrentYear()`/
`ReadCurrentTick()`, matching the handoff's own expected pre-state exactly).
Tested from uniquely named copies (`df-overseer-diggable-dsftest0917.lua`,
`df-overseer-farm-dsftest0917.lua`) via `dfhack.internal.addScriptPath`
on a `/tmp` directory, per `docs/TRAPS.md` (2026-09-17) -- the deployed
scripts were never touched (`md5sum` on
`/opt/df/game/hack/scripts/df-overseer-diggable.lua` matched before and
after: `7f5f62013cb8ec394ca16fe5798f9ff9`), and the test directory and
loader scripts were deleted, `removeScriptPath`'d, and confirmed gone
(re-running the test command after cleanup returned "not a recognized
command").

- `./dfhack-run df-overseer-diggable find-stair -1 "Embark Site" 30` (OLD,
  still-deployed, unfixed script): rank 1 is `distance_tiles:0,
  direction:"S"` -- the exact candidate the live test found sitting on
  this fort's own Stockpile.
- `./dfhack-run df-overseer-diggable-dsftest0917 find-stair -1 "Embark Site" 30`
  (NEW, fixed copy): rank 1 is now `distance_tiles:1, direction:"NW"`, with
  every one of the 5 results carrying `tiles_unoccupied:true` and none at
  distance 0 -- the occupied tile is gone from the list entirely, not just
  reordered.
- Direct read at the old rank-1 tile confirmed why: a throwaway Lua script
  read `occupancy.building == 2` there via `dfhack.maps.getTileFlags`,
  matching the live test's own finding (Building id=1, type=Stockpile).
- `./dfhack-run df-overseer-diggable-dsftest0917 dig-stair -1 "Embark Site" 1 30 true`
  (dry run): picked the same new rank-1 candidate (`distance_tiles:1,
  direction:"NW"`), returned `would_run_downstair_blueprint`/
  `would_run_upstair_blueprint` only, no quickfort call, no mutation.
- `./dfhack-run df-overseer-farm-dsftest0917 list`: plot 4 unchanged,
  `exists:true`, all four seasons `MUSHROOM_HELMET_PLUMP` -- matches the
  live-test handoff's own final state, confirming nothing about this
  session touched it.
- `./dfhack-run df-overseer-farm-dsftest0917 set-crop 4 spring BUSH_QUARRY true`
  (dry run): unchanged shape, `would_set_plant_index:177`, no write.
- `./dfhack-run df-overseer-farm-dsftest0917 set-crop 999 spring BUSH_QUARRY true`:
  confirmed the `nil, message` -> `{"error": "no farm plot with id 999..."}`
  shape still prints correctly (this refusal path's code was untouched by
  either fix, exercised here only to confirm the file still loads and
  runs cleanly under the new command name).
- Orphan check: read `flags.dig` directly at the two tiles the live test
  left behind -- lower tile still `6` (`UpStair`), upper tile still `0`
  (`No`) -- exactly the live test's own end state, untouched by anything
  in this session. This also cross-checked `dig_designation_name`'s
  reverse-enum lookup against real values (`6` -> `"UpStair"`, `0` ->
  `"No"`), the same API call shape the new code uses.

**3. What only a real designation or write can prove** (none of this ran
this session; real mutation was forbidden):

- A real `dig-stair` call at the new rank-1 candidate (`dry_run=false`),
  confirming both halves designate for real this time (`downstair_designated`
  and `upstair_designated` both true, read back via `flags.dig`), and that
  the pair actually becomes a real dig job once a miner paths to it
  (`dfhack.job.checkDesignationsNow()` is quickfort's own concern, not
  re-verified here).
- The rollback branch: deliberately engineering a lower-half failure (e.g.
  a manufactured building/obstruction at the lower tile, or a rank pointed
  at a candidate whose lower tile becomes newly occupied between the two
  calls -- hard to arrange naturally since `is_diggable`+`tile_unoccupied`
  already filter for exactly this at selection time) to confirm
  `quickfort undo` actually clears the upper half's designation and that
  the read-back after the undo call reports `No` for real, not just that
  the undo call returned `CR_OK`.
- `set_farm_crop`'s new `nil, message` failure path on the real-write
  branch specifically (as opposed to the refusal branches, which are
  read-only and were exercised this session) -- would need a write timed
  to fail, e.g. the plot destroyed between validation and the struct
  write, not something this session could safely arrange.
- Whether the fixed `dig-stair` actually stops leaving orphans across a
  realistic sequence of calls (e.g. two calls in a row where the first
  candidate becomes occupied by the time the second is attempted).

**4. New traps** -- none added to `docs/TRAPS.md` (out of scope, per
constraints); noting here for whoever next touches this file: none found
this session beyond what `docs/TRAPS.md` (2026-09-17 section) and the
research doc already record. The `getTileFlags` returns
`(designation, occupancy)` -- not `(flags, occupancy)` as its parameter
name in this file's existing code (`local ok, flags, occupancy = ...`)
implies -- is worth knowing but is not new; it's the same struct the file
already reads `.hidden`/`.flow_size`/`.dig` off of, confirmed again this
session, not contradicted.

**5. Suite counts:** `python -m pytest -q` (system `python`, 3.12.4):
**306 passed, 1 skipped** -- identical to the baseline CLAUDE.md states,
expected since every change this stream made is Lua-only. Also ran
`dfmcp/tests/{test_registry,test_roles,test_tools}.py` alone (the three
files that reference `TOOLS.yaml`) after the YAML edit: **81 passed**.
`.venv-dfmcp` does not exist in this worktree, as the handoff predicted;
not run. `scripts/dfhack/TOOLS.yaml` was also parsed directly with
`yaml.safe_load` to confirm it's still well-formed after the edits.

**6. Branch and commits:** worktree branch `worktree-agent-a1bbe96feb08aa105`,
fast-forwarded onto `main` at `c43fe4f` (was missing beforehand, only
`d2238f2`), then two commits on top: `26d6e22` "Fix dig-stair: rank out
occupied candidates, verify by read-back, never leave one half" (the three
touched code/config files) and a second commit adding this Result section
to this doc.

No refusal encountered from any harness or classifier this session.
