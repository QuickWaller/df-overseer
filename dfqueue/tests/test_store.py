"""`dfqueue.store`: SQLite append-only writes, refusal-with-nothing-written
in either table, atomic proposal+prediction inserts, and the
`latest`/`pending_due`/`export_jsonl` query helpers the feed and grader need.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3

import pytest

from dfqueue import render, schema, store
from dfqueue.tests._helpers import (
    make_abandon, make_amend, make_answer, make_ask, make_escalation,
    make_executed, make_observation, make_pass, make_project, make_proposal,
    make_ruling,
)
from learning.predictions.schema import GRADED_TRUE, PENDING


def _accept_and_execute(path, proposal_id, *, execution_cycle, ruling_id=None, **executed_overrides):
    """Test helper: append an accepting ruling for `proposal_id`, then a
    matching `executed` record at `execution_cycle` -- the two writes every
    grading test now needs before a prediction is due, since `docs/
    AGENT-LOOP.md` item 4 starts a proposal's window at execution, not at
    the proposal's own write time. Returns `(ruling, executed)`."""
    ruling = store.append(
        make_ruling(id=ruling_id, proposal_id=proposal_id), path,
    )
    # A project (implicit single step) must exist before any execution:
    # the server refuses `executed` for an accepted ruling with no project.
    store.append(make_project(from_ruling=ruling["id"], steps=[]), path)
    executed = store.append(
        make_executed(ruling_id=ruling["id"], cycle=execution_cycle, **executed_overrides),
        path,
    )
    return ruling, executed


def _db(tmp_path):
    return tmp_path / "queue.sqlite3"


# ---- proposal/pass/ruling round trip -------------------------------------------


def test_append_then_load_round_trips_a_proposal(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=178877)

    assert written["id"]  # assigned
    assert written["ts"]  # assigned, UTC

    loaded = store.load(path)
    assert len(loaded) == 1
    assert loaded[0] == written

    xml = render.to_xml(loaded[0])
    assert xml.startswith("<proposal ")
    assert "<type>workshop_siting</type>" in xml
    assert 'signal="fort.population"' in xml


def test_append_then_load_round_trips_a_pass(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_pass(), path)

    loaded = store.load(path)
    assert loaded == [written]

    xml = render.to_xml(loaded[0])
    assert xml.startswith("<pass ")
    assert "<reason>" in xml


def test_append_then_load_round_trips_an_escalation(tmp_path):
    """Added handoffs/2026-09-22-loop-conductor-fixes.md item 3: an
    escalation is a standalone record, same class as `pass` -- no reference
    to another record, needs no game_tick."""
    path = _db(tmp_path)
    written = store.append(make_escalation(), path)

    loaded = store.load(path)
    assert loaded == [written]

    xml = render.to_xml(loaded[0])
    assert xml.startswith("<escalation ")
    assert "<reason>" in xml

    # It is not a proposal and not an ask -- neither queue-state read
    # conductor/cycle.py relies on (queue.overview's own two halves) may
    # ever count it.
    assert store.pending_proposals(path) == []
    assert store.open_asks(path) == []


def test_append_then_load_round_trips_a_ruling(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=178877)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)

    loaded = store.load(path)
    assert loaded == [proposal, ruling]

    xml = render.to_xml(loaded[1])
    assert xml.startswith("<ruling ")
    assert f"<proposal_id>{proposal['id']}</proposal_id>" in xml


def test_id_and_ts_are_assigned_when_absent(tmp_path):
    path = _db(tmp_path)
    record = make_proposal()
    assert "id" not in record and "ts" not in record

    written = store.append(record, path, game_tick=100)
    assert written["id"] == "proposal-0001"
    assert written["ts"]

    second = store.append(make_proposal(), path, game_tick=100)
    assert second["id"] == "proposal-0002"


def test_id_and_ts_are_preserved_when_present(tmp_path):
    path = _db(tmp_path)
    record = make_proposal(id="p-0001", ts="2026-09-14T00:00:00+00:00")
    written = store.append(record, path, game_tick=100)
    assert written["id"] == "p-0001"
    assert written["ts"] == "2026-09-14T00:00:00+00:00"


# ---- refusals write nothing to either table ------------------------------------


def test_append_refuses_an_invalid_record_and_writes_nothing(tmp_path):
    path = _db(tmp_path)
    bad = make_proposal(suggested_priority=99)

    with pytest.raises(store.QueueError):
        store.append(bad, path, game_tick=100)

    assert store.load(path) == []
    assert store.pending_due(path, 10**9) == []


def test_append_refuses_a_second_write_after_a_prior_refusal_leaves_db_intact(tmp_path):
    path = _db(tmp_path)
    good = store.append(make_proposal(), path, game_tick=100)

    bad = make_proposal(cost={"estimate": -1, "unit": "dwarf_ticks"})
    with pytest.raises(store.QueueError):
        store.append(bad, path, game_tick=100)

    assert store.load(path) == [good]


def test_proposal_missing_game_tick_is_refused_and_writes_nothing(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="game_tick"):
        store.append(make_proposal(), path)  # no game_tick kwarg

    assert store.load(path) == []


def test_dangling_proposal_id_is_refused(tmp_path):
    path = _db(tmp_path)
    ruling = make_ruling(proposal_id="proposal-9999")

    with pytest.raises(store.QueueError, match="does not refer to an existing proposal"):
        store.append(ruling, path)

    assert store.load(path) == []


def test_ruling_against_a_real_proposal_from_a_different_db_is_still_dangling(tmp_path):
    other_path = tmp_path / "other-fort.sqlite3"
    proposal = store.append(make_proposal(), other_path, game_tick=100)

    path = _db(tmp_path)
    ruling = make_ruling(proposal_id=proposal["id"])
    with pytest.raises(store.QueueError, match="does not refer to an existing proposal"):
        store.append(ruling, path)
    assert store.load(path) == []


# ---- duplicate-proposal detection -----------------------------------------------
#
# `handoffs/2026-09-28-queue-duplicate-proposal-check.md`: `proposal-0009`
# duplicated the still-open `proposal-0007` (both queuing brewing directly at
# the Still) without either advisor knowing the other existed. A near-
# duplicate is never refused (unlike a gotcha, `dfmcp/gotchas_store.py`'s
# `add_entry`) -- it is still written, flagged with `duplicate_of` naming the
# existing open proposal.


