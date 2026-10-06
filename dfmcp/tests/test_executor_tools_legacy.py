"""Deploy-2a executor tools: `queue.close_legacy`, `queue.cutover`,
`queue.execution_state` (dfmcp/executor_tools.py), plus the two load rules in
dfmcp/roles.py (executor-only tools, routed tools on no allowlist).

No DFHack: these tools never call it, and the tests prove that by passing a
`call_dfhack` that fails the test if used.
"""

from __future__ import annotations

import asyncio

import pytest
import yaml

from dfmcp import executor_tools as et
from dfmcp import queue_tools
from dfmcp.registry import load_registry
from dfmcp.roles import RoleValidationError, load_roster
from dfqueue import routing, store
from dfqueue.tests._helpers import make_executed, make_project, make_proposal, make_ruling


REAL_YAML = routing.ACTION_TOOLS_PATH


async def _no_dfhack(*a, **k):
    raise AssertionError("an executor close/cutover tool must never call DFHack")


def _call(tool, args, db, role="conductor"):
    return et.call(tool, role, args, db_path=db, write_lock=asyncio.Lock(), call_dfhack=_no_dfhack)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "q.sqlite3"


def set_routing(monkeypatch, tmp_path, **flags):
    data = yaml.safe_load(REAL_YAML.read_text(encoding="utf-8"))
    data["groups"]["rooms"].update(flags)
    p = tmp_path / "action_tools.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(routing, "ACTION_TOOLS_PATH", p)


def accepted(path, n, ptype="room_siting", executed=False):
    role = "quartermaster" if ptype == "work_order" else "architect"
    p = store.append(make_proposal(
        role=role, type=ptype, summary=f"Idea number {n} " + "q" * n, rationale=f"Because reason {n} " + "w" * n),
        path, game_tick=10)
    r = store.append(make_ruling(p["id"]), path)
    if executed:
        pid = f"project-{len(store.list_project_ids(path)) + 1:04d}"
        step = {"id": f"{pid}/s1", "tool": "construction.mine-vein", "args": {},
                "targets": {"set": ["t1"]}, "requires": [], "trigger": "all_success",
                "prefer_after": [], "guards": "default"}
        store.append(make_project(from_ruling=r["id"], steps=[step]), path)
        store.append(make_executed(
            r["id"], step_id=step["id"],
            actions=[{"tool": "construction.mine-vein", "outcome": "success",
                      "targets": ["t1"], "target_state": "done"}]), path)
    return p, r


def test_tools_are_executor_only_native_and_do_not_mutate():
    for tid in (et.QUEUE_CLOSE_LEGACY, et.QUEUE_CUTOVER, et.QUEUE_EXECUTION_STATE):
        tool = et.NATIVE_TOOLS[tid]
        assert tool.executor_only and tool.native and not tool.mutates
        text, schema = tool.describe("conductor")
        assert schema["additionalProperties"] is False and text


@pytest.mark.parametrize("role", ["architect", "overseer", "quartermaster", "consultant"])
@pytest.mark.asyncio
async def test_no_model_role_may_call_any_executor_tool(db, role):
    for tid, args in (
        (et.QUEUE_CLOSE_LEGACY, {"target_id": "ruling-0001", "reason": "x"}),
        (et.QUEUE_CUTOVER, {"group": "legacy"}),
        (et.QUEUE_EXECUTION_STATE, {}),
    ):
        with pytest.raises(queue_tools.QueueToolError, match="only the conductor"):
            await _call(tid, args, db, role=role)
    assert not db.exists()


@pytest.mark.asyncio
async def test_unknown_argument_refused(db):
    with pytest.raises(queue_tools.QueueToolError, match="unexpected argument"):
        await _call(et.QUEUE_CUTOVER, {"group": "legacy", "role": "x"}, db)


@pytest.mark.asyncio
async def test_cutover_check_lists_every_accepted_ruling_and_changes_nothing(db):
    accepted(db, 1)
    accepted(db, 2, ptype="work_order", executed=True)
    text, out = await _call(et.QUEUE_CUTOVER, {"group": "legacy"}, db)
    assert out["ok"] and out["blockers"] == [] and out["applied"] is False
    assert out["would_close"] == 2
    assert {t["id"]: t["executed"] for t in out["targets"]} == {"ruling-0001": False, "ruling-0002": True}
    assert store.cutover(db, "legacy") is None
    assert [r for r in store.load(db) if r["kind"] == "close"] == []


@pytest.mark.asyncio
async def test_cutover_apply_closes_with_computed_outcomes_and_no_dfhack(db):
    accepted(db, 1)
    accepted(db, 2, executed=True)
    _, out = await _call(et.QUEUE_CUTOVER, {"group": "legacy", "apply": True}, db)
    assert out["applied"] and out["cutover_id"] == "ruling-0002"
    outcomes = {c["id"]: c["outcome"] for c in out["closed"]}
    assert outcomes == {"ruling-0001": "not_done", "ruling-0002": "completed"}
    closes = [r for r in store.load(db) if r["kind"] == "close"]
    assert len(closes) == 2 and all(c["role"] == "conductor" for c in closes)
    assert store.legacy_targets(db, "legacy") == []
    # work done after the cutover is untouched, and a rerun does not close it
    accepted(db, 3)
    _, again = await _call(et.QUEUE_CUTOVER, {"group": "legacy", "apply": True}, db)
    assert again["closed"] == [] and again["cutover_id"] == "ruling-0002"
    assert not [r for r in store.load(db) if r["kind"] == "close" and r.get("ruling_id") == "ruling-0003"]


