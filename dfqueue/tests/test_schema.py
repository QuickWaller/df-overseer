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
    make_abandon, make_amend, make_answer, make_ask, make_escalation,
    make_executed, make_observation, make_pass, make_project, make_proposal,
    make_ruling,
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


# ---- duplicate_of: the stateless (type-only) half of write-time validation ------
#
# `duplicate_of`'s *existence* check (must name a real proposal already in
# the queue) needs the loaded database, so it lives in
# `dfqueue/store.py::append()` (same split as `ruling`'s own `proposal_id`)
# and is covered in `test_store.py`. This file only covers what `validate()`
# itself can check without a database: the field is optional, and when given
# it must be a non-empty string.


def test_proposal_without_duplicate_of_validates_clean():
    assert "duplicate_of" not in make_proposal()
    assert schema.validate(make_proposal()) == []


def test_proposal_with_a_string_duplicate_of_validates_clean():
    record = make_proposal(duplicate_of="proposal-0001")
    assert schema.validate(record) == []


def test_proposal_with_an_empty_duplicate_of_is_refused():
    record = make_proposal(duplicate_of="")
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.duplicate_of")


def test_proposal_with_a_non_string_duplicate_of_is_refused():
    record = make_proposal(duplicate_of=42)
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "record.duplicate_of")


# ---- near_duplicate_reason: pure text comparison, no database ------------------
#
# `handoffs/2026-09-28-queue-duplicate-proposal-check.md`: the same shape as
# `dfmcp.gotchas_store.near_duplicate_reason` (title/body), applied to a
# proposal's own `summary`/`rationale`. The caller (`dfqueue/store.py`'s
# `_find_duplicate_proposal`) is what scopes candidates to the same `type`
# and "still open" -- this function itself never looks at `type` at all, so
# these tests exercise it directly with plain dicts.


def test_near_duplicate_reason_none_for_unrelated_summaries():
    candidate = {"summary": "Site the next workshop south of the wagon.", "rationale": "Short haul."}
    existing = {"summary": "Dig a well in the eastern cavern.", "rationale": "Water access."}
    assert schema.near_duplicate_reason(candidate, existing) is None


def test_near_duplicate_reason_catches_an_identical_summary():
    candidate = {"summary": "Queue brewing directly at the Still.", "rationale": "We are low on drink."}
    existing = {"summary": "Queue brewing directly at the Still.", "rationale": "Booze stock is falling."}
    reason = schema.near_duplicate_reason(candidate, existing)
    assert reason is not None
    assert "identical" in reason


def test_near_duplicate_reason_catches_a_reworded_summary_by_word_overlap():
    """proposal-0009 vs proposal-0007's own real shape: same underlying
    action, different phrasing -- caught by word-set Jaccard, not an exact
    string match."""
    candidate = {
        "summary": "Queue a direct brewing job at the Still to cover the drink shortfall.",
        "rationale": "Drink stock is under the safety margin.",
    }
    existing = {
        "summary": "Queue a direct job at the Still to brew and cover the drink shortfall.",
        "rationale": "We are projected to run dry within the season.",
    }
    reason = schema.near_duplicate_reason(candidate, existing)
    assert reason is not None


def test_near_duplicate_reason_catches_a_near_identical_rationale_with_a_different_summary():
    candidate = {
        "summary": "Build a still at the north workshop row.",
        "rationale": "Drink stock has fallen under the safety margin for this season.",
    }
    existing = {
        "summary": "Site a new brewery workshop north of the stockpile.",
        "rationale": "Drink stock has fallen under the safety margin for this season, roughly.",
    }
    reason = schema.near_duplicate_reason(candidate, existing)
    assert reason is not None
    assert "rationale" in reason


def test_near_duplicate_reason_ignores_missing_fields_without_raising():
    assert schema.near_duplicate_reason({}, {}) is None


# ---- project / step schema (handoffs/2026-09-28-dfqueue-project-step-schema.md) ---


def test_valid_project_validates_clean():
    assert schema.validate(make_project()) == []


def test_project_role_restricted_to_sole_writer():
    """Same restriction as ruling/executed/escalation (§9: the project is
    the Overseer's own ordered plan)."""
    record = make_project(role="architect")
    errors = _errors_mentioning(schema.validate(record), "record.role")
    assert errors, "an architect-authored project should be refused"


