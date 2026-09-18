-- df-overseer-well.lua
--@module = true
--
-- handoffs/2026-09-17-water-and-industry-tools.md item 5: the user's
-- fallback plan if a Water Source zone does not let the founders drink.
-- A well needs no bridge and sidesteps the disputed getWalkableGroup-near-
-- ramps question entirely (research/2026-09-17-pool-reachability.md
-- CORRECTION note, §4 item 2): the draw point sits on the fort's own
-- interior floor, not out on the pool's own RAMP-shaped bank.
--
-- MECHANISM, verified from THIS install's own source this session,
-- `hack/scripts/internal/quickfort/build.lua`:
--   - `#build` symbol `l` places `df.building_type.Well`, gated by
--     `is_tile_empty_and_floor_adjacent`:
--       shape must be EMPTY or RAMP_TOP, AND `is_valid_tile_base` (not
--       hidden, `flow_size <= 1`, no building already there), AND at
--       least one of the 4 orthogonal neighbours is FLOOR-shaped.
--     Quoted/read directly, not guessed: this is exactly the rule the
--     handoff's own live-verification already named.
--   - `dfhack.buildings.getFiltersByType({}, df.building_type.Well, -1,
--     -1)` returns BLOCKS, BUCKET, CHAIN, TRAPPARTS (one each) --
--     re-confirmed live this session, matching the handoff's own figures
--     exactly.
--
-- THE TILE THIS RULE DESCRIBES, concretely: on this map, every pool's
-- water sits at z168 in RAMP-shaped tiles, with RAMP_TOP/AIR directly
-- above at z169 (`research/2026-09-17-pool-reachability.md`). A well's
-- own draw tile is that z169 RAMP_TOP -- `is_tile_empty_and_floor_adjacent`
-- itself says nothing about what's below, so this project's OWN domain
-- rule (this well must actually draw from real water, not just sit over
-- open air) is layered on top, exactly the way df-overseer-zone.lua's
-- is_water_source_tile and df-overseer-farm.lua's crop_validity each
-- layer a project rule over a looser quickfort placement rule: the tile
-- directly below (same x,y, z-1) must be revealed, not magma, and at
-- least 3/7 deep -- the wiki's own well depth requirement
-- (research/2026-09-17-pool-reachability.md §4, version-matched to this
-- exact install, v53.16: "at least 3/7 deep").
--
-- Usage: ./dfhack-run df-overseer-well find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-well build [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5
local MIN_WELL_DEPTH = 3

-- Mirrors quickfort's is_valid_tile_base (hack/scripts/internal/quickfort/
-- build.lua) -- same predicate df-overseer-farm.lua's valid_tile_base
-- already mirrors for the same reason ("validate against the game's own
-- rules rather than reimplementing them"), duplicated here rather than
-- reqscript'd since farm.lua's copy is a local (non-exported) function.
local function valid_tile_base(pos)
  local ok, flags, occupancy = pcall(dfhack.maps.getTileFlags, pos)
  if not ok or not flags then
    return false
  end
  if (flags.liquid_type == true or flags.liquid_type == df.tile_liquid.Magma)
      and flags.flow_size >= 1 then
    return false
  end
  return not flags.hidden and flags.flow_size <= 1 and occupancy.building == 0
end

local function is_floor_shape(x, y, z)
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return false
  end
  local ok_shape, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  return ok_shape and shape == df.tiletype_shape.FLOOR
end

local function is_floor_adjacent(x, y, z)
  return is_floor_shape(x + 1, y, z) or is_floor_shape(x - 1, y, z)
    or is_floor_shape(x, y + 1, z) or is_floor_shape(x, y - 1, z)
end

-- The tile directly below (x,y,z-1): revealed, not magma, flow_size >= 3
-- (the wiki's own well minimum depth). See header.
local function water_below(x, y, z)
  local below_z = z - 1
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, below_z)
  if not ok_vis or not visible then
    return false, nil
  end
  local ok_flags, flags = pcall(dfhack.maps.getTileFlags, xyz2pos(x, y, below_z))
  if not ok_flags or not flags then
    return false, nil
  end
  if flags.liquid_type == true or flags.liquid_type == df.tile_liquid.Magma then
    return false, nil
  end
  if not flags.flow_size or flags.flow_size < MIN_WELL_DEPTH then
    return false, nil
  end
  return true, {
    flow_size = flags.flow_size,
    stagnant = flags.water_stagnant or false,
    salt = flags.water_salt or false,
  }
end

-- Returns (ok, info). ok requires: revealed, shape EMPTY or RAMP_TOP,
-- valid_tile_base, floor-adjacent (quickfort's own well rule), AND real
-- water at least 3/7 deep directly beneath (this project's own domain
-- rule -- see header).
local function is_well_tile(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis or not visible then
    return false, nil
  end
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return false, nil
  end
  local ok_shape, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  if not ok_shape or (shape ~= df.tiletype_shape.EMPTY and shape ~= df.tiletype_shape.RAMP_TOP) then
    return false, nil
  end
  local pos = xyz2pos(x, y, z)
  if not valid_tile_base(pos) then
    return false, nil
  end
  if not is_floor_adjacent(x, y, z) then
    return false, nil
  end
  local has_water, water_info = water_below(x, y, z)
  if not has_water then
    return false, nil
  end
  return true, water_info
end

local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

-- Server-side only: ranked well-tile candidates (1x1 -- a well is always a
-- single tile), real coordinates kept. Shared by find_well/build_well, same
-- "one ranking implementation" guarantee every other df-overseer-*.lua
-- fused pair gives.
local function ranked_candidates(level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local candidates = {}
  for x = ax - radius, ax + radius do
    for y = ay - radius, ay + radius do
      local ok, water_info = is_well_tile(x, y, z)
      if ok then
        local dx, dy = x - ax, y - ay
        table.insert(candidates, {
          x = x, y = y,
          dist_to_anchor = math.sqrt(dx * dx + dy * dy),
          water_info = water_info,
        })
      end
    end
  end
  table.sort(candidates, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local chosen = {}
  for i = 1, math.min(MAX_RESULTS, #candidates) do
    table.insert(chosen, candidates[i])
  end
  return chosen, nil, z
end

-- Same is_fort_owned test as df-overseer-stocks.lua, duplicated here for
-- the same reason df-overseer-workshop.lua/df-overseer-trees.lua already
-- duplicate it (stocks.lua is not a touched surface this stream).
local function is_on_hidden_tile(item)
  local ok_pos, x, y, z = pcall(dfhack.items.getPosition, item)
  if not ok_pos or not x then
    return false
  end
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    return false
  end
  return not visible
end

local function is_fort_owned_item(item)
  local f = item.flags
  return not f.trader and not f.garbage_collect and not f.removed
    and not is_on_hidden_tile(item)
end

-- SILENT-ZERO FIX (handoffs/2026-09-19-silent-zero-fix.md,
-- research/2026-09-19-unverified-claims-audit.md finding 3): this used to
-- `return 0` when `item_type_other_id` did not resolve into a vector --
-- the same shape as the FEED_WATER_WOUNDED incident recorded in
-- docs/PRODUCTION-MODEL.md §13 (a name that does not exist, silently
-- reported as a genuine zero). Returns count(number or nil), err(string or
-- nil) -- err set means count is nil, not zero. Mirrors df-overseer-
-- labor.lua's `set_labor`, the fix already made once for the write path.
local function count_fort_owned(item_type_other_id)
  local ok, vec = pcall(function() return df.global.world.items.other[item_type_other_id] end)
  if not ok or not vec then
    return nil, "unknown item type: " .. tostring(item_type_other_id)
  end
  local n = 0
  for i = 0, #vec - 1 do
    if is_fort_owned_item(vec[i]) then
      n = n + 1
    end
  end
  return n, nil
end

-- BLOCKS, BUCKET, CHAIN, TRAPPARTS (mechanism) -- live-confirmed this
-- session via dfhack.buildings.getFiltersByType({}, df.building_type.Well,
-- -1, -1), matching the handoff's own figures exactly. Reported fresh on
-- every call, never cached. Each of the four is looked up independently, so
-- one bad name reports only its own miss, never masks the other three's
-- real counts -- `fort_owned_errors` carries only the entries that actually
-- failed, omitted entirely when all four resolve.
local function requirements()
  local blocks, blocks_err = count_fort_owned("BLOCKS")
  local bucket, bucket_err = count_fort_owned("BUCKET")
  local chain, chain_err = count_fort_owned("CHAIN")
  -- "Mechanism" items are the TRAPPARTS item type on this install
  -- (df-overseer-well.lua's own live check, same enum name the handoff
  -- cites) -- reported under both keys so a caller matching either name
  -- finds it.
  local trapparts, trapparts_err = count_fort_owned("TRAPPARTS")
  local errors = {
    BLOCKS = blocks_err, BUCKET = bucket_err, CHAIN = chain_err,
    TRAPPARTS = trapparts_err,
  }
  local has_error = blocks_err or bucket_err or chain_err or trapparts_err
  return {
    materials = {"BLOCKS", "BUCKET", "CHAIN", "TRAPPARTS"},
    fort_owned = {
      BLOCKS = blocks,
      BUCKET = bucket,
      CHAIN = chain,
      TRAPPARTS = trapparts,
    },
    fort_owned_errors = has_error and errors or nil,
  }
end

function find_well(level, near, radius_tiles)
  local chosen, err, resolved_z = ranked_candidates(level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z

  local results = {}
  for _, c in ipairs(chosen) do
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, c.x, c.y, z)
    local info = ok_near and near_info
    table.insert(results, {
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      water_depth = c.water_info.flow_size,
      water_stagnant = c.water_info.stagnant,
      water_salt = c.water_info.salt,
      requirements = requirements(),
    })
  end
  return results
end

local function parse_quickfort_stats(output)
  local stats = {}
  if not output then
    return stats
  end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then
      stats[label] = tonumber(value)
    end
  end
  return stats
end

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- DRY_RUN defaults to true. A dry run resolves the candidate and returns
-- exactly what would be built, without calling quickfort. Only an explicit
-- false performs the real mutation. UNTESTED live (mutation forbidden this
-- session).
function build_well(level, near, blueprint_file, rank, radius_tiles, dry_run)
  rank = rank or 1
  local dry = truthy_dry_run(dry_run)
  local chosen, err, resolved_z = ranked_candidates(level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end

  local c = chosen[rank]
  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, c.x, c.y, z)
  local info = ok_near and near_info
  local req = requirements()

  if dry then
    return {
      dry_run = true,
      rank = rank,
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      water_depth = c.water_info.flow_size,
      water_stagnant = c.water_info.stagnant,
      water_salt = c.water_info.salt,
      requirements = req,
      would_run_blueprint = blueprint_file,
    }
  end

  -- Real mutation. c.x,c.y exist only inside this function's local scope,
  -- for the instant it takes to build quickfort's argument list -- never
  -- printed or returned. UNTESTED live -- see header.
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', blueprint_file, '-c',
    string.format('%d,%d,%d', c.x, c.y, z))

  return {
    dry_run = false,
    rank = rank,
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    requirements = req,
    blueprint = blueprint_file,
    quickfort_ok = ok_run and result == CR_OK,
    quickfort_error = (not ok_run) and tostring(output) or nil,
    quickfort_stats = ok_run and parse_quickfort_stats(output) or nil,
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "find" then
  local level, near, radius
  if tonumber(args[2]) then
    level, near, radius = tonumber(args[2]), args[3], tonumber(args[4])
  else
    near, radius = args[2], tonumber(args[3])
  end
  if not near then
    print("usage: df-overseer-well find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_well(level, near, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "build" then
  local level, near, blueprint, rank, radius, dry_run
  if tonumber(args[2]) then
    level, near, blueprint, rank, radius, dry_run =
      tonumber(args[2]), args[3], args[4], tonumber(args[5]), tonumber(args[6]), args[7]
  else
    near, blueprint, rank, radius, dry_run =
      args[2], args[3], tonumber(args[4]), tonumber(args[5]), args[6]
  end
  if not (near and blueprint) then
    print("usage: df-overseer-well build [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]")
  else
    local result, err = build_well(level, near, blueprint, rank, radius, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-well find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-well build [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]")
end
