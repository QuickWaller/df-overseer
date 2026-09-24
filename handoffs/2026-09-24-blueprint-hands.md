# Handoff: the Architect has eyes but no hands for carving, smoothing and furnishing

Date: 2026-09-24. **Offline build. No deploy, no VM mutation, no fort change.**
Live reads are allowed only where this brief names them, bounded and read-only,
and the fort stays paused. A deploy and the first real build each need their
own go-ahead, which the orchestrating session will ask for separately.

Read `CLAUDE.md` first, then `Working.md` (START HERE), the register rows
dated 2026-09-24 (quickfort already covers smoothing, engraving and traffic;
soil cannot be smoothed; the Architect stays propose-only), `blueprints/README.md`,
`blueprints/templates/bedroom-cell-v1.*`, `scripts/dfhack/df-overseer-surface.lua`
(the read side this verb pairs with) and the Architect's `proposal-0003` in
`evals/live/2026-09-24-architect-rematch/`.

## The gap

The Architect now proposes a sound room (stair, carve, smooth, furnish, zone)
but nothing can carry it out. The generic `building` tool places furniture and
`zone.place` places zones. Nothing carves rooms, smooths or engraves
surfaces, sets traffic, or constructs a wall where the material cannot be
smoothed (soil, ore). The register already records that quickfort's `#dig`
mode covers smoothing, carving, engraving and traffic designation; it has
never been read for what it exactly does or run.

## What to build

1. **Read quickfort from the installed source, not memory.** On the VM
   (read-only, no changes): `hack/docs`, `hack/scripts/quickfort.lua` and
   `hack/scripts/internal/quickfort/*`. Establish, with file and line cites:
   the `#dig` symbols for carve, smooth, engrave, track/traffic; how `#build`
   places walls; whether a dry run exists and what it reports; the Lua entry
   point and its arguments; what it returns on partial failure; how it handles
   tiles it cannot designate. Write it up as
   `research/2026-09-24-quickfort-hands.md`, marking verified vs inferred.
2. **One generic verb**, `scripts/dfhack/df-overseer-blueprint.lua`, wrapping
   quickfort. It takes a template id (from `blueprints/templates/`) or a named
   blueprint plus a site reference, dry run by default, real run only when
   asked. It must return what quickfort reported, then re-read the result
   with the surface layer's own reads (enclosure, finish, material) so a
   caller sees whether the room actually came out enclosed and finished,
   not just that designations were queued.
3. **Site reference without model-facing coordinates.** The verb must not ask a
   model to emit a raw coordinate and must not print one. Work out how a site
   is named (a handle from an existing find tool, a zone id, a landmark plus an
   offset) and say why. If quickfort needs an absolute start tile, resolve it
   inside the tool.
4. **Enforce the soil rule in data, not branches**: where a finish is required
   and the material cannot be smoothed, the verb reports that rather than
   silently leaving rough soil. Use the tile classification the surface layer
   already has.
5. **Generic by rule.** Any template, any blueprint, no per-room branches.
   Cost of the next room type must be one data entry.

## Scope

Yours: `scripts/dfhack/df-overseer-blueprint.lua` (new), `scripts/dfhack/TOOLS.yaml`,
`dfmcp/tools.py` and the matching schema, the allowlist for the **architect**
only (write verbs are not granted to the other advisors), tests, and
`research/2026-09-24-quickfort-hands.md`. Not yours: any other `.lua`,
`conductor/**`, `doctrine/**`, `dfqueue/**`, and per the `handoffs/` rule
`Working.md`, `decisions/DECISIONS.md`, `memory/` and `handoffs/INDEX.md`.
Collect owed register lines in your Result.

## Rules

- `git merge --ff-only main` first; this brief is committed on main.
- Both suites green with numbers quoted: ambient `python -m pytest` (baseline
  **1423 passed, 3 skipped**) and `dfmcp/tests` in `.venv-dfmcp` (baseline
  **652 passed**). Use `python`.
- pcall-guarded reads that return defaults hide failures: use the
  `read_failures` plus `dfhack.printerr` pattern.
- Bounded footprints and rings only, never an unbounded live query. Coordinate
  free output. No rendered map. No armok capability. No em dashes in prose.
  **No attribution lines in any commit message.** Commit as you go.
- Stop and report on any permission or classifier refusal. Never route around
  one through another agent or session.

## Done means

Given a template and a site, the verb's dry run states what would be
designated and what could not be, and its real run reports designations
queued plus a surface re-read. The research doc says exactly what quickfort
does and does not cover, so the next stream knows which gaps remain (wall
construction, furniture placement order). The Result names the live check a
deploy should run against a throwaway site and what the check cannot see.

## Result

