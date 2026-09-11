"""Prediction log schema: pre-registered predictions, graded mechanically.

Implements `docs/MEMORY-ARCHITECTURE.md`'s own example —

    decision:    dig a second farm level on z-4
    expectation: food stores stop falling within 2 seasons
    check_at:    year 253, Autumn
    signal:      food_stores trend

— as data, per `research/2026-08-25-learning-architecture.md` §1.3 (this is
**pre-registration**, the clinical-trial/Registered-Reports discipline against
HARKing: committing to a prediction and how it will be checked *before* the
outcome is known, because an LLM can produce a fluent, convincing post-hoc
story connecting any decision to any outcome — §1.2's finding, not a
hypothetical).

Two requirements from §1.3, enforced here rather than left to discipline:

1. **Grading is mechanical, never the model re-reading its own prediction.**
   `predictions/grade.py` reads `ledger` state; nothing here ever asks a model
   whether its prediction "felt right."
2. **A prediction must be falsifiable at write time.** `signal` is a dotted
   path (reusing `ledger.store.get_path`'s exact addressing) that must resolve
   to a `MECHANICAL` or `DERIVED` ledger field — `register()` in `store.py`
   refuses to write a prediction whose signal cannot be mechanically checked,
   or that points at a `HUMAN`/`AGENT` field (grading a human's or the agent's
   own prose would smuggle self-report back in through the signal).

## The scope this is deliberately built at, and the gap it does not paper over

`signal` can only resolve against **the fort ledger** — the only mechanical
store that exists in code. `docs/MEMORY-ARCHITECTURE.md`'s own example,
"food stores trend," has no matching ledger field: the ledger is one row
*per fort*, written mostly at embark and at the end, not a running dossier of
mid-fort state. A **fort dossier** (working state that dies with the fort) is
still just a design concept with no module — see `ROADMAP.md`. Predictions
whose natural signal is mid-fort trend data cannot be expressed yet; this
module does not pretend otherwise. What it *does* cover for real: any
prediction about embark covariates, design choices, or fort outcome/threat
fields — including the design doc's other example, "seal the caverns before
year 3," which maps directly onto the ledger's own `design.caverns_sealed`
and `design.caverns_sealed_year` fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ledger.schema import AGENT, DERIVED, GRADEABLE_SOURCES, HUMAN, MECHANICAL

SCHEMA_VERSION = 1

# ---- prediction status ------------------------------------------------------

PENDING = "pending"
GRADED_TRUE = "graded_true"
GRADED_FALSE = "graded_false"
UNRESOLVABLE = "unresolvable"

#: DERIVED — set only by grade.py, never written by hand. A hand-edited status
#: would be exactly the self-report loophole this module exists to close.
PREDICTION_STATUS = (PENDING, GRADED_TRUE, GRADED_FALSE, UNRESOLVABLE)

# ---- predicate: the mechanical comparison ----------------------------------

#: A closed, small op set on purpose — this is the entire vocabulary grading
#: is allowed to evaluate. No "eval this expression": an arbitrary predicate
#: language would reopen exactly the unfalsifiability problem §1.3 flags
#: ("things should improve" is worthless because nothing can contradict it).
EQ, NE, GTE, LTE, GT, LT = "eq", "ne", "gte", "lte", "gt", "lt"
IN, CONTAINS, EXISTS, NOT_EXISTS = "in", "contains", "exists", "not_exists"
PREDICATE_OPS = (EQ, NE, GTE, LTE, GT, LT, IN, CONTAINS, EXISTS, NOT_EXISTS)

#: Ops that test presence/absence rather than compare against a value —
#: `predicate_value` must be null for these and non-null for every other op.
PRESENCE_OPS = (EXISTS, NOT_EXISTS)


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    required: bool = True
    nullable: bool = False


# Flat by design — unlike the ledger, a prediction has no nested records to
# express. `signal`/`predicate_op`/`predicate_value` together are the whole
# falsifiable claim; `decision`/`expectation` are prose colour, HUMAN-sourced,
# and never read by grading (enforced by grade.py calling into
# `ledger.store.assert_gradeable`, not by convention).
FIELDS: tuple[Field, ...] = (
    Field("schema_version", "integer"),
    Field("prediction_id", "string"),
    Field("fort_id", "string"),
    Field("decision", "string"),
    Field("expectation", "string"),
    Field("signal", "string"),
    Field("predicate_op", "vocab"),
    Field("predicate_value", "any", nullable=True),
    Field("check_at_year", "integer"),
    Field("registered_at", "string"),
    Field("status", "vocab"),
    Field("graded_at", "string", nullable=True),
    Field("actual_value", "any", nullable=True),
)

FIELD_SOURCE = {
    "schema_version": DERIVED,
    "prediction_id": HUMAN,
    "fort_id": HUMAN,
    "decision": HUMAN,
    "expectation": HUMAN,
    "signal": HUMAN,
    "predicate_op": HUMAN,
    "predicate_value": HUMAN,
    "check_at_year": HUMAN,
    "registered_at": DERIVED,
    "status": DERIVED,
    "graded_at": DERIVED,
    "actual_value": DERIVED,
}


def validate(row) -> list[str]:
    """Validate one prediction row. Returns a list of errors; empty is valid.

    Beyond per-field types, this enforces the two requirements from the module
    docstring: `signal` must resolve to a gradeable ledger field, and a
    presence op (`exists`/`not_exists`) must not carry a comparison value.
    """
    if not isinstance(row, dict):
        return ["row: expected an object"]

    errors: list[str] = []
    known = {f.name for f in FIELDS}
    for key in row:
        if key not in known:
            errors.append(f"row.{key}: not a field in the schema")

    for field in FIELDS:
        if field.name not in row:
            if field.required:
                errors.append(f"row.{field.name}: required field is missing")
            continue
        value = row[field.name]
        if value is None:
            if not field.nullable:
                errors.append(f"row.{field.name}: null is not allowed for this field")
            continue
        if field.type == "string" and (not isinstance(value, str) or not value):
            errors.append(f"row.{field.name}: expected a non-empty string")
        elif field.type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            errors.append(f"row.{field.name}: expected an integer")
        elif field.type == "vocab":
            vocab = {
                "predicate_op": PREDICATE_OPS,
                "status": PREDICTION_STATUS,
            }.get(field.name, ())
            if value not in vocab:
                errors.append(f"row.{field.name}: {value!r} is not in {vocab}")
        # "any" (predicate_value, actual_value) is intentionally unchecked —
        # the target type depends on the field the signal points at.

    if errors:
        return errors

    if row["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"row.schema_version: row is version {row['schema_version']}, "
            f"this code is version {SCHEMA_VERSION}"
        )

    # The write-time falsifiability gate. Deferred import: predictions/ must
    # not become a hard dependency of ledger/, only the reverse.
    from ..ledger.store import field_source

    source = field_source(row["signal"])
    if source is None:
        errors.append(f"row.signal: {row['signal']!r} does not resolve to a known ledger field")
    elif source not in GRADEABLE_SOURCES:
        errors.append(
            f"row.signal: {row['signal']!r} is {source}-sourced and must "
            f"never be graded (allowed: {sorted(GRADEABLE_SOURCES)})"
        )

    is_presence_op = row["predicate_op"] in PRESENCE_OPS
    if is_presence_op and row["predicate_value"] is not None:
        errors.append(
            f"row.predicate_value: must be null when predicate_op is "
            f"{row['predicate_op']!r}"
        )
    if not is_presence_op and row["predicate_value"] is None:
        errors.append(
            f"row.predicate_value: required (non-null) when predicate_op is "
            f"{row['predicate_op']!r}"
        )

    return errors


def new_prediction(
    prediction_id: str, fort_id: str, decision: str, expectation: str,
    signal: str, predicate_op: str, predicate_value, check_at_year: int,
    registered_at: str,
) -> dict:
    """Build a freshly-registered prediction row: ungraded, status=pending."""
    return {
        "schema_version": SCHEMA_VERSION,
        "prediction_id": prediction_id,
        "fort_id": fort_id,
        "decision": decision,
        "expectation": expectation,
        "signal": signal,
        "predicate_op": predicate_op,
        "predicate_value": predicate_value,
        "check_at_year": check_at_year,
        "registered_at": registered_at,
        "status": PENDING,
        "graded_at": None,
        "actual_value": None,
    }
