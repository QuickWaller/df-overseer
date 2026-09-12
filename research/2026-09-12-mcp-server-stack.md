# MCP Server Stack: SDK, Auth, Per-Role Listing, Transport

Date: 2026-09-12
Scope: settle which SDK/protocol revision/transport df-overseer's MCP server should
be built on, how it sees a caller's bearer token, whether `tools/list` can differ
per role (Overseer/Architect/Consultant), the error path for a `Roster.check`
denial, what `research/2026-09-12-openclaw-primitives.md` already says about the
client side, and the deployment shape on VM 103. Read-only pass; nothing in the
repo was changed, no VM was touched.
Status: **verified against actual installed SDK source**, both the version
already present in this environment (`mcp` 1.27.1, pip-installed locally,
`fastmcp` 3.2.4 also present as an unrelated third-party package) and the
current PyPI release (`mcp` 2.2.0, installed into an isolated scratch directory
this session purely to read its source — not added to the repo or any shared
environment). Every claim below is confidence-flagged individually.

---

## TL;DR (answers, no evidence)

1. **Base SDK: the official `mcp` PyPI package, but target the 2.x line
   (`mcp>=2,<3`), not 1.x.** 1.x is now in security-fix-only maintenance mode.
   Current protocol revision per 2.x source is **2026-07-28**; per the
   1.27.1 copy actually installed in this environment it is **2025-11-25**
   (`DEFAULT_NEGOTIATED_VERSION` stays `2025-03-26` for back-compat clients in
   both). **Streamable HTTP** (not the older combined HTTP+SSE transport, not
   stdio) is the correct transport — stdio is a non-starter here since
   openclaw and the DF VM are different hosts.
2. **Per-request auth hook: yes, a real one.** `mcp.server.auth.provider.TokenVerifier`
   (`async def verify_token(token: str) -> AccessToken | None`) is a stable
   Protocol, unchanged in shape across 1.27.1 and 2.2.0. `AccessToken.client_id`
   is exactly where a role name belongs. Inside a handler, the verified identity
   reaches you either via `mcp.server.auth.middleware.auth_context.get_access_token()`
   (a contextvar, both versions) or, in 2.x specifically, as an explicit `ctx`
   argument the handler receives directly.
3. **THE CRUX — yes, per-caller `tools/list` is supported, but only via the
   low-level `Server`, not the high-level wrapper.** The low-level API resolves
   `tools/list` per request (1.x: a decorator whose handler runs inside a
   fresh `contextvars.ContextVar` set per request; 2.x: an explicit
   `on_list_tools=(ctx, params) -> ListToolsResult` callback that receives the
   per-request context as a normal argument, no contextvar needed). Either
   way: write a handler that reads the caller's role off the verified token and
   returns `Roster`-filtered tools. **The high-level convenience wrapper
   (`mcp.server.fastmcp.FastMCP` in 1.x, `mcp.server.mcpserver.MCPServer` in 2.x)
   does not do this out of the box** — its `list_tools()` takes no arguments and
   returns one static list for every caller — so "one server instance per role"
   is not needed as a fallback; it's an unnecessary workaround for a limitation
   that doesn't apply once you drop to the low-level API.
4. **Recommendation: the low-level `Server` API, not FastMCP/MCPServer.**
   Cost: you write the ASGI wiring (`Server.streamable_http_app(...)`, already
   provided as a method) and the `tools/list`/`tools/call` handlers yourself,
   instead of getting them auto-generated from `@mcp.tool()`-decorated Python
   functions. Given per-role filtering is the entire point of this server, that
   cost is unavoidable either way — FastMCP/MCPServer would have to be
   subclassed and its `list_tools` overridden to get the same behavior, which
   is strictly more code than using the low-level API directly.
5. **Error path: return an MCP tool error (`CallToolResult(isError=True, ...)`),
   never a protocol-level error, for a `Roster.check` denial.** The low-level
   Server's `call_tool` wrapper catches any exception your handler raises and
   turns it into exactly that shape anyway (`except Exception as e: return
   self._make_error_result(str(e))`), so raising `PermissionError(reason)` from
   inside the tool handler is sufficient and idiomatic. A protocol-level error
   (`McpError`/`ErrorData`) is a different wire shape reserved for
   malformed/unknown requests; the reference client (`mcp.client.session`) turns
   that into a raised `McpError` in the calling code, not model-visible content
   — the wrong channel for "you don't have this tool, here's why."
