# Thinking budget for the agents (DeepSeek V4 via openclaw)

Date: 2026-10-08. Read-only research. Sources: DeepSeek official API docs fetched 2026-10-08 (cited by URL), the openclaw 2026.9.4 image's own docs and bundled `dist/` source plus the installed `@openclaw/deepseek-provider` 2026.9.4 plugin (read on the agent VM, nothing run), pinned configs, `conductor/runner.py`, 57 archived run envelopes, and the 41-row runs DB.

## Answer first

1. **There is no token thinking budget for DeepSeek V4.** The only reasoning control is a three-level effort dial, `reasoning_effort` = `low | high | max`, plus an on/off switch (`thinking.type` or effort `none`). `budget_tokens` does not exist in DeepSeek's native API; on its Anthropic-compatible endpoint it is accepted and explicitly ignored. `max_tokens` is the only token cap, and it is per request (per model call), not per run.
2. **openclaw can set both, per role, but with two limits.** It passes `reasoning_effort` and `max_tokens`, but its DeepSeek plugin only ever sends `off`, `high` or `max` (never `low`). `agent exec --thinking <level>` is a per-run flag; the conductor does not use it yet. openclaw has no max-turns cap and no per-run token or cost cap. Its tool-loop detector is off by default and its thresholds are fixed constants.
3. **The real problem is volume, not loops.** Reasoning is 90 to 98 percent of every run's output tokens, runs use 8 to 10 model calls each, and 5 of 57 archived runs (architect 4, planner 1, plus an early overseer) hit the 600 s wall clock and were killed with their work lost. The wall clock is currently the only, and the worst, budget. No identical-call loops were found (max repeat of one call within a run: 2).
4. **Cost is probably understated by about 2x.** The logged `cost_usd` comes from openclaw's own hard-coded estimate table, not from DeepSeek's bill. DeepSeek's pricing page today lists higher, peak/off-peak Pro rates. See "Pricing" below. The orchestrator's check that the 0.435/0.87 rates reproduce the logged cost is circular, because those numbers are the table openclaw uses to compute the logged cost.

## Verdict on the two third-party leads

### GitHub README (nwfella/deepseek-thinking-guide, 0 stars, no sources cited)

