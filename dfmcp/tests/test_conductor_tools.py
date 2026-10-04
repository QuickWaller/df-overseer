"""`conductor.report` (dfmcp/conductor_tools.py) and its store (dfqueue/runs.py).

No MCP SDK import, so this runs under the ambient interpreter too.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time

import pytest

from dfmcp import conductor_tools as ct
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfmcp import queue_tools, doctrine_tools, series_tools, gotchas_tools, knowledge_tools
from dfqueue import runs, store

pytestmark = pytest.mark.asyncio


def _call(args, db, role="conductor"):
    return ct.call(ct.CONDUCTOR_REPORT, role, args, queue_db_path=db, write_lock=asyncio.Lock())


@pytest.fixture
def db(tmp_path):
    return tmp_path / "Fort.sqlite3"


async def test_only_the_conductor_may_report(db):
    for role in ("architect", "overseer", "quartermaster", "consultant"):
        with pytest.raises(ct.ConductorToolError, match="only the conductor"):
            await _call({"phase": "start", "role": "architect"}, db, role=role)
    assert not runs.runs_path(db).exists()


async def test_unknown_argument_is_refused_and_writes_nothing(db):
    with pytest.raises(ct.ConductorToolError, match="unexpected argument"):
        await _call({"phase": "start", "role": "architect", "ts": "x"}, db)
    assert not runs.runs_path(db).exists()


async def test_start_then_end_roundtrip(db):
    text, out = await _call(
        {"phase": "start", "role": "architect", "wake_reason": "routine_review",
         "wake_detail": "d", "cycle": 3}, db)
    assert out["run_id"] == "run-0001"
    _, end = await _call(
        {"phase": "end", "run_id": "run-0001", "status": "ok", "ok": True, "timed_out": False,
         "duration_s": 12.5, "cost_usd": 0.04, "error": None, "final_answer": "All quiet."}, db)
    assert end["records"] == 0
    row = runs.get_run(runs.runs_path(db), "run-0001")
    assert row["role"] == "architect" and row["wake_reason"] == "routine_review"
    assert row["cycle"] == 3 and row["ok"] == 1 and row["cost_usd"] == 0.04
    assert row["final_answer"] == "All quiet." and row["ended_at"] >= row["started_at"]


async def test_final_answer_is_capped(db):
    await _call({"phase": "start", "role": "overseer"}, db)
    await _call({"phase": "end", "run_id": "run-0001", "final_answer": "x" * 10000}, db)
    fa = runs.get_run(runs.runs_path(db), "run-0001")["final_answer"]
    assert len(fa) == runs.FINAL_ANSWER_MAX and fa.endswith("[truncated]")


async def test_end_without_start_creates_the_row_backdated(db):
    _, out = await _call(
        {"phase": "end", "role": "consultant", "wake_reason": "ask_open", "duration_s": 60,
         "ok": False, "timed_out": True, "error": "timeout"}, db)
    row = runs.get_run(runs.runs_path(db), out["run_id"])
    started = runs._parse(row["started_at"])
    ended = runs._parse(row["ended_at"])
    assert 59 <= (ended - started).total_seconds() <= 61
    assert row["timed_out"] == 1 and row["error"] == "timeout"


async def test_end_unknown_or_repeated_run_is_refused(db):
    with pytest.raises(ct.ConductorToolError, match="unknown run_id"):
        await _call({"phase": "end", "run_id": "run-0099"}, db)
    await _call({"phase": "start", "role": "architect"}, db)
    await _call({"phase": "end", "run_id": "run-0001"}, db)
    with pytest.raises(ct.ConductorToolError, match="already ended"):
        await _call({"phase": "end", "run_id": "run-0001"}, db)


async def test_bad_role_and_types_refused(db):
    with pytest.raises(ct.ConductorToolError):
        await _call({"phase": "start", "role": "conductor"}, db)
    with pytest.raises(ct.ConductorToolError, match="boolean"):
        await _call({"phase": "start", "role": "architect"}, db)
        await _call({"phase": "end", "run_id": "run-0001", "ok": "yes"}, db)


async def test_unwritable_store_is_a_refusal_not_a_crash(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(ct.ConductorToolError, match="unavailable"):
        await _call({"phase": "start", "role": "architect"}, blocker / "Fort.sqlite3")


def _rec(i, kind, role, ts, **extra):
    return {"id": i, "kind": kind, "role": role, "ts": ts, **extra}


def test_records_in_window_filters_by_role_and_time_and_resolves_threads():
    recs = [
        _rec("proposal-0001", "proposal", "architect", "2026-10-05T10:00:05+00:00"),
        _rec("proposal-0002", "proposal", "architect", "2026-10-05T09:00:00+00:00"),
        _rec("pass-0001", "pass", "quartermaster", "2026-10-05T10:00:06+00:00"),
        _rec("ruling-0001", "ruling", "overseer", "2026-10-05T10:00:07+00:00", proposal_id="proposal-0001"),
        _rec("executed-0001", "executed", "overseer", "2026-10-05T10:00:08+00:00", ruling_id="ruling-0001"),
        _rec("amend-0001", "amend", "overseer", "2026-10-05T10:00:09+00:00", project_id="project-0001"),
    ]
    a = runs.records_in_window(recs, "architect", "2026-10-05T10:00:00+00:00", "2026-10-05T10:01:00+00:00")
    assert a == [{"id": "proposal-0001", "kind": "proposal", "thread": "proposal-0001"}]
    o = runs.records_in_window(recs, "overseer", "2026-10-05T10:00:00+00:00", "2026-10-05T10:01:00+00:00")
    assert [(r["id"], r["thread"]) for r in o] == [
        ("ruling-0001", "proposal-0001"), ("executed-0001", "proposal-0001"),
        ("amend-0001", "project-0001"),
    ]


async def test_end_links_records_the_role_wrote_in_the_window(db):
    # Real queue records written between start and end by the right role.
    from dfqueue import schema
    await _call({"phase": "start", "role": "quartermaster", "wake_reason": "routine_review"}, db)
    now = runs._now().isoformat()
    with sqlite3.connect(db) as c:  # a minimal records table, as dfqueue.store lays it out
        c.executescript(store._SCHEMA_SQL)
        for rid, role in (("pass-0001", "quartermaster"), ("pass-0002", "architect")):
            c.execute(
                "INSERT INTO records (id, ts, kind, role, cycle, type, proposal_id, payload) "
                "VALUES (?, ?, 'pass', ?, 1, NULL, NULL, ?)",
                (rid, now, role, json.dumps({"id": rid, "kind": "pass", "role": role, "ts": now})),
            )
    time.sleep(0.01)
    _, out = await _call({"phase": "end", "run_id": "run-0001", "ok": True}, db)
    assert out["records"] == 1
    row = runs.get_run(runs.runs_path(db), "run-0001")
    assert json.loads(row["records_json"]) == [{"id": "pass-0001", "kind": "pass", "thread": "pass-0001"}]


async def test_read_only_reader_never_creates_and_sees_rows(db, tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        runs.read_runs_readonly(tmp_path / "missing.sqlite3")
    await _call({"phase": "start", "role": "architect"}, db)
    rows = runs.read_runs_readonly(runs.runs_path(db))
    assert [r["run_id"] for r in rows] == ["run-0001"]


async def test_old_rows_are_pruned(db, monkeypatch):
    monkeypatch.setattr(runs, "KEEP_ROWS", 3)
    for _ in range(5):
        _, o = await _call({"phase": "start", "role": "architect"}, db)
        await _call({"phase": "end", "run_id": o["run_id"]}, db)
    assert len(runs.read_runs_readonly(runs.runs_path(db))) == 3


def test_tool_is_registered_for_the_conductor_only():
    reg = load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **ct.NATIVE_TOOLS,
    })
    roster = load_roster(reg)
    assert roster.check("conductor", "conductor.report")[0] is True
    for role in ("architect", "overseer", "quartermaster", "consultant"):
        assert roster.check(role, "conductor.report")[0] is False
    desc, schema_ = reg.get("conductor.report").describe("conductor")
    assert schema_["additionalProperties"] is False and "role" in schema_["properties"]
