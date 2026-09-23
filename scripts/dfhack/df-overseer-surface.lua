-- df-overseer-surface.lua
--@module = true
--
-- handoffs/2026-09-24-surface-perception.md: the perception layer an audit
-- found missing from the Architect's 39 read grants (research/2026-09-24-
-- room-layout-best-practices.md, research/2026-09-23-room-and-zone-
-- requirements.md). Without this file, nothing above it can see a wall as a
-- wall, so enclosure is unanswerable; cannot see whether a surface is
-- smoothed or engraved, so the user's "every room at least smoothed"
-- standard is invisible; cannot read a traffic designation at all.
--
-- WHY ONE FILE FOR FOUR QUESTIONS: enclosure, finish, material and traffic
-- all answer over the SAME two tile sets of a single zone -- its own
-- footprint (x1..x2, y1..y2 at its own z) and the one-tile ring immediately
-- around that footprint -- so they share one zone-resolution helper and one
-- per-tile reader. Kept as four separate verbs rather than one combined
-- blob, the same call df-overseer-nobles.lua made for verify vs
-- requirements: "a caller may well want the appointment check without the
-- room check or vice versa, and conflating them would hide which one
-- failed."
--
-- ACT/SENSE RULE (binds every read here, df-overseer-diggable.lua's own
-- ACT/SENSE FIX header, decisions/DECISIONS.md 2026-09-16): a hidden tile
-- reports unknown, never its true value, never a silent default. Unlike
-- diggable.lua's dig designation (which acts blindly into unrevealed
-- ground), nothing here ever WRITES a designation, so there is no
-- symmetric "admit unconditionally" case to mirror -- every tile this file
-- touches is a pure read, and every hidden tile it touches is reported
-- hidden, full stop. A read failure (isTileVisible/getTileType/tiletype
-- attrs erroring on a VISIBLE tile) is tracked the same way, via
-- `read_failures` plus `dfhack.printerr`, the discipline df-overseer-
-- nobles.lua's room_value_status and df-overseer-zone.lua's
-- zone_room_value_status both already use: a failed read reports itself as
-- a failed read, never collapsed into a default.
--
-- BOUNDED ALWAYS: every command below is anchored on a zone id, resolved
-- once via `df.building.find` (O(1), not a scan of the zone vector -- see
-- MEASURED LIVE below) to its own x1/y1/x2/y2/z. All tile reads are then
-- exactly the zone's own footprint (width*height tiles) plus its one-tile
-- boundary ring (2*(width+height)+4 tiles) -- never a flood-fill, never a
-- map scan. MAX_FOOTPRINT_TILES below is a hard refusal, not a silent
-- truncation, on the off chance a caller names a zone far larger than any
-- real room on this fort.
--
-- QUESTION-LEVEL VERBS, NEVER A TILE DUMP (docs/PURPOSE.md commitment 1):
-- every result is a count, a fraction, or a small breakdown table keyed by
-- game enum name, never a per-tile list of positions -- nothing here could
-- be reassembled into a map, the same discipline df-overseer-diggable.lua
-- and df-overseer-trees.lua already hold to for the same reason.
--
-- COMMANDS (all output is one JSON object; an unreadable/hidden tile is
-- counted as unknown, never guessed):
--   enclosure ZONE_ID   is the zone's footprint enclosed, and if not, how
--                       badly: a count of boundary-ring gaps, each typed
--                       doorway / open_floor_edge / missing_wall. Three-
--                       state result: enclosed / not_enclosed / cannot_tell
--                       (nobles.requirements' own discipline: a confirmed
--                       gap always outranks an unknown tile, but no unknown
--                       tile is ever silently read as "fine").
--   finish ZONE_ID      how many of the footprint's floor tiles, and how
--                       many of the boundary ring's WALL-shaped tiles, are
--                       smooth / engraved / rough_natural / constructed.
--                       Counts and fractions only.
--   material ZONE_ID    what every boundary-ring tile (any shape, not just
--                       WALL -- an open ring tile still has an underlying
--                       material once something is built or dug there) is
--                       made of, at the game's own tiletype_material
--                       granularity (SOIL, STONE, CONSTRUCTION, ...).
--   traffic ZONE_ID     the traffic designation (Normal/Low/High/
--                       Restricted) set over the zone's own footprint
--                       tiles. READ ONLY: this fort has never had a
--                       traffic designation set anywhere (memory/dfhack-
--                       environment.md, "0 of 6,856,704 tiles are
--                       non-Normal"), so every real call here is expected
--                       to report 100% Normal, not an error -- setting a
--                       traffic designation is a mutation and belongs with
--                       the layout-checker action work, not this stream.
--
-- WALL-LIKE SHAPES AND WHY FORTIFICATION IS NOT A GAP: `enclosure` treats a
-- ring tile as a solid boundary segment (not a gap) if its shape is WALL or
-- FORTIFICATION -- both block movement, the property enclosure is actually
-- asking about, even though a fortification is see-through and would not
-- read as "finished" the way a smoothed wall would. `finish` and `material`
-- deliberately do NOT follow that same widening: `finish`'s "boundary wall
-- tiles" and `material`'s per-tile material reading both use their own,
-- narrower or wider tile sets as documented above, because finish/material
-- are asked about the physical stuff of the boundary, not whether it stops
-- a dwarf.
--
-- SOIL-SMOOTHING QUESTION, SETTLED FROM THE INSTALL'S OWN TILETYPE DATA
-- (Working.md 2026-09-24: "a design rule rests on [soil cannot be smoothed]
-- ... needs verification"; live read-only probe, this stream, VM 103,
-- DFHack 53.16-r1.1, fort paused throughout): iterated every tiletype in
-- `df.tiletype.attrs` (697 entries, index range 0..696) and grouped by
-- `.material`/`.special`. There is exactly ONE tiletype with `.material ==
-- SOIL` and `.shape == WALL` on this install: `SoilWall`, `.special ==
-- NONE (-1)`. Across EVERY shape, not just WALL, no SOIL-material tiletype
-- anywhere in the full 697-entry table carries `.special == SMOOTH (3)` or
-- `SMOOTH_DEAD (11)` -- the only specials any SOIL tiletype carries are
-- NONE, NORMAL, FURROWED or WET. By contrast STONE-material WALL tiletypes
-- include 20 entries with `.special == SMOOTH`. **Soil cannot be smoothed
-- in 53.16: confirmed from the install's own static tiletype table, not
-- inferred** -- there is no "smoothed soil" tiletype for DFHack to switch a
-- tile to, the same way there is no tiletype for a task the game engine
-- itself has no representation for. This settles Working.md's open
-- question: the "smooth where stone, construct a wall where soil" design
-- rule is correct as stated. (The probe script itself was not committed;
-- it read only `df.tiletype`/`df.tiletype_shape`/`df.tiletype_material`/
-- `df.tiletype_special`, static install data, no map tile was touched.)
--
-- MEASURED LIVE, this stream, VM 103/Uniboslan (paused throughout, fort
-- quicksaved before this stream began, read-only):
-- `df.building.find(ZONE_ID)` resolves both of the fort's real zones (10,
-- 11) directly to a `building_civzonest` with real x1/y1/x2/y2/z, O(1), not
-- a scan of ACTIVITY_ZONE -- cheaper than df-overseer-zone.lua's own
-- MAX_ZONE_SCAN-bounded walk, which this file does not need since it is
-- never asked to enumerate zones, only to resolve one by id. Both zones
-- read back a 3x3 footprint. Zone 10's boundary ring is essentially all
-- open grass floor (GRASS_LIGHT/GRASS_DARK material, FLOOR shape) with no
-- WALL-shaped tile anywhere on it -- `enclosure` on zone 10 reports
-- not_enclosed, every one of its ring tiles an open_floor_edge gap except
-- one SHRUB tile, consistent with CLAUDE.md's "both outdoors" status line.
-- Zone 11's ring is the same open grass floor plus exactly one WALL-shaped
-- tile (material TREE -- a living tree presents shape WALL, per the game's
-- own tiletype table) and one building-occupied RAMP_TOP tile --
-- `enclosure` on zone 11 also reports not_enclosed, for the same reason.
-- Both fully visible (no hidden ring tiles on either), so both reports are
-- definite not_enclosed, not cannot_tell. `traffic` on both zones reads
-- Normal on all 9 footprint tiles, matching the fort-wide "0 non-Normal
-- tiles" fact above -- a real "none set" read, not an error. `finish` on
-- zone 11's one WALL-shaped tile is the case that caught the TreeTrunkPillar
-- bug documented above: fixed, it now reads rough_natural, not smooth. Both
-- zones' floor tiles read entirely rough_natural (grass), consistent with
-- neither having ever been dug or smoothed. See this handoff's own Result
-- section for the exact live transcript this header summarises.

