# OpenClaw MCP Auth: Static Bearer Token vs OAuth, Per-Agent Credentials, and Error Surfacing

Date: 2026-09-12
Scope: close the one gap left between `research/2026-09-12-mcp-server-stack.md`
(server side: `TokenVerifier` takes a bearer token, hands back a role identity)
and `research/2026-09-12-openclaw-primitives.md` (client side: documented only
`auth: "oauth"` and TLS/mTLS, never a plain static-header option). Settles
whether openclaw can attach a static `Authorization: Bearer <token>` to a
remote MCP server, the exact config shape, whether per-agent server allowlists
interact with auth (can Overseer/Architect/Consultant hold different
credentials against the *same* server URL), and whether `isError` content
reaches the model as readable text. Read-only pass; nothing in this repo
changed except this file, no VM touched.
Status: **verified primarily against openclaw's own current `main`-branch
source** (`github.com/openclaw/openclaw`, read file-by-file via the GitHub
API/`gh api` this session — not a summary, not a blog post), cross-checked
against the in-repo authoritative doc (`docs/gateway/config-extensions.md` on
`main`) and closed GitHub issues with their raw `state_reason`/body fetched
directly. Every claim is confidence-flagged individually. Version context:
the two prior briefs pinned openclaw at `2026.9.4` (released 2026-09-11); the
source read here is whatever `main` is at fetch time today (2026-09-12), which
should be at or ahead of `2026.9.4` — not pinned to an exact commit SHA, flagged
where that matters.

---

## TL;DR (answers, no evidence)

1. **Yes. Static bearer header — or any fixed custom header — is a real,
   first-class, documented config surface, not a workaround.** `mcp.servers.<name>.headers`
   is a plain `Record<string, string>` sent as literal HTTP headers on every
   request the client makes to that server (`StreamableHTTPClientTransport`'s
   `requestInit.headers`). **Verified by direct read of current `main` source**
   (`src/agents/mcp-transport.ts`, `src/agents/mcp-transport-config.ts`), not
   inferred from docs. `auth: "oauth"` is a separate, opt-in, mutually-adjacent
   mechanism — setting it does not gate or require the `headers` key at all.
2. **Exact shape**:
   ```json5
   mcp: {
     servers: {
       "df-overseer": {
         url: "https://<df-mcp-host>/mcp",
         transport: "streamable-http",
         headers: { Authorization: "Bearer ${DF_MCP_TOKEN_OVERSEER}" },
       },
     },
   }
   ```
   **The value can and should come from an environment variable, not be
   written into `openclaw.json` literally.** `${VAR_NAME}` substitution is a
   real, generic mechanism applied to the whole config tree at load time
   (`src/config/env-substitution.ts`, wired in via `src/config/io.read-helpers.ts`/
   `src/config/mutate.ts`) — **verified by direct source read**, and separately
   corroborated by two closed-as-completed GitHub issues confirming this exact
   header path was fixed and is exercised (§2 below). openclaw additionally
   warns operators when a header value looks like a literal credential rather
   than a `${VAR}` reference, and redacts header values that do resolve to
   secrets from logs/status output. Any header name works, not just
   `Authorization` — the map is generic.
3. **Question 3 (is `oauth` satisfiable minimally, or is mTLS lighter) is
   moot.** Static-header auth is already the lightest path and is fully
   supported today; there is no need to stand up a token-issuing OAuth
   authorization server on the DF MCP side, and no need for mTLS either
   (though `sslVerify`/`clientCert`/`clientKey` remain available if ever
   wanted as an additional layer). Build the DF MCP server's `TokenVerifier`
   exactly as `research/2026-09-12-mcp-server-stack.md` already planned, with
   no OAuth machinery on either side.
