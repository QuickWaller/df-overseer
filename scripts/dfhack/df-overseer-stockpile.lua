-- df-overseer-stockpile.lua
--@module = true
--
-- handoffs/2026-09-18-lever-gap-tools.md deliverable 2: a read-only
-- stockpile tool. docs/PRODUCTION-MODEL.md §8 names stockpile occupancy as
-- one of the very few LEADING indicators this design has (a pile at 80% and
-- rising predicts a backed-up workshop before it happens), and §13's lever
-- table lists "stockpile link misconfigured" and "stockpile full" as two of
-- the six diagnoses no tool could previously act on or even see.
--
-- Two commands, both read-only:
--   list     -- every stockpile: id, landmark-relative name, occupied/total
--               tiles, coarse accept categories.
--   links ID -- the give/take links for one stockpile OR workshop building.
--
-- OCCUPIED / TOTAL TILES, verified live this session against Uniboslan's
-- two real stockpiles (ids 1 and 2, both full 5x5=25-tile rectangles, z168
-- and z169):
--
-- TOTAL: `dfhack.buildings.containsTile(bld, x, y)` walked over the
-- building's own x1..x2/y1..y2 bounding box, live-confirmed to return
-- exactly 25 for both piles, matching
-- `dfhack.buildings.countExtentTiles(bld, 0)` (also tried, also 25 on both
-- -- the two APIs agree). containsTile is used, not countExtentTiles,
-- because it is called per-tile, which lets each tile also get the
-- hidden-tile check below; countExtentTiles returns one opaque int with no
-- way to filter individual tiles. Neither pile carved any tile out of its
-- rectangle on this fort, so the exact-shape case (a non-rectangular pile)
-- is UNTESTED live -- the per-tile walk is written to handle it correctly
-- regardless (containsTile is exactly DFHack's own "is this tile part of
-- the extent" primitive), just not exercised against a real carved-out
-- example.
--
-- OCCUPIED: `dfhack.buildings.getStockpileContents(bld)` returns every item
-- in the pile (33 items in pile 1, 8 in pile 2, live-read), which is an
-- ITEM count, not a TILE count -- the handoff is explicit that the two must
-- not be conflated (a bin or a stack puts several items on one tile). Each
-- item's `dfhack.items.getPosition` was read and deduplicated by (x,y,z):
-- pile 1's 33 items resolved to 24 DISTINCT tile positions, all inside the
-- pile's own bounds -- confirmed live, not assumed. That distinct-position
-- count is "occupied tiles" here. A tile with a hidden position (see below)
-- is excluded from occupied same as from total, so the fraction stays
-- meaningful even if it can never happen for a player-built pile.
--
-- HIDDEN-TILE FILTER: mirrors df-overseer-stocks.lua's `is_on_hidden_tile`
-- (decisions/DECISIONS.md 2026-09-16, "agents may only know what a vanilla
-- player could know") -- same `dfhack.maps.isTileVisible` test, same
-- "unresolvable position treated as visible" fallback -- but reimplemented
-- as `is_hidden_tile(x, y, z)` here rather than reqscript'd, because that
-- function is item-scoped (`dfhack.items.getPosition(item)` inside it) and
-- this file also needs to test bare pile-extent tiles that may hold no
-- item at all. Both of Uniboslan's piles read fully visible, 0 hidden
-- tiles each, live-confirmed -- an honest, unsurprising result for a
-- fort's own built stockpile, not something this tool assumes.
--
-- ACCEPTS (coarse level, per the handoff's own wording): read from
-- `building.settings.flags`, confirmed live to be exactly DF's own 17
-- top-level stockpile-category toggles (animals, food, furniture, refuse,
-- stone, wood, gems, finished_goods, leather, cloth, sheet, bars_blocks,
-- weapons, armor, ammo, coins, corpses -- matching the in-game stockpile
-- settings screen's own category list, confirmed by enumerating the live
-- struct's string keys and finding exactly these 17, no more). Both of
-- Uniboslan's piles today accept the same five: food, furniture, stone,
-- wood, bars_blocks (live-read, general-purpose starting piles). This is
-- the coarse category toggle only, not the deep per-subtype filter
-- (`settings.food.prepared_meals`-style detail) -- the handoff asks for
-- "coarse level" explicitly.
--
-- LINKS: `building_stockpilest.links.{give,take}_{to,from}_{pile,workshop}`
-- for a stockpile, `building.profile.links` (same four field names) for a
-- workshop -- both confirmed live this session to be real struct fields on
-- Uniboslan's own buildings, matching
-- research/2026-09-18-schema-extraction-live.md §5's own finding. All four
-- vectors read empty (0) on both of Uniboslan's stockpiles and its one
-- workshop today: real, live-confirmed "not configured," not a read
-- failure. What each vector holds when non-empty (a pointer directly usable
-- as a building, versus a raw id needing a separate resolve) is NOT
-- independently exercised this session, since nothing on this fort is
-- linked -- `resolve_link_target` below is written defensively (pcall
-- around every field access) and marks an entry `resolved = false` rather
-- than guessing if this assumption turns out wrong once a real link exists.
--
-- Never a coordinate: every id below resolves to a landmark name/direction/
-- distance_tiles via df-overseer-landmarks.lua's own `nearest_landmark`,
-- the same helper df-overseer-workshop.lua already uses for this exact
-- purpose -- reused, not reinvented.
--
-- Usage: ./dfhack-run df-overseer-stockpile list
-- Usage: ./dfhack-run df-overseer-stockpile links ID
--
-- WRITING (handoffs/2026-10-01-stockpile-writing.md): place, configure, link,
-- unlink. Four commands, all mutating, DRY_RUN default true.
--
-- MECHANISM, from DFHack source at tag 53.16-r1 (dfhack.git) with `scripts`
-- pinned to DFHack/scripts.git commit 7549711a993e03bef19e90b27427096c1099853e
-- (the exact commit that tag's own submodule pointer names):
--
-- SIZE: a #place blueprint cell's content is a stockpile-type key string;
-- adjacent matching cells become one pile whose footprint is exactly the
-- cell grid quickfort_building groups (place.lua's own header comment,
-- scripts/internal/quickfort/place.lua:4-10: "width, height: number between
-- 1 and 31" -- this project's own place enforces that same 1..31 cap rather
-- than trusting quickfort to reject an oversized request silently). This
-- file writes a throwaway #place CSV of exactly W by H cells, same pattern
-- df-overseer-zone.lua's write_rect_blueprint uses for #zone.
--
-- CATEGORIES: `stockpile_db_raw` (place.lua:78-97) maps ONE ascii letter per
-- top-level category to the SAME 17 tokens this file's own CATEGORY_NAMES
-- already reads from `bld.settings.flags` (see the header above). Several
-- letters concatenated in one cell (e.g. "sw") make ONE custom pile that
-- accepts all of them -- `make_db_entry` (place.lua:113-164) walks the key
-- string char by char. Separately, `configure_stockpile` (place.lua:256-268)
-- applies each category via `stockpiles.import_settings('library/cat_'..cat,
-- {id=bld.id, mode='enable'})` -- `import_settings` (plugins/lua/
-- stockpiles.lua:124-134, dfhack.git tag 53.16-r1) resolves that to a
-- `.dfstock` preset file and calls the plugin's own bound `stockpiles_import`
-- (plugins/stockpiles/stockpiles.cpp:87-124), which turns opts.mode into a
-- DeserializeMode (enable/disable/else set) and hands the preset file plus
-- mode to `StockpileSerializer`. `read_category` (plugins/stockpiles/
-- StockpileSerializer.cpp:901-929) is what mode actually does: ENABLE sets
-- the category's own top-level flag bit AND every subtype field the preset
-- file carries a value for; DISABLE clears the bit and zeroes those same
-- fields, but only when the bit was already set; SET clears everything
-- first, then applies the file wholesale. This file's `stockpile.configure`
-- below drives exactly this: enable the requested categories, disable
-- whatever else this pile currently accepts, read back with the SAME
-- `accepted_categories` the read-only `list`/`links` commands already use.
--
-- PRESETS EXIST, one per category (`cat_ammo` through `cat_wood`, confirmed
-- by a directory listing of data/stockpiles/ at this tag -- all 17 files
-- present, matching CATEGORY_NAMES 1:1 via CATEGORY_INFO's preset field
-- below). UNVERIFIED FROM SOURCE: the actual protobuf bytes of any single
-- cat_X.dfstock were never decoded, so "every subtype the category has" is
-- inferred only from read_category's own code path (above), not confirmed
-- against one file's real payload. A NAMING MISMATCH is real, not
-- unverified: this file's own accept-category name is "sheet" (the raw
-- df-structures field, confirmed live per the header above) but the preset
-- and place.lua's own categories={'sheets'} entry (place.lua:92) both use
-- the plural "sheets" -- CATEGORY_INFO below carries both spellings
-- explicitly so nothing has to remember which is which. Finer per-subtype
-- filters, container counts (bins/barrels/wheelbarrows) and named
-- give_to/take_from targets are ALSO settable through a #place cell's own
-- `:key=val` properties (place.lua:100-244, `parse_properties`/
-- `custom_stockpile`) and through named (non-category) preset files via the
-- `:name(mode,filters)` transformation syntax (scripts/internal/quickfort/
-- parse.lua:770-780, `parse_stockpile_transformations`) -- NEITHER is
-- exposed by the coarse tools below, matching this file's own existing
-- "coarse level" scope for `list`/`links`.
--
-- LINKS: `create_stockpile` (place.lua:293-334) queues named give_to/
-- take_from targets, resolved by `link_stockpiles` (place.lua:372-415)
-- against live piles/workshops by name or id via `utils.insert_sorted`
-- (Lua API.rst:4077-4082) on the SAME four vectors this file's own `links`
-- command already reads (`give_to_pile`/`take_from_pile`/`give_to_workshop`/
-- `take_from_workshop`, on `bld.links` for a stockpile or `bld.profile.links`
-- for a workshop): a pile giving to a pile writes give_to_pile on the giver
-- and take_from_pile on the receiver; a pile giving to a workshop writes
-- give_to_workshop on the giver and (the workshop's own) take_from_pile on
-- the receiver; a workshop giving to a pile writes (the workshop's own)
-- give_to_pile and the pile's take_from_workshop. `stockpile.link`/`unlink`
-- below encode exactly this as one small data table (LINK_RULE), no per-kind
-- branch, and use the same insert_sorted plus its inverse `erase_sorted_key`
-- (Lua API.rst:4093-4097) quickfort itself uses, keyed by building id.
--
-- WHY `df-overseer-openarea.lua`'s finder (`is_free`), NOT place.lua's own
-- `is_valid_stockpile_tile` (place.lua:29-43, which additionally demands a
-- FLOOR/BOULDER/PEBBLES/STAIR/RAMP/TWIG/SAPLING/SHRUB tile shape): the
-- handoff asks for this reuse explicitly, matching every other finder in
-- this codebase. It is coarser than quickfort's own check -- a walkable,
-- building-free, visible tile this file judges "free" could still fail
-- `is_valid_stockpile_tile`'s own shape test (open space, a tree, a chasm
-- edge). quickfort's own `check_tiles_and_extents` degrades this
-- gracefully, not silently: an invalid tile is skipped from the extent
-- (counted under "Stockpile tiles skipped (tile occupied)", place.lua:433-
-- 436) rather than erroring, so a placement can come back SMALLER than
-- W*H tiles even when `quickfort_ok` is true -- read `quickfort_stats` and
-- the `read_back` occupied/total counts, never assume the requested
-- footprint was fully honoured. Only a live run settles whether this gap
-- ever actually bites on Uniboslan's own terrain.
--
-- Usage: ./dfhack-run df-overseer-stockpile place W H [LEVEL] NEAR_LANDMARK CATEGORIES [RANK] [RADIUS_TILES] [DRY_RUN] [RES_ID] [OVERRIDE]
-- Usage: ./dfhack-run df-overseer-stockpile configure ID CATEGORIES [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-stockpile link ID TARGET_ID give|take [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-stockpile unlink ID TARGET_ID give|take [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-stockpile settings ID [LINKS_ONLY] [MAX_BINS] [MAX_BARRELS] [MAX_WHEELBARROWS] [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-stockpile materials ID CATEGORY
-- Usage: ./dfhack-run df-overseer-stockpile set-materials ID CATEGORY MATERIALS [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-stockpile health
-- Usage: ./dfhack-run df-overseer-stockpile plan-feed WORKSHOP_KIND|ID
-- Usage: ./dfhack-run df-overseer-stockpile remove ID [DRY_RUN]
--
-- handoffs/2026-10-07-stockpile-tool-gaps.md added settings, materials,
-- set-materials, health, plan-feed and remove, plus links-only/container
-- reads on list/links and single-class-trap warnings on link. ALL OF IT IS
-- UNVERIFIED LIVE (offline stream); the building field names for links-only
-- and container counts, and the settings.<category>.mats layout, are
-- recalled, not read from source (see links_only_of and MATERIAL_FILTERS).

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local openarea_mod = reqscript('df-overseer-openarea')
local reservations_mod = reqscript('df-overseer-reservations')
-- handoffs/2026-10-07-stockpile-tool-gaps.md item 4/5: the per-workshop-kind
-- input/output table, as data (df-overseer-stockpile-kinds.lua).
local kinds_mod = reqscript('df-overseer-stockpile-kinds')

-- See header: mirrors df-overseer-stocks.lua's is_on_hidden_tile, adapted
-- to take a bare position rather than an item.
local function is_hidden_tile(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    return false
  end
  return not visible
end

-- DF's own 17 top-level stockpile category toggles, live-confirmed this
-- session (see header) -- listed explicitly rather than trusting pairs()
-- over `settings.flags`, whose live dump also carried a run of unnamed
-- integer-keyed bits (17-31) alongside the 17 named ones; only the named
-- keys are a category a player would recognise from the stockpile screen.
local CATEGORY_NAMES = {
  "animals", "food", "furniture", "refuse", "stone", "wood", "gems",
  "finished_goods", "leather", "cloth", "sheet", "bars_blocks", "weapons",
  "armor", "ammo", "coins", "corpses",
}

-- Per-category tokens WRITING needs, keyed by the same CATEGORY_NAMES above
-- (see the file header's "CATEGORIES" section for the source citations):
--   letter -- the #place cell key (place.lua's stockpile_db_raw, letter to
--     concatenate into a custom pile's key string).
--   preset -- the cat_<preset>.dfstock library file `stockpile.configure`
--     imports to enable/disable that whole category. Differs from the name
--     itself ONLY for "sheet" (this file's/df-structures' singular field
--     name) vs "sheets" (the preset file and place.lua's own plural).
local CATEGORY_INFO = {
  animals        = {letter = "a", preset = "animals"},
  food           = {letter = "f", preset = "food"},
  furniture      = {letter = "u", preset = "furniture"},
  refuse         = {letter = "r", preset = "refuse"},
  stone          = {letter = "s", preset = "stone"},
  wood           = {letter = "w", preset = "wood"},
  gems           = {letter = "e", preset = "gems"},
  finished_goods = {letter = "g", preset = "finished_goods"},
  leather        = {letter = "l", preset = "leather"},
  cloth          = {letter = "h", preset = "cloth"},
  sheet          = {letter = "S", preset = "sheets"},
  bars_blocks    = {letter = "b", preset = "bars_blocks"},
  weapons        = {letter = "p", preset = "weapons"},
  armor          = {letter = "d", preset = "armor"},
  ammo           = {letter = "z", preset = "ammo"},
  coins          = {letter = "n", preset = "coins"},
  corpses        = {letter = "y", preset = "corpses"},
}

-- Comma-separated CATEGORIES arg -> ordered, deduplicated list of valid
-- names, or nil, err naming the bad token and the valid set. Shared by
-- place and configure so the two commands can never disagree on spelling
-- or validity.
local function parse_categories(csv)
  if not csv or csv == "" then
    return nil, "CATEGORIES is required (comma-separated, from: "
      .. table.concat(CATEGORY_NAMES, ", ") .. ")"
  end
  local names, seen = {}, {}
  for tok in csv:gmatch('[^,]+') do
    if not CATEGORY_INFO[tok] then
      return nil, "unknown category '" .. tok .. "'; valid: " .. table.concat(CATEGORY_NAMES, ", ")
    end
    if not seen[tok] then
      seen[tok] = true
      table.insert(names, tok)
    end
  end
  if #names == 0 then
    return nil, "CATEGORIES had no valid entries"
  end
  return names
end

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

local function accepted_categories(bld)
  local ok_f, flags = pcall(function() return bld.settings.flags end)
  if not ok_f or not flags then
    return nil
  end
  local out = {}
  for _, name in ipairs(CATEGORY_NAMES) do
    local ok_v, v = pcall(function() return flags[name] end)
    if ok_v and v then
      table.insert(out, name)
    end
  end
  return out
end

-- See header: per-tile containsTile walk, not the opaque countExtentTiles
-- int, so each tile can also get the hidden-tile check. Returns
-- (total_tiles, exact) -- exact is false only if containsTile itself could
-- not be called at all (API missing), in which case total_tiles falls back
-- to countExtentTiles with no per-tile hidden filter, and the caller must
-- say so rather than presenting it as equally precise.
local function total_tiles(bld)
  local any_ok = false
  local n = 0
  for x = bld.x1, bld.x2 do
    for y = bld.y1, bld.y2 do
      local ok_c, inside = pcall(dfhack.buildings.containsTile, bld, x, y)
      if ok_c then
        any_ok = true
        if inside and not is_hidden_tile(x, y, bld.z) then
          n = n + 1
        end
      end
    end
  end
  if any_ok then
    return n, true
  end
  local ok_ext, ext_n = pcall(dfhack.buildings.countExtentTiles, bld, 0)
  return (ok_ext and ext_n) or nil, false
end

-- See header: item-position dedup, not the raw item count.
local function occupied_tiles(bld)
  local ok_items, items = pcall(dfhack.buildings.getStockpileContents, bld)
  if not ok_items or not items then
    return nil
  end
  local seen = {}
  local n = 0
  for _, it in ipairs(items) do
    local ok_pos, x, y, z = pcall(dfhack.items.getPosition, it)
    if ok_pos and x and not is_hidden_tile(x, y, z) then
      local key = x .. "," .. y .. "," .. z
      if not seen[key] then
        seen[key] = true
        n = n + 1
      end
    end
  end
  return n
end

local function landmark_info(x1, x2, y1, y2, z)
  local cx = math.floor((x1 + x2) / 2 + 0.5)
  local cy = math.floor((y1 + y2) / 2 + 0.5)
  local ok_near, info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  return ok_near and info or nil
end

-- Shared by `links` (read) and the new `configure`/`link`/`unlink` (write):
-- one linear scan over every building by id, factored out so all four
-- commands agree on how an id resolves.
local function find_building_by_id(id)
  for _, bld in ipairs(df.global.world.buildings.all) do
    if bld.id == id then
      return bld
    end
  end
  return nil
end

-- ---------------------------------------------------------------------------
-- Links-only flag and container counts (handoffs/2026-10-07-stockpile-tool-
-- gaps.md items 1 and 2).
--
-- FIELD NAMES ARE UNVERIFIED. No df-structures or DFHack source is available
-- offline in this repo (grep over the repo finds the names only in
-- research/2026-10-07-stockpile-logistics.md, "recalled as `use_links_only`,
-- not read this session"). Recalled from df-structures'
-- building_stockpilest: `use_links_only`, `max_barrels`, `max_bins`,
-- `max_wheelbarrows` directly on the building. Every read is pcall'd and a
-- field the install does not have reads as nil, reported as such (never a
-- guessed value): nothing here hard-codes a default, per the research's own
-- "read the field live" rule. Only a live read on the fort settles the names
-- and the polarity of `use_links_only`.
-- ---------------------------------------------------------------------------

local CONTAINER_FIELDS = {"max_barrels", "max_bins", "max_wheelbarrows"}
local LINKS_ONLY_FIELD = "use_links_only"

local function read_field(bld, name)
  local ok, v = pcall(function() return bld[name] end)
  if ok then
    return v
  end
  return nil
end

-- Normalises the flag whether the install stores it as a bool or an int.
local function as_bool(v)
  if v == nil then
    return nil
  end
  if type(v) == "number" then
    return v ~= 0
  end
  return v and true or false
end

local function links_only_of(bld)
  return as_bool(read_field(bld, LINKS_ONLY_FIELD))
end

local function containers_of(bld)
  local out, any = {}, false
  for _, f in ipairs(CONTAINER_FIELDS) do
    local v = read_field(bld, f)
    if type(v) == "number" then
      any = true
    end
    out[f] = type(v) == "number" and v or nil
  end
  if not any then
    return nil
  end
  return out
end

function list_stockpiles()
  local out = {}
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_type, btype = pcall(function() return bld:getType() end)
    if ok_type and btype == df.building_type.Stockpile then
      local total, total_exact = total_tiles(bld)
      local info = landmark_info(bld.x1, bld.x2, bld.y1, bld.y2, bld.z)
      table.insert(out, {
        id = bld.id,
        near_landmark = info and info.name or nil,
        direction = info and info.direction or nil,
        distance_tiles = info and info.distance_tiles or nil,
        occupied_tiles = occupied_tiles(bld),
        total_tiles = total,
        total_tiles_exact = total_exact,
        accepts = accepted_categories(bld),
        links_only = links_only_of(bld),
        containers = containers_of(bld),
      })
    end
  end
  return {stockpiles = out}
end

local LINK_FIELDS = {
  "give_to_pile", "take_from_pile", "give_to_workshop", "take_from_workshop",
}

-- See header: defensive on purpose -- nothing on Uniboslan is linked today,
-- so the "target is a usable building pointer" assumption is untested live.
local function resolve_link_target(target)
  local ok_id, id = pcall(function() return target.id end)
  if not ok_id or not id then
    return nil
  end
  local ok_type, btype = pcall(function() return target:getType() end)
  local kind = ok_type and df.building_type[btype] or nil
  local ok_bounds, x1, x2, y1, y2, z =
    pcall(function()
      return target.x1, target.x2, target.y1, target.y2, target.z
    end)
  local info = ok_bounds and landmark_info(x1, x2, y1, y2, z) or nil
  return {
    id = id,
    kind = kind,
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
  }
end

local function read_links(links_struct)
  local out = {}
  for _, field in ipairs(LINK_FIELDS) do
    local entry = {count = 0, targets = {}, resolved = true}
    local ok_vec, vec = pcall(function() return links_struct[field] end)
    if ok_vec and vec then
      local ok_len, n = pcall(function() return #vec end)
      if ok_len then
        entry.count = n
        for i = 0, n - 1 do
          local ok_t, t = pcall(function() return vec[i] end)
          local resolved = ok_t and t and resolve_link_target(t)
          if resolved then
            table.insert(entry.targets, resolved)
          elseif n > 0 then
            entry.resolved = false
          end
        end
      else
        entry.resolved = false
      end
    else
      entry.resolved = false
    end
    out[field] = entry
  end
  return out
end

-- Shared by `links` (read) and the new `link`/`unlink` (write): resolves an
-- id to (bld, "stockpile"|"workshop", nil) or (nil, nil, err) -- the exact
-- two kinds a link edge can touch, per the file header's LINKS section.
local function resolve_pile_or_shop(id)
  id = tonumber(id)
  if not id then
    return nil, nil, "ID must be a number"
  end
  local found = find_building_by_id(id)
  if not found then
    return nil, nil, "no building with id " .. tostring(id)
  end
  local ok_type, btype = pcall(function() return found:getType() end)
  if not ok_type then
    return nil, nil, "could not resolve building type for id " .. tostring(id)
  end
  if btype == df.building_type.Stockpile then
    return found, "stockpile", nil
  elseif btype == df.building_type.Workshop
      or (df.building_type.Furnace ~= nil and btype == df.building_type.Furnace) then
    -- A Furnace (smelter, kiln...) carries the same `profile.links` as a
    -- Workshop and is a link target in the game; treated as kind "workshop"
    -- so link/unlink/health/plan-feed need no second branch. UNVERIFIED live:
    -- the existing live checks covered a Workshop only.
    return found, "workshop", nil
  else
    local ok_name, name = pcall(function() return df.building_type[btype] end)
    return nil, nil, "id " .. tostring(id) .. " is not a stockpile or workshop ("
      .. (ok_name and name or "unknown type") .. ")"
  end
end

function stockpile_links(id)
  local found, kind, err = resolve_pile_or_shop(id)
  if not found then
    return nil, err
  end
  if kind == "stockpile" then
    return {id = tonumber(id), kind = kind, links = read_links(found.links),
            links_only = links_only_of(found), containers = containers_of(found)}
  end
  local ok_p, prof = pcall(function() return found.profile end)
  if not ok_p or not prof then
    return nil, "workshop id " .. tostring(id) .. " has no profile"
  end
  return {id = tonumber(id), kind = kind, links = read_links(prof.links)}
end

-- ---------------------------------------------------------------------------
-- place: site-find + #place, same shape as every other WxH designating tool
-- in this codebase (df-overseer-workshop.lua's build_workshop is the closest
-- relative -- one generated blueprint, one quickfort run).
-- ---------------------------------------------------------------------------

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

-- Duplicated from df-overseer-openarea.lua/df-overseer-workshop.lua rather
-- than shared -- see either file's own comment for why.
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- Every top-left position where a w-by-h window is entirely free tiles
-- (openarea_mod.is_free -- see the file header's WHY note on its
-- coarseness vs place.lua's own is_valid_stockpile_tile), within the given
-- box at the given z. Same shape as df-overseer-workshop.lua's own
-- find_candidates, calling the reqscript'd is_free rather than a local copy.
local function find_place_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local free = {}
  for x = min_x, max_x do
    free[x] = {}
    for y = min_y, max_y do
      free[x][y] = openarea_mod.is_free(x, y, z)
    end
  end
  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      local fits = true
      for dx = 0, w - 1 do
        if not fits then break end
        for dy = 0, h - 1 do
          if not free[x + dx][y + dy] then
            fits = false
            break
          end
        end
      end
      if fits then
        table.insert(candidates, {x = x, y = y})
      end
    end
  end
  return candidates
end

-- res_id: a candidate window overlapping a reservation this call does not
-- hold is dropped before ranking, via reservations_mod's own shared
-- `filter_reserved`, same pattern as every other finder in this codebase.
local function ranked_place_candidates(w, h, level, near, radius_tiles, res_id)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local candidates = find_place_candidates(
    w, h, z, ax - radius, ax + radius, ay - radius, ay + radius)
  candidates = reservations_mod.filter_reserved(candidates, res_id,
    function(c) return reservations_mod.rect_tiles(c.x, c.y, z, w, h) end)

  for _, c in ipairs(candidates) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(candidates, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local chosen = {}
  for _, c in ipairs(candidates) do
    local ok = true
    for _, existing in ipairs(chosen) do
      if overlaps(c, existing, w, h) then
        ok = false
        break
      end
    end
    if ok then
      table.insert(chosen, c)
      if #chosen >= MAX_RESULTS then
        break
      end
    end
  end
  return chosen, nil, z
end

-- Concatenates each requested category's #place letter (place.lua:78-97) --
-- several letters in one cell make one custom pile accepting all of them.
local function place_key(names)
  local letters = {}
  for _, n in ipairs(names) do
    table.insert(letters, CATEGORY_INFO[n].letter)
  end
  return table.concat(letters)
end

local function place_blueprint_text(w, h, key)
  local rows = {"#place generated by df-overseer-stockpile"}
  for _ = 1, h do
    local cells = {}
    for _ = 1, w do
      cells[#cells + 1] = key
    end
    rows[#rows + 1] = table.concat(cells, ",")
  end
  return table.concat(rows, "\n") .. "\n"
end

local function write_place_blueprint(w, h, key)
  local filename = string.format("_tmp-stockpile-%s-%dx%d-%d.csv", key, w, h, os.time())
  local path = "dfhack-config/blueprints/" .. filename
  local f, open_err = io.open(path, "w")
  if not f then
    return nil, "could not open blueprint for writing: " .. tostring(open_err)
  end
  f:write(place_blueprint_text(w, h, key))
  f:close()
  return filename
end

-- Duplicated from df-overseer-zone.lua/df-overseer-openarea.lua's own
-- parse_quickfort_stats rather than shared -- same rationale as
-- resolve_level above.
local function parse_quickfort_stats(output)
  local stats = {}
  if not output then
    return stats
  end
  for line in output:gmatch('[^\n]+') do
    local label, value = line:match('^  ([^:]-): (%d+)%s*$')
    if label and value then
      stats[label] = tonumber(value)
    end
  end
  return stats
end

local function max_stockpile_id()
  local sv = df.global.world.buildings.other.STOCKPILE
  local m = -1
  for i = 0, math.min(#sv, 5000) - 1 do
    if sv[i].id > m then
      m = sv[i].id
    end
  end
  return m
end

-- DRY_RUN defaults to true. RES_ID/OVERRIDE exactly as every other
-- designating tool (df-overseer-openarea.lua/df-overseer-workshop.lua/
-- df-overseer-zone.lua): checked against the fixed literal "stockpile" kind
-- token (no per-kind template distinction the way zone kinds have).
function place_stockpile(w, h, level, near, categories, rank, radius_tiles, dry_run, res_id, override)
  if override ~= nil and res_id == nil then
    return nil, "OVERRIDE requires RES_ID"
  end
  w, h = tonumber(w), tonumber(h)
  if not (w and h) then
    return nil, "W and H are required numbers"
  end
  -- place.lua's own stockpile_template: width/height 1..31 (file header,
  -- see this file's own header WRITING/SIZE note).
  if w < 1 or w > 31 or h < 1 or h > 31 then
    return nil, "W and H must each be between 1 and 31 (quickfort's own stockpile size limit)"
  end
  local names, cerr = parse_categories(categories)
  if not names then
    return nil, cerr
  end
  rank = rank or 1
  local dry = truthy_dry_run(dry_run)

  local chosen, err, z = ranked_place_candidates(w, h, level, near, radius_tiles, res_id)
  if err then
    return nil, err
  end
  if rank < 1 or rank > #chosen then
    return nil, string.format("no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end
  local c = chosen[rank]
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)
  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local info = ok_near and near_info

  -- Computed before check_tiles/designating; recorded only at the real
  -- success point below, same pattern as every other designating tool.
  local tiles = reservations_mod.rect_tiles(c.x, c.y, z, w, h)
  local needs_override = override ~= nil
    and reservations_mod.override_needed(tiles, res_id, "stockpile")
  local conflict = reservations_mod.check_tiles(tiles, nil, res_id, "stockpile", override)
  if conflict then
    return nil, conflict.message
  end

  local key = place_key(names)
  local result = {
    rank = rank,
    dims = {w, h},
    categories = names,
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    dry_run = dry,
  }

  local filename, write_err = write_place_blueprint(w, h, key)
  if not filename then
    result.quickfort_ok = false
    result.quickfort_error = write_err
    return result
  end
  result.blueprint = {mode = "place", key = key, file = filename, cells = string.format("%dx%d", w, h)}
  local coord = string.format('%d,%d,%d', c.x, c.y, z)

  if dry then
    local ok_run, output, res = pcall(
      dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord, '-d')
    local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
    result.blueprint.removed = (ok_rm and rm == true)
    local stats = ok_run and parse_quickfort_stats(output) or nil
    result.validation = {
      by = "quickfort run --dry-run",
      ok = ok_run and res == CR_OK,
      error = (not ok_run) and tostring(output) or nil,
      stats = stats or {},
    }
    return result
  end

  -- REAL PATH. UNTESTED live: no real placement has been allowed this
  -- session (offline worktree, no VM access).
  local before_id = max_stockpile_id()
  local ok_run, output, res = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', filename, '-c', coord)
  local ok_rm, rm = pcall(os.remove, "dfhack-config/blueprints/" .. filename)
  result.blueprint.removed = (ok_rm and rm == true)
  local quickfort_ok = ok_run and res == CR_OK
  result.quickfort_ok = quickfort_ok
  result.quickfort_error = (not ok_run) and tostring(output) or nil
  result.quickfort_stats = ok_run and parse_quickfort_stats(output) or nil
  if needs_override and quickfort_ok then
    reservations_mod.record_override(res_id, "stockpile.place", "stockpile", override)
  end

  -- Task 4: report what the game now holds, not what was asked. Find the
  -- newest Stockpile at the window's own centre tile (findAtTile, the same
  -- occupancy primitive df-overseer-openarea.lua's is_free already uses).
  local cpos = xyz2pos(cx, cy, z)
  local bld = nil
  local ok_b, found = pcall(dfhack.buildings.findAtTile, cpos)
  if ok_b and found and found.id > before_id then
    local ok_t, btype = pcall(function() return found:getType() end)
    if ok_t and btype == df.building_type.Stockpile then
      bld = found
    end
  end
  local total = bld and total_tiles(bld) or nil
  result.read_back = {
    stockpile_found = bld ~= nil,
    id = bld and bld.id or nil,
    accepts = bld and accepted_categories(bld) or nil,
    occupied_tiles = bld and occupied_tiles(bld) or nil,
    total_tiles = total,
  }
  return result
end

-- ---------------------------------------------------------------------------
-- configure: replace-semantics category toggle on an EXISTING pile. Diffs
-- the requested set against accepted_categories' own current read so a
-- caller never has to track what a pile already accepts -- enable what's
-- missing, disable what's no longer wanted, leave the rest untouched.
-- DRY_RUN defaults to true (not asked explicitly by the handoff item 3, but
-- every other mutating command in this file/codebase defaults it, and this
-- one mutates a live building same as the others).
-- ---------------------------------------------------------------------------

function stockpile_configure(id, categories, dry_run)
  id = tonumber(id)
  if not id then
    return nil, "ID must be a number"
  end
  local bld, kind, rerr = resolve_pile_or_shop(id)
  if not bld then
    return nil, rerr
  end
  if kind ~= "stockpile" then
    return nil, "id " .. tostring(id) .. " is not a stockpile (" .. kind .. ")"
  end
  local names, cerr = parse_categories(categories)
  if not names then
    return nil, cerr
  end
  local dry = truthy_dry_run(dry_run)

  local want = {}
  for _, n in ipairs(names) do
    want[n] = true
  end
  local current = accepted_categories(bld) or {}
  local current_set = {}
  for _, n in ipairs(current) do
    current_set[n] = true
  end

  local to_enable, to_disable = {}, {}
  for _, n in ipairs(CATEGORY_NAMES) do
    if want[n] and not current_set[n] then
      table.insert(to_enable, n)
    elseif current_set[n] and not want[n] then
      table.insert(to_disable, n)
    end
  end

  local result = {
    id = id, dry_run = dry, requested = names, current_accepts = current,
    would_enable = to_enable, would_disable = to_disable,
  }
  if dry then
    return result
  end

  -- REAL PATH. UNTESTED live. See the file header's PRESETS EXIST note:
  -- mode='enable'/'disable' each act on one whole category via its own
  -- cat_<preset> library file.
  local stockpiles_mod = require('plugins.stockpiles')
  for _, n in ipairs(to_enable) do
    stockpiles_mod.import_settings("library/cat_" .. CATEGORY_INFO[n].preset, {id = id, mode = "enable"})
  end
  for _, n in ipairs(to_disable) do
    stockpiles_mod.import_settings("library/cat_" .. CATEGORY_INFO[n].preset, {id = id, mode = "disable"})
  end
  result.read_back = {accepts = accepted_categories(bld)}
  return result
end

-- ---------------------------------------------------------------------------
-- Per-kind input/output reads (handoffs/2026-10-07-stockpile-tool-gaps.md
-- items 4 and 5). The table itself is DATA in
-- df-overseer-stockpile-kinds.lua; everything below is generic over it.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Runtime derivation of a workshop kind's input/output classes from the
-- game's own data (coordinator ruling 2026-10-07, CLAUDE.md "Tools must be
-- generalisable"): `dfhack.workshops.getJobs(building_type, subtype, custom)`
-- is the module behind the in-game "add job" menu and the source
-- workjob.list-jobs reads: per job, its reagent specs (`items`) and
-- `job_fields` (job_type, reaction_name). Products of reaction jobs come from
-- `df.global.world.raws.reactions.reactions[].products`. What the game does
-- not encode (item type to stockpile category, a smelter's fuel, products of
-- built-in jobs) is HAND DATA in df-overseer-stockpile-kinds.lua, each part
-- marked there. If derivation fails for a kind the hand FALLBACK table is
-- used and the entry says source = "fallback_table".
--
-- A kind has many jobs and a workshop runs ONE at a time, so reagents of
-- different jobs are alternatives, not a joint requirement. A class is
-- therefore `partial` (needed by some jobs, not all) or mandatory (every job
-- of the kind needs it); only a mandatory class is a trap when unlinked.
-- UNVERIFIED LIVE: the spec field shapes (item_type, flags1/2/3 tables) are
-- the ones df-overseer-workjob.lua reads live; the category mapping is hand
-- data; reaction product field names (`item_type`) are recalled.
-- ---------------------------------------------------------------------------

local FLAG_FIELDS = {"flags1", "flags2", "flags3"}

-- (building_type, subtype, canonical_name) for a workshop/furnace kind name,
-- case-insensitive, via the enums' own bounds (pairs() over a DFHack enum
-- does not yield names, per df-overseer-workjob.lua's header).
local function kind_ids(name)
  if not name then
    return nil
  end
  local want = tostring(name):lower()
  for _, spec in ipairs({{"workshop_type", df.building_type.Workshop},
                         {"furnace_type", df.building_type.Furnace}}) do
    local enum = df[spec[1]]
    if enum and spec[2] ~= nil then
      local ok_f, first = pcall(function() return enum._first_item end)
      local ok_l, last = pcall(function() return enum._last_item end)
      if ok_f and ok_l and first and last then
        for i = first, last do
          local ok_n, n = pcall(function() return enum[i] end)
          if ok_n and type(n) == "string" and n:lower() == want and n ~= "Custom" then
            return spec[2], i, n
          end
        end
      end
    end
  end
  return nil
end

local function known_kind_names()
  local out, seen = {}, {}
  for _, enum_name in ipairs({"workshop_type", "furnace_type"}) do
    local enum = df[enum_name]
    local ok_f, first = pcall(function() return enum._first_item end)
    local ok_l, last = pcall(function() return enum._last_item end)
    if ok_f and ok_l and first and last then
      for i = first, last do
        local ok_n, n = pcall(function() return enum[i] end)
        if ok_n and type(n) == "string" and n ~= "Custom" and not seen[n] then
          seen[n] = true
          table.insert(out, n)
        end
      end
    end
  end
  for n in pairs(kinds_mod.FALLBACK_KINDS) do
    if not seen[n] then
      seen[n] = true
      table.insert(out, n)
    end
  end
  table.sort(out)
  return out
end

-- One reagent spec -> {categories, role, type_name} or nil, unmapped_reason.
local function classify_spec(spec)
  local ok_t, itype = pcall(function() return spec.item_type end)
  local type_name = nil
  if ok_t and type(itype) == "number" and itype >= 0 then
    local ok_n, n = pcall(function() return df.item_type[itype] end)
    if ok_n and type(n) == "string" then
      type_name = n
    end
  end
  if type_name then
    local cats = kinds_mod.ITEM_TYPE_CATEGORIES[type_name]
    if not cats then
      return nil, "item type " .. type_name
    end
    local role = kinds_mod.CONTAINER_ITEM_TYPES[type_name] and "container" or "input"
    return {categories = cats, role = role, type_name = type_name, availability = type_name}
  end
  -- Tag-matched reagent: look for a flag the hand data knows.
  for _, field in ipairs(FLAG_FIELDS) do
    local ok_f, tbl = pcall(function() return spec[field] end)
    if ok_f and type(tbl) == "table" then
      local flag_names = {}
      for flag, on in pairs(tbl) do
        if on then
          table.insert(flag_names, tostring(flag))
        end
      end
      table.sort(flag_names)  -- deterministic: pairs() order is not
      for _, flag in ipairs(flag_names) do
        local fc = kinds_mod.FLAG_CATEGORIES[flag]
        if fc then
          return {categories = fc.categories, role = fc.role, type_name = "flag:" .. flag,
                  availability = fc.availability}
        end
      end
    end
  end
  return nil, "wildcard reagent with no known flag"
end

local function cats_key(role, cats)
  return role .. ":" .. table.concat(cats, "+")
end

local function reaction_products(reaction_name)
  local out = {}
  local ok, reactions = pcall(function() return df.global.world.raws.reactions.reactions end)
  if not ok or not reactions then
    return out
  end
  local ok_n, n = pcall(function() return #reactions end)
  if not ok_n or not n then
    return out
  end
  for i = 0, n - 1 do
    local ok_r, r = pcall(function() return reactions[i] end)
    if ok_r and r and r.code == reaction_name then
      local ok_p, prods = pcall(function() return r.products end)
      if ok_p and prods then
        local ok_pn, pn = pcall(function() return #prods end)
        for j = 0, (ok_pn and pn or 0) - 1 do
          local ok_pp, p = pcall(function() return prods[j] end)
          local ok_it, it = pcall(function() return p.item_type end)
          if ok_pp and p and ok_it and type(it) == "number" and it >= 0 then
            local ok_in, iname = pcall(function() return df.item_type[it] end)
            if ok_in and type(iname) == "string" then
              table.insert(out, iname)
            end
          end
        end
      end
      break
    end
  end
  return out
end

-- Derives one kind from the game's job table. Returns an entry or nil, why.
local function derive_kind(btype, sub, canonical)
  local ok_m, workshops_mod = pcall(require, 'dfhack.workshops')
  if not ok_m or type(workshops_mod) ~= "table" or not workshops_mod.getJobs then
    return nil, "dfhack.workshops.getJobs unavailable"
  end
  local ok_j, jobs = pcall(workshops_mod.getJobs, btype, sub, -1)
  if not ok_j or jobs == nil then
    return nil, "getJobs failed"
  end
  local classes, order, unmapped, unmapped_seen = {}, {}, {}, {}
  local product_types, product_seen = {}, {}
  local job_count = 0
  local keys = {}
  for k in pairs(jobs) do
    table.insert(keys, k)
  end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do
    local job = jobs[k]
    local specs = job.items
    if type(specs) == "table" and #specs > 0 then
      job_count = job_count + 1
      local in_this_job = {}
      for _, spec in ipairs(specs) do
        local c, why = classify_spec(spec)
        if not c then
          if not unmapped_seen[why] then
            unmapped_seen[why] = true
            table.insert(unmapped, why)
          end
        else
          local key = cats_key(c.role, c.categories)
          if not classes[key] then
            classes[key] = {role = c.role, categories = c.categories, types = {}, type_seen = {}, jobs = 0}
            table.insert(order, key)
          end
          local cl = classes[key]
          cl.avail = cl.avail or c.availability
          if not cl.type_seen[c.type_name] then
            cl.type_seen[c.type_name] = true
            table.insert(cl.types, c.type_name)
          end
          if not in_this_job[key] then
            in_this_job[key] = true
            cl.jobs = cl.jobs + 1
          end
        end
      end
    end
    local rn = job.job_fields and job.job_fields.reaction_name
    if rn then
      for _, t in ipairs(reaction_products(rn)) do
        if not product_seen[t] then
          product_seen[t] = true
          table.insert(product_types, t)
        end
      end
    end
  end
  if job_count == 0 then
    return nil, "no jobs with reagents"
  end
  local inputs = {}
  for _, key in ipairs(order) do
    local cl = classes[key]
    local partial = cl.jobs < job_count
    local avail = cl.avail
    table.insert(inputs, {
      id = cl.role .. ":" .. table.concat(cl.categories, "+"),
      label = table.concat(cl.types, "/"):lower(),
      role = cl.role, categories = cl.categories, availability = avail,
      feeder_tiles = kinds_mod.FEEDER_TILES[cl.role] or 4,
      partial = partial,
      optional_when = partial and ("only " .. cl.jobs .. " of " .. job_count
        .. " jobs of this workshop need it") or nil,
      jobs_needing = cl.jobs, job_count = job_count,
    })
  end
  local have = {}
  for _, c in ipairs(inputs) do
    have[c.role .. ":" .. table.concat(c.categories, "+")] = true
  end
  for _, ov in ipairs(kinds_mod.OVERLAYS[canonical] or {}) do
    local oid = ov.role .. ":" .. table.concat(ov.categories, "+")
    if not have[oid] then
      table.insert(inputs, {
        id = ov.id, label = ov.label, role = ov.role, categories = ov.categories,
        feeder_tiles = kinds_mod.FEEDER_TILES[ov.role] or 4,
        optional_when = ov.optional_when, overlay = true,
      })
    end
  end
  local outputs, out_seen = {}, {}
  for _, t in ipairs(product_types) do
    local cats = kinds_mod.ITEM_TYPE_CATEGORIES[t]
    if cats then
      local oid = "product:" .. table.concat(cats, "+")
      if not out_seen[oid] then
        out_seen[oid] = true
        table.insert(outputs, {id = oid, label = t:lower(), categories = cats, derived = true})
      end
    elseif not unmapped_seen["product " .. t] then
      unmapped_seen["product " .. t] = true
      table.insert(unmapped, "product " .. t)
    end
  end
  for _, h in ipairs(kinds_mod.OUTPUT_HINTS[canonical] or {}) do
    table.insert(outputs, {id = h.id, label = h.label, categories = h.categories, hand_hint = true})
  end
  return {source = "game_data", inputs = inputs, outputs = outputs,
          unmapped = unmapped, job_count = job_count}
end

local derived_cache = {}

-- Returns (canonical_name, entry) or nil. entry.source is "game_data" (derived
-- from the game's jobs) or "fallback_table" (hand table; derivation failed,
-- entry.derive_error says why). Cached per process: the job table does not
-- change while the game runs.
local function find_kind(name)
  local btype, sub, canonical = kind_ids(name)
  local fb_name, fb = kinds_mod.find_fallback_kind(name)
  canonical = canonical or fb_name
  if not canonical then
    return nil
  end
  if derived_cache[canonical] == nil then
    local entry, why
    if btype then
      entry, why = derive_kind(btype, sub, canonical)
    else
      why = "kind not in the game's workshop/furnace enums"
    end
    if not entry and fb then
      entry = {source = "fallback_table", inputs = fb.inputs, outputs = fb.outputs,
               unmapped = {}, derive_error = why}
    end
    derived_cache[canonical] = entry or false
  end
  local e = derived_cache[canonical]
  if not e then
    return nil
  end
  return canonical, e
end

local function vec_to_list(vec)
  local out = {}
  if not vec then
    return out
  end
  local ok_len, n = pcall(function() return #vec end)
  if not ok_len or not n then
    return out
  end
  for i = 0, n - 1 do
    local ok_t, t = pcall(function() return vec[i] end)
    if ok_t and t then
      table.insert(out, t)
    end
  end
  return out
end

-- Game subtype name of a Workshop or Furnace building, or nil (a custom
-- workshop, or an install where the enum read fails).
local function workshop_kind_name(bld)
  local ok_t, btype = pcall(function() return bld:getType() end)
  if not ok_t then
    return nil
  end
  local enum_name = (btype == df.building_type.Workshop) and "workshop_type" or "furnace_type"
  local ok, name = pcall(function() return df[enum_name][bld.type] end)
  if ok and type(name) == "string" then
    return name
  end
  return nil
end

local function is_shop_type(btype)
  return btype == df.building_type.Workshop
    or (df.building_type.Furnace ~= nil and btype == df.building_type.Furnace)
end

local function shop_links(bld)
  local ok, prof = pcall(function() return bld.profile end)
  if not ok or not prof then
    return nil
  end
  return prof.links
end

local function accepts_set(pile)
  local set = {}
  for _, n in ipairs(accepted_categories(pile) or {}) do
    set[n] = true
  end
  return set
end

local function accepts_any(set, cats)
  for _, c in ipairs(cats) do
    if set[c] then
      return true
    end
  end
  return false
end

local function cats_text(cats)
  return table.concat(cats, "/")
end

-- One pile's id list, for reports.
local function pile_ids(piles)
  local out = {}
  for _, p in ipairs(piles) do
    table.insert(out, p.id)
  end
  return out
end

-- The single-class-trap check (research section 1, rec 4): which input
-- classes of `entry` would have NO linked source if the workshop's
-- take-from piles were `piles` (a list of pile buildings). Optional classes
-- (optional_when) come back separately: not a trap, but worth saying.
local function uncovered_classes(entry, piles)
  local missing, optional = {}, {}
  for _, cls in ipairs(entry.inputs) do
    local covered = false
    for _, p in ipairs(piles) do
      if accepts_any(accepts_set(p), cls.categories) then
        covered = true
        break
      end
    end
    if not covered then
      if cls.optional_when or cls.partial then
        table.insert(optional, cls)
      else
        table.insert(missing, cls)
      end
    end
  end
  return missing, optional
end

local function class_labels(list)
  local out = {}
  for _, c in ipairs(list) do
    table.insert(out, c.id .. " (" .. c.label .. ")")
  end
  return out
end

-- Warnings for a link edge about to be made (or made). `pile` is the
-- stockpile (ID), `shop` the workshop/furnace target, `direction` give|take
-- from the PILE's point of view. Never refuses: warns, per the handoff.
local function link_warnings(pile, shop, direction)
  local warnings = {}
  local kname = workshop_kind_name(shop)
  local _, entry = find_kind(kname)
  if not entry then
    table.insert(warnings, {
      code = "unknown_workshop_kind",
      message = "no input/output table for workshop kind '" .. tostring(kname)
        .. "'; the single-class trap cannot be checked",
    })
    return warnings
  end
  if direction == "give" then
    -- The pile will feed the workshop: after this link the workshop draws
    -- ONLY from its linked piles (wiki Workshop page), so every input class
    -- needs a source among them.
    local links = shop_links(shop)
    local piles = links and vec_to_list(links.take_from_pile) or {}
    local already = false
    for _, p in ipairs(piles) do
      if p.id == pile.id then
        already = true
      end
    end
    if not already then
      table.insert(piles, pile)
    end
    local feeds_any = false
    for _, cls in ipairs(entry.inputs) do
      if accepts_any(accepts_set(pile), cls.categories) then
        feeds_any = true
      end
    end
    if not feeds_any then
      table.insert(warnings, {
        code = "pile_feeds_no_input_class",
        message = "pile " .. tostring(pile.id) .. " accepts none of the input classes of a "
          .. kname .. "; once linked the workshop looks only in linked piles",
      })
    end
    local missing, optional = uncovered_classes(entry, piles)
    if #missing > 0 then
      table.insert(warnings, {
        code = "single_class_trap",
        message = "after this link the " .. kname .. " draws only from linked piles and no linked pile "
          .. "accepts: " .. table.concat(class_labels(missing), ", ")
          .. "; it will stall until every input class is linked",
        uncovered = class_labels(missing),
      })
    end
    if #optional > 0 then
      table.insert(warnings, {
        code = "optional_class_unlinked",
        message = "no linked pile accepts: " .. table.concat(class_labels(optional), ", ")
          .. " (needed unless " .. tostring(optional[1].optional_when) .. ")",
        uncovered = class_labels(optional),
      })
    end
  else
    -- Pile takes from the workshop: an output pile. Products the pile does
    -- not accept sit in the workshop (wiki Workshop page).
    local set = accepts_set(pile)
    local rejected = {}
    for _, prod in ipairs(entry.outputs) do
      if not accepts_any(set, prod.categories) then
        table.insert(rejected, prod.id .. " (" .. prod.label .. ", needs "
          .. cats_text(prod.categories) .. ")")
      end
    end
    if #rejected > 0 then
      table.insert(warnings, {
        code = "output_pile_rejects_products",
        message = "pile " .. tostring(pile.id) .. " does not accept: " .. table.concat(rejected, ", ")
          .. "; those products are not moved and sit in the " .. kname .. " until a linked pile accepts them",
        uncovered = rejected,
      })
    end
  end
  return warnings
end

-- ---------------------------------------------------------------------------
-- link / unlink: one edge (give or take) between this stockpile and another
-- pile or a workshop, by id. See the file header's LINKS section for the
-- source citations behind LINK_RULE -- table-driven, no per-kind branch.
-- ---------------------------------------------------------------------------

-- Where the OTHER end's link vectors live: a stockpile's own `.links`, or a
-- workshop's `.profile.links` (both confirmed live by this file's own
-- `links` command; see its header and TOOLS.yaml entry).
local function other_links_struct(bld, kind)
  if kind == "workshop" then
    local ok, prof = pcall(function() return bld.profile end)
    if not ok or not prof then
      return nil, "workshop has no profile"
    end
    return prof.links
  end
  return bld.links
end

-- direction (this stockpile's own relation to the target) x target_kind ->
-- {self_field, other_field}, both on the SAME LINK_FIELDS vocabulary
-- stockpile_links already reads. Matches place.lua's link_stockpiles
-- exactly (file header): give to a pile writes give_to_pile/take_from_pile;
-- give to a workshop writes give_to_workshop/(workshop's)take_from_pile;
-- take from a pile writes take_from_pile/give_to_pile; take from a workshop
-- writes take_from_workshop/(workshop's)give_to_pile.
local LINK_RULE = {
  give = {
    stockpile = {self_field = "give_to_pile", other_field = "take_from_pile"},
    workshop  = {self_field = "give_to_workshop", other_field = "take_from_pile"},
  },
  take = {
    stockpile = {self_field = "take_from_pile", other_field = "give_to_pile"},
    workshop  = {self_field = "take_from_workshop", other_field = "give_to_pile"},
  },
}

-- apply: "link" (insert_sorted both ends) or "unlink" (erase_sorted_key both
-- ends) -- one function, since the two are mirror images of each other over
-- the same resolved rule. DRY_RUN defaults to true.
local function do_link_change(id, target_id, direction, dry_run, apply)
  local bld, kind, err = resolve_pile_or_shop(id)
  if not bld then
    return nil, err
  end
  if kind ~= "stockpile" then
    return nil, "ID " .. tostring(id) .. " must be a stockpile (" .. kind .. ")"
  end
  local target_bld, target_kind, terr = resolve_pile_or_shop(target_id)
  if not target_bld then
    return nil, terr
  end
  local rule = LINK_RULE[direction] and LINK_RULE[direction][target_kind]
  if not rule then
    return nil, "direction must be 'give' or 'take'; TARGET_ID must resolve to a stockpile or workshop"
  end
  local dry = truthy_dry_run(dry_run)
  local result = {
    id = tonumber(id), target_id = tonumber(target_id),
    direction = direction, target_kind = target_kind, dry_run = dry,
  }
  -- handoffs/2026-10-07-stockpile-tool-gaps.md item 5: warn (never refuse)
  -- on the single-class trap and on an output pile that rejects the
  -- workshop's products. Computed BEFORE the link is applied, so a dry run
  -- and a real run say the same thing. Only a link to a workshop/furnace
  -- has anything to check.
  if apply == "link" and target_kind == "workshop" then
    result.warnings = link_warnings(bld, target_bld, direction)
  end
  if dry then
    result.would = apply
    return result
  end

  -- REAL PATH. UNTESTED live.
  local self_vec = bld.links[rule.self_field]
  local other_struct, oerr = other_links_struct(target_bld, target_kind)
  if not other_struct then
    return nil, oerr
  end
  local other_vec = other_struct[rule.other_field]
  local utils = require('utils')
  if apply == "link" then
    utils.insert_sorted(self_vec, target_bld, 'id')
    utils.insert_sorted(other_vec, bld, 'id')
  else
    utils.erase_sorted_key(self_vec, tonumber(target_id), 'id')
    utils.erase_sorted_key(other_vec, tonumber(id), 'id')
  end

  -- Task 4: read back through the SAME stockpile_links the read-only
  -- command uses, not an echo of what was asked.
  result.read_back = stockpile_links(id)
  return result
end

function stockpile_link(id, target_id, direction, dry_run)
  return do_link_change(id, target_id, direction, dry_run, "link")
end

function stockpile_unlink(id, target_id, direction, dry_run)
  return do_link_change(id, target_id, direction, dry_run, "unlink")
end

-- ---------------------------------------------------------------------------
-- settings: links-only flag and container counts, WRITE
-- (handoffs/2026-10-07-stockpile-tool-gaps.md items 1 and 2). Field names are
-- UNVERIFIED, see links_only_of's header above. Unchanged fields are left
-- alone; an omitted argument or the word "keep" means unchanged. Refuses a
-- field this install does not expose rather than writing blind. DRY_RUN
-- defaults to true; a real run reads the values back.
-- ---------------------------------------------------------------------------

local function is_keep(v)
  return v == nil or tostring(v):lower() == "keep"
end

local function parse_count(name, v)
  if is_keep(v) then
    return nil
  end
  local n = tonumber(v)
  if not n or n < 0 or n ~= math.floor(n) then
    return nil, name .. " must be a whole number >= 0 (or 'keep')"
  end
  return n
end

function stockpile_settings(id, links_only, max_bins, max_barrels, max_wheelbarrows, dry_run)
  local bld, kind, rerr = resolve_pile_or_shop(id)
  if not bld then
    return nil, rerr
  end
  if kind ~= "stockpile" then
    return nil, "id " .. tostring(id) .. " is not a stockpile (" .. kind .. ")"
  end
  local want = {}
  if not is_keep(links_only) then
    local s = tostring(links_only):lower()
    if s == "true" or s == "1" or s == "yes" then
      want[LINKS_ONLY_FIELD] = true
    elseif s == "false" or s == "0" or s == "no" then
      want[LINKS_ONLY_FIELD] = false
    else
      return nil, "LINKS_ONLY must be true, false or keep"
    end
  end
  for field, raw in pairs({max_bins = max_bins, max_barrels = max_barrels, max_wheelbarrows = max_wheelbarrows}) do
    local n, perr = parse_count(field:upper(), raw)
    if perr then
      return nil, perr
    end
    if n ~= nil then
      want[field] = n
    end
  end
  if next(want) == nil then
    return nil, "nothing to change: give LINKS_ONLY, MAX_BINS, MAX_BARRELS or MAX_WHEELBARROWS"
  end
  local dry = truthy_dry_run(dry_run)

  local current, changes, unreadable = {}, {}, {}
  for field, to in pairs(want) do
    local v = read_field(bld, field)
    if v == nil then
      table.insert(unreadable, field)
    else
      if field == LINKS_ONLY_FIELD then
        current[field] = as_bool(v)
      else
        current[field] = v
      end
      if current[field] ~= to then
        changes[field] = {from = current[field], to = to}
      end
    end
  end
  if #unreadable > 0 then
    table.sort(unreadable)
    return nil, "this install does not expose: " .. table.concat(unreadable, ", ")
      .. " on a stockpile (field names are unverified); refusing to write blind"
  end
  local result = {id = tonumber(id), dry_run = dry, would_change = changes,
                  unverified_fields = true}
  if dry then
    return result
  end
  -- REAL PATH. UNTESTED live.
  for field, ch in pairs(changes) do
    local raw = read_field(bld, field)
    local value = ch.to
    if field == LINKS_ONLY_FIELD and type(raw) == "number" then
      value = ch.to and 1 or 0
    end
    local ok_w, werr = pcall(function() bld[field] = value end)
    if not ok_w then
      return nil, "writing " .. field .. " failed: " .. tostring(werr)
    end
  end
  result.read_back = {links_only = links_only_of(bld), containers = containers_of(bld)}
  return result
end

-- ---------------------------------------------------------------------------
-- materials / set-materials: material filters finer than the 17 categories
-- (handoffs/2026-10-07-stockpile-tool-gaps.md item 3). Reads the game's OWN
-- material list for the category (the raws vector the pile's per-material
-- booleans are indexed by), never a table of ours: adding a category is one
-- MATERIAL_FILTERS entry. UNVERIFIED live: the recalled layout is
-- `settings.<key>.mats`, a vector<bool> indexed like the raws vector (stone
-- by df.global.world.raws.inorganics, wood by raws.plants.all); the
-- `include` path picks which raws belong in the list (stone: IS_STONE
-- inorganics; wood: TREE plants) and is the part most likely to differ from
-- the in-game list. Replace semantics over the LISTED materials only;
-- indexes the list does not include are never touched.
-- ---------------------------------------------------------------------------

local MATERIAL_FILTERS = {
  stone = {settings_key = "stone", vec = "mats", raws = {"inorganics"},
           include = {"material", "flags", "IS_STONE"}},
  wood  = {settings_key = "wood", vec = "mats", raws = {"plants", "all"},
           include = {"flags", "TREE"}},
}

local function walk_path(root, path)
  local cur = root
  for _, key in ipairs(path) do
    local ok, nxt = pcall(function() return cur[key] end)
    if not ok or nxt == nil then
      return nil
    end
    cur = nxt
  end
  return cur
end

local function supported_filter_categories()
  local names = {}
  for k in pairs(MATERIAL_FILTERS) do
    table.insert(names, k)
  end
  table.sort(names)
  return names
end

-- {index =, name =, enabled =} for every listed material of `category`.
local function material_entries(bld, category)
  local spec = MATERIAL_FILTERS[category]
  if not spec then
    return nil, "no material list for category '" .. tostring(category) .. "'; supported: "
      .. table.concat(supported_filter_categories(), ", ")
  end
  local flags_vec = walk_path(bld, {"settings", spec.settings_key, spec.vec})
  if not flags_vec then
    return nil, "this install does not expose settings." .. spec.settings_key .. "." .. spec.vec
      .. " on a stockpile (layout unverified)"
  end
  local raws = walk_path(df.global.world.raws, spec.raws)
  if not raws then
    return nil, "could not read the game's " .. table.concat(spec.raws, ".") .. " list"
  end
  local out = {}
  local ok_len, n = pcall(function() return #raws end)
  if not ok_len or not n then
    return nil, "could not size the game's material list"
  end
  for i = 0, n - 1 do
    local ok_r, raw = pcall(function() return raws[i] end)
    if ok_r and raw then
      local included = walk_path(raw, spec.include)
      if included then
        local ok_id, name = pcall(function() return raw.id end)
        local ok_en, en = pcall(function() return flags_vec[i] end)
        if ok_id and type(name) == "string" then
          table.insert(out, {index = i, name = name, enabled = (ok_en and en) and true or false})
        end
      end
    end
  end
  return out, nil, spec
end

function stockpile_materials(id, category)
  local bld, kind, rerr = resolve_pile_or_shop(id)
  if not bld then
    return nil, rerr
  end
  if kind ~= "stockpile" then
    return nil, "id " .. tostring(id) .. " is not a stockpile (" .. kind .. ")"
  end
  local entries, err = material_entries(bld, category)
  if not entries then
    return nil, err
  end
  local enabled, disabled = {}, {}
  for _, e in ipairs(entries) do
    table.insert(e.enabled and enabled or disabled, e.name)
  end
  local cat_on = false
  for _, n in ipairs(accepted_categories(bld) or {}) do
    if n == category then
      cat_on = true
    end
  end
  return {id = tonumber(id), category = category, category_accepted = cat_on,
          enabled = enabled, disabled = disabled, total = #entries}
end

function stockpile_set_materials(id, category, materials, dry_run)
  local bld, kind, rerr = resolve_pile_or_shop(id)
  if not bld then
    return nil, rerr
  end
  if kind ~= "stockpile" then
    return nil, "id " .. tostring(id) .. " is not a stockpile (" .. kind .. ")"
  end
  if not materials or materials == "" then
    return nil, "MATERIALS is required (comma-separated names from stockpile.materials, or 'all' or 'none')"
  end
  local entries, err, spec = material_entries(bld, category)
  if not entries then
    return nil, err
  end
  local by_name = {}
  for _, e in ipairs(entries) do
    by_name[e.name:upper()] = e
  end
  local want = {}
  local lowered = materials:lower()
  if lowered == "all" then
    for _, e in ipairs(entries) do
      want[e.name] = true
    end
  elseif lowered ~= "none" then
    for tok in materials:gmatch('[^,]+') do
      local e = by_name[tok:upper()]
      if not e then
        return nil, "unknown " .. category .. " material '" .. tok
          .. "'; read stockpile.materials for the game's own list"
      end
      want[e.name] = true
    end
  end
  local dry = truthy_dry_run(dry_run)
  local to_enable, to_disable = {}, {}
  for _, e in ipairs(entries) do
    if want[e.name] and not e.enabled then
      table.insert(to_enable, e.name)
    elseif e.enabled and not want[e.name] then
      table.insert(to_disable, e.name)
    end
  end
  local warnings = {}
  local cat_on = false
  for _, n in ipairs(accepted_categories(bld) or {}) do
    if n == category then
      cat_on = true
    end
  end
  if not cat_on then
    table.insert(warnings, {
      code = "category_not_accepted",
      message = "the pile does not accept category '" .. category
        .. "' at all; material choices do nothing until stockpile.configure enables it",
    })
  end
  local result = {id = tonumber(id), category = category, dry_run = dry,
                  would_enable = to_enable, would_disable = to_disable, warnings = warnings}
  if dry then
    return result
  end
  -- REAL PATH. UNTESTED live.
  local flags_vec = walk_path(bld, {"settings", spec.settings_key, spec.vec})
  for _, e in ipairs(entries) do
    local target = want[e.name] and true or false
    if target ~= e.enabled then
      local ok_w, werr = pcall(function() flags_vec[e.index] = target end)
      if not ok_w then
        return nil, "writing material " .. e.name .. " failed: " .. tostring(werr)
      end
    end
  end
  result.read_back = stockpile_materials(id, category)
  return result
end

-- ---------------------------------------------------------------------------
-- health (read): per linked workshop, does every input class have a
-- non-empty linked source, is it available fort-wide when it does not, and
-- does its output link accept its products
-- (handoffs/2026-10-07-stockpile-tool-gaps.md item 4; per-kind table in
-- df-overseer-stockpile-kinds.lua). Coordinate-free: ids and landmarks only.
-- A workshop with no links at all is skipped (it draws from anywhere).
-- Fort-wide supply is asked of df-overseer-stocks.lua's get_availability,
-- only for a class that has a problem (that scan is heavy), and only when
-- the table names an items.other key for the class.
-- ---------------------------------------------------------------------------

local function fort_supply(cls)
  if not cls.availability then
    return nil
  end
  local ok_m, m = pcall(reqscript, 'df-overseer-stocks')
  if not ok_m or type(m) ~= "table" or not m.get_availability then
    return nil
  end
  local ok, res = pcall(m.get_availability, cls.availability)
  if not ok or type(res) ~= "table" then
    return nil
  end
  return res.available_units
end

function stockpile_health()
  local out, problem_count = {}, 0
  local occupied_cache = {}
  local function occupied(p)
    if occupied_cache[p.id] == nil then
      occupied_cache[p.id] = occupied_tiles(p) or false
    end
    return occupied_cache[p.id] or 0
  end
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_t, btype = pcall(function() return bld:getType() end)
    if ok_t and is_shop_type(btype) then
      local links = shop_links(bld)
      local in_piles = links and vec_to_list(links.take_from_pile) or {}
      local out_piles = links and vec_to_list(links.give_to_pile) or {}
      if #in_piles > 0 or #out_piles > 0 then
        local kname = workshop_kind_name(bld)
        local _, entry = find_kind(kname)
        local info = landmark_info(bld.x1, bld.x2, bld.y1, bld.y2, bld.z)
        local rec = {
          id = bld.id, kind = kname, kind_known = entry ~= nil,
          kind_source = entry and entry.source or nil,
          unmapped = entry and entry.unmapped or nil,
          near_landmark = info and info.name or nil,
          direction = info and info.direction or nil,
          distance_tiles = info and info.distance_tiles or nil,
          input_mode = (#in_piles > 0) and "linked_piles_only" or "any_source",
          linked_input_piles = pile_ids(in_piles),
          linked_output_piles = pile_ids(out_piles),
          classes = {}, products = {}, problems = {},
        }
        if not entry then
          table.insert(rec.problems, "unknown_kind")
        else
          if #in_piles > 0 then
            for _, cls in ipairs(entry.inputs) do
              local sources, any_accepting, any_nonempty = {}, false, false
              for _, p in ipairs(in_piles) do
                if accepts_any(accepts_set(p), cls.categories) then
                  any_accepting = true
                  local occ = occupied(p)
                  if occ > 0 then
                    any_nonempty = true
                  end
                  table.insert(sources, {pile_id = p.id, occupied_tiles = occ})
                end
              end
              local status
              if any_nonempty then
                status = "ok"
              elseif any_accepting then
                status = "linked_source_empty"
              elseif cls.optional_when or cls.partial then
                status = "not_linked_optional"
              else
                status = "no_linked_source"
              end
              local crec = {id = cls.id, label = cls.label, role = cls.role,
                            status = status, linked_sources = sources}
              if status == "linked_source_empty" or status == "no_linked_source" then
                table.insert(rec.problems, status .. ":" .. cls.id)
                crec.fort_wide_available_units = fort_supply(cls)
              end
              table.insert(rec.classes, crec)
            end
          end
          for _, prod in ipairs(entry.outputs) do
            local accepted_by = {}
            for _, p in ipairs(out_piles) do
              if accepts_any(accepts_set(p), prod.categories) then
                table.insert(accepted_by, p.id)
              end
            end
            local status
            if #out_piles == 0 then
              status = "no_output_link"
            elseif #accepted_by > 0 then
              status = "ok"
            else
              status = "rejected"
              table.insert(rec.problems, "output_rejected:" .. prod.id)
            end
            table.insert(rec.products, {id = prod.id, label = prod.label,
                                        status = status, accepted_by = accepted_by})
          end
        end
        problem_count = problem_count + #rec.problems
        table.insert(out, rec)
      end
    end
  end
  return {workshops = out, problem_count = problem_count,
          table_provenance = "per-kind classes derived from the game's job definitions at runtime "
            .. "(see each workshop's kind_source); hand data only for item-type categories, fuel and "
            .. "built-in job products; unverified live"}
end

-- ---------------------------------------------------------------------------
-- plan-feed (read; a dry-run spec, nothing is built): the piles, classes,
-- sizes, links and containers a workshop kind needs, from the per-kind
-- table. Accepts a kind name or a workshop id; with an id, classes already
-- covered by that workshop's current links are left out of the spec. Each
-- feeder is the research's point-of-use pile: bounded, links-only, no bins,
-- barrels or wheelbarrows, fed from a bulk pile that takes from anywhere.
-- ---------------------------------------------------------------------------

function stockpile_plan_feed(kind_or_id)
  if not kind_or_id or kind_or_id == "" then
    return nil, "usage: WORKSHOP_KIND (e.g. Still) or a workshop building id"
  end
  local shop, kname, entry
  local as_id = tonumber(kind_or_id)
  if as_id then
    local bld, kind, rerr = resolve_pile_or_shop(as_id)
    if not bld then
      return nil, rerr
    end
    if kind ~= "workshop" then
      return nil, "id " .. tostring(kind_or_id) .. " is not a workshop or furnace (" .. kind .. ")"
    end
    shop = bld
    kname = workshop_kind_name(bld)
    local _, e = find_kind(kname)
    entry = e
    if not entry then
      return nil, "no input/output table for workshop kind '" .. tostring(kname) .. "'"
    end
  else
    local k, e = find_kind(kind_or_id)
    if not e then
      local names = known_kind_names()
      return nil, "unknown workshop kind '" .. tostring(kind_or_id) .. "'; known: " .. table.concat(names, ", ")
    end
    kname, entry = k, e
  end

  local covered = {}
  local has_output_link = false
  if shop then
    local links = shop_links(shop)
    local in_piles = links and vec_to_list(links.take_from_pile) or {}
    has_output_link = links and #vec_to_list(links.give_to_pile) > 0 or false
    for _, cls in ipairs(entry.inputs) do
      for _, p in ipairs(in_piles) do
        if accepts_any(accepts_set(p), cls.categories) then
          covered[cls.id] = true
        end
      end
    end
  end

  local piles, plinks, notes = {}, {}, {}
  local sources_seen = {}
  local zero_containers = {max_barrels = 0, max_bins = 0, max_wheelbarrows = 0}
  for _, cls in ipairs(entry.inputs) do
    if not covered[cls.id] then
      local handle = "feeder:" .. cls.id
      local src = "source:" .. cats_text(cls.categories)
      table.insert(piles, {
        handle = handle, purpose = "feeder", for_class = cls.id, label = cls.label,
        role = cls.role, accepts = cls.categories, size_tiles = cls.feeder_tiles,
        links_only = true, containers = zero_containers,
        optional_when = cls.optional_when,
      })
      if not sources_seen[src] then
        sources_seen[src] = true
        table.insert(piles, {
          handle = src, purpose = "source", accepts = cls.categories,
          size_tiles = nil, links_only = false,
          note = "the bulk pile near the producer; reuse an existing any-source pile that "
            .. "accepts these categories if there is one",
        })
      end
      table.insert(plinks, {pile = src, target = handle, direction = "give"})
      table.insert(plinks, {pile = handle, target = "workshop", direction = "give"})
    end
  end
  if not has_output_link then
    local cats, seen = {}, {}
    for _, prod in ipairs(entry.outputs) do
      for _, c in ipairs(prod.categories) do
        if not seen[c] then
          seen[c] = true
          table.insert(cats, c)
        end
      end
    end
    table.insert(piles, {
      handle = "output", purpose = "output", accepts = cats, size_tiles = 4,
      links_only = false,
      note = "must accept every product, or the rejected ones sit in the workshop",
    })
    table.insert(plinks, {pile = "output", target = "workshop", direction = "take"})
  end
  table.insert(notes, "feeders are links-only with no bins, barrels or wheelbarrows so items travel loose")
  table.insert(notes, "the table is hand-authored and unverified live; finer material choices go through stockpile.set-materials")

  local covered_ids = {}
  for id in pairs(covered) do
    table.insert(covered_ids, id)
  end
  table.sort(covered_ids)
  return {
    kind = kname, workshop_id = shop and shop.id or nil, dry_run = true,
    kind_source = entry.source, unmapped = entry.unmapped, derive_error = entry.derive_error,
    already_covered_classes = covered_ids,
    piles = piles, links = plinks, notes = notes,
  }
end

-- ---------------------------------------------------------------------------
-- remove: retire a pile (handoffs/2026-10-07-stockpile-tool-gaps.md item 6).
-- DRY_RUN defaults to true. Stockpiles only. A real run asks DFHack to
-- deconstruct the building (`dfhack.buildings.deconstruct`); whether that
-- removes a stockpile at once, and cleans the link vectors on the other ends,
-- is UNVERIFIED live, so the real run reads the building back and reports
-- whether it is gone. Items in the pile stay where they lie.
-- ---------------------------------------------------------------------------

function stockpile_remove(id, dry_run)
  local bld, kind, rerr = resolve_pile_or_shop(id)
  if not bld then
    return nil, rerr
  end
  if kind ~= "stockpile" then
    return nil, "id " .. tostring(id) .. " is not a stockpile (" .. kind .. ")"
  end
  local dry = truthy_dry_run(dry_run)
  local links = read_links(bld.links)
  local warnings = {}
  local items = nil
  local ok_items, contents = pcall(dfhack.buildings.getStockpileContents, bld)
  if ok_items and contents then
    items = #contents
  end
  if items and items > 0 then
    table.insert(warnings, {code = "pile_not_empty", message = tostring(items)
      .. " items are in the pile; they stay where they lie but are no longer in a pile"})
  end
  -- Workshops this pile feeds: removing it may leave one with no linked
  -- source (it then draws from anywhere) or without a class it needed.
  for _, t in ipairs(links.give_to_workshop.targets) do
    local shop = find_building_by_id(t.id)
    local sl = shop and shop_links(shop)
    local remaining = {}
    if sl then
      for _, p in ipairs(vec_to_list(sl.take_from_pile)) do
        if p.id ~= bld.id then
          table.insert(remaining, p)
        end
      end
    end
    local _, entry = find_kind(shop and workshop_kind_name(shop))
    if #remaining == 0 then
      table.insert(warnings, {code = "workshop_loses_all_feeders", message = "workshop " .. tostring(t.id)
        .. " would have no linked input pile and would draw from anywhere again"})
    elseif entry then
      local missing = uncovered_classes(entry, remaining)
      if #missing > 0 then
        table.insert(warnings, {code = "single_class_trap", message = "workshop " .. tostring(t.id)
          .. " would be left with no linked pile accepting: "
          .. table.concat(class_labels(missing), ", ")})
      end
    end
  end
  local result = {
    id = tonumber(id), dry_run = dry, items_in_pile = items,
    links_dropped = {
      give_to_pile = links.give_to_pile.count, take_from_pile = links.take_from_pile.count,
      give_to_workshop = links.give_to_workshop.count, take_from_workshop = links.take_from_workshop.count,
    },
    warnings = warnings,
  }
  if dry then
    return result
  end
  -- REAL PATH. UNTESTED live.
  local ok_d, derr = pcall(dfhack.buildings.deconstruct, bld)
  if not ok_d then
    return nil, "deconstruct failed: " .. tostring(derr)
  end
  result.read_back = {still_present = find_building_by_id(tonumber(id)) ~= nil}
  return result
end


-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

-- LEVEL is optional in `place` the same way every other df-overseer-*.lua
-- finder handles it: args[4] is read as LEVEL only when it parses as a
-- number, otherwise it's NEAR_LANDMARK and every argument after it shifts
-- left by one.
local USAGE = {
  "usage: df-overseer-stockpile list",
  "usage: df-overseer-stockpile links ID",
  "usage: df-overseer-stockpile place W H [LEVEL] NEAR_LANDMARK CATEGORIES [RANK] [RADIUS_TILES] [DRY_RUN] [RES_ID] [OVERRIDE]",
  "usage: df-overseer-stockpile configure ID CATEGORIES [DRY_RUN]",
  "usage: df-overseer-stockpile link ID TARGET_ID give|take [DRY_RUN]",
  "usage: df-overseer-stockpile unlink ID TARGET_ID give|take [DRY_RUN]",
  "usage: df-overseer-stockpile settings ID [LINKS_ONLY] [MAX_BINS] [MAX_BARRELS] [MAX_WHEELBARROWS] [DRY_RUN]",
  "usage: df-overseer-stockpile materials ID CATEGORY",
  "usage: df-overseer-stockpile set-materials ID CATEGORY MATERIALS [DRY_RUN]",
  "usage: df-overseer-stockpile health",
  "usage: df-overseer-stockpile plan-feed WORKSHOP_KIND|ID",
  "usage: df-overseer-stockpile remove ID [DRY_RUN]",
}
local function print_usage()
  for _, line in ipairs(USAGE) do
    print(line)
  end
end

if cmd == "list" then
  print(json.encode(list_stockpiles()))
elseif cmd == "links" then
  local id = args[2]
  if not id then
    print_usage()
  else
    local result, err = stockpile_links(id)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "place" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, categories, rank, radius, dry_run, res_id, override
  if tonumber(args[4]) then
    level, near, categories, rank, radius, dry_run, res_id, override =
      tonumber(args[4]), args[5], args[6], tonumber(args[7]), tonumber(args[8]), args[9], args[10], args[11]
  else
    near, categories, rank, radius, dry_run, res_id, override =
      args[4], args[5], tonumber(args[6]), tonumber(args[7]), args[8], args[9], args[10]
  end
  if not (w and h and near and categories) then
    print_usage()
  else
    local result, err = place_stockpile(w, h, level, near, categories, rank, radius, dry_run, res_id, override)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "configure" then
  local id, categories, dry_run = args[2], args[3], args[4]
  if not (id and categories) then
    print_usage()
  else
    local result, err = stockpile_configure(id, categories, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "link" then
  local id, target_id, direction, dry_run = args[2], args[3], args[4], args[5]
  if not (id and target_id and direction) then
    print_usage()
  else
    local result, err = stockpile_link(id, target_id, direction, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "unlink" then
  local id, target_id, direction, dry_run = args[2], args[3], args[4], args[5]
  if not (id and target_id and direction) then
    print_usage()
  else
    local result, err = stockpile_unlink(id, target_id, direction, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "settings" then
  if not args[2] then
    print_usage()
  else
    local result, err = stockpile_settings(args[2], args[3], args[4], args[5], args[6], args[7])
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "materials" then
  if not (args[2] and args[3]) then
    print_usage()
  else
    local result, err = stockpile_materials(args[2], args[3])
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "set-materials" then
  if not (args[2] and args[3] and args[4]) then
    print_usage()
  else
    local result, err = stockpile_set_materials(args[2], args[3], args[4], args[5])
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "health" then
  print(json.encode(stockpile_health()))
elseif cmd == "plan-feed" then
  if not args[2] then
    print_usage()
  else
    local result, err = stockpile_plan_feed(args[2])
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "remove" then
  if not args[2] then
    print_usage()
  else
    local result, err = stockpile_remove(args[2], args[3])
    print(json.encode(err and {error = err} or result))
  end
else
  print_usage()
end
