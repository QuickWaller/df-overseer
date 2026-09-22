"""Unit tests on `dfqueue.schema.validate` directly: every refusal the
handoff brief names, plus the type vocabulary and the coordinate scan.

Positive round-trips (append/load/to_xml) live in `test_store.py` and
`test_render.py`; this file is about the write-time gate itself.
"""

from __future__ import annotations

import copy

import pytest

from dfqueue import schema
from dfqueue.tests._helpers import (
    make_answer, make_ask, make_escalation, make_executed, make_pass,
    make_proposal, make_ruling,
)


def _errors_mentioning(errors: list[str], substring: str) -> list[str]:
    return [e for e in errors if substring in e]


# ---- valid records pass clean ------------------------------------------------


def test_valid_proposal_validates_clean():
    assert schema.validate(make_proposal()) == []


def test_valid_pass_validates_clean():
    assert schema.validate(make_pass()) == []


def test_valid_ruling_validates_clean():
    assert schema.validate(make_ruling()) == []


# ---- unknown kind or field ---------------------------------------------------


def test_unknown_kind_is_refused():
    record = make_proposal(kind="plan")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.kind")


def test_missing_kind_is_refused():
    record = make_proposal()
    del record["kind"]
    errors = schema.validate(record)
    assert errors == ["record.kind: required field is missing"]


def test_unknown_field_is_refused():
    record = make_proposal(extra_field="not part of the schema")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.extra_field: not a field in the proposal schema")


# ---- missing or empty required field -----------------------------------------