### Milestone 1: research doc written (offline, VM read-only)

`research/2026-09-24-quickfort-hands.md` done. Headline findings: `-n` needs `/label` for a
.csv (bare word is read as a sheet name); quickfort refuses to smooth SOIL itself
(`dig.lua:77-87,288-297`), agreeing with the surface layer; `Cw` refuses WALL-shaped
tiles (`build.lua:107-165`), so standing soil cannot be finished in one blueprint (dig
then `Cw`); `#meta` applies sections back to back and swallows section errors
(`meta.lua:106-113`); building-occupied tiles are dropped from `s`/`d` uncounted.

A dry run (`-d`) writes nothing in dig, build or zone modes (source; not observed live).

### Milestone 2: the verb, manifest, grants and tests (offline)

Built: `scripts/dfhack/df-overseer-blueprint.lua` (new), five `TOOLS.yaml` commands
(`blueprint.plan`, `.preview`, `.apply`, `.sites`, `.status`), scoped argument text in
`dfmcp/tools.py`, allowlists, `tests/test_blueprint_tool_manifest.py` (26 tests) and
`tests/test_blueprint_lua_logic.py` (16 tests, runs the real Lua against a fake DFHack world in
lupa, skipped when lupa is absent), plus `tests/lua_stubs/dfhack_blueprint_world.lua`.
No Lua could be run against DFHack; nothing was run on the VM beyond `cat` of quickfort's source.

Design as built:
- **Generic.** The .csv is the only per-template input: sections and modes, footprint, the room
  rectangle (bounding box of the first zone section), and the finish requirement (every `s` cell
  of a dig section). No room word appears in code (a test greps for it). Next room type = one .csv
  deployed to `dfhack-config/blueprints/templates/` (or flat, the starter layout).
- **Site reference (item 3).** One argument, SITE. A landmark name means "find a new site" for a
  phase that starts by digging, ranked by the very same `ranked_candidates` diggable.find uses
  (RANK N is the same candidate), reached through the upvalue trick building.lua already uses on
  quickfort. A real first apply issues an opaque `site-N` handle whose real tile lives only in
  DFHack's per-site persistent state; every later phase, `status` and `sites` use the handle.
  Rejected: a zone id (a new room has none until after the dig), and landmark plus offset (an
  offset is a coordinate). The multi-phase case is why a handle is unavoidable: after the shell is
  dug the tiles are no longer diggable, so the site cannot be re-found by ranking.
- **Soil rule in data (item 4).** Each `s` cell's tile is classified with quickfort's own
  smoothable set (STONE, FEATURE, LAVA_STONE, MINERAL, FROZEN_LIQUID). `finish_plan` counts
  smoothable, already finished, and blocked by material name; `finish_required_met` is false and a
  `remedy` is given. "SOIL" appears nowhere in code (a test enforces that). Hidden and
  building-occupied cells are counted too, because quickfort drops them uncounted.
- **Order guard.** A phase whose sections include build, zone or place is refused before quickfort
  is called while the site has outstanding dig/smooth designations or a carve cell still solid.
- **Re-read (item 2).** `read_back` carries the pending-designation count (and
  `designations_landed`, false when quickfort claims tiles but the game shows none), the per-cell
  finish state, and the surface layer's own `enclosure`, `finish` and `boundary_material` over the
  room rectangle. Those reads are zone-id anchored, so the verb swaps surface.lua's module-local
  `find_zone` for a rectangle for the duration of one read and restores it, self-checking that the
  swap reached all three functions (`shim_restored`, and `surface.error` if not). This is the
  riskiest line in the file: it works in the fake world (Lua 5.4) but has never met DFHack. A test
  pins that `find_zone` stays a module local and that surface.lua reads only x1/y1/x2/y2/z/id off it.
- **Read vs mutate.** `preview` is `effect: read` (a dry run). `apply` defaults to a dry run and is
  `effect: mutate`; only `false` writes.

### DEVIATION FROM THE BRIEF, needs the orchestrator's eye

The brief said "allowlist for the architect only". `dfmcp/roles.py` rule 2 refuses a mutating tool
on any role but the roster's `sole_writer` (overseer), the Architect's own `write_authority: none`
says the same, and the 2026-09-24 register keeps the Architect propose-only. So the Architect
holds the four READ verbs (`plan`, `preview`, `sites`, `status`), and **`blueprint.apply` is on the
overseer's write list only**. Nobody else holds any of them (tested). If the intent really is a
mutating grant to the Architect, that needs a register row and a change to roles.py, which is not
this stream's file.

### Numbers

- Ambient `python -m pytest`: **1449 passed, 4 skipped** (baseline 1423 passed, 3 skipped; +26 new
  passing, +1 skip is the lupa module when lupa is absent).
