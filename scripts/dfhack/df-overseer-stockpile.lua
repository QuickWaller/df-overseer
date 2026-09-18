-- df-overseer-stockpile.lua
--@module = true
--
-- handoffs/2026-09-18-lever-gap-tools.md deliverable 2: a read-only
-- stockpile tool. docs/PRODUCTION-MODEL.md §8 names stockpile occupancy as
-- one of the very few LEADING indicators this design has (a pile at 80% and
-- rising predicts a backed-up workshop before it happens), and §13's lever
-- table lists "stockpile link misconfigured" and "stockpile full" as two of
-- the six diagnoses no tool could previously act on or even see.
--
-- Two commands, both read-only:
--   list     -- every stockpile: id, landmark-relative name, occupied/total
--               tiles, coarse accept categories.
--   links ID -- the give/take links for one stockpile OR workshop building.
--
-- OCCUPIED / TOTAL TILES, verified live this session against Uniboslan's
-- two real stockpiles (ids 1 and 2, both full 5x5=25-tile rectangles, z168
-- and z169):
--
-- TOTAL: `dfhack.buildings.containsTile(bld, x, y)` walked over the
-- building's own x1..x2/y1..y2 bounding box, live-confirmed to return
-- exactly 25 for both piles, matching
-- `dfhack.buildings.countExtentTiles(bld, 0)` (also tried, also 25 on both
-- -- the two APIs agree). containsTile is used, not countExtentTiles,
-- because it is called per-tile, which lets each tile also get the
-- hidden-tile check below; countExtentTiles returns one opaque int with no
-- way to filter individual tiles. Neither pile carved any tile out of its
-- rectangle on this fort, so the exact-shape case (a non-rectangular pile)
-- is UNTESTED live -- the per-tile walk is written to handle it correctly
-- regardless (containsTile is exactly DFHack's own "is this tile part of
-- the extent" primitive), just not exercised against a real carved-out
-- example.
--
-- OCCUPIED: `dfhack.buildings.getStockpileContents(bld)` returns every item
-- in the pile (33 items in pile 1, 8 in pile 2, live-read), which is an
-- ITEM count, not a TILE count -- the handoff is explicit that the two must
-- not be conflated (a bin or a stack puts several items on one tile). Each
-- item's `dfhack.items.getPosition` was read and deduplicated by (x,y,z):
-- pile 1's 33 items resolved to 24 DISTINCT tile positions, all inside the
-- pile's own bounds -- confirmed live, not assumed. That distinct-position
-- count is "occupied tiles" here. A tile with a hidden position (see below)
-- is excluded from occupied same as from total, so the fraction stays
-- meaningful even if it can never happen for a player-built pile.
--
-- HIDDEN-TILE FILTER: mirrors df-overseer-stocks.lua's `is_on_hidden_tile`
-- (decisions/DECISIONS.md 2026-09-16, "agents may only know what a vanilla
-- player could know") -- same `dfhack.maps.isTileVisible` test, same
-- "unresolvable position treated as visible" fallback -- but reimplemented
-- as `is_hidden_tile(x, y, z)` here rather than reqscript'd, because that
-- function is item-scoped (`dfhack.items.getPosition(item)` inside it) and
-- this file also needs to test bare pile-extent tiles that may hold no
-- item at all. Both of Uniboslan's piles read fully visible, 0 hidden
-- tiles each, live-confirmed -- an honest, unsurprising result for a
-- fort's own built stockpile, not something this tool assumes.
--
-- ACCEPTS (coarse level, per the handoff's own wording): read from
-- `building.settings.flags`, confirmed live to be exactly DF's own 17
-- top-level stockpile-category toggles (animals, food, furniture, refuse,
-- stone, wood, gems, finished_goods, leather, cloth, sheet, bars_blocks,
-- weapons, armor, ammo, coins, corpses -- matching the in-game stockpile
-- settings screen's own category list, confirmed by enumerating the live
-- struct's string keys and finding exactly these 17, no more). Both of
-- Uniboslan's piles today accept the same five: food, furniture, stone,
-- wood, bars_blocks (live-read, general-purpose starting piles). This is
-- the coarse category toggle only, not the deep per-subtype filter
-- (`settings.food.prepared_meals`-style detail) -- the handoff asks for
-- "coarse level" explicitly.
--
-- LINKS: `building_stockpilest.links.{give,take}_{to,from}_{pile,workshop}`
-- for a stockpile, `building.profile.links` (same four field names) for a
-- workshop -- both confirmed live this session to be real struct fields on
-- Uniboslan's own buildings, matching
-- research/2026-09-18-schema-extraction-live.md §5's own finding. All four
-- vectors read empty (0) on both of Uniboslan's stockpiles and its one
-- workshop today: real, live-confirmed "not configured," not a read
-- failure. What each vector holds when non-empty (a pointer directly usable
-- as a building, versus a raw id needing a separate resolve) is NOT
-- independently exercised this session, since nothing on this fort is
-- linked -- `resolve_link_target` below is written defensively (pcall
-- around every field access) and marks an entry `resolved = false` rather
-- than guessing if this assumption turns out wrong once a real link exists.
--
-- Never a coordinate: every id below resolves to a landmark name/direction/
-- distance_tiles via df-overseer-landmarks.lua's own `nearest_landmark`,
-- the same helper df-overseer-workshop.lua already uses for this exact
-- purpose -- reused, not reinvented.
--
-- Usage: ./dfhack-run df-overseer-stockpile list
-- Usage: ./dfhack-run df-overseer-stockpile links ID

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

-- See header: mirrors df-overseer-stocks.lua's is_on_hidden_tile, adapted
-- to take a bare position rather than an item.
local function is_hidden_tile(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    return false
  end
  return not visible
end

-- DF's own 17 top-level stockpile category toggles, live-confirmed this
-- session (see header) -- listed explicitly rather than trusting pairs()
-- over `settings.flags`, whose live dump also carried a run of unnamed
-- integer-keyed bits (17-31) alongside the 17 named ones; only the named
-- keys are a category a player would recognise from the stockpile screen.
local CATEGORY_NAMES = {
  "animals", "food", "furniture", "refuse", "stone", "wood", "gems",
  "finished_goods", "leather", "cloth", "sheet", "bars_blocks", "weapons",
  "armor", "ammo", "coins", "corpses",
}

local function accepted_categories(bld)
  local ok_f, flags = pcall(function() return bld.settings.flags end)
  if not ok_f or not flags then
    return nil
  end
  local out = {}
  for _, name in ipairs(CATEGORY_NAMES) do
    local ok_v, v = pcall(function() return flags[name] end)
    if ok_v and v then
      table.insert(out, name)
    end
  end
  return out
end

-- See header: per-tile containsTile walk, not the opaque countExtentTiles
-- int, so each tile can also get the hidden-tile check. Returns
-- (total_tiles, exact) -- exact is false only if containsTile itself could
-- not be called at all (API missing), in which case total_tiles falls back
-- to countExtentTiles with no per-tile hidden filter, and the caller must
-- say so rather than presenting it as equally precise.
local function total_tiles(bld)
  local any_ok = false
  local n = 0
  for x = bld.x1, bld.x2 do
    for y = bld.y1, bld.y2 do
      local ok_c, inside = pcall(dfhack.buildings.containsTile, bld, x, y)
      if ok_c then
        any_ok = true
        if inside and not is_hidden_tile(x, y, bld.z) then
          n = n + 1
        end
      end
    end
  end
  if any_ok then
    return n, true
  end
  local ok_ext, ext_n = pcall(dfhack.buildings.countExtentTiles, bld, 0)
  return (ok_ext and ext_n) or nil, false
end

-- See header: item-position dedup, not the raw item count.
local function occupied_tiles(bld)
  local ok_items, items = pcall(dfhack.buildings.getStockpileContents, bld)
  if not ok_items or not items then
    return nil
  end
  local seen = {}
  local n = 0
  for _, it in ipairs(items) do
    local ok_pos, x, y, z = pcall(dfhack.items.getPosition, it)
    if ok_pos and x and not is_hidden_tile(x, y, z) then
      local key = x .. "," .. y .. "," .. z
      if not seen[key] then
        seen[key] = true
        n = n + 1
      end
    end
  end
  return n
end

local function landmark_info(x1, x2, y1, y2, z)
  local cx = math.floor((x1 + x2) / 2 + 0.5)
  local cy = math.floor((y1 + y2) / 2 + 0.5)
  local ok_near, info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  return ok_near and info or nil
end

function list_stockpiles()
  local out = {}
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_type, btype = pcall(function() return bld:getType() end)
    if ok_type and btype == df.building_type.Stockpile then
      local total, total_exact = total_tiles(bld)
      local info = landmark_info(bld.x1, bld.x2, bld.y1, bld.y2, bld.z)
      table.insert(out, {
        id = bld.id,
        near_landmark = info and info.name or nil,
        direction = info and info.direction or nil,
        distance_tiles = info and info.distance_tiles or nil,
        occupied_tiles = occupied_tiles(bld),
        total_tiles = total,
        total_tiles_exact = total_exact,
        accepts = accepted_categories(bld),
      })
    end
  end
  return {stockpiles = out}
end

local LINK_FIELDS = {
  "give_to_pile", "take_from_pile", "give_to_workshop", "take_from_workshop",
}

-- See header: defensive on purpose -- nothing on Uniboslan is linked today,
-- so the "target is a usable building pointer" assumption is untested live.
local function resolve_link_target(target)
  local ok_id, id = pcall(function() return target.id end)
  if not ok_id or not id then
    return nil
  end
  local ok_type, btype = pcall(function() return target:getType() end)
  local kind = ok_type and df.building_type[btype] or nil
  local ok_bounds, x1, x2, y1, y2, z =
    pcall(function()
      return target.x1, target.x2, target.y1, target.y2, target.z
    end)
  local info = ok_bounds and landmark_info(x1, x2, y1, y2, z) or nil
  return {
    id = id,
    kind = kind,
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
  }
end

local function read_links(links_struct)
  local out = {}
  for _, field in ipairs(LINK_FIELDS) do
    local entry = {count = 0, targets = {}, resolved = true}
    local ok_vec, vec = pcall(function() return links_struct[field] end)
    if ok_vec and vec then
      local ok_len, n = pcall(function() return #vec end)
      if ok_len then
        entry.count = n
        for i = 0, n - 1 do
          local ok_t, t = pcall(function() return vec[i] end)
          local resolved = ok_t and t and resolve_link_target(t)
          if resolved then
            table.insert(entry.targets, resolved)
          elseif n > 0 then
            entry.resolved = false
          end
        end
      else
        entry.resolved = false
      end
    else
      entry.resolved = false
    end
    out[field] = entry
  end
  return out
end

function stockpile_links(id)
  id = tonumber(id)
  if not id then
    return nil, "ID must be a number"
  end
  local found = nil
  for _, bld in ipairs(df.global.world.buildings.all) do
    if bld.id == id then
      found = bld
      break
    end
  end
  if not found then
    return nil, "no building with id " .. tostring(id)
  end
  local ok_type, btype = pcall(function() return found:getType() end)
  if not ok_type then
    return nil, "could not resolve building type for id " .. tostring(id)
  end
  if btype == df.building_type.Stockpile then
    return {id = id, kind = "stockpile", links = read_links(found.links)}
  elseif btype == df.building_type.Workshop then
    local ok_p, prof = pcall(function() return found.profile end)
    if not ok_p or not prof then
      return nil, "workshop id " .. tostring(id) .. " has no profile"
    end
    return {id = id, kind = "workshop", links = read_links(prof.links)}
  else
    local ok_name, name = pcall(function() return df.building_type[btype] end)
    return nil, "id " .. tostring(id) .. " is not a stockpile or workshop ("
      .. (ok_name and name or "unknown type") .. ")"
  end
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "list" then
  print(json.encode(list_stockpiles()))
elseif cmd == "links" then
  local id = args[2]
  if not id then
    print("usage: df-overseer-stockpile links ID")
  else
    local result, err = stockpile_links(id)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-stockpile list")
  print("usage: df-overseer-stockpile links ID")
end
