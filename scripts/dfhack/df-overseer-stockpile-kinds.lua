-- df-overseer-stockpile-kinds.lua
--@module = true
--
-- DATA, not logic: the per-workshop-kind input/output table behind
-- stockpile.health, stockpile.plan-feed and stockpile.link's single-class
-- trap warning (handoffs/2026-10-07-stockpile-tool-gaps.md item 4/5;
-- research/2026-10-07-stockpile-logistics.md sections 1, 5, 7). Adding a
-- workshop kind is one entry here, no code change in
-- df-overseer-stockpile.lua.
--
-- PROVENANCE, honestly: HAND-AUTHORED from the DF wiki's Workshop and
-- Stockpile pages (research section 1: "a linked workshop needs a pile for
-- EVERY input class, including containers and fuel"). It is NOT derived from
-- the game's own reaction/job data: that derivation (production/extract.py
-- reads reaction files offline; no runtime DFHack read of "which item
-- classes does a job of this workshop need" was built) is future work, and
-- every entry is therefore UNVERIFIED against a live fort until checked
-- (`verified = false` on each, so a consumer can say so). Where a class
-- depends on game state rather than the workshop kind (a Smelter needs fuel
-- unless it is magma-fed), the class carries `optional_when`.
--
-- KEYS are the game's own subtype names (df.workshop_type[...] for a
-- Workshop, df.furnace_type[...] for a Furnace), the same names
-- df-overseer-building.lua's kind table calls its subtypes.
--
-- CLASS FIELDS:
--   id            -- stable token ("ore", "fuel", "barrel").
--   label         -- plain words for a report.
--   role          -- "input" | "container" | "fuel".
--   categories    -- the coarse stockpile categories (df-overseer-stockpile.lua
--                    CATEGORY_NAMES) a pile must accept to hold this class;
--                    a pile accepting ANY of them can source it.
--   availability  -- optional df.global.world.items.other key to ask
--                    stocks.availability about, fort-wide; absent when no
--                    single key fits.
--   feeder_tiles  -- plan-feed's suggested line-side buffer size: bounded,
--                    a few jobs' worth, not "as big as possible" (research
--                    section 4, kanban).
--   optional_when -- a short condition under which the class is not needed.
-- OUTPUTS: {id, label, categories} products; an output pile must accept at
-- least one category of EACH product it is expected to take.

KINDS = {
  Still = {
    verified = false,
    inputs = {
      {id = "plants", label = "brewable plants or fruit", role = "input",
       categories = {"food"}, availability = "PLANT", feeder_tiles = 4},
      {id = "barrel", label = "empty barrels", role = "container",
       categories = {"furniture"}, availability = "BARREL", feeder_tiles = 2},
    },
    outputs = {
      {id = "drink", label = "drink (in barrels)", categories = {"food"}},
    },
  },
  Kitchen = {
    verified = false,
    inputs = {
      {id = "ingredients", label = "cookable ingredients", role = "input",
       categories = {"food"}, feeder_tiles = 4},
    },
    outputs = {
      {id = "meals", label = "prepared meals", categories = {"food"}},
    },
  },
  Masons = {
    verified = false,
    inputs = {
      {id = "stone", label = "stone", role = "input",
       categories = {"stone"}, availability = "BOULDER", feeder_tiles = 4},
    },
    outputs = {
      {id = "blocks", label = "blocks", categories = {"bars_blocks"}},
      {id = "furniture", label = "stone furniture", categories = {"furniture"}},
    },
  },
  Carpenters = {
    verified = false,
    inputs = {
      {id = "wood", label = "logs", role = "input",
       categories = {"wood"}, availability = "WOOD", feeder_tiles = 4},
    },
    outputs = {
      {id = "furniture", label = "wooden furniture", categories = {"furniture"}},
      {id = "finished", label = "wooden goods", categories = {"finished_goods"}},
    },
  },
  Mechanics = {
    verified = false,
    inputs = {
      {id = "stone", label = "stone", role = "input",
       categories = {"stone"}, availability = "BOULDER", feeder_tiles = 2},
    },
    outputs = {
      {id = "mechanisms", label = "mechanisms and trap parts",
       categories = {"finished_goods", "weapons", "furniture"}},
    },
  },
  Craftsdwarfs = {
    verified = false,
    inputs = {
      {id = "material", label = "stone, wood, bone or other craft material",
       role = "input", categories = {"stone", "wood", "refuse", "leather", "cloth"},
       feeder_tiles = 4},
    },
    outputs = {
      {id = "crafts", label = "crafts and finished goods", categories = {"finished_goods"}},
    },
  },
  Butchers = {
    verified = false,
    inputs = {
      {id = "carcasses", label = "carcasses", role = "input",
       categories = {"corpses", "refuse"}, feeder_tiles = 4},
    },
    outputs = {
      {id = "meat", label = "meat, fat, bones and skin", categories = {"food", "refuse", "leather"}},
    },
  },
  Tanners = {
    verified = false,
    inputs = {
      {id = "hides", label = "raw hides", role = "input",
       categories = {"refuse"}, feeder_tiles = 4},
    },
    outputs = {
      {id = "leather", label = "leather", categories = {"leather"}},
    },
  },
  Leatherworks = {
    verified = false,
    inputs = {
      {id = "leather", label = "leather", role = "input",
       categories = {"leather"}, feeder_tiles = 4},
    },
    outputs = {
      {id = "goods", label = "leather goods", categories = {"finished_goods", "armor", "furniture"}},
    },
  },
  Smelter = {
    verified = false,
    inputs = {
      {id = "ore", label = "ore", role = "input",
       categories = {"stone"}, feeder_tiles = 4},
      {id = "fuel", label = "fuel (coal or charcoal)", role = "fuel",
       categories = {"bars_blocks"}, feeder_tiles = 4,
       optional_when = "the smelter is fed by magma"},
    },
    outputs = {
      {id = "bars", label = "metal bars", categories = {"bars_blocks"}},
    },
  },
  WoodFurnace = {
    verified = false,
    inputs = {
      {id = "logs", label = "logs", role = "input",
       categories = {"wood"}, availability = "WOOD", feeder_tiles = 4},
    },
    outputs = {
      {id = "charcoal", label = "charcoal and ash", categories = {"bars_blocks"}},
    },
  },
}

-- Case-insensitive lookup of a kind by name; returns (name, entry) or nil.
function find_kind(name)
  if not name then
    return nil
  end
  local want = tostring(name):lower()
  for k, entry in pairs(KINDS) do
    if k:lower() == want then
      return k, entry
    end
  end
  return nil
end

if dfhack_flags and dfhack_flags.module then
  return
end
