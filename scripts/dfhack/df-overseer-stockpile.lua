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

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local openarea_mod = reqscript('df-overseer-openarea')
local reservations_mod = reqscript('df-overseer-reservations')

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
  elseif btype == df.building_type.Workshop then
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
    return {id = tonumber(id), kind = kind, links = read_links(found.links)}
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
else
  print_usage()
end
