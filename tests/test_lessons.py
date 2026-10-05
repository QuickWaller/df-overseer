"""Lessons: gotchas written or confirmed during a run (`dfqueue/lessons.py`)
and the publisher's per-fort `lessons.json`."""
from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, REPO_ROOT)

import stream_publisher as sp  # noqa: E402
from dfqueue import lessons, runs, site_data, store  # noqa: E402
from dfqueue.tests._helpers import make_proposal  # noqa: E402

START, END = "2026-10-05T10:00:00+00:00", "2026-10-05T10:10:00+00:00"


def _run(run_id="run-0001", role="architect", threads=("proposal-0001",), ended=END):
    return {
        "run_id": run_id, "role": role, "started_at": START, "ended_at": ended,
        "records_json": json.dumps([{"id": t, "kind": "proposal", "thread": t} for t in threads]),
    }


def _entry(gid, title, *, role="architect", at="2026-10-05T10:05:00+00:00", outcomes=()):
    return {"id": gid, "title": title, "written_by_role": role, "created_at": at, "outcomes": list(outcomes),
            "list": "gotcha", "body": "b", "status": "active", "tool": None, "kind": None}


def test_a_gotcha_written_in_the_runs_window_by_its_role_is_a_new_lesson():
    out = lessons.build_lessons([_run()], [_entry("gotcha-0001", "Soil never smooths")], public=True)
    assert out == {"lessons": [{
        "run_id": "run-0001", "thread": "proposal-0001", "role": "architect", "kind": "new",
        "gotcha_id": "gotcha-0001", "title": "Soil never smooths", "result": None,
        "at": "2026-10-05T10:05:00+00:00",
    }]}


def test_wrong_role_or_outside_the_window_matches_nothing():
    entries = [
        _entry("gotcha-0001", "Other role", role="overseer"),
        _entry("gotcha-0002", "Too early", at="2026-10-05T09:59:00+00:00"),
        _entry("gotcha-0003", "Too late", at="2026-10-05T10:11:00+00:00"),
    ]
    assert lessons.build_lessons([_run()], entries, public=True) == {"lessons": []}
    assert lessons.build_lessons([_run(ended=None)], [_entry("g", "t")], public=True) == {"lessons": []}


def test_an_outcome_recorded_in_the_window_is_an_outcome_lesson_even_on_an_old_gotcha():
    entry = _entry("gotcha-0001", "Stair needs two miners", at="2026-09-01T00:00:00+00:00", outcomes=[
        {"at": "2026-10-05T10:02:00+00:00", "role": "architect", "result": "worked", "note": "n"},
        {"at": "2026-10-05T10:03:00+00:00", "role": "overseer", "result": "did_not_work", "note": None},
        {"at": "2026-09-02T00:00:00+00:00", "role": "architect", "result": "worked", "note": None},
    ])
    out = lessons.build_lessons([_run()], [entry], public=False)["lessons"]
    assert [(x["kind"], x["result"]) for x in out] == [("outcome", "worked")]


def test_a_lesson_belongs_to_every_thread_its_run_touched():
    out = lessons.build_lessons([_run(threads=("proposal-0001", "proposal-0002", "proposal-0001"))],
                                [_entry("g1", "A thing")], public=True)["lessons"]
    assert [x["thread"] for x in out] == ["proposal-0001", "proposal-0002"]


def test_a_run_that_wrote_no_record_adds_no_lesson():
    assert lessons.build_lessons([_run(threads=())], [_entry("g1", "A thing")], public=True) == {"lessons": []}


def test_unsafe_titles_are_skipped_in_public_but_kept_for_the_operator():
    entries = [_entry("g1", "Dig at /opt/df/secret first"), _entry("g2", "Fine title")]
    pub = lessons.build_lessons([_run()], entries, public=True)["lessons"]
    op = lessons.build_lessons([_run()], entries, public=False)["lessons"]
    assert [x["gotcha_id"] for x in pub] == ["g2"]
    assert sorted(x["gotcha_id"] for x in op) == ["g1", "g2"]


def test_no_inputs_is_an_empty_payload():
    assert lessons.build_lessons(None, None, public=True) == {"lessons": []}


class _Pusher:
    def __call__(self, local_dir, relay, *, delete=False, rsync_bin="rsync"):
        pass


def test_run_cycle_writes_lessons_json_only_with_a_run_store(tmp_path, monkeypatch):
    db = tmp_path / "queue.sqlite3"
    store.append(make_proposal(), db, game_tick=100)
    gotchas_db = tmp_path / "gotchas.sqlite3"
    gotchas_db.write_bytes(b"")
    entries = [_entry("gotcha-0001", "Soil never smooths", at="2099-01-01T00:00:00+00:00")]
    monkeypatch.setattr(site_data, "load_gotchas_readonly", lambda path: entries)
    cfg = sp.PublisherConfig(db_path=str(db), staging_dir=str(tmp_path / "stage"), gotchas_db=str(gotchas_db))
    sp.run_cycle(cfg, now=1.0, pusher=_Pusher())
    assert not (tmp_path / "stage/public/forts/queue/lessons.json").exists()

    rp = runs.runs_path(db)
    run = runs.start_run(rp, role="architect", wake_reason="routine_review", wake_detail="d", cycle=1)
    runs.end_run(
        rp, run_id=run["run_id"], role=None, wake_reason=None, wake_detail=None, cycle=None,
        status="ok", ok=True, timed_out=False, duration_s=5.0, cost_usd=0.01, error=None,
        final_answer="Proposed.", records=[{"id": "proposal-0001", "kind": "proposal", "thread": "proposal-0001"}],
    )
    # Make the gotcha fall in the run's real (wall-clock) window.
    row = runs.get_run(rp, run["run_id"])
    entries[0]["created_at"] = row["started_at"]
    sp.run_cycle(cfg, now=2.0, pusher=_Pusher(), journal_reader=lambda: [])
    for side in ("public", "operator"):
        doc = json.loads((tmp_path / f"stage/{side}/forts/queue/lessons.json").read_text())
        assert [(x["kind"], x["title"], x["thread"]) for x in doc["lessons"]] == [
            ("new", "Soil never smooths", "proposal-0001")]
