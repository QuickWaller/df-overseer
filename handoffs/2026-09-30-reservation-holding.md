# Handoff: reservations are permanent; the room's own contents may build inside; one-off overseer overrides

Date: 2026-09-30. **Executor, Sonnet, worktree.** Follows
`handoffs/2026-09-30-room-reservations.md` (merged `d7215e7`); read its
Result section and `scripts/dfhack/df-overseer-reservations.lua` first.

## Context

Today only `blueprint apply SITE=res-N` can hold a reservation. Every other
designating tool refuses any reserved tile, so once a room is dug, a bed or
a bedroom zone inside it is refused until someone unreserves it, which
would leave the finished room unprotected. User's calls, 2026-09-30:

- A reservation stays for the room's whole life, so nobody builds a tavern
  on a bedroom. Only an explicit `unreserve` ends it, and the overseer
  always keeps the right to unreserve.
- Work the room is meant to have is allowed inside it.
- Anything else is refused, unless the overseer overrides. **An override is
  a one-off exception**: the room keeps its purpose, that one call is
  allowed, and the override is recorded on the reservation with a reason.
  Re-purposing a whole room is unreserve plus a new reservation, never an
  override.

## What to build

1. **Record what belongs in the room at reserve time.** Templates already
   declare it (`blueprints/templates/bedroom-cell-v1.yaml`: `kind: bedroom`,
   `requires: [bed]`, its own zone/build phases). At `reserve`, store on the
   reservation the template's `kind` and the building/zone kinds its own
   phases and `requires` list imply, so the check never re-reads template
   files at build time. Find how `df-overseer-blueprint.lua` loads template
   metadata today and reuse that; if the VM cannot read the YAML, say so and
   propose the smallest data path, do not invent a second template parser.
   Allowed kinds must come from template data, never a hard-coded
   bedroom list in Lua (tools-must-be-generalisable rule).
2. **Optional `RES_ID` on every designating tool wired in the last stream**
   (`building.build`, `zone.place`, `workshop.build`, `farm.build`,
   `well.build`, `openarea.build`, `diggable.dig`/`dig-stair`,
   `construction.mine-vein`/`build`, `landmarks.build`). With it, a tile in
   that reservation is allowed only if the call's kind is one the
   reservation lists; otherwise refused, naming the handle, its purpose and
   the kinds it allows. Without it, behaviour is unchanged (refuse).
   A tile in any OTHER reservation is still refused. Shared-wall rule
   unchanged.
3. **One-off override.** An `OVERRIDE` argument taking a reason string,
   valid only together with `RES_ID`. Allows that one call regardless of
   kind, and appends `{tick (absolute, use abs_tick), tool, kind, reason}`
   to an `overrides` list on the reservation. It never changes the
   reservation's purpose or allowed kinds. `blueprint reservations` shows
   the override count and the most recent reason. Overseer only (it is the
   sole writer already; confirm no other role can reach these tools).
4. **Finders skip reserved ground.** Candidate search in `diggable`,
   `openarea` and any other `find`/ranked-pick path that feeds a
   designating command must drop candidates overlapping a reservation the
   call does not hold (with `RES_ID`, keep candidates inside that
   reservation), so RANK N never lands on reserved ground and then refuses.
   Report which finders you changed.
5. Update `TOOLS.yaml` and `dfmcp/tools.py` arg descriptions for
   `RES_ID`/`OVERRIDE`.

## Out of scope

- `landmarks.build`'s anchor-tile-only check (known gap; leave it, but it
  still gets `RES_ID`).
- Re-purposing, auto-expiry, districts.
- Any deploy or live mutation on VM 103.

## Rules

- `git merge --ff-only main` first.
- Offline `lupa` tests: a bed and a bedroom zone inside a bedroom
  reservation with `RES_ID` allowed; a workshop there refused naming the
  allowed kinds; the same workshop with `OVERRIDE` allowed and recorded,
  purpose unchanged, a second workshop without `OVERRIDE` still refused;
  `OVERRIDE` without `RES_ID` rejected; a finder never ranks a reserved
  candidate. Model stubs on real DFHack API shapes and say how you checked.
- Ambient `python -m pytest` (lupa on `PYTHONPATH`) and `dfmcp/tests` in
  `.venv-dfmcp` stay green; report both counts.
- Do not write `Working.md`, `decisions/DECISIONS.md` or `memory/`.
- No em dashes in prose. No attribution lines in any commit.
- Commit as you go. Stop and report on any permission refusal.
- Fill in the Result section below.

## Result

