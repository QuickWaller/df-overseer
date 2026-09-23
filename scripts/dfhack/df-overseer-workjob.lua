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
-- workshop is not in that queue and never was. That is a legitimate vanilla
-- action, unlike hand-setting `status.validated` (well-finish's own one-off,
-- labelled exception, not to be repeated). This file is that action, built
-- as a proper, reviewed, tested tool rather than the ad-hoc script
-- well-and-harvest.md section 6 drafted and had refused by the permission
-- classifier (`[Modify Shared Resources]`) when it tried to run it directly.
--
-- **A NEW FILE, not a df-overseer-workshop.lua subcommand.** That file's own
-- header is explicit about its scope: it "finds and builds workshops"
-- (structures), sharing df-overseer-openarea.lua's site-selection machinery
-- with df-overseer-farm.lua/df-overseer-zone.lua/df-overseer-trees.lua/
-- df-overseer-well.lua. Queuing a job at an EXISTING workshop is a different
-- concern with no site-finding step at all (the workshop already exists,
-- addressed by landmark name, same as df-overseer-landmarks.lua's own
-- building enumeration already names it) -- forcing it into workshop.lua
-- would blur that file's one job (siting/building) with this one
-- (queuing/manufacturing), the same separation of concerns
-- df-overseer-orders.lua already keeps from df-overseer-workshop.lua today.
--
-- THE DFHACK CODE PATH FOLLOWED, cited by file, not guessed (same standard
-- df-overseer-orders.lua's header sets):
--
--   `dfhack.job.createLinked()` + `df.job_item:new()` + `job.job_items.
--   elements:insert('#', jitem)` + `dfhack.job.assignToWorkshop(job,
--   workshop)` is the exact sequence DFHack's OWN shipped script
--   `idle-crafting.lua`'s `makeRockCraft` function uses to queue a rock-
--   crafting job at a specific, already-built workshop with no Manager
--   involved (github.com/DFHack/scripts, `idle-crafting.lua`, function
--   `makeRockCraft`) -- confirmed again independently in
--   `library/lua/dfhack/workshops.lua` (github.com/DFHack/dfhack), the
--   module backing the real in-game "q -> add job" menu, whose own Masons
--   "construct blocks" and Mechanics "construct mechanisms" job
--   definitions use an IDENTICAL job_item: `item_type=BOULDER,
--   vector_id=BOULDER, mat_type=0, mat_index=-1, quantity=1,
--   flags3={hard=true}` for both. This matches, verbatim, what
--   handoffs/2026-09-19-well-and-harvest.md section 6 already found live
--   on THIS install reading the same two files this session re-confirmed
--   against the public DFHack source. `dfhack.job.assignToWorkshop` is
--   registered in `library/LuaApi.cpp`'s `dfhack_job_module` table
--   (github.com/DFHack/dfhack) and is documented (DFHack Lua API
--   reference, dfhack.job section) to do nothing and return false if the
--   workshop already has 10 jobs queued -- `MAX_WORKSHOP_JOBS` below,
--   checked BEFORE attempting the call so a full queue is refused with a
--   clear reason rather than a silent no-op.
--
--   `CustomReaction` jobs (BREW_DRINK_FROM_PLANT) are different: no DFHack
--   script this session could find builds a reaction job's job_items
--   GENERICALLY from the reaction's own reagents. `idle-crafting.lua` hand-
--   writes exactly one known reagent (BOULDER); `gui/workshop-job.lua`
--   (github.com/DFHack/scripts) only READS an already-populated job's
--   existing `job_items`/`contains` back against `df.reaction.find(iobj.
--   reaction_id).reagents[ri]` -- it never constructs a new job_item from a
--   reagent. The vanilla "add job" screen does this construction inside
--   the DF engine's own C++ binary, not in any DFHack Lua script this
--   project has found. So `reagent_job_item` below is THIS PROJECT'S OWN
--   code, not a reused DFHack path -- flagged honestly rather than claimed
--   otherwise. It does the one thing that is not a guess: a straight field
--   copy of `item_type`/`item_subtype`/`mat_type`/`mat_index`/`quantity`
--   off each live `df.reaction_reagent` entry in `df.global.world.raws.
--   reactions.reactions[i].reagents` into a matching `df.job_item` --
--   these are the same fields the raw `[REAGENT:name:quantity:item_type:
--   item_subtype:mat_type:mat_index]` token (DF's own documented modding
--   format) populates, read back rather than re-derived. **It REFUSES,
--   rather than guesses, whenever a reagent's own `item_type` is a
--   wildcard/tag-matched NONE** (a reagent matched by a tag like
--   `[CONTAINER]` rather than a concrete item type -- vanilla brewing's
--   own "an empty barrel or bag" reagent is exactly this shape on the
--   wiki's documented token, unconfirmed against this install's live raws
--   by this offline stream). A caller sees exactly which reagent could not
--   be resolved and why, never a job queued on a half-guessed spec.
--
-- NEVER sets `status.validated` and never touches
-- `df.global.world.manager_orders.all` -- this file has no relationship to
-- df-overseer-orders.lua's queue at all, by design; it is the OTHER
-- legitimate route, not a patch on the first one.
--
-- Workshop resolution reuses two already-verified fields from THIS
-- project's own code (not re-derived): `bld.type` compared against
-- `df.workshop_type[...]` is df-overseer-workshop.lua's own
-- `workshop_exists_count` pattern (that file, this repo) for "is this
-- building the right kind of workshop"; `bld.flags.exists` is
-- df-overseer-farm.lua's own `set_farm_crop`/`find_farm_plots` pattern for
-- "is construction actually finished" (that file, this repo, both already
-- live-verified in prior sessions). A workshop landmark is resolved by
-- exact name match against `dfhack.buildings.getName(bld)`, the same
-- lookup df-overseer-landmarks.lua's own building enumeration already
-- performs -- reading, not reqscript-ing, to avoid coupling this file's
-- addressing to that file's own persisted-seed logic.
--
-- DRY_RUN defaults to true, same contract as every other write tool in this
-- project (df-overseer-orders.lua's create_order, df-overseer-workshop.lua's
-- build_workshop). A dry run resolves the workshop, checks its kind,
-- construction state and queue length, and builds (but never inserts) the
-- job_item spec, reporting exactly what would be queued and any refusal
-- reason -- without ever calling dfhack.job.createLinked. Only an explicit
-- `false` performs the real mutation. **This build stream never sets
-- DRY_RUN to false against a live DFHack process -- the real mutation path
-- below is UNTESTED live, exactly as this repo's convention requires this
-- to be stated (df-overseer-orders.lua/df-overseer-workshop.lua's own
-- headers say the same about their own real-mutation paths before first
-- live use).**
--
-- No coordinates in any input or output. `resolve_workshop` reads a
-- building object server-side and never returns or prints its x/y/z; the
-- caller only ever sees the landmark NAME back.
--
-- CANCEL, added handoffs/2026-09-23-order-job-attribution-and-checks.md item
-- 5: a write tool, sole_writer overseer only (agents/ROSTER.yaml), same as
-- queue above -- kept out of every advisor's allowlist. Takes a job id (not
-- a workshop landmark: cancelling addresses the specific job, the same
-- granularity `dfhack.job.removeJob` itself works at). REFUSES, rather than
-- cancelling, any job that is not this fort's own queued workshop-production
-- work: a job with no resolvable workshop holder (a haul job, an eat/sleep
-- job, anything not a "q -> add job" style production job) is out of this
-- tool's domain by construction, the same boundary queue_job's own job_items
-- only ever build for a workshop job. Reuses
-- df-overseer-stuckjobs.lua's `job_origin` (reqscript'd, see that file's own
-- header) rather than a second attribution implementation, per CLAUDE.md's
-- generalisability rule. DRY_RUN defaults to true, same contract as
-- queue_job. UNTESTED live: this stream never sets DRY_RUN to false against
-- a live DFHack process (Hard lines: no unbounded query, and no write verb
-- in this stream is exercised against the fort -- the exact command is
-- recorded as owed for the first supervised run).
--
-- Usage: ./dfhack-run df-overseer-workjob list
-- Usage: ./dfhack-run df-overseer-workjob queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN] [REPEAT]
-- Usage: ./dfhack-run df-overseer-workjob cancel JOB_ID [DRY_RUN]

