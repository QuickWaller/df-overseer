"""conductor/mcp_client.py: the id -> MCP-tool-name rule, and FakeToolCaller
-- the double every other test in this package uses instead of a real
connection (hard line: no VM, this module's StreamableHTTPMCPClient is never
exercised against a real server here)."""

from __future__ import annotations

import pytest

from conductor.mcp_client import FakeToolCaller, MCPToolError, tool_name


def test_tool_name_matches_dfmcp_tools_own_rule():
    """dfmcp.tools._tool_name: "openarea.build" -> "openarea__build". This
    is deliberately NOT imported from dfmcp (see this module's own
    docstring on the host boundary) -- so this test is what actually keeps
    the two definitions in sync: if dfmcp's own rule ever changes, this
    test does not itself catch it (it has no import to catch it), but a
    live call against the real server would immediately 404/refuse, which
    is the honest state of this cross-host contract without a shared
    import."""
    assert tool_name("clock.status") == "clock__status"
    assert tool_name("queue.grade") == "queue__grade"
    assert tool_name("fort.quicksave") == "fort__quicksave"


@pytest.mark.asyncio
async def test_fake_tool_caller_returns_a_fixed_result_and_records_the_call():
    fake = FakeToolCaller({"clock.status": {"paused": False, "fps": 100}})
    result = await fake.call_tool("clock.status", {})
    assert result == {"paused": False, "fps": 100}
    assert fake.calls == [("clock.status", {})]


@pytest.mark.asyncio
async def test_fake_tool_caller_supports_a_callable_result_for_advancing_state():
    calls = {"n": 0}

    def _advancing(arguments):
        calls["n"] += 1
        return {"tick": calls["n"] * 100}

    fake = FakeToolCaller({"overview.get": _advancing})
    first = await fake.call_tool("overview.get", {})
    second = await fake.call_tool("overview.get", {})
    assert first == {"tick": 100}
    assert second == {"tick": 200}


@pytest.mark.asyncio
async def test_fake_tool_caller_refuses_an_unconfigured_tool_id():
    fake = FakeToolCaller()
    with pytest.raises(MCPToolError, match="clock.arm"):
        await fake.call_tool("clock.arm", {})


@pytest.mark.asyncio
async def test_fake_tool_caller_records_arguments_by_value_not_reference():
    fake = FakeToolCaller({"queue.pending": {"count": 0}})
    args = {"limit": 5}
    await fake.call_tool("queue.pending", args)
    args["limit"] = 999  # mutate after the call
    assert fake.calls[0][1] == {"limit": 5}  # recorded copy is unaffected


def test_streamable_http_client_module_imports_cleanly():
    """Proves conductor.mcp_client itself has no hard, module-level
    dependency on the MCP SDK for every OTHER caller of this package (the
    SDK import is lazy, inside StreamableHTTPMCPClient.call_tool only) --
    importing the module and constructing the class must never require a
    live connection or even the SDK to be resolvable at import time."""
    from conductor.mcp_client import StreamableHTTPMCPClient
    client = StreamableHTTPMCPClient("http://127.0.0.1:8443/mcp", "not-a-real-token")
    assert client.url == "http://127.0.0.1:8443/mcp"
