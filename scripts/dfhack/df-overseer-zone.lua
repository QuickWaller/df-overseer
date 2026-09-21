-- df-overseer-zone.lua
--@module = true
--
-- handoffs/2026-09-21-zone-tool-generalise.md. ONE tool that lists, finds a
-- site for, and places any zone kind DFHack's quickfort knows, with an
-- optional owner. It replaces the water-source-only tool (handoffs/
-- 2026-09-17-water-and-industry-tools.md item 1), whose header said other
-- kinds should be a table entry and not a rewrite. Rule behind it (CLAUDE.md,
-- "Tools must be generalisable"): the KIND is an argument, everything that
-- differs per kind is read from the game's own data at run time or sits in
-- the one policy table below, and the next kind costs no new code.
--
-- WHERE THE KIND TABLE COMES FROM. quickfort keeps every zone kind in
-- `zone_db_raw`, a `local` in hack/scripts/internal/quickfort/zone.lua (18
-- keys on this install; the handoff said 17). The module exports only
-- do_run/do_orders/do_undo. Same choice as df-overseer-building.lua, for the
-- same reasons (parsing the file text would re-implement its helper calls
-- and defaults pass): reach the live table through Lua upvalues, each hop
-- looked up BY NAME with debug.getupvalue, never by slot number:
--   do_run -> upvalue `zone_db` -> its metatable's __index (`custom_zone`)
--   -> upvalue `parse_zone_config` -> upvalue `zone_db_raw`.
-- Every hop that a DFHack update could rename fails loud, naming the hop
-- (a structural check of every entry follows), never an empty list.
-- Each entry gives: the quickfort key (`o`), the label, the civzone type in
-- default_data.type, the size limits (1..inf for every zone), and the tile
-- rule `is_valid_tile_fn` (for every zone: the tile is not hidden). That tile
-- rule is CALLED here, not copied.
--
-- KIND TOKENS. The token is the game's own civzone_type enum name (Office,
-- Bedroom, DiningHall, WaterSource, ...), never a display label (labels such
-- as "Pen/Pasture" would not survive the MCP layer). A caller may also pass
-- the label or quickfort's own key: matching ignores case, spaces, slashes
-- and underscores, so the old `water_source` still resolves to WaterSource.
--
-- PER-KIND POLICY LIVES IN DATA. ZONE_POLICY below is the only place a kind
-- is special. A kind with no entry is a plain rectangle of DEFAULT_DIMS on
-- walkable floor with no owner: that is what a new kind costs, zero entries.
-- WaterSource is the one kind with its own candidate finder (`finder =
-- "water_body"`, unchanged in behaviour from the water-source-only tool: a
-- pond is not a rectangle the caller sizes, so W H are refused for it).
-- Sizes, `prefer_indoors` and the caveats are THIS PROJECT'S choices, not
-- game data, and are labelled so in the result.
--
-- SITES for rectangle kinds. A tile is eligible when it is revealed to a
-- vanilla player (dfhack.maps.isTileVisible, the 2026-09-16 knowledge-scope
-- rule), passes the kind's OWN quickfort tile rule, has no building on it,
-- carries no liquid, is walkable (a walkable group other than 0) and is not
-- already covered by a zone of the same type. Every tile of the W x H window
-- must be eligible and all must be in ONE walkable group, so the room cannot
-- straddle two disconnected areas. Windows are counted through a summed-area
-- table (one pass over the box), ranked by distance from the landmark
-- (kinds with `prefer_indoors` list fully indoor sites first: the tile's
-- `outside` flag, the same test quickfort's Bed rule uses), and the top few
-- non-overlapping ones returned. This is the building tool's site search
-- (df-overseer-building.lua) with the walkability rule tightened from "in or
-- beside" to "every tile", because a zone is the floor dwarves stand on.
-- Duplicated rather than shared: that file's search is a local function of a
-- script this stream may not edit.
--
-- OWNER. Two paths exist on this install and both are exposed behind one
-- optional argument, OWNER, told apart by its shape (all digits = a unit id,
-- otherwise a position code):
--   * position code -> `require('plugins.preserve-rooms').assignToRole(code,
--     zone)`. This is what quickfort's own `assigned_unit=` zone property
--     calls (zone.lua create_zone). The plugin reserves the room for whoever
--     holds that role, follows the role if it changes hands, and per its docs
--     only for Bedroom, DiningHall, Office and Tomb (also the four zone types
--     the plugin's overlay appears on). A vacant role leaves the zone
--     reserved and suspended (its docs). Codes come from the plugin's own
--     `code_lookup` table (23 on this fort), matched case-insensitively.
--   * unit id -> `dfhack.buildings.setOwner(zone, unit)` ("Returns false in
--     case of error"). This is the vanilla equivalent of picking the owner on
--     the room's own screen; nothing follows a role.
-- quickfort's dry run returns from create_zone BEFORE it assigns anything, so
-- a dry run can prove the code, unit and kind checks but not the assignment.
-- The real path reads the assignment back (assigned_unit_id and the game's
-- own getOwner) and is UNTESTED live: no real placement was allowed.
--
-- ROOM VALUE. A noble's `required_office` (and required_bedroom, _dining,
-- _tomb) is a room value. The result's `requirements.room_value` lists, from
-- the fortress entity's own position data, which positions require a value
-- from this kind and whether anyone holds them. What COUNTS toward a room's
-- value is not exposed by the game's data or DFHack's API (no room-value
-- function; only dfhack.buildings.getRoomDescription, which returns the
-- quality word as the room's screen shows it): the result says so and
-- carries the external, older-version wiki account marked unverified here.
--
-- BLUEPRINT (rectangle kinds and the water body): generated in code, mode
-- `#zone`, the kind's own key in every cell, written to dfhack-config/
-- blueprints/ (where quickfort resolves plain filenames, TRAPS.md), run, then
-- removed. No raw coordinate is printed or returned (design commitment #1);
-- the window's top-left exists only inside place_zone's local scope, for the
-- `-c` argument.
--
-- DRY_RUN defaults to true. For rectangle kinds a dry run resolves the site,
-- generates the blueprint and asks quickfort itself to validate it with `-d`
-- (reported under `validation`, never under quickfort_ok, which a real run
-- owns), then removes the scratch file. For WaterSource a dry run is exactly
-- what it always was: no blueprint, no quickfort. Only an explicit false
-- performs the real mutation.
--
-- Usage: ./dfhack-run df-overseer-zone list-kinds [FILTER]
-- Usage: ./dfhack-run df-overseer-zone find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-zone place KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN] [OWNER]
--   W H are optional (a kind's default size is used); one bare number is
--   LEVEL, two are W H, three are W H LEVEL. A positional CLI cannot skip a
--   slot once a later one is given, so OWNER needs RANK RADIUS DRY_RUN first.

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5
local MAX_TILE_CHECKS = 250000
local MAX_DIM = 31
local MAX_LIST = 500

-- json.lua (Friedl): an entry equal to this sentinel encodes as null, and an
-- empty table encodes as [] unless it says it is an object.
local NULL = "\0"
local function encode(v) return json.encode(v, {null = NULL}) end
local function empty_object()
  return setmetatable({}, {__tostring = function() return "JSON object" end})
end
local function nn(v) if v == nil then return NULL end return v end

-- ---------------------------------------------------------------------------
-- Per-kind policy (DATA). Keyed by df.civzone_type enum name.
-- ---------------------------------------------------------------------------

local DEFAULT_POLICY = {
  finder = "rectangle",
  default_dims = {3, 3},   -- this project's choice, not game data
  prefer_indoors = false,
  owner = false,           -- can a unit or role be given this zone
  position_field = nil,    -- entity_position field holding a required room value
  caveat = nil,
}

local ZONE_POLICY = {
  WaterSource = {finder = "water_body"},
  -- Rooms. `owner` per the preserve-rooms docs and overlay (Bedroom,
  -- DiningHall, Office, Tomb); position_field per df.entity_position.
  Office = {default_dims = {3, 3}, prefer_indoors = true, owner = true,
    position_field = "required_office"},
  Bedroom = {default_dims = {3, 3}, prefer_indoors = true, owner = true,
    position_field = "required_bedroom"},
  DiningHall = {default_dims = {4, 4}, prefer_indoors = true, owner = true,
    position_field = "required_dining"},
  Tomb = {default_dims = {1, 2}, owner = true, position_field = "required_tomb"},
  MeetingHall = {default_dims = {5, 5}, prefer_indoors = true},
  Dormitory = {default_dims = {5, 5}, prefer_indoors = true},
  Barracks = {default_dims = {5, 5}, prefer_indoors = true},
  -- Kinds that are only useful on particular terrain. No terrain rule is
  -- encoded, so the tool says so instead of implying it checked.
  FishingArea = {caveat = "only useful with water in reach; this tool does not check terrain for this kind"},
  SandCollection = {caveat = "only useful on sand; this tool does not check terrain for this kind"},
  ClayCollection = {caveat = "only useful on clay; this tool does not check terrain for this kind"},
  PlantGathering = {caveat = "only useful where trees or shrubs grow; this tool does not check terrain for this kind"},
  Pen = {caveat = "only useful on grass, with animals to pen; this tool does not check terrain for this kind"},
  Pond = {caveat = "a pit or pond needs a sensible floor; this tool does not check terrain for this kind"},
}

local function policy_for(k)
  local p = {}
  for key, v in pairs(DEFAULT_POLICY) do p[key] = v end
  for key, v in pairs(ZONE_POLICY[k.token] or {}) do p[key] = v end
  return p
end

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
  local ok, mod = pcall(reqscript, 'internal/quickfort/zone')
  if not ok or type(mod) ~= 'table' then
    return nil, "could not load internal/quickfort/zone: " .. tostring(mod)
  end
  if type(mod.do_run) ~= 'function' then
    return nil, "quickfort's zone module no longer exports do_run"
  end
  local zone_db = upvalue_by_name(mod.do_run, 'zone_db')
  if type(zone_db) ~= 'table' then
    return nil, "do_run no longer closes over an upvalue named zone_db"
  end
  local mt = getmetatable(zone_db)
  local custom = mt and mt.__index
  if type(custom) ~= 'function' then
    return nil, "zone_db no longer has a function __index (custom_zone)"
  end
  local parse = upvalue_by_name(custom, 'parse_zone_config')
  if type(parse) ~= 'function' then
    return nil, "zone_db's __index no longer closes over a function named parse_zone_config"
  end
  local raw = upvalue_by_name(parse, 'zone_db_raw')
  if type(raw) ~= 'table' then
    return nil, "parse_zone_config no longer closes over an upvalue named zone_db_raw"
  end
  local n = 0
  for k, e in pairs(raw) do
    n = n + 1
    if type(e) ~= 'table' or e.label == nil or type(e.default_data) ~= 'table'
        or e.default_data.type == nil
        or e.min_width == nil or e.max_width == nil
        or e.min_height == nil or e.max_height == nil
        or type(e.is_valid_tile_fn) ~= 'function' then
      return nil, "quickfort zone entry '" .. tostring(k)
        .. "' lacks label/default_data.type/size limits/is_valid_tile_fn: the table layout changed"
    end
  end
  if n == 0 then
    return nil, "quickfort's zone table is empty"
  end
  return raw
end

local function norm(s)
  return (tostring(s):lower():gsub("[^%w]", ""))
end

-- Returns list, by_norm, by_key, err
local function enumerate_kinds()
  local raw, err = load_quickfort_table()
  if not raw then return nil, nil, nil, err end
  local keys = {}
  for k in pairs(raw) do keys[#keys + 1] = k end
  table.sort(keys)
  local kinds = {}
  for _, key in ipairs(keys) do
    local e = raw[key]
    local tid = e.default_data.type
    local tname = df.civzone_type[tid]
    if tname == nil then
      return nil, nil, nil, "zone entry '" .. key .. "' has type " .. tostring(tid)
        .. " which is not a df.civzone_type value"
    end
    kinds[#kinds + 1] = {
      entry = e, key = key, label = tostring(e.label),
      token = tostring(tname), type_id = tid,
      min_w = e.min_width, max_w = e.max_width,
      min_h = e.min_height, max_h = e.max_height,
    }
  end
  local by_norm, by_key = {}, {}
  for _, k in ipairs(kinds) do
    for _, name in ipairs({k.token, k.label}) do
      local nm = norm(name)
      if by_norm[nm] and by_norm[nm] ~= k then
        return nil, nil, nil, "zone kind name collision after normalising: " .. name
      end
      by_norm[nm] = k
    end
    by_key[k.key] = k
  end
  table.sort(kinds, function(a, b) return a.token < b.token end)
  return kinds, by_norm, by_key
end

local function finite(n)
  if n == math.huge then return NULL end
  return n
end

local function kind_summary(k)
  local p = policy_for(k)
  return {
    token = k.token,
    key = k.key,
    label = k.label,
    finder = p.finder,
    min = {k.min_w, k.min_h},
    max = {finite(k.max_w), finite(k.max_h)},
    default_dims = p.finder == "rectangle" and p.default_dims or NULL,
    owner_capable = p.owner,
    room_value_field = nn(p.position_field),
    prefer_indoors = p.prefer_indoors,
    caveat = nn(p.caveat),
    policy_source = ZONE_POLICY[k.token] and "ZONE_POLICY entry" or "default (no entry)",
  }
end

local function resolve_kind(name)
  local kinds, by_norm, by_key, err = enumerate_kinds()
  if not kinds then return nil, err end
  local s = tostring(name or "")
  local k = by_norm[norm(s)] or by_key[s]
  if k then return k end
  local hints = {}
  local q = norm(s)
  if #q >= 2 then
    for _, c in ipairs(kinds) do
      if norm(c.token):find(q, 1, true) or norm(c.label):find(q, 1, true) then
        hints[#hints + 1] = c.token
        if #hints >= 8 then break end
      end
    end
  end
  local msg = "unknown zone kind: " .. s .. " (run list-kinds)"
  if #hints > 0 then msg = msg .. "; did you mean: " .. table.concat(hints, ", ") end
  return nil, msg
end

function list_kinds(filter)
  local kinds, _, _, err = enumerate_kinds()
  if not kinds then return nil, err end
  local out = {}
  local q = filter and norm(filter) or nil
  for _, k in ipairs(kinds) do
    if not q or q == "" or norm(k.token):find(q, 1, true) or norm(k.label):find(q, 1, true) then
      out[#out + 1] = kind_summary(k)
    end
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Shared helpers
-- ---------------------------------------------------------------------------

-- LEVEL relative to the landmark's own z, same contract as every other
-- df-overseer-*.lua finder. Duplicated rather than shared -- see any of
-- those files' own comment for why.
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- ---------------------------------------------------------------------------
-- WaterSource: the water-body finder, unchanged in behaviour
-- ---------------------------------------------------------------------------

-- Revealed, not magma, actually carrying water (flow_size >= 1), and not
-- already under a building. This is this project's OWN domain rule
-- ("targeting revealed water tiles"), layered on top of quickfort's own
-- (much looser) is_valid_zone_tile: a WaterSource zone is only useful on
-- water. Returns (ok, info) where info carries flow_size/stagnant/salt.
local function is_water_source_tile(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis or not visible then
    return false, nil
  end
  local pos = xyz2pos(x, y, z)
  local ok_flags, flags = pcall(dfhack.maps.getTileFlags, pos)
  if not ok_flags or not flags then
    return false, nil
  end
  -- docs/TRAPS.md: liquid_type is a plain Lua boolean on this build
  -- (false=Water, true=Magma), not the df.tile_liquid enum -- hedge both
  -- forms, same pattern df-overseer-farm.lua's valid_tile_base already uses.
  if flags.liquid_type == true or flags.liquid_type == df.tile_liquid.Magma then
    return false, nil
  end
  if not flags.flow_size or flags.flow_size < 1 then
    return false, nil
  end
  local ok_bld, bld = pcall(dfhack.buildings.findAtTile, pos)
  if ok_bld and bld then
    return false, nil
  end
  return true, {
    flow_size = flags.flow_size,
    stagnant = flags.water_stagnant or false,
    salt = flags.water_salt or false,
  }
end

-- 4-connected flood fill over the scoped box, water tiles only. Returns a
-- list of components, each {tiles = {{x,y},...}, min_x,max_x,min_y,max_y,
-- flow_min,flow_max,any_stagnant,any_salt}.
local function find_water_components(z, min_x, max_x, min_y, max_y)
  local info = {}
  for x = min_x, max_x do
    for y = min_y, max_y do
      local ok, tinfo = is_water_source_tile(x, y, z)
      if ok then
        info[x] = info[x] or {}
        info[x][y] = tinfo
      end
    end
  end

  local visited = {}
  local components = {}
  for x = min_x, max_x do
    for y = min_y, max_y do
      if info[x] and info[x][y] and not (visited[x] and visited[x][y]) then
        -- Explicit stack, no recursion, no per-tile pcall inside the
        -- flood loop itself -- docs/TRAPS.md's per-tile-closure/pcall cost
        -- warning; is_water_source_tile above already ran its own pcalls
        -- once per tile during the scan pass, not per flood-fill step.
        local stack = {{x, y}}
        local comp = {
          tiles = {}, min_x = x, max_x = x, min_y = y, max_y = y,
          flow_min = math.huge, flow_max = -math.huge,
          any_stagnant = false, any_salt = false,
        }
        visited[x] = visited[x] or {}
        visited[x][y] = true
        while #stack > 0 do
          local cur = table.remove(stack)
          local cx, cy = cur[1], cur[2]
          local tinfo = info[cx][cy]
          table.insert(comp.tiles, {cx, cy})
          comp.min_x = math.min(comp.min_x, cx)
          comp.max_x = math.max(comp.max_x, cx)
          comp.min_y = math.min(comp.min_y, cy)
          comp.max_y = math.max(comp.max_y, cy)
          comp.flow_min = math.min(comp.flow_min, tinfo.flow_size)
          comp.flow_max = math.max(comp.flow_max, tinfo.flow_size)
          comp.any_stagnant = comp.any_stagnant or tinfo.stagnant
          comp.any_salt = comp.any_salt or tinfo.salt
          local neighbors = {{cx + 1, cy}, {cx - 1, cy}, {cx, cy + 1}, {cx, cy - 1}}
          for _, n in ipairs(neighbors) do
            local nx, ny = n[1], n[2]
            if nx >= min_x and nx <= max_x and ny >= min_y and ny <= max_y
                and info[nx] and info[nx][ny]
                and not (visited[nx] and visited[nx][ny]) then
              visited[nx] = visited[nx] or {}
              visited[nx][ny] = true
              table.insert(stack, {nx, ny})
            end
          end
        end
        table.insert(components, comp)
      end
    end
  end
  return components
end

-- Server-side only: ranked water-body components (real coordinates kept on
-- each component's own tiles/bbox fields, never stripped here). Shared by
-- the find and place paths, so "rank 1" can never mean two different bodies
-- depending which entry point asked.
local function ranked_water_bodies(level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local components = find_water_components(z, ax - radius, ax + radius, ay - radius, ay + radius)

  for _, c in ipairs(components) do
    local cx = (c.min_x + c.max_x) / 2
    local cy = (c.min_y + c.max_y) / 2
    local dx, dy = cx - ax, cy - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(components, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local chosen = {}
  for i = 1, math.min(MAX_RESULTS, #components) do
    table.insert(chosen, components[i])
  end
  return chosen, nil, z
end

-- Writes a throwaway `#zone` blueprint CSV covering the component's own
-- bounding box, `symbol` only at the component's own water tiles, blank
-- elsewhere. Returns the bare filename (for quickfort's own -c resolution)
-- or nil, err. UNTESTED live (no real placement has ever been allowed).
local function write_water_blueprint(comp, symbol, label)
  local member = {}
  for _, t in ipairs(comp.tiles) do
    local x, y = t[1], t[2]
    member[x] = member[x] or {}
    member[x][y] = true
  end
  local filename = string.format("_tmp-zone-%d-%d-%d.csv", comp.min_x, comp.min_y, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then
    return nil, "could not open blueprint for writing: " .. tostring(open_err)
  end
  f:write(string.format("#zone %s\n", label))
  for y = comp.min_y, comp.max_y do
    local row = {}
    for x = comp.min_x, comp.max_x do
      row[#row + 1] = (member[x] and member[x][y]) and symbol or ""
    end
    f:write(table.concat(row, ",") .. "\n")
  end
  f:close()
  return filename
end

local function water_info(kind_label, token, c, z, rank)
  local cx = math.floor((c.min_x + c.max_x) / 2 + 0.5)
  local cy = math.floor((c.min_y + c.max_y) / 2 + 0.5)
  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local info = ok_near and near_info
  local r = {
    kind = kind_label,
    token = token,
    dims = {c.max_x - c.min_x + 1, c.max_y - c.min_y + 1},
    tile_count = #c.tiles,
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    depth_min = c.flow_min,
    depth_max = c.flow_max,
    stagnant = c.any_stagnant,
    salt = c.any_salt,
  }
  if rank then r.rank = rank end
  return r
end

local function find_water(k, level, near, radius_tiles)
  local chosen, err, z = ranked_water_bodies(level, near, radius_tiles)
  if err then return nil, err end
  local results = {}
  for _, c in ipairs(chosen) do
    table.insert(results, water_info(k.label, k.token, c, z, nil))
  end
  return results
end

local function place_water(k, level, near, rank, radius_tiles, dry)
  rank = rank or 1
  local chosen, err, z = ranked_water_bodies(level, near, radius_tiles)
  if err then return nil, err end
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end
  local c = chosen[rank]
  local base = water_info(k.label, k.token, c, z, nil)
  base.dry_run = dry
  base.rank = rank

  if dry then
    base.would_zone_tiles = #c.tiles
    return base
  end

  -- Real mutation. The bounding box's own top-left (c.min_x,c.min_y) is
  -- the coordinate that ever exists outside this function's local scope,
  -- and only inside quickfort's own -c argument -- never printed or
  -- returned. UNTESTED live.
  local symbol = k.key
  local filename, write_err = write_water_blueprint(c, symbol, k.label)
  if not filename then
    base.quickfort_ok = false
    base.quickfort_error = write_err
    return base
  end

  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', filename, '-c',
    string.format('%d,%d,%d', c.min_x, c.min_y, z))

  pcall(os.remove, "dfhack-config/blueprints/" .. filename)

  base.quickfort_ok = ok_run and result == CR_OK
  base.quickfort_error = (not ok_run) and tostring(output) or nil
  return base
end

-- ---------------------------------------------------------------------------
-- Rectangle kinds: site search
-- ---------------------------------------------------------------------------

local function resolve_dims(k, p, w, h)
  if w == nil and h == nil then
    return p.default_dims[1], p.default_dims[2]
  end
  if w == nil or h == nil then
    return nil, "give both W and H, or neither for the kind's default size"
  end
  if w ~= math.floor(w) or h ~= math.floor(h) then
    return nil, "W and H must be whole numbers"
  end
  if w < k.min_w or w > k.max_w or h < k.min_h or h > k.max_h then
    return nil, string.format("%s footprint %dx%d is outside the game's allowed width %s..%s, height %s..%s",
      k.token, w, h, tostring(k.min_w), tostring(k.max_w), tostring(k.min_h), tostring(k.max_h))
  end
  if w > MAX_DIM or h > MAX_DIM then
    return nil, string.format("%s footprint %dx%d is larger than this tool's limit of %d per side",
      k.token, w, h, MAX_DIM)
  end
  return w, h
end

-- One tile against the kind's own rule plus this tool's floor rules.
-- Returns eligible, walkable_group, indoors.
local function zone_tile(k, x, y, z, stats)
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
  local ok_f, flags, occ = pcall(dfhack.maps.getTileFlags, pos)
  if not ok_f or not flags or not occ then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("getTileFlags: " .. tostring(flags))
    return false
  end
  if occ.building ~= 0 then stats.occupied = stats.occupied + 1; return false end
  if flags.flow_size and flags.flow_size >= 1 then stats.wet = stats.wet + 1; return false end
  local ok_v, valid = pcall(k.entry.is_valid_tile_fn, pos, k.entry, nil)
  if not ok_v then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("is_valid_tile_fn: " .. tostring(valid))
    return false
  end
  if not valid then return false end
  local ok_g, g = pcall(dfhack.maps.getWalkableGroup, pos)
  if not ok_g then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("getWalkableGroup: " .. tostring(g))
    return false
  end
  if g == nil or g == 0 then stats.not_walkable = stats.not_walkable + 1; return false end
  local ok_z, zones = pcall(dfhack.buildings.findCivzonesAt, pos)
  if ok_z and zones then
    for _, zn in ipairs(zones) do
      if zn.type == k.type_id then stats.already_zoned = stats.already_zoned + 1; return false end
    end
  elseif not ok_z then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("findCivzonesAt: " .. tostring(zones))
    return false
  end
  return true, g, not flags.outside
end

-- Returns chosen (list of {x,y,dist,indoors}), search_stats, err, z
local function ranked_rects(k, p, w, h, level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then return nil, nil, "landmark not found: " .. tostring(near) end
  local z, level_err = resolve_level(az, level, near)
  if level_err then return nil, nil, level_err end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)
  if radius < 1 then radius = 1 end
  local min_x, max_x, min_y, max_y = ax - radius, ax + radius, ay - radius, ay + radius
  local nx, ny = max_x - min_x + 1, max_y - min_y + 1
  if nx * ny > MAX_TILE_CHECKS then return nil, nil, "search area too large" end
  local stats = {checked = 0, errors = 0, first_error = nil, occupied = 0, wet = 0,
    not_walkable = 0, already_zoned = 0, eligible = 0, windows = 0}

  -- per-tile pass, then summed-area tables of eligible and indoor tiles
  local group, elig_sat, indoor_sat = {}, {}, {}
  for i = 0, nx do elig_sat[i] = {}; indoor_sat[i] = {}; for j = 0, ny do elig_sat[i][j] = 0; indoor_sat[i][j] = 0 end end
  for i = 1, nx do
    group[i] = {}
    for j = 1, ny do
      local ok, g, indoors = zone_tile(k, min_x + i - 1, min_y + j - 1, z, stats)
      local e = ok and 1 or 0
      local d = (ok and indoors) and 1 or 0
      if ok then stats.eligible = stats.eligible + 1; group[i][j] = g end
      elig_sat[i][j] = e + elig_sat[i - 1][j] + elig_sat[i][j - 1] - elig_sat[i - 1][j - 1]
      indoor_sat[i][j] = d + indoor_sat[i - 1][j] + indoor_sat[i][j - 1] - indoor_sat[i - 1][j - 1]
    end
  end
  local function rect_sum(sat, i, j)  -- window with top-left (i,j), 1-based
    return sat[i + w - 1][j + h - 1] - sat[i - 1][j + h - 1] - sat[i + w - 1][j - 1] + sat[i - 1][j - 1]
  end

  local candidates = {}
  for i = 1, nx - w + 1 do
    for j = 1, ny - h + 1 do
      stats.windows = stats.windows + 1
      if rect_sum(elig_sat, i, j) == w * h then
        local g0 = group[i][j]
        local same = true
        for dx = 0, w - 1 do
          if not same then break end
          for dy = 0, h - 1 do
            if group[i + dx][j + dy] ~= g0 then same = false; break end
          end
        end
        if same then
          local cx, cy = min_x + i - 1 + (w - 1) / 2, min_y + j - 1 + (h - 1) / 2
          local ddx, ddy = cx - ax, cy - ay
          candidates[#candidates + 1] = {
            x = min_x + i - 1, y = min_y + j - 1,
            dist = math.sqrt(ddx * ddx + ddy * ddy),
            indoors = (rect_sum(indoor_sat, i, j) == w * h),
          }
        end
      end
    end
  end
  table.sort(candidates, function(a, b)
    if p.prefer_indoors and a.indoors ~= b.indoors then return a.indoors end
    return a.dist < b.dist
  end)

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
    eligible_tiles = stats.eligible,
    rejected = {occupied = stats.occupied, liquid = stats.wet,
      not_walkable = stats.not_walkable, already_zoned_same_type = stats.already_zoned},
    windows_checked = stats.windows,
    fitting_sites = #candidates,
    check_errors = stats.errors,
    first_check_error = nn(stats.first_error),
  }
  return chosen, search, nil, z
end

local function rect_site_info(k, p, c, w, h, z, rank)
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)
  local ok_near, info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  info = ok_near and info or nil
  local r = {
    kind = k.label,
    token = k.token,
    dims = {w, h},
    tile_count = w * h,
    near_landmark = nn(info and info.name),
    direction = nn(info and info.direction),
    distance_tiles = nn(info and info.distance_tiles),
  }
  if rank then r.rank = rank end
  if p.prefer_indoors then r.indoors = c.indoors end
  return r
end

-- ---------------------------------------------------------------------------
-- Positions, requirements and owner
-- ---------------------------------------------------------------------------

local function fort_entity()
  local pi = df.global.plotinfo
  local e = pi and pi.main and pi.main.fortress_entity
  if not e then return nil, "no fortress entity (is a fortress loaded?)" end
  return e
end

-- holders[code] = list of unit ids currently holding a position with that code
local function holders_by_code(e)
  local by_id = {}
  for i = 0, math.min(#e.positions.own, MAX_LIST) - 1 do
    local pos = e.positions.own[i]
    by_id[pos.id] = pos
  end
  local held = {}
  for i = 0, math.min(#e.positions.assignments, MAX_LIST) - 1 do
    local a = e.positions.assignments[i]
    local pos = by_id[a.position_id]
    if pos then
      held[pos.code] = held[pos.code] or {}
      if a.histfig >= 0 then
        local fig = df.historical_figure.find(a.histfig)
        if fig and fig.unit_id >= 0 then
          table.insert(held[pos.code], fig.unit_id)
        end
      end
    end
  end
  return by_id, held
end

local ROOM_VALUE_EXTERNAL = "Not exposed by this game's data or DFHack: there is no room-value function, "
  .. "only dfhack.buildings.getRoomDescription (the quality word the room's screen shows). "
  .. "External, UNVERIFIED on this install and written for the older DF2014 (0.47) wiki page "
  .. "'Room': value is the total of the floor and walls (smoothing and engraving add value), "
  .. "plus the value of furniture and other constructions inside the room; quality words start "
  .. "at 1 (Meager), 100 (Modest), 250, 500, 1000, 1500, 2500 and 10000 (Royal), and the same "
  .. "steps apply to offices, dining rooms and tombs. A required value of 1 would then mean any "
  .. "positive room value; whether a bare, unsmoothed office floor is worth 0 on this version is unknown."

local function requirements_for(k, p)
  local rv = {}
  if not p.position_field then
    rv.applies = false
    rv.reason = "no position in the game's data asks for a room value from this kind (positions carry "
      .. "required_office, required_bedroom, required_dining and required_tomb only)"
    return {room_value = rv, other = "no further requirement data exists for this kind"}
  end
  rv.applies = true
  rv.position_field = p.position_field
  local e, err = fort_entity()
  if not e then
    rv.positions = NULL
    rv.error = err
  else
    local by_id, held = holders_by_code(e)
    local rows = {}
    for _, pos in pairs(by_id) do
      local need = pos[p.position_field]
      if need and need > 0 then
        local h = held[pos.code] or {}
        local pop_ok = pos.requires_population == 0 or pos.flags.HAS_MET_POP_REQ == true
        rows[#rows + 1] = {
          code = pos.code,
          required_value = need,
          vacant = (#h == 0),
          holder_unit_ids = h,
          population_requirement_met = pop_ok,
        }
      end
    end
    table.sort(rows, function(a, b) return a.code < b.code end)
    rv.positions = rows
  end
  rv.what_counts = ROOM_VALUE_EXTERNAL
  rv.read_back_after_placement = "dfhack.buildings.getRoomDescription on the placed zone"
  return {room_value = rv}
end

-- Validates OWNER for a kind. Returns plan, err. plan.by is "position" or "unit".
local function resolve_owner(k, p, owner)
  if owner == nil or owner == "" then return nil end
  local s = tostring(owner)
  if not p.owner then
    return nil, string.format("refused: %s cannot have an owner (only kinds marked owner in ZONE_POLICY can: "
      .. "Bedroom, DiningHall, Office, Tomb)", k.token)
  end
  if s:match("^%d+$") then
    local uid = tonumber(s)
    local unit = df.unit.find(uid)
    if not unit then return nil, "refused: no unit with id " .. uid end
    if not dfhack.units.isAlive(unit) then return nil, "refused: unit " .. uid .. " is not alive" end
    if not dfhack.units.isCitizen(unit) then return nil, "refused: unit " .. uid .. " is not a citizen of this fortress" end
    return {by = "unit", unit_id = uid, unit = unit,
      effect = "the zone is owned by this unit through dfhack.buildings.setOwner; nothing follows a role"}
  end
  if not s:match("^[A-Za-z_]+$") then
    return nil, "refused: OWNER must be a unit id (digits) or a position code (letters and underscores)"
  end
  local ok, pr = pcall(require, 'plugins.preserve-rooms')
  if not ok or type(pr) ~= 'table' or type(pr.assignToRole) ~= 'function' then
    return nil, "refused: the preserve-rooms plugin's Lua module is not available"
  end
  local lookup = pr.code_lookup
  if type(lookup) ~= 'table' or next(lookup) == nil then
    return nil, "refused: preserve-rooms has no role table yet (it is filled when a fortress map loads)"
  end
  local group = lookup[s:lower()]
  if not group then
    local codes = {}
    for code in pairs(lookup) do codes[#codes + 1] = code:upper() end
    table.sort(codes)
    return nil, "refused: unknown position code " .. s .. "; known: " .. table.concat(codes, ", ")
  end
  local group_codes = {}
  for i = 1, #group do group_codes[#group_codes + 1] = group[i] end
  local holders = {}
  local e = fort_entity()
  if e then
    local _, held = holders_by_code(e)
    for _, code in ipairs(group_codes) do
      for _, uid in ipairs(held[code] or {}) do holders[#holders + 1] = uid end
    end
  end
  local plan = {by = "position", code = s:upper(), group_codes = group_codes,
    group_required_value = group.required_value, holder_unit_ids = holders,
    vacant = (#holders == 0)}
  if plan.vacant then
    plan.effect = "nobody holds this role now: per the preserve-rooms docs the zone is reserved and suspended "
      .. "until someone does, then assigned to them"
  else
    plan.effect = "assigned to the current holder and re-assigned if the role changes hands (preserve-rooms)"
  end
  return plan
end

local function owner_block(plan)
  if not plan then return nil end
  if plan.by == "unit" then
    return {by = "unit", unit_id = plan.unit_id, effect = plan.effect,
      mechanism = "dfhack.buildings.setOwner"}
  end
  return {by = "position", code = plan.code, group_codes = plan.group_codes,
    holder_unit_ids = plan.holder_unit_ids, vacant = plan.vacant, effect = plan.effect,
    mechanism = "preserve-rooms assignToRole"}
end

-- Real path only, UNTESTED live. Returns a table describing what was done and
-- read back. `zone` is the new civzone.
local function apply_owner(zone, plan)
  local out = {by = plan.by}
  if plan.by == "unit" then
    local ok, res = pcall(dfhack.buildings.setOwner, zone, plan.unit)
    out.applied = ok and res ~= false
    if not ok then out.error = tostring(res)
    elseif res == false then out.error = "dfhack.buildings.setOwner returned false" end
  else
    local ok, pr = pcall(require, 'plugins.preserve-rooms')
    local before
    if ok and type(pr.preserve_rooms_getState) == 'function' then
      local ok_s, _, st = pcall(pr.preserve_rooms_getState)
      before = ok_s and st and st.nobles or nil
    end
    local ok_a, err = pcall(pr.assignToRole, plan.code, zone)
    out.applied = ok_a
    if not ok_a then out.error = tostring(err) end
    if before ~= nil and type(pr.preserve_rooms_getState) == 'function' then
      local ok_s, _, st = pcall(pr.preserve_rooms_getState)
      out.noble_rooms_managed = {before = before, after = (ok_s and st) and st.nobles or NULL}
    end
  end
  local ok_o, owner = pcall(dfhack.buildings.getOwner, zone)
  out.read_back = {
    assigned_unit_id = zone.assigned_unit_id,
    get_owner_unit_id = (ok_o and owner) and owner.id or NULL,
  }
  if plan.by == "position" and not plan.vacant then
    out.read_back.expected_holder_unit_ids = plan.holder_unit_ids
    out.read_back.note = "if assigned_unit_id is still -1 the plugin has not run its cycle yet; "
      .. "'preserve-rooms now' does an immediate update (not run by this tool)"
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Blueprint, quickfort stats
-- ---------------------------------------------------------------------------

local function blueprint_text(k, w, h)
  local rows = {"#zone generated by df-overseer-zone"}
  for _ = 1, h do
    local cells = {}
    for _ = 1, w do cells[#cells + 1] = k.key end
    rows[#rows + 1] = table.concat(cells, ",")
  end
  return table.concat(rows, "\n") .. "\n"
end

local function write_rect_blueprint(k, w, h)
  local filename = string.format("_tmp-zone-%s-%dx%d-%d.csv", k.token, w, h, os.time())
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

-- quickfort returns CR_OK even when it designated nothing (verified for the
-- building mode, docs/BUILDING-TOOL.md; the same finish-with-nothing shape
-- applies here). So "ok" means the run finished, at least one zone was
-- designated and every OTHER counter quickfort printed is zero, except the
-- informational "Zone tiles designated".
local DESIGNATED_LABEL = "Zones designated"
local INFO_LABELS = {["Zone tiles designated"] = true}
function assess_quickfort(ran, res, stats)
  local problems = {}
  if not ran then return false, problems end
  for label, n in pairs(stats or {}) do
    if label ~= DESIGNATED_LABEL and not INFO_LABELS[label] and n ~= 0 then
      problems[#problems + 1] = label .. ": " .. tostring(n)
    end
  end
  table.sort(problems)
  local designated = (stats or {})[DESIGNATED_LABEL] or 0
  return (res == CR_OK and designated >= 1 and #problems == 0), problems
end

local function max_zone_id()
  local zv = df.global.world.buildings.other.ACTIVITY_ZONE
  local m = -1
  for i = 0, math.min(#zv, 5000) - 1 do
    if zv[i].id > m then m = zv[i].id end
  end
  return m
end

-- ---------------------------------------------------------------------------
-- Commands
-- ---------------------------------------------------------------------------

local function elig_note(search)
  return string.format("%d tiles checked, %d eligible, %d check errors%s",
    search.tiles_checked, search.eligible_tiles, search.check_errors,
    search.first_check_error ~= NULL and (" (first: " .. search.first_check_error .. ")") or "")
end

function find_zone_area(kind_name, w, h, level, near, radius_tiles)
  local k, kerr = resolve_kind(kind_name)
  if not k then return nil, kerr end
  local p = policy_for(k)
  if p.finder == "water_body" then
    if w ~= nil or h ~= nil then
      return nil, k.token .. " takes no W H: its footprint follows the water body"
    end
    return find_water(k, level, near, radius_tiles)
  end
  local dw, dh = resolve_dims(k, p, w, h)
  if not dw then return nil, dh end
  local chosen, search, err, z = ranked_rects(k, p, dw, dh, level, near, radius_tiles)
  if err then return nil, err end
  if #chosen == 0 then
    return nil, string.format("no site for %s (%dx%d) near %s; search: %s; rejected %s",
      k.token, dw, dh, tostring(near), elig_note(search), encode(search.rejected))
  end
  local req = requirements_for(k, p)
  local results = {}
  for rank, c in ipairs(chosen) do
    local r = rect_site_info(k, p, c, dw, dh, z, rank)
    r.search = search
    r.requirements = req
    if p.caveat then r.caveat = p.caveat end
    results[#results + 1] = r
  end
  return results
end

-- DRY_RUN defaults to true. See the header for what each mode does.
function place_zone(kind_name, w, h, level, near, rank, radius_tiles, dry_run, owner)
  local k, kerr = resolve_kind(kind_name)
  if not k then return nil, kerr end
  local p = policy_for(k)
  local dry = truthy_dry_run(dry_run)
  local plan, oerr = resolve_owner(k, p, owner)
  if oerr then return nil, oerr end

  if p.finder == "water_body" then
    if w ~= nil or h ~= nil then
      return nil, k.token .. " takes no W H: its footprint follows the water body"
    end
    local res, err = place_water(k, level, near, rank, radius_tiles, dry)
    return res, err
  end

  local dw, dh = resolve_dims(k, p, w, h)
  if not dw then return nil, dh end
  rank = rank or 1
  local chosen, search, err, z = ranked_rects(k, p, dw, dh, level, near, radius_tiles)
  if err then return nil, err end
  if rank < 1 or rank > #chosen then
    return nil, string.format("no candidate at rank %d (found %d near %s); search: %s",
      rank, #chosen, tostring(near), elig_note(search))
  end
  local c = chosen[rank]
  local result = rect_site_info(k, p, c, dw, dh, z, rank)
  result.dry_run = dry
  result.search = search
  result.requirements = requirements_for(k, p)
  if p.caveat then result.caveat = p.caveat end
  if plan then result.owner = owner_block(plan) end

  -- Blueprint on the guest. The top-left (c.x, c.y, z) is used only in the -c
  -- argument below and is never printed or returned.
  local filename, write_err = write_rect_blueprint(k, dw, dh)
  result.blueprint = {mode = "zone", key = k.key, cells = string.format("%dx%d", dw, dh)}
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
    if plan then
      result.owner.dry_run_note = "quickfort's dry run stops before it assigns, so the owner checks above "
        .. "(kind, code or unit) were made by this tool, and the assignment itself is only exercised by a real run"
    end
    return result
  end

  -- REAL PATH. UNTESTED live: no real placement has been allowed.
  local before_id = max_zone_id()
  local ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord)
  local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
  result.blueprint.removed = (ok_rm and rm == true)
  local stats = ok_run and parse_quickfort_stats(output) or nil
  local ok_v, problems = assess_quickfort(ok_run, res, stats)
  result.quickfort_ok = ok_v
  result.quickfort_error = (not ok_run) and tostring(output) or NULL
  result.quickfort_stats = (stats and next(stats)) and stats or empty_object()
  result.quickfort_problems = problems

  -- Read the zone back: quickfort can report success without a zone. Find it
  -- as the newest civzone of this type over the window's centre tile.
  local cpos = xyz2pos(c.x + math.floor((dw - 1) / 2), c.y + math.floor((dh - 1) / 2), z)
  local zone
  local ok_z, zones = pcall(dfhack.buildings.findCivzonesAt, cpos)
  if ok_z and zones then
    for _, zn in ipairs(zones) do
      if zn.type == k.type_id and zn.id > before_id and (not zone or zn.id > zone.id) then zone = zn end
    end
  end
  result.read_back = {
    zone_found = zone ~= nil,
    type_matches = zone ~= nil and zone.type == k.type_id or false,
    id = zone and zone.id or NULL,
    error = (not ok_z) and tostring(zones) or NULL,
  }
  if zone then
    local ok_d, desc = pcall(dfhack.buildings.getRoomDescription, zone)
    result.read_back.room_description = (ok_d and desc ~= "") and desc or NULL
    if plan then result.owner_result = apply_owner(zone, plan) end
  elseif plan then
    result.owner_result = {by = plan.by, applied = false, error = "the zone could not be found to assign"}
  end
  return result
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local USAGE = {
  "usage: df-overseer-zone list-kinds [FILTER]",
  "usage: df-overseer-zone find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES]",
  "usage: df-overseer-zone place KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN] [OWNER]",
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
    local res, err = find_zone_area(kind, w, h, level, near, tonumber(args[nxt]))
    print(encode(err and {error = err} or res))
  end
elseif cmd == "place" then
  local kind = args[2]
  local w, h, level, near, nxt = parse_site_args(args)
  if not (kind and near) then
    print(encode({error = USAGE[3]}))
  else
    local res, err = place_zone(kind, w, h, level, near, tonumber(args[nxt]),
      tonumber(args[nxt + 1]), args[nxt + 2], args[nxt + 3])
    print(encode(err and {error = err} or res))
  end
else
  for _, l in ipairs(USAGE) do print(l) end
end
