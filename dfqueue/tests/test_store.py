"""`dfqueue.store`: append-only writes, refusal-with-nothing-written, and the
proposal/pass/ruling round trip through append -> load -> to_xml.
"""

from __future__ import annotations

import pytest

from dfqueue import render, schema, store
from dfqueue.tests._helpers import make_pass, make_proposal, make_ruling


def test_append_then_load_round_trips_a_proposal(tmp_path):
    path = tmp_path / "queue.jsonl"
    written = store.append(make_proposal(), path)

    assert written["id"]  # assigned
    assert written["ts"]  # assigned, UTC

    loaded = store.load(path)
    assert len(loaded) == 1
    assert loaded[0] == written

    xml = render.to_xml(loaded[0])
    assert xml.startswith("<proposal ")
    assert "<type>workshop_siting</type>" in xml
    assert 'signal="design.entrance_count"' in xml


def test_append_then_load_round_trips_a_pass(tmp_path):
    path = tmp_path / "queue.jsonl"
    written = store.append(make_pass(), path)

    loaded = store.load(path)
    assert loaded == [written]

    xml = render.to_xml(loaded[0])
    assert xml.startswith("<pass ")
    assert "<reason>" in xml


def test_append_then_load_round_trips_a_ruling(tmp_path):
    path = tmp_path / "queue.jsonl"
    proposal = store.append(make_proposal(), path)
    ruling = store.append(make_ruling(proposal_id=proposal["id"]), path)

    loaded = store.load(path)
    assert loaded == [proposal, ruling]

    xml = render.to_xml(loaded[1])
    assert xml.startswith("<ruling ")
    assert f"<proposal_id>{proposal['id']}</proposal_id>" in xml


def test_id_and_ts_are_assigned_when_absent(tmp_path):
    path = tmp_path / "queue.jsonl"
    record = make_proposal()
    assert "id" not in record and "ts" not in record

    written = store.append(record, path)
    assert written["id"] == "proposal-0001"
    assert written["ts"]

    second = store.append(make_proposal(), path)
    assert second["id"] == "proposal-0002"


def test_id_and_ts_are_preserved_when_present(tmp_path):
    path = tmp_path / "queue.jsonl"
    record = make_proposal(id="p-0001", ts="2026-09-14T00:00:00+00:00")
    written = store.append(record, path)
    assert written["id"] == "p-0001"
    assert written["ts"] == "2026-09-14T00:00:00+00:00"


# ---- refusals write nothing ----------------------------------------------------


def test_append_refuses_an_invalid_record_and_writes_nothing(tmp_path):
    path = tmp_path / "queue.jsonl"
    bad = make_proposal(suggested_priority=99)

    with pytest.raises(store.QueueError):
        store.append(bad, path)

    assert not path.exists()


def test_append_refuses_a_second_write_after_a_prior_refusal_leaves_file_intact(tmp_path):
    path = tmp_path / "queue.jsonl"
    good = store.append(make_proposal(), path)
    before = path.read_text(encoding="utf-8")

    bad = make_proposal(cost={"estimate": -1, "unit": "dwarf_ticks"})
    with pytest.raises(store.QueueError):
        store.append(bad, path)

    after = path.read_text(encoding="utf-8")
    assert after == before
    assert store.load(path) == [good]


def test_dangling_proposal_id_is_refused(tmp_path):
    path = tmp_path / "queue.jsonl"
    ruling = make_ruling(proposal_id="proposal-9999")

    with pytest.raises(store.QueueError, match="does not refer to an existing proposal"):
        store.append(ruling, path)

    assert not path.exists()


def test_ruling_against_a_real_proposal_from_a_different_queue_is_still_dangling(tmp_path):
    # Appending a ruling to an *empty* queue that references an id that
    # would be valid in some other fort's queue must still be refused: the
    # check is against this file, not against ids in general.
    other_path = tmp_path / "other-fort.jsonl"
    proposal = store.append(make_proposal(), other_path)

    path = tmp_path / "queue.jsonl"
    ruling = make_ruling(proposal_id=proposal["id"])
    with pytest.raises(store.QueueError, match="does not refer to an existing proposal"):
        store.append(ruling, path)
    assert not path.exists()


def test_duplicate_explicit_id_is_refused(tmp_path):
    path = tmp_path / "queue.jsonl"
    store.append(make_proposal(id="dupe"), path)
    with pytest.raises(store.QueueError, match="already in the queue"):
        store.append(make_pass(id="dupe"), path)


# ---- load() behaviour ------------------------------------------------------------


def test_load_of_a_missing_file_returns_empty(tmp_path):
    assert store.load(tmp_path / "nope.jsonl") == []


def test_load_raises_on_a_corrupt_line_rather_than_skipping_it(tmp_path):
    path = tmp_path / "queue.jsonl"
    store.append(make_proposal(), path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind": "proposal", "role": "architect"}\n')  # missing fields

    with pytest.raises(store.QueueError):
        store.load(path)


def test_default_path_uses_the_roster_fort_name():
    assert store.default_path().name == f"{schema.fort_name()}.jsonl"
