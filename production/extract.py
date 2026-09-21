"""The two-pass extractor: raws in, `production` schema rows out.

`docs/PRODUCTION-MODEL.md` §6:

**Pass 1, parse.** Read the reaction files, the plant file, the material
template file and the item-tool file. Emit processes, flows, attributes and
classes. Flows whose product material is parametric
(`GET_MATERIAL_FROM_REAGENT`, `GET_ITEM_DATA_FROM_REAGENT`) are written with
`node_id` NULL.

**Pass 2, materialise.** For each parametric flow, join the reagent's own
class filter against `material_reaction_product` to enumerate the concrete
nodes, then expand one flow row into N. One brewing recipe becomes five
drinks.

## Fixture provenance, and why this file is not a full DF raw parser

This offline stream has no VM, no SSH, no DFHack, no fort
(`handoffs/2026-09-18-production-package.md`), and no raws mirror exists
anywhere in this repo. `research/2026-09-18-schema-extraction-static.md`
already did a real, read-only, line-cited audit of the four shipped
reaction files, the plant file, `material_template_default.txt` and
`item_tool.txt` on VM 103's actual install. `production/tests/fixtures/`
is built from **that audit's own verbatim quotes** wherever one exists
(each fixture file's header records exactly which lines are direct quotes,
citing the audit's own file:line, versus which lines are structural
scaffolding this stream authored to make a genuine token parseable in a
small file). See `production/tests/fixtures/PROVENANCE.md` for the full
per-file breakdown; this is reported in the handoff write-up, not buried.

Because the fixtures are a small hand-assembled subset rather than the full
159-reaction corpus, this parser is intentionally narrow: it handles the
token shapes the audit actually verified (REAGENT/PRODUCT positional
fields, the reagent-side class-filter flags, PRODUCT_TO_CONTAINER,
PRODUCT_DIMENSION, GET_MATERIAL_FROM_REAGENT/GET_ITEM_DATA_FROM_REAGENT,
MATERIAL_REACTION_PRODUCT/ITEM_REACTION_PRODUCT, ROTS, SIZE,
CONTAINER_CAPACITY) and does not claim to parse every token family DF's raw
format supports.

## 2026-09-19: run against the real 159-reaction corpus for the first time

The above was all true of this file until 2026-09-19: fully tested, never
run against real data. That stream (`handoffs/2026-09-19-real-corpus-
extraction.md`) had the real corpus (read-only, pulled from VM 103 into a
session scratchpad, never committed here) and found several real token
shapes the fixture subset had no way to exercise -- a second "no value"
sentinel (`NO_SUBTYPE` alongside `NONE`), a DF reagent shorthand that
collapses distinct ore/material reagents into one class if read naively
(`METAL_ORE:<material>`), `GET_ITEM_DATA_FROM_REAGENT` sitting in the item-
type position instead of the material-source position, the *real*
`MATERIAL_REACTION_PRODUCT` argument shape (no item type at all -- pass2
now supplies it from the reaction's own PRODUCT line), and reaction-level
tokens (`NAME`, `CATEGORY*`) that were being silently misattributed rather
than dropped or captured. All fixed here; see `research/2026-09-19-real-
corpus-extraction.md` for the full findings and the real coverage table.
The fixtures and the tests built on them are untouched and still pass --
this section is the honesty update the file above asked for once real data
became available.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from . import store

FIXTURES_DIR = Path(__file__).resolve().parent / "tests" / "fixtures"

_TOKEN_RE = re.compile(r"\[([^\[\]]+)\]")

# ---- generic raw tokenizer ------------------------------------------------------


def _iter_tokens(text: str):
    """Yield (line_no, token_name, args) for every `[TOKEN:arg:arg...]` in
    file order. Free text outside brackets (including inline human comments
    like `reaction_other.txt:273`'s "barrel or any non-absorbing tool with
    FOOD_STORAGE") is real DF raw-format behaviour, confirmed by the audit,
    and is simply skipped here, the same way DF's own parser ignores it."""
    for m in _TOKEN_RE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        parts = m.group(1).split(":")
        yield line_no, parts[0], parts[1:]


def _to_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# Real-corpus finding, 2026-09-19: the fixtures (all effectively drawn from
# reaction_other.txt) only ever used "NONE" as the no-value sentinel for a
# subtype/mat-category slot. reaction_smelter.txt uses a SECOND, different
# sentinel, "NO_SUBTYPE", for the identical purpose (e.g. real
# `[REAGENT:A:1:BOULDER:NO_SUBTYPE:INORGANIC:COAL_BITUMINOUS]`,
# `[PRODUCT:100:9:BAR:NO_SUBTYPE:COAL:COKE]`). Before this fix, every one of
# the 23 smelter-file product node ids carried a spurious literal
# ":NO_SUBTYPE:" segment (e.g. "BAR:NO_SUBTYPE:COAL" instead of "BAR:COAL"),
# silently marked verified_raws. Treat both sentinels, and a bare None,
# as "no value" everywhere a "no value" check is made.
_NONE_TOKENS = (None, "NONE", "NO_SUBTYPE")


def _is_none(v) -> bool:
    return v in _NONE_TOKENS


# ---- pass 1a: reaction files -----------------------------------------------------

_SEASON_FLAGS = {"SPRING", "SUMMER", "AUTUMN", "WINTER"}


def parse_reactions(text: str, source_path: str) -> list[dict]:
    """Group a reaction file's tokens into one dict per `[REACTION:...]`
    block, each carrying its reagents and products with their own sub-flags
    attached. A reaction with `[ADVENTURE_MODE_ENABLED]` and no `[BUILDING]`
    is an adventurer-mode-only craft, not a fortress-mode process (audit
    §5: 11 of 159 reactions, all confirmed this way) -- flagged with
    `adventure_mode=True` here; the caller filters these out."""
    reactions: list[dict] = []
    cur: dict | None = None
    cur_reagent: dict | None = None
    cur_product: dict | None = None

    for line_no, name, args in _iter_tokens(text):
        if name == "REACTION":
            if cur is not None:
                reactions.append(cur)
            cur = {
                "id": args[0] if args else None,
                "line": line_no,
                "source_path": source_path,
                "buildings": [],
                "skill": None,
                "adventure_mode": False,
                "name": None,
                "category": None,
                "category_name": None,
                "category_description": None,
                "reagents": [],
                "products": [],
                "unparsed": [],
            }
            cur_reagent = cur_product = None
            continue
        if cur is None:
            continue  # a token before any [REACTION:...] (e.g. [OBJECT:REACTION])

        if name == "BUILDING":
            cur["buildings"].append(args[0] if args else None)
        elif name == "SKILL":
            cur["skill"] = args[0] if args else None
        elif name == "ADVENTURE_MODE_ENABLED":
            cur["adventure_mode"] = True
        elif name == "NAME":
            # Present on every one of the 159 real reactions, always before
            # any REAGENT/PRODUCT opens. Before this fix it fell into the
            # generic catch-all with no reagent/product yet open, so it was
            # silently dropped every single time -- the highest-volume
            # instance of exactly the "parser silently ignored a line"
            # failure mode this stream was asked to hunt for. Captured as
            # an attribute now, same treatment as CATEGORY below.
            cur["name"] = ":".join(args) if args else None
        elif name == "CATEGORY":
            # Real-corpus finding, 2026-09-19: CATEGORY/CATEGORY_NAME/
            # CATEGORY_DESCRIPTION are reaction-level UI-grouping tokens
            # (98/159 real reactions carry one, e.g. reaction_dyes.txt's
            # `[CATEGORY:MAKE_DYE]`), but they sit textually AFTER the last
            # [REAGENT:...]/[PRODUCT:...] block, once SKILL has already run.
            # Before this fix, the catch-all "attach to whichever
            # reagent/product is currently open" branch below silently
            # misattributed every one of them onto the LAST-parsed
            # product's (or reagent's) own flags list -- never corrupting a
            # read field, since nothing else reads a "CATEGORY" flag, but
            # real per-reaction metadata was being lost/mislabelled rather
            # than captured. Recognised explicitly here instead.
            cur["category"] = args[0] if args else None
        elif name == "CATEGORY_NAME":
            cur["category_name"] = ":".join(args) if args else None
        elif name == "CATEGORY_DESCRIPTION":
            # Free prose; rejoin on ':' in case the description text itself
            # contains one (none do in the 2026-09-19 corpus, verified, but
            # a bare args[0] would silently truncate one that did).
            cur["category_description"] = ":".join(args) if args else None
        elif name == "REAGENT":
            cur_reagent = {
                "name": args[0] if len(args) > 0 else None,
                "quantity": args[1] if len(args) > 1 else None,
                "item_type": args[2] if len(args) > 2 else None,
                "subtype": args[3] if len(args) > 3 else None,
                "mat_category": args[4] if len(args) > 4 else None,
                "mat_args": args[5:],
                "flags": [],
                "line": line_no,
            }
            cur["reagents"].append(cur_reagent)
            cur_product = None
        elif name == "PRODUCT":
            cur_product = {
                "probability": args[0] if len(args) > 0 else None,
                "quantity": args[1] if len(args) > 1 else None,
                "item_type": args[2] if len(args) > 2 else None,
                "subtype": args[3] if len(args) > 3 else None,
                "mat_source_type": args[4] if len(args) > 4 else None,
                "mat_args": args[5:],
                "container_target": None,
                "dimension": None,
                "flags": [],
                "line": line_no,
            }
            cur["products"].append(cur_product)
            cur_reagent = None
        elif name == "PRODUCT_TO_CONTAINER":
            if cur_product is not None:
                cur_product["container_target"] = args[0] if args else None
        elif name == "PRODUCT_DIMENSION":
            if cur_product is not None:
                cur_product["dimension"] = args[0] if args else None
        else:
            # A bare flag or class token (PRESERVE_REAGENT, EMPTY,
            # REACTION_CLASS, HAS_MATERIAL_REACTION_PRODUCT, NOT_IMPROVED,
            # HAS_TOOL_USE, FOOD_STORAGE_CONTAINER, ANY_PLANT_MATERIAL, ...)
            # attaches to whichever reagent/product sub-record is currently
            # open, matching how these tokens sit directly under a
            # [REAGENT:...] or [PRODUCT:...] line in the real files.
            target = cur_product if cur_product is not None else cur_reagent
            if target is not None:
                target["flags"].append((name, args))
            else:
                # Orphaned: a bare token with neither a reagent nor a
                # product currently open to attach to (and not one of the
                # reaction-level tokens recognised above). Before this fix
                # nothing recorded this case at all -- it just vanished.
                # Report it rather than silently dropping it; a caller can
                # decide whether it matters.
                cur["unparsed"].append({
                    "reaction_id": cur["id"], "token": name, "args": args,
                    "line": line_no, "reason": "no open reagent/product to attach to",
                })
    if cur is not None:
        reactions.append(cur)
    return reactions


# ---- pass 1b: plant file ----------------------------------------------------------


def parse_plants(text: str, source_path: str) -> list[dict]:
    """One dict per `[PLANT:...]` block.

    Real-corpus finding, 2026-09-19: `mrp` (`MATERIAL_REACTION_PRODUCT`)
    entries do NOT carry an item type at all. The real shape, confirmed
    across all 179 real occurrences in `vanilla_plants/objects/`, is
    exactly 3 args, `token:mat_type:mat_name`
    (e.g. `[MATERIAL_REACTION_PRODUCT:DRINK_MAT:LOCAL_PLANT_MAT:DRINK]`,
    `plant_standard.txt:13`) -- `mat_type` is a material-lookup family
    (`LOCAL_PLANT_MAT` in every real occurrence read this session: "look
    at this plant's own material list"), and `mat_name` is the *name of a
    material local to this same plant* (here, the one declared by this
    plant's own `[USE_MATERIAL_TEMPLATE:DRINK:PLANT_ALCOHOL_TEMPLATE]`),
    not an item type and not a fabricated node suffix. This stream's
    predecessor (offline, no VM) never saw a real MRP line and used its own
    invented 3-arg form, `token:item_type:node_suffix`
    (`production/tests/fixtures/plant_standard.txt`, e.g.
    `DRINK_MAT:DRINK:PLUMP_HELMET_WINE`) -- coincidentally also 3 args, so
    the shape looked plausible, but positions 2 and 3 meant something else
    entirely. The concrete item a token resolves to is only known once a
    *reaction's own* `[PRODUCT:...]` line is read (its item type, e.g.
    `DRINK` vs `SEEDS`, is NOT reproduced by the MRP line: compare
    `MATERIAL_REACTION_PRODUCT:SEED_MAT:LOCAL_PLANT_MAT:SEED` (mat_name
    "SEED", singular) against the real product line's own item type
    `SEEDS` (plural) -- proof the two are different vocabularies, not the
    same string reused). See `pass2` for where the item type actually gets
    combined with what this function resolves.

    `irp` (`ITEM_REACTION_PRODUCT`) is a different token family with a
    different, longer real shape: `token:item_type:item_subtype:mat_type:
    mat_name` (5 args -- confirmed by the corpus's one real occurrence,
    quarry bush's `[ITEM_REACTION_PRODUCT:BAG_ITEM:PLANT_GROWTH:LEAVES:
    LOCAL_PLANT_MAT:LEAF]`, `plant_standard.txt:223`). Unlike MRP, IRP DOES
    carry its own item type, so its result node is fully knowable right
    here, needing no reaction. The committed fixture
    (`production/tests/fixtures/plant_standard.txt`) still encodes the
    predecessor stream's invented 3-arg IRP form
    (`token:item_type:node_suffix`); fixtures are frozen (this handoff:
    "do not modify `production/tests/fixtures/**` at all"), so both the
    3-arg legacy shape and the 5-arg real shape are accepted here, tagged
    by which one fired. A shape matching neither is recorded as unparsed
    rather than silently guessed at.
    """
    plants: list[dict] = []
    cur: dict | None = None
    for line_no, name, args in _iter_tokens(text):
        if name == "PLANT":
            if cur is not None:
                plants.append(cur)
            cur = {
                "id": args[0] if args else None,
                "line": line_no,
                "source_path": source_path,
                "growdur": None,
                "seasons": [],
                "plant_value": None,
                "material_value": None,
                "mrp": [],
                "irp": [],
                "unparsed": [],
            }
            continue
        if cur is None:
            continue
        if name == "GROWDUR":
            cur["growdur"] = args[0] if args else None
        elif name in _SEASON_FLAGS:
            cur["seasons"].append(name)
        elif name == "VALUE":
            cur["plant_value"] = args[0] if args else None
        elif name == "MATERIAL_VALUE":
            cur["material_value"] = args[0] if args else None
        elif name == "MATERIAL_REACTION_PRODUCT":
            if len(args) == 3:
                cur["mrp"].append({
                    "token": args[0], "mat_type": args[1], "mat_name": args[2],
                    "line": line_no,
                })
            else:
                cur["unparsed"].append({
                    "plant_id": cur["id"], "token": name, "args": args, "line": line_no,
                    "reason": f"expected exactly 3 args (token:mat_type:mat_name), got {len(args)}",
                })
        elif name == "ITEM_REACTION_PRODUCT":
            if len(args) == 5:
                cur["irp"].append({
                    "token": args[0], "item_type": args[1], "item_subtype": args[2],
                    "mat_type": args[3], "mat_name": args[4], "line": line_no, "shape": "real_5arg",
                })
            elif len(args) == 3:
                # Legacy fixture-only shape (token:item_type:node_suffix) --
                # kept solely because the committed, frozen fixture still
                # uses it. No real corpus line has 3 args for this token.
                cur["irp"].append({
                    "token": args[0], "item_type": args[1], "item_subtype": None,
                    "mat_type": None, "mat_name": args[2], "line": line_no, "shape": "legacy_3arg",
                })
            else:
                cur["unparsed"].append({
                    "plant_id": cur["id"], "token": name, "args": args, "line": line_no,
                    "reason": f"expected 3 (legacy) or 5 (real) args, got {len(args)}",
                })
    if cur is not None:
        plants.append(cur)
    return plants


# ---- pass 1c: material templates ---------------------------------------------------


def parse_material_templates(text: str, source_path: str) -> dict:
    """`{template_name: {"rots": bool, "line": int, "source_path": str}}`.
    `[ROTS]` lives on the material template, never on an item or plant
    definition directly (audit §6, `material_template_default.txt`)."""
    templates: dict = {}
    cur_name: str | None = None
    for line_no, name, args in _iter_tokens(text):
        if name == "MATERIAL_TEMPLATE":
            cur_name = args[0] if args else None
            if cur_name:
                templates[cur_name] = {"rots": False, "line": line_no, "source_path": source_path}
        elif name == "ROTS" and cur_name:
            templates[cur_name]["rots"] = True
    return templates


# ---- pass 1d: item tools -----------------------------------------------------------


def parse_item_tools(text: str, source_path: str) -> dict:
    """`{tool_name: {"size", "container_capacity", "value", "line", "source_path"}}`.
    `ITEM_TOOL_WHEELBARROW`/`ITEM_TOOL_MINECART` are the audit's "two free
    wins" (§8): both blocks were quoted verbatim and promote straight to
    `verified_raws`."""
    tools: dict = {}
    cur_name: str | None = None
    for line_no, name, args in _iter_tokens(text):
        if name == "ITEM_TOOL":
            cur_name = args[0] if args else None
            if cur_name:
                tools[cur_name] = {
                    "size": None, "container_capacity": None, "value": None,
                    "line": line_no, "source_path": source_path,
                }
        elif cur_name is None:
            continue
        elif name == "SIZE":
            tools[cur_name]["size"] = args[0] if args else None
        elif name == "CONTAINER_CAPACITY":
            tools[cur_name]["container_capacity"] = args[0] if args else None
        elif name == "VALUE":
            tools[cur_name]["value"] = args[0] if args else None
    return tools


# ---- consumption derivation (docs/PRODUCTION-MODEL.md #5) --------------------------


def derive_consumption(
    *, preserve_reagent: bool, not_improved: bool, reaction_has_product: bool,
    product_to_container_target: bool,
) -> str:
    """The four-outcome rule, zero exceptions across 159 reactions / 314
    reagent lines in the audit. Order matters only in that
    `modified_in_place` must be checked before `occupied_until_released`:
    a reaction with no `[PRODUCT]` line at all cannot have any reagent
    named by a `PRODUCT_TO_CONTAINER`, so the two conditions never actually
    overlap, but checking `modified_in_place` first keeps the branches
    honestly ordered to match the spec table's own row order."""
    if not preserve_reagent:
        return schema.CONSUMED
    if not reaction_has_product and not_improved:
        return schema.MODIFIED_IN_PLACE
    if product_to_container_target:
        return schema.OCCUPIED_UNTIL_RELEASED
    return schema.OCCUPIED_JOB


# ---- reagent class-filter resolution (audit sec3) -----------------------------------


def _reagent_class(reagent: dict) -> tuple[str | None, str | None, str | None]:
    """`(class_name, mechanism, container_class)` for one reagent, per
    the three-plus-more raw mechanisms audit sec3 found: `REACTION_CLASS`,
    `HAS_MATERIAL_REACTION_PRODUCT`, the hardcoded `ANY_PLANT_MATERIAL`/
    `ANY_BONE_MATERIAL` flags, the ad hoc `FOOD_STORAGE_CONTAINER` flag,
    `HAS_TOOL_USE:...`, and finally a bare item type (bag, bucket) or a
    fixed material named directly (e.g. `lye`, an ore).

    Real-corpus finding, 2026-09-19: the "fixed material named directly"
    case does NOT return `(None, None, None)` as this docstring originally
    claimed (untested, since no fixture exercised it) -- it falls into the
    bare-item-type branch below and DID return a value, just a lossy,
    material-blind one. Two real shapes collapse every reagent of a given
    item type into the same class string, losing the material entirely:
      - `[REAGENT:B:1:METAL_ORE:COPPER]` (12 occurrences, reaction_smelter.
        txt): DF's short form for an ore reagent. `METAL_ORE` has no
        subtype/mat-category slots of its own; the material lands directly
        in the subtype position. Before this fix every metal-ore reagent
        of every smelting reaction extracted as the identical class
        "METAL_ORE", indistinguishable from each other.
      - `[REAGENT:lye:150:LIQUID_MISC:NONE:LYE]` (2 occurrences): the
        standard 5/6/7-arg shape with a bare material name (not a
        PLANT_MAT/METAL/INORGANIC family) in the mat-category slot. Before
        this fix this extracted as the bare class "LIQUID_MISC".
    Both are fixed here by qualifying the class with whatever material can
    be read off the reagent's own remaining fields, reusing `_fixed_node_id`
    for the standard-shape case since its family/bare-material handling is
    already correct."""
    flags = {f[0]: f[1] for f in reagent["flags"]}
    if "REACTION_CLASS" in flags:
        args = flags["REACTION_CLASS"]
        return (args[0] if args else None), schema.MECH_REACTION_CLASS, None
    if "HAS_MATERIAL_REACTION_PRODUCT" in flags:
        args = flags["HAS_MATERIAL_REACTION_PRODUCT"]
        return (args[0] if args else None), schema.MECH_MATERIAL_REACTION_PRODUCT, None
    if "ANY_PLANT_MATERIAL" in flags:
        return "ANY_PLANT_MATERIAL", schema.MECH_HARDCODED_FLAG, None
    if "ANY_BONE_MATERIAL" in flags:
        return "ANY_BONE_MATERIAL", schema.MECH_HARDCODED_FLAG, None
    if "FOOD_STORAGE_CONTAINER" in flags:
        return "FOOD_STORAGE_CONTAINER", schema.MECH_AD_HOC_FLAG, "FOOD_STORAGE_CONTAINER"
    if "HAS_TOOL_USE" in flags:
        args = flags["HAS_TOOL_USE"]
        cls = args[0] if args else None
        return cls, schema.MECH_TOOL_USE_FLAG, cls
    item_type = reagent.get("item_type")
    if item_type == "METAL_ORE" and not _is_none(reagent.get("subtype")):
        class_name = f"METAL_ORE:{reagent['subtype']}"
        container_class = class_name if "EMPTY" in flags else None
        return class_name, schema.MECH_ITEM_TYPE_ONLY, container_class
    if not _is_none(item_type):
        # Qualify with a material when the standard shape's mat-category/
        # mat-args slots actually carry one; falls back to the bare item
        # type when they don't (e.g. NONE/NONE, or a genuine class-filter
        # reagent already handled above).
        class_name = _fixed_node_id(
            item_type, None, reagent.get("mat_category"), reagent.get("mat_args") or [],
        )
        container_class = class_name if "EMPTY" in flags else None
        return class_name, schema.MECH_ITEM_TYPE_ONLY, container_class
    return None, None, None


# ---- fixed node-id formatting -----------------------------------------------------


def _fixed_node_id(item_type, subtype, mat_source_type, mat_args) -> str | None:
    """`item type x material`, e.g. `DRINK:PLUMP_HELMET_WINE`, for a product
    (or reagent) whose material is NOT parametric. `mat_source_type` is
    either a family name with the real material as its first arg
    (`PLANT_MAT:<species>:<part>`, `METAL:<alloy>`, `INORGANIC:<mat>` --
    audit sec2) or a bare material name used directly (`COAL`, `PEARLASH`,
    `LYE`)."""
    if _is_none(item_type):
        return None
    if _is_none(mat_source_type):
        material_id = None
    elif mat_source_type in ("PLANT_MAT", "METAL", "INORGANIC") and mat_args:
        material_id = mat_args[0]
    else:
        material_id = mat_source_type
    parts = [item_type]
    if not _is_none(subtype):
        parts.append(subtype)
    if not _is_none(material_id):
        parts.append(material_id)
    return ":".join(parts)


# ---- unit determination (audit sec4) -------------------------------------------------


def _determine_unit(item_type, subtype, dimension, item_tools: dict):
    """`(unit, unit_source, raw_value)`. Three real branches, audit sec4:
    (a) `[PRODUCT_DIMENSION:n]` present -> volume, direct read; (b) item
    type is a raw-moddable `TOOL` subtype with its own `[SIZE:n]` -> volume
    via a join to the item-tool raws; (c) neither -> not derivable from any
    file on this install (the pressed-liquid `LIQUID_MISC` products)."""
    if dimension is not None:
        return schema.UNIT_VOLUME, schema.UNIT_SOURCE_PRODUCT_DIMENSION, dimension
    if item_type == "TOOL" and subtype in item_tools:
        size = item_tools[subtype].get("size")
        if size is not None:
            return schema.UNIT_VOLUME, schema.UNIT_SOURCE_ITEM_SIZE_LOOKUP, size
    return None, schema.UNIT_SOURCE_ABSENT, None


# ---- durability (audit sec6) -----------------------------------------------------------

#: Which material template a product's item type inherits rot status from.
#: A convention this stream authored (the audit's own verdict on this
#: column: "extractable with a lookup we must author"), not a raw-stated
#: mapping. `PLANT` here means raw harvested plant matter, not the growing
#: plant object.
ITEM_TYPE_TEMPLATE = {
    "DRINK": "PLANT_ALCOHOL_TEMPLATE",
    "SEEDS": "SEED_TEMPLATE",
    "PLANT": "STRUCTURAL_PLANT_TEMPLATE",
    "POWDER_MISC": "PLANT_POWDER_TEMPLATE",
}


def _durability(item_type: str | None, material_templates: dict) -> str | None:
    template_name = ITEM_TYPE_TEMPLATE.get(item_type)
    if template_name is None:
        return None
    template = material_templates.get(template_name)
    if template is None:
        return None
    return schema.PERISHABLE if template["rots"] else schema.DURABLE


# ---- pass 1: parse -----------------------------------------------------------------


def pass1(
    reaction_texts: list[tuple[str, str]],   # [(text, source_path), ...]
    plant_text: tuple[str, str],
    material_template_text: tuple[str, str],
    item_tool_text: tuple[str, str],
) -> dict:
    """Returns a dict of row lists (`nodes`, `classes`,
    `material_reaction_products`, `processes`, `flows`, `attributes`), plus
    `_parsed_reactions` and `item_tools` for pass 2's own use. Flows with a
    parametric product carry `node_id=None`, `status='unavailable'` and the
    bookkeeping keys `_parametric`, `_mat_source_reagent`,
    `_mat_source_token` for pass 2 to resolve or leave honestly unresolved.
    """
    material_templates = parse_material_templates(*material_template_text)
    item_tools = parse_item_tools(*item_tool_text)
    plants = parse_plants(*plant_text)

    nodes: dict[str, dict] = {}
    classes: list[dict] = []
    mrp_rows: list[dict] = []
    processes: list[dict] = []
    flows: list[dict] = []
    attributes: list[dict] = []

    def add_node(node: dict) -> None:
        # First writer wins; every caller here derives the same id from the
        # same genuine facts, so a second write would only ever be a
        # duplicate, never a conflicting value.
        nodes.setdefault(node["id"], node)

    # ---- item tools: independent of any reaction, real raw facts on their own ----
    for tool_name, tool in item_tools.items():
        node_id = f"TOOL:{tool_name}"
        add_node({
            "id": node_id, "kind": schema.KIND_ITEM_TYPE, "display_name": tool_name,
            "durability": None, "status": schema.VERIFIED_RAWS,
            "source_ref": f"{tool['source_path']}:{tool['line']}",
        })
        for attr_name, raw_key, unit in (
            ("size", "size", "cm3"), ("container_capacity", "container_capacity", "cm3"),
            ("value", "value", None),
        ):
            v = tool.get(raw_key)
            if v is not None:
                attributes.append({
                    "subject_id": node_id, "name": attr_name, "value": v, "unit": unit,
                    "status": schema.VERIFIED_RAWS,
                    "source_ref": f"{tool['source_path']}:{tool['line']}",
                })

    # ---- plants: the plant itself, its attributes, and its MRP/IRP entries ----
    unparsed: list[dict] = []
    for plant in plants:
        for entry in plant["unparsed"]:
            unparsed.append({**entry, "source_path": plant["source_path"]})
        plant_node_id = f"PLANT:{plant['id']}"
        plant_source = f"{plant['source_path']}:{plant['line']}"
        add_node({
            "id": plant_node_id, "kind": schema.KIND_PLANT, "display_name": plant["id"],
            "durability": _durability("PLANT", material_templates),
            "status": schema.VERIFIED_RAWS, "source_ref": plant_source,
        })
        if plant["growdur"] is not None:
            attributes.append({
                "subject_id": plant_node_id, "name": "growdur", "value": plant["growdur"],
                "unit": "ticks", "status": schema.VERIFIED_RAWS, "source_ref": plant_source,
            })
        if plant["seasons"]:
            attributes.append({
                "subject_id": plant_node_id, "name": "valid_seasons",
                "value": ",".join(plant["seasons"]), "unit": None,
                "status": schema.VERIFIED_RAWS, "source_ref": plant_source,
            })
        if plant["plant_value"] is not None:
            attributes.append({
                "subject_id": plant_node_id, "name": "plant_value", "value": plant["plant_value"],
                "unit": None, "status": schema.VERIFIED_RAWS, "source_ref": plant_source,
            })
        if plant["material_value"] is not None:
            attributes.append({
                "subject_id": plant_node_id, "name": "material_value", "value": plant["material_value"],
                "unit": None, "status": schema.VERIFIED_RAWS, "source_ref": plant_source,
            })

        if any(e["token"] == "DRINK_MAT" for e in plant["mrp"]):
            classes.append({
                "node_id": plant_node_id, "class": "BREWABLE_PLANT",
                "mechanism": schema.MECH_MATERIAL_REACTION_PRODUCT,
                "source_ref": plant_source,
            })

        for entry in plant["mrp"]:
            # Real shape (see parse_plants' docstring): token, mat_type,
            # mat_name -- no item type. What this row "yields" (the DDL's
            # own words) is therefore a MATERIAL local to this plant (e.g.
            # "this plant's own DRINK material"), not an item; the concrete
            # ITEM only exists once a reaction's PRODUCT line supplies an
            # item type, which is pass2's job, not this loop's. Building an
            # item-shaped node_id straight from this entry (as the
            # predecessor stream's fixture-only format assumed) is exactly
            # the bug this fix removes.
            result_node = f"MATERIAL:{plant['id']}:{entry['mat_name']}"
            src = f"{plant['source_path']}:{entry['line']}"
            add_node({
                "id": result_node, "kind": schema.KIND_MATERIAL,
                "display_name": f"{plant['id']} {entry['mat_name']}",
                "durability": None, "status": schema.VERIFIED_RAWS, "source_ref": src,
            })
            mrp_rows.append({
                "material_id": f"PLANT:{plant['id']}", "token": entry["token"],
                "result_node": result_node, "token_family": schema.FAMILY_MATERIAL_REACTION_PRODUCT,
                "source_ref": src,
                # Bookkeeping for pass2's join, stripped before any row is
                # ever written (store.write_all only reads the DDL columns).
                "_plant_id": plant["id"],
            })
        for entry in plant["irp"]:
            # Unlike MRP, ITEM_REACTION_PRODUCT DOES carry its own item
            # type (real 5-arg shape) or did in this stream's legacy 3-arg
            # fixture form (parse_plants normalises both) -- so the
            # concrete node is fully knowable right here, no reaction
            # needed. Material (mat_type/mat_name) is recorded on the mrp
            # row's source data but deliberately not folded into the node
            # id: this is the spec's own flagged "do not resolve" BAG_ITEM
            # case (docs/PRODUCTION-MODEL.md §6), so a coarser, honestly-
            # partial id is preferable to inventing a false precision.
            result_node = _fixed_node_id(entry["item_type"], entry["item_subtype"], None, [])
            if result_node is None:
                continue
            src = f"{plant['source_path']}:{entry['line']}"
            add_node({
                "id": result_node, "kind": schema.KIND_ITEM_TYPE,
                "display_name": result_node,
                "durability": _durability(entry["item_type"], material_templates),
                "status": schema.VERIFIED_RAWS, "source_ref": src,
            })
            mrp_rows.append({
                "material_id": f"PLANT:{plant['id']}", "token": entry["token"],
                "result_node": result_node, "token_family": schema.FAMILY_ITEM_REACTION_PRODUCT,
                "source_ref": src,
            })

    # ---- reactions ----
    for text, source_path in reaction_texts:
        for reaction in parse_reactions(text, source_path):
            for entry in reaction["unparsed"]:
                unparsed.append({**entry, "source_path": source_path})
            if reaction["adventure_mode"] and not reaction["buildings"]:
                continue  # audit sec5: adventurer-mode craft, not a fortress process

            reaction_source = f"{source_path}:{reaction['line']}"
            primary_building = reaction["buildings"][0] if reaction["buildings"] else None
            workshop_node = None
            if primary_building:
                workshop_node = f"BUILDING:{primary_building}"
                add_node({
                    "id": workshop_node, "kind": schema.KIND_BUILDING,
                    "display_name": primary_building, "durability": None,
                    "status": schema.VERIFIED_RAWS, "source_ref": reaction_source,
                })
            for extra in reaction["buildings"][1:]:
                # audit sec5: 2/159 reactions list more than one [BUILDING:...].
                # The spec's workshop_node column is a single scalar; the
                # extra building(s) are recorded as an attribute rather than
                # silently dropped.
                attributes.append({
                    "subject_id": reaction["id"], "name": "workshop_alt", "value": extra,
                    "unit": None, "status": schema.VERIFIED_RAWS, "source_ref": reaction_source,
                })

            # `[SKILL:...]` names a *skill* (BREWING, CARPENTRY), not a labor
            # (BREWER, CARPENTER): the two enums differ and the raws carry no
            # translation. Before 2026-09-21 this wrote the skill token into
            # `labor`, so a reader taking that column at its word would have
            # returned skill names as labors. `labor` is now left NULL here
            # (the raws alone do not determine it) and the skill token is kept
            # as an attribute; `production.labor_ingest` resolves skill to
            # labor from the game's own tables and records how, per row.
            processes.append({
                "id": reaction["id"], "workshop_node": workshop_node,
                "labor": None, "is_hardcoded": 0,
                "source_ref": reaction_source,
            })
            if reaction["skill"] is not None:
                attributes.append({
                    "subject_id": reaction["id"], "name": "skill", "value": reaction["skill"],
                    "unit": None, "status": schema.VERIFIED_RAWS, "source_ref": reaction_source,
                })

            # CATEGORY/CATEGORY_NAME/CATEGORY_DESCRIPTION: real per-reaction
            # UI-grouping metadata (98/159 reactions carry one), now
            # correctly attributed to the reaction itself (parse_reactions)
            # instead of silently landing on whatever reagent/product
            # happened to be open last. Recorded via production_attribute,
            # the table this schema already uses for this kind of overflow
            # fact (see workshop_alt above) -- no schema change needed.
            for attr_name, value in (
                ("display_name", reaction["name"]),
                ("category", reaction["category"]),
                ("category_name", reaction["category_name"]),
                ("category_description", reaction["category_description"]),
            ):
                if value is not None:
                    attributes.append({
                        "subject_id": reaction["id"], "name": attr_name, "value": value,
                        "unit": None, "status": schema.VERIFIED_RAWS, "source_ref": reaction_source,
                    })

            product_to_container_targets = {
                p["container_target"] for p in reaction["products"] if p["container_target"]
            }
            reaction_has_product = len(reaction["products"]) > 0

            # Real-corpus finding, 2026-09-19: MAKE_MEAD's product line
            # (real: `[PRODUCT:100:5:DRINK:NONE:GET_MATERIAL_FROM_REAGENT:
            # honey:DRINK_MAT]`) names a token, DRINK_MAT, that IS a real
            # entry in material_reaction_products -- but only because 16
            # unrelated PLANTS happen to declare that same token name. The
            # "honey" reagent it actually names
            # (`[REAGENT:honey:150:LIQUID_MISC:NONE:CREATURE_MAT:
            # HONEY_BEE:HONEY]`) has no HAS_MATERIAL_REACTION_PRODUCT flag
            # at all -- it is a FIXED creature material, and this corpus
            # has no creature files to resolve what DRINK_MAT means on
            # honeybee honey (not pulled down for this stream). Before this
            # fix, pass2 matched purely by token *name*, so MAKE_MEAD
            # spuriously materialised into 16 plant-flavoured "mead" nodes
            # it has no real connection to -- every one stamped
            # verified_raws. Recording, per reagent name, which mechanism
            # actually resolved its class lets pass2 refuse to join a
            # parametric product against material_reaction_product unless
            # the reagent it names was ACTUALLY filtered via
            # HAS_MATERIAL_REACTION_PRODUCT (the only mechanism that join
            # table's rows are ever sourced from) -- not merely happens to
            # share a token string with one that was.
            reagent_mechanism_by_name: dict[str, str | None] = {}

            for reagent in reaction["reagents"]:
                flags = {f[0] for f in reagent["flags"]}
                preserve = "PRESERVE_REAGENT" in flags
                not_improved = "NOT_IMPROVED" in flags
                is_target = reagent["name"] in product_to_container_targets
                consumption = derive_consumption(
                    preserve_reagent=preserve, not_improved=not_improved,
                    reaction_has_product=reaction_has_product,
                    product_to_container_target=is_target,
                )
                class_name, mechanism, container_class = _reagent_class(reagent)
                if reagent["name"] is not None:
                    reagent_mechanism_by_name[reagent["name"]] = mechanism
                flows.append({
                    "process_id": reaction["id"], "direction": schema.REAGENT,
                    "node_id": class_name, "quantity": _to_int(reagent["quantity"]),
                    "unit": None, "unit_source": schema.UNIT_SOURCE_ABSENT,
                    "consumption": consumption,
                    # audit sec1: reagents carry no probability token at all;
                    # a required-match reagent is a constant 100, never read.
                    "probability": 100,
                    "container_class": container_class,
                    "status": schema.VERIFIED_RAWS if class_name is not None else schema.UNAVAILABLE,
                    "source_ref": f"{source_path}:{reagent['line']}",
                })

            for product in reaction["products"]:
                mat_source_type = product["mat_source_type"]
                mat_args = product["mat_args"]

                # Real-corpus finding, 2026-09-19: GET_ITEM_DATA_FROM_REAGENT
                # can sit in the ITEM TYPE position instead of the material-
                # source position this extractor previously assumed for
                # both GET_*_FROM_REAGENT tokens. The one real occurrence
                # (reaction_other.txt:328, PROCESS_PLANT_TO_BAG) is a 5-arg
                # product line with NO item_type/subtype/mat_source_type/
                # mat_args in the usual 7-arg sense at all:
                # `[PRODUCT:100:5:GET_ITEM_DATA_FROM_REAGENT:plant:
                # BAG_ITEM]` parses (by this file's own positional fields)
                # as item_type="GET_ITEM_DATA_FROM_REAGENT", subtype=
                # "plant", mat_source_type="BAG_ITEM". Before this fix the
                # `mat_source_type in (...)` check below never matched
                # (mat_source_type here is "BAG_ITEM", not the marker), so
                # `_fixed_node_id` built a node id straight out of the
                # literal token text ("GET_ITEM_DATA_FROM_REAGENT:plant:
                # BAG_ITEM") and marked it verified_raws: silently WRONG,
                # not merely unavailable, and worse than the already-known
                # BAG_ITEM token-family mismatch (docs/PRODUCTION-MODEL.md
                # §6) it was supposed to be one instance of. This is the
                # ONLY occurrence of this shape across all 159 real
                # reactions (measured); the original mat_source_type-
                # position check is kept too, belt and suspenders, in case
                # a modded raw ever uses the position this file originally
                # assumed.
                item_data_in_item_type_slot = product["item_type"] == "GET_ITEM_DATA_FROM_REAGENT"
                parametric = (
                    item_data_in_item_type_slot
                    or mat_source_type in ("GET_MATERIAL_FROM_REAGENT", "GET_ITEM_DATA_FROM_REAGENT")
                )
                # DF's own item type is unresolved until the reagent's
                # matched material/item is known -- not derivable from this
                # product line alone when it's in this shape.
                effective_item_type = None if item_data_in_item_type_slot else product["item_type"]

                node_id = None
                if not parametric:
                    node_id = _fixed_node_id(
                        effective_item_type, product["subtype"], mat_source_type, mat_args,
                    )
                    if node_id is not None:
                        add_node({
                            "id": node_id, "kind": schema.KIND_ITEM_TYPE,
                            "display_name": node_id,
                            "durability": _durability(effective_item_type, material_templates),
                            "status": schema.VERIFIED_RAWS,
                            "source_ref": f"{source_path}:{product['line']}",
                        })
                unit, unit_source, _raw_unit_value = _determine_unit(
                    effective_item_type, product["subtype"], product["dimension"], item_tools,
                )
                flow = {
                    "process_id": reaction["id"], "direction": schema.PRODUCT,
                    "node_id": node_id, "quantity": _to_int(product["quantity"]),
                    "unit": unit, "unit_source": unit_source, "consumption": None,
                    "probability": _to_int(product["probability"]) or 100,
                    "container_class": None,
                    "status": schema.VERIFIED_RAWS if node_id is not None else schema.UNAVAILABLE,
                    "source_ref": f"{source_path}:{product['line']}",
                }
                if parametric:
                    flow["_parametric"] = True
                    if item_data_in_item_type_slot:
                        flow["_mat_source_reagent"] = product["subtype"]
                        flow["_mat_source_token"] = mat_source_type
                    else:
                        flow["_mat_source_reagent"] = mat_args[0] if mat_args else None
                        flow["_mat_source_token"] = mat_args[1] if len(mat_args) > 1 else None
                    flow["_item_type"] = effective_item_type
                    flow["_subtype"] = None if item_data_in_item_type_slot else product["subtype"]
                    # See the MAKE_MEAD comment above `reagent_mechanism_by_
                    # name`: only a reagent actually filtered via HAS_
                    # MATERIAL_REACTION_PRODUCT is a legitimate target for
                    # pass2's material_reaction_product join.
                    flow["_mat_source_mechanism"] = reagent_mechanism_by_name.get(
                        flow["_mat_source_reagent"]
                    )
                flows.append(flow)

    return {
        "nodes": nodes, "classes": classes, "material_reaction_products": mrp_rows,
        "processes": processes, "flows": flows, "attributes": attributes,
        "unparsed": unparsed, "material_templates": material_templates,
    }


# ---- pass 2: materialise ---------------------------------------------------------


def pass2(pass1_result: dict) -> dict:
    """Resolve every parametric flow (`node_id is None`, `_parametric`)
    against `material_reaction_products`, expanding one row into N.

    Matching is **strict on `token_family`**: a parametric product is only
    matched against `material_reaction_product`-family rows, never
    `item_reaction_product`-family ones, regardless of which family the
    reagent's own class filter came from. This is deliberate, per the
    handoff and `docs/PRODUCTION-MODEL.md` §6: "One unresolved
    inconsistency, do not paper over it" -- `PROCESS_PLANT_TO_BAG` filters
    via `HAS_MATERIAL_REACTION_PRODUCT:BAG_ITEM` while quarry bush declares
    `ITEM_REACTION_PRODUCT:BAG_ITEM`, a different family with the same
    name, and whether the engine actually matches across families is not
    knowable from text files. Strict matching means that flow's rows stay
    `node_id=NULL, status='unavailable'` rather than silently resolving
    (wrong) or silently vanishing (worse) -- the gap is visible in the
    coverage table, which is the whole point of recording `token_family` on
    the join table in the first place.

    Real-corpus finding, 2026-09-19: a `material_reaction_product` row's
    own `result_node` (built in `pass1`) is now a MATERIAL node (this
    plant's own named local material -- see `pass1`'s plant loop), because
    that is genuinely all a bare MRP line states. The concrete ITEM node a
    parametric flow resolves to needs the flow's own `_item_type` (read off
    the *reaction's* `[PRODUCT:...]` line, e.g. `DRINK` vs `SEEDS`)
    combined with the matched material's plant -- both only come together
    here, in pass 2, which is the actual reason this design needs two
    passes, not merely that *a* join happens somewhere.
    """
    nodes = dict(pass1_result["nodes"])
    mrp_rows = pass1_result["material_reaction_products"]
    classes = list(pass1_result["classes"])
    material_templates = pass1_result.get("material_templates", {})

    resolved_flows: list[dict] = []
    for flow in pass1_result["flows"]:
        if not flow.get("_parametric"):
            resolved_flows.append(flow)
            continue

        token = flow.get("_mat_source_token")
        # Real-corpus finding, 2026-09-19 (MAKE_MEAD): matching by token
        # NAME alone is not enough -- a token can coincidentally collide
        # with one from a completely unrelated material family. Only join
        # if the reagent this product actually names was itself filtered
        # via HAS_MATERIAL_REACTION_PRODUCT (see pass1's
        # `reagent_mechanism_by_name`); otherwise the material is fixed
        # elsewhere (a creature file this corpus doesn't have, for
        # MAKE_MEAD's honey) and no amount of token-matching against the
        # plant corpus can honestly resolve it.
        eligible = flow.get("_mat_source_mechanism") == schema.MECH_MATERIAL_REACTION_PRODUCT
        matches = [
            r for r in mrp_rows
            if r["token"] == token and r["token_family"] == schema.FAMILY_MATERIAL_REACTION_PRODUCT
        ] if (token and eligible) else []

        clean = {k: v for k, v in flow.items() if not k.startswith("_")}
        item_type = flow.get("_item_type")

        if not matches:
            # Unresolved on purpose -- see docstring. Leave exactly one row,
            # honestly marked, rather than 0 (silently vanished) or a guess.
            resolved_flows.append(clean)
            continue

        if item_type is None:
            # A real match exists (we know which material), but DF's own
            # item type for this flow isn't derivable from the product line
            # alone (the GET_ITEM_DATA_FROM_REAGENT-in-item-type-slot shape
            # -- see pass1). Building "<None>:<plant>" would be a guess with
            # a status='verified_raws' label on it; stay unresolved instead.
            # Not exercised by the 2026-09-19 corpus (its one such flow,
            # PROCESS_PLANT_TO_BAG's bag, has zero material_reaction_product
            # -family matches for token BAG_ITEM to begin with -- this
            # branch is defensive, for a shape this stream hasn't seen).
            resolved_flows.append(clean)
            continue

        for m in matches:
            row = dict(clean)
            plant_id = m.get("_plant_id")
            item_node_id = f"{item_type}:{plant_id}" if plant_id is not None else None
            if item_node_id is None:
                resolved_flows.append(clean)
                continue
            join_source = f"{clean['source_ref']} + {m['source_ref']} (pass 2 join on {token!r})"
            if item_node_id not in nodes:
                nodes[item_node_id] = {
                    "id": item_node_id, "kind": schema.KIND_ITEM_TYPE,
                    "display_name": item_node_id,
                    "durability": _durability(item_type, material_templates),
                    "status": schema.VERIFIED_RAWS, "source_ref": join_source,
                }
            if item_type == "DRINK":
                classes.append({
                    "node_id": item_node_id, "class": "DRINK",
                    "mechanism": schema.MECH_MATERIAL_REACTION_PRODUCT,
                    "source_ref": join_source,
                })
            row["node_id"] = item_node_id
            row["status"] = schema.VERIFIED_RAWS
            row["source_ref"] = join_source
            resolved_flows.append(row)

    return {
        "nodes": nodes, "classes": classes,
        "material_reaction_products": mrp_rows,
        "processes": pass1_result["processes"],
        "flows": resolved_flows,
        "attributes": pass1_result["attributes"],
        "unparsed": pass1_result.get("unparsed", []),
    }


# ---- cycle check (docs/PRODUCTION-MODEL.md sec2/sec14, audit sec9) -----------------


def build_edges(flows: list[dict]) -> set[tuple[str, str]]:
    """Reagent-node -> product-node edges, one process at a time. Coarse on
    purpose, matching the audit's own method (sec9): every reagent node of a
    process is linked to every product node of that same process, which can
    only *add* spurious edges relative to the true material-precise graph,
    never hide a real cycle. So an absence of a cycle in this coarse graph
    is a valid (non-exhaustive) argument that none exists in the real one
    either; finding one here would need the finer graph to confirm."""
    by_process: dict[str, dict[str, list[str]]] = {}
    for f in flows:
        node_id = f.get("node_id")
        if node_id is None:
            continue
        sides = by_process.setdefault(f["process_id"], {schema.REAGENT: [], schema.PRODUCT: []})
        sides[f["direction"]].append(node_id)
    edges: set[tuple[str, str]] = set()
    for sides in by_process.values():
        for r in sides[schema.REAGENT]:
            for p in sides[schema.PRODUCT]:
                if r != p:
                    edges.add((r, p))
    return edges


def find_cycle(edges: set[tuple[str, str]]) -> list[str] | None:
    """Plain DFS cycle detection (white/gray/black colouring) over the edge
    set `build_edges` produces. No `scipy`, no `networkx`: `docs/
    PRODUCTION-MODEL.md` sec2 says a direct solve suffices because the
    static audit found no cycle, and this function is how that claim gets
    checked against the extracted graph rather than merely repeated.
    Returns the cycle as a node-id path if one exists, else None."""
    graph: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for a, b in edges:
        graph.setdefault(a, []).append(b)
        nodes.add(a)
        nodes.add(b)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        path.append(node)
        for nxt in graph.get(node, []):
            if color[nxt] == GRAY:
                return path[path.index(nxt):] + [nxt]
            if color[nxt] == WHITE:
                found = dfs(nxt)
                if found:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for node in sorted(nodes):
        if color[node] == WHITE:
            found = dfs(node)
            if found:
                return found
    return None


# ---- orchestration -----------------------------------------------------------------


def _read(path: Path) -> tuple[str, str]:
    return path.read_text(encoding="utf-8"), str(path)


DEFAULT_REACTION_FILES = (
    "reaction_other.txt", "reaction_adv_carpenter.txt",
    "reaction_dyes.txt", "reaction_smelter.txt",
)


def extract_from_sources(
    reaction_texts: list[tuple[str, str]],
    plant_text: tuple[str, str],
    material_template_text: tuple[str, str],
    item_tool_text: tuple[str, str],
) -> dict:
    """Run both passes against arbitrary `(text, source_path)` sources and
    return the table->rows dict, plus an `unparsed` list (NOT one of
    `store.write_all`'s kwargs -- pop it before splatting this dict at
    `write_all`, same as `main` below does). Factored out of `extract` so a
    caller with a real, differently-laid-out raws directory (not this
    package's flat `tests/fixtures/`) can run the identical pipeline; see
    `research/2026-09-19-real-corpus-extraction.md` for the one-off script
    that did exactly this against the real 159-reaction corpus."""
    p1 = pass1(reaction_texts, plant_text, material_template_text, item_tool_text)
    p2 = pass2(p1)
    return {
        "nodes": list(p2["nodes"].values()),
        "classes": p2["classes"],
        "material_reaction_products": p2["material_reaction_products"],
        "processes": p2["processes"],
        "flows": p2["flows"],
        "attributes": p2["attributes"],
        "observations": [],
        "unparsed": p2["unparsed"],
    }


def extract(fixtures_dir: Path = FIXTURES_DIR) -> dict:
    """Run both passes against the fixture files in `fixtures_dir` and
    return the table->rows dict `store.write_all` expects (plus `unparsed`,
    which isn't one of its kwargs -- see `extract_from_sources`)."""
    reaction_texts = [_read(fixtures_dir / name) for name in DEFAULT_REACTION_FILES]
    plant_text = _read(fixtures_dir / "plant_standard.txt")
    material_template_text = _read(fixtures_dir / "material_template_default.txt")
    item_tool_text = _read(fixtures_dir / "item_tool.txt")
    return extract_from_sources(reaction_texts, plant_text, material_template_text, item_tool_text)


def main() -> None:
    rows = extract()
    unparsed = rows.pop("unparsed", [])
    counts = store.write_all(store.default_path(), **rows)
    for table, n in counts.items():
        print(f"{table}: {n}")
    print(f"unparsed: {len(unparsed)}")


if __name__ == "__main__":
    main()
