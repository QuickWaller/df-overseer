-- df-overseer-blueprint.lua
--@module = true
--
-- handoffs/2026-09-24-blueprint-hands.md: the Architect's hands. One generic
-- verb that applies any quickfort template or named blueprint to a site, and
-- then re-reads the game to say whether the room really came out enclosed and
-- finished, not merely that designations were queued. Everything this file
-- assumes about quickfort was read from the installed source and is written
-- up, with file:line cites and a verified/inferred split, in
-- research/2026-09-24-quickfort-hands.md. Read that before changing this.
--
-- WHAT IT IS, AND IS NOT. Generic: it takes a template or blueprint NAME and
-- reads everything that differs per room from that blueprint's own .csv (its
-- sections, their modes, their footprint, which cells ask for a smooth
-- finish, which cell block is the room's zone). There is no `if kind ==
-- "bedroom"` anywhere: the cost of the next room type is one .csv, deployed
-- where quickfort can resolve it. It is a wrapper, not a reimplementation:
-- quickfort does the designating, this file decides where, in what order,
-- and whether it worked.
--
-- WHERE THE BLUEPRINT FILE COMES FROM. `dfhack-config/blueprints/templates/
-- NAME.csv` on the guest, else `dfhack-config/blueprints/NAME.csv` (the
-- starter files' flat layout). NAME is a bare identifier
-- ([A-Za-z0-9_-]+): never a path. Deploying the .csv there is a deploy step
-- (plain scp, same as the starter files; blueprints/README.md), not this
-- file's job. The .yaml metadata beside a template in the repo is for people
-- and dfmcp; this file never reads it (a guest has no YAML parser, and the
-- .csv is the single source of truth for everything below).
--
-- SITE REFERENCE WITHOUT COORDINATES (task item 3). Three options were
-- weighed:
--   1. A zone id. Rejected as the primary handle: a new room has no zone
--      until its zone blueprint runs, which is after the dig this verb has
--      to place first, and a zone id names a rectangle the caller did not
--      choose the shape of.
--   2. A landmark plus an offset. Rejected: an offset is a coordinate in
--      disguise, exactly what design commitment #1 forbids a model to emit.
--   3. The siblings' own convention, kept: a NEW site is `landmark + LEVEL +
--      RANK (+ RADIUS)`, ranked by the very same finder the Architect already
--      read (df-overseer-diggable.lua's ranked_candidates, so RANK N here is
--      the N-th candidate diggable.find showed it); and a site that has been
--      carved is then named by an OPAQUE HANDLE, `site-N`, issued by the first
--      real apply and stored (with its real top-left tile) in DFHack's own
--      per-site persistent state. Every later phase, re-read and listing
--      names the site by handle. The coordinate exists only in that stored
--      table and in local variables building quickfort's `-c` argument; it is
--      never printed, returned or logged. This is what makes multi-phase
--      templates possible at all: after the shell is dug the tiles are no
--      longer diggable, so a caller cannot re-find the site by ranking, and
--      it has no other stable way to refer to it.
-- The two forms share one argument, SITE: `site-N` is a handle; anything else
-- is a landmark name and means "find a new site" (dig phases only). A
-- landmark literally named like `site-3` is therefore unreachable; the
-- landmark list should never contain one.
--
-- SURFACE RE-READ, VIA A SHIM (task item 2). df-overseer-surface.lua's four
-- reads are anchored on a ZONE id, and a freshly dug shell has no zone. Its
-- module-local `find_zone(zone_id)` is the only thing that turns an id into
-- a rectangle, and it reads exactly x1/y1/x2/y2/z/id off the result. So this
-- file, for the duration of one read, swaps that upvalue for a function that
-- returns the room rectangle (the bounding box of the template's own zone
-- section), calls the surface layer's `enclosure`, `finish` and
-- `boundary_material` unchanged, and restores the original in every case.
-- That is fragile in exactly the way df-overseer-building.lua's own
-- upvalue read of quickfort's table is fragile, and it is guarded the same
-- way: if the upvalue is not there, or the swap does not take effect in all
-- three functions, `surface.error` says so and nothing pretends to have
-- been read. tests/test_blueprint_tool_manifest.py pins the upvalue's name in
-- df-overseer-surface.lua so a rename fails offline. A permanent fix is for
-- surface.lua to export rectangle-anchored variants; that file is another
-- stream's, so it is recorded as owed, not done here.
--
-- SOIL RULE IN DATA (task item 4). "Finish required" is not a table in this
-- file: it is every `s` cell of the blueprint's dig sections, i.e. the
-- template's own declaration. Before a dig phase runs, each such cell's
-- tile is classified with the same test quickfort itself applies
-- (dig.lua:77-87 hard_natural_materials, dig.lua:288-297 do_smooth: STONE,
-- FEATURE, LAVA_STONE, MINERAL, FROZEN_LIQUID can be smoothed; SOIL and
-- anything else cannot; hidden tiles cannot be smoothed until revealed) and
-- the result is reported as `finish_plan`: how many cells will smooth, how
-- many are already finished, and, by material name, how many CANNOT be
-- smoothed. `finish_required_met` is false while any cannot, with a `remedy`
-- that says what the blocked tiles need. The verb does not pick a material
-- or resolve the wall itself: a standing soil wall cannot be built over
-- either (build.lua:107-165 refuses WALL shape), so the only route is dig
-- then construct, two applications a completed dig apart; that remains a
-- gap, named in the research doc, and this verb reports it rather than
-- leaving rough soil silently.
--
-- ORDER GUARD. quickfort applies whatever it is told, in whatever order
-- (meta.lua applies its sections back to back in one tick), and a bed or zone
-- designated on a still-solid tile is silently dropped. So a phase whose
-- sections include build, zone or place is refused, before quickfort is
-- called, while the site still has outstanding dig/smooth designations or
-- any `d`-type cell still WALL-shaped. This is by MODE, not by template.
--
-- BOUNDED: the site rectangle is at most MAX_SITE_TILES tiles; every read is
-- over that rectangle or its one-tile ring. A read failure on a visible tile
-- goes to `read_failures` and dfhack.printerr, never to a default (the
-- ACT/SENSE and read-failure discipline of df-overseer-surface.lua).
--
-- NEVER RETURNED: any coordinate, the raw quickfort output (it can contain
-- "removing existing job at X, Y, Z"; only lines matching the statistics
-- pattern are read). No rendered map, only counts.
--
-- READ vs MUTATE. `preview` is a dry run and is `effect: read`: quickfort's
-- `-d` writes nothing in dig, build or zone modes (dig.lua:856-880, 908-910;
-- build.lua:1346-1354; zone.lua:356-359, verified from source, not yet
-- observed live). `apply` defaults to a dry run too and is `effect: mutate`.
-- Only an explicit DRY_RUN=false writes, and that path is UNTESTED live:
-- the handoff forbids running it, and the live check is in its Result.
--
-- Usage: ./dfhack-run df-overseer-blueprint plan TEMPLATE
-- Usage: ./dfhack-run df-overseer-blueprint preview TEMPLATE PHASE SITE [LEVEL] [RANK] [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-blueprint apply TEMPLATE PHASE SITE [DRY_RUN] [LEVEL] [RANK] [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-blueprint sites
-- Usage: ./dfhack-run df-overseer-blueprint status SITE_ID

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local diggable_mod = reqscript('df-overseer-diggable')
local surface_mod = reqscript('df-overseer-surface')

local NULL = "\0"
local function encode(v) return json.encode(v, {null = NULL}) end
local function nn(v) if v == nil then return NULL end return v end
local function empty_object()
  return setmetatable({}, {__tostring = function() return "JSON object" end})
end

local STATE_KEY = 'df-overseer-blueprint_v1'
local MAX_SITE_TILES = 2500      -- 50x50: no real room comes close
local MAX_META_DEPTH = 4
local BLUEPRINT_DIR = 'dfhack-config/blueprints/'

-- Section modes this file understands the cells of. Others are skipped for
-- geometry (notes, aliases) or refused (see supported_modes below).
local GRID_MODES = {dig = true, build = true, place = true, zone = true, meta = true}
-- Modes that need solid tiles already dug: refused while the shell is pending.
local NEEDS_DUG_SHELL = {build = true, place = true, zone = true}
-- Symbols whose meaning in a `dig` section is "this cell is carved out".
local CARVE_SYMBOLS = {d = true, h = true, u = true, j = true, i = true, r = true}
local SMOOTH_SYMBOL = 's'

-- What quickfort prints that is progress, not a problem (command.lua:183-196,
-- dig.lua:890-901, build.lua:1321-1324, zone.lua:388-395, meta.lua:83).
local LABEL_DIG = "Tiles designated for digging"
local LABEL_ZONES = "Zones designated"
local LABEL_BUILDINGS = "Buildings designated"
local LABEL_ZONE_TILES = "Zone tiles designated"
local LABEL_META = "Blueprints applied"
local PROGRESS_LABELS = {
  [LABEL_DIG] = true, [LABEL_ZONES] = true, [LABEL_BUILDINGS] = true,
  [LABEL_ZONE_TILES] = true, [LABEL_META] = true,
}

-- ---------------------------------------------------------------------------
-- Small helpers
-- ---------------------------------------------------------------------------

local function valid_name(s)
  return type(s) == 'string' and #s > 0 and #s <= 80 and s:match('^[%w_%-]+$') ~= nil
end

local function truthy_dry_run(v)
  if v == nil then return true end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

local function shape_of(tt) return df.tiletype.attrs[tt].shape end

local function material_name(mat)
  local ok, name = pcall(function() return df.tiletype_material[mat] end)
  return (ok and name) or ("<unknown:" .. tostring(mat) .. ">")
end

-- quickfort's own notion of a smoothable ("hard") natural material,
-- dig.lua:77-87. Copied, not reqscript'd: hard_natural_materials is a local
-- of a quickfort internal. If quickfort's set ever changes, the live check's
-- finish_plan versus quickfort's own "could not be designated" counter will
-- disagree, which is how a drift shows.
local SMOOTHABLE_MATERIALS = {}
for _, name in ipairs({"STONE", "FEATURE", "LAVA_STONE", "MINERAL", "FROZEN_LIQUID"}) do
  local mat = df.tiletype_material[name]
  if mat ~= nil then SMOOTHABLE_MATERIALS[mat] = true end
end

local function upvalue_by_name(fn, want)
  if type(fn) ~= 'function' then return nil end
  local i = 1
  while true do
    local n, v = debug.getupvalue(fn, i)
    if n == nil then return nil end
    if n == want then return v, i end
    i = i + 1
  end
end

-- ---------------------------------------------------------------------------
-- Reading the blueprint file (the only source of per-template facts)
-- ---------------------------------------------------------------------------

local function read_file(path)
  local f, err = io.open(path, 'r')
  if not f then return nil, tostring(err) end
  local text = f:read('*a')
  f:close()
  return text
end

-- Returns quickfort_name, text  or nil, err.
local function locate_blueprint(name)
  if not valid_name(name) then
    return nil, "blueprint name must be a bare identifier (letters, digits, _ or -), got a value that is not"
  end
  local tried = {}
  for _, rel in ipairs({'templates/' .. name .. '.csv', name .. '.csv'}) do
    local text = read_file(BLUEPRINT_DIR .. rel)
    if text then return rel, text end
    tried[#tried + 1] = rel
  end
  return nil, "no blueprint '" .. name .. "' on the guest (looked for " ..
    table.concat(tried, " and ") .. " under dfhack-config/blueprints/); deploy the .csv first"
end

-- Parses quickfort's multi-section .csv into sections. Only what this file
-- needs: each section's mode, label, modeline flags, and its non-empty cells
-- as {x, y, text}, 1-based, with (1,1) the blueprint's top-left cell.
-- Rules mirrored from quickfort (parse.lua modeline grammar): a line
-- beginning `#` followed by a valid mode word starts a section; in a grid
-- row a cell beginning `#` starts a comment and ends the row; a cell of a
-- single backtick is quickfort's "ignore this cell". Blank lines count as
-- rows. Sections of mode notes/aliases/ignore are recorded but carry no cells.
local VALID_MODES = {dig = true, build = true, place = true, zone = true,
  burrow = true, meta = true, notes = true, ignore = true, aliases = true}