local json = require('json')
local utils = require('utils')
local textutil = reqscript('df-overseer-textutil')
local stuckjobs_mod = reqscript('df-overseer-stuckjobs')

-- Per DFHack's own documented cap on dfhack.job.assignToWorkshop (see
-- header): it silently does nothing and returns false past this many jobs
-- queued at one workshop. Checked here first so the refusal names the real
-- reason instead of a bare "assign failed".
local MAX_WORKSHOP_JOBS = 10

-- JOB_INFO, structured for a later job to be a new table entry, matching
-- df-overseer-orders.lua's own JOB_INFO/df-overseer-zone.lua's KIND_INFO
-- extensibility precedent.
--
--   kind = "fixed_boulder" -> a single hand-built BOULDER job_item, the
--     idle-crafting.lua/workshops.lua spec cited above. Used for the two
--     plain construction job types the well needs.
--   kind = "reaction" -> job_items built generically from the named
--     reaction's own live reagents (reagent_job_item below), refusing
--     rather than guessing on any reagent it cannot resolve.
--
-- A cooking/processing job (PrepareMeal) was considered and deliberately
-- left out: unlike ConstructBlocks/ConstructMechanisms/BREW_DRINK_FROM_PLANT,
-- a meal job's own ingredient count and quality tier are chosen at queue
-- time in the real "add job" screen (1-5 ingredients depending on the
-- selected meal quality), not fixed by the job type or derivable from a
-- single reaction's reagents the way brewing is -- building that spec
-- correctly would mean guessing a meal-quality-to-ingredient-count mapping
-- this offline stream has no live install to check, which is exactly the
-- guessing this file's whole design refuses to do. Not cheap; left out.
local JOB_INFO = {
  blocks = {
    job_type = "ConstructBlocks",
    workshop_subtype = "Masons",
    kind = "fixed_boulder",
  },
  mechanisms = {
    job_type = "ConstructMechanisms",
    workshop_subtype = "Mechanics",
    kind = "fixed_boulder",
  },
  brew_drink = {
    job_type = "CustomReaction",
    reaction = "BREW_DRINK_FROM_PLANT",
    workshop_subtype = "Still",
    kind = "reaction",
  },
}

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- The idle-crafting.lua/workshops.lua spec, cited in full in the header.
-- Verified, not guessed: matches handoffs/2026-09-19-well-and-harvest.md
-- section 6's own live read of this exact install's own source files.
local function fixed_boulder_job_item()
  local jitem = df.job_item:new()
  jitem.item_type = df.item_type.BOULDER
  jitem.item_subtype = -1
  jitem.mat_type = 0
  jitem.mat_index = -1
  jitem.quantity = 1
  jitem.vector_id = df.job_item_vector_id.BOULDER
  jitem.flags3.hard = true
  return jitem
