-- A minimal fake DFHack world for df-overseer-surface.lua's `vein_material`/
-- `decode_vein_tile` (handoffs/2026-09-28-ore-vein-recovery-and-construction-
-- tool.md). Loaded by tests/test_surface_vein_material_lua_logic.py, which
-- runs the REAL scripts/dfhack/df-overseer-surface.lua against it in lupa.
--
-- This proves the FILE'S OWN LOGIC (how it walks a zone's boundary ring, how
-- it classifies a tile once it has a shape/material/vein-event answer, how
-- it degrades to "unknown" rather than guessing on any read failure) against
-- a fake world whose shape matches this stream's best understanding of the
-- real API. It proves NOTHING about whether `dfhack.maps.getTileBlock`,
-- `block.block_events`, `df.block_square_event_mineralst`, `.tile_bitmask:
-- get(x, y)` or `.inorganic_mat` are the real field names DFHack uses --
-- that is an unverified live check, called out in this stream's Result and
-- in the .lua file's own header comment for `decode_vein_tile`.

local function enum(names)
  local t = {}
  for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end
  return t
end

-- A 0-indexed vector the way DFHack exposes them: v[0]..v[#v-1].
local function vec(list)
  local v = {}
  for i, x in ipairs(list or {}) do v[i - 1] = x end
  return setmetatable(v, {__len = function() return #(list or {}) end})
end

df = {
  tiletype_shape = enum({
    "WALL", "FORTIFICATION", "FLOOR", "BOULDER", "PEBBLES", "STAIR_UP",
    "STAIR_DOWN", "STAIR_UPDOWN", "RAMP", "RAMP_TOP", "BROOK_BED",
    "BROOK_TOP", "BRANCH", "TRUNK_BRANCH", "TWIG", "SAPLING", "SHRUB",
    "ENDLESS_PIT", "EMPTY",
  }),
  tiletype_material = enum({
    "STONE", "SOIL", "FEATURE", "MINERAL", "LAVA_STONE", "FROZEN_LIQUID",
    "CONSTRUCTION", "AIR", "TREE", "GRASS_LIGHT", "GRASS_DARK",
  }),
  tiletype_special = enum({"NONE", "NORMAL", "SMOOTH", "FURROWED", "WET", "SMOOTH_DEAD"}),
  building_type = enum({"Door", "Workshop"}),
  building = {find = function(id) return BUILDINGS[id] end},
  building_civzonest = {is_instance = function(_, b) return b ~= nil and b._civzone == true end},
  block_square_event_mineralst = {is_instance = function(_, ev) return type(ev) == "table" and ev._mineral_event == true end},
  tiletype = {attrs = setmetatable({}, {__index = function(_, tt) return TILETYPES[tt] end})},
  global = {
    world = {
      event = {engravings = vec({})},
      raws = {inorganics = setmetatable({}, {__index = function(_, i) return INORGANICS[i] end})},
    },
  },
}

BUILDINGS = {}
TILES = {}       -- "x,y,z" -> tiletype id
HIDDEN = {}      -- "x,y,z" -> true
BLOCK_EVENTS = {} -- "x,y,z" -> list of event tables, or "ERROR"
TILETYPES = {}   -- id -> {shape=, material=, special=}
INORGANICS = {}  -- idx -> {id=, material={economic_uses=vec}}
local next_tt = 0

local function key(x, y, z) return x .. "," .. y .. "," .. z end

function add_zone(id, x1, y1, x2, y2, z)
  local b = {id = id, x1 = x1, y1 = y1, x2 = x2, y2 = y2, z = z, _civzone = true}
  BUILDINGS[id] = b
  return b
end

-- Registers a new tiletype id for (shape, material, special) and assigns it
-- to (x, y, z). `special` defaults to NONE.
function set_tile(x, y, z, shape, material, special)
  local tt = next_tt
  next_tt = next_tt + 1
  TILETYPES[tt] = {shape = df.tiletype_shape[shape], material = df.tiletype_material[material],
    special = df.tiletype_special[special or "NONE"]}
  TILES[key(x, y, z)] = tt
end

function set_hidden(x, y, z, hidden)
  HIDDEN[key(x, y, z)] = (hidden ~= false)
end

-- A real vein event at (x, y, z): `present` (default true) simulates
-- tile_bitmask:get(...) returning true for this exact tile.
function set_vein_event(x, y, z, inorganic_idx, present)
  local ev = {_mineral_event = true, inorganic_mat = inorganic_idx}
  local p = (present ~= false)
  ev.tile_bitmask = {get = function(_, lx, ly) return p end}
  BLOCK_EVENTS[key(x, y, z)] = {ev}
end

-- No vein event at all (a MINERAL/FEATURE tile with nothing matching it --
-- the "unknown" case, never guessed at).
function set_no_vein_event(x, y, z)
  BLOCK_EVENTS[key(x, y, z)] = {}
end

-- Simulates dfhack.maps.getTileBlock itself failing for this tile.
function set_block_read_error(x, y, z)
  BLOCK_EVENTS[key(x, y, z)] = "ERROR"
end

function set_inorganic(idx, id, economic_uses)
  INORGANICS[idx] = {id = id, material = {economic_uses = vec(economic_uses or {})}}
end

dfhack = {
  maps = {
    isValidTilePos = function(x, y, z) return true end,
    isTileVisible = function(x, y, z) return not HIDDEN[key(x, y, z)] end,
    getTileType = function(x, y, z)
      local tt = TILES[key(x, y, z)]
      if tt == nil then error("no tiletype set for this test tile") end
      return tt
    end,
    getTileBlock = function(x, y, z)
      local be = BLOCK_EVENTS[key(x, y, z)]
      if be == "ERROR" then error("boom: getTileBlock failed") end
      return {block_events = vec(be or {})}
    end,
  },
  buildings = {
    findAtTile = function(pos) return nil end,
  },
  printerr = function(m) ERRS = (ERRS or "") .. m .. "\n" end,
}

dfhack_flags = {module = true}
function xyz2pos(x, y, z) return {x = x, y = y, z = z} end
package.loaded["json"] = {encode = function() return "json" end}
function require(n) return package.loaded[n] end

-- decode_vein_tile/tile_read/find_zone/ring_tiles are `local` in the real
-- df-overseer-surface.lua on purpose (see that file's own header): reached
-- here the same way df-overseer-construction.lua reaches them for real,
-- via debug.getupvalue against the one exported function that closes over
-- them (`vein_material`).
function upvalue_by_name(fn, name)
  local i = 1
  while true do
    local n, v = debug.getupvalue(fn, i)
    if n == nil then return nil end
    if n == name then return v end
    i = i + 1
  end
end
