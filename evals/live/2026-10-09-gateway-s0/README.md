# Gateway S0: install, checks, and the idle canary

Date: 2026-10-09. VM 106, openclaw 2026.9.4 (commit 3a9d69d), image pinned by digest
`sha256:cc596b84...f101` (the `:latest` the conductor already had, now referenced by digest).
Spec: `research/2026-10-09-gateway-sessions-v1.md` (sections 3, 7, 9, 11, 12, 15).
Read-only role used for every turn: the **Consultant**, one read tool (`doctrine.get`), no game action.
Nothing was enabled at boot. `conductor.service`, the operator hold and the one-shot state dir
(`/opt/openclaw/config`) were not touched by this stream.

Legend: **V** verified live here, **N** not verified, **F** failed (a finding, not a pass).

## What is live

- `openclaw-gateway.service` installed (`/etc/systemd/system`), **started by hand, disabled at boot**,
  docker container `openclaw-gateway`, `--network host`, `--bind loopback --auth token`, port from
  `/opt/openclaw/gateway/gateway.env`.
- Own state dir `/var/lib/openclaw-gateway/state` (never `/opt/openclaw/config`), config
  `/opt/openclaw/gateway/config/openclaw.json` mounted read-only (not hot-reloaded), per-role workspaces
  under `/opt/openclaw/gateway/workspaces` (only the Consultant's `SOUL.md` is populated).
- Token: `/opt/openclaw/secrets/gateway-token.env` (0600) on the VM and the gitignored workstation `.env`;
  row added to `infra/local.secrets-rotation.md` (name only).
- Thin client helper for tests only (`/home/df/gwc.sh`, not in the repo).

## Containment: proactive features

| Feature | Setting | Result |
|---|---|---|
| Heartbeat | `agents.defaults.heartbeat.every: "0m"`, `cron.enabled: false`, `OPENCLAW_SKIP_CRON=1` | V: log `[heartbeat] disabled`; `health` shows every agent heartbeat disabled |
| Scheduled skill reviews | `skills.workshop.autonomous.mode: "off"`, `agents.defaults.skills: []`, `skills.allowBundled: []` | V: before this setting the Gateway had created **5 enabled weekly `skill-collection-review` agent-turn cron jobs** (inert only because cron was off); after it, `cron.list` shows all 10 jobs (5 reviews, 5 heartbeats) `enabled: false` |
| Plugins | `plugins.allow: ["deepseek"]`, `plugins.deny: ["memory-core"]`, `plugins.slots.memory: "none"`, entries only `deepseek` | V: log `http server listening (0 plugins)`. The first config listed 14 plugins (browser, canvas, cua-computer, device-pair, file-transfer, geolocation, codex, memory-core ...) and logged `codex`/`memory-core` "enabled automatically": those two were triggered by my own `plugins.entries.codex`/`memory-core` config entries. Removed. The DeepSeek provider still works (provider is not a listed plugin) |
| Control UI, terminal | `gateway.controlUi.enabled:false`, `gateway.terminal.enabled:false` | V: config accepted; N: not probed over HTTP |
| Channels, hooks, gmail | none configured | V: startup outcomes `hooks-disabled`, `not-configured` |
| Auto-update check | `update.checkOnStart: false` | config accepted |
| Config reload | `gateway.reload.mode: "off"` | accepted; each hand restart logged `config reload superseded`, no live apply |
| health-monitor | built in, 300 s | V: it is a channel-health monitor; with no channels it has nothing to restart; no model call in the journal from it |

Tool containment inside the Gateway: **V**. `systemPromptReport.tools` for a Consultant turn lists exactly 29
tools, all `df-consultant__*` (no exec, browser, shell or file tools), matching `agents/consultant/tools.yaml`;
`skills: []` after the change (14 bundled skill blurbs were in the prompt before it). Charter: `SOUL.md` is
injected (6,661 chars); `AGENTS.md`, `IDENTITY.md`, `BOOTSTRAP.md` report `missing` and inject only a short
placeholder line (76, 78, 0 chars), no template text.

## S0 checks

| Check | Result |
|---|---|
| Token auth through the CLI client | **V.** No token: `gateway_credentials_required`. Wrong token: `AUTH_TOKEN_MISMATCH`. Right token (via `--env-file` with `OPENCLAW_GATEWAY_TOKEN`, never argv): `gateway call health` and `agent` work. The `/startupz` probe needs no auth and returned `{"ok":true,"status":"started"}` |
| `--model` accepted under token auth | **V.** `agent --model deepseek/deepseek-v4-flash` ran to `status: ok` (the `agent` call asks for admin scope; it was granted) |
| One real MCP tool call in a Gateway turn | **V.** `df-consultant__doctrine__get` called once, `toolSummary {calls:1, tools:[...], failures:0}`, dfmcp journal shows the call with `role: consultant`, `tool_id: doctrine.get`. First turn 9.6 s wall, 7.1 s model, 2 assistant turns, usage in 14,795 / cacheRead 12,032 / out 321, cost $0.0022. `${ENV}` in the MCP `Authorization` header and in the MCP `url` both resolve (the Gateway reached dfmcp). Raw envelope: `conductor/tests/fixtures/gateway/agent_turn_mcp_tool_call.json` |
| `chat.history` shape | **V.** Object `{sessionKey, sessionId, messages[], pendingInputs, deltaCursor, hasMore, totalMessages, defaults, sessionInfo, thinkingLevel}`. Messages for the turn: `user`, `assistant` (blocks `thinking`, `toolCall`), `toolResult` (text blocks, `isError`), `assistant` (`thinking`, `text`). Fixture: `chat_history_after_tool_call.json` |
| `sessions.abort` | **F.** From a separate `gateway call` client it returned `INVALID_REQUEST unauthorized` three times (`sessions.abort` twice, `chat.abort` once; also with explicit `--url` and `--token`), while `sessions.list` showed the run `hasActiveRun: true`. The abort handler refuses a requester that does not own the run and is not admin; the shared-token `gateway call` client is neither here. Fixture: `sessions_abort_unauthorized.json`. **What does work:** SIGTERM of the `agent` client container (what the conductor's outer kill does). V: client exit 143, session status `killed`, `abortedLastRun: true`, and the dfmcp journal shows the last Consultant call 1.2 s before the TERM and none after, so the Gateway stopped the run. Design consequence: the conductor must abort by killing its own client (section 5.4's first step); the `sessions.abort` "belt" does not work with this auth and must be dropped or redesigned |
| Kill mid-turn, restart, wipe | **V (partly).** `docker kill` of the Gateway mid-turn: the `agent` client got `gateway closed (1006)` plus the "Gateway may still be running this turn" text (fixture `transport_loss_stderr.txt`), systemd restarted the unit in 10 s (`NRestarts=1`), `/startupz` started 40 s later. The `ExecStartPre` wipe deleted the per-agent session database (listing after the restart showed none) and no recovery or resume line appeared in the log. After the wipe the doctor logged "Removed missing agent database registry entry" and "Startup migration warnings; continuing with degraded state": harmless but visible, and a candidate for a one-time `openclaw doctor --fix` |
| Does a dfmcp restart refresh cached tool lists? | **Partly.** Restarting `dfmcp-server.service` makes the Gateway log `[bundle-mcp] server "..." closed; next request reconnects` (once per role server), and the next turns on both a new key and an existing key succeeded with a tool call. **N:** whether the reconnect also re-lists tools could not be shown, because no tool definition changed. Keep the manifest rule (restart the Gateway after a dfmcp deploy) |
| Charter caching | **V: not cached.** Appending a line to `SOUL.md` changed the next turn's `SOUL.md` rawChars (6,661 to 6,700) and system-prompt hash on both an existing key and a new key; restoring it changed it back. A charter deploy needs no Gateway restart (a cold prefix is still paid) |
| Resident memory | **V.** 464 MiB at the first idle sample, 428 MiB after turns, 312 MiB after a clean restart (container, `docker stats`); VM total 1.97 GiB, about 1.0 GiB available while it ran. Tight if all five roles' sessions get long; re-measure after the 24 h canary |
| Restart recovery | **V:** the unit wipes `agents/*/agent/openclaw-agent.sqlite*` at start. `find` reports "No such file" harmlessly on the first ever start (the `-` prefix ignores it) |
| `${ENV}` in MCP `url` | **V** (see MCP row) |
| Provider/session stall watchdog | N: no `session.stalled` seen in a 30-call, 75 s turn |

### Test hygiene: what the long turn was

During S0 I ran a deliberately long test turn (30 sequential `doctrine.get` calls, 240 s timeout) to have
something to abort. Because `sessions.abort` was refused, three such turns ran to completion (about 75 to 90 s
each, not 10 minutes), and the 03:23:45 container exit with status 137 was my own `docker kill` for the
kill-and-restart test, not a timeout or OOM (`dmesg`/journal show no OOM). Cost of all S0 turns: well under $0.05.
Later tests used a 60 s timeout and one call.

## Isolation from the one-shot runs (checked after a conductor cycle overlapped S0)

A one-shot Quartermaster run in a `--once` cycle (03:30:55 to 03:34:56Z) was recorded `status: error`,
241 s, no usage, empty error. Findings:

- **Not the Gateway.** The Gateway mounts only `/var/lib/openclaw-gateway/state`,
  `/opt/openclaw/gateway/config/openclaw.json` (read-only) and `/opt/openclaw/gateway/workspaces`; the one-shot
  runs mount `/opt/openclaw/config`, their pinned config dir and `/opt/openclaw/<role>-workspace`. No shared
  directory, lock file or port (one-shot containers are on the default bridge; the Gateway is on the host
  network, loopback, and the one-shot runs never open a listener). Files under `/opt/openclaw/config` changed only
  at the one-shot runs' own times (03:30:54 to 03:34:56), none at the Gateway's start times.
- The run was alive and working the whole time: the dfmcp journal shows the Quartermaster making reads and
  filing (`queue.propose` accepted 03:34:25, `gotchas.write` 03:34:46) until 03:34:46, and the container exited
  at 03:34:56, so the run completed its work and the conductor got no parseable envelope.
- **One thing of mine overlapped it:** at about 03:34:15 I restarted `dfmcp-server.service` for the tool-list
  check, not knowing a cycle was in flight (I did not check the conductor first; I should have). The
  Quartermaster's next call at 03:34:20 succeeded, so it survived, but a restart under a live cycle was wrong and
  is listed here as a mistake. The cause of the empty envelope is **not established**; it needs the run's own
  stdout, which the archive does not keep (`raw: null`).

## Idle canary

- Script: `scripts/ops/gateway_idle_canary.sh` (copied to `/home/df/gateway_idle_canary.sh` on VM 106).
- **Started 2026-10-09T03:35:34Z** (after the final restart with the final config; start time stored in
  `/var/lib/openclaw-gateway/canary-start`). The 24 h window ends 2026-10-10T03:35:34Z.
- Read it: `scripts/vm-ssh.sh openclaw '/home/df/gateway_idle_canary.sh check'`. PASS needs: unit active; zero
  model calls and zero agent runs in the Gateway journal since the start; zero sessions touched; zero enabled
  cron/heartbeat jobs. It counts only Gateway-originated activity, so one-shot conductor cycles
  may keep running during the window. There is deliberately no dfmcp-journal check: one-shot runs
  use the same VM, address and role tokens, and the journal cannot tell the two apart.
- No turns may be sent through the Gateway during the window (they would count as a FAIL); a Gateway restart inside the window
  restarts the clock (the script reports `gateway starts inside window`).
- First check at 03:35:38Z: PASS (0 model calls, 0 agent runs, 0 sessions, 0 enabled jobs, 312 MiB).

## Fixtures

`conductor/tests/fixtures/gateway/` (scrubbed: no token, no address; `df-consultant` is the MCP server name):
`agent_turn_mcp_tool_call.json` (the full `agent --json` reply envelope: `{runId, status, summary, result:{payloads, meta}}`),
`chat_history_after_tool_call.json`, `sessions_abort_unauthorized.json`, `auth_wrong_token.txt`,
`transport_loss_stderr.txt`. Not captured: an inner-timeout envelope, a provider-error envelope (the one-shot
route's timeout shape is in `evals/live/2026-10-07-openclaw-multiturn`).

## Open items for the next streams

1. Drop or redesign the `sessions.abort` belt (it is `unauthorized` for this client); the client SIGTERM is the abort.
2. The `agent` reply envelope's `meta.systemPromptReport` is about 15 KB of the 18 KB; the mapper should ignore it.
3. Quartermaster empty-envelope cause (above) is open.
4. Whether `openclaw doctor --fix` on the Gateway state is wanted once (startup migration warning after the wipe).
