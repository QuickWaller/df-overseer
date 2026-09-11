-- df-overseer-combat.lua
--
-- Real combat/threat detection -- the gap found and documented 2026-09-11
-- (decisions/DECISIONS.md, "First real combat on Uniboslan"): a real kea
-- attacked the fort, dogs and a citizen fisherdwarf fought and killed it,
-- and `unit-status hostile` (df-overseer-labor.lua) never saw any of it,
-- before, during, or after -- it only ever reported 4 harmless deep-cavern
-- demons via dfhack.units.isDanger/isInvader. research/2026-08-25-spatial-
-- perception.md §5's inline correction concluded the right fix is almost
-- certainly event-driven (docs/PURPOSE.md build order item 5, get_diff_since
-- via eventful), not a better static predicate, since "something attacked
-- something" is inherently an event, not a fact queryable out of current
-- world state. This file is that investigation's prototype.
--
-- EXHAUSTIVE PREDICATE CHECK, done before writing anything below (task
-- explicitly asked for this, not just accepting the known gap): every
-- dfhack.units.* function in `hack/docs/docs/dev/Lua API.txt` matching
-- danger|invader|combat|attack|fight|aggress|hostile|threat is isDanger,
-- isGreatDanger, isInvader -- already known-bad -- plus one NOT previously
-- checked: isAgitated(unit) ("the unit is an agitated creature"), which
-- isDanger's own doc text claims to fold in ("This includes... agitated
-- wildlife"). Checked live against the actual kea (unit id 321, confirmed
-- dfhack.units.isDead == true, matching the decision-log narrative):
-- isAgitated == false, isDanger == false, isWildlife == true. So the kea's
-- attack was not an "agitated wildlife" state DF itself flagged either --
-- it was bog-standard aggressive wildlife behavior with no unit-level
-- static flag at all. There is no sibling predicate this repo missed;
-- static per-unit state genuinely does not carry this signal for this
-- case, confirming the event-driven conclusion rather than assuming it.
--
-- TWO MECHANISMS INVESTIGATED, BOTH VERIFIED LIVE, kept as two commands
-- because they have different, complementary strengths:
--
-- (1) `recent-combat` / `since-report` -- poll df.global.world.status.reports.
--     Verified real and structured, not gamelog.txt text scraping: each
--     report is a native DFHack struct with `id` (monotonic, matches
--     world.status.next_report_id), `type` (a df.announcement_type enum
--     value -- e.g. 38 = COMBAT_STRIKE_DETAILS, 11 = COMBAT_JUMP_DODGE_
--     STRIKE -- not a raw string DFHack leaves for us to pattern-match),
--     `year`, `time` (in-game tick), `pos` (coord, real x/y/z, confirmed
--     live: 99,96,170 for the kea fight), and `text` (the same line
--     gamelog.txt carries). Live-replayed against Uniboslan's actual
--     stored reports: of 34 total reports since embark, exactly 21 carry
--     a type this script classifies as combat/threat, and reconstruct the
--     kea fight blow-by-blow end to end -- dog scratches/bites, the
--     fisherdwarf's iron pick lodging in the wound, "an artery... has
--     been opened," the fatal "the lower spine collapses" -- matching
--     decisions/DECISIONS.md's gamelog.txt-derived narrative exactly, but
--     arriving as typed structs to filter on an integer set, not verb
--     phrases to grep. This needs no registration, no daemon, and works
--     purely retrospectively -- it already had the whole historical fight
--     sitting in memory while the fort was paused, no unpause required to
--     verify it.
--
--     GENUINE GAP, not glossed over: the kea's own death generated NO
--     report at all. `PET_DEATH`/`CITIZEN_DEATH` announcement types exist
--     but only cover tame/citizen units; ordinary never-tamed wildlife
--     gets no death announcement in this structure. So `recent-combat`
--     sees the entire fight in rich detail but cannot, on its own, assert
--     "and it died" for a wild animal -- confirming death needs a
--     separate live dfhack.units.isDead() check on a unit id pulled from
--     elsewhere (e.g. the event log below, or a caller-supplied id).
--
--     SCALING CAVEAT, honestly flagged, not solved here: world.status.
--     reports is DFHack's live backing store for the *entire* gamelog, so
--     like gamelog.txt itself it grows unboundedly over a long fort ("hundreds,
--     not millions," per the job-list precedent in the research doc, is a
--     reasonable guess but was NOT measured against a multi-year fort this
--     session). `since-report` scans from the front each call, which is
--     fine now (34 reports, fort is 6 in-game months old) but would want a
--     smarter starting point (id/index are 1:1 in every case checked live
--     this session, so a direct-index seek is possible) before trusting it
--     unmodified against a year-5 fort.
--
-- (2) `event-log since CURSOR` -- a real eventful-registered listener on
--     onReport (fires for every report, verified in the doc: "This happens
--     more often than you probably think") and onUnitAttack (fires with
--     structured attackerId/defenderId/woundId -- real unit ids, not names
--     parsed out of text) and onUnitDeath, logged into a plain _G ring
--     buffer with a monotonic id, matching get_diff_since's {cursor,
--     events} shape from the research spec almost exactly.
--
--     VERIFIED LIVE, not assumed: (a) eventful.plug.so is loaded and
--     require("plugins.eventful") succeeds; (b) a plain Lua _G value DOES
--     survive across separate `dfhack-run` invocations within the same
--     running DF process -- confirmed directly this session with a fresh,
--     independent counter test (two separate SSH/dfhack-run calls
--     incrementing and reading back the same _G value returned 1 then 2,
--     not 1 then 1 -- registration in one call really is visible to a
--     later call, not re-initialized each time); (c) with the fort briefly
--     unpaused for this specific test (paused before, re-paused and
--     quicksaved after -- see decisions/DECISIONS.md this date for the
--     exact before/after pause-state and save-mtime evidence), the
--     registered onReport listener actually fired for real newly-created
--     reports during that window, and its logged entries' ids/text matched
--     world.status.reports' own newly-appended entries for the same
--     window -- i.e. the *delivery* mechanism itself was exercised end to
--     end, not just the registration call succeeding without erroring.
--     This closes the one gap the (separate, unmerged
--     perception-layer-experiments branch's) df-overseer-diff.lua
--     explicitly left open for its own JOB_COMPLETED/UNIT_DEATH listeners:
--     "a real eventful-triggered callback actually firing... is NOT
--     verified." For onUnitAttack specifically: no real attack happened
--     during this session's brief test window (the fort's animals did not
--     fight again in the ~15 unpaused seconds used), so onUnitAttack's
--     *delivery* remains verified only by doc text and by the same proven
--     _G-persistence/registration mechanism onReport now demonstrates end
--     to end -- flagged as the honest remaining gap, not claimed as fully
--     closed.
--
-- NOTE ON A DISCREPANCY FOUND WHILE BUILDING THIS: VM 103's
-- hack/scripts/ already has df-overseer-diff.lua, -overview.lua,
-- -chokepoints.lua, -connectivity.lua, -landmarks.lua, -openarea.lua,
-- -stuckjobs.lua deployed and live (dated 2026-09-10) -- these are the
-- perception-layer-experiments branch's build-order items 2-8, not part of
-- this repo's `main` checkout (confirmed: none of those files exist in
-- this repo's scripts/dfhack/ on main). The live VM is running code from an
-- unmerged branch that CLAUDE.md's status banner says was "deliberately
-- kept off main." This script is deliberately kept independent of that
-- branch's df-overseer-diff.lua (different file, different command names)
-- rather than extending it, so as not to blur that branch-separation
-- decision from a main-branch task -- flagged for the orchestrator to
-- reconcile, not resolved here.
--
-- Usage: ./dfhack-run df-overseer-combat <command> [args...]
--   recent-combat [N]
--     -- last N combat/threat-family reports (default 20), oldest first.
--   since-report REPORT_ID
--     -- every combat/threat-family report with id > REPORT_ID, plus a
--        cursor line to pass back next call. Poll-based, no registration.
--   event-log since CURSOR
--     -- drains the eventful-registered ring buffer (REPORT/UNIT_ATTACK/
--        UNIT_DEATH) for entries with id > CURSOR. Registers listeners on
--        first use (once per DF process lifetime, _G-guarded); events
--        before registration are not retroactively captured -- use
--        recent-combat/since-report for history, event-log for going
--        forward from whenever this was first called.

