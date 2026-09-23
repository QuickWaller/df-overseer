-- df-overseer-ledger.lua
--@module = true
--
-- handoffs/2026-09-23-attention-tiers-ingame.md item 4. A standing, per-race
-- observation ledger (research/2026-09-23-wildlife-threat-classes.md S:E3):
-- aggregated sightings and outcomes for wildlife and threats
-- df-overseer-threat.lua's find_threats (and, once wired, df-overseer-
-- diff.lua's REPORT log) already sees, so a repeated harmless visitor
-- becomes a pattern readable on the Overseer's own next ordinary wake,
-- instead of either silence or a repeated tripwire.
--
-- ============================================================================
-- HARD RULE, STRUCTURAL, NOT A COMMENT. This file's write path (record()
-- below, and load_rows/save_rows, everything it calls) NEVER calls
-- dfhack.world.SetPauseState, clock_pause, clock_resume, repeatUtil.* or any
-- df-overseer-clock.lua function -- this file does not even reqscript
-- df-overseer-clock. It is READ by df-overseer-threat.lua (a prior-distance
-- lookup, ledger_closest_distance) and WRITTEN by df-overseer-clock.lua's own
-- tripwire step, but the pause/slow/wake DECISION is made there, not here --
-- this file only ever aggregates what it is told. tests/
-- test_observation_ledger.py greps this file's own source for exactly the
-- forbidden call names as the structural guard, so a future edit that
-- accidentally wires a pause call in here fails a test, not just a review.
--
-- ============================================================================
-- STORAGE. A single JSON file, atomic replace (json.encode_file), the same
-- single-writer discipline df-overseer-clock.lua's own latch file already
-- uses (see that file's header) -- kept in a SEPARATE file/directory from the
-- clock's latch, because the two have different lifecycles: the latch is
-- cleared once acknowledged; this ledger accumulates and only ever decays at
-- read time (below).
--
-- ============================================================================
-- KEY: race name only (df-overseer-threat.lua's own race_name(unit)), never a
-- per-unit id. A wandering wildlife population turns over individuals, and a
-- vanilla player watching wildlife does not track individual identities
-- either (research doc S:E3(2)) -- per-unit tracking would fragment the
-- count without adding anything a player-visible observer could use.
--
-- ============================================================================
-- DECAY: read-time only, never swept on write (S:E3(3)). A row whose
-- `outcomes` table holds ONLY "present" and whose last_seen_tick is older
-- than the caller's own window is left out of a read_ledger() call's
-- results -- nothing is ever deleted from the file by a read. A row with any
-- non-"present" outcome (theft, kill, buildingdestroyer, ...) is never
-- subject to the window; it graduates to the permanent record, per the
-- handoff's own instruction.
--
-- ============================================================================
-- PLAYER VISIBILITY. Every field this ledger stores (race, tick, distance,
-- outcome name) is already something df-overseer-threat.lua's find_threats
-- and df-overseer-diff.lua's REPORT log legally expose today (both
-- knowledge_scope: player_visible/player_derivable, see those files'
-- headers); aggregating them over time adds no new capability, only memory
-- (research doc S:E3(6)). This file reads nothing itself -- every value it
-- stores was already read, and already judged legal, by its caller.

local json = require('json')

local STATE_DIR = "dfhack-config/overseer-ledger"
local STATE_FILE = STATE_DIR .. "/observations.json"

-- Reasoned, not sourced -- same honesty as df-overseer-threat.lua's own
-- DEFAULT_CLOSE_RANGE_TILES (see that file): research/2026-09-23-wildlife-
-- threat-classes.md S:C is explicit that this project has no measured
-- tick-to-tile number to derive a real decay window from. ~100 real seconds
-- at base_fps 100, a round multiple of df-overseer-clock.lua's own
-- DEFAULT_CHECK_INTERVAL_TICKS (100). Overridable by the caller; not tuned
-- against a live fort.
local DEFAULT_DECAY_WINDOW_TICKS = 10000

local function ensure_state_dir()
  if not dfhack.filesystem.isdir(STATE_DIR) then
    dfhack.filesystem.mkdir_recursive(STATE_DIR)
  end
end

-- {} on a missing/unreadable file (json.decode_file's own documented
-- fallback), same discipline as df-overseer-clock.lua's read_latch.
local function load_rows()
  ensure_state_dir()
  local ok, data = pcall(json.decode_file, STATE_FILE)
  if not ok or type(data) ~= "table" then
    return {}
  end
  return data
end

local function save_rows(rows)
  ensure_state_dir()
  json.encode_file(rows, STATE_FILE)
end

-- Same tick formula as df-overseer-clock.lua's own read_tick -- duplicated,
-- not reqscript'd, on purpose: this file must never reqscript
-- df-overseer-clock (see header's hard rule) even for a harmless read, so
-- the dependency edge itself cannot become a route to a pause/wake call
-- later without someone noticing they had to ADD a new require line.
local function current_tick()
  local ok, cur_year, cur_year_tick = pcall(function()
    return df.global.cur_year, df.global.cur_year_tick
  end)
  if not ok then
    return nil
  end
  return cur_year * 403200 + cur_year_tick
end

-- ----------------------------------------------------------------------------
-- Read-only: the prior closest_distance_tiles this ledger has on file for
-- RACE, or nil on a first sighting. Called by df-overseer-threat.lua BEFORE
-- this scan's own record() call, per the "closing in" rule
-- (research doc S:E1, df-overseer-threat.lua's own tier comment). Never
-- mutates.
function ledger_closest_distance(race)
  if not race then
    return nil
  end
  local rows = load_rows()
  local row = rows[race]
  return row and row.closest_distance_tiles or nil
end

-- ----------------------------------------------------------------------------
-- The only write entry point. race: string, required. tick/distance_tiles:
-- number or nil. outcome: "present" (default), "theft", "kill", or any other
-- name a caller supplies -- this file does not enumerate outcomes, the
-- find_threats/REPORT callers decide, per the research doc's own "reuse the
-- report layer as the source of truth for did-something, don't invent a
-- second one" (S:E3(4)).
--
-- NEVER calls SetPauseState, never calls clock_*, never calls repeatUtil.*.
-- See header.
function record(race, tick, distance_tiles, outcome)
  if not race or race == "" then
    return { ok = false, error = "record requires a race" }
  end
  outcome = outcome or "present"

  local rows = load_rows()
  local row = rows[race]
  if not row then
    row = {
      race = race,
      first_seen_tick = tick,
      last_seen_tick = tick,
      sighting_count = 0,
      closest_distance_tiles = distance_tiles,
      outcomes = {},
    }
    rows[race] = row
  end

  row.sighting_count = (row.sighting_count or 0) + 1
  if tick ~= nil then
    row.first_seen_tick = row.first_seen_tick or tick
    row.last_seen_tick = tick
  end
  if distance_tiles ~= nil
      and (row.closest_distance_tiles == nil or distance_tiles < row.closest_distance_tiles) then
    row.closest_distance_tiles = distance_tiles
  end
  row.outcomes[outcome] = (row.outcomes[outcome] or 0) + 1

  save_rows(rows)
  return { ok = true, race = race, row = row }
end

-- ----------------------------------------------------------------------------
-- Read verb (handoff item 4: "provide a read verb and grant it to the roles
-- that should see it"). max_age_ticks: rows whose ONLY outcome is "present"
-- and whose last_seen_tick is older than (now - max_age_ticks) are left out.
-- A row with any other outcome always survives, regardless of age. nil
-- max_age_ticks (or an unreadable current tick) disables the window --
-- returns every row.
function read_ledger(max_age_ticks)
  local rows = load_rows()
  local now_tick = current_tick()
  local out = {}
  for _, row in pairs(rows) do
    local only_present = true
    for outcome_name, _ in pairs(row.outcomes or {}) do
      if outcome_name ~= "present" then
        only_present = false
        break
      end
    end
    local stale = max_age_ticks ~= nil and now_tick ~= nil and row.last_seen_tick ~= nil
      and (now_tick - row.last_seen_tick) > max_age_ticks
    if not (only_present and stale) then
      table.insert(out, row)
    end
  end
  table.sort(out, function(a, b) return (a.race or "") < (b.race or "") end)
  return out
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "record" then
  local race = args[2]
  local tick = tonumber(args[3])
  local distance = tonumber(args[4])
  local outcome = args[5]
  print(json.encode(record(race, tick, distance, outcome)))
elseif cmd == "read" then
  local max_age = tonumber(args[2]) or DEFAULT_DECAY_WINDOW_TICKS
  print(json.encode({ rows = read_ledger(max_age) }))
else
  print("usage: df-overseer-ledger <record RACE TICK DISTANCE_TILES [OUTCOME]|read [MAX_AGE_TICKS]>")
end
