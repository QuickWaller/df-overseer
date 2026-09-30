-- df-overseer-building.lua
--@module = true
--
-- handoffs/2026-09-21-building-tool-lua.md, design in docs/BUILDING-TOOL.md
-- (contract C1). ONE tool that lists, finds a site for, and builds any
-- building kind DFHack's quickfort knows, where df-overseer-workshop.lua
-- covers five hard-coded workshop kinds. Rule behind it (CLAUDE.md, "Tools
-- must be generalisable"): the KIND is an argument, everything that differs
-- per kind is read from the game's own data at run time, and the next kind
-- costs no new code.
--
-- WHERE THE KIND TABLE COMES FROM. quickfort keeps every buildable kind in
-- `building_db_raw`, a `local` in hack/scripts/internal/quickfort/build.lua
-- (177 keys on this install, about 150 distinct kinds once alias keys are
-- folded). The module exports only do_run/do_orders/do_undo, no getter.
-- Options weighed, least fragile chosen:
--   1. Parse the file text. Rejected: the table is Lua source with helper
--      calls (make_bridge_entry, make_trackstop_entry, ...) and a defaults
--      pass that runs after it (the 3x3 workshop footprint is filled in by
--      that pass, not written in the table), so text parsing would have to
--      re-implement both.
--   2. Read another exported structure. None exists: dfhack.buildings has
--      filters and constructors but no kind list, and the raws carry only
--      the two custom workshops (docs/BUILDING-TOOL.md item 1).
--   3. CHOSEN: reach the live table through Lua upvalues. `do_run` (exported)
--      closes over `building_db`; its metatable's __index is the local
--      function `custom_building`, which closes over `building_db_raw`. Both
--      hops are looked up BY NAME with debug.getupvalue, never by slot number.
--      This yields the table as the running quickfort actually sees it,
--      defaults already applied (footprints, is_valid_tile_fn), including the
--      per-kind tile validators, which this tool calls rather than copies.
--   WHAT A DFHACK UPDATE WOULD BREAK: renaming the upvalues `building_db` or
--   `building_db_raw`, renaming `do_run`, or restructuring so the raw table
--   is no longer reachable through that chain. Every one of those fails LOUD:
--   the load returns an error naming the missing hop (never an empty list),
--   and the tool reports it instead of guessing. Renaming a KIND's key or a
--   label changes only tokens derived from keys (see below), and adding a
--   kind adds a token with no change here.
--
-- KIND TOKENS. A caller names a kind by a token that survives the MCP layer
-- (no apostrophes, no spaces), never a display label. The token is the
-- subtype's own enum name (Masons, Still, WoodFurnace, Lever), or the raws
-- code for a custom workshop (SOAP_MAKER), or the building type's enum name
-- when there is no subtype (Bed, Door, Well). When two distinct table entries
-- would share a token (the bridge, screw pump, roller and track families are
-- direction variants of one building type), the token is `<Base>_<key>` from
-- quickfort's own key (Bridge_gw). The bare quickfort key (case sensitive,
-- for example `wl`) is also accepted. Matching a token is case insensitive.
--
-- SITES. A footprint tile is eligible when it is revealed to a vanilla
-- player (dfhack.maps.isTileVisible, the 2026-09-16 knowledge-scope rule),
-- has no building on it, and passes the kind's OWN quickfort validator
-- (beds must be indoors, doors need an adjacent wall, farm plots need soil,
-- and so on, all read from the table). At least one footprint tile or a tile
-- edge-adjacent to the footprint must be walkable, so a dwarf can reach it.
-- Sites are ranked by distance from the landmark and the top few
-- non-overlapping ones returned. LIMITATION: a kind that goes on open
-- space or a machine-shaft tile can still be found only where a walkable
-- neighbour exists; nothing here proves reachability from the fort's main
-- area, same as every sibling find tool.
--
-- BLUEPRINT. Generated in code (mode `#build`, the kind's own key in every
-- cell of the footprint), written to dfhack-config/blueprints/ where quickfort
-- resolves plain filenames, and removed again after use. No per-kind CSVs.
-- Shape follows blueprints/starter-*.csv.
--
-- REQUIREMENTS are live facts only, no labor names and no confidence
-- (contract C1). What the kind needs to be built comes from the game itself,
-- dfhack.buildings.getFiltersByType, joined to stock counts through
-- df-overseer-stocks.lua's availability read (the six-deduction one; the
-- plain fort-owned count this file's sibling used to report ignored
-- in_building and was found to overstate boulders, register 2026-09-19).
-- Counts are by ITEM TYPE ONLY for a plain item-type filter: a filter's own
-- flags (empty, screw, fire_safe, non_economic) are listed but not applied,
-- and the result says so.
-- NB the filters' `vector_id` is a df.job_item_vector_id, whose numbers do
-- NOT line up with df.items_other_id (54 is BED in one and CHAIN in the
-- other); this file maps by NAME, from the filter's item_type.
--
-- MATERIAL CHOICE (2026-09-28, handoffs/2026-09-28-building-material-choice-
-- and-repeat-kind.md; corrected 2026-09-28,
-- handoffs/2026-09-28-building-economic-uses-fix.md). A `building_material`-
-- class filter (boulder/log/block, any of them) is broken down by decoded
-- material name (dfhack.matinfo.decode), not just item type, so counts
-- distinguish, say, SHALE boulders from HEMATITE boulders. Whether a
-- material is worth treating as "economic" (ore or gem, the stone type
-- haulers do not move by default) is read per material using
-- `inorganic:isOre()` / `inorganic.material:isGem()` -- NOT the
-- `economic_uses` field the first version of this fix used. That field was
-- proved wrong for exactly this question, live, on this same install
-- (`research/2026-09-28-ore-detection.md`): `economic_uses` answers "which
-- reactions are registered against this material", not "is this ore/gem
-- worth treating specially", and it read empty for hematite even though
-- hematite is definitely iron ore. `isOre()`/`isGem()` are the calls
-- DFHack's own bundled `prospector` plugin uses, and are already the
-- live-verified fix applied to the identical question over a map tile's
-- vein material in `df-overseer-surface.lua`'s `decode_vein_tile`
-- (commits `be0ab31`, `365f17b`). The tool DEFAULTS to excluding economic
-- materials from the material it would actually build with -- the
-- motivating case is the 2026-09-25 live run building the fort's first
-- Carpenter's Workshop out of 8 hematite blocks (economic) while shale sat
-- available. MATERIAL_CHOICE, the tool's last argument, overrides this:
-- "allow_economic" opts back in, or naming a material directly (e.g.
-- SHALE) picks it explicitly even if it is economic -- an explicit choice
-- is never second-guessed, same shape as df-overseer-workjob.lua's
-- `reagent_choice` fix (2026-09-25): candidates listed, resolved by
-- explicit choice or a safe default, never silently guessed. If the
-- filter's own flags already require non_economic, that always wins over
-- an "allow_economic" override (the game would refuse economic material
-- there regardless).
--
-- ENFORCED, NOT JUST ADVISORY, AS OF 2026-10-01 (handoffs/2026-10-01-
-- buildingplan-material-filter.md, register 2026-09-30 ruling): a REAL
-- (non-dry) build now writes the resolved CLASS (every eligible material
-- name, not just the single reported chosen_material) into buildingplan's
-- own per-building-type filter for the duration of the quickfort run, then
-- restores whatever was there before -- see apply_material_filters and its
-- header comment below for the mechanism, sourced from DFHack at 53.16-r1.
-- Before this fix the blueprint carried no material at all and buildingplan
-- attached the closest item, which could be ore
-- (evals/live/2026-09-30-reservations-deploy/README.md, correction).
--
-- KIND_PREVIOUSLY_BUILT (2026-09-28, same handoff). `find` and `build` both
-- report whether a real (non-dry-run) building of this exact kind
-- (type/subtype/custom) already exists at full build stage
-- (bld:getBuildStage() == bld:getMaxBuildStage(), the same live-verified
-- fields df-overseer-zone.lua's content_row already reads) -- true, false,
-- or null when a matching building's stage or subtype could not be read.
-- This replaces a static "never build live" note that stayed stale after
-- the fort's first real build (see TOOLS.yaml): the caller (or the MCP
-- layer's go-ahead gate) reads this field instead of trusting fixed text.
--
-- `gaps` is a plain list of strings (docs/BUILDING-TOOL.md decision 5): the
-- tool reports and never refuses, so "build now, barrels later" still works.
--
-- DRY_RUN defaults to true. A dry run resolves the site, generates the
-- blueprint, and asks quickfort itself to validate it with `-d`
-- (--dry-run, documented as "don't actually change any game state"),
-- reporting that under `validation`, never under quickfort_ok (contract C1
-- reserves quickfort_ok/quickfort_error/quickfort_stats for a REAL build).
-- quickfort returns success even when it designated nothing (negative control,
-- live 2026-09-21: an indoor-only Bed on an outdoor tile gave result 0 with
-- "Unsuitable tiles for building: 1"), so `ok` is computed from its statistics:
-- at least one building designated and no problem counter above zero. A real
-- build additionally reads the tile back (`read_back`).
-- The only side effect of a dry run is a scratch blueprint file on the
-- guest, deleted straight after. Only an explicit false performs the real
-- mutation, and that path is UNTESTED live (register: first real build of a
-- never-built kind is a separate stream needing the user's go-ahead).
--
-- No raw coordinate is ever printed or returned (design commitment #1); the
-- footprint's top-left exists only inside build_kind's local scope, to build
-- quickfort's -c argument.
--
-- Usage: ./dfhack-run df-overseer-building list-kinds [FILTER]
-- Usage: ./dfhack-run df-overseer-building find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [MATERIAL_CHOICE]
-- Usage: ./dfhack-run df-overseer-building build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]
--   W H are optional for fixed-size kinds and validated against the kind's
--   min/max for the rest; one bare number is LEVEL, two are W H, three are
--   W H LEVEL. A positional CLI cannot skip a slot once a later one is given.
--   MATERIAL_CHOICE is optional and only affects a building_material filter:
--   omit it to exclude economic materials by default, pass "allow_economic"
--   to allow them, or name a material (e.g. SHALE) to pick it explicitly.

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local stocks_mod = reqscript('df-overseer-stocks')
-- handoffs/2026-09-30-room-reservations.md decision 3/4: no holding concept
-- for this tool -- refuses a tile inside a reservation it does not hold.
local reservations_mod = reqscript('df-overseer-reservations')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5
local MAX_TILE_CHECKS = 250000

-- json.lua (Friedl): an entry equal to this sentinel encodes as null, and an
-- empty table encodes as [] unless it says it is an object.
local NULL = "\0"
local function encode(v) return json.encode(v, {null = NULL}) end
local function empty_object()
  return setmetatable({}, {__tostring = function() return "JSON object" end})
end
local function nn(v) if v == nil then return NULL end return v end

-- ---------------------------------------------------------------------------
-- Reading quickfort's table (see header for the choice and its fragility)
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

-- Returns raw_table, err. Every hop that can vanish in a DFHack update
-- reports which hop it was.
local function load_quickfort_table()
  if type(debug) ~= 'table' or type(debug.getupvalue) ~= 'function' then
    return nil, "debug.getupvalue is not available in this DFHack Lua"
  end
  local ok, mod = pcall(reqscript, 'internal/quickfort/build')
  if not ok or type(mod) ~= 'table' then
    return nil, "could not load internal/quickfort/build: " .. tostring(mod)
  end
  if type(mod.do_run) ~= 'function' then
    return nil, "quickfort's build module no longer exports do_run"
  end
  local building_db = upvalue_by_name(mod.do_run, 'building_db')
  if type(building_db) ~= 'table' then
    return nil, "do_run no longer closes over an upvalue named building_db"
  end
  local mt = getmetatable(building_db)
  local lookup = mt and mt.__index
  local raw = upvalue_by_name(lookup, 'building_db_raw')
  if type(raw) ~= 'table' then
    return nil, "building_db's __index no longer closes over an upvalue named building_db_raw"
  end
  local n = 0
  for k, e in pairs(raw) do
    n = n + 1
    if type(e) ~= 'table' or e.label == nil or e.type == nil
        or e.min_width == nil or e.max_width == nil
        or e.min_height == nil or e.max_height == nil
        or type(e.is_valid_tile_fn) ~= 'function' then
      return nil, "quickfort table entry '" .. tostring(k)
        .. "' lacks label/type/footprint/is_valid_tile_fn: the table layout changed"
    end
  end
  if n == 0 then
    return nil, "quickfort's building table is empty"
  end
  return raw
end

-- Game structure only: which enum names a building type's numeric subtype.
-- An unlisted type falls back to the number, never to an error.
local SUBTYPE_ENUMS = {
  [df.building_type.Workshop] = df.workshop_type,
  [df.building_type.Furnace] = df.furnace_type,
  [df.building_type.Construction] = df.construction_type,
  [df.building_type.Trap] = df.trap_type,
  [df.building_type.SiegeEngine] = df.siegeengine_type,
}

local function enum_name(enum, v)
  if enum == nil or v == nil then return nil end
  local ok, n = pcall(function() return enum[v] end)
  if ok and n ~= nil then return tostring(n) end
  return nil
end

local function sanitize(s)
  return (tostring(s):gsub("[^%w_]", "x"))
end

-- Returns list, by_token (lowercase token), by_key, err
local function enumerate_kinds()
  local raw, err = load_quickfort_table()
  if not raw then return nil, nil, nil, err end

  -- fold alias keys (g -> gs, Ms -> Msu): same table object, keep the longest key
  local groups, order = {}, {}
  local keys = {}
  for k in pairs(raw) do keys[#keys + 1] = k end
  table.sort(keys)
  for _, k in ipairs(keys) do
    local e = raw[k]
    if not groups[e] then groups[e] = {}; order[#order + 1] = e end
    table.insert(groups[e], k)
  end

  local kinds = {}
  for _, e in ipairs(order) do
    local ks = groups[e]
    table.sort(ks, function(a, b)
      if #a ~= #b then return #a > #b end
      return a < b
    end)
    local key = ks[1]
    local aliases = {}
    for i = 2, #ks do aliases[#aliases + 1] = ks[i] end

    local type_name = enum_name(df.building_type, e.type) or tostring(e.type)
    local sub_enum = SUBTYPE_ENUMS[e.type]
    local subtype_name = enum_name(sub_enum, e.subtype)
    local base, custom_code = type_name, nil
    if e.subtype ~= nil then
      if e.custom ~= nil then
        local ok, code = pcall(function() return df.global.world.raws.buildings.all[e.custom].code end)
        if ok and code and code ~= '' then
          custom_code = tostring(code)
          base = custom_code
        else
          base = type_name .. "_custom" .. tostring(e.custom)
        end
      else
        base = subtype_name or (type_name .. "_" .. tostring(e.subtype))
      end
    end
    kinds[#kinds + 1] = {
      entry = e, key = key, aliases = aliases, label = tostring(e.label),
      type_name = type_name, subtype_name = subtype_name, subtype_id = e.subtype,
      custom_code = custom_code, base = sanitize(base),
      min_w = e.min_width, max_w = e.max_width, min_h = e.min_height, max_h = e.max_height,
      has_extents = e.has_extents and true or false,
    }
  end

  -- tokens: base name if unique among distinct entries, else Base_key
  local count = {}
  for _, k in ipairs(kinds) do
    local l = k.base:lower()
    count[l] = (count[l] or 0) + 1
  end
  local by_token, by_key = {}, {}
  for _, k in ipairs(kinds) do
    k.token = (count[k.base:lower()] > 1) and (k.base .. "_" .. sanitize(k.key)) or k.base
    local lt = k.token:lower()
    if by_token[lt] then
      return nil, nil, nil, "kind token collision after disambiguation: " .. k.token
    end
    by_token[lt] = k
    by_key[k.key] = k
    for _, a in ipairs(k.aliases) do by_key[a] = k end
  end
  table.sort(kinds, function(a, b)
    if a.type_name ~= b.type_name then return a.type_name < b.type_name end
    return a.token < b.token
  end)
  return kinds, by_token, by_key
end

-- Exported (handoffs/2026-09-30-reservation-holding.md item 1): given a
-- quickfort #build-mode cell key (e.g. "b"), the building kind TOKEN that
-- key designates (e.g. "bed"), or nil if the key resolves to nothing known.
-- df-overseer-blueprint.lua's reserve_site calls this once per distinct
-- #build cell in a template, rather than a second key->kind table living
-- there -- the same by_key this file's own resolve_kind already reads.
function kind_token_for_key(key)
  local kinds, _, by_key, err = enumerate_kinds()
  if not kinds then return nil, err end
  local k = by_key[key]
  return k and k.token or nil
end

local function kind_summary(k)
  return {
    token = k.token,
    key = k.key,
    aliases = k.aliases,
    label = k.label,
    type = k.type_name,
    subtype = nn(k.subtype_name),
    custom_code = nn(k.custom_code),
    min = {k.min_w, k.min_h},
    max = {k.max_w, k.max_h},
    fixed_size = (k.min_w == k.max_w and k.min_h == k.max_h),
    has_extents = k.has_extents,
  }
end

local function kind_brief(k)
  return {token = k.token, key = k.key, label = k.label, type = k.type_name,
          subtype = nn(k.subtype_name)}
end

local function resolve_kind(name)
  local kinds, by_token, by_key, err = enumerate_kinds()
  if not kinds then return nil, err end
  local s = tostring(name or "")
  local k = by_token[s:lower()] or by_key[s]
  if k then return k end
  local hints = {}
  local q = s:lower()
  if #q >= 2 then
    for _, c in ipairs(kinds) do
      if c.token:lower():find(q, 1, true) or c.label:lower():find(q, 1, true) then
        hints[#hints + 1] = c.token
        if #hints >= 8 then break end
      end
    end
  end
  local msg = "unknown building kind: " .. s .. " (run list-kinds)"
  if #hints > 0 then msg = msg .. "; did you mean: " .. table.concat(hints, ", ") end
  return nil, msg
end

-- ---------------------------------------------------------------------------
-- Has a real building of this kind already been built? (see header,
-- "KIND_PREVIOUSLY_BUILT")
-- ---------------------------------------------------------------------------

-- want == nil: no constraint, trivially matches. ok == false: the instance's
-- own field could not be read, so the match is unknown (nil), never guessed
-- either way. Otherwise a plain equality.
local function tri_match(want, ok, have)
  if want == nil then return true end
  if not ok then return nil end
  return have == want
end

-- Subtype field name is genuinely per-type in df-structures: Workshop and
-- Furnace instances carry it as `.type` (df-overseer-workjob.lua's
-- workshop_kind_ids already reads it this way, live-verified there); other
-- subtyped classes may expose a getSubtype() method instead. Both are tried;
-- neither existing is an honest "could not read", not a guess.
local function instance_subtype(bld, btype)
  if SUBTYPE_ENUMS[btype] == nil then return nil, true end
  local ok, sub = pcall(function() return bld.type end)
  if ok and sub ~= nil then return sub, true end
  local ok2, sub2 = pcall(function() return bld:getSubtype() end)
  if ok2 and sub2 ~= nil then return sub2, true end
  return nil, false
end

-- `bld.custom_type`, an index into df.global.world.raws.buildings.workshops
-- for a Custom workshop: the same field df-overseer-workjob.lua's
-- workshop_kind_ids and df-overseer-orders.lua's workshop_exists_count
-- already read live.
local function instance_custom(bld, btype, sub)
  if not (btype == df.building_type.Workshop and sub == df.workshop_type.Custom) then
    return nil, true
  end
  local ok, c = pcall(function() return bld.custom_type end)
  if ok then return c, true end
  return nil, false
end

-- Returns true/false/NULL (unknown) plus a note (nil when the answer is a
-- plain true/false). true requires at least one matching building at full
-- build stage (bld:getBuildStage() == bld:getMaxBuildStage(), the same
-- fields df-overseer-zone.lua's content_row already reads live). NULL means
-- every matching building's subtype or build stage could not be confirmed
-- -- never reported as false, which would be a guess.
local function kind_previously_built(k)
  local e = k.entry
  local ok_b, buildings = pcall(function() return df.global.world.buildings.all end)
  if not ok_b then
    return NULL, "could not read df.global.world.buildings.all: " .. tostring(buildings)
  end
  local matched, completed, unreadable = 0, 0, 0
  for _, bld in ipairs(buildings) do
    local ok_t, btype = pcall(function() return bld:getType() end)
    if ok_t and btype == e.type then
      local sub, sub_ok = instance_subtype(bld, btype)
      local sub_match = tri_match(e.subtype, sub_ok, sub)
      if sub_match ~= false then
        local cust, cust_ok = instance_custom(bld, btype, sub)
        local cust_match = tri_match(e.custom, cust_ok, cust)
        if cust_match ~= false then
          matched = matched + 1
          if sub_match == nil or cust_match == nil then
            unreadable = unreadable + 1
          else
            local ok_s, stage = pcall(function() return bld:getBuildStage() end)
            local ok_m, max_stage = pcall(function() return bld:getMaxBuildStage() end)
            if ok_s and ok_m then
              if stage >= max_stage then completed = completed + 1 end
            else
              unreadable = unreadable + 1
            end
          end
        end
      end
    end
  end
  if completed > 0 then return true, nil end
  if unreadable > 0 then
    return NULL, string.format(
      "checked %d matching building(s), could not confirm subtype/build-stage for %d of them",
      matched, unreadable)
  end
  return false, nil
end

function list_kinds(filter)
  local kinds, _, _, err = enumerate_kinds()
  if not kinds then return nil, err end
  local out = {}
  local q = filter and tostring(filter):lower() or nil
  for _, k in ipairs(kinds) do
    if not q or k.token:lower():find(q, 1, true) or k.label:lower():find(q, 1, true)
        or k.type_name:lower():find(q, 1, true) then
      out[#out + 1] = kind_summary(k)
    end
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Footprint
-- ---------------------------------------------------------------------------

local function resolve_dims(k, w, h)
  local fixed = (k.min_w == k.max_w and k.min_h == k.max_h)
  if w == nil and h == nil then
    if fixed then return k.min_w, k.min_h end
    return nil, string.format("%s needs W and H (width %d..%d, height %d..%d)",
      k.token, k.min_w, k.max_w, k.min_h, k.max_h)
  end
  if w == nil or h == nil then
    return nil, "give both W and H, or neither for a fixed-size kind"
  end
  if w ~= math.floor(w) or h ~= math.floor(h) then
    return nil, "W and H must be whole numbers"
  end
  if w < k.min_w or w > k.max_w or h < k.min_h or h > k.max_h then
    return nil, string.format("%s footprint %dx%d is outside the allowed width %d..%d, height %d..%d",
      k.token, w, h, k.min_w, k.max_w, k.min_h, k.max_h)
  end
  return w, h
end

-- ---------------------------------------------------------------------------
-- Site search
-- ---------------------------------------------------------------------------

local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

-- One tile against the kind's own rules. `b` is the quickfort-shaped window
-- (pos, width, height) some validators read (bridges).
local function tile_ok(entry, x, y, z, b, stats)
  stats.checked = stats.checked + 1
  if not dfhack.maps.isValidTilePos(x, y, z) then return false end
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("isTileVisible: " .. tostring(visible))
    return false
  end
  if not visible then return false end
  local pos = xyz2pos(x, y, z)
  local ok_b, bld = pcall(dfhack.buildings.findAtTile, pos)
  if not ok_b then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("findAtTile: " .. tostring(bld))
    return false
  end
  if bld then return false end
  local ok_v, valid = pcall(entry.is_valid_tile_fn, pos, entry, b)
  if not ok_v then
    stats.errors = stats.errors + 1
    stats.first_error = stats.first_error or ("is_valid_tile_fn: " .. tostring(valid))
    return false
  end
  return valid and true or false
end

local function walkable(x, y, z, cache)
  local key = x * 100000 + y
  local v = cache[key]
  if v ~= nil then return v end
  local ok, g = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  v = ok and g ~= nil and g ~= 0
  cache[key] = v
  return v
end

-- Returns chosen (list of {x,y,dist}), search_stats, err, z
-- res_id (handoffs/2026-09-30-reservation-gaps.md item 1): a candidate
-- window overlapping a reservation this call does not hold is dropped
-- before ranking, via reservations_mod's own shared `filter_reserved`
-- (the same helper df-overseer-diggable.lua's/df-overseer-openarea.lua's
-- own ranked_candidates already use), so RANK N never lands on reserved
-- ground and then refuses at build_kind's own check_tiles below.
-- find_kind passes nil (no RES_ID argument exists there); build_kind
-- passes its own res_id.
local function ranked_sites(k, w, h, level, near, radius_tiles, res_id)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then return nil, nil, "landmark not found: " .. tostring(near) end
  local z, level_err = resolve_level(az, level, near)
  if level_err then return nil, nil, level_err end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)
  if radius < 1 then radius = 1 end
  local min_x, max_x, min_y, max_y = ax - radius, ax + radius, ay - radius, ay + radius
  local entry = k.entry
  local stats = {checked = 0, errors = 0, first_error = nil, eligible_tiles = 0, windows = 0}

  local per_window = (entry.type == df.building_type.Bridge)  -- bridge validity depends on the window
  local elig = {}
  if not per_window then
    if (max_x - min_x + 1) * (max_y - min_y + 1) > MAX_TILE_CHECKS then
      return nil, nil, "search area too large"
    end
    for x = min_x, max_x do
      elig[x] = {}
      for y = min_y, max_y do
        local b = {pos = xyz2pos(x, y, z), width = 1, height = 1}
        local ok = tile_ok(entry, x, y, z, b, stats)
        elig[x][y] = ok
        if ok then stats.eligible_tiles = stats.eligible_tiles + 1 end
      end
    end
  else
    local windows = (max_x - min_x - w + 2) * (max_y - min_y - h + 2)
    if windows * w * h > MAX_TILE_CHECKS then
      return nil, nil, "search area too large for a per-window kind; lower RADIUS_TILES"
    end
  end

  local wcache = {}
  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      stats.windows = stats.windows + 1
      local fits = true
      if per_window then
        local b = {pos = xyz2pos(x, y, z), width = w, height = h}
        for dx = 0, w - 1 do
          if not fits then break end
          for dy = 0, h - 1 do
            if not tile_ok(entry, x + dx, y + dy, z, b, stats) then fits = false; break end
          end
        end
      else
        for dx = 0, w - 1 do
          if not fits then break end
          for dy = 0, h - 1 do
            if not elig[x + dx][y + dy] then fits = false; break end
          end
        end
      end
      if fits then
        -- a dwarf must be able to reach it: a walkable tile in or edge-adjacent
        local touch = false
        for dx = -1, w do
          if touch then break end
          for dy = -1, h do
            local inside = dx >= 0 and dx < w and dy >= 0 and dy < h
            local edge = (dx == -1 or dx == w) ~= (dy == -1 or dy == h)
            if inside or edge then
              if walkable(x + dx, y + dy, z, wcache) then touch = true; break end
            end
          end
        end
        if touch then
          local cx, cy = x + (w - 1) / 2, y + (h - 1) / 2
          local ddx, ddy = cx - ax, cy - ay
          candidates[#candidates + 1] = {x = x, y = y, dist = math.sqrt(ddx * ddx + ddy * ddy)}
        end
      end
    end
  end
  candidates = reservations_mod.filter_reserved(candidates, res_id,
    function(c) return reservations_mod.rect_tiles(c.x, c.y, z, w, h) end)
  table.sort(candidates, function(a, b) return a.dist < b.dist end)

  local chosen = {}
  for _, c in ipairs(candidates) do
    local ok = true
    for _, e in ipairs(chosen) do
      if overlaps(c, e, w, h) then ok = false; break end
    end
    if ok then
      chosen[#chosen + 1] = c
      if #chosen >= MAX_RESULTS then break end
    end
  end
  local search = {
    radius_tiles = radius,
    tiles_checked = stats.checked,
    eligible_tiles = per_window and NULL or stats.eligible_tiles,
    eligible_note = per_window and "not counted: this kind's tile rule depends on the footprint window" or NULL,
    windows_checked = stats.windows,
    fitting_sites = #candidates,
    check_errors = stats.errors,
    first_check_error = nn(stats.first_error),
  }
  return chosen, search, nil, z
end

local function site_info(c, w, h, z, rank)
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)
  local ok_near, info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  info = ok_near and info or nil
  return {
    rank = rank,
    near_landmark = nn(info and info.name),
    direction = nn(info and info.direction),
    distance_tiles = nn(info and info.distance_tiles),
  }
end

-- ---------------------------------------------------------------------------
-- Requirements (live facts) and gaps
-- ---------------------------------------------------------------------------

local BUILDING_MATERIAL_TYPES = {"BOULDER", "WOOD", "BLOCKS"}

-- ---------------------------------------------------------------------------
-- Material breakdown and choice for building_material filters (see header,
-- "MATERIAL CHOICE"). A second, narrower item scan: df-overseer-stocks.lua's
-- own fort-owned/marginal-flag helpers are `local` and not exported through
-- reqscript, so this repeats the same five-flag "available" gate (in_job,
-- forbid, owned, in_building, construction) plus the trader/garbage_collect/
-- removed fort-ownership check, WITHOUT that file's connectivity/hidden-tile
-- check -- a caveat this file reports (`material_scan_errors` never hides a
-- read failure, but an unreachable-yet-otherwise-free item can still count
-- here where stocks_mod's own availability read would exclude it).
-- ---------------------------------------------------------------------------

local function item_is_available(item)
  local ok_f, f = pcall(function() return item.flags end)
  if not ok_f then return nil, "could not read item.flags" end
  local ok_own, trader = pcall(function() return f.trader end)
  if not ok_own then return nil, "could not read item.flags.trader" end
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

local function item_units_simple(item)
  local ok, n = pcall(function() return item.stack_size end)
  if ok and type(n) == "number" and n > 0 then return n end
  return 1
end

-- Decodes one item's material. `mi.material.id` gives the display name.
-- The economic (ore/gem) flag is `inorganic:isOre()` or
-- `inorganic.material:isGem()` -- NOT `inorganic.economic_uses`, which
-- research/2026-09-28-ore-detection.md live-proved answers a different
-- question (registered reactions, not ore-worthiness) and read empty for
-- known iron ore. `dfhack.matinfo.decode(item)` (the item-based overload
-- used here) and `dfhack.matinfo.decode(0, idx)` (the tile/vein-event-based
-- overload df-overseer-surface.lua's decode_vein_tile uses) both return a
-- MaterialInfo whose `.inorganic` is the same `inorganic_raw` struct type
-- when the material is inorganic, so the same `:isOre()`/`.material:
-- isGem()` accessors apply -- this is DFHack's documented decode() contract
-- (one decoder, several ways to name the material), not re-derived here.
-- UNVERIFIED LIVE as of this fix (no VM access from this worktree): confirm
-- with a read-only `dfhack-run lua` call against a real inorganic item
-- before trusting this in a live decision, the same way decode_vein_tile's
-- tile-based path was confirmed in research/2026-09-28-ore-detection.md. A
-- read failure here is reported, not guessed around.
local function decode_item_material(item)
  if type(dfhack.matinfo) ~= 'table' or type(dfhack.matinfo.decode) ~= 'function' then
    return nil, "dfhack.matinfo.decode is not available on this DFHack Lua"
  end
  local ok, mi = pcall(dfhack.matinfo.decode, item)
  if not ok or mi == nil then
    return nil, "dfhack.matinfo.decode failed: " .. tostring(mi)
  end
  -- Prefer MaterialInfo:toString() (2026-10-01 fix): this is the SAME string
  -- buildingplan's own mat_cache is keyed by (buildingplan.cpp
  -- `mat_cache.emplace(mi.toString(), ...)`), so a report using this name
  -- names something the real filter vocabulary also recognises, instead of
  -- `.material.id` (which reads empty for a boulder on this fort, per the
  -- live test that found the filter-write bug, and fell back to the opaque
  -- "material_0_243" shape below).
  local name
  local ok_ts, ts = pcall(function() return mi:toString() end)
  if ok_ts and ts and ts ~= "" and ts ~= "any" then name = tostring(ts) end
  if not name then
    local ok_n, id = pcall(function() return mi.material and mi.material.id end)
    if ok_n and id and id ~= "" then name = tostring(id) end
  end
  if not name then
    local ok_ti, t = pcall(function() return mi.type end)
    local ok_ix, ix = pcall(function() return mi.index end)
    name = "material_" .. tostring(ok_ti and t or "?") .. "_" .. tostring(ok_ix and ix or "?")
  end
  local economic, economic_error
  local ok_i, inorg = pcall(function() return mi.inorganic end)
  if ok_i and inorg then
    local ok_ore, is_ore = pcall(function() return inorg:isOre() end)
    local ok_gem, is_gem = pcall(function() return inorg.material and inorg.material:isGem() end)
    if ok_ore and ok_gem then
      economic = is_ore or is_gem
    else
      economic_error = "could not read inorganic:isOre()/inorganic.material:isGem(): " ..
        tostring(is_ore) .. " / " .. tostring(is_gem)
    end
  else
    -- Not an inorganic (stone/ore) material at all: wood and other organics
    -- are never "economic stone" in this sense.
    economic = false
  end
  return {name = name, economic = economic, economic_error = economic_error}
end

-- Scans the given df.global.world.items.other[TYPE] vectors for fort-owned,
-- unclaimed items and groups them by decoded material name. Returns
-- by_name (map name -> {name, item_type, units, item_count, economic,
-- economic_error}), errors (bounded list of strings, never abandons the
-- whole scan for one bad item).
local function material_breakdown(type_names)
  local by_name, errors = {}, {}
  for _, type_name in ipairs(type_names) do
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
              rec = {name = mat.name, item_type = type_name, units = 0, item_count = 0,
                     economic = mat.economic, economic_error = mat.economic_error}
              by_name[mat.name] = rec
            end
            rec.units = rec.units + item_units_simple(item)
            rec.item_count = rec.item_count + 1
          end
        end
      end
    else
      errors[#errors + 1] = "no df.global.world.items.other vector named " .. tostring(type_name)
    end
  end
  return by_name, errors
end

local function flags_request_non_economic(flags)
  for _, f in ipairs(flags) do
    if f:find("non_economic", 1, true) then return true end
  end
  return false
end

-- ---------------------------------------------------------------------------
-- buildingplan's OWN material vocabulary (2026-10-01 fix, handoffs/
-- 2026-10-01-buildingplan-material-filter.md: a live dfhack-run lua test on
-- VM 103, reversible, restored after, found the first cut of this fix was a
-- SILENT NO-OP). Evidence: `setMaterialFilter` only keeps names it
-- recognises in its own `mat_cache`, keyed by `MaterialInfo:toString()`
-- (buildingplan.cpp `cache_matched`, `mat_cache.emplace(mi.toString(), ...)`,
-- decoded via `dfhack.matinfo.decode(0, idx)` for every inorganic, matching
-- df-overseer-surface.lua's own decode_vein_tile overload) -- live-confirmed
-- `dfhack.matinfo.decode(0,243):toString() == "shale"`,
-- `dfhack.matinfo.decode(0,182):toString() == "hematite"`. This file's OWN
-- stock-based names (decode_item_material's `.material.id`, which read empty
-- for boulders on this fort, falling back to the "material_0_243" shape) never
-- matched that vocabulary, so `["WOOD", "material_0_243"]` matched NOTHING in
-- `mat_cache`, and `ItemFilter::matches` treats an unmatched/empty name list
-- as "no restriction" (buildingplan.cpp line ~926) -- confirmed live: that
-- exact list left all 367 materials enabled, while writing {"shale"} left
-- exactly 1.
--
-- THE FIX: never build the write list from stock. `getMaterialFilter(btype,
-- sub, cust, index0)` returns every name buildingplan considers valid for
-- THAT filter (already narrowed to the filter's own item-type/flags via
-- `mat.matches(jitem)`, buildingplan.cpp lines 979-982), each tagged with its
-- buildingplan CATEGORY ("stone", "wood", ...) and current stock `count` --
-- this IS the vocabulary `setMaterialFilter` will actually recognise for
-- that filter, live-confirmed (367 valid names read back for a Wall's index
-- 0 on VM 103). This also removes the "built from live stock" gap: a
-- material with zero units today still appears in the vocabulary and stays
-- eligible.
-- ---------------------------------------------------------------------------

local function buildingplan_module()
  local ok, bp = pcall(require, 'plugins.buildingplan')
  if not ok or type(bp) ~= 'table' then
    return nil, "could not load plugins.buildingplan: " .. tostring(bp)
  end
  if type(bp.setMaterialFilter) ~= 'function' or type(bp.getMaterialFilter) ~= 'function' then
    return nil, "plugins.buildingplan does not expose setMaterialFilter/getMaterialFilter on this DFHack build"
  end
  return bp
end

-- Raw call, shared by the vocabulary read below and the prior-state read
-- apply_material_filters takes before writing (and again, as a readback,
-- right after). Returns ret (the name -> {count=, enabled=, category=}
-- string-keyed map DFHack returns, or {} if the index does not exist), err.
local function bp_get_material_filter(bp, btype, sub, cust, index0)
  local ok, ret = pcall(bp.getMaterialFilter, btype, sub, cust, index0)
  if not ok then return nil, "getMaterialFilter failed: " .. tostring(ret) end
  if ret == nil or type(ret) ~= 'table' then return {}, nil end
  return ret, nil
end

-- The full vocabulary for one filter: name -> {category=, count=, enabled=}.
-- Never gated on current stock -- see the header above.
local function vocabulary_for_filter(bp, btype, sub, cust, index0)
  local ret, err = bp_get_material_filter(bp, btype, sub, cust, index0)
  if not ret then return nil, err end
  local vocab = {}
  for name, props in pairs(ret) do
    if type(props) == 'table' then
      vocab[name] = {
        category = props.category,
        count = tonumber(props.count) or 0,
        enabled = (props.enabled == "true"),
      }
    end
  end
  return vocab
end

-- Every inorganic material name, in buildingplan's own MaterialInfo:toString()
-- form, that this fort's raws mark ore or gem
-- (dfhack.matinfo.decode(0, idx):inorganic:isOre()/.material:isGem(), the
-- same tile/vein-event overload df-overseer-surface.lua's decode_vein_tile
-- already uses; live-verified for this fix, 2026-10-01: 0:182 (HEMATITE) is
-- isOre()==true, 0:243 (SHALE) is isOre()==false). Scans every inorganic
-- once; a caller needing this for more than one filter in the same call
-- should compute it once and share it, not call this per filter.
local function economic_inorganic_names()
  local names = {}
  local ok_inorg, inorganics = pcall(function() return df.global.world.raws.inorganics.all end)
  if not ok_inorg or inorganics == nil then
    return nil, "could not read df.global.world.raws.inorganics.all: " .. tostring(inorganics)
  end
  local ok_len, len = pcall(function() return #inorganics end)
  if not ok_len then return nil, "could not read df.global.world.raws.inorganics.all's length" end
  for idx = 0, len - 1 do
    local ok_mi, mi = pcall(dfhack.matinfo.decode, 0, idx)
    if ok_mi and mi then
      local ok_name, name = pcall(function() return mi:toString() end)
      local ok_inorg2, inorg = pcall(function() return mi.inorganic end)
      if ok_name and name and ok_inorg2 and inorg then
        local ok_ore, is_ore = pcall(function() return inorg:isOre() end)
        local ok_gem, is_gem = pcall(function() return inorg.material and inorg.material:isGem() end)
        if (ok_ore and is_ore) or (ok_gem and is_gem) then
          names[name] = true
        end
      end
    end
  end
  return names
end

-- Builds the class actually written to buildingplan's filter, from ITS OWN
-- vocabulary, never stock: every vocab name that is not economic (by
-- economic_inorganic_names, OR buildingplan's own "gem" category -- the
-- fix's instruction: a gem-category material counts as economic even where
-- isOre()/isGem() alone would miss it), unless allow_economic widens that to
-- every vocab name, or a single named choice narrows it to one, validated
-- against THIS vocabulary (never against stock, so a zero-stock material
-- already known to buildingplan can still be named). Returns names (a list;
-- nil only on a hard error, NEVER an empty list, so the caller cannot mistake
-- "could not resolve" for "the class is genuinely empty"), error.
DEFAULT_CLASS_CATEGORIES = {stone = true, wood = true}

local function resolve_filter_class(vocab, flags, choice, economic_names)
  if not vocab or not next(vocab) then
    return nil, "buildingplan reports no material vocabulary for this filter"
  end
  if not economic_names then
    return nil, "could not determine which materials are economic (ore/gem)"
  end
  local must_non_economic = flags_request_non_economic(flags)
  local function is_economic(name, entry)
    return economic_names[name] == true or entry.category == "gem"
  end

  local requested_name, allow_economic = nil, false
  if choice ~= nil and tostring(choice) ~= "" then
    if tostring(choice):lower() == "allow_economic" then
      allow_economic = true
    else
      requested_name = tostring(choice)
    end
  end

  -- A category name (stone, wood, ...) as the choice: that whole class,
  -- still minus economic materials unless allow_economic.
  if requested_name then
    local cat = requested_name:lower()
    local cat_names = {}
    for name, entry in pairs(vocab) do
      if entry.category == cat and not (is_economic(name, entry) and must_non_economic) then
        cat_names[#cat_names + 1] = name
      end
    end
    if #cat_names > 0 then table.sort(cat_names); return cat_names, nil end
  end

  if requested_name then
    local match_name, match_entry
    for name, entry in pairs(vocab) do
      if name:lower() == requested_name:lower() then match_name, match_entry = name, entry end
    end
    if not match_name then
      return nil, "requested material " .. requested_name
        .. " is not in buildingplan's own vocabulary for this filter"
    end
    if is_economic(match_name, match_entry) and must_non_economic then
      return nil, "requested material " .. match_name
        .. " is economic, but this filter's own flags require non_economic"
    end
    return {match_name}, nil
  end

  -- The default class is data (register 2026-09-30: "any non-ore stone,
  -- any wood"): only DEFAULT_CLASS_CATEGORIES when the vocabulary has any
  -- of them (a wall must never take metal bars or adamantine by default);
  -- otherwise every non-economic category the filter accepts.
  local use_default_cats = false
  if not allow_economic then
    for _, entry in pairs(vocab) do
      if DEFAULT_CLASS_CATEGORIES[entry.category] then use_default_cats = true; break end
    end
  end
  local names = {}
  for name, entry in pairs(vocab) do
    if (not use_default_cats or DEFAULT_CLASS_CATEGORIES[entry.category])
        and not (is_economic(name, entry) and not (allow_economic and not must_non_economic)) then
      names[#names + 1] = name
    end
  end
  table.sort(names)
  if #names == 0 then
    return nil, "only economic material(s) are in buildingplan's vocabulary for this filter; "
      .. "pass allow_economic or name one explicitly to use them"
  end
  return names, nil
end

-- Applies the caller's MATERIAL_CHOICE (or the safe default) to a
-- building_material filter's stock breakdown, writing straight into `rec`.
-- `choice` is nil (default: exclude economic materials), "allow_economic"
-- (caller opts in), or a material name (caller names one directly, honoured
-- even if it is economic, unless the filter's own flags require
-- non_economic -- an explicit choice is never second-guessed except by the
-- game's own rule). Same shape as df-overseer-workjob.lua's reagent_choice:
-- candidates listed, resolved by explicit choice or a safe default, never
-- silently guessed.
-- filter_ctx is {vocab=, vocab_err=, economic_names=, economic_err=} (see
-- resolve_filter_class's header): the CLASS written to buildingplan's filter
-- is resolved from THAT, independent of every stock-based branch below,
-- since the 2026-10-01 fix (a live silent no-op, see the header comment
-- above buildingplan_module). rec.materials/chosen_material/available/
-- excluded_materials/material_choice stay stock-based, advisory only, as
-- they always were.
local function resolve_material_choice(rec, by_name, errors, flags, choice, filter_ctx)
  filter_ctx = filter_ctx or {}
  if filter_ctx.vocab_err then
    rec.filter_class_error = filter_ctx.vocab_err
  elseif filter_ctx.economic_err then
    rec.filter_class_error = filter_ctx.economic_err
  else
    local names, ferr = resolve_filter_class(filter_ctx.vocab, flags, choice, filter_ctx.economic_names)
    if ferr then
      rec.filter_class_error = ferr
    else
      rec.filter_material_names = names
    end
  end

  local materials = {}
  for _, m in pairs(by_name) do materials[#materials + 1] = m end
  table.sort(materials, function(a, b)
    if a.units ~= b.units then return a.units > b.units end
    return a.name < b.name
  end)
  rec.materials = materials
  if #errors > 0 then rec.material_scan_errors = errors end

  local must_non_economic = flags_request_non_economic(flags)
  local requested_name, allow_economic = nil, false
  if choice ~= nil and tostring(choice) ~= "" then
    if tostring(choice):lower() == "allow_economic" then
      allow_economic = true
    else
      requested_name = tostring(choice)
    end
  end

  if requested_name then
    local m
    for _, cand in ipairs(materials) do
      if cand.name:lower() == requested_name:lower() then m = cand end
    end
    if not m then
      rec.material_choice_error = "requested material " .. requested_name
        .. " is not among the available materials for this filter"
      rec.available = 0
      return
    end
    if m.economic and must_non_economic then
      rec.material_choice_error = "requested material " .. m.name
        .. " is economic, but this filter's own flags require non_economic"
      rec.available = 0
      return
    end
    rec.chosen_material = m.name
    rec.material_choice = "caller named " .. m.name .. " explicitly"
    rec.available = m.units
    return
  end

  local excluded, eligible = {}, {}
  for _, m in ipairs(materials) do
    if m.economic == true and not (allow_economic and not must_non_economic) then
      excluded[#excluded + 1] = m.name
    else
      eligible[#eligible + 1] = m
    end
  end
  if #excluded > 0 then rec.excluded_materials = excluded end

  if #eligible == 0 then
    rec.available = 0
    if #excluded > 0 then
      rec.material_choice_error = "only economic material(s) available (" .. table.concat(excluded, ", ")
        .. "); pass allow_economic or name one explicitly to use them"
    end
    return
  end
  local best = eligible[1]
  rec.chosen_material = best.name
  rec.available = best.units
  rec.material_choice = allow_economic
    and "default: highest-stock material, economic materials allowed by caller"
    or "default: highest-stock non-economic material"
end

local function true_flags(t, prefix)
  local out = {}
  if t == nil then return out end
  pcall(function()
    for name, v in pairs(t) do
      if v == true then out[#out + 1] = prefix .. tostring(name) end
    end
  end)
  table.sort(out)
  return out
end

local function stock_for(type_name, cache)
  if cache[type_name] then return cache[type_name] end
  local ok, res, err = pcall(stocks_mod.get_availability, type_name)
  local rec
  if not ok then
    rec = {total = NULL, available = NULL, error = "availability read failed: " .. tostring(res)}
  elseif not res then
    rec = {total = NULL, available = NULL, error = tostring(err)}
  else
    rec = {
      total = nn(res.total_units),
      available = nn(res.available_units),
      unnetted = nn(res.unnetted_units),
      in_building = nn(res.in_building_units),
      in_job = nn(res.in_job_units),
    }
    if res.flag_read_errors and #res.flag_read_errors > 0 then
      rec.flag_read_errors = res.flag_read_errors
    end
  end
  cache[type_name] = rec
  return rec
end

-- Exported (2026-10-01) so a sibling tool (construction.lua) can compute the
-- same filter breakdown and CLASS-write recs from raw (type, subtype, custom)
-- without needing this file's internal kind table at all -- construction.lua
-- only ever has the subtype's NAME (from this file's own kind_summary), not
-- its numeric enum, so it resolves the number itself (df.construction_type
-- is a bidirectional DFHack enum table, name and number both index it) and
-- calls straight in here. `label` is used only in gap/error text.
function building_filters_and_gaps(btype, sub, cust, material_choice, label)
  if sub == nil then sub = -1 end
  if cust == nil then cust = -1 end
  label = label or "this kind"
  local bp_ok, bp_enabled = pcall(function() return require('plugins.buildingplan').isEnabled() end)
  local bm = {
    source = "dfhack.buildings.getFiltersByType",
    buildingplan_enabled = bp_ok and bp_enabled or NULL,
  }
  if not bp_ok then bm.buildingplan_error = tostring(bp_enabled) end
  -- The real module handle, for the vocabulary reads below -- separate from
  -- the isEnabled() check above so bm.buildingplan_enabled keeps its exact
  -- prior meaning/shape.
  local bp_mod, bp_mod_err = buildingplan_module()
  -- Lazy, shared across every filter in this call: a full raws scan, not
  -- worth repeating per filter (see economic_inorganic_names's header).
  local economic_names, economic_err, economic_computed = nil, nil, false
  local function economic_names_once()
    if not economic_computed then
      economic_names, economic_err = economic_inorganic_names()
      economic_computed = true
    end
    return economic_names, economic_err
  end
  local gaps = {}

  local ok, filters = pcall(dfhack.buildings.getFiltersByType, {}, btype, sub, cust)
  if not ok or filters == nil then
    bm.error = "getFiltersByType failed: " .. tostring(filters)
    bm.filters = {}
    gaps[#gaps + 1] = "could not read what " .. label .. " needs to build: " .. bm.error
    return {building_material = bm}, gaps
  end

  local out, cache = {}, {}
  for i = 1, #filters do
    local f = filters[i]
    local rec = {index = i}
    local qty = f.quantity
    rec.quantity = (qty == nil) and 1 or qty
    if qty ~= nil and qty < 0 then
      rec.quantity_note = "quantity is " .. tostring(qty) .. " in the game's filter: it depends on the footprint"
    end
    local flags = true_flags(f.flags1, "flags1.")
    for _, x in ipairs(true_flags(f.flags2, "flags2.")) do flags[#flags + 1] = x end
    for _, x in ipairs(true_flags(f.flags3, "flags3.")) do flags[#flags + 1] = x end
    rec.flags = flags

    local names = nil
    local class_flag = f.flags2 and f.flags2.building_material
    if class_flag then
      rec.need = "any building material (boulder, log or block)"
      rec.count_scope = "item type and decoded material; economic materials excluded by default (see material_choice)"
      names = BUILDING_MATERIAL_TYPES
    elseif f.item_type ~= nil and f.item_type >= 0 then
      rec.count_scope = "item type only; the filter's own flags are not applied"
      local tname = enum_name(df.item_type, f.item_type)
      rec.need = tname or ("item_type " .. tostring(f.item_type))
      rec.item_type = tname
      local vname = f.vector_id and enum_name(df.job_item_vector_id, f.vector_id) or nil
      if vname and tname and vname ~= tname then rec.vector_name_disagrees = vname end
      local ok_vec, vec = pcall(function() return df.global.world.items.other[tname or ""] end)
      if tname and ok_vec and vec then
        names = {tname}
      else
        rec.count_error = "no df.global.world.items.other vector named " .. tostring(tname)
      end
    else
      rec.count_scope = "item type only; the filter's own flags are not applied"
      rec.need = (#flags > 0) and ("an item matching " .. table.concat(flags, ", "))
        or "an item (the filter names no type and no flags)"
      rec.count_error = "the filter has no item type and is not the building_material class, "
        .. "so it cannot be counted by type"
    end

    if names then
      rec.stock = {}
      local avail_sum, any_error = 0, false
      for _, n in ipairs(names) do
        local s = stock_for(n, cache)
        rec.stock[n] = s
        if s.error or s.available == NULL then any_error = true else avail_sum = avail_sum + s.available end
      end
      if any_error then
        rec.available = NULL
        gaps[#gaps + 1] = "could not count stock for " .. rec.need .. " (see stock errors)"
      else
        rec.available = avail_sum
        if rec.quantity >= 0 and avail_sum < rec.quantity then
          gaps[#gaps + 1] = string.format("needs %d of %s, %d available", rec.quantity, rec.need, avail_sum)
        elseif rec.quantity < 0 then
          gaps[#gaps + 1] = string.format("%s: quantity depends on size, %d available", rec.need, avail_sum)
        end
      end

      if class_flag then
        -- Overrides rec.available with the material-aware figure (post
        -- economic exclusion, or the caller's explicit choice): this is
        -- what the build path will actually select, so it is what gating
        -- gaps should be checked against, not the raw item-type sum above.
        local by_name, mat_errors = material_breakdown(names)
        local vocab, vocab_err
        if bp_mod then
          vocab, vocab_err = vocabulary_for_filter(bp_mod, btype, sub, cust, i - 1)
        else
          vocab_err = "plugins.buildingplan unavailable: " .. tostring(bp_mod_err)
        end
        local econ_names, econ_err = economic_names_once()
        resolve_material_choice(rec, by_name, mat_errors, flags, material_choice, {
          vocab = vocab, vocab_err = vocab_err, economic_names = econ_names, economic_err = econ_err,
        })
        if rec.material_choice_error then
          gaps[#gaps + 1] = rec.material_choice_error .. " (" .. rec.need .. ")"
        elseif rec.excluded_materials and rec.quantity >= 0 and rec.chosen_material
            and rec.available < rec.quantity then
          gaps[#gaps + 1] = string.format(
            "needs %d of %s, only %d available once economic material(s) (%s) are excluded by default",
            rec.quantity, rec.need, rec.available, table.concat(rec.excluded_materials, ", "))
        end
        if rec.filter_class_error then
          gaps[#gaps + 1] = "buildingplan filter class (" .. rec.need .. "): " .. rec.filter_class_error
        end
      end
    else
      rec.available = NULL
      gaps[#gaps + 1] = "could not count stock for " .. rec.need .. ": " .. tostring(rec.count_error)
    end
    out[#out + 1] = rec
  end
  bm.filters = out
  if #out == 0 then
    bm.note = "the game lists no material filter for this kind"
  end
  return {building_material = bm}, gaps
end

local function requirements_for(k, material_choice)
  local e = k.entry
  return building_filters_and_gaps(e.type, e.subtype, e.custom, material_choice, k.token)
end

-- ---------------------------------------------------------------------------
-- Writing the chosen CLASS into buildingplan's own material filter
-- (2026-10-01, handoffs/2026-10-01-buildingplan-material-filter.md; register
-- 2026-09-30 ruling: we choose a material CLASS, the game picks the item).
--
-- THE MECHANISM, from DFHack source at tag 53.16-r1 (downloaded fresh for
-- this fix, plugins/buildingplan/buildingplan.cpp):
--
-- - `setMaterialFilter(building_type, subtype, custom, index, material_names)`
--   and `getMaterialFilter(building_type, subtype, custom, index)` are
--   plugin Lua commands [verified: source, buildingplan.cpp lines 900-956
--   (setMaterialFilter), 957-1010ish (getMaterialFilter), exposed via
--   DFHACK_PLUGIN_LUA_COMMANDS around line 1236-1247]. Called from Lua as
--   `require('plugins.buildingplan').setMaterialFilter(...)`, the same
--   require-and-call shape this file already uses for `isEnabled()`.
-- - The filter is keyed by `BuildingTypeKey(type, subtype, custom)` only
--   [verified: source, `get_item_filters(*out, key)` at both call sites]:
--   ONE filter per building type/subtype/custom combination, shared by every
--   building of that kind this fort ever plans -- NOT per building
--   instance, and quickfort's `#build` mode has no per-cell material syntax
--   at this tag [from research/2026-09-30-item-binding-design.md section
--   1.2, itself sourced from `internal/quickfort/build.lua`]. This is why
--   the code below sets the filter immediately before the real quickfort
--   run and restores it immediately after (the handoff's instruction for
--   exactly this case: "if only a default exists, set it for the call and
--   restore it, and say so").
-- - `setMaterialFilter`'s fifth argument is a flat list of MATERIAL NAMES,
--   matched by `ItemFilter::matches`: "if the materials list is empty, an
--   item matches by mask alone; otherwise it must be IN the list" [verified:
--   source, itemfilter.cpp, fetched the same pass]. There is a COARSER
--   category mask too (`setMaterialMaskFilter`, tokens "stone", "wood",
--   "metal", ...), but a mask can only mean "all of a class, economic or
--   not" -- it cannot express "not ore, not gem" by itself. So "any non-ore
--   stone" is written here as an EXPLICIT NAME LIST. The mask is never
--   touched by this fix.
-- - **A name only counts if buildingplan's own `mat_cache` recognises it**
--   [verified live, 2026-10-01, see the header above buildingplan_module far
--   above: the first cut of this fix built that list from this file's own
--   stock scan and its names never matched `mat_cache` at all, so every
--   write silently landed as the empty-list case below]. The list actually
--   written here comes from `vocabulary_for_filter`/`resolve_filter_class`
--   (see their headers above resolve_material_choice), which read the names
--   from buildingplan's OWN `getMaterialFilter`, never from stock.
-- - Passing an EMPTY name list does not mean "match nothing": it resets the
--   filter to "match by mask alone" (buildingplan.cpp: "if all materials are
--   disabled, reset the mask" for the sibling mask-setter, and matches()'s
--   own "materials list is empty" branch above) -- i.e. wide open. This code
--   never writes an empty list for that reason: a kind with nothing eligible
--   right now is reported as a gap and the filter is left untouched.
-- - **The write is verified by reading it back** (`apply_material_filters`
--   below): after `setMaterialFilter`, `getMaterialFilter` is called again;
--   if the enabled set it reports does not exactly match what was written
--   (the live-caught failure mode: everything still enabled, meaning the
--   names were not recognised), the prior filter is restored immediately and
--   the rec is reported failed, never silently treated as applied.
--
-- WHAT THIS DOES NOT COVER, source did not settle it:
-- - Whether `setMaterialFilter`'s list, once WRITTEN AND READ BACK CORRECTLY,
--   is genuinely honoured by DF's own item search on a running fort (as
--   opposed to `buildingplan`'s own bookkeeping, which the readback proves) --
--   [unverified, needs a live build-and-watch test].
-- - Whether `quickfort run`'s own building-placement step (inside the window
--   between the filter write and its restore, below) reads this same
--   (type, subtype, custom) key before or after `addPlannedBuilding`, i.e.
--   whether the window is actually wide enough to matter -- reasoned from
--   quickfort calling `buildingplan`'s registration synchronously during its
--   own `#build` run, not observed live.
-- - The restore logic below reconstructs `getMaterialFilter`'s prior state
--   (every name "true" is read back as "no restriction", any other set of
--   "true" names is read back as that exact list) from its OWN documented
--   return shape [verified: source, the props.enabled expression]; this is
--   exact by construction, not an approximation, PROVIDED getMaterialFilter's
--   transformed view has no information loss versus the real internal
--   `mat_filter` set, which was not independently re-derived from raw
--   structures for this pass.
-- ---------------------------------------------------------------------------

-- Returns names (a list; {} means "no restriction", see header), err.
local function read_material_filter(bp, btype, sub, cust, index0)
  local ret, err = bp_get_material_filter(bp, btype, sub, cust, index0)
  if not ret then return nil, err end
  local names, all_true, any = {}, true, false
  for name, props in pairs(ret) do
    any = true
    if type(props) == 'table' and props.enabled == "true" then
      names[#names + 1] = name
    else
      all_true = false
    end
  end
  if not any or all_true then return {}, nil end
  table.sort(names)
  return names, nil
end

local function write_material_filter(bp, btype, sub, cust, index0, names)
  local ok, err = pcall(bp.setMaterialFilter, btype, sub, cust, index0, names or {})
  if not ok then return false, "setMaterialFilter failed: " .. tostring(err) end
  return true
end

-- Reads back what buildingplan now reports as enabled for this filter,
-- comparing it against `want` (the exact set of names just written). Any
-- mismatch (fewer enabled than written -- some names were not recognised; or
-- MORE enabled, up to and including every material in the vocabulary -- the
-- live-caught silent-no-op failure mode) is reported, never silently
-- accepted. `economic_names` (may be nil if that scan failed) is used only
-- to report which of the enabled names are economic, for visibility.
local function verify_material_filter(bp, btype, sub, cust, index0, want, economic_names)
  local after, aerr = vocabulary_for_filter(bp, btype, sub, cust, index0)
  if not after then
    return false, nil, nil, "readback failed: " .. tostring(aerr)
  end
  local enabled, economic_enabled, want_set = {}, {}, {}
  for _, n in ipairs(want) do want_set[n] = true end
  for name, entry in pairs(after) do
    if entry.enabled then
      enabled[#enabled + 1] = name
      if economic_names and (economic_names[name] or entry.category == "gem") then
        economic_enabled[#economic_enabled + 1] = name
      end
    end
  end
  table.sort(enabled)
  table.sort(economic_enabled)
  local matches = (#enabled == #want)
  if matches then
    for _, n in ipairs(enabled) do
      if not want_set[n] then matches = false break end
    end
  end
  local err = nil
  if not matches then
    err = string.format(
      "readback mismatch: wrote %d material(s), buildingplan now reports %d enabled -- the write was likely not recognised",
      #want, #enabled)
  end
  return matches, enabled, economic_enabled, err
end

-- Writes rec.filter_material_names (from resolve_material_choice, via
-- building_filters_and_gaps) into buildingplan's own filter for every
-- building_material rec in `filter_recs` that has a non-empty list, saving
-- what was there first, WRITING, then READING BACK to confirm the write
-- actually took (see the header above and verify_material_filter's own
-- comment: the live-caught bug was a silent no-op that this readback alone
-- would have caught). A mismatch restores the prior state immediately and is
-- reported failed, never counted as applied. Returns a report table and a
-- restore() function the caller MUST call once the real quickfort run has
-- finished (success or not) -- this is the "set for the call, restore after"
-- contract, for whichever recs DID apply successfully.
function apply_material_filters(btype, sub, cust, filter_recs)
  local bp, berr = buildingplan_module()
  if not bp then
    return {applied = {}, skipped = "buildingplan unavailable: " .. tostring(berr)}, function() return {} end
  end
  local economic_names = economic_inorganic_names()
  local applied, saved = {}, {}
  for _, rec in ipairs(filter_recs or {}) do
    if rec.filter_material_names and #rec.filter_material_names > 0 then
      local index0 = rec.index - 1
      local prev, rerr = read_material_filter(bp, btype, sub, cust, index0)
      if prev == nil then
        applied[#applied + 1] = {index = rec.index, ok = false, error = rerr}
      else
        local ok, werr = write_material_filter(bp, btype, sub, cust, index0, rec.filter_material_names)
        local entry = {index = rec.index, ok = ok, error = nn(werr), materials = rec.filter_material_names}
        if ok then
          local matches, enabled, econ_enabled, verr = verify_material_filter(
            bp, btype, sub, cust, index0, rec.filter_material_names, economic_names)
          entry.enabled_count = enabled and #enabled or NULL
          entry.economic_enabled = econ_enabled or {}
          if not matches then
            entry.ok = false
            entry.error = verr
            local rok, rwerr = write_material_filter(bp, btype, sub, cust, index0, prev)
            entry.restored_on_mismatch = rok
            if not rok then entry.restore_on_mismatch_error = nn(rwerr) end
          end
        end
        applied[#applied + 1] = entry
        if entry.ok then saved[#saved + 1] = {index0 = index0, names = prev} end
      end
    end
  end
  local function restore()
    local restored = {}
    for _, s in ipairs(saved) do
      local ok, werr = write_material_filter(bp, btype, sub, cust, s.index0, s.names)
      restored[#restored + 1] = {index = s.index0 + 1, ok = ok, error = nn(werr)}
    end
    return restored
  end
  return {applied = applied}, restore
end

-- ---------------------------------------------------------------------------
-- Blueprint (generated, never a per-kind file)
-- ---------------------------------------------------------------------------

local function blueprint_text(k, w, h)
  local rows = {"#build generated by df-overseer-building"}
  for _ = 1, h do
    local cells = {}
    for _ = 1, w do cells[#cells + 1] = k.key end
    rows[#rows + 1] = table.concat(cells, ",")
  end
  return table.concat(rows, "\n") .. "\n"
end

local function write_blueprint(k, w, h)
  local filename = string.format("_tmp-building-%s-%dx%d-%d.csv", sanitize(k.token), w, h, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then return nil, "could not open blueprint for writing: " .. tostring(open_err) end
  f:write(blueprint_text(k, w, h))
  f:close()
  return filename
end

function parse_quickfort_stats(output)
  local stats = {}
  if not output then return stats end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then stats[label] = tonumber(value) end
  end
  return stats
end

-- quickfort returns CR_OK even when it designated nothing (a negative control
-- on this install: a Bed on an outdoor tile printed "Buildings designated: 0,
-- Unsuitable tiles for building: 1" and result CR_OK). So "ok" here means the
-- run finished, at least one building was designated, and every OTHER stat
-- quickfort printed (each is a problem counter) is zero.
local DESIGNATED_LABEL = "Buildings designated"
function assess_quickfort(ran, res, stats)
  local problems = {}
  if not ran then return false, problems end
  for label, n in pairs(stats or {}) do
    if label ~= DESIGNATED_LABEL and n ~= 0 then
      problems[#problems + 1] = label .. ": " .. tostring(n)
    end
  end
  table.sort(problems)
  local designated = (stats or {})[DESIGNATED_LABEL] or 0
  return (res == CR_OK and designated >= 1 and #problems == 0), problems
end

local function truthy_dry_run(v)
  if v == nil then return true end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- ---------------------------------------------------------------------------
-- Commands
-- ---------------------------------------------------------------------------

local function elig_str(search)
  if search.eligible_tiles == NULL then return "n/a" end
  return tostring(search.eligible_tiles)
end

function find_kind(kind_name, w, h, level, near, radius_tiles, material_choice)
  local k, kerr = resolve_kind(kind_name)
  if not k then return nil, kerr end
  local dw, dh = resolve_dims(k, w, h)
  if not dw then return nil, dh end
  local chosen, search, err, z = ranked_sites(k, dw, dh, level, near, radius_tiles, nil)
  if err then return nil, err end
  if #chosen == 0 then
    return nil, string.format("no site for %s (%dx%d) near %s; search: %d tiles checked, %s eligible, %d check errors%s",
      k.token, dw, dh, tostring(near), search.tiles_checked, elig_str(search), search.check_errors,
      search.first_check_error ~= NULL and (" (first: " .. search.first_check_error .. ")") or "")
  end
  local req, gaps = requirements_for(k, material_choice)
  local prev_built, prev_note = kind_previously_built(k)
  local results = {}
  for rank, c in ipairs(chosen) do
    results[#results + 1] = {
      kind = kind_brief(k),
      dims = {dw, dh},
      site = site_info(c, dw, dh, z, rank),
      search = search,
      requirements = req,
      gaps = #gaps > 0 and gaps or {},
      kind_previously_built = prev_built,
      kind_previously_built_note = nn(prev_note),
    }
  end
  return results
end

function build_kind(kind_name, w, h, level, near, rank, radius_tiles, dry_run, material_choice, res_id, override)
  if override ~= nil and res_id == nil then
    return nil, "OVERRIDE requires RES_ID"
  end
  local k, kerr = resolve_kind(kind_name)
  if not k then return nil, kerr end
  local dw, dh = resolve_dims(k, w, h)
  if not dw then return nil, dh end
  rank = rank or 1
  local dry = truthy_dry_run(dry_run)
  local chosen, search, err, z = ranked_sites(k, dw, dh, level, near, radius_tiles, res_id)
  if err then return nil, err end
  if rank < 1 or rank > #chosen then
    return nil, string.format("no candidate at rank %d (found %d near %s); search: %d tiles checked, %s eligible, %d check errors",
      rank, #chosen, tostring(near), search.tiles_checked, elig_str(search), search.check_errors)
  end
  local c = chosen[rank]
  local req, gaps = requirements_for(k, material_choice)
  local prev_built, prev_note = kind_previously_built(k)
  local result = {
    kind = kind_brief(k),
    dims = {dw, dh},
    site = site_info(c, dw, dh, z, rank),
    dry_run = dry,
    search = search,
    requirements = req,
    gaps = #gaps > 0 and gaps or {},
    kind_previously_built = prev_built,
    kind_previously_built_note = nn(prev_note),
  }

  -- Blueprint on the guest. The top-left (c.x, c.y, z) is used only in the -c
  -- argument below and is never printed or returned.
  local filename, write_err = write_blueprint(k, dw, dh)
  result.blueprint = {mode = "build", key = k.key, cells = string.format("%dx%d", dw, dh)}
  if not filename then
    if dry then
      result.validation = {by = "quickfort --dry-run", ok = false, error = write_err}
    else
      result.quickfort_ok = false
      result.quickfort_error = write_err
    end
    return result
  end
  result.blueprint.file = filename

  -- Computed BEFORE check_tiles/designating (handoff review, 2026-09-30):
  -- record_override below must fire only if this override was actually
  -- consumed (some tile is in res_id and k.token was not on its own
  -- allowed_kinds), the run is real, and the designation then succeeds --
  -- never on a dry run, never for an override that was not needed, never
  -- for a designation that failed.
  local rect_tiles = reservations_mod.rect_tiles(c.x, c.y, z, dw, dh)
  local needs_override = override ~= nil
    and reservations_mod.override_needed(rect_tiles, res_id, k.token)
  local conflict = reservations_mod.check_tiles(rect_tiles, nil, res_id, k.token, override)
  if conflict then
    pcall(os.remove, "dfhack-config/blueprints/" .. filename)
    return nil, conflict.message
  end

  local coord = string.format('%d,%d,%d', c.x, c.y, z)
  if dry then
    local ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord, '-d')
    local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
    result.blueprint.removed = (ok_rm and rm == true)
    local stats = ok_run and parse_quickfort_stats(output) or nil
    local ok_v, problems = assess_quickfort(ok_run, res, stats)
    result.validation = {
      by = "quickfort run --dry-run",
      ok = ok_v,
      problems = problems,
      error = (not ok_run) and tostring(output) or NULL,
      stats = (stats and next(stats)) and stats or empty_object(),
    }
    return result
  end

  -- Write the chosen CLASS into buildingplan's own filter for the duration
  -- of this real run, restoring immediately after (see apply_material_filters
  -- above for the mechanism and why this is a set-and-restore, not a
  -- permanent change): only the building_material filters this call actually
  -- resolved a non-empty class for are touched.
  local filter_recs = {}
  if req.building_material and req.building_material.filters then
    for _, rec in ipairs(req.building_material.filters) do
      if rec.filter_material_names then filter_recs[#filter_recs + 1] = rec end
    end
  end
  local mf_report, mf_restore
  if #filter_recs > 0 and req.building_material.buildingplan_enabled == true then
    mf_report, mf_restore = apply_material_filters(k.entry.type, k.entry.subtype, k.entry.custom, filter_recs)
  end

  local ok_run, output, res = pcall(dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord)

  if mf_restore then
    mf_report.restored = mf_restore()
    result.material_filter = mf_report
  end

  local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
  result.blueprint.removed = (ok_rm and rm == true)
  local stats = ok_run and parse_quickfort_stats(output) or nil
  local ok_v, problems = assess_quickfort(ok_run, res, stats)
  result.quickfort_ok = ok_v
  result.quickfort_error = (not ok_run) and tostring(output) or NULL
  result.quickfort_stats = (stats and next(stats)) and stats or empty_object()
  result.quickfort_problems = problems
  if needs_override and ok_v then
    reservations_mod.record_override(res_id, "building.build", k.token, override)
  end
  -- Read the tile back: quickfort can report success without a building
  -- (TRAPS.md), so look at the game. UNTESTED live, like the whole real path.
  local ok_b, bld = pcall(dfhack.buildings.findAtTile, xyz2pos(c.x, c.y, z))
  result.read_back = {
    building_found = ok_b and bld ~= nil and bld ~= false,
    type_matches = ok_b and bld and bld:getType() == k.entry.type or false,
    error = (not ok_b) and tostring(bld) or NULL,
  }
  return result
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local USAGE = {
  "usage: df-overseer-building list-kinds [FILTER]",
  "usage: df-overseer-building find KIND [W H] [LEVEL] NEAR_LANDMARK [RADIUS_TILES] [MATERIAL_CHOICE]",
  "usage: df-overseer-building build KIND [W H] [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES] [DRY_RUN] [MATERIAL_CHOICE] [RES_ID] [OVERRIDE]",
}

-- After KIND: up to three leading numbers (1 = LEVEL, 2 = W H, 3 = W H LEVEL),
-- then NEAR_LANDMARK, then the rest. Returns w, h, level, near, rest_index.
local function parse_site_args(args)
  local nums, i = {}, 3
  while #nums < 3 and args[i] ~= nil and tonumber(args[i]) ~= nil do
    nums[#nums + 1] = tonumber(args[i])
    i = i + 1
  end
  local w, h, level
  if #nums == 1 then level = nums[1]
  elseif #nums == 2 then w, h = nums[1], nums[2]
  elseif #nums == 3 then w, h, level = nums[1], nums[2], nums[3] end
  return w, h, level, args[i], i + 1
end

local args = {...}
local cmd = args[1]

if cmd == "list-kinds" then
  local res, err = list_kinds(args[2])
  print(encode(err and {error = err} or res))
elseif cmd == "find" then
  local kind = args[2]
  local w, h, level, near, nxt = parse_site_args(args)
  if not (kind and near) then
    print(encode({error = USAGE[2]}))
  else
    local res, err = find_kind(kind, w, h, level, near, tonumber(args[nxt]), args[nxt + 1])
    print(encode(err and {error = err} or res))
  end
elseif cmd == "build" then
  local kind = args[2]
  local w, h, level, near, nxt = parse_site_args(args)
  if not (kind and near) then
    print(encode({error = USAGE[3]}))
  else
    local res, err = build_kind(kind, w, h, level, near, tonumber(args[nxt]), tonumber(args[nxt + 1]), args[nxt + 2], args[nxt + 3], args[nxt + 4], args[nxt + 5])
    print(encode(err and {error = err} or res))
  end
else
  for _, l in ipairs(USAGE) do print(l) end
end