end

-- Live lookup by the reaction's own `code` field (the same field
-- df-overseer-orders.lua's create_order comment cites for brew_drink/soap),
-- never a hardcoded index -- survives raws reordering.
local function find_reaction(code)
  local reactions = df.global.world.raws.reactions.reactions
  for i = 0, #reactions - 1 do
    if reactions[i].code == code then
      return reactions[i]
    end
  end
  return nil
end

-- See header: a straight field copy off a live df.reaction_reagent, not a
-- guess, refusing on a wildcard/tag-matched reagent (item_type unset or
-- negative) rather than inventing a filter for it.
local function reagent_job_item(reagent, idx)
  local ok_it, item_type = pcall(function() return reagent.item_type end)
  if not ok_it or item_type == nil or item_type < 0 then
    return nil, string.format(
      "reagent %d has no concrete item_type (a wildcard/tag-matched reagent"
        .. " -- e.g. a generic container match -- is not supported by this"
        .. " tool; refusing rather than guessing a filter for it)", idx)
  end
  local jitem = df.job_item:new()
  jitem.item_type = item_type
  local ok_ist, item_subtype = pcall(function() return reagent.item_subtype end)
  jitem.item_subtype = (ok_ist and item_subtype) or -1
  local ok_mt, mat_type = pcall(function() return reagent.mat_type end)
  jitem.mat_type = (ok_mt and mat_type) or -1
  local ok_mi, mat_index = pcall(function() return reagent.mat_index end)
  jitem.mat_index = (ok_mi and mat_index) or -1
  local ok_q, quantity = pcall(function() return reagent.quantity end)
  jitem.quantity = (ok_q and quantity and quantity > 0) and quantity or 1
  return jitem
end

