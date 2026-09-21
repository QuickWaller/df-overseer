-- df-overseer-building.lua
--@module = true
--
-- handoffs/2026-09-21-building-tool-lua.md, design in docs/BUILDING-TOOL.md
-- (contract C1). ONE tool that lists, finds a site for, and builds any
-- building kind DFHack's quickfort knows, where df-overseer-workshop.lua
-- covers five hard-coded workshop kinds. Rule behind it (CLAUDE.md, "Tools
-- must be generalisable"): the KIND is an argument, everything that differs
-- per kind is read from the game's own data at run time, and the next kind
-- costs no new code.
--
-- WHERE THE KIND TABLE COMES FROM. quickfort keeps every buildable kind in
-- `building_db_raw`, a `local` in hack/scripts/internal/quickfort/build.lua
-- (177 keys on this install, about 150 distinct kinds once alias keys are
-- folded). The module exports only do_run/do_orders/do_undo, no getter.
-- Options weighed, least fragile chosen:
--   1. Parse the file text. Rejected: the table is Lua source with helper
--      calls (make_bridge_entry, make_trackstop_entry, ...) and a defaults
--      pass that runs after it (the 3x3 workshop footprint is filled in by
--      that pass, not written in the table), so text parsing would have to
--      re-implement both.
--   2. Read another exported structure. None exists: dfhack.buildings has
--      filters and constructors but no kind list, and the raws carry only
--      the two custom workshops (docs/BUILDING-TOOL.md item 1).
--   3. CHOSEN: reach the live table through Lua upvalues. `do_run` (exported)
--      closes over `building_db`; its metatable's __index is the local
--      function `custom_building`, which closes over `building_db_raw`. Both
--      hops are looked up BY NAME with debug.getupvalue, never by slot number.
--      This yields the table as the running quickfort actually sees it,
--      defaults already applied (footprints, is_valid_tile_fn), including the
--      per-kind tile validators, which this tool calls rather than copies.
--   WHAT A DFHACK UPDATE WOULD BREAK: renaming the upvalues `building_db` or
--   `building_db_raw`, renaming `do_run`, or restructuring so the raw table
--   is no longer reachable through that chain. Every one of those fails LOUD:
--   the load returns an error naming the missing hop (never an empty list),
--   and the tool reports it instead of guessing. Renaming a KIND's key or a
--   label changes only tokens derived from keys (see below), and adding a
--   kind adds a token with no change here.
--
-- KIND TOKENS. A caller names a kind by a token that survives the MCP layer
-- (no apostrophes, no spaces), never a display label. The token is the
-- subtype's own enum name (Masons, Still, WoodFurnace, Lever), or the raws
-- code for a custom workshop (SOAP_MAKER), or the building type's enum name
-- when there is no subtype (Bed, Door, Well). When two distinct table entries
-- would share a token (the bridge, screw pump, roller and track families are
-- direction variants of one building type), the token is `<Base>_<key>` from
-- quickfort's own key (Bridge_gw). The bare quickfort key (case sensitive,
-- for example `wl`) is also accepted. Matching a token is case insensitive.
--
-- SITES. A footprint tile is eligible when it is revealed to a vanilla
-- player (dfhack.maps.isTileVisible, the 2026-09-16 knowledge-scope rule),
-- has no building on it, and passes the kind's OWN quickfort validator
-- (beds must be indoors, doors need an adjacent wall, farm plots need soil,
-- and so on, all read from the table). At least one footprint tile or a tile
-- edge-adjacent to the footprint must be walkable, so a dwarf can reach it.
-- Sites are ranked by distance from the landmark and the top few
-- non-overlapping ones returned. LIMITATION: a kind that goes on open
-- space or a machine-shaft tile can still be found only where a walkable
-- neighbour exists; nothing here proves reachability from the fort's main
-- area, same as every sibling find tool.
--
-- BLUEPRINT. Generated in code (mode `#build`, the kind's own key in every
-- cell of the footprint), written to dfhack-config/blueprints/ where quickfort
-- resolves plain filenames, and removed again after use. No per-kind CSVs.
-- Shape follows blueprints/starter-*.csv.
--
-- REQUIREMENTS are live facts only, no labor names and no confidence
-- (contract C1). What the kind needs to be built comes from the game itself,
-- dfhack.buildings.getFiltersByType, joined to stock counts through
-- df-overseer-stocks.lua's availability read (the six-deduction one; the
-- plain fort-owned count this file's sibling used to report ignored
-- in_building and was found to overstate boulders, register 2026-09-19).
-- Counts are by ITEM TYPE ONLY: a filter's own flags (empty, screw, fire_safe,
-- non_economic) are listed but not applied, and the result says so.
-- NB the filters' `vector_id` is a df.job_item_vector_id, whose numbers do
-- NOT line up with df.items_other_id (54 is BED in one and CHAIN in the
-- other); this file maps by NAME, from the filter's item_type.
--
-- `gaps` is a plain list of strings (docs/BUILDING-TOOL.md decision 5): the
-- tool reports and never refuses, so "build now, barrels later" still works.
--
-- DRY_RUN defaults to true. A dry run resolves the site, generates the
-- blueprint, and asks quickfort itself to validate it with `-d`
-- (--dry-run, documented as "don't actually change any game state"),
-- reporting that under `validation`, never under quickfort_ok (contract C1
-- reserves quickfort_ok/quickfort_error/quickfort_stats for a REAL build).
-- quickfort returns success even when it designated nothing (negative control,
-- live 2026-09-21: an indoor-only Bed on an outdoor tile gave result 0 with
-- "Unsuitable tiles for building: 1"), so `ok` is computed from its statistics:
-- at least one building designated and no problem counter above zero. A real
-- build additionally reads the tile back (`read_back`).
-- The only side effect of a dry run is a scratch blueprint file on the
-- guest, deleted straight after. Only an explicit false performs the real
-- mutation, and that path is UNTESTED live (register: first real build of a
-- never-built kind is a separate stream needing the user's go-ahead).
--
-- No raw coordinate is ever printed or returned (design commitment #1); the
-- footprint's top-left exists only inside build_kind's local scope, to build
-- quickfort's -c argument.
--
-- Usage: ./dfhack-run df-overseer-building list-kinds [FILTER]
-- Usage: ./dfhack-run df-overseer-building find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-building build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]
--   W H are optional for fixed-size kinds and validated against the kind's
--   min/max for the rest; one bare number is LEVEL, two are W H, three are
--   W H LEVEL. A positional CLI cannot skip a slot once a later one is given.

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local stocks_mod = reqscript('df-overseer-stocks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5
local MAX_TILE_CHECKS = 250000

-- json.lua (Friedl): an entry equal to this sentinel encodes as null, and an
-- empty table encodes as [] unless it says it is an object.
local NULL = "\0"
local function encode(v) return json.encode(v, {null = NULL}) end
local function empty_object()
  return setmetatable({}, {__tostring = function() return "JSON object" end})
end
local function nn(v) if v == nil then return NULL end return v end

-- ---------------------------------------------------------------------------
-- Reading quickfort's table (see header for the choice and its fragility)
-- ---------------------------------------------------------------------------

local function upvalue_by_name(fn, want)
  if type(fn) ~= 'function' then return nil end
  local i = 1
  while true do
    local n, v = debug.getupvalue(fn, i)
    if n == nil then return nil end
    if n == want then return v end
    i = i + 1
  end
end

-- Returns raw_table, err. Every hop that can vanish in a DFHack update
-- reports which hop it was.
local function load_quickfort_table()
  if type(debug) ~= 'table' or type(debug.getupvalue) ~= 'function' then
    return nil, "debug.getupvalue is not available in this DFHack Lua"
  end
  local ok, mod = pcall(reqscript, 'internal/quickfort/build')
  if not ok or type(mod) ~= 'table' then
    return nil, "could not load internal/quickfort/build: " .. tostring(mod)
  end
  if type(mod.do_run) ~= 'function' then
    return nil, "quickfort's build module no longer exports do_run"
  end
  local building_db = upvalue_by_name(mod.do_run, 'building_db')
  if type(building_db) ~= 'table' then
    return nil, "do_run no longer closes over an upvalue named building_db"
  end
  local mt = getmetatable(building_db)
  local lookup = mt and mt.__index
  local raw = upvalue_by_name(lookup, 'building_db_raw')
  if type(raw) ~= 'table' then
    return nil, "building_db's __index no longer closes over an upvalue named building_db_raw"
  end
  local n = 0
  for k, e in pairs(raw) do
    n = n + 1
    if type(e) ~= 'table' or e.label == nil or e.type == nil
        or e.min_width == nil or e.max_width == nil
        or e.min_height == nil or e.max_height == nil
        or type(e.is_valid_tile_fn) ~= 'function' then
      return nil, "quickfort table entry '" .. tostring(k)
        .. "' lacks label/type/footprint/is_valid_tile_fn: the table layout changed"
    end
  end
  if n == 0 then
    return nil, "quickfort's building table is empty"
  end
  return raw
end

-- Game structure only: which enum names a building type's numeric subtype.
-- An unlisted type falls back to the number, never to an error.
local SUBTYPE_ENUMS = {
  [df.building_type.Workshop] = df.workshop_type,
  [df.building_type.Furnace] = df.furnace_type,
  [df.building_type.Construction] = df.construction_type,
  [df.building_type.Trap] = df.trap_type,
  [df.building_type.SiegeEngine] = df.siegeengine_type,
}

local function enum_name(enum, v)
  if enum == nil or v == nil then return nil end
  local ok, n = pcall(function() return enum[v] end)
  if ok and n ~= nil then return tostring(n) end
  return nil
end

local function sanitize(s)
  return (tostring(s):gsub("[^%w_]", "x"))
end

-- Returns list, by_token (lowercase token), by_key, err
local function enumerate_kinds()
  local raw, err = load_quickfort_table()
  if not raw then return nil, nil, nil, err end

  -- fold alias keys (g -> gs, Ms -> Msu): same table object, keep the longest key
  local groups, order = {}, {}
  local keys = {}
  for k in pairs(raw) do keys[#keys + 1] = k end
  table.sort(keys)
  for _, k in ipairs(keys) do
    local e = raw[k]
    if not groups[e] then groups[e] = {}; order[#order + 1] = e end
    table.insert(groups[e], k)
  end

  local kinds = {}
  for _, e in ipairs(order) do
    local ks = groups[e]
    table.sort(ks, function(a, b)
      if #a ~= #b then return #a > #b end
      return a < b
    end)
    local key = ks[1]
    local aliases = {}
    for i = 2, #ks do aliases[#aliases + 1] = ks[i] end

    local type_name = enum_name(df.building_type, e.type) or tostring(e.type)
    local sub_enum = SUBTYPE_ENUMS[e.type]
    local subtype_name = enum_name(sub_enum, e.subtype)
    local base, custom_code = type_name, nil
    if e.subtype ~= nil then
      if e.custom ~= nil then
        local ok, code = pcall(function() return df.global.world.raws.buildings.all[e.custom].code end)
        if ok and code and code ~= '' then
          custom_code = tostring(code)
          base = custom_code
        else
          base = type_name .. "_custom" .. tostring(e.custom)
        end
      else
        base = subtype_name or (type_name .. "_" .. tostring(e.subtype))
      end
    end
    kinds[#kinds + 1] = {
      entry = e, key = key, aliases = aliases, label = tostring(e.label),
      type_name = type_name, subtype_name = subtype_name, subtype_id = e.subtype,
      custom_code = custom_code, base = sanitize(base),
      min_w = e.min_width, max_w = e.max_width, min_h = e.min_height, max_h = e.max_height,
      has_extents = e.has_extents and true or false,
    }
  end

  -- tokens: base name if unique among distinct entries, else Base_key
  local count = {}
  for _, k in ipairs(kinds) do
    local l = k.base:lower()
    count[l] = (count[l] or 0) + 1
  end
  local by_token, by_key = {}, {}
  for _, k in ipairs(kinds) do
    k.token = (count[k.base:lower()] > 1) and (k.base .. "_" .. sanitize(k.key)) or k.base
    local lt = k.token:lower()
    if by_token[lt] then
      return nil, nil, nil, "kind token collision after disambiguation: " .. k.token
    end
    by_token[lt] = k
    by_key[k.key] = k
    for _, a in ipairs(k.aliases) do by_key[a] = k end
  end
  table.sort(kinds, function(a, b)
    if a.type_name ~= b.type_name then return a.type_name < b.type_name end
    return a.token < b.token
  end)
  return kinds, by_token, by_key
end

local function kind_summary(k)
  return {
    token = k.token,
    key = k.key,
    aliases = k.aliases,
    label = k.label,
    type = k.type_name,
    subtype = nn(k.subtype_name),
    custom_code = nn(k.custom_code),
    min = {k.min_w, k.min_h},
    max = {k.max_w, k.max_h},
    fixed_size = (k.min_w == k.max_w and k.min_h == k.max_h),
    has_extents = k.has_extents,
  }
end

local function kind_brief(k)
  return {token = k.token, key = k.key, label = k.label, type = k.type_name,
          subtype = nn(k.subtype_name)}
end

local function resolve_kind(name)
  local kinds, by_token, by_key, err = enumerate_kinds()
  if not kinds then return nil, err end
  local s = tostring(name or "")
  local k = by_token[s:lower()] or by_key[s]
  if k then return k end
  local hints = {}
  local q = s:lower()
  if #q >= 2 then
    for _, c in ipairs(kinds) do
      if c.token:lower():find(q, 1, true) or c.label:lower():find(q, 1, true) then
        hints[#hints + 1] = c.token
        if #hints >= 8 then break end
      end
    end
  end
  local msg = "unknown building kind: " .. s .. " (run list-kinds)"
  if #hints > 0 then msg = msg .. "; did you mean: " .. table.concat(hints, ", ") end
  return nil, msg
end

function list_kinds(filter)
  local kinds, _, _, err = enumerate_kinds()
  if not kinds then return nil, err end
  local out = {}
  local q = filter and tostring(filter):lower() or nil
  for _, k in ipairs(kinds) do
    if not q or k.token:lower():find(q, 1, true) or k.label:lower():find(q, 1, true)
        or k.type_name:lower():find(q, 1, true) then
      out[#out + 1] = kind_summary(k)
    end
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Footprint
-- ---------------------------------------------------------------------------

local function resolve_dims(k, w, h)
  local fixed = (k.min_w == k.max_w and k.min_h == k.max_h)
  if w == nil and h == nil then
    if fixed then return k.min_w, k.min_h end
    return nil, string.format("%s needs W and H (width %d..%d, height %d..%d)",
      k.token, k.min_w, k.max_w, k.min_h, k.max_h)
  end
  if w == nil or h == nil then
    return nil, "give both W and H, or neither for a fixed-size kind"
  end
  if w ~= math.floor(w) or h ~= math.floor(h) then
    return nil, "W and H must be whole numbers"
  end
  if w < k.min_w or w > k.max_w or h < k.min_h or h > k.max_h then
    return nil, string.format("%s footprint %dx%d is outside the allowed width %d..%d, height %d..%d",
      k.token, w, h, k.min_w, k.max_w, k.min_h, k.max_h)
  end
  return w, h
end

-- ---------------------------------------------------------------------------
-- Site search
-- ---------------------------------------------------------------------------

local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
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

-- One tile against the kind's own rules. `b` is the quickfort-shaped window
-- (pos, width, height) some validators read (bridges).
local function tile_ok(entry, x, y, z, b, stats)
  stats.checked = stats.checked + 1
  if not dfhack.maps.isValidTilePos(x, y, z) then return false end
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("isTileVisible: " .. tostring(visible))
    return false
  end
  if not visible then return false end
  local pos = xyz2pos(x, y, z)
  local ok_b, bld = pcall(dfhack.buildings.findAtTile, pos)
  if not ok_b then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("findAtTile: " .. tostring(bld))
    return false
  end
  if bld then return false end
  local ok_v, valid = pcall(entry.is_valid_tile_fn, pos, entry, b)
  if not ok_v then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("is_valid_tile_fn: " .. tostring(valid))
    return false
  end
  return valid and true or false
end

local function walkable(x, y, z, cache)
  local key = x * 100000 + y
  local v = cache[key]
  if v ~= nil then return v end
  local ok, g = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  v = ok and g ~= nil and g ~= 0
  cache[key] = v
  return v
end

-- Returns chosen (list of {x,y,dist}), search_stats, err, z
local function ranked_sites(k, w, h, level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then return nil, nil, "landmark not found: " .. tostring(near) end
  local z, level_err = resolve_level(az, level, near)
  if level_err then return nil, nil, level_err end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)
  if radius < 1 then radius = 1 end
  local min_x, max_x, min_y, max_y = ax - radius, ax + radius, ay - radius, ay + radius
  local entry = k.entry
  local stats = {checked = 0, errors = 0, first_error = nil, eligible_tiles = 0, windows = 0}

  local per_window = (entry.type == df.building_type.Bridge)  -- bridge validity depends on the window
  local elig = {}
  if not per_window then
    if (max_x - min_x + 1) * (max_y - min_y + 1) > MAX_TILE_CHECKS then
      return nil, nil, "search area too large"
    end
    for x = min_x, max_x do
      elig[x] = {}
      for y = min_y, max_y do
        local b = {pos = xyz2pos(x, y, z), width = 1, height = 1}
        local ok = tile_ok(entry, x, y, z, b, stats)
        elig[x][y] = ok
        if ok then stats.eligible_tiles = stats.eligible_tiles + 1 end
      end
    end
  else
    local windows = (max_x - min_x - w + 2) * (max_y - min_y - h + 2)
    if windows * w * h > MAX_TILE_CHECKS then
      return nil, nil, "search area too large for a per-window kind; lower RADIUS_TILES"
    end
  end

  local wcache = {}
  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      stats.windows = stats.windows + 1
      local fits = true
      if per_window then
        local b = {pos = xyz2pos(x, y, z), width = w, height = h}
        for dx = 0, w - 1 do
          if not fits then break end
          for dy = 0, h - 1 do
            if not tile_ok(entry, x + dx, y + dy, z, b, stats) then fits = false; break end
          end
        end
      else
        for dx = 0, w - 1 do
          if not fits then break end
          for dy = 0, h - 1 do
            if not elig[x + dx][y + dy] then fits = false; break end
          end
        end
      end
      if fits then
        -- a dwarf must be able to reach it: a walkable tile in or edge-adjacent
        local touch = false
        for dx = -1, w do
          if touch then break end
          for dy = -1, h do
            local inside = dx >= 0 and dx < w and dy >= 0 and dy < h
            local edge = (dx == -1 or dx == w) ~= (dy == -1 or dy == h)
            if inside or edge then
              if walkable(x + dx, y + dy, z, wcache) then touch = true; break end
            end
          end
        end
        if touch then
          local cx, cy = x + (w - 1) / 2, y + (h - 1) / 2
          local ddx, ddy = cx - ax, cy - ay
          candidates[#candidates + 1] = {x = x, y = y, dist = math.sqrt(ddx * ddx + ddy * ddy)}
        end
      end
    end
  end
  table.sort(candidates, function(a, b) return a.dist < b.dist end)

  local chosen = {}
  for _, c in ipairs(candidates) do
    local ok = true
    for _, e in ipairs(chosen) do
      if overlaps(c, e, w, h) then ok = false; break end
    end
    if ok then
      chosen[#chosen + 1] = c
      if #chosen >= MAX_RESULTS then break end
    end
  end
  local search = {
    radius_tiles = radius,
    tiles_checked = stats.checked,
    eligible_tiles = per_window and NULL or stats.eligible_tiles,
    eligible_note = per_window and "not counted: this kind's tile rule depends on the footprint window" or NULL,
    windows_checked = stats.windows,
    fitting_sites = #candidates,
    check_errors = stats.errors,
    first_check_error = nn(stats.first_error),
  }
  return chosen, search, nil, z
end

local function site_info(c, w, h, z, rank)
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)
  local ok_near, info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  info = ok_near and info or nil
  return {
    rank = rank,
    near_landmark = nn(info and info.name),
    direction = nn(info and info.direction),
    distance_tiles = nn(info and info.distance_tiles),
  }
end

-- ---------------------------------------------------------------------------
-- Requirements (live facts) and gaps
-- ---------------------------------------------------------------------------

local BUILDING_MATERIAL_TYPES = {"BOULDER", "WOOD", "BLOCKS"}

local function true_flags(t, prefix)
  local out = {}
  if t == nil then return out end
  pcall(function()
    for name, v in pairs(t) do
      if v == true then out[#out + 1] = prefix .. tostring(name) end
    end
  end)
  table.sort(out)
  return out
end

local function stock_for(type_name, cache)
  if cache[type_name] then return cache[type_name] end
  local ok, res, err = pcall(stocks_mod.get_availability, type_name)
  local rec
  if not ok then
    rec = {total = NULL, available = NULL, error = "availability read failed: " .. tostring(res)}
  elseif not res then
    rec = {total = NULL, available = NULL, error = tostring(err)}
  else
    rec = {
      total = nn(res.total_units),
      available = nn(res.available_units),
      unnetted = nn(res.unnetted_units),
      in_building = nn(res.in_building_units),
      in_job = nn(res.in_job_units),
    }
    if res.flag_read_errors and #res.flag_read_errors > 0 then
      rec.flag_read_errors = res.flag_read_errors
    end
  end
  cache[type_name] = rec
  return rec
end

local function requirements_for(k)
  local e = k.entry
  local sub = e.subtype
  if sub == nil then sub = -1 end
  local cust = e.custom
  if cust == nil then cust = -1 end
  local bp_ok, bp = pcall(function() return require('plugins.buildingplan').isEnabled() end)
  local bm = {
    source = "dfhack.buildings.getFiltersByType",
    buildingplan_enabled = bp_ok and bp or NULL,
  }
  if not bp_ok then bm.buildingplan_error = tostring(bp) end
  local gaps = {}

  local ok, filters = pcall(dfhack.buildings.getFiltersByType, {}, e.type, sub, cust)
  if not ok or filters == nil then
    bm.error = "getFiltersByType failed: " .. tostring(filters)
    bm.filters = {}
    gaps[#gaps + 1] = "could not read what " .. k.token .. " needs to build: " .. bm.error
    return {building_material = bm}, gaps
  end

  local out, cache = {}, {}
  for i = 1, #filters do
    local f = filters[i]
    local rec = {index = i}
    local qty = f.quantity
    rec.quantity = (qty == nil) and 1 or qty
    if qty ~= nil and qty < 0 then
      rec.quantity_note = "quantity is " .. tostring(qty) .. " in the game's filter: it depends on the footprint"
    end
    local flags = true_flags(f.flags1, "flags1.")
    for _, x in ipairs(true_flags(f.flags2, "flags2.")) do flags[#flags + 1] = x end
    for _, x in ipairs(true_flags(f.flags3, "flags3.")) do flags[#flags + 1] = x end
    rec.flags = flags
    rec.count_scope = "item type only; the filter's own flags are not applied"

    local names = nil
    local class_flag = f.flags2 and f.flags2.building_material
    if class_flag then
      rec.need = "any building material (boulder, log or block)"
      names = BUILDING_MATERIAL_TYPES
    elseif f.item_type ~= nil and f.item_type >= 0 then
      local tname = enum_name(df.item_type, f.item_type)
      rec.need = tname or ("item_type " .. tostring(f.item_type))
      rec.item_type = tname
      local vname = f.vector_id and enum_name(df.job_item_vector_id, f.vector_id) or nil
      if vname and tname and vname ~= tname then rec.vector_name_disagrees = vname end
      local ok_vec, vec = pcall(function() return df.global.world.items.other[tname or ""] end)
      if tname and ok_vec and vec then
        names = {tname}
      else
        rec.count_error = "no df.global.world.items.other vector named " .. tostring(tname)
      end
    else
      rec.need = (#flags > 0) and ("an item matching " .. table.concat(flags, ", "))
        or "an item (the filter names no type and no flags)"
      rec.count_error = "the filter has no item type and is not the building_material class, "
        .. "so it cannot be counted by type"
    end

    if names then
      rec.stock = {}
      local avail_sum, any_error = 0, false
      for _, n in ipairs(names) do
        local s = stock_for(n, cache)
        rec.stock[n] = s
        if s.error or s.available == NULL then any_error = true else avail_sum = avail_sum + s.available end
      end
      if any_error then
        rec.available = NULL
        gaps[#gaps + 1] = "could not count stock for " .. rec.need .. " (see stock errors)"
      else
        rec.available = avail_sum
        if rec.quantity >= 0 and avail_sum < rec.quantity then
          gaps[#gaps + 1] = string.format("needs %d of %s, %d available", rec.quantity, rec.need, avail_sum)
        elseif rec.quantity < 0 then
          gaps[#gaps + 1] = string.format("%s: quantity depends on size, %d available", rec.need, avail_sum)
        end
      end
    else
      rec.available = NULL
      gaps[#gaps + 1] = "could not count stock for " .. rec.need .. ": " .. tostring(rec.count_error)
    end
    out[#out + 1] = rec
  end
  bm.filters = out
  if #out == 0 then
    bm.note = "the game lists no material filter for this kind"
  end
  return {building_material = bm}, gaps
end

-- ---------------------------------------------------------------------------
-- Blueprint (generated, never a per-kind file)
-- ---------------------------------------------------------------------------

local function blueprint_text(k, w, h)
  local rows = {"#build generated by df-overseer-building"}
  for _ = 1, h do
    local cells = {}
    for _ = 1, w do cells[#cells + 1] = k.key end
    rows[#rows + 1] = table.concat(cells, ",")
  end
  return table.concat(rows, "\n") .. "\n"
end

local function write_blueprint(k, w, h)
  local filename = string.format("_tmp-building-%s-%dx%d-%d.csv", sanitize(k.token), w, h, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then return nil, "could not open blueprint for writing: " .. tostring(open_err) end
  f:write(blueprint_text(k, w, h))
  f:close()
  return filename
end

function parse_quickfort_stats(output)
  local stats = {}
  if not output then return stats end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then stats[label] = tonumber(value) end
  end
  return stats
end

-- quickfort returns CR_OK even when it designated nothing (a negative control
-- on this install: a Bed on an outdoor tile printed "Buildings designated: 0,
-- Unsuitable tiles for building: 1" and result CR_OK). So "ok" here means the
-- run finished, at least one building was designated, and every OTHER stat
-- quickfort printed (each is a problem counter) is zero.
local DESIGNATED_LABEL = "Buildings designated"
function assess_quickfort(ran, res, stats)
  local problems = {}
  if not ran then return false, problems end
  for label, n in pairs(stats or {}) do
    if label ~= DESIGNATED_LABEL and n ~= 0 then
      problems[#problems + 1] = label .. ": " .. tostring(n)
    end
  end
  table.sort(problems)
  local designated = (stats or {})[DESIGNATED_LABEL] or 0
  return (res == CR_OK and designated >= 1 and #problems == 0), problems
end

local function truthy_dry_run(v)
  if v == nil then return true end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- ---------------------------------------------------------------------------
-- Commands
-- ---------------------------------------------------------------------------

local function elig_str(search)
  if search.eligible_tiles == NULL then return "n/a" end
  return tostring(search.eligible_tiles)
end

function find_kind(kind_name, w, h, level, near, radius_tiles)
  local k, kerr = resolve_kind(kind_name)
  if not k then return nil, kerr end
  local dw, dh = resolve_dims(k, w, h)
  if not dw then return nil, dh end
  local chosen, search, err, z = ranked_sites(k, dw, dh, level, near, radius_tiles)
  if err then return nil, err end
  if #chosen == 0 then
    return nil, string.format("no site for %s (%dx%d) near %s; search: %d tiles checked, %s eligible, %d check errors%s",
      k.token, dw, dh, tostring(near), search.tiles_checked, elig_str(search), search.check_errors,
      search.first_check_error ~= NULL and (" (first: " .. search.first_check_error .. ")") or "")
  end
  local req, gaps = requirements_for(k)
  local results = {}
  for rank, c in ipairs(chosen) do
    results[#results + 1] = {
      kind = kind_brief(k),
      dims = {dw, dh},
      site = site_info(c, dw, dh, z, rank),
      search = search,
      requirements = req,
      gaps = #gaps > 0 and gaps or {},
    }
  end
  return results
end

function build_kind(kind_name, w, h, level, near, rank, radius_tiles, dry_run)
  local k, kerr = resolve_kind(kind_name)
  if not k then return nil, kerr end
  local dw, dh = resolve_dims(k, w, h)
  if not dw then return nil, dh end
  rank = rank or 1
  local dry = truthy_dry_run(dry_run)
  local chosen, search, err, z = ranked_sites(k, dw, dh, level, near, radius_tiles)
  if err then return nil, err end
  if rank < 1 or rank > #chosen then
    return nil, string.format("no candidate at rank %d (found %d near %s); search: %d tiles checked, %s eligible, %d check errors",
      rank, #chosen, tostring(near), search.tiles_checked, elig_str(search), search.check_errors)
  end
  local c = chosen[rank]
  local req, gaps = requirements_for(k)
  local result = {
    kind = kind_brief(k),
    dims = {dw, dh},
    site = site_info(c, dw, dh, z, rank),
    dry_run = dry,
    search = search,
    requirements = req,
    gaps = #gaps > 0 and gaps or {},
  }

  -- Blueprint on the guest. The top-left (c.x, c.y, z) is used only in the -c
  -- argument below and is never printed or returned.
  local filename, write_err = write_blueprint(k, dw, dh)
  result.blueprint = {mode = "build", key = k.key, cells = string.format("%dx%d", dw, dh)}
  if not filename then
    if dry then
      result.validation = {by = "quickfort --dry-run", ok = false, error = write_err}
    else
      result.quickfort_ok = false
      result.quickfort_error = write_err
    end
    return result
  end
  result.blueprint.file = filename

  local coord = string.format('%d,%d,%d', c.x, c.y, z)
  if dry then
    local ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord, '-d')
    local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
    result.blueprint.removed = (ok_rm and rm == true)
    local stats = ok_run and parse_quickfort_stats(output) or nil
    local ok_v, problems = assess_quickfort(ok_run, res, stats)
    result.validation = {
      by = "quickfort run --dry-run",
      ok = ok_v,
      problems = problems,
      error = (not ok_run) and tostring(output) or NULL,
      stats = (stats and next(stats)) and stats or empty_object(),
    }
    return result
  end

  local ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord)
  local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
  result.blueprint.removed = (ok_rm and rm == true)
  local stats = ok_run and parse_quickfort_stats(output) or nil
  local ok_v, problems = assess_quickfort(ok_run, res, stats)
  result.quickfort_ok = ok_v
  result.quickfort_error = (not ok_run) and tostring(output) or NULL
  result.quickfort_stats = (stats and next(stats)) and stats or empty_object()
  result.quickfort_problems = problems
  -- Read the tile back: quickfort can report success without a building
  -- (TRAPS.md), so look at the game. UNTESTED live, like the whole real path.
  local ok_b, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(c.x, c.y, z))
  result.read_back = {
    building_found = ok_b and bld ~= nil and bld ~= false,
    type_matches = ok_b and bld and bld:getType() == k.entry.type or false,
    error = (not ok_b) and tostring(bld) or NULL,
  }
  return result
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local USAGE = {
  "usage: df-overseer-building list-kinds [FILTER]",
  "usage: df-overseer-building find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]",
  "usage: df-overseer-building build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN]",
}

-- After KIND: up to three leading numbers (1 = LEVEL, 2 = W H, 3 = W H LEVEL),
-- then NEAR_LANDMARK, then the rest. Returns w, h, level, near, rest_index.
local function parse_site_args(args)
  local nums, i = {}, 3
  while #nums < 3 and args[i] ~= nil and tonumber(args[i]) ~= nil do
    nums[#nums + 1] = tonumber(args[i])
    i = i + 1
  end
  local w, h, level
  if #nums == 1 then level = nums[1]
  elseif #nums == 2 then w, h = nums[1], nums[2]
  elseif #nums == 3 then w, h, level = nums[1], nums[2], nums[3] end
  return w, h, level, args[i], i + 1
end

local args = {...}
local cmd = args[1]

if cmd == "list-kinds" then
  local res, err = list_kinds(args[2])
  print(encode(err and {error = err} or res))
elseif cmd == "find" then
  local kind = args[2]
  local w, h, level, near, nxt = parse_site_args(args)
  if not (kind and near) then
    print(encode({error = USAGE[2]}))
  else
    local res, err = find_kind(kind, w, h, level, near, tonumber(args[nxt]))
    print(encode(err and {error = err} or res))
  end
elseif cmd == "build" then
  local kind = args[2]
  local w, h, level, near, nxt = parse_site_args(args)
  if not (kind and near) then
    print(encode({error = USAGE[3]}))
  else
    local res, err = build_kind(kind, w, h, level, near, tonumber(args[nxt]), tonumber(args[nxt + 1]), args[nxt + 2])
    print(encode(err and {error = err} or res))
  end
else
  for _, l in ipairs(USAGE) do print(l) end
end
