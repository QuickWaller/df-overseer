# Handoff: close the reservation gaps (finders, workshop kinds, landmarks footprint, per-command descriptions)

Date: 2026-09-30. **Executor, Sonnet, worktree.** Follows
`handoffs/2026-09-30-room-reservations.md` and
`handoffs/2026-09-30-reservation-holding.md` (merged `d7215e7`, `3e6e35b`).
Read both Result sections and `scripts/dfhack/df-overseer-reservations.lua`
first.

## Codebase-wide rules (review has caught each of these being broken)

- A dry run never changes anything: no persistent state, no designation, no
  record. Mutations happen only on a real run, after success.
- No tile coordinate ever leaves a tool in any output or error.
- DFHack's `ReadCurrentTick` is the tick within the current year and resets
  at New Year. For ages or intervals use `reservations_mod.abs_tick()`.
- Per-kind detail comes from the game's own data or a data entry, never a
  hard-coded list of kinds in a tool (tools-must-be-generalisable rule).
- Test stubs must model the real DFHack API shape. Say how you checked each
  one against live-verified sibling code; this repo has shipped wrong-field
  stubs twice.
- A new trailing optional argument must stay reachable through dfmcp: every
  optional before it needs a declared default in `TOOLS.yaml` equal to what
  the Lua does when the argument is omitted.

## What to do

1. **Finders skip reserved ground everywhere.** `building.lua`, `zone.lua`,
   `farm.lua`, `well.lua` and `workshop.lua` rank candidate sites without
   skipping reserved ones (their build then refuses the chosen tile). Make
   each ranking call the shared `reservations_mod.filter_reserved` exactly
   as `diggable`/`openarea` already do, so RANK N never lands on reserved
   ground (with `RES_ID`, candidates inside that reservation are kept).
2. **Workshop kinds through the game's own kind table.** `workshop.lua`
   keeps its own lowercase kind keys (`still`, `mason`, ...), which do not
   match `building.lua`'s tokens (`Still`, `Masons`). Resolve workshop
   kinds through `building.lua`'s kind table (the same one
   `kind_token_for_key` uses), so the kind checked against a reservation's
   `allowed_kinds` is the same token a template's `#build` cell resolves
   to. Keep `workshop.build`'s existing accepted inputs working (map old
   keys to tokens if agents or tests use them; say which). If a genuinely
   per-workshop policy lives in that table (labor, reagents), leave it but
   key it by the building token.
3. **`landmarks.build` checks its full footprint.** It checks only its
   anchor tile because it never learns the blueprint's size.
   `df-overseer-blueprint.lua` already parses blueprint CSV cells (for
   `template_allowed_kinds`). Reuse that parsing, exported if needed, to
   get the footprint of `BLUEPRINT_FILE` and check every tile it will
   cover. No second CSV parser. If the file's footprint cannot be read,
   refuse rather than fall back to anchor-only.
4. **Per-command argument descriptions in dfmcp.** `dfmcp/tools.py` scopes
   argument descriptions per script, so `zone.place`'s `OVERRIDE` (a
   reservation exception reason) and `zone.assign-owner`'s `OVERRIDE` share
   one blended description. Add per-command scoping (for example a key like
   `zone.place.OVERRIDE`) that wins over per-script and bare entries, then
   split that description into its two meanings. Update the module's own
   docs for the lookup order, and test the precedence.

## Out of scope

- Project MCP tools (a separate brief, dispatched after this merges; it also
  edits `dfmcp/tools.py`).
- Any deploy or live mutation on VM 103. The orchestrator live-verifies
  after merge with real dry-run calls.

## Rules

- `git merge --ff-only main` first.
- Tests: each of the five finders drops a reserved candidate (at least one
  run through the real tool file where stubs exist; the rest may go through
  the shared helper, say which); a workshop kind resolves to the same token
  a `#build` cell gives; `landmarks.build` refused when any footprint tile
  is reserved, not just the anchor; description precedence (command over
  script over bare).
