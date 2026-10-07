# Can the conductor push several messages into one openclaw session per wake?

Date: 2026-10-07. Live experiment on the agent VM (VM 106), openclaw 2026.9.4 image
(the conductor's `ghcr.io/openclaw/openclaw:latest`), model `deepseek/deepseek-v4-pro`.
A THROWAWAY agent ("tester"): no MCP servers, no fort tools, no fort token, its own
temp dir under `/tmp`, the DeepSeek key read by name only into a 0600 file in that
dir. The fort, dfmcp, `conductor.service`, the conductor's state and the real role
configs were not touched; the conductor was not run. Everything was removed after
(temp dir gone, no containers, no stray processes; checked).

## Verdict

**Yes, with caveats.** Two working routes, both tested:

1. **`agent --local --session-key <key>`**, one `docker run --rm` per message, state
   dir retained between calls. The session carries context across calls. Works, but
   about 7 to 9 s of process overhead per message.
2. **Gateway mode** (`gateway run` in one long-lived container, `agent --session-key`
   as a thin client per message). Same carrying, about 2 s overhead per message, and a
   real `/new` reset that keeps the session key. Needs a long-lived process the
   conductor owns, with real `gateway.auth` (tested only with `none` on loopback).

Neither needed any change to the prompt or tools. A pushed follow-up turn costs
about $0.0002 to $0.0005 because the whole prefix is read from DeepSeek's cache, and
the cross-run cache hits too, in both routes (see the system prompt section).

## Commands (redacted)

Help (read-only): `docker run --rm --entrypoint node <image> openclaw.mjs agent --help`
and `... agent exec --help`, `sessions --help`, `gateway --help`. Session flags are on
`agent`, not `agent exec`: `--local`, `--session-key <agent:<id>:<key>>`,
`--session-id`, `--message/-m`, `--message-file`, `--json`, `--timeout <s>`,
`--model`, `--thinking`. `agent exec` has no session flag (consistent with
`research/2026-10-07-persistent-sessions.md`).

Local route, one call per message (same key every call):

    docker run --rm --hostname tester --user 1000:1000 --entrypoint node \
      --env-file <file holding only DEEPSEEK_API_KEY> \
      -v <tmp>/state:/home/node/.openclaw \
      -v <tmp>/openclaw.json:/home/node/.openclaw/openclaw.json:ro \
      -v <tmp>/ws:<tmp>/ws \
      <image> openclaw.mjs agent --local --session-key agent:tester:<S> \
      --model deepseek/deepseek-v4-pro --json --timeout <s> -m "<message>"

Gateway route:

    docker run -d --name <gw> --network host ...same mounts... <image> \
      openclaw.mjs gateway run --port <p> --bind loopback --auth none --allow-unconfigured
    # per message, a second short container with --network host and its own empty
    # state dir:
    openclaw.mjs agent --session-key agent:tester:<S> --model ... --json --timeout <s> -m "<message>"

Setup lessons (both routes): the temp state dir needed the deepseek provider plugin
copied from the conductor's state dir (`npm/`, copied, the original untouched), and
the config needs `models.providers.deepseek.apiKey = {source: env, provider: default,
id: DEEPSEEK_API_KEY}` (without it: "requires an explicit base URL" error). The real
pinned configs do not carry this; they rely on the persisted auth store, so a
session route would keep mounting that state dir.

## Results

Wall is the whole `docker run` as seen from the shell; "model" is `meta.durationMs`
from the envelope. Overhead = wall minus model.

### Local route (`agent --local --session-key`)

| Turn | Message | Reply | Wall s | Model s | Overhead s | input | cacheRead | output |
|---|---|---|---|---|---|---|---|---|
| 1 | remember PELICAN | OK | 14.6 | 6.4 | 8.2 | 39514 (2 calls) | 22784 | 293 |
| 2 | what was the code word | PELICAN | 11.8 | 2.7 | 9.1 | 127 | 31232 | 5 |
| 3 | reasoning (farm arithmetic) | correct working, 117.61 | 14.3 | 6.7 | 7.6 | 235 | 31232 | 686 |

Turn 2 recalled PELICAN with no tool call (assistantTurns 1), so context carried in
the session. Turns 2 and 3 read about 31k tokens from cache and paid for roughly 130
to 240 uncached input tokens. Turn 1 was partly cold (the very first session) and the
agent used its built-in memory tool (see the tool section).

Overhead per local message is 7 to 9 s (container start, plugin load, sqlite open),
against model times of 2 to 7 s: process start dominates short turns.

### Gateway route (long-lived gateway, thin client per message, 60 s gaps)

| Turn | Message | Reply | Wall s | Model s | Overhead s | input | cacheRead | output |
|---|---|---|---|---|---|---|---|---|
| 1 | remember OTTER | OK | 7.3 | 4.7 | 2.6 | 324 | 30208 | 150 |
| 2 (+60 s) | code word? | OTTER | 4.2 | 2.0 | 2.2 | 258 | 30464 | 22 |
| 3 | `/new` | "New session started." | 2.3 | 0 | 2.3 | n/a | n/a | n/a |
| 4 | code word? | UNKNOWN (reset worked) | 4.2 | 2.1 | 2.1 | 325 | 30208 | 48 |
| 5 | reasoning (primes) | correct | 6.0 | 3.8 | 2.1 | 166 | 30464 | 340 |

Overhead per gateway message is about 2 s, mostly the client container start.

### Timeout behaviour (local route, `--timeout 1`)

The turn returned rc=1 after 9.5 s wall with an error payload ("Request timed out
before a response was generated", isError true) and `meta.error.kind =
incomplete_turn`, `livenessState = paused`, no usage block. The session was still
usable: the next turn on the same key answered PELICAN correctly. The timed-out
user message stays in the history (the next turn's uncached input rose from 127 to
913 tokens), so a timed-out prompt is not forgotten and the model may see it. The
inner deadline fired at about 0.9 s; the rest of the 9.5 s was process overhead. Not
tested in gateway mode.

## Addition A: wiping history while keeping the session

| Method | Result |
|---|---|
| `/reset` or `/new` as a message to `agent --local` | Not a command there. Treated as ordinary text, same session id, history kept. Do not use. |
| Delete message rows in the agent sqlite (`transcript_events`) | Breaks the store: a foreign key check on `session_transcript_active_events` / `transcript_event_identities` fails and every later call errors. Deleting those rows too still failed. Not viable. (The throwaway db was wiped and rebuilt.) |
| Config `session.reset = {mode: idle, idleMinutes: 1}` with `--local` | Works: after a 75 s gap the same key got a new session id and a clean history (turn 2 recalled MARMOT, the turn after the gap answered UNKNOWN). Turn after reset: input 283, cacheRead 30720, output 44. It is gap-driven, not on demand. |
| Gateway `agent --session-key ... -m "/new"` | Works, on demand. Reply "New session started." (2.3 s, no model call). The next turn answered UNKNOWN with cacheRead 30208 of about 30.5k total, input 325. The envelope still reports the old session id on the turn after, so detect the reset by the reply text, not the id. |
| Fresh `--session-key` per reset | Trivially works and is the safest local-route reset: a new key starts at the system prompt, and the cross-run cache hits (first calls of fresh keys read 30720 cached). |

So reset without compaction is available and cheap, and the system prompt prefix is
read from cache after it: cacheRead 30208 to 30720 on the first turn after a reset,
against about 30.5k to 31k total prompt tokens (the whole prefix including tool
schemas), with 283 to 325 uncached input tokens.

Test hygiene caveat: the throwaway agent's built-in memory tool writes notes to its
workspace `memory/` files, and a fresh session loads them. In the first reset
attempts the agent had written PELICAN there, so the "reset" session still knew it
(through a memory read). Later tests told the agent not to use tools and cleared
`memory/`. A fort role with write tools and a workspace would carry the same
cross-session leakage.

## Addition B: long-lived process, gaps, reset between turns, system prompt

Gateway mode is available and worked first time with `--auth none --bind loopback`
in a throwaway container (`--allow-unconfigured`, config `gateway.mode=local`). The
table above is that run: five messages, 60 s gaps, `/new` between turns 2 and 4.
Latency was 4.2 to 7.3 s wall per answered turn (2.0 to 4.7 s model), cacheRead
30208 to 30464 on every turn including the first turn of a new session and the first
after a reset. An earlier gateway run had the 1 minute idle reset configured, which
silently reset the session during the 60 s gap and made "recall" fail: an idle reset
setting can reset a session mid-wake if gaps are long, so leave it unset.

### System prompt capture and what varies

openclaw redacts its own system prompt in its diagnostics, so the prompt was
captured by pointing the throwaway provider `baseUrl` at a local capture server and
reading the request body (two runs, different session keys, minutes apart).

- The request has 52 tool definitions (built-ins), a system message of 27,765 chars,
  and the messages. The two captured system messages and tool lists were byte
  identical across sessions and runs.
- No session id, run id, host name, random id or clock time is in the system
  message. (`--hostname` is irrelevant for this version: no `host=` appears.)
- One per-day item: a `## Temporal Context` block with `Current date: 2026-10-07`
  and the time zone (UTC), in the final DYNAMIC section at the end of the system
  message. It changes once a day and sits after about 27k of stable text, so a day
  change costs only the tail.
- The system message ends with a `## Runtime` line: the model identity and the
  reasoning level. These change only if the model or thinking level changes.
- The first user message is an internal-context block ("Active exec sessions: none",
  "Active Subagents: none"): stable here, but it changes if sub-agents or exec
  sessions are live. The user's own message follows.
- What does vary: workspace files injected into the system message (AGENTS.md,
  SOUL.md, IDENTITY.md, USER.md, memory notes). Notes the agent writes change the
  prompt for later sessions. `systemPromptReport.hash` in the envelope differed on
  every run even though the text was identical, so it is not a proxy for "will the
  cache hit".

Does the cross-run cache hit? Yes in this setup: with identical config and
workspace, new processes and new session keys read 30208 to 30720 tokens from cache
on their first call, including the first call after a reset. Cold starts were seen
only after longer idle (cacheRead 0 once, on the very first gateway call, minutes
after the previous activity). DeepSeek's TTL is best effort and was not measured.

## Tool use inside a pushed turn

openclaw has built-in tools (52 in the request). The throwaway agent wrote the code
word to a workspace memory file during an early pushed turn (that turn had
assistantTurns 2, and the file was found afterwards containing PELICAN), and later
turns and fresh sessions read it back. So a tool call inside a pushed turn works and
its effect is visible to later turns. Not tested with MCP tools (out of scope).

## What the conductor would need

- Route. Local: a per-wake state dir and a stable session key
  (`agent:<role>:<wake id>`), one `docker run` per message, messages sent serially
  (the state dir needs exclusive ownership), keeping the `--state-dir` design the
  reasoning capture already uses. Gateway: one gateway container per wake, a client
  call per message, torn down at wake end, with real gateway auth.
- Flags: `agent --local --session-key agent:<id>:<key> --json --timeout <s>
  -m|--message-file`, not `agent exec`. `--message-file` exists and avoids argv limits.
- Turn completion: one process exit per message in both routes. rc 0 with a
  `payloads[0]` that is not `isError` is a reply. The local envelope is
  `{payloads, meta}`; the gateway envelope wraps it as
  `{runId, status, summary, result}` with the same `meta`. Read
  `meta.livenessState` (`working` ok, `paused` or `abandoned` bad), `meta.error`, and
  `meta.agentMeta.usage` / `lastCallUsage` (input, cacheRead, output, cost).
- Timeout handling: each message gets its own `--timeout` plus an outer kill with
  grace, as today. After an inner timeout (rc 1, `incomplete_turn`, `paused`) the
  session stays usable but the unanswered prompt stays in history; the conductor
  must choose to resend (the model sees it twice) or reset. An outer kill of a local
  run mid-write, and killing a gateway client mid-turn, were not tested.
- Reset: gateway `/new`; local a fresh session key. Do not rely on `/reset` or `/new`
  in `--local`, on sqlite edits, or on idle reset.
- Overhead budget: about 7 to 9 s per message locally, about 2 s via the gateway.
- Not covered: multi-hour sessions, compaction, concurrent sessions on one gateway,
  gateway token auth, MCP tools through a session, the provider cache TTL. The cost
  and drift arguments in `research/2026-10-07-persistent-sessions.md` are unaffected:
  this shows pushing turns is mechanically possible and cheap, not that it is wise.
