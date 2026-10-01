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
from dfqueue.tests._helpers import (
    make_abandon, make_amend, make_executed, make_observation, make_project,
    make_proposal, make_ruling,
)


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


# ---- step_board_states: records-only, no step_targets table ----------------
#
# `step_board_states` and `project_board_status` are a SECOND read path, used
# by the stream board (handoffs/2026-10-02-stream-board.md) precisely
# because the offline fixtures are plain `records.jsonl` with no
# `step_targets` table at all. Every record here is a plain dict (not run
# through `store.append`), matching `test_feed.py`'s own convention.

_PROJECT = make_project(id="project-0001", from_ruling="ruling-0001")
_S1, _S2 = _PROJECT["steps"][0]["id"], _PROJECT["steps"][1]["id"]


def _base_records():
    return [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        dict(_PROJECT),
    ]


def test_step_board_states_fresh_project_is_ready_then_waiting():
    states = feed_status.step_board_states(_base_records(), "project-0001")
    by_id = {s["id"]: s for s in states}
    assert by_id[_S1]["state"] == "ready"  # no requires
    assert by_id[_S2]["state"] == "waiting"  # requires s1, not done
    assert by_id[_S1]["done"] == 0 and by_id[_S1]["total"] == 3


def test_step_board_states_partial_progress_reads_active():
    records = _base_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9, step_id=_S1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1"], "target_state": "issued",
            }],
        ),
    ]
    states = {s["id"]: s for s in feed_status.step_board_states(records, "project-0001")}
    assert states[_S1]["state"] == "active"
    assert states[_S1]["done"] == 0 and states[_S1]["total"] == 3


def test_step_board_states_all_targets_done_reads_done_and_unblocks_next():
    records = _base_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9, step_id=_S1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
    ]
    states = {s["id"]: s for s in feed_status.step_board_states(records, "project-0001")}
    assert states[_S1]["state"] == "done"
    assert states[_S2]["state"] == "ready"


def test_step_board_states_a_held_target_reads_hold_with_private_detail():
    records = _base_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9, step_id=_S1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "blocked",
                "targets": ["ring-13-ore-1"], "target_state": "held",
                "detail": "no free miner",
            }],
        ),
    ]
    states = {s["id"]: s for s in feed_status.step_board_states(records, "project-0001")}
    assert states[_S1]["state"] == "hold"
    assert states[_S1]["held_detail"] == "no free miner"
    # Waiting on a held prerequisite is still "waiting", not "ready".
    assert states[_S2]["state"] == "waiting"


def test_step_board_states_unknown_project_is_empty():
    assert feed_status.step_board_states(_base_records(), "project-9999") == []


def test_step_board_states_legacy_no_steps_project_has_no_job_graph():
    records = [
        make_proposal(id="proposal-0001"),
        make_ruling(id="ruling-0001", proposal_id="proposal-0001"),
        make_project(id="project-0001", from_ruling="ruling-0001", steps=[]),
    ]
    assert feed_status.step_board_states(records, "project-0001") == []


def test_step_board_states_an_added_step_is_tagged_with_its_version():
    amended_steps = _PROJECT["steps"] + [{
        "id": "project-0001/s3", "tool": "stockpile.designate", "args": {},
        "targets": {"set": ["t1"]}, "requires": [_S2],
        "trigger": "all_success", "prefer_after": [], "guards": "default",
    }]
    records = _base_records() + [
        make_amend(
            id="amend-0001", project_id="project-0001", adds=["project-0001/s3"],
            replaces=[], drops=[], steps=amended_steps,
        ),
    ]
    states = {s["id"]: s for s in feed_status.step_board_states(records, "project-0001")}
    assert "added_version" not in states[_S1]
    assert "added_version" not in states[_S2]
    assert states["project-0001/s3"]["added_version"] == 2


def test_step_board_states_a_dropped_step_is_simply_absent():
    # The amend's own `steps` is the complete current plan -- s1 is not
    # redeclared, so it drops out of the job graph entirely, same as
    # `store._current_steps_and_version`'s own "never a diff" contract.
    records = _base_records() + [
        make_amend(
            id="amend-0001", project_id="project-0001", replaces=[_S1], adds=[], drops=[],
            steps=[_PROJECT["steps"][1]],
        ),
    ]
    states = {s["id"] for s in feed_status.step_board_states(records, "project-0001")}
    assert states == {_S2}


# ---- project_board_status ----------------------------------------------------


def test_project_board_status_active_then_done():
    fresh = feed_status.project_board_status(_base_records(), "project-0001")
    assert fresh == "active"

    done_records = _base_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9, step_id=_S1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
        make_executed(
            id="executed-0002", ruling_id="ruling-0001", cycle=12, step_id=_S2,
            actions=[{"tool": "construction.build", "outcome": "success"}],
        ),
    ]
    assert feed_status.project_board_status(done_records, "project-0001") == "done"


def test_project_board_status_hold_beats_active_when_any_step_is_held():
    records = _base_records() + [
        make_executed(
            id="executed-0001", ruling_id="ruling-0001", cycle=9, step_id=_S1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "blocked",
                "targets": ["ring-13-ore-1"], "target_state": "held",
            }],
        ),
    ]
    assert feed_status.project_board_status(records, "project-0001") == "hold"


def test_project_board_status_abandoned_overrides_everything_else():
    records = _base_records() + [make_abandon(project_id="project-0001")]
    assert feed_status.project_board_status(records, "project-0001") == "abandoned"


def test_project_board_status_unknown_project_is_none():
    assert feed_status.project_board_status(_base_records(), "project-9999") is None


# ---- hold codes and dfqueue/public_text.yaml ---------------------------------


def test_load_public_text_missing_file_is_empty_not_an_error(tmp_path):
    assert feed_status.load_public_text(tmp_path / "does-not-exist.yaml") == {}


def test_load_public_text_reads_a_flat_code_to_text_map(tmp_path):
    p = tmp_path / "public_text.yaml"
    p.write_text("no_worker: No dwarf is free for this job.\n", encoding="utf-8")
    assert feed_status.load_public_text(p) == {
        "no_worker": "No dwarf is free for this job.",
    }


def test_step_hold_text_with_no_observation_is_honestly_unknown():
    assert feed_status.step_hold_text(_base_records(), "project-0001", _S1, {}) == (None, None)


def test_step_hold_text_reads_the_latest_observations_hold_code():
    records = _base_records() + [
        make_observation(
            id="observation-0001", project_id="project-0001", step_id=_S1,
            results=[{"target": "ring-13-ore-1", "status": "not_observable",
                      "reason": "tile unreadable", "hold_code": "site_unreachable"}],
        ),
    ]
    public_text = {"site_unreachable": "The site cannot be reached right now."}
    text, code = feed_status.step_hold_text(records, "project-0001", _S1, public_text)
    assert code == "site_unreachable"
    assert text == "The site cannot be reached right now."


def test_step_hold_text_an_unmapped_code_still_names_the_code_not_a_guess():
    records = _base_records() + [
        make_observation(
            id="observation-0001", project_id="project-0001", step_id=_S1,
            results=[{"target": "ring-13-ore-1", "status": "not_observable",
                      "reason": "tile unreadable", "hold_code": "other"}],
        ),
    ]
    text, code = feed_status.step_hold_text(records, "project-0001", _S1, {})
    assert code == "other"
    assert text is None
