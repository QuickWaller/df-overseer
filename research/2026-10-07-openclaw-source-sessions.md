# openclaw source dive: sessions, resets, prompt, queue, aborts, compaction, driver

Date: 2026-10-07. Read-only. Source read from shallow clones of
`openclaw/openclaw`: tag `v2026.9.4` (commit 3a9d69db, 2026-09-10, "tag") and main
(commit af716af2, 2026-10-06, "main"). Paths are repo-relative; line numbers are from
the tag unless marked main. The installed image is `:latest`, last recorded 2026.9.4.
The live test (`evals/live/2026-10-07-openclaw-multiturn/README.md`) confirmed multi-turn
via `agent --local --session-key` and via the Gateway with `/new`, and a byte-identical
system prompt except the date line. This file covers the source behind that, and the
questions the live test did not (5 to 8).

## Short answers

1. `agent exec` mints `randomUUID()` per call and has no session flag; `agent` does
   (`--session-key`, `--session-id`), via the Gateway or `--local`. Same key appends to
   the same transcript. History is per-agent SQLite.
2. `/new` and `/reset` rotate the transcript window and keep the key. Default reset mode
   is `none`; `daily` and `idle` are opt-in.
3. The system prompt has few volatile fields: date (below the cache boundary), Runtime
   line (relocated to the first user turn on OpenAI-compatible providers). Reasoning
   content is replayed for DeepSeek. Cache can hit across runs and after a reset.
4. Default queue mode is `steer`, cap 20, drop `summarize`. Applies to Gateway and
   embedded chat paths. `exec` and one-shot `--local` have no queue; the per-session
   lane serialises runs.
5. Abort in the Gateway persists a partial assistant message and repairs dangling tool
   calls; the next turn works. `--local` SIGTERM does not send `chat.abort`.
6. `agents.defaults.compaction.enabled: false` disables proactive compaction; overflow
   recovery and manual compaction remain. A "truncate to N lines" API exists
   (`sessions.compact` with `maxLines`) but keeps the tail, not the system prompt; the
   cleaner way is `sessions.reset`, which keeps the key and rebuilds the prompt.
7. Yes: a WebSocket Gateway protocol with `agent` plus `agent.wait`, `sessions.send`,
   `sessions.abort`, `sessions.reset`, and a private SDK `@openclaw/sdk` wrapping them.
8. Risks: exclusive state ownership, per-session serialisation, unbounded history with
   a 1M window, no compaction below about 980k, stale tool state, and Gateway auth.

## 1. Session lifecycle (confirmed in source)

- `agent exec`: `src/commands/agent-exec.ts:217` `const sessionId = randomUUID();`,
  passed to `runAgent({ message, sessionId, ... })` (about `:425`) with no `sessionKey`
  unless `timeoutMs`/`maxToolCalls` deps are set (then a synthetic
  `agent:<id>:agent-exec:<uuid>` scope key, `:359-362`). The exec options
  (`src/cli/program/register.agent-turn.ts:109-135`) have no session flag. Same on main
  (`agent-exec.ts:176`). `--state-dir` retains the SQLite but each call is a new session;
  it takes an exclusive embedded state lock (`agent-exec.ts:371-381`).
- `agent`: options `--session-key`, `--session-id`, `--agent`, `--local`, `--json`,
  `--timeout` (`register.agent-turn.ts:23-52`). Key shape `agent:<id>:<key>`; a bare key
  is scoped to `--agent` (`src/commands/agent-via-gateway.ts:559-586`, docs
  `docs/cli/agent.md:372`).
- Gateway path: RPC `agent` with `sessionKey`, `idempotencyKey`, `timeout`,
  `expectFinal: true` (`agent-via-gateway.ts:1099-1121`). `--local` path: takes
  `acquireEmbeddedAgentStateLock` and runs the embedded `agentCommand` (`:1285-1311`).
- Resolution: `src/agents/command/session.ts:580-683` `resolveSession`. With an existing
  entry that is "fresh" it reuses `sessionEntry.sessionId` (`:653-654`); otherwise a new
  UUID, `isNewSession = !fresh && !requestedSessionId` (`:655`). **A second call with the
  same key appends to the same conversation unless the reset policy marks it stale.**
  `--session-id` alone synthesises key `agent:<id>:explicit:<id>` (`:170-175`).
