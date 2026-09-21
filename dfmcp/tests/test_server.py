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
import logging
import tempfile
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

import pytest
import pytest_asyncio

from dfqueue import store as _dfqueue_store

from dfmcp.dfhack_client import DFHackConnectionPool, _encode_run_command_request
from dfmcp.doctrine_tools import NATIVE_TOOLS as DOCTRINE_NATIVE_TOOLS
from dfmcp.queue_tools import NATIVE_TOOLS
from dfmcp.registry import load_registry
from dfmcp.roles import load_roster
from dfmcp.series_tools import NATIVE_TOOLS as SERIES_NATIVE_TOOLS
from dfmcp.gotchas_tools import NATIVE_TOOLS as GOTCHAS_NATIVE_TOOLS
from dfmcp.knowledge_tools import NATIVE_TOOLS as KNOWLEDGE_NATIVE_TOOLS
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
    # native_tools=NATIVE_TOOLS: the real agents/architect/tools.yaml and
    # agents/overseer/tools.yaml now grant real queue.* ids
    # (handoffs/2026-09-15-queue-into-dfmcp.md), which roles.py rule 1
    # requires to exist in the registry -- load_roster(registry) below would
    # otherwise fail to load the real roster for every test in this file.
    # DOCTRINE_NATIVE_TOOLS merged in too, added
    # handoffs/2026-09-19-get-doctrine-tool.md: agents/consultant/tools.yaml
    # now grants doctrine.get, same rule-1 requirement. SERIES_NATIVE_TOOLS
    # merged in too, added handoffs/2026-09-19-series-mcp-tools.md:
    # agents/overseer/tools.yaml and agents/consultant/tools.yaml now grant
    # series.* ids, same rule-1 requirement.
    return load_registry(native_tools={**NATIVE_TOOLS, **DOCTRINE_NATIVE_TOOLS, **SERIES_NATIVE_TOOLS, **GOTCHAS_NATIVE_TOOLS, **KNOWLEDGE_NATIVE_TOOLS})


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


def _app(registry, roster, pool, queue_db_path=None):
    """A fresh Server + ASGI app. See module docstring for why this is
    called once per session rather than shared across a test.

    `queue_db_path` defaults to a fresh throwaway SQLite path per call
    (added `handoffs/2026-09-15-queue-into-dfmcp.md`), so every existing
    call site in this file that does not care about queue tools keeps
    working unchanged. Tests that DO care (TestQueueTools below) pass an
    explicit path so they can inspect what was written afterward via
    dfqueue.store directly."""
    if queue_db_path is None:
        queue_db_path = Path(tempfile.mkdtemp()) / "test-queue.sqlite3"
    server = build_mcp_server(registry, roster, pool, Path(queue_db_path))
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

    async def test_every_call_writes_one_json_log_line(self, registry, roster, pool, fake_dfhack, caplog):
        """A result, a refusal and a script error each leave exactly one
        parseable line with the correlating ids, and the token never
        appears in any of them."""
        caplog.set_level(logging.INFO, logger="dfmcp.calls")
        fake_dfhack.queue_actions(
            make_ok_action('[{"name": "Wagon", "exits": []}]'),
            make_ok_action('{"error": "level -500 from Embark Site is outside the map"}'),
        )
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            await session.call_tool("landmarks__list", {})
            await session.call_tool(
                "openarea__build",
                {"w": 3, "h": 3, "near_landmark": "MainHall", "blueprint_file": "stockpile.csv"},
            )
            await session.call_tool(
                "diggable__find", {"w": 3, "h": 3, "level": -500, "near_landmark": "Embark Site"}
            )

        records = [r for r in caplog.records if r.name == "dfmcp.calls"]
        assert len(records) == 3
        assert all(ARCHITECT_TOKEN not in r.getMessage() for r in records)
        ok, refused, script_error = (json.loads(r.getMessage()) for r in records)

        for line in (ok, refused, script_error):
            assert line["event"] == "tools/call"
            assert line["role"] == "architect"
            assert line["session_id"]
            assert line["request_id"] is not None
            assert line["duration_ms"] >= 0
        assert ok["session_id"] == refused["session_id"] == script_error["session_id"]

        assert ok["tool"] == "landmarks__list" and ok["tool_id"] == "landmarks.list"
        assert ok["is_error"] is False and ok["error"] is None and ok["result_chars"] > 0

        assert refused["tool"] == "openarea__build" and refused["is_error"] is True
        assert refused["error"]

        assert script_error["arguments"]["level"] == -500
        assert script_error["is_error"] is True
        assert script_error["error"] == "level -500 from Embark Site is outside the map"

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
# Native queue.* tools (handoffs/2026-09-15-queue-into-dfmcp.md): the four
# tests this stream's brief names explicitly, plus the edge cases the same
# brief's "Tests (required, not optional)" section lists. These are the
# first tests to exercise dfmcp.queue_tools end to end, through the real
# ASGI app, against FakeDFHackServer for the one DFHack call the native
# handlers make (overview.get, to stamp cycle/snapshot).
# ==========================================================================

