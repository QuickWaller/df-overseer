-- df-overseer-connectivity.lua
--
-- check_reachable / get_connectivity_report: the first real perception-layer
-- primitives, docs/PURPOSE.md build order item 2. Reuses warn-stranded.lua's
-- verified getStrandedGroups() (loaded via reqscript) rather than
-- reimplementing the walkability-group grouping logic -- same reasoning as
-- df-overseer-ui.lua: depend on tested stock DFHack code instead of
-- re-deriving it. Confirmed live 2026-09-10 against a real fort (Uniboslan):
-- reqscript('warn-stranded').getStrandedGroups() returns the exact grouped
-- data this file reshapes into the research spec's JSON shape
-- (research/2026-08-25-spatial-perception.md).
--
-- Usage: ./dfhack-run df-overseer-connectivity <report|check UNIT_ID UNIT_ID>
--   report      -- get_connectivity_report(): JSON, stranded groups + main group id
--   check A B   -- check_reachable() stopgap: takes two citizen unit ids, not
--                  landmark names -- the landmark system (build order item 3)
--                  doesn't exist yet, so named endpoints aren't resolvable.
--                  Replace this stopgap's signature once get_landmark() exists.
--
-- near_landmark (part of the research spec's stranded_groups shape) is
-- intentionally omitted here, not stubbed with raw coordinates: design
-- commitment #1 (docs/PURPOSE.md) rules out exposing raw map geometry to the
-- model, and the research spec explicitly replaced the original draft's
-- approx_pos field with near_landmark for exactly that reason. Wire this in
-- once the landmark system exists rather than leaking coordinates now.
--
-- JSON key order is deterministic without any manual sorting: DFHack's own
-- json.lua delegates encoding to a C++ (jsonxx-derived) internal module,
-- confirmed live across repeated fresh process runs to emit object keys in
-- stable alphabetical order regardless of Lua table insertion order.

local json = require('json')
local stranded = reqscript('warn-stranded')

local function unit_name(unit)
  return dfhack.translation.translateName(dfhack.units.getVisibleName(unit))
end

local function get_connectivity_report()
  local groupList, _, mainGroup = stranded.getStrandedGroups()
  local strandedGroups = {}
  for _, group in ipairs(groupList) do
    local names = {}
    for _, unit in ipairs(group.units) do
      table.insert(names, unit_name(unit))
    end
    table.insert(strandedGroups, {
      group_id = group.walkGroup,
      unit_names = names,
    })
  end
  return {
    stranded_groups = strandedGroups,
    main_group_id = mainGroup,
  }
end

local function check_reachable(unit_id_a, unit_id_b)
  local a = df.unit.find(unit_id_a)
  local b = df.unit.find(unit_id_b)
  if not a or not b then
    return { reachable = false, from_group = -1, to_group = -1,
             note = "unit id not found" }
  end
  local posA = xyz2pos(dfhack.units.getPosition(a))
  local posB = xyz2pos(dfhack.units.getPosition(b))
  return {
    reachable = dfhack.maps.canWalkBetween(posA, posB),
    from_group = dfhack.maps.getWalkableGroup(posA),
    to_group = dfhack.maps.getWalkableGroup(posB),
  }
end

local args = {...}
local cmd = args[1]

if cmd == "report" then
  print(json.encode(get_connectivity_report()))
elseif cmd == "check" then
  local a, b = tonumber(args[2]), tonumber(args[3])
  if not a or not b then
    print("usage: df-overseer-connectivity check UNIT_ID UNIT_ID")
  else
    print(json.encode(check_reachable(a, b)))
  end
else
  print("usage: df-overseer-connectivity <report|check UNIT_ID UNIT_ID>")
end
