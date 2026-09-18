-- df-overseer-workshop.lua
--@module = true
--
-- handoffs/2026-09-16-farm-and-still-tools.md Part 3: the fort has no
-- still (so no way to turn any of its four brewable owned crops -- plump
-- helmet, pig tail, cave wheat, sweet pod -- into drink) and no kitchen.
-- This file finds and builds workshops, landmark-relative, no raw
-- coordinates ever crossing the model boundary (design commitment #1).
-- Originally `still`/`kitchen` only, the two that handoff named.
--
-- EXTENDED handoffs/2026-09-17-water-and-industry-tools.md item 3: `mason`,
-- `mechanic`, `carpenter` -- see KIND_INFO below for their own #build
-- symbols/labors and `building_material_report` for the generic
-- boulder/log/block requirement all five kinds share (live-verified this
-- session to be identical across all five, not assumed).
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
--   - `named_requirement` (kitchen only, added 2026-09-16 per the user's
--     own real-world input): "restrict cooking of plants and seeds needed
--     for replanting, or the farm loses its seed stock" -- cooking a plant
--     or its seed consumes it with no seed returned, unlike eating it raw
--     or brewing it, which does return a seed; an unrestricted kitchen can
--     cook through the exact seed stock a farm depends on. **No
--     cooking-restriction tool is built in this stream** (out of scope,
--     per the user's own instruction) -- this is read-only investigation,
--     reported as data.
--   - `seed_protection` (kitchen only): where this setting actually lives
--     on this install, investigated read-only, not by designating or
--     toggling anything: `df.global.plotinfo.kitchen` is the vanilla
--     Kitchen-tab exclusion list -- five parallel arrays
--     (`exc_types`/`item_types`/`item_subtypes`/`mat_types`/`mat_indices`),
--     confirmed live this session (110 entries, all `item_type == SEEDS`).
--     **This install's own DEFAULT kitchen settings already exclude every
--     known plant's SEEDS item-type from cooking**, including all six of
--     this fort's owned crops -- MUSHROOM_HELMET_PLUMP, GRASS_TAIL_PIG,
--     GRASS_WHEAT_CAVE, POD_SWEET, BUSH_QUARRY and MUSHROOM_CUP_DIMPLE
--     were each found present in the live exclusion list by mat_index,
--     cross-checked against df.global.world.raws.plants.all the same way
--     df-overseer-stocks.lua resolves a SEEDS item's plant name. So the
--     vanilla safeguard the user described is already active for this
--     fort's own seeds, by DF's own default, before this project ever
--     touches a kitchen -- not something this stream added or needs to.
--     No entry with `item_type == PLANT` (the harvested crop, as opposed
--     to its seed) was found for any of the six; not investigated further
--     since replanting only ever consumes SEEDS, never the harvested
--     PLANT item, in the mechanism df-overseer-farm.lua's set_farm_crop
--     already relies on. `seed_protection` reports, per fort-owned seed
--     (from df-overseer-stocks.lua's get_seeds(), reqscript'd -- reading
--     that file, not editing it, so it stays outside this stream's
--     touched-surfaces list), whether it is currently in this exclusion
--     list -- computed fresh on every call, never cached, so a later
--     change to the setting (in-game or otherwise) is reflected
--     immediately rather than baked into this file's own assumption.
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
-- Read-only use of df-overseer-stocks.lua's get_seeds() (fort-owned seed
-- ids), for the kitchen seed_protection check below -- reqscript reads
-- that file, it does not edit it, so this stays outside this stream's
-- touched-surfaces list (see header).
local stocks_mod = reqscript('df-overseer-stocks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

-- workshop_type read directly from hack/scripts/internal/quickfort/build.lua
-- on this install (its `wl`/`wz` #build symbol entries), not guessed.
--
-- ADDED handoffs/2026-09-17-water-and-industry-tools.md item 3: `mason`,
-- `mechanic`, `carpenter` -- the three workshops the well/orders tools
-- depend on (blocks, mechanisms, and this project's own building-material
-- reporting need all three). Their own #build symbols (`wm`/`wt`/`wc`) and
-- labors (`MASON`/`MECHANIC`/`CARPENTER`) were each read directly from this
-- install's own build.lua/df.unit_labor this session, matching the exact
-- verification standard still/kitchen already set. None needs a container
-- (mason/mechanic/carpenter output blocks/mechanisms/finished goods
-- directly, never into a barrel).
local KIND_INFO = {
  still = {label = "Still", subtype = df.workshop_type.Still,
    labor = "BREWER", needs_container = "BARREL"},
  kitchen = {label = "Kitchen", subtype = df.workshop_type.Kitchen,
    labor = "COOK", needs_container = nil,
    named_requirement = "restrict cooking of plants and seeds needed for "
      .. "replanting, or the farm loses its seed stock"},
  mason = {label = "Mason's Workshop", subtype = df.workshop_type.Masons,
    labor = "MASON", needs_container = nil},
  mechanic = {label = "Mechanic's Workshop", subtype = df.workshop_type.Mechanics,
    labor = "MECHANIC", needs_container = nil},
  carpenter = {label = "Carpenter's Workshop", subtype = df.workshop_type.Carpenters,
    labor = "CARPENTER", needs_container = nil},
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

-- SILENT-ZERO FIX (handoffs/2026-09-19-silent-zero-fix.md,
-- research/2026-09-19-unverified-claims-audit.md finding 3): this used to
-- `return 0` when `item_type_other_id` did not resolve into a vector --
-- the same shape as the FEED_WATER_WOUNDED incident recorded in
-- docs/PRODUCTION-MODEL.md §13 (a name that does not exist, silently
-- reported as a genuine zero). Returns count(number or nil), err(string or
-- nil) -- err set means count is nil, not zero. Mirrors df-overseer-
-- labor.lua's `set_labor`, the fix already made once for the write path.
local function count_fort_owned(item_type_other_id)
  local ok, vec = pcall(function() return df.global.world.items.other[item_type_other_id] end)
  if not ok or not vec then
    return nil, "unknown item type: " .. tostring(item_type_other_id)
  end
  local n = 0
  for i = 0, #vec - 1 do
    if is_fort_owned_item(vec[i]) then
      n = n + 1
    end
  end
  return n, nil
end

-- Same fix, same reason, as count_fort_owned above.
local function labor_enabled_count(labor_name)
  local code = df.unit_labor[labor_name]
  if code == nil or code < 0 then
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

local function find_plant_by_id(id)
  local plants = df.global.world.raws.plants.all
  for i = 0, #plants - 1 do
    if plants[i].id == id then
      return i
    end
  end
  return nil
end

-- Read-only: is plant_index already in df.global.plotinfo.kitchen's
-- exclusion list for item_type SEEDS? See header -- this is the vanilla
-- Kitchen-tab "don't cook this" setting, investigated live this session,
-- never written to here.
local function kitchen_excludes_seed(plant_index)
  local ok_k, kitchen = pcall(function() return df.global.plotinfo.kitchen end)
  if not ok_k or not kitchen then
    return nil
  end
  local ok_n, n = pcall(function() return #kitchen.exc_types end)
  if not ok_n then
    return nil
  end
  for i = 0, n - 1 do
    local ok_it, it = pcall(function() return kitchen.item_types[i] end)
    local ok_mi, mi = pcall(function() return kitchen.mat_indices[i] end)
    if ok_it and ok_mi and it == df.item_type.SEEDS and mi == plant_index then
      return true
    end
  end
  return false
end

-- Per fort-owned seed (df-overseer-stocks.lua's get_seeds(), read-only),
-- whether it is currently protected from kitchen cooking. Kitchen only.
local function seed_protection_report()
  local seeds = stocks_mod.get_seeds()
  local protected, unprotected, unknown = {}, {}, {}
  for crop_id, units in pairs(seeds.by_plant_units or {}) do
    if units > 0 then
      local idx = find_plant_by_id(crop_id)
      local excluded = idx and kitchen_excludes_seed(idx)
      if excluded == nil then
        table.insert(unknown, crop_id)
      elseif excluded then
        table.insert(protected, crop_id)
      else
        table.insert(unprotected, crop_id)
      end
    end
  end
  table.sort(protected)
  table.sort(unprotected)
  table.sort(unknown)
  return {protected = protected, unprotected = unprotected, unknown = unknown}
end

-- ADDED handoffs/2026-09-17-water-and-industry-tools.md item 3: every one
-- of these five workshop kinds is a basic, zero-frills workshop, and
-- `dfhack.buildings.getFiltersByType({}, df.building_type.Workshop,
-- <subtype>, -1)` returns, for ALL FIVE (live-verified this session, not
-- assumed to generalise from mason/mechanic/carpenter alone -- still and
-- kitchen were checked too), a single filter with no item_type/mat_type at
-- all, just `flags2.building_material = true` -- DF's generic "any boulder,
-- log, or block" construction-material class, not a specific item type.
-- This answers the still/kitchen stream's own open question ("logs or
-- boulders, whichever the game accepts") for real: it is BOTH, plus
-- blocks, interchangeably. Reported fresh on every call, never cached.
-- Each of BOULDER/WOOD/BLOCKS is looked up independently, so one bad name
-- reports only its own miss, never masks the other two's real counts.
-- `fort_owned_errors` carries only the entries that actually failed (see
-- count_fort_owned's own header) -- omitted entirely when all three
-- resolve, so a caller can check `fort_owned_errors == nil` as "clean".
local function building_material_report()
  local boulder, boulder_err = count_fort_owned("BOULDER")
  local wood, wood_err = count_fort_owned("WOOD")
  local blocks, blocks_err = count_fort_owned("BLOCKS")
  local errors = {BOULDER = boulder_err, WOOD = wood_err, BLOCKS = blocks_err}
  local has_error = boulder_err or wood_err or blocks_err
  return {
    accepts = {"BOULDER", "WOOD", "BLOCKS"},
    fort_owned = {
      BOULDER = boulder,
      WOOD = wood,
      BLOCKS = blocks,
    },
    fort_owned_errors = has_error and errors or nil,
  }
end

local function requirements_for(kind_info)
  local labor_count, labor_err = labor_enabled_count(kind_info.labor)
  local req = {
    labor = kind_info.labor,
    citizens_with_labor = labor_count,
    citizens_with_labor_error = labor_err,
    building_material = building_material_report(),
  }
  if kind_info.needs_container then
    local container_count, container_err = count_fort_owned(kind_info.needs_container)
    req.needs_container = kind_info.needs_container
    req.fort_owned_containers = container_count
    req.fort_owned_containers_error = container_err
  end
  if kind_info.named_requirement then
    req.named_requirement = kind_info.named_requirement
    req.seed_protection = seed_protection_report()
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
    return nil, "unknown workshop kind: " .. tostring(kind) .. " (expected still/kitchen/mason/mechanic/carpenter)"
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
    return nil, "unknown workshop kind: " .. tostring(kind) .. " (expected still/kitchen/mason/mechanic/carpenter)"
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
