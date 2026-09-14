-- df-overseer-chokepoints.lua
--@module = true
--
-- docs/PURPOSE.md build order item 7 (first half): find_chokepoints, a
-- deliberately cheap heuristic approximation of BWTA
-- (research/2026-08-25-spatial-perception.md §2.5/§5.3), not a full
-- Voronoi-skeleton port. Scoped near a landmark, radius-capped (same
-- pattern and hard cap as df-overseer-openarea.lua's find_open_area).
--
-- Two chokepoint kinds, not one -- the research doc's own §5.3 sketch
-- only describes the first:
--   "corridor": a walkable, building-free tile on the SAME z-level whose
--     two tiles perpendicular to some axis are both non-walkable -- i.e.
--     the passage is exactly one tile wide there. This is the literal
--     heuristic §5.3 describes: "a boundary tile is a chokepoint
--     candidate if the two tiles perpendicular to the boundary-crossing
--     direction are both non-walkable."
--   "stair": any up/down/updown stair or ramp tile in the box. NOT in the
--     research doc's sketch -- added because it's the single most common
--     real chokepoint shape in an actual DF fort (one staircase connecting
--     a dug room to the surface, confirmed live on Uniboslan: a
--     soil-stair-up at z168 paired with a stone-stair-down at z169,
--     x=100,y=96 -- the sole z-transition for the current room). A same-
--     z-level-only corridor scan would never find this, and it is
--     arguably the more common bottleneck shape than a horizontal 1-wide
--     hallway in an early-game fort. Deliberately coarse: this flags
--     EVERY stair/ramp tile in the box, without proving it is the SOLE
--     connector between two walkable groups (that would need a real
--     graph-cut check -- removing the tile and re-testing connectivity --
--     which this first slice does not attempt). Treat "stair" results as
--     "likely narrow points," not proven-unique bottlenecks.
--
-- This deviates from the research spec's exact output shape in one
-- honest, documented way: the spec wants `between: [landmark_a,
-- landmark_b]` (the two named regions a chokepoint sits between), which
-- assumes region-pair adjacency data this project's landmark system does
-- not track yet (landmarks currently expose a centroid + nearest-N exits,
-- not full region extents/boundaries -- see df-overseer-landmarks.lua).
-- Building real region-pair adjacency is real, separate work, not
-- attempted here. Instead each result carries `near_landmark` (singular,
-- via nearest_landmark, reqscript'd) -- an honest simplification, not a
-- silent substitution.
--
-- `pos_for_action_tools` deliberately DOES carry a raw coordinate, per
-- the research spec's own explicit exception (§5): "the one place in this
-- tool set where a raw coordinate is the point of the output -- a door/
-- trap has to be built somewhere specific." Design commitment #1 is not
-- violated by this -- the model is handed a short, bounded, pre-computed
-- list, never asked to derive the coordinate itself from geometry.
--
-- Z REPLACED WITH LEVEL, now optional, an offset relative to NEAR_LANDMARK's
-- own z rather than a required absolute DF coordinate (gap found live
-- 2026-09-14, handoffs/2026-09-14-relative-level-args.md -- see
-- df-overseer-openarea.lua's header for the full story of the same change
-- there). This file's `find` was the one command in the three-file gap that
-- required an absolute Z at all, with no default -- every caller had to
-- already know a real DF z-coordinate just to call it, the same problem the
-- other two files had already closed by defaulting. LEVEL keeps the same
-- argument position (still the first argument after the verb) so the
-- CLI stays parseable the same way as find_open_area/find_diggable_area:
-- a numeric first argument is LEVEL, otherwise it's NEAR_LANDMARK and LEVEL
-- defaults to 0 (the landmark's own level). `resolve_level` (duplicated from
-- df-overseer-openarea.lua/df-overseer-diggable.lua) adds az + LEVEL and
-- validates against the real map bounds (dfhack.maps.getSize()'s
-- z_count_block) -- a level outside the map is a returned error naming
-- LEVEL and the landmark, never the resolved absolute z, instead of
-- whatever find_chokepoints would have done with a nonsense absolute z
-- (an empty or garbage result, never tested against an out-of-range value).
--
-- Usage: ./dfhack-run df-overseer-chokepoints find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 10

local function walkable(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group ~= 0
end

local function free(x, y, z)
  if not walkable(x, y, z) then
    return false
  end
  local ok, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(x, y, z))
  return ok and not bld
end

local function is_stair_or_ramp(x, y, z)
  local ok, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok or not tt then
    return false
  end
  local ok2, caption = pcall(function() return df.tiletype.attrs[tt].caption end)
  if not ok2 or not caption then
    return false
  end
  return caption:find('[Ss]tair') ~= nil or caption:find('[Rr]amp') ~= nil
end

-- A "corridor" chokepoint: free, and either its N/S neighbors are both
-- non-walkable while E/W are both walkable (an east-west 1-wide passage),
-- or the mirror image (a north-south 1-wide passage).
local function is_corridor_chokepoint(x, y, z)
  if not free(x, y, z) then
    return false
  end
  local n, s, e, w = walkable(x, y - 1, z), walkable(x, y + 1, z),
                     walkable(x + 1, y, z), walkable(x - 1, y, z)
  return (not n and not s and e and w) or (not e and not w and n and s)
end

-- LEVEL is an offset relative to a landmark's own level (0/nil = same level,
-- negative = below, positive = above), never an absolute DF z-coordinate --
-- see the file header for why. Returns the resolved absolute z, or nil plus
-- an error naming LEVEL and landmark_name (never the resolved absolute
-- value, per design commitment #1) if that level doesn't exist on this map.
-- Duplicated identically in df-overseer-openarea.lua and
-- df-overseer-diggable.lua rather than shared -- a small, self-contained,
-- pure function with no chokepoints-specific state.
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

function find_chokepoints(level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)
  local min_x, max_x, min_y, max_y = ax - radius, ax + radius, ay - radius, ay + radius

  local hits = {}
  for x = min_x, max_x do
    for y = min_y, max_y do
      if is_corridor_chokepoint(x, y, z) then
        table.insert(hits, {x = x, y = y, z = z, kind = "corridor"})
      elseif is_stair_or_ramp(x, y, z) and walkable(x, y, z) then
        table.insert(hits, {x = x, y = y, z = z, kind = "stair"})
      end
    end
  end

  for _, h in ipairs(hits) do
    local dx, dy = h.x - ax, h.y - ay
    h.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(hits, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local results = {}
  for i, h in ipairs(hits) do
    if i > MAX_RESULTS then
      break
    end
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, h.x, h.y, h.z)
    local info = ok_near and near_info
    table.insert(results, {
      kind = h.kind,
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      pos_for_action_tools = {h.x, h.y, h.z},
      width_tiles = 1,
    })
  end
  return results
end

-- Same module-load guard as the other df-overseer-*.lua scripts.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

-- LEVEL is optional (see file header): args[2] is read as LEVEL only when
-- it parses as a number, otherwise it's NEAR_LANDMARK and RADIUS_TILES
-- shifts left by one, with level left nil so find_chokepoints defaults it
-- to 0 (the landmark's own level). Same sniff-the-next-token technique
-- df-overseer-openarea.lua/df-overseer-diggable.lua use, just starting one
-- slot earlier since this command has no W/H ahead of LEVEL.
if cmd == "find" then
  local level, near, radius
  if tonumber(args[2]) then
    level, near, radius = tonumber(args[2]), args[3], tonumber(args[4])
  else
    near, radius = args[2], tonumber(args[3])
  end
  if not near then
    print("usage: df-overseer-chokepoints find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_chokepoints(level, near, radius)
    print(json.encode(err and {error = err} or results))
  end
else
  print("usage: df-overseer-chokepoints find [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
end
