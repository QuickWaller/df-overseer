"""The execute phase wired into the cycle (stage 2D): when it runs, when it
does not, what it owes the proposer, and that it never resumes the fort."""

from __future__ import annotations

import json

import pytest

from conductor.cycle import run_cycle
from conductor.execute import ExecuteStore
from conductor.hold import HoldStore, hold_path_for
from conductor.runner import FakeRoleRunner
from conductor.tests.test_cycle import (
    _base_tools, _clock_status, _deps, _run_that_called,
)
from conductor.triage import OVERSEER

pytestmark = pytest.mark.asyncio

ARCHITECT = "architect"

READY = {"open_projects": [{"project_id": "project-0001", "role": "architect", "steps_open": 1, "phases_remaining": 1}],
         "ready_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1", "urgency": "normal"}]}


def _tools(state=None, **extra):
    tools = _base_tools()
    tools["queue.execution_state"] = state if state is not None else READY
    tools["queue.run_step"] = {"class": "success", "handle": "site-1"}
    tools.update(extra)
    return tools


def _names(deps):
    return [c[0] for c in deps.tool_caller.calls]


async def test_an_ordinary_cycle_runs_the_ready_step_after_a_quicksave(tmp_path):
    deps = _deps(tmp_path, tools=_tools())
    result = await run_cycle(1, deps)
    names = _names(deps)
    assert "queue.run_step" in names
    assert names.index("fort.quicksave") < names.index("queue.run_step")
    assert result.execute["steps_run"] == 1
    assert not [n for n in names if n in ("clock.resume", "clock.clear")]


async def test_the_phase_runs_after_the_overseer(tmp_path):
    tools = _tools()
    tools["queue.overview"] = {"proposals": {"count": 1, "proposal_ids": ["proposal-0001"]}, "asks": {"count": 0, "ask_ids": []}}
    runner = FakeRoleRunner()
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)
    assert OVERSEER in result.roles_woken
    assert any(c["role"] == OVERSEER for c in runner.calls)
    assert _names(deps).index("queue.run_step") > _names(deps).index("queue.grade")


async def test_a_dry_run_makes_no_execute_call(tmp_path):
    deps = _deps(tmp_path, tools=_tools(), dry_run=True)
    await run_cycle(1, deps)
    # queue.execution_state is a read the plan watch also makes; run_step is the execute call
    assert "queue.run_step" not in _names(deps)


async def test_an_operator_hold_skips_the_phase(tmp_path):
    deps = _deps(tmp_path, tools=_tools())
    HoldStore(hold_path_for(deps.cursor_store.path)).set("keep paused", who="test")
    result = await run_cycle(1, deps)
    assert "queue.run_step" not in _names(deps)
    assert result.execute == {"ran": False, "skipped": "operator hold", "steps_run": 0, "actions": [], "wakes": [], "errors": []}


async def test_a_hold_with_allow_execution_runs_steps_but_never_resumes(tmp_path):
    tools = _tools()
    tools["clock.status"] = _clock_status(paused=True)
    deps = _deps(tmp_path, tools=tools)
    HoldStore(hold_path_for(deps.cursor_store.path)).set("keep paused", who="test", allow_execution=True)
    result = await run_cycle(1, deps)
    names = _names(deps)
    assert "queue.run_step" in names
    assert not [n for n in names if n in ("clock.resume", "clock.clear")]
    assert result.hold["allow_execution"] is True


async def test_an_escalation_this_cycle_skips_the_phase(tmp_path):
    tools = _tools()
    tools["queue.overview"] = {"proposals": {"count": 1, "proposal_ids": ["proposal-0001"]}, "asks": {"count": 0, "ask_ids": []}}
    runner = FakeRoleRunner({OVERSEER: _run_that_called("queue.escalate")})
    deps = _deps(tmp_path, tools=tools, runner=runner)
    result = await run_cycle(1, deps)
    assert result.escalated is True
    assert "queue.run_step" not in _names(deps)
    assert result.execute["skipped"] == "an escalation this cycle"


async def test_an_unreadable_execution_state_does_not_stop_the_cycle(tmp_path):
    tools = _base_tools()  # no queue.execution_state: the fake raises, as an undeployed dfmcp would
    deps = _deps(tmp_path, tools=tools)
    result = await run_cycle(1, deps)
    assert result.execute["ran"] is False


async def test_a_done_step_owes_the_proposer_a_wake_that_fires_next_cycle(tmp_path):
    state = {"open_projects": [{"project_id": "project-0001", "role": "architect", "steps_open": 1, "phases_remaining": 1}],
             "issued_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1"}]}
    tools = _tools(state, **{"queue.observe": {"state": "done", "observation_id": "observation-0001", "detail": "ok", "recorded": True}})
    deps = _deps(tmp_path, tools=tools)
    first = await run_cycle(1, deps)
    assert any(w["reason"] == "step_done" for w in first.execute["wakes"])
    lane = json.loads((tmp_path / "lane_state.json").read_text(encoding="utf-8"))
    assert any(k.startswith("step_done:") for k in lane["pending"][ARCHITECT])

    runner = FakeRoleRunner()
    second = await run_cycle(2, _deps_again(tmp_path, tools, runner))
    assert ARCHITECT in second.roles_woken
    prompt = next(c for c in runner.calls if c["role"] == ARCHITECT)["prompt"]
    assert "project-0001/s1 is done" in prompt