- Storage: per-agent `agents/<id>/agent/openclaw-agent.sqlite`
  (`docs/concepts/session.md:253`). Schema `src/state/openclaw-agent-schema.sql`:
  `session_nodes` (key, `current_session_id`, `entry_json`, `:15`), `session_windows`
  (one row per transcript id, `previous_session_id`, `reason` in
  initial/reset/rollover/fork/rewind/switch/recovery/compaction, `:116`),
  `transcript_events` (`session_id, seq, event_json`, append-only tree, `:393`),
  `session_transcript_active_events` (active path projection, `:677`). Main adds cold
  archive and FTS row tables. Docs: `docs/reference/session-management-compaction/store.md`.
- Load into next request: the embedded runner takes the active branch of the transcript,
  sanitises it by provider policy (`src/agents/embedded-agent-runner/replay-history.ts:
  600-700`), applies `limitHistoryTurns` and re-pairs tool calls
  (`run/attempt-history-prepare.ts:121-160`), then sends system, tools, messages.
- Docs vs code: docs say exec "retains sessions" with `--state-dir`
  (`docs/cli/agent.md:42`); code agrees, but with a new id each call. No discrepancy.

## 2. Reset

- Policy: `src/config/sessions/reset-policy.ts:22` default mode `none`; `:83-85` `none`
  returns fresh forever; `daily` stale when the session started before the last
  `atHour` (default 4, `:23`); `idle` stale after `idleMinutes` since last real
  interaction (`:92-101`). Heartbeat, cron and exec events do not extend freshness
  (`docs/concepts/session.md:179-182`). `updatedAt === 0` is a one-time reset tombstone
  (`:80`).
- Manual: `/new` and `/reset` in chat, or RPC `sessions.reset {key, reason: new|reset,
  expectedSessionId?}` (`packages/gateway-protocol/src/schema/sessions.ts:512-517` main;
  handler `src/gateway/server-methods/sessions-mutations.ts:609` main, scope
  `operator.admin`, `core-descriptors.ts:258` main). The CLI treats a leading `/new` or
  `/reset` message as needing admin scope (`agent-via-gateway.ts:506-508,1073`).
- Effect (main `src/gateway/session-reset-service.ts:1058-1320`): appends a `reset`
  boundary event to the old window with `context: "clear"` (`:1067-1071`), then writes a
  fresh entry: new `sessionStartedAt`, `systemSent: false`, `compactionCount: 0`, token
  counters 0 (`:1146-1250`). **The key is kept and a new window (sessionId) begins**; I
  did not trace the function that rotates the id (the live test observed it). Old
  transcript stays in SQLite (`archivePreviousTranscript: false`, `:1064`). User-chosen
  model/auth overrides survive, automatic fallbacks are cleared
  (`src/config/sessions/reset-preserved-selection.ts`). Thinking, verbose and queue
  overrides are carried (`:1152-1186`).
- System prompt after reset: rebuilt from scratch every request (the stored-prompt
  "series" feature is Anthropic-only, see 6); identical inputs except date and, in the
  tag, `sessionId=` in the Runtime line, which is relocated out of the system message
  for DeepSeek (see 3). Matches the live test.

## 3. System prompt and DeepSeek cache

Built by `buildSystemPrompt` in `src/agents/system-prompt.ts` (tag). Order, as one string:

1. Stable prefix (`:1183-1414`, cached by key via `cacheStablePromptPrefix`): "You are a
   personal assistant...", `## Tooling` with tool lines in the fixed `toolOrder`
   (`:915-976`, extra tools sorted), tool-call style, safety, runtime-context rules,
   OpenClaw control, skills, memory, directory/workspace (`:1079-1085`), docs, Project
   Context files, then `SYSTEM_PROMPT_CACHE_BOUNDARY` (`:1412`).
2. Volatile suffix: `## Temporal Context` first (`:1420`; `Current date: YYYY-MM-DD`,
   `Time zone`, from `src/agents/date-time.ts:81-98`; date only, no clock time), then
   project memory, delegation, silent replies, exec approval, user identity, messaging,
   extra system prompt, watched sessions (`:1423-1549`).
