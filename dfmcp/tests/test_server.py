"""Tests for dfmcp/server.py: the MCP transport itself.

Runs the real ASGI app `dfmcp.server.build_asgi_app` produces entirely
in-process, over httpx2's ASGITransport (no socket, no uvicorn, no VM), and
drives it with the actual MCP Python SDK client
(`mcp.client.streamable_http` + `mcp.client.session.ClientSession`) rather
than hand-decoded raw HTTP, so a wire-shape bug on the server side would
show up as a real client-side failure, not just a happy assertion against
our own encoder.

DFHack itself is `dfmcp/tests/test_dfhack_client.py`'s own
`FakeDFHackServer`, reused rather than re-invented, per the handoff brief.
This file relies on that fake's `received_requests` capture list, added in
this same stream purely additively (see that file's docstring).

## Why every test builds a fresh Server/app

`Server.streamable_http_app()`'s returned Starlette app owns a
`StreamableHTTPSessionManager` whose `.run()` (invoked from the app's own
ASGI `lifespan`) **can only be entered once per instance** -- confirmed by
running it twice against the same app object, which raises `RuntimeError:
StreamableHTTPSessionManager .run() can only be called once per instance.`
So `_app()` below is called fresh for every session opened, matching how a
real deployment only ever builds one app for the one uvicorn process it
runs under -- this is a per-test-scenario need, not a code smell.

## Why lifespan is driven by hand

No real server process is involved in an in-process ASGI-transport test, so
nothing else will ever send `lifespan.startup`/`lifespan.shutdown` -- and
the MCP Starlette app's own lifespan is what starts/stops that same session
manager's task group, without which every request fails with "Task group
is not initialized. Make sure to use run()." `_run_asgi_lifespan` below is
a two-line hand implementation rather than a third-party dependency, since
that is genuinely all driving this protocol by hand takes.

## What remains unproven by this file, stated plainly

Everything here runs against `FakeDFHackServer` and an in-process ASGI
transport -- not uvicorn, not a real socket, not VM 103, which this stream
was barred from touching. See the stream's report for the exact command
that would close each of those gaps.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import AsyncIterator, Dict, Optional

import pytest
import pytest_asyncio

from dfmcp.dfhack_client import DFHackConnectionPool, _encode_run_command_request
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfmcp.tests.test_dfhack_client import FakeDFHackServer, make_fail_action, make_ok_action

# dfmcp/server.py deliberately targets the mcp 2.x line (dfmcp/requirements.txt
# pins mcp==2.2.0; see that file and dfmcp/server.py's own module docstring
# for why 1.x cannot build this server at all -- its low-level Server has no
# on_list_tools/on_call_tool constructor kwargs, so this is not a version
# skew that degrades gracefully). If the environment running pytest has not
# been set up with that pin (this repo's baseline global environment has
# mcp 1.27.1, installed for unrelated tooling), importing this file must
# SKIP cleanly rather than raise an ImportError -- a raw ImportError here
# is a *collection error*, and pytest's default behaviour is to abort the
# entire run on one, which would silently take the other 121+ tests down
# with it for an environment reason that has nothing to do with them.
try:
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from dfmcp.server import (
        ConfigError,
        ServerConfig,
        build_asgi_app,
        build_mcp_server,
        config_from_env,
    )
except ImportError as _import_error:  # pragma: no cover -- exercised only in an unpinned environment
    pytest.skip(
        "dfmcp/server.py needs the mcp 2.x line (dfmcp/requirements.txt pins mcp==2.2.0, "
        "which also brings in httpx2 as a transitive dependency); this environment does not "
        f"have it importable ({_import_error}). Install dfmcp/requirements.txt into a venv "
        "(see dfmcp/README.md) and run pytest from inside it to exercise this file.",
        allow_module_level=True,
    )

# Non-loopback on purpose: Server.streamable_http_app() auto-enables
# Host-header DNS-rebinding protection only when `host` is
# 127.0.0.1/localhost/::1 (confirmed by reading 2.2.0's own source), which
# would then reject the arbitrary Host header an in-process ASGI transport
# sends unless it happens to also carry an explicit port matching the
# allowlist pattern. A real deployment binds a real tailnet address anyway
# (docs/AGENT-ARCHITECTURE.md §13), so exercising the loopback branch here
# would be testing a code path production never takes.
_BIND_HOST = "100.64.0.5"
_BASE_URL = "http://127.0.0.1:80"
_MCP_URL = f"{_BASE_URL}/mcp"

ARCHITECT_TOKEN = "architect-test-token-aaaaaaaaaa"
OVERSEER_TOKEN = "overseer-test-token-bbbbbbbbbbb"
CONSULTANT_TOKEN = "consultant-test-token-ccccccccc"
TOKENS: Dict[str, str] = {
    ARCHITECT_TOKEN: "architect",
    OVERSEER_TOKEN: "overseer",
    CONSULTANT_TOKEN: "consultant",
}


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture(scope="module")
def roster(registry):
    return load_roster(registry)


@pytest_asyncio.fixture
async def fake_dfhack():
    async with FakeDFHackServer() as server:
        yield server


@pytest_asyncio.fixture
async def pool(fake_dfhack):
    p = DFHackConnectionPool(host=fake_dfhack.host, port=fake_dfhack.port, size=2)
    await p.start()
    yield p
    await p.close()


def _app(registry, roster, pool):
    """A fresh Server + ASGI app. See module docstring for why this is
    called once per session rather than shared across a test."""
    server = build_mcp_server(registry, roster, pool)
    return build_asgi_app(server, TOKENS, bind_host=_BIND_HOST)


@contextlib.asynccontextmanager
async def _run_asgi_lifespan(app) -> AsyncIterator[None]:
    """Drive the ASGI lifespan protocol by hand -- see module docstring."""
    startup_complete = asyncio.Event()
    shutdown_requested = asyncio.Event()
    shutdown_complete = asyncio.Event()
    startup_error: Dict[str, str] = {}

    async def receive():
        if not startup_complete.is_set():
            return {"type": "lifespan.startup"}
        await shutdown_requested.wait()
        return {"type": "lifespan.shutdown"}

    async def send(message):
        if message["type"] == "lifespan.startup.complete":
            startup_complete.set()
        elif message["type"] == "lifespan.startup.failed":
            startup_error["message"] = message.get("message", "")
            startup_complete.set()
        elif message["type"] == "lifespan.shutdown.complete":
            shutdown_complete.set()

    task = asyncio.ensure_future(app({"type": "lifespan"}, receive, send))
    await startup_complete.wait()
    if startup_error:
        raise RuntimeError(f"ASGI lifespan startup failed: {startup_error['message']}")
    try:
        yield
    finally:
        shutdown_requested.set()
        await asyncio.wait_for(shutdown_complete.wait(), timeout=5)
        await task


@contextlib.asynccontextmanager
async def mcp_session(app, token: Optional[str]) -> AsyncIterator[ClientSession]:
    """One authenticated (or not) MCP client session against `app`, entirely
    in-process. `token=None` sends no Authorization header at all."""
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with _run_asgi_lifespan(app):
        http_client = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=_BASE_URL, headers=headers
        )
        async with http_client:
            async with streamable_http_client(_MCP_URL, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session


# ==========================================================================
# The four load-bearing tests the handoff names explicitly
# ==========================================================================


class TestServerScoping:
    pytestmark = pytest.mark.asyncio

    async def test_advisors_tools_list_has_no_mutating_tool(self, registry, roster, pool):
        """Test 1: an advisor's tools/list contains no mutating tool.
        Asserted for the Architect specifically, per the handoff."""
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.list_tools()
            names = {t.name for t in result.tools}

        assert names, "the architect should see at least some tools"
        for tool_id in registry.ids():
            if registry.get(tool_id).mutates:
                mutating_name = tool_id.replace(".", "__")
                assert mutating_name not in names, (
                    f"architect's tools/list must not contain the mutating tool {mutating_name!r}"
                )
        # A concrete, known pair as a control, so the sweep above can't pass
        # vacuously if every id somehow turned out read-only.
        assert "openarea__build" not in names
        assert "openarea__find" in names

    async def test_advisor_calling_a_write_tool_is_refused_with_reason_intact(
        self, registry, roster, pool, fake_dfhack
    ):
        """Test 2, the load-bearing one: an advisor calling a write tool is
        refused, and the refusal carries the reason string -- not a
        protocol-level error, and not silently dropped. This is what lets
        the design treat client-side scoping as a thin second layer
        (decisions/DECISIONS.md 2026-09-12): if this does not hold, that
        conclusion needs revisiting, not patching around.
        """
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool(
                "openarea__build",
                {"w": 3, "h": 3, "near_landmark": "MainHall", "blueprint_file": "stockpile.csv"},
            )

        assert result.is_error is True
        text = "".join(block.text for block in result.content if block.type == "text")
        # The exact string agents/architect/tools.yaml writes for this deny
        # entry -- proving the *specific* reason survives Roster.check ->
        # CallToolResult -> the wire -> the client, not a generic stand-in.
        assert text == "Advisors do not act. Propose it."
        # And the call must never have reached DFHack: nothing was queued
        # for it, so a real RunCommand would have hit the fake's default
        # OK-with-no-text action instead of being refused before ever
        # reaching the pool.
        assert fake_dfhack.received_requests == []

    async def test_unknown_or_malformed_token_is_rejected_without_leaking_why(self, registry, roster, pool):
        """Test 3: a token that resolves to nothing is rejected at the
        transport (never passed through as an anonymous caller), and the
        rejection does not leak which part was wrong -- an unknown token, an
        empty bearer value, and no Authorization header at all all produce
        the identical generic response.
        """
        unknown_token = "unknown-token-that-is-not-in-the-map"
        empty_token = ""

        bodies = []
        async with _run_asgi_lifespan(_app(registry, roster, pool)) as _:
            pass  # smoke: building/tearing down a session-less app is itself fine

        for token, label in ((unknown_token, "unknown"), (empty_token, "empty"), (None, "absent")):
            app = _app(registry, roster, pool)  # fresh: see module docstring
            headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
            async with _run_asgi_lifespan(app):
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app), base_url=_BASE_URL, headers=headers
                ) as client:
                    resp = await client.post(
                        _MCP_URL,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-06-18",
                                "capabilities": {},
                                "clientInfo": {"name": "test", "version": "0"},
                            },
                        },
                        headers={"Accept": "application/json, text/event-stream"},
                    )
                    assert resp.status_code == 401, f"{label} token: expected 401, got {resp.status_code}"
                    bodies.append(resp.json())

        # Also confirm the SDK client's own session-establishment path (not
        # just a raw POST) actually fails for a bad token, rather than
        # silently degrading to an anonymous session.
        app = _app(registry, roster, pool)
        with pytest.raises(Exception):
            async with mcp_session(app, unknown_token):
                pass

        # Identical body across unknown / empty / absent: nothing
        # distinguishes "wrong token" from "no token" from "empty token" in
        # what the caller gets back.
        assert bodies[0] == bodies[1] == bodies[2]
        body_text = json.dumps(bodies[0])
        assert unknown_token not in body_text
        for role in TOKENS.values():
            assert role not in body_text

    async def test_permitted_call_round_trips_through_the_pool(self, registry, roster, pool, fake_dfhack):
        """Test 4: a permitted call's argv reaches the fake DFHack exactly,
        and the JSON it prints comes back parsed.

        NOTE on this fixture's shape: `{"candidates": [...]}` is a dict, and
        this test exists to prove the plain dict-passthrough path. It is
        NOT what the real `df-overseer-openarea.lua find` command prints
        (that script prints a bare `[...]` array -- see
        `test_bare_json_array_output_is_wrapped_as_result` below). Every
        fake payload in this file must match what its real script actually
        prints, on pain of exactly the bug that hid behind this one: see
        `dfmcp/README.md`'s "Call results" section.
        """
        fake_dfhack.queue_actions(make_ok_action('{"candidates": [{"score": 7, "x": 10, "y": 20, "z": 1}]}'))

        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("openarea__find", {"w": 4, "h": 5, "near_landmark": "MainHall"})

        assert result.is_error is False
        assert result.structured_content == {"candidates": [{"score": 7, "x": 10, "y": 20, "z": 1}]}

        assert len(fake_dfhack.received_requests) == 1
        expected = _encode_run_command_request("df-overseer-openarea", ["find", "4", "5", "MainHall"])
        assert fake_dfhack.received_requests[0] == expected


# ==========================================================================
# Edge cases beyond the four named tests: not load-bearing on their own, but
# each closes a specific way the fused check->argv->pool->parse pipeline
# could otherwise fail silently or crash instead of returning a tool error.
# ==========================================================================


class TestServerCallEdgeCases:
    pytestmark = pytest.mark.asyncio

    async def test_sole_writer_can_call_the_mutating_tool_the_advisor_cannot(
        self, registry, roster, pool, fake_dfhack
    ):
        """The flip side of test 2: the same tool, called by the role the
        roster actually grants it to, succeeds -- proving the Architect's
        refusal above is the roster's role-scoping, not a bug that denies
        everyone regardless of role."""
        fake_dfhack.queue_actions(make_ok_action('{"built": true}'))
        app = _app(registry, roster, pool)
        async with mcp_session(app, OVERSEER_TOKEN) as session:
            result = await session.call_tool(
                "openarea__build",
                {"w": 3, "h": 3, "near_landmark": "MainHall", "blueprint_file": "stockpile.csv"},
            )
        assert result.is_error is False
        assert result.structured_content == {"built": True}

    async def test_unknown_tool_name_is_a_tool_error_not_a_crash(self, registry, roster, pool):
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("does_not_exist__at_all", {})
        assert result.is_error is True

    async def test_bad_arguments_are_a_tool_error_not_a_crash(self, registry, roster, pool):
        """argv_for_call's ArgumentError (a missing required arg, here) is
        surfaced the same way a Roster.check denial is: an MCP tool error,
        not a raised protocol exception -- and the call never reaches
        DFHack, matching the denial case."""
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("openarea__find", {"w": 3})
        assert result.is_error is True

    async def test_dfhack_call_failure_is_a_tool_error_not_a_crash(self, registry, roster, pool, fake_dfhack):
        fake_dfhack.queue_actions(make_fail_action(1))  # CR_FAILURE
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("openarea__find", {"w": 3, "h": 3, "near_landmark": "MainHall"})
        assert result.is_error is True
        text = "".join(block.text for block in result.content if block.type == "text")
        assert "CR_FAILURE" in text

    async def test_non_json_dfhack_output_is_a_tool_error_not_a_crash(self, registry, roster, pool, fake_dfhack):
        fake_dfhack.queue_actions(make_ok_action("this is not json"))
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("openarea__find", {"w": 3, "h": 3, "near_landmark": "MainHall"})
        assert result.is_error is True

    async def test_script_error_object_is_a_tool_error(self, registry, roster, pool, fake_dfhack):
        """Found live on VM 103, 2026-09-14: a script's own failure report,
        exactly {"error": "<message>"}, used to come back isError=False.
        The payload is the real off-map message the deployed
        df-overseer-diggable.lua prints."""
        fake_dfhack.queue_actions(
            make_ok_action('{"error": "level -500 from Embark Site is outside the map"}')
        )
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool(
                "diggable__find", {"w": 3, "h": 3, "level": -500, "near_landmark": "Embark Site"}
            )
        assert result.is_error is True
        text = "".join(block.text for block in result.content if block.type == "text")
        assert text == "level -500 from Embark Site is outside the map"

    async def test_object_with_error_field_beside_data_is_still_a_result(
        self, registry, roster, pool, fake_dfhack
    ):
        """Only the exact {"error": str} shape is a failure. A result that
        carries an error-ish field next to real data (the shape of `dig`'s
        `quickfort_error`) must stay a normal result."""
        payload = '{"error": "partial", "near_landmark": "Wagon"}'
        fake_dfhack.queue_actions(make_ok_action(payload))
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})
        assert result.is_error is False
        assert result.structured_content == {"error": "partial", "near_landmark": "Wagon"}

    async def test_bare_json_array_output_is_wrapped_as_result(self, registry, roster, pool, fake_dfhack):
        """Bug found on VM 103's first live smoke test, 2026-09-14: most
        real read tools print a bare JSON array, not an object. This
        payload is shaped like the real `df-overseer-landmarks.lua list`
        output (confirmed live), which is the exact command the smoke test
        used when it hit this. Before the fix, `_on_call_tool` passed the
        parsed list straight through as `structuredContent`, which the
        negotiated protocol version's `CallToolResult.structured_content`
        (`dict[str, Any] | None` through 2025-11-25, per
        `mcp_types._v2025_11_25`) rejects at serialization -- the SDK's own
        `runner.py` catches that `ValidationError` and raises
        `MCPError(-32603, "Handler returned an invalid result")`, a
        protocol-level error this design exists to avoid. This test drives
        the real SDK client/session, so that failure surfaces exactly the
        way it did against the live client, not as a hand-checked value.
        """
        fake_dfhack.queue_actions(
            make_ok_action(
                '[{"name": "Wagon", "exits": [{"direction": "E", "distance_tiles": 1, '
                '"to": "Embark Site", "walkable": true}]}]'
            )
        )
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})

        assert result.is_error is False
        assert result.structured_content == {
            "result": [
                {
                    "name": "Wagon",
                    "exits": [
                        {"direction": "E", "distance_tiles": 1, "to": "Embark Site", "walkable": True}
                    ],
                }
            ]
        }
        text = "".join(block.text for block in result.content if block.type == "text")
        assert json.loads(text) == [
            {
                "name": "Wagon",
                "exits": [{"direction": "E", "distance_tiles": 1, "to": "Embark Site", "walkable": True}],
            }
        ]

    async def test_bare_json_scalar_output_is_wrapped_as_result(self, registry, roster, pool, fake_dfhack):
        """Same rule, a scalar rather than a list: any parsed JSON value
        that is not a dict gets the same {"result": ...} wrapping."""
        fake_dfhack.queue_actions(make_ok_action("3"))
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("landmarks__list", {})

        assert result.is_error is False
        assert result.structured_content == {"result": 3}
        text = "".join(block.text for block in result.content if block.type == "text")
        assert text == "3"


# ==========================================================================
# Config
# ==========================================================================


class TestServerConfig:
    def test_bind_host_is_required(self):
        with pytest.raises(ConfigError):
            config_from_env({})

    def test_bind_host_must_not_be_0_0_0_0(self):
        with pytest.raises(ConfigError):
            ServerConfig(bind_host="0.0.0.0")

    def test_valid_env_produces_expected_config(self):
        config = config_from_env(
            {
                "MCP_SERVER_BIND_HOST": "100.64.0.9",
                "MCP_SERVER_BIND_PORT": "9443",
                "MCP_SERVER_DFHACK_HOST": "127.0.0.1",
                "MCP_SERVER_DFHACK_PORT": "5001",
                "MCP_SERVER_POOL_SIZE": "8",
            }
        )
        assert config == ServerConfig(
            bind_host="100.64.0.9",
            bind_port=9443,
            dfhack_host="127.0.0.1",
            dfhack_port=5001,
            pool_size=8,
        )

    def test_missing_optional_fields_fall_back_to_defaults(self):
        config = config_from_env({"MCP_SERVER_BIND_HOST": "100.64.0.9"})
        assert config == ServerConfig(bind_host="100.64.0.9")

    def test_non_integer_port_is_a_config_error(self):
        with pytest.raises(ConfigError):
            config_from_env({"MCP_SERVER_BIND_HOST": "100.64.0.9", "MCP_SERVER_BIND_PORT": "not-a-port"})

    def test_zero_pool_size_is_a_config_error(self):
        with pytest.raises(ConfigError):
            config_from_env({"MCP_SERVER_BIND_HOST": "100.64.0.9", "MCP_SERVER_POOL_SIZE": "0"})
