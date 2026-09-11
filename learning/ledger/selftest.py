"""Checks on the ledger itself. Run before trusting any row it holds.

    python -m ledger.selftest

Two kinds of check live here, and the second kind is the point.

**Positive checks** confirm a good row validates and the store round-trips.
Those are easy and prove little on their own.

**Negative checks** confirm the validator actually *catches* each rule it
claims to enforce. A validator nobody has fed a bad row is a validator with no
evidence behind it. This repo's standing rule is "before reporting an
all-clear, confirm the check you ran could actually have detected the problem
in question." Every cross-field rule in `schema.validate` therefore has a
matching row here that breaks it, and the test fails if the breakage sails
through.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

from .schema import (
    CONTRIBUTING_FACTOR,
    DESIGN_FIELDS,
    DIAGNOSTICITY,
    FORT_FIELDS,
    OBSERVATION_RELATION,
    RECORD_FIELDS,
    UNRECORDED,
    Field,
    blank_row,
    validate,
)
from . import store

EXAMPLE = Path(__file__).resolve().parent / "examples" / "example-fort.json"

# The two vocabularies that deliberately have no `unrecorded` member: both
# describe a judgement that only exists because someone made it. An
# observation with `unrecorded` diagnosticity is not a weak observation, it is
# an absent one, and should be left out of the list entirely.
VOCABS_WITHOUT_UNRECORDED = {DIAGNOSTICITY, OBSERVATION_RELATION}

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")


def _all_fields() -> list[tuple[str, Field]]:
    out = [("row", f) for f in FORT_FIELDS]
    for record, fields in RECORD_FIELDS.items():
        out.extend((record, f) for f in fields)
    return out


# ---- 1. the schema is internally consistent -------------------------------


def check_schema_consistency() -> None:
    print("schema consistency")

    for where, field in _all_fields():
        if field.type == "vocab":
            check(
                f"{where}.{field.name} has a vocabulary",
                field.vocab is not None,
            )
        if field.type.startswith(("object:", "record_list:")):
            sub = field.type.split(":", 1)[1]
            check(
                f"{where}.{field.name} points at a real record type",
                sub in RECORD_FIELDS,
                f"{sub!r} is not in RECORD_FIELDS",
            )

    # Section 3.2's core rule, checked structurally: every vocabulary that
    # describes an observation of the world must be able to say "we did not
    # record this", or an absent measurement gets silently coded as a value.
    for where, field in _all_fields():
        if field.type != "vocab" or field.vocab is None:
            continue
        if field.vocab in VOCABS_WITHOUT_UNRECORDED:
            continue
        check(
            f"{where}.{field.name} vocabulary can express 'unrecorded'",
            UNRECORDED in field.vocab,
        )

    for vocab_name, vocab in (
        ("DIAGNOSTICITY", DIAGNOSTICITY),
        ("OBSERVATION_RELATION", OBSERVATION_RELATION),
        ("CONTRIBUTING_FACTOR", CONTRIBUTING_FACTOR),
    ):
        check(
            f"{vocab_name} has no duplicate members",
            len(set(vocab)) == len(vocab),
        )

    # A ledger that cannot record its own operator's mistakes will read as a
    # success story regardless of what happened. Checked, not just intended.
    for required in ("agent_error", "fps_collapse", "human_intervention"):
        check(
            f"CONTRIBUTING_FACTOR can record {required!r}",
            required in CONTRIBUTING_FACTOR,
        )

    # Orthogonality (module docstring): entrance choices must be separate
    # fields or the one-variable-at-a-time selector has nothing to vary.
    design_names = {f.name for f in DESIGN_FIELDS}
    check(
        "entrance design is split into orthogonal axes",
        {"entrance_count", "entrance_seal", "entrance_traps"} <= design_names,
        f"got {sorted(n for n in design_names if 'entrance' in n)}",
    )
    check(
        "there is no bundled `entrance_design` field",
        "entrance_design" not in design_names,
    )


# ---- 2. a good row validates ----------------------------------------------


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def check_example_valid() -> None:
    print("the worked example")
    row = load_example()
    errors = validate(row)
    check("example row validates clean", not errors, "; ".join(errors))

    # Independent re-derivation: recompute the DERIVED field a second way
    # rather than trusting the validator that just passed it.
    expected = row["outcome"]["end_year"] - row["embark"]["start_year"]
    check(
        "example duration_years re-derives correctly",
        row["outcome"]["duration_years"] == expected,
        f"stored {row['outcome']['duration_years']}, recomputed {expected}",
    )

    check(
        "example is not in the real ledger",
        all(
            r["fort_id"] != row["fort_id"]
            for r in store.load(store.DEFAULT_PATH)
        ),
        "invented data has leaked into forts.jsonl",
    )


# ---- 3. the validator catches what it claims to catch ---------------------


def check_validator_catches() -> None:
    print("negative checks (does the validator actually fire?)")
    good = load_example()

    def breaks(name: str, mutate, expect_substring: str) -> None:
        row = copy.deepcopy(good)
        mutate(row)
        errors = validate(row)
        hit = any(expect_substring in e for e in errors)
        check(
            name,
            hit,
            f"expected an error mentioning {expect_substring!r}, got {errors}",
        )

    breaks(
        "rejects a value outside a vocabulary",
        lambda r: r["design"].__setitem__("entrance_seal", "portcullis"),
        "vocabulary",
    )
    breaks(
        "rejects a missing required field",
        lambda r: r["design"].pop("entrance_count"),
        "required field is missing",
    )
    breaks(
        "rejects an unknown field (a typo'd key is silent data loss)",
        lambda r: r["design"].__setitem__("entrence_seal", "door"),
        "not a field in the schema",
    )
    breaks(
        "rejects null in a non-nullable field",
        lambda r: r["design"].__setitem__("entrance_seal", None),
        "null is not allowed",
    )
    breaks(
        "rejects a bool where an integer belongs",
        lambda r: r["design"].__setitem__("entrance_count", True),
        "expected an integer",
    )
    breaks(
        "rejects a dead fort with no contributing factors (rule 3)",
        lambda r: r["outcome"].__setitem__("contributing_factors", []),
        "at least one contributing factor",
    )
    breaks(
        "rejects tied contributing-factor ranks",
        lambda r: r["outcome"]["contributing_factors"][1].__setitem__("rank", 1),
        "ranks must be 1..n",
    )
    breaks(
        "rejects a duration that disagrees with its inputs",
        lambda r: r["outcome"].__setitem__("duration_years", 99),
        "disagrees with",
    )
    breaks(
        "rejects a multi-variable 'experiment'",
        lambda r: r["experiment"].__setitem__(
            "variable", "design.entrance_seal,design.entrance_traps"
        ),
        "one field only",
    )
    breaks(
        "rejects a row from a different schema version",
        lambda r: r.__setitem__("schema_version", 99),
        "schema_version",
    )
    breaks(
        "rejects a bad nested record inside a list",
        lambda r: r["threat_log"][0].__setitem__("kind", "dragon"),
        "vocabulary",
    )

    # blank_row is meant to be an unfinished template, not a shippable row.
    blank = blank_row("x", "w", "s", "X", "2026-08-27")
    check(
        "blank_row is deliberately invalid until filled in",
        bool(validate(blank)),
        "a blank template validated clean, which invites placeholder data",
    )


# ---- 4. the store ---------------------------------------------------------


def check_store() -> None:
    print("store behaviour")
    good = load_example()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "forts.jsonl"

        check("load of a missing ledger returns empty", store.load(path) == [])

        store.append(good, path)
        rows = store.load(path)
        check("append then load round-trips one row", len(rows) == 1)
        check("round-tripped row is unchanged", rows[0] == good)

        try:
            store.append(good, path)
            check("append refuses a duplicate fort_id", False, "it accepted one")
        except store.LedgerError:
            check("append refuses a duplicate fort_id", True)

        bad = copy.deepcopy(good)
        bad["fort_id"] = "other"
        bad["design"]["entrance_seal"] = "portcullis"
        try:
            store.append(bad, path)
            check("append refuses an invalid row", False, "it accepted one")
        except store.LedgerError:
            check("append refuses an invalid row", True)

        # A corrupt line must stop the load, not be skipped: skipping shrinks
        # an already tiny sample without changing any visible count.
        path.write_text(
            json.dumps(good) + "\n" + '{"fort_id": "truncated"}\n',
            encoding="utf-8",
        )
        try:
            store.load(path)
            check("load raises on an invalid row rather than skipping it", False,
                  "it silently dropped the bad row")
        except store.LedgerError:
            check("load raises on an invalid row rather than skipping it", True)

    # get_path, including list indexing
    check(
        "get_path reads a nested scalar",
        store.get_path(good, "design.entrance_seal") == "drawbridge",
    )
    check(
        "get_path indexes into a list",
        store.get_path(good, "threat_log.2.breach_location")
        == "Lower Mushroom Gallery",
    )
    check("get_path returns None for a bad path",
          store.get_path(good, "design.nope") is None)


# ---- 5. stratification refuses to pool `unrecorded` -----------------------


def check_stratify() -> None:
    print("stratification")
    good = load_example()

    a = copy.deepcopy(good)
    a["fort_id"] = "a"
    b = copy.deepcopy(good)
    b["fort_id"] = "b"
    b["design"]["entrance_seal"] = "none"
    c = copy.deepcopy(good)
    c["fort_id"] = "c"
    c["design"]["entrance_seal"] = UNRECORDED

    result = store.stratify([a, b, c], "design.entrance_seal")
    check(
        "unrecorded rows are dropped, not made into a bucket",
        all(s.value != UNRECORDED for s in result.strata),
    )
    check("two strata remain", len(result.strata) == 2, result.summary())
    check("the dropped count is reported", result.dropped_unrecorded == 1)
    check("usable + dropped == total",
          result.usable + result.dropped_unrecorded == result.total_rows)

    cov = store.coverage([a, b, c], ["design.entrance_seal"])
    check(
        "coverage counts only recorded values",
        cov["design.entrance_seal"] == 2,
        str(cov),
    )

    # The grading guard: AGENT-sourced fields must be refused.
    try:
        store.assert_gradeable("notes")
        check("assert_gradeable refuses an AGENT field", False, "it allowed `notes`")
    except store.LedgerError:
        check("assert_gradeable refuses an AGENT field", True)

    try:
        store.assert_gradeable("observations.0.rationale")
        check("assert_gradeable refuses a HUMAN field", False,
              "it allowed a human-written rationale")
    except store.LedgerError:
        check("assert_gradeable refuses a HUMAN field", True)

    try:
        store.assert_gradeable("design.entrance_seal")
        check("assert_gradeable allows a MECHANICAL field", True)
    except store.LedgerError as exc:
        check("assert_gradeable allows a MECHANICAL field", False, str(exc))


def main() -> int:
    print("fort ledger selftest\n")
    check_schema_consistency()
    print()
    check_example_valid()
    print()
    check_validator_catches()
    print()
    check_store()
    print()
    check_stratify()

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
