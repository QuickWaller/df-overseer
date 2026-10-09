# What openclaw adds to each agent run, and what can be cut

Date: 2026-10-09. Read-only. Sources: openclaw 2026.9.4 (commit 3a9d69d, the image installed on VM 106, `ghcr.io/openclaw/openclaw:latest`), its bundled `docs/` and `dist/` read in a throwaway `docker run --entrypoint sh` (no agent run), one real captured request (the architect run of 2026-10-07, retained in a thinking state dir on VM 106), 65 archived run envelopes, the pinned per-role configs, and the repo's own tool registry measured offline. No config changed, nothing started.

## Answer first

1. **openclaw adds very little, and most of what it adds we already cut.** The captured request had no built-in tools (all 55 tools were dfmcp tools), no skills section, no memory section, and no USER, HEARTBEAT, TOOLS, MEMORY or BOOTSTRAP files. The one mechanism doing this is already in every pinned config: `agents.entries.<role>.tools.allow: ["<host>__*"]`. Across 65 archived run envelopes, all 131 distinct tools ever called are dfmcp tools; no run used a built-in.
2. **What openclaw still adds is about 2.0k tokens of system prompt, of which roughly 1.2 to 1.5k is irrelevant to us, and none of it is configurable.** OpenClaw owns the generated prompt (docs: `systemPromptOverride` was removed; `promptMode` is set by the runtime, not user config). The only switch that touches it, `contextInjection: "never"`, would also stop `SOUL.md` being injected, and `SOUL.md` is how the charter is delivered. So it must not be used.
3. **The big per-call payload is ours, not openclaw's.** First model call of the captured run: 20,237 prompt tokens (19,853 uncached plus 384 cached). Estimated split: tool schemas about 15.5k (77 percent), system prompt about 2.0k (10 percent), briefing about 1.6k (8 percent), the remainder is wire overhead. After the 2026-10-08 charter-mount fix the charter adds another 1.8k to 2.9k tokens per role (it was missing from this capture).
4. **Savings available from config: about 70 tokens per call, effectively nothing. Savings available from our own content: about 3.4k tokens per call for the architect (about 21 percent of its tool schemas) by dropping the "Verified against a live fort" provenance tails from tool descriptions.** That is a dfmcp change, not an openclaw one, and it is a judgment call (see below).
5. **In money terms none of this matters much; reasoning output does.** At official DeepSeek Pro off-peak rates the architect run of 2026-10-08 cost about $0.128, of which output (43k tokens, 90 percent or more reasoning) was about $0.085. The whole fixed prefix (tools plus system prompt) is roughly $0.015 per run, mostly the one uncached first call. Trimming openclaw's 1.2k tokens is worth about $0.001 per run. See `research/2026-10-08-thinking-budget.md` for why the cost and wall clock are output-bound.

## Method and calibration

- **Request payload (verified).** openclaw writes `trajectory_runtime_events` rows into the per-agent SQLite (`agents/<id>/agent/openclaw-agent.sqlite`). The `context.compiled` event holds `systemPrompt`, `prompt`, `messages` and `tools`. Only one such capture exists (the architect run of 2026-10-07 23:10, state dir `/var/lib/conductor/thinking/...`); the shared state dir's five agent databases have zero trajectory rows, and normal conductor runs do not retain a state dir. So I have one real payload, for one role, from before the charter-mount fix of 2026-10-08.
- **The captured `tools` array is truncated** (its last element is the string "[Truncated]", total 11,005 chars for 55 entries). Do not use it for sizing. I measured tool schemas offline instead: `dfmcp.tools.tool_definitions` for each role, serialised in OpenAI function form, compact JSON.
- **Token calibration (verified arithmetic, inferred ratio).** Real first-call prompt tokens 20,237 against about 76k characters (59k tools estimated for 55 of 57 tools, 7.5k system, 6.1k briefing, plus wrapper) gives about 3.75 chars per token. All token figures below use that ratio; treat as plus or minus 10 percent. The estimate (19.3k) landed 5 percent under the real 20.2k, which is why I trust it at this precision and no better.
- A model-bound check: the `custom` transcript rows (up to 77k chars each) are `openclaw.cache-ttl` bookkeeping, not sent to the model (usage input of 22k at that point confirms it).

## What the request actually contains (architect, captured)

### System prompt, by section (verified, chars from the captured string; tokens at 3.75 chars each)

