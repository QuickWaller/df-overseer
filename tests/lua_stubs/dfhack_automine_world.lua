-- A fake DFHack world for tests/test_automine_lua_logic.py:
-- df-overseer-automine.lua (research/2026-10-09-auto-mine.md).
--
-- Scope, honestly: tiles are keyed "x,y,z" and exposed through the SAME block
-- shape the script reads (dfhack.maps.getTileBlock(x,y,z) -> block with
-- designation[lx][ly], occupancy[lx][ly], flags). It does not model what the
-- game does with the auto bit (following a vein, priority); that is the live
-- test's job. The surface leaf is a fake whose decode_vein answers from the
-- tile's `vein` field; the hazard and reservations leaves are small fakes with
-- the same function names, so the script's own wiring is what is under test.

dfhack_flags = { module = true }

-- ---- json: in-memory encode_file/decode_file like DFHack's json -------------
local FILES = {}
package.loaded["json"] = {
  encode = function(v) return "json" end,
  encode_file = function(v, path) FILES[path] = v end,
  decode_file = function(path)
    if FILES[path] == nil then error("no such file " .. path) end
    return FILES[path]
  end,
}
function require(n) return package.loaded[n] end

df = {
  tile_dig_designation = { No = 0, Default = 1, Channel = 3, UpStair = 4, DownStair = 5, UpDownStair = 6, Ramp = 7 },
  tiletype_shape = { WALL = 0, FLOOR = 1, EMPTY = 2 },
  tiletype = { attrs = {} },
  announcement_type = { FEATURE_DISCOVERY = 2, STRUCK_MINERAL = 4 },
  global = {
    cur_year = 100, cur_year_tick = 1000,
    world = { status = { reports = {} } },
  },
}

TILES = {}
SAVED_BLOCKS = {}
local function key(x, y, z) return x .. "," .. y .. "," .. z end

-- tt id -> shape
df.tiletype.attrs[1] = { shape = df.tiletype_shape.WALL }
df.tiletype.attrs[2] = { shape = df.tiletype_shape.FLOOR }

function reset_world()
  TILES = {}
  BLOCKS = {}
  FILES = {}
  df.global.world.status.reports = {}
  df.global.cur_year, df.global.cur_year_tick = 100, 1000
  VEIN = {}
  HAZARD = {}
  RESERVED = {}
  DECODE_CALLS = {}
  MISSING_SURFACE = false
end
BLOCKS = {}

-- shape: "wall" | "floor"; opts: hidden, dig, auto, vein = {name=, kind=}
function set_tile(x, y, z, shape, opts)
  opts = opts or {}
  TILES[key(x, y, z)] = {
    tt = shape == "wall" and 1 or 2,
    hidden = opts.hidden or false,
    dig = opts.dig or df.tile_dig_designation.No,
    auto = opts.auto or false,
    vein = opts.vein,
  }
end

local function block_for(x, y, z)
  local bx, by = x - x % 16, y - y % 16
  local k = key(bx, by, z)
  local blk = BLOCKS[k]
  if blk then return blk end
  blk = { designation = {}, occupancy = {}, flags = { designated = false } }
  for lx = 0, 15 do
    blk.designation[lx], blk.occupancy[lx] = {}, {}
    for ly = 0, 15 do
      local t = TILES[key(bx + lx, by + ly, z)]
      -- proxy objects that read and write the tile record
      blk.designation[lx][ly] = setmetatable({}, {
        __index = function(_, f)
          local tt = TILES[key(bx + lx, by + ly, z)]
          if not tt then return (f == "hidden") and true or df.tile_dig_designation.No end
          return tt[f]
        end,
        __newindex = function(_, f, v)
          local tt = TILES[key(bx + lx, by + ly, z)]
          if tt then tt[f] = v end
        end,
      })
      blk.occupancy[lx][ly] = setmetatable({}, {
        __index = function(_, f)
          local tt = TILES[key(bx + lx, by + ly, z)]
          if f == "dig_auto" then return tt and tt.auto or false end
          return false
        end,
        __newindex = function(_, f, v)
          local tt = TILES[key(bx + lx, by + ly, z)]
          if tt and f == "dig_auto" then tt.auto = v end
        end,
      })
    end
  end
  BLOCKS[k] = blk
  return blk
end

dfhack = {
  maps = {
    getTileBlock = function(x, y, z)
      -- an unmapped column reads as no block, like the real call off the map
      if x < 0 or y < 0 then return nil end
      return block_for(x, y, z)
    end,
    getTileType = function(x, y, z)
      local t = TILES[key(x, y, z)]
      if not t then return -1 end
      return t.tt
    end,
  },
  filesystem = { isdir = function() return true end, mkdir_recursive = function() end },
}

-- ---- the leaves the script reqscripts ---------------------------------------
local surface = {
  decode_vein = function(x, y, z)
    DECODE_CALLS[#DECODE_CALLS + 1] = key(x, y, z)
    local t = TILES[key(x, y, z)]
    if t and t.hidden then error("a hidden tile must never be decoded") end
    if not t or not t.vein then return { ok = true, vein_status = "not_mineral" } end
    return {
      ok = true, vein_status = t.vein.kind and "ore_or_gem" or "not_economic",
      mineral_name = t.vein.name, kind = t.vein.kind,
    }
  end,
}
local hazard = {
  begin_scan = function() end,
  check_tile = function(x, y, z)
    if HAZARD[key(x, y, z)] then return { kind = "aquifer", where = "tile", via = "revealed" } end
    return nil
  end,
}
local resv = {
  check_tiles = function(tiles)
    local t = tiles[1]
    local r = RESERVED[key(t.x, t.y, t.z)]
    if r then return { handle = r, purpose = "bedroom" } end
    return nil
  end,
}
function reqscript(n)
  if n == "df-overseer-surface" then
    if MISSING_SURFACE then error("no such script") end
    return surface
  end
  if n == "df-overseer-hazard" then return hazard end
  if n == "df-overseer-reservations" then return resv end
  error("unexpected reqscript " .. tostring(n))
end

function add_report(rtype, year, time, pos)
  local reports = df.global.world.status.reports
  reports[#reports] = { type = rtype, year = year, time = time, pos = pos }
  -- DFHack vectors are 0-based with a length; model with a length metamethod
  local n = 0
  for k in pairs(reports) do if type(k) == "number" and k >= n then n = k + 1 end end
  setmetatable(reports, { __len = function() return n end })
end

HAZARD = {}
RESERVED = {}
VEIN = {}
DECODE_CALLS = {}
MISSING_SURFACE = false