4. **A real correction to both prior briefs, flagged loudly as instructed.**
   `mcp.servers.<name>.codex.agents` — the mechanism both
   `research/2026-09-12-openclaw-primitives.md` §3/§4 and
   `research/2026-09-12-mcp-server-stack.md` §6 relied on as "per-agent MCP
   server allowlisting" — **is scoped to the Codex app-server harness only.**
   The authoritative in-repo doc says this in plain language: *"This block is
   OpenClaw metadata for Codex app-server threads only; it does not affect ACP
   sessions, generic Codex harness config, or other runtime adapters."*
   Confirmed independently by reading `src/agents/native-mcp-policy.ts`: for
   ordinary embedded openclaw agents (the `agents.entries.<agentId>` shape both
   prior briefs otherwise correctly document), per-agent MCP tool restriction
   runs through the **general** `agents.entries.<agentId>.tools.allow`/`.deny`
   mechanism, matched against MCP tool identities named
   `<safeServerName>__<toolName>` — not through `codex.agents` at all, unless
   the agent in question is specifically a Codex-app-server-harness agent.
   **This does not break the one-token-per-role design** — it changes which
   knob implements the second (defence-in-depth) layer. See §4 for the
   corrected recipe. It is a smaller finding than "one credential per URL,"
   but real: anyone building `mcp/` config against the two prior briefs'
   literal `codex.agents` claim would wire a control that silently does
   nothing for a non-Codex agent.
5. **Yes. `isError` content reaches the model as readable text, not swallowed.**
   Verified by direct read of current `main` source: `projectMcpCallToolResult()`
   in `src/agents/mcp-content.ts` reads `result.isError`, projects the MCP
   `content` blocks (including the actual `TextContent` reason string) into the
   agent-visible tool result unchanged, and additionally stamps
   `details.status: "error"` when `isError` is true. This is the exact
   function called from the tool-invocation path used for a declared external
   MCP server (`src/agents/agent-bundle-mcp-materialize.ts`: `const result =
   await runtime.callTool(serverName, toolName, input); const agentResult =
   projectMcpCallToolResult(result, ...)`). A `CallToolResult(isError=True,
   content=[TextContent(text=reason)])` denial from the DF MCP server will
   reach the model as its tool-result text, reason string intact.

---

## 1–3. Static bearer header: real, documented, and how to use it

**The in-repo authoritative doc** (`docs/gateway/config-extensions.md` on
`main`, fetched directly, not a summary) gives the full schema in one place:

```json5
{
  mcp: {
    servers: {
      remote: {
        url: "https://example.com/mcp",
        transport: "streamable-http", // streamable-http | sse
        requestTimeoutMs: 20000,
        connectionTimeoutMs: 5000,
        supportsParallelToolCalls: true,
        headers: {
          Authorization: "Bearer ${MCP_REMOTE_TOKEN}",
        },
        auth: "oauth",
        oauth: { identity: "per-requester", scope: "docs.read" },
        sslVerify: true,
        clientCert: "/path/to/client.crt",
        clientKey: "/path/to/client.key",
        toolFilter: { include: ["search_*"], exclude: ["admin_*"] },
        codex: { agents: ["main"], defaultToolsApprovalMode: "approve" },
      },
    },
  },
}
```
**Verified** — this is the literal content of `docs/gateway/config-extensions.md`
at the path `mcp.servers.<name>`, fetched via `gh api
repos/openclaw/openclaw/contents/docs/gateway/config-extensions.md` this
session (i.e., the doc file itself, not the rendered `docs.openclaw.ai` page,
though the rendered page returned the same content when fetched separately).

**Read `headers` and `auth` as two independent knobs, not a menu of mutually
exclusive levels.** Confirmed by reading the actual resolution code
(`src/agents/mcp-transport.ts`, lines ~160-226):

```ts
const headers =
  resolved.auth === "oauth" || authProfileId
    ? withoutMcpAuthorizationHeader(resolved.headers)
    : resolved.headers;
...
transport: new OpenClawStreamableHTTPClientTransport(new URL(resolved.url), {
  requestInit: resolved.auth === "oauth" || !headers ? undefined : { headers },
})
```
**Verified by direct source read.** Two things this settles:
- When `auth` is *not* `"oauth"` (the design's case — no OAuth authorization
  server exists or is wanted), whatever `headers` map is configured — including
  a manually issued static `Authorization: Bearer <token>` — is passed
  unmodified into the `StreamableHTTPClientTransport`'s `requestInit.headers`,
  which the MCP TypeScript SDK attaches to every POST/GET/DELETE request it
  makes to that server (initialize, `tools/list`, `tools/call`, session
  teardown). This is the literal mechanism the design needs.
- When `auth: "oauth"` *is* set, any static `Authorization` header is stripped
  (`withoutMcpAuthorizationHeader`) and a real OAuth-flow-derived bearer is
  substituted instead (`withMcpOAuthBearer`, same file). The two are not
  additive — `auth: "oauth"` is a genuine alternate path, not a
  supplement to `headers`. Since the design wants exactly the latter, simply
  never set `auth` on the DF MCP server entries and the static token in
  `headers` is what ships on the wire, full stop.

