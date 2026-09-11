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
-- ranked/labelled status list, not raw memory). `near_landmark` is
-- deliberately omitted from unit-status's output: the landmark system this
-- repo's spec calls for lives only on the perception-layer-experiments
-- branch (a different session's work, not merged to main) -- raw x,y,z is
-- printed instead, a placeholder until that lands.
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

local args = {...}
local cmd = args[1]

local function citizen_line(unit, is_idle, is_injured, is_military)
  local x, y, z = dfhack.units.getPosition(unit)
  local job = unit.job.current_job
  local job_name = job and dfhack.job.getName(job) or "idle"
  local wounds = unit.body.wounds and #unit.body.wounds or 0
  return string.format(
    "CITIZEN id=%d profession=%q pos=%d,%d,%d job=%q wounds=%d"
      .. " idle=%s injured=%s military=%s",
    unit.id, dfhack.units.getProfessionName(unit), x or -1, y or -1, z or -1,
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
      if dfhack.units.isDanger(unit) and not dfhack.units.isOwnCiv(unit) then
        local x, y, z = dfhack.units.getPosition(unit)
        print(string.format(
          "THREAT id=%d race=%q pos=%d,%d,%d invader=%s danger=%s",
          unit.id, dfhack.units.getRaceName(unit), x or -1, y or -1, z or -1,
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

local function set_labor(unit, labor_name, state)
  local code = df.unit_labor[labor_name]
  if code == nil or code < 0 then
    return false, "unknown labor: " .. tostring(labor_name)
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
