-- df-overseer-pause.lua
--@module = true
--
-- handoffs/2026-10-05-pause-safety.md. Why is the fort paused or stuck, and
-- can a player-equivalent action clear it? The game-side half of the
-- conductor's pause watchdog (conductor/pause_watch.py holds the decision
-- table; this file only reads and dismisses).
--
--   why              -- read: why the game is paused or not advancing
--   dismiss [MAX]    -- mutate: close pending popups a player could close
--
-- WHAT THIS FILE ESTABLISHED (read-only live probes, VM 103, 2026-10-05):
-- the game's own announcement flags are readable at
-- df.global.d_init.announcements.flags[type] (DO_MEGA, PAUSE, ALERT, ...).
-- FORT_POSITION_SUCCESSION is DO_MEGA, i.e. a mega popup; 35 types are, and
-- on this install none carries the PAUSE flag. A mega popup is queued in
-- df.global.world.status.popups and renders inside viewscreen_dwarfmodest,
-- so neither the viewscreen type nor the focus string can see it: the
-- vector must be read. The popup carries no announcement type; the type is
-- found from the newest report of a DO_MEGA/PAUSE type at the current tick.
--
-- NEVER RESUMES, NEVER CLEARS A LATCH. dismiss only closes a box (what a
-- player does with the Okay button) and records what it said first. Whether
-- to resume is the conductor's decision, made with this file's `why` and
-- the harmless list in conductor/pause_policy.yaml; clock.resume itself
-- still refuses while a tripwire is latched.
--
-- NO ARMOK: everything read here is on screen for a player (the popup's
-- text, the report text, the screen type). dismiss uses the same mouse
-- click a player would, located by scanning the character buffer for the
-- button's own text (the technique df-overseer-ui.lua already uses; the
-- scan never leaves this script).
--
-- WHICH POPUPS ARE SAFE IS A LIST, NOT BRANCHES: POPUP_KINDS below. Each
-- kind has a detector (how many are pending, what they say) and an ordered
-- list of dismiss strategies (data: a strategy name and its argument), each
-- strategy implemented once in STRATEGIES. A new kind is a table entry.
-- A strategy with `enabled = false` is documented and inert.
--
-- UNVERIFIED LIVE as of this stream (offline build): which strategy
-- actually closes a real mega popup on this install. The deploy plan's
-- supervised test provokes a harmless one (dfhack.gui.showPopupAnnouncement,
-- the same push the vanilla BOX path performs) on the paused fort and
-- records which strategy cleared it; the strategy order below is the
-- hypothesis, to be reordered by that result.
--
-- BOUNDED READS ONLY (docs/TRAPS.md): popups is a vector that is almost
-- always empty; the report scan walks backward from the newest report and
-- stops at MAX_REPORT_SCAN or the time window, whichever is first; the
-- character-buffer scan is one screen.

local json = require('json')
local gui = require('gui')

local TICKS_PER_YEAR = 403200

local DEFAULT_WINDOW_TICKS = 1200   -- one game day: reports this recent explain a pause
local MAX_REPORT_SCAN = 60
local MAX_REPORTS_OUT = 8
local MAX_TEXT = 240
local DEFAULT_DISMISS_MAX = 5

local ORDINARY_VIEWSCREEN = "viewscreen_dwarfmodest"

-- ----------------------------------------------------------------------------
-- small safe helpers

local function trunc(s)
  s = tostring(s or "")
  s = s:gsub("[%c]+", " ")
  if #s > MAX_TEXT then s = s:sub(1, MAX_TEXT) .. "..." end
  return s
end

local function utf8_text(s)
  local ok, textutil = pcall(reqscript, 'df-overseer-textutil')
  if ok and textutil and textutil.to_utf8 then
    local ok2, out = pcall(textutil.to_utf8, s)
    if ok2 and out then return out end
  end
  return s
end

