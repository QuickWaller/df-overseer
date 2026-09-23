-- df-overseer-reachability.lua
--@module = true
--
-- handoffs/2026-09-23-landmark-reachability.md: the single, shared "can a
-- dwarf get from A to B" primitive, replacing the per-file centroid-vs-
-- centroid `dfhack.maps.canWalkBetween` calls that df-overseer-landmarks.lua,
-- df-overseer-connectivity.lua and df-overseer-threat.lua each used to make
-- independently. Built because a live read (orchestrating session,
-- 2026-09-23) found the fort's own Well reading `walkable: false` to every
-- neighbour: the Well's centre tile is a RampTop, which nobody can stand on,
-- so EVERY comparison anchored on that exact tile fails -- not because the
-- Well is unreachable (four of its eight neighbour tiles can walk to the
-- Still, so it plainly isn't), but because the centroid picked to represent
-- it is the wrong tile to ask the question about. Every landmark whose
-- centre tile is not standable (anything over a channel, a stair, a ramp, a
-- bridge) was at risk of the same false negative.
--
-- A SECOND, independent reason this needed fixing, not just the centroid
-- choice: `research/2026-09-17-pool-reachability.md` (live-verified against
-- this exact install, DFHack 53.16-r1.1) found `dfhack.maps.getWalkableGroup`
-- itself reads **0** ("not walkable") for RAMP and RAMP_TOP shaped tiles in
-- this build **regardless of true walkability** -- 74 of 98 RAMP/RAMP_TOP
-- tiles tested were directly, physically 4-adjacent to a tile in the fort's
-- own main walkable group, yet themselves read group 0. That report's own
-- conclusion: "it is the cache artifact, confirmed by direct physical-
-- adjacency contradiction, not a real terrain gap." So a tile reading group
-- 0 is not, by itself, proof of "not standable" when its own shape is RAMP
-- or RAMP_TOP -- it may just be this build's known blind spot. Every other
-- shape's group-0 reading is taken at face value; no comparable live
-- evidence questions it for FLOOR/WALL/STAIR/etc.
--
-- NOT INSTALL-CONFIRMED THIS SESSION (offline stream, no VM access, no live
-- DFHack call -- handoffs/2026-09-23-landmark-reachability.md's own hard
-- line). Nothing here calls a new accessor: `dfhack.maps.canWalkBetween`,
-- `dfhack.maps.getWalkableGroup`, `dfhack.maps.getTileType` and
-- `df.tiletype.attrs[t].shape` are each already live-verified call sites in
-- this repo (df-overseer-connectivity.lua/openarea.lua/diggable.lua/
-- chokepoints.lua/threat.lua for the first two; df-overseer-well.lua/
-- farm.lua/diggable.lua for the second two), and `df.tiletype_shape.RAMP`/
-- `.RAMP_TOP` are exactly the enum members `research/2026-09-17-pool-
-- reachability.md`'s own live probe classified tiles with. This file only
-- reorganises already-verified primitives into one place; it does not claim
-- any of them freshly confirmed against the install this session.
--
-- THE FIX, in one sentence: never trust a single tile's own reading:
-- resolve each side of a reachability question to a real standable tile
-- (the position itself if it already reads a nonzero group, else its
-- immediate 8-neighbour ring, else give up honestly), then compare the two
-- resolved groups -- and always keep "could not resolve either side" as its
-- own outcome, distinct from "resolved and definitely different groups".
--
-- Three states everywhere this module answers a reachability question,
-- never two: "reachable", "unreachable", "unknown" (with a reason). A
-- two-state boolean cannot express "the tool doesn't know" -- collapsing
-- "unknown" into "unreachable" is exactly the false-negative bug this file
-- exists to fix, so nothing in this module ever does that collapse.
--
-- RING SIZE IS DELIBERATELY SHALLOW (8 neighbours, one tile out, not a
-- flood-fill or a pathfind): the handoff's own instruction is "falling back
-- to the tiles immediately around it (which is how a well, a stair or a
-- bridge is really used)". A single ring covers exactly the regression case
-- this file was built for (the Well's own centre tile plus its 8
-- neighbours) without risking a false "adjacent" claim against some other,
-- unrelated tile several tiles away that happens to resolve first.
--
-- Module exports (via reqscript('df-overseer-reachability'), same pattern
-- every df-overseer-*.lua file uses):
--   resolve_group(x, y, z) -> {group, how, blind_spot} | nil, reason
--     Server-side only -- takes a raw tile position, returns a walkable
--     group id and how it was resolved ("at" the position itself, or
--     "adjacent" via the 8-neighbour ring), never a coordinate. nil, reason
--     means neither the position nor any of its 8 neighbours resolved to a
--     standable tile -- genuinely "unknown", not "unreachable".
--   reachable_between(ax, ay, az, bx, by, bz) -> {status, reason?, from_via?,
--       to_via?, from_group?, to_group?}
--     status is "reachable" | "unreachable" | "unknown". Never returns a
--     coordinate. Used by df-overseer-landmarks.lua's build_exits and
--     df-overseer-connectivity.lua's check_reachable/check_reachable_units.
--   group_matches(x, y, z, target_groups) -> matched(bool), how, group
--     For df-overseer-threat.lua: does THIS exact position (a unit's real
--     standing tile, which cannot be substituted for a neighbour's) belong
--     to, or sit immediately beside, one of a set of target walkable
--     groups. Same resolve_group primitive underneath, reshaped for the
--     "one tile against a set of groups" question threat.lua asks instead
--     of "two tiles against each other".
--
-- Usage: this file is a library only (dfhack_flags.module guard below with
-- no CLI branch) -- every command stays on the tool that already owned it,
-- per the handoff's "one shared helper" instruction, not a new CLI surface.

local RING_RADIUS = 1

-- The 8 orthogonal+diagonal offsets at radius 1, same neighbourhood the
-- live orchestrating read used to establish the Well's own regression case
-- ("all eight tiles around the Well", "four... can walk to the Still").
local RING_OFFSETS = {
  {dx = 0, dy = -1}, {dx = 1, dy = -1}, {dx = 1, dy = 0}, {dx = 1, dy = 1},
  {dx = 0, dy = 1}, {dx = -1, dy = 1}, {dx = -1, dy = 0}, {dx = -1, dy = -1},
}

local function tile_shape(x, y, z)
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return nil
  end
  local ok_shape, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  return ok_shape and shape or nil
end

local function walkable_group(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group or 0
end

-- A RAMP/RAMP_TOP tile reading group 0 is this build's own known blind spot
-- (research/2026-09-17-pool-reachability.md, see header) -- not reliable
-- evidence the tile is actually unstandable. Every other shape's group-0
-- reading has no comparable live evidence against it and is taken at face
-- value.
local function is_blind_spot_shape(shape)
  return shape == df.tiletype_shape.RAMP or shape == df.tiletype_shape.RAMP_TOP
end

-- One tile's classification: its own walkable group, whether that group
-- alone counts as standable, and whether a 0 reading here is the known
-- blind spot rather than a trustworthy "not standable".
local function probe(x, y, z)
  local group = walkable_group(x, y, z)
  local shape = tile_shape(x, y, z)
  return {
    group = group,
    standable = group ~= 0,
    blind_spot = group == 0 and shape ~= nil and is_blind_spot_shape(shape),
  }
end

-- Exported. Server-side only: takes a raw tile position, never returns one.
-- Tries the position itself first; if it doesn't resolve to a standable
-- tile, tries its 8-neighbour ring (RING_RADIUS); if nothing in that
-- neighbourhood resolves either, returns nil plus an honest reason.
function resolve_group(x, y, z)
  local center = probe(x, y, z)
  if center.standable then
    return {group = center.group, how = "at", blind_spot = false}
  end

  for _, off in ipairs(RING_OFFSETS) do
    local p = probe(x + off.dx, y + off.dy, z)
    if p.standable then
      return {group = p.group, how = "adjacent", blind_spot = false}
    end
  end

  if center.blind_spot then
    return nil, string.format(
      "own tile reads walkable group 0 on a RAMP/RAMP_TOP shape, this "
        .. "build's own known blind spot (research/2026-09-17-pool-"
        .. "reachability.md); no standable tile found within %d tile(s)",
      RING_RADIUS)
  end
  return nil, string.format(
    "no standable tile found at the position or within %d tile(s) of it",
    RING_RADIUS)
end

-- Exported. Two positions in, a tri-state reachability verdict out. Never a
-- coordinate anywhere in the result.
function reachable_between(ax, ay, az, bx, by, bz)
  local a, a_err = resolve_group(ax, ay, az)
  local b, b_err = resolve_group(bx, by, bz)

  if not a or not b then
    local reasons = {}
    if not a then table.insert(reasons, "from: " .. a_err) end
    if not b then table.insert(reasons, "to: " .. b_err) end
    return {status = "unknown", reason = table.concat(reasons, "; ")}
  end

  if a.group == b.group then
    return {status = "reachable", from_via = a.how, to_via = b.how,
            from_group = a.group, to_group = b.group}
  end
  return {status = "unreachable", from_via = a.how, to_via = b.how,
          from_group = a.group, to_group = b.group}
end

-- Exported. For df-overseer-threat.lua: does the exact tile (x,y,z) belong
-- to, or sit immediately beside, one of `target_groups` (a set, {[group_id]
-- = true, ...})? Unlike reachable_between, this never substitutes a
-- neighbour tile for (x,y,z) itself in the result -- a hostile unit's own
-- position cannot be moved to make the check pass, so `how = "adjacent"`
-- here means "not standing in the target network itself, but the tile it
-- occupies touches a tile that is", the same physically-adjacent-to-group-11
-- contradiction research/2026-09-17-pool-reachability.md's own live probe
-- used to prove the blind spot exists in the first place.
function group_matches(x, y, z, target_groups)
  local center = probe(x, y, z)
  if center.standable and target_groups[center.group] then
    return true, "at", center.group
  end

  for _, off in ipairs(RING_OFFSETS) do
    local p = probe(x + off.dx, y + off.dy, z)
    if p.standable and target_groups[p.group] then
      return true, "adjacent", p.group
    end
  end

  return false, nil, center.group
end

-- Library-only: no CLI branch. Loading this file (reqscript, from another
-- df-overseer-*.lua script) is side-effect-free, same guard every other
-- file in this set uses.
if dfhack_flags.module then
  return
end

print("df-overseer-reachability is a library module, not a CLI tool -- reqscript it from another df-overseer-*.lua script.")