6. **openclaw client side (per the existing brief, not re-derived): streamable-http
   is a documented, supported transport (`mcp.servers.<name>.transport:
   "streamable-http"`), and per-agent server scoping (`codex.agents`) plus
   glob `toolFilter` both exist as real, first-class mechanisms — exactly the
   defence-in-depth layer `docs/AGENT-ARCHITECTURE.md` §13 asks for.
   **Real gap**: the brief documents `auth: "oauth"` (with `oauth.identity:
   "shared"|"per-requester"`) and TLS/mTLS controls for HTTP-transport MCP
   servers, but never documents a plain static-bearer-header option. Given the
   locked design is "one static long-lived token per role, issued at the seam"
   (not an OAuth handshake), whether openclaw's MCP client can just send a
   fixed `Authorization: Bearer <token>` per server entry, or whether it insists
   on a real OAuth flow, is **not answered by the existing brief and blocks a
   clean implementation** — flagged below as the one open question worth a
   dedicated follow-up before writing server code against it.
7. **Deployment: ASGI app via `Server.streamable_http_app()`, run under
   `uvicorn.Server` (already a direct dependency of `mcp` itself), under a
   systemd unit bound to the tailnet interface's own address (`host=`), never
   `0.0.0.0`, on Ubuntu 24.04 / Python 3.12 — both 1.27.1 and 2.2.0 declare
   `Requires-Python: >=3.10`, so 3.12 is fine either way.** This repo pins
   nothing at the root today (no root `requirements.txt`/`pyproject.toml`);
   the only precedent is `evals/compliance/requirements.txt` and
   `evals/perception/requirements.txt`, each a single unpinned
   `anthropic>=1.0` line. Adding this server means either following that same
   per-component convention (`mcp/requirements.txt` or similar) or starting a
   root `pyproject.toml` — a real, undecided choice, not something this
   research settles.

---

## 1. SDK and protocol revision — verified, with a version discrepancy flagged

**Base**: the official `mcp` PyPI package (`modelcontextprotocol/python-sdk`)
is the right base — there is no reason to reach for the third-party `fastmcp`
project (PyPI `fastmcp`, `gofastmcp.com`, by Jeremiah Lowin) that happens to
also be installed in this environment (`pip show fastmcp` → version 3.2.4,
`Requires: ... mcp ...`). That package is a separate, much heavier superset
built *on top of* the official SDK (see §4/§7 dependency footprint below); it
is not needed for what this server does and was not evaluated further, since
nothing in the task requires its extra surface (OpenAPI-from-spec generation,
mounting, its own CLI, etc.).

**Protocol revision — a real, checked discrepancy between what's installed and
what's current.** Reading `mcp/types.py` directly:

- **What's actually installed in this environment (`mcp` 1.27.1)**:
  `LATEST_PROTOCOL_VERSION = "2025-11-25"`, `DEFAULT_NEGOTIATED_VERSION =
  "2025-03-26"`, `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26",
  "2025-06-18", "2025-11-25"]` (`mcp/shared/version.py`). **Verified** by
  direct read.
- **What's current on PyPI (`mcp` 2.2.0, released per PyPI's history page
  2026-07-28-adjacent)**: installed into an isolated scratch directory this
  session and read directly. `mcp/server/lowlevel/server.py`'s docstring for
  the deprecation of `on_set_logging_level`/`on_roots_list_changed`/
  `on_progress` cites **"2026-07-28 (SEP-2577)"** as the version that
  deprecated them, and imports `MODERN_PROTOCOL_VERSIONS` from
  `mcp_types.version` (protocol types are now their own `mcp-types` PyPI
  package, pinned `==2.2.0`, a real structural split from 1.x). **Verified**
  by direct read of 2.2.0 source; the exact string `"2026-07-28"` is quoted
  verbatim from a deprecation warning message, not inferred.
- Cross-checked against a web summary (PyPI history page, GitHub releases
  page — **probable**, fetched via a summarizing tool, not read byte-for-byte):
  2.0.0 shipped 2026-07-28, described by the project itself as "a major rework
  of the SDK... to support the 2026-07-28 MCP specification... and to fix
  long-standing architectural issues," with **1.x now in maintenance mode,
  security fixes only**.

**The discrepancy, named plainly**: the copy of `mcp` already sitting in this
research environment (1.27.1) is a 1.x release that predates the 2.x rework
and therefore does not speak the current (2026-07-28) protocol revision — its
own `LATEST_PROTOCOL_VERSION` constant tops out at 2025-11-25. Building
df-overseer's MCP server against whatever happens to `pip install mcp` without
a version constraint could land on either line depending on when it's run;
given 1.x's maintenance-only status, **the deliberate choice should be `mcp>=2,<3`**,
not "whatever's newest 1.x" and not the pre-installed 1.27.1 this report had
to fall back to reading for most of its 1.x-side evidence.