- Run ambient `python -m pytest` (lupa on `PYTHONPATH`) and `dfmcp/tests`
  with `C:/website-projects/df-automation/.venv-dfmcp/Scripts/python.exe -m
  pytest -q dfmcp/tests`; report both counts (baseline 2030/3 and 699).
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in the Result section below.

## Result

**1. Finders skip reserved ground everywhere.** `building.lua`'s
`ranked_sites`, `zone.lua`'s `ranked_rects` AND `ranked_water_bodies`,
`farm.lua`'s and `workshop.lua`'s own `ranked_candidates` each now call
`reservations_mod.filter_reserved` on their raw candidate list before
sorting/deduping, exactly as `diggable.lua`/`openarea.lua` already did. Each
`find_*` caller (no `RES_ID` argument exists on any of these five find
commands) passes `nil`; each `build_*`/`place_zone` caller passes its own
`res_id`. Zone's water-body path needed its own `tiles_for` conversion
(native `{x,y}` pairs, not a rectangle) rather than reusing `rect_tiles`.
Tested `well.lua`'s real `ranked_candidates` end to end (the smallest honest
terrain surface of the five: no quickfort internal validator table the way
`building.lua`'s `tile_ok` needs) against a small fake DFHack world plus the
real `df-overseer-reservations.lua`
(`tests/test_finder_reservation_skip_lua_logic.py`,
`tests/lua_stubs/dfhack_well_reservations_world.lua`). `building`/`zone`/
`farm`/`workshop` have no existing fake game-map-world stub (building one
under time pressure risks modelling the wrong field), so those four are
checked by direct source inspection for the identical `filter_reserved` call
shape, in the same test file.

**2. Workshop kinds through the game's own kind table.**
`df-overseer-workshop.lua` kept its own lowercase kind keys (still/kitchen/
mason/mechanic/carpenter), which did not match `building.lua`'s tokens
(Still/Kitchen/Masons/Mechanics/Carpenters) -- flagged live in the prior
stream's own Result as a real gap. New `resolve_workshop_kind` resolves
every input (an old lowercase key, or a `building.lua` token/subtype
directly) through `building_mod.list_kinds`, restricted to type "Workshop",
the identical pattern `df-overseer-construction.lua`'s own
`resolve_construction_kind` already established for type "Construction".
`KIND_INFO` (labor/needs_container/named_requirement policy) is now keyed
by the building token; the value used for reservation checks
(`check_tiles`/`override_needed`/`record_override`) is always
`building_mod`'s own live-resolved token, never a hardcoded guess -- a token
collision surfaces as "no policy for this kind yet", not a silent mismatch.
Old inputs (still/kitchen/mason/mechanic/carpenter, case-insensitive) keep
working via an explicit alias table. Tested with a fake `building_mod`
exposing only `list_kinds` (the one function this file calls), the same
narrow-fake pattern `test_construction_lua_logic.py`'s own
`resolve_construction_kind` tests already use
(`tests/test_workshop_kind_lua_logic.py`,
`tests/lua_stubs/dfhack_workshop_kind_world.lua`); 13 tests cover the five
old-key mappings, direct token/subtype input, case-insensitivity, an
unknown kind, a real building kind with no policy entry, and a simulated
token collision (proving the safety net: a collided token is refused as
"no policy yet," never silently applied under the wrong token).

