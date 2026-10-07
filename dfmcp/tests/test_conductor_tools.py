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


async def test_end_carries_thinking_capped(db):
    await _call({"phase": "start", "role": "architect"}, db)
    await _call({"phase": "end", "run_id": "run-0001", "status": "ok", "ok": True,
                 "thinking": "Weighing the farm level.\n\nStone is one level down."}, db)
    row = runs.get_run(runs.runs_path(db), "run-0001")
    assert row["thinking"] == "Weighing the farm level.\n\nStone is one level down."
    await _call({"phase": "start", "role": "overseer"}, db)
    await _call({"phase": "end", "run_id": "run-0002", "thinking": "y" * 20000}, db)
    t = runs.get_run(runs.runs_path(db), "run-0002")["thinking"]
    assert len(t) == runs.THINKING_MAX and t.endswith("[truncated]")


async def test_a_store_made_before_thinking_gains_the_column(db):
    path = runs.runs_path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(runs._SCHEMA.replace(",\n    thinking TEXT", ""))
    conn.close()
    assert "thinking" not in {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(runs)")}
    await _call({"phase": "start", "role": "architect"}, db)
    await _call({"phase": "end", "run_id": "run-0001", "thinking": "Short thought."}, db)
    assert runs.get_run(path, "run-0001")["thinking"] == "Short thought."


async def test_end_carries_transcript_whole_and_drops_an_oversize_one(db):
    await _call({"phase": "start", "role": "architect"}, db)
    body = '{"rounds":[{"n":1}],"omitted_rounds":0}'
    await _call({"phase": "end", "run_id": "run-0001", "status": "ok", "ok": True, "transcript": body}, db)
    assert runs.get_run(runs.runs_path(db), "run-0001")["transcript"] == body
    await _call({"phase": "start", "role": "overseer"}, db)
    await _call({"phase": "end", "run_id": "run-0002", "transcript": "y" * (runs.TRANSCRIPT_MAX + 1)}, db)
    assert runs.get_run(runs.runs_path(db), "run-0002")["transcript"] is None


async def test_a_store_made_before_transcripts_gains_the_column(db):
    path = runs.runs_path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(runs._SCHEMA.replace(",\n    transcript TEXT", ""))
    conn.close()
    assert "transcript" not in {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(runs)")}
    await _call({"phase": "start", "role": "architect"}, db)
    await _call({"phase": "end", "run_id": "run-0001", "transcript": "{}"}, db)
    assert runs.get_run(path, "run-0001")["transcript"] == "{}"


# ---- pause.verdict / pause.verdict_read (handoffs/2026-10-05-safe-to-resume.md) ----


def _vcall(tool, args, db, role):
    return ct.call(tool, role, args, queue_db_path=db, write_lock=asyncio.Lock())


async def test_pause_verdict_is_the_overseers_alone(db):
    for role in ("architect", "quartermaster", "consultant", "conductor"):
        with pytest.raises(ct.ConductorToolError, match="only the Overseer"):
            await _vcall(ct.PAUSE_VERDICT, {"resume": True, "reason": "x"}, db, role)
    assert not ct.pause_verdict_path(db).exists()


async def test_pause_verdict_read_is_the_conductors_alone(db):
    for role in ("architect", "overseer", "quartermaster", "consultant"):
        with pytest.raises(ct.ConductorToolError, match="only the conductor"):
            await _vcall(ct.PAUSE_VERDICT_READ, {}, db, role)


async def test_pause_verdict_roundtrip_and_since_id(db):
    _, empty = await _vcall(ct.PAUSE_VERDICT_READ, {}, db, "conductor")
    assert empty == {"latest_id": 0, "verdicts": []}
    _, v1 = await _vcall(ct.PAUSE_VERDICT, {"resume": False, "reason": "  a   siege\nmay form "}, db, "overseer")
    assert v1["id"] == 1 and v1["resume"] is False and v1["reason"] == "a siege may form"
    _, v2 = await _vcall(ct.PAUSE_VERDICT, {"resume": True, "reason": "harmless"}, db, "overseer")
    _, out = await _vcall(ct.PAUSE_VERDICT_READ, {"since_id": 1}, db, "conductor")
    assert out["latest_id"] == 2 and [r["id"] for r in out["verdicts"]] == [2] and out["verdicts"][0]["resume"] is True


@pytest.mark.parametrize("args", [
    {"resume": "yes", "reason": "x"}, {"resume": True}, {"resume": True, "reason": "  "},
    {"resume": True, "reason": "x", "extra": 1},
])
async def test_pause_verdict_bad_arguments_write_nothing(db, args):
    with pytest.raises(ct.ConductorToolError):
        await _vcall(ct.PAUSE_VERDICT, args, db, "overseer")
    assert not ct.pause_verdict_path(db).exists()


def test_pause_verdict_allowlists_and_the_overseer_still_has_no_resume():
    reg = load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **ct.NATIVE_TOOLS,
    })
    roster = load_roster(reg)
    assert roster.check("overseer", "pause.verdict")[0] is True
    assert roster.check("conductor", "pause.verdict")[0] is False
    assert roster.check("conductor", "pause.verdict_read")[0] is True
    for role in ("architect", "overseer", "quartermaster", "consultant"):
        assert roster.check(role, "pause.verdict_read")[0] is False
    for role in ("architect", "quartermaster", "consultant"):
        assert roster.check(role, "pause.verdict")[0] is False
    assert roster.check("overseer", "clock.resume")[0] is False


