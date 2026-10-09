-- df-overseer-automine.lua
--@module = true
--
-- The game's own "automine" dig mode (research/2026-10-09-auto-mine.md,
-- decisions/DECISIONS.md 2026-10-09 "Auto mining"). A tile dug with
-- `tile_occupancy.dig_auto` set makes the game designate its revealed
-- neighbours of the same vein or cluster material for mining, so a vein our
-- digs touch is followed on its own. This leaf holds the three player-
-- equivalent actions around that, and nothing else:
--
--   mark / mark_rect  set dig_auto on the Default-dig tiles of a dig we just
--                     designated (blueprint apply, diggable dig call this).
--   scan [MAX]        the conductor's once-per-cycle pass: (1) the cavern
--                     reaction, (2) designate revealed ore or gem tiles that
--                     touch a tile we dug, Default dig plus dig_auto.
--   followed_checker  is this tile an auto-followed designation, not ours?
--
-- THE TRAP THIS RESPECTS. DFHack's own dig source: "Auto dig only works on
-- default dig designation. Setting dig_auto for any other designation prevents
-- dwarves from digging that tile at all." So the bit is only ever set where
-- `designation.dig == Default`, never on a channel, stair or ramp.
--
-- NO ARMOK (docs/ARMOK-RULINGS.md). A tile's `hidden` flag is read first and a
-- hidden tile is never decoded or designated; ore is found only on tiles a
-- player can already see. Designating a visible vein tile for mining and
-- clearing a designation are things a player does. Hazard bands are the same
-- ones `df-overseer-hazard` uses for every other dig.
--
-- NO COORDINATES LEAVE THIS FILE. Results are counts, mineral names and
-- reservation handles. The state file keeps tile keys on the guest only.
--
-- WHAT IS NOT PROVEN (research file, "Needs a live test"): that the bit on a
-- plain tile is harmless, the followed tiles' priority, whether a followed
-- tile beside damp stone is cancelled, and whether FEATURE_DISCOVERY carries a
-- usable `pos`. The cavern reaction therefore has a fallback for a report with
-- no position. First live use is a supervised read-only call.
--
-- All policy is data (POLICY).

local json = require('json')

POLICY = {
  -- Bounds of one scan call.
  max_per_call = 40,
  max_examined = 4000,
  -- Which vein kinds scan designates. decode_vein reads the game's own
  -- inorganic flags (isOre, isGem); this is only which of those we want.
  kinds = {ore = true, gem = true},
  -- Cavern reaction: clear auto designations within this many tiles (and
  -- cavern_z_radius levels) of a FEATURE_DISCOVERY report; with no usable
  -- position, within cavern_radius of the last `fallback_rects` dig records.
  cavern_radius = 10,
  cavern_z_radius = 2,
  fallback_rects = 3,
  -- Ledger bounds.
  max_rects = 64,
  max_marked_keys = 4000,
}

STATE_DIR = "dfhack-config/overseer-automine"
STATE_FILE = STATE_DIR .. "/state.json"

local TICKS_PER_YEAR = 403200
local MAX_REPORT_SCAN = 6000

local function abs_tick()
  local ok, y, t = pcall(function() return df.global.cur_year, df.global.cur_year_tick end)
  if not ok or y == nil then return 0 end
  return y * TICKS_PER_YEAR + t
end

-- ---------------------------------------------------------------------------
-- State. {rects = {{x1,y1,x2,y2,z,tick,kind}}, marked = {"x,y,z"}, last_report_abs}
-- kind "dig": a dig we issued (the tiles in `marked` are exactly the ones we
-- set auto on). kind "scan": a tile the scan designated.
-- ---------------------------------------------------------------------------

local function ensure_dir()
  if not dfhack.filesystem.isdir(STATE_DIR) then
    dfhack.filesystem.mkdir_recursive(STATE_DIR)
  end
end

local function load_state()
  local ok, data = pcall(json.decode_file, STATE_FILE)
  if not ok or type(data) ~= "table" then data = {} end
  data.rects = type(data.rects) == "table" and data.rects or {}
  data.marked = type(data.marked) == "table" and data.marked or {}
  if data.last_report_abs == nil then data.last_report_abs = abs_tick() end
  return data
end

local function save_state(state)
  local ok = pcall(function()
    ensure_dir()
    json.encode_file(state, STATE_FILE)
  end)
  return ok
end

