-- A minimal fake DFHack world for the zone owner links: zones, units, the
-- unit's owned_buildings vector, the fortress positions, and a fake
-- dfhack.buildings.setOwner that can write both directions of the link, or
-- only one (SET_OWNER_MODE), to prove the tool's read-back notices. Loaded by
-- tests/test_zone_owner_lua_logic.py, which runs the REAL
-- scripts/dfhack/df-overseer-zone.lua against it in lupa. It proves the file's
-- own logic, not what a real DFHack setOwner does: that is the live check.

local function enum(names) local t = {} for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end return t end

-- A 0-indexed vector the way DFHack exposes them: v[0]..v[#v-1].
local function vec(list)
  local v = {}
  for i, x in ipairs(list) do v[i - 1] = x end
  return setmetatable(v, {__len = function() return #list end})
end
-- An owned_buildings vector that tracks its own length as items are added/removed.
local function new_vec()
  local items = {}
  local v = {_items = items}
  return setmetatable(v, {
    __len = function() return #items end,
    __index = function(_, k) if type(k) == "number" then return items[k + 1] end end,
  })
end

ZONES, UNITS, BUILDINGS = {}, {}, {}
SET_OWNER_MODE = "both"    -- both | zone_only | unit_only
SET_OWNER_CALLS = {}
GET_OWNER_FAILS = false
DESC_FAILS = false
ROOM_DESC = ""
ERRS = ""

df = {
  civzone_type = enum({"Bedroom", "Office", "DiningHall", "Tomb", "MeetingHall", "Pen"}),
  building = {find = function(id) return BUILDINGS[id] end},
  building_civzonest = {is_instance = function(_, b) return b ~= nil and b._civzone == true end},
  unit = {find = function(id) return UNITS[id] end},
  historical_figure = {find = function(id) return {unit_id = id} end},
  global = {
    world = {buildings = {other = {ACTIVITY_ZONE = vec({})}}},
    plotinfo = {main = {fortress_entity = {positions = {own = vec({}), assignments = vec({})}}}},
  },
}

function add_zone(id, kind, assigned)
  local z = {id = id, type = df.civzone_type[kind], assigned_unit_id = assigned or -1, _civzone = true}
  ZONES[#ZONES + 1] = z
  BUILDINGS[id] = z
  df.global.world.buildings.other.ACTIVITY_ZONE = vec(ZONES)
  if assigned and assigned >= 0 and UNITS[assigned] then
    UNITS[assigned].owned_buildings._items[#UNITS[assigned].owned_buildings._items + 1] = z
  end
  return z
end
function add_workshop(id) BUILDINGS[id] = {id = id, type = 0, _civzone = false} end
function add_unit(id, alive, citizen)
  UNITS[id] = {id = id, _alive = alive ~= false, _citizen = citizen ~= false, owned_buildings = new_vec()}
end
-- positions: list of {code=, id=, required_office=, ..., holder_unit=}
function set_positions(list)
  local own, assign = {}, {}
  for _, p in ipairs(list) do
    own[#own + 1] = {id = p.id, code = p.code, required_office = p.required_office or 0,
      required_bedroom = p.required_bedroom or 0, required_dining = p.required_dining or 0,
      required_tomb = p.required_tomb or 0}
    if p.holder_unit then assign[#assign + 1] = {position_id = p.id, histfig = p.holder_unit} end
  end
  df.global.plotinfo.main.fortress_entity.positions = {own = vec(own), assignments = vec(assign)}
end
function zone_assigned(id) return BUILDINGS[id].assigned_unit_id end
function unit_owned_ids(uid)
  local out = {}
  for _, b in ipairs(UNITS[uid].owned_buildings._items) do out[#out + 1] = b.id end
  return out
end

dfhack = {
  units = {
    isAlive = function(u) return u._alive end,
    isCitizen = function(u) return u._citizen end,
  },
  buildings = {
    getOwner = function(z)
      if GET_OWNER_FAILS then error("getOwner boom") end
      if z.assigned_unit_id >= 0 then return UNITS[z.assigned_unit_id] end
      return nil
    end,
    getRoomDescription = function(z)
      if DESC_FAILS then error("desc boom") end
      return ROOM_DESC
    end,
    setOwner = function(z, u)
      SET_OWNER_CALLS[#SET_OWNER_CALLS + 1] = {zone = z.id, unit = u and u.id or false}
      local prev = z.assigned_unit_id >= 0 and UNITS[z.assigned_unit_id] or nil
      if SET_OWNER_MODE ~= "zone_only" and prev then
        local items = prev.owned_buildings._items
        for i = #items, 1, -1 do if items[i].id == z.id then table.remove(items, i) end end
      end
      if SET_OWNER_MODE ~= "unit_only" then
        z.assigned_unit_id = u and u.id or -1
      end
      if SET_OWNER_MODE ~= "zone_only" and u then
        local items = u.owned_buildings._items
        items[#items + 1] = z
      end
      return true
    end,
  },
  printerr = function(m) ERRS = ERRS .. m .. "\n" end,
}
dfhack_flags = {module = true}
package.loaded["json"] = {encode = function() return "json" end}
function require(n) return package.loaded[n] end
function reqscript(n) return {} end
function clear_unit_items(uid) local it = UNITS[uid].owned_buildings._items for i = #it, 1, -1 do it[i] = nil end end
