-- df-overseer-diggable.lua
--@module = true
--
-- Closes the gap found live 2026-09-11 (research/2026-08-25-spatial-
-- perception.md's "Gap found live 2026-09-11" note, added to the spec on
-- `main` at 0a47c56/f48a641/89a04d2 -- NOT yet merged into this branch's
-- checkout of that file, read directly from those commits instead):
-- `find_open_area` (df-overseer-openarea.lua) only ever searches *walkable*
-- tiles -- confirmed live the hard way, running a `#dig` blueprint at a
-- find_open_area candidate designated zero tiles, because the candidate was
-- already-open floor. Nothing in the spec found a candidate region of
-- *solid, diggable* rock/soil. This is that primitive: the inverse of
-- find_open_area's is_free scan -- non-walkable, WALL-shaped, natural
-- (non-construction) material tiles instead of walkable ones -- otherwise
-- the same scoped maximal-rectangle-scan shape as find_open_area's
-- terrain="built" case (same MAX_RADIUS cap, same near-landmark anchoring,
-- same design commitment #1: real coordinates never leave this file).
--
-- Diggability check: a tile counts as diggable if (a) it is NOT walkable
-- (dfhack.maps.getWalkableGroup == 0 -- if it's already walkable it's not
-- solid, that's find_open_area's job) and (b) its tiletype shape is WALL
-- and (c) its tiletype material is one mining actually excavates: STONE,
-- SOIL, FEATURE (mineral/gem veins embedded in stone), MINERAL, LAVA_STONE,
-- or FROZEN_LIQUID (glacier ice). CONSTRUCTION (a built wall) is
-- deliberately excluded -- removing a construction is a different DFHack
-- job (`dig` vs `remove construction`), not what this primitive is for.
--
-- Reachability constraint (research spec, 0a47c56, corrected in 89a04d2):
-- a dig job needs a dwarf standing on an adjacent WALKABLE tile to mine
-- from -- the exact boundary-connectivity lesson this project already paid
-- for once (2026-09-10: a floor dig beneath a completed stair never became
-- a job because the connecting tile wasn't itself a matching stair type).
-- v1 scope, per the spec's own corrected call: only return candidates that
-- directly border the existing walkable network (same getWalkableGroup as
-- the search anchor, checked on the ring of tiles immediately surrounding
-- the WxH box). This is a reasonable, simple first cut, NOT a claim that
-- non-adjacent candidates are invalid -- a fuller version would instead
-- score non-adjacent candidates by connector-tunnel cost (the
-- entrance+connector+room pattern this project already uses) and let the
-- model choose to pay it, matching rank_candidate_sites' frontier/cost-and-
-- gain term. Not attempted here; v1 filters them out and says so in the
-- doc comment, not silently.
--
-- `dig` subcommand (added 2026-09-11, same session as find_diggable_area
-- itself, after find_diggable_area was live-verified against VM 103):
-- closes the loop the same way `build_open_area` did for `find_open_area`
-- (`decisions/DECISIONS.md` 2026-09-11, "Closed the coordinate-resolution
-- gap..."). `dig_diggable_area` is the fused resolve-and-act primitive --
-- NOT the research spec's original `designate_dig(shape, pos, dims)`
-- sketch (§5.2), which assumed some upstream tool would hand it a raw
-- `pos` and never specified one. Matching `build_open_area`'s exact shape
-- instead: takes a `blueprint_file` (a `#dig` quickfort blueprint, e.g.
-- `starter-room-5x5.csv`) rather than a `shape` enum, re-runs this file's
-- own `ranked_candidates`, resolves the chosen candidate's real cx,cy
-- internally, and calls `quickfort run BLUEPRINT_FILE -c cx,cy,z` directly
-- -- the coordinate exists only inside this function's local scope, for
-- the instant it takes to build quickfort's argument list, never returned
-- or printed. `parse_quickfort_stats` is intentionally duplicated from
-- `df-overseer-openarea.lua` rather than shared, to avoid touching that
-- file's own uncommitted in-flight changes (`build`/`build_open_area`,
-- Working.md 2026-09-11) for a few identical lines.
--
-- Real mutation, not a query: unlike `find_diggable_area`, calling `dig`
-- creates a genuine dig designation dwarves will act on -- treat a live
-- call the same as any other fort-mutating action this project already
-- gates (quicksave discipline, a peer/user heads-up), not like the
-- read-only `find` subcommand.
--
-- Enum names verified against the actual installed DFHack 53.16-r1.1
-- (`memory/dfhack-environment.md`), not recalled from memory or web
-- results, per this project's "mark verified vs proposed" rule: WALL
-- (`df.tiletype_shape`) and STONE/SOIL/FEATURE/MINERAL/LAVA_STONE/
-- FROZEN_LIQUID (`df.tiletype_material`) all appear exactly this way in
-- the local install's own `hack/lua/tile-material.lua` (its `BasicMats`
-- table) and `hack/docs/docs/tools/tiletypes.txt`.
--
-- `find_diggable_area` itself IS live-verified against VM 103/Uniboslan
-- (`decisions/DECISIONS.md` 2026-09-11, "live-verified against VM 103,
-- both a correct negative and a correct positive"): a correct empty
-- result near the surface Embark Site (nearby WALL-shaped tiles were all
-- TREE material, correctly excluded) and a correct set of 5 ranked SOIL
-- candidates underground near Stockpile #1. `dig_diggable_area`/`dig`
-- (below) is NOT yet live-tested -- unlike `find`, it's a real fort
-- mutation, so a live call needs the same explicit go-ahead as any other
-- mutating action this project gates, not just a peer heads-up.
--
-- Z defaulted to NEAR_LANDMARK's own z (same fix, same day, as
-- df-overseer-openarea.lua -- see that file's header for the full story):
-- ranked_candidates already resolves the landmark's real az internally and
-- was discarding it in favor of this argument, with no coordinate-free way
-- for a caller to learn the right value otherwise.
--
-- Z REPLACED WITH LEVEL, an offset relative to NEAR_LANDMARK's own z, not an
-- absolute DF coordinate (gap found live 2026-09-14, handoffs/2026-09-14-
-- relative-level-args.md -- see df-overseer-openarea.lua's header for the
-- full story, this file's identical bug and fix): the live probe that found
-- this gap was against THIS tool specifically -- find_diggable_area called
-- with z=0/-1/-2/-3/-4 (Uniboslan's map runs z 0-185, landmarks sit at
-- z 168-169, so every one of those was nowhere near the fort) returned `[]`
-- every time, an empty list rather than an error, and the caller concluded
-- there was nothing diggable underground. LEVEL=0 (the default, unchanged
-- behavior for every caller that omits it) means the landmark's own level;
-- -1 means one level below; 1 means one above. `resolve_level` adds
-- az + LEVEL and validates against the real map bounds
-- (dfhack.maps.getSize()'s z_count_block) -- a level outside the map is now
-- a returned error naming LEVEL and the landmark, never the resolved
-- absolute z (design commitment #1), instead of a silent empty result.
-- Called correctly (landmark z minus 1) this tool returns 5 real candidates
-- near Embark Site/Stockpile #2/Wagon; at landmark z minus 2 and below it
-- correctly returns 0 (no tile there is walkable yet, so v1's "must border
-- the walkable network" filter rejects everything, by design -- see the
-- header above, not a bug this change touches).
--
-- KNOWLEDGE-SCOPE FIX, 2026-09-16 (handoffs/2026-09-16-knowledge-scope-audit.md,
-- following decisions/DECISIONS.md 2026-09-16 "Agents may only know what a
-- vanilla player could know" and research/2026-09-16-player-visibility.md):
-- this tool was OMNISCIENT before this fix. `is_diggable` never checked
-- `designation.hidden`/`dfhack.maps.isTileVisible`, so a WxH candidate box
-- could sit entirely in undug rock a vanilla player has never seen so much
-- as a neighboring wall of, and `material` was read straight off the tile
-- regardless -- exactly the "name an undiscovered vein's material before
-- it's ever revealed" gap the research doc's bottom line calls out. Fixed
-- (that day) by requiring `dfhack.maps.isTileVisible` on EVERY tile in the
-- box, hidden or not. That over-corrected -- see the ACT/SENSE FIX below,
-- which replaces it.
--
-- ACT/SENSE FIX, 2026-09-16 (handoffs/2026-09-16-farm-and-still-tools.md):
-- the knowledge-scope fix above conflated ACTING on a tile with KNOWING
-- about it. A vanilla player designates a dig into unrevealed ground
-- constantly -- that is how every underground room in this game is ever
-- built -- they just cannot see what is inside it first. Requiring
-- `isTileVisible` on the whole box made `find_diggable_area` unable to
-- propose ANY candidate with so much as one hidden tile in it, which is
-- nearly every candidate near a young fort's small revealed footprint:
-- measured live on Uniboslan, `find 5 5 [0|-1|-2|-3] NEAR_LANDMARK` against
-- Embark Site and Stockpile #1 returned `[]` at every level with the
-- over-corrected code (baseline, this session). Confirmed from DFHack's own
-- source, not just inferred: `hack/scripts/internal/quickfort/dig.lua`'s
-- own header comment states the real rule verbatim -- "if the tile is
-- hidden, we designate blindly to avoid spoilers. If it's visible, the
-- shape and material of the target tile affects whether the designation
-- has any effect." Its per-designation functions (`do_mine`, `do_down_stair`,
-- etc.) literally skip their own shape/material gate `if not
-- digctx.flags.hidden` -- a hidden tile is designated unconditionally, no
-- properties read at all.
--
-- `is_diggable` now returns a third value, `hidden`, and treats the two
-- cases asymmetrically, matching that source exactly:
--   - HIDDEN tile: admitted UNCONDITIONALLY. Nothing about it -- material,
--     shape, whether it's even solid -- is read or used to choose, rank or
--     describe the candidate (the user's own framing, register 2026-09-16:
--     "not allowed: using any property of a hidden tile to choose, rank,
--     filter or describe a candidate: its material, its shape... its
--     contents"). If it turns out to already be open floor, the real dig
--     job will simply no-op that tile when it actually runs, same as a
--     vanilla player's own blind designation over already-open ground would
--     -- admitting it here costs nothing.
--   - REVEALED tile: unchanged from the original (pre-knowledge-scope-fix)
--     checks -- not walkable, WALL-shaped, natural diggable material. This
--     data IS player-known once uncovered, so reading it is not a
--     knowledge-scope violation; it never was.
-- `material` is nil for a hidden tile in both the per-tile check and the
-- final result (still reported only from the candidate's own top-left
-- tile, informational-only, per the existing comment on that field) --
-- never omitted-then-guessed, never backfilled from a neighbor.
--
-- Each candidate also reports `interior_fully_revealed` (true only if NO
-- tile in the box is hidden) -- an aggregate boolean derived from something
-- a vanilla player looking at their own map screen can already tell (an
-- area with dark unrevealed patches vs. one fully lit), not a per-tile
-- material/shape leak, so it stays inside player_derivable scope.
--
-- `borders_walkable_network` (the anchoring/reachability ring check) also
-- gained a `dfhack.maps.isTileVisible` requirement on the ring tile itself:
-- the register's own wording ("a candidate must be reachable from the
-- revealed walkable network") means anchoring must still come from ground
-- the player has actually seen, even though the candidate's OWN interior
-- may now include hidden tiles. Unaffected by this fort's real geometry
-- today (see below): every ring tile that already matched was revealed
-- anyway, since walkable ground is not the same test as revealed ground
-- but happens to coincide here.
--
-- MEASURED LIVE, this session, Uniboslan (paused, read-only): baseline
-- (over-corrected code) returned `[]` for `find 5 5 LEVEL NEAR_LANDMARK`
-- at LEVEL 0/-1/-2/-3 near both "Embark Site" and "Stockpile #1". After
-- this fix, `find 5 5 -1 "Embark Site"` returns real candidates bordering
-- the existing walkable network at z168 (one level below the surface) --
-- see the handoff's own report for the exact count. This is the same
-- z168 "farm room" case CLAUDE.md's 2026-09-16 status line names.
--
-- THE GRASS-TILE QUESTION (`docs/TRAPS.md`: "a downstair can't be
-- designated on a grass tile"), investigated by source and one live
-- read-only probe, NOT by designating anything (mutation is forbidden this
-- session):
--   - `hack/scripts/internal/quickfort/dig.lua`'s `do_down_stair` (the `j`
--     dig-mode symbol) admits a revealed tile if it is a WALL, a
--     FORTIFICATION, `is_diggable_floor` (shape FLOOR/BOULDER/PEBBLES --
--     material is NOT checked here), a removable shape, gatherable, or a
--     sapling; it only refuses outright on `is_tree`. A live read confirmed
--     this fort's own grass tiles carry shape FLOOR with material
--     GRASS_LIGHT/GRASS_DARK -- i.e. by this function's own logic, a grass
--     tile's SHAPE should satisfy `is_diggable_floor` the same as any other
--     floor. **This repo's source reading did not find the mechanism the
--     recorded trap describes** -- it may live below quickfort's Lua layer
--     (an engine-level job-creation check quickfort's own designation call
--     cannot see), or the original one-off observation may have had an
--     uncontrolled second factor. Left unresolved rather than guessed at;
--     re-verifying it would require an actual designation, which this
--     session cannot run.
--   - What IS confirmed live: this fort's own existing entrance/connector
--     stair pair (`blueprints/starter-entrance-1x1.csv`/
--     `starter-connector-1x1.csv`, built and applied by an earlier session)
--     sits on a bare STONE surface tile, not grass or soil, and is a real,
--     working STAIR_DOWN/STAIR_UP pair today, part of the SAME walkable
--     group as the surface landmarks above it -- confirmed via
--     `getWalkableGroup` returning the identical group id at the surface
--     (near "Embark Site") and one level down (near "Stockpile #2").
--   - Practical consequence for this fix: because that connector already
--     exists and is already part of the walkable network `ranked_candidates`
--     anchors to, `find_diggable_area`'s existing ring-adjacency check
--     (`borders_walkable_network`, unchanged in shape by this fix) already
--     reaches z168 through it with NO new stair-authoring code needed --
--     confirmed by the live LEVEL=-1 result above. Authoring a NEW vertical
--     connector where none yet exists remains v1's own documented non-goal
--     (see this file's original header, "non-adjacent candidates are simply
--     absent rather than ranked low... not attempted here") and is
--     unchanged by this stream. A future stream that needs a genuinely new
--     surface entry point should prefer a non-grass/non-soil surface tile,
--     matching this fort's own working precedent, until the grass question
--     above is actually settled by a live designation test.
--
-- STAIR-DOWN CANDIDATE KIND, 2026-09-17 (handoffs/2026-09-17-dig-down-to-
-- stone.md): the gap named in that handoff's "Why" section -- `find W H
-- LEVEL NEAR_LANDMARK` above can never return a candidate at a level with
-- no walkable tile yet (v1's own `borders_walkable_network` scope limit,
-- see this file's original header), which is exactly Uniboslan's situation
-- at z167 (stone) under z168 (the walkable farm room): nothing there can
-- ever border a network that does not exist yet at that z. That is not a
-- bug in the box-scan primitive; a box scan is the wrong shape for "the one
-- tile where a NEW vertical connector should go." This adds a second,
-- narrower candidate kind to the SAME file (per the handoff's own
-- preference for extending diggable.find/dig over a new tool id) instead
-- of a box: `find-stair`/`dig-stair` look for a single WALKABLE column at
-- the landmark's own level (LEVEL, default 0, same convention as `find`
-- above) whose tile directly one level below is diggable -- i.e. a valid
-- anchor for the same downstair/upstair pair this fort's own original
-- entrance+connector already used (blueprints/starter-entrance-1x1.csv,
-- blueprints/starter-connector-1x1.csv -- both fixed 1x1 #dig blueprints
-- already in this repo, reused as-is rather than invented new; a stair
-- connector is always exactly this one pair, so there is nothing for a
-- caller to usefully choose in a BLUEPRINT_FILE argument the way
-- dig_diggable_area's room shape needs one).
--
-- Boundary-connectivity lesson (2026-09-10, restated in this file's
-- original header) applies here by construction, not by a caller's care:
-- `dig_stair_down` always designates BOTH the downstair (upper level) and
-- the matching upstair (lower level, same x,y) in one call, exactly the
-- pair that lesson says must both exist for a job to ever form -- there is
-- no way to call this tool and get only one half of the pair.
--
-- "Plus room to dig from there" (the handoff's Goal): deliberately NOT this
-- kind's job. Once `dig-stair` designates the pair and a dwarf carves it,
-- the upstair tile itself becomes walkable, which is exactly the missing
-- ingredient `find`/`dig` above need to succeed at the lower level on a
-- later call -- the existing box-scan primitive already does "room to dig"
-- once this kind has extended the network down to it. Chaining two
-- existing-shaped primitives instead of building one primitive that does
-- both keeps this addition narrow and reuses code that is already
-- live-verified.
--
-- THE GRASS-TILE QUESTION (see this file's original header): left
-- unresolved there by source reading, not settled either way. This kind
-- does NOT filter or exclude a walkable upper-level candidate by its
-- surface material (grass or otherwise) -- source reading found no
-- confirming mechanism for the recorded trap, so silently excluding grass
-- tiles here would be guessing in the opposite, equally unverified,
-- direction. Instead each candidate reports its own upper-level tile
-- material (`upper_tile_material`), a player-visible fact (the tile is
-- walkable, hence revealed), so a caller can choose to avoid grass until
-- the question is actually settled by a live designation test, without
-- this tool asserting either answer for them.
--
-- Usage: ./dfhack-run df-overseer-diggable find W H [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-diggable dig W H [LEVEL] NEAR_LANDMARK BLUEPRINT_FILE [RANK] [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-diggable find-stair [LEVEL] NEAR_LANDMARK [RADIUS_TILES]
-- Usage: ./dfhack-run df-overseer-diggable dig-stair [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30
local MAX_RESULTS = 5

local DIGGABLE_MATERIALS = {
  [df.tiletype_material.STONE] = true,
  [df.tiletype_material.SOIL] = true,
  [df.tiletype_material.FEATURE] = true,
  [df.tiletype_material.MINERAL] = true,
  [df.tiletype_material.LAVA_STONE] = true,
  [df.tiletype_material.FROZEN_LIQUID] = true,
}

-- Fixed 1x1 #dig blueprints for find-stair/dig-stair below -- this fort's
-- own original entrance/connector pair, already in blueprints/ and already
-- the live-working precedent for a stair connector (see the STAIR-DOWN
-- CANDIDATE KIND header comment above). Not a caller-supplied
-- BLUEPRINT_FILE argument: a stair connector is always exactly this one
-- pair.
local DOWNSTAIR_BLUEPRINT = "starter-entrance-1x1.csv"
local UPSTAIR_BLUEPRINT = "starter-connector-1x1.csv"

local function walkable_group(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group or 0
end

-- Returns (admit: bool, material: df.tiletype_material or nil, hidden: bool).
-- ACT/SENSE FIX, 2026-09-16 -- see header. A hidden tile is admitted
-- unconditionally, with no material/shape/walkable read used to decide
-- that: matching a vanilla player's own ability to designate a dig into
-- ground they've never revealed. A revealed tile keeps the original
-- checks (solid, WALL-shaped, natural diggable material) unchanged.
local function is_diggable(x, y, z)
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    return false, nil, false
  end
  if not visible then
    return true, nil, true
  end
  if walkable_group(x, y, z) ~= 0 then
    return false, nil, false
  end
  local ok_tt, tt = pcall(dfhack.maps.getTileType, x, y, z)
  if not ok_tt or not tt or tt < 0 then
    return false, nil, false
  end
  local ok_shape, shape = pcall(function() return df.tiletype.attrs[tt].shape end)
  if not ok_shape or shape ~= df.tiletype_shape.WALL then
    return false, nil, false
  end
  local ok_mat, mat = pcall(function() return df.tiletype.attrs[tt].material end)
  if not ok_mat or not DIGGABLE_MATERIALS[mat] then
    return false, nil, false
  end
  return true, mat, false
end

-- Every top-left position where a w-by-h window is entirely diggable tiles,
-- within the given box at the given z. Mirrors find_candidates in
-- df-overseer-openarea.lua exactly, with is_diggable in place of is_free.
local function find_candidates(w, h, z, min_x, max_x, min_y, max_y)
  local diggable, material, hidden = {}, {}, {}
  for x = min_x, max_x do
    diggable[x] = {}
    material[x] = {}
    hidden[x] = {}
    for y = min_y, max_y do
      local ok, mat, hid = is_diggable(x, y, z)
      diggable[x][y] = ok
      material[x][y] = mat
      hidden[x][y] = hid
    end
  end

  local candidates = {}
  for x = min_x, max_x - w + 1 do
    for y = min_y, max_y - h + 1 do
      local fits = true
      local any_hidden = false
      for dx = 0, w - 1 do
        if not fits then break end
        for dy = 0, h - 1 do
          if not diggable[x + dx][y + dy] then
            fits = false
            break
          end
          if hidden[x + dx][y + dy] then
            any_hidden = true
          end
        end
      end
      if fits then
        table.insert(candidates, {
          x = x, y = y,
          material = material[x][y],
          any_hidden = any_hidden,
        })
      end
    end
  end
  return candidates
end

-- Two candidate windows (both w-by-h, top-left at a.x,a.y / b.x,b.y).
local function overlaps(a, b, w, h)
  return a.x < b.x + w and b.x < a.x + w and a.y < b.y + h and b.y < a.y + h
end

-- True if any tile on the ring immediately surrounding the w-by-h box at
-- x,y (8-connected: cardinal and diagonal neighbors) is walkable and, when
-- required_group is given, shares that walkable group. required_group is
-- nil when the anchor landmark itself isn't on a resolvable walkable group
-- (rare -- falls back to "any walkable neighbor counts" rather than
-- rejecting every candidate over an anchor-side lookup failure).
-- ACT/SENSE FIX, 2026-09-16 -- see header: anchoring must still come from
-- REVEALED ground, even though a candidate's own interior may now include
-- hidden tiles. A ring tile is only a valid anchor if isTileVisible is
-- also true.
local function borders_walkable_network(x, y, w, h, z, required_group)
  for rx = x - 1, x + w do
    for ry = y - 1, y + h do
      local on_ring = rx < x or rx >= x + w or ry < y or ry >= y + h
      if on_ring then
        local ok_vis, visible = pcall(dfhack.maps.isTileVisible, rx, ry, z)
        if ok_vis and visible then
          local group = walkable_group(rx, ry, z)
          if group ~= 0 and (not required_group or group == required_group) then
            return true
          end
        end
      end
    end
  end
  return false
end

-- LEVEL is an offset relative to a landmark's own level (0/nil = same level,
-- negative = below, positive = above), never an absolute DF z-coordinate --
-- see the file header for why. Returns the resolved absolute z, or nil plus
-- an error naming LEVEL and landmark_name (never the resolved absolute
-- value, per design commitment #1) if that level doesn't exist on this map.
-- Duplicated identically in df-overseer-openarea.lua and
-- df-overseer-chokepoints.lua -- see this file's own parse_quickfort_stats
-- comment for why duplication over reqscript here.
local function resolve_level(az, level, landmark_name)
  level = level or 0
  local z = az + level
  local _, _, z_count = dfhack.maps.getSize()
  if z < 0 or z >= z_count then
    return nil, string.format("level %d from %s is outside the map", level, landmark_name)
  end
  return z
end

-- Server-side only: ranked, deduplicated, non-overlapping, network-adjacent
-- top-left corners (real x,y coordinates, never stripped here) for a
-- WxH diggable region near `near`, closest-to-anchor first.
local function ranked_candidates(w, h, level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local anchor_group = walkable_group(ax, ay, az)
  if anchor_group == 0 then
    anchor_group = nil
  end

  local candidates = find_candidates(
    w, h, z, ax - radius, ax + radius, ay - radius, ay + radius)

  local adjacent = {}
  for _, c in ipairs(candidates) do
    if borders_walkable_network(c.x, c.y, w, h, z, anchor_group) then
      table.insert(adjacent, c)
    end
  end

  for _, c in ipairs(adjacent) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(adjacent, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  -- Greedily keep only non-overlapping candidates, closest-to-anchor
  -- first, same dedup as find_open_area.
  local chosen = {}
  for _, c in ipairs(adjacent) do
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

function find_diggable_area(w, h, level, near, radius_tiles)
  local chosen, err, resolved_z = ranked_candidates(w, h, level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z

  local results = {}
  for _, c in ipairs(chosen) do
    local cx = c.x + math.floor((w - 1) / 2)
    local cy = c.y + math.floor((h - 1) / 2)
    local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
    local info = ok_near and near_info
    local ok_mat_name, mat_name = pcall(function()
      return c.material and df.tiletype_material[c.material] or nil
    end)
    table.insert(results, {
      dims = {w, h},
      near_landmark = info and info.name or nil,
      direction = info and info.direction or nil,
      distance_tiles = info and info.distance_tiles or nil,
      -- Reported from this candidate's own top-left tile, not surveyed
      -- across the whole box -- informational only, a mixed-material
      -- region (e.g. stone shading into a mineral vein) is common and not
      -- itself disqualifying.
      material = ok_mat_name and mat_name or nil,
      interior_fully_revealed = not c.any_hidden,
      borders_walkable_network = true,  -- v1 only returns these; see header
    })
  end
  return results
end

-- Parses quickfort's own "Blueprint statistics:" block into a plain
-- label->count table. Line-anchored the same deliberate way as
-- df-overseer-openarea.lua's identical helper (see that file's comment for
-- the full rationale): "two leading spaces, label, colon, digits, nothing
-- else" can never match a coordinate-bearing line like dig.lua's own
-- "removing existing job at X, Y, Z", so no raw position can leak through
-- even if some other quickfort mode's stdout format changes later.
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

-- See the header comment above for the full design rationale. Picks
-- candidate `rank` (default 1) from the exact same ranking find_diggable_area
-- uses, resolves its real center coordinate, and runs
-- `quickfort run BLUEPRINT_FILE -c cx,cy,z` directly against it. The real
-- coordinate lives only in this function's own local scope -- never
-- assigned into, printed, or returned in anything handed back to the
-- caller. `blueprint_file` resolves relative to dfhack-config/blueprints/
-- on the guest (quickfort's own resolution rule, not this repo's tree) --
-- pass a bare filename already deployed there, e.g. `starter-room-5x5.csv`.
function dig_diggable_area(w, h, level, near, blueprint_file, rank, radius_tiles)
  rank = rank or 1
  local chosen, err, resolved_z = ranked_candidates(w, h, level, near, radius_tiles)
  if err then
    return nil, err
  end
  local z = resolved_z
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end

  local c = chosen[rank]
  local cx = c.x + math.floor((w - 1) / 2)
  local cy = c.y + math.floor((h - 1) / 2)

  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, cx, cy, z)
  local info = ok_near and near_info
  local ok_mat_name, mat_name = pcall(function()
    return c.material and df.tiletype_material[c.material] or nil
  end)

  -- The one place a real coordinate exists in this file: assembled
  -- directly into quickfort's own argument list, never stored anywhere
  -- else and never returned.
  --
  -- BUG FOUND LIVE 2026-09-11, FIXED HERE: this used to pass cx,cy (the
  -- box's computed CENTER) as quickfort's -c argument. quickfort's own docs
  -- (hack/docs/docs/tools/quickfort.txt: "the blueprint start position...
  -- is the upper left corner by default") say -c anchors the blueprint's
  -- TOP-LEFT, not its center -- so the actual dig landed shifted by
  -- (floor((w-1)/2), floor((h-1)/2)) tiles from the box ranked_candidates
  -- and borders_walkable_network had actually validated, silently placing
  -- it somewhere the adjacency check never checked. Confirmed live: a real
  -- dig call designated a real 5x5 region with ZERO walkable neighbors on
  -- its border (no dwarf ever claimed the job after ~14 in-game days
  -- unpaused), while a direct re-scan of the box the algorithm actually
  -- validated (c.x,c.y, before the center offset) showed real walkable
  -- neighbors on its ring. `c.x,c.y` (the true, validated top-left) is the
  -- correct argument here; cx,cy stays real and correct for
  -- nearest_landmark's direction/distance reporting below, where "center"
  -- is the right choice -- only the quickfort call was wrong.
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', blueprint_file, '-c',
    string.format('%d,%d,%d', c.x, c.y, z))

  return {
    rank = rank,
    dims = {w, h},
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    material = ok_mat_name and mat_name or nil,
    interior_fully_revealed = not c.any_hidden,
    blueprint = blueprint_file,
    quickfort_ok = ok_run and result == CR_OK,
    quickfort_error = (not ok_run) and tostring(output) or nil,
    quickfort_stats = ok_run and parse_quickfort_stats(output) or nil,
  }
end

-- Ranked, single-tile stair-anchor candidates near `near`: a WALKABLE
-- column on the network at LEVEL (default 0, same landmark-relative
-- convention as `find`/`dig` above) whose tile directly one level below is
-- diggable. Each candidate is where a downstair (upper) + upstair (lower)
-- pair could be designated to extend the walkable network down one level.
-- Unlike ranked_candidates above, this returns single points, not WxH
-- rectangles -- a stair connector is inherently a column, not an area --
-- so there is no overlap-dedup pass (distinct points cannot overlap).
-- Server-side only: real x,y coordinates never leave this function.
local function ranked_stair_candidates(level, near, radius_tiles)
  local ax, ay, az = landmarks_mod.get_landmark_centroid(near)
  if not ax then
    return nil, "landmark not found: " .. near
  end
  local upper_z, level_err = resolve_level(az, level, near)
  if level_err then
    return nil, level_err
  end
  local lower_z = upper_z - 1
  if lower_z < 0 then
    return nil, string.format(
      "no level below level %d from %s to place an upstair", level or 0, near)
  end
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)

  local anchor_group = walkable_group(ax, ay, upper_z)
  if anchor_group == 0 then
    anchor_group = nil
  end

  local candidates = {}
  for x = ax - radius, ax + radius do
    for y = ay - radius, ay + radius do
      local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, upper_z)
      if ok_vis and visible then
        local group = walkable_group(x, y, upper_z)
        if group ~= 0 and (not anchor_group or group == anchor_group) then
          local admit, lower_mat, lower_hidden = is_diggable(x, y, lower_z)
          if admit then
            local ok_ut, upper_tt = pcall(dfhack.maps.getTileType, x, y, upper_z)
            local upper_mat
            if ok_ut and upper_tt and upper_tt >= 0 then
              local ok_um, um = pcall(function() return df.tiletype.attrs[upper_tt].material end)
              upper_mat = ok_um and um or nil
            end
            table.insert(candidates, {
              x = x, y = y,
              lower_material = lower_mat,
              lower_hidden = lower_hidden,
              upper_material = upper_mat,
            })
          end
        end
      end
    end
  end

  for _, c in ipairs(candidates) do
    local dx, dy = c.x - ax, c.y - ay
    c.dist_to_anchor = math.sqrt(dx * dx + dy * dy)
  end
  table.sort(candidates, function(a, b) return a.dist_to_anchor < b.dist_to_anchor end)

  local chosen = {}
  for _, c in ipairs(candidates) do
    table.insert(chosen, c)
    if #chosen >= MAX_RESULTS then
      break
    end
  end
  return chosen, nil, upper_z, lower_z
end

-- Builds one candidate's reported fields (near_landmark/direction/distance
-- from its own point, plus both tiles' informational material/hidden
-- state) -- shared between find_stair_down and dig_stair_down so the two
-- can never report the ranking differently.
local function describe_stair_candidate(c, upper_z)
  local ok_near, near_info = pcall(landmarks_mod.nearest_landmark, c.x, c.y, upper_z)
  local info = ok_near and near_info
  local ok_um, um_name = pcall(function()
    return c.upper_material and df.tiletype_material[c.upper_material] or nil
  end)
  local ok_lm, lm_name = pcall(function()
    return c.lower_material and df.tiletype_material[c.lower_material] or nil
  end)
  return {
    near_landmark = info and info.name or nil,
    direction = info and info.direction or nil,
    distance_tiles = info and info.distance_tiles or nil,
    -- Informational only, per the STAIR-DOWN CANDIDATE KIND header comment
    -- above (the grass-tile question): never used here to filter or rank.
    upper_tile_material = ok_um and um_name or nil,
    lower_tile_material = ok_lm and lm_name or nil,
    lower_tile_hidden = c.lower_hidden,
    borders_walkable_network = true,  -- selection requires it; see above
  }
end

function find_stair_down(level, near, radius_tiles)
  local chosen, err, upper_z = ranked_stair_candidates(level, near, radius_tiles)
  if err then
    return nil, err
  end
  local results = {}
  for _, c in ipairs(chosen) do
    table.insert(results, describe_stair_candidate(c, upper_z))
  end
  return results
end

-- Designates BOTH halves of one stair pair in a single call: a downstair
-- at the candidate's own (walkable) level, and the matching upstair
-- directly beneath it. Never one without the other -- see the
-- boundary-connectivity note in the header comment above. Real coordinates
-- exist only in this function's own local scope, same discipline as
-- dig_diggable_area above.
function dig_stair_down(level, near, rank, radius_tiles)
  rank = rank or 1
  local chosen, err, upper_z, lower_z = ranked_stair_candidates(level, near, radius_tiles)
  if err then
    return nil, err
  end
  if rank < 1 or rank > #chosen then
    return nil, string.format(
      "no candidate at rank %d (found %d near %s)", rank, #chosen, near)
  end
  local c = chosen[rank]
  local described = describe_stair_candidate(c, upper_z)

  local ok_down, out_down, res_down = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', DOWNSTAIR_BLUEPRINT, '-c',
    string.format('%d,%d,%d', c.x, c.y, upper_z))
  local ok_up, out_up, res_up = pcall(
    dfhack.run_command_silent, 'quickfort', 'run', UPSTAIR_BLUEPRINT, '-c',
    string.format('%d,%d,%d', c.x, c.y, lower_z))

  described.rank = rank
  described.downstair_blueprint = DOWNSTAIR_BLUEPRINT
  described.downstair_ok = ok_down and res_down == CR_OK
  described.downstair_error = (not ok_down) and tostring(out_down) or nil
  described.downstair_stats = ok_down and parse_quickfort_stats(out_down) or nil
  described.upstair_blueprint = UPSTAIR_BLUEPRINT
  described.upstair_ok = ok_up and res_up == CR_OK
  described.upstair_error = (not ok_up) and tostring(out_up) or nil
  described.upstair_stats = ok_up and parse_quickfort_stats(out_up) or nil
  return described
end

-- Same module-load guard as the other df-overseer-*.lua scripts.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

-- LEVEL is optional in both subcommands (see file header): args[4] is read
-- as LEVEL only when it parses as a number, otherwise it's NEAR_LANDMARK and
-- every argument after it shifts left by one, with level left nil so
-- ranked_candidates defaults it to 0 (the landmark's own level).
if cmd == "find" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, radius
  if tonumber(args[4]) then
    level, near, radius = tonumber(args[4]), args[5], tonumber(args[6])
  else
    near, radius = args[4], tonumber(args[5])
  end
  if not (w and h and near) then
    print("usage: df-overseer-diggable find W H [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_diggable_area(w, h, level, near, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "dig" then
  local w, h = tonumber(args[2]), tonumber(args[3])
  local level, near, blueprint, rank, radius
  if tonumber(args[4]) then
    level, near, blueprint, rank, radius =
      tonumber(args[4]), args[5], args[6], tonumber(args[7]), tonumber(args[8])
  else
    near, blueprint, rank, radius =
      args[4], args[5], tonumber(args[6]), tonumber(args[7])
  end
  if not (w and h and near and blueprint) then
    print("usage: df-overseer-diggable dig W H [LEVEL] NEAR_LANDMARK"
      .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES]")
  else
    local result, err = dig_diggable_area(w, h, level, near, blueprint, rank, radius)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "find-stair" then
  local level, near, radius
  if tonumber(args[2]) then
    level, near, radius = tonumber(args[2]), args[3], tonumber(args[4])
  else
    near, radius = args[2], tonumber(args[3])
  end
  if not near then
    print("usage: df-overseer-diggable find-stair [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  else
    local results, err = find_stair_down(level, near, radius)
    print(json.encode(err and {error = err} or results))
  end
elseif cmd == "dig-stair" then
  local level, near, rank, radius
  if tonumber(args[2]) then
    level, near, rank, radius = tonumber(args[2]), args[3], tonumber(args[4]), tonumber(args[5])
  else
    near, rank, radius = args[2], tonumber(args[3]), tonumber(args[4])
  end
  if not near then
    print("usage: df-overseer-diggable dig-stair [LEVEL] NEAR_LANDMARK [RANK] [RADIUS_TILES]")
  else
    local result, err = dig_stair_down(level, near, rank, radius)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-diggable find W H [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-diggable dig W H [LEVEL] NEAR_LANDMARK"
    .. " BLUEPRINT_FILE [RANK] [RADIUS_TILES]")
  print("usage: df-overseer-diggable find-stair [LEVEL] NEAR_LANDMARK [RADIUS_TILES]")
  print("usage: df-overseer-diggable dig-stair [LEVEL] NEAR_LANDMARK"
    .. " [RANK] [RADIUS_TILES]")
end
