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
correctly. See `_AUTH_SETTINGS` below.

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
from dataclasses import dataclass
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
from .registry import Registry, load_registry
from .roles import Roster, load_roster
from .tools import ArgumentError, argv_for_call, build_tool_names, tool_definitions

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

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
    """

    bind_host: str
    bind_port: int = 8443
    dfhack_host: str = "127.0.0.1"
    dfhack_port: int = 5000
    pool_size: int = 4

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


_ENV_KEYS = {
    "bind_host": "MCP_SERVER_BIND_HOST",
    "bind_port": "MCP_SERVER_BIND_PORT",
    "dfhack_host": "MCP_SERVER_DFHACK_HOST",
    "dfhack_port": "MCP_SERVER_DFHACK_PORT",
    "pool_size": "MCP_SERVER_POOL_SIZE",
}

_INT_FIELDS = {"bind_port", "dfhack_port", "pool_size"}


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
            if field_name == "bind_host":
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


def build_mcp_server(registry: Registry, roster: Roster, pool: DFHackConnectionPool) -> Server:
    """Build the low-level Server, wired to this registry/roster/pool.

    `tools/list` and `tools/call` are the only two request kinds this
    server answers; everything else is the SDK's own default handling
    (ping, etc).
    """
    id_to_name, name_to_id = build_tool_names(registry)

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

    async def _on_call_tool(
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
                structured = json.loads(stripped)
            except json.JSONDecodeError:
                return _tool_result_error(
                    f"{tool_id} printed output that is not valid JSON: {raw!r}"
                )

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=structured,
            isError=False,
        )

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
        server = build_mcp_server(registry, roster, pool)
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
    config = load_config()
    registry = load_registry()
    roster = load_roster(registry)
    tokens = load_role_tokens(roster)
    asyncio.run(_serve(config, registry, roster, tokens))


if __name__ == "__main__":
    main()
