-- df-overseer-workjob.lua
--@module = true
--
-- handoffs/2026-09-19-workshop-add-job.md: manager work orders stall on this
-- fort. handoffs/2026-09-19-well-and-harvest.md section 5 and
-- handoffs/2026-09-19-well-finish.md section 2-4 each independently ran the
-- fort for tens of thousands of ticks with a matching workshop built, the
-- right material sitting available, and (in well-finish's case) `validated`
-- hand-set true, and NEVER saw `ConstructBlocks`/`ConstructMechanisms`/
-- `CustomReaction BREW_DRINK_FROM_PLANT` become a real job -- this install
-- has no citizen holding the Manager noble position
-- (df-overseer-orders.lua's own header), and whatever else the engine gates
-- job-dispatch-from-queue on is not exposed by the `manager_order` struct's
-- readable fields.
--
-- **The honest alternative, per the user's own correction**: a player can
-- queue a one-off job directly at a workshop by clicking it (the "q" menu's
-- own "add new job" action) with no Manager involved at all -- Manager
-- orders are a QUEUE that needs a Manager to approve; a direct job at a
-- workshop is not in that queue and never was. This file is that action.
--
-- =============================================================================
-- GENERALISED handoffs/2026-09-21-workjob-generalise.md, dispatched
-- 2026-09-23. WHAT CHANGED AND WHY, read this before the rest of the file:
--
-- The tool used to know three jobs by a hand-maintained JOB_INFO table
-- (blocks/mechanisms/brew_drink) while df-overseer-orders.lua's own
-- JOB_INFO knew twelve -- the concrete shape of CLAUDE.md's "tools must be
-- generalisable" rule being broken, named explicitly in Working.md START
-- HERE. **DFHack already builds a workshop's job list generically**:
-- `hack/lua/dfhack/workshops.lua`'s own `getJobs(buildingId, workshopId,
-- customId)` -- the exact module behind the game's "q -> add job" menu --
-- returns, for ANY workshop or furnace kind, its hard-coded job definitions
-- (jobs_workshop/jobs_furnace, each entry `{name, items, job_fields}`) PLUS
-- every reaction the raws attach to that specific building
-- (`addReactionJobs`, reading `df.global.world.raws.reactions.reactions`
-- live), with each reaction's own reagents already converted to a job_item
-- filter spec by `reagentToJobItem` (`utils.clone_with_default(reagent,
-- input_filter_defaults)`). This file's whole three-job table is now GONE,
-- replaced by reading this same module every call -- the job vocabulary is
-- the game's, not a second hand-maintained list, per the handoff's own
-- test: "if you end up with a table of twelve, the stream has failed its
-- own point."
--
-- SOURCE CITED, READ LIVE ON THIS INSTALL, NOT ASSUMED: the exact text of
-- `/opt/df/game/hack/lua/dfhack/workshops.lua` (578 lines) was read over
-- SSH this stream, not from memory or the public GitHub mirror -- see the
-- coverage numbers and item-spec shape below, both measured against this
-- install's own DFHack build and raws, read-only, fort paused throughout.
--
-- **Coverage, measured, not estimated** (`getJobs` called for every one of
-- df.workshop_type's 25 kinds and df.furnace_type's 8 kinds, building_id
-- fixed, workshopId walked 0..24 / 0..7 via the enum's own `_first_item`/
-- `_last_item` bounds -- `pairs()` over a DFHack enum-type object does NOT
-- yield its name<->int entries, verified live this session; only the
-- int->name reverse lookup via `enum[i]` does):
--   - workshop_type: 25 kinds total. 11 have a hard-coded jobs_workshop
--     entry (Jewelers, Fishery, Masons, Carpenters, Kitchen, Butchers,
--     Mechanics, Loom, Leatherworks, Dyers, Siege). Of the other 14,
--     10 STILL get real jobs purely from raws reactions via
--     `addReactionJobs` (Ashery 1, Craftsdwarfs 104, Custom 6 [-1
--     wildcard scan; a named custom workshop sees only its own], Farmers 2,
--     MagmaForge 15, MetalsmithsForge 15, Millstone 2, Quern 2, Still 3,
--     Tanners 2). Only 4 kinds returned ZERO jobs from `getJobs` on this
--     install's raws: Bowyers, Clothiers, Kennels, Tool -- likely
--     legacy/non-manufacturing kinds (Kennels trains/assigns animals, not
--     a "q -> add job" workshop at all), NOT independently confirmed why
--     from source this stream, flagged honestly rather than guessed.
--   - furnace_type: 8 kinds total. 5 hard-coded (Smelter, MagmaSmelter,
--     GlassFurnace, WoodFurnace, Kiln). Of the other 3, 2 get real jobs
--     from raws reactions (MagmaGlassFurnace 13, MagmaKiln 20). Only
--     Custom furnace returned zero at customId=-1 (wildcard; a named
--     custom furnace may still see its own reactions).
--   - **Net: 28 of 33 workshop+furnace kinds have at least one real,
--     queueable job through `getJobs` on this install's own raws; 5 do
--     not** (Bowyers, Clothiers, Kennels, Tool workshop; Custom furnace at
--     the wildcard scan). This is the honest generalisation ceiling: this
--     tool now covers everything `getJobs` covers, and states by name what
--     it does not, rather than silently returning nothing for those 5.
--   - Known noise, not a bug in this file: `getJobs` for Smelter/
--     MagmaSmelter runs DFHack's own `addSmeltJobs`, which calls bare
--     `print`/`printall` for every smeltable ore in the raws -- that is
--     upstream DFHack's own debug output, unsuppressable from here without
--     monkeypatching a shipped module, and will show up in the dfhack log
--     (not this tool's stdout JSON) whenever `list-jobs`/`queue` targets a
--     real Smelter or Magma Smelter. Harmless, just noted so it is not
--     mistaken for a leak or a crash.
--
-- **Item-spec shape, read live, not guessed**: `df.job_item:new()`'s own
-- real field set (introspected via `pairs()` on a fresh instance) is
-- item_type, item_subtype, mat_type, mat_index, quantity, flags1/2/3
-- (bitfields), flags4/5 (plain numbers), reaction_class,
-- has_material_reaction_product, metal_ore, min_dimension, has_tool_use,
-- vector_id, reaction_id, reagent_index, contains, dye_color,
-- job_details_*. `getJobs`'s own item-filter tables (both the hard-coded
-- jobs_workshop/jobs_furnace entries, merged against `input_filter_defaults`
-- and the kind's own `defaults`, AND the reaction-derived entries from
-- `reagentToJobItem`) use EXACTLY these field names. This means the
-- generic conversion below (`job_item_from_spec`) is a straight field
-- copy, not a guess -- the same "kind reads from the game's own data"
-- pattern df-overseer-building.lua/df-overseer-zone.lua already use.
-- **Cross-check against the tool's own prior hand-written spec**: Masons'
-- "construct blocks" job, read live through `getJobs` this session, came
-- back item_type=BOULDER(4), item_subtype=-1, mat_type=0, mat_index=-1,
-- quantity=1, flags3={hard=true}, vector_id=BOULDER(19) -- field-for-field
-- IDENTICAL to the old hand-written `fixed_boulder_job_item` below's
-- replacement. This is strong evidence the generic path reproduces the
-- old, live-verified (2026-09-19, real blocks/mechanisms jobs queued and
-- the well built from them) behaviour exactly, not merely "similar".
-- **One thing the generic path does DIFFERENTLY, and probably better**:
-- `getJobs`'s reaction-derived item specs carry `reaction_id`/
-- `reagent_index` (which reagent slot of which reaction this job_item
-- satisfies); the OLD hand-written `reagent_job_item` never set either
-- field on the job_item it built. Whether the engine actually needs that
-- linkage to bind a produced item back to the right reagent slot is NOT
-- confirmed live (never exercised: this stream still queues no real job),
-- but copying it through now, since the real "add job" menu code path
-- clearly sets it, is more faithful than the old omission -- flagged
-- honestly as a discovered gap in the tool's own prior version, not a
-- claim that the old jobs (blocks/mechanisms, both fixed_boulder, neither
-- ever carried a real reaction_id/reagent_index anyway) were wrong.
--
-- **Job token scheme, generalised.** A job is now addressed by:
--   - `job_type` name lowercased (e.g. "constructblocks") for any
--     non-reaction job, OR
--   - `"reaction:" .. reaction_code:lower()` for a `CustomReaction` job
--     (job_type alone is ambiguous across many different reactions at one
--     workshop -- Still alone offers three: BREW_DRINK_FROM_PLANT,
--     BREW_DRINK_FROM_PLANT_GROWTH, MAKE_MEAD, read live this session,
--     TWO OF WHICH the old three-token tool could never reach at all).
-- **The three old short tokens (blocks/mechanisms/brew_drink) still work,
-- unchanged, via `LEGACY_ALIASES` below** -- resolved against whatever
-- workshop the caller actually names, by matching the alias's own
-- job_type/reaction against that workshop's REAL `getJobs` output, not by
-- a separate hardcoded spec. This also means the old wrong-workshop-kind
-- refusal is now implicit and more informative: asking for `blocks` at a
-- workshop that does not offer a `ConstructBlocks` job returns "not
-- offered at workshop X; available: ..." listing what that workshop
-- actually has, rather than a fixed "wrong kind" message.
--
-- **Requirements/availability, deliverable 3**: `list-jobs` and `queue`'s
-- dry-run both report each needed item's six-deduction availability by
-- REUSING `df-overseer-stocks.lua`'s own `get_availability` (reqscript'd,
-- not re-derived -- CLAUDE.md's generalisability rule again: this project
-- already owns one honest, live-verified item-counting engine, this file
-- does not get a second one). A job whose item is concrete gets a real
-- availability read; a job whose item stays a wildcard after all defaults
-- merge (item_type still -1) is refused outright, exactly as before --
-- refusing rather than guessing which of many possible items to queue
-- against.
--
-- **Unknown is never zero.** Every guarded (`pcall`) read that could fail
-- collects into a `read_failures` array on the result (both `list-jobs`
-- and `queue`) and is also relayed via `dfhack.printerr` when non-empty --
-- the exact pattern `docs/TRAPS.md`'s "A pcall-guarded read that degrades
-- to `false` on failure can hide a bug through a full deploy" entry
-- requires, since this file reads reagents, job definitions and item
-- fields off live raws, precisely the surface that bug lived on. No
-- guarded read here silently becomes a default value without a matching
-- entry in `read_failures`.
--
-- COUNT, added this stream: `queue` now takes an optional trailing COUNT
-- (default 1), queuing that many IDENTICAL jobs, refusing (never
-- truncating) if the workshop's current queue plus COUNT would exceed
-- `MAX_WORKSHOP_JOBS`. Each real queue call still returns `job_id` (the
-- first, for back-compat) and the new `job_ids` (all of them).
--
-- Still live, read-only this stream: NO real job is queued against VM 103
-- by this build (`DRY_RUN=false` is UNTESTED live, exactly as the old
-- version already stated about itself for blocks/mechanisms, now true of
-- the whole generalised surface too). See the handoff's own report section
-- for the exact supervised test this owes.
-- =============================================================================
--
-- NEVER sets `status.validated` and never touches
-- `df.global.world.manager_orders.all` -- this file has no relationship to
-- df-overseer-orders.lua's queue at all, by design; it is the OTHER
-- legitimate route, not a patch on the first one.
--
-- Workshop/furnace resolution: `bld.flags.exists` (df-overseer-farm.lua's
-- own construction-gate pattern) and an exact `dfhack.buildings.getName`
-- match against the landmark name (df-overseer-landmarks.lua's own
-- lookup), same as before -- generalised only to accept EITHER a Workshop
-- or a Furnace building, not just Workshop, since `getJobs` covers both.
--
-- DRY_RUN defaults to true, same contract as every other write tool in this
-- project. No coordinates in any input or output -- `resolve_building`
-- reads a building object server-side and never returns or prints its
-- x/y/z; the caller only ever sees the landmark NAME back.
--
-- CANCEL is unchanged by this stream (added
-- handoffs/2026-09-23-order-job-attribution-and-checks.md item 5): a job id
-- (not a workshop landmark), reusing df-overseer-stuckjobs.lua's
-- `job_origin`, sole_writer overseer only.
--
-- Usage: ./dfhack-run df-overseer-workjob list
-- Usage: ./dfhack-run df-overseer-workjob list-jobs WORKSHOP_LANDMARK_NAME
-- Usage: ./dfhack-run df-overseer-workjob queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN] [REPEAT] [COUNT]
-- Usage: ./dfhack-run df-overseer-workjob cancel JOB_ID [DRY_RUN]

local json = require('json')
local utils = require('utils')
local textutil = reqscript('df-overseer-textutil')
local stuckjobs_mod = reqscript('df-overseer-stuckjobs')
local stocks_mod = reqscript('df-overseer-stocks')
-- The real DFHack module behind the game's own "q -> add job" menu -- see
-- header. A native dfhack module (mkmodule('dfhack.workshops')), not a
-- df-overseer-*.lua script, so `require`, not `reqscript`.
local workshops_mod = require('dfhack.workshops')

-- Per DFHack's own documented cap on dfhack.job.assignToWorkshop (see
-- header): it silently does nothing and returns false past this many jobs
-- queued at one workshop. Checked here first so the refusal names the real
-- reason instead of a bare "assign failed".
local MAX_WORKSHOP_JOBS = 10

-- The only three tokens this tool used to know, kept resolvable exactly as
-- before -- see header. Each alias is matched against the NAMED workshop's
-- own real `getJobs` output (job_type name + optional reaction code), not a
-- separate hand-built spec, so a workshop that does not actually offer the
-- aliased job still refuses honestly rather than silently accepting it.
local LEGACY_ALIASES = {
  blocks = {job_type = "ConstructBlocks"},
  mechanisms = {job_type = "ConstructMechanisms"},
  brew_drink = {job_type = "CustomReaction", reaction = "BREW_DRINK_FROM_PLANT"},
}

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- REPEAT, added handoffs/2026-09-23-order-job-attribution-and-checks.md item
-- 6: "let workjob.queue set it, off by default, explicit when asked."
-- Confirmed from DFHack's own current shipped source, not guessed: both
-- `gui/workflow.lua` and (independently) a search of DFHack's df-structures
-- job_flags bitfield agree the field is `job.flags['repeat']` (bracket
-- notation required -- `repeat` is a Lua reserved word). NOT independently
-- confirmed by introspecting this install's own live `df.job._fields`
-- (this build stream still exercises no write verb against the fort).
local function truthy_repeat(v)
  if v == nil then
    return false
  end
  local s = tostring(v):lower()
  return s == "true" or s == "1" or s == "yes"
end

-- ============================================================================
-- Generic building resolution: ANY Workshop or Furnace, addressed by exact
-- landmark name -- see header. Returns the building object; callers must
-- never print or return it directly (no coordinates in output).
local function resolve_building_generic(name)
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_name, bname = pcall(dfhack.buildings.getName, bld)
    bname = ok_name and textutil.to_utf8(bname) or bname
    if ok_name and bname == name then
      local ok_btype, btype = pcall(function() return bld:getType() end)
      if not ok_btype then
        return nil, "landmark '" .. name .. "': could not read building type"
      end
      if btype ~= df.building_type.Workshop and btype ~= df.building_type.Furnace then
        return nil, "landmark '" .. name .. "' is not a workshop or furnace"
      end
      local ok_exists, exists = pcall(function() return bld.flags.exists end)
      if not ok_exists or not exists then
        return nil, "workshop '" .. name .. "' is still under construction"
          .. " (flags.exists is false)"
      end
      return bld
    end
  end
  return nil, "unknown workshop: " .. tostring(name)
end

-- Reads (building_id, kind_id, custom_id, kind_name) off a resolved
-- building, generically over Workshop/Furnace and over Custom vs. built-in
-- subtype -- the exact three arguments `workshops.getJobs` itself takes.
-- Custom-workshop resolution (`bld.custom_type`, an index into
-- `df.global.world.raws.buildings.workshops`) mirrors
-- df-overseer-orders.lua's own `workshop_exists_count` pattern, read fresh,
-- never hardcoded.
local function workshop_kind_ids(bld)
  local ok_btype, btype = pcall(function() return bld:getType() end)
  if not ok_btype then
    return nil, nil, nil, nil, "could not read building type"
  end
  local ok_sub, sub = pcall(function() return bld.type end)
  if not ok_sub then
    return nil, nil, nil, nil, "could not read workshop/furnace subtype"
  end
  local kind_name
  if btype == df.building_type.Workshop then
    kind_name = df.workshop_type[sub]
  else
    kind_name = df.furnace_type[sub]
  end
  local custom = -1
  local is_custom = (btype == df.building_type.Workshop and sub == df.workshop_type.Custom)
  if is_custom then
    local ok_c, c = pcall(function() return bld.custom_type end)
    custom = (ok_c and c) or -1
  end
  return btype, sub, custom, kind_name
end

-- Fetches this workshop's real job list from DFHack's own module -- see
-- header for the coverage numbers this was measured against.
local function get_real_jobs(bld)
  local btype, sub, custom, kind_name, err = workshop_kind_ids(bld)
  if err then
    return nil, nil, err
  end
  local ok_jobs, jobs = pcall(workshops_mod.getJobs, btype, sub, custom)
  if not ok_jobs or jobs == nil then
    return nil, kind_name, "workshops.getJobs failed for this workshop"
      .. " (building_type=" .. tostring(btype) .. ", subtype=" .. tostring(sub) .. ")"
  end
  return jobs, kind_name, nil
end

-- Token + display info for one getJobs() entry. Returns
-- (token, job_type_name, reaction_name), any of which may be nil if the
-- underlying job_type integer could not be resolved to a name (an
-- unreadable field, reported by the caller via read_failures, never
-- silently dropped).
local function job_token(contents)
  local job_type_int = contents.job_fields and contents.job_fields.job_type
  local job_type_name = job_type_int and df.job_type[job_type_int]
  local reaction_name = contents.job_fields and contents.job_fields.reaction_name
  local token
  if job_type_name == "CustomReaction" and reaction_name then
    token = "reaction:" .. reaction_name:lower()
  elseif job_type_name then
    token = job_type_name:lower()
  end
  return token, job_type_name, reaction_name
end

-- ============================================================================
-- Generic job_item construction: a straight field copy off a getJobs() item
-- filter spec into a real df.job_item -- see header's field-name mapping,
-- read live, not guessed. Returns (jitem, read_failures): read_failures
-- names any spec field that could not be read as its expected type, so a
-- caller sees exactly what degraded rather than a silent default.
local NUMERIC_FIELDS = {
  {"item_type", -1}, {"item_subtype", -1}, {"mat_type", -1}, {"mat_index", -1},
  {"quantity", 1}, {"min_dimension", -1}, {"metal_ore", -1}, {"has_tool_use", -1},
  {"flags4", 0}, {"flags5", 0},
}
-- Present only on reaction-derived specs; copied through when present
-- (see header: the old tool never set these, this is a discovered gap).
local OPTIONAL_NUMERIC_FIELDS = {"vector_id", "reaction_id", "reagent_index"}
local STRING_FIELDS = {"reaction_class", "has_material_reaction_product"}
local FLAG_TABLE_FIELDS = {"flags1", "flags2", "flags3"}

local function job_item_from_spec(spec)
  local jitem = df.job_item:new()
  local read_failures = {}

  for _, entry in ipairs(NUMERIC_FIELDS) do
    local field, default = entry[1], entry[2]
    local ok, v = pcall(function() return spec[field] end)
    if ok and type(v) == "number" then
      jitem[field] = v
    else
      jitem[field] = default
      table.insert(read_failures, field)
    end
  end

  for _, field in ipairs(OPTIONAL_NUMERIC_FIELDS) do
    local ok, v = pcall(function() return spec[field] end)
    if ok and type(v) == "number" then
      jitem[field] = v
    elseif ok and v ~= nil then
      table.insert(read_failures, field)
    end
    -- v == nil (field genuinely absent, e.g. a hard-coded job's item has no
    -- reaction_id) is NOT a read failure -- it is an honest "not
    -- applicable", left at df.job_item:new()'s own default.
  end

  for _, field in ipairs(STRING_FIELDS) do
    local ok, v = pcall(function() return spec[field] end)
    if ok and type(v) == "string" and v ~= "" then
      jitem[field] = v
    elseif ok and v ~= "" and v ~= nil then
      table.insert(read_failures, field)
    end
  end

  for _, field in ipairs(FLAG_TABLE_FIELDS) do
    local ok, tbl = pcall(function() return spec[field] end)
    if ok and type(tbl) == "table" then
      for k, v in pairs(tbl) do
        if v then
          local fok = pcall(function() jitem[field][k] = true end)
          if not fok then
            table.insert(read_failures, field .. "." .. tostring(k))
          end
        end
      end
    elseif not ok then
      table.insert(read_failures, field)
    end
  end

  return jitem, read_failures
end

-- Builds every job_item this job entry needs (never partially -- either all
-- resolve to a concrete item or nothing is returned), refusing rather than
-- guessing on the first wildcard/tag-matched item (item_type still -1
-- after all defaults merged). This is the exact refusal contract the old
-- reagent_job_item already had for brew_drink's own container reagent,
-- generalised over every job this tool now reaches.
local function build_job_items_from_spec(job_entry)
  local items = job_entry.items or {}
  local job_items, diagnostics, read_failures = {}, {}, {}
  for idx, spec in ipairs(items) do
    local ok_it, item_type = pcall(function() return spec.item_type end)
    if not ok_it then
      return nil, string.format("item %d: item_type could not be read", idx)
    end
    if item_type == nil or item_type < 0 then
      return nil, string.format(
        "item %d has no concrete item_type (a wildcard/tag-matched reagent"
          .. " -- e.g. a generic container match -- is not supported by this"
          .. " tool; refusing rather than guessing a filter for it)", idx)
    end
    local jitem, item_read_failures = job_item_from_spec(spec)
    for _, f in ipairs(item_read_failures) do
      table.insert(read_failures, "item " .. idx .. ": " .. f)
    end
    local ok_name, type_name = pcall(function() return df.item_type[item_type] end)
    table.insert(job_items, jitem)
    table.insert(diagnostics, {
      resolved = true,
      index = idx,
      item_type = ok_name and type_name or nil,
      quantity = jitem.quantity,
    })
  end
  if #job_items == 0 then
    return nil, "this job has no items defined (unexpected)"
  end
  return job_items, diagnostics, read_failures
end

-- ============================================================================
-- Per-item summary for list-jobs: class/quantity/material constraint, plus
-- a six-deduction availability read for any concrete item, REUSING
-- df-overseer-stocks.lua's own get_availability (see header -- not
-- re-derived).
local function summarise_item_spec(spec)
  local read_failures = {}
  local function get(field)
    local ok, v = pcall(function() return spec[field] end)
    if not ok then
      table.insert(read_failures, field)
      return nil
    end
    return v
  end
  local function true_flags(field)
    local tbl = get(field)
    local out = {}
    if type(tbl) == "table" then
      for k, v in pairs(tbl) do
        if v and k ~= "allow_artifact" then
          table.insert(out, field .. "." .. tostring(k))
        end
      end
      table.sort(out)
    end
    return out
  end

  local item_type = get("item_type")
  local item_type_name = nil
  if item_type and item_type >= 0 then
    local ok, name = pcall(function() return df.item_type[item_type] end)
    if ok then
      item_type_name = name
    else
      table.insert(read_failures, "item_type name lookup")
    end
  end

  local mat_type = get("mat_type")
  local mat_index = get("mat_index")
  local quantity = get("quantity") or 1
  local reaction_class = get("reaction_class")
  local has_mat_reaction_product = get("has_material_reaction_product")
  local min_dimension = get("min_dimension")

  local class_flags = {}
  for _, f in ipairs(true_flags("flags1")) do table.insert(class_flags, f) end
  for _, f in ipairs(true_flags("flags2")) do table.insert(class_flags, f) end
  for _, f in ipairs(true_flags("flags3")) do table.insert(class_flags, f) end

  local summary = {
    item_type = item_type_name,
    concrete = (item_type ~= nil and item_type >= 0),
    quantity = quantity,
    mat_type = (mat_type and mat_type >= 0) and mat_type or nil,
    mat_index = (mat_index and mat_index >= 0) and mat_index or nil,
    class_flags = class_flags,
    reaction_class = (reaction_class ~= nil and reaction_class ~= "") and reaction_class or nil,
    has_material_reaction_product = (has_mat_reaction_product ~= nil
      and has_mat_reaction_product ~= "") and has_mat_reaction_product or nil,
    min_dimension = (min_dimension and min_dimension >= 0) and min_dimension or nil,
  }

  if summary.concrete and item_type_name then
    local ok_avail, avail = pcall(stocks_mod.get_availability, item_type_name)
    if ok_avail and avail then
      summary.availability = avail
    else
      table.insert(read_failures, "availability lookup for " .. tostring(item_type_name))
    end
  end

  return summary, read_failures
end

-- ============================================================================
-- list (unchanged): the three legacy tokens only, exactly as before this
-- stream -- deliberately NOT replaced by list-jobs below, so an existing
-- caller (dfmcp's own `workjob.list`, no args) keeps working byte-for-byte.
function list_jobs()
  local known = {}
  for k in pairs(LEGACY_ALIASES) do table.insert(known, k) end
  table.sort(known)
  return {jobs = known}
end

-- list-jobs WORKSHOP_LANDMARK_NAME (NEW, deliverable 1): every job the game
-- offers at an existing workshop/furnace, from getJobs, each with a token
-- to pass to `queue`, its name, and what it needs.
function list_workshop_jobs(workshop_name)
  if not workshop_name or workshop_name == "" then
    return nil, "usage: df-overseer-workjob list-jobs WORKSHOP_LANDMARK_NAME"
  end
  local bld, resolve_err = resolve_building_generic(workshop_name)
  if not bld then
    return nil, resolve_err
  end
  local jobs, kind_name, jobs_err = get_real_jobs(bld)
  if jobs_err then
    return nil, jobs_err
  end

  local btype = bld:getType()
  local keys = {}
  for k in pairs(jobs) do table.insert(keys, k) end
  table.sort(keys)

  local result_jobs = {}
  local read_failures = {}
  for _, k in ipairs(keys) do
    local contents = jobs[k]
    local token, job_type_name, reaction_name = job_token(contents)
    if not job_type_name then
      table.insert(read_failures, "job #" .. tostring(k) .. ": job_type could not be resolved to a name")
    end
    local items_summary = {}
    for _, spec in ipairs(contents.items or {}) do
      local summary, item_rf = summarise_item_spec(spec)
      table.insert(items_summary, summary)
      for _, f in ipairs(item_rf) do
        table.insert(read_failures, "job #" .. tostring(k) .. " (" .. tostring(contents.name) .. "): " .. f)
      end
    end
    table.insert(result_jobs, {
      token = token,
      name = contents.name,
      job_type = job_type_name,
      reaction = reaction_name,
      items = items_summary,
    })
  end

  if #read_failures > 0 then
    dfhack.printerr("df-overseer-workjob list-jobs: " .. #read_failures
      .. " read failure(s) for workshop '" .. workshop_name .. "', see read_failures in result")
  end

  return {
    workshop = workshop_name,
    workshop_building_type = (btype == df.building_type.Workshop) and "Workshop" or "Furnace",
    workshop_kind = kind_name,
    job_count = #result_jobs,
    jobs = result_jobs,
    read_failures = read_failures,
  }
end

-- Resolves a requested JOB token (a legacy alias OR a generic
-- job_type/reaction token) against a workshop's REAL getJobs() output.
-- Returns (matched_entry, available_tokens) or (nil, available_tokens) if
-- not offered here.
local function resolve_requested_job(requested, jobs)
  local alias = LEGACY_ALIASES[requested]
  local matched
  local available_tokens = {}
  local keys = {}
  for k in pairs(jobs) do table.insert(keys, k) end
  table.sort(keys)
  for _, k in ipairs(keys) do
    local contents = jobs[k]
    local token, job_type_name, reaction_name = job_token(contents)
    if token then
      table.insert(available_tokens, token)
    end
    if not matched then
      local is_match
      if alias then
        is_match = (job_type_name == alias.job_type)
          and (not alias.reaction or reaction_name == alias.reaction)
      else
        is_match = (token ~= nil and token == requested)
      end
      if is_match then
        matched = contents
      end
    end
  end
  return matched, available_tokens
end

-- DRY_RUN defaults to true. REPEAT defaults to false. COUNT defaults to 1
-- (added this stream): queues COUNT identical jobs, refusing rather than
-- truncating if the workshop's current queue plus COUNT would exceed
-- MAX_WORKSHOP_JOBS. See header for the full call sequence real mutation
-- reproduces, and for why this path remains UNTESTED live this stream.
function queue_job(job_name, workshop_name, dry_run, repeat_flag, count)
  if not job_name or job_name == "" then
    return nil, "JOB is required"
  end
  if not workshop_name or workshop_name == "" then
    return nil, "WORKSHOP_LANDMARK_NAME is required"
  end
  local n = tonumber(count) or 1
  if n < 1 or n ~= math.floor(n) then
    return nil, "COUNT must be a whole number of at least 1"
  end

  local bld, resolve_err = resolve_building_generic(workshop_name)
  if not bld then
    return nil, resolve_err
  end
  local jobs, kind_name, jobs_err = get_real_jobs(bld)
  if jobs_err then
    return nil, jobs_err
  end

  local requested = tostring(job_name):lower()
  local matched, available_tokens = resolve_requested_job(requested, jobs)
  if not matched then
    table.sort(available_tokens)
    return nil, "job '" .. tostring(job_name) .. "' is not offered at workshop '"
      .. workshop_name .. "' (" .. tostring(kind_name) .. "); available: "
      .. (#available_tokens > 0 and table.concat(available_tokens, ", ") or "none")
  end

  local dry = truthy_dry_run(dry_run)
  local want_repeat = truthy_repeat(repeat_flag)

  local ok_jobs_n, njobs = pcall(function() return #bld.jobs end)
  local jobs_queued_before = ok_jobs_n and njobs or nil
  if ok_jobs_n and njobs then
    if njobs >= MAX_WORKSHOP_JOBS then
      return nil, string.format(
        "workshop '%s' has a full job queue (%d/%d)", workshop_name, njobs, MAX_WORKSHOP_JOBS)
    end
    if njobs + n > MAX_WORKSHOP_JOBS then
      return nil, string.format(
        "COUNT %d would exceed workshop '%s''s job queue cap (%d queued now, room for %d more, cap %d)",
        n, workshop_name, njobs, MAX_WORKSHOP_JOBS - njobs, MAX_WORKSHOP_JOBS)
    end
  end

  local job_items, diag_or_err, read_failures = build_job_items_from_spec(matched)
  if not job_items then
    return nil, diag_or_err
  end
  local diagnostics = diag_or_err
  read_failures = read_failures or {}

  local _, job_type_name, reaction_name = job_token(matched)

  local base = {
    dry_run = dry,
    job = job_type_name,
    reaction = reaction_name,
    job_name = matched.name,
    workshop = workshop_name,
    workshop_kind = kind_name,
    jobs_queued_before = jobs_queued_before,
    max_workshop_jobs = MAX_WORKSHOP_JOBS,
    job_item_count = #job_items,
    job_item_diagnostics = diagnostics,
    repeat_requested = want_repeat,
    count = n,
    read_failures = read_failures,
  }

  if #read_failures > 0 then
    dfhack.printerr("df-overseer-workjob queue: " .. #read_failures
      .. " read failure(s) building job_items for '" .. tostring(job_name)
      .. "' at '" .. workshop_name .. "', see read_failures in result")
  end

  if dry then
    base.would_queue = true
    return base
  end

  -- Real mutation, n times. Reproduces idle-crafting.lua's makeRockCraft
  -- sequence exactly (dfhack.job.createLinked -> populate -> assignToWorkshop)
  -- -- see header. UNTESTED live: this build stream never runs with
  -- DRY_RUN=false.
  local queued_ids = {}
  for i = 1, n do
    local items_i, err_i = build_job_items_from_spec(matched)
    if not items_i then
      base.create_ok = false
      base.create_error = "job " .. i .. " of " .. n .. ": " .. tostring(err_i)
      base.job_ids = queued_ids
      return base
    end
    local ok_job, job_or_err = pcall(dfhack.job.createLinked)
    if not ok_job or not job_or_err then
      base.create_ok = false
      base.create_error = "job " .. i .. " of " .. n .. ": createLinked failed: " .. tostring(job_or_err)
      base.job_ids = queued_ids
      return base
    end
    local job = job_or_err
    job.job_type = df.job_type[job_type_name]
    if reaction_name then
      job.reaction_name = reaction_name
    end
    local ok_insert = pcall(function()
      for _, jitem in ipairs(items_i) do
        job.job_items.elements:insert('#', jitem)
      end
    end)
    if not ok_insert then
      pcall(dfhack.job.removeJob, job)
      base.create_ok = false
      base.create_error = "job " .. i .. " of " .. n .. ": failed to attach job_items; job removed"
      base.job_ids = queued_ids
      return base
    end
    local ok_assign, assigned = pcall(dfhack.job.assignToWorkshop, job, bld)
    if not ok_assign or not assigned then
      -- Never leave an orphan job in world.jobs.list not linked to any
      -- workshop -- see df-overseer-orders.lua's cancel_order for the same
      -- "clean up rather than leave dangling state" convention.
      pcall(dfhack.job.removeJob, job)
      base.create_ok = false
      base.create_error = "job " .. i .. " of " .. n
        .. ": assignToWorkshop failed (workshop full or rejected the job); job removed"
      base.job_ids = queued_ids
      return base
    end
    if want_repeat then
      local ok_repeat = pcall(function() job.flags['repeat'] = true end)
      base.repeat_set = ok_repeat
    end
    table.insert(queued_ids, job.id)
  end

  base.create_ok = true
  base.job_ids = queued_ids
  base.job_id = queued_ids[1]
  return base
end

-- Finds a live job by id in df.global.world.jobs.list. Returns the job
-- object plus its resolved workshop holder (nil if none), or nil plus an
-- error if no such job exists.
local function find_job_by_id(job_id)
  for _, job in utils.listpairs(df.global.world.jobs.list) do
    if job.id == job_id then
      local ok_holder, holder = pcall(dfhack.job.getHolder, job)
      return job, (ok_holder and holder) or nil
    end
  end
  return nil, "no job with id " .. tostring(job_id)
end

-- See header: refuses any job that is not a workshop-held production job,
-- rather than cancelling it. DRY_RUN defaults to true. UNTESTED live.
function cancel_job(job_id, dry_run)
  job_id = tonumber(job_id)
  if not job_id then
    return nil, "JOB_ID must be a number"
  end
  local dry = truthy_dry_run(dry_run)

  local job, holder_or_err = find_job_by_id(job_id)
  if not job then
    return nil, holder_or_err
  end
  local holder = holder_or_err
  if not holder then
    return nil, "job " .. job_id .. " has no workshop holder"
      .. " (not this fort's own queued workshop-production work;"
      .. " this tool only cancels jobs created at a workshop)"
  end
  local ok_btype, btype = pcall(function() return holder:getType() end)
  if not ok_btype or btype ~= df.building_type.Workshop then
    return nil, "job " .. job_id .. " is held by a non-workshop building,"
      .. " refusing (not this fort's own queued workshop-production work)"
  end

  local ok_type, jtype = pcall(function() return df.job_type[job.job_type] end)
  local origin = stuckjobs_mod.job_origin(job)
  local base = {
    dry_run = dry,
    job_id = job_id,
    job_type = ok_type and jtype or "unknown",
    order_id = origin.order_id,
    from_order = origin.from_order,
  }

  if dry then
    base.would_cancel = true
    return base
  end

  -- Real mutation. UNTESTED live -- see header.
  local ok_remove = pcall(dfhack.job.removeJob, job)
  base.cancel_ok = ok_remove
  return base
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "list" then
  print(json.encode(list_jobs()))
elseif cmd == "list-jobs" then
  local workshop = args[2]
  local result, err = list_workshop_jobs(workshop)
  print(json.encode(err and {error = err} or result))
elseif cmd == "queue" then
  local job, workshop, dry_run, repeat_flag, count = args[2], args[3], args[4], args[5], args[6]
  if not (job and workshop) then
    print("usage: df-overseer-workjob queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN] [REPEAT] [COUNT]")
  else
    local result, err = queue_job(job, workshop, dry_run, repeat_flag, count)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "cancel" then
  local job_id, dry_run = args[2], args[3]
  if not job_id then
    print("usage: df-overseer-workjob cancel JOB_ID [DRY_RUN]")
  else
    local result, err = cancel_job(job_id, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-workjob list")
  print("usage: df-overseer-workjob list-jobs WORKSHOP_LANDMARK_NAME")
  print("usage: df-overseer-workjob queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN] [REPEAT] [COUNT]")
  print("usage: df-overseer-workjob cancel JOB_ID [DRY_RUN]")
end
