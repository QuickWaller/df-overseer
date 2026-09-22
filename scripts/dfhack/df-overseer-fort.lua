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
-- WHICH SLOT WAS WRITTEN: NEVER PREDICTED, ALWAYS OBSERVED. FIXED 2026-09-22
-- (handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md). The original
-- version of this tool predicted the target slot as whichever named
-- directory had the OLDEST world.sav mtime at issue time, on the theory that
-- quicksave's confirmed overwrite-oldest rotation policy
-- (memory/dfhack-environment.md, live-confirmed twice in
-- research/2026-09-11-quicksave-silent-noop.md ss3-4) always picks it. That
-- theory turned out wrong on a real fort: the encoding-fix stream's own
-- quicksave predicted "autosave 1" while the save landed in "autosave 2"
-- (evals/live/2026-09-22-loop-game-text-encoding/README.md). The tool no
-- longer predicts anything -- it reports every named slot's mtime before
-- firing and, on a later confirm call, reports whichever slot's mtime
-- actually changed. Reading exactly three named directories, both before and
-- during confirm, is a bounded read (docs/TRAPS.md), never a scan.
--
-- The three slots' parent directory is derived from dfhack.getSavePath()
-- (the CURRENT save directory, which memory/dfhack-environment.md notes can
-- report "current" rather than a slot name -- irrelevant here since only its
-- PARENT is used) by stripping its final path component. FOUND LIVE this
-- stream, not assumed: on VM 103, dfhack.getSavePath() reports a path
-- derived from the game's own install directory (e.g.
-- "/opt/df/game/save/autosave 3") that DOES NOT EXIST as a real directory
-- at all -- a known, already-documented quirk of this exact install
-- (research/2026-09-11-quicksave-silent-noop.md ss3, docs/TRAPS.md "Saves
-- live at the XDG path, not in the game directory"), never previously
-- encoded into a runtime check, only into prose. The real save directory is
-- the XDG basedir (`~/.local/share/Bay 12 Games/Dwarf Fortress/save` on
-- Linux). save_root() below is self-verifying rather than hardcoding one or
-- the other: it tries the getSavePath()-derived candidate first (so a
-- future DFHack/install fix that makes getSavePath() correct needs no
-- further change here), and falls back to the documented XDG candidate,
-- picking whichever one dfhack.filesystem.isdir confirms is a real
-- directory. Verified live this stream: the getSavePath()-derived candidate
-- does not exist; the XDG candidate does and holds the real, currently
-- rotating "autosave 1/2/3" directories.

local json = require('json')

local SLOT_NAMES = { "autosave 1", "autosave 2", "autosave 3" }

local function save_root()
  local path = dfhack.getSavePath()
  if not path then
    return nil, "dfhack.getSavePath() returned nil -- no world loaded"
  end
  local candidate_a = path:match("^(.*)[/\\][^/\\]+[/\\]?$")
  if candidate_a and dfhack.filesystem.isdir(candidate_a) then
    return candidate_a, nil
  end

  local home = os.getenv("HOME")
  local candidate_b = home and (home .. "/.local/share/Bay 12 Games/Dwarf Fortress/save") or nil
  if candidate_b and dfhack.filesystem.isdir(candidate_b) then
    return candidate_b, nil
  end

  return nil, "no real save directory found -- tried "
    .. tostring(candidate_a or "(could not derive a parent from getSavePath() result " .. tostring(path) .. ")")
    .. " and " .. tostring(candidate_b or "(no HOME env var, XDG candidate not attempted)")
end

local function slot_mtime(root, slot_name)
  local world_sav = root .. "/" .. slot_name .. "/world.sav"
  local ok, mtime = pcall(dfhack.filesystem.mtime, world_sav)
  if not ok or mtime == nil or mtime < 0 then
    return nil
  end
  return mtime
end

-- FIXED 2026-09-22 (handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md):
-- the original "issued" reply predicted the target slot as the one with the
-- OLDEST mtime among the three named slots, on the theory that quicksave's
-- overwrite-oldest rotation always picks it. Found live, not by this stream
-- (evals/live/2026-09-22-loop-game-text-encoding/README.md, "Found live,
-- not fixed"): the encoding-fix stream's own quicksave predicted "autosave
-- 1" while the save actually landed in "autosave 2" -- the prediction was
-- simply wrong on a real fort, and the conductor and the deploy rules trust
-- this tool's report, so a guess is not good enough.
--
-- The fix drops prediction entirely. "issued" now returns the mtime of
-- EVERY named slot as it stood immediately before firing quicksave (three
-- bounded stat calls, same cost as before). Passing all three prior mtimes
-- back (an all-or-nothing group, the same convention as the tool's
-- original two-arg CONFIRM_SLOT/CONFIRM_PRIOR_MTIME pair, just now three
-- members and no separate mode flag needed) reports whichever slot's mtime
-- actually moved -- the truth, read after the fact, never a guess about
-- which slot the rotation policy will pick.
function fort_quicksave(prior_autosave_1, prior_autosave_2, prior_autosave_3)
  local root, root_err = save_root()
  if not root then
    return { ok = false, error = root_err }
  end

  if prior_autosave_1 ~= nil or prior_autosave_2 ~= nil or prior_autosave_3 ~= nil then
    local priors = { tonumber(prior_autosave_1), tonumber(prior_autosave_2), tonumber(prior_autosave_3) }
    for i, name in ipairs(SLOT_NAMES) do
      if priors[i] == nil then
        return {
          ok = false,
          error = "confirm needs three prior mtimes, one per slot in order "
            .. table.concat(SLOT_NAMES, ", ") .. " -- missing/non-numeric value for " .. name,
        }
      end
    end
    local slots = {}
    local changed = {}
    for i, name in ipairs(SLOT_NAMES) do
      local current = slot_mtime(root, name)
      slots[name] = { prior_mtime = priors[i], current_mtime = current }
      if current ~= nil and current ~= priors[i] then
        table.insert(changed, name)
      end
    end
    local result = {
      ok = true,
      mode = "confirm",
      slots = slots,
      changed_slots = changed,
      confirmed = (#changed == 1),
      ambiguous = (#changed > 1),
    }
    if #changed == 1 then
      result.slot = changed[1]
    end
    return result
  end

  local prior_mtimes = {}
  for _, name in ipairs(SLOT_NAMES) do
    -- json.encode drops a nil table value silently; a missing slot file
    -- (fresh install, never rotated into yet) is reported as -1, the same
    -- "older than any real mtime" sentinel a missing slot should sort as,
    -- so the confirm call can still tell -1 apart from a real timestamp.
    prior_mtimes[name] = slot_mtime(root, name) or -1
  end
  dfhack.run_command('quicksave')
  return {
    ok = true,
    mode = "issued",
    issued = true,
    prior_mtimes = prior_mtimes,
    note = "quicksave is asynchronous (render-loop-gated, up to ~90s observed); "
      .. "this call does not confirm completion or predict a slot -- poll "
      .. "again later with 'quicksave " .. tostring(prior_mtimes["autosave 1"])
      .. " " .. tostring(prior_mtimes["autosave 2"]) .. " " .. tostring(prior_mtimes["autosave 3"])
      .. "' (spaced out, never in a tight loop); the confirmed slot is "
      .. "whichever mtime actually changed, never a prediction",
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "quicksave" then
  print(json.encode(fort_quicksave(args[2], args[3], args[4])))
else
  print("usage: df-overseer-fort quicksave [PRIOR_AUTOSAVE_1 PRIOR_AUTOSAVE_2 PRIOR_AUTOSAVE_3]")
end
