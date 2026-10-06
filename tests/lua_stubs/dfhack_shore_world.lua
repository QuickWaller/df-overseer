-- A fake DFHack tile world for the zone tool's shore finder (WaterSource and
-- FishingArea). Loaded by tests/test_zone_shore_lua_logic.py, which runs the
-- REAL scripts/dfhack/df-overseer-zone.lua against it in lupa. Tiles are set
-- with set_tile(x, y, z, spec); everything not set is solid rock (not
-- walkable, dry). It proves the finder's own logic (which tiles are offered,
-- which are refused), not what real DFHack returns for any accessor.

local function enum(names) local t = {} for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end return t end

df = {
  civzone_type = enum({"Bedroom", "Office", "WaterSource", "FishingArea", "Tomb"}),
  tiletype_shape = enum({"WALL", "FLOOR", "RAMP", "RAMP_TOP"}),
  tiletype = {attrs = {}},
  tile_liquid = {Water = 0, Magma = 1},
}
-- tiletype id == shape id in this fake
for i = 0, 3 do df.tiletype.attrs[i] = {shape = i} end

TILES = {}
BUILDINGS_AT = {}
ZONES_AT = {}
MAP_SIZE = {40, 40, 10}
local function key(x, y, z) return x .. "," .. y .. "," .. z end

-- spec: {shape = "FLOOR"|"RAMP_TOP"|"WALL"|"RAMP", water = n, hidden = bool, group = n}
function set_tile(x, y, z, spec)
  spec.shape = spec.shape or "FLOOR"
  TILES[key(x, y, z)] = spec
end
function add_building(x, y, z) BUILDINGS_AT[key(x, y, z)] = {id = 1} end
function add_zone_at(x, y, z, kind) ZONES_AT[key(x, y, z)] = {{type = df.civzone_type[kind]}} end
function fill(x0, y0, x1, y1, z, spec)
  for x = x0, x1 do for y = y0, y1 do
    local s = {}
    for k, v in pairs(spec) do s[k] = v end
    set_tile(x, y, z, s)
  end end
end

local function tile(pos) return TILES[key(pos.x, pos.y, pos.z)] end
function xyz2pos(x, y, z) return {x = x, y = y, z = z} end

dfhack = {
  maps = {
    getSize = function() return MAP_SIZE[1], MAP_SIZE[2], MAP_SIZE[3] end,
    isValidTilePos = function(x, y, z)
      return x >= 0 and y >= 0 and z >= 0 and x < MAP_SIZE[1] and y < MAP_SIZE[2] and z < MAP_SIZE[3]
    end,
    isTileVisible = function(x, y, z)
      local t = TILES[key(x, y, z)]
      return t ~= nil and not t.hidden
    end,
    getTileFlags = function(pos)
      local t = tile(pos)
      local flags = {liquid_type = false, flow_size = t and t.water or 0,
        water_stagnant = false, water_salt = false, outside = true}
      local occ = {building = BUILDINGS_AT[key(pos.x, pos.y, pos.z)] and 1 or 0}
      return flags, occ
    end,
    getWalkableGroup = function(pos)
      local t = tile(pos)
      if not t or (t.water or 0) > 0 then return 0 end
      if t.shape == "WALL" or t.shape == "RAMP" or t.shape == "RAMP_TOP" then return 0 end  -- the build's ramp blind spot
      return t.group or 1
    end,
    getTileType = function(pos)
      local t = tile(pos)
      return t and df.tiletype_shape[t.shape] or 0
    end,
  },
  buildings = {
    findAtTile = function(pos) return BUILDINGS_AT[key(pos.x, pos.y, pos.z)] end,
    findCivzonesAt = function(pos) return ZONES_AT[key(pos.x, pos.y, pos.z)] end,
  },
  printerr = function() end,
}
dfhack_flags = {module = true}
package.loaded["json"] = {encode = function() return "json" end}

-- quickfort's zone table, reachable the way the tool digs for it:
-- do_run -> zone_db -> metatable.__index -> parse_zone_config -> zone_db_raw
local function always_valid() return true end
local zone_db_raw = {}
for _, spec in ipairs({{"w", "Water Source", "WaterSource"}, {"f", "Fishing", "FishingArea"},
    {"b", "Bedroom", "Bedroom"}}) do
  zone_db_raw[spec[1]] = {label = spec[2], default_data = {type = df.civzone_type[spec[3]]},
    min_width = 1, max_width = math.huge, min_height = 1, max_height = math.huge,
    is_valid_tile_fn = always_valid}
end
local function parse_zone_config() return zone_db_raw[1] end
local zone_db = setmetatable({}, {__index = function(_, k) return parse_zone_config(k) end})
local function do_run() return zone_db end
local quickfort_zone = {do_run = do_run}

-- landmarks: one landmark "Spring" at LANDMARK = {x, y, z}
LANDMARK = {20, 20, 5}
local landmarks = {
  get_landmark_centroid = function(name)
    if name ~= "Spring" then return nil end
    return LANDMARK[1], LANDMARK[2], LANDMARK[3]
  end,
  nearest_landmark = function() return {name = "Spring", direction = "here", distance_tiles = 0} end,
}
local reservations = {
  filter_reserved = function(list) return list end,
  check_tiles = function() return nil end,
  rect_tiles = function() return {} end,
  override_needed = function() return false end,
  record_override = function() end,
}
function require(n) return package.loaded[n] end
function reqscript(n)
  if n == 'internal/quickfort/zone' then return quickfort_zone end
  if n == 'df-overseer-landmarks' then return landmarks end
  if n == 'df-overseer-reservations' then return reservations end
  return {}
end