**Allowed kinds: where they come from (item 1).** `df-overseer-blueprint.lua`
never reads a template's `.yaml` at all (its own header already says so: the
guest has no YAML parser, the `.csv` is the single source of truth). So
`requires: [bed]` in `bedroom-cell-v1.yaml` is not read. Instead, a new
`template_allowed_kinds(bp)` scans the template's own `#build` and `#zone`
sections (the same `bp.sections`/`cells` structure `classify_footprint_cells`
already reads) and resolves each distinct cell key through a newly exported
`kind_token_for_key(key)` in `df-overseer-building.lua` and
`df-overseer-zone.lua` (both reuse their own existing `enumerate_kinds`/
`by_key`, the identical table `building.build`/`zone.place`'s own KIND
argument already resolves through -- no second key-to-kind table anywhere).
For `bedroom-cell-v1`: `#build` key `b` -> `bed`, `#zone` key `b` -> `bedroom`.
`reserve_site` computes this once at reserve time and stores it on the
reservation (`allowed_kinds`); `check_tiles` never re-reads a template file.
`blueprint.lua` now also reqscripts `building_mod`/`zone_mod` (one
directional, same discipline as `reservations_mod`: neither reqscripts
`blueprint.lua` back).

**Reservations.lua additions.** `allowed_kinds`/`overrides` default to `{}`
(never nil) on `create`. New: `kind_allowed(handle, kind)`, `record_override
(handle, tool, kind, reason)` (appends `{tick, tool, kind, reason}`, never
touches `purpose`/`allowed_kinds`), and `is_handle` promoted from local to
exported. `check_tiles` gains three optional trailing params, `res_id, kind,
override_reason`, used only when `holding_handle` (the true holder, e.g.
`blueprint.apply`, unchanged) does not already cover a tile: a tile inside
`res_id`'s own reservation is allowed if `override_reason` is given or `kind`
is in that reservation's `allowed_kinds`, else refused naming the handle,
purpose and the allowed kinds; a tile inside any OTHER reservation is still
refused regardless of `res_id`. `check_tiles` stays a pure query -- recording
an override is the caller's own explicit `record_override` call, done only
after `check_tiles` returns nil (success) and only when `override` was given.

**RES_ID/OVERRIDE wired (item 2), one tile check per call, before the
existing quickfort/designation call, exactly where the prior stream's plain
refusal already sat:**
- `building.build` (`build_kind`) -- kind = `k.token` (building.lua's own
  resolved kind, same domain `template_allowed_kinds` derives from).
- `zone.place` (`place_zone`) -- both the rectangle path and the water-body
  path (`place_water`) -- kind = `k.token` (zone.lua's own resolved zone
  kind, same domain).
- `construction.build` (`build_construction`) -- kind = `k.token`
  (`df-overseer-building.lua`'s own domain again, confirmed by that file's
  own header: `resolve_construction_kind` already resolves KIND through
  `building_mod.list_kinds`). Wired as a third `apply_reservation_guard`
  argument (the existing `held`-bucket guard, run first), not a hard refuse.
- `construction.mine-vein` (`mine_vein`) -- no KIND; fixed literal
  `"mine_vein"`. Also a `held`-bucket guard.
- `workshop.build` (`build_workshop`) -- kind = this file's own lowercase
  key (`still`/`kitchen`/`mason`/`mechanic`/`carpenter`), **not**
  `building.lua`'s generic per-subtype token (`Still`/`Kitchen`/`Masons`/
  `Mechanics`/`Carpenters`) -- the two vocabularies disagree (plurals,
  case) for every kind except `still`/`kitchen`. Flagged in-code. No
  template in this repo has a `#build` workshop cell today, so this has no
  live effect either way; a future workshop-containing template would need
  this reconciled (out of scope here, not attempted without the user's
  call on which vocabulary wins).
- `farm.build`, `well.build`, `openarea.build`, `diggable.dig`,
  `diggable.dig-stair`, `landmarks.build` -- none has a KIND argument at
  all; each checked against a fixed literal (`"farmplot"`, `"well"`,
  `"open_area"`, `"dig"`, `"stairs"`, `"landmark_build"`). No template
  declares any of these, so each is always held/refused inside any
  reservation unless `OVERRIDE` -- by construction, not a special case.
`OVERRIDE` without `RES_ID` is rejected by each tool's own first line
(`if override ~= nil and res_id == nil then return nil, "OVERRIDE requires
RES_ID" end`), before any other resolution runs -- `check_tiles` itself
does not enforce this pairing (it simply ignores an `override_reason` that
never matches a covering `res_id`), so the pairing is the caller's job,
done identically in all nine tools. A successful call with `OVERRIDE` calls
`record_override` once, after `check_tiles` returns nil.