**Where the header value resolves at config load, not request time** — this
matters for the "no secret in a public repo" constraint. `src/config/env-substitution.ts`
implements generic `${VAR_NAME}` interpolation (uppercase names only,
`$${VAR}` escapes a literal), applied recursively across the whole config
object by `resolveConfigEnvVars()`, called from the general config
read/mutate path (`src/config/io.read-helpers.ts`, `src/config/mutate.ts`) —
**not** something specific to MCP. **Verified by direct source read of the
current file**, which is the strongest confirmation available (this is the
same generic mechanism every other secret-bearing config key in openclaw
already relies on, not a special case built for MCP). Practically: put
`DF_MCP_TOKEN_OVERSEER=<real-token>` in the openclaw host's own environment
(systemd `EnvironmentFile=`, a `.env` the process loads, whatever this
project's convention becomes for that VM), and `openclaw.json` itself commits
only the literal string `"Bearer ${DF_MCP_TOKEN_OVERSEER}"` — safe for a
public repo's example/template config, exactly the `infra/local.*` pattern
this repo already uses elsewhere in spirit, though openclaw's config lives on
openclaw's own VM, not in this repo, so the actual constraint is "don't put
the real token in any file this repo tracks," which this satisfies trivially
since the token never needs to touch this repo at all.

**A real discrepancy worth naming: the prior brief fetched the same doc page
and reported a JSON5 example with no `headers`/`auth`/`oauth`/TLS keys at
all** (`research/2026-09-12-openclaw-primitives.md` §4's quoted snippet stops
at `transport: "streamable-http"`). Both that brief and this one describe
their `docs.openclaw.ai/gateway/config-extensions` fetch as "fetched live."
Re-fetching the identical page and the identical doc file this session
produced the full schema including `headers` on the first attempt, and the
`headers` key demonstrably predates 2026-09-12 by about five months (GitHub
issues referencing it are filed against openclaw `2026.4.10` and `2026.4.22`,
well before either brief's research date). **The likely explanation is a
fetch/extraction limitation in the earlier session's tool call, not a
same-day documentation change** — but this could not be fully ruled out
without knowing exactly what the earlier session's fetch returned internally,
so it is named as a discrepancy per this project's evidence standard rather
than silently corrected. Practical lesson for future briefs on this same
doc: fetch the raw doc file (or ask explicitly for auth-related keys, as this
pass did) rather than trusting a first-pass general summary to surface every
key.

**Corroborating evidence, one level down in confidence: three closed GitHub
issues, all `state_reason: "completed"`, read via the GitHub API directly
(raw JSON `state`/`state_reason`/`body`/`closed_at`/`created_at` fields, not a
summary):**

- **#65590** ("MCP streamable-http transport not forwarding custom headers to
  remote servers," filed 2026-04-12 against `2026.4.10`, closed 2026-04-26)
  — closing bot comment (`clawsweeper[bot]`, citing commit `e23d17da79dc`)
  states the codebase "properly reads and preserves HTTP headers from MCP
  server configuration... passes headers into the SDK's
  `StreamableHTTPClientTransport`... for POST/GET/DELETE requests during
  initialization, tool listing, and tool calls." This matches exactly what
  this session's own direct source read of `mcp-transport.ts` found — **this
  session's independent source read is the higher-confidence claim; the
  bot comment is corroboration**, not the primary evidence.
- **#70901** ("MCP HTTP server headers don't expand `${ENV_VAR}` syntax,"
  filed 2026-04-24 against `2026.4.22`, closed 2026-04-26, two days later) —
  closing bot comment cites `src/config/env-substitution.ts` by name, the
  same file this session read directly and confirmed still implements generic
  recursive substitution on `main` today.
- **#72196** ("expose custom-header configuration... some servers require
  `x-api-key`, not Bearer," filed and closed 2026-04-26 the same day, 76
  minutes apart) — closing bot comment states the requested `authHeaders`
  field is unnecessary because `headers?: Record<string, string | number |
  boolean>` already accepts arbitrary header names. **Independently
  confirmed this session**: no `authHeaders` key exists anywhere in the
  current source (`gh api search/code` for `"authHeaders"` inside
  `openclaw/openclaw` returns zero hits in MCP-related files), and
  `mcp-http.ts`'s own type declares `headers?: Record<string, string>` with
  no restriction to a specific header name. So a non-`Authorization` fixed
  header (e.g. `x-api-key`, if the DF MCP server ever wanted one) works the
  same way, no special config key needed.

