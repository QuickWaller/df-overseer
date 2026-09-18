# OpenClaw capability inventory for the multi-agent host decision

Date: 2026-09-18. Read-only research pass, not a tutorial. Synthesizes three
prior research briefs (`research/2026-09-12-openclaw-primitives.md`,
`research/2026-09-14-openclaw-mcp-wiring.md`,
`research/2026-09-15-openclaw-secret-storage.md`), six prior handoffs, two
`docs/AGENT-ARCHITECTURE.md` sections, `docs/TRAPS.md`, and this session's own
fresh, read-only checks against VM 106 (SSH, `docker run --rm --entrypoint
node ... openclaw.mjs --help`/`config schema`/`hooks list`, `docker ps -a`,
`docker images`, `ss -tlnp`). **No agent run, no gateway start, no config
mutation, no model call was made this session.** Every command that touched
the live host is quoted below or was already run and reported by a prior
session; this pass adds only inspection commands (`--help`, `--version`,
`config get`/`config schema`/`secrets audit` against a read-only mount,
`ps`/`ss`/`images`).

Version confirmed unchanged since 2026-09-14: **OpenClaw 2026.9.4 (`3a9d69d`)**.
Confirmed live this session: `docker run --rm --entrypoint node
ghcr.io/openclaw/openclaw:latest openclaw.mjs --version`.

Live state on VM 106, confirmed this session, matches every prior report with
no drift: `docker ps -a` empty, one image present (`ghcr.io/openclaw/openclaw:
latest`, 4.58GB), no `openclaw`-named systemd unit (user or system), no port
listening beyond baseline (sshd, the loopback DNS stub resolver, and a
loopback `containerd` socket at `127.0.0.1:39389`, traced to `containerd`
PID 744, the same baseline every prior stream recorded, not a new service).
`/opt/openclaw/config`, `/opt/openclaw/secrets`, `/opt/openclaw/architect-
workspace` exist as before.

**One new, small finding this session**: `config get`/`secrets audit` against
a **read-only** bind mount of `/opt/openclaw/config` now fail with `unable to
open database file`, where the identical read-only-mount pattern worked for
the 2026-09-15 secret-storage research. `config file` (which only reports a
path, never opens `state/openclaw.sqlite`) still succeeds read-only. Plausible
cause, not confirmed: SQLite in WAL mode needs at least an attempted lock/
journal-file open even for a read, and the container's mount became strictly
read-only at the OS layer rather than only at Docker's abstraction, or the
database has a pending WAL checkpoint since the 2026-09-16 ruling run. Not
chased further, doing so would need a non-read-only mount, which risks an
unintended write and was out of scope for an inspection pass. **Flagged as an
open operational quirk**: don't assume a read-only audit will always work
against ambient state; it may need `--rm`'s ordinary (writable) bind instead,
which is itself then a small write-capability requirement worth knowing about
before scripting a "safe, read-only health check."

---

## 1. Capability table

