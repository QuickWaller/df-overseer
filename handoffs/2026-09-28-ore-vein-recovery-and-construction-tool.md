# Handoff: recover an ore vein smoothed into a room wall, and build the missing "construct" tool this needs

Date: 2026-09-28. **Executor, Sonnet, worktree-isolated. Code and tests only. NO deploy, no VM, no live game call.**

## Context

`decisions/DECISIONS.md` 2026-09-24 ("Ore veins in a room's walls were smoothed
instead of mined and replaced with a constructed wall") recorded a real gap:
this fort's room pipeline smooths a wall's ore/gem veins in place instead of
mining them out and replacing the hole with a constructed wall, because (a)
`df-overseer-blueprint.lua` classifies by quickfort's smoothable set, which
allows mineral, so an ore vein reads as an ordinary smoothable wall, and
(b) `surface.material` only reports a class (STONE/MINERAL), never which
mineral, so no tool can currently tell ore from ordinary stone. The user
deferred it 2026-09-24 ("note it for later"); today (2026-09-28) the user
asked to do it.

**Live-confirmed today** (read-only, orchestrator, on VM 103): the Manager's
Office (zone 13) has exactly 5 ring tiles reading `MINERAL` class, matching
the register's count. The register says these are hematite, an ore, still
present under the smoothing (smoothing does not destroy the vein) and
"recoverable now": mine it out, then build a constructed wall in its place
(wall after dig, never before -- a wall-shaped tile cannot take a
construction, `research/2026-09-24-quickfort-hands.md`). **No tool in this
codebase can build a construction (wall/floor/etc.) at all** -- that half is
missing entirely, not just buggy.

## What to build (two pieces, both generalisable per `CLAUDE.md`'s rule: take
the kind as an argument, read per-kind detail from the game's own data, no
per-instance branching, and per this repo's hard commitment never take raw
map coordinates from a caller -- everything is zone/landmark-anchored)