- With lupa on the path (a scratch install via PYTHONPATH; lupa is not a repo dependency): the 16
  Lua-logic tests **passed**.
- `dfmcp/tests` in `.venv-dfmcp`: **652 passed** (unchanged).
- Verify-the-verification: adding SOIL to the Lua's smoothable set made exactly the two soil tests
  fail (one structural, one behavioural), then reverted.

### Deploy prerequisites (nothing was deployed)

1. Copy `scripts/dfhack/df-overseer-blueprint.lua` to the guest with the other scripts (it
   `reqscript`s landmarks, diggable and surface, already there).
2. Copy `blueprints/templates/bedroom-cell-v1.csv` to `dfhack-config/blueprints/templates/` on the
   guest (plain scp; `blueprints/README.md` says the guest layout is flat, which the verb also accepts).
3. Deploy the dfmcp server (TOOLS.yaml, tools.py, both tools.yaml) so the new ids exist.
4. Check `buildingplan` is enabled on VM 103 before any real `Cw` or furniture phase (build.lua
   warns unplanned buildings vanish without materials in stock); not established here.

### The live check a deploy should run (throwaway site, in this order)

Against the paused fort, after a quicksave, each step's output read before the next:
1. `blueprint.plan bedroom-cell-v1`: expect footprint 5x5, room 3x3, 15 finish cells, four phases.
   Proves the guest can read the .csv and the parse matches.
2. `blueprint.preview bedroom-cell-v1 bedroom_cell_v1_shell <landmark> 0 1`, then rank 2 and 3.
   Expect `stats["Tiles designated for digging"]` near 25 and `ok: true` on a stone site. Compare
   `finish_plan.blocked_by_material` with quickfort's own "Tiles that could not be designated"
   counter: on a soil site they should agree, which is the live proof the copied smoothable set
   matches quickfort's. Count designations on the fort before and after to prove the dry run wrote
   nothing.
3. Negative controls: a preview against a made-up handle (expect a named error), and a
   `bedroom_cell_v1_finish` preview against a real handle before its dig ran (expect `blocked`).
4. Only with a separate go-ahead: one real `apply` of the shell phase on a throwaway stone site,
   then `status` immediately (expect `designations_landed: true`, `pending_designations > 0`),
   unpause for a bounded window, `status` until `shell_done`, then apply
   `bedroom_cell_v1_finish` (needs a Bed item in stock) and read `status` last. Also confirm
   `read_back.surface` matches a direct `surface.enclosure` call on the zone id the zone phase
   created: the shim's live proof, and the only check that it reads the rectangle the real zone covers.

What that check cannot see: whether the entrance edge faces the corridor (nothing orients the
blueprint; `-t` is unused); whether `Cw` or a bed completes (needs materials and dwarf time beyond a
short window); whether `run_command_silent` returns quickfort's stdout for `#dig` stat lines
(inferred from the same pattern working for `#build`/`#zone`); the standing-soil finish (no verb
does it); a seam shared with a neighbouring cell (one cell per apply); and the `Blueprints applied`
swallow check on a genuinely failing section (needs one to exist).

### Remaining gaps for the next stream

1. Finishing a standing soil or ore wall: dig, then `Cw`, two applications a completed dig apart.
2. Entrance orientation (transform choice) and tiling neighbouring cells with shared seams.
3. surface.lua should export rectangle-anchored reads; then the shim can go.
4. Engraving as a second pass after smoothing completes (`e` needs a smooth tile).
5. Furniture that must go inside before a door, and a material-stock precheck for `Cw` and beds.

### Register lines owed (for the orchestrator)

- 2026-09-24: quickfort covers dig, smooth, engrave, traffic and constructed walls, but `Cw` refuses
  WALL-shaped tiles and `s` refuses SOIL, so a standing soil wall cannot be finished by any single
  blueprint; the template README's Cw fallback holds only for already-open tiles.
  Source: `research/2026-09-24-quickfort-hands.md`.
- 2026-09-24: blueprint verb built offline (`df-overseer-blueprint.lua`). Site reference is a landmark
  ranked as diggable.find ranks it, then an opaque `site-N` handle; not a zone id, not an offset.
  `apply` is the overseer's only, the Architect previews (roles.py rule 2, propose-only).
- Trap for `docs/TRAPS.md`: `-n` for a .csv must be `/label` (a bare word is a sheet name); `#meta`
  swallows a failing section (printerr only), so check `Blueprints applied`; building-occupied tiles
  are dropped from `s`/`d` with no counter.
- Stale or incomplete, not edited (out of scope): `blueprints/README.md` (deploy layout says flat)
  and the bedroom template's Cw resolution note (true only for already-open tiles).