local json = require('json')

local NULL = "\0"
local MAX_FOOTPRINT_TILES = 2500   -- 50x50; no real room on this fort comes close
local MAX_RING_TILES = 900         -- perimeter of a MAX_FOOTPRINT_TILES square, generous
local MAX_ENGRAVINGS = 20000       -- bounded scan of world.event.engravings, not the map

-- ---------------------------------------------------------------------------
-- Zone resolution
-- ---------------------------------------------------------------------------

-- O(1): df.building.find is a direct id lookup, not a scan of the zone
-- vector (df-overseer-zone.lua's list_zones walks ACTIVITY_ZONE bounded by
-- its own MAX_ZONE_SCAN because IT enumerates; this file only ever
-- resolves one caller-named id).
local function find_zone(zone_id)
  local id = tonumber(zone_id)
  if not id then return nil, "ZONE_ID must be a number" end
  local ok, b = pcall(df.building.find, id)
  if not ok or not b then
    return nil, "no building with id " .. tostring(zone_id)
  end
  local ok_i, is_zone = pcall(function() return df.building_civzonest:is_instance(b) end)
  if not ok_i or not is_zone then
    return nil, "building id " .. id .. " exists but is not an activity zone"
  end
  return b
end

local function footprint_dims(b)
  return (b.x2 - b.x1 + 1), (b.y2 - b.y1 + 1)
