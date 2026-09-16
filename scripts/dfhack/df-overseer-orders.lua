-- df-overseer-orders.lua
--@module = true
--
-- handoffs/2026-09-17-water-and-industry-tools.md item 4: manager work
-- orders, the only route this project has to stone blocks, mechanisms,
-- barrels and brew drink -- none of which any existing tool can produce.
-- Wraps `workorder.lua`'s own `create_orders()`/`preprocess_orders()`/
-- `fillin_defaults()` (memory/dfhack-environment.md: "the only route to
-- manager work orders, since `stocks` and `workflow` are both
-- unavailable"), reqscript'd the same way df-overseer-farm.lua reqscripts
-- df-overseer-stocks.lua.
--
-- CALL SHAPE, verified from THIS install's own source this session, not
-- guessed or taken from the wiki: `workorder.lua`'s own CLI default action
-- (`default_action`, its registered entry point for `workorder JOB_TYPE
-- AMOUNT`) does exactly `orders = {{job = jobtype, amount_total =
-- tonumber(n)}}` then `preprocess_orders(orders)` (fills in `id` as a
-- negative index when absent, normalises `amount_total`) then
-- `fillin_defaults(orders)` (metatable default `frequency = 'OneTime'`)
-- then `create_orders(orders)`. `create_order` below reproduces that exact
-- three-call sequence rather than hand-building a `df.manager_order`
-- struct, so this project's tool can never drift from what the CLI itself
-- does when DFHack updates that file.
--
-- JOB TYPES, each live-verified this session by reading the real
-- df.job_type enum on this install (bounds via `_first_item`/
-- `_last_item`, per docs/TRAPS.md's enum-iteration trap -- `pairs()` alone
-- only sees the sentinels):
--   blocks       -> job_type 80  ConstructBlocks
--   mechanisms   -> job_type 139 ConstructMechanisms
--   barrels      -> job_type 125 MakeBarrel
--   brew_drink   -> job_type 209 CustomReaction, reaction_name
--                   BREW_DRINK_FROM_PLANT (live-confirmed present in
--                   df.global.world.raws.reactions.reactions' own `code`
--                   field -- no df.job_type named "Brew*" exists on this
--                   build; brewing is a reaction, not its own job type,
--                   matching create_orders' own `it["reaction"]` handling).
--
-- MANAGER PREREQUISITE, checked live this session per the handoff's own
-- instruction, and the answer is a genuine open question, not a clean
-- yes/no: `create_orders` itself has NO code-level check for an appointed
-- Manager at all -- reading the function found nothing gating order
-- creation on one. But `dfhack.units.getNoblePositions` over every active
-- unit on this fort found ZERO citizens currently holding the MANAGER
-- noble position (a scan of `df.global.world.entities.all` for an entity
-- with a MANAGER position DID find one filled assignment, but its
-- histfig's own `unit_id` did not resolve to a live unit via
-- `dfhack.units.getUnitByHistfigId` -- that entity is very likely an
-- unrelated site elsewhere in the world, not Uniboslan's own site
-- government; the unit-scoped API is the more trustworthy signal for "who
-- holds this position on THIS fort" and it found nobody). So: **this tool
-- CAN write an order into `world.manager_orders.all` regardless of whether
-- a Manager is appointed** (nothing in the DFHack API stops it), but
-- **whether DF's own engine then validates/assigns that order into a real
-- workshop job without a Manager appointed is NOT verified** -- this
-- project has no way to advance time to find out without unpausing the
-- fort, out of scope this stream. `list_orders`/`create_order` both report
-- `manager_appointed` so a caller can see this precondition rather than
-- assume it. Appointing one is a nobles-screen action this project has no
-- tool for yet.
--
-- WORKSHOP PREREQUISITE: an order can only ever be fulfilled once a
-- matching workshop exists (a ConstructBlocks order needs a Mason's
-- Workshop; brew_drink needs a Still) -- `create_order` reports
-- `workshop_exists` (a live count of built workshops of the right
-- subtype) as informational, but does NOT refuse to create an order when
-- none exists yet: an infinite-amount order queued ahead of the workshop
-- being built is a normal, valid vanilla workflow, not a mistake.
--
-- DRY_RUN, same contract as every other write in this project: defaults to
-- true. A dry run resolves and validates the job/amount and reports
-- exactly what would be queued, without ever calling create_orders. Only
-- an explicit false performs the real mutation -- UNTESTED live (mutation
-- forbidden this session); `preprocess_orders`/`fillin_defaults` were
-- confirmed live to load and expose the right function types via
-- reqscript, `create_orders` itself was never called.
--
-- CANCEL: `world.manager_orders.all:erase(idx)` plus `order:delete()`,
-- inferred by convention from workorder.lua's own with_onerror cleanup
-- path (which calls `order:delete()` to roll back a not-yet-inserted
-- order) and research/2026-09-16-food-and-drink-logistics.md §4's own
-- finding that `:erase(idx)` is a supported vector operation on this
-- structure -- NOT independently proven by a real removal this session.
--
-- Usage: ./dfhack-run df-overseer-orders list
-- Usage: ./dfhack-run df-overseer-orders create JOB AMOUNT [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-orders cancel ID [DRY_RUN]

local json = require('json')
local workorder_mod = reqscript('workorder')

-- Structured for a later job name to be a new table entry, matching
-- df-overseer-zone.lua's KIND_INFO/df-overseer-workshop.lua's KIND_INFO
-- extensibility precedent.
local JOB_INFO = {
  blocks = {job = "ConstructBlocks", workshop_subtype = "Masons"},
  mechanisms = {job = "ConstructMechanisms", workshop_subtype = "Mechanics"},
  barrels = {job = "MakeBarrel", workshop_subtype = "Carpenters"},
  brew_drink = {job = "CustomReaction", reaction = "BREW_DRINK_FROM_PLANT",
    workshop_subtype = "Still"},
}

-- See header: unit-scoped, live-verified this session to find nobody. Not
-- cached -- computed fresh on every call, since a manager could be
-- appointed between calls.
local function manager_appointed()
  for _, unit in ipairs(df.global.world.units.active) do
    local ok, positions = pcall(dfhack.units.getNoblePositions, unit)
    if ok and positions then
      for _, p in ipairs(positions) do
        local ok_code, code = pcall(function() return p.position.code end)
        if ok_code and code == 'MANAGER' then
          return true
        end
      end
    end
  end
  return false
end

-- Live count of built workshops whose subtype matches the job's own
-- workshop_subtype (a Workshop building of the right kind, however built
-- -- not limited to ones this project's own workshop.build created).
local function workshop_exists_count(subtype_name)
  local subtype = df.workshop_type[subtype_name]
  if not subtype then
    return nil
  end
  local n = 0
  for _, bld in ipairs(df.global.world.buildings.all) do
    local ok_type, btype = pcall(function() return bld:getType() end)
    if ok_type and btype == df.building_type.Workshop then
      local ok_sub, sub = pcall(function() return bld.type end)
      if ok_sub and sub == subtype then
        n = n + 1
      end
    end
  end
  return n
end

local function resolve_job_name(id_or_reaction)
  local ok, name = pcall(function() return df.job_type[id_or_reaction] end)
  return ok and name or nil
end

function list_orders()
  local out = {}
  local vec = df.global.world.manager_orders.all
  for i = 0, #vec - 1 do
    local order = vec[i]
    local ok_job, job_type = pcall(function() return order.job_type end)
    local job_name = ok_job and resolve_job_name(job_type) or nil
    local ok_reaction, reaction = pcall(function() return order.reaction_name end)
    table.insert(out, {
      id = order.id,
      queue_position = i + 1,
      job = job_name,
      reaction = (ok_reaction and reaction ~= "") and reaction or nil,
      amount_left = order.amount_left,
      amount_total = order.amount_total,
    })
  end
  return {
    orders = out,
    manager_appointed = manager_appointed(),
  }
end

local function truthy_dry_run(v)
  if v == nil then
    return true
  end
  local s = tostring(v):lower()
  return not (s == "false" or s == "0" or s == "no")
end

-- DRY_RUN defaults to true. See header for the exact call shape this
-- mirrors and what is/isn't verified live.
function create_order(job_name, amount, dry_run)
  local info = JOB_INFO[tostring(job_name):lower()]
  if not info then
    local known = {}
    for k in pairs(JOB_INFO) do table.insert(known, k) end
    table.sort(known)
    return nil, "unknown job: " .. tostring(job_name)
      .. " (expected one of: " .. table.concat(known, ", ") .. ")"
  end
  amount = tonumber(amount)
  if not amount or amount < 0 then
    return nil, "AMOUNT must be a non-negative integer (0 = infinite)"
  end
  local dry = truthy_dry_run(dry_run)

  local base = {
    dry_run = dry,
    job = job_name,
    amount = amount,
    manager_appointed = manager_appointed(),
    workshop_exists = workshop_exists_count(info.workshop_subtype),
  }

  if dry then
    base.would_queue = {job = info.job, reaction = info.reaction, amount_total = amount}
    return base
  end

  -- Real mutation. Reproduces workorder.lua's own default_action call
  -- sequence exactly -- see header. UNTESTED live (mutation forbidden this
  -- session).
  local order = {job = info.job, amount_total = amount}
  if info.reaction then
    order.reaction = info.reaction
  end
  local ok, orders_or_err = pcall(workorder_mod.preprocess_orders, {order})
  if not ok then
    base.create_ok = false
    base.create_error = tostring(orders_or_err)
    return base
  end
  local orders = orders_or_err
  pcall(workorder_mod.fillin_defaults, orders)
  local ok_create, create_err = pcall(workorder_mod.create_orders, orders)
  base.create_ok = ok_create
  base.create_error = (not ok_create) and tostring(create_err) or nil
  return base
end

-- DRY_RUN defaults to true. See header for the erase+delete mechanism and
-- why it is inferred by convention rather than independently proven.
function cancel_order(id, dry_run)
  id = tonumber(id)
  if not id then
    return nil, "ID must be a number"
  end
  local dry = truthy_dry_run(dry_run)

  local vec = df.global.world.manager_orders.all
  local idx, found = nil, nil
  for i = 0, #vec - 1 do
    if vec[i].id == id then
      idx = i
      found = vec[i]
      break
    end
  end
  if not found then
    return nil, "no manager order with id " .. tostring(id)
  end

  if dry then
    local ok_job, job_type = pcall(function() return found.job_type end)
    return {
      dry_run = true,
      id = id,
      job = ok_job and resolve_job_name(job_type) or nil,
      amount_left = found.amount_left,
    }
  end

  -- Real mutation. UNTESTED live -- see header.
  local ok_erase = pcall(function() vec:erase(idx) end)
  local ok_delete = pcall(function() found:delete() end)
  return {
    dry_run = false,
    id = id,
    erase_ok = ok_erase,
    delete_ok = ok_delete,
  }
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "list" then
  print(json.encode(list_orders()))
elseif cmd == "create" then
  local job, amount, dry_run = args[2], args[3], args[4]
  if not (job and amount) then
    print("usage: df-overseer-orders create JOB AMOUNT [DRY_RUN]")
  else
    local result, err = create_order(job, amount, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "cancel" then
  local id, dry_run = args[2], args[3]
  if not id then
    print("usage: df-overseer-orders cancel ID [DRY_RUN]")
  else
    local result, err = cancel_order(id, dry_run)
    print(json.encode(err and {error = err} or result))
  end
else
  print("usage: df-overseer-orders list")
  print("usage: df-overseer-orders create JOB AMOUNT [DRY_RUN]")
  print("usage: df-overseer-orders cancel ID [DRY_RUN]")
end
