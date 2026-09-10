-- df-overseer-landmarks.lua
--
-- docs/PURPOSE.md build order item 3: the real landmark system on burrows +
-- buildings, exits-first representation (research/2026-08-25-spatial-perception.md
-- §5/§10). Extends the seed-landmark-only first slice (decisions/DECISIONS.md
-- 2026-09-10, "Add an experimental seed landmark") with live burrow/building
-- enumeration and a nearest-neighbor adjacency graph, verified against a real
-- fort (Uniboslan) this session. Still EXPERIMENTAL -- lives on
-- perception-layer-experiments, not main.
--
-- Design commitment #1 (docs/PURPOSE.md): the model is never shown a map.
-- This script never reads raw tile/MapBlock geometry (no RemoteFortressReader,
-- no GetBlockList) -- every landmark is a pre-aggregated fact (name, kind,
-- a handful of named exits with direction+distance), computed here in code,
-- and centroids never leave this file's server-side tables.
--
-- Landmarks come from three sources, merged into one list every call:
--   1. The persisted seed ("Embark Site", the citizen-position centroid from
--      the first slice) -- kept for continuity even once real landmarks
--      exist, since it's still the only anchor on a day-one embark with no
--      buildings or burrows yet.
--   2. df.global.world.buildings.all, filtered to buildings with a non-empty
--      dfhack.buildings.getName() (unnamed/internal buildings would otherwise
--      flood the list with noise). Confirmed live 2026-09-10 against
--      Uniboslan: a plain quickfort-placed stockpile gets a real default
--      name ("Stockpile #1"), and the embark wagon is itself a `building`
--      (building_type "Wagon") -- this fixes a wrong assumption from the
--      seed-landmark session, which checked world.vehicles.all (empty for
--      this embark) and concluded no wagon object existed at all.
--   3. df.global.plotinfo.burrows.list -- NOT df.global.world.burrows.all,
--      which does not exist as a field (confirmed live: "Cannot read field
--      world.burrows: not found"). This corrects
--      research/2026-08-25-spatial-perception.md §10's prototype sketch,
--      which guessed world.burrows.all and flagged it explicitly as
--      unverified. dfhack.burrows.getName() never returns an empty string
--      (falls back to DF's own UI placeholder name per Lua API.txt), so no
--      filtering is needed here the way buildings need it.
--
-- Centroid computation, both verified live and both real bugs the prior
-- session's design would have hit if used verbatim:
--   - Buildings: dfhack.buildings.getSize(building) returns (w, h, cx, cy)
--     where cx/cy are LOCAL to the building's own bounding box (a 3x3 wagon
--     returned cx=1,cy=1; a 5x5 stockpile returned cx=2,cy=2) -- NOT absolute
--     map coordinates, despite research/2026-08-25-spatial-perception.md
--     §10's prototype sketch treating them as if they were (it would have
--     collapsed every building's centroid onto roughly the same nonsense
--     point). Absolute centroid is (b.x1+b.x2)/2, (b.y1+b.y2)/2, b.z instead
--     -- confirmed live against the same two buildings.
--   - Burrows: dfhack.burrows.listBlocks(burrow) returns map_block pointers,
--     each carrying an absolute tile-space top-left corner at
--     block.map_pos.{x,y,z} (confirmed live via dfhack.maps.getTileBlock),
--     not a block-index pair needing a *16 conversion. Centroid is the mean
--     of each block's map_pos plus an 8-tile offset to hit the block's own
--     center, across every block in the burrow.
--
-- Exits: nearest-N by geometric distance (as
-- research/2026-08-25-spatial-perception.md §10 sketches), each ALSO tagged
-- with a live-verified `walkable` bool from dfhack.maps.canWalkBetween on the
-- two centroid tiles -- the fix the research doc's own honest caveat asked
-- for ("a landmark on the other side of a wall could show up as a close
-- 'exit' it isn't actually possible to use"). A centroid tile is not
-- guaranteed walkable itself (an irregular burrow's mean point can land
-- outside it entirely), so canWalkBetween is called under pcall and a
-- failure is reported as walkable=false, never as a crash.
--
-- Usage: ./dfhack-run df-overseer-landmarks <list|get NAME>

local json = require('json')

local GLOBAL_KEY = 'df-overseer-landmarks_v1'
local MAX_EXITS_PER_LANDMARK = 3

local COMPASS = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}

