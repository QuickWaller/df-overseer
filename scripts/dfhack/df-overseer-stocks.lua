-- df-overseer-stocks.lua
--@module = true
--
-- handoffs/2026-09-16-stocks-read-and-labor-race.md item 1: the sharpest
-- named gap in the project. On 2026-09-16 the orchestrator counted 234 food
-- and 50 drink items on the map and reported the fort fed; every one was
-- `flags.foreign`, sitting in merchant wagons, and the user caught it from
-- the screen. This tool exists to make that distinction mechanically,
-- forever, instead of by a human staring at a raw count.
--
-- THE LOAD-BEARING CORRECTION, verified live against Uniboslan (paused,
-- 15 citizens, tick 213622) before writing a single line of ownership logic
-- below, not assumed from the handoff's own suggestion:
--
-- `flags.foreign` is NOT a fort-owned/caravan-owned test. It is an ORIGIN
-- flag ("did this item come from off-site", i.e. embark outfitting OR a
-- caravan), not a CURRENT-OWNERSHIP flag. Live evidence, this session:
--   - The fort's own starting barrels (BARREL ids 794-798), sitting
--     on_ground at the embark site, never inside any wagon or container,
--     carry `foreign=true`. So do the fort's own starting seeds (all 119 of
--     them) and the fort's own starting wood, already built into a
--     building. Using `not flags.foreign` as the ownership test would have
--     zeroed out the fort's OWN embark supplies, not just the caravan's --
--     a worse bug than the one this tool exists to fix, not a fix for it.
--   - By contrast, `flags.foreign` is FALSE on every item this session
--     found that was produced on-site after founding (checked: ANY_REFUSE
--     items, e.g. butchering/skeletal remains, carry no `foreign` flag at
--     all).
--   - `flags.trader` is the real signal. Every item with `trader=true` in
--     this session's sample was, without exception, either (a) inside a
--     currently-present merchant's own wagon/container chain, or (b)
--     directly held by a unit for which `dfhack.units.isMerchant()` returns
--     true (checked live via each item's own `UNIT_HOLDER` general_ref,
--     resolved to a real unit, resolved to isMerchant==true) -- confirmed
--     for a BOULDER a caravan brought to sell. `trader` was ALWAYS a subset
--     of `foreign` in a full-item-vector sweep this session ran (1344 items
--     in play: 565 foreign, 292 trader, 292 both, ZERO trader-without-
--     foreign) -- i.e. every caravan-held good is also origin-foreign, but
--     the reverse does not hold, which is exactly the bug: `foreign` alone
--     cannot tell "still in the caravan's wagon" apart from "the fort's own
--     unclaimed embark stock."
--   - Concretely, on the live fort this session checked: of 119 SEEDS
--     items, 60 are `trader=true` (the caravan is offering seed varieties
--     for sale) and only 59 are genuinely fort-owned -- so even the
--     handoff's own framing ("the fort has 119 seeds recorded") already
--     overcounts by roughly half if read naively off the SEEDS vector
--     without this filter.
--   - `dfhack.units.isOwnCiv()` on the caravan's own merchant units returns
--     TRUE (this fort's first caravan is dispatched by the player's own
--     civilization, the ordinary case for a young fort's home-civ trade
--     caravan) -- so civ identity is ALSO not a usable ownership test here,
--     independently of the foreign/trader finding above.
--
-- So `is_fort_owned` below tests `not flags.trader`, never `not
-- flags.foreign`. `foreign_total` is still reported per bucket (the count
-- this flag actually measures: total items of that kind currently in play,
-- own + caravan's) so a caller can see both numbers and the gap between
-- them, rather than silently discarding the old, wrong signal with no
-- trace of what it would have said.
--
-- NOT VERIFIED, flagged rather than assumed: whether `flags.foreign` is
-- ever cleared once an item is fully "integrated" into the fort (e.g. after
-- a season, after being moved to a proper stockpile) -- this session only
-- observed a fort still within its first year. If it never clears, the
-- name is simply misleading for this project's purposes for the life of a
-- fort, not a transient embark-only quirk. Also not verified: `flags.owned`
-- (a real, distinct bitfield flag) was checked and found unrelated --
-- it was false on every DRINK/BOULDER/SEED item sampled and is believed to
-- track personal (per-dwarf) ownership, not fort-vs-caravan, but this was
-- not exhaustively confirmed against a citizen-owned item.
--
-- `is_fort_owned` also excludes `garbage_collect`/`removed` defensively
-- (an item mid-deletion should never count as fort stock) -- these did not
-- fire on anything sampled this session, so this is an honest, untested
-- safety net, not a live-confirmed behavior.
--
-- Buckets, chosen to match DFHack's own item-type/other-id classification
-- rather than reinventing one:
--   drink          -- df.global.world.items.other.DRINK (real alcohol
--                     items; ANY_DRINK was checked and is identical in
--                     count on this fort, so DRINK is used as the
--                     narrower, more literal bucket)
--   prepared_meals -- df.global.world.items.other.FOOD (DF's own "cooked
--                     meal" item type; confirmed 0 on this fort, consistent
--                     with "no kitchen built yet")
--   raw_edibles    -- df.global.world.items.other.ANY_EDIBLE_RAW (DFHack's
--                     own "edible without cooking" classification --
--                     meat/fish/plant/cheese/etc, verified non-empty and
--                     non-trivial on this fort)
--
-- `rotten`/`unreachable` per bucket, per the handoff's own minimum bar,
-- counted in UNITS -- see the "units vs item_count" section below for why:
--   rotten       -- `flags.rotten` on a fort-owned item in that bucket.
--                    Verified real and currently non-zero fort-wide (16 in
--                    play across the whole map this session), though this
--                    session's 3 sampled buckets happened to show 0 -- the
--                    mechanism was exercised and returns a real, non-error
--                    count, not assumed to always read 0.
--   unreachable  -- a fort-owned item whose tile's dfhack.maps.
--                    getWalkableGroup() differs from the fort's main
--                    citizen group (reused from df-overseer-connectivity.lua's
--                    get_connectivity_report(), the same primitive
--                    df-overseer-openarea.lua's is_free already uses live).
--                    An item whose position cannot be resolved at all
--                    (pcall failure, e.g. something deep in a unit's own
--                    inventory) is counted in NEITHER reachable nor
--                    unreachable -- an honest gap, not a guess, matching
--                    this repo's idle_ticks=null idiom in
--                    df-overseer-stuckjobs.lua.
--
-- ============================================================================
-- FIXED 2026-09-16, same day, found by the user reading the screen a THIRD
-- time: "count" IS THE TRAP WORD IN THIS FILE. Read this before touching
-- any field below.
--
-- Three separate miscounts of this exact fort's food happened in one day,
-- every one caught by the user looking at the actual screen, none caught by
-- this project's own tools first:
--   1. Counting the caravan's goods as the fort's own (the bug that started
--      this whole handoff -- 234 food/50 drink items, all foreign).
--   2. Over-correcting with `flags.foreign` as the ownership test (see this
--      file's header above) -- would have zeroed the fort's own embark
--      supplies, a DIFFERENT wrong number, not a fix for the first one.
--   3. THIS bug: `count_bucket` counted ITEM ENTITIES (`own = own + 1` per
--      item), not stack units. DF's own stocks screen -- and every human
--      reading it -- counts units. A fisherdwarf's catch sits in the item
--      vector as a handful of item entities, each with `item.stack_size`
--      possibly >1 (confirmed live this session: FISH/MEAT/PLANT items on
--      this exact fort carry stack_size 4-5, not 1). Reporting "5 raw
--      edible items" when the real number is 24 units of food is exactly
--      as wrong as reporting 0 was -- both are confident, specific, and
--      false. **This bug hid inside the very SEEDS bucket this file used
--      as its own worked example above**, because SEEDS items on this
--      fort happen to carry `stack_size == 1` always (confirmed live,
--      59 items, sum of stack_size also 59) -- a coincidence, not a
--      property of the mechanism, and the reason a same-day dry-run
--      comparison against real seed counts did not catch this.
--
-- `stack_size` was checked live, per type, before trusting it, not assumed
-- present or sane: DRINK (25 units/item, 2 items -> 50 units total),
-- ANY_EDIBLE_RAW/MEAT/FISH/PLANT/CHEESE (4-5 units/item, matches the DF
-- wiki's ordinary butchering/fishing/harvest yield), SEEDS and BARREL
-- (always exactly 1 -- neither actually stacks on this fort). FOOD (the
-- prepared-meals bucket) has zero items on this fort right now, so its own
-- `stack_size` could not be directly sampled -- inferred, not verified, to
-- carry the field too, since it is a base `item` struct field observed
-- present and well-formed on every OTHER type tested here, never type-
-- specific in df-structures. Flagged rather than silently assumed.
--
-- THE FIX: every bucket below now reports BOTH `units` (the `stack_size`
-- sum -- what "how much food do we have" means, and now the PRIMARY field)
-- and `item_count` (the distinct-entity count -- what a hauling job or a
-- container slot actually deals with; a real, different, still-useful
-- number, never silently discarded in favor of `units`). `foreign_units`/
-- `foreign_item_count` mirror the same split on the caravan's side, so the
-- exact same ambiguity cannot quietly reappear there later. `rotten`/
-- `unreachable` are unit sums too, for the identical reason: "1 rotten
-- item" that is actually 5 rotten units of food understates the problem
-- the same way item-counting understated the fort's food.
-- ============================================================================
--
-- ADDED handoffs/2026-09-19-per-item-flags-tool.md, offline build stream (no
-- VM, no DFHack process, no deploy). docs/PRODUCTION-MODEL.md sec7: "Available
-- stock is never total stock", four exact deductions --
--   claimed by a pending job  -- item.flags.in_job
--   owned by a dwarf          -- item.flags.owned, plus the UNIT_HOLDER ref
--   forbidden                 -- item.flags.forbid (NOT `forbidden`)
--   caravan-owned              -- flags.trader, ALREADY netted above by
--                                 is_fort_owned/count_bucket/get_seeds
-- handoffs/2026-09-19-snapshot-assembler.md's write-up grepped every
-- committed tool and found only `trader` reachable: `count_bucket` above
-- folds straight to `units`/`item_count` sums with no per-item record
-- surviving, so nothing downstream could net in_job/owned/forbid even in
-- principle. `production/snapshot.py` already has the fully-netted code
-- path built and tested against fixtures; it has nothing real to consume.
-- `get_availability` below is what feeds it: one DF item-type name in
-- (e.g. "BUCKET", the motivating case -- 3 fort-owned, unforbidden,
-- unclaimed buckets and the fort still logged "Give water: Need empty
-- bucket" at tick 214135, because a totals-only read cannot see the
-- difference between "0 exist" and "3 exist, all claimed/forbidden/owned"),
-- a per-flag-netted breakdown out.
--
-- THE ASSERT-DON'T-TRUST RULE THIS FILE IS BUILT AROUND (docs/TRAPS.md,
-- "Added 2026-09-18": `item.flags.forbidden` "errors outright" live on this
-- install -- `forbidden` is not a field, `forbid` is). A plain
-- `item.flags.<name>` read is exactly the trap: if a name is wrong OR a
-- field is genuinely absent on some future DFHack version and access
-- degrades to a silent nil instead of an error, nil is falsy, so the
-- deduction would read as "never true" and available_units would overcount
-- -- reproducing the exact bug this tool exists to fix, silently. So every
-- read of in_job/forbid/owned below goes through `checked_flag`, which
-- treats "the pcall raised" AND "the pcall returned something that isn't a
-- real boolean" as the SAME honest failure (`ok=false`), never as `false`.
-- An item whose flag couldn't be checked is counted in neither
-- `available` nor a false "unavailable due to X" bucket -- it goes to
-- `unnetted_units`/`unnetted_item_count`, and the flag's name is added to
-- the result's own `flag_read_errors` list, once per distinct name, so a
-- caller can never mistake a silently-broken netting for a clean zero (the
-- project's own prior "0 of 15 for a token that does not exist" incident).
--
-- `owned` NEEDS ITS OTHER HALF, PER SPEC, AND THAT HALF IS UNVERIFIED
-- OFFLINE. This file's own header above already establishes `flags.owned`
-- as a real, distinct field (checked live, found false on every DRINK/
-- BOULDER/SEED item sampled, believed personal not fort ownership --
-- "believed", not proven, since no citizen-owned item was in that sample).
-- docs/PRODUCTION-MODEL.md sec7 is explicit that `owned` alone is not the
-- deduction: it needs the item's own UNIT_HOLDER general_ref as
-- confirmation. `checked_unit_holder_ref` below calls
-- `dfhack.items.getGeneralRef(item, df.general_ref_type.UNIT_HOLDER)`,
-- the same class of call this file's OWN header already describes using
-- to confirm `flags.trader` against a live merchant unit -- but that
-- specific call, for UNIT_HOLDER specifically, has never been run by any
-- COMMITTED code in this repo. The only precedent is an uncommitted, ad
-- hoc `dfhack-run lua` probe in a chat session
-- (df-overseer-orders.lua's own header, tick 227160: "3 fort-owned ...
-- unclaimed, no holder", read by hand, not by this file). So every result
-- this tool returns carries `owned_ref_check.verified_offline = false`,
-- unconditionally -- this stream cannot make that true, only a live run
-- against a real DFHack process can, and until then `owned_units` should
-- be read as "flagged owned", not as an independently confirmed dwarf
-- claim.
--
-- Usage: ./dfhack-run df-overseer-stocks food-drink
-- Usage: ./dfhack-run df-overseer-stocks seeds
-- Usage: ./dfhack-run df-overseer-stocks availability BUCKET

local json = require('json')
local connectivity_mod = reqscript('df-overseer-connectivity')

-- See this file's header for the live verification behind this test.
-- Deliberately NOT `not item.flags.foreign` -- see above.
-- Knowledge scope (decisions/DECISIONS.md 2026-09-16, "agents may only know
-- what a vanilla player could know"). `not flags.trader` alone would count an
-- item lying in an unopened cavern as the fort's own food -- wrong as
-- ownership, and a leak, since the agent would learn the item exists before
-- anyone uncovered it. So an item whose position resolves to a hidden tile is
-- excluded. An item whose position cannot be resolved at all is kept: that is
-- overwhelmingly an item held or stored inside the fort, and excluding it
-- would undercount real stores, the failure this file exists to prevent.
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

-- Returns true/false, or nil if the item's position could not be resolved
-- at all (never guessed as either reachable or unreachable).
local function is_unreachable(item, main_group_id)
  local ok_pos, x, y, z = pcall(dfhack.items.getPosition, item)
  if not ok_pos or not x then
    return nil
  end
  local ok_grp, group = pcall(dfhack.maps.getWalkableGroup, xyz2pos(x, y, z))
  if not ok_grp then
    return nil
  end
  return group ~= main_group_id
end

-- `item.stack_size` is a plain integer field on every item type this file
-- touches (checked live, per type, see this file's "count is the trap
-- word" section). A read failure has never been observed live -- the
-- fallback of 1 unit exists so an unexpected miss degrades to
-- under-by-a-little (still counts the item) rather than silently vanishing
-- the item from every total, which would be the worse failure mode of the
-- two.
local function item_units(item)
  local ok, stack_size = pcall(function() return item.stack_size end)
  if ok and type(stack_size) == "number" and stack_size > 0 then
    return stack_size
  end
  return 1
end

local function count_bucket(vec, main_group_id)
  local own_units, own_items = 0, 0
  local foreign_units, foreign_items = 0, 0
  local rotten_units, unreachable_units = 0, 0
  for i = 0, #vec - 1 do
    local item = vec[i]
    local units = item_units(item)
    if is_fort_owned(item) then
      own_units = own_units + units
      own_items = own_items + 1
      if item.flags.rotten then
        rotten_units = rotten_units + units
      end
      if is_unreachable(item, main_group_id) then
        unreachable_units = unreachable_units + units
      end
    else
      foreign_units = foreign_units + units
      foreign_items = foreign_items + 1
    end
  end
  return {
    units = own_units,
    item_count = own_items,
    foreign_units = foreign_units,
    foreign_item_count = foreign_items,
    rotten_units = rotten_units,
    unreachable_units = unreachable_units,
  }
end

function get_food_drink()
  local report = connectivity_mod.get_connectivity_report()
  local main_group_id = report.main_group_id
  return {
    drink = count_bucket(df.global.world.items.other.DRINK, main_group_id),
    prepared_meals = count_bucket(df.global.world.items.other.FOOD, main_group_id),
    raw_edibles = count_bucket(df.global.world.items.other.ANY_EDIBLE_RAW, main_group_id),
  }
end

-- Plant name resolution: SEEDS items carry mat_type/mat_index, and for a
-- plant seed, mat_index indexes df.global.world.raws.plants.all (confirmed
-- live this session: index 173 on this install resolves to
-- MUSHROOM_HELMET_PLUMP, the standard dwarven plump helmet). A resolution
-- failure (a mat_index this repo has not seen) falls back to an honest
-- "mat_index_<N>" label rather than a guessed name.
--
-- units vs item_count, same split as get_food_drink() and for the same
-- reason (see this file's "count is the trap word" section) -- confirmed
-- live this session that SEEDS items on THIS fort always carry
-- stack_size == 1 (119 items, sum of stack_size also 119), so `total_units`
-- and `total_item_count` happen to be numerically equal here. That
-- equality is an observed fact about this fort right now, not a property
-- of the SEEDS item type verified in general -- reporting only one number
-- would silently repeat the exact assumption that hid this bug in the
-- food-drink buckets, so both are reported here too.
function get_seeds()
  local units_by_plant = {}
  local item_count_by_plant = {}
  local total_units, total_items = 0, 0
  local vec = df.global.world.items.other.SEEDS
  for i = 0, #vec - 1 do
    local item = vec[i]
    if is_fort_owned(item) then
      local units = item_units(item)
      local ok, plant = pcall(function()
        return df.global.world.raws.plants.all[item.mat_index]
      end)
      local name = (ok and plant and plant.id) or ("mat_index_" .. tostring(item.mat_index))
      units_by_plant[name] = (units_by_plant[name] or 0) + units
      item_count_by_plant[name] = (item_count_by_plant[name] or 0) + 1
      total_units = total_units + units
      total_items = total_items + 1
    end
  end
  return {
    total_units = total_units,
    total_item_count = total_items,
    by_plant_units = units_by_plant,
    by_plant_item_count = item_count_by_plant,
  }
end

-- ============================================================================
-- get_availability: the per-item-flags tool. See this file's header above
-- (handoffs/2026-09-19-per-item-flags-tool.md) for why this exists and the
-- honesty rules it is built around.

-- Returns (ok, value). ok is false if this specific named flag could not be
-- read as a real boolean from item.flags on THIS DFHack version -- whether
-- because the read raised (docs/TRAPS.md: `item.flags.forbidden` "errors
-- outright" on this install) or because it silently returned something
-- that is not `true`/`false` (a hypothetical, not observed, but the whole
-- point of this function is to never assume it can't happen). Callers MUST
-- branch on `ok` before trusting `value` -- treating a failed read as
-- `false` is the exact bug (docs/PRODUCTION-MODEL.md sec7, `forbid` not
-- `forbidden`) this tool exists to stop reproducing.
local function checked_flag(item, flag_name)
  local ok, value = pcall(function() return item.flags[flag_name] end)
  if not ok or type(value) ~= "boolean" then
    return false, nil
  end
  return true, value
end

-- Returns (ok, has_ref). ok is false if the UNIT_HOLDER general_ref lookup
-- itself could not be performed (df.general_ref_type.UNIT_HOLDER missing on
-- this build, dfhack.items.getGeneralRef erroring, etc.) -- distinct from
-- has_ref=false, which means the lookup ran cleanly and found no holder.
-- UNVERIFIED OFFLINE (see this file's header): this exact call has never
-- run against a live DFHack process from committed code. Every caller of
-- this function must surface that caveat, not just the count.
local function checked_unit_holder_ref(item)
  local ok, ref = pcall(function()
    return dfhack.items.getGeneralRef(item, df.general_ref_type.UNIT_HOLDER)
  end)
  if not ok then
    return false, nil
  end
  return true, (ref ~= nil)
end

-- Walks ONE df.global.world.items.other[type_name] vector and nets it by
-- all four deduction flags docs/PRODUCTION-MODEL.md sec7 names. Trader (and
-- the same garbage_collect/removed/hidden-tile guard every other function
-- in this file already uses) is netted via the existing, already-verified
-- `is_fort_owned` -- unchanged, not touched by this addition, so
-- food-drink/seeds' own verified behavior cannot regress. in_job/forbid/
-- owned are the marginal three this stream adds, each read through
-- `checked_flag` so a bad field name degrades to an honest "unnetted" tally
-- instead of a silent false-negative.
local function count_availability(vec, main_group_id)
  local total_units, total_items = 0, 0
  local avail_units, avail_items = 0, 0
  local in_job_units, in_job_items = 0, 0
  local forbid_units, forbid_items = 0, 0
  local owned_units, owned_items = 0, 0
  local owned_with_holder_ref, owned_without_holder_ref, owned_ref_lookup_errors = 0, 0, 0
  local trader_units, trader_items = 0, 0
  local rotten_units, unreachable_units = 0, 0
  local unnetted_units, unnetted_items = 0, 0
  local flag_read_errors = {}
  local flag_read_errors_seen = {}

  local function note_error(name)
    if not flag_read_errors_seen[name] then
      flag_read_errors_seen[name] = true
      table.insert(flag_read_errors, name)
    end
  end

  for i = 0, #vec - 1 do
    local item = vec[i]
    local units = item_units(item)

    if item.flags.trader then
      trader_units = trader_units + units
      trader_items = trader_items + 1
    end

    if is_fort_owned(item) then
      total_units = total_units + units
      total_items = total_items + 1

      if item.flags.rotten then
        rotten_units = rotten_units + units
      end
      if is_unreachable(item, main_group_id) then
        unreachable_units = unreachable_units + units
      end

      local in_job_ok, in_job_val = checked_flag(item, "in_job")
      local forbid_ok, forbid_val = checked_flag(item, "forbid")
      local owned_ok, owned_val = checked_flag(item, "owned")
      if not in_job_ok then note_error("in_job") end
      if not forbid_ok then note_error("forbid") end
      if not owned_ok then note_error("owned") end

      if in_job_ok and in_job_val then
        in_job_units = in_job_units + units
        in_job_items = in_job_items + 1
      end
      if forbid_ok and forbid_val then
        forbid_units = forbid_units + units
        forbid_items = forbid_items + 1
      end
      if owned_ok and owned_val then
        owned_units = owned_units + units
        owned_items = owned_items + 1
        local ref_ok, has_ref = checked_unit_holder_ref(item)
        if not ref_ok then
          owned_ref_lookup_errors = owned_ref_lookup_errors + 1
        elseif has_ref then
          owned_with_holder_ref = owned_with_holder_ref + 1
        else
          owned_without_holder_ref = owned_without_holder_ref + 1
        end
      end

      -- Available requires all three marginal flags to have been readable
      -- AND all false. A read failure on ANY of them means this item's
      -- true availability is unknown, not available -- it goes to
      -- `unnetted`, never silently into `avail`.
      if in_job_ok and forbid_ok and owned_ok then
        if (not in_job_val) and (not forbid_val) and (not owned_val) then
          avail_units = avail_units + units
          avail_items = avail_items + 1
        end
      else
        unnetted_units = unnetted_units + units
        unnetted_items = unnetted_items + 1
      end
    end
  end

  return {
    total_units = total_units,
    total_item_count = total_items,
    available_units = avail_units,
    available_item_count = avail_items,
    unnetted_units = unnetted_units,
    unnetted_item_count = unnetted_items,
    in_job_units = in_job_units,
    in_job_item_count = in_job_items,
    forbid_units = forbid_units,
    forbid_item_count = forbid_items,
    owned_units = owned_units,
    owned_item_count = owned_items,
    owned_ref_check = {
      with_unit_holder_ref = owned_with_holder_ref,
      without_unit_holder_ref = owned_without_holder_ref,
      lookup_errors = owned_ref_lookup_errors,
      -- Always false: see this file's header, "UNVERIFIED OFFLINE". Never
      -- flip this to true from inside this file -- it can only become
      -- true from an actual live-run write-up, by a session that ran this
      -- exact command against a real DFHack process.
      verified_offline = false,
    },
    trader_units = trader_units,
    trader_item_count = trader_items,
    rotten_units = rotten_units,
    unreachable_units = unreachable_units,
    flag_read_errors = flag_read_errors,
  }
end

-- type_name: a df.global.world.items.other key, e.g. "BUCKET" (the
-- motivating case -- see this file's header), "DRINK", "SEEDS", "CHAIN",
-- "BLOCKS", "TRAPPARTS", "ANY_EDIBLE_RAW". Returns (nil, message) for an
-- unknown type rather than a silently-empty result -- matching
-- production/snapshot.py's own UnknownNodeError convention, per this
-- stream's handoff: "Unknown node ids are an error, not a silent skip."
function get_availability(type_name)
  if not type_name or type_name == "" then
    return nil, "usage: df-overseer-stocks availability ITEM_TYPE (e.g. BUCKET, DRINK, SEEDS, ANY_EDIBLE_RAW, CHAIN, BLOCKS, TRAPPARTS)"
  end
  local ok_vec, vec = pcall(function() return df.global.world.items.other[type_name] end)
  if not ok_vec or not vec then
    return nil, "unknown item type: " .. tostring(type_name)
      .. " (not a df.global.world.items.other key on this install)"
  end

  local report = connectivity_mod.get_connectivity_report()
  local main_group_id = report.main_group_id

  local result = count_availability(vec, main_group_id)
  result.type = type_name
  return result
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local args = {...}
local cmd = args[1]

if cmd == "food-drink" then
  print(json.encode(get_food_drink()))
elseif cmd == "seeds" then
  print(json.encode(get_seeds()))
elseif cmd == "availability" then
  local result, err = get_availability(args[2])
  if err then
    print(json.encode({error = err}))
  else
    print(json.encode(result))
  end
else
  print("usage: df-overseer-stocks <food-drink|seeds|availability ITEM_TYPE>")
end
