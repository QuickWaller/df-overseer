# Gateway sessions v1: buildable plan and self red team

> **v1.1 (2026-10-09, same day): section 15 revises the session layout** for the
> register row "Session layout: per relevant open proposal; Overseer per wake;
> mid-run news". Where section 15 disagrees with sections 1 to 14 (session keys,
> reset, items, concurrency, rollout, build streams), section 15 wins. Containment,
> supervision, fallback and S0 stand as written.

Date: 2026-10-09. Design spec, read-only: no VM touched, no config changed, no agent
run. Written for the user's register rows of 2026-10-09 (sessions 7: openclaw's
always-running Gateway now, overriding the red team's local-file-first; 8: the inbox
derived from conductor state, no new store; 9: keep today's run limits, 10 min per
run and 20 for the Overseer, no per-turn budget shape; 10: pause stamp on tool
replies, now built in `dfmcp/pause_stamp.py`), plus the 2026-10-09 row making the
conductor the only writer to the game and the 2026-10-08 row "the Overseer rules one
item at a time".

Supersedes, where they disagree: `research/2026-10-08-sessions-design.md` (the
per-wake Gateway container, the inbox store, strikes) and the red team's
"local route first" (`research/2026-10-08-sessions-red-team.md`, M1). Keeps the red
team's two blockers (B1 charter and prompt, B2 envelope) and most of its smaller
fixes, which apply to the Gateway route unchanged.

Confidence key, per claim:
- **[V]** verified in this repo's code or a recorded live run in `evals/live/`.
- **[S]** read in openclaw source or its bundled docs at tag `v2026.9.4` (commit
  3a9d69d, the commit `research/2026-10-09-openclaw-context-audit.md` records as the
  image installed on VM 106), from a sparse clone in a scratch directory, deleted
  after. Read, not run.
- **[I]** inferred, not checked.
- **[gap]** cannot be settled offline; stage S0 (section 11) must answer it.

## 1. Answer

1. **One always-running openclaw Gateway on VM 106, in a docker container under a
   new systemd unit `openclaw-gateway.service`, hosting all five roles as five
   agents.** Loopback only, token auth, its own state directory (never the shared
   one the one-shot runs mount), image pinned by digest, config read-only and not
   hot-reloaded, and every proactive Gateway feature switched off (heartbeat, cron,
   Control UI, operator terminal). The conductor stays the dispatcher; the queue
   stays the only channel between roles.
2. **The conductor talks to it through the openclaw CLI thin client**, one short
   `docker run --rm --network host ... openclaw.mjs agent --session-key ... --json
   --timeout <s> --message-file <f>` per item (about 2 s overhead, proven live), and
   `openclaw.mjs gateway call <method>` for the few RPCs it needs (`chat.history` for
   the transcript, `sessions.abort` for a stuck turn). No Python WebSocket client.
3. **One session per role per wake, keyed `agent:<role>:w<wake_id>`.** A fresh key is
   the reset between wakes: no `/new`, no admin-only reset call, no reply-text
   detection. Inside a wake, items are pushed one at a time, each a new user message
   appended to the session. Proactive compaction off; no idle or daily reset; a
   per-wake prompt-token ceiling (250k) stops the wake and carries the rest.
4. **Items are derived per wake, in memory, from what the conductor already holds**
   (lane pending keys, triage reasons merged into one review item, `pending_brief`,
   open asks, the retry clock). Outcomes are runs-row columns. A failed or timed-out
   item advances that key's existing backoff record. No new store, no strikes.
5. **Run limits unchanged.** The role's 600 s (Overseer 1200 s) is the whole wake's
   budget across all its items; each turn's `--timeout` is what is left of it, plus
   today's 60 s outer grace. No per-item cap, no loop guard.
6. **Gateway down means today's path.** The conductor probes the Gateway's
   unauthenticated `/startupz` at each wake open; anything but "started" runs that
   role through today's `agent exec` one-shot, with one site alert per outage.
7. **Cost: neutral on input, unknown on output.** The Gateway does not warm the
   provider cache across wakes and costs no tokens while idle (once the proactive
   features are off). Within a wake a pushed item reads the whole earlier context
   from cache, as one-shot rounds already do. Output (reasoning) is two thirds of
   cost and is what one-item-per-turn might move; measure it, do not assume it.
8. **Staged rollout**: S0 checks and a 24 h idle canary, then the Consultant alone,
   then the Planner, then the Quartermaster and Architect, then the Overseer in `all`
   mode, then `single`. Per-role policy flag; one-shot stays the default and the
   rollback.

The plain cost of the Gateway, and how each part is contained, is section 9. In one
line: an always-on process that holds every role's credentials and, by default,
starts agent turns on its own; contained by switching that behaviour off, proving it
off with an idle canary, wiping session state at every start, and refusing to
execute any game action that was not recorded inside a wake the conductor opened.

## 2. What changed since the design and the red team

| Topic | 2026-10-08 design | Red team | This plan | Why |
|---|---|---|---|---|
| Transport | Gateway container per role per wake | local `agent --local` first, Gateway later | one always-running Gateway, all roles | decision 7 |
| Inbox | conductor SQLite item store, 8 states, strikes | derive in memory, reuse backoff | derive in memory, reuse backoff | decision 8 |
| Timeouts | role budget plus per-item cap (half) | agree | role budget only, turn wait = remainder | decision 9 |
| Mid-turn push | turn-boundary push; stamp as D8 | recommend stamp | stamp built; turn-boundary line added on top | decision 10 |
| Reset | fresh per-wake state dir | agree | fresh session key per wake, one state dir | always-running process owns one dir |
| Overseer | `single` vs `all` paired experiment | stage it; harness only on evidence | `all` then `single` on live wakes; no grader | 2026-10-08 one-at-a-time row, decision 11 |
| Game writes | Overseer tools wrote directly | n/a | conductor is the only writer | 2026-10-09 row; becomes a containment (9.3) |

## 3. Topology and process model on VM 106

```
conductor.service (python, host)                 openclaw-gateway.service
  |-- probe GET 127.0.0.1:<port>/startupz -------> [container: gateway run --bind loopback --auth token]
  |-- docker run --rm --network host                 state dir: /var/lib/openclaw-gateway/state (own)
  |     openclaw.mjs agent --session-key ...  -----> agents: architect, consultant, overseer, planner, quartermaster
  |     openclaw.mjs gateway call chat.history       workspaces: <role>-workspace/SOUL.md (charter, read-only)
  |-- docker run --rm ... agent exec  (fallback)     MCP: one dfmcp server entry per role, role token each
  `-- dfmcp (VM 103) for queue, briefing, report