local args = {...}
local cmd = args[1]

-- df.announcement_type ids this fort-defense caller actually needs to
-- distinguish, grouped into categories. Verified live against this
-- install's real enum (df.announcement_type), not guessed from names
-- alone -- every id below was read back from the live enum and, for the
-- "strike"/"miss_or_block"/"charge"/"grapple"/"status"/"hostile_speech"
-- groups, cross-checked against the 21 real reports that reconstruct the
-- kea fight.
local CATEGORY = {}
local function tag(category, ...)
  for _, id in ipairs({...}) do CATEGORY[id] = category end
end

-- Blow-by-blow combat (the family that reconstructs a fight in detail)
tag("strike", 38, 39)                                   -- COMBAT_STRIKE_DETAILS(_2)
tag("miss_or_block", 10, 11, 12, 13, 14, 15)            -- dodge/block/parry/counterstrike
tag("charge", 8, 9, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25)
tag("grapple", 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 42, 43, 167)
tag("status", 40, 41, 44, 45, 46, 47, 48, 125, 166)     -- enraged/stuck-in/KO/stunned/pain/interrupted
tag("hostile_speech", 177)                              -- CONFLICT_CONVERSATION

-- Higher-level threat announcements -- not blow-by-blow, but exactly the
-- "something is attacking" signal isDanger/isInvader/isAgitated all
-- missed for ordinary wildlife; these cover the cases they're aimed at
-- (sieges, ambushes, undead, tantrums) instead.
tag("ambush", 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 95, 322)
tag("night_attack", 136, 137, 138)
tag("undead_or_ghost", 139, 150)
tag("berserk_or_tantrum", 96, 183, 285)
tag("death", 106, 107)  -- CITIZEN_DEATH, PET_DEATH -- wild animals not covered, see header

local function category_of(rtype)
  return CATEGORY[rtype]
