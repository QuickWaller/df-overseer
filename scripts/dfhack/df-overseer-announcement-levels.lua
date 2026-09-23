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
-- SLOW_REPORT_IDS (23 ids): NOT acted on by this repo's Lua side
-- at all (handoffs/2026-09-23-attention-tiers-ingame.md item 2: "not yours
-- to act on"). Exposed read-only, via the `slow-ids` CLI command below and
-- the `announcement-levels.slow-ids` MCP tool that command becomes
-- (scripts/dfhack/TOOLS.yaml), so the sibling conductor stream
-- (docs/AGENT-LOOP.md ss3's "wake the role named in wake, through
-- conductor/triage.py's existing machinery") can route them without this
-- stream touching conductor/. Field shape (also recorded in this stream's
-- handoff Result):
--   pause-ids -> {"ids": [{"id": N, "name": "..."}, ...]}
--   slow-ids  -> {"ids": [{"id": N, "name": "...", "wake": ["overseer", ...]}, ...]}

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

SLOW_REPORT_IDS = { -- id -> { name = ..., wake = {role, ...} }
  [55] = { name = "AMBUSH_THIEF", wake = {"overseer"} },
  [56] = { name = "AMBUSH_THIEF_SUPPORT_SKULKING", wake = {"overseer"} },
  [57] = { name = "AMBUSH_THIEF_SUPPORT_NATURE", wake = {"overseer"} },
  [58] = { name = "AMBUSH_THIEF_SUPPORT", wake = {"overseer"} },
  [59] = { name = "AMBUSH_MISCHIEVOUS", wake = {"overseer"} },
  [61] = { name = "AMBUSH_SNATCHER_SUPPORT", wake = {"overseer"} },
  [85] = { name = "STRANGE_MOOD", wake = {"architect", "quartermaster"} },
  [91] = { name = "MOOD_BUILDING_CLAIMED", wake = {"quartermaster"} },
  [100] = { name = "MASTER_ARCHITECTURE_LOST", wake = {"overseer"} },
  [101] = { name = "MASTER_CONSTRUCTION_LOST", wake = {"overseer"} },
  [108] = { name = "ENDGAME_EVENT_1", wake = {"overseer"} },
  [109] = { name = "ENDGAME_EVENT_1B", wake = {"overseer"} },
  [110] = { name = "ENDGAME_EVENT_2", wake = {"overseer"} },
  [112] = { name = "CAUGHT_IN_FLAMES", wake = {"overseer"} },
  [128] = { name = "BLOCK_FIRE", wake = {"overseer"} },
  [129] = { name = "BREATHE_FIRE", wake = {"overseer"} },
  [140] = { name = "FLAME_HIT", wake = {"overseer"} },
  [151] = { name = "CITIZEN_MISSING", wake = {"overseer"} },
  [153] = { name = "EMBRACE", wake = {"overseer"} },
  [154] = { name = "STRANGE_RAIN_SNOW", wake = {"overseer"} },
  [155] = { name = "STRANGE_CLOUD", wake = {"overseer"} },
  [181] = { name = "STRESSED_CITIZEN", wake = {"overseer"} },
  [183] = { name = "CITIZEN_TANTRUM", wake = {"overseer"} },
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
    table.insert(out, { id = id, name = info.name, wake = info.wake })
  end
  print(json.encode({ ids = out }))
elseif cmd == "level" then
  local id = tonumber(args[2])
  if PAUSE_REPORT_IDS[id] then
    print(json.encode({ id = id, level = "pause", name = PAUSE_REPORT_IDS[id] }))
  elseif SLOW_REPORT_IDS[id] then
    print(json.encode({ id = id, level = "slow", name = SLOW_REPORT_IDS[id].name, wake = SLOW_REPORT_IDS[id].wake }))
  else
    print(json.encode({ id = id, level = "not_pause_or_slow" }))
  end
else
  print("usage: df-overseer-announcement-levels <pause-ids|slow-ids|level TYPE_ID>")
end
