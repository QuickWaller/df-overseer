"""Reading and writing the production database: one SQLite file per fort,
following `dfqueue/store.py`'s own precedent (WAL journal, `Row` factory,
schema-version check, one `with conn:` transaction per write).

Unlike `dfqueue`, nothing here is a queue an agent writes to over time: the
extractor (`extract.py`) populates the whole database in one run, so
`write_all()` is the one real write path, wrapped in a single transaction —
either the full extraction lands, or the database is left exactly as it was.
`schema.py`'s `validate_*` functions run before any row reaches SQLite, so a
malformed row raises `StoreError` with nothing written, same contract as
`dfqueue.store.append()`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import schema

DEFAULT_DIR = Path(__file__).resolve().parent


class StoreError(Exception):
    """Raised when a row would be written that fails `schema.py` validation.
    Never swallowed; the whole write is refused."""


def default_path(fort: str = "uniboslan") -> Path:
    return DEFAULT_DIR / f"{fort}.sqlite3"


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        schema.create_schema(conn)
        yield conn
    finally:
        conn.close()


def _validate_all(kind: str, rows: list[dict], validator) -> None:
    errors: list[str] = []
    for i, row in enumerate(rows):
        for e in validator(row):
            errors.append(f"{kind}[{i}]: {e}")
    if errors:
        raise StoreError(
            f"refusing to write {kind}, {len(errors)} row(s) invalid:\n  "
            + "\n  ".join(errors)
        )


def write_all(
    path: str | Path,
    *,
    nodes: list[dict] | None = None,
    classes: list[dict] | None = None,
    material_reaction_products: list[dict] | None = None,
    processes: list[dict] | None = None,
    flows: list[dict] | None = None,
    attributes: list[dict] | None = None,
    observations: list[dict] | None = None,
    reset: bool = True,
) -> dict:
    """Validate and write a full extraction in one transaction.

    `reset=True` (the default) clears every table first, so re-running the
    extractor against a fixture set is idempotent rather than accumulating
    duplicate rows across runs -- this module has no notion of "already
    extracted this reaction," unlike dfqueue's id-collision check, because
    there is exactly one writer (the extractor) and no append-only audit
    trail requirement here.

    Returns a dict of row counts per table, the same shape `extract.py`'s
    caller (and the handoff's coverage table) wants.
    """
    nodes = nodes or []
    classes = classes or []
    material_reaction_products = material_reaction_products or []
    processes = processes or []
    flows = flows or []
    attributes = attributes or []
    observations = observations or []

    _validate_all("production_node", nodes, schema.validate_node)
    _validate_all("production_class", classes, schema.validate_class)
    _validate_all(
        "material_reaction_product", material_reaction_products,
        schema.validate_material_reaction_product,
    )
    _validate_all("production_process", processes, schema.validate_process)
    _validate_all("production_flow", flows, schema.validate_flow)
    _validate_all("production_attribute", attributes, schema.validate_attribute)
    _validate_all("production_observation", observations, schema.validate_observation)

    with connect(path) as conn:
        with conn:
            if reset:
                for table in (
                    "production_flow", "production_class", "material_reaction_product",
                    "production_attribute", "production_observation",
                    "production_process", "production_node",
                ):
                    conn.execute(f"DELETE FROM {table}")

            conn.executemany(
                "INSERT INTO production_node (id, kind, display_name, durability, status, source_ref) "
                "VALUES (:id, :kind, :display_name, :durability, :status, :source_ref)",
                [{**{"durability": None}, **n} for n in nodes],
            )
            conn.executemany(
                "INSERT INTO production_class (node_id, class, mechanism, source_ref) "
                "VALUES (:node_id, :class, :mechanism, :source_ref)",
                classes,
            )
            conn.executemany(
                "INSERT INTO material_reaction_product "
                "(material_id, token, result_node, token_family, source_ref) "
                "VALUES (:material_id, :token, :result_node, :token_family, :source_ref)",
                material_reaction_products,
            )
            conn.executemany(
                "INSERT INTO production_process (id, workshop_node, labor, is_hardcoded, source_ref) "
                "VALUES (:id, :workshop_node, :labor, :is_hardcoded, :source_ref)",
                [{**{"workshop_node": None, "labor": None, "is_hardcoded": 0}, **p} for p in processes],
            )
            conn.executemany(
                "INSERT INTO production_flow "
                "(process_id, direction, node_id, quantity, unit, unit_source, consumption, "
                "probability, container_class, status, source_ref) "
                "VALUES (:process_id, :direction, :node_id, :quantity, :unit, :unit_source, "
                ":consumption, :probability, :container_class, :status, :source_ref)",
                [
                    {
                        **{
                            "node_id": None, "quantity": None, "unit": None,
                            "consumption": None, "probability": 100, "container_class": None,
                        },
                        **f,
                    }
                    for f in flows
                ],
            )
            conn.executemany(
                "INSERT INTO production_attribute (subject_id, name, value, unit, status, source_ref) "
                "VALUES (:subject_id, :name, :value, :unit, :status, :source_ref)",
                [{**{"unit": None}, **a} for a in attributes],
            )
            conn.executemany(
                "INSERT INTO production_observation "
                "(abs_tick, subject_id, metric, value, unit, skill_level, status, source_ref) "
                "VALUES (:abs_tick, :subject_id, :metric, :value, :unit, :skill_level, :status, :source_ref)",
                [{**{"unit": None, "skill_level": None}, **o} for o in observations],
            )

    return {
        "production_node": len(nodes),
        "production_class": len(classes),
        "material_reaction_product": len(material_reaction_products),
        "production_process": len(processes),
        "production_flow": len(flows),
        "production_attribute": len(attributes),
        "production_observation": len(observations),
    }


def coverage(path: str | Path) -> dict:
    """Rows per table, and of those, how many carry `status='prior'` and how
    many carry a NULL `node_id` (`production_flow` only) -- the headline
    honesty check the audit asked extraction to preserve, not just
    reproduce. `null_columns` reports, per table, the columns with at least
    one NULL value found, restricted to columns the schema allows to be NULL
    (durability, workshop_node/labor, node_id/quantity/unit/consumption/
    container_class, unit, skill_level) -- never a NOT NULL column, since a
    NULL there would mean a write bypassed validation, not an honest gap.
    """
    tables_and_status_col = [
        "production_node", "production_class", "material_reaction_product",
        "production_process", "production_flow", "production_attribute",
        "production_observation",
    ]
    #: production_class, material_reaction_product and production_process
    #: carry no status column (schema.py's DDL, copied verbatim from
    #: docs/PRODUCTION-MODEL.md §4): only production_node, production_flow,
    #: production_attribute and production_observation are graded facts in
    #: this schema's own design. A process row's confidence rides on its
    #: workshop_node/labor being resolved (production_node.status) and on
    #: is_hardcoded, not on a status of its own.
    _NO_STATUS_TABLES = {"production_class", "material_reaction_product", "production_process"}
    tables_with_status = {t for t in tables_and_status_col if t not in _NO_STATUS_TABLES}
    nullable_columns = {
        "production_node": ["durability"],
        "production_class": [],
        "material_reaction_product": [],
        "production_process": ["workshop_node", "labor"],
        "production_flow": ["node_id", "quantity", "unit", "consumption", "container_class"],
        "production_attribute": ["unit"],
        "production_observation": ["unit", "skill_level"],
    }
    result: dict = {}
    with connect(path) as conn:
        for table in tables_and_status_col:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            if table in tables_with_status:
                prior = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE status = ?", (schema.PRIOR,)
                ).fetchone()["n"]
                unavailable = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE status = ?", (schema.UNAVAILABLE,)
                ).fetchone()["n"]
            else:
                prior = unavailable = None
            null_columns = []
            for col in nullable_columns[table]:
                n = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE {col} IS NULL"
                ).fetchone()["n"]
                if n:
                    null_columns.append((col, n))
            result[table] = {
                "total": total,
                "prior": prior,
                "unavailable": unavailable,
                "null_columns": null_columns,
            }
    return result
