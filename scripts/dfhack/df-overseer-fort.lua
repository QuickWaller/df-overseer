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
-- WHICH SLOT WAS WRITTEN: NEVER PREDICTED, ALWAYS OBSERVED FROM DF'S OWN
-- RECORD, NOT FROM FILE MTIMES. REWRITTEN 2026-09-22
-- (handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md), TWICE in the
-- same stream:
--
-- First pass: dropped the original oldest-mtime PREDICTION (it was wrong on
-- a real fort -- the encoding-fix stream's own quicksave predicted "autosave
-- 1", the save landed in "autosave 2",
-- evals/live/2026-09-22-loop-game-text-encoding/README.md) in favour of
-- reading every named slot's real `world.sav` mtime via
-- `dfhack.filesystem.mtime` before and after firing.
--
-- Second pass, found live deploying THAT fix to VM 103, not assumed:
-- `dfhack.filesystem.mtime` is BROKEN on this install. Its own doc says it
-- returns "the modification time (in seconds)... or -1 if path does not
-- exist"; live-verified against `stat`'s real values (which matched
-- wall-clock time exactly), it instead returns huge, nonsensical negative
-- numbers on the order of -1e18 to -5e18 for every real, existing file
-- tested (a compiled binary, a log file, a save file) -- never a plausible
-- epoch-seconds value. `io.popen`/`os.execute` are sandboxed out of this
-- DFHack Lua environment entirely (`pcall(io.popen, ...)` fails live: "attempt
-- to call a nil value"), so there is no in-sandbox way to shell out to a
-- working `stat` as a fallback -- and shelling out would arguably be a bigger
-- capability than a player has anyway, the same reasoning `CLAUDE.md`'s "no
-- armok" rule already applies elsewhere in this project.
--
-- The fix drops file mtimes ENTIRELY and uses the handoff's own explicitly
-- sanctioned alternative instead: "DF's own record of the save",
-- `df.global.world.cur_savegame.save_dir`. Live-verified this stream,
-- end to end: read before a real `quicksave`, it read "autosave 3"; after
-- the save actually landed (confirmed independently via the OS's own `stat`
-- over ssh, outside this tool, showing a fresh `autosave 1/world.sav` mtime),
-- it read "autosave 1" -- the exact slot the rotation actually picked, not a
-- guess. This is the same signal the encoding-fix stream used by hand
-- ("cur_savegame.save_dir plus a fresh matching world.sav mtime").
--
-- Known, honest limitation of a plain equality check: if the rotation ever
-- picks the SAME slot twice in a row across two "issue" calls with no
-- intervening confirm (not possible with the documented overwrite-oldest,
-- 3-slot policy unless two OTHER quicksaves already rotated back around --
-- an unlikely cadence for this tool's real call pattern, roughly once per
-- conductor cycle), "confirmed" would read false even though a real save did
-- land. Not engineered around, since it cannot happen without knowing
-- ahead of time that this SPECIFIC scenario matters to a real caller, and
-- doing so would need tracking more state than this tool currently has any
-- other reason to hold.
local json = require('json')

local function current_save_dir()
  local ok, dir = pcall(function() return df.global.world.cur_savegame.save_dir end)
  if not ok or dir == nil or dir == "" then
    return nil
  end
  return dir
end

-- quicksave [PRIOR_SAVE_DIR]
--
-- No arg: fires quicksave and returns cur_savegame.save_dir as it stood
-- immediately before firing (never confirmed inline -- see header).
--
-- One arg (PRIOR_SAVE_DIR, the value the "issued" call returned): does NOT
-- re-fire quicksave, just reports whether cur_savegame.save_dir now reads a
-- DIFFERENT value -- the slot DF itself just wrote to, read from its own
-- record, never a guess. Meant to be called again later, spaced out, not in
-- a tight loop (up to ~90s observed for a save to actually land).
function fort_quicksave(prior_save_dir)
  if prior_save_dir ~= nil then
    local current = current_save_dir()
    local confirmed = current ~= nil and current ~= prior_save_dir
    local result = {
      ok = true,
      mode = "confirm",
      prior_save_dir = prior_save_dir,
      current_save_dir = current,
      confirmed = confirmed,
    }
    if confirmed then
      result.slot = current
    end
    return result
  end

  local prior = current_save_dir()
  dfhack.run_command('quicksave')
  return {
    ok = true,
    mode = "issued",
    issued = true,
    prior_save_dir = prior,
    note = "quicksave is asynchronous (render-loop-gated, up to ~90s observed); "
      .. "this call does not confirm completion or predict a slot -- poll "
      .. "again later with 'quicksave " .. tostring(prior)
      .. "' (spaced out, never in a tight loop); the confirmed slot is "
      .. "cur_savegame.save_dir's new value, DF's own record, never a guess",
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "quicksave" then
  print(json.encode(fort_quicksave(args[2])))
else
  print("usage: df-overseer-fort quicksave [PRIOR_SAVE_DIR]")
end
