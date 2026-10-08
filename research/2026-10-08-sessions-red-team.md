# Per-role openclaw sessions: red team

Date: 2026-10-08. Red team of `research/2026-10-08-sessions-design.md` (commit
b760956), owed by the register row of 2026-10-08 "Build per-role openclaw sessions".
Read-only: no VM touched, nothing run against the fort or the agent VM. openclaw
source was read from a fresh sparse clone of tag `v2026.9.4` (the version the
multiturn test recorded) in a scratch directory, deleted after.

Confidence key, per claim: **[V]** verified here by reading this repo's code or a
recorded live run; **[S]** verified here by reading openclaw source at `v2026.9.4`
(file named); **[I]** inferred, not checked; **[gap]** could not be checked.

## 1. Verdict

**Build it, but not this version.** The user's decision (sessions, items one at a
time, reset between wakes, pause pushes) is sound and the design serves it, but it
builds roughly three times the machinery the first useful version needs, and it
misses two things that would break safety or measurement the moment a role moves
off `agent exec`:

1. **Changing the route changes the prompt, not just the transport.** `agent exec`
   applies its own config overlay (workspace forced to the container's working
   directory, `skipBootstrap: true`, a coding tool profile); `agent` (both `--local`
   and the Gateway) does not. So a session run would, for the first time, load the
   configured workspace, which means the charter (good) and openclaw's bootstrap
   templates, including `BOOTSTRAP.md`'s "ask what to call you" first-run ritual,
   on every wake, because every wake starts from a wiped workspace (bad). Any
   comparison of sessions against today's one-shot runs would be confounded by the
   charter appearing at the same time. (B1)
2. **The session envelope is not the exec envelope.** Escalation detection, cost
   and status all read `agent exec`'s projected envelope (`toolSummary`, `costUsd`,
   `status` at top level). The `agent --json` route returns the raw `{payloads,
   meta}` shape. The design's `TurnResult` has no tool summary at all, so a clean
   Overseer escalation inside a session would not pause the fort. (B2)

Beyond those: the Gateway-per-wake transport buys about 30 to 60 s per role wake and
a clean-abort path the design's own recovery never relies on; the inbox store,
strikes and dead letters duplicate machinery the lane store and `conductor/backoff.py`
already have; and the paired experiment needs a new server flag and a harness to
answer a question it will probably return "inconclusive" on. The smallest version
worth building first is in section 4.

## 2. Findings, ranked

### Blockers

**B1. The `agent` route loads a different prompt from `agent exec`: charter,
bootstrap templates and workspace all change at once.** [S, V]

- `agent exec` overrides every agent entry's `workspace` with its `--cwd` (default
  `process.cwd()`) and sets `agents.defaults.skipBootstrap: true`
  (`src/commands/agent-exec-input.ts` `buildExecRunOverlay`, lines 123 to 147;
  `src/commands/agent-exec.ts` lines 273 and 430, `workspaceDir: cwd`). The image's
  `WORKDIR` is `/app` (`Dockerfile` lines 72 and 240) and `conductor/runner.py`
  `build_command` passes no `--cwd` and no `-w` [V]. That is the root cause of the
  register's 2026-10-08 finding "Agents have been running without their role
  charters" (`evals/live/2026-10-08-charter-delivery/`), whose own "Not verified"
  list asks exactly this. The fix that landed while this was written (3aa4d18,
  read-only mount of the charter at `/app/SOUL.md`, and a refusal to run a role
  without one) is correct for `agent exec`. `agent exec --cwd <role workspace>` (a
  documented exec flag, `src/cli/program/register.agent-turn.ts` line 112) would be
  the more direct alternative, since it makes the configured workspace real; either
  works for one-shot. Neither carries over to the session route, below: there the
  `/app` mount is irrelevant and the workspace path is what counts.