**Confidence note on the three bot closures**: `clawsweeper[bot]` closures are
an AI-assisted triage step ("reviewed using GPT-5.5 reasoning against commit
X"), not a human maintainer's manual confirmation or this session's own test
run. Treated here as **probable, not verified**, on their own — but for
`#65590` and `#70901` specifically, this session's own direct read of the
current source (§ above) independently confirms the same conclusion at
**verified** confidence, so the combination is solid. For `#72196` (the
`x-api-key`/arbitrary-header-name claim), this session's confirmation is the
type-signature read (`headers?: Record<string, string...>`, no
`authHeaders` anywhere) — also **verified**, not resting on the bot alone.

**A related, lower-stakes integration risk found along the way, not asked for
but worth flagging**: issue **#72757** ("bundle-mcp Streamable HTTP client:
opens optional GET SSE stream before POST initialize; fails 405 on POST-only
MCP servers," filed 2026-04-27, closed) and **#66940** ("missing Accept header
causes connection failure") both describe openclaw's streamable-HTTP client
being stricter/pickier about handshake details than some servers expect. The
Python `mcp` SDK's `Server.streamable_http_app()` (per
`research/2026-09-12-mcp-server-stack.md`) is a spec-compliant server and
should not trip either issue, but this is now a named, concrete thing to
check in the "not verified" list below (a live smoke test) rather than an
assumption.

## 4. Per-agent allowlists and auth: the `codex.agents` correction

**Direct quote, `docs/gateway/config-extensions.md`, `mcp.servers.<name>.codex`
entry** (fetched from the doc file on `main`, not a summary):

> "This block is OpenClaw metadata for Codex app-server threads only; it does
> not affect ACP sessions, generic Codex harness config, or other runtime
> adapters."