| Claim | Verdict | Evidence |
|---|---|---|
| DeepSeek exposes `budget_tokens` on `deepseek-reasoner` | **Does not hold** | `deepseek-reasoner` was retired 2026-07-24 15:59 UTC (openclaw provider doc, secondary source; the official model table now lists only `deepseek-flash` and `deepseek-v4-pro`). The string `budget` appears nowhere in the official thinking-mode, chat-completion, pricing, rate-limit or change-log pages. The Anthropic-compat page says: `thinking` "Supported (`budget_tokens` is ignored)" (https://api-docs.deepseek.com/guides/anthropic_api). Confirmed. |
| "A reasoning-effort dial on most providers" | **Holds for DeepSeek, in different form** | Official: `reasoning_effort` in `none | low | high | max`; `minimal` maps to `low`; `medium` and `xhigh` map to `high`; `ultra` maps to `max`. Default `high`. https://api-docs.deepseek.com/guides/thinking_mode and https://api-docs.deepseek.com/api/create-chat-completion. Confirmed. |
| Levels 0-1 minimal, 2 medium, 3 high, 4 max | **Does not hold** | No numeric scale exists. Real effective values are three (`low`, `high`, `max`) plus off. "Medium" is just an alias of `high`. |
| "Level 2 is the sweet spot for agentic work" | **No basis** | DeepSeek's change log (2026-08-13) says: low for simple tasks, high for daily Agent tasks, max for more complex scenarios. So the official sweet spot for agent work is `high`, which is already our default. |
| Meta-rule: budget scales with search-space size, not difficulty | **Unverified heuristic, sensible as framing only** | No source. It is not a documented DeepSeek behaviour. Used below as a framing for choosing effort, not as a parameter. |

### OpenClaw hosting page (marketing)

| Claim | Verdict |
|---|---|
| Two variants, Flash and Pro | Holds, but names changed. Official model table (https://api-docs.deepseek.com/quick_start/pricing, fetched 2026-10-08): `deepseek-flash` (DeepSeek-V4.1-Flash, released 2026-09-10) and `deepseek-v4-pro` (DeepSeek-V4-Pro-0813). `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are legacy aliases, "temporarily routed" to V4.1 Flash and billed at Flash price (change log 2026-09-10). Our pinned configs still say `deepseek/deepseek-v4-flash`, so a Flash run today is silently V4.1 Flash, not the model the research earlier described. |
| Pro GA build 0813 on 2026-08-12 | Official change log says **2026-08-13**, same model id `deepseek-v4-pro`. Pro stays available after 2026-09-14 "with billing method unchanged" (change log 2026-09-10). |
| Pro $0.435 in, $0.87 out, $0.003625 cache hit; Flash $0.14/$0.28 | **Does not match the official page today**; matches openclaw's built-in estimate table exactly (plugin `models-DA9ipAUh.js`: Flash .14/.28/.0028, Pro .435/.87/.003625). See Pricing. |
| Flash ~1/3 of Pro output cost, 5x concurrency | Concurrency holds: 2500 Flash vs 500 Pro per account (https://api-docs.deepseek.com/quick_start/rate_limit). Cost ratio on the official page: output $0.60 vs $1.98 off-peak (Flash is about 30 percent of Pro), input cache-miss $0.15 vs $0.66. "Agent-tuned": unverified marketing. |

## Q1. DeepSeek API parameters (official docs, fetched 2026-10-08)

| Item | Finding | Confidence |
|---|---|---|
| Model id | `deepseek/deepseek-v4-pro` in `conductor/config.py` `DEFAULT_MODEL`; runner passes `--model` per run; API id `deepseek-v4-pro`. Official id list: `deepseek-flash`, `deepseek-v4-pro`. | Confirmed (code and docs) |
| Thinking on/off | `thinking: {"type": "enabled|disabled"}` (OpenAI format) or `reasoning_effort: "none"` disables. Default: thinking enabled, effort `high`. | Confirmed (official) |
| Effort | `reasoning_effort` in `none, low, high, max`, same for V4-Pro and V4-Flash ("three thinking effort levels", change log 2026-08-13). | Confirmed |
| Token budget parameter | None. `budget_tokens` ignored on the Anthropic endpoint; absent from native API. | Confirmed |
| `max_tokens` | 1 to 393216 (384K). Default when unset: 8K non-thinking, **64K thinking, 128K thinking with effort `max`**. | Confirmed (official) |
| Do reasoning tokens count against `max_tokens`? | Docs define `reasoning_tokens` as a breakdown inside `completion_tokens_details`, and the thinking-mode default of 64K is far above the non-thinking 8K, which implies the cap covers CoT plus answer. The docs never state it in one sentence. | Strongly implied, not stated |
| Behaviour when the cap is hit mid-reasoning | Documented only as `finish_reason: "length"` ("maximum number of tokens specified in the request was reached"), with the note that content "may be partially cut off". Nothing says whether a reasoning-only truncation returns empty content or a half tool call. openclaw has a `promoteThinkingOnlyFinalOutputToText` path for `stopReason` `length`, suggesting reasoning-only truncation does occur. | Unknown beyond `length`; not tested live |
| Other `finish_reason` values | `stop, length, content_filter, tool_calls, insufficient_system_resource, aborted`. | Confirmed |
| Account spend limit | None documented. Billing is a topped-up or granted balance; running out returns an "out of balance" error (https://api-docs.deepseek.com/quick_start/error_codes). No hard daily cap parameter found. | Confirmed absence in docs; cannot see the console |
| Sampling in thinking mode | `temperature`, penalties have no effect; `top_p` floored to 0.95. | Confirmed |
| Concurrency | 500 (Pro), 2500 (Flash) per account; 429 beyond. | Confirmed |

### Pricing (official page 2026-10-08 versus openclaw estimate)

Official, per 1M tokens, Pro: cache hit $0.022 off-peak / $0.044 peak; cache miss $0.66 / $1.32; output $1.98 / $3.96. Flash: $0.003/$0.006, $0.15/$0.30, $0.60/$1.20. Peak is 01:00-04:00 and 06:00-10:00 UTC Monday to Friday; all else off-peak (new prices effective 2026-08-16 16:00 UTC per change log 2026-08-13).

Check on the architect run of 2026-10-08 (645,760 cache + 43,707 input + 43,163 output): openclaw estimate $0.0589 (matches the logged $0.058905); at the official off-peak Pro rates it is about $0.128, at peak about $0.256. So the true bill is plausibly 2.2x to 4.4x the logged cost. **Not verified against an actual balance movement**; the cheap way to settle it is to read the console balance before and after one known run (the user can do this; I cannot).

## Q2. openclaw 2026.9.4

### Where thinking effort takes effect (confirmed by reading source and docs on the installed image)

- Resolution order (image doc `docs/tools/thinking.md`): inline directive, session override, **per-agent `agents.entries.<id>.thinkingDefault`**, global `agents.defaults.thinkingDefault`, then provider default (DeepSeek V4 profile default: `high`).
- **Per run, from the conductor: `agent exec --thinking <level>`** (image doc `docs/cli/agent.md`, `agent exec` options list; same doc lists `--model`, `--fallback`, `--timeout`). `runner.py` builds the command with `--model` and `--timeout` only; it does not pass `--thinking`. Not run live (I may not run agents); flag exists in the documented option list.
- DeepSeek plugin level set: `off, minimal, low, medium, high, xhigh, max` (plugin `dist/thinking.js`), default `high`.
- **Mapping to the wire (core `dist/provider-stream-shared-*.mjs`, `resolveDeepSeekV4ReasoningEffort`): `xhigh` and `max` send `reasoning_effort: "max"`, every other non-off level sends `"high"`. `off` or `none` sends `thinking: {type: "disabled"}` and deletes effort.** The wrapper sets `payload.reasoning_effort` after any user params, so a user param cannot reach `low`. Net: openclaw can express off, high, max only. Matches the image's own DeepSeek doc ("lower non-off levels map to `high`").

### max_tokens

- Config sources merged per model request (`dist/model-extra-params-*.mjs`): `agents.defaults.params`, `agents.defaults.models["<provider>/<model>"].params`, **`agents.entries.<id>.models["<provider>/<model>"].params`**, `agents.entries.<id>.params`. `canonicalizeMaxTokensParam` accepts `maxTokens` or `max_tokens` and sets the stream's `maxTokens` (`extra-params-*.mjs` lines 243-244). The DeepSeek catalog entries carry `compat.maxTokensField: "max_tokens"`, so the outbound field is `max_tokens`. Catalog `maxTokens` is 384000 for all three models.
- Confidence: **read from source, not observed on the wire.** Caveat: the image doc says authored provider params can influence runtime selection; pin `agentRuntime.id: "openclaw"` if added, and validate the pinned config with `openclaw config validate` (not run).
- The pinned per-role configs (`/opt/openclaw/conductor/pinned-configs/<role>.json`) currently have no `params`, no `thinkingDefault`, no `tools.loopDetection`. They list both models and default to `deepseek/deepseek-v4-flash`, which the runner always overrides with `--model`.

### Loop guard and caps

- `tools.loopDetection.enabled`, **default false**, per-agent override at `agents.entries.<id>.tools.loopDetection` (`docs/tools/loop-detection.md`, `docs/gateway/config-tools/built-in-tools.md`). When enabled (`dist/tool-loop-detection-*.mjs`): history of 30 calls, warning at 10 identical calls or no-progress repeats, critical at 20 (blocks), global circuit breaker at 30; detectors: generic repeat, known-poll no-progress, ping-pong, argument churn, unknown-tool repeat. Warnings are injected as messages to the model; critical blocks the next call. Schema also lists `warningThreshold`, `criticalThreshold`, `globalCircuitBreakerThreshold`, `windowSize`, `historySize`, `detectors`, but the code read uses constants (10/20/30/30) and a `resolveToolLoopWarningThreshold()` that returns 10, so **those keys appear to be inert in this build** (inference from the bundle; not tested).
- Post-compaction guard: armed unless `enabled: false`; aborts with `compaction_loop_persisted`. Irrelevant to us (runs are one-shot).
- **No max-turns, no per-run token cap, no per-run cost cap found** (image docs searched; the only `maxTurns` hits are xAI code-execution and web search options). The only run-level bounds: `--timeout` (default 600) and the conductor's `role_timeout_seconds` (overseer 1200).
- Conductor side: `docker kill` after timeout, which loses the run's answer. Status `timeout`, final answer "Request timed out before a response was generated".

## Q3. Live baseline

Sources: 57 run envelopes in the conductor's runtime directory on the agent VM (usage present for the 35 runs since 2026-10-05 08:29; earlier envelopes lack usage), and the runs DB on the fort VM (41 rows; has cost, duration, wake reason, thinking text capped at 12,000 characters, transcript rounds since run-0022; **no token usage columns**, a gap worth closing).

Per role, runs with usage (output includes reasoning):

| Role | n | Model calls/run avg, max | Output tok avg, max | Reasoning tok median, avg, max | Reasoning share of output | Reasoning per call avg |
|---|---|---|---|---|---|---|
| quartermaster | 12 | 8.8, 14 | 31.0k, 76.6k | 23.7k, 28.8k, 72.7k | 93% | 3.3k |
| overseer | 10 | 8.2, 13 | 33.1k, 65.5k | 26.6k, 30.6k, 62.4k | 92% | 3.7k |
| architect | 9 | 9.7, 16 | 41.9k, 65.5k | 42.2k, 39.9k, 62.5k | 95% | 4.1k |
| consultant | 3 | 11.0, 12 | 19.1k, 24.9k | 18.2k, 17.2k, 22.8k | 90% | 1.6k |
| planner | 1 | 5 | 44.5k | 43.5k (timed out) | 98% | 8.7k |

Wall clock and cost (DB, 41 runs; cost is the openclaw estimate): quartermaster avg 311 s, $0.05; architect 414 s, $0.053; overseer 360 s, $0.063; consultant 206 s, $0.043; planner 317 s, $0.03.

By wake reason (DB, small n): consultant `open_ask` 142-295 s; architect `ore_exposed` 61 s (about 5.7k reasoning), `alert_crossed` 390-527 s, `ruling_on_own` 520-607 s (timed out once), `prediction_graded` 342-608 s (timed out twice), `routine_review` 361 s; quartermaster `stuck_job` 178 s, `unsupplied_building` 138 s, `prediction_graded` 195-270 s, `stalled_order` 293-483 s, `ruling_on_own` 183-584 s, `routine_review` 442 s; overseer `queue_pending` 144-696 s; planner `plan_bootstrap` 27 s ($0.012, 6 calls) versus `roadmap_stage_entered` timed out at 607 s.

Timeouts: 5 of 57 envelopes (architect 3 of its 9 runs with usage, the one planner run with usage, and the overseer on 2026-09-25 before its cap was raised), each at about 607 s with 40-45k reasoning tokens where usage exists. The four with usage were still reasoning (97 to 99 percent of output).

Repeated identical tool calls (transcripts, 30 runs with rounds): the most any single (tool, args) pair repeated within a run was 2 (runs 0028, 0031, 0040); 27 runs had none. Tool results are clipped in the archive, so "no progress" cannot be judged, only repetition. No loop behaviour is present in this data; the loop detector would not have fired and is not the lever.

Throughput implication: about 70 to 100 reasoning tokens per second end to end, so 600 s buys roughly 40-60k reasoning tokens, which is why 40-45k-reasoning runs keep hitting the wall.

## Recommended mechanism

Three layers, in order of how well they work.

1. **Effort per wake reason, set per run by the conductor with `--thinking`** (off, high, max are the only distinct wire values). This is the only knob that changes how much the model thinks; default stays `high`. Use `off` only where an A/B shows no quality loss; use `max` only for the rare hard decision.
2. **`max_tokens` per model call in each role's pinned config, as a runaway backstop, not a budget.** Reasoning per call averages 1.6k to 4.1k (planner 8.7k); a per-call cap of 16k leaves 4x headroom. Hitting it yields `finish_reason: length` with unknown content, so keep it loose until the truncation behaviour is verified live (below). Set at `agents.entries.<role>.models["deepseek/deepseek-v4-pro"].params.maxTokens`.
3. **A conductor-side run budget with soft and hard stops**, because openclaw has none. The conductor already mounts the run's state dir (`--state-dir`) and reads its `transcript_events`; extend `runner.py` to poll that SQLite file while the container runs and compute cumulative output/reasoning tokens and model-call count. Soft stop: at the soft budget, nothing can be injected into a one-shot `agent exec`, so log a `budget_soft` event and (optionally) shorten the next wake for that reason. Hard stop: `docker kill` at the hard budget, same as timeout but earlier and logged as `budget_exceeded` with the partial work recorded, instead of at 600 s with nothing. Also store `usage`, `assistant_turns` and effort/model in the runs DB (columns missing today).
4. **Loop signals on the conductor side** (cheap, since openclaw's detector is off): per run, count repeats of identical (tool, args); flag at 3 (baseline max is 2); flag a read tool returning the same result hash 3 times; flag calls per run above 25 (baseline max 16 model calls, 33 tool calls in one architect run); flag timeouts per role per day above 1; flag reasoning share below 50 percent or one call above the per-call cap. Optionally enable openclaw's own detector per role (`agents.entries.<role>.tools.loopDetection.enabled: true`) for its in-run warning messages, accepting fixed thresholds 10/20/30.

## Proposed starting values per wake reason (framed by the search-space heuristic)

Framing: decisions that search a large space (placement, planning, rulings with side effects) get more thinking; lookups and acknowledgements get less. All values are starting points derived from the baseline, to be tuned from the A/B below. "Soft" and "hard" are cumulative reasoning tokens per run; per-call `max_tokens` 16k except where noted.

| Wake reason (role) | Model | Effort | Soft / hard reasoning | Timeout |
|---|---|---|---|---|
| `open_ask` (consultant) lookup | Pro (Flash in A/B) | high; A/B `off` | 20k / 35k | 400 s |
| `ore_exposed`, `stuck_job`, `unsupplied_building` (architect/quartermaster) small, bounded | Flash in A/B, else Pro | high | 12k / 25k | 300 s |
| `routine_review`, `season_change` (quartermaster) | Flash in A/B, else Pro | high | 25k / 45k | 450 s |
| `prediction_graded` (architect, quartermaster) | Pro | high | 30k / 55k | 600 s |
| `stalled_order`, `blocked_order`, `vital_nearing_threshold` (quartermaster) | Pro | high | 30k / 50k | 600 s |
| `alert_crossed`, `ruling_on_own` (architect placement) | Pro | high | 45k / 70k | 900 s |
| `queue_pending` (overseer) | Pro | high | 35k / 65k | 900 s |
| `tripwire`, `unexplained_pause` (overseer, safety) | Pro | max | 60k / 90k | 1200 s (keeps current) |
| `plan_bootstrap` (planner, small) | Pro | high | 10k / 25k | 300 s |
| `roadmap_stage_entered`, `plan_review` (planner stage adoption, large space) | Pro | high; max only after A/B | 50k / 80k | 900 s (now times out at 600) |

Notes: the heaviest observed runs (architect and overseer 62k, quartermaster 73k) sit above the hard values on purpose for architect-ruling and overseer-queue; those are the cases to watch. Raising the timeouts for architect and planner is as much a cost decision as a budget one: the current kills discard 40-45k tokens of paid reasoning for no answer. Wake reasons not listed (`lane_event`, `answer_ready`, `step_done` and the rest with no waking role) need no value yet.

## A/B plan (before switching anything)

Goal: same wakes, Flash (`deepseek-flash`) versus Pro versus Pro at lower effort, judged on a paused copy so nothing real changes.

1. Freeze inputs. Use the existing replay data (`dfqueue/tests/fixtures/wake_window_2026_10_05.json` pattern) and the archived briefings in the runs DB; pick 6 to 8 wakes per role from `ore_exposed`, `stuck_job`, `routine_review`, `open_ask`, `ruling_on_own`, `queue_pending`, `plan_bootstrap`. Advisors (architect, consultant, planner) are read-only and idempotent, so they can be replayed against a paused snapshot; actors (quartermaster, overseer) need a paused copy of the fort or a dry-run MCP profile that rejects writes.
2. Arms per wake: Pro/high (control), Flash/high, Pro/off, and for hard wakes Pro/max. Three repetitions each to see variance.
3. Record per run: reasoning tokens, output tokens, model calls, wall clock, finish reasons, estimated cost and the console balance delta for a batch (to settle the pricing question), and a quality grade (proposal accepted or ruled the same as control; same tool writes; wrong tool calls). Grade advisors offline by comparing proposals; grade actors by the resulting state diff.
4. Decision rule: switch a wake reason to a cheaper arm only if it matches the control in at least 90 percent of paired wakes and has no new tool errors. Change one reason at a time, and keep the `CONDUCTOR_MODEL_<ROLE>` override as the rollback.

## How to verify live (needs a supervised run; I did not run any agent)

1. Wire check: run one `agent exec --thinking max` and one `--thinking off` for a cheap role with the pinned config containing a small `maxTokens`, and inspect the request payload (DeepSeek returns usage; with `--json` the envelope has `usage.reasoningTokens`). Expect `reasoning_tokens` near zero for `off`, higher for `max`, and a `finish_reason` of `length` (stopReason `length`) with `maxTokens` set very low (for example 512), which also answers what a mid-reasoning truncation looks like (empty content, partial tool call, or error). Do this on a throwaway prompt, not a fort wake.
2. Confirm the effort actually sent: enable openclaw request logging for one run, or point the base URL at a local logging proxy for one run, and look for `reasoning_effort` and `max_tokens`.
3. Confirm the pinned config is accepted: validate a candidate pinned config before mounting it.
4. Settle pricing: record the DeepSeek console balance before and after a known run and compare with the official-rate arithmetic above.
5. After each change, read `usage.reasoningTokens`, `assistant_turns` and `status` from the new envelopes and compare against the baseline table; the timeout count per role is the headline metric.

## Not verified

- Whether `max_tokens` and `reasoning_effort` reach the wire from the pinned config (source read only; no live request inspected; I may not run agents).
- Whether `--thinking` on `agent exec` behaves as documented in 2026.9.4 (documented, not run).
- Behaviour of a request truncated by `max_tokens` mid-reasoning (docs say only `finish_reason: length`).
- Whether reasoning tokens count toward `max_tokens` as one pool (implied by docs, not stated).
- The true bill versus the logged estimate (no console access).
- Whether the schema keys `warningThreshold` and friends are inert (inferred from constants in the bundle).
- Whether any DeepSeek account-level spend limit exists in the console (docs show none).
- The openclaw doc search for a per-run token cap was by keyword; a feature under a name I did not search for could exist. The `agent_end` and `before_tool_call` plugin hooks would be the place to build one if wanted.
- Flash quality on our roles: only marketing and the vendor's own benchmark list exist; nothing project-specific.
- Run usage before 2026-10-05 08:29 and per-wake-reason reasoning tokens (envelopes carry usage by role and cycle, the DB carries wake reason, and the two were not joined; the per-reason timing above is wall clock only).
- Any numeric 0-4 effort scale in DeepSeek or openclaw (the nwfella README's levels): none found.