local function parse_sections(text)
  local sections, cur = {}, nil
  local unnamed = 0
  for raw in (text .. "\n"):gmatch("([^\n]*)\n") do
    local line = raw:gsub("\r$", "")
    local mode = line:match("^#(%a+)")
    if mode and VALID_MODES[mode] then
      unnamed = unnamed + 1
      cur = {
        mode = mode,
        label = line:match("label%(([^)]*)%)") or tostring(unnamed),
        has_start = line:find("start%(") ~= nil,
        has_hidden = line:find("hidden%(") ~= nil,
        cells = {}, row = 0, w = 0, h = 0,
      }
      sections[#sections + 1] = cur
    elseif cur and GRID_MODES[cur.mode] then
      cur.row = cur.row + 1
      local x = 0
      for cell in (line .. ","):gmatch("([^,]*),") do
        x = x + 1
        local t = cell:match("^%s*(.-)%s*$")
        if t:sub(1, 1) == "#" then break end
        if #t > 0 and t ~= "`" then
          cur.cells[#cur.cells + 1] = {x = x, y = cur.row, text = t}
          if x > cur.w then cur.w = x end
          if cur.row > cur.h then cur.h = cur.row end
        end
      end
    end
  end
  return sections
end

local function section_by_label(sections, label)
  for _, s in ipairs(sections) do
    if s.label == label then return s end
  end
  return nil
end

-- The leaf (non-meta) sections a phase resolves to, in application order.
-- A meta section's cells each name another section (`/label`, possibly with
-- modifiers after a space). Cycle- and depth-guarded.
local function leaf_sections(sections, sec, out, depth, path)
  out = out or {}
  depth = depth or 0
  path = path or {}
  if depth > MAX_META_DEPTH then return nil, "meta nesting deeper than " .. MAX_META_DEPTH end
  if sec.mode ~= "meta" then
    out[#out + 1] = sec
    return out
  end
  if path[sec.label] then return nil, "meta blueprint '" .. sec.label .. "' refers to itself" end
  path[sec.label] = true
  table.sort(sec.cells, function(a, b)
    if a.y ~= b.y then return a.y < b.y end
    return a.x < b.x
  end)
  local refs = 0
  for _, c in ipairs(sec.cells) do
    local ref = c.text:match("^/?([^%s]+)")
    local target = ref and section_by_label(sections, ref)
    if not target then
      return nil, "meta '" .. sec.label .. "' names a section '" .. tostring(ref) .. "' the file does not have"
    end
    refs = refs + 1
    local ok, err = leaf_sections(sections, target, out, depth + 1, path)
    if not ok then return nil, err end
  end
  path[sec.label] = nil
  sec.meta_refs = refs
  return out
end

-- Everything the rest of the file needs to know about a blueprint.
local function load_blueprint(name)
  local qname, text = locate_blueprint(name)
  if not qname then return nil, text end
  local sections = parse_sections(text)
  if #sections == 0 then return nil, "no quickfort sections found in " .. qname end
  local w, h = 0, 0
  local room = nil
  for _, s in ipairs(sections) do
    if s.has_start or s.has_hidden then
      return nil, "section '" .. s.label .. "' uses start() or hidden(), which shift the origin; this verb does not support that"
    end
    if GRID_MODES[s.mode] and s.mode ~= "meta" then
      if s.w > w then w = s.w end
      if s.h > h then h = s.h end
    end
    if s.mode == "zone" and not room and #s.cells > 0 then
      local x1, y1, x2, y2 = 1e9, 1e9, 0, 0
      for _, c in ipairs(s.cells) do
        x1 = math.min(x1, c.x); y1 = math.min(y1, c.y)
        x2 = math.max(x2, c.x); y2 = math.max(y2, c.y)
      end
      room = {x1 = x1, y1 = y1, x2 = x2, y2 = y2}
    end
  end
  if w == 0 or h == 0 then return nil, "blueprint has no cells to apply" end
  return {name = name, qname = qname, sections = sections, w = w, h = h, room = room}
end

-- ---------------------------------------------------------------------------
-- Site state (coordinates live here, server side only)
-- ---------------------------------------------------------------------------

local function load_state()
  return dfhack.persistent.getSiteData(STATE_KEY, {next_id = 1, sites = {}})
end
local function save_state(state)
  dfhack.persistent.saveSiteData(STATE_KEY, state)
end

local function is_handle(s)
  return type(s) == 'string' and s:match('^site%-%d+$') ~= nil
end

local function site_brief(site)
  local cx = site.x + math.floor((site.w - 1) / 2)
  local cy = site.y + math.floor((site.h - 1) / 2)
  local ok, info = pcall(landmarks_mod.nearest_landmark, cx, cy, site.z)
  info = ok and info or nil
  return {
    near_landmark = nn(info and info.name),
    direction = nn(info and info.direction),
    distance_tiles = nn(info and info.distance_tiles),
  }
end

-- New-site finder: the same ranking diggable.find showed the caller.
local function find_new_site(bp, near, level, rank, radius)
  local ranked = upvalue_by_name(diggable_mod.find_diggable_area, 'ranked_candidates')
  if type(ranked) ~= 'function' then
    return nil, "df-overseer-diggable no longer has a ranked_candidates upvalue on find_diggable_area; the site finder cannot be reached (see this file's header)"
  end
  rank = rank or 1
  local ok, chosen, err, z = pcall(ranked, bp.w, bp.h, level, near, radius)
  if not ok then return nil, "site search failed: " .. tostring(chosen) end
  if err then return nil, err end
  if rank < 1 or rank > #chosen then
    return nil, string.format("no candidate at rank %d (found %d near %s for a %dx%d footprint)",
      rank, #chosen, near, bp.w, bp.h)
  end
  local c = chosen[rank]
  return {x = c.x, y = c.y, z = z, w = bp.w, h = bp.h, any_hidden = c.any_hidden and true or false}
end

-- ---------------------------------------------------------------------------
-- Tile reads over the site rectangle
-- ---------------------------------------------------------------------------

local function tile_info(x, y, z)
  if not dfhack.maps.isValidTilePos(x, y, z) then return {ok = false, err = "invalid tile position"} end
  local okv, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not okv then return {ok = false, err = "isTileVisible failed: " .. tostring(visible)} end
  if not visible then return {ok = true, hidden = true} end
  local ok, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok or not tt or tt < 0 then return {ok = false, err = "getTileType failed: " .. tostring(tt)} end
  local oka, attrs = pcall(function() return df.tiletype.attrs[tt] end)
  if not oka or not attrs then return {ok = false, err = "tiletype attrs read failed"} end
  local occupied = false
  local okb, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(x, y, z))
  if okb and bld then occupied = true end
  return {ok = true, hidden = false, shape = attrs.shape, material = attrs.material,
    special = attrs.special, occupied = occupied}
end

local function note_failure(failures, where, err)
  failures[#failures + 1] = where .. ": " .. tostring(err)
  pcall(function() dfhack.printerr("df-overseer-blueprint: read failure, " .. where .. ": " .. tostring(err)) end)
end

-- Outstanding dig/smooth designations inside the site rectangle: the proof
-- that quickfort's designations landed (and, later, that they are done).
local function count_pending(site, failures)
  local n = 0
  for x = site.x, site.x + site.w - 1 do
    for y = site.y, site.y + site.h - 1 do
      local ok, flags = pcall(dfhack.maps.getTileFlags, xyz2pos(x, y, site.z))
      if not ok or not flags then
        note_failure(failures, "pending designations", flags)
      elseif flags.dig ~= df.tile_dig_designation.No or flags.smooth > 0 then
        n = n + 1
      end
    end
  end
  return n
end

-- The template's finish requirement, classified against the CURRENT tiles.
-- Data-driven: the cells are the blueprint's own `s` cells in dig sections.
local function finish_state(site, leaves, failures)
  local out = {
    required_cells = 0, smoothable = 0, already_finished = 0,
    blocked_by_material = {}, blocked_total = 0,
    occupied_by_building = 0, hidden = 0, other_shape = 0, unreadable = 0,
  }
  for _, sec in ipairs(leaves) do
    if sec.mode == "dig" then
      for _, c in ipairs(sec.cells) do
        if c.text == SMOOTH_SYMBOL then
          out.required_cells = out.required_cells + 1
          local t = tile_info(site.x + c.x - 1, site.y + c.y - 1, site.z)
          if not t.ok then
            out.unreadable = out.unreadable + 1
            note_failure(failures, "finish cell", t.err)
          elseif t.hidden then
            out.hidden = out.hidden + 1
          elseif t.material == df.tiletype_material.CONSTRUCTION
              or (t.special == df.tiletype_special.SMOOTH and SMOOTHABLE_MATERIALS[t.material]) then
            -- The material test matters: DFHack reuses the SMOOTH numeric slot
            -- for a tree's own trunk pillar (df-overseer-surface.lua header).
            out.already_finished = out.already_finished + 1
          elseif t.occupied then
            -- quickfort drops these silently and uncounted (dig.lua:842-844)
            out.occupied_by_building = out.occupied_by_building + 1
          elseif t.shape ~= df.tiletype_shape.WALL and t.shape ~= df.tiletype_shape.FLOOR then
            out.other_shape = out.other_shape + 1
          elseif SMOOTHABLE_MATERIALS[t.material] then
            out.smoothable = out.smoothable + 1
          else
            local name = material_name(t.material)
            out.blocked_by_material[name] = (out.blocked_by_material[name] or 0) + 1
            out.blocked_total = out.blocked_total + 1
          end
        end
      end
    end
  end
  if next(out.blocked_by_material) == nil then out.blocked_by_material = empty_object() end
  return out
end

local function remedy_for(fin)
  if fin.blocked_total > 0 then
    return "These wall tiles are a material quickfort cannot smooth (soil is not smoothable in this DFHack, "
      .. "dig.lua:77-87). A standing wall of that material also cannot be built over (build.lua:107-165), so the "
      .. "finish needs the tile dug out and then constructed as a wall in a later application, or a different site "
      .. "in stone. This verb reports it and does not resolve it."
  end
  return NULL
end

-- Have the `d`-type cells actually been carved (no longer WALL-shaped)?
-- Also the outstanding-designation count: together the "shell is done" test.
local function shell_prerequisites(site, leaves_all, failures)
  local undug, checked = 0, 0
  for _, sec in ipairs(leaves_all) do
    if sec.mode == "dig" then
      for _, c in ipairs(sec.cells) do
        if CARVE_SYMBOLS[c.text] then
          checked = checked + 1
          local t = tile_info(site.x + c.x - 1, site.y + c.y - 1, site.z)
          if not t.ok then note_failure(failures, "carve cell", t.err)
          elseif t.hidden or t.shape == df.tiletype_shape.WALL then undug = undug + 1 end
        end
      end
    end
  end
  return {carve_cells = checked, still_solid = undug,
    pending_designations = count_pending(site, failures)}
end

-- ---------------------------------------------------------------------------
-- Surface re-read through the zone-id shim (see header)
-- ---------------------------------------------------------------------------

local function surface_reread(site, room)
  if not room then
    return {skipped = "the blueprint has no zone section, so it declares no room rectangle to re-read"}
  end
  local rect = {
    id = 0,
    x1 = site.x + room.x1 - 1, y1 = site.y + room.y1 - 1,
    x2 = site.x + room.x2 - 1, y2 = site.y + room.y2 - 1, z = site.z,
  }
  local fns = {enclosure = surface_mod.enclosure, finish = surface_mod.finish,
    material = surface_mod.boundary_material}
  local orig, idx = upvalue_by_name(fns.enclosure, 'find_zone')
  if type(orig) ~= 'function' then
    return {error = "df-overseer-surface no longer exposes find_zone as an upvalue of enclosure; the re-read cannot run (see this file's header)"}
  end
  local shim = function() return rect end
  local out = {by = "df-overseer-surface, room rectangle from the blueprint's own zone section"}
  local function swap_in()
    debug.setupvalue(fns.enclosure, idx, shim)
    -- Prove the swap reached the other two closures (same shared local):
    local seen = upvalue_by_name(fns.finish, 'find_zone')
    local seen2 = upvalue_by_name(fns.material, 'find_zone')
    return seen == shim and seen2 == shim
  end
  local okc, took = pcall(swap_in)
  if not okc or not took then
    pcall(debug.setupvalue, fns.enclosure, idx, orig)
    return {error = "the surface shim did not take effect in all three reads (" .. tostring(took) .. "); nothing was read"}
  end
  local results = {}
  for name, fn in pairs(fns) do
    local ok, res = pcall(fn, 0)
    results[name] = ok and res or {error = tostring(res)}
  end
  pcall(debug.setupvalue, fns.enclosure, idx, orig)
  local restored = upvalue_by_name(fns.finish, 'find_zone') == orig
  for name, res in pairs(results) do
    if type(res) == 'table' then res.zone_id = nil end
    out[name] = res
  end
  out.shim_restored = restored
  return out
end

-- ---------------------------------------------------------------------------
-- quickfort
-- ---------------------------------------------------------------------------

-- Same line-anchored pattern as df-overseer-building.lua's parser: two
-- leading spaces, label, colon, digits, nothing else. It can never match a
-- coordinate-bearing line.
local function parse_stats(output)
  local stats = {}
  if not output then return stats end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then stats[label] = tonumber(value) end
  end
  return stats
end

local function run_quickfort(qname, label, site, dry)
  local coord = string.format('%d,%d,%d', site.x, site.y, site.z)
  local argv = {'run', qname, '-c', coord, '-n', '/' .. label}
  if dry then argv[#argv + 1] = '-d' end
  local ok, output, res = pcall(dfhack.run_command_silent, 'quickfort', table.unpack(argv))
  local stats = ok and parse_stats(output) or {}
  return {ran = ok, result = res, stats = stats, error = (not ok) and tostring(output) or nil}
end

-- Turns quickfort's statistics into what a caller needs. `ok` is true only
-- when the run finished, designated something, every non-progress counter is
-- zero, and (for a meta) every named sub-blueprint was applied: a meta swallows
-- a failing section with only a printerr (meta.lua:106-113).
local function assess(run, phase_sec)
  local stats = run.stats
  local problems = {}
  for label, n in pairs(stats) do
    if not PROGRESS_LABELS[label] and n ~= 0 then
      problems[#problems + 1] = label .. ": " .. tostring(n)
    end
  end
  table.sort(problems)
  local designated = {
    dig_tiles = stats[LABEL_DIG] or 0,
    zones = stats[LABEL_ZONES] or 0,
    buildings = stats[LABEL_BUILDINGS] or 0,
  }
  local total = designated.dig_tiles + designated.zones + designated.buildings
  if phase_sec.mode == "meta" and phase_sec.meta_refs then
    local applied = stats[LABEL_META] or 0
    if applied < phase_sec.meta_refs then
      problems[#problems + 1] = string.format(
        "Blueprints applied: %d of the %d this meta names (a failing section is swallowed, meta.lua:106-113)",
        applied, phase_sec.meta_refs)
    end
  end
  local ok = run.ran and run.result == CR_OK and total >= 1 and #problems == 0
  return ok, problems, designated, total
end

-- ---------------------------------------------------------------------------
-- Commands
-- ---------------------------------------------------------------------------

-- plan TEMPLATE: what the blueprint declares. Reads a file, never the map.
function plan_template(name)
  local bp, err = load_blueprint(name)
  if not bp then return nil, err end
  local phases = {}
  for _, s in ipairs(bp.sections) do
    if s.mode ~= "notes" and s.mode ~= "aliases" and s.mode ~= "ignore" then
      local leaves, lerr = leaf_sections(bp.sections, s)
      local entry = {label = s.label, mode = s.mode, cells = #s.cells}
      if s.mode == "meta" then
        local names = {}
        for _, l in ipairs(leaves or {}) do names[#names + 1] = l.label end
        entry.applies = names
        if lerr then entry.error = lerr end
      end
      local needs_shell = false
      for _, l in ipairs(leaves or {}) do
        if NEEDS_DUG_SHELL[l.mode] then needs_shell = true end
      end
      entry.needs_dug_shell = needs_shell
      phases[#phases + 1] = entry
    end
  end
  local finish_cells = 0
  for _, s in ipairs(bp.sections) do
    if s.mode == "dig" then
      for _, c in ipairs(s.cells) do if c.text == SMOOTH_SYMBOL then finish_cells = finish_cells + 1 end end
    end
  end
  local result = {
    blueprint = bp.name,
    footprint = {width = bp.w, height = bp.h},
    room = bp.room and {width = bp.room.x2 - bp.room.x1 + 1, height = bp.room.y2 - bp.room.y1 + 1} or NULL,
    finish_required_cells = finish_cells,
    phases = phases,
    site_argument = "SITE is a landmark name for the first (dig) phase of a new room, or a site-N handle for every later phase",
  }
  return result
end

-- The one implementation behind `preview` (always dry) and `apply`.
local function run_phase(name, phase, site_arg, level, rank, radius, dry)
  local bp, err = load_blueprint(name)
  if not bp then return nil, err end
  if not valid_name(phase) then return nil, "PHASE must be a section label from `plan`" end
  local sec = section_by_label(bp.sections, phase)
  if not sec or sec.mode == "notes" or sec.mode == "aliases" then
    local labels = {}
    for _, s in ipairs(bp.sections) do
      if s.mode ~= "notes" and s.mode ~= "aliases" then labels[#labels + 1] = s.label end
    end
    return nil, "no phase '" .. phase .. "' in " .. bp.qname .. "; phases are: " .. table.concat(labels, ", ")
  end
  local leaves, lerr = leaf_sections(bp.sections, sec)
  if not leaves then return nil, lerr end
  local all_dig = {}
  for _, s in ipairs(bp.sections) do if s.mode == "dig" then all_dig[#all_dig + 1] = s end end

  local failures = {}
  local result = {
    blueprint = bp.name, phase = phase, mode = sec.mode, dry_run = dry,
    read_failures = failures,
  }

  -- Site: a stored handle, or a new one found near a landmark.
  local site, handle, state
  if is_handle(site_arg) then
    if level ~= nil or rank ~= nil or radius ~= nil then
      return nil, "LEVEL, RANK and RADIUS_TILES only apply when SITE is a landmark; a handle already fixes the site"
    end
    state = load_state()
    local s = state.sites[site_arg]
    if not s then return nil, "no site '" .. site_arg .. "' (see sites)" end
    if s.blueprint ~= bp.name then
      return nil, "site '" .. site_arg .. "' was carved from '" .. tostring(s.blueprint) ..
        "', not '" .. bp.name .. "'"
    end
    site, handle = s, site_arg
    result.site = {handle = handle, source = "stored"}
  else
    if sec.mode ~= "dig" and not (sec.mode == "meta" and leaves[1] and leaves[1].mode == "dig") then
      return nil, "a new site can only be found for a phase that starts by digging; give a site-N handle for phase '" .. phase .. "'"
    end
    local found, ferr = find_new_site(bp, site_arg, level, rank, radius)
    if not found then return nil, ferr end
    site = found
    result.site = {handle = NULL, source = "found", rank = rank or 1,
      note = dry and "a real apply registers this as a new site-N handle"
        or "registered below on success",
      interior_fully_revealed = not found.any_hidden}
  end
  if site.w * site.h > MAX_SITE_TILES then
    return nil, "site footprint is over this tool's " .. MAX_SITE_TILES .. "-tile bound"
  end
  local brief = site_brief(site)
  result.site.near_landmark = brief.near_landmark
  result.site.direction = brief.direction
  result.site.distance_tiles = brief.distance_tiles
  result.site.footprint = {width = site.w, height = site.h}

  -- Order guard, by mode.
  local needs_shell = false
  for _, l in ipairs(leaves) do if NEEDS_DUG_SHELL[l.mode] then needs_shell = true end end
  if needs_shell then
    local pre = shell_prerequisites(site, all_dig, failures)
    result.prerequisites = pre
    if pre.pending_designations > 0 or pre.still_solid > 0 then
      result.blocked = true
      result.blocked_reason = string.format(
        "the shell is not finished: %d outstanding dig/smooth designations and %d carve cells still solid. "
        .. "quickfort would drop the furniture or zone on solid tiles; apply the dig phase and let it complete first",
        pre.pending_designations, pre.still_solid)
      result.ok = false
      return result
    end
  end

  -- Soil rule (before applying, from the tiles as they are now).
  local fin = finish_state(site, leaves, failures)
  result.finish_plan = fin
  result.finish_required_met = (fin.blocked_total == 0 and fin.occupied_by_building == 0
    and fin.hidden == 0 and fin.unreadable == 0)
  if not result.finish_required_met then
    result.remedy = remedy_for(fin)
  end

  -- Ask quickfort.
  local run = run_quickfort(bp.qname, phase, site, dry)
  local ok, problems, designated, total = assess(run, sec)
  result.quickfort = {
    ran = run.ran, result_ok = run.ran and run.result == CR_OK,
    error = nn(run.error), stats = next(run.stats) and run.stats or empty_object(),
    problems = problems,
  }
  result.designated = designated
  result.ok = ok

  if dry then
    result.would_designate = total
    return result
  end

  -- Real run: prove it from the game, not from quickfort's counters.
  if total >= 1 and not handle then
    state = state or load_state()
    handle = "site-" .. tostring(state.next_id)
    state.next_id = state.next_id + 1
    state.sites[handle] = {x = site.x, y = site.y, z = site.z, w = site.w, h = site.h,
      blueprint = bp.name, phases = {}}
    result.site.handle = handle
  end
  if handle then
    state = state or load_state()
    local entry = state.sites[handle]
    local okt, tick = pcall(dfhack.world.ReadCurrentTick)
    entry.phases[#entry.phases + 1] = {label = phase, tick = okt and tick or nil}
    save_state(state)
  end
  local pending = count_pending(site, failures)
  result.read_back = {
    pending_designations = pending,
    designations_landed = (designated.dig_tiles == 0) or pending > 0,
    finish_state = finish_state(site, all_dig, failures),
    surface = surface_reread(site, bp.room),
    note = "surface reads are only meaningful once dwarves have finished the work; right after apply they describe the site as it stands, not as designated",
  }
  return result
end

function preview_phase(name, phase, site_arg, level, rank, radius)
  return run_phase(name, phase, site_arg, level, rank, radius, true)
end

function apply_phase(name, phase, site_arg, dry_run, level, rank, radius)
  return run_phase(name, phase, site_arg, level, rank, radius, truthy_dry_run(dry_run))
end

function list_sites()
  local state = load_state()
  local out = {}
  for handle, s in pairs(state.sites) do
    local phases = {}
    for _, p in ipairs(s.phases or {}) do phases[#phases + 1] = p.label end
    local b = site_brief(s)
    out[#out + 1] = {handle = handle, blueprint = s.blueprint, phases_applied = phases,
      footprint = {width = s.w, height = s.h},
      near_landmark = b.near_landmark, direction = b.direction, distance_tiles = b.distance_tiles}
  end
  table.sort(out, function(a, b) return a.handle < b.handle end)
  return out
end

function site_status(handle)
  if not is_handle(handle) then return nil, "SITE_ID must look like site-3 (see sites)" end
  local state = load_state()
  local site = state.sites[handle]
  if not site then return nil, "no site '" .. handle .. "' (see sites)" end
  local bp, err = load_blueprint(site.blueprint)
  if not bp then return nil, err end
  local failures = {}
  local all_leaves = {}
  for _, s in ipairs(bp.sections) do if s.mode == "dig" then all_leaves[#all_leaves + 1] = s end end
  local phases = {}
  for _, p in ipairs(site.phases or {}) do phases[#phases + 1] = p.label end
  local pre = shell_prerequisites(site, all_leaves, failures)
  local fin = finish_state(site, all_leaves, failures)
  local b = site_brief(site)
  return {
    handle = handle, blueprint = site.blueprint, phases_applied = phases,
    site = {near_landmark = b.near_landmark, direction = b.direction, distance_tiles = b.distance_tiles,
      footprint = {width = site.w, height = site.h}},
    shell = pre,
    shell_done = pre.pending_designations == 0 and pre.still_solid == 0,
    finish_state = fin,
    finish_required_met = fin.blocked_total == 0 and fin.smoothable == 0 and fin.hidden == 0
      and fin.occupied_by_building == 0 and fin.unreadable == 0,
    remedy = remedy_for(fin),
    surface = surface_reread(site, bp.room),
    read_failures = failures,
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

local USAGE = {
  "usage: df-overseer-blueprint plan TEMPLATE",
  "usage: df-overseer-blueprint preview TEMPLATE PHASE SITE [LEVEL] [RANK] [RADIUS_TILES]",
  "usage: df-overseer-blueprint apply TEMPLATE PHASE SITE [DRY_RUN] [LEVEL] [RANK] [RADIUS_TILES]",
  "usage: df-overseer-blueprint sites",
  "usage: df-overseer-blueprint status SITE_ID",
}

local function emit(res, err)
  print(encode(err and {error = err} or res))
end

if cmd == "plan" then
  if not args[2] then print(USAGE[1]) else emit(plan_template(args[2])) end
elseif cmd == "preview" then
  if not (args[2] and args[3] and args[4]) then print(USAGE[2])
  else emit(preview_phase(args[2], args[3], args[4], tonumber(args[5]), tonumber(args[6]), tonumber(args[7]))) end
elseif cmd == "apply" then
  if not (args[2] and args[3] and args[4]) then print(USAGE[3])
  else emit(apply_phase(args[2], args[3], args[4], args[5], tonumber(args[6]), tonumber(args[7]), tonumber(args[8]))) end
elseif cmd == "sites" then
  print(encode(list_sites()))
elseif cmd == "status" then
  if not args[2] then print(USAGE[5]) else emit(site_status(args[2])) end
else
  for _, l in ipairs(USAGE) do print(l) end
end