| Section | chars | tokens | Needed by us? |
|---|---|---|---|
| Tooling (header plus one line per tool name, 55 names) | 1,594 | 425 | Names duplicate the schemas; the header "tools policy-filtered" is harmless |
| Tool Call Style (incl. /approve, exec approval text) | 490 | 131 | No (we have no exec) |
| Execution Bias | 466 | 124 | Mixed: "act now", "continue to done" is tolerable, not needed |
| Promised Work (background, delegated, follow-through) | 501 | 134 | No (no cron, no subagents) |
| Safety | 882 | 235 | Harmless, mostly about login codes, config edits |
| Runtime Context (internal-context delimiters) | 497 | 133 | No (no runtime-context carriers on our runs) |
| OpenClaw Control | 305 | 81 | No |
| Workspace (working directory `/app`, workspaceOnly note) | 278 | 74 | No |
| Documentation (`/app/docs`, GitHub) | 493 | 131 | No; even invites reading docs with no read tool |
| Workspace Files header plus three "[MISSING]" markers (AGENTS.md, SOUL.md, IDENTITY.md) | 530 | 143 | SOUL.md is the charter slot; the AGENTS and IDENTITY markers are pure waste (about 57 tokens) |
| Temporal Context (date, UTC) | 60 | 16 | Yes, but the briefing carries the game tick, not the date |
| Assistant Output Directives (MEDIA, audio, reply tags) | 404 | 108 | No |
| Silent Replies (`NO_REPLY`) | 120 | 32 | No |
| Messaging | 245 | 65 | No |
| Runtime line (agent, session key, os, node, model) | 584 | 156 | No; host is pinned to the role name by the runner |
| Opening line and cache markers | ~150 | ~40 | n/a |
| **Total** | **7,482** | **~2,000** | about 1.2 to 1.5k irrelevant |

Of the ~2.0k, only the tool-name list, a slice of Execution Bias and the SOUL slot do anything for our roles. The rest is openclaw's general assistant scaffolding (channels, approvals, subagents, docs).

The opening sentence is "You are a personal assistant running inside OpenClaw." and the injected-files header describes SOUL.md as "persona/tone. Follow it unless higher-priority instructions override." So the charter reaches the model framed as persona, below an assistant identity. That is a behaviour question, not a token one, and I did not test it.

### Tools

- Built-in tools in the request: **none** (verified, all 55 names in the Tooling list carry the dfmcp prefix). `tools.allow` with only the dfmcp glob is what filters them (verified from the prompt; docs: `tool-policy.md` profiles are a base allowlist, `allow` is applied on top; the unset default would otherwise include fs, exec, web, sessions, memory, cron and more).
- Built-in tools never called (verified): 131 distinct tools across 65 envelopes, none unprefixed.
- Our schemas, per role (offline from the repo registry, current as of this commit; live architect had 55 at capture, now 57):

| Role | tools | schema chars | est. tokens | of which "Verified against a live fort" tails (chars) | parameter descriptions (chars) |
|---|---|---|---|---|---|
| architect | 57 | 62,005 | ~16.5k | 12,869 | 20,512 |
| overseer | 83 | 101,907 | ~27.2k | 14,561 | 38,372 |
| quartermaster | 28 | 36,365 | ~9.7k | 4,716 | 11,197 |
| consultant | 29 | 33,511 | ~8.9k | 2,883 | 11,991 |
| planner | 15 | 18,901 | ~5.0k | 1,014 | 3,446 |

  The largest single schema is `queue.propose` (6.7k chars, about 1.8k tokens) for the architect, then `building.find`, `zone.find` (2.8 to 3.0k each).

### Workspace and bootstrap files

- Injected: `AGENTS.md`, `SOUL.md`, `IDENTITY.md` slots only, resolved from the container cwd `/app`, not the configured workspace (matches the 2026-10-08 charter-delivery finding). In the capture all three were `[MISSING]`, so the charter was absent from this run; the runner now mounts it at `/app/SOUL.md`.
- Not injected (verified by absence in the capture; docs list them as loaded when present): `USER.md`, `MEMORY.md`, `BOOTSTRAP.md`. `HEARTBEAT.md` and `TOOLS.md` do not appear in this version's bootstrap set at all; the docs say heartbeat scratch is not a bootstrap file and "HEARTBEAT.md is accepted but a no-op" in `skipOptionalBootstrapFiles`. `TOOLS.md` is not mentioned in the 2026.9.4 docs I read; I did not find it in the injection code either (not exhaustively searched).
- The `## Tools` section of AGENTS.md is mentioned in the prompt ("guides usage; never grants availability") but AGENTS.md is empty for us.
- Skills: the prompt has no Skills section (verified in the capture). The source builds the section only when `skillsPrompt` is non-empty (`system-prompt-params-*.mjs`); why it is empty here is **not traced** (probable cause: skill loading needs a `read` tool, which the allowlist removes; inferred). The image ships `/app/skills` and the state dir has a `plugin-skills` directory with two entries (browser-automation, canvas); neither reached the prompt.
- Memory: no memory section, no recall instructions (verified in the capture; memory index tables in the SQLite are empty).

