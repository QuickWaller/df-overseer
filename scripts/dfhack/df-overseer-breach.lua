-- df-overseer-breach.lua
--@module = true
--
-- The second of two safety detectors research/2026-09-12-dfhack-capability-
-- checks.md §5 found this project has NO usable signal for: water or magma
-- breach. A checked negative across both DFHack's EventType enum and its
-- announcement_type enum (that research brief's own targeted grep of the
-- full announcement enum for FLOOD/BREACH/MAGMA/WATER/FLOW/DROWN/SURGE/CHASM
-- found nothing but two unrelated cosmetic/fishing messages). Must be polled
-- from scratch. This file is that poller.
--
-- CORRECTION TO THE RESEARCH BRIEF, found reading source this session: the
-- brief names the candidate as "df.global.world.flows... which the liquids
-- tool already reads". Neither half of that is quite right, checked
-- directly against df-structures @ 1dd01aad (df.world.xml, df.flow.xml,
-- df.block.xml) and dfhack @ b638b59d (plugins/liquids.cpp):
--   - There is no field literally named world.flows. The real fields are
--     world.orphaned_flows (an stl-vector<flow_info*>, "flows that are not
--     tied to a map_block", df.world.xml) and, separately, a per-block
--     `flows` vector (map_block.flows, df.block.xml). Neither is a single
--     flat "all active flows" list.
--   - `flow_info`/`flow_type` (df.flow.xml) is NOT a liquid-volume record.
--     Its actual enum items are airborne effect clouds: Miasma, Steam
--     (MIST_WATER), Mist (MIST_WATERFALL), MaterialDust, MagmaMist
--     (MIST_LAVA), Smoke, Dragonfire, Fire, Web, MaterialGas, MaterialVapor,
--     OceanWave, SeaFoam, ItemCloud. Steam/Mist/MagmaMist DO correlate with
--     nearby water/magma activity (evaporation, waterfalls, exposed lava),
--     but a flow_info entry is a rendered cloud effect, not "this tile has N
--     units of liquid" -- a slow, undramatic seep into a mined-out tunnel
--     can plausibly raise no cloud at all. So orphaned_flows/block.flows
--     were investigated as the brief asked, and are NOT used below as the
--     stage-1 gate for exactly this reason -- they would miss the quiet
--     case this detector most needs to catch. plugins/liquids.cpp itself,
--     read directly, confirms it does NOT touch world.flows/orphaned_flows
--     at all; it reads/writes per-tile liquid state via a MapCache
--     designation object instead (see below) -- so the brief's own "the
--     liquids tool already reads it" clause does not hold either.
--
-- THE REAL PER-TILE SIGNAL, source-confirmed two ways: (a) dfhack @
-- b638b59d's plugins/liquids.cpp itself, read directly: `des.bits.flow_size`
-- (0-7 depth) and `des.bits.liquid_type` (tile_liquid::Water/Magma) on a
-- MapCache-wrapped tile_designation; (b) independently confirmed against
-- THIS project's own exact installed build (DFHack 53.16-r1.1,
-- memory/dfhack-environment.md), not just a version-tag-matched clone --
-- several of that build's own shipped Lua scripts use the exact same fields
-- directly in Lua, read verbatim from the local install:
--   block.designation[x%16][y%16].flow_size   -- hack/scripts/deep-embark.lua:65,
--     hfs-pit.lua:86/100 (both read AND write this exact path)
--   block.designation[x%16][y%16].liquid_type  -- hack/scripts/devel/light.lua:233-285,
--     hack/scripts/modtools/spawn-liquid.lua:11-30 (df.tile_liquid.Water/Magma)
--   block.flags.update_liquid                  -- hack/scripts/extinguish.lua:46,
--     exterminate.lua:13, modtools/spawn-liquid.lua:33 (all WRITE this field
--     to mark a block for liquid-flow simulation -- confirms it's a real,
--     settable, per-block bit, not a derived/read-only value)
-- No live DFHack command was run to confirm this project's OWN fort ever
-- sets these fields during real play -- see the honest-gap list below.
--
-- TWO-STAGE DESIGN, because cost matters (the task's own framing, and this
-- project's own experience: df-overseer-diff.lua already flags
-- world.status.reports as growing unboundedly and needing a smarter
-- approach before a year-5 fort).
--
-- STAGE 1 (cheap, global, every poll): iterate every map block via
-- dfhack.maps.getBlock(bx,by,bz) across dfhack.maps.getSize()'s block-count
-- bounds (both confirmed directly from hack/lua/dfhack.lua's own
-- getSize() implementation, read from the local install: `return
-- map.x_count_block, map.y_count_block, map.z_count_block`) and read ONLY
-- `block.flags.update_liquid` -- one boolean field per block, not per tile.
-- REAL POLLING COST, stated honestly: O(x_count_block * y_count_block *
-- z_count_block) getBlock calls, each a cheap flag read. This is bounded by
-- the embark's fixed x,y footprint and the world's fixed z-height ceiling --
-- NOT by how much the fort has dug out. That is the actual cost property
-- that makes this viable on a year-5 fort: excavating another thousand
-- tiles does not add a single iteration to stage 1, because block COUNT is
-- fixed by map geometry, not by dig progress. What is NOT measured: the
-- real wall-clock cost of thousands of getBlock calls at Lua/native-binding
-- overhead on VM 103's actual hardware -- reasoned from the API's
-- documented shape, not timed. See the live-verification handoff.
--
-- Considered and NOT adopted as the stage-1 gate: a raw count of
-- world.orphaned_flows (or per-block flows) entries tagged Steam/Mist/
-- MagmaMist. It would be cheaper still (that vector is normally short), but
-- per the correction above it is a cloud-presence proxy, not a liquid-
-- presence signal, and would systematically miss a slow seep. Not wired in
-- at all here, rather than wired in as a false economy -- flagged as an
-- open idea, not a rejected-and-forgotten one, in case a later session
-- wants it as a supplementary early-warning hint alongside stage 1, not
-- instead of it.
--
-- STAGE 2 (localized, only when stage 1 trips): for each block flagged
-- update_liquid this poll -- normally zero -- scan its 16x16
-- `designation[tx][ty].flow_size`/`.liquid_type` tiles directly (the same
-- block object stage 1 already fetched, not re-fetched). Cost: O(256 *
-- blocks_flowing_this_poll), and blocks_flowing_this_poll is the whole
-- point of stage 1 -- normally 0, so stage 2 normally does not run at all.
--
-- SEVERITY, not just presence -- the harder design problem, because "is
-- this tile's liquid a problem" is NOT answerable from presence alone.
-- Standing water in a well is real, present, flow_size > 0 water, exactly
-- as designed -- flagging it every poll forever would make this detector
-- useless by making it constantly noisy. THE FIX ADOPTED: liquid presence
-- is compared against a session-scoped baseline of "flow_size last seen at
-- this exact tile" (a plain _G table, same pattern and same justification
-- as df-overseer-diff.lua's own event log: ephemeral/session-scoped is
-- fine, nothing here needs to survive a DFHack process restart). Only a
-- RISE (current flow_size > last-seen at that tile) counts as a finding at
-- all. A well's water, once seen once, stops triggering forever (its
-- flow_size neither rises nor is re-reported as new) -- exactly the
-- "standing water in a well is not a breach" requirement, achieved by
-- delta rather than by trying to special-case "well" as a building type.
--
-- HONEST CONSEQUENCE OF THAT FIX, stated plainly, not buried: the FIRST
-- call this DFHack process ever makes to check_breach cannot distinguish
-- "always been here" from "just appeared", because there is no prior
-- baseline to compare against. So the first call silently SEEDS the
-- baseline from whatever is currently flowing and reports severity="none"
-- regardless of what is actually present (`first_call=true` in the
-- output says so explicitly -- never silently). If a real breach is
-- already actively rising at the exact moment this tool is first invoked
-- after a DF/DFHack process start (including after any restart -- _G does
-- not survive one), that specific poll will miss it, and only the
-- following poll (once flow_size has risen further) will catch the
-- continuation. This is a real, load-bearing limitation of a from-scratch,
-- no-history poller, not an oversight -- see the live-verification handoff
-- for how to test around it deliberately.
--
-- REACHABILITY reused deliberately, matching the sibling threat detector
-- (df-overseer-threat.lua) and the task's own instruction to compose
-- verified machinery rather than invent new heuristics per detector: a
-- rising tile is escalated if it is ADJACENT to the walkable network any
-- citizen currently occupies, OR within radius_tiles of a named landmark.
-- Deliberately checks the RING around the liquid tile, not the liquid
-- tile's own walkable group -- a tile actually covered by deep water or
-- magma is almost never itself walkable (getWalkableGroup would read 0
-- there even for water spreading directly into a dwarf's corridor), so
-- testing the liquid tile's own group would silently never fire. Mirrors
-- df-overseer-diggable.lua's borders_walkable_network ring check exactly,
-- same same-z-level-only limitation, stated there and true here too: a
-- breach spreading down a stairwell to the level below is not detected by
-- this ring check at all, only by the flow_size scan eventually reaching
-- that level's own blocks on a later poll.
--
-- Design commitment #1: never a raw coordinate. Findings carry
-- near_landmark/direction/distance_tiles (via nearest_landmark, reqscript'd)
-- exactly like every other deployed perception tool -- never x/y/z. The
-- baseline table's keys ARE coordinate-shaped ("x,y,z" strings) but never
-- leave this file's own _G state.
--
-- KNOWN UNBOUNDED GROWTH, flagged rather than glossed over (same category
-- of honesty df-overseer-diff.lua already applies to world.status.reports):
-- the baseline table never evicts a key once a tile has ever flowed, even
-- after that tile stops flowing. A slow leak that migrates across many
-- tiles over a long session grows this table without bound. Not a problem
-- at the scale this project has tested anything at; worth instrumenting if
-- it ever matters, not solved here.
--
-- Usage: ./dfhack-run df-overseer-breach check [RADIUS_TILES]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')

local MAX_RADIUS = 60
local DEFAULT_RADIUS = 30

local SEV_RANK = { none = 0, info = 1, moderate = 2, severe = 3, critical = 4 }

local function walkable_group(x, y, z)
  local ok, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  return ok and group or 0
end

-- Duplicated from df-overseer-threat.lua rather than shared via reqscript --
-- same rationale df-overseer-landmarks.lua already gives for duplicating
-- parse_quickfort_stats: a small, self-contained, pure helper, not worth a
-- cross-file dependency for six lines.
local function citizen_groups()
  local groups = {}
  for _, unit in ipairs(dfhack.units.getCitizens()) do
    local x, y, z = dfhack.units.getPosition(unit)
    if x then
      local g = walkable_group(x, y, z)
      if g ~= 0 then
        groups[g] = true
      end
    end
  end
  return groups
end

-- True if any of the 8 same-z neighbors of x,y is walkable and in `groups`.
-- See header: deliberately checks the RING, not the liquid tile's own
-- group, which would almost always read 0. Mirrors
-- df-overseer-diggable.lua's borders_walkable_network.
local function adjacent_to_citizen_network(x, y, z, groups)
  for dx = -1, 1 do
    for dy = -1, 1 do
      if not (dx == 0 and dy == 0) then
        local g = walkable_group(x + dx, y + dy, z)
        if g ~= 0 and groups[g] then
          return true
        end
      end
    end
  end
  return false
end

local function describe_position(x, y, z)
  local ok, info = pcall(landmarks_mod.nearest_landmark, x, y, z)
  return ok and info or nil
end

-- STAGE 1. Returns the list of {bx,by,bz,block} entries currently flagged
-- update_liquid, plus the total block count scanned (for honest cost
-- reporting in the output, not just the doc comment).
local function scan_flowing_blocks()
  local bx_max, by_max, bz_max = dfhack.maps.getSize()
  local flowing = {}
  local scanned = 0
  for bz = 0, bz_max - 1 do
    for bx = 0, bx_max - 1 do
      for by = 0, by_max - 1 do
        scanned = scanned + 1
        local ok, block = pcall(dfhack.maps.getBlock, bx, by, bz)
        if ok and block then
          local ok_f, is_flowing = pcall(function() return block.flags.update_liquid end)
          if ok_f and is_flowing then
            table.insert(flowing, {bx = bx, by = by, bz = bz, block = block})
          end
        end
      end
    end
  end
  return flowing, scanned
end

-- STAGE 2, scoped to one already-flagged block. Returns every tile in it
-- with flow_size > 0 -- real presence, not yet compared to the baseline.
local function scan_block_tiles(entry)
  local base_x, base_y, base_z = entry.bx * 16, entry.by * 16, entry.bz
  local hits = {}
  for tx = 0, 15 do
    for ty = 0, 15 do
      local ok, des = pcall(function() return entry.block.designation[tx][ty] end)
      if ok and des and des.flow_size and des.flow_size > 0 then
        table.insert(hits, {
          x = base_x + tx, y = base_y + ty, z = base_z,
          flow_size = des.flow_size, liquid_type = des.liquid_type,
        })
      end
    end
  end
  return hits
end

if not _G.__df_overseer_breach_initialized then
  -- key "x,y,z" -> last-seen flow_size at that tile. See header for why
  -- this is a plain _G table (session-scoped, same as df-overseer-diff.lua's
  -- event log) and why unbounded growth is a known, accepted limitation.
  _G.__df_overseer_breach_baseline = {}
  _G.__df_overseer_breach_seeded = false
  _G.__df_overseer_breach_initialized = true
end

-- Exported for other df-overseer-*.lua scripts via reqscript, matching the
-- module-export convention every other file in this set uses.
function check_breach(radius_tiles)
  local radius = math.min(radius_tiles or DEFAULT_RADIUS, MAX_RADIUS)
  local flowing_blocks, blocks_scanned = scan_flowing_blocks()

  if #flowing_blocks == 0 then
    return {
      stage1_triggered = false,
      severity = "none",
      blocks_scanned = blocks_scanned,
      blocks_flowing = 0,
      findings = {},
      note = "no map block flagged update_liquid this poll -- stage 2 skipped entirely",
    }
  end

  local first_call = not _G.__df_overseer_breach_seeded
  local groups = citizen_groups()
  local findings = {}
  local worst_rank = 0

  for _, entry in ipairs(flowing_blocks) do
    for _, hit in ipairs(scan_block_tiles(entry)) do
      local key = string.format("%d,%d,%d", hit.x, hit.y, hit.z)
      local prev = _G.__df_overseer_breach_baseline[key] or 0
      local delta = hit.flow_size - prev
      _G.__df_overseer_breach_baseline[key] = hit.flow_size

      if not first_call and delta > 0 then
        local reachable = adjacent_to_citizen_network(hit.x, hit.y, hit.z, groups)
        local near = describe_position(hit.x, hit.y, hit.z)
        if not reachable and near and near.distance_tiles <= radius then
          reachable = true
        end
        local is_magma = hit.liquid_type == df.tile_liquid.Magma

        local severity
        if reachable and is_magma then
          severity = "critical"
        elseif reachable or is_magma then
          severity = "severe"
        else
          severity = "moderate"
        end
        if SEV_RANK[severity] > worst_rank then
          worst_rank = SEV_RANK[severity]
        end

        table.insert(findings, {
          liquid_type = is_magma and "Magma" or "Water",
          flow_size = hit.flow_size,
          rose_by = delta,
          near_landmark = near and near.name or nil,
          direction = near and near.direction or nil,
          distance_tiles = near and near.distance_tiles or nil,
          adjacent_to_walkable_network = reachable,
          severity = severity,
        })
      end
    end
  end

  _G.__df_overseer_breach_seeded = true

  local overall
  if first_call then
    overall = "none"
  elseif #findings == 0 then
    overall = "info"
  else
    for name, rank in pairs(SEV_RANK) do
      if rank == worst_rank then overall = name end
    end
  end

  table.sort(findings, function(a, b) return SEV_RANK[a.severity] > SEV_RANK[b.severity] end)

  return {
    stage1_triggered = true,
    first_call = first_call,
    severity = overall,
    blocks_scanned = blocks_scanned,
    blocks_flowing = #flowing_blocks,
    findings = findings,
    note = first_call
      and "first call this DF process: baseline seeded silently from current state, no severity judgment possible yet -- call again to detect a real change"
      or (#findings == 0
        and "stage 1 tripped (liquid actively flowing somewhere) but nothing rose since the last poll -- likely known/stable (e.g. a well, a river)"
        or nil),
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "check" then
  local radius = tonumber(args[2])
  print(json.encode(check_breach(radius)))
else
  print("usage: df-overseer-breach check [RADIUS_TILES]")
end