end

local function report_line(rep)
  local cat = category_of(rep.type)
  local type_name = df.announcement_type[rep.type] or tostring(rep.type)
  return string.format(
    "COMBAT id=%d year=%d time=%d category=%q type=%q pos=%d,%d,%d text=%q",
    rep.id, rep.year, rep.time, cat, type_name,
    rep.pos.x, rep.pos.y, rep.pos.z, rep.text)
end

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
    print("usage: df-overseer-combat since-report REPORT_ID")
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

-- Event-driven layer. Registration happens once per DF process lifetime,
-- guarded by a plain _G flag -- confirmed live this session that a plain
-- Lua global survives across separate dfhack-run invocations within the
-- same running DF process (see header). The log itself is a plain _G
-- table, not dfhack.persistent-backed: ephemeral/session-scoped by design,
-- matching the (separate, unmerged) df-overseer-diff.lua's own stated
-- reasoning for the same choice.
local function ensure_event_log()
  if _G.__df_overseer_combat_registered then return end

  local eventful = require('plugins.eventful')
  _G.__df_overseer_combat_log = {}
  _G.__df_overseer_combat_next_id = 1

  local function log_event(etype, at_tick, detail)
    local entry = {
      id = _G.__df_overseer_combat_next_id,
      type = etype,
      at_tick = at_tick,
      detail = detail,
    }
    _G.__df_overseer_combat_next_id = _G.__df_overseer_combat_next_id + 1
    table.insert(_G.__df_overseer_combat_log, entry)
  end

  eventful.enableEvent(eventful.eventType.REPORT, 1)
  eventful.onReport.df_overseer_combat = function(report_id)
    local reports = df.global.world.status.reports
    -- reports[] is indexed 0..#-1; id has been 1:1 with index+1 in every
    -- case checked live this session, but don't hard-assume it -- scan
    -- from the end (the new report is always the newest).
    for i = #reports - 1, 0, -1 do
      local rep = reports[i]
      if rep.id == report_id then
        local cat = category_of(rep.type)
        if cat then
          log_event("REPORT", rep.time,
            string.format("category=%s type=%s text=%s", cat,
              df.announcement_type[rep.type] or tostring(rep.type), rep.text))
        end
        break
      elseif rep.id < report_id then
        break
      end
    end
  end

  eventful.enableEvent(eventful.eventType.UNIT_ATTACK, 1)
  eventful.onUnitAttack.df_overseer_combat = function(attacker_id, defender_id, wound_id)
    local function unit_desc(id)
      local u = df.unit.find(id)
      if not u then return "unit " .. tostring(id) end
      local ok, name = pcall(function()
        return dfhack.translation.translateName(dfhack.units.getVisibleName(u))
      end)
      local race = select(2, pcall(dfhack.units.getRaceName, u)) or "?"
      return string.format("%s (%s, id=%d)", ok and name ~= "" and name or race, race, id)
    end
    log_event("UNIT_ATTACK", dfhack.world.ReadCurrentTick(),
      string.format("%s wounded %s (wound id=%s)",
        unit_desc(attacker_id), unit_desc(defender_id), tostring(wound_id)))
  end

  eventful.enableEvent(eventful.eventType.UNIT_DEATH, 1)
  eventful.onUnitDeath.df_overseer_combat = function(unit_id)
    local u = df.unit.find(unit_id)
    local ok, name = pcall(function()
      return dfhack.translation.translateName(dfhack.units.getVisibleName(u))
    end)
    local race = u and select(2, pcall(dfhack.units.getRaceName, u)) or "?"
    log_event("UNIT_DEATH", dfhack.world.ReadCurrentTick(),
      string.format("%s (%s, id=%d) died", ok and name ~= "" and name or race, race, unit_id))
  end

  _G.__df_overseer_combat_registered = true
end

local function event_log_since(cursor_str)
  local cursor = tonumber(cursor_str)
  if not cursor then
    print("usage: df-overseer-combat event-log since CURSOR")
    return
  end
  ensure_event_log()
  local printed = 0
  local last_id = cursor
  for _, e in ipairs(_G.__df_overseer_combat_log) do
    if e.id > cursor then
      print(string.format("EVENT id=%d type=%q at_tick=%d detail=%q",
        e.id, e.type, e.at_tick, e.detail))
      printed = printed + 1
    end
    if e.id > last_id then last_id = e.id end
  end
  print(string.format("-- cursor=%d %d new event(s) --", last_id, printed))
end

if cmd == "recent-combat" then
  recent_combat(args[2])
elseif cmd == "since-report" then
  since_report(args[2])
elseif cmd == "event-log" and args[2] == "since" then
  event_log_since(args[3])
elseif cmd == "event-log" and args[2] == "register" then
  -- Registers the listeners without draining -- useful to call once
  -- ahead of time so nothing is missed between registration and the
  -- first `since` poll.
  ensure_event_log()
  print(string.format("registered (next_id=%d)", _G.__df_overseer_combat_next_id))
else
  print("usage: df-overseer-combat <recent-combat [N]|since-report REPORT_ID"
    .. "|event-log register|event-log since CURSOR>")
end
