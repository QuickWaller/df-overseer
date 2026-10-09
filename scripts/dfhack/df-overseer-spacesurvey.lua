-- df-overseer-spacesurvey.lua
--@module = true
--
-- Read-only survey of UNUSED DUG SPACE (register 2026-10-09 "Unused dug space
-- survey"). Backs `openarea.survey`. Nothing here designates, builds or
-- writes anything.
--
-- WHAT IT ANSWERS. Where is there already-dug, revealed floor that belongs to
-- nothing: not a zone, a stockpile, a building, a reservation or a corridor.
-- The Architect can then propose a room in space that already exists instead
-- of digging new rock. `openarea.find` only answers a size the caller asks
-- for; this one reports what is there.
--
-- A tile is OPEN if it is revealed (not hidden), its shape is FLOOR (stairs
-- and ramps are circulation, never space), no deep liquid is on it, it is not
-- outside (open sky), and no building occupies it. It is CLAIMED if it lies in
-- any zone, any stockpile, any building footprint or any reservation. Open
-- and unclaimed tiles that sit in at least one 2x2 block of open unclaimed
-- tiles are SPACE; the remaining open unclaimed tiles (width-1 runs) are
-- CORRIDOR and are not regions, but a region records whether it touches one
-- (or a corridor-role reservation). Regions are 4-connected components of
-- SPACE.
--
-- THE WINDOW. Never the whole map (the full-map scan hung DF, catalogue P-7).
-- Per level, a box around each of OUR OWN records (zones, stockpiles,
-- buildings, reservations, blueprint sites, landmarks), padded and merged;
-- total tiles are held under a hard cap in DATA. Over the cap the tool REFUSES
-- with an error and never truncates. Space outside every window is not seen.
--
-- COORDINATE RULE (docs/PURPOSE.md commitment 1). Real coordinates live only
-- inside survey(). The report holds ids (a hash of the region's lowest tile,
-- never a coordinate), counts, bounding-box width and height, a ratio, level
-- offsets and landmark names with distances. No tile list, no grid.
--
-- Pure logic (survey) takes a `world` table so
-- tests/test_spacesurvey_lua_logic.py drives it with a fake map:
--   world.boxes      list of {z, x1, y1, x2, y2} scan boxes (already merged)
--   world.tile(x,y,z) -> "open" | "claimed" | "corridor" | nil (unknown/solid)
--   world.landmarks  list of {name, x, y, z}
--
-- Usage (via df-overseer-openarea): survey [MIN_TILES] [MAX_RESULTS]

local DATA = {
  -- Hard cap on tiles read across all windows. Over it, REFUSE.
  max_window_tiles = 60000,
  -- Padding added around each record rectangle, and the gap under which two
  -- rectangles on a level merge into one window.
  window_margin = 10,
  window_merge_gap = 10,
  -- A region needs at least this many tiles to be listed (arg default).
  default_min_tiles = 9,
  default_max_results = 10,
  max_results_cap = 30,
  -- An open tile belongs to SPACE (not corridor) if it is in some NxN block of
  -- open unclaimed tiles.
  space_block = 2,
  -- Nearest landmarks listed per region.
  nearest_landmarks = 3,
  -- Building types never counted as a claim on a tile (none today).
  ignored_building_types = {},
}

function data() return DATA end

local function key(x, y, z) return (z * 1024 + y) * 1024 + x end
local function unkey(k) return k % 1024, (k // 1024) % 1024, k // 1048576 end

-- Merge rectangles on one level (inclusive x1..x2, y1..y2) that overlap or lie
-- within `gap` of each other, repeating until stable.
function merge_rects(list, gap)
  local rects = {}
  for _, r in ipairs(list) do rects[#rects + 1] = { x1 = r.x1, y1 = r.y1, x2 = r.x2, y2 = r.y2 } end
  local changed = true
  while changed do
    changed = false
    local out = {}
    for _, r in ipairs(rects) do
      local merged = false
      for _, o in ipairs(out) do
        if r.x1 <= o.x2 + gap and o.x1 <= r.x2 + gap and r.y1 <= o.y2 + gap and o.y1 <= r.y2 + gap then
          o.x1, o.y1 = math.min(o.x1, r.x1), math.min(o.y1, r.y1)
          o.x2, o.y2 = math.max(o.x2, r.x2), math.max(o.y2, r.y2)
          merged, changed = true, true
          break
        end
      end
      if not merged then out[#out + 1] = r end
    end
    rects = out
  end
  return rects
end

-- records: list of {x1,y1,x2,y2,z}. Returns boxes (padded, merged per level).
function make_boxes(records, margin, gap)
  local by_z, zs = {}, {}
  for _, r in ipairs(records) do
    if not by_z[r.z] then by_z[r.z] = {}; zs[#zs + 1] = r.z end
    local l = by_z[r.z]
    l[#l + 1] = { x1 = r.x1 - margin, y1 = r.y1 - margin, x2 = r.x2 + margin, y2 = r.y2 + margin }
  end
  table.sort(zs)
  local boxes = {}
  for _, z in ipairs(zs) do
    for _, m in ipairs(merge_rects(by_z[z], gap)) do
      boxes[#boxes + 1] = { z = z, x1 = math.max(0, m.x1), y1 = math.max(0, m.y1), x2 = m.x2, y2 = m.y2 }
    end
  end
  return boxes
end

local function hash_id(k)
  -- Knuth multiplicative hash of the lowest tile's key, kept to 6 hex digits.
  return string.format("region-%06x", (k * 2654435761) % 16777216)
end

-- Returns the report table, or nil plus an error string.
function survey(world, opts)
  opts = opts or {}
  local min_tiles = opts.min_tiles or DATA.default_min_tiles
  local max_results = math.min(opts.max_results or DATA.default_max_results, DATA.max_results_cap)
  local cap = opts.cap or DATA.max_window_tiles

  local total = 0
  for _, b in ipairs(world.boxes) do
    total = total + (b.x2 - b.x1 + 1) * (b.y2 - b.y1 + 1)
  end
  if total > cap then
    return nil, string.format(
      "the scan window is %d tiles, over the cap of %d; refusing rather than truncating", total, cap)
  end

  -- Classify every tile once.
  local kind = {}
  local open = {}
  for _, b in ipairs(world.boxes) do
    for z = b.z, b.z do
      for y = b.y1, b.y2 do
        for x = b.x1, b.x2 do
          local k = key(x, y, z)
          if kind[k] == nil then
            local c = world.tile(x, y, z) or false
            kind[k] = c
          end
        end
      end
    end
  end

  -- SPACE = open tiles in some NxN block of open tiles.
  local n = DATA.space_block
  local space = {}
  for k, c in pairs(kind) do
    if c == "open" then
      local x, y, z = unkey(k)
      for ox = x - n + 1, x do
        for oy = y - n + 1, y do
          local all = true
          for dx = 0, n - 1 do
            for dy = 0, n - 1 do
              if kind[key(ox + dx, oy + dy, z)] ~= "open" then all = false; break end
            end
            if not all then break end
          end
          if all then space[k] = true end
        end
        if space[k] then break end
      end
    end
  end

  local function is_corridor(k)
    local c = kind[k]
    return c == "corridor" or (c == "open" and not space[k])
  end

  -- Components of SPACE.
  local seen, regions = {}, {}
  local ks = {}
  for k in pairs(space) do ks[#ks + 1] = k end
  table.sort(ks)
  for _, start in ipairs(ks) do
    if not seen[start] then
      local stack, count = { start }, 0
      seen[start] = true
      local minx, miny, maxx, maxy
      local touches = false
      local sumx, sumy = 0, 0
      local _, _, z = unkey(start)
      while #stack > 0 do
        local k = table.remove(stack)
        local x, y = unkey(k)
        count = count + 1
        sumx, sumy = sumx + x, sumy + y
        minx = minx and math.min(minx, x) or x
        maxx = maxx and math.max(maxx, x) or x
        miny = miny and math.min(miny, y) or y
        maxy = maxy and math.max(maxy, y) or y
        for _, d in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
          local nk = key(x + d[1], y + d[2], z)
          if space[nk] then
            if not seen[nk] then seen[nk] = true; stack[#stack + 1] = nk end
          elseif is_corridor(nk) then
            touches = true
          end
        end
      end
      if count >= min_tiles then
        local w, h = maxx - minx + 1, maxy - miny + 1
        local cx, cy = sumx / count, sumy / count
        local near = {}
        for _, lm in ipairs(world.landmarks or {}) do
          local dx, dy = lm.x - cx, lm.y - cy
          near[#near + 1] = {
            name = lm.name,
            distance_tiles = math.floor(math.sqrt(dx * dx + dy * dy) + 0.5),
            level_offset = z - lm.z,
          }
        end
        table.sort(near, function(a, b)
          if a.distance_tiles ~= b.distance_tiles then return a.distance_tiles < b.distance_tiles end
          return a.name < b.name
        end)
        while #near > DATA.nearest_landmarks do table.remove(near) end
        local rect = count / (w * h)
        regions[#regions + 1] = {
          id = hash_id(start),
          tiles = count,
          bbox = { w = w, h = h },
          rectangularity = math.floor(rect * 100 + 0.5) / 100,
          tiles_to_square = w * h - count,
          level_vs_nearest_landmark = near[1] and near[1].level_offset or nil,
          nearest_landmarks = near,
          touches_corridor = touches,
          _score = count * rect,
        }
      end
    end
  end

  table.sort(regions, function(a, b)
    if a._score ~= b._score then return a._score > b._score end
    return a.id < b.id
  end)
  local found = #regions
  while #regions > max_results do table.remove(regions) end
  for _, r in ipairs(regions) do r._score = nil end
  return {
    regions = regions,
    found = found,
    shown = #regions,
    min_tiles = min_tiles,
    scanned_tiles = total,
    notes = {
      "Only space inside a window around our own records (zones, stockpiles, buildings, reservations, sites, landmarks) is seen.",
      "Distances are straight-line tiles to the region's centre, not walking distance.",
      "level_offset is the region's level minus the landmark's: negative means below it.",
    },
  }
end

-- ---------------------------------------------------------------------------
-- Live world (DFHack). Not driven by the offline tests.
-- ---------------------------------------------------------------------------

local function add_rect(set, records, x1, y1, x2, y2, z)
  for y = y1, y2 do
    for x = x1, x2 do set[key(x, y, z)] = true end
  end
  records[#records + 1] = { x1 = x1, y1 = y1, x2 = x2, y2 = y2, z = z }
end

function live_world()
  local claimed, corridor, records = {}, {}, {}
  local errs = {}

  local okb, all = pcall(function() return df.global.world.buildings.all end)
  if okb and all then
    for _, bld in ipairs(all) do
      local okt, bt = pcall(function() return df.building_type[bld:getType()] end)
      if okt and not DATA.ignored_building_types[bt] then
        local extents_done = false
        local okr, room = pcall(function() return bld.room end)
        if okr and room and room.extents and room.width and room.width > 0 then
          -- Stockpiles and zones: only the flagged tiles of the room rectangle.
          local w, h = room.width, room.height
          local x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
          for dy = 0, h - 1 do
            for dx = 0, w - 1 do
              if room.extents[dy * w + dx] ~= 0 then
                local x, y = room.x + dx, room.y + dy
                claimed[key(x, y, bld.z)] = true
                x1, y1, x2, y2 = math.min(x1, x), math.min(y1, y), math.max(x2, x), math.max(y2, y)
              end
            end
          end
          if x1 <= x2 then
            records[#records + 1] = { x1 = x1, y1 = y1, x2 = x2, y2 = y2, z = bld.z }
          end
          extents_done = true
        end
        if not extents_done then
          add_rect(claimed, records, bld.x1, bld.y1, bld.x2, bld.y2, bld.z)
        end
      end
    end
  else
    errs[#errs + 1] = "could not read buildings"
  end

  local okr, rs = pcall(reqscript, 'df-overseer-reservations')
  if okr and rs and rs.list_raw then
    for _, r in ipairs(rs.list_raw()) do
      local okt, tiles = pcall(rs.tiles_of, r.handle)
      if okt and tiles then
        for _, t in ipairs(tiles) do
          if r.role == "corridor" then corridor[key(t.x, t.y, t.z)] = true
          else claimed[key(t.x, t.y, t.z)] = true end
          records[#records + 1] = { x1 = t.x, y1 = t.y, x2 = t.x, y2 = t.y, z = t.z }
        end
      end
    end
  else
    errs[#errs + 1] = "could not read reservations"
  end

  local okbp, bp = pcall(reqscript, 'df-overseer-blueprint')
  if okbp and bp and bp.all_sites_raw then
    for _, s in ipairs(bp.all_sites_raw()) do
      records[#records + 1] = { x1 = s.x, y1 = s.y, x2 = s.x + s.w - 1, y2 = s.y + s.h - 1, z = s.z }
    end
  end

  local landmarks = {}
  local okl, lm = pcall(reqscript, 'df-overseer-landmarks')
  if okl and lm and lm.landmarks_with_coords then
    local list = lm.landmarks_with_coords()
    for _, l in ipairs(list or {}) do
      landmarks[#landmarks + 1] = { name = l.name, x = l.x, y = l.y, z = l.z }
      records[#records + 1] = { x1 = l.x, y1 = l.y, x2 = l.x, y2 = l.y, z = l.z }
    end
  else
    errs[#errs + 1] = "could not read landmarks"
  end

  local w = {
    boxes = make_boxes(records, DATA.window_margin, DATA.window_merge_gap),
    landmarks = landmarks,
    errors = errs,
  }
  w.tile = function(x, y, z)
    local k = key(x, y, z)
    if corridor[k] then return "corridor" end
    local blk = dfhack.maps.getTileBlock(x, y, z)
    if not blk then return nil end
    local lx, ly = x % 16, y % 16
    local des = blk.designation[lx][ly]
    if des.hidden or des.outside then return nil end
    local tt = blk.tiletype[lx][ly]
    if df.tiletype_shape[df.tiletype.attrs[tt].shape] ~= "FLOOR" then return nil end
    if des.flow_size >= 4 then return nil end
    if claimed[k] or blk.occupancy[lx][ly].building ~= 0 then return "claimed" end
    return "open"
  end
  return w
end

function survey_live(min_tiles, max_results)
  local world = live_world()
  local report, err = survey(world, { min_tiles = min_tiles, max_results = max_results })
  if not report then return { error = err } end
  for _, e in ipairs(world.errors) do
    report.notes[#report.notes + 1] = e
  end
  return report
end
