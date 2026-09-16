-- df-overseer-farm.lua
--@module = true
--
-- handoffs/2026-09-16-farm-and-still-tools.md Part 2: the fort (Uniboslan,
-- 15 citizens) owns 24 units of food, no drink, and no farm plot -- and
-- all six seed types it owns (plump helmet, pig tail, cave wheat, sweet
-- pod, quarry bush, dimple cup) are SUBTERRANEAN-only crops, confirmed live
-- this session (see "CROP BIOME CLASSIFICATION" below) -- so a farm on the
-- open surface would grow nothing this fort can plant. This file finds and
-- builds farm plots and assigns crops to them, landmark-relative, no raw
-- coordinates ever crossing the model boundary (design commitment #1).
--
-- Same fused perceive-then-act idiom as df-overseer-openarea.lua and
-- df-overseer-diggable.lua: `ranked_candidates` is shared by `find` and
-- `build` so "candidate rank 1" can never mean two different tiles
-- depending which entry point asked, and a real coordinate exists only
-- inside a function's own local scope for the instant it takes to build
-- quickfort's argument list.
--
-- GROUND RULE, sourced from THIS install's own
-- hack/scripts/internal/quickfort/build.lua, not reimplemented from a
-- guess: `is_valid_tile_farm(pos)` there is `is_valid_tile_dirt(pos) or
-- (is_floor(pos) and has_mud(pos))`. `is_farm_tile` below mirrors that
-- exact predicate chain (is_valid_tile_base -> is_valid_tile_generic ->
-- is_valid_tile_dirt, plus the separate is_floor+has_mud branch for
-- muddied stone) so a candidate this tool proposes is a candidate
-- quickfort's own `#build` `p` (Farm Plot) symbol will actually accept --
-- per the handoff's own instruction, "validate against the game's own
-- rules rather than reimplementing them." Deliberately NOT built on
-- df-overseer-openarea.lua's `is_free` (openarea's ground rule is "any
-- walkable, building-free tile"; farm's is materially different --
-- soil/grass/plant material or muddied stone specifically), unlike
-- df-overseer-workshop.lua (Part 3), which genuinely does reuse it.
--
-- `is_valid_tile_base` in that source already requires `not
-- flags.hidden` -- so this tool's ground rule is inherently
-- knowledge-scope-safe: a hidden tile can never be a farm-plot candidate,
-- with no separate isTileVisible check needed here the way
-- df-overseer-diggable.lua/df-overseer-openarea.lua needed one added.
-- `outside` is reported per candidate (`dfhack.maps.getTileFlags(pos).outside`,
-- the same field `is_valid_tile_inside` in that source tests) -- directly
-- player-visible (light vs. dark, roofed vs. open sky) on a revealed tile,
-- never a sensed property.
--
-- A candidate box is required to be UNIFORMLY inside or uniformly outside
-- -- a mixed box is rejected outright (v1 scope, stated rather than
-- silently guessed): DF does allow a farm plot straddling both, but this
-- tool's own crop-validity check (below) is a single inside/outside
-- classification per plot, and a plot that is genuinely mixed would need
-- per-tile crop rules this project has no use for today (none of this
-- fort's owned seeds are surface crops -- see below).
--
-- CROP BIOME CLASSIFICATION, verified live this session against this
-- install's own raws (not assumed from the wiki): `plant_raw.flags` is a
-- bitfield with one `BIOME_<name>` key per real DF biome (48 total,
-- enumerated live). Exactly three are cavern biomes:
-- BIOME_SUBTERRANEAN_WATER/_CHASM/_LAVA; every other BIOME_* key is a
-- surface biome. All six of this fort's owned seed types carry ONLY
-- BIOME_SUBTERRANEAN_WATER true and every other BIOME_* flag false --
-- confirmed by a live, read-only probe this session, matching
-- CLAUDE.md's 2026-09-16 status line ("All six seed types... are
-- subterranean crops"). A plant with at least one true BIOME_SUBTERRANEAN_*
-- flag is underground-plantable; a plant with at least one true non-
-- subterranean BIOME_* flag is outside-plantable (a plant can be both --
-- not exercised by this fort's own seeds, but not excluded either). A
-- plant with NO true BIOME_* flag at all is refused rather than guessed
-- at -- this project's own "mark verified vs proposed" rule. This is a
-- coarser test than DF's full region-biome matching (which surface biome
-- exactly, not just "some surface biome") -- named as a real simplification,
-- defensible because this fort owns no surface seed to need the finer
-- test, not because the finer test doesn't exist.
--
-- SEASON/CROP WRITE MECHANISM: `building_farmplotst.plant_id` is a
-- length-4 array, confirmed live this session by allocating a standalone
-- (never world-attached) `building_farmplotst` and enumerating its fields
-- -- this settles food-and-drink-logistics research's own "most concrete
-- next research step" (candidate (c): a direct struct write, by analogy
-- with set_labor's `unit.status.labors[code]` pattern). `df.season` is
-- confirmed live as {Spring=0, Summer=1, Autumn=2, Winter=3}. `plant_id`'s
-- own index convention (a plant-raw index, the same scheme
-- `item.mat_index` uses for SEEDS items in df-overseer-stocks.lua) is
-- inferred by strong convention-consistency with that already-verified
-- field, NOT independently proven by writing to it -- this session cannot
-- mutate the fort, so `set_farm_crop`'s real (non-dry-run) write path is
-- UNTESTED live. Flagged rather than assumed working.
--
-- autofarm (the shipped DFHack plugin, confirmed present as a compiled
-- .plug.so on this install) was checked and ruled out for this tool's
-- purpose: it reassigns crops FORTRESS-WIDE by seed-stock threshold, with
-- no per-named-plot control at all (its own docs, hack/docs/docs/tools/
-- autofarm.txt) -- exactly the gap food-and-drink-logistics research
-- flagged. `set_farm_crop` is a real Quartermaster-shaped tool where
-- autofarm is not.
--
-- Plots are made addressable the same way df-overseer-landmarks.lua
-- already names buildings (a non-empty dfhack.buildings.getName()) --
-- `build_farm_plot` explicitly names the plot it just built (a farm plot's
-- own DF-default name was not verified to be non-empty, so this tool never
-- relies on it) via `dfhack.buildings.setName`, "Farm Plot #<n>" with n
-- one past the count of existing landmarks already matching that pattern.
-- UNTESTED live for the same reason as the plant_id write above.
--
-- Dry-run mode (handoffs/2026-09-16-farm-and-still-tools.md, "Verification
-- without mutating the fort"): both `build_farm_plot` and `set_farm_crop`
-- default DRY_RUN to true. A dry run resolves the target, runs every
-- validation this file has (tile states, crop validity, seed
-- availability), and returns exactly what it would do -- WITHOUT calling
-- quickfort or writing any struct field. Only an explicit `false` performs
-- the real mutation. This session only ever calls with DRY_RUN true (the
-- fort must stay paused and unmutated) -- see the handoff's report for what
-- was verified live in dry-run mode specifically.
--
-- Usage: ./dfhack-run df-overseer-farm find W H [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-farm build W H [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-farm set-crop NAME SEASON CROP [DRY_RUN]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local stocks_mod = reqscript('df-overseer-stocks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

local DIRT_MATERIALS = {
  [df.tiletype_material.SOIL] = true,
  [df.tiletype_material.GRASS_LIGHT] = true,
  [df.tiletype_material.GRASS_DARK] = true,
  [df.tiletype_material.GRASS_DRY] = true,
  [df.tiletype_material.GRASS_DEAD] = true,
  [df.tiletype_material.PLANT] = true,
}

local DIRT_BAD_SHAPES = {
  [df.tiletype_shape.BOULDER] = true,
  [df.tiletype_shape.PEBBLES] = true,
  [df.tiletype_shape.WALL] = true,
}

local GENERIC_SHAPES = {
  [df.tiletype_shape.FLOOR] = true,
  [df.tiletype_shape.BOULDER] = true,
  [df.tiletype_shape.PEBBLES] = true,
  [df.tiletype_shape.TWIG] = true,
  [df.tiletype_shape.SAPLING] = true,
  [df.tiletype_shape.SHRUB] = true,
}

-- Mirrors quickfort's is_valid_tile_base (hack/scripts/internal/quickfort/
-- build.lua) exactly, including its liquid_type hedge (docs/TRAPS.md:
-- liquid_type is a plain Lua boolean on this build, not the enum -- that
-- file's own source already tests both forms, so this does too).
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

local function valid_tile_generic(pos, tt)
  if not valid_tile_base(pos) then
    return false
  end
  local ok, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  return ok and GENERIC_SHAPES[shape] or false
end

local function valid_tile_dirt(pos, tt)
  local ok_s, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  local ok_m, mat = pcall(function() return df.tiletype.attrs[tt].material end)
  if not ok_s or not ok_m then
    return false
  end
  if DIRT_BAD_SHAPES[shape] then
    return false
  end
  return DIRT_MATERIALS[mat] and valid_tile_generic(pos, tt)
end

local function is_floor(tt)
  local ok, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  if not ok then
    return false
  end
  local ok2, basic = pcall(function() return df.tiletype_shape.attrs[shape].basic_shape end)
  return ok2 and basic == df.tiletype_shape_basic.Floor
end

local function has_mud(pos)
  local ok, block = pcall(dfhack.maps.getTileBlock, pos)
  if not ok or not block then
    return false
  end
  local ok2, events = pcall(function() return block.block_events end)
  if not ok2 or not events then
    return false
  end
  for _, bev in ipairs(events) do
    local ok3, kind = pcall(function() return bev:getType() end)
    if ok3 and kind == df.block_square_event_type.material_spatter then
      local ok4, mat_type = pcall(function() return bev.mat_type end)
      local ok5, mat_state = pcall(function() return bev.mat_state end)
      if ok4 and ok5 and mat_type == df.builtin_mats.MUD
          and mat_state == df.matter_state.Solid then
        return true
      end
    end
  end
  return false
end

-- Returns (is_farm_tile: bool, outside: bool or nil). outside is nil when
-- the tile isn't a farm tile at all -- never guessed.
local function farm_tile_status(x, y, z)
  local pos = xyz2pos(x, y, z)
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return false, nil
  end
  local ok = valid_tile_dirt(pos, tt) or (is_floor(tt) and has_mud(pos))
  if not ok then
    return false, nil
  end
  local ok_flags, flags = pcall(dfhack.maps.getTileFlags, pos)
  if not ok_flags or not flags then
    return false, nil
  end
  return true, flags.outside
end

-- Every top-left position where a w-by-h window is entirely farm tiles,
-- uniformly inside or uniformly outside (a mixed box is rejected -- see
-- header), within the given box at the given z.
local function find_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local farm, outside = {}, {}
  for x = min_x, max_x do
    farm[x] = {}
    outside[x] = {}
    for y = min_y, max_y do
      local ok, out = farm_tile_status(x, y, z)
      farm[x][y] = ok
      outside[x][y] = out
    end
  end

  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      local fits, uniform, out_val = true, true, outside[x][y]
      for dx = 0, w - 1 do
        if not fits then break end
        for dy = 0, h - 1 do
          if not farm[x + dx][y + dy] then
            fits = false
            break
          end
          if outside[x + dx][y + dy] ~= out_val then
            uniform = false
          end
        end
      end
      if fits and uniform then
        table.insert(candidates, {x = x, y = y, outside = out_val})
      end
    end
  end
  return candidates
end

local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- Duplicated from df-overseer-openarea.lua/df-overseer-diggable.lua rather
-- than shared -- see either file's own comment for why (a small,
-- self-contained pure function, no farm-specific state).
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

local function ranked_candidates(w, h, level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local candidates = find_candidates(
    w, h, z, ax - radius, ax + radius, ay - radius, ay + radius)

  for _, c in ipairs(candidates) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(candidates, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local chosen = {}
  for _, c in ipairs(candidates) do
    local ok = true
    for _, existing in ipairs(chosen) do
      if overlaps(c, existing, w, h) then
        ok = false
        break
      end
    end
    if ok then
      table.insert(chosen, c)
      if #chosen >= MAX_RESULTS then
        break
      end
    end
  end
  return chosen, nil, z
end

-- BIOME_SUBTERRANEAN_WATER/_CHASM/_LAVA are the only three cavern biomes in
-- this install's plant_raw_flags enum (48 BIOME_* keys total, enumerated
-- live this session) -- everything else named BIOME_* is a surface biome.
-- See header for the live verification and the simplification this is.
local function classify_plant_biome(plant)
  local underground_ok, surface_ok, any_biome = false, false, false
  local ok_f, flags = pcall(function() return plant.flags end)
  if not ok_f or not flags then
    return false, false, false
  end
  for k, v in pairs(flags) do
    if v == true then
      local key = tostring(k)
      if key:match('^BIOME_') then
        any_biome = true
        if key:match('^BIOME_SUBTERRANEAN_') then
          underground_ok = true
        else
          surface_ok = true
        end
      end
    end
  end
  return underground_ok, surface_ok, any_biome
end

local function find_plant_by_id(id)
  local plants = df.global.world.raws.plants.all
  for i = 0, #plants - 1 do
    if plants[i].id == id then
      return plants[i], i
    end
  end
  return nil, nil
end

-- Returns (ok: bool, reason: string or nil, plant_index: number or nil).
-- Refuses (never guesses) a crop with no BIOME_* data at all.
local function crop_validity(crop_id, plot_outside)
  local plant, idx = find_plant_by_id(crop_id)
  if not plant then
    return false, "unknown crop: " .. tostring(crop_id)
  end
  local seeds = stocks_mod.get_seeds()
  local units = (seeds.by_plant_units or {})[crop_id] or 0
  if units <= 0 then
    return false, "fort holds no " .. crop_id .. " seed"
  end
  local underground_ok, surface_ok, any_biome = classify_plant_biome(plant)
  if not any_biome then
    return false, "no biome data for " .. crop_id .. " -- refusing rather than guessing"
  end
  if plot_outside and not surface_ok then
    return false, crop_id .. " is underground-only; this plot is outside"
  end
  if not plot_outside and not underground_ok then
    return false, crop_id .. " is surface-only; this plot is inside"
  end
  return true, nil, idx
end

-- Fort-owned seed ids valid for a plot of the given outside-ness, for
-- exposing "what could grow here" alongside a candidate (handoff Part 2:
-- "Expose the fort's valid crops for a given plot as part of farm.find").
local function valid_crops_for(plot_outside)
  local seeds = stocks_mod.get_seeds()
  local valid = {}
  for crop_id, units in pairs(seeds.by_plant_units or {}) do
    if units > 0 then
      local ok = crop_validity(crop_id, plot_outside)
      if ok then
        table.insert(valid, crop_id)
      end
    end
  end
  table.sort(valid)
  return valid
end

function find_farm_plot_area(w, h, level, near, radius_tiles)
  local chosen, err, resolved_z = ranked_candidates(w, h, level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = c.x + math.floor((w - 1) / 2)
    local cy = c.y + math.floor((h - 1) / 2)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local info = ok_near and near_info
    table.insert(results, {
      dims = {w, h},
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      outside = c.outside,
      valid_crops = valid_crops_for(c.outside),
    })
  end
  return results
end

-- Parses quickfort's own "Blueprint statistics:" block. See
-- df-overseer-openarea.lua's identical helper for the full rationale;
-- duplicated rather than shared for the same reason as resolve_level above.
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

-- True unless the string is exactly "false"/"0"/"no" (case-insensitive).
-- DRY_RUN defaults to true (unset/nil) -- see header. Only an explicit
-- false-ish value performs a real mutation.
local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- Stable landmark name for a newly built plot: "Farm Plot #<n>", n one
-- past however many existing landmarks already match that pattern. Only
-- called from the real (non-dry-run) path -- UNTESTED live, see header.
local function next_farm_plot_name()
  local landmarks, err = landmarks_mod.list_landmarks()
  local max_n = 0
  if not err then
    for _, lm in ipairs(landmarks) do
      local n = tostring(lm.name or ""):match('^Farm Plot #(%d+)$')
      if n and tonumber(n) > max_n then
        max_n = tonumber(n)
      end
    end
  end
  return string.format("Farm Plot #%d", max_n + 1)
end

-- DRY_RUN defaults to true. A dry run resolves the candidate and returns
-- exactly what would be built, without calling quickfort. See header.
function build_farm_plot(w, h, level, near, blueprint_file, rank, radius_tiles, dry_run)
  rank = rank or 1
  local dry = truthy_dry_run(dry_run)
  local chosen, err, resolved_z = ranked_candidates(w, h, level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end

  local c = chosen[rank]
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)
  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local info = ok_near and near_info

  if dry then
    return {
      dry_run = true,
      rank = rank,
      dims = {w, h},
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      outside = c.outside,
      valid_crops = valid_crops_for(c.outside),
      would_run_blueprint = blueprint_file,
      would_be_named = next_farm_plot_name(),
    }
  end

  -- Real mutation. Same top-left anchoring as build_open_area/
  -- dig_diggable_area (c.x,c.y, the validated top-left, never the
  -- computed center) -- see either file's own header for the
  -- top-left-vs-center quickfort bug this project already paid for once.
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', blueprint_file, '-c',
    string.format('%d,%d,%d', c.x, c.y, z))

  local name = nil
  if ok_run and result == CR_OK then
    local ok_bld, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(c.x, c.y, z))
    if ok_bld and bld then
      name = next_farm_plot_name()
      pcall(dfhack.buildings.setName, bld, name)
    end
  end

  return {
    dry_run = false,
    rank = rank,
    dims = {w, h},
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    outside = c.outside,
    blueprint = blueprint_file,
    quickfort_ok = ok_run and result == CR_OK,
    quickfort_error = (not ok_run) and tostring(output) or nil,
    quickfort_stats = ok_run and parse_quickfort_stats(output) or nil,
    named = name,
  }
end

-- Finds a named, built farm plot the same way df-overseer-landmarks.lua's
-- own building enumeration does (a non-empty dfhack.buildings.getName()),
-- but returns the building pointer itself (server-side only, never
-- returned to any caller) since set_farm_crop needs to read its outside-
-- ness and, in the real path, write its plant_id field -- landmarks.lua
-- deliberately never hands out anything but a bare coordinate.
local function find_farm_plot_by_name(name)
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_type, btype = pcall(function() return bld:getType() end)
    if ok_type and btype == df.building_type.FarmPlot then
      local ok_name, bname = pcall(dfhack.buildings.getName, bld)
      if ok_name and bname ~= "" and bname == name then
        return bld
      end
    end
  end
  return nil
end

local SEASON_INDEX = {spring = 0, summer = 1, autumn = 2, winter = 3}

-- DRY_RUN defaults to true. A dry run resolves the plot, validates the
-- season and crop, and returns exactly what would be written, without
-- touching plant_id. See header -- the real write is UNTESTED live.
function set_farm_crop(name, season, crop, dry_run)
  local dry = truthy_dry_run(dry_run)
  local bld = find_farm_plot_by_name(name)
  if not bld then
    return nil, "no farm plot named " .. tostring(name)
  end
  local season_idx = SEASON_INDEX[tostring(season):lower()]
  if not season_idx then
    return nil, "unknown season " .. tostring(season)
      .. " (expected spring/summer/autumn/winter)"
  end
  local ok_pos, x, y, z = pcall(function() return bld.x1, bld.y1, bld.z end)
  if not ok_pos then
    return nil, "could not resolve plot position"
  end
  local ok_flags, flags = pcall(dfhack.maps.getTileFlags, xyz2pos(x, y, z))
  if not ok_flags or not flags then
    return nil, "could not resolve plot tile state"
  end
  local plot_outside = flags.outside

  local ok, reason, plant_idx = crop_validity(crop, plot_outside)
  if not ok then
    return nil, reason
  end

  if dry then
    return {
      dry_run = true,
      plot = name,
      season = season,
      crop = crop,
      outside = plot_outside,
      would_set_plant_index = plant_idx,
    }
  end

  -- Real mutation: a direct struct write, by the same pattern as
  -- df-overseer-labor.lua's set_labor (unit.status.labors[code]).
  -- UNTESTED live -- see header.
  local ok_write = pcall(function() bld.plant_id[season_idx] = plant_idx end)
  return {
    dry_run = false,
    plot = name,
    season = season,
    crop = crop,
    outside = plot_outside,
    write_ok = ok_write,
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "find" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, radius
  if tonumber(args[4]) then
    level, near, radius = tonumber(args[4]), args[5], tonumber(args[6])
  else
    near, radius = args[4], tonumber(args[5])
  end
  if not (w and h and near) then
    print("usage: df-overseer-farm find W H [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_farm_plot_area(w, h, level, near, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "build" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, blueprint, rank, radius, dry_run
  if tonumber(args[4]) then
    level, near, blueprint, rank, radius, dry_run =
      tonumber(args[4]), args[5], args[6], tonumber(args[7]), tonumber(args[8]), args[9]
  else
    near, blueprint, rank, radius, dry_run =
      args[4], args[5], tonumber(args[6]), tonumber(args[7]), args[8]
  end
  if not (w and h and near and blueprint) then
    print("usage: df-overseer-farm build W H [LEVEL] NEAR_LANDMARK"
      .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]")
  else
    local result, err = build_farm_plot(w, h, level, near, blueprint, rank, radius, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "set-crop" then
  local name, season, crop, dry_run = args[2], args[3], args[4], args[5]
  if not (name and season and crop) then
    print("usage: df-overseer-farm set-crop NAME SEASON CROP [DRY_RUN]")
  else
    local result, err = set_farm_crop(name, season, crop, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-farm find W H [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-farm build W H [LEVEL] NEAR_LANDMARK"
    .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]")
  print("usage: df-overseer-farm set-crop NAME SEASON CROP [DRY_RUN]")
end
