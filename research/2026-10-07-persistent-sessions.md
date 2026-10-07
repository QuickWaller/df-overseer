# Persistent sessions versus one-shot runs for the fort agents (openclaw, DeepSeek v4 pro)

Date: 2026-10-07. Read-only investigation. Nothing on any VM was written, restarted
or run; the runs database was opened read-only; the agent VM's docker socket is not
readable by the SSH user, so the installed image was not inspected.

Question (user): should the agents be sessions that stay alive across wakes instead
of one-shot runs, and how does that perform with openclaw specifically?

## 1. Answer

**Do not make the agents persistent sessions. Keep one-shot runs, and put the
continuity the roles actually need into a small, curated, queue-resident
notebook that the conductor injects into each briefing.** Reasons, strongest first:

1. **The tool cannot do it today.** `openclaw agent exec`, the entry point the
   conductor uses, mints a new random session id on every invocation and has no
   flag to pass a session id or key (read in source, both the installed-era tag
   and current main). Persistence means leaving `agent exec` for either the
   Gateway (never run in this project, which the register already ruled out on
   2026-09-22) or `agent --local --session-key` against a retained state
   directory (documented, not tried here). Either is a new execution path,
   not a flag.
2. **It does not save money.** Output tokens are 52% of cost and a persistent
   session does not reduce them. Measured on real runs, a persistent session whose
   cache stays warm costs about the same as one-shot with a perfect cache
   (overseer $0.055 to $0.089 per wake as the context grows from 0 to 800k tokens,
   versus $0.066 measured one-shot), and at the real wake cadence (gaps from minutes
   to 36 hours, cache TTL unknown and best-effort) the expected cost is 35 to 55%
   higher than one-shot. A cold cache on a carried 400k context costs $0.22 to $0.24
   for the first round alone, three to five times a whole one-shot wake.
3. **It adds the failure modes this fort is most exposed to.** The fort state
   changes between wakes while the session's memory of it does not. Long-context
   degradation, early-assumption lock-in and stale tool results are all documented
   (section 4). The queue already makes decisions durable and the server already
   re-reads cited facts, so a persistent session would hold a second, unaudited,
   decaying copy of what the system already stores authoritatively.
4. **The one real benefit is cheap to get otherwise.** What a one-shot run lacks is
   "what was I in the middle of, and what did I learn that the queue does not
   record". That is a few hundred tokens, not a 100k-token transcript.

A **burst-scoped session** (alive within about 20 minutes, then reset, option c) is
safe but pointless: cost within 2% of one-shot on the real log, and it needs the same
non-`exec` execution path as full persistence.

A side finding worth more than the whole question: **the cross-run cache may be
broken by something specific to `agent exec`, and a stable session key might fix it**
(section 3.4). That is a cheap experiment with a bounded upside (at most about
$0.01 per overseer wake; the run-by-run ceiling is in
`research/2026-10-07-cross-run-cache.md`), so it is worth a test, not a redesign.

## 2. What openclaw supports (primary sources)

Sources: the openclaw repository's docs and source on GitHub, read through the API on
2026-10-07 (main branch; the tag `v2026.9.4`, the last version this repo recorded as
installed, for `agent-exec.ts`). Latest release at the time is `v2026.10.1-beta.1`
(published 2026-10-05). The conductor pulls `ghcr.io/openclaw/openclaw:latest`, so the
installed version is unconfirmed: the last version recorded in this repo is
2026.9.4 (`research/2026-09-18-openclaw-capabilities.md`).

**Session model (docs `concepts/session.md`, confirmed).**
- Sessions are owned by the Gateway. Sources route to session keys; cron jobs get a
  fresh session per run.
- A session keeps its `sessionId` until reset. Default reset mode is `none`: no
  automatic reset; compaction manages growth. Optional `daily` and `idle` resets
  exist, and heartbeat, cron and exec events do not extend idle freshness.
- Transcripts and session rows live in a per-agent SQLite database under the state
  directory (`agents/<id>/agent/openclaw-agent.sqlite`), archived transcript files in
  `agents/<id>/sessions/`. Maintenance prunes after 30 days or 5000 rows by default.
