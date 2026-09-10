-- df-overseer-overview.lua
--
-- docs/PURPOSE.md build order item 4: get_overview() / context tiering with
-- deterministic JSON (research/2026-08-25-spatial-perception.md §5/§7/§9).
-- Composes the two prior build-order items rather than re-deriving
-- anything: df-overseer-landmarks.lua's list_landmarks() for tier1, and
-- df-overseer-connectivity.lua's get_connectivity_report() for tier2's
-- alerts, both loaded via reqscript (same pattern those two files already
-- established for reusing warn-stranded.lua).
--
-- Three tiers, stable-to-volatile, per §7's prefix-caching design: tier0
-- (session-constant: fortress name), tier1 (slow-changing: population,
-- landmark table), tier2 (volatile: in-game date/tick, alerts). This
-- script does not itself enforce ordering in the JSON -- DFHack's own
-- json.lua encodes object keys in stable alphabetical order (confirmed
-- live, see df-overseer-connectivity.lua's comments), and "tier0" <
-- "tier1" < "tier2" alphabetically happens to match the intended
-- stable-to-volatile order, so no manual key-ordering code is needed here.
-- What *is* handled deliberately: df-overseer-landmarks.lua's
-- list_landmarks() now sorts landmarks (and each one's exits) by name
-- rather than engine iteration order, so tier1 doesn't silently reshuffle
-- turn to turn and bust a cache for no reason -- build item 4's "must sort
-- keys" requirement, generalized to array ordering, not just object keys.
--
-- get_diff_since (build order item 5, eventful-based) is NOT implemented
-- here -- tier2 below is a fresh snapshot every call, not an incremental
-- diff log. That is real, separate work, sequenced after this one
-- deliberately (docs/PURPOSE.md build order).
--
-- resource_summary (part of the research spec's get_overview() shape) is
-- NOT implemented here either -- it needs a prospect-equivalent resource
-- scan this pass didn't attempt, and fabricating a field with no real
-- backing would be worse than omitting it. Flagged, not silently dropped.
--
-- Usage: ./dfhack-run df-overseer-overview [get]

local json = require('json')
local landmarks_mod = reqscript('df-overseer-landmarks')
local connectivity_mod = reqscript('df-overseer-connectivity')

local function fortress_name()
  local ok_site, site = pcall(dfhack.world.getCurrentSite)
  if not ok_site or not site then
    return nil
  end
  local ok_name, name = pcall(dfhack.translation.translateName, site.name)
  return (ok_name and name ~= '') and name or nil
end

-- One human-readable alert string per stranded group -- an actual sentence,
-- not a raw struct dump, matching the research spec's alerts: [str] shape
-- (§5's get_overview signature).
local function stranded_alerts(report)
  local alerts = {}
  for _, group in ipairs(report.stranded_groups) do
    local detail
    if #group.unit_names == 1 then
      detail = ("1 citizen stranded (group %d): %s"):format(
        group.group_id, group.unit_names[1])
    else
      detail = ("%d citizens stranded (group %d)"):format(
        #group.unit_names, group.group_id)
    end
    if group.near_landmark then
      detail = detail .. (", near %s (%s, %d tiles)"):format(
        group.near_landmark, group.direction, group.distance_tiles)
    end
    table.insert(alerts, detail)
  end
  return alerts
end

local function get_overview()
  local landmark_list, lm_err = landmarks_mod.list_landmarks()
  local report = connectivity_mod.get_connectivity_report()

  return {
    tier0 = {
      fortress = fortress_name() or "unknown",
    },
    tier1 = {
      population = #dfhack.units.getCitizens(true),
      landmarks = lm_err and {} or landmark_list,
    },
    tier2 = {
      in_game_date = ("year %d, month %d, day %d, tick %d"):format(
        dfhack.world.ReadCurrentYear(), dfhack.world.ReadCurrentMonth() + 1,
        dfhack.world.ReadCurrentDay(), dfhack.world.ReadCurrentTick()),
      main_group_id = report.main_group_id,
      alerts = stranded_alerts(report),
    },
  }
end

local args = {...}
local cmd = args[1]

if cmd == "get" or not cmd then
  print(json.encode(get_overview()))
else
  print("usage: df-overseer-overview [get]")
end
