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
--   enabled-counts LABOR [LABOR...]
--     -- read only. JSON {"counts": {LABOR: n or null}, "errors": {LABOR: msg}}:
--        how many citizens have each labor enabled. ADDED 2026-09-21
--        (handoffs/2026-09-21-building-tool-lua.md, contract C1). A name that
--        is not a real df.unit_labor entry is `null` plus an error, NEVER 0:
--        FEED_WATER_WOUNDED never existed and used to print 0, the silent-zero
--        bug class this repo has shipped five times (register 2026-09-19).
--        Names are resolved through df.unit_labor and checked by round trip
--        (code back to name), so enum internals such as `_last_item` cannot
--        pass as labors, and NONE (-1) is rejected as not a labor.
--   quota LABOR MIN MAX [POOL] [DRY_RUN]
--     -- ADDED 2026-10-01 (handoffs/2026-10-01-labor-quota.md,
--        research/2026-10-01-quartermaster-levers.md §2). Sets autolabor's
--        per-labour minimum/maximum/talent-pool through its own CLI (the
--        only interface that exists -- no Lua accessor). Refuses when
--        autolabor's enabled state can't be determined, or when it is
--        confirmed off. DRY_RUN defaults to true; only an explicit `false`
--        performs the real call. On a real write, the report is always a
--        fresh read-back through `quota-status`, never an echo of the
--        MIN/MAX/POOL the caller passed.
--   quota-status [LABOR]
--     -- ADDED 2026-10-01, read only. Parses `autolabor list`'s own text
--        output (its only query surface) for one labour or, with no
--        argument, every labour it reports. Each entry carries autolabor's
--        own self-reported "currently N dwarfs" AND an independently-read
--        per-citizen count (the same honest enabled-counts logic
--        `enabled-counts` already uses), so target and actual can be
--        cross-checked from two angles rather than trusting one echo.
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
local textutil = reqscript('df-overseer-textutil')
local json = require('json')

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

local function citizen_row(unit, is_idle, is_injured, is_military)
  local x, y, z = dfhack.units.getPosition(unit)
  local near, direction, distance = describe_position(x, y, z)
  local job = unit.job.current_job
  local job_name = job and textutil.to_utf8(dfhack.job.getName(job)) or "idle"
  local wounds = unit.body.wounds and #unit.body.wounds or 0
  return {
    id = unit.id,
    profession = textutil.to_utf8(dfhack.units.getProfessionName(unit)),
    near_landmark = near,
    direction = direction,
    distance_tiles = distance,
    job = job_name,
    wounds = wounds,
    idle = is_idle,
    injured = is_injured,
    military = is_military,
  }
end

