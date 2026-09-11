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
-- `dig` subcommand (added 2026-09-11, same session as find_diggable_area
-- itself, after find_diggable_area was live-verified against VM 103):
-- closes the loop the same way `build_open_area` did for `find_open_area`
-- (`decisions/DECISIONS.md` 2026-09-11, "Closed the coordinate-resolution
-- gap..."). `dig_diggable_area` is the fused resolve-and-act primitive --
-- NOT the research spec's original `designate_dig(shape, pos, dims)`
-- sketch (§5.2), which assumed some upstream tool would hand it a raw
-- `pos` and never specified one. Matching `build_open_area`'s exact shape
-- instead: takes a `blueprint_file` (a `#dig` quickfort blueprint, e.g.
-- `starter-room-5x5.csv`) rather than a `shape` enum, re-runs this file's
-- own `ranked_candidates`, resolves the chosen candidate's real cx,cy
-- internally, and calls `quickfort run BLUEPRINT_FILE -c cx,cy,z` directly
-- -- the coordinate exists only inside this function's local scope, for
-- the instant it takes to build quickfort's argument list, never returned
-- or printed. `parse_quickfort_stats` is intentionally duplicated from
-- `df-overseer-openarea.lua` rather than shared, to avoid touching that
-- file's own uncommitted in-flight changes (`build`/`build_open_area`,
-- Working.md 2026-09-11) for a few identical lines.
--
-- Real mutation, not a query: unlike `find_diggable_area`, calling `dig`
-- creates a genuine dig designation dwarves will act on -- treat a live
-- call the same as any other fort-mutating action this project already
-- gates (quicksave discipline, a peer/user heads-up), not like the
-- read-only `find` subcommand.
--
-- Enum names verified against the actual installed DFHack 53.16-r1.1
-- (`memory/dfhack-environment.md`), not recalled from memory or web
-- results, per this project's "mark verified vs proposed" rule: WALL
-- (`df.tiletype_shape`) and STONE/SOIL/FEATURE/MINERAL/LAVA_STONE/
-- FROZEN_LIQUID (`df.tiletype_material`) all appear exactly this way in
-- the local install's own `hack/lua/tile-material.lua` (its `BasicMats`
-- table) and `hack/docs/docs/tools/tiletypes.txt`.
--
-- `find_diggable_area` itself IS live-verified against VM 103/Uniboslan
-- (`decisions/DECISIONS.md` 2026-09-11, "live-verified against VM 103,
-- both a correct negative and a correct positive"): a correct empty
-- result near the surface Embark Site (nearby WALL-shaped tiles were all
-- TREE material, correctly excluded) and a correct set of 5 ranked SOIL
-- candidates underground near Stockpile #1. `dig_diggable_area`/`dig`
-- (below) is NOT yet live-tested -- unlike `find`, it's a real fort
-- mutation, so a live call needs the same explicit go-ahead as any other
-- mutating action this project gates, not just a peer heads-up.
--
-- Usage: ./dfhack-run df-overseer-diggable find W H Z NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-diggable dig W H Z NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]

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

-- Parses quickfort's own "Blueprint statistics:" block into a plain
-- label->count table. Line-anchored the same deliberate way as
-- df-overseer-openarea.lua's identical helper (see that file's comment for
-- the full rationale): "two leading spaces, label, colon, digits, nothing
-- else" can never match a coordinate-bearing line like dig.lua's own
-- "removing existing job at X, Y, Z", so no raw position can leak through
-- even if some other quickfort mode's stdout format changes later.
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

-- See the header comment above for the full design rationale. Picks
-- candidate `rank` (default 1) from the exact same ranking find_diggable_area
-- uses, resolves its real center coordinate, and runs
-- `quickfort run BLUEPRINT_FILE -c cx,cy,z` directly against it. The real
-- coordinate lives only in this function's own local scope -- never
-- assigned into, printed, or returned in anything handed back to the
-- caller. `blueprint_file` resolves relative to dfhack-config/blueprints/
-- on the guest (quickfort's own resolution rule, not this repo's tree) --
-- pass a bare filename already deployed there, e.g. `starter-room-5x5.csv`.
function dig_diggable_area(w, h, z, near, blueprint_file, rank, radius_tiles)
  rank = rank or 1
  local chosen, err = ranked_candidates(w, h, z, near, radius_tiles)
  if err then
    return nil, err
  end
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end

  local c = chosen[rank]
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)

  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local info = ok_near and near_info
  local ok_mat_name, mat_name = pcall(function()
    return c.material and df.tiletype_material[c.material] or nil
  end)

  -- The one place a real coordinate exists in this file: assembled
  -- directly into quickfort's own argument list, never stored anywhere
  -- else and never returned.
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', blueprint_file, '-c',
    string.format('%d,%d,%d', cx, cy, z))

  return {
    rank = rank,
    dims = {w, h},
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    material = ok_mat_name and mat_name or nil,
    blueprint = blueprint_file,
    quickfort_ok = ok_run and result == CR_OK,
    quickfort_error = (not ok_run) and tostring(output) or nil,
    quickfort_stats = ok_run and parse_quickfort_stats(output) or nil,
  }
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
elseif cmd == "dig" then
  local w, h, z = tonumber(args[2]), tonumber(args[3]), tonumber(args[4])
  local near = args[5]
  local blueprint = args[6]
  local rank = tonumber(args[7])
  local radius = tonumber(args[8])
  if not (w and h and z and near and blueprint) then
    print("usage: df-overseer-diggable dig W H Z NEAR_LANDMARK"
      .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES]")
  else
    local result, err = dig_diggable_area(w, h, z, near, blueprint, rank, radius)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-diggable find W H Z NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-diggable dig W H Z NEAR_LANDMARK"
    .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES]")
end
