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
--      citizen's tile resolve to the same nonzero walkable group, via
--      df-overseer-reachability.lua's shared group_matches/resolve_group
--      (reqscript'd, FIXED 2026-09-23, handoffs/2026-09-23-landmark-
--      reachability.md -- see citizen_groups()'s and the scan loop's own
--      inline notes below for exactly what changed and why: a RAMP/
--      RAMP_TOP tile reads walkable group 0 in this build regardless of
--      true walkability, research/2026-09-17-pool-reachability.md, so both
--      a citizen's own tile and a candidate's own tile are now resolved
--      with an immediate-neighbour fallback rather than trusted alone).
--      BLIND SPOT, still open, NOT fixed by the above: getWalkableGroup
--      models GROUND pathing connectivity only (Lua API.txt, quoted in
--      df-overseer-openarea.lua's own comment: "only updated while the game
--      is unpaused"). A flying or swimming creature can sit in open air or
--      deep water with group 0 -- genuinely reachable, invisible to this
--      criterion alone, and the 8-neighbour-ring fallback does not help
--      here (open air/deep water's neighbours are typically also group 0,
--      not a RAMP/RAMP_TOP false negative). NOT independently verified this
--      session (no live flying-creature case observed) -- flagged as an
--      open question below.
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
-- KNOWLEDGE-SCOPE FIX, 2026-09-16 (handoffs/2026-09-16-knowledge-scope-audit.md,
-- decisions/DECISIONS.md 2026-09-16 "Agents may only know what a vanilla
-- player could know"; research/2026-09-16-player-visibility.md's bottom
-- line names this file as "the single hardest grey zone" and this exact
-- tension by name). dfhack.units.isHidden(unit) ("hidden to the player,
-- accounting for sneaking... works for any game mode") used to be read and
-- REPORTED as an informational field, never a filter -- and this tool's own
-- stated purpose is catching ambush/sneaking units precisely BECAUSE
-- isHidden says a vanilla player cannot see them. That is a real,
-- structural OMNISCIENCE, not an edge case: reading world.units.active
-- directly bypasses the announcement/UI layer entirely, the same
-- reveal-plugin-style gap this project has otherwise relied on for good
-- reasons. The user's ruling (register, 2026-09-16) is that sneaking
-- ambushers are not allowed, full stop -- so isHidden units are now
-- EXCLUDED from the candidate list outright (added to the same `excluded`
-- check as isDead/isOwnCiv/isFortControlled below), not merely relabeled.
--
-- COVERAGE LOST, stated plainly, per the handoff's own instruction: this
-- tool's whole reason for existing was catching exactly what it now
-- excludes. An ambusher or a sneaking creature standing on a revealed tile,
-- not yet fort-controlled, will no longer appear in `scan`'s results at all
-- until it stops sneaking/steps onto a tile isHidden reads false for (an
-- ambush that reveals itself by attacking, a sneak that gets spotted) or the
-- game's own announcement layer tells the player something happened. The
-- reachable-but-unflagged failure mode this file was built to fix (the kea
-- attack unit-status hostile missed) is UNCHANGED by this fix -- ordinary
-- visible wildlife/hostiles reachable via shares_walkable_group/
-- near_a_landmark are still caught, this only removes the isHidden branch.
--
-- THE VANILLA-LEGAL EQUIVALENT, per the handoff's instruction to check
-- rather than build a new tool here: DF's own announcement layer sometimes
-- tells a player "something happened" without revealing the still-hidden
-- actor. df-overseer-diff.lua's REPORT_CATEGORY already tags exactly this
-- family, confirmed present in this build's live announcement_type enum
-- (research doc §9, live-confirmed ids): "ambush" (ids 53-66, 95, 322),
-- "night_attack" (136-138), "undead_or_ghost" (139, 150), plus the
-- separately-noted CREATURE_STEALS_OBJECT case (seen live in this fort's
-- own announcement log, research doc §9) where a theft is announced without
-- naming the still-hidden thief. `df-overseer-diff.lua since`'s REPORT
-- branch is the correct, already-built, player-visible route to "something
-- is wrong, unspecified" -- not built fresh here, per the handoff's
-- instruction not to build a new announcements tool in this stream.
--
-- Design commitment #1: never a raw coordinate. Every result carries
-- near_landmark/direction/distance_tiles (via nearest_landmark, reqscript'd)
-- exactly like every other deployed perception tool -- never x/y/z.
--
-- Usage: ./dfhack-run df-overseer-threat scan [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local textutil = reqscript('df-overseer-textutil')
local reachability = reqscript('df-overseer-reachability')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 15

-- FIXED 2026-09-23 (handoffs/2026-09-23-landmark-reachability.md): this used
-- to call dfhack.maps.getWalkableGroup directly on each citizen's own tile
-- and silently drop any citizen whose tile read group 0. Per
-- df-overseer-reachability.lua's own header (research/2026-09-17-pool-
-- reachability.md, live-verified against this exact install), a RAMP or
-- RAMP_TOP shaped tile reads group 0 in this build REGARDLESS of true
-- walkability -- so a citizen standing on ordinary ramp terrain (not an
-- edge case: any dwarf climbing between two floors is on a RAMP tile) could
-- be silently excluded from `groups` even though they are plainly part of
-- the fort's own walkable network. Now resolved via the shared
-- resolve_group, which falls back to the citizen's own immediate
-- 8-neighbour ring before giving up -- a citizen physically standing
-- somewhere always has SOME real neighbouring floor, so this should now
-- capture every citizen's true group rather than only the ones whose exact
-- tile happens not to be the blind-spot shape.
--
-- BEHAVIOUR CHANGE, stated plainly per the handoff's own instruction: a
-- fort with any citizen standing on a RAMP/RAMP_TOP tile at scan time will
-- now include that citizen's real group in `groups` where it previously did
-- not. This can only ADD groups to the set (never remove one), so it can
-- only make find_threats MORE permissive (more true reachable candidates
-- recognised via shares_walkable_group_with_citizens), never less --- this
-- fixes the same "reachable but unflagged" failure class the kea-attack
-- miss this file's own header documents, it does not reintroduce it.
local function citizen_groups()
  local groups = {}
  for _, unit in ipairs(dfhack.units.getCitizens()) do
    local x, y, z = dfhack.units.getPosition(unit)
    if x then
      local resolved = reachability.resolve_group(x, y, z)
      if resolved then
        groups[resolved.group] = true
      end
    end
  end
  return groups
end

local function race_name(unit)
  local ok, name = pcall(dfhack.units.getRaceName, unit)
  return ok and textutil.to_utf8(name) or "unknown"
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
    local ok_hidden, hidden = pcall(dfhack.units.isHidden, unit)
    -- KNOWLEDGE-SCOPE FIX, 2026-09-16: isHidden is now an exclusion, not an
    -- informational field -- see header. ok_hidden false (isHidden itself
    -- errored) is treated as hidden, the safe default, never the permissive
    -- one.
    local is_hidden = (not ok_hidden) or hidden
    local excluded = (ok_dead and dead)
      or (ok_own and own)
      or (ok_fc and fort_controlled)
      or is_hidden

    if not excluded then
      local x, y, z = dfhack.units.getPosition(unit)
      if x then
        -- FIXED 2026-09-23: was a bare walkable_group(x,y,z) ~= 0 check on
        -- the candidate's own tile only -- exactly the reading
        -- research/2026-09-17-pool-reachability.md proved unreliable for
        -- RAMP/RAMP_TOP shapes. group_matches also checks the candidate's
        -- immediate 8-neighbour ring before concluding no match, using the
        -- same shared primitive citizen_groups() above now uses. See that
        -- function's own BEHAVIOUR CHANGE note.
        local shares_group, shares_how = reachability.group_matches(x, y, z, groups)

        local near = describe_position(x, y, z)
        local within_radius = near ~= nil and near.distance_tiles <= radius

        if shares_group or within_radius then
          local flags = danger_flags(unit)

          local why = {}
          if shares_group then
            -- shares_how is "at" (own tile is in the citizen network) or
            -- "adjacent" (own tile wasn't, but its immediate 8-neighbour
            -- ring is -- the RAMP/RAMP_TOP blind-spot case this file's
            -- 2026-09-23 fix added).
            table.insert(why, shares_how == "adjacent"
              and "shares_walkable_group_with_citizens (via_adjacent_tile)"
              or "shares_walkable_group_with_citizens")
          end
          if within_radius then
            table.insert(why, string.format(
              "within_%d_tiles_of_%s", radius, near.name))
          end
          if flags.is_great_danger then table.insert(why, "flagged_isGreatDanger (HEURISTIC)") end
          if flags.is_invader then table.insert(why, "flagged_isInvader (HEURISTIC)") end
          if flags.is_danger then table.insert(why, "flagged_isDanger (HEURISTIC)") end
          if flags.is_agitated then table.insert(why, "flagged_isAgitated (HEURISTIC)") end
          -- No "unit_is_hidden_or_sneaking" entry: any such unit is now
          -- excluded above, before reaching this point, per the
          -- KNOWLEDGE-SCOPE FIX -- see header.

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
              shares_walkable_group_via = shares_group and shares_how or nil,
              within_bounded_distance_of_landmark = within_radius,
              reliability = "MECHANICAL",
            },
            flags = flags,
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
