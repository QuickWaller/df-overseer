-- A minimal fake DFHack world for df-overseer-orders.lua's generalised
-- create/reorder/recheck/check-duplicate, loaded by
-- tests/test_orders_conditions_lua_logic.py, which runs the REAL
-- scripts/dfhack/df-overseer-orders.lua against it in lupa.
--
-- handoffs/2026-10-01-orders-conditions.md: this proves the OFFLINE logic
-- this stream actually wrote -- job/reaction resolution, argument parsing
-- and validation (refusing a malformed argument with a named reason, on
-- both the dry-run and the real-mutation path), the reorder/recheck vector
-- primitives, and that a real create reads the new order back from
-- `world.manager_orders.all` rather than echoing the request.
--
-- WHAT THIS STUB CANNOT PROVE, stated plainly (per the handoff's own
-- instruction):
--   - The real `workorder.lua`'s own `qerror` message TEXT: WORKORDER.
--     create_orders below rejects an invalid job type and an invalid
--     material_category (the two cases this stream's own code cannot
--     already catch before reaching it) but is this repo's own
--     approximation of wo.lua:194-441, not the genuine DFHack script.
--   - `job_material_category`'s real flag names. DFHack does not ship
--     that bitfield's definition as source at all (see the .lua file's
--     own header) -- MATERIAL_CATEGORY_FLAGS below is a representative,
--     invented set (stone/wood/metal/gem/bone), not the true list.
--   - Whether DF's own (closed) engine ever dispatches a created order
--     into a real workshop job, with or without a Manager appointed, or
--     whether `orders recheck`-equivalent bit-clearing actually causes a
--     re-evaluation. Every one of those is a live-fort question, not
--     something a fake world can settle.

dfhack_flags = {module = true}

local function enum(names)
  local e = {NONE = -1, [-1] = "NONE"}
  for i, n in ipairs(names) do e[n] = i - 1; e[i - 1] = n end
  return e
end

