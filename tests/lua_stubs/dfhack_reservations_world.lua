-- A minimal fake DFHack world for tests/test_reservations_lua_logic.py, which
-- runs the REAL scripts/dfhack/df-overseer-reservations.lua against it in
-- lupa. reservations.lua is a dependency-free leaf (its own header): it only
-- needs dfhack.persistent, dfhack.world.ReadCurrentTick, and a
-- reqscript('df-overseer-landmarks') stub, so this fake world is small.

NOW = 1000
YEAR = 0

-- cur_year for abs_tick(): absolute tick = YEAR * 403200 + NOW.
df = {global = setmetatable({}, {__index = function(_, k) if k == 'cur_year' then return YEAR end end})}

dfhack_flags = {module = true}

dfhack = {
  persistent = {
    _s = {},
    getSiteData = function(k, default)
      if dfhack.persistent._s[k] == nil then dfhack.persistent._s[k] = default end
      return dfhack.persistent._s[k]
    end,
    saveSiteData = function(k, v) dfhack.persistent._s[k] = v end,
  },
  world = {ReadCurrentTick = function() return NOW end},
}

local LANDMARKS = {
  nearest_landmark = function(x, y, z) return {name = "Well", direction = "NE", distance_tiles = 7} end,
}

function reqscript(n)
  if n == "df-overseer-landmarks" then return LANDMARKS end
  return {}
end
function require(n) return package.loaded and package.loaded[n] end
