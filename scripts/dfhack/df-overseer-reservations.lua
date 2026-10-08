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

-- Exported (handoffs/2026-09-30-reservation-holding.md): every OTHER
-- designating tool's own RES_ID argument validation reuses this, rather than
-- a second regex per file.
function is_handle(s)
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

-- TILE CLASSES AND SHAPES (circulation hands, red team B2).
-- A footprint is one of two stored shapes, both read through class_at:
--   rect:  {x, y, z, w, h, wall_cells, portal_cells} -- one level, a
--          rectangle (every reservation made before 2026-10-08, and every
--          template reservation still); wall_cells/portal_cells are sets of
--          0-based "dx,dy" keys, every other tile of the rectangle is strict.
--   tiles: {tiles = {["x,y,z"] = class}} -- any set of tiles on any levels (a
--          routed corridor, a stair column). x, y, z (the LOWEST level), w, h
--          and z_max are kept as the bounding box so a reader that only knows
--          rectangles still gets a sane (if coarser) answer.
-- Classes: "wall" (a boundary tile no dig ever touches), "portal" (the tile
-- where a room's entrance meets a corridor) and "strict" (carve, interior,
-- or anything else). A footprint also has a `role`, "room" or "corridor".
-- Two footprints may share a tile ONLY if (a) both call it wall (the
-- original shared-wall rule), or (b) one calls it portal, the other calls it
-- portal or wall, and their roles are the two DIFFERENT known roles: so one
-- room and one corridor, never two rooms and never two corridors, and a
-- third footprint on a tile already shared by a room and a corridor always
-- clashes with one of them. A footprint with no role never shares a portal
-- (the strict default). Everything else is refused.
local CLASSES = {wall = true, portal = true, strict = true}
local ROLES = {room = true, corridor = true}

-- The class this footprint gives tile (x, y, z), or nil if it does not cover it.
local function class_at(rec, x, y, z)
  if rec.tiles ~= nil then return rec.tiles[x .. "," .. y .. "," .. z] end
  if z ~= rec.z then return nil end
  local dx, dy = x - rec.x, y - rec.y
  if dx < 0 or dx >= rec.w or dy < 0 or dy >= rec.h then return nil end
  local key = dx .. "," .. dy
  if rec.wall_cells ~= nil and rec.wall_cells[key] == true then return "wall" end
  if rec.portal_cells ~= nil and rec.portal_cells[key] == true then return "portal" end
  return "strict"
end

-- True if footprint `rec` covers (x, y, z), either shape.
local function contains(rec, x, y, z)
  return class_at(rec, x, y, z) ~= nil
end

-- Calls fn(x, y, z, class) for every tile `rec` covers, either shape.
local function each_tile(rec, fn)
  if rec.tiles ~= nil then
    for key, cls in pairs(rec.tiles) do
      local x, y, z = key:match("^(-?%d+),(-?%d+),(-?%d+)$")
      fn(tonumber(x), tonumber(y), tonumber(z), cls)
    end
    return
  end
  for dx = 0, rec.w - 1 do
    for dy = 0, rec.h - 1 do
      local x, y = rec.x + dx, rec.y + dy
      fn(x, y, rec.z, class_at(rec, x, y, rec.z))
    end
  end
end

-- May two footprints share one tile? See the header above.
local function compatible(cls_a, role_a, cls_b, role_b)
  if cls_a == "wall" and cls_b == "wall" then return true end
  local portal_a, portal_b = cls_a == "portal", cls_b == "portal"
  if (portal_a or portal_b) and (cls_a == "wall" or portal_a) and (cls_b == "wall" or portal_b) then
    return role_a ~= nil and role_b ~= nil and role_a ~= role_b
  end
  return false
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
function find_conflicts(new_x, new_y, new_z, new_w, new_h, new_wall_cells, other_footprints, exclude_handle,
    new_portal_cells, new_role)
  local tiles = {}
  for dx = 0, new_w - 1 do
    for dy = 0, new_h - 1 do
      local key = dx .. "," .. dy
      local cls = "strict"
      if new_wall_cells ~= nil and new_wall_cells[key] == true then cls = "wall"
      elseif new_portal_cells ~= nil and new_portal_cells[key] == true then cls = "portal" end
      tiles[(new_x + dx) .. "," .. (new_y + dy) .. "," .. new_z] = cls
    end
  end
  return find_conflicts_tiles(tiles, new_role, other_footprints, exclude_handle)
