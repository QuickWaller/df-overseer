"""Direct actions (2026-10-09, "the conductor is the only game writer"): an Overseer
write-tool call is validated, previewed and recorded as a ready-ruled one-step project;
the conductor's execute phase is the only thing that runs it."""

from __future__ import annotations

import asyncio

import pytest

from dfmcp import conductor_tools, direct_actions, doctrine_tools, gotchas_tools, knowledge_tools
from dfmcp import executor_tools as et
from dfmcp import queue_tools, series_tools
from dfmcp.executor_run import ExecEnv
from dfmcp.queue_tools import QueueToolError
from dfmcp.registry import load_registry
from dfqueue import routing, store

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def registry():
    return load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS,
    })


class World:
    def __init__(self):
        self.calls = []
        self.refuse_dry = None

    async def call_tool(self, tool, args, *, timeout=None):
        self.calls.append((tool, dict(args)))
        if args.get("dry_run") == "true":
            if self.refuse_dry:
                return {"error": self.refuse_dry}
            return {"dry_run": True, "would": "clear"}
        return {"dry_run": False, "cleared": True}

    async def dfhack(self, tool, args):
        if tool == "overview.get":
            return {"tier2": {"in_game_date": "year 0, month 1, day 1, tick 1000", "alerts": []}}
        if tool == "clock.status":
            return {"tripwire": None}
        raise AssertionError(tool)

    def real(self):
        return [c for c in self.calls if c[1].get("dry_run") == "false"]


@pytest.fixture
def rig(tmp_path, registry):
    w = World()
    env = ExecEnv(db_path=tmp_path / "q.sqlite3", write_lock=asyncio.Lock(), call_tool=w.call_tool,
                  call_dfhack=w.dfhack, registry=registry)
    return w, env


TOOL = "zone.clear-owner"


def test_routing_marks_the_direct_tools_and_leaves_set_crop_alone():
    tools = routing.direct_tools()
    assert len(tools) == 15 and "farm.set-crop" not in tools
    assert routing.group_of_tool("farm.set-crop") == "orders"
    assert routing.is_routed("direct_action") and routing.is_direct("direct_action")
    assert routing.executed_groups() == ["direct"]
    assert routing.routed_tools() == []  # the Overseer keeps every tool on its allowlist


def test_preview_detection(registry):
    t = registry.get(TOOL)
    assert direct_actions.is_preview(t, {"zone_id": "1"})  # DRY_RUN defaults to true
    assert direct_actions.is_preview(t, {"zone_id": "1", "dry_run": "true"})
    assert not direct_actions.is_preview(t, {"zone_id": "1", "dry_run": "false"})
    assert not direct_actions.is_preview(registry.get("labor.set-labor"), {})


def test_only_the_sole_writer_is_recorded():
    assert direct_actions.is_direct_tool(TOOL, store.sole_writer())
    assert not direct_actions.is_direct_tool(TOOL, "architect")
    assert not direct_actions.is_direct_tool("overview.get", store.sole_writer())


async def file(env, **args):
    return await direct_actions.file_action(env, store.sole_writer(), TOOL, {"zone_id": "3", "dry_run": "false", **args})


async def test_a_call_is_recorded_not_written(rig):
    w, env = rig
    text, out = await file(env)
    assert "Queued" in text and out["queued"]
    assert w.real() == []  # dry-run preview only: the game is never written here
    assert [c[1]["dry_run"] for c in w.calls] == ["true"]
    assert len(store.openable_rulings(env.db_path)) == 1


async def test_a_refused_preview_records_nothing(rig):
    w, env = rig
    w.refuse_dry = "zone 3 has no owner"
    with pytest.raises(QueueToolError, match="no owner"):
        await file(env)
    assert w.real() == []
    assert not env.db_path.exists() or store.openable_rulings(env.db_path) == []


async def test_bad_arguments_are_refused_before_any_call(rig):
    w, env = rig
    with pytest.raises(QueueToolError):
        await direct_actions.file_action(env, store.sole_writer(), TOOL, {"nonsense": 1})
    assert w.calls == []


async def run_tool(env, w, tool_id, **args):
    return await et.call(tool_id, "conductor", args, db_path=env.db_path, write_lock=env.write_lock,
                         call_dfhack=w.dfhack, call_tool=w.call_tool, registry=env.registry)


async def open_it(env, w):
    await file(env)
    _t, st = await run_tool(env, w, "queue.execution_state")
    assert len(st["to_open"]) == 1
    _t, opened = await run_tool(env, w, "queue.open_project", ruling_id=st["to_open"][0]["ruling_id"])
    return opened


async def test_the_executor_runs_it_once_as_a_one_node_project(rig):
    w, env = rig
    opened = await open_it(env, w)
    _t, st = await run_tool(env, w, "queue.execution_state")
    assert st["open_projects"][0]["direct"] is True
    assert [r["step_id"] for r in st["ready_steps"]] == [opened["step_ids"][0]]
    _t, ran = await run_tool(env, w, "queue.run_step", project_id=opened["project_id"], step_id=opened["step_ids"][0])
    assert ran["class"] == "success"
    assert len(w.real()) == 1 and w.real()[0][0] == TOOL and w.real()[0][1]["zone_id"] == "3"


async def test_a_refusal_at_execution_fails_cleanly_and_changes_nothing(rig):
    w, env = rig
    opened = await open_it(env, w)
    w.refuse_dry = "the zone is gone"
    _t, ran = await run_tool(env, w, "queue.run_step", project_id=opened["project_id"], step_id=opened["step_ids"][0])
    assert ran["class"] == "needs_judgment" and w.real() == []
