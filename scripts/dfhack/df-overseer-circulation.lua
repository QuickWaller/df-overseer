-- df-overseer-circulation.lua
--@module = true
--
-- Stage C1 of research/2026-10-08-architect-circulation-design.md (as cut by
-- research/2026-10-08-architect-circulation-red-team.md, which wins where
-- they disagree): a READ-ONLY circulation graph. Nothing here designates,
-- builds, pauses or writes anything.
--
-- WHAT IT ANSWERS. How do the rooms we have made connect: which rooms are
-- reached only by walking through another room (and whether the room walked
-- through is private, like a bedroom), where the dead ends are, which single
-- links are the only connection between named places (landmarks, stairs,
-- public rooms), and how many steps it is from the bedrooms to the dining
-- hall, the well and the stairs. The user found bedrooms opening into each
-- other by eye; this puts the same finding in numbers.
--
-- THE WINDOW (red team B4, catalogue P-7). The full-map scan that hung DF read
-- 6.86 million tiles with a closure each, and a walkable group's extent is
-- the whole surface, so neither the full map nor a group's extent is ever
-- scanned. The window is built ONLY from our own records: blueprint sites,
-- reservations, zones of room kinds, and named landmarks that sit near them.
-- Per level, each record's rectangle is merged with others within a small gap
-- (so a far-off tomb gets its own small window, never one huge box), padded by
-- a small margin, and the total tile count is checked against a hard cap held
-- in DATA. Over the cap the tool REFUSES with a clear error; it never
-- truncates. Tiles are read one block lookup at a time with no per-tile
-- closure, only inside those rectangles. Levels are only the levels that have
-- records; a stair or ramp that leaves the window is followed down its shaft
-- (a handful of single-tile reads) or reported as unknown, never scanned.
--
-- WHAT A TILE IS. A tile is walkable if its shape is in DATA.passable_shapes,
-- it is not hidden (a hidden tile is something a player cannot know, so it is
-- never read as open or shut, it is counted and its neighbours become
-- "frontier" nodes), no obstacle building stands on it, and no deep liquid is
-- on it. Movement is orthogonal. Doors do not block; a forbidden door is
-- recorded on the edge it sits on. Liquids and diagonal squeezes are not
-- modelled (stated in `notes`).
--
-- THE GRAPH. Nodes: rooms (zones of room kinds, by zone id and kind), named
-- landmarks (Well, workshops, depot), stairs and ramps (vertical landings),
-- open areas (wide leftover space), dead ends, frontiers (where the window
-- ends or an unrevealed tile begins) and junctions (a corridor run touching
-- three or more nodes). Edges: segments (a run of corridor tiles between two
-- nodes: length in steps, width class from the narrowest tile on it, doors),
-- openings (two nodes touching directly), and vertical links (stairs
-- certain, ramps inferred and marked so). Anything uncertain is listed in
-- `unknown`, never guessed.
--
-- REACHABILITY. The tile graph is built from tile shapes. The game's own
-- walkable groups (dfhack.maps.getWalkableGroup, the same source as
-- df-overseer-reachability.lua's tri-state helper) are read for each node and
-- compared with the graph's components: a disagreement is reported under
-- `group_agreement`, never silently resolved. NOTE (red team, verified in the
-- DFHack Lua API doc): that group cache is only updated while the game is
-- UNPAUSED, so on a paused fort a disagreement can be a stale cache and a
-- new dig or door change is invisible to it; `notes` says so every time.
--
-- COORDINATE RULE (docs/PURPOSE.md commitment 1). Real tile coordinates live
-- only inside this file, in the internal graph. The returned report holds
-- ids, kinds, names and numbers; levels are relative to the window's lowest
-- level. There is no tile list, grid or position anywhere in it.
--
-- Usage: ./dfhack-run df-overseer-circulation <graph|walk FROM TO>
--   graph        -- build the window and graph and return the report
--   walk FROM TO -- steps and the nodes passed between two named endpoints
--                   (rooms by name or "Kind #id", landmarks, "Stair n")
--
-- Pure logic (build_graph, summarize, walk_between) takes a `world` table so
-- tests/test_circulation_lua_logic.py can drive it with a fake map.

local json = require('json')
local textutil = reqscript('df-overseer-textutil')

-- ---------------------------------------------------------------------------
-- Data: everything per-kind or per-fort-policy lives here, not in branches.
-- ---------------------------------------------------------------------------
local DATA = {
  -- Hard cap on tiles read across the whole window. Over it, REFUSE.
  max_window_tiles = 60000,
  -- Padding added around each merged record rectangle.
  window_margin = 3,
  -- Two record rectangles on a level closer than this merge into one window.
  window_merge_gap = 10,
  -- A landmark joins the window only if within this many tiles of a window.
  landmark_reach = 24,
  -- Zones larger than this are not rooms (pastures, big gathering areas).
  zone_max_tiles = 900,
  -- Zone kinds (df.civzone_type names) that count as rooms.
  room_zone_kinds = {
    Bedroom = true, DiningHall = true, Dormitory = true, Barracks = true,
    Office = true, MeetingHall = true, Hospital = true, Tomb = true,
    Library = true, Temple = true,
  },
  -- Room kinds that must be leaves: nobody should walk through them.
  private_kinds = { Bedroom = true, Dormitory = true },
  -- Building types (df.building_type names) worth being a named landmark.
  landmark_building_kinds = {
    Well = true, Workshop = true, Furnace = true, TradeDepot = true,
  },
  -- Room kinds and landmark kinds that anchor a "single point of failure"
  -- report (a link is only reported if both sides hold at least one).
  anchor_room_kinds = { DiningHall = true, MeetingHall = true, Hospital = true },
  -- Tile shapes (df.tiletype_shape names) a dwarf can stand on.
  passable_shapes = {
    FLOOR = true, RAMP = true, STAIR_UP = true, STAIR_DOWN = true,
    STAIR_UPDOWN = true, BOULDER = true, PEBBLES = true, SHRUB = true,
    SAPLING = true, TWIG = true,
  },
  -- Building occupancy classes (df.tile_building_occ names) that block.
  blocked_occupancy = { Obstacle = true, Well = true, Impassable = true },
  -- Liquid depth at or above which a tile is not walked (reported unknown).
  deep_liquid_size = 4,
  -- Width classes by tile thickness (an NxN block of open tiles).
  width_classes = { { name = "narrow", max = 1 }, { name = "standard", max = 2 },
                    { name = "wide", max = 99 } },
  -- A tile this thick (NxN open block) belongs to an open area, not a corridor.
  open_area_min_width = 3,
  -- How far a stair or ramp shaft is followed outside the window.
  max_shaft_levels = 12,
  -- Walk numbers: sources are room kinds, targets are by label.
  walk_source_kinds = { "Bedroom" },
  walk_targets = {
    { label = "dining", room_kind = "DiningHall" },
    { label = "well", landmark_kind = "Well" },
    { label = "stairs", vertical = true },
  },
  -- Output caps (listed counts are always given in full alongside).
  max_rows = 60,
  max_nodes_listed = 300,
  max_edges_listed = 400,
}

function data() return DATA end

-- ---------------------------------------------------------------------------
-- Small helpers
-- ---------------------------------------------------------------------------
local function key(x, y, z) return (z * 1024 + y) * 1024 + x end
local function unkey(k) return k % 1024, (k // 1024) % 1024, k // 1048576 end

local function width_class(w)
  for _, c in ipairs(DATA.width_classes) do
    if w <= c.max then return c.name end
  end
  return DATA.width_classes[#DATA.width_classes].name
end

local function median(list)
  if #list == 0 then return nil end
  local s = {}
  for i, v in ipairs(list) do s[i] = v end
  table.sort(s)
  local n = #s
  if n % 2 == 1 then return s[(n + 1) // 2] end
  return (s[n // 2] + s[n // 2 + 1]) / 2
end

local function sorted_keys(t)
  local ks = {}
  for k in pairs(t) do ks[#ks + 1] = k end
  table.sort(ks)
  return ks
end

-- ---------------------------------------------------------------------------
-- Window
-- ---------------------------------------------------------------------------
local function rect_gap(a, b)
  local dx = math.max(a.x1 - b.x2, b.x1 - a.x2, 0)
  local dy = math.max(a.y1 - b.y2, b.y1 - a.y2, 0)
  return math.max(dx, dy)
end

local function merge_rects(list, gap)
  local merged = true
  while merged do
    merged = false
    for i = 1, #list do
      for j = i + 1, #list do
        if rect_gap(list[i], list[j]) <= gap then
          local a, b = list[i], list[j]
          a.x1, a.y1 = math.min(a.x1, b.x1), math.min(a.y1, b.y1)
          a.x2, a.y2 = math.max(a.x2, b.x2), math.max(a.y2, b.y2)
          table.remove(list, j)
          merged = true
          break
        end
      end
      if merged then break end
    end
  end
end

local function is_room_zone(zone)
  if not DATA.room_zone_kinds[zone.kind] then return false end
  local area = (zone.x2 - zone.x1 + 1) * (zone.y2 - zone.y1 + 1)
  return area <= DATA.zone_max_tiles
end

-- Returns windows, total_tiles, outside_landmarks or nil, error.
local function make_windows(world, cap)
  local per = {}
  local function add(z, x1, y1, x2, y2)
    per[z] = per[z] or {}
    table.insert(per[z], { x1 = x1, y1 = y1, x2 = x2, y2 = y2 })
  end
  for _, s in ipairs(world.sites or {}) do
    add(s.z, s.x, s.y, s.x + s.w - 1, s.y + s.h - 1)
  end
  for _, r in ipairs(world.reservations or {}) do
    add(r.z, r.x, r.y, r.x + r.w - 1, r.y + r.h - 1)
  end
  for _, zn in ipairs(world.zones or {}) do
    if is_room_zone(zn) then add(zn.z, zn.x1, zn.y1, zn.x2, zn.y2) end
  end
  if next(per) == nil then
    return nil, "no blueprint sites, reservations or room zones to build a window from"
  end
  for _, list in pairs(per) do merge_rects(list, DATA.window_merge_gap) end

  local outside = {}
  for _, lm in ipairs(world.landmarks or {}) do
    local joined = false
    for _, r in ipairs(per[lm.z] or {}) do
      if rect_gap(r, lm) <= DATA.landmark_reach then
        r.x1, r.y1 = math.min(r.x1, lm.x1), math.min(r.y1, lm.y1)
        r.x2, r.y2 = math.max(r.x2, lm.x2), math.max(r.y2, lm.y2)
        joined = true
        break
      end
    end
    if not joined then outside[#outside + 1] = lm.name end
  end

  local windows, total = {}, 0
  for _, z in ipairs(sorted_keys(per)) do
    merge_rects(per[z], DATA.window_merge_gap)
    for _, r in ipairs(per[z]) do
      local m = DATA.window_margin
      local w = {
        z = z,
        x1 = math.max(0, r.x1 - m), y1 = math.max(0, r.y1 - m),
        x2 = r.x2 + m, y2 = r.y2 + m,
      }
      total = total + (w.x2 - w.x1 + 1) * (w.y2 - w.y1 + 1)
      windows[#windows + 1] = w
    end
  end
  if total > cap then
    return nil, string.format(
      "refusing: the window built from our own records needs %d tiles over %d window(s) and %d level(s), "
        .. "above the cap of %d. It is not truncated; narrow the records or raise the cap in the tool's data.",
      total, #windows, #sorted_keys(per), cap)
  end
  return windows, total, outside
end

-- ---------------------------------------------------------------------------
-- Graph construction
-- ---------------------------------------------------------------------------
local NBR = { 1, -1, 1024, -1024 }

local function room_label(zone)
  if zone.name and zone.name ~= "" then return zone.name end
  return string.format("%s #%s", zone.kind, tostring(zone.id))
end

function build_graph(world, opts)
  opts = opts or {}
  local cap = math.min(opts.cap or DATA.max_window_tiles, DATA.max_window_tiles)
  local windows, total, outside = make_windows(world, cap)
  if not windows then return nil, total end

  local g = {
    unknown = {}, notes = {}, nodes = {}, node_order = {}, edges = {},
    window_count = #windows, window_tiles = total, outside_landmarks = outside,
    cap = cap,
  }
  local function unk(msg) g.unknown[#g.unknown + 1] = msg end

  local minz = math.huge
  for _, w in ipairs(windows) do minz = math.min(minz, w.z) end
  g.minz = minz
  local levels_seen = {}
  for _, w in ipairs(windows) do levels_seen[w.z] = true end
  g.level_count = #sorted_keys(levels_seen)

  -- Read tiles -------------------------------------------------------------
  local tiles, walk, door = {}, {}, {}
  local hidden_count, unreadable, deep_count = 0, 0, 0
  for _, w in ipairs(windows) do
    for y = w.y1, w.y2 do
      for x = w.x1, w.x2 do
        local t = world.read_tile(x, y, w.z)
        local k = key(x, y, w.z)
        if t == nil then
          unreadable = unreadable + 1
          tiles[k] = { unread = true }
        elseif t.hidden then
          hidden_count = hidden_count + 1
          tiles[k] = { hidden = true }
        else
          tiles[k] = { shape = t.shape }
          if t.deep then
            deep_count = deep_count + 1
          elseif not t.blocked and DATA.passable_shapes[t.shape] then
            walk[k] = true
            if t.door then door[k] = t.door end
          end
        end
      end
    end
  end
  g.hidden_tiles, g.unreadable_tiles = hidden_count, unreadable
  if hidden_count > 0 then
    unk(string.format("%d tile(s) in the window are not revealed; treated as not walkable and not guessed", hidden_count))
  end
  if unreadable > 0 then
    unk(string.format("%d tile(s) could not be read", unreadable))
  end
  if deep_count > 0 then
    unk(string.format("%d tile(s) hold deep liquid and are not walked", deep_count))
  end
  g.tiles, g.walk, g.door = tiles, walk, door

  -- Vertical links (tile level) --------------------------------------------
  local vlinks = {}  -- key -> list of {to=key, certainty=, dz=}
  local function vlink(a, b, certainty, dz)
    vlinks[a] = vlinks[a] or {}
    vlinks[b] = vlinks[b] or {}
    table.insert(vlinks[a], { to = b, certainty = certainty, dz = dz })
    table.insert(vlinks[b], { to = a, certainty = certainty, dz = -dz })
  end
  local linked = {}
  local function is_down_capable(shape) return shape == "STAIR_DOWN" or shape == "STAIR_UPDOWN" end
  local function is_up_capable(shape) return shape == "STAIR_UP" or shape == "STAIR_UPDOWN" end

  local stair_keys = {}
  for k in pairs(walk) do
    local sh = tiles[k].shape
    if sh == "STAIR_UP" or sh == "STAIR_DOWN" or sh == "STAIR_UPDOWN" then
      stair_keys[#stair_keys + 1] = k
    end
  end
  table.sort(stair_keys)
  for _, k in ipairs(stair_keys) do
    local x, y, z = unkey(k)
    if is_up_capable(tiles[k].shape) then
      -- Follow the shaft up until a window level, a break, or the limit.
      local found
      for dz = 1, DATA.max_shaft_levels do
        local uk = key(x, y, z + dz)
        local ut = tiles[uk]
        if ut then
          if walk[uk] and is_down_capable(ut.shape) then found = { uk, dz } end
          break
        end
        local t = world.read_tile(x, y, z + dz)
        if not t or t.hidden then break end
        if t.shape == "STAIR_DOWN" then
          -- Reached the bottom of a shaft level that is not in the window.
          break
        elseif t.shape ~= "STAIR_UPDOWN" then
          break
        end
      end
      if found then
        vlink(k, found[1], "certain", found[2])
        linked[k], linked[found[1]] = true, true
      end
    end
  end
  for _, k in ipairs(stair_keys) do
    if not linked[k] then
      local sh = tiles[k].shape
      -- A stair end with no partner inside the window or shaft reach.
      unk(string.format("a %s stair landing has no matching stair in the window or its shaft",
        sh == "STAIR_UP" and "up" or (sh == "STAIR_DOWN" and "down" or "up/down")))
    end
  end

  local ramp_keys = {}
  for k in pairs(walk) do
    if tiles[k].shape == "RAMP" then ramp_keys[#ramp_keys + 1] = k end
  end
  table.sort(ramp_keys)
  for _, k in ipairs(ramp_keys) do
    local x, y, z = unkey(k)
    local top = tiles[key(x, y, z + 1)]
    if top and top.shape == "RAMP_TOP" then
      local any = false
      for dy = -1, 1 do
        for dx = -1, 1 do
          if dx ~= 0 or dy ~= 0 then
            local nk = key(x + dx, y + dy, z + 1)
            if walk[nk] and tiles[nk].shape ~= "RAMP" then
              vlink(k, nk, "inferred", 1)
              any = true
            end
          end
        end
      end
      if not any then unk("a ramp has no standable tile above its slope in the window") end
    else
      unk("a ramp's upper level is not in the window or does not show a ramp top")
    end
  end

  -- Nodes --------------------------------------------------------------------
  local owner = {}
  local counters = {}
  local function new_node(kind, id, fields)
    local n = fields or {}
    n.kind = kind
    n.id = id
    n.tiles = n.tiles or {}
    n.edges = {}
    g.nodes[id] = n
    g.node_order[#g.node_order + 1] = id
    return n
  end
  local function seq(prefix)
    counters[prefix] = (counters[prefix] or 0) + 1
    return prefix .. "-" .. counters[prefix]
  end
  local function claim(n, k)
    owner[k] = n.id
    n.tiles[#n.tiles + 1] = k
  end

  -- Rooms: larger zones first so a smaller zone inside one wins its tiles.
  local zones = {}
  for _, zn in ipairs(world.zones or {}) do
    if is_room_zone(zn) then zones[#zones + 1] = zn end
  end
  table.sort(zones, function(a, b)
    local aa = (a.x2 - a.x1 + 1) * (a.y2 - a.y1 + 1)
    local ab = (b.x2 - b.x1 + 1) * (b.y2 - b.y1 + 1)
    if aa ~= ab then return aa > ab end
    return tostring(a.id) < tostring(b.id)
  end)
  local room_nodes_by_zone = {}
  for _, zn in ipairs(zones) do
    local id = "room-" .. tostring(zn.id)
    local n = new_node("room", id, {
      name = room_label(zn), room_kind = zn.kind, zone_id = zn.id,
      private = DATA.private_kinds[zn.kind] == true, z = zn.z,
    })
    room_nodes_by_zone[zn.id] = n
    for y = zn.y1, zn.y2 do
      for x = zn.x1, zn.x2 do
        local k = key(x, y, zn.z)
        if walk[k] then
          -- take the tile from any earlier (larger) zone
          local prev = owner[k]
          if prev then
            local pn = g.nodes[prev]
            for i, tk in ipairs(pn.tiles) do
              if tk == k then table.remove(pn.tiles, i) break end
            end
          end
          claim(n, k)
        end
      end
    end
  end
  for _, id in ipairs(g.node_order) do
    local n = g.nodes[id]
    if #n.tiles == 0 then
      unk(string.format("%s has no walkable tile in the window and is left out of the walk checks", n.name))
    end
  end

  -- Stair and ramp landings (tiles with vertical links), unless in a room.
  local vkeys = {}
  for k in pairs(vlinks) do vkeys[#vkeys + 1] = k end
  table.sort(vkeys)
  local stair_counter = 0
  for _, k in ipairs(vkeys) do
    if not owner[k] then
      local sh = tiles[k].shape
      local isstair = sh == "STAIR_UP" or sh == "STAIR_DOWN" or sh == "STAIR_UPDOWN"
      local id
      local n
      if isstair then
        stair_counter = stair_counter + 1
        id = "stair-" .. stair_counter
        n = new_node("stair", id, { name = "Stair " .. stair_counter, z = select(3, unkey(k)) })
      else
        id = seq("ramp")
        n = new_node("ramp", id, { name = "Ramp " .. id:match("%d+$"), z = select(3, unkey(k)) })
      end
      claim(n, k)
    end
  end

  -- Landmarks: footprint walkable tiles, else the walkable tiles beside it.
  local lms = {}
  for _, lm in ipairs(world.landmarks or {}) do lms[#lms + 1] = lm end
  table.sort(lms, function(a, b) return tostring(a.id) < tostring(b.id) end)
  for _, lm in ipairs(lms) do
    if levels_seen[lm.z] then
      local foot = {}
      for y = lm.y1, lm.y2 do
        for x = lm.x1, lm.x2 do
          local k = key(x, y, lm.z)
          if walk[k] then foot[#foot + 1] = k end
        end
      end
      if #foot == 0 then
        for y = lm.y1, lm.y2 do
          for x = lm.x1, lm.x2 do
            for _, d in ipairs(NBR) do
              local nk = key(x, y, lm.z) + d
              if walk[nk] then foot[#foot + 1] = nk end
            end
          end
        end
      end
      local free, aliased = {}, nil
      for _, k in ipairs(foot) do
        local o = owner[k]
        if o == nil then free[#free + 1] = k
        elseif g.nodes[o].kind == "room" then aliased = aliased or o end
      end
      if #free > 0 then
        local n = new_node("landmark", "lm-" .. tostring(lm.id), {
          name = lm.name, landmark_kind = lm.kind, z = lm.z,
        })
        for _, k in ipairs(free) do
          if not owner[k] then claim(n, k) end
        end
      elseif aliased then
        local rn = g.nodes[aliased]
        rn.aliases = rn.aliases or {}
        table.insert(rn.aliases, lm.name)
      else
        unk(string.format("landmark %s has no standable tile at or beside it in the window", lm.name))
      end
    end
  end

  -- Circulation tiles: walkable, unowned.
  local function circ(k) return walk[k] and owner[k] == nil end

  -- Width: the largest N in 1..open_area_min_width with an NxN block of open
  -- (walkable, not room) tiles containing the tile.
  local function open_tile(k) return walk[k] and (owner[k] == nil or g.nodes[owner[k]].kind ~= "room") end
  local function block_ok(x0, y0, z, n)
    for dy = 0, n - 1 do
      for dx = 0, n - 1 do
        if not open_tile(key(x0 + dx, y0 + dy, z)) then return false end
      end
    end
    return true
  end
  local twidth = {}
  local circ_keys = {}
  for k in pairs(walk) do
    if circ(k) then circ_keys[#circ_keys + 1] = k end
  end
  table.sort(circ_keys)
  for _, k in ipairs(circ_keys) do
    local x, y, z = unkey(k)
    local best = 1
    for n = 2, DATA.open_area_min_width do
      local found = false
      for oy = 0, n - 1 do
        for ox = 0, n - 1 do
          if block_ok(x - ox, y - oy, z, n) then found = true break end
        end
        if found then break end
      end
      if found then best = n else break end
    end
    twidth[k] = best
  end

  -- Open areas: connected comps of wide tiles.
  local seen = {}
  for _, k in ipairs(circ_keys) do
    if twidth[k] >= DATA.open_area_min_width and not seen[k] and not owner[k] then
      local n = new_node("open_area", seq("open"), { z = select(3, unkey(k)) })
      n.name = "Open area " .. n.id:match("%d+$")
      local stack = { k }
      seen[k] = true
      while #stack > 0 do
        local c = table.remove(stack)
        claim(n, c)
        for _, d in ipairs(NBR) do
          local nk = c + d
          if circ(nk) and not seen[nk] and twidth[nk] and twidth[nk] >= DATA.open_area_min_width then
            seen[nk] = true
            stack[#stack + 1] = nk
          end
        end
      end
    end
  end

  -- Degree helper (4 neighbours plus vertical links).
  local function degree(k)
    local d = 0
    for _, o in ipairs(NBR) do if walk[k + o] then d = d + 1 end end
    d = d + #(vlinks[k] or {})
    return d
  end
  local function frontier_tile(k)
    for _, o in ipairs(NBR) do
      local t = tiles[k + o]
      if t == nil or t.hidden or t.unread then return true end
    end
    return false
  end

  -- Frontiers and dead ends.
  for _, k in ipairs(circ_keys) do
    if not owner[k] then
      if frontier_tile(k) then
        local n = new_node("frontier", seq("frontier"), { z = select(3, unkey(k)) })
        n.name = "Window edge " .. n.id:match("%d+$")
        claim(n, k)
      elseif degree(k) <= 1 then
        local n = new_node("dead_end", seq("dead"), { z = select(3, unkey(k)) })
        n.name = "Dead end " .. n.id:match("%d+$")
        claim(n, k)
      end
    end
  end

  -- Thin junction tiles: a width-1 corridor tile with three or more ways on.
  for _, k in ipairs(circ_keys) do
    if not owner[k] and twidth[k] == 1 and degree(k) >= 3 then
      local n = new_node("junction", seq("junc"), { z = select(3, unkey(k)) })
      n.name = "Junction " .. n.id:match("%d+$")
      local stack = { k }
      claim(n, k)
      while #stack > 0 do
        local c = table.remove(stack)
        for _, d in ipairs(NBR) do
          local nk = c + d
          if circ(nk) and not owner[nk] and twidth[nk] == 1 and degree(nk) >= 3 then
            claim(n, nk)
            stack[#stack + 1] = nk
          end
        end
      end
    end
  end

  -- Plain runs ---------------------------------------------------------------
  local edge_count = 0
  local function new_edge(a, b, fields)
    edge_count = edge_count + 1
    local e = fields or {}
    e.id = "e" .. edge_count
    e.a, e.b = a, b
    g.edges[#g.edges + 1] = e
    table.insert(g.nodes[a].edges, e)
    if b ~= a then table.insert(g.nodes[b].edges, e) end
    return e
  end

  local function bfs_in(set, sources)
    local dist, queue, head = {}, {}, 1
    for _, s in ipairs(sources) do dist[s] = 1; queue[#queue + 1] = s end
    while head <= #queue do
      local c = queue[head]; head = head + 1
      for _, o in ipairs(NBR) do
        local nk = c + o
        if set[nk] and not dist[nk] then
          dist[nk] = dist[c] + 1
          queue[#queue + 1] = nk
        end
      end
    end
    return dist
  end

  local run_seen = {}
  local pair_open = {}   -- direct adjacency aggregation: "a|b" -> edge
  for _, k in ipairs(circ_keys) do
    if circ(k) and not run_seen[k] then
      local run, set, stack = {}, {}, { k }
      run_seen[k] = true
      while #stack > 0 do
        local c = table.remove(stack)
        run[#run + 1] = c
        set[c] = true
        for _, o in ipairs(NBR) do
          local nk = c + o
          if circ(nk) and not run_seen[nk] then
            run_seen[nk] = true
            stack[#stack + 1] = nk
          end
        end
      end
      -- contacts: node id -> contact tiles in the run
      local contacts, corder = {}, {}
      for _, c in ipairs(run) do
        for _, o in ipairs(NBR) do
          local own = owner[c + o]
          if own then
            if not contacts[own] then contacts[own] = {}; corder[#corder + 1] = own end
            local list = contacts[own]
            if list[#list] ~= c then list[#list + 1] = c end
          end
        end
      end
      table.sort(corder)
      local minw = 99
      local run_doors = {}
      for _, c in ipairs(run) do
        minw = math.min(minw, twidth[c] or 1)
        if door[c] then run_doors[#run_doors + 1] = { tile = c, door = door[c] } end
      end
      local function doors_out(list)
        local out = {}
        for _, d in ipairs(list) do
          out[#out + 1] = { state = d.door.forbidden and "forbidden" or "usable" }
        end
        return out
      end
      local dists = {}
      for _, nid in ipairs(corder) do dists[nid] = bfs_in(set, contacts[nid]) end
      local z = select(3, unkey(run[1]))
      if #corder == 0 then
        unk("a stretch of walkable corridor touches no known node")
      elseif #corder == 1 then
        -- a loop back to the same node: carries no new connection
      elseif #corder == 2 then
        local a, b = corder[1], corder[2]
        local best
        for _, c in ipairs(run) do
          local da, db = dists[a][c], dists[b][c]
          if da and db and (not best or da + db < best) then best = da + db end
        end
        if best then
          new_edge(a, b, { kind = "segment", steps = best, width = minw, doors = doors_out(run_doors),
                           dz = 0, certainty = "certain", z = z })
        end
      else
        -- three or more nodes meet in this run: a junction at the best tile.
        local jn = new_node("junction", seq("junc"), { z = z })
        jn.name = "Junction " .. jn.id:match("%d+$")
        local bestk, bestscore
        for _, c in ipairs(run) do
          local worst, ok = 0, true
          for _, nid in ipairs(corder) do
            local d = dists[nid][c]
            if not d then ok = false break end
            worst = math.max(worst, d)
          end
          if ok and (not bestscore or worst < bestscore) then bestk, bestscore = c, worst end
        end
        jn.tiles = { bestk }
        for _, nid in ipairs(corder) do
          local mine = {}
          for _, d in ipairs(run_doors) do
            local best, bestn
            for _, other in ipairs(corder) do
              local dd = dists[other][d.tile]
              if dd and (not best or dd < best) then best, bestn = dd, other end
            end
            if bestn == nid then mine[#mine + 1] = d end
          end
          new_edge(nid, jn.id, { kind = "segment", steps = dists[nid][bestk] or 1, width = minw,
                                 doors = doors_out(mine), dz = 0, certainty = "certain", z = z,
                                 via_junction = true })
        end
      end
    end
  end

  -- Direct adjacency between two different nodes (no plain tile between).
  local owner_keys = {}
  for k in pairs(owner) do owner_keys[#owner_keys + 1] = k end
  table.sort(owner_keys)
  for _, k in ipairs(owner_keys) do
    for _, o in ipairs({ 1, 1024 }) do
      local nk = k + o
      local a, b = owner[k], owner[nk]
      if a and b and a ~= b then
        if a > b then a, b = b, a end
        local pk = a .. "|" .. b
        local e = pair_open[pk]
        if not e then
          e = new_edge(a, b, { kind = "opening", steps = 1, width = 0, doors = {}, dz = 0,
                               certainty = "certain", z = g.nodes[a].z })
          pair_open[pk] = e
        end
        e.width = e.width + 1
        if door[k] then table.insert(e.doors, { state = door[k].forbidden and "forbidden" or "usable" }) end
        if door[nk] then table.insert(e.doors, { state = door[nk].forbidden and "forbidden" or "usable" }) end
      end
    end
  end

  -- Vertical edges at node level.
  local vseen = {}
  local vk_sorted = {}
  for k in pairs(vlinks) do vk_sorted[#vk_sorted + 1] = k end
  table.sort(vk_sorted)
  for _, k in ipairs(vk_sorted) do
    for _, vl in ipairs(vlinks[k]) do
      if vl.dz > 0 then
        local a, b = owner[k], owner[vl.to]
        if a and b then
          local vk = a .. "|" .. b .. "|" .. vl.certainty
          if not vseen[vk] then
            vseen[vk] = true
            new_edge(a, b, { kind = "vertical", steps = vl.dz, width = 1, doors = {}, dz = vl.dz,
                             certainty = vl.certainty })
          end
        elseif a or b then
          unk("a vertical link ends on a tile that belongs to no node")
        end
      end
    end
  end

  g.vlinks, g.owner = vlinks, owner
  g.twidth = twidth

  -- Walk groups for agreement ------------------------------------------------
  if world.group_at then
    for _, id in ipairs(g.node_order) do
      local n = g.nodes[id]
      local k = n.tiles[1]
      if k then
        local x, y, z = unkey(k)
        n.group = world.group_at(x, y, z)
      end
    end
  end

  g.notes = {
    "movement is orthogonal; diagonal squeezes and liquids are not modelled",
    "steps are tile steps inside the window; a stair or ramp counts as one step per level",
    "the game's walkable-group cache only updates while the game is unpaused; on a paused fort a group disagreement may be stale",
    "the window is built from our own records only; places outside it are not described",
  }
  return g
end

-- ---------------------------------------------------------------------------
-- Tile BFS (walk numbers and walk paths)
-- ---------------------------------------------------------------------------
local function tile_bfs(g, sources, want_parent, stop_set)
  local dist, parent, queue, head = {}, want_parent and {} or nil, {}, 1
  for _, s in ipairs(sources) do
    if not dist[s] then dist[s] = 0; queue[#queue + 1] = s end
  end
  while head <= #queue do
    local c = queue[head]; head = head + 1
    if stop_set and stop_set[c] then return dist, parent, c end
    local d = dist[c] + 1
    for _, o in ipairs(NBR) do
      local nk = c + o
      if g.walk[nk] and not dist[nk] then
        dist[nk] = d
        if parent then parent[nk] = c end
        queue[#queue + 1] = nk
      end
    end
    for _, vl in ipairs(g.vlinks[c] or {}) do
      local nk = vl.to
      if not dist[nk] then
        dist[nk] = d
        if parent then parent[nk] = c end
        queue[#queue + 1] = nk
      end
    end
  end
  return dist, parent, nil
end

local function node_tiles(g, id)
  local n = g.nodes[id]
  local out = {}
  for _, k in ipairs(n.tiles) do out[#out + 1] = k end
  return out
end

local function level_of(g, n) return (n.z or g.minz) - g.minz end

-- ---------------------------------------------------------------------------
-- Checks
-- ---------------------------------------------------------------------------
local function node_adjacency(g)
  local adj = {}
  for _, id in ipairs(g.node_order) do adj[id] = {} end
  for _, e in ipairs(g.edges) do
    table.insert(adj[e.a], { to = e.b, edge = e })
    if e.a ~= e.b then table.insert(adj[e.b], { to = e.a, edge = e }) end
  end
  return adj
end

local function is_room(g, id) return g.nodes[id].kind == "room" end

-- Rooms whose shortest access to a non-room node crosses other rooms.
local function rooms_through_rooms(g, adj)
  local cost, parent, done = {}, {}, {}
  for _, id in ipairs(g.node_order) do
    if not is_room(g, id) then cost[id] = 0 end
  end
  while true do
    local best, bid
    for _, id in ipairs(g.node_order) do
      if cost[id] and not done[id] and (not best or cost[id] < best) then best, bid = cost[id], id end
    end
    if not bid then break end
    done[bid] = true
    for _, a in ipairs(adj[bid]) do
      if is_room(g, a.to) then
        local c = cost[bid] + 1
        if not cost[a.to] or c < cost[a.to] then cost[a.to] = c; parent[a.to] = bid end
      end
    end
  end
  local rows, no_access = {}, {}
  for _, id in ipairs(g.node_order) do
    if is_room(g, id) then
      local n = g.nodes[id]
      if not cost[id] then
        no_access[#no_access + 1] = { room = n.name, room_kind = n.room_kind }
      elseif cost[id] >= 2 then
        local through, crosses_private = {}, false
        local cur = parent[id]
        while cur and is_room(g, cur) do
          local cn = g.nodes[cur]
          through[#through + 1] = { room = cn.name, room_kind = cn.room_kind, private = cn.private }
          if cn.private then crosses_private = true end
          cur = parent[cur]
        end
        rows[#rows + 1] = {
          room = n.name, room_kind = n.room_kind, private = n.private,
          rooms_crossed = cost[id] - 1, through = through, crosses_private_room = crosses_private,
        }
      end
    end
  end
  return rows, no_access
end

-- Bridges and articulation points (Tarjan, recursive; graphs here are small).
local function bridges_and_cuts(g, adj)
  local disc, low, bridges, cuts = {}, {}, {}, {}
  local time = 0
  local function dfs(u, pedge)
    time = time + 1
    disc[u], low[u] = time, time
    local children = 0
    for _, a in ipairs(adj[u]) do
      if a.edge ~= pedge and a.to ~= u then
        if disc[a.to] then
          low[u] = math.min(low[u], disc[a.to])
        else
          children = children + 1
          dfs(a.to, a.edge)
          low[u] = math.min(low[u], low[a.to])
          if low[a.to] > disc[u] then bridges[#bridges + 1] = a.edge end
          if pedge ~= nil and low[a.to] >= disc[u] then cuts[u] = true end
        end
      end
    end
    if pedge == nil and children > 1 then cuts[u] = true end
  end
  for _, id in ipairs(g.node_order) do
    if not disc[id] then dfs(id, nil) end
  end
  return bridges, cuts
end

-- Component id per node, ignoring one edge and/or one node.
local function components(g, adj, skip_edge, skip_node)
  local comp, n = {}, 0
  for _, id in ipairs(g.node_order) do
    if not comp[id] and id ~= skip_node then
      n = n + 1
      comp[id] = n
      local stack = { id }
      while #stack > 0 do
        local c = table.remove(stack)
        for _, a in ipairs(adj[c]) do
          if a.edge ~= skip_edge and a.to ~= skip_node and not comp[a.to] then
            comp[a.to] = n
            stack[#stack + 1] = a.to
          end
        end
      end
    end
  end
  return comp, n
end

local function is_anchor(g, n)
  if n.kind == "landmark" or n.kind == "stair" then return true end
  if n.kind == "room" and DATA.anchor_room_kinds[n.room_kind] then return true end
  return false
end

local function side_summary(g, comp, which)
  local anchors, kinds = {}, {}
  for _, id in ipairs(g.node_order) do
    if comp[id] == which then
      local n = g.nodes[id]
      if is_anchor(g, n) then anchors[#anchors + 1] = n.name end
      if n.kind == "room" then kinds[n.room_kind] = (kinds[n.room_kind] or 0) + 1 end
    end
  end
  table.sort(anchors)
  return { anchors = anchors, rooms_by_kind = kinds }
end

local function edge_brief(g, e)
  local doors = {}
  for _, d in ipairs(e.doors or {}) do doors[#doors + 1] = d.state end
  return {
    id = e.id, kind = e.kind, a = e.a, b = e.b, steps = e.steps,
    width_class = e.kind == "vertical" and "stair" or width_class(e.width or 1),
    min_width = e.width, level_change = e.dz, doors = doors, certainty = e.certainty,
    via_junction = e.via_junction,
  }
end

-- ---------------------------------------------------------------------------
-- Report (model-facing: ids, kinds, names, numbers only)
-- ---------------------------------------------------------------------------
local function endpoint_names(g)
  local names, ids = {}, {}
  for _, id in ipairs(g.node_order) do
    local n = g.nodes[id]
    if n.kind == "room" or n.kind == "landmark" or n.kind == "stair" then
      names[#names + 1] = n.name
      ids[#ids + 1] = id
    end
    if n.aliases then
      for _, a in ipairs(n.aliases) do names[#names + 1] = a; ids[#ids + 1] = id end
    end
  end
  return names, ids
end

local function resolve_endpoint(g, query)
  local names, ids = endpoint_names(g)
  local idx, err = textutil.match_name(query, names)
  if not idx then return nil, err end
  return ids[idx]
end

local function walk_numbers(g)
  local sources = {}
  for _, id in ipairs(g.node_order) do
    local n = g.nodes[id]
    if n.kind == "room" and #n.tiles > 0 then
      for _, sk in ipairs(DATA.walk_source_kinds) do
        if n.room_kind == sk then sources[#sources + 1] = id end
      end
    end
  end
  local fields = {}
  for _, t in ipairs(DATA.walk_targets) do fields[#fields + 1] = t.label end

  local dists = {}
  for _, t in ipairs(DATA.walk_targets) do
    local srcs = {}
    for _, id in ipairs(g.node_order) do
      local n = g.nodes[id]
      local hit = (t.room_kind and n.kind == "room" and n.room_kind == t.room_kind)
        or (t.landmark_kind and n.kind == "landmark" and n.landmark_kind == t.landmark_kind)
        or (t.vertical and (n.kind == "stair" or n.kind == "ramp"))
      if hit then
        for _, k in ipairs(n.tiles) do srcs[#srcs + 1] = k end
      end
    end
    if #srcs > 0 then dists[t.label] = (tile_bfs(g, srcs)) else dists[t.label] = false end
  end

  local rows = {}
  local per = {}
  for _, id in ipairs(sources) do
    local n = g.nodes[id]
    local row = { room = n.name, room_kind = n.room_kind }
    for _, t in ipairs(DATA.walk_targets) do
      local d = dists[t.label]
      local best
      if d then
        for _, k in ipairs(n.tiles) do
          if d[k] and (not best or d[k] < best) then best = d[k] end
        end
      end
      row[t.label .. "_steps"] = best
      row["has_" .. t.label] = d ~= false
      per[n.room_kind] = per[n.room_kind] or {}
      per[n.room_kind][t.label] = per[n.room_kind][t.label] or { values = {}, unreachable = 0 }
      if best then table.insert(per[n.room_kind][t.label].values, best)
      else per[n.room_kind][t.label].unreachable = per[n.room_kind][t.label].unreachable + 1 end
    end
    rows[#rows + 1] = row
  end
  local summary = {}
  for kind, labels in pairs(per) do
    summary[kind] = { rooms = 0 }
    for _, id in ipairs(sources) do
      if g.nodes[id].room_kind == kind then summary[kind].rooms = summary[kind].rooms + 1 end
    end
    for label, rec in pairs(labels) do
      local vals = rec.values
      local mn, mx
      for _, v in ipairs(vals) do
        mn = mn and math.min(mn, v) or v
        mx = mx and math.max(mx, v) or v
      end
      summary[kind][label] = { min = mn, median = median(vals), max = mx,
                               rooms_reaching = #vals, rooms_not_reaching = rec.unreachable }
    end
  end
  return rows, summary
end

function summarize(g)
  local adj = node_adjacency(g)
  local report = {}

  local by_kind = {}
  for _, id in ipairs(g.node_order) do
    local k = g.nodes[id].kind
    by_kind[k] = (by_kind[k] or 0) + 1
  end
  local vertical_edges, maxlevel = 0, 0
  for _, e in ipairs(g.edges) do
    if e.kind == "vertical" then vertical_edges = vertical_edges + 1 end
  end
  for _, id in ipairs(g.node_order) do maxlevel = math.max(maxlevel, level_of(g, g.nodes[id])) end

  report.window = {
    windows = g.window_count, levels = g.level_count, tile_count = g.window_tiles, tile_cap = g.cap,
    hidden_tiles = g.hidden_tiles, unreadable_tiles = g.unreadable_tiles,
    landmarks_outside_window = g.outside_landmarks,
  }
  report.counts = { nodes = #g.node_order, edges = #g.edges, vertical_edges = vertical_edges,
                    nodes_by_kind = by_kind }

  -- nodes
  local nodes = {}
  local omit_junctions = #g.node_order > DATA.max_nodes_listed
  for _, id in ipairs(g.node_order) do
    local n = g.nodes[id]
    if not (omit_junctions and (n.kind == "junction" or n.kind == "frontier")) then
      nodes[#nodes + 1] = {
        id = id, kind = n.kind, name = n.name, room_kind = n.room_kind, private = n.private,
        landmark_kind = n.landmark_kind, level = level_of(g, n), also_named = n.aliases,
      }
    end
  end
  report.nodes = nodes
  report.nodes_listed_in_full = not omit_junctions

  local edges = {}
  for _, e in ipairs(g.edges) do
    if #edges < DATA.max_edges_listed then edges[#edges + 1] = edge_brief(g, e) end
  end
  report.edges = edges
  report.edges_listed_in_full = #g.edges <= DATA.max_edges_listed

  -- checks
  local through, no_access = rooms_through_rooms(g, adj)
  local private_through = 0
  for _, r in ipairs(through) do if r.crosses_private_room then private_through = private_through + 1 end end

  local openings = {}
  for _, e in ipairs(g.edges) do
    if e.kind ~= "vertical" and is_room(g, e.a) and is_room(g, e.b) then
      local a, b = g.nodes[e.a], g.nodes[e.b]
      openings[#openings + 1] = {
        rooms = { a.name, b.name }, kinds = { a.room_kind, b.room_kind },
        both_private = a.private and b.private or false, steps = e.steps,
      }
    end
  end

  local dead = {}
  for _, id in ipairs(g.node_order) do
    local n = g.nodes[id]
    if n.kind == "dead_end" and n.edges[1] then
      local e = n.edges[1]
      local other = e.a == id and e.b or e.a
      local on = g.nodes[other]
      dead[#dead + 1] = {
        node = id, leads_from = on.name or on.id, leads_from_kind = on.room_kind or on.kind,
        steps = e.steps, width_class = width_class(e.width or 1),
      }
    end
  end

  local bridges, cuts = bridges_and_cuts(g, adj)
  local spof, leaf_bridges = {}, 0
  for _, e in ipairs(bridges) do
    local comp = components(g, adj, e, nil)
    local ca, cb = comp[e.a], comp[e.b]
    local sa, sb = side_summary(g, comp, ca), side_summary(g, comp, cb)
    if #sa.anchors > 0 and #sb.anchors > 0 then
      local br = edge_brief(g, e)
      br.side_a = sa
      br.side_b = sb
      br.joins = { g.nodes[e.a].name or e.a, g.nodes[e.b].name or e.b }
      spof[#spof + 1] = br
    else
      leaf_bridges = leaf_bridges + 1
    end
  end
  local cut_rows = {}
  for _, id in ipairs(sorted_keys(cuts)) do
    local n = g.nodes[id]
    do
      local comp, count = components(g, adj, nil, id)
      local anchored = 0
      for c = 1, count do
        for _, oid in ipairs(g.node_order) do
          if comp[oid] == c and is_anchor(g, g.nodes[oid]) then anchored = anchored + 1 break end
        end
      end
      if anchored >= 2 then
        cut_rows[#cut_rows + 1] = { node = id, kind = n.kind, name = n.name,
                                    anchored_pieces_if_removed = anchored }
      end
    end
  end

  local comp, ccount = components(g, adj, nil, nil)
  local csize = {}
  for _, id in ipairs(g.node_order) do csize[comp[id]] = (csize[comp[id]] or 0) + 1 end
  local main, mainsize = nil, -1
  for c = 1, ccount do if csize[c] > mainsize then main, mainsize = c, csize[c] end end
  local comp_rows = {}
  for c = 1, ccount do
    if c ~= main then
      local named = {}
      for _, id in ipairs(g.node_order) do
        local n = g.nodes[id]
        if comp[id] == c and (n.kind == "room" or n.kind == "landmark" or n.kind == "stair") then
          named[#named + 1] = n.name
        end
      end
      comp_rows[#comp_rows + 1] = { nodes = csize[c], named = named }
    end
  end

  -- group agreement
  local comp_groups, multi, sharing = {}, 0, 0
  local group_comps = {}
  local no_group = 0
  for _, id in ipairs(g.node_order) do
    local n = g.nodes[id]
    if n.group == nil then
      no_group = no_group + 1
    elseif n.group ~= 0 then
      comp_groups[comp[id]] = comp_groups[comp[id]] or {}
      comp_groups[comp[id]][n.group] = true
      group_comps[n.group] = group_comps[n.group] or {}
      group_comps[n.group][comp[id]] = true
    end
  end
  for _, gs in pairs(comp_groups) do
    local c = 0
    for _ in pairs(gs) do c = c + 1 end
    if c > 1 then multi = multi + 1 end
  end
  for _, cs in pairs(group_comps) do
    local c = 0
    for _ in pairs(cs) do c = c + 1 end
    if c > 1 then sharing = sharing + 1 end
  end

  local rows, wsum = walk_numbers(g)
  local shown_rows = {}
  for i, r in ipairs(rows) do
    if i <= DATA.max_rows then shown_rows[#shown_rows + 1] = r end
  end

  report.checks = {
    rooms_through_rooms = through,
    rooms_with_no_public_access = no_access,
    private_rooms_opening_onto_each_other = openings,
    dead_ends = dead,
    single_points_of_failure = spof,
    articulation_points = cut_rows,
    disconnected_pieces = comp_rows,
    group_agreement = {
      graph_pieces_spanning_several_game_groups = multi,
      game_groups_spanning_several_graph_pieces = sharing,
      nodes_without_a_group_reading = no_group,
    },
  }
  report.flags = {
    room_reached_only_through_another_room = #through > 0,
    private_room_reached_only_through_a_private_room = private_through > 0,
    private_rooms_open_onto_each_other = (function()
      for _, o in ipairs(openings) do if o.both_private then return true end end
      return false
    end)(),
    dead_end_present = #dead > 0,
    single_point_of_failure_between_anchors = #spof > 0,
    graph_in_one_piece = ccount <= 1,
    has_unknowns = #g.unknown > 0,
  }
  report.counts.rooms_through_rooms = #through
  report.counts.private_rooms_through_private_rooms = private_through
  report.counts.leaf_bridges_not_listed = leaf_bridges
  report.walks = { rows = shown_rows, rows_total = #rows, by_room_kind = wsum }
  report.unknown = g.unknown
  report.notes = g.notes
  return report
end

-- Walk between two named endpoints.
function walk_between(g, from_name, to_name)
  local a, aerr = resolve_endpoint(g, from_name)
  if not a then return { status = "unknown", reason = aerr } end
  local b, berr = resolve_endpoint(g, to_name)
  if not b then return { status = "unknown", reason = berr } end
  local srcs, dst = node_tiles(g, a), {}
  for _, k in ipairs(g.nodes[b].tiles) do dst[k] = true end
  if #srcs == 0 or next(dst) == nil then
    return { status = "unknown", reason = "an endpoint has no walkable tile in the window" }
  end
  local dist, parent, hit = tile_bfs(g, srcs, true, dst)
  if not hit then
    return { status = "unreachable_in_window", from = g.nodes[a].name, to = g.nodes[b].name,
             note = "no walk inside the window; the game's own connectivity.check covers outside it" }
  end
  local via, last = {}, nil
  local doors, minw = 0, 99
  local c = hit
  local path = {}
  while c do path[#path + 1] = c; c = parent[c] end
  for i = #path, 1, -1 do
    local k = path[i]
    local o = g.owner[k]
    if o and o ~= last then
      via[#via + 1] = { node = o, kind = g.nodes[o].kind, name = g.nodes[o].name }
      last = o
    end
    if g.door[k] then doors = doors + 1 end
    if g.twidth[k] then minw = math.min(minw, g.twidth[k]) end
  end
  local rooms_crossed = 0
  for i, v in ipairs(via) do
    if v.kind == "room" and v.node ~= a and v.node ~= b then rooms_crossed = rooms_crossed + 1 end
  end
  return {
    status = "reachable", from = g.nodes[a].name, to = g.nodes[b].name,
    steps = dist[hit], doors_on_path = doors, rooms_walked_through = rooms_crossed,
    narrowest = minw < 99 and width_class(minw) or nil, via = via,
  }
end

-- ---------------------------------------------------------------------------
-- Live world
-- ---------------------------------------------------------------------------
local function live_world()
  local w = { sites = {}, reservations = {}, zones = {}, landmarks = {} }
  local errs = {}

  local ok, bp = pcall(reqscript, 'df-overseer-blueprint')
  if ok and bp and bp.all_sites_raw then
    for _, s in ipairs(bp.all_sites_raw()) do
      w.sites[#w.sites + 1] = { id = s.handle, kind = s.blueprint, x = s.x, y = s.y, z = s.z, w = s.w, h = s.h }
    end
  else
    errs[#errs + 1] = "could not read blueprint sites"
  end
  local okr, rs = pcall(reqscript, 'df-overseer-reservations')
  if okr and rs and rs.list_raw then
    for _, r in ipairs(rs.list_raw()) do
      w.reservations[#w.reservations + 1] = { id = r.handle, x = r.x, y = r.y, z = r.z, w = r.w, h = r.h }
    end
  else
    errs[#errs + 1] = "could not read reservations"
  end

  local okz, zv = pcall(function() return df.global.world.buildings.other.ACTIVITY_ZONE end)
  if okz and zv then
    for i = 0, #zv - 1 do
      local z = zv[i]
      local okk, kind = pcall(function() return df.civzone_type[z.type] end)
      if okk and type(kind) == "string" and DATA.room_zone_kinds[kind] then
        local name = ""
        local okn, nm = pcall(function() return z.name end)
        if okn and type(nm) == "string" then name = textutil.to_utf8(nm) end
        w.zones[#w.zones + 1] = { id = z.id, kind = kind, name = name,
          x1 = z.x1, y1 = z.y1, x2 = z.x2, y2 = z.y2, z = z.z }
      end
    end
  else
    errs[#errs + 1] = "could not read zones"
  end

  local okb, all = pcall(function() return df.global.world.buildings.all end)
  if okb and all then
    for _, bld in ipairs(all) do
      local okt, kind = pcall(function() return df.building_type[bld:getType()] end)
      if okt and DATA.landmark_building_kinds[kind] then
        local okn, name = pcall(dfhack.buildings.getName, bld)
        if okn and name and name ~= '' then
          w.landmarks[#w.landmarks + 1] = { id = bld.id, name = textutil.to_utf8(name), kind = kind,
            x1 = bld.x1, y1 = bld.y1, x2 = bld.x2, y2 = bld.y2, z = bld.z }
        end
      end
    end
  end

  local door_type = df.building_type.Door
  w.read_tile = function(x, y, z)
    local blk = dfhack.maps.getTileBlock(x, y, z)
    if not blk then return nil end
    local lx, ly = x % 16, y % 16
    local des = blk.designation[lx][ly]
    if des.hidden then return { hidden = true } end
    local tt = blk.tiletype[lx][ly]
    local shape = df.tiletype_shape[df.tiletype.attrs[tt].shape]
    local t = { shape = shape }
    if des.flow_size >= DATA.deep_liquid_size then t.deep = true end
    local occ = blk.occupancy[lx][ly].building
    if occ ~= 0 then
      local oname = df.tile_building_occ[occ]
      if DATA.blocked_occupancy[oname] then
        t.blocked = true
      elseif oname ~= "Planned" then
        local bld = dfhack.buildings.findAtTile(xyz2pos(x, y, z))
        if bld and bld:getType() == door_type then
          t.door = { id = bld.id, forbidden = bld.door_flags.forbidden and true or false }
        end
      end
    end
    return t
  end
  w.group_at = function(x, y, z)
    local okg, grp = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
    if okg then return grp end
    return nil
  end
  return w, errs
end

local function live_graph()
  local world, errs = live_world()
  local g, err = build_graph(world)
  if not g then return nil, err end
  for _, e in ipairs(errs) do g.unknown[#g.unknown + 1] = e end
  return g
end

function circulation_graph()
  local g, err = live_graph()
  if not g then return { ok = false, error = err } end
  local r = summarize(g)
  r.ok = true
  return r
end

function circulation_walk(from_name, to_name)
  local g, err = live_graph()
  if not g then return { ok = false, error = err } end
  local r = walk_between(g, from_name, to_name)
  r.ok = r.status == "reachable"
  return r
end

if dfhack_flags.module then
  return
end

local args = { ... }
local cmd = args[1]
if cmd == "graph" then
  print(json.encode(circulation_graph()))
elseif cmd == "walk" then
  if not args[2] or not args[3] then
    print("usage: df-overseer-circulation walk FROM TO")
  else
    print(json.encode(circulation_walk(args[2], args[3])))
  end
else
  print("usage: df-overseer-circulation <graph|walk FROM TO>")
end
