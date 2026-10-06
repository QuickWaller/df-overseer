"""The conductor wakes whoever an ask is addressed to
(handoffs/2026-10-07-ask-addressing.md). An ask with no `to` map in the
overview (the pre-addressing shape) is still the Consultant's.
"""
from __future__ import annotations

import json
import logging

import pytest

from conductor.cycle import run_cycle
from conductor.runner import FakeRoleRunner
from conductor.tests.test_cycle import _base_tools, _deps, _queue_overview
from conductor.triage import CONSULTANT, OVERSEER

pytestmark = pytest.mark.asyncio


def _asks(**to):
    ids = [i for v in to.values() for i in v]
    return {"count": len(ids), "ask_ids": ids, "to": to}


async def test_an_ask_to_another_role_wakes_that_role_not_the_consultant(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(asks=_asks(quartermaster=["ask-0001"]))
    runner = FakeRoleRunner()
    result = await run_cycle(1, _deps(tmp_path, tools=tools, runner=runner))

    assert "quartermaster" in result.roles_woken
    assert CONSULTANT not in result.roles_woken
    assert OVERSEER not in result.roles_woken
    call = next(c for c in runner.calls if c["role"] == "quartermaster")
    assert json.loads(call["prompt"])["queue"]["ids"]["items"] == ["ask-0001"]


async def test_each_addressee_is_woken_and_sees_only_its_own_asks(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(
        asks=_asks(consultant=["ask-0001"], quartermaster=["ask-0002"]),
    )
    runner = FakeRoleRunner()
    result = await run_cycle(1, _deps(tmp_path, tools=tools, runner=runner))

    assert {"quartermaster", CONSULTANT} <= set(result.roles_woken)
    seen = {
        c["role"]: json.loads(c["prompt"])["queue"]["ids"]["items"]
        for c in runner.calls if c["role"] in ("quartermaster", CONSULTANT)
    }
    assert seen == {"quartermaster": ["ask-0002"], CONSULTANT: ["ask-0001"]}


async def test_the_pre_addressing_overview_shape_is_still_the_consultants(tmp_path):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(asks={"count": 1, "ask_ids": ["ask-0001"]})
    result = await run_cycle(1, _deps(tmp_path, tools=tools))
    assert CONSULTANT in result.roles_woken


async def test_an_ask_to_a_role_the_conductor_does_not_run_wakes_nobody(tmp_path, caplog):
    tools = _base_tools()
    tools["queue.overview"] = _queue_overview(asks=_asks(logistics=["ask-0001"]))
    runner = FakeRoleRunner()
    with caplog.at_level(logging.WARNING):
        result = await run_cycle(1, _deps(tmp_path, tools=tools, runner=runner))

    assert "logistics" not in result.roles_woken
    assert CONSULTANT not in result.roles_woken
    assert not [c for c in runner.calls if c["role"] == "logistics"]
    assert "logistics" in caplog.text
