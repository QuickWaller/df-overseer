--@module = true
-- GENERATED from blueprints/room-kinds.yaml and blueprints/templates/*.yaml by
--   python -m dfqueue.room_kinds --write-lua
-- Do not edit by hand: a test fails when this differs from the YAML. The guest
-- has no YAML parser, which is the only reason this file exists.
--
-- Room kind data (register 2026-10-08, D1/D2/D5/D7): per kind its shape
-- generator, size range, required furniture, access rule, privacy and door
-- policy, keyed by the kind id the templates' `kind:` names. Read by
-- df-overseer-blueprint.lua (the placement gate) and df-overseer-circulation.lua.
-- Reqscript only; no CLI.

local DATA = {
  ["kinds"] = {
    ["barracks"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        5,
        10,
      },
      ["interior_width"] = {
        5,
        10,
      },
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 2,
          ["item"] = "bed",
        },
        {
          ["count"] = 1,
          ["item"] = "weapon_rack",
        },
        {
          ["count"] = 1,
          ["item"] = "armor_stand",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Barracks",
    },
    ["bedroom"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "door",
      ["door_ground"] = "user_standard",
      ["interior_depth"] = {
        3,
        3,
      },
      ["interior_width"] = {
        3,
        3,
      },
      ["private"] = true,
      ["required_furniture"] = {
        {
          ["count"] = 1,
          ["item"] = "bed",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Bedroom",
    },
    ["dining_hall"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        5,
        12,
      },
      ["interior_width"] = {
        5,
        12,
      },
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 1,
          ["item"] = "table",
        },
        {
          ["count"] = 1,
          ["item"] = "chair",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "DiningHall",
    },
    ["dormitory"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        4,
        8,
      },
      ["interior_width"] = {
        4,
        8,
      },
      ["private"] = true,
      ["required_furniture"] = {
        {
          ["count"] = 4,
          ["item"] = "bed",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Dormitory",
    },
    ["hospital"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        5,
        9,
      },
      ["interior_width"] = {
        5,
        9,
      },
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 2,
          ["item"] = "bed",
        },
        {
          ["count"] = 1,
          ["item"] = "table",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Hospital",
    },
    ["jail"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "door",
      ["door_ground"] = "access_control",
      ["interior_depth"] = {
        3,
        8,
      },
      ["interior_width"] = {
        3,
        8,
      },
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 1,
          ["item"] = "cage",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Dungeon",
    },
    ["library"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        4,
        10,
      },
      ["interior_width"] = {
        4,
        10,
      },
      ["location"] = "Library",
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 1,
          ["item"] = "bookcase",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "MeetingHall",
    },
    ["meeting_hall"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        5,
        12,
      },
      ["interior_width"] = {
        5,
        12,
      },
      ["private"] = false,
      ["required_furniture"] = {},
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "MeetingHall",
    },
    ["office"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        3,
        3,
      },
      ["interior_width"] = {
        3,
        3,
      },
      ["private"] = true,
      ["required_furniture"] = {
        {
          ["count"] = 1,
          ["item"] = "chair",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Office",
    },
    ["tavern"] = {
      ["access"] = {
        ["kinds"] = {
          "dining_hall",
        },
        ["mode"] = "opens_onto",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        5,
        12,
      },
      ["interior_width"] = {
        5,
        12,
      },
      ["location"] = "Tavern",
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 2,
          ["item"] = "table",
        },
        {
          ["count"] = 2,
          ["item"] = "chair",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "MeetingHall",
    },
    ["temple"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        4,
        10,
      },
      ["interior_width"] = {
        4,
        10,
      },
      ["location"] = "Temple",
      ["private"] = false,
      ["required_furniture"] = {},
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "MeetingHall",
    },
    ["tomb"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "any",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        1,
        3,
      },
      ["interior_width"] = {
        1,
        3,
      },
      ["private"] = false,
      ["required_furniture"] = {
        {
          ["count"] = 1,
          ["item"] = "coffin",
        },
      },
      ["shape_generator"] = "rectangular_room",
      ["zone_kind"] = "Tomb",
    },
    ["workshop_room"] = {
      ["access"] = {
        ["kinds"] = {},
        ["mode"] = "corridor",
      },
      ["door_default"] = "none",
      ["interior_depth"] = {
        3,
        9,
      },
      ["interior_width"] = {
        3,
        9,
      },
      ["private"] = false,
      ["required_furniture"] = {},
      ["shape_generator"] = "workshop_bay",
    },
  },
  ["template_kind"] = {
    ["bedroom-cell"] = "bedroom",
    ["office-room"] = "office",
  },
  ["zone_to_kind"] = {
    ["Barracks"] = "barracks",
    ["Bedroom"] = "bedroom",
    ["DiningHall"] = "dining_hall",
    ["Dormitory"] = "dormitory",
    ["Dungeon"] = "jail",
    ["Hospital"] = "hospital",
    ["MeetingHall"] = "meeting_hall",
    ["Office"] = "office",
    ["Tomb"] = "tomb",
  },
}

function data() return DATA end

-- The kind entry (with its id) for a kind id, or nil.
function kind(id)
  local k = DATA.kinds[id]
  if not k then return nil end
  local out = { id = id }
  for f, v in pairs(k) do out[f] = v end
  return out
end

-- The kind id of a blueprint name ("bedroom-cell-v1" or "bedroom-cell"), or nil.
function kind_of_blueprint(name)
  local base = tostring(name or ""):gsub("%-v%d+$", "")
  return DATA.template_kind[base]
end

-- The kind id for a df.civzone_type name (primary zone of a kind only), or nil.
function kind_of_zone(zone_kind)
  return DATA.zone_to_kind[zone_kind]
end

-- True if the kind id is private (nobody should walk through it).
function is_private(id)
  local k = DATA.kinds[id]
  return k ~= nil and k.private == true
end