- Gateway restart recovery resumes an interrupted turn, preserving tool calls and
  results.

**`agent exec` (docs `cli/agent.md`, and source `src/commands/agent-exec.ts`).**
- Docs: "runs one embedded agent turn without connecting to a Gateway". `--state-dir`
  "retains sessions and other run state"; a retained state dir needs exclusive
  ownership (exec refuses to start while a Gateway or another writer holds it).
- **Source: `const sessionId = randomUUID();` on every call, passed to the agent
  command; the exec options list has no session id or key.** Confirmed identical in
  tag `v2026.9.4` and main. So `--state-dir` retains transcripts but each exec run
  starts a new session in it. This matches the repo's observation that the state dir
  is "retained for transcripts". Confidence: high for the code; the installed image
  was not inspected, but both ends of the version range agree.
- Docs vs code: no discrepancy found on this point. The docs imply persistence
  ("retain sessions") only in the sense of keeping the files.

**Ways to get a persistent session (none tried here).**
- `openclaw agent --session-key agent:<id>:<key>` or `--session-id` through the
  Gateway. Requires a running Gateway. Never run in this project; the register
  (2026-09-22) and `research/2026-09-18-openclaw-capabilities.md` section 3 chose the
  dispatcher plus queue partly for this reason. The native session-to-session lane
  was reported serialised (one concurrent operation).
- `openclaw agent --local --session-key ...` embedded. The docs say a standalone
  `--local` process may reuse a main session but refuses while Gateway restart
  recovery is pending, and that one-shot `--local` skips optional post-turn work (the
  pre-compaction memory flush) while required compaction still happens before
  inference. Whether `--local` honours a retained state dir (exec has `--state-dir`;
  `agent` documents no such flag, though exec sets `OPENCLAW_STATE_DIR`) is
  **not verified**.

**Compaction and context limits (docs `concepts/compaction.md`, `providers/deepseek.md`,
source constant).**
- DeepSeek v4 pro is listed with a 1,000,000-token context and 384,000 max output.
- Auto-compaction runs "when the session nears the context limit" or on a provider
  overflow error. The reserve floor constant is 20,000 tokens
  (`DEFAULT_AGENT_COMPACTION_RESERVE_TOKENS_FLOOR`), so the trigger is somewhere near
  980k tokens (inferred from the constant and the docs, not read from the trigger
  code). `keepRecentTokens` default 20,000. Mode defaults to `safeguard` (summary
  quality audit; required identifiers must survive). A timed-out summary commits the
  compaction without a summary, which the docs say drops older facts for good.
- A "memory flush" turn can write notes to workspace memory files before compaction.
  Not run in one-shot `--local`/exec.
- **Practical reading: at a 1M window, openclaw's compaction will essentially never
  fire at our scale before quality has already degraded.** The context-rot literature
  (section 4) shows degradation well below the window; nothing in openclaw acts on
  that.

**Session pruning (docs `concepts/session-pruning.md`).** Trims old tool results,
default off for non-Anthropic providers. If enabled for DeepSeek it rewrites old
messages, which by construction invalidates the DeepSeek prefix cache from the first
cleared result. So the one openclaw mechanism that limits tool-result bloat conflicts
with the cache.

