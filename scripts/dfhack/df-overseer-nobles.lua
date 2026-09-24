-- df-overseer-nobles.lua
--@module = true
--
-- handoffs/2026-09-21-nobles-appoint.md: a generic tool for the fortress's
-- noble and official positions (Manager, Bookkeeper, Broker, Captain of the
-- Guard, and the rest), taking the POSITION CODE as an argument. Nothing here
-- is manager-specific; the position's own data decides what is allowed.
--
-- WHY: manager work orders never become jobs on this fort because nobody holds
-- the MANAGER position (register 2026-09-19). A player fixes that on the
-- Nobles screen, so appointing is fair under the armok rule
-- (docs/ARMOK-RULINGS.md). DFHack has no named tool for it; this follows the
-- mechanism DFHack's own scripts use: hack/scripts/make-monarch.lua (set the
-- assignment's histfig, insert a histfig_entity_link_positionst into the
-- holder's entity_links) and hack/scripts/internal/emigration/unit-link-utils.lua
-- (the removal side: a former_positionst link and a remove_hf_entity_link
-- history event).
--
-- COMMANDS (all output is one JSON object; an unreadable field is null plus
-- an error, never a default):
--   list                                  every position of the fortress entity
--   verify POSITION_CODE                  read-only consistency check, both sides
--   requirements POSITION_CODE            read-only: which of this position's
--                                          own requirement fields are met
--   appoint POSITION_CODE UNIT_ID [DRY_RUN] [VERSION]
--   unappoint POSITION_CODE [DRY_RUN] [VERSION]
--
-- DRY_RUN defaults to true; only the literal word `false` writes. VERSION is
-- `minimal` (default: the monarch script's writes only) or `with_event` (also
-- writes the matching history event, as the emigration helper does). The live
-- test builds the minimal version first and reports which one the game needed.
--
-- Every refusal names its reason and is derived from the position's own data
-- (flags.ELECTED, requires_population with flags.HAS_MET_POP_REQ, the
-- assignments already held) or from the unit (alive, citizen, adult, has a
-- historical figure). All loops are bounded.
--
-- REQUIREMENTS (handoffs/2026-09-23-position-requirements-check.md). `verify`
-- answers "is this appointment internally consistent" (histfig links, vector
-- index, getNoblePositions); it never reads a single requirement field, which
-- is exactly how a Manager with no working Office read as "set up". This is
-- the other question, kept as its own verb rather than folded into `verify`,
-- because a caller may well want the appointment check without the room
-- check or vice versa, and conflating them would hide which one failed.
--
-- Reads every requirement field research/2026-09-23-room-and-zone-requirements.md
-- found on df.entity_position: the four room-value fields (required_office,
-- _bedroom, _dining, _tomb) and the four furniture-count fields
-- (required_boxes, _cabinets, _racks, _stands). No per-position branch exists
-- anywhere in this check: ROOM_VALUE_FIELDS and FURNITURE_FIELDS below are
-- plain data tables, so a position this fort has never appointed is read by
-- the exact same loop.
--
-- ROOM VALUE HAS NO NUMBER TO READ. DFHack exposes no numeric room value
-- anywhere (confirmed live in the research pass above: dfhack.buildings has
-- exactly one function with "room"/"quality"/"value" in its name,
-- getRoomDescription, and it returns only a quality-word string or empty).
-- So a room-value requirement's status is one of three, never a number
-- compared against one:
--   met         at least one zone of the needed kind, owned by the holder,
--               read back a non-empty quality word.
--   not_met     ONLY with evidence independent of the description: the
--               holder owns no zone of that kind at all, or every owned
--               zone contains none of the furniture kinds ZONE_POLICY lists
--               for that kind (df-overseer-zone.lua's zone_furniture_report,
--               the one implementation of "is furniture inside this zone").
--               An EMPTY DESCRIPTION ALONE NEVER YIELDS not_met: on this
--               fort (2026-09-24) getRoomDescription returned "" on the
--               Manager's owned office (unit passed or not, paused fort)
--               while the game's own nobles screen accepted the room, so
--               empty is not evidence of a bad room
--               (handoffs/2026-09-24-room-proxy-fix.md).
--   cannot_tell the position is vacant, its holder cannot be resolved to a
--               live unit, a read failed, or the description was empty and
--               the zone does contain qualifying furniture (the game's own
--               nobles screen is the arbiter then).
-- cannot_tell is never collapsed into not_met or met: a failed read reports
-- itself as a failed read (read_failures, dfhack.printerr), same discipline
-- df-overseer-threat.lua's class_flags uses.
--
-- FURNITURE COUNTS HAVE NO CHECK AT ALL. required_boxes/_cabinets/_racks/
-- _stands exist and are read, but nothing in DFHack's API or this game's own
-- exposed data says whether they are satisfied (research doc, "What could
-- not be verified"). Every one of these always reports cannot_tell: this
-- project does not invent a check it cannot back with a real read.

local json = require('json')
local textutil = reqscript('df-overseer-textutil')

local NULL = "\0"
local MAX_ITEMS = 500

local function entity()
  local pi = df.global.plotinfo
  local e = pi and pi.main and pi.main.fortress_entity
  if not e then return nil, "no fortress entity (is a fortress loaded?)" end
  return e
end

local function positions_by_id(e)
  local by_id = {}
  for i = 0, math.min(#e.positions.own, MAX_ITEMS) - 1 do
    local p = e.positions.own[i]
    by_id[p.id] = p
  end
  return by_id
end

local function position_name(p)
  local ok, n = pcall(function() return p.name[0] end)
  if ok and type(n) == "string" and n ~= "" then return textutil.to_utf8(n) end
  return NULL
end

local function flags_of(p)
  local out = {}
  for k, v in pairs(p.flags) do
    if v == true then out[#out + 1] = tostring(k) end
  end
  table.sort(out)
  return out
end

-- Assignments of one position code, as {idx (0-based vector index), a, p}.
local function assignments_for(e, code)
  local by_id = positions_by_id(e)
  local found = {}
  for i = 0, math.min(#e.positions.assignments, MAX_ITEMS) - 1 do
    local a = e.positions.assignments[i]
    local p = by_id[a.position_id]
    if p and p.code == code then
      found[#found + 1] = {idx = i, a = a, p = p}
    end
  end
  return found
end

local function known_codes(e)
  local codes, seen = {}, {}
  for _, p in pairs(positions_by_id(e)) do
    if not seen[p.code] then seen[p.code] = true; codes[#codes + 1] = p.code end
  end
  table.sort(codes)
  return codes
end

-- Holder of an assignment: unit id (or nil when vacant), and an error string
-- when the assignment names a historical figure that cannot be read.
local function holder_of(a)
  if a.histfig < 0 then return nil end
  local fig = df.historical_figure.find(a.histfig)
  if not fig then
    return NULL, "assignment names histfig " .. a.histfig .. " but no such historical figure exists"
  end
  return fig.unit_id
end

local function describe(e, item)
  local a, p = item.a, item.p
  local holder, herr = holder_of(a)
  local row = {
    code = p.code,
    name = position_name(p),
    position_id = p.id,
    assignment_id = a.id,
    assignment_index = item.idx,
    vacant = a.histfig < 0,
    holder_unit_id = holder == nil and NULL or holder,
    holder_histfig_id = a.histfig >= 0 and a.histfig or NULL,
    elected = p.flags.ELECTED == true,
    requires_population = p.requires_population,
    population_requirement_met = p.flags.HAS_MET_POP_REQ == true,
    position_active_flag = p.flags.ACTIVE == true,
    assignment_active = a.flags.active == true,
    number = p.number,
    is_leader = p.flags.IS_LEADER == true,
    required_office = p.required_office,
    description = p.description ~= "" and p.description or NULL,
  }
  if herr then row.error = herr end
  return row
end

local function list()
  local e, err = entity()
  if not e then return {error = err} end
  local rows = {}
  local by_id = positions_by_id(e)
  for i = 0, math.min(#e.positions.assignments, MAX_ITEMS) - 1 do
    local a = e.positions.assignments[i]
    local p = by_id[a.position_id]
    if p then
      rows[#rows + 1] = describe(e, {idx = i, a = a, p = p})
    else
      rows[#rows + 1] = {assignment_id = a.id, assignment_index = i,
        error = "assignment names position_id " .. a.position_id .. " which the entity does not define"}
    end
  end
  return {entity_id = e.id, positions = rows}
end

local function position_link(fig, e, a)
  for i = 0, math.min(#fig.entity_links, MAX_ITEMS) - 1 do
    local l = fig.entity_links[i]
    if df.histfig_entity_link_positionst:is_instance(l)
       and l.entity_id == e.id and l.assignment_id == a.id then
      return l, i
    end
  end
  return nil
end

-- Both-sides consistency for every assignment of one code. Each check is a
-- named boolean; `consistent` is true only if every held assignment passes.
local function verify(code)
  local e, err = entity()
  if not e then return {error = err} end
  local items = assignments_for(e, code)
  if #items == 0 then
    return {error = "unknown position code " .. tostring(code) .. "; known: " .. table.concat(known_codes(e), ", ")}
  end
  local out, consistent = {}, true
  for _, item in ipairs(items) do
    local a = item.a
    local row = {assignment_id = a.id, assignment_index = item.idx, vacant = a.histfig < 0}
    if a.histfig >= 0 then
      local fig = df.historical_figure.find(a.histfig)
      if not fig then
        row.error = "assignment names a historical figure that does not exist"
        consistent = false
      else
        local link = position_link(fig, e, a)
        row.assignment_histfig_is_holder = (a.histfig == fig.id)
        row.assignment_histfig2_matches = (a.histfig2 == a.histfig)
        row.figure_has_position_link = (link ~= nil)
        row.link_vector_index_matches = link ~= nil and link.assignment_vector_idx == item.idx or false
        local unit = fig.unit_id >= 0 and df.unit.find(fig.unit_id) or nil
        row.holder_unit_id = fig.unit_id >= 0 and fig.unit_id or NULL
        if not unit then
          row.get_noble_positions_lists_it = NULL
          row.error = "holder's unit cannot be found, so getNoblePositions was not checked"
          consistent = false
        else
          local seen = false
          local ok, nps = pcall(dfhack.units.getNoblePositions, unit)
          if ok then
            for _, np in ipairs(nps or {}) do
              if np.position.code == code and np.assignment.id == a.id then seen = true end
            end
          else
            row.error = "getNoblePositions raised: " .. tostring(nps)
          end
          row.get_noble_positions_lists_it = seen
        end
        for _, k in ipairs({"assignment_histfig_is_holder", "assignment_histfig2_matches",
                            "figure_has_position_link", "link_vector_index_matches",
                            "get_noble_positions_lists_it"}) do
          if row[k] ~= true then consistent = false end
        end
      end
    else
      -- a vacant assignment must not be claimed by any figure's link
      row.note = "vacant"
    end
    out[#out + 1] = row
  end
  return {position = code, entity_id = e.id, consistent = consistent, assignments = out}
end

-- ---------------------------------------------------------------------------
-- requirements: data-driven read of a position's own requirement fields.
-- See the header for what each status means and why. DATA ONLY below: the
-- field name and the zone kind it asks a value from. df-overseer-zone.lua's
-- own ZONE_POLICY carries the same position_field choices for these four
-- kinds; this table is not read through that file's quickfort-upvalue reach
-- (deliberately -- civzone_type is the game's own stable engine enum, not
-- something quickfort's own zone table defines, so resolving a kind name to
-- a type id here does not need that file's more fragile path at all).
-- ---------------------------------------------------------------------------

local ROOM_VALUE_FIELDS = {
  {field = "required_office", kind = "Office"},
  {field = "required_bedroom", kind = "Bedroom"},
  {field = "required_dining", kind = "DiningHall"},
  {field = "required_tomb", kind = "Tomb"},
}

local FURNITURE_FIELDS = {
  "required_boxes", "required_cabinets", "required_racks", "required_stands",
}

local MAX_ZONES = 5000

-- Zones of one civzone_type kind, owned by unit_id (assigned_unit_id or the
-- game's own getOwner agreeing -- same two owner mechanisms
-- df-overseer-zone.lua's apply_owner/check_owner read back). Bounded over
-- the fortress's own zone vector, same cap df-overseer-zone.lua's
-- max_zone_id uses. Returns a list (possibly empty) or nil, err.
local function owned_zones_of_kind(kind_name, unit_id)
  local type_id = df.civzone_type[kind_name]
  if type_id == nil then
    return nil, "df.civzone_type has no member named " .. tostring(kind_name)
  end
  local ok_v, zv = pcall(function() return df.global.world.buildings.other.ACTIVITY_ZONE end)
  if not ok_v or not zv then
    return nil, "could not read the fortress's own zone vector: " .. tostring(zv)
  end
  local out = {}
  for i = 0, math.min(#zv, MAX_ZONES) - 1 do
    local z = zv[i]
    if z.type == type_id then
      local ok_o, owner = pcall(dfhack.buildings.getOwner, z)
      local owner_id = (ok_o and owner) and owner.id or nil
      if z.assigned_unit_id == unit_id or owner_id == unit_id then
        local ok_d, desc = pcall(dfhack.buildings.getRoomDescription, z)
        table.insert(out, {
          id = z.id,
          zone = z,
          description_ok = ok_d,
          description = (ok_d and desc ~= "") and desc or NULL,
          description_error = (not ok_d) and tostring(desc) or nil,
        })
      end
    end
  end
  return out
end

-- df-overseer-zone.lua, for zone_furniture_report. Lazy and pcall-guarded so a
-- failure to load it is a cannot_tell with a read failure, never a crash.
local function zone_module()
  local ok, mod = pcall(reqscript, 'df-overseer-zone')
  if ok then return mod end
  return nil
end

-- One room-value requirement's status. `holder_uid` nil plus `holder_reason`
-- set means "no live unit to evaluate against" (vacant, unresolvable
-- histfig, or a histfig with no unit) -- always cannot_tell, never a guess.
local function room_value_status(kind, field, required, holder_uid, holder_reason, read_failures)
  if not required or required <= 0 then
    return {position_field = field, required = required or 0, status = "not_required"}
  end
  if holder_uid == nil then
    return {position_field = field, required = required, status = "cannot_tell", detail = holder_reason}
  end
  local zones, zerr = owned_zones_of_kind(kind, holder_uid)
  if not zones then
    table.insert(read_failures, kind .. ": " .. tostring(zerr))
    return {position_field = field, required = required, status = "cannot_tell", detail = zerr}
  end
  if #zones == 0 then
    return {position_field = field, required = required, status = "not_met",
      detail = "holder owns no " .. kind .. " zone; a positive room value needs an owned room of this kind"}
  end
  local any_nonempty, any_read_ok, any_read_failed = false, false, false
  local zone_ids = {}
  for _, z in ipairs(zones) do
    table.insert(zone_ids, z.id)
    if z.description_ok then
      any_read_ok = true
      if z.description ~= NULL then any_nonempty = true end
    else
      any_read_failed = true
      table.insert(read_failures, kind .. " zone " .. z.id .. ": getRoomDescription failed: "
        .. tostring(z.description_error))
    end
  end
  if any_read_failed then
    pcall(function()
      dfhack.printerr(string.format(
        "df-overseer-nobles: room_value_status read failure kind=%s holder=%s zones=%s",
        kind, tostring(holder_uid), table.concat(zone_ids, ",")))
    end)
  end
  if any_nonempty then
    return {position_field = field, required = required, status = "met", zone_ids = zone_ids,
      detail = "at least one owned zone reports a nonempty quality word"}
  end
  -- No owned zone has a non-empty description. An empty description is NOT
  -- evidence of a bad room (see the header), so look for independent
  -- evidence: the defining furniture inside each owned zone.
  local zmod = zone_module()
  local any_furniture, any_unknown = false, false
  local qualifying_detail = {}
  for _, z in ipairs(zones) do
    local rep, rerr
    if zmod and zmod.zone_furniture_report then
      local ok_r, r1, r2 = pcall(zmod.zone_furniture_report, z.zone)
      if ok_r then rep, rerr = r1, r2 else rerr = tostring(r1) end
    else
      rerr = "df-overseer-zone.lua's zone_furniture_report is not available"
    end
    if not rep then
      any_unknown = true
      table.insert(read_failures, kind .. " zone " .. z.id .. ": contents read failed: " .. tostring(rerr))
    else
      for _, f in ipairs(rep.read_failures or {}) do
        any_unknown = true
        table.insert(read_failures, kind .. " zone " .. z.id .. ": contents: " .. tostring(f))
      end
      if rep.furniture_kinds == nil or rep.furniture_kinds == NULL then
        -- No defining furniture is listed for this kind: no independent evidence.
        any_unknown = true
      elseif rep.matching_count > 0 then
        any_furniture = true
        table.insert(qualifying_detail, string.format("zone %s holds %d qualifying building(s), %d complete",
          tostring(z.id), rep.matching_count, rep.complete_matching_count))
      end
    end
  end
  if any_furniture then
    return {position_field = field, required = required, status = "cannot_tell", zone_ids = zone_ids,
      detail = (any_read_ok and "getRoomDescription came back empty" or "getRoomDescription could not be read")
        .. " but the owned zone does contain qualifying furniture (" .. table.concat(qualifying_detail, "; ")
        .. "). An empty description is not evidence of a bad room (it read empty on a room the game's "
        .. "own nobles screen accepted, 2026-09-24): the game's own nobles screen is the arbiter."}
  end
  if any_unknown then
    return {position_field = field, required = required, status = "cannot_tell", zone_ids = zone_ids,
      detail = "the description was not a non-empty word and the independent furniture check could not "
        .. "be completed; see read_failures"}
  end
  return {position_field = field, required = required, status = "not_met", zone_ids = zone_ids,
    detail = "every owned zone contains none of the furniture kinds ZONE_POLICY lists for " .. kind
      .. " (independent of getRoomDescription, which is not evidence either way when empty)"}
end

local function furniture_status(field, required)
  if not required or required <= 0 then
    return {required = required or 0, status = "not_required"}
  end
  return {required = required, status = "cannot_tell",
    detail = "DFHack exposes no furniture-count-per-position check; only the required count is "
      .. "read (research/2026-09-23-room-and-zone-requirements.md Q6)"}
end

-- Every requirement field of one position code, per assignment slot (a code
-- can have more than one). No per-position branch: the two field tables
-- above are the only place a specific field name appears.
function requirements(code)
  local e, err = entity()
  if not e then return {error = err} end
  local items = assignments_for(e, code)
  if #items == 0 then
    return {error = "unknown position code " .. tostring(code) .. "; known: " .. table.concat(known_codes(e), ", ")}
  end
  local read_failures = {}
  local rows = {}
  for _, item in ipairs(items) do
    local a, p = item.a, item.p
    local vacant = a.histfig < 0
    local holder, herr = holder_of(a)
    local holder_uid, holder_reason
    if vacant then
      holder_reason = "position is vacant; no holder to own a room"
    elseif holder == NULL then
      holder_reason = herr
    elseif type(holder) == "number" and holder >= 0 then
      holder_uid = holder
    else
      holder_reason = "assignment's historical figure has no live unit (unit_id " .. tostring(holder) .. ")"
    end

    local room_value = {}
    for _, rvf in ipairs(ROOM_VALUE_FIELDS) do
      room_value[rvf.kind] = room_value_status(rvf.kind, rvf.field, p[rvf.field], holder_uid, holder_reason, read_failures)
    end
    local furniture = {}
    for _, ff in ipairs(FURNITURE_FIELDS) do
      furniture[ff] = furniture_status(ff, p[ff])
    end
    rows[#rows + 1] = {
      assignment_id = a.id,
      assignment_index = item.idx,
      vacant = vacant,
      holder_unit_id = holder_uid or NULL,
      room_value = room_value,
      furniture = furniture,
    }
  end
  return {position = code, entity_id = e.id, assignments = rows, read_failures = read_failures}
end

local function is_dry(arg)
  return arg ~= "false"
end

local function refuse(reason)
  return nil, "refused: " .. reason
end

local function check_position(e, code, holding)
  local items = assignments_for(e, code)
  if #items == 0 then
    return nil, "unknown position code " .. tostring(code) .. "; known: " .. table.concat(known_codes(e), ", ")
  end
  local p = items[1].p
  if p.flags.ELECTED then
    return refuse(code .. " is an elected position; the game fills it by election, not by appointment")
  end
  if p.requires_population > 0 and not p.flags.HAS_MET_POP_REQ then
    return refuse(code .. " requires a population of " .. p.requires_population .. " and this fortress has not met it")
  end
  local target
  for _, item in ipairs(items) do
    local held = item.a.histfig >= 0
    if holding == held then target = target or item end
  end
  if not target then
    if holding then return refuse(code .. " is vacant; nobody holds it")
    else
      local h = holder_of(items[1].a)
      return refuse(code .. " is already held by unit " .. tostring(h)
        .. (#items > 1 and (" (all " .. #items .. " slots are filled)") or ""))
    end
  end
  return target
end

local function check_unit(unit_id)
  local uid = tonumber(unit_id)
  if not uid then return nil, nil, "UNIT_ID must be a number" end
  local unit = df.unit.find(uid)
  if not unit then return nil, nil, "refused: no unit with id " .. uid end
  if not dfhack.units.isAlive(unit) then return nil, nil, "refused: unit " .. uid .. " is not alive" end
  if not dfhack.units.isCitizen(unit) then return nil, nil, "refused: unit " .. uid .. " is not a citizen of this fortress" end
  if not dfhack.units.isAdult(unit) then return nil, nil, "refused: unit " .. uid .. " is not an adult" end
  if unit.hist_figure_id < 0 then return nil, nil, "refused: unit " .. uid .. " has no historical figure" end
  local fig = df.historical_figure.find(unit.hist_figure_id)
  if not fig then return nil, nil, "refused: unit " .. uid .. " names histfig " .. unit.hist_figure_id .. " which does not exist" end
  return unit, fig
end

local function next_event_id()
  local id = df.global.hist_event_next_id
  df.global.hist_event_next_id = id + 1
  return id
end

local function appoint(code, unit_id, dry_arg, version)
  local e, err = entity()
  if not e then return nil, err end
  version = version or "minimal"
  if version ~= "minimal" and version ~= "with_event" then
    return nil, "VERSION must be minimal or with_event"
  end
  local target, terr = check_position(e, code, false)
  if not target then return nil, terr end
  local unit, fig, uerr = check_unit(unit_id)
  if not unit then return nil, uerr end

  local a, p = target.a, target.p
  local plan = {
    position = code, position_id = p.id, assignment_id = a.id, assignment_index = target.idx,
    unit_id = unit.id, unit_name = textutil.to_utf8(dfhack.units.getReadableName(unit)), histfig_id = fig.id,
    version = version,
    would_write = {
      "assignment.histfig = " .. fig.id, "assignment.histfig2 = " .. fig.id,
      "insert histfig_entity_link_positionst (entity " .. e.id .. ", assignment " .. a.id
        .. ", vector index " .. target.idx .. ", start_year " .. df.global.cur_year .. ")",
    },
  }
  if version == "with_event" then
    plan.would_write[#plan.would_write + 1] = "insert history_event_add_hf_entity_linkst (POSITION)"
  end
  if is_dry(dry_arg) then
    plan.dry_run = true
    return plan
  end

  plan.dry_run = false
  local ok, werr = pcall(function()
    fig.entity_links:insert("#", {new = df.histfig_entity_link_positionst,
      entity_id = e.id, link_strength = 100, assignment_id = a.id,
      assignment_vector_idx = target.idx, start_year = df.global.cur_year})
  end)
  if not ok then return nil, "write failed before changing the assignment: " .. tostring(werr) end
  a.histfig = fig.id
  a.histfig2 = fig.id
  if version == "with_event" then
    local eok, eerr = pcall(function()
      df.global.world.history.events:insert("#", {new = df.history_event_add_hf_entity_linkst,
        year = df.global.cur_year, seconds = df.global.cur_year_tick, id = next_event_id(),
        civ = e.id, histfig = fig.id, link_type = df.histfig_entity_link_type.POSITION,
        position_id = p.id})
    end)
    plan.event_written = eok
    if not eok then plan.event_error = tostring(eerr) end
  end
  plan.verification = verify(code)
  return plan
end

local function unappoint(code, dry_arg, version)
  local e, err = entity()
  if not e then return nil, err end
  version = version or "minimal"
  if version ~= "minimal" and version ~= "with_event" then
    return nil, "VERSION must be minimal or with_event"
  end
  local target, terr = check_position(e, code, true)
  if not target then return nil, terr end
  local a, p = target.a, target.p
  local fig = df.historical_figure.find(a.histfig)
  if not fig then return nil, "assignment names histfig " .. a.histfig .. " which does not exist; refusing to guess" end
  local link, li = position_link(fig, e, a)
  local plan = {
    position = code, assignment_id = a.id, assignment_index = target.idx,
    holder_histfig_id = fig.id, holder_unit_id = fig.unit_id >= 0 and fig.unit_id or NULL,
    version = version,
    would_write = {
      "assignment.histfig = -1", "assignment.histfig2 = -1",
      link and "replace the figure's positionst link with a former_positionst link"
        or "no positionst link found on the figure (nothing to replace)",
    },
  }
  if version == "with_event" then
    plan.would_write[#plan.would_write + 1] = "insert history_event_remove_hf_entity_linkst"
  end
  if is_dry(dry_arg) then
    plan.dry_run = true
    return plan
  end

  plan.dry_run = false
  local start_year = link and link.start_year or df.global.cur_year
  if link then
    fig.entity_links:erase(li)
    link:delete()
  end
  fig.entity_links:insert("#", {new = df.histfig_entity_link_former_positionst,
    assignment_id = a.id, start_year = start_year, entity_id = e.id,
    end_year = df.global.cur_year, link_strength = 100})
  a.histfig = -1
  a.histfig2 = -1
  if version == "with_event" then
    local eok, eerr = pcall(function()
      df.global.world.history.events:insert("#", {new = df.history_event_remove_hf_entity_linkst,
        year = df.global.cur_year, seconds = df.global.cur_year_tick, id = next_event_id(),
        civ = e.id, histfig = fig.id, link_type = df.histfig_entity_link_type.POSITION,
        position_id = p.id})
    end)
    plan.event_written = eok
    if not eok then plan.event_error = tostring(eerr) end
  end
  plan.verification = verify(code)
  return plan
end

if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

local function emit(result, err)
  print(json.encode(err and {error = err} or result, {null = NULL}))
end

if cmd == "list" then
  emit(list())
elseif cmd == "verify" then
  if not args[2] then
    print("usage: df-overseer-nobles verify POSITION_CODE")
  else
    emit(verify(args[2]))
  end
elseif cmd == "requirements" then
  if not args[2] then
    print("usage: df-overseer-nobles requirements POSITION_CODE")
  else
    emit(requirements(args[2]))
  end
elseif cmd == "appoint" then
  if not (args[2] and args[3]) then
    print("usage: df-overseer-nobles appoint POSITION_CODE UNIT_ID [DRY_RUN] [VERSION]")
  else
    emit(appoint(args[2], args[3], args[4], args[5]))
  end
elseif cmd == "unappoint" then
  if not args[2] then
    print("usage: df-overseer-nobles unappoint POSITION_CODE [DRY_RUN] [VERSION]")
  else
    emit(unappoint(args[2], args[3], args[4]))
  end
else
  print("usage: df-overseer-nobles list")
  print("usage: df-overseer-nobles verify POSITION_CODE")
  print("usage: df-overseer-nobles requirements POSITION_CODE")
  print("usage: df-overseer-nobles appoint POSITION_CODE UNIT_ID [DRY_RUN] [VERSION]")
  print("usage: df-overseer-nobles unappoint POSITION_CODE [DRY_RUN] [VERSION]")
end
