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

local json = require('json')
local surface_mod = reqscript('df-overseer-surface')
local building_mod = reqscript('df-overseer-building')
-- handoffs/2026-09-30-room-reservations.md decision 3: mine-vein and build
-- both hold (not refuse) a ring tile inside a reservation neither holds --
-- see apply_reservation_guard below, next to the other two guards.
local reservations_mod = reqscript('df-overseer-reservations')

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

  -- Guards, in this order (per the handoff: item_present is the simpler
  -- guard with no open technical question; run it first for an early,
  -- cheap hold before keeps_access's more involved neighbour scan). Both
  -- read live world state regardless of `dry`, so a dry run and a real run
  -- report holds identically -- a hold is not a run-level failure (`ok`
  -- stays true below, `results` simply omits the held targets).
  local reservation_held, after_reservation = apply_reservation_guard(candidates, res_id, k.token, override)
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
else
  print("usage: df-overseer-construction mine-vein ZONE_ID [DRY_RUN] [RES_ID] [OVERRIDE]")
  print("usage: df-overseer-construction build ZONE_ID KIND [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]")
end
