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
-- 2026-10-01 (handoffs/2026-10-01-orders-conditions.md, offline build, no
-- live access this stream): GENERALISED over job type, and given frequency,
-- item/order conditions and a material-category class filter, per
-- research/2026-10-01-quartermaster-levers.md §1 (source-cited against
-- DFHack tag 53.16-r1). This is a BREAKING CHANGE from the prior
-- twelve-entry JOB_INFO table (blocks/mechanisms/barrels/brew_drink/bucket/
-- bed/door/table/chair/splint/crutch/soap): JOB is no longer a lookup into
-- a hand-maintained table (already flagged as a generalisability violation,
-- research/2026-09-30-policy-audit.md §1 row 2) -- see JOB below for the
-- new resolution rule. Any caller (or role prompt) still passing the old
-- short names (e.g. "blocks") must switch to the real job_type name
-- (e.g. "ConstructBlocks") -- this file no longer recognises the alias.
--
-- JOB, resolved generically, never a per-job branch: first tried as a live
-- `df.job_type` name (e.g. "ConstructBlocks", "MakeBucket", "ConstructBed");
-- if that fails, tried as a reaction code against
-- `world.raws.reactions.reactions`' own `code` field (e.g.
-- "BREW_DRINK_FROM_PLANT", "MAKE_SOAP_FROM_TALLOW"), which resolves to
-- `job = "CustomReaction", reaction = CODE` -- exactly workorder.lua's own
-- `it["reaction"]` handling (wo.lua:208-210). A bare "CustomReaction" with
-- no matching reaction code is refused: it is a real job_type name, so the
-- first branch matches it, but wo.lua's own CustomReaction jobs are
-- meaningless without a reaction_name, so this is caught explicitly rather
-- than silently queuing an order that can never be fulfilled. The
-- workshop-subtype/`workshop_exists` informational count this tool used to
-- report is REMOVED: it depended entirely on the same per-job hardcoded
-- table this stream removes (df.job_type carries no live-queryable
-- workshop-subtype attribute at all, confirmed against df.job.xml's own
-- `job_type` enum-attr list at the pinned tag -- caption/type/labor/item/
-- possible_item/material/skill*/is_designation, nothing workshop-shaped),
-- so it could not be generalised rather than dropped.
--
-- Optional arguments (all flat strings/numbers on the positional CLI,
-- "" meaning "omit", per dfmcp/tools.py's own arg_defaults mechanism):
--   FREQUENCY          -- a `df.workquota_frequency_type` name (OneTime,
--                         Daily, Monthly, Seasonally, Yearly -- validated
--                         live against the real enum, never a hardcoded
--                         list); omitted, wo.lua's own fillin_defaults
--                         defaults to OneTime, unchanged from before.
--   MATERIAL           -- anything `dfhack.matinfo.find` accepts, e.g.
--                         "INORGANIC:GRANITE" (wo.lua:236-243).
--   MATERIAL_CATEGORY  -- a comma-separated list of `job_material_category`
--                         flag names, e.g. "stone,wood" (the class filter,
--                         matching `DEFAULT_CLASS_CATEGORIES` in
--                         df-overseer-building.lua as a WORKED EXAMPLE, not
--                         an automatic default this tool applies itself --
--                         which class a given job wants varies per job, and
--                         hardcoding "these jobs get stone+wood" would be
--                         exactly the per-job branch this project's
--                         generalisability rule forbids. This tool never
--                         hardcodes the flag NAMES either: `validate_
--                         material_category` reads them live off a
--                         throwaway `df.manager_order`'s own
--                         `material_category` bitfield, since DFHack does
--                         not expose `job_material_category`'s flag list as
--                         source in df-structures at the pinned tag (a repo
--                         search across every root .xml file at commit
--                         1dd01aad64219afa0578f1328cf15bd0c6006d5a found the
--                         type only ever REFERENCED, at df.workquota.xml,
--                         never DEFINED -- it is generated at DF's own
--                         build time, not shipped as source DFHack mirrors).
--   WORKSHOP_ID        -- pins the order to one existing building id
--                         (wo.lua:286-292), validated against `df.building.
--                         find`.
--   MAX_WORKSHOPS      -- caps concurrent workshops pulling from this order,
--                         0 = unlimited (wo.lua:294-296).
--   ITEM_CONDITIONS    -- "COND:VALUE[:ITEM_TYPE[:MATERIAL]]", multiple
--                         conditions separated by ";". COND is a
--                         `df.logic_condition_type` name (AtLeast, AtMost,
--                         GreaterThan, LessThan, Exactly, Not -- validated
--                         live, per wo.lua:298-378/df.workquota.xml). A
--                         MATERIAL value containing its own ":" (e.g.
--                         "INORGANIC:GRANITE") must be the LAST field of its
--                         condition -- parsing rejoins every field from
--                         position 4 onward rather than trying to
--                         disambiguate a nested ":". Example: "make barrels
--                         until at least 5 exist" is
--                         "AtLeast:5:BARREL".
--   ORDER_CONDITIONS   -- "ORDER_ID:STATE", multiple separated by ";".
--                         STATE is Activated or Completed
--                         (`df.workquota_order_condition_type`, wo.lua:
--                         380-397). ORDER_ID must already exist in the live
--                         queue: this tool creates one order per call, not
--                         a batch, so (unlike wo.lua's own batch id_mapping)
--                         it cannot chain to a sibling order created in the
--                         same call -- refused by name if the id is not
--                         found in `world.manager_orders.all`, not silently
--                         accepted and left to fail inside create_orders.
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
-- workshop job without a Manager appointed is NOT verified** (register
-- 2026-09-30/2026-10-01: the user reports manager work orders DO now
-- dispatch on the live fort, but that is a live observation, not something
-- this offline stream re-confirmed). `list_orders`/`create_order` both
-- report `manager_appointed` so a caller can see this precondition rather
-- than assume it.
--
-- DRY_RUN, same contract as every other write in this project: defaults to
-- true. A dry run resolves and validates every argument (job, amount,
-- frequency, material, material_category, item/order conditions) and
-- reports exactly what would be queued, without ever calling create_orders
-- -- a malformed argument is refused (named reason) on the dry-run path
-- too, not only on a real write. Only an explicit false performs the real
-- mutation -- UNTESTED live this stream (mutation forbidden, no live
-- access per the handoff).
--
-- CANCEL: `world.manager_orders.all:erase(idx)` plus `order:delete()`,
-- inferred by convention from workorder.lua's own with_onerror cleanup
-- path (which calls `order:delete()` to roll back a not-yet-inserted
-- order) and research/2026-09-16-food-and-drink-logistics.md §4's own
-- finding that `:erase(idx)` is a supported vector operation on this
-- structure -- NOT independently proven by a real removal this session.
--
-- REORDER: research/2026-10-01-quartermaster-levers.md §1 found no native
-- "move order to position N" at all -- `create_orders` only ever appends
-- (wo.lua:440), and the only native reordering, the `orders` plugin's
-- `sort` command (orders.cpp:1012-1034), applies one fixed rule (workshop-
-- pinned first, then one-time before repeating), not an arbitrary move.
-- `reorder_order` below does the same direct erase+insert splice
-- `cancel_order` already uses for deletion, moved to a caller-chosen
-- 1-based POSITION instead of removed outright.
--
-- RECHECK: research/2026-10-01-quartermaster-levers.md §1 first proposed
-- this as "wraps native `orders recheck`", but reading orders.cpp directly
-- (orders_recheck_command, orders.cpp:1040-1051) found that command takes
-- NO id argument at all -- it walks the WHOLE queue and clears
-- validated/active on every order that both has item_conditions and is
-- currently active. There is no native per-order recheck to wrap. This
-- tool instead reproduces that exact same gate (item_conditions present,
-- status.active true) scoped to one requested ID, writing the two bits
-- directly -- the same class of primitive `cancel_order`'s vector splice
-- already uses, and no more "armok" than the native command clearing the
-- same two bits fort-wide (manager_order_status, df.workquota.xml:59-62,
-- carries no armok tag of its own; the gate purely mirrors player-visible
-- Manager-screen behaviour).
--
-- CHECK_DUPLICATE, added handoffs/2026-09-23-order-job-attribution-and-
-- checks.md item 4: a duplicate-production check in code, not left to a
-- model's judgement. Decision, stated per that handoff's own instruction:
-- this lives in a LUA TOOL (here), not a native dfmcp tool and not dfqueue.
-- Reasoning: the two things it must scan (world.manager_orders.all and the
-- live job list) are both already server-side, DFHack-only data this file
-- and df-overseer-stuckjobs.lua already read directly; a native dfmcp tool
-- would just be an extra network round trip re-fetching the same two Lua
-- calls dfmcp already exposes as orders.list/stuckjobs.find, and dfqueue has
-- no live-game coupling at all today (SQLite plus schema validation at write
-- time, decisions/DECISIONS.md 2026-09-15) -- giving it one just for this
-- check would be new architecture, not a cheap addition. Both the Overseer
-- (before it writes an order or a direct job) and the queue's own validation
-- path (by calling this MCP tool before a `work_order` proposal is written
-- or ruled on, the same way any other precondition is read today) can call
-- it as an ordinary read tool. 2026-10-01: now resolves JOB the same
-- generic way create_order does (see above), not JOB_INFO.
--
-- Usage: ./dfhack-run df-overseer-orders list
-- Usage: ./dfhack-run df-overseer-orders create JOB AMOUNT [FREQUENCY]
--          [MATERIAL] [MATERIAL_CATEGORY] [WORKSHOP_ID] [MAX_WORKSHOPS]
--          [ITEM_CONDITIONS] [ORDER_CONDITIONS] [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-orders reorder ID POSITION [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-orders recheck ID [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-orders cancel ID [DRY_RUN]
-- Usage: ./dfhack-run df-overseer-orders check-duplicate JOB

local json = require('json')
local workorder_mod = reqscript('workorder')
local stuckjobs_mod = reqscript('df-overseer-stuckjobs')

-- MATERIAL POLICY, handoffs/2026-10-07-valid-manager-orders.md. A manager
-- order for an item job with no material (mat_type -1, mat_index -1, empty
-- material_category) is shown by the game as "Make unknown material ..." and
-- never produced anything on the live fort (evals/live/2026-10-07-manager-
-- orders/README.md). DFHack's own shipped order library
-- (hack/data/orders/*.json, read on the live install 2026-10-07: 228 orders
-- over 6 files) never issues one: every item job carries a material or a
-- material_category, and only reactions and raw-processing jobs carry none.
-- This table is that library, reduced to one policy per job type, as DATA
-- (a new job is one entry, no new code):
--   material = "INORGANIC"   default `material` (any stone; the library's own
--                            value for stone furniture, blocks, mechanisms)
--   category = {"wood"}      default `material_category` flag names
--   none = true              a job that takes no material (the library issues
--                            these bare); a reaction (CustomReaction) is
--                            always this
--   requires = true          the library carries several variants (a metal
--                            per order, leather/silk/cloth, glass colours),
--                            so no default is honest: the caller must pass
--                            MATERIAL or MATERIAL_CATEGORY
-- A job in none of these (not in the library) is neither defaulted nor
-- flagged: create still demands an explicit material, list stays silent.
-- tests/test_orders_library_parity.py checks every entry against the
-- library files (tests/fixtures/dfhack_orders/).
-- MakeBarrel is not in the library; it takes wood by analogy with its
-- library sibling MakeBucket (marked inferred, not library-derived).
ORDER_MATERIAL_POLICY = {
  ConstructArmorStand = {material = "INORGANIC"},
  ConstructBlocks = {material = "INORGANIC"},
  ConstructCabinet = {material = "INORGANIC"},
  ConstructChest = {material = "INORGANIC"},
  ConstructCoffin = {material = "INORGANIC"},
  ConstructDoor = {material = "INORGANIC"},
  ConstructFloodgate = {material = "INORGANIC"},
  ConstructGrate = {material = "INORGANIC"},
  ConstructHatchCover = {material = "INORGANIC"},
  ConstructMechanisms = {material = "INORGANIC"},
  ConstructSlab = {material = "INORGANIC"},
  ConstructStatue = {material = "INORGANIC"},
  ConstructTable = {material = "INORGANIC"},
  ConstructThrone = {material = "INORGANIC"},
  ConstructWeaponRack = {material = "INORGANIC"},
  MakeGoblet = {material = "INORGANIC"},
  ConstructBed = {category = {"wood"}},
  ConstructBin = {category = {"wood"}},
  ConstructCrutch = {category = {"wood"}},
  ConstructSplint = {category = {"wood"}},
  MakeBucket = {category = {"wood"}},
  MakeCage = {category = {"wood"}},
  MakeBarrel = {category = {"wood"}, inferred = true},
  MakeBackpack = {category = {"leather"}},
  MakeQuiver = {category = {"leather"}},
  SpinThread = {category = {"strand"}},
  CollectSand = {none = true},
  DyeCloth = {none = true},
  MakeAsh = {none = true},
  MakeCharcoal = {none = true},
  MakeLye = {none = true},
  MakePotashFromAsh = {none = true},
  MakeTotem = {none = true},
  MeltMetalObject = {none = true},
  MillPlants = {none = true},
  PrepareMeal = {none = true},
  ProcessPlants = {none = true},
  ProcessPlantsBarrel = {none = true},
  CustomReaction = {none = true},
  ConstructBag = {requires = true},
  ExtractMetalStrands = {requires = true},
  MakeAmmo = {requires = true},
  MakeArmor = {requires = true},
  MakeFlask = {requires = true},
  MakeGloves = {requires = true},
  MakeHelm = {requires = true},
  MakePants = {requires = true},
  MakePipeSection = {requires = true},
  MakeRawGlass = {requires = true},
  MakeShield = {requires = true},
  MakeShoes = {requires = true},
  MakeTool = {requires = true},
  MakeTrapComponent = {requires = true},
  MakeWeapon = {requires = true},
  MakeWindow = {requires = true},
  SmeltOre = {requires = true},
  WeaveCloth = {requires = true},
}

local function needs_material(policy)
  return policy ~= nil and (policy.material ~= nil or policy.category ~= nil or policy.requires == true)
end

-- Generic job resolution: a live `df.job_type` name, or (falling back) a
-- reaction code from world.raws.reactions.reactions -- see header. Never a
-- per-job branch, never a hardcoded table of known jobs.
local function resolve_job(job_arg)
  local name = tostring(job_arg)
  if name == "" or name == "NONE" then
    return nil
  end
  local ok, as_type = pcall(function() return df.job_type[name] end)
  if ok and type(as_type) == "number" then
    return {job = name, reaction = nil}
  end
  local ok_r, reactions = pcall(function() return df.global.world.raws.reactions.reactions end)
  if ok_r and reactions then
    for i = 0, #reactions - 1 do
      local ok_code, code = pcall(function() return reactions[i].code end)
      if ok_code and code == name then
        return {job = "CustomReaction", reaction = name}
      end
    end
  end
  return nil
end

local function resolve_job_name(id_or_reaction)
  local ok, name = pcall(function() return df.job_type[id_or_reaction] end)
  return ok and name or nil
end

-- Enum type name for order.frequency is NOT confirmed live on this install
-- (research/2026-09-18-work-orders.md/2026-09-23 both only ever read
-- job_type/status-style fields, not this one). manager_order.frequency is a
-- struct-nested enum (research/2026-09-23-work-orders-vs-direct-jobs.md §A1:
-- "NONE/OneTime/Daily/Monthly/Seasonally/Yearly, a plain enum"), and this
-- project's own precedent for a struct-nested enum is
-- `df.<struct>.T_<field>` (DFHack's usual naming for an enum declared
-- inline). Tried here defensively, in order, never guessed past a raw
-- number: a caller told `frequency_name = nil, frequency = <int>` knows
-- exactly as much as this tool could confirm, not a silently wrong label.
-- 2026-10-01: research/2026-10-01-quartermaster-levers.md §1 confirms the
-- real top-level type name IS `df.workquota_frequency_type` (df.workquota.
-- xml, source-verified) -- kept as the first candidate below, the old
-- struct-nested guesses kept only as a fallback in case this install's own
-- binding differs.
local FREQUENCY_ENUM_CANDIDATES = {
  "workquota_frequency_type",
  "manager_order.T_frequency",
  "manager_order_frequency",
}

local function resolve_frequency_name(raw)
  if raw == nil then
    return nil
  end
  for _, path in ipairs(FREQUENCY_ENUM_CANDIDATES) do
    local enum = df
    for part in path:gmatch("[^.]+") do
      if enum == nil then break end
      enum = enum[part]
    end
    if enum then
      local ok, name = pcall(function() return enum[raw] end)
      if ok and name then
        return name
      end
    end
  end
  return nil
end

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

-- Order status/progress fields, added handoffs/2026-09-23-order-job-
-- attribution-and-checks.md: `manager_order.status` carries `validated`/
-- `active` bits (live-verified on this fort's three stuck orders:
-- validated=true, active=false -- the failure is a missing announcement,
-- not a missing state; superseded 2026-10-07, see evals/live/2026-10-07-manager-orders); `finished_year`/`finished_year_tick` are both -1 on
-- those same orders. Every field is read defensively (pcall) and reported
-- as nil, never a guessed default, if the struct shape does not match what
-- this comment documents.
-- NOTE: deliberately NOT the usual `ok and v or nil` shortcut anywhere in
-- here -- `validated`/`active` are booleans, and that idiom silently turns a
-- real `false` into `nil` (Lua's `false or nil` is `nil`), which would be
-- exactly backwards for a status bit. Every field below is set with a plain
-- `if ok then out.field = v end` instead.
local function order_status_fields(order)
  local out = {validated = nil, active = nil, finished_year = nil, finished_year_tick = nil}
  local ok_status, status = pcall(function() return order.status end)
  if ok_status and status then
    local ok_v, v = pcall(function() return status.validated end)
    if ok_v then out.validated = v end
    local ok_a, a = pcall(function() return status.active end)
    if ok_a then out.active = a end
  end
  local ok_fy, fy = pcall(function() return order.finished_year end)
  if ok_fy then out.finished_year = fy end
  local ok_fyt, fyt = pcall(function() return order.finished_year_tick end)
  if ok_fyt then out.finished_year_tick = fyt end
  return out
end

-- Reads live bitfield flags that are set to true, by NAME, never against a
-- hardcoded flag list -- see the header's MATERIAL_CATEGORY note for why
-- this project does not (and cannot, from DFHack source alone) know
-- job_material_category's flag names in advance. DFHack Lua exposes a
-- bitfield struct field as a plain table of name -> bool, so this is a
-- generic reflection, not a guess.
local function true_flag_names(bitfield)
  local out
  local ok = pcall(function()
    out = {}
    for k, v in pairs(bitfield) do
      if v == true then table.insert(out, k) end
    end
  end)
  if not ok then return nil end
  table.sort(out)
  return out
end

local function describe_item_condition(cond)
  local ok_ct, ct = pcall(function() return cond.compare_type end)
  local ok_val, val = pcall(function() return cond.compare_val end)
  local ok_it, it = pcall(function() return cond.item_type end)
  local ok_mt, mt = pcall(function() return cond.mat_type end)
  local ok_mi, mi = pcall(function() return cond.mat_index end)
  local out = {}
  if ok_ct then out.condition = df.logic_condition_type[ct] end
  if ok_val then out.value = val end
  if ok_it and it ~= nil and it ~= df.item_type.NONE then
    out.item_type = df.item_type[it]
  end
  if ok_mt and ok_mi and mt ~= nil and mt >= 0 then
    local ok_m, mi_obj = pcall(dfhack.matinfo.decode, mt, mi)
    if ok_m and mi_obj then
      local ok_s, s = pcall(function() return mi_obj:toString() end)
      if ok_s then out.material = s end
    end
  end
  return out
end

local function describe_order_condition(cond)
  local ok_id, oid = pcall(function() return cond.order_id end)
  local ok_c, c = pcall(function() return cond.condition end)
  local out = {}
  if ok_id then out.order = oid end
  if ok_c then out.condition = df.workquota_order_condition_type[c] end
  return out
end

-- The one shared "read the order back as the game holds it" function --
-- used by list_orders (task 4: never an echo of the request) and, after a
-- real create, by create_order's own post-write readback.
local function describe_order(order)
  local ok_job, job_type = pcall(function() return order.job_type end)
  local job_name = ok_job and resolve_job_name(job_type) or nil
  local ok_reaction, reaction = pcall(function() return order.reaction_name end)
  local ok_freq, freq_raw = pcall(function() return order.frequency end)
  local ok_maxws, max_workshops = pcall(function() return order.max_workshops end)
  local ok_wsid, workshop_id = pcall(function() return order.workshop_id end)
  local ok_cat, cat = pcall(function() return order.material_category end)
  local ok_mt, mat_type = pcall(function() return order.mat_type end)
  local ok_mi, mat_index = pcall(function() return order.mat_index end)
  local status_fields = order_status_fields(order)

  local item_conditions = {}
  local ok_ic, ic_vec = pcall(function() return order.item_conditions end)
  if ok_ic and ic_vec then
    for i = 0, #ic_vec - 1 do
      table.insert(item_conditions, describe_item_condition(ic_vec[i]))
    end
  end

  local order_conditions = {}
  local ok_oc, oc_vec = pcall(function() return order.order_conditions end)
  if ok_oc and oc_vec then
    for i = 0, #oc_vec - 1 do
      table.insert(order_conditions, describe_order_condition(oc_vec[i]))
    end
  end

  local row = {
    id = order.id,
    job = job_name,
    reaction = (ok_reaction and reaction ~= "") and reaction or nil,
    amount_left = order.amount_left,
    amount_total = order.amount_total,
    frequency = ok_freq and resolve_frequency_name(freq_raw) or nil,
    frequency_raw = ok_freq and freq_raw or nil,
    max_workshops = ok_maxws and max_workshops or nil,
    workshop_id = (ok_wsid and workshop_id ~= -1) and workshop_id or nil,
    material_category = ok_cat and true_flag_names(cat) or nil,
    item_conditions = item_conditions,
    order_conditions = order_conditions,
  }
  for k, v in pairs(status_fields) do
    row[k] = v
  end

  -- Material as the game holds it, and the invalid_material flag: a job the
  -- policy says needs a material, ordered with none (mat_type < 0 and no
  -- category flag), is shown by the game as "Make unknown material".
  local material_set = false
  if ok_mt and ok_mi and mat_type ~= nil and mat_type >= 0 then
    material_set = true
    local ok_m, mi_obj = pcall(dfhack.matinfo.decode, mat_type, mat_index)
    if ok_m and mi_obj then
      local ok_s, str = pcall(function() return mi_obj:toString() end)
      if ok_s then row.material = str end
    end
  end
  local policy = job_name and ORDER_MATERIAL_POLICY[job_name] or nil
  if needs_material(policy) and not material_set
      and not (row.material_category and #row.material_category > 0) then
    row.invalid_material = true
    row.invalid_material_reason = tostring(job_name)
      .. " needs a material or material category and this order has none"
      .. " (the game shows it as \"Make unknown material\" and it makes nothing);"
      .. " cancel it and create it again with MATERIAL or MATERIAL_CATEGORY"
  else
    row.invalid_material = false
  end
  return row
end

function list_orders()
  local out = {}
  local vec = df.global.world.manager_orders.all
  for i = 0, #vec - 1 do
    local row = describe_order(vec[i])
    row.queue_position = i + 1
    table.insert(out, row)
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

-- "" (dfmcp's own "omit" sentinel for a skipped optional flat-string
-- argument) and nil both mean "not given".
local function is_blank(v)
  return v == nil or v == ""
end

local function split_list(s, sep)
  local out = {}
  if is_blank(s) then return out end
  for part in tostring(s):gmatch("([^" .. sep .. "]+)") do
    table.insert(out, part)
  end
  return out
end

-- Splits on a literal separator, preserving empty fields (Lua's gmatch-based
-- splitting does not, which would silently misalign "AtMost:50::GRANITE"'s
-- deliberately-empty ITEM_TYPE field).
local function split_fields(s, sep)
  local out = {}
  local pos = 1
  while true do
    local i = s:find(sep, pos, true)
    if not i then
      table.insert(out, s:sub(pos))
      break
    end
    table.insert(out, s:sub(pos, i - 1))
    pos = i + #sep
  end
  return out
end

-- See header: validated against the REAL bitfield's own live keys (a
-- throwaway df.manager_order, never inserted into world.manager_orders.all,
-- matching workorder.lua's own with_onerror new/delete pattern), since this
-- project has no source-level list of job_material_category's flag names.
local function validate_material_category(names)
  if #names == 0 then
    return true
  end
  local tmp = df.manager_order:new()
  local unknown = {}
  local ok, err = pcall(function()
    local present = {}
    for k in pairs(tmp.material_category) do present[k] = true end
    for _, n in ipairs(names) do
      if not present[n] then unknown[#unknown + 1] = n end
    end
  end)
  tmp:delete()
  if not ok then
    return false, "could not validate material_category against the live bitfield: " .. tostring(err)
  end
  if #unknown > 0 then
    return false, "unknown material_category flag(s): " .. table.concat(unknown, ", ")
  end
  return true
end

-- See header for the syntax. Never refuses here -- validate_item_condition
-- below does that, with a field-numbered reason.
local function parse_item_conditions(s)
  local out = {}
  if is_blank(s) then return out end
  for _, chunk in ipairs(split_fields(s, ";")) do
    if chunk ~= "" then
      local f = split_fields(chunk, ":")
      local cond = {condition = f[1], value = f[2]}
      if f[3] and f[3] ~= "" then cond.item_type = f[3] end
      if f[4] then
        cond.material = table.concat(f, ":", 4)
      end
      table.insert(out, cond)
    end
  end
  return out
end

local function validate_item_condition(cond, idx)
  if not cond.condition or cond.condition == "" then
    return "item_conditions[" .. idx .. "]: missing comparison operator"
  end
  local ok_c, cid = pcall(function() return df.logic_condition_type[cond.condition] end)
  if not (ok_c and type(cid) == "number") or cond.condition == "NONE" then
    return "item_conditions[" .. idx .. "]: unknown comparison operator "
      .. tostring(cond.condition) .. " (expected AtLeast, AtMost, GreaterThan, LessThan, Exactly or Not)"
  end
  if not cond.value or tonumber(cond.value) == nil then
    return "item_conditions[" .. idx .. "]: value must be a number, got " .. tostring(cond.value)
  end
  if cond.item_type then
    local ok_it, it = pcall(function() return df.item_type[cond.item_type] end)
    if not (ok_it and type(it) == "number") then
      return "item_conditions[" .. idx .. "]: unknown item_type " .. tostring(cond.item_type)
    end
  end
  if cond.material then
    local ok_m, mat = pcall(dfhack.matinfo.find, cond.material)
    if not (ok_m and mat) then
      return "item_conditions[" .. idx .. "]: unknown material " .. tostring(cond.material)
    end
  end
  return nil
end

local function parse_order_conditions(s)
  local out = {}
  if is_blank(s) then return out end
  for _, chunk in ipairs(split_fields(s, ";")) do
    if chunk ~= "" then
      local f = split_fields(chunk, ":")
      table.insert(out, {order = f[1], condition = f[2]})
    end
  end
  return out
end

local function validate_order_condition(cond, idx)
  if not cond.order or tonumber(cond.order) == nil then
    return "order_conditions[" .. idx .. "]: order id must be a number, got " .. tostring(cond.order)
  end
  if not cond.condition or cond.condition == "" then
    return "order_conditions[" .. idx .. "]: missing state (expected Activated or Completed)"
  end
  local ok_c, cid = pcall(function() return df.workquota_order_condition_type[cond.condition] end)
  if not (ok_c and type(cid) == "number") or cond.condition == "NONE" then
    return "order_conditions[" .. idx .. "]: unknown state " .. tostring(cond.condition)
      .. " (expected Activated or Completed)"
  end
  local target = tonumber(cond.order)
  local found = false
  local vec = df.global.world.manager_orders.all
  for i = 0, #vec - 1 do
    if vec[i].id == target then found = true break end
  end
  if not found then
    return "order_conditions[" .. idx .. "]: no existing manager order with id " .. tostring(target)
      .. " (order_conditions can only reference an order already in the queue, not a sibling"
      .. " created in the same call -- this tool creates one order per call, not a batch)"
  end
  return nil
end

-- DRY_RUN defaults to true. See header for the full argument shape, and for
-- MANAGER PREREQUISITE / WORKSHOP PREREQUISITE caveats. Every optional
-- argument is "" (dfmcp's own "omit" sentinel) when not given.
function create_order(
  job_arg, amount, frequency, material, material_category,
  workshop_id, max_workshops, item_conditions, order_conditions, dry_run
)
  local resolved = resolve_job(job_arg)
  if not resolved then
    return nil, "unknown job: " .. tostring(job_arg)
      .. " (expected a live df.job_type name, e.g. ConstructBlocks, or a"
      .. " reaction code from world.raws.reactions.reactions, e.g. BREW_DRINK_FROM_PLANT)"
  end
  if resolved.job == "CustomReaction" and not resolved.reaction then
    return nil, "CustomReaction requires a reaction code: pass the reaction's raw code"
      .. " (e.g. BREW_DRINK_FROM_PLANT) as JOB, not the job type name CustomReaction itself"
  end

  amount = tonumber(amount)
  if not amount or amount < 0 then
    return nil, "AMOUNT must be a non-negative integer (0 = infinite)"
  end

  local order = {job = resolved.job, amount_total = amount}
  if resolved.reaction then
    order.reaction = resolved.reaction
  end

  if not is_blank(frequency) then
    local ok_f, fid = pcall(function() return df.workquota_frequency_type[frequency] end)
    if not (ok_f and type(fid) == "number") or frequency == "NONE" then
      return nil, "unknown frequency: " .. tostring(frequency)
        .. " (expected one of OneTime, Daily, Monthly, Seasonally, Yearly)"
    end
    order.frequency = frequency
  end

  if not is_blank(material) then
    local ok_m, mat = pcall(dfhack.matinfo.find, material)
    if not (ok_m and mat) then
      return nil, "unknown material: " .. tostring(material)
    end
    order.material = material
  end

  local category_names = split_list(material_category, ",")
  if #category_names > 0 then
    local ok_cat, cat_err = validate_material_category(category_names)
    if not ok_cat then
      return nil, cat_err
    end
    order.material_category = category_names
  end

  -- A valid order needs a material for an item job (see ORDER_MATERIAL_POLICY).
  -- Default it from the policy when the caller gave none, or refuse by name.
  local defaulted = false
  if is_blank(material) and #category_names == 0 and not resolved.reaction then
    local policy = ORDER_MATERIAL_POLICY[resolved.job]
    if policy == nil or policy.requires then
      return nil, tostring(resolved.job) .. " needs a material: pass MATERIAL (e.g."
        .. " INORGANIC:GRANITE, INORGANIC:IRON) or MATERIAL_CATEGORY (e.g. wood, leather)."
        .. " An order with neither is shown by the game as \"Make unknown material\""
        .. " and is never worked."
    elseif policy.material then
      order.material = policy.material
      defaulted = true
    elseif policy.category then
      order.material_category = {table.unpack(policy.category)}
      defaulted = true
    end
  end

  if not is_blank(workshop_id) then
    local wsid = tonumber(workshop_id)
    if not wsid then
      return nil, "WORKSHOP_ID must be a number"
    end
    if not df.building.find(wsid) then
      return nil, "no building with id " .. tostring(wsid)
    end
    order.workshop_id = wsid
  end

  if not is_blank(max_workshops) then
    local maxws = tonumber(max_workshops)
    if not maxws or maxws < 0 then
      return nil, "MAX_WORKSHOPS must be a non-negative integer (0 = unlimited)"
    end
    order.max_workshops = maxws
  end

  local parsed_item_conditions = parse_item_conditions(item_conditions)
  for i, cond in ipairs(parsed_item_conditions) do
    local err = validate_item_condition(cond, i)
    if err then return nil, err end
  end
  if #parsed_item_conditions > 0 then
    order.item_conditions = parsed_item_conditions
  end

  local parsed_order_conditions = parse_order_conditions(order_conditions)
  for i, cond in ipairs(parsed_order_conditions) do
    local err = validate_order_condition(cond, i)
    if err then return nil, err end
  end
  if #parsed_order_conditions > 0 then
    order.order_conditions = parsed_order_conditions
  end

  local dry = truthy_dry_run(dry_run)

  local base = {
    dry_run = dry,
    manager_appointed = manager_appointed(),
    material_defaulted = defaulted,
  }

  if dry then
    base.would_queue = order
    return base
  end

  -- Real mutation. Reproduces workorder.lua's own default_action call
  -- sequence exactly -- see header. UNTESTED live (mutation forbidden this
  -- session, no live access per the handoff).
  local expected_id = df.global.world.manager_orders.manager_order_next_id
  local ok_pre, orders_or_err = pcall(workorder_mod.preprocess_orders, {order})
  if not ok_pre then
    base.create_ok = false
    base.create_error = tostring(orders_or_err)
    return base
  end
  local orders = orders_or_err
  -- workorder.lua prints "Queuing JOB xN" to stdout from inside
  -- create_orders (wo.lua:437). On stdout it lands before our JSON, so the
  -- MCP layer reads a successful create as a failure (found live
  -- 2026-10-01: order 4 was created while the call reported isError). Its
  -- print is looked up in the script's own env, so shadow it there for the
  -- duration of the call and report the lines as a field instead.
  local captured = {}
  local had_print = rawget(workorder_mod, 'print')
  workorder_mod.print = function(...)
    local parts = {}
    for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    captured[#captured + 1] = table.concat(parts, '\t')
  end
  pcall(workorder_mod.fillin_defaults, orders)
  local ok_create, create_err = pcall(workorder_mod.create_orders, orders)
  workorder_mod.print = had_print
  if #captured > 0 then base.workorder_output = captured end
  base.create_ok = ok_create
  base.create_error = (not ok_create) and tostring(create_err) or nil
  if ok_create then
    -- Read back the order as the game now holds it (task 4: never an echo
    -- of the request). expected_id is the pre-call manager_order_next_id --
    -- create_orders assigns exactly that id to our one order
    -- (wo.lua:188-192, id_mapping keyed off the counter before it
    -- increments), so this is exact under the ordinary single-caller,
    -- paused-fort assumption every write in this project already makes, not
    -- a guess.
    local vec = df.global.world.manager_orders.all
    local found = nil
    for i = 0, #vec - 1 do
      if vec[i].id == expected_id then found = vec[i] break end
    end
    if found then
      base.order = describe_order(found)
      -- Item binding 3b: a handle the conductor records against the project that made this
      -- order, so only orders our system created are ever cancelled by code
      -- (dfqueue/action_tools.yaml created_refs).
      base.order_handle = "order-" .. tostring(found.id)
    else
      base.create_note = "order reported created but not found at expected id "
        .. tostring(expected_id) .. " -- amount_total may have resolved to a"
        .. " skip (create_orders' own amount<0 delete path, wo.lua:422-427)"
    end
  end
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

-- DRY_RUN defaults to true. See header's REORDER section for why this is a
-- direct vector splice, not a native command. POSITION is 1-based, matching
-- list_orders' own queue_position.
function reorder_order(id, position, dry_run)
  id = tonumber(id)
  if not id then
    return nil, "ID must be a number"
  end
  position = tonumber(position)
  if not position or position < 1 or position ~= math.floor(position) then
    return nil, "POSITION must be a positive integer (1-based, matching orders.list's queue_position)"
  end

  local vec = df.global.world.manager_orders.all
  local idx = nil
  for i = 0, #vec - 1 do
    if vec[i].id == id then idx = i break end
  end
  if not idx then
    return nil, "no manager order with id " .. tostring(id)
  end

  local n = #vec
  local target_idx = math.min(position - 1, n - 1)
  local dry = truthy_dry_run(dry_run)

  if dry then
    return {
      dry_run = true,
      id = id,
      current_position = idx + 1,
      requested_position = position,
      would_move_to_position = target_idx + 1,
    }
  end

  -- Real mutation. UNTESTED live -- see header.
  local order = vec[idx]
  local ok_erase = pcall(function() vec:erase(idx) end)
  local insert_idx = target_idx
  if ok_erase and insert_idx > idx then
    -- erasing idx shifted everything after it left by one.
    insert_idx = insert_idx - 1
  end
  local ok_insert = false
  if ok_erase then
    ok_insert = pcall(function() vec:insert(insert_idx, order) end)
  end
  return {
    dry_run = false,
    id = id,
    erase_ok = ok_erase,
    insert_ok = ok_insert,
    new_position = ok_insert and (insert_idx + 1) or nil,
  }
end

-- DRY_RUN defaults to true. See header's RECHECK section: there is no
-- native per-order recheck to wrap, so this mirrors the native command's
-- own gate (item_conditions present, status.active true) scoped to one id.
-- Never hard-refuses on an ineligible order (matching check_duplicate's own
-- "report, don't refuse" style for a legitimate no-op state) -- only ID
-- itself being unparseable or unknown is a refusal.
function recheck_order(id, dry_run)
  id = tonumber(id)
  if not id then
    return nil, "ID must be a number"
  end

  local vec = df.global.world.manager_orders.all
  local found = nil
  for i = 0, #vec - 1 do
    if vec[i].id == id then found = vec[i] break end
  end
  if not found then
    return nil, "no manager order with id " .. tostring(id)
  end

  local ok_ic, ic_vec = pcall(function() return found.item_conditions end)
  local has_conditions = ok_ic and ic_vec ~= nil and #ic_vec > 0
  local status_fields = order_status_fields(found)
  local eligible = has_conditions and status_fields.active == true
  local dry = truthy_dry_run(dry_run)

  if not eligible then
    return {
      dry_run = dry,
      id = id,
      has_item_conditions = has_conditions,
      active = status_fields.active,
      would_recheck = false,
      recheck_ok = false,
      reason = (not has_conditions)
        and "no item_conditions on this order -- matches native `orders recheck`'s own gate,"
          .. " which only ever touches conditioned orders"
        or "order is not currently active -- native `orders recheck` only clears bits on"
          .. " orders that are both conditioned and active",
    }
  end

  if dry then
    return {
      dry_run = true,
      id = id,
      has_item_conditions = has_conditions,
      active = status_fields.active,
      would_recheck = true,
    }
  end

  -- Real mutation. UNTESTED live -- see header.
  local ok_v = pcall(function() found.status.validated = false end)
  local ok_a = pcall(function() found.status.active = false end)
  return {
    dry_run = false,
    id = id,
    cleared_validated = ok_v,
    cleared_active = ok_a,
  }
end

-- Scans both routes for something already in flight for JOB: open manager
-- orders (world.manager_orders.all, resolve_job for the job_type/reaction
-- mapping) and live jobs (df-overseer-stuckjobs.lua's find_jobs_by_type,
-- reqscript'd -- see the header for why this lives here rather than in a
-- native dfmcp tool or dfqueue). Read-only; never refuses, only reports, so
-- the caller (the Overseer, before it writes) decides what "duplicate"
-- means for its own action.
function check_duplicate(job_name)
  local resolved = resolve_job(job_name)
  if not resolved then
    return nil, "unknown job: " .. tostring(job_name)
      .. " (expected a live df.job_type name or a reaction code)"
  end

  local orders_in_flight = {}
  local vec = df.global.world.manager_orders.all
  for i = 0, #vec - 1 do
    local order = vec[i]
    local ok_job, job_type = pcall(function() return order.job_type end)
    local job_name_live = ok_job and resolve_job_name(job_type) or nil
    local reaction_match = true
    if resolved.reaction then
      local ok_r, r = pcall(function() return order.reaction_name end)
      reaction_match = ok_r and r == resolved.reaction
    end
    if ok_job and job_name_live == resolved.job and reaction_match then
      local status_fields = order_status_fields(order)
      table.insert(orders_in_flight, {
        id = order.id,
        amount_left = order.amount_left,
        amount_total = order.amount_total,
        validated = status_fields.validated,
        active = status_fields.active,
      })
    end
  end

  local ok_jobs, jobs_in_flight = pcall(
    stuckjobs_mod.find_jobs_by_type, resolved.job, resolved.reaction)
  if not ok_jobs then
    jobs_in_flight = nil
  end

  return {
    job = job_name,
    orders_in_flight = orders_in_flight,
    jobs_in_flight = jobs_in_flight,
    duplicate_risk = (#orders_in_flight > 0)
      or (jobs_in_flight ~= nil and #jobs_in_flight > 0),
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
  local job, amount, frequency, material, material_category, workshop_id,
    max_workshops, item_conditions, order_conditions, dry_run =
    args[2], args[3], args[4], args[5], args[6], args[7], args[8], args[9], args[10], args[11]
  if not (job and amount) then
    print("usage: df-overseer-orders create JOB AMOUNT [FREQUENCY] [MATERIAL]"
      .. " [MATERIAL_CATEGORY] [WORKSHOP_ID] [MAX_WORKSHOPS] [ITEM_CONDITIONS]"
      .. " [ORDER_CONDITIONS] [DRY_RUN]")
  else
    local result, err = create_order(job, amount, frequency, material,
      material_category, workshop_id, max_workshops, item_conditions,
      order_conditions, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "reorder" then
  local id, position, dry_run = args[2], args[3], args[4]
  if not (id and position) then
    print("usage: df-overseer-orders reorder ID POSITION [DRY_RUN]")
  else
    local result, err = reorder_order(id, position, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "recheck" then
  local id, dry_run = args[2], args[3]
  if not id then
    print("usage: df-overseer-orders recheck ID [DRY_RUN]")
  else
    local result, err = recheck_order(id, dry_run)
    print(json.encode(err and {error = err} or result))
  end
elseif cmd == "check-duplicate" then
  local job = args[2]
  if not job then
    print("usage: df-overseer-orders check-duplicate JOB")
  else
    local result, err = check_duplicate(job)
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
  print("usage: df-overseer-orders create JOB AMOUNT [FREQUENCY] [MATERIAL]"
    .. " [MATERIAL_CATEGORY] [WORKSHOP_ID] [MAX_WORKSHOPS] [ITEM_CONDITIONS]"
    .. " [ORDER_CONDITIONS] [DRY_RUN]")
  print("usage: df-overseer-orders reorder ID POSITION [DRY_RUN]")
  print("usage: df-overseer-orders recheck ID [DRY_RUN]")
  print("usage: df-overseer-orders check-duplicate JOB")
  print("usage: df-overseer-orders cancel ID [DRY_RUN]")
end
