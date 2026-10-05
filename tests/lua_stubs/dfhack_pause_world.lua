-- A fake DFHack world for tests/test_pause_lua_logic.py:
-- df-overseer-pause.lua's `why` and `dismiss` (handoffs/2026-10-05-pause-safety.md).
--
-- Scope, honestly: this models only the surfaces the script reads, with the
-- field names and the 0-based vector shape confirmed by read-only probes of
-- the live install (popup_message = text/color/bright/portrait_hfid;
-- d_init.announcements.flags[type].DO_MEGA/PAUSE; world.status.popups and
-- .reports). It does NOT model what the real game does when a button is
-- clicked: the fake closes the front popup when the click lands on the
-- character-buffer cell where an "Okay" or "More" label was drawn, which is
-- the behaviour the script ASSUMES. Whether a real mega popup closes that
-- way is exactly what the supervised live test settles.

dfhack_flags = { module = true }

package.loaded["json"] = { encode = function(v) return v end }

-- 0-based vector with a real length, like a DFHack stl-vector.
local function vector(items)
  local v = { _n = 0 }
  local mt = {}
  mt.__len = function(self) return rawget(self, "_n") end
  mt.__index = function(self, k)
    if k == "erase" then
      return function(this, idx)
        local n = rawget(this, "_n")
        for i = idx, n - 2 do rawset(this, i, rawget(this, i + 1)) end
        rawset(this, n - 1, nil)
        rawset(this, "_n", n - 1)
      end
    end
    return nil
  end
  setmetatable(v, mt)
  for _, it in ipairs(items or {}) do
    rawset(v, v._n, it)
    rawset(v, "_n", v._n + 1)
  end
  return v
end

local ANN = { "FORT_POSITION_SUCCESSION", "MEGABEAST_ARRIVAL", "MIGRANT_ARRIVAL", "BIRTH_CITIZEN" }
local announcement_type = {}
for i, name in ipairs(ANN) do
  announcement_type[i - 1] = name
  announcement_type[name] = i - 1
end

WORLD = {
  paused = true,
  viewscreen = "viewscreen_dwarfmodest",
  focus = { "dwarfmode/Default" },
  help_open = false,
  cur_year = 100,
  cur_year_tick = 5000,
  tripwire = nil,
  clicks = {},
  screen_labels = {},   -- { {text=, x=, y=} } drawn on the character buffer
  buttons_close_popup = true,  -- test hook: false models a click that does nothing
}

local flags = {
  [0] = { DO_MEGA = true },
  [1] = { DO_MEGA = true },
  [2] = {},
  [3] = {},
}

df = {
  announcement_type = announcement_type,
  global = {
    cur_year = 0, cur_year_tick = 0,
    gps = { mouse_x = 0, mouse_y = 0 },
    d_init = { announcements = { flags = flags } },
    world = { status = { popups = vector({}), reports = vector({}) } },
    game = { main_interface = { help = { open = false } } },
  },
}

function reset_world()
  WORLD.paused = true
  WORLD.viewscreen = "viewscreen_dwarfmodest"
  WORLD.focus = { "dwarfmode/Default" }
  WORLD.cur_year = 100
  WORLD.cur_year_tick = 5000
  WORLD.tripwire = nil
  WORLD.clicks = {}
  WORLD.screen_labels = {}
  WORLD.buttons_close_popup = true
  df.global.cur_year = WORLD.cur_year
  df.global.cur_year_tick = WORLD.cur_year_tick
  df.global.world.status.popups = vector({})
  df.global.world.status.reports = vector({})
  df.global.game.main_interface.help.open = false
end

function add_popup(text)
  local p = df.global.world.status.popups
  rawset(p, p._n, { text = text })
  rawset(p, "_n", p._n + 1)
  -- the box draws an Okay button (More while others are queued)
  WORLD.screen_labels = { { text = (p._n > 1) and "More" or "Okay", x = 30, y = 12 } }
end

function add_report(id, type_id, text, year, time)
  local r = df.global.world.status.reports
  rawset(r, r._n, { id = id, type = type_id, text = text, year = year, time = time })
  rawset(r, "_n", r._n + 1)
end

function set_viewscreen(name) WORLD.viewscreen = name end
function set_help_open(v) df.global.game.main_interface.help.open = v end
function set_buttons_close_popup(v) WORLD.buttons_close_popup = v end
function set_tripwire(t) WORLD.tripwire = t end
function set_paused(v) WORLD.paused = v end
function popup_count() return #df.global.world.status.popups end
function click_count() return #WORLD.clicks end

local function refresh_labels()
  local p = df.global.world.status.popups
  if #p == 0 then
    WORLD.screen_labels = {}
  else
    WORLD.screen_labels = { { text = (#p > 1) and "More" or "Okay", x = 30, y = 12 } }
  end
end

dfhack = {
  world = { ReadPauseState = function() return WORLD.paused end },
  gui = {
    getDFViewscreen = function() return { _type = "<type: " .. WORLD.viewscreen .. ">" } end,
    getCurViewscreen = function() return { _type = "<type: " .. WORLD.viewscreen .. ">" } end,
    getCurFocus = function() return WORLD.focus end,
  },
  screen = {
    getWindowSize = function() return 80, 25 end,
    readTile = function(x, y)
      for _, lab in ipairs(WORLD.screen_labels) do
        if y == lab.y and x >= lab.x and x < lab.x + #lab.text then
          return { ch = lab.text:byte(x - lab.x + 1) }
        end
      end
      return { ch = 32 }
    end,
  },
}

package.loaded["gui"] = {
  simulateInput = function(_, key)
    WORLD.clicks[#WORLD.clicks + 1] = { key = key, x = df.global.gps.mouse_x, y = df.global.gps.mouse_y }
    for _, lab in ipairs(WORLD.screen_labels) do
      if df.global.gps.mouse_y == lab.y and df.global.gps.mouse_x >= lab.x
          and df.global.gps.mouse_x < lab.x + #lab.text and WORLD.buttons_close_popup then
        local p = df.global.world.status.popups
        if #p > 0 then p:erase(0) end
        refresh_labels()
        return
      end
    end
  end,
}

function require(n)
  if package.loaded[n] then return package.loaded[n] end
  return {}
end

function reqscript(n)
  if n == "df-overseer-clock" then
    return {
      clock_status = function()
        return {
          paused = WORLD.paused, tripwire = WORLD.tripwire,
          cur_year_tick = df.global.cur_year_tick,
          abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick,
        }
      end,
    }
  end
  return {}
end
