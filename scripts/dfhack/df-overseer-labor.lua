-- df-overseer-labor.lua
--
-- Dwarf/labor management perception + action primitives -- the gap found
-- 2026-09-11 (decisions/DECISIONS.md same date): docs/PURPOSE.md's numbered
-- build order (items 0-9) is entirely spatial/perception work; nothing in
-- it covers labor, skills, happiness, or mood. DFHack's own GUI equivalent
-- (`manipulator`, "equivalent to the popular Dwarf Therapist utility") is
-- confirmed `Tags: unavailable` on this exact install (checked live against
-- hack/docs/docs/tools/manipulator.txt and gui/manipulator.txt, both carry
-- the tag) -- it is not a usable fallback here. `autolabor` (a real,
-- loadable compiled plugin -- hack/plugins/autolabor.plug.so is present and
-- its own doc carries no `unavailable` tag, confirmed live) is a sensible
-- baseline underneath this, but enabling it is a separate decision this
-- script does not make.
--
-- This is get_unit_status (research/2026-08-25-spatial-perception.md §5)
-- plus a thin set_labor action tool, following design commitment #2
-- (docs/PURPOSE.md: code does the mechanics -- reading/writing the labor
-- bitfield -- the model does the judgment of which labor to assign, given a
-- ranked/labelled status list, not raw memory).
--
-- FIXED 2026-09-12 (found building scripts/dfhack/TOOLS.yaml's
-- coordinate-bearing audit): this used to print raw pos=x,y,z for every
-- citizen/threat row, a documented placeholder for the time before the
-- landmark system existed on main ("the landmark system this repo's spec
-- calls for lives only on the perception-layer-experiments branch... raw
-- x,y,z is printed instead, a placeholder until that lands"). That branch
-- merged into main 2026-09-12, so the placeholder reason no longer holds --
-- both citizen_line and the hostile-filter branch below now resolve
-- near_landmark/direction/distance_tiles via df-overseer-landmarks.lua's
-- nearest_landmark (reqscript'd), same pattern every other perception tool
-- uses, and never print the raw coordinate. Not yet redeployed to VM 103 --
-- this is a code fix pending the next deploy/live-verify pass.
--
-- Usage: ./dfhack-run df-overseer-labor <command> [args...]
--   unit-status [idle|injured|military|hostile]
--     -- idle/injured/military filter citizens; hostile scans ALL active
--        units on the map for dfhack.units.isDanger() instead (see caveat
--        below) -- these are not the same population. Omit the filter for
--        every living, sane citizen.
--   labors UNIT_ID
--     -- lists every labor currently enabled for one citizen, addressed by
--        dfhack.units id (the id= field in unit-status's own output, NOT a
--        getCitizens() list index -- that ordering is not a stable handle
--        across separate calls).
--   set-labor UNIT_ID LABOR_NAME on|off
--     -- flips one labor bit. LABOR_NAME is a df.unit_labor name (MINE,
--        HAUL_STONE, FARM, ...); `labors` on any citizen shows live examples.
--
-- Verified live against Uniboslan 2026-09-11 (7 citizens, all healthy, no
-- military, Year 30) before writing any of the logic below, not assumed
-- from docs alone: dfhack.units.getCitizens/isCitizen/getPosition/
-- getProfessionName/getReadableName; unit.job.current_job + dfhack.job.getName
-- (nil correctly means idle); unit.body.wounds (a numeric-array field, #-count
-- read 0 across every citizen -- consistent with the prior handover's "all 7
-- alive and behaving normally"); unit.military.squad_id (-1 == unassigned);
-- df.global.world.units.active (53 units on-map this session) combined with
-- dfhack.units.isDanger/isInvader/isOwnCiv (4 flagged, see caveat);
-- unit.status.labors as a genuine indexable AND settable bitfield keyed by
-- df.unit_labor codes; df.unit_labor's actual shape (an enum wrapper, not a
-- plain Lua table -- pairs() over it returns internal implementation fields,
-- not labor entries; the real range is `_first_item`=-1.._last_item`=93,
-- numeric-indexed back to the name string); and unit.id + df.unit.find(id)
-- as a stable per-unit handle across calls. This closes the one primitive
-- the research spec flagged as unverified for get_unit_status (raw
-- flags1/2/3 bit-guessing for hostile detection, §5) with something better,
-- not just something confirmed: dfhack.units.isDanger/isInvader are real,
-- documented, present-on-this-install functions -- no raw flag reading was
-- needed at all.
--
-- KNOWLEDGE-SCOPE FIX, 2026-09-16 (handoffs/2026-09-16-knowledge-scope-audit.md,
-- decisions/DECISIONS.md 2026-09-16 "Agents may only know what a vanilla
-- player could know"): the `hostile` filter was OMNISCIENT before this fix --
-- it scanned world.units.active with no reachability check and no
-- dfhack.units.isHidden check at all, which is exactly how it surfaced the 4
-- demons 40 z-levels down behind solid rock (decisions/DECISIONS.md
-- 2026-09-11) that motivated df-overseer-threat.lua's build in the first
-- place. Fixed by excluding any unit dfhack.units.isHidden reports true for
-- (research/2026-09-16-player-visibility.md §5: isHidden is the correct
-- composite predicate -- tile-hidden OR ambushing-and-not-fort-controlled --
-- not isVisible, whose own doc admits "doesn't account for sneaking").
-- Expected, and confirmed live (see the handoff's report): the same 5
-- isHidden units this fort's own demons/deep-cavern units already
-- represent should now disappear from `hostile`'s output entirely.
--
-- Caveat, not yet resolved: dfhack.units.isDanger() is broader than
-- "hostile invader" -- its own doc lists night creatures, semi-megabeasts,
-- agitated wildlife, and crazed units alongside invaders/marauders. The
-- live count (4) on this fort's current map is far more consistent with
-- ordinary agitated wildlife than an actual goblin incursion (the nearby
-- goblins were "a short trip east," not confirmed on-map per the embark
-- notes). `unit-status hostile`'s output includes each hit's own
-- `invader=`/`danger=` fields precisely so a caller can tell those apart
-- instead of treating every row as a confirmed siege -- cross-check against
-- isInvader specifically once a real siege happens.
--
-- FIXED 2026-09-16 (handoffs/2026-09-16-stocks-read-and-labor-race.md item
-- 3, closing the race found and recorded 2026-09-12,
-- decisions/DECISIONS.md same date, "Found and verified: set_labor already
-- races autolabor on ordinary citizens"): `set_labor` used to write
-- `unit.status.labors[code]` directly with zero coordination, an
-- unprotected single-writer violation against `autolabor`'s own reassignment
-- cycle (enabled and confirmed actually assigning jobs on this fort,
-- decisions/DECISIONS.md 2026-09-11).
--
-- THE FIX, verified live piece by piece before being written, not assumed:
--   - `plugins.autolabor.isEnabled()` is a real, present Lua API
--     (`require('plugins.autolabor')` succeeds on this install and exposes
--     `isEnabled`/`setEnabled`, confirmed live) -- used to detect whether
--     the race can even happen right now, rather than assuming autolabor is
--     always on. Confirmed live this session: `isEnabled()` returns `true`
--     on Uniboslan today.
--   - autolabor's own shipped doc (`hack/docs/docs/tools/autolabor.txt`,
--     read directly this session, not recalled) documents a real per-LABOR
--     exemption: `autolabor <LABOR> disable` takes autolabor out of
--     managing that one labor. **THE LOAD-BEARING CAVEAT, stated plainly
--     rather than glossed over: this is FORT-WIDE, not per-unit.** There is
--     no per-citizen exemption from autolabor short of active military duty
--     (already exempt by autolabor's own design, confirmed via
--     `unit.military.squad_id`) or a burrow restriction (not used here --
--     it has its own heavy side effects on movement and was not verified
--     as a clean alternative). So calling `set-labor` on a labor autolabor
--     is actively managing means: from that point on, autolabor will never
--     again auto-assign OR auto-unassign that labor for ANY citizen, not
--     just the one this call targeted. `set_labor`'s own return message
--     says this plainly every time it happens -- never a silent side
--     effect.
--   - `autolabor <LABOR> disable`'s exact command line, and `df.unit_labor`
--     code names matching autolabor's own labor names 1:1 (confirmed live:
--     `df.unit_labor.FISH == 41`, and `autolabor list` prints a `FISH:`
--     row using that same name), were both confirmed this session.
--     **NOT live-executed this session**: the `disable` call itself was
--     never actually run against Uniboslan -- it is a real change to the
--     running fort's automation config, not a read, and this stream's own
--     constraint is read-only live access with no deploy and no write to
--     the game. So the mechanism is verified by documentation and by every
--     read-only piece around it (isEnabled, CR_OK, the labor-name mapping),
--     never by watching the actual `disable` call succeed live. Treat this
--     exact code path as verified-by-mechanism, not verified-by-execution,
--     until a future session with go-ahead to touch autolabor's live config
--     re-confirms it.
--   - If autolabor's enabled-state genuinely cannot be determined (the
--     plugin fails to load, or `isEnabled()` itself errors), `set_labor`
--     now REFUSES with a clear reason instead of guessing either way --
--     per this stream's own instruction: an honest refusal beats a silent
--     race, and beats a silent over-caution just as much.

local landmarks_mod = reqscript('df-overseer-landmarks')

local args = {...}
local cmd = args[1]

-- Server-side only: resolves a raw x,y,z to near_landmark/direction/
-- distance_tiles, never handing the coordinate itself back to a caller.
-- Best-effort -- a resolution failure (e.g. no landmarks at all) falls back
-- to an honest "unknown" rather than crashing the whole status line.
local function describe_position(x, y, z)
  if not x then
    return "unknown", "?", -1
  end
  local ok, info = pcall(landmarks_mod.nearest_landmark, x, y, z)
  if ok and info then
    return info.name, info.direction, info.distance_tiles
  end
  return "unknown", "?", -1
end

local function citizen_line(unit, is_idle, is_injured, is_military)
  local x, y, z = dfhack.units.getPosition(unit)
  local near, direction, distance = describe_position(x, y, z)
  local job = unit.job.current_job
  local job_name = job and dfhack.job.getName(job) or "idle"
  local wounds = unit.body.wounds and #unit.body.wounds or 0
  return string.format(
    "CITIZEN id=%d profession=%q near_landmark=%q direction=%s distance_tiles=%d"
      .. " job=%q wounds=%d idle=%s injured=%s military=%s",
    unit.id, dfhack.units.getProfessionName(unit), near, direction, distance,
    job_name, wounds, tostring(is_idle), tostring(is_injured),
    tostring(is_military))
end

local function unit_status(filter)
  local printed = 0
  if filter ~= "hostile" then
    for _, unit in ipairs(dfhack.units.getCitizens()) do
      local is_idle = unit.job.current_job == nil
      local wounds = unit.body.wounds and #unit.body.wounds or 0
      local is_injured = wounds > 0
      local is_military = unit.military.squad_id ~= -1
      local include = (filter == nil)
        or (filter == "idle" and is_idle)
        or (filter == "injured" and is_injured)
        or (filter == "military" and is_military)
      if include then
        print(citizen_line(unit, is_idle, is_injured, is_military))
        printed = printed + 1
      end
    end
  else
    for _, unit in ipairs(df.global.world.units.active) do
      local ok_hidden, hidden = pcall(dfhack.units.isHidden, unit)
      -- ok_hidden false (isHidden itself errored) is treated as hidden --
      -- the safe default when visibility can't be determined at all, never
      -- the permissive one. See the KNOWLEDGE-SCOPE FIX note above.
      local is_hidden = (not ok_hidden) or hidden
      if dfhack.units.isDanger(unit) and not dfhack.units.isOwnCiv(unit)
          and not is_hidden then
        local x, y, z = dfhack.units.getPosition(unit)
        local near, direction, distance = describe_position(x, y, z)
        print(string.format(
          "THREAT id=%d race=%q near_landmark=%q direction=%s distance_tiles=%d"
            .. " invader=%s danger=%s",
          unit.id, dfhack.units.getRaceName(unit), near, direction, distance,
          tostring(dfhack.units.isInvader(unit)),
          tostring(dfhack.units.isDanger(unit))))
        printed = printed + 1
      end
    end
  end
  print(string.format("-- %d result(s) --", printed))
end

-- Addresses a citizen by dfhack.units id, never a getCitizens() list index --
-- that ordering is not guaranteed stable between two separate dfhack-run
-- invocations (a fresh Lua state each time), so an index handed back from
-- one call is not a safe handle to pass into a later one.
local function find_citizen(id_str)
  local id = tonumber(id_str)
  if not id then return nil, "not a numeric unit id: " .. tostring(id_str) end
  local unit = df.unit.find(id)
  if not unit then return nil, "no unit with id " .. id_str end
  if not dfhack.units.isCitizen(unit) then
    return nil, "unit " .. id_str .. " exists but is not a citizen"
  end
  return unit
end

-- df.unit_labor is an enum wrapper, not a plain Lua table -- pairs() over it
-- yields internal fields (_first_item, attrs, ...), not labor entries.
-- Confirmed live 2026-09-11: the real range is numeric, _first_item=-1
-- through _last_item=93, and df.unit_labor[code] reverse-looks-up the name.
local function each_labor_code()
  local i = -1
  return function()
    i = i + 1
    if i > df.unit_labor._last_item then return nil end
    return i, df.unit_labor[i]
  end
end

local function list_labors(unit)
  local on = {}
  for code, name in each_labor_code() do
    if code >= 0 and unit.status.labors[code] then
      on[#on + 1] = name
    end
  end
  table.sort(on)
  print(string.format("id=%d labors_on=%s", unit.id,
    #on > 0 and table.concat(on, ",") or "(none)"))
end

-- Returns enabled(bool), err(string or nil). `err` set (enabled == nil)
-- means "genuinely could not tell" -- the plugin failed to load, or its own
-- isEnabled() call errored -- never guessed as either true or false.
local function autolabor_enabled()
  local ok_req, mod = pcall(require, 'plugins.autolabor')
  if not ok_req then
    return nil, "plugins.autolabor could not be loaded: " .. tostring(mod)
  end
  local ok_call, enabled = pcall(mod.isEnabled)
  if not ok_call then
    return nil, "plugins.autolabor.isEnabled() failed: " .. tostring(enabled)
  end
  return enabled, nil
end

-- Takes ONE labor out of autolabor's management, FORT-WIDE (see this file's
-- header comment for why this is not per-unit). Returns ok(bool), err.
local function autolabor_disable_labor(labor_name)
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'autolabor', labor_name, 'disable')
  if not ok_run then
    return false, tostring(output)
  end
  if result ~= CR_OK then
    return false, string.format(
      "autolabor %s disable returned a non-OK result: %s",
      labor_name, tostring(output))
  end
  return true, nil
end

local function set_labor(unit, labor_name, state)
  local code = df.unit_labor[labor_name]
  if code == nil or code < 0 then
    return false, "unknown labor: " .. tostring(labor_name)
  end

  -- Already exempt by autolabor's own design (its own doc, confirmed live
  -- this session): no need to touch autolabor's fort-wide config for a
  -- unit it was never going to reassign anyway.
  local is_military = unit.military.squad_id ~= -1

  if not is_military then
    local enabled, status_err = autolabor_enabled()
    if enabled == nil then
      return false, string.format(
        "refusing to set %s on id=%d: could not determine whether "
          .. "autolabor is enabled (%s), and writing the labor bit "
          .. "directly without knowing is exactly the unverified race "
          .. "this check exists to prevent",
        labor_name, unit.id, status_err)
    end
    if enabled then
      local ok, disable_err = autolabor_disable_labor(labor_name)
      if not ok then
        return false, string.format(
          "refusing to set %s on id=%d: could not take it out of "
            .. "autolabor's management first (%s), and writing it "
            .. "directly while autolabor still manages it would silently "
            .. "lose to autolabor's next reassignment cycle",
          labor_name, unit.id, disable_err)
      end
      unit.status.labors[code] = state
      return true, string.format(
        "id=%d %s -> %s (autolabor no longer manages %s for ANY citizen, "
          .. "fort-wide, from now on)",
        unit.id, labor_name, tostring(state), labor_name)
    end
  end

  unit.status.labors[code] = state
  return true, string.format("id=%d %s -> %s", unit.id, labor_name,
    tostring(state))
end

if cmd == "unit-status" then
  local filter = args[2]
  if filter and filter ~= "idle" and filter ~= "injured"
      and filter ~= "military" and filter ~= "hostile" then
    print("usage: df-overseer-labor unit-status [idle|injured|military|hostile]")
  else
    unit_status(filter)
  end
elseif cmd == "labors" then
  local unit, err = find_citizen(args[2])
  if not unit then
    print("FAIL: " .. err)
  else
    list_labors(unit)
  end
elseif cmd == "set-labor" then
  local unit, err = find_citizen(args[2])
  if not unit then
    print("FAIL: " .. err)
  elseif args[4] ~= "on" and args[4] ~= "off" then
    print("usage: df-overseer-labor set-labor UNIT_ID LABOR_NAME on|off")
  else
    local ok, msg = set_labor(unit, args[3], args[4] == "on")
    print((ok and "OK: " or "FAIL: ") .. msg)
  end
else
  print("usage: df-overseer-labor <unit-status [idle|injured|military|hostile]"
    .. "|labors UNIT_ID|set-labor UNIT_ID LABOR_NAME on|off>")
end