def test_a_near_duplicate_proposal_is_written_and_flagged_not_refused(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    assert "duplicate_of" not in first

    second = store.append(
        make_proposal(
            summary="Site the next workshop on the open ground south of Embark Site.",
        ),
        path, game_tick=100,
    )

    assert second["duplicate_of"] == first["id"]
    assert second["duplicate_reason"]  # reported to the caller of append()
    # But the reason is NOT persisted -- only duplicate_of, a real schema
    # field, is. Reading it back must not carry the transient key.
    loaded = store.load(path)
    assert len(loaded) == 2
    assert loaded[1]["duplicate_of"] == first["id"]
    assert "duplicate_reason" not in loaded[1]


def test_a_near_duplicate_proposal_still_lands_in_pending_proposals(tmp_path):
    """Never silently dropped, never refused: both the original and its
    duplicate stay visible to the Overseer."""
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    second = store.append(
        make_proposal(summary="Site the next workshop on the open ground south of Embark Site."),
        path, game_tick=100,
    )
    pending_ids = [r["id"] for r in store.pending_proposals(path)]
    assert pending_ids == [first["id"], second["id"]]


def test_unrelated_proposals_of_the_same_type_are_not_flagged_as_duplicates(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    second = store.append(
        make_proposal(
            summary="Dig a second stairwell down to the ore vein two levels below.",
            rationale="The single stairwell is already a haul bottleneck for miners.",
        ),
        path, game_tick=100,
    )
    assert "duplicate_of" not in second
    assert first["id"] != second["id"]


def test_proposals_of_a_different_type_are_never_compared_even_with_the_same_summary(tmp_path):
    """`type` scopes the candidate pool (`dfqueue/store.py`'s
    `_find_duplicate_proposal`): identical text under a different `type`
    must not collide."""
    path = _db(tmp_path)
    first = store.append(make_proposal(type="workshop_siting"), path, game_tick=100)
    second = store.append(make_proposal(type="stockpile_siting"), path, game_tick=100)
    assert first["summary"] == second["summary"]
    assert "duplicate_of" not in second


def test_a_duplicate_is_not_flagged_once_the_original_has_a_final_ruling(tmp_path):
    """"Still open" mirrors `pending_proposals`'s own definition: once the
    original is finally ruled (accept/reject), it is no longer a live
    duplicate candidate -- the second proposal is its own, independent one."""
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=first["id"], decision="accept"), path)

    second = store.append(
        make_proposal(summary="Site the next workshop on the open ground south of Embark Site."),
        path, game_tick=100,
    )
    assert "duplicate_of" not in second


def test_a_duplicate_is_still_flagged_against_a_merely_deferred_original(tmp_path):
    """A `defer` ruling ("decide later") never closes a proposal -- it stays
    a live duplicate candidate, same as it stays open to a further ruling."""
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=first["id"], decision="defer"), path)

    second = store.append(
        make_proposal(summary="Site the next workshop on the open ground south of Embark Site."),
        path, game_tick=100,
    )
    assert second["duplicate_of"] == first["id"]


