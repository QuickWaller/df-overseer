-- df-overseer-clock.lua
--@module = true
--
-- handoffs/2026-09-22-loop-clock-conductor-role.md. Code, never a model,
-- controls the game clock (docs/AGENT-LOOP.md ss2-3). This file is the
-- game-side half: a frame-cap control, a pause/resume gate, and an in-game
-- tripwire watcher that pauses the fort itself and latches why, so the fort
-- stays safe even if the conductor process (a separate, later stream) or
-- openclaw dies. docs/TRAPS.md, "the wedged command pipe that took the SSH
-- watchdog down": the tripwire runs INSIDE the game loop via a DFHack
-- `repeat`, the same registration pattern as `overseer-autosave` and
-- `overseer-sampler` (both wired through dfhack-config/init/onMapLoad.init),
-- not over SSH, so a wedged external command pipe cannot take the pause gate
-- down with it.
--
-- ============================================================================
-- BOUNDED READS ONLY -- docs/TRAPS.md's "no unbounded query against a live
-- DFHack process" rule. Every function below iterates a specific, named,
-- small vector: dfhack.units.getCitizens() (bounded by population),
-- world.units.active (bounded by active units, the same vector
-- df-overseer-threat.lua's own find_threats already iterates), or exactly
-- three named save-slot directories. Nothing here scans map tiles.
--
-- ============================================================================
-- WHY SET-SPEED/PAUSE/RESUME/ARM/DISARM/CLEAR ARE A NEW EXCEPTION IN
-- dfmcp/roles.py, NOT A LOOSENING OF IT. dfmcp/roles.py's rule 2 currently
-- refuses ANY mutating tool to any role but the roster's sole_writer
-- (the Overseer). Clock control mutates DFHack's OWN runtime state (the
-- frame cap, the pause flag, a scheduled watcher) but never the FORT the
-- way a designation or a build does, and it is explicitly code's job, never
-- a model's (docs/AGENT-LOOP.md: "Starting and stopping the fort belong to
-- code, never to a model"). roles.py now carries a narrow, explicit,
-- load-time-checked exception: a fixed set of canonical tool ids
-- (SYSTEM_CLASS_TOOL_IDS) may be granted ONLY to a role of kind "system",
-- and that check applies even to the sole_writer -- the Overseer's charter
-- line "never unpause without being asked to" is therefore a structural,
-- tested guarantee (agents/conductor's tools.yaml is the only tools.yaml
-- that may reference clock.resume; agents/overseer/tools.yaml is not this
-- stream's file to touch and today references no clock tool at all), not
-- just a sentence in a role.md a future edit could quietly contradict.
--
-- ============================================================================
-- KNOWLEDGE SCOPE: hunger/thirst are read, never returned raw.
-- research/2026-09-16-food-clock-and-farm-lead-time.md's own bottom line
-- (its S:%S last section) is explicit: "the raw hunger_timer/thirst_timer
-- integers themselves... are diagnostic-only -- not something any vanilla
-- screen shows a player... A legitimate citizen-status-class tool could
-- reconstruct... whether any citizen's status icon is currently flashing...
-- entirely from player-visible facts... It could NOT legitimately expose
-- 'Solon's hunger_timer is 34,261'." So every tripwire/status output below
-- reads unit.counters2.hunger_timer/thirst_timer internally (the ONLY way to
-- compute the threshold at all) but returns only the derived, player-legal
-- CATEGORY the game's own status flash would show ("hungry"/"starving",
-- "thirsty"/"dehydrated"), never the raw tick integer. Tagged
-- knowledge_scope: player_derivable throughout this file for exactly this
-- reason -- an internal read producing a safe, bounded, player-legal output,
-- the same shape df-overseer-threat.lua's own find_threats already uses.
--
-- ============================================================================
-- SOURCING THE CRITICAL THRESHOLDS. Per the handoff's own instruction
-- ("source the hunger/thirst critical values... or make it a required
-- argument"): DEFAULT_HUNGER_CRITICAL (75000) and DEFAULT_THIRST_CRITICAL
-- (50000) are read directly from this install's own shipped
-- hack/scripts/full-heal.lua, whose is_in_dire_need() hard-codes
-- `hunger_timer > 75000 or thirst_timer > 50000 or sleepiness_timer >
-- 150000`, cross-validated against the DF wiki's own documented
-- "Starving"/"Dehydrated" status-flash thresholds
-- (research/2026-09-16-food-clock-and-farm-lead-time.md ss1, "these numbers
-- are not a guess"). DEFAULT_WARNING_HUNGER (50000, "Hungry" flash) and
-- DEFAULT_WARNING_THIRST (25000, "Thirsty" flash) are the same source's
-- earlier, non-critical flash thresholds, used only by vitals.summary's
-- warning_count, not by the tripwire's pause decision. All four are
-- arguments with these sourced defaults, never bare constants a caller
-- cannot override.
--
-- ============================================================================
-- WHY fort.quicksave DOES NOT LIVE IN THIS FILE, AND WHY IT NEVER BLOCKS
-- WAITING FOR CONFIRMATION. See df-overseer-fort.lua's own header: the short
-- version is docs/AGENT-ARCHITECTURE.md ss6's own finding that a DFHack script
-- call holds the suspend lock for its whole duration, and
-- research/2026-09-11-quicksave-silent-noop.md's finding that quicksave can
-- take 45-80+ real seconds to actually land because it is gated on a render
-- pass -- so a script that busy-waited for that confirmation would itself be
-- the thing preventing the render pass the save depends on. A tool must
-- never hold the suspend lock across an indeterminate wait.
--
-- ============================================================================
-- WHY THE LATCH IS A FILE, NOT A LUA GLOBAL. Same reasoning as
-- df-overseer-sampler.lua's own header: DFHack's script loader reuses one
-- persistent `env` table per script PATH across separate `dfhack-run`
-- invocations (confirmed by reading hack/lua/dfhack.lua's
-- run_script_with_env: `scripts[file].env` is cached and re-used, only the
-- top-level chunk is re-executed), so a plain global WOULD survive across
-- CLI calls within one process -- but it would also wrongly survive a world
-- unload/reload (a different fort loading in the same DFHack process), which
-- repeat-util.lua's own onStateChange handler already guards its `repeating`
-- table against but a bare global here would not. `arm` therefore always
-- resets the latch file to "no latch" before scheduling, so a fresh arm is
-- always a clean start; the closure repeat-util holds after arm (the actual
-- check function) is itself killed automatically on world unload, since
-- repeat-util clears `repeating` on SC_WORLD_UNLOADED. NAMED GAP: if a world
-- unloads and reloads while armed WITHOUT anyone calling arm/disarm/clear in
-- between, the latch file could still show a stale latch from the previous
-- load until the next arm. Not fixed here; say so in the deploy checklist.
--
-- ============================================================================
-- WHY PAUSE FREEZES THE WATCHER TOO, AND WHY THAT IS THE POINT, NOT A BUG.
-- The tripwire's periodic check is scheduled in TICKS
-- (repeat-util/dfhack.timeout), and ticks stop advancing while the game is
-- paused. So once a trip pauses the fort, the same scheduled check simply
-- stops firing -- no extra "already latched, skip" bookkeeping is needed to
-- stop it re-tripping while paused. If something bypasses this file's own
-- `resume` guard (a human at the UI/VNC unpausing directly), ticks resume,
-- the watcher fires again, and if the ORIGINAL condition (or a new one) is
-- still true it re-pauses and re-latches -- a real, deliberate defense in
-- depth, not an oversight. The check function still reads the latch file
-- first and leaves an existing, unresolved latch's reason untouched (first
-- cause wins), only re-asserting the pause.

local json = require('json')
local repeatUtil = require('repeat-util')
local threat_mod = reqscript('df-overseer-threat')
local ledger_mod = reqscript('df-overseer-ledger')
local announcement_levels = reqscript('df-overseer-announcement-levels')

local TRIPWIRE_NAME = "overseer-tripwire"
local STATE_DIR = "dfhack-config/overseer-clock"
local LATCH_FILE = STATE_DIR .. "/tripwire_latch.json"
-- Advisory: the "slow" tier's own record, NEVER blocks resume (clock_resume
-- only ever checks LATCH_FILE, see below) -- a purely informational note the
-- conductor can read off clock_status while deciding who to wake. Kept
-- separate from the latch file on purpose: the two have different
-- lifecycles (a latch is cleared once acknowledged; this is just
-- overwritten by the next slow-tier trip).
local ADVISORY_FILE = STATE_DIR .. "/tripwire_advisory.json"

