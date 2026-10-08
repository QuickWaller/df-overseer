"""`parallel.proposers` (policy): the Architect, Quartermaster and Consultant
run concurrently, the Overseer (the one judge) strictly after them, starts
staggered, and every filing attributed to its recorded author. Fake runner
with real asyncio timing, no docker."""

from __future__ import annotations

import asyncio
import dataclasses
import time

import pytest

from conductor import lanes
from conductor.cycle import run_cycle
from conductor.runner import FakeRoleRunner, RunResult
from conductor.tests.test_cycle import (
    POLICY, _base_tools, _deps, _queue_overview, _wake_both_advisors,
)
from conductor.triage import OVERSEER

pytestmark = pytest.mark.asyncio

PAR = dataclasses.replace(POLICY, parallel_proposers=True, parallel_stagger_seconds=0.05)


class TimedRunner(FakeRoleRunner):
    """Sleeps per role, records start/end offsets and peak concurrency, and
    'files' a proposal per advisor into `filed` (id -> recorded author)."""

    def __init__(self, delays, filed):
        super().__init__()
        self.delays, self.filed = delays, filed
        self.t0 = time.monotonic()
        self.events = []
        self.running = 0
        self.peak = 0
        self.isolated_state = True
        self.overseer_overlap = False

    async def run(self, role, prompt, *, model, timeout_seconds, charter=None):
        self.calls.append({"role": role, "timeout_seconds": timeout_seconds, "model": model})
        self.running += 1
        self.peak = max(self.peak, self.running)
        if role == OVERSEER and self.running > 1:
            self.overseer_overlap = True
        self.events.append(("start", role, time.monotonic() - self.t0))
        await asyncio.sleep(self.delays.get(role, 0.0))
        if role in ("architect", "quartermaster"):
            self.filed[f"proposal-{role}"] = role
        self.events.append(("end", role, time.monotonic() - self.t0))
        self.running -= 1
        return RunResult(
            role=role, ok=True, status="ok", cost_usd=0.01, wall_clock_seconds=self.delays.get(role, 0.0),
            timed_out=False, tool_summary={}, final_answer="done", raw={},
        )


def _tools(filed):
    tools = _base_tools()
    _wake_both_advisors(tools)

    def overview(_args):
        ids = ["proposal-0001", *filed]
        return _queue_overview(proposals={
            "count": len(ids), "proposal_ids": ids,
            "by_role": {"proposal-0001": "planner", **filed},
        })

    tools["queue.overview"] = overview
    return tools


def _start(runner, role):
    return next(t for kind, r, t in runner.events if kind == "start" and r == role)


def _end(runner, role):
    return next(t for kind, r, t in runner.events if kind == "end" and r == role)


async def test_off_by_default_the_roles_run_one_at_a_time(tmp_path):
    assert POLICY.parallel_proposers is False
    filed = {}
    runner = TimedRunner({"architect": 0.1, "quartermaster": 0.1}, filed)
    result = await run_cycle(1, _deps(tmp_path, tools=_tools(filed), runner=runner))
    assert runner.peak == 1
    assert [r.role for r in result.role_runs] == ["architect", "quartermaster", OVERSEER]
    assert all(not g["concurrent"] for g in result.role_groups)


async def test_proposers_overlap_in_time_and_the_overseer_runs_alone_after_them(tmp_path):
    filed = {}
    runner = TimedRunner({"architect": 0.3, "quartermaster": 0.3, OVERSEER: 0.05}, filed)
    result = await run_cycle(1, _deps(tmp_path, tools=_tools(filed), runner=runner, policy=PAR))
    assert runner.peak == 2 and not runner.overseer_overlap
    # overlap: the Quartermaster starts before the Architect ends
    assert _start(runner, "quartermaster") < _end(runner, "architect")
    # the judge starts only after both proposers ended
    assert _start(runner, OVERSEER) >= max(_end(runner, "architect"), _end(runner, "quartermaster"))
    # staggered by the policy value
    assert _start(runner, "quartermaster") - _start(runner, "architect") >= 0.045
    # results are in roster order, one run per role, per-role timeout and model untouched
    assert [r.role for r in result.role_runs] == ["architect", "quartermaster", OVERSEER]
    by_role = {c["role"]: c for c in runner.calls}
    assert by_role[OVERSEER]["timeout_seconds"] == POLICY.role_timeout_seconds["overseer"]
    assert by_role["architect"]["timeout_seconds"] == by_role["quartermaster"]["timeout_seconds"]


async def test_cycle_wall_clock_is_reported_and_beats_the_serial_sum(tmp_path):
    filed = {}
    runner = TimedRunner({"architect": 0.3, "quartermaster": 0.3}, filed)
    result = await run_cycle(1, _deps(tmp_path, tools=_tools(filed), runner=runner, policy=PAR))
    group = next(g for g in result.role_groups if g["concurrent"])
    assert group["roles"] == ["architect", "quartermaster"]
    assert group["wall_seconds"] < 0.55           # concurrent, not 0.6
    assert set(group["run_seconds"]) == {"architect", "quartermaster"}
    assert result.wall_seconds is not None and result.wall_seconds >= group["wall_seconds"]
    assert (result.archived_path / "summary.json").read_text(encoding="utf-8").count("wall_seconds") >= 2


async def test_each_filing_goes_to_its_recorded_author_even_when_both_finish_together(tmp_path):
    filed = {}
    runner = TimedRunner({"architect": 0.05, "quartermaster": 0.2}, filed)
    deps = _deps(tmp_path, tools=_tools(filed), runner=runner, policy=PAR)
    await run_cycle(1, deps)
    state = lanes.LaneStore(tmp_path / "lane_state.json").load()
    # The old diff rule would give both new ids to whichever run was read first.
    assert state.proposers["proposal-architect"] == "architect"
    assert state.proposers["proposal-quartermaster"] == "quartermaster"


async def test_without_an_isolated_state_dir_it_falls_back_to_serial(tmp_path):
    filed = {}
    runner = TimedRunner({"architect": 0.1, "quartermaster": 0.1}, filed)
    runner.isolated_state = False
    await run_cycle(1, _deps(tmp_path, tools=_tools(filed), runner=runner, policy=PAR))
    assert runner.peak == 1


async def test_a_lone_proposer_just_runs_and_the_planner_is_never_grouped(tmp_path):
    filed = {}
    tools = _tools(filed)
    runner = TimedRunner({"architect": 0.01}, filed)
    result = await run_cycle(1, _deps(tmp_path, tools=tools, runner=runner, policy=PAR))
    assert runner.peak <= 2
    assert not any("planner" in g["roles"] and len(g["roles"]) > 1 for g in result.role_groups)
