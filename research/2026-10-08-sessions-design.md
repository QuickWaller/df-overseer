# Per-role openclaw sessions: design

Date: 2026-10-08. Design spec, read-only (no VM touched, nothing run). Written for
the user's decision of 2026-10-08 (register row "Build per-role openclaw sessions
(reset between wakes); drop the own-filings block; ..."). A red team is owed
before any build (same register row).

Confidence key: **[V]** verified in this repo's code or in a live run recorded in
`evals/live/`; **[S]** read in openclaw source by `research/2026-10-07-openclaw-source-sessions.md`
(tag `v2026.9.4` and main), not run here; **[I]** inferred, to be checked at the
stage named. Nothing marked [I] should be built on without that stage's check.

Inputs read, not re-derived: `research/2026-10-07-session-inbox-options.md` (the
inbox mechanisms, batching evidence), `research/2026-10-07-openclaw-source-sessions.md`
(transport facts), `research/2026-10-07-persistent-sessions.md` (why always-alive
was rejected), `evals/live/2026-10-07-openclaw-multiturn/README.md` (multi-turn,
`/new`, timeout, cache, live), `evals/live/2026-10-07-cache-miss-cause/README.md`
(prefix stability on the real Overseer config), `research/2026-10-07-wake-audit.md`,
`research/2026-10-07-notebook-design.md` and its red team, the fort dossier red team
(paired same-state design), `conductor/` (runner, cycle, briefing, lanes, execute,
pause_watch, policy.yaml), `dfqueue/runs.py`, `dfqueue/wake_metrics.py`,
`agents/*/role.md`, and register rows 2026-10-05 to 2026-10-08.

## 1. Answer

1. **Transport: an openclaw Gateway per role per wake, driven by the CLI thin
   client, one message per item.** Not always-alive: the gateway container lives
   for one wake and is removed. `agent --local --session-key` stays as the
   fallback transport behind the same interface. Both routes were proven live for
   multi-turn and cache reuse; the gateway costs about 2 s per message against 7 to
   9 s, has an on-demand reset and a documented clean abort. Neither route offers
   a verified mid-turn injection, so pushes land at the next turn boundary (section 6.4).
2. **Reset by a fresh per-wake state directory**, copied from a per-role template
   (auth and plugins, no sessions), rather than literally sending `/new` to a
   long-lived store. It gives the same clean start the user asked for, needs no
   admin scope, cannot inherit a pending restart-recovery turn, and keeps today's
   transcript reader unchanged. This is a user decision (D2): `/new` on a
   persistent per-role store is the literal alternative and also works.
3. **Concurrency: serial first, then Planner, then Architect, Quartermaster and
   Consultant in parallel, then the Overseer.** Parallel needs two fixes first:
   proposal attribution by author instead of by before/after diff, and one state
   directory per role. The expected cycle is about the slowest advisor plus the
   Overseer, roughly 10 to 15 minutes against 17 to 22 today [I].
4. **The inbox is data, persisted by the conductor**: one row per item, built from
   the wake reasons and lane keys the conductor already computes, ordered by
   class then urgency then age, acknowledged by a server-verified goal state where
   one exists (a ruling, an answer) and by turn completion otherwise. A started item
   that times out gets a strike; three strikes dead-letter it with a site alert.
   An item never started is carried with no strike.
5. **Timeouts: one overall budget per role per wake** (today's
   `role_timeout_seconds`: 600 s, Overseer 1200 s) **plus a per-turn wait**, the
   smaller of a per-item cap and what is left of the budget. I did not find the
   user's earlier preference for this in the register (section 5); the brief states
   it and the design follows it.
6. **Cache**: the stable prefix (tool list, system message) is already
   byte-identical across runs on the real Overseer config [V]. Every variable thing
   goes in user messages, appended, never edited. One wake's session grows by its
   items only, with a token ceiling that rotates to a fresh session.
7. **Metrics**: one `runs` row per item, carrying a `wake_id`, so the Board's
   transcript tab and `wake_metrics` keep working; per-wake figures are sums over a
   `wake_id`. Additive columns, no schema break.