end

-- Every (x,y,z) in the zone's own footprint rectangle.
local function footprint_tiles(b)
  local out = {}
  for x = b.x1, b.x2 do
    for y = b.y1, b.y2 do
      out[#out + 1] = {x, y, b.z}
    end
  end
  return out
end

-- Every (x,y,z) in the one-tile ring immediately around the footprint
-- (never inside it). Same shape as df-overseer-diggable.lua's
-- borders_walkable_network ring, generalised to a rectangle's full
-- perimeter rather than one edge.
local function ring_tiles(b)
  local out = {}
  for x = b.x1 - 1, b.x2 + 1 do
    out[#out + 1] = {x, b.y1 - 1, b.z}
    out[#out + 1] = {x, b.y2 + 1, b.z}
  end
  for y = b.y1, b.y2 do
    out[#out + 1] = {b.x1 - 1, y, b.z}
    out[#out + 1] = {b.x2 + 1, y, b.z}
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Per-tile read: hidden tiles report hidden, never a guessed value. A read
-- failure on a visible tile is `ok = false` with `err` set, never defaulted.
-- ---------------------------------------------------------------------------

local function tile_read(x, y, z)
  if not dfhack.maps.isValidTilePos(x, y, z) then
    return {ok = false, err = "invalid tile position"}
  end
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    return {ok = false, err = "isTileVisible failed: " .. tostring(visible)}
  end
  if not visible then
    return {ok = true, hidden = true}
  end
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return {ok = false, err = "getTileType failed: " .. tostring(tt)}
  end
  local ok_s, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  local ok_m, mat = pcall(function() return df.tiletype.attrs[tt].material end)
  local ok_sp, special = pcall(function() return df.tiletype.attrs[tt].special end)
  if not (ok_s and ok_m and ok_sp) then
    return {ok = false, err = "df.tiletype.attrs read failed for tiletype " .. tostring(tt)}
  end
  local building_type = nil
  local ok_b, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(x, y, z))
  if ok_b and bld then
    local ok_t, t = pcall(function() return bld:getType() end)
    if ok_t then building_type = t end
  end
  return {ok = true, hidden = false, shape = shape, material = mat, special = special,
    building_type = building_type}
end

local function shape_name(shape)
  if shape == nil then return NULL end
  local ok, name = pcall(function() return df.tiletype_shape[shape] end)
  return (ok and name) or ("<unknown:" .. tostring(shape) .. ">")
end

local function material_name(mat)
  if mat == nil then return NULL end
  local ok, name = pcall(function() return df.tiletype_material[mat] end)
  return (ok and name) or ("<unknown:" .. tostring(mat) .. ">")
end

local function building_type_name(bt)
  if bt == nil then return NULL end
  local ok, name = pcall(function() return df.building_type[bt] end)
  return (ok and name) or ("<unknown:" .. tostring(bt) .. ">")
end

local WALL_LIKE_SHAPES = {
  [df.tiletype_shape.WALL] = true,
  [df.tiletype_shape.FORTIFICATION] = true,
}

-- Shapes a dwarf can stand on or move through freely -- an open_floor_edge
-- gap, as opposed to a shape suggesting a wall belongs there but is absent
-- (EMPTY) or an unrecognised shape (treated the same as EMPTY: honestly
-- "missing_wall", not guessed as open).
local OPEN_WALKABLE_SHAPES = {
  [df.tiletype_shape.FLOOR] = true,
  [df.tiletype_shape.BOULDER] = true,
  [df.tiletype_shape.PEBBLES] = true,
  [df.tiletype_shape.STAIR_UP] = true,
  [df.tiletype_shape.STAIR_DOWN] = true,
  [df.tiletype_shape.STAIR_UPDOWN] = true,
  [df.tiletype_shape.RAMP] = true,
  [df.tiletype_shape.RAMP_TOP] = true,
  [df.tiletype_shape.BROOK_BED] = true,
  [df.tiletype_shape.BROOK_TOP] = true,
  [df.tiletype_shape.BRANCH] = true,
  [df.tiletype_shape.TRUNK_BRANCH] = true,
  [df.tiletype_shape.TWIG] = true,
  [df.tiletype_shape.SAPLING] = true,
  [df.tiletype_shape.SHRUB] = true,
  [df.tiletype_shape.ENDLESS_PIT] = true,
}

local DOOR_BUILDING_TYPE = df.building_type.Door

-- ---------------------------------------------------------------------------
-- enclosure ZONE_ID
-- ---------------------------------------------------------------------------

function enclosure(zone_id)
  local b, err = find_zone(zone_id)
  if not b then return {error = err} end
  local w, h = footprint_dims(b)
  if w * h > MAX_FOOTPRINT_TILES then
    return {error = "zone " .. b.id .. " footprint is " .. w .. "x" .. h
      .. ", over this tool's " .. MAX_FOOTPRINT_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local ring = ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end

  local read_failures = {}
  local gaps_by_type = {doorway = 0, open_floor_edge = 0, missing_wall = 0}
  local gap_count = 0
  local unknown_count = 0
  local wall_like_count = 0

  for _, xyz in ipairs(ring) do
    local t = tile_read(xyz[1], xyz[2], xyz[3])
    if not t.ok then
      unknown_count = unknown_count + 1
      table.insert(read_failures, "boundary tile: " .. t.err)
      pcall(function()
        dfhack.printerr("df-overseer-surface: enclosure zone=" .. b.id .. " read failure: " .. t.err)
      end)
    elseif t.hidden then
      unknown_count = unknown_count + 1
    elseif WALL_LIKE_SHAPES[t.shape] then
      wall_like_count = wall_like_count + 1
    elseif t.building_type == DOOR_BUILDING_TYPE then
      gaps_by_type.doorway = gaps_by_type.doorway + 1
      gap_count = gap_count + 1
    elseif OPEN_WALKABLE_SHAPES[t.shape] then
      gaps_by_type.open_floor_edge = gaps_by_type.open_floor_edge + 1
      gap_count = gap_count + 1
    else
      -- EMPTY, or any shape this table does not recognise: honestly
      -- "missing_wall", never guessed as open.
      gaps_by_type.missing_wall = gaps_by_type.missing_wall + 1
      gap_count = gap_count + 1
    end
  end

  local status
  if gap_count > 0 then
    status = "not_enclosed"
  elseif unknown_count > 0 then
    status = "cannot_tell"
  else
    status = "enclosed"
  end

  return {
    zone_id = b.id,
    footprint = {width = w, height = h},
    boundary_ring_tiles = #ring,
    status = status,
    gap_count = gap_count,
    gaps_by_type = gaps_by_type,
    wall_like_tiles = wall_like_count,
    unknown_tiles = unknown_count,
    read_failures = read_failures,
  }
end

-- ---------------------------------------------------------------------------
-- finish ZONE_ID
-- ---------------------------------------------------------------------------

-- Positions of every recorded engraving, bounded, built once per call (not
-- a map scan: `world.event.engravings` is the game's own list of real
-- engravings, currently 0 entries on this fort -- memory/dfhack-
-- environment.md has no prior figure for this, first read this stream).
local function engraved_positions()
  local ok, ev = pcall(function() return df.global.world.event.engravings end)
  local set, truncated = {}, false
  if not ok or not ev then return set, false, "world.event.engravings unreadable: " .. tostring(ev) end
  local n = math.min(#ev, MAX_ENGRAVINGS)
  truncated = #ev > MAX_ENGRAVINGS
  for i = 0, n - 1 do
    local eng = ev[i]
    local ok_p, x, y, z = pcall(function() return eng.pos.x, eng.pos.y, eng.pos.z end)
    if ok_p then
      set[x .. "," .. y .. "," .. z] = true
    end
  end
  return set, truncated, nil
end

-- One tile's finish class: smooth / engraved / rough_natural / constructed,
-- or nil (hidden/unreadable, caller tracks separately). `engraved_set` maps
-- "x,y,z" -> true for every recorded engraving.
local SMOOTH_SPECIALS = {
  [df.tiletype_special.SMOOTH] = true,
  [df.tiletype_special.SMOOTH_DEAD] = true,
}

-- LIVE BUG FOUND AND FIXED THIS STREAM, against zone 11's own real boundary
-- tile: `.special` is NOT exclusively a mason's-smoothing marker. A live
-- read-only probe of every WALL-shaped, TREE-material tiletype found
-- `TreeTrunkPillar` (a living tree trunk's own pillar shape, not anything a
-- dwarf smoothed) carries `.special == SMOOTH (3)` -- the same numeric slot
-- the game's masonry uses for an actually-smoothed stone wall, and
-- `TreeDeadTrunkPillar` likewise carries `SMOOTH_DEAD (11)`. Zone 11's one
-- real WALL-shaped ring tile IS a living tree, and the first version of
-- this classifier reported it "smooth" -- a real tile the game itself has
-- never let anyone finish, read back as satisfying the user's "every room
-- at least smoothed" standard. Restricting the SMOOTH/SMOOTH_DEAD check to
-- the same diggable-material set df-overseer-diggable.lua's own
-- DIGGABLE_MATERIALS table already uses (a natural material a mason could
-- actually be asked to smooth: STONE, SOIL, FEATURE, MINERAL, LAVA_STONE,
-- FROZEN_LIQUID; duplicated here rather than shared, same reqscript-
-- coupling call diggable.lua's own header already made for
-- parse_quickfort_stats) fixes it: TREE/PLANT/GRASS_*/other organic or
-- liquid materials always read rough_natural now, never smooth, regardless
-- of what `.special` happens to carry.
local FINISHABLE_MATERIALS = {
  [df.tiletype_material.STONE] = true,
  [df.tiletype_material.SOIL] = true,
  [df.tiletype_material.FEATURE] = true,
  [df.tiletype_material.MINERAL] = true,
  [df.tiletype_material.LAVA_STONE] = true,
  [df.tiletype_material.FROZEN_LIQUID] = true,
}

local function finish_class(t, x, y, z, engraved_set)
  if not t.ok or t.hidden then return nil end
  if t.material == df.tiletype_material.CONSTRUCTION then return "constructed" end
  if FINISHABLE_MATERIALS[t.material] and SMOOTH_SPECIALS[t.special] then
    if engraved_set[x .. "," .. y .. "," .. z] then return "engraved" end
    return "smooth"
  end
  return "rough_natural"
end

local function empty_finish_bucket()
  return {counted = 0, smooth = 0, engraved = 0, rough_natural = 0, constructed = 0, unknown = 0}
end

local function fraction_finished(bucket)
  if bucket.counted == 0 then return NULL end
  return (bucket.smooth + bucket.engraved + bucket.constructed) / bucket.counted
end

function finish(zone_id)
  local b, err = find_zone(zone_id)
  if not b then return {error = err} end
  local w, h = footprint_dims(b)
  if w * h > MAX_FOOTPRINT_TILES then
    return {error = "zone " .. b.id .. " footprint is " .. w .. "x" .. h
      .. ", over this tool's " .. MAX_FOOTPRINT_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local ring = ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end

  local engraved_set, eng_truncated, eng_err = engraved_positions()
  local read_failures = {}
  if eng_err then table.insert(read_failures, eng_err) end

  local floor = empty_finish_bucket()
  for _, xyz in ipairs(footprint_tiles(b)) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local t = tile_read(x, y, z)
    floor.counted = floor.counted + 1
    if not t.ok then
      floor.unknown = floor.unknown + 1
      table.insert(read_failures, "floor tile: " .. t.err)
      pcall(function() dfhack.printerr("df-overseer-surface: finish zone=" .. b.id .. " floor read failure: " .. t.err) end)
    elseif t.hidden then
      floor.unknown = floor.unknown + 1
    else
      local class = finish_class(t, x, y, z, engraved_set)
      floor[class] = floor[class] + 1
    end
  end

  local boundary_wall = empty_finish_bucket()
  for _, xyz in ipairs(ring) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local t = tile_read(x, y, z)
    if t.ok and not t.hidden and t.shape == df.tiletype_shape.WALL then
      boundary_wall.counted = boundary_wall.counted + 1
      local class = finish_class(t, x, y, z, engraved_set)
      boundary_wall[class] = boundary_wall[class] + 1
    elseif t.ok and t.hidden then
      -- A hidden ring tile might or might not turn out to be a wall at
      -- all; it is not counted into boundary_wall's total (we don't yet
      -- know it IS a wall tile), but is surfaced so a caller knows the
      -- boundary is not fully revealed.
      boundary_wall.unknown = boundary_wall.unknown + 1
    elseif not t.ok then
      table.insert(read_failures, "boundary tile: " .. t.err)
      pcall(function() dfhack.printerr("df-overseer-surface: finish zone=" .. b.id .. " boundary read failure: " .. t.err) end)
    end
  end

  return {
    zone_id = b.id,
    footprint = {width = w, height = h},
    floor = floor,
    floor_fraction_finished = fraction_finished(floor),
    boundary_wall = boundary_wall,
    boundary_wall_fraction_finished = fraction_finished(boundary_wall),
    engravings_scan_truncated = eng_truncated,
    read_failures = read_failures,
  }
end

-- ---------------------------------------------------------------------------
-- material ZONE_ID
-- ---------------------------------------------------------------------------

function boundary_material(zone_id)
  local b, err = find_zone(zone_id)
  if not b then return {error = err} end
  local ring = ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end

  local by_material = {}
  local unknown = 0
  local read_failures = {}
  for _, xyz in ipairs(ring) do
    local t = tile_read(xyz[1], xyz[2], xyz[3])
    if not t.ok then
      unknown = unknown + 1
      table.insert(read_failures, "boundary tile: " .. t.err)
      pcall(function() dfhack.printerr("df-overseer-surface: material zone=" .. b.id .. " read failure: " .. t.err) end)
    elseif t.hidden then
      unknown = unknown + 1
    else
      local name = material_name(t.material)
      by_material[name] = (by_material[name] or 0) + 1
    end
  end

  return {
    zone_id = b.id,
    boundary_ring_tiles = #ring,
    by_material = by_material,
    unknown_tiles = unknown,
    read_failures = read_failures,
  }
end

-- ---------------------------------------------------------------------------
-- traffic ZONE_ID (read only -- see header)
-- ---------------------------------------------------------------------------

local TRAFFIC_NAMES = {[0] = "Normal", [1] = "Low", [2] = "High", [3] = "Restricted"}

function traffic(zone_id)
  local b, err = find_zone(zone_id)
  if not b then return {error = err} end
  local w, h = footprint_dims(b)
  if w * h > MAX_FOOTPRINT_TILES then
    return {error = "zone " .. b.id .. " footprint is " .. w .. "x" .. h
      .. ", over this tool's " .. MAX_FOOTPRINT_TILES .. "-tile bound; refusing rather than scanning it"}
  end

  local by_class = {Normal = 0, Low = 0, High = 0, Restricted = 0}
  local unknown = 0
  local read_failures = {}
  local counted = 0
  for _, xyz in ipairs(footprint_tiles(b)) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    counted = counted + 1
    if not dfhack.maps.isValidTilePos(x, y, z) then
      unknown = unknown + 1
      table.insert(read_failures, "floor tile: invalid tile position")
    else
      local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
      if not ok_vis then
        unknown = unknown + 1
        table.insert(read_failures, "floor tile: isTileVisible failed: " .. tostring(visible))
      elseif not visible then
        unknown = unknown + 1
      else
        local ok_f, flags = pcall(dfhack.maps.getTileFlags, xyz2pos(x, y, z))
        if not ok_f or not flags then
          unknown = unknown + 1
          table.insert(read_failures, "floor tile: getTileFlags failed: " .. tostring(flags))
          pcall(function() dfhack.printerr("df-overseer-surface: traffic zone=" .. b.id .. " read failure") end)
        else
          local name = TRAFFIC_NAMES[flags.traffic]
          if name then
            by_class[name] = by_class[name] + 1
          else
            unknown = unknown + 1
            table.insert(read_failures, "floor tile: unrecognised traffic value " .. tostring(flags.traffic))
          end
        end
      end
    end
  end

  return {
    zone_id = b.id,
    footprint = {width = w, height = h},
    footprint_tiles = counted,
    by_class = by_class,
    unknown_tiles = unknown,
    all_normal = (by_class.Low == 0 and by_class.High == 0 and by_class.Restricted == 0 and unknown == 0),
    read_failures = read_failures,
  }
end

-- ---------------------------------------------------------------------------
-- CLI
-- ---------------------------------------------------------------------------

if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

local function emit(result)
  print(json.encode(result, {null = NULL}))
end

if cmd == "enclosure" then
  if not args[2] then
    print("usage: df-overseer-surface enclosure ZONE_ID")
  else
    emit(enclosure(args[2]))
  end
elseif cmd == "finish" then
  if not args[2] then
    print("usage: df-overseer-surface finish ZONE_ID")
  else
    emit(finish(args[2]))
  end
elseif cmd == "material" then
  if not args[2] then
    print("usage: df-overseer-surface material ZONE_ID")
  else
    emit(boundary_material(args[2]))
  end
elseif cmd == "traffic" then
  if not args[2] then
    print("usage: df-overseer-surface traffic ZONE_ID")
  else
    emit(traffic(args[2]))
  end
else
  print("usage: df-overseer-surface enclosure ZONE_ID")
  print("usage: df-overseer-surface finish ZONE_ID")
  print("usage: df-overseer-surface material ZONE_ID")
  print("usage: df-overseer-surface traffic ZONE_ID")
end