-- Returns ONE table for every path (citizens or threats, filtered or not,
-- empty or not); the caller prints it as a single JSON object, the shape
-- every other tool uses. The old output was one "CITIZEN id=..." text line
-- per unit plus a "-- N result(s) --" trailer, which the MCP layer could
-- not parse (found live 2026-10-08).
function unit_status(filter)
  local rows = {}
  local key = "citizens"
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
        rows[#rows + 1] = citizen_row(unit, is_idle, is_injured, is_military)
      end
    end
  else
    key = "threats"
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
        rows[#rows + 1] = {
          id = unit.id,
          race = textutil.to_utf8(dfhack.units.getRaceName(unit)),
          near_landmark = near,
          direction = direction,
          distance_tiles = distance,
          invader = dfhack.units.isInvader(unit) and true or false,
          danger = dfhack.units.isDanger(unit) and true or false,
        }
      end
    end
  end
  return {filter = filter or "all", count = #rows, [key] = rows}
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

-- enabled-counts (contract C1). Returns counts, errors. A lookup that fails
-- is null in counts plus a message in errors, never 0. NULL is json.lua's
-- null sentinel, passed to encode below.
local NULL = "\0"

local function labor_code_for(name)
  if type(name) ~= "string" or not name:match("^[A-Z][A-Z0-9_]*$") then
    return nil, "not a df.unit_labor name: " .. tostring(name)
  end
  local ok, code = pcall(function() return df.unit_labor[name] end)
  if not ok or type(code) ~= "number" then
    return nil, "unknown labor: " .. name
  end
  if code < 0 then
    return nil, "not a real labor (code " .. tostring(code) .. "): " .. name
  end
  local ok_back, back = pcall(function() return df.unit_labor[code] end)
  if not ok_back or back ~= name then
    return nil, "labor name does not round-trip through df.unit_labor: " .. name
  end
  return code
end

-- True unless the string is exactly "false"/"0"/"no" (case-insensitive).
-- DRY_RUN defaults to true (unset/nil), the same
-- farm/workshop/zone/trees/well precedent (df-overseer-farm.lua's own
-- truthy_dry_run). Only an explicit false-ish value performs a real
-- mutation.
local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

local function enabled_counts(names)
  local counts, errors = {}, {}
  local codes = {}
  for _, name in ipairs(names) do
    if counts[name] == nil then
      local code, err = labor_code_for(name)
      if code then
        codes[name] = code
        counts[name] = 0
      else
        counts[name] = NULL
        errors[name] = err
      end
    end
  end
  local ok_c, cits = pcall(dfhack.units.getCitizens)
  if not ok_c then
    for name in pairs(codes) do
      counts[name] = NULL
      errors[name] = "could not list citizens: " .. tostring(cits)
    end
    return counts, errors
  end
  for _, unit in ipairs(cits) do
    for name, code in pairs(codes) do
      local ok_l, on = pcall(function() return unit.status.labors[code] end)
      if not ok_l then
        counts[name] = NULL
        errors[name] = "could not read labor bit: " .. tostring(on)
        codes[name] = nil
      elseif on then
        counts[name] = counts[name] + 1
      end
    end
  end
  return counts, errors
end

-- labor.quota / labor.quota-status (handoffs/2026-10-01-labor-quota.md,
-- research/2026-10-01-quartermaster-levers.md §2): autolabor is the labour
-- engine on this fort (register 2026-09-30, "set intent, let the game
-- execute"); this repo's job is to set its per-labour min/max/pool targets,
-- never to hand-assign a labour to a count of dwarves itself. Per-labour
-- min/max/pool are exposed ONLY through the plugin's own CLI
-- (`autolabor LABOR MIN MAX [POOL]`), with no Lua accessor beyond
-- isEnabled/setEnabled (research §2, "no Lua accessor exists for
-- minimum_dwarfs/maximum_dwarfs"), so this shells out the same way
-- set_labor's own autolabor_disable_labor already does, and reads the
-- setting back by parsing `autolabor list`'s text output (the only query
-- surface that exists; research §2 flags a bare `autolabor LABOR` with no
-- further argument as unverified whether it is a real per-labor query, so
-- this deliberately parses the full `list` output instead of depending on
-- that unverified form).

-- Parses one line of `autolabor list`/`status` output. Verified-from-source
-- format (research §2, `autolabor.cpp:1057-1069` print_labor): either
-- "LABORNAME:  minimum N, maximum M, pool P, currently C dwarfs", or
-- "LABORNAME:  disabled", or "LABORNAME:  haulers, currently C dwarfs"
-- (that last shape confirmed live 2026-10-01). Never executed live
-- this session (offline stream, no live access) -- this parser is
-- verified-by-mechanism against the research's cited source text, not
-- verified-by-execution; a live call is the first thing that should
-- confirm it (see this file's TOOLS.yaml entry).
local function parse_autolabor_list()
  local ok_run, output, result = pcall(dfhack.run_command_silent, 'autolabor', 'list')
  if not ok_run then
    return nil, "autolabor list call failed: " .. tostring(output)
  end
  if result ~= CR_OK then
    return nil, "autolabor list returned a non-OK result: " .. tostring(output)
  end
  local entries = {}
  for line in tostring(output):gmatch("[^\r\n]+") do
    local name, rest = line:match("^(%u[%u%d_]*):%s*(.+)$")
    if name then
      -- Live 2026-10-01: the real text is "haulers, currently 18 dwarfs",
      -- not a bare "haulers"; accept both, with the count when present.
      local word = rest:match("^(disabled)") or rest:match("^(haulers)")
      if word then
        entries[name] = {mode = word, autolabor_currently = tonumber(rest:match("currently%s+(%d+)"))}
      else
        local min_s, max_s, pool_s, cur_s = rest:match(
          "minimum%s+(%d+),%s*maximum%s+(%d+),%s*pool%s+(%d+),%s*currently%s+(%d+)%s+dwarfs")
        if min_s then
          entries[name] = {
            mode = "automatic",
            minimum = tonumber(min_s),
            maximum = tonumber(max_s),
            pool = tonumber(pool_s),
            autolabor_currently = tonumber(cur_s),
          }
        else
          -- Honest fallback, never a guessed shape: a line that matched the
          -- "LABOR: ..." prefix but neither known suffix form is reported
          -- as unrecognised rather than silently dropped or mis-parsed.
          entries[name] = {mode = "unrecognised", raw = rest}
        end
      end
    end
  end
  return entries, nil
end

-- Reads autolabor's current settings for `names` (a list of df.unit_labor
-- names), or every labor autolabor reports when `names` is nil/empty.
-- Cross-checks each against a live per-citizen bitfield scan
-- (enabled_counts, the same honest-never-a-guessed-zero read this file's
-- read-only command already uses), so the result carries both autolabor's
-- own self-reported "currently" count and an independently-read one --
-- the model sees target versus actual from two angles, not one echo.
-- Always returns two tables (result, errors); a name with no usable data
-- appears only in errors, never as a silently-omitted or guessed entry.
-- Global, not local, like df-overseer-stockpile.lua's own command-level
-- functions (place_stockpile etc.) -- lets a lua-logic test load this file
-- against a fake DFHack world and call the real command function directly,
-- the same technique tests/test_stockpile_writing_lua_logic.py already uses.
function labor_quota_status(names)
  local entries, list_err = parse_autolabor_list()
  local result, errors = {}, {}
  if not entries then
    if names and #names > 0 then
      for _, n in ipairs(names) do errors[n] = list_err end
    else
      errors["_autolabor_list"] = list_err
    end
    return result, errors
  end

  local want = {}
  if names and #names > 0 then
    for _, n in ipairs(names) do want[#want + 1] = n end
  else
    for n in pairs(entries) do want[#want + 1] = n end
    table.sort(want)
  end

  local valid_names = {}
  for _, n in ipairs(want) do
    local code, code_err = labor_code_for(n)
    if not code then
      errors[n] = code_err
    elseif not entries[n] then
      errors[n] = "no autolabor entry for " .. n .. " (autolabor list did not report it)"
    else
      result[n] = entries[n]
      valid_names[#valid_names + 1] = n
    end
  end

  if #valid_names > 0 then
    local counts, count_errors = enabled_counts(valid_names)
    for _, n in ipairs(valid_names) do
      result[n].actual_enabled_count = counts[n]
      if count_errors[n] then
        errors[n] = count_errors[n]
      end
    end
  end

  return result, errors
end

-- Sets one labour's autolabor minimum/maximum/talent-pool. Refuses exactly
-- like set_labor when autolabor's enabled state can't be determined, or
-- when autolabor is confirmed not enabled at all -- this tool IS autolabor's
-- own lever, so it makes no sense to shell out to a plugin that is off.
-- DRY_RUN defaults to true: a dry run validates everything (labor name,
-- MIN/MAX/POOL shape, autolabor's enabled state) and reports exactly what
-- would be set, without calling the CLI. Only an explicit false performs
-- the real `autolabor LABOR MIN MAX [POOL]` call, and the report on success
-- is always a fresh read-back through labor_quota_status, never an echo of
-- the MIN/MAX/POOL the caller passed in (task 3 of the handoff).
function labor_quota(labor_name, min_v, max_v, pool_v, dry_run)
  local code, err = labor_code_for(labor_name)
  if not code then
    return false, err
  end

  local min_n, max_n = tonumber(min_v), tonumber(max_v)
  if min_v == nil or min_n == nil then
    return false, "MIN must be a number, got " .. tostring(min_v)
  end
  if max_v == nil or max_n == nil then
    return false, "MAX must be a number, got " .. tostring(max_v)
  end
  if min_n < 0 or max_n < 0 or min_n ~= math.floor(min_n) or max_n ~= math.floor(max_n) then
    return false, "MIN and MAX must be non-negative integers"
  end
  if min_n > max_n then
    return false, string.format("MIN (%d) must be <= MAX (%d)", min_n, max_n)
  end

  local pool_n = nil
  if pool_v ~= nil and pool_v ~= "" then
    pool_n = tonumber(pool_v)
    if pool_n == nil or pool_n < 0 or pool_n ~= math.floor(pool_n) then
      return false, "POOL must be a non-negative integer, got " .. tostring(pool_v)
    end
  end

  local enabled, status_err = autolabor_enabled()
  if enabled == nil then
    return false, string.format(
      "refusing to set a quota on %s: could not determine whether autolabor "
        .. "is enabled (%s), and shelling to its CLI without knowing is "
        .. "exactly the kind of blind write this check exists to prevent",
      labor_name, status_err)
  end
  if not enabled then
    return false, string.format(
      "refusing to set a quota on %s: autolabor is not enabled on this "
        .. "fort, so there is no engine here for a quota to configure",
      labor_name)
  end

  if truthy_dry_run(dry_run) then
    return true, {
      dry_run = true,
      labor = labor_name,
      would_set = {minimum = min_n, maximum = max_n, pool = pool_n},
    }
  end

  local cmd_args = {labor_name, tostring(min_n), tostring(max_n)}
  if pool_n ~= nil then
    cmd_args[#cmd_args + 1] = tostring(pool_n)
  end
  local ok_run, output, result = pcall(
    dfhack.run_command_silent, 'autolabor', table.unpack(cmd_args))
  if not ok_run then
    return false, string.format("autolabor %s call failed: %s",
      table.concat(cmd_args, " "), tostring(output))
  end
  if result ~= CR_OK then
    return false, string.format("autolabor %s returned a non-OK result: %s",
      table.concat(cmd_args, " "), tostring(output))
  end

  local status, status_errs = labor_quota_status({labor_name})
  if not status[labor_name] then
    return false, string.format(
      "autolabor %s %d %d accepted, but the read-back failed: %s",
      labor_name, min_n, max_n,
      tostring(status_errs[labor_name] or status_errs["_autolabor_list"] or "unknown"))
  end
  return true, {
    dry_run = false,
    labor = labor_name,
    read_back = status[labor_name],
  }
end

if cmd == "unit-status" then
  local filter = args[2]
  if filter and filter ~= "idle" and filter ~= "injured"
      and filter ~= "military" and filter ~= "hostile" then
    print(json.encode(
      {error = "usage: df-overseer-labor unit-status [idle|injured|military|hostile]"},
      {null = NULL}))
  else
    print(json.encode(unit_status(filter), {null = NULL}))
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
elseif cmd == "enabled-counts" then
  if #args < 2 then
    print(json.encode({error = "usage: df-overseer-labor enabled-counts LABOR [LABOR...]"}, {null = NULL}))
  else
    local names = {}
    for i = 2, #args do names[#names + 1] = args[i] end
    local counts, errors = enabled_counts(names)
    if next(errors) == nil then
      errors = setmetatable({}, {__tostring = function() return "JSON object" end})
    end
    print(json.encode({counts = counts, errors = errors}, {null = NULL}))
  end
elseif cmd == "quota" then
  if #args < 4 then
    print(json.encode(
      {error = "usage: df-overseer-labor quota LABOR MIN MAX [POOL] [DRY_RUN]"},
      {null = NULL}))
  else
    local ok, payload = labor_quota(args[2], args[3], args[4], args[5], args[6])
    if ok then
      print(json.encode(payload, {null = NULL}))
    else
      print(json.encode({error = payload}, {null = NULL}))
    end
  end
elseif cmd == "quota-status" then
  local names = args[2] and {args[2]} or nil
  local status, errors = labor_quota_status(names)
  if next(errors) == nil then
    errors = setmetatable({}, {__tostring = function() return "JSON object" end})
  end
  print(json.encode({status = status, errors = errors}, {null = NULL}))
else
  print("usage: df-overseer-labor <unit-status [idle|injured|military|hostile]"
    .. "|labors UNIT_ID|set-labor UNIT_ID LABOR_NAME on|off"
    .. "|enabled-counts LABOR [LABOR...]"
    .. "|quota LABOR MIN MAX [POOL] [DRY_RUN]|quota-status [LABOR]>")
end