def _deps_again(tmp_path, tools, runner):
    return _deps(tmp_path, tools=tools, runner=runner)


async def test_the_execute_state_is_saved_and_a_done_step_is_not_announced_twice(tmp_path):
    state = {"open_projects": [{"project_id": "project-0001", "role": "architect", "steps_open": 1, "phases_remaining": 0}],
             "issued_steps": [{"project_id": "project-0001", "step_id": "project-0001/s1"}]}
    tools = _tools(state, **{"queue.observe": {"state": "done", "observation_id": "observation-0001", "detail": "ok"}})
    await run_cycle(1, _deps(tmp_path, tools=tools))
    saved = ExecuteStore(tmp_path / "execute_state.json").load()
    assert saved.sent == ["project-0001/s1"]
    again = await run_cycle(2, _deps(tmp_path, tools=tools))
    assert not [w for w in again.execute["wakes"] if w["reason"] == "step_done"]


# ---- under a tripwire latch ------------------------------------------------


def _latched_tools(state):
    tools = _tools(state)
    tools["clock.status"] = _clock_status(paused=True, tripwire={"reason": "thirst_critical", "tick": 999, "detail": "x"})
    return tools


async def test_a_latch_runs_only_high_urgency_steps_and_never_resumes(tmp_path):
    state = {"open_projects": [{"project_id": "project-0001", "role": "architect", "steps_open": 2, "phases_remaining": 0}],
             "ready_steps": [
                 {"project_id": "project-0001", "step_id": "project-0001/s1", "urgency": "normal"},
                 {"project_id": "project-0001", "step_id": "project-0001/s2", "urgency": "high"}]}
    deps = _deps(tmp_path, tools=_latched_tools(state))
    result = await run_cycle(1, deps)
    ran = [a["step_id"] for t, a in deps.tool_caller.calls if t == "queue.run_step"]
    assert ran == ["project-0001/s2"]
    assert result.execute["steps_run"] == 1
    assert not [n for n in _names(deps) if n == "clock.resume"]


async def test_a_latch_with_an_escalating_overseer_runs_no_step(tmp_path):
    runner = FakeRoleRunner({OVERSEER: _run_that_called("queue.escalate")})
    deps = _deps(tmp_path, tools=_latched_tools(READY), runner=runner)
    result = await run_cycle(1, deps)
    assert result.escalated is True and "queue.run_step" not in _names(deps)
    assert result.execute is None


async def test_a_latch_under_a_plain_hold_runs_no_step(tmp_path):
    deps = _deps(tmp_path, tools=_latched_tools(READY))
    HoldStore(hold_path_for(deps.cursor_store.path)).set("keep paused", who="test")
    await run_cycle(1, deps)
    assert "queue.run_step" not in _names(deps)


# ---- routing lines in briefings ----------------------------------------------


async def test_routing_from_the_server_shapes_the_ruling_ask_and_freezes_the_architect(tmp_path):
    state = {**READY, "routing": {"routed_types": ["work_order"], "unrouted_types": ["room_siting"],
                                   "frozen_types": ["room_siting"]}}
    tools = _tools(state)
    tools["queue.overview"] = {"proposals": {"count": 1, "proposal_ids": ["proposal-0001"]}, "asks": {"count": 0, "ask_ids": []}}
    tools["diff.since"] = __import__("conductor.tests.test_cycle", fromlist=["x"])._diff_sequence(
        [[{"id": 1, "type": "JOB_COMPLETED", "detail": "Dig"}], []])
    runner = FakeRoleRunner()
    await run_cycle(1, _deps(tmp_path, tools=tools, runner=runner))
    overseer = next(c for c in runner.calls if c["role"] == OVERSEER)["prompt"]
    assert "work_order are carried out by the conductor" in overseer
    architect = json.loads(next(c for c in runner.calls if c["role"] == ARCHITECT)["prompt"])
    assert architect["frozen"]["types"] == ["room_siting"]


async def test_a_server_that_reports_no_routing_leaves_the_briefings_as_they_were(tmp_path):
    runner = FakeRoleRunner()
    tools = _tools()
    tools["queue.overview"] = {"proposals": {"count": 1, "proposal_ids": ["proposal-0001"]}, "asks": {"count": 0, "ask_ids": []}}
    await run_cycle(1, _deps(tmp_path, tools=tools, runner=runner))
    overseer = next(c for c in runner.calls if c["role"] == OVERSEER)["prompt"]
    assert "ACCEPTED ROUTED WORK" not in overseer and "carry out each proposal you accept" in overseer
