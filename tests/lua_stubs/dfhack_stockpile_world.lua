-- A fake DFHack world for tests/test_stockpile_writing_lua_logic.py:
-- df-overseer-stockpile.lua's writing commands (place, configure, link,
-- unlink), added by handoffs/2026-10-01-stockpile-writing.md.
--
-- Scope, honestly: this models exactly enough of the real game surface to
-- exercise this project's OWN logic -- category validation/letter/preset
-- mapping, the reservation-skip wiring, the enable/disable diff configure
-- computes, and the give/take vector bookkeeping link/unlink does. It does
-- NOT model quickfort itself: `run_command_silent('quickfort', 'run', ...)`
-- is faked here as "parse the #place blueprint file this project's own code
-- just wrote, and construct a stockpile of that shape" -- a much simpler
-- and more permissive stand-in than the real quickfort_building pipeline
-- (place.lua's own is_valid_stockpile_tile, extent grouping, container
-- defaults, and its own do_run stats are none of them exercised here). Per
-- this project's own established caution (the offline fake world has
-- disagreed with the real API twice, tests/test_finder_reservation_skip_lua_logic.py's
-- own header): nothing here proves the real quickfort #place run, the real
-- plugins.stockpiles import/export round trip, or the real link vectors'
-- exact field types on a live building -- only a live run settles those.

local NULL = "\0"

df = {
  building_type = {Stockpile = 1, Workshop = 2, FarmPlot = 3, Furnace = 4},
  -- handoffs/2026-10-07-stockpile-tool-gaps.md: subtype enums, name <-> id,
  -- enough for workshop_kind_name (df[enum][bld.type] -> name).
  workshop_type = {[0] = "Carpenters", [1] = "Still", [2] = "Masons", [3] = "Kitchen",
                   [4] = "Custom", [5] = "Mechanics", [6] = "Craftsdwarfs", [7] = "Butchers",
                   Carpenters = 0, Still = 1, Masons = 2, Kitchen = 3, Custom = 4,
                   Mechanics = 5, Craftsdwarfs = 6, Butchers = 7,
                   _first_item = 0, _last_item = 7},
  furnace_type = {[0] = "WoodFurnace", [1] = "Smelter", WoodFurnace = 0, Smelter = 1,
                  _first_item = 0, _last_item = 1},
  -- 6 (GEM_ODD) is deliberately absent from the hand category table.
  item_type = {[0] = "BOULDER", [1] = "WOOD", [2] = "PLANT", [3] = "BARREL", [4] = "BAR",
               [5] = "BLOCKS", [6] = "GEM_ODD", [7] = "DRINK"},
}
dfhack_flags = {module = true}
package.loaded["json"] = {encode = function() return "" end}
function require(n)
  if package.loaded[n] then return package.loaded[n] end
  return {}
end

CR_OK = 0

