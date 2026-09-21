"""`dfqueue.grade.run_grading_cycle` and its CLI: `docs/AGENT-LOOP.md` item
2, "Grading on demand" -- the entry point a conductor service calls once
per cycle. Offline only (no VM, no DFHack process): the CLI is wired to a
"replay" JSON file of pre-captured tool responses, never a live call.
"""

from __future__ import annotations

import json

import pytest

from dfqueue import grade, store
from dfqueue.tests._helpers import make_executed, make_proposal, make_ruling
from learning.predictions.schema import GRADED_TRUE, PENDING

_OVERVIEW_JSON = {
    "tier1": {"population": 7},
    "tier2": {"in_game_date": "year 1, month 1, day 1, tick 500", "alerts": []},
}


def _call_tool(tool_id, arguments):
    if tool_id == "overview.get":
        return _OVERVIEW_JSON
    raise AssertionError(f"unexpected call: {tool_id} {arguments}")


# ---- run_grading_cycle() -----------------------------------------------------


def test_run_grading_cycle_reads_the_current_tick_from_overview(tmp_path):
    path = tmp_path / "queue.sqlite3"
    result = grade.run_grading_cycle(path, _call_tool, graded_at="2026-09-22T00:00:00+00:00")
    assert result["current_game_tick"] == grade.GAME_TICKS_PER_YEAR + 500
    assert result["graded"] == []
    assert result["unexecuted"] == []


def test_run_grading_cycle_grades_a_due_prediction_and_reports_unexecuted(tmp_path):
    path = tmp_path / "queue.sqlite3"
    tick = grade.game_tick_from_overview(_OVERVIEW_JSON)

    # A proposal armed to be due well before the current tick.
    due_soon = store.append(
        make_proposal(
            summary="Due-soon proposal, distinct text.",
            prediction={"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1},
        ),
        path, game_tick=0,
    )
    ruling = store.append(make_ruling(proposal_id=due_soon["id"]), path)
    store.append(make_executed(ruling_id=ruling["id"], cycle=0), path)

    # A second, accepted-but-never-executed proposal.
    unexecuted = store.append(
        make_proposal(summary="Unexecuted proposal, distinct text."), path, game_tick=0,
    )
    store.append(make_ruling(proposal_id=unexecuted["id"]), path)

    result = grade.run_grading_cycle(path, _call_tool, graded_at="2026-09-22T00:00:00+00:00")

    assert len(result["graded"]) == 1
    assert result["graded"][0]["status"] == GRADED_TRUE

    assert len(result["unexecuted"]) == 1
    assert result["unexecuted"][0]["proposal"]["id"] == unexecuted["id"]


def test_run_grading_cycle_is_idempotent(tmp_path):
    path = tmp_path / "queue.sqlite3"
    due_soon = store.append(
        make_proposal(
            prediction={"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1},
        ),
        path, game_tick=0,
    )
    ruling = store.append(make_ruling(proposal_id=due_soon["id"]), path)
    store.append(make_executed(ruling_id=ruling["id"], cycle=0), path)

    first = grade.run_grading_cycle(path, _call_tool, graded_at="2026-09-22T00:00:00+00:00")
    assert len(first["graded"]) == 1

    second = grade.run_grading_cycle(path, _call_tool, graded_at="2026-09-22T01:00:00+00:00")
    assert second["graded"] == []  # nothing left pending to grade
    assert second["unexecuted"] == first["unexecuted"] == []


def test_run_grading_cycle_defaults_graded_at_to_now(tmp_path):
    path = tmp_path / "queue.sqlite3"
    result = grade.run_grading_cycle(path, _call_tool)
    assert result["graded_at"]  # a real ISO string was stamped, not None


# ---- CLI -----------------------------------------------------------------------


def _write_replay(tmp_path, overview=_OVERVIEW_JSON):
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(
        json.dumps({"calls": [{"tool_id": "overview.get", "args": {}, "result": overview}]}),
        encoding="utf-8",
    )
    return replay_path


def test_cli_main_runs_a_grading_cycle_and_prints_json(tmp_path, capsys):
    path = tmp_path / "queue.sqlite3"
    due_soon = store.append(
        make_proposal(
            prediction={"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1},
        ),
        path, game_tick=0,
    )
    ruling = store.append(make_ruling(proposal_id=due_soon["id"]), path)
    store.append(make_executed(ruling_id=ruling["id"], cycle=0), path)

    replay_path = _write_replay(tmp_path)

    exit_code = grade.main([
        "--db", str(path), "--replay", str(replay_path),
        "--graded-at", "2026-09-22T00:00:00+00:00",
    ])
    assert exit_code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["graded_count"] == 1
    assert out["graded"][0]["status"] == GRADED_TRUE
    assert out["unexecuted_count"] == 0


def test_cli_main_reports_unexecuted_proposal_ids(tmp_path, capsys):
    path = tmp_path / "queue.sqlite3"
    unexecuted = store.append(make_proposal(), path, game_tick=0)
    store.append(make_ruling(proposal_id=unexecuted["id"]), path)

    replay_path = _write_replay(tmp_path)
    grade.main(["--db", str(path), "--replay", str(replay_path)])

    out = json.loads(capsys.readouterr().out)
    assert out["unexecuted_count"] == 1
    assert out["unexecuted_proposal_ids"] == [unexecuted["id"]]


def test_cli_replay_raises_a_clear_error_for_an_unmatched_call(tmp_path):
    call_tool = grade._call_tool_from_replay({"calls": []})
    with pytest.raises(KeyError, match="no replay entry"):
        call_tool("overview.get", {})
