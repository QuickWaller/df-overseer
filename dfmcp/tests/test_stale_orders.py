"""Item binding 3b (register 2026-10-09): the manager orders our own direct steps create carry a
handle that traces to their project, and `queue.cancel_stale_orders` cancels only those, only
once the project is done with them, never a started one, never one we did not make."""

from __future__ import annotations

import asyncio

import pytest

from dfmcp import conductor_tools, direct_actions, doctrine_tools, gotchas_tools, knowledge_tools
from dfmcp import executor_tools as et
from dfmcp import queue_tools, series_tools
from dfmcp.executor_run import ExecEnv
from dfmcp.registry import load_registry
from dfqueue import routing, store

pytestmark = pytest.mark.asyncio

TOOL = "orders.create"
ARGS = {"job": "ConstructBlocks", "amount": 8, "material": "INORGANIC", "dry_run": "false"}


@pytest.fixture(scope="module")
def registry():
    return load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS,
    })


class World:
    def __init__(self):
        self.calls = []
        self.next_id = 5
        self.orders = {}
        self.cancel_error = None
        self.omit_handle = False

    async def call_tool(self, tool, args, *, timeout=None):
        self.calls.append((tool, dict(args)))
        if tool == "orders.create":
            if args.get("dry_run") == "true":
                return {"dry_run": True, "would_queue": {}}
            oid, self.next_id = self.next_id, self.next_id + 1
            self.orders[oid] = {"id": oid, "active": False, "amount_left": 8, "amount_total": 8}
            out = {"dry_run": False, "create_ok": True, "order": {"id": oid}}
            if not self.omit_handle:
                out["order_handle"] = f"order-{oid}"
            return out
        if tool == "orders.list":
            return {"orders": list(self.orders.values()), "manager_appointed": True}
        if tool == "orders.cancel":
            if self.cancel_error:
                return {"error": self.cancel_error}
            self.orders.pop(int(args["id"]), None)
            return {"dry_run": False, "id": int(args["id"]), "erase_ok": True, "delete_ok": True}
        raise AssertionError(tool)

    async def dfhack(self, tool, args):
        if tool == "overview.get":
            return {"tier2": {"in_game_date": "year 0, month 1, day 1, tick 1000", "alerts": []}}
        if tool == "clock.status":
            return {"tripwire": None}
        raise AssertionError(tool)

    def cancels(self):
        return [c for c in self.calls if c[0] == "orders.cancel"]


@pytest.fixture
def rig(tmp_path, registry):
    w = World()
    env = ExecEnv(db_path=tmp_path / "q.sqlite3", write_lock=asyncio.Lock(), call_tool=w.call_tool,
                  call_dfhack=w.dfhack, registry=registry)
    return w, env


async def run_tool(env, w, tool_id, **args):
    return await et.call(tool_id, "conductor", args, db_path=env.db_path, write_lock=env.write_lock,
                         call_dfhack=w.dfhack, call_tool=w.call_tool, registry=env.registry)


async def make_order(env, w):
    """File, open and run one orders.create direct action; returns (project_id, run result)."""
    await direct_actions.file_action(env, store.sole_writer(), TOOL, dict(ARGS))
    _t, st = await run_tool(env, w, "queue.execution_state")
    _t, opened = await run_tool(env, w, "queue.open_project", ruling_id=st["to_open"][-1]["ruling_id"])
    _t, ran = await run_tool(env, w, "queue.run_step", project_id=opened["project_id"],
                             step_id=opened["step_ids"][0])
    return opened["project_id"], ran


async def close(env, w, pid, outcome, tick=1000):
    await run_tool(env, w, "queue.close", project_id=pid, outcome=outcome, reason="test")


async def cancel(env, w, **kw):
    _t, out = await run_tool(env, w, "queue.cancel_stale_orders", **kw)
    return out


def test_the_data_names_the_ref_and_its_cancel():
    ref = routing.created_refs()[TOOL]
    assert ref["prefix"] == "order-" and ref["cancel_tool"] == "orders.cancel" and ref["handle_path"] == "order_handle"


async def test_the_create_step_records_the_order_handle_against_its_project(rig):
    w, env = rig
    pid, ran = await make_order(env, w)
    assert ran["class"] == "success" and ran["handle"] == "order-5"
    assert store.issued_handles(env.db_path, pid) == ["order-5"]


async def test_an_order_the_game_skipped_has_no_handle_and_is_still_a_success(rig):
    w, env = rig
    w.omit_handle = True
    pid, ran = await make_order(env, w)
    assert ran["class"] == "success" and store.issued_handles(env.db_path, pid) == []