# A minimal but real-shaped `overview.get` payload: `tier1.population` and
# `tier2.in_game_date`/`tier2.alerts` are exactly what
# `dfqueue.grade.game_tick_from_overview` and `learning.live_signals.read`
# read (see df-overseer-overview.lua / learning/live_signals.py). year 1,
# tick 500 -> game_tick 1*403200 + 500 = 403700.
_OVERVIEW_JSON = (
    '{"tier1": {"population": 7}, '
    '"tier2": {"in_game_date": "year 1, month 1, day 1, tick 500", "alerts": []}}'
)
_EXPECTED_GAME_TICK = 1 * 403200 + 500

_VALID_PROPOSE_ARGS = {
    "type": "workshop_siting",  # a real agents/architect/tools.yaml-granted TYPE_VOCAB_BY_ROLE entry
    "summary": "Site the next workshop on open ground near the Wagon.",
    "rationale": "Shortest hauling path of the candidates offered.",
    "prediction": {"signal": "fort.population", "op": "gte", "value": 1, "check_after_ticks": 1200},
    "cost": {"estimate": 10, "unit": "dwarf_ticks"},
    "suggested_priority": 3,
    "preconditions": [{"landmark": "Wagon", "state": "exists"}],
    "public_rationale": "Puts the workshop near the wagon.",
}

_VALID_RULE_ARGS = {
    "decision": "accept", "reason": "Shortest hauling path.", "public_rationale": "Approved.",
}