local function direction_and_distance(from, to)
  local dx, dy = to.x - from.x, to.y - from.y
  local dist = math.floor(math.sqrt(dx * dx + dy * dy) + 0.5)
  local angle = math.atan(dy, dx)
  local idx = math.floor(((angle + math.pi) / (2 * math.pi)) * 8 + 0.5) % 8 + 1
  return COMPASS[idx], dist
end

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

-- Live-enumerated, never persisted -- buildings are already persisted by DF
-- itself, and re-deriving them fresh every call means a deconstructed
-- building silently drops out instead of leaving a stale landmark behind.
local function enumerate_buildings()
  local out = {}
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok, name = pcall(dfhack.buildings.getName, bld)
    if ok and name and name ~= '' then
      local ok_type, kind = pcall(function() return df.building_type[bld:getType()] end)
      table.insert(out, {
        name = name,
        kind = ok_type and kind or 'unknown',
        x = math.floor((bld.x1 + bld.x2) / 2 + 0.5),
        y = math.floor((bld.y1 + bld.y2) / 2 + 0.5),
        z = bld.z,
      })
    end
  end
  return out
end

local function enumerate_burrows()
  local out = {}
  for _, br in ipairs(df.global.plotinfo.burrows.list) do
    local ok_blocks, blocks = pcall(dfhack.burrows.listBlocks, br)
    if ok_blocks and blocks and #blocks > 0 then
      local sx, sy, sz = 0, 0, 0
      for _, blk in ipairs(blocks) do
        sx, sy, sz = sx + blk.map_pos.x, sy + blk.map_pos.y, sz + blk.map_pos.z
      end
      local n = #blocks
      table.insert(out, {
        name = dfhack.burrows.getName(br),
        kind = 'burrow',
        x = math.floor(sx / n + 8.5),
        y = math.floor(sy / n + 8.5),
        z = math.floor(sz / n + 0.5),
      })
    end
  end
  return out
end

-- Mutates `landmarks` in place, adding an `exits` field to each and
-- stripping the (server-side-only, per design commitment #1) x/y/z fields
-- before the caller serializes the result.
local function build_exits_and_strip_coords(landmarks, max_edges)
  for _, a in ipairs(landmarks) do
    local candidates = {}
    for _, b in ipairs(landmarks) do
      if a ~= b and a.name ~= b.name then
        local dir, dist = direction_and_distance(a, b)
        local ok_walk, walkable = pcall(
          dfhack.maps.canWalkBetween, xyz2pos(a.x, a.y, a.z), xyz2pos(b.x, b.y, b.z))
        table.insert(candidates, {
          to = b.name,
          direction = dir,
          distance_tiles = dist,
          walkable = ok_walk and walkable or false,
        })
      end
    end
    table.sort(candidates, function(x, y) return x.distance_tiles < y.distance_tiles end)
    a.exits = {}
    for i = 1, math.min(max_edges, #candidates) do
      table.insert(a.exits, candidates[i])
    end
  end
  for _, lm in ipairs(landmarks) do
    lm.x, lm.y, lm.z = nil, nil, nil
  end
end

-- Returns the full landmark table (seed + live buildings + live burrows,
-- each with a computed `exits` list) and an optional error string. Two
-- return values (not one) so a failure is distinguishable from a genuinely
-- empty landmark set -- callers must not splat this directly into
-- json.encode (see the seed-slice's original bug, decisions/DECISIONS.md
-- 2026-09-10).
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

  local landmarks = {}
  for _, lm in ipairs(state.landmarks) do
    table.insert(landmarks, {name = lm.name, kind = lm.kind, x = lm.x, y = lm.y, z = lm.z})
  end
  for _, lm in ipairs(enumerate_buildings()) do
    table.insert(landmarks, lm)
  end
  for _, lm in ipairs(enumerate_burrows()) do
    table.insert(landmarks, lm)
  end

  build_exits_and_strip_coords(landmarks, MAX_EXITS_PER_LANDMARK)
  return landmarks
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
