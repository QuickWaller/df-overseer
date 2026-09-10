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
-- Usage: ./dfhack-run df-overseer-connectivity <report|check FROM TO|check-units UNIT_ID UNIT_ID>
--   report              -- get_connectivity_report(): stranded groups (each
--                          now with near_landmark/direction/distance_tiles,
--                          see below) + main group id
--   check FROM TO        -- check_reachable(): named landmark endpoints,
--                          resolved via df-overseer-landmarks.lua's
--                          get_landmark_centroid (reqscript'd, same pattern
--                          this file already used for warn-stranded's
--                          getStrandedGroups). This replaces the original
--                          stopgap now that the landmark system exists
--                          (build order item 3, 2026-09-10).
--   check-units A B      -- the old unit-id-only form, kept for low-level
--                          debugging (e.g. checking a specific citizen
--                          against another without naming a landmark).
--
-- near_landmark was omitted in the first version of this file, not stubbed
-- with raw coordinates: design commitment #1 (docs/PURPOSE.md) rules out
-- exposing raw map geometry to the model, and the research spec explicitly
-- replaced the original draft's approx_pos field with near_landmark for
-- exactly that reason (research/2026-08-25-spatial-perception.md §5). Now
-- wired in via df-overseer-landmarks.lua's nearest_landmark(x,y,z), which
-- keeps the same server-side-only coordinate discipline: the centroid
-- computed here never leaves this file, only the resulting landmark
-- name/direction/distance does.
--
-- JSON key order is deterministic without any manual sorting: DFHack's own
-- json.lua delegates encoding to a C++ (jsonxx-derived) internal module,
-- confirmed live across repeated fresh process runs to emit object keys in
-- stable alphabetical order regardless of Lua table insertion order.

local json = require('json')
local stranded = reqscript('warn-stranded')
local landmarks = reqscript('df-overseer-landmarks')

local function unit_name(unit)
  return dfhack.translation.translateName(dfhack.units.getVisibleName(unit))
end

-- Mean position of a stranded group's units, for a nearest_landmark lookup.
-- Server-side only, per the comment above -- never printed raw.
local function group_centroid(units)
  local sx, sy, sz = 0, 0, 0
  for _, unit in ipairs(units) do
    local pos = xyz2pos(dfhack.units.getPosition(unit))
    sx, sy, sz = sx + pos.x, sy + pos.y, sz + pos.z
  end
  local n = #units
  return sx / n, sy / n, sz / n
end

local function get_connectivity_report()
  local groupList, _, mainGroup = stranded.getStrandedGroups()
  local strandedGroups = {}
  for _, group in ipairs(groupList) do
    local names = {}
    for _, unit in ipairs(group.units) do
      table.insert(names, unit_name(unit))
    end
    local entry = {
      group_id = group.walkGroup,
      unit_names = names,
    }
    -- Best-effort: a landmark lookup failure (e.g. no citizens at all,
    -- hitting the seed's own error path) must not break the stranded
    -- report itself -- reachability alerts matter more than the anchor.
    local ok_pos, cx, cy, cz = pcall(group_centroid, group.units)
    if ok_pos then
      local ok_near, near = pcall(landmarks.nearest_landmark, cx, cy, cz)
      if ok_near and near then
        entry.near_landmark = near.name
        entry.direction = near.direction
        entry.distance_tiles = near.distance_tiles
      end
    end
    table.insert(strandedGroups, entry)
  end
  return {
    stranded_groups = strandedGroups,
    main_group_id = mainGroup,
  }
end

local function check_reachable(from_name, to_name)
  local ax, ay, az = landmarks.get_landmark_centroid(from_name)
  if not ax then
    return { reachable = false, from_group = -1, to_group = -1,
             note = "landmark not found: " .. from_name }
  end
  local bx, by, bz = landmarks.get_landmark_centroid(to_name)
  if not bx then
    return { reachable = false, from_group = -1, to_group = -1,
             note = "landmark not found: " .. to_name }
  end
  local posA, posB = xyz2pos(ax, ay, az), xyz2pos(bx, by, bz)
  return {
    reachable = dfhack.maps.canWalkBetween(posA, posB),
    from_group = dfhack.maps.getWalkableGroup(posA),
    to_group = dfhack.maps.getWalkableGroup(posB),
  }
end

local function check_reachable_units(unit_id_a, unit_id_b)
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
  if not args[2] or not args[3] then
    print("usage: df-overseer-connectivity check FROM TO")
  else
    print(json.encode(check_reachable(args[2], args[3])))
  end
elseif cmd == "check-units" then
  local a, b = tonumber(args[2]), tonumber(args[3])
  if not a or not b then
    print("usage: df-overseer-connectivity check-units UNIT_ID UNIT_ID")
  else
    print(json.encode(check_reachable_units(a, b)))
  end
else
  print("usage: df-overseer-connectivity <report|check FROM TO|check-units UNIT_ID UNIT_ID>")
end
