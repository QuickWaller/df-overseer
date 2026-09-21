"""Run #1's real proposal (`evals/live/2026-09-14-architect-first-charter/run.json`,
the `final` field's fenced XML block) parsed into a dfqueue record and run
through `schema.validate` for real.

This is the brief's own honesty check, run twice over. First, verbatim: does
the raw XML `dfqueue` inherited from the first proposal-queue stream still
fail, and on exactly the check the earlier stream documented? Second,
corrected: `handoffs/2026-09-15-live-signals-sqlite.md` closed the actual gap
(no mid-fort signal registry existed) by adding `learning.live_signals` — so
this file also proves that swapping *only* the prediction's `signal` for the
new registry's quoted-landmark shape, `landmark."<name>".exit."Wagon".
distance_tiles`, makes the same real proposal validate and then grade for
real, coordinate-free the whole way through. Nothing here was loosened to
get that result: the real gap (no mid-fort signal store) is what got built.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from dfqueue import grade as dfqueue_grade
from dfqueue import schema, store
from dfqueue.tests._helpers import make_executed, make_ruling
from learning.predictions.schema import GRADED_FALSE, GRADED_TRUE

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
    """Does run #1's real proposal, verbatim, pass dfqueue's write-time gate?
    No — and exactly one check refuses it, the prediction's `signal`:
    `landmarks.new_workshop.exit_to_Wagon.distance_tiles` is neither a known
    live signal (`learning.live_signals`'s grammar requires a quoted
    landmark name, `landmark."new_workshop".exit."Wagon".distance_tiles`)
    nor a ledger field (`learning/ledger/schema.py`'s `FORT_FIELDS` has no
    top-level `landmarks` at all). Coordinates, cost, priority, role, type
    and preconditions all pass; nothing here was loosened to get that
    result.
    """
    record = _load_run1_proposal()
    errors = schema.validate(record)

    non_prediction_errors = [e for e in errors if not e.startswith("record.prediction")]
    assert non_prediction_errors == [], (
        f"expected every non-prediction check to pass, got: {non_prediction_errors}"
    )

    assert len(errors) == 1, f"expected exactly one refusal, got: {errors}"
    assert "not a known live signal" in errors[0]
    assert "landmarks.new_workshop.exit_to_Wagon.distance_tiles" in errors[0]


def test_run1_proposal_is_refused_by_append_and_writes_nothing(tmp_path):
    record = _load_run1_proposal()
    path = tmp_path / "queue.sqlite3"

    with pytest.raises(store.QueueError, match="not a known live signal"):
        store.append(record, path, game_tick=178877)

    assert store.load(path) == []


# ---- the corrected, quoted-landmark form: closes the real gap -----------------


def _corrected_signal(workshop_name: str = "new_workshop") -> str:
    """`handoffs/2026-09-15-live-signals-sqlite.md`'s own worked case: run
    #1's proposal, unchanged except its prediction's `signal`, rewritten
    into `learning.live_signals`'s quoted-landmark grammar. `new_workshop`
    is a placeholder the fixture itself names (per the brief) — at proposal
    time no such landmark exists yet, which is exactly the "unresolvable,
    not an error" case `learning.live_signals` is built to allow."""
    return f'landmark."{workshop_name}".exit."Wagon".distance_tiles'


def test_run1_proposal_with_the_corrected_signal_validates_clean():
    record = _load_run1_proposal()
    record["prediction"]["signal"] = _corrected_signal()
    assert schema.validate(record) == []


