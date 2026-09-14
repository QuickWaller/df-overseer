"""`dfqueue.store`: SQLite append-only writes, refusal-with-nothing-written
in either table, atomic proposal+prediction inserts, and the
`latest`/`pending_due`/`export_jsonl` query helpers the feed and grader need.
"""

from __future__ import annotations

import json

import pytest

from dfqueue import render, schema, store
from dfqueue.tests._helpers import make_pass, make_proposal, make_ruling
from learning.predictions.schema import GRADED_TRUE, PENDING


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
    # due_game_tick = 1000 + 500 = 1500

    assert store.pending_due(path, 1499) == []

    due_at = store.pending_due(path, 1500)
    assert len(due_at) == 1
    row = due_at[0]
    assert row["record_id"] == written["id"]
    assert row["signal"] == "fort.population"
    assert row["op"] == "gte"
    assert row["value"] == 1
    assert row["registered_game_tick"] == 1000
    assert row["due_game_tick"] == 1500
    assert row["status"] == PENDING
    assert row["actual_value"] is None

    assert len(store.pending_due(path, 5000)) == 1  # still there, "at or before"


def test_pending_due_excludes_a_graded_prediction(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=0)  # check_after_ticks=1200 -> due 1200

    due = store.pending_due(path, 1200)
    assert len(due) == 1

    store.apply_grades(path, [{
        "id": due[0]["id"], "status": GRADED_TRUE, "actual_value": 15,
        "graded_at": "2026-09-15T00:00:00+00:00", "grade_note": "",
    }])

    assert store.pending_due(path, 1200) == []


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