-- Returns a list of df.job_item objects (not yet inserted into any job) and
-- a per-reagent diagnostics list, or nil plus an error naming exactly which
-- reagent could not be resolved. Never partially succeeds: either every
-- reagent (fixed spec's one slot, or a reaction's whole reagent list)
-- resolves, or nothing is returned to queue.
local function build_job_items(info)
  if info.kind == "fixed_boulder" then
    return {fixed_boulder_job_item()}, {{resolved = true, spec = "BOULDER (mat_type=0, flags3.hard)"}}
  elseif info.kind == "reaction" then
    local reaction = find_reaction(info.reaction)
    if not reaction then
      return nil, "reaction not found in this install's own raws: " .. info.reaction
    end
    local job_items, diagnostics = {}, {}
    for i = 0, #reaction.reagents - 1 do
      local jitem, err = reagent_job_item(reaction.reagents[i], i)
      if not jitem then
        return nil, string.format(
          "cannot build job_items for reaction %s: %s", info.reaction, err)
      end
      table.insert(job_items, jitem)
      table.insert(diagnostics, {resolved = true, reagent_index = i})
    end
    if #job_items == 0 then
      return nil, "reaction " .. info.reaction .. " has no reagents (unexpected)"
    end
    return job_items, diagnostics
  end
  return nil, "internal error: unknown job kind " .. tostring(info.kind)
end

-- Resolves WORKSHOP_LANDMARK_NAME to a live building object, refusing
-- explicitly (never guessing) on every bad case the handoff names: not
-- found, not a workshop at all, the wrong kind of workshop, or still under
-- construction. Returns the building object -- callers must never print or
-- return it directly (no coordinates in output; see header).
local function resolve_workshop(name, info)
  local target_subtype = df.workshop_type[info.workshop_subtype]
  local found_wrong_kind = nil
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_name, bname = pcall(dfhack.buildings.getName, bld)
    bname = ok_name and textutil.to_utf8(bname) or bname
    if ok_name and bname == name then
      local ok_btype, btype = pcall(function() return bld:getType() end)
      if not ok_btype or btype ~= df.building_type.Workshop then
        return nil, "landmark '" .. name .. "' is not a workshop"
      end
      -- df-overseer-workshop.lua's own workshop_exists_count pattern: the
      -- subtype field is confusingly named `.type`, not `.subtype`.
      local ok_sub, sub = pcall(function() return bld.type end)
      if not ok_sub or sub ~= target_subtype then
        found_wrong_kind = true
      else
        -- df-overseer-farm.lua's own construction-gate pattern.
        local ok_exists, exists = pcall(function() return bld.flags.exists end)
        if not ok_exists or not exists then
          return nil, "workshop '" .. name .. "' is still under construction"
            .. " (flags.exists is false)"
        end
        return bld
      end
    end
  end
  if found_wrong_kind then
    return nil, "workshop '" .. name .. "' is not a " .. info.workshop_subtype
      .. " workshop (needed for " .. tostring(JOB_INFO[info._key] and info._key or "this job") .. ")"
  end
  return nil, "unknown workshop: " .. tostring(name)
end

