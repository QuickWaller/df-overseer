-- A minimal fake DFHack world for df-overseer-construction.lua
-- (handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md). Loaded
-- by tests/test_construction_lua_logic.py, which runs the REAL
-- scripts/dfhack/df-overseer-construction.lua against it in lupa.
--
-- Proves the FILE'S OWN LOGIC (which ring tiles it treats as ore/gem
-- candidates, which it refuses and why, that `build` refuses a still-WALL
-- tile rather than guessing, that both verbs apply one single-cell
-- blueprint per tile via a stubbed quickfort). It stubs out
-- df-overseer-surface.lua and df-overseer-building.lua entirely (both are
-- reqscript'd, real modules in production) and fakes `io.open`/`os.remove`
-- so no real file touches disk. It proves nothing about the real quickfort
-- CLI or the real vein-decode API -- see df-overseer-surface.lua's own
-- header and this stream's Result section for that.

local function enum(names)
  local t = {}
  for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end
  return t
end

local NULL = "\0"

-- ---------------------------------------------------------------------------
-- Fake item world, for the item_present guard
-- (handoffs/2026-09-28-keeps-access-guard.md). ITEMS holds every fake item;
-- add_item(id, item_type, x, y, z, opts) registers one at a real position,
-- with the same trader/garbage_collect/removed flags the guard's
-- is_fort_owned_item_flags checks. An item with no position at all (opts.no_pos)
-- proves dfhack.items.getPosition failing/returning nil is handled, not just
-- items elsewhere on the map.
-- ---------------------------------------------------------------------------

ITEMS = {}

-- `item_type` is the TOKEN NAME ("BOULDER"), converted here to the enum
-- ordinal df.item_type expects `item:getType()` to return -- the real
-- df.item_type[ordinal] -> name round trip df-overseer-construction.lua's
-- item_present_at relies on, not just the name handed straight back.
function add_item(id, item_type, x, y, z, opts)
  opts = opts or {}
  local it = {
    id = id,
    _item_type_ordinal = df.item_type[item_type],
    _x = opts.no_pos and nil or x,
    _y = opts.no_pos and nil or y,
    _z = opts.no_pos and nil or z,
    flags = {
      trader = opts.trader == true,
      garbage_collect = opts.garbage_collect == true,
      removed = opts.removed == true,
    },
  }
  function it:getType() return self._item_type_ordinal end
  ITEMS[#ITEMS + 1] = it
end

df = {
  tiletype_shape = enum({"WALL", "FLOOR", "RAMP", "EMPTY"}),
  item_type = enum({"BOULDER", "ROUGH", "WOOD", "BLOCKS"}),
  global = {world = {items = {all = ITEMS}}},
}

CR_OK = 0

-- ---------------------------------------------------------------------------
-- Fake df-overseer-surface module
-- ---------------------------------------------------------------------------

ZONES = {}
RINGS = {}   -- zone id -> list of {x,y,z}
TILES = {}   -- "x,y,z" -> {ok=, hidden=, shape=}
VEINS = {}   -- "x,y,z" -> {vein_status=, mineral_name=, error=}

local function key(x, y, z) return x .. "," .. y .. "," .. z end

function add_zone(id)
  ZONES[id] = {id = id}
end

function set_ring(zone_id, tiles)
  local t = {}
  for i, xyz in ipairs(tiles) do t[i] = xyz end
  RINGS[zone_id] = t
end

function set_tile(x, y, z, shape, opts)
  opts = opts or {}
  TILES[key(x, y, z)] = {ok = (opts.ok ~= false), hidden = (opts.hidden == true),
    shape = shape and df.tiletype_shape[shape] or nil, err = opts.err}
end

function set_vein(x, y, z, vein_status, mineral_name, error_msg)
  VEINS[key(x, y, z)] = {vein_status = vein_status, mineral_name = mineral_name, error = error_msg}
end

-- Shaped like the REAL df-overseer-surface.lua on purpose: find_zone,
-- ring_tiles, tile_read and decode_vein_tile are all `local`, and the only
-- thing exposed on the fake module table is `vein_material`, which closes
-- over the first three; decode_vein_tile itself closes over tile_read. This
-- is exactly the upvalue chain df-overseer-construction.lua's own
-- `surface_hooks()` extracts via `debug.getupvalue` (the same idiom
-- df-overseer-building.lua already uses to reach quickfort's own local
-- table) -- a fake module that just handed these out as plain named fields
-- would not exercise that extraction at all.
local function find_zone(zone_id)
  local b = ZONES[tonumber(zone_id) or zone_id]
  if not b then return nil, "no building with id " .. tostring(zone_id) end
  return b
end

local function ring_tiles(b) return RINGS[b.id] or {} end

local function tile_read(x, y, z)
  local t = TILES[key(x, y, z)]
  if not t then return {ok = false, err = "no test tile set for " .. key(x, y, z)} end
  return t
end

local function decode_vein_tile(x, y, z)
  local t = tile_read(x, y, z)
  if not t.ok then return {vein_status = "unreadable", error = t.err} end
  if t.hidden then return {vein_status = "hidden"} end
  return VEINS[key(x, y, z)] or {vein_status = "not_mineral", economic = false}
end

local function vein_material(zone_id)
  local b, err = find_zone(zone_id)
  if not b then return {error = err} end
  local out = {}
  for i, xyz in ipairs(ring_tiles(b)) do out[i] = decode_vein_tile(xyz[1], xyz[2], xyz[3]) end
  return out
end

local FAKE_SURFACE = {vein_material = vein_material}

-- ---------------------------------------------------------------------------
-- Fake df-overseer-building module (only list_kinds is used)
-- ---------------------------------------------------------------------------

KINDS = {}   -- list of {type=, subtype=, token=, key=, label=}

function set_kinds(list)
  local t = {}
  for i, k in ipairs(list) do
    t[i] = {type = k.type, subtype = k.subtype or NULL, token = k.token, key = k.key, label = k.label or k.token}
  end
  KINDS = t
end

local FAKE_BUILDING = {
  list_kinds = function(_) return KINDS end,
}

package.loaded = package.loaded or {}
package.loaded['df-overseer-surface'] = FAKE_SURFACE
package.loaded['df-overseer-building'] = FAKE_BUILDING
package.loaded['json'] = {encode = function(v) return "json" end}

function reqscript(name) return package.loaded[name] or {} end
function require(name) return package.loaded[name] end

dfhack_flags = {module = true}

-- ---------------------------------------------------------------------------
-- Fake quickfort + filesystem
-- ---------------------------------------------------------------------------

QUICKFORT_CALLS = {}
QUICKFORT_QUEUE = {}

function queue_quickfort(output, res)
  QUICKFORT_QUEUE[#QUICKFORT_QUEUE + 1] = {output = output, res = (res == nil) and CR_OK or res}
end

dfhack = {
  run_command_silent = function(...)
    local a = {...}
    QUICKFORT_CALLS[#QUICKFORT_CALLS + 1] = a
    local resp = table.remove(QUICKFORT_QUEUE, 1)
    if resp == nil then return "", CR_OK end
    return resp.output, resp.res
  end,
  items = {
    getPosition = function(item)
      if item._x == nil then return nil end
      return item._x, item._y, item._z
    end,
  },
}

WRITTEN_FILES = {}

local fake_file_mt = {__index = {}}
function fake_file_mt.__index:write(s)
  self._buf = (self._buf or "") .. s
end
function fake_file_mt.__index:close()
  WRITTEN_FILES[self._path] = self._buf or ""
end

io = io or {}
io.open = function(path, mode)
  if mode == "w" then
    return setmetatable({_path = path}, fake_file_mt)
  end
  return nil, "fake io.open only supports write mode in this test"
end

os = os or {}
os.remove = function(path) WRITTEN_FILES[path] = nil; return true end
os.time = function() return 1 end