def test_run1_proposal_with_the_corrected_signal_is_appended_and_graded_true(tmp_path):
    """End to end: append the corrected proposal, accept and execute it
    (`docs/AGENT-LOOP.md` item 4: the window starts at execution, not at
    write time, so this now needs a ruling and an `executed` record before
    the prediction is due at all), so its prediction becomes a pending row
    due at the EXECUTION tick + 1200, matching the XML's own
    `check_after_ticks="1200"`), then grade it once the workshop exists and
    sits 7 tiles from the Wagon — `op="lte" value="7"` — and confirm it
    grades true."""
    record = _load_run1_proposal()
    record["prediction"]["signal"] = _corrected_signal()

    path = tmp_path / "queue.sqlite3"
    written = store.append(record, path, game_tick=178877)
    assert written["prediction"]["check_after_ticks"] == 1200

    # Not due at all yet -- not even armed, with no ruling or execution.
    assert store.pending_due(path, 10**9) == []

    ruling = store.append(make_ruling(proposal_id=written["id"]), path)
    store.append(make_executed(ruling_id=ruling["id"], cycle=178877), path)
    # Now armed from the execution tick: due at 178877 + 1200.

    due_before = store.pending_due(path, 178877 + 1199)
    assert due_before == []

    def call_tool(tool_id, arguments):
        if tool_id == "landmarks.get" and arguments == {"name": "new_workshop"}:
            return {
                "name": "new_workshop",
                "kind": "Mason's Workshop",
                "exits": [{"to": "Wagon", "direction": "N", "distance_tiles": 7, "walkable": True}],
            }
        raise AssertionError(f"unexpected call: {tool_id} {arguments}")

    updates = dfqueue_grade.grade_due(
        path, 178877 + 1200, call_tool, graded_at="2026-09-16T00:00:00+00:00",
    )
    assert len(updates) == 1
    assert updates[0]["status"] == GRADED_TRUE
    assert updates[0]["actual_value"] == 7

    assert store.pending_due(path, 178877 + 1200) == []  # graded, no longer pending


def test_run1_proposal_grades_false_if_the_workshop_lands_further_than_predicted(tmp_path):
    record = _load_run1_proposal()
    record["prediction"]["signal"] = _corrected_signal()

    path = tmp_path / "queue.sqlite3"
    written = store.append(record, path, game_tick=178877)
    ruling = store.append(make_ruling(proposal_id=written["id"]), path)
    store.append(make_executed(ruling_id=ruling["id"], cycle=178877), path)

    def call_tool(tool_id, arguments):
        return {
            "name": "new_workshop", "kind": "Mason's Workshop",
            "exits": [{"to": "Wagon", "direction": "N", "distance_tiles": 12, "walkable": True}],
        }

    updates = dfqueue_grade.grade_due(
        path, 178877 + 1200, call_tool, graded_at="2026-09-16T00:00:00+00:00",
    )
    assert updates[0]["status"] == GRADED_FALSE
    assert updates[0]["actual_value"] == 12


def test_run1_proposal_grades_unresolvable_if_the_workshop_still_does_not_exist(tmp_path):
    record = _load_run1_proposal()
    record["prediction"]["signal"] = _corrected_signal()

    path = tmp_path / "queue.sqlite3"
    written = store.append(record, path, game_tick=178877)
    ruling = store.append(make_ruling(proposal_id=written["id"]), path)
    store.append(make_executed(ruling_id=ruling["id"], cycle=178877), path)

    def call_tool(tool_id, arguments):
        return {"error": "not found"}

    from learning.predictions.schema import UNRESOLVABLE as UNRESOLVABLE_STATUS

    updates = dfqueue_grade.grade_due(
        path, 178877 + 1200, call_tool, graded_at="2026-09-16T00:00:00+00:00",
    )
    assert updates[0]["status"] == UNRESOLVABLE_STATUS
    assert updates[0]["actual_value"] is None


def test_a_ruling_could_reference_run1s_proposal_id_once_it_is_appendable():
    # Documents the id run #1 actually used, so a future ruling fixture can
    # reference it directly once a real prediction signal exists.
    record = _load_run1_proposal()
    assert record["id"] == "p-0001"
    ruling = make_ruling(proposal_id="p-0001")
    assert schema.validate(ruling) == []