local function vec_len(v)
  local ok, n = pcall(function() return #v end)
  return ok and n or 0
end

-- popup_message.text / report.text may be a plain string or a vector of
-- strings; join either way.
local function text_of(obj)
  local ok, t = pcall(function() return obj.text end)
  if not ok or t == nil then return "" end
  if type(t) == "string" then return t end
  local parts = {}
  local ok2 = pcall(function()
    for i = 0, #t - 1 do parts[#parts + 1] = tostring(t[i]) end
  end)
  if not ok2 then return tostring(t) end
  return table.concat(parts, " ")
end

local function viewscreen_type()
  local ok, t = pcall(function() return tostring(dfhack.gui.getDFViewscreen(true)._type) end)
  if not ok then return nil end
  return (t:gsub("^<type: ", ""):gsub(">$", ""))
end

local function focus_string()
  local ok, f = pcall(function() return table.concat(dfhack.gui.getCurFocus(true), "|") end)
  return ok and f or nil
end

local function help_open()
  local ok, o = pcall(function() return df.global.game.main_interface.help.open end)
  return ok and o == true or false
end

local function current_abs_tick()
  local ok, t = pcall(function() return df.global.cur_year * TICKS_PER_YEAR + df.global.cur_year_tick end)
  return ok and t or nil
end

-- ----------------------------------------------------------------------------
-- character-buffer text scan (df-overseer-ui.lua's technique): locate a
-- button by its own text, never by a guessed coordinate.

local function find_text(target)
  local w, h = dfhack.screen.getWindowSize()
  for y = 0, h - 1 do
    local line = {}
    for x = 0, w - 1 do
      local tile = dfhack.screen.readTile(x, y)
      local ch = tile and tile.ch
      line[#line + 1] = (ch and ch >= 32 and ch < 127) and string.char(ch) or " "
    end
    local s, e = table.concat(line):find(target, 1, true)
    if s then return y, s - 1, e - 1 end
  end
  return nil
end

-- ----------------------------------------------------------------------------
-- POPUP KINDS: the data. detect() returns (pending_count, {texts}).

local function detect_mega()
  local ok, popups = pcall(function() return df.global.world.status.popups end)
  if not ok or not popups then return 0, {} end
  local texts = {}
  for i = 0, vec_len(popups) - 1 do
    if #texts >= MAX_REPORTS_OUT then break end
    texts[#texts + 1] = trunc(utf8_text(text_of(popups[i])))
  end
  return vec_len(popups), texts
end

local function detect_help()
  if help_open() then return 1, { "help or tutorial box" } end
  return 0, {}
end

POPUP_KINDS = {
  {
    id = "mega",
    detect = detect_mega,
    -- The wiki's own description of the BOX/DO_MEGA popup: "requiring a
    -- click on the Okay button to close it ... the button says More and
    -- displays the next box" (research/2026-10-01-unattended-popups.md).
    strategies = {
      { name = "click_text", arg = "Okay" },
      { name = "click_text", arg = "More" },
      -- Inert on purpose: removing the entry from the vector is not what a
      -- player does, and is unverified. Documented for the live test.
      { name = "pop_front", enabled = false },
    },
  },
  {
    id = "tutorial_help",
    detect = detect_help,
    strategies = {
      { name = "help_close" },
    },
  },
}

-- ----------------------------------------------------------------------------
-- Strategies: each returns true when it did something (verification of the
-- effect is the caller's, by re-running the detector).

STRATEGIES = {
  click_text = function(arg)
    local row, cs, ce = find_text(arg)
    if not row then return false, "text not found: " .. tostring(arg) end
    df.global.gps.mouse_x = math.floor((cs + ce) / 2)
    df.global.gps.mouse_y = row
    gui.simulateInput(dfhack.gui.getCurViewscreen(), '_MOUSE_L')
    return true, "clicked " .. tostring(arg)
  end,
  help_close = function()
    df.global.game.main_interface.help.open = false
    return true, "closed help"
  end,
  pop_front = function()
    local popups = df.global.world.status.popups
    if vec_len(popups) == 0 then return false, "no popup" end
    popups:erase(0)
    return true, "erased the first popup entry"
  end,
}

-- ----------------------------------------------------------------------------
-- why

local function flags_for(rtype)
  local ok, fl = pcall(function() return df.global.d_init.announcements.flags[rtype] end)
  if not ok or not fl then return nil end
  local out = {}
  for _, name in ipairs({ "DO_MEGA", "PAUSE", "ALERT", "RECENTER" }) do
    local ok2, v = pcall(function() return fl[name] end)
    if ok2 and v then out[#out + 1] = name end
  end
  return out
end

local function type_name(rtype)
  local ok, n = pcall(function() return df.announcement_type[rtype] end)
  return ok and n and tostring(n) or tostring(rtype)
end

-- Reports at or just before the current tick whose announcement type carries
-- DO_MEGA or PAUSE: the candidate causes of a game-forced pause.
local function recent_flagged_reports(window_ticks)
  local out = {}
  local ok, reports = pcall(function() return df.global.world.status.reports end)
  if not ok or not reports then return out end
  local now = current_abs_tick()
  local n = vec_len(reports)
  local scanned = 0
  for i = n - 1, 0, -1 do
    scanned = scanned + 1
    if scanned > MAX_REPORT_SCAN or #out >= MAX_REPORTS_OUT then break end
    local rep = reports[i]
    local ok_t, rtick = pcall(function() return rep.year * TICKS_PER_YEAR + rep.time end)
    if now and ok_t and (now - rtick) > window_ticks then break end
    local flags = flags_for(rep.type)
    if flags and (#flags > 0) then
      local hit = false
      for _, f in ipairs(flags) do if f == "DO_MEGA" or f == "PAUSE" then hit = true end end
      if hit then
        out[#out + 1] = {
          id = rep.id, type = type_name(rep.type), flags = flags,
          tick = ok_t and rtick or nil, text = trunc(utf8_text(text_of(rep))),
        }
      end
    end
  end
  return out
end

local function popup_report()
  local kinds, total = {}, 0
  for _, kind in ipairs(POPUP_KINDS) do
    local count, texts = kind.detect()
    kinds[#kinds + 1] = { kind = kind.id, pending = count, texts = texts }
    total = total + count
  end
  return kinds, total
end

function pause_why(window_ticks)
  local window = tonumber(window_ticks) or DEFAULT_WINDOW_TICKS
  local clock = reqscript('df-overseer-clock')
  local status = clock.clock_status()
  local kinds, popups_total = popup_report()
  local vs = viewscreen_type()
  local paused = dfhack.world.ReadPauseState()
  local reports = recent_flagged_reports(window)

  local cause
  if status.tripwire then
    cause = "tripwire"
  elseif vs ~= nil and vs ~= ORDINARY_VIEWSCREEN then
    cause = "modal_viewscreen"
  elseif popups_total > 0 then
    cause = "popup"
  elseif paused and #reports > 0 then
    cause = "announcement"
  elseif paused then
    cause = "plain_pause"
  else
    cause = "running"
  end

  return {
    ok = true,
    paused = paused,
    cause = cause,
    tripwire = status.tripwire,
    abs_tick = status.abs_tick,
    cur_year_tick = status.cur_year_tick,
    viewscreen_type = vs,
    focus = focus_string(),
    popups_pending = popups_total,
    popups = kinds,
    recent_reports = reports,
    window_ticks = window,
  }
end

-- ----------------------------------------------------------------------------
-- dismiss

local function strategy_enabled(s)
  return s.enabled ~= false and STRATEGIES[s.name] ~= nil
end

function pause_dismiss(max_boxes)
  local cap = tonumber(max_boxes) or DEFAULT_DISMISS_MAX
  if cap < 1 then
    return { ok = false, error = "MAX must be at least 1" }
  end
  local done, attempts = {}, {}
  local ok_all = true
  for _ = 1, cap do
    local progressed = false
    for _, kind in ipairs(POPUP_KINDS) do
      local before, texts = kind.detect()
      if before > 0 then
        local cleared = false
        for _, s in ipairs(kind.strategies) do
          if strategy_enabled(s) then
            local ok_run, did, note = pcall(STRATEGIES[s.name], s.arg)
            attempts[#attempts + 1] = {
              kind = kind.id, strategy = s.name, arg = s.arg,
              did = ok_run and did or false, note = ok_run and note or tostring(did),
            }
            if ok_run and did then
              local after = kind.detect()
              if after < before then
                done[#done + 1] = {
                  kind = kind.id, strategy = s.name, said = texts[1], before = before, after = after,
                }
                cleared, progressed = true, true
                break
              end
            end
          end
        end
        if not cleared then ok_all = false end
      end
    end
    if not progressed then break end
  end
  local remaining = select(2, popup_report())
  return {
    ok = ok_all and remaining == 0,
    dismissed = done,
    attempts = attempts,
    remaining = remaining,
    note = (remaining > 0) and "a popup is still pending; nothing was resumed or forced" or nil,
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "why" then
  print(json.encode(pause_why(args[2])))
elseif cmd == "dismiss" then
  print(json.encode(pause_dismiss(args[2])))
else
  print("usage: df-overseer-pause <why [WINDOW_TICKS]|dismiss [MAX]>")
end
