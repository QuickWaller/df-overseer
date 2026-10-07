"""conductor/cycle.py's `conductor.report` brackets around each role run
(handoffs/2026-10-05-conductor-report.md)."""

from __future__ import annotations

import pytest

from conductor.cycle import run_cycle
from conductor.mcp_client import MCPToolError
from conductor.runner import FakeRoleRunner, RunResult
from conductor.tests.test_cycle import (
    _base_tools, _clock_status, _deps, _queue_overview,
)
from conductor.triage import CONSULTANT, OVERSEER

pytestmark = pytest.mark.asyncio


def _ask_tools(report):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(asks={"count": 1, "ask_ids": ["ask-0001"]})
    tools["conductor.report"] = report
    return tools


def _ok(role, **kw):
    base = dict(role=role, ok=True, status="ok", cost_usd=0.02, wall_clock_seconds=7.5,
                timed_out=False, tool_summary={}, final_answer="Answered ask-0001.", raw={})
    base.update(kw)
    return RunResult(**base)


async def test_start_and_end_bracket_the_run_and_carry_the_wake_reason(tmp_path):
    seen = []

    def report(args):
        seen.append(dict(args))
        return {"run_id": "run-0007"}

    runner = FakeRoleRunner({CONSULTANT: _ok(CONSULTANT)})
    deps = _deps(tmp_path, tools=_ask_tools(report), runner=runner)
    await run_cycle(4, deps)

    assert [a["phase"] for a in seen] == ["start", "end"]
    start, end = seen
    assert start["role"] == CONSULTANT and start["cycle"] == 4 and start["wake_reason"]
    assert end["run_id"] == "run-0007"
    assert end["ok"] is True and end["cost_usd"] == 0.02 and end["duration_s"] == 7.5
    assert end["final_answer"] == "Answered ask-0001." and end["timed_out"] is False
    assert "role" not in end  # run_id is enough when start succeeded


async def test_a_failed_start_makes_the_end_call_self_contained(tmp_path):
    seen = []

    def report(args):
        seen.append(dict(args))
        if args["phase"] == "start":
            raise MCPToolError("conductor.report: dfmcp is unreachable")
        return {"run_id": "run-0001"}

    runner = FakeRoleRunner({CONSULTANT: _ok(CONSULTANT)})
    deps = _deps(tmp_path, tools=_ask_tools(report), runner=runner)
    result = await run_cycle(1, deps)

    assert len(result.role_runs) == 1 and result.role_runs[0].ok
    end = seen[-1]
    assert "run_id" not in end
    assert end["role"] == CONSULTANT and end["wake_reason"] and end["cycle"] == 1


async def test_a_report_failure_never_breaks_the_cycle_and_is_logged(tmp_path, caplog):
    def report(args):
        raise MCPToolError("refused")

    runner = FakeRoleRunner({CONSULTANT: _ok(CONSULTANT)})
    deps = _deps(tmp_path, tools=_ask_tools(report), runner=runner)
    with caplog.at_level("WARNING"):
        result = await run_cycle(1, deps)
    assert result.roles_woken and result.role_runs[0].ok
    assert any("conductor.report" in r.message for r in caplog.records)


async def test_a_tool_not_deployed_yet_is_the_same_as_a_failure(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(asks={"count": 1, "ask_ids": ["ask-0001"]})
    runner = FakeRoleRunner({CONSULTANT: _ok(CONSULTANT)})
    deps = _deps(tmp_path, tools=tools, runner=runner)  # no conductor.report configured
    result = await run_cycle(1, deps)
    assert result.role_runs[0].ok


async def test_the_tripwire_overseer_run_is_reported_too(tmp_path):
    seen = []
    tools = _base_tools()
    tools["clock.status"] = _clock_status(
        paused=True, tripwire={"reason": "hunger_critical", "tick": 999, "detail": "Urist is starving"},
    )
    tools["conductor.report"] = lambda a: (seen.append(dict(a)) or {"run_id": "run-0002"})
    runner = FakeRoleRunner({OVERSEER: _ok(OVERSEER, final_answer="Handled.")})
    deps = _deps(tmp_path, tools=tools, runner=runner)
    await run_cycle(2, deps)
    # hunger wakes the Quartermaster first, then the Overseer: both are reported
    overseer_rows = [r for r in seen if r.get("role") == OVERSEER]
    assert overseer_rows[0]["wake_reason"] == "tripwire"
    assert "hunger_critical" in overseer_rows[0]["wake_detail"]
    assert any(r.get("final_answer") == "Handled." for r in seen)


async def test_a_dry_run_reports_nothing(tmp_path):
    seen = []
    tools = _ask_tools(lambda a: (seen.append(a) or {}))
    deps = _deps(tmp_path, tools=tools, dry_run=True)
    await run_cycle(1, deps)
    assert seen == []


async def test_the_transcript_goes_out_as_compact_json_and_is_archived(tmp_path):
    import json
    seen = []
    transcript = {"rounds": [{"n": 1, "text": "hi", "calls": [], "reasoning": None, "usage": {"input": 5}}], "omitted_rounds": 0}
    runner = FakeRoleRunner({CONSULTANT: _ok(CONSULTANT, transcript=transcript)})
    deps = _deps(tmp_path, tools=_ask_tools(lambda a: (seen.append(dict(a)) or {"run_id": "run-0001"})), runner=runner)
    await run_cycle(1, deps)
    end = seen[-1]
    assert json.loads(end["transcript"]) == transcript and " " not in end["transcript"].replace("hi", "")
    plain = [dict(a) for a in seen]
    runner2 = FakeRoleRunner({CONSULTANT: _ok(CONSULTANT)})
    seen2 = []
    await run_cycle(2, _deps(tmp_path, tools=_ask_tools(lambda a: (seen2.append(dict(a)) or {"run_id": "run-0002"})), runner=runner2))
    assert "transcript" not in seen2[-1] and plain
