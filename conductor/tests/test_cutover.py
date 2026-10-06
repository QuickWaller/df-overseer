"""conductor/cutover.py: the 2a operator CLI, over a fake tool caller."""

import pytest

from conductor import cutover
from conductor.mcp_client import FakeToolCaller, MCPToolError

pytestmark = pytest.mark.asyncio


def _state(*, set_at=None, targets=(), blockers=(), group="legacy"):
    return {"ok": not blockers, "blockers": list(blockers), "group": group, "cutover_set": set_at,
            "would_close": len(targets), "targets": list(targets), "applied": False}


_T = [{"kind": "ruling", "id": "ruling-0001", "executed": False, "summary": "a bedroom"},
      {"kind": "ruling", "id": "ruling-0002", "executed": True, "summary": "a stair"}]


async def test_check_lists_every_target_and_calls_only_the_read_form():
    caller = FakeToolCaller({"queue.cutover": _state(targets=_T)})
    lines = []
    code = await cutover.run("legacy", False, caller, out=lines.append)
    assert code == 0
    assert caller.calls == [("queue.cutover", {"group": "legacy", "apply": False})]
    text = "\n".join(lines)
    assert "ruling-0001 (not executed)" in text and "ruling-0002 (executed)" in text
    assert "nothing was changed" in text


async def test_check_with_a_blocker_exits_nonzero():
    caller = FakeToolCaller({"queue.cutover": _state(blockers=["rooms is not frozen"], group="rooms")})
    assert await cutover.run("rooms", False, caller, out=lambda _l: None) == 1


async def test_apply_refuses_on_a_blocker_without_calling_apply():
    caller = FakeToolCaller({"queue.cutover": _state(blockers=["legacy cutover not set"], group="rooms")})
    assert await cutover.run("rooms", True, caller, out=lambda _l: None) == 1
    assert all(a["apply"] is False for _t, a in caller.calls)


async def test_apply_closes_then_rechecks_and_reports_clean():
    seq = [
        _state(targets=_T),
        {**_state(set_at="ruling-0002"), "applied": True, "cutover_id": "ruling-0002",
         "closed": [{"id": "ruling-0001", "close_id": "close-0001", "outcome": "not_done"},
                    {"id": "ruling-0002", "close_id": "close-0002", "outcome": "completed"}]},
        _state(set_at="ruling-0002"),
    ]
    caller = FakeToolCaller({"queue.cutover": lambda _a: seq.pop(0)})
    lines = []
    assert await cutover.run("legacy", True, caller, out=lines.append) == 0
    assert [a["apply"] for _t, a in caller.calls] == [False, True, False]
    assert "ruling-0001 -> close-0001 not_done" in "\n".join(lines)
    assert "nothing left to close" in "\n".join(lines)


async def test_apply_that_leaves_targets_open_exits_nonzero():
    seq = [_state(targets=_T), {**_state(set_at="ruling-0002"), "applied": True, "closed": []},
           _state(set_at="ruling-0002", targets=_T[:1])]
    caller = FakeToolCaller({"queue.cutover": lambda _a: seq.pop(0)})
    assert await cutover.run("legacy", True, caller, out=lambda _l: None) == 1


async def test_rooms_apply_reminds_the_operator_to_flip_routed():
    seq = [_state(group="rooms"), {**_state(group="rooms", set_at="ruling-0002"), "applied": True, "closed": []},
           _state(group="rooms", set_at="ruling-0002")]
    caller = FakeToolCaller({"queue.cutover": lambda _a: seq.pop(0)})
    lines = []
    assert await cutover.run("rooms", True, caller, out=lines.append) == 0
    assert "routed: true" in "\n".join(lines)


async def test_a_failed_call_is_exit_two_not_a_traceback():
    def boom(_a):
        raise MCPToolError("queue.cutover: dfmcp is unreachable")
    assert await cutover.run("legacy", False, FakeToolCaller({"queue.cutover": boom}), out=lambda _l: None) == 2


def test_the_cli_defaults_to_check():
    caller = FakeToolCaller({"queue.cutover": _state()})
    assert cutover.main(["legacy"], caller=caller) == 0
    assert all(a["apply"] is False for _t, a in caller.calls)
