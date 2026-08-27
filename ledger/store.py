"""Reading, writing and stratifying the fort ledger.

The ledger is **JSONL, one row per fort, git-tracked**. That choice is not
laziness about databases:

- At N~20 rows a full scan in Python is instant, so a query engine buys
  nothing and costs a schema migration path.
- JSONL diffs per row, which means a fort's record shows up in `git log` as
  one reviewable addition, the same reasoning that put the perception eval's
  results under version control (register, 2026-08-27).
- The project's stated goal is a public report built from accumulated
  experiment data. A file anyone can read with `cat` serves that; a binary
  database does not.

If cross-fort queries ever outgrow this, build SQLite as a *derived read
model* rebuilt from the JSONL, not as the system of record.

## Why stratification lives here rather than in the caller

`stratify` refuses to pool `unrecorded` into a bucket, and reports how many
rows it dropped for that reason. This is the enforcement point for section
3.2's warning: a caller that could quietly treat "we didn't look" as a
measurement would defeat the schema's whole purpose, so the store does not
offer that option.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .schema import (
    FORT_FIELDS,
    GRADEABLE_SOURCES,
    RECORD_FIELDS,
    UNRECORDED,
    validate,
)

DEFAULT_PATH = Path(__file__).resolve().parent / "forts.jsonl"


class LedgerError(Exception):
    """Raised when a row would corrupt the ledger. Never swallowed."""


# ---- reading and writing --------------------------------------------------


def load(path: str | Path = DEFAULT_PATH) -> list[dict]:
    """Load every row. Invalid rows raise rather than being skipped.

    Skipping a bad row would silently shrink the sample of an already tiny
    sample, and the shrinkage would not appear in any count.
    """
    p = Path(path)
    if not p.exists():
        return []

    rows: list[dict] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{p}:{lineno}: not valid JSON: {exc}") from exc
        errors = validate(row)
        if errors:
            raise LedgerError(
                f"{p}:{lineno}: invalid ledger row:\n  " + "\n  ".join(errors)
            )
        rows.append(row)

    ids = [r["fort_id"] for r in rows]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise LedgerError(f"{p}: duplicate fort_id(s): {sorted(duplicates)}")

    return rows


def append(row: dict, path: str | Path = DEFAULT_PATH) -> None:
    """Validate and append one row. Refuses invalid rows and duplicate ids."""
    errors = validate(row)
    if errors:
        raise LedgerError("refusing to write an invalid row:\n  " + "\n  ".join(errors))

    p = Path(path)
    existing = {r["fort_id"] for r in load(p)}
    if row["fort_id"] in existing:
        raise LedgerError(
            f"fort_id {row['fort_id']!r} is already in the ledger. A fort's "
            "row is written once, at the end; correcting one is an edit with "
            "a reason, not a second append."
        )

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        # sort_keys so a rewritten row diffs against its predecessor cleanly.
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


# ---- field access ---------------------------------------------------------


def get_path(row: dict, dotted: str):
    """Read a dotted path like `design.entrance_seal` or `threat_log.0.kind`."""
    node = row
    for part in dotted.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node


def field_source(dotted: str) -> str | None:
    """The declared `source` of a dotted top-level path, or None if unknown.

    Used to keep grading off `AGENT`-sourced fields; see `assert_gradeable`.
    """
    parts = dotted.split(".")
    fields = {f.name: f for f in FORT_FIELDS}
    field = fields.get(parts[0])
    if field is None:
        return None
    if len(parts) == 1:
        return field.source

    if field.type.startswith("object:"):
        sub = RECORD_FIELDS[field.type.split(":", 1)[1]]
    elif field.type.startswith("record_list:"):
        sub = RECORD_FIELDS[field.type.split(":", 1)[1]]
        parts = parts[1:]  # skip the list index
    else:
        return None

    leaf = {f.name: f for f in sub}.get(parts[-1])
    return leaf.source if leaf else None


def assert_gradeable(dotted: str) -> None:
    """Raise unless `dotted` names a MECHANICAL or DERIVED field.

    `docs/MEMORY-ARCHITECTURE.md`: "Never grade the agent's account of its own
    learning." Any future grading or evidence-update code should call this on
    every field it reads, so that rule is enforced by the code rather than
    remembered by whoever is writing it.
    """
    source = field_source(dotted)
    if source is None:
        raise LedgerError(f"{dotted!r} is not a field in the schema")
    if source not in GRADEABLE_SOURCES:
        raise LedgerError(
            f"{dotted!r} is {source}-sourced and must not be read by grading "
            f"code (allowed: {sorted(GRADEABLE_SOURCES)})"
        )


# ---- stratification -------------------------------------------------------


@dataclass
class Stratum:
    """One group of forts sharing a value of the stratifying field."""

    value: str
    rows: list[dict]

    @property
    def n(self) -> int:
        return len(self.rows)


@dataclass
class Stratification:
    """The result of grouping forts by a feature.

    `dropped_unrecorded` is part of the result rather than a log line: it is
    the honest denominator. A comparison across two strata of 3 that silently
    discarded 9 rows is a different claim from one that discarded none.
    """

    field: str
    strata: list[Stratum]
    dropped_unrecorded: int
    total_rows: int

    @property
    def usable(self) -> int:
        return sum(s.n for s in self.strata)

    def summary(self) -> str:
        parts = ", ".join(f"{s.value}={s.n}" for s in self.strata) or "nothing"
        return (
            f"{self.field}: {parts} "
            f"({self.usable}/{self.total_rows} rows usable, "
            f"{self.dropped_unrecorded} unrecorded)"
        )


def stratify(rows: list[dict], dotted: str) -> Stratification:
    """Group rows by a field's value, excluding `unrecorded` rather than
    pooling it.

    Section 3.2: an unrecorded feature can never become a lesson. Pooling
    `unrecorded` into its own bucket would let it look like a finding.
    """
    strata: dict[str, list[dict]] = defaultdict(list)
    dropped = 0
    for row in rows:
        value = get_path(row, dotted)
        if value is None or value == UNRECORDED:
            dropped += 1
            continue
        strata[str(value)].append(row)

    return Stratification(
        field=dotted,
        strata=[Stratum(v, rs) for v, rs in sorted(strata.items())],
        dropped_unrecorded=dropped,
        total_rows=len(rows),
    )


def coverage(rows: list[dict], dotted_fields: list[str]) -> dict[str, int]:
    """How many rows actually recorded each field.

    This is the direct answer to "the schema defines what is learnable": the
    schema sets the ceiling, coverage says how much of it has been reached.
    A field at 0 is a field about which nothing can ever be concluded, no
    matter how much reasoning is applied to the rows.
    """
    return {
        f: sum(
            1
            for r in rows
            if (v := get_path(r, f)) is not None and v != UNRECORDED
        )
        for f in dotted_fields
    }


def design_fields() -> list[str]:
    """Dotted paths for every design feature: the default stratification set."""
    return [f"design.{f.name}" for f in RECORD_FIELDS["design"]]
