-- df-overseer-fort.lua
--@module = true
--
-- handoffs/2026-09-22-loop-clock-conductor-role.md, build item 2: a
-- quicksave tool for the conductor, granted the same narrow `kind: system`
-- exception as df-overseer-clock.lua's tools (see that file's header for the
-- roles.py rationale). A separate file, not folded into df-overseer-clock.lua,
-- because its canonical id needs the `fort.` prefix
-- (docs/AGENT-LOOP.md's own naming: `fort.quicksave`, distinct from the
-- `clock.*` control-plane group) and because its one real design problem --
-- how to report a quicksave's outcome without ever blocking on it -- is
-- self-contained and deserves its own header rather than crowding
-- df-overseer-clock.lua's already-long one.
--
-- ============================================================================
-- WHY THIS TOOL NEVER BLOCKS WAITING FOR THE SAVE TO LAND, EVEN THOUGH THE
-- HANDOFF ASKS FOR A RESULT "CONFIRMED BY THE SLOT'S MTIME CHANGING".
-- Two already-established facts in this project combine into a real hazard,
-- not just caution:
--   1. hack/scripts/quicksave.lua (read directly, quoted in
--      research/2026-09-11-quicksave-silent-noop.md) is NOT synchronous: it
--      pushes a QuicksaveOverlay screen and the actual save() call only runs
--      inside that screen's OWN :render() method, on a LATER render pass --
--      observed live taking anywhere from under 8 seconds to over 80.
--   2. docs/AGENT-ARCHITECTURE.md ss6 (verified from source, not guessed):
--      "DFHack opens its suspend window once per simulation tick, after the
--      tick's own work finishes" -- so a script call runs WHILE the engine's
--      normal tick/render work is suspended. A script that busy-waited
--      inside one call for the save to land would therefore itself be
--      holding the exact suspend lock the pending render pass needs to fire,
--      which could prevent the save it is waiting for from EVER completing --
--      a self-deadlock, not merely a slow poll. docs/TRAPS.md's wedged-pipe
--      incident is the same family of mistake (one script call
--      monopolising the command pipe) with a different trigger.
-- So this tool fires quicksave and returns IMMEDIATELY with enough
-- information for the CALLER to confirm out of band, over separate,
-- cheap, spaced-out calls -- exactly how research/2026-09-11's own
-- reproduction actually verified a real save (several independent
-- `dfhack-run` round trips over up to ~90 real seconds, never one blocking
-- call). This is a deliberate deviation from the handoff's literal phrasing
-- ("reports the slot written, confirmed by the slot's mtime changing"); see
-- this stream's report for the flag raised about it.
--
-- ============================================================================
-- WHICH SLOT WILL BE WRITTEN. Confirmed rotation policy
-- (memory/dfhack-environment.md, "quicksave rotates slot directories
-- (autosave 1 to 3)... overwrite-oldest, not fixed round-robin", live-
-- confirmed twice in research/2026-09-11-quicksave-silent-noop.md ss3-4): the
-- next quicksave lands in whichever of the three `autosave N` directories has
-- the OLDEST world.sav mtime at the moment it is issued. Reading exactly
-- three named directories is a bounded read (docs/TRAPS.md), never a scan.
--
-- The three slots' parent directory is derived from dfhack.getSavePath()
-- (the CURRENT save directory, which memory/dfhack-environment.md notes can
-- report "current" rather than a slot name -- irrelevant here since only its
-- PARENT is used) by stripping its final path component. NOT independently
-- live-verified this stream (no VM, no live fort) -- named as an exact live
-- check this stream's report asks the deploy stream to run.

local json = require('json')

local SLOT_NAMES = { "autosave 1", "autosave 2", "autosave 3" }

local function save_root()
  local path = dfhack.getSavePath()
  if not path then
    return nil, "dfhack.getSavePath() returned nil -- no world loaded"
  end
  local root = path:match("^(.*)[/\\][^/\\]+[/\\]?$")
  if not root then
    return nil, "could not derive a parent directory from getSavePath() result " .. tostring(path)
  end
  return root, nil
end

local function slot_mtime(root, slot_name)
  local world_sav = root .. "/" .. slot_name .. "/world.sav"
  local ok, mtime = pcall(dfhack.filesystem.mtime, world_sav)
  if not ok or mtime == nil or mtime < 0 then
    return nil
  end
  return mtime
end

-- The slot with the OLDEST mtime among the three named slots is the one the
-- rotation policy will overwrite next. A slot that cannot be read (missing,
-- fresh install) sorts as "oldest" (mtime -1 treated as older than any real
-- mtime), since an absent slot is exactly where the next save should land.
local function oldest_slot(root)
  local oldest_name, oldest_mtime = nil, nil
  for _, name in ipairs(SLOT_NAMES) do
    local m = slot_mtime(root, name)
    local sort_key = m or -1
    if oldest_mtime == nil or sort_key < oldest_mtime then
      oldest_name, oldest_mtime = name, sort_key
    end
  end
  return oldest_name, oldest_mtime
end

-- quicksave [CONFIRM_SLOT CONFIRM_PRIOR_MTIME]
--
-- No args: fire quicksave, return the predicted target slot and its mtime
-- immediately before firing (never confirmed inline -- see header).
--
-- Both args given (an all-or-nothing pair, per the registry's own
-- convention): do NOT fire quicksave again; just report whether
-- CONFIRM_SLOT's world.sav mtime has moved past CONFIRM_PRIOR_MTIME. This is
-- the caller's own out-of-band confirmation step, meant to be called again
-- with real wall-clock gaps between attempts (up to ~90s observed,
-- research/2026-09-11-quicksave-silent-noop.md), never in a tight loop.
function fort_quicksave(confirm_slot, confirm_prior_mtime)
  local root, root_err = save_root()
  if not root then
    return { ok = false, error = root_err }
  end

  if confirm_slot and confirm_prior_mtime then
    local prior = tonumber(confirm_prior_mtime)
    if not prior then
      return { ok = false, error = "CONFIRM_PRIOR_MTIME must be a number, got " .. tostring(confirm_prior_mtime) }
    end
    local ok_slot = false
    for _, name in ipairs(SLOT_NAMES) do
      if name == confirm_slot then ok_slot = true end
    end
    if not ok_slot then
      return { ok = false, error = "CONFIRM_SLOT must be one of \"autosave 1\"/\"autosave 2\"/\"autosave 3\", got " .. tostring(confirm_slot) }
    end
    local current = slot_mtime(root, confirm_slot)
    return {
      ok = true,
      mode = "confirm",
      slot = confirm_slot,
      prior_mtime = prior,
      current_mtime = current,
      confirmed = (current ~= nil and current ~= prior),
    }
  end

  local target_slot, prior_mtime = oldest_slot(root)
  dfhack.run_command('quicksave')
  return {
    ok = true,
    mode = "issued",
    issued = true,
    predicted_slot = target_slot,
    predicted_slot_prior_mtime = prior_mtime,
    note = "quicksave is asynchronous (render-loop-gated, up to ~90s observed); "
      .. "this call does not confirm completion -- poll again later with "
      .. "'quicksave " .. tostring(target_slot) .. " " .. tostring(prior_mtime)
      .. "' (spaced out, never in a tight loop) to confirm the mtime moved",
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "quicksave" then
  print(json.encode(fort_quicksave(args[2], args[3])))
else
  print("usage: df-overseer-fort quicksave [CONFIRM_SLOT CONFIRM_PRIOR_MTIME]")
end
