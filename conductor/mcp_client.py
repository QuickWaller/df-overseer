"""The conductor's own MCP client: how the conductor calls `dfmcp` on VM 103
as the `conductor` role (`MCP_ROLE_TOKEN_CONDUCTOR`) -- the only token this
package ever holds directly. Every other role's own token belongs to that
role's own `openclaw` run (`conductor/runner.py`'s pinned per-role configs),
never to this client.

`ToolCaller` is the interface the rest of this package depends on
(`call_tool(tool_id, arguments) -> parsed result`); `conductor/cycle.py` and
every other module here talk to it, never to the MCP SDK directly.
`StreamableHTTPMCPClient` is the real implementation, built on the same MCP
SDK `dfmcp/server.py` already depends on (`mcp.client.streamable_http`,
`mcp.client.session`) -- **never exercised against a real server in this
stream** (hard line: no VM). `FakeToolCaller` is what every other test in
this package uses instead.

`dfmcp.tools.build_tool_names`'s own id -> MCP-tool-name scheme
(`"clock.status"` -> `"clock__status"`, `"."` replaced with `"__"`) is
re-implemented here by the same pure rule (`tool_name` below), never
imported from `dfmcp` directly: this package runs on a different host
(VM 106) and talks to `dfmcp` only over the wire, so importing its Python
package here would blur the exact host boundary
`docs/AGENT-ARCHITECTURE.md` §13 draws.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple, Union


class MCPToolError(Exception):
    """A tool call was refused (`isError=True`) or the transport itself
    failed. Always carries the tool id and the reason text -- never a raw
    SDK exception leaking past this module's own boundary, matching
    `dfqueue`/`dfmcp`'s own "storage errors are refusals too" discipline
    applied here to the transport instead."""


def tool_name(tool_id: str) -> str:
    """`"clock.status"` -> `"clock__status"` -- the same rule
    `dfmcp.tools._tool_name` applies server-side. Re-implemented, not
    imported: see this module's own docstring for why."""
    return tool_id.replace(".", "__")


class ToolCaller(Protocol):
    async def call_tool(self, tool_id: str, arguments: Mapping[str, Any]) -> Any: ...


ResultOrFactory = Union[Any, Callable[[Mapping[str, Any]], Any]]


class FakeToolCaller:
    """Test double: a fixed `{tool_id: result}` map. A value may instead be
    a callable `(arguments) -> result` for a test that needs a different
    answer on successive calls (an advancing game tick, for instance) or
    that wants to assert on the arguments it was actually called with.
    Records every call made, in order."""

    def __init__(self, results: Optional[Dict[str, ResultOrFactory]] = None):
        self._results: Dict[str, ResultOrFactory] = dict(results or {})
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def set_result(self, tool_id: str, result: ResultOrFactory) -> None:
        self._results[tool_id] = result

    async def call_tool(self, tool_id: str, arguments: Mapping[str, Any]) -> Any:
        args = dict(arguments)
        self.calls.append((tool_id, args))
        if tool_id not in self._results:
            raise MCPToolError(f"FakeToolCaller: no result configured for {tool_id!r}")
        result = self._results[tool_id]
        return result(args) if callable(result) else result


class StreamableHTTPMCPClient:
    """The real implementation: one bearer-token-authenticated MCP session
    per call, over streamable HTTP, matching `dfmcp/server.py`'s own
    transport exactly (see that module's docstring, "Low-level Server, not
    FastMCP/MCPServer"). **Never opened against a real server in this
    stream** -- hard line: no VM.

    A short-lived session per call, not a held-open one, so a conductor
    restart or a `dfmcp-server` restart never leaves this side of the
    connection in a stale state to recover from; the cost (a fresh MCP
    handshake per tool call) is judged acceptable against the conductor's
    own cycle cadence, but this was **not measured live** -- flagged in
    this stream's report as a design point worth a second look once real
    cycle timing exists.
    """

    def __init__(self, url: str, token: str, *, timeout_seconds: float = 30.0):
        self.url = url
        self._token = token
        self.timeout_seconds = timeout_seconds

    async def call_tool(self, tool_id: str, arguments: Mapping[str, Any]) -> Any:
        # Imported lazily: every OTHER module in this package (policy,
        # triage, briefing, cursors, archive, runner) must import cleanly
        # with no MCP SDK installed at all -- matching how dfmcp/server.py
        # is the one module in ITS package that imports the SDK (see its
        # own docstring, "THE NAMING TRAP"/"Low-level Server"). Only this
        # class, and only this method, needs it.
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        name = tool_name(tool_id)
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with streamablehttp_client(self.url, headers=headers) as (read, write, _get_session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, dict(arguments))
        except MCPToolError:
            raise
        except Exception as exc:  # any SDK/transport failure: connection refused, timeout, protocol error
            raise MCPToolError(f"{tool_id}: dfmcp is unreachable: {type(exc).__name__}: {exc}") from exc

        if result.isError:
            text = "".join(
                block.text for block in result.content if getattr(block, "type", None) == "text"
            )
            raise MCPToolError(f"{tool_id}: {text}")

        if result.structuredContent is not None:
            return result.structuredContent

        # Every tool this role calls returns structuredContent per
        # dfmcp/server.py's own contract, so this branch should not be
        # reached live; kept as a defensive fallback (parse the text block
        # as JSON if it looks like it) rather than raising, since a missing
        # structuredContent is not itself evidence the call failed.
        text = "".join(
            block.text for block in result.content if getattr(block, "type", None) == "text"
        )
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
