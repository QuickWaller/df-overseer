-- df-overseer-sampler.lua
--@module = true
--
-- handoffs/2026-09-19-sampler.md. The game samples itself: this file is
-- registered as a DFHack `repeat` (every 1 game day) via
-- dfhack-config/init/onMapLoad.init, next to the existing
-- `overseer-autosave` line, which it does not touch. It writes one
-- append-only JSONL record per sample to a per-timeline file, in EXACTLY
-- the version-1 record format `docs/TIMESERIES.md` defines. That file is
-- the contract between this script and the separate `dfseries` store; it is
-- not edited here, and if anything in it turns out to be wrong that is
-- reported in the handoff write-up, not patched in place.
--
-- ============================================================================
-- BOUNDED READS ONLY -- docs/TRAPS.md, "DFHack command execution is not
-- safely concurrent" (2026-09-19: an unbounded full-map query wedged the
-- command pipe for 10+ minutes and took the watchdog's own pause call with
-- it, costing a 22,000-tick rollback). Every function below iterates a
-- specific, named vector -- citizens, world.units.all, one item-type vector
-- per known type, the job list -- and NEVER touches map tiles. The item
-- vectors and the job list are exactly the primitives docs/TIMESERIES.md
-- design decision 4 names as the allowed shape.
--
-- ============================================================================
-- is_fort_owned is COPIED, not required, from df-overseer-stocks.lua.
-- That file's own predicate (`not flags.trader and not flags.garbage_collect
-- and not flags.removed and not on a hidden tile`) is a local function, not
-- exported, and this stream's touched surfaces explicitly exclude editing
-- df-overseer-stocks.lua to export it. So the LOGIC is reused verbatim --
-- copied unchanged, not re-derived -- while the Lua binding is necessarily
-- a duplicate. See that file's header for the live verification behind
-- this exact predicate (flags.trader, not flags.foreign; verified against
-- Uniboslan 2026-09-16).
--
-- ============================================================================
-- A FAILED READ IS NEVER A ZERO. Same rule as the silent-zero fix
-- (handoffs/2026-09-19-silent-zero-fix.md): every metric this file can
-- produce goes through `add_metric`, which either records a real value or
-- an explicit `error` string with `value` left out of the Lua table
-- entirely -- and the hand-rolled JSON encoder below (see next section)
-- turns an absent value into a literal JSON `null`, per the contract's
-- "value is a number or null; null requires error" rule.
--
-- ============================================================================
-- WHY A HAND-ROLLED JSON ENCODER INSTEAD OF `require('json')`.
-- Every other df-overseer-*.lua script uses the bundled `json` module, and
-- that module's `encode()` is trusted for well-formed, all-present tables.
-- But this file's whole point is emitting an EXPLICIT `null` for a failed
-- read, and in Lua a table field set to `nil` is not stored at all --
-- `t.value = nil` makes `value` ABSENT from the table, not present-with-null.
-- df-overseer-stuckjobs.lua's `idle_ticks = idle_ticks` idiom (referenced in
-- df-overseer-stocks.lua's own header) relies on exactly this: a failed
-- `idle_ticks` is OMITTED from the JSON object, not written as `null`. The
-- deploy-and-live-verify write-up (handoffs/2026-09-19-deploy-and-live-verify.md)
-- confirms this for the same encoder: a broken lookup made a field "absent
-- from the object entirely -- not present, not 0". That is fine for that
-- tool's contract (caller checks for the key), but docs/TIMESERIES.md is
-- explicit that `value` must be a literal JSON `null`, not an absent key, so
-- the store can tell "no metric was attempted" (key absent, a store-side
-- version drift) from "a metric was attempted and failed" (key present,
-- value null, error set). Rather than assume the bundled `json` module's
-- untested null-encoding behaviour one way or the other -- exactly the kind
-- of assumption this project's own TRAPS.md exists to warn against -- this
-- file hand-rolls a small encoder for its own fixed, fully-known record
-- shape, where "null" is written literally and on purpose.

local SAMPLER_VERSION = "1.0.0"
local SAMPLE_DIR = "dfhack-config/timeseries"
local STATE_FILE = SAMPLE_DIR .. "/.current_timeline.txt"

-- ----------------------------------------------------------------------------
-- Minimal JSON emission, scoped ONLY to this file's own fixed record shape
-- (top-level scalars plus one flat `metrics` array of {subject, metric,
-- value|null, unit, error?}). Not a general encoder.

local function esc(s)
  s = tostring(s)
  s = s:gsub('\\', '\\\\')
  s = s:gsub('"', '\\"')
  s = s:gsub('\n', '\\n')
  s = s:gsub('\r', '\\r')
  s = s:gsub('\t', '\\t')
  return s
end

local function json_str(s)
  return '"' .. esc(s) .. '"'
end

local function json_num_or_null(v)
  if v == nil or type(v) ~= "number" then
    return "null"
  end
  if v == math.floor(v) then
    return string.format("%d", v)
  end
  return tostring(v)
end

local function metric_json(m)
  local parts = {
    '"subject":' .. json_str(m.subject),
    '"metric":' .. json_str(m.metric),
    '"value":' .. json_num_or_null(m.value),
    '"unit":' .. json_str(m.unit),
  }
  if m.error then
    table.insert(parts, '"error":' .. json_str(m.error))
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

local function record_json(rec)
  local metrics_parts = {}
  for _, m in ipairs(rec.metrics) do
    table.insert(metrics_parts, metric_json(m))
  end
  local parts = {
    '"v":' .. tostring(rec.v),
    '"timeline_id":' .. json_str(rec.timeline_id),
    '"timeline_start_abs_tick":' .. json_num_or_null(rec.timeline_start_abs_tick),
    '"abs_tick":' .. json_num_or_null(rec.abs_tick),
    '"cur_year":' .. json_num_or_null(rec.cur_year),
    '"cur_year_tick":' .. json_num_or_null(rec.cur_year_tick),
    '"wall_utc":' .. json_str(rec.wall_utc),
    '"sampler_version":' .. json_str(rec.sampler_version),
    '"metrics":[' .. table.concat(metrics_parts, ",") .. "]",
  }
  return "{" .. table.concat(parts, ",") .. "}"
end

-- ----------------------------------------------------------------------------
-- Metric bookkeeping. `ok=false` always drops `value` (absent -> encoded as
-- `null` above) and always carries `err` as the `error` string.

local function add_metric(list, subject, metric, ok, value, unit, err)
  if ok then
    table.insert(list, {subject = subject, metric = metric, value = value, unit = unit})
  else
    table.insert(list, {subject = subject, metric = metric, value = nil, unit = unit,
      error = tostring(err or "unknown error")})
  end
end

-- Returns (true, number, nil) only if fn() ran clean AND returned a real
-- Lua number. A clean-but-non-number result is treated the same as a raised
-- error (docs/TRAPS.md's assert-don't-trust rule): never guessed as zero.
local function checked_number_field(fn)
  local ok, v = pcall(fn)
  if ok and type(v) == "number" then
    return true, v, nil
  elseif ok then
    return false, nil, "field did not resolve to a number (got " .. type(v) .. ")"
  else
    return false, nil, tostring(v)
  end
end

-- ----------------------------------------------------------------------------
-- is_fort_owned, copied verbatim from df-overseer-stocks.lua -- see this
-- file's header.

local function is_on_hidden_tile(item)
  local ok_pos, x, y, z = pcall(dfhack.items.getPosition, item)
  if not ok_pos or not x then
    return false
  end
  local ok_vis, visible = pcall(dfhack.maps.isTileVisible, x, y, z)
  if not ok_vis then
    return false
  end
  return not visible
end

local function is_fort_owned(item)
  local f = item.flags
  return not f.trader and not f.garbage_collect and not f.removed
    and not is_on_hidden_tile(item)
end

local function item_units(item)
  local ok, stack_size = pcall(function() return item.stack_size end)
  if ok and type(stack_size) == "number" and stack_size > 0 then
    return stack_size
  end
  return 1
end

-- ----------------------------------------------------------------------------
-- fort/population, fort/deaths

local function get_fort_metrics(list, ok_cit, citizens, cit_err)
  if ok_cit and citizens then
    add_metric(list, "fort", "population", true, #citizens, "citizens")
  else
    add_metric(list, "fort", "population", false, nil, "citizens", cit_err)
  end

  -- No persistent death counter exists anywhere on this install (checked:
  -- no eventful-independent tally, no ledger). Best available signal:
  -- units still resident in world.units.all that are both dead and this
  -- fort's own civ. This UNDERCOUNTS once a corpse fully decays out of the
  -- vector -- a real, named gap, not hidden. Uniboslan has had zero deaths
  -- as of this stream, so this path is implemented but not yet exercised
  -- against a real death; say so plainly in the write-up rather than
  -- claiming it as measured.
  local ok_dead, dead_or_err = pcall(function()
    local n = 0
    local vec = df.global.world.units.all
    for i = 0, #vec - 1 do
      local u = vec[i]
      local ok_d, is_dead = pcall(dfhack.units.isDead, u)
      local ok_o, is_own = pcall(dfhack.units.isOwnCiv, u)
      if ok_d and is_dead and ok_o and is_own then
        n = n + 1
      end
    end
    return n
  end)
  add_metric(list, "fort", "deaths", ok_dead, ok_dead and dead_or_err or nil,
    "citizens", (not ok_dead) and dead_or_err or nil)
end

-- ----------------------------------------------------------------------------
-- unit:<id>/thirst_timer, hunger_timer, sleepiness_timer
-- counters2, not counters (docs/TRAPS.md, 2026-09-18 audit).

local function get_unit_timer_metrics(list, citizens)
  for _, u in ipairs(citizens) do
    local ok_id, uid = pcall(function() return u.id end)
    if ok_id and uid ~= nil then
      local subj = "unit:" .. tostring(uid)
      local ok_t, t, err_t = checked_number_field(function() return u.counters2.thirst_timer end)
      add_metric(list, subj, "thirst_timer", ok_t, t, "ticks", err_t)
      local ok_h, h, err_h = checked_number_field(function() return u.counters2.hunger_timer end)
      add_metric(list, subj, "hunger_timer", ok_h, h, "ticks", err_h)
      local ok_s, s, err_s = checked_number_field(function() return u.counters2.sleepiness_timer end)
      add_metric(list, subj, "sleepiness_timer", ok_s, s, "ticks", err_s)
    end
  end
end

-- ----------------------------------------------------------------------------
-- item:<TYPE>/stock -- the starter set from docs/TIMESERIES.md: DRINK,
-- FOOD, SEEDS, PLANT, WOOD, BOULDER, BARREL, BUCKET. A type that is not a
-- real df.global.world.items.other key on this install reports null+error
-- for that one subject, never a silent 0 and never skipped without a trace.

local ITEM_TYPES = {"DRINK", "FOOD", "SEEDS", "PLANT", "WOOD", "BOULDER", "BARREL", "BUCKET"}

local function get_item_stock_metrics(list)
  for _, type_name in ipairs(ITEM_TYPES) do
    local subj = "item:" .. type_name
    local ok_vec, vec = pcall(function() return df.global.world.items.other[type_name] end)
    if ok_vec and vec then
      local ok_sum, total_or_err = pcall(function()
        local n = 0
        for i = 0, #vec - 1 do
          local item = vec[i]
          if is_fort_owned(item) then
            n = n + item_units(item)
          end
        end
        return n
      end)
      add_metric(list, subj, "stock", ok_sum, ok_sum and total_or_err or nil,
        "units", (not ok_sum) and total_or_err or nil)
    else
      add_metric(list, subj, "stock", false, nil, "units",
        "unknown item type: " .. tostring(type_name)
          .. " (not a df.global.world.items.other key on this install)")
    end
  end
end

-- ----------------------------------------------------------------------------
-- job:<JobType>/queue_depth -- df.global.world.jobs.list is a linked list
-- (.next/.item), not df.global.job_list (docs/TRAPS.md). Bounded by the
-- number of live jobs, never map tiles.

local function get_job_queue_metrics(list)
  local ok_walk, counts_or_err = pcall(function()
    local counts = {}
    local node = df.global.world.jobs.list
    local guard = 0
    while node do
      guard = guard + 1
      if guard > 200000 then
        error("job list walk exceeded safety bound, possible cycle")
      end
      local job = node.item
      if job then
        local ok_jt, jt_name = pcall(function() return df.job_type[job.job_type] end)
        local name = (ok_jt and jt_name) or ("job_type_" .. tostring(job.job_type))
        counts[name] = (counts[name] or 0) + 1
      end
      node = node.next
    end
    return counts
  end)
  if ok_walk then
    for job_type, n in pairs(counts_or_err) do
      add_metric(list, "job:" .. job_type, "queue_depth", true, n, "jobs")
    end
  else
    add_metric(list, "job:unknown", "queue_depth", false, nil, "jobs", counts_or_err)
  end
end

-- ----------------------------------------------------------------------------
-- Timeline minting and state. A new id is minted once per map load, from
-- dfhack-config/init/onMapLoad.init calling `mint` directly (not from the
-- repeat, which only calls `sample`). State is kept in a tiny two-line text
-- file rather than a Lua global, because reqscript's module cache
-- (docs/TRAPS.md) persists for the life of the DFHack PROCESS, which can
-- outlive a single map load (unload one fort, load another) -- a file
-- written fresh by onMapLoad.init is the thing that is actually guaranteed
-- to be per-load.

local function generate_timeline_id()
  local seed = (os.time() or 0) * 1000 + math.floor(((os.clock() or 0) * 1000) % 1000)
  math.randomseed(seed)
  local suffix = math.random(0, 999999)
  return string.format("tl-%s-%06d", os.date("!%Y%m%dT%H%M%SZ"), suffix)
end

local function read_current_tick()
  return pcall(function()
    local y = df.global.cur_year
    local t = df.global.cur_year_tick
    return y, t, y * 403200 + t
  end)
end

function mint_timeline()
  local ok_tick, cur_year, cur_year_tick, abs_tick = read_current_tick()
  local start_tick = ok_tick and abs_tick or nil
  local id = generate_timeline_id()
  local f, ferr = io.open(STATE_FILE, "w")
  if not f then
    print("df-overseer-sampler ERROR: could not open " .. STATE_FILE
      .. " for write: " .. tostring(ferr)
      .. " (does " .. SAMPLE_DIR .. " exist?)")
    return nil, nil
  end
  f:write(id .. "\n")
  f:write(tostring(start_tick or "") .. "\n")
  f:close()
  print("df-overseer-sampler: minted timeline " .. id
    .. " timeline_start_abs_tick=" .. tostring(start_tick))
  return id, start_tick
end

local function read_current_timeline()
  local f = io.open(STATE_FILE, "r")
  if not f then
    return nil, nil, "no timeline state file at " .. STATE_FILE .. "; mint has not run this load"
  end
  local id = f:read("*l")
  local start_str = f:read("*l")
  f:close()
  if not id or id == "" then
    return nil, nil, "timeline state file is empty or malformed"
  end
  return id, tonumber(start_str), nil
end

-- ----------------------------------------------------------------------------
-- sample(): the repeat's own command. One atomic append, one line, one
-- sample event, matching docs/TIMESERIES.md's "one line per sample event,
-- not per metric" rule so a torn final line is detectable as exactly one
-- bad line.

function sample()
  local timeline_id, timeline_start_abs_tick, tl_err = read_current_timeline()
  if not timeline_id then
    -- A `sample` firing before any `mint` this load is a real gap (the
    -- onMapLoad wiring failed to run first), not something to patch over
    -- silently -- logged loudly, then self-healed by minting now so the
    -- run does not lose the whole interval.
    print("df-overseer-sampler WARNING: " .. tostring(tl_err) .. "; minting now")
    timeline_id, timeline_start_abs_tick = mint_timeline()
    if not timeline_id then
      print("df-overseer-sampler ERROR: mint failed too; dropping this sample")
      return
    end
  end

  local ok_tick, cur_year, cur_year_tick, abs_tick = read_current_tick()
  if not ok_tick then
    print("df-overseer-sampler ERROR: could not read current tick, dropping this sample: "
      .. tostring(cur_year))
    return
  end

  local metrics = {}
  local ok_cit, citizens = pcall(dfhack.units.getCitizens, true)
  get_fort_metrics(metrics, ok_cit, citizens, ok_cit and nil or tostring(citizens))
  get_unit_timer_metrics(metrics, (ok_cit and citizens) or {})
  get_item_stock_metrics(metrics)
  get_job_queue_metrics(metrics)

  local record = {
    v = 1,
    timeline_id = timeline_id,
    timeline_start_abs_tick = timeline_start_abs_tick,
    abs_tick = abs_tick,
    cur_year = cur_year,
    cur_year_tick = cur_year_tick,
    wall_utc = os.date("!%Y-%m-%dT%H:%M:%SZ"),
    sampler_version = SAMPLER_VERSION,
    metrics = metrics,
  }
  local line = record_json(record)

  local sample_path = SAMPLE_DIR .. "/" .. timeline_id .. ".jsonl"
  local f, ferr = io.open(sample_path, "a")
  if not f then
    print("df-overseer-sampler ERROR: could not open " .. sample_path
      .. " for append: " .. tostring(ferr))
    return
  end
  f:write(line .. "\n")
  f:close()
  print("df-overseer-sampler: sample written to " .. sample_path
    .. " abs_tick=" .. tostring(abs_tick) .. " metrics=" .. tostring(#metrics))
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "mint" then
  mint_timeline()
elseif cmd == "sample" then
  -- Outermost guard: an uncaught error here must never be able to take the
  -- `repeat` registration down with it.
  local ok, err = pcall(sample)
  if not ok then
    print("df-overseer-sampler ERROR in sample(): " .. tostring(err))
  end
else
  print("usage: df-overseer-sampler <mint|sample>")
end
