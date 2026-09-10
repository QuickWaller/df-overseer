-- df-overseer-ui.lua
--
-- Reusable DF v50+ menu/UI automation helpers, deployed once onto VM 103's
-- own hack/scripts/ directory (see install_df.py's `ui-install` subcommand)
-- so future sessions call an already-tested tool instead of hand-writing a
-- fresh Lua script over SSH for every single button click -- that
-- one-off-script pattern is what made 2026-09-09/10's embark-flow work slow
-- and made the same techniques (buffer-scan for text, atomic mouse
-- position+click, retry-and-verify) get re-derived from scratch each time.
--
-- Usage: ./dfhack-run df-overseer-ui <command> [args...]
--   type            -- print the current real (non-DFHack-overlay) viewscreen type
--   click TEXT      -- buffer-scan for TEXT, click its center, retry up to 3x,
--                      verify by checking whether TEXT is still present after
--   dump            -- print every non-blank row of the character buffer
--                      (diagnostic only -- the map viewport itself renders via
--                      a texture-blit path invisible to this, confirmed
--                      2026-09-09; this only sees real character-buffer text)
--
-- Known limitation, not solved by this script: gui.simulateInput's _MOUSE_L
-- click is unreliable for on-screen targets far from screen-center (the
-- Embark button, direct map clicks) even when this exact click() technique
-- works fine for centered buttons (title screen, mode picker). See
-- Working.md's queued task ("make the final click Embark register") for the
-- open gps.precise_mouse_x/y lead -- this script does not yet account for it.

local gui = require('gui')

local function screen_type()
  return tostring(dfhack.gui.getDFViewscreen(true)._type)
end

-- Scans the full character buffer for the first exact occurrence of `target`
-- and returns its row and column span. Returns nil if not found. This is the
-- 2026-09-09 title-screen-bootstrap technique (gui/kitchen-info.lua's
-- label-locator idiom) -- scan for real text, never guess a pixel coordinate
-- from a screenshot, per design commitment #1's spirit even for menu
-- automation that isn't itself game-state perception.
local function find_text(target)
  local w, h = dfhack.screen.getWindowSize()
  for y = 0, h - 1 do
    local line = ""
    for x = 0, w - 1 do
      local tile = dfhack.screen.readTile(x, y)
      local ch = tile and tile.ch
      line = line .. (ch and ch >= 32 and ch < 127 and string.char(ch) or " ")
    end
    local s, e = line:find(target, 1, true)
    if s then return y, s - 1, e - 1 end
  end
  return nil
end

-- Clicks the center of the first match for `target`, retrying up to
-- `attempts` times (default 3) -- clicks on this UI are genuinely flaky
-- (confirmed repeatedly 2026-09-09/10, cause unconfirmed), not a bug in this
-- function specifically. "Success" is verified by re-scanning for the same
-- text afterward and treating its disappearance as a proxy for "something
-- changed" -- imperfect (the text could theoretically still be present on a
-- new screen by coincidence) but matches the verification standard already
-- established live this session, and is far better than assuming success
-- from a lack of a Lua error.
local function click_text(target, attempts)
  attempts = attempts or 3
  for i = 1, attempts do
    local row, cs, ce = find_text(target)
    if not row then
      return false, string.format("text not found (attempt %d): %s", i, target)
    end
    local cx = math.floor((cs + ce) / 2)
    local scr = dfhack.gui.getCurViewscreen()
    df.global.gps.mouse_x = cx
    df.global.gps.mouse_y = row
    gui.simulateInput(scr, '_MOUSE_L')
    if not find_text(target) then
      return true, string.format("clicked (%d,%d) on attempt %d/%d, verified", cx, row, i, attempts)
    end
    -- text still present -- either the click had no effect, or this screen
    -- genuinely still shows the same text after a real transition (a false
    -- negative this simple check can't rule out). Retry.
  end
  return false, string.format("clicked but '%s' still present after %d attempts (unverified)", target, attempts)
end

local function dump_screen()
  local w, h = dfhack.screen.getWindowSize()
  print(string.format("window size: %dx%d, current type: %s", w, h, screen_type()))
  for y = 0, h - 1 do
    local line = ""
    local has_text = false
    for x = 0, w - 1 do
      local tile = dfhack.screen.readTile(x, y)
      local ch = tile and tile.ch
      local c
      if ch and ch >= 32 and ch < 127 then
        c = string.char(ch)
      else
        c = "."
      end
      if c ~= "." and c ~= " " then has_text = true end
      line = line .. c
    end
    if has_text then print(string.format("%2d: %s", y, line)) end
  end
end

-- Embark-site-sweep helpers, added 2026-09-10. These are specific to
-- viewscreen_choose_start_sitest and depend on a finding from that same
-- session: neighbor_hover_mm_* (the live-hovered embark rectangle) only
-- updates from real mouse movement while scr.choosing_embark is true --
-- during ordinary browsing (choosing_embark false) it is frozen, even
-- though the hover-info text panel updates in both modes. This was not
-- previously documented; research/2026-09-10-embark-screen-rendering-and-coordinates.md
-- only tested it via a real embark placement click, not casual hovering.
-- The sweep therefore has to run inside choosing_embark mode throughout.

-- Clicks the real "Embark" button at its known row-57 position directly,
-- rather than a text scan -- a whole-screen scan for "Embark" false-matches
-- the instructional sentence at row 52 first (see the screen atlas in
-- docs/DF-UI-AUTOMATION.md). Caller must already be on
-- viewscreen_choose_start_sitest with zoomed_in true.
local function embark_mode()
  local scr = dfhack.gui.getCurViewscreen()
  if scr.choosing_embark then
    return true, "already in choosing_embark mode"
  end
  df.global.gps.mouse_x = 115
  df.global.gps.mouse_y = 57
  gui.simulateInput(scr, '_MOUSE_L')
  scr = dfhack.gui.getCurViewscreen()
  if scr.choosing_embark then
    return true, "entered choosing_embark mode"
  end
  return false, "Embark click did not flip choosing_embark"
end

-- Cancels choosing_embark mode with LEAVESCREEN (confirmed live 2026-09-10
-- to cleanly return to ordinary browsing with warn_mm_* untouched, no
-- confirm/abort prompt, so long as the local map itself was never clicked).
local function leave_embark_mode()
  local scr = dfhack.gui.getCurViewscreen()
  gui.simulateInput(scr, 'LEAVESCREEN')
  scr = dfhack.gui.getCurViewscreen()
  return not scr.choosing_embark
end

-- Reads the current hover state: the live neighbor_hover_mm_* rectangle
-- (only meaningful in choosing_embark mode -- see above) plus a handful of
-- buffer-scanned criteria flags from the hover-info side panel (biome name
-- row, aquifer/soil/tree lines). This is read-only: it does not move the
-- mouse itself, so the caller drives the real cursor (xdotool, over SSH)
-- before calling this. One compact tagged line, easy to grep/parse from
-- the calling shell loop.
local function row_text(y)
  local w = dfhack.screen.getWindowSize()
  local line = ""
  for x = 0, w - 1 do
    local tile = dfhack.screen.readTile(x, y)
    local ch = tile and tile.ch
    line = line .. (ch and ch >= 32 and ch < 127 and string.char(ch) or " ")
  end
  return line
end

local function hover_info()
  local scr = dfhack.gui.getCurViewscreen()
  local sx, sy, ex, ey = scr.neighbor_hover_mm_sx, scr.neighbor_hover_mm_sy,
                         scr.neighbor_hover_mm_ex, scr.neighbor_hover_mm_ey
  -- Panel rows confirmed live 2026-09-10: 1 = region name, 4 = biome name,
  -- 5 = temperature, 6 = trees, 7 = other vegetation, 8 = surroundings;
  -- soil/aquifer lines float lower (17-22ish) depending on how many mineral
  -- lines print above them, so search a wider band rather than one row.
  -- Row 4 carries an extra "N x N" embark-size prefix while choosing_embark
  -- is true (not present during plain browsing, confirmed live 2026-09-10)
  -- ahead of the actual biome name -- search the whole row for "Ocean"
  -- rather than assuming the biome name is the row's only content.
  local biome = row_text(4):match("%S.*%S") or ""
  local trees = row_text(6):match("%S.*%S") or ""
  local flags = ""
  for y = 15, 24 do
    flags = flags .. " " .. row_text(y)
  end
  local ocean = (flags:find("Ocean") or biome:find("Ocean")) and 1 or 0
  local aquifer = flags:find("aquifer") and 1 or 0
  local no_soil = flags:find("No soil") and 1 or 0
  print(string.format(
    "HOVER sx=%d sy=%d ex=%d ey=%d ocean=%d aquifer=%d no_soil=%d biome=%q trees=%q",
    sx, sy, ex, ey, ocean, aquifer, no_soil, biome, trees))
end

local args = {...}
local cmd = args[1]

if cmd == "type" then
  print(screen_type())
elseif cmd == "click" then
  if not args[2] then
    print("usage: df-overseer-ui click \"TEXT TO FIND\"")
  else
    local ok, msg = click_text(args[2])
    print((ok and "OK: " or "FAIL: ") .. msg)
  end
elseif cmd == "dump" then
  dump_screen()
elseif cmd == "embark-mode" then
  local ok, msg = embark_mode()
  print((ok and "OK: " or "FAIL: ") .. msg)
elseif cmd == "leave-embark-mode" then
  print(leave_embark_mode() and "OK: left choosing_embark mode" or "FAIL: still in choosing_embark mode")
elseif cmd == "hover" then
  hover_info()
else
  print("usage: df-overseer-ui <type|click TEXT|dump|embark-mode|leave-embark-mode|hover>")
end
