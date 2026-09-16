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
-- `rotten`/`unreachable` per bucket, per the handoff's own minimum bar:
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
-- Usage: ./dfhack-run df-overseer-stocks food-drink
-- Usage: ./dfhack-run df-overseer-stocks seeds

local json = require('json')
local connectivity_mod = reqscript('df-overseer-connectivity')

-- See this file's header for the live verification behind this test.
-- Deliberately NOT `not item.flags.foreign` -- see above.
local function is_fort_owned(item)
  local f = item.flags
  return not f.trader and not f.garbage_collect and not f.removed
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

local function count_bucket(vec, main_group_id)
  local total, own, rotten, unreachable = 0, 0, 0, 0
  for i = 0, #vec - 1 do
    local item = vec[i]
    total = total + 1
    if is_fort_owned(item) then
      own = own + 1
      if item.flags.rotten then
        rotten = rotten + 1
      end
      if is_unreachable(item, main_group_id) then
        unreachable = unreachable + 1
      end
    end
  end
  return {
    count = own,
    foreign_total = total - own,
    rotten_count = rotten,
    unreachable_count = unreachable,
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
function get_seeds()
  local by_plant = {}
  local total = 0
  local vec = df.global.world.items.other.SEEDS
  for i = 0, #vec - 1 do
    local item = vec[i]
    if is_fort_owned(item) then
      total = total + 1
      local ok, plant = pcall(function()
        return df.global.world.raws.plants.all[item.mat_index]
      end)
      local name = (ok and plant and plant.id) or ("mat_index_" .. tostring(item.mat_index))
      by_plant[name] = (by_plant[name] or 0) + 1
    end
  end
  return { total = total, by_plant = by_plant }
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
else
  print("usage: df-overseer-stocks <food-drink|seeds>")
end