def test_duplicate_of_rendered_in_the_proposal_xml(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    second = store.append(
        make_proposal(summary="Site the next workshop on the open ground south of Embark Site."),
        path, game_tick=100,
    )
    xml = render.to_xml(store.load(path)[1])
    assert f"<duplicate_of>{first['id']}</duplicate_of>" in xml
    assert second["id"]  # sanity: it was written, not refused


def test_a_caller_supplied_duplicate_of_must_name_a_real_proposal(tmp_path):
    path = _db(tmp_path)
    bad = make_proposal(duplicate_of="proposal-9999")
    with pytest.raises(store.QueueError, match="does not refer to an existing proposal"):
        store.append(bad, path, game_tick=100)
    assert store.load(path) == []


def test_a_caller_supplied_duplicate_of_naming_a_real_proposal_is_accepted_as_is(tmp_path):
    """A caller (or a future admin tool) may set `duplicate_of` directly;
    when it already names a real proposal, auto-detection is skipped rather
    than overriding the caller's own value."""
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    second = store.append(
        make_proposal(
            summary="Completely unrelated dig order for the eastern cavern.",
            rationale="Nothing to do with the first proposal at all.",
            duplicate_of=first["id"],
        ),
        path, game_tick=100,
    )
    assert second["duplicate_of"] == first["id"]
    assert "duplicate_reason" not in second  # auto-detection never ran


def test_duplicate_explicit_id_is_refused(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(id="dupe"), path, game_tick=100)
    with pytest.raises(store.QueueError, match="already in the queue"):
        store.append(make_pass(id="dupe"), path)


# ---- the proposal + its prediction commit atomically ---------------------------


def test_a_proposal_and_its_prediction_are_inserted_in_one_transaction(tmp_path, monkeypatch):
    path = _db(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure between the two inserts")

    monkeypatch.setattr(store, "_insert_prediction", boom)

    with pytest.raises(RuntimeError, match="simulated failure"):
        store.append(make_proposal(), path, game_tick=100)

    # Neither the records row nor a predictions row landed.
    assert store.load(path) == []
    assert store.pending_due(path, 10**9) == []


def test_a_pass_never_touches_the_predictions_table(tmp_path, monkeypatch):
    path = _db(tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("a pass has no prediction; _insert_prediction must not run")

    monkeypatch.setattr(store, "_insert_prediction", boom)
    store.append(make_pass(), path)  # would raise via monkeypatch if this were ever called

    assert len(store.load(path)) == 1


# ---- load() / latest() -----------------------------------------------------------


def test_load_of_a_missing_db_returns_empty(tmp_path):
    assert store.load(tmp_path / "nope.sqlite3") == []


def test_default_path_uses_the_roster_fort_name():
    assert store.default_path().name == f"{schema.fort_name()}.sqlite3"


def test_latest_returns_the_n_most_recently_appended_records_newest_first(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_pass(), path)
    second = store.append(make_proposal(), path, game_tick=100)
    third = store.append(make_pass(reason="a second, distinct pass reason here."), path)

    top2 = store.latest(path, 2)
    assert [r["id"] for r in top2] == [third["id"], second["id"]]

    everything = store.latest(path, 10)
    assert [r["id"] for r in everything] == [third["id"], second["id"], first["id"]]


# ---- pending_due() ----------------------------------------------------------------


def test_pending_due_returns_only_predictions_due_at_or_before_the_tick(tmp_path):
    path = _db(tmp_path)
    written = store.append(
        make_proposal(prediction={
            "signal": "fort.population", "op": "gte", "value": 1,
            "check_after_ticks": 500,
        }),
        path, game_tick=1000,
    )
    # Not due yet -- not even armed: this proposal has no ruling or
    # execution record, so its prediction is still AWAITING_EXECUTION.
    assert store.pending_due(path, 10**9) == []

    _accept_and_execute(path, written["id"], execution_cycle=1000)
    # due_game_tick = 1000 (execution tick) + 500 (check_after_ticks) = 1500

    assert store.pending_due(path, 1499) == []

    due_at = store.pending_due(path, 1500)
    assert len(due_at) == 1
    row = due_at[0]
    assert row["record_id"] == written["id"]
    assert row["signal"] == "fort.population"
    assert row["op"] == "gte"
    assert row["value"] == 1
    assert row["due_game_tick"] == 1500
    assert row["status"] == PENDING
    assert row["actual_value"] is None

    assert len(store.pending_due(path, 5000)) == 1  # still there, "at or before"


def test_pending_due_excludes_a_graded_prediction(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)  # check_after_ticks=1200
    _accept_and_execute(path, written["id"], execution_cycle=0)  # due 0 + 1200 = 1200

    due = store.pending_due(path, 1200)
    assert len(due) == 1

    store.apply_grades(path, [{
        "id": due[0]["id"], "status": GRADED_TRUE, "actual_value": 15,
        "graded_at": "2026-09-15T00:00:00+00:00", "grade_note": "",
    }])

    assert store.pending_due(path, 1200) == []


# ---- execution arms the prediction (docs/AGENT-LOOP.md item 4) -------------------


def test_a_freshly_appended_proposal_is_awaiting_execution_not_pending(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=100)

    with store._connect(path) as conn:
        row = conn.execute(
            "SELECT status, check_after_ticks FROM predictions WHERE record_id = ?",
            (written["id"],),
        ).fetchone()
    assert row["status"] == store.AWAITING_EXECUTION
    assert row["check_after_ticks"] == 1200  # make_proposal's own default


def test_the_first_executed_record_arms_the_prediction_from_its_own_cycle(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=100)  # written far before execution

    _accept_and_execute(path, written["id"], execution_cycle=99999)
    # due_game_tick must come from the EXECUTION tick (99999), never the
    # original write-time game_tick (100).

    assert store.pending_due(path, 99999 + 1199) == []
    due = store.pending_due(path, 99999 + 1200)
    assert len(due) == 1
    assert due[0]["due_game_tick"] == 99999 + 1200
    assert due[0]["status"] == PENDING


def test_a_second_executed_record_for_the_same_ruling_does_not_re_arm(tmp_path):
    """A retry (or a second, later executed record for any reason) must not
    move the window a second time -- see `_arm_prediction_on_first_
    execution`'s own docstring."""
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)
    ruling, first = _accept_and_execute(path, written["id"], execution_cycle=1000)
    # due = 1000 + 1200 = 2200

    second = store.append(
        make_executed(ruling_id=ruling["id"], cycle=50000, notes="A later retry, logged."),
        path,
    )
    assert second["id"] != first["id"]

    due = store.pending_due(path, 2200)
    assert len(due) == 1
    assert due[0]["due_game_tick"] == 2200  # unchanged by the second executed record


def test_executed_is_refused_against_a_nonexistent_ruling(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="does not refer to an existing ruling"):
        store.append(make_executed(ruling_id="ruling-9999"), path)


def test_executed_is_refused_against_a_rejected_ruling(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    ruling = store.append(make_ruling(proposal_id=proposal["id"], decision="reject"), path)

    with pytest.raises(store.QueueError, match="not 'accept'"):
        store.append(make_executed(ruling_id=ruling["id"]), path)


def test_executed_round_trips_a_failed_action(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)
    store.append(make_project(from_ruling=ruling["id"], steps=[]), path)
    executed = store.append(
        make_executed(
            ruling_id=ruling["id"],
            actions=[{"tool": "workshop.build", "outcome": "failure", "detail": "stale precondition"}],
            notes="Precondition no longer held; nothing built.",
        ),
        path,
    )
    assert store.load(path)[-1] == executed
    assert executed["actions"][0]["outcome"] == "failure"


# ---- 2026-10-05: no execution without a project --------------------------------


def test_executed_is_refused_for_an_accepted_ruling_with_no_project(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)
    with pytest.raises(store.QueueError) as exc:
        store.append(make_executed(ruling_id=ruling["id"]), path)
    text = str(exc.value)
    assert "queue.project" in text and f"from_ruling='{ruling['id']}'" in text
    assert "step_id" in text
    assert [r for r in store.load(path) if r["kind"] == "executed"] == []


def test_executed_is_refused_with_a_step_id_and_no_project_too(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)
    with pytest.raises(store.QueueError, match="queue.project"):
        store.append(make_executed(ruling_id=ruling["id"], step_id="s1"), path)


def test_executed_requires_step_id_once_a_real_project_exists(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, _project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="step_id: required"):
        store.append(make_executed(ruling_id=ruling["id"], cycle=2), path)


def test_an_older_accepted_ruling_can_get_a_project_later_and_then_execute(tmp_path):
    """The live case: proposal-0013/0014 were accepted before the rule and
    have no project. Creating the project now, long after the ruling, must
    unblock execution."""
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)
    with pytest.raises(store.QueueError, match="queue.project"):
        store.append(make_executed(ruling_id=ruling["id"], cycle=900000), path)
    # Much later: a project for the old ruling, then the execution.
    project = store.append(make_project(from_ruling=ruling["id"], cycle=900000), path)
    s1 = project["steps"][0]["id"]
    with pytest.raises(store.QueueError, match="step_id: required"):
        store.append(make_executed(ruling_id=ruling["id"], cycle=900001), path)
    executed = store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=900001, step_id=s1,
            actions=[{"tool": "construction.mine-vein", "outcome": "success",
                      "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                      "target_state": "done"}],
        ),
        path,
    )
    assert executed["step_id"] == s1


# ---- unexecuted_accepted_proposals() -- docs/AGENT-LOOP.md item 4 ----------------


def test_unexecuted_accepted_proposals_lists_an_accepted_never_executed_one(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)

    unexecuted = store.unexecuted_accepted_proposals(path)
    assert len(unexecuted) == 1
    assert unexecuted[0]["proposal"]["id"] == proposal["id"]
    assert unexecuted[0]["ruling_id"] == ruling["id"]


def test_unexecuted_accepted_proposals_excludes_an_executed_one(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    _accept_and_execute(path, proposal["id"], execution_cycle=100)

    assert store.unexecuted_accepted_proposals(path) == []


def test_unexecuted_accepted_proposals_excludes_a_rejected_one(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    store.append(make_ruling(proposal_id=proposal["id"], decision="reject"), path)

    assert store.unexecuted_accepted_proposals(path) == []


def test_unexecuted_accepted_proposals_excludes_an_unruled_one(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=0)

    assert store.unexecuted_accepted_proposals(path) == []


# ---- ask / answer / fact-check -- docs/AGENT-LOOP.md item 7 ----------------------


def test_ask_and_answer_round_trip(tmp_path):
    path = _db(tmp_path)
    ask = store.append(make_ask(), path)
    answer = store.append(make_answer(ask_id=ask["id"]), path)

    assert store.load(path) == [ask, answer]
    assert store.open_asks(path) == []  # answered, so no longer open


def test_open_asks_lists_an_unanswered_ask_oldest_first(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_ask(question="First question, distinct text."), path)
    second = store.append(make_ask(question="Second question, distinct text."), path)
    store.append(make_answer(ask_id=first["id"]), path)

    open_ = store.open_asks(path)
    assert [r["id"] for r in open_] == [second["id"]]


def test_answer_is_refused_against_a_nonexistent_ask(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="does not refer to an existing ask"):
        store.append(make_answer(ask_id="ask-9999"), path)


def test_a_second_answer_to_the_same_ask_is_refused(tmp_path):
    path = _db(tmp_path)
    ask = store.append(make_ask(), path)
    store.append(make_answer(ask_id=ask["id"]), path)

    with pytest.raises(store.QueueError, match="already has an answer"):
        store.append(make_answer(ask_id=ask["id"], answer="A second, different answer."), path)


def test_ask_with_a_proposal_id_is_refused_if_the_proposal_does_not_exist(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="does not refer to an existing proposal"):
        store.append(make_ask(role="overseer", proposal_id="proposal-9999"), path)


def test_a_fact_check_blocks_ruling_on_its_proposal_until_answered(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    ask = store.append(make_ask(role="overseer", proposal_id=proposal["id"]), path)

    with pytest.raises(store.QueueError, match="open fact-check"):
        store.append(make_ruling(proposal_id=proposal["id"]), path)

    store.append(make_answer(ask_id=ask["id"]), path)
    # Now the fact-check is closed, so the ruling goes through.
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)
    assert ruling["decision"] == "accept"


def test_a_plain_ask_from_an_advisor_never_blocks_ruling(tmp_path):
    """Only an ask from the Overseer naming a proposal is a fact-check.
    An architect's own lookup ask, even with the same proposal_id set,
    never blocks anything."""
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=0)
    store.append(make_ask(role="architect", proposal_id=proposal["id"]), path)

    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)
    assert ruling["decision"] == "accept"


# ---- migrating a v1 database (predictions had no check_after_ticks column) -------


def _build_v1_database(path):
    """Hand-build a v1-shaped queue database: a `records` row plus a
    `predictions` row, both written the OLD way (no `check_after_ticks`
    column exists yet, `status` already `pending`, `due_game_tick` already
    computed at write time) -- standing in for a real database this
    project's earlier code already wrote, since none is committed to the
    repo (`dfqueue/*.sqlite3` is gitignored). Proves `_ensure_schema`'s
    migration path against a database this test builds by hand, not
    against a fixture that already assumes the new shape.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute(
            "CREATE TABLE records (id TEXT PRIMARY KEY, ts TEXT NOT NULL, "
            "kind TEXT NOT NULL, role TEXT NOT NULL, cycle INTEGER NOT NULL, "
            "type TEXT, proposal_id TEXT, payload TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE predictions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "record_id TEXT NOT NULL REFERENCES records(id), signal TEXT NOT NULL, "
            "op TEXT NOT NULL, value TEXT, registered_game_tick INTEGER NOT NULL, "
            "due_game_tick INTEGER NOT NULL, status TEXT NOT NULL, "
            "actual_value TEXT, graded_at TEXT, grade_note TEXT)"
        )
        legacy_proposal = make_proposal(id="proposal-0001", ts="2026-09-01T00:00:00+00:00")
        legacy_proposal["cycle"] = 100
        conn.execute(
            "INSERT INTO records (id, ts, kind, role, cycle, type, proposal_id, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                legacy_proposal["id"], legacy_proposal["ts"], "proposal", "architect", 100,
                legacy_proposal["type"], None,
                json.dumps(legacy_proposal, sort_keys=True),
            ),
        )
        conn.execute(
            "INSERT INTO predictions (record_id, signal, op, value, registered_game_tick, "
            "due_game_tick, status, actual_value, graded_at, grade_note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("proposal-0001", "fort.population", "gte", "1", 100, 1300, "pending", None, None, None),
        )
        conn.commit()
    finally:
        conn.close()


def test_a_v1_database_migrates_and_keeps_its_old_pending_row_readable(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    _build_v1_database(path)

    # Opening it at all runs _ensure_schema's migration path.
    loaded = store.load(path)
    assert len(loaded) == 1
    assert loaded[0]["id"] == "proposal-0001"

    # The legacy row's OWN due_game_tick (computed at write time, under the
    # old rule) is preserved verbatim -- a compatible default, not a
    # reinterpretation: this row was never "awaiting execution" and this
    # migration must not retroactively make it so.
    due = store.pending_due(path, 1300)
    assert len(due) == 1
    assert due[0]["due_game_tick"] == 1300
    assert due[0]["status"] == PENDING

    # check_after_ticks was backfilled (1300 - 100 = 1200), even though no
    # code path in this version ever reads it for an already-armed legacy
    # row.
    with store._connect(path) as conn:
        row = conn.execute(
            "SELECT check_after_ticks FROM predictions WHERE record_id = ?",
            ("proposal-0001",),
        ).fetchone()
    assert row["check_after_ticks"] == 1200


def test_a_migrated_v1_database_accepts_a_brand_new_proposal_under_the_new_rule(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    _build_v1_database(path)
    store.load(path)  # triggers the migration

    written = store.append(make_proposal(id="proposal-0002"), path, game_tick=5000)
    # New rows use the new rule: awaiting execution, not immediately due
    # (the legacy proposal-0001 row is still due under the old rule it was
    # written under, so this checks proposal-0002 specifically rather than
    # asserting the whole list is empty).
    due_ids = [row["record_id"] for row in store.pending_due(path, 5000 + 1200)]
    assert written["id"] not in due_ids

    with store._connect(path) as conn:
        row = conn.execute(
            "SELECT status FROM predictions WHERE record_id = ?", (written["id"],),
        ).fetchone()
    assert row["status"] == store.AWAITING_EXECUTION


def test_a_database_newer_than_this_code_is_refused(tmp_path):
    path = tmp_path / "future.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (store.SCHEMA_VERSION + 1,))
    conn.commit()
    conn.close()

    with pytest.raises(store.QueueError, match="newer database, older code"):
        store.load(path)


# ---- pending_proposals() -- added handoffs/2026-09-15-queue-into-dfmcp.md,
# for queue.pending (dfmcp/queue_tools.py) -----------------------------------------


def test_pending_proposals_excludes_a_ruled_one_and_keeps_an_unruled_one(tmp_path):
    path = _db(tmp_path)
    ruled = store.append(make_proposal(), path, game_tick=100)
    unruled = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=ruled["id"]), path)  # decision="accept" by default

    pending = store.pending_proposals(path)
    assert [r["id"] for r in pending] == [unruled["id"]]


def test_pending_proposals_keeps_a_deferred_proposal(tmp_path):
    """Phase A review, 2026-09-15: a proposal ruled only `defer` ("decide
    later") must stay visible to the Overseer, not vanish the way any
    ruling used to make it vanish before this fix."""
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=proposal["id"], decision="defer"), path)

    pending = store.pending_proposals(path)
    assert [r["id"] for r in pending] == [proposal["id"]]


def test_pending_proposals_excludes_a_rejected_one(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=proposal["id"], decision="reject"), path)

    assert store.pending_proposals(path) == []


def test_a_ruling_after_a_defer_is_allowed_and_a_second_defer_keeps_it_pending(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=proposal["id"], decision="defer"), path)
    # A second ruling on the same proposal, after a defer, is not refused.
    second = store.append(make_ruling(proposal_id=proposal["id"], decision="defer"), path)
    assert second["decision"] == "defer"
    assert [r["id"] for r in store.pending_proposals(path)] == [proposal["id"]]

    # And a final ruling after a defer is allowed too, and does close it.
    store.append(make_ruling(proposal_id=proposal["id"], decision="accept"), path)
    assert store.pending_proposals(path) == []


def test_a_second_final_ruling_is_refused_and_writes_nothing(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=proposal["id"], decision="accept"), path)

    before = store.load(path)
    with pytest.raises(store.QueueError, match="already has a final ruling"):
        store.append(make_ruling(proposal_id=proposal["id"], decision="reject"), path)

    assert store.load(path) == before  # nothing written by the refused second ruling


def test_a_defer_after_a_reject_is_also_refused(tmp_path):
    """The refusal is about the EXISTING ruling being final, not about what
    the new one is trying to say: even a further defer is refused once the
    proposal already has a final ruling."""
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    store.append(make_ruling(proposal_id=proposal["id"], decision="reject"), path)

    with pytest.raises(store.QueueError, match="already has a final ruling"):
        store.append(make_ruling(proposal_id=proposal["id"], decision="defer"), path)


def test_pending_proposals_is_oldest_first(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    second = store.append(make_proposal(), path, game_tick=100)
    third = store.append(make_proposal(), path, game_tick=100)

    assert [r["id"] for r in store.pending_proposals(path)] == [
        first["id"], second["id"], third["id"],
    ]


def test_pending_proposals_respects_limit(tmp_path):
    path = _db(tmp_path)
    first = store.append(make_proposal(), path, game_tick=100)
    store.append(make_proposal(), path, game_tick=100)

    assert [r["id"] for r in store.pending_proposals(path, limit=1)] == [first["id"]]


def test_pending_proposals_never_returns_a_pass_record(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=100)
    store.append(make_pass(), path)

    assert [r["id"] for r in store.pending_proposals(path)] == [proposal["id"]]


def test_pending_proposals_of_an_empty_queue_is_empty(tmp_path):
    path = _db(tmp_path)
    assert store.pending_proposals(path) == []


# ---- export_jsonl -----------------------------------------------------------------


def test_export_jsonl_is_deterministic_and_git_trackable(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=0)
    store.append(make_pass(), path)

    out_dir = tmp_path / "export"
    store.export_jsonl(path, out_dir)

    records_text = (out_dir / "records.jsonl").read_text(encoding="utf-8")
    predictions_text = (out_dir / "predictions.jsonl").read_text(encoding="utf-8")

    record_lines = [json.loads(l) for l in records_text.splitlines()]
    assert len(record_lines) == 2
    assert {r["kind"] for r in record_lines} == {"proposal", "pass"}

    prediction_lines = [json.loads(l) for l in predictions_text.splitlines()]
    assert len(prediction_lines) == 1
    assert prediction_lines[0]["signal"] == "fort.population"

    # A second export of the same, unchanged database is byte-identical.
    out_dir2 = tmp_path / "export2"
    store.export_jsonl(path, out_dir2)
    assert (out_dir / "records.jsonl").read_bytes() == (out_dir2 / "records.jsonl").read_bytes()
    assert (
        (out_dir / "predictions.jsonl").read_bytes()
        == (out_dir2 / "predictions.jsonl").read_bytes()
    )


# ---- void_prediction: admin-only, keeps the record visible ----------------------
#
# handoffs/2026-09-22-loop-conductor-service.md item 3;
# decisions/DECISIONS.md 2026-09-22 ("proposal-0001 is voided with a note").


def test_void_prediction_flips_status_and_keeps_the_proposal_visible(tmp_path):
    path = _db(tmp_path)
    proposal = store.append(make_proposal(), path, game_tick=1000)

    result = store.void_prediction(path, proposal["id"], "fort has changed completely; voided per user's call")
    assert result["proposal_id"] == proposal["id"]
    assert result["status"] == store.VOID
    assert result["note"] == "fort has changed completely; voided per user's call"
    assert result["voided_at"]

    # The proposal RECORD itself is untouched, still loadable and unchanged.
    loaded = store.load(path)
    assert len(loaded) == 1
    assert loaded[0] == proposal

    # The prediction row now carries the reason, never silently disappears.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, grade_note, graded_at FROM predictions WHERE record_id = ?",
            (proposal["id"],),
        ).fetchone()
    assert row["status"] == store.VOID
    assert row["grade_note"] == "fort has changed completely; voided per user's call"
    assert row["graded_at"]


def test_void_prediction_is_skipped_by_the_grader(tmp_path):
    """The whole point: a voided prediction must never show up as due,
    however overdue its (possibly pre-migration) due_game_tick is."""
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)
    _accept_and_execute(path, written["id"], execution_cycle=0)  # due at tick 1200

    assert len(store.pending_due(path, 1200)) == 1  # due and still gradeable before voiding

    store.void_prediction(path, written["id"], "left over from a superseded design")

    assert store.pending_due(path, 10**9) == []  # never due again, at any tick


def test_void_prediction_works_on_an_awaiting_execution_proposal(tmp_path):
    """proposal-0001's own real shape: ruled but never executed, so its
    prediction never left AWAITING_EXECUTION. Voiding must not require an
    execution record first."""
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)

    result = store.void_prediction(path, written["id"], "ruled but never executed; fort has moved on")
    assert result["status"] == store.VOID


def test_void_prediction_requires_a_non_empty_note(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)

    with pytest.raises(store.QueueError, match="note"):
        store.void_prediction(path, written["id"], "")
    with pytest.raises(store.QueueError, match="note"):
        store.void_prediction(path, written["id"], "   ")

    # Nothing written: still voidable afterward, proving the refusal above
    # left the prediction's status untouched.
    result = store.void_prediction(path, written["id"], "a real reason")
    assert result["status"] == store.VOID


def test_void_prediction_refuses_an_unknown_proposal_id(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="proposal-9999"):
        store.void_prediction(path, "proposal-9999", "a real reason")


def test_void_prediction_refuses_an_already_graded_prediction(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)
    _accept_and_execute(path, written["id"], execution_cycle=0)
    due = store.pending_due(path, 1200)
    store.apply_grades(path, [{
        "id": due[0]["id"], "status": GRADED_TRUE, "actual_value": 15,
        "graded_at": "2026-09-15T00:00:00+00:00", "grade_note": "",
    }])

    with pytest.raises(store.QueueError, match="already"):
        store.void_prediction(path, written["id"], "too late, already graded")


def test_void_prediction_refuses_a_second_void(tmp_path):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)
    store.void_prediction(path, written["id"], "first void")

    with pytest.raises(store.QueueError, match="already"):
        store.void_prediction(path, written["id"], "second void attempt")


def test_cli_void_writes_json_to_stdout(tmp_path, capsys):
    path = _db(tmp_path)
    written = store.append(make_proposal(), path, game_tick=0)

    exit_code = store._cli_void([
        "--db", str(path), "--proposal-id", written["id"], "--note", "cli round trip",
    ])
    assert exit_code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["proposal_id"] == written["id"]
    assert out["status"] == store.VOID
    assert out["note"] == "cli round trip"


def test_cli_void_reports_a_refusal_on_stderr_and_returns_nonzero(tmp_path, capsys):
    path = _db(tmp_path)

    exit_code = store._cli_void([
        "--db", str(path), "--proposal-id", "proposal-9999", "--note", "does not exist",
    ])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    err = json.loads(captured.err)
    assert "proposal-9999" in err["error"]


# ---- project / step_targets fold (handoffs/2026-09-28-dfqueue-project-step-schema.md) ---


def _rule_and_project(path, *, proposal_id="proposal-0001", project_overrides=None, ruling_id=None):
    ruling = store.append(make_ruling(id=ruling_id, proposal_id=proposal_id), path)
    project = store.append(
        make_project(from_ruling=ruling["id"], **(project_overrides or {})), path,
    )
    return ruling, project


def test_project_with_no_steps_becomes_a_valid_one_step_project_unchanged(tmp_path):
    """design §5.3: "a proposal with no steps block is a one-step project,
    so every existing proposal type keeps working unchanged." A `ruling`
    with no `steps` given at all still round-trips through `store.append`,
    and the stored project carries exactly one synthetic, non-tool-bound
    step -- and an `executed` record for that ruling still works with NO
    `step_id` at all, exactly as it did before this stream."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path, project_overrides={"steps": []})

    assert len(project["steps"]) == 1
    step = project["steps"][0]
    assert step["tool"] is None
    assert step["implicit"] is True

    # Unchanged legacy behaviour: no step_id needed to execute.
    executed = store.append(make_executed(ruling_id=ruling["id"], cycle=101), path)
    assert executed.get("step_id") is None

    status = store.project_status(path, project["id"])
    assert status["status"] == "done"  # an executed record exists for this ruling
    assert status["counts"] == {}  # nothing tracked at per-target granularity


def test_project_omitted_steps_key_also_becomes_one_step(tmp_path):
    """Same as above but via an absent `steps` key rather than an explicit
    empty list -- both spellings of "no steps block" are treated alike."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(make_ruling(proposal_id="proposal-0001"), path)
    record = make_project(from_ruling=ruling["id"])
    del record["steps"]
    project = store.append(record, path)
    assert len(project["steps"]) == 1
    assert project["steps"][0]["implicit"] is True


def test_project_from_ruling_must_be_an_accepted_ruling(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(
        make_ruling(proposal_id="proposal-0001", decision="reject"), path,
    )
    with pytest.raises(store.QueueError, match="not.*accept"):
        store.append(make_project(from_ruling=ruling["id"]), path)


def test_project_second_project_for_same_ruling_refused(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="already has a project"):
        store.append(make_project(from_ruling=ruling["id"]), path)


def test_executed_step_id_must_belong_to_the_ruling_own_project(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="not a step"):
        store.append(
            make_executed(ruling_id=ruling["id"], cycle=2, step_id="no-such-step"), path,
        )


def test_executed_step_id_before_any_project_is_refused(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(make_ruling(proposal_id="proposal-0001"), path)
    with pytest.raises(store.QueueError, match="no project yet"):
        store.append(
            make_executed(ruling_id=ruling["id"], cycle=2, step_id="whatever/s1"), path,
        )


def test_target_state_folds_correctly_from_append_only_records(tmp_path):
    """design §4.4/§4.5: `step_targets` is a materialised fold over
    append-only `project`/`executed` records, the same pattern
    `predictions` already uses. Seeded at `waiting`/`ready` when the project
    is written, then updated by each `executed` action that names
    `targets`+`target_state` -- never edited any other way."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0]["id"], project["steps"][1]["id"]

    # Seeded: s1 has no requires -> ready; s2 requires s1 -> waiting.
    rows = {(r["step_id"], r["target"]): r["state"] for r in store.target_states(path, project["id"])}
    assert rows[(s1, "ring-13-ore-1")] == store.READY
    assert rows[(s1, "ring-13-ore-2")] == store.READY
    # s2's targets are dynamic (`from_step`), so nothing is seeded for it yet.
    assert not any(step_id == s2 for step_id, _ in rows)

    # Two of s1's three targets get issued; two dig jobs designated.
    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=5, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                "target_state": "issued", "game_refs": [2701, 2702],
            }],
        ),
        path,
    )
    rows = {(r["step_id"], r["target"]): r["state"] for r in store.target_states(path, project["id"])}
    assert rows[(s1, "ring-13-ore-1")] == store.ISSUED
    assert rows[(s1, "ring-13-ore-2")] == store.ISSUED

    # Later: the fort finishes both, a second executed record marks them done.
    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=9, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                "target_state": "done",
            }],
        ),
        path,
    )
    rows_list = store.target_states(path, project["id"])
    rows = {(r["step_id"], r["target"]): r for r in rows_list}
    assert rows[(s1, "ring-13-ore-1")]["state"] == store.DONE
    assert rows[(s1, "ring-13-ore-1")]["last_tick"] == 9
    # The third target was never mentioned by any executed action: still ready.
    assert rows[(s1, "ring-13-ore-3")]["state"] == store.READY

    # "4 of 5 issued, 1 held"-shaped counting, via project_status.
    status = store.project_status(path, project["id"])
    assert status["counts"][store.DONE] == 2
    assert status["counts"][store.READY] == 1
    assert status["status"] == "active"  # s1 not fully done, s2 not started


