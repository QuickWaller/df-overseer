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
-- Registration (eventful.enableEvent + the onX listener tables) happens
-- once per DF process lifetime, guarded by a plain _G flag. Confirmed live
-- 2026-09-10, load-bearing for this whole design: a plain Lua global DOES
-- survive across separate `dfhack-run` invocations within the same running
-- DF process (two independent SSH calls incrementing and reading back the
-- same _G counter returned 1 then 2, not 1 then 1) -- DFHack's Lua state is
-- not reset per CLI invocation. The event log itself is intentionally a
-- plain _G table, not dfhack.persistent-backed: it is meant to be
-- ephemeral/session-scoped ("everything since my last call this
-- game-process-lifetime"), not durable across a restart, and nothing in
-- this design needs it to survive one.
--
-- FOLDED IN 2026-09-12, merging perception-layer-experiments into main:
-- this file originally wired only JOB_COMPLETED/UNIT_DEATH; a separate,
-- main-branch investigation (df-overseer-combat.lua, built the same day a
-- real kea attack went undetected by unit-status hostile) independently
-- built REPORT/UNIT_ATTACK registration into its OWN _G log, plus a
-- retrospective, registration-free poll over world.status.reports
-- (recent-combat/since-report). The two files were kept deliberately
-- separate at the time specifically to avoid a main-branch task touching
-- the still-unmerged branch -- see decisions/DECISIONS.md's row on
-- df-overseer-combat.lua. That reason no longer applies once both live in
-- the same tree, and running two independent eventful registrations for
-- the same UNIT_DEATH event into two different _G ring buffers was real,
-- avoidable waste, not a feature. combat.lua's exhaustive predicate check
-- (every dfhack.units.* function matching danger|invader|combat|attack|
-- fight|aggress|hostile|threat, checked live against the actual kea) is
-- preserved in its own commit history, not repeated here. Four event
-- types now share one registration path and one log: JOB_COMPLETED,
-- UNIT_DEATH, REPORT (tagged into combat/threat categories, from
-- combat.lua's own category table, verified against 21 real reports that
-- reconstructed the kea fight blow-by-blow), and UNIT_ATTACK (structured
-- attacker/defender/wound ids, not text parsing). eventful exposes more
-- types still (BUILDING, INTERACTION, INVENTORY_CHANGE, JOB_INITIATED,
-- SYNDROME, UNIT_NEW_ACTIVE, UNLOAD) -- deliberately not wired up, add
-- more as a real consumer needs them, matching this project's "don't
-- build past what's used" style.
--
-- VERIFIED LIVE (combat.lua's investigation, both mechanisms): (a)
-- `recent-combat`/`since-report` read df.global.world.status.reports
-- directly -- each report is a native struct (id, type as a real
-- df.announcement_type enum value, year, time, pos, text), not
-- gamelog.txt text-scraping; live-replayed against Uniboslan's actual 34
-- stored reports, 21 matched a combat/threat category and reconstructed
-- the kea fight end to end. This needs no registration and works
-- retrospectively even while paused. GENUINE GAP, not glossed over: the
-- kea's own death generated no report at all (PET_DEATH/CITIZEN_DEATH
-- only cover tame/citizen units) -- confirming death for wild animals
-- needs a separate dfhack.units.isDead() check, e.g. via the UNIT_DEATH
-- event below. SCALING CAVEAT: world.status.reports is DFHack's live
-- backing store for the whole gamelog and grows unboundedly over a long
-- fort ("hundreds, not millions" is a reasonable but unmeasured guess);
-- since-report scans from the front each call, fine at 34 reports, would
-- want a smarter starting point before trusting it against a year-5 fort.
-- (b) the eventful onReport/onUnitAttack path: eventful.plug.so loads,
-- a plain _G value survives across separate dfhack-run invocations
-- (independently re-confirmed the same session as this fold), and with
-- the fort briefly unpaused, the registered onReport listener actually
-- fired for real newly-created reports, matching world.status.reports'
-- own newly-appended entries for the same window -- the delivery
-- mechanism itself was exercised end to end, not just the registration
-- call succeeding. onUnitAttack's real delivery specifically remains
-- verified only by the same proven _G-persistence/registration mechanism
-- plus doc text, not a real attack during a live test window -- flagged
-- honestly, not claimed as fully closed.
--
-- HONEST GAP CARRIED FORWARD from this file's original JOB_COMPLETED/
-- UNIT_DEATH-only version: those two specifically were verified via
-- registration-not-erroring and hand-calling the listener directly, not
-- a real trigger firing -- see decisions/DECISIONS.md's original
-- get_diff_since row for the full trail. REPORT's real delivery is now
-- independently confirmed (above); UNIT_DEATH's is not.
--
-- Usage: ./dfhack-run df-overseer-diff since CURSOR   -- CURSOR: integer, 0 for everything
--        ./dfhack-run df-overseer-diff recent-combat [N]
--          -- last N combat/threat-family reports (default 20), oldest
--             first. Poll-based, no registration, works even while paused.
--        ./dfhack-run df-overseer-diff since-report REPORT_ID
--          -- every combat/threat-family report with id > REPORT_ID, plus
--             a cursor line to pass back next call.

local json = require('json')
local eventful = require('plugins.eventful')

-- df.announcement_type ids this fort-defense caller needs to distinguish,
-- grouped into categories. Verified live against this install's real enum
-- (df.announcement_type), not guessed from names alone -- every id below
-- was read back from the live enum and, for the "strike"/"miss_or_block"/
-- "charge"/"grapple"/"status"/"hostile_speech" groups, cross-checked
-- against the 21 real reports that reconstruct the kea fight.
local REPORT_CATEGORY = {}
local function tag_category(category, ...)
  for _, id in ipairs({...}) do REPORT_CATEGORY[id] = category end
end

-- Blow-by-blow combat (the family that reconstructs a fight in detail)
tag_category("strike", 38, 39)                          -- COMBAT_STRIKE_DETAILS(_2)
tag_category("miss_or_block", 10, 11, 12, 13, 14, 15)    -- dodge/block/parry/counterstrike
tag_category("charge", 8, 9, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25)
tag_category("grapple", 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 42, 43, 167)
tag_category("status", 40, 41, 44, 45, 46, 47, 48, 125, 166)  -- enraged/stuck-in/KO/stunned/pain/interrupted
tag_category("hostile_speech", 177)                      -- CONFLICT_CONVERSATION

-- Higher-level threat announcements -- not blow-by-blow, but exactly the
-- "something is attacking" signal isDanger/isInvader/isAgitated all miss
-- for ordinary wildlife; these cover the cases they're aimed at (sieges,
-- ambushes, undead, tantrums) instead.
tag_category("ambush", 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 95, 322)
tag_category("night_attack", 136, 137, 138)
tag_category("undead_or_ghost", 139, 150)
tag_category("berserk_or_tantrum", 96, 183, 285)
tag_category("death", 106, 107)  -- CITIZEN_DEATH, PET_DEATH -- wild animals not covered, see header