async def test_every_wake_reason_is_stored_ordered_and_deduplicated(db):
    await _call({"phase": "start", "role": "architect", "wake_reason": "stuck_job",
                 "wake_reasons": ["stuck_job", "season_change", "stuck_job", "open_ask"]}, db)
    row = runs.get_run(runs.runs_path(db), "run-0001")
    assert row["wake_reason"] == "stuck_job"
    assert json.loads(row["wake_reasons"]) == ["stuck_job", "season_change", "open_ask"]
    assert runs.decode_wake_reasons(row) == ["stuck_job", "season_change", "open_ask"]


async def test_end_without_a_start_still_records_the_reasons(db):
    await _call({"phase": "end", "role": "consultant", "wake_reason": "open_ask",
                 "wake_reasons": ["open_ask", "routine_review"], "duration_s": 5, "status": "ok"}, db)
    row = runs.get_run(runs.runs_path(db), "run-0001")
    assert runs.decode_wake_reasons(row) == ["open_ask", "routine_review"]


async def test_a_lone_wake_reason_leads_the_list_and_bad_lists_are_refused(db):
    await _call({"phase": "start", "role": "overseer", "wake_reason": "queue_pending"}, db)
    assert runs.decode_wake_reasons(runs.get_run(runs.runs_path(db), "run-0001")) == ["queue_pending"]
    with pytest.raises(ct.ConductorToolError):
        await _call({"phase": "start", "role": "overseer", "wake_reasons": "queue_pending"}, db)
    with pytest.raises(ct.ConductorToolError):
        await _call({"phase": "start", "role": "overseer", "wake_reasons": [1]}, db)


def test_an_old_store_is_migrated_and_old_rows_fall_back_to_the_one_reason(tmp_path):
    p = tmp_path / "old.runs.sqlite3"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, role TEXT NOT NULL, wake_reason TEXT, "
                 "wake_detail TEXT, cycle INTEGER, started_at TEXT NOT NULL, ended_at TEXT, status TEXT, "
                 "ok INTEGER, timed_out INTEGER, duration_s REAL, cost_usd REAL, error TEXT, "
                 "final_answer TEXT, records_json TEXT)")
    conn.execute("INSERT INTO runs (run_id, role, wake_reason, started_at) VALUES "
                 "('run-0001', 'architect', 'routine_review', '2026-10-01T00:00:00+00:00')")
    conn.commit()
    conn.close()
    runs.start_run(p, role="overseer", wake_reason="a", wake_detail=None, cycle=1, wake_reasons=["a", "b"])
    old, new = runs.get_run(p, "run-0001"), runs.get_run(p, "run-0002")
    assert runs.decode_wake_reasons(old) == ["routine_review"]
    assert runs.decode_wake_reasons(new) == ["a", "b"]
