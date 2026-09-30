# Handoff: stockpile writing (place, configure, link)

Date: 2026-10-01. **Executor, Sonnet, worktree. Offline code only, no live
access** (the orchestrator live-verifies after merge).

## Why

The minimal starting point (register 2026-10-01): the agents run the fort one
game year hands-off. Today they can only read stockpiles
(`scripts/dfhack/df-overseer-stockpile.lua`: `list`, `links`). Without
writing, food spoils, hauling stalls and refuse piles up. Principle (register
2026-09-30): set intent, let the game execute; a stockpile's settings and
links are exactly the native lever DF gives a player.

## Tasks, in order (commit after each)

1. **Mechanism, from DFHack `53.16-r1` source** (GitHub `DFHack/dfhack`:
   quickfort `#place` mode and its stockpile settings syntax,
   `plugins/stockpiles` and its Lua API, `library/modules/Buildings.cpp` for
   links). Answer with file and line: how a script places a stockpile of a
   given size; how its accepted categories (and finer settings) are set;
   whether presets exist and what they cover; how give/take links to a
   workshop or another stockpile are written. Say "unverified" where source
   does not settle it.
2. **`stockpile.place`**: KIND-free and generalisable: size W H, level,
   `NEAR_LANDMARK`, rank and radius like every other finder (reuse
   `df-overseer-openarea.lua`'s finder rather than a new one; skip reserved
   ground via `df-overseer-reservations.lua`'s `filter_reserved`), the
   categories to accept as an argument, `DRY_RUN` default true, `RES_ID` and
   `OVERRIDE` exactly as the other designating tools take them.
3. **`stockpile.configure ID CATEGORIES`**: change what an existing pile
   accepts. **`stockpile.link ID TARGET_ID give|take`** and **`unlink`**: to
   a workshop or pile, by id. Both `DRY_RUN` default true.
4. Reports state what the game now holds (read back), not what was asked.
5. `TOOLS.yaml` entries (mutating commands tagged as the others are), and
   tests in the existing lupa style. Note plainly what the stub cannot prove
   (the offline fake world has disagreed with the real API twice).

## Rules

- First step: `git merge --ff-only main`. Commit your plan early, then after
  each task; agents here get cancelled mid-run.
- Do not write `Working.md`, `decisions/DECISIONS.md`, `memory/`, or any
  `agents/*/tools.yaml` (the orchestrator grants roles after merge; say in
  the Result which role should get which command).
- No em dashes in prose. No attribution lines in any commit.
- Generalisable, no armok capabilities, never a rendered map (`CLAUDE.md`).
- Tests: ambient `python -m pytest`, and `dfmcp/tests` with the main
  checkout's `.venv-dfmcp`; report both counts.
- Stop and report on any permission refusal.

## Touched surfaces

`scripts/dfhack/df-overseer-stockpile.lua`, `scripts/dfhack/TOOLS.yaml`,
tests and lua stubs. Read-only use of openarea and reservations.

## Result

Mechanism documented in the .lua file's own header, sourced from DFHack
53.16-r1 (dfhack.git) with `scripts` pinned to DFHack/scripts.git commit
7549711a993e03bef19e90b27427096c1099853e: `#place` sizes a pile from its
own cell grid (1..31 per axis, place.lua:4-10); a cell's letters
(place.lua:78-97) pick categories, several letters combine into one
custom pile (place.lua:109-164); `configure_stockpile` (place.lua:256-268)
enables/disables a whole category via `plugins.stockpiles.import_settings`
against a `cat_<name>.dfstock` library preset (all 17 confirmed present),
whose real ENABLE/DISABLE semantics live in
`StockpileSerializer::read_category`
(plugins/stockpiles/StockpileSerializer.cpp:901-929); give/take links
(place.lua:372-415) write the same four vectors the existing `links`
command already reads. One real naming trap found and documented:
"sheet" (this file's own accept-category name) vs "sheets" (the preset
and place.lua's own spelling).

Built: `place`, `configure`, `link`, `unlink` in
`scripts/dfhack/df-overseer-stockpile.lua`, all DRY_RUN-true by default,
reusing openarea's `is_free` finder and reservations'
`filter_reserved`/`check_tiles` for `place`. Reports read back the real
building state, never an echo of the request. TOOLS.yaml entries added
(`live_deployed: false`, `verified: unverified`). Tests:
`tests/test_stockpile_writing_lua_logic.py` (14 new, against
`tests/lua_stubs/dfhack_stockpile_world.lua` plus the REAL
reservations.lua) — states plainly the fake quickfort run does not
exercise the real quickfort_building pipeline (tile-shape validity,
extent grouping, container defaults) or the real plugin's subtype
behaviour.

Test counts (this stream): ambient `python -m pytest` 2142 passed, 3
skipped (lupa on PYTHONPATH). `dfmcp/tests` under the main checkout's
`.venv-dfmcp`: 722 passed.

Role: checked agents/*/tools.yaml -- `stockpile.list`/`stockpile.links`
(read) are already granted to overseer, architect AND quartermaster;
`zone.place` (the closest mutating precedent) is granted to overseer
and architect only, not quartermaster. Recommend: `place` (siting a
new pile) alongside overseer/architect's existing `zone.place`/
`workshop.build`; `configure`/`link`/`unlink` (routine stockpile
management, no siting) to quartermaster, which already reads
`stockpile.list`/`links` and is this project's production-lever role
(register 2026-09-30, the quartermaster-levers research just
dispatched per git log). Final grant is the orchestrator's call.

Only a live run settles: whether `is_free`'s coarser check (vs
place.lua's own `is_valid_stockpile_tile`) ever actually produces a
short pile on Uniboslan's real terrain; whether `configure`'s
enable/disable round-trips correctly against a real building's
`settings.flags`; and the real shape of `give_to_pile` etc. on a live
stockpile/workshop pair.