### Briefing and charter

- Briefing (our `prompt`): 6,073 chars, about 1.6k tokens, for that architect wake.
- Charter via SOUL.md (our `agents/<role>/role.md`, sizes in bytes): architect 11,073 (about 2.9k tokens), quartermaster 10,909, overseer 10,594, planner 7,798, consultant 6,782 (about 1.8k). Not in the capture; estimated. Bootstrap per-file cap is 20,000 chars and total cap 60,000, so no charter is truncated today (architect is the largest at 11k).

## What the model pays per run (from real usage)

Archived envelopes (verified): a typical recent run is 7 to 12 model calls with 240k to 700k cached tokens and 50k to 90k uncached input. The fixed prefix (tools plus system prompt plus charter) is re-sent every call: for the architect about 20k tokens by 12 calls, about 240k, i.e. roughly 40 percent of its cached reads. It is billed at the cache-hit rate after the first call.

One thing worth measuring and not yet known: the captured first call had only **384 cached tokens of 20,237**. If a prior run of the same role had been recent, the stable prefix (tools plus stable system prompt, about 17k tokens) should have hit the cache. Either the previous run was outside DeepSeek's cache retention (likely, wakes are hours apart), or something early in the request varies between runs. I could not tell which. The cost of a cold prefix is the first call at the miss rate (about $0.011 for 16.5k tokens at official Pro off-peak).

## What can be turned off, and what it saves

| Lever | Exists? | Est. saving per call | Risk | Verdict |
|---|---|---|---|---|
| Built-in tools (exec, fs, web, browser, sessions, memory, cron, message, etc.) | Already off via `tools.allow` | 0 (already done) | If the allow list is ever dropped or mis-globbed, a full coding-profile tool set (many schemas, plus exec) reappears | Keep. Worth a regression check: assert no non-dfmcp tool name in a run's tool summary, or run `openclaw` config validation in the deploy |
| Skills | Not injected (verified); `agents.entries.<id>.skills: []` is the explicit off | 0 now | None | Optional belt and braces, saves nothing today |
| Bootstrap files (USER, MEMORY, BOOTSTRAP, HEARTBEAT, TOOLS) | Not injected | 0 | None | Nothing to do |
| `agents.defaults.skipBootstrap` / `skipOptionalBootstrapFiles` | Exist, but only control file *creation* in the workspace, not injection | 0 to ~60 (cannot remove the `[MISSING]` markers) | Low | Not useful here |
| `contextInjection: "never"` | Exists | ~200 (workspace section and markers) | **Removes SOUL.md, i.e. the charter. Breaks every role** | Do not use |
| `contextInjection: "continuation-skip"` | Exists | 0 (one-shot runs have no continuation turns) | None | No effect |
| `bootstrapMaxChars` / `bootstrapTotalMaxChars` | Exist (20k / 60k) | 0 | A charter above 20k chars would truncate silently with a notice | Keep defaults; note the ceiling |
| System prompt replacement or minimal mode | **No.** Override removed (docs `config-migrations.md`: "OpenClaw owns the generated system prompt"); `promptMode` is runtime-set (full by default; minimal is for sub-agents) | would be ~1.2 to 1.5k | n/a | Not available by config. Reachable only through a plugin or hook (`before_prompt_build`, `agent:bootstrap`), which is a larger and riskier change than the saving justifies |
| `experimental.localModelLean` | Exists, removes optional tools (browser, message, media, tts, pdf) | 0 (already filtered) | Experimental | No effect for us |
| `tools.toolSearch` (modes `code`, `tools`, `directory`) | Exists, experimental | ~10k tokens for the architect, ~20k for the overseer (inferred: replaces schemas with a directory capped at 18k chars, shorter than our schemas) | **Adds model calls**: MCP tool input schemas are "unknown" until `describe`, so each first use of a tool needs an extra round trip; the thinking-budget research shows each extra call costs about 3 to 4k reasoning tokens and runs are already wall-clock bound (5 of 57 runs hit 600 s). Also changes the model-facing surface we validated, and the docs call it experimental | Do not use. Token saving is mostly cached-read tokens at a few cents per million; the extra calls cost far more |
| Our own tool descriptions (dfmcp) | Ours to change | architect ~3.4k, overseer ~3.9k, quartermaster ~1.3k, consultant ~0.8k (the provenance tails alone) | The tails are written for human audit ("Verified against a live fort: 2026-09-21 ...", handoff paths, register pointers). Some carry real caution for the model ("NOT yet live-verified", "unverified"); 7 of the architect's 57 descriptions say "unverified" | Judgment call for whoever owns `dfmcp/tool_guidance.py` and the confidence legend. A compact one-line status (verified, unverified, partial) would keep the signal and drop the prose |
| Our own parameter descriptions (dfmcp) | Ours to change | up to the 20.5k chars (about 5.5k tokens) for the architect, 38k (about 10k tokens) for the overseer if halved, about half that | They carry the "never a coordinate, never a path" guidance models need | Only trim with eval backing; not recommended as a blind cut |