async def test_an_open_project_s_order_is_never_cancelled(rig):
    w, env = rig
    await make_order(env, w)
    out = await cancel(env, w, outcomes=["abandoned", "superseded", "completed"], tick=99999)
    assert out["cancelled"] == [] and w.cancels() == []


@pytest.mark.parametrize("outcome", ["abandoned", "superseded"])
async def test_an_abandoned_or_superseded_projects_unstarted_order_is_cancelled_and_logged(rig, outcome):
    w, env = rig
    pid, _ = await make_order(env, w)
    await close(env, w, pid, outcome)
    out = await cancel(env, w, outcomes=["abandoned", "superseded"])
    [row] = out["cancelled"]
    assert row["project_id"] == pid and row["handle"] == "order-5" and row["proposal_id"] and row["outcome"] == outcome
    assert w.cancels() == [("orders.cancel", {"id": "5", "dry_run": "false"})]
    assert 5 not in w.orders
    # logged against the project, and not done twice
    marker = [r for r in store.step_runs(env.db_path, pid) if r["step_id"] == "cleanup:order-5"]
    assert len(marker) == 1 and marker[0]["outcome"] == "success"
    again = await cancel(env, w, outcomes=["abandoned", "superseded"])
    assert again == {"cancelled": [], "left": [], "failed": []} and len(w.cancels()) == 1


async def test_a_started_order_is_left_alone_for_good(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    w.orders[5]["amount_left"] = 5  # the game has made some
    await close(env, w, pid, "abandoned")
    out = await cancel(env, w, outcomes=["abandoned"])
    assert out["cancelled"] == [] and "started" in out["left"][0]["why"] and w.cancels() == []
    await cancel(env, w, outcomes=["abandoned"])
    assert w.cancels() == []


async def test_an_active_order_is_left_alone(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    w.orders[5]["active"] = True
    await close(env, w, pid, "abandoned")
    out = await cancel(env, w, outcomes=["abandoned"])
    assert out["cancelled"] == [] and w.cancels() == []


async def test_a_foreign_order_is_never_touched(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    w.orders[9] = {"id": 9, "active": False, "amount_left": 3, "amount_total": 3}  # not ours
    await close(env, w, pid, "abandoned")
    await cancel(env, w, outcomes=["abandoned"])
    assert [int(c[1]["id"]) for c in w.cancels()] == [5] and 9 in w.orders


async def test_an_order_that_is_already_gone_is_settled_without_a_cancel(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    w.orders.clear()
    await close(env, w, pid, "abandoned")
    out = await cancel(env, w, outcomes=["abandoned"])
    assert out["left"][0]["why"] == "already gone" and w.cancels() == []


async def test_a_completed_project_waits_the_grace_and_needs_a_known_tick(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    await close(env, w, pid, "completed")
    closed_at = next(r["cycle"] for r in store.load(env.db_path) if r.get("kind") == "close")
    kw = dict(outcomes=["abandoned", "completed"], completed_grace_ticks=600)
    assert (await cancel(env, w, **kw))["cancelled"] == []  # no tick: skipped
    assert (await cancel(env, w, tick=closed_at + 599, **kw))["cancelled"] == []
    assert len((await cancel(env, w, tick=closed_at + 600, **kw))["cancelled"]) == 1


async def test_an_outcome_not_listed_is_not_cancelled(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    await close(env, w, pid, "not_done")
    assert (await cancel(env, w, outcomes=["abandoned", "superseded"]))["cancelled"] == []


async def test_a_refused_cancel_is_reported_and_retried_next_time(rig):
    w, env = rig
    pid, _ = await make_order(env, w)
    await close(env, w, pid, "abandoned")
    w.cancel_error = "the game is busy"
    out = await cancel(env, w, outcomes=["abandoned"])
    assert out["cancelled"] == [] and "busy" in out["failed"][0]["detail"] and 5 in w.orders
    w.cancel_error = None
    assert len((await cancel(env, w, outcomes=["abandoned"]))["cancelled"]) == 1


async def test_the_per_call_cap_is_honoured(rig):
    w, env = rig
    for _ in range(3):
        pid, _ = await make_order(env, w)
        await close(env, w, pid, "abandoned")
    assert len((await cancel(env, w, outcomes=["abandoned"], max=2))["cancelled"]) == 2
    assert len((await cancel(env, w, outcomes=["abandoned"], max=2))["cancelled"]) == 1


async def test_only_the_conductor_may_call_it(rig):
    w, env = rig
    from dfmcp.queue_tools import QueueToolError
    with pytest.raises(QueueToolError):
        await et.call("queue.cancel_stale_orders", "overseer", {}, db_path=env.db_path,
                      write_lock=env.write_lock, call_dfhack=w.dfhack, call_tool=w.call_tool, registry=env.registry)
