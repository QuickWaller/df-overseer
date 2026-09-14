# Stream: get openclaw running on VM 106 and learn its real config schema

**Written** 2026-09-14. **Status:** re-dispatched 2026-09-14 from step 2.
**User go-ahead:** given for continuing the openclaw seam, and again for the
re-dispatch. VM 106 runs nothing but Docker, so this is the low-risk half.

**Step 1 is already done.** The first dispatch was stopped early for session
context and had already installed Docker 29.1.3 from distro packages
(verified directly afterwards: active, no images, no containers). Start at
step 2.

## Why

`dfmcp` is a live, enabled service on VM 103 and VM 106 has already called it
with curl. The only thing left is the real client. **openclaw is not
installed anywhere**, and the `mcp.servers` / `agents.entries` schema in
`research/2026-09-12-openclaw-mcp-auth.md` was read from upstream source and
has never been confirmed against a running build. The scaffold at
`../openclaw` uses an unrelated `agent.yaml` shape with no `mcp` key at all.
**So the deliverable here is knowledge, not a wired client.**

## Read first

1. `research/2026-09-14-openclaw-mcp-wiring.md` (the recon, and its own
   correction note at the end).
2. `research/2026-09-12-openclaw-mcp-auth.md` (the schema claims to test).
3. `C:\website-projects\openclaw` (the scaffold: `docker-compose.yml`,
   `config/*/agent.yaml`). It is a separate repo. **Do not commit in it.**
4. `docs/AGENT-ARCHITECTURE.md` §13 (the two locked requirements).

## What to do

1. **Install Docker on VM 106** (apt is fine here, it is a bare VM). Nothing
   else on that host matters, so prefer the distro packages unless the image
   needs newer.
2. **Get openclaw running**: pull `ghcr.io/openclaw/openclaw:latest` and start
   it. **If the image does not exist or needs credentials, stop and report** —
   that is a fact worth more than a workaround.
3. **Learn the real config schema.** Whatever the running build actually
   reads: config file locations, the shape for registering an MCP server over
   HTTP with an `Authorization` header, and the shape for per-agent tool
   allow/deny lists. Prefer primary evidence, in this order: a JSON schema or
   `--help` from the binary, the image's own docs or example configs, then
   source inside the image. **Quote what you find, with the path inside the
   container.**
4. **Test that it parses**, not that it talks to a model: add our server as an
   MCP entry pointing at VM 103's LAN address with a **placeholder** token,
   and get openclaw to validate or list its config. A "server registered,
   auth failed" style result is a pass here.
5. **Write up the diff** between what the 2026-09-12 brief claimed and what
   the running build actually wants, entry by entry.

## Hard lines

- **No real role tokens on VM 106**, and no LLM API key anywhere on that host.
  This stream must not make a single paid model call. Wiring a real token and
  running an agent is a separate, gated step.
- **Do not touch VM 103.** The live fort and the MCP service are on it. You
  may point config at its address, but change nothing there.
- Public repo: no address, hostname or token in any tracked file or in your
  report. Name env keys instead.
- Do not commit, in this repo or the scaffold. Do not edit `Working.md`,
  `decisions/`, `memory/` or other handoff docs.
- If the estate gains a listening service, say so plainly in the report: it is
  a `home-lab` `inventory/services.yaml` obligation.

## Report

Executor shape, plus **"Findings to record"**: the schema as it really is, the
per-entry diff against the old brief, what openclaw needs that we have not
planned for (secrets handling, model config, storage), and the exact reversal
steps for everything you installed.

## Result, 2026-09-14 (step 2 onward, re-dispatched run)

**Status: done.** `ghcr.io/openclaw/openclaw:latest` (OpenClaw 2026.9.4,
commit `3a9d69d`) was already present on VM 106 from the earlier session (no
registry credentials configured anywhere on the host: confirmed
`~/.docker/config.json` and `/root/.docker/config.json` both absent, so the
image is genuinely anonymously pullable, no stop condition hit). No
`docker pull` was needed; existence and version were confirmed with
`docker images` / `docker inspect`.

**What actually ran, all via ephemeral `docker run --rm --entrypoint node
ghcr.io/openclaw/openclaw:latest openclaw.mjs ...`** (never the full
`docker-compose.yml` stack, deliberately: that stack pulls in Cloudflare
Tunnel, Telegram, and MS365 secrets this task has no reason to touch, and
several of its env vars turned out not to exist in this build at all, see
below):

- `openclaw.mjs --help`, `config --help`, `mcp --help`, `mcp add --help`,
  `gateway --help`, `secrets --help`, `models --help`: the CLI's own surface.
