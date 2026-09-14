"""Run #1's real proposal (`evals/live/2026-09-14-architect-first-charter/run.json`,
the `final` field's fenced XML block) parsed into a dfqueue record and run
through `schema.validate` for real.

This is the brief's own honesty check: does not loosen
`learning.predictions` to make a live proposal pass, and reports exactly
which check refuses it if any do.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from dfqueue import schema, store
from dfqueue.tests._helpers import make_ruling

RUN1_PATH = (
    Path(__file__).resolve().parents[2]
    / "evals" / "live" / "2026-09-14-architect-first-charter" / "run.json"
)

_XML_FENCE = re.compile(r"```xml\s*\n(.*?)```", re.DOTALL)


def _load_run1_proposal() -> dict:
    data = json.loads(RUN1_PATH.read_text(encoding="utf-8"))
    match = _XML_FENCE.search(data["final"])
    assert match, "no ```xml fenced block found in run #1's `final` field"
    elem = ET.fromstring(match.group(1).strip())
    assert elem.tag == "proposal"

    preconditions = []
    for requires in elem.find("preconditions").findall("requires"):
        item = {"state": requires.get("state")}
        if requires.get("landmark") is not None:
            item["landmark"] = requires.get("landmark")
        else:
            item["area"] = requires.get("area")
        preconditions.append(item)

    pred = elem.find("prediction")
    value = pred.get("value")
    try:
        value = int(value)
    except (TypeError, ValueError):
        pass

    cost = elem.find("cost")

    return {
        "kind": "proposal",
        "id": elem.get("id"),
        "role": elem.get("role"),
        "cycle": int(elem.get("cycle")),
        "snapshot": elem.get("snapshot"),
        "type": elem.find("type").text.strip(),
        "summary": elem.find("summary").text.strip(),
        "rationale": elem.find("rationale").text.strip(),
        "prediction": {
            "signal": pred.get("signal"),
            "op": pred.get("op"),
            "value": value,
            "check_after_ticks": int(pred.get("check_after_ticks")),
        },
        "cost": {"estimate": int(cost.get("estimate")), "unit": cost.get("unit")},
        "suggested_priority": int(elem.find("suggested_priority").text.strip()),
        "preconditions": preconditions,
        "public_rationale": elem.find("public_rationale").text.strip(),
    }


def test_run1_fixture_parses_the_expected_shape():
    record = _load_run1_proposal()
    assert record["id"] == "p-0001"
    assert record["role"] == "architect"
    assert record["type"] == "workshop_siting"
    assert record["prediction"]["signal"] == (
        "landmarks.new_workshop.exit_to_Wagon.distance_tiles"
    )
    assert record["prediction"]["op"] == "lte"
    assert record["prediction"]["check_after_ticks"] == 1200


def test_run1_proposal_fails_write_time_validation_on_its_prediction_only():
    """The brief's central question: does run #1's real proposal pass
    dfqueue's write-time gate today? No — and exactly one check refuses it,
    the prediction's `signal`, because `landmarks.*` has no matching
    top-level field in `learning/ledger/schema.py`'s `FORT_FIELDS` (the
    ledger is one row per fort, written mostly at embark and at the end, not
    a live perception/landmarks store). Coordinates, cost, priority, role,
    type and preconditions all pass; nothing here was loosened to get that
    result.
    """
    record = _load_run1_proposal()
    errors = schema.validate(record)

    non_prediction_errors = [e for e in errors if not e.startswith("record.prediction")]
    assert non_prediction_errors == [], (
        f"expected every non-prediction check to pass, got: {non_prediction_errors}"
    )

    assert len(errors) == 1, f"expected exactly one refusal, got: {errors}"
    assert "does not resolve to a known ledger field" in errors[0]
    assert "landmarks.new_workshop.exit_to_Wagon.distance_tiles" in errors[0]


def test_run1_proposal_is_refused_by_append_and_writes_nothing(tmp_path):
    record = _load_run1_proposal()
    path = tmp_path / "queue.jsonl"

    with pytest.raises(store.QueueError, match="does not resolve to a known ledger field"):
        store.append(record, path)

    assert not path.exists()


def test_a_ledger_rooted_signal_in_the_same_shape_would_have_passed():
    """Proof that the refusal is about the *signal*, not about run #1's
    proposal in general: swap only `prediction.signal` for a real ledger
    field of the same type and the whole record validates clean."""
    record = _load_run1_proposal()
    record["prediction"]["signal"] = "design.entrance_count"
    record["prediction"]["op"] = "gte"
    record["prediction"]["value"] = 1
    assert schema.validate(record) == []


def test_a_ruling_could_reference_run1s_proposal_id_once_it_is_appendable():
    # Documents the id run #1 actually used, so a future ruling fixture can
    # reference it directly once a real prediction signal exists.
    record = _load_run1_proposal()
    assert record["id"] == "p-0001"
    ruling = make_ruling(proposal_id="p-0001")
    assert schema.validate(ruling) == []
