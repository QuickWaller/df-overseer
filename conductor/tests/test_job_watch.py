"""conductor/job_watch.py: stuck jobs polled from stuckjobs.find."""

from __future__ import annotations

import json

import pytest

from conductor.job_watch import (
    JobWatchStore, MAX_DETAIL_LINES, describe, evaluate_jobs, jobs_from_result,
)

THRESH = 2400
RENOTIFY = 12000


def _job(**kw):
    base = {
        "job_type": "ConstructBuilding", "detail": "Construct Bed", "building": "Bed",
        "waiting_on": "suspended", "idle_ticks": None, "near_landmark": "Well",
        "direction": "N", "distance_tiles": 4, "order_id": None, "from_order": None,
    }
    base.update(kw)
    return base


def _run(store, jobs, tick, dry_run=False, **kw):
    return evaluate_jobs(
        jobs, game_tick=tick, unclaimed_threshold_ticks=kw.get("unclaimed", THRESH),
        suspended_threshold_ticks=kw.get("suspended", THRESH), renotify_ticks=RENOTIFY,
        store=store, dry_run=dry_run,
    )


@pytest.fixture
def store(tmp_path):
    return JobWatchStore(tmp_path / "job_watch.json")


def test_a_fresh_job_does_not_fire_before_the_threshold(store):
    assert not _run(store, [_job()], 10_000).any_due
    assert not _run(store, [_job()], 10_000 + THRESH - 1).any_due


def test_a_job_fires_once_at_the_threshold_then_stays_quiet_until_renotify(store):
    _run(store, [_job()], 10_000)
    first = _run(store, [_job()], 10_000 + THRESH)
    assert first.any_due and len(first.stuck) == 1
    again = _run(store, [_job()], 10_000 + THRESH + 100)
    assert not again.any_due
    assert len(again.stuck) == 1  # still reported to the briefing digest
    later = _run(store, [_job()], 10_000 + THRESH + RENOTIFY)
    assert later.any_due


def test_a_job_that_clears_resets_its_clock(store):
    _run(store, [_job()], 10_000)
    _run(store, [], 10_000 + THRESH)  # claimed or finished
    back = _run(store, [_job()], 10_000 + THRESH + 10)
    assert not back.any_due  # fresh clock, not instantly due on stale history
    assert _run(store, [_job()], 10_000 + 2 * THRESH + 10).any_due


def test_suspended_and_unclaimed_use_their_own_thresholds(store):
    jobs = [_job(), _job(detail="Dig", job_type="Dig", building=None, waiting_on="no worker assigned")]
    _run(store, jobs, 0, suspended=5000, unclaimed=1000)
    res = _run(store, jobs, 1000, suspended=5000, unclaimed=1000)
    assert [j.kind for j in res.due] == ["unclaimed"]
    res2 = _run(store, jobs, 5000, suspended=5000, unclaimed=1000)
    assert {j.kind for j in res2.stuck} == {"suspended", "unclaimed"}


def test_two_identical_jobs_are_tracked_separately(store):
    _run(store, [_job()], 0)
    res = _run(store, [_job(), _job()], THRESH)  # second one is new this poll
    assert len(res.stuck) == 1
    res2 = _run(store, [_job(), _job()], 2 * THRESH)
    assert len(res2.stuck) == 2


def test_idle_ticks_is_not_used_as_the_age(store):
    # The tool's idle_ticks measures time since the job started, which a job
    # with a briefly absent worker also accumulates; age is our own sighting.
    res = _run(store, [_job(idle_ticks=999_999)], 10_000)
    assert not res.any_due


def test_dry_run_reads_but_never_writes_state(store):
    _run(store, [_job()], 0, dry_run=True)
    assert not store.path.exists()
    _run(store, [_job()], 0)
    snapshot = store.path.read_text(encoding="utf-8")
    _run(store, [_job()], THRESH, dry_run=True)
    assert store.path.read_text(encoding="utf-8") == snapshot


def test_game_tick_none_is_inert_and_leaves_state_alone(store):
    assert not _run(store, [_job()], None).any_due
    assert not store.path.exists()


def test_detail_is_capped_and_names_the_overflow(store):
    jobs = [_job(detail=f"Job {i}", distance_tiles=i) for i in range(MAX_DETAIL_LINES + 3)]
    _run(store, jobs, 0)
    res = _run(store, jobs, THRESH)
    detail = res.wake_detail()
    assert detail.startswith(f"{len(jobs)} stuck jobs:")
    assert "and 3 more" in detail
    assert detail.count("Job ") == MAX_DETAIL_LINES


def test_describe_is_plain_english():
    line = describe(_job(), "suspended", 3 * 1200 + 5)
    assert line == "Construct Bed suspended for 3 game days, 4 tiles N of Well"
    assert describe(_job(near_landmark=None), "unclaimed", 100) == "Construct Bed unclaimed for 1 game day"
    assert "None" not in describe(_job(detail=None, job_type=None, near_landmark=None), "unclaimed", 5)


def test_state_file_round_trips_and_a_corrupt_one_raises(store):
    _run(store, [_job()], 5)
    assert list(json.loads(store.path.read_text(encoding="utf-8"))["jobs"].values())[0]["first_seen"] == 5
    store.path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        store.load()


def test_jobs_from_result_tolerates_shapes():
    assert jobs_from_result([_job(), "junk"]) == [_job()]
    assert jobs_from_result({"jobs": [_job()]}) == [_job()]
    assert jobs_from_result(None) == []
    assert jobs_from_result({"error": "x"}) == []
