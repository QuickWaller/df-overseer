-- df-overseer-zone.lua
--@module = true
--
-- handoffs/2026-09-17-water-and-industry-tools.md item 1: the fort has no
-- drink it can reach and zero zones of any kind. The user's plan starts
-- with a Water Source zone directly on the pond water; this file is that
-- tool, structured so pasture/meeting-area/other zone kinds are a new
-- KIND_INFO table entry later, not a rewrite (per the handoff's own
-- instruction).
--
-- MECHANISM, verified from THIS install's own source this session (not
-- guessed), `hack/scripts/internal/quickfort/zone.lua`:
--   - quickfort's `#zone` symbol `w` places `df.civzone_type.WaterSource`
--     (live-confirmed enum value 82) -- `zone_db.w = {label='Water Source',
--     default_data={type=df.civzone_type.WaterSource}}`.
--   - Placement validity (`is_valid_zone_tile`) is ONLY `not
--     designation.hidden` -- quickfort itself does not require the tile to
--     actually contain water to place a WaterSource zone there. That
--     domain constraint ("targeting revealed water tiles") is this
--     project's own choice, not something quickfort enforces, so it is
--     applied here at candidate-selection time, before any tile is offered.
--   - `zone_template.has_extents = true` and `is_valid_zone_extent` only
--     requires at least one true cell in `extent_grid` -- CONFIRMED from
--     source that a zone blueprint's blank cells become false extent
--     cells (the same mechanism every quickfort `#place`/`#zone` mode
--     uses for a non-rectangular shape; this is standard, documented
--     quickfort behaviour, not a guess). So a zone can be shaped to the
--     water body's own footprint, not forced into a filled rectangle the
--     way farm/workshop `build` blueprints are.
--   - `do_run` (`check_tiles_and_extents`) SKIPS occupied tiles (a
--     building already there) rather than erroring -- reported as a stat,
--     never a hard failure.
--
-- CANDIDATE SHAPE: unlike farm/workshop/openarea/diggable, a pond is not a
-- rectangle the caller can specify as W H -- pond sizes on this map vary
-- from 4 to 31+ tiles (`research/2026-09-17-pool-reachability.md`) and are
-- irregular. So `zone.find` runs its OWN scoped 4-connected flood fill
-- (bounded by MAX_RADIUS, same box-scan cost profile as every other finder
-- here) over tiles matching `is_water_source_tile` (revealed, not magma,
-- `flow_size >= 1`, no building at the tile) near the landmark, and reports
-- each connected water body's bounding box, real tile count (distinct from
-- the bbox area, since the shape is irregular), and per-body depth/
-- stagnant/salt aggregates -- fields a player looking at their own map
-- screen can already see (depth by hovering, stagnant/salt by the
-- in-game "murky/foul" water description). `zone.place` shares the exact
-- same ranking (`ranked_water_bodies`), so "rank 1" can never mean two
-- different bodies depending which entry point asked -- same guarantee
-- every other df-overseer-*.lua fused find/act pair already gives.
--
-- BUILD MECHANISM: `zone.place`'s real (non-dry-run) path generates a
-- throwaway `#zone` blueprint CSV IN CODE, matching the chosen water
-- body's own membership set (a `w` cell only where that body's own water
-- tiles are, blank elsewhere), writes it to
-- `dfhack-config/blueprints/` (the directory quickfort itself resolves a
-- bare filename against -- TRAPS.md), runs `quickfort run <name> -c
-- x0,y0,z`, then deletes the file -- same "delete the throwaway blueprint
-- after" discipline `handoffs/2026-09-17-water-source-zone-test.md` uses
-- for its own hand-placed zone. The real coordinate (the bounding box's
-- own top-left) exists only inside this function's local scope, for the
-- instant it takes to build the blueprint text and the quickfort
-- argument list -- never printed or returned, same guarantee every other
-- build_*/dig_*/place_* function in this project gives. `io` availability
-- inside a DFHack script context was confirmed live this session with a
-- READ-ONLY open of an existing blueprint (no write) -- see this stream's
-- report for the exact check; the WRITE path itself is UNTESTED live
-- (mutation forbidden this session), flagged rather than assumed working.
--
-- KNOWLEDGE SCOPE: `is_water_source_tile` requires `dfhack.maps.
-- isTileVisible`, so a candidate can never include a tile a vanilla player
-- has not uncovered -- no hidden-tile admission the way df-overseer-
-- diggable.lua's act/sense fix allows, because there is nothing to "act
-- into" here the way there is for a dig: quickfort's own is_valid_zone_tile
-- already refuses a hidden tile outright (no blind-designate case exists
-- for zones), so the two rules agree and there is no asymmetry to encode.
--
-- Usage: ./dfhack-run df-overseer-zone find KIND [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-zone place KIND [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

-- Structured for a later kind to be a new table entry, not a rewrite (per
-- the handoff). Only water_source is implemented this stream. `symbol` is
-- the quickfort `#zone` mode character, read directly from this install's
-- own zone.lua (see header) -- never guessed.
local KIND_INFO = {
  water_source = {label = "Water Source", symbol = "w",
    civzone_type_name = "WaterSource"},
}

-- Revealed, not magma, actually carrying water (flow_size >= 1), and not
-- already under a building. This is this project's OWN domain rule
-- ("targeting revealed water tiles"), layered on top of quickfort's own
-- (much looser) is_valid_zone_tile -- see header. Returns (ok, info) where
-- info carries flow_size/stagnant/salt for a true tile, nil for a false one.
local function is_water_source_tile(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis or not visible then
    return false, nil
  end
  local pos = xyz2pos(x, y, z)
  local ok_flags, flags = pcall(dfhack.maps.getTileFlags, pos)
  if not ok_flags or not flags then
    return false, nil
  end
  -- docs/TRAPS.md: liquid_type is a plain Lua boolean on this build
  -- (false=Water, true=Magma), not the df.tile_liquid enum -- hedge both
  -- forms, same pattern df-overseer-farm.lua's valid_tile_base already uses.
  if flags.liquid_type == true or flags.liquid_type == df.tile_liquid.Magma then
    return false, nil
  end
  if not flags.flow_size or flags.flow_size < 1 then
    return false, nil
  end
  local ok_bld, bld = pcall(dfhack.buildings.findAtTile, pos)
  if ok_bld and bld then
    return false, nil
  end
  return true, {
    flow_size = flags.flow_size,
    stagnant = flags.water_stagnant or false,
    salt = flags.water_salt or false,
  }
end

-- LEVEL relative to the landmark's own z, same contract as every other
-- df-overseer-*.lua finder. Duplicated rather than shared -- see any of
-- those files' own comment for why.
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

-- 4-connected flood fill over the scoped box, water tiles only. Returns a
-- list of components, each {tiles = {{x,y},...}, min_x,max_x,min_y,max_y,
-- flow_min,flow_max,any_stagnant,any_salt}.
local function find_water_components(z, min_x, max_x, min_y, max_y)
  local info = {}
  for x = min_x, max_x do
    for y = min_y, max_y do
      local ok, tinfo = is_water_source_tile(x, y, z)
      if ok then
        info[x] = info[x] or {}
        info[x][y] = tinfo
      end
    end
  end

  local visited = {}
  local components = {}
  for x = min_x, max_x do
    for y = min_y, max_y do
      if info[x] and info[x][y] and not (visited[x] and visited[x][y]) then
        -- Explicit stack, no recursion, no per-tile pcall inside the
        -- flood loop itself -- docs/TRAPS.md's per-tile-closure/pcall cost
        -- warning; is_water_source_tile above already ran its own pcalls
        -- once per tile during the scan pass, not per flood-fill step.
        local stack = {{x, y}}
        local comp = {
          tiles = {}, min_x = x, max_x = x, min_y = y, max_y = y,
          flow_min = math.huge, flow_max = -math.huge,
          any_stagnant = false, any_salt = false,
        }
        visited[x] = visited[x] or {}
        visited[x][y] = true
        while #stack > 0 do
          local cur = table.remove(stack)
          local cx, cy = cur[1], cur[2]
          local tinfo = info[cx][cy]
          table.insert(comp.tiles, {cx, cy})
          comp.min_x = math.min(comp.min_x, cx)
          comp.max_x = math.max(comp.max_x, cx)
          comp.min_y = math.min(comp.min_y, cy)
          comp.max_y = math.max(comp.max_y, cy)
          comp.flow_min = math.min(comp.flow_min, tinfo.flow_size)
          comp.flow_max = math.max(comp.flow_max, tinfo.flow_size)
          comp.any_stagnant = comp.any_stagnant or tinfo.stagnant
          comp.any_salt = comp.any_salt or tinfo.salt
          local neighbors = {{cx + 1, cy}, {cx - 1, cy}, {cx, cy + 1}, {cx, cy - 1}}
          for _, n in ipairs(neighbors) do
            local nx, ny = n[1], n[2]
            if nx >= min_x and nx <= max_x and ny >= min_y and ny <= max_y
                and info[nx] and info[nx][ny]
                and not (visited[nx] and visited[nx][ny]) then
              visited[nx] = visited[nx] or {}
              visited[nx][ny] = true
              table.insert(stack, {nx, ny})
            end
          end
        end
        table.insert(components, comp)
      end
    end
  end
  return components
end

-- Server-side only: ranked water-body components (real coordinates kept on
-- each component's own tiles/bbox fields, never stripped here). Shared by
-- find_zone_area (which strips coordinates) and place_zone (which needs
-- them to build the throwaway blueprint) -- same "one ranking
-- implementation" guarantee every other df-overseer-*.lua fused pair gives.
local function ranked_water_bodies(level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local components = find_water_components(z, ax - radius, ax + radius, ay - radius, ay + radius)

  for _, c in ipairs(components) do
    local cx = (c.min_x + c.max_x) / 2
    local cy = (c.min_y + c.max_y) / 2
    local dx, dy = cx - ax, cy - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(components, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local chosen = {}
  for i = 1, math.min(MAX_RESULTS, #components) do
    table.insert(chosen, components[i])
  end
  return chosen, nil, z
end

function find_zone_area(kind, level, near, radius_tiles)
  local kind_info = KIND_INFO[tostring(kind):lower()]
  if not kind_info then
    return nil, "unknown zone kind: " .. tostring(kind) .. " (expected water_source)"
  end
  local chosen, err, resolved_z = ranked_water_bodies(level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = math.floor((c.min_x + c.max_x) / 2 + 0.5)
    local cy = math.floor((c.min_y + c.max_y) / 2 + 0.5)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local info = ok_near and near_info
    table.insert(results, {
      kind = kind_info.label,
      dims = {c.max_x - c.min_x + 1, c.max_y - c.min_y + 1},
      tile_count = #c.tiles,
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      depth_min = c.flow_min,
      depth_max = c.flow_max,
      stagnant = c.any_stagnant,
      salt = c.any_salt,
    })
  end
  return results
end

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- Writes a throwaway `#zone` blueprint CSV covering the component's own
-- bounding box, `symbol` only at the component's own water tiles, blank
-- elsewhere. Returns the bare filename (for quickfort's own -c resolution)
-- or nil, err. UNTESTED live -- see header; io availability itself WAS
-- confirmed live (read-only open of an existing file), this write path was
-- not (mutation forbidden this session).
local function write_zone_blueprint(comp, symbol, label)
  local member = {}
  for _, t in ipairs(comp.tiles) do
    local x, y = t[1], t[2]
    member[x] = member[x] or {}
    member[x][y] = true
  end
  local filename = string.format("_tmp-zone-%d-%d-%d.csv", comp.min_x, comp.min_y, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then
    return nil, "could not open blueprint for writing: " .. tostring(open_err)
  end
  f:write(string.format("#zone %s\n", label))
  for y = comp.min_y, comp.max_y do
    local row = {}
    for x = comp.min_x, comp.max_x do
      row[#row + 1] = (member[x] and member[x][y]) and symbol or ""
    end
    f:write(table.concat(row, ",") .. "\n")
  end
  f:close()
  return filename
end

-- DRY_RUN defaults to true. A dry run resolves the chosen water body and
-- reports exactly what would be built, without writing any blueprint file
-- or calling quickfort. Only an explicit false performs the real mutation.
function place_zone(kind, level, near, rank, radius_tiles, dry_run)
  local kind_info = KIND_INFO[tostring(kind):lower()]
  if not kind_info then
    return nil, "unknown zone kind: " .. tostring(kind) .. " (expected water_source)"
  end
  rank = rank or 1
  local dry = truthy_dry_run(dry_run)
  local chosen, err, resolved_z = ranked_water_bodies(level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end

  local c = chosen[rank]
  local cx = math.floor((c.min_x + c.max_x) / 2 + 0.5)
  local cy = math.floor((c.min_y + c.max_y) / 2 + 0.5)
  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local info = ok_near and near_info

  local base = {
    dry_run = dry,
    rank = rank,
    kind = kind_info.label,
    dims = {c.max_x - c.min_x + 1, c.max_y - c.min_y + 1},
    tile_count = #c.tiles,
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    depth_min = c.flow_min,
    depth_max = c.flow_max,
    stagnant = c.any_stagnant,
    salt = c.any_salt,
  }

  if dry then
    base.would_zone_tiles = #c.tiles
    return base
  end

  -- Real mutation. The bounding box's own top-left (c.min_x,c.min_y) is
  -- the coordinate that ever exists outside this function's local scope,
  -- and only inside quickfort's own -c argument -- never printed or
  -- returned. UNTESTED live -- see header.
  local filename, write_err = write_zone_blueprint(c, kind_info.symbol, kind_info.label)
  if not filename then
    base.quickfort_ok = false
    base.quickfort_error = write_err
    return base
  end

  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', filename, '-c',
    string.format('%d,%d,%d', c.min_x, c.min_y, z))

  pcall(os.remove, "dfhack-config/blueprints/" .. filename)

  base.quickfort_ok = ok_run and result == CR_OK
  base.quickfort_error = (not ok_run) and tostring(output) or nil
  return base
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "find" then
  local kind = args[2]
  local level, near, radius
  if tonumber(args[3]) then
    level, near, radius = tonumber(args[3]), args[4], tonumber(args[5])
  else
    near, radius = args[3], tonumber(args[4])
  end
  if not (kind and near) then
    print("usage: df-overseer-zone find KIND [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_zone_area(kind, level, near, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "place" then
  local kind = args[2]
  local level, near, rank, radius, dry_run
  if tonumber(args[3]) then
    level, near, rank, radius, dry_run =
      tonumber(args[3]), args[4], tonumber(args[5]), tonumber(args[6]), args[7]
  else
    near, rank, radius, dry_run = args[3], tonumber(args[4]), tonumber(args[5]), args[6]
  end
  if not (kind and near) then
    print("usage: df-overseer-zone place KIND [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]")
  else
    local result, err = place_zone(kind, level, near, rank, radius, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-zone find KIND [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-zone place KIND [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]")
end
