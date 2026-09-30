-- A minimal fake DFHack world for tests/test_workshop_kind_lua_logic.py:
-- proves df-overseer-workshop.lua's real `resolve_workshop_kind`
-- (handoffs/2026-09-30-reservation-gaps.md item 2) resolves a workshop kind
-- through a FAKE df-overseer-building.lua's own `list_kinds` (only
-- list_kinds is used, the same narrow fake
-- tests/lua_stubs/dfhack_construction_world.lua's own resolve_construction_kind
-- test already uses -- building.lua itself is not a touched surface this
-- stream and needs the real game API, so faking only the one function this
-- file actually calls is the honest choice, not a guess at building.lua's
-- own internals).

local NULL = "\0"

df = {}
dfhack_flags = {module = true}
package.loaded["json"] = {encode = function() return "" end}
function require(n) return package.loaded[n] end

-- KINDS: list of {type=, subtype=, token=, key=, label=}, set by set_kinds().
KINDS = {}
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

local landmarks = {nearest_landmark = function() return nil end, get_landmark_centroid = function() return nil end}
local openarea = {is_free = function() return false end}

function reqscript(n)
  if n == "df-overseer-building" then return FAKE_BUILDING end
  if n == "df-overseer-landmarks" then return landmarks end
  if n == "df-overseer-openarea" then return openarea end
  if n == "df-overseer-reservations" then return {} end
  if n == "df-overseer-stocks" then return {} end
  return {}
end