**3. `landmarks.build` checks its full footprint.** `build_at_landmark`
used to check only its own anchor tile, since it never learned
`BLUEPRINT_FILE`'s footprint size. `df-overseer-blueprint.lua`'s own
quickfort-CSV parser (`locate_blueprint`/`parse_sections`/`load_blueprint`)
could not simply be reqscript'd from `landmarks.lua` directly: that file
already reqscripts `df-overseer-landmarks.lua` (for near-landmark siting),
so the reverse edge would close a two-way reqscript cycle -- exactly what
`df-overseer-reservations.lua`'s own header warns against ("correctness
would depend on which file's own top-level execution had gotten further").
Extracted the parser verbatim into a new dependency-free leaf,
`df-overseer-blueprint-parse.lua` (no game API at all, pure text/CSV
parsing); `blueprint.lua`'s own exported `load_blueprint` is now a one-line
delegator to it, so there is exactly one parser, not two, and both files
reqscript the shared leaf instead of each other. The leaf adds
`load_blueprint_file(path)` for `landmarks.lua`'s own `BLUEPRINT_FILE`
convention (an exact, already-deployed path passed to quickfort's own `run`
verbatim), distinct from `blueprint.lua`'s own `TEMPLATE` bare-name
convention (`load_blueprint(name)`, tries `templates/NAME.csv` then
`NAME.csv`). `build_at_landmark` now checks every tile of the resolved
footprint, anchored top-left at the landmark's own centroid (the same
top-left anchoring `quickfort run -c` already uses), and refuses outright
-- never falling back to anchor-only -- if the footprint cannot be read at
all. Tested against the real `df-overseer-reservations.lua` and the real
new leaf, both loaded from source
(`tests/test_landmarks_footprint_lua_logic.py`,
`tests/lua_stubs/dfhack_landmarks_footprint_world.lua`): a reservation
inside the footprint but off the anchor tile is now caught (the literal
live gap this item fixes), one outside the footprint is untouched, `RES_ID`
+ `OVERRIDE` holds the whole footprint (not just the anchor), `RES_ID`
alone still refuses since "landmark_build" is never on any reservation's
allowed_kinds by construction, an unparseable blueprint file is refused
rather than silently treated as anchor-only, and a 2-tile-wide blueprint
whose SECOND tile (not the anchor) is reserved is still caught. The
extraction itself is proven behaviour-preserving: all 75 pre-existing
blueprint lua-logic and manifest tests pass unchanged (the test stub now
also loads the real new leaf, mirroring how it already loads the real
`df-overseer-reservations.lua`).

**4. Per-command argument descriptions in dfmcp.** `dfmcp/tools.py`'s
`_describe` scoped a description per SCRIPT only
(`tool.id.split(".", 1)[0]`), so `zone.place`'s `OVERRIDE` (a
reservation-exception reason string) and `zone.assign-owner`'s `OVERRIDE`
(an exact-word-`true` switch) shared one blended bare description. Added
per-command scoping: `_describe` now takes an optional `tool_id` and checks
a command-level key (`f"{tool_id}.{name}"`, e.g. `"zone.assign-owner.OVERRIDE"`)
before the script-level key (`f"{scope}.{name}"`) before the bare key,
threaded through `_parse_arg_tokens`/`_parse_one` from `_arg_specs_for_tool`
(which already has `tool.id`); `_parse_arg_token`, the single-token entry
point kept for callers that only see one name, passes neither, unchanged.
The bare `"OVERRIDE"` entry now describes only the reservation-exception
meaning (used by every other `OVERRIDE`-taking command); a new
`"zone.assign-owner.OVERRIDE"` command-scoped entry describes that one
command's own, unrelated meaning. Documented the full lookup order
(command over script over bare) in the module's own docstring, in the
existing "Argument descriptions" section. Tested `_describe`'s precedence
directly with a throwaway argument name (command beats script beats bare;
a sibling command in the same script still falls through to the script
entry; an unrelated script falls through to bare) and the real
`zone.place`/`zone.assign-owner` split through the registry
(`dfmcp/tests/test_tools.py`).

**Codebase-wide rules, how each was honored:**
- No dry run changes anything: none of the four items touches dry-run
  behavior; every reservation check remains a pure query before any
  designation, unchanged from the prior two streams' own discipline.
- No tile coordinate ever leaves a tool in any output or error: item 3's new
  footprint check reuses `reservations_mod.check_tiles`'s own
  coordinate-free refusal message unchanged; the new leaf file
  (`df-overseer-blueprint-parse.lua`) never sees or returns a game
  coordinate at all, only a parsed footprint size.
