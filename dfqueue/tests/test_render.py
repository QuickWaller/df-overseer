"""`dfqueue.render`: the public-view allowlist (docs/AGENT-ARCHITECTURE.md §8)
and the XML prompt form (§4).

The allowlist test is the one that matters most here: step 2 (a later
stream) publishes straight from `public_view`, so this is the only thing
standing between the schema and the public stream. §8 is explicit that this
must be an allowlist, never a denylist, so the test proves it by adding a
brand-new field to a record and checking it never appears, rather than only
checking that today's known-sensitive fields are absent.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from dfqueue import render
from dfqueue.tests._helpers import (
    make_answer, make_ask, make_executed, make_pass, make_proposal,
    make_ruling,
)


def test_public_view_never_leaks_a_field_added_to_the_record():
    record = make_proposal(id="proposal-0001", ts="2026-09-14T00:00:00+00:00")
    record["totally_new_field_nobody_allowlisted"] = "should never appear"
    view = render.public_view(record)
    assert "totally_new_field_nobody_allowlisted" not in view
    assert "should never appear" not in view.values()


def test_public_view_of_a_proposal_carries_exactly_the_allowlisted_fields():
    record = make_proposal(id="proposal-0001", ts="2026-09-14T00:00:00+00:00")
    view = render.public_view(record)
    assert view == {
        "id": "proposal-0001",
        "ts": "2026-09-14T00:00:00+00:00",
        "kind": "proposal",
        "role": "architect",
        "type": "workshop_siting",
        "public_rationale": record["public_rationale"],
        "suggested_priority": 3,
    }
    # Internal-only fields never appear, even though they are on the record.
    for private_field in ("rationale", "prediction", "cost", "preconditions", "cycle", "snapshot"):
        assert private_field not in view


def test_public_view_of_a_ruling_carries_the_decision_not_the_private_reason():
    record = make_ruling(id="ruling-0001", ts="2026-09-14T00:00:00+00:00")
    view = render.public_view(record)
    assert view == {
        "id": "ruling-0001",
        "ts": "2026-09-14T00:00:00+00:00",
        "kind": "ruling",
        "role": "overseer",
        "public_rationale": record["public_rationale"],
        "decision": "accept",
    }
    assert "reason" not in view
    assert "proposal_id" not in view


def test_public_view_of_a_pass_carries_no_type_or_rationale_at_all():
    record = make_pass(id="pass-0001", ts="2026-09-14T00:00:00+00:00")
    view = render.public_view(record)
    assert view == {
        "id": "pass-0001",
        "ts": "2026-09-14T00:00:00+00:00",
        "kind": "pass",
        "role": "architect",
    }
    assert "reason" not in view


# ---- to_xml -----------------------------------------------------------------------


def test_to_xml_proposal_is_well_formed_and_escapes_special_characters():
    record = make_proposal(
        id="proposal-0001",
        rationale="Cost < benefit & the stair needs \"care\".",
    )
    xml = render.to_xml(record)
    root = ET.fromstring(xml)  # raises if not well-formed
    assert root.tag == "proposal"
    assert root.get("id") == "proposal-0001"
    assert root.find("rationale").text == "Cost < benefit & the stair needs \"care\"."
    prediction = root.find("prediction")
    assert prediction.get("signal") == "fort.population"
    assert prediction.get("check_after_ticks") == "1200"
    preconditions = root.find("preconditions").findall("requires")
    assert len(preconditions) == 2


def test_to_xml_pass_is_well_formed():
    record = make_pass(id="pass-0001")
    xml = render.to_xml(record)
    root = ET.fromstring(xml)
    assert root.tag == "pass"
    assert root.find("reason") is not None


def test_to_xml_ruling_is_well_formed():
    record = make_ruling(id="ruling-0001")
    xml = render.to_xml(record)
    root = ET.fromstring(xml)
    assert root.tag == "ruling"
    assert root.find("decision").text == "accept"
    assert root.find("proposal_id").text == "proposal-0001"


def test_to_xml_executed_is_well_formed_with_one_action_per_element():
    record = make_executed(
        id="executed-0001",
        actions=[
            {"tool": "workshop.build", "outcome": "success"},
            {"tool": "farm.set-crop", "outcome": "failure", "detail": "stale precondition"},
        ],
    )
    xml = render.to_xml(record)
    root = ET.fromstring(xml)
    assert root.tag == "executed"
    assert root.find("ruling_id").text == "ruling-0001"
    actions = root.find("actions").findall("action")
    assert len(actions) == 2
    assert actions[0].get("tool") == "workshop.build"
    assert actions[0].get("outcome") == "success"
    assert actions[1].get("detail") == "stale precondition"
    assert root.find("notes") is not None


def test_to_xml_ask_is_well_formed_with_and_without_a_proposal_id():
    xml = render.to_xml(make_ask(id="ask-0001"))
    root = ET.fromstring(xml)
    assert root.tag == "ask"
    assert root.find("question") is not None
    assert root.find("proposal_id") is None

    xml2 = render.to_xml(make_ask(id="ask-0002", role="overseer", proposal_id="proposal-0001"))
    root2 = ET.fromstring(xml2)
    assert root2.find("proposal_id").text == "proposal-0001"


def test_to_xml_answer_is_well_formed():
    record = make_answer(id="answer-0001")
    xml = render.to_xml(record)
    root = ET.fromstring(xml)
    assert root.tag == "answer"
    assert root.find("ask_id").text == "ask-0001"
    assert root.find("answer") is not None


def test_public_view_of_executed_carries_only_the_common_allowlisted_fields():
    record = make_executed(id="executed-0001", ts="2026-09-22T00:00:00+00:00")
    view = render.public_view(record)
    assert view == {
        "id": "executed-0001", "ts": "2026-09-22T00:00:00+00:00",
        "kind": "executed", "role": "overseer",
    }
    assert "ruling_id" not in view
    assert "actions" not in view
    assert "notes" not in view