end

-- The same check for a proposed footprint that is any set of tiles:
-- new_tiles is {["x,y,z"] = class}, new_role "room"|"corridor"|nil.
function find_conflicts_tiles(new_tiles, new_role, other_footprints, exclude_handle)
  local state = load_state()
  local existing = {}
  for handle, rec in pairs(state.reservations) do
    if handle ~= exclude_handle then
      existing[#existing + 1] = {kind = "reservation", handle = handle, purpose = rec.purpose, role = rec.role,
        x = rec.x, y = rec.y, z = rec.z, w = rec.w, h = rec.h, wall_cells = rec.wall_cells,
        portal_cells = rec.portal_cells, tiles = rec.tiles}
    end
  end
  for _, f in ipairs(other_footprints or {}) do
    existing[#existing + 1] = {kind = "site", handle = f.label, purpose = nil, role = f.role,
      x = f.x, y = f.y, z = f.z, w = f.w, h = f.h, wall_cells = f.wall_cells,
      portal_cells = f.portal_cells, tiles = f.tiles}
  end

  local conflicts, seen = {}, {}
  for key, new_cls in pairs(new_tiles) do
    local x, y, z = key:match("^(-?%d+),(-?%d+),(-?%d+)$")
    x, y, z = tonumber(x), tonumber(y), tonumber(z)
    for _, e in ipairs(existing) do
      local ekey = e.kind .. ":" .. tostring(e.handle)
      if not seen[ekey] then
        local ecls = class_at(e, x, y, z)
        if ecls ~= nil and not compatible(new_cls, new_role, ecls, e.role) then
          seen[ekey] = true
          conflicts[#conflicts + 1] = {kind = e.kind, handle = e.handle, purpose = e.purpose}
        end
      end
    end
  end
  table.sort(conflicts, function(a, b) return tostring(a.handle) < tostring(b.handle) end)
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
  -- allowed_kinds (handoffs/2026-09-30-reservation-holding.md item 1): a list
  -- of kind tokens the caller (df-overseer-blueprint.lua's reserve_site)
  -- derived from the template's own #build/#zone cells -- never invented
  -- here. Defaults to an empty list, never nil, so kind_allowed below never
  -- has to guess whether "no list" means "everything" or "nothing" (it means
  -- nothing -- the strict, never-default-permissive rule this codebase
  -- already uses everywhere else).
  stored.allowed_kinds = stored.allowed_kinds or {}
  stored.overrides = stored.overrides or {}
  state.reservations[handle] = stored
  save_state(state)
  return handle
end

-- A reservation over any set of tiles on any levels (a routed corridor, a
-- stair column). rec: {tiles = {["x,y,z"] = "wall"|"portal"|"strict"},
-- role = "room"|"corridor", purpose, blueprint (optional), allowed_kinds
-- (optional)}. Derives the bounding box (x, y, lowest z, w, h, z_max) and
-- stores it with the tiles. Returns handle, or nil, err.
function create_tile_set(rec)
  if type(rec) ~= 'table' or type(rec.tiles) ~= 'table' or next(rec.tiles) == nil then
    return nil, "a tile-set reservation needs a non-empty tiles table"
  end
  if rec.role ~= nil and not ROLES[rec.role] then
    return nil, "role must be 'room' or 'corridor'"
  end
  local x1, y1, z1, x2, y2, z2 = 1e9, 1e9, 1e9, -1e9, -1e9, -1e9
  for key, cls in pairs(rec.tiles) do
    if not CLASSES[cls] then return nil, "tile class must be wall, portal or strict, got " .. tostring(cls) end
    local x, y, z = key:match("^(-?%d+),(-?%d+),(-?%d+)$")
    if not x then return nil, "tile keys must look like 'x,y,z'" end
    x, y, z = tonumber(x), tonumber(y), tonumber(z)
    x1 = math.min(x1, x); x2 = math.max(x2, x)
    y1 = math.min(y1, y); y2 = math.max(y2, y)
    z1 = math.min(z1, z); z2 = math.max(z2, z)
  end
  local stored = {}
  for k, v in pairs(rec) do stored[k] = v end
  stored.x, stored.y, stored.z = x1, y1, z1
  stored.w, stored.h, stored.z_max = x2 - x1 + 1, y2 - y1 + 1, z2
  stored.shape = "tiles"
  return create(stored)
end

-- Every tile a reservation covers, as a list of {x, y, z, class}. Internal
-- (real coordinates), like get_raw: for a Lua caller that routes or checks,
-- never for anything surfaced to an agent. Reads both stored shapes.
function tiles_of(handle)
  local rec = get_raw(handle)
  if not rec then return nil end
  local out = {}
  each_tile(rec, function(x, y, z, cls) out[#out + 1] = {x = x, y = y, z = z, class = cls} end)
  return out
end

-- True if `kind` is one of `handle`'s own declared allowed kinds. False (not
-- nil) on an unknown handle or an unlisted kind -- there is nothing "unknown"
-- about "no reservation says this kind is fine here".
function kind_allowed(handle, kind)
  local rec = get_raw(handle)
  if not rec or kind == nil then return false end
  for _, k in ipairs(rec.allowed_kinds or {}) do
    if k == kind then return true end
  end
  return false
end

-- True only if OVERRIDE would actually be consumed: some tile in `tiles`
-- lies inside `res_id`'s own reservation AND `kind` is NOT one of that
-- reservation's allowed_kinds. False for a malformed/unknown res_id, for a
-- kind that is already allowed (no override needed), and for a call whose
-- tiles never touch res_id at all (there is nothing here for an override to
-- have overridden). Callers use this BEFORE designating anything to decide
-- whether a later successful, real (non-dry) call is worth recording --
-- see handoff review, 2026-09-30: recording must never happen for a dry
-- run, for an override that was not actually needed, or for a designation
-- that then failed, so this is deliberately a separate, side-effect-free
-- query from check_tiles/record_override, computed once up front and
-- carried by the caller to its own success point.
function override_needed(tiles, res_id, kind)
  if res_id == nil or not is_handle(res_id) then return false end
  local rec = get_raw(res_id)
  if not rec then return false end
  if kind_allowed(res_id, kind) then return false end
  for _, t in ipairs(tiles) do
    if contains(rec, t.x, t.y, t.z) then
      return true
    end
  end
  return false
end

-- Appends a one-off override record to `handle` (item 3): {tick (absolute),
-- tool, kind, reason}. Never changes allowed_kinds or purpose -- a
-- re-purposed room is unreserve plus a new reserve, never this. Returns
-- (true) or (false, err).
function record_override(handle, tool, kind, reason)
  if not is_handle(handle) then return false, "RES_ID must look like res-3" end
  local state = load_state()
  local rec = state.reservations[handle]
  if not rec then return false, "no reservation '" .. handle .. "'" end
  rec.overrides = rec.overrides or {}
  rec.overrides[#rec.overrides + 1] = {tick = abs_tick(), tool = nn(tool), kind = nn(kind), reason = tostring(reason)}
  save_state(state)
  return true
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
  each_tile(rec, function(x, y, z)
    for other_handle, other in pairs(state.reservations) do
      if not seen[other_handle] and contains(other, x, y, z) then
        seen[other_handle] = true
        remaining[#remaining + 1] = other_handle
      end
    end
  end)
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
-- hold or is not otherwise entitled to; otherwise the FIRST conflicting
-- tile's reservation info, never a coordinate: {handle =, purpose =,
-- near_landmark =, direction =, distance_tiles =, message =}.
--
-- holding_handle (decision 4, room-reservations handoff): the TRUE holder --
-- only df-overseer-blueprint.lua's own apply ever passes one (the
-- reservation SITE was resolved from), and it bypasses every check on that
-- reservation's own tiles regardless of kind. Unchanged by this handoff.
--
-- res_id, kind, override_reason (handoffs/2026-09-30-reservation-holding.md
-- items 2-3): every OTHER designating tool's optional RES_ID/OVERRIDE. A
-- tile inside the res_id reservation is allowed if override_reason is given
-- (one-off exception, recorded by the CALLER via record_override once this
-- returns nil -- this function stays a pure query, no side effects) or if
-- `kind` is one of that reservation's own allowed_kinds. A tile inside any
-- OTHER reservation is still refused, exactly as if res_id had not been
-- given at all.
function check_tiles(tiles, holding_handle, res_id, kind, override_reason)
  if res_id ~= nil and not is_handle(res_id) then
    return {message = "RES_ID must look like res-3"}
  end
  local claim_rec = nil
  if res_id ~= nil then
    claim_rec = get_raw(res_id)
    if not claim_rec then
      return {message = "no reservation '" .. res_id .. "'"}
    end
  end
  local state = load_state()
  for _, t in ipairs(tiles) do
    -- Collect every reservation covering this tile FIRST: a shared wall
    -- tile can be covered by more than one, and holding (or being entitled
    -- to) just one of them is enough -- checking handle-by-handle and
    -- bailing on the first non-held match would wrongly refuse a tile the
    -- caller's own held/claimed reservation also covers.
    local held_here, claim_here, first_other = false, false, nil
    for handle, rec in pairs(state.reservations) do
      if contains(rec, t.x, t.y, t.z) then
        if handle == holding_handle then
          held_here = true
        elseif res_id ~= nil and handle == res_id then
          claim_here = true
        elseif not first_other then
          first_other = {handle = handle, rec = rec}
        end
      end
    end
    if not held_here then
      if claim_here then
        if override_reason == nil and not kind_allowed(res_id, kind) then
          local allowed = claim_rec.allowed_kinds or {}
          return {
            handle = res_id, purpose = claim_rec.purpose,
            message = "tile(s) here are reserved as " .. res_id .. " (" .. tostring(claim_rec.purpose)
              .. "); this call's kind (" .. tostring(kind) .. ") is not one this reservation allows ("
              .. (#allowed > 0 and table.concat(allowed, ", ") or "none")
              .. "); pass OVERRIDE with a reason for a one-off exception",
          }
        end
        -- else: kind is allowed, or an override reason was given -- this
        -- tile is fine; keep checking the rest.
      elseif first_other then
        local handle, rec = first_other.handle, first_other.rec
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
            .. "), near " .. where .. "; this tool is not that reservation's holder"
            .. (res_id ~= nil and " (RES_ID named a different reservation)" or ""),
        }
      end
    end
  end
  return nil
end

-- ---------------------------------------------------------------------------
-- Finder-skip (handoffs/2026-09-30-reservation-holding.md item 4): "a
-- finder never ranks a reserved candidate", factored ONCE here rather than
-- duplicated per finder, so df-overseer-diggable.lua's own two ranking
-- functions (WxH windows, and single-point stair-pair candidates) and
-- df-overseer-openarea.lua's ranking function all share one filter instead
-- of three near-identical loops.
-- ---------------------------------------------------------------------------

-- Drops any candidate from `candidates` whose own tiles (tiles_for(c),
-- called once per candidate) overlap a reservation this call does not hold
-- -- reusing check_tiles's own holding_handle bypass slot for `res_id`
-- (nil: refuse any reservation at all; a handle: keep a candidate inside
-- THAT reservation, still drop one inside any OTHER). `tiles_for` is a
-- function so this works for a WxH rectangle candidate (df-overseer-
-- diggable.lua's/df-overseer-openarea.lua's `{x=, y=}` windows) and for a
-- single-point, two-z-level candidate (df-overseer-diggable.lua's stair
-- pairs) alike, without this file knowing either shape.
function filter_reserved(candidates, res_id, tiles_for)
  local kept = {}
  for _, c in ipairs(candidates) do
    if not check_tiles(tiles_for(c), res_id) then
      kept[#kept + 1] = c
    end
  end
  return kept
end

-- No dfhack_flags.module guard, no CLI section -- see header, "Usage".
