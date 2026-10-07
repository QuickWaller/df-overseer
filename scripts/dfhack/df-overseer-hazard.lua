-- df-overseer-hazard.lua
--@module = true
--
-- The aquifer / magma siting rule, in one dependency-free leaf that every
-- siting and dig path asks (diggable find/dig/find-stair/dig-stair,
-- blueprint preview/apply, construction mine-vein). User decision
-- 2026-10-08: "for now lets only choose spots with no aquifer", and the same
-- for magma. The reason (research/2026-10-08-architect-circulation-red-team.md
-- M1): the game cancels a dig beside aquifer ("damp") or magma ("warm") stone
-- by itself, and a light aquifer that is breached seeps water onto the
-- fortress. Better never to site there than to dig, be cancelled, and misread
-- the cancellation as a stuck dig.
--
-- WHAT THE RULE READS (no-armok, docs/ARMOK-RULINGS.md and CLAUDE.md): only
-- what a player can already see. A tile's `designation.water_table` bit
-- (aquifer) and its liquid (magma) are read ONLY on a tile whose
-- `designation.hidden` is false. A hidden tile is never inspected for either
-- bit; it counts as UNKNOWN. This file never reads a bit of a hidden tile
-- other than `hidden` itself.
--
-- THE RULE FOR UNKNOWN (policy, below): a hidden tile is allowed only when no
-- REVEALED hazard tile of that kind exists within `unknown_band_margin` z
-- levels of it anywhere on the map. In words: if the player has seen aquifer
-- on level N, hidden rock on levels N-margin..N+margin is treated as possibly
-- aquifer and refused. If nothing of that kind is revealed anywhere near, the
-- hidden rock is allowed (exactly as before this rule), because a player
-- cannot know otherwise either. Conservative on purpose, and relaxable in
-- POLICY.
--
-- FORT STATE, 2026-10-08 (read-only scan of VM 103, designation.hidden false
-- only): zero revealed aquifer tiles on any of the 186 levels. So today the
-- band set is empty and the rule excludes nothing; it starts to bite the
-- moment a digger exposes damp stone. Not a bug: the guard exists for that
-- moment.
--
-- ALL POLICY IS DATA (CLAUDE.md "policy in data, not branches"). Relaxing the
-- user's decision later is an edit to POLICY, no code change.

