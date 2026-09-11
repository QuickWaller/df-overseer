-- df-overseer-diggable.lua
--@module = true
--
-- Closes the gap found live 2026-09-11 (research/2026-08-25-spatial-
-- perception.md's "Gap found live 2026-09-11" note, added to the spec on
-- `main` at 0a47c56/f48a641/89a04d2 -- NOT yet merged into this branch's
-- checkout of that file, read directly from those commits instead):
-- `find_open_area` (df-overseer-openarea.lua) only ever searches *walkable*
-- tiles -- confirmed live the hard way, running a `#dig` blueprint at a
-- find_open_area candidate designated zero tiles, because the candidate was
-- already-open floor. Nothing in the spec found a candidate region of
-- *solid, diggable* rock/soil. This is that primitive: the inverse of
-- find_open_area's is_free scan -- non-walkable, WALL-shaped, natural
-- (non-construction) material tiles instead of walkable ones -- otherwise
-- the same scoped maximal-rectangle-scan shape as find_open_area's
-- terrain="built" case (same MAX_RADIUS cap, same near-landmark anchoring,
-- same design commitment #1: real coordinates never leave this file).
--
-- Diggability check: a tile counts as diggable if (a) it is NOT walkable
-- (dfhack.maps.getWalkableGroup == 0 -- if it's already walkable it's not
-- solid, that's find_open_area's job) and (b) its tiletype shape is WALL
-- and (c) its tiletype material is one mining actually excavates: STONE,
-- SOIL, FEATURE (mineral/gem veins embedded in stone), MINERAL, LAVA_STONE,
-- or FROZEN_LIQUID (glacier ice). CONSTRUCTION (a built wall) is
-- deliberately excluded -- removing a construction is a different DFHack
-- job (`dig` vs `remove construction`), not what this primitive is for.
--
-- Reachability constraint (research spec, 0a47c56, corrected in 89a04d2):
-- a dig job needs a dwarf standing on an adjacent WALKABLE tile to mine
-- from -- the exact boundary-connectivity lesson this project already paid
-- for once (2026-09-10: a floor dig beneath a completed stair never became
-- a job because the connecting tile wasn't itself a matching stair type).
-- v1 scope, per the spec's own corrected call: only return candidates that
-- directly border the existing walkable network (same getWalkableGroup as
-- the search anchor, checked on the ring of tiles immediately surrounding
-- the WxH box). This is a reasonable, simple first cut, NOT a claim that
-- non-adjacent candidates are invalid -- a fuller version would instead
-- score non-adjacent candidates by connector-tunnel cost (the
-- entrance+connector+room pattern this project already uses) and let the
-- model choose to pay it, matching rank_candidate_sites' frontier/cost-and-
-- gain term. Not attempted here; v1 filters them out and says so in the
-- doc comment, not silently.
--
-- No `build`/dig-execution subcommand here (mirroring df-overseer-
-- openarea.lua's `build_open_area`) -- `designate_dig` (research spec
-- §5.2) is a separate, not-yet-built action tool. This file is perception
-- only: it answers "where could I dig," never "dig here."
--
-- Enum names verified against the actual installed DFHack 53.16-r1.1
-- (`memory/dfhack-environment.md`), not recalled from memory or web
-- results, per this project's "mark verified vs proposed" rule: WALL
-- (`df.tiletype_shape`) and STONE/SOIL/FEATURE/MINERAL/LAVA_STONE/
-- FROZEN_LIQUID (`df.tiletype_material`) all appear exactly this way in
-- the local install's own `hack/lua/tile-material.lua` (its `BasicMats`
-- table) and `hack/docs/docs/tools/tiletypes.txt`. NOT yet verified live
-- against VM 103's actual terrain -- no dfhack-run call against the fort
-- has happened for this file, only static verification against the
-- shipped DFHack source. Flag this as still-proposed behavior until a live
-- run confirms it, per the same rule.
--
-- Usage: ./dfhack-run df-overseer-diggable find W H Z NEAR_LANDMARK [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

local DIGGABLE_MATERIALS = {
  [df.tiletype_material.STONE] = true,
  [df.tiletype_material.SOIL] = true,
  [df.tiletype_material.FEATURE] = true,
  [df.tiletype_material.MINERAL] = true,
  [df.tiletype_material.LAVA_STONE] = true,
  [df.tiletype_material.FROZEN_LIQUID] = true,
}

local function walkable_group(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group or 0
end

-- Returns (is_diggable: bool, material: df.tiletype_material or nil).
-- A tile is diggable if it's solid (not walkable), shaped as a wall, and
-- made of a natural material mining actually excavates (see header).
local function is_diggable(x, y, z)
  if walkable_group(x, y, z) ~= 0 then
    return false
  end
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return false
  end
  local ok_shape, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  if not ok_shape or shape ~= df.tiletype_shape.WALL then
    return false
  end
  local ok_mat, mat = pcall(function() return df.tiletype.attrs[tt].material end)
  if not ok_mat or not DIGGABLE_MATERIALS[mat] then
    return false
  end
  return true, mat
end

-- Every top-left position where a w-by-h window is entirely diggable tiles,
-- within the given box at the given z. Mirrors find_candidates in
-- df-overseer-openarea.lua exactly, with is_diggable in place of is_free.
local function find_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local diggable, material = {}, {}
  for x = min_x, max_x do
    diggable[x] = {}
    material[x] = {}
    for y = min_y, max_y do
      local ok, mat = is_diggable(x, y, z)
      diggable[x][y] = ok
      material[x][y] = mat
    end
  end

  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      local fits = true
      for dx = 0, w - 1 do
        if not fits then break end
        for dy = 0, h - 1 do
          if not diggable[x + dx][y + dy] then
            fits = false
            break
          end
        end
      end
      if fits then
        table.insert(candidates, {x = x, y = y, material = material[x][y]})
      end
    end
  end
  return candidates
end

-- Two candidate windows (both w-by-h, top-left at a.x,a.y / b.x,b.y).
local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- True if any tile on the ring immediately surrounding the w-by-h box at
-- x,y (8-connected: cardinal and diagonal neighbors) is walkable and, when
-- required_group is given, shares that walkable group. required_group is
-- nil when the anchor landmark itself isn't on a resolvable walkable group
-- (rare -- falls back to "any walkable neighbor counts" rather than
-- rejecting every candidate over an anchor-side lookup failure).
local function borders_walkable_network(x, y, w, h, z, required_group)
  for rx = x - 1, x + w do
    for ry = y - 1, y + h do
      local on_ring = rx < x or rx >= x + w or ry < y or ry >= y + h
      if on_ring then
        local group = walkable_group(rx, ry, z)
        if group ~= 0 and (not required_group or group == required_group) then
          return true
        end
      end
    end
  end
  return false
end

-- Server-side only: ranked, deduplicated, non-overlapping, network-adjacent
-- top-left corners (real x,y coordinates, never stripped here) for a
-- WxH diggable region near `near`, closest-to-anchor first.
local function ranked_candidates(w, h, z, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local anchor_group = walkable_group(ax, ay, az)
  if anchor_group == 0 then
    anchor_group = nil
  end

  local candidates = find_candidates(
    w, h, z, ax - radius, ax + radius, ay - radius, ay + radius)

  local adjacent = {}
  for _, c in ipairs(candidates) do
    if borders_walkable_network(c.x, c.y, w, h, z, anchor_group) then
      table.insert(adjacent, c)
    end
  end

  for _, c in ipairs(adjacent) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(adjacent, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  -- Greedily keep only non-overlapping candidates, closest-to-anchor
  -- first, same dedup as find_open_area.
  local chosen = {}
  for _, c in ipairs(adjacent) do
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
  return chosen
end

function find_diggable_area(w, h, z, near, radius_tiles)
  local chosen, err = ranked_candidates(w, h, z, near, radius_tiles)
  if err then
    return nil, err
  end

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = c.x + math.floor((w - 1) / 2)
    local cy = c.y + math.floor((h - 1) / 2)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local info = ok_near and near_info
    local ok_mat_name, mat_name = pcall(function()
      return c.material and df.tiletype_material[c.material] or nil
    end)
    table.insert(results, {
      dims = {w, h},
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      -- Reported from this candidate's own top-left tile, not surveyed
      -- across the whole box -- informational only, a mixed-material
      -- region (e.g. stone shading into a mineral vein) is common and not
      -- itself disqualifying.
      material = ok_mat_name and mat_name or nil,
      borders_walkable_network = true,  -- v1 only returns these; see header
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
    print("usage: df-overseer-diggable find W H Z NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_diggable_area(w, h, z, near, radius)
    print(json.encode(err and {error = err} or results))
  end
else
  print("usage: df-overseer-diggable find W H Z NEAR_LANDMARK [RADIUS_TILES]")
end
