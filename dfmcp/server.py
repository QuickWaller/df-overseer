"""The MCP transport: the HTTP endpoint that ties registry.py, roles.py,
tools.py, auth.py and dfhack_client.py together into an actual MCP server.

Everything this module needs was already built as a pure, transport-free
function of files in this repo -- see dfmcp/README.md. This is the one
module in the package that imports the MCP SDK, and it exists to do exactly
one job per caller request: resolve who is calling, ask dfmcp.tools for
that role's own tool list or check a call against dfmcp.roles.Roster, then
run it against DFHack through dfmcp.dfhack_client and hand back the parsed
result. Design settled by research/2026-09-12-mcp-server-stack.md and
research/2026-09-12-openclaw-mcp-auth.md -- built to those, not re-derived
here; see this module's own corrections below where building against them
found something they did not.

## THE NAMING TRAP

**`mcp` (imported below, unqualified) is the MCP SDK.** `dfmcp` (this
package) is ours. Both were named `mcp` until 2026-09-12; a local `mcp/`
directory used to shadow the SDK for anything running with the repo root on
`sys.path`. If an import here ever needs a `sys.path` hack to resolve, that
is the collision coming back -- stop and report, per the handoff brief.

## Low-level Server, not FastMCP/MCPServer

Per-caller `tools/list` is only reachable where per-request identity lives;
`mcp.server.fastmcp.FastMCP`/`mcp.server.mcpserver.MCPServer`'s
`list_tools()` takes no arguments and returns one static list to every
caller. `mcp.server.lowlevel.server.Server` is built with `on_list_tools`/
`on_call_tool` callbacks that receive the caller's own per-request context
directly (2.x shape; confirmed against the installed 2.2.0 source, not just
read from the brief).

## A correction to research/2026-09-12-mcp-server-stack.md's own proposed
## workaround

The brief flagged (§2, "not verified") that `AuthSettings.issuer_url` is a
required field even in a resource-server-only configuration with no OAuth
authorization server, and proposed skipping `AuthSettings` entirely,
hand-assembling `BearerAuthBackend` + `AuthContextMiddleware` directly around
whatever ASGI app `Server.streamable_http_app()` produces.

**Built against the real 2.2.0 source, that workaround is wrong, not just
unverified, for a reason more specific than "untested": doing it naively
would silently break the lifespan protocol.** `streamable_http_app()`'s own
composition wraps `RequireAuthMiddleware` around only the one `/mcp` Route's
*endpoint*, never around the whole `Starlette` app -- the app's `lifespan=`
callable (which starts/stops `StreamableHTTPSessionManager`) is never passed
through any auth middleware at all. `RequireAuthMiddleware` itself does not
special-case `scope["type"] == "lifespan"` the way Starlette's own
`AuthenticationMiddleware` does (confirmed by reading both directly): a
hand-rolled version that wraps the *entire* ASGI callable, lifespan
included, would intercept the server's own startup/shutdown scope, find no
`scope["user"]` (there is no HTTP connection to authenticate), and try to
send an HTTP-shaped 401 response down a lifespan channel that expects
`lifespan.startup.complete`/`lifespan.shutdown.complete` messages instead --
breaking every server start.

**The actual, much smaller fix**: `AuthSettings` also requires
`resource_server_url` (a second required field the brief's own read did not
name -- confirmed by construction: `AuthSettings(issuer_url=...)` alone
raises a pydantic `ValidationError` for the missing field). Neither field is
ever dereferenced unless something else is also configured that this design
never sets: `issuer_url` is only read by `create_auth_routes`, which only
runs `if auth_server_provider` (never supplied here -- there is no OAuth
authorization server); `resource_server_url` only grows a real,
harmless-but-present `.well-known/oauth-protected-resource`-style metadata
route (`create_protected_resource_routes`), and is only used to scope a
token to a specific audience via `BearerAuthBackend`'s
`resource_server_url=` kwarg when `AuthSettings.validate_token_resource` is
also set, which it is not, by default, here. So: pass two syntactically
valid but semantically inert placeholder URLs, get the SDK's own (correctly
lifespan-safe) middleware composition for free, and never write a
`sys.path`-adjacent, hand-rolled version of what the SDK already does
correctly. See `_PLACEHOLDER_ISSUER_URL`/`_PLACEHOLDER_RESOURCE_URL` and
`build_asgi_app` below.

## Denials: an MCP tool result, not a protocol error

Per the brief's §5, a `Roster.check` denial becomes
`types.CallToolResult(isError=True, content=[TextContent(text=reason)])`,
never a raised `McpError`/protocol-level error -- the latter is a different
wire shape the reference client turns into a raised Python exception in the
*calling* code, not something a host necessarily threads back into what the
model sees. An unresolvable tool name and a bad-argument `ArgumentError`
from `dfmcp.tools.argv_for_call` get the identical treatment: both are
"this specific call cannot proceed, here is why", exactly the shape a tool
result (as opposed to a broken request) is for.

## What this module deliberately does not do

- No token issuance, no OAuth authorization server, no TLS termination
  (that is the tailnet's job, not this server's -- see
  docs/AGENT-ARCHITECTURE.md §13).
- No caching or hot-reload of the registry/roster: both are loaded once at
  startup, matching dfmcp.registry/dfmcp.roles's own "load once" contract.
- No retry/backoff around DFHack calls beyond what `DFHackConnectionPool`
  already does (self-healing reconnection on next use, per
  dfmcp/dfhack_client.py). A call made while DFHack is down still fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from pydantic import AnyHttpUrl

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel.server import Server
import mcp.types as types

from .auth import DEFAULT_ENV_PATH as DEFAULT_TOKEN_ENV_PATH
from .auth import _read_dotenv, load_role_tokens, resolve
from .dfhack_client import (
    DFHackCallError,
    DFHackConnectionError,
    DFHackConnectionPool,
    DFHackProtocolError,
)
from . import doctrine_tools, queue_tools
from .registry import Registry, load_registry
from .roles import Roster, load_roster
from .tools import ArgumentError, argv_for_call, build_tool_names, tool_definitions

# Never dereferenced as a real network address -- see this module's
# docstring for exactly which code paths would need to read them (neither
# does, given this design's config: no auth_server_provider, no
# validate_token_resource). Kept as recognisably-fake, non-resolving
# addresses on purpose, not because they will ever be fetched.
_PLACEHOLDER_ISSUER_URL = AnyHttpUrl("https://df-overseer.invalid/issuer")
_PLACEHOLDER_RESOURCE_URL = AnyHttpUrl("https://df-overseer.invalid/resource")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


class ConfigError(Exception):
    """A required server config value is missing or invalid.

    Matching RegistryError/RoleValidationError/AuthConfigError's own style:
    a hard failure at startup, never a silent fallback to something that
    could accidentally be public.
    """


@dataclass(frozen=True)
class ServerConfig:
    """Everything the transport needs to know that is not the registry,
    the roster, or a role's tokens.

    `bind_host` has **no default**, deliberately: docs/AGENT-ARCHITECTURE.md
    §13 requires the bind address to be tailnet-only and explicit, "with no
    default that could accidentally be public." A missing value is a
    ConfigError, never a silent fall-through to "0.0.0.0" or any other
    default.

    `queue_db` also has **no default**, added
    `handoffs/2026-09-15-queue-into-dfmcp.md`, same style and same reason:
    `dfqueue.store`'s own `default_path()` sits inside the code tree
    (`dfqueue/<fort>.sqlite3`), and a code redeploy on VM 103 must never be
    able to clobber live queue data by resolving to a path relative to
    wherever the checkout happens to be. A missing value is a ConfigError,
    never a silent fall-through to that in-tree default.

    `doctrine_path`, added `handoffs/2026-09-19-get-doctrine-tool.md`, is
    the opposite case from `queue_db`: `doctrine/seed.yaml` is checked into
    this repo (read-only from the server's point of view) and travels with
    the code on every deploy, so an in-tree default is safe here the same
    way `registry.DEFAULT_TOOLS_YAML` already is -- see
    `dfmcp/doctrine_tools.py`'s module docstring, "Where the file lives at
    runtime".
    """

    bind_host: str
    queue_db: str
    bind_port: int = 8443
    dfhack_host: str = "127.0.0.1"
    dfhack_port: int = 5000
    pool_size: int = 4
    doctrine_path: str = str(doctrine_tools.DEFAULT_DOCTRINE_PATH)

    def __post_init__(self) -> None:
        if not self.bind_host or not self.bind_host.strip():
            raise ConfigError(
                "bind_host must be set explicitly -- there is no default, because a "
                "default here could accidentally end up public. Set MCP_SERVER_BIND_HOST."
            )
        if self.bind_host == "0.0.0.0":
            raise ConfigError(
                "bind_host must not be 0.0.0.0 -- the MCP server binds the tailnet "
                "interface's own address only, per docs/AGENT-ARCHITECTURE.md §13."
            )
        if not self.queue_db or not self.queue_db.strip():
            raise ConfigError(
                "queue_db must be set explicitly -- there is no default, because the "
                "in-tree default (dfqueue/<fort>.sqlite3) must never be clobberable by a "
                "code redeploy. Set MCP_SERVER_QUEUE_DB."
            )


_ENV_KEYS = {
    "bind_host": "MCP_SERVER_BIND_HOST",
    "queue_db": "MCP_SERVER_QUEUE_DB",
    "bind_port": "MCP_SERVER_BIND_PORT",
    "dfhack_host": "MCP_SERVER_DFHACK_HOST",
    "dfhack_port": "MCP_SERVER_DFHACK_PORT",
    "pool_size": "MCP_SERVER_POOL_SIZE",
    "doctrine_path": "MCP_SERVER_DOCTRINE_PATH",
}

_INT_FIELDS = {"bind_port", "dfhack_port", "pool_size"}
_REQUIRED_FIELDS = {"bind_host", "queue_db"}


def config_from_env(env: Mapping[str, str]) -> ServerConfig:
    """Build a ServerConfig from a plain {name: value} mapping (e.g.
    os.environ, or a dict merged from a .env file). Pure and dependency-free
    so tests can exercise it with a plain dict -- no file or real
    environment variable required.

    Raises ConfigError for a missing bind_host, an out-of-range int field,
    or 0.0.0.0. Every other field falls back to ServerConfig's own default
    when absent.
    """
    kwargs: Dict[str, Any] = {}
    for field_name, env_key in _ENV_KEYS.items():
        raw = env.get(env_key)
        if raw is None or raw.strip() == "":
            if field_name in _REQUIRED_FIELDS:
                raise ConfigError(f"{env_key} is required and was not set")
            continue
        if field_name in _INT_FIELDS:
            try:
                kwargs[field_name] = int(raw)
            except ValueError:
                raise ConfigError(f"{env_key}={raw!r} is not a valid integer") from None
        else:
            kwargs[field_name] = raw
    for field_name in _INT_FIELDS:
        if field_name in kwargs and kwargs[field_name] < 1:
            raise ConfigError(f"{_ENV_KEYS[field_name]} must be at least 1, got {kwargs[field_name]}")
    return ServerConfig(**kwargs)


def load_config(path: Path = DEFAULT_TOKEN_ENV_PATH) -> ServerConfig:
    """Load config for the real entry point: `.env` merged under the real
    process environment (a real env var wins over a `.env` entry, matching
    the common convention). Reuses dfmcp.auth's own `.env` reader rather
    than a third copy of the same parsing logic -- see dfmcp/README.md's
    note on why `scripts/pve.py`'s version is not imported directly.
    """
    import os

    env: Dict[str, str] = dict(_read_dotenv(Path(path))) if Path(path).is_file() else {}
    env.update(os.environ)
    return config_from_env(env)


# --------------------------------------------------------------------------
# Auth: mapping a bearer token to a role, at the SDK's own seam
# --------------------------------------------------------------------------


class RoleTokenVerifier(TokenVerifier):
    """Resolves a bearer token to a role via dfmcp.auth.resolve, and hands
    the SDK back an AccessToken with the role name as `client_id` -- exactly
    where docs/AGENT-ARCHITECTURE.md §13 says role identity belongs: a
    credential, not a claim.

    Returns None (never an empty/anonymous AccessToken) for anything that
    does not resolve, so an unknown or malformed token is rejected by the
    SDK's own RequireAuthMiddleware at the transport, before any handler of
    ours ever runs -- never passed through as an anonymous caller.
    """

    def __init__(self, tokens: Mapping[str, str]) -> None:
        self._tokens = tokens

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        role = resolve(token, self._tokens)
        if role is None:
            return None
        return AccessToken(token=token, client_id=role, scopes=[role], expires_at=None, resource=None)


def _current_role() -> Optional[str]:
    """The calling role for the in-flight request, read off the SDK's own
    contextvar (populated by AuthContextMiddleware, itself only reachable
    once BearerAuthBackend/RoleTokenVerifier accepted the token -- see
    module docstring for why `auth=`/`token_verifier=` must be supplied
    together to actually wire that middleware in). None only if this is
    somehow reached without going through RequireAuthMiddleware at all,
    which should not be possible via the transport this module builds.
    """
    access_token = get_access_token()
    return access_token.client_id if access_token is not None else None


# --------------------------------------------------------------------------
# The low-level Server: tools/list and tools/call, per caller role
# --------------------------------------------------------------------------


def _tool_result_error(reason: str) -> types.CallToolResult:
    """The one denial/failure shape this module ever returns: a normal MCP
    tool result carrying isError=True and the reason as plain text -- never
    a protocol-level error. See module docstring §"Denials"."""
    return types.CallToolResult(content=[types.TextContent(type="text", text=reason)], isError=True)


# --------------------------------------------------------------------------
# The call log: one JSON object per tools/call
# --------------------------------------------------------------------------

# Added 2026-09-14 after the second architect charter run: 3 of its 14 calls
# came back isError and nothing anywhere recorded which ones or with what
# arguments (headless `openclaw agent exec` keeps no transcript; uvicorn's
# access log has HTTP status only). docs/AGENT-ARCHITECTURE.md §10 already
# assumes this exists: friction.jsonl is "mechanical, from the tool-call
# log". One line per call, correlatable by MCP session id and JSON-RPC
# request id. It records the role, never the token; arguments are logged
# as given because no tool argument carries a secret (they are landmark
# names, sizes, levels and blueprint filenames).
CALL_LOG = logging.getLogger("dfmcp.calls")
_CALL_LOG_ERROR_CHARS = 500


def _call_log_line(
    ctx: ServerRequestContext,
    params: types.CallToolRequestParams,
    tool_id: Optional[str],
    started: float,
    *,
    is_error: bool,
    error: Optional[str],
    result_chars: Optional[int],
) -> Dict[str, Any]:
    request = getattr(ctx, "request", None)
    headers = getattr(request, "headers", None)
    client = getattr(request, "client", None)
    return {
        "event": "tools/call",
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "session_id": headers.get("mcp-session-id") if headers is not None else None,
        "request_id": ctx.request_id,
        "client": client.host if client is not None else None,
        "role": _current_role(),
        "tool": params.name,
        "tool_id": tool_id,
        "arguments": dict(params.arguments or {}),
        "is_error": is_error,
        "error": error[:_CALL_LOG_ERROR_CHARS] if error else None,
        "result_chars": result_chars,
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
    }


def _configure_call_log() -> None:
    """Send the call log to stderr as bare JSON lines. Under systemd that is
    journald, so the log reads back as JSONL with
    `journalctl -u dfmcp-server.service -o cat | grep '"event": "tools/call"'`.
    Only `main()` calls this, so tests see the records through pytest's own
    capture instead."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    CALL_LOG.addHandler(handler)
    CALL_LOG.setLevel(logging.INFO)
    CALL_LOG.propagate = False


def build_mcp_server(
    registry: Registry, roster: Roster, pool: DFHackConnectionPool, queue_db_path: Path,
    doctrine_path: Path = doctrine_tools.DEFAULT_DOCTRINE_PATH,
) -> Server:
    """Build the low-level Server, wired to this registry/roster/pool.

    `tools/list` and `tools/call` are the only two request kinds this
    server answers; everything else is the SDK's own default handling
    (ping, etc).

    `queue_db_path`, added `handoffs/2026-09-15-queue-into-dfmcp.md`: the
    SQLite file `dfmcp.queue_tools`' native tools (`queue.propose` etc.)
    read and write, via `dfqueue.store`. Passed through from
    `ServerConfig.queue_db` (`main()`/`_serve()` below); a test builds the
    server with its own throwaway path (`dfmcp/tests/test_server.py`).

    `doctrine_path`, added `handoffs/2026-09-19-get-doctrine-tool.md`: the
    YAML file `dfmcp.doctrine_tools`'s native `doctrine.get` reads.
    Defaults to the in-tree `doctrine/seed.yaml` (see that module's
    docstring for why a default is safe here unlike `queue_db_path` above);
    passed through from `ServerConfig.doctrine_path` in real use.

    Also builds this server's one `queue_write_lock` (Phase A review,
    2026-09-15): an `asyncio.Lock`, created fresh here rather than as a
    `dfmcp.queue_tools` module-level global, because an `asyncio.Lock`
    binds to whichever event loop first acquires it and raises if reused
    from a different one -- a module-level singleton would break the
    moment more than one event loop (a real server restart, or one test
    after another) ever touched it. One lock per built `Server`, matching
    how `pool`/`registry`/`roster` are already scoped. See
    `dfmcp/queue_tools.py`'s own docstring, "SQLite runs off the event
    loop, and writes are serialised", for why this exists and why it is
    held only around `store.append`, never around the DFHack stamping call.
    """
    id_to_name, name_to_id = build_tool_names(registry)
    queue_write_lock = asyncio.Lock()

    async def _call_dfhack(tool_id: str, arguments: Mapping[str, Any]) -> Any:
        """The one DFHack call `dfmcp.queue_tools` needs (`overview.get`, to
        stamp a queue record's `cycle`/`snapshot`), reusing this same
        registry/pool rather than a second RPC path. Deliberately bypasses
        `Roster.check` -- see `dfmcp/queue_tools.py`'s module docstring,
        "The internal DFHack call bypasses Roster.check", for why that is
        the server's own bookkeeping rather than a call made on the
        caller's behalf. Raises DFHackCallError/DFHackConnectionError/
        DFHackProtocolError/json.JSONDecodeError -- queue_tools.py catches
        all of those generically via `except Exception`, matching how it is
        already agnostic about dfhack_client's specific exception types.
        """
        tool = registry.get(tool_id)
        argv = argv_for_call(tool, arguments)
        raw = await pool.run_command(argv[0], argv[1:])
        stripped = raw.strip()
        if not stripped:
            return None
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and set(parsed) == {"error"} and isinstance(parsed["error"], str):
            raise DFHackCallError(parsed["error"])
        return parsed

    async def _on_list_tools(
        ctx: ServerRequestContext, params: Optional[types.PaginatedRequestParams]
    ) -> types.ListToolsResult:
        role = _current_role()
        if role is None:
            # Should not be reachable: RequireAuthMiddleware gates every
            # request before it gets here. Fail closed, not open, if it
            # somehow is.
            return types.ListToolsResult(tools=[])
        defs = tool_definitions(registry, roster, role)
        tools = [
            types.Tool(name=d["name"], description=d["description"], inputSchema=d["inputSchema"])
            for d in defs
        ]
        return types.ListToolsResult(tools=tools)

    async def _handle_call_tool(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        role = _current_role()
        if role is None:
            return _tool_result_error("no authenticated role for this request")

        tool_id = name_to_id.get(params.name)
        if tool_id is None:
            return _tool_result_error(f"unknown tool {params.name!r}")

        # The actual boundary: Roster.check is consulted here regardless of
        # what tools/list showed this caller. A client that calls a tool it
        # was never listed is refused the same way a client that never
        # called tools/list at all would be -- listing is never itself the
        # enforcement (research doc §3; docs/AGENT-ARCHITECTURE.md §13
        # requirement 1).
        allowed, reason = roster.check(role, tool_id)
        if not allowed:
            return _tool_result_error(reason)

        tool = registry.get(tool_id)

        if getattr(tool, "native", False):
            # Not a DFHack command at all, so argv_for_call/pool.run_command
            # below (built for a positional CLI signature) do not apply.
            # Routed by which native module actually owns this id -- added
            # handoffs/2026-09-19-get-doctrine-tool.md alongside
            # dfmcp.queue_tools's own queue.propose/pass/rule/pending, which
            # this branch served exclusively before. See dfmcp/queue_tools.py
            # and dfmcp/doctrine_tools.py's own module docstrings.
            try:
                if tool_id in queue_tools.NATIVE_TOOL_IDS:
                    text, structured = await queue_tools.call(
                        tool_id, role, params.arguments or {},
                        db_path=queue_db_path, call_dfhack=_call_dfhack,
                        write_lock=queue_write_lock,
                    )
                elif tool_id in doctrine_tools.NATIVE_TOOL_IDS:
                    text, structured = await doctrine_tools.call(
                        tool_id, role, params.arguments or {},
                        doctrine_path=doctrine_path,
                    )
                else:  # pragma: no cover -- every native id belongs to one of the above
                    raise AssertionError(f"native tool id {tool_id!r} has no owning module")
            except queue_tools.QueueToolError as exc:
                return _tool_result_error(str(exc))
            except doctrine_tools.DoctrineToolError as exc:
                return _tool_result_error(str(exc))
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
                isError=False,
            )

        try:
            argv = argv_for_call(tool, params.arguments or {})
        except ArgumentError as exc:
            return _tool_result_error(str(exc))

        command, arguments = argv[0], argv[1:]
        try:
            raw = await pool.run_command(command, arguments)
        except DFHackCallError as exc:
            return _tool_result_error(str(exc))
        except DFHackConnectionError as exc:
            return _tool_result_error(f"DFHack is unreachable: {exc}")
        except DFHackProtocolError as exc:
            return _tool_result_error(f"DFHack protocol error: {exc}")

        text = raw
        structured: Any = None
        stripped = raw.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return _tool_result_error(
                    f"{tool_id} printed output that is not valid JSON: {raw!r}"
                )
            # Bug found on VM 103's first live smoke test, 2026-09-14: most
            # real read tools print a bare JSON array (confirmed live via
            # `df-overseer-landmarks.lua list`; see dfmcp/README.md's "Call
            # results" section for the full list), not an object. Passing
            # a list straight through as structuredContent worked in this
            # module's own tests, whose fake payloads all happened to be
            # objects, but fails against a real client: mcp_types'
            # CallToolResult.structured_content is `dict[str, Any] | None`
            # through protocol 2025-11-25 (only 2026-07-28 allows any JSON
            # value), so the SDK's runner rejects a bare list at
            # serialization with a protocol-level MCPError, not a tool
            # error -- exactly what this design exists to avoid. Rule,
            # applied regardless of negotiated protocol version so every
            # client sees the same shape: a parsed dict passes through
            # unchanged; anything else (list, number, string, bool, null)
            # is wrapped as {"result": <value>}. The text content block
            # always keeps the raw JSON exactly as printed, either way.
            # A script reporting its own failure prints exactly
            # {"error": "<message>"} (every df-overseer-*.lua uses that one
            # shape: landmark not found, a level off the map). Found live on
            # VM 103 2026-09-14: those used to reach the client as a normal
            # isError=False result, so a model could read "outside the map"
            # as data rather than as a failed call. Only that exact shape
            # counts; an object that merely has an error-ish field alongside
            # real data (e.g. `dig`'s `quickfort_error`) is still a result.
            if (
                isinstance(parsed, dict)
                and set(parsed) == {"error"}
                and isinstance(parsed["error"], str)
            ):
                return _tool_result_error(parsed["error"])
            if isinstance(parsed, dict):
                structured = parsed
            else:
                structured = {"result": parsed}

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=structured,
            isError=False,
        )

    async def _on_call_tool(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        # Wraps every return path of _handle_call_tool (refusals, argument
        # errors, DFHack failures, script errors, results), so no call can
        # leave the server without a log line.
        started = time.monotonic()
        tool_id = name_to_id.get(params.name)
        try:
            result = await _handle_call_tool(ctx, params)
        except BaseException as exc:
            line = _call_log_line(
                ctx, params, tool_id, started,
                is_error=True, error=f"unhandled {type(exc).__name__}: {exc}", result_chars=None,
            )
            CALL_LOG.info(json.dumps(line, default=str, sort_keys=True))
            raise
        text = "".join(block.text for block in result.content if getattr(block, "type", None) == "text")
        line = _call_log_line(
            ctx, params, tool_id, started,
            is_error=bool(result.is_error), error=text if result.is_error else None, result_chars=len(text),
        )
        CALL_LOG.info(json.dumps(line, default=str, sort_keys=True))
        return result

    return Server(
        name="df-overseer",
        version="0.1.0",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


# --------------------------------------------------------------------------
# The ASGI app
# --------------------------------------------------------------------------


def build_asgi_app(server: Server, tokens: Mapping[str, str], bind_host: str):
    """The Starlette ASGI app: streamable HTTP transport, bearer-token auth
    wired in via the SDK's own (lifespan-safe) composition. See this
    module's docstring for exactly why `auth=` and `token_verifier=` are
    both required together, and why the two placeholder URLs inside
    `auth=` are never dereferenced by anything this design configures.

    `bind_host` is passed through to `streamable_http_app` for its own
    loopback-vs-not DNS-rebinding-protection default (2.2.0 auto-enables it
    only when `host` is a loopback address) -- it does not itself bind a
    socket; that is uvicorn's job in `main()` below.
    """
    verifier = RoleTokenVerifier(tokens)
    auth_settings = AuthSettings(
        issuer_url=_PLACEHOLDER_ISSUER_URL,
        resource_server_url=_PLACEHOLDER_RESOURCE_URL,
        # Explicit rather than left to default: this design has no resource
        # indicator to check a token against (RoleTokenVerifier's
        # AccessToken always carries resource=None), so audience validation
        # has nothing to validate. The SDK warns that the unset default
        # will itself change to True in 3.0 -- set explicitly so upgrading
        # the pin later cannot silently start rejecting every token.
        validate_token_resource=False,
    )
    return server.streamable_http_app(host=bind_host, auth=auth_settings, token_verifier=verifier)


# --------------------------------------------------------------------------
# Entry point -- not run by anything in this repo yet. See
# infra/dfmcp-server.service and this stream's report for the exact,
# un-run command that would start this for real.
# --------------------------------------------------------------------------


async def _serve(config: ServerConfig, registry: Registry, roster: Roster, tokens: Mapping[str, str]) -> None:
    import uvicorn

    pool = DFHackConnectionPool(host=config.dfhack_host, port=config.dfhack_port, size=config.pool_size)
    await pool.start()
    try:
        server = build_mcp_server(
            registry, roster, pool, Path(config.queue_db), Path(config.doctrine_path),
        )
        app = build_asgi_app(server, tokens, config.bind_host)
        uvicorn_config = uvicorn.Config(app, host=config.bind_host, port=config.bind_port, log_level="info")
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()
    finally:
        await pool.close()


def main() -> None:
    """Not invoked by anything in this repo or on any VM yet -- this
    stream was barred from deploying. See the report for the exact
    `python -m dfmcp.server` invocation and the undeployed systemd unit
    this would run under."""
    _configure_call_log()
    config = load_config()
    registry = load_registry(native_tools={**queue_tools.NATIVE_TOOLS, **doctrine_tools.NATIVE_TOOLS})
    roster = load_roster(registry)
    tokens = load_role_tokens(roster)
    asyncio.run(_serve(config, registry, roster, tokens))


if __name__ == "__main__":
    main()