-- A 0-indexed, fixed-length vector the way DFHack exposes a read vector.
local function vec(list)
  local v = {}
  for i, x in ipairs(list) do v[i - 1] = x end
  return setmetatable(v, {__len = function() return #list end})
end

-- A mutable 0-indexed vector supporting the two primitives this file's
-- cancel/reorder/create code actually calls: :insert(pos_or_'#', item) and
-- :erase(idx).
local function mutable_vec(list)
  local items = list or {}
  local v = {_items = items}
  local methods = {
    insert = function(_, pos, item)
      if pos == '#' then
        table.insert(items, item)
      else
        table.insert(items, pos + 1, item)
      end
    end,
    erase = function(_, idx)
      table.remove(items, idx + 1)
    end,
  }
  return setmetatable(v, {
    __len = function() return #items end,
    __index = function(_, k)
      if type(k) == "number" then return items[k + 1] end
      return methods[k]
    end,
  })
end

package.loaded['json'] = {encode = function() return "" end}
_G.require = function(n) return package.loaded[n] end

MATERIAL_CATEGORY_FLAGS = {"stone", "wood", "metal", "gem", "bone"}
BUILDINGS = {}
REACTIONS = {}
BAD_MATERIALS = {["BAD:MATERIAL"] = true, ["NOPE"] = true}

df = {
  job_type = enum({"ConstructBlocks", "MakeBucket", "ConstructBed", "CustomReaction"}),
  item_type = enum({"BARREL", "DRINK", "BOULDER"}),
  logic_condition_type = enum({"AtLeast", "AtMost", "GreaterThan", "LessThan", "Exactly", "Not"}),
  workquota_order_condition_type = enum({"Activated", "Completed"}),
  workquota_frequency_type = enum({"OneTime", "Daily", "Monthly", "Seasonally", "Yearly"}),
  building = {find = function(id) return BUILDINGS[id] end},
  manager_order = {
    new = function()
      local mc = {}
      for _, k in ipairs(MATERIAL_CATEGORY_FLAGS) do mc[k] = false end
      return {material_category = mc, delete = function() end}
    end,
  },
  global = {
    world = {
      units = {active = {}},
      manager_orders = {
        all = mutable_vec({}),
        manager_order_next_id = 0,
      },
      raws = {reactions = {reactions = vec(REACTIONS)}},
    },
  },
}

dfhack = {
  matinfo = {
    find = function(s)
      if s == nil or s == "" or BAD_MATERIALS[s] then return nil end
      return {name = s, type = 0, index = (s == "INORGANIC") and -1 or 1}
    end,
    decode = function(mt, mi)
      if mt == nil or mt < 0 then return nil end
      return {toString = function() return "material(" .. tostring(mt) .. "," .. tostring(mi) .. ")" end}
    end,
  },
  units = {getNoblePositions = function() return {} end},
}

function add_building(id) BUILDINGS[id] = {id = id} end
function add_reaction(code)
  table.insert(REACTIONS, {code = code})
  df.global.world.raws.reactions.reactions = vec(REACTIONS)
end

-- Seeds an existing queue entry directly (for reorder/recheck/check-duplicate/
-- order_conditions-referencing-an-existing-order tests), bypassing
-- create_order entirely -- this is test setup, not something the tool
-- itself does.
function add_order(id, job, opts)
  opts = opts or {}
  local mc = {}
  for _, k in ipairs(MATERIAL_CATEGORY_FLAGS) do mc[k] = false end
  local order = {
    id = id,
    job_type = df.job_type[job],
    reaction_name = opts.reaction or "",
    amount_left = opts.amount_left or 1,
    amount_total = opts.amount_total or 1,
    frequency = df.workquota_frequency_type[opts.frequency or "OneTime"],
    status = {validated = opts.validated or false, active = opts.active or false},
    finished_year = -1,
    finished_year_tick = -1,
    max_workshops = opts.max_workshops or 0,
    workshop_id = opts.workshop_id or -1,
    material_category = mc,
    mat_type = opts.mat_type or -1,
    mat_index = opts.mat_index or -1,
    item_conditions = vec(opts.item_conditions or {}),
    order_conditions = vec({}),
  }
  df.global.world.manager_orders.all:insert('#', order)
  if id >= df.global.world.manager_orders.manager_order_next_id then
    df.global.world.manager_orders.manager_order_next_id = id + 1
  end
  return order
end

-- A faithful-enough approximation of wo.lua's own preprocess_orders/
-- fillin_defaults/create_orders (see this file's own header for exactly
-- what it does NOT prove). Rejects an invalid job type and an invalid
-- material_category the same way the real script does (by field name, via
-- `error()`, matching wo.lua's own `qerror` control flow closely enough for
-- create_order's pcall-and-report wrapper to be exercised for real).
local WORKORDER = {}

function WORKORDER.preprocess_orders(orders)
  if orders.job then orders = {orders} end
  for i, o in ipairs(orders) do
    if not o.id then o.id = -i end
    if o.amount_total == nil then o.amount_total = 0 end
  end
  return orders
end

function WORKORDER.fillin_defaults(orders)
  for _, o in ipairs(orders) do
    if not o.frequency then o.frequency = "OneTime" end
  end
end

function WORKORDER.create_orders(orders)
  for _, it in ipairs(orders) do
    -- The real workorder.lua prints this from its own env (wo.lua:437);
    -- modelled as an env lookup so a shadowed print is honoured.
    ;(rawget(WORKORDER, 'print') or print)("Queuing " .. tostring(it.job) .. " x" .. tostring(it.amount_total))
    local jt = df.job_type[it.job]
    if jt == nil then
      error("Invalid job type for manager order: " .. tostring(it.job))
    end

    local mc = {}
    for _, k in ipairs(MATERIAL_CATEGORY_FLAGS) do mc[k] = false end
    if it.material_category then
      local present = {}
      for _, k in ipairs(MATERIAL_CATEGORY_FLAGS) do present[k] = true end
      local bad = {}
      for _, n in ipairs(it.material_category) do
        if present[n] then mc[n] = true else bad[#bad + 1] = n end
      end
      if #bad > 0 then
        error("Invalid material_category value for manager order: " .. table.concat(bad, ", "))
      end
    end

    local item_conditions = {}
    for _, c in ipairs(it.item_conditions or {}) do
      table.insert(item_conditions, {
        compare_type = df.logic_condition_type[c.condition],
        compare_val = tonumber(c.value),
        item_type = (c.item_type and df.item_type[c.item_type]) or df.item_type.NONE,
        mat_type = -1,
        mat_index = -1,
      })
    end
    local order_conditions = {}
    for _, c in ipairs(it.order_conditions or {}) do
      table.insert(order_conditions, {
        order_id = tonumber(c.order),
        condition = df.workquota_order_condition_type[c.condition],
      })
    end

    local mo = df.global.world.manager_orders
    local id = mo.manager_order_next_id
    mo.manager_order_next_id = id + 1

    local order = {
      id = id,
      job_type = jt,
      reaction_name = it.reaction or "",
      amount_left = it.amount_total,
      amount_total = it.amount_total,
      frequency = df.workquota_frequency_type[it.frequency or "OneTime"],
      status = {validated = false, active = false},
      finished_year = -1,
      finished_year_tick = -1,
      max_workshops = it.max_workshops or 0,
      workshop_id = it.workshop_id or -1,
      material_category = mc,
      mat_type = (it.material and dfhack.matinfo.find(it.material).type) or -1,
      mat_index = (it.material and dfhack.matinfo.find(it.material).index) or -1,
      item_conditions = vec(item_conditions),
      order_conditions = vec(order_conditions),
    }
    mo.all:insert('#', order)
  end
end

local STUCKJOBS = {
  find_jobs_by_type = function(job, reaction) return {} end,
}

function reqscript(name)
  if name == 'workorder' then return WORKORDER end
  if name == 'df-overseer-stuckjobs' then return STUCKJOBS end
  error("reqscript: unknown module " .. tostring(name))
end
