-- A minimal fake DFHack world for tests/test_finder_reservation_skip_lua_logic.py:
-- proves df-overseer-well.lua's real `ranked_candidates` (shared by
-- find_well/build_well) drops a reserved candidate before ranking
-- (handoffs/2026-09-30-reservation-gaps.md item 1), against the REAL
-- df-overseer-reservations.lua (loaded from source below, the same
-- real-load-over-fake pattern tests/lua_stubs/dfhack_blueprint_world.lua
-- already uses and documents, since reservations.lua is a dependency-free
-- leaf: it only reqscripts df-overseer-landmarks, faked here, and reads
-- dfhack.persistent/dfhack.world.ReadCurrentTick, also faked here).
--
-- Well is chosen over building/zone/farm/workshop as the "at least one
-- real tool file" case because its own terrain predicate (is_well_tile) is
-- the smallest surface to model honestly: visibility, tile shape, one
-- floor-adjacent neighbour, and a water-depth flag below -- no quickfort
-- internal validator table (building.lua's tile_ok needs
-- 'internal/quickfort/build''s own is_valid_tile_fn, out of reach here
-- without risking exactly the "modelled the wrong field" failure this
-- project's own handoffs repeatedly warn about).

local function enum(names)
  local t = {}
  for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end
  return t
end

df = {
  tiletype_shape = enum({"EMPTY", "FLOOR", "WALL", "RAMP_TOP"}),
  tile_liquid = {Magma = 99},
  -- cur_year: abs_tick() (df-overseer-reservations.lua) reads it with
  -- ReadCurrentTick.
  global = setmetatable({}, {__index = function(_, k) if k == 'cur_year' then return YEAR or 0 end end}),
}
-- attrs[shape_value].shape == shape_value: getTileType below returns the
-- shape value directly (no separate tile-type-id indirection needed for
-- this test), so this is a plain identity lookup, not a guessed shape.
df.tiletype = {attrs = setmetatable({}, {__index = function(_, v) return {shape = v} end})}

function xyz2pos(x, y, z) return {x = x, y = y, z = z} end
local function key(x, y, z) return x .. "," .. y .. "," .. z end

TT = {}     -- key -> shape enum value (candidate tile itself, and its floor neighbour)
VIS = {}    -- key -> false marks hidden; default visible
FLAGS = {}  -- key -> {liquid_type=, flow_size=, water_stagnant=, water_salt=}

function set_shape(x, y, z, shape_name) TT[key(x, y, z)] = df.tiletype_shape[shape_name] end
function set_hidden(x, y, z) VIS[key(x, y, z)] = false end
function set_flow(x, y, z, flow_size)
  FLAGS[key(x, y, z)] = {liquid_type = false, flow_size = flow_size, water_stagnant = false, water_salt = false}
end

dfhack = {
  maps = {
    isTileVisible = function(x, y, z) return VIS[key(x, y, z)] ~= false end,
    getTileType = function(x, y, z)
      local v = TT[key(x, y, z)]
      if v == nil then return -1 end
      return v
    end,
    getTileFlags = function(pos)
      local f = FLAGS[key(pos.x, pos.y, pos.z)] or {liquid_type = false, flow_size = 0}
      return f, {building = 0}
    end,
    getSize = function() return 1, 1, 20 end,
  },
  persistent = {
    _s = {},
    getSiteData = function(k, default)
      if dfhack.persistent._s[k] == nil then dfhack.persistent._s[k] = default end
      return dfhack.persistent._s[k]
    end,
    saveSiteData = function(k, v) dfhack.persistent._s[k] = v end,
  },
  world = {ReadCurrentTick = function() return NOW or 1000 end},
}
dfhack_flags = {module = true}
package.loaded["json"] = {encode = function() return "" end}
function require(n) return package.loaded[n] end

local ANCHOR = {x = 5, y = 5, z = 5}
local landmarks = {
  get_landmark_centroid = function(near)
    if near == "Nowhere" then return nil end
    return ANCHOR.x, ANCHOR.y, ANCHOR.z
  end,
  nearest_landmark = function(x, y, z) return {name = "Well Site", direction = "NE", distance_tiles = 3} end,
}

local RESERVATIONS_LUA_PATH = ...
local RESERVATIONS_MOD = nil
function reqscript(n)
  if n == "df-overseer-landmarks" then return landmarks end
  if n == "df-overseer-reservations" then
    if not RESERVATIONS_MOD then
      local f = io.open(RESERVATIONS_LUA_PATH, "r")
      local src = f:read("*a")
      f:close()
      -- Real reqscript gives a loaded script its OWN environment table
      -- (backed by the shared globals), which is what lets reservations.lua's
      -- own unqualified `function get_raw(...)` etc. become
      -- `reservations_mod.get_raw` -- replicated here exactly as
      -- dfhack_blueprint_world.lua's own copy of this trick documents.
      local env = setmetatable({}, {__index = _G})
      local chunk = assert(load(src, "reservations.lua", "t", env))
      chunk()
      RESERVATIONS_MOD = env
    end
    return RESERVATIONS_MOD
  end
end
