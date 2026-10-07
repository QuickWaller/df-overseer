--@module = true
-- df-overseer-screen.lua
--
-- What the player currently SEES, as text: the game's focus strings, which
-- panel or menu is open, whether that panel blocks resuming the fort, and
-- (on request) the panel's own text lines.
--
-- Why it exists (evals/live/2026-10-08-manager-appointment/README.md): an open
-- Work Orders panel (focus dwarfmode/Info/WORK_ORDERS/Default) made a scripted
-- resume a silent no-op: the game stayed paused. The conductor resumes the
-- fort unattended, so the same panel would stall it with no explanation.
-- clock.resume and clock.status use blocking_panel() below to NAME the panel.
--
-- ============================================================================
-- DESIGN COMMITMENT 1 (docs/PURPOSE.md): THIS NEVER RETURNS A RENDERED MAP.
-- Text is read only while the focus matches a rule marked text_ok (an Info or
-- sheet panel). With the plain map showing (dwarfmode/Default) or any focus
-- no rule marks text_ok, the text is REFUSED, not trimmed. Every line that is
-- returned is also filtered to prose-like text (printable ASCII, mostly
-- letters and digits, at least a word long), which drops tile glyph noise.
-- The map viewport itself renders by texture blit and does not appear in the
-- character buffer, so this is a second guard, not the only one.
--
-- ============================================================================
-- DATA, NOT BRANCHES. PANEL_RULES is the whole policy. First match wins. A
-- new panel kind is one table entry. `blocks_resume` states whether an open
-- panel of that kind stops the game from unpausing; only the entries whose
-- `verified` field names a live observation are known, the rest are stated
-- as the safe guess and say so.
--
-- Armok: reads only what a player sees on their own screen
-- (docs/ARMOK-RULINGS.md, "reading something a player can already see is
-- fine"). Read only: no input is simulated, nothing is closed or opened.

local MAX_LINES = 80
local MAX_LINE_CHARS = 160
local MIN_LINE_ALNUM = 3
local MIN_ALNUM_FRACTION = 0.6

-- A focus outside this prefix means the game is not on the fortress play
-- screen at all (title, a world screen, a save prompt): it blocks resume.
local PLAY_SCREEN_PREFIX = "dwarfmode"

PANEL_RULES = {
  {
    name = "info_panel",
    prefix = "dwarfmode/Info/",
    blocks_resume = true,
    text_ok = true,
    verified = "dwarfmode/Info/WORK_ORDERS/Default blocked a scripted resume live, 2026-10-08; "
      .. "the other Info panels (Labor, Stocks, Justice...) are assumed to behave the same",
  },
  {
    name = "view_sheet",
    prefix = "dwarfmode/ViewSheets",
    blocks_resume = false,
    text_ok = true,
    verified = "unverified: a unit or building sheet is believed not to stop the clock",
  },
  {
    name = "play_screen",
    prefix = "dwarfmode/Default",
    blocks_resume = false,
    text_ok = false,
    verified = "the plain map; read live 2026-10-08. Text is refused here by design",
  },
  {
    name = "non_play_screen",
    outside_play_screen = true,
    blocks_resume = true,
    text_ok = false,
    verified = "a screen other than the fortress play screen cannot be running",
  },
  {
    -- Anything dwarfmode that no rule above names (a designation or build
    -- mode, a zone editor, ...): reported by its focus, treated as not
    -- blocking and unread, because none has been seen to block.
    name = "unclassified",
    prefix = "dwarfmode",
    blocks_resume = false,
    text_ok = false,
    verified = "unverified: report the focus, make no claim",
  },
}

-- ----------------------------------------------------------------------------
-- pure logic (tested without a game)

local function rule_matches(rule, focus)
  if rule.outside_play_screen then
    return focus:sub(1, #PLAY_SCREEN_PREFIX) ~= PLAY_SCREEN_PREFIX
  end
  if rule.prefix == "dwarfmode/Default" then
    return focus == rule.prefix or focus:sub(1, #rule.prefix + 1) == rule.prefix .. "/"
  end
  return focus:sub(1, #rule.prefix) == rule.prefix
end

-- The rule for one focus string, or nil when the string is empty.
function rule_for_focus(focus)
  if type(focus) ~= "string" or focus == "" then return nil end
  for _, rule in ipairs(PANEL_RULES) do
    if rule_matches(rule, focus) then return rule end
  end
  return nil
end

-- Classify a list of focus strings (the game returns several, outermost
-- first). The panel is the last matching rule that is not the bare play
-- screen; blocking is set if ANY focus string matches a blocking rule.
function classify_focus(foci)
  local panel, blocking
  for _, f in ipairs(foci or {}) do
    local rule = rule_for_focus(f)
    if rule then
      if rule.blocks_resume and not blocking then
        blocking = { name = rule.name, focus = f }
      end
      if rule.name ~= "play_screen" then
        panel = { name = rule.name, focus = f, text_ok = rule.text_ok, verified = rule.verified }
      end
    end
  end
  return panel, blocking
end

-- Keep only prose-like lines: printable ASCII, enough letters and digits,
-- mostly alphanumeric or spaces. Drops glyph noise.
function clean_lines(raw)
  local out = {}
  for _, line in ipairs(raw or {}) do
    local s = tostring(line):gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")
    if #s > MAX_LINE_CHARS then s = s:sub(1, MAX_LINE_CHARS) end
    local _, alnum = s:gsub("%w", "")
    local _, plain = s:gsub("[%w ]", "")
    if alnum >= MIN_LINE_ALNUM and #s > 0 and (plain / #s) >= MIN_ALNUM_FRACTION then
      out[#out + 1] = s
      if #out >= MAX_LINES then break end
    end
  end
  return out
end

-- ----------------------------------------------------------------------------
-- game reads

local function to_list(list)
  local out = {}
  for i = 1, #list do out[#out + 1] = tostring(list[i]) end
  return out
end

local function focus_list()
  local ok, f = pcall(function()
    return to_list(dfhack.gui.getFocusStrings(dfhack.gui.getDFViewscreen(true)))
  end)
  if ok and f and #f > 0 then return f end
  local ok2, g = pcall(function() return to_list(dfhack.gui.getCurFocus(true)) end)
  if ok2 and g and #g > 0 then return g end
  return nil
end

local function screen_lines()
  local w, h = dfhack.screen.getWindowSize()
  local raw = {}
  for y = 0, h - 1 do
    local row = {}
    for x = 0, w - 1 do
      local tile = dfhack.screen.readTile(x, y)
      local ch = tile and tile.ch
      row[#row + 1] = (ch and ch >= 32 and ch < 127) and string.char(ch) or " "
    end
    raw[#raw + 1] = table.concat(row)
  end
  return raw
end

-- Module function used by df-overseer-clock: nil when nothing blocks, else
-- { name =, focus = }. Never throws.
function blocking_panel()
  local ok, res = pcall(function()
    local foci = focus_list()
    if not foci then return nil end
    local _, blocking = classify_focus(foci)
    return blocking
  end)
  if ok then return res end
  return nil
end

function screen_read(with_text)
  local foci = focus_list()
  if not foci then
    return { ok = false, error = "could not read the focus strings" }
  end
  local panel, blocking = classify_focus(foci)
  local out = {
    ok = true,
    focus = foci,
    panel = panel and panel.name or nil,
    blocks_resume = blocking ~= nil,
    blocking = blocking,
  }
  local want = with_text == true or with_text == "true" or with_text == "1" or with_text == "text"
  if want then
    if panel and panel.text_ok then
      out.lines = clean_lines(screen_lines())
    else
      out.text_refused = "no readable panel is open; the only content is the map, which is never returned"
    end
  end
  return out
end

-- ----------------------------------------------------------------------------
-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "read" then
  print(json.encode(screen_read(args[2])))
else
  print("usage: df-overseer-screen <read [WITH_TEXT]>")
end
