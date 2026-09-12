-- df-overseer-threat.lua
--@module = true
--
-- The first of two safety detectors research/2026-09-12-dfhack-capability-
-- checks.md §5 found this project has NO usable signal for: hostile
-- appearance. `INVASION` (df-overseer-diff.lua's event layer) fires only
-- for DF-registered invasions -- not an ambush, a lone thief, a sneaking
-- creature, or wildlife turning aggressive. `df-overseer-labor unit-status
-- hostile` (dfhack.units.isDanger/isInvader) is separately proven wrong in
-- BOTH directions the same day it was tested: missed a real kea attack,
-- flagged harmless deep-cavern demons ~40 z-levels down behind solid rock
-- (decisions/DECISIONS.md 2026-09-11/12).
--
-- THE INSIGHT THIS FILE IS BUILT ON: both failures point the same way. The
-- demons were flagged but unreachable; the kea was reachable but unflagged.
-- A hostility flag got both wrong. Reachability gets both right. So this
-- file filters candidates by whether they can actually get to a citizen --
-- composing df-overseer-connectivity.lua's/df-overseer-openarea.lua's
-- ALREADY-VERIFIED dfhack.maps.getWalkableGroup/canWalkBetween machinery --
-- and treats every isDanger/isInvader/isAgitated/isGreatDanger flag as one
-- input among several, logged and labeled HEURISTIC, never the filter
-- itself. No new hostility heuristic is invented here.
--
-- Two independent reachability criteria (OR, not AND -- see below for why
-- each alone has a real blind spot):
--   1. shares_walkable_group: the candidate's tile and at least one living
--      citizen's tile return the same nonzero dfhack.maps.getWalkableGroup
--      id. This is the mechanism df-overseer-connectivity.lua's
--      check_reachable already uses, unmodified. BLIND SPOT: getWalkableGroup
--      models GROUND pathing connectivity only (Lua API.txt, quoted in
--      df-overseer-openarea.lua's own comment: "only updated while the game
--      is unpaused"). A flying or swimming creature can sit in open air or
--      deep water with group 0 -- genuinely reachable, invisible to this
--      criterion alone. NOT independently verified this session (no live
--      flying-creature case observed) -- flagged as an open question below.
--   2. near_a_landmark: dfhack.units.getPosition(candidate) resolves (via
--      df-overseer-landmarks.lua's nearest_landmark, reqscript'd, same as
--      every other perception tool) within radius_tiles of ANY named
--      landmark -- i.e. "close to something we've built or dug", a proxy for
--      "near the fort" that survives criterion 1's blind spot (a flying
--      hostile hovering right over the dining hall has group 0 but a small
--      near_landmark distance). Its own blind spot: a creature 40 z-levels
--      down but geometrically close in x,y to a landmark's own z (rare, but
--      possible on a tall fort) could pass this check without being
--      remotely reachable -- radius_tiles is deliberately capped (see
--      MAX_RADIUS) precisely to bound how bad this gets, not to eliminate it.
--
-- Neither criterion alone is claimed sufficient; using both as an OR is a
-- deliberate, documented tradeoff, not an oversight. A future version could
-- tighten criterion 2 by also requiring z-proximity -- not attempted here,
-- flagged as an open question in the handoff.
--
-- Wildlife policy, per the design brief verbatim: "Wildlife that is merely
-- present and unreachable is not a threat. Wildlife inside the fort is,
-- regardless of what any flag says." So the FILTER is reachability only --
-- every dfhack.units.isDanger/isInvader/isAgitated/isGreatDanger flag is
-- read and reported, never used to admit or reject a candidate. This means
-- a harmless songbird that wanders into the walkable network WILL appear in
-- the ranked list (ranked low, since it carries no flag and no isFortControlled
-- exclusion applies to genuinely wild animals) -- a deliberate consequence of
-- "never let the flag be the decision", not a bug. Tuning how much wildlife
-- noise this produces on a real fort is explicitly UNVERIFIED (see handoff).
--
-- Exclusions: dfhack.units.isDead(unit) (a corpse is not a threat) and
-- dfhack.units.isOwnCiv(unit) OR dfhack.units.isFortControlled(unit).
-- isOwnCiv matches df-overseer-labor.lua's existing hostile-filter precedent
-- (kept for continuity); isFortControlled is ADDED here, not present in that
-- file -- its own shipped doc text (Lua API.txt: "isFortControlled(unit)...
-- based on checks for units hidden in ambush, and includes tame animals")
-- is why: it catches a player's own tame war dog and a player's own
-- ambushing squad member that isOwnCiv might not reliably flag, neither of
-- which should ever appear as a "threat". NOT independently live-tested
-- against a real tame pet on the map this session -- flagged below.
--
-- Sneaking/ambush visibility: dfhack.units.isHidden(unit) ("hidden to the
-- player, accounting for sneaking... works for any game mode") is read and
-- reported as an informational field, not a filter. DFHack's unit list
-- (df.global.world.units.active) is a direct memory read, unlike the
-- announcement/UI layer INVASION depends on -- the same reveal-plugin-style
-- visibility gap this project has relied on elsewhere. This is *why* this
-- tool can plausibly see an ambusher or sneaking creature the moment it's on
-- the map, structurally addressing the exact blind spot named in the task.
-- NOT independently live-tested against a real ambush this session --
-- flagged below.
--
-- Design commitment #1: never a raw coordinate. Every result carries
-- near_landmark/direction/distance_tiles (via nearest_landmark, reqscript'd)
-- exactly like every other deployed perception tool -- never x/y/z.
--
-- Usage: ./dfhack-run df-overseer-threat scan [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 15

local function walkable_group(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group or 0
end

-- The set of walkable groups any living citizen currently occupies. Usually
-- one id, but a stranded/split fort (df-overseer-connectivity.lua's own
-- concern) can have more than one -- every group any citizen is standing in
-- counts, since a threat reaching ANY of them is real, not just the main one.
local function citizen_groups()
  local groups = {}
  for _, unit in ipairs(dfhack.units.getCitizens()) do
    local x, y, z = dfhack.units.getPosition(unit)
    if x then
      local g = walkable_group(x, y, z)
      if g ~= 0 then
        groups[g] = true
      end
    end
  end
  return groups
end

local function race_name(unit)
  local ok, name = pcall(dfhack.units.getRaceName, unit)
  return ok and name or "unknown"
end

-- Server-side only, same fallback discipline as df-overseer-labor.lua's
-- describe_position: a landmark-resolution failure degrades to "unknown"
-- rather than crashing the whole scan.
local function describe_position(x, y, z)
  if not x then
    return nil
  end
  local ok, info = pcall(landmarks_mod.nearest_landmark, x, y, z)
  return ok and info or nil
end

-- Every flag this project has already found unreliable (decisions/
-- DECISIONS.md 2026-09-11/12), read and reported, never filtered on.
-- Explicitly labeled HEURISTIC per docs/AGENT-ARCHITECTURE.md §10's
-- MECHANICAL/DERIVED/HEURISTIC vocabulary -- this is the first tool in this
-- repo to apply that tagging inline in its own output, not just in
-- TOOLS.yaml metadata, because the whole point of this file is that the
-- flags must visibly NOT be the reason a candidate is here.
local function danger_flags(unit)
  local function safe(fn)
    local ok, v = pcall(fn, unit)
    return ok and v or false
  end
  return {
    is_danger = safe(dfhack.units.isDanger),
    is_invader = safe(dfhack.units.isInvader),
    is_agitated = safe(dfhack.units.isAgitated),
    is_great_danger = safe(dfhack.units.isGreatDanger),
    reliability = "HEURISTIC",
  }
end

-- Exported for other df-overseer-*.lua scripts via reqscript, matching the
-- module-export convention every other file in this set uses.
function find_threats(radius_tiles)
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)
  local groups = citizen_groups()

  local candidates = {}
  for _, unit in ipairs(df.global.world.units.active) do
    local ok_dead, dead = pcall(dfhack.units.isDead, unit)
    local ok_own, own = pcall(dfhack.units.isOwnCiv, unit)
    local ok_fc, fort_controlled = pcall(dfhack.units.isFortControlled, unit)
    local excluded = (ok_dead and dead)
      or (ok_own and own)
      or (ok_fc and fort_controlled)

    if not excluded then
      local x, y, z = dfhack.units.getPosition(unit)
      if x then
        local group = walkable_group(x, y, z)
        local shares_group = group ~= 0 and groups[group] == true

        local near = describe_position(x, y, z)
        local within_radius = near ~= nil and near.distance_tiles <= radius

        if shares_group or within_radius then
          local ok_hidden, hidden = pcall(dfhack.units.isHidden, unit)
          local flags = danger_flags(unit)

          local why = {}
          if shares_group then
            table.insert(why, "shares_walkable_group_with_citizens")
          end
          if within_radius then
            table.insert(why, string.format(
              "within_%d_tiles_of_%s", radius, near.name))
          end
          if flags.is_great_danger then table.insert(why, "flagged_isGreatDanger (HEURISTIC)") end
          if flags.is_invader then table.insert(why, "flagged_isInvader (HEURISTIC)") end
          if flags.is_danger then table.insert(why, "flagged_isDanger (HEURISTIC)") end
          if flags.is_agitated then table.insert(why, "flagged_isAgitated (HEURISTIC)") end
          if ok_hidden and hidden then table.insert(why, "unit_is_hidden_or_sneaking") end

          -- Ranking score: reachability dominates (it's the filter, so it
          -- should also dominate the order), flags are a real but secondary
          -- tiebreak, distance is the final tiebreak. Deliberately NOT
          -- tuned against a live fort -- see handoff.
          local score = 0
          if shares_group then score = score + 1000 end
          if within_radius then score = score + 500 end
          if flags.is_great_danger then score = score + 50
          elseif flags.is_invader then score = score + 40
          elseif flags.is_danger then score = score + 30
          elseif flags.is_agitated then score = score + 20 end
          score = score - (near and near.distance_tiles or radius) * 0.1

          table.insert(candidates, {
            unit_id = unit.id,
            race = race_name(unit),
            near_landmark = near and near.name or nil,
            direction = near and near.direction or nil,
            distance_tiles = near and near.distance_tiles or nil,
            reachable = {
              shares_walkable_group_with_citizens = shares_group,
              within_bounded_distance_of_landmark = within_radius,
              reliability = "MECHANICAL",
            },
            flags = flags,
            hidden = ok_hidden and hidden or false,
            why = why,
            _score = score,
          })
        end
      end
    end
  end

  table.sort(candidates, function(a, b) return a._score > b._score end)

  local results = {}
  for i, c in ipairs(candidates) do
    if i > MAX_RESULTS then break end
    c._score = nil
    c.rank = i
    table.insert(results, c)
  end
  return results
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "scan" then
  local radius = tonumber(args[2])
  print(json.encode(find_threats(radius)))
else
  print("usage: df-overseer-threat scan [RADIUS_TILES]")
end
