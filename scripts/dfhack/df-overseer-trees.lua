-- df-overseer-trees.lua
--@module = true
--
-- handoffs/2026-09-17-water-and-industry-tools.md item 2: about 1,593
-- visible trees on this map and no way for any agent tool to fell one. The
-- fort needs logs for building material (mason/carpenter/mechanic
-- workshops, wells, and any future construction) and this is the only
-- source (fort-owned WOOD stands at 3 units this session).
--
-- MECHANISM, verified from THIS install's own source this session,
-- `hack/scripts/internal/quickfort/dig.lua`:
--   - Tree felling is its OWN quickfort `#dig` symbol, `t`, wired to
--     `do_chop` -- a genuinely different action from `d` (mine), not a
--     shape/material special case of it.
--   - `do_chop(digctx)`: `if digctx.flags.hidden then return nil end` --
--     UNLIKE do_mine/do_down_stair (which admit a hidden tile
--     unconditionally, the act/sense rule df-overseer-diggable.lua now
--     encodes), do_chop REFUSES a hidden tile outright. There is no
--     "blind chop" case in this game's own source, so `trees.find`/
--     `trees.fell` require `dfhack.maps.isTileVisible` on every candidate
--     with no asymmetric hidden-tile admission -- the two rules already
--     agree here, unlike the dig case.
--   - On a revealed TREE-material tile, `do_chop` calls
--     `dfhack.maps.getPlantAtTile(pos)` then `values.dig_chop(plant)`,
--     which resolves (`values = values_run`) to
--     `dfhack.designations.markPlant` -- a real, confirmed DFHack Lua API,
--     not a struct write this project invented. `trees.fell` below calls
--     this SAME primitive directly rather than going through quickfort
--     with a dynamically generated blueprint (the shape df-overseer-
--     zone.lua's place_zone uses for an irregular water body): felling
--     targets scattered, non-adjacent single tiles across a search box,
--     which a rectangular quickfort grid can express (blank elsewhere) but
--     at more complexity for no behavioural difference from calling the
--     one-line primitive DFHack's own quickfort chop action already
--     reduces to. This is the same kind of choice df-overseer-farm.lua's
--     set_farm_crop already made (a direct struct/API write over a
--     quickfort blueprint) for an analogous reason -- not a new pattern.
--
-- LABOR AND TOOL, live-verified this session (not guessed):
--   `df.unit_labor.CUTWOOD` (index 10) is the wood-cutting labor.
--   This install's weapon itemdefs contain no plain "AXE" id -- only
--   `ITEM_WEAPON_AXE_BATTLE`/`_GREAT`/`_TRAINING` -- so "owns an axe" is
--   reported as the fort-owned count of any WEAPON item whose itemdef id
--   contains "AXE" (2 on this fort this session), not a single named
--   subtype; flagged rather than assumed to be exactly one canonical axe
--   type.
--
-- REACHABILITY: a standing tree occupies its own tile (TREE-material,
-- non-walkable), so felling is like mining a wall -- a dwarf works it from
-- an adjacent walkable tile, never by standing on it. `reachable` mirrors
-- df-overseer-diggable.lua's own ring-adjacency idea, simplified to a
-- single tile's 4 orthogonal neighbours (no landmark-group requirement,
-- since a lone tree far from the fort may still be validly reachable via
-- some other part of the walkable network `find_diggable_area`'s own
-- anchor-group check would incorrectly reject).
--
-- REPORT SHAPE: `trees.find` does NOT return one entry per tree -- roughly
-- 1,593 visible trees exist on this map, and per design commitment #1 no
-- coordinate would be returnable per-tree anyway. Matching the handoff's
-- own wording ("count, distance band, reachable"), it returns fixed-width
-- 10-tile distance bands out to the search radius, each with a tree count
-- and a reachable-tree count -- an aggregate a player could in principle
-- reconstruct by walking the map and counting, never a raw per-tile dump.
--
-- Usage: ./dfhack-run df-overseer-trees find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-trees fell N [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [DRY_RUN]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local BAND_WIDTH = 10
local CUTWOOD_LABOR = "CUTWOOD"

-- Revealed TREE-material tile, whether or not it is currently walkable
-- adjacent (that's the separate `reachable` field, not a filter here).
local function is_tree_tile(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis or not visible then
    return false
  end
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return false
  end
  local ok_mat, mat = pcall(function() return df.tiletype.attrs[tt].material end)
  return ok_mat and mat == df.tiletype_material.TREE
end

local function walkable_group(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group or 0
end

-- A tree tile is choppable in practice only if a dwarf can stand next to it
-- -- any of its 4 orthogonal neighbours is walkable. See header.
local function is_reachable(x, y, z)
  local neighbors = {{x + 1, y}, {x - 1, y}, {x, y + 1}, {x, y - 1}}
  for _, n in ipairs(neighbors) do
    if walkable_group(n[1], n[2], z) ~= 0 then
      return true
    end
  end
  return false
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

-- Every revealed tree tile in the scoped box, each tagged with its own
-- distance from the anchor and its reachability. Server-side only (real
-- coordinates kept per entry); find_trees/fell_trees strip or consume them
-- respectively.
local function scan_trees(z, ax, ay, min_x, max_x, min_y, max_y)
  local trees = {}
  for x = min_x, max_x do
    for y = min_y, max_y do
      if is_tree_tile(x, y, z) then
        local dx, dy = x - ax, y - ay
        table.insert(trees, {
          x = x, y = y,
          dist = math.sqrt(dx * dx + dy * dy),
          reachable = is_reachable(x, y, z),
        })
      end
    end
  end
  table.sort(trees, function(a, b) return a.dist < b.dist end)
  return trees
end

local function labor_enabled_count(labor_name)
  local code = df.unit_labor[labor_name]
  if not code then
    return 0
  end
  local n = 0
  for _, unit in ipairs(df.global.world.units.active) do
    local ok, is_cit = pcall(dfhack.units.isCitizen, unit)
    if ok and is_cit and unit.status.labors[code] then
      n = n + 1
    end
  end
  return n
end

-- Fort-owned count of any WEAPON item whose itemdef id contains "AXE" --
-- see header for why this is not a single named subtype on this install.
-- Same is_fort_owned test as df-overseer-stocks.lua (duplicated rather than
-- reqscript'd -- that file is not a touched surface this stream, matching
-- df-overseer-workshop.lua's own precedent for the identical choice).
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

local function count_fort_owned_axes()
  local vec = df.global.world.items.other.WEAPON
  local n = 0
  for i = 0, #vec - 1 do
    local item = vec[i]
    local ok, id = pcall(function() return item.subtype.id end)
    if ok and id and id:lower():find('axe') and is_fort_owned_item(item) then
      n = n + 1
    end
  end
  return n
end

function find_trees(level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local trees = scan_trees(z, ax, ay, ax - radius, ax + radius, ay - radius, ay + radius)

  local bands = {}
  local n_bands = math.ceil(radius / BAND_WIDTH)
  for i = 1, n_bands do
    bands[i] = {distance_tiles_max = i * BAND_WIDTH, count = 0, reachable_count = 0}
  end
  local total, total_reachable = 0, 0
  for _, t in ipairs(trees) do
    total = total + 1
    if t.reachable then
      total_reachable = total_reachable + 1
    end
    local band_idx = math.min(n_bands, math.floor(t.dist / BAND_WIDTH) + 1)
    bands[band_idx].count = bands[band_idx].count + 1
    if t.reachable then
      bands[band_idx].reachable_count = bands[band_idx].reachable_count + 1
    end
  end

  return {
    near_landmark = near,
    radius_tiles = radius,
    total_count = total,
    total_reachable = total_reachable,
    bands = bands,
    labor = CUTWOOD_LABOR,
    citizens_with_labor = labor_enabled_count(CUTWOOD_LABOR),
    fort_owned_axes = count_fort_owned_axes(),
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
-- trees and reports exactly what would be marked, without calling
-- dfhack.designations.markPlant on anything. Only an explicit false
-- performs the real mutation. UNTESTED live (mutation forbidden this
-- session) -- the underlying primitive (dfhack.designations.markPlant) is
-- confirmed from source to be exactly what quickfort's own `t` chop symbol
-- calls, not invented here.
function fell_trees(n, level, near, radius_tiles, dry_run)
  n = tonumber(n)
  if not n or n < 1 then
    return nil, "N must be a positive integer"
  end
  local dry = truthy_dry_run(dry_run)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local trees = scan_trees(z, ax, ay, ax - radius, ax + radius, ay - radius, ay + radius)
  local reachable = {}
  for _, t in ipairs(trees) do
    if t.reachable then
      table.insert(reachable, t)
    end
  end

  local chosen_n = math.min(n, #reachable)
  local chosen = {}
  for i = 1, chosen_n do
    table.insert(chosen, reachable[i])
  end

  local result = {
    dry_run = dry,
    requested = n,
    near_landmark = near,
    would_fell = chosen_n,
    nearest_distance_tiles = chosen_n > 0 and chosen[1].dist or nil,
    farthest_distance_tiles = chosen_n > 0 and chosen[chosen_n].dist or nil,
    labor = CUTWOOD_LABOR,
    citizens_with_labor = labor_enabled_count(CUTWOOD_LABOR),
    fort_owned_axes = count_fort_owned_axes(),
  }

  if dry then
    return result
  end

  -- Real mutation. Each chosen tile's own x,y,z exists only inside this
  -- loop's local scope, for the instant it takes to resolve the plant and
  -- mark it -- never printed or returned.
  local marked = 0
  for _, t in ipairs(chosen) do
    local ok_plant, plant = pcall(dfhack.maps.getPlantAtTile, xyz2pos(t.x, t.y, z))
    if ok_plant and plant then
      local ok_mark = pcall(dfhack.designations.markPlant, plant)
      if ok_mark then
        marked = marked + 1
      end
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
  local level, near, radius
  if tonumber(args[2]) then
    level, near, radius = tonumber(args[2]), args[3], tonumber(args[4])
  else
    near, radius = args[2], tonumber(args[3])
  end
  if not near then
    print("usage: df-overseer-trees find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local result, err = find_trees(level, near, radius)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "fell" then
  local n = args[2]
  local level, near, radius, dry_run
  if tonumber(args[3]) then
    level, near, radius, dry_run = tonumber(args[3]), args[4], tonumber(args[5]), args[6]
  else
    near, radius, dry_run = args[3], tonumber(args[4]), args[5]
  end
  if not (n and near) then
    print("usage: df-overseer-trees fell N [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [DRY_RUN]")
  else
    local result, err = fell_trees(n, level, near, radius, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-trees find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-trees fell N [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [DRY_RUN]")
end