3. `## Runtime` tail (`:1551-1560`): reasoning line, then a relocatable region holding
   `buildRuntimeLine` (`:1565-1608`): `name | agent | session=<key> | sessionId | host |
   repo | os (arch) | node | model | default_model | shell | channel | capabilities`.
   Per-run fields: `host=` (the conductor pins `--hostname <role>`), `sessionId=` (tag
   only; main drops it, `src/agents/system-prompt-runtime.ts:15-16`), `model`. Cron run
   suffixes are stripped (`:1574-1576`).
4. Transport (`packages/ai/src/openai-completions-messages.ts:78-98,308-355`): for an
   OpenAI-compatible provider (DeepSeek's api is `openai-completions`,
   `extensions/deepseek/models.ts:12`) the Runtime region is cut out of the system
   message and appended to the first following user turn, so the system message is the
   stable part plus the dated suffix. The date is therefore the only per-day change in
   the system message, matching the live test.

Request body (`packages/ai/src/transports/openai-completions-params.ts:352-460`):
`messages` (system, history, new user turn), `tools` sorted by name (`:280`,
`sortTransportToolsByName`), `stream_options.include_usage`, optional
`prompt_cache_key` (`:379-380`). DeepSeek caches by exact prefix; the date sits late in
the system message, so a date change invalidates everything after it (tools as the
provider orders them, and all history), while same-day runs and a `/new` reset share the
prefix, as the live test measured.

`reasoning_content`: replayed. `extensions/deepseek/index.ts:36-41` (main) uses the
openai-compatible replay family with `dropReasoningFromHistory: false`;
`src/plugin-sdk/provider-stream-shared.ts:436-476` backfills `reasoning_content: ""` on
assistant messages and `:479-514` sets `thinking: {type: enabled}` plus
`reasoning_effort` (main line numbers). With thinking off the field is stripped
(`docs/providers/deepseek.md`). The tag reads the level from `params.thinkingLevel` only;
main also honours `options.reasoning`.

## 4. Inbound queue (`docs/concepts/queue.md`, main; the tag is nearly the same)

- Modes (`:38-47`): `steer` (default, inject into the active run), `followup` (run after),
  `collect` (coalesce into one followup), `interrupt` (abort active, run newest).
- Defaults (`:27-36`): `steer`, 500 ms debounce, `cap: 20`, `drop: "summarize"`
  (`old` and `new` also exist, `:87-89`). Per-session `/queue ...` override (`:127-131`),
  config `messages.queue` (`:59-73`).
- Lanes: per-session lane `session:<key>` serialises everything touching a session
  (`:21,202`); global `main` lane capped by `agents.defaults.maxConcurrent` (`:22,197`).
- Entry points: the Gateway reply pipeline; `openclaw chat` and `tui --local` apply the
  same four modes in the embedded runtime (`:161-166`). An `agent --local` or `agent
  exec` process has no pending queue: it takes the state lock, runs one turn, exits. A
  second `agent` call to a Gateway session while a run is active goes through the lane,
  and a repeat with the same idempotency key returns `status: "in_flight"`
  (`src/gateway/agent-turn/agent-dedupe.ts:215`).
- Tag to main delta: main adds operator-scope rules for collect and steer, cancelled
  queued request semantics, and larger `main` lane concurrency.

## 5. Timeouts and aborts

- Exec: deadline default 600 s (`agent-exec.ts:38`), timeout exit code 2, error envelope
  `status: "timeout"` (`:66-68,178-193`). Exec state is temporary unless `--state-dir`.
- `agent` timeout: `--timeout` default 600 s on the CLI, 48 h for ordinary Gateway turns
  (`docs/cli/agent.md:337`; `src/agents/timeout.ts:13`). `0` disables.
- Gateway abort: `chat.abort` and `sessions.abort` capture the partial assistant text
  before signalling (`src/gateway/server-methods/chat-aborted-partial.ts:58-111`, main)
  and persist it as an assistant message with `abortMeta {aborted: true, origin, runId}`
  (`:94-110`, idempotency key `<runId>:assistant`). A failed partial save is a warning on
  the abort reply, not a blocker (`:112-114`). Stop or timeout also cancels recovery and
  retries (`docs/concepts/compaction.md:46`, main).
