-- Minimal fake DFHack environment for tests/test_circulation_lua_logic.py.
-- df-overseer-circulation.lua's pure logic (build_graph, summarize,
-- walk_between) takes a `world` table, so all this stub provides is the
-- module-load surface: dfhack_flags, require('json'), and a reqscript that
-- returns a tiny name matcher for df-overseer-textutil.

dfhack_flags = { module = true }
dfhack = {}
df = {}

local function norm(s) return (s:lower():gsub("[^%w]", "")) end

local TEXTUTIL = {
  match_name = function(query, names)
    for i, n in ipairs(names) do if n == query then return i end end
    local q, hit, count = norm(query), nil, 0
    for i, n in ipairs(names) do
      if norm(n) == q then hit = hit or i; count = count + 1 end
    end
    if count == 1 then return hit end
    if count == 0 then return nil, "no name matches '" .. query .. "'", {} end
    return nil, "ambiguous name '" .. query .. "'", {}
  end,
  to_utf8 = function(s) return s end,
}

-- Tests may install fake modules (or a real file's source) by name.
FAKE_MODULES = {}
local LOADED = {}

function reqscript(n)
  if FAKE_MODULES[n] then return FAKE_MODULES[n] end
  if n == "df-overseer-textutil" then return TEXTUTIL end
  return {}
end

local JSON = { encode = function(v) return "{}" end }
function require(n)
  if n == "json" then return JSON end
  return nil
end

-- Builds a world from ASCII layers.  layers = {[z] = {row strings}}.
-- Legend: '#' wall, '.' floor, 'D' floor with a door, '<' stair up,
-- '>' stair down, 'X' stair up/down, 'w' floor with an obstacle building,
-- '?' hidden, 'v' ramp, '^' ramp top, ' ' empty.
function make_world(layers, spec)
  local LEG = {
    ['#'] = { shape = "WALL" },
    ['.'] = { shape = "FLOOR" },
    ['D'] = { shape = "FLOOR", door = { id = 1, forbidden = false } },
    ['F'] = { shape = "FLOOR", door = { id = 2, forbidden = true } },
    ['<'] = { shape = "STAIR_UP" },
    ['>'] = { shape = "STAIR_DOWN" },
    ['X'] = { shape = "STAIR_UPDOWN" },
    ['w'] = { shape = "FLOOR", blocked = true },
    ['?'] = { hidden = true },
    ['v'] = { shape = "RAMP" },
    ['^'] = { shape = "RAMP_TOP" },
    [' '] = { shape = "EMPTY" },
  }
  local world = {
    sites = spec.sites or {}, reservations = spec.reservations or {},
    zones = spec.zones or {}, landmarks = spec.landmarks or {},
  }
  world.reads = 0
  world.read_tile = function(x, y, z)
    world.reads = world.reads + 1
    local layer = layers[z]
    if not layer then return { shape = "WALL" } end
    local row = layer[y + 1]
    if not row or x < 0 or x >= #row then return { shape = "WALL" } end
    local ch = row:sub(x + 1, x + 1)
    local t = LEG[ch]
    local copy = {}
    for k, v in pairs(t) do copy[k] = v end
    return copy
  end
  world.group_at = function(x, y, z) return 1 end
  return world
end
