# Handoff: reserve tiles for specific planned rooms

Date: 2026-09-30. **Executor, Sonnet, worktree.**

## Context

User's call, 2026-09-30: agents need a way to hold ground for a planned
room so other work cannot take it (a workshop landing where the bedrooms
were meant to go, a corridor dug through a planned farm). **Scope is
specific planned rooms only.** Broad districts ("this region is
residential") are explicitly out: they belong to the owed Opus + user
zoning design session (`Working.md`, memory `zoning-design-session-owed`).

Nothing does this today. `df-overseer-blueprint.lua`'s `site-N` handles
exist only after a real dig has been designated, so they record work
started, not ground held. The game's own zones claim tiles only for things
already built.

Read first: `research/2026-09-28-job-dependency-graph.md` (the guard
model; a reservation check is one more guard in its closed vocabulary),
`scripts/dfhack/df-overseer-blueprint.lua` (site handles, footprint and
orientation resolution, `dfhack.persistent.getSiteData`/`saveSiteData` at
about line 398), and `scripts/dfhack/df-overseer-construction.lua`'s
`apply_keeps_access_guard`/`held` bucket (the pattern for a named hold).

## Design decisions already made (do not reopen)

1. **Storage is DFHack per-site persistent state**, the same mechanism
   blueprint site handles use, not dfqueue. dfqueue filters coordinates
   out on purpose and the Lua tools cannot read its SQLite; the tile set
   must live where the checking tools run. Agents only ever see a handle
   (`res-N`), a purpose string, footprint size and nearest landmark with
   direction and distance. **Never a tile position**, in any output.
2. **A reservation is a planned room's footprint**, resolved exactly the
   way `blueprint preview`/`apply` resolve a template at a site (template,
   landmark or handle, level, rank, radius, orientation with the access
   gate). Reuse blueprint.lua's resolution code; do not write a second
   footprint resolver. Adding `reserve`, `reservations` and `unreserve`
   verbs to `df-overseer-blueprint.lua` is the expected shape; a small
   shared module holding the store and the check (for example
   `df-overseer-reservations.lua`) is fine if other scripts need to
   `reqscript` it.
3. **One shared check, every designating tool.** Any tool that designates
   dig, builds, places a zone or stockpile, or applies a blueprint on map
   tiles refuses (or holds, where the tool already has a `held` bucket)
   any tile inside a reservation it does not hold. The refusal names the
   handle, its purpose and nearest landmark, never the tiles. Enumerate
   every `effect: mutate` command in `scripts/dfhack/TOOLS.yaml` and
   report in your Result which ones you wired and which you exempted and
   why (labor, orders, clock, nobles and the like are not map
   designation and are exempt).
4. **Holding a reservation.** `blueprint apply` of the same template on a
   reserved site is the holder: it proceeds, and the issued `site-N`
   handle records the `res-N` it came from. Other tools can pass an
   explicit reservation handle argument only if that is cheap to add;
   otherwise they simply refuse, and say so in your Result.
5. **Overlap rule (revised by the user, 2026-09-30, mid-stream).** Original
   text: "No overlaps. `reserve` refuses a footprint that overlaps another
   reservation or an existing blueprint site, naming the conflict." **Revised
   rule, now implemented:** adjacent planned rooms must be able to share a
   wall (templates already declare seam edges so tiled copies share walls
   instead of doubling them). Two reservations may overlap only on boundary
   tiles that **both** footprints mark as wall (a tile some `#dig` section
   marks with the smooth symbol, never a carve cell and never a tile no
   `#dig` section mentions at all -- unclassified is always treated the
   strict way, never assumed compatible). Any overlap touching an interior,
   carve, or unclassified tile of either footprint is refused, naming the
   conflict. A shared wall tile is held jointly: either holder's own
   blueprint apply may build or designate it, and unreserving one holder
   leaves the tile held by the other -- this falls out of `check_tiles`/
   `find_conflicts` re-scanning the live table on every call, with no
   separate joint-ownership record. The same rule applies to a reservation
   versus an existing blueprint site.
6. **Lifecycle:** reserved, then in use (a site was issued from it), then
   released by explicit `unreserve`. No automatic expiry. `reservations`
   reports each one's age in ticks and whether any work has started, so a
   stale plan is visible and the overseer decides.
7. **Hidden tiles** may fall inside a reservation. Nothing about their
   contents is ever reported or counted (no-armok rule).
8. **Roles:** `reserve`/`unreserve` real runs are overseer only (the
   roster's sole writer), dry runs and `reservations` also for the
   architect, matching how `blueprint apply` is granted. Wire them through
   `TOOLS.yaml`, the registry and `agents/*/tools.yaml` the same way the
   existing blueprint verbs are, and update any tool-count tests that pin
   role totals.
9. `DRY_RUN` defaults to true on `reserve` and `unreserve`.

## Out of scope

- Districts or regions, auto-sizing, choosing where rooms go.
- dfqueue schema changes (a project step may later name a `res-N`; not now).
- Any deploy to VM 103 or live mutation. Read-only live checks are
  welcome if credentials exist in your worktree; the orchestrator does the
  live verification after merge.

## Rules

- `git merge --ff-only main` first (main has unpushed commits your
  worktree needs, including the construction.lua guards).
- Offline `lupa` tests for: reserve then a conflicting build/dig refused
  with the handle named and no coordinate leaked; the holder's own
  `blueprint apply` allowed; overlap refused; unreserve frees the tiles;
  hidden tiles not reported. Model stubs on the real DFHack API shapes
  (the repo has twice shipped stubs that modelled the wrong field; say in
  your Result how you checked each stubbed API).
- Ambient `python -m pytest` (lupa on `PYTHONPATH`) and `dfmcp/tests` in
  `.venv-dfmcp` stay green; report both counts.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in this handoff's Result section: what was built, which tools were
  wired or exempted, test counts, anything unverified.

## Result

**Built.**

- `scripts/dfhack/df-overseer-reservations.lua` (new): a dependency-free
  ledger. Persistent state under `df-overseer-reservations_v1` (the same
  `dfhack.persistent.getSiteData`/`saveSiteData` mechanism
  `df-overseer-blueprint.lua`'s own site-N handles use, confirmed by reading
  that file's existing, already-live `load_state`/`save_state` pair rather
  than guessing the API shape). Exports: `create`, `get_raw`/`list_raw`
  (internal-only, coordinate-bearing, documented as such), `mark_in_use`,
  `remove` (returns the OTHER reservation handles still covering any of the
  freed footprint's tiles, so a shared wall's continued hold is visible),
  `find_conflicts` (the reserve-time overlap check, implementing the revised
  decision 5), `check_tiles` (the shared per-tile refusal every designating
  tool calls) and `rect_tiles` (one shared rectangle enumerator so no two
  files build the tile list slightly differently). No CLI section: it is a
  pure `reqscript` leaf, one-directional (`df-overseer-blueprint.lua`
  reqscripts it; it reqscripts only `df-overseer-landmarks.lua` for
  near-landmark/direction/distance reporting, and never reqscripts
  `df-overseer-blueprint.lua` back -- a two-way reqscript between them would
  make correctness depend on which file's top-level `reqscript` call runs
  first, so the shape from decision 2 ("a small shared module holding the
  store and the check") was implemented as blueprint.lua depending on this
  leaf, not the other way around).
- `df-overseer-blueprint.lua` gains `reserve TEMPLATE PURPOSE SITE [DRY_RUN]
  [LEVEL] [RANK] [RADIUS_TILES]`, `reservations`, `unreserve RES_ID
  [DRY_RUN]`. `reserve` resolves a footprint via a newly extracted
  `resolve_new_site` (the exact orientation-search-plus-access-gate logic
  `apply`'s own new-site path already used, pulled out verbatim so both
  paths share one implementation, per decision 2 -- the extraction was
  proven behavior-preserving by running the full existing
  `test_blueprint_lua_logic.py` suite before and after: all 39 pre-existing
  tests still pass unchanged), classifies the template's own `#dig` cells
  wall vs. carve (`classify_footprint_cells`, new), and checks the result
  against every existing reservation and every existing blueprint site
  (`all_sites_raw`, new, paired with a `classify_site_cells` helper that
  re-derives a carved site's own wall cells from its stored template name,
  defaulting to "no wall cells known" -- i.e. strict -- if that template can
  no longer be loaded). `apply`'s SITE argument now also accepts a `res-N`
  handle (`is_reservation_handle`): it uses the reservation's own stored
  footprint and orientation directly (skipping the landmark search), refuses
  if the reservation's stored template does not match, refuses if the
  reservation was already carved into a site, and on a real success calls
  `mark_in_use` and records `site.reservation` on the new site-N record.
  Every resolved site (whichever of the three paths produced it) is checked
  against `check_tiles` before the order guard runs, refusing with the
  conflicting handle/purpose/landmark and never a coordinate.
- Docs and manifest: `TOOLS.yaml` gets the three new commands under
  `df-overseer-blueprint.lua` (all `knowledge_scope: player_derivable`,
  `verified: unverified`, `live_deployed: false`); `dfmcp/tools.py` gets
  `blueprint.PURPOSE`/`blueprint.RES_ID` argument descriptions (`SITE`,
  `TEMPLATE`, `DRY_RUN` already had tool-scoped entries that cover `reserve`/
  `unreserve` too); `agents/overseer/tools.yaml` grants `blueprint.reserve`,
  `blueprint.reservations`, `blueprint.unreserve`; `agents/architect/
  tools.yaml` grants only `blueprint.reservations` (see "Deviation from
  decision 8" below).

**Tools wired to the shared reservation check** (decision 3), each call
inserted immediately before the tool's own `quickfort`/designation call so a
refusal never reaches it:
- `openarea.build` (`build_open_area`) -- full W x H rectangle.
- `diggable.dig` (`dig_diggable_area`) -- full W x H rectangle.
- `diggable.dig-stair` (`dig_stair_down`) -- both the upstair and downstair
  tile, checked together before either is designated (it always designates
  the pair or neither).
- `farm.build` (`build_farm_plot`) -- full W x H rectangle.
- `workshop.build` (`build_workshop`) -- full W x H rectangle.
- `well.build` (`build_well`) -- its single tile.
- `building.build` (`build_kind`) -- full `dw x dh` rectangle (the resolved
  dims, after `resolve_dims`); the temporary single-use blueprint file is
  removed on a refusal too, matching how every other refusal path in that
  function already cleans it up.
- `zone.place` (`place_zone`) -- the rectangle path (`dw x dh`) AND the
  water-body path (`place_water`, using the flood-filled component's own
  exact tile list, `c.tiles`, converted from its native `{x,y}` array pairs)
  -- both are `places a zone` per decision 3, and water bodies are not
  rectangular so they needed their own tile-list conversion rather than
  reusing `rect_tiles`.
- `landmarks.build` (`build_at_landmark`) -- **anchor-tile only**, not the
  full footprint: this tool takes no W/H at all and never parses the
  blueprint file to learn its footprint (see its own header on why: it is
  the "I already know the exact landmark" shortcut around `openarea.build`'s
  ranked-candidate search), so a full-footprint check is not cheap here the
  way it is everywhere else. Documented as a named limitation in the code,
  not silently skipped.
- `construction.mine-vein` (`mine_vein`) and `construction.build`
  (`build_construction`) -- wired as a THIRD guard (`apply_reservation_guard`,
  new) alongside the existing `item_present`/`keeps_access` guards, using
  the same `held`-bucket shape (a reservation conflict holds just that ring
  tile, not the whole call) rather than a hard refusal, since both tools
  already have that bucket and decision 3 explicitly allows "or holds, where
  the tool already has a held bucket." Run first (before item_present), on
  the reasoning that "you don't hold this ground at all" is a more
  fundamental gate than the other two guards' live-world checks, though the
  handoff did not mandate an order.

**Exempted, with reasons** (every remaining `effect: mutate` command in
`TOOLS.yaml`, enumerated from the full manifest scan, `grep -n "effect:
mutate"` then cross-referenced to its script/command):
- `landmarks.build` -- wired (see above; listed here only to be explicit
  that it is not exempt, it is partially wired).
- `farm.set-crop` (`set_farm_crop`) -- writes `building_farmplotst.
  plant_id[season]` on an ALREADY-BUILT farm plot; it never designates a map
  tile, so there is no footprint for a reservation to conflict with.
- `zone.assign-owner`/`zone.clear-owner` -- both only change an
  already-placed zone's owner link (`unit.relations.*`), never a map
  designation.
- `trees.fell` (`fell_trees`) -- tree felling is not one of decision 3's
  four enumerated categories (dig/build/place zone or stockpile/apply
  blueprint); it clears vegetation, it does not claim ground for a planned
  room. Not wired.
- `orders.create`/`orders.cancel`, `workjob.queue`/`workjob.cancel` --
  manager work orders and direct workshop jobs; explicitly named as exempt
  in the handoff itself ("labor, orders, clock, nobles and the like").
- `labor.set-labor` -- a labor flip, not a map designation.
- `ui.click`, `ui.embark-mode`, `ui.leave-embark-mode` -- UI-driven state
  changes (embark bootstrap and screen interaction), not map designation.
- `nobles.appoint`/`nobles.unappoint` -- position assignment, not a map
  tile.
- `clock.set-speed`/`clock.pause`/`clock.resume`/`clock.arm`/`clock.disarm`/
  `clock.clear` -- the in-game clock/tripwire, not map designation.
- `fort.quicksave` -- a save, not a designation, and ruled a test-harness-
  only power for the ARMOK-adjacent reload question elsewhere
  (`docs/ARMOK-RULINGS.md`); irrelevant to reservations either way.
- `ledger.record` -- writes the observation ledger, not the map.
- `blueprint.apply`/`blueprint.release` -- these ARE map-designation tools,
  but `apply` is not "exempt": it is the reservation mechanism's own HOLDER
  (decision 4), wired as described above, not a plain refuse-on-conflict
  tool. `release` only withdraws a STALLED site's own prior designations
  (quickfort `undo`); it never designates new tiles, so there is nothing new
  for it to check against a reservation -- if the underlying site was itself
  the reservation's own holder, releasing it does not touch the reservation
  record at all (that is what `unreserve` is for).
- `blueprint.reserve`/`blueprint.unreserve` themselves -- not applicable to
  themselves.

**Deviation from decision 8, flagged rather than silently made:** the
decision's literal text ("dry runs and `reservations` also for the
architect, matching how `blueprint apply` is granted") could not be
implemented as written. `dfmcp/roles.py` rule 2 refuses to load the roster
if ANY role other than the declared `sole_writer` is granted a tool tagged
`effect: mutate`, with no carve-out for "but it defaults to a dry run" --
confirmed by reading `roles.py` directly (not assumed), and it is the exact
same rule that already keeps the Architect from holding `blueprint.apply`
itself, even though `apply` also defaults to `DRY_RUN: true`
(`test_architect_gets_the_reads_and_never_apply` in
`tests/test_blueprint_tool_manifest.py` pins this for `apply`/`release`
already). So `blueprint.reserve`/`blueprint.unreserve` follow that exact
precedent: the Architect is granted `blueprint.reservations` (a `read`) and
never the two `mutate`-tagged verbs. Implementing an actual "dry-run-only"
grant would need a new mechanism in `dfmcp/roles.py` itself (a real, if
small, architectural change); out of scope here without the user's
go-ahead, and not attempted.

**How each stubbed API was checked** (per the handoff's own "the repo has
twice shipped stubs that modelled the wrong field" caution):
- `dfhack.persistent.getSiteData`/`saveSiteData`: read directly from
  `df-overseer-blueprint.lua`'s own already-live `load_state`/`save_state`
  (not re-derived or guessed) -- same two-argument shape, same "default on
  first read" behavior. Found and fixed a real bug in the EXISTING test
  stub while doing this: `tests/lua_stubs/dfhack_blueprint_world.lua`'s fake
  persistent store used one unkeyed slot (`dfhack.persistent._s`) shared by
  every `STATE_KEY`, which would have silently collided
  `df-overseer-blueprint_v1` and `df-overseer-reservations_v1` state the
  moment both files' persistent calls ran in the same test process. Fixed to
  a per-key table before writing any reservation test against it.
- `dfhack.world.ReadCurrentTick`: already used identically by
  `df-overseer-blueprint.lua`'s own `dig_progress`/`release_site`; reused
  the same `pcall(dfhack.world.ReadCurrentTick)` idiom, not a new guess.
- `reqscript`: DFHack's real `reqscript` hands back the loaded script's OWN
  per-script global environment table (so its unqualified `function foo()`
  definitions become `module.foo`), not the caller's globals. The existing
  test stubs for blueprint/construction did not need to reproduce this
  themselves because they only ever `reqscript` HAND-WRITTEN fake tables.
  This stream's tests, by contrast, load the REAL
  `df-overseer-reservations.lua` from inside `dfhack_blueprint_world.lua`
  and `dfhack_construction_world.lua`'s stubs (see below), which does need
  it -- replicated with `load(src, name, "t", setmetatable({}, {__index =
  _G}))`, confirmed working with a standalone lupa probe before relying on
  it in the actual test suite.

**Tests.**
- `tests/test_reservations_lua_logic.py` (new, 17 tests) against
  `tests/lua_stubs/dfhack_reservations_world.lua` (new, minimal): create/
  list/get_raw; `check_tiles` refusal naming the handle with no coordinate
  in the message; the holder passing through its own reservation; the
  revised decision 5 directly -- two rooms sharing a wall line accepted, an
  interior overlap refused, an unclassified tile never assumed compatible, a
  reservation-vs-supplied-site-footprint conflict; `remove`'s
  remaining-holders return and, explicitly, "a shared wall tile stays held
  after one holder unreserves." Writing this test caught a REAL bug before
  it shipped: the first `check_tiles` implementation returned a conflict on
  the first non-held covering reservation even when the SAME tile was ALSO
  covered by a reservation the caller does hold (exactly the shared-wall
  case) -- fixed to collect every covering reservation per tile before
  deciding, then the test passed.
- `tests/test_blueprint_lua_logic.py`: 8 new tests through the real
  `df-overseer-blueprint.lua` (now loading the real
  `df-overseer-reservations.lua` too, see above) -- reserve returns a
  handle/footprint/landmark and no coordinate anywhere in the result tree
  (checked recursively); reserve defaults to a dry run and reserves nothing;
  a plain `apply` is blocked by an unrelated reservation, naming it, with
  quickfort never called; `apply` with the `res-N` handle succeeds as
  holder, and `reservations` then shows it `in_use` with the new site
  handle; a different-template reservation is refused; `reserve` refuses
  overlap with an already-carved site; `unreserve` releases and
  `reservations` then lists none left; `unreserve` defaults to a dry run.
  All 39 pre-existing tests in this file still pass unchanged (the
  `resolve_new_site` extraction is behavior-preserving).
- `tests/test_construction_lua_logic.py`: 2 new tests -- `mine-vein` holds a
  reserved ring tile rather than refusing the whole call (the unreserved
  tile is still designated); `build` holds a reserved target before the
  item_present/keeps_access guards even run.
- `tests/test_blueprint_tool_manifest.py`: extended (`RESERVE_READ_ID`/
  `RESERVE_ID`/`UNRESERVE_ID` folded into `ALL_IDS` and the grant tests) so
  the manifest/dispatch/grant checks cover the three new commands the same
  way they already covered `apply`/`release`.
- Counts: **ambient `python -m pytest -q` (lupa already present on this
  workstation's ambient `PYTHONPATH`, not installed separately) = 2004
  passed, 3 skipped** (up from the 1979/3 this worktree started at after
  merging `main`, i.e. +25 net from this stream's own additions). **`dfmcp/
  tests` in `.venv-dfmcp` = 698 passed**, unchanged from before this stream
  (no `dfmcp` source files needed changing beyond the argument-description
  table and the two `agents/*/tools.yaml` grants, both covered by the
  manifest test above, not by a dedicated `dfmcp/tests` file).

**Left unverified** (offline build only; this worktree has no VM 103
credentials, and no deploy was in scope):
- Nothing here has run against a real DFHack process. The persistent-state
  shape, `reqscript` semantics, and `dfhack.world.ReadCurrentTick` were all
  checked against this file's own already-live sibling code (see above),
  not against a running game, so the same residual risk every other
  offline-built tool in this repo already carries applies here too.
- `landmarks.build`'s anchor-tile-only check is a real, intentional gap
  (documented in the code): a reservation that covers only the INTERIOR of
  a large footprint applied via this route, missing its anchor tile, would
  not be caught. No live case has exercised this path either way.
- The `res-N`-as-SITE-argument path in `apply` was only exercised against
  the bedroom-cell-v1 template (the one real template in this repo); no
  other real template has gone through `reserve` then `apply res-N`.
- Whether `dfhack.persistent`'s real (non-test-stub) serialisation handles a
  `wall_cells` table with potentially hundreds of string keys (up to the
  2500-tile `MAX_SITE_TILES` bound) without a size or performance surprise
  is unverified; every other per-site record in this codebase is far
  smaller.
- No deploy to VM 103, per the handoff's own scope; the orchestrator does
  the live verification after merge, per "Out of scope."
