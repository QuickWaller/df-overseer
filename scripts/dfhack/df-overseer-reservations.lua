-- df-overseer-reservations.lua
--@module = true
--
-- handoffs/2026-09-30-room-reservations.md. A generic, blueprint-agnostic
-- ledger of reserved ground: a rectangle (x, y, z, w, h) tagged, cell by
-- cell, wall or strict (carve/interior/unclassified), plus a purpose string
-- and the game tick it was created. This file owns exactly two things:
-- persistent storage (DFHack per-site persistent state, the same mechanism
-- df-overseer-blueprint.lua's own site-N handles already use) and the
-- overlap/conflict MATH. It knows nothing about quickfort, templates or
-- orientation -- df-overseer-blueprint.lua's `reserve`/`reservations`/
-- `unreserve` commands (that file, per this handoff's decision 2: "reuse
-- blueprint.lua's resolution code; do not write a second footprint
-- resolver") resolve a footprint and classify its cells, then call in here
-- with plain data.
--
-- WHY A SEPARATE FILE, NOT FOLDED INTO df-overseer-blueprint.lua: every
-- OTHER designating tool in this codebase (farm, workshop, well, building,
-- zone, openarea, diggable, landmarks, construction) also needs
-- `check_tiles`/`rect_tiles` and must not reqscript the much larger
-- blueprint.lua just to reach them.
--
-- NO REQSCRIPT CYCLE: df-overseer-blueprint.lua reqscripts this file (for
-- storage and the overlap math); this file NEVER reqscripts
-- df-overseer-blueprint.lua back. A two-way reqscript here would make this
-- file's own exported functions depend on how far blueprint.lua's own
-- top-level execution had gotten before it called reqscript on this file --
-- fragile and unnecessary, since everything this file needs (a footprint's
-- own coordinates and its wall/carve classification) can simply be passed
-- in as plain data by the caller instead. This file does reqscript
-- df-overseer-landmarks.lua, which is a leaf module with no reqscript of
-- its own, so that stays a one-way, acyclic edge.
--
-- COORDINATE RULE (design commitment #1): a real x/y/z is stored here (the
-- whole point -- this is where the ground is actually held) but is NEVER
-- printed or returned by anything a caller ultimately surfaces to an agent.
-- `get_raw`/`list_raw` below are internal-only, by name and by this
-- comment, exactly like df-overseer-blueprint.lua's own `load_state`:
-- df-overseer-blueprint.lua's `reservations` command strips every
-- coordinate down to a handle/purpose/footprint-size/near-landmark tuple
-- before printing. `check_tiles`'s own conflict return is coordinate-free
-- for the same reason -- any calling tool may return it verbatim.
--
-- SHARED-WALL OVERLAP (user's correction, 2026-09-30, revising the
-- handoff's original decision 5 "no overlaps"): two footprints may overlap
-- ONLY on a tile BOTH classify as wall (their own boundary, a tile no dig/
-- carve designation ever touches) -- a shared wall between adjacent tiled
-- rooms, matching blueprints/templates/*.yaml's own declared seam edges. An
-- overlap on any tile either side classifies as anything else (carve/
-- interior, or simply unclassified by that footprint -- never assumed
-- compatible, the three-valued "never default to the permissive answer"
-- rule this codebase already uses everywhere else) is refused, naming the
-- conflicting handle. A wall tile inside more than one reservation is HELD
-- JOINTLY: removing one reservation leaves it held by the other(s) for
-- free -- find_conflicts/check_tiles re-scan the live table on every call,
-- there is no separate joint-ownership record to keep in sync or forget to
-- update.
--
-- Usage: reqscript only -- this file has no CLI section. The commands a
-- caller actually runs are df-overseer-blueprint's own `reserve`/
-- `reservations`/`unreserve`.

local landmarks_mod = reqscript('df-overseer-landmarks')

local NULL = "\0"
local function nn(v) if v == nil then return NULL end return v end

local STATE_KEY = 'df-overseer-reservations_v1'

local function load_state()
  return dfhack.persistent.getSiteData(STATE_KEY, {next_id = 1, reservations = {}})
end
local function save_state(state)
  dfhack.persistent.saveSiteData(STATE_KEY, state)
end

-- An absolute game tick: cur_year * 403200 + cur_year_tick, the same
-- formula as df-overseer-clock.lua's read_tick. dfhack.world.ReadCurrentTick
-- alone is the tick WITHIN the current year and wraps to 0 every new year,
-- so an age or "ticks since" built from it goes negative across a year
-- boundary. Returns nil if either half cannot be read. Exported so
-- df-overseer-blueprint.lua (which already reqscripts this file) uses the
-- same clock for its site phase ticks and stall detection.
local TICKS_PER_YEAR = 403200
function abs_tick()
  local okt, t = pcall(dfhack.world.ReadCurrentTick)
  if not okt or t == nil then return nil end
  local oky, y = pcall(function() return df.global.cur_year end)
  if not oky or y == nil then return nil end
  return y * TICKS_PER_YEAR + t
end

local function is_handle(s)
  return type(s) == 'string' and s:match('^res%-%d+$') ~= nil
end

-- near_landmark/direction/distance from a rectangle's own centre. Same
-- shape as df-overseer-blueprint.lua's local `site_brief`, duplicated here
-- (a handful of lines) rather than reqscript'd, so this file stays the leaf
-- described in the header above -- matching this codebase's own established
-- call (df-overseer-construction.lua's header, "MATERIAL CHOICE": duplicate
-- a few lines rather than couple two files that would otherwise cycle or
-- over-depend on each other).
local function rect_brief(rec)
  local cx = rec.x + math.floor((rec.w - 1) / 2)
  local cy = rec.y + math.floor((rec.h - 1) / 2)
  local ok, info = pcall(landmarks_mod.nearest_landmark, cx, cy, rec.z)
  info = ok and info or nil
  return {
    near_landmark = nn(info and info.name),
    direction = nn(info and info.direction),
    distance_tiles = nn(info and info.distance_tiles),
  }
end

-- ---------------------------------------------------------------------------
-- Internal-only reads: real coordinates. Never call from anything that
-- prints or returns the result to an agent -- see header.
-- ---------------------------------------------------------------------------

function get_raw(handle)
  local state = load_state()
  return state.reservations[handle]
end

function list_raw()
  local state = load_state()
  local out = {}
  for handle, rec in pairs(state.reservations) do
    local copy = {}
    for k, v in pairs(rec) do copy[k] = v end
    copy.handle = handle
    out[#out + 1] = copy
  end
  table.sort(out, function(a, b) return a.handle < b.handle end)
  return out
end

-- ---------------------------------------------------------------------------
-- Overlap math
-- ---------------------------------------------------------------------------

-- True if (x, y, z) falls inside footprint `rec` (x, y, z, w, h); also
-- returns the tile's 0-based position local to rec (dx, dy).
local function contains(rec, x, y, z)
  if z ~= rec.z then return false end
  local dx, dy = x - rec.x, y - rec.y
  if dx < 0 or dx >= rec.w or dy < 0 or dy >= rec.h then return false end
  return true, dx, dy
end

local function is_wall(rec, dx, dy)
  return rec.wall_cells ~= nil and rec.wall_cells[dx .. "," .. dy] == true
end

-- Every existing footprint (this file's own stored reservations, plus
-- `other_footprints` -- e.g. df-overseer-blueprint.lua's own site-N records,
-- supplied as plain data by the caller; see header on why this file never
-- reqscripts blueprint.lua itself to fetch them directly) that CONFLICTS
-- with a proposed NEW footprint (new_x, new_y, new_z, new_w, new_h,
-- new_wall_cells): a conflict is any tile where the new footprint and an
-- existing one overlap and at least one of the two does not classify that
-- tile as wall. `exclude_handle` skips one reservation of this file's own
-- (kept for symmetry; reserve_site does not need it today, since it is
-- always checking a footprint that does not exist yet). Returns a list of
-- {kind = "reservation"|"site", handle =, purpose =} -- never a coordinate
-- -- deduplicated, one entry per conflicting existing footprint.
function find_conflicts(new_x, new_y, new_z, new_w, new_h, new_wall_cells, other_footprints, exclude_handle)
  local state = load_state()
  local existing = {}
  for handle, rec in pairs(state.reservations) do
    if handle ~= exclude_handle then
      existing[#existing + 1] = {kind = "reservation", handle = handle, purpose = rec.purpose,
        x = rec.x, y = rec.y, z = rec.z, w = rec.w, h = rec.h, wall_cells = rec.wall_cells}
    end
  end
  for _, f in ipairs(other_footprints or {}) do
    existing[#existing + 1] = {kind = "site", handle = f.label, purpose = nil,
      x = f.x, y = f.y, z = f.z, w = f.w, h = f.h, wall_cells = f.wall_cells}
  end

  local conflicts, seen = {}, {}
  for dx = 0, new_w - 1 do
    for dy = 0, new_h - 1 do
      local x, y = new_x + dx, new_y + dy
      local new_wall = new_wall_cells ~= nil and new_wall_cells[dx .. "," .. dy] == true
      for _, e in ipairs(existing) do
        local key = e.kind .. ":" .. tostring(e.handle)
        if not seen[key] then
          local inside, edx, edy = contains(e, x, y, new_z)
          if inside then
            local existing_wall = is_wall(e, edx, edy)
            if not (new_wall and existing_wall) then
              seen[key] = true
              conflicts[#conflicts + 1] = {kind = e.kind, handle = e.handle, purpose = e.purpose}
            end
          end
        end
      end
    end
  end
  return conflicts
end

-- ---------------------------------------------------------------------------
-- Creation / lifecycle / removal
-- ---------------------------------------------------------------------------

-- rec: {x, y, z, w, h, orient, bw, bh, blueprint, purpose, wall_cells}.
-- Stamps created_tick and site_handle = nil, assigns and returns a new
-- handle.
function create(rec)
  local state = load_state()
  local handle = "res-" .. tostring(state.next_id)
  state.next_id = state.next_id + 1
  local stored = {}
  for k, v in pairs(rec) do stored[k] = v end
  stored.created_tick = abs_tick()
  stored.site_handle = nil
  state.reservations[handle] = stored
  save_state(state)
  return handle
end

-- Marks a reservation "in use": a blueprint apply carved/built from it
-- (decision 6's lifecycle: reserved -> in use -> released by unreserve).
function mark_in_use(handle, site_handle)
  local state = load_state()
  local rec = state.reservations[handle]
  if not rec then return false end
  rec.site_handle = site_handle
  save_state(state)
  return true
end

-- Removes a reservation outright (decision 6: no automatic expiry, always
-- an explicit call). Returns (removed: bool, remaining_holders: a sorted
-- list of OTHER reservation handles still covering any of the removed
-- reservation's tiles -- a shared wall stays held by them, see header) or
-- (false, nil, err) if handle is malformed or unknown.
function remove(handle)
  if not is_handle(handle) then return false, nil, "RES_ID must look like res-3" end
  local state = load_state()
  local rec = state.reservations[handle]
  if not rec then return false, nil, "no reservation '" .. handle .. "'" end
  state.reservations[handle] = nil
  save_state(state)
  local remaining, seen = {}, {}
  for dx = 0, rec.w - 1 do
    for dy = 0, rec.h - 1 do
      local x, y = rec.x + dx, rec.y + dy
      for other_handle, other in pairs(state.reservations) do
        if not seen[other_handle] then
          if contains(other, x, y, rec.z) then
            seen[other_handle] = true
            remaining[#remaining + 1] = other_handle
          end
        end
      end
    end
  end
  table.sort(remaining)
  return true, remaining, nil
end

-- ---------------------------------------------------------------------------
-- The shared check every designating tool calls before mutating tiles
-- (handoffs/2026-09-30-room-reservations.md decision 3).
-- ---------------------------------------------------------------------------

-- Every tile of a w x h rectangle at x, y, z -- a small shared helper so
-- every calling tool builds its candidate tile list the same way, never a
-- second, slightly different rectangle enumerator per file.
function rect_tiles(x, y, z, w, h)
  local out = {}
  for dx = 0, w - 1 do
    for dy = 0, h - 1 do
      out[#out + 1] = {x = x + dx, y = y + dy, z = z}
    end
  end
  return out
end

-- tiles: a list of {x =, y =, z =} (rect_tiles above, or a tool's own
-- per-tile candidate list, e.g. df-overseer-construction.lua's ring
-- candidates). holding_handle: a res-N this call is entitled to build or
-- designate over -- decision 4: only df-overseer-blueprint.lua's own apply
-- ever passes one (the reservation SITE was resolved from); every other
-- tool in this codebase calls this with holding_handle = nil and simply
-- refuses on any covering reservation (decision 4: "otherwise they simply
-- refuse"). A tile covered by MORE than one reservation (a shared wall) is
-- fine as long as holding_handle is ONE of the covering handles -- "either
-- holder's own blueprint apply may build or designate it" (the user's
-- correction).
--
-- Returns nil if every tile is clear of a reservation this call does not
-- hold; otherwise the FIRST conflicting tile's reservation info, never a
-- coordinate: {handle =, purpose =, near_landmark =, direction =,
-- distance_tiles =, message =}.
function check_tiles(tiles, holding_handle)
  local state = load_state()
  for _, t in ipairs(tiles) do
    -- Collect every reservation covering this tile FIRST: a shared wall
    -- tile can be covered by more than one, and holding just one of them is
    -- enough (the user's correction) -- checking handle-by-handle and
    -- bailing on the first non-held match would wrongly refuse a tile the
    -- caller's own held reservation also covers.
    local held_here, first_other = false, nil
    for handle, rec in pairs(state.reservations) do
      if contains(rec, t.x, t.y, t.z) then
        if handle == holding_handle then
          held_here = true
        elseif not first_other then
          first_other = {handle = handle, rec = rec}
        end
      end
    end
    if not held_here and first_other then
      local handle, rec = first_other.handle, first_other.rec
      do
        local brief = rect_brief(rec)
        local where = (brief.near_landmark ~= NULL)
          and (tostring(brief.near_landmark) .. " " .. tostring(brief.direction) .. " "
            .. tostring(brief.distance_tiles) .. " tiles")
          or "an unlocatable landmark"
        return {
          handle = handle, purpose = rec.purpose,
          near_landmark = brief.near_landmark, direction = brief.direction,
          distance_tiles = brief.distance_tiles,
          message = "tile(s) here are reserved as " .. handle .. " (" .. tostring(rec.purpose)
            .. "), near " .. where .. "; this tool is not that reservation's holder",
        }
      end
    end
  end
  return nil
end

-- No dfhack_flags.module guard, no CLI section -- see header, "Usage".