- `agent` (local or Gateway) has no such overlay: it uses the configured
  `agents.entries.<role>.workspace` and runs `ensureAgentWorkspace` with
  `ensureBootstrapFiles: !skipBootstrap` (`src/agents/command/prepare.ts` line
  370). The pinned configs set no `skipBootstrap` [V, the one committed example
  `evals/live/2026-09-15-overseer-first-ruling/pinned-config.json`; the live ones
  are described in the charter-delivery README]. On a workspace holding only our
  `SOUL.md`, openclaw then seeds `AGENTS.md` (6.4 kB, "If `BOOTSTRAP.md` exists,
  follow it", memory-writing conventions), `IDENTITY.md`, `USER.md`, and possibly
  `BOOTSTRAP.md` (5 kB, "Birth Sequence ... ask what to call you")
  (`src/agents/workspace.ts` lines 1040 to 1200; templates under
  `docs/reference/templates/`) [S; whether `BOOTSTRAP.md` is written depends on
  `workspaceProfileLooksConfigured`, not traced, so I]. The design wipes the
  workspace every wake, so this happens every wake.
- Consequences: (a) a session arm and a one-shot arm differ in the system prompt,
  so S3/S4 metrics against the pre-session baseline measure the charter and the
  templates, not sessions; (b) the templates invite memory writes and persona
  rituals in a fort role's prompt.
- **Fix.** Deploy the one-shot charter fix (landed, 3aa4d18) and re-baseline the
  one-shot metrics with charters present (a handful of cycles at least) before any
  session comparison. The session runner writes `SOUL.md` to the configured
  workspace (today's `write_soul` already does) and must not rely on the `/app`
  mount. Add `agents.defaults.skipBootstrap: true` to every pinned
  config used by a session route. S0's first check becomes: capture the request of
  the same role on both routes and diff them; the system message and tool list must
  be identical apart from the known per-run lines.

**B2. Escalation detection, cost and status depend on exec's envelope, which the
session route does not produce.** [V, S]

- `cycle.py` `_overseer_called_escalate` reads `run_result.tool_summary["tools"]`
  (line 458), and only a detected escalation pauses the fort in an ordinary cycle
  (lines 1055 to 1065). `runner.py` takes `costUsd`, `status`, `ok`,
  `assistantTurns`, `usage` from the top level of exec's envelope.
- exec builds that projection itself (`src/commands/agent-exec-result.ts` lines
  120 to 157: `status`, `ok`, `usage`, `costUsd`, `assistantTurns`, `toolSummary`
  lifted out of `meta`). `agent --json` writes the raw result (local) or
  `buildGatewayJsonResponse` (Gateway, `src/commands/agent-via-gateway.ts` line
  1189); the multiturn test saw `{payloads, meta}` and `{runId, status, summary,
  result}` [V]. `toolSummary` lives on `meta` in the embedded run type
  (`src/agents/embedded-agent-runner/types.ts` line 242) [S], so it is probably
  reachable at `meta.toolSummary` [I].
- The design's `TurnResult` (section 3.2) lists no tool summary. Built as written,
  an Overseer that calls `queue.escalate` in item 3 of a session would not pause
  the fort, and `plan_watch.last_refusal` would lose its input.
- **Fix.** `TurnResult` carries the tools called and the raw `meta`; a mapping
  function from the `agent` envelope to today's `RunResult` fields, unit-tested
  against a captured real envelope (S0); escalation checked after every Overseer
  turn, pausing at once rather than at wake close; a test where a fake session turn
  escalates and the fort pauses.

### Major

**M1. The Gateway per wake is not worth it now (D1).** [V, S, I]

What it buys, against `agent --local --session-key agent:<role>:<wake_id>` on the
same per-wake state dir:

- About 5 to 7 s less per message [V, multiturn README]. Live data put a typical
  wake at 1 to 3 items (the wake audit: 21 runs over 11 cycles; the Overseer made
  13 rulings over 6 runs), so 10 to 20 s per role wake, under 5 percent of a 5 to 6
  minute run.
- A clean abort on SIGTERM [S]. But the design never relies on it: on a hard stop it
  checks for idle and, if not idle, discards the state dir and opens a fresh session
  (section 5). The local route can simply always do that on a hard stop: kill the
  container by name (today's `_kill_container`), discard the dir, re-brief for the
  remaining items. A discarded dir also removes the one real local-route hazard,
  that the next call may treat the killed turn as interrupted and reuse its message
  (`isInterruptedTurnEntry`, source report section 5) [S, untested].
- Idempotency keys: the queue already makes filings exactly-once for rulings,
  answers and typed steps (design 4.3) [V].
- `steer` for a true mid-turn push: unverified, and the design defers it to S7.

What it costs: token auth (untested), a readiness probe, `--network container:`
(untested here), a detached long-lived container per role per wake that the
conductor must reap, restart-recovery hazards, and a second envelope shape.
Both routes need the same template state dir, since `agent --local` resolves its
auth store and plugins from its own state dir (the multiturn test had to copy
`npm/`) [V], so the template is not a Gateway-specific cost.

**Fix.** Build the local route first behind the `SessionTransport` interface; keep
the Gateway as the S7 experiment it already half is (adopt it only if `steer` is
shown to inject cleanly and the user wants true mid-turn pushes).

**M2. The inbox store, strikes and dead letters duplicate what exists.** [V]

- `LaneState.pending` already holds one pending entry per role and key, persisted
  by the lane store, and `clear_served` already clears it (`lanes.py` lines 90 to
  160, 521). `conductor/backoff.py` already gives every standing fact an
  exponential renotify counted in wakes and a `stalled` state after
  `renotify_max_wakes` (register 2026-10-07, wake cleanup). Strikes plus a dead
  letter are a second, differently counted version of the same thing.
- A new conductor SQLite store with eight item states, coalescing and crash
  resolution is the largest new surface in the design, and "set intent, let the
  game execute; beware over-engineering" applies to our own plumbing too.
- **Fix.** Derive the item list per wake, in memory, from what the cycle already
  reads (lane pending keys, triage reasons, `pending_brief`, open asks); record
  each item's outcome only as runs-row columns (`item_kind`, `item_ref`,
  `outcome`); clear lane keys per key on done; count a failed or timed-out item as
  one more wake on that key's existing backoff record, so a key that keeps failing
  stalls through the mechanism that already alerts. After a crash, nothing needs
  resolving: uncleared keys are still pending and goal states are re-read next
  cycle. Add a store only if S3's data shows a need.

**M3. Partial filings at a timeout, and double filing across strikes.** [V, I]

- A lane item is "done when the turn ended ok" (4.3). A turn that files a proposal
  and then times out is marked timed out and carried with a strike; next wake the
  role gets the same item with no sign it already filed. The structural duplicate
  refusal covers typed step identities only (`dfqueue/step_identity.yaml`, register
  2026-10-07); untyped near-duplicates are flagged `duplicate_of`, not refused
  (`store.py` lines 1007 to 1017) [V]. Three such partial successes dead-letter a
  key that was making progress.
- **Fix.** After every turn, read the records written in the item's window
  (`runs.records_in_window`, already per role and time) [V]; no strike when the
  turn wrote a record; a carried item's text names what was filed for it last time.

**M4. Duplicate check atomicity is fine; parallel advisors lose less than claimed
and gain less than claimed (D3).** [V, I]

- Atomicity: every queue write goes through `_append_locked`, one `asyncio.Lock`
  per server held around the whole `store.append` call (check and insert in one
  thread call) (`dfmcp/queue_tools.py` lines 1397 to 1412) [V]. Within the one
  dfmcp process, two simultaneous identical typed filings cannot both land. The
  design's [I] on this can become [V].
- Today's serial advisors do not see each other's same-cycle filings in their
  briefings either: `queue_state` is read once at the top of the cycle and
  re-read only after the advisors (`cycle.py` lines 905 to 935) [V]. Parallel
  running loses no briefing-level coordination.
- Savings: the wake audit records 116 minutes of agent wall clock over 11 real
  cycles, about 10.5 minutes per cycle with about 1.9 role runs per cycle, and the
  2b deploy cycle was 61 s, 266 s and 185 s (register 2026-10-07) [V]. The
  design's "17 to 22 minutes today" is about twice the recorded figure, and
  parallel advisors save `sum - max` only in cycles where two or more advisors
  wake, which the stricter lane wakes make rarer [I].
- New risks: DFHack reads are served by a pool of 4 serialised connections
  (`dfmcp/server.py` line 205) [V], and `queue.propose` bounds its cited reads at
  60 s and refuses as busy past that (`FILING_READ_TIMEOUT_SECONDS`,
  `queue_tools.py` line 1415) [V]; contention under parallel roles plus the pause
  poller could turn into "busy, file again" refusals [I].
- Today's one-shot runs probably would not collide on state locks: exec takes its
  lock on `--state-dir`, which is per run, and repoints `OPENCLAW_STATE_DIR` there
  (`agent-exec.ts` lines 118 to 128, 370 to 381) [S]. The design's "parallel needs
  per-role state dirs" is true for sessions, not a statement about today.
- **Fix.** Do the author-based attribution fix now, independent of sessions
  (records carry `role`, `runs.records_in_window` already filters on it) [V]. Keep
  `parallel` out of the plan until the runs table shows how often two advisors
  co-wake and what that costs in wall time.

**M5. Secrets multiply with the per-wake template copy.** [V, I]

- The DeepSeek key lives in plaintext in openclaw's state SQLite (register
  2026-09-14). A template "holding the auth store", copied per wake per role,
  writes a fresh plaintext key copy to disk every wake; a crash between copy and
  delete leaves copies under `/var/lib/conductor`.
- **Fix.** For the session route, set the provider key from the environment in the
  pinned config (`models.providers.deepseek.apiKey = {source: env, ...}`, the form
  the multiturn test used) [V], so the template holds only the plugin directory,
  which can be bind-mounted read-only instead of copied [I, S0 checks]. Per-wake
  dirs mode 0700, swept at start. Add the copies to the secrets-rotation reasoning
  if any remain.

**M6. Orphan sweep without a single-instance guard.** [V, I]

- The conductor has no instance lock (no `flock` or lock file anywhere in
  `conductor/`) [V]. The design's crash recovery removes every container named
  `conductor-gw-*` and `conductor-cl-*` and deletes stale session dirs at start. A
  hand-run `--once` started while another cycle is live (the service once armed,
  or two transient units) would kill the other's sessions mid-turn.
- Detached containers are not in the conductor unit's cgroup, so stopping a
  transient unit does not stop them [I]; today's runner already notes that killing
  the `docker run` client leaves the container running (`runner.py`, timeout path)
  [V].
- **Fix.** An exclusive lock on the conductor state dir held for the whole cycle;
  sweep only when the lock is held; label containers with the instance and wake id
  and sweep by label.

**M7. Advisors' keyless reasons as separate items multiply turns on one fact.** [V, I]

- The design makes one item per keyless wake reason (`routine_review`,
  `stuck_job`, `vital_nearing_threshold`, plan wakes) and admits the wake audit's
  "five reasons for one drink fact" pile-up is out of scope (4.1). Split into
  turns, the same fact gets addressed several times: more rounds and more
  near-duplicate filings, the churn the audit measured [I].
- **Fix.** For advisors, one item per lane key that names a distinct thing (alert,
  ore site, unsupplied building, noble room, ask, answer, ruling on own proposal);
  all keyless reasons merge into one "review" item. Keep the Planner one-shot: its
  wakes end in one plan write.

**M8. Tripwire mid-wake needs the rest of the cycle stopped, not only the sessions
(D17).** [V, I]

- After the role loop `_run_cycle` runs the execute phase with `latched=False`
  (`cycle.py` lines 1068 to 1073) [V]. A latch detected by the poller mid-wake must
  skip that phase; "run the tripwire cycle at once" must not nest inside
  `_run_cycle`.
- Waiting for in-flight turns "within their wait" can be several minutes (per-item
  cap is half the role budget). The fort is paused by the latch, so this is safe but
  slow.
- **Fix.** On a latch: stop starting items, kill in-flight non-owner turns (discard
  their dirs), skip execute, end the cycle early with the latch recorded, and let
  the next cycle take the existing tripwire branch, which runs first
  (`cycle.py` line 709).

**M9. The experiment is costly to stand up and probably inconclusive (D9 to
D12).** [V, I]

- Power, recomputed exactly (two-sided exact McNemar, alpha 0.05, pairs assumed
  independent and the two arms independent within a proposal, which is the most
  favourable case): for an indefensible rate of 20 percent against 5 percent,
  power is 0.52 at 50 pairs, 0.71 at 70, 0.84 at 90; for 15 against 5 it is 0.26,
  0.40, 0.53; for 10 against 5, 0.07 to 0.16. Rulings within one docket are
  correlated, so the effective sample is smaller still. The design's "about 15
  points at conventional power" holds only near 90 independent pairs.
- The base rate is unknown and may be low; if both arms are near 5 percent, the
  result is "inconclusive" and the D10 rule decides on cost, which production data
  measure without any harness.
- Cache order bias: the arm run second on a docket reads a warmer cache. Arm order
  is randomised, but cost comparisons should use token counts at fixed rates, not
  billed cost.
- Isolation: the design needs a new dfmcp "game writes refused" flag (S4 build). An
  experiment role whose allowlist has the reads and `queue.rule` but no game-write
  tools gives the same refusal with no new server code, since the allowlist is the
  boundary (`docs/AGENT-ARCHITECTURE.md` principle 8) [I that a role-only
  allowlist is enough for the second instance; check against `roles.py` rules].
- Live dockets rarely reach 3 proposals [V, design 8.2 and the wake audit], so most
  dockets must be manufactured by advisor runs.
- **Fix.** Keep the user's paired design but stage it: first run `all` in sessions
  (S4) and then `single` on live wakes, with cost, defer rate and the objective
  consistency errors (accepting both of an `overlaps` or `duplicate_of` pair)
  compared directly; run the paired harness only if those are close and the user
  still wants the quality question answered. If it runs: a pre-set stopping rule
  (for example, stop as inconclusive if after 8 dockets the discordant pairs are
  fewer than 6), analysis by docket (paired permutation on per-docket rates), and
  the role allowlist instead of a server flag.

### Minor

- **m1. Wall-time and cycle numbers.** Replace the brief's "5 to 10 minutes, 17 to
  22 per cycle" with the recorded figures (M4). [V]
- **m2. Per-wake sums of `first_write_round` and `orientation_reads` are
  meaningless.** Define them per wake (rounds before the wake's first write) and per
  item separately. `wake_metrics.transcript_metrics` computes them per transcript
  (lines 443 to 499) [V].
- **m3. Public summaries per item.** Per-item replies such as "ruled, waiting" would
  each become a public run summary (register 2026-10-05). Publish one summary per
  wake (`wake_close`) and keep item replies in the transcript tab. The awake strip
  should key on `wake_open`/`wake_close`, or it flickers between items. [I]
- **m4. Transcript read only at close loses everything on a crash.** On the local
  route the state dir has no writer between turns, so read the transcript per turn;
  this also avoids the WAL read-only trap the publisher hit (Working.md, 2026-10-02)
  if anything ever reads it while a Gateway holds it. [V for the trap, I for the
  rest]
- **m5. Rotation at 250k tokens (D14).** With at most 8 items it will rarely fire;
  stopping the wake and carrying the rest is simpler than rotation with
  re-briefing. Keep the ceiling, drop rotation in v1. [I]
- **m6. Bundled S1.** The FORT pause line and `own_filings.recent: 0` are decided,
  small and independent of sessions, and should ship alone. They landed while this
  was written (3e8aa9d, "filings block off, FORT PAUSED line in every briefing");
  S1 shrinks to the runs columns and the inbox.
- **m7. Rollback needs a restart and a separate inbox flag.** Policy is loaded once
  in `build_deps` (`service.py` line 84) [V], as the design notes. Rendering the
  inbox into one-shot briefings (S1) means `roles: oneshot` does not roll the inbox
  back; give it its own flag.
- **m8. Pause pushes include the conductor's own changes.** The conductor sets the
  speed, pauses on escalation, and the Overseer's verdict resumes; filter
  self-caused changes or say who caused them, or the push is noise. [I]
- **m9. Errored frames are dropped at replay** (`erroredAssistantResultPolicy:
  "drop"`, source report section 5) [S]: after a failed turn, later requests no
  longer match the cached sequence from that point. Cost only.
- **m10. Image pin (D15) is independent of sessions.** The tag-to-main drift affects
  one-shot runs too; do it now. [V, `runner.py` `DEFAULT_IMAGE` is `:latest`]
- **m11. The Consultant is rarely woken** (1 run plus 3 before the runs DB in the
  wake audit) [V]. As the first session role (D16) its live check may wait; plan to
  stage asks under the hold.

## 3. The questions asked

**(1) Gateway plus fresh state dir versus the simplest route.** Fresh per-wake state
dir: keep (it is needed on both routes and removes every restart-recovery and
stale-lock question by construction). Gateway: defer (M1). The simplest thing that
gives multi-item wakes is `agent --local --session-key agent:<role>:<wake_id>
--message-file <f> --json --timeout <s>`, one `docker run --rm` per message, against
a per-wake state dir built from a plugin-only template, with `skipBootstrap: true`
in the pinned config and the key from the environment.

**(2) Failure modes.** Start and stop races and orphans: M6. Partial filings and
double filing: M3. State dir copy cost: unmeasured [gap], made moot by mounting the
plugin dir read-only (M5). DeepSeek rate limits: unverified [gap]; with serial roles
the request rate does not change from today, so this is a parallel-only question.
Attribution by diff: wrong under parallelism, fixable now by author (M4). Duplicate
check atomicity: atomic within one dfmcp process (M4) [V]. Tripwire mid-wake: M8.

**(3) Cache and cost.** Appending items keeps the prefix byte-identical within a wake
[V for short sessions, multiturn turns 2 and 3 read about 31k cached], with the
caveats in m9 and the daily date line. Cost per wake should stay close to one-shot:
at the fitted rates (input $0.435/M, cache read $0.0036/M, output $0.87/M,
`research/2026-10-07-persistent-sessions.md` 3.3) replaying history from cache is
nearly free, and one-shot already carries the same growing context across its own
rounds. The real cost risk is per-item re-orientation (each item re-reading vitals)
and, in `single` mode, a fresh high-effort reasoning block per proposal (output is
52 percent of cost) [I]; a guess of 0 to 15 percent above today's $0.05 to $0.07,
which S3's metrics settle. One wake-time risk: a cache eviction mid-wake on a large
context, for example 250k at $0.435/M, is about $0.11 [I, arithmetic].

**(4) Parallel roles.** Safe enough with per-role dirs and the author attribution
fix; saves little on recorded cycles; adds DFHack contention and busy refusals (M4).

**(5) The experiment.** Underpowered for anything but a large gap (M9 numbers), and
the deciding numbers (cost, consistency errors) can be had from production. Worth
running only after those, and only if the user still wants the quality answer.

**(6) Observability.** Per-item runs rows are right (D13); fix the per-wake
aggregates (m2), public summaries and the awake strip (m3), and read transcripts per
turn (m4). Add `cycle_id` now; it is cheap and makes "which runs were one cycle"
exact rather than the 120 s sweep heuristic.

**(7) Migration and rollback.** Per-role flag is right; add an inbox flag (m7), note
the restart, and make the first stage the one-shot charter fix plus a re-baseline,
since every later comparison depends on it (B1).

## 4. The smallest version worth building first

1. **Now, independent of sessions:** deploy the landed charter fix (3aa4d18) and
   verify it from the retained prompt for all five roles; the FORT line and
   filings-off (3e8aa9d, landed); pin the image by digest; author-based proposal
   and ask attribution; `cycle_id` on runs rows. Then several one-shot cycles as
   the new baseline.
2. **S0, live, throwaway plus one real read-only role:** the checks in section 6.
3. **Sessions v1:** local route only, serial only, one role first. Item list derived
   in memory from lane pending keys, merged keyless reasons, open asks and
   `pending_brief`; one turn per item; outcomes as runs-row columns; lane keys
   cleared per key; failures advance the existing backoff; escalation checked
   per turn; pause changes prepended to the next item; on a hard stop, kill,
   discard the dir and re-brief; token ceiling stops the wake.
4. **Then** the Overseer in `all`, then `single` on live wakes with cost and
   consistency compared; the paired harness, Gateway, `steer` and parallel roles
   only on evidence.

If the user wants the true mid-run push now, D8 (pause state stamped on dfmcp tool
replies) is the only route that reaches a model mid-turn without unverified openclaw
features, and it serves one-shot runs today.

## 5. D1 to D17

| D | Verdict | Reason |
|---|---|---|
| D1 Transport | **Disagree** | Local route first; Gateway's gains are small and its abort is not used by the recovery path (M1). |
| D2 Reset by fresh dir | **Agree, amended** | Plugin dir mounted read-only, key from env, 0700, `skipBootstrap: true` (B1, M5). |
| D3 Concurrency | **Agree on serial; disagree on scheduling parallel** | Gate on co-wake data; do the attribution fix now anyway (M4). |
| D4 Done means | **Agree, amended** | Also read records written in the item's window (M3). |
| D5 Strikes | **Disagree** | Reuse the backoff records; no strike when the turn wrote a record (M2, M3). |
| D6 Timeouts | **Agree** | Shape is right; the Overseer's 1200 s must cover up to 8 single-mode turns, so watch it. The user's earlier preference is not in the register (confirmed by the design's search; I did not repeat it). |
| D7 No retry in the same wake | **Agree** | Matches the wake audit's repeated Architect timeouts. |
| D8 Tool-reply pause stamp | **Agree, recommend** | Only verified mid-turn channel; helps one-shot today. |
| D9 Two arms | **Agree** | `by_fact` lacks a reliable key. |
| D10 Inconclusive rule | **Agree, amended** | Add a pre-set stopping rule and docket-level analysis (M9). |
| D11 Judge | **Partly agree** | Blind Opus grading is fine; cap the user's review load and report grader-replicate agreement. |
| D12 Isolation | **Disagree on the server flag** | Use an experiment role allowlist without game-write tools (M9). |
| D13 Runs rows per item | **Agree, amended** | Per-wake aggregates defined properly; one public summary per wake (m2, m3). |
| D14 Ceiling with rotation | **Partly agree** | Keep the ceiling, stop and carry instead of rotating in v1 (m5). |
| D15 Image pin | **Agree** | Do it now, independent of sessions (m10). |
| D16 Consultant first | **Agree** | Lowest risk and goal-verifiable; stage asks, since it rarely wakes (m11). |
| D17 Tripwire mid-wake | **Agree in direction, amended** | Kill non-owner turns, skip execute, end the cycle, let the next cycle's tripwire branch run (M8). |

## 6. What S0 must verify before anything else

In order; nothing is built past step 1 until steps 1 to 4 pass.

1. **Charter delivery on one-shot is deployed and re-baselined** (B1): retained prompt
   shows each role's charter under the workspace path, not `/app ... [MISSING]`.
2. **Same role, both routes, captured requests diffed** (B1): `agent exec` (with
   the charter fix) versus `agent --local --session-key` with `skipBootstrap: true`. System message
   identical apart from the date and Runtime lines; no `AGENTS.md`, `BOOTSTRAP.md`,
   `IDENTITY.md` or `USER.md` template text; tool list byte-identical (sha).
3. **Envelope mapping** (B2): a real `agent --local --json` envelope from a turn that
   called an MCP tool; locate `toolSummary`, `costUsd`, `assistantTurns`, usage and
   status; the mapping function's test fixture is that envelope.
4. **MCP tools across turns:** a second turn on the same key calls a dfmcp read; the
   tool list fetched per process is byte-identical turn to turn; cacheRead on turn 2
   covers turn 1.
5. Inner timeout during an MCP tool call: session usable after, and whether a queue
   write in flight landed (M3).
6. Hard kill mid-turn: container gone after `docker kill`, no further dfmcp calls in
   the server log from that session, dir discarded.
7. Template: plugin dir mounted read-only works; key from env works with no auth
   SQLite copied; size and setup time recorded.
8. Image digest recorded.

Gateway token auth, `--network container:`, Gateway readiness and abort are S7
questions, not S0, under this red team's recommendation.

## 7. Not verified

- Whether `BOOTSTRAP.md` is actually seeded on a workspace that holds only `SOUL.md`
  (`workspaceProfileLooksConfigured` not traced); the `AGENTS.md`, `IDENTITY.md` and
  `USER.md` seeding is read from source, not run.
- That `meta.toolSummary` is present in the `agent --json` envelope (type read, not
  an emitted envelope).
- Whether the plugin directory works mounted read-only inside a fresh state dir.
- DeepSeek rate limiting under concurrent calls (no primary source read).
- How often two advisors co-wake per cycle (the runs DB is on the VM; not read).
- That a role-only allowlist is enough to make a second dfmcp instance write-safe
  for the experiment (`dfmcp/roles.py` rules not traced for that case).
- Everything here is against openclaw `v2026.9.4`; the installed image digest was
  not inspected.
- Power figures assume independent pairs; real dockets are clustered, so they are
  upper bounds.