```

### 3.1 One Gateway, not one per role

- One process, five `agents.entries`, the five dfmcp server entries in `mcp.servers`,
  each agent's `tools.allow` limited to its own server prefix, as every pinned config
  already does [V, `evals/live/2026-09-15-overseer-first-ruling/pinned-config.json`;
  context audit "Tools"]. The real boundary stays server-side: dfmcp enforces each
  role's allowlist from the bearer token [V, CLAUDE.md "Per-role allowlists enforced
  server-side"].
- Token exposure does not change: today one secrets env file carrying every role's
  token goes to every run container (`CONDUCTOR_SECRETS_ENV_FILE`, one path for all
  roles) [V, `infra/conductor.example.env`, `runner.py` `build_command`]. What
  changes is that the holder is alive around the clock instead of for one run.
- The default run lane is process-wide with concurrency `min(16, max(8, CPUs))`, so
  five sessions can run at once if `parallel.proposers` is ever turned on; each
  session key has its own serialising lane [S, `docs/concepts/queue.md`].
- openclaw's own docs say operator scopes "are a control-plane guardrail inside one
  trusted Gateway operator domain, not hostile multi-tenant isolation. For strong
  separation ... run separate Gateways" [S, `docs/gateway/operator-scopes.md`]. Our
  roles are one trust domain (same owner, same secrets file), so one Gateway is
  enough; per-role Gateways are the alternative if a role ever needs real isolation
  (open decision U1).

### 3.2 Its own state directory

- A Gateway takes an exclusive ownership lock keyed by its state directory; `agent
  --local` and `agent exec --state-dir` refuse to start while a Gateway owns that
  directory [S, `docs/gateway/gateway-lock.md`, `docs/cli/agent.md`]. The one-shot
  runs mount the shared `openclaw_state_dir` read-write at `/home/node/.openclaw`
  [V, `runner.py` `build_command`]. So the Gateway must never be given that
  directory, or the fallback path breaks exactly when it is needed.
- Lock liveness is judged from the recorded PID and process start identity [S, same
  doc]. Across containers each process sees its own PID namespace, so a second
  container could judge a live owner dead and reclaim the lock [I]. Never share a
  state dir across containers; do not test whether the lock holds.
- Contents: the DeepSeek provider plugin (`npm/`, copied once at install, as the
  multiturn test had to [V]), the merged config mounted read-only over
  `openclaw.json`, the five workspaces, and the per-agent session SQLite. The
  DeepSeek key comes from the environment through the config
  (`models.providers.deepseek.apiKey = {source: env, provider: default, id:
  DEEPSEEK_API_KEY}`, the form the multiturn test used [V]), so no plaintext key is
  written into the Gateway's auth store (red team M5).
- The one-shot fallback should run with an isolated `--state-dir`
  (`CONDUCTOR_THINKING_STATE_DIR` set), which also captures its transcript; whether
  VM 106 sets it today is not recorded here [gap; `Working.md` notes
  `parallel.proposers` needs it].

### 3.3 Charter and prompt (red team B1, still a blocker)

- `agent` (Gateway or local) uses each agent's configured workspace and seeds
  openclaw's bootstrap templates unless `skipBootstrap` is set; `agent exec` forces
  workspace to its cwd and skips bootstrap [S, red team B1 citing
  `agent-exec-input.ts`, `prepare.ts`; `docs/cli/agent.md` exec section confirms
  "workspace bootstrap files are skipped"].
- So the merged config sets `agents.defaults.skipBootstrap: true` and
  `agents.defaults.contextInjection: "always"` (the documented default, set
  explicitly: `continuation-skip` would drop the charter from later turns and change
  the prompt mid-session) [S, `docs/gateway/config-agents/workspace-and-bootstrap.md`].
  Never `"never"`, which drops `SOUL.md` (context audit).
- Each workspace holds only `SOUL.md`. The charter stays in place between wakes
  (unlike today's write-then-delete); at each wake open the conductor checks the
  workspace `SOUL.md` hash against `agents/<role>/role.md` and rewrites it if they
  differ. A role whose charter cannot be confirmed does not open a session (today's
  refusal rule, `runner.py` `charter_missing`, carried over) [V for the rule].
- Whether the Gateway re-reads `SOUL.md` per turn or caches it is [gap]; S0 changes
  it between two turns and reads the next request. If cached, a charter deploy
  restarts the Gateway (section 7).
- The fallback path keeps today's `/app/SOUL.md` mount from the same workspace file,
  so both routes read one charter source [V, `runner.py` `CHARTER_MOUNT`].
- The two routes' system prompts will differ slightly (workspace line, exec's
  overlay) [S, B1]. Consequences: switching a role between routes costs one cold
  prefix, and session-route metrics need a short re-baseline rather than a direct
  comparison with pre-session one-shot runs.

### 3.4 Gateway config (merged, committed as a template)

Today's pinned configs live only on VM 106 (`/opt/openclaw/conductor/pinned-configs/`)
[V, context audit; `conductor/config.py`]. v1 brings the Gateway config under the
repo as a template with `${ENV}` placeholders only (no address, no token, no
hostname), rendered by the deploy. Keys that matter, all [S] unless marked:

```json5
{
  gateway: {
    mode: "local",                       // startup refuses without it
    bind: "loopback", port: 18789,       // port from conductor.env in practice
    auth: { mode: "token" },             // token from OPENCLAW_GATEWAY_TOKEN env
    reload: { mode: "off" },             // config changes only at an explicit restart
    controlUi: { enabled: false },
  },
  terminal: { enabled: false },          // default true: an admin-scoped host PTY
  cron: { enabled: false },              // no automations, so no scheduled heartbeats
  session: { reset: { mode: "none" } },  // the default, set explicitly
  agents: {
    defaults: {
      skipBootstrap: true, contextInjection: "always",
      compaction: { enabled: false },
      heartbeat: { every: "0m" },
      // model default as today; per-run --model still passed
    },
    entries: { /* five roles: workspace, tools.allow, skills: [] */ },
  },
  mcp: { servers: { /* five, url and token by ${ENV} */ } },
  models: { providers: { deepseek: { apiKey: { source: "env", provider: "default", id: "DEEPSEEK_API_KEY" } } } },
}
```

`${ENV}` interpolation in MCP headers is used today [V, pinned config example]; in the
MCP `url` field it is [I], checked when the template is first rendered.

## 4. How the conductor talks to the Gateway

### 4.1 One turn

Per item, a client container on the host network with its own empty state dir and a
tiny client config (`gateway.mode: local`, the port), the token in its env file:

```
docker run --rm --network host --entrypoint node --env-file <secrets> \
  -v <client-state>:/home/node/.openclaw -v <client-config>:/home/node/.openclaw/openclaw.json:ro \
  -v <msg dir>:/msg:ro <image@digest> openclaw.mjs agent \
  --session-key agent:<role>:w<wake_id> --model <model> --json \
  --timeout <remaining s> --message-file /msg/<item>.txt
