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
-- once per DF process lifetime PER REGISTRATION VERSION, guarded by a _G
-- string keyed on a version constant this file bumps whenever listener code
-- changes (see REGISTRATION_VERSION below, added
-- 2026-09-22, handoffs/2026-09-22-loop-diff-reregister-quicksave-slot.md --
-- a plain boolean guard was the original design and is why the
-- encoding-fix stream's listener changes never took effect on the running
-- process until this fix). Confirmed live 2026-09-10, load-bearing for this
-- whole design: a plain Lua global DOES survive across separate
-- `dfhack-run` invocations within the same running DF process (two
-- independent SSH calls incrementing and reading back the same _G counter
-- returned 1 then 2, not 1 then 1) -- DFHack's Lua state is not reset per
-- CLI invocation. The event log itself is intentionally a plain _G table,
-- not dfhack.persistent-backed: it is meant to be ephemeral/session-scoped
-- ("everything since my last call this game-process-lifetime"), not
-- durable across a restart, and nothing in this design needs it to survive
-- one.
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
-- KNOWLEDGE-SCOPE FIX, 2026-09-16 (handoffs/2026-09-16-knowledge-scope-audit.md,
-- decisions/DECISIONS.md 2026-09-16 "Agents may only know what a vanilla
-- player could know"): research/2026-09-16-player-visibility.md tags
-- UNIT_DEATH omniscient outright -- it "fires engine-wide for ANY unit's
-- death", and this file's own long-standing honest gap note already admits
-- "the kea's own death generated no report at all", i.e. this raw event is
-- broader than the announcement layer and was never gated by visibility at
-- all. UNIT_ATTACK is flagged "player_derivable, leaning omniscient" --
-- structured attacker/defender/wound data with no stated visibility
-- condition, not independently confirmed either way.
--
-- FIXED by gating both listeners on dfhack.units.isHidden of the unit(s)
-- involved, at the moment the event fires: a dead/attacked unit that
-- isHidden reports true for (tile-hidden, or ambushing and not
-- fort-controlled -- research doc §5) is not logged. UNIT_DEATH checks the
-- one unit; UNIT_ATTACK checks BOTH attacker and defender and requires
-- BOTH visible, since a vanilla player witnessing a fight needs the whole
-- scene visible, not just one side -- an ambusher striking a visible
-- citizen is exactly the case a vanilla player would NOT get to see (the
-- ambush is the point of being hidden). A unit lookup failure (already dead
-- and deallocated by the time the listener runs, or any pcall failure) is
-- treated as hidden, the safe default, never the permissive one. JOB_COMPLETED
-- and the REPORT branch are UNCHANGED -- both are already player-visible by
-- construction (a player's own dwarf's job; an entry DF already put in the
-- player's own gamelog), per the research doc's own classification.
--
-- VERIFIED ONLY BY SOURCE READING, stated plainly per the handoff's own
-- instruction: live event firing needs the clock running, and the fort
-- stays paused for this whole audit (constraint, this handoff), so neither
-- gate was exercised against a real death or a real attack this session.
-- dfhack.units.isHidden itself is already live-verified elsewhere in this
-- project (df-overseer-threat.lua, df-overseer-labor.lua, both fixed the
-- same day) -- what is NOT verified here is that a real UNIT_DEATH/
-- UNIT_ATTACK event still carries a resolvable df.unit.find(id) at the
-- instant the listener runs (a dead unit could plausibly already be
-- deallocated) -- if it does not, the pcall failure path above excludes it,
-- which is safe (favors under- over over-reporting) but unverified as to
-- whether it silently excludes MORE than intended, e.g. every death, not
-- just hidden ones. Flagged as an open question for the next live-verification
-- session with the fort actually running.
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
local landmarks_mod = reqscript('df-overseer-landmarks')
local textutil = reqscript('df-overseer-textutil')
local ledger_mod = reqscript('df-overseer-ledger')
local announcement_levels = reqscript('df-overseer-announcement-levels')

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

-- ADDED 2026-09-23 (handoffs/2026-09-23-attention-tiers-ingame.md item 3):
-- theft was invisible to this file. CREATURE_STEALS_OBJECT (a kea actually
-- taking something) was not tagged at all -- confirmed absent by grep before
-- this change, consistent with research/2026-09-16-player-visibility.md's
-- own S:9 listing it as a named grey zone. Added here plus every sibling id
-- research/data/2026-09-23-announcement-severity.yaml's own `alert_type:
-- CRIME` family marks `notice` or higher that this table omitted (checked
-- against every CRIME-tagged id in that file, not just the one the handoff
-- named): MISCHIEF_LEVER/PLATE/CAGE/CHAIN (a lever/plate/cage/chain pulled
-- or triggered -- the vanilla-legal fallback for a MISCHIEVOUS-class
-- creature research/2026-09-23-wildlife-threat-classes.md S:D/E2 says this
-- project has no legal way to see directly), CITIZEN_SNATCHED (a citizen
-- taken, already `pause`-level in that same file and in
-- df-overseer-announcement-levels.lua's PAUSE_REPORT_IDS -- tagged here too
-- so `since`/`recent-combat` can surface it in the full event log, not just
-- the tripwire latch), and CRIME_WITNESS_HANDOFF/STOLEN/ITEM_MOVED/
-- ITEM_MISSING (a witnessed theft-adjacent event). AMBUSH_THIEF/
-- AMBUSH_SNATCHER (ids 55, 60) were already covered by the "ambush" tag
-- above; not duplicated here.
tag_category("theft", 145)  -- CREATURE_STEALS_OBJECT
tag_category("mischief", 75, 76, 77, 78)  -- MISCHIEF_LEVER/PLATE/CAGE/CHAIN
tag_category("snatched", 252)  -- CITIZEN_SNATCHED
tag_category("crime_witness", 332, 333, 334, 335)  -- CRIME_WITNESS_*

local function category_of(rtype)
  return REPORT_CATEGORY[rtype]
end

-- REGISTRATION VERSION, 2026-09-22 (handoffs/2026-09-22-loop-diff-reregister-
-- quicksave-slot.md). Found live by the encoding-fix stream (evals/live/
-- 2026-09-22-loop-game-text-encoding/README.md, "Found live, not fixed"):
-- the old guard was a plain boolean (`_G.__df_overseer_diff_registered`),
-- true forever once set, so a redeploy that changed this file's listener
-- closures never took effect on the already-running DF process -- the
-- eventful callbacks kept firing the PRE-encoding-fix code that never
-- called textutil.to_utf8. Fixed here by keying the guard on a version
-- string instead of a boolean: bump REGISTRATION_VERSION whenever a
-- listener's own code changes, and the block below re-runs, replacing the
-- listeners.
--
-- Why replacement is clean, not layered (the handoff's "if eventful's
-- storage makes clean replacement impossible, stop and report" line):
-- verified by SOURCE READING of the installed eventful plugin's Lua
-- wrapper (hack/lua/plugins/eventful.lua on the Windows install, the
-- closest available copy -- the onX tables themselves and enableEvent are
-- native-plugin-exposed, not defined in that Lua file, so this is not a
-- read of the actual storage implementation). What IS verified: this file
-- already registers every listener as a plain Lua table assignment under a
-- fixed string key (`eventful.onJobCompleted.df_overseer_diff = function
-- ... end`, and likewise onUnitDeath/onReport/onUnitAttack) -- the
-- documented DFHack idiom for eventful (named-slot registration, the same
-- mechanism a script uses to unregister by setting the key to nil).
-- Reassigning a Lua table key always replaces its prior value; this is a
-- language guarantee, not something that depends on eventful's own
-- internal implementation, PROVIDED eventful fires by reading through this
-- same table by key at dispatch time rather than keeping a separate
-- append-only list captured at registration -- which the named-slot
-- registration/unregistration idiom implies but this stream could not
-- confirm from the native plugin's source. Not independently verified
-- live this stream (no VM in the offline-code phase); the live deploy step
-- checks handler counts under each key before/after to catch layering if
-- this assumption is wrong.
-- Bumped 2026-09-23 (handoffs/2026-09-23-attention-tiers-ingame.md item 3/4):
-- REPORT_CATEGORY gained the theft/mischief/snatched/crime_witness tags and
-- onReport's own closure gained the ledger write for a "theft" category --
-- both are listener-code changes, so per this constant's own documented
-- rule the guard below must re-run and replace the already-registered
-- listeners on the next load, not keep serving the pre-2026-09-23 closure.
local REGISTRATION_VERSION = "2026-09-23-diff-theft-ledger-1"

if _G.__df_overseer_diff_registered_version ~= REGISTRATION_VERSION then
  _G.__df_overseer_diff_log = _G.__df_overseer_diff_log or {}
  _G.__df_overseer_diff_next_id = _G.__df_overseer_diff_next_id or 1

  -- One-time conversion of legacy entries: any entry already in the log
  -- with no `encoding_version` field was logged by a closure that predates
  -- this file's own encoding_version bookkeeping, i.e. by the pre-encoding-
  -- fix listeners (raw CP437 `detail`, per the encoding-fix stream's live
  -- finding, 13 of 1210 entries on Uniboslan). Convert each such entry's
  -- `detail` exactly once via textutil.to_utf8 (the same helper every
  -- other game-text call site in this project uses; safe on already-ASCII
  -- text per its own header, since ASCII bytes pass through df2utf
  -- unchanged) and stamp it so no future re-registration ever touches it
  -- again -- converting an already-UTF-8 string with df2utf mangles it, so
  -- this marker is the only thing standing between "convert once" and
  -- "convert every redeploy". A fresh entry from THIS version's listeners
  -- (below) is always stamped at creation, so it can never be mistaken for
  -- an unconverted legacy one, no matter how many future version bumps
  -- happen.
  for _, entry in ipairs(_G.__df_overseer_diff_log) do
    if entry.encoding_version == nil then
      if entry.detail then
        entry.detail = textutil.to_utf8(entry.detail)
      end
      entry.encoding_version = "legacy-converted"
    end
  end

  local function log_event(entry)
    entry.id = _G.__df_overseer_diff_next_id
    entry.at_tick = dfhack.world.ReadCurrentTick()
    entry.encoding_version = REGISTRATION_VERSION
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
    log_event({type = "JOB_COMPLETED", detail = ok and textutil.to_utf8(name) or "unknown job"})
  end

  -- KNOWLEDGE-SCOPE FIX, 2026-09-16: excludes any death dfhack.units.isHidden
  -- reports true for, or where the unit can't even be resolved (safe
  -- default) -- see header.
  local function unit_is_hidden(unit_id)
    local unit = df.unit.find(unit_id)
    if not unit then
      return true
    end
    local ok, hidden = pcall(dfhack.units.isHidden, unit)
    return (not ok) or hidden
  end

  eventful.enableEvent(eventful.eventType.UNIT_DEATH, 10)
  eventful.onUnitDeath.df_overseer_diff = function(unit_id)
    if unit_is_hidden(unit_id) then
      return
    end
    local ok, name = pcall(function()
      return textutil.to_utf8(dfhack.translation.translateName(
        dfhack.units.getVisibleName(df.unit.find(unit_id))))
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
              df.announcement_type[rep.type] or tostring(rep.type), textutil.to_utf8(rep.text)),
          })
        end
        -- ADDED 2026-09-23 (handoffs/2026-09-23-attention-tiers-ingame.md
        -- item 4, research/2026-09-23-wildlife-threat-classes.md S:E3(4)):
        -- feed a theft outcome into the observation ledger from the SAME
        -- report stream that already drives the "theft" category above,
        -- rather than inventing a second detector. HONEST LIMITATION, named
        -- rather than guessed around: df.report carries no structured race
        -- field, only English text (rep.text) -- attributing "which race
        -- did this" would need parsing that text against a species-name
        -- dictionary, not attempted this stream (no VM to verify against
        -- real report text, and a wrong guess is worse than an honest
        -- "unknown"). Recorded under race "unknown" so the outcome is never
        -- lost, flagged here and in this stream's Result as a real,
        -- follow-on gap. Never pauses or wakes: record() is a pure
        -- aggregate write (see df-overseer-ledger.lua's own header).
        if cat == "theft" then
          pcall(ledger_mod.record, "unknown", dfhack.world.ReadCurrentTick(), nil, "theft")
        end

        -- RECONCILED 2026-09-23 with the already-merged sibling conductor
        -- stream (handoffs/2026-09-23-stalled-order-poller.md): that stream
        -- built conductor/cycle.py's _classify_slow_announcements against an
        -- ASSUMED diff.since event shape for the 23 slow-level announcement
        -- ids, since the two streams could not talk directly. This is that
        -- shape, emitted for real: a newly-arrived report whose type is one
        -- of df-overseer-announcement-levels.lua's SLOW_REPORT_IDS logs a
        -- SEPARATE event (not folded into the "REPORT" event above, and not
        -- gated on `cat` -- a slow id may or may not also carry a
        -- REPORT_CATEGORY tag, e.g. AMBUSH_MISCHIEVOUS does via "ambush",
        -- most others do not). Handoff item 2's own line ("not yours to act
        -- on") is respected: this only LOGS the event into the same
        -- diff.since stream every other role already reads through its own
        -- cursor -- it never pauses, never changes FPS, never decides who
        -- wakes. That decision is conductor/cycle.py's, already built.
        local ok_slow, slow_info = pcall(function() return announcement_levels.SLOW_REPORT_IDS[rep.type] end)
        if ok_slow and slow_info then
          log_event({
            type = "announcement_slow",
            announcement_type = slow_info.name,
            tick = dfhack.world.ReadCurrentTick(),
            wake = slow_info.wake,
            detail = slow_info.detail,
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
    -- KNOWLEDGE-SCOPE FIX, 2026-09-16: logged only if BOTH participants are
    -- visible -- a vanilla player witnessing a fight needs the whole scene
    -- visible, not just one side. See header.
    if unit_is_hidden(attacker_id) or unit_is_hidden(defender_id) then
      return
    end
    local function unit_desc(id)
      local u = df.unit.find(id)
      if not u then return "unit " .. tostring(id) end
      local ok, name = pcall(function()
        return textutil.to_utf8(dfhack.translation.translateName(dfhack.units.getVisibleName(u)))
      end)
      local race = textutil.to_utf8(select(2, pcall(dfhack.units.getRaceName, u)) or "?")
      return string.format("%s (%s, id=%d)", ok and name ~= "" and name or race, race, id)
    end
    log_event({
      type = "UNIT_ATTACK",
      detail = string.format("%s wounded %s (wound id=%s)",
        unit_desc(attacker_id), unit_desc(defender_id), tostring(wound_id)),
    })
  end

  _G.__df_overseer_diff_registered_version = REGISTRATION_VERSION
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

-- FIXED 2026-09-12 (found building scripts/dfhack/TOOLS.yaml's
-- coordinate-bearing audit): this used to print rep.pos.x/y/z raw -- an
-- undocumented design-commitment-#1 violation, the same category of issue
-- as the already-known df-overseer-labor unit-status leak, just never
-- flagged until the manifest's per-command audit surfaced it. Now resolves
-- near_landmark/direction/distance_tiles via df-overseer-landmarks.lua's
-- nearest_landmark (reqscript'd), same as every other perception tool.
-- Best-effort: a resolution failure falls back to an honest "unknown"
-- rather than crashing recent-combat/since-report entirely. Not yet
-- redeployed to VM 103 -- code fix pending the next deploy/live-verify pass.
local function report_line(rep)
  local cat = category_of(rep.type)
  local type_name = df.announcement_type[rep.type] or tostring(rep.type)
  local near, direction, distance = "unknown", "?", -1
  local ok, info = pcall(landmarks_mod.nearest_landmark, rep.pos.x, rep.pos.y, rep.pos.z)
  if ok and info then
    near, direction, distance = info.name, info.direction, info.distance_tiles
  end
  return string.format(
    "COMBAT id=%d year=%d time=%d category=%q type=%q near_landmark=%q"
      .. " direction=%s distance_tiles=%d text=%q",
    rep.id, rep.year, rep.time, cat, type_name, near, direction, distance, textutil.to_utf8(rep.text))
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