**System prompt and tool definitions across turns (docs `concepts/system-prompt.md`,
`concepts/context.md`, source `src/agents/system-prompt-runtime.ts`).**
- The system prompt and the tool schemas are rebuilt and resent on every request (the
  context doc shows tool schemas at roughly 8k tokens as a counted component). History
  is replayed. DeepSeek thinking sessions require replaying `reasoning_content` on
  follow-up tool turns (docs `providers/deepseek.md`); our transcripts agree (round
  7 of the newest overseer run grows by the prior round's output).
- openclaw splits the prompt at an internal cache boundary: "stable" content above,
  "volatile" below (Runtime line, Temporal Context date, Project Memory facts, and
  more). The boundary is internal metadata; for a prefix-matching provider the whole
  system message is one string, so volatile content still invalidates everything
  after it.
- openclaw's own tracker shows this repeatedly bit DeepSeek users: issue 94518
  ("DeepSeek cache hit rate under 10 percent after 6.x upgrade", closed July 2026),
  107076 (dynamic tool list before the boundary, 0% hits on exact-prefix providers,
  closed), 156977 ("prompt cache invalidated every turn: tool-set membership change
  plus dynamic system-prompt suffix", reported on 2026.9.6, closed 2026-09-24, so a
  fix may or may not be in the installed image), 96773 (turn-scoped developer
  instructions causing 20%/99% hit oscillation, closed). These are bug reports read
  from the tracker, not independently reproduced.

## 3. DeepSeek cache behaviour and cost per wake

### 3.1 What the real runs show

The newest two runs carry per-round usage in the runs DB `transcript` column
(`run-0023` overseer, `run-0022` quartermaster; the other 21 rows have no transcript,
confirmed by length). Source: read-only query of the runs database; usage per round
is `{input, cacheRead, output, reasoningTokens, total}`, and `total = input + cacheRead
+ output`, so prompt size per round = `input + cacheRead`.

| Run | Round 1 prompt | Round 1 cacheRead | Rounds | Final prompt | Output total |
|---|---|---|---|---|---|
| run-0023 overseer | 29,860 | **0** | 12 | 108,651 | 35,701 |
| run-0022 quartermaster | 11,069 | **1,408** | 8 | 62,500 | 22,789 |

- **Confirmed**: round 1 read nothing from cache for the overseer (the task's note),
  and only 1,408 tokens for the quartermaster. From round 2 on, 96 to 99% of the
  prompt is read from cache, in multiples of 64 tokens, consistent with DeepSeek
  caching at request boundaries in 64-token units. Within a run the cache works.
- Prompt growth is large: overseer 29.9k to 108.7k in one wake (about 83k added per
  wake including the briefing, tool results and replayed reasoning). Quartermaster
  11.1k to 62.5k (about 54k).
- I reproduced the pricing fit from the previous study on run-0023 by hand (inputs,
  cache reads, outputs priced at $0.435, $0.0036 and $0.87 per M reproduce the
  recorded $0.0662). Those rates are the fitted ones, not DeepSeek's list prices.

### 3.2 DeepSeek's documented cache behaviour

From `research/2026-10-07-cross-run-cache.md` (primary source read earlier today):
prefix matching only, best effort, entries cleared "usually within a few hours to a
few days", no fixed TTL, hits proven in our data at gaps up to 215 minutes, none
demonstrated after about 36 hours. A persistent session depends on that cache more
than one-shot does, because its prompt is mostly history.

### 3.3 Cost per wake (model, assumptions stated)

Model: per round, cost = input x $0.435/M + cacheRead x $0.0036/M + output x $0.87/M.
Profile: the two real runs above, assuming the briefing is 4k tokens (overseer) and 2k
(quartermaster) and so the fixed base (system prompt, tools, charter) is 25.9k and
9.1k. **The briefing sizes are assumptions; the result is insensitive to them.**
A persistent session at wake k carries the previous end-of-wake context (the sum of
all earlier growth) and adds the same per-wake behaviour. Output tokens held equal
across options (a persistent session might cut orientation rounds; unproven, not
credited). No compaction modelled (it would not fire below about 980k).

Per-wake cost by option, from a throwaway simulation over the real wake log
(23 runs, overseer 7 wakes, quartermaster 10):

| Option | Overseer per wake | Quartermaster per wake | Notes |
|---|---|---|---|
| (a) one-shot, as measured | $0.066 | $0.039 | the profile runs' actual cost |
| (a') one-shot, base prefix cached across runs | $0.055 | $0.036 | the ceiling for fixing the cross-run cache |
| (b1) persistent, cache always warm | $0.067 mean ($0.058 at 100k carried, $0.076 at 520k, $0.089 at 800k) | $0.043 mean | best case for persistence |
| (b2) persistent, cache warm only if gap is 4 hours or less | $0.089 | $0.060 | the real log has gaps of hours to 36 hours |
| (b3) persistent, cache always cold on resume | $0.184 | $0.151 | worst case |
| (c) session alive only inside a 20-minute burst, then reset | $0.065 | $0.038 | about 2% under one-shot |

Per-wake cost against carried context, the same model, shown directly:

| Carried context | Overseer warm | Overseer cold | Quartermaster warm | Quartermaster cold |
|---|---|---|---|---|
| 0 (fresh) | $0.055 | $0.066 | $0.036 | $0.040 |
| 100k | $0.058 | $0.101 | $0.038 | $0.082 |
| 200k | $0.063 | $0.149 | $0.041 | $0.128 |
| 400k | $0.071 | $0.244 | $0.047 | $0.220 |
| 800k | $0.089 | $0.434 | $0.059 | $0.404 |

Reading it:
- **Warm persistent is a wash against a perfect one-shot** ($0.055 versus $0.058 to
  $0.063 once a session carries 100k to 200k), because round 1's savings (the base
  prefix, about $0.011 for the overseer) are eaten by every round re-reading the
  carried history at $0.0036/M. Break-even is near 250k carried tokens for the
  overseer; the overseer's session reaches that after about 3 wakes.
- **Cold is the danger.** One cache miss on a carried context of 400k costs $0.24,
  four overseer wakes' worth. The cache is best-effort and cleared "after hours to
  days", our wake log has 2 to 36 hour gaps, and every deploy that touches a charter,
  tool allowlist or runtime line invalidates the whole carried prefix. One-shot's
  worst case is bounded by its small base.
- Output is untouched: 52% of cost across the 17 measured runs, so "cheaper because
  the cache holds more" cannot be the case for persistence.
- **Caveat on the one-shot baseline**: the overseer paid a full-miss round 1 in the
  newest run. If fixing that is possible (3.4), one-shot drops to (a'), widening the
  gap in its favour.
- Not modelled: the quartermaster, the architect and the consultant at other cadences;
  the planner; any wake-reduction from the wake audit
  (`research/2026-10-07-wake-audit.md`). Fewer wakes make a persistent session's
  idle gaps longer, which makes its cache colder, not warmer.

### 3.4 A cross-run cache hypothesis found along the way (medium to low confidence)

`buildRuntimeLine` in `src/agents/system-prompt-runtime.ts` (main) writes
`session=<baseSessionKey>` into the Runtime line of the system prompt, after
stripping only cron run suffixes. For an exec run, the session key resolved from the
random session id is `agent:<id>:explicit:<uuid>`
(`buildExplicitSessionIdSessionKey` in `src/agents/command/session.ts`). If that key
reaches the Runtime line (not verified for this path or for the installed version),
then **every exec run's system prompt differs at the Runtime line**, and a
prefix-matching provider can only hit what precedes it. That would explain
round 1 hitting 0 to 1,408 tokens while the repo's `--hostname` fix, which removed the
changing `host=` field, did not produce reliable hits. It is consistent with the
numbers (1,408 tokens is about the size of the stable system prompt head). It is
not proven: I could not read a rendered prompt, and the prompt section order beyond
the docs' description is unverified. A test needs one real run with prompt capture or
openclaw's cache-trace logging, which I did not do. Also unverified: whether tool
schemas serialise before or after that line for DeepSeek.

Consequence if true: a stable session key (which needs `agent --local --session-key`,
not exec) would fix round-1 misses without any persistence, by pairing a **fixed key
with a fresh transcript each wake**. That may or may not be possible (session reset
semantics); it is the cheapest experiment to run before touching the architecture.

## 4. Persistent versus stateless agents for long-running work (evidence)

Read this session (WebFetch of the source):
- **Laban, Hayashi, Zhou, Neville, "LLMs Get Lost in Multi-Turn Conversation"
  (arXiv 2505.06120).** Over 200,000 simulated conversations, "an average drop of 39%
  across six generation tasks" in multi-turn versus single-turn; the cause is that
  models "make assumptions in early turns and prematurely attempt to generate final
  solutions, on which they overly rely", and then fail to recover. A loss of some
  capability and a large increase in unreliability. Directly relevant: this is the
  stale-belief and error-compounding mechanism, measured.
- **Chroma, "Context Rot" (research page, 2025).** 18 models; performance degrades as
  input length grows even on simple tasks; distractors hurt more at long length, with
  models differing in whether they abstain or answer confidently wrong. Direct source
  for "bigger window is not better memory". (Provider-neutral; DeepSeek v4 not in the
  tested set, so applicability is by analogy.)
- **Anthropic, "Effective context engineering for AI agents".** Names context rot,
  compaction (summarise and restart, with the risk that "overly aggressive
  summarization" loses subtle but important details), structured note-taking outside
  the window, and sub-agents with clean contexts returning 1,000 to 2,000 token
  summaries. These are the same three options this memo compares.
- **Anthropic, "Effective harnesses for long-running agents".** Their long-running
  harness deliberately starts every session with no memory ("each new session begins
  with no memory of what came before") and bridges sessions with an explicit progress
  file, a structured feature list the agent may only mark done, and git history, read
  at the start of each session. That is the stateless-plus-notebook shape, from a
  group with every incentive to prefer persistence.
- **Packer et al., MemGPT (arXiv 2310.08560).** Tiered memory with the model paging
  between a small main context and external stores. Its premise is the same as the
  conclusion here: the window is not the memory.

From recall, not re-fetched this session (treat as pointers, medium confidence):
Liu et al., "Lost in the Middle" (TACL 2024; position-dependent recall); Hsieh et al.,
RULER (2024; effective context length shorter than the claimed window); Park et al.,
Generative Agents (2023; a memory stream, retrieval by recency, importance and
relevance, and periodic reflection that writes distilled higher-level notes); Wang et
al., Voyager (2023; a skill library of verified code, retrieved by description, which
is the repo's playbook idea); Shinn et al., Reflexion (2023; verbal self-reflections
carried into the next trial). Cognition's "Don't build multi-agents" write-up on
summarisation as a lossy bottleneck is another pointer.

What the evidence supports, and does not:
- Supports: carrying a long raw transcript across a changing environment degrades
  reliability and compounds early mistakes; summarising it loses details; bounded,
  curated, externally stored notes plus fresh context is the pattern production
  long-running harnesses converge on.
- Does not show: that persistence loses on every task. For tasks where the world is
  static and the history is the task (a long conversation, a code review), a live
  session is natural. Our agents are the reverse: a world that changes under them,
  with an authoritative external record.
- No direct evidence exists for DeepSeek v4 pro in this regime. Everything above is
  other models; the direction is consistent but the magnitude is unmeasured for ours.

## 5. Fit with this repo

- **The architecture already chose statelessness on purpose.** Register 2026-09-22
  (agent loop MVP: "one-shot runs over the queue"), `docs/AGENT-LOOP.md` section 1
  ("independent one-shot `agent exec` run with fresh context; roles talk only through
  `dfqueue`"; the Gateway, heartbeat and `sessions_send` are not used), and
  `research/2026-09-18-openclaw-capabilities.md`. Persistence reverses that, and
  adds a Gateway or a new embedded path, plus the session-store write ownership
  constraint (exclusive state dir).
- **The queue is the durable record, and cited facts are re-read by the server.** A
  persistent session's memory of a proposal, ruling or stock reading would be a
  second copy that can disagree with the first. The briefing already carries the
  working memory that matters: `conductor/briefing.py` builds "DECIDED, DO NOT REDO"
  from `queue.pending_brief` (open projects, the last rulings), in a deliberate
  stable-first order for caching.
- **The documented failure that persistence would worsen is proposal repetition.**
  The wake audit (`research/2026-10-07-wake-audit.md`) found the same facts producing
  repeat proposals and repeated defers. A persistent session that "remembers" drink
  was 0 would anchor on it (the Laban mechanism), where a fresh run re-reads the
  stocks tool. That argues for state read from tools each wake, which the stateless
  design already forces.
- **The memory architecture is about durable stores, not conversation state**
  (`docs/MEMORY-ARCHITECTURE.md`: chronicle, doctrine, playbooks, fort dossier;
  retrieval by tool, "not context-stuffing"; the dossier "is still uncoded" and is
  named the gating piece for per-cycle learning). A per-role notebook is a thin slice
  of the dossier, and fits that document's own direction: the dossier row says
  "working state: landmarks, plans, open problems, always loaded".
- **The Planner's `fort_plan`** (`research/2026-10-07-planner-design.md`, in flight)
  is already a versioned, queue-resident, server-validated document rendered into the
  prompt. It is the notebook pattern for plan state. A per-role notebook should reuse
  its storage and rendering, not invent a second mechanism.
- **Observability and the stream.** Every inter-agent message with sender, recipient
  and rationale is an agreed requirement. A notebook entry that is a queue record is
  joinable to tool calls like everything else. A hidden session transcript is not.

## 6. If a per-role notebook is built (proposed design, nothing built)

Shape (all **proposed**):
- **One slot per role**, a single record in the queue store, overwritten by
  `notebook.set` (never appended), so it cannot grow. Hard cap, for example 1,500
  tokens (about 6 KB); the write tool rejects over-cap and tells the role to prune.
  Versioned (id, supersedes, tick written) so the history is audited and the stream
  can show diffs.
- **Contents are intent and open threads only, never facts about the fort.** Allowed
  kinds: `watching` (what I am waiting to see, and the signal to check),
  `learned` (a lesson the queue does not record: "direct brew jobs stall when no
  barrel is free, see gotcha-N"), `next` (the first step I intend on the next wake),
  `avoid` (an approach tried and why it failed). A fact the fort can state (a stock
  level, a position) is refused by schema or flagged `stale_after_tick`, because the
  conductor should re-read those.
- **Injected by the conductor, after the stable prefix and before the ask**, as a
  labelled block ("YOUR NOTES FROM YOUR LAST WAKE, written at tick N, treat as
  unverified"), with its age. It rides in the briefing, the position already last in
  the prompt, so it cannot disturb the cache prefix.
- **Staleness controls**: every entry carries its tick and an expiry (default a few
  game days, so a note from before a deploy or a pause expires); the briefing prints
  the age; the conductor drops entries whose referenced proposal or project is closed
  (it can look that up). The role's charter says notes are hypotheses and the tools
  are ground truth.
- **Who writes it**: the role, as the last action of its wake, using a tool already
  allowed to that role only (no cross-role reads; the Overseer remains the sole
  writer of rulings, `agents/ROSTER.yaml` `sole_writer`). The server, not the role,
  stamps tick and role from the credential.
- **Fits openclaw without openclaw's memory**: exec skips workspace bootstrap files,
  so openclaw's `MEMORY.md` route would not load anyway, and it is not auditable. A
  queue-backed notebook works with `agent exec` unchanged.
- **Verification before adopting**: A/B on the repeat-proposal metric from the wake
  audit (duplicate or deferred-repeat proposals per day), not on cost. Keep it small:
  if the notebook ends up carrying fort state, it has become the stale persistent
  session by another name.
- Cost: about 1.5k extra prompt tokens per wake, $0.0007 per wake at a cache miss
  (1.5k x $0.435/M), nothing material.

## 7. Recommendation and trade-offs

**Recommendation.** (1) Stay one-shot. (2) Run the cheap cache experiment in 3.4
(stable session key, fresh transcript), because the largest measurable inefficiency is
round-1 misses and it needs no architecture change. (3) If continuity is wanted, build
the capped notebook in section 6, scoped to `watching`, `learned`, `next` and `avoid`,
on top of the queue and the Planner's plan storage. (4) Do not start a Gateway for
this; if a Gateway is ever adopted for other reasons, revisit, still with the
notebook, not an infinite transcript.

| | One-shot (today) | Persistent | Burst-scoped | One-shot + notebook (recommended) |
|---|---|---|---|---|
| Needs a new execution path | no | yes (Gateway or `--local`) | yes | no |
| Cost per wake (overseer) | $0.055 to $0.066 | $0.067 warm best case, $0.089 realistic, $0.18 cold | $0.065 | about $0.056 to $0.067 |
| Stale beliefs | none by construction | high, grows with gaps | low | low if notes are expiring and labelled |
| Cache dependence | low (small base) | very high | low | low |
| Deploy blast radius | none | a charter or tool change cold-starts a 100k to 800k prefix | small | none |
| Auditability | queue plus transcript | transcript only | partial | queue, joinable |
| Continuity | none beyond the briefing | full, decaying | within 20 min | curated, bounded |
| Where it wins | simplicity, correctness | long single tasks in a static world | none significant | repeated-proposal wakes |

Trade-offs accepted by this recommendation: the roles re-derive orientation every
wake (they pay roughly the same rounds each time), and a lesson the role does not
write down is lost. The notebook is the mitigation, and its failure mode (an
over-trusted stale note) is the one to test for.

When to revisit: if wakes become genuinely conversational (the Overseer in a tight
loop with the Architect over minutes), or if a measured benefit appears from the A/B
above. Persistence would then be worth a bounded trial on one role with
`--local --session-key`, a hard cap on carried tokens (say 150k) and a daily reset.

## 8. Not verified

- **Installed openclaw version.** The image is `:latest`; docker is not readable by the
  SSH user, and no `--version` run was permitted. Last recorded: 2026.9.4. Findings
  about `agent exec` were confirmed at that tag and at main; the cache bug reports
  (2026.5 to 2026.9.6) may or may not be fixed in the installed image.
- **Whether `agent --local --session-key` works with a retained state dir** and how a
  session behaves across container runs. Docs suggest it can; untested by design.
- **Whether the Runtime line carries a per-run session key for exec, and prompt
  section order for DeepSeek** (3.4). Needs a captured request or cache-trace log.
- **DeepSeek cache TTL.** Not documented; the 4 hour threshold in option b2 is an
  assumption bracketed by a warm and a cold case, not a measurement.
- **Briefing token sizes** (assumed 4k and 2k) and **per-wake growth** (taken from one
  overseer run and one quartermaster run; other runs have no per-round usage, so the
  variance is unknown). Architect, consultant and the planned Planner not profiled.
- **Exact compaction trigger** (inferred from the constant, not read from the
  trigger code) and whether compaction would help or harm a deepseek reasoning
  session (reasoning replay with compaction not examined).
- **Persistent sessions' possible savings on output** (fewer orientation rounds) were
  not credited and not measured.
- **No evidence specific to DeepSeek v4 pro** on long-context degradation; the papers
  tested other models. The recalled citations in section 4 were not re-fetched.
- The cost rates used are the fitted ones from the previous study, not DeepSeek's list
  prices; the ratios between options hold (cold is about 120 times a hit in any case),
  the absolute dollars scale with the rates.

## Sources

Repo: `conductor/runner.py` (`build_command`), `conductor/briefing.py`,
`docs/AGENT-LOOP.md`, `docs/MEMORY-ARCHITECTURE.md`,
`research/2026-10-07-cross-run-cache.md`, `research/2026-10-07-wake-audit.md`,
`research/2026-10-07-planner-design.md`, `research/2026-09-18-openclaw-capabilities.md`,
`decisions/DECISIONS.md` (2026-09-22 rows), runs database (read-only).

openclaw (GitHub): `docs/cli/agent.md`, `docs/cli/resume.md`, `docs/concepts/session.md`,
`docs/concepts/compaction.md`, `docs/concepts/session-pruning.md`,
`docs/concepts/system-prompt.md`, `docs/concepts/context.md`, `docs/providers/deepseek.md`,
`src/commands/agent-exec.ts` (tags `v2026.9.4` and main), `src/agents/command/session.ts`,
`src/agents/system-prompt-runtime.ts`, `src/agents/agent-settings.ts`; issues 94518,
96773, 107076, 156977.

External: arXiv 2505.06120 (Laban et al.); arXiv 2310.08560 (Packer et al.); Chroma,
"Context Rot"; Anthropic Engineering, "Effective context engineering for AI agents"
and "Effective harnesses for long-running agents".
