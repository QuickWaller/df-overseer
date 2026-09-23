-- df-overseer-announcement-levels.lua
--@module = true
--
-- GENERATED FILE. Do not hand-edit -- run
-- `python scripts/gen_announcement_pause_slow.py` to regenerate from
-- research/data/2026-09-23-announcement-severity.yaml (the source classification;
-- read research/2026-09-23-announcement-severity.md first for method and
-- caveats). tests/test_announcement_levels_generated.py fails if this file
-- and a fresh run of the generator ever disagree.
--
-- handoffs/2026-09-23-attention-tiers-ingame.md item 2: exposes exactly the
-- two report-level id sets this project's fifth tripwire and the sibling
-- conductor stream need.
--
-- PAUSE_REPORT_IDS (25 ids): df-overseer-clock.lua's fifth
-- tripwire pauses the fort on a newly-arrived df.status.reports entry whose
-- `type` is one of these -- the same "literal id table" shape
-- df-overseer-diff.lua's own REPORT_CATEGORY already uses, generated here
-- instead of hand-copied.
--
-- SLOW_REPORT_IDS (23 ids): NOT PAUSED anywhere in this repo's Lua
-- (handoffs/2026-09-23-attention-tiers-ingame.md item 2: "not yours to act
-- on"). Two consumers: (1) df-overseer-diff.lua's onReport emits a
-- diff.since event `{"type": "announcement_slow", "announcement_type":
-- name, "tick": T, "wake": {...}, "detail": reason}` for a newly-arrived
-- slow-level report -- the exact shape the already-merged sibling conductor
-- stream's conductor/cycle.py `_classify_slow_announcements` assumed and
-- coded against, reconciled here (see this stream's own Result); (2) the
-- `slow-ids`/`level` CLI commands below (and the `announcement-levels.*`
-- MCP tools they become, scripts/dfhack/TOOLS.yaml) for direct
-- introspection. Field shape:
--   pause-ids -> {"ids": [{"id": N, "name": "..."}, ...]}
--   slow-ids  -> {"ids": [{"id": N, "name": "...", "wake": ["overseer", ...], "detail": "..."}, ...]}

local json = require('json')


PAUSE_REPORT_IDS = { -- id -> announcement_type name (df.announcement_type)
  [53] = "AMBUSH_DEFENDER",
  [54] = "AMBUSH_RESIDENT",
  [60] = "AMBUSH_SNATCHER",
  [62] = "AMBUSH_AMBUSHER_NATURE",
  [63] = "AMBUSH_AMBUSHER",
  [82] = "CAVE_COLLAPSE",
  [93] = "MEGABEAST_ARRIVAL",
  [94] = "WEREBEAST_ARRIVAL",
  [95] = "BEAST_AMBUSH",
  [96] = "BERSERK_CITIZEN",
  [106] = "CITIZEN_DEATH",
  [107] = "PET_DEATH",
  [136] = "NIGHT_ATTACK_STARTS",
  [139] = "GHOST_ATTACK",
  [147] = "BODY_TRANSFORMATION",
  [148] = "INTERACTION_ACTOR",
  [149] = "INTERACTION_TARGET",
  [150] = "UNDEAD_ATTACK",
  [182] = "CITIZEN_LOST_TO_STRESS",
  [252] = "CITIZEN_SNATCHED",
  [285] = "POSSESSED_TANTRUM",
  [286] = "BUILDING_TOPPLED_BY_GHOST",
  [313] = "BUILDING_DESTROYED_OR_TOPPLED",
  [314] = "DEITY_CURSE",
  [327] = "EMERGENCY_TACTICAL_CONTROL",
}

SLOW_REPORT_IDS = { -- id -> { name = ..., wake = {role, ...}, detail = "..." }
  [55] = { name = "AMBUSH_THIEF", wake = {"overseer"}, detail = "a thief-class ambush is underway; item loss is real but not fort-ending, worth the Overseer's attention at thinking speed rather than a full stop" },
  [56] = { name = "AMBUSH_THIEF_SUPPORT_SKULKING", wake = {"overseer"}, detail = "a thief-class ambush is underway; item loss is real but not fort-ending, worth the Overseer's attention at thinking speed rather than a full stop" },
  [57] = { name = "AMBUSH_THIEF_SUPPORT_NATURE", wake = {"overseer"}, detail = "a thief-class ambush is underway; item loss is real but not fort-ending, worth the Overseer's attention at thinking speed rather than a full stop" },
  [58] = { name = "AMBUSH_THIEF_SUPPORT", wake = {"overseer"}, detail = "a thief-class ambush is underway; item loss is real but not fort-ending, worth the Overseer's attention at thinking speed rather than a full stop" },
  [59] = { name = "AMBUSH_MISCHIEVOUS", wake = {"overseer"}, detail = "a mischief-class ambusher (this is the announcement family a kea's approach would actually surface under, per the sibling wildlife-threat brief); slow and let the Quartermaster or Overseer glance at it rather than pausing the fort outright -- the concrete fix for the kea overreaction" },
  [61] = { name = "AMBUSH_SNATCHER_SUPPORT", wake = {"overseer"}, detail = "a thief-class ambush is underway; item loss is real but not fort-ending, worth the Overseer's attention at thinking speed rather than a full stop" },
  [85] = { name = "STRANGE_MOOD", wake = {"architect", "quartermaster"}, detail = "a mood has struck a citizen; needs a workshop and materials routed to them within a bounded window or it turns bad (insanity/death), so worth acting on soon but not an instant pause" },
  [91] = { name = "MOOD_BUILDING_CLAIMED", wake = {"quartermaster"}, detail = "a moody citizen has claimed a workshop; the Quartermaster needs to route materials to them" },
  [100] = { name = "MASTER_ARCHITECTURE_LOST", wake = {"overseer"}, detail = "a masterwork-tier structure was lost; a real, rare loss the Overseer should see soon but not a stop-the-world event" },
  [101] = { name = "MASTER_CONSTRUCTION_LOST", wake = {"overseer"}, detail = "a masterwork-tier structure was lost; a real, rare loss the Overseer should see soon but not a stop-the-world event" },
  [108] = { name = "ENDGAME_EVENT_1", wake = {"overseer"}, detail = "a world-tier endgame event is happening; rare and consequential enough to slow for, though this fort has never triggered one to verify against" },
  [109] = { name = "ENDGAME_EVENT_1B", wake = {"overseer"}, detail = "a world-tier endgame event is happening; rare and consequential enough to slow for, though this fort has never triggered one to verify against" },
  [110] = { name = "ENDGAME_EVENT_2", wake = {"overseer"}, detail = "a world-tier endgame event is happening; rare and consequential enough to slow for, though this fort has never triggered one to verify against" },
  [112] = { name = "CAUGHT_IN_FLAMES", wake = {"overseer"}, detail = "a unit is on fire or breathing fire; fast-developing physical harm, worth waking the Overseer even without a full pause since the outcome (a burn death) is already covered by the death tripwire once it happens" },
  [128] = { name = "BLOCK_FIRE", wake = {"overseer"}, detail = "a unit is on fire or breathing fire; fast-developing physical harm, worth waking the Overseer even without a full pause since the outcome (a burn death) is already covered by the death tripwire once it happens" },
  [129] = { name = "BREATHE_FIRE", wake = {"overseer"}, detail = "a unit is on fire or breathing fire; fast-developing physical harm, worth waking the Overseer even without a full pause since the outcome (a burn death) is already covered by the death tripwire once it happens" },
  [140] = { name = "FLAME_HIT", wake = {"overseer"}, detail = "a unit is on fire or breathing fire; fast-developing physical harm, worth waking the Overseer even without a full pause since the outcome (a burn death) is already covered by the death tripwire once it happens" },
  [151] = { name = "CITIZEN_MISSING", wake = {"overseer"}, detail = "a citizen is reported missing; could mean lost, trapped or dead off-screen, worth checking soon" },
  [153] = { name = "EMBRACE", wake = {"overseer"}, detail = "a vampire has embraced a victim; a subtle, hard-to-detect precursor threat worth a look though not urgent in ticks" },
  [154] = { name = "STRANGE_RAIN_SNOW", wake = {"overseer"}, detail = "an unnatural weather event (syndrome-carrying rain/cloud) is occurring; can injure or transform any citizen caught outside, worth a look at thinking speed" },
  [155] = { name = "STRANGE_CLOUD", wake = {"overseer"}, detail = "an unnatural weather event (syndrome-carrying rain/cloud) is occurring; can injure or transform any citizen caught outside, worth a look at thinking speed" },
  [181] = { name = "STRESSED_CITIZEN", wake = {"overseer"}, detail = "a citizen is stressed or tantruming; a precursor to CITIZEN_LOST_TO_STRESS/BERSERK_CITIZEN, worth the Overseer noticing before it escalates to a pause-worthy event" },
  [183] = { name = "CITIZEN_TANTRUM", wake = {"overseer"}, detail = "a citizen is stressed or tantruming; a precursor to CITIZEN_LOST_TO_STRESS/BERSERK_CITIZEN, worth the Overseer noticing before it escalates to a pause-worthy event" },
}

function is_pause_report(rtype)
  return PAUSE_REPORT_IDS[rtype] ~= nil
end

function is_slow_report(rtype)
  return SLOW_REPORT_IDS[rtype] ~= nil
end

-- Same module-load guard as every other df-overseer-*.lua script.
if dfhack_flags.module then
  return
end

local function sorted_ids(tbl)
  local ids = {}
  for id, _ in pairs(tbl) do table.insert(ids, id) end
  table.sort(ids)
  return ids
end

local args = {...}
local cmd = args[1]

if cmd == "pause-ids" then
  local out = {}
  for _, id in ipairs(sorted_ids(PAUSE_REPORT_IDS)) do
    table.insert(out, { id = id, name = PAUSE_REPORT_IDS[id] })
  end
  print(json.encode({ ids = out }))
elseif cmd == "slow-ids" then
  local out = {}
  for _, id in ipairs(sorted_ids(SLOW_REPORT_IDS)) do
    local info = SLOW_REPORT_IDS[id]
    table.insert(out, { id = id, name = info.name, wake = info.wake, detail = info.detail })
  end
  print(json.encode({ ids = out }))
elseif cmd == "level" then
  local id = tonumber(args[2])
  if PAUSE_REPORT_IDS[id] then
    print(json.encode({ id = id, level = "pause", name = PAUSE_REPORT_IDS[id] }))
  elseif SLOW_REPORT_IDS[id] then
    print(json.encode({ id = id, level = "slow", name = SLOW_REPORT_IDS[id].name, wake = SLOW_REPORT_IDS[id].wake, detail = SLOW_REPORT_IDS[id].detail }))
  else
    print(json.encode({ id = id, level = "not_pause_or_slow" }))
  end
else
  print("usage: df-overseer-announcement-levels <pause-ids|slow-ids|level TYPE_ID>")
end
