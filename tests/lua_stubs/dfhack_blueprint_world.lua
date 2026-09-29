-- A minimal fake DFHack world (tiles, quickfort, persistent state, a stub surface
-- module with the module-local find_zone the blueprint verb swaps). Loaded by
-- tests/test_blueprint_lua_logic.py, which runs the REAL df-overseer-blueprint.lua
-- against it in lupa. It proves the file's own logic (parse, soil rule, order
-- guard, stats assessment, handles, the shim), not any real DFHack behaviour.

-- ---- stub DFHack world ----
local function enum(names) local t = {} for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end return t end
df = {
  tiletype_material = enum({"AIR","SOIL","STONE","FEATURE","LAVA_STONE","MINERAL","FROZEN_LIQUID","CONSTRUCTION","GRASS_LIGHT","TREE"}),
  tiletype_shape = enum({"EMPTY","FLOOR","WALL","FORTIFICATION","RAMP"}),
  tiletype_special = enum({"NORMAL","SMOOTH"}),
  tile_dig_designation = {No = 0, Default = 1},
  tiletype = {attrs = {}},
  job_type = enum({"Dig","DigChannel","SmoothWall","ConstructBuilding"}),
  -- cur_year: abs_tick() (df-overseer-reservations.lua) reads it with
  -- ReadCurrentTick; tests move time with NOW (and YEAR where a year boundary matters).
  global = setmetatable({world = {jobs = {list = {next = nil}}}}, {__index = function(_, k) if k == 'cur_year' then return YEAR or 0 end end}),
}
-- set_jobs({{job_type="Dig", x=, y=, z=}, ...}) rebuilds the linked list
-- DFHack exposes at df.global.world.jobs.list.
function set_jobs(list)
  local head = nil
  for i = #list, 1, -1 do
    local j = list[i]
    head = {item = {job_type = df.job_type[j.job_type], pos = {x = j.x, y = j.y, z = j.z}, worker = j.worker, worker_fails = j.worker_fails}, next = head}
  end
  df.global.world.jobs.list.next = head
end
CR_OK = 0
function xyz2pos(x, y, z) return {x = x, y = y, z = z} end
function set_dig(x, y, z, v) TILES[x .. ',' .. y .. ',' .. z].dig = v end
-- tiles: key "x,y,z" -> {shape, material, special, dig, smooth, occupied}
TILES = {}
local function key(x, y, z) return x .. "," .. y .. "," .. z end
function set_tile(x, y, z, shape, mat, special, extra)
  local id = #df.tiletype.attrs + 1
  df.tiletype.attrs[id] = {shape = df.tiletype_shape[shape], material = df.tiletype_material[mat], special = df.tiletype_special[special or "NORMAL"]}
  TILES[key(x, y, z)] = {tt = id, dig = 0, smooth = 0, occupied = extra and extra.occupied, hidden = extra and extra.hidden}
