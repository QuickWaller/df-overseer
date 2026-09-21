-- df-overseer-vitals.lua
--@module = true
--
-- handoffs/2026-09-22-loop-clock-conductor-role.md, build item 3:
-- vitals.summary, the conductor's per-cycle Tier 0 read (docs/AGENT-LOOP.md
-- ss1 "Read": "the conductor reads vitals, the diff since each role last
-- woke, and the queue"). A small, O(population)-not-O(map-size) aggregate,
-- never a per-citizen dump -- the conductor's briefing budget
-- (docs/AGENT-LOOP.md item 6, "Tier 0 figures only... nothing that grows
-- with the fort") is the reason this exists as its own tool rather than the
-- caller re-deriving it from getCitizens() every cycle.
--
-- ============================================================================
-- WHY THIS NEVER RETURNS A RAW hunger_timer/thirst_timer INTEGER.
-- research/2026-09-16-food-clock-and-farm-lead-time.md's own bottom line is
-- explicit and is treated here as binding, not advisory: "the raw
-- hunger_timer/thirst_timer integers themselves... are diagnostic-only --
-- not something any vanilla screen shows a player... A legitimate
-- citizen-status-class tool could reconstruct... whether any citizen's
-- status icon is currently flashing... entirely from player-visible facts...
-- It could NOT legitimately expose 'Solon's hunger_timer is 34,261'." So
-- this file reads counters2.hunger_timer/thirst_timer internally (the only
-- way to compute anything at all) but returns only the derived CATEGORY a
-- player's own status-flash icon would show: "fine"/"hungry"/"starving" and
-- "fine"/"thirsty"/"dehydrated". Tagged knowledge_scope: player_derivable in
-- TOOLS.yaml for exactly this reason -- an internal read producing a safe,
-- bounded, player-legal output, the same shape df-overseer-threat.lua's own
-- find_threats already uses for danger flags it reads but never filters on
-- directly.
--
-- Thresholds: sourced identically to df-overseer-clock.lua (see that file's
-- header) from hack/scripts/full-heal.lua's is_in_dire_need() (critical: 75000
-- hunger / 50000 thirst) plus the same research doc's earlier, non-critical
-- "Hungry"/"Thirsty" flash thresholds (50000 / 25000) for the warning level.
-- Deliberately duplicated as literals rather than shared via reqscript with
-- df-overseer-clock.lua: both files are small, the numbers are load-bearing
-- and worth reading in place, and this project's own precedent
-- (df-overseer-sampler.lua's header: "is_fort_owned is COPIED, not
-- required... the LOGIC is reused verbatim... while the Lua binding is
-- necessarily a duplicate") already treats this as the right call over
-- cross-file coupling for a handful of numbers.
--
-- ============================================================================
-- DEATHS. Reuses the SAME approach df-overseer-sampler.lua's own
-- get_fort_metrics already uses and has live-verified the shape of
-- (decisions/DECISIONS.md 2026-09-19: "a deliberately broken lookup...
-- produced null plus an error... never 0"): count units in
-- world.units.all that are both dfhack.units.isDead and dfhack.units.isOwnCiv.
-- Bounded (a specific, named vector, never a map scan). Same documented
-- undercount: a corpse that fully decays out of the vector is no longer
-- counted. Copied rather than reqscript'd for the same reason sampler copies
-- is_fort_owned from df-overseer-stocks.lua: the source function is a local,
-- not exported, and this stream's touched surfaces do not include editing
-- df-overseer-sampler.lua to export it.

local json = require('json')

-- Sourced above.
local HUNGER_WARNING, HUNGER_CRITICAL = 50000, 75000
local THIRST_WARNING, THIRST_CRITICAL = 25000, 50000

local function hunger_status(h)
  if h > HUNGER_CRITICAL then return "starving" end
  if h > HUNGER_WARNING then return "hungry" end
  return "fine"
end

local function thirst_status(t)
  if t > THIRST_CRITICAL then return "dehydrated" end
  if t > THIRST_WARNING then return "thirsty" end
  return "fine"
end

-- Rank: dehydrated/starving worst, then thirsty/hungry, then fine. Hunger and
-- thirst are ranked independently (two separate "worst" fields), matching
-- the handoff's "worst hunger and thirst" (plural), not a single combined
-- worst-citizen figure.
local STATUS_RANK = { fine = 0, hungry = 1, thirsty = 1, starving = 2, dehydrated = 2 }

local function read_tick()
  local ok, cur_year, cur_year_tick = pcall(function()
    return df.global.cur_year, df.global.cur_year_tick
  end)
  if not ok then
    return false, nil, nil, nil
  end
  return true, cur_year, cur_year_tick, cur_year * 403200 + cur_year_tick
end

local function count_dead_own_civ()
  local ok, n_or_err = pcall(function()
    local n = 0
    local vec = df.global.world.units.all
    for i = 0, #vec - 1 do
      local u = vec[i]
      local ok_d, is_dead = pcall(dfhack.units.isDead, u)
      local ok_o, is_own = pcall(dfhack.units.isOwnCiv, u)
      if ok_d and is_dead and ok_o and is_own then
        n = n + 1
      end
    end
    return n
  end)
  if ok then
    return true, n_or_err, nil
  end
  return false, nil, tostring(n_or_err)
end

function vitals_summary()
  local ok_tick, cur_year, cur_year_tick, abs_tick = read_tick()

  local ok_cit, citizens = pcall(dfhack.units.getCitizens, true)
  if not ok_cit or not citizens then
    return {
      ok = false,
      error = "could not read citizens: " .. tostring(citizens),
    }
  end

  local worst_hunger, worst_hunger_rank = "fine", 0
  local worst_thirst, worst_thirst_rank = "fine", 0
  local warning_count = 0

  for _, u in ipairs(citizens) do
    local ok_h, h = pcall(function() return u.counters2.hunger_timer end)
    local ok_t, t = pcall(function() return u.counters2.thirst_timer end)
    local h_status = (ok_h and type(h) == "number") and hunger_status(h) or nil
    local t_status = (ok_t and type(t) == "number") and thirst_status(t) or nil

    if h_status and STATUS_RANK[h_status] > worst_hunger_rank then
      worst_hunger, worst_hunger_rank = h_status, STATUS_RANK[h_status]
    end
    if t_status and STATUS_RANK[t_status] > worst_thirst_rank then
      worst_thirst, worst_thirst_rank = t_status, STATUS_RANK[t_status]
    end
    if (h_status and h_status ~= "fine") or (t_status and t_status ~= "fine") then
      warning_count = warning_count + 1
    end
  end

  local ok_dead, dead_total, dead_err = count_dead_own_civ()

  return {
    ok = true,
    cur_year = ok_tick and cur_year or nil,
    cur_year_tick = ok_tick and cur_year_tick or nil,
    abs_tick = ok_tick and abs_tick or nil,
    alive = #citizens,
    dead_total = ok_dead and dead_total or nil,
    dead_total_error = (not ok_dead) and dead_err or nil,
    dead_total_caveat = "undercounts once a corpse fully decays out of "
      .. "world.units.all -- same documented gap as df-overseer-sampler.lua's "
      .. "own fort/deaths metric",
    worst_hunger_status = worst_hunger,
    hunger_warning_threshold = "hungry",
    hunger_critical_threshold = "starving",
    worst_thirst_status = worst_thirst,
    thirst_warning_threshold = "thirsty",
    thirst_critical_threshold = "dehydrated",
    warning_count = warning_count,
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "summary" then
  print(json.encode(vitals_summary()))
else
  print("usage: df-overseer-vitals summary")
end
