"""Checks on the prediction log itself. Run before trusting any grade it produces.

    python -m predictions.selftest

Mirrors `ledger/selftest.py`'s philosophy: negative checks matter more than
positive ones. A validator nobody has fed a bad prediction is a validator with
no evidence behind it — this repo's standing rule is "confirm the check you
ran could actually have detected the problem," so every rule `schema.validate`
and `grade.grade` claim to enforce has a matching case here that breaks it.

Reuses `ledger`'s own worked example (`ledger/examples/example-fort.json`) as
the ledger row predictions grade against, rather than inventing a second
fixture that could quietly drift from the real schema.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

from ..ledger.selftest import EXAMPLE as EXAMPLE_FORT_PATH
from . import grade as grade_mod
from . import store
from .schema import (
    EQ, EXISTS, GRADED_FALSE, GRADED_TRUE, GTE, LTE, NOT_EXISTS, PENDING,
    UNRESOLVABLE, new_prediction, validate,
)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")


def load_example_fort() -> dict:
    return json.loads(EXAMPLE_FORT_PATH.read_text(encoding="utf-8"))


def _good() -> dict:
    return new_prediction(
        prediction_id="pred-001",
        fort_id="EXAMPLE-ironbound-y205",
        decision="seal the caverns early",
        expectation="caverns will be recorded as sealed by year 210",
        signal="design.caverns_sealed_year",
        predicate_op=LTE,
        predicate_value=210,
        check_at_year=210,
        registered_at="2026-09-11",
    )


# ---- 1. write-time falsifiability gate (research 1.3) ---------------------


def check_write_time_gate() -> None:
    print("write-time falsifiability gate")

    good = _good()
    check("a well-formed prediction validates clean", not validate(good), str(validate(good)))

    def breaks(name: str, mutate, expect_substring: str) -> None:
        row = copy.deepcopy(good)
        mutate(row)
        errors = validate(row)
        hit = any(expect_substring in e for e in errors)
        check(name, hit, f"expected an error mentioning {expect_substring!r}, got {errors}")

    breaks(
        "rejects a signal pointing at an AGENT field (notes)",
        lambda r: r.__setitem__("signal", "notes"),
        "must never be graded",
    )
    breaks(
        "rejects a signal pointing at a HUMAN field (an observation's rationale)",
        lambda r: r.__setitem__("signal", "observations.0.rationale"),
        "must never be graded",
    )
    breaks(
        "rejects a signal that doesn't resolve to any ledger field",
        lambda r: r.__setitem__("signal", "nonsense.path.here"),
        "does not resolve",
    )
    breaks(
        "rejects a comparison op with no predicate_value",
        lambda r: (r.__setitem__("predicate_op", EQ), r.__setitem__("predicate_value", None)),
        "required (non-null)",
    )
    breaks(
        "rejects a presence op carrying a predicate_value",
        lambda r: (r.__setitem__("predicate_op", EXISTS), r.__setitem__("predicate_value", "x")),
        "must be null",
    )
    breaks(
        "rejects an unknown predicate_op",
        lambda r: r.__setitem__("predicate_op", "roughly_equals"),
        "is not in",
    )
    breaks(
        "rejects a value outside the status vocabulary",
        lambda r: r.__setitem__("status", "sort_of_true"),
        "is not in",
    )
    breaks(
        "rejects an unknown field (a typo'd key is silent data loss)",
        lambda r: r.__setitem__("sgnal", "design.entrance_count"),
        "not a field in the schema",
    )
    breaks(
        "rejects a row from a different schema version",
        lambda r: r.__setitem__("schema_version", 99),
        "schema_version",
    )


# ---- 2. grading is mechanical and matches the ledger row -------------------


def check_grading() -> None:
    print("grading")
    fort = load_example_fort()

    def graded(signal, op, value, expect_status, expect_value=None):
        p = new_prediction(
            "p", fort["fort_id"], "d", "e", signal, op, value, 999, "2026-09-11",
        )
        result = grade_mod.grade(p, fort)
        name = f"{signal} {op} {value!r} -> {expect_status}"
        check(name, result.status == expect_status,
              f"got status={result.status} actual_value={result.actual_value!r}")
        if expect_status != UNRESOLVABLE and expect_value is not None:
            check(f"{name} (actual_value recorded)", result.actual_value == expect_value)

    # True and false comparisons against the same real fixture fields the
    # ledger's own selftest already trusts, not invented numbers.
    graded("design.caverns_sealed_year", LTE, 210, GRADED_TRUE, 208)
    graded("outcome.total_deaths", LTE, 10, GRADED_FALSE, 47)
    graded("design.caverns_sealed", EQ, "sealed", GRADED_FALSE, "partial")
    graded("outcome.status", EQ, "dead_abandoned", GRADED_TRUE, "dead_abandoned")
    graded("design.max_depth_z", EXISTS, None, GRADED_TRUE, 42)

    # A legitimately-null field (no breach happened) — not_exists is the
    # correct way to predict "no breach," and it must not read as unresolvable
    # just because the underlying value is None.
    graded("threat_log.0.breach_location", NOT_EXISTS, None, GRADED_TRUE)

    # Genuinely not-yet-recorded (an alive fort's not-yet-final field) must
    # come back unresolvable, not silently graded false. Grade a fresh dict
    # rather than the ended-fort fixture: grade() only ever reads via
    # get_path, so it does not need a schema-valid ledger row to exercise.
    alive = {"outcome": {"wealth_at_end": None}}
    p = new_prediction("p2", "some-alive-fort", "d", "e",
                        "outcome.wealth_at_end", GTE, 100000, 999, "2026-09-11")
    result = grade_mod.grade(p, alive)
    check("a not-yet-recorded field grades unresolvable, not false",
          result.status == UNRESOLVABLE, f"got {result.status}")

    # check_at_year not yet reached -> pending, regardless of what the ledger
    # row already says (a prediction is not "checked early" just because the
    # answer happens to already be knowable).
    p3 = new_prediction("p3", fort["fort_id"], "d", "e",
                         "outcome.total_deaths", LTE, 10, 300, "2026-09-11")
    early = grade_mod.grade(p3, fort, current_year=250)
    check("grading before check_at_year returns pending", early.status == PENDING)
    late = grade_mod.grade(p3, fort, current_year=300)
    check("grading at/after check_at_year actually grades",
          late.status in (GRADED_TRUE, GRADED_FALSE))

    # Defense in depth: grade() must re-check gradeability itself, not trust
    # that the row was ever validated.
    ungated = new_prediction("p4", fort["fort_id"], "d", "e",
                              "notes", EQ, "x", 999, "2026-09-11")
    try:
        grade_mod.grade(ungated, fort)
        check("grade() refuses an AGENT-sourced signal even if validation was skipped",
              False, "it graded an AGENT field")
    except Exception:
        check("grade() refuses an AGENT-sourced signal even if validation was skipped", True)


# ---- 3. the store -----------------------------------------------------------


def check_store() -> None:
    print("store behaviour")
    good = _good()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "predictions.jsonl"

        check("load of a missing log returns empty", store.load(path) == [])

        store.register(good, path)
        rows = store.load(path)
        check("register then load round-trips one row", len(rows) == 1)
        check("round-tripped row is unchanged", rows[0] == good)

        try:
            store.register(good, path)
            check("register refuses a duplicate prediction_id", False, "it accepted one")
        except store.PredictionError:
            check("register refuses a duplicate prediction_id", True)

        graded = copy.deepcopy(good)
        graded["prediction_id"] = "other"
        graded["status"] = GRADED_TRUE
        try:
            store.register(graded, path)
            check("register refuses a row that already carries a grade", False, "it accepted one")
        except store.PredictionError:
            check("register refuses a row that already carries a grade", True)

        invalid = copy.deepcopy(good)
        invalid["prediction_id"] = "other2"
        invalid["signal"] = "notes"
        try:
            store.register(invalid, path)
            check("register refuses an invalid (ungradeable-signal) row", False, "it accepted one")
        except store.PredictionError:
            check("register refuses an invalid (ungradeable-signal) row", True)

        # A corrupt line must stop the load, not be skipped.
        path.write_text(
            json.dumps(good) + "\n" + '{"prediction_id": "truncated"}\n',
            encoding="utf-8",
        )
        try:
            store.load(path)
            check("load raises on an invalid row rather than skipping it", False,
                  "it silently dropped the bad row")
        except store.PredictionError:
            check("load raises on an invalid row rather than skipping it", True)

    # rewrite_all persists a grade update in place.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "predictions.jsonl"
        store.register(good, path)
        rows = store.load(path)
        updated = grade_mod.apply_grade(
            rows[0], grade_mod.GradeResult(GRADED_TRUE, 208), "2026-09-12",
        )
        store.rewrite_all([updated], path)
        reloaded = store.load(path)
        check("rewrite_all persists a grade", reloaded[0]["status"] == GRADED_TRUE)
        check("rewrite_all persists graded_at", reloaded[0]["graded_at"] == "2026-09-12")
        check("rewrite_all persists actual_value", reloaded[0]["actual_value"] == 208)


# ---- 4. grade_all batches correctly, and leaves what it should alone ------


def check_grade_all() -> None:
    print("grade_all")
    fort = load_example_fort()

    p_hit = _good()  # caverns_sealed_year=208 <= 210 -> true
    p_no_fort = new_prediction("p-orphan", "no-such-fort", "d", "e",
                                "outcome.total_deaths", LTE, 10, 999, "2026-09-11")
    already = copy.deepcopy(_good())
    already["prediction_id"] = "p-already"
    already["status"] = GRADED_FALSE
    already["graded_at"] = "2026-01-01"
    already["actual_value"] = 999

    out = grade_mod.grade_all(
        [p_hit, p_no_fort, already],
        {fort["fort_id"]: fort},
        graded_at="2026-09-12",
    )
    by_id = {r["prediction_id"]: r for r in out}
    check("a matched pending prediction gets graded",
          by_id["pred-001"]["status"] == GRADED_TRUE)
    check("a prediction with no matching fort is left pending, not marked unresolvable",
          by_id["p-orphan"]["status"] == PENDING)
    check("an already-graded prediction is left untouched",
          by_id["p-already"]["status"] == GRADED_FALSE
          and by_id["p-already"]["graded_at"] == "2026-01-01")


def main() -> int:
    print("prediction log selftest\n")
    check_write_time_gate()
    print()
    check_grading()
    print()
    check_store()
    print()
    check_grade_all()

    print()
    if failures:
        print(f"{len(failures)} FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
