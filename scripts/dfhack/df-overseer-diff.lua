-- df-overseer-diff.lua
--@module = true
--
-- docs/PURPOSE.md build order item 5: get_diff_since() via eventful
-- (research/2026-08-25-spatial-perception.md §3.2/§7/§10) -- push-based
-- event log with a monotonic cursor, the AriGraph-style incremental-update
-- pattern §2.3 cites, not a snapshot-diff (re-reading the whole world every
-- call and comparing). Tier 2 of get_overview (df-overseer-overview.lua)
-- is a fresh snapshot every call, not this; this is the separate,
-- later piece build order item 5 always called out as its own work.
--
-- Registration (eventful.enableEvent + the onJobCompleted/onUnitDeath
-- listener tables) happens once per DF process lifetime, guarded by a
-- plain _G flag. Confirmed live 2026-09-10, load-bearing for this whole
-- design: a plain Lua global DOES survive across separate `dfhack-run`
-- invocations within the same running DF process (two independent SSH
-- calls incrementing and reading back the same _G counter returned 1 then
-- 2, not 1 then 1) -- DFHack's Lua state is not reset per CLI invocation.
-- The event log itself is intentionally a plain _G table, not
-- dfhack.persistent-backed: it is meant to be ephemeral/session-scoped
-- ("everything since my last call this game-process-lifetime"), not
-- durable across a restart, and nothing in this design needs it to
-- survive one.
--
-- Two event sources for this first slice, both confirmed real in the
-- research doc via a grep of stock scripts' actual eventful.eventType
-- usage (not just the docs): JOB_COMPLETED and UNIT_DEATH. eventful
-- exposes more types (BUILDING, INTERACTION, INVENTORY_CHANGE,
-- JOB_INITIATED, REPORT, SYNDROME, UNIT_ATTACK, UNIT_NEW_ACTIVE, UNLOAD) --
-- deliberately not all wired up here; add more as a real consumer needs
-- them, matching this project's "don't build past what's used" style.
--
-- HONEST GAP, not silently skipped: the live fort (Uniboslan) was left
-- paused this session per the user's own "pause when not actively driving
-- it" rule (Working.md durable traps), and no game ticks means no real
-- JOB_COMPLETED/UNIT_DEATH ever fires -- unpausing just to manufacture a
-- test event felt like overstepping a standing instruction for a query
-- tool's own test coverage. What IS verified live: the registration calls
-- themselves don't error, eventful.eventType.JOB_COMPLETED/UNIT_DEATH
-- resolve to real values (3 and 5), and the _G-persistence-across-calls
-- mechanism this whole design depends on. What's NOT verified: a real
-- eventful-triggered callback actually firing and landing in the log via
-- the real subscription path (as opposed to the log/drain logic itself,
-- which was exercised by hand-calling the registered listener directly --
-- see decisions/DECISIONS.md). Worth a real check once the fort is
-- unpaused and playing forward again.
--
-- Usage: ./dfhack-run df-overseer-diff since CURSOR   -- CURSOR: integer, 0 for everything

local json = require('json')
local eventful = require('plugins.eventful')

if not _G.__df_overseer_diff_registered then
  _G.__df_overseer_diff_log = {}
  _G.__df_overseer_diff_next_id = 1

  local function log_event(entry)
    entry.id = _G.__df_overseer_diff_next_id
    entry.at_tick = dfhack.world.ReadCurrentTick()
    _G.__df_overseer_diff_next_id = _G.__df_overseer_diff_next_id + 1
    table.insert(_G.__df_overseer_diff_log, entry)
  end
  -- Exposed (global, no `local`) so this file's own live verification can
  -- call it directly without waiting for a real eventful trigger -- see
  -- the HONEST GAP note above.
  _G.__df_overseer_diff_log_event = log_event

  eventful.enableEvent(eventful.eventType.JOB_COMPLETED, 10)
  eventful.onJobCompleted.df_overseer_diff = function(job)
    local ok, name = pcall(dfhack.job.getName, job)
    log_event({type = "JOB_COMPLETED", detail = ok and name or "unknown job"})
  end

  eventful.enableEvent(eventful.eventType.UNIT_DEATH, 10)
  eventful.onUnitDeath.df_overseer_diff = function(unit_id)
    local ok, name = pcall(function()
      return dfhack.translation.translateName(
        dfhack.units.getVisibleName(df.unit.find(unit_id)))
    end)
    log_event({type = "UNIT_DEATH", detail = ok and name or ("unit " .. tostring(unit_id))})
  end

  _G.__df_overseer_diff_registered = true
end

-- Every event with id > cursor, plus the new cursor to pass next time.
-- Array index is deliberately NOT the cursor (a real implementation
-- trimming old entries to bound memory would invalidate an index-based
-- cursor silently) -- id is monotonic and independent of trimming, per
-- the research doc's own sketch-level caution about this exact mistake.
function drain_since(cursor)
  local events = {}
  for _, e in ipairs(_G.__df_overseer_diff_log) do
    if e.id > cursor then
      table.insert(events, e)
    end
  end
  return events, _G.__df_overseer_diff_next_id - 1
end

-- Same module-load guard as the other df-overseer-*.lua scripts.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "since" then
  local cursor = tonumber(args[2])
  if not cursor then
    print("usage: df-overseer-diff since CURSOR")
  else
    local events, new_cursor = drain_since(cursor)
    print(json.encode({cursor = tostring(new_cursor), events = events}))
  end
else
  print("usage: df-overseer-diff since CURSOR")
end
