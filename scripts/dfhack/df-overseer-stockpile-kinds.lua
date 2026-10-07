-- df-overseer-stockpile-kinds.lua
--@module = true
--
-- HAND DATA for stockpile.health, stockpile.plan-feed and stockpile.link's
-- single-class trap warning (handoffs/2026-10-07-stockpile-tool-gaps.md item
-- 4/5). The per-workshop-kind input/output table is DERIVED AT RUNTIME from
-- the game's own job and reaction definitions (df-overseer-stockpile.lua's
-- derive_kind: dfhack.workshops.getJobs per kind, the same source
-- workjob.list-jobs reads, plus df.global.world.raws.reactions' products).
-- This file holds ONLY what the game does not encode, each section marked:
--
--   ITEM_TYPE_CATEGORIES -- df.item_type name -> the coarse stockpile
--       categories (df-overseer-stockpile.lua CATEGORY_NAMES) a pile must
--       accept to hold it. The game has this mapping inside its own stockpile
--       logic but exposes no table of it, so it is hand data. An item type
--       absent here is reported as `unmapped`, never guessed.
--   FLAG_CATEGORIES -- job_item flag name -> {categories, role} for tag-matched
--       reagents with no item_type (a still's "empty food storage container").
--   OVERLAYS -- classes the job definitions do not carry at all (a smelter's
--       fuel, optional when magma-fed).
--   OUTPUT_HINTS -- products of built-in jobs (a mason's blocks), which
--       DFHack's job table does not list; reaction products ARE derived.
--   FEEDER_TILES -- bounded line-side buffer sizes (research section 4).
--   FALLBACK_KINDS -- the previous hand-authored whole-kind table. Used ONLY
--       when runtime derivation fails for a kind (getJobs unavailable or
--       empty); the entry is then flagged source = "fallback_table". Also the
--       test fixture for the hand data. HAND-AUTHORED from the wiki, unverified.
--
-- Everything here is UNVERIFIED against a live fort until checked.

ITEM_TYPE_CATEGORIES = {
  BOULDER = {"stone"}, WOOD = {"wood"}, BAR = {"bars_blocks"}, BLOCKS = {"bars_blocks"},
  BARREL = {"furniture"}, BIN = {"furniture"}, BUCKET = {"furniture"}, BAG = {"furniture"},
  FLASK = {"furniture"}, POT = {"furniture"}, JUG = {"furniture"}, CAGE = {"furniture"},
  CHAIN = {"furniture"}, ROPE = {"furniture"}, TRAPPARTS = {"finished_goods"},
  DRINK = {"food"}, FOOD = {"food"}, PLANT = {"food"}, PLANT_GROWTH = {"food"},
  MEAT = {"food"}, FISH = {"food"}, CHEESE = {"food"}, SEEDS = {"food"}, EGG = {"food"},
  GLOB = {"refuse"}, BONE = {"refuse"}, SKIN_RAW = {"refuse"}, CORPSE = {"corpses"},
  CORPSEPIECE = {"refuse"}, SKIN_TANNED = {"leather"}, THREAD = {"cloth"}, CLOTH = {"cloth"},
  ROUGH = {"gems"}, SMALLGEM = {"gems"}, SHEET = {"sheet"}, COIN = {"coins"},
  FIGURINE = {"finished_goods"}, CRAFTS = {"finished_goods"}, TOY = {"finished_goods"},
  DOOR = {"furniture"}, TABLE = {"furniture"}, CHAIR = {"furniture"}, BED = {"furniture"},
  CABINET = {"furniture"}, COFFIN = {"furniture"}, STATUE = {"furniture"}, QUIVER = {"finished_goods"},
  WEAPON = {"weapons"}, ARMOR = {"armor"}, SHOES = {"armor"}, HELM = {"armor"},
  GLOVES = {"armor"}, PANTS = {"armor"}, SHIELD = {"armor"}, AMMO = {"ammo"},
}

FLAG_CATEGORIES = {
  -- availability: the items.other key stocks.availability is asked about; an
  -- APPROXIMATION for a tag-matched class (barrels are the usual food storage).
  food_storage = {categories = {"furniture"}, role = "container", availability = "BARREL"},
  -- `empty` is a qualifier on a container, not a class: deliberately absent.
}

-- Roles by item type for the types that are containers rather than ingredients.
CONTAINER_ITEM_TYPES = {BARREL = true, BIN = true, BUCKET = true, BAG = true,
                        FLASK = true, POT = true, JUG = true, CAGE = true}

FEEDER_TILES = {input = 4, container = 2, fuel = 4}

OVERLAYS = {
  Smelter = {
    {id = "fuel", label = "fuel (coal or charcoal)", role = "fuel",
     categories = {"bars_blocks"}, optional_when = "the smelter is fed by magma"},
  },
  GlassFurnace = {
    {id = "fuel", label = "fuel (coal or charcoal)", role = "fuel",
     categories = {"bars_blocks"}, optional_when = "the furnace is fed by magma"},
  },
  Kiln = {
    {id = "fuel", label = "fuel (coal or charcoal)", role = "fuel",
     categories = {"bars_blocks"}, optional_when = "the kiln is fed by magma"},
  },
  MetalsmithsForge = {
    {id = "fuel", label = "fuel (coal or charcoal)", role = "fuel",
     categories = {"bars_blocks"}, optional_when = "the forge is fed by magma"},
  },
}

FALLBACK_KINDS = {
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

-- Case-insensitive lookup in the FALLBACK table; returns (name, entry) or nil.
function find_fallback_kind(name)
  if not name then
    return nil
  end
  local want = tostring(name):lower()
  for k, entry in pairs(FALLBACK_KINDS) do
    if k:lower() == want then
      return k, entry
    end
  end
  return nil
end

-- Products of built-in (non-reaction) jobs: taken from the fallback table's
-- outputs, the only place they are written down.
OUTPUT_HINTS = {}
for k, entry in pairs(FALLBACK_KINDS) do
  OUTPUT_HINTS[k] = entry.outputs
end

if dfhack_flags and dfhack_flags.module then
  return
end
