"""`dfqueue.store`: SQLite append-only writes, refusal-with-nothing-written
in either table, atomic proposal+prediction inserts, and the
`latest`/`pending_due`/`export_jsonl` query helpers the feed and grader need.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from dfqueue import render, schema, store
from dfqueue.tests._helpers import (
    make_answer, make_ask, make_executed, make_pass, make_proposal,
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