- Dangling tool calls: `installSessionToolResultGuard` synthesises missing tool results
  (`src/agents/session-tool-result-guard.ts:213`, `allowSyntheticToolResults` default
  true; aborted and error assistant turns are not counted as pending, `:76-83`, main).
  At replay, `sanitizeToolUseResultPairingForModel` drops errored assistant frames
  (`erroredAssistantResultPolicy: "drop"`, `session-transcript-repair.ts:288-295,351`) and
  inserts synthetic error results for missing ids (`:359-370`), main. On the next turn
  `isInterruptedTurnEntry` recognises aborted turns
  (`embedded-agent-runner/run/pre-persisted-user-turn.ts:30-60`, main) so the original
  user message is reused rather than duplicated.
- Prompt timeout inside a turn: a final error payload "Request timed out..." with
  `replayInvalid` metadata (`run/terminal-timeout.ts:55-117`, main); history keeps what
  was persisted. The next turn works (by this code; not run).
- Signals: `agent` via the Gateway on SIGTERM or SIGINT sends `chat.abort` for an accepted
  run; **`--local` does not** (`docs/cli/agent.md:375`). Transport loss to the Gateway is
  ambiguous and the CLI never reruns the turn (`:374`); keep the idempotency key and call
  `agent.wait`.
- Gateway restart: an interrupted turn is resumed with its recorded tool calls and
  results (`docs/concepts/session.md:209-249`); three failed starts exhaust the budget,
  then `/new` or `/reset`. A standalone `--local` refuses to reuse a main session while
  recovery is pending (`docs/cli/agent.md:370`).

## 6. Compaction and pruning

- Default: auto-compaction on, near the context limit or on overflow error; default
  `mode: "safeguard"` for new configs (`docs/concepts/compaction.md:26,40`). Reserve
  floor 20,000 tokens, `keepRecentTokens` 20,000 (`:98`). Trigger code not read, so
  about 980k on a 1M window is inferred.
- Disable: `agents.defaults.compaction.enabled: false` stops proactive threshold
  compaction and optional maintenance; overflow-recovery compaction and manual `/compact`
  remain (`:56` main, `:47` tag). Pruning is a separate setting, off unless
  `agents.defaults.contextPruning.mode: "cache-ttl"` (`docs/concepts/session-pruning.md:29`);
  it rewrites old messages, which would break the prefix cache.
- A timed-out summary commits compaction with no summary and loses older facts
  (`compaction.md:48-50`).
- Truncate API: Gateway RPC `sessions.compact {key, agentId?, maxLines}` and
  `openclaw sessions compact <key> --max-lines N` permanently truncate the SQLite
  transcript to the last N lines, no backup (`docs/cli/sessions.md:507-540`, main; the tag
  has it at `:365-372`). It keeps the tail, not "system prompt only", and for DeepSeek the
  system prompt is not stored in the transcript anyway (rebuilt per request). To drop
  history use `sessions.reset`. `/compact` as an `agent --message` is refused
  (`agent-via-gateway.ts:1271-1276`).
- The stored system-prompt "series" entries (`openclaw.system-prompt`) apply only when
  `inHistorySystemUpdates` is true, which is set only for direct Anthropic
  (`src/agents/transcript-policy.ts:230-238`, main). Not used for DeepSeek.

## 7. A programmatic driver

Facts:
- The Gateway is a WebSocket server. Handshake: server event `connect.challenge`; client
  request `connect {minProtocol, maxProtocol: 4, client{id,mode}, role: "operator",
  scopes: [operator.read, operator.write], auth{token}}`; reply `hello-ok`
  (`docs/gateway/protocol/handshake.md:10-110`, main). Frames are `req`, `res`, `event`.
- Methods (main `src/gateway/methods/core-descriptors.ts:248-249,258,363-382`): `agent`
  (dynamic scope), `agent.wait` (`operator.write`), `sessions.send`, `sessions.abort`,
  `sessions.reset` (`operator.admin`), `sessions.compact`, `chat.send`, `chat.abort`.
- `agent` params (`packages/gateway-protocol/src/schema/agent.ts:289-330`, main):
  `message`, `agentId`, `sessionKey`, `model`, `thinking`, `timeout` (integer seconds),
  `lane`, `extraSystemPrompt`, `idempotencyKey`. Reply carries `runId`, `status`,
  `result`.