def test_project_step_tool_must_be_a_real_registry_id():
    record = make_project()
    record["steps"][0]["tool"] = "not_a_real_tool.frobnicate"
    errors = _errors_mentioning(schema.validate(record), "steps.0.tool")
    assert errors, "a made-up tool id should be refused"
    assert "not a real tool id" in errors[0]


def test_project_step_requires_must_reference_a_sibling_step():
    record = make_project()
    record["steps"][1]["requires"] = ["no-such-step"]
    errors = _errors_mentioning(schema.validate(record), "steps.1.requires")
    assert errors


def test_project_step_cannot_require_itself():
    record = make_project()
    record["steps"][0]["requires"] = [record["steps"][0]["id"]]
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "may not require itself")


def test_project_requires_cycle_is_refused():
    record = make_project()
    record["steps"][0]["requires"] = [record["steps"][1]["id"]]
    # s1 now requires s2, and s2 already requires s1: a two-step cycle.
    errors = schema.validate(record)
    assert _errors_mentioning(errors, "cycle")


def test_project_step_trigger_vocabulary():
    record = make_project()
    record["steps"][1]["trigger"] = "one_success"  # not in the closed vocab
    errors = _errors_mentioning(schema.validate(record), "steps.1.trigger")
    assert errors


def test_project_step_trigger_all_success_and_all_done_both_valid():
    record = make_project()
    record["steps"][0]["trigger"] = "all_success"
    record["steps"][1]["trigger"] = "all_done"
    assert schema.validate(record) == []


def test_project_zero_steps_refused_by_validate_directly():
    """`store.normalize_project` fills this in on the real write path
    (`store.append()`, tested in `test_store.py`); calling `validate()`
    directly on a raw empty-steps record is refused rather than silently
    treated as a vacuously-done project."""
    record = make_project(steps=[])
    errors = _errors_mentioning(schema.validate(record), "record.steps")
    assert errors


def test_project_summary_coordinate_scan():
    record = make_project(summary="Wall off the tile at (4, 9, -2).")
    errors = _errors_mentioning(schema.validate(record), "record.summary")
    assert errors


def test_project_targets_set_coordinate_scan():
    """design §4.3: target handles are opaque, never a raw coordinate. The
    existing coordinate filter must cover this new field."""
    record = make_project()
    record["steps"][0]["targets"]["set"] = ["x=12"]
    errors = _errors_mentioning(schema.validate(record), "steps.0.targets.set")
    assert errors


def test_project_guards_default_sentinel_and_extra_list_both_valid():
    record = make_project()
    record["steps"][0]["guards"] = "default"
    record["steps"][1]["guards"] = ["keeps_access", "not_over_pending_designation"]
    assert schema.validate(record) == []


def test_project_guards_rejects_junk():
    record = make_project()
    record["steps"][0]["guards"] = "not-default-and-not-a-list"
    errors = _errors_mentioning(schema.validate(record), "steps.0.guards")
    assert errors


# ---- public display fields (handoffs/2026-10-02-queue-display-fields.md) -----


def test_project_without_public_fields_still_validates_clean():
    """An old project record, written before this stream, never had
    public_title/public_rationale/urgency at all -- all three are optional."""
    record = make_project()
    assert "public_title" not in record
    assert schema.validate(record) == []


def test_project_public_title_and_rationale_and_urgency_validate_clean():
    record = make_project(
        public_title="Recover the hematite vein",
        public_rationale="The ring's own smoothing pass exposed ore.",
        urgency="elevated",
    )
    assert schema.validate(record) == []


def test_project_public_title_too_long_is_refused():
    record = make_project(public_title="x" * 61)
    errors = _errors_mentioning(schema.validate(record), "record.public_title")
    assert errors


def test_project_public_title_at_the_limit_is_fine():
    record = make_project(public_title="x" * 60)
    assert schema.validate(record) == []


def test_project_public_rationale_too_long_is_refused():
    record = make_project(public_rationale="x" * 301)
    errors = _errors_mentioning(schema.validate(record), "record.public_rationale")
    assert errors