| Feature | Supported? | How verified | Source |
|---|---|---|---|
| Multiple named agents in one config | **Yes** | Live: `agents.entries.architect`/`.overseer` both configured and both ran real `agent exec` calls against the fort (2026-09-15/16 runs) | `docs.openclaw.ai/concepts/multi-agent` (fetched live 09-12); live runs 09-15/16 |
| Agent-to-agent call/handoff within openclaw | **Primitive exists (`sessions_send`/`sessions_spawn`), never used in practice, and has a confirmed bottleneck** | Doc-confirmed primitive; the one hard number (lane hardcoded `maxConcurrent: 1`) verified by reading the actual open GitHub issue and the source file it names | `docs.openclaw.ai/concepts/multi-agent`; `github.com/openclaw/openclaw` issue `#14214` (2026-02-11, closed not-planned/stale, current-version status not re-checked) |
| Gateway/daemon/server mode | **Exists, never run in this project** | `openclaw gateway --help` (fetched live this session): `run`/`install`/`start`/`stop`/`status`/`probe`/`health`/`usage-cost` all present | This session, live `--help` |
| Cron/scheduler/webhook trigger | **Yes, three real mechanisms, all gated by a live Gateway** | Doc-confirmed: heartbeat (default 30 min), `at`/`every`/`cron`/`on-exit`/`stream` schedules, condition watchers (30s poll floor), and a real webhook (`hooks.enabled`, HTTP-triggered, the one true push) | `docs.openclaw.ai/gateway/heartbeat`, `.../automation/cron-jobs/schedules` (fetched live 09-12) |
| Several agents in one process/container | **Yes, by config; concurrency is lane-based, not free** | `agents.defaults.maxConcurrent`, `agents.defaults.subagents.maxConcurrent` (default 1) are real schema keys | `research/2026-09-12-openclaw-primitives.md` §1 (probable on the exact default, verified on the keys existing) |
| Parallel runs, isolation between them | **Each `agent exec` is a fully separate, throwaway container in this project's actual usage** | Every real run so far used `docker run --rm`, never `docker compose up`, never a shared container | Every handoff 2026-09-14 through 2026-09-16 |
| Persistence between runs | **Per-agent SQLite**, not shared across agents | `~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite` + session transcript files; separate `state/openclaw.sqlite` for runtime auth/config state | Doc-confirmed 09-12; live-observed file paths 09-14/09-15 |
| `agent exec --json` schema/contract | **A named "stable agent-exec JSON envelope," real fields observed live: `toolSummary`, `usage` (input/output/cache-read/reasoning/total tokens), `costUsd`, `assistantTurns`** | Confirmed by `agent exec --help`'s own text ("Emit the stable agent-exec JSON envelope") plus five real `run.json` artifacts in `evals/live/` | This session's `--help`; `evals/live/2026-09-14-*`, `evals/live/2026-09-15-*` |
| Max-turns / timeout | **Yes**: `--timeout <seconds>` (agent exec deadline, default 600s per `--help`); the parent `agent` command separately has `--timeout` (default 600 or config value) | Live `--help` this session | This session |
| Distinguishing refusal vs tool error vs limit-hit vs host crash | **Partial.** A tool error surfaces as `isError: true` inside a normal 200-status JSON-RPC response (confirmed live: 3 of 14 calls in one real run). A local pre-network failure (`Unknown model`) is a distinct `$0`, ~130ms local failure with no `provider-transport-fetch` log line, so "never reached the model" is distinguishable from "reached it and failed" by grepping for that log line. **No distinct, structured code for "the model itself refused"** was found in the JSON envelope or in the schema; it would show up as ordinary assistant text, not a typed field. Host crash/recovery is a doc-only claim (up to 3 automatic recovery attempts on restart), never tested live | Live runs 09-14 (isError), TRAPS.md (`isError` field-name gotcha), `research/2026-09-12-openclaw-primitives.md` §8 (crash semantics, doc-only) |
| Hard spend cap / rate limit | **No.** Confirmed directly from the docs' own token-use page and independently by this project's own $9-13 Opus overrun elsewhere | `docs.openclaw.ai/reference/token-use` (fetched live 09-12) |
| Cost observability | **Per-run**: `costUsd` and a full token breakdown in every `agent exec --json` result. **Aggregate**: a real `openclaw gateway usage-cost` command exists (`--agent`, `--all-agents`, `--days`) but needs a **running Gateway** to answer (it takes `--url`/`--port`/`--token`/`--password`, gateway-RPC-shaped flags), not usable in this project's gateway-free `agent exec` pattern without standing one up | This session's live `--help`; per-run costs from every real run to date |
| Per-agent model | **Yes**, `agents.entries.<id>.model`, string or `{primary, fallbacks}` object, fully independent per agent, live-used (architect and overseer both ran `deepseek/deepseek-v4-flash`; overseer's config also lists `deepseek-v4-pro` as available) | Doc-confirmed 09-12; live config 09-15/16 |
| Per-agent tool allowlist | **Yes, real feature, glob-confirmed live**: `agents.entries.<id>.tools.allow/deny`, matched against `<safeServerName>__<toolName>` identities; `"df-overseer__*"` demonstrably matched as a glob against 9 distinct real tool names in one live run | Schema + live run 09-15 (`evals/live/2026-09-15-architect-third-charter/`) |
| Charter/prompt injection | **Yes, via workspace bootstrap files (`SOUL.md`/`AGENTS.md`/`USER.md`), not a CLI flag.** `agent exec --help` has no `--instructions`/`--system-prompt` flag; the real mechanism is `agents.entries.<id>.workspace` pointing at a directory holding `SOUL.md` | Live-confirmed 09-14: `config get agents.entries.main --json` echoed the configured workspace before the run |
| MCP servers per agent | **Yes**, `mcp.servers.<name>` declared globally, scoped to agents by which `agents.entries.<id>.tools.allow` names match that server's tool prefix. (`mcp.servers.<name>.codex.agents` looks like a more direct per-server allowlist but is Codex-app-server-only per the schema's own description, confirmed twice from independent primary sources, do not use it for general scoping) | `docs.openclaw.ai/gateway/config-extensions`; schema `description` string, confirmed independently in two separate research passes |
| System-prompt layering / caching | **Layering: yes** (bootstrap files stack: `IDENTITY.md`/`USER.md`/`SOUL.md`, `bootstrapContextFiles` schema enum seen live). **Prompt caching: not separately investigated this pass**, though live `usage` blocks already show real `cache-read` token counts (20864-73088 tokens per run), so caching is evidently active by default at the provider-call level, not something this project has to configure | This session's schema read (`bootstrapContextFiles` enum); prior runs' own `usage` blocks |
| Real secrets options for credentials | **Two independently working mechanisms today, no fully clean end-to-end path yet**: (1) `mcp.servers.<name>.headers.<key>` accepts `${ENV_VAR}` string substitution, **works with zero plaintext residue**, live-proven for the MCP role tokens. (2) `models.providers.<id>.apiKey` accepts a schema-valid SecretRef (`{source: env\|file\|exec\|store, ...}`), **schema-confirmed, config-settable, and live-observed to resolve** (`secrets audit`: `unresolvedRefCount: 0`), but a pre-existing plaintext `auth.profiles.<id>` entry **unconditionally shadows it at call time** (`REF_SHADOWED`, the audit tool's own diagnostic code) | `research/2026-09-15-openclaw-secret-storage.md`; `docs/TRAPS.md` "Added 2026-09-15/16" section |
| Hooks/middleware around tool calls | **No tool-call-level hook exists.** openclaw's own `hooks` subsystem is real (`hooks list --json`, confirmed live this session) but every bundled hook fires on a **session/command/gateway-lifecycle** event (`gateway:startup`, `agent:bootstrap`, `command`, `session:compact:before/after`, `command:new`, `command:reset`, `session:auto-reset`), a fresh grep of the full 55,932-line schema this session for `tool*` and event-name patterns found no `tool:before`/`tool:after`-shaped event or any pre/post-tool-call interception point | This session: `hooks list --json` (live), `config schema` grepped for tool-call event names (none found) |
| Version stability / upgrade risk | **Pinned to `latest` in every deploy so far; the schema has already changed at least twice mid-project** (the `_note` key was accepted then rejected between two runs in the same week; `agents.ownership: "explicit"` and `agents.defaults.systemAgent.agentId` were both undocumented requirements discovered only by hitting them) | `docs/TRAPS.md` "Added 2026-09-15/16" section |

---

## 2. What our design currently assumes that openclaw cannot cleanly do, and the workaround

1. **Fast fan-out to several specialists at once.** The `sessions_send`
   inter-agent lane is hardcoded to `maxConcurrent: 1` (GitHub issue
   `#14214`, filed 2026-02-11, closed not-planned/stale, this project has
   not re-verified whether `2026.9.4` still has this exact limitation, so
   treat it as **probable-current**, not certain). Waking three specialists
   would serialize at roughly 30s/target (the reported default timeout).
   **Workaround already adopted by this project**: don't use openclaw's
   native inter-agent send at all. Every real multi-agent interaction to
   date (architect proposes, overseer rules) has gone through `dfqueue` as
   two independent one-shot `agent exec` invocations, not through
   `sessions_send`/`sessions_spawn`. This sidesteps the bottleneck entirely
   because there is no openclaw-native call in the path.

2. **Sub-30-second event-driven reaction from openclaw's own scheduler.**
   Condition watchers have a 30-second poll floor; only a hooks-endpoint
   webhook is true push, and that needs a running Gateway. **Workaround**:
   have the fort side push (a small process on VM 103 watching
   `get_diff_since`/DFHack events) rather than have openclaw poll, this
   is new code in this repo, not an openclaw feature. Not built yet.

3. **A hard spend cap.** None exists in openclaw. **Workaround**: provider-
   side billing caps (Anthropic/DeepSeek account limits) plus this
   project's own per-role `model.yaml` conventions and human review, the
   same pattern already forced by the $9-13 Opus overrun this project has
   already lived through elsewhere. Aggregate cost visibility
   (`gateway usage-cost`) additionally requires a running Gateway, which
   this project has never stood up, so today, cost tracking is entirely
   per-run (`costUsd` from each `agent exec --json`), collected by hand
   into `evals/live/*/README.md`, not aggregated by openclaw itself.

4. **A single, uniform mechanism for keeping every model-provider key out of
   plaintext.** The MCP role tokens (architect, overseer) already achieve
   this cleanly via `${ENV_VAR}` header substitution. The DeepSeek
   provider key does **not**: `agent exec`'s model-catalog resolution step
   needed a stored `auth.profiles.deepseek:manual` entry to recognize the
   model at all before any SecretRef was tried, and once that plaintext
   profile exists it permanently shadows a later SecretRef, confirmed live
   (`REF_SHADOWED`). **Workaround, untested**: remove the plaintext auth
   profile first (`models auth logout --provider deepseek` or equivalent),
   *then* set the SecretRef and re-test whether `agent exec` still resolves
   the model without ever creating a new plaintext profile. This project
   has deliberately not done this yet ("leave that profile alone" was an
   explicit instruction in the 2026-09-15 ruling run), it is the single
   most concrete unclosed loop in the whole secrets story.

5. **Any tool-call-level interception for logging, a safety veto, or a
   spend gate.** Confirmed absent this session (the `hooks` subsystem is
   session/command/gateway-lifecycle only). **Workaround, already the
   design's plan and unaffected by this finding**: `dfmcp/roles.py`
   enforces the safety boundary server-side, at the MCP server, not inside
   openclaw. Nothing here changes that design decision; if anything it
   reinforces it, since openclaw genuinely has no equivalent enforcement
   point to lean on instead.

6. **Shared, cross-agent state ("the fort dossier").** Each agent's session
   store is isolated by design; nothing pools it automatically.
   **Workaround, already the plan**: the DF MCP server itself and
   `dfqueue`'s SQLite queue are the real shared substrate, this is not a
   new gap this pass discovered, it was already the architecture's answer
   (`docs/AGENT-ARCHITECTURE.md` §7's finding, re-confirmed here).

7. **Config schema stability across a `latest` pin.** Two undocumented
   requirements (`agents.ownership: "explicit"`, `agents.defaults.
   systemAgent.agentId`) and one accepted-then-rejected key (`_note`) have
   already surfaced within one week of active use, each discovered only by
   hitting it live, not by reading the schema or `config validate` output
   in advance. **Workaround**: none structural, `docs/TRAPS.md` is
   already the project's running list of these, and the practical mitigation
   is to keep re-validating a working config after every VM rebuild or
   openclaw image pull, not to trust that a config that validated once
   still will.

---

## 3. The one open design question: dispatcher-plus-queue, or direct calls?

**Recommendation: keep routing every agent-to-agent interaction through
`dfqueue`, not through openclaw's native `sessions_send`/`sessions_spawn`.**
This is not a new call, it is what this project has already done in every
real run to date (architect run #3's proposal, the overseer's ruling), and
this research finds no reason to reconsider it. Four independent reasons:

- **The native primitive has a confirmed real bottleneck** (item 1 above),
  and this project's actual roster shape (an Overseer plus several
  specialists) is exactly the fan-out pattern that bottleneck punishes.
- **The native primitive gives no structured record.** `sessions_send`
  passes a message; `dfqueue` enforces a typed, validated schema at write
  time (closed `type` vocabulary, a falsifiable `prediction`, a named
  `cost`). `docs/AGENT-ARCHITECTURE.md` §4's whole "writes are tool calls,
  reads are XML" design depends on that enforcement happening somewhere,
  and openclaw's own inter-agent channel enforces nothing of the kind, it
  is prose in, prose out.
- **The queue is already the audit log this project needs**, and a second,
  parallel channel (openclaw's own session logs for `sessions_send` traffic)
  would mean two record systems answering "what did agents tell each
  other," an unforced coordination cost the current one-shot design
  entirely avoids by construction: there is no live inter-agent channel to
  audit, because there is no live inter-agent channel.
- **openclaw's own crash/persistence model doesn't understand external
  side effects** (confirmed doc-only, not tested live): if a
  `sessions_send` round-trip crashed mid-flight, nothing here suggests
  openclaw would know whether the queue write it was trying to relay had
  already landed. Routing through `dfqueue` directly, one write-time-
  validated tool call per role turn, sidesteps that ambiguity because the
  queue's own write is the transaction boundary, not a chat message that
  might or might not have been delivered.

**What would change this recommendation**: if a future need genuinely
requires two agents to negotiate synchronously within one turn (not this
project's current no-peer-chat design, see `docs/AGENT-ARCHITECTURE.md` §4),
`sessions_spawn`'s sub-agent path is a better fit than `sessions_send`,
because sub-agent results return non-blocking/push-based rather than through
the same serialized lane, but nothing in this project's roster today needs
that, and adopting it would mean building a second communication channel
alongside the queue for no design reason yet identified.

---

## 4. What could not be verified

- **Whether the `sessions_send` lane-concurrency bottleneck (`#14214`) is
  still present in `2026.9.4`.** The issue is from `2026.2.9`, closed
  not-planned/stale; nobody in this project has re-read the current
  `src/gateway/server-lanes.ts` against the actually-running image, only
  against GitHub's hosted source at the time of the 2026-09-12 research
  pass. Treated as probable-current in §2/§3 above, not certain.
- **Whether removing the plaintext DeepSeek `auth.profiles` entry and
  relying solely on the `models.providers.deepseek.apiKey` SecretRef
  actually works end-to-end.** Schema-valid and partially live-observed
  (the ref resolves; it's just shadowed), but the actual "no plaintext
  anywhere, model still resolves" experiment has never been run, every
  session that could have tried it was explicitly told to leave the
  existing profile alone.
- **Whether `openclaw secrets store`'s `secret`-kind values are encrypted
  at the row level.** The backing SQLite file itself is not whole-file
  encrypted (confirmed via `file(1)`, real SQLite header), and the store is
  empty on this install, so there is no row to inspect either way.
- **The exact cause of this session's own new finding** (read-only mount
  now failing to open `state/openclaw.sqlite` where it worked on
  2026-09-15). Plausible SQLite WAL/lock explanation given above, not
  confirmed, and not chased further to respect the read-only mandate.
- **Real memory/CPU footprint of running a Gateway continuously**, since
  every real run in this project has used throwaway `agent exec`
  containers, never `gateway run`. No measurement exists anywhere in this
  project.
- **Whether openclaw's documented "up to 3 automatic recovery attempts"
  after a crash covers, or even knows about, a DF-side mutation that was
  in flight when the crash happened.** Nothing found (docs or schema)
  addresses this; it would need a live crash-injection test this pass
  did not attempt (and which the project's `agent exec`-only pattern makes
  hard to even stage, since there is no long-running process to crash).
- **Full current model-provider pricing/cost-cap options** beyond what
  `agent exec --json`'s own `usage`/`costUsd` fields report, `models
  list` exposes no pricing field in this build, so any "cheapest model"
  claim anywhere in this project's history (including this report's own
  table) is a naming-convention inference, not a verified price.

## Relevant to

The user's live multi-agent design work (agent-to-agent question, §3 above);
`docs/AGENT-ARCHITECTURE.md` §3-4 (specialist scoping, no-peer-chat), §13-14
(deployment topology, open items); `Working.md`'s "In discussion: designing
the learning loop" section, specifically "how roles call each other," which
this report answers directly for the near term (they don't call each other
via openclaw; they discuss via the queue) while leaving open how a future
learning role that must be "callable by other roles and able to call them in
turn" would work, since that is a capability neither openclaw's native
channel nor `dfqueue`'s current one-shot shape actually provides today.