local function note_rect(state, x1, y1, x2, y2, z, kind)
  local rects = state.rects
  rects[#rects + 1] = {x1 = x1, y1 = y1, x2 = x2, y2 = y2, z = z, tick = abs_tick(), kind = kind}
  while #rects > POLICY.max_rects do table.remove(rects, 1) end
end

local function trim_marked(state)
  local m = state.marked
  local over = #m - POLICY.max_marked_keys
  if over > 0 then
    for _ = 1, over do table.remove(m, 1) end
  end
end

-- ---------------------------------------------------------------------------
-- Tile access
-- ---------------------------------------------------------------------------

local function cell(x, y, z)
  local ok, blk = pcall(dfhack.maps.getTileBlock, x, y, z)
  if not ok or not blk then return nil end
  return blk, x % 16, y % 16
end

-- Sets the auto bit on one tile iff its dig designation is Default.
-- Returns "marked", "already", "non_default" or "unreadable".
local function mark_tile(x, y, z)
  local blk, lx, ly = cell(x, y, z)
  if not blk then return "unreadable" end
  local ok, res = pcall(function()
    local d = blk.designation[lx][ly]
    if d.dig ~= df.tile_dig_designation.Default then return "non_default" end
    local o = blk.occupancy[lx][ly]
    if o.dig_auto then return "already" end
    o.dig_auto = true
    blk.flags.designated = true
    return "marked"
  end)
  return ok and res or "unreadable"
end

local function empty_counts()
  return {requested = 0, marked = 0, already_auto = 0, skipped_non_default = 0, skipped_unreadable = 0}
end

local function tally(counts, r)
  counts.requested = counts.requested + 1
  if r == "marked" then counts.marked = counts.marked + 1
  elseif r == "already" then counts.already_auto = counts.already_auto + 1
  elseif r == "non_default" then counts.skipped_non_default = counts.skipped_non_default + 1
  else counts.skipped_unreadable = counts.skipped_unreadable + 1 end
end

-- opts.record (default true): remember the dig in the ledger. opts.kind
-- (default "dig").
-- tiles: list of {x, y, z}.
function mark(tiles, opts)
  local counts = empty_counts()
  local keys = {}
  local by_z = {}
  for _, t in ipairs(tiles or {}) do
    local r = mark_tile(t.x, t.y, t.z)
    tally(counts, r)
    if r == "marked" or r == "already" then
      local b = by_z[t.z]
      if not b then b = {x1 = t.x, y1 = t.y, x2 = t.x, y2 = t.y, z = t.z}; by_z[t.z] = b end
      b.x1, b.y1 = math.min(b.x1, t.x), math.min(b.y1, t.y)
      b.x2, b.y2 = math.max(b.x2, t.x), math.max(b.y2, t.y)
      keys[#keys + 1] = t.x .. "," .. t.y .. "," .. t.z
    end
  end
  if opts and opts.record == false then return counts end
  -- one ledger row per level touched
  local state = load_state()
  for _, b in pairs(by_z) do note_rect(state, b.x1, b.y1, b.x2, b.y2, b.z, (opts and opts.kind) or "dig") end
  for _, k in ipairs(keys) do state.marked[#state.marked + 1] = k end
  trim_marked(state)
  counts.ledger_saved = save_state(state)
  return counts
end

-- A rectangle at one level: the shape both dig tools already hold.
function mark_rect(x, y, z, w, h, opts)
  local tiles = {}
  for dx = 0, w - 1 do
    for dy = 0, h - 1 do tiles[#tiles + 1] = {x = x + dx, y = y + dy, z = z} end
  end
  return mark(tiles, opts)
end

-- ---------------------------------------------------------------------------
-- Census: followed (not ours) vs ours
-- ---------------------------------------------------------------------------

-- Returns a function (x, y, z) -> true when the tile carries the auto bit AND
-- is not one of the tiles this module set the bit on for a dig of ours: that
-- is a tile the game designated by following a vein (or a scan designation).
-- Loads the ledger once. Total: an unreadable tile or ledger reads false.
function followed_checker()
  local ok, state = pcall(load_state)
  local ours = {}
  if ok then for _, k in ipairs(state.marked) do ours[k] = true end end
  return function(x, y, z)
    local blk, lx, ly = cell(x, y, z)
    if not blk then return false end
    local okb, auto = pcall(function() return blk.occupancy[lx][ly].dig_auto end)
    if not okb or not auto then return false end
    return not ours[x .. "," .. y .. "," .. z]
  end
end

-- ---------------------------------------------------------------------------
-- Cavern reaction
-- ---------------------------------------------------------------------------

local function discovery_type_id()
  local ok, id = pcall(function() return df.announcement_type.FEATURE_DISCOVERY end)
  if ok then return id end
  return nil
end

-- New FEATURE_DISCOVERY reports since `since_abs`: list of {abs, x, y, z}
-- (x nil when the report has no usable position), and the newest abs seen.
local function new_discoveries(since_abs)
  local id = discovery_type_id()
  local out, newest = {}, since_abs
  if id == nil then return out, newest, false end
  local ok = pcall(function()
    local reports = df.global.world.status.reports
    local scanned = 0
    for i = #reports - 1, 0, -1 do
      local rep = reports[i]
      scanned = scanned + 1
      if scanned > MAX_REPORT_SCAN then break end
      local abs = rep.year * TICKS_PER_YEAR + rep.time
      if abs <= since_abs then break end
      if abs > newest then newest = abs end
      if rep.type == id then
        local e = {abs = abs}
        if rep.pos and rep.pos.x ~= nil and rep.pos.x >= 0 then
          e.x, e.y, e.z = rep.pos.x, rep.pos.y, rep.pos.z
        end
        out[#out + 1] = e
      end
    end
  end)
  return out, newest, ok
end

-- Clears the auto bit and the dig designation on UNDUG auto tiles (dig is
-- Default and the bit is set) inside the cube. Returns the number cleared.
local function clear_auto_in(x1, y1, x2, y2, z1, z2)
  local cleared = 0
  for z = z1, z2 do
    for x = x1, x2 do
      for y = y1, y2 do
        local blk, lx, ly = cell(x, y, z)
        if blk then
          pcall(function()
            local o = blk.occupancy[lx][ly]
            local d = blk.designation[lx][ly]
            if o.dig_auto and d.dig == df.tile_dig_designation.Default then
              o.dig_auto = false
              d.dig = df.tile_dig_designation.No
              cleared = cleared + 1
            end
          end)
        end
      end
    end
  end
  return cleared
end

local function cavern_reaction(state)
  local found, newest, read_ok = new_discoveries(state.last_report_abs)
  if newest > state.last_report_abs then state.last_report_abs = newest end
  if #found == 0 then return nil, read_ok end
  local R, ZR = POLICY.cavern_radius, POLICY.cavern_z_radius
  local cleared, located = 0, 0
  for _, e in ipairs(found) do
    if e.x then
      located = located + 1
      cleared = cleared + clear_auto_in(e.x - R, e.y - R, e.x + R, e.y + R, e.z - ZR, e.z + ZR)
    end
  end
  if located < #found then
    -- no usable position on at least one report: fall back to the most recent
    -- dig records, widened by the same radius.
    local rects = state.rects
    local from = math.max(1, #rects - POLICY.fallback_rects + 1)
    for i = from, #rects do
      local r = rects[i]
      cleared = cleared + clear_auto_in(r.x1 - R, r.y1 - R, r.x2 + R, r.y2 + R, r.z - ZR, r.z + ZR)
    end
  end
  return {
    breaches = #found, located = located, cleared_tiles = cleared,
    note = string.format(
      "Cavern breach reported by the game (%d report%s): automatic mining was cleared on %d undug tile%s near it; "
      .. "expect open cave, check the nearest dig for creatures and for water.",
      #found, #found == 1 and "" or "s", cleared, cleared == 1 and "" or "s"),
  }, read_ok
end

-- ---------------------------------------------------------------------------
-- Exposed-ore pass
-- ---------------------------------------------------------------------------

local function load_mod(name)
  local ok, m = pcall(reqscript, name)
  if ok and type(m) == "table" then return m end
  return nil
end

local function shape_at(x, y, z)
  local ok, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok or not tt or tt < 0 then return nil end
  local oka, attrs = pcall(function() return df.tiletype.attrs[tt] end)
  if not oka or not attrs then return nil end
  return attrs.shape
end

-- Is this tile one of ours and open (dug, or designated to be dug)?
local function ours_open(x, y, z)
  local blk, lx, ly = cell(x, y, z)
  if not blk then return false end
  local ok, d = pcall(function() return blk.designation[lx][ly].dig end)
  if ok and d ~= df.tile_dig_designation.No then return true end
  local sh = shape_at(x, y, z)
  return sh ~= nil and sh ~= df.tiletype_shape.WALL
end

local NEIGHBOURS = {}
for dx = -1, 1 do for dy = -1, 1 do if dx ~= 0 or dy ~= 0 then NEIGHBOURS[#NEIGHBOURS + 1] = {dx, dy} end end end

-- Revealed, undesignated vein tiles of a wanted kind touching a tile we dug.
-- `max` bounds designations this call (default POLICY.max_per_call).
function scan(max)
  max = tonumber(max) or POLICY.max_per_call
  if max < 1 then return {ok = false, error = "MAX must be at least 1"} end
  max = math.min(max, POLICY.max_per_call)

  local state = load_state()
  local out = {
    ok = true, examined = 0, vein_tiles_seen = 0, designated = 0, skipped_hazard = 0,
    already_designated = 0, in_reservation = 0, reserved_handles = {}, by_mineral = {},
    capped = false, unreadable = 0, ledger_rects = #state.rects,
  }

  local cav = cavern_reaction(state)
  if cav then out.cavern = cav end

  local surface = load_mod('df-overseer-surface')
  local hazard = load_mod('df-overseer-hazard')
  local resv = load_mod('df-overseer-reservations')
  if not surface or not surface.decode_vein then
    out.ok = false
    out.error = "df-overseer-surface decode_vein is not available"
    save_state(state)
    return out
  end
  if hazard and hazard.begin_scan then hazard.begin_scan() end

  -- Candidate tiles: every tile of every ledger rect, widened by one.
  local seen = {}
  local bbox_by_z = {}
  local handles_seen = {}
  local stop = false
  for i = #state.rects, 1, -1 do
    local r = state.rects[i]
    if r.kind == "dig" then
      for x = r.x1 - 1, r.x2 + 1 do
        for y = r.y1 - 1, r.y2 + 1 do
          local key = x .. "," .. y .. "," .. r.z
          if not seen[key] then
            seen[key] = true
            if out.examined >= POLICY.max_examined or out.designated >= max then
              out.capped = true; stop = true; break
            end
            out.examined = out.examined + 1
            local blk, lx, ly = cell(x, y, r.z)
            if blk then
              local okd, des = pcall(function() return blk.designation[lx][ly] end)
              -- hidden first, always: nothing else of a hidden tile is read.
              if okd and not des.hidden then
                if des.dig ~= df.tile_dig_designation.No or blk.occupancy[lx][ly].dig_auto then
                  out.already_designated = out.already_designated + 1
                elseif shape_at(x, y, r.z) == df.tiletype_shape.WALL then
                  local rec = surface.decode_vein(x, y, r.z)
                  if rec and rec.vein_status == "ore_or_gem" and POLICY.kinds[rec.kind] then
                    out.vein_tiles_seen = out.vein_tiles_seen + 1
                    local touches = false
                    for _, nb in ipairs(NEIGHBOURS) do
                      local nx, ny = x + nb[1], y + nb[2]
                      -- the neighbour must lie inside the dig we recorded, so a natural
                      -- cave or an old tunnel beside a vein is never mistaken for ours.
                      if nx >= r.x1 and nx <= r.x2 and ny >= r.y1 and ny <= r.y2
                          and ours_open(nx, ny, r.z) then touches = true; break end
                    end
                    if touches then
                      local hz = hazard and hazard.check_tile(x, y, r.z) or nil
                      if hz then
                        out.skipped_hazard = out.skipped_hazard + 1
                      else
                        if resv then
                          local okc, conflict = pcall(resv.check_tiles, {{x = x, y = y, z = r.z}}, nil)
                          if okc and conflict then
                            out.in_reservation = out.in_reservation + 1
                            if conflict.handle and not handles_seen[conflict.handle] then
                              handles_seen[conflict.handle] = true
                              out.reserved_handles[#out.reserved_handles + 1] =
                                {handle = conflict.handle, purpose = conflict.purpose}
                            end
                          end
                        end
                        des.dig = df.tile_dig_designation.Default
                        blk.occupancy[lx][ly].dig_auto = true
                        blk.flags.designated = true
                        out.designated = out.designated + 1
                        out.by_mineral[rec.mineral_name or "unknown"] =
                          (out.by_mineral[rec.mineral_name or "unknown"] or 0) + 1
                        local b = bbox_by_z[r.z]
                        if not b then b = {x1 = x, y1 = y, x2 = x, y2 = y}; bbox_by_z[r.z] = b end
                        b.x1, b.y1 = math.min(b.x1, x), math.min(b.y1, y)
                        b.x2, b.y2 = math.max(b.x2, x), math.max(b.y2, y)
                      end
                    end
                  elseif rec and rec.vein_status == "unknown" then
                    out.unreadable = out.unreadable + 1
                  end
                end
              end
            end
          end
        end
        if stop then break end
      end
    end
    if stop then break end
  end

  for z, b in pairs(bbox_by_z) do note_rect(state, b.x1, b.y1, b.x2, b.y2, z, "scan") end
  out.ledger_saved = save_state(state)
  if next(out.by_mineral) == nil then out.by_mineral = {} end
  out.summary = string.format(
    "automine scan: %d designated, %d vein tiles seen, %d skipped (hazard), %d inside a reservation%s",
    out.designated, out.vein_tiles_seen, out.skipped_hazard, out.in_reservation, cav and "; cavern reaction fired" or "")
  return out
end

if dfhack_flags and dfhack_flags.module then
  return
end

local args = {...}
if args[1] == "scan" then
  print(json.encode(scan(args[2])))
else
  print("usage: df-overseer-automine scan [MAX]")
end
