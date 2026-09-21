"""Result shapes of `df-overseer-building.lua` `find` and `build`, as builders.

**Provenance, read this before trusting a value.** The field names and nesting
are the ones the Lua tool writes (`requirements_for`, `find_kind`,
`build_kind`, `kind_brief`, `site_info`, and the `search` block in
`scripts/dfhack/df-overseer-building.lua`), copied field for field. The values
that matter to the join are the ones the live deploy report recorded
(`handoffs/2026-09-21-deploy-building-batch.md`): Well showed
`needs 1 of TRAPPARTS, 0 available`, Bed showed `needs 1 of BED, 0 available`,
Masons and FarmPlot showed no gap, five candidates per find, and a `build` dry
run carries `validation: {"by": "quickfort run --dry-run", "ok": true,
"stats": {"Buildings designated": 1}}`. The deploy report did not keep the raw
JSON, so the per-item stock numbers not stated there are plausible values, not
a capture, and they are chosen to match the stated gaps. Nothing here is a
coordinate, an address or a token.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

BUILDING_MATERIAL_NEED = "any building material (boulder, log or block)"


def stock_rec(total: int, available: int, **extra: Any) -> Dict[str, Any]:
    return {"total": total, "available": available, "unnetted": total, "in_building": 0, "in_job": 0, **extra}


def filter_rec(
    index: int,
    need: str,
    available: Optional[int],
    quantity: int = 1,
    *,
    item_type: Optional[str] = None,
    stock: Optional[Dict[str, Dict[str, Any]]] = None,
    flags: Optional[List[str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """One entry of `building_material.filters`, in the Lua tool's field names."""
    rec: Dict[str, Any] = {"index": index, "quantity": quantity, "flags": flags or []}
    rec["count_scope"] = "item type only; the filter's own flags are not applied"
    rec["need"] = need
    if item_type:
        rec["item_type"] = item_type
    if stock is not None:
        rec["stock"] = stock
    rec["available"] = available
    rec.update(extra)
    return rec


def material_filter(index: int = 1, boulder: int = 0, wood: int = 3, blocks: int = 4) -> Dict[str, Any]:
    """The building_material class filter a workshop has (Masons, Kiln, ...)."""
    return filter_rec(
        index,
        BUILDING_MATERIAL_NEED,
        boulder + wood + blocks,
        1,
        stock={"BOULDER": stock_rec(boulder, boulder), "WOOD": stock_rec(wood, wood), "BLOCKS": stock_rec(blocks, blocks)},
        flags=["flags2.building_material"],
    )


def item_filter(index: int, type_name: str, available: int, quantity: int = 1) -> Dict[str, Any]:
    return filter_rec(
        index, type_name, available, quantity, item_type=type_name,
        stock={type_name: stock_rec(available, available)},
    )


def requirements(filters: List[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
    bm: Dict[str, Any] = {
        "source": "dfhack.buildings.getFiltersByType",
        "buildingplan_enabled": False,
        "filters": filters,
    }
    if not filters:
        bm["note"] = "the game lists no material filter for this kind"
    bm.update(extra)
    return {"building_material": bm}


def kind_brief(token: str, type_name: str, subtype: Optional[str] = None, key: str = "x") -> Dict[str, Any]:
    return {"token": token, "key": key, "label": token, "type": type_name, "subtype": subtype}


SEARCH = {
    "radius_tiles": 30, "tiles_checked": 1849, "eligible_tiles": 412, "eligible_note": None,
    "windows_checked": 0, "fitting_sites": 37, "check_errors": 0, "first_check_error": None,
}


def site(rank: int, near: str = "Embark Site", direction: str = "E", distance: int = 3) -> Dict[str, Any]:
    return {"rank": rank, "near_landmark": near, "direction": direction, "distance_tiles": distance + rank}


def find_candidates(
    kind: Dict[str, Any], dims: List[int], reqs: Dict[str, Any], gaps: List[str], n: int = 5
) -> List[Dict[str, Any]]:
    """`find_kind`'s return: an array, one entry per ranked site, each carrying
    the same `requirements` and `gaps` (the tool computes them once)."""
    return [
        {"kind": kind, "dims": dims, "site": site(r), "search": SEARCH, "requirements": reqs, "gaps": list(gaps)}
        for r in range(1, n + 1)
    ]


def build_dry_run(kind: Dict[str, Any], dims: List[int], reqs: Dict[str, Any], gaps: List[str]) -> Dict[str, Any]:
    """`build_kind`'s dry-run return: one object."""
    return {
        "kind": kind, "dims": dims, "site": site(1), "dry_run": True, "search": SEARCH,
        "requirements": reqs, "gaps": list(gaps),
        "blueprint": {"mode": "build", "key": kind["key"], "cells": f"{dims[0]}x{dims[1]}", "file": "_tmp-building.csv", "removed": True},
        "validation": {"by": "quickfort run --dry-run", "ok": True, "problems": [],
                       "error": None, "stats": {"Buildings designated": 1}},
    }


# ---- the five kinds the deploy report exercised ---------------------------

MASONS_KIND = kind_brief("Masons", "Workshop", "Masons", "m")
BED_KIND = kind_brief("Bed", "Bed", None, "b")
WELL_KIND = kind_brief("Well", "Well", None, "l")
FARM_KIND = kind_brief("FarmPlot", "FarmPlot", None, "p")

# Masons: needs one building material, the fort has WOOD 3 and BLOCKS 4.
MASONS_REQ = requirements([material_filter()])
# Bed: one BED item, none in stock. Deploy report: `needs 1 of BED, 0 available`.
BED_REQ = requirements([item_filter(1, "BED", 0)])
BED_GAP = "needs 1 of BED, 0 available"
# Well: BLOCKS, BUCKET, CHAIN in stock, TRAPPARTS (the mechanism) not.
# Deploy report: `needs 1 of TRAPPARTS, 0 available`.
WELL_REQ = requirements(
    [item_filter(1, "BLOCKS", 4), item_filter(2, "BUCKET", 3), item_filter(3, "CHAIN", 3), item_filter(4, "TRAPPARTS", 0)]
)
WELL_GAP = "needs 1 of TRAPPARTS, 0 available"
# FarmPlot: the game lists no material filter.
FARM_REQ = requirements([])


def masons_find() -> List[Dict[str, Any]]:
    return find_candidates(MASONS_KIND, [3, 3], MASONS_REQ, [])


def bed_find() -> List[Dict[str, Any]]:
    return find_candidates(BED_KIND, [1, 1], BED_REQ, [BED_GAP])


def well_find() -> List[Dict[str, Any]]:
    return find_candidates(WELL_KIND, [1, 1], WELL_REQ, [WELL_GAP])


def farm_find() -> List[Dict[str, Any]]:
    return find_candidates(FARM_KIND, [5, 5], FARM_REQ, [])


def bed_build() -> Dict[str, Any]:
    return build_dry_run(BED_KIND, [1, 1], BED_REQ, [BED_GAP])


def masons_build() -> Dict[str, Any]:
    return build_dry_run(MASONS_KIND, [3, 3], MASONS_REQ, [])


def as_wire(value: Any) -> str:
    """The text the tool prints: one JSON document."""
    return json.dumps(value)


def as_structured(value: Any) -> Dict[str, Any]:
    """What the server hands `tool_guidance.enrich`: an object as is, an array
    wrapped as `{"result": [...]}`."""
    return value if isinstance(value, dict) else {"result": value}
