-- A minimal fake DFHack world for df-overseer-construction.lua
-- (handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md). Loaded
-- by tests/test_construction_lua_logic.py, which runs the REAL
-- scripts/dfhack/df-overseer-construction.lua against it in lupa.
--
-- Proves the FILE'S OWN LOGIC (which ring tiles it treats as ore/gem
-- candidates, which it refuses and why, that `build` refuses a still-WALL
-- tile rather than guessing, that both verbs apply one single-cell
-- blueprint per tile via a stubbed quickfort). It stubs out
-- df-overseer-surface.lua and df-overseer-building.lua entirely (both are
-- reqscript'd, real modules in production) and fakes `io.open`/`os.remove`
-- so no real file touches disk. It proves nothing about the real quickfort
-- CLI or the real vein-decode API -- see df-overseer-surface.lua's own
-- header and this stream's Result section for that.

local function enum(names)
  local t = {}
  for i, n in ipairs(names) do t[n] = i - 1; t[i - 1] = n end
  return t
end

local NULL = "\0"

-- ---------------------------------------------------------------------------
-- Fake item world, for the item_present guard
-- (handoffs/2026-09-28-keeps-access-guard.md). ITEMS holds every fake item;
-- add_item(id, item_type, x, y, z, opts) registers one at a real position,
-- with the same trader/garbage_collect/removed flags the guard's
-- is_fort_owned_item_flags checks. An item with no position at all (opts.no_pos)
-- proves dfhack.items.getPosition failing/returning nil is handled, not just
-- items elsewhere on the map.
-- ---------------------------------------------------------------------------

ITEMS = {}

-- `item_type` is the TOKEN NAME ("BOULDER"), converted here to the enum
-- ordinal df.item_type expects `item:getType()` to return -- the real
-- df.item_type[ordinal] -> name round trip df-overseer-construction.lua's
-- item_present_at relies on, not just the name handed straight back.
function add_item(id, item_type, x, y, z, opts)
  opts = opts or {}
  local it = {
    id = id,
    _item_type_ordinal = df.item_type[item_type],
    _x = opts.no_pos and nil or x,
    _y = opts.no_pos and nil or y,
    _z = opts.no_pos and nil or z,
    flags = {
      trader = opts.trader == true,
      garbage_collect = opts.garbage_collect == true,
      removed = opts.removed == true,
    },
  }
  function it:getType() return self._item_type_ordinal end
  ITEMS[#ITEMS + 1] = it
end

df = {
  tiletype_shape = enum({"WALL", "FLOOR", "RAMP", "EMPTY"}),
  item_type = enum({"BOULDER", "ROUGH", "WOOD", "BLOCKS"}),
  building_type = enum({"Workshop", "Furnace", "Construction", "Trap", "SiegeEngine", "Bed", "Door"}),
  -- 2026-10-01 (handoffs/2026-10-01-buildingplan-material-filter.md):
  -- construction_type_numbers relies on this being bidirectional (a name
  -- like "Wall" indexes straight to its number), the same property every
  -- real DFHack enum table has.
  construction_type = enum({"Wall", "Floor", "Ramp", "UpStair", "DownStair"}),
  global = {world = {items = {all = ITEMS}, jobs = {list = nil}, buildings = {all = {}}}},
  building_civzonest = {
    -- handoffs/2026-10-01-entrances-get-doors.md audit's own no-ZONE_ID path
    -- (iterate every civzone): this fake never registers a civzone in
    -- df.global.world.buildings.all, so is_instance is never asked to
    -- return true in any test here -- every audit test names its ZONE_ID
    -- explicitly. Present only so a call to is_instance does not error.
    is_instance = function(_) return false end,
  },
}

CR_OK = 0

-- A real DFHack global (dfhack.buildings.findAtTile(xyz2pos(x,y,z)) is the
-- exact call df-overseer-surface.lua's own tile_read already makes live);
-- this fake just needs SOME table shape a position-taking call can use as
-- a lookup key, never printed or compared to anything but itself.
function xyz2pos(x, y, z) return {x = x, y = y, z = z} end

-- ---------------------------------------------------------------------------
-- Fake df-overseer-surface module
-- ---------------------------------------------------------------------------

ZONES = {}
RINGS = {}   -- zone id -> list of {x,y,z}
TILES = {}   -- "x,y,z" -> {ok=, hidden=, shape=}
VEINS = {}   -- "x,y,z" -> {vein_status=, mineral_name=, error=}

local function key(x, y, z) return x .. "," .. y .. "," .. z end

-- x1/y1/x2/y2 default to a single far-away cell (1000,1000,0) that no real
-- test target coordinate ever collides with -- existing tests that only
-- care about item_present/keeps_access/reservation/material guards never
-- need to think about zone geometry at all; only the entrance-specific
-- tests below pass a real footprint (the office's own, from the eval).
function add_zone(id, x1, y1, x2, y2)
  ZONES[id] = {id = id, x1 = x1 or 1000, y1 = y1 or 1000, x2 = x2 or 1000, y2 = y2 or 1000}
end

function set_ring(zone_id, tiles)
  local t = {}
  for i, xyz in ipairs(tiles) do t[i] = xyz end
  RINGS[zone_id] = t
end

function set_tile(x, y, z, shape, opts)
  opts = opts or {}
  TILES[key(x, y, z)] = {ok = (opts.ok ~= false), hidden = (opts.hidden == true),
    shape = shape and df.tiletype_shape[shape] or nil, err = opts.err}
end

function set_vein(x, y, z, vein_status, mineral_name, error_msg)
  VEINS[key(x, y, z)] = {vein_status = vein_status, mineral_name = mineral_name, error = error_msg}
end

-- Shaped like the REAL df-overseer-surface.lua on purpose: find_zone,
-- ring_tiles, tile_read and decode_vein_tile are all `local`, and the only
-- thing exposed on the fake module table is `vein_material`, which closes
-- over the first three; decode_vein_tile itself closes over tile_read. This
-- is exactly the upvalue chain df-overseer-construction.lua's own
-- `surface_hooks()` extracts via `debug.getupvalue` (the same idiom
-- df-overseer-building.lua already uses to reach quickfort's own local
-- table) -- a fake module that just handed these out as plain named fields
-- would not exercise that extraction at all.
local function find_zone(zone_id)
  local b = ZONES[tonumber(zone_id) or zone_id]
  if not b then return nil, "no building with id " .. tostring(zone_id) end
  return b
end

local function ring_tiles(b) return RINGS[b.id] or {} end

local function tile_read(x, y, z)
  local t = TILES[key(x, y, z)]
  if not t then return {ok = false, err = "no test tile set for " .. key(x, y, z)} end
  return t
end

local function decode_vein_tile(x, y, z)
  local t = tile_read(x, y, z)
  if not t.ok then return {vein_status = "unreadable", error = t.err} end
  if t.hidden then return {vein_status = "hidden"} end
  return VEINS[key(x, y, z)] or {vein_status = "not_mineral", economic = false}
end

local function vein_material(zone_id)
  local b, err = find_zone(zone_id)
  if not b then return {error = err} end
  local out = {}
  for i, xyz in ipairs(ring_tiles(b)) do out[i] = decode_vein_tile(xyz[1], xyz[2], xyz[3]) end
  return out
end

local FAKE_SURFACE = {vein_material = vein_material}

-- ---------------------------------------------------------------------------
-- Fake df-overseer-building module (only list_kinds is used)
-- ---------------------------------------------------------------------------

KINDS = {}   -- list of {type=, subtype=, token=, key=, label=}

function set_kinds(list)
  local t = {}
  for i, k in ipairs(list) do
    t[i] = {type = k.type, subtype = k.subtype or NULL, token = k.token, key = k.key, label = k.label or k.token}
  end
  KINDS = t
end

-- 2026-10-01 (handoffs/2026-10-01-buildingplan-material-filter.md): the real
-- df-overseer-building.lua now exports building_filters_and_gaps (the real
-- material breakdown) and apply_material_filters (the buildingplan write);
-- construction.lua calls straight into both. This fake models the SHAPE of
-- both without re-implementing the real economic-exclusion logic (that is
-- fully covered against the real building.lua by
-- tests/test_building_material_and_previously_built_lua_logic.py and
-- tests/test_buildingplan_material_filter_lua_logic.py) -- a test here sets
-- what building_filters_and_gaps should return via set_building_filters, and
-- reads what apply_material_filters was called with via
-- APPLIED_FILTER_CALLS/RESTORE_CALLS.
BUILDING_FILTERS = nil
BUILDINGPLAN_ENABLED = false
APPLIED_FILTER_CALLS = {}
RESTORE_CALLS = 0

function set_building_filters(list, enabled)
  local t = {}
  for i, rec in ipairs(list or {}) do t[i] = rec end
  BUILDING_FILTERS = t
  BUILDINGPLAN_ENABLED = (enabled ~= false)
end

local FAKE_BUILDING = {
  list_kinds = function(_) return KINDS end,
  building_filters_and_gaps = function(btype, sub, cust, material_choice, label)
    local filters = BUILDING_FILTERS or {}
    local bm = {source = "fake", buildingplan_enabled = BUILDINGPLAN_ENABLED, filters = filters}
    if #filters == 0 then
      bm.note = "the game lists no material filter for this kind"
    end
    return {building_material = bm}, {}
  end,
  apply_material_filters = function(btype, sub, cust, filter_recs)
    local applied = {}
    for _, rec in ipairs(filter_recs) do
      APPLIED_FILTER_CALLS[#APPLIED_FILTER_CALLS + 1] = {
        btype = btype, sub = sub, cust = cust, index = rec.index, names = rec.filter_material_names,
      }
      applied[#applied + 1] = {index = rec.index, ok = true, materials = rec.filter_material_names}
    end
    local function restore()
      RESTORE_CALLS = RESTORE_CALLS + 1
      return {}
    end
    return {applied = applied}, restore
  end,
}

-- Fake df-overseer-reservations.lua (handoffs/2026-09-30-room-reservations.md):
-- RESERVED is a list of {x=, y=, z=, handle=, purpose=} the test sets via
-- set_reserved(); check_tiles reports the first match not equal to
-- `holding`, in the real module's own coordinate-free shape.
RESERVED = {}
function set_reserved(list) RESERVED = list end
-- override_needed/record_override (handoffs/2026-09-30-reservation-holding.md
-- review, item 1): this fake does not model allowed_kinds at all (no
-- construction test needs kind-gating, only the reservation guard itself),
-- so override_needed here is simply "some tile is covered by a RESERVED
-- entry matching res_id" -- good enough to prove the OVERRIDE/RES_ID pairing
-- plumbing (guard clause, and the caller's own needs_override/
-- record_override wiring) without re-modelling the real allowed_kinds logic,
-- which is already fully covered by tests/test_reservations_lua_logic.py
-- against the REAL reservations.lua.
OVERRIDES = {}
local FAKE_RESERVATIONS = {
  check_tiles = function(tiles, holding, res_id, kind, override)
    for _, t in ipairs(tiles) do
      for _, r in ipairs(RESERVED) do
        if r.x == t.x and r.y == t.y and r.z == t.z then
          if r.handle == holding then
            -- held: fine regardless of kind/override
          elseif r.handle == res_id then
            if override == nil then
              return {
                handle = r.handle, purpose = r.purpose,
                message = "tile(s) here are reserved as " .. r.handle .. " (" .. tostring(r.purpose)
                  .. "); this call's kind is not one this reservation allows",
              }
            end
            -- override given: fine
          else
            return {
              handle = r.handle, purpose = r.purpose,
              near_landmark = r.near_landmark or "Well", direction = r.direction or "N",
              distance_tiles = r.distance_tiles or 1,
              message = "tile(s) here are reserved as " .. r.handle .. " (" .. tostring(r.purpose) .. ")",
            }
          end
        end
      end
    end
    return nil
  end,
  override_needed = function(tiles, res_id, kind)
    if res_id == nil then return false end
    for _, t in ipairs(tiles) do
      for _, r in ipairs(RESERVED) do
        if r.handle == res_id and r.x == t.x and r.y == t.y and r.z == t.z then
          return true
        end
      end
    end
    return false
  end,
  -- RESERVED entries may carry site_handle = "site-N" (the real record's own field).
  list_raw = function()
    local out, seen = {}, {}
    for _, r in ipairs(RESERVED) do
      if not seen[r.handle] then
        seen[r.handle] = true
        out[#out + 1] = {handle = r.handle, site_handle = r.site_handle}
      end
    end
    return out
  end,
  record_override = function(handle, tool, kind, reason)
    OVERRIDES[#OVERRIDES + 1] = {handle = handle, tool = tool, kind = kind, reason = reason}
    return true
  end,
  rect_tiles = function(x, y, z, w, h)
    local out = {}
    for dx = 0, w - 1 do for dy = 0, h - 1 do out[#out + 1] = {x = x + dx, y = y + dy, z = z} end end
    return out
  end,
}

-- ---------------------------------------------------------------------------
-- Fake df-overseer-reachability.lua / df-overseer-connectivity.lua
-- (handoffs/2026-10-01-entrances-get-doors.md): GROUPS is a plain
-- "x,y,z" -> walkable-group-id map a test fills in with set_group;
-- MAIN_GROUP is the fort's own main group, read by main_group_id() through
-- get_connectivity_report. group_matches mirrors the REAL
-- df-overseer-reachability.lua's own signature (x, y, z, target_groups) ->
-- matched, how, group -- "at"/the real group id are good enough fakes here,
-- find_entrances only ever looks at the first return value.
-- ---------------------------------------------------------------------------

GROUPS = {}
MAIN_GROUP = nil
function set_group(x, y, z, group) GROUPS[key(x, y, z)] = group end
function set_main_group(group) MAIN_GROUP = group end

local FAKE_REACHABILITY = {
  group_matches = function(x, y, z, target_groups)
    local g = GROUPS[key(x, y, z)]
    if g == nil then return false, nil, nil end
    return target_groups[g] == true, "at", g
  end,
}

local FAKE_CONNECTIVITY = {
  get_connectivity_report = function()
    return {main_group_id = MAIN_GROUP}
  end,
}

-- add_entrance_fixture(zone_id, [ex, ey, ez]) -- appends one open ring tile
-- to RINGS[zone_id] whose OUTSIDE neighbour (per
-- df-overseer-construction.lua's own ring_edge_neighbours, against the
-- zone's footprint -- the x1=y1=x2=y2=1000 default from add_zone unless the
-- test gave its own) is registered in the fort's main walkable group, so
-- find_entrances reports exactly this tile as the zone's entrance. Tests
-- that do not themselves test entrance behaviour call this once, purely so
-- build_construction/build_door/audit do not refuse the whole call for "no
-- entrance" -- appended LAST, so its ring_position is always the highest,
-- keeping every other guard's own held-list ordering (held[0], etc.)
-- unaffected; `open_tiles_found`/ring-tile counts in those tests do need
-- the +1 this tile adds.
function add_entrance_fixture(zone_id, ex, ey, ez)
  ex, ey, ez = ex or 1000, ey or 999, ez or 0
  RINGS[zone_id] = RINGS[zone_id] or {}
  table.insert(RINGS[zone_id], {ex, ey, ez})
  TILES[key(ex, ey, ez)] = {ok = true, hidden = false, shape = df.tiletype_shape.FLOOR}
  set_group(ex, ey - 1, ez, 1)
  if MAIN_GROUP == nil then MAIN_GROUP = 1 end
end

-- ---------------------------------------------------------------------------
-- Fake buildings-at-tile + jobs world (handoffs/2026-10-01-entrances-get-
-- doors.md: planned_construction_at/job_for_building/audit_constructions).
-- ---------------------------------------------------------------------------

BUILDINGS_AT_TILE = {}
JOBS = {}
df.global.world.jobs.list = JOBS

-- set_planned_building(x, y, z, building_id, build_stage, max_build_stage,
-- [building_type]) registers a building (Construction by default) at
-- (x,y,z). "planned" (audit_constructions' own meaning) when build_stage <
-- max_build_stage, matching the live bld:getBuildStage()==
-- bld:getMaxBuildStage() check df-overseer-building.lua's
-- kind_previously_built and df-overseer-zone.lua's content_row already use.
function set_planned_building(x, y, z, building_id, build_stage, max_build_stage, building_type)
  local bld = {
    id = building_id,
    _type = df.building_type[building_type or "Construction"],
    _stage = build_stage,
    _max_stage = max_build_stage,
  }
  function bld:getType() return self._type end
  function bld:getBuildStage() return self._stage end
  function bld:getMaxBuildStage() return self._max_stage end
  BUILDINGS_AT_TILE[key(x, y, z)] = bld
  return bld
end

-- add_job(bld) -- a job "attached to" `bld` via dfhack.job.getHolder, the
-- same building->job link df-overseer-stuckjobs.lua's own get_stuck_jobs
-- already reads live.
function add_job(bld)
  local job = {id = #JOBS + 1, flags = {suspend = false}, _holder = bld}
  JOBS[#JOBS + 1] = job
  return job
end

function job_suspended(bld)
  for _, job in ipairs(JOBS) do
    if job._holder == bld then return job.flags.suspend == true end
  end
  return nil
end

package.loaded = package.loaded or {}
package.loaded['df-overseer-surface'] = FAKE_SURFACE
package.loaded['df-overseer-building'] = FAKE_BUILDING
package.loaded['df-overseer-reservations'] = FAKE_RESERVATIONS
package.loaded['df-overseer-reachability'] = FAKE_REACHABILITY
package.loaded['df-overseer-connectivity'] = FAKE_CONNECTIVITY
-- 2026-10-08 siting policy: a fake hazard module. HAZARD_TILES["x,y,z"] = true makes
-- that tile refuse (the real policy has its own tests in
-- tests/test_aquifer_siting_lua_logic.py).
HAZARD_TILES = {}
package.loaded['df-overseer-hazard'] = {
  begin_scan = function() end,
  check_tile = function(x, y, z)
    if HAZARD_TILES[x .. "," .. y .. "," .. z] then return {kind = "aquifer", where = "tile", via = "revealed"} end
    return nil
  end,
  message = function(hz) return "refused by the siting policy: aquifer" end,
}
package.loaded['json'] = {encode = function(v) return "json" end}
package.loaded['utils'] = {listpairs = function(t) return ipairs(t) end}

function reqscript(name) return package.loaded[name] or {} end
function require(name) return package.loaded[name] end

dfhack_flags = {module = true}

-- ---------------------------------------------------------------------------
-- Fake quickfort + filesystem
-- ---------------------------------------------------------------------------

QUICKFORT_CALLS = {}
QUICKFORT_QUEUE = {}

function queue_quickfort(output, res)
  QUICKFORT_QUEUE[#QUICKFORT_QUEUE + 1] = {output = output, res = (res == nil) and CR_OK or res}
end

dfhack = {
  run_command_silent = function(...)
    local a = {...}
    QUICKFORT_CALLS[#QUICKFORT_CALLS + 1] = a
    local resp = table.remove(QUICKFORT_QUEUE, 1)
    if resp == nil then return "", CR_OK end
    return resp.output, resp.res
  end,
  items = {
    getPosition = function(item)
      if item._x == nil then return nil end
      return item._x, item._y, item._z
    end,
  },
  buildings = {
    findAtTile = function(pos) return BUILDINGS_AT_TILE[key(pos.x, pos.y, pos.z)] end,
  },
  job = {
    getHolder = function(job) return job._holder end,
  },
}

WRITTEN_FILES = {}

local fake_file_mt = {__index = {}}
function fake_file_mt.__index:write(s)
  self._buf = (self._buf or "") .. s
end
function fake_file_mt.__index:close()
  WRITTEN_FILES[self._path] = self._buf or ""
end

io = io or {}
io.open = function(path, mode)
  if mode == "w" then
    return setmetatable({_path = path}, fake_file_mt)
  end
  return nil, "fake io.open only supports write mode in this test"
end

os = os or {}
os.remove = function(path) WRITTEN_FILES[path] = nil; return true end
os.time = function() return 1 end