def test_target_state_fold_records_a_held_target_with_its_reason(tmp_path):
    """s2's own `requires: [s1]` (`trigger: all_done`) must be satisfied
    before an `executed` record naming s2 is accepted at all (item 2,
    `handoffs/2026-10-01-queue-bugs-and-amend.md`), so s1 is finished first
    -- this test's own point (a held target's reason surviving into
    `project_status`) is otherwise unaffected."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1 = project["steps"][0]["id"]
    s2 = project["steps"][1]["id"]

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=10, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
        path,
    )

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=20, step_id=s2,
            actions=[{
                "tool": "construction.build", "outcome": "success",
                "targets": ["ring-13-wall-5"], "target_state": "held",
                "detail": "would cut off exposed ore that is still to be worked",
            }],
        ),
        path,
    )
    status = store.project_status(path, project["id"])
    assert status["top_blocker"] == {
        "step_id": s2, "target": "ring-13-wall-5",
        "reason": "would cut off exposed ore that is still to be worked",
    }
    assert status["counts"][store.HELD] == 1


def test_rollback_drift_flags_a_target_recorded_after_the_current_tick(tmp_path):
    """design §4.4, "Rollback": a target's `last_tick` after the fort's
    CURRENT tick means the world has gone backwards (a crash reload) since
    that record was written. `rollback_drift` takes the current tick as a
    plain argument -- it never reads DFHack itself."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1 = project["steps"][0]["id"]

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=500, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1"], "target_state": "done",
            }],
        ),
        path,
    )

    # The world is now at tick 300 -- BEFORE the tick that record claims,
    # e.g. a crash rolled it back to an earlier save.
    drift = store.rollback_drift(path, project["id"], current_tick=300)
    assert len(drift) == 1
    assert drift[0]["target"] == "ring-13-ore-1"
    assert drift[0]["status"] == "contradicted"
    assert drift[0]["reason"] == "world_rolled_back"
    assert drift[0]["recorded_tick"] == 500

    # No drift once the world has actually caught back up.
    assert store.rollback_drift(path, project["id"], current_tick=500) == []
    assert store.rollback_drift(path, project["id"], current_tick=600) == []


