"""A direct action in the conductor's execute phase: the operator hold blocks it, it runs
after the Overseer's run in the same cycle, and a failure is reported to the Overseer."""

from __future__ import annotations

import pytest

from conductor.cycle import run_cycle
from conductor.execute import ExecuteState, run_execute
from conductor.hold import HoldStore, hold_path_for
from conductor.policy import ExecutionPolicy
from conductor.tests.test_cycle import _base_tools, _deps

pytestmark = pytest.mark.asyncio

STATE = {
    "open_projects": [{"project_id": "project-0001", "role": "overseer", "direct": True,
                       "steps_open": 1, "phases_remaining": 0}],
    "ready_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1", "urgency": "normal",
                     "tool": "trees.fell", "args": {}}],
}


def _tools(**extra):
    tools = _base_tools()
    tools["queue.execution_state"] = STATE
    tools["queue.run_step"] = {"class": "success"}
    tools.update(extra)
    return tools


def _names(deps):
    return [c[0] for c in deps.tool_caller.calls]


async def test_the_hold_blocks_a_direct_action(tmp_path):
    deps = _deps(tmp_path, tools=_tools())
    HoldStore(hold_path_for(deps.cursor_store.path)).set("keep paused", who="test")
    result = await run_cycle(1, deps)
    assert "queue.run_step" not in _names(deps)
    assert result.execute["skipped"] == "operator hold"


async def test_a_direct_action_runs_with_a_quicksave_first(tmp_path):
    deps = _deps(tmp_path, tools=_tools())
    result = await run_cycle(1, deps)
    names = _names(deps)
    assert result.execute["steps_run"] == 1
    assert names.index("fort.quicksave") < names.index("queue.run_step")


async def test_dry_run_cycle_makes_no_write(tmp_path):
    deps = _deps(tmp_path, tools=_tools(), dry_run=True)
    await run_cycle(1, deps)
    assert "queue.run_step" not in _names(deps) and "fort.quicksave" not in _names(deps)


async def test_a_failed_direct_action_wakes_the_overseer_and_closes_not_done():
    calls = []

    async def call(tool, args):
        calls.append((tool, dict(args)))
        if tool == "queue.execution_state":
            return STATE
        if tool == "queue.run_step":
            return {"class": "failed", "retryable": False, "detail": "the tree is gone"}
        if tool == "queue.close":
            return {"close_id": "close-1"}
        return {}

    report = await run_execute(call, ExecutionPolicy(), ExecuteState(), game_tick=100, fallback_roles=("overseer",))
    assert [w.role for w in report.wakes] == ["overseer"]
    assert "did not run" in report.wakes[0].text and "tree is gone" in report.wakes[0].text
    close = [c for c in calls if c[0] == "queue.close"]
    assert close and close[0][1]["outcome"] == "not_done"
