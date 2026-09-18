-- df-overseer-harvest.lua
--@module = true
--
-- handoffs/2026-09-19-well-and-harvest.md goal 2: harvest a lot of WILD
-- plants (the HERBALIST labour's gather-plants action), explicitly not
-- farming -- the user asked for wild-gathered plants and no new farm plot.
-- No existing df-overseer-*.lua tool designates this: df-overseer-trees.lua
-- covers felling only. This is a genuine lever gap, recorded per that
-- handoff's own instruction and closed here with a small, bounded tool
-- rather than an unrepeatable one-off live mutation.
--
-- MECHANISM, verified from this install's own source this session,
-- `hack/scripts/internal/quickfort/dig.lua`:
--   - Quickfort's `#dig` blueprint symbol `p` (Gather Plants) is wired to
--     `do_gather`, which -- like `do_chop` for felling, symbol `t` --
--     refuses a hidden tile outright (`if digctx.flags.hidden then return
--     nil end`, no "blind gather" case, unlike ordinary mining) and
--     otherwise requires `tileattrs.shape == df.tiletype_shape.SHRUB`
--     (`is_gatherable`). When both hold it just sets `digctx.flags.dig =
--     values.dig_default` -- the SAME `tile_designation.dig` field ordinary
--     mining uses; the engine reads it as a gather job because the tile's
--     shape is SHRUB, not a wall.
--   - `dfhack.designations.markPlant`, the exact primitive
--     df-overseer-trees.lua already uses for felling, is generic over plant
--     type -- live-tested this session against this fort's own map:
--     `canMarkPlant` returned true for 200/200 sampled wild shrub-type
--     (`DRY_PLANT`/`WET_PLANT`) plants, none already marked. Used directly
--     here, matching trees.lua's own justification for skipping quickfort
--     (scattered, non-adjacent single tiles -- no behavioural difference
--     from calling the one-line primitive at more complexity).
--
-- BOUNDED QUERY DISCIPLINE (docs/TRAPS.md, "DFHack command execution is not
-- safely concurrent, and the watchdog is not exempt" -- an unbounded
-- full-map tile scan wedged the command pipe for 10+ minutes on
-- 2026-09-19 and cost a 22,000-tick rollback): candidate-finding here NEVER
-- scans map tiles, box or full-map. `df.global.world.plants.all` is a
-- bounded vector (9,642 entries live-counted on this fort this session,
-- nowhere near the ~6.86M-tile scale that caused the incident), iterated
-- once with no per-entry pcall closure allocated inside the loop body
-- (research/2026-09-12-dfhack-capability-checks.md's own "closure per
-- iteration is catastrophic at map scale" finding). Every reachability/
-- visibility check below is a single targeted point lookup at that plant's
-- own already-known position, not a scan of any kind.
--
-- SPECIES AND BREWABILITY: candidates are grouped by their raw plant id
-- (`df.global.world.raws.plants.all[plant.material].id`). The BREWABLE set
-- below was checked this session directly against this install's own
-- `data/vanilla/vanilla_plants/objects/*.txt` for
-- `MATERIAL_REACTION_PRODUCT:DRINK_MAT` in each id's own raw block -- a
-- one-time reading of THIS install's raws for the species THIS fort's own
-- plants.all vector actually contains this session, not a general claim
-- about vanilla DF or an exhaustive species list.
--
-- REACHABILITY: unlike a tree (a non-walkable, wall-shaped tile worked
-- from an adjacent tile -- df-overseer-trees.lua's `is_reachable`), a SHRUB
-- tile is itself walkable: a dwarf stands ON it to gather. So reachability
-- here checks the plant's OWN tile's walkable group against the map's main
-- group (df-overseer-connectivity.lua's `get_connectivity_report`), not a
-- neighbour ring.
--
-- LABOR: HERBALIST (df.unit_labor.HERBALIST) is the gathering labour on
-- this install, confirmed by enumerating df.unit_labor's real names live
-- (PLANT is farming/seed-sowing, a different labour). Neither `find` nor
-- `gather` ever hand-sets a labour -- matching df-overseer-labor.lua's own
-- autolabor-preserving discipline, this tool only reports how many
-- citizens already carry it.
--
-- SPECIES is always the LAST argument, optional, to sidestep the ambiguity
-- an earlier draft of this file's own arg parsing had (a leading optional
-- token that could be either SPECIES or LEVEL) -- found and fixed before
-- ever being deployed.
--
-- Usage: ./dfhack-run df-overseer-harvest find [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [SPECIES]
-- Usage: ./dfhack-run df-overseer-harvest gather N [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [DRY_RUN] [SPECIES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local connectivity_mod = reqscript('df-overseer-connectivity')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local HERBALIST_LABOR = "HERBALIST"

-- See header "SPECIES AND BREWABILITY". Checked against this install's own
-- raws 2026-09-19, matching doctrine `brewing-chain-from-raws` /
-- `plump-helmet-is-brewable`.
local BREWABLE = {
  BERRIES_FISHER = true,
  BERRY_SUN = true,
  BLACKBERRY = true,
  CRANBERRY = true,
  GRASS_TAIL_PIG = true,
  GRASS_WHEAT_CAVE = true,
  KANIWA = true,
  MUSHROOM_HELMET_PLUMP = true,
  POD_SWEET = true,
  REED_ROPE = true,
  WEED_RAT = true,
  WILD_CARROT = true,
}

local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

local function plant_species(plant)
  local ok, raw = pcall(function() return df.global.world.raws.plants.all[plant.material] end)
  if ok and raw then return raw.id end
  return "UNKNOWN_" .. tostring(plant.material)
end

-- SILENT-ZERO FIX discipline (matches df-overseer-trees.lua's
-- labor_enabled_count, df-overseer-labor.lua's set_labor): an unknown
-- labour token is a distinct outcome from "resolved, zero citizens have
-- it", never collapsed into the same number.
local function labor_enabled_count(labor_name)
  local code = df.unit_labor[labor_name]
  if code == nil then
    return nil, "unknown labor: " .. tostring(labor_name)
  end
  local n = 0
  for _, unit in ipairs(df.global.world.units.active) do
    local ok, is_cit = pcall(dfhack.units.isCitizen, unit)
    if ok and is_cit and unit.status.labors[code] then
      n = n + 1
    end
  end
  return n, nil
end

-- One targeted point check per candidate plant -- never a scan. Returns a
-- table: visible, reachable (own tile's walkable group matches the map's
-- main group), already_marked.
local function plant_info(plant, main_group_id)
  local x, y, z = plant.pos.x, plant.pos.y, plant.pos.z
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  visible = ok_vis and visible or false
  local ok_group, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  local ok_mark, marked = pcall(dfhack.designations.isPlantMarked, plant)
  return {
    visible = visible,
    reachable = ok_group and group ~= 0 and group == main_group_id,
    already_marked = ok_mark and marked or false,
  }
end

-- Every visible, unmarked, gatherable-species wild plant within radius of
-- (ax,ay) at level z, each tagged with distance/reachable/brewable. Server-
-- side only (the plant object and its real position live in the returned
-- table); find_gatherable/gather_plants strip or consume respectively.
local function gatherable_candidates(z, ax, ay, radius, species_filter, main_group_id)
  local out = {}
  for _, p in ipairs(df.global.world.plants.all) do
    if (p.type == df.plant_type.DRY_PLANT or p.type == df.plant_type.WET_PLANT)
        and p.pos.z == z then
      local dx, dy = p.pos.x - ax, p.pos.y - ay
      local dist = math.sqrt(dx * dx + dy * dy)
      if dist <= radius then
        local species = plant_species(p)
        if not species_filter or species == species_filter then
          local info = plant_info(p, main_group_id)
          if info.visible and not info.already_marked then
            table.insert(out, {
              plant = p,
              species = species,
              dist = dist,
              reachable = info.reachable,
              brewable = BREWABLE[species] or false,
            })
          end
        end
      end
    end
  end
  -- Reachable and brewable candidates first, then nearest.
  table.sort(out, function(a, b)
    if a.reachable ~= b.reachable then return a.reachable end
    if a.brewable ~= b.brewable then return a.brewable end
    return a.dist < b.dist
  end)
  return out
end

-- Coordinate-free aggregate report: per-species counts, never a per-plant
-- dump (design commitment #1 -- no raw coordinate leaves this function).
function find_gatherable(species_filter, level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. tostring(near)
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local report = connectivity_mod.get_connectivity_report()
  local main_group_id = report.main_group_id

  local candidates = gatherable_candidates(z, ax, ay, radius, species_filter, main_group_id)

  local by_species = {}
  local total, total_reachable, total_brewable = 0, 0, 0
  for _, c in ipairs(candidates) do
    total = total + 1
    if c.reachable then total_reachable = total_reachable + 1 end
    if c.brewable then total_brewable = total_brewable + 1 end
    local s = by_species[c.species]
    if not s then
      s = {species = c.species, brewable = c.brewable, count = 0, reachable_count = 0}
      by_species[c.species] = s
    end
    s.count = s.count + 1
    if c.reachable then s.reachable_count = s.reachable_count + 1 end
  end
  local species_list = {}
  for _, s in pairs(by_species) do
    table.insert(species_list, s)
  end
  table.sort(species_list, function(a, b) return a.count > b.count end)

  local citizens_with_labor, labor_err = labor_enabled_count(HERBALIST_LABOR)
  return {
    near_landmark = near,
    radius_tiles = radius,
    species_filter = species_filter,
    total_count = total,
    total_reachable = total_reachable,
    total_brewable = total_brewable,
    species = species_list,
    labor = HERBALIST_LABOR,
    citizens_with_labor = citizens_with_labor,
    citizens_with_labor_error = labor_err,
  }
end

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- DRY_RUN defaults to true. A dry run resolves the nearest N reachable
-- (brewable-preferred) candidates and reports exactly what would be
-- marked, without calling dfhack.designations.markPlant on anything. Only
-- an explicit false performs the real mutation.
function gather_plants(n, species_filter, level, near, radius_tiles, dry_run)
  n = tonumber(n)
  if not n or n < 1 then
    return nil, "N must be a positive integer"
  end
  local dry = truthy_dry_run(dry_run)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. tostring(near)
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local report = connectivity_mod.get_connectivity_report()
  local main_group_id = report.main_group_id

  local candidates = gatherable_candidates(z, ax, ay, radius, species_filter, main_group_id)
  local reachable = {}
  for _, c in ipairs(candidates) do
    if c.reachable then table.insert(reachable, c) end
  end

  local chosen_n = math.min(n, #reachable)
  local chosen = {}
  for i = 1, chosen_n do
    table.insert(chosen, reachable[i])
  end

  local brewable_chosen = 0
  for _, c in ipairs(chosen) do
    if c.brewable then brewable_chosen = brewable_chosen + 1 end
  end

  local citizens_with_labor, labor_err = labor_enabled_count(HERBALIST_LABOR)
  local result = {
    dry_run = dry,
    requested = n,
    near_landmark = near,
    species_filter = species_filter,
    would_gather = chosen_n,
    would_gather_brewable = brewable_chosen,
    nearest_distance_tiles = chosen_n > 0 and chosen[1].dist or nil,
    farthest_distance_tiles = chosen_n > 0 and chosen[chosen_n].dist or nil,
    labor = HERBALIST_LABOR,
    citizens_with_labor = citizens_with_labor,
    citizens_with_labor_error = labor_err,
  }

  if dry then
    return result
  end

  -- Real mutation. Each chosen plant's own position exists only inside this
  -- loop's local scope -- never printed or returned.
  local marked = 0
  for _, c in ipairs(chosen) do
    local ok_mark = pcall(dfhack.designations.markPlant, c.plant)
    if ok_mark then
      marked = marked + 1
    end
  end
  result.marked = marked
  return result
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "find" then
  local level, near, radius, species
  if tonumber(args[2]) then
    level, near, radius, species = tonumber(args[2]), args[3], tonumber(args[4]), args[5]
  else
    near, radius, species = args[2], tonumber(args[3]), args[4]
  end
  if not near then
    print("usage: df-overseer-harvest find [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [SPECIES]")
  else
    local result, err = find_gatherable(species, level, near, radius)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "gather" then
  local n = args[2]
  local level, near, radius, dry_run, species
  if tonumber(args[3]) then
    level, near, radius, dry_run, species =
      tonumber(args[3]), args[4], tonumber(args[5]), args[6], args[7]
  else
    near, radius, dry_run, species = args[3], tonumber(args[4]), args[5], args[6]
  end
  if not (n and near) then
    print("usage: df-overseer-harvest gather N [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [DRY_RUN] [SPECIES]")
  else
    local result, err = gather_plants(n, species, level, near, radius, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-harvest find [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [SPECIES]")
  print("usage: df-overseer-harvest gather N [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [DRY_RUN] [SPECIES]")
end
