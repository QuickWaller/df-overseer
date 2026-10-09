"""Decision 10: the pause stamp on tool replies (dfmcp/pause_stamp.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dfmcp import pause_stamp as ps
from dfmcp.server import build_asgi_app, build_mcp_server
from dfmcp.tests.test_dfhack_client import make_ok_action
from dfmcp.tests.test_server import (  # noqa: F401 -- fixtures
    ARCHITECT_TOKEN, TOKENS, _BIND_HOST, fake_dfhack, mcp_session, pool, registry, roster,
)


def test_stamp_text_shapes():
    assert ps.stamp_text({"paused": False}) is None
    assert ps.stamp_text(None) is None
    assert ps.stamp_text("junk") is None
    assert ps.stamp_text({"paused": "yes"}) is None
    assert ps.stamp_text({"paused": True}) == "paused"
    assert ps.stamp_text({"paused": True, "tripwire": {"reason": "death"}}) == "paused, tripwire: death"
    assert ps.stamp_text({"paused": True, "blocking_panel": {"name": "Petitions"}}) == "paused, panel open: Petitions"
    assert len(ps.stamp_text({"paused": True, "tripwire": {"reason": "x" * 500}})) == ps.MAX_LEN


class _Clock:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.mark.asyncio
async def test_cache_one_read_per_window_and_refresh():
    calls = []
    clock = _Clock()

    async def read():
        calls.append(1)
        return {"paused": True}

    s = ps.PauseStamp(read, ttl=5, now=clock)
    assert await s.current() == "paused"
    assert await s.current() == "paused"
    assert len(calls) == 1
    clock.t = 6
    await s.current()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_fails_open_and_caches_failure():
    calls = []

    async def read():
        calls.append(1)
        raise RuntimeError("dfhack down")

    s = ps.PauseStamp(read, ttl=5, now=_Clock())
    assert await s.current() is None
    assert await s.current() is None
    assert len(calls) == 1


def test_apply_adds_field_and_text_and_wraps_non_dict():
    from mcp import types

    r = types.CallToolResult(content=[types.TextContent(type="text", text="[1]")], structuredContent=None, isError=False)
    out = ps.apply(r, "paused")
    assert out.structured_content == {"fort_paused": "paused"}
    assert out.content[-1].text == 'fort_paused: "paused"'
    assert out.is_error is False
    assert ps.apply(r, None) is r


def _app(registry, roster, pool, stamp):
    server = build_mcp_server(
        registry, roster, pool, Path(tempfile.mkdtemp()) / "q.sqlite3", stamp_pause=stamp,
    )
    return build_asgi_app(server, TOKENS, bind_host=_BIND_HOST)


@pytest.mark.asyncio
async def test_server_stamps_when_paused(registry, roster, pool, fake_dfhack):
    fake_dfhack.queue_actions(make_ok_action('{"candidates": []}'), make_ok_action('{"paused": true, "fps": 100}'))
    async with mcp_session(_app(registry, roster, pool, True), ARCHITECT_TOKEN) as session:
        result = await session.call_tool("openarea__find", {"w": 4, "h": 5, "near_landmark": "MainHall"})
    assert result.is_error is False
    assert result.structured_content == {"candidates": [], "fort_paused": "paused"}


@pytest.mark.asyncio
async def test_server_adds_nothing_when_running_or_status_fails(registry, roster, pool, fake_dfhack):
    fake_dfhack.queue_actions(make_ok_action('{"candidates": []}'), make_ok_action('{"paused": false}'))
    async with mcp_session(_app(registry, roster, pool, True), ARCHITECT_TOKEN) as session:
        result = await session.call_tool("openarea__find", {"w": 4, "h": 5, "near_landmark": "MainHall"})
    assert result.structured_content == {"candidates": []}

    fake_dfhack.queue_actions(make_ok_action('{"candidates": []}'), make_ok_action("not json"))
    async with mcp_session(_app(registry, roster, pool, True), ARCHITECT_TOKEN) as session:
        result = await session.call_tool("openarea__find", {"w": 4, "h": 5, "near_landmark": "MainHall"})
    assert result.is_error is False
    assert result.structured_content == {"candidates": []}


@pytest.mark.asyncio
async def test_server_default_is_off(registry, roster, pool, fake_dfhack):
    fake_dfhack.queue_actions(make_ok_action('{"candidates": []}'))
    async with mcp_session(_app(registry, roster, pool, False), ARCHITECT_TOKEN) as session:
        result = await session.call_tool("openarea__find", {"w": 4, "h": 5, "near_landmark": "MainHall"})
    assert result.structured_content == {"candidates": []}
    assert len(fake_dfhack.received_requests) == 1