**This directly contradicts how both prior briefs characterized it.**
`research/2026-09-12-openclaw-primitives.md` §3 called it "a non-empty
allowlist of agent ids permitted to reach that server in the first place"
without qualification, and `research/2026-09-12-mcp-server-stack.md` §6 built
its recommended deployment shape ("one `mcp.servers` entry per role... each
scoped via `codex.agents` to only the one openclaw agent playing that role")
directly on that unqualified reading. **Unless df-overseer's Overseer,
Architect and Consultant are specifically run as Codex-app-server-harness
agents (nothing in either prior brief or `docs/AGENT-ARCHITECTURE.md`
suggests they are — the `agents.entries.<agentId>` shape both briefs document
elsewhere is the plain embedded-openclaw-agent runtime, not the Codex
harness), `codex.agents` on a df-overseer MCP server entry would be inert
metadata that does nothing to restrict which agent can reach it.**

**What actually does this for an ordinary embedded agent** — confirmed by
direct read of `src/agents/native-mcp-policy.ts` (current `main`): per-agent
MCP tool restriction runs through `applyFinalEffectiveToolPolicy`, the same
general tool-policy pipeline that handles built-in tools, applied against MCP
tool identities. Each MCP tool from a declared server gets a stable per-server
identity (`{serverName, toolName}` pairs tracked internally, exposed to config
as `<safeServerName>__<toolName>` — confirmed by
`docs/gateway/sandbox-vs-tool-policy-vs-elevated`'s own example,
`outlook__send_mail` / `outlook__*`, for the closely-related sandbox-allowlist
syntax that uses the identical server-prefix scheme). So the general,
non-Codex-specific control surface is `agents.entries.<agentId>.tools.allow` /
`.deny` (or the workspace `denyTools` variant already cited in
`research/2026-09-12-openclaw-primitives.md` §3), naming these
`<safeServerName>__<toolName>` identities or a glob over them.

**This does not break the one-token-per-role scheme — it relocates the second
layer.** The corrected recipe:

1. Declare **three separate `mcp.servers` entries** pointing at the identical
   DF MCP server URL, one per role — e.g. `df-overseer`, `df-architect`,
   `df-consultant` — each with its own `headers.Authorization: "Bearer
   ${DF_MCP_TOKEN_<ROLE>}"`. **Confirmed these are fully independent, not
   deduplicated by URL**: config resolution (`resolveMcpTransportConfig`,
   §1-3 above) and runtime/connection admission are both keyed by the
   *server name* (the `mcp.servers.<name>` key), never by URL —
   `src/agents/agent-bundle-mcp-runtime-shared.ts`'s cache-key fields
   (`includeServerNames`, `excludeServerNames`, `safeServerNamesByServer`,
   `connectionOverrides: ReadonlyMap<string, ...>`) are all name-keyed, and
   the doc's own admission-limit language ("Each Gateway admits at most 256
   OpenClaw-managed MCP runtimes with server connections... A runtime can own
   multiple configured server connections") describes connections per
   configured server, with no URL-based merging logic anywhere in the source
   read this session. **Verified** by source read; nothing in the doc states
   this outright as a positive claim ("yes, duplicate URLs work"), so this is
   assembled from the absence of any dedup-by-URL code path plus the
   name-keyed cache/config shape, not from a single sentence saying so
   explicitly — flagged as the strongest inference this pass supports, not a
   quoted guarantee.
2. Scope each role's own `agents.entries.<roleAgentId>.tools.allow` to only
   that role's server's tool identities (e.g. `["df-overseer__*"]` for the
   Overseer agent), or `.deny` the other two servers' identities on each
   specialist. This is the real defence-in-depth second layer
   `docs/AGENT-ARCHITECTURE.md` §13 wants — just implemented with
   `tools.allow/deny`, not `codex.agents`.
3. If df-overseer *does* end up routing any role through the Codex app-server
   harness specifically (not currently the plan), `codex.agents` becomes
   additionally meaningful for that one agent, but should not be relied on as
   the only or primary control for the embedded-agent case.

**So, answering the brief's explicit "bigger finding" framing directly: this
is not the one-credential-per-URL failure mode the brief was most worried
about.** Two agents on one openclaw host *can* present different credentials
to the same MCP server URL, and the mechanism to keep them from reaching each
other's server is real and general — it is just a different config key than
either prior brief named. The fallback the brief floated ("one server
endpoint per role") is **not needed**; distinct `mcp.servers` names sharing
one URL already gets you that isolation without needing distinct DNS
names/ports on the DF-MCP side.

## 5. `isError` surfacing — verified by source, not by running anything

`src/agents/mcp-content.ts`:

```ts
export function projectMcpCallToolResult(
  result: { content?: unknown; structuredContent?: unknown; isError?: unknown },
  details: Record<string, unknown> = {},
): AgentToolResult<unknown> {
  const isError = result.isError === true;
  const content = projectMcpCallToolResultContent(result);
  const projected: AgentToolResult<unknown> = {
    content: content.length > 0 ? content : [{
      type: "text",
      text: isError
        ? "MCP tool failed without returning content."
        : "MCP tool completed without returning content.",
    }],
    details: {
      ...details,
      ...(result.structuredContent !== undefined ? { structuredContent: result.structuredContent } : {}),
      ...(isError ? { status: "error" } : {}),
    },
  };
  ...
}
```

**Verified**: this reads the wire-level `isError` boolean off the raw MCP
`CallToolResult`, and — critically — still runs the `content` array (which is
where a `TextContent(text=reason)` block from a `Roster.check` denial would
live, per `research/2026-09-12-mcp-server-stack.md` §5's recommended server
shape) through `projectMcpCallToolResultContent()`, which maps each MCP
content block (`text`/`image`/`audio`/`resource_link`/`resource`) into the
agent-visible content array unchanged for `text` blocks. It does **not**
discard or collapse the content when `isError` is true — it only *adds* a
`details.status: "error"` marker alongside the real text, and only
substitutes a generic placeholder string in the narrow case where the server
returned `isError: true` with a genuinely empty `content` array (which a
well-built denial response, always including a reason `TextContent`, would
never do).

**Confirmed this is the code path used for a declared external/remote MCP
server's tool calls, not some other internal-tool-only path**:
`src/agents/agent-bundle-mcp-materialize.ts` line ~484-485:
```ts
const result = await runtime.callTool(serverName, toolName, input);
const agentResult = projectMcpCallToolResult(result, { ... });
```
This is the direct call-and-project pair for a `serverName`/`toolName`
invocation against a bundled/declared MCP server — exactly what a DF MCP tool
call from the Overseer/Architect/Consultant would be.

**What was not independently re-verified**: whether `AgentToolResult`'s
`content`/`details` shape, once produced here, definitely lands verbatim in
the actual model-facing message the LLM API receives (as opposed to being
filtered again by some later, UI-only or chat-projection-specific layer). The
`details.status: "error"` field reads as metadata for openclaw's own UI/log
surfaces, not something that would be stripped from the `content` array
before it reaches the model — but this project has not traced the full chain
from `AgentToolResult` to the literal `tool_result` block sent to the
provider API, so this is **probable, not verified-end-to-end**. Flagged
explicitly in "not verified" below with the concrete experiment that would
close it.

---

## Not verified / could not check this pass

- **The exact commit/version of `main` this session read against.** Not
  pinned to a specific SHA or tag; read via the GitHub Contents/Search API at
  fetch time today (2026-09-12), which should be at or ahead of the
  `2026.9.4` release both prior briefs pinned, but this was not cross-checked
  against a release tag directly (e.g. by diffing `main` against the
  `2026.9.4` tag). If openclaw ships a point release between now and when
  this is acted on, re-confirm the specific lines quoted here still match.
- **End-to-end verification that a real DF MCP server's `Authorization:
  Bearer <token>` header actually arrives and is read correctly by the
  `mcp` Python SDK's `BearerAuthBackend`, with an openclaw agent on the other
  end.** This whole report is a source-code read of openclaw's client side
  plus a source-code read (in the companion brief) of the Python SDK's server
  side; the two have never been run against each other. **Concrete
  experiment that would settle it**: stand up a five-line low-level `Server`
  with one dummy tool and a `TokenVerifier` checking a fixed string (per
  `research/2026-09-12-mcp-server-stack.md`'s own suggested smoke test),
  point a throwaway openclaw agent's `mcp.servers.<name>` entry at it with
  `headers.Authorization: "Bearer <the-fixed-string>"` and no `auth` key, and
  confirm the agent can list and call the dummy tool. This is the single
  highest-value follow-up, since it is the one thing genuinely nobody has run.
- **Whether the GET-before-POST handshake behavior in issues #72757/#66940 is
  still present on current `main`**, and whether it would actually trip
  against the Python SDK's `streamable_http_app()`. Not traced past the two
  issue reports; both are closed, but this session did not confirm their
  fix status the way it did for the header-forwarding issues (no bot
  closing-comment content was fetched for these two). Worth a five-minute
  check before the live smoke test above, since a 405-on-GET failure would
  look like an auth failure at first glance and could be misdiagnosed.
- **Whether `AgentToolResult.content`/`.details` (§5) is the final,
  unmodified shape that reaches the model**, versus being transformed once
  more by a chat-projection or UI-collapsing layer before the provider API
  call. Not traced past `projectMcpCallToolResult`'s own return value — see
  §5's caveat. The live smoke test above (have the dummy tool return
  `isError: true` with a distinctive reason string, then check the actual
  provider-API request body openclaw sends) would settle this at the same
  time as the auth test, for negligible extra cost.
- **Whether declaring the same URL under two `mcp.servers` names causes any
  behavior on the *DF MCP server's own* side** (e.g. two concurrent MCP
  sessions, session-ID handling, or connection-count assumptions) — this is
  a question about the server this project will build, not about openclaw,
  and was out of scope for this pass; flagged so it isn't silently assumed
  fine on the strength of "openclaw supports declaring it" alone.
- **The exact spelling/casing rule for a header name that is not
  `Authorization`** (e.g. would `X-API-Key` versus `x-api-key` matter) — the
  type signature confirms arbitrary keys are accepted and passed through, but
  HTTP header case-normalization behavior of the underlying `fetch`/`Headers`
  implementation was not separately traced. Almost certainly a non-issue
  (the `Headers` object normalizes case per the Fetch spec), but not
  independently confirmed by reading `mcp-transport.ts`'s own header-merge
  code (which does lower-case its own dedup map, per lines 110-115 quoted in
  §1-3) beyond what's already quoted above.

## Relevant to

`docs/AGENT-ARCHITECTURE.md` §13 (the two locked deployment requirements this
report closes the client-side half of) and its §14 item list (the openclaw
primitives entry should be corrected/annotated to point here for the
`codex.agents` scoping caveat); `research/2026-09-12-mcp-server-stack.md` §6's
own "not verified" item on this exact question, now closed; and the
not-yet-built `mcp/` config for openclaw's own host, which should be written
against §1-4 here (`headers` + env-var token, three separately-named server
entries, `tools.allow`/`.deny` for the second layer) rather than against
either prior brief's `codex.agents`-centric recipe.