```

- Proven live on 2026-10-07 with `--auth none`: client container on the host
  network, its own empty state dir, about 2 s overhead per message [V, multiturn
  README]. Token auth through the client is [gap], S0.
- `--model` makes the CLI request admin scope; a local (not remote-mode) CLI asks for
  admin anyway [S, `agent-via-gateway.ts` lines 1070 to 1086]. Shared-token auth is
  "trusted operator access" [S, operator-scopes "Shared-secret auth"], so admin is
  expected to be granted [I, S0]. Passing `--model` per turn keeps
  `CONDUCTOR_MODEL_<ROLE>` working without a Gateway restart.
- `--timeout` is sent as the run's own deadline (`timeout` in the `agent` RPC) and
  also bounds the client wait [S, lines 1099 to 1120]. The conductor's outer kill
  stays at `timeout + 60 s` (`OUTER_KILL_GRACE_SECONDS`) [V].
- The CLI picks a random idempotency key per invocation and has no flag to set it
  (`opts.runId` is not a registered option) [S, `register.agent-turn.ts`,
  `agent-via-gateway.ts` line 1070]. So a conductor retry is never deduplicated by
  openclaw; exactly-once rests on the queue (4.4).
- Exit status: 0 for a completed turn, 1 for error, timeout or cancel; an unknown
  status string fails closed [S, `markAgentRunExitCode`].
- `--message-file` avoids argv limits (4 MiB cap) [S, docs].

### 4.2 Envelope mapping (red team B2, still a blocker)

- Gateway `--json` prints the raw Gateway response `{runId, status, summary,
  result}`, adding `deliveryStatus` only when delivering [S,
  `buildGatewayJsonResponse`, line 930]. The run stats live on `result.meta.agentMeta`
  and the tool summary on `result.meta.toolSummary` [S, `docs/cli/agent.md`: "The
  agent run-stat fields appear on `meta.agentMeta` in the `openclaw agent --json`
  response; the outer tool summary remains at `meta.toolSummary`"].
- One pure function maps it onto today's `RunResult` (status, ok, cost, usage,
  assistant turns, tool summary, final text), so `cycle.py`, the archive and
  `_overseer_called_escalate` see the same shape as from exec [V for those readers].
  Its unit tests use real envelopes captured at S0 [gap until then]: a plain reply,
  an MCP tool call, an inner timeout, a provider error, an abort, and `in_flight`.
- Escalation is checked after every Overseer turn, not at wake close: a turn whose
  tool summary contains `queue.escalate` pauses the fort at once and ends the wake.

### 4.3 Transcript

- Read once per wake at close through `openclaw.mjs gateway call chat.history
  --params '{"sessionKey": ...}' --json` (method registered, `operator.read`) [S,
  `src/gateway/methods/core-descriptors.ts` line 355]. Its reply shape against our
  `build_transcript` is [gap]; S0 captures it and an adapter is written if needed.
- Not read from the Gateway's SQLite on the host: that file is owned by the
  container's user and in WAL mode while the Gateway writes it, the trap the
  publisher hit (`Working.md`, 2026-10-02) [V for the trap].
- If the history read fails, each item's runs row still has its envelope (cost,
  usage, tools, final text); only the per-round transcript is lost. Cut per item at
  each user message, as the design proposed (design section 7).

### 4.4 Exactly-once

Unchanged from the design and the red team, and now load-bearing: the queue refuses
a repeated final ruling, a second answer to an ask, and a repeated typed step [V,
design 4.3, `dfqueue/store.py`, `dfmcp/queue_tools.py` `_append_locked`]. Before any
resend the conductor reads the goal state; after transport loss it never resends
the same item in the same wake, because the Gateway may still finish the turn [S,
`docs/cli/agent.md`: "Transport loss is ambiguous"].

## 5. One session per role, items one at a time

### 5.1 Items, derived (decision 8)

| Role | Items, in order | Source, all existing [V] |
|---|---|---|
| Consultant | one per open ask addressed to it | `queue.overview` asks |
| Planner | one item: the plan wake (red team M7: its wakes end in one plan write) | plan watch, triage |
| Architect, Quartermaster | one per lane key naming a distinct thing (alert, ore site, unsupplied building, noble room, answer to its ask, ruling on its proposal), then ONE review item merging every keyless reason (`routine_review`, `stuck_job`, vitals, unused space line) | `LaneState.pending`, triage reasons |
| Overseer `all` | one item: today's ruling briefing | `build_ruling_briefing` |
| Overseer `single` | a docket header (one line per pending proposal: id, role, type, urgency, flags), then one proposal per item, then accepted-not-carried-out items | `queue.pending_brief`, `to_carry_out` |

- Order within a role: owed replies first (asks, answers, rulings on own filings),
  then lane work, then the review item; deterministic, ticks not wall times, so the
  rendered text is replay-stable.
- `max_items_per_wake` 8; the rest are carried (stay pending, no penalty).
- Done means: a server-visible goal state where one exists (a ruling naming the
  proposal, an answer to the ask, a plan record) [V, design 4.3]; otherwise the turn
  ended ok. Red team M3: a turn that wrote any record in its window counts as
  progress, never as a failure, even if it then timed out.
- A failed or timed-out item: its lane key stays pending and its backoff record
  (`conductor/backoff.py`) counts one more wake; a key that keeps failing stalls and
  alerts through the mechanism that exists [V, `backoff.py` docstring].
- Outcome per item recorded as runs-row columns (section 8), nothing else.
- Superseded mid-wake (the goal state appears before the item is sent, for example
  an ask answered elsewhere): skipped and named in the next message.

### 5.2 The message stream

- First message: the wake briefing (today's builders, unchanged content: FORT line,
  vitals, alerts, roadmap, DECIDED block) plus the docket line ("N items this wake,
  one at a time; finish each, then stop") plus item 1. One turn, no "ready" turn.
- Each later message: any control lines since the last turn, then `ITEM k of N`, the
  item text and its ask.
- Control lines: a pause-state change since the last turn ("FORT CHANGED at tick T:
  running to paused, tripwire thirst_critical"), filtered of the conductor's own
  actions or attributed to them (red team m8); an item stopped by the budget ("item
  k was stopped at the time limit and returns next wake; do not continue it",
  because a timed-out prompt stays in history [V, multiturn]).
- Mid-turn, the pause stamp on every tool reply already tells the model the fort is
  paused [V, `dfmcp/pause_stamp.py`, decision 10]; the control line covers the
  turn boundary and the reason, which the stamp keeps short.

### 5.3 Reset, compaction, ceiling

- **Between wakes: a fresh session key** (`agent:<role>:w<wake_id>`). A new key
  starts at the system prompt; proven live as "the safest local-route reset" and the
  cross-run cache hit on first calls of fresh keys [V, multiturn Addition A]. Only one
  session per role is live at a time, which is the user's "one session per role".
- Alternative (open decision U2): a fixed key `agent:<role>:main` with `/new` sent at
  wake open. Proven live on the Gateway [V], but the envelope keeps the old session id
  so the reset is detected only by the reply text "New session started." [V], it
  needs admin scope [S, line 1073], and old windows accumulate under one key.
- **Compaction: never in v1.** `agents.defaults.compaction.enabled: false` stops
  proactive compaction; overflow recovery remains but cannot trigger below about
  980k on a 1M window [S, source report section 6]. Pruning stays off (it rewrites old
  messages and breaks the prefix cache) [S].
- **Ceiling:** when a turn's prompt (input plus cache read) passes 250k tokens, no
  further item is sent; the rest are carried to the next wake, which opens a fresh
  key. No rotation inside a wake (red team m5). For scale, a whole one-shot Overseer
  run reached 108.7k [V, persistent-sessions 3.1].
- No idle or daily reset: an idle reset fired mid-wake in the live test and broke
  recall [V, multiturn Addition B].
- **Session store hygiene:** the store is disposable by design (the queue and the
  runs DB are the record). It is wiped at every Gateway start (section 7.2); between
  restarts, built-in maintenance prunes after 30 days or 5000 rows [S, source report
  section 8].

### 5.4 Run limits (decision 9)

- Budget per role per wake = `role_timeout_seconds` (600 s, Overseer 1200 s), the
  same numbers as today [V, `policy.yaml`, `cycle.py` `_timeout_for`].
- Each turn's `--timeout` = floor of what is left; outer kill at that plus 60 s.
- Fewer than 60 s left: stop, carry the rest. (A practical floor, not a per-item
  cap: a turn cannot do anything useful in less.)
- Budget hit mid-turn: SIGTERM the client, which sends `chat.abort` for an accepted
  run [S, `docs/cli/agent.md`]; then `gateway call sessions.abort` for the key as a
  belt [S, method registered `operator.write`]; the wake ends. The session is never
  reused (next wake has a new key), so the half-finished turn in its history does not
  matter.

### 5.5 Overseer specifics

- `all` first: the session route with today's single ruling turn. Behaviour equals
  one-shot apart from transport and the B1 prompt differences, so it is the safe
  first setting.
- `single` next, per the 2026-10-08 row: one proposal per turn with the docket header
  as the overview of the rest. Judged on live wakes by cost per docket, defer rate,
  consistency errors (accepting both of an `overlaps` or `duplicate_of` pair) and
  prediction grading; no blind grader for now (decision 11).
- Game actions: the Overseer's direct write tools record ready-ruled one-step
  actions and the conductor executes them after the Overseer's run [V, register
  2026-10-09]. In v1 "after the run" means after the Overseer's wake closes.
  Executing per item (the pipelining the 2026-10-08 row wants) is a later stage.

## 6. Concurrency

v1 is serial, in today's order (Planner, advisors, Consultant, Overseer, execute).
`parallel.proposers` already exists and is built [V, `policy.yaml` `parallel`,
`cycle.py` lines 970 to 1110]; with sessions, parallel roles are concurrent sessions
in one Gateway, so the per-run isolated state dir it needs for exec is not needed on
the session route. Turning it on stays a separate, later switch (the DFHack pool of
four and the 60 s filing read bound are the risks, red team M4).

## 7. Supervision

### 7.1 The unit (`infra/units/openclaw/openclaw-gateway.service`, new)

- `User=df`, `SupplementaryGroups=docker`, the same hardening block as
  `conductor.service` [V, `infra/units/openclaw/conductor.service`].
- `ExecStartPre=-/usr/bin/docker rm -f openclaw-gateway` (a leftover container from a
  crash).
- `ExecStartPre=` the session wipe (7.2).
- `ExecStart=/usr/bin/docker run --rm --name openclaw-gateway --network host
  --entrypoint node --env-file <secrets> -v <gw state>:/home/node/.openclaw -v
  <gateway config>:/home/node/.openclaw/openclaw.json:ro -v <workspaces...>
  <image@digest> openclaw.mjs gateway run --bind loopback --port <p> --auth token`.
- `ExecStop=/usr/bin/docker stop -t 300 openclaw-gateway`, `TimeoutStopSec=330`: a
  requested stop drains active turns for up to 5 minutes by default [S,
  `docs/gateway/restart-recovery.md`]; killing only the `docker run` client would
  leave the container running, the same trap the runner documents [V, `runner.py`
  timeout path].
- `Restart=on-failure`, `RestartSec=10`, `RestartPreventExitStatus=78`: a Gateway that
  finds another healthy owner exits 78 so a supervisor does not loop [S,
  `docs/gateway/gateway-lock.md`].
- Not `OPENCLAW_SUPERVISOR_MODE=external`: that mode is for supervisors that consume
  openclaw's restart handoffs [S, `restart-and-supervision.md`]; systemd plus docker
  restarting a fresh process is simpler and the handoff is not needed.

### 7.2 Restart is a clean slate

- Restart recovery is "always on": a turn interrupted by a crash or forced stop is
  re-dispatched a few seconds after startup with a synthetic "your previous turn was
  interrupted" message, up to three charged attempts, if the interruption is under
  2 hours old [S, `restart-recovery.md` "Automatic resume"]. No config switch to turn
  it off was found [S, searched that doc; not exhaustive in source].
- A recovered turn would run with no conductor watching: it could file queue records
  and, for the Overseer, record ready-ruled actions.
- Containment: `ExecStartPre` deletes the per-agent session databases
  (`agents/*/agent/openclaw-agent.sqlite*`) in the Gateway's state dir before start,
  so recovery has nothing to resume. Whether startup is clean on a state dir with
  those files absent (it should be: a fresh install has none) is [I], S0 checks it
  and that no recovery dispatch appears in the log. The files are owned by the
  container's user, so the wipe runs as a short container with the same user [I].
- Whether recovery even applies to `agent` RPC turns on explicit keys (the docs say
  "main-session" turns) is not settled [gap]; the wipe makes the answer irrelevant.

### 7.3 Health check and what the conductor does

- At each wake open: `GET http://127.0.0.1:<port>/startupz` with a 2 s timeout, from
  Python directly (no container). `200` with `status: "started"` means usable;
  anything else means down [S, `docs/gateway/health.md`: unauthenticated probes;
  `/startupz` "for traffic admission", `/healthz` liveness only].
- Down: that role runs today's one-shot `agent exec` this wake, with its items
  rendered into one briefing as today; a site alert "Gateway down, roles on one-shot"
  once per outage, renotified by the backoff rule. No retry loop.
- Lost mid-wake (client exits with a transport error, or the probe now fails): the
  in-flight item's goal state is read; the remaining items of that role are carried
  (not handed to a fallback run in the same wake, since the Gateway may still finish
  the in-flight turn). Next wake probes again.
- `scripts/drift_check.py` adds `openclaw-gateway.service` to its services section
  (active, enabled once the user says so).
- The conductor never starts, stops or restarts the unit. Restarts are deploy steps
  (7.4) or systemd's own on crash.

### 7.4 Deploys that must restart the Gateway

- **Every vm103-dfmcp deploy.** A Gateway keeps unchanged MCP servers' connections
  "and cached tools, including for runs already in progress" [S, `docs/tools/mcp.md`];
  with reload off, a dfmcp change to tools or their descriptions would not reach the
  roles until the Gateway restarts. Whether a dfmcp restart forces a reconnect and a
  fresh tool list is [gap], S0. Until shown, the deploy manifest restarts the Gateway
  after vm103-dfmcp.
- Every Gateway config, image or charter change (charter only if S0 shows caching).
- Only while the conductor is idle: the conductor takes an exclusive lock on its
  state dir for each cycle (red team M6, owed anyway), and the deploy step waits for
  it (`flock`) before restarting. A restart under a live wake is what the drain and
  the wipe exist for, but avoiding it is cheaper.
- Every such restart costs one cold prefix per role on its next wake (already true of
  any tool-list change, `Working.md` lesson 2026-10-08).

## 8. Runs rows, metrics, Board

As the design (section 7) with the red team's amendments: one runs row per item turn
with additive columns `wake_id`, `item_seq`, `item_kind`, `item_ref`, `outcome`,
`transport` (`gateway` or `oneshot`), `cycle_id`; per-wake figures defined per wake,
not summed where a sum means nothing (red team m2); one public summary per wake from a
`wake_close` report, item replies kept in the transcript tab (m3); the awake strip
keyed on `wake_open` and `wake_close`. A one-shot run is a wake of one item, so old
and new rows read the same way.

## 9. Self red team: what the Gateway costs, and how each cost is contained

The red team preferred the local route because the Gateway's measurable gain is
small: live wakes carry 1 to 3 items, so the 5 to 7 s saved per message is 10 to 20 s
per role wake, under 5 percent of a run [V, red team M1]. That is still true. The
user chose the Gateway anyway, for the structure (a live session per role that items
are pushed into, later pipelining for the Overseer). Here is the price, plainly.

### 9.1 An always-on process that starts agent turns by itself (severity: high)

By default a Gateway runs heartbeat turns every 30 minutes in each agent's main
session [S, `docs/gateway/heartbeat.md` "Defaults"], serves a Control UI with chat,
offers an admin-scoped operator terminal that "starts a host PTY in the selected
agent workspace" (default on) [S, `config-gateway.md`], resumes interrupted turns
after a restart (9.3), and applies config edits live. Any of these would be an agent
acting on the fort, or spending, outside the conductor.

- What already limits it: with no channel configured, an ambient heartbeat poll has
  no route and is skipped before the model is called ("Routeless ambient polls are
  pure model burn, but only they may skip") [S, `src/infra/heartbeat-runner-execution.ts`
  lines 356 to 367]. Triggered wakes (hook, cron, exec completion) are not skipped.
- Containment: `heartbeat.every: "0m"`, `cron.enabled: false`, `controlUi.enabled:
  false`, `terminal.enabled: false`, `reload.mode: "off"`, no channels, no hooks,
  loopback bind with token auth, config mounted read-only.
- Proof, not trust: a 24 hour idle canary at S0 with zero model calls (no new
  transcript rows, no DeepSeek usage in the Gateway's logs) and zero dfmcp tool calls
  attributed to role tokens in the dfmcp journal outside conductor-opened wakes.
  The same dfmcp-journal check runs as a standing drift check afterwards.

### 9.2 Every role's credentials live in one long-running process (medium)

Same tokens as today's run containers, but resident around the clock; anyone who can
reach the loopback port with the Gateway token can drive any role.

- Containment: loopback only (host network, `--bind loopback`); token in the secrets
  env file only, never argv (the docs warn inline secrets show in process listings)
  [S]; a new row in the gitignored secrets-rotation list for the Gateway token; the
  dfmcp side still enforces each role's allowlist by token, and game writes are the
  conductor's alone (9.3).

### 9.3 Work the conductor did not open (high, contained by the single-writer rule)

Restart recovery, a mis-set feature, or a stray client could run a role turn the
conductor never opened.

- First containment: the session wipe at start (7.2).
- Second, and the one that matters: since 2026-10-09 no role writes to the game; the
  Overseer's write tools record ready-ruled actions that the conductor's execute
  phase runs [V, register]. v1 adds one rule to `conductor/execute.py`: execute only
  actions recorded inside the time window of an Overseer wake the conductor opened
  (`runs.records_in_window` already finds records by role and window [V, red team
  M3]); anything else is held and raised as an alert, never executed. So the worst a
  stray turn can do is file queue records, which the server validates, deduplicates
  and the Overseer rules on.

### 9.4 A second execution path to keep working (medium)

Two envelope shapes, two charter delivery routes, two prompt variants, and a
fallback that only runs when something is already wrong.

- Containment: one mapping function to `RunResult` with contract tests on captured
  envelopes from both routes; the charter hash check on both; a forced-down test at
  every rollout stage (stop the Gateway, run one `--once` cycle, see the role run
  one-shot and the alert fire); the per-role flag means a misbehaving role goes back
  to one-shot with one line.

### 9.5 Drift between the Gateway and everything around it (medium)

Cached MCP tool catalogs (7.4), a config that changes only at restart, an image tag
that moves (`runner.py` `DEFAULT_IMAGE` is `:latest` today [V]), and a pinned config
that today lives only on the VM.

- Containment: image pinned by digest for the Gateway, the client and the fallback,
  recorded on every runs row (red team m10, do it now regardless); Gateway config
  committed as a template and deployed (3.4); dfmcp deploys restart the Gateway
  (7.4); `drift_check.py` compares the rendered config's hash with the deployed one.

### 9.6 Ambiguity after a lost connection (low)

A turn can finish after its client died [S]; there is no conductor-chosen
idempotency key [S, 4.1].

- Containment: never resend in the same wake; read the goal state; the queue's
  refusals make a later repeat harmless for rulings, answers and typed steps [V].
  Untyped near-duplicates are only flagged, not refused [V, red team M3]; the Overseer
  sees the `duplicate_of` flag in its briefing.

### 9.7 Resources and new unknowns (low to medium)

- Memory and CPU of a resident Node process on VM 106: unmeasured [gap]; S0 records
  RSS after a day.
- A Gateway-side watchdog can abort sessions "stalled" past a built-in threshold [S,
  `docs/concepts/queue.md` troubleshooting]. DeepSeek reasoning streams tokens, so a
  long think should read as progress [I]; S0 watches for `session.stalled` in logs.
- Startup migrations write the config when legacy keys need migrating [S,
  `cli/gateway/running.md`]; with a read-only mount that write fails, so a template
  that needs migrating fails loudly at start rather than silently changing [I].
- Gateway token auth, the client over the host network with a token, MCP tools inside
  a Gateway turn, `chat.history`'s shape, and abort behaviour: all [gap], S0.

### 9.8 Things this plan deliberately does not use

`steer`, `followup` or `collect` queue modes (the conductor sends one item at a time
and waits, so no turn is ever queued behind another); `sessions.send`; the private
SDK; Tool Search; openclaw memory and skills; `contextInjection: "never"`. Each was
either unverified, unnecessary for one-at-a-time delivery, or rejected by the context
audit.

## 10. Token and cache effect

Rates, official DeepSeek off-peak per million tokens [V, `research/2026-10-08-thinking-budget.md`]:
Flash cache hit $0.003, miss $0.15, output $0.60; Pro hit $0.022, miss $0.66, output
$1.98. All roles are on Flash for now (register 2026-10-09). The real bill has run 3
to 5 times the logged cost (same register row), so treat these as ratios.

| Case | Prompt | Cached | Measured where |
|---|---|---|---|
| Today, cold first call of a wake (Architect) | 20,237 | 384 | context audit [V] |
| Today, cold first call (Overseer run-0023) | 29,860 | 0 | persistent sessions 3.1 [V] |
| Today, rounds 2+ within a run | grows to 62k to 109k | 96 to 99 percent | same [V] |
| Session, pushed turn in a warm session (throwaway) | about 31k | 30,208 to 31,232 | multiturn [V] |
| Session, first turn after a reset or in a new process (same day) | about 30.5k | 30,208 to 30,720 | multiturn [V] |

What follows, per wake:

- **The cold prefix is the same on both routes.** The provider caches by prefix, not
  by process, and the Gateway does not keep the provider's cache warm between wakes.
  A wake that starts cold pays it either way: about 30k x $0.15/M = $0.0045 on Flash
  ($0.020 on Pro) for the Overseer's first call. Wakes are hours apart and DeepSeek's
  retention is unstated, hits proven up to 215 minutes [V, cross-run cache research].
- **A pushed item is nearly free on input.** At 100k carried context, 100k x $0.003/M
  plus about 800 new tokens x $0.15/M is about $0.0004 per item on Flash. One-shot
  pays the same for its later rounds; splitting into items adds one extra first
  request per item, not a new prefix.
- **Output decides.** Output is about two thirds of cost (reasoning) [V, register
  2026-10-09 Flash row]. Whether one item per turn makes the model re-orient per item
  (more reasoning) or think less per item (narrower task) is unknown; the red team's
  guess was 0 to 15 percent above today [I]. The runs columns (section 8) measure it per
  role at each stage.
- **Avoidable cold prefixes:** each switch between routes for a role (3.3), each
  Gateway restart after a dfmcp or charter deploy (7.4), and the date line at UTC
  midnight [S]. Batch deploys.
- **Idle cost: zero tokens**, once 9.1 is proven by the canary.

## 11. Failure modes and tests

| Failure | Detection | Response | Test |
|---|---|---|---|
| Gateway down at wake open | `/startupz` not 200 started | role runs one-shot; one alert per outage | unit: fake probe down, assert one-shot path and alert; live: stop unit, run `--once` |
| Gateway dies mid-wake | client transport error, probe fails | read goal state of in-flight item; carry the rest; no fallback in the same wake | unit: fake transport raises after accept; assert no resend |
| Turn hits its `--timeout` | envelope status timeout or `incomplete_turn` | item carried, backoff advanced unless it wrote a record; wake ends if budget gone | unit: fake timeout envelope; live S2: tiny budget on one item |
| Outer kill needed | conductor wait expires | SIGTERM client (sends `chat.abort`), `gateway call sessions.abort`, end wake | unit; live S0 (abort mid MCP call, then check no further dfmcp calls from that session in the dfmcp journal) |
| Overseer escalates in item k | `queue.escalate` in `meta.toolSummary` | pause at once, end the wake, skip execute | unit: fake turn with the tool, assert pause called before item k+1 |
| Tripwire latches mid-wake | pause poller | start no new items in any session, kill in-flight non-owner turns, skip execute, end cycle; next cycle takes the tripwire branch (red team M8) | unit |
| Stray turn records an Overseer action | record outside an opened wake window | not executed; alert | unit in `execute.py` tests |
| Restart recovery resumes a turn | dfmcp journal shows role calls with no open wake | wipe at start prevents; alert if seen | live S0: kill the container mid-turn, restart unit, watch for 10 minutes |
| Idle Gateway runs a turn | canary: transcript rows, provider usage, dfmcp calls | config fix; Gateway off until fixed | live S0, 24 h |
| Tool list stale after dfmcp deploy | first turn's tool summary names a removed tool, or drift check | restart Gateway (deploy step) | live S0: deploy-equivalent dfmcp restart, compare tool list before and after |
| Charter missing or stale | hash check at wake open | refuse to open the session; one-shot also refuses | unit; live S0 capture shows `SOUL.md` text, no `AGENTS.md`/`BOOTSTRAP.md`/`IDENTITY.md`/`USER.md` template text |
| Envelope shape changes (image moved) | mapping returns unknown status | fail closed as an error item | contract tests on captured fixtures; digest pin |
| Session grows past ceiling | turn usage | stop sending, carry | unit |
| Lost connection, turn finishes anyway | goal state appears later | counted next cycle by goal state; no resend | unit |
| Two conductors at once | instance lock | second exits | unit on the lock |
| State dir shared by mistake | exec refuses to start ("Gateway owns it") | config error at deploy | deploy check: Gateway state path differs from `CONDUCTOR_OPENCLAW_STATE_DIR` |

Offline tests use a `FakeSessionTransport` in the style of `FakeRoleRunner` [V,
`runner.py`]; no test runs docker. Live checks run with the fort paused under the
operator hold unless stated.

## 12. Staged rollout

| Stage | What | Gate to pass |
|---|---|---|
| S0 | Install `openclaw-gateway.service` with the template config; checks: token auth through the client on the host network; request capture for the Consultant on both routes (system prompt and tool list hashes; charter present; no template files); `chat.history` shape; MCP tool call inside a Gateway turn; abort mid MCP call; kill mid-turn plus restart with the wipe; dfmcp restart and the tool list; charter change between turns; envelope fixtures; RSS after a day; 24 h idle canary | `evals/live/<date>-gateway-s0/README.md` answering each; canary clean. Nothing below starts before the canary passes |
| S1 | Conductor code merged with every role on `oneshot`; runs columns; instance lock; execute-window rule; image digest pin | ordinary `--once` cycles unchanged; columns filled with `transport: oneshot` |
| S2 | Consultant on `session` | a cycle with two staged asks: both answered once, two item rows under one `wake_id`, transcript per item on the Board; hold flipped during the wake shows the control line in the next message; forced-down test runs it one-shot |
| S3 | Planner on `session` (single item) | several routine cycles: plan writes as before, cost and wall per wake recorded |
| S4 | Quartermaster, then Architect | a wake with at least two items each; lane keys cleared per key; a forced timeout carries an item without losing a record it wrote |
| S5 | Overseer on `session`, mode `all` | rules a live docket with the same records a one-shot run would; escalation test pauses the fort |
| S6 | Overseer mode `single` | a run of live ruling wakes; cost per docket, defer rate and consistency errors compared with S5; register row with the numbers |
| Later | per-item execute for the Overseer (pipelining); `parallel.proposers` on sessions; true mid-turn steering only if ever needed | each its own decision |

Arming `conductor.service` stays on its own track; every stage above runs under
hand-run `--once` cycles. Policy is loaded once at service start [V, `service.py`
`build_deps`], so under the service a flag change needs a restart; under `--once` it
does not.

Policy block (`conductor/policy.yaml`):

```yaml
sessions:
  transport: gateway          # gateway | oneshot: global kill switch
  roles:                      # per role, oneshot is the default and the rollback
    consultant: oneshot
    planner: oneshot
    quartermaster: oneshot
    architect: oneshot
    overseer: oneshot
  overseer_ruling_mode: all   # all | single
  max_items_per_wake: 8
  min_turn_seconds: 60
  max_session_prompt_tokens: 250000
  probe_timeout_seconds: 2
```

## 13. Discrepancies found

- `Working.md` "User decisions open (older list)" still recommends the local route
  first for sessions; decision 7 overrides it. Worth a memory audit pass.
- `conductor/service.py`'s docstring says charters are read fresh every cycle; the code
  loads them once at start (already flagged by the 2026-10-08 design, still open).
- `research/2026-10-07-persistent-sessions.md` says the Gateway was never run in this
  project; the 2026-10-07 multiturn test ran a throwaway one. The research predates it.
- openclaw docs against code: none found on the points used here. The docs'
  `chat.history` and `sessions.abort` scopes match the method registry [S].

## 14. Not verified

Everything marked [gap] above, collected: token auth through the CLI client; admin
scope granted to a shared-token client for `--model`; MCP tools inside a Gateway turn;
the emitted Gateway envelope (fixture); `chat.history`'s reply shape; abort behaviour
in practice; whether restart recovery applies to explicit-key `agent` turns and
whether the start-time wipe is clean; whether `SOUL.md` is cached; whether a dfmcp
restart refreshes the Gateway's tool list; `${ENV}` in an MCP `url`; resident memory;
whether VM 106 sets `CONDUCTOR_THINKING_STATE_DIR`; the session-stall watchdog
against long reasoning; output-token change from one item per turn. The source read
was at tag `v2026.9.4`; the installed image is recorded as that commit by the context
audit, not re-inspected here.

## 15. v1.1: sessions per relevant open proposal (2026-10-09)

Input: register row 2026-10-09 "Session layout: per relevant open proposal; Overseer
per wake; mid-run news" (user). Its premise, accepted here: sessions do not lower
per-token cost (section 10 showed DeepSeek already caches prefixes); their value is
fewer re-orientation turns, quick back-and-forth on one piece of work, and news
arriving mid-run. Same confidence key as above.

Defaults carried over unchanged: U1 one Gateway; U4 started by hand until the 24 h
canary passes; U8 a dfmcp deploy restarts the Gateway; the whole of sections 3.2 to
3.4, 4, 7, 9 and the S0 list. Changed by the new layout: U2 (key per wake) is
replaced by keys per (role, proposal) (15.1); U3 (wipe on restart) stands but now
resets sessions that span many wakes (15.6); U7 (containment) is restated per
activation instead of per wake (15.9).

### 15.1 Session keys

| Session | Key | Opens | Closes |
|---|---|---|---|
| Proposal session | the draft key it was mapped from, or `agent:<role>:p<proposal_id>` on a reopen | the role is relevant to an open proposal and has something to act on (15.3) | proposal closed, size cap, Gateway restart (15.6) |
| Drafting session | `agent:<role>:d<activation_id>` | a lane item for this role that none of its open proposals covers (an alert, an ore site, the review item) | at the end of its activation if nothing was filed; otherwise it becomes the filed proposal's session |
| Overseer session | `agent:overseer:w<wake_id>` | the Overseer wakes | nothing pending and every other session in the cycle idle, or its 20 min activation budget |
| Planner, Consultant | none: one-shot as today | | |

- **Draft to proposal: mapped, not re-keyed.** No session rename was found in
  openclaw's method registry [I]; a new key would be a new, empty session and lose the
  drafting context, which is the point. So the conductor records `proposal_id ->
  session key` when it sees the filing (records carry their author, and the turn
  window identifies the session) [V for the author column, `dfqueue/store.py`]. A
  reopen after a close or a wipe uses the canonical `p<proposal_id>` key with a
  re-brief (15.6).
- **A drafting activation that files two or more proposals**: one session, mapped to
  all of them, closed when the last closes (Q1).
- **Planner and Consultant** run one-shot unless pulled into a proposal (15.3); then
  they get a proposal session like anyone else. The Planner's own `plan_change`
  proposals count as its own (Q2).
- The map and a per-session "news delivered up to" cursor live in one small
  single-writer file beside the cursor store (`sessions_state.json`). It is a key
  map, not an inbox: every item and every piece of news is still derived each cycle
  from the queue and the conductor's existing state (decision 8).

### 15.2 Overseer: one pipelined session per wake

- Opens when triage wakes the Overseer (pending proposals, a verdict item,
  carry-out items). First message: today's ruling briefing header (FORT line, DECIDED
  block) plus a docket overview of everything pending, then the first proposal.
- Pipelined: after every turn of any other session in the cycle, the conductor
  re-reads the pending list (`queue.pending_brief`) and pushes each newly filed
  proposal into the Overseer session as its next item, with a one-line overview of
  the rest (the 2026-10-08 one-at-a-time row) [V for the read]. The Overseer rules each
  as it arrives and no longer waits for the slowest proposer.
- So the Overseer runs at the same time as the advisors' sessions; today's cycle
  order (advisors, then Overseer) gives way to "Overseer session open while proposal
  sessions run". That needs the concurrency of 15.5 from the start.
- Game actions: the conductor executes ready-ruled actions recorded inside the
  Overseer's activation window. At first it executes once, when the session closes
  (as v1). Executing after each ruling turn, the full pipelining, is a later switch
  (Q5). Escalation is still checked after every Overseer turn.

### 15.3 How the conductor decides relevance

A role R is relevant to an open proposal P when any of these holds:

| Rule | Read from |
|---|---|
| R filed P | the record's `role` [V, store] |
| an ask with `proposal_id = P` is addressed to R (R pulled in to answer) | asks carry an optional `proposal_id`, validated to name a real proposal [V, `dfqueue/store.py` near line 579] |
| R filed an ask or a pass with `proposal_id = P` (R asked about it, or advised on it) | same records [V for asks; I for passes] |
| P is the Overseer's to rule | not per proposal: the Overseer sees P through its per-wake session (15.2) |

Anything else does not get a proposal session:
- an ask with no `proposal_id`: the Consultant answers it one-shot, as today;
- a lane fact that none of R's open proposals covers (an alert, an ore site, the
  review item): a drafting session;
- a lane fact that one of R's open proposals does cover (an ore site R already
  proposed mining, an unsupplied building R already filed for): routed to that
  proposal's session as news, not a new draft. "Covers" is matched on the step
  identity the duplicate refusal already uses (`dfqueue/step_identity.yaml`) for typed
  proposals, and not matched otherwise [V for typed identities; I for untyped];
- no session for a proposal R has no part in (the user's rule).

### 15.4 News routing

Sources are only what the conductor already observes [V for each module named]:

| Event | Source | Tied to | Class |
|---|---|---|---|
| step done | `execute.py` (`done`) | project, so proposal | informational; actionable when it is the last step |
| step needs attention (failed, transient, unknown, ore held) | `execute.py` (`attend`) | proposal | actionable |
| stock hold on a step | `stock_hold.py` note | proposal | informational; actionable at the 3a thresholds (survival target, older than one game day, blocking other steps) [V, register 3a] |
| ruling on P (accept, reject, defer, amend) | queue records | P | reject, defer, amend actionable; accept informational |
| answered ask about P | queue records | P, to the asker's session | actionable |
| graded prediction missed | `queue.grade` names the proposer [V, `lanes.py` docstring] | P | actionable |
| stuck job | `job_watch.py` | P only if the job came from one of P's issued steps; otherwise the role's lane | actionable after its threshold |
| dig cancelled into damp or warm stone | the game cancels it [V, register auto mining]; the conductor sees the dig vanish or the step fail | P via the step, if traceable [I] | informational unless the step fails |
| cavern breach | `automine.py` cavern note | fort-wide | actionable, to every affected session and the Overseer |
| tripwire, starvation risk, unexplained pause | `tripwire.py`, vitals alerts, `pause_watch.py` | fort-wide | actionable; a tripwire also stops new turns (red team M8) |
| pause state change | pause poller | fort-wide | control line; mid-turn the stamp already says it |

- "Affected sessions" for a fort-wide alarm: every open session of a role whose lane
  lists that alarm in `lane_triggers` (policy data, no per-role branch), plus the
  Overseer [V for `lane_triggers`].
- **Actionable news triggers an activation** of its session (a turn) in the next
  cycle if the session is idle. **Informational news is batched**: it rides as lines
  at the top of the session's next message, whenever that comes, capped at 8 lines
  with "and k more".
- News is derived each cycle from queue records and execute state since the
  session's delivered cursor, so a conductor restart loses nothing. The cursor
  advances only when a turn carrying the lines completes ok.

### 15.5 Concurrency and run limits

- Parallel sessions of one role on different proposals are allowed: each key has its
  own lane in the Gateway, and the process-wide lane admits at least 8 runs [S,
  `docs/concepts/queue.md`]. Never two activations on the same key.
- Caps (policy data): `max_concurrent_per_role` 2, `max_concurrent_total` 4, set by the
  DFHack pool of four connections and the 60 s filing read bound (red team M4) [V].
  DeepSeek Flash allows 2500 concurrent requests per account [V, thinking-budget
  research]. Anything over the cap waits for the next cycle, oldest actionable first.
- Starts are staggered as `parallel.stagger_seconds` already does (1.5 s) [V], so a
  same-role session started second can read the first's cached system prompt and
  tools.
- **The 10/20 min limit applies per session activation.** An activation is the run of
  turns a session takes from being woken until nothing actionable is left; each
  turn's `--timeout` is what remains of that activation's 600 s (Overseer 1200 s). Two
  sessions of one role each get their own budget.
- Conflicts between two sessions of one role are caught where they are today: the
  duplicate refusal holds one lock over check and write, reservations are checked in
  one game-side call, and the Overseer rules on both [V, register 2026-10-08
  concurrency row].

### 15.6 Close and reset

- **Proposal closed** (final reject, project done or abandoned, superseded,
  withdrawn): every session mapped to it leaves the map and its key is never sent to
  again. Its rows are left to openclaw's pruning and the start-time wipe.
- **Size cap**: when a turn's prompt passes the cap, the session is dropped and the
  next activation opens a fresh `p<proposal_id>` key (with a suffix) with a
  **re-brief built from the queue**: the proposal, its ruling, its steps and their
  state, open asks and answers about it, and the undelivered news. Never a model-made
  summary of the old transcript. Recommended cap for cross-wake sessions: 120k, lower
  than v1's 250k, because a session resumed after the provider cache has expired pays
  its whole history at the miss rate (15.8) (Q4).
- **Gateway restart** (a crash, or every dfmcp deploy under U8): the wipe empties
  every session, and each open proposal reopens with the same re-brief on its next
  activation. Deploys are frequent, so sessions will often restart from a re-brief.
  That is acceptable because the re-brief comes from the record, and it is the price
  of keeping U3 and U8.
- **Staleness**: a proposal session can carry tool results from days ago. Every
  activation's first message opens with a fresh FORT line and vitals and one fixed
  line: "earlier tool results in this session may be out of date; re-read before
  acting". This is the stale-belief risk the persistent-sessions research
  documented, bounded here by the proposal's lifetime and the cap (Q9).
- A drafting session that filed nothing closes at the end of its activation.

### 15.7 News for a session whose role is mid-turn

- Never sent while that session's turn is in flight: a second `agent` call would only
  wait in the session's lane [S], and no verified mid-turn injection exists.
- Held, and delivered as the first lines of the session's next message. If the
  in-flight turn ends with nothing else queued, actionable news starts the next turn
  at once within the same activation, budget permitting; informational news waits.
- A pause or tripwire reaches the model mid-turn through the tool-reply stamp
  (decision 10) [V]; a tripwire also stops new turns.
- Another session of the same role being mid-turn does not hold this session's news:
  news is per session.

### 15.8 Cost of N open sessions on the Gateway

- **Idle: no tokens.** A session that is not activated sends nothing; its transcript is
  rows in the per-agent SQLite [S]. Memory per idle session is probably small [I]; S0
  records RSS with several sessions open.
- **Resume after the provider cache has expired** (hours to days; retention unstated
  [V, cross-run cache research]): the whole carried history is re-read once at the
  miss rate. Flash: 60k carried costs $0.009, 120k $0.018, 250k $0.0375. Pro: $0.040,
  $0.079, $0.165. A one-shot run instead pays its roughly 30k base cold ($0.0045 on
  Flash) plus the rounds spent re-orienting (reasoning output, $0.60/M on Flash).
  Sessions win when the re-orientation they save outweighs the cold history; the cap
  bounds the worst resume (Q4).
- **Resume while warm** (same hour): the carried history at the hit rate, about
  $0.0003 per 100k on Flash.
- **Fan-out**: a fort-wide alarm activates every affected session, so N open sessions
  cost N turns. Only actionable alarms do this; informational news never starts a
  turn.
- **Disk**: rows accumulate per key; the start-time wipe and openclaw's 30 day / 5000
  row pruning bound it [S].

### 15.9 What else changes

- U7 restated: execute only Overseer actions recorded inside an Overseer activation
  the conductor opened.
- Transcript: `chat.history` read at the end of each activation for that key. Runs
  rows per turn gain `session_key`, `proposal_id` and `activation_id` beside v1's
  columns (section 8).
- Items (5.1) are now per session: a proposal session's items are its actionable news
  plus any lane fact routed to it; a drafting session's item is the lane fact that
  opened it.

### 15.10 Rollout, revised

| Stage | What | Gate |
|---|---|---|
| S0 | as section 12, plus several open sessions for RSS, and one session resumed after a cache gap for its cold cost | README; canary clean |
| S1 | code merged, every role one-shot; runs columns; instance lock; execute window rule; digest pin; `sessions_state.json` written but unused | ordinary cycles unchanged |
| S2 | first proposal-session role at `max_concurrent_per_role` 1 (Q6: Quartermaster) | a proposal filed from a drafting session and mapped; a step result and a ruling delivered as news; an answered ask triggers a turn; the size cap and re-brief forced once |
| S3 | Architect, still one session at a time | the same checks; an alert fan-out reaches its sessions |
| S4 | Overseer per-wake session, executing at close | rules proposals pushed during the cycle; escalation pauses at once |
| S5 | concurrency on: 2 per role, 4 in total | busy refusals no higher than today; no duplicate filing lands |
| S6 | Overseer executes after each ruling turn | each ruled action executes within its activation; the hold blocks it |
| Later | Planner and Consultant proposal sessions when pulled in (one-shot until then) | |

### 15.11 Build streams, revised (no file in two streams)

At the time of writing another session had an unfinished merge in the shared
working tree touching `conductor/cycle.py`, `conductor/execute.py`,
`conductor/policy.py` and `conductor/policy.yaml`, and adding `conductor/stock_hold.py`.
Every conductor stream below starts after that lands on main.

1. **Gateway infra and S0** (live, VM 106): `infra/units/openclaw/openclaw-gateway.service`
   (new); a Gateway config template under `infra/openclaw/` (new);
   `infra/deploy-manifest.yaml`; `infra/conductor.example.env`; `scripts/drift_check.py`;
   `evals/live/<date>-gateway-s0/README.md`; a row in the gitignored secrets-rotation file.
2. **Session transport** (offline, fake transport): `conductor/session_runner.py` (new:
   transport protocol, Gateway transport, fake, envelope mapping, `chat.history`
   adapter); `conductor/runner.py` (digest pin, shared `RunResult` mapping);
   `conductor/tests/test_session_runner.py` (new); `conductor/tests/test_runner.py`.
3. **Sessions and news** (offline): `conductor/sessions.py` (new: key map, relevance,
   open and close rules, size cap, re-brief, `sessions_state.json`); `conductor/news.py`
   (new: event-to-session routing, classes, batching); `conductor/cycle.py` (activation
   loop, Overseer pipelining, concurrency caps); `conductor/policy.py` and
   `conductor/policy.yaml` (a `sessions` block: per-role mode, caps, size cap, news
   classes as data); `conductor/config.py`; `conductor/service.py` (instance lock);
   `conductor/briefing.py` (re-brief and the staleness line);
   `conductor/tests/test_sessions.py` and `test_news.py` (new); `conductor/tests/test_cycle.py`.
4. **Execute containment**: `conductor/execute.py` (activation-window rule; execute at
   close now, per ruling later behind a flag); `conductor/tests/test_execute.py`.
5. **Records and metrics** (dfmcp, dfqueue): `dfmcp/conductor_tools.py` (report fields);
   `dfmcp/queue_tools.py` (only if `queue.overview` or `pending_brief` must expose the
   `proposal_id` of asks and passes, or the author per proposal; check what is already
   exposed first); `dfqueue/runs.py`; `dfqueue/wake_metrics.py`; `dfqueue/live.py`;
   their tests.

Order: 1 first (its S0 fixtures feed 2); 2, 4 and 5 can run in parallel offline; 3
after 2's interface is fixed.

### 15.12 Open questions, with recommendations

- **Q1** A drafting activation files two proposals: **one shared session mapped to
  both**, closed when the last closes (splitting would lose the shared context).
- **Q2** The Planner's own `plan_change` proposals count as "its own", giving it a
  proposal session for them: **yes**, consistent with "own proposals".
- **Q3** Concurrency caps: **2 sessions per role, 4 in total** to start; raise only on
  S5 data.
- **Q4** Size cap for cross-wake sessions: **120k prompt tokens**, then a re-brief
  from the queue.
- **Q5** Overseer actions: **execute when its session closes first**, then after each
  ruling turn from S6.
- **Q6** First proposal-session role: **Quartermaster** (smaller proposals; stock-hold
  news exercises the router), then the Architect.
- **Q7** Is an accepted ruling actionable for the proposer? **No, informational**:
  execution does the work. Reject, defer and amend are actionable.
- **Q8** Stuck jobs and dig cancels that cannot be traced to a step: **the role's lane,
  as today** (a drafting session), never guessed onto a proposal.
- **Q9** Staleness guard: **yes**, a fresh FORT and vitals block and the "re-read
  before acting" line at the top of every activation.

### 15.13 Not verified (additions)

That openclaw has no session rename (only the method registry was searched); whether
passes carry `proposal_id` as asks do; whether dig cancels into damp or warm stone are
observable per step today; RSS and disk per open session; the cold cost of a real
resumed session (arithmetic only; S0 measures one); whether `queue.overview` already
exposes the author per proposal on main (a branch built it; not checked here).