**Streamable HTTP is correct, confirmed from the spec-revision history
itself, not just convention**: `mcp.server.streamable_http` exists as its own
module in both 1.27.1 and 2.2.0, described in its own docstring as "an HTTP
transport layer with Streamable HTTP... bidirectional communication using
HTTP requests and responses, with streaming support." `mcp.server.sse` still
exists in both versions too (the older, pre-2025-03-26 HTTP+SSE transport,
kept for backward compatibility with old clients) — not the one to build a
new server on. stdio (`mcp.server.stdio`) is irrelevant here for the reason
already given in the task brief: client and server are different hosts.
**Verified** (module presence and docstrings read directly in both versions).

## 2. Per-request authentication — verified, one hook, stable across the major version bump

**The hook**: `mcp.server.auth.provider.TokenVerifier` — a `Protocol` with one
method, `async def verify_token(self, token: str) -> AccessToken | None`.
`AccessToken` (same module) is a pydantic `BaseModel`: `token: str, client_id:
str, scopes: list[str], expires_at: int | None, resource: str | None`.
**This is exactly where role identity belongs**: implement `TokenVerifier`
by checking the presented string against a config mapping token → role
(e.g. a small YAML alongside `agents/ROSTER.yaml`), and return
`AccessToken(client_id=role_name, scopes=[role_name], ...)`. Verified by
direct read of `mcp/server/auth/provider.py` in **both** 1.27.1 (lines 92-96)
and 2.2.0 (lines 124-127, byte-identical shape) — this interface did not
change across the major version bump, which is a real point in its favor as
the thing to build against.

**How the verified identity actually reaches a tool handler** — two
independent, both-real paths, confirmed by source, not doc pages:

- **A contextvar, in both versions**: `mcp.server.auth.middleware.bearer_auth.BearerAuthBackend`
  (a Starlette `AuthenticationBackend`) reads the `Authorization: Bearer …`
  header, calls `token_verifier.verify_token(token)`, and on success returns
  `AuthenticatedUser(auth_info)`. `mcp.server.auth.middleware.auth_context.AuthContextMiddleware`
  then lifts that off `scope["user"]` into a `contextvars.ContextVar` (default
  `None`), and `mcp.server.auth.middleware.auth_context.get_access_token()` is
  the free function that reads it back — callable from anywhere inside the
  async call stack of that one HTTP request, including from inside a
  `tools/list` or `tools/call` handler. Verified, identical file paths and
  near-identical code in 1.27.1 and 2.2.0 (2.x's `BearerAuthBackend` gained an
  extra `resource_server_url` constructor kwarg for RFC 8707 audience
  checking; the bearer-header-to-contextvar mechanism itself is unchanged).
- **An explicit context argument in 2.x specifically**: 2.x's low-level
  `Server.__init__` takes handlers as `on_list_tools`, `on_call_tool`, etc.,
  each typed `Callable[[ServerRequestContext[LifespanResultT], ParamsT],
  Awaitable[ResultT]]` — the caller's request context is a normal positional
  argument, not something the handler body has to reach for via a
  contextvar. `ServerRequestContext` (`mcp/server/context.py`) carries
  `session`, `lifespan_context`, `protocol_version`, `method`, `params`,
  and `request: RequestT | None` ("the HTTP request... the transport
  attached," per its own docstring) — so the raw Starlette `Request` (and its
  headers) is reachable there too, as a second, header-level route to the
  same information, independent of the auth subsystem entirely if ever
  wanted. **Verified** by direct read of `mcp/server/context.py` and
  `mcp/server/lowlevel/server.py` in 2.2.0.
- In 1.x, the equivalent per-request object is `mcp.shared.context.RequestContext`
  (not `ServerRequestContext` — the class was renamed/moved for 2.x), reached
  via the low-level `Server.request_context` **property**, which does
  `return request_ctx.get()` off a module-level `contextvars.ContextVar` that
  `Server._handle_request` sets fresh on every single inbound request
  (`token = request_ctx.set(RequestContext(...))`, `mcp/server/lowlevel/server.py`
  lines ~753 onward). **Verified** by direct read — this is what makes 1.x's
  decorator-registered `list_tools()`/`call_tool()` handlers per-request too,
  even though the handler function signature itself takes no context
  parameter: it fetches it via `server.request_context` (or the free function
  `get_access_token()`) instead.

