-- df-overseer-digcancel.lua
--@module = true
--
-- The game's own dig cancellations, read from the report store so they are
-- never mistaken for a stuck, stalled or stranded dig.
--
-- When a miner is about to dig a tile beside aquifer ("damp") or magma
-- ("warm") stone, the game itself cancels the dig designation and posts an
-- announcement: DIG_CANCEL_DAMP (id 52) or DIG_CANCEL_WARM (id 51) in this
-- version's df.announcement_type (research/data/2026-09-23-announcement-
-- types.tsv; research/2026-10-08-architect-circulation-red-team.md M1/W-6).
-- Because the designation is removed, a designation-and-job census sees "no
-- pending dig and no job": it reads as finished, or as a stall, and the old
-- recovery (release, re-apply, strand diagnosis) is the wrong answer. The
-- right answer is the one the game gave: this spot is damp or warm. Re-site
-- it. NEVER retry it: re-designating the same tile only gets cancelled again.
--
-- Players see these in the announcement log, so this is no-armok information.
-- A report carries its tile (`rep.pos`); it is matched to a caller's rect and
-- described landmark-relative, never returned as a coordinate.
--
-- Used by df-overseer-blueprint.lua (dig progress: state `cancelled_by_game`)
-- and df-overseer-stuckjobs.lua (a workerless dig job on a tile the game has
-- cancelled is reported as such, not as "no worker assigned").

KIND_BY_TYPE = {DIG_CANCEL_DAMP = "damp", DIG_CANCEL_WARM = "warm"}

local TICKS_PER_YEAR = 403200
local MAX_SCAN = 6000

local function type_ids()
  local ids = {}
  for name, kind in pairs(KIND_BY_TYPE) do
    local ok, id = pcall(function() return df.announcement_type[name] end)
    if ok and id ~= nil then ids[id] = kind end
  end
  return ids
end

-- Every dig-cancel report newer than `since_abs_tick` (an absolute tick, year
-- * 403200 + tick in year; nil for "as far back as the log goes"). Newest
-- first. Each: {kind = "damp"|"warm", x, y, z, abs_tick}.
function recent(since_abs_tick)
  local ids = type_ids()
  local out = {}
  local ok = pcall(function()
    local reports = df.global.world.status.reports
    local scanned = 0
    for i = #reports - 1, 0, -1 do
      local rep = reports[i]
      scanned = scanned + 1
      if scanned > MAX_SCAN then break end
      local abs = rep.year * TICKS_PER_YEAR + rep.time
      if since_abs_tick and abs < since_abs_tick then break end
      local kind = ids[rep.type]
      if kind and rep.pos and rep.pos.x ~= nil and rep.pos.x >= 0 then
        out[#out + 1] = {kind = kind, x = rep.pos.x, y = rep.pos.y, z = rep.pos.z, abs_tick = abs}
      end
    end
  end)
  return out, ok
end

-- Cancellations inside the rect {x, y, w, h} at level z. Returns
-- {damp = n, warm = m, total = n+m, tiles = {{kind, x, y, z}}, read_ok}.
-- Distinct tiles only (a tile cancelled twice is one tile).
function in_rect(x, y, w, h, z, since_abs_tick)
  local list, ok = recent(since_abs_tick)
  local res = {damp = 0, warm = 0, total = 0, tiles = {}, read_ok = ok}
  local seen = {}
  for _, c in ipairs(list) do
    if c.z == z and c.x >= x and c.x <= x + w - 1 and c.y >= y and c.y <= y + h - 1 then
      local key = c.x .. "," .. c.y
      if not seen[key] then
        seen[key] = true
        res[c.kind] = res[c.kind] + 1
        res.total = res.total + 1
        res.tiles[#res.tiles + 1] = c
      end
    end
  end
  return res
end

-- The kind ("damp"/"warm") if the game cancelled a dig on exactly this tile
-- since `since_abs_tick`, else nil.
function kind_at(x, y, z, since_abs_tick)
  for _, c in ipairs((recent(since_abs_tick))) do
    if c.x == x and c.y == y and c.z == z then return c.kind end
  end
  return nil
end

function label(kind)
  return "cancelled by the game: " .. tostring(kind)
end

-- Landmark-relative descriptions of up to `limit` cancelled tiles. Needs
-- df-overseer-landmarks; if it cannot be loaded the descriptions are omitted,
-- never replaced by coordinates.
function describe(tiles, limit)
  local ok_mod, landmarks = pcall(reqscript, 'df-overseer-landmarks')
  local out = {}
  for i, t in ipairs(tiles) do
    if i > (limit or 5) then break end
    local entry = {kind = t.kind, status = label(t.kind)}
    if ok_mod and type(landmarks) == 'table' then
      local ok, info = pcall(landmarks.nearest_landmark, t.x, t.y, t.z)
      if ok and info then
        entry.near_landmark, entry.direction, entry.distance_tiles = info.name, info.direction, info.distance_tiles
      end
    end
    out[#out + 1] = entry
  end
  return out
end

if dfhack_flags and dfhack_flags.module then
  return
end
print("df-overseer-digcancel is a module; see its header")
