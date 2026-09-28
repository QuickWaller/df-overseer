-- df-overseer-construction.lua
--@module = true
--
-- handoffs/2026-09-28-ore-vein-recovery-and-construction-tool.md.
-- decisions/DECISIONS.md 2026-09-24 found a real gap: this fort's room
-- pipeline smoothed an ore vein into a room's wall instead of mining it out
-- and replacing the hole with a constructed wall, because (a)
-- df-overseer-blueprint.lua's smoothable set allows mineral, so an ore vein
-- reads as an ordinary smoothable wall, and (b) NOTHING in this codebase
-- could build a construction (wall/floor/etc.) at all -- that half was
-- missing entirely, not just buggy. This file is that missing half, plus
-- the mining step that must run before it (research/2026-09-24-quickfort-
-- hands.md section 3: "the only route to a finished soil-or-vein wall is
-- two steps: dig the tile out, let the job complete, then build the
-- construction over the now-open tile -- a one-shot blueprint cannot
-- express that").
--
-- GENERALISABLE BY RULE (CLAUDE.md, "Tools must be generalisable"):
--   - `mine-vein` takes no kind at all -- ore/gem identification is read
--     from the game's own vein data (df-overseer-surface.lua's
--     decode_vein_tile, extended for exactly this by this same handoff),
--     never a hard-coded "hematite" branch.
--   - `build` takes KIND as an argument, resolved the SAME way
--     df-overseer-building.lua's own generic build tool resolves any other
--     building kind (its exported `list_kinds`, reused here rather than
--     re-implemented -- see resolve_construction_kind below). Today's live
--     case is Wall; naming Floor, Ramp, UpStair, DownStair or any other
--     construction subtype quickfort knows costs no new code here.
--
-- ZONE-ANCHORED, NEVER A RAW COORDINATE (design commitment #1): both verbs
-- take a ZONE_ID and act over that zone's own boundary ring, resolved
-- through df-overseer-surface.lua's own find_zone/ring_tiles (promoted from
-- `local` to global by this same stream specifically so this file could
-- reuse them instead of duplicating the zone-resolution/ring-walk logic --
-- see that file's header comment on the change). A real x,y,z exists only
-- inside this file's own local scope, for the instant it takes to build
-- quickfort's `-c` argument, exactly like df-overseer-building.lua's
-- build_kind and df-overseer-diggable.lua's dig_diggable_area already do.
--
-- ONE TILE, ONE BLUEPRINT APPLICATION -- not a sparse multi-cell blueprint
-- with blank cells standing for "leave this tile alone". A zone's ore/gem
-- tiles are typically a handful scattered around a ring (the motivating
-- case is 5 of a 3x3 office's 16 ring tiles), and this stream found no
-- confirmed source reading (research/2026-09-24-quickfort-hands.md does not
-- cover it) for how quickfort's #dig/#build parsers treat a blank grid
-- cell. Rather than guess at an unverified mechanism, each identified tile
-- gets its OWN 1x1 blueprint applied via `-c` at that tile's own real
-- coordinate -- the exact, already-verified shape df-overseer-diggable.lua's
-- dig-stair and df-overseer-building.lua's build_kind already use for a
-- single-cell application. Slower for many tiles, but every step is a
-- pattern this codebase has already run for real, not a new one.
--
-- ORDER IS ENFORCED BY WHAT `build` READS, NOT BY BOOKKEEPING: `build`
-- re-reads each ring tile's live shape before deciding (never assumes
-- `mine-vein` already ran, per the handoff's own instruction). A tile still
-- shaped WALL is refused by name ("not yet mined"), never silently skipped
-- or guessed open -- matching every other refuse-rather-than-guess
-- discipline in this codebase (df-overseer-diggable.lua's is_diggable,
-- df-overseer-surface.lua's tile_read).
--
-- MATERIAL CHOICE: reuses the exact policy df-overseer-building.lua's
-- 2026-09-28 material-choice fix already established for a
-- building_material filter (default to excluding the game's own "economic"
-- stone unless the caller opts in) rather than inventing a second policy.
-- That logic lives in building.lua as file-local functions, not exported,
-- so a materially IDENTICAL, shortened version is duplicated here
-- (`material_report`) purely as ADVISORY reporting -- the real
-- `quickfort run` call below, like building.lua's own build_kind, has no
-- way to force quickfort/buildingplan to pick a specific material; only
-- reporting what is available and what would default is possible from
-- outside. Same reqscript-coupling-avoidance call this codebase already
-- makes repeatedly (df-overseer-diggable.lua's parse_quickfort_stats,
-- df-overseer-building.lua's own stock scan next to stocks_mod).
--
-- Usage: ./dfhack-run df-overseer-construction mine-vein ZONE_ID [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-construction build ZONE_ID KIND [DRY_RUN]

local json = require('json')
local surface_mod = reqscript('df-overseer-surface')
local building_mod = reqscript('df-overseer-building')

local NULL = "\0"
local function nn(v) if v == nil then return NULL end return v end
local function encode(v) return json.encode(v, {null = NULL}) end

-- Same bound as df-overseer-surface.lua's own MAX_RING_TILES (duplicated,
-- not reqscript'd, so this file's own refusal message is self-contained;
-- kept numerically identical on purpose).
local MAX_RING_TILES = 900

local function truthy_dry_run(v)
  if v == nil then return true end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- ---------------------------------------------------------------------------
-- Reaching df-overseer-surface.lua's zone-resolution/ring-walk/vein-decode
-- WITHOUT promoting them to globals there (see that file's own header on
-- `find_zone`: promoting them broke df-overseer-blueprint.lua's rectangle
-- shim, which depends on find_zone staying a real upvalue of
-- enclosure/finish/boundary_material). Same `debug.getupvalue` idiom
-- df-overseer-building.lua already uses to reach quickfort's own local
-- table (`upvalue_by_name` there), duplicated here rather than reqscript'd
-- (it is file-local in building.lua too). `vein_material` is the one
-- exported function that closes over find_zone/ring_tiles/decode_vein_tile;
-- decode_vein_tile itself closes over tile_read, so it takes a second hop.
-- Every hop that could vanish in a future surface.lua edit reports which
-- hop it was, never a silent nil.
-- ---------------------------------------------------------------------------

local function upvalue_by_name(fn, want)
  if type(fn) ~= 'function' then return nil end
  local i = 1
  while true do
    local n, v = debug.getupvalue(fn, i)
    if n == nil then return nil end
    if n == want then return v end
    i = i + 1
  end
end

local function surface_hooks()
  if type(debug) ~= 'table' or type(debug.getupvalue) ~= 'function' then
    return nil, "debug.getupvalue is not available in this DFHack Lua"
  end
  local vm = surface_mod.vein_material
  if type(vm) ~= 'function' then
    return nil, "df-overseer-surface.lua no longer exports vein_material"
  end
  local find_zone = upvalue_by_name(vm, 'find_zone')
  local ring_tiles = upvalue_by_name(vm, 'ring_tiles')
  local decode_vein_tile = upvalue_by_name(vm, 'decode_vein_tile')
  if not (find_zone and ring_tiles and decode_vein_tile) then
    return nil, "vein_material no longer closes over find_zone/ring_tiles/decode_vein_tile by those names"
  end
  local tile_read = upvalue_by_name(decode_vein_tile, 'tile_read')
  if not tile_read then
    return nil, "decode_vein_tile no longer closes over tile_read by that name"
  end
  return {find_zone = find_zone, ring_tiles = ring_tiles, decode_vein_tile = decode_vein_tile, tile_read = tile_read}
end

-- ---------------------------------------------------------------------------
-- Blueprint plumbing: one tile, one application. Mirrors
-- df-overseer-building.lua's write_blueprint/parse_quickfort_stats exactly
-- (duplicated rather than reqscript'd -- both are file-local there).
-- ---------------------------------------------------------------------------

local function write_single_cell_blueprint(mode, cell, tag)
  local filename = string.format("_tmp-construction-%s-%s-%d.csv", tag, cell, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then return nil, "could not open blueprint for writing: " .. tostring(open_err) end
  f:write("#" .. mode .. "\n" .. cell .. "\n")
  f:close()
  return filename
end

local function parse_quickfort_stats(output)
  local stats = {}
  if not output then return stats end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then stats[label] = tonumber(value) end
  end
  return stats
end

-- `label` is the one stat that counts a successful designation ("Tiles
-- designated for digging" for #dig, "Buildings designated" for #build --
-- research/2026-09-24-quickfort-hands.md sections 2-3); every OTHER stat
-- quickfort printed is a problem counter, same rule
-- df-overseer-building.lua's assess_quickfort already established (a
-- negative control there found quickfort returns CR_OK even when it
-- designated nothing).
local function assess(ran, res, stats, label)
  local problems = {}
  if not ran then return false, problems end
  for l, n in pairs(stats or {}) do
    if l ~= label and n ~= 0 then
      problems[#problems + 1] = l .. ": " .. tostring(n)
    end
  end
  table.sort(problems)
  local designated = (stats or {})[label] or 0
  return (res == CR_OK and designated >= 1 and #problems == 0), problems
end

-- Applies one single-cell blueprint at (x, y, z) via `-c`, real coordinate
-- used only for the instant it takes to build this argument (never
-- returned). Returns a result record; the blueprint file is always removed
-- afterward, dry run or real.
local function apply_single_cell(mode, cell, x, y, z, dry, label, tag)
  local filename, werr = write_single_cell_blueprint(mode, cell, tag)
  if not filename then
    return {ok = false, error = werr}
  end
  local coord = string.format('%d,%d,%d', x, y, z)
  local ok_run, output, res
  if dry then
    ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord, '-d')
  else
    ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord)
  end
  local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
  local stats = ok_run and parse_quickfort_stats(output) or nil
  local ok_v, problems = assess(ok_run, res, stats, label)
  return {
    ok = ok_v,
    problems = problems,
    error = (not ok_run) and tostring(output) or nil,
    stats = stats,
    blueprint_removed = (ok_rm and rm == true),
  }
end

-- ---------------------------------------------------------------------------
-- mine-vein ZONE_ID [DRY_RUN]
-- ---------------------------------------------------------------------------

function mine_vein(zone_id, dry_run)
  local hooks, herr = surface_hooks()
  if not hooks then return {error = herr} end
  local b, err = hooks.find_zone(zone_id)
  if not b then return {error = err} end
  local ring = hooks.ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local dry = truthy_dry_run(dry_run)

  local candidates, already_open, refused = {}, {}, {}
  for i, xyz in ipairs(ring) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local rec = hooks.decode_vein_tile(x, y, z)
    if rec.vein_status == "ore_or_gem" then
      local t = hooks.tile_read(x, y, z)
      if t.ok and not t.hidden and t.shape == df.tiletype_shape.WALL then
        candidates[#candidates + 1] = {ring_position = i, x = x, y = y, z = z, mineral_name = rec.mineral_name}
      elseif t.ok and not t.hidden then
        already_open[#already_open + 1] = string.format(
          "ring tile %d (%s): already open, nothing to mine", i, tostring(rec.mineral_name))
      else
        refused[#refused + 1] = string.format(
          "ring tile %d (%s): could not confirm its current shape (%s); refusing to designate rather than guess",
          i, tostring(rec.mineral_name), t.err or "hidden")
      end
    elseif rec.vein_status == "unknown" or rec.vein_status == "unreadable" then
      refused[#refused + 1] = string.format(
        "ring tile %d: vein classification %s%s; refusing to designate rather than guess it is ore",
        i, rec.vein_status, rec.error and (" (" .. rec.error .. ")") or "")
    end
    -- not_mineral / not_economic / hidden: not ore, not listed as refused --
    -- confidently NOT a candidate, not an unclassifiable one.
  end

  local results = {}
  for _, c in ipairs(candidates) do
    local r = apply_single_cell('dig', 'd', c.x, c.y, c.z, dry, 'Tiles designated for digging', 'mine')
    results[#results + 1] = {
      ring_position = c.ring_position,
      mineral_name = c.mineral_name,
      dry_run = dry,
      ok = r.ok,
      problems = r.problems,
      error = nn(r.error),
      stats = (r.stats and next(r.stats)) and r.stats or {},
    }
  end

  return {
    zone_id = b.id,
    boundary_ring_tiles = #ring,
    ore_tiles_found = #candidates,
    already_open = already_open,
    refused = refused,
    dry_run = dry,
    results = results,
  }
end

-- ---------------------------------------------------------------------------
-- Material choice (advisory only -- see header)
-- ---------------------------------------------------------------------------

-- Duplicated from df-overseer-building.lua's item_is_available (file-local
-- there): the same five-flag "available" gate (in_job, forbid, owned,
-- in_building, construction) plus the trader/garbage_collect/removed
-- fort-ownership check.
local function item_is_available(item)
  local ok_f, f = pcall(function() return item.flags end)
  if not ok_f then return nil, "could not read item.flags" end
  local ok_t, trader = pcall(function() return f.trader end)
  if not ok_t then return nil, "could not read item.flags.trader" end
  if trader then return false end
  local ok_gc, gc = pcall(function() return f.garbage_collect end)
  if ok_gc and gc then return false end
  local ok_rm, rm = pcall(function() return f.removed end)
  if ok_rm and rm then return false end
  for _, flag in ipairs({"in_job", "forbid", "owned", "in_building", "construction"}) do
    local ok, v = pcall(function() return f[flag] end)
    if not ok then return nil, "could not read item.flags." .. flag end
    if v then return false end
  end
  return true
end

-- Duplicated from df-overseer-building.lua's decode_item_material.
-- UNVERIFIED LIVE (inherited caveat, same as there): dfhack.matinfo.decode's
-- exact field names (.material.id, .inorganic.economic_uses) were not
-- independently re-confirmed by this stream.
local function decode_item_material(item)
  if type(dfhack.matinfo) ~= 'table' or type(dfhack.matinfo.decode) ~= 'function' then
    return nil, "dfhack.matinfo.decode is not available on this DFHack Lua"
  end
  local ok, mi = pcall(dfhack.matinfo.decode, item)
  if not ok or mi == nil then
    return nil, "dfhack.matinfo.decode failed: " .. tostring(mi)
  end
  local name
  local ok_n, id = pcall(function() return mi.material and mi.material.id end)
  if ok_n and id and id ~= "" then name = tostring(id) end
  if not name then name = "material_unknown" end
  local economic
  local ok_i, inorg = pcall(function() return mi.inorganic end)
  if ok_i and inorg then
    local ok_u, uses = pcall(function() return inorg.economic_uses end)
    if ok_u and uses ~= nil then economic = (#uses > 0) end
  else
    economic = false
  end
  return {name = name, economic = economic}
end

-- A lean, advisory-only version of building.lua's material_breakdown +
-- resolve_material_choice: what boulder/log/block stock exists, broken
-- down by decoded material, defaulting to excluding economic material.
-- Never gates the real quickfort call below (see header: quickfort has no
-- parameter for this from outside).
local BUILDING_MATERIAL_TYPES = {"BOULDER", "WOOD", "BLOCKS"}

local function material_report()
  local by_name, errors = {}, {}
  for _, type_name in ipairs(BUILDING_MATERIAL_TYPES) do
    local ok_vec, vec = pcall(function() return df.global.world.items.other[type_name] end)
    if ok_vec and vec then
      for i = 0, #vec - 1 do
        local item = vec[i]
        local avail, avail_err = item_is_available(item)
        if avail == nil then
          errors[#errors + 1] = type_name .. " item: " .. tostring(avail_err)
        elseif avail then
          local mat, mat_err = decode_item_material(item)
          if not mat then
            errors[#errors + 1] = type_name .. " item: " .. tostring(mat_err)
          else
            local rec = by_name[mat.name]
            if not rec then
              rec = {name = mat.name, economic = mat.economic, units = 0}
              by_name[mat.name] = rec
            end
            rec.units = rec.units + 1
          end
        end
      end
    end
  end
  local materials, excluded = {}, {}
  for _, m in pairs(by_name) do materials[#materials + 1] = m end
  table.sort(materials, function(a, b)
    if a.units ~= b.units then return a.units > b.units end
    return a.name < b.name
  end)
  local eligible = {}
  for _, m in ipairs(materials) do
    if m.economic == true then
      excluded[#excluded + 1] = m.name
    else
      eligible[#eligible + 1] = m
    end
  end
  local note
  if #eligible > 0 then
    note = "default: highest-stock non-economic material would be " .. eligible[1].name
      .. "; buildingplan/quickfort makes the real choice at build time, this is advisory only"
  elseif #materials > 0 then
    note = "only economic material(s) available (" .. table.concat(excluded, ", ") .. "); advisory only"
  else
    note = "no boulder/log/block stock found"
  end
  return {materials = materials, excluded_materials = excluded, note = note, scan_errors = errors}
end

-- ---------------------------------------------------------------------------
-- build ZONE_ID KIND [DRY_RUN]
-- ---------------------------------------------------------------------------

-- Resolves KIND to a quickfort key through df-overseer-building.lua's own
-- exported list_kinds (never re-implemented): exact, case-insensitive match
-- on token or subtype name, restricted to type "Construction" -- the
-- generalisable hook the header promises (Floor, Ramp, UpStair, ... cost no
-- new code here, only a different KIND string).
local function resolve_construction_kind(kind_name)
  local kinds, err = building_mod.list_kinds(kind_name)
  if not kinds then return nil, "could not read building kinds: " .. tostring(err) end
  local q = tostring(kind_name or ""):lower()
  local matches = {}
  for _, k in ipairs(kinds) do
    if k.type == "Construction" then
      local subtype = (k.subtype ~= NULL) and tostring(k.subtype) or nil
      if k.token:lower() == q or (subtype and subtype:lower() == q) then
        matches[#matches + 1] = k
      end
    end
  end
  if #matches == 0 then
    local hints = {}
    for _, k in ipairs(kinds) do
      if k.type == "Construction" then hints[#hints + 1] = k.token end
    end
    local msg = "unknown construction kind: " .. tostring(kind_name)
    if #hints > 0 then msg = msg .. "; construction kinds this install knows: " .. table.concat(hints, ", ") end
    return nil, msg
  end
  if #matches > 1 then
    return nil, "ambiguous construction kind " .. tostring(kind_name) .. ": ambiguity this tool did not expect"
  end
  return matches[1]
end

function build_construction(zone_id, kind_name, dry_run)
  local k, kerr = resolve_construction_kind(kind_name)
  if not k then return {error = kerr} end
  local hooks, herr = surface_hooks()
  if not hooks then return {error = herr} end
  local b, err = hooks.find_zone(zone_id)
  if not b then return {error = err} end
  local ring = hooks.ring_tiles(b)
  if #ring > MAX_RING_TILES then
    return {error = "zone " .. b.id .. "'s boundary ring is " .. #ring
      .. " tiles, over this tool's " .. MAX_RING_TILES .. "-tile bound; refusing rather than scanning it"}
  end
  local dry = truthy_dry_run(dry_run)

  local candidates, refused = {}, {}
  for i, xyz in ipairs(ring) do
    local x, y, z = xyz[1], xyz[2], xyz[3]
    local t = hooks.tile_read(x, y, z)
    if not t.ok then
      refused[#refused + 1] = string.format("ring tile %d: could not read its shape (%s); refusing to guess", i, t.err)
    elseif t.hidden then
      refused[#refused + 1] = string.format("ring tile %d: hidden; refusing to guess it is open", i)
    elseif t.shape == df.tiletype_shape.WALL then
      refused[#refused + 1] = string.format("ring tile %d: still a wall, not yet mined; run mine-vein first", i)
    else
      candidates[#candidates + 1] = {ring_position = i, x = x, y = y, z = z}
    end
  end

  local results = {}
  for _, c in ipairs(candidates) do
    local r = apply_single_cell('build', k.key, c.x, c.y, c.z, dry, 'Buildings designated', 'build')
    results[#results + 1] = {
      ring_position = c.ring_position,
      dry_run = dry,
      ok = r.ok,
      problems = r.problems,
      error = nn(r.error),
      stats = (r.stats and next(r.stats)) and r.stats or {},
    }
  end

  return {
    zone_id = b.id,
    kind = {token = k.token, key = k.key, label = k.label, type = k.type, subtype = k.subtype},
    boundary_ring_tiles = #ring,
    open_tiles_found = #candidates,
    refused = refused,
    dry_run = dry,
    material_report = material_report(),
    results = results,
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
  print(encode(result))
end

if cmd == "mine-vein" then
  if not args[2] then
    print("usage: df-overseer-construction mine-vein ZONE_ID [DRY_RUN]")
  else
    emit(mine_vein(args[2], args[3]))
  end
elseif cmd == "build" then
  if not (args[2] and args[3]) then
    print("usage: df-overseer-construction build ZONE_ID KIND [DRY_RUN]")
  else
    emit(build_construction(args[2], args[3], args[4]))
  end
else
  print("usage: df-overseer-construction mine-vein ZONE_ID [DRY_RUN]")
  print("usage: df-overseer-construction build ZONE_ID KIND [DRY_RUN]")
end