**A real friction point in the SDK's own convenience path, found by reading
the code, not assumed**: both versions' `AuthSettings`
(`mcp.server.auth.settings.AuthSettings`) declare `issuer_url: AnyHttpUrl =
Field(...)` as a **required** field, with a docstring reading "OAuth
authorization server URL that issues tokens for this resource server" — even
in the "resource server only" configuration path (i.e., supplying only a
`token_verifier`, no `auth_server_provider`, meaning this server never runs
an OAuth authorization flow itself). This means using the SDK's bundled
`auth=AuthSettings(...)` bootstrap on `streamable_http_app(...)` forces an
`issuer_url` to be configured even though this design has no OAuth
authorization server at all — just a static, manually-issued token per role.
**Verified identical in both 1.27.1 and 2.2.0** by direct read of
`mcp/server/auth/settings.py` in each.

**The practical way around that friction, inferred from the code's own
structure rather than any doc page**: skip the SDK's `auth=`/`AuthSettings`
convenience path entirely. `TokenVerifier`, `BearerAuthBackend`, and
`AuthContextMiddleware` are usable as plain, independent Starlette middleware
building blocks — nothing in their own code requires `AuthSettings` or an
issuer URL to exist. Assemble them directly (`AuthenticationMiddleware(...,
backend=BearerAuthBackend(our_verifier))` + `AuthContextMiddleware`) around
whichever ASGI app the low-level `Server` produces, and never construct an
`AuthSettings` at all. This is composition the SDK's own `streamable_http_app()`
implementation does internally when `auth` is supplied (see 2.2.0's
`Server.streamable_http_app`, read in full, lines 770-786) — nothing prevents
doing the same wiring by hand and dropping the OAuth-shaped
`issuer_url`/`resource_server_url` ceremony this design doesn't need. This is
**inferred from source structure, not independently run** — flagged in "not
verified" below as the one thing worth a five-minute smoke test before
committing to it.

## 3. THE CRUX: per-caller `tools/list` — verified yes, at the low-level API only

**Direct answer**: `tools/list` is resolved **per request** (not per
connection, not per session) by the low-level `Server`, in both versions —
this is a mechanical consequence of how the request-context plumbing above
works, not a special "supports per-caller listing" feature that needed to
be separately added.

