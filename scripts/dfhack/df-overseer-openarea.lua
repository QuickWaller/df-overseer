-- df-overseer-openarea.lua
--@module = true
--
-- docs/PURPOSE.md build order item 6: find_open_area, terrain="built",
-- hard radius cap from day one (research/2026-08-25-spatial-perception.md
-- §5.3). This is terrain="built" only -- the maximal-rectangle-style scan
-- over gridded/constructed space. terrain="cavern" (build order item 9,
-- deliberately last) needs a genuinely different algorithm (a distance-
-- transform/clustering split of an irregular walkable region, not a
-- rectangle scan) and is NOT attempted here.
--
-- Scoped, never whole-map, per design commitment #1 and the research
-- doc's own caution (BWTA's history: a mature, purpose-built terrain
-- analysis algorithm was slow enough on StarCraft-sized maps to justify a
-- 10x-faster sequel -- don't assume any region scan is free by default).
-- `near` (a landmark name, required -- resolved via
-- df-overseer-landmarks.lua's get_landmark_centroid, reqscript'd) anchors
-- the search box; `radius_tiles` is clamped to a hard cap (60) in code,
-- not just documented as a recommendation, matching the research doc's
-- explicit instruction to enforce this at the tool-schema level.
--
-- A tile is "free" if it's walkable (dfhack.maps.getWalkableGroup ~= 0,
-- confirmed live: 0 on a solid wall, a real group id like 11 on open
-- floor) and carries no building (dfhack.buildings.findAtTile, confirmed
-- live: nil on open floor, a real building pointer on a stockpile tile).
-- Per the documented caveat on getWalkableGroup (Lua API.txt, repeated in
-- research/2026-08-25-spatial-perception.md §3.2): this cache only
-- updates while the game is unpaused. Not a live risk today (DF does not
-- simulate at all while paused, so nothing can go stale mid-query), but
-- worth remembering for a future consumer that calls this immediately
-- after an unpause.
--
-- Candidate search: for this first slice, a plain O(box_area * w * h)
-- window check, not the classic histogram/stack "largest rectangle"
-- algorithm the research doc's own §5.3 sketch describes -- deliberately
-- simpler to write and verify correctly, and cheap enough at the capped
-- box size (up to 121x121 tiles) for the small room dimensions this
-- project actually designs with (2x2 embarks, 5x5 starter rooms). Revisit
-- if profiling ever shows this matters at a larger scale.
--
-- Each returned candidate's near_landmark/direction/distance_tiles
-- describes the candidate's OWN nearest landmark (via nearest_landmark,
-- reqscript'd), which is usually but not necessarily the same landmark
-- used to scope the search box -- e.g. a large open area's center could
-- end up closer to a different landmark than the one it was searched
-- "near".
--
-- Usage: ./dfhack-run df-overseer-openarea find W H Z NEAR_LANDMARK [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

local function is_free(x, y, z)
  local pos = xyz2pos(x, y, z)
  local ok_walk, group = pcall(dfhack.maps.getWalkableGroup, pos)
  if not ok_walk or group == 0 then
    return false
  end
  local ok_bld, bld = pcall(dfhack.buildings.findAtTile, pos)
  return ok_bld and not bld
end

-- Every top-left position where a w-by-h window is entirely free tiles,
-- within the given box at the given z.
local function find_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local free = {}
  for x = min_x, max_x do
    free[x] = {}
    for y = min_y, max_y do
      free[x][y] = is_free(x, y, z)
    end
  end

  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      local fits = true
      for dx = 0, w - 1 do
        if not fits then break end
        for dy = 0, h - 1 do
          if not free[x + dx][y + dy] then
            fits = false
            break
          end
        end
      end
      if fits then
        table.insert(candidates, {x = x, y = y})
      end
    end
  end
  return candidates
end

-- Two candidate windows (both w-by-h, top-left at a.x,a.y / b.x,b.y).
local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

function find_open_area(w, h, z, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local candidates = find_candidates(
    w, h, z, ax - radius, ax + radius, ay - radius, ay + radius)

  for _, c in ipairs(candidates) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(candidates, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  -- Greedily keep only non-overlapping candidates, closest-to-anchor
  -- first, so results aren't N near-duplicate placements one tile apart.
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

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = c.x + math.floor((w - 1) / 2)
    local cy = c.y + math.floor((h - 1) / 2)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local ok_group, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(cx, cy, z))
    local info = ok_near and near_info
    table.insert(results, {
      dims = {w, h},
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      walkable_group = ok_group and group or -1,
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

if cmd == "find" then
  local w, h, z = tonumber(args[2]), tonumber(args[3]), tonumber(args[4])
  local near = args[5]
  local radius = tonumber(args[6])
  if not (w and h and z and near) then
    print("usage: df-overseer-openarea find W H Z NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_open_area(w, h, z, near, radius)
    print(json.encode(err and {error = err} or results))
  end
else
  print("usage: df-overseer-openarea find W H Z NEAR_LANDMARK [RADIUS_TILES]")
end
