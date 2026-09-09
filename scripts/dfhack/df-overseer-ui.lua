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
else
  print("usage: df-overseer-ui <type|click TEXT|dump>")
end