local function category_of(rtype)
  return REPORT_CATEGORY[rtype]
end

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
  -- the HONEST GAP notes above.
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

  eventful.enableEvent(eventful.eventType.REPORT, 1)
  eventful.onReport.df_overseer_diff = function(report_id)
    local reports = df.global.world.status.reports
    -- reports[] is indexed 0..#-1; id has been 1:1 with index+1 in every
    -- case checked live, but don't hard-assume it -- scan from the end
    -- (the new report is always the newest).
    for i = #reports - 1, 0, -1 do
      local rep = reports[i]
      if rep.id == report_id then
        local cat = category_of(rep.type)
        if cat then
          log_event({
            type = "REPORT",
            detail = string.format("category=%s type=%s text=%s", cat,
              df.announcement_type[rep.type] or tostring(rep.type), rep.text),
          })
        end
        break
      elseif rep.id < report_id then
        break
      end
    end
  end

  eventful.enableEvent(eventful.eventType.UNIT_ATTACK, 1)
  eventful.onUnitAttack.df_overseer_diff = function(attacker_id, defender_id, wound_id)
    local function unit_desc(id)
      local u = df.unit.find(id)
      if not u then return "unit " .. tostring(id) end
      local ok, name = pcall(function()
        return dfhack.translation.translateName(dfhack.units.getVisibleName(u))
      end)
      local race = select(2, pcall(dfhack.units.getRaceName, u)) or "?"
      return string.format("%s (%s, id=%d)", ok and name ~= "" and name or race, race, id)
    end
    log_event({
      type = "UNIT_ATTACK",
      detail = string.format("%s wounded %s (wound id=%s)",
        unit_desc(attacker_id), unit_desc(defender_id), tostring(wound_id)),
    })
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

local function report_line(rep)
  local cat = category_of(rep.type)
  local type_name = df.announcement_type[rep.type] or tostring(rep.type)
  return string.format(
    "COMBAT id=%d year=%d time=%d category=%q type=%q pos=%d,%d,%d text=%q",
    rep.id, rep.year, rep.time, cat, type_name,
    rep.pos.x, rep.pos.y, rep.pos.z, rep.text)
end

-- Retrospective, registration-free poll over world.status.reports -- see
-- the header for why this is kept distinct from the eventful-based log
-- above rather than folded into it: it answers a different question
-- (reconstruct history from the game's own report store, works even
-- while paused) than "what happened since my last call" does.
local function recent_combat(n)
  n = tonumber(n) or 20
  local reports = df.global.world.status.reports
  local matches = {}
  -- Scan back-to-front and stop once we have n matches -- O(n) in the
  -- common case where combat/threat reports aren't rare, rather than
  -- always paying for the full history every call.
  for i = #reports - 1, 0, -1 do
    local rep = reports[i]
    if category_of(rep.type) then
      table.insert(matches, 1, rep)
      if #matches >= n then break end
    end
  end
  for _, rep in ipairs(matches) do
    print(report_line(rep))
  end
  print(string.format("-- %d combat/threat report(s) of %d total in memory --",
    #matches, #reports))
end

local function since_report(id_str)
  local id = tonumber(id_str)
  if not id then
    print("usage: df-overseer-diff since-report REPORT_ID")
    return
  end
  local reports = df.global.world.status.reports
  local printed = 0
  local last_id = id
  for i = 0, #reports - 1 do
    local rep = reports[i]
    if rep.id > id and category_of(rep.type) then
      print(report_line(rep))
      printed = printed + 1
    end
    if rep.id > last_id then last_id = rep.id end
  end
  print(string.format("-- cursor=%d %d new combat/threat report(s) --", last_id, printed))
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
elseif cmd == "recent-combat" then
  recent_combat(args[2])
elseif cmd == "since-report" then
  since_report(args[2])
else
  print("usage: df-overseer-diff <since CURSOR|recent-combat [N]|since-report REPORT_ID>")
end