def test_trigger_all_success_requires_every_target_done(tmp_path):
    step = {"id": "s2", "requires": ["s1"], "trigger": "all_success"}
    assert not store.step_prerequisites_satisfied(step, {"s1": [store.ISSUED, store.DONE]})
    assert not store.step_prerequisites_satisfied(step, {"s1": [store.DONE, store.FAILED]})
    assert store.step_prerequisites_satisfied(step, {"s1": [store.DONE, store.DONE]})


def test_trigger_all_done_accepts_any_finished_outcome(tmp_path):
    """"mine the vein" can end with some tiles unmineable, and the wall
    step should still run on the ones that were (design §2.2)."""
    step = {"id": "s2", "requires": ["s1"], "trigger": "all_done"}
    assert store.step_prerequisites_satisfied(step, {"s1": [store.DONE, store.FAILED, store.ABANDONED]})
    assert not store.step_prerequisites_satisfied(step, {"s1": [store.DONE, store.ISSUED]})
    assert not store.step_prerequisites_satisfied(step, {"s1": [store.DONE, store.HELD]})


def test_trigger_unsatisfied_when_prerequisite_untracked(tmp_path):
    """A required step with no recorded targets at all (never seeded, or a
    dynamic `from_step` step whose predecessor has not run yet) is never
    vacuously satisfied."""
    step = {"id": "s2", "requires": ["s1"], "trigger": "all_success"}
    assert not store.step_prerequisites_satisfied(step, {})
    assert not store.step_prerequisites_satisfied(step, {"s1": []})