- `ReadCurrentTick`/`abs_tick()`: untouched by this stream; no new tick
  arithmetic was added.
- Per-kind detail from the game's own data: item 2 is precisely this rule
  applied where it had been missed -- workshop kinds now come from
  `building_mod.list_kinds`, never a hardcoded list.
- Test stubs modeled on real DFHack API shapes, with how each was checked
  stated per item above (well's terrain predicate checked field-by-field
  against its own real implementation; the fake `building_mod` exposes only
  the one real function, `list_kinds`, this file calls; the landmarks/
  blueprint-parse stub loads two REAL dependency-free leaves from source
  rather than faking either).
- A new trailing optional argument reachable through dfmcp: item 1 added no
  new arguments (reused existing `res_id` parameters already threaded
  through every `build_*`/`place_zone` signature by the prior stream); item
  2 changed no argument shape, only what a `KIND` string resolves to
  internally; items 3 and 4 add no new arguments either.

**Test counts.** Ambient `python -m pytest -q` (lupa on `PYTHONPATH`, this
worktree) = **2058 passed, 3 skipped** (up from this stream's own starting
baseline of 2030/3: +28 net, across
`tests/test_finder_reservation_skip_lua_logic.py` (7),
`tests/test_workshop_kind_lua_logic.py` (13),
`tests/test_landmarks_footprint_lua_logic.py` (6), and
`dfmcp/tests/test_tools.py`'s own two new precedence tests, which the
ambient run also collects). `C:/website-projects/df-automation/.venv-dfmcp/
Scripts/python.exe -m pytest -q dfmcp/tests` = **701 passed, 0 skipped**
(up from the stated baseline of 699: +2, the two new
`test_command_scoped_description_wins_over_script_scoped_and_bare`/
`test_zone_assign_owner_override_no_longer_blended_with_zone_place` tests).
The one known-flaky race test
(`test_queue_tools.py::TestWriteSerialisation::
test_concurrent_raw_appends_without_serialization_can_collide`) did not
flake in either full run.

**Left unverified / real, named gaps, not silently left:**
- Nothing in this stream ran against a real DFHack process (no VM 103
  credentials in this worktree, and no deploy was in scope). All four items
  are offline-built and offline-tested only, the same residual risk every
  other offline tool in this repo carries.
- Item 1's `building`/`zone`/`farm`/`workshop` finder-skip is proven at the
  shared `filter_reserved` layer (thoroughly unit-tested) and by direct
  source inspection of each call site, but not with an independent
  end-to-end test through any of those four files themselves (no existing
  fake game-map-world stub for any of them; building one under time
  pressure risks modelling the wrong field, the same caution the prior two
  streams already raised for these same four files' own designation call
  sites).
- Item 2: no real template in this repo declares a `#build` workshop cell
  today (unchanged from the prior stream's own note), so
  `resolve_workshop_kind`'s live effect on an actual reservation is still
  unexercised outside its own dedicated tests.
- Item 3: `building.lua`'s `ranked_sites`/`zone.lua`'s own ranking
  functions were NOT given a similar "learn my own footprint before
  checking" treatment beyond what item 1 already does for them (item 1 and
  item 3 are about different tools: item 1 is ranking-time skip, item 3 is
  `landmarks.build`'s previously-anchor-only check specifically) -- these
  are unrelated gaps, not left over from this item.
- Item 4: only `zone`'s `OVERRIDE` was fixed, the one the handoff named. A
  scan of every existing script-scoped `_ARG_DESCRIPTIONS` key (`building.*`,
  `zone.*`, `blueprint.*`, `workshop.*`, `workjob.*`) found no other case
  where two commands in the same script give the same argument name two
  clearly different meanings, but this was a review of the existing scoped
  entries, not an exhaustive audit of every bare-keyed argument across every
  command signature -- the mechanism is generic and ready for the next one
  if a reviewer finds one.

**Deploy/live mutation:** none, per scope. No VM 103 credentials in this
worktree; the orchestrator does live verification after merge.