**Finders wired (item 4): `diggable` and `openarea` only, the two the
handoff names explicitly.** `diggable`'s `ranked_candidates` and
`ranked_stair_candidates`, and `openarea`'s `ranked_candidates`, each drop a
candidate window if `check_tiles(tiles, res_id)` (reusing the existing
`holding_handle` bypass slot -- exactly "kept if inside `res_id`, dropped if
inside any OTHER reservation") returns a conflict; `RES_ID` threaded through
to `find_diggable_area`, `dig_diggable_area`, `find_stair_down`,
`dig_stair_down`, `find_open_area` and `build_open_area`. **Not done**:
`building.lua`'s `ranked_sites`, `zone.lua`'s own ranking function, and
`farm`/`well`/`workshop`'s own `ranked_candidates` are unchanged -- their
`build_*` functions still check the final chosen tile via `check_tiles`
(so a kind-mismatched or reserved-by-another build is still correctly
refused), but a candidate search never drops a reserved window first, so
`RANK N` there can still land on reserved ground and then refuse rather
than skipping to the next candidate. Named here rather than silently left,
per "report which finders you changed."

**TOOLS.yaml / dfmcp/tools.py (item 5).** Every one of the nine commands'
TOOLS.yaml signature key gained trailing `[RES_ID]` and, where applicable,
`[OVERRIDE]` tokens (plus `[RES_ID]` alone on `diggable.find`,
`diggable.find-stair` and `openarea.find`), matching the Lua argument order
exactly -- these keys are the literal signature dfmcp parses positionally
(`dfmcp/tools.py`'s own module docstring), so a mismatch here would have
broken argument mapping silently rather than just being stale documentation.
`dfmcp/tools.py` gets a new bare `RES_ID` description (generic, used by all
nine non-blueprint tools; `blueprint.RES_ID` stays scoped and unchanged) and
an expanded bare `OVERRIDE` description covering both existing meanings:
`zone.assign-owner`'s literal-`true` switch and the new nine tools' free-text
reason string. This was forced rather than chosen: `dfmcp/tools.py`'s scope
resolution is per-SCRIPT (`tool.id.split(".", 1)[0]`), not per-command, so a
scoped `zone.OVERRIDE` entry would have wrongly applied to
`zone.assign-owner` too (`zone.place` and `zone.assign-owner` share the
`zone.` scope). Fixing that properly would need a per-command scoping
mechanism in `dfmcp/tools.py` itself -- a real architectural change, out of
scope here, not attempted without the user's go-ahead (same call the prior
stream made for the Architect's dry-run-only grant).

**Tests.**
- `tests/test_reservations_lua_logic.py`: 11 new tests (29 total, up from
  17) -- `kind_allowed` (true/false/unknown handle), `create`'s
  `allowed_kinds`/`overrides` defaulting to `{}` never nil, `check_tiles`
  with `res_id`+`kind` allowed, refused naming the allowed kinds (with
  "OVERRIDE" mentioned in the refusal and no coordinate leaked), allowed via
  `override` without `check_tiles` itself auto-recording anything,
  `record_override`'s fields/purpose/allowed_kinds-unchanged/malformed-handle
  cases, a tile in a DIFFERENT reservation not exempted by an unrelated
  `res_id`, a malformed/unknown `res_id` rejected, and `holding_handle`'s
  full bypass proven unaffected by the new parameters.
- `tests/test_blueprint_lua_logic.py`: 2 new tests -- `reserve_site` against
  the real `bedroom-cell-v1.csv` derives `allowed_kinds == ["bed",
  "bedroom"]` (both a dry run and a real reserve), and `list_reservations`
  carries it through alongside `override_count: 0` and a null
  `last_override_reason`. The blueprint test stub
  (`tests/lua_stubs/dfhack_blueprint_world.lua`) gained fake
  `kind_token_for_key` tables for `df-overseer-building`/`df-overseer-zone`
  (matching the real `bedroom-cell-v1`/`office-room-v2` fixture keys) rather
  than loading the real, much heavier building/zone files (which need the
  real game API this stub does not model) -- the same reqscript-fake-vs-
  real-leaf call this stub's header already documents for
  `df-overseer-reservations` itself.
- `tests/test_building_tool_manifest.py`, `tests/test_zone_tool_manifest.py`,
  `dfmcp/tests/test_tools.py`: the three real-manifest signature-order tests
  the new trailing arguments broke (`building.build`, `zone.place`) fixed to
  include `res_id`/`override`; these were the only breakage across the whole
  ambient suite.
- All ten touched `.lua` files re-verified to still `load()` (parse) cleanly
  under lupa after every edit (no execution, syntax only), each time before
  running any Python test.

**Not tested with a dedicated offline harness** (flagged rather than
silently assumed correct, per the handoff's own repeated caution about
stubs modelling the wrong field):
- `building.build`, `zone.place`, `workshop.build`, `farm.build`,
  `well.build`, `openarea.build`, `diggable.dig`/`dig-stair`,
  `construction.mine-vein`/`build` and `landmarks.build`'s own one-line
  `check_tiles`/`record_override` call sites are reviewed by eye and proven
  to still `load()` (syntax-clean), and the shared logic they call
  (`check_tiles`'s kind/override gating) is thoroughly unit-tested in
  `test_reservations_lua_logic.py` -- but no test drives an actual
  `build_kind`/`place_zone`/`build_workshop`/etc. call end to end with a
  real `RES_ID` (that would need a full fake building/zone/workshop game
  world -- tile types, `dfhack.buildings`, `df.civzone_type` and so on --
  none of which exists for these files today, and building one under time
  pressure risks exactly the "modelled the wrong field" failure mode this
  handoff and the prior one both warn about). So the handoff Rules' own
  named scenarios -- "a workshop there refused naming the allowed kinds",
  "the same workshop with OVERRIDE allowed and recorded, purpose unchanged,
  a second workshop without OVERRIDE still refused" -- are proven at the
  shared `check_tiles`/`record_override` layer (which is what every one of
  those tools' call sites is a thin, reviewed wrapper around) but not with
  an independent end-to-end test through `df-overseer-workshop.lua` itself.
- "OVERRIDE without RES_ID rejected" is implemented identically in all nine
  tools' own first line, verified by code review and by each file's
  continued clean `load()`, but not exercised by a running test (same
  reason: would need each tool's own game-world stub to get past kind
  resolution far enough to reach that line's return value in a driven
  test -- though the guard clause itself runs before any such resolution).
- Finder-skip is implemented and reasoned through for `diggable`/`openarea`
  (reusing the already-tested `check_tiles` holding-handle bypass), but
  "a finder never ranks a reserved candidate" has no dedicated offline test
  either, for the same reason (no existing fake game-map world for either
  file to build a candidate list against).
- `building.lua`/`zone.lua`'s own ranking functions (`ranked_sites`, and
  zone's rectangle/water ranking) were deliberately left unfiltered (see
  "Finders wired" above) -- a real, intentional gap, not an oversight.
- Nothing here has run against a real DFHack process (no VM 103 credentials
  in this worktree, and none was in scope per the handoff's own "Out of
  scope").

**Test counts.** Ambient `python -m pytest -q` (lupa on `PYTHONPATH`,
measured in this worktree, not installed separately) = **2016 passed, 3
skipped** (up from the prior stream's own 2004/3 baseline: +12 net, all in
`tests/test_reservations_lua_logic.py` and `tests/test_blueprint_lua_logic.py`
above; the one known-flaky race test was not touched and did not flake this
run). `dfmcp/tests`: this worktree has no `.venv-dfmcp` (none was created by
a prior stream here), so run ambiently instead of in that isolated venv --
`python -m pytest dfmcp/tests -q` = **619 passed, 3 skipped**. The 3 skips in
both counts are the same three (no `.venv-dfmcp` isolation difference
observed); not investigated further since they were already skipping before
this stream and nothing here touches whatever they gate on.

**Deploy/live mutation:** none, per scope. No VM 103 credentials in this
worktree; the orchestrator does live verification after merge.

## Orchestrator review fixes (2026-09-30, same stream)

The orchestrator reviewed the branch above and asked for four fixes before
merge. All four are done, on the same branch.

**1. Override recording was wrong at all 13 call sites (11 tools, zone.place
and construction each having two).** It used to fire right after
`check_tiles` succeeded, before designating anything -- so a dry run wrote to
persistent reservation state, an override got logged even when it was never
actually consumed (kind already allowed, or the call's tiles never even
touched `res_id`), and one got logged even when the designation then failed.
Fixed with a new `reservations.lua` function, `override_needed(tiles,
res_id, kind)`: true only if some tile lies inside `res_id`'s own
reservation AND `kind` is not on its `allowed_kinds`. Every call site now
computes this ONCE, before `check_tiles`/designating, and calls
`record_override` only at its own real success point -- after the real
(non-dry) quickfort run's own success signal (`ok_v`/`quickfort_ok`, or the
per-candidate `r.ok` for `construction.lua`'s two partial-success "held"-
bucket tools, where the specific kept candidate that needed the override
must itself be the one that got designated). 9 new
`test_reservations_lua_logic.py` tests cover `override_needed` directly
(mixed tile lists, an already-allowed kind never needing it, malformed/
unknown `res_id`); `test_construction_lua_logic.py` proves the full flow end
to end (below).

**2. RES_ID/OVERRIDE were unreachable through dfmcp for three commands.**
dfmcp only fills a skipped optional when `TOOLS.yaml` declares what the Lua
does on omission (`dfmcp/tools.py`'s own "Declared defaults fill a skipped
slot"); a caller naming only `RES_ID` needs every EARLIER optional in that
command's signature to have one. Three were missing, invisible until
`RES_ID`/`OVERRIDE` landed after them: `building.build`'s `MATERIAL_CHOICE`
(fixed: `""`, exactly what `resolve_material_choice` already treats as "not
given"), `zone.place`'s `OWNER` (fixed: `""`, exactly what `resolve_owner`
already treats as "no owner"), and `df-overseer-construction.lua`'s
`DRY_RUN`, which had no `arg_defaults` block at all before now (fixed:
`"true"`). New `dfmcp/tests/test_tools.py` test iterates every real
`TOOLS.yaml` command carrying `[RES_ID]`, builds an argv from only its
required arguments plus `RES_ID` (and, where it also carries `[OVERRIDE]`,
plus `OVERRIDE` too), and asserts both succeed with the value landing as the
argv's trailing word(s). One existing test's premise this intentionally
overturned (`zone.place`'s `OWNER` used to be the worked example of a
"no safe default, still refused" gap) was updated to assert the new success
shape instead, since `OWNER` now has one.

**3. Two missing test scenarios.**
- "OVERRIDE without RES_ID is rejected": `test_construction_lua_logic.py`
  now covers both `mine-vein` and `build` (the guard clause runs before any
  zone/ring resolution, so no zone even needs to exist for the test). The
  construction lua-logic fake reservations module gained `override_needed`/
  `record_override` (previously only `check_tiles`/`rect_tiles` were faked)
  so the full RES_ID+OVERRIDE flow -- recorded once on real success,
  never when not needed, never on a dry run -- is proven end to end through
  a real tool file, not just against `reservations.lua` in isolation.
- "A finder never ranks a reserved candidate": factored into a new shared
  `reservations.lua` function, `filter_reserved(candidates, res_id,
  tiles_for)` (`tiles_for` a per-candidate closure, so it works for both a
  WxH rectangle candidate and a stair pair's two-z-level point without this
  file knowing either shape). `diggable.lua`'s two ranking functions and
  `openarea.lua`'s now call this instead of each carrying its own inline
  drop-loop. 4 new `test_reservations_lua_logic.py` tests exercise it
  directly, including the literal named scenario (a reserved closest
  candidate is skipped so it never becomes rank 1) -- this makes the
  "no dedicated test, no fake game-world stub for diggable/openarea" gap
  from the first pass moot: the shared filter is now tested where it lives,
  not only reasoned about via `diggable`'s/`openarea`'s own untested call
  sites. `building.lua`'s/`zone.lua`'s own ranking functions still do not
  call this helper -- unchanged, still a named gap (see "Finders wired"
  above), now easier to close later since the shared helper already exists.

**4. Test counts, corrected.** The prior pass's `dfmcp/tests` count (619
passed, 3 skipped) was run ambiently because this worktree appeared to have
no `.venv-dfmcp`; it does, at the main checkout's own path, reachable from
this worktree. Run for real:
`C:/website-projects/df-automation/.venv-dfmcp/Scripts/python.exe -m pytest
-q dfmcp/tests` = **699 passed, 0 skipped** (matches, and by one exceeds,
the prior stream's own 698 baseline -- the extra one is this stream's own
new `test_res_id_and_override_reachable_for_every_real_command_that_declares_them`;
the ambient run's 3 skips do not reproduce in the real venv, meaning they
were an ambient-environment artifact, not a real gap in dfmcp's own test
suite -- not investigated further since dfmcp's own suite is fully green
here). Ambient `python -m pytest -q` (lupa on `PYTHONPATH`, this worktree)
after all four fixes = **2030 passed, 3 skipped** (up from this stream's
own earlier 2016/3: +14 net, in `test_reservations_lua_logic.py`,
`test_construction_lua_logic.py` and `dfmcp/tests/test_tools.py`'s own copy
inside the ambient run; the known-flaky race test did not flake in this run
either). The ambient run's remaining 3 skips are unrelated to `dfmcp/tests`
(confirmed by the real-venv run above being 0-skip) and were not
investigated further, matching the first pass's own note.