# ---- observation ---------------------------------------------------------------


def test_observation_project_id_and_step_id_must_exist(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)

    with pytest.raises(store.QueueError, match="does not refer to an existing project"):
        store.append(
            make_observation(project_id="no-such-project", step_id=project["steps"][0]["id"]), path,
        )

    with pytest.raises(store.QueueError, match="not a step"):
        store.append(make_observation(project_id=project["id"], step_id="no-such-step"), path)


def test_observation_round_trips_and_never_touches_step_targets(tmp_path):
    """design §4.4: "Observations never change recorded state." Writing one
    must not alter `step_targets` at all."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1 = project["steps"][0]["id"]

    before = store.target_states(path, project["id"])
    store.append(make_observation(project_id=project["id"], step_id=s1), path)
    after = store.target_states(path, project["id"])
    assert before == after

    loaded = store.load(path)
    assert loaded[-1]["kind"] == schema.OBSERVATION
    xml = render.to_xml(loaded[-1])
    assert xml.startswith("<observation ")


# ---- item 1: a step (and a project) with no rows yet is never vacuously
# "done" (handoffs/2026-10-01-queue-bugs-and-amend.md) -------------------------


def test_step_status_is_never_vacuously_done_with_no_rows_and_no_executed_record():
    """The literal bug: `all(state in (...) for state in [])` is `True` in
    Python, so a step never seeded at all used to read `done` by
    construction. `step_status` must read `active` instead."""
    assert store.step_status([], has_executed_record=False) == "active"
    assert store.step_status([], has_executed_record=True) == store.DONE
    assert store.step_status([store.DONE, store.DONE], has_executed_record=False) == store.DONE
    assert store.step_status([store.DONE, store.READY], has_executed_record=False) == "active"


def test_project_status_active_while_an_unseeded_step_has_not_run(tmp_path):
    """The project-level shape of the same bug: s1 (literal targets) fully
    `done`, s2 (dynamic `from_step`, never seeded, never executed) still
    open. The OLD code folded every seeded row into one flat list and
    called `all()` over just that -- s2 contributed nothing to the list, so
    it could not stop the project from reading `done`. It must read
    `active`."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1 = project["steps"][0]["id"]

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=9, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
        path,
    )
    status = store.project_status(path, project["id"])
    assert status["status"] == "active"  # s2 never touched -- not done