local MIN_FPS = 1
-- Arbitrary, generous ceiling well above any base_fps/think_fps value this
-- project configures (100/10, docs/AGENT-LOOP.md ss2) -- a sanity guard
-- against a typo (a missing decimal point, an extra zero), not a researched
-- engine limit.
local MAX_FPS = 1000

-- Sourced above: hack/scripts/full-heal.lua's is_in_dire_need(), cross-
-- validated against the DF wiki's status-flash thresholds
-- (research/2026-09-16-food-clock-and-farm-lead-time.md).
local DEFAULT_HUNGER_CRITICAL = 75000   -- "Starving" flash
local DEFAULT_THIRST_CRITICAL = 50000   -- "Dehydrated" flash

-- Sourced: docs/AGENT-LOOP.md ss2's own "Three levels" table, "Slowed:
-- think_fps, starting value 10". Used only for the slow-tier wildlife/
-- invader case (df-overseer-threat.lua's classify_tier) -- the announcement
-- tripwire's own slow ids (df-overseer-announcement-levels.lua) are
-- deliberately NOT acted on here at all, see that file's header and this
-- stream's Result.
local DEFAULT_THINK_FPS = 10

-- Default periodic-check cadence and the threat-scan cadence multiple.
-- Reasoned, not sourced: getCitizens()+two numeric comparisons per citizen
-- is cheap enough to run every 100 ticks (about 1s of real time at
-- base_fps=100); find_threats() is heavier (iterates world.units.active plus
-- a landmark resolution per candidate), so it runs once every
-- THREAT_CHECK_EVERY_N vitals checks by default -- "run it at a lower
-- cadence and say so", per the handoff.
local DEFAULT_CHECK_INTERVAL_TICKS = 100
local DEFAULT_THREAT_CHECK_EVERY_N = 10

-- ----------------------------------------------------------------------------
-- Small helpers

local function ensure_state_dir()
  if not dfhack.filesystem.isdir(STATE_DIR) then
    dfhack.filesystem.mkdir_recursive(STATE_DIR)
  end
end

local function read_tick()
  local ok, cur_year, cur_year_tick = pcall(function()
    return df.global.cur_year, df.global.cur_year_tick
  end)
  if not ok then
    return false, nil, nil, nil
  end
  return true, cur_year, cur_year_tick, cur_year * 403200 + cur_year_tick
end

-- {} on a missing/unreadable file (json.decode_file's own documented
-- fallback), read as "no latch".
local function read_latch()
  ensure_state_dir()
  local ok, data = pcall(json.decode_file, LATCH_FILE)
  if not ok or type(data) ~= "table" or not data.reason then
    return nil
  end
  return data
end

local function write_latch(latch)
  ensure_state_dir()
  json.encode_file(latch, LATCH_FILE)
end

local function clear_latch_file()
  ensure_state_dir()
  json.encode_file({}, LATCH_FILE)
end

-- Advisory (slow tier): nil on a missing/unreadable/empty file, same
-- fallback discipline as read_latch. Never gates resume -- clock_resume
-- below only ever checks read_latch().
local function read_advisory()
  ensure_state_dir()
  local ok, data = pcall(json.decode_file, ADVISORY_FILE)
  if not ok or type(data) ~= "table" or not data.reason then
    return nil
  end
  return data
end

local function write_advisory(advisory)
  ensure_state_dir()
  json.encode_file(advisory, ADVISORY_FILE)
end

-- ----------------------------------------------------------------------------
-- set-speed FPS

function clock_set_speed(fps)
  local capnum = tonumber(fps)
  if not capnum then
    return { ok = false, error = "FPS must be a number, got " .. tostring(fps) }
  end
  if capnum < MIN_FPS or capnum > MAX_FPS then
    return { ok = false, error = string.format(
      "FPS %s outside sane range [%d, %d]", tostring(capnum), MIN_FPS, MAX_FPS) }
  end
  local old_fps = df.global.enabler.fps
  df.global.enabler.fps = capnum
  -- Mirrors setfps.lua's own write exactly (hack/scripts/setfps.lua),
  -- confirmed present at this install's version.
  local ok_gfps, gfps = pcall(function() return df.global.enabler.gfps end)
  if ok_gfps and type(gfps) == "number" and gfps > 0 then
    df.global.enabler.fps_per_gfps = capnum / gfps
  end
  return { ok = true, old_fps = old_fps, new_fps = df.global.enabler.fps }
end

-- ----------------------------------------------------------------------------
-- pause / resume

function clock_pause()
  dfhack.world.SetPauseState(true)
  return { ok = true, paused = dfhack.world.ReadPauseState() }
end

function clock_resume()
  local latch = read_latch()
  if latch then
    return {
      ok = false,
      error = "refused: a tripwire is latched (reason=" .. tostring(latch.reason)
        .. "); call clock.clear first",
      tripwire = latch,
    }
  end
  dfhack.world.SetPauseState(false)
  return { ok = true, paused = dfhack.world.ReadPauseState() }
end

-- ----------------------------------------------------------------------------
-- status

function clock_status()
  local ok_tick, cur_year, cur_year_tick, abs_tick = read_tick()
  return {
    paused = dfhack.world.ReadPauseState(),
    fps = df.global.enabler.fps,
    cur_year = ok_tick and cur_year or nil,
    cur_year_tick = ok_tick and cur_year_tick or nil,
    abs_tick = ok_tick and abs_tick or nil,
    armed = repeatUtil.isScheduled(TRIPWIRE_NAME),
    tripwire = read_latch(),
    -- Added handoffs/2026-09-23-attention-tiers-ingame.md: the most recent
    -- slow-tier trip, if any -- purely informational, never blocks resume
    -- (see read_advisory's own comment).
    advisory = read_advisory(),
  }
end

-- ----------------------------------------------------------------------------
-- The periodic check. A closure over arm's own local config/snapshot, held
-- alive by repeat-util's own persistent module table (see header) -- never
-- itself reloaded when this FILE is reloaded for a later CLI call.

local function citizen_ids_now()
  local ok, citizens = pcall(dfhack.units.getCitizens, true)
  if not ok or not citizens then
    return nil, {}
  end
  local ids = {}
  for _, u in ipairs(citizens) do
    local ok_id, uid = pcall(function() return u.id end)
    if ok_id and uid ~= nil then
      ids[uid] = true
    end
  end
  return citizens, ids
end

local function hunger_status(hunger_timer, warning, critical)
  if hunger_timer > critical then return "starving" end
  if hunger_timer > warning then return "hungry" end
  return "fine"
end

local function thirst_status(thirst_timer, warning, critical)
  if thirst_timer > critical then return "dehydrated" end
  if thirst_timer > warning then return "thirsty" end
  return "fine"
end

-- Bounded initial cursor for the announcement tripwire (step 4 below):
-- the current max report id at arm time, so a fresh arm never retroactively
-- pauses on history already in world.status.reports -- same "clean start on
-- arm" discipline the death check's known_ids and the latch file already
-- have (see header, "why arm always resets the latch first").
local function current_max_report_id()
  local ok, reports = pcall(function() return df.global.world.status.reports end)
  if not ok or not reports or #reports == 0 then
    return 0
  end
  local ok_id, id = pcall(function() return reports[#reports - 1].id end)
  return (ok_id and id) or 0
end

-- Bounded scan (docs/TRAPS.md): walks backward from the newest report only
-- until it reaches one at or before last_seen_id -- cost is proportional to
-- how many NEW reports arrived since the last check (bounded by how often
-- this tripwire fires), never the full report history, same technique
-- df-overseer-diff.lua's own onReport/recent_combat already use.
local function new_pause_reports(last_seen_id)
  local ok, reports = pcall(function() return df.global.world.status.reports end)
  if not ok or not reports then
    return {}, last_seen_id
  end
  local hits = {}
  local max_id = last_seen_id
  for i = #reports - 1, 0, -1 do
    local rep = reports[i]
    if rep.id <= last_seen_id then
      break
    end
    if rep.id > max_id then
      max_id = rep.id
    end
    local ok_pause, is_pause = pcall(announcement_levels.is_pause_report, rep.type)
    if ok_pause and is_pause then
      table.insert(hits, 1, rep)
    end
  end
  return hits, max_id
end

local function make_check_fn(hunger_critical, thirst_critical, threat_check_every_n, think_fps)
  local known_ids = select(2, citizen_ids_now())
  local fire_count = 0
  local last_seen_report_id = current_max_report_id()

  return function()
    fire_count = fire_count + 1

    -- First cause wins: an unresolved latch means a human/conductor has not
    -- yet cleared it. Just re-assert pause (defense in depth, see header)
    -- and skip re-deriving a new reason.
    if read_latch() then
      dfhack.world.SetPauseState(true)
      return
    end

    local ok_tick, _, _, abs_tick = read_tick()
    local tick_now = ok_tick and abs_tick or -1

    -- 1. Death since the last check (cheap: a set-membership diff).
    -- ITEM 5 OF handoffs/2026-09-23-attention-tiers-ingame.md, CHECKED AND
    -- REPORTED: research/2026-09-23-announcement-severity.md S:A.3 says "the
    -- existing death tripwire fires on the raw DFHack UNIT_DEATH eventful
    -- event", tagged omniscient by research/2026-09-16-player-visibility.md.
    -- Read against the ACTUAL code (not the design doc's paraphrase) this
    -- session: this check has never used UNIT_DEATH -- it is, and always
    -- was, a dfhack.units.getCitizens() roster diff, i.e. "is a citizen who
    -- was on MY fort's own citizen list a moment ago no longer on it" --
    -- already scoped to the player's own fort roster (a real screen a
    -- vanilla player has), not the omniscient world.units.active-wide event.
    -- No change made here for that reason: there is no omniscience to fix.
    -- DUAL-ARMED FOR FREE by step 4 below instead: CITIZEN_DEATH (id 106)
    -- and PET_DEATH (id 107) are both `pause`-level in
    -- research/data/2026-09-23-announcement-severity.yaml, so they are
    -- already members of df-overseer-announcement-levels.lua's
    -- PAUSE_REPORT_IDS -- step 4's own announcement tripwire independently
    -- pauses on either, a player-visible, DF-announced corroborating signal
    -- alongside this roster diff, with no separate wiring needed. This also
    -- adds coverage this roster diff structurally cannot have: PET_DEATH
    -- (getCitizens() only ever lists dwarves, never animals).
    local citizens, current_ids = citizen_ids_now()
    local missing = {}
    for uid, _ in pairs(known_ids) do
      if not current_ids[uid] then
        table.insert(missing, uid)
      end
    end
    known_ids = current_ids
    if #missing > 0 then
      write_latch({
        reason = "death",
        tick = tick_now,
        detail = {
          missing_citizen_count = #missing,
          missing_citizen_ids = missing,
          caveat = "a citizen can also leave this set by going insane, not only by "
            .. "dying (dfhack.units.getCitizens excludes insane citizens by default); "
            .. "confirm the cause via a live check before treating this as certain",
        },
      })
      dfhack.world.SetPauseState(true)
      return
    end

    -- 2. Hunger/thirst past critical, over the SAME citizen list (no second
    -- bounded read).
    local worst = nil
    for _, u in ipairs(citizens) do
      local ok_h, h = pcall(function() return u.counters2.hunger_timer end)
      local ok_t, t = pcall(function() return u.counters2.thirst_timer end)
      if ok_h and type(h) == "number" and h > hunger_critical then
        worst = { unit_id = u.id, status = "hunger:starving" }
        break
      end
      if ok_t and type(t) == "number" and t > thirst_critical then
        worst = { unit_id = u.id, status = "thirst:dehydrated" }
        break
      end
    end
    if worst then
      write_latch({
        reason = (worst.status:match("^hunger") and "hunger_critical" or "thirst_critical"),
        tick = tick_now,
        detail = { unit_id = worst.unit_id, status = worst.status:match(":(.+)$") },
      })
      dfhack.world.SetPauseState(true)
      return
    end

    -- 3. Hostile reachable, at a lower cadence (see header rationale).
    -- THREE TIERS, handoffs/2026-09-23-attention-tiers-ingame.md item 1
    -- (research/2026-09-23-wildlife-threat-classes.md S:E1, taken as
    -- written): every candidate find_threats returns now carries its own
    -- `tier` (df-overseer-threat.lua's classify_tier). This used to pause
    -- on ANY candidate at all -- the failure a kea 68 tiles away exposed
    -- (evals/live/2026-09-23-office-and-first-real-build/). Now:
    --   pause tier       -> latch and pause, exactly as before.
    --   slow tier        -> NOT paused. FPS set to think_fps and an
    --                       ADVISORY (not the latch) written -- the
    --                       conductor's own triage (a later stream) decides
    --                       who to wake from it, per docs/AGENT-LOOP.md ss2.
    --   record_only tier -> nothing here at all; every candidate this scan
    --                       saw is written to the ledger below regardless
    --                       of tier, so a repeated harmless visitor becomes
    --                       a pattern, not silence.
    -- LEDGER WRITE ORDER: every candidate's tier was computed by find_threats
    -- against the ledger's PRIOR state (a read-only lookup,
    -- ledger_closest_distance); the record() calls below happen strictly
    -- AFTER that computation, for every scan, so a single scan's own
    -- candidates never see each other's fresh writes mid-computation.
    if fire_count % threat_check_every_n == 0 then
      local ok_scan, threats = pcall(threat_mod.find_threats)
      if ok_scan and threats then
        for _, candidate in ipairs(threats) do
          pcall(ledger_mod.record, candidate.race, tick_now, candidate.distance_tiles, "present")
        end

        if #threats > 0 then
          local top = threats[1]
          if top.tier == "pause" then
            write_latch({
              reason = "hostile_reachable",
              tick = tick_now,
              detail = {
                race = top.race,
                near_landmark = top.near_landmark,
                direction = top.direction,
                distance_tiles = top.distance_tiles,
                tier = top.tier,
                tier_reasons = top.tier_reasons,
                why = top.why,
              },
            })
            dfhack.world.SetPauseState(true)
            return
          elseif top.tier == "slow" then
            clock_set_speed(think_fps)
            write_advisory({
              reason = "hostile_slow",
              tick = tick_now,
              detail = {
                race = top.race,
                near_landmark = top.near_landmark,
                direction = top.direction,
                distance_tiles = top.distance_tiles,
                tier = top.tier,
                tier_reasons = top.tier_reasons,
                why = top.why,
              },
            })
          end
          -- record_only: already written to the ledger above; nothing else
          -- to do here.
        end
      end
    end

    -- 4. A newly-arrived announcement of pause severity. A SEPARATE
    -- tripwire (handoffs/2026-09-23-attention-tiers-ingame.md item 2), not
    -- folded into step 3's hostile-reachable check above -- a fixed-id
    -- lookup over the report stream is a different mechanism than a
    -- reachability/raw-tag read over live units. Table generated from
    -- research/data/2026-09-23-announcement-severity.yaml
    -- (scripts/gen_announcement_pause_slow.py), 25 ids. The 23 `slow` ids
    -- in the same classification are deliberately NOT read here at all --
    -- see df-overseer-announcement-levels.lua's own header and this
    -- stream's Result for the field shape exposed to the sibling conductor
    -- stream instead. Bounded scan: new_pause_reports only walks reports
    -- newer than the last check, never the full history (docs/TRAPS.md).
    local pause_reports, new_max_id = new_pause_reports(last_seen_report_id)
    last_seen_report_id = new_max_id
    if #pause_reports > 0 then
      local rep = pause_reports[1]
      write_latch({
        reason = "announcement",
        tick = tick_now,
        detail = {
          type_id = rep.type,
          type_name = df.announcement_type[rep.type] or tostring(rep.type),
          report_id = rep.id,
          new_pause_report_count = #pause_reports,
        },
      })
      dfhack.world.SetPauseState(true)
      return
    end
  end
end

-- ----------------------------------------------------------------------------
-- arm [HUNGER_CRITICAL THIRST_CRITICAL CHECK_INTERVAL_TICKS THREAT_CHECK_EVERY_N THINK_FPS]

function clock_arm(hunger_critical, thirst_critical, check_interval_ticks, threat_check_every_n, think_fps)
  hunger_critical = tonumber(hunger_critical) or DEFAULT_HUNGER_CRITICAL
  thirst_critical = tonumber(thirst_critical) or DEFAULT_THIRST_CRITICAL
  check_interval_ticks = tonumber(check_interval_ticks) or DEFAULT_CHECK_INTERVAL_TICKS
  threat_check_every_n = tonumber(threat_check_every_n) or DEFAULT_THREAT_CHECK_EVERY_N
  think_fps = tonumber(think_fps) or DEFAULT_THINK_FPS

  if hunger_critical <= 0 or thirst_critical <= 0 then
    return { ok = false, error = "hunger_critical/thirst_critical must be positive tick counts" }
  end
  if check_interval_ticks <= 0 or threat_check_every_n <= 0 then
    return { ok = false, error = "check_interval_ticks/threat_check_every_n must be positive" }
  end
  if think_fps < MIN_FPS or think_fps > MAX_FPS then
    return { ok = false, error = string.format(
      "think_fps %s outside sane range [%d, %d]", tostring(think_fps), MIN_FPS, MAX_FPS) }
  end

  clear_latch_file()
  write_advisory({})
  local check_fn = make_check_fn(hunger_critical, thirst_critical, threat_check_every_n, think_fps)
  -- scheduleEvery cancels any existing schedule of the same name first
  -- (repeat-util.lua's own scheduleEvery), so re-arming is safe and clean.
  repeatUtil.scheduleEvery(TRIPWIRE_NAME, check_interval_ticks, "ticks", check_fn)

  return {
    ok = true,
    armed = true,
    hunger_critical = hunger_critical,
    thirst_critical = thirst_critical,
    check_interval_ticks = check_interval_ticks,
    threat_check_every_n = threat_check_every_n,
    think_fps = think_fps,
  }
end

function clock_disarm()
  local was_armed = repeatUtil.isScheduled(TRIPWIRE_NAME)
  repeatUtil.cancel(TRIPWIRE_NAME)
  return { ok = true, was_armed = was_armed, armed = repeatUtil.isScheduled(TRIPWIRE_NAME) }
end

function clock_clear()
  local had_latch = read_latch() ~= nil
  clear_latch_file()
  return { ok = true, had_latch = had_latch }
end

-- ----------------------------------------------------------------------------
-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "set-speed" then
  print(json.encode(clock_set_speed(args[2])))
elseif cmd == "pause" then
  print(json.encode(clock_pause()))
elseif cmd == "resume" then
  print(json.encode(clock_resume()))
elseif cmd == "status" then
  print(json.encode(clock_status()))
elseif cmd == "arm" then
  print(json.encode(clock_arm(args[2], args[3], args[4], args[5], args[6])))
elseif cmd == "disarm" then
  print(json.encode(clock_disarm()))
elseif cmd == "clear" then
  print(json.encode(clock_clear()))
else
  print("usage: df-overseer-clock <set-speed FPS|pause|resume|status|arm [HUNGER_CRITICAL THIRST_CRITICAL CHECK_INTERVAL_TICKS THREAT_CHECK_EVERY_N THINK_FPS]|disarm|clear>")
end