class TestQueueTools:
    pytestmark = pytest.mark.asyncio

    async def test_queue_tools_list_is_role_scoped(self, registry, roster, pool):
        """Test named in the brief: per-role tools/list shows exactly the
        right queue tools. Architect gets propose+pass only, overseer gets
        rule+pending only, consultant (whose type vocabulary is empty and
        whose tools.yaml keeps queue.propose `planned`, per the brief) gets
        none of the four."""
        # A fresh app per session: Server.streamable_http_app()'s session
        # manager can only run its lifespan once per instance (module
        # docstring, "Why every test builds a fresh Server/app").
        async with mcp_session(_app(registry, roster, pool), ARCHITECT_TOKEN) as session:
            architect_names = {t.name for t in (await session.list_tools()).tools}
        async with mcp_session(_app(registry, roster, pool), OVERSEER_TOKEN) as session:
            overseer_names = {t.name for t in (await session.list_tools()).tools}
        async with mcp_session(_app(registry, roster, pool), CONSULTANT_TOKEN) as session:
            consultant_names = {t.name for t in (await session.list_tools()).tools}

        assert {"queue__propose", "queue__pass"} <= architect_names
        assert not ({"queue__rule", "queue__pending"} & architect_names)

        assert {"queue__rule", "queue__pending"} <= overseer_names
        assert not ({"queue__propose", "queue__pass"} & overseer_names)

        # Updated 2026-09-22 (handoffs/2026-09-22-loop-queue-quartermaster.md):
        # the consultant now reads its open asks and answers them, and still
        # never proposes, passes or rules.
        assert {"queue__pending", "queue__answer"} <= consultant_names
        assert not ({"queue__propose", "queue__pass", "queue__rule"} & consultant_names)

    async def test_propose_writes_a_record_stamped_with_the_live_game_tick(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """Test named in the brief: a valid proposal is written with the
        tick taken from a fake overview.get."""
        queue_db = tmp_path / "queue.sqlite3"
        fake_dfhack.queue_actions(make_ok_action(_OVERVIEW_JSON))
        app = _app(registry, roster, pool, queue_db)

        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("queue__propose", _VALID_PROPOSE_ARGS)

        assert result.is_error is False
        assert result.structured_content["role"] == "architect"
        assert result.structured_content["cycle"] == _EXPECTED_GAME_TICK
        assert result.structured_content["snapshot"] == f"tick-{_EXPECTED_GAME_TICK}"
        text = "".join(b.text for b in result.content if b.type == "text")
        assert text.startswith("<proposal ")

        written = _dfqueue_store.load(queue_db)
        assert len(written) == 1
        assert written[0]["id"] == result.structured_content["id"]
        assert written[0]["role"] == "architect"

        assert len(fake_dfhack.received_requests) == 1
        expected = _encode_run_command_request("df-overseer-overview", ["get"])
        assert fake_dfhack.received_requests[0] == expected

    async def test_propose_with_a_supplied_role_argument_is_refused_and_writes_nothing(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """Test named in the brief: a supplied `role` argument is refused,
        not silently ignored, and nothing is written. Never even reaches
        DFHack: the argument check runs before cycle/snapshot stamping."""
        queue_db = tmp_path / "queue.sqlite3"
        app = _app(registry, roster, pool, queue_db)

        args = dict(_VALID_PROPOSE_ARGS)
        args["role"] = "overseer"  # attempting to assert an identity other than the caller's own

        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("queue__propose", args)

        assert result.is_error is True
        text = "".join(b.text for b in result.content if b.type == "text")
        assert "role" in text
        assert _dfqueue_store.load(queue_db) == []
        assert fake_dfhack.received_requests == []

    async def test_propose_with_extra_stray_fields_is_also_refused(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """The same refusal, for id/ts/cycle/snapshot too, not just role --
        none of the five may ever be supplied."""
        queue_db = tmp_path / "queue.sqlite3"
        for stray in ("id", "ts", "cycle", "snapshot"):
            args = dict(_VALID_PROPOSE_ARGS)
            args[stray] = "attempted-override"
            app = _app(registry, roster, pool, queue_db)  # fresh: see module docstring
            async with mcp_session(app, ARCHITECT_TOKEN) as session:
                result = await session.call_tool("queue__propose", args)
            assert result.is_error is True, stray
        assert _dfqueue_store.load(queue_db) == []
        assert fake_dfhack.received_requests == []

    async def test_propose_with_a_malformed_record_is_refused_with_reasons_and_writes_nothing(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """Test named in the brief: a malformed proposal returns isError
        listing the errors and writes nothing. Reaches DFHack (the argument
        shape is fine; only a value inside it is invalid), so an
        overview.get action must be queued."""
        queue_db = tmp_path / "queue.sqlite3"
        fake_dfhack.queue_actions(make_ok_action(_OVERVIEW_JSON))
        app = _app(registry, roster, pool, queue_db)

        args = dict(_VALID_PROPOSE_ARGS)
        args["suggested_priority"] = 99  # out of the valid 1-7 range

        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("queue__propose", args)

        assert result.is_error is True
        text = "".join(b.text for b in result.content if b.type == "text")
        assert "suggested_priority" in text
        assert _dfqueue_store.load(queue_db) == []

    async def test_propose_when_dfhack_is_unreachable_is_refused_and_writes_nothing(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """Test named in the brief: DFHack unreachable at propose time means
        refused and nothing written."""
        queue_db = tmp_path / "queue.sqlite3"
        fake_dfhack.queue_actions(make_fail_action(1))  # CR_FAILURE on the overview.get call
        app = _app(registry, roster, pool, queue_db)

        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("queue__propose", _VALID_PROPOSE_ARGS)

        assert result.is_error is True
        text = "".join(b.text for b in result.content if b.type == "text")
        assert "DFHack" in text
        assert _dfqueue_store.load(queue_db) == []

    async def test_architect_calling_queue_rule_is_refused_by_roster_check(
        self, registry, roster, pool, fake_dfhack
    ):
        """Test named in the brief: architect calling queue.rule is refused
        by Roster.check -- before the native handler ever runs, so no
        DFHack call happens either, matching test 2's DFHack-side-effect
        proof for the DFHack-tool case."""
        app = _app(registry, roster, pool)
        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            result = await session.call_tool("queue__rule", _VALID_RULE_ARGS | {"proposal_id": "proposal-0001"})
        assert result.is_error is True
        assert fake_dfhack.received_requests == []

    async def test_rule_on_a_nonexistent_proposal_is_refused(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """Test named in the brief: a ruling on a nonexistent proposal is
        refused."""
        queue_db = tmp_path / "queue.sqlite3"
        fake_dfhack.queue_actions(make_ok_action(_OVERVIEW_JSON))
        app = _app(registry, roster, pool, queue_db)

        async with mcp_session(app, OVERSEER_TOKEN) as session:
            result = await session.call_tool(
                "queue__rule", _VALID_RULE_ARGS | {"proposal_id": "proposal-9999"}
            )

        assert result.is_error is True
        text = "".join(b.text for b in result.content if b.type == "text")
        assert "does not refer to an existing proposal" in text
        assert _dfqueue_store.load(queue_db) == []

    async def test_pending_returns_xml_and_drops_a_proposal_once_ruled(
        self, registry, roster, pool, fake_dfhack, tmp_path
    ):
        """Test named in the brief: queue.pending returns XML and drops a
        proposal once ruled."""
        queue_db = tmp_path / "queue.sqlite3"
        fake_dfhack.queue_actions(
            make_ok_action(_OVERVIEW_JSON),  # the propose call's own stamping
            make_ok_action(_OVERVIEW_JSON),  # the rule call's own stamping
        )
        # A fresh app per session throughout (module docstring, "Why every
        # test builds a fresh Server/app"); state persists across them via
        # the shared queue_db SQLite file, not via the app object.
        async with mcp_session(_app(registry, roster, pool, queue_db), ARCHITECT_TOKEN) as session:
            propose_result = await session.call_tool("queue__propose", _VALID_PROPOSE_ARGS)
        proposal_id = propose_result.structured_content["id"]

        async with mcp_session(_app(registry, roster, pool, queue_db), OVERSEER_TOKEN) as session:
            pending_before = await session.call_tool("queue__pending", {})
        text_before = "".join(b.text for b in pending_before.content if b.type == "text")
        assert proposal_id in text_before
        assert text_before.startswith("<proposal ")
        assert pending_before.structured_content == {"count": 1, "proposal_ids": [proposal_id]}

        async with mcp_session(_app(registry, roster, pool, queue_db), OVERSEER_TOKEN) as session:
            rule_result = await session.call_tool(
                "queue__rule", _VALID_RULE_ARGS | {"proposal_id": proposal_id}
            )
            assert rule_result.is_error is False
            pending_after = await session.call_tool("queue__pending", {})

        assert pending_after.structured_content == {"count": 0, "proposal_ids": []}
        text_after = "".join(b.text for b in pending_after.content if b.type == "text")
        assert proposal_id not in text_after

    async def test_queue_call_is_logged(self, registry, roster, pool, fake_dfhack, tmp_path, caplog):
        """Test named in the brief: the queue call is logged, through the
        same _on_call_tool wrapper as every other tool, and never with the
        bearer token."""
        caplog.set_level(logging.INFO, logger="dfmcp.calls")
        queue_db = tmp_path / "queue.sqlite3"
        fake_dfhack.queue_actions(make_ok_action(_OVERVIEW_JSON))
        app = _app(registry, roster, pool, queue_db)

        async with mcp_session(app, ARCHITECT_TOKEN) as session:
            await session.call_tool("queue__propose", _VALID_PROPOSE_ARGS)

        records = [r for r in caplog.records if r.name == "dfmcp.calls"]
        assert len(records) == 1
        assert ARCHITECT_TOKEN not in records[0].getMessage()
        line = json.loads(records[0].getMessage())
        assert line["tool"] == "queue__propose" and line["tool_id"] == "queue.propose"
        assert line["is_error"] is False
        assert line["role"] == "architect"


# ==========================================================================
# Config
# ==========================================================================


class TestServerConfig:
    def test_bind_host_is_required(self):
        with pytest.raises(ConfigError):
            config_from_env({})

    def test_bind_host_must_not_be_0_0_0_0(self):
        with pytest.raises(ConfigError):
            ServerConfig(bind_host="0.0.0.0", queue_db="test.sqlite3")

    def test_queue_db_is_required(self):
        """Added handoffs/2026-09-15-queue-into-dfmcp.md: same treatment as
        bind_host -- no default, because the in-tree default
        (dfqueue/<fort>.sqlite3) must never be clobberable by a code
        redeploy."""
        with pytest.raises(ConfigError):
            config_from_env({"MCP_SERVER_BIND_HOST": "100.64.0.9"})

    def test_valid_env_produces_expected_config(self):
        config = config_from_env(
            {
                "MCP_SERVER_BIND_HOST": "100.64.0.9",
                "MCP_SERVER_QUEUE_DB": "/var/lib/dfmcp/uniboslan.sqlite3",
                "MCP_SERVER_BIND_PORT": "9443",
                "MCP_SERVER_DFHACK_HOST": "127.0.0.1",
                "MCP_SERVER_DFHACK_PORT": "5001",
                "MCP_SERVER_POOL_SIZE": "8",
            }
        )
        assert config == ServerConfig(
            bind_host="100.64.0.9",
            queue_db="/var/lib/dfmcp/uniboslan.sqlite3",
            bind_port=9443,
            dfhack_host="127.0.0.1",
            dfhack_port=5001,
            pool_size=8,
        )

    def test_missing_optional_fields_fall_back_to_defaults(self):
        config = config_from_env({
            "MCP_SERVER_BIND_HOST": "100.64.0.9",
            "MCP_SERVER_QUEUE_DB": "/var/lib/dfmcp/uniboslan.sqlite3",
        })
        assert config == ServerConfig(
            bind_host="100.64.0.9", queue_db="/var/lib/dfmcp/uniboslan.sqlite3",
        )

    def test_non_integer_port_is_a_config_error(self):
        with pytest.raises(ConfigError):
            config_from_env({
                "MCP_SERVER_BIND_HOST": "100.64.0.9",
                "MCP_SERVER_QUEUE_DB": "test.sqlite3",
                "MCP_SERVER_BIND_PORT": "not-a-port",
            })

    def test_zero_pool_size_is_a_config_error(self):
        with pytest.raises(ConfigError):
            config_from_env({
                "MCP_SERVER_BIND_HOST": "100.64.0.9",
                "MCP_SERVER_QUEUE_DB": "test.sqlite3",
                "MCP_SERVER_POOL_SIZE": "0",
            })
