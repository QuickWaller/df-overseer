-- df-overseer-landmarks.lua
--
-- EXPERIMENTAL, first slice of docs/PURPOSE.md build order item 3 (the
-- landmark system on burrows). Not the full system -- burrows/buildings
-- give free landmark nodes once anything exists to name, but a fresh
-- embark has none: no burrow, no building, and (confirmed live 2026-09-10
-- against Uniboslan) not even a wagon object (world.vehicles.all is
-- empty for this embark profile). Every downstream tool that expresses
-- results relative to a named landmark (find_open_area's `near` param,
-- get_connectivity_report's near_landmark field) has nothing to anchor to
-- on day one without this. User's framing, 2026-09-10: try this as a
-- genuine experiment, not a settled design -- see decisions/DECISIONS.md.
--
-- The seed landmark, "Embark Site", is the centroid of citizen positions
-- at first use (not a wagon -- confirmed unreliable/absent above), computed
-- once and persisted via dfhack.persistent.saveSiteData (the same
-- site-scoped mechanism warn-stranded.lua uses for its own state, so it
-- survives saves/reloads correctly). Once real burrows/buildings exist,
-- they become additional landmarks; this seed is meant to be one node
-- among many, not a replacement for the fuller system.
--
-- Usage: ./dfhack-run df-overseer-landmarks <list|get NAME>

local json = require('json')

local GLOBAL_KEY = 'df-overseer-landmarks_v1'

local function compute_embark_site_centroid()
  local citizens = dfhack.units.getCitizens(true)
  if #citizens == 0 then
    return nil, "no citizens found -- can't compute an embark-site centroid"
  end
  local sx, sy, sz = 0, 0, 0
  for _, unit in ipairs(citizens) do
    local pos = xyz2pos(dfhack.units.getPosition(unit))
    sx, sy, sz = sx + pos.x, sy + pos.y, sz + pos.z
  end
  local n = #citizens
  return {
    name = "Embark Site",
    kind = "seed",
    x = math.floor(sx / n + 0.5),
    y = math.floor(sy / n + 0.5),
    z = math.floor(sz / n + 0.5),
  }
end

-- Returns the persisted landmark table and an optional error string.
-- Computes and saves the seed landmark on first call. Currently always
-- exactly one entry (the seed); this is the extension point for real
-- burrow/building enumeration later. Two return values (not one) so a
-- failure (e.g. queried before the map has finished loading, confirmed
-- live 2026-09-10 to actually happen right after a "Continue active game"
-- reload) is distinguishable from a genuinely empty landmark set -- callers
-- must not splat this directly into a function taking positional args
-- (json.encode(list_landmarks()) would pass the error string as encode's
-- second, options, argument and crash inside pairs()).
local function list_landmarks()
  local state = dfhack.persistent.getSiteData(GLOBAL_KEY, {landmarks = {}})
  if #state.landmarks == 0 then
    local seed, err = compute_embark_site_centroid()
    if not seed then
      return {}, err
    end
    state.landmarks = {seed}
    dfhack.persistent.saveSiteData(GLOBAL_KEY, state)
  end
  return state.landmarks
end

local function get_landmark(name)
  for _, lm in ipairs(list_landmarks()) do
    if lm.name == name then
      return lm
    end
  end
  return nil
end

local args = {...}
local cmd = args[1]

if cmd == "list" then
  local landmarks, err = list_landmarks()
  print(json.encode(err and {error = err} or landmarks))
elseif cmd == "get" then
  if not args[2] then
    print("usage: df-overseer-landmarks get NAME")
  else
    local lm = get_landmark(args[2])
    print(lm and json.encode(lm) or json.encode({error = "not found"}))
  end
else
  print("usage: df-overseer-landmarks <list|get NAME>")
end
