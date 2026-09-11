"""Mechanical prediction grading. No model is ever asked to judge its own prediction.

Build order item 3 (`research/2026-08-25-learning-architecture.md` §7):
"a scripted comparison of a `signal` field against recorded state at
`check_at`." This is that comparison — nothing here reads `decision` or
`expectation` (the prose fields); grading only ever touches `signal`,
`predicate_op`/`predicate_value`, and the ledger row they resolve against.
Matches the register's standing position (2026-08-25: "All learning grading
is mechanical") and `docs/MEMORY-ARCHITECTURE.md`'s explicit rule: "never
grade the agent's account of its own learning."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ledger.schema import UNRECORDED
from ..ledger.store import assert_gradeable, get_path

from .schema import (
    CONTAINS, EQ, EXISTS, GRADED_FALSE, GRADED_TRUE, GT, GTE, IN, LT, LTE,
    NE, NOT_EXISTS, PENDING, PRESENCE_OPS, UNRESOLVABLE,
)


class GradingError(Exception):
    """Raised when a prediction cannot even be attempted — not a graded outcome."""


@dataclass
class GradeResult:
    status: str  # pending | graded_true | graded_false | unresolvable
    actual_value: Any
    note: str = ""


def _apply(op: str, actual, target) -> bool:
    if op == EQ:
        return actual == target
    if op == NE:
        return actual != target
    if op == GTE:
        return actual >= target
    if op == LTE:
        return actual <= target
    if op == GT:
        return actual > target
    if op == LT:
        return actual < target
    if op == IN:
        return actual in target
    if op == CONTAINS:
        return target in actual
    raise GradingError(f"unhandled predicate_op {op!r}")  # PRESENCE_OPS handled by the caller


def grade(prediction: dict, ledger_row: dict, current_year: int | None = None) -> GradeResult:
    """Grade one prediction against one ledger row.

    `current_year` is optional and exists for a fort that is still alive: pass
    the fort's current in-game year to get a `pending` result rather than a
    premature grade when `check_at_year` has not arrived yet. Omit it once a
    fort has actually ended — the ledger row is then the final word regardless
    of any particular year.
    """
    signal = prediction["signal"]
    assert_gradeable(signal)  # raises if signal is not MECHANICAL/DERIVED — defense
    # in depth: schema.validate already refused this at registration time, but
    # grading re-checks rather than trusting a row it did not itself validate.

    if current_year is not None and current_year < prediction["check_at_year"]:
        return GradeResult(PENDING, None, "check_at_year has not arrived yet")

    value = get_path(ledger_row, signal)
    op = prediction["predicate_op"]

    if op in PRESENCE_OPS:
        present = value is not None and value != UNRECORDED
        ok = present if op == EXISTS else not present
        return GradeResult(GRADED_TRUE if ok else GRADED_FALSE, value)

    if value is None or value == UNRECORDED:
        return GradeResult(UNRESOLVABLE, value, "signal is not yet recorded in the ledger")

    ok = _apply(op, value, prediction["predicate_value"])
    return GradeResult(GRADED_TRUE if ok else GRADED_FALSE, value)


def apply_grade(prediction: dict, result: GradeResult, graded_at: str) -> dict:
    """Return a copy of `prediction` with the grade applied.

    Never mutates in place — the caller (`store.rewrite_all`) is what commits
    a change, so a grading pass that finds nothing to update touches nothing.
    """
    if result.status == PENDING:
        return prediction
    updated = dict(prediction)
    updated["status"] = result.status
    updated["graded_at"] = graded_at
    updated["actual_value"] = result.actual_value
    return updated


def grade_all(
    predictions: list[dict], ledger_rows_by_fort_id: dict[str, dict],
    graded_at: str, current_year: int | None = None,
) -> list[dict]:
    """Grade every still-`pending` prediction that has a matching ledger row.

    A prediction whose `fort_id` has no ledger row yet is left untouched
    (not `unresolvable` — the fort simply hasn't been written yet, which is a
    different fact from "the field is unrecorded").
    """
    out = []
    for p in predictions:
        if p["status"] != PENDING:
            out.append(p)
            continue
        row = ledger_rows_by_fort_id.get(p["fort_id"])
        if row is None:
            out.append(p)
            continue
        result = grade(p, row, current_year=current_year)
        out.append(apply_grade(p, result, graded_at))
    return out
