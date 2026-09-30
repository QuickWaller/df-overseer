-- A minimal fake DFHack world for tests/test_landmarks_footprint_lua_logic.py:
-- proves df-overseer-landmarks.lua's real `build_at_landmark`
-- (handoffs/2026-09-30-reservation-gaps.md item 3) now checks every tile of
-- BLUEPRINT_FILE's own footprint against a reservation, not just its anchor
-- tile -- against the REAL df-overseer-reservations.lua and the REAL
-- df-overseer-blueprint-parse.lua (both dependency-free leaves, loaded from
-- source exactly as tests/lua_stubs/dfhack_blueprint_world.lua's own header
-- documents doing for df-overseer-reservations.lua: real integration, not a
-- second, parallel fake of either).

df = {}
dfhack_flags = {module = true}
package.loaded["json"] = {encode = function() return "" end}
function require(n) return package.loaded[n] end

CR_OK = 0
dfhack = {
  persistent = {
    _s = {},
    getSiteData = function(k, default)
      if dfhack.persistent._s[k] == nil then dfhack.persistent._s[k] = default end
      return dfhack.persistent._s[k]
    end,
    saveSiteData = function(k, v) dfhack.persistent._s[k] = v end,
  },
  world = {ReadCurrentTick = function() return NOW or 1000 end},
  run_command_silent = function(cmd, ...)
    local a = {...}
    CALLS = CALLS or {}
    CALLS[#CALLS + 1] = cmd .. " " .. table.concat(a, " ")
    return QF_OUTPUT or "", CR_OK
  end,
}
df.global = setmetatable({}, {__index = function(_, k) if k == 'cur_year' then return YEAR or 0 end end})

local landmarks_seed = {x = 5, y = 5, z = 5}
local landmarks = {
  nearest_landmark = function(x, y, z) return {name = "Anchor", direction = "N", distance_tiles = 0} end,
}

local RESERVATIONS_MOD = nil
local PARSE_MOD = nil

function reqscript(n)
  if n == "df-overseer-landmarks" then return landmarks end
  if n == "df-overseer-textutil" then return {} end
  if n == "df-overseer-reachability" then return {} end
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
  if n == "df-overseer-blueprint-parse" then
    if not PARSE_MOD then
      local f = io.open(BLUEPRINT_PARSE_LUA_PATH, "r")
      local src = f:read("*a")
      f:close()
      local env = setmetatable({}, {__index = _G})
      local chunk = assert(load(src, "blueprint-parse.lua", "t", env))
      chunk()
      PARSE_MOD = env
    end
    return PARSE_MOD
  end
end

-- get_landmark_centroid is a GLOBAL df-overseer-landmarks.lua function
-- itself (the file under test), not something this stub fakes -- but
-- build_at_landmark calls it directly (same-file global), so it must
-- resolve for real once landmarks.lua loads. This stub only needs to seed
-- what get_landmark_centroid's own real implementation reads
-- (merged_landmarks_with_coords -> dfhack.persistent) -- simplest path:
-- landmarks.lua's own real get_landmark_centroid walks live buildings/
-- burrows plus a persisted seed landmark. Rather than modelling all of
-- that, the test overrides get_landmark_centroid directly after load (see
-- the Python harness) -- this keeps the fake surface to exactly what this
-- test needs, not a guess at landmarks.lua's own unrelated internals.