@pytest.mark.asyncio
async def test_cutover_apply_resumes_after_a_crash(db):
    accepted(db, 1)
    accepted(db, 2)
    store.set_cutover(db, "legacy", "ruling-0002")
    store.close_legacy(db, "ruling-0001", reason="half done")
    _, out = await _call(et.QUEUE_CUTOVER, {"group": "legacy", "apply": True}, db)
    assert [c["id"] for c in out["closed"]] == ["ruling-0002"]


@pytest.mark.asyncio
async def test_cutover_blockers_for_a_group(db, tmp_path, monkeypatch):
    accepted(db, 1)
    _, out = await _call(et.QUEUE_CUTOVER, {"group": "rooms", "apply": True}, db)
    assert not out["ok"] and not out["applied"]
    joined = " | ".join(out["blockers"])
    assert "legacy cutover is not set" in joined and "not frozen" in joined
    assert store.cutover(db, "rooms") is None
    set_routing(monkeypatch, tmp_path, frozen=True)
    await _call(et.QUEUE_CUTOVER, {"group": "legacy", "apply": True}, db)
    _, ok = await _call(et.QUEUE_CUTOVER, {"group": "rooms"}, db)
    assert ok["ok"], ok["blockers"]
    set_routing(monkeypatch, tmp_path, frozen=True, routed=True)
    _, routed = await _call(et.QUEUE_CUTOVER, {"group": "rooms"}, db)
    assert any("already routed" in b for b in routed["blockers"])


@pytest.mark.asyncio
async def test_cutover_rejects_an_unknown_group_and_an_empty_queue(db):
    with pytest.raises(queue_tools.QueueToolError, match="not `legacy` or a routing group"):
        await _call(et.QUEUE_CUTOVER, {"group": "nope"}, db)
    _, out = await _call(et.QUEUE_CUTOVER, {"group": "legacy"}, db)
    assert any("no ruling" in b for b in out["blockers"])


@pytest.mark.asyncio
async def test_close_legacy_tool_closes_one_and_refuses_above_the_cutover(db):
    accepted(db, 1)
    accepted(db, 2)
    store.set_cutover(db, "legacy", "ruling-0001")
    _, out = await _call(et.QUEUE_CLOSE_LEGACY, {"target_id": "ruling-0001", "reason": "swept"}, db)
    assert out["outcome"] == "not_done" and out["close_id"].startswith("close-")
    with pytest.raises(queue_tools.QueueToolError, match="above its cutover"):
        await _call(et.QUEUE_CLOSE_LEGACY, {"target_id": "ruling-0002", "reason": "swept"}, db)
    with pytest.raises(queue_tools.QueueToolError, match="'reason'"):
        await _call(et.QUEUE_CLOSE_LEGACY, {"target_id": "ruling-0001"}, db)


@pytest.mark.asyncio
async def test_execution_state_is_read_only_and_empty_on_a_quiet_queue(db):
    accepted(db, 1)
    before = store.load(db)
    text, out = await _call(et.QUEUE_EXECUTION_STATE, {}, db)
    assert out["open_projects"] == [] and out["ready_steps"] == [] and out["unresolved_runs"] == []
    assert out["awaiting_cleanup"] == [] and out["done_since"] == []
    assert store.load(db) == before


# ---- roles.py load rules ------------------------------------------------------------


def _registry():
    from dfmcp import (
        conductor_tools, doctrine_tools, gotchas_tools, knowledge_tools, series_tools,
    )
    return load_registry(native_tools={
        **queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS, **series_tools.NATIVE_TOOLS,
        **gotchas_tools.NATIVE_TOOLS, **knowledge_tools.NATIVE_TOOLS, **conductor_tools.NATIVE_TOOLS,
    })


def test_real_roster_loads_and_only_the_conductor_holds_executor_tools():
    registry = _registry()
    roster = load_roster(registry)
    for role, perms in roster.roles.items():
        held = {t for t in set(perms.read) | set(perms.write) if getattr(registry.get(t), "executor_only", False)}
        if role == "conductor":
            assert held == set(et.NATIVE_TOOLS)  # all ten, and nothing else
        else:
            assert held == set(), role


def _roster_with(tmp_path, role, tool_id, section="read"):
    """The real agents dir with `tool_id` added to `role`'s allowlist."""
    import shutil
    from dfmcp.roles import DEFAULT_AGENTS_DIR
    dst = tmp_path / "agents"
    shutil.copytree(DEFAULT_AGENTS_DIR, dst)
    f = dst / role / "tools.yaml"
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    doc.setdefault(section, []).append({"id": tool_id, "status": "exists"})
    f.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return dst


@pytest.mark.parametrize("role", ["overseer", "architect"])
def test_granting_an_executor_tool_to_a_model_fails_the_load(tmp_path, role):
    registry = _registry()
    agents = _roster_with(tmp_path, role, et.QUEUE_CLOSE_LEGACY)
    with pytest.raises(RoleValidationError, match="executor-only"):
        load_roster(registry, agents)


def test_a_routed_tool_on_an_allowlist_fails_the_load(tmp_path, monkeypatch):
    registry = _registry()
    set_routing(monkeypatch, tmp_path, routed=True)
    load_roster(registry)  # stage 2E: the Overseer no longer holds a rooms tool
    # Verify the verification: the same load must refuse once one is granted back.
    agents = _roster_with(tmp_path, "overseer", "blueprint.reserve", section="write")
    with pytest.raises(RoleValidationError, match="routed group"):
        load_roster(registry, agents)
