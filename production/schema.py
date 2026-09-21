"""The production schema: seven tables, DDL plus row validation.

Copied from `docs/PRODUCTION-MODEL.md` §4 verbatim (see that file for the
full rationale). Three corrections were load-bearing in the design pass and
must not be "simplified back" here:

1. **`material_reaction_product` exists** because 42% of product lines
   inherit their material from a reagent at job time
   (`GET_MATERIAL_FROM_REAGENT`), including every food and drink reaction.
   Without this table there is no way to emit a concrete node id for
   brewing (`research/2026-09-18-schema-extraction-static.md` §2).
2. **`consumption` has four values, not three.** `modified_in_place` is for
   the `[IMPROVEMENT]`-only reactions that have no `[PRODUCT]` line at all
   (the four `GLAZE_*` reactions) — see §1 of the same audit.
3. **`production_observation.abs_tick`** is `cur_year * 403200 +
   cur_year_tick`, never the bare tick, which resets annually
   (`docs/PRODUCTION-MODEL.md` §4, "Why `abs_tick` and not `tick`").

`production_process.labor` holds a `df.unit_labor` token (BREWER), **never** a
raws `[SKILL:...]` token (BREWING): the spec's "SKILL to labor" step needs a
table the raws do not carry. The extractor leaves it NULL and records the skill
as a `skill` attribute; `labor_ingest.py` fills it from the game's own tables
and records how in a `labor_basis` attribute (2026-09-21).

`production_process.capacity_theoretical` is deliberately absent: no file on
any read install states a job-time figure, and a column nothing can fill
invites a guess.

Every row carries `status` (one of `STATUS_VALUES`) and `source_ref` (the
file:line, or a documented construction rule, that the row's own values
trace back to). That pair is load-bearing, not decoration: it is what lets a
query degrade honestly instead of quietly mixing a raw-verified figure with
a guess.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

# ---- status vocabulary (docs/PRODUCTION-MODEL.md §4) --------------------------
#
# This is also the quadrant taxonomy (§3): Q1/Q2 raw-derived facts land as
# `verified_raws`, a wiki/community figure not yet checked against this
# install's raws is `prior`, an opportunistic live measurement is
# `measured`, and a figure no file states is `unavailable`. Q4 never gets a
# row at all, by construction — there is no fifth value for it.

VERIFIED_RAWS = "verified_raws"
PRIOR = "prior"
MEASURED = "measured"
UNAVAILABLE = "unavailable"
STATUS_VALUES = (VERIFIED_RAWS, PRIOR, MEASURED, UNAVAILABLE)

# ---- production_node.kind ------------------------------------------------------

KIND_PLANT = "plant"
KIND_ITEM_TYPE = "item_type"
KIND_MATERIAL = "material"
KIND_BUILDING = "building"
NODE_KINDS = (KIND_PLANT, KIND_ITEM_TYPE, KIND_MATERIAL, KIND_BUILDING)

DURABLE = "durable"
PERISHABLE = "perishable"
DURABILITY_VALUES = (DURABLE, PERISHABLE)

# ---- production_class.mechanism -------------------------------------------------
#
# `docs/PRODUCTION-MODEL.md` §4's inline SQL comment names three:
# `reaction_class | material_reaction_product | hardcoded_flag`. The static
# audit (§3) found class membership actually expressed through *more* than
# three raw mechanisms once container-class reagents are included:
# `FOOD_STORAGE_CONTAINER` is its own single-purpose ad hoc flag (raw
# author's own inline comment, not engine-hardcoded the way
# `ANY_PLANT_MATERIAL` is), and `HAS_TOOL_USE:LIQUID_CONTAINER` is a fourth,
# unrelated tool-use flag. Rather than force those into `hardcoded_flag`
# (which would misrepresent them as engine-matched rather than
# raw-authored), this module extends the vocabulary with two more values and
# flags the extension here — this is reported as a spec gap in the handoff
# write-up, not silently patched. `mechanism` has no `CHECK` constraint in
# the DDL (only `production_class.class` bears the "well, the DDL comment
# lists three" name), so nothing breaks; this constant list is the
# documented, honest superset.

MECH_REACTION_CLASS = "reaction_class"
MECH_MATERIAL_REACTION_PRODUCT = "material_reaction_product"
MECH_HARDCODED_FLAG = "hardcoded_flag"
MECH_AD_HOC_FLAG = "ad_hoc_flag"           # FOOD_STORAGE_CONTAINER
MECH_TOOL_USE_FLAG = "tool_use_flag"       # HAS_TOOL_USE:LIQUID_CONTAINER
MECH_ITEM_TYPE_ONLY = "item_type_only"     # bag/bucket: bare item type, no class token at all
CLASS_MECHANISMS = (
    MECH_REACTION_CLASS, MECH_MATERIAL_REACTION_PRODUCT, MECH_HARDCODED_FLAG,
    MECH_AD_HOC_FLAG, MECH_TOOL_USE_FLAG, MECH_ITEM_TYPE_ONLY,
)

# ---- material_reaction_product.token_family --------------------------------
#
# The unresolved `BAG_ITEM` inconsistency (spec §6, audit §3):
# `PROCESS_PLANT_TO_BAG` filters on `HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM`
# while quarry bush declares `ITEM_REACTION_PRODUCT:BAG_ITEM`, a different
# token family with the same name. Recorded so a query can see the mismatch
# rather than an extractor silently matching (or silently dropping) across
# families. Deliberately not resolved here — see `extract.py`.

FAMILY_MATERIAL_REACTION_PRODUCT = "material_reaction_product"
FAMILY_ITEM_REACTION_PRODUCT = "item_reaction_product"
TOKEN_FAMILIES = (FAMILY_MATERIAL_REACTION_PRODUCT, FAMILY_ITEM_REACTION_PRODUCT)

# ---- production_flow.direction --------------------------------------------------

REAGENT = "reagent"
PRODUCT = "product"
FLOW_DIRECTIONS = (REAGENT, PRODUCT)

# ---- production_flow.unit -------------------------------------------------------

UNIT_UNITS = "units"
UNIT_STACKS = "stacks"
UNIT_VOLUME = "volume"
FLOW_UNITS = (UNIT_UNITS, UNIT_STACKS, UNIT_VOLUME)

UNIT_SOURCE_PRODUCT_DIMENSION = "product_dimension"
UNIT_SOURCE_ITEM_SIZE_LOOKUP = "item_size_lookup"
UNIT_SOURCE_ABSENT = "absent"
UNIT_SOURCES = (
    UNIT_SOURCE_PRODUCT_DIMENSION, UNIT_SOURCE_ITEM_SIZE_LOOKUP, UNIT_SOURCE_ABSENT,
)

# ---- production_flow.consumption: four outcomes, not three ---------------------
#
# docs/PRODUCTION-MODEL.md §5. Derivation lives in `extract.derive_consumption`;
# this module only names the closed vocabulary.

CONSUMED = "consumed"
OCCUPIED_UNTIL_RELEASED = "occupied_until_released"
OCCUPIED_JOB = "occupied_job"
MODIFIED_IN_PLACE = "modified_in_place"
CONSUMPTION_VALUES = (CONSUMED, OCCUPIED_UNTIL_RELEASED, OCCUPIED_JOB, MODIFIED_IN_PLACE)

# ---- production_observation.metric (open-ended; a starter vocabulary) ----------

METRIC_STOCK = "stock"
METRIC_QUEUE_DEPTH = "queue_depth"
METRIC_POPULATION = "population"
METRIC_JOB_DURATION = "job_duration"
METRIC_TILES_OCCUPIED = "tiles_occupied"
OBSERVATION_METRICS = (
    METRIC_STOCK, METRIC_QUEUE_DEPTH, METRIC_POPULATION, METRIC_JOB_DURATION,
    METRIC_TILES_OCCUPIED,
)

# ---- abs_tick (docs/PRODUCTION-MODEL.md §4/§11) ---------------------------------

TICKS_PER_YEAR = 403200


def abs_tick(cur_year: int, cur_year_tick: int) -> int:
    """`cur_year * 403200 + cur_year_tick`. Never use the bare tick
    (`cur_year_tick` alone, or DFHack's `ReadCurrentTick()`) as a row key or
    a sort key: it resets to 0 every year, so two observations a full year
    apart with the same `cur_year_tick` would otherwise collide and any rate
    computed across the boundary would be silently wrong. Verified live
    against Uniboslan (227160 of 403200 at time of writing)."""
    if isinstance(cur_year, bool) or not isinstance(cur_year, int):
        raise TypeError(f"cur_year must be an int, got {cur_year!r}")
    if isinstance(cur_year_tick, bool) or not isinstance(cur_year_tick, int):
        raise TypeError(f"cur_year_tick must be an int, got {cur_year_tick!r}")
    if not (0 <= cur_year_tick < TICKS_PER_YEAR):
        raise ValueError(
            f"cur_year_tick must be in [0, {TICKS_PER_YEAR}), got {cur_year_tick!r}"
        )
    return cur_year * TICKS_PER_YEAR + cur_year_tick


# ---- DDL, copied verbatim from docs/PRODUCTION-MODEL.md §4 ---------------------

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- Items, materials and buildings.
CREATE TABLE IF NOT EXISTS production_node (
  id            TEXT PRIMARY KEY,  -- item type x material, e.g. 'DRINK:PLUMP_HELMET_WINE'
  kind          TEXT NOT NULL,     -- plant | item_type | material | building
  display_name  TEXT NOT NULL,
  durability    TEXT,              -- durable | perishable; splits days of cover
  status        TEXT NOT NULL,
  source_ref    TEXT NOT NULL
);

-- Class membership. Reagents point at a class, products at a specific node.
CREATE TABLE IF NOT EXISTS production_class (
  node_id   TEXT NOT NULL REFERENCES production_node(id),
  class     TEXT NOT NULL,         -- DRINK, FOOD_STORAGE_CONTAINER, BREWABLE_PLANT
  mechanism TEXT NOT NULL,         -- reaction_class | material_reaction_product | hardcoded_flag | ...
  source_ref TEXT NOT NULL
);

-- CORRECTED, and the reason extraction needs two passes. 42% of product lines
-- inherit their material from a reagent at job time
-- (GET_MATERIAL_FROM_REAGENT), including every food and drink reaction. The
-- concrete ids are not on the reaction line; they are on the material.
CREATE TABLE IF NOT EXISTS material_reaction_product (
  material_id  TEXT NOT NULL,      -- e.g. the plump helmet structural material
  token        TEXT NOT NULL,      -- e.g. 'DRINK_MAT', 'SEED_MAT', 'BAG_ITEM'
  result_node  TEXT NOT NULL,      -- the concrete node this yields
  token_family TEXT NOT NULL,      -- material_reaction_product | item_reaction_product
  source_ref   TEXT NOT NULL
);

-- One row per reaction, or per hardcoded job type.
CREATE TABLE IF NOT EXISTS production_process (
  id            TEXT PRIMARY KEY,  -- reaction code, e.g. 'BREW_DRINK_FROM_PLANT'
  workshop_node TEXT REFERENCES production_node(id),
  labor         TEXT,
  is_hardcoded  INTEGER NOT NULL DEFAULT 0,
  source_ref    TEXT NOT NULL
);
-- NOTE: capacity_theoretical was designed here and is DELIBERATELY ABSENT.
-- No job-time figure exists in the raws, in DFHack's docs, or on the wiki. A
-- column nothing can fill invites a guess.

-- The N-in, M-out edges.
CREATE TABLE IF NOT EXISTS production_flow (
  process_id   TEXT NOT NULL REFERENCES production_process(id),
  direction    TEXT NOT NULL,      -- reagent | product
  node_id      TEXT,               -- a class for reagents, a node for products; NULL if parametric before pass 2
  quantity     INTEGER,
  unit         TEXT,               -- units | stacks | volume
  unit_source  TEXT NOT NULL,      -- product_dimension | item_size_lookup | absent
  consumption  TEXT,               -- see PRODUCTION-MODEL.md #5; reagents only
  probability  INTEGER NOT NULL DEFAULT 100,
  container_class TEXT,
  status       TEXT NOT NULL,
  source_ref   TEXT NOT NULL
);

-- One row per fact, so a prior can be promoted without a migration.
CREATE TABLE IF NOT EXISTS production_attribute (
  subject_id TEXT NOT NULL,        -- a node or a process
  name       TEXT NOT NULL,        -- growdur | valid_seasons | capacity | density | value
  value      TEXT NOT NULL,
  unit       TEXT,
  status     TEXT NOT NULL,
  source_ref TEXT NOT NULL
);

-- The time series. Every rate in this design needs two of these rows.
CREATE TABLE IF NOT EXISTS production_observation (
  abs_tick    INTEGER NOT NULL,    -- CORRECTED: cur_year * 403200 + cur_year_tick
  subject_id  TEXT NOT NULL,       -- a node, process, workshop, stockpile, or 'fort'
  metric      TEXT NOT NULL,       -- stock | queue_depth | population | job_duration | tiles_occupied
  value       REAL NOT NULL,
  unit        TEXT,
  skill_level INTEGER,             -- REQUIRED for job_duration, or the figure rots
  status      TEXT NOT NULL,
  source_ref  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flow_process ON production_flow(process_id);
CREATE INDEX IF NOT EXISTS idx_class_node ON production_class(node_id);
CREATE INDEX IF NOT EXISTS idx_mrp_token ON material_reaction_product(token, token_family);
CREATE INDEX IF NOT EXISTS idx_attribute_subject ON production_attribute(subject_id);
CREATE INDEX IF NOT EXISTS idx_observation_subject_tick ON production_observation(subject_id, abs_tick);
"""

REPO_ROOT = Path(__file__).resolve().parent.parent


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif row[0] != SCHEMA_VERSION:
        raise ValueError(
            f"database is schema_version {row[0]}, this code is {SCHEMA_VERSION}"
        )


# ---- row validation ------------------------------------------------------------
#
# Not a queue accepting untrusted agent writes (unlike dfqueue's
# `validate()`); this is the extractor's own sanity check on rows it is
# about to write, so a bug in `extract.py` fails loudly instead of writing a
# row with an out-of-vocabulary status into the database. Kept proportionate
# to that job: closed-vocabulary and required-field checks, no coordinate
# scan (this schema has no free-text field a coordinate could hide in, and
# no place for one — docs/PRODUCTION-MODEL.md §16).


def _require(record: dict, fields: tuple, errors: list[str]) -> None:
    for f in fields:
        if f not in record or record[f] is None:
            errors.append(f"{f}: required field is missing")


def validate_node(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("id", "kind", "display_name", "status", "source_ref"), errors)
    if row.get("kind") is not None and row["kind"] not in NODE_KINDS:
        errors.append(f"kind: {row['kind']!r} is not in {NODE_KINDS}")
    if row.get("status") is not None and row["status"] not in STATUS_VALUES:
        errors.append(f"status: {row['status']!r} is not in {STATUS_VALUES}")
    dur = row.get("durability")
    if dur is not None and dur not in DURABILITY_VALUES:
        errors.append(f"durability: {dur!r} is not in {DURABILITY_VALUES}")
    return errors


def validate_class(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("node_id", "class", "mechanism", "source_ref"), errors)
    if row.get("mechanism") is not None and row["mechanism"] not in CLASS_MECHANISMS:
        errors.append(f"mechanism: {row['mechanism']!r} is not in {CLASS_MECHANISMS}")
    return errors


def validate_material_reaction_product(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("material_id", "token", "result_node", "token_family", "source_ref"), errors)
    fam = row.get("token_family")
    if fam is not None and fam not in TOKEN_FAMILIES:
        errors.append(f"token_family: {fam!r} is not in {TOKEN_FAMILIES}")
    return errors


def validate_process(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("id", "source_ref"), errors)
    hc = row.get("is_hardcoded", 0)
    if hc not in (0, 1):
        errors.append(f"is_hardcoded: expected 0 or 1, got {hc!r}")
    return errors


def validate_flow(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("process_id", "direction", "unit_source", "status", "source_ref"), errors)
    if row.get("direction") is not None and row["direction"] not in FLOW_DIRECTIONS:
        errors.append(f"direction: {row['direction']!r} is not in {FLOW_DIRECTIONS}")
    unit = row.get("unit")
    if unit is not None and unit not in FLOW_UNITS:
        errors.append(f"unit: {unit!r} is not in {FLOW_UNITS}")
    unit_source = row.get("unit_source")
    if unit_source is not None and unit_source not in UNIT_SOURCES:
        errors.append(f"unit_source: {unit_source!r} is not in {UNIT_SOURCES}")
    consumption = row.get("consumption")
    if row.get("direction") == PRODUCT and consumption is not None:
        errors.append("consumption: must be null for a product row (reagents only)")
    if row.get("direction") == REAGENT and consumption is not None and consumption not in CONSUMPTION_VALUES:
        errors.append(f"consumption: {consumption!r} is not in {CONSUMPTION_VALUES}")
    status = row.get("status")
    if status is not None and status not in STATUS_VALUES:
        errors.append(f"status: {status!r} is not in {STATUS_VALUES}")
    if row.get("node_id") is None and status not in (UNAVAILABLE, None):
        # A NULL node_id before pass 2, or one pass 2 never resolved, should
        # read honestly as unavailable rather than any other status.
        errors.append(
            f"status: node_id is NULL but status is {status!r}, expected {UNAVAILABLE!r}"
        )
    return errors


def validate_attribute(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("subject_id", "name", "value", "status", "source_ref"), errors)
    if row.get("status") is not None and row["status"] not in STATUS_VALUES:
        errors.append(f"status: {row['status']!r} is not in {STATUS_VALUES}")
    return errors


def validate_observation(row: dict) -> list[str]:
    errors: list[str] = []
    _require(row, ("abs_tick", "subject_id", "metric", "value", "status", "source_ref"), errors)
    if row.get("metric") is not None and row["metric"] not in OBSERVATION_METRICS:
        errors.append(f"metric: {row['metric']!r} is not in {OBSERVATION_METRICS}")
    if row.get("status") is not None and row["status"] not in STATUS_VALUES:
        errors.append(f"status: {row['status']!r} is not in {STATUS_VALUES}")
    if row.get("metric") == METRIC_JOB_DURATION and row.get("skill_level") is None:
        errors.append("skill_level: required for metric='job_duration', or the figure rots")
    return errors