def test_missing_role_is_refused():
    record = make_proposal()
    del record["role"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.role")


def test_empty_summary_is_refused():
    record = make_proposal(summary="")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.summary: expected a non-empty string")


def test_missing_snapshot_is_refused():
    record = make_proposal()
    del record["snapshot"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.snapshot: required field is missing")


def test_missing_reason_on_pass_is_refused():
    record = make_pass()
    del record["reason"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.reason: required field is missing")


# ---- type not in the role's vocabulary ---------------------------------------


def test_architect_type_outside_its_vocabulary_is_refused():
    record = make_proposal(type="farm_siting")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.type")
    assert _errors_mentioning(errors, "'architect'")


def test_architect_may_use_every_type_in_its_own_vocabulary():
    for t in schema.ARCHITECT_TYPES:
        record = make_proposal(type=t)
        assert schema.validate(record) == [], f"{t} unexpectedly refused"


# ---- consultant proposal ------------------------------------------------------


def test_consultant_proposal_is_refused():
    record = make_proposal(role="consultant", type="room_siting")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "does not propose")


# ---- non-Overseer ruling ------------------------------------------------------


def test_ruling_from_a_non_sole_writer_role_is_refused():
    record = make_ruling(role="architect")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "sole_writer")


def test_ruling_from_the_overseer_is_accepted():
    record = make_ruling(role="overseer")
    assert schema.validate(record) == []


# ---- dangling proposal_id (store-level; see test_store.py) -------------------


def test_ruling_missing_proposal_id_is_refused():
    record = make_ruling()
    del record["proposal_id"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.proposal_id: required field is missing")


# ---- priority out of range ----------------------------------------------------


def test_priority_zero_is_refused():
    record = make_proposal(suggested_priority=0)
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.suggested_priority")


def test_priority_eight_is_refused():
    record = make_proposal(suggested_priority=8)
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.suggested_priority")


def test_priority_one_through_seven_all_accepted():
    for p in range(1, 8):
        record = make_proposal(suggested_priority=p)
        assert schema.validate(record) == [], f"priority {p} unexpectedly refused"


# ---- cost <= 0 ------------------------------------------------------------------


def test_cost_zero_is_refused():
    record = make_proposal(cost={"estimate": 0, "unit": "dwarf_ticks"})
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.cost.estimate")


def test_cost_negative_is_refused():
    record = make_proposal(cost={"estimate": -5, "unit": "dwarf_ticks"})
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.cost.estimate")


def test_cost_unknown_unit_is_refused():
    record = make_proposal(cost={"estimate": 10, "unit": "seconds"})
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.cost.unit")


# ---- coordinate in a text field --------------------------------------------------


def test_coordinate_x_equals_in_rationale_is_refused():
    record = make_proposal(rationale="Put the workshop at x=12, it is close enough.")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.rationale")
    assert _errors_mentioning(errors, "raw-coordinate")


def test_coordinate_z_equals_in_public_rationale_is_refused():
    record = make_proposal(public_rationale="This level is z=-3, deep enough to be safe.")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.public_rationale")


def test_bracketed_numeric_triple_in_summary_is_refused():
    record = make_proposal(summary="Dig the room at (4, 9, -2) near the stair.")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.summary")


def test_parenthesised_numeric_triple_in_reason_is_refused():
    record = make_pass(reason="Nothing viable was found near [4, 9, 2].")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.reason")


def test_coordinate_free_phrases_all_pass():
    # These must NOT be flagged: the regex has to stay conservative enough
    # to leave ordinary named-landmark/relative-direction prose alone
    # (docs/PURPOSE.md commitment #3), or advisors get trained to write
    # around the filter instead of using it as intended.
    phrases = [
        "5 tiles SE of Embark Site",
        "3x3",
        "level -1",
        "priority 4",
    ]
    for phrase in phrases:
        record = make_proposal(rationale=f"The candidate sits {phrase} from the wagon.")
        errors = schema.validate(record)
        assert _errors_mentioning(errors, "raw-coordinate") == [], (
            f"{phrase!r} was wrongly flagged as a coordinate: {errors}"
        )


# ---- bad prediction --------------------------------------------------------------


def test_prediction_signal_pointing_at_a_ledger_field_is_refused():
    # `notes` is a real ledger field (AGENT-sourced), but ledger fields --
    # gradeable or not -- are fort-level claims and belong in
    # learning/predictions/, not a dfqueue proposal.
    record = make_proposal(prediction={
        "signal": "notes", "op": "eq", "value": "x", "check_after_ticks": 100,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "fort-level claims belong in learning/predictions/")


def test_prediction_signal_pointing_at_a_gradeable_ledger_field_is_also_refused():
    # design.entrance_count is MECHANICAL (gradeable) in learning/ledger,
    # but that is exactly the case dfqueue must still refuse: gradeable
    # ledger fields belong to learning/predictions/, not to a proposal.
    record = make_proposal(prediction={
        "signal": "design.entrance_count", "op": "gte", "value": 1,
        "check_after_ticks": 1200,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "fort-level claims belong in learning/predictions/")


def test_prediction_signal_using_run1s_raw_unquoted_shape_is_refused():
    # The exact string run #1's real proposal used, before this stream's
    # quoting rule existed -- see dfqueue/tests/test_run1_fixture.py for the
    # corrected, quoted form that now passes.
    record = make_proposal(prediction={
        "signal": "landmarks.new_workshop.exit_to_Wagon.distance_tiles",
        "op": "lte", "value": 7, "check_after_ticks": 1200,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "not a known live signal")


def test_prediction_live_signal_with_a_quoted_landmark_name_is_accepted():
    record = make_proposal(prediction={
        "signal": 'landmark."Stockpile #2".exit."Wagon".distance_tiles',
        "op": "lte", "value": 7, "check_after_ticks": 1200,
    })
    assert schema.validate(record) == []


def test_prediction_unknown_predicate_op_is_refused():
    record = make_proposal(prediction={
        "signal": "fort.population", "op": "roughly_equals",
        "value": 1, "check_after_ticks": 100,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.prediction")


def test_prediction_presence_op_with_a_value_is_refused():
    record = make_proposal(prediction={
        "signal": "fort.stuck_jobs.count", "op": "exists",
        "value": "should be null", "check_after_ticks": 100,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "must be null")


def test_prediction_presence_op_without_a_value_is_accepted():
    record = make_proposal(prediction={
        "signal": "fort.stuck_jobs.count", "op": "exists",
        "check_after_ticks": 100,
    })
    assert schema.validate(record) == []


def test_prediction_missing_signal_is_refused():
    record = make_proposal(prediction={
        "op": "eq", "value": 1, "check_after_ticks": 100,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.prediction.signal: required field is missing")


def test_prediction_check_after_ticks_zero_is_refused():
    record = make_proposal(prediction={
        "signal": "fort.population", "op": "gte", "value": 1,
        "check_after_ticks": 0,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.prediction.check_after_ticks")


def test_prediction_check_after_ticks_negative_is_refused():
    record = make_proposal(prediction={
        "signal": "fort.population", "op": "gte", "value": 1,
        "check_after_ticks": -5,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.prediction.check_after_ticks")


def test_prediction_value_type_mismatch_against_an_integer_signal_is_refused():
    record = make_proposal(prediction={
        "signal": "fort.population", "op": "gte", "value": "fifteen",
        "check_after_ticks": 100,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "integer-valued")


def test_prediction_value_type_mismatch_against_a_boolean_signal_is_refused():
    record = make_proposal(prediction={
        "signal": 'landmark."Wagon".exists', "op": "eq", "value": 1,
        "check_after_ticks": 100,
    })
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "boolean-valued")


def test_prediction_boolean_value_against_a_boolean_signal_is_accepted():
    record = make_proposal(prediction={
        "signal": 'landmark."Wagon".exists', "op": "eq", "value": True,
        "check_after_ticks": 100,
    })
    assert schema.validate(record) == []


# ---- role must be enabled in agents/ROSTER.yaml -------------------------------


def test_disabled_role_is_refused():
    # marshal: still disabled in agents/ROSTER.yaml (quartermaster was enabled 2026-09-22).
    record = make_pass(role="marshal")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "not an enabled role")


def test_role_not_in_the_roster_at_all_is_refused():
    record = make_pass(role="wizard")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "not an enabled role")


# ---- the record passed to validate() is never mutated -------------------------


def test_validate_does_not_mutate_its_argument():
    record = make_proposal()
    before = copy.deepcopy(record)
    schema.validate(record)
    assert record == before


# ---- executed -----------------------------------------------------------------


def test_valid_executed_validates_clean():
    assert schema.validate(make_executed()) == []


def test_executed_requires_ruling_id():
    record = make_executed()
    del record["ruling_id"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.ruling_id: required")


def test_executed_requires_a_non_empty_actions_list():
    errors = schema.validate(make_executed(actions=[]))
    assert _errors_mentioning(errors, "record.actions: expected a non-empty list")


def test_executed_action_outcome_must_be_success_or_failure():
    record = make_executed(actions=[{"tool": "workshop.build", "outcome": "maybe"}])
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.actions.0.outcome")


def test_executed_a_failed_action_is_a_valid_record():
    record = make_executed(actions=[
        {"tool": "workshop.build", "outcome": "failure", "detail": "precondition stale"},
    ])
    assert schema.validate(record) == []


def test_executed_action_detail_is_coordinate_scanned():
    record = make_executed(actions=[
        {"tool": "workshop.build", "outcome": "failure", "detail": "stalled at x=12"},
    ])
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "raw-coordinate pattern")


def test_executed_requires_notes():
    record = make_executed()
    del record["notes"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.notes: required")


def test_executed_only_the_sole_writer_may_write_one():
    record = make_executed(role="architect")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "only the roster's sole_writer")


# ---- ask ------------------------------------------------------------------------


def test_valid_ask_validates_clean():
    assert schema.validate(make_ask()) == []


def test_ask_with_a_proposal_id_validates_clean():
    assert schema.validate(make_ask(role="overseer", proposal_id="proposal-0001")) == []


def test_ask_requires_a_question():
    record = make_ask()
    del record["question"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.question: required")


def test_ask_question_is_coordinate_scanned():
    errors = schema.validate(make_ask(question="What happens at (4, 9, -2)?"))
    assert _errors_mentioning(errors, "raw-coordinate pattern")


@pytest.mark.parametrize("role", ["consultant", "marshal", "chronicler"])
def test_ask_is_refused_from_a_role_outside_the_closed_set(role):
    # consultant is enabled but not an asker (it answers); marshal/chronicler
    # are disabled, so both the role-restriction and enabled-role checks
    # would fire -- assert on the ask-specific one here.
    record = make_ask(role=role)
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "may write an ask")


# ---- answer ---------------------------------------------------------------------


def test_valid_answer_validates_clean():
    assert schema.validate(make_answer()) == []


def test_answer_requires_ask_id():
    record = make_answer()
    del record["ask_id"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.ask_id: required")


def test_answer_requires_answer_text():
    record = make_answer()
    del record["answer"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.answer: required")


def test_answer_is_refused_from_any_role_but_consultant():
    record = make_answer(role="architect")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "only 'consultant' may write an answer")


# ---- escalation (handoffs/2026-09-22-loop-conductor-fixes.md item 3) ------------


def test_valid_escalation_validates_clean():
    assert schema.validate(make_escalation()) == []


def test_escalation_requires_a_reason():
    record = make_escalation()
    del record["reason"]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.reason: required")


def test_escalation_reason_is_coordinate_scanned():
    errors = schema.validate(make_escalation(reason="Happens at (4, 9, -2)."))
    assert _errors_mentioning(errors, "raw-coordinate pattern")


def test_escalation_from_a_non_sole_writer_role_is_refused():
    record = make_escalation(role="architect")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "only the roster's sole_writer")


def test_escalation_rejects_an_unknown_field():
    record = make_escalation(public_rationale="not a field on this record")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.public_rationale: not a field in the escalation schema")


# ---- the quartermaster's type vocabulary --------------------------------------
#
# agents/ROSTER.yaml still has quartermaster `enabled: false`
# (handoffs/2026-09-22-loop-queue-quartermaster.md: "Do not flip enabled in
# ROSTER.yaml", that is the orchestrator's job at merge), so a real proposal
# from this role is refused on the enabled-role check regardless of its
# type. These tests isolate the type-vocabulary question by monkeypatching
# `schema.enabled_roles` directly (never `_load_roster`'s lru_cache, so the
# real on-disk roster is never touched and no other test can be affected).


def test_quartermaster_type_vocabulary_is_the_three_mvp_types():
    assert schema.TYPE_VOCAB_BY_ROLE["quartermaster"] == (
        schema.WORK_ORDER, schema.CROP_PLAN, schema.STOCK_TARGET,
    )


@pytest.mark.parametrize("ptype", [
    schema.WORK_ORDER, schema.CROP_PLAN, schema.STOCK_TARGET,
])
def test_quartermaster_proposal_with_an_own_type_only_fails_on_enabled_role(
    monkeypatch, ptype,
):
    monkeypatch.setattr(
        schema, "enabled_roles",
        lambda: frozenset({"architect", "overseer", "consultant", "quartermaster"}),
    )
    record = make_proposal(role="quartermaster", type=ptype)
    assert schema.validate(record) == []


def test_quartermaster_proposal_with_an_architect_type_is_refused_even_once_enabled(
    monkeypatch,
):
    monkeypatch.setattr(
        schema, "enabled_roles",
        lambda: frozenset({"architect", "overseer", "consultant", "quartermaster"}),
    )
    record = make_proposal(role="quartermaster", type=schema.WORKSHOP_SITING)
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "not in the proposal-type vocabulary")


def test_quartermaster_proposal_is_accepted_by_the_real_on_disk_roster_today():
    """Confirms the actual state, unmocked: quartermaster was enabled in
    agents/ROSTER.yaml on 2026-09-22 (agent loop MVP), so its role check
    passes. Other fields of this helper-built record may still be refused;
    only the role check is asserted here."""
    record = make_proposal(role="quartermaster", type=schema.WORK_ORDER)
    errors = schema.validate(record)
    assert not _errors_mentioning(errors, "not an enabled role")