def test_project_public_title_coordinate_scan():
    record = make_project(public_title="Wall at (4, 9, -2)")
    errors = _errors_mentioning(schema.validate(record), "record.public_title")
    assert errors


def test_project_public_rationale_coordinate_scan():
    record = make_project(public_rationale="Still pending at x=12.")
    errors = _errors_mentioning(schema.validate(record), "record.public_rationale")
    assert errors


def test_project_public_title_empty_string_is_refused():
    record = make_project(public_title="")
    errors = _errors_mentioning(schema.validate(record), "record.public_title")
    assert errors


def test_project_urgency_vocabulary():
    record = make_project(urgency="urgent")
    errors = _errors_mentioning(schema.validate(record), "record.urgency")
    assert errors


def test_project_urgency_each_value_in_closed_vocabulary_is_valid():
    for value in ("normal", "elevated", "high"):
        record = make_project(urgency=value)
        assert schema.validate(record) == [], value


def test_project_step_label_validates_clean():
    record = make_project()
    record["steps"][0]["label"] = "Smooth walls"
    assert schema.validate(record) == []


def test_project_step_label_too_long_is_refused():
    record = make_project()
    record["steps"][0]["label"] = "x" * 25
    errors = _errors_mentioning(schema.validate(record), "steps.0.label")
    assert errors


def test_project_step_label_at_the_limit_is_fine():
    record = make_project()
    record["steps"][0]["label"] = "x" * 24
    assert schema.validate(record) == []


def test_project_step_label_coordinate_scan():
    record = make_project()
    record["steps"][0]["label"] = "Wall at (4, 9, -2)"
    errors = _errors_mentioning(schema.validate(record), "steps.0.label")
    assert errors


def test_project_step_label_empty_string_is_refused():
    record = make_project()
    record["steps"][0]["label"] = ""
    errors = _errors_mentioning(schema.validate(record), "steps.0.label")
    assert errors


def test_amend_public_rationale_validates_clean():
    record = make_amend(public_rationale="Dropping the now-unreachable tile.")
    assert schema.validate(record) == []


def test_amend_public_rationale_too_long_is_refused():
    record = make_amend(public_rationale="x" * 301)
    errors = _errors_mentioning(schema.validate(record), "record.public_rationale")
    assert errors


def test_abandon_public_rationale_validates_clean():
    record = make_abandon(public_rationale="The vein played out.")
    assert schema.validate(record) == []


def test_abandon_public_rationale_too_long_is_refused():
    record = make_abandon(public_rationale="x" * 301)
    errors = _errors_mentioning(schema.validate(record), "record.public_rationale")
    assert errors


def test_observation_hold_code_validates_clean():
    record = make_observation()
    record["results"][0]["hold_code"] = "no_worker"
    assert schema.validate(record) == []


def test_observation_unknown_hold_code_is_refused():
    record = make_observation()
    record["results"][0]["hold_code"] = "made_up_code"
    errors = _errors_mentioning(schema.validate(record), "results.0.hold_code")
    assert errors


def test_observation_hold_code_vocabulary_matches_public_text_file():
    """`schema.hold_codes()` must read `dfqueue/public_text.yaml`'s own keys,
    not a hardcoded tuple -- the 'one data entry, no new code' rule."""
    assert schema.hold_codes() == {
        "no_material_in_reach", "site_unreachable", "site_flooded",
        "no_worker", "waiting_for_haul", "preview_failed", "tool_refused",
        "other",
    }


# ---- executed: step_id, targets, game_refs, target_state ---------------------


def test_executed_with_step_id_and_targets_validates_clean():
    record = make_executed(
        step_id="project-0001/s1",
        actions=[
            {
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                "target_state": "issued",
                "game_refs": [2701, 2702],
            },
        ],
    )
    assert schema.validate(record) == []


def test_executed_action_targets_requires_target_state():
    record = make_executed(
        actions=[{"tool": "construction.build", "outcome": "success", "targets": ["ring-13-ore-1"]}],
    )
    errors = _errors_mentioning(schema.validate(record), "actions.0")
    assert errors, "targets without a target_state should be refused"


def test_executed_action_target_state_vocabulary():
    record = make_executed(
        actions=[{
            "tool": "construction.build", "outcome": "success",
            "targets": ["ring-13-ore-1"], "target_state": "waiting",
        }],
    )
    errors = _errors_mentioning(schema.validate(record), "target_state")
    assert errors, "'waiting'/'ready' are structural, never asserted by a record"