8. **The Overseer's mode is a switch**, `single` (a docket header, then one
   proposal per turn) or `all` (today's ruling briefing as one turn), settled by
   paired runs on a scratch copy of the queue with the fort paused. Honestly sized,
   about 15 to 20 dockets will show only a large quality gap (around 15 points in
   the rate of indefensible rulings); smaller effects will read as inconclusive, so
   the decision rule for that case is set before the runs (D10).
9. **Migration**: a per-role flag in `conductor/policy.yaml`, one-shot stays the
   default and the rollback, the Consultant goes first. Seven stages, each with a
   live check.

## 2. What the evidence settles, and what it does not

| Question | Finding | Source | Conf. |
|---|---|---|---|
| Can one session take several messages? | Yes, both routes; turn 2 recalled a code word with no tool call | multiturn README, results tables | V |
| Overhead per message | Local 7 to 9 s (container start, plugin load); gateway about 2 s (client container start) | multiturn README | V |
| Reset keeping the key | Gateway `/new` works on demand; `/new` sent to `--local` is plain text and does nothing; a fresh key is the safe local reset; idle reset can fire mid-wake and must stay unset | multiturn README, Addition A and B | V |
| Cache after reset or new process | cacheRead 30208 to 30720 of about 30.5k on the first turn after a reset or in a new process | multiturn README | V |
| Real Overseer prefix stable across runs | Byte-identical up to the user message (tools 104,905 bytes, system 8,208 chars); differences start in the user message (timestamp, briefing, Runtime line with session ids) | cache-miss README | V |
| Inner timeout leaves the session usable | Yes (local, `--timeout 1`): `incomplete_turn`, `livenessState paused`, next turn fine, but the timed-out prompt stays in history | multiturn README | V |
| Gateway abort | `chat.abort`/`sessions.abort` persist the partial reply and repair dangling tool calls; next turn works | source report 5 | S |
| `--local` on SIGTERM | Does not send `chat.abort`; a hard kill mid-write was not tested | source report 5, multiturn README | S, gap |
| Gateway restart | Resumes an interrupted turn with its recorded tool calls; three failed starts, then a reset | source report 5 | S |
| Queue modes (`steer`, `followup`, `collect`) | Documented for the Gateway reply pipeline and embedded chat; an `agent` RPC to a busy session waits in the session lane instead | source report 4 | S |
| Exclusive state ownership | `--local` and exec take an exclusive lock on their state dir | source report 1, 8 | S |
| `agent exec` sessions | New random session id per call, no session flag | source report 1 | S |
| MCP tools inside a pushed turn | Not tested (the throwaway agent had no MCP servers) | multiturn README | gap |
| Gateway token auth | Not tested (live test used `--auth none` on loopback) | multiturn README | gap |
| Charter in the system message | In the capture the workspace `SOUL.md` showed as `[MISSING]`; not established whether real runs behave the same | cache-miss README, caveat | gap |
| Installed image version | Not inspected; tag and main differ (Runtime `sessionId`, queue, reset service) | source report, risks | gap |

Two consequences shape the whole design. First, no route gives a verified way to
put text in front of a model in the middle of a turn, so "mid-run push" is built
as a push at the next turn boundary, with true injection left to a test (S7).
Second, a gateway restarted on the same state directory resumes the interrupted
turn, so a hard stop must never be followed by a restart on the same directory;
that is the main reason for per-wake state directories.

The 2026-09-22 register row chose "dispatcher plus queue, not openclaw's Gateway
or native agent messaging". This design keeps that shape: the conductor remains the
dispatcher and the queue remains the only channel between roles. The Gateway is
used only as a transport for one role's turns inside one wake, which that row did
not consider. Say so to the red team rather than treating it as reopened.

## 3. Transport

### 3.1 Options

**A. Gateway, one container per role per wake, CLI thin client per message
(recommended).** Per wake and role the conductor:

1. copies the role's template state dir to `<conductor state>/sessions/<wake_id>/<role>/state`;
2. starts `docker run -d --name conductor-gw-<role>-<wake8> --hostname <role> ...
   openclaw.mjs gateway run --bind loopback --auth token --port <p>`, with the same
   mounts as today's runner: the per-wake state at `/home/node/.openclaw`, the
   role's pinned config read-only over `openclaw.json`, the role workspace, the
   secrets env file, and the gateway token supplied by env file;
3. waits for readiness (a cheap read, for example `openclaw.mjs health` or a
   `sessions list`, to be chosen at S0) with a bound;
4. for each message runs a short client container `docker run --rm
   --network container:conductor-gw-<role>-<wake8> ... openclaw.mjs agent
   --session-key agent:<role>:wake --json --timeout <s> --message-file <f>`, so the
   client reaches the gateway's loopback without host networking and two parallel
   gateways never collide on a port;
5. at close, `docker stop` then `docker rm` the gateway, reads the transcript from
   the state dir (today's `read_transcript`, unchanged), and deletes the dir.

Why: about 2 s per message, on-demand reset if wanted, the documented clean abort
(SIGTERM on the client sends `chat.abort` for an accepted run, [S]), idempotency
keys on `agent` (a repeat returns `in_flight`, [S]), and the only route on which
`steer` could later be tried. Costs: a container start per wake (time not measured,
S0), gateway token auth (not tested), and a long-running process per role for the
length of one wake (supervised by the conductor's own container naming, section 9).

`--network container:<name>` sharing the gateway's network namespace is standard
docker behaviour [I]; S0 checks it. If it fails, `docker exec` into the gateway
container with the client's own empty state dir set by env is the second choice
[I], and host networking with distinct ports the third.

**B. `agent --local --session-key` per message (fallback).** One `docker run --rm`
per message against the same per-wake state dir, messages strictly serial (the
state dir lock). Close to today's runner (`build_command` gains `agent --local
--session-key ... --message-file` in place of `agent exec ... <prompt>`). Costs 7
to 9 s per message, has no abort path (SIGTERM does not send `chat.abort`), and a
hard kill mid-write may leave a stale lock (untested). With 3 to 8 items a wake the
overhead is under a minute and does not matter against 5 to 10 minute role runs; the
abort gap does.

**C. A Python WebSocket client to the Gateway.** `agent` plus `agent.wait {runId,
timeoutMs}` plus `sessions.abort` gives the cleanest timeout handling [S], but the
SDK is private and not on npm, and the protocol (challenge, `connect`, scopes,
v4 frames) would be ours to maintain. Not now; revisit only if the CLI client's
timeout or abort proves unreliable at S0.

### 3.2 Interface

One protocol in a new `conductor/session_runner.py`, two implementations and a
fake, so `cycle.py` never knows which route runs:

```
class SessionTransport(Protocol):
    async def open(self, role, wake_id, *, model, charter) -> SessionHandle
    async def send(self, handle, text, *, turn_wait_s, idempotency_key) -> TurnResult
    async def abort(self, handle) -> AbortResult        # gateway: SIGTERM client, verify idle
    async def close(self, handle) -> SessionClose       # transcript, cleanup
TurnResult: status, ok, liveness, timed_out, wall_s, model_ms, usage, cost_usd,
            final_text, error_kind, assistant_turns
```

`TurnResult` reads the envelope fields the multiturn test named: `payloads[0]`
not `isError`, `meta.livenessState` (`working` good; `paused`, `abandoned` bad),
`meta.error`, `meta.agentMeta.usage` and `lastCallUsage` [V for the local route;
the gateway wraps the same `meta` in `{runId, status, summary, result}`, V].

### 3.3 Process model on the agent VM

- The conductor stays what it is: a Python process under `conductor.service` (venv
  on the host, `SupplementaryGroups=docker`, `ReadWritePaths` covering
  `/var/lib/conductor` and `/opt/openclaw`) that launches containers [V,
  `infra/units/openclaw/conductor.service`]. Nothing new runs as a service.
- Per role a **template state dir** (for example `/opt/openclaw/role-state/<role>/`)
  holding only the auth store and the provider plugin (`npm/`), refreshed from the
  shared `openclaw_state_dir` by the deploy, never written at run time. The live
  test had to copy the DeepSeek plugin into a fresh state dir, and real pinned
  configs rely on the persisted auth store [V, multiturn README "Setup lessons"],
  so the template must carry both. S0 measures its size and copy time.
- Per wake and role a **session state dir** copied from the template, owned by
  that role's gateway alone, deleted at close. This is also what makes parallel
  roles safe: today all roles mount one shared `openclaw_state_dir` read-write and
  only run one at a time [V, `runner.py` `build_command`].
- The role workspace is wiped at open apart from the charter written as `SOUL.md`
  (today's `write_soul`), so no workspace memory file carries across wakes. The
  throwaway test showed the built-in memory tool leaking across resets [V]; the
  fort configs appear to expose only MCP tools (82 for the Overseer in the
  capture, matching its allowlist) [I], which S0 confirms.
- Image pinned by digest in conductor config instead of `:latest`, recorded per
  run. The tag-to-main drift in reset, queue and the Runtime line [S] makes an
  unannounced image change a behaviour change.

### 3.4 Concurrency

Today the roles run serially in a fixed order: Planner first so a new plan is in
place before anyone is briefed, then advisors, then the Consultant (re-woken for
asks filed by advisors earlier in the same cycle), then the Overseer, then the
execute phase [V, `cycle.py` role loop, `triage.py`, `service.py` `ROLES`]. That
order is load-bearing for the Planner and for the Overseer, not for the advisors.

Recommended order once sessions are stable: **Planner; then Architect,
Quartermaster and Consultant concurrently; then the Overseer; then execute.**

- The Consultant's session opens with the advisors' and takes asks as items as
  they are filed: the conductor re-reads `queue.overview` after each advisor turn
  and pushes any new ask addressed to it. It closes when every advisor session has
  closed and no ask is open for it, or at its budget. This replaces today's
  one-shot re-wake after the advisors.
- Later (S6), an answer to an ask from an advisor whose session is still open is
  pushed into that session as an item, so the asker can act in the same wake
  rather than on the next `answer_ready` wake.
- The Overseer stays last so it rules on a complete docket. Pipelining proposals
  into an open Overseer session as they are filed is possible but would make the
  docket unstable, which conflicts with the grouping experiment; not proposed.

What must change before parallel runs:

1. **Proposal and ask attribution.** `lanes.attribute_new_proposals` credits every
   pending id that appeared during a role's run to that role, because "the
   conductor cannot read an author" [V, `cycle.py` comment before the call,
   `lanes.py`]. With two advisors running at once that is wrong. The author is on
   the record (the ruling briefing prints `p.get('role')` from
   `queue.pending_brief` [V, `briefing.py`]), so attribution should read it: add
   `role` per id to `queue.overview` (a dfmcp change) or use `pending_brief`.
2. **One state dir per role** (above).
3. **dfmcp under concurrent callers.** DFHack calls go through a pool of 4
   connections, each serialised [V, `dfmcp/dfhack_client.py`, `server.py`
   `pool_size: 4`]; queue writes are serialised (CLAUDE.md notes a deliberate race
   test on unserialised raw appends). Two advisors filing the same action at once
   should hit the duplicate refusal for the second; that the check and the append
   are atomic under the serialisation is [I], S6 tests it.
4. **Provider rate limits** for concurrent DeepSeek calls: unknown [gap]; S6 watches
   for 429s.

Cost is unchanged by parallelism; only wall time drops. Concurrency is a policy
switch (`sessions.parallel: false` by default) so a problem reverts to serial
without a deploy of code.

## 4. The inbox as data

### 4.1 What an item is

An item is one thing a role must deal with in this wake, made from inputs the
conductor already computes; nothing new is observed.

| Role | Items | Built from |
|---|---|---|
| Overseer | one per pending proposal shown (cap 8, as `OVERSEER_BRIEF_CAP`); one per accepted-not-carried-out proposal; one verdict item on `tripwire` or `unexplained_pause` | `queue.pending_brief`, `to_carry_out`, pause watch [V] |
| Architect, Quartermaster, Planner | one per lane pending key (`alert:`, `ruling:`, `ore:`, `unsupplied:`, `noble_room:`, `answer:`, step and idle wakes), one per keyless wake reason (`routine_review`, `stuck_job`, `vital_nearing_threshold`, plan wakes) | `LaneState.pending`, `triage` wakes and reasons [V, `lanes.py`, `triage.py`] |
| Consultant | one per open ask addressed to it | `queue.overview` asks [V] |
| Any | control pushes: pause state changed, item superseded, tripwire latched | pause poller (6.4) |

Row shape, in a conductor-side SQLite file beside the cursor and lane stores
(single writer, like them):

```
item_id      "<wake_id>:<seq>"
wake_id      one per (cycle, role, session); equals run_id in one-shot mode
role, seq, class, kind, key       key = the coalescing key (lane key, proposal id, ask id, reason)
ref          proposal id / ask id / lane key / reason
text         the rendered item, fixed at creation
created_cycle, created_at, game_tick
status       queued | sent | done | timed_out | failed | superseded | carried | dead
strikes, attempts
turn_run_id  the runs row of the turn that handled it
result_refs  queue record ids found for it (rulings, answers, proposals, passes)
```

Coalescing: one open item per (role, key). A later signal for the same key updates
the open item's text and adds a reason line, never a second item. This is the wake
audit's fact coalescing applied at the item level; it does not by itself fix the
audit's cross-reason pile-up (five reasons for one drink fact), which needs a
`fact` key in policy (wake audit section 5) and is out of scope here.

### 4.2 Ordering and priority

Classes, served in order, stable within a class:

1. **control**: pushes (never stand-alone turns unless no item follows, see 6.4);
2. **safety**: the Overseer's verdict item on a tripwire or unexplained pause;
3. **owed replies**: asks addressed to the role, answers to its asks, rulings on its
   own proposals, step attention on its projects;
4. **lane work**: alerts, ore, unsupplied buildings, noble rooms, stuck jobs, plan
   wakes;
5. **routine**: routine review last.

Within the Overseer's proposals: urgency (the proposal's priority field) high to
low, then oldest first, then id. Order is deterministic so a replay renders the same
bytes (cache, audit). No randomised order (the permutation-consistency idea in the
inbox research is noted and declined for the same reasons it gave).

`max_items_per_wake` (policy, start 8) caps a wake; the rest are carried with no
strike and reported as a count line in the docket header.

### 4.3 Acknowledgement and idempotency

An item is done when its goal state is visible, checked by the conductor after the
turn, never taken from the model's prose:

| Item | Done when | Retry is safe because |
|---|---|---|
| Proposal to rule | a ruling naming it exists after the turn (accept, reject or defer) | a final ruling is accepted once; later rulings on it are refused [V, `dfqueue/store.py` `FINAL_DECISIONS`]; a repeated defer is allowed and would only add a defer |
| Accepted, not carried out | the step's `queue.executed` or the project exists, as today | the server requires the project and `step_id` [V, register 2026-10-05] |
| Ask to answer | an answer record for the ask exists | at most one answer per ask, enforced at write time [V, `store.py` `open_asks`] |
| Lane item | the turn ended ok (`ok`, liveness `working`) | a proposal repeating an open action is refused naming the original, any role [V, register 2026-10-07 "Duplicate proposals are refused by action, not wording"] |
| Verdict item | a `pause.verdict` from this turn (today's `read_verdict_after`) or an escalation | the pause watch reads the verdict once [V, `pause_watch.py`] |

Exactly-once filing therefore rests on the queue, not on the transport: the queue
is the write-ahead log and the server refuses the repeat. On the gateway route each
`agent` call also carries `idempotency_key = item_id:attempt`, so a client retry
after a lost connection returns `in_flight` instead of a second run [S].

Before any retry the conductor reads the goal state first. This is the same rule the
execute phase already follows for uncertain steps ("a call that may have been sent
is read, never retried blind", [V, `execute.py` docstring step 2]).

### 4.4 Unfinished items

| Situation | Item becomes | Strike | Lane state |
|---|---|---|---|
| Never sent (budget spent, cap reached, wake cut short) | `carried` | no | lane key stays pending, served next wake |
| Sent, turn timed out | `timed_out`, carried | yes | stays pending |
| Sent, provider or envelope error | `failed`, carried | yes | stays pending |
| Sent, conductor crashed before reading the result | resolved at restart by reading the goal state: `done` if met, else `carried` | no (not the item's fault) | stays pending unless done |
| Goal reached by another path (proposal closed by the conductor, ask answered elsewhere) | `superseded` | no | cleared |
| Third strike | `dead`, site alert once, no further wake for this key until the condition changes | n/a | cleared, recorded |

A timed-out item is not retried in the same wake: an item that exhausted one turn
budget is likely to exhaust the next, and the wake audit's Architect runs that timed
out twice in a row are the case in point. `clear_served` today clears a role's lane
pending only after a whole run is ok [V, `cycle.py`]; under sessions it clears per
key, for done or superseded items only.

## 5. Timeouts

**What the register says.** I searched the register, `Working.md`, the research
files and both memory indexes for an earlier user preference for "one overall
timeout plus per-turn waits" and found none recorded. The nearest are the 600 s
default and the Overseer's raise to 1200 s (register 2026-09-25), the 2026-10-05
research's soft budget shown to the worker, and the 2026-09-23 row on measured run
timing. The design follows the brief's statement of the preference; if the user
meant something else, D6 is where to say so.

Design:

- **Overall budget per role per wake** = today's `role_timeout_seconds` (600 s,
  Overseer 1200 s), enforced by the conductor across all of the role's turns.
- **Per-turn wait** = min(per-item cap, remaining budget), passed as the turn's
  inner `--timeout`, with an outer grace (today 60 s, `OUTER_KILL_GRACE_SECONDS`)
  before the conductor acts itself. Per-item cap: start at half the role's budget,
  so one item can never starve the rest, policy data per item kind.
- **On the inner timeout** (envelope `incomplete_turn`): the session stays usable
  [V, local]; the item is `timed_out`; the next item's message starts with one line:
  "Item k (ref) was stopped at its time limit and will come back next wake; do not
  continue it." The prompt that timed out stays in history [V], which is why the
  line is needed.
- **On the outer grace expiring**: stop the client container (SIGTERM, then kill);
  on the gateway route that sends `chat.abort` [S]; confirm the session is idle with
  the next send (an `in_flight` reply means it is not). If it is not idle, stop the
  gateway, discard its state dir, and open a fresh session (new state dir copy,
  briefing again) for the remaining items. Never restart a gateway on the old dir:
  restart recovery would resume the aborted turn, tool calls included [S].
- **Budget left for fewer than a minimum turn** (policy, start 60 s): stop sending;
  the rest are carried.
- The `expected calls` hint in the ruling ask stays, per item in `single` mode.

## 6. Session lifecycle

### 6.1 Open

1. Triage decides which roles wake (unchanged). The inbox builds the role's items.
   No items, no session.
2. Copy the template state dir, wipe the workspace, write `SOUL.md`.
3. Start the transport (gateway, or nothing for the local route).
4. `conductor.report` phase `wake_open` (new) with `wake_id`, role, the item list
   (ids and kinds only) and the mode.

### 6.2 Briefing (first message)

The first message is the wake briefing plus the first item, in one turn, so no turn
is spent on "ready". Order, stable material first and the ask last, as today:

```
WAKE <wake_id> role=<role> reasons=<all reasons> game tick <t>
FORT <pause line, 6.4>
VITALS ... / ALERT ... / ROADMAP ...           (as today's briefings)
DECIDED, DO NOT REDO ...                       (Overseer, as today)
DOCKET <n> items this wake: one line each (id, kind, ref, urgency); <m> carried
HOW THIS WAKE RUNS: items arrive one at a time; finish each, then stop and wait.
ITEM 1 of n: <item text>
<the item's ask>
```

For advisors the JSON briefing of `build_briefing` stays as the body until a text
form is designed; the items and docket lines are added. The own-filings block is
off from S1 (`own_filings.recent: 0`; the register row decided it, but HEAD's
`conductor/policy.yaml` still has `recent: 5` [V], so S1 flips it).

### 6.3 Item loop

For each next item: build the message (`ITEM k of n`, any control lines queued since
the last turn, the item text, its ask), `send`, read the `TurnResult`, check the goal
state (4.3), write the item row, report the turn (`conductor.report` phase `end`
with `wake_id`, `item_seq`, kind, ref), update lane state for that key. Stop on: no
items left, budget spent, two consecutive failed turns, a tripwire latch (6.4), or
the session token ceiling (rotate, 6.6).

### 6.4 Pause state: briefing line and pushes

**Briefing line (now, independent of sessions).** One line from reads the conductor
already makes: `clock.status`, `pause.why`, the hold store, the tripwire latch, the
pause watch state and its panel note [V, `pause_watch.py` `panel_note`]:

`FORT paused since tick T: <operator hold | tripwire <name> | conductor escalation |
player or popup <announcement> | panel <name> blocks resume | unexplained>` or
`FORT running at <fps> fps`.

The ruling briefing today has no such line [V, `briefing.py`]; the register row says
it goes in now, so it is S1 work for both briefing builders.

**Pushes during a wake.** A poller task polls `clock.status` every
`pause_poll_seconds` (start 15 s) while any session is open, and `pause.why` when the
state flips. A change becomes a control item for every open session:

`FORT CHANGED at tick T: running -> paused (tripwire thirst_critical latched).`

Delivery is at the next turn boundary, prepended to the next item's message. If the
session has no further item and the change matters to its open work (a tripwire), it
is sent as a stand-alone short turn. Reason: no transport offers a verified way to
reach a model mid-turn (section 2); an `agent` call to a busy gateway session waits
in the lane [S], and `steer` is documented for the reply pipeline, not shown for
`agent` calls. A true mid-turn push is S7: test `steer` (or `sessions.send`) on the
gateway, and adopt it only if it injects without corrupting the turn.

A separate, transport-independent route reaches a model mid-turn today: dfmcp could
add `fort: {paused, why}` to every tool reply while the fort is paused. It needs no
openclaw feature and also serves one-shot runs. That is not what the user chose, so it
is offered as D8, not designed in.

**Tripwire mid-wake.** On a latch: push the change, start no further item in any
session, let in-flight turns end within their wait, close every session (the
remaining items carried, no strikes), and run the tripwire cycle at once. The
tripwire path itself is unchanged.

### 6.5 Close

Read the goal state of every item one last time, report `wake_close` (counts: done,
carried, timed out, dead; cost and wall sums), stop and remove the gateway, read the
transcript from the state dir, split it per item (6.7), delete the state dir, delete
`SOUL.md`. Lane cursors and the routine-review cursor commit as today, but per item:
the role's diff cursor advances when the wake closes with no `failed` item; the
routine-review cursor advances when the `routine_review` item is done.

### 6.6 Reset and rotation

Each wake starts in a new state dir, so it starts at the system prompt with no
history; that is the reset (D2). Inside a wake a **token ceiling**
(`max_session_tokens`, start 250k, from the turn's reported input plus cacheRead)
closes the session and opens a fresh one for the remaining items with the briefing
again plus a line naming the items already handled. DeepSeek's window is 1M and
openclaw would not compact before about 980k [S, inferred trigger], well past where
long-context decay sets in (persistent-sessions section 4), so the ceiling is ours.
Compaction and pruning stay off (pruning rewrites old messages and breaks the prefix
cache [S]).

### 6.7 Prompt cache

What stays byte-stable, and so cached across wakes and across roles' wakes:
the tool list (sorted by name) and the system message, apart from the date line in
its dynamic tail [V, cache-miss README and multiturn capture]. Rules for everything
else:

1. Nothing variable in the charter or the tool list; deploys that change either cost
   one cold prefix per role, so batch them (Working.md lesson 2026-10-08).
2. The wake briefing goes in the first user message. The first user message also
   carries openclaw's timestamp prefix and its relocated Runtime line (session ids on
   the tag, not on main) [V, S], so it is never cacheable across wakes; that is a few
   hundred tokens.
3. Items and pushes are appended as new user messages, never edited in, never
   re-rendered. Within a wake, turn k reads everything before it from cache [V,
   turns 2 and 3 read about 31k cached on the throwaway]. DeepSeek reasoning content
   is replayed in history [S], so earlier reasoning is input, cached.
4. The docket header is fixed for the wake. A change (an item superseded) is said in
   a later message, not by rewriting the header.
5. Item text is deterministic: sorted keys, no wall-clock times, game ticks only.
6. The date line changes at UTC midnight; a wake crossing it pays one cold tail.
7. **Check first:** the cache-miss capture showed the charter `[MISSING]` from the
   system message. If real runs do the same, every role has been running without its
   charter in the system prompt, which matters more than any cache question. S0
   checks a real run's request before anything else is built.

## 7. Transcripts and metrics

**Runs rows.** One row per item turn, written through `conductor.report` as today,
with additive columns in `dfqueue/runs.py` and `dfmcp/conductor_tools.py`:
`wake_id`, `item_seq`, `item_kind`, `item_ref`, `session_mode` (`oneshot` or
`session`), `transport`, `arm` (experiment only, null otherwise). In one-shot mode a
run is one wake with one item (`wake_id = run_id`, `item_seq = 1`), so old and new
rows read the same way. Rationale for per-item rows: records a run touched are found
by role and time window (`records_in_window` [V, `dfqueue/runs.py`,
`wake_metrics._run_record_ids`]); a role's items are sequential, so per-item windows
attribute each filing to the item that made it, which per-wake rows cannot.

**Transcript per item.** The session's `transcript_events` are read once at close
(today's `read_transcript`, from a state dir that held only this wake) and cut at
each user message into per-item segments, each stored on its item's row and capped by
the existing `transcript:` policy block. The wake row (`wake_open` and `wake_close`
reports) carries the docket and counts. Reasoning is cut the same way.

**`wake_metrics`.** Per-wake rows become sums over `wake_id` (cost, rounds, tokens,
first write round, orientation reads, `passed`); every existing group and the
published schema `wake_metrics/1` stay valid, since additions are not breaking. New,
additive: an `items` group per role (items per wake, done rate, timed-out rate,
carried, dead, turn overhead seconds = wall minus model time, cache read share per
turn). The sweep rule (runs within 120 s are one sweep) still works with overlapping
parallel runs, since an overlap reads as a gap under 120 s [V, `_sweeps`]; a
`cycle_id` column would be cleaner and is cheap to add with the others.

**Board.** The awake strip and transcript tab group rows by `wake_id` (one card per
wake, items inside), a `dfqueue/live.py` change. Public text rules are unchanged.

**Archive.** The per-cycle JSON gains each role's item list and outcomes beside its
briefing.

## 8. The Overseer switch and the paired-run experiment

### 8.1 The switch

`sessions.overseer_ruling_mode: single | all`.

- `all`: today's `build_ruling_briefing` as one turn inside a session. Behaviour
  equals today's except the transport, so it is the safe first setting.
- `single`: the briefing carries a docket header listing every proposal (id, role,
  type, urgency, one-line summary, `duplicate_of` and `overlaps` flags from
  `pending_brief`), then one proposal per turn with its full block (rationale,
  prediction, cited facts, preview), and a line naming what was already ruled this
  wake. The header is what the inbox research recommended to keep cross-item
  awareness when items are judged singly (session-inbox section 5).
- A third mode, `by_fact` (one fact group per turn), was the research's preferred
  shape but needs a fact key on proposals that does not exist reliably today; it is
  left out of the experiment to keep two arms and the power it has.

### 8.2 The experiment

**Question.** Does `single` rule as well as `all`, and at what cost?

**Isolation.** The fort paused under the operator hold, unchanged throughout. A
second dfmcp instance (own port, same role tokens) pointed at a scratch copy of the
queue, with game writes refused (a server flag; dfmcp has no such flag today, so it
is S4 build work [I]). Each run gets its own fresh copy of the docket's snapshot, so
neither arm sees the other's rulings. Its runs store sits beside the scratch queue,
so the experiment never enters the live metrics. Both arms get the "rule only" ask
(no carrying out), since carrying out would hit the write refusal: this departs from
production for unrouted types and is stated as a limit.

**Dockets.** A docket is a snapshot of pending proposals. Two sources: (a) the live
pending set when the experiment runs; (b) fresh dockets made by running the advisors
on the paused fort into a scratch queue with their real wake reasons, keeping only
dockets with 3 or more proposals. Historical dockets rebuilt from the append-only
queue are not used as the main source: cited facts are refreshed against today's
fort, so old proposals turn into "obviously stale", a different test.

**Pairs.** Each docket ruled once per arm, arm order randomised per docket; a second
replicate per arm on a third of dockets gives the within-arm noise floor
(test-retest agreement).

**Measured.**

- Primary: the share of rulings judged not defensible, paired by proposal (same
  proposal under both arms), tested with McNemar on the discordant pairs.
- Consistency errors, objective: accepting both of a pair flagged `overlaps` or
  `duplicate_of` by `pending_brief`, and rulings whose reason contradicts another
  ruling in the same docket.
- Cost per docket, wall time per docket, rounds per proposal, cache-read share,
  defer rate, and how often a reason cites another item.

**Judging quality.** Blind: the grader sees the docket, the cited facts and each
ruling with its reason, arm hidden and proposals shuffled, and marks each ruling
defensible or not with a one-line reason. An Opus grader rates all rulings; the user
reviews every case where the grader and the within-arm replicate disagree, plus a
random 20 percent. Model judges show position and verbosity bias but reach over 80
percent agreement with people (session-inbox section 5), so the user check is the
calibration.

**Sample size, honestly.** Live dockets are small (the queue has rarely held more
than a handful of pending proposals), and each fresh docket costs an advisor run plus
two Overseer runs. A realistic set is 15 to 20 dockets of 3 to 5 proposals, so 50 to
90 paired rulings. With a paired test that detects only a large gap, about 15
percentage points in the indefensible rate (for example 20 percent against 5
percent) at conventional power [I, normal approximation; the true rate is unknown].
A gap of 5 to 10 points will usually read as inconclusive. Cost and wall time
differences are measured far more precisely and will likely be the deciding numbers.
Money is small: about 40 to 60 Overseer runs at the observed $0.06 average plus
advisor runs and the grader, a few dollars. Calendar time is the cost: it needs the
scratch dfmcp instance and supervised sessions.

**Decision rule, set before the runs (D10).** Recommended: if one arm is worse on
quality by the test, choose the other; if quality is inconclusive, choose the arm
with lower cost per docket, and if cost is within 15 percent, `single` (the user's
stated design). Report the result as a register row with the numbers, including
"inconclusive" if that is what it is.

## 9. Failure modes and recovery

| Failure | Detection | Recovery |
|---|---|---|
| Gateway fails to start, or auth error | readiness bound, envelope error | that role runs one-shot this wake (items rendered into one briefing as today), one site alert; policy `fallback: oneshot` |
| Turn hits its inner timeout | `incomplete_turn` | item `timed_out` plus strike; session continues with the stop line (5) |
| Turn hangs past the grace | conductor wait expires | stop client (abort); if not idle, stop gateway, new session for the rest |
| Provider error, empty or bad JSON envelope | envelope parse, as today's runner | item `failed` plus strike; two in a row ends the wake |
| Conductor crash mid-wake | systemd restart | at start: remove containers named `conductor-gw-*` and `conductor-cl-*`; resolve `sent` items by goal state; close dangling runs rows as `abandoned`; delete stale session dirs |
| Restart recovery would resume an aborted turn | by construction | never restart a gateway on a used state dir |
| Session grows large | token ceiling | rotate (6.6) |
| Item overtaken mid-wake | goal state read before sending | `superseded`, skipped, said in the next message |
| Duplicate filing on retry | server refusal | idempotency rests on the queue (4.3) |
| Workspace or memory leakage | S0 check of tools and workspace | workspace wiped per wake; built-in tools off |
| Charter missing from the prompt | S0 capture | fix before S2 |
| Tripwire latches mid-wake | pause poller | push, stop starting items, close, run the tripwire cycle |
| Parallel roles collide on a state lock | per-role dirs | by construction |
| A key always times out | strikes | dead letter after 3, alert, no re-wake until the condition changes |
| Image changes under `:latest` | digest recorded per run | pin by digest |
| DeepSeek cache evicted between wakes | cacheRead in usage | cost only; nothing to recover |

## 10. Migration

`conductor/policy.yaml` gains:

```yaml
sessions:
  transport: gateway            # gateway | local
  roles:                        # oneshot | session, per role; oneshot is the default and the rollback
    consultant: oneshot
    architect: oneshot
    quartermaster: oneshot
    planner: oneshot
    overseer: oneshot
  overseer_ruling_mode: all     # all | single
  parallel: false
  max_items_per_wake: 8
  item_wait_fraction: 0.5       # per-item cap as a share of the role budget
  min_turn_seconds: 60
  max_session_tokens: 250000
  pause_poll_seconds: 15
  strikes_to_dead_letter: 3
  fallback: oneshot
```

`DockerOpenClawRunner` stays as is. Rollback for a role is one line back to `oneshot`.
It takes effect on the next `--once` run, but under the service only after a restart:
`conductor/service.py` `build_deps` loads the policy and the charters once at start
[V], although the `service.py` module docstring and `load_charters`'s own docstring say
charters are "read fresh every cycle". That is a doc-versus-code discrepancy worth
fixing on its own (reload policy per cycle, or correct the docstrings); flagged here,
not changed. New code: `conductor/inbox.py` (pure: build, coalesce, order, render,
ack checks), `conductor/session_runner.py` (transport protocol, gateway, local, fake),
a session loop called from `cycle.py` per role, dfmcp `conductor.report` fields and
`runs` columns, `live.py` grouping, `wake_metrics` items group.

Stages, each with its live check (fort paused, operator hold on, unless stated):

| Stage | What | Live check |
|---|---|---|
| S0 | Checks only, throwaway agent plus one real role config (Consultant, read-only tools): pinned image digest; gateway with token auth on loopback; client via `--network container:`; MCP tools in a gateway session; a real run's request captured to see whether the charter is present; SIGTERM the client mid-tool-call, then a next turn; gateway start time and template copy time; transcript read per turn | a written `evals/live/` README answering each check; nothing built until the charter question is answered |
| S1 | Inbox as data, rendered into today's one-shot briefings; FORT pause line in both briefing builders; own-filings block off; runs columns (`wake_id` etc.) | one `--once` cycle: inbox rows exist, one item per role-run row, the FORT line correct for the hold, Board and Metrics unchanged |
| S2 | Session runner for the Consultant (asks as items), pause poller and turn-boundary push | a cycle with two asks open: both answered once, two item rows under one `wake_id`, per-item transcript on the Board; flip the hold during the wake and see the push land in the next item's message |
| S3 | Architect, Quartermaster, Planner on sessions, serial | a cycle with each advisor holding at least two items; lane keys clear per item; a forced inner timeout on one item carries it with a strike |
| S4 | Overseer on sessions in `all` mode; then the scratch dfmcp instance and experiment harness; run the pairs | `all` mode rules a live docket the same way a one-shot run would (same records); experiment report as an `evals/live/` README and a register row |
| S5 | Set the Overseer mode by the experiment's rule | next live ruling wake in the chosen mode |
| S6 | Parallel advisors and Consultant (after the attribution fix), answer push to an open asker | one cycle in parallel: attribution correct on simultaneous filings, no state-lock errors, no 429s, wall time recorded |
| S7 | Optional: test `steer` or `sessions.send` for a true mid-turn push | a throwaway session takes an injected line mid-turn without a broken turn; adopt only then |

Arming `conductor.service` stays on its own track (Working.md phase 2, the user's yes
on the day). Sessions can be built and checked entirely under hand-run `--once`
cycles.

## 11. User decisions

One per line, recommendation first.

- **D1 Transport.** Recommend a Gateway per role per wake with the CLI thin client, `agent --local --session-key` as the fallback behind the same interface. Alternative: local only (simpler, no abort path).
- **D2 Reset.** Recommend a fresh per-wake state dir copied from a per-role template. Alternative: literal `/new` on a persistent per-role store (needs admin scope, keeps growing history on disk, transcript reads must filter by window).
- **D3 Concurrency.** Recommend serial first, then Planner, then Architect, Quartermaster and Consultant in parallel, then the Overseer, behind `sessions.parallel`, after the attribution fix.
- **D4 Done means.** Recommend server-verified goal states for rulings, answers, carry-outs and verdicts; turn completion for lane items.
- **D5 Strikes.** Recommend a strike only for a started item that timed out or failed, three strikes to a dead letter with one site alert; never-started items carried free.
- **D6 Timeouts.** Recommend one overall budget per role per wake (today's 600 s, Overseer 1200 s) and a per-turn wait of min(half the budget, what is left). I found no earlier register record of the user's preference; confirm this is it.
- **D7 Timed-out item.** Recommend not retrying it in the same wake; it returns next wake with its strike.
- **D8 Tool-reply pause stamp.** Recommend adding `fort: {paused, why}` to dfmcp tool replies while paused, as the only verified mid-turn channel and useful to one-shot runs too; not in the user's original choice, so ask.
- **D9 Experiment arms.** Recommend `single` (with a docket header) against `all`; `by_fact` later if proposals gain a fact key.
- **D10 Inconclusive rule.** Recommend: worse quality loses; if inconclusive, the cheaper arm per docket; within 15 percent on cost, `single`.
- **D11 Quality judge.** Recommend a blind Opus grader on every ruling, the user reviewing all grader-replicate disagreements and a random 20 percent.
- **D12 Experiment isolation.** Recommend a second dfmcp instance on a scratch queue copy with game writes refused, both arms on the "rule only" ask.
- **D13 Runs rows.** Recommend one row per item with a `wake_id`, per-wake figures summed.
- **D14 Session ceiling.** Recommend rotating to a fresh session at 250k tokens within a wake.
- **D15 Image pin.** Recommend pinning the openclaw image by digest and recording it per run.
- **D16 First role.** Recommend the Consultant first, the Overseer last.
- **D17 Tripwire mid-wake.** Recommend: push, start no new items, close sessions, run the tripwire cycle at once.

## 12. Not verified

- MCP tools inside a pushed turn, gateway token auth, the client over `--network
  container:`, gateway start time, template copy time and size: S0.
- Whether real runs carry the charter in the system message: the capture showed it
  missing; S0 must answer it first.
- Gateway abort behaviour is from source, not run; `--local` hard kill and stale lock
  untested.
- Whether any openclaw route injects a message mid-turn; `steer` is documented for
  the reply pipeline only.
- Atomicity of the duplicate check under concurrent filings; DeepSeek rate limits
  under parallel roles.
- The installed image version; findings are for tag `v2026.9.4` and main.
- The wall-time estimate for parallel cycles (10 to 15 minutes) is arithmetic on the
  brief's 5 to 10 minutes per role and 17 to 22 minutes per cycle, not measured.
- Whether one item per turn changes rounds or orientation reads per item compared
  with one-shot: unknown until S3's metrics.
- Experiment power figures use a normal approximation with an assumed base rate; the
  real indefensible-ruling rate is unknown.
- The user's earlier timeout preference: not found in any repo record.
