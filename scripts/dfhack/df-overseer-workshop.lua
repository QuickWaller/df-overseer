-- df-overseer-workshop.lua
--@module = true
--
-- handoffs/2026-09-16-farm-and-still-tools.md Part 3: the fort has no
-- still (so no way to turn any of its four brewable owned crops -- plump
-- helmet, pig tail, cave wheat, sweet pod -- into drink) and no kitchen.
-- This file finds and builds workshops, landmark-relative, no raw
-- coordinates ever crossing the model boundary (design commitment #1).
-- Only `still` and `kitchen` are covered -- the two the handoff names.
--
-- REUSES df-overseer-openarea.lua's `is_free` directly (reqscript'd,
-- exported there 2026-09-16 for exactly this), per the handoff's own
-- instruction: a workshop's site rule is identical to find_open_area's
-- ("any walkable, building-free, revealed tile") -- unlike
-- df-overseer-farm.lua (Part 2), whose ground rule is materially
-- different (specific dirt/mud floor) and so mirrors quickfort's own
-- is_valid_tile_farm instead of reusing is_free. Same fused
-- perceive-then-act idiom as every other df-overseer-*.lua file:
-- `ranked_candidates` is shared by `find` and `build`, and a real
-- coordinate exists only inside a function's own local scope for the
-- instant it takes to build quickfort's argument list.
--
-- Both workshops are a fixed 3x3 footprint (ordinary DFHack/DF workshop
-- size), placed via quickfort's own `#build` symbols -- read directly from
-- this install's hack/scripts/internal/quickfort/build.lua, not guessed:
-- `wl` = Still (Workshop, subtype Still), `wz` = Kitchen (Workshop, subtype
-- Kitchen). Since `is_free` already requires isTileVisible (the
-- 2026-09-16 knowledge-scope fix) and building-free, this tool inherits
-- that guarantee with no separate visibility check needed here.
--
-- WHAT A WORKSHOP NEEDS TO OPERATE, reported alongside every candidate
-- (not a separate command -- the handoff names only find/build for this
-- part) so the caller can act on it directly:
--   - `labor`: the df.unit_labor code name that must be enabled on at
--     least one citizen for the workshop to ever produce anything --
--     BREWER (confirmed live this session, code 30) for a still, COOK
--     (confirmed live, code 38) for a kitchen. Read the same way
--     df-overseer-labor.lua's list_labors reads a unit's own labors
--     (unit.status.labors[code]), never written here -- this stream builds
--     no manager orders or labor assignments, per the handoff's own limit.
--   - `citizens_with_labor`: how many citizens already have it enabled
--     (1 BREWER already, live this session -- likely autolabor's own
--     doing, not this project's).
--   - `needs_container`/`fort_owned_containers`: a still's output (drink)
--     needs a barrel. `df-overseer-stocks.lua` is NOT a touched surface
--     for this stream (handoff's own surface list), so this file counts
--     fort-owned BARREL items itself rather than extending that file --
--     the exact same is_fort_owned test (not flags.trader, not
--     garbage_collect/removed, not on a hidden tile) as
--     df-overseer-stocks.lua uses, duplicated deliberately rather than
--     risking a concurrent stream's own in-flight changes to that file.
--     23 BARREL items exist fort-wide this session (not yet filtered for
--     ownership at the time this was checked); the filtered, live count is
--     computed fresh on every call, never cached. A kitchen's output
--     (prepared meals) does not strictly need a container to be produced,
--     so `needs_container` is nil for kitchen.
--
-- Dry-run mode (same contract as df-overseer-farm.lua's write commands):
-- `build_workshop` defaults DRY_RUN to true. A dry run resolves the
-- candidate and returns exactly what would be built, without calling
-- quickfort. Only an explicit `false` performs the real mutation. This
-- session only ever calls with DRY_RUN true (the fort must stay paused and
-- unmutated).
--
-- Addressability: unlike df-overseer-farm.lua's build_farm_plot, this file
-- does NOT explicitly rename the building it creates. A workshop's own
-- DF-default name was not verified here (this session cannot build one to
-- check), and df-overseer-landmarks.lua's building enumeration already
-- picks up ANY building with a non-empty dfhack.buildings.getName() with
-- no code change needed if that default turns out sensible -- flagged as
-- unverified rather than assumed, matching this project's own "mark
-- verified vs proposed" rule.
--
-- Usage: ./dfhack-run df-overseer-workshop find W H [LEVEL] NEAR_LANDMARK KIND [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-workshop build W H [LEVEL] NEAR_LANDMARK KIND BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local openarea_mod = reqscript('df-overseer-openarea')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

-- workshop_type read directly from hack/scripts/internal/quickfort/build.lua
-- on this install (its `wl`/`wz` #build symbol entries), not guessed.
local KIND_INFO = {
  still = {label = "Still", subtype = df.workshop_type.Still,
    labor = "BREWER", needs_container = "BARREL"},
  kitchen = {label = "Kitchen", subtype = df.workshop_type.Kitchen,
    labor = "COOK", needs_container = nil},
}

-- Same is_fort_owned test as df-overseer-stocks.lua (not flags.trader, not
-- garbage_collect/removed, not on a hidden tile) -- duplicated rather than
-- reqscript'd, see header for why (stocks.lua is not a touched surface
-- this stream).
local function is_fort_owned_item(item)
  local f = item.flags
  if f.trader or f.garbage_collect or f.removed then
    return false
  end
  local ok_pos, x, y, z = pcall(dfhack.items.getPosition, item)
  if ok_pos and x then
    local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
    if ok_vis and not visible then
      return false
    end
  end
  return true
end

local function count_fort_owned(item_type_other_id)
  local ok, vec = pcall(function() return df.global.world.items.other[item_type_other_id] end)
  if not ok or not vec then
    return 0
  end
  local n = 0
  for i = 0, #vec - 1 do
    if is_fort_owned_item(vec[i]) then
      n = n + 1
    end
  end
  return n
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

local function requirements_for(kind_info)
  local req = {
    labor = kind_info.labor,
    citizens_with_labor = labor_enabled_count(kind_info.labor),
  }
  if kind_info.needs_container then
    req.needs_container = kind_info.needs_container
    req.fort_owned_containers = count_fort_owned(kind_info.needs_container)
  end
  return req
end

local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- Duplicated from df-overseer-openarea.lua/df-overseer-diggable.lua rather
-- than shared -- see either file's own comment for why.
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

-- Every top-left position where a w-by-h window is entirely free tiles
-- (openarea_mod.is_free -- see header), within the given box at the given
-- z. Same shape as openarea's own find_candidates, but calling the
-- reqscript'd is_free rather than a local copy.
local function find_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local free = {}
  for x = min_x, max_x do
    free[x] = {}
    for y = min_y, max_y do
      free[x][y] = openarea_mod.is_free(x, y, z)
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

function find_workshop_area(w, h, level, near, kind, radius_tiles)
  local kind_info = KIND_INFO[tostring(kind):lower()]
  if not kind_info then
    return nil, "unknown workshop kind: " .. tostring(kind) .. " (expected still/kitchen)"
  end
  local chosen, err, resolved_z = ranked_candidates(w, h, level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z
  local req = requirements_for(kind_info)

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = c.x + math.floor((w - 1) / 2)
    local cy = c.y + math.floor((h - 1) / 2)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local info = ok_near and near_info
    table.insert(results, {
      dims = {w, h},
      kind = kind_info.label,
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      requirements = req,
    })
  end
  return results
end

-- DRY_RUN defaults to true. A dry run resolves the candidate and returns
-- exactly what would be built, without calling quickfort. See header --
-- the real path is UNTESTED live (mutation forbidden this session).
function build_workshop(w, h, level, near, kind, blueprint_file, rank, radius_tiles, dry_run)
  local kind_info = KIND_INFO[tostring(kind):lower()]
  if not kind_info then
    return nil, "unknown workshop kind: " .. tostring(kind) .. " (expected still/kitchen)"
  end
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
  local req = requirements_for(kind_info)

  if dry then
    return {
      dry_run = true,
      rank = rank,
      dims = {w, h},
      kind = kind_info.label,
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      requirements = req,
      would_run_blueprint = blueprint_file,
    }
  end

  -- Real mutation. Same top-left anchoring as every other build_* in this
  -- project (c.x,c.y, the validated top-left, never the computed center).
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', blueprint_file, '-c',
    string.format('%d,%d,%d', c.x, c.y, z))

  return {
    dry_run = false,
    rank = rank,
    dims = {w, h},
    kind = kind_info.label,
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

-- KIND always immediately follows NEAR_LANDMARK -- LEVEL is optional the
-- same way every other df-overseer-*.lua file handles it (args[4] read as
-- LEVEL only when it parses as a number).
if cmd == "find" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, kind, radius
  if tonumber(args[4]) then
    level, near, kind, radius = tonumber(args[4]), args[5], args[6], tonumber(args[7])
  else
    near, kind, radius = args[4], args[5], tonumber(args[6])
  end
  if not (w and h and near and kind) then
    print("usage: df-overseer-workshop find W H [LEVEL] NEAR_LANDMARK KIND [RADIUS_TILES]")
  else
    local results, err = find_workshop_area(w, h, level, near, kind, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "build" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, kind, blueprint, rank, radius, dry_run
  if tonumber(args[4]) then
    level, near, kind, blueprint, rank, radius, dry_run =
      tonumber(args[4]), args[5], args[6], args[7], tonumber(args[8]), tonumber(args[9]), args[10]
  else
    near, kind, blueprint, rank, radius, dry_run =
      args[4], args[5], args[6], tonumber(args[7]), tonumber(args[8]), args[9]
  end
  if not (w and h and near and kind and blueprint) then
    print("usage: df-overseer-workshop build W H [LEVEL] NEAR_LANDMARK KIND"
      .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]")
  else
    local result, err = build_workshop(w, h, level, near, kind, blueprint, rank, radius, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-workshop find W H [LEVEL] NEAR_LANDMARK KIND [RADIUS_TILES]")
  print("usage: df-overseer-workshop build W H [LEVEL] NEAR_LANDMARK KIND"
    .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES] [DRY_RUN]")
end