def test_executed_action_targets_coordinate_scan():
    record = make_executed(
        actions=[{
            "tool": "construction.build", "outcome": "success",
            "targets": ["(4, 9, -2)"], "target_state": "issued",
        }],
    )
    errors = _errors_mentioning(schema.validate(record), "actions.0.targets")
    assert errors


def test_executed_action_game_refs_coordinate_scan():
    record = make_executed(
        actions=[{
            "tool": "construction.build", "outcome": "success",
            "targets": ["ring-13-ore-1"], "target_state": "issued",
            "game_refs": ["z=-3"],
        }],
    )
    errors = _errors_mentioning(schema.validate(record), "actions.0.game_refs")
    assert errors


# ---- observation ---------------------------------------------------------------


def test_valid_observation_validates_clean():
    assert schema.validate(make_observation()) == []


def test_observation_role_restricted_to_conductor():
    record = make_observation(role="overseer")
    errors = _errors_mentioning(schema.validate(record), "record.role")
    assert errors, "only the conductor (code) may write an observation"


def test_observation_status_vocabulary():
    record = make_observation()
    record["results"][0]["status"] = "probably_fine"
    errors = _errors_mentioning(schema.validate(record), "results.0.status")
    assert errors


def test_observation_target_coordinate_scan():
    record = make_observation()
    record["results"][0]["target"] = "(4, 9, -2)"
    errors = _errors_mentioning(schema.validate(record), "results.0.target")
    assert errors


def test_observation_reason_coordinate_scan():
    record = make_observation()
    record["results"][0]["reason"] = "still pending at x=12"
    errors = _errors_mentioning(schema.validate(record), "results.0.reason")
    assert errors


# ---- amend / abandon (handoffs/2026-10-01-queue-bugs-and-amend.md item 3) ----


def test_valid_amend_validates_clean():
    assert schema.validate(make_amend()) == []


def test_amend_role_restricted_to_sole_writer():
    """Same restriction as ruling/executed/escalation/project."""
    record = make_amend(role="architect")
    errors = _errors_mentioning(schema.validate(record), "record.role")
    assert errors, "an architect-authored amend should be refused"


def test_amend_requires_a_reason():
    record = make_amend()
    del record["reason"]
    errors = _errors_mentioning(schema.validate(record), "record.reason")
    assert errors


def test_amend_reason_coordinate_scan():
    record = make_amend(reason="Wall off the tile at (4, 9, -2) instead.")
    errors = _errors_mentioning(schema.validate(record), "record.reason")
    assert errors


def test_amend_steps_cannot_be_empty():
    record = make_amend(steps=[])
    errors = _errors_mentioning(schema.validate(record), "record.steps")
    assert errors


def test_amend_steps_use_the_same_per_step_rules_as_project():
    """Same closed step schema as `project` (real tool ids, no self-require,
    no cycle) -- exercised once here to prove the shared validation path,
    not the whole matrix `test_project_*` above already covers."""
    record = make_amend()
    record["steps"][0]["tool"] = "not_a_real_tool.frobnicate"
    errors = _errors_mentioning(schema.validate(record), "steps.0.tool")
    assert errors
    assert "not a real tool id" in errors[0]


def test_amend_replaces_adds_drops_must_be_string_lists():
    record = make_amend()
    record["replaces"] = [123]
    errors = _errors_mentioning(schema.validate(record), "record.replaces.0")
    assert errors


def test_valid_abandon_validates_clean():
    assert schema.validate(make_abandon()) == []


def test_abandon_role_restricted_to_sole_writer():
    record = make_abandon(role="architect")
    errors = _errors_mentioning(schema.validate(record), "record.role")
    assert errors, "an architect-authored abandon should be refused"


def test_abandon_requires_a_reason():
    record = make_abandon()
    del record["reason"]
    errors = _errors_mentioning(schema.validate(record), "record.reason")
    assert errors


def test_abandon_requires_a_project_id():
    record = make_abandon()
    del record["project_id"]
    errors = _errors_mentioning(schema.validate(record), "record.project_id")
    assert errors