-- Known JOB values -- the same vocabulary the real "q -> add job" menu
-- offers at the matching workshop kind. Exported so a caller (or a future
-- reqscript'ing tool) can list them without shelling out to the CLI.
function list_jobs()
  local known = {}
  for k in pairs(JOB_INFO) do table.insert(known, k) end
  table.sort(known)
  return {jobs = known}
end

-- REPEAT, added handoffs/2026-09-23-order-job-attribution-and-checks.md item
-- 6: "let workjob.queue set it, off by default, explicit when asked."
-- Confirmed from DFHack's own current shipped source, not guessed: both
-- `gui/workflow.lua` and (independently) a search of DFHack's df-structures
-- job_flags bitfield agree the field is `job.flags['repeat']` (bracket
-- notation required -- `repeat` is a Lua reserved word, so `job.flags.repeat`
-- would not even parse). This is a source-code-level confirmation, the same
-- standard this file's header already applies to the fixed_boulder_job_item
-- spec (cited to idle-crafting.lua/workshops.lua by name), NOT an
-- introspection of THIS install's own live df.job._fields for a `repeat` key
-- inside its flags bitfield -- that live confirmation was out of reach this
-- stream (offline build; the hard lines forbid any write verb being
-- exercised against the fort before deploy). If a live read ever shows this
-- field does not exist or behaves differently on this build, that is a real
-- finding to record, not a silent assumption to keep making.
local function truthy_repeat(v)
  if v == nil then
    return false
  end
  local s = tostring(v):lower()
  return s == "true" or s == "1" or s == "yes"
end

-- DRY_RUN defaults to true. See header for the exact call sequence this
-- mirrors when DRY_RUN is false, and why that path is UNTESTED live this
-- stream. REPEAT defaults to false (off unless explicitly asked for; see
-- the REPEAT comment above) and is only meaningful when DRY_RUN is false.
function queue_job(job_name, workshop_name, dry_run, repeat_flag)
  local key = tostring(job_name):lower()
  local info = JOB_INFO[key]
  if not info then
    local known = {}
    for k in pairs(JOB_INFO) do table.insert(known, k) end
    table.sort(known)
    return nil, "unknown job: " .. tostring(job_name)
      .. " (expected one of: " .. table.concat(known, ", ") .. ")"
  end
  info._key = key
  if not workshop_name or workshop_name == "" then
    return nil, "WORKSHOP_LANDMARK_NAME is required"
  end
  local dry = truthy_dry_run(dry_run)

  local bld, resolve_err = resolve_workshop(workshop_name, info)
  if not bld then
    return nil, resolve_err
  end

  local ok_jobs, njobs = pcall(function() return #bld.jobs end)
  local jobs_queued_before = ok_jobs and njobs or nil
  if ok_jobs and njobs and njobs >= MAX_WORKSHOP_JOBS then
    return nil, string.format(
      "workshop '%s' has a full job queue (%d/%d)",
      workshop_name, njobs, MAX_WORKSHOP_JOBS)
  end

  local job_items, items_or_err = build_job_items(info)
  if not job_items then
    return nil, items_or_err
  end
  local diagnostics = items_or_err

  local want_repeat = truthy_repeat(repeat_flag)

  local base = {
    dry_run = dry,
    job = info.job_type,
    reaction = info.reaction,
    workshop = workshop_name,
    workshop_kind = info.workshop_subtype,
    jobs_queued_before = jobs_queued_before,
    max_workshop_jobs = MAX_WORKSHOP_JOBS,
    job_item_count = #job_items,
    job_item_diagnostics = diagnostics,
    repeat_requested = want_repeat,
  }

  if dry then
    base.would_queue = true
    return base
  end

  -- Real mutation. Reproduces idle-crafting.lua's makeRockCraft sequence
  -- exactly (dfhack.job.createLinked -> populate -> assignToWorkshop) --
  -- see header. UNTESTED live: this build stream never runs with
  -- DRY_RUN=false.
  local ok_job, job_or_err = pcall(dfhack.job.createLinked)
  if not ok_job or not job_or_err then
    base.create_ok = false
    base.create_error = tostring(job_or_err)
    return base
  end
  local job = job_or_err
  job.job_type = df.job_type[info.job_type]
  if info.reaction then
    job.reaction_name = info.reaction
  end
  local ok_insert = pcall(function()
    for _, jitem in ipairs(job_items) do
      job.job_items.elements:insert('#', jitem)
    end
  end)
  if not ok_insert then
    pcall(dfhack.job.removeJob, job)
    base.create_ok = false
    base.create_error = "failed to attach job_items; job removed"
    return base
  end

  local ok_assign, assigned = pcall(dfhack.job.assignToWorkshop, job, bld)
  if not ok_assign or not assigned then
    -- Never leave an orphan job in world.jobs.list not linked to any
    -- workshop -- see df-overseer-orders.lua's cancel_order for the same
    -- "clean up rather than leave dangling state" convention.
    pcall(dfhack.job.removeJob, job)
    base.create_ok = false
    base.create_error = "assignToWorkshop failed (workshop full or rejected"
      .. " the job); job removed"
    return base
  end

  if want_repeat then
    local ok_repeat = pcall(function() job.flags['repeat'] = true end)
    base.repeat_set = ok_repeat
  end

  base.create_ok = true
  base.job_id = job.id
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
-- rather than cancelling it -- this tool's domain is workshop jobs
-- (queue_job's own creation contract), not any job on world.jobs.list.
-- DRY_RUN defaults to true. UNTESTED live -- see header.
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
elseif cmd == "queue" then
  local job, workshop, dry_run, repeat_flag = args[2], args[3], args[4], args[5]
  if not (job and workshop) then
    print("usage: df-overseer-workjob queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN] [REPEAT]")
  else
    local result, err = queue_job(job, workshop, dry_run, repeat_flag)
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
  print("usage: df-overseer-workjob queue JOB WORKSHOP_LANDMARK_NAME [DRY_RUN] [REPEAT]")
  print("usage: df-overseer-workjob cancel JOB_ID [DRY_RUN]")
end