def test_project_status_done_once_every_step_including_the_unseeded_one_finishes(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0]["id"], project["steps"][1]["id"]

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=9, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
        path,
    )
    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=12, step_id=s2,
            actions=[{"tool": "construction.build", "outcome": "success"}],
        ),
        path,
    )
    status = store.project_status(path, project["id"])
    assert status["status"] == "done"
    assert status["version"] == 1


# ---- item 2: queue.executed checks the step's own tool and requires ---------


def test_executed_refuses_a_tool_that_does_not_match_the_steps_own_declaration(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1 = project["steps"][0]["id"]

    with pytest.raises(store.QueueError, match="does not match step"):
        store.append(
            make_executed(
                ruling_id=ruling["id"], cycle=5, step_id=s1,
                actions=[{"tool": "workshop.build", "outcome": "success"}],
            ),
            path,
        )


def test_executed_refuses_a_step_whose_requires_are_not_yet_satisfied(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s2 = project["steps"][1]["id"]  # requires s1, trigger all_done

    with pytest.raises(store.QueueError, match="not yet satisfied"):
        store.append(
            make_executed(
                ruling_id=ruling["id"], cycle=5, step_id=s2,
                actions=[{"tool": "construction.build", "outcome": "success"}],
            ),
            path,
        )


def test_executed_allowed_once_requires_are_satisfied(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0]["id"], project["steps"][1]["id"]

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=5, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
        path,
    )
    # No longer refused: s1 is fully done, satisfying s2's all_done trigger.
    executed = store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=6, step_id=s2,
            actions=[{"tool": "construction.build", "outcome": "success"}],
        ),
        path,
    )
    assert executed["step_id"] == s2


def test_executed_implicit_step_keeps_its_old_rules(tmp_path):
    """No `step_id` at all (the legacy one-step-project path) is exempt from
    both new checks -- `make_executed`'s own default action tool
    (`workshop.build`) does not match anything because there is no step to
    match against."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(make_ruling(proposal_id="proposal-0001"), path)
    store.append(make_project(from_ruling=ruling["id"], steps=[]), path)
    executed = store.append(make_executed(ruling_id=ruling["id"], cycle=2), path)
    assert executed.get("step_id") is None


# ---- item 3: amend / abandon ---------------------------------------------------


def test_amend_project_id_must_be_a_real_project(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="does not refer to an existing project"):
        store.append(make_amend(project_id="no-such-project"), path)


def test_amend_replaces_names_a_step_id_from_the_previous_version(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="is not a step id in the previous version"):
        store.append(
            make_amend(project_id=project["id"], replaces=["no-such-step"]), path,
        )


def test_amend_adds_must_name_a_step_id_in_its_own_new_steps(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="is not a step id in this amendment"):
        store.append(
            make_amend(project_id=project["id"], adds=["not-a-new-step"]), path,
        )


def test_amend_accepts_a_reused_step_id_that_is_byte_identical(tmp_path):
    """A step id kept from the previous version, with its own definition
    unchanged (canonical JSON identical), round-trips clean -- this is the
    ordinary case of "amend one step, leave the other alone"."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0], project["steps"][1]

    written = store.append(
        make_amend(
            project_id=project["id"],
            replaces=[],
            adds=[],
            drops=[],
            steps=[copy.deepcopy(s1), copy.deepcopy(s2)],
        ),
        path,
    )
    assert [s["id"] for s in written["steps"]] == [s1["id"], s2["id"]]


def test_amend_refuses_reusing_a_step_id_whose_definition_changed(tmp_path):
    """Enforcement, not convention (user's call, 2026-10-01): a step id kept
    from the previous version but silently redefined (here, s1's own
    `targets` shrinks from three tiles to two, everything else the same) is
    refused, naming the step id -- it must take a fresh id and list the old
    one in replaces/drops instead. This is what closes the target-seeding
    gap this handoff first only flagged: without it, the DROPPED target's
    row would linger in step_targets under a live id forever."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0], project["steps"][1]
    changed_s1 = copy.deepcopy(s1)
    changed_s1["targets"]["set"] = changed_s1["targets"]["set"][:-1]  # drop one target

    with pytest.raises(store.QueueError, match=re.escape(s1["id"]) + r".*definition changed"):
        store.append(
            make_amend(
                project_id=project["id"],
                replaces=[s1["id"]],
                adds=[],
                drops=[],
                steps=[changed_s1, copy.deepcopy(s2)],
            ),
            path,
        )


def test_amend_label_only_change_keeps_the_same_step_id(tmp_path):
    """`handoffs/2026-10-02-queue-display-fields.md`: changing only a step's
    `label` (cosmetic display text the reconciler never reads) must NOT
    trip the byte-identical reuse check -- a label-only edit keeps the same
    step id, unlike a real definition change (see the refusal test above,
    which still fires for `targets`)."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0], project["steps"][1]
    relabelled_s1 = copy.deepcopy(s1)
    relabelled_s1["label"] = "Mine the vein"

    written = store.append(
        make_amend(
            project_id=project["id"],
            replaces=[],
            adds=[],
            drops=[],
            steps=[relabelled_s1, copy.deepcopy(s2)],
        ),
        path,
    )
    assert [s["id"] for s in written["steps"]] == [s1["id"], s2["id"]]
    assert written["steps"][0]["label"] == "Mine the vein"


