"""Shared setup for the labor tests: a small hand-built graph using **real**
reaction ids, building tokens and skills (each checked against the real
extraction of the install's `vanilla_reactions` raws on 2026-09-21, out of
tree), plus the path to the committed dump fixture."""

from __future__ import annotations

from pathlib import Path

from production import schema, store

FIXTURE_DUMP = Path(__file__).resolve().parent / "fixtures" / "labor_dump"

#: (reaction id, raw building token, [SKILL:...] token), all real.
REACTIONS = [
    ("BREW_DRINK_FROM_PLANT", "STILL", "BREWING"),
    ("BREW_DRINK_FROM_PLANT_GROWTH", "STILL", "BREWING"),
    ("MAKE_MEAD", "STILL", "BREWING"),
    ("GLAZE_STATUE", "KILN", "GLAZING"),
    ("GLAZE_JUG", "KILN", "GLAZING"),
    ("BILLON_MAKING", "SMELTER", "SMELT"),
    ("ACACIA_BARK_DYE", "DYER", "PROCESSPLANTS"),
    ("MAKE WOODEN CHAIR", "CARPENTER", "CARPENTRY"),
    ("PROCESS_PLANT_TO_BAG", "FARMER", "PROCESSPLANTS"),
    ("MAKE_SHEET_FROM_PLANT", "FARMER", "PAPERMAKING"),
]

_REF = "labor test fixture (real reaction id, building token and skill)"


def build_graph(path, *, labor_column: dict[str, str] | None = None) -> None:
    """Write the extractor-shaped graph: reaction rows with a NULL labor and the
    skill as an attribute (`extract.py` since 2026-09-21). `labor_column` forces
    a labor onto named rows to simulate the old, pre-split extractor output."""
    labor_column = labor_column or {}
    tokens = sorted({b for _, b, _ in REACTIONS})
    nodes = [
        {"id": f"BUILDING:{t}", "kind": schema.KIND_BUILDING, "display_name": t,
         "status": schema.VERIFIED_RAWS, "source_ref": _REF}
        for t in tokens
    ]
    processes = [
        {"id": rid, "workshop_node": f"BUILDING:{b}", "labor": labor_column.get(rid),
         "is_hardcoded": 0, "source_ref": _REF}
        for rid, b, _ in REACTIONS
    ]
    attributes = [
        {"subject_id": rid, "name": "skill", "value": skill,
         "status": schema.VERIFIED_RAWS, "source_ref": _REF}
        for rid, _, skill in REACTIONS
    ]
    store.write_all(path, nodes=nodes, processes=processes, attributes=attributes)


def rows(path, sql: str, params=()) -> list[dict]:
    with store.connect(path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