end
dfhack = {
  job = {getWorker = function(job) if job.worker_fails then error("getWorker boom") end return job.worker end},
  maps = {
    isValidTilePos = function(x, y, z) return TILES[key(x, y, z)] ~= nil end,
    isTileVisible = function(x, y, z) return not TILES[key(x, y, z)].hidden end,
    getTileType = function(x, y, z) return TILES[key(x, y, z)].tt end,
    getWalkableGroup = function(pos)
      local t = TILES[key(pos.x, pos.y, pos.z)]
      if not t or t.hidden then return 0 end
      local shape = df.tiletype.attrs[t.tt].shape
      return (shape == df.tiletype_shape.FLOOR or shape == df.tiletype_shape.RAMP) and 1 or 0
    end,
    getTileFlags = function(pos) local t = TILES[key(pos.x, pos.y, pos.z)]; return {dig = t.dig, smooth = t.smooth} end,
  },
  buildings = {findAtTile = function(pos) return TILES[key(pos.x, pos.y, pos.z)].occupied and {} or nil end},
  persistent = {
    -- Keyed by STATE_KEY (handoffs/2026-09-30-room-reservations.md: this
    -- stub now also loads the real df-overseer-reservations.lua, which
    -- persists under its OWN key, 'df-overseer-reservations_v1' -- a single
    -- unkeyed slot would collide the two files' state).
    _s = {},
    getSiteData = function(k, default)
      if dfhack.persistent._s[k] == nil then dfhack.persistent._s[k] = default end
      return dfhack.persistent._s[k]
    end,
    saveSiteData = function(k, v) dfhack.persistent._s[k] = v end,
  },
  world = {ReadCurrentTick = function() return NOW or 1234 end},
  printerr = function(m) ERRS = (ERRS or "") .. m .. "\n" end,
  run_command_silent = function(cmd, ...)
    local a = {...}
    CALLS = CALLS or {}
    CALLS[#CALLS + 1] = cmd .. " " .. table.concat(a, " ")
    if ON_QF then ON_QF(cmd, a) end
    return QF_OUTPUT or "", CR_OK
  end,
}
dfhack_flags = {module = true}
local json = {encode = function(v) return "json" end}
package.loaded["json"] = json
function require(n) return package.loaded[n] end

-- diggable stub with the ranked_candidates upvalue
local ranked_candidates = function(w, h, level, near, radius)
  if near == "Nowhere" then return nil, "landmark not found: " .. near end
  return {{x = 10, y = 10}, {x = 30, y = 10}}, nil, 5
end
-- landmarks stub
local landmarks = {nearest_landmark = function(x, y, z) return {name = "Well", direction = "NE", distance_tiles = 7} end}
-- surface stub with the module-local find_zone the shim swaps
local find_zone = function(id) error("real find_zone should not be called") end
local surface = {}
function surface.enclosure(id) local b = find_zone(id); return {zone_id = b.id, w = b.x2 - b.x1 + 1, status = "not_enclosed"} end
function surface.finish(id) local b = find_zone(id); return {zone_id = b.id, h = b.y2 - b.y1 + 1} end
function surface.boundary_material(id) local b = find_zone(id); return {zone_id = b.id, ring = 16} end
SURFACE_ORIG = function() return find_zone end
SURFACE = surface
local RESERVATIONS_MOD = nil
-- handoffs/2026-09-30-reservation-holding.md item 1: fake, minimal
-- kind_token_for_key tables, the same shape df-overseer-building.lua's and
-- df-overseer-zone.lua's own exported kind_token_for_key have -- NOT the
-- real files (unlike df-overseer-reservations.lua above, building.lua and
-- zone.lua are not dependency-free: they need dfhack.buildings/df.civzone_type
-- and the rest of the real game API this stub does not model). Keys match
-- the real bedroom-cell-v1.csv ("b" in #build is the bed, "b" in #zone is
-- the bedroom) and office-room-v2.csv ("c"/"o") fixtures this test suite
-- copies onto the guest, so a test reserving either template gets a
-- realistic, non-empty allowed_kinds list.
local BUILD_KIND_BY_KEY = {b = "bed", c = "chair"}
local ZONE_KIND_BY_KEY = {b = "bedroom", o = "office"}
function reqscript(n)
  if n == "df-overseer-landmarks" then return landmarks end
  if n == "df-overseer-diggable" then return {find_diggable_area = function() return ranked_candidates() end} end
  if n == "df-overseer-surface" then return surface end
  if n == "df-overseer-building" then
    return {kind_token_for_key = function(key) return BUILD_KIND_BY_KEY[key] end}
  end
  if n == "df-overseer-zone" then
    return {kind_token_for_key = function(key) return ZONE_KIND_BY_KEY[key] end}
  end
  if n == "df-overseer-reservations" then
    -- Loads the REAL df-overseer-reservations.lua (a dependency-free leaf:
    -- it only reqscripts df-overseer-landmarks, already stubbed above, and
    -- reads dfhack.persistent/dfhack.world.ReadCurrentTick, already stubbed
    -- above too) -- see tests/test_blueprint_lua_logic.py's own comment on
    -- why this is a real load, not a second parallel fake.
    if not RESERVATIONS_MOD then
      local f = io.open(RESERVATIONS_LUA_PATH, "r")
      local src = f:read("*a")
      f:close()
      -- Real DFHack reqscript gives a loaded script its OWN environment
      -- table (backed by the shared globals) and hands that table back as
      -- the "module" -- that is what lets reservations.lua's own unqualified
      -- `function get_raw(...)` etc. become `reservations_mod.get_raw`
      -- instead of polluting this whole test's global table. Replicated
      -- here with a plain __index-to-_G env table, since lupa's default
      -- `load` (no env argument) would run the chunk against the shared
      -- globals directly, same as this stub's own blueprint.lua load below.
      local env = setmetatable({}, {__index = _G})
      local chunk = assert(load(src, "reservations.lua", "t", env))
      chunk()
      RESERVATIONS_MOD = env
    end
    return RESERVATIONS_MOD
  end
end