- `openclaw.mjs config schema`: the full JSON Schema (draft-07) for
  `openclaw.json`, 55,932 lines, saved to this session's scratchpad and read
  directly (not summarized from a tool).
- `openclaw.mjs config file` / `config validate`: confirmed the default
  config path and that a fresh, empty config space validates cleanly.
- `openclaw.mjs mcp add df-overseer --url http://<VM103-LAN-IP>:8443/mcp
  --transport streamable-http --header 'Authorization=Bearer
  PLACEHOLDER_TOKEN_NOT_REAL_0000' --no-probe`: registered the server without
  a network call first.
- `openclaw.mjs mcp show / status / doctor / probe [--json]`: inspected and
  then actually probed the live entry (a real HTTP POST from VM 106 to VM
  103's MCP endpoint, placeholder token, explicitly permitted by this task's
  hard lines).
- `openclaw.mjs config set mcp.servers.df-overseer.headers.Authorization
  'Bearer ${DF_MCP_TOKEN_PLACEHOLDER}'` then re-ran `mcp show --json` / `mcp
  doctor` / `mcp probe` twice, once with the container env var unset and once
  with it set to the same placeholder string, to directly exercise
  `${VAR}` substitution rather than trust the source-read claim.
- A direct `curl -X POST http://<VM103-LAN-IP>:8443/mcp ...` from VM 106,
  outside openclaw entirely, to get the raw HTTP status underneath openclaw's
  own (redacted, generic) error text.

**No paid model call was made or attempted at any point.** No `openclaw
agent`, `chat`, `tui`, `onboard`, or `gateway run` command was ever issued, no
provider was configured, and no LLM API key (real or placeholder) was ever
set in the container environment or written to disk. `docker ps -a` and `ss
-tlnp` after the run show zero containers and zero new listening ports on VM
106 (only sshd and the local DNS stub resolver). **Nothing on VM 106 listens
today**, so there is no new `home-lab` `inventory/services.yaml` entry needed
yet; that obligation starts the day something runs `gateway run` durably.

### Findings to record

**1. The real schema, quoted, with paths inside the container.**