def test_amend_accepts_a_changed_step_under_a_fresh_id(tmp_path):
    """The enforced escape hatch: a changed step takes a NEW id, and the
    old one is named in `drops` (or `replaces`) -- never redefined in
    place. Changes s2 rather than s1: s1 has a dependent (s2's own
    `requires`/`from_step`), and renaming a step with a dependent would
    force the dependent to change too, which is a different scenario than
    this test means to isolate."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    s1, s2 = project["steps"][0], project["steps"][1]
    new_s2 = copy.deepcopy(s2)
    new_s2["id"] = "project-0001/s2-v2"
    new_s2["trigger"] = "all_success"  # was all_done: a real, isolated change

    written = store.append(
        make_amend(
            project_id=project["id"],
            replaces=[],
            adds=["project-0001/s2-v2"],
            drops=[s2["id"]],
            steps=[copy.deepcopy(s1), new_s2],
        ),
        path,
    )
    assert [s["id"] for s in written["steps"]] == [s1["id"], "project-0001/s2-v2"]


def test_amend_bumps_the_version_and_project_status_reads_the_latest_one(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)

    status_v1 = store.project_status(path, project["id"])
    assert status_v1["version"] == 1

    # v2 drops the original two-step plan down to one BRAND NEW step,
    # replacing both s1 and s2 (a different id, never the same id with a
    # shrunk target set -- reusing an id would leave the OLD version's own
    # rows for the targets it no longer declares sitting in step_targets
    # forever, since an amendment only ever adds rows, never prunes one a
    # later version stopped naming; see this handoff's Result section).
    store.append(
        make_amend(
            project_id=project["id"],
            replaces=[],
            adds=["project-0001/s1b"],
            drops=["project-0001/s1", "project-0001/s2"],
            steps=[{
                "id": "project-0001/s1b",
                "tool": "construction.mine-vein",
                "args": {},
                "targets": {"set": ["ring-13-ore-1", "ring-13-ore-2"]},
                "requires": [],
                "trigger": "all_success",
                "prefer_after": [],
                "guards": "default",
            }],
        ),
        path,
    )

    status_v2 = store.project_status(path, project["id"])
    assert status_v2["version"] == 2
    assert status_v2["status"] == "active"  # the new step has not run yet

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=9, step_id="project-0001/s1b",
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2"],
                "target_state": "done",
            }],
        ),
        path,
    )
    status_v2_done = store.project_status(path, project["id"])
    assert status_v2_done["status"] == "done"


def test_amend_seeds_a_brand_new_step_added_by_the_amendment(tmp_path):
    """A step an amendment ADDS (not present in the original version) must
    still be reachable by `queue.executed`, and its literal targets get
    seeded the same way a fresh project's own steps do."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)

    store.append(
        make_amend(
            project_id=project["id"],
            adds=["project-0001/s3"],
            steps=project["steps"] + [{
                "id": "project-0001/s3",
                "tool": "construction.build",
                "args": {"kind": "Floor"},
                "targets": {"set": ["ring-13-floor-1"]},
                "requires": [],
                "trigger": "all_success",
                "prefer_after": [],
                "guards": "default",
            }],
        ),
        path,
    )

    rows = {r["target"]: r["state"] for r in store.target_states(path, project["id"])
            if r["step_id"] == "project-0001/s3"}
    assert rows == {"ring-13-floor-1": store.READY}

    executed = store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=9, step_id="project-0001/s3",
            actions=[{
                "tool": "construction.build", "outcome": "success",
                "targets": ["ring-13-floor-1"], "target_state": "done",
            }],
        ),
        path,
    )
    assert executed["step_id"] == "project-0001/s3"


def test_amend_does_not_overwrite_the_original_project_record(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    original_steps = copy.deepcopy(project["steps"])

    # A fresh id for the changed step (never the old id with a shrunk
    # target set -- item 3's own byte-identical-reuse rule would refuse
    # that; see test_amend_refuses_reusing_a_step_id_whose_definition_changed).
    store.append(
        make_amend(
            project_id=project["id"],
            drops=["project-0001/s1"],
            adds=["project-0001/s1b"],
            steps=[{
                "id": "project-0001/s1b",
                "tool": "construction.mine-vein",
                "args": {},
                "targets": {"set": ["ring-13-ore-1"]},
                "requires": [],
                "trigger": "all_success",
                "prefer_after": [],
                "guards": "default",
            }],
        ),
        path,
    )

    reloaded = json.loads(
        json.dumps(
            [r for r in store.load(path) if r["kind"] == schema.PROJECT][0]
        )
    )
    assert reloaded["steps"] == original_steps


def test_amend_role_must_be_the_sole_writer(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="sole_writer"):
        store.append(make_amend(project_id=project["id"], role="architect"), path)


def test_abandon_project_id_must_be_a_real_project(tmp_path):
    path = _db(tmp_path)
    with pytest.raises(store.QueueError, match="does not refer to an existing project"):
        store.append(make_abandon(project_id="no-such-project"), path)


def test_abandon_refuses_a_second_abandon(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    store.append(make_abandon(project_id=project["id"]), path)
    with pytest.raises(store.QueueError, match="already abandoned"):
        store.append(make_abandon(project_id=project["id"]), path)


def test_abandon_refuses_an_amend_afterwards(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    store.append(make_abandon(project_id=project["id"]), path)
    with pytest.raises(store.QueueError, match="is abandoned"):
        store.append(make_amend(project_id=project["id"]), path)


def test_abandon_marks_project_status_abandoned_with_reason_and_leaves_executed_history(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    s1 = project["steps"][0]["id"]

    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=5, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1"], "target_state": "done",
            }],
        ),
        path,
    )
    before_counts = store.project_status(path, project["id"])["counts"]

    reason = "The vein played out; the whole ring is walled off already."
    store.append(make_abandon(project_id=project["id"], reason=reason), path)

    status = store.project_status(path, project["id"])
    assert status["status"] == store.PROJECT_ABANDONED
    assert status["abandoned_reason"] == reason
    # Executed history untouched: the same target-state counts as before.
    assert status["counts"] == before_counts


def test_abandon_role_must_be_the_sole_writer(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _ruling, project = _rule_and_project(path)
    with pytest.raises(store.QueueError, match="sole_writer"):
        store.append(make_abandon(project_id=project["id"], role="architect"), path)
