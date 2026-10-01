-- df-overseer-construction.lua
--@module = true
--
-- handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md.
-- decisions/DECISIONS.md 2026-09-24 found a real gap: this fort's room
-- pipeline smoothed an ore vein into a room's wall instead of mining it out
-- and replacing the hole with a constructed wall, because (a)
-- df-overseer-blueprint.lua's smoothable set allows mineral, so an ore vein
-- reads as an ordinary smoothable wall, and (b) NOTHING in this codebase
-- could build a construction (wall/floor/etc.) at all -- that half was
-- missing entirely, not just buggy. This file is that missing half, plus
-- the mining step that must run before it (research/2026-09-24-quickfort-
-- hands.md section 3: "the only route to a finished soil-or-vein wall is
-- two steps: dig the tile out, let the job complete, then build the
-- construction over the now-open tile -- a one-shot blueprint cannot
-- express that").
--
-- GENERALISABLE BY RULE (CLAUDE.md, "Tools must be generalisable"):
--   - `mine-vein` takes no kind at all -- ore/gem identification is read
--     from the game's own vein data (df-overseer-surface.lua's
--     decode_vein_tile, extended for exactly this by this same handoff),
--     never a hard-coded "hematite" branch.
--   - `build` takes KIND as an argument, resolved the SAME way
--     df-overseer-building.lua's own generic build tool resolves any other
--     building kind (its exported `list_kinds`, reused here rather than
--     re-implemented -- see resolve_construction_kind below). Today's live
--     case is Wall; naming Floor, Ramp, UpStair, DownStair or any other
--     construction subtype quickfort knows costs no new code here.
--
-- ZONE-ANCHORED, NEVER A RAW COORDINATE (design commitment #1): both verbs
-- take a ZONE_ID and act over that zone's own boundary ring, resolved
-- through df-overseer-surface.lua's own find_zone/ring_tiles (promoted from
-- `local` to global by this same stream specifically so this file could
-- reuse them instead of duplicating the zone-resolution/ring-walk logic --
-- see that file's header comment on the change). A real x,y,z exists only
-- inside this file's own local scope, for the instant it takes to build
-- quickfort's `-c` argument, exactly like df-overseer-building.lua's
-- build_kind and df-overseer-diggable.lua's dig_diggable_area already do.
--
-- ONE TILE, ONE BLUEPRINT APPLICATION -- not a sparse multi-cell blueprint
-- with blank cells standing for "leave this tile alone". A zone's ore/gem
-- tiles are typically a handful scattered around a ring (the motivating
-- case is 5 of a 3x3 office's 16 ring tiles), and this stream found no
-- confirmed source reading (research/2026-09-24-quickfort-hands.md does not
-- cover it) for how quickfort's #dig/#build parsers treat a blank grid
-- cell. Rather than guess at an unverified mechanism, each identified tile
-- gets its OWN 1x1 blueprint applied via `-c` at that tile's own real
-- coordinate -- the exact, already-verified shape df-overseer-diggable.lua's
-- dig-stair and df-overseer-building.lua's build_kind already use for a
-- single-cell application. Slower for many tiles, but every step is a
-- pattern this codebase has already run for real, not a new one.
--
-- ORDER IS ENFORCED BY WHAT `build` READS, NOT BY BOOKKEEPING: `build`
-- re-reads each ring tile's live shape before deciding (never assumes
-- `mine-vein` already ran, per the handoff's own instruction). A tile still
-- shaped WALL is refused by name ("not yet mined"), never silently skipped
-- or guessed open -- matching every other refuse-rather-than-guess
-- discipline in this codebase (df-overseer-diggable.lua's is_diggable,
-- df-overseer-surface.lua's tile_read).
--
-- MATERIAL CHOICE: as of 2026-10-01 (handoffs/2026-10-01-buildingplan-
-- material-filter.md, register 2026-09-30 ruling) this is ENFORCED, not just
-- advisory. building.lua exports `building_filters_and_gaps` (the real
-- material breakdown/economic-exclusion logic, by raw building type/subtype/
-- custom rather than its own internal kind table) and `apply_material_filters`
-- (writes the resolved CLASS into buildingplan's own per-building-type
-- filter for the duration of a real quickfort run, then restores what was
-- there before -- see that file's header comments on both for the mechanism,
-- sourced from DFHack at 53.16-r1). This file calls straight into both
-- rather than duplicating them, now that the real write needs the real
-- logic, not just a report. `k` here only ever carries the subtype's NAME
-- (df-overseer-building.lua's own kind_summary), never its numeric enum;
-- `df.construction_type` is a bidirectional DFHack enum table (name and
-- number both index it, the same property building.lua's own enum_name
-- already relies on), so the number is recovered with `df.construction_type
-- [k.subtype]` -- [reasoned, not verified live].
--
-- GUARDS (added by handoffs/2026-09-28-keeps-access-guard.md, building on
-- research/2026-09-28-job-dependency-graph.md section 4.2): `build` now runs
-- two tool-layer refusal guards over its candidate targets before
-- designating anything -- `item_present` (an unhauled item sits on the
-- target tile) and `keeps_access` (building all of this step's targets
-- together would seal off exposed, reachable ore). A held target is neither
-- built nor counted as `refused`; it appears in a new `held` list with a
-- named reason, and the rest of the step proceeds. See the guard section
-- below (just above build_construction) for the full reasoning, including
-- why keeps_access does NOT call df-overseer-reachability.lua's hypothetical
-- pathfinding (it can't answer one) and instead uses a narrower, live,
-- no-mutation neighbour check.
--
-- Usage: ./dfhack-run df-overseer-construction mine-vein ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]
-- Usage: ./dfhack-run df-overseer-construction build ZONE_ID KIND [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]
--   MATERIAL_CHOICE is optional, same contract as df-overseer-building.lua's
--   own build: omit it to exclude economic materials by default, pass
--   "allow_economic" to allow them, or name a material (e.g. SHALE) to pick
--   it explicitly.
-- Usage: ./dfhack-run df-overseer-construction door ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]
-- Usage: ./dfhack-run df-overseer-construction audit [ZONE_ID] [DRY_RUN]
--
-- ENTRANCE GUARD, door, audit (handoffs/2026-10-01-entrances-get-doors.md):
-- live incident 2026-10-01 (evals/live/2026-10-01-queue-and-material-deploy/
-- README.md, "Month window, a sealed office") -- `build` designated ring
-- walls around the office on 2026-09-28 that included the room's own way
-- out; `keeps_access` protects exposed ore, not a room's own exit, and
-- never re-checked walls designated before it existed. This stream adds:
--   - `find_entrances` (below, next to `build`'s guards): a ring tile is the
--     room's entrance if it has an inside neighbour that is the zone's own
--     footprint rectangle (structural -- always true for a non-corner ring
--     tile, by the geometry of `ring_tiles`/`footprint_tiles` in
--     df-overseer-surface.lua) and an outside neighbour that belongs to the
--     fort's main walkable group (the group most citizens are in, read via
--     df-overseer-connectivity.lua's exported get_connectivity_report,
--     never re-derived here). A ring CORNER never qualifies: neither of its
--     two orthogonal neighbours lies inside the footprint, so it cannot be
--     "the way out" by this definition -- see ring_edge_neighbours below.
--   - `build` now computes this zone's entrances before designating
--     anything. Zero entrances found among the OPEN ring tiles this call
--     could touch refuses the WHOLE call by name (never guesses it is safe
--     to proceed with no exit); any found entrance tile is pulled out of
--     the candidate set before the other guards run and reported in `held`
--     with guard "entrance" (a named skip, never silent) -- for EVERY KIND,
--     not just Wall: per CLAUDE.md's generalisability rule, this guard does
--     not try to know which construction subtypes block walking and which
--     do not (that would be per-kind branching in code); it conservatively
--     protects the entrance tile from any construction.build call.
--   - `door` places a Door (df-overseer-building.lua's own generic
--     list_kinds, not a hard-coded building number) at every entrance this
--     same find_entrances identifies, through the identical one-tile
--     quickfort `-c` application `build`/`mine-vein` already use. Chosen
--     over "a documented call to building.build Door at that tile"
--     (the handoff's other option) because building.build's own site
--     search (`ranked_sites`, NEAR_LANDMARK plus a search radius) finds an
--     open area that FITS a building, which is the wrong question for "put
--     a door at THIS exact, already-known entrance tile" -- construction.lua
--     already owns the exact-ring-tile-targeting machinery `build` and
--     `mine-vein` use (apply_single_cell, the reservation/item_present
--     guards), so `door` reuses it rather than bending building.lua's
--     site-search tool to a job it was not built for. MATERIAL_CHOICE is
--     not threaded through for Door (unlike `build`): buildingplan's own
--     default applies, undocumented scope choice stated here plainly rather
--     than silently dropped.
--   - `audit` is the backstop for walls designated BEFORE this guard
--     existed (exactly the 2026-09-28 walls that caused the incident): for
--     a zone (or every activity zone the game knows, if ZONE_ID is
--     omitted), it reads every ring tile's live state and classifies each
--     as built (shape already WALL), planned (a Construction building
--     exists here, per the same bld:getBuildStage() == bld:getMaxBuildStage()
--     check df-overseer-building.lua's kind_previously_built and
--     df-overseer-zone.lua's content_row already use live, but NOT yet at
--     max stage -- the job has not finished, the tile has not become a wall
--     yet) or open (neither). It then asks find_entrances the same
--     question over just the OPEN tiles: if none of them would still work
--     as an entrance once every PLANNED tile also finishes, the room is
--     one bad job completion away from being sealed, exactly building 22's
--     situation on 2026-09-28. The planned tile(s) that themselves would
--     have qualified as the entrance (found by the same find_entrances
--     against the planned set) are named `at_risk`; a mutating,
--     DRY_RUN-default-true call sets `job.flags.suspend` on at least one of
--     them (the same hand stopgap `job.flags.suspend` used live on building
--     22, now a named tool action instead of a manual flag flip), using the
--     deterministic first-in-ring-order tie-break `keeps_access` already
--     established for "hold just enough to keep one approach open".
--
-- NOT VERIFIED LIVE (offline stream, no VM access): the whole entrance/
-- door/audit path, same honesty this file's header already states for
-- mine-vein/build. `bld:getBuildStage()`/`getMaxBuildStage()` and
-- `dfhack.job.getHolder`/`job.flags.suspend` are each already a live-
-- verified call site elsewhere in this codebase (df-overseer-building.lua's
-- kind_previously_built, df-overseer-zone.lua's content_row,
-- df-overseer-stuckjobs.lua's get_stuck_jobs/job.flags.suspend) -- this file
-- only recombines them, it does not claim them freshly confirmed here.

local json = require('json')
local utils = require('utils')
local surface_mod = reqscript('df-overseer-surface')
local building_mod = reqscript('df-overseer-building')
-- handoffs/2026-09-30-room-reservations.md decision 3: mine-vein and build
-- both hold (not refuse) a ring tile inside a reservation neither holds --
-- see apply_reservation_guard below, next to the other two guards.
local reservations_mod = reqscript('df-overseer-reservations')
-- handoffs/2026-10-01-entrances-get-doors.md: the shared tri-state
-- reachability primitive (group_matches, never a new pathfind) and the
-- "main walkable group" reading (get_connectivity_report's own
-- main_group_id, reused rather than re-derived from warn-stranded here).
local reachability_mod = reqscript('df-overseer-reachability')
local connectivity_mod = reqscript('df-overseer-connectivity')

local NULL = "\0"
local function nn(v) if v == nil then return NULL end return v end
local function encode(v) return json.encode(v, {null = NULL}) end

-- Same bound as df-overseer-surface.lua's own MAX_RING_TILES (duplicated,
-- not reqscript'd, so this file's own refusal message is self-contained;
-- kept numerically identical on purpose).
local MAX_RING_TILES = 900

local function truthy_dry_run(v)
  if v == nil then return true end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- ---------------------------------------------------------------------------
-- Reaching df-overseer-surface.lua's zone-resolution/ring-walk/vein-decode
-- WITHOUT promoting them to globals there (see that file's own header on
-- `find_zone`: promoting them broke df-overseer-blueprint.lua's rectangle
-- shim, which depends on find_zone staying a real upvalue of
-- enclosure/finish/boundary_material). Same `debug.getupvalue` idiom
-- df-overseer-building.lua already uses to reach quickfort's own local
-- table (`upvalue_by_name` there), duplicated here rather than reqscript'd
-- (it is file-local in building.lua too). `vein_material` is the one
-- exported function that closes over find_zone/ring_tiles/decode_vein_tile;
-- decode_vein_tile itself closes over tile_read, so it takes a second hop.
-- Every hop that could vanish in a future surface.lua edit reports which
-- hop it was, never a silent nil.
-- ---------------------------------------------------------------------------

local function upvalue_by_name(fn, want)
  if type(fn) ~= 'function' then return nil end
  local i = 1
  while true do
    local n, v = debug.getupvalue(fn, i)
    if n == nil then return nil end
    if n == want then return v end
    i = i + 1
  end
end

local function surface_hooks()
  if type(debug) ~= 'table' or type(debug.getupvalue) ~= 'function' then
    return nil, "debug.getupvalue is not available in this DFHack Lua"
  end
  local vm = surface_mod.vein_material
  if type(vm) ~= 'function' then
    return nil, "df-overseer-surface.lua no longer exports vein_material"
  end
  local find_zone = upvalue_by_name(vm, 'find_zone')
  local ring_tiles = upvalue_by_name(vm, 'ring_tiles')
  local decode_vein_tile = upvalue_by_name(vm, 'decode_vein_tile')
  if not (find_zone and ring_tiles and decode_vein_tile) then
    return nil, "vein_material no longer closes over find_zone/ring_tiles/decode_vein_tile by those names"
  end
  local tile_read = upvalue_by_name(decode_vein_tile, 'tile_read')
  if not tile_read then
    return nil, "decode_vein_tile no longer closes over tile_read by that name"
  end
  return {find_zone = find_zone, ring_tiles = ring_tiles, decode_vein_tile = decode_vein_tile, tile_read = tile_read}
end

-- ---------------------------------------------------------------------------
-- Blueprint plumbing: one tile, one application. Mirrors
-- df-overseer-building.lua's write_blueprint/parse_quickfort_stats exactly
-- (duplicated rather than reqscript'd -- both are file-local there).
-- ---------------------------------------------------------------------------

local function write_single_cell_blueprint(mode, cell, tag)
  local filename = string.format("_tmp-construction-%s-%s-%d.csv", tag, cell, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then return nil, "could not open blueprint for writing: " .. tostring(open_err) end
  f:write("#" .. mode .. "\n" .. cell .. "\n")
  f:close()
  return filename
end

local function parse_quickfort_stats(output)
  local stats = {}
  if not output then return stats end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then stats[label] = tonumber(value) end
  end
  return stats
end

-- `label` is the one stat that counts a successful designation ("Tiles
-- designated for digging" for #dig, "Buildings designated" for #build --
-- research/2026-09-24-quickfort-hands.md sections 2-3); every OTHER stat
-- quickfort printed is a problem counter, same rule
-- df-overseer-building.lua's assess_quickfort already established (a
-- negative control there found quickfort returns CR_OK even when it
-- designated nothing).
local function assess(ran, res, stats, label)
  local problems = {}
  if not ran then return false, problems end
  for l, n in pairs(stats or {}) do
    if l ~= label and n ~= 0 then
      problems[#problems + 1] = l .. ": " .. tostring(n)
    end
  end
  table.sort(problems)
  local designated = (stats or {})[label] or 0
  return (res == CR_OK and designated >= 1 and #problems == 0), problems
end

-- Applies one single-cell blueprint at (x, y, z) via `-c`, real coordinate
-- used only for the instant it takes to build this argument (never
-- returned). Returns a result record; the blueprint file is always removed
-- afterward, dry run or real.
local function apply_single_cell(mode, cell, x, y, z, dry, label, tag)
  local filename, werr = write_single_cell_blueprint(mode, cell, tag)
  if not filename then
    return {ok = false, error = werr}
  end
  local coord = string.format('%d,%d,%d', x, y, z)
  local ok_run, output, res
  if dry then
    ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord, '-d')
  else
    ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord)
  end
  local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
  local stats = ok_run and parse_quickfort_stats(output) or nil
  local ok_v, problems = assess(ok_run, res, stats, label)
  return {
    ok = ok_v,
    problems = problems,
    error = (not ok_run) and tostring(output) or nil,
    stats = stats,
    blueprint_removed = (ok_rm and rm == true),
  }
end

-- ---- reservation (handoffs/2026-09-30-room-reservations.md decision 3) ---
--
-- Every designating tool refuses a tile inside a reservation it does not
-- hold. This tool already has a `held` bucket (mine-vein below, and the two
-- guards further down for build), so a reservation conflict holds just the
-- affected ring tile(s) rather than refusing the whole call -- matching
-- item_present/keeps_access's own "held is not refused" shape. No
-- holding-handle concept here (decision 4): always checked with no holder.
-- Defined here, before mine_vein, so mine_vein's own lexical scope (a Lua
-- `local function` is only visible from its definition point onward) can
-- see it -- item_present/keeps_access are defined right before their own
-- caller (build_construction) for the identical reason.
-- res_id/kind/override (handoffs/2026-09-30-reservation-holding.md items
-- 2-3): threaded straight into check_tiles, which already does the RES_ID/
-- kind/override-reason gating (see that file). A held candidate here is
-- exactly "check_tiles refused this one tile" -- either it belongs to an
-- unrelated reservation, or it belongs to res_id's own reservation but this
-- call's kind is not one it allows and no override was given.
local function apply_reservation_guard(candidates, res_id, kind, override)
  local held, kept = {}, {}
  for _, c in ipairs(candidates) do
    local conflict = reservations_mod.check_tiles({{x = c.x, y = c.y, z = c.z}}, nil, res_id, kind, override)
    if conflict then
      held[#held + 1] = {ring_position = c.ring_position, reason = conflict.message}
    else
      kept[#kept + 1] = c
    end
  end
  return held, kept
end

-- ---------------------------------------------------------------------------
-- mine-vein ZONE_ID [DRY_RUN]
-- ---------------------------------------------------------------------------

-- RES_ID/OVERRIDE (handoffs/2026-09-30-reservation-holding.md item 2):
-- mine-vein has no KIND at all -- checked against the fixed literal
-- "mine_vein". No template declares it: mining out a vein IN a reserved
-- wall ring is destructive to that wall, never a template's own intent, so
-- it is always held unless OVERRIDE.
function mine_vein(zone_id, dry_run, res_id, override)
  if override ~= nil and res_id == nil then
    return {error = "OVERRIDE requires RES_ID"}
  end
  local hooks, herr = surface_hooks()
  if not hooks then return {error = herr} end
  local b, err = hooks.find_zone(zone_id)
  if not b then return {error = err} end
  local ring = hooks.ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local dry = truthy_dry_run(dry_run)

  local candidates, already_open, refused = {}, {}, {}
  for i, xyz in ipairs(ring) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local rec = hooks.decode_vein_tile(x, y, z)
    if rec.vein_status == "ore_or_gem" then
      local t = hooks.tile_read(x, y, z)
      if t.ok and not t.hidden and t.shape == df.tiletype_shape.WALL then
        candidates[#candidates + 1] = {ring_position = i, x = x, y = y, z = z, mineral_name = rec.mineral_name}
      elseif t.ok and not t.hidden then
        already_open[#already_open + 1] = string.format(
          "ring tile %d (%s): already open, nothing to mine", i, tostring(rec.mineral_name))
      else
        refused[#refused + 1] = string.format(
          "ring tile %d (%s): could not confirm its current shape (%s); refusing to designate rather than guess",
          i, tostring(rec.mineral_name), t.err or "hidden")
      end
    elseif rec.vein_status == "unknown" or rec.vein_status == "unreadable" then
      refused[#refused + 1] = string.format(
        "ring tile %d: vein classification %s%s; refusing to designate rather than guess it is ore",
        i, rec.vein_status, rec.error and (" (" .. rec.error .. ")") or "")
    end
    -- not_mineral / not_economic / hidden: not ore, not listed as refused --
    -- confidently NOT a candidate, not an unclassifiable one.
  end

  -- Reservation guard (handoffs/2026-09-30-room-reservations.md decision 3),
  -- run before digging any candidate: this tool already reports a `held`
  -- bucket separate from `refused`, so a reservation conflict holds just
  -- that ring tile rather than refusing the whole call.
  local reservation_held, kept_candidates = apply_reservation_guard(candidates, res_id, "mine_vein", override)
  local held = {}
  for _, h in ipairs(reservation_held) do
    held[#held + 1] = string.format("ring tile %d: held (reservation) -- %s", h.ring_position, h.reason)
  end

  -- Which kept candidates only got through BECAUSE of OVERRIDE (handoff
  -- review, 2026-09-30): recording must happen only once, only for a real
  -- (non-dry) run, and only if a tile that actually needed the override was
  -- actually designated successfully below -- never merely because OVERRIDE
  -- was passed.
  local override_candidates = {}
  if override ~= nil then
    for _, c in ipairs(kept_candidates) do
      if reservations_mod.override_needed({{x = c.x, y = c.y, z = c.z}}, res_id, "mine_vein") then
        override_candidates[#override_candidates + 1] = c
      end
    end
  end

  local results = {}
  for _, c in ipairs(kept_candidates) do
    local r = apply_single_cell('dig', 'd', c.x, c.y, c.z, dry, 'Tiles designated for digging', 'mine')
    results[#results + 1] = {
      ring_position = c.ring_position,
      mineral_name = c.mineral_name,
      dry_run = dry,
      ok = r.ok,
      problems = r.problems,
      error = nn(r.error),
      stats = (r.stats and next(r.stats)) and r.stats or {},
    }
    if not dry and r.ok then
      for _, oc in ipairs(override_candidates) do
        if oc == c then
          reservations_mod.record_override(res_id, "construction.mine-vein", "mine_vein", override)
          override_candidates = {}  -- record at most once per call
          break
        end
      end
    end
  end

  return {
    zone_id = b.id,
    boundary_ring_tiles = #ring,
    ore_tiles_found = #candidates,
    already_open = already_open,
    refused = refused,
    held = held,
    dry_run = dry,
    results = results,
  }
end

-- ---------------------------------------------------------------------------
-- Material choice: resolves the numeric (building_type, subtype) for a
-- construction KIND and delegates to building.lua's own
-- building_filters_and_gaps/apply_material_filters (see header, MATERIAL
-- CHOICE). Constructions have no `custom` (unlike a Custom workshop), so
-- cust is always nil/-1 here.
-- ---------------------------------------------------------------------------

-- Returns btype, sub (numbers), err. [reasoned, not verified live -- see
-- header]: df.construction_type is assumed bidirectional, same as every
-- other DFHack enum table this codebase already reads both ways
-- (building.lua's enum_name).
local function construction_type_numbers(k)
  local ok_bt, btype = pcall(function() return df.building_type.Construction end)
  if not ok_bt or btype == nil then
    return nil, nil, "df.building_type.Construction is not available"
  end
  if k.subtype == nil or k.subtype == NULL then
    return btype, nil, nil
  end
  local ok_sub, sub = pcall(function() return df.construction_type[k.subtype] end)
  if not ok_sub or sub == nil then
    return nil, nil, "could not resolve construction subtype '" .. tostring(k.subtype)
      .. "' back to a number via df.construction_type"
  end
  return btype, sub, nil
end

-- ---------------------------------------------------------------------------
-- Guards: keeps_access, item_present
--
-- handoffs/2026-09-28-keeps-access-guard.md, building on
-- research/2026-09-28-job-dependency-graph.md section 4.2: a guard is a
-- closed, data-listed predicate over the world, evaluated PER TARGET,
-- JOINTLY OVER THE WHOLE STEP, returning pass/hold/unknown -- never
-- defaulting to pass on a read failure. A `held` target is structurally
-- different from a `refused` one: `refused` means "this input is wrong, fix
-- your call"; `held` means "this input is fine, but designating it now would
-- cause a specific, named harm, try again once that changes." Both a dry
-- run and a real run report holds identically (guards read live world state,
-- never dry/real branching); only actually-held targets are skipped, the
-- rest of the step proceeds normally.
--
-- OUT OF SCOPE HERE (per the handoff): the `from_step`/explicit-targets
-- refactor (the "doorway hazard" -- `build` still treats every open ring
-- tile as a candidate); `dfqueue`/project/step records of any kind; a third
-- guard kind or attaching either guard to a different tool. These guards
-- are pure tool-layer refusals with no persistent record beyond the
-- `held`/`refused` response shape below.
-- ---------------------------------------------------------------------------

local ORTHOGONAL_OFFSETS = {
  {dx = 0, dy = -1}, {dx = 1, dy = 0}, {dx = 0, dy = 1}, {dx = -1, dy = 0},
}

local function guard_key(x, y, z) return x .. "," .. y .. "," .. z end

-- ---- item_present (haul-before-seal) ---------------------------------------
--
-- Working.md's boulder-yield finding: "a build step must never proceed
-- while an un-hauled ore/valuable item sits on its target tile." No open
-- technical question, per the handoff; this is the simpler of the two
-- guards.
--
-- Duplicated three-flag ownership check (trader/garbage_collect/removed),
-- the same one df-overseer-well.lua's is_fort_owned_item and this file's own
-- item_is_available (above) already use, file-local in all three -- not
-- reqscript'd, matching this file's own established duplication policy
-- (header: "MATERIAL CHOICE").

local function is_fort_owned_item_flags(item)
  local ok_f, f = pcall(function() return item.flags end)
  if not ok_f or not f then return nil, "could not read item.flags" end
  local ok_t, trader = pcall(function() return f.trader end)
  local ok_g, gc = pcall(function() return f.garbage_collect end)
  local ok_r, rm = pcall(function() return f.removed end)
  if not (ok_t and ok_g and ok_r) then
    return nil, "could not read item.flags.trader/garbage_collect/removed"
  end
  return not trader and not gc and not rm
end

-- Returns {item_type = "..."} if a fort-owned item sits on (x, y, z); false
-- if none does; nil, reason if the scan itself could not be trusted (this
-- is the guard's own "unknown" case -- never silently "false" on a read
-- failure).
local function item_present_at(x, y, z)
  local ok_all, all_items = pcall(function() return df.global.world.items.all end)
  if not ok_all or not all_items then
    return nil, "world.items.all could not be read"
  end
  local unreadable = 0
  for _, item in ipairs(all_items) do
    local ok_pos, ix, iy, iz = pcall(dfhack.items.getPosition, item)
    if ok_pos and ix ~= nil and ix == x and iy == y and iz == z then
      local owned, oerr = is_fort_owned_item_flags(item)
      if owned == nil then
        unreadable = unreadable + 1
      elseif owned then
        local ok_t, tname = pcall(function() return df.item_type[item:getType()] end)
        return {item_type = ok_t and tname or "unknown_item"}
      end
    end
  end
  if unreadable > 0 then
    return nil, unreadable .. " item(s) on this tile could not be classified"
  end
  return false
end

-- Runs item_present over every candidate target (never a coordinate in the
-- reason, per this repo's coordinate rule -- names the item instead).
-- Returns (held, kept): `held` a list of {ring_position, reason}; `kept` the
-- candidates the guard did not hold, in original order.
local function apply_item_present_guard(candidates)
  local held, kept = {}, {}
  for _, c in ipairs(candidates) do
    local found, err = item_present_at(c.x, c.y, c.z)
    if found == nil then
      held[#held + 1] = {ring_position = c.ring_position,
        reason = "could not confirm whether an item sits here (" .. tostring(err)
          .. "); holding rather than guessing"}
    elseif found then
      held[#held + 1] = {ring_position = c.ring_position,
        reason = "an unhauled " .. tostring(found.item_type) .. " sits on this tile; haul it before sealing"}
    else
      kept[#kept + 1] = c
    end
  end
  return held, kept
end

-- ---- keeps_access -----------------------------------------------------
--
-- research/2026-09-28-job-dependency-graph.md section 5.1's flagged open
-- question ("what step 6 needs that does not exist today") and section 7
-- point 1: whether df-overseer-reachability.lua's tri-state helper can
-- answer a HYPOTHETICAL ("if these tiles became walls, is this tile still
-- reachable") without mutating the map.
--
-- READ IN FULL FOR THIS HANDOFF, ANSWER: NO. Every exported function there
-- (resolve_group, reachable_between, group_matches) resolves against the
-- world's OWN CURRENT dfhack.maps.getWalkableGroup cache -- there is no
-- parameter anywhere in that file for "pretend tile X is a wall", and no
-- pathfind-with-a-hypothetical-obstacle call exists in this codebase at
-- all. Answering the hypothetical for real would mean actually building the
-- wall, re-reading, and deconstructing the ones that fail (the handoff's
-- option (b)) -- which contradicts this very file's own header discipline
-- ("ORDER IS ENFORCED BY WHAT `build` READS, NOT BY BOOKKEEPING" -- never
-- mutate the map just to find out). So this guard takes option (a): a
-- narrower, conservative check with NO pathfinding hypothetical at all, and
-- no reqscript of df-overseer-reachability.lua.
--
-- THE CHECK: for every exposed, not-hidden, still-unmined (WALL-shaped) ore/
-- gem tile orthogonally adjacent to one of this step's own build targets,
-- read that ore tile's own four orthogonal neighbours live. If at least one
-- of them is open (not hidden, shape ~= WALL) and is NOT one of this step's
-- own targets, the ore stays reachable through it regardless of what this
-- step does: pass. If every currently-open orthogonal neighbour of that ore
-- tile IS one of this step's targets, building all of them would seal it:
-- hold just enough of them (the deterministic tie-break below) to leave one
-- approach open, per the handoff's "hold only the tiles needed to keep at
-- least one approach open".
--
-- WHY ORTHOGONAL ONLY, NOT ALL 8 NEIGHBOURS: research/2026-09-28's own
-- section 7 point 2 flags "whether a miner can dig from a diagonal
-- neighbour" as UNVERIFIED. This guard never relies on that assumption
-- either way: it only ever trusts, or proposes holding, an orthogonal
-- neighbour, never a diagonal one.
--
-- WHY A HIDDEN NEIGHBOUR IS NEVER TREATED AS AN ESCAPE ROUTE OR AS UNKNOWN:
-- the no-armok rule (CLAUDE.md) -- a hidden tile is simply excluded from the
-- approach count (neither "open" nor grounds for "unknown"), the same
-- `hidden_tiles: ignore` the design's own yaml sketch states.
--
-- DELIBERATE NARROWING versus the design's yaml sketch, stated per the
-- handoff's "state your reasoning": the design's `protects:` list also
-- names `pending_designations` (a dig/channel/smooth/engrave queued
-- elsewhere, mirroring suspendmanager's ERASE_DESIGNATION). This guard does
-- not track pending designations -- that needs the project/step model a
-- parallel stream owns (handoffs/2026-09-28-dfqueue-project-step-schema.md),
-- not a tool-layer read. Only the ore/gem case this handoff asked for is
-- built here.

-- Tri-state: true (open, safe to trust or to hold-avoid), false (not open:
-- still a wall), nil (unreadable -- distinct from hidden, which is excluded
-- entirely, never counted as "unknown").
local function tile_open(hooks, x, y, z)
  local t = hooks.tile_read(x, y, z)
  if not t.ok then return nil, "unreadable" end
  if t.hidden then return nil, "hidden" end
  return t.shape ~= df.tiletype_shape.WALL, nil
end

-- All exposed, not-hidden, still-WALL ore/gem tiles orthogonally adjacent to
-- ANY of `candidates`, deduped by coordinate: "jointly over the step" means
-- never evaluating the same ore tile once per neighbouring target.
local function protected_ore_tiles(hooks, candidates)
  local seen, ore = {}, {}
  for _, c in ipairs(candidates) do
    for _, off in ipairs(ORTHOGONAL_OFFSETS) do
      local ox, oy, oz = c.x + off.dx, c.y + off.dy, c.z
      local k = guard_key(ox, oy, oz)
      if not seen[k] then
        local t = hooks.tile_read(ox, oy, oz)
        if t.ok and not t.hidden and t.shape == df.tiletype_shape.WALL then
          local rec = hooks.decode_vein_tile(ox, oy, oz)
          if rec.vein_status == "ore_or_gem" then
            seen[k] = true
            ore[#ore + 1] = {x = ox, y = oy, z = oz, mineral_name = rec.mineral_name}
          end
        end
      end
    end
  end
  return ore
end

-- Runs keeps_access over `candidates` (the targets that survived
-- item_present -- see build_construction for why item_present runs first).
-- Returns (held, kept) in the same shape apply_item_present_guard does.
local function apply_keeps_access_guard(hooks, candidates)
  local target_set = {}
  for _, c in ipairs(candidates) do target_set[guard_key(c.x, c.y, c.z)] = c end

  local ore_tiles = protected_ore_tiles(hooks, candidates)
  local held_keys, held_reason = {}, {}

  for _, ore in ipairs(ore_tiles) do
    local approaches = {}
    local any_open_free = false
    local unknown_here = false
    for _, off in ipairs(ORTHOGONAL_OFFSETS) do
      local nx, ny, nz = ore.x + off.dx, ore.y + off.dy, ore.z
      local open, why = tile_open(hooks, nx, ny, nz)
      if open == nil then
        if why == "unreadable" then unknown_here = true end
        -- hidden: silently excluded, per the no-armok rule (header above)
      elseif open then
        local nk = guard_key(nx, ny, nz)
        if target_set[nk] then
          if not held_keys[nk] then approaches[#approaches + 1] = nk end
        else
          any_open_free = true
        end
      end
    end
    if not any_open_free and unknown_here then
      -- Could not fully confirm this ore tile's escape route: hold every
      -- target-set neighbour found so far rather than guess it stays
      -- reachable (three-valued rule: unknown never defaults to pass).
      for _, nk in ipairs(approaches) do
        if not held_keys[nk] then
          held_keys[nk] = true
          held_reason[nk] = "could not confirm every neighbour of exposed "
            .. tostring(ore.mineral_name) .. " ore; holding rather than guessing it stays reachable"
        end
      end
    elseif not any_open_free and #approaches > 0 then
      -- Every currently-open orthogonal neighbour of this ore tile is one of
      -- this step's own targets: hold the first one found, in the fixed
      -- N,E,S,W scan order (ORTHOGONAL_OFFSETS' own order) -- this guard's
      -- deterministic tie-break, since every approach considered here is
      -- already orthogonal-only (see header on diagonal mining). The rest
      -- of this ore tile's neighbouring targets proceed.
      local nk = approaches[1]
      held_keys[nk] = true
      held_reason[nk] = "would cut off exposed " .. tostring(ore.mineral_name)
        .. " ore that is still to be worked"
    end
  end

  local held, kept = {}, {}
  for _, c in ipairs(candidates) do
    local nk = guard_key(c.x, c.y, c.z)
    if held_keys[nk] then
      held[#held + 1] = {ring_position = c.ring_position, reason = held_reason[nk]}
    else
      kept[#kept + 1] = c
    end
  end
  return held, kept
end

-- ---- entrance (handoffs/2026-10-01-entrances-get-doors.md) ----------------
--
-- See the file header for the full reasoning. This is a THIRD guard, in the
-- same held/kept shape as item_present/keeps_access, but with one
-- difference: finding ZERO entrances is not a per-tile hold, it is a
-- whole-call refusal (there is no safe subset of targets to proceed with
-- if the room would end up with no way out at all).

-- Classifies a ring tile against the zone's own footprint rectangle `b`
-- (b.x1/x2/y1/y2 -- the same fields df-overseer-surface.lua's own
-- ring_tiles/footprint_tiles already read off the real building_civzonest).
-- Returns inside_xyz, outside_xyz for a straight-edge ring tile (the single
-- orthogonal neighbour that lies inside the footprint, and the one that
-- continues straight on past the ring); nil, nil for a ring CORNER, which
-- has no neighbour inside the footprint at all (both its orthogonal
-- neighbours are themselves other ring tiles) and so can never be "the way
-- out" by this definition.
local function ring_edge_neighbours(b, x, y, z)
  if x >= b.x1 and x <= b.x2 and y == b.y1 - 1 then
    return {x, b.y1, z}, {x, y - 1, z}
  elseif x >= b.x1 and x <= b.x2 and y == b.y2 + 1 then
    return {x, b.y2, z}, {x, y + 1, z}
  elseif y >= b.y1 and y <= b.y2 and x == b.x1 - 1 then
    return {b.x1, y, z}, {x - 1, y, z}
  elseif y >= b.y1 and y <= b.y2 and x == b.x2 + 1 then
    return {b.x2, y, z}, {x + 1, y, z}
  end
  return nil, nil
end

-- The fort's main walkable group id (the group most citizens are in),
-- reused from df-overseer-connectivity.lua's own exported
-- get_connectivity_report rather than re-deriving it from warn-stranded
-- here. 0 is DFHack's own "not walkable" sentinel (df-overseer-
-- reachability.lua's own header), never a real group -- treated the same as
-- a missing report: unknown, not a guessed group.
local function main_group_id()
  local ok, report = pcall(connectivity_mod.get_connectivity_report)
  if not ok or not report or report.main_group_id == nil or report.main_group_id == 0 then
    return nil, "could not read the fort's main walkable group from connectivity.report"
  end
  return report.main_group_id
end

-- Every tile in `candidates` (a list of {ring_position, x, y, z}) whose
-- outside neighbour (per ring_edge_neighbours) belongs to `main_group`,
-- per df-overseer-reachability.lua's own group_matches (never a new
-- pathfind -- see that file's header on why a hypothetical path check does
-- not exist in this codebase). A corner (ring_edge_neighbours returns nil)
-- is never an entrance. Returns a list of {ring_position, x, y, z}, in the
-- same order `candidates` was given.
local function find_entrances(b, candidates, main_group)
  local entrances = {}
  for _, c in ipairs(candidates) do
    local inside, outside = ring_edge_neighbours(b, c.x, c.y, c.z)
    if inside and outside then
      local matched = reachability_mod.group_matches(outside[1], outside[2], outside[3], {[main_group] = true})
      if matched then
        entrances[#entrances + 1] = {ring_position = c.ring_position, x = c.x, y = c.y, z = c.z}
      end
    end
  end
  return entrances
end

-- Runs find_entrances over `candidates`, splitting them into (held, kept,
-- entrances) -- `entrances` kept separately (not just folded into `held`)
-- because build_door needs the coordinates, while build_construction only
-- needs the held/kept split. `candidates` must already be the OPEN ring
-- tiles a call could actually touch (same precondition build_construction's
-- own first loop already establishes).
local function apply_entrance_guard(b, candidates, main_group)
  local entrances = find_entrances(b, candidates, main_group)
  local entrance_set = {}
  for _, e in ipairs(entrances) do entrance_set[guard_key(e.x, e.y, e.z)] = true end
  local held, kept = {}, {}
  for _, c in ipairs(candidates) do
    if entrance_set[guard_key(c.x, c.y, c.z)] then
      held[#held + 1] = {ring_position = c.ring_position,
        reason = "this zone's own entrance; building here would seal the room"}
    else
      kept[#kept + 1] = c
    end
  end
  return held, kept, entrances
end

-- Shared by build_construction and build_door: every ring tile's live
-- shape, split into (candidates, refused) -- a tile still shaped WALL or
-- unreadable/hidden is `refused` by name, never guessed open, same
-- discipline build_construction's own loop already used before this was
-- pulled out into its own function.
local function collect_open_ring_candidates(hooks, ring)
  local candidates, refused = {}, {}
  for i, xyz in ipairs(ring) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local t = hooks.tile_read(x, y, z)
    if not t.ok then
      refused[#refused + 1] = string.format("ring tile %d: could not read its shape (%s); refusing to guess", i, t.err)
    elseif t.hidden then
      refused[#refused + 1] = string.format("ring tile %d: hidden; refusing to guess it is open", i)
    elseif t.shape == df.tiletype_shape.WALL then
      refused[#refused + 1] = string.format("ring tile %d: still a wall, not yet mined; run mine-vein first", i)
    else
      candidates[#candidates + 1] = {ring_position = i, x = x, y = y, z = z}
    end
  end
  return candidates, refused
end

-- ---------------------------------------------------------------------------
-- build ZONE_ID KIND [DRY_RUN]
-- ---------------------------------------------------------------------------

-- Resolves KIND to a quickfort key through df-overseer-building.lua's own
-- exported list_kinds (never re-implemented): exact, case-insensitive match
-- on token or subtype name, restricted to type "Construction" -- the
-- generalisable hook the header promises (Floor, Ramp, UpStair, ... cost no
-- new code here, only a different KIND string).
local function resolve_construction_kind(kind_name)
  local kinds, err = building_mod.list_kinds(kind_name)
  if not kinds then return nil, "could not read building kinds: " .. tostring(err) end
  local q = tostring(kind_name or ""):lower()
  local matches = {}
  for _, k in ipairs(kinds) do
    if k.type == "Construction" then
      local subtype = (k.subtype ~= NULL) and tostring(k.subtype) or nil
      if k.token:lower() == q or (subtype and subtype:lower() == q) then
        matches[#matches + 1] = k
      end
    end
  end
  if #matches == 0 then
    local hints = {}
    for _, k in ipairs(kinds) do
      if k.type == "Construction" then hints[#hints + 1] = k.token end
    end
    local msg = "unknown construction kind: " .. tostring(kind_name)
    if #hints > 0 then msg = msg .. "; construction kinds this install knows: " .. table.concat(hints, ", ") end
    return nil, msg
  end
  if #matches > 1 then
    return nil, "ambiguous construction kind " .. tostring(kind_name) .. ": ambiguity this tool did not expect"
  end
  return matches[1]
end

-- RES_ID/OVERRIDE (handoffs/2026-09-30-reservation-holding.md items 2-3):
-- k.token is df-overseer-building.lua's own generic per-subtype token
-- (e.g. "Wall") -- the identical domain df-overseer-blueprint.lua's
-- template_allowed_kinds derives a template's #build cells through, so no
-- vocabulary mismatch here (unlike df-overseer-workshop.lua's own local
-- kind keys, see that file's comment).
function build_construction(zone_id, kind_name, dry_run, material_choice, res_id, override)
  if override ~= nil and res_id == nil then
    return {error = "OVERRIDE requires RES_ID"}
  end
  local k, kerr = resolve_construction_kind(kind_name)
  if not k then return {error = kerr} end
  local hooks, herr = surface_hooks()
  if not hooks then return {error = herr} end
  local b, err = hooks.find_zone(zone_id)
  if not b then return {error = err} end
  local ring = hooks.ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local dry = truthy_dry_run(dry_run)

  local candidates, refused = collect_open_ring_candidates(hooks, ring)

  -- Entrance guard (handoffs/2026-10-01-entrances-get-doors.md), run before
  -- any other guard: a zone with no detectable entrance among its open ring
  -- tiles is refused outright (never designate anything that could leave
  -- the room with no way out at all), and any ring tile that IS the
  -- entrance is pulled out of the candidate set before item_present/
  -- keeps_access ever see it -- see apply_entrance_guard's own header.
  local main_group, mg_err = main_group_id()
  if not main_group then
    return {error = "could not confirm this zone's entrance (" .. tostring(mg_err)
      .. "); refusing rather than risk sealing the room"}
  end
  local entrance_held, after_entrance, entrances_found = apply_entrance_guard(b, candidates, main_group)
  if #entrances_found == 0 then
    return {error = "zone " .. b.id .. " has no detectable entrance among its open ring tiles; "
      .. "refusing to build here, this would seal the room"}
  end

  -- Guards, in this order (per the handoff: item_present is the simpler
  -- guard with no open technical question; run it first for an early,
  -- cheap hold before keeps_access's more involved neighbour scan). Both
  -- read live world state regardless of `dry`, so a dry run and a real run
  -- report holds identically -- a hold is not a run-level failure (`ok`
  -- stays true below, `results` simply omits the held targets).
  local reservation_held, after_reservation = apply_reservation_guard(after_entrance, res_id, k.token, override)
  -- Which of the candidates that passed the reservation guard only did so
  -- BECAUSE of OVERRIDE (handoff review, 2026-09-30) -- computed here,
  -- before the other two guards or any designation, so a later guard
  -- dropping one is not mistaken for it never having needed the override.
  local override_candidates = {}
  if override ~= nil then
    for _, c in ipairs(after_reservation) do
      if reservations_mod.override_needed({{x = c.x, y = c.y, z = c.z}}, res_id, k.token) then
        override_candidates[#override_candidates + 1] = c
      end
    end
  end
  local item_held, after_item_present = apply_item_present_guard(after_reservation)
  local access_held, final_candidates = apply_keeps_access_guard(hooks, after_item_present)

  local held_records = {}
  for _, h in ipairs(entrance_held) do
    held_records[#held_records + 1] = {ring_position = h.ring_position, guard = "entrance", reason = h.reason}
  end
  for _, h in ipairs(reservation_held) do
    held_records[#held_records + 1] = {ring_position = h.ring_position, guard = "reservation", reason = h.reason}
  end
  for _, h in ipairs(item_held) do
    held_records[#held_records + 1] = {ring_position = h.ring_position, guard = "item_present", reason = h.reason}
  end
  for _, h in ipairs(access_held) do
    held_records[#held_records + 1] = {ring_position = h.ring_position, guard = "keeps_access", reason = h.reason}
  end
  table.sort(held_records, function(a, b) return a.ring_position < b.ring_position end)
  local held = {}
  for _, h in ipairs(held_records) do
    held[#held + 1] = string.format("ring tile %d: held (%s) -- %s", h.ring_position, h.guard, h.reason)
  end

  -- Requirements/material breakdown, and (2026-10-01, see header MATERIAL
  -- CHOICE) the real class write into buildingplan's own filter, bracketed
  -- around every real (non-dry) build call below so it applies to the whole
  -- step and is restored once the step finishes -- never per tile, since
  -- every ring tile of one `build` call shares the same (building_type,
  -- subtype).
  local ctype, csub, tnerr = construction_type_numbers(k)
  local req, mgaps
  if tnerr then
    req = {building_material = {error = tnerr, filters = {}}}
    mgaps = {tnerr}
  else
    req, mgaps = building_mod.building_filters_and_gaps(ctype, csub, nil, material_choice, k.token)
  end
  local filter_recs = {}
  if req.building_material and req.building_material.filters then
    for _, rec in ipairs(req.building_material.filters) do
      if rec.filter_material_names then filter_recs[#filter_recs + 1] = rec end
    end
  end
  local mf_report, mf_restore
  if not dry and not tnerr and #filter_recs > 0 and req.building_material.buildingplan_enabled == true then
    mf_report, mf_restore = building_mod.apply_material_filters(ctype, csub, nil, filter_recs)
  end

  local results = {}
  for _, c in ipairs(final_candidates) do
    local r = apply_single_cell('build', k.key, c.x, c.y, c.z, dry, 'Buildings designated', 'build')
    results[#results + 1] = {
      ring_position = c.ring_position,
      dry_run = dry,
      ok = r.ok,
      problems = r.problems,
      error = nn(r.error),
      stats = (r.stats and next(r.stats)) and r.stats or {},
    }
    if not dry and r.ok then
      for _, oc in ipairs(override_candidates) do
        if oc == c then
          reservations_mod.record_override(res_id, "construction.build", k.token, override)
          override_candidates = {}  -- record at most once per call
          break
        end
      end
    end
  end

  if mf_restore then
    mf_report.restored = mf_restore()
  end

  return {
    zone_id = b.id,
    kind = {token = k.token, key = k.key, label = k.label, type = k.type, subtype = k.subtype},
    boundary_ring_tiles = #ring,
    open_tiles_found = #candidates,
    entrances_found = #entrances_found,
    refused = refused,
    held = held,
    dry_run = dry,
    material_report = req.building_material,
    material_gaps = mgaps,
    material_filter = mf_report,
    results = results,
  }
end

-- ---------------------------------------------------------------------------
-- door ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]
--
-- handoffs/2026-10-01-entrances-get-doors.md task 3: see the file header
-- ("Chosen over...") for why this is a sibling verb here rather than a
-- building.build Door call. Resolves the Door kind through
-- df-overseer-building.lua's own list_kinds (never a hard-coded building
-- number), finds this zone's entrance(s) via the exact same find_entrances
-- every call build_construction now runs, and places one Door at each --
-- never anywhere else on the ring. MATERIAL_CHOICE is deliberately not
-- threaded through here (see header); buildingplan's own default applies.
-- ---------------------------------------------------------------------------

local function resolve_door_kind()
  local kinds, err = building_mod.list_kinds("Door")
  if not kinds then return nil, "could not read building kinds: " .. tostring(err) end
  for _, k in ipairs(kinds) do
    if k.token == "Door" then return k end
  end
  return nil, "this install's building kinds have no Door entry"
end

function build_door(zone_id, dry_run, res_id, override)
  if override ~= nil and res_id == nil then
    return {error = "OVERRIDE requires RES_ID"}
  end
  local k, kerr = resolve_door_kind()
  if not k then return {error = kerr} end
  local hooks, herr = surface_hooks()
  if not hooks then return {error = herr} end
  local b, err = hooks.find_zone(zone_id)
  if not b then return {error = err} end
  local ring = hooks.ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local dry = truthy_dry_run(dry_run)

  local candidates, refused = collect_open_ring_candidates(hooks, ring)

  local main_group, mg_err = main_group_id()
  if not main_group then
    return {error = "could not confirm this zone's entrance (" .. tostring(mg_err)
      .. "); refusing rather than guess where to put a door"}
  end
  local entrances = find_entrances(b, candidates, main_group)
  if #entrances == 0 then
    return {error = "zone " .. b.id .. " has no detectable entrance among its open ring tiles; "
      .. "refusing to place a door anywhere"}
  end

  -- Same reservation/item_present guards build_construction runs, applied
  -- only over the entrance tiles themselves (never the rest of the ring --
  -- door only ever targets an entrance).
  local reservation_held, after_reservation = apply_reservation_guard(entrances, res_id, k.token, override)
  local override_candidates = {}
  if override ~= nil then
    for _, c in ipairs(after_reservation) do
      if reservations_mod.override_needed({{x = c.x, y = c.y, z = c.z}}, res_id, k.token) then
        override_candidates[#override_candidates + 1] = c
      end
    end
  end
  local item_held, final_candidates = apply_item_present_guard(after_reservation)

  local held_records = {}
  for _, h in ipairs(reservation_held) do
    held_records[#held_records + 1] = {ring_position = h.ring_position, guard = "reservation", reason = h.reason}
  end
  for _, h in ipairs(item_held) do
    held_records[#held_records + 1] = {ring_position = h.ring_position, guard = "item_present", reason = h.reason}
  end
  table.sort(held_records, function(a, c) return a.ring_position < c.ring_position end)
  local held = {}
  for _, h in ipairs(held_records) do
    held[#held + 1] = string.format("ring tile %d: held (%s) -- %s", h.ring_position, h.guard, h.reason)
  end

  local results = {}
  for _, c in ipairs(final_candidates) do
    local r = apply_single_cell('build', k.key, c.x, c.y, c.z, dry, 'Buildings designated', 'door')
    results[#results + 1] = {
      ring_position = c.ring_position,
      dry_run = dry,
      ok = r.ok,
      problems = r.problems,
      error = nn(r.error),
      stats = (r.stats and next(r.stats)) and r.stats or {},
    }
    if not dry and r.ok then
      for _, oc in ipairs(override_candidates) do
        if oc == c then
          reservations_mod.record_override(res_id, "construction.door", k.token, override)
          override_candidates = {}  -- record at most once per call
          break
        end
      end
    end
  end

  return {
    zone_id = b.id,
    kind = {token = k.token, key = k.key, label = k.label},
    boundary_ring_tiles = #ring,
    entrances_found = #entrances,
    refused = refused,
    held = held,
    dry_run = dry,
    results = results,
  }
end

-- ---------------------------------------------------------------------------
-- audit [ZONE_ID] [DRY_RUN]
--
-- handoffs/2026-10-01-entrances-get-doors.md task 4: the backstop for walls
-- designated BEFORE this entrance guard existed (exactly the 2026-09-28
-- office walls). See the file header for the full reasoning: classifies
-- every ring tile as built/planned/open, asks find_entrances whether an
-- entrance would still exist once every PLANNED tile also finishes, and (a
-- real, non-dry call) suspends just enough of the at-risk planned tiles'
-- own jobs to keep one open, via job.flags.suspend -- the exact hand
-- stopgap used live on building 22, 2026-09-28.
-- ---------------------------------------------------------------------------

-- True/false/nil (unknown), per the same bld:getBuildStage()==
-- bld:getMaxBuildStage() live-verified check df-overseer-building.lua's
-- kind_previously_built and df-overseer-zone.lua's content_row already use.
-- A tile with no building at all, or a building that is not a Construction,
-- is simply "no planned construction here" (false), never "unknown".
local function planned_construction_at(x, y, z)
  local ok_b, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(x, y, z))
  if not ok_b or not bld then return false, nil end
  local ok_t, btype = pcall(function() return bld:getType() end)
  if not ok_t or btype ~= df.building_type.Construction then return false, nil end
  local ok_s, stage = pcall(function() return bld:getBuildStage() end)
  local ok_m, max_stage = pcall(function() return bld:getMaxBuildStage() end)
  if not (ok_s and ok_m) then return nil, bld end
  if stage >= max_stage then return false, nil end  -- already finished: this is `built`, not `planned`
  return true, bld
end

-- The job attached to a planned building, via the same
-- utils.listpairs(df.global.world.jobs.list) + dfhack.job.getHolder
-- traversal df-overseer-stuckjobs.lua's own get_stuck_jobs already uses
-- live (see that file's header for the confirmation). nil if no job is
-- currently attached (a genuinely idle planned building, or a read failure)
-- -- never guessed.
local function job_for_building(bld)
  for _, job in utils.listpairs(df.global.world.jobs.list) do
    local ok_h, holder = pcall(dfhack.job.getHolder, job)
    if ok_h and holder == bld then return job end
  end
  return nil
end

-- One zone's audit: built/planned/open ring tiles, whether an entrance
-- would survive every planned tile completing, and (if not) which planned
-- tile(s) are the critical ones (the same deterministic first-in-ring-order
-- tie-break keeps_access already established).
local function audit_one_zone(hooks, b, main_group, dry)
  local ring = hooks.ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {zone_id = b.id, error = "boundary ring is " .. #ring .. " tiles, over this tool's "
      .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end

  local open_tiles, planned_tiles, built_tiles, unknown_tiles = {}, {}, {}, {}
  local planned_by_key = {}
  for i, xyz in ipairs(ring) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local t = hooks.tile_read(x, y, z)
    if not t.ok or t.hidden then
      unknown_tiles[#unknown_tiles + 1] = i
    elseif t.shape == df.tiletype_shape.WALL then
      built_tiles[#built_tiles + 1] = {ring_position = i, x = x, y = y, z = z}
    else
      local planned, bld = planned_construction_at(x, y, z)
      if planned == nil then
        unknown_tiles[#unknown_tiles + 1] = i
      elseif planned then
        local rec = {ring_position = i, x = x, y = y, z = z, building_id = bld.id, bld = bld}
        planned_tiles[#planned_tiles + 1] = rec
        planned_by_key[guard_key(x, y, z)] = rec
      else
        open_tiles[#open_tiles + 1] = {ring_position = i, x = x, y = y, z = z}
      end
    end
  end

  local entrances_now = find_entrances(b, open_tiles, main_group)
  -- Would an entrance survive once every PLANNED tile also completes? Only
  -- the OPEN tiles (neither built nor planned) could still serve as one.
  local would_strand = #entrances_now == 0

  -- Of the planned tiles, which would THEMSELVES have qualified as the
  -- entrance had they stayed open -- i.e. finishing them is what removes
  -- the last way out. Only reported/suspended when the room would actually
  -- be stranded; a planned tile that happens to sit on a structurally
  -- viable entrance spot is not itself a problem if another real entrance
  -- survives regardless.
  local at_risk, suspended = {}, {}
  if would_strand then
    local critical = find_entrances(b, planned_tiles, main_group)
    table.sort(critical, function(a, c) return a.ring_position < c.ring_position end)
    for _, c in ipairs(critical) do
      local rec = planned_by_key[guard_key(c.x, c.y, c.z)]
      at_risk[#at_risk + 1] = {ring_position = rec.ring_position, building_id = rec.building_id}
    end
    if not dry and #at_risk > 0 then
      -- Deterministic tie-break (keeps_access's own rule): suspending the
      -- FIRST at-risk tile (lowest ring_position) is enough to keep one
      -- approach open again; the rest are left alone.
      local target = at_risk[1]
      local target_rec = planned_by_key[guard_key(critical[1].x, critical[1].y, critical[1].z)]
      local job = job_for_building(target_rec.bld)
      if job then
        local ok_set = pcall(function() job.flags.suspend = true end)
        suspended[#suspended + 1] = {building_id = target.building_id, ok = ok_set == true}
      else
        suspended[#suspended + 1] = {building_id = target.building_id, ok = false,
          note = "no job currently attached to this building; could not suspend"}
      end
    end
  end

  return {
    zone_id = b.id,
    boundary_ring_tiles = #ring,
    built = #built_tiles,
    planned = #planned_tiles,
    open = #open_tiles,
    unknown_tiles = #unknown_tiles,
    would_strand = would_strand,
    at_risk = at_risk,
    dry_run = dry,
    suspended = suspended,
  }
end

function audit_constructions(zone_id, dry_run)
  local hooks, herr = surface_hooks()
  if not hooks then return {error = herr} end

  local zones = {}
  if zone_id ~= nil then
    local b, err = hooks.find_zone(zone_id)
    if not b then return {error = err} end
    zones = {b}
  else
    local ok_all, all = pcall(function() return df.global.world.buildings.all end)
    if not ok_all or not all then return {error = "could not read df.global.world.buildings.all"} end
    for _, bld in ipairs(all) do
      local ok_i, is_zone = pcall(function() return df.building_civzonest:is_instance(bld) end)
      if ok_i and is_zone then zones[#zones + 1] = bld end
    end
  end

  local main_group, mg_err = main_group_id()
  if not main_group then
    return {error = "could not read the fort's main walkable group (" .. tostring(mg_err) .. ")"}
  end

  local dry = truthy_dry_run(dry_run)
  local zone_reports = {}
  for _, b in ipairs(zones) do
    zone_reports[#zone_reports + 1] = audit_one_zone(hooks, b, main_group, dry)
  end
  return {zones_checked = #zones, dry_run = dry, zones = zone_reports}
end

-- ---------------------------------------------------------------------------
-- CLI
-- ---------------------------------------------------------------------------

if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

local function emit(result)
  print(encode(result))
end

if cmd == "mine-vein" then
  if not args[2] then
    print("usage: df-overseer-construction mine-vein ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]")
  else
    emit(mine_vein(args[2], args[3], args[4], args[5]))
  end
elseif cmd == "build" then
  if not (args[2] and args[3]) then
    print("usage: df-overseer-construction build ZONE_ID KIND [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]")
  else
    emit(build_construction(args[2], args[3], args[4], args[5], args[6], args[7]))
  end
elseif cmd == "door" then
  if not args[2] then
    print("usage: df-overseer-construction door ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]")
  else
    emit(build_door(args[2], args[3], args[4], args[5]))
  end
elseif cmd == "audit" then
  emit(audit_constructions(args[2], args[3]))
else
  print("usage: df-overseer-construction mine-vein ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]")
  print("usage: df-overseer-construction build ZONE_ID KIND [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]")
  print("usage: df-overseer-construction door ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]")
  print("usage: df-overseer-construction audit [ZONE_ID] [DRY_RUN]")
end
