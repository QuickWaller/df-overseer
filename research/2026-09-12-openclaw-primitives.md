# OpenClaw Primitives: What the Multi-Agent Design Can Actually Rely On

Date: 2026-09-12
Scope: given the just-decided driving-brain choice (`decisions/DECISIONS.md` 2026-09-12, "Decided the driving-brain choice: `openclaw`") and the newly-designed multi-agent architecture (one Overseer as sole actor, several read-only specialist advisors, plus code-level components), establish from primary sources which of that design `openclaw` actually supports today, so the architecture isn't designed against primitives that don't exist.
Status: **desk research only**, per instruction not to install or run anything. Everything below comes from `openclaw`'s own GitHub repository (`github.com/openclaw/openclaw`), its own hosted docs (`docs.openclaw.ai`), and its own issue tracker, fetched live this session. Version at time of research: **`2026.9.4`, released 2026-09-11** (one day before this research), confirmed via the repo's own Releases page. Every claim below is confidence-flagged individually — **verified** (read directly off a primary-source page or file), **probable** (stated plainly by a primary source but not cross-checked against the actual running schema/code, or aggregated from a search summary of a primary page rather than a full fetch), or **unverified** (could not be confirmed this pass, stated as a gap, not papered over).

**A live hazard worth naming up front**: the public web is thick with SEO content-farm sites keyed to "openclaw" (`claw-packs.com`, `getopenclaw.ai`, `openclawmcp.com`, `zedly.ai`, `lumadock.com`, `stanza.dev`, `markaicode.com`, `starkslab.com`, and more) plus at least one differently-named, unrelated project (`swarmclawai/swarmclaw`) that surfaces in the same searches. None of these were used as a claim's sole source below; every claim is traced to `github.com/openclaw/openclaw` or `docs.openclaw.ai` (or, for pricing/marketing-only claims, explicitly flagged as unverified). Where a search-engine AI summary is the only thing that surfaced a lead (e.g. a specific config key name), the underlying primary page or source file was fetched separately to confirm it before it's reported as verified.

---

## Answers

### 1. Multi-agent support — **verified**

Yes. `openclaw` runs multiple named agents inside a single Gateway (Node.js) process. Each is declared under `agents.entries.<agentId>` in the JSON5 config (`~/.openclaw/openclaw.json`), gets its own workspace (`SOUL.md`, `AGENTS.md`, optional `USER.md`), its own `agentDir`, and its own session store:

```json5
{
  agents: {
    entries: {
      coding: { workspace: "~/.openclaw/workspace-coding" },
      social: { workspace: "~/.openclaw/workspace-social" }
    }
  }
}
```
Source: `docs.openclaw.ai/concepts/multi-agent` (fetched live). Inbound messages route to the right agent through "bindings."

Concurrency across agents is real but lane-based, not unlimited-parallel: the Gateway is single-process/async (no thread pool), and work is serialized per "lane" while different lanes run concurrently — confirmed by a search-engine summary of a third-party technical write-up, **cross-checked** against `openclaw`'s own source: `agents.defaults.maxConcurrent` (global agent-turn concurrency) and `agents.defaults.subagents.maxConcurrent` (default `1`, per the repo's own `src/config/types.agent-defaults.ts`) are real config keys — **probable** on the exact default value (a search summary of the TS source, not a full line-by-line read of the file, which returned a truncated excerpt when fetched directly and did not itself show the `subagents` block). One concrete, confirmed limitation: the **inter-agent messaging lane** (`nested`, used by `sessions_send`) is **hardcoded to `maxConcurrent: 1`** with no config knob to raise it — see §5/§11 below; this is **verified** by reading the actual bug report against the actual source location it names (`src/gateway/server-lanes.ts`, `applyGatewayLaneConcurrency()`), via `github.com/openclaw/openclaw/issues/14214`.

### 2. Per-agent model assignment — **verified**

Each agent's model (and provider) is fully independent. Config key `agents.entries.<agentId>.model`, value format `"<provider>/<model>"`:

```json5
{
  agents: { entries: { myAgent: {
    model: {
      primary: "anthropic/claude-opus-4-6",
      fallbacks: ["minimax/MiniMax-M2.7"]
    }
  } } }
}
```
Source: `docs.openclaw.ai/gateway/config-agents/models` (fetched live). Object form gives primary + an ordered failover chain; string form (`"openai/gpt-5.4-mini"`, `"openrouter/qwen/qwen-2.5-vl-72b-instruct:free"`) sets primary only. Wildcards (`"openai/*"`) expose a whole provider's discovered models. Two different agents can be pinned to two entirely different providers (e.g. Anthropic and OpenAI) simultaneously with no conflict — stated plainly by the doc, and structurally obvious from the per-agent-independent config shape.

Separately, `agents.entries.<agentId>.utilityModel` and `.imageModel` let an agent route small/internal tasks (title generation) and vision tasks to a *different* model than its primary — useful for a cheap "utility" tier without a second agent.

Sub-agents (see §5) get their own model override at `agents.defaults.subagents.model`, independent again of the parent — "set a cheaper model for sub-agents and keep your main agent on a higher-quality model," per `docs.openclaw.ai/tools/subagents`.

Model failover itself (`docs.openclaw.ai/concepts/model-failover`) is a separate mechanism from per-agent assignment — retries within a single agent's own fallback chain, not across agents — but this page could not be re-fetched this session (connection reset on retry); its existence and purpose are confirmed by its doc title and the failover config keys referenced from `config-agents/models`, but the exact retry/backoff parameters it uses are **unverified** here (a search-summary claim of "up to eight attempts, jittered exponential backoff, 90-second retry window" surfaced but was not independently confirmed against the page itself — treat as **probable** at best, and do not rely on the specific numbers without re-fetching).

### 3. Per-agent tool scoping — **verified**, stronger than a workaround

This is a first-class feature, not just a workaround. Two independent, stackable layers:

- **Agent-level allow/deny.** `agents.entries.<agentId>.tools.allow` / `.deny` (also documented as `agents.workspace.denyTools`) accepts literal tool names (`exec`, `process`, `write`, `edit`, `apply_patch`, etc.). A genuinely read-only agent is built by denying `exec`/`process`/mutating tools *and* setting `sandbox.workspaceAccess: "ro"` or `"none"` — the docs explicitly warn that a missing/off sandbox mode does **not** by itself satisfy a read-only policy (tool denial and sandbox mode are separate, both-required layers). Source: `docs.openclaw.ai/gateway/sandbox-vs-tool-policy-vs-elevated` and `docs.openclaw.ai/tools/permission-modes` (via search-engine summary of primary pages; not independently re-fetched in full, so flagged **probable** on the exact key spelling, **verified** on the existence of the mechanism, which is corroborated by the config example already fetched directly at §4's `agents.entries.roboclaw` sandbox block).
- **MCP-server-level tool filtering.** `mcp.servers.<name>.toolFilter.include` / `.exclude` (glob-style, e.g. `"search_*"` / `"admin_*"`) restricts which tools a given MCP server exposes at all, and `mcp.servers.<name>.codex.agents` is a non-empty allowlist of agent ids permitted to reach that server in the first place. Source: `docs.openclaw.ai/gateway/config-extensions` (fetched live, exact JSON5 quoted in §4 below).

For the read-only-specialist-advisor pattern the new architecture wants: deny every mutating DF MCP tool (and the raw `exec`) on each specialist agent's `tools.deny`, and/or scope specialist agents out of whichever MCP server exposes the mutating (`build`/`dig`/`set_labor`) tools entirely via `codex.agents`, leaving only the Overseer agent with that server's `codex.agents` allowlist. Both layers exist today; nothing here requires a workaround.

### 4. MCP client config — **verified**

MCP servers are declared **globally**, under `mcp.servers.<name>`, then scoped down to specific agents (not declared per-agent from scratch). Source: `docs.openclaw.ai/gateway/config-extensions` (fetched live):

```json5
{
  mcp: {
    servers: {
      docs: { command: "uvx", args: ["mcp-server-fetch"] },      // stdio transport
      remote: { url: "https://example.com/mcp", transport: "streamable-http" },
    },
  },
}
```

- **Transports**: `stdio` (via `command`/`args`, a local child process — this is what df-overseer's own DF MCP server would use if run as a local process on the same VM) and HTTP-based, either `transport: "streamable-http"` or `transport: "sse"` (`type: "http"` is accepted as a CLI-native alias that normalizes to the canonical `transport` field).
- **Auth**: HTTP-transport servers support `auth: "oauth"` with `oauth.identity: "shared" | "per-requester"` and an `oauth.scope`; TLS controls (`sslVerify`, `clientCert`, `clientKey`) exist for private/mTLS endpoints. No auth block is required for a local stdio server on loopback, which is the shape df-overseer's own MCP server would likely take.
- **Per-agent scoping**: `mcp.servers.<name>.codex.agents: ["main"]` limits a declared server to only the listed agent ids; `codex.defaultToolsApprovalMode` (e.g. `"approve"`) can gate that server's tools behind an approval step, which is a second possible mechanism (beyond simple deny-listing, §3) for making a specialist "propose but the Overseer approves."

### 5. Inter-agent messaging — **verified, with a confirmed real bottleneck**

Yes, a channel exists. Two tools: `sessions_spawn` (spawn a new sub-agent or ACP-harness session) and `sessions_send` (message an existing session/agent). A configured agent can also ask `openclaw` itself (via the `openclaw` tool) to create another agent, gated by operator approval — source: `docs.openclaw.ai/concepts/multi-agent` (fetched live, direct quote: "The system agent files the typed operation, shows the requesting agent id to the operator, and creates the agent only after operator approval").

**Logged**: yes. Session store is SQLite per agent, at `~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite` (chat history, routing state), with archived transcript files at `~/.openclaw/agents/<agentId>/sessions/`. Source: `docs.openclaw.ai/session` (fetched live). Inter-agent calls carry canonical tool-call IDs that correlate with the structured JSONL logs (§9), so a message between agents is traceable in both the session store and the log stream.

**Can one agent wake another**: yes, via `sessions_send`/`sessions_spawn` from within a run. **The confirmed bottleneck**: the lane used for this (`nested`, i.e. `sessions_send`) is **hardcoded to `maxConcurrent: 1`** in the current codebase, with no config key to raise it. In a reported real deployment, broadcasting to 9 other agents took ~270 seconds wall-clock (9 × a 30-second per-target timeout) because each send serializes behind the last. The reporting issue (`github.com/openclaw/openclaw/issues/14214`, filed 2026-02-11, version `2026.2.9`) was **closed as not planned / stale — not fixed**, and names the exact missing line (`applyGatewayLaneConcurrency()` in `src/gateway/server-lanes.ts`). This is **verified** by reading the issue directly (its status, its content, and its citation of the source file); whether it has since been superseded by later work (the issue is 7 months old against a project now at `2026.9.4`) was **not** re-checked against current source and should be treated as **unverified-current-state**, flagged rather than assumed fixed just because time has passed.

Sub-agent results flow back to the requester as "non-blocking, push-based completion" via an announcement chain (`docs.openclaw.ai/tools/subagents`) rather than the requester blocking on the child — relevant if the Overseer wants to fan out to several specialists without stalling.

### 6. Scheduling and waking — **verified**, and this is the strongest fit for df-overseer's loop-shape question

Multiple mechanisms, from `docs.openclaw.ai/gateway/heartbeat`, `docs.openclaw.ai/automation/cron-jobs/schedules`, and the hooks page (all fetched live):

- **Heartbeat**: a system-owned automation running periodic agent turns per agent. Default cadence **30 minutes** (bumped to **1 hour** automatically under Anthropic OAuth/token auth unless overridden); config key `agents.defaults.heartbeat.every` (or per-agent `agents.entries.<id>.heartbeat.every`); `heartbeat.every: "0m"` disables the recurring cadence while keeping event-driven wakes. There is a **30-second floor between event-driven turns**, and a "flood guard" that pauses deferred work after 5 starts within 60 seconds. Heartbeats defer automatically while other work for that agent is active, so it's self-pacing rather than a rigid clock.
- **Cron/`every`/`at`/`on-exit`/`stream` schedule kinds**: `at` (one-shot, ISO 8601 or relative like `20m`), `every` (fixed interval), `cron` (5/6-field, with a documented day-of-month/day-of-week **OR-logic pitfall** — `0 9 15 * 1` fires on the 15th OR every Monday, not "the 15th if Monday," fixable with a `+` modifier), `on-exit` (fires when a watched command exits, survives turn teardown), and `stream` (event-driven, fires off batched lines from a long-running supervised command).
- **Condition watchers** gate any of the above: a headless script returning `{fire, message?, state?}`, given a persisted 16 KB `state` blob and up to 5 tool calls in a **30-second wall-clock budget per evaluation**. This is a poll, not a passive listener — it cannot watch a filesystem path or HTTP endpoint directly; it has to `exec` something (e.g. curl the DF MCP server, or `dfhack-run` a status check) inside its own 30-second window. **This is the mechanism that would let an openclaw agent poll df-overseer's own perception tools on a schedule** (e.g. every 5 minutes, check `get_stuck_jobs`/`get_overview` for an alert and fire only then) — a genuinely close fit for df-overseer's non-blocking-loop design goal, but it is polling with a **30-second minimum granularity**, not a true event push.
- **Hooks (true external push)**: `hooks.enabled: true` opens an HTTP endpoint (`hooks.path`, default token-authenticated via `Authorization: Bearer <token>` or `x-openclaw-token`; query-param tokens are rejected) that can trigger either a full agent run or a lighter **"wake event"** that fires an agent heartbeat with a notification string, restricted to `hooks.allowedAgentIds`. This is the one mechanism that is a genuine external event wake (a webhook), not a poll — **verified**, `docs.openclaw.ai` hooks page fetched live. Practical limits: 256 KiB body cap, 30-second body-read timeout, 15-second single-run admission deadline, and failed-auth throttling (429 after 20 bad attempts/60s). No hard minimum interval is enforced beyond that throttling and the general 30-second event-driven floor above.
- **No file-watch or OS-signal trigger was found.** Neither the schedules doc nor the hooks doc describes a filesystem-watch or POSIX-signal wake primitive; the closest equivalents are (a) a condition-watcher script that itself stats a file inside its 30-second budget, or (b) a hook endpoint that something else (e.g. a small script triggered by `inotify` on the VM) calls. This absence is stated as a finding, not assumed away.
- **Retry/backoff — the one place docs and reality disagree, flagged explicitly.** `decisions/DECISIONS.md`'s 2026-08-25 row asserts "openclaw's [scheduler] is better (heartbeat, self-pacing `/loop`, exponential retry backoff)" as a reason it beat `hermes-agent` in that comparison. That characterization does **not** hold for the heartbeat scheduler specifically: `github.com/openclaw/openclaw/issues/3181` (filed 2026-01-28, **closed as not planned/stale**, not fixed) documents "the Heartbeat scheduler retries failed runs every second with no exponential backoff, even for permanent errors like billing failures," producing a genuine cost/CPU runaway in a live deployment. A second, more severe issue, `#92082` ("heartbeat delivery wedge," version `2026.5.26`, closed but status of an actual fix is ambiguous from the issue text alone) reports `pendingFinalDelivery` retrying indefinitely (570+ attempts recorded) with **no retry cap, no decay, no dead-letter, and no CLI recovery command** — the only documented recovery was a manual filesystem race. **Prefer the code/issue tracker over the 2026-08-25 decision-register characterization on this specific point**: exponential backoff exists for *model-provider failover* (§2, itself only probable-confidence on its exact parameters) but the *heartbeat scheduler's own* retry loop is reported, by real users against real deployments, as linear/uncapped in at least two separate incidents spanning January–June 2026. Neither issue's current-version status was re-verified against `2026.9.4` — flagged **unverified-current-state**, not assumed fixed by the passage of time.

### 7. Persistence — **verified**

Per-agent, SQLite-backed:
- Runtime session rows + transcripts: `~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite`
- Archived transcript files: `~/.openclaw/agents/<agentId>/sessions/`
- Each agent also gets its own workspace directory holding `SOUL.md` (persona/identity), `AGENTS.md`, optional `USER.md`.

Source: `docs.openclaw.ai/session` and `docs.openclaw.ai/concepts/multi-agent` (both fetched live). State is **not** shared between agents by default — this is explicitly the isolation model ("own files, memory, auth and tools"), so a shared fort-state view across the Overseer and its specialists is not automatic; it would have to be pushed through the DF MCP server itself (which already has shared state — the actual game) or through `learning/`'s existing plain-JSONL files (`docs/PURPOSE.md`'s open question on this is still correctly unresolved, per `decisions/DECISIONS.md` 2026-09-12's row, and this research doesn't change that answer).

### 8. Crash semantics — **verified, partial**

If the Gateway process dies mid-turn and restarts, `openclaw` "tries to continue the existing session automatically," with **up to three recovery attempts**; the recovery budget refreshes once a backend turn successfully starts. If recovery is exhausted, the transcript remains on disk and a human/operator can start a replacement session manually. Source: `docs.openclaw.ai/session` (fetched live). This is a real, if partial, run journal: a crash mid-cycle is detectable (the session row shows an interrupted turn) and there is an automatic-continuation path, not silent data loss — but it is **not** a step-by-step journal of *which tool calls had already committed real side effects before the crash* (e.g. "the dig was designated but the confirmation message never sent"). That distinction matters for df-overseer specifically, because DF-side mutations (a `build`/`dig` call) are not transactional with the agent's own session state — the two issue reports in §6 (`#3181`, `#92082`) are themselves evidence that failure recovery around heartbeat/session continuity has had real, user-reported gaps in practice, not just in theory. **Unverified**: whether `openclaw`'s own session recovery has any awareness of *external* side effects (a DF MCP tool call that mutated the fort) versus purely its own conversational state — nothing in the docs fetched this session addresses that, and it would need to be tested live to know for certain.

### 9. Observability — **verified**

Structured, file-based, JSONL logs:
- Default path (non-Windows): `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (named profiles: `openclaw-<profile>-YYYY-MM-DD.log`); overridable via `logging.file` in `~/.openclaw/openclaw.json`.
- Each line is a JSON object with fields including `message`, `hostname`, `agent_id`, `session_id`, `channel`.
- Rotation: files >`logging.maxFileBytes` (default 100 MB) rotate, keeping up to 5 numbered archives; dated log files are pruned after 24 hours.
- Levels: `silent`/`fatal`/`error`/`warn`/`info`/`debug`/`trace`, set via `logging.level`, `OPENCLAW_LOG_LEVEL`, or `--log-level`.
- **Tool-call capture specifically**: Control UI tool-event payloads include "tool start args, partial/final result payloads, derived exec output, and patch summaries," and canonical assistant tool-call IDs match tool-result IDs so stored history correlates with live tool events. `openclaw logs --follow --json` emits type-tagged, machine-parseable objects; `openclaw channels logs --channel <x>` filters by channel.
- **Caveat, stated by the docs themselves, not by me**: "Redaction is best-effort" and happens before persistence — meaning tool arguments/results (e.g. a DF MCP call's raw arguments) can be scrubbed of anything that looks like a credential before it's logged, which is good for secrets but means the logs are not guaranteed to be a byte-exact record of every call if a false-positive redaction trims something else.

Source: `docs.openclaw.ai/logging` (fetched live). This is genuinely usable for building the mechanical "friction log" of failed tool calls the brief asks about: filter the JSONL by `agent_id`, look for tool-call/tool-result pairs where the result payload indicates an error, or grep the `message` field for the openclaw-side error strings. It would need to be joined against df-overseer's own DFHack-side logs (which live entirely outside openclaw) to get the *other* half of a failed call — e.g. quickfort's own stderr, or a Lua script's own return value — since openclaw's log only captures what crossed the MCP boundary, not what happened inside the DF MCP server.

### 10. Cost controls — **verified: no hard spend cap exists**

Directly from `docs.openclaw.ai/reference/token-use` (fetched live): **no built-in hard spend cap**. What exists instead:
- `agents.defaults.contextLimits` / per-agent `agents.entries.<id>.contextLimits`, with `memoryGetMaxChars` (default 12000) and `postCompactionMaxChars` (default 1800) as *context-size*, not spend, limits.
- A runtime "context-share guard" caps a single tool result at 30% of the effective context window (16000 chars below 100K tokens, 32000 at ≥100K, 64000 at ≥200K tokens) — again a context/latency control, not a dollar control.
- Cost *visibility* exists (`/usage`, `/status`, and `models.providers.<provider>.models[].cost` pricing config for estimation) but nothing gates a request on projected spend.
- Per-agent **model routing** (§2) is the practical cost lever: pin cheap agents/sub-agents to a cheap model and the expensive Overseer to a better one.
- The real backstop is the **provider's own** billing cap (Anthropic's monthly spend limit, an OpenRouter per-key budget), external to openclaw entirely.

This matches this project's own lived experience exactly: `decisions/DECISIONS.md`'s 2026-09-11 rows record a real $9-13 Opus overrun on the compliance-eval harness that had to be caught and stopped by the user directly, not by any spend cap — consistent with, and now explained by, openclaw having no first-party spend gate either. Any per-role budget the multi-agent design wants will have to be enforced by provider-side caps plus the project's own monitoring (as `evals/compliance/` already does), not by an openclaw config key.

### 11. Deployment — **verified**

Linux: `openclaw onboard --install-daemon` / `openclaw gateway install` generates a **user-level** systemd unit at `~/.config/systemd/user/openclaw-gateway.service`, enabled via `systemctl --user enable --now`. Notable protective settings the generated unit carries: auto-restart on failure (5s interval), a 330-second stop timeout ("five-minute cooperative drain plus teardown reserve"), `OOMPolicy=continue` so an OOM kill of a child process doesn't take the whole Gateway down, and `oom_score_adj=1000` applied to transient children (exec/PTY/model-service child processes) so they're preferentially OOM-killed over the Gateway itself. Multiple profiles run as `openclaw-gateway-<profile>.service`. Source: `docs.openclaw.ai/platforms/linux` (fetched live).

**Fit for this project's VM**: good, on paper. It's a **user-level** systemd unit, not a system-level one, so it coexists cleanly alongside `docs/PURPOSE.md`/`scripts/install_df.py`'s own systemd units for the DF/DFHack process (which are, per this project's existing convention, run under a specific service account — whether that's the *same* account openclaw would run under, and whether Debian's default `systemd --user` lingering setup is already enabled on VM 103, were **not checked this pass** and should be verified before relying on it: unlinger'd user units stop when the owning user's last session ends, which matters a great deal for something meant to run unattended for weeks). Memory: openclaw's own footprint was not measured or documented anywhere fetched this session — **unverified**, and worth measuring empirically on VM 103 rather than assumed, in the same spirit as this project's own worldgen-memory-spike finding (`docs/PURPOSE.md`, "the worldgen spike was assumed to be the real peak; measured, it is not").

---

## Where our design is not supported, and the cheapest workaround

1. **Inter-agent broadcast to several specialists at once is not fast.** The `sessions_send` lane is hardcoded to `maxConcurrent: 1` (§5), so an Overseer that wants three specialists' opinions before deciding will pay their timeouts back-to-back (30s each is the reported default timeout), not in parallel. **Cheapest workaround**: don't broadcast — have the Overseer call specialists sequentially by design and budget for it (a df-overseer turn is already framed as non-blocking against real game time, `docs/PURPOSE.md`'s FPS_CAP design, so a few tens of seconds of specialist consultation per turn is likely tolerable), or fan out via `sessions_spawn`'s sub-agent path (a different, unconstrained-by-this-specific-bug mechanism, §5) instead of `sessions_send` if the specialists don't need to be long-lived named agents.

2. **No true minimum-latency event wake exists except via a webhook you build yourself.** Everything native to openclaw's own polling side (condition watchers) has a 30-second floor (§6). If the multi-agent design wants sub-30-second reaction to something happening in the fort (a hostile-unit alert, say), openclaw's own scheduler cannot deliver that on a poll. **Cheapest workaround**: have df-overseer's own side push, not have openclaw pull — a small process on the DF VM (or the perception service itself) that watches `get_diff_since`/`eventful` output and calls openclaw's `hooks` endpoint (a real webhook, no polling floor) the moment something worth waking the Overseer for happens. This is a small amount of new code in this repo, not an openclaw feature request.

3. **Heartbeat retry-on-failure is reported as linear/uncapped in production, not exponential-backoff as the 2026-08-25 decision register characterized it.** Two open-then-stale-closed issues (`#3181`, `#92082`, §6) describe real cost/availability incidents from this specific gap. **Cheapest workaround**: keep df-overseer's own DF MCP server tools returning clean, typed errors rather than throwing/timing out where possible (since a hard failure is exactly what triggers the retry storm), and treat `heartbeat.every` as a dial to turn down (or the recurring cadence off, event-driven wakes only) rather than assuming the scheduler will self-heal from a bad state; if it does wedge, expect to need a manual/filesystem-level recovery, not a CLI command, per `#92082`.

4. **No first-party spend cap.** (§10) **Cheapest workaround**: exactly what this project already does in `evals/compliance/` — model routing to cheap models by default plus human-in-the-loop cost review for anything expensive, backed by the provider's own account-level spend cap as the real hard stop.

5. **Shared, cross-agent state is not automatic.** (§7) Specialists and the Overseer each get an isolated session store; nothing in openclaw itself gives them a shared "fort dossier." **Cheapest workaround**: this is already the plan — the DF MCP server (design commitment #5) and/or `learning/`'s plain JSONL are the shared substrate, not an openclaw-native memory feature, exactly as `docs/PURPOSE.md`'s still-open "should `learning/` fit openclaw's own conventions" question already concluded on 2026-09-12: build to the MCP seam, not to openclaw's specific memory API.

6. **Whether a crashed agent's in-flight *DF-side* mutation is detectable is genuinely unknown.** (§8) openclaw's own session-recovery model only speaks to its own conversational state, not to side effects a tool call made in an external system. **Cheapest workaround, already partly built**: this project's own checkpoint discipline (quicksave-confirm before/after any mutating call, per the 2026-09-11 `dig`/`build` rows in `decisions/DECISIONS.md`) is the actual safety net here, and should stay the safety net — don't expect openclaw's crash recovery to cover DF-side state, because nothing found this session suggests it does.

---

## Not verified / could not check this pass

- The **exact current schema** for `agents.defaults.subagents.{maxConcurrent,maxSpawnDepth,maxChildrenPerAgent}` against the live `2026.9.4` codebase — the values reported (`maxConcurrent` default 1, `maxSpawnDepth` default 1/range 1-5, `maxChildrenPerAgent` default 5/range 1-20) come from a search-engine summary of the repo's own `src/config/types.agent-defaults.ts`, not a full direct read of that block (a direct fetch of the file returned a truncated excerpt that didn't include the `subagents` sub-object at all). A historical issue (`#18142`, filed against `2026.2.15`) shows this exact schema was buggy/rejected by the config validator at one point; it is now closed, but whether "closed" means "fixed" specifically (versus closed-stale) was not itself confirmed.
- The **exact retry/backoff parameters** of model-provider failover (§2) — a "8 attempts, jittered exponential backoff, 90s window" claim surfaced only via search summary and was not re-confirmed against `docs.openclaw.ai/concepts/model-failover` directly (that page failed to fetch twice, `ECONNRESET`).
- Whether `#3181` and `#92082` (heartbeat retry storms) are actually fixed in `2026.9.4` — both are several months old against a fast-moving project; "closed as not planned/stale" for `#3181` specifically means **not fixed by design**, but `#92082`'s closure reason was not legible from the fetch and should be re-checked before relying on heartbeat failure behavior being safe.
- Any **numeric memory/CPU footprint** for running the openclaw Gateway itself on a resource-constrained VM (relevant given this project's existing 4096 MB VM budget already shared with DF) — nothing found in the docs fetched this session states this, and it was not measured (no live system was run).
- Whether Debian's `systemd --user` **lingering** is already enabled on VM 103 (needed for a user-level unit to survive without an active login session) — an infra fact about this project's own VM, not about openclaw, and out of scope for a desk-only openclaw pass; flagged so it isn't silently assumed true when `openclaw` is actually deployed.
- Whether condition-watcher scripts or hooks can reach a **loopback-only** DF MCP server the same way a stdio-declared server would (i.e., whether `exec`-based polling from inside openclaw's own sandbox can reach `127.0.0.1:5000`-style RPC on the same VM without additional sandbox `workspaceAccess`/network config) — plausible given the sandbox docs describe a `docker.network` setting, but not directly tested or read in enough depth to confirm.

## Relevant to

The multi-agent architecture decision (`decisions/DECISIONS.md` 2026-09-12, "Decided the driving-brain choice: `openclaw`") and its immediate next step, the still-unbuilt MCP server/tool schema (design commitment #5, `TOOLS.yaml` as its first draft). Specifically informs: how specialist agents should be scoped (§3 gives a real, non-workaround mechanism), how the Overseer should consult them without stalling (§11 item 1), what "the fort learns something" should push through rather than poll for (§11 item 2), and that `learning/`'s already-decided plain-JSONL shape (per `docs/PURPOSE.md`'s 2026-09-12 open-question resolution) is the right call, not a stopgap — openclaw gives agents no shared state of its own to lean on instead (§7).