1. **Identify which of a zone's own ring/footprint tiles are ore or gem, not
   just "MINERAL class."** Research the real, live DFHack API for decoding a
   *map tile's* specific mineral/vein material (not an item's -- this is
   different code from `dfhack.matinfo.decode(item)` used in
   `df-overseer-building.lua`'s material-choice fix from earlier today; a map
   tile's vein material comes through the block's geology, e.g.
   `dfhack.maps.getTileBlock`, `block.designation[x%16][y%16]`, the region's
   geo-layer/vein data, or `dfhack.maps.getGeoBiome` -- read DFHack's own
   source, do not guess the field path; an earlier orchestrator attempt at
   this crashed on a wrong field name and was abandoned rather than shipped).
   Once you have the real mineral id, use the same "is this economic"
   determination the material-choice fix already established today
   (`dfhack.matinfo.decode(...).inorganic.economic_uses`) to classify ore/gem
   vs ordinary stone. Extend `df-overseer-surface.lua`'s existing
   `ring_tiles`/`footprint_tiles`/`tile_read` machinery (read it first --
   don't duplicate it) with a new read, e.g. `surface vein-material ZONE_ID`,
   reporting per-ring-tile: material class, decoded mineral name (or
   `unknown`, never guessed), and whether it's economic (ore/gem).
2. **A new tool to mine identified ore/gem tiles and, once open, construct a
   wall in their place.** Two actions, one new script (e.g.
   `df-overseer-construction.lua`), zone-anchored like everything else here
   (a `ZONE_ID`, never a raw coordinate):
   - `mine-vein ZONE_ID [DRY_RUN]`: designate for digging every ring tile of
     the given zone that step 1 identifies as ore/gem. Report what it found,
     what it designated, and refuse (report why) any tile it can't classify
     confidently rather than guessing.
   - `build ZONE_ID KIND [DRY_RUN]`: for the same zone's ring tiles, wherever
     one is now open ground (not a wall -- read this live, don't assume the
     mine step already ran), designate a construction of KIND (generalised:
     Wall today, but take the kind as data the same way `building.build`
     does, not hardcoded to Wall). Read `research/2026-09-24-quickfort-hands.md`
     for the exact ordering/material rules a constructed wall needs. Refuse
     clearly (never silently skip) any tile that is still a wall (hasn't
     been mined yet) rather than guessing it's fine.
   Use whatever material-choice logic already exists (today's
   `building.build` non-economic-default fix) for what a construction should
   build from, rather than inventing a second material policy.

## Apply it

Once both pieces exist and pass offline tests, produce (but do not run) the
exact two live commands the orchestrator should run against zone 13 to
recover its 5 hematite tiles: dry-run first, then real. Do not call the live
fort yourself.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Touched surfaces: `scripts/dfhack/df-overseer-surface.lua`, a new
  `scripts/dfhack/df-overseer-construction.lua`, `TOOLS.yaml`, `dfmcp/`
  registration if a new script needs one, and their tests. Do NOT touch
  `Working.md`, `decisions/`, `memory/`, `handoffs/INDEX.md`.
- **Offline `lupa` tests are necessary but not sufficient** -- 2026-09-28's
  register/`Working.md` documents a real live crash (`kind_previously_built`'s
  vector-indexing bug) that 14 passing offline tests never caught, because
  the fake DFHack world doesn't faithfully model the real API's edge cases.
  Write the offline tests, but flag in your Result section exactly which
  parts are unverified against the real game (the tile-material decode API
  above is the single highest-risk unknown here) so the orchestrator
  live-tests those specifically and cautiously before trusting them, the same
  way today's building-tool bug was caught before it touched the fort.
- `python -m pytest` with `lupa` on PYTHONPATH (`CLAUDE.md`'s traps section)
  and `dfmcp/tests` in `.venv-dfmcp`; report counts before and after.
- No em dashes in prose. **No attribution lines in commit messages.**
- Commit after each piece. Do not push. Stop and report on any permission
  refusal.
- Fill in the Result section: what you built, the real API you found (or
  couldn't confirm) for tile-level mineral decoding, test counts, and the
  exact two commands for the orchestrator to run live on zone 13.

## Result

**Built, both pieces, code and tests only, no live call.**

1. `surface.vein-material` (`scripts/dfhack/df-overseer-surface.lua`): per
   boundary-ring tile, the decoded mineral name and whether it is economic
   (ore/gem), via `dfhack.maps.getTileBlock(x,y,z).block_events`, matched
   against `df.block_square_event_mineralst:is_instance`, its
   `tile_bitmask:get(x%16, y%16)`, its `inorganic_mat` index into
   `df.global.world.raws.inorganics`, and that raw's `.material.economic_uses`
   (non-empty = economic, the same rule `df-overseer-building.lua`'s
   2026-09-28 material-choice fix already established for an item's
   material). Three-plus-state `vein_status`: not_mineral / ore_or_gem /
   not_economic / hidden / unreadable / unknown -- unknown covers a
   MINERAL/FEATURE tile whose vein event could not be matched or decoded,
   never a guessed name (mirrors the earlier orchestrator crash this handoff
   references: every hop here is `pcall`-guarded so the same class of
   mistake degrades to `unknown`, not a crash).
2. `df-overseer-construction.lua` (new file): `mine-vein ZONE_ID [DRY_RUN]`
   designates a real dig on every ring tile `vein-material` confidently
   calls ore/gem and that is still shaped WALL (refusing, by name, any tile
   it cannot classify confidently); `build ZONE_ID KIND [DRY_RUN]` resolves
   KIND generically through `df-overseer-building.lua`'s own exported
   `list_kinds` (Wall today, any construction subtype at no new-code cost)
   and designates it on every ring tile that reads open ground right now,
   refusing a still-WALL tile ("not yet mined") rather than assuming
   mine-vein already ran. Each identified tile gets its own single-cell
   `#dig`/`#build` blueprint applied via `quickfort run -c x,y,z` -- the
   same already-verified one-tile-at-a-time shape
   `df-overseer-diggable.lua`'s dig-stair and `df-overseer-building.lua`'s
   build_kind already use, chosen over an untested sparse/blank-cell
   blueprint. `build`'s `material_report` reuses building.lua's
   default-non-economic policy as pure advisory reporting (duplicated, not
   invented fresh) since quickfort itself has no parameter to force a
   material choice from outside -- true of building.lua's own build_kind
   too.
3. **Reuse without breaking the blueprint shim.** The first cut promoted
   `find_zone`/`ring_tiles`/`tile_read` from `local` to global in
   `surface.lua` so `construction.lua` could call them directly. That broke
   `tests/test_blueprint_tool_manifest.py::test_shim_contract_holds_in_the_
   surface_layer`: `df-overseer-blueprint.lua`'s rectangle-anchored site
   shim depends on `find_zone` staying a real Lua upvalue of
   `enclosure`/`finish`/`boundary_material` so it can swap it with
   `debug.setupvalue` and restore it. Fixed by keeping everything `local`
   in `surface.lua` and having `construction.lua` extract
   `find_zone`/`ring_tiles`/`decode_vein_tile` (and, one hop further,
   `tile_read`) via `debug.getupvalue` against the one exported function
   that closes over them (`vein_material`) -- the same idiom
   `df-overseer-building.lua` already uses to reach quickfort's own local
   table. Read-only extraction, no swap-and-restore risk.

**The real DFHack API for tile-level mineral decoding -- HIGHEST-RISK
UNVERIFIED PIECE, exactly as flagged.** This stream had no VM/DFHack process
to read source against (unlike research/2026-09-24-quickfort-hands.md,
which read the installed `hack/scripts/internal/quickfort/*.lua` directly
over SSH). The chain implemented -- `dfhack.maps.getTileBlock` ->
`block.block_events` -> `df.block_square_event_mineralst:is_instance` ->
`.tile_bitmask:get(x%16,y%16)` -> `.inorganic_mat` ->
`df.global.world.raws.inorganics[idx]` -> `.id`/`.material.economic_uses`
-- is DFHack's well-known, long-stable vein mechanism from general
knowledge, not a source read this session performed. It has been proven
only against a fake world (`tests/test_surface_vein_material_lua_logic.py`);
it has never touched a real DFHack process. Every hop is `pcall`-guarded so
a wrong field name degrades to `vein_status: "unknown"` with `error` set,
never a crash and never a fabricated mineral name -- but "degrades safely"
is not "correct", and this must be checked against zone 13's real 5
hematite tiles before anything downstream trusts it.

**Test counts** (`python -m pytest`, `lupa` installed to a scratch
`--target` dir and put on `PYTHONPATH`, per `CLAUDE.md`'s traps section;
`dfmcp/tests` already included in the top-level count on this repo layout):
**before, 1910 passed, 3 skipped** (measured at this handoff's own commit,
`8f019a5`, before any of this stream's edits); **after, 1930 passed, 3
skipped** -- the 20 new tests are
`tests/test_surface_vein_material_lua_logic.py` (11) and
`tests/test_construction_lua_logic.py` (9), both against fake worlds in
`tests/lua_stubs/`. `tests/test_surface_tool_manifest.py` and
`tests/test_blueprint_tool_manifest.py` (the shim-contract guard above)
both still pass.

**Exact two commands for the orchestrator to run live on zone 13** (dry run
first, then real; both need their own go-ahead per this repo's mutation
rules -- not run by this stream):

```
./dfhack-run df-overseer-surface vein-material 13
```
(read-only sanity check first: confirm the 5 known hematite tiles actually
come back `vein_status: "ore_or_gem"`, `mineral_name: "HEMATITE"` -- if this
reads `unknown` instead, the API chain above is wrong and nothing past this
point should be trusted.)

```
./dfhack-run df-overseer-construction mine-vein 13 true
```
then, only if that dry run's `ore_tiles_found` is 5 and every result's `ok`
is true:
```
./dfhack-run df-overseer-construction mine-vein 13 false
```
and once the dig jobs have actually completed (re-check with
`surface.finish`/a direct tile read, not just quickfort's own stats -- see
`research/2026-09-24-quickfort-hands.md`'s "a dig flag is not a job"
finding):
```
./dfhack-run df-overseer-construction build 13 Wall true
```
then, if `open_tiles_found` matches and every result's `ok` is true:
```
./dfhack-run df-overseer-construction build 13 Wall false
```