-- ---------------------------------------------------------------------------
-- Map/terrain: a settable free-tile grid, read by our fake is_free (wired
-- through reqscript'd "df-overseer-openarea" below), plus getSize/xyz2pos.
-- ---------------------------------------------------------------------------

local FREE = {}
function set_free(x, y, z, free)
  FREE[x] = FREE[x] or {}
  FREE[x][y] = FREE[x][y] or {}
  FREE[x][y][z] = free
end
local function is_free(x, y, z)
  return FREE[x] and FREE[x][y] and FREE[x][y][z] or false
end

function xyz2pos(x, y, z) return {x = x, y = y, z = z} end

dfhack = {
  maps = {
    getSize = function() return 100, 100, 200 end,
  },
  buildings = {},
  items = {},
  run_command_silent = nil,  -- set below, needs access to BUILDINGS
  -- df-overseer-reservations.lua's own abs_tick/load_state/save_state need
  -- these two -- same fakes tests/lua_stubs/dfhack_well_reservations_world.lua
  -- already documents needing for the identical reason.
  persistent = {
    _s = {},
    getSiteData = function(k, default)
      if dfhack.persistent._s[k] == nil then dfhack.persistent._s[k] = default end
      return dfhack.persistent._s[k]
    end,
    saveSiteData = function(k, v) dfhack.persistent._s[k] = v end,
  },
  world = {ReadCurrentTick = function() return 1000 end},
}

-- ---------------------------------------------------------------------------
-- Buildings: a flat list, ids assigned on creation. Stockpiles carry
-- settings.flags (category booleans) and links (the four vectors).
-- Workshops carry profile.links.
-- ---------------------------------------------------------------------------

BUILDINGS = {}
local next_id = 1

-- A dfhack STL-vector proxy is 0-INDEXED (df-overseer-stockpile.lua's own
-- read_links does `for i = 0, n - 1 do vec[i] end`, confirmed by this file's
-- pre-existing `links` command, live-verified per TOOLS.yaml) -- a plain
-- 1-indexed Lua array would silently read one entry short/off-by-one, so
-- this stands in as {n=<count>, [0]=.., [1]=.., ...} with __len returning
-- n, and the fake utils functions below (not the real Lua stdlib
-- table.insert/ipairs, which assume 1-indexing) are what read and write it.
local function new_link_vec()
  return setmetatable({n = 0}, {__len = function(self) return self.n end})
end

-- A 0-indexed dfhack-style vector of booleans/values, with __len.
function new_vec(values)
  local v = setmetatable({n = #values}, {__len = function(self) return self.n end})
  for i, val in ipairs(values) do v[i - 1] = val end
  return v
end

-- Game material lists the material filters read (df.global.world.raws).
-- Index 0 is a metal (not IS_STONE) so the include filter has work to do.
RAWS = {
  inorganics = new_vec({
    {id = "NATIVE_GOLD", material = {flags = {IS_STONE = false}}},
    {id = "GRANITE", material = {flags = {IS_STONE = true}}},
    {id = "MARBLE", material = {flags = {IS_STONE = true}}},
    {id = "HEMATITE", material = {flags = {IS_STONE = true}}},
  }),
  reactions = {reactions = new_vec({}), },
  plants = {all = new_vec({
    {id = "OAK", flags = {TREE = true}},
    {id = "WHEAT", flags = {TREE = false}},
    {id = "BIRCH", flags = {TREE = true}},
  })},
}

local function make_stockpile(x, y, z, w, h, flags, no_container_fields)
  local bld = {
    id = next_id, x1 = x, x2 = x + w - 1, y1 = y, y2 = y + h - 1, z = z,
    _type = df.building_type.Stockpile,
    settings = {
      flags = flags or {},
      stone = {mats = new_vec({false, false, false, false})},
      wood = {mats = new_vec({false, false, false})},
    },
    _contents = {},
    links = {
      give_to_pile = new_link_vec(), take_from_pile = new_link_vec(),
      give_to_workshop = new_link_vec(), take_from_workshop = new_link_vec(),
    },
  }
  if not no_container_fields then
    bld.use_links_only = 0
    bld.max_barrels = w * h
    bld.max_bins = w * h
    bld.max_wheelbarrows = 0
  end
  function bld:getType() return self._type end
  next_id = next_id + 1
  table.insert(BUILDINGS, bld)
  return bld
end

-- Test helper: a stockpile with chosen category flags, no quickfort.
function make_pile(x, y, z, w, h, flags, no_container_fields)
  return make_stockpile(x, y, z, w, h, flags, no_container_fields)
end

-- Test helper: put n items in a pile, one per tile along its top row.
function fill_pile(bld, n)
  bld._contents = {}
  for i = 1, n do
    table.insert(bld._contents, {x = bld.x1 + (i - 1) % (bld.x2 - bld.x1 + 1), y = bld.y1, z = bld.z})
  end
end

function make_workshop(x, y, z, kind, building_type)
  local bld = {
    id = next_id, x1 = x, x2 = x, y1 = y, y2 = y, z = z,
    _type = building_type or df.building_type.Workshop,
    type = (kind and (df.workshop_type[kind] or df.furnace_type[kind])) or 0,
    profile = {
      links = {
        give_to_pile = new_link_vec(), take_from_pile = new_link_vec(),
        give_to_workshop = new_link_vec(), take_from_workshop = new_link_vec(),
      },
    },
  }
  function bld:getType() return self._type end
  next_id = next_id + 1
  table.insert(BUILDINGS, bld)
  return bld
end

df.global = {
  cur_year = 1,  -- df-overseer-reservations.lua's own abs_tick reads this
  world = {
    raws = RAWS,
    buildings = {
      all = BUILDINGS,
      other = {
        STOCKPILE = setmetatable({}, {
          __len = function() return 0 end,  -- max_stockpile_id: no pre-existing piles in a fresh test
          __index = function() return nil end,
        }),
      },
    },
  },
}

function dfhack.buildings.findAtTile(pos)
  for _, b in ipairs(BUILDINGS) do
    if b._type == df.building_type.Stockpile and pos.x >= b.x1 and pos.x <= b.x2
        and pos.y >= b.y1 and pos.y <= b.y2 and pos.z == b.z then
      return b
    end
  end
  return nil
end

function dfhack.buildings.containsTile(bld, x, y)
  return x >= bld.x1 and x <= bld.x2 and y >= bld.y1 and y <= bld.y2
end

function dfhack.buildings.getStockpileContents(bld) return bld._contents or {} end
dfhack.items.getPosition = function(it) return it.x, it.y, it.z end

function make_furnace(x, y, z, kind)
  return make_workshop(x, y, z, kind, df.building_type.Furnace)
end

DECONSTRUCTED = {}
function dfhack.buildings.deconstruct(bld)
  table.insert(DECONSTRUCTED, bld.id)
  for i, b in ipairs(BUILDINGS) do
    if b == bld then table.remove(BUILDINGS, i) break end
  end
end

-- Fake dfhack.workshops.getJobs: per kind NAME, a list of jobs shaped like the
-- real module's output (items = reagent specs, job_fields). A kind with no
-- entry returns nil, like a failed getJobs, so the hand fallback table is used.
FAKE_JOBS = {}
local function spec(item_type, flags)
  local f = flags or {}
  return {item_type = item_type, quantity = 1, flags1 = f.flags1 or {}, flags2 = f.flags2 or {},
          flags3 = f.flags3 or {}}
end
local function job(items, reaction)
  return {items = items, job_fields = {job_type = 0, reaction_name = reaction}}
end
-- the tag-matched "empty food storage container" reagent of a brew job
local function container_spec() return spec(-1, {flags2 = {food_storage = true, empty = true}}) end
FAKE_JOBS.Still = {job({spec(2), container_spec()}, "BREW_FROM_PLANT"),
                   job({spec(2), container_spec()}, "BREW_FROM_PLANT_2")}
FAKE_JOBS.Masons = {job({spec(0)}), job({spec(0)}), job({spec(0)})}
FAKE_JOBS.Carpenters = {job({spec(1)}), job({spec(1)})}
FAKE_JOBS.Kitchen = {job({spec(2)}, "PREPARE_MEAL")}
FAKE_JOBS.Smelter = {job({spec(0)}), job({spec(0)})}
FAKE_JOBS.Craftsdwarfs = {job({spec(0)}), job({spec(1)})}
FAKE_JOBS.Butchers = {job({spec(6), spec(2)})}
RAWS.reactions.reactions = new_vec({
  {code = "BREW_FROM_PLANT", products = new_vec({{item_type = 7}})},
  {code = "BREW_FROM_PLANT_2", products = new_vec({{item_type = 7}})},
  {code = "PREPARE_MEAL", products = new_vec({{item_type = 2}, {item_type = 6}})},
})
GETJOBS_CALLS = 0
package.loaded["dfhack.workshops"] = {
  getJobs = function(btype, sub, custom)
    GETJOBS_CALLS = GETJOBS_CALLS + 1
    local name = (btype == df.building_type.Workshop) and df.workshop_type[sub] or df.furnace_type[sub]
    return FAKE_JOBS[name]
  end,
}

STOCKS_AVAILABLE = {}
function set_availability(key, units) STOCKS_AVAILABLE[key] = units end

dfhack.maps.isTileVisible = function() return true end

-- ---------------------------------------------------------------------------
-- Fake quickfort: parses the #place CSV this project's own code wrote,
-- reads its one repeated key, and constructs a Stockpile of that shape with
-- every requested category's flag set true -- see this file's own header
-- for exactly what this does and does not prove.
-- ---------------------------------------------------------------------------

-- letter -> category name, the inverse of df-overseer-stockpile.lua's own
-- CATEGORY_INFO (duplicated here deliberately: this is the fake world
-- checking the real file's output, not sharing its table).
local LETTER_TO_CATEGORY = {
  a = "animals", f = "food", u = "furniture", r = "refuse", s = "stone",
  w = "wood", e = "gems", g = "finished_goods", l = "leather", h = "cloth",
  S = "sheet", b = "bars_blocks", p = "weapons", d = "armor", z = "ammo",
  n = "coins", y = "corpses",
}

QUICKFORT_CALLS = {}
dfhack.run_command_silent = function(tool, action, filename, ...)
  table.insert(QUICKFORT_CALLS, {tool = tool, action = action, filename = filename, args = {...}})
  local args = {...}
  local dash_c_idx
  for i, a in ipairs(args) do if a == '-c' then dash_c_idx = i end end
  local coord = dash_c_idx and args[dash_c_idx + 1]
  local dry = false
  for _, a in ipairs(args) do if a == '-d' then dry = true end end

  -- quickfort resolves a bare filename against dfhack-config/blueprints/,
  -- not the working directory (this project's own documented trap, see
  -- df-overseer-openarea.lua's build_open_area comment) -- the real file
  -- writes there and passes quickfort the bare name, so the fake must
  -- resolve it the same way rather than opening the bare name directly.
  local f = io.open("dfhack-config/blueprints/" .. filename, "r")
  if not f then return "file not found", 1 end
  local lines = {}
  for line in f:lines() do table.insert(lines, line) end
  f:close()
  local h = #lines - 1  -- first line is the "#place ..." header
  local w = 0
  local key = ""
  if #lines > 1 then
    local cells = {}
    for cell in lines[2]:gmatch('[^,]+') do table.insert(cells, cell) end
    w = #cells
    key = cells[1] or ""
  end

  if dry then
    return string.format("Blueprint statistics:\n  Stockpiles designated: 1\n"), CR_OK
  end

  local cx, cy, cz = coord:match('(%-?%d+),(%-?%d+),(%-?%d+)')
  cx, cy, cz = tonumber(cx), tonumber(cy), tonumber(cz)
  local flags = {}
  for letter in key:gmatch('.') do
    local cat = LETTER_TO_CATEGORY[letter]
    if cat then flags[cat] = true end
  end
  make_stockpile(cx, cy, cz, w, h, flags)
  return string.format("Blueprint statistics:\n  Stockpiles designated: 1\n"), CR_OK
end

-- ---------------------------------------------------------------------------
-- utils.insert_sorted / erase_sorted_key: faked over the plain-array link
-- vectors above, matching Lua API.rst's documented contract closely enough
-- for this project's own call shape (vector, item, 'id').
-- ---------------------------------------------------------------------------

package.loaded["utils"] = {
  insert_sorted = function(vec, item, field)
    for i = 0, vec.n - 1 do
      if vec[i][field] == item[field] then return false, vec[i] end
    end
    local pos = vec.n
    for i = 0, vec.n - 1 do
      if vec[i][field] > item[field] then pos = i break end
    end
    for i = vec.n, pos + 1, -1 do vec[i] = vec[i - 1] end
    vec[pos] = item
    vec.n = vec.n + 1
    return true, item
  end,
  erase_sorted_key = function(vec, key, field)
    for i = 0, vec.n - 1 do
      if vec[i][field] == key then
        for j = i, vec.n - 2 do vec[j] = vec[j + 1] end
        vec[vec.n - 1] = nil
        vec.n = vec.n - 1
        return true
      end
    end
    return false
  end,
}

-- ---------------------------------------------------------------------------
-- plugins.stockpiles: fakes only import_settings -- sets/clears the
-- category's own top-level flag, mirroring StockpileSerializer's
-- read_category ENABLE/DISABLE semantics (see the real file's own header
-- citation) at the coarse level this project's configure command uses.
-- ---------------------------------------------------------------------------

local function find_bld(id)
  for _, b in ipairs(BUILDINGS) do
    if b.id == id then return b end
  end
  return nil
end

package.loaded["plugins.stockpiles"] = {
  import_settings = function(name, opts)
    local cat = name:match("^library/cat_(.+)$")
    local bld = find_bld(opts.id)
    if not bld or not cat then return end
    -- reverse the "sheets" plural preset spelling back to the struct field
    if cat == "sheets" then cat = "sheet" end
    bld.settings.flags[cat] = (opts.mode == "enable")
  end,
}

-- ---------------------------------------------------------------------------
-- Landmarks / openarea / reservations: same narrow-fake pattern
-- tests/lua_stubs/dfhack_workshop_kind_world.lua already uses. Reservations
-- is loaded FOR REAL (a dependency-free leaf, per
-- tests/lua_stubs/dfhack_well_reservations_world.lua's own header) so
-- filter_reserved/check_tiles are proven against the real file, not a
-- second fake of them.
-- ---------------------------------------------------------------------------

local ANCHOR = {x = 50, y = 50, z = 10}
function set_anchor(x, y, z) ANCHOR = {x = x, y = y, z = z} end

local landmarks = {
  get_landmark_centroid = function(name) return ANCHOR.x, ANCHOR.y, ANCHOR.z end,
  nearest_landmark = function(x, y, z) return {name = "Anchor", direction = "here", distance_tiles = 0} end,
}
local openarea = {is_free = is_free}

-- df-overseer-reservations.lua is loaded FOR REAL (a dependency-free leaf),
-- not faked a second time -- same technique
-- tests/lua_stubs/dfhack_well_reservations_world.lua's own header documents
-- and its own comments explain in full: real `reqscript` gives a loaded
-- script its OWN environment table backed by the shared globals via
-- `__index = _G`, which is what turns reservations.lua's own unqualified
-- `function get_raw(...)` etc. into `reservations_mod.get_raw`. The path to
-- the real file is passed as this stub chunk's own `...` argument.
local RESERVATIONS_LUA_PATH, KINDS_LUA_PATH = ...
local RESERVATIONS_MOD = nil
local KINDS_MOD = nil

function reqscript(n)
  if n == "df-overseer-landmarks" then return landmarks end
  if n == "df-overseer-openarea" then return openarea end
  if n == "df-overseer-reservations" then
    if not RESERVATIONS_MOD then
      local f = io.open(RESERVATIONS_LUA_PATH, "r")
      local src = f:read("*a")
      f:close()
      local env = setmetatable({}, {__index = _G})
      local chunk = assert(load(src, "reservations.lua", "t", env))
      chunk()
      RESERVATIONS_MOD = env
    end
    return RESERVATIONS_MOD
  end
  if n == "df-overseer-stockpile-kinds" then
    if not KINDS_MOD then
      local f = io.open(KINDS_LUA_PATH, "r")
      local src = f:read("*a")
      f:close()
      local env = setmetatable({dfhack_flags = {module = true}}, {__index = _G})
      local chunk = assert(load(src, "stockpile-kinds.lua", "t", env))
      chunk()
      KINDS_MOD = env
    end
    return KINDS_MOD
  end
  if n == "df-overseer-stocks" then
    return {get_availability = function(key)
      return {available_units = STOCKS_AVAILABLE[key] or 0}
    end}
  end
  return {}
end
