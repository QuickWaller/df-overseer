-- df-overseer-openarea.lua
--@module = true
--
-- docs/PURPOSE.md build order item 6: find_open_area, terrain="built",
-- hard radius cap from day one (research/2026-08-25-spatial-perception.md
-- §5.3). This is terrain="built" only -- the maximal-rectangle-style scan
-- over gridded/constructed space. terrain="cavern" (build order item 9,
-- deliberately last) needs a genuinely different algorithm (a distance-
-- transform/clustering split of an irregular walkable region, not a
-- rectangle scan) and is NOT attempted here.
--
-- Scoped, never whole-map, per design commitment #1 and the research
-- doc's own caution (BWTA's history: a mature, purpose-built terrain
-- analysis algorithm was slow enough on StarCraft-sized maps to justify a
-- 10x-faster sequel -- don't assume any region scan is free by default).
-- `near` (a landmark name, required -- resolved via
-- df-overseer-landmarks.lua's get_landmark_centroid, reqscript'd) anchors
-- the search box; `radius_tiles` is clamped to a hard cap (60) in code,
-- not just documented as a recommendation, matching the research doc's
-- explicit instruction to enforce this at the tool-schema level.
--
-- A tile is "free" if it's walkable (dfhack.maps.getWalkableGroup ~= 0,
-- confirmed live: 0 on a solid wall, a real group id like 11 on open
-- floor) and carries no building (dfhack.buildings.findAtTile, confirmed
-- live: nil on open floor, a real building pointer on a stockpile tile).
-- Per the documented caveat on getWalkableGroup (Lua API.txt, repeated in
-- research/2026-08-25-spatial-perception.md §3.2): this cache only
-- updates while the game is unpaused. Not a live risk today (DF does not
-- simulate at all while paused, so nothing can go stale mid-query), but
-- worth remembering for a future consumer that calls this immediately
-- after an unpause.
--
-- Candidate search: for this first slice, a plain O(box_area * w * h)
-- window check, not the classic histogram/stack "largest rectangle"
-- algorithm the research doc's own §5.3 sketch describes -- deliberately
-- simpler to write and verify correctly, and cheap enough at the capped
-- box size (up to 121x121 tiles) for the small room dimensions this
-- project actually designs with (2x2 embarks, 5x5 starter rooms). Revisit
-- if profiling ever shows this matters at a larger scale.
--
-- Each returned candidate's near_landmark/direction/distance_tiles
-- describes the candidate's OWN nearest landmark (via nearest_landmark,
-- reqscript'd), which is usually but not necessarily the same landmark
-- used to scope the search box -- e.g. a large open area's center could
-- end up closer to a different landmark than the one it was searched
-- "near".
--
-- `build` subcommand (added 2026-09-11, closing the gap decisions/DECISIONS.md
-- 2026-09-11's "First real autonomous-play experiment on Uniboslan" found
-- live): find_open_area's ranked candidates were real and correctly judged
-- by a model, but nothing converted a CHOSEN candidate into something
-- `quickfort run -c x,y,z` can actually anchor to -- every perception tool,
-- this one included, deliberately strips coordinates before returning
-- (design commitment #1). `build_open_area` fuses resolution and action
-- into one atomic call rather than adding a `resolve_candidate`-style query
-- that would hand a live coordinate back to whatever called it (the model,
-- in this project's architecture) for no benefit -- nothing else in this
-- toolkit needs a coordinate for any purpose other than this exact
-- quickfort call. It re-runs the SAME ranking `find_open_area` uses
-- (`ranked_candidates`, extracted below so the two literally cannot drift
-- apart on which candidate is "rank 1"), resolves the chosen candidate's
-- real cx,cy internally, and runs `quickfort run BLUEPRINT_FILE -c cx,cy,z`
-- directly. The real coordinate exists only inside `build_open_area`'s own
-- local scope, for the instant it takes to build the quickfort command's
-- argument list -- never assigned into, printed, or returned in anything
-- this function hands back. quickfort's own console output is captured via
-- `dfhack.run_command_silent` and never forwarded verbatim: besides the
-- general principle, `hack/scripts/internal/quickfort/dig.lua` prints
-- "removing existing job at X, Y, Z" verbatim when re-designating an
-- already-job'd tile, which would leak a real coordinate through this
-- tool's own JSON if raw text were ever returned wholesale. Only the
-- "  <label>: <N>" statistics lines quickfort itself prints (see
-- `finish_commands` in `hack/scripts/internal/quickfort/command.lua`,
-- "Blueprint statistics:" followed by lines like
-- "  Tiles designated for digging: 25") are parsed out, by label name, into
-- a plain label->count table -- never free-text, so nothing coordinate-
-- shaped can ever ride along even if some other quickfort mode's stdout
-- format changes later. See `df-overseer-landmarks.lua`'s `build_at_landmark`
-- for the parallel primitive when the target is a named landmark directly,
-- not a ranked open-area search.
--
-- Z defaults to NEAR_LANDMARK's own z (found live 2026-09-11, a Haiku-driven
-- run: ranked_candidates already resolves the landmark's real az internally
-- via get_landmark_centroid and was discarding it in favor of this argument,
-- forcing every caller to supply a bare level number with no coordinate-free
-- way to learn the right one -- the model-facing failure mode this produced
-- was worse than "can't find a value," it was "guess 0, get a real but
-- unrelated walkable_group back, and silently no-op a build there." Pass an
-- explicit Z only to search a different level than the landmark's own.
--
-- Usage: ./dfhack-run df-overseer-openarea find W H [Z] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-openarea build W H [Z] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

local function is_free(x, y, z)
  local pos = xyz2pos(x, y, z)
  local ok_walk, group = pcall(dfhack.maps.getWalkableGroup, pos)
  if not ok_walk or group == 0 then
    return false
  end
  local ok_bld, bld = pcall(dfhack.buildings.findAtTile, pos)
  return ok_bld and not bld
end

-- Every top-left position where a w-by-h window is entirely free tiles,
-- within the given box at the given z.
local function find_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local free = {}
  for x = min_x, max_x do
    free[x] = {}
    for y = min_y, max_y do
      free[x][y] = is_free(x, y, z)
    end
  end

  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      local fits = true
      for dx = 0, w - 1 do
        if not fits then break end
        for dy = 0, h - 1 do
          if not free[x + dx][y + dy] then
            fits = false
            break
          end
        end
      end
      if fits then
        table.insert(candidates, {x = x, y = y})
      end
    end
  end
  return candidates
end

-- Two candidate windows (both w-by-h, top-left at a.x,a.y / b.x,b.y).
local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- Server-side only: ranked, deduplicated, non-overlapping top-left corners
-- (real x,y coordinates, never stripped here) for a WxH window near `near`,
-- closest-to-anchor first. Shared by find_open_area (which strips
-- coordinates before returning to any caller) and build_open_area (which
-- needs the real coordinate to anchor quickfort) -- one ranking
-- implementation, so "candidate rank 1" can never mean two different tiles
-- depending which entry point asked.
local function ranked_candidates(w, h, z, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  -- Default to the landmark's own level rather than requiring the caller
  -- to supply one -- see the file header for why this matters.
  z = z or az
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local candidates = find_candidates(
    w, h, z, ax - radius, ax + radius, ay - radius, ay + radius)

  for _, c in ipairs(candidates) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(candidates, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  -- Greedily keep only non-overlapping candidates, closest-to-anchor
  -- first, so results aren't N near-duplicate placements one tile apart.
  local chosen = {}
  for _, c in ipairs(candidates) do
    local ok = true
    for _, existing in ipairs(chosen) do
      if overlaps(c, existing, w, h) then
        ok = false
        break
      end
    end
    if ok then
      table.insert(chosen, c)
      if #chosen >= MAX_RESULTS then
        break
      end
    end
  end
  return chosen, nil, z
end

function find_open_area(w, h, z, near, radius_tiles)
  local chosen, err, resolved_z = ranked_candidates(w, h, z, near, radius_tiles)
  if err then
    return nil, err
  end
  z = resolved_z

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = c.x + math.floor((w - 1) / 2)
    local cy = c.y + math.floor((h - 1) / 2)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local ok_group, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(cx, cy, z))
    local info = ok_near and near_info
    table.insert(results, {
      dims = {w, h},
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      walkable_group = ok_group and group or -1,
    })
  end
  return results
end

-- Parses quickfort's own "Blueprint statistics:" block (see
-- hack/scripts/internal/quickfort/command.lua's finish_commands) into a
-- plain label->count table. Deliberately line-anchored ("two leading
-- spaces, label, colon, digits, nothing else") so it can never accidentally
-- pick up a coordinate-bearing line like dig.lua's own
-- "removing existing job at X, Y, Z" -- that line has no trailing
-- ": <digits>" and isn't indented the same way, so it never matches.
local function parse_quickfort_stats(output)
  local stats = {}
  if not output then
    return stats
  end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then
      stats[label] = tonumber(value)
    end
  end
  return stats
end

-- See the header comment above for the full design rationale. Picks
-- candidate `rank` (default 1) from the exact same ranking find_open_area
-- uses, resolves its real center coordinate, and runs
-- `quickfort run BLUEPRINT_FILE -c cx,cy,z` directly against it. The real
-- coordinate lives only in this function's own local scope -- it is never
-- assigned into, printed, or returned in anything handed back to the
-- caller. Note on `blueprint_file`: quickfort resolves a bare filename
-- relative to dfhack-config/blueprints/, not the working directory or an
-- absolute path (Working.md's own documented trap) -- pass a bare filename
-- for a blueprint already deployed there.
function build_open_area(w, h, z, near, blueprint_file, rank, radius_tiles)
  rank = rank or 1
  local chosen, err, resolved_z = ranked_candidates(w, h, z, near, radius_tiles)
  if err then
    return nil, err
  end
  z = resolved_z
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end

  local c = chosen[rank]
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)

  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local ok_group, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(cx, cy, z))
  local info = ok_near and near_info

  -- The one place a real coordinate exists in this file: assembled
  -- directly into quickfort's own argument list, never stored anywhere
  -- else and never returned. run_command_silent runs with the core
  -- suspended and hands back (output, command_result) rather than
  -- printing to the console -- confirmed against hack/docs/docs/dev/Lua
  -- API.txt, not assumed.
  --
  -- BUG FOUND LIVE 2026-09-11 (in df-overseer-diggable.lua's parallel
  -- dig_diggable_area, same code shape -- FIXED HERE TOO, not just there):
  -- this used to pass cx,cy (the box's computed CENTER) as quickfort's -c
  -- argument. quickfort's own docs (hack/docs/docs/tools/quickfort.txt:
  -- "the blueprint start position... is the upper left corner by default")
  -- say -c anchors the blueprint's TOP-LEFT, not its center -- so every
  -- build_open_area call has actually been placing blueprints shifted by
  -- (floor((w-1)/2), floor((h-1)/2)) tiles from the box ranked_candidates
  -- validated as free. Stockpile #2 (decisions/DECISIONS.md 2026-09-11)
  -- still worked because find_open_area's candidates sit inside a broadly
  -- open, already-walkable region, so the shift likely still landed on
  -- free tiles -- lucky, not correct, and NOT guaranteed for a tighter
  -- candidate near map edges or other buildings. `c.x,c.y` (the true,
  -- validated top-left) is the correct argument; cx,cy stays right for
  -- nearest_landmark/getWalkableGroup's reporting above, where "center" is
  -- the right choice -- only the quickfort call itself was wrong.
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', blueprint_file, '-c',
    string.format('%d,%d,%d', c.x, c.y, z))

  return {
    rank = rank,
    dims = {w, h},
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    walkable_group = ok_group and group or -1,
    blueprint = blueprint_file,
    quickfort_ok = ok_run and result == CR_OK,
    quickfort_error = (not ok_run) and tostring(output) or nil,
    quickfort_stats = ok_run and parse_quickfort_stats(output) or nil,
  }
end

-- Same module-load guard as the other df-overseer-*.lua scripts.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

-- Z is optional in both subcommands (see file header): args[4] is read as Z
-- only when it parses as a number, otherwise it's NEAR_LANDMARK and every
-- argument after it shifts left by one, with z left nil so ranked_candidates
-- defaults it to the landmark's own level.
if cmd == "find" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local z, near, radius
  if tonumber(args[4]) then
    z, near, radius = tonumber(args[4]), args[5], tonumber(args[6])
  else
    near, radius = args[4], tonumber(args[5])
  end
  if not (w and h and near) then
    print("usage: df-overseer-openarea find W H [Z] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_open_area(w, h, z, near, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "build" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local z, near, blueprint, rank, radius
  if tonumber(args[4]) then
    z, near, blueprint, rank, radius =
      tonumber(args[4]), args[5], args[6], tonumber(args[7]), tonumber(args[8])
  else
    near, blueprint, rank, radius =
      args[4], args[5], tonumber(args[6]), tonumber(args[7])
  end
  if not (w and h and near and blueprint) then
    print("usage: df-overseer-openarea build W H [Z] NEAR_LANDMARK"
      .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES]")
  else
    local result, err = build_open_area(w, h, z, near, blueprint, rank, radius)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-openarea find W H [Z] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-openarea build W H [Z] NEAR_LANDMARK"
    .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES]")
end