- **1.27.1**: `Server.list_tools()` is a decorator. Whatever function is
  registered runs inside the `_handle_request` code path, which — before
  calling it — does `token = request_ctx.set(RequestContext(...))` (a fresh
  `contextvars.ContextVar` value, built from *that specific incoming
  request's* session/metadata) and resets it in a `finally` after the call.
  So a `@server.list_tools()`-decorated function that calls
  `get_access_token()` (or `server.request_context`) inside its own body sees
  the identity of the caller who sent *this* `tools/list` call, every time,
  fresh. **Verified** by direct read of `mcp/server/lowlevel/server.py`
  (`list_tools()` decorator at line 434, `_handle_request`'s `request_ctx.set(...)`
  at line ~753).
- **2.2.0**: even more directly — `on_list_tools` is a plain callback,
  `Callable[[ServerRequestContext[LifespanResultT], PaginatedRequestParams |
  None], Awaitable[ListToolsResult]]`, registered once at `Server(...)`
  construction (or via `add_request_handler("tools/list", ...)`), and called
  fresh with a new `ServerRequestContext` on every `tools/list` request — no
  contextvar indirection needed at all; the caller's context is just the
  first argument. **Verified** by direct read of `mcp/server/lowlevel/server.py`'s
  `Server.__init__` (`_spec_requests` table mapping `"tools/list"` to
  `on_list_tools`, line 458) and `mcp/server/context.py`'s
  `ServerRequestContext` dataclass.

**Concrete recipe this implies** (not run, but a straightforward composition
of everything above, so flagged **probable-mechanically-sound** rather than
**verified-by-execution**): implement `TokenVerifier.verify_token` to map the
presented bearer string to a role via `AccessToken.client_id`; in the
`tools/list` handler, read that role (`get_access_token().client_id` in 1.x,
or the `ctx` argument's session/request in 2.x) and call `Roster.roles[role]`
to build the filtered `list[Tool]` — `RolePermissions.read`/`.write` already
give exactly the allowed id set — before returning `ListToolsResult`. Because
`Roster.check()` is also consulted again inside the `tools/call` handler on
every actual call (never trust the list alone — a client could, in principle,
try to call a tool it wasn't listed, and the server-side check is the actual
boundary per `docs/AGENT-ARCHITECTURE.md` §13's requirement #1), this gives
the Overseer-cannot-discover / Architect-cannot-act split `docs/AGENT-ARCHITECTURE.md`
§5 describes structurally, for free, from data already built (`mcp/registry.py`,
`mcp/roles.py`) — no new permission logic, just a handler that calls
`Roster.check` per id when assembling the list, and again on every call.

**What does NOT do this out of the box, confirmed by reading it rather than
assumed from its name**: the high-level convenience wrapper. 1.x's
`mcp.server.fastmcp.FastMCP.list_tools(self) -> list[MCPTool]` takes **no
arguments at all** and just returns `self._tool_manager.list_tools()` — the
same static list for every caller, every time (`mcp/server/fastmcp/server.py`
line 315). 2.x's equivalent, `mcp.server.mcpserver.MCPServer.list_tools(self)
-> list[MCPTool]`, has the identical no-argument shape (confirmed at
`mcp/server/mcpserver/server.py` line 507; wired to the low-level server the
same static way, `on_list_tools=self._handle_list_tools`, line 218). Neither
of these is a dead end — **you can subclass either and override `list_tools`**,
since `_setup_handlers`/`__init__` binds `self.list_tools` (ordinary Python
method resolution picks up an override in a subclass) — but that is strictly
more code than just using the low-level API's `on_list_tools`/`@list_tools()`
directly, which already hands you per-request context as designed.

**So, answering the brief's own fallback menu directly**: per-caller listing
*is* supported by this SDK, at the low-level API. **One server instance (or
port) per role is not needed** — it would only be the right call if the SDK
genuinely couldn't do per-caller listing at all, which it can. Dropping to
the low-level `Server` API is not a fallback here; it is simply the
correct choice given the requirement, see §4.

## 4. FastMCP/MCPServer vs. the low-level API — recommend low-level, cost stated

**Recommendation: the low-level `Server` API** (`mcp.server.lowlevel.server.Server`
in both versions — the import path is stable across the rework even though
its constructor shape changed, per §1/§3).

**What this costs, stated plainly rather than glossed over**:

- No `@mcp.tool()` decorator turning a typed Python function into a
  `Tool` + JSON Schema automatically. `mcp/registry.py` already has
  everything needed to build a `types.Tool` (id, description, and — not yet
  built — a JSON Schema from `Tool.args`) for every entry in the registry, so
  this is bounded work, not open-ended, but it is work FastMCP/MCPServer
  would have done for free for a single global tool list.
- No auto-generated `inputSchema` validation path unless it's built the same
  way FastMCP does it (`jsonschema.validate` against a schema attached to
  each `types.Tool`, which the low-level `call_tool()` decorator already
  does automatically in 1.x if a `Tool.inputSchema` is supplied via the tool
  cache — see `_get_cached_tool_definition`/`call_tool()`,
  `mcp/server/lowlevel/server.py` lines 476-533 in 1.27.1). So this part is
  actually still free at the low-level API, as long as the `tools/list`
  handler populates real `inputSchema`s.
- More boilerplate for the ASGI app itself: `Server.streamable_http_app(...)`
  exists as a method on the low-level `Server` directly in **2.x** (confirmed
  by direct read, `mcp/server/lowlevel/server.py` line 721) — this already
  does the routes/middleware/auth wiring FastMCP would otherwise hide. In
  **1.x**, the equivalent (`StreamableHTTPSessionManager` +
  `StreamableHTTPASGIApp` + your own `Starlette(...)`) is not a bundled
  one-call method on the low-level `Server` — FastMCP's own
  `streamable_http_app()` (`mcp/server/fastmcp/server.py` line 950) is the
  only place that assembly is done for you in 1.x, so on 1.x specifically,
  going low-level means copying roughly that same ~80-line assembly rather
  than getting it as a method call. **This is a real, version-dependent
  cost difference** and another point in favor of targeting 2.x: the
  low-level API is more self-sufficient there.

Given per-role tool lists are the entire reason this server exists, the
alternative (FastMCP/MCPServer, subclassed and with `list_tools` overridden
anyway) buys nothing but the input-schema/decorator convenience while still
requiring the same override — so it is not a real alternative, just a
heavier path to the same place.

## 5. The error path — verified

**Use an MCP tool error (`CallToolResult(isError=True, content=[TextContent(...)])`),
not a protocol-level error**, for a `Roster.check` denial. Two ways to get
there, both landing on the identical wire shape:

- Return `types.CallToolResult(content=[types.TextContent(type="text",
  text=reason)], isError=True)` directly from the `call_tool` handler when
  `Roster.check(role, tool_id)` returns `(False, reason)`.
- Or simply `raise SomeException(reason)` — the low-level `call_tool()`
  decorator's handler wraps the actual call in `try/except Exception as e:
  return self._make_error_result(str(e))`, and `_make_error_result` builds
  exactly the same `CallToolResult(isError=True, ...)` shape
  (`mcp/server/lowlevel/server.py`, 1.27.1 lines 467-474 and 583-584).
  **Verified** by direct read; both paths produce the same JSON-RPC-level
  **success** response (the RPC call itself did not fail) whose *result
  object* signals a tool-level failure.

**Why this, and not a protocol-level error, is what the calling agent
actually reads**: a protocol-level error is `types.ErrorData` wrapped in a
JSON-RPC `"error"` member, and the reference client
(`mcp.client.session`/`mcp.shared.session.BaseSession.send_request`) turns
that into a raised `McpError` in the *calling Python code*
(`mcp/shared/session.py` line ~294-306, `raise McpError(response_or_error.error)`,
**verified** by direct read). That is a different, framework-level channel:
whether the text of that exception ever reaches the LLM's context at all
depends entirely on the *client's own* exception handling around its
`call_tool()` call — many client/host integrations (agent loops built to
just report "the tool call failed" generically, or to crash the turn) do not
thread an arbitrary exception's message back into the conversation the model
sees, whereas a `CallToolResult` **is** the tool's actual result and gets
returned to the calling code as a normal, successful value — the standard
place a host surfaces tool output text to the model. The MCP spec itself
draws this line (reflected in the SDK's own choice to catch `Exception` and
convert it, rather than let a generic exception propagate as a protocol
error) — **confirmed by the code's actual behavior**, not by locating the
specific spec sentence saying so (that text was not independently located in
this pass; the behavioral evidence from reading both the server's
exception-to-CallToolResult conversion and the client's
error-to-raised-McpError split stands on its own and is the stronger kind of
evidence per this project's own evidence standard).

## 6. openclaw's client side — per the existing brief only, not re-derived

Everything below is a direct read of `research/2026-09-12-openclaw-primitives.md`
(§3, §4), not new research against openclaw itself.

- **Transport**: `mcp.servers.<name>.transport` accepts `"streamable-http"`
  or `"sse"` for HTTP-based servers (`type: "http"` is accepted too, as a CLI
  alias that normalizes to `transport`). Streamable HTTP is directly
  supported — **verified per that brief** (its own confidence flag: fetched
  live from `docs.openclaw.ai/gateway/config-extensions`).
- **Auth, and the gap**: the brief states HTTP-transport servers "support
  `auth: "oauth"` with `oauth.identity: "shared" | "per-requester"` and an
  `oauth.scope`; TLS controls (`sslVerify`, `clientCert`, `clientKey`) exist
  for private/mTLS endpoints." **It does not mention any plain
  static-bearer-header or custom-header config key for an MCP server entry.**
  Given the locked design (`docs/AGENT-ARCHITECTURE.md` §13, item 2) is "one
  token per role, issued at the seam" — a static, manually-distributed
  secret, not a token obtained through an OAuth authorization flow — this is
  a real, load-bearing gap: it is not established whether openclaw's MCP
  client can be pointed at a remote streamable-http server with a fixed
  `Authorization: Bearer <token>` header, or whether its only two
  documented options are a full OAuth handshake (`auth: "oauth"`) or mTLS
  client certificates. **This blocks writing the server's auth story with
  full confidence** until settled — see "not verified" below for the exact
  follow-up.
- **Per-agent server allowlists and `toolFilter`, confirmed real (defence in
  depth, per the locked design)**: `mcp.servers.<name>.codex.agents:
  ["main"]` restricts a declared MCP server to specific openclaw agent ids;
  `mcp.servers.<name>.toolFilter.include`/`.exclude` (glob-style) filters
  which of that server's tools a given declaration exposes at all. Practical
  shape this implies for openclaw's config: **one `mcp.servers` entry per
  role** (e.g. `df-overseer-overseer`, `df-overseer-architect`,
  `df-overseer-consultant`), each pointed at the same remote URL, each
  carrying that role's own credential, each scoped via `codex.agents` to only
  the one openclaw agent playing that role — mirroring the server-side
  allowlist as the second, non-authoritative layer `docs/AGENT-ARCHITECTURE.md`
  §13 calls for. This is a natural reading of the brief's own §3/§4, not a
  separate finding from openclaw's docs — **probable**, not independently
  re-verified against openclaw's config schema this pass.

## 7. Deployment shape — verified where source-checkable, flagged where not

- **ASGI app + runner**: `Server.streamable_http_app(...)` (2.x, a method on
  the low-level `Server` itself, confirmed above) or the hand-assembled
  `StreamableHTTPSessionManager` + `StreamableHTTPASGIApp` + `Starlette(...)`
  (1.x) produces a plain ASGI application. Both versions ship `uvicorn` as a
  direct dependency (`Requires-Dist: uvicorn>=0.31.1; sys_platform !=
  'emscripten'`, confirmed in both 1.27.1's and 2.2.0's `METADATA`), and
  both FastMCP's and 2.x's low-level `streamable_http_app` machinery default
  to `uvicorn.Server(uvicorn.Config(app, host=..., port=...))` as the runner
  — so no separate ASGI-server dependency needs adding. **Bind explicitly to
  the tailnet interface's own address** (pass that address as `host=`, not
  `"0.0.0.0"`) — 2.x's `streamable_http_app` even auto-enables DNS-rebinding
  protection when `host` is a loopback address (`127.0.0.1`/`localhost`/`::1`),
  which is a reason to pass the real tailnet address explicitly rather than
  leaving the default, so that protection (and the right `allowed_hosts`)
  actually matches what's bound. **Verified** (both `Requires-Dist` lines
  read directly; the `streamable_http_app` host-based branch read directly
  in 2.2.0, lines 741-747).
- **Python 3.12 support — verified for both candidate versions**:
  1.27.1's `METADATA` lists `Programming Language :: Python :: 3.10` through
  `3.13` as classifiers; 2.2.0's `METADATA` states `Requires-Python: >=3.10`
  outright. Ubuntu 24.04's system Python 3.12 (confirmed as this research
  machine's own interpreter version, `Python 3.12.4`) is inside both
  ranges.
- **Dependency footprint — verified by reading `METADATA` directly, and it
  differs meaningfully between the two candidate versions**:
  - `mcp` **1.27.1**: `anyio`, `httpx`, `httpx-sse`, `jsonschema`,
    `pydantic`, `pydantic-settings`, `pyjwt[crypto]`, `python-multipart`,
    `sse-starlette`, `starlette`, `typing-extensions`, `typing-inspection`,
    `uvicorn` (plus `pywin32` gated to `sys_platform == 'win32'`, irrelevant
    on the Ubuntu VM).
  - `mcp` **2.2.0**: `anyio`, `httpx2` (a *different* package name from
    `httpx` — a real, structural dependency change, not a typo; not
    investigated further this pass), `jsonschema`, **`mcp-types` (a new,
    separately-versioned split-out package, pinned `==2.2.0`)**,
    **`opentelemetry-api` (a genuinely new mandatory dependency 1.x did not
    have)**, `pydantic`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`,
    `starlette`, `typing-extensions`, `typing-inspection`, `uvicorn`.
  - By contrast, the third-party `fastmcp` (jlowin) package installed
    alongside `mcp` 1.27.1 in this environment pulls in `authlib`,
    `cyclopts`, `exceptiongroup`, `griffelib`, `jsonref`,
    `jsonschema-path`, `openapi-pydantic`, `opentelemetry-api`,
    `packaging`, `platformdirs`, `py-key-value-aio`, `pyperclip`,
    `python-dotenv`, `pyyaml`, `rich`, `uncalled-for`, `watchfiles`,
    `websockets` **in addition to** `mcp` itself — a visibly larger surface,
    reinforcing §1's recommendation to build on the official SDK directly
    rather than that package. **Verified**, all lines read directly from the
    installed/scratch-installed packages' own `METADATA`/`pip show` output.
- **This repo pins nothing at the root today — verified by search, not
  assumed**: no `requirements.txt`, `pyproject.toml`, or lock file exists at
  the repo root (`find . -iname "requirements*.txt" -o -iname
  "pyproject.toml" -o -iname "*.lock" -o -iname "Pipfile*"` returns only
  `evals/compliance/requirements.txt` and `evals/perception/requirements.txt`,
  each a single unpinned `anthropic>=1.0` line, plus an unrelated
  `.claude/scheduled_tasks.lock`). Adding an MCP server introduces the first
  real multi-package dependency surface (`mcp` plus its own transitive tree)
  this repo has had — worth a deliberate decision (a `mcp/requirements.txt`
  following the `evals/` precedent, versus starting a root
  `pyproject.toml`) rather than an implicit one, but that decision is out of
  scope for this research pass.
- **systemd unit shape**: not designed here (out of scope, no VM touched),
  but the ingredients are: `ExecStart=` a venv's `python -m
  <server module>` (or a small `__main__` invoking `uvicorn.Server(...)`
  directly, since `uvicorn` itself needn't be run as its own separate CLI
  process), `Restart=on-failure`, running under whatever service account
  already runs DFHack per this project's existing convention (per
  `research/2026-09-12-openclaw-primitives.md` §11's note that this exact
  question — same account or not — was not checked there either), and no
  public-facing proxy of any kind in front of it.

---

## Not verified / could not check this pass

- **Whether openclaw's MCP client can send a static bearer token (not an
  OAuth-negotiated one) to a remote `streamable-http` server.** This is the
  single most load-bearing open question left by this pass — it decides
  whether the server-side `TokenVerifier` design (checking a static,
  manually-issued per-role secret) can be wired up on the openclaw side at
  all without inventing a real OAuth authorization server on top of it just
  to satisfy openclaw's client. **Concrete next step**: fetch
  `docs.openclaw.ai/gateway/config-extensions` in full (not a search-summary
  pass) looking specifically for a `headers`/`apiKey`/`bearerToken`-shaped
  key on an `mcp.servers.<name>` entry, or read openclaw's own MCP-client
  source (`github.com/openclaw/openclaw`, wherever it builds the HTTP
  transport for a declared MCP server) for how it attaches `auth.oauth` to
  outgoing requests — does it do a real authorization-code/client-credentials
  exchange, or can `oauth.identity: "shared"` degenerate to "just send this
  fixed token"? Neither this pass nor the cited brief settled it.
- **Whether skipping `AuthSettings`/`issuer_url` entirely and hand-assembling
  `BearerAuthBackend` + `AuthContextMiddleware` (§2's proposed workaround for
  the OAuth-shaped `issuer_url` requirement) actually works end-to-end.**
  This is inferred from reading how the SDK's own `streamable_http_app()`
  composes those same middleware classes, not from running a server and
  sending it a request. **Concrete experiment that would settle it**: build
  a five-line low-level `Server` with one dummy tool, wrap its
  `streamable_http_app()`-produced Starlette app in hand-rolled
  `AuthenticationMiddleware(backend=BearerAuthBackend(fake_verifier))` +
  `AuthContextMiddleware` (no `AuthSettings` involved at all), run it under
  `uvicorn` locally, and confirm with `curl -H "Authorization: Bearer
  <token>"` that `get_access_token()` inside a handler actually returns the
  expected `AccessToken`. Not done this pass — read-only, no server was
  started.
- **Whether 2.x's `httpx2` and `mcp-types` (both new, structurally distinct
  package names introduced in the 2.x line) are themselves stable, widely
  available, and Python-3.12-compatible independent of `mcp` itself.** Their
  own `Requires-Python`/platform constraints were not individually checked —
  only that `pip install mcp==2.2.0` succeeded and produced importable code
  in this environment, which is Windows, not the target Ubuntu 24.04 VM.
  **Concrete next step**: `pip install mcp==2.2.0` (or whatever 2.x patch is
  current then) into a throwaway venv on the actual VM 103 (or an equivalent
  Ubuntu 24.04 container) before committing to 2.x for real, rather than
  trusting a Windows-machine install as a stand-in for the Linux target.
- **The exact spec-text justification for "tool errors go in `CallToolResult`,
  protocol errors are for the RPC layer."** §5's conclusion rests on reading
  the SDK's actual behavior (exception-to-`CallToolResult` conversion
  server-side, error-to-raised-`McpError` conversion client-side), which is
  strong evidence, but the specific sentence of the MCP specification text
  saying this outright was not independently located and quoted in this
  pass — flagged so this isn't overstated as "the spec says," only as "the
  reference implementation on both ends behaves this way."
- **Whether openclaw's own host-side agent loop, specifically, surfaces
  `CallToolResult(isError=True, ...)` content to the model as normal tool
  output** (as opposed to some hosts that might collapse any `isError`
  result into a generic "tool failed" system message without the reason
  text). This is a claim about openclaw's *host* behavior, not the MCP SDK,
  and `research/2026-09-12-openclaw-primitives.md` does not address it —
  genuinely unknown until either read from openclaw's own tool-result
  handling source or observed empirically once both sides exist.

## Relevant to

`docs/AGENT-ARCHITECTURE.md` §13 (deployment topology, the two locked
requirements this report was scoped to serve) and its still-open §14 items;
the not-yet-built MCP server itself (the next concrete build step after
`mcp/registry.py`/`mcp/roles.py`, per `mcp/README.md`'s own scope statement);
and `research/2026-09-12-openclaw-primitives.md` §3/§4, whose gap on
static-bearer-vs-OAuth this report surfaces as the one blocking unknown for
the client side of this same seam.
