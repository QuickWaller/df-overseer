-- df-overseer-stuckjobs.lua
--@module = true
--
-- docs/PURPOSE.md build order item 8: get_stuck_jobs. Flagged in
-- research/2026-08-25-spatial-perception.md §3.2/§5 as the least-verified
-- primitive in the whole design: "I could not find a stock script that
-- walks the full df.global.world.job_list linked list... flagging as
-- unverified-locally-but-standard: use with a touch more caution, and
-- validate the traversal against a live game before relying on it."
--
-- Actually verified this session, not just trusted as standard knowledge:
--   - `utils.listpairs(df.global.world.jobs.list)` is the real, canonical
--     traversal idiom -- confirmed live in THREE separate stock
--     scripts/plugins on this exact install (hack/scripts/suspend.lua,
--     hack/lua/plugins/dwarfvet.lua, hack/lua/plugins/suspendmanager.lua),
--     stronger confirmation than the research doc managed to find.
--   - `job.flags.working` / `job.flags.suspend` are confirmed real,
--     shipped-code fields (suspend.lua sets both;
--     internal/notify/notifications.lua reads .working).
--   - `job.pos.x/y/z` and `dfhack.job.getWorker(job)` confirmed via
--     hack/scripts/do-job-now.lua.
--
-- "Stuck" here means: no worker currently assigned
-- (dfhack.job.getWorker(job) == nil). A job with `job.flags.suspend` set
-- is reported too (it genuinely isn't progressing) but distinctly labeled
-- `waiting_on = "suspended"` -- a suspended job has an explicit,
-- deliberate reason, not an unexplained stall. This does NOT diagnose WHY
-- an unsuspended job has no worker (missing skill, missing material, no
-- idle unit available) -- that's real, separate analysis this first slice
-- doesn't attempt. `waiting_on` for the ordinary case is just "no worker
-- assigned", an honest label, not a guessed root cause.
--
-- `idle_ticks` needs to know when a job started, which DF does not expose
-- as a plain queryable field on the job struct -- so this script
-- registers its own eventful.enableEvent(JOB_INITIATED) handler (same
-- pattern as df-overseer-diff.lua) to record each job's start tick by id,
-- once per DF process lifetime. A job that already existed BEFORE this
-- script's first registration this process lifetime has no recorded
-- start tick and is reported with `idle_ticks = null`, not a guessed
-- value -- an honest gap, not silently defaulted to 0. The `min_idle_ticks`
-- filter only excludes jobs with a KNOWN idle_ticks below the threshold;
-- a job with an unknown idle_ticks is always included, since silently
-- hiding it would be worse than surfacing it with an honest "don't know
-- how long" marker.
--
-- ATTRIBUTION, added handoffs/2026-09-23-order-job-attribution-and-checks.md:
-- `df.job` has an `order_id` field, found by the orchestrating session's live
-- introspection of `df.job._fields` on this install and matching DFHack's own
-- `/opt/df/game/hack/scripts/do-job-now.lua:106` (`job.order_id == needle`).
-- CORRECTS `research/2026-09-18-work-orders.md`'s own explicit "no field
-- found" negative (dated correction note added there, not a silent edit).
-- `job_origin` below is the one shared way this project describes a job's
-- origin -- `get_stuck_jobs` and `find_jobs_by_type` both use it, so a caller
-- never sees two different shapes for the same fact. The sentinel value for
-- "no order" is NOT independently confirmed live this stream (offline build,
-- no VM in this session's write-access window before deploy); read
-- defensively and report both the raw field and the derived boolean, so a
-- wrong assumption about the sentinel is visible in `order_id_raw` rather
-- than silently baked into `from_order`. Treated as "from an order" only
-- when `order_id` reads as a non-nil integer >= 0, the ordinary DF/DFHack
-- convention for "no id" (order ids for orders created via
-- df-overseer-orders.lua's own create_order are always >= 0 by the time
-- `preprocess_orders` finishes -- see that file's own header -- so a
-- negative order_id is not mistaken for a real order this project created).
-- A real (non-local) function so other df-overseer-*.lua tools can
-- reqscript this file and reuse the one shared shape -- see the comment
-- above. df-overseer-workjob.lua's cancel_job does exactly this.
-- NOTE: no `ok and v or nil` shortcut for `from_order` -- it is a boolean,
-- and that idiom silently turns a real `false` into `nil` (Lua's
-- `false or nil` is `nil`), backwards for a yes/no field. Built with a plain
-- if/else instead.
function job_origin(job)
  local ok, raw = pcall(function() return job.order_id end)
  if not ok or raw == nil then
    return {order_id = nil, order_id_raw = nil, from_order = nil}
  end
  local from_order
  if raw >= 0 then
    from_order = true
  else
    from_order = false
  end
  return {
    order_id = from_order and raw or nil,
    order_id_raw = raw,
    from_order = from_order,
  }
end

-- Usage: ./dfhack-run df-overseer-stuckjobs find [MIN_IDLE_TICKS]

local json = require('json')
local utils = require('utils')
local landmarks_mod = reqscript('df-overseer-landmarks')
local textutil = reqscript('df-overseer-textutil')

if not _G.__df_overseer_stuckjobs_registered then
  _G.__df_overseer_job_start_tick = _G.__df_overseer_job_start_tick or {}

  local eventful = require('plugins.eventful')
  eventful.enableEvent(eventful.eventType.JOB_INITIATED, 10)
  eventful.onJobInitiated.df_overseer_stuckjobs = function(job)
    _G.__df_overseer_job_start_tick[job.id] = dfhack.world.ReadCurrentTick()
  end

  _G.__df_overseer_stuckjobs_registered = true
end

function get_stuck_jobs(min_idle_ticks)
  local now = dfhack.world.ReadCurrentTick()
  local results = {}
  for _, job in utils.listpairs(df.global.world.jobs.list) do
    local ok_worker, worker = pcall(dfhack.job.getWorker, job)
    local has_worker = ok_worker and worker ~= nil
    if not has_worker then
      local start_tick = _G.__df_overseer_job_start_tick[job.id]
      local idle_ticks = start_tick and (now - start_tick) or nil
      if not min_idle_ticks or min_idle_ticks == 0 or not idle_ticks
          or idle_ticks >= min_idle_ticks then
        local ok_name, name = pcall(dfhack.job.getName, job)
        local ok_type, jtype = pcall(function() return df.job_type[job.job_type] end)
        local ok_holder, holder = pcall(dfhack.job.getHolder, job)
        local building_name = nil
        if ok_holder and holder then
          local ok_bname, bname = pcall(dfhack.buildings.getName, holder)
          building_name = ok_bname and textutil.to_utf8(bname) or nil
        end
        local ok_near, near_info = pcall(
          landmarks_mod.nearest_landmark, job.pos.x, job.pos.y, job.pos.z)
        local info = ok_near and near_info
        local origin = job_origin(job)
        table.insert(results, {
          job_type = ok_type and jtype or "unknown",
          detail = ok_name and textutil.to_utf8(name) or nil,
          building = building_name,
          waiting_on = job.flags.suspend and "suspended" or "no worker assigned",
          idle_ticks = idle_ticks,
          near_landmark = info and info.name or nil,
          direction = info and info.direction or nil,
          distance_tiles = info and info.distance_tiles or nil,
          order_id = origin.order_id,
          from_order = origin.from_order,
        })
      end
    end
  end
  return results
end

-- Added handoffs/2026-09-23-order-job-attribution-and-checks.md item 4 (the
-- duplicate-production check): unlike get_stuck_jobs above, this does NOT
-- filter to workerless jobs -- a job already being worked is still "in
-- flight" and a duplicate check that missed it would undercount real
-- production. Matches by job_type name (and reaction_name, when the job
-- type is CustomReaction) against every live job on this site, stuck or not.
-- Exported and reqscript'd by df-overseer-orders.lua's check_duplicate so
-- both routes' in-flight production use the one traversal and the one
-- job_origin helper, per CLAUDE.md's generalisability rule ("one shared way
-- of describing a job's origin, not a special case per tool").
function find_jobs_by_type(job_type_name, reaction_name)
  local results = {}
  for _, job in utils.listpairs(df.global.world.jobs.list) do
    local ok_type, jtype = pcall(function() return df.job_type[job.job_type] end)
    if ok_type and jtype == job_type_name then
      local reaction_ok = true
      if reaction_name then
        local ok_r, r = pcall(function() return job.reaction_name end)
        reaction_ok = ok_r and r == reaction_name
      end
      if reaction_ok then
        local ok_worker, worker = pcall(dfhack.job.getWorker, job)
        local origin = job_origin(job)
        table.insert(results, {
          job_id = job.id,
          job_type = jtype,
          has_worker = ok_worker and worker ~= nil,
          order_id = origin.order_id,
          from_order = origin.from_order,
        })
      end
    end
  end
  return results
end

-- Same module-load guard as the other df-overseer-*.lua scripts.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "find" then
  local min_idle = tonumber(args[2])
  print(json.encode(get_stuck_jobs(min_idle)))
else
  print("usage: df-overseer-stuckjobs find [MIN_IDLE_TICKS]")
end