Config file: **`~/.openclaw/openclaw.json`** by default
(`/home/node/.openclaw/openclaw.json`, where `node` is the image's built-in user),
relocatable with **`OPENCLAW_STATE_DIR`** (a whole directory) or
**`OPENCLAW_CONFIG_PATH`** (the exact file). Confirmed live: setting
`OPENCLAW_STATE_DIR=/opt/openclaw/config` and mounting that path moved
`config file`'s reported path into it; a static string search of the shipped
bundle (`grep -ao 'OPENCLAW_[A-Z_]*' /app/openclaw.mjs | sort -u`) found
these 11 in the launcher file. **That is not the full list:** across all of
`/app` (excluding `node_modules`) there are 484 distinct `OPENCLAW_*` names
(orchestrator check). The 11 from the launcher: `OPENCLAW_BUNDLED_PLUGINS_DIR`,
`OPENCLAW_BUNDLED_VERSION`, `OPENCLAW_COMPILE_CACHE_DISABLED_RESPAWNED`,
`OPENCLAW_CONFIG_PATH`, `OPENCLAW_CONTAINER`,
`OPENCLAW_DISABLE_BUNDLED_PLUGINS`,
`OPENCLAW_DISABLE_CLI_STARTUP_HELP_FAST_PATH`, `OPENCLAW_HOME`,
`OPENCLAW_NODE_UPDATE_RESPAWNED`, `OPENCLAW_PACKAGED_COMPILE_CACHE_RESPAWNED`,
`OPENCLAW_STATE_DIR`.

`mcp.servers.<name>` (from `config schema`, `mcp.servers.additionalProperties`,
schema line 45866 in the saved copy), condensed to the keys this task cares
about:
```
{
  "enabled": boolean,
  "command": string, "args": string[], "env": {string: string|number|boolean}, "cwd": string,  // stdio transport
  "url": string (format: uri),
  "transport": "stdio" | "sse" | "streamable-http",
  "headers": { [key: string]: string | number | boolean },
  "connectionTimeoutMs": number, "requestTimeoutMs": number,
  "supportsParallelToolCalls": boolean,
  "auth": "oauth",   // the only const; omit the whole key for static-header auth
  "oauth": { "identity": "shared"|"per-requester", "authProfileId": string, "scope": string, "redirectUrl": uri, "clientMetadataUrl": uri },
  "sslVerify": boolean, "clientCert": string, "clientKey": string,
  "toolFilter": { "include": string[], "exclude": string[] },   // per-server tool allow/deny, exact names or "*" globs
  "codex": { "agents": string[], "defaultToolsApprovalMode": "auto"|"prompt"|"approve" }
    // schema's own description, quoted verbatim: "OpenClaw projection
    // metadata for Codex app-server threads only. It does not affect ACP
    // sessions or generic Codex harness config."
}
```
`agents.entries.<agentId>.tools` (schema line 8341 in the saved copy):
```
{
  "profile": "minimal"|"coding"|"messaging"|"full",
  "allow": string[], "alsoAllow": string[], "deny": string[],
  "byProvider": { [provider]: { "allow": [...], "alsoAllow": [...], "deny": [...], "profile": ... } },
  "toolsBySender": { [senderId]: { "allow": [...], "alsoAllow": [...], "deny": [...] } },
  ...
}
```
MCP tool identities that these `allow`/`deny` lists match against use the
`safeServerName` field literally (confirmed present in `mcp probe --json`'s
diagnostics output, e.g. `"safeServerName": "df-overseer"`), corroborating
but not independently re-deriving the `<safeServerName>__<toolName>` pattern
`research/2026-09-12-openclaw-mcp-auth.md` read from
`native-mcp-policy.ts`/the sandbox-allowlist doc example.

Storage layout actually observed under `OPENCLAW_STATE_DIR`, none of it
previously documented anywhere in this repo or the scaffold: `openclaw.json`
(mode 0600) + `openclaw.json.bak` (auto-backup written on every `mcp`/`config`
write) + `config-journal-fingerprint.key` (mode 0600, purpose not explored)
+ `state/openclaw.sqlite[-wal,-shm]` (a real runtime SQLite DB, separate
from any memory/QMD store). The directory itself is created mode 0700.
Reversible in full: `sudo rm -rf /opt/openclaw`.

**2. Per-entry diff against `research/2026-09-12-openclaw-mcp-auth.md`.**

| Claim | Verdict | Detail |
|---|---|---|
| `mcp.servers.<name>.url`/`transport`/`headers` | **Confirmed, and strengthened** | Schema matches; `headers` values may be `string\|number\|boolean`, not just `string` as the brief's Record type said: a widening, not a contradiction. |
| `${VAR}` substitution on `headers` | **Confirmed live**, upgraded from source-read to run: unresolved reference is what's stored on disk, a clear "Missing *** var ... feature using this value will be unavailable" warning appears with the var unset, and `mcp show --json` returns the resolved literal once the var is set in the container env. |
| `auth: "oauth"` is a separate path from `headers`, not additive | **Confirmed** (schema: `auth` is a bare `const: "oauth"`, nothing else; our entry has no `auth` key at all, and static-header auth demonstrably worked: it reached VM 103 and got a real 401). |
| `toolFilter.include`/`.exclude` | **Confirmed**, key names match the brief's own JSON5 example exactly. |
| `codex.agents` is Codex-app-server-only, not a general per-agent allowlist (the brief's own correction) | **Independently re-confirmed**, this time from the JSON schema's own `description` string, not just the doc page and `native-mcp-policy.ts` the brief cited: a second, different primary source landing on the identical sentence. |
| `agents.entries.<agentId>.tools.allow`/`.deny` is the real per-agent MCP restriction mechanism | **Confirmed**, schema line 8341, plus previously-unrecorded siblings `alsoAllow`, `byProvider`, `toolsBySender`, `profile`. |
| `isError` content reaches the model as readable text | **Not re-tested this pass.** Our probe never got past a 401 to a real tool call, so this still rests on the brief's source read of `mcp-content.ts`/`agent-bundle-mcp-materialize.ts`, not a live run. |
| openclaw warns when a header value looks like a literal credential | **Confirmed live**: `mcp doctor` printed exactly this for our entry: *"headers.Authorization contains a literal sensitive value; prefer an environment-backed value outside committed config."* One oddity: the warning persisted even after switching to the `${VAR}` form with the var supplied. Plausibly `doctor` inspects the *resolved* value (which, once resolved, is by definition a literal credential) rather than the on-disk form; not traced further, flagged as observed-not-explained rather than a bug claim. |
| Exact openclaw version/commit read from source | **Now pinned for real**: `2026.9.4` / `3a9d69d`, matching what both original prior briefs assumed as baseline. |

**3. What openclaw needs that we have not planned for.**

- **A first-class CLI for exactly this job** (`openclaw mcp
  add/configure/doctor/list/probe/reload/serve/set/show/status/tools/unset`,
  `openclaw config get/set/patch/schema/validate`): the actual recipe for
  wiring the DF MCP server should be these commands, not hand-written JSON5
  in a committed file as both prior research briefs assumed.
- **`openclaw secrets`** (`store`: "team-scoped SQLite secret and
  environment store", `audit`: "audit plaintext secrets, unresolved refs,
  and precedence drift", `configure`, `reload`) and **`openclaw models auth`**
  ("manage system/agent credentials on this machine") are the real mechanisms
  for anything beyond a single static bearer header or a bare `${VAR}`.
  Worth a dedicated look before a real provider key or a real role token is
  ever wired in. Neither was exercised this pass (would need a real secret to
  demonstrate meaningfully, barred by this task's hard lines).
- **The scaffold (`C:\website-projects\openclaw`) is mostly right, with two
  real gaps.** *(Rewritten by the orchestrator after verification; see
  "Orchestrator correction" at the end. The executor's original bullet said
  five scaffold settings and `/healthz` did not exist, from a search of
  `openclaw.mjs` alone, which is a 22 KB launcher.)* Searched across all of
  `/app` in the image: **`OPENCLAW_CONFIG_DIR` and
  `OPENCLAW_AUTH_PROFILE_SECRET_DIR` appear in zero files**, so the scaffold's
  config mount would be ignored and config would land in the container's
  throwaway `/home/node/.openclaw` unless `OPENCLAW_STATE_DIR` (127 files) is
  set instead: a silent data-loss trap on container recreation. The rest do
  exist: `OPENCLAW_WORKSPACE_DIR` (13 files), `OPENCLAW_GATEWAY_PASSWORD`
  (37 files, `preferredEnvVar`), `DEEPSEEK_API_KEY` (9 files, a provider
  `envVars` entry) and `/healthz` (13 files, a real `pathname: "/healthz"`
  route). Whether the scaffold's healthcheck port is right was not checked.
  **Not fixed** (separate repo, no commits there per this task's rule).

**4. Whether any service now listens on VM 106, and on which port.** No.
Verified with `docker ps -a` (empty) and `ss -tlnp` (only `:22` sshd and the
local `127.0.0.53`/`127.0.0.54` DNS stub resolver) after every command in
this run. Every `docker run` used `--rm` with no `-p`/`-d`; nothing was ever
started as a daemon or container in the background. No `home-lab`
`inventory/services.yaml` entry is owed yet.

**5. Exact reversal steps**, none executed (left in place deliberately, all
of it inert and secret-free):
```
docker rmi ghcr.io/openclaw/openclaw:latest   # frees ~4.58GB
sudo rm -rf /opt/openclaw                     # config.json, .bak, journal key, sqlite state
```
Nothing else to reverse: no container was left running, no systemd unit, no
crontab entry, no compose stack was ever started, and Docker itself (step 1)
was already accepted as kept infrastructure by the earlier dispatch.

**State intentionally left on VM 106**, for the next stream to build on: the
pulled image, and `/opt/openclaw/config/openclaw.json` (mode 0600) holding
one MCP server entry, `df-overseer`, pointing at VM 103's real LAN address on
port 8443 at `/mcp`, `transport: streamable-http`, with
`headers.Authorization` set to the **unresolved** reference
`"Bearer ${DF_MCP_TOKEN_PLACEHOLDER}"`. The placeholder string itself was
only ever passed as a `docker run -e` value in throwaway `--rm` containers,
never written to any file. `openclaw.json` also carries two default stub
blocks (`plugins.entries.anthropic`, `.codex`, both `sessionCatalog:
{enabled: false}`) that openclaw itself wrote on first save, not anything
this run added deliberately.

**Correction to this doc's own earlier assumption:** the image was already
present when this run started. The local pull time *can* be dated:
`docker image inspect --format '{{.Metadata.LastTagTime}}'` gives
2026-09-14 00:45 UTC, so the first dispatch pulled it. The orchestrator's
"no images" check after stopping that dispatch was therefore either run
before the pull finished or was wrong; which one was not established.

## Orchestrator correction, 2026-09-14

Checked on VM 106 directly after the report, not taken on trust:
- **Held up:** no containers; nothing new listening (`ss -tlnp`: sshd, DNS
  stub, containerd on loopback); `/opt/openclaw` contents and modes as
  described; `openclaw.json` holds the `df-overseer` entry with the
  unresolved `${DF_MCP_TOKEN_PLACEHOLDER}` reference and no literal secret;
  no Docker registry credentials.
- **Did not hold up:** the scaffold findings and the "11 recognized vars"
  list. `/app/openclaw.mjs` is a 22 KB launcher and `/app` holds 7,476 JS
  files outside `node_modules`, so a search of that one file could not have
  found most of what it claimed was missing. Re-searched across `/app` with
  `grep -rlF <name> /app --include=*.js --include=*.mjs --include=*.cjs
  --include=*.json`; findings section 3 is rewritten with the results.
- **Not re-checked:** the schema quotes (they come from the binary's own
  `config schema` output, the strongest source available) and the `mcp probe`
  401 (the transport already returns 401 on a bad token, verified earlier).
