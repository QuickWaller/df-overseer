"""`dfqueue.feed_status`: the read-only equivalent of `store.project_status`
the stream page publisher needs (slice S1, closing the gap `dfqueue/feed.py`'s
own `GAPS` list names).

Builds each test database with `store.append` (the real writer, exercising
the same `step_targets` projection a live fort's queue would have), then
reads it back ONLY through `feed_status`'s read-only functions -- proving
`feed_status` never needs `store._connect` or any write path to answer the
same questions `store.project_status` does. Mirrors
`test_store.py`'s own project-status tests one for one so a future change to
either module's logic is easy to compare against the other.
"""

from __future__ import annotations

import sqlite3

import pytest

from dfqueue import feed_status, store
from dfqueue.tests._helpers import make_executed, make_project, make_proposal, make_ruling


def _db(tmp_path):
    return tmp_path / "queue.sqlite3"


def _rule_and_project(path, *, proposal_id="proposal-0001", project_overrides=None, ruling_id=None):
    ruling = store.append(make_ruling(id=ruling_id, proposal_id=proposal_id), path)
    project = store.append(
        make_project(from_ruling=ruling["id"], **(project_overrides or {})), path,
    )
    return ruling, project


# ---- parity with store.project_status ---------------------------------------


def test_matches_store_for_a_one_step_legacy_project(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path, project_overrides={"steps": []})
    store.append(make_executed(ruling_id=ruling["id"], cycle=101), path)

    assert feed_status.project_status_readonly(path, project["id"]) == (
        store.project_status(path, project["id"])
    )


def test_matches_store_while_an_unseeded_step_has_not_run(tmp_path):
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

    readonly = feed_status.project_status_readonly(path, project["id"])
    assert readonly["status"] == "active"
    assert readonly == store.project_status(path, project["id"])


def test_matches_store_once_every_step_finishes(tmp_path):
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

    readonly = feed_status.project_status_readonly(path, project["id"])
    assert readonly["status"] == "done"
    assert readonly["version"] == 1
    assert readonly == store.project_status(path, project["id"])


def test_matches_store_for_an_abandoned_project(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    ruling, project = _rule_and_project(path)
    store.append(
        {
            "kind": "abandon", "role": "overseer", "cycle": 30,
            "snapshot": "tick 209700", "project_id": project["id"],
            "reason": "The vein played out.",
        },
        path,
    )

    readonly = feed_status.project_status_readonly(path, project["id"])
    assert readonly["status"] == store.PROJECT_ABANDONED
    assert readonly["abandoned_reason"] == "The vein played out."
    assert readonly == store.project_status(path, project["id"])


def test_list_project_ids_readonly_matches_store(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _rule_and_project(path)
    store.append(make_proposal(), path, game_tick=100)
    _rule_and_project(path, proposal_id="proposal-0002", ruling_id="ruling-0002")

    assert (
        feed_status.list_project_ids_readonly(path) == store.list_project_ids(path)
    )


def test_all_project_statuses_readonly_covers_every_project(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _, project1 = _rule_and_project(path)
    store.append(make_proposal(), path, game_tick=100)
    _, project2 = _rule_and_project(
        path, proposal_id="proposal-0002", ruling_id="ruling-0002",
    )

    statuses = feed_status.all_project_statuses_readonly(path)
    assert set(statuses) == {project1["id"], project2["id"]}


# ---- never a write path -------------------------------------------------------


def test_project_status_readonly_raises_on_an_unknown_project(tmp_path):
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _rule_and_project(path)

    with pytest.raises(store.QueueError):
        feed_status.project_status_readonly(path, "project-9999")


def test_project_status_readonly_never_creates_a_missing_database(tmp_path):
    """`store._connect` would create the file and its schema on open; the
    read-only URI must not -- a publisher pointed at a not-yet-provisioned
    path must fail loudly, never silently create an empty queue."""
    path = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        feed_status.project_status_readonly(path, "project-0001")
    assert not path.exists()


def test_project_status_readonly_connection_is_actually_read_only(tmp_path):
    """A belt-and-braces check: even calling a write statement over the same
    URI this module opens must fail, proving `mode=ro` is doing real work
    and not just a naming convention."""
    path = _db(tmp_path)
    store.append(make_proposal(), path, game_tick=100)
    _rule_and_project(path)

    conn = feed_status._connect_readonly(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM records")
    finally:
        conn.close()