POLICY = {
  -- Refuse any dig tile that is, or touches, a revealed aquifer tile.
  exclude_aquifer = true,
  -- Same for a revealed magma tile (the game's "warm" cancel).
  exclude_magma = true,
  -- A tile is "touching" a hazard when a hazard tile is within this Manhattan
  -- distance (|dx|+|dy|+|dz|), so 1 is the six orthogonal and vertical
  -- neighbours the user named. 0 would mean the tile itself only.
  adjacency_radius = 1,
  -- "band": a hidden tile is refused when a revealed hazard of that kind
  -- exists within unknown_band_margin levels. "allow": hidden is never a
  -- reason. "refuse": any hidden tile is a reason (too strict to be useful
  -- for a fort dug into fresh rock; here for completeness).
  unknown_policy = "band",
  unknown_band_margin = 1,
  -- The band set is a whole-map scan; reuse it for this many milliseconds.
  cache_ms = 30000,
}

KINDS = {
  aquifer = {policy_key = "exclude_aquifer", phrase = "aquifer (damp) stone"},
  magma = {policy_key = "exclude_magma", phrase = "magma (warm) stone"},
}
-- Fixed order so the first reported hazard is deterministic.
KIND_ORDER = {"aquifer", "magma"}

local state_cache = {}      -- "x,y,z" -> "aquifer" | "magma" | "safe" | "hidden" | "none"
local band_cache = nil      -- {at = ms, kinds = {aquifer = {[z] = true}, magma = {...}}}
local counters = {}

local function now_ms()
  local ok, t = pcall(dfhack.getTickCount)
  if ok and t then return t end
  return 0
end

function reset()
  state_cache = {}
  band_cache = nil
  counters = {}
end

-- Called at the start of one finder run so the exclusion counts it reports are
-- its own. The tile-state cache is also dropped here so a finder never reads
-- a tile revealed a minute ago as still hidden.
function begin_scan()
  state_cache = {}
  counters = {}
end

function excluded_counts()
  local out, total = {}, 0
  for k, n in pairs(counters) do out[k] = n; total = total + n end
  out.total = total
  return out
end

local function bump(kind)
  counters[kind] = (counters[kind] or 0) + 1
end

-- One tile's visible hazard state. `designation.hidden` is read first and a
-- hidden tile's water_table / liquid bits are never touched.
local function tile_state(x, y, z)
  local key = x .. "," .. y .. "," .. z
  local s = state_cache[key]
  if s ~= nil then return s end
  local ok, des = pcall(dfhack.maps.getTileFlags, x, y, z)
  if not ok or des == nil then
    s = "none"   -- off the map or unreadable: not rock, not a reason
  elseif des.hidden then
    s = "hidden"
  elseif des.water_table then
    s = "aquifer"
  elseif des.flow_size and des.flow_size > 0
      and df.tile_liquid and des.liquid_type == df.tile_liquid.Magma then
    s = "magma"
  else
    s = "safe"
  end
  state_cache[key] = s
  return s
end

-- Every z level that holds at least one REVEALED hazard tile of each kind.
-- Walks the map's allocated blocks once, reading `hidden` before anything else.
local function bands()
  local t = now_ms()
  if band_cache and (t - band_cache.at) < POLICY.cache_ms then return band_cache.kinds end
  local kinds = {aquifer = {}, magma = {}}
  local ok = pcall(function()
    local blocks = df.global.world.map.map_blocks
    for i = 0, #blocks - 1 do
      local blk = blocks[i]
      local z = blk.map_pos.z
      local need_a = not kinds.aquifer[z]
      local need_m = not kinds.magma[z]
      if need_a or need_m then
        for tx = 0, 15 do
          for ty = 0, 15 do
            local d = blk.designation[tx][ty]
            if not d.hidden then
              if need_a and d.water_table then kinds.aquifer[z] = true; need_a = false end
              if need_m and d.flow_size > 0 and d.liquid_type == df.tile_liquid.Magma then
                kinds.magma[z] = true; need_m = false
              end
            end
          end
          if not (need_a or need_m) then break end
        end
      end
    end
  end)
  if not ok then
    -- An unreadable map is not "no hazard": refuse by marking every kind as
    -- banded everywhere. Callers see a clear reason rather than a silent pass.
    kinds = {aquifer = {_all = true}, magma = {_all = true}, unreadable = true}
  end
  band_cache = {at = t, kinds = kinds}
  return kinds
end

local function in_band(kind, z)
  local set = bands()[kind]
  if set._all then return true end
  local m = POLICY.unknown_band_margin or 0
  for dz = -m, m do
    if set[z + dz] then return true end
  end
  return false
end

local function enabled(kind)
  return POLICY[KINDS[kind].policy_key] and true or false
end

-- Offsets within the adjacency radius (Manhattan), nearest first, so the tile
-- itself is reported before a neighbour.
local function offsets(r)
  local out = {}
  for dx = -r, r do
    for dy = -r, r do
      for dz = -r, r do
        local d = math.abs(dx) + math.abs(dy) + math.abs(dz)
        if d <= r then out[#out + 1] = {dx, dy, dz, d} end
      end
    end
  end
  table.sort(out, function(a, b) return a[4] < b[4] end)
  return out
end

-- Why one tile may not be dug, or nil. Returns {kind, where, via}: where is
-- "tile" or "adjacent"; via is "revealed" (a visible hazard tile) or
-- "unknown_band" (a hidden tile on a level band with a revealed hazard).
function check_tile(x, y, z)
  local unknown = nil
  for _, o in ipairs(offsets(POLICY.adjacency_radius or 0)) do
    local tz = z + o[3]
    local s = tile_state(x + o[1], y + o[2], tz)
    local where = (o[4] == 0) and "tile" or "adjacent"
    if (s == "aquifer" or s == "magma") and enabled(s) then
      bump(s)
      return {kind = s, where = where, via = "revealed"}
    elseif s == "hidden" and not unknown then
      local up = POLICY.unknown_policy
      if up == "refuse" then
        unknown = {kind = "aquifer", where = where, via = "unknown_band"}
      elseif up == "band" then
        for _, k in ipairs(KIND_ORDER) do
          if enabled(k) and in_band(k, tz) then
            unknown = {kind = k, where = where, via = "unknown_band"}
            break
          end
        end
      end
    end
  end
  if unknown then bump(unknown.kind .. "_unknown"); return unknown end
  return nil
end

-- First hazard among a list of {x, y, z}; returns hazard, tile_index.
function check_tiles(tiles)
  for i, t in ipairs(tiles) do
    local h = check_tile(t.x, t.y, t.z)
    if h then return h, i end
  end
  return nil
end

function check_rect(x, y, z, w, h)
  for dx = 0, w - 1 do
    for dy = 0, h - 1 do
      local hz = check_tile(x + dx, y + dy, z)
      if hz then
        hz.x, hz.y, hz.z = x + dx, y + dy, z
        return hz
      end
    end
  end
  return nil
end

-- A coordinate-free sentence. `where_text` is the caller's landmark-relative
-- description of the offending tile (for example "12 tiles east of the Well"),
-- or nil.
function message(hz, where_text)
  local phrase = KINDS[hz.kind].phrase
  local loc = where_text and (" " .. where_text) or ""
  if hz.via == "unknown_band" then
    return string.format(
      "refused by the siting policy: an unrevealed tile%s could be %s, and %s has been revealed on this level band "
      .. "(policy: only sites with no aquifer or magma; hidden rock near revealed hazard counts as unsafe)",
      loc, phrase, phrase)
  end
  return string.format(
    "refused by the siting policy: the dig %s%s %s (policy: only sites with no aquifer or magma, "
    .. "adjacency radius %d; relax in df-overseer-hazard POLICY)",
    hz.where == "tile" and "would be in" or "would touch", loc, phrase, POLICY.adjacency_radius or 0)
end

-- Appended to a "nothing found" error when candidates were dropped for this.
function exclusion_note()
  local c = excluded_counts()
  if c.total == 0 then return nil end
  local parts = {}
  for _, k in ipairs({"aquifer", "magma", "aquifer_unknown", "magma_unknown"}) do
    if c[k] then parts[#parts + 1] = string.format("%d %s", c[k], (k:gsub("_", " "))) end
  end
  return string.format(
    "%d candidate tile(s) were excluded by the siting policy (no aquifer or magma sites; %s)",
    c.total, table.concat(parts, ", "))
end

if dfhack_flags and dfhack_flags.module then
  return
end
print("df-overseer-hazard is a module; see its header")