## Estimated saving, honestly

- Config-only, safe: **about 0 tokens** (everything safe is already set).
- Config plus accepting unavailable-without-a-plugin cuts (system prompt scaffolding): about 1.2 to 1.5k tokens per call, not reachable by config.
- Our own descriptions, the one real lever: about 3.4k tokens per call for the architect (the verified-tail prose) and 3.9k for the overseer, i.e. 20 percent and 14 percent of their tool schema cost, and about 9 to 16 percent of each role's total fixed prefix (tools, system prompt and charter together).
- Money: at most a few tenths of a cent per run for any of these (the prefix is cache-read after the first call). The reason to do the dfmcp trim is prefill latency and a cleaner tool surface for the model, not cost.

## Discrepancies, docs against code, and surprises

- **Docs against capture.** The docs name AGENTS, SOUL, IDENTITY, USER, BOOTSTRAP and MEMORY as bootstrap files, and `HEARTBEAT.md` only as an accepted no-op; the request showed just the AGENTS, SOUL and IDENTITY slots (the others are injected only when present, and none exist in `/app`). No discrepancy in substance, but the capture, not the docs list, is what shows which slots appear.
- **The charter-delivery bug is visible in the capture.** The 2026-10-07 request shows `/app/SOUL.md [MISSING]`, so that run had no charter at all. That is the bug fixed 2026-10-08 (see `evals/live/2026-10-08-charter-delivery`); this audit independently reproduces its symptom from the payload.
- **The prompt tells the model the tools list in two places** (tool name lines in Tooling plus the schemas). Not configurable.
- `tools.allow` containing only the dfmcp glob hides even `session_status`, `progress_card` and the other default-on tools. Verified by the capture, not just the docs.

## NOT VERIFIED

- Only one real payload (architect, 2026-10-07, pre charter-mount fix). Prompts for the other four roles and for a post-fix architect run are not captured; their system prompt should be near-identical except the tool-name list length and the SOUL contents (inferred). A cheap way to get them: pass `CONDUCTOR_THINKING_STATE_DIR` retention for one supervised cycle, or add a one-off `context.compiled` dump. I did not run an agent.
- Why the Skills section is empty (probable: no `read` tool) was not traced in source.
- Whether the stable prefix is cached across runs. The one first call had 384 cached tokens; I could not see a prior same-role run's timing relative to the DeepSeek cache window.
- Token figures use a 3.75 chars-per-token ratio calibrated on one request, not a real DeepSeek tokenizer. Plus or minus 10 percent.
- Whether the "persona" framing of SOUL.md under "You are a personal assistant" measurably weakens charter adherence: not tested.
- Official-rate dollar figures come from the DeepSeek pricing page as recorded in `research/2026-10-08-thinking-budget.md`; not checked against a balance.
- `tools.toolSearch` token savings and extra-call cost are inferred from its docs and the earlier thinking-budget numbers; not run.
- I did not confirm that `agents.entries.<id>.skills: []` or `tools.allow` behaves identically across a conductor-pinned config reload (the pinned configs all carry the same allow entry, verified by reading them).

## Recommendations (for the orchestrator to decide)

1. Leave the openclaw config as it is: the tool allowlist is the right and only effective lever, and it is already set on all five roles. Do not enable `contextInjection: "never"` or Tool Search.
2. Add a cheap guard that no non-dfmcp tool ever appears (the archived `tool_summary.tools` already makes this a one-line check in the conductor report).
3. If prefill or tool-surface noise matters, trim the "Verified against a live fort" tails in dfmcp descriptions to a short status line (about 3 to 4k tokens per call for the two largest roles), with an eval, as a dfmcp change.
4. If a real per-role prompt breakdown is wanted for the report, capture one `context.compiled` event per role in the next supervised cycle (state dir retention), now that SOUL.md is mounted.

## Relevant files

- `conductor/runner.py` (docker invocation, SOUL.md mount, `--hostname <role>`)
- `/opt/openclaw/conductor/pinned-configs/<role>.json` on VM 106 (the `tools.allow` entry)
- `dfmcp/tools.py` `tool_definitions` (schema source), `agents/<role>/role.md` (charter), `agents/<role>/tools.yaml`
- `research/2026-10-07-openclaw-source-sessions.md`, `research/2026-10-08-thinking-budget.md`