- `agent.wait {runId, timeoutMs}` (`:379-382`) blocks until the run ends or the wait
  expires; handler `src/gateway/server-methods/agent.ts:19-61`. Statuses seen in source:
  `ok`, `error`, `timeout`, `in_flight` (`agent-turn/agent-dedupe.ts:78,149,215`).
- Private SDK `packages/sdk/src/client.ts` (main; `@openclaw/sdk`, `private: true`,
  `0.0.0-private`, so not on npm): `new OpenClaw({url, token})`;
  `runs.create({agentId, sessionKey, input, timeoutMs})` (`:532-544`) calls `agent` with
  `expectFinal: false` and returns a `Run`; `Run.wait({timeoutMs})` (`:393-416`) calls
  `agent.wait` with no client request timeout; `Run.cancel()` calls `sessions.abort`
  (`:418-423`); `Session.send` uses `sessions.send` (`:433-450`); `Session.compact`
  (`:463-470`); `Run.events()` streams events. The reference client closes the socket on
  tick-watchdog silence and reconnects (`docs/gateway/protocol/versioning.md:66-70`).
- Non-WebSocket JSON: `agent --json` prints one envelope per call; exec's stable
  envelope is `{ok, status, final, payloads, usage, costUsd, toolSummary, sessionId}`
  (`docs/cli/agent.md:83-103`). No streaming JSON from the CLI.

Minimal driver (proposed, not run):
1. Own one long-lived `gateway run --bind loopback --auth token` container (the live test
   used `--auth none`); mount the per-role pinned config and persisted auth/plugin state.
2. Per wake and role: connect; if a clean context is wanted call
   `sessions.reset {key, reason: "new"}` first (admin scope); `agent {agentId,
   sessionKey: "agent:<role>:wake", message: <briefing>, timeout: 600, idempotencyKey:
   <wake-uuid>}`; take `runId`; `agent.wait {runId, timeoutMs}`; for each follow-up send
   `agent` again on the same key (it serialises in the session lane) and wait again.
3. On wait timeout call `sessions.abort {key, runId}`, then read the partial reply.
Alternative with no Gateway: one `docker run ... agent --local --session-key ...` per
message (live-tested; 7 to 9 s of overhead each).

## 8. Risks of per-role long-lived sessions

- Single owner of a state dir: `--local` and exec with `--state-dir` refuse to start while
  a Gateway or another embedded writer holds it (`docs/cli/agent.md:42,369`;
  `src/infra/embedded-state-lock.ts`). Overlapping conductor invocations on one role
  would collide; give each role its own state dir.
- Per-session serialisation: one run per session at a time (`queue.md:202`). Set the queue
  mode explicitly (`followup` or `collect`); the default `steer` injects into a running
  turn.
- Unbounded growth: default no auto reset, a 1M window, compaction not before about 980k;
  session maintenance prunes sessions after 30 days or 5000 rows, not turns
  (`docs/concepts/session.md:282-299`). A long session gets dearer and degrades first.
- Gateway process state: memory and SQLite WAL growth in one long process, warm MCP
  loopback resources (`docs/cli/agent.md:368`), restart-recovery budget of 3.
- Auth: a Gateway needs real `gateway.auth`; the live test used none on loopback.
- Cache coupling: the date changes daily; pruning rewrites the prefix; charter or tool
  changes invalidate a carried prefix (see `research/2026-10-07-persistent-sessions.md`).
- Stale beliefs: replayed tool results describe an old fort.
- Tag to main drift (queue, reset service, `sessionId` in the Runtime line) means
  behaviour may differ by image; pin the image.

## Not verified

- The installed image version (docker not inspected); findings are tag 2026.9.4 and main.
- How the session id is rotated on `/new` (not traced; observed live).
- Compaction trigger arithmetic (inferred from docs and the 20k constant).
- The order of `tools` versus `messages` in DeepSeek's template, and whether
  `prompt_cache_key` is sent for DeepSeek (`supportsPromptCacheKey` compat not read).
- Behaviour of a hard-killed `--local` run (stale state lock), and abort mid-thinking
  replay on DeepSeek.
- Gateway `agent` reply fields beyond `runId`, `status`, `result`, and token auth setup;
  nothing here was run.
- Some line numbers are approximate to a few lines (marked "about").
